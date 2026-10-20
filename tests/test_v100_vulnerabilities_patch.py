"""
Unit tests validating patches for all 7 critical vulnerabilities (A-G)
and supplementary stability/security fixes (Ek-1, Ek-2).
"""

import base64
import json
import math
import random
import time
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from synapse_shield.engine import analyze_behavior
from synapse_shield.features import extract_features
from synapse_shield.main import fetch_logs_summary, init_db
from synapse_shield.middleware import SynapseShieldMiddleware
from synapse_shield.storage import SQLiteStorageBackend
from synapse_shield.tokens import (
    generate_challenge,
    verify_and_consume_token,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    init_db()


# ============================================================================
# [AÇIK A] Brave Farbling Camouflage Bypass Prevention
# ============================================================================
def test_brave_farbling_with_ai_bot_score_not_bypassed():
    """
    A bot sending is_webgl_hooked: True or is_canvas_hooked: True must NOT be capped
    at 34.0 (Human) if its movement triggers critical bot anomalies (e.g. heuristic >= 70 or ai_score >= 50).
    """
    # Linear movement triggers 0 jerk and straightness=1.0 -> heuristic >= 70
    bot_linear_movements = [{"x": 100 + i * 10, "y": 100 + i * 10, "t": 1000 + i * 20} for i in range(30)]
    bot_telemetry = {
        "browser": {
            "is_webgl_hooked": True,
            "is_canvas_hooked": True,
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
        },
        "mouse_movements": bot_linear_movements,
        "clicks": [{"x": 400, "y": 400, "t": 1600}],
        "keystrokes": [],
    }

    score, classification, reasons, details = analyze_behavior(bot_telemetry)
    assert classification == "Bot"
    assert score > 34.0
    assert not any("capped at 34.0" in r for r in reasons)


def test_brave_farbling_legitimate_human_is_capped():
    """
    A genuine human user with Brave farbling (canvas/webgl hooked) and natural kinematic jitter
    should be correctly protected and capped at 34.0.
    """
    random.seed(42)
    human_movements = []
    t_curr = 1000
    for i in range(35):
        t_curr += random.randint(18, 32)
        human_movements.append(
            {
                "x": round(50 + i * 12 + random.gauss(0, 1.8)),
                "y": round(100 + math.sin(i / 3.0) * 18.0 + random.gauss(0, 1.8)),
                "t": t_curr,
            }
        )

    clean_brave_telemetry = {
        "browser": {
            "is_canvas_hooked": True,
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
        },
        "mouse_movements": human_movements,
        "clicks": [{"x": 400, "y": 200, "t": t_curr}],
        "keystrokes": [],
    }
    score, classification, reasons, _ = analyze_behavior(clean_brave_telemetry)
    assert score <= 34.0
    assert classification == "Human"
    assert any("capped at 34.0" in r for r in reasons)


# ============================================================================
# [AÇIK B] Time-Travel & Stale Telemetry Protection
# ============================================================================
def test_stale_telemetry_timestamp_rejected():
    """
    Telemetry with event timestamps from hours/days ago (epoch ms) must be rejected
    even if the challenge token is fresh.
    """
    ch = generate_challenge()
    stale_epoch = int((time.time() - 3600) * 1000)  # 1 hour ago
    token_envelope = {
        "challenge": ch["challenge"],
        "telemetry": {
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": stale_epoch + i * 20} for i in range(25)],
        },
    }
    token_b64 = base64.b64encode(json.dumps(token_envelope).encode()).decode()

    valid, reason, _ = verify_and_consume_token(token_b64)
    assert not valid
    assert "stale" in reason.lower() or "bayat" in reason.lower()


def test_type_error_timestamp_rejected_safely():
    """
    Non-numeric timestamp (e.g. string or object) should be safely rejected without crashing.
    """
    ch = generate_challenge()
    token_envelope = {
        "challenge": ch["challenge"],
        "telemetry": {
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100, "y": 100, "t": "not_a_number"}],
        },
    }
    token_b64 = base64.b64encode(json.dumps(token_envelope).encode()).decode()

    valid, reason, _ = verify_and_consume_token(token_b64)
    assert not valid
    assert "typeerror" in reason.lower() or "zaman damgası" in reason.lower()


# ============================================================================
# [AÇIK C] Zero-Event Empty Telemetry Bypass Prevention
# ============================================================================
def test_zero_event_empty_telemetry_penalized():
    """
    Telemetry with completely empty user events (no mouse, touch, clicks, scrolls, keys)
    must receive +60 risk penalty and be flagged as automated/headless script.
    """
    empty_telemetry = {
        "browser": {
            "webdriver": False,
            "plugins_length": 3,
            "screen_width": 1920,
            "screen_height": 1080,
            "device_memory": 8,
            "hardware_concurrency": 8,
        },
        "mouse_movements": [],
        "touches": [],
        "clicks": [],
        "scrolls": [],
        "keystrokes": [],
    }

    score, classification, reasons, details = analyze_behavior(empty_telemetry)
    assert classification == "Bot"
    assert score >= 50.0
    assert any("Zero user interaction telemetry detected" in r for r in reasons)


# ============================================================================
# [AÇIK D] Keystroke Dynamics Dwell-Time Alignment
# ============================================================================
def test_keystroke_dynamics_dwell_time_pairing():
    """
    Event-stream pairing of down and up events should accurately measure dwell times
    and keep key_count equal to the number of keypresses (not doubled).
    """
    keystrokes = [
        {"key": "a", "type": "down", "t": 100},
        {"key": "a", "type": "up", "t": 180},   # dwell = 80ms
        {"key": "b", "type": "down", "t": 240},
        {"key": "b", "type": "up", "t": 310},   # dwell = 70ms
        {"key": "c", "type": "down", "t": 380},
        {"key": "c", "type": "up", "t": 460},   # dwell = 80ms
    ]

    telemetry = {"keystrokes": keystrokes}
    feats = extract_features(telemetry)

    assert feats["key_count"] == 3  # not 6!
    assert feats["avg_dwell_time"] > 0
    # Average dwell should be around (80 + 70 + 80) / 3 = 76.66ms
    assert 70.0 <= feats["avg_dwell_time"] <= 85.0


# ============================================================================
# [AÇIK E] Multi-Worker SQLite Storage Persistence
# ============================================================================
def test_sqlite_storage_multi_worker_shared_state(tmp_path):
    """
    Separate SQLiteStorageBackend instances pointing to the same DB file must share
    consumed nonces and banned IPs immediately via write-through.
    """
    db_file = tmp_path / "shared_synapse.db"
    worker1 = SQLiteStorageBackend(db_path=str(db_file))
    worker2 = SQLiteStorageBackend(db_path=str(db_file))

    nonce = "shared-worker-test-nonce-123"
    # Worker 1 consumes the nonce
    assert worker1.consume_nonce(nonce, ttl_sec=60)
    # Worker 2 attempts to consume the same nonce -> rejected (Replay detected across workers)
    assert not worker2.consume_nonce(nonce, ttl_sec=60)

    # Worker 1 bans an IP
    worker1.ban_ip("192.168.1.99", duration_sec=60)

    # Worker 2 should see the IP banned immediately
    assert worker2.is_ip_banned("192.168.1.99")


# ============================================================================
# [AÇIK F] Middleware Poisson Flood Tracking & Request Counting
# ============================================================================
def test_middleware_request_counting_and_poisson_flood(tmp_path):
    """
    Rapid requests from the same IP must increment request count and trigger Poisson anomaly.
    """
    db_file = tmp_path / "storage_flood.db"
    storage = SQLiteStorageBackend(db_path=str(db_file))

    test_ip = "10.0.0.88"
    for _ in range(12):
        count = storage.record_and_get_request_count(test_ip, window_sec=10)

    assert count >= 12

    # High request rate (>10 req in 10s) generates high Poisson score
    telemetry = {
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
        "mouse_movements": [{"x": 100, "y": 100, "t": 100}],
    }
    score, cls, reasons, _ = analyze_behavior(telemetry, recent_request_count=count)
    assert any("Poisson" in r and "anomaly" in r.lower() for r in reasons)


# ============================================================================
# [AÇIK G] Non-JSON Multipart / Form-Data Body Support
# ============================================================================
def test_middleware_allows_non_json_multipart_with_header_token():
    """
    A protected POST request with multipart/form-data or application/x-www-form-urlencoded
    must NOT fail with 400 'Invalid JSON payload' when X-Synapse-Token header is provided.
    """
    app = FastAPI()
    app.add_middleware(SynapseShieldMiddleware, protected_paths=["/upload"], max_risk_score=50.0)

    @app.post("/upload")
    async def upload_file(request: Request):
        body = await request.body()
        return PlainTextResponse(f"RECEIVED_{len(body)}")

    client = TestClient(app)

    # 1. Without token -> 403 Missing token
    res1 = client.post("/upload", content=b"--boundary\r\nContent-Disposition: form-data\r\n\r\nhello\r\n--boundary--",
                       headers={"content-type": "multipart/form-data; boundary=boundary"})
    assert res1.status_code == 403
    assert "Missing token" in res1.json().get("error", "")

    # 2. With valid human token in X-Synapse-Token header and form-urlencoded body
    random.seed(42)
    human_movements = []
    t_curr = 1000
    for i in range(35):
        t_curr += random.randint(18, 32)
        human_movements.append(
            {
                "x": round(50 + i * 12 + random.gauss(0, 1.8)),
                "y": round(100 + math.sin(i / 3.0) * 18.0 + random.gauss(0, 1.8)),
                "t": t_curr,
            }
        )

    ch = generate_challenge()
    tok_envelope = {
        "challenge": ch["challenge"],
        "telemetry": {
            "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": human_movements,
            "clicks": [{"x": 100, "y": 100, "t": t_curr}],
        },
    }
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()

    raw_body = b"field1=value1&field2=value2"
    res2 = client.post(
        "/upload",
        content=raw_body,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-synapse-token": tok_b64,
        },
    )
    assert res2.status_code == 200
    assert f"RECEIVED_{len(raw_body)}" in res2.text


# ============================================================================
# [EK-1] Token Size Limit Cap (64 KB)
# ============================================================================
def test_oversized_token_rejected_immediately():
    """
    Tokens exceeding 64 KB (65,536 chars) must be rejected immediately to prevent DoS.
    """
    huge_token = "A" * 70_000
    valid, reason, _ = verify_and_consume_token(huge_token)
    assert not valid
    assert "payload too large" in reason.lower() or "geçersiz token boyutu" in reason.lower()


# ============================================================================
# [EK-2] WebSocket Status Summary Safe Fetch
# ============================================================================
def test_fetch_logs_summary_callable_without_request():
    """
    fetch_logs_summary should be directly callable by background WebSocket threads
    without raising TypeError: missing 1 required positional argument: 'request'.
    """
    result = fetch_logs_summary(limit=5)
    assert isinstance(result, dict)
    assert "logs" in result
    assert "total_requests" in result
    assert "bot_requests" in result


# ============================================================================
# [EK-3] 3, 4, 5 Point Straight Line Bot Detection (engine.py mouse_points >= 3)
# ============================================================================
def test_three_to_five_point_straight_line_bot_detected():
    """
    Ensure straight-line trajectories with 3, 4, or 5 points (ruler straight, distance > 30px)
    are accurately identified as Bot rather than Human (score >= 50.0).
    """
    for pt_count in [3, 4, 5]:
        points = [{"x": 100 + i * 50, "y": 100, "t": 1000 + i * 50} for i in range(pt_count)]
        telemetry = {
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": points,
            "clicks": [{"x": points[-1]["x"], "y": points[-1]["y"], "t": points[-1]["t"] + 10, "button": 0}],
            "keys": [],
        }
        score, classification, reasons, _ = analyze_behavior(telemetry)
        assert classification == "Bot", f"Failed for {pt_count} points straight line: got {classification} with score {score}"
        assert score >= 50.0


# ============================================================================
# [EK-4] 1-2 Point Desktop Click Instantaneous Teleportation Macro Bot
# ============================================================================
def test_teleport_click_macro_bot_detected():
    """
    Ensure that 1 or 2 isolated mouse coordinates followed by a click/key interaction
    on a desktop environment are flagged as an instantaneous cursor teleportation macro bot.
    """
    for pt_count in [1, 2]:
        points = [{"x": 200, "y": 200, "t": 1000 + i * 10} for i in range(pt_count)]
        telemetry = {
            "browser": {"webdriver": False, "touch_supported": False, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": points,
            "clicks": [{"x": 200, "y": 200, "t": 1050, "button": 0}],
            "keys": [],
        }
        score, classification, reasons, _ = analyze_behavior(telemetry)
        assert classification == "Bot", f"Failed for teleport {pt_count} points: got {classification} with score {score}"
        assert any("Instantaneous cursor teleportation" in r for r in reasons)

