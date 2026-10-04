"""
Synapse Shield - Security Patches Test Suite
Validates the mitigation of all 11 reported vulnerabilities (P0, P1, P2).
"""

import base64
import json
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient

from synapse_shield.engine import analyze_behavior
from synapse_shield.features import extract_features, MultimodalTokenizer
from synapse_shield.main import app, validate_webhook_url
from synapse_shield.storage import SQLiteStorageBackend, get_storage
from synapse_shield.tokens import (
    generate_challenge,
    generate_pow_salt,
    verify_and_consume_token,
    verify_and_consume_pow,
)


@pytest.fixture
def client():
    return TestClient(app)


# --- [AÇIK-01] XSS Protection Verification ---
def test_xss_protection_in_logs_and_html():
    from synapse_shield.main import save_log

    # User agent with raw XSS payload
    xss_ua = "<img/src=x/onerror=alert(document.domain)>"
    save_log(
        ip="127.0.0.1",
        user_agent=xss_ua,
        bot_score=100.0,
        classification="Bot",
        threat_type="STEALTH_AUTOMATION",
        reasons=["Test XSS"],
        features={},
        telemetry={},
    )
    # Check that reading index.html defines escapeHtml
    with open("src/synapse_shield/static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert "function escapeHtml(str)" in html
    assert "escapeHtml(log.user_agent" in html


# --- [AÇIK-02] WebSocket Terminal Admin Authentication ---
def test_websocket_terminal_auth(client, monkeypatch):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "super_secret_123")
    monkeypatch.setenv("SYNAPSE_DEV_MODE", "0")

    # Connecting without token or with invalid token should be rejected (WS_1008_POLICY_VIOLATION)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/terminal", headers={"Origin": "http://testserver", "Host": "testserver"}) as ws:
            pass

    with pytest.raises(Exception):
        with client.websocket_connect("/ws/terminal?token=wrong_secret", headers={"Origin": "http://testserver", "Host": "testserver"}) as ws:
            pass

    # Connecting with valid token succeeds
    with client.websocket_connect("/ws/terminal?token=super_secret_123", headers={"Origin": "http://testserver", "Host": "testserver"}) as ws:
        msg1 = ws.receive_text()
        assert "Synapse Shield Cyber-Console" in msg1


# --- [AÇIK-03] Webhook SSRF and DNS Rebinding ---
def test_webhook_ssrf_and_dns_rebinding(client, monkeypatch):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "super_secret_123")

    # Unauthorized access blocked
    res1 = client.get("/api/settings/webhooks")
    assert res1.status_code == 401

    res2 = client.post("/api/settings/webhooks", json={"discord_url": "https://discord.com/api/webhooks/123"})
    assert res2.status_code == 401

    # Valid secret
    headers = {"X-Admin-Secret": "super_secret_123"}
    get_res = client.get("/api/settings/webhooks", headers=headers)
    assert get_res.status_code == 200

    # SSRF: HTTP scheme rejected
    with pytest.raises(Exception):
        validate_webhook_url("http://discord.com/webhook")

    # SSRF & DNS Rebinding: Private IP / arbitrary domain rejected
    with pytest.raises(Exception):
        validate_webhook_url("https://127.0.0.1/evil")

    with pytest.raises(Exception):
        validate_webhook_url("https://169.254.169.254/latest/meta-data")

    with pytest.raises(Exception):
        validate_webhook_url("https://attacker-domain.com/hook")

    # Legitimate Discord and Telegram domains allowed
    validate_webhook_url("https://discord.com/api/webhooks/test")
    validate_webhook_url("https://discordapp.com/api/webhooks/test")
    validate_webhook_url("https://api.telegram.org/bot123/send")


# --- [AÇIK-04] Brave Farbling Override Logic Flaw ---
def test_brave_farbling_override_with_anomalies():
    # Human mouse movements (straightness < 0.99, avg_jerk > 0.00008)
    mouse_movements = [{"x": 100 + i * 2, "y": 100 + (i % 3) * 5, "t": i * 30} for i in range(25)]

    # Case A: Pure organic user with Brave canvas farbling -> Capped at 34% (Human)
    clean_brave_telemetry = {
        "browser": {"is_canvas_hooked": True, "webdriver": False, "screen_width": 1920, "screen_height": 1080},
        "mouse_movements": mouse_movements,
        "clicks": [{"x": 140, "y": 110, "t": 750}],
        "keystrokes": [],
    }
    score_a, cls_a, reasons_a, _ = analyze_behavior(clean_brave_telemetry)
    assert score_a <= 34.0
    assert cls_a == "Human"
    assert any("capped at 34.0" in r for r in reasons_a)

    # Case B: Bot using Brave farbling BUT with headless screen (0x0) -> Farbling override must NOT apply!
    bot_headless_telemetry = {
        "browser": {"is_canvas_hooked": True, "webdriver": False, "screen_width": 0, "screen_height": 0},
        "mouse_movements": mouse_movements,
        "clicks": [{"x": 140, "y": 110, "t": 750}],
        "keystrokes": [],
    }
    score_b, cls_b, reasons_b, _ = analyze_behavior(bot_headless_telemetry)
    assert not any("capped at 34.0" in r for r in reasons_b)
    assert score_b > 34.0

    # Case C: Bot using Brave farbling BUT with robotic superfast keystrokes -> Must NOT be capped!
    bot_robotic_keys_telemetry = {
        "browser": {"is_canvas_hooked": True, "webdriver": False, "screen_width": 1920, "screen_height": 1080},
        "mouse_movements": mouse_movements,
        "clicks": [{"x": 140, "y": 110, "t": 750}],
        "keystrokes": [{"t": i * 10, "type": "down"} for i in range(10)],  # constant 10ms typing!
    }
    score_c, cls_c, reasons_c, _ = analyze_behavior(bot_robotic_keys_telemetry)
    assert not any("capped at 34.0" in r for r in reasons_c)


# --- [AÇIK-05] PoW Replay / Nonce Consumption ---
def test_pow_replay_protection():
    salt = generate_pow_salt()
    # Find a valid 4-zero nonce
    import hashlib

    found_nonce = None
    for n in range(500000):
        h = hashlib.sha256((salt + str(n)).encode()).hexdigest()
        if h.startswith("0000"):
            found_nonce = str(n)
            break
    assert found_nonce is not None

    # First consumption: valid
    res1 = verify_and_consume_pow(salt, found_nonce)
    assert res1 is True

    # Second consumption (Replay): must be False!
    res2 = verify_and_consume_pow(salt, found_nonce)
    assert res2 is False


# --- [AÇIK-06] Early Nonce Consumption (Probe & Retry Protection) ---
def test_early_nonce_consumption(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "1500")
    challenge_data = generate_challenge()
    challenge = challenge_data["challenge"]

    # Submit too fast (< 1.5s)
    envelope = {"challenge": challenge, "telemetry": {}}
    token_str = base64.b64encode(json.dumps(envelope).encode()).decode()

    # Attempt 1: Rejected because too fast
    is_valid1, reason1, _ = verify_and_consume_token(token_str)
    assert is_valid1 is False
    assert "Humanly Impossible Speed" in reason1

    # Attempt 2: Even if time passes, the nonce was burned on Attempt 1!
    is_valid2, reason2, _ = verify_and_consume_token(token_str)
    assert is_valid2 is False
    assert "Replay Detected" in reason2 or "Yeniden Oynatma" in reason2


# --- [AÇIK-07] Active Learning Poisoning Protection ---
def test_active_learning_poisoning_protection(client, monkeypatch):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "super_secret_123")
    # /api/collect_dataset is protected by admin secret
    res = client.post("/api/collect_dataset", json={"mouse_movements": []})
    assert res.status_code == 401

    headers = {"X-Admin-Secret": "super_secret_123"}
    res_auth = client.post("/api/collect_dataset", json={"mouse_movements": []}, headers=headers)
    assert res_auth.status_code == 200


# --- [AÇIK-08] Multi-Worker SQLite Strike Table & Composite Index ---
def test_sqlite_ip_strikes_index_and_concurrency(tmp_path):
    db_file = str(tmp_path / "test_strikes.db")
    storage = SQLiteStorageBackend(db_path=db_file)

    # Check that ip_strikes table and index exist
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_strikes'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ip_strikes_ip_ts'")
    assert cur.fetchone() is not None
    conn.close()

    test_ip = "192.168.1.100"
    assert not storage.is_ip_banned(test_ip)
    # Record 3 strikes -> not banned
    assert storage.record_bot_strike(test_ip, threshold=4) is False
    assert storage.record_bot_strike(test_ip, threshold=4) is False
    assert storage.record_bot_strike(test_ip, threshold=4) is False
    assert not storage.is_ip_banned(test_ip)

    # 4th strike -> banned
    assert storage.record_bot_strike(test_ip, threshold=4) is True
    assert storage.is_ip_banned(test_ip) is True


# --- [AÇIK-09] Token Expired Separation ---
def test_token_expired_response(client, monkeypatch):
    # Construct an expired challenge (> 60s ago)
    import secrets
    import hmac
    import hashlib
    from synapse_shield.tokens import SECRET_KEY

    nonce = secrets.token_hex(16)
    ts = int((time.time() - 90) * 1000)  # 90 seconds ago
    sig = hmac.HMAC(SECRET_KEY, f"{nonce}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
    challenge = f"{nonce}.{ts}.{sig}"

    envelope = {"challenge": challenge, "telemetry": {}}
    token_str = base64.b64encode(json.dumps(envelope).encode()).decode()

    res = client.post("/api/score", json={"token": token_str})
    assert res.status_code == 400
    data = res.json()
    assert data.get("code") == "EXPIRED"
    assert data.get("status") == "token_expired"


# --- [AÇIK-10] Keystroke DoS Linear Complexity & Capping ---
def test_keystroke_dos_linear_time_and_capping():
    # 5,000 keystrokes payload
    huge_keystrokes = []
    for i in range(5000):
        huge_keystrokes.append({"t": i * 10, "type": "down", "code": "KeyA"})
        huge_keystrokes.append({"t": i * 10 + 5, "type": "up", "code": "KeyA"})

    telemetry = {"keystrokes": huge_keystrokes}

    t0 = time.perf_counter()
    features = extract_features(telemetry)
    elapsed_features = time.perf_counter() - t0

    # Must be capped at 150
    assert features["key_count"] <= 150
    assert elapsed_features < 0.05  # < 50ms

    tokenizer = MultimodalTokenizer()
    t1 = time.perf_counter()
    static_vec = tokenizer.tokenize_static(telemetry)
    elapsed_tok = time.perf_counter() - t1

    assert len(static_vec) == 8
    assert elapsed_tok < 0.05  # < 50ms (previously took seconds due to O(N^2))


# --- [AÇIK-11] Middleware IP Ban and Strike Enforcement ---
def test_middleware_ip_ban_enforcement():
    from fastapi import FastAPI
    from synapse_shield.middleware import SynapseShieldMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SynapseShieldMiddleware, protected_paths=["/protected"], max_risk_score=50.0)

    @test_app.post("/protected/action")
    async def action():
        return {"result": "ok"}

    mid_client = TestClient(test_app)

    # 1. Banned IP is blocked immediately
    storage = get_storage()
    storage.ban_ip("testclient", duration_sec=60, reason="Test ban")
    assert storage.is_ip_banned("testclient") is True

    res = mid_client.post("/protected/action", json={})
    assert res.status_code == 403
    assert "banned" in res.json()["error"].lower()

    # Unban and test invalid token triggers strike
    storage.unban_ip("testclient")
    assert storage.is_ip_banned("testclient") is False

    # Send 4 invalid token attempts -> triggers strike and bans IP
    for _ in range(4):
        mid_client.post("/protected/action", json={"token": "invalid_fake_token"})

    assert storage.is_ip_banned("testclient") is True
    storage.unban_ip("testclient")


# --- [v0.9.3] Poisson CPU Safety & Numerical Stability ---
def test_poisson_anomaly_cpu_safety_and_clamping():
    from synapse_shield.engine import poisson_anomaly_score

    # Normal values
    assert poisson_anomaly_score(0) == 0.0
    assert poisson_anomaly_score(1) == 0.0
    assert 0.0 < poisson_anomaly_score(5, lambda_val=2.0) < 1.0

    # High frequency / DoS values: should return 1.0 instantly without factorial overflow
    t0 = time.perf_counter()
    score_huge = poisson_anomaly_score(100_000, lambda_val=2.0)
    elapsed = time.perf_counter() - t0

    assert score_huge == 1.0
    assert elapsed < 0.001  # < 1 millisecond


# --- [v0.9.3] IPv4-Mapped IPv6 Masking & Trusted Proxies Configuration ---
def test_mask_ip_ipv4_mapped_and_trusted_proxies(monkeypatch):
    from synapse_shield.main import mask_ip, _get_trusted_proxies

    # IPv4 standard
    assert mask_ip("192.168.1.45") == "192.168.1.*"

    # IPv4-mapped IPv6 must unmap to IPv4 before masking
    assert mask_ip("::ffff:192.168.1.45") == "192.168.1.*"
    assert mask_ip("::ffff:10.0.0.12") == "10.0.0.*"

    # Standard IPv6
    masked_v6 = mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    assert masked_v6.startswith("2001:0db8:85a3:")

    # SYNAPSE_TRUSTED_PROXIES configuration
    monkeypatch.setenv("SYNAPSE_TRUSTED_PROXIES", "10.0.0.1, 192.168.1.1, 127.0.0.1")
    proxies = _get_trusted_proxies()
    assert "10.0.0.1" in proxies
    assert "192.168.1.1" in proxies
    assert "127.0.0.1" in proxies


# --- [v0.9.3] API Logs Query Limit Bounds ---
def test_api_logs_query_limit_bounded(client, monkeypatch):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "test_admin_key")

    # Limit within allowed bounds (1 to 1000)
    res = client.get("/api/logs?limit=50", headers={"X-Admin-Secret": "test_admin_key"})
    assert res.status_code == 200

    # Limit exceeding 1000 must be rejected with 422 Unprocessable Entity
    res_huge = client.get("/api/logs?limit=1001", headers={"X-Admin-Secret": "test_admin_key"})
    assert res_huge.status_code == 422

    # Negative or 0 limit must also be rejected
    res_zero = client.get("/api/logs?limit=0", headers={"X-Admin-Secret": "test_admin_key"})
    assert res_zero.status_code == 422


# --- [v0.9.3] Model Training Output Path Traversal Guard ---
def test_train_path_traversal_guard():
    from synapse_shield.train import retrain_fc2

    with pytest.raises(ValueError, match="must be .npz"):
        retrain_fc2(epochs=1, output_path="malicious_script.sh")

    with pytest.raises(ValueError, match="must be .npz"):
        retrain_fc2(epochs=1, output_path="/etc/passwd")

