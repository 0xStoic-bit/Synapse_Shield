"""v0.10.6: the "chaotic curvature" check must ignore stop/quantisation artefacts.

kappa = |v x a| / |v|^3 explodes as the cursor slows to a stop; real human pointing ends in slow homing,
so the ungated variance flagged ~67% of real human windows (SapiMouse replay, research/human_sim).
"""

import math
import random

import pytest

from synapse_shield import features as feat
from synapse_shield.engine import analyze_behavior

try:
    from synapse_shield import synapse_core_rs
except ImportError:  # pragma: no cover
    try:
        import synapse_core_rs
    except ImportError:
        synapse_core_rs = None


def _browser():
    return {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
            "touch_supported": False}


def _human_like_moves(rnd: random.Random) -> list[dict]:
    """What the SDK sends for real human pointing: a curved, decelerating aimed movement (1-px quantised,
    30 ms throttled) that stops near the target, then a few 1-px corrections after 150-550 ms pauses.
    The browser emits nothing while the cursor rests, so each correction is a tiny step over a long gap:
    |v| is near zero there and kappa = |v x a| / |v|^3 reaches 30-100 (pattern measured on SapiMouse)."""
    moves = []
    t = 1000.0
    x0, y0 = 100.0, 200.0
    for _ in range(3):
        n = rnd.randint(14, 22)
        bow = rnd.uniform(30, 90) * rnd.choice([-1, 1])
        dx, dy = rnd.uniform(250, 500), rnd.uniform(-250, 250)
        for i in range(1, n):
            u = i / (n - 1)
            s = 1 - (1 - u) ** 2.2
            x = x0 + dx * s - bow * math.sin(math.pi * s) * dy / math.hypot(dx, dy)
            y = y0 + dy * s + bow * math.sin(math.pi * s) * dx / math.hypot(dx, dy) + rnd.uniform(-1.5, 1.5)
            t += 30 + rnd.randint(0, 4)
            moves.append({"x": round(x), "y": round(y), "t": round(t)})
        cx, cy = moves[-1]["x"], moves[-1]["y"]
        for _ in range(rnd.randint(2, 4)):
            t += rnd.uniform(150, 550)
            cx += rnd.choice([-1, 1]) if rnd.random() < 0.5 else 0
            cy += rnd.choice([-1, 1])
            moves.append({"x": cx, "y": cy, "t": round(t)})
        x0, y0 = cx, cy
        t += rnd.uniform(200, 600)
    return moves


def _min_jerk_moves(bow: float = 80.0) -> list[dict]:
    """Minimum-jerk bot rounded to 0.01 px (as adversarial.generate_* do). Speed is ~0 at both ends, so the
    rounding noise there inflates the all-points variance: only the moving-points statistic flags it."""
    moves = []
    n = 50
    for i in range(n):
        u = i / (n - 1)
        s = 10 * u**3 - 15 * u**4 + 6 * u**5
        moves.append({"x": round(100 + 600 * s, 2), "y": round(100 + 350 * s + bow * math.sin(math.pi * s), 2),
                      "t": 1000 + i * 25})
    return moves


def _xyt(moves):
    return [m["x"] for m in moves], [m["y"] for m in moves], [m["t"] for m in moves]


@pytest.mark.parametrize("seed", range(20))
def test_stop_artefacts_are_not_chaotic_curvature(seed):
    moves = _human_like_moves(random.Random(seed))
    m = feat._curvature_metrics(*_xyt(moves))
    # The ungated variance is still dominated by the stop artefact; only the verdict changes.
    assert m["curvature_score"] < 0.75, m
    f = feat.extract_features({"mouse_movements": moves, "clicks": [], "keystrokes": [], "scrolls": [],
                               "browser": _browser()}, force_python=True)
    assert f["curvature_score"] < 0.75


@pytest.mark.parametrize("bow", [0.0, 80.0])
def test_minimum_jerk_with_resting_ends_is_flagged(bow):
    m = feat._curvature_metrics(*_xyt(_min_jerk_moves(bow)))
    # Guard that this fixture really needs the moving-points path: the all-points moments are not smooth.
    assert m["curvature_var"] > 1e-4 and m["curvature_rate_var"] > 1e-8, m
    assert m["curvature_score"] >= 0.90, m


def test_gated_dt_matches_all_points_dt_when_nothing_is_dropped():
    """Irregular sampling: the gated d(kappa)/dt spacing must be the all-points spacing (dt_a[1:])."""
    np = feat.np
    dt_a = np.array([20.0, 16.5, 33.0, 41.5, 25.0, 16.0])
    assert np.array_equal(feat._gated_dts(dt_a, np.ones(6, bool)), dt_a[1:])


def test_gated_dt_sums_the_steps_of_dropped_points():
    np = feat.np
    dt_a = np.array([20.0, 16.5, 33.0, 41.5, 25.0, 16.0])
    keep = np.array([True, False, True, True, False, True])
    # kept 0 -> 2: 16.5 + 33.0; 2 -> 3: 41.5; 3 -> 5: 25.0 + 16.0
    assert feat._gated_dts(dt_a, keep).tolist() == [49.5, 41.5, 41.0]
    assert feat._gated_dts(dt_a, np.array([False, False, True, False, False, True])).tolist() == [82.5]


def test_too_few_moving_points_gives_no_chaos_verdict():
    rnd = random.Random(11)
    moves = [{"x": round(300 + rnd.uniform(-2, 2)), "y": round(300 + rnd.uniform(-2, 2)), "t": 1000 + i * 30}
             for i in range(30)]
    assert feat._curvature_metrics(*_xyt(moves))["curvature_score"] < 0.75


def test_human_like_path_is_not_blocked_by_curvature_rule():
    tel = {"mouse_movements": _human_like_moves(random.Random(3)), "clicks": [], "keystrokes": [],
           "scrolls": [], "browser": _browser()}
    _, _, reasons, _ = analyze_behavior(tel)
    assert not any("differential curvature" in r for r in reasons), reasons


@pytest.mark.skipif(synapse_core_rs is None, reason="Rust core not built")
@pytest.mark.parametrize("seed", range(10))
def test_rust_and_python_curvature_agree(seed):
    rnd = random.Random(100 + seed)
    for moves in (_human_like_moves(rnd), _min_jerk_moves()):
        x, y, t = _xyt(moves)
        py = feat._curvature_metrics(x, y, t)
        rs = synapse_core_rs.evaluate_curvature_zerocopy_rs(x, y, t)
        assert py["curvature_score"] == rs["curvature_score"]
        for k in ("mean_curvature", "curvature_var", "curvature_rate_var"):
            assert py[k] == pytest.approx(rs[k], rel=1e-9, abs=1e-12)
