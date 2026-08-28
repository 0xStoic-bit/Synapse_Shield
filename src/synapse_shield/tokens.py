"""
Synapse Shield - Cryptographic Token & Replay Attack Defense
Handles HMAC-SHA256 challenge generation, expiration, and single-use nonce tracking.
"""

import hmac
import hashlib
import time
import secrets
import json
import base64
import os
import threading
from typing import Tuple, Dict, Any

# Güvenlik Anahtarı (SYNAPSE_SHIELD_SECRET_KEY ortam değişkeninden okunur)
_ENV_SECRET = os.environ.get("SYNAPSE_SHIELD_SECRET_KEY") or os.environ.get("SYNAPSE_SECRET_KEY")
SECRET_KEY_IS_EPHEMERAL = not bool(_ENV_SECRET)
SECRET_KEY = _ENV_SECRET.encode("utf-8") if _ENV_SECRET else secrets.token_bytes(32)

TOKEN_TTL_SEC = 60
_NONCE_RETENTION_SEC = 120


class InMemoryNonceStore:
    """Tek kullanımlık Nonce önbelleği (Nonce -> Expiry Timestamp). Süreç-içi ve thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._used: Dict[str, int] = {}

    def _purge_locked(self, now: int) -> None:
        for key in [k for k, exp in self._used.items() if exp < now]:
            del self._used[key]

    def seen(self, nonce: str) -> bool:
        now = int(time.time())
        with self._lock:
            self._purge_locked(now)
            return nonce in self._used

    def add(self, nonce: str, ttl: int = _NONCE_RETENTION_SEC) -> None:
        with self._lock:
            self._used[nonce] = int(time.time()) + ttl


_nonce_store: Any = InMemoryNonceStore()
USED_NONCES: Dict[str, int] = _nonce_store._used


def set_nonce_store(store: Any) -> None:
    """Nonce deposunu değiştir; `seen(nonce)` ve `add(nonce, ttl)` sağlamalıdır."""
    global _nonce_store, USED_NONCES
    _nonce_store = store
    USED_NONCES = getattr(store, "_used", {})


def generate_challenge(expires_in_sec: int = TOKEN_TTL_SEC) -> Dict[str, Any]:
    """
    İstemciye HMAC-SHA256 ile imzalanmış tek kullanımlık bir challenge üretir.
    Format: nonce.timestamp.signature
    """
    nonce = secrets.token_hex(16)
    ts = int(time.time())
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
    if now - ts > TOKEN_TTL_SEC:
        return False, f"Token zaman aşımına uğradı ({now - ts}sn > {TOKEN_TTL_SEC}sn)", {}
    if ts - now > 5:
        return False, "Gelecek zaman damgası (Saat manipülasyonu)", {}

    # 3. Replay Attack (Yeniden Oynatma) Kontrolü
    if _nonce_store.seen(nonce):
        return False, "Yeniden Oynatma Saldırısı: Bu token zaten kullanıldı! (Replay Detected)", {}

    # 4. Nonce'ı 'kullanıldı' olarak işaretle
    _nonce_store.add(nonce, _NONCE_RETENTION_SEC)
    return True, "Geçerli", telemetry
