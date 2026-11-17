"""#39-C shape invariance (IP+UA and IP-only, current request included), short-trace gray-area challenge with
PoW off, and the single CNN forward pass.

Measurements behind the thresholds live in the scratchpad scripts named in engine.py / core.py comments; these
tests only pin the contract (synthetic edge cases, no metric claims).
"""

import base64
import json
import math
import random

import pytest

from synapse_shield import adversarial as adv
from synapse_shield import core, engine, tokens
from synapse_shield.engine import analyze_behavior, trajectory_shape_hash

BROWSER = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False}
SHAPE_REASON = "Same normalized trajectory shape repeated"


def _tel(moves, click_dt=110):
    last = moves[-1]
    return {"mouse_movements": moves, "clicks": [{"x": last["x"], "y": last["y"], "t": last["t"] + click_dt}],
            "keystrokes": [], "scrolls": [], "browser": dict(BROWSER)}


def _template(seed=5, steps=45):
    rnd = random.Random(seed)
    return adv.generate_humanized_bezier_telemetry(start=(150, 200), end=(700, 480), steps=steps, sample_ms=30.0,
                                                   rng=rnd)["mouse_movements"]


def _variant(base, rnd, scale=1.0, noise=1.0, warp=1.0):
    x0, y0, t0 = base[0]["x"], base[0]["y"], base[0]["t"]
    dx, dy = rnd.uniform(-60, 60), rnd.uniform(-60, 60)
    return [{"x": round(x0 + (m["x"] - x0) * scale + dx + rnd.gauss(0, noise)),
             "y": round(y0 + (m["y"] - y0) * scale + dy + rnd.gauss(0, noise)),
             "t": round(1000 + (m["t"] - t0) * warp)} for m in base]


def _token(telemetry):
    env = {"challenge": tokens.generate_challenge()["challenge"], "telemetry": telemetry}
    return base64.b64encode(json.dumps(env).encode()).decode()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("SYNAPSE_ENABLE_POW", "SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "SYNAPSE_SHORT_TRACE_CHALLENGE",
              "SYNAPSE_TRAJECTORY_REPLAY"):
        monkeypatch.delenv(k, raising=False)


# ---------------- #39-C shape invariance ----------------

def test_shape_hash_is_invariant_to_translation_scale_and_time_warp():
    base = _template()
    rnd = random.Random(1)
    h0 = int(trajectory_shape_hash(_tel(base)), 16)
    for kw in ({"scale": 1.2, "noise": 0.0}, {"scale": 0.85, "noise": 1.0}, {"warp": 1.08, "noise": 1.0}):
        h = int(trajectory_shape_hash(_tel(_variant(base, rnd, **kw))), 16)
        assert bin(h0 ^ h).count("1") <= engine.SHAPE_INVARIANCE_MAX_HAMMING, kw


def test_shape_hash_gate_skips_short_or_tiny_traces():
    assert trajectory_shape_hash(_tel(_template(steps=8))) is None
    tiny = [{"x": 100 + (i % 3), "y": 100, "t": 1000 + 30 * i} for i in range(30)]
    assert trajectory_shape_hash(_tel(tiny)) is None
    assert trajectory_shape_hash({"mouse_movements": [{"x": "a"}] * 20}) is None


def _hist(tel):
    _, _, _, d = analyze_behavior(tel)
    f = d["features"]
    return {"avg_jerk": f["avg_jerk"], "straightness": f["straightness"], "total_distance": f["total_distance"],
            "sh": d["shape_hash"]}


def test_shape_invariance_fires_on_third_request_counting_the_current_one():
    base, rnd = _template(), random.Random(2)
    tels = [_tel(_variant(base, rnd, scale=rnd.uniform(0.8, 1.25))) for _ in range(3)]
    hist = [_hist(tels[0]), _hist(tels[1])]
    _, cls, reasons, _ = analyze_behavior(tels[2], session_history=hist)
    assert cls == "Bot" and any(SHAPE_REASON in r and "session" in r for r in reasons)
    # One prior request is not enough evidence.
    _, _, reasons, _ = analyze_behavior(tels[2], session_history=hist[1:])
    assert not any(SHAPE_REASON in r for r in reasons)


def test_shape_invariance_uses_ip_only_history():
    base, rnd = _template(), random.Random(3)
    tels = [_tel(_variant(base, rnd, noise=1.5)) for _ in range(3)]
    ip_hist = [{"sh": _hist(tels[0])["sh"]}, {"sh": _hist(tels[1])["sh"]}]
    _, cls, reasons, _ = analyze_behavior(tels[2], session_history=[], ip_history=ip_hist)
    assert cls == "Bot" and any(SHAPE_REASON in r and "IP" in r for r in reasons)


def test_different_trajectories_do_not_trigger_shape_invariance():
    tels = [_tel(_template(seed=s)) for s in (11, 12)]
    other = adv.generate_humanized_bezier_telemetry(start=(900, 700), end=(300, 150), steps=50, sample_ms=30.0,
                                                    rng=random.Random(13))["mouse_movements"]
    _, _, reasons, _ = analyze_behavior(_tel(other), session_history=[_hist(t) for t in tels],
                                        ip_history=[{"sh": _hist(t)["sh"]} for t in tels])
    assert not any(SHAPE_REASON in r for r in reasons)


def test_kinematic_invariance_now_counts_the_current_request():
    """Exact template: the legacy fuzzy delta now fires with 2 stored + current (was: 3 stored)."""
    tel = _tel(_template())
    h = _hist(tel)
    h.pop("sh")
    _, cls, reasons, _ = analyze_behavior(tel, session_history=[dict(h), dict(h)])
    assert cls == "Bot" and any("High fuzzy kinematic similarity" in r for r in reasons)


def _gray_human_like(seed=3):
    """Deterministic bell-shaped 70-point path that the engine scores 45 (allowed with PoW off)."""
    r = random.Random(seed)
    mv, x, y, t = [], 150.0, 200.0, 1000
    for i in range(70):
        p = i / 69
        v = math.sin(math.pi * p) ** 1.5
        x += 9 * v + r.gauss(0, 1.2) + (3 if 30 < i < 36 else 0)
        y += 4 * v * math.cos(3 * p) + r.gauss(0, 1.2)
        t += r.choice([16, 17, 33, 30, 25])
        mv.append({"x": round(x), "y": round(y), "t": t})
    return mv


def test_core_catches_user_agent_rotation_on_third_request(monkeypatch):
    monkeypatch.setenv("SYNAPSE_TRAJECTORY_REPLAY", "0")  # isolate #39-C from the exact-replay check (#39-A)
    base, rnd = _gray_human_like(), random.Random(4)
    ip = "198.18.39.3"
    actions = []
    for i in range(3):
        tel = _tel(_variant(base, rnd, scale=rnd.uniform(0.85, 1.2), noise=0.0))
        d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=f"ua-rotated-{i}", token=_token(tel))
        actions.append((d.action, d.reasons))
    assert actions[0][0] == "allow" and actions[1][0] == "allow", [a for a, _ in actions]
    assert actions[2][0] == "block" and any(SHAPE_REASON in r and "IP" in r for r in actions[2][1])


# ---------------- short trace gray-area challenge (PoW off) ----------------

def _short_humanized_tel(seed=0):
    rnd = random.Random(seed)
    mv = adv.generate_humanized_bezier_telemetry(start=(200, 300), end=(650, 420), steps=20, sample_ms=30.0,
                                                 rng=rnd)["mouse_movements"]
    return _tel(mv)


def test_short_trace_gate_sets_flag():
    score, cls, _, d = analyze_behavior(_short_humanized_tel())
    assert d["short_trace_gated"] is True and cls == "Human" and 35.0 <= score < 50.0
    _, _, _, d = analyze_behavior(_tel(_template(steps=60)))
    assert d["short_trace_gated"] is False


def test_short_trace_gray_area_is_challenged_with_pow_off():
    d = core.evaluate_synapse_request_sync(client_ip="198.18.38.1", user_agent="ua", token=_token(_short_humanized_tel()),
                                           enable_pow=False)
    assert d.action == "challenge" and d.status_code == 429 and not d.allowed, (d.action, d.bot_score)


@pytest.mark.parametrize("how", ["argument", "environment"])
def test_short_trace_challenge_can_be_turned_off(monkeypatch, how):
    kwargs = {}
    if how == "argument":
        kwargs["short_trace_challenge"] = False
    else:
        monkeypatch.setenv("SYNAPSE_SHORT_TRACE_CHALLENGE", "0")
    d = core.evaluate_synapse_request_sync(client_ip="198.18.38.2", user_agent="ua", token=_token(_short_humanized_tel()),
                                           enable_pow=False, **kwargs)
    assert d.allowed and d.action == "allow"


def _routed(score, classification="Human", gated=True):
    feat = {"total_interactive_events": 20, "mouse_points": 20}

    def analyze(telemetry, *a, **k):
        return score, classification, ["routed"], {"features": feat, "threat_type": None, "short_trace_gated": gated}

    return analyze


@pytest.mark.parametrize("score,classification", [(52.0, "Bot"), (45.0, "Bot")])
def test_short_trace_challenge_never_turns_a_block_into_a_challenge(monkeypatch, score, classification):
    monkeypatch.setattr(core, "analyze_behavior", _routed(score, classification))
    d = core.evaluate_synapse_request_sync(client_ip="198.18.38.3", user_agent="ua", token=_token(_short_humanized_tel()),
                                           enable_pow=False)
    assert d.action == "block"


def test_ungated_gray_area_without_pow_is_unchanged(monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior", _routed(42.0, gated=False))
    d = core.evaluate_synapse_request_sync(client_ip="198.18.38.4", user_agent="ua", token=_token(_short_humanized_tel()),
                                           enable_pow=False)
    assert d.allowed and d.action == "allow"


def test_short_trace_challenge_not_issued_in_shadow_mode():
    d = core.evaluate_synapse_request_sync(client_ip="198.18.38.5", user_agent="ua", token=_token(_short_humanized_tel()),
                                           enable_pow=False, mode="shadow")
    assert d.allowed and d.action == "allow" and d.shadow_mode


# ---------------- single CNN forward pass ----------------

class _CountingModel:
    def __init__(self, mode, raw):
        self.cnn_mode, self.raw, self.raw_calls, self.predict_calls = mode, raw, 0, 0

    def predict_raw(self, *_):
        self.raw_calls += 1
        return self.raw

    def predict(self, *_):  # pragma: no cover - must not be called
        self.predict_calls += 1
        return self.raw if self.cnn_mode == "enforce" else 0.0


@pytest.mark.parametrize("mode,expected_ai", [("shadow", 0.0), ("enforce", 70.0)])
def test_cnn_runs_exactly_one_forward_pass(monkeypatch, mode, expected_ai):
    model = _CountingModel(mode, 0.7)
    monkeypatch.setattr(engine, "_ai_model", model)
    _, _, _, d = analyze_behavior(_tel(_template(steps=60)))
    assert model.raw_calls == 1 and model.predict_calls == 0
    assert d["ai_score"] == pytest.approx(expected_ai)
    assert d["ai_raw_score"] == pytest.approx(70.0)
