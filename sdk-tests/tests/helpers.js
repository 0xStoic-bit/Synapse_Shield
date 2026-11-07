// Shared helpers for the Synapse Shield SDK test suite.
import { vi } from "vitest";

export const CHALLENGE = "testnonce.1700000000000.bindhash.signature";

/** Stub global fetch so `/api/challenge` returns a deterministic challenge. */
export function mockChallengeFetch() {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => ({ challenge: CHALLENGE }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  window.fetch = fetchMock;
  return fetchMock;
}

/** Decode a `{ token }` payload produced by any SDK back into its JSON envelope. */
export function decodeToken(token) {
  const binary = atob(token);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

/** Fire a keydown/keyup pair on `target` (bubbles to window like a real key press). */
export function pressKey(target, key, code = "") {
  const opts = { key, code, bubbles: true, cancelable: true };
  target.dispatchEvent(new KeyboardEvent("keydown", opts));
  target.dispatchEvent(new KeyboardEvent("keyup", opts));
}

/** Type a whole string one key at a time (iterating by code point, as a keyboard would). */
export function typeText(target, text) {
  for (const ch of Array.from(text)) pressKey(target, ch);
}

export function makeInput(attrs = {}) {
  const el = document.createElement("input");
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  document.body.appendChild(el);
  return el;
}

/**
 * Key values a browser reports as a single printed "character" that are longer than one
 * UTF-16 code unit — the cases a naive `key.length === 1` mask lets through.
 */
export const MULTI_UNIT_CHARACTER_KEYS = [
  "😀", // emoji (surrogate pair, length 2)
  "𝒜", // mathematical script letter outside the BMP (length 2)
  "لا", // Arabic lam-alef ligature key on Arabic layouts (length 2)
  "é", // "e" + combining acute accent (length 2)
  "İ", // Turkish dotted capital I: "İ".toLowerCase() === "i̇" (length 2)
  // Whole words that arrive in KeyboardEvent.key via word completion / IME commit. They look like
  // key names to a regex ([A-Z][A-Za-z0-9]+) but are not on the closed allow-list.
  "Mustafa",
  "Sifre123",
  "Ankara",
  "Ab",
];

/** Named (non-printing) keys whose names are not PII and must be preserved. */
export const FUNCTIONAL_KEYS = ["Enter", "Backspace", "Tab", "Shift", "ArrowLeft", "Unidentified", "Process", "F12", "Escape", "Delete"];

/** PII strings typed in the tests; none of them may ever appear in a serialized payload. */
export const SECRET_TEXT = "Ş1fre-Gizli_42!ğüİ";
export const PLAIN_TEXT = "the quick brown fox 2026";

/**
 * Assert that a decoded telemetry envelope carries no raw typed characters:
 * every keystroke key is either "masked" or a lower-cased functional key name.
 */
export function assertNoRawCharacters(expect, envelope, typedStrings) {
  const allowed = new Set(["masked", ...FUNCTIONAL_KEYS.map((k) => k.toLowerCase())]);
  const keystrokes = envelope.telemetry.keystrokes;
  for (const ks of keystrokes) {
    expect(allowed.has(ks.key), `leaked key value: ${JSON.stringify(ks.key)}`).toBe(true);
  }
  const serializedKeys = JSON.stringify(keystrokes);
  for (const s of typedStrings) {
    for (const ch of Array.from(s)) {
      if (ch === " ") continue;
      // Only inspect key values (timestamps contain digits legitimately).
      const leaked = keystrokes.some((ks) => ks.key === ch || ks.key === ch.toLowerCase());
      expect(leaked, `character ${JSON.stringify(ch)} leaked in ${serializedKeys}`).toBe(false);
    }
  }
}
