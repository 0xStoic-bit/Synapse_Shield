"""
Synapse Shield v0.7.1 - Apex Adversarial Benchmark Test Suite
Simulates state-of-the-art biomechanical kinematics, spatial coherence,
and automated PoW challenge resolution against http://127.0.0.1:8000.
Strictly designed for local defensive calibration.
"""

import time
import math
import random
import json
import base64
import hashlib
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
CHALLENGE_URL = f"{BASE_URL}/api/challenge"
SCORE_URL = f"{BASE_URL}/api/score"

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def fetch_challenge() -> str:
    req = urllib.request.Request(CHALLENGE_URL)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())["challenge"]

def solve_pow(salt: str, difficulty: int = 4) -> str:
    """Sunucudan gelen HMAC imzalı PoW bulmacasını çözer ('0000' arar)."""
    target = "0" * difficulty
    nonce = 0
    t0 = time.perf_counter()
    while True:
        cand = f"{salt}:{nonce}"
        h = hashlib.sha256(cand.encode()).hexdigest()
        if h.startswith(target):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(f"  - PoW Bulmacası {elapsed_ms:.1f}ms içinde çözüldü (Nonce: {nonce})")
            return str(nonce)
        nonce += 1

def generate_apex_trajectory(start: tuple, target: tuple, duration_ms: int = 1600, steps: int = 55):
    """
    Flash & Hogan 5. Derece Minimum Jerk Modeli + Doğal Rota Sapması (Curvature).
    """
    x0, y0 = start
    x1, y1 = target
    t_start = int(time.time() * 1000)
    movements = []

    # Doğal insan rotası kavisi (Doğrusallık indeksinin 0.985'in altında kalması için)
    mid_deviation = random.uniform(-25.0, 25.0)

    for i in range(steps):
        tau = i / float(steps - 1)
        # 5. Derece Minimum Jerk Polinomu: 10t^3 - 15t^4 + 6t^5
        poly = 10 * (tau ** 3) - 15 * (tau ** 4) + 6 * (tau ** 5)

        # Rota kavisi (Doğal insan eli düz cetvel çizmez)
        curve = math.sin(tau * math.pi) * mid_deviation

        # Sakkadik alt hareket (Son %20'lik yaklaşmada hedefi hizalama mikro-yavaşlaması)
        submovement = 0.0
        if tau > 0.75:
            sub_tau = (tau - 0.75) / 0.25
            submovement = math.sin(sub_tau * math.pi) * 1.8

        x = x0 + (x1 - x0) * poly + curve + submovement
        y = y0 + (y1 - y0) * poly + (curve * 0.5) + submovement

        # 8-12 Hz Nöromüsküler Titreme (Tremor)
        t_sec = (duration_ms * tau) / 1000.0
        tremor_x = 0.35 * math.sin(2 * math.pi * 9.8 * t_sec) + random.gauss(0, 0.15)
        tremor_y = 0.35 * math.cos(2 * math.pi * 10.5 * t_sec) + random.gauss(0, 0.15)

        movements.append({
            "x": round(x + tremor_x, 2),
            "y": round(y + tremor_y, 2),
            "t": t_start + int(duration_ms * tau)
        })

    return movements

def build_payload(challenge: str, pow_salt: str = None, pow_nonce: str = None) -> dict:
    start_pos = (random.randint(150, 300), random.randint(200, 400))
    target_button = (random.randint(550, 750), random.randint(250, 350))

    movements = generate_apex_trajectory(start_pos, target_button, duration_ms=1650, steps=60)
    last_point = movements[-1]

    # Uzamsal Tutarlılık: Tıklama, farenin durduğu koordinatla birebir aynı noktada (<=0.5px)
    click_time = last_point["t"] + random.randint(30, 45) # Tıklama durduktan sonra gerçekleşir
    clicks = [{
        "x": last_point["x"],
        "y": last_point["y"],
        "t": click_time
    }]

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
            "is_plugin_array_fake": False,
            "has_webdriver_own_prop": False,
            "is_webgl_hooked": False,
            "is_canvas_hooked": False
        }
    }

    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000)
    }

    payload = {"token": base64.b64encode(json.dumps(envelope).encode()).decode()}
    if pow_salt and pow_nonce:
        payload["pow_salt"] = pow_salt
        payload["pow_nonce"] = pow_nonce

    return payload

def run_apex_test():
    print(f"\n{C.BOLD}{C.CYAN}=============================================================={C.END}")
    print(f"{C.BOLD}{C.CYAN}    APEX ADVERSARIAL BENCHMARK TEST (v0.7.1){C.END}")
    print(f"{C.BOLD}{C.CYAN}=============================================================={C.END}\n")

    # 1. Challenge Al
    print("[1/3] Kriptografik HMAC Challenge alınıyor...")
    challenge = fetch_challenge()
    print(f"  - Token Challenge: {C.YELLOW}{challenge[:35]}...{C.END}")

    # 2. İnsan Düşünme & Hareket Süresi (Dwell Time: >1.6 sn)
    wait_time = random.uniform(1.8, 2.3)
    print(f"[2/3] Fizyolojik dwell-time simülasyonu ({wait_time:.2f}s bekleniyor)...")
    time.sleep(wait_time)

    # 3. Apex Telemetrisini İlet
    payload = build_payload(challenge)
    print("[3/3] Biyomekanik paket /api/score uç noktasına iletiliyor...")

    def send(p):
        req = urllib.request.Request(SCORE_URL, data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    t0 = time.perf_counter()
    status, res = send(payload)
    latency = (time.perf_counter() - t0) * 1000

    # 4. Akıllı PoW Meydan Okuması (Smart Challenge) Yönetimi
    if res.get("status") == "challenge_required":
        print(f"\n{C.YELLOW} [!] Sunucu Gri Alanda 'Proof-of-Work' Meydan Okuması İstedi!{C.END}")
        salt = res["pow_salt"]
        diff = res.get("pow_difficulty", 4)
        nonce = solve_pow(salt, diff)

        # Bulmaca çözümüyle tekrar gönder
        payload["pow_salt"] = salt
        payload["pow_nonce"] = nonce
        print("[+] Çözüm sunucuya iletiliyor...")
        t0 = time.perf_counter()
        status, res = send(payload)
        latency = (time.perf_counter() - t0) * 1000

    score = res.get("bot_score", 0.0)
    classification = res.get("classification", "Unknown")
    threat = res.get("details", {}).get("threat_type", "NONE")
    reasons = res.get("reasons", [])

    print(f"\n{C.BOLD}=============================================================={C.END}")
    print(f"Sunucu Yanıt Gecikmesi: {C.YELLOW}{latency:.2f} ms{C.END}")
    print(f"HTTP Kodu:              {status}")
    print(f"Karar:                  {C.GREEN if classification == 'Human' else C.RED}{classification}{C.END} (Risk: {score:.1f}%)")
    print(f"Tehdit Atfı:            {C.CYAN}{threat}{C.END}")
    print(f"Tetiklenen Nedenler:")
    for r in reasons:
        print(f"  * {r}")
    print(f"{C.BOLD}=============================================================={C.END}\n")

if __name__ == "__main__": 
    run_apex_test()
