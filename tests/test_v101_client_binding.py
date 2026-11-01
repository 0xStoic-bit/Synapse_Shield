"""
Unit and Integration Tests for Synapse Shield v0.10.1:
1. Cryptographic Client Network Binding (IP Subnet & User-Agent Binding)
2. Token Relay & Harvesting Attack Mitigation
3. Subnet Roaming Tolerance (/24 IPv4 & /64 IPv6)
4. SQLite Worker Thread-Pool Leak-Free Cleanup
5. Synapse Shield Doctor System Diagnostic Audit
"""

import base64
import json
import os
import sqlite3
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from synapse_shield.doctor import run_doctor
from synapse_shield.main import _cleanup_connections, _open_connections, app, get_connection
from synapse_shield.tokens import (
    compute_client_binding_hash,
    generate_challenge,
    get_client_subnet,
    verify_and_consume_token,
)


def _make_token(challenge_str: str, duration_ms: int = 1600) -> str:
    now_base = 1000
    pts = [{"x": 100 + i * 5, "y": 150 + (i % 4) * 3, "t": now_base + i * 40} for i in range(15)]
    telemetry = {
        "mouse_movements": pts,
        "clicks": [{"x": pts[-1]["x"], "y": pts[-1]["y"], "t": now_base + 1550}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
        },
    }
    envelope = {"challenge": challenge_str, "telemetry": telemetry}
    return base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# 1. Challenge Format & Subnet Masking Tests
# ---------------------------------------------------------------------------


def test_subnet_masking():
    # IPv4 /24 mask
    assert get_client_subnet("192.168.1.45") == "192.168.1.0"
    assert get_client_subnet("10.0.5.200") == "10.0.5.0"
    # IPv6 /64 mask
    ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
    assert get_client_subnet(ipv6) == "2001:db8:85a3::"
    # Invalid IP fallback
    assert get_client_subnet("localhost_custom") == "localhost_custom"
    assert get_client_subnet(None) == "unknown_subnet"


def test_challenge_binding_format():
    # Unbound challenge -> 3 parts
    unbound_ch = generate_challenge(expires_in_sec=60)
    assert len(unbound_ch["challenge"].split(".")) == 3

    # Client-bound challenge -> 4 parts (nonce.ts.bind_hash.sig)
    bound_ch = generate_challenge(expires_in_sec=60, client_ip="198.51.100.12", user_agent="Mozilla/5.0 TestBrowser")
    parts = bound_ch["challenge"].split(".")
    assert len(parts) == 4
    bind_hash = parts[2]
    expected_hash = compute_client_binding_hash("198.51.100.12", "Mozilla/5.0 TestBrowser")
    assert bind_hash == expected_hash


# ---------------------------------------------------------------------------
# 2. Token Relay Attack Mitigation Tests
# ---------------------------------------------------------------------------


def test_token_relay_different_ip_blocked():
    """
    Challenge generated for IP A (198.51.100.5) must be rejected if presented by IP B (203.0.113.50).
    """
    client_a_ip = "198.51.100.5"
    attacker_ip = "203.0.113.50"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"

    ch = generate_challenge(expires_in_sec=60, client_ip=client_a_ip, user_agent=ua)
    token = _make_token(ch["challenge"])

    # Legitimate client submit
    is_valid, reason, _ = verify_and_consume_token(token, client_ip=attacker_ip, user_agent=ua)
    assert is_valid is False
    assert "Token Relay Saldırısı" in reason or "Binding Mismatch" in reason


def test_token_relay_different_user_agent_blocked():
    """
    Challenge generated with a browser User-Agent must be rejected if submitted with curl/python UA.
    """
    ip = "198.51.100.5"
    browser_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    bot_ua = "python-requests/2.31.0"

    ch = generate_challenge(expires_in_sec=60, client_ip=ip, user_agent=browser_ua)
    token = _make_token(ch["challenge"])

    is_valid, reason, _ = verify_and_consume_token(token, client_ip=ip, user_agent=bot_ua)
    assert is_valid is False
    assert "Token Relay Saldırısı" in reason or "Binding Mismatch" in reason


def test_client_binding_subnet_tolerance():
    """
    Legitimate client roaming between cell towers in the same /24 IPv4 subnet must be allowed.
    """
    ip_tower_1 = "198.51.100.10"
    ip_tower_2 = "198.51.100.88"  # Same /24 subnet (198.51.100.0)
    ua = "Mozilla/5.0 Mobile/15E148 Safari/604.1"

    ch = generate_challenge(expires_in_sec=60, client_ip=ip_tower_1, user_agent=ua)
    token = _make_token(ch["challenge"])

    is_valid, reason, _ = verify_and_consume_token(token, client_ip=ip_tower_2, user_agent=ua)
    assert is_valid is True
    assert reason == "Geçerli"


def test_strict_token_binding_mode_rejects_unbound_token():
    """
    In SYNAPSE_TOKEN_BINDING=strict mode, legacy unbound tokens (3 parts) must be rejected.
    """
    unbound_ch = generate_challenge(expires_in_sec=60)  # 3 parts
    token = _make_token(unbound_ch["challenge"])

    with patch.dict(os.environ, {"SYNAPSE_TOKEN_BINDING": "strict"}):
        is_valid, reason, _ = verify_and_consume_token(token, client_ip="192.168.1.1", user_agent="TestUA")
        assert is_valid is False
        assert "Unbound Token Rejected in Strict Mode" in reason


# ---------------------------------------------------------------------------
# 3. End-to-End API Token Relay Test via FastAPI TestClient
# ---------------------------------------------------------------------------


def test_api_token_relay_via_fastapi():
    """
    FastAPI client tests Token Relay:
    1. GET /api/challenge from Client A
    2. POST /api/score from Attacker IP with different User-Agent
    Must trigger HTTP 200 with status: blocked and threat_type: TOKEN_RELAY_ATTACK.
    """
    client = TestClient(app)

    # 1. Client A fetches challenge
    res = client.get("/api/challenge", headers={"User-Agent": "LegitBrowser/1.0"})
    assert res.status_code == 200
    ch_data = res.json()
    assert len(ch_data["challenge"].split(".")) == 4

    token = _make_token(ch_data["challenge"])

    # 2. Attacker relays token with different User-Agent
    score_res = client.post(
        "/api/score",
        json={"token": token},
        headers={"User-Agent": "BotHarvestingScript/9.0"},
    )
    assert score_res.status_code == 200
    data = score_res.json()
    assert data["status"] == "blocked"
    assert data["threat_type"] == "TOKEN_RELAY_ATTACK"
    assert any("Token Relay Saldırısı" in r for r in data["reasons"])


# ---------------------------------------------------------------------------
# 4. SQLite Thread-Pool Leak-Free Connection Lifecycle Tests
# ---------------------------------------------------------------------------


def test_sqlite_worker_pool_connection_cleanup():
    """
    Verifies that connections opened across multiple worker threads are tracked in
    _open_connections and cleanly closed upon _cleanup_connections().
    """
    created_conns = []

    def worker_task():
        conn = get_connection()
        created_conns.append(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()

    threads = [threading.Thread(target=worker_task) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All connections must be registered
    assert len(_open_connections) >= 5

    # Run cleanup
    _cleanup_connections()

    # Set must be cleared
    assert len(_open_connections) == 0

    # Ensure connections are closed (attempting cursor on closed conn raises ProgrammingError)
    for conn in created_conns:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.cursor()


# ---------------------------------------------------------------------------
# 5. Doctor Health Check Test
# ---------------------------------------------------------------------------


def test_synapse_shield_doctor_execution():
    """
    Verifies that synapse-shield doctor diagnostic suite runs and returns 0.
    """
    exit_code = run_doctor()
    assert exit_code == 0

