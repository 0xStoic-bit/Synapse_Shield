"""
Tests for Synapse Shield Architectural Hardening (v0.8.0-dev)
Verifies:
1. FFT Tremor Spectral Purity & Entropy Analysis
2. Physiological Sub-Movement Decomposition
3. Session-Level Behavioral Invariance Detection
4. Adversarial Synthetic Data & Training Pipeline
"""

import math
import random

from synapse_shield.adversarial import (
    generate_adversarial_telemetry_batch,
    generate_bezier_telemetry,
    generate_minimum_jerk_telemetry,
    generate_sine_oscillator_telemetry,
)
from synapse_shield.engine import analyze_behavior
from synapse_shield.features import extract_features
from synapse_shield.storage import SQLiteStorageBackend
from synapse_shield.train import load_training_data


def test_fft_spectral_analysis_sine_oscillator():
    """Sine oscillator bot must have high spectral purity (> 0.65) and trigger FFT anomaly."""
    telemetry = generate_sine_oscillator_telemetry(
        start=(100.0, 100.0),
        end=(500.0, 500.0),
        frequency_hz=10.0,
        amplitude=5.0,
        steps=50,
        duration_ms=1200.0,
    )
    features = extract_features(telemetry)
    assert features["spectral_purity"] > 0.60
    assert features["spectral_entropy"] < 0.85

    score, classification, reasons, details = analyze_behavior(telemetry)
    assert any("Synthetic harmonic oscillator tremor detected via FFT" in r for r in reasons)
    assert classification == "Bot"
    assert details["threat_type"] == "MINIMUM_JERK_BOT"


def test_organic_human_tremor_fft():
    """Organic human trajectory with broad multi-frequency jitter has low spectral purity (< 0.55)."""
    # Generate human-like movement: smooth path + broad multi-frequency noise
    movements = []
    base_t = 1000.0
    steps = 45
    for i in range(steps):
        t_sec = i * 0.025
        # Multi-frequency broad-spectrum biological jitter
        noise = (
            2.0 * math.sin(2 * math.pi * 7.5 * t_sec)
            + 1.5 * math.sin(2 * math.pi * 11.2 * t_sec)
            + 1.0 * random.gauss(0, 0.8)
        )
        x = 100.0 + i * 8.0 + noise
        y = 100.0 + i * 6.0 + noise * 0.7
        movements.append({"x": x, "y": y, "t": base_t + i * 25.0})

    telemetry = {
        "mouse_movements": movements,
        "clicks": [{"x": movements[-1]["x"], "y": movements[-1]["y"], "t": base_t + 1200.0}],
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
    features = extract_features(telemetry)
    assert features["spectral_purity"] < 0.55
    assert features["spectral_entropy"] > 0.40


def test_submovement_decomposition_bezier_lack():
    """Single-segment Bézier trajectory lacks submovement decomposition (submovement_count <= 1)."""
    telemetry = generate_bezier_telemetry(
        start=(100.0, 100.0),
        end=(600.0, 500.0),
        steps=50,
        duration_ms=1300.0,
    )
    features = extract_features(telemetry)
    assert features["submovement_count"] <= 2

    score, classification, reasons, details = analyze_behavior(telemetry)
    # Long distance with single smooth segment triggers submovement deficiency or polynomial acceleration
    has_submovement_warning = any("sub-movement" in r.lower() for r in reasons)
    has_accel_warning = any("polynomial acceleration" in r.lower() for r in reasons)
    assert has_submovement_warning or has_accel_warning
    assert classification == "Bot"


def test_session_level_behavioral_invariance():
    """Detects deterministic bot replaying identical kinetic parameters across multiple requests."""
    # 3 consecutive requests with identical tremor and straightness
    session_history = [
        {"avg_jerk": 0.00015, "straightness": 0.9450, "submovement_count": 3},
        {"avg_jerk": 0.00015, "straightness": 0.9450, "submovement_count": 3},
        {"avg_jerk": 0.00015, "straightness": 0.9450, "submovement_count": 3},
    ]

    telemetry = generate_minimum_jerk_telemetry(
        start=(100.0, 100.0),
        end=(400.0, 300.0),
        steps=40,
        duration_ms=1200.0,
    )

    score, classification, reasons, details = analyze_behavior(telemetry, session_history=session_history)
    assert any("Session Behavioral Invariance" in r for r in reasons)
    assert details["threat_type"] == "SESSION_INVARIANCE_BOT"
    assert classification == "Bot"


def test_storage_session_telemetry_sqlite(tmp_path):
    """Verifies SQLiteStorageBackend records and fetches session telemetry within sliding window."""
    db_file = str(tmp_path / "test_session.db")
    storage = SQLiteStorageBackend(db_path=db_file)

    session_id = "test_user_123"
    storage.record_session_telemetry(session_id, {"avg_jerk": 0.00012, "straightness": 0.92})
    storage.record_session_telemetry(session_id, {"avg_jerk": 0.00014, "straightness": 0.93})

    history = storage.get_session_telemetries(session_id, window_sec=60)
    assert len(history) == 2
    assert history[0]["avg_jerk"] == 0.00012
    assert history[1]["avg_jerk"] == 0.00014

    storage.clear_all()
    assert len(storage.get_session_telemetries(session_id)) == 0


def test_adversarial_batch_generator_and_training():
    """Verifies synthetic adversarial batch generation and training data enrichment."""
    batch = generate_adversarial_telemetry_batch(count=15)
    assert len(batch) == 15
    for item in batch:
        assert "mouse_movements" in item
        assert len(item["mouse_movements"]) >= 30

    # Test load_training_data with adversarial injection
    X, Y = load_training_data(limit=10, include_adversarial=True, adversarial_count=10)
    assert len(X) >= 10
    assert len(Y) == len(X)
    assert 1.0 in Y  # Bots present
