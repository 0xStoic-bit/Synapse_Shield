"""
Synapse Shield - Kinematic Feature Extractor v0.4.1 (Anti-Bezier Hardened)
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
        "dt_var": 0.0,
        "click_count": 0,
        "key_count": 0,
        "key_interval_avg": 0.0,
        "key_interval_var": 0.0,
        "webdriver": False,
        "screen_valid": True,
        "scroll_count": 0,
        "terminal_decel_ratio": 1.0,
        "velocity_skewness": 0.0,
        "plugins_length": 1,
        "touch_supported": False,
        "screen_width": 1024.0,
    }

    if not isinstance(telemetry, dict):
        return features

    # 1. Tarayıcı ve Ekran
    browser = telemetry.get("browser", {})
    if isinstance(browser, dict):
        features["webdriver"] = bool(browser.get("webdriver", False))
        try:
            screen_width = float(browser.get("screen_width", 0))
            screen_height = float(browser.get("screen_height", 0))
            features["screen_width"] = screen_width
            if screen_width <= 0 or screen_height <= 0 or math.isnan(screen_width) or math.isnan(screen_height):
                features["screen_valid"] = False
        except (ValueError, TypeError):
            features["screen_valid"] = False
            
        features["touch_supported"] = bool(browser.get("touch_supported", False))
        try:
            features["plugins_length"] = int(browser.get("plugins_length", 1))
        except:
            features["plugins_length"] = 1

    # 2. Sayaçlar
    scrolls = telemetry.get("scrolls", [])
    clicks = telemetry.get("clicks", [])
    features["scroll_count"] = len(scrolls) if isinstance(scrolls, list) else 0
    features["click_count"] = len(clicks) if isinstance(clicks, list) else 0

    # 3. Klavye Dinamikleri
    keystrokes = telemetry.get("keystrokes", [])
    if isinstance(keystrokes, list) and len(keystrokes) > 0:
        valid_keys = [k for k in keystrokes if isinstance(k, dict) and "t" in k and isinstance(k["t"], (int, float)) and not math.isnan(k["t"])]
        features["key_count"] = len(valid_keys)
        if len(valid_keys) > 1:
            sorted_keys = sorted(valid_keys, key=lambda k: k["t"])
            intervals = [max(0.0, sorted_keys[i]["t"] - sorted_keys[i - 1]["t"]) for i in range(1, len(sorted_keys))]
            if intervals:
                avg_int = sum(intervals) / len(intervals)
                features["key_interval_avg"] = avg_int
                features["key_interval_var"] = sum((x - avg_int) ** 2 for x in intervals) / len(intervals)

    # 4. Fare Kinematiği & Biyomekanik Titreme
    mouse_movements = telemetry.get("mouse_movements", [])
    if isinstance(mouse_movements, list):
        valid_moves = []
        for m in mouse_movements:
            if isinstance(m, dict) and "x" in m and "y" in m and "t" in m:
                try:
                    x = float(m["x"])
                    y = float(m["y"])
                    t = float(m["t"])
                    if not (math.isnan(x) or math.isnan(y) or math.isnan(t) or math.isinf(x) or math.isinf(y) or math.isinf(t)):
                        valid_moves.append({"x": x, "y": y, "t": t})
                except (ValueError, TypeError):
                    continue

        features["mouse_points"] = len(valid_moves)

        if len(valid_moves) >= 3:
            # En fazla 300 nokta işleyerek CPU darboğazını engelle
            movements = sorted(valid_moves, key=lambda m: m["t"])[:300]
            distances, dts, velocities = [], [], []
            start_x, start_y = movements[0]["x"], movements[0]["y"]
            end_x, end_y = movements[-1]["x"], movements[-1]["y"]
            displacement = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
            
            for i in range(1, len(movements)):
                x1, y1, t1 = movements[i-1]["x"], movements[i-1]["y"], movements[i-1]["t"]
                x2, y2, t2 = movements[i]["x"], movements[i]["y"], movements[i]["t"]
                
                d_dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                d_time = max(0.1, t2 - t1)
                
                distances.append(d_dist)
                dts.append(d_time)
                velocities.append(d_dist / d_time)
            
            total_dist = sum(distances)
            features["total_distance"] = total_dist
            features["straightness"] = (displacement / total_dist) if total_dist > 1e-4 else 1.0
            features["straightness"] = min(1.0, max(0.0, features["straightness"]))
                
            if velocities:
                avg_vel = sum(velocities) / len(velocities)
                max_vel = max(velocities)
                features["avg_velocity"] = avg_vel
                features["max_velocity"] = max_vel
                features["velocity_var"] = sum((v - avg_vel) ** 2 for v in velocities) / len(velocities)
                
                # dt varyansı (Zamanlama jitter'ı)
                avg_dt = sum(dts) / len(dts)
                features["dt_var"] = sum((dt - avg_dt) ** 2 for dt in dts) / len(dts)
                
                # Fitts Kanunu: Hedefe varırken yavaşlama oranı
                last_segment_count = max(1, int(len(velocities) * 0.25))
                terminal_avg_vel = sum(velocities[-last_segment_count:]) / last_segment_count
                features["terminal_decel_ratio"] = (terminal_avg_vel / max_vel) if max_vel > 1e-5 else 1.0
                
                # Hız tepe noktası asimetrisi
                peak_idx = velocities.index(max_vel)
                features["velocity_skewness"] = peak_idx / float(max(1, len(velocities)))
                
                # İvme ve Jerk (Sarsıntı / Titreme)
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
