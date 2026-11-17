// React hook: automatic proof-of-work retry on HTTP 429 `challenge_required`.
// The transport (fetch) is scripted, but the proof-of-work itself is computed for real with Web Crypto.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { decodeToken } from "./helpers.js";
import { solvePow } from "../../synapse-shield-react/src/pow.ts";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
const sha256hex = async (s) => {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
};
const SIGNED_SALT = "0123456789abcdef.1800000000000.3.deadbeef";

/** A challenge shaped like the server's (`nonce.ts.bind.sig`) whose timestamp is "now", like a real fetch. */
let challengeCounter = 0;
const newChallenge = () => `n${++challengeCounter}.${Date.now()}.bind.sig`;

const jsonResponse = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** Scripted server: challenge endpoint + a protected endpoint answering from `submitResponses`. */
function installServer(submitResponses) {
  const submits = [];
  const fetchMock = vi.fn(async (url, init) => {
    if (String(url).startsWith("/api/challenge")) return jsonResponse(200, { challenge: newChallenge() });
    const body = JSON.parse(init.body);
    submits.push({ url, body, at: Date.now() });
    const next = submitResponses.shift();
    return jsonResponse(next.status, next.body);
  });
  vi.stubGlobal("fetch", fetchMock);
  window.fetch = fetchMock;
  return { submits, fetchMock };
}

async function mountHook() {
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
  return { api: () => api, unmount: () => act(async () => root.unmount()) };
}

/** Runs submitProtected inside act() so the hook's state updates are flushed like in a real render. */
async function submit(api) {
  let res;
  await act(async () => {
    res = await api.submitProtected("/api/login", buildBody);
  });
  return res;
}

const buildBody = (p) => ({ user: "u", synapse_token: p.token, pow_salt: p.pow_salt, pow_nonce: p.pow_nonce });

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = () => null;
});

describe("React solvePow", () => {
  it("returns a nonce whose sha256(salt + nonce) has the required zero hex prefix, at every difficulty", async () => {
    for (const difficulty of [1, 2, 3, 4]) {
      const result = await solvePow(SIGNED_SALT, difficulty);
      expect(result).not.toBeNull();
      expect(result.salt).toBe(SIGNED_SALT);
      expect((await sha256hex(SIGNED_SALT + result.nonce)).startsWith("0".repeat(difficulty))).toBe(true);
    }
  });

  it("returns null for an empty salt and when the attempt budget is exhausted", async () => {
    expect(await solvePow("", 3)).toBeNull();
    expect(await solvePow(SIGNED_SALT, 64, 2000)).toBeNull(); // 64 zero nibbles is unreachable
  });
});

describe("React submitProtected - PoW retry", () => {
  let mounted;
  beforeEach(() => {
    document.body.innerHTML = "";
  });
  afterEach(async () => {
    if (mounted) await mounted.unmount();
    mounted = null;
  });

  it("429 challenge_required -> solves -> second request carries valid pow fields and a fresh token -> 200", async () => {
    const server = installServer([
      { status: 429, body: { status: "challenge_required", action: "challenge", pow_difficulty: 3, pow_salt: SIGNED_SALT } },
      { status: 200, body: { status: "allowed" } },
    ]);
    mounted = await mountHook();
    const api = mounted.api();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a", code: "KeyA" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "a", code: "KeyA" }));

    const res = await submit(api);
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("allowed");

    expect(server.submits).toHaveLength(2);
    const [first, second] = server.submits.map((s) => s.body);
    expect(first.pow_nonce).toBeUndefined();
    expect(second.pow_salt).toBe(SIGNED_SALT);
    expect(typeof second.pow_nonce).toBe("number");
    expect((await sha256hex(SIGNED_SALT + second.pow_nonce)).startsWith("000")).toBe(true);

    // Single-use challenges: the retry must use a different token than the first request.
    const env1 = decodeToken(first.synapse_token);
    const env2 = decodeToken(second.synapse_token);
    expect(env2.challenge).not.toBe(env1.challenge);
    // Server rules: token age >= 1.5 s at send time, and telemetry not older than challenge_ts - 5 s.
    const ts2 = parseInt(env2.challenge.split(".")[1], 10);
    expect(server.submits[1].at - ts2).toBeGreaterThanOrEqual(1500);
    const times = env2.telemetry.keystrokes.map((k) => k.t);
    expect(times.length).toBeGreaterThan(0);
    expect(Math.min(...times)).toBeGreaterThanOrEqual(ts2 - 5000);
  }, 20000);

  it("does not loop: a second 429 is returned to the caller after exactly two requests", async () => {
    const challenge = { status: "challenge_required", action: "challenge", pow_difficulty: 3, pow_salt: SIGNED_SALT };
    const server = installServer([
      { status: 429, body: challenge },
      { status: 429, body: { ...challenge, pow_salt: "aa.1800000000001.3.bb" } },
      { status: 200, body: { status: "allowed" } }, // must never be requested
    ]);
    mounted = await mountHook();
    const res = await submit(mounted.api());
    expect(res.status).toBe(429);
    expect(server.submits).toHaveLength(2);
  }, 20000);

  it("returns non-PoW responses untouched without retrying (200 and non-challenge 429)", async () => {
    const server = installServer([
      { status: 200, body: { status: "allowed" } },
      { status: 429, body: { error: "rate limited" } },
    ]);
    mounted = await mountHook();
    const ok = await submit(mounted.api());
    expect(ok.status).toBe(200);
    const limited = await submit(mounted.api());
    expect(limited.status).toBe(429);
    expect(server.submits).toHaveLength(2);
  }, 20000);
});

// End-to-end against the real Python server verifier: salt from generate_pow_salt, nonce from the React solver,
// verdict from verify_and_consume_pow (incl. single-use consumption). Skipped when no Python with synapse_shield.
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
  SYNAPSE_SECRET_KEY: "ab".repeat(32),
  SYNAPSE_DB_PATH: path.join(mkdtempSync(path.join(tmpdir(), "synapse-pow-")), "nonces.db"),
};
const runPy = (code, args = []) => {
  const r = spawnSync(PY[0], [...PY.slice(1), "-c", code, ...args], { encoding: "utf8", env: pyEnv });
  if (r.status !== 0) throw new Error(r.stderr);
  return r.stdout.trim();
};

describe.skipIf(!PY)("React solvePow vs Python verify_and_consume_pow", () => {
  it("server accepts the React nonce once and rejects its replay", async () => {
    const salt = runPy(
      "from synapse_shield.tokens import generate_pow_salt; print(generate_pow_salt(client_ip='203.0.113.7', difficulty=4))",
    );
    const solved = await solvePow(salt, 4);
    expect(solved).not.toBeNull();
    const verify =
      "import sys; from synapse_shield.tokens import verify_and_consume_pow as v; print(v(sys.argv[1], sys.argv[2], client_ip='203.0.113.7'))";
    expect(runPy(verify, [salt, String(solved.nonce)])).toBe("True");
    expect(runPy(verify, [salt, String(solved.nonce)])).toBe("False"); // replay
  }, 60000);
});
