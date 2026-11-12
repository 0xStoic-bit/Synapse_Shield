"""Stable rule codes for decision reasons.

``reasons`` are human-readable sentences (with numbers) and may be reworded; dashboards and per-cohort
analysis need low-cardinality identifiers instead. ``rule_codes`` maps the reasons of a verdict to a sorted
tuple of codes. Informational reasons (verified-human notes, AI confidence lines) have no code; a risk
reason that matches no pattern becomes ``"other"``.

A test pins every pattern to the text in ``engine.py`` / ``core.py`` so a reworded reason cannot silently
go uncounted.
"""

from __future__ import annotations

from collections.abc import Iterable

# (code, substring found in the reason). First match wins; keep specific patterns first.
RULE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ip_penalized", "temporarily penalized"),
    ("ip_banned", "IP_BANNED"),
    ("webdriver", "navigator.webdriver"),
    ("stealth_tamper", "Stealth browser tamper"),
    ("hook_without_motion", "hooks detected without human motion"),
    ("hook_without_motion", "hook detected without human motion"),
    ("screen_invalid", "Invalid or headless screen"),
    ("plugins_missing", "Missing browser plugins"),
    ("no_interaction", "Zero user interaction telemetry"),
    ("scroll_only", "DESKTOP_SCROLL_ONLY_SUBMISSION"),
    ("spoofed_touch", "Spoofed touch_supported"),
    ("events_without_motion", "without mouse movement telemetry"),
    ("teleport", "Instantaneous cursor teleportation"),
    ("mobile_emulation", "Synthetic mobile emulat"),
    ("touch_emulation", "Synthetic touch emulation"),
    ("tap_instant", "Superhuman instantaneous touch tap"),
    ("tap_constant", "Robotic constant-duration touch taps"),
    ("straight_line", "Euclidean straight-line trajectory"),
    ("velocity_variance", "Near-zero velocity variance"),
    ("polynomial_accel", "Unnatural polynomial acceleration"),
    ("smoothness", "Unnatural mathematical smoothness"),
    ("zero_entropy_micro", "Zero-entropy micro-trajectory"),
    ("fixed_timer", "Deterministic fixed-interval timer"),
    ("no_terminal_decel", "Lack of terminal deceleration"),
    ("superhuman_velocity", "Superhuman mouse velocity"),
    ("harmonic_tremor", "Synthetic harmonic oscillator tremor"),
    ("no_submovements", "Lack of physiological sub-movement"),
    ("stutter", "sub-movement stutter"),
    ("curvature", "Synthetic differential curvature"),
    ("click_misaligned", "Click-to-cursor spatial misalignment"),
    ("keystroke_biometrics", "Abnormal keystroke biometrics"),
    ("keystroke_constant", "Robotic constant-interval keystroke"),
    ("keystroke_superhuman", "Superhuman input frequency"),
    ("request_frequency", "Poisson request frequency anomaly"),
    ("session_invariance", "Session Behavioral Invariance"),
    ("ai_error", "AI Model Error"),
)

# Reasons that describe verified-human evidence or model confidence, never a rule that fired.
INFORMATIONAL_PATTERNS: tuple[str, ...] = (
    "verified",
    "Risk lowered",
    "organic human kinematics",
    "organic human motion",
    "capped at",
    "AI Engine Confidence",
    "Natural behavioral telemetry",
)

OTHER = "other"


def rule_code(reason: str) -> str | None:
    """Code for one reason, ``None`` when the reason is informational."""
    for code, needle in RULE_PATTERNS:
        if needle in reason:
            return code
    if any(p in reason for p in INFORMATIONAL_PATTERNS):
        return None
    return OTHER


def rule_codes(reasons: Iterable[str]) -> tuple[str, ...]:
    """Sorted unique rule codes for a verdict's reasons."""
    return tuple(sorted({c for c in (rule_code(str(r)) for r in reasons) if c}))
