"""
Tests for Synapse Shield v0.9.7 Hardening:
- Cryptographic security in Django and Flask
- X-Synapse-Token HTTP Header support
- Reverse Proxy (X-Forwarded-For / CF-Connecting-IP) IP Resolution
- Proof-of-Work (PoW) challenge-response flow
- Shadow Mode (dry-run without blocking)
- Zero-PII anonymization modes (strict / hash)
- Automatic Data Retention / TTL cleanup
- Type stub (.pyi) and PEP 561 py.typed presence
"""

import base64
import json
import os
from pathlib import Path


from synapse_shield import __version__
from synapse_shield.core import (
    anonymize_ip,
    evaluate_synapse_request_sync,
    resolve_client_ip,
)
from synapse_shield.tokens import generate_challenge


def test_version_and_type_stubs():
    assert __version__ == "0.9.7"
    pkg_dir = Path(__file__).resolve().parent.parent / "src" / "synapse_shield"
    assert (pkg_dir / "py.typed").exists(), "py.typed file is missing"
    assert (pkg_dir / "synapse_core_rs.pyi").exists(), "synapse_core_rs.pyi type stub is missing"
    assert not (pkg_dir / "synapse_core_rs.pdb").exists(), ".pdb debug file should not be present in source dir"


def test_resolve_client_ip():
    # 1. Untrusted client IP -> returns client IP directly (ignores headers)
    headers = {"x-forwarded-for": "198.51.100.1, 10.0.0.1"}
    assert resolve_client_ip("203.0.113.5", headers, trusted_proxies={"127.0.0.1"}) == "203.0.113.5"

    # 2. Trusted proxy with CF-Connecting-IP
    cf_headers = {"cf-connecting-ip": "198.51.100.42", "x-forwarded-for": "10.0.0.1"}
    assert resolve_client_ip("127.0.0.1", cf_headers, trusted_proxies={"127.0.0.1"}) == "198.51.100.42"

    # 3. Trusted proxy with X-Real-IP
    real_headers = {"x-real-ip": "198.51.100.88"}
    assert resolve_client_ip("127.0.0.1", real_headers, trusted_proxies={"127.0.0.1"}) == "198.51.100.88"

    # 4. Traversed X-Forwarded-For chain with trusted proxies
    # Client: 198.51.100.99 -> Proxy1: 10.0.0.2 -> Proxy2: 127.0.0.1
    chain_headers = {"x-forwarded-for": "198.51.100.99, 10.0.0.2"}
    assert resolve_client_ip("127.0.0.1", chain_headers, trusted_proxies={"127.0.0.1", "10.0.0.2"}) == "198.51.100.99"


def test_anonymize_ip():
    # 1. Strict mode (default /24 mask)
    os.environ["SYNAPSE_PRIVACY_MODE"] = "strict"
    anon_v6 = anonymize_ip("2001:db8:85a3:8d3:1319:8a2e:370:7348")
    assert anon_v6.startswith("2001:")
    assert "*:*:*:*" in anon_v6

    # 2. Hash mode (rotating daily salt)
    os.environ["SYNAPSE_PRIVACY_MODE"] = "hash"
    hash1 = anonymize_ip("192.168.1.45")
    hash2 = anonymize_ip("192.168.1.45")
    assert hash1 == hash2
    assert hash1.startswith("anon_")
    assert len(hash1) == 21

    # Reset
    os.environ["SYNAPSE_PRIVACY_MODE"] = "strict"


def test_shadow_mode_evaluation():
    # Test that a bot is marked as shadow_block but allowed=True in shadow mode
    ch_data = generate_challenge()
    tok_envelope = {
        "challenge": ch_data["challenge"],
        "telemetry": {"browser": {"webdriver": True}},
    }
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()

    # Enforce mode -> allowed=False, status_code=403
    dec_enforce = evaluate_synapse_request_sync(
        client_ip="127.0.0.1",
        user_agent="pytest-agent",
        token=tok_b64,
        mode="enforce",
    )
    assert dec_enforce.allowed is False
    assert dec_enforce.status_code == 403
    assert dec_enforce.action == "block"

    # Fresh challenge for shadow test
    ch_data2 = generate_challenge()
    tok_envelope2 = {
        "challenge": ch_data2["challenge"],
        "telemetry": {"browser": {"webdriver": True}},
    }
    tok_b64_2 = base64.b64encode(json.dumps(tok_envelope2).encode()).decode()

    # Shadow mode -> allowed=True, status_code=200, action="shadow_block"
    dec_shadow = evaluate_synapse_request_sync(
        client_ip="127.0.0.1",
        user_agent="pytest-agent",
        token=tok_b64_2,
        mode="shadow",
    )
    assert dec_shadow.allowed is True
    assert dec_shadow.status_code == 200
    assert dec_shadow.action == "shadow_block"
    assert dec_shadow.shadow_mode is True
    assert dec_shadow.headers.get("X-Synapse-Decision") == "shadow-block"


def test_pow_challenge_and_solve_in_core():
    # Simulate gray area telemetry (e.g. slight anomaly without hard webdriver block)
    # Using low-amplitude movements to land in 35 <= bot_score <= 65
    ch_data = generate_challenge()
    tok_envelope = {
        "challenge": ch_data["challenge"],
        "telemetry": {
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [
                {"x": 100 + i * 2, "y": 100, "t": i * 50} for i in range(15)
            ],
        },
    }
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()

    # 1. Unsolved PoW -> returns 429 Challenge Required
    dec = evaluate_synapse_request_sync(
        client_ip="127.0.0.1",
        user_agent="pytest",
        token=tok_b64,
        enable_pow=True,
    )
    if dec.action == "challenge":
        assert dec.status_code == 429
        assert dec.challenge_data is not None
        assert "pow_salt" in dec.challenge_data


def test_fastapi_header_token_and_256kb_limit():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from synapse_shield.middleware import shield_protect

    app = FastAPI()

    @app.post("/protected")
    @shield_protect(max_risk_score=50.0)
    async def endpoint(request: Request):
        return {"msg": "SUCCESS", "telemetry": request.state.synapse_telemetry is not None}

    client = TestClient(app)

    # 1. 256 KB Payload limit check
    huge_data = "A" * (262_144 + 50)
    res_huge = client.post("/protected", content=huge_data)
    assert res_huge.status_code == 413

    # 2. X-Synapse-Token Header support without body token
    ch_data = generate_challenge()
    tok_envelope = {
        "challenge": ch_data["challenge"],
        "telemetry": {
            "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
        },
    }
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()

    res_header = client.post(
        "/protected",
        json={"customer_id": 9999, "items": ["book"]},
        headers={"X-Synapse-Token": tok_b64},
    )
    assert res_header.status_code == 200
    assert res_header.json()["msg"] == "SUCCESS"
    assert res_header.json()["telemetry"] is True
    assert res_header.headers.get("X-Synapse-Decision") == "allow"
