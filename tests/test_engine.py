import pytest
import random
import math
from synapse_shield.engine import analyze_behavior, poisson_anomaly_score

def test_poisson_anomaly():
    score_low = poisson_anomaly_score(k=2, lambda_val=2.0)
    score_high = poisson_anomaly_score(k=10, lambda_val=2.0)
    assert score_low < 0.90
    assert score_high >= 0.99

def test_selenium_headless_properties():
    telemetry = {"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}}
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"
    assert "Automation tool interface" in str(reasons)

def test_straight_line_bot():
    linear_movements = [{"x": 10 + i * 20, "y": 10 + i * 10, "t": 1000 + i * 20} for i in range(25)]
    telemetry = {"mouse_movements": linear_movements}
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"
    assert score >= 50.0

def test_robotic_keyboard():
    # Çok düzenli (varyanssız) klavye vuruşları
    keystrokes = [{"t": 1000 + i * 100} for i in range(10)]
    telemetry = {"keystrokes": keystrokes}
    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Bot"

def test_human_verification():
    human_movements = []
    t_h = 1000
    for i in range(35):
        t_h += random.randint(18, 32)
        human_movements.append({"x": round(50 + i*12 + random.gauss(0, 1.8)), "y": round(100 + math.sin(i/3.0)*18.0 + random.gauss(0, 1.8)), "t": t_h})
        
    human_payload = {
        "mouse_movements": human_movements,
        "clicks": [{"x": 400, "y": 200, "t": t_h}],
        "keystrokes": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080
        }
    }
    score, classification, reasons, details = analyze_behavior(human_payload)
    assert classification == "Human"
    assert score <= 50.0

def test_anti_stealth_hard_block():
    payload = {
        "mouse_movements": [],
        "browser": {
            "webdriver": False,
            "is_plugin_array_fake": True,
            "has_webdriver_own_prop": False
        }
    }
    score, classification, reasons, details = analyze_behavior(payload)
    assert classification == "Bot"
    assert score >= 100.0
    assert any("Stealth browser tamper detected" in r for r in reasons)

def test_anti_stealth_privacy_extension():
    # Privacy extension (CanvasBlocker) ama temiz insan telemetrisi
    payload = {
        "mouse_movements": [{"x": 10 + i, "y": 20 + i, "t": 1000 + i*30} for i in range(20)],
        "browser": {
            "webdriver": False,
            "is_plugin_array_fake": False,
            "is_webgl_hooked": True
        }
    }
    score, classification, reasons, details = analyze_behavior(payload)
    # Temiz telemetri olmadığı için heuristics bunu bot yapabilir, ama 40 puan eklendiğini teyit edelim.
    assert score >= 40.0
    assert any("Browser fingerprinting hook detected" in r for r in reasons)
