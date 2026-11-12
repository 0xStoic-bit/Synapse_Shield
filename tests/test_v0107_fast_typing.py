"""v0.10.7: fast real typists with key rollover must not be flagged "superhuman"; auto-typers still are.

Real fast typists average < 25 ms between release and the next press (keys overlap) but the intervals are
widely spread (variance in the thousands of ms^2). Auto-typers are constant or narrowly jittered.
"""

import random

import pytest

from synapse_shield import engine, features as feat
from synapse_shield.engine import _superhuman_key_interval, analyze_behavior

try:
    from synapse_shield import synapse_core_rs
except ImportError:  # pragma: no cover
    synapse_core_rs = None

BROWSER = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False}


def _keys(flights, holds):
    ks, t = [], 1000.0
    for i, h in enumerate(holds):
        ks.append({"type": "down", "key": "masked", "t": t})
        ks.append({"type": "up", "key": "masked", "t": t + h, "down": t, "up": t + h, "duration_ms": h})
        t += h + (flights[i] if i < len(flights) else 0.0)
    return ks


def _rollover_typist(seed):
    rnd = random.Random(seed)
    holds = [rnd.uniform(90, 140) for _ in range(12)]
    raw = [rnd.gauss(0, 70) for _ in range(11)]
    for i in rnd.sample(range(11), 3):
        raw[i] += 160  # occasional pauses, as in real typing (keeps flight entropy realistic)
    mean = sum(raw) / len(raw)
    flights = [f - mean + 12.0 for f in raw]  # mean exactly 12 ms, wide spread: rollover typing
    return _keys(flights, holds)


def _autotyper(seed, jitter):
    rnd = random.Random(seed)
    holds = [rnd.uniform(60, 90) for _ in range(12)]
    flights = [10 + rnd.uniform(-jitter, jitter) for _ in range(11)]
    return _keys(flights, holds)


def _features(keys, force_python=True):
    return feat.extract_features({"mouse_movements": [], "clicks": [], "keystrokes": keys, "scrolls": [],
                                  "browser": dict(BROWSER)}, force_python=force_python)


@pytest.mark.parametrize("seed", range(20))
def test_rollover_typist_is_not_superhuman(seed):
    f = _features(_rollover_typist(seed))
    assert 0 < f["key_interval_avg"] < 25, f["key_interval_avg"]
    assert f["key_interval_var"] > engine.SUPERHUMAN_KEY_MAX_VAR_MS2
    assert not _superhuman_key_interval(f)
    assert f["keystroke_score"] < 0.70, f["keystroke_score"]


@pytest.mark.parametrize("jitter", [0, 5, 15, 30])
def test_autotyper_is_still_superhuman(jitter):
    f = _features(_autotyper(1, jitter))
    assert 0 < f["key_interval_avg"] < 25
    assert _superhuman_key_interval(f)
    assert f["keystroke_score"] >= 0.70


def test_variance_boundary():
    assert _superhuman_key_interval({"key_interval_avg": 10.0, "key_interval_var": 999.0})
    assert not _superhuman_key_interval({"key_interval_avg": 10.0, "key_interval_var": 1000.0})
    assert not _superhuman_key_interval({"key_interval_avg": 25.0, "key_interval_var": 0.0})
    assert not _superhuman_key_interval({"key_interval_avg": 0.0, "key_interval_var": 0.0})


def test_constant_is_shared_with_features():
    assert engine.SUPERHUMAN_KEY_MAX_VAR_MS2 == feat.SUPERHUMAN_FLIGHT_MAX_VAR == 1000.0


@pytest.mark.skipif(synapse_core_rs is None, reason="Rust core not built")
@pytest.mark.parametrize("make", [lambda: _rollover_typist(3), lambda: _autotyper(2, 0), lambda: _autotyper(2, 20)])
def test_rust_and_python_keystroke_scores_agree(make):
    keys = make()
    py = _features(keys, force_python=True)
    rs = _features(keys, force_python=False)
    assert py["keystroke_score"] == pytest.approx(rs["keystroke_score"], abs=1e-9)


def test_end_to_end_rollover_typing_is_not_blocked_for_speed():
    moves = [{"x": 200 + 9 * i + (i % 3), "y": 300 + 4 * i + (i % 2) * 3, "t": 1000 + 33 * i} for i in range(25)]
    keys = _rollover_typist(5)
    tel = {"mouse_movements": moves, "clicks": [{"x": 420, "y": 400, "t": 1900}], "keystrokes": keys,
           "scrolls": [], "browser": dict(BROWSER)}
    _, _, reasons, _ = analyze_behavior(tel)
    assert not any("Superhuman input frequency" in r for r in reasons), reasons
