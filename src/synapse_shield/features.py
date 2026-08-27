"""
Synapse Shield - Kinematic Feature Extractor v0.2.0
Extracts 19D physical motion vectors + Fitts's Law Deceleration Profiles.
"""

import math
from typing import Dict, Any, List

def extract_features(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    features = {
        "mouse_points": 0,
        "total_distance": 0.0,
        "straightness": 1.0,
        "avg_velocity": 0.0,
        "max_velocity": 0.0,
        "velocity_var": 0.0,
        "avg_acceleration": 0.0,
        "acceleration_var": 0.0,
        "avg_jerk": 0.0,
        "click_count": 0,
        "key_count": 0,
        "key_interval_avg": 0.0,
        "key_interval_var": 0.0,
        "webdriver": False,
        "screen_valid": True,
        "scroll_count": 0,
        "terminal_decel_ratio": 1.0,  # Fitts Kanunu: Son hız / Tepe hız oranı
        "velocity_skewness": 0.0,     # Hız profilinin asimetrisi (Balistik vs Düzeltici)
    }

    # Tarayıcı Nitelikleri
    browser = telemetry.get("browser", {})
    features["webdriver"] = bool(browser.get("webdriver", False))
    
    screen_width = browser.get("screen_width", 0)
    screen_height = browser.get("screen_height", 0)
    if screen_width <= 0 or screen_height <= 0:
        features["screen_valid"] = False

    features["scroll_count"] = len(telemetry.get("scrolls", []))
    features["click_count"] = len(telemetry.get("clicks", []))

    # Klavye Dinamikleri
    keystrokes = telemetry.get("keystrokes", [])
    features["key_count"] = len(keystrokes)
    if len(keystrokes) > 1:
        sorted_keys = sorted(keystrokes, key=lambda k: k.get("t", 0))
        intervals = [max(0.0, sorted_keys[i].get("t", 0) - sorted_keys[i - 1].get("t", 0)) for i in range(1, len(sorted_keys))]
        if intervals:
            avg_int = sum(intervals) / len(intervals)
            features["key_interval_avg"] = avg_int
            features["key_interval_var"] = sum((x - avg_int) ** 2 for x in intervals) / len(intervals)

    # Fare Hareketi ve Fitts Kanunu Kinematiği
    mouse_movements = telemetry.get("mouse_movements", [])
    features["mouse_points"] = len(mouse_movements)
    
    if len(mouse_movements) > 2:
        movements = sorted(mouse_movements, key=lambda m: m.get("t", 0))
        
        distances, dts, velocities = [], [], []
        start_x, start_y = movements[0].get("x", 0), movements[0].get("y", 0)
        end_x, end_y = movements[-1].get("x", 0), movements[-1].get("y", 0)
        displacement = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        
        for i in range(1, len(movements)):
            x1, y1, t1 = movements[i-1].get("x", 0), movements[i-1].get("y", 0), movements[i-1].get("t", 0)
            x2, y2, t2 = movements[i].get("x", 0), movements[i].get("y", 0), movements[i].get("t", 0)
            
            d_dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            d_time = max(0.1, t2 - t1)
            
            distances.append(d_dist)
            dts.append(d_time)
            velocities.append(d_dist / d_time)
        
        total_dist = sum(distances)
        features["total_distance"] = total_dist
        features["straightness"] = (displacement / total_dist) if total_dist > 0 else 1.0
            
        if velocities:
            avg_vel = sum(velocities) / len(velocities)
            max_vel = max(velocities)
            features["avg_velocity"] = avg_vel
            features["max_velocity"] = max_vel
            features["velocity_var"] = sum((v - avg_vel) ** 2 for v in velocities) / len(velocities)
            
            # FITTS KANUNU 1: Son %20'lik Yoldaki Yavaşlama Oranı
            last_segment_count = max(1, int(len(velocities) * 0.25))
            terminal_avg_vel = sum(velocities[-last_segment_count:]) / last_segment_count
            features["terminal_decel_ratio"] = (terminal_avg_vel / max_vel) if max_vel > 0 else 1.0
            
            # FITTS KANUNU 2: Hızın Tepe Noktası Konumu (Skewer / Asimetri)
            peak_idx = velocities.index(max_vel)
            features["velocity_skewness"] = peak_idx / float(len(velocities)) # İnsanda 0.25 - 0.45 arası
            
            # İvme ve Jerk (Sarsıntı) Hesabı
            accelerations = []
            for i in range(1, len(velocities)):
                accelerations.append((velocities[i] - velocities[i-1]) / dts[i])
                
            if accelerations:
                avg_acc = sum(accelerations) / len(accelerations)
                features["avg_acceleration"] = avg_acc
                features["acceleration_var"] = sum((a - avg_acc) ** 2 for a in accelerations) / len(accelerations)
                
                jerks = []
                for i in range(1, len(accelerations)):
                    jerks.append((accelerations[i] - accelerations[i-1]) / dts[i+1])
                
                if jerks:
                    features["avg_jerk"] = sum(map(abs, jerks)) / len(jerks)

    return features
