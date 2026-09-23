"""
Synapse Shield v0.8.0 - Native Rust Core Parity and Performance Verification Suite
"""

import time
import pytest
from synapse_shield.features import extract_features, is_rust_accelerated
from synapse_shield.adversarial import (
    generate_bezier_telemetry,
    generate_sine_oscillator_telemetry,
    generate_minimum_jerk_telemetry,
    generate_synthetic_human_telemetry
)

try:
    import synapse_core_rs
    HAS_RUST = True
except ImportError:
    HAS_RUST = False


def test_rust_module_availability():
    """Verify that the native synapse_core_rs extension is compiled and accessible."""
    if not HAS_RUST:
        pytest.skip("synapse_core_rs binary extension not installed in current environment.")
    
    assert synapse_core_rs.is_rust_core_active() is True
    assert "0.8.0" in synapse_core_rs.get_core_version()
    assert is_rust_accelerated() is True


@pytest.mark.parametrize("generator", [
    generate_synthetic_human_telemetry,
    generate_bezier_telemetry,
    generate_sine_oscillator_telemetry,
    generate_minimum_jerk_telemetry,
])
def test_rust_vs_python_parity(generator):
    """
    Ensure 100% mathematical parity across all 24 features between
    the native Rust core and the pure Python/NumPy implementation.
    """
    if not HAS_RUST:
        pytest.skip("synapse_core_rs not installed")

    telemetry = generator()
    py_feat = extract_features(telemetry, force_python=True)
    rs_feat = extract_features(telemetry, force_python=False)

    assert set(py_feat.keys()) == set(rs_feat.keys()), "Feature keys mismatch"

    for key, py_val in py_feat.items():
        rs_val = rs_feat[key]
        if isinstance(py_val, float):
            assert abs(py_val - rs_val) < 1e-4, f"Parity mismatch on float feature '{key}': py={py_val}, rs={rs_val}"
        else:
            assert py_val == rs_val, f"Parity mismatch on discrete feature '{key}': py={py_val}, rs={rs_val}"


def test_edge_cases_and_graceful_handling():
    """Verify that Rust core gracefully handles edge cases, empty payloads, and invalid data."""
    if not HAS_RUST:
        pytest.skip("synapse_core_rs not installed")

    # Empty dictionary
    empty_feat = extract_features({}, force_python=False)
    assert empty_feat["mouse_points"] == 0
    assert empty_feat["straightness"] == 1.0

    # Malformed mouse points with NaN/Infs
    malformed = {
        "mouse_movements": [
            {"x": "not_a_num", "y": 10.0, "t": 100.0},
            {"x": float("nan"), "y": 20.0, "t": 200.0},
            {"x": 100.0, "y": 100.0, "t": 300.0},
            {"x": 150.0, "y": 120.0, "t": 350.0},
            {"x": 200.0, "y": 140.0, "t": 400.0},
        ],
        "browser": {"webdriver": True, "screen_width": -1}
    }
    feat = extract_features(malformed, force_python=False)
    assert feat["mouse_points"] == 3
    assert feat["webdriver"] is True
    assert feat["screen_valid"] is False


def test_rust_performance_speedup():
    """Verify that the native Rust implementation is measurably faster than pure Python."""
    if not HAS_RUST:
        pytest.skip("synapse_core_rs not installed")

    telemetry = generate_synthetic_human_telemetry()

    # Python timing
    t0 = time.perf_counter_ns()
    for _ in range(100):
        extract_features(telemetry, force_python=True)
    t_py = (time.perf_counter_ns() - t0) / 100

    # Rust timing
    t0 = time.perf_counter_ns()
    for _ in range(100):
        extract_features(telemetry, force_python=False)
    t_rs = (time.perf_counter_ns() - t0) / 100

    # Rust must be at least 2x faster than pure Python
    speedup = t_py / t_rs
    assert speedup > 2.0, f"Expected Rust to be > 2.0x faster, got {speedup:.2f}x (py={t_py/1000:.1f}us, rs={t_rs/1000:.1f}us)"


def test_rust_two_bucket_nonce_deduplication():
    """Verify that the Two-Bucket Rust cache detects replays instantly."""
    if not HAS_RUST:
        pytest.skip("synapse_core_rs not installed")

    synapse_core_rs.clear_state_engine_rs()
    nonce1 = "test_nonce_alpha_12345"
    nonce2 = "test_nonce_beta_67890"

    # First consumption succeeds
    assert synapse_core_rs.consume_nonce_rs(nonce1) is True
    assert synapse_core_rs.consume_nonce_rs(nonce2) is True

    # Immediate replay fails
    assert synapse_core_rs.consume_nonce_rs(nonce1) is False
    assert synapse_core_rs.consume_nonce_rs(nonce2) is False

    stats = synapse_core_rs.get_state_engine_stats_rs()
    assert stats["current_bucket_nonces"] == 2


def test_rust_l1_ip_ban_lifecycle():
    """Verify that L1 IP Ban Cache operates in nanoseconds with hydration and expiry."""
    if not HAS_RUST:
        pytest.skip("synapse_core_rs not installed")

    synapse_core_rs.clear_state_engine_rs()
    test_ip = "192.168.1.55"

    assert synapse_core_rs.is_ip_banned_rs(test_ip) is False

    # Ban for 10 seconds
    synapse_core_rs.ban_ip_rs(test_ip, 10)
    assert synapse_core_rs.is_ip_banned_rs(test_ip) is True

    # Unban
    synapse_core_rs.unban_ip_rs(test_ip)
    assert synapse_core_rs.is_ip_banned_rs(test_ip) is False

    # Hydrate multiple bans
    future_epoch = int(time.time()) + 100
    synapse_core_rs.hydrate_bans_rs([("10.0.0.1", future_epoch), ("10.0.0.2", future_epoch)])
    assert synapse_core_rs.is_ip_banned_rs("10.0.0.1") is True
    assert synapse_core_rs.is_ip_banned_rs("10.0.0.2") is True
    assert synapse_core_rs.is_ip_banned_rs("10.0.0.3") is False


def test_storage_backend_integration_with_rust():
    """Verify that SQLiteStorageBackend delegates to Rust L1 seamlessly."""
    from synapse_shield.storage import SQLiteStorageBackend

    backend = SQLiteStorageBackend()
    backend.clear_all()

    # Nonce check
    n = "storage_test_nonce_xyz"
    assert backend.consume_nonce(n) is True
    assert backend.consume_nonce(n) is False  # Replay blocked

    # IP Ban check
    ip = "172.16.0.42"
    assert backend.is_ip_banned(ip) is False
    backend.ban_ip(ip, duration_sec=5)
    assert backend.is_ip_banned(ip) is True
    backend.unban_ip(ip)
    assert backend.is_ip_banned(ip) is False
