"""
Synapse Shield v0.9.2 - Differential Curvature Analysis & Keystroke Dynamics Test Suite
"""

import math
import numpy as np
import pytest
import time
from synapse_shield.features import extract_features, evaluate_curvature_zerocopy, is_rust_accelerated
from synapse_shield.engine import analyze_behavior
from synapse_shield.adversarial import (
    generate_bezier_telemetry,
    generate_synthetic_human_telemetry,
    generate_minimum_jerk_telemetry,
)

try:
    import synapse_core_rs
    HAS_RUST = True
except ImportError:
    HAS_RUST = False


def test_v092_bezier_curvature_detection():
    """Bézier curves exhibit unnaturally smooth rate of curvature variance and must be flagged."""
    telemetry = generate_bezier_telemetry(
        start=(100.0, 100.0),
        end=(700.0, 450.0),
        steps=65,
        duration_ms=1200.0,
    )
    features = extract_features(telemetry)
    assert "curvature_score" in features
    assert features["curvature_score"] >= 0.75
    assert features["curvature_rate_var"] < 1e-6

    score, decision, reasons, _ = analyze_behavior(telemetry)
    assert decision == "Bot"
    assert any("curvature" in r.lower() for r in reasons)


def test_v092_natural_human_curvature():
    """Biological human trajectory with neuromuscular damping must pass curvature analysis."""
    telemetry = generate_synthetic_human_telemetry(
        start=(120.0, 140.0),
        end=(680.0, 520.0),
        steps=55,
        duration_ms=1500.0,
    )
    features = extract_features(telemetry)
    assert features["curvature_score"] < 0.35
    assert features["curvature_rate_var"] > 1e-8

    score, decision, reasons, _ = analyze_behavior(telemetry)
    assert decision == "Human"
    assert not any("curvature" in r.lower() for r in reasons)


def test_v092_zerocopy_simd_numpy_buffer():
    """Verify AVX2 SIMD zero-copy buffer evaluation directly on NumPy float64 arrays."""
    steps = 100
    t = np.linspace(0, 1500, steps, dtype=np.float64)
    # Cubic polynomial
    tau = np.linspace(0, 1, steps, dtype=np.float64)
    x = (100.0 + 500.0 * (3 * tau**2 - 2 * tau**3)).astype(np.float64)
    y = (100.0 + 350.0 * np.sin(tau * np.pi)).astype(np.float64)

    metrics = evaluate_curvature_zerocopy(x, y, t)
    assert "curvature_score" in metrics
    assert "mean_curvature" in metrics
    assert "curvature_var" in metrics
    assert "curvature_rate_var" in metrics
    assert isinstance(metrics["curvature_score"], float)
    assert metrics["mean_curvature"] >= 0.0

    if HAS_RUST:
        rs_metrics = synapse_core_rs.evaluate_curvature_zerocopy_rs(x, y, t)
        assert abs(metrics["curvature_score"] - rs_metrics["curvature_score"]) < 1e-4


def test_v092_keystroke_dwell_and_flight_bot_detection():
    """Constant dwell time (e.g. 50ms) and fixed interval flight times must be flagged as robotic."""
    # Synthetic bot typing 10 characters with robotic 50ms dwell and 100ms interval
    keystrokes = []
    base_t = 1000.0
    for i in range(10):
        t_down = base_t + i * 150.0
        t_up = t_down + 50.0
        key_char = "a" if i % 2 == 0 else "b"
        keystrokes.append({"t": t_down, "down": t_down, "up": t_up, "key": key_char, "type": "down"})
        keystrokes.append({"t": t_up, "down": t_down, "up": t_up, "key": key_char, "type": "up"})

    telemetry = {
        "mouse_movements": [
            {"x": 100.0 + i * 5.0, "y": 100.0 + i * 3.0, "t": 1000.0 + i * 20.0}
            for i in range(30)
        ],
        "clicks": [],
        "keystrokes": keystrokes,
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "touch_supported": False,
        },
    }

    if HAS_RUST:
        metrics = synapse_core_rs.evaluate_keystroke_dynamics_rs(keystrokes)
        assert metrics["avg_dwell_time"] == pytest.approx(50.0, abs=1.0)
        assert metrics["dwell_time_var"] == pytest.approx(0.0, abs=0.5)
        assert metrics["keystroke_score"] >= 0.70

    score, decision, reasons, _ = analyze_behavior(telemetry)
    assert decision == "Bot"
    assert any("keystroke" in r.lower() or "robotic" in r.lower() for r in reasons)


def test_v092_bypass_hunter_redteam_payload():
    """
    Red Team Test: Verify that the user's Hermite cubic S-curve bypass payload
    is completely blocked by Synapse Shield v0.9.2.
    """
    steps = 65
    start_x, start_y = 100.0, 100.0
    end_x, end_y = 700.0, 450.0
    current_time = 1000.0

    t = np.linspace(0, 1, steps)
    submovements = 3 * t**2 - 2 * t**3
    telemetry_moves = []
    for i in range(steps):
        prog = submovements[i]
        x = start_x + (end_x - start_x) * prog
        y = start_y + (end_y - start_y) * prog
        telemetry_moves.append({"x": float(x), "y": float(y), "t": float(current_time + i * 16.0)})

    payload = {
        "mouse_movements": telemetry_moves,
        "clicks": [{"x": end_x, "y": end_y, "t": current_time + steps * 16.0 + 50.0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "touch_supported": False,
        },
    }

    features = extract_features(payload)
    # The linear path with mathematical sigmoid speed has zero differential curvature
    assert features["curvature_score"] >= 0.90 or features["straightness"] > 0.99

    score, decision, reasons, _ = analyze_behavior(payload)
    assert decision == "Bot"
    assert any("curvature" in r.lower() or "straight" in r.lower() for r in reasons)
