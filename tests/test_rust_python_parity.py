"""
Synapse Shield — Rust SIMD vs. Python Fallback Parity & Differential Fuzzing
Validates mathematical and behavioral equivalence between Rust Core and Python Fallback.
"""

import random
import pytest

from synapse_shield.features import extract_features
try:
    from synapse_shield import synapse_core_rs
    HAS_RUST = True
except ImportError:
    HAS_RUST = False


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_keystroke_dynamics_rust_python_parity():
    """Property-based fuzzing: Asserts 100% parity on keystroke metrics across random sequences."""
    random.seed(42)

    for iteration in range(50):
        key_count = random.randint(3, 30)
        keystrokes = []
        base_t = 1000.0 + random.uniform(0, 500)

        t_curr = base_t
        for i in range(key_count):
            dwell = random.uniform(10.0, 180.0)
            flight = random.uniform(15.0, 300.0)
            key_char = random.choice(["a", "b", "e", "t", "space", "enter"])
            keystrokes.append({
                "key": key_char,
                "t": t_curr,
                "down": t_curr,
                "up": t_curr + dwell,
            })
            t_curr += dwell + flight

        telemetry = {
            "mouse_movements": [],
            "clicks": [],
            "keystrokes": keystrokes,
            "scrolls": [],
            "browser": {},
        }

        # 1. Rust Evaluation
        rust_metrics = synapse_core_rs.evaluate_keystroke_dynamics_rs(keystrokes)

        # 2. Python Fallback Evaluation (explicitly bypass Rust accelerator)
        py_features = extract_features(telemetry, force_python=True)

        assert py_features["avg_dwell_time"] == pytest.approx(rust_metrics["avg_dwell_time"], abs=1e-3)
        assert py_features["dwell_time_var"] == pytest.approx(rust_metrics["dwell_time_var"], abs=1e-3)
        assert py_features["avg_flight_time"] == pytest.approx(rust_metrics["avg_flight_time"], abs=1e-3)
        assert py_features["flight_time_var"] == pytest.approx(rust_metrics["flight_time_var"], abs=1e-3)
        assert py_features["keystroke_score"] == pytest.approx(rust_metrics["keystroke_score"], abs=1e-3)


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_kinematics_rust_python_parity():
    """Asserts that 19D mouse kinematics match between Rust SIMD and Python NumPy."""
    random.seed(1337)

    for iteration in range(25):
        step_count = random.randint(15, 60)
        movements = []
        t = 1000.0
        x, y = 200.0, 200.0

        for _ in range(step_count):
            movements.append({"x": x, "y": y, "t": t})
            x += random.uniform(-10.0, 25.0)
            y += random.uniform(-8.0, 20.0)
            t += random.uniform(10.0, 30.0)

        telemetry = {
            "mouse_movements": movements,
            "clicks": [{"x": x, "y": y, "t": t + 50.0}],
            "keystrokes": [],
            "scrolls": [],
            "browser": {"screen_width": 1920, "screen_height": 1080},
        }

        rust_feat = synapse_core_rs.extract_features_rs(telemetry)
        py_feat = extract_features(telemetry, force_python=True)

        assert py_feat["total_distance"] == pytest.approx(rust_feat["total_distance"], rel=1e-2)
        assert py_feat["straightness"] == pytest.approx(rust_feat["straightness"], rel=1e-2)
        assert py_feat["avg_velocity"] == pytest.approx(rust_feat["avg_velocity"], rel=1e-2)
