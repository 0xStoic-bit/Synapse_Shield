"""
Synapse Shield - Active Learning Pipeline
Zero-Dependency NumPy fine-tuning for the 1D-CNN Dense layers.
"""

import json
import logging
import os
import sqlite3
import tempfile

import numpy as np

from synapse_shield.features import MultimodalTokenizer

logger = logging.getLogger("synapse_shield.train")

DB_FILE = os.environ.get("SYNAPSE_DB_PATH", os.path.join(tempfile.gettempdir(), "synapse_shield.db"))
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npz")

def load_training_data(limit=1000, include_adversarial: bool = True, adversarial_count: int = 20) -> tuple[list, list]:
    """
    Fetches raw telemetry from logs to use as training data.
    Only uses clear, verified edge cases (bot_score >= 90 for Bots, bot_score <= 10 for verified Humans)
    to enforce confident active learning and prevent model poisoning.
    Optionally enriches the dataset with synthetic adversarial bot samples (Adversarial Training).
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT classification, telemetry, threat_type, reasons, features 
            FROM logs 
            WHERE telemetry IS NOT NULL 
              AND (bot_score >= 90 OR bot_score <= 10)
            ORDER BY id DESC LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        X_telemetry = []
        Y_labels = []
        
        for row in rows:
            label_str, telemetry_json, threat_type, reasons_json, features_json = row
            try:
                telemetry = json.loads(telemetry_json)
                reasons = json.loads(reasons_json) if reasons_json else []
                
                # Model Zehirleme Koruması (Anti-Poisoning Filter):
                if label_str == "Human":
                    # İnsan verisi için doğrulanmış organik hareket şartı
                    if threat_type and threat_type != "CLEAN_HUMAN":
                        continue
                    # Farbling veya geçici override ile skoru düşürülmüş kayıtları havuza alma
                    if any("farbling" in r.lower() or "capped at 34" in r.lower() for r in reasons):
                        continue
                    # Yeterli fare hareketi olmayanları insan zannetme
                    moves = telemetry.get("mouse_movements", [])
                    if not isinstance(moves, list) or len(moves) < 5:
                        continue
                    Y_labels.append(0.0)
                else:
                    # Bot verisi için
                    if threat_type == "CLEAN_HUMAN":
                        continue
                    Y_labels.append(1.0)

                X_telemetry.append(telemetry)
            except Exception:
                continue
                
        # Düşmansal Eğitim (Adversarial Training): Sentetik matematiksel bot telemetrileri enjekte et
        if include_adversarial:
            try:
                from synapse_shield.adversarial import generate_adversarial_telemetry_batch
                adv_samples = generate_adversarial_telemetry_batch(count=adversarial_count)
                for sample in adv_samples:
                    X_telemetry.append(sample)
                    Y_labels.append(1.0)
            except Exception as e:
                logger.warning(f"Adversarial batch generation skipped: {e}")

        return X_telemetry, Y_labels
    except Exception as e:
        print(f"[Error] Failed to load training data from SQLite: {e}")
        if include_adversarial:
            try:
                from synapse_shield.adversarial import generate_adversarial_telemetry_batch
                adv_samples = generate_adversarial_telemetry_batch(count=adversarial_count)
                return adv_samples, [1.0] * len(adv_samples)
            except Exception:
                pass
        return [], []

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

def retrain_fc2(epochs=5, learning_rate=0.01, callback=None) -> dict:
    """
    Fine-tunes the final FC layer (fc2_w, fc2_b) using Binary Cross Entropy (BCE)
    and Stochastic Gradient Descent (SGD) completely in NumPy.
    """
    def notify(msg: str):
        print(msg)
        if callback:
            try:
                callback(msg)
            except Exception:
                pass

    notify("[*] Synapse Shield Active Learning Pipeline Initiated...")
    
    if not os.path.exists(WEIGHTS_PATH):
        err = f"❌ Error: Model weights not found at {WEIGHTS_PATH}"
        notify(err)
        return {"success": False, "error": err}

    # Load data
    notify("[*] Loading high-confidence telemetry logs from database...")
    X_telemetry, Y_labels = load_training_data(limit=1000)
    
    if len(X_telemetry) < 10:
        err = "[!] Not enough high-confidence data for retraining. At least 10 samples required."
        notify(err)
        return {"success": False, "error": err}
        
    notify(f"[+] Found {len(X_telemetry)} valid samples ({int(sum(Y_labels))} Bots, {len(Y_labels) - int(sum(Y_labels))} Humans).")
    
    tokenizer = MultimodalTokenizer(max_mouse_steps=60)
    
    # Load current weights safely with context manager
    with np.load(WEIGHTS_PATH) as data:
        conv_w = np.array(data['conv_w'])
        conv_b = np.array(data['conv_b'])
        fc1_w = np.array(data['fc1_w'])
        fc1_b = np.array(data['fc1_b'])
        fc2_w = np.array(data['fc2_w']) # shape (16, 1)
        fc2_b = np.array(data['fc2_b']) # shape (1,)
    
    # Prepare extracted feature vectors (Forward pass up to FC1)
    notify("[*] Extracting deep features (Forward Pass: Conv1D + MaxPool + FC1)...")
    
    fc1_outputs = []
    
    for idx, telemetry in enumerate(X_telemetry):
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
        x = np.maximum(0, x) # ReLU output of FC1 (shape: 16,)
        
        fc1_outputs.append(x)
        
    X_train = np.array(fc1_outputs) # shape (N, 16)
    Y_train = np.array(Y_labels).reshape(-1, 1) # shape (N, 1)
    
    notify(f"[*] Starting Fine-Tuning (Transfer Learning on FC2, {epochs} epochs, lr={learning_rate})...")
    
    n_samples = X_train.shape[0]
    avg_loss = 0.0
    accuracy = 0.0
    
    # SGD Training Loop
    for epoch in range(epochs):
        total_loss = 0.0
        correct = 0
        
        # Shuffle
        indices = np.arange(n_samples)
        np.random.shuffle(indices)
        
        for i in indices:
            x_i = X_train[i].reshape(1, -1) # (1, 16)
            y_i = Y_train[i]
            
            # Forward FC2
            z = np.dot(x_i, fc2_w) + fc2_b
            a = sigmoid(z) # (1, 1)
            
            # Loss (BCE)
            loss = - (y_i * np.log(a + 1e-9) + (1 - y_i) * np.log(1 - a + 1e-9))
            total_loss += loss[0, 0]
            
            pred = 1.0 if a >= 0.5 else 0.0
            if pred == y_i:
                correct += 1
                
            # Backprop on FC2
            dz = a - y_i # (1, 1)
            dw = np.dot(x_i.T, dz) # (16, 1)
            db = np.sum(dz)
            
            # Update weights
            fc2_w -= learning_rate * dw
            fc2_b -= learning_rate * db
            
        avg_loss = float(total_loss / n_samples)
        accuracy = float((correct / n_samples) * 100.0)
        notify(f"   Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.4f} | Accuracy: {accuracy:.2f}%")
        
    notify(f"[*] Saving updated weights to {WEIGHTS_PATH}...")
    weights_dir = os.path.dirname(os.path.abspath(WEIGHTS_PATH))
    
    with tempfile.NamedTemporaryFile(dir=weights_dir, delete=False, suffix=".npz") as tmp_f:
        tmp_name = tmp_f.name
        np.savez_compressed(
            tmp_f,
            conv_w=conv_w,
            conv_b=conv_b,
            fc1_w=fc1_w,
            fc1_b=fc1_b,
            fc2_w=fc2_w,
            fc2_b=fc2_b
        )
    
    try:
        os.replace(tmp_name, WEIGHTS_PATH)
    except OSError:
        import shutil
        import time
        time.sleep(0.05)
        try:
            shutil.copyfile(tmp_name, WEIGHTS_PATH)
            os.remove(tmp_name)
        except Exception as copy_err:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            notify(f"❌ Error saving weights: {copy_err}")
            return {"success": False, "error": str(copy_err)}

    notify("[+] Model successfully retrained and weights updated!")
    return {
        "success": True,
        "samples": len(X_telemetry),
        "epochs": epochs,
        "loss": avg_loss,
        "accuracy": accuracy
    }

if __name__ == "__main__":
    retrain_fc2()
