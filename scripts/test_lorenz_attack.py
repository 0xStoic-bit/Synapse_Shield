import sys
import os
sys.path.insert(0, os.path.abspath("src"))

import numpy as np
import math
import json
from synapse_shield.engine import analyze_behavior

# 1. Lorenz Attractor (Runge-Kutta 4) Simülasyonu
def lorenz(x, y, z, s=10.0, r=28.0, b=8.0/3.0):
    x_dot = s * (y - x)
    y_dot = r * x - y - x * z
    z_dot = x * y - b * z
    return x_dot, y_dot, z_dot

dt = 0.01
num_steps = 60

xs = np.empty(num_steps)
ys = np.empty(num_steps)
zs = np.empty(num_steps)
xs[0], ys[0], zs[0] = (0.1, 1.0, 1.05)

for i in range(num_steps - 1):
    x_dot, y_dot, z_dot = lorenz(xs[i], ys[i], zs[i])
    xs[i + 1] = xs[i] + x_dot * dt
    ys[i + 1] = ys[i] + y_dot * dt
    zs[i + 1] = zs[i] + z_dot * dt

start_x, start_y = 100.0, 100.0
target_x, target_y = 800.0, 600.0

# 2. Lorenz kaosu + Exponential Damping (Son %25'te Fitts frenlemesi)
trajectory = []
base_time = 1700000000000.0

for i in range(num_steps):
    t = i / float(num_steps - 1)
    
    # 5. Dereceden Minimum Jerk baz eğrisi (doğal insan ivmesi)
    s = 10 * (t**3) - 15 * (t**4) + 6 * (t**5)
    
    # Son %25'lik pencere (t > 0.75) için exponential decay (frenleme)
    if t > 0.75:
        damping = math.exp(-4.0 * (t - 0.75))
    else:
        damping = 1.0
        
    # Kaotik mikro salınım (Lorenz ölçeklenmiş)
    chaos_x = xs[i] * 1.8 * damping
    chaos_y = ys[i] * 1.8 * damping
    
    curr_x = start_x + (target_x - start_x) * s + chaos_x
    curr_y = start_y + (target_y - start_y) * s + chaos_y
    
    # Doğal dwell-time ve jitter
    time_delta = 16.0 + np.random.exponential(1.5)
    base_time += time_delta
    
    trajectory.append({'x': float(curr_x), 'y': float(curr_y), 't': float(base_time)})

# Telemetri paketi (Temiz tarayıcı profili taklidi + Son noktada Click)
telemetry = {
    "mouse_movements": trajectory,
    "clicks": [{"x": trajectory[-1]["x"], "y": trajectory[-1]["y"], "t": trajectory[-1]["t"]}],
    "keyboard": {
        "key_interval_avg": 120.0,
        "key_interval_var": 450.0,
        "paste_used": False
    },
    "browser": {
        "webdriver": False,
        "screen_width": 1920,
        "screen_height": 1080,
        "is_plugin_array_fake": False,
        "has_webdriver_own_prop": False,
        "is_webgl_hooked": False,
        "is_canvas_hooked": False,
        "is_brave": False
    }
}

risk_score, action, reasons, debug_features = analyze_behavior(telemetry)

print("=" * 60)
print("     LORENZ ATTRACTOR + EXPONENTIAL DECAY ATTACK REPORT")
print("=" * 60)
feats = debug_features.get("features", {})
print(f"Risk Score   : {risk_score:.2f}%")
print(f"Action       : {action}")
print(f"Straightness : {feats.get('straightness', 0):.4f}")
print(f"Avg Jerk     : {feats.get('avg_jerk', 0):.6f}")
print(f"Vel Variance : {feats.get('velocity_var', 0):.4f}")
print(f"Terminal Dec : {feats.get('terminal_decel_ratio', 0):.4f}")
print(f"AI Score     : {debug_features.get('ai_score', 0):.2f}%")
print("-" * 60)
print("Tetiklenen Savunmalar (Reasons):")
for r in reasons:
    print(f" - {r}")
print("=" * 60)
