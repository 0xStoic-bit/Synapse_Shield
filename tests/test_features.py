import pytest
import math
from synapse_shield.features import extract_features

def test_empty_telemetry():
    features = extract_features({})
    assert features["mouse_points"] == 0
    assert features["click_count"] == 0
    assert features["webdriver"] == False
    assert features["straightness"] == 1.0

def test_missing_data_payloads():
    telemetry = {"browser": {}, "mouse_movements": []}
    features = extract_features(telemetry)
    assert features["screen_valid"] == False
    assert features["total_distance"] == 0.0

def test_nan_infinity_coordinates():
    telemetry = {
        "mouse_movements": [
            {"x": float('nan'), "y": 10, "t": 100},
            {"x": float('inf'), "y": float('-inf'), "t": 120}
        ]
    }
    features = extract_features(telemetry)
    # The math operations shouldn't crash completely, should degrade gracefully.
    assert "total_distance" in features

def test_zero_division_time_delta():
    # Delta t = 0
    telemetry = {
        "mouse_movements": [
            {"x": 10, "y": 10, "t": 100},
            {"x": 20, "y": 20, "t": 100} # Same timestamp
        ]
    }
    features = extract_features(telemetry)
    # We enforce max(0.1, t2 - t1) in our algorithm so Delta T = 0 will not crash
    assert "avg_velocity" in features
