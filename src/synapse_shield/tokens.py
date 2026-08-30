"""
Synapse Shield - Cryptographic Token & Replay Attack Defense
Handles HMAC-SHA256 challenge generation, expiration, and single-use nonce tracking.
"""

import os
import hmac
import hashlib
import time
import secrets
import json
import base64
import warnings
import logging
from pathlib import Path
from typing import Tuple, Dict, Any

logger = logging.getLogger("synapse_shield")


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

# Tek kullanımlık Nonce önbelleği (Nonce -> Expiry Timestamp)
USED_NONCES: Dict[str, int] = {}

def generate_challenge(expires_in_sec: int = 60) -> Dict[str, Any]:
    """
    İstemciye HMAC-SHA256 ile imzalanmış tek kullanımlık bir challenge üretir.
    Format: nonce.timestamp.signature
    """
    # Süresi dolan nonceları temizleyerek memory leak'i önle
    now = int(time.time())
    expired_nonces = [k for k, exp in USED_NONCES.items() if exp < now]
    for k in expired_nonces:
        del USED_NONCES[k]

    nonce = secrets.token_hex(16)
    ts = now
    signature = hmac.HMAC(SECRET_KEY, f"{nonce}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    challenge = f"{nonce}.{ts}.{signature}"
    return {
        "challenge": challenge,
        "expires_in": expires_in_sec
    }

def verify_and_consume_token(token_str: str) -> Tuple[bool, str, Dict[str, Any]]:
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

    now = int(time.time())
    # 2. Zaman Aşımı Kontrolü (60 saniye)
    if now - ts > 60:
        return False, f"Token zaman aşımına uğradı ({now - ts}sn > 60sn)", {}
    if ts - now > 5:
        return False, "Gelecek zaman damgası (Saat manipülasyonu)", {}

    # 3. Süresi Dolan Nonce'ları Temizle
    expired_nonces = [k for k, exp in USED_NONCES.items() if exp < now]
    for k in expired_nonces:
        del USED_NONCES[k]

    # 4. Replay Attack (Yeniden Oynatma) Kontrolü
    if nonce in USED_NONCES:
        return False, "Yeniden Oynatma Saldırısı: Bu token zaten kullanıldı! (Replay Detected)", {}

    # Nonce'ı 120 saniyeliğine 'kullanıldı' olarak işaretle
    USED_NONCES[nonce] = now + 120
    return True, "Geçerli", telemetry
