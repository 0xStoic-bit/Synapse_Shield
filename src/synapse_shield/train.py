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
BASE_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npz")
WEIGHTS_PATH = BASE_WEIGHTS_PATH
DEFAULT_LOCAL_WEIGHTS_PATH = os.path.join(os.getcwd(), "synapse_weights.npz")


def get_active_weights_path() -> str:
    """Returns the path of the weights file to load, prioritizing custom/local over base."""
    env_w = os.environ.get("SYNAPSE_WEIGHTS_PATH")
    if env_w and os.path.exists(env_w):
        return env_w
    if os.path.exists(DEFAULT_LOCAL_WEIGHTS_PATH):
        return DEFAULT_LOCAL_WEIGHTS_PATH
    return BASE_WEIGHTS_PATH


def load_training_data(
    limit: int = 1000,
    include_adversarial: bool = True,
    adversarial_count: int = 20,
    bootstrap: bool = False,
    bootstrap_count: int = 30,
) -> tuple[list, list]:
    """
    Fetches raw telemetry from logs to use as training data.
    Only uses clear, verified edge cases (bot_score >= 90 for Bots, bot_score <= 10 for verified Humans)
    to enforce confident active learning and prevent model poisoning.
    Optionally enriches the dataset with synthetic adversarial bot samples (Adversarial Training).
    If bootstrap=True or database has zero verified human samples, automatically synthesizes
    balanced biological human and adversarial bot telemetries to prevent class collapse.
    """
    X_telemetry = []
    Y_labels = []

    try:
        if os.path.exists(DB_FILE):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT classification, telemetry, threat_type, reasons, features 
                FROM logs 
                WHERE telemetry IS NOT NULL 
                  AND (bot_score >= 90 OR bot_score <= 10)
                ORDER BY id DESC LIMIT ?
            """,
                (limit,),
            )

            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                label_str, telemetry_json, threat_type, reasons_json, features_json = row
                try:
                    telemetry = json.loads(telemetry_json)
                    reasons = json.loads(reasons_json) if reasons_json else []

                    # Model Zehirleme Koruması (Anti-Poisoning Filter):
                    if label_str == "Human":
                        if threat_type and threat_type != "CLEAN_HUMAN":
                            continue
                        if any("farbling" in r.lower() or "capped at 34" in r.lower() for r in reasons):
                            continue
                        moves = telemetry.get("mouse_movements", [])
                        if not isinstance(moves, list) or len(moves) < 5:
                            continue
                        Y_labels.append(0.0)
                    else:
                        if threat_type == "CLEAN_HUMAN":
                            continue
                        Y_labels.append(1.0)

                    X_telemetry.append(telemetry)
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Could not load historical telemetry from database: {e}")

    num_humans = sum(1 for y in Y_labels if y == 0.0)

    # Bootstrap Modu: Sıfır insan verisi veya explicit bootstrap varsa sentetik insan telemetrisi ekle
    if bootstrap or num_humans == 0:
        try:
            from synapse_shield.adversarial import generate_synthetic_human_batch

            count_to_add = max(bootstrap_count, 20)
            human_synth = generate_synthetic_human_batch(count=count_to_add)
            for sample in human_synth:
                X_telemetry.append(sample)
                Y_labels.append(0.0)
            logger.info(f"Bootstrapped {len(human_synth)} synthetic human training samples.")
        except Exception as e:
            logger.warning(f"Synthetic human bootstrap failed: {e}")

    # Düşmansal Eğitim (Adversarial Training): Sentetik matematiksel bot telemetrileri enjekte et
    if include_adversarial or bootstrap:
        try:
            from synapse_shield.adversarial import generate_adversarial_telemetry_batch

            adv_count = max(adversarial_count, bootstrap_count if bootstrap else 20)
            adv_samples = generate_adversarial_telemetry_batch(count=adv_count)
            for sample in adv_samples:
                X_telemetry.append(sample)
                Y_labels.append(1.0)
            logger.info(f"Injected {len(adv_samples)} adversarial bot training samples.")
        except Exception as e:
            logger.warning(f"Adversarial batch generation skipped: {e}")

    return X_telemetry, Y_labels


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def retrain_fc2(
    epochs: int = 5,
    learning_rate: float = 0.01,
    callback=None,
    bootstrap: bool = False,
    output_path: str | None = None,
    overwrite_base: bool = False,
) -> dict:
    """
    Fine-tunes the final FC layer (fc2_w, fc2_b) using Binary Cross Entropy (BCE)
    and Stochastic Gradient Descent (SGD) completely in NumPy.
    Saves weights to ./synapse_weights.npz (or output_path) by default to prevent package pollution.
    """

    def notify(msg: str):
        print(msg)
        if callback:
            try:
                callback(msg)
            except Exception:
                pass

    notify("[*] Synapse Shield Active Learning Pipeline Initiated...")

    # 1. Load data
    X_telemetry, Y_labels = load_training_data(limit=500, include_adversarial=True, bootstrap=bootstrap)

    if len(X_telemetry) < 4:
        notify(f"[-] Not enough training data ({len(X_telemetry)} samples). Need at least 4. Aborting.")
        return {"success": False, "error": "Not enough samples"}

    num_bots = int(sum(Y_labels))
    num_humans = len(Y_labels) - num_bots
    notify(f"[+] Found {len(X_telemetry)} valid samples ({num_bots} Bots, {num_humans} Humans).")

    tokenizer = MultimodalTokenizer(max_mouse_steps=60)

    input_weights = get_active_weights_path()
    notify(f"[*] Loading base model weights from: {input_weights}")

    # Load current weights safely with context manager
    with np.load(input_weights) as data:
        conv_w = np.array(data["conv_w"])
        conv_b = np.array(data["conv_b"])
        fc1_w = np.array(data["fc1_w"])
        fc1_b = np.array(data["fc1_b"])
        fc2_w = np.array(data["fc2_w"])  # shape (16, 1)
        fc2_b = np.array(data["fc2_b"])  # shape (1,)

    # Prepare extracted feature vectors (Forward pass up to FC1)
    notify("[*] Extracting deep features (Forward Pass: Conv1D + MaxPool + FC1)...")

    fc1_outputs = []

    for idx, telemetry in enumerate(X_telemetry):
        fused = tokenizer.fuse(telemetry)

        mouse = np.array(fused["mouse_tensor"], dtype=np.float32).T
        static = np.array(fused["static_vector"], dtype=np.float32)

        padded_mouse = np.pad(mouse, ((0, 0), (1, 1)), mode="constant", constant_values=0.0)
        c_out = np.zeros((16, 60), dtype=np.float32)

        for j in range(60):
            window = padded_mouse[:, j : j + 3]
            c_out[:, j] = np.sum(conv_w * window, axis=(1, 2)) + conv_b

        c_out = np.maximum(0, c_out)
        pool_out = np.max(c_out, axis=1)
        merged = np.concatenate((pool_out, static))

        x = np.dot(merged, fc1_w) + fc1_b
        x = np.maximum(0, x)  # ReLU output of FC1 (shape: 16,)

        fc1_outputs.append(x)

    X_train = np.array(fc1_outputs)  # shape (N, 16)
    Y_train = np.array(Y_labels).reshape(-1, 1)  # shape (N, 1)

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
            x_i = X_train[i].reshape(1, -1)  # (1, 16)
            y_i = Y_train[i]

            # Forward FC2
            z = np.dot(x_i, fc2_w) + fc2_b
            a = sigmoid(z)  # (1, 1)

            # Loss (BCE)
            loss = -(y_i * np.log(a + 1e-9) + (1 - y_i) * np.log(1 - a + 1e-9))
            total_loss += loss[0, 0]

            pred = 1.0 if a >= 0.5 else 0.0
            if pred == y_i:
                correct += 1

            # Backprop on FC2
            dz = a - y_i  # (1, 1)
            dw = np.dot(x_i.T, dz)  # (16, 1)
            db = np.sum(dz)

            # Update weights
            fc2_w -= learning_rate * dw
            fc2_b -= learning_rate * db

        avg_loss = float(total_loss / n_samples)
        accuracy = float((correct / n_samples) * 100.0)
        notify(f"   Epoch {epoch + 1}/{epochs} | Loss: {avg_loss:.4f} | Accuracy: {accuracy:.2f}%")

    target_weights_path = (
        BASE_WEIGHTS_PATH
        if overwrite_base
        else output_path
        if output_path
        else os.environ.get("SYNAPSE_WEIGHTS_PATH", DEFAULT_LOCAL_WEIGHTS_PATH)
    )

    notify(f"[*] Saving updated weights to {target_weights_path}...")
    weights_dir = os.path.dirname(os.path.abspath(target_weights_path))
    if weights_dir and not os.path.exists(weights_dir):
        os.makedirs(weights_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(dir=weights_dir or None, delete=False, suffix=".npz") as tmp_f:
        tmp_name = tmp_f.name
        np.savez_compressed(tmp_f, conv_w=conv_w, conv_b=conv_b, fc1_w=fc1_w, fc1_b=fc1_b, fc2_w=fc2_w, fc2_b=fc2_b)

    try:
        os.replace(tmp_name, target_weights_path)
    except OSError:
        import shutil
        import time

        time.sleep(0.05)
        try:
            shutil.copyfile(tmp_name, target_weights_path)
            os.remove(tmp_name)
        except Exception as copy_err:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            notify(f"❌ Error saving weights: {copy_err}")
            return {"success": False, "error": str(copy_err)}

    notify(f"[+] Model successfully retrained and weights saved to {target_weights_path}!")
    return {"success": True, "samples": len(X_telemetry), "epochs": epochs, "loss": avg_loss, "accuracy": accuracy}


if __name__ == "__main__":
    retrain_fc2()
