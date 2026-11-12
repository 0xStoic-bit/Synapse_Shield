"""Coarse, privacy-preserving input cohorts for Shadow Mode analysis.

A global false-positive rate can hide one broken group (touch, high-DPR, zoomed browsers...).
This module reduces a session to two low-cardinality labels so shadow verdicts can be compared per
cohort, without ever storing pointer traces:

  input : touch | pointer | keyboard | none
  dpr   : lt1 | 1x | 1.25-1.9x | 2x+ | unknown

Notes:
  * "pointer" covers mouse AND trackpad: they cannot be told apart reliably from the event stream,
    and guessing would turn the label into a fingerprint. Trackpad vs mouse needs a host-supplied hint.
  * devicePixelRatio moves with browser zoom, so the dpr label also separates zoomed sessions.
"""

from __future__ import annotations

import math
from typing import Any

INPUT_LABELS = ("touch", "pointer", "keyboard", "none")
DPR_LABELS = ("lt1", "1x", "1.25-1.9x", "2x+", "unknown")
OUTCOME_LABELS = ("completed", "abandoned")


def dpr_bucket(dpr: Any) -> str:
    try:
        v = float(dpr)
    except (TypeError, ValueError):
        return "unknown"
    if math.isnan(v) or math.isinf(v) or v <= 0:
        return "unknown"
    if v < 0.99:
        return "lt1"
    if v < 1.25:
        return "1x"
    if v < 2.0:
        return "1.25-1.9x"
    return "2x+"


def input_class(features: dict[str, Any] | None) -> str:
    if not features:
        return "none"
    if features.get("touch_event_count", 0) > 0:
        return "touch"
    if features.get("mouse_points", 0) >= 3:
        return "pointer"
    if features.get("key_count", 0) > 0:
        return "keyboard"
    return "none"


def cohort_of(features: dict[str, Any] | None) -> dict[str, str]:
    """Return {"input": ..., "dpr": ...} for a feature dict (or unknown values when absent)."""
    if not features:
        return {"input": "none", "dpr": "unknown"}
    return {"input": input_class(features), "dpr": dpr_bucket(features.get("device_pixel_ratio"))}
