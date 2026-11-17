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


def _sdk_masked_keystrokes(gaps_and_flags, dwells):
    """Build keystrokes exactly as the v0.10.4+ SDKs send them: key="masked" plus is_freq_digraph."""
    ks = []
    t = 1000.0
    for (gap, is_freq), dwell in zip(gaps_and_flags, dwells):
        t += gap
        ks.append({"type": "down", "key": "masked", "t": t, "is_freq_digraph": is_freq})
        ks.append({"type": "up", "key": "masked", "t": t + dwell, "duration_ms": dwell, "is_freq_digraph": is_freq})
    return ks


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_masked_sdk_digraph_flag_rust_python_parity():
    """Regression: the Rust core used to ignore the SDK's client-side is_freq_digraph flag
    (Python 0.40 vs Rust 0.00 on the same masked telemetry). Fixed 2026-11-06."""
    # Frequent digraphs typed *slower* than rare ones: no linguistic muscle memory (+0.40 in Python).
    gaps_and_flags = [
        (0.0, False), (300.0, True), (130.0, False), (280.0, True), (150.0, False),
        (320.0, True), (95.0, False), (260.0, True), (170.0, False), (140.0, False),
    ]
    dwells = [92.0, 118.0, 76.0, 131.0, 104.0, 88.0, 112.0, 97.0, 125.0, 83.0]
    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": _sdk_masked_keystrokes(gaps_and_flags, dwells),
        "scrolls": [],
        "browser": {"touch_supported": False},
    }
    rust_feat = extract_features(telemetry)
    py_feat = extract_features(telemetry, force_python=True)
    assert py_feat["keystroke_score"] == pytest.approx(rust_feat["keystroke_score"], abs=1e-4)



@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_masked_sdk_keystrokes_differential_fuzz():
    """Differential fuzzing on SDK-shaped (masked + is_freq_digraph) keystrokes.

    Before the fix, 25 of 60 random samples scored differently in Rust and Python. Covers typed
    down/up pairs, untyped legacy events, missing/None flags, IME keys and Turkish letters.
    """
    rng = random.Random(20261106)
    for _ in range(200):
        n = rng.randint(3, 25)
        ks, t = [], 1000.0
        style = rng.choice(["typed", "untyped"])
        for i in range(n):
            t += rng.uniform(20.0, 400.0)
            dwell = rng.uniform(5.0, 200.0)
            key = rng.choice(["masked", "masked", "masked", "Unidentified", "Process", "ş", "a", "Enter"])
            flag = rng.choice([True, False, None, "absent"])
            if style == "typed":
                down = {"type": "down", "key": key, "t": t}
                up = {"type": "up", "key": key, "t": t + dwell, "duration_ms": dwell}
                if flag != "absent":
                    down["is_freq_digraph"] = flag
                    if rng.random() < 0.5:
                        up["is_freq_digraph"] = flag
                ks += [down, up]
            else:
                ev = {"key": key, "t": t, "up": t + dwell}
                if flag != "absent":
                    ev["is_freq_digraph"] = flag
                ks.append(ev)
        telemetry = {"mouse_movements": [], "clicks": [], "keystrokes": ks, "scrolls": [],
                     "browser": {"touch_supported": False}}
        rust = extract_features(telemetry)
        py = extract_features(telemetry, force_python=True)
        assert py["keystroke_score"] == pytest.approx(rust["keystroke_score"], abs=1e-4), ks


_BROWSER_VARIANTS = [
    None, True, False, 0, 1, 5, -3, 1920, 2**70, -(2**70), 0.0, 390.0, 1920.7, -1.5, float("nan"), float("inf"),
    1e300, "1920", "390", "5", "5.9", "-2", "1e3", ".5", "5.", "+7", "", " 1920", "1920 ", "1_920", "inf", "nan",
    "abc", "0x10", "1e400", "true", "False", "1", "0", "9" * 70, [], {}, b"1920",
]
_BROWSER_FIELDS = ["screen_width", "screen_height", "max_touch_points", "plugins_length", "device_pixel_ratio",
                   "motion_variance", "webdriver", "touch_supported"]
_BROWSER_OUT = ["screen_width", "screen_valid", "max_touch_points", "plugins_length", "device_pixel_ratio",
                "motion_variance", "webdriver", "touch_supported", "mobile_hardware_mismatch"]


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (a != a and b != b) or abs(a - b) < 1e-9
    return a == b and type(a) is type(b)


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_browser_numeric_fields_string_float_none_bool_parity():
    """screen_width="1920" used to give Python 1920 and Rust 0. Both sides now share one strict parser."""
    rng = random.Random(20261117)
    cases = [{f: v} for f in _BROWSER_FIELDS for v in _BROWSER_VARIANTS]
    for _ in range(400):
        cases.append({f: rng.choice(_BROWSER_VARIANTS) for f in _BROWSER_FIELDS if rng.random() < 0.7})
    for browser in cases:
        browser.setdefault("webgl_renderer", "Apple GPU")
        tel = {"browser": browser, "mouse_movements": [{"x": 1.0, "y": 2.0, "t": 0.0}, {"x": 5.0, "y": 9.0, "t": 16.0}]}
        py = extract_features(tel, force_python=True)
        rs = extract_features(tel)
        for k in _BROWSER_OUT:
            assert _same(py.get(k), rs.get(k)), f"{k} mismatch for {browser!r}: py={py.get(k)!r} rs={rs.get(k)!r}"
    f = extract_features({"browser": {"screen_width": "1920", "screen_height": "1080", "max_touch_points": "5"}})
    assert f["screen_width"] == 1920.0 and f["screen_valid"] and f["max_touch_points"] == 5


@pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")
def test_raw_key_name_fast_frequent_digraphs_cannot_lower_score():
    """Raw key names are client data: 'frequent digraphs faster' must not subtract 0.25 (Rust and Python)."""
    keys, t, ks = "thxqthzwthjk", 0.0, []
    for i, k in enumerate(keys):
        t += 40.0 if (i > 0 and keys[i - 1:i + 1] == "th") else 300.0 + 2.0 * i
        ks.append({"key": k, "down": t, "up": t + 9.0})  # 9 ms dwell -> +0.75, the only other evidence
    tel = {"browser": {"screen_width": 1920, "screen_height": 1080}, "keystrokes": ks}
    py = extract_features(tel, force_python=True)["keystroke_score"]
    rs = extract_features(tel)["keystroke_score"]
    assert abs(py - rs) < 1e-9
    assert py >= 0.75, py
