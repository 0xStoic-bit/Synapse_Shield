"""
Synapse Shield - Comprehensive All-in-One Test Suite
Tests Kinematics, Poisson math, HMAC Token Challenge, Replay Defense, and Adversarial Bot Vectors.
"""

import os
import sys
import time
import math
import random
import json
import base64

# src klasörünü Python yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def run_all_tests():
    print(f"\n{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.CYAN}║     🛡️  SYNAPSE SHIELD — HER ŞEYİ TEST EDEN SÜİT (v0.3.0)    ║{C.END}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════════╝{C.END}\n")

    total_tests = 0
    passed_tests = 0

    def assert_test(name: str, condition: bool, detail: str = ""):
        nonlocal total_tests, passed_tests
        total_tests += 1
        if condition:
            passed_tests += 1
            print(f"  {C.GREEN}✔ BAŞARILI{C.END} : {name} {C.YELLOW}({detail}){C.END}" if detail else f"  {C.GREEN}✔ BAŞARILI{C.END} : {name}")
        else:
            print(f"  {C.RED}✖ BAŞARISIZ{C.END} : {name} - {detail}")

    # --- 1. KİNEMATİK VE JERK MATEMATİĞİ TESTİ ---
    print(f"{C.BOLD}📦 [MODÜL 1] Kinematik ve Biyomekanik Öznitelikler (features.py){C.END}")
    from synapse_shield.features import extract_features
    
    linear_movements = [{"x": 10 + i * 20, "y": 10 + i * 10, "t": 1000 + i * 20} for i in range(25)]
    f_linear = extract_features({"mouse_movements": linear_movements, "clicks": [], "keystrokes": []})
    assert_test("Doğrusal Bot Tespiti (Straightness == 1.0)", math.isclose(f_linear["straightness"], 1.0, rel_tol=1e-3), f"Straightness={f_linear['straightness']:.4f}")
    assert_test("Sıfır Hız Varyansı Tespiti", f_linear["velocity_var"] < 1e-4, f"Var={f_linear['velocity_var']:.6f}")

    human_movements = []
    t_h = 1000
    for i in range(35):
        t_h += random.randint(18, 32)
        human_movements.append({"x": round(50 + i*12 + random.gauss(0, 1.8)), "y": round(100 + math.sin(i/3.0)*18.0 + random.gauss(0, 1.8)), "t": t_h})
    f_human = extract_features({"mouse_movements": human_movements, "clicks": [{"x": 400, "y": 200, "t": t_h}], "keystrokes": []})
    assert_test("İnsan Kavisli Rota (Straightness < 0.95)", f_human["straightness"] < 0.95, f"Straightness={f_human['straightness']:.4f}")
    assert_test("İnsan Biyolojik Kas Titremesi (Jerk > 0)", f_human["avg_jerk"] > 0, f"Jerk={f_human['avg_jerk']:.6f}")

    # --- 2. POISSON FREKANS MATEMATİĞİ TESTİ ---
    print(f"\n{C.BOLD}📊 [MODÜL 2] Poisson DDoS & İstek Frekansı (engine.py){C.END}")
    from synapse_shield.engine import poisson_anomaly_score
    score_low = poisson_anomaly_score(k=2, lambda_val=2.0)
    score_high = poisson_anomaly_score(k=10, lambda_val=2.0)
    assert_test("Normal Kullanıcı (k=2 İstek -> Anomali Yok)", score_low < 0.90, f"Skor={score_low*100:.1f}%")
    assert_test("DDoS Saldırısı (k=10 İstek -> %99+ Anomali)", score_high >= 0.99, f"Skor={score_high*100:.2f}%")

    # --- 3. KRİPTOGRAFİK TOKEN VE REPLAY ATTACK TESTİ ---
    print(f"\n{C.BOLD}🔐 [MODÜL 3] HMAC Challenge & Replay Attack Koruması (tokens.py){C.END}")
    from synapse_shield.tokens import generate_challenge, verify_and_consume_token
    
    ch_data = generate_challenge()
    tok_envelope = {"challenge": ch_data["challenge"], "telemetry": {"mouse_movements": human_movements}}
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
    
    ok1, reason1, _ = verify_and_consume_token(tok_b64)
    assert_test("1. Token Doğrulaması (Geçerli Nonce)", ok1, reason1)
    
    ok2, reason2, _ = verify_and_consume_token(tok_b64)
    assert_test("2. Replay Attack Engeli (Aynı Token 2. Kez Kullanılamaz)", not ok2, reason2)

    # --- 4. MOTOR KARAR TESTİ (SALDIRI VEKTÖRLERİ) ---
    print(f"\n{C.BOLD}🤖 [MODÜL 4] Karar Motoru & Saldırı Vektörleri (engine.py){C.END}")
    from synapse_shield.engine import analyze_behavior
    
    score_sel, class_sel, _, _ = analyze_behavior({"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}})
    assert_test("Selenium Headless Bot Engelleme", class_sel == "Bot" and score_sel == 100.0, f"Risk={score_sel}%")

    score_lin, class_lin, _, _ = analyze_behavior({"mouse_movements": linear_movements})
    assert_test("Doğrusal Düz Çizgi Botu Engelleme", class_lin == "Bot" and score_lin >= 75.0, f"Risk={score_lin}%")

    # Gerçek İnsan Oturumu (Ekran Boyutuyla Birlikte)
    human_payload = {
        "mouse_movements": human_movements,
        "clicks": [{"x": 400, "y": 200, "t": t_h}],
        "keystrokes": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080
        }
    }

    # Modül 4 içindeki çağrı:
    score_hum, class_hum, _, _ = analyze_behavior(human_payload)
    assert_test("Gerçek İnsan Geçiş İzni (ALLOW)", class_hum == "Human" and score_hum < 20.0, f"Risk={score_hum}%")

    # --- RAPOR ---
    print(f"\n{C.BOLD}{C.CYAN}══════════════════════════════════════════════════════════════{C.END}")
    success_rate = (passed_tests / total_tests) * 100
    if passed_tests == total_tests:
        print(f"  {C.BOLD}{C.GREEN}🎉 TÜM SİSTEM KUSURSUZ ÇALIŞIYOR: {passed_tests}/{total_tests} (%{success_rate:.1f}){C.END}")
    else:
        print(f"  {C.BOLD}{C.RED}⚠️ BAZI TESTLER BAŞARISIZ: {passed_tests}/{total_tests}{C.END}")
    print(f"{C.BOLD}{C.CYAN}══════════════════════════════════════════════════════════════{C.END}\n")

if __name__ == "__main__":
    run_all_tests()