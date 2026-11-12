"""Shadow Mode cohort telemetry: verdicts are labelled per coarse input cohort, and host-reported session
outcomes are joined with them, without storing any pointer trace."""

import base64
import json

import pytest

from synapse_shield import core, metrics, tokens
from synapse_shield.cohort import cohort_of, dpr_bucket, input_class


def _token() -> str:
    raw = json.dumps({"challenge": tokens.generate_challenge()["challenge"], "telemetry": {}})
    return base64.b64encode(raw.encode()).decode()


def _fake(score, classification="Human", **features):
    def analyze(telemetry, *a, **k):
        return score, classification, ["fake"], {"features": dict(features), "threat_type": None}

    return analyze


@pytest.fixture
def prom(monkeypatch):
    pytest.importorskip("prometheus_client")
    monkeypatch.setattr(core, "METRICS_ENABLED", True)
    for name in ("synapse_requests_total", "synapse_shadow_requests_total", "synapse_shadow_cohort_total",
                 "synapse_shadow_outcomes_total", "synapse_replays_detected_total", "synapse_pow_solved_total",
                 "synapse_inference_latency_seconds"):
        monkeypatch.setattr(core, name, getattr(metrics, name))
    return metrics


def _n(counter, **labels):
    return counter.labels(**labels)._value.get()


@pytest.mark.parametrize("dpr,expected", [
    (1.0, "1x"), (1.1, "1x"), (1.25, "1.25-1.9x"), (1.5, "1.25-1.9x"), (1.99, "1.25-1.9x"),
    (2.0, "2x+"), (3.0, "2x+"), (0.8, "lt1"), (0.5, "lt1"),
    (0, "unknown"), (-1, "unknown"), (float("nan"), "unknown"), (float("inf"), "unknown"),
    (None, "unknown"), ("abc", "unknown"),
])
def test_dpr_bucket(dpr, expected):
    assert dpr_bucket(dpr) == expected


@pytest.mark.parametrize("feats,expected", [
    ({"touch_event_count": 4, "mouse_points": 20}, "touch"),
    ({"mouse_points": 3}, "pointer"),
    ({"mouse_points": 2, "key_count": 9}, "keyboard"),
    ({"mouse_points": 2}, "none"),
    ({}, "none"),
    (None, "none"),
])
def test_input_class(feats, expected):
    assert input_class(feats) == expected


def test_cohort_has_bounded_cardinality_and_no_trace_data():
    c = cohort_of({"mouse_points": 50, "device_pixel_ratio": 2.0, "avg_jerk": 1.23, "x": [1, 2, 3]})
    assert set(c) == {"input", "dpr"}
    assert c == {"input": "pointer", "dpr": "2x+"}


def test_shadow_block_is_counted_per_cohort(prom, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior",
                        _fake(90.0, "Bot", mouse_points=40, total_interactive_events=40, device_pixel_ratio=2.0))
    before = _n(prom.synapse_shadow_cohort_total, action="block", input="pointer", dpr="2x+")
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.1", user_agent="u", token=_token(), mode="shadow")
    assert d.action == "shadow_block" and d.allowed
    assert d.cohort == {"input": "pointer", "dpr": "2x+"}
    assert d.to_dict()["cohort"] == d.cohort
    assert _n(prom.synapse_shadow_cohort_total, action="block", input="pointer", dpr="2x+") == before + 1


def test_shadow_allow_is_counted_per_cohort(prom, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior",
                        _fake(5.0, touch_event_count=6, mouse_points=6, total_interactive_events=6,
                              device_pixel_ratio=3.0))
    before = _n(prom.synapse_shadow_cohort_total, action="allow", input="touch", dpr="2x+")
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.2", user_agent="u", token=_token(), mode="shadow")
    assert d.action == "allow" and d.cohort == {"input": "touch", "dpr": "2x+"}
    assert _n(prom.synapse_shadow_cohort_total, action="allow", input="touch", dpr="2x+") == before + 1


def test_enforce_mode_does_not_touch_cohort_metrics_or_decision(prom, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior",
                        _fake(5.0, mouse_points=40, total_interactive_events=40, device_pixel_ratio=1.0))
    before = _n(prom.synapse_shadow_cohort_total, action="allow", input="pointer", dpr="1x")
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.3", user_agent="u", token=_token())
    assert d.cohort is None and "cohort" not in d.to_dict()
    assert _n(prom.synapse_shadow_cohort_total, action="allow", input="pointer", dpr="1x") == before


def test_non_behavioural_shadow_verdicts_have_no_cohort(prom):
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.4", user_agent="u", token=None, mode="shadow")
    assert d.action == "shadow_block" and d.cohort is None


def test_outcome_join_counts_verdict_cohort_and_outcome(prom, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior",
                        _fake(90.0, "Bot", mouse_points=40, total_interactive_events=40, device_pixel_ratio=1.5))
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.5", user_agent="u", token=_token(), mode="shadow")
    lbl = dict(simulated_action="block", input="pointer", dpr="1.25-1.9x")
    done0 = _n(prom.synapse_shadow_outcomes_total, outcome="completed", **lbl)
    gone0 = _n(prom.synapse_shadow_outcomes_total, outcome="abandoned", **lbl)
    assert core.report_shadow_outcome(d, completed=True) is True
    assert core.report_shadow_outcome(d, completed=False) is True
    assert _n(prom.synapse_shadow_outcomes_total, outcome="completed", **lbl) == done0 + 1
    assert _n(prom.synapse_shadow_outcomes_total, outcome="abandoned", **lbl) == gone0 + 1


def test_outcome_join_ignores_decisions_without_shadow_cohort(prom):
    assert core.report_shadow_outcome(core.SynapseDecision(allowed=True), completed=True) is False
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.6", user_agent="u", token=None, mode="shadow")
    assert core.report_shadow_outcome(d, completed=True) is False


def test_outcome_join_is_a_noop_when_metrics_disabled(prom, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior",
                        _fake(5.0, mouse_points=40, total_interactive_events=40, device_pixel_ratio=1.0))
    d = core.evaluate_synapse_request_sync(client_ip="198.51.100.7", user_agent="u", token=_token(), mode="shadow")
    lbl = dict(simulated_action="allow", input="pointer", dpr="1x", outcome="completed")
    before = _n(prom.synapse_shadow_outcomes_total, **lbl)
    monkeypatch.setattr(core, "METRICS_ENABLED", False)
    assert core.report_shadow_outcome(d, completed=True) is True
    assert _n(prom.synapse_shadow_outcomes_total, **lbl) == before


def test_public_export():
    import synapse_shield

    assert synapse_shield.report_shadow_outcome is core.report_shadow_outcome
