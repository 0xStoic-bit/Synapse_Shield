"""Motor sertleştirmeleri (kinematics-engine, aşama 2A): #38a kısa iz kapısı, #5 istemci bayrakları,
#6 Enter sentetik tık, input_events gözlem alanı, CNN ham skor gözlemi.

Buradaki diziler yalnızca kuralların sınır koşullarını sabitler (no_mock_data). Oranlar (FPR/TPR) gerçek
SapiMouse / CMU yeniden oynatımıyla ölçüldü; testlere sayı olarak gömülmez.
"""

from __future__ import annotations

import pytest

from synapse_shield import engine
from synapse_shield.features import extract_features

DESKTOP = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False}


def _features_with(monkeypatch, **overrides):
    """engine.extract_features'ı, boş telemetrinin varsayılanları + verilen öznitelikler döndürecek şekilde sarar."""
    base = extract_features({"browser": dict(DESKTOP)}, force_python=True)
    base.update(overrides)
    monkeypatch.setattr(engine, "extract_features", lambda tel, *a, **k: dict(base))


def _weak_only(points: int, **extra):
    """Yalnızca düzlük + FFT + alt-hareket kurallarını tetikleyen öznitelikler (bağımsız sinyal yok)."""
    f = dict(mouse_points=points, total_distance=400.0, straightness=0.99, velocity_var=0.05,
             acceleration_var=1e-3, avg_jerk=5e-4, dt_var=40.0, terminal_decel_ratio=0.2, max_velocity=2.0,
             spectral_purity=0.9, spectral_entropy=0.3, submovement_count=1, curvature_score=0.1, click_count=1)
    f.update(extra)
    return f


def _tel():
    return {"mouse_movements": [], "clicks": [], "keystrokes": [], "scrolls": [], "browser": dict(DESKTOP)}


# ---------------------------------------------------------------- #38a kısa iz kapısı
def test_short_trace_weak_rules_alone_stay_in_gray_area(monkeypatch):
    _features_with(monkeypatch, **_weak_only(20))
    score, cls, reasons, _ = engine.analyze_behavior(_tel())
    assert any("Insufficient trajectory evidence" in r for r in reasons)
    assert 35.0 <= score < 50.0
    assert cls == "Human"


def test_long_trace_weak_rules_still_block(monkeypatch):
    _features_with(monkeypatch, **_weak_only(engine.SHORT_TRACE_MAX_POINTS))
    score, cls, reasons, _ = engine.analyze_behavior(_tel())
    assert not any("Insufficient trajectory evidence" in r for r in reasons)
    assert cls == "Bot"


def test_short_trace_with_independent_signal_still_blocks(monkeypatch):
    # Jerk eksikliği (bağımsız sinyal) + kısa izin zayıf kuralları -> BLOCK kalır.
    _features_with(monkeypatch, **_weak_only(20, avg_jerk=1e-6))
    score, cls, _, _ = engine.analyze_behavior(_tel())
    assert cls == "Bot" and score >= 50.0


def test_short_trace_exact_straight_line_is_not_capped(monkeypatch):
    # Demir Kural 2: kusursuz doğru (straightness = 1.0) kısa izde de tam ceza alır.
    _features_with(monkeypatch, **_weak_only(15, straightness=1.0, spectral_purity=0.1, submovement_count=3))
    score, cls, _, _ = engine.analyze_behavior(_tel())
    assert cls == "Bot"


@pytest.mark.parametrize("points", [10, 25, 39])
def test_gate_applies_below_threshold(monkeypatch, points):
    _features_with(monkeypatch, **_weak_only(points, straightness=0.9, submovement_count=3))  # yalnız FFT (65)
    score, cls, reasons, _ = engine.analyze_behavior(_tel())
    assert score == pytest.approx(engine.SHORT_TRACE_WEAK_RISK_CAP)
    assert cls == "Human"


# ---------------------------------------------------------------- #6 Enter sentetik tık
def _mouse_then_enter(click_dt: float, with_keydown: bool = True):
    moves = [{"x": 100 + i * 9 + (i % 3), "y": 200 + i * 4 + (i % 2), "t": 1000 + i * 31 + (i % 4)} for i in range(50)]
    keys = []
    t = 3000
    for _ in range(8):
        keys += [{"type": "down", "key": "masked", "t": t}, {"type": "up", "key": "masked", "t": t + 90}]
        t += 180 + (t % 70)
    if with_keydown:
        keys += [{"type": "down", "key": "masked", "t": t}, {"type": "up", "key": "masked", "t": t + 80}]
    clicks = [{"x": moves[-1]["x"], "y": moves[-1]["y"], "t": 2700}, {"x": 0, "y": 0, "t": t + click_dt}]
    return {"mouse_movements": moves, "clicks": clicks, "keystrokes": keys, "scrolls": [], "browser": dict(DESKTOP)}


def test_enter_synthetic_click_is_not_click_misalignment():
    _, _, reasons, det = engine.analyze_behavior(_mouse_then_enter(2))
    assert det["features"]["synthetic_click_count"] == 1
    assert not any("Click-to-cursor" in r for r in reasons)


def test_coordinate_less_click_without_keydown_is_still_checked():
    _, _, reasons, det = engine.analyze_behavior(_mouse_then_enter(2, with_keydown=False))
    assert det["features"]["synthetic_click_count"] == 0
    assert any("Click-to-cursor" in r for r in reasons)


def test_coordinate_less_click_long_after_keydown_is_still_checked():
    _, _, reasons, _ = engine.analyze_behavior(_mouse_then_enter(engine.SYNTHETIC_ENTER_CLICK_MAX_MS + 30))
    assert any("Click-to-cursor" in r for r in reasons)


# ---------------------------------------------------------------- #5 istemci bayrakları
def _typed(n=14, dwell=5, key="masked", flags=False, screen=1920, touch_clicks=False, spread=3):
    ev, t, prev = [], 2000, None
    for i in range(n):
        gap = 120 if i % 2 else 260
        d, u = t, t + dwell + (i * 37) % spread
        e = {"type": "down", "key": key, "t": d}
        e2 = {"type": "up", "key": key, "t": u, "down": d, "up": u, "duration_ms": u - d}
        if flags:
            fq = prev == 120  # saldırgan: kısa aralıktan sonra gelen tuşu "sık digraph" işaretler
            e["is_freq_digraph"] = e2["is_freq_digraph"] = fq
        ev += [e, e2]
        prev = gap
        t += gap
    br = dict(DESKTOP, screen_width=screen, screen_height=800 if screen < 1024 else 1080)
    clicks = []
    if touch_clicks:
        br["touch_supported"] = True
        br["max_touch_points"] = 5
        clicks = [{"x": 100, "y": 300, "t": t + 50, "r": 11.5, "tap_duration_ms": 90, "source": "touch"}]
    return {"mouse_movements": [], "clicks": clicks, "keystrokes": ev, "scrolls": [], "browser": br}


def _abnormal(reasons):
    return any("Abnormal keystroke biometrics" in r for r in reasons)


def test_desktop_ime_key_names_do_not_skip_dwell_checks():
    _, _, reasons, _ = engine.analyze_behavior(_typed(key="unidentified"))
    assert _abnormal(reasons)


def test_real_mobile_ime_with_touch_evidence_keeps_exemption():
    _, _, reasons, _ = engine.analyze_behavior(_typed(key="unidentified", screen=412, touch_clicks=True))
    assert not _abnormal(reasons)


def test_client_digraph_flag_cannot_lower_keystroke_score():
    _, _, with_flags, det = engine.analyze_behavior(_typed(flags=True))
    _, _, without, _ = engine.analyze_behavior(_typed(flags=False))
    assert _abnormal(without)
    assert _abnormal(with_flags)
    assert det["features"]["keystroke_score_effective"] >= 0.70


def test_human_like_dwell_with_honest_flags_not_abnormal():
    _, _, reasons, _ = engine.analyze_behavior(_typed(dwell=80, flags=True, spread=45))
    assert not _abnormal(reasons)


# ---------------------------------------------------------------- input_events (yalnızca gözlem)
def test_input_events_are_observed_but_do_not_change_the_decision():
    base = {"mouse_movements": [], "clicks": [{"x": 0, "y": 0, "t": 2500}], "keystrokes": [], "scrolls": [],
            "browser": dict(DESKTOP)}
    flagged = dict(base, input_events=[{"t": 1500, "kind": "autofill"}, {"t": 1600, "kind": "paste"},
                                       {"t": 1700, "kind": "bogus"}, "x"])
    s0, c0, _, _ = engine.analyze_behavior(base)
    s1, c1, _, d1 = engine.analyze_behavior(flagged)
    assert (s0, c0) == (s1, c1)
    f = d1["features"]
    assert f["input_event_count"] == 2 and f["autofill_seen"] and f["paste_seen"] and not f["insert_seen"]


# ---------------------------------------------------------------- CNN ham skor gözlemi
def test_ai_raw_score_is_reported_without_affecting_shadow_decision():
    if engine._ai_model is None:
        pytest.skip("model yüklenemedi")
    tel = {"mouse_movements": [{"x": 100 + i * 7 + (i % 5), "y": 300 + (i * i) % 11, "t": 1000 + i * 31 + i % 3}
                               for i in range(70)], "clicks": [], "keystrokes": [], "scrolls": [],
           "browser": dict(DESKTOP)}
    _, _, _, det = engine.analyze_behavior(tel)
    assert det["ai_raw_score"] is not None and 0.0 <= det["ai_raw_score"] <= 100.0
    if engine._ai_model.cnn_mode == "shadow":
        assert det["ai_score"] == 0.0
