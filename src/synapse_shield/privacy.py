"""
Synapse Shield - Server-side Zero-PII keystroke guard.

Since v0.10.4 the browser SDKs mask every printed character (`key: "masked"`) and send a
client-side `is_freq_digraph` flag instead. Older SDKs (and hand-rolled clients) still send the
typed characters themselves. This module enforces the same contract on the server, at the single
point every request passes through (token verification), so raw text never reaches the scoring
engine, application handlers (`request.state.synapse_telemetry`), logs or the dataset store.

Before masking, the digraph flag is derived from the raw sequence exactly like the SDK does, so
legacy clients keep the linguistic muscle-memory signal.
"""

from __future__ import annotations

from typing import Any

# Must match FREQUENT_DIGRAPHS in static/synapse-sdk.js and crates/synapse_core_rs/src/keystrokes.rs.
FREQUENT_DIGRAPHS = frozenset({
    "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha",
    "at", "en", "es", "of", "or", "nt", "ea", "ti", "to", "it",
    "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve",
    "la", "ik", "ak", "el", "al", "ma", "me", "ba", "ka",
})

# Closed allow-list of W3C UI Events control keys (compared case-insensitively; the SDKs send them
# lower-cased). Anything else, including multi-character printed text such as a name or password
# delivered by an IME, word completion or a hand-rolled client, is masked. Keep in sync with
# NAMED_KEYS in synapse-sdk.js and both framework hooks.
NAMED_KEYS = frozenset({
    "enter", "backspace", "tab", "shift", "control", "alt",
    "altgraph", "meta", "capslock", "escape", "arrowleft", "arrowright",
    "arrowup", "arrowdown", "home", "end", "pageup", "pagedown",
    "insert", "delete", "dead", "process", "unidentified", "numlock",
    "scrolllock", "contextmenu", "pause", "printscreen", "clear", "compose",
    "f1", "f2", "f3", "f4", "f5", "f6",
    "f7", "f8", "f9", "f10", "f11", "f12",
    "f13", "f14", "f15", "f16", "f17", "f18",
    "f19", "f20", "f21", "f22", "f23", "f24",
})
_SAFE_VALUES = {"masked", "unknown"}


def safe_key_name(key: Any) -> str:
    """Return the key name if it is a named key, otherwise "masked"."""
    if key is None or key == "":
        return "unknown"
    k = str(key)
    if k in _SAFE_VALUES or k.lower() in NAMED_KEYS:
        return k
    return "masked"


def _is_raw_text(key: Any) -> bool:
    return safe_key_name(key) == "masked" and key != "masked"


def sanitize_keystrokes(keystrokes: Any) -> Any:
    """Return a PII-free copy of a keystroke list (input is not modified).

    * Keys that are not named keys are replaced with "masked".
    * If raw characters were present and the client sent no `is_freq_digraph`, the flag is
      computed from consecutive keydowns (SDK semantics) and keyups inherit their keydown's flag.
    * Lists without any raw character are returned unchanged (current SDKs).
    """
    if not isinstance(keystrokes, list):
        return keystrokes
    if not any(isinstance(k, dict) and _is_raw_text(k.get("key")) for k in keystrokes):
        return keystrokes

    out: list[Any] = []
    last_raw = ""
    pending: dict[str, list[bool]] = {}
    for k in keystrokes:
        if not isinstance(k, dict):
            out.append(k)
            continue
        ev = dict(k)
        raw = str(k.get("key", "") or "").lower()
        ev_type = k.get("type")
        if ev_type == "up":
            queue = pending.get(raw)
            flag = queue.pop(0) if queue else False
        else:
            flag = len(last_raw) == 1 and len(raw) == 1 and (last_raw + raw) in FREQUENT_DIGRAPHS
            last_raw = raw
            if ev_type == "down":
                pending.setdefault(raw, []).append(flag)
        if "is_freq_digraph" not in ev:
            ev["is_freq_digraph"] = flag
        ev["key"] = safe_key_name(k.get("key"))
        out.append(ev)
    return out


def sanitize_telemetry(telemetry: Any) -> Any:
    """Return telemetry with its keystrokes passed through :func:`sanitize_keystrokes`."""
    if not isinstance(telemetry, dict) or "keystrokes" not in telemetry:
        return telemetry
    cleaned = sanitize_keystrokes(telemetry["keystrokes"])
    if cleaned is telemetry["keystrokes"]:
        return telemetry
    return {**telemetry, "keystrokes": cleaned}
