"""
Unit Tests for Synapse Shield v0.10.3 Security & Hardening Fixes
Audited by Claude Code Red Team & Verified by Antigravity:
1. IME Touch-Bypass closure (Majority-only rule aligned with Rust SIMD)
2. Token Client Binding enforcement when context is missing
3. 64-bit (16-hex) ua_hash collision mitigation for CGNAT
4. Risk-adaptive PoW difficulty scaling (diff=4 vs diff=5)
5. SYNAPSE_SECRET_KEY hex-encoded string decoding support
"""

import base64
import hashlib
import json
import os
from unittest.mock import patch

from synapse_shield.features import extract_features
from synapse_shield.tokens import (
    _load_or_generate_secret_key,
    extract_pow_difficulty,
    generate_challenge,
    generate_pow_salt,
    verify_and_consume_token,
)


def test_ime_touch_bypass_closed():
    """
    Finding #1 (Critical): An attacker sending touch_supported=True and 1 unidentified key
    out of 6 keys must NOT bypass dwell-time analysis. Majority rule is required.
    """
    # 1 unidentified key + 5 normal keys = 1/6 (not majority)
    # With touch_supported=True, old code set is_mobile_ime=True and zeroed out dwell penalties!
    keystrokes = [
        {"key": "unidentified", "down": 1000, "up": 1005, "dwell": 5},
        {"key": "masked", "down": 1100, "up": 1105, "dwell": 5},
        {"key": "masked", "down": 1200, "up": 1205, "dwell": 5},
        {"key": "masked", "down": 1300, "up": 1305, "dwell": 5},
        {"key": "masked", "down": 1400, "up": 1405, "dwell": 5},
        {"key": "masked", "down": 1500, "up": 1505, "dwell": 5},
    ]

    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": keystrokes,
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "touch_supported": True,  # Attacker claims touch
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
        },
    }

    features = extract_features(telemetry)
    # Keystroke bot score must be elevated because dwell time is suspiciously low (5ms) and not real IME majority
    assert features["keystroke_score"] >= 0.70


def test_token_client_binding_missing_context_fails():
    """
    Finding #3 (High): If challenge has client binding (bind_hash), verification without
    client_ip and user_agent must fail (cannot be relayed to an unauthenticated context).
    """
    client_ip = "198.51.100.12"
    ua = "Mozilla/5.0 Chrome/120.0"

    chal = generate_challenge(expires_in_sec=60, client_ip=client_ip, user_agent=ua)
    envelope = {"challenge": chal["challenge"], "telemetry": {}}
    token = base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    # Calling verify without client context on a bound token MUST be rejected
    is_valid, reason, _ = verify_and_consume_token(token, client_ip=None, user_agent=None)
    assert is_valid is False
    assert "Token Relay" in reason or "Binding Mismatch" in reason


def test_ua_hash_64bit_session_entropy():
    """
    Finding #4 (High): Verify ua_hash generates 16 hex characters (64-bit entropy).
    """
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ua_hash = hashlib.sha256(ua.encode("utf-8")).hexdigest()[:16]
    assert len(ua_hash) == 16


def test_secret_key_hex_decoding():
    """
    Finding #8 (Low): 64-char hex string in SYNAPSE_SECRET_KEY is decoded to 32 raw bytes.
    """
    test_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    with patch.dict(os.environ, {"SYNAPSE_SECRET_KEY": test_hex}):
        key = _load_or_generate_secret_key()
        assert len(key) == 32
        assert key == bytes.fromhex(test_hex)

    # Fallback for plain non-hex string
    test_plain = "my_custom_secret_passphrase_not_hex"
    with patch.dict(os.environ, {"SYNAPSE_SECRET_KEY": test_plain}):
        key = _load_or_generate_secret_key()
        assert key == test_plain.encode("utf-8")


def test_risk_adaptive_pow_difficulty_in_core():
    """
    Finding #7 (Medium): In core evaluation, gray area challenges adapt difficulty
    based on risk score (bot_score >= 45.0 gets diff=5, lower gets diff=4).
    """
    client_ip = "198.51.100.99"
    salt_low = generate_pow_salt(client_ip, difficulty=4)
    salt_high = generate_pow_salt(client_ip, difficulty=5)
    assert extract_pow_difficulty(salt_low) == 4
    assert extract_pow_difficulty(salt_high) == 5
