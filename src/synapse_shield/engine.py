"""
Synapse Shield - Core Behavioral Decision Engine v0.4.1 (Anti-Bezier Hardened)
"""

import math
from typing import Dict, Any, List, Tuple
from .features import extract_features

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
    telemetry: Dict[str, Any], 
    recent_request_count: int = 1,
    is_ip_penalized: bool = False,
    accessibility_mode: bool = False
) -> Tuple[float, str, List[str], Dict[str, Any]]:
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
        
    # 2. Ekran Boyutları (Headless)
    if not features["screen_valid"]:
        total_risk += 35.0
        reasons.append("Invalid or headless screen dimensions detected.")
        
    # 3. Faresiz Form Etkileşimi
    if (features["click_count"] > 0 or features["key_count"] > 0) and features["mouse_points"] == 0:
        total_risk += 50.0
        reasons.append("Interactive events occurred without mouse movement telemetry.")

    # 4. Kinematik & Bézier Eğrisi Analizi
    if features["mouse_points"] > 5:
        # Erişilebilirlik modunda matematiksel katılık azaltılır (örn. Trackball kullanıcıları için)
        acc_multiplier = 0.3 if accessibility_mode else 1.0

        # A. Doğrusallık (Düz Çizgi Botları)
        if features["total_distance"] > 30 and features["straightness"] > 0.985:
            risk_add = 75.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(f"Euclidean straight-line trajectory detected (straightness: {features['straightness']:.4f}) [+{risk_add:.1f}].")
            
        # B. Robotik Hız & İvme Varyansı
        if features["total_distance"] > 30 and features["velocity_var"] < 1e-5:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(f"Near-zero velocity variance observed in mouse path [+{risk_add:.1f}].")
            
        # C. Bézier Eğrisi & Polinomal İvme İmzası (Bézier botlarında < 1.5e-5)
        if features["total_distance"] > 30 and features["acceleration_var"] < 1.5e-5:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(f"Unnatural polynomial acceleration curve detected (acceleration_var: {features['acceleration_var']:.7f}) [+{risk_add:.1f}].")

        # D. Nöromüsküler Jerk Titremesi Eksikliği (Bézier matematiksel pürüzsüzlük tespiti)
        if features["total_distance"] > 50 and features["avg_jerk"] < 0.00008:
            risk_add = 65.0 * acc_multiplier
            total_risk += risk_add
            reasons.append(f"Unnatural mathematical smoothness: Missing physiological 8-12Hz Jerk tremor (avg_jerk: {features['avg_jerk']:.7f}) [+{risk_add:.1f}].")

        # E. Deterministik Zamanlayıcı (dt_var == 0)
        if features["mouse_points"] >= 10 and features["dt_var"] < 0.01:
            total_risk += 35.0
            reasons.append("Deterministic fixed-interval timer observed (zero dt variance).")

        # F. FITTS KANUNU (Hedefe Yaklaşırken Yavaşlamayan Eğri Botları)
        if features["click_count"] > 0 and features["total_distance"] > 50:
            if features["terminal_decel_ratio"] > 0.70:
                total_risk += 45.0
                reasons.append(f"Fitts's Law violation: Lack of terminal deceleration before click ({features['terminal_decel_ratio']:.2f}).")

        # G. İnsanüstü Hız
        if features["max_velocity"] > 15.0:
            total_risk += 40.0
            reasons.append(f"Superhuman mouse velocity (max: {features['max_velocity']:.2f} px/ms).")

    # 5. Klavye Dinamikleri
    if features["key_count"] > 3:
        if features["key_interval_var"] < 4.0:
            total_risk += 60.0
            reasons.append(f"Highly rhythmic typing pattern detected (variance: {features['key_interval_var']:.2f} ms²).")
            
        if features["key_interval_avg"] < 25.0:
            total_risk += 50.0
            reasons.append(f"Superhuman input frequency (avg typing interval: {features['key_interval_avg']:.1f} ms).")

    # 6. Poisson Frekans Analizi & Akıllı Biyometrik Füzyon
    freq_anomaly = poisson_anomaly_score(recent_request_count, lambda_val=2.0)
    if freq_anomaly >= 0.95:
        is_human_telemetry = (
            features["mouse_points"] > 5 
            and features["straightness"] < 0.96 
            and features["avg_jerk"] > 0.00010
            and features["acceleration_var"] > 2e-5
        )
        if is_human_telemetry:
            total_risk += 25.0 * freq_anomaly
            reasons.append(f"High request frequency ({recent_request_count} req/10s), but organic human kinematics verified.")
        else:
            total_risk += 60.0 * freq_anomaly
            reasons.append(f"Poisson request frequency anomaly (rate: {recent_request_count} req/10s, risk confidence: {freq_anomaly*100:.1f}%).")

    bot_score = min(100.0, max(0.0, total_risk))
    classification = "Bot" if bot_score >= 50.0 else "Human"
    
    if bot_score < 10.0:
        reasons.append("Natural behavioral telemetry flags verified.")
        
    details = {
        "features": features,
        "recent_request_count": recent_request_count,
        "poisson_anomaly_score": freq_anomaly,
        "is_ip_penalized": is_ip_penalized,
        "accessibility_mode": accessibility_mode
    }
    
    return bot_score, classification, reasons, details
