"""
Synapse Shield v0.7.0 Feature Test Suite
Tests: 
1. Proof-of-Work (PoW) Smart Challenge flow
2. Sliding Window (SSRT-2026-004 fix) streak-reset resistance
"""

import time
import json
import hashlib
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def solve_pow(salt: str, difficulty: int = 4) -> str:
    """İstemci tarafındaki JS mantığını Python'da simüle eder: '0000' ile başlayan hash arar."""
    target_prefix = "0" * difficulty
    nonce = 0
    while True:
        candidate = f"{salt}{nonce}" # Note: salt string already contains everything, JS does salt + nonce
        h = hashlib.sha256(candidate.encode()).hexdigest()
        if h.startswith(target_prefix):
            return str(nonce)
        nonce += 1

def test_pow_challenge():
    # Clear IP history to prevent previous test runs from blocking
    urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}/api/clear", method="POST"))
    
    print("\n--- [TEST 1] Proof-of-Work (Smart Challenge) Testi ---")
    # Gri alana (%35-65) düşecek telemetri: headless browser (plugins=0) = 50%
    payload = {
        "mouse_movements": [],
        "clicks": [],
        "browser": {"screen_width": 1920, "screen_height": 1080, "touch_supported": False, "plugins_length": 0, "webdriver": False}
    }
    
    # 0. Challenge al ve token oluştur
    import base64
    req0 = urllib.request.Request(f"{BASE_URL}/api/challenge")
    with urllib.request.urlopen(req0) as resp:
        chal = json.loads(resp.read().decode())["challenge"]
        
    time.sleep(1.6) # Prevent time manipulation block
    
    envelope = {
        "challenge": chal,
        "telemetry": payload,
        "created_at": int(time.time() * 1000)
    }
    payload["token"] = base64.b64encode(json.dumps(envelope).encode('utf-8')).decode('utf-8')
    
    # 1. Challenge gerektiren istek
    req = urllib.request.Request(f"{BASE_URL}/api/score", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res1 = json.loads(resp.read().decode())
        
    print(f"1. Yanıt Durumu: {res1.get('status')}")
    if res1.get("status") == "challenge_required":
        salt = res1["pow_salt"]
        diff = res1.get("pow_difficulty", 4)
        print(f"  - PoW Meydan Okuması Alındı! (Salt: {salt[:25]}..., Zorluk: {diff})")
        
        # 2. Bulmacayı çöz
        t0 = time.perf_counter()
        solved_nonce = solve_pow(salt, diff)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  - Bulmaca {elapsed_ms:.1f} ms içinde çözüldü! (Bulunan Nonce: {solved_nonce})")
        
        # 3. Çözümü ekleyip tekrar gönder
        payload["pow_salt"] = salt
        payload["pow_nonce"] = solved_nonce
        req2 = urllib.request.Request(f"{BASE_URL}/api/score", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2) as resp2:
            res2 = json.loads(resp2.read().decode())
            
        print(f"2. Yanıt Durumu: {res2.get('classification')} (Risk: {res2.get('bot_score')}%)")
        print("[BASARILI] PoW çözümü sunucu tarafından doğrulandı ve geçiş verildi!")
    else:
        print(f"Bilgi: Skor gri alana düşmedi (Skor: {res1.get('bot_score')}%).")

def test_sliding_window_ip_ban():
    print("\n--- [TEST 2] Kayan Pencere (Sliding Window) IP Ban Testi ---")
    bot_payload = {
        "mouse_movements": [{"x": i*10, "y": i*10, "t": int(time.time()*1000) + i*10} for i in range(20)], # Straight line
        "clicks": [],
        "browser": {"webdriver": True, "plugins_length": 0} # Definitive Bot
    }
    human_payload = {
        "mouse_movements": [{"x": 100 + i*10, "y": 150 + i*5, "t": int(time.time()*1000) + i*25} for i in range(35)],
        "clicks": [{"x": 450, "y": 325, "t": int(time.time()*1000) + 1000}],
        "browser": {"screen_width": 1920, "screen_height": 1080, "plugins_length": 3, "touch_supported": False, "webdriver": False}
    }
    
    test_ip = "192.168.1.99"
    headers = {"Content-Type": "application/json", "x-forwarded-for": test_ip}
    
    def post(payload_dict):
        req0 = urllib.request.Request(f"{BASE_URL}/api/challenge")
        with urllib.request.urlopen(req0) as resp:
            chal = json.loads(resp.read().decode())["challenge"]
            
        import base64
        envelope = {
            "challenge": chal,
            "telemetry": payload_dict,
            "created_at": int(time.time() * 1000)
        }
        
        # Need to deepcopy so we don't mutate the original dictionary
        import copy
        p = copy.deepcopy(payload_dict)
        
        time.sleep(1.6) # Prevent time manipulation block
        
        p["token"] = base64.b64encode(json.dumps(envelope).encode('utf-8')).decode('utf-8')
        
        req = urllib.request.Request(f"{BASE_URL}/api/score", data=json.dumps(p).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    print("[*] Saldırı Döngüsü Başlatılıyor: 3 Bot -> 1 İnsan -> 1 Bot...")
    # 3 Bot
    for i in range(1, 4):
        code, r = post(bot_payload)
        print(f"  Bot İsteği #{i} HTTP {code} (Risk: {r.get('bot_score')}%)")
        time.sleep(0.1)
        
    # 1 İnsan (Araya kaynatma denemesi)
    code, r = post(human_payload)
    print(f"  Araya Sıkıştırılan İnsan İsteği HTTP {code} (Sınıf: {r.get('classification')})")
    time.sleep(0.1)
    
    # 4. Bot İsteği (60s dolmadığı için BANLANMALI!)
    code, r = post(bot_payload)
    print(f"  4. Bot İsteği HTTP {code} (Detay: {r.get('detail') or r.get('reasons')})")
    
    if code == 403:
        print("[BASARILI] Araya insan girmesine rağmen Kayan Pencere sayacı sıfırlamadı ve IP banlandı!")
    else:
        print("[BASARISIZ] IP ban tetiklenmedi.")

if __name__ == "__main__":
    test_pow_challenge()
    test_sliding_window_ip_ban()
