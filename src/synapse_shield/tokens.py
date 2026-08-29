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
from typing import Tuple, Dict, Any

# Güvenlik Anahtarı (Production'da .env'den okunabilir)
SECRET_KEY = os.environ.get("SYNAPSE_SECRET_KEY", secrets.token_hex(32)).encode()

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
    signature = hmac.new(SECRET_KEY, f"{nonce}:{ts}".encode(), hashlib.sha256).hexdigest()
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
    expected_sig = hmac.new(SECRET_KEY, f"{nonce}:{ts}".encode(), hashlib.sha256).hexdigest()
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
