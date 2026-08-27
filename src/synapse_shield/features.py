import math
from typing import Dict, Any, List

def extract_features(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts behavioral kinematic features from raw telemetry data.
    """
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
    }

    # Browser attributes
    browser = telemetry.get("browser", {})
    features["webdriver"] = bool(browser.get("webdriver", False))
    
    screen_width = browser.get("screen_width", 0)
    screen_height = browser.get("screen_height", 0)
    if screen_width <= 0 or screen_height <= 0:
        features["screen_valid"] = False

    # Scroll data
    scrolls = telemetry.get("scrolls", [])
    features["scroll_count"] = len(scrolls)

    # Click data
    clicks = telemetry.get("clicks", [])
    features["click_count"] = len(clicks)

    # Keystroke data
    keystrokes = telemetry.get("keystrokes", [])
    features["key_count"] = len(keystrokes)
    if len(keystrokes) > 1:
        # Calculate intervals between consecutive keystroke down events
        intervals = []
        # Sort by timestamp
        sorted_keys = sorted(keystrokes, key=lambda k: k.get("t", 0))
        for i in range(1, len(sorted_keys)):
            dt = sorted_keys[i].get("t", 0) - sorted_keys[i - 1].get("t", 0)
            intervals.append(max(0.0, dt))
        
        if intervals:
            avg_int = sum(intervals) / len(intervals)
            features["key_interval_avg"] = avg_int
            # Calculate variance
            var_int = sum((x - avg_int) ** 2 for x in intervals) / len(intervals)
            features["key_interval_var"] = var_int

    # Mouse movement kinematics
    mouse_movements = telemetry.get("mouse_movements", [])
    features["mouse_points"] = len(mouse_movements)
    
    if len(mouse_movements) > 1:
        # Sort by timestamp to ensure chronological order
        movements = sorted(mouse_movements, key=lambda m: m.get("t", 0))
        
        distances = []
        dts = []
        velocities = []
        
        start_x, start_y = movements[0].get("x", 0), movements[0].get("y", 0)
        end_x, end_y = movements[-1].get("x", 0), movements[-1].get("y", 0)
        
        # Total straight-line (Euclidean) distance
        displacement = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        
        # Calculate point-to-point distances and velocities
        for i in range(1, len(movements)):
            x1, y1, t1 = movements[i-1].get("x", 0), movements[i-1].get("y", 0), movements[i-1].get("t", 0)
            x2, y2, t2 = movements[i].get("x", 0), movements[i].get("y", 0), movements[i].get("t", 0)
            
            d_dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            d_time = max(0.1, t2 - t1) # Avoid division by zero, use 0.1ms minimum
            
            distances.append(d_dist)
            dts.append(d_time)
            
            vel = d_dist / d_time # pixels per ms
            velocities.append(vel)
        
        total_dist = sum(distances)
        features["total_distance"] = total_dist
        
        if total_dist > 0:
            features["straightness"] = displacement / total_dist
        else:
            features["straightness"] = 1.0
            
        if velocities:
            avg_vel = sum(velocities) / len(velocities)
            features["avg_velocity"] = avg_vel
            features["max_velocity"] = max(velocities)
            # Velocity variance
            vel_var = sum((v - avg_vel) ** 2 for v in velocities) / len(velocities)
            features["velocity_var"] = vel_var
            
            # Accelerations (change in velocity over time)
            accelerations = []
            for i in range(1, len(velocities)):
                dv = velocities[i] - velocities[i-1]
                dt = dts[i]
                acc = dv / dt
                accelerations.append(acc)
                
            if accelerations:
                avg_acc = sum(accelerations) / len(accelerations)
                features["avg_acceleration"] = avg_acc
                acc_var = sum((a - avg_acc) ** 2 for a in accelerations) / len(accelerations)
                features["acceleration_var"] = acc_var
                
                # Jerk (change in acceleration over time)
                jerks = []
                for i in range(1, len(accelerations)):
                    da = accelerations[i] - accelerations[i-1]
                    dt = dts[i+1] # t at index i+1 matches the time difference for acceleration[i]
                    jerk = da / dt
                    jerks.append(jerk)
                
                if jerks:
                    features["avg_jerk"] = sum(map(abs, jerks)) / len(jerks)

    return features
