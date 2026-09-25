"""
Synapse Shield - Core Behavioral Decision Engine v0.4.1 (Anti-Bezier Hardened)
"""

import math
from typing import Any

from .features import MultimodalTokenizer, extract_features
from .models import SynapseHybridModel

# --- GLOBAL WARMUP ---
# FastAPI (Uvicorn) worker başına sadece 1 kez yüklenir, RAM'de kalır.
try:
    _tokenizer = MultimodalTokenizer(max_mouse_steps=60)
    _ai_model = SynapseHybridModel()
except Exception as e:
    _tokenizer = None
    _ai_model = None
    print(f"[Synapse Shield] AI Model load failed: {e}")


def reload_ai_model() -> bool:
    """Reloads the 1D-CNN model weights dynamically from disk into memory."""
    global _ai_model, _tokenizer
    try:
        _tokenizer = MultimodalTokenizer(max_mouse_steps=60)
        _ai_model = SynapseHybridModel()
        return True
    except Exception as e:
        print(f"[Synapse Shield] AI Model reload failed: {e}")
        return False


def poisson_anomaly_score(k: int, lambda_val: float = 2.0) -> float:
    if k <= 1:
        return 0.0
    cumulative_prob = 0.0
    for i in range(k):
        try:
            term = (math.pow(lambda_val, i) * math.exp(-lambda_val)) / math.factorial(i)
            cumulative_prob += term
        except (OverflowError, ValueError):
            break
    return min(1.0, max(0.0, cumulative_prob))


def analyze_behavior(
    telemetry: dict[str, Any],
    recent_request_count: int = 1,
    is_ip_penalized: bool = False,
    accessibility_mode: bool = False,
    session_history: list[dict[str, Any]] | None = None,
) -> tuple[float, str, list[str], dict[str, Any]]:
    features = extract_features(telemetry)
    reasons = []
    total_risk = 0.0

    # 0. Dinamik IP Ceza Durumu
    if is_ip_penalized:
        total_risk += 50.0
        reasons.append("IP address is temporarily penalized due to repeated high-risk bot activity.")

    # 1. Webdriver Tespiti (Hard Block)
    if features["webdriver"]:
        total_risk += 100.0
        reasons.append("Automation tool interface (navigator.webdriver) detected.")

    # 1.5 Anti-Stealth & Prototype Tamper Detection
    browser_data = telemetry.get("browser", {})
    is_stealth_automation = (
        features.get("webdriver", False)
        or browser_data.get("is_plugin_array_fake")
        or browser_data.get("has_webdriver_own_prop")
    )

    if browser_data.get("is_plugin_array_fake") or browser_data.get("has_webdriver_own_prop"):
        total_risk += 100.0
        reasons.append("Stealth browser tamper detected: Mocked plugins or webdriver prototype override (100% Bot).")

    is_dual_hook = browser_data.get("is_webgl_hooked") and browser_data.get("is_canvas_hooked")
    has_human_motion = features.get("straightness", 1.0) < 0.99 and features.get("avg_jerk", 0) > 0.00008

    if is_dual_hook:
        if has_human_motion:
            total_risk += 45.0  # Brave gibi gizlilik tarayıcısı kullanan gerçek insan!
            reasons.append("Privacy browser farbling detected with organic human motion.")
        else:
            total_risk += 85.0  # Hem çift kanca var hem de robotik hareket -> BOT!
            reasons.append("Simultaneous WebGL and Canvas prototype hooks detected without human motion.")
    elif browser_data.get("is_webgl_hooked") or browser_data.get("is_canvas_hooked"):
        if has_human_motion:
            total_risk += 34.0
            reasons.append(
                "Browser fingerprinting hook detected, but human motion verified (Risk lowered to avoid PoW)."
            )
        else:
            total_risk += 45.0
            reasons.append("Browser fingerprinting hook detected without human motion (Possible bot).")

    # 2. Ekran Boyutları (Headless)
    if not features["screen_valid"]:
        total_risk += 35.0
        reasons.append("Invalid or headless screen dimensions detected.")

    # 2.5 Tarayıcı Eklenti Kontrolü (Mobil Yanlış Pozitif Korumalı)
    if (
        not features.get("touch_supported", False)
        and features.get("screen_width", 0) >= 1024
        and features.get("plugins_length", 1) == 0
    ):
        total_risk += 50.0
        reasons.append("Missing browser plugins in desktop environment (Possible headless/stealth bot).")

    # 3. Faresiz Form Etkileşimi
    is_touch = browser_data.get("touch_supported", False)
    if (features["click_count"] > 0 or features["key_count"] > 0) and features["mouse_points"] == 0:
        total_risk += 50.0
        reasons.append("Interactive events occurred without mouse movement telemetry.")

    # 3.5 Mobil & Dokunmatik Biyometrik Doğrulama (Capacitive Touch Kinematics)
    if is_touch:
        screen_w = features.get("screen_width", 1024)
        features.get("max_touch_points", 0)
        touch_count = features.get("touch_event_count", 0)
        avg_radius = features.get("avg_touch_radius", 0.0)
        radius_var = features.get("touch_radius_var", 0.0)

        # A. Sentetik Mobil Emülasyon Tespiti (Küçük ekran + touch_supported var ama maxTouchPoints açıkça 0)
        if "max_touch_points" in browser_data and browser_data["max_touch_points"] == 0 and screen_w < 768:
            total_risk += 60.0
            reasons.append("Synthetic mobile emulation: touch_supported is true on mobile viewport but maxTouchPoints is 0.")

        # B. Doğal Biyolojik Parmak Uyumu (Fleshy Finger Compliance & Area Bonus)
        # Fiziksel kapasitif ekranda insan parmağı temas yüzeyinde mikro deformasyon üretir
        if touch_count >= 2 and avg_radius >= 3.0:
            total_risk = max(0.0, total_risk - 15.0)
            reasons.append(
                f"Capacitive human touch contact verified (avg_radius: {avg_radius:.1f}px, compliance_var: {radius_var:.3f})."
            )

    # 4. Kinematik & Bézier Eğrisi Analizi
    if features["mouse_points"] > 5:
        # Erişilebilirlik modunda matematiksel katılık azaltılır (örn. Trackball kullanıcıları için)
        acc_multiplier = 0.3 if accessibility_mode else 1.0

        # A. Doğrusallık (Düz Çizgi Botları)
        if features["total_distance"] > 30 and features["straightness"] > 0.985 and not is_touch:
            risk_add = 75.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(
                f"Euclidean straight-line trajectory detected (straightness: {features['straightness']:.4f}) [+{risk_add:.1f}]."
            )

        # B. Robotik Hız & İvme Varyansı
        if features["total_distance"] > 30 and features["velocity_var"] < 1e-5:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(f"Near-zero velocity variance observed in mouse path [+{risk_add:.1f}].")

        # C. Bézier Eğrisi & Polinomal İvme İmzası (Bézier botlarında < 1.5e-5)
        if features["total_distance"] > 30 and features["acceleration_var"] < 1.5e-5:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(
                f"Unnatural polynomial acceleration curve detected (acceleration_var: {features['acceleration_var']:.7f}) [+{risk_add:.1f}]."
            )

        # D. Nöromüsküler Jerk Titremesi Eksikliği (Bézier matematiksel pürüzsüzlük tespiti)
        if features["total_distance"] > 50 and features["avg_jerk"] < 0.00008 and not is_touch:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(
                f"Unnatural mathematical smoothness: Missing physiological 8-12Hz Jerk tremor (avg_jerk: {features['avg_jerk']:.7f}) [+{risk_add:.1f}]."
            )

        # E. Deterministik Zamanlayıcı (dt_var == 0)
        if features["mouse_points"] >= 10 and features["dt_var"] < 0.01:
            total_risk += 35.0
            reasons.append("Deterministic fixed-interval timer observed (zero dt variance).")

        # F. FITTS KANUNU (Hedefe Yaklaşırken Yavaşlamayan Eğri Botları)
        if features["click_count"] > 0 and features["total_distance"] > 50:
            if features["terminal_decel_ratio"] > 0.70:
                total_risk += 45.0
                reasons.append(
                    f"Fitts's Law violation: Lack of terminal deceleration before click ({features['terminal_decel_ratio']:.2f})."
                )

        # G. İnsanüstü Hız
        if features["max_velocity"] > 15.0:
            total_risk += 40.0
            reasons.append(f"Superhuman mouse velocity (max: {features['max_velocity']:.2f} px/ms).")

        # H. Tremor Spektral Saflığı (FFT Spectral Purity & Entropi)
        # Biyolojik insan tremoru stokastik ve geniş bantlıdır; botların sinüs dalgaları tek frekansta sivrilir
        if features["total_distance"] > 30 and not is_touch:
            purity = features.get("spectral_purity", 0.0)
            entropy = features.get("spectral_entropy", 1.0)
            if purity > 0.65:
                risk_add = 65.0 * acc_multiplier
                total_risk += risk_add
                reasons.append(
                    f"Synthetic harmonic oscillator tremor detected via FFT (spectral_purity: {purity:.3f}, spectral_entropy: {entropy:.3f}) [+{risk_add:.1f}]."
                )

        # I. Alt-Hareket (Sub-movement Decomposition) Dağılımı
        # Hızlı insan hareketleri hedefe varana kadar mikro düzeltme darbeleri (2-4 tepe) üretir
        if not is_touch:
            submoves = features.get("submovement_count", 0)
            if features["total_distance"] > 60 and submoves <= 1:
                risk_add = 55.0 * acc_multiplier
                total_risk += risk_add
                reasons.append(
                    f"Lack of physiological sub-movement decomposition in trajectory (submovement_count: {submoves}, distance: {features['total_distance']:.1f}px) [+{risk_add:.1f}]."
                )
            elif features["total_distance"] > 40 and submoves > 18:
                risk_add = 45.0 * acc_multiplier
                total_risk += risk_add
                reasons.append(
                    f"Superhuman artificial sub-movement stutter detected ({submoves} peaks) [+{risk_add:.1f}]."
                )

    # 5. Klavye Dinamikleri
    if features.get("key_count", 0) >= 3:
        if features.get("key_interval_var", 50.0) < 2.0:
            total_risk += 75.0
            reasons.append("Robotic constant-interval keystroke timing detected.")

        if features.get("key_interval_avg", 100.0) < 25.0:
            total_risk += 50.0
            reasons.append(f"Superhuman input frequency (avg typing interval: {features['key_interval_avg']:.1f} ms).")

    # 6. Poisson Frekans Analizi & Akıllı Biyometrik Füzyon
    freq_anomaly = poisson_anomaly_score(recent_request_count, lambda_val=2.0)
    if freq_anomaly >= 0.95:
        if is_touch:
            is_human_telemetry = (
                (features.get("mouse_points", 0) > 0 or features.get("click_count", 0) > 0)
                and (features.get("avg_touch_radius", 0.0) > 0.0 or features.get("touch_supported", False))
            )
        else:
            is_human_telemetry = (
                features["mouse_points"] > 5
                and features["straightness"] < 0.96
                and features["avg_jerk"] > 0.00010
                and features["acceleration_var"] > 2e-5
            )
        if is_human_telemetry:
            total_risk += 25.0 * freq_anomaly
            reasons.append(
                f"High request frequency ({recent_request_count} req/10s), but organic human kinematics verified."
            )
        else:
            total_risk += 60.0 * freq_anomaly
            reasons.append(
                f"Poisson request frequency anomaly (rate: {recent_request_count} req/10s, risk confidence: {freq_anomaly * 100:.1f}%)."
            )

    # 6.5 Oturum Düzeyinde Kinetik Değişmezlik (Session Behavioral Invariance)
    # Aynı oturumdan gelen ardışık isteklerde kinetik parametrelerin robotik sabitliği
    if session_history and len(session_history) >= 3:
        s_jerks = [float(h.get("avg_jerk", 0.0)) for h in session_history if "avg_jerk" in h]
        s_straightness = [float(h.get("straightness", 0.0)) for h in session_history if "straightness" in h]

        # Jerk varyansı: bot her istekte aynı sabit tremor genliğini yolluyorsa
        if len(s_jerks) >= 3 and all(j > 0 for j in s_jerks):
            mean_j = sum(s_jerks) / len(s_jerks)
            jerk_var = sum((x - mean_j) ** 2 for x in s_jerks) / len(s_jerks)
            if jerk_var < 1e-12:
                total_risk += 60.0
                reasons.append(
                    "Session Behavioral Invariance: Identical neuromuscular jerk tremor repeated across session requests (deterministic bot template)."
                )

        # Straightness varyansı: bot her istekte tıpatıp aynı düzlüğü üretiyorsa
        if len(s_straightness) >= 3:
            mean_s = sum(s_straightness) / len(s_straightness)
            st_var = sum((x - mean_s) ** 2 for x in s_straightness) / len(s_straightness)
            if st_var < 1e-8:
                total_risk += 50.0
                reasons.append(
                    "Session Behavioral Invariance: Zero straightness variance across consecutive session requests."
                )

    heuristic_score = min(100.0, max(0.0, total_risk))

    # 7. Yapay Zeka (1D-CNN) Puanlaması
    ai_score = 0.0
    if _ai_model and _tokenizer:
        try:
            fused = _tokenizer.fuse(telemetry)
            ai_prob = _ai_model.predict(fused["mouse_tensor"], fused["static_vector"])
            ai_score = ai_prob * 100.0
        except Exception as e:
            ai_score = 0.0
            reasons.append(f"AI Model Error: {e!s}")

    # 8. Max Gating (Karar Birleştirme)
    final_bot_score = max(heuristic_score, ai_score)

    # Brave Farbling Override: Sadece ve sadece başka kritik anomali yoksa skoru düşür
    typing_speed_anomaly = features.get("key_count", 0) >= 3 and (
        features.get("key_interval_var", 50.0) < 2.0 or features.get("key_interval_avg", 100.0) < 25.0
    )
    fitts_violation = (
        features.get("click_count", 0) > 0
        and features.get("total_distance", 0) > 50
        and features.get("terminal_decel_ratio", 0.0) > 0.70
    )
    has_critical_bot_anomaly = (
        is_stealth_automation
        or (not features.get("screen_valid", True))
        or typing_speed_anomaly
        or fitts_violation
        or (recent_request_count > 5 and freq_anomaly >= 0.95)
        or (features.get("max_velocity", 0.0) > 15.0)
    )

    is_brave_like = is_dual_hook or browser_data.get("is_webgl_hooked") or browser_data.get("is_canvas_hooked")
    if is_brave_like and has_human_motion and not has_critical_bot_anomaly:
        final_bot_score = min(final_bot_score, 34.0)
        reasons.append(
            "AI and heuristic scores capped at 34.0 due to verified organic human motion with privacy farbling."
        )

    classification = "Bot" if final_bot_score >= 50.0 else "Human"

    if final_bot_score >= 50.0:
        if ai_score >= 50.0:
            reasons.append(f"1D-CNN AI Engine Confidence: {ai_score:.1f}% Bot.")
    else:
        if final_bot_score < 10.0:
            reasons.append("Natural behavioral telemetry flags verified by AI & Heuristics.")

    # 9. Tehdit Atıf Hiyerarşisi (Threat Attribution Hierarchy)
    threat_type = classify_threat(
        features=features,
        telemetry=telemetry,
        recent_request_count=recent_request_count,
        freq_anomaly=freq_anomaly,
        ai_score=ai_score,
        classification=classification,
        reasons=reasons,
    )

    details = {
        "features": features,
        "recent_request_count": recent_request_count,
        "poisson_anomaly_score": freq_anomaly,
        "heuristic_score": heuristic_score,
        "ai_score": ai_score,
        "threat_type": threat_type,
        "is_ip_penalized": is_ip_penalized,
        "accessibility_mode": accessibility_mode,
        "session_history_count": len(session_history) if session_history else 0,
    }

    return final_bot_score, classification, reasons, details


def classify_threat(
    features: dict[str, Any],
    telemetry: dict[str, Any],
    recent_request_count: int,
    freq_anomaly: float,
    ai_score: float,
    classification: str,
    reasons: list[str] | None = None,
) -> str:
    """
    Deterministik Tehdit Atıf Hiyerarşisi:
    REPLAY_ATTACK > STEALTH_AUTOMATION > MINIMUM_JERK_BOT > LINEAR_MACRO > POISSON_FLOOD > ROBOTIC_KEYSTROKE > UNKNOWN_ANOMALY / CLEAN_HUMAN
    """
    if classification == "Human":
        return "CLEAN_HUMAN"

    if reasons and any("Session Behavioral Invariance" in r for r in reasons):
        return "SESSION_INVARIANCE_BOT"

    browser_data = telemetry.get("browser", {})

    # 1. STEALTH_AUTOMATION (Tarayıcı Seviyesi / Stealth Botlar)
    is_stealth = (
        features.get("webdriver", False)
        or browser_data.get("is_plugin_array_fake", False)
        or browser_data.get("has_webdriver_own_prop", False)
        or browser_data.get("is_webgl_hooked", False)
        or browser_data.get("is_canvas_hooked", False)
        or (not features.get("screen_valid", True))
        or (
            not features.get("touch_supported", False)
            and features.get("screen_width", 0) >= 1024
            and features.get("plugins_length", 1) == 0
        )
    )
    if is_stealth:
        return "STEALTH_AUTOMATION"

    # 2. MINIMUM_JERK_BOT (Sentetik Biyolojik Eğri / Flash & Hogan / Bézier İvme / Fitts İhlali / Spektral Sinüs)
    # Düz çizgi olmayan (straightness <= 0.985) ancak sentetik pürüzsüzlüğe / düşük jerk'e sahip eğriler veya FFT sinüs osilatörü
    if (
        features.get("mouse_points", 0) > 5
        and features.get("total_distance", 0) > 30
        and not features.get("touch_supported", False)
    ):
        is_min_jerk = (
            features.get("straightness", 0.0) <= 0.985
            and (
                features.get("avg_jerk", 1.0) < 0.00008
                or features.get("acceleration_var", 1.0) < 1.5e-5
                or (features.get("click_count", 0) > 0 and features.get("terminal_decel_ratio", 0.0) > 0.70)
                or (features.get("mouse_points", 0) >= 10 and features.get("dt_var", 1.0) < 0.01)
                or (features.get("total_distance", 0) > 60 and features.get("submovement_count", 0) <= 1)
            )
        ) or (features.get("spectral_purity", 0.0) > 0.65)
        if is_min_jerk:
            return "MINIMUM_JERK_BOT"

    # 3. LINEAR_MACRO (Doğrusal Hareket / Sıfır Hız Varyansı / Teleport Fare)
    is_linear = (
        features.get("mouse_points", 0) > 5
        and features.get("total_distance", 0) > 30
        and not features.get("touch_supported", False)
        and (features.get("straightness", 0.0) > 0.985 or features.get("velocity_var", 1.0) < 1e-5)
    ) or (
        (features.get("click_count", 0) > 0 or features.get("key_count", 0) > 0)
        and features.get("mouse_points", 0) == 0
        and not features.get("touch_supported", False)
    )
    if is_linear:
        return "LINEAR_MACRO"

    # 4. POISSON_FLOOD (Hacimsel Anomali / DoS)
    if recent_request_count > 5 and freq_anomaly >= 0.95:
        return "POISSON_FLOOD"

    # 5. ROBOTIC_KEYSTROKE (Mekanik Klavye Girişi)
    if features.get("key_count", 0) > 3:
        if features.get("key_interval_var", 100.0) < 4.0 or features.get("key_interval_avg", 100.0) < 25.0:
            return "ROBOTIC_KEYSTROKE"

    # 6. Genel AI veya Kural Anomalisi
    return "UNKNOWN_ANOMALY"
