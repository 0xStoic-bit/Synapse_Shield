// Single-use challenge lifecycle (React + Vue) and the Vue proof-of-work solver.
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { adapters } from "./adapters.js";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = () => null;
});

for (const id of ["react", "vue"]) {
  describe(`${adapters[id].name} — single-use challenge`, () => {
    let sdk;
    beforeEach(async () => {
      document.body.innerHTML = "";
      sdk = await adapters[id].create();
      await sdk.start();
    });
    afterEach(async () => {
      await sdk.stop();
    });

    it("consumes the challenge after building a token and fetches the next one", async () => {
      const first = sdk.payload();
      expect(first.token).toBeTruthy();
      // The challenge is spent: building another token before the refresh lands must not replay it.
      expect(sdk.payload().token).toBeUndefined();
      await flush();
      await flush();
      expect(sdk.payload().token).toBeTruthy();
    });
  });
}

describe("Vue solvePow", () => {
  let sdk;
  beforeEach(async () => {
    document.body.innerHTML = "";
    sdk = await adapters.vue.create();
    await sdk.start();
  });
  afterEach(async () => {
    await sdk.stop();
  });

  const sha256hex = async (s) => {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  };

  it("solves against the server's signed salt: sha256(salt + nonce) has the required zero prefix", async () => {
    const signedSalt = "0123456789abcdef.1800000000000.3.deadbeef";
    const result = await sdk.api().solvePow(signedSalt, 3);
    expect(result).not.toBeNull();
    expect(result.salt).toBe(signedSalt); // never a client-generated salt
    expect((await sha256hex(signedSalt + result.nonce)).startsWith("000")).toBe(true);
  });

  it("is attached to the token envelope and body fields", async () => {
    const solved = await sdk.api().solvePow("aa.1.1.bb", 1);
    const payload = sdk.api().getProtectedPayload(solved);
    expect(payload.pow_salt).toBe("aa.1.1.bb");
    expect(payload.pow_nonce).toBe(solved.nonce);
  });
});
