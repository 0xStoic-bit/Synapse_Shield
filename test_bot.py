"""
Synapse Shield - Red Team Automated Bot Attack Suite
"""

import time
import math
import random
import json
import urllib.request
import urllib.error

TARGET_URL = "http://127.0.0.1:8000/api/score"

class C:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def send_attack(name: str, payload: dict, ip_suffix: int = 1) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        TARGET_URL,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': f'SynapseShield-RedTeamBot/2.0 ({name})',
            'X-Forwarded-For': f'192.168.1.{ip_suffix}'  # Simüle edilmiş istemci IP'si
        }
    )
    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:
            t_end = time.perf_counter()
            latency = (t_end - t_start) * 1000
            res = json.loads(resp.read().decode('utf-8'))
            res['network_latency_ms'] = round(latency, 2)
            return res
    except urllib.error.HTTPError as e:
        t_end = time.perf_counter()
        latency = (t_end - t_start) * 1000
        try:
            res = json.loads(e.read().decode('utf-8'))
            res['network_latency_ms'] = round(latency, 2)
            return res
        except Exception:
            return {"status": "error", "code": e.code, "bot_score": 100.0, "classification": "Bot", "reasons": [f"HTTP {e.code} Blocked"]}
    except Exception as e:
        return {"status": "connection_error", "detail": str(e)}

def print_result(attack_num: int, title: str, res: dict, expected_blocked: bool = True):
    score = res.get("bot_score", 0.0)
    classification = res.get("classification", "Unknown")
    reasons = res.get("reasons", [])
    latency = res.get("network_latency_ms", 0.0)
    
    is_blocked = (classification == "Bot" or score >= 50.0)
    
    if expected_blocked:
        success = is_blocked
        status_text = f"{C.GREEN}✅ KALKAN BAŞARILI (Bot Engellendi){C.END}" if success else f"{C.RED}❌ KALKAN DELİNDİ (Bot Geçti){C.END}"
    else:
        success = not is_blocked
        status_text = f"{C.GREEN}✅ GEÇİŞ ONAYLANDI (İnsan Tanındı){C.END}" if success else f"{C.RED}❌ YANLIŞ ALARM (İnsan Engellendi){C.END}"

    print(f"\n{C.BOLD}{C.CYAN}┌─────────────────────────────────────────────────────────────{C.END}")
    print(f"{C.BOLD}{C.CYAN}│ SALDIRI #{attack_num}: {title}{C.END}")
    print(f"{C.BOLD}{C.CYAN}├─────────────────────────────────────────────────────────────{C.END}")
    print(f"│  Durum:        {status_text}")
    print(f"│  Karar:        {C.RED if is_blocked else C.GREEN}{classification.upper()}{C.END} (Risk: {score:.1f}%)")
    print(f"│  Ağ Gecikmesi: {C.YELLOW}{latency} ms{C.END}")
    print(f"│  Tetiklenen Kalkan Nedenleri:")
    for r in reasons:
        print(f"│    → {C.YELLOW}{r}{C.END}")
    print(f"{C.BOLD}{C.CYAN}└─────────────────────────────────────────────────────────────{C.END}")

# --- SALDIRI VEKTÖRLERİ ---

def attack_1_headless():
    return {
        "mouse_movements": [{"x": 10, "y": 10, "t": int(time.time()*1000) - 500}],
        "clicks": [{"x": 20, "y": 20, "t": int(time.time()*1000)}],
        "keystrokes": [], "scrolls": [],
        "browser": {"webdriver": True, "screen_width": 800, "screen_height": 600, "touch_supported": False}
    }

def attack_2_linear():
    movements = []
    startX, startY = 50, 100
    endX, endY = 850, 600
    steps = 25
    t = int(time.time() * 1000) - 1000
    for i in range(steps):
        r = i / float(steps)
        movements.append({"x": round(startX + (endX - startX) * r), "y": round(startY + (endY - startY) * r), "t": t + i * 20})
    return {
        "mouse_movements": movements, "clicks": [{"x": endX, "y": endY, "t": t + 510}],
        "keystrokes": [], "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080}
    }

def attack_3_bezier():
    movements = []
    p0, p1, p2 = (50, 50), (400, 700), (900, 200)
    steps = 30
    t = int(time.time() * 1000) - 1200
    for i in range(steps):
        a = i / float(steps)
        bx = (1 - a)**2 * p0[0] + 2 * (1 - a) * a * p1[0] + a**2 * p2[0]
        by = (1 - a)**2 * p0 + 2 * (1 - a) * a * p1 + a**2 * p2
        movements.append({"x": round(bx), "y": round(by), "t": t + i * 20})
    return {
        "mouse_movements": movements, "clicks": [], "keystrokes": [], "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080}
    }

def attack_4_autotyper():
    keystrokes = []
    t = int(time.time() * 1000) - 800
    for i in range(12):
        keystrokes.append({"type": "down", "t": t})
        keystrokes.append({"type": "up", "t": t + 40})
        t += 100
    return {
        "mouse_movements": [], "clicks": [{"x": 300, "y": 400, "t": t + 10}],
        "keystrokes": keystrokes, "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080}
    }

def attack_5_poisson():
    print(f"\n{C.YELLOW}[*] Poisson DDoS Saldırısı Başlatılıyor (192.168.1.50 IP'sinden 8 seri istek)...{C.END}")
    flood_payload = {
        "mouse_movements": [], "clicks": [], "keystrokes": [], "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080}
    }
    for _ in range(7):
        send_attack("DDoS-Ping", flood_payload, ip_suffix=50)
        time.sleep(0.02)
    return flood_payload

def control_human():
    movements = []
    t = int(time.time() * 1000) - 1500
    x, y = 100.0, 150.0
    for i in range(40):
        t += random.randint(18, 38)
        x += random.uniform(8, 22) + random.gauss(0, 1.8)
        y += math.sin(i / 3.5) * 15.0 + random.gauss(0, 1.8)
        movements.append({"x": round(x), "y": round(y), "t": t})
        
    keystrokes = []
    t += 100
    for _ in range(6):
        keystrokes.append({"type": "down", "t": t})
        t += random.randint(70, 130)
        keystrokes.append({"type": "up", "t": t})
        t += random.randint(110, 240)
        
    return {
        "mouse_movements": movements, "clicks": [{"x": round(x), "y": round(y), "t": t}],
        "keystrokes": keystrokes, "scrolls": [{"y": 120, "t": t}],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080}
    }

def main():
    print(f"\n{C.BOLD}{C.YELLOW}╔═════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.YELLOW}║   🔴 SYNAPSE SHIELD — RED TEAM BOT SALDIRI SİMÜLATÖRÜ       ║{C.END}")
    print(f"{C.BOLD}{C.YELLOW}╚═════════════════════════════════════════════════════════════╝{C.END}")
    print(f"Hedef Sunucu: {C.BOLD}{TARGET_URL}{C.END}")
    print("Saldırılar başlatılıyor...\n")

    res1 = send_attack("Selenium", attack_1_headless(), ip_suffix=10)
    print_result(1, "Selenium Headless Crawler", res1, expected_blocked=True)
    time.sleep(0.3)

    res2 = send_attack("LinearMouse", attack_2_linear(), ip_suffix=20)
    print_result(2, "Doğrusal Fare Botu (Linear Trajectory)", res2, expected_blocked=True)
    time.sleep(0.3)

    res3 = send_attack("BezierBot", attack_3_bezier(), ip_suffix=30)
    print_result(3, "Yapay Bézier Eğrisi Botu (No-Jerk Curve)", res3, expected_blocked=True)
    time.sleep(0.3)

    res4 = send_attack("AutoTyper", attack_4_autotyper(), ip_suffix=40)
    print_result(4, "Robotik Klavye Otomatı (Fixed-Interval Typer)", res4, expected_blocked=True)
    time.sleep(0.3)

    payload_5 = attack_5_poisson()
    res5 = send_attack("PoissonFlood", payload_5, ip_suffix=50)
    print_result(5, "Poisson İstek Bombardımanı (API Flooder)", res5, expected_blocked=True)
    time.sleep(0.3)

    res6 = send_attack("NaturalHuman", control_human(), ip_suffix=60)
    print_result(6, "Doğal İnsan Ziyaretçisi (Control Group)", res6, expected_blocked=False)

    print(f"\n{C.BOLD}{C.GREEN}═════════════════════════════════════════════════════════════{C.END}")
    print(f"{C.BOLD}{C.GREEN}🎯 TÜM SALDIRI TESTLERİ TAMAMLANDI!{C.END}")
    print(f"{C.BOLD}{C.GREEN}═════════════════════════════════════════════════════════════{C.END}\n")

if __name__ == "__main__":
    main()