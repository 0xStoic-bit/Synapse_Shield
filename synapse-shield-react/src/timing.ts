// Server freshness contract (tokens.py verify_and_consume_token), applied with a 100 ms safety margin:
//   token age >= 1.5 s; telemetry span <= token age + 0.5 s (Time Travel);
//   epoch-ms timestamps: min_t >= challenge_ts - 5 s (Stale Telemetry) and max_t <= now + 2 s.
// Kept identical in synapse-shield-react/src/timing.ts and synapse-shield-vue/src/timing.ts.
export const MIN_CHALLENGE_AGE_MS = 1600;
const STALE_LIMIT_MS = 4900;
const SPAN_SLACK_MS = 400;
// Retry after a fresh challenge: wait at most this long, then send the most recent window that fits...
const MAX_RETRY_WAIT_MS = 3000;
// ...unless that window would leave fewer than 3 mouse points while the session had them (engine.py rejects
// 0-2 point "teleport" sessions); then wait up to this long so the last 3 points fit.
const MAX_MOUSE_GUARD_WAIT_MS = 8000;
const TIME_FIELDS = ["t", "down", "up", "time"] as const;

export type SynapseInputKind = "autofill" | "paste" | "ime" | "insert";

type TimedEvent = { [field: string]: any };
export interface TelemetryLists {
  mouse_movements: TimedEvent[];
  clicks: TimedEvent[];
  keystrokes: TimedEvent[];
  scrolls: TimedEvent[];
  input_events: TimedEvent[];
}
const LIST_KEYS = ["mouse_movements", "clicks", "keystrokes", "scrolls", "input_events"] as const;

export function challengeTimestamp(challenge: string | null): number | null {
  if (!challenge) return null;
  const parts = challenge.split(".");
  if (parts.length < 2) return null;
  const parsed = parseInt(parts[1], 10);
  return isNaN(parsed) ? null : parsed;
}

function eventMinTime(ev: TimedEvent | undefined): number {
  let min = Infinity;
  if (!ev) return min;
  for (const f of TIME_FIELDS) {
    const v = ev[f];
    if (typeof v === "number" && v < min) min = v;
  }
  return min;
}

function bounds(t: TelemetryLists): { min: number; max: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (const key of LIST_KEYS) {
    for (const ev of t[key] || []) {
      for (const f of TIME_FIELDS) {
        const v = ev ? ev[f] : undefined;
        if (typeof v === "number") {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
  }
  return min === Infinity ? null : { min, max };
}

/**
 * Returns a copy of `t` holding only the events the server can accept for a challenge issued at `challengeTs`
 * that is `ageMs` old: the most recent window of length age + 0.4 s and, for epoch timestamps, nothing older than
 * challenge_ts - 4.9 s. An event is dropped as a whole when any of its time fields (t / down / up) is outside.
 */
export function fitTelemetry<T extends TelemetryLists>(t: T, challengeTs: number | null, ageMs: number): T {
  const b = bounds(t);
  if (!b) return t;
  let cutoff = b.max - Math.max(0, ageMs) - SPAN_SLACK_MS;
  if (b.min > 10_000_000_000 && challengeTs !== null) cutoff = Math.max(cutoff, challengeTs - STALE_LIMIT_MS);
  const out: any = { ...t };
  for (const key of LIST_KEYS) out[key] = (t[key] || []).filter((ev) => eventMinTime(ev) >= cutoff);
  return out as T;
}

/** How old a fresh retry challenge must be before sending: <= 3 s (<= 8 s only to keep the last 3 mouse points). */
export function retryWaitMs(t: TelemetryLists): number {
  const b = bounds(t);
  if (!b) return MIN_CHALLENGE_AGE_MS;
  let target = Math.min(b.max - b.min, MAX_RETRY_WAIT_MS + SPAN_SLACK_MS);
  const moves = t.mouse_movements || [];
  if (moves.length >= 3) {
    const needed = b.max - eventMinTime(moves[moves.length - 3]);
    if (needed > target) target = Math.min(needed, MAX_MOUSE_GUARD_WAIT_MS + SPAN_SLACK_MS);
  }
  return Math.max(MIN_CHALLENGE_AGE_MS, target - SPAN_SLACK_MS);
}

/**
 * Retry preparation (in place): keep the most recent window the token age allows (span <= age + 0.4 s) and shift
 * it just past `challengeTs` so the Stale rule holds. Intervals between events are preserved.
 */
export function alignForRetry(t: TelemetryLists, challengeTs: number, ageMs: number): void {
  const fitted = fitTelemetry(t, null, ageMs);
  for (const key of LIST_KEYS) t[key] = fitted[key];
  const b = bounds(t);
  if (!b || b.min >= challengeTs) return;
  const shift = challengeTs - b.min + 50;
  for (const key of LIST_KEYS) {
    for (const ev of t[key]) {
      for (const f of TIME_FIELDS) if (typeof ev[f] === "number") ev[f] += shift;
    }
  }
}

/**
 * Zero-PII input-path classification: only the kind of an insertion, never its content (e.data, clipboard and
 * field values are not read). Autofill / password managers commonly fire plain `input` events without
 * InputEvent.inputType, or "insertReplacementText"; paste and IME commits are counted by their own events.
 */
export function inputEventKind(e: Event): SynapseInputKind | null {
  const type = typeof (e as InputEvent).inputType === "string" ? (e as InputEvent).inputType : "";
  if (!type || type === "insertReplacementText") return "autofill";
  if (type === "insertFromDrop") return "paste";
  if (type === "insertFromPaste" || type === "insertFromPasteAsQuotation") return null;
  if (type === "insertCompositionText" || type === "insertFromComposition") return null;
  if (type.indexOf("insert") === 0) return "insert";
  return null;
}
