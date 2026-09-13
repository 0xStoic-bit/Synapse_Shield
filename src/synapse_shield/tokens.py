"""
Synapse Shield - Cryptographic Token & Replay Attack Defense
Handles HMAC-SHA256 challenge generation, expiration, and single-use nonce tracking.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

from synapse_shield.storage import get_storage

logger = logging.getLogger("synapse_shield")

DB_FILE = os.environ.get("SYNAPSE_DB_PATH", os.path.join(tempfile.gettempdir(), "synapse_shield.db"))


def _load_or_generate_secret_key() -> bytes:
    """
    Kalıcı SECRET_KEY yükleme stratejisi: ENV > dosya > yeni oluştur + uyar.
    Production ortamında SYNAPSE_SECRET_KEY env variable'ı zorunlu olarak ayarlanmalıdır.
    """
    # 1. Öncelik: Ortam değişkeni
    env_key = os.environ.get("SYNAPSE_SECRET_KEY")
    if env_key:
        return env_key.encode()

    # 2. Öncelik: Kalıcı dosya fallback
    key_dir = Path.home() / ".synapse_shield"
    key_file = key_dir / "secret.key"
    if key_file.exists():
        logger.info("SECRET_KEY dosyadan okunuyor: %s", key_file)
        return key_file.read_bytes()

    # 3. Yeni key oluştur ve dosyaya yaz
    new_key = secrets.token_hex(32)
    try:
        key_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_text(new_key)
        # Windows'da chmod 0o600 desteklenmeyebilir, hata yutulur
        try:
            key_file.chmod(0o600)
        except OSError:
            pass
        logger.info("Yeni SECRET_KEY oluşturuldu ve kaydedildi: %s", key_file)
    except OSError as e:
        logger.warning("SECRET_KEY dosyaya yazılamadı (%s). Geçici key kullanılıyor.", e)

    warnings.warn(
        "SYNAPSE_SECRET_KEY env variable tanımlı değil! "
        f"Geçici key üretildi ve '{key_file}' dosyasına yazıldı. "
        "Production ortamında SYNAPSE_SECRET_KEY env variable'ı zorunlu olarak ayarlanmalıdır.",
        UserWarning,
        stacklevel=2,
    )
    return new_key.encode()


SECRET_KEY = _load_or_generate_secret_key()

def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS used_nonces (
            nonce TEXT PRIMARY KEY,
            expires_at INTEGER
        )
    """)
    conn.commit()

def _cleanup_expired_nonces():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        _ensure_table(conn)
        now = int(time.time())
        conn.execute("DELETE FROM used_nonces WHERE expires_at < ?", (now,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Nonce cleanup failed: {e}")

def generate_challenge(expires_in_sec: int = 60) -> dict[str, Any]:
    """
    İstemciye HMAC-SHA256 ile imzalanmış tek kullanımlık bir challenge üretir.
    Format: nonce.timestamp.signature
    """
    # Süresi dolan nonceları temizleyerek db şişmesini önle
    _cleanup_expired_nonces()
    
    now_ms = int(time.time() * 1000)

    nonce = secrets.token_hex(16)
    ts = now_ms
    signature = hmac.HMAC(SECRET_KEY, f"{nonce}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    challenge = f"{nonce}.{ts}.{signature}"
    return {
        "challenge": challenge,
        "expires_in": expires_in_sec
    }

def verify_and_consume_token(token_str: str) -> tuple[bool, str, dict[str, Any]]:
    """
    İstemciden gelen token'ı çözer; imza, zaman aşımı ve Replay Attack kontrolü yapar.
    Returns: (is_valid: bool, reason: str, telemetry: dict)
    """
    try:
        raw_json = base64.b64decode(token_str.encode('utf-8')).decode('utf-8')
        payload = json.loads(raw_json)
    except Exception:
        return False, "Geçersiz token formatı / Base64 hatası", {}

    challenge = payload.get("challenge", "")
    telemetry = payload.get("telemetry", {})
    
    parts = challenge.split(".")
    if len(parts) != 3:
        return False, "Bozuk challenge yapısı", {}

    nonce, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False, "Geçersiz zaman damgası", {}

    # 1. Kriptografik HMAC İmzasını Doğrula
    expected_sig = hmac.HMAC(SECRET_KEY, f"{nonce}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False, "Sahte challenge imzası (Forged Signature)", {}

    now_ms = int(time.time() * 1000)
    elapsed_ms = now_ms - ts
    elapsed_sec = elapsed_ms / 1000.0

    # 2. Zaman Aşımı ve Manipülasyon Kontrolü (Milisaniye Hassasiyetinde)
    if elapsed_sec > 60.0:
        return False, f"Token zaman aşımına uğradı ({elapsed_sec:.1f}sn > 60sn)", {}
    if ts - now_ms > 5000:
        return False, "Gelecek zaman damgası (Saat manipülasyonu)", {}
    min_elapsed = int(os.environ.get("SYNAPSE_MIN_ELAPSED_MS", 1500))
    if elapsed_ms < min_elapsed:
        return False, f"Zaman manipülasyonu (Humanly Impossible Speed): elapsed={elapsed_sec:.2f}s", {}

    # 2.5 Time Travel Kontrolü (DeepSeek Advanced Bypass Koruması)
    # Eğer bot 1.6 saniye bekleyip, içine 3 saniyelik telemetri sığdırmaya çalışırsa yakalanır!
    elapsed_time = elapsed_sec
    try:
        events = telemetry.get("mouse_movements", []) + telemetry.get("keystrokes", []) + telemetry.get("clicks", []) + telemetry.get("scrolls", [])
        if events:
            timestamps = [e.get("t", 0) for e in events if isinstance(e, dict) and "t" in e]
            if timestamps:
                telemetry_duration_sec = (max(timestamps) - min(timestamps)) / 1000.0
                # Telemetrideki olayların süresi, dünyadaki geçen süreden büyük olamaz (0.5s network gecikme payı)
                if min_elapsed > 0 and telemetry_duration_sec > elapsed_time + 0.5:
                    return False, f"Zaman yolculuğu tespit edildi (Time Travel Bot): Telemetri {telemetry_duration_sec:.1f}s sürüyor ancak token {elapsed_time:.1f}s önce alındı!", {}
    except Exception as e:
        logger.warning(f"Telemetry time travel check failed: {e}")

    # 3. Süresi Dolan Nonce'ları Temizle
    _cleanup_expired_nonces()

    # 4. Replay Attack (Yeniden Oynatma) Kontrolü (SQLite veya Dağıtık Redis)
    is_valid_nonce = get_storage().consume_nonce(nonce, ttl_sec=120)
    if not is_valid_nonce:
        return False, "Yeniden Oynatma Saldırısı: Bu token zaten kullanıldı! (Replay Detected)", {}

    return True, "Geçerli", telemetry

def generate_pow_salt() -> str:
    """
    PoW (Proof of Work) için HMAC imzalı salt üretir.
    Format: salt_hex.timestamp.signature
    """
    salt_hex = secrets.token_hex(8)
    ts = int(time.time() * 1000)
    signature = hmac.HMAC(SECRET_KEY, f"{salt_hex}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    return f"{salt_hex}.{ts}.{signature}"

def verify_pow_salt(signed_salt: str) -> bool:
    """
    İstemciden gelen imzalı salt'ın geçerliliğini ve süresini kontrol eder (Son 60 saniye).
    """
    parts = signed_salt.split(".")
    if len(parts) != 3:
        return False
    salt_hex, ts_str, sig = parts
    
    try:
        ts = int(ts_str)
    except ValueError:
        return False
        
    expected_sig = hmac.HMAC(SECRET_KEY, f"{salt_hex}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
        
    now_ms = int(time.time() * 1000)
    elapsed_sec = (now_ms - ts) / 1000.0
    # 60 saniyeden eskiyse veya gelecek zamandaysa reddet
    return not (elapsed_sec > 60.0 or elapsed_sec < -5.0)
