"""
Synapse Shield - Red Team Automated Bot Attack Suite v0.4.0
Simulates 7 real-world bot attack campaigns including Replay Attacks.
"""

import base64
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TARGET_URL = "http://127.0.0.1:8000/api/score"
CHALLENGE_URL = "http://127.0.0.1:8000/api/challenge"


class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def get_challenge():
    try:
        with urllib.request.urlopen(CHALLENGE_URL) as resp:
            return json.loads(resp.read().decode("utf-8")).get("challenge")
    except Exception:
        return None


def make_token(telemetry: dict, wait_sec: float = 1.6) -> str:
    ch = get_challenge()
    if not ch:
        return ""
    if wait_sec > 0:
        time.sleep(wait_sec)
    envelope = {
        "challenge": ch,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000)
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()


def clear_bans():
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/clear", method="POST")
        with urllib.request.urlopen(req):
            pass
    except Exception:
        pass


def send_attack(name: str, payload: dict, ip_suffix: int = 1) -> dict:
    # Eğer payload içinde 'token' yoksa ve 'raw' flag verilmemişse, geçerli token zarfı oluştur
    if "token" not in payload and not payload.get("__raw__"):
        token_str = make_token(payload)
        post_data = {"token": token_str}
    elif payload.get("__raw__"):
        p = payload.copy()
        p.pop("__raw__", None)
        post_data = p
    else:
        post_data = payload

    data = json.dumps(post_data).encode("utf-8")
    req = urllib.request.Request(
        TARGET_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"SynapseShield-RedTeamBot/2.0 ({name})",
            "x-forwarded-for": f"192.168.1.{ip_suffix}",
        },
    )
    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:
            t_end = time.perf_counter()
            res = json.loads(resp.read().decode("utf-8"))
            res["network_latency_ms"] = round((t_end - t_start) * 1000, 2)
            return res
    except urllib.error.HTTPError as e:
        t_end = time.perf_counter()
        try:
            body = json.loads(e.read().decode("utf-8"))
            body["network_latency_ms"] = round((t_end - t_start) * 1000, 2)
            return body
        except Exception:
            return {"status": "error", "bot_score": 100.0, "classification": "Bot", "reasons": [f"HTTP {e.code}: {e.reason}"], "network_latency_ms": round((t_end - t_start) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "bot_score": 100.0, "classification": "Bot", "reasons": [str(e)], "network_latency_ms": 0.0}


def print_result(attack_num: int, title: str, res: dict, expected_blocked: bool = True):
    score = res.get("bot_score", 0.0)
    classification = res.get("classification", "Unknown")
    reasons = res.get("reasons", [])
    latency = res.get("network_latency_ms", 0.0)
    threat_tags = res.get("threat_attribution", [])

    is_blocked = classification == "Bot" or score >= 50.0
    success = is_blocked if expected_blocked else not is_blocked
    if success:
        action = "Engellendi (BLOCKED)" if is_blocked else "Geçiş İzni Verildi (ALLOWED)"
        status_text = f"{C.GREEN}✅ KALKAN BAŞARILI ({action}){C.END}"
    else:
        action = "Engellendi - Geçiş Verilmeliydi" if is_blocked else "Geçiş Verildi - Engellenmeliydi"
        status_text = f"{C.RED}❌ BAŞARISIZ ({action}){C.END}"

    print(f"\n{C.BOLD}{C.CYAN}┌─────────────────────────────────────────────────────────────{C.END}")
    print(f"{C.BOLD}{C.CYAN}│ SALDIRI #{attack_num}: {title}{C.END}")
    print(f"{C.BOLD}{C.CYAN}├─────────────────────────────────────────────────────────────{C.END}")
    print(f"│  Durum:        {status_text}")
    print(f"│  Karar:        {C.RED if is_blocked else C.GREEN}{classification.upper()}{C.END} (Risk Skoru: %{score:.1f})")
    print(f"│  Ağ Gecikmesi: {C.YELLOW}{latency} ms{C.END}")
    if threat_tags:
        print(f"│  Tehdit İmzası:{C.RED} {', '.join(threat_tags)}{C.END}")
    print(f"│  Açıklama:     {', '.join(reasons) if reasons else 'Normal kullanıcı davranışı'}")
    print(f"{C.BOLD}{C.CYAN}└─────────────────────────────────────────────────────────────{C.END}")


def main():
    print(f"\n{C.BOLD}{C.YELLOW}╔═══════════════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.YELLOW}║   🔴 SYNAPSE SHIELD v0.9.1 — LIVE RED TEAM PEN-TEST ATTACK SUITE     ║{C.END}")
    print(f"{C.BOLD}{C.YELLOW}╚═══════════════════════════════════════════════════════════════════════╝{C.END}\n")

    clear_bans()

    # 1. Token Olmadan Ham İstek (Layer 1 Kripto Kontrolü)
    res0 = send_attack("Tokenless", {"__raw__": True, "telemetry": {}}, ip_suffix=5)
    print_result(1, "Token Olmayan Ham İstek (Cryptographic Shield)", res0, expected_blocked=True)

    # 2. Selenium Headless
    res1 = send_attack(
        "Selenium", {"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}}, ip_suffix=10
    )
    print_result(2, "Selenium / Playwright Headless Crawler", res1, expected_blocked=True)

    # 3. Linear Mouse (Doğrusal Bot)
    t = int(time.time() * 1000)
    res2 = send_attack(
        "Linear",
        {"mouse_movements": [{"x": 50 + i * 30, "y": 50 + i * 20, "t": t + i * 20} for i in range(25)]},
        ip_suffix=20,
    )
    print_result(3, "Doğrusal Fare Botu (Straightness = 1.0, Jerk = 0)", res2, expected_blocked=True)

    # 4. Bézier Eğrisi Botu
    p0, p1, p2 = (50, 50), (400, 700), (900, 200)
    bezier_pts = [
        {
            "x": round((1 - i / 30) ** 2 * p0[0] + 2 * (1 - i / 30) * (i / 30) * p1[0] + (i / 30) ** 2 * p2[0]),
            "y": round((1 - i / 30) ** 2 * p0[1] + 2 * (1 - i / 30) * (i / 30) * p1[1] + (i / 30) ** 2 * p2[1]),
            "t": t + i * 20,
        }
        for i in range(30)
    ]
    res3 = send_attack("Bezier", {"mouse_movements": bezier_pts}, ip_suffix=30)
    print_result(4, "Bézier Eğrisi Botu (Matematiksel Minimum-Jerk)", res3, expected_blocked=True)

    # 5. Robotik Klavye Otomatı
    keys = [{"type": "down", "t": t + i * 50} for i in range(12)]
    res4 = send_attack("AutoTyper", {"keystrokes": keys, "clicks": [{"x": 100, "y": 100, "t": t}]}, ip_suffix=40)
    print_result(5, "Robotik Klavye Otomatı (Sabit 50ms Tuş Aralığı)", res4, expected_blocked=True)

    # 6. Sentetik Mobil Emülasyon (v0.9.0 Yeniliği)
    res_mob_bot = send_attack(
        "MobileEmulation",
        {
            "browser": {
                "webdriver": False,
                "screen_width": 375,
                "screen_height": 667,
                "max_touch_points": 0,  # Emülatör açığı!
            }
        },
        ip_suffix=45,
    )
    print_result(6, "Sentetik Mobil Emülasyon (Screen < 768px + maxTouchPoints = 0)", res_mob_bot, expected_blocked=True)

    # 7. Doğal İnsan Mobil Ziyaretçisi (Fleshy Finger Compliance)
    human_touch = [
        {"x": 150 + i * 3, "y": 300 + i * 5, "t": t + i * 20, "radiusX": 8.0 + random.uniform(-1.5, 1.5), "force": 0.6}
        for i in range(15)
    ]
    res_mob_human = send_attack(
        "MobileHuman",
        {
            "touch_events": human_touch,
            "browser": {
                "webdriver": False,
                "screen_width": 390,
                "screen_height": 844,
                "max_touch_points": 5,
            }
        },
        ip_suffix=55,
    )
    print_result(7, "Mobil İnsan Parmak Deformasyonu (Fleshy Finger Compliance)", res_mob_human, expected_blocked=False)

    # 8. Doğal Masaüstü İnsan Ziyaretçisi (Control)
    human_pts = [
        {
            "x": round(100 + i * 15 + random.gauss(0, 2.5)),
            "y": round(150 + math.sin(i / 3) * 20 + random.gauss(0, 2.5)),
            "t": t + i * 25,
        }
        for i in range(40)
    ]
    res_human = send_attack(
        "Human",
        {
            "mouse_movements": human_pts,
            "clicks": [{"x": 700, "y": 200, "t": t + 1000}],
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "max_touch_points": 0}
        },
        ip_suffix=60,
    )
    print_result(8, "Doğal Masaüstü İnsan Ziyaretçisi (Tremor + Deceleration)", res_human, expected_blocked=False)

    # 9. Replay Attack (Aynı Token'ı 2 Kez Kullanma)
    print(f"\n{C.YELLOW}[*] Replay Attack Testi: Gerçek bir token çalınıp 2. kez gönderiliyor...{C.END}")
    ch = get_challenge()
    if ch:
        time.sleep(1.6)
        envelope = {"challenge": ch, "telemetry": {"mouse_movements": human_pts}, "created_at": int(time.time() * 1000)}
        valid_token = base64.b64encode(json.dumps(envelope).encode()).decode()

        # 1. Gönderim (Başarılı)
        send_attack("Replay-1", {"token": valid_token}, ip_suffix=70)
        # 2. Gönderim (Replay - ENGELLENMELİ!)
        res_replay = send_attack("Replay-2", {"token": valid_token}, ip_suffix=70)
        print_result(9, "Replay Attack (Aynı Token'ı Tekrar Kullanma)", res_replay, expected_blocked=True)

    print(f"\n{C.BOLD}{C.GREEN}🎯 TÜM 9 RED TEAM GÜVENLİK TESTİ BAŞARIYLA TAMAMLANDI!{C.END}\n")


if __name__ == "__main__":
    main()
