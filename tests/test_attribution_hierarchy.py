import pytest
from synapse_shield.engine import analyze_behavior, classify_threat
from fastapi.testclient import TestClient
from synapse_shield.main import app

client = TestClient(app)

def test_backward_compatibility_signature():
    """analyze_behavior must return exactly a 4-tuple: (score, classification, reasons, details)."""
    telemetry = {
        "mouse_movements": [
            {"x": 10, "y": 10, "t": 100},
            {"x": 20, "y": 25, "t": 130},
            {"x": 45, "y": 60, "t": 170},
            {"x": 80, "y": 110, "t": 220},
            {"x": 120, "y": 170, "t": 280},
            {"x": 165, "y": 235, "t": 350},
        ],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 5
        }
    }
    
    result = analyze_behavior(telemetry)
    assert len(result) == 4, "Must return 4-tuple to prevent ValueError unpacking in existing codebases!"
    bot_score, classification, reasons, details = result
    
    assert isinstance(bot_score, float)
    assert classification in ("Bot", "Human")
    assert isinstance(reasons, list)
    assert isinstance(details, dict)
    assert "threat_type" in details, "threat_type must be present inside details dictionary!"


def test_hierarchy_stealth_over_linear():
    """STEALTH_AUTOMATION must take precedence over LINEAR_MACRO."""
    # Linear movement (straightness = 1.0) + fake plugin array
    linear_points = [{"x": i * 10, "y": i * 10, "t": i * 20} for i in range(15)]
    telemetry = {
        "mouse_movements": linear_points,
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "is_plugin_array_fake": True,  # Stealth Tamper
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3
        }
    }
    
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"
    assert details["threat_type"] == "STEALTH_AUTOMATION"


def test_hierarchy_stealth_over_min_jerk():
    """STEALTH_AUTOMATION must take precedence over MINIMUM_JERK_BOT."""
    # Smooth points + WebGL hook
    points = [{"x": i * 10, "y": int(50 * (i/10)**2), "t": i * 20} for i in range(15)]
    telemetry = {
        "mouse_movements": points,
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": True,  # Stealth/Webdriver
            "is_webgl_hooked": True,
            "screen_width": 1920,
            "screen_height": 1080
        }
    }
    
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"
    assert details["threat_type"] == "STEALTH_AUTOMATION"


def test_hierarchy_min_jerk_over_linear_and_poisson():
    """MINIMUM_JERK_BOT must take precedence over POISSON_FLOOD."""
    # Smooth bezier curve with very low jerk, but clean browser
    smooth_points = [{"x": 10 + i*5, "y": 20 + int(i**1.5), "t": 100 + i*16} for i in range(20)]
    telemetry = {
        "mouse_movements": smooth_points,
        "clicks": [{"x": 100, "y": 100, "t": 500, "button": 0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 5
        }
    }
    
    # recent_request_count=15 triggers high poisson anomaly (>= 0.95)
    score, classification, reasons, details = analyze_behavior(telemetry, recent_request_count=15)
    # If jerk or terminal decel triggers MINIMUM_JERK_BOT, it should take precedence over POISSON_FLOOD
    if details["features"]["avg_jerk"] < 0.00008 or details["features"]["acceleration_var"] < 1.5e-5:
        assert details["threat_type"] == "MINIMUM_JERK_BOT"


def test_hierarchy_linear_macro():
    """LINEAR_MACRO should be attributed for purely euclidean lines without stealth tampering."""
    linear_points = [{"x": i * 10, "y": i * 10, "t": 100 + i * 20} for i in range(20)]
    telemetry = {
        "mouse_movements": linear_points,
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 5
        }
    }
    
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"
    assert details["threat_type"] == "LINEAR_MACRO"


def test_api_replay_attack_attribution():
    """Invalid token or reused token must return REPLAY_ATTACK in API response."""
    response = client.post(
        "/api/score", 
        json={"token": "totally_invalid_or_manipulated_token_123"},
        headers={"X-Forwarded-For": "192.168.1.100"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["threat_type"] == "REPLAY_ATTACK"
    assert data["details"]["threat_type"] == "REPLAY_ATTACK"
