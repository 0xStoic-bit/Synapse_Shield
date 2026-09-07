"""
Synapse Shield - Active Learning Pipeline
Zero-Dependency NumPy fine-tuning for the 1D-CNN Dense layers.
"""

import os
import sqlite3
import numpy as np
import tempfile
import json
import logging
from typing import Tuple

from synapse_shield.features import MultimodalTokenizer

logger = logging.getLogger("synapse_shield.train")

DB_FILE = os.environ.get("SYNAPSE_DB_PATH", os.path.join(tempfile.gettempdir(), "synapse_shield.db"))
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npz")

def load_training_data(limit=1000) -> Tuple[list, list]:
    """
    Fetches raw telemetry from logs to use as training data.
    Only uses clear edge cases (bot_score > 90 for Bots, bot_score < 10 for Humans)
    to enforce confident active learning.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT classification, telemetry 
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
            label_str, telemetry_json = row
            try:
                telemetry = json.loads(telemetry_json)
                X_telemetry.append(telemetry)
                Y_labels.append(1.0 if label_str == "Bot" else 0.0)
            except Exception:
                continue
                
        return X_telemetry, Y_labels
    except Exception as e:
        print(f"[Error] Failed to load training data from SQLite: {e}")
        return [], []

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

def retrain_fc2(epochs=5, learning_rate=0.01):
    """
    Fine-tunes the final FC layer (fc2_w, fc2_b) using Binary Cross Entropy (BCE)
    and Stochastic Gradient Descent (SGD) completely in NumPy.
    """
    print(f"[*] Synapse Shield Active Learning Pipeline Initiated...")
    
    if not os.path.exists(WEIGHTS_PATH):
        print(f"❌ Error: Model weights not found at {WEIGHTS_PATH}")
        return

    # Load data
    print("[*] Loading high-confidence telemetry logs from database...")
    X_telemetry, Y_labels = load_training_data(limit=1000)
    
    if len(X_telemetry) < 10:
        print("[!] Not enough high-confidence data for retraining. At least 10 samples required.")
        return
        
    print(f"[+] Found {len(X_telemetry)} valid samples ({int(sum(Y_labels))} Bots, {len(Y_labels) - int(sum(Y_labels))} Humans).")
    
    tokenizer = MultimodalTokenizer(max_mouse_steps=60)
    
    # Load current weights
    data = np.load(WEIGHTS_PATH)
    conv_w = data['conv_w']
    conv_b = data['conv_b']
    fc1_w = data['fc1_w']
    fc1_b = data['fc1_b']
    fc2_w = data['fc2_w'] # shape (16, 1)
    fc2_b = data['fc2_b'] # shape (1,)
    
    # Prepare extracted feature vectors (Forward pass up to FC1)
    print("[*] Extracting deep features (Forward Pass: Conv1D + MaxPool + FC1)...")
    
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
    
    print("[*] Starting Fine-Tuning (Transfer Learning on FC2)...")
    
    n_samples = X_train.shape[0]
    
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
            
        avg_loss = total_loss / n_samples
        accuracy = (correct / n_samples) * 100.0
        print(f"   Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.4f} | Accuracy: {accuracy:.2f}%")
        
    print(f"[*] Saving updated weights to {WEIGHTS_PATH}...")
    np.savez_compressed(
        WEIGHTS_PATH,
        conv_w=conv_w,
        conv_b=conv_b,
        fc1_w=fc1_w,
        fc1_b=fc1_b,
        fc2_w=fc2_w,
        fc2_b=fc2_b
    )
    print("[+] Model successfully retrained and weights updated!")

if __name__ == "__main__":
    retrain_fc2()
