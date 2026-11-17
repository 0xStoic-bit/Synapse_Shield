// Long SPA sessions, retries and non-keyboard input across the three SDKs, verified by the REAL Python server code
// (tokens.verify_and_consume_token / verify_and_consume_pow, engine.analyze_behavior) through py_contract.py.
// Challenges are signed in JS with the same HMAC key the Python side loads (SYNAPSE_SECRET_KEY), so their timestamp
// can be placed anywhere in the past; the verifier always runs against the real clock.
//   #13  getToken / getProtectedPayload / submitProtected after a long session (renewed or background challenge)
//   #17  input_events (autofill / paste / IME / insert): Zero-PII, key_count untouched, tolerated by the server
//   #3   Vue submitProtected (429 challenge_required -> fresh challenge -> PoW -> exactly one retry)
//   #20  retry of a 2 min session: short wait + most recent window instead of a 30-55 s wait / Time Travel
//   #21  vanilla EXPIRED retry uses the same alignment as the PoW retry
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { spawnSync } from "node:child_process";
import { createHmac, randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { createApp, defineComponent, nextTick } from "vue";
import { decodeToken, makeInput, pressKey } from "./helpers.js";

const SECRET_HEX = "ab".repeat(32);
const here = path.dirname(fileURLToPath(import.meta.url));

function findPython() {
  for (const cmd of [["py", "-3.10"], ["python3"], ["python"]]) {
    const r = spawnSync(cmd[0], [...cmd.slice(1), "-c", "import synapse_shield"], { encoding: "utf8" });
    if (r.status === 0) return cmd;
  }
  return null;
}
const PY = findPython();
const pyEnv = {
  ...process.env,
  SYNAPSE_SECRET_KEY: SECRET_HEX,
  SYNAPSE_DB_PATH: path.join(mkdtempSync(path.join(tmpdir(), "synapse-long-")), "nonces.db"),
};
function py(args, input = "") {
  const r = spawnSync(PY[0], [...PY.slice(1), path.join(here, "py_contract.py"), ...args], {
    encoding: "utf8",
    env: pyEnv,
    input,
  });
  if (r.status !== 0) throw new Error(r.stderr);
  return JSON.parse(r.stdout.trim().split("\n").pop());
}
const pyVerify = (token, pow) => py(["verify", ...(pow ? [pow.salt, String(pow.nonce)] : [])], token);

/** A server-format challenge (`nonce.ts.sig`, tokens.py) signed with the shared key at timestamp `ts`. */
function signedChallenge(ts) {
  const nonce = randomBytes(16).toString("hex");
  const sig = createHmac("sha256", Buffer.from(SECRET_HEX, "hex")).update(`${nonce}:${ts}`).digest("hex");
  return `${nonce}.${ts}.${sig}`;
}

const jsonResponse = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** Installs fetch: `/api/challenge` returns a challenge signed at the (possibly mocked) current time. */
function installFetch(onSubmit) {
  const submits = [];
  const fetchMock = vi.fn(async (url, init) => {
    if (String(url).includes("/challenge")) return jsonResponse(200, { challenge: signedChallenge(Date.now()) });
    const body = JSON.parse(init.body);
    submits.push({ body, at: Date.now() });
    return onSubmit(body, submits.length);
  });
  vi.stubGlobal("fetch", fetchMock);
  window.fetch = fetchMock;
  return submits;
}

const realNow = Date.now.bind(Date);
/** Runs `fn` with Date.now shifted `offsetMs` into the past (async-safe; real timers keep running). */
async function withClockOffset(offsetMs, fn) {
  const spy = vi.spyOn(Date, "now").mockImplementation(() => realNow() - offsetMs);
  try {
    return await fn();
  } finally {
    spy.mockRestore();
  }
}

/**
 * A human-paced session through the real listeners, ending `endAgoMs` before now: a mouse sample every 40 ms on a
 * wavy path and a key press every 2 s, over `durationMs`.
 */
function simulateSession(durationMs, endAgoMs = 200) {
  const end = realNow() - endAgoMs;
  const start = end - durationMs;
  const spy = vi.spyOn(Date, "now");
  let nextKey = start;
  for (let t = start, i = 0; t <= end; t += 40, i++) {
    spy.mockReturnValue(t);
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 200 + 150 * Math.sin(i / 25) + (i % 7), clientY: 300 + 90 * Math.cos(i / 31) }),
    );
    if (t >= nextKey) {
      pressKey(window, "a", "KeyA");
      nextKey += 2000;
    }
  }
  spy.mockRestore();
}

/** Dispatches every non-keyboard text-entry path once, carrying text that must never reach the payload. */
function simulateInputPaths() {
  const el = makeInput({ name: "email" });
  el.value = "Gizli-Autofill";
  el.dispatchEvent(new Event("input", { bubbles: true })); // autofill: plain Event, no inputType
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: "GizliTyped" }));
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertFromPaste", data: "GizliPaste" })); // counted by paste
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" })); // not an insertion
  el.dispatchEvent(new Event("paste", { bubbles: true }));
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertCompositionText", data: "Gizliİme" })); // counted by compositionend
  el.dispatchEvent(new Event("compositionend", { bubbles: true }));
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertReplacementText", data: "GizliRepl" }));
}
const EXPECTED_KINDS = ["autofill", "insert", "paste", "ime", "autofill"];

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function mountReact() {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const { useSynapseShield } = await import("../../synapse-shield-react/src/useSynapseShield.ts");
  let api = null;
  const Harness = () => {
    api = useSynapseShield();
    return null;
  };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(Harness)));
  await act(async () => flush());
  await act(async () => flush());
  return { api: () => api, unmount: () => act(async () => root.unmount()) };
}

async function mountVue() {
  const { useSynapseShield } = await import("../../synapse-shield-vue/src/useSynapseShield.ts");
  let api = null;
  const Harness = defineComponent({
    setup() {
      api = useSynapseShield();
      return () => null;
    },
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const app = createApp(Harness);
  app.mount(container);
  for (let i = 0; i < 10 && !api.isReady.value; i++) {
    await flush();
    await nextTick();
  }
  return { api: () => api, unmount: async () => app.unmount() };
}

const buildBody = (p) => ({ user: "u", synapse_token: p.token, pow_salt: p.pow_salt, pow_nonce: p.pow_nonce });

/** Protected endpoint backed by the Python verifier; optional first answer (e.g. a 429 PoW challenge). */
function verifyingServer(firstAnswer) {
  const verdicts = [];
  const submits = installFetch((body, n) => {
    if (n === 1 && firstAnswer) return jsonResponse(firstAnswer.status, firstAnswer.body);
    const token = body.synapse_token || body.token;
    const pow = body.pow_salt ? { salt: body.pow_salt, nonce: body.pow_nonce } : null;
    const v = pyVerify(token, pow);
    verdicts.push(v);
    return jsonResponse(v.ok ? 200 : 403, v.ok ? { status: "allowed" } : { status: "rejected", reason: v.reason });
  });
  return { submits, verdicts };
}

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = () => null;
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

// ----------------------------------------------------------------------------------------------------------------
describe.skipIf(!PY)("Vanilla SDK vs Python verifier", () => {
  let sdk;
  beforeAll(async () => {
    installFetch(() => jsonResponse(200, {}));
    await import("../../src/synapse_shield/static/synapse-sdk.js");
    sdk = window.SynapseShield;
    await sdk.init();
  });

  it("#13 getToken() after 2 min in an SPA (challenge renewed at use) is accepted", async () => {
    sdk.reset();
    sdk.lastMoveTime = 0; // the mocked clock of simulateSession runs behind the previous test's real-time samples
    installFetch(() => jsonResponse(200, {}));
    sdk.currentChallenge = signedChallenge(realNow() - 120000);
    sdk.challengeCreatedAt = realNow() - 120000;
    simulateSession(120000);
    const token = await sdk.getToken();
    const v = pyVerify(token);
    expect(v.reason).toBe("Geçerli");
    const tel = decodeToken(token).telemetry;
    expect(tel.mouse_movements.length).toBeGreaterThanOrEqual(3);
  }, 30000);

  it("#13 getToken() with a 10 s old background challenge after a 2 min session is accepted", async () => {
    sdk.reset();
    sdk.lastMoveTime = 0; // the mocked clock of simulateSession runs behind the previous test's real-time samples
    installFetch(() => jsonResponse(200, {}));
    sdk.currentChallenge = signedChallenge(realNow() - 10000);
    sdk.challengeCreatedAt = realNow() - 10000;
    simulateSession(120000);
    const token = await sdk.getToken();
    expect(pyVerify(token).reason).toBe("Geçerli");
    // The window the token can vouch for (~10 s) is kept, not just the last moment.
    const moves = decodeToken(token).telemetry.mouse_movements;
    expect(moves[moves.length - 1].t - moves[0].t).toBeGreaterThan(8000);
  }, 30000);

  it("#21 EXPIRED retry: 20 s session, aligned like the PoW retry, accepted; single retry", async () => {
    sdk.reset();
    sdk.lastMoveTime = 0; // the mocked clock of simulateSession runs behind the previous test's real-time samples
    const verdicts = [];
    const submits = installFetch((body, n) => {
      if (n === 1) return jsonResponse(200, { code: "EXPIRED", status: "token_expired" });
      const v = pyVerify(body.token);
      verdicts.push(v);
      return jsonResponse(200, v.ok ? { status: "allowed" } : { status: "rejected", reason: v.reason });
    });
    sdk.currentChallenge = signedChallenge(realNow() - 3000);
    sdk.challengeCreatedAt = realNow() - 3000;
    simulateSession(20000);
    const result = await sdk.submit("/api/login");
    expect(verdicts[0]?.reason).toBe("Geçerli");
    expect(result.status).toBe("allowed");
    expect(submits).toHaveLength(2);
    expect(submits[1].at - submits[0].at).toBeLessThan(5000);
  }, 30000);

  it("#20 PoW retry of a 2 min session: <= ~3 s wait, accepted with a valid PoW", async () => {
    sdk.reset();
    sdk.lastMoveTime = 0; // the mocked clock of simulateSession runs behind the previous test's real-time samples
    const salt = py(["salt", "3"]).salt;
    const verdicts = [];
    const submits = installFetch((body, n) => {
      if (n === 1) return jsonResponse(200, { status: "challenge_required", pow_difficulty: 3, pow_salt: salt });
      const v = pyVerify(body.token, { salt: body.pow_salt, nonce: body.pow_nonce });
      verdicts.push(v);
      return jsonResponse(200, v.ok ? { status: "allowed" } : { status: "rejected", reason: v.reason });
    });
    sdk.currentChallenge = signedChallenge(realNow() - 3000);
    sdk.challengeCreatedAt = realNow() - 3000;
    simulateSession(120000);
    const result = await sdk.submit("/api/login");
    expect(verdicts[0]).toMatchObject({ ok: true, pow: true });
    expect(result.status).toBe("allowed");
    expect(submits[1].at - submits[0].at).toBeLessThan(6000);
    expect(decodeToken(submits[1].body.token).telemetry.mouse_movements.length).toBeGreaterThanOrEqual(3);
  }, 60000);

  it("#17 input_events: kinds only (no content), key_count untouched, tolerated and score-neutral on the server", async () => {
    sdk.reset();
    sdk.lastMoveTime = 0; // the mocked clock of simulateSession runs behind the previous test's real-time samples
    installFetch(() => jsonResponse(200, {}));
    sdk.currentChallenge = signedChallenge(realNow() - 2000);
    sdk.challengeCreatedAt = realNow() - 2000;
    simulateInputPaths();
    expect(sdk.inputEvents.map((e) => e.kind)).toEqual(EXPECTED_KINDS);
    expect(sdk.keystrokes).toHaveLength(0);
    const token = sdk.getPayload().token;
    const json = JSON.stringify(decodeToken(token));
    expect(json).not.toMatch(/Gizli/);
    for (const ev of decodeToken(token).telemetry.input_events) expect(Object.keys(ev).sort()).toEqual(["kind", "t"]);
    const v = pyVerify(token);
    expect(v.ok).toBe(true);
    expect(v.input_events.map((e) => e.kind)).toEqual(EXPECTED_KINDS);
    expect(v.score_with).toBe(v.score_without);
    expect(v.key_count_with).toBe(0);
    expect(v.key_count_without).toBe(0);
  }, 30000);
});

// ----------------------------------------------------------------------------------------------------------------
describe.skipIf(!PY)("React SDK vs Python verifier", () => {
  let mounted;
  afterEach(async () => {
    if (mounted) await mounted.unmount();
    mounted = null;
  });

  it("#13 submitProtected() after 2 min on the page (challenge renewed at use) is accepted", async () => {
    const { verdicts } = verifyingServer();
    mounted = await withClockOffset(120000, () => mountReact()); // challenge fetched "2 min ago"
    simulateSession(118000);
    let res;
    await act(async () => {
      res = await mounted.api().submitProtected("/api/login", buildBody);
    });
    expect(verdicts[0].reason).toBe("Geçerli");
    expect(res.status).toBe(200);
  }, 30000);

  it("#13 getProtectedPayload() with a 10 s old challenge after a 2 min session is accepted", async () => {
    installFetch(() => jsonResponse(200, {}));
    mounted = await withClockOffset(10000, () => mountReact());
    simulateSession(120000);
    let payload;
    await act(async () => {
      payload = mounted.api().getProtectedPayload();
    });
    expect(pyVerify(payload.token).reason).toBe("Geçerli");
  }, 30000);

  it("#20 PoW retry of a 2 min session: short wait, accepted with a valid PoW", async () => {
    const salt = py(["salt", "3"]).salt;
    const { submits, verdicts } = verifyingServer({
      status: 429,
      body: { status: "challenge_required", action: "challenge", pow_difficulty: 3, pow_salt: salt },
    });
    mounted = await withClockOffset(3000, () => mountReact());
    simulateSession(120000);
    let res;
    await act(async () => {
      res = await mounted.api().submitProtected("/api/login", buildBody);
    });
    expect(verdicts[0]).toMatchObject({ ok: true, pow: true });
    expect(res.status).toBe(200);
    expect(submits).toHaveLength(2);
    expect(submits[1].at - submits[0].at).toBeLessThan(6000);
  }, 60000);

  it("#17 input_events recorded (kinds only), key_count untouched", async () => {
    installFetch(() => jsonResponse(200, {}));
    mounted = await withClockOffset(2000, () => mountReact());
    simulateInputPaths();
    let payload;
    await act(async () => {
      payload = mounted.api().getProtectedPayload();
    });
    const env = decodeToken(payload.token);
    expect(env.telemetry.input_events.map((e) => e.kind)).toEqual(EXPECTED_KINDS);
    expect(env.telemetry.keystrokes).toHaveLength(0);
    expect(JSON.stringify(env)).not.toMatch(/Gizli/);
    const v = pyVerify(payload.token);
    expect(v.ok).toBe(true);
    expect(v.score_with).toBe(v.score_without);
  }, 30000);
});

// ----------------------------------------------------------------------------------------------------------------
describe("Vue SDK submitProtected (scripted server)", () => {
  let mounted;
  afterEach(async () => {
    if (mounted) await mounted.unmount();
    mounted = null;
  });
  const challenge = { status: "challenge_required", action: "challenge", pow_difficulty: 2, pow_salt: "0123456789abcdef.1800000000000.2.deadbeef" };

  it("#3 does not loop: a second 429 is returned after exactly two requests", async () => {
    const answers = [
      { status: 429, body: challenge },
      { status: 429, body: { ...challenge, pow_salt: "aa.1800000000001.2.bb" } },
      { status: 200, body: { status: "allowed" } },
    ];
    const submits = installFetch(() => {
      const a = answers.shift();
      return jsonResponse(a.status, a.body);
    });
    mounted = await withClockOffset(2000, () => mountVue());
    const res = await mounted.api().submitProtected("/api/login", buildBody);
    expect(res.status).toBe(429);
    expect(submits).toHaveLength(2);
    expect(submits[0].body.pow_nonce).toBeUndefined();
    expect(submits[1].body.pow_salt).toBe(challenge.pow_salt);
    expect(decodeToken(submits[1].body.synapse_token).challenge).not.toBe(decodeToken(submits[0].body.synapse_token).challenge);
  }, 30000);

  it("#3 returns non-PoW responses untouched without retrying (200 and non-challenge 429)", async () => {
    const answers = [
      { status: 200, body: { status: "allowed" } },
      { status: 429, body: { error: "rate limited" } },
    ];
    const submits = installFetch(() => {
      const a = answers.shift();
      return jsonResponse(a.status, a.body);
    });
    mounted = await withClockOffset(2000, () => mountVue());
    expect((await mounted.api().submitProtected("/api/login", buildBody)).status).toBe(200);
    expect((await mounted.api().submitProtected("/api/login", buildBody)).status).toBe(429);
    expect(submits).toHaveLength(2);
  }, 30000);
});

describe.skipIf(!PY)("Vue SDK vs Python verifier", () => {
  let mounted;
  afterEach(async () => {
    if (mounted) await mounted.unmount();
    mounted = null;
  });

  it("#13 getProtectedPayload() with a 10 s old challenge after a 2 min session is accepted", async () => {
    installFetch(() => jsonResponse(200, {}));
    mounted = await withClockOffset(10000, () => mountVue());
    simulateSession(120000);
    const payload = mounted.api().getProtectedPayload();
    expect(pyVerify(payload.token).reason).toBe("Geçerli");
  }, 30000);

  it("#13 submitProtected() after 2 min on the page (challenge renewed at use) is accepted", async () => {
    const { verdicts } = verifyingServer();
    mounted = await withClockOffset(120000, () => mountVue());
    simulateSession(118000);
    const res = await mounted.api().submitProtected("/api/login", buildBody);
    expect(verdicts[0].reason).toBe("Geçerli");
    expect(res.status).toBe(200);
  }, 30000);

  it("#3 + #20 PoW retry of a 2 min session: one retry, short wait, accepted with a valid PoW", async () => {
    const salt = py(["salt", "3"]).salt;
    const { submits, verdicts } = verifyingServer({
      status: 429,
      body: { status: "challenge_required", action: "challenge", pow_difficulty: 3, pow_salt: salt },
    });
    mounted = await withClockOffset(3000, () => mountVue());
    simulateSession(120000);
    const res = await mounted.api().submitProtected("/api/login", buildBody);
    expect(verdicts[0]).toMatchObject({ ok: true, pow: true });
    expect(res.status).toBe(200);
    expect(submits).toHaveLength(2);
    expect(submits[1].at - submits[0].at).toBeLessThan(8000);
  }, 60000);

  it("#17 input_events recorded (kinds only), key_count untouched", async () => {
    installFetch(() => jsonResponse(200, {}));
    mounted = await withClockOffset(2000, () => mountVue());
    simulateInputPaths();
    const env = decodeToken(mounted.api().getProtectedPayload().token);
    expect(env.telemetry.input_events.map((e) => e.kind)).toEqual(EXPECTED_KINDS);
    expect(env.telemetry.keystrokes).toHaveLength(0);
    expect(JSON.stringify(env)).not.toMatch(/Gizli/);
  }, 30000);
});
