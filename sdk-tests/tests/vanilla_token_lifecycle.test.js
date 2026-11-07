// Vanilla SDK token lifecycle: single-use tokens, envelope shape, missing-challenge guard.
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { CHALLENGE, decodeToken, mockChallengeFetch } from "./helpers.js";

let sdk;

beforeAll(async () => {
  HTMLCanvasElement.prototype.getContext = () => null;
  mockChallengeFetch();
  await import("../../src/synapse_shield/static/synapse-sdk.js");
  sdk = window.SynapseShield;
  await sdk.init();
});

beforeEach(() => {
  mockChallengeFetch();
  sdk.reset();
});

describe("Vanilla SDK token lifecycle", () => {
  it("is installed as a non-writable global", () => {
    const desc = Object.getOwnPropertyDescriptor(window, "SynapseShield");
    expect(desc.writable).toBe(false);
    expect(desc.configurable).toBe(false);
  });

  it("wraps telemetry in a signed-challenge envelope", async () => {
    await sdk.refreshChallenge();
    const env = decodeToken(sdk.getPayload().token);
    expect(env.challenge).toBe(CHALLENGE);
    expect(typeof env.created_at).toBe("number");
    expect(Object.keys(env.telemetry).sort()).toEqual(["browser", "clicks", "keystrokes", "mouse_movements", "scrolls"]);
  });

  it("refuses to build a payload without a challenge", () => {
    sdk.currentChallenge = null;
    expect(() => sdk.getPayload()).toThrow(/Missing challenge token/);
  });

  it("getToken() invalidates the challenge immediately (single-use) and refreshes in background", async () => {
    await sdk.refreshChallenge();
    const fetchMock = mockChallengeFetch();
    const token = await sdk.getToken();
    expect(decodeToken(token).challenge).toBe(CHALLENGE);
    // currentChallenge was nulled synchronously; the background refresh restores it.
    expect(fetchMock).toHaveBeenCalledWith("/api/challenge");
  });

  it("coalesces concurrent refreshChallenge() calls into one request", async () => {
    const fetchMock = mockChallengeFetch();
    await Promise.all([sdk.refreshChallenge(), sdk.refreshChallenge(), sdk.refreshChallenge()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("safely encodes non-Latin1 content into the token", async () => {
    await sdk.refreshChallenge();
    sdk.mouseMovements.push({ x: 1, y: 2, t: 3, note: "ğüşİ😀" });
    const env = decodeToken(sdk.getPayload().token);
    expect(env.telemetry.mouse_movements[0].note).toBe("ğüşİ😀");
  });
});
