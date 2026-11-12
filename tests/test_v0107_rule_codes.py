"""Stable rule codes for decision reasons, and the per-cohort shadow rule counter."""

import base64
import json
import pathlib

import pytest

from synapse_shield import core, metrics, rules, tokens
from synapse_shield.adversarial import generate_adversarial_telemetry_batch
from synapse_shield.engine import analyze_behavior

SRC = pathlib.Path(core.__file__).parent


def test_every_pattern_still_appears_in_the_source():
    text = (SRC / "engine.py").read_text(encoding="utf-8") + (SRC / "core.py").read_text(encoding="utf-8")
    stale = [needle for _, needle in rules.RULE_PATTERNS if needle not in text]
    assert not stale, f"reason text changed, update rules.RULE_PATTERNS: {stale}"


def test_codes_are_low_cardinality_identifiers():
    codes = {c for c, _ in rules.RULE_PATTERNS}
    assert all(c.replace("_", "").isalnum() and c == c.lower() for c in codes)
    assert 25 <= len(codes) <= 60


@pytest.mark.parametrize("reason,code", [
    ("Superhuman artificial sub-movement stutter detected (30 peaks) [+45.0].", "stutter"),
    ("Lack of physiological sub-movement decomposition in trajectory (submovement_count: 1)", "no_submovements"),
    ("Synthetic differential curvature profile detected (curvature_score: 0.95)", "curvature"),
    ("Superhuman input frequency (avg typing interval: 9.0 ms).", "keystroke_superhuman"),
    ("Session Behavioral Invariance: Zero straightness variance across consecutive session requests.",
     "session_invariance"),
    ("Something new nobody mapped yet", "other"),
])
def test_rule_code(reason, code):
    assert rules.rule_code(reason) == code


@pytest.mark.parametrize("reason", [
    "AI and heuristic scores capped at 34.0 due to verified organic human motion with privacy farbling.",
    "1D-CNN AI Engine Confidence: 12.0% Bot.",
    "Natural behavioral telemetry flags verified by AI & Heuristics.",
    "Capacitive human touch contact verified (avg_radius: 11.0px, compliance_var: 0.100).",
])
def test_informational_reasons_have_no_code(reason):
    assert rules.rule_code(reason) is None


def test_rule_codes_are_sorted_and_unique():
    out = rules.rule_codes(["Superhuman mouse velocity (max: 99)", "Superhuman mouse velocity again",
                            "Euclidean straight-line trajectory detected", "1D-CNN AI Engine Confidence: 90% Bot."])
    assert out == ("straight_line", "superhuman_velocity")


def test_real_bot_verdicts_use_known_codes_not_other():
    seen = set()
    for tel in generate_adversarial_telemetry_batch(30):
        _, _, reasons, _ = analyze_behavior(tel)
        seen |= set(rules.rule_codes(reasons))
    assert seen, "bots must trigger rules"
    assert rules.OTHER not in seen, "a bot verdict produced a reason with no rule code"


def _token():
    raw = json.dumps({"challenge": tokens.generate_challenge()["challenge"], "telemetry": {}})
    return base64.b64encode(raw.encode()).decode()


def _fake(score, classification, reasons, **features):
    def analyze(telemetry, *a, **k):
        return score, classification, list(reasons), {"features": dict(features), "threat_type": None}

    return analyze


def test_shadow_block_counts_rules_per_cohort(monkeypatch):
    pytest.importorskip("prometheus_client")
    monkeypatch.setattr(core, "METRICS_ENABLED", True)
    for name in ("synapse_requests_total", "synapse_shadow_requests_total", "synapse_shadow_cohort_total",
                 "synapse_shadow_outcomes_total", "synapse_shadow_rules_total", "synapse_replays_detected_total",
                 "synapse_pow_solved_total", "synapse_inference_latency_seconds"):
        monkeypatch.setattr(core, name, getattr(metrics, name))
    monkeypatch.setattr(core, "analyze_behavior", _fake(
        90.0, "Bot", ["Superhuman artificial sub-movement stutter detected (30 peaks) [+45.0].",
                      "Synthetic differential curvature profile detected (x)",
                      "1D-CNN AI Engine Confidence: 90.0% Bot."],
        mouse_points=40, total_interactive_events=40, device_pixel_ratio=2.0))
    c = metrics.synapse_shadow_rules_total
    before = {r: c.labels(input="pointer", dpr="2x+", rule=r)._value.get() for r in ("stutter", "curvature")}
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.20", user_agent="u", token=_token(), mode="shadow")
    assert d.rule_codes == ("curvature", "stutter")
    assert d.to_dict()["rule_codes"] == ["curvature", "stutter"]
    for r in ("stutter", "curvature"):
        assert c.labels(input="pointer", dpr="2x+", rule=r)._value.get() == before[r] + 1


def test_enforce_mode_has_no_rule_codes(monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior", _fake(
        90.0, "Bot", ["Superhuman mouse velocity (max: 99)"], mouse_points=40, total_interactive_events=40))
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.21", user_agent="u", token=_token())
    assert d.rule_codes == ()
