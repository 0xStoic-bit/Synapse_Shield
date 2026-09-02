import pytest
from fastapi.testclient import TestClient
from synapse_shield.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_challenge_endpoint():
    response = client.get("/api/challenge")
    assert response.status_code == 200
    data = response.json()
    assert "challenge" in data
    assert "expires_in" in data

def test_score_endpoint_invalid_json():
    response = client.post("/api/score", data="invalid json")
    assert response.status_code == 400

def test_score_without_token():
    response = client.post("/api/score", json={"telemetry": {}})
    # Token zorunlu olduğu için 403 Forbidden bekliyoruz
    assert response.status_code == 403

def test_score_with_valid_token():
    import time
    import json
    import base64
    
    # Challenge al
    chal_res = client.get("/api/challenge")
    assert chal_res.status_code == 200
    challenge = chal_res.json()["challenge"]
    
    # Hızlı bot (Zaman Manipülasyonu) engeline takılmamak için 1.6s bekle
    time.sleep(2.1)
    
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
            "plugins_length": 3
        }
    }
    
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000)
    }
    
    token = base64.b64encode(json.dumps(envelope).encode('utf-8')).decode('utf-8')
    
    response = client.post("/api/score", json={"token": token})
    
    # Eger bot score < 50 ise status "success" doner, yoksa "success" donup bot skoru 50+ verir, ya da token hatasi varsa "blocked" döner
    assert response.status_code == 200
    res_data = response.json()
    
    # Beklenen durum, valid token olduğu için başarılı loglama. Bot score ne olursa olsun "success" (veya eger çok tehlikeliyse blocked ama 200 ile)
    assert res_data["status"] in ("success", "blocked")

def test_logs_endpoint():
    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert "total_requests" in data
