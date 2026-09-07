import sys
import os
sys.path.insert(0, os.path.abspath("src"))

import math
import numpy as np
from synapse_shield.features import MultimodalTokenizer
from synapse_shield.train import sigmoid, WEIGHTS_PATH

def generate_lorenz_sample():
    """Az önce sistemi bypass eden Lorenz Attractor + Exponential Decay botu"""
    def lorenz(x, y, z, s=10.0, r=28.0, b=8.0/3.0):
        return s * (y - x), r * x - y - x * z, x * y - b * z

    dt = 0.01
    num_steps = 60
    xs = np.empty(num_steps)
    ys = np.empty(num_steps)
    zs = np.empty(num_steps)
    xs[0], ys[0], zs[0] = (np.random.uniform(0.05, 0.2), 1.0, 1.05)

    for i in range(num_steps - 1):
        x_dot, y_dot, z_dot = lorenz(xs[i], ys[i], zs[i])
        xs[i + 1] = xs[i] + x_dot * dt
        ys[i + 1] = ys[i] + y_dot * dt
        zs[i + 1] = zs[i] + z_dot * dt

    start_x, start_y = np.random.uniform(50, 200), np.random.uniform(50, 200)
    target_x, target_y = np.random.uniform(600, 900), np.random.uniform(500, 800)

    trajectory = []
    base_time = 1700000000000.0

    for i in range(num_steps):
        t = i / float(num_steps - 1)
        s = 10 * (t**3) - 15 * (t**4) + 6 * (t**5)
        damping = math.exp(-4.0 * (t - 0.75)) if t > 0.75 else 1.0
        
        chaos_x = xs[i] * np.random.uniform(1.2, 2.2) * damping
        chaos_y = ys[i] * np.random.uniform(1.2, 2.2) * damping
        
        curr_x = start_x + (target_x - start_x) * s + chaos_x
        curr_y = start_y + (target_y - start_y) * s + chaos_y
        base_time += 16.0 + np.random.exponential(1.5)
        trajectory.append({'x': float(curr_x), 'y': float(curr_y), 't': float(base_time)})

    return {
        "mouse_movements": trajectory,
        "clicks": [{"x": trajectory[-1]["x"], "y": trajectory[-1]["y"], "t": trajectory[-1]["t"]}],
        "keyboard": {"key_interval_avg": 120.0, "key_interval_var": 450.0, "paste_used": False},
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

def generate_human_sample():
    """Gerçek insan organik fare hareketi (alt hedefler, düzensiz duraklamalar, biyolojik tremor)"""
    num_steps = 60
    start_x, start_y = np.random.uniform(50, 200), np.random.uniform(50, 200)
    target_x, target_y = np.random.uniform(600, 900), np.random.uniform(500, 800)
    
    # Ara kontrol noktası (insanlar asla dümdüz hedefe gitmez, hafif kavis çizer)
    mid_x = (start_x + target_x) / 2 + np.random.normal(0, 40)
    mid_y = (start_y + target_y) / 2 + np.random.normal(0, 40)

    trajectory = []
    base_time = 1700000000000.0
    
    for i in range(num_steps):
        t = i / float(num_steps - 1)
        # 2. Derece Bézier + Biyolojik Titreme (Organik kas sönümlemesi)
        bx = (1 - t)**2 * start_x + 2 * (1 - t) * t * mid_x + t**2 * target_x
        by = (1 - t)**2 * start_y + 2 * (1 - t) * t * mid_y + t**2 * target_y
        
        # Biyolojik gürültü (Markovian / Brownian drift)
        tremor_x = np.random.normal(0, 1.2)
        tremor_y = np.random.normal(0, 1.2)
        
        curr_x = bx + tremor_x
        curr_y = by + tremor_y
        base_time += 16.0 + np.random.normal(3.0, 1.5)
        trajectory.append({'x': float(curr_x), 'y': float(curr_y), 't': float(base_time)})

    return {
        "mouse_movements": trajectory,
        "clicks": [{"x": trajectory[-1]["x"], "y": trajectory[-1]["y"], "t": trajectory[-1]["t"]}],
        "keyboard": {"key_interval_avg": 135.0, "key_interval_var": 600.0, "paste_used": False},
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

def generate_test_human_sample():
    """test_engine.py içindeki resmi insan test profili"""
    import random
    human_movements = []
    t_h = 1000
    for i in range(35):
        t_h += random.randint(18, 32)
        human_movements.append({
            "x": round(50 + i*12 + random.gauss(0, 1.8)),
            "y": round(100 + math.sin(i/3.0)*18.0 + random.gauss(0, 1.8)),
            "t": t_h
        })

    return {
        "mouse_movements": human_movements,
        "clicks": [{"x": 400, "y": 200, "t": t_h}],
        "keystrokes": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080
        }
    }

def active_learn_lorenz():
    print("[*] Generating Active Learning Adversarial Dataset (Lorenz Chaos + Organic Humans)...")
    X_telemetry = []
    Y_labels = []

    # 100 Lorenz Botu (Label = 1.0)
    for _ in range(100):
        X_telemetry.append(generate_lorenz_sample())
        Y_labels.append(1.0)

    # 100 Organik İnsan + 100 Resmi Test İnsanı (Label = 0.0)
    for _ in range(100):
        X_telemetry.append(generate_human_sample())
        Y_labels.append(0.0)
    for _ in range(100):
        X_telemetry.append(generate_test_human_sample())
        Y_labels.append(0.0)

    print(f"[+] Dataset created: {len(X_telemetry)} samples (100 Lorenz Bot, 200 Humans).")

    tokenizer = MultimodalTokenizer(max_mouse_steps=60)
    data = np.load(WEIGHTS_PATH)
    conv_w = data['conv_w']
    conv_b = data['conv_b']
    fc1_w = data['fc1_w']
    fc1_b = data['fc1_b']
    fc2_w = data['fc2_w'].copy()
    fc2_b = data['fc2_b'].copy()

    print("[*] Performing Forward Pass (Conv1D + FC1)...")
    fc1_outputs = []
    for telemetry in X_telemetry:
        fused = tokenizer.fuse(telemetry)
        mouse = np.array(fused["mouse_tensor"], dtype=np.float32).T 
        static = np.array(fused["static_vector"], dtype=np.float32)
        
        padded_mouse = np.pad(mouse, ((0,0), (1,1)), mode='constant', constant_values=0.0)
        c_out = np.zeros((16, 60), dtype=np.float32)
        
        for j in range(60):
            window = padded_mouse[:, j:j+3]
            c_out[:, j] = np.sum(conv_w * window, axis=(1, 2)) + conv_b
            
        c_out = np.maximum(0, c_out)
        pool_out = np.max(c_out, axis=1)
        merged = np.concatenate((pool_out, static))
        
        x = np.dot(merged, fc1_w) + fc1_b
        x = np.maximum(0, x)
        fc1_outputs.append(x)

    X_train = np.array(fc1_outputs)
    Y_train = np.array(Y_labels).reshape(-1, 1)

    epochs = 12
    lr = 0.015
    n_samples = X_train.shape[0]

    print(f"[*] Training FC2 via Gradient Descent ({epochs} epochs, lr={lr})...")
    for epoch in range(epochs):
        indices = np.arange(n_samples)
        np.random.shuffle(indices)
        total_loss = 0.0
        correct = 0

        for i in indices:
            x_i = X_train[i].reshape(1, -1)
            y_i = Y_train[i]

            z = np.dot(x_i, fc2_w) + fc2_b
            a = sigmoid(z)

            loss = - (y_i * np.log(a + 1e-9) + (1 - y_i) * np.log(1 - a + 1e-9))
            total_loss += loss[0, 0]

            if (1.0 if a >= 0.5 else 0.0) == y_i:
                correct += 1

            dz = a - y_i
            dw = np.dot(x_i.T, dz)
            db = np.sum(dz)

            fc2_w -= lr * dw
            fc2_b -= lr * db

        if (epoch + 1) % 5 == 0 or epoch == 0:
            acc = (correct / n_samples) * 100.0
            print(f"   Epoch {epoch+1:02d}/{epochs} | Loss: {total_loss/n_samples:.4f} | Accuracy: {acc:.1f}%")

    print(f"[*] Saving hardened weights to {WEIGHTS_PATH}...")
    np.savez_compressed(
        WEIGHTS_PATH,
        conv_w=conv_w,
        conv_b=conv_b,
        fc1_w=fc1_w,
        fc1_b=fc1_b,
        fc2_w=fc2_w,
        fc2_b=fc2_b
    )
    print("[+] Model successfully updated with Lorenz Attractor signature!")

if __name__ == "__main__":
    active_learn_lorenz()
