"""
Synapse Shield - Comprehensive All-in-One Test Suite v0.2.0
"""

import sys
import time
import math
import random
import json
import base64

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def run_all_tests():
    print(f"\n{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.CYAN}║     🛡️  SYNAPSE SHIELD — ALL-IN-ONE TEST SUITE (v0.2.0)      ║{C.END}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════════╝{C.END}\n")

    total_tests, passed_tests = 0, 0

    def assert_test(name: str, condition: bool, detail: str = ""):
        nonlocal total_tests, passed_tests
        total_tests += 1
        if condition:
            passed_tests += 1
            print(f"  {C.GREEN}✔ PASSED{C.END} : {name} {C.YELLOW}({detail}){C.END}" if detail else f"  {C.GREEN}✔ PASSED{C.END} : {name}")
        else:
            print(f"  {C.RED}✖ FAILED{C.END} : {name} - {detail}")

    from synapse_shield.features import extract_features
    from synapse_shield.engine import analyze_behavior, poisson_anomaly_score
    from synapse_shield.tokens import generate_challenge, verify_and_consume_token

    # 1. KİNEMATİK MODÜLÜ
    print(f"{C.BOLD}📦 [MODÜL 1] Kinematik ve Biyomekanik Öznitelik Çıkarımı{C.END}")
    linear_movements = [{"x": 10 + i * 20, "y": 10 + i * 10, "t": 1000 + i * 20} for i in range(25)]
    f_linear = extract_features({"mouse_movements": linear_movements, "clicks": [], "keystrokes": []})
    
    assert_test("Doğrusallık Tespiti (Straightness ≈ 1.0)", math.isclose(f_linear["straightness"], 1.0, rel_tol=1e-3), f"Straightness={f_linear['straightness']:.4f}")
    assert_test("Sıfır Hız Varyansı Tespiti", f_linear["velocity_var"] < 1e-4, f"Var={f_linear['velocity_var']:.6f}")

    # Doğal İnsan Hareketi (Fitts Yavaşlamalı)
    human_movements = []
    t_h = 1000
    for i in range(35):
        t_h += random.randint(20, 35)
        # Sona doğru adımı küçülterek Fitts yavaşlaması sağlar
        step = 14 if i < 25 else 3 
        hx = 50 + i * step + random.gauss(0, 1.5)
        hy = 100 + math.sin(i / 3.0) * 20.0 + random.gauss(0, 1.5)
        human_movements.append({"x": round(hx), "y": round(hy), "t": t_h})
        
    f_human = extract_features({"mouse_movements": human_movements, "clicks": [{"x": human_movements[-1]["x"], "y": human_movements[-1]["y"], "t": t_h + 150}], "keystrokes": []})
    assert_test("İnsan Kavisli Rota Tespiti (Straightness < 0.95)", f_human["straightness"] < 0.95, f"Straightness={f_human['straightness']:.4f}")
    assert_test("İnsan Kas Titremesi (Jerk > 0)", f_human["avg_jerk"] > 0, f"Jerk={f_human['avg_jerk']:.5f}")

    # 2. POISSON MODÜLÜ
    print(f"\n{C.BOLD}📊 [MODÜL 2] Poisson Frekans & Yoğunluk Analizi{C.END}")
    score_low = poisson_anomaly_score(k=2, lambda_val=2.0)
    score_high = poisson_anomaly_score(k=10, lambda_val=2.0)
    assert_test("Normal İstek (k=2 -> Anomali Yok)", score_low < 0.90)
    assert_test("DDoS İstek Bombardımanı (k=10 -> %99+ Anomali)", score_high >= 0.99)

    # 3. TOKEN & REPLAY MODÜLÜ
    print(f"\n{C.BOLD}🔐 [MODÜL 3] HMAC Token & Replay Attack Koruması{C.END}")
    ch_data = generate_challenge()
    envelope = {"challenge": ch_data["challenge"], "telemetry": {}}
    tok_b64 = base64.b64encode(json.dumps(envelope).encode()).decode()
    
    ok1, reason1, _ = verify_and_consume_token(tok_b64)
    assert_test("1. Token Doğrulaması (Valid Nonce)", ok1, reason1)
    
    ok2, reason2, _ = verify_and_consume_token(tok_b64)
    assert_test("2. Token Replay Saldırısı Engeli (Replay Defense)", not ok2, reason2)

    # 4. BOT SALDIRI SÜİTİ
    print(f"\n{C.BOLD}🤖 [MODÜL 4] Davranışsal Karar Motoru (Saldırı Vektörleri){C.END}")
    s1, c1, _, _ = analyze_behavior({"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}})
    assert_test("Selenium Webdriver Yakalama", c1 == "Bot")

    s2, c2, _, _ = analyze_behavior({"mouse_movements": linear_movements})
    assert_test("Doğrusal Düz Çizgi Botu Yakalama", c2 == "Bot")

    keys_robotic = [{"type": "down", "t": 1000 + i * 50} for i in range(15)]
    s3, c3, _, _ = analyze_behavior({"mouse_movements": [], "clicks": [{"x": 100, "y": 100, "t": 1000}], "keystrokes": keys_robotic})
    assert_test("Robotik Klavye Otomatı Yakalama", c3 == "Bot")

    s4, c4, _, _ = analyze_behavior({
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
        "mouse_movements": human_movements,
        "clicks": [{"x": human_movements[-1]["x"], "y": human_movements[-1]["y"], "t": t_h + 150}],
        "keystrokes": []
    })
    assert_test("Gerçek İnsan Geçiş İzni (ALLOW)", c4 == "Human" and s4 < 20.0, f"Risk={s4}%")

    print(f"\n{C.BOLD}{C.CYAN}══════════════════════════════════════════════════════════════{C.END}")
    print(f"  {C.BOLD}{C.GREEN}🎯 SONUÇ: {passed_tests}/{total_tests} Test Başarıyla Geçti (%{(passed_tests/total_tests)*100:.1f}){C.END}")
    print(f"{C.BOLD}{C.CYAN}══════════════════════════════════════════════════════════════{C.END}\n")

if __name__ == "__main__":
    run_all_tests()