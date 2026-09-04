"""
Synapse Shield - Advanced Adversarial Benchmark & Stress Testing Suite
Simulates state-of-the-art biomechanical kinematics against http://127.0.0.1:8000.
Strictly designed for local defensive validation.
"""

import time
import math
import random
import json
import base64
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
CHALLENGE_URL = f"{BASE_URL}/api/challenge"
SCORE_URL = f"{BASE_URL}/api/score"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def fetch_challenge() -> str:
    """Sunucudan kriptografik HMAC-SHA256 imzalı tek kullanımlık challenge alır."""
    req = urllib.request.Request(CHALLENGE_URL)
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data["challenge"]

def clear_api():
    """Test öncesi API IP Ban temizliği."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/clear", method="POST")
        urllib.request.urlopen(req, timeout=5)
    except:
        pass

def minimum_jerk_trajectory(start: tuple, end: tuple, duration_ms: int = 1400, steps: int = 50):
    """
    Flash & Hogan (1985) Minimum Jerk Modeli.
    İnsan beyninin motor korteksindeki 5. derece balistik hızlanma ve yavaşlama polinomu:
    x(tau) = x0 + (x1 - x0) * (10*tau^3 - 15*tau^4 + 6*tau^5)
    """
    x0, y0 = start
    x1, y1 = end
    t_start = int(time.time() * 1000)
    movements = []
    
    for i in range(steps):
        tau = i / float(steps - 1)
        # Minimum Jerk 5. derece polinomu
        poly = 10 * (tau ** 3) - 15 * (tau ** 4) + 6 * (tau ** 5)
        
        # Submovement ve mikro-düzeltme (Son %25'lik dilimde hedefi hizalama)
        submovement = 0.0
        if tau > 0.70:
            submovement = math.sin((tau - 0.70) * math.pi * 3.33) * 1.5
            
        x = x0 + (x1 - x0) * poly + submovement
        y = y0 + (y1 - y0) * poly + submovement
        
        # İnsan nöromüsküler 8-12 Hz titreşimi (amplitüd < 0.6px)
        t_sec = (duration_ms * tau) / 1000.0
        tremor_x = 0.4 * math.sin(2 * math.pi * 9.5 * t_sec)
        tremor_y = 0.4 * math.cos(2 * math.pi * 10.2 * t_sec)
        
        timestamp = t_start + int(duration_ms * tau)
        movements.append({
            "x": round(x + tremor_x, 2),
            "y": round(y + tremor_y, 2),
            "t": timestamp
        })
        
    return movements

def generate_adversarial_payload(challenge: str) -> dict:
    """
    Fitts Kanunu, Uzamsal Tutarlılık ve Doğru Zamanlama Sırasını
    sağlayan gelişmiş sentetik insan telemetrisi üretir.
    """
    # 1. Başlangıç ve Hedef Buton Koordinatları
    start_pos = (random.randint(150, 300), random.randint(200, 400))
    button_target = (random.randint(550, 750), random.randint(250, 350))
    
    # 2. Minimum Jerk Hareketi (1.6 saniyelik doğal hareket süresi)
    movements = minimum_jerk_trajectory(start_pos, button_target, duration_ms=1600, steps=55)
    last_point = movements[-1]
    
    # 3. Uzamsal Tutarlılık (Spatial Coherence): 
    # Tıklama, farenin durduğu koordinatın maksimum 1-2 piksel çevresinde gerçekleşir
    click_time = last_point["t"] + random.randint(25, 45) # Tıklama butonda durduktan sonra olur
    clicks = [{
        "x": round(last_point["x"] + random.uniform(-1.0, 1.0), 2),
        "y": round(last_point["y"] + random.uniform(-1.0, 1.0), 2),
        "t": click_time
    }]
    
    # 4. Tarayıcı Bütünlüğü (V8 Prototip Sahtekarlığı Yok)
    telemetry = {
        "mouse_movements": movements,
        "clicks": clicks,
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 5,
            "is_plugin_array_fake": False,      # Prototype sahteleme yok
            "has_webdriver_own_prop": False,    # Prototip kancası yok
            "is_webgl_hooked": False,           # WebGL orijinal
            "is_canvas_hooked": False           # Canvas orijinal
        }
    }
    
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000)
    }
    token = base64.b64encode(json.dumps(envelope).encode()).decode()
    return {"token": token}

def run_test():
    print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════╗{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}║   🔬 SYNAPSE SHIELD — İLERİ SEVİYE BENCHMARK TESTİ (v0.6.4)   ║{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════════╝{Colors.END}\n")

    clear_api()

    # 1. Challenge Al
    print("[1/3] Sunucudan imzalı challenge alınıyor...")
    ch = fetch_challenge()
    print(f"  → Challenge: {Colors.YELLOW}{ch[:35]}...{Colors.END}")

    # 2. İnsan Düşünme & Hareket Süresi (Dwell Time Kalkanı: >1.5 sn)
    wait_sec = random.uniform(1.8, 2.4)
    print(f"[2/3] Fizyolojik hareket ve düşünme süresi bekleniyor ({wait_sec:.2f}s)...")
    time.sleep(wait_sec)

    # 3. Minimum Jerk Telemetrisini Paketle ve Gönder
    payload = generate_adversarial_payload(ch)
    print("[3/3] Biyomekanik paket /api/score uç noktasına iletiliyor...")
    
    req = urllib.request.Request(
        SCORE_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            t1 = time.perf_counter()
            result = json.loads(resp.read().decode())
            latency_ms = (t1 - t0) * 1000
            
            score = result.get("bot_score", 0.0)
            classification = result.get("classification", "Unknown")
            reasons = result.get("reasons", [])
            
            print(f"\n{Colors.BOLD}--- TEST SONUCU ---{Colors.END}")
            print(f"Sunucu Yanıt Gecikmesi: {Colors.YELLOW}{latency_ms:.2f} ms{Colors.END}")
            print(f"Karar:                  {Colors.GREEN if classification == 'Human' else Colors.RED}{classification}{Colors.END}")
            print(f"Risk Skoru:             {score:.1f}%")
            print("Tetiklenen Güvenlik Nedenleri:")
            for r in reasons:
                print(f"  • {r}")
                
    except urllib.error.HTTPError as e:
        print(f"{Colors.RED}❌ HTTP {e.code} ile engellendi.{Colors.END}")

if __name__ == "__main__":
    run_test()
