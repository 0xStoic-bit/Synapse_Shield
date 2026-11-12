"""v0.10.7: the sub-movement "stutter" rule needs a high peak DENSITY, not just a high peak count.

The raw count grows with window length, so long real sessions with several aimed movements exceeded 18.
"""

import math
import random

import pytest

from synapse_shield import engine
from synapse_shield.engine import analyze_behavior

BROWSER = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False}


def _reasons(moves):
    last = moves[-1]
    tel = {"mouse_movements": moves, "clicks": [{"x": last["x"], "y": last["y"], "t": last["t"] + 80}],
           "keystrokes": [], "scrolls": [], "browser": dict(BROWSER)}
    return analyze_behavior(tel)[2]


def _long_human_like(n_moves: int, seed: int) -> list[dict]:
    """Several aimed, bell-shaped movements back to back (many velocity peaks overall, low density)."""
    rnd = random.Random(seed)
    out, t, x, y = [], 1000, 100.0, 200.0
    for _ in range(n_moves):
        dx, dy = rnd.uniform(150, 500), rnd.uniform(-200, 200)
        n = rnd.randint(28, 40)
        for i in range(1, n):
            u = i / (n - 1)
            s = 10 * u**3 - 15 * u**4 + 6 * u**5
            t += 30
            out.append({"x": round(x + dx * s + rnd.uniform(-0.8, 0.8)),
                        "y": round(y + dy * s + 25 * math.sin(math.pi * s) + rnd.uniform(-0.8, 0.8)), "t": t})
        x, y = out[-1]["x"], out[-1]["y"]
        t += rnd.randint(150, 400)
    return out


def _stutter_bot(n: int, seed: int, noise: float = 4.0) -> list[dict]:
    rnd = random.Random(seed)
    return [{"x": round(100 + i * 8 + rnd.uniform(-noise, noise)), "y": round(300 + rnd.uniform(-noise, noise)),
             "t": 1000 + i * 30} for i in range(n)]


def _is_stutter(reason: str) -> bool:
    return "sub-movement stutter" in reason


def test_constants_are_exposed():
    assert engine.STUTTER_MIN_PEAKS == 18
    assert 0.15 < engine.STUTTER_MIN_PEAK_DENSITY < 0.33


@pytest.mark.parametrize("seed", range(10))
def test_long_human_sessions_are_not_stutter(seed):
    moves = _long_human_like(8, seed)
    from synapse_shield.features import extract_features
    f = extract_features({"mouse_movements": moves, "clicks": [], "keystrokes": [], "scrolls": [],
                          "browser": dict(BROWSER)}, force_python=True)
    assert f["submovement_count"] > engine.STUTTER_MIN_PEAKS, "fixture must exceed the raw peak count"
    assert not any(_is_stutter(r) for r in _reasons(moves))


@pytest.mark.parametrize("seed", range(10))
def test_independent_noise_stutter_bot_is_still_flagged(seed):
    assert any(_is_stutter(r) for r in _reasons(_stutter_bot(80, seed)))


def test_density_is_peaks_per_sample(monkeypatch):
    moves = _stutter_bot(80, 1)
    assert any(_is_stutter(r) for r in _reasons(moves))
    monkeypatch.setattr(engine, "STUTTER_MIN_PEAK_DENSITY", 0.99)
    assert not any(_is_stutter(r) for r in _reasons(moves))
