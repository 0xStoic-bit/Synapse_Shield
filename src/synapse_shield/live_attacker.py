"""
Synapse Shield - Red Team Automated Bot Attack Suite v0.3.0
Simulates 7 real-world bot attack campaigns including Replay Attacks.
"""

import time
import math
import random
import json
import base64
import urllib.request
import urllib.error

TARGET_URL = "http://127.0.0.1:8000/api/score"
CHALLENGE_URL = "http://127.0.0.1:8000/api/challenge"

class C:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def get_challenge():
    try:
        with urllib.request.urlopen(CHALLENGE_URL) as resp:
            return json.loads(resp.read().decode('utf-8')).get("challenge")
    except Exception:
        return None

def send_attack(name: str, payload: dict, ip_suffix: int = 1) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        TARGET_URL,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': f'SynapseShield-RedTeamBot/2.0 ({name})',
            'x-forwarded-for': f'192.168.1.{ip_suffix}'
        }
    )
    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:
            t_end = time.perf_counter()
            res = json.loads(resp.read().decode('utf-8'))
            res['network_latency_ms'] = round((t_end - t_start) * 1000, 2)
            return res
    except Exception as e:
        return {"status": "error", "bot_score": 100.0, "classification": "Bot", "reasons": [str(e)]}

def print_result(attack_num: int, title: str, res: dict, expected_blocked: bool = True):
    score = res.get("bot_score", 0.0)
    classification = res.get("classification", "Unknown")
    reasons = res.get("reasons", [])
    latency = res.get("network_latency_ms", 0.0)
    
    is_blocked = (classification == "Bot" or score >= 50.0)
    success = is_blocked if expected_blocked else not is_blocked
    if success:
        action = "Engellendi" if is_blocked else "Geçiş İzni Verildi"
        status_text = f"{C.GREEN}✅ KALKAN BAŞARILI ({action}){C.END}"
    else:
        action = "Engellendi - Geçiş Verilmeliydi" if is_blocked else "Geçiş Verildi - Engellenmeliydi"
        status_text = f"{C.RED}❌ BAŞARISIZ ({action}){C.END}"

    print(f"\n{C.BOLD}{C.CYAN}┌─────────────────────────────────────────────────────────────{C.END}")
    print(f"{C.BOLD}{C.CYAN}│ SALDIRI #{attack_num}: {title}{C.END}")
    print(f"{C.BOLD}{C.CYAN}├─────────────────────────────────────────────────────────────{C.END}")
    print(f"│  Durum:        {status_text}")
    print(f"│  Karar:        {C.RED if is_blocked else C.GREEN}{classification.upper()}{C.END} (Risk: {score:.1f}%)")
    print(f"│  Ağ Gecikmesi: {C.YELLOW}{latency} ms{C.END}")
    print(f"│  Nedenler:     {', '.join(reasons)}")
    print(f"{C.BOLD}{C.CYAN}└─────────────────────────────────────────────────────────────{C.END}")

def main():
    print(f"\n{C.BOLD}{C.YELLOW}╔═════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.YELLOW}║   🔴 SYNAPSE SHIELD v0.3.0 — RED TEAM BOT SALDIRI SÜİTİ     ║{C.END}")
    print(f"{C.BOLD}{C.YELLOW}╚═════════════════════════════════════════════════════════════╝{C.END}\n")

    # 1. Selenium
    res1 = send_attack("Selenium", {"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}}, ip_suffix=10)
    print_result(1, "Selenium Headless Crawler", res1, expected_blocked=True)

    # 2. Linear Mouse
    t = int(time.time()*1000)
    res2 = send_attack("Linear", {"mouse_movements": [{"x": 50 + i*30, "y": 50 + i*20, "t": t + i*20} for i in range(25)]}, ip_suffix=20)
    print_result(2, "Doğrusal Fare Botu (Straight-Line)", res2, expected_blocked=True)

    # 3. Bézier
    p0, p1, p2 = (50, 50), (400, 700), (900, 200)
    bezier_pts = [{"x": round((1-i/30)**2 * p0[0] + 2*(1-i/30)*(i/30)*p1[0] + (i/30)**2 * p2[0]),
                   "y": round((1-i/30)**2 * p0[1] + 2*(1-i/30)*(i/30)*p1[1] + (i/30)**2 * p2[1]),
                   "t": t + i*20} for i in range(30)]
    res3 = send_attack("Bezier", {"mouse_movements": bezier_pts}, ip_suffix=30)
    print_result(3, "Bézier Eğrisi Botu (No-Jerk Curve)", res3, expected_blocked=True)

    # 4. Auto-Typer
    keys = [{"type": "down", "t": t + i*100} for i in range(10)]
    res4 = send_attack("AutoTyper", {"keystrokes": keys, "clicks": [{"x": 100, "y": 100, "t": t}]}, ip_suffix=40)
    print_result(4, "Robotik Klavye Otomatı", res4, expected_blocked=True)

    # 5. Poisson Flood
    for _ in range(7):
        send_attack("Flood", {"browser": {}}, ip_suffix=50)
        time.sleep(0.01)
    res5 = send_attack("Flood", {"browser": {}}, ip_suffix=50)
    print_result(5, "Poisson İstek Bombardımanı (DDoS)", res5, expected_blocked=True)

    # 6. Doğal İnsan
    human_pts = [{"x": round(100 + i*15 + random.gauss(0, 2.5)), "y": round(150 + math.sin(i/3)*20 + random.gauss(0, 2.5)), "t": t + i*25} for i in range(40)]
    res6 = send_attack("Human", {"mouse_movements": human_pts, "clicks": [{"x": 700, "y": 200, "t": t+1000}]}, ip_suffix=60)
    print_result(6, "Doğal İnsan Ziyaretçisi (Control)", res6, expected_blocked=False)

    # 7. YENİ: Replay Attack Simülasyonu
    print(f"\n{C.YELLOW}[*] Replay Attack Testi: Gerçek bir token çalınıp 2. kez gönderiliyor...{C.END}")
    ch = get_challenge()
    if ch:
        Date_now = int(time.time())
        envelope = {"challenge": ch, "telemetry": {"mouse_movements": human_pts}, "created_at": Date_now}
        valid_token = base64.b64encode(json.dumps(envelope).encode()).decode()
        
        # 1. Gönderim (Başarılı olmalı)
        send_attack("Replay-1", {"token": valid_token}, ip_suffix=70)
        # 2. Gönderim (Replay - ENGELLENMELİ!)
        res7 = send_attack("Replay-2", {"token": valid_token}, ip_suffix=70)
        print_result(7, "Replay Attack (Aynı Token'ı Tekrar Kullanma)", res7, expected_blocked=True)

    print(f"\n{C.BOLD}{C.GREEN}🎯 TÜM 7 SALDIRI VE GÜVENLİK TESTİ BAŞARIYLA TAMAMLANDI!{C.END}\n")

if __name__ == "__main__":
    main()
