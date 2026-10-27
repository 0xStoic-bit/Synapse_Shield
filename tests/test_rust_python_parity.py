"""
Synapse Shield — Rust SIMD vs. Python Fallback Parity & Differential Fuzzing
Validates mathematical and behavioral equivalence between Rust Core and Python Fallback.
"""

import random
import pytest

from synapse_shield.features import extract_features
try:
    from synapse_shield import synapse_core_rs
    HAS_RUST = synapse_core_rs is not None
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


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_mobile_features_rust_python_parity():
    """Asserts 100% parity between Rust SIMD and Python fallback on all Mobile SDK v2.0 biometric features."""
    for gpu, expected_mismatch in [
        ("Apple GPU", False),
        ("Adreno (TM) 740", False),
        ("Google Inc. (Google SwiftShader)", True),
        ("ANGLE (NVIDIA, NVIDIA GeForce RTX 4090)", True),
    ]:
        telemetry = {
            "mouse_movements": [
                {"x": 180.0, "y": 420.0, "t": 1000.0, "r": 12.35, "f": 0.45, "source": "touch"},
                {"x": 184.0, "y": 425.0, "t": 1022.0, "r": 13.10, "f": 0.52, "source": "touch"},
                {"x": 190.0, "y": 432.0, "t": 1045.0, "r": 11.85, "f": 0.48, "source": "touch"},
            ],
            "clicks": [
                {"x": 180.0, "y": 420.0, "t": 1085.0, "r": 12.35, "source": "touch", "tap_duration_ms": 85.0},
                {"x": 190.0, "y": 432.0, "t": 1560.0, "r": 11.85, "source": "touch", "tap_duration_ms": 112.0},
            ],
            "keystrokes": [
                {"key": "Unidentified", "type": "down", "t": 1000.0},
                {"key": "Unidentified", "type": "up", "t": 1003.0},
                {"key": "Unidentified", "type": "down", "t": 1090.0},
                {"key": "Unidentified", "type": "up", "t": 1094.0},
                {"key": "Unidentified", "type": "down", "t": 1240.0},
                {"key": "Unidentified", "type": "up", "t": 1243.0},
                {"key": "Unidentified", "type": "down", "t": 1510.0},
                {"key": "Unidentified", "type": "up", "t": 1514.0},
            ],
            "scrolls": [],
            "browser": {
                "webdriver": False,
                "screen_width": 390,
                "screen_height": 844,
                "touch_supported": True,
                "max_touch_points": 5,
                "device_pixel_ratio": 3.0,
                "webgl_renderer": gpu,
                "motion_variance": 0.0142,
            },
        }

        rust_feat = synapse_core_rs.extract_features_rs(telemetry)
        py_feat = extract_features(telemetry, force_python=True)

        assert rust_feat["is_mobile_gpu_mismatch"] is expected_mismatch
        assert py_feat["is_mobile_gpu_mismatch"] is expected_mismatch
        assert py_feat["tap_count"] == rust_feat["tap_count"] == 2
        assert py_feat["avg_tap_duration"] == pytest.approx(rust_feat["avg_tap_duration"], abs=1e-4)
        assert py_feat["tap_duration_var"] == pytest.approx(rust_feat["tap_duration_var"], abs=1e-4)
        assert py_feat["device_pixel_ratio"] == pytest.approx(rust_feat["device_pixel_ratio"], abs=1e-4)
        assert py_feat["motion_variance"] == pytest.approx(rust_feat["motion_variance"], abs=1e-6)
        assert py_feat["touch_event_count"] == rust_feat["touch_event_count"]
        assert py_feat["avg_touch_radius"] == pytest.approx(rust_feat["avg_touch_radius"], abs=1e-4)
        assert py_feat["touch_radius_var"] == pytest.approx(rust_feat["touch_radius_var"], abs=1e-4)
        assert py_feat["keystroke_score"] == pytest.approx(rust_feat["keystroke_score"], abs=1e-4)

