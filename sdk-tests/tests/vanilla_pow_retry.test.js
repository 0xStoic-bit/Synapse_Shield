// Vanilla SDK: proof-of-work solver bounds and the single PoW retry with server-compatible timing.
// The transport (fetch) is scripted and the proof-of-work is hashed for real with Web Crypto. The server's three
// freshness rules from tokens.py are re-implemented below, one by one, and the cross test at the bottom runs the
// real Python verifier (verify_and_consume_token / verify_and_consume_pow) on the token the SDK built.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { decodeToken, pressKey } from "./helpers.js";

const realSetTimeout = globalThis.setTimeout;
const realDelay = (ms) => new Promise((resolve) => realSetTimeout(resolve, ms));
const SIGNED_SALT = "0123456789abcdef.1800000000000.3.deadbeef";

const sha256hex = async (s) => {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
};

const jsonResponse = (body) => ({ ok: true, json: async () => body });

/**
 * The three telemetry rules of tokens.py verify_and_consume_token, with the same constants:
 *   tokens.py:269-274  age > 60 s -> expired, ts - now > 5 s -> future, age < 1.5 s -> too fast
 *   tokens.py:310      A. Time Travel: telemetry span > token age + 0.5 s
 *   tokens.py:319-324  B. Stale: min_t < ts - 5000 or max_t > now + 2000 (epoch-ms timestamps)
 * Timestamps come from every "t", "down", "up" field (tokens.py:78, 288-301). Returns null when accepted.
 */
function serverFreshnessVerdict(token, nowMs) {
  const env = decodeToken(token);
  const ts = parseInt(env.challenge.split(".")[1], 10);
  const ageMs = nowMs - ts;
  if (ageMs / 1000 > 60) return "expired";
  if (ts - nowMs > 5000) return "future";
  if (ageMs < 1500) return "too fast";
  const times = [];
  for (const list of [env.telemetry.mouse_movements, env.telemetry.keystrokes, env.telemetry.clicks, env.telemetry.scrolls]) {
    for (const e of list) for (const f of ["t", "down", "up", "time"]) if (typeof e[f] === "number") times.push(e[f]);
  }
  if (times.length === 0) return null;
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  if ((maxT - minT) / 1000 > ageMs / 1000 + 0.5) return "time travel";
  if (minT < ts - 5000 || maxT > nowMs + 2000) return "stale";
  return null;
}

let sdk;
beforeAll(async () => {
  HTMLCanvasElement.prototype.getContext = () => null;
  vi.stubGlobal("fetch", async () => jsonResponse({ challenge: "x.1700000000000.b.s" }));
  window.fetch = globalThis.fetch;
  await import("../../src/synapse_shield/static/synapse-sdk.js");
  sdk = window.SynapseShield;
  await sdk.init();
});

/** Types `count` keys, one every `gapMs` of (mocked) time, ending at `endMs`; events go through the real listeners. */
function typeSession(count, gapMs, endMs) {
  const start = endMs - (count - 1) * gapMs;
  const spy = vi.spyOn(Date, "now");
  for (let i = 0; i < count; i++) {
    spy.mockReturnValue(start + i * gapMs);
    pressKey(window, "a", "KeyA");
  }
  spy.mockRestore();
}

describe("Vanilla solvePoW", () => {
  it("finds a real nonce at difficulties 1-4 (sha256(salt + nonce) starts with that many zero hex chars)", async () => {
    for (const difficulty of [1, 2, 3, 4]) {
      const nonce = await sdk.solvePoW(SIGNED_SALT, difficulty);
      expect((await sha256hex(SIGNED_SALT + nonce)).startsWith("0".repeat(difficulty))).toBe(true);
    }
  }, 60000);

  it("solves difficulty 5, the value core.py issues for score >= 45 (~1M hashes on average)", async () => {
    const nonce = await sdk.solvePoW(SIGNED_SALT, 5);
    expect((await sha256hex(SIGNED_SALT + nonce)).startsWith("00000")).toBe(true);
    expect(Number(nonce)).toBeLessThan(20000000);
  }, 240000);

  it("yields to the event loop between batches (never one long synchronous loop)", async () => {
    let ticks = 0;
    const timer = setInterval(() => { ticks++; }, 1);
    await sdk.solvePoW(SIGNED_SALT, 4);
    clearInterval(timer);
    expect(ticks).toBeGreaterThan(0);
  }, 60000);
});

describe("Vanilla submit() PoW retry", () => {
  const challengeBody = { status: "challenge_required", action: "challenge", pow_difficulty: 1, pow_salt: SIGNED_SALT };
  let submits;

  /** Scripted server on a fake clock (Date + setTimeout); real timers stay available through realDelay. */
  function installServer(responses) {
    submits = [];
    let n = 0;
    const fetchMock = vi.fn(async (url, init) => {
      if (String(url).startsWith("/api/challenge")) return jsonResponse({ challenge: `n${++n}.${Date.now()}.bind.sig` });
      const body = JSON.parse(init.body);
      submits.push({ body, at: Date.now() });
      return jsonResponse(responses.shift());
    });
    vi.stubGlobal("fetch", fetchMock);
    window.fetch = fetchMock;
  }

  /** Drives the fake clock until `promise` settles; fake time moves 1 s per real 5 ms. */
  async function runUntilSettled(promise) {
    let done = false;
    const tracked = promise.finally(() => { done = true; });
    while (!done) {
      await realDelay(5);
      await vi.advanceTimersByTimeAsync(1000);
    }
    return tracked;
  }

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    sdk.reset();
    sdk.currentChallenge = null;
    sdk.challengeCreatedAt = 0;
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  for (const sessionMs of [900, 20000, 45000, 120000]) {
    it(`a ${sessionMs / 1000} s typing session retries with telemetry that passes all three tokens.py rules`, async () => {
      installServer([{ ...challengeBody }, { status: "allowed" }]);
      await sdk.refreshChallenge();
      // The session ended "now": 25 keystroke pairs (the SDK keeps the last 50 events).
      typeSession(25, Math.max(10, Math.floor(sessionMs / 24)), Date.now());
      const result = await runUntilSettled(sdk.submit("/api/login"));

      expect(result.status).toBe("allowed");
      expect(submits).toHaveLength(2);
      const [first, second] = submits.map((s) => s.body);
      expect(first.pow_nonce).toBeUndefined();
      expect(second.pow_salt).toBe(SIGNED_SALT);
      expect((await sha256hex(SIGNED_SALT + second.pow_nonce)).startsWith("0")).toBe(true);
      // Single-use: the retry carries a fresh challenge.
      expect(decodeToken(second.token).challenge).not.toBe(decodeToken(first.token).challenge);
      // Every session length is accepted: the retry waits at most ~3 s and sends the most recent window that fits
      // (no 30-55 s wait, no Time Travel for sessions longer than 30.4 s).
      expect(serverFreshnessVerdict(second.token, submits[1].at)).toBeNull();
      expect(submits[1].at - submits[0].at).toBeLessThanOrEqual(5000);
      const keys = decodeToken(second.token).telemetry.keystrokes;
      expect(keys.length).toBeGreaterThan(0);
    }, 60000);
  }

  it("a second challenge_required is returned to the caller after exactly two requests (single retry)", async () => {
    installServer([{ ...challengeBody }, { ...challengeBody, pow_salt: "aa.1800000000001.1.bb" }, { status: "allowed" }]);
    await sdk.refreshChallenge();
    typeSession(5, 100, Date.now());
    const result = await runUntilSettled(sdk.submit("/api/login"));
    expect(result.status).toBe("challenge_required");
    expect(submits).toHaveLength(2);
  }, 60000);

  it("retryWithPoW=true never starts another PoW round", async () => {
    installServer([{ ...challengeBody }, { status: "allowed" }]);
    await sdk.refreshChallenge();
    const result = await runUntilSettled(sdk.submit("/api/login", true));
    expect(result.status).toBe("challenge_required");
    expect(submits).toHaveLength(1);
  }, 60000);
});

// End-to-end: the Python server code verifies the real retry token (and PoW) the vanilla SDK builds after a
// 20 s keyboard-only session. Real clock, real hashing, real HMAC challenges. Skipped without Python + synapse_shield.
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
  SYNAPSE_DB_PATH: path.join(mkdtempSync(path.join(tmpdir(), "synapse-vanilla-pow-")), "nonces.db"),
};
const runPy = (code, args = []) => {
  const r = spawnSync(PY[0], [...PY.slice(1), "-c", code, ...args], { encoding: "utf8", env: pyEnv });
  if (r.status !== 0) throw new Error(r.stderr);
  return r.stdout.trim();
};

describe.skipIf(!PY)("Vanilla submit() retry vs Python verify_and_consume_token", () => {
  it("a 20 s keyboard-only session: the retry token and PoW are accepted by the real server verifier", async () => {
    vi.useRealTimers();
    sdk.reset();
    sdk.currentChallenge = null;
    sdk.challengeCreatedAt = 0;
    const salt = runPy("from synapse_shield.tokens import generate_pow_salt as g; print(g(difficulty=3))");
    const newChallenge = () =>
      runPy("from synapse_shield.tokens import generate_challenge as g; print(g()['challenge'])");

    let verdict = null;
    let calls = 0;
    const fetchMock = vi.fn(async (url, init) => {
      if (String(url).startsWith("/api/challenge")) return jsonResponse({ challenge: newChallenge() });
      calls++;
      if (calls === 1) return jsonResponse({ status: "challenge_required", action: "challenge", pow_difficulty: 3, pow_salt: salt });
      const body = JSON.parse(init.body);
      // Verify at send time, exactly as the server would: nonce is consumed, then the telemetry rules run.
      verdict = JSON.parse(runPy(
        "import sys, json; from synapse_shield.tokens import verify_and_consume_token as vt, verify_and_consume_pow as vp;"
        + "ok, reason, _ = vt(sys.argv[1]); pow_ok = vp(sys.argv[2], sys.argv[3]);"
        + "print(json.dumps({'ok': ok, 'reason': reason, 'pow': pow_ok}))",
        [body.token, body.pow_salt, String(body.pow_nonce)],
      ));
      return jsonResponse({ status: "allowed" });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.fetch = fetchMock;

    await sdk.refreshChallenge();
    typeSession(25, 830, Date.now()); // ~20 s of typing that ended now
    const result = await sdk.submit("/api/login");

    expect(result.status).toBe("allowed");
    expect(calls).toBe(2);
    expect(verdict).toEqual({ ok: true, reason: expect.any(String), pow: true });
  }, 120000);
});
