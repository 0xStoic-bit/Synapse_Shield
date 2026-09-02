import pytest
import time
import json
import base64
from fastapi.testclient import TestClient
from synapse_shield.main import app

client = TestClient(app)

def create_token(challenge: str, telemetry: dict) -> str:
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000)
    }
    return base64.b64encode(json.dumps(envelope).encode('utf-8')).decode('utf-8')

def test_fast_bot_time_manipulation():
    """
    Challenge'ı aldıktan hemen sonra 1.5 saniyeden önce token gönderen bot.
    Zaman manipülasyonundan engellenmelidir.
    """
    chal_res = client.get("/api/challenge")
    challenge = chal_res.json()["challenge"]
    
    # Bekleme (sleep) olmadan direkt istek!
    token = create_token(challenge, {})
    response = client.post("/api/score", json={"token": token})
    
    # API artık 200 dönüp status: blocked json'ı yolluyor
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "blocked"
    assert "Zaman manipülasyonu" in str(res_data["reasons"])

def test_replay_attack():
    """
    Kullanılmış bir token'ın tekrar kullanılması durumunda engellenmesi.
    """
    chal_res = client.get("/api/challenge")
    challenge = chal_res.json()["challenge"]
    
    # Geçerli bir zaman aralığı (1.6sn) bekleyelim.
    time.sleep(2.1)
    
    token = create_token(challenge, {"browser": {"plugins_length": 1}})
    
    # İlk istek başarılı olmalı (Token geçerli)
    res1 = client.post("/api/score", json={"token": token})
    assert res1.status_code == 200
    
    # İkinci kez AYNI token'ı atıyoruz -> Replay Attack engeli!
    res2 = client.post("/api/score", json={"token": token})
    assert res2.status_code == 200
    assert res2.json()["status"] == "blocked"
    assert "Yeniden Oynatma" in str(res2.json()["reasons"])

def test_headless_browser_detection():
    """
    Masaüstü (touch_supported=False, screen_width=1920) cihazda plugins_length=0
    ile atılan isteğin yüksek risk alması (headless) testi.
    """
    chal_res = client.get("/api/challenge")
    challenge = chal_res.json()["challenge"]
    
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
            "plugins_length": 0  # HEADLESS INDICATOR
        }
    }
    
    token = create_token(challenge, telemetry)
    response = client.post("/api/score", json={"token": token})
    
    # Endpoint bot olarak logladıktan sonra JSON döner
    assert response.status_code == 200
    res_data = response.json()
    assert "bot_score" in res_data
    assert res_data["bot_score"] >= 50.0
    assert "Missing browser plugins in desktop environment" in str(res_data["reasons"])
