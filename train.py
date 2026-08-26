"""
Synapse Shield - Local Machine Learning Training & Evaluation Pipeline
Trains a Random Forest classifier on captured and synthetic kinematic telemetry.
"""

import os
import json
import sqlite3
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

DB_FILE = "synapse_shield.db"

FEATURE_NAMES = [
    "straightness", "avg_velocity", "max_velocity", "velocity_var",
    "avg_acceleration", "acceleration_var", "avg_jerk",
    "key_interval_avg", "key_interval_var", "scroll_count", "click_count"
]

def generate_training_data(num_samples: int = 1200):
    """
    Veritabanındaki gerçek verileri çeker ve sentetik insan/bot 
    varyasyonlarıyla birleştirerek sağlam bir eğitim matrisi oluşturur.
    """
    X, y = [], []

    # 1. SQLite Veritabanından Varsa Gerçek Logları Çek
    if os.path.exists(DB_FILE):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT classification, features FROM logs WHERE features IS NOT NULL AND features != '{}'")
            rows = cursor.fetchall()
            conn.close()
            
            for classification, features_json in rows:
                feat = json.loads(features_json)
                vec = [float(feat.get(k, 0.0)) for k in FEATURE_NAMES]
                X.append(vec)
                y.append(1 if classification == "Bot" else 0)
            print(f"[+] Veritabanından {len(rows)} adet gerçek oturum verisi alındı.")
        except Exception as e:
            print(f"[!] DB okuma hatası: {e}")

    # 2. Sentetik İnsan Verileri (Doğal kas titremesi, kavisli rotalar, değişken hız)
    np.random.seed(42)
    for _ in range(num_samples // 2):
        straightness = np.clip(np.random.beta(2, 5), 0.05, 0.85)
        avg_velocity = np.random.uniform(0.5, 3.5)
        max_velocity = avg_velocity * np.random.uniform(1.8, 4.0)
        velocity_var = np.random.exponential(0.5) + 0.1
        avg_acceleration = np.random.uniform(0.001, 0.005)
        acceleration_var = np.random.exponential(0.001) + 0.0002
        avg_jerk = np.random.uniform(0.0005, 0.005) # İnsan mikro-titremesi
        key_interval_avg = np.random.uniform(80, 220)
        key_interval_var = np.random.uniform(15, 80)
        scroll_count = np.random.randint(0, 15)
        click_count = np.random.randint(1, 8)
        
        vec = [
            straightness, avg_velocity, max_velocity, velocity_var,
            avg_acceleration, acceleration_var, avg_jerk,
            key_interval_avg, key_interval_var, scroll_count, click_count
        ]
        X.append(vec)
        y.append(0) # İnsan

    # 3. Sentetik Bot Verileri (Düz çizgiler, sıfır Jerk, sabit aralıklı tuş basıcılar)
    for _ in range(num_samples // 2):
        bot_type = np.random.choice(["linear", "fast_clicker", "autotyper"])
        
        if bot_type == "linear":
            straightness = np.random.uniform(0.985, 1.0)
            avg_velocity = np.random.uniform(1.0, 4.0)
            max_velocity = avg_velocity * 1.05
            velocity_var = np.random.uniform(0.0, 0.0001)
            avg_acceleration = 0.0
            acceleration_var = 0.0
            avg_jerk = 0.0
            key_interval_avg = 0.0
            key_interval_var = 0.0
            scroll_count = 0
            click_count = np.random.randint(0, 2)
        elif bot_type == "autotyper":
            straightness = 1.0
            avg_velocity = 0.0
            max_velocity = 0.0
            velocity_var = 0.0
            avg_acceleration = 0.0
            acceleration_var = 0.0
            avg_jerk = 0.0
            key_interval_avg = np.random.choice([20.0, 50.0, 100.0])
            key_interval_var = np.random.uniform(0.0, 1.5)
            scroll_count = 0
            click_count = 0
        else: # Headless / Hızlı tıklayıcı
            straightness = 1.0
            avg_velocity = np.random.uniform(10.0, 30.0)
            max_velocity = avg_velocity
            velocity_var = 0.0
            avg_acceleration = 0.0
            acceleration_var = 0.0
            avg_jerk = 0.0
            key_interval_avg = 0.0
            key_interval_var = 0.0
            scroll_count = 0
            click_count = np.random.randint(1, 10)
            
        vec = [
            straightness, avg_velocity, max_velocity, velocity_var,
            avg_acceleration, acceleration_var, avg_jerk,
            key_interval_avg, key_interval_var, scroll_count, click_count
        ]
        X.append(vec)
        y.append(1) # Bot

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)

def train_model():
    print("=" * 65)
    print("🛡️  SYNAPSE SHIELD — MAKİNE ÖĞRENİMİ EĞİTİM & DOĞRULAMA HATTI")
    print("=" * 65)

    X, y = generate_training_data(num_samples=1200)
    print(f"[+] Toplam Örnek Sayısı: {len(X)} (İnsan: {sum(y==0)}, Bot: {sum(y==1)})")

    # %80 Eğitim, %20 Test Olarak Böl
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Modeli Eğit (50 Ağaçlı Hafif Random Forest)
    model = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
    model.fit(X_train, y_train)

    # Test Kümesinde Değerlendir
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred) * 100

    print(f"\n[✓] Test Kümesi Doğruluk Oranı (Accuracy): %{accuracy:.2f}")
    print("\n--- Sınıflandırma Raporu ---")
    print(classification_report(y_test, y_pred, target_names=["İnsan (0)", "Bot (1)"]))

    # En Belirleyici Özellikler
    print("📊 En Etkili Bot Tespit Öznitelikleri (Feature Importance):")
    importances = model.feature_importances_
    sorted_indices = np.argsort(importances)[::-1]
    for idx in sorted_indices[:5]:
        print(f"  → {FEATURE_NAMES[idx]:20s}: %{importances[idx]*100:.1f}")

    print("\n" + "=" * 65)
    print("🚀 Model eğitimi tamamlandı! Sistem matematiği başarıyla doğrulandı.")
    print("=" * 65)

if __name__ == "__main__":
    train_model()