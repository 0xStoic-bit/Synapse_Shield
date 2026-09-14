import base64
import hashlib
import json
import time
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
from synapse_shield.main import app
from synapse_shield.engine import analyze_behavior

client = TestClient(app)


def test_sdk_static_serving():
    """Verify that the SDK static endpoint serves the updated v0.7.4 JavaScript SDK."""
    response = client.get("/static/synapse-sdk.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "")
    content = response.text
    assert "Synapse Shield SDK v0.7.4" in content
    assert "safeBtoa" in content
    assert "solvePoW" in content
    assert "touchstart" in content
    assert "touchmove" in content
    assert "touchend" in content
    assert "checkLeadingZeroHex" in content
    assert "SynapseShield" in content
    assert "Object.defineProperty" in content


def test_utf8_token_handling():
    """Verify that non-Latin1 / UTF-8 Unicode characters are handled correctly by the scoring endpoint."""
    chal_res = client.get("/api/challenge")
    assert chal_res.status_code == 200
    challenge = chal_res.json()["challenge"]

    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
            "languages": "tr-TR,tr,en-US,en",
            "user_comment": "İstanbul Şişli İstasyon / Türkçe karakter testi: çğıöşü ÇĞİÖŞÜ",
        },
    }

    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }

    raw_json = json.dumps(envelope, ensure_ascii=False)
    token_str = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")

    res = client.post("/api/score", json={"token": token_str})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["classification"] == "Human"
    assert data["threat_type"] == "CLEAN_HUMAN"


def test_pow_gray_area_and_fresh_retry():
    """
    Test the complete PoW workflow:
    1. Initial request lands in gray area (35.0 <= score <= 65.0) -> returns 'challenge_required'.
    2. Client solves PoW.
    3. Client fetches a fresh challenge (v0.7.2 SDK fix) to prevent Replay Attack.
    4. Client resubmits with fresh token and PoW credentials -> succeeds with reduced risk.
    """
    # 1. First challenge
    chal1_res = client.get("/api/challenge")
    challenge1 = chal1_res.json()["challenge"]

    # Telemetry designed for gray area: is_webgl_hooked adds +40.0 risk
    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
            "is_webgl_hooked": True,
            "is_canvas_hooked": False,
        },
    }

    envelope1 = {
        "challenge": challenge1,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }
    token1 = base64.b64encode(json.dumps(envelope1).encode("utf-8")).decode("utf-8")

    # Initial submission -> challenge_required
    res1 = client.post("/api/score", json={"token": token1})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "challenge_required"
    assert "pow_salt" in data1
    assert data1["pow_difficulty"] == 4

    pow_salt = data1["pow_salt"]

    # 2. Solve PoW
    nonce = 0
    found_nonce = None
    while nonce < 100000:
        hash_val = hashlib.sha256((pow_salt + str(nonce)).encode()).hexdigest()
        if hash_val.startswith("0000"):
            found_nonce = str(nonce)
            break
        nonce += 1

    assert found_nonce is not None, "PoW should be solved within bounds"

    # 3. Fetch a fresh challenge (SDK v0.7.2 behavior)
    chal2_res = client.get("/api/challenge")
    challenge2 = chal2_res.json()["challenge"]

    envelope2 = {
        "challenge": challenge2,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }
    token2 = base64.b64encode(json.dumps(envelope2).encode("utf-8")).decode("utf-8")

    # 4. Retry with fresh challenge token and valid PoW
    res2 = client.post(
        "/api/score",
        json={
            "token": token2,
            "pow_nonce": found_nonce,
            "pow_salt": pow_salt,
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "success"
    assert data2["classification"] == "Human"
    assert data2["bot_score"] == 20.0  # 40.0 - 20.0 = 20.0
    assert any("PoW Challenge successfully solved" in r for r in data2["reasons"])


def test_pow_replay_attack_rejection_on_reused_token():
    """Verify that reusing the consumed challenge token during PoW retry is rejected as REPLAY_ATTACK."""
    chal_res = client.get("/api/challenge")
    challenge = chal_res.json()["challenge"]

    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
            "is_webgl_hooked": True,
        },
    }

    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }
    token = base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    res1 = client.post("/api/score", json={"token": token})
    assert res1.json()["status"] == "challenge_required"
    pow_salt = res1.json()["pow_salt"]

    # Reusing the SAME consumed token (reproducing the pre-v0.7.2 bug)
    res_buggy_retry = client.post(
        "/api/score",
        json={
            "token": token,
            "pow_nonce": "12345",
            "pow_salt": pow_salt,
        },
    )
    assert res_buggy_retry.status_code == 200
    data_buggy = res_buggy_retry.json()
    assert data_buggy["status"] == "blocked"
    assert data_buggy["threat_type"] == "REPLAY_ATTACK"
    assert data_buggy["bot_score"] == 100.0


def test_mobile_touch_telemetry_support():
    """Verify that mobile telemetry with touch events avoids missing mouse and plugin false positives."""
    # When a mobile user taps the screen, SDK captures touchstart and touchmove points into mouseMovements
    telemetry = {
        "mouse_movements": [
            {"x": 180, "y": 320, "t": 1000},
            {"x": 181, "y": 321, "t": 1025},
        ],
        "clicks": [
            {"x": 181, "y": 321, "t": 1030}
        ],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 390,
            "screen_height": 844,
            "touch_supported": True,
            "plugins_length": 0,  # Mobile browsers usually have 0 plugins
            "languages": "en-US,en",
        },
    }

    score, classification, reasons, details = analyze_behavior(telemetry)
    assert classification == "Human"
    assert score < 30.0
    assert not any("Missing browser plugins in desktop environment" in r for r in reasons)
    assert not any("Interactive events occurred without mouse movement telemetry" in r for r in reasons)


def test_dynamic_pow_difficulty_logic():
    """Test dynamic difficulty validator with various leading zero targets."""
    def check_leading_zero_hex(hash_bytes: bytes, difficulty: int) -> bool:
        full_bytes = difficulty // 2
        for i in range(full_bytes):
            if hash_bytes[i] != 0:
                return False
        if difficulty % 2 != 0:
            if (hash_bytes[full_bytes] >> 4) != 0:
                return False
        return True

    # 4 zeros = 2 zero bytes (0x00, 0x00)
    assert check_leading_zero_hex(bytes([0x00, 0x00, 0x12, 0x34]), 4) is True
    assert check_leading_zero_hex(bytes([0x00, 0x01, 0x12, 0x34]), 4) is False

    # 3 zeros = 1 zero byte + upper nibble 0 (0x00, 0x0F)
    assert check_leading_zero_hex(bytes([0x00, 0x05, 0x12, 0x34]), 3) is True
    assert check_leading_zero_hex(bytes([0x00, 0x15, 0x12, 0x34]), 3) is False

    # 5 zeros = 2 zero bytes + upper nibble 0 (0x00, 0x00, 0x0A)
    assert check_leading_zero_hex(bytes([0x00, 0x00, 0x0A, 0x34]), 5) is True
    assert check_leading_zero_hex(bytes([0x00, 0x00, 0xFA, 0x34]), 5) is False
