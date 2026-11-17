"""Keyed trajectory fingerprint for single-request replay detection (#39-A).

A recorded human trajectory that passed once can be re-submitted with a fresh token from a fresh IP or
User-Agent; every per-IP / per-device signal misses that. This module turns the pointer path into an opaque
64-bit tag so the server can remember "this exact path was already accepted" without keeping the path.

Fingerprint = HMAC-SHA256(SECRET_KEY, "traj\\x1f" + integer (dx, dy, dt) delta sequence)[:16 hex].

* Deltas, not absolute values: a replay shifted in time (new epoch timestamps) or translated on screen keeps
  the same deltas, so it keeps the same fingerprint.
* Quantisation step 1 px / 1 ms (plain rounding to integers). Measured (scratchpad p2b/quant39.py, SapiMouse
  1507 windows / 120 users and 697 simulated login sessions): no step from (1,1) to (8,16) produces a single
  human collision, and no step survives +-1 px noise or +-1 ms jitter in more than 3 % (SapiMouse) of
  recordings, because any exact-bin hash breaks once one delta crosses a bin edge. A coarser step only adds
  collision risk, so the finest step is used. Defeating it with noise is a known limit of an exact hash.
* Keyed with the token-signing SECRET_KEY (same scheme as storage.client_strike_key): the stored tag cannot
  be linked to a trajectory without the key, and raw coordinates never reach storage.
* Entropy gate: fewer than MIN_POINTS points, a total path shorter than MIN_PATH_PX, or fewer than
  MIN_DISTINCT_DELTAS distinct deltas -> None (not fingerprinted). Short taps / tiny paths have too few
  distinct values for "never seen twice" to hold across real users.
* Touch: the SDKs put touch points into ``mouse_movements``, so touch trajectories are covered by the same
  field. Keystrokes, clicks and scrolls are not used.
"""
from __future__ import annotations

import hashlib
import hmac
import math
from typing import Any

MIN_POINTS = 20
MIN_PATH_PX = 100.0
MIN_DISTINCT_DELTAS = 5
_MAX_POINTS = 5000  # bounded work; the payload cap (256 KB) already limits this in practice
_DOMAIN = b"traj\x1f"


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def quantized_deltas(telemetry: Any) -> list[tuple[int, int, int]] | None:
    """Integer (dx, dy, dt) deltas of ``mouse_movements``, or None if malformed / below the entropy gate."""
    if not isinstance(telemetry, dict):
        return None
    moves = telemetry.get("mouse_movements")
    if not isinstance(moves, list) or len(moves) < MIN_POINTS:
        return None
    pts = []
    for m in moves[:_MAX_POINTS]:
        if not isinstance(m, dict):
            return None
        x, y, t = _num(m.get("x")), _num(m.get("y")), _num(m.get("t"))
        if x is None or y is None or t is None:
            return None
        # floor(v + 0.5), not round(): banker's rounding maps 1100.5 -> 1100 but 1877.5 -> 1878, so an
        # integer time shift / translation of a fractional trace would change the deltas.
        pts.append((math.floor(x + 0.5), math.floor(y + 0.5), math.floor(t + 0.5)))
    deltas = [(b[0] - a[0], b[1] - a[1], b[2] - a[2]) for a, b in zip(pts, pts[1:])]
    path = sum(math.hypot(dx, dy) for dx, dy, _ in deltas)
    if path < MIN_PATH_PX or len(set(deltas)) < MIN_DISTINCT_DELTAS:
        return None
    return deltas


def trajectory_fingerprint(telemetry: Any, secret_key: bytes | None = None) -> str | None:
    """Opaque 64-bit hex tag ("t_" + 16 hex) of the trajectory, or None when it is not fingerprinted."""
    deltas = quantized_deltas(telemetry)
    if deltas is None:
        return None
    if secret_key is None:
        from synapse_shield.tokens import SECRET_KEY

        secret_key = SECRET_KEY
    raw = _DOMAIN + ";".join(f"{dx},{dy},{dt}" for dx, dy, dt in deltas).encode("ascii")
    return "t_" + hmac.HMAC(secret_key, raw, digestmod=hashlib.sha256).hexdigest()[:16]
