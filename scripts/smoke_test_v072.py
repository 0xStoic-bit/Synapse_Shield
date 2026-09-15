"""
Synapse Shield v0.7.2 Smoke Test Suite
Validates JavaScript SDK v0.7.2 serving, UTF-8 Base64 token decodes,
Gray Area Proof-of-Work (PoW) fresh-challenge retry flow,
Replay Attack detection on reused tokens, and Mobile Touch Telemetry.
"""

import base64
import hashlib
import json
import time
import sys
import os

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
os.environ["SYNAPSE_MIN_ELAPSED_MS"] = "0"
os.environ["SYNAPSE_ADMIN_SECRET"] = "smoke-secret"

from fastapi.testclient import TestClient
from synapse_shield.main import app

client = TestClient(app)

def run_smoke_tests():
    print("=" * 70)
    print("        SYNAPSE SHIELD v0.7.2 SMOKE TEST SUITE")
    print("=" * 70)
    
    # 0. Clear previous IP state
    client.post("/api/clear", headers={"X-Admin-Secret": "smoke-secret"})

    # Test 1: Static SDK Serving
    print("\n[TEST 1] Static SDK Serving (/static/synapse-sdk.js)...")
    res_sdk = client.get("/static/synapse-sdk.js")
    assert res_sdk.status_code == 200, f"SDK fetch failed: {res_sdk.status_code}"
    sdk_code = res_sdk.text
    assert "Synapse Shield SDK" in sdk_code, "SDK header missing in SDK"
    assert "safeBtoa" in sdk_code, "safeBtoa missing in SDK"
    assert "getCleanFunctionToString" in sdk_code, "iframe prototype unhooker missing in SDK"
    assert "touchstart" in sdk_code, "touchstart listener missing in SDK"
    assert "touchmove" in sdk_code, "touchmove listener missing in SDK"
    assert "touchend" in sdk_code, "touchend listener missing in SDK"
    assert "checkLeadingZeroHex" in sdk_code, "Dynamic PoW validator missing in SDK"
    assert "Object.defineProperty" in sdk_code, "SDK immutability freeze missing in SDK"
    print("  -> PASS: SDK v0.7.2 served with all anti-tamper & mobile features.")

    # Test 2: Challenge Acquisition
    print("\n[TEST 2] Challenge Generation (/api/challenge)...")
    res_chal = client.get("/api/challenge")
    assert res_chal.status_code == 200, f"Challenge fetch failed: {res_chal.status_code}"
    chal_data = res_chal.json()
    assert "challenge" in chal_data and "expires_in" in chal_data
    challenge = chal_data["challenge"]
    parts = challenge.split(".")
    assert len(parts) == 3, "Challenge format must be nonce.timestamp.signature"
    print(f"  -> PASS: Challenge acquired: {parts[0][:8]}... (Nonce), {parts[1]} (Timestamp)")

    # Test 3: UTF-8 Unicode Token Decoding
    print("\n[TEST 3] UTF-8 Base64 Token Handling (safeBtoa compatibility)...")
    utf8_telemetry = {
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
            "locale_strings": "İstanbul Şişli İstasyon / Türkçe test: çğıöşü ÇĞİÖŞÜ",
        }
    }
    envelope_utf8 = {
        "challenge": challenge,
        "telemetry": utf8_telemetry,
        "created_at": int(time.time() * 1000)
    }
    raw_utf8 = json.dumps(envelope_utf8, ensure_ascii=False)
    b64_utf8 = base64.b64encode(raw_utf8.encode("utf-8")).decode("utf-8")
    
    res_utf8 = client.post("/api/score", json={"token": b64_utf8})
    assert res_utf8.status_code == 200
    utf8_resp = res_utf8.json()
    assert utf8_resp["status"] == "success"
    assert utf8_resp["classification"] == "Human"
    print(f"  -> PASS: UTF-8 token evaluated successfully (Classification: {utf8_resp['classification']}, Bot Score: {utf8_resp['bot_score']}%)")

    # Test 4: Gray Area PoW Challenge & Secure Retry Flow
    print("\n[TEST 4] Gray Area Proof-of-Work (PoW) Flow & Fresh Token Retry...")
    chal_gray = client.get("/api/challenge").json()["challenge"]
    gray_telemetry = {
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
        }
    }
    envelope_gray = {
        "challenge": chal_gray,
        "telemetry": gray_telemetry,
        "created_at": int(time.time() * 1000)
    }
    token_gray = base64.b64encode(json.dumps(envelope_gray).encode("utf-8")).decode("utf-8")
    
    res_gray1 = client.post("/api/score", json={"token": token_gray})
    assert res_gray1.status_code == 200
    data_gray1 = res_gray1.json()
    assert data_gray1["status"] == "challenge_required"
    pow_salt = data_gray1["pow_salt"]
    pow_diff = data_gray1.get("pow_difficulty", 4)
    print(f"  -> Step 1 PASS: Status is 'challenge_required', difficulty={pow_diff}, salt={pow_salt[:20]}...")

    # Solve PoW
    t0 = time.perf_counter()
    nonce = 0
    while True:
        cand = f"{pow_salt}{nonce}"
        h = hashlib.sha256(cand.encode()).hexdigest()
        if h.startswith("0000"):
            solved_nonce = str(nonce)
            break
        nonce += 1
    dur_ms = (time.perf_counter() - t0) * 1000
    print(f"  -> Step 2 PASS: Solved PoW in {dur_ms:.1f}ms (Nonce: {solved_nonce})")

    # Fetch Fresh Challenge (v0.7.2 fix)
    chal_fresh = client.get("/api/challenge").json()["challenge"]
    envelope_fresh = {
        "challenge": chal_fresh,
        "telemetry": gray_telemetry,
        "created_at": int(time.time() * 1000)
    }
    token_fresh = base64.b64encode(json.dumps(envelope_fresh).encode("utf-8")).decode("utf-8")

    # Resubmit with fresh challenge token and valid PoW
    res_pow_retry = client.post(
        "/api/score",
        json={
            "token": token_fresh,
            "pow_nonce": solved_nonce,
            "pow_salt": pow_salt
        }
    )
    assert res_pow_retry.status_code == 200
    data_pow_retry = res_pow_retry.json()
    assert data_pow_retry["status"] == "success"
    assert data_pow_retry["classification"] == "Human"
    assert data_pow_retry["bot_score"] == 20.0
    print(f"  -> Step 3 PASS: PoW accepted! Score reduced from 40.0 to {data_pow_retry['bot_score']}%, Classification: Human.")

    # Test 5: Replay Attack on Reused Token
    print("\n[TEST 5] Replay Attack Block on Consumed Token...")
    res_replay = client.post(
        "/api/score",
        json={
            "token": token_gray, # Reusing the first consumed token
            "pow_nonce": solved_nonce,
            "pow_salt": pow_salt
        }
    )
    assert res_replay.status_code == 200
    data_replay = res_replay.json()
    assert data_replay["status"] == "blocked"
    assert data_replay["threat_type"] == "REPLAY_ATTACK"
    assert data_replay["bot_score"] == 100.0
    print("  -> PASS: Reused token immediately blocked as REPLAY_ATTACK (bot_score=100.0%).")

    # Test 6: Mobile Touch Biometrics
    print("\n[TEST 6] Mobile Touchscreen Behavioral Biometrics...")
    mobile_telemetry = {
        "mouse_movements": [
            {"x": 160, "y": 300, "t": 1000},
            {"x": 161, "y": 301, "t": 1028},
        ],
        "clicks": [
            {"x": 161, "y": 301, "t": 1032}
        ],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 390,
            "screen_height": 844,
            "touch_supported": True,
            "plugins_length": 0,
            "languages": "en-US,en"
        }
    }
    chal_mob = client.get("/api/challenge").json()["challenge"]
    env_mob = {
        "challenge": chal_mob,
        "telemetry": mobile_telemetry,
        "created_at": int(time.time() * 1000)
    }
    tok_mob = base64.b64encode(json.dumps(env_mob).encode("utf-8")).decode("utf-8")
    res_mob = client.post("/api/score", json={"token": tok_mob})
    assert res_mob.status_code == 200
    data_mob = res_mob.json()
    assert data_mob["status"] == "success"
    assert data_mob["classification"] == "Human"
    assert data_mob["bot_score"] < 10.0
    print(f"  -> PASS: Mobile touch tap classified as Clean Human (Risk: {data_mob['bot_score']:.2f}%).")

    print("\n" + "=" * 70)
    print("  ALL 6 SMOKE TESTS PASSED SUCCESSFULLY! SYNAPSE SHIELD v0.7.2 IS READY.")
    print("=" * 70)

if __name__ == "__main__":
    run_smoke_tests()
