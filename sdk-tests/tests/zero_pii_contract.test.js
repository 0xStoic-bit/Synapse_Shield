// Zero-PII keystroke contract — the same assertions run against Vanilla JS, React and Vue.
//
// The guarantee under test (README / CHANGELOG v0.10.4): no typed character, in any field,
// ever leaves the browser. Only "masked" or a functional key name may appear in telemetry,
// while timing features (dwell, flight, digraph frequency) stay intact.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { adapters } from "./adapters.js";
import {
  FUNCTIONAL_KEYS,
  MULTI_UNIT_CHARACTER_KEYS,
  PLAIN_TEXT,
  SECRET_TEXT,
  assertNoRawCharacters,
  makeInput,
  pressKey,
  typeText,
} from "./helpers.js";

beforeAll(() => {
  // jsdom has no WebGL/canvas; return null instead of logging "not implemented" noise.
  HTMLCanvasElement.prototype.getContext = () => null;
});

for (const [id, adapter] of Object.entries(adapters)) {
  describe(`${adapter.name} — Zero-PII keystroke contract`, () => {
    let sdk;

    beforeEach(async () => {
      document.body.innerHTML = "";
      sdk = await adapter.create();
      await sdk.start();
      // Clear digraph memory carried over from a previous test, then drop that key too.
      pressKey(document.body, "Shift");
      sdk.reset();
    });

    afterEach(async () => {
      await sdk.stop();
      vi.useRealTimers();
    });

    it("masks every printable character typed into a normal field", () => {
      const input = makeInput({ type: "text", name: "search" });
      typeText(input, PLAIN_TEXT);
      const env = sdk.envelope();
      expect(env.telemetry.keystrokes.length).toBe(Array.from(PLAIN_TEXT).length * 2);
      assertNoRawCharacters(expect, env, [PLAIN_TEXT]);
      for (const ks of env.telemetry.keystrokes) expect(ks.key).toBe("masked");
    });

    it("masks non-ASCII (Turkish) letters, digits and symbols", () => {
      const input = makeInput({ type: "text", name: "comment" });
      typeText(input, SECRET_TEXT);
      assertNoRawCharacters(expect, sdk.envelope(), [SECRET_TEXT]);
    });

    it.each(MULTI_UNIT_CHARACTER_KEYS)(
      "masks a single key press whose value is longer than one UTF-16 unit: %s",
      (key) => {
        const input = makeInput({ type: "text", name: "chat" });
        pressKey(input, key);
        const keys = sdk.envelope().telemetry.keystrokes.map((k) => k.key);
        expect(keys).toEqual(["masked", "masked"]);
      },
    );

    it("preserves functional key names (lower-cased) outside sensitive fields", () => {
      const input = makeInput({ type: "text", name: "notes" });
      for (const key of FUNCTIONAL_KEYS) pressKey(input, key);
      const downs = sdk.envelope().telemetry.keystrokes.filter((k) => k.type === "down").map((k) => k.key);
      expect(downs).toEqual(FUNCTIONAL_KEYS.map((k) => k.toLowerCase()));
    });

    it.each([
      [{ type: "password", name: "pw" }],
      [{ type: "text", name: "credit_card_number" }],
      [{ type: "text", id: "cvv" }],
      [{ type: "text", autocomplete: "cc-number" }],
      [{ type: "text", autocomplete: "one-time-code", name: "otp_token" }],
    ])("masks functional keys too inside a sensitive field %j", (attrs) => {
      const input = makeInput(attrs);
      typeText(input, SECRET_TEXT);
      pressKey(input, "Backspace");
      pressKey(input, "Enter");
      const env = sdk.envelope();
      for (const ks of env.telemetry.keystrokes) expect(ks.key).toBe("masked");
    });

    it("never serialises typed text anywhere in the token envelope", () => {
      const pw = makeInput({ type: "password", name: "password" });
      const user = makeInput({ type: "text", name: "username" });
      typeText(user, "mustafa.gungor");
      typeText(pw, SECRET_TEXT);
      const json = JSON.stringify(sdk.envelope());
      for (const fragment of ["mustafa", "gungor", "Gizli", "gizli", "fre-", "ğüİ"]) {
        expect(json.includes(fragment), `"${fragment}" found in envelope`).toBe(false);
      }
    });

    it("keeps client-side digraph scoring while masking (\"th\" is a frequent digraph)", () => {
      const input = makeInput({ type: "text", name: "q" });
      typeText(input, "th");
      const ks = sdk.envelope().telemetry.keystrokes;
      expect(ks.map((k) => k.key)).toEqual(["masked", "masked", "masked", "masked"]);
      const hDown = ks[2];
      expect(hDown.type).toBe("down");
      expect(hDown.is_freq_digraph).toBe(true);
    });

    it("records dwell time on keyup for masked keys", () => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(1_800_000_000_000);
      const input = makeInput({ type: "text", name: "q" });
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "a", code: "KeyA", bubbles: true }));
      vi.setSystemTime(1_800_000_000_087);
      input.dispatchEvent(new KeyboardEvent("keyup", { key: "a", code: "KeyA", bubbles: true }));
      const up = sdk.envelope().telemetry.keystrokes.find((k) => k.type === "up");
      expect(up.key).toBe("masked");
      expect(up.duration_ms).toBe(87);
    });

    it("caps the keystroke buffer at 50 events", () => {
      const input = makeInput({ type: "text", name: "q" });
      typeText(input, "a".repeat(40)); // 80 events
      expect(sdk.envelope().telemetry.keystrokes.length).toBe(50);
    });

    it("reset() clears buffered keystrokes", () => {
      const input = makeInput({ type: "text", name: "q" });
      typeText(input, "abc");
      sdk.reset();
      expect(sdk.envelope().telemetry.keystrokes).toEqual([]);
    });

    if (id !== "vanilla") {
      it("detaches key listeners on unmount", async () => {
        const input = makeInput({ type: "text", name: "q" });
        await sdk.stop();
        const before = sdk.keystrokes().length;
        typeText(input, "xyz");
        expect(sdk.keystrokes().length).toBe(before);
        // Re-create so afterEach can stop cleanly.
        sdk = await adapter.create();
        await sdk.start();
      });
    }
  });
}
