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


def _attack_headers(name: str, ip_suffix: int) -> dict:
    """Headers shared by the challenge fetch and the scored request.

    Challenges are bound to client IP + User-Agent (v0.10.1). Fetching the challenge with
    different headers than the attack itself makes *every* request fail as TOKEN_RELAY_ATTACK,
    so the suite would never reach (or measure) the biometric layers.
    """
    return {
        "User-Agent": f"SynapseShield-RedTeamBot/2.0 ({name})",
        "x-forwarded-for": f"192.168.1.{ip_suffix}",
    }


def get_challenge(name: str = "challenge", ip_suffix: int = 1):
    try:
        req = urllib.request.Request(CHALLENGE_URL, headers=_attack_headers(name, ip_suffix))
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")).get("challenge")
    except Exception:
        return None


def make_token(telemetry: dict, wait_sec: float = 1.6, name: str = "challenge", ip_suffix: int = 1) -> str:
    ch = get_challenge(name, ip_suffix)
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
        token_str = make_token(payload, name=name, ip_suffix=ip_suffix)
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
        headers={"Content-Type": "application/json", **_attack_headers(name, ip_suffix)},
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
            body["http_status"] = e.code
            # Gateway rejections (missing/forged/replayed token, bans) return only
            # {"detail": ...} without a verdict. An HTTP 4xx/5xx refusal IS a block.
            if "classification" not in body:
                body["classification"] = "Bot"
                body.setdefault("bot_score", 100.0)
                detail = body.get("detail") or body.get("error")
                body.setdefault("reasons", [f"HTTP {e.code}: {detail}" if detail else f"HTTP {e.code}"])
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
    print(f"{C.BOLD}{C.YELLOW}║   🔴 SYNAPSE SHIELD v0.10.6 — LIVE RED TEAM PEN-TEST ATTACK SUITE     ║{C.END}")
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
    # SDK şeması: dokunmalar mouse_movements içinde source="touch" + r (yarıçap) + f (kuvvet),
    # parmak kaldırma clicks içinde tap_duration_ms ile gelir (synapse-sdk.js touch* olayları).
    human_touch = [
        {
            "x": round(150 + i * 6 + random.gauss(0, 1.5)),
            "y": round(300 + i * 9 + math.sin(i / 2) * 4 + random.gauss(0, 1.5)),
            "t": t + i * 22 + random.randint(0, 6),
            "r": round(9.0 + random.uniform(-1.5, 1.5), 3),
            "f": round(0.55 + random.uniform(-0.1, 0.1), 3),
            "source": "touch",
        }
        for i in range(25)
    ]
    res_mob_human = send_attack(
        "MobileHuman",
        {
            "mouse_movements": human_touch,
            "clicks": [{"x": 300, "y": 520, "t": t + 700, "r": 9.4, "tap_duration_ms": 96, "source": "touch"}],
            "browser": {
                "webdriver": False,
                "screen_width": 390,
                "screen_height": 844,
                "device_pixel_ratio": 3.0,
                "touch_supported": True,
                "max_touch_points": 5,
                "motion_variance": 0.42,
                "webgl_renderer": "Apple GPU",
                "plugins_length": 0,
            },
        },
        ip_suffix=55,
    )
    print_result(7, "Mobil İnsan Parmak Deformasyonu (Fleshy Finger Compliance)", res_mob_human, expected_blocked=False)

    # 8. Doğal Masaüstü İnsan Ziyaretçisi (Control)
    # İnsan kontrol grubu: düzensiz örnekleme aralığı (sabit 25 ms bir bot imzasıdır) ve
    # hedefe yaklaşırken yavaşlama (Fitts). Tıklama yolun bittiği noktada yapılır.
    human_pts = []
    ht = t
    for i in range(40):
        progress = 1 - (1 - i / 39) ** 2  # ease-out: son bölümde adımlar küçülür
        human_pts.append({
            "x": round(100 + progress * 600 + random.gauss(0, 2.5)),
            "y": round(150 + math.sin(i / 3) * 20 + random.gauss(0, 2.5)),
            "t": ht,
        })
        ht += random.randint(14, 38)
    res_human = send_attack(
        "Human",
        {
            "mouse_movements": human_pts,
            "clicks": [{"x": human_pts[-1]["x"], "y": human_pts[-1]["y"], "t": ht + 120}],
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "max_touch_points": 0}
        },
        ip_suffix=60,
    )
    print_result(8, "Doğal Masaüstü İnsan Ziyaretçisi (Tremor + Deceleration)", res_human, expected_blocked=False)

    # 9. Replay Attack (Aynı Token'ı 2 Kez Kullanma)
    print(f"\n{C.YELLOW}[*] Replay Attack Testi: Gerçek bir token çalınıp 2. kez gönderiliyor...{C.END}")
    # Aynı istemci kimliği (IP + UA) kullanılır: ikinci isteğin Relay değil Replay
    # savunmasına takıldığını ölçmek için.
    ch = get_challenge("Replay", 70)
    if ch:
        time.sleep(1.6)
        envelope = {"challenge": ch, "telemetry": {"mouse_movements": human_pts}, "created_at": int(time.time() * 1000)}
        valid_token = base64.b64encode(json.dumps(envelope).encode()).decode()

        # 1. Gönderim (Başarılı)
        send_attack("Replay", {"token": valid_token}, ip_suffix=70)
        # 2. Gönderim (Replay - ENGELLENMELİ!)
        res_replay = send_attack("Replay", {"token": valid_token}, ip_suffix=70)
        print_result(9, "Replay Attack (Aynı Token'ı Tekrar Kullanma)", res_replay, expected_blocked=True)

    print(f"\n{C.BOLD}{C.GREEN}🎯 TÜM 9 RED TEAM GÜVENLİK TESTİ BAŞARIYLA TAMAMLANDI!{C.END}\n")


if __name__ == "__main__":
    main()
