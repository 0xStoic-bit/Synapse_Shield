"""
Admin & operations surface of the reference FastAPI server (main.py).

Covers the security properties of the endpoints the cockpit uses, not just their happy paths:
  * Webhook alerts: payloads go only to the configured Discord/Telegram hosts; failures are
    swallowed (an alerting outage must never break request scoring).
  * Webhook settings: SSRF guard rejects non-HTTPS and look-alike domains.
  * Log export (txt/md): admin-only, and raw client IPs never appear (GDPR/KVKK masking).
  * WebSocket cyber-console: Origin/Host CSWSH check, admin token, every command.
  * Dataset collection limits, /metrics, challenge rate limiter LRU, static routes.

Outbound HTTP is intercepted; no network traffic is generated.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from synapse_shield import main
from synapse_shield.storage import get_storage

ADMIN = {"X-Admin-Secret": "pytest-secret"}
WS_HEADERS = {"Origin": "http://testserver", "Host": "testserver"}


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def outbound(monkeypatch):
    """Capture outgoing webhook requests instead of sending them."""
    sent: list[tuple[str, dict]] = []

    def fake_urlopen(req, timeout=None):
        sent.append((req.full_url, json.loads(req.data.decode("utf-8"))))
        if "fail" in req.full_url:
            raise OSError("network unreachable")

    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen)
    return sent


def _set_webhooks(discord: str = "", tg_token: str = "", tg_chat: str = "") -> None:
    conn = main.get_connection()
    conn.execute(
        "UPDATE webhook_settings SET discord_url=?, telegram_token=?, telegram_chat_id=? WHERE id=1",
        (discord, tg_token, tg_chat),
    )
    conn.commit()


@pytest.fixture(autouse=True)
def _reset_webhooks():
    main.init_db()
    _set_webhooks()
    yield
    _set_webhooks()


# --------------------------------------------------------------------------------------------
# Webhook alerts
# --------------------------------------------------------------------------------------------


def test_webhook_alert_goes_to_configured_hosts_only(outbound):
    _set_webhooks("https://discord.com/api/webhooks/1/abc", "123:TOKEN", "42")
    main.send_webhook_notification("203.0.113.9", "WEBDRIVER", 97.5, ["navigator.webdriver=true"])

    hosts = [urllib.parse.urlsplit(u).hostname for u, _ in outbound]
    assert hosts == ["discord.com", "api.telegram.org"]
    discord_body = outbound[0][1]["embeds"][0]["description"]
    assert "WEBDRIVER" in discord_body and "%97.5" in discord_body
    assert outbound[1][1]["chat_id"] == "42"
    assert outbound[1][0].endswith("/bot123:TOKEN/sendMessage")


def test_webhook_alert_noop_and_failure_paths(outbound, monkeypatch, capsys):
    main.send_webhook_notification("1.1.1.1", "X", 90, [])
    assert outbound == [], "no webhooks configured -> nothing is sent"

    _set_webhooks("https://discord.com/fail", "t", "")  # telegram incomplete -> discord only
    main.send_webhook_notification("1.1.1.1", "X", 90, [])
    assert len(outbound) == 1 and "Unknown anomaly" in outbound[0][1]["embeds"][0]["description"]

    _set_webhooks("", "fail", "7")
    main.send_webhook_notification("1.1.1.1", "X", 90, ["r"])
    assert len(outbound) == 2

    conn = main.get_connection()
    conn.execute("DELETE FROM webhook_settings")
    conn.commit()
    main.send_webhook_notification("1.1.1.1", "X", 90, ["r"])  # missing settings row
    assert len(outbound) == 2
    main.init_db()

    def broken_conn():
        raise RuntimeError("db gone")

    monkeypatch.setattr(main, "get_connection", broken_conn)
    main.send_webhook_notification("1.1.1.1", "X", 90, ["r"])
    assert "Webhook Notification Error: db gone" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# Webhook settings (SSRF)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/1",  # not HTTPS
        "https://evil.example/api/webhooks/1",
        "https://discord.com.evil.example/x",  # suffix look-alike
        "https://notdiscord.com/x",  # prefix look-alike
        "https://127.0.0.1/x",
    ],
)
def test_webhook_settings_reject_ssrf_targets(client, url):
    r = client.post("/api/settings/webhooks", json={"discord_url": url}, headers=ADMIN)
    assert r.status_code == 400


def test_webhook_settings_roundtrip(client):
    assert client.get("/api/settings/webhooks", headers=ADMIN).json()["discord_url"] == ""
    body = {"discord_url": "https://canary.discord.com/api/webhooks/9", "telegram_token": " t ", "telegram_chat_id": "5"}
    assert client.post("/api/settings/webhooks", json=body, headers=ADMIN).json() == {"status": "success"}
    got = client.get("/api/settings/webhooks", headers=ADMIN).json()
    assert got == {"discord_url": body["discord_url"], "telegram_token": "t", "telegram_chat_id": "5"}

    r = client.post("/api/settings/webhooks", content="{bad", headers={**ADMIN, "content-type": "application/json"})
    assert r.status_code == 400

    conn = main.get_connection()
    conn.execute("DELETE FROM webhook_settings")
    conn.commit()
    assert client.get("/api/settings/webhooks", headers=ADMIN).json()["discord_url"] == ""
    main.init_db()


# --------------------------------------------------------------------------------------------
# Log export & summary
# --------------------------------------------------------------------------------------------


def _seed_logs():
    conn = main.get_connection()
    rows = [
        ("2026-11-06T10:00:00+00:00", "198.51.100.77", "ua-bot", 95.0, "Bot", "WEBDRIVER", json.dumps(["webdriver"]), "{}"),
        ("2026-11-06T10:00:01+00:00", "198.51.100.78", "ua-human", 5.0, "Human", None, None, None),
    ]
    conn.executemany(
        "INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, threat_type, reasons, features) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


@pytest.mark.parametrize("fmt,marker", [("md", "| ID |"), ("txt", "AUDIT & SECURITY")])
def test_log_export_masks_ips_and_requires_admin(client, fmt, marker):
    _seed_logs()
    assert client.get(f"/api/logs/export?format={fmt}").status_code == 401
    r = client.get(f"/api/logs/export?format={fmt}", headers=ADMIN)
    assert r.status_code == 200
    assert marker in r.text
    assert "attachment; filename=synapse_security" in r.headers["content-disposition"]
    assert "198.51.100.77" not in r.text and "198.51.100.78" not in r.text, "raw IPs must never be exported"
    assert "WEBDRIVER" in r.text and "UNKNOWN" in r.text


def test_log_export_rejects_unknown_format(client):
    assert client.get("/api/logs/export?format=csv", headers=ADMIN).status_code == 422


def test_logs_summary(client):
    _seed_logs()
    s = client.get("/api/logs?limit=10", headers=ADMIN).json()
    assert s["total_requests"] == 2 and s["bot_requests"] == 1
    assert s["threat_distribution"] == {"WEBDRIVER": 1}
    assert sorted(log["ip"] for log in s["logs"]) == ["198.51.100.*", "198.51.100.*"], "last octet must be masked"


# --------------------------------------------------------------------------------------------
# WebSocket cyber-console
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{"Host": "testserver"}, {"Origin": "http://evil.example", "Host": "testserver"}],
)
def test_ws_console_rejects_cross_site_origin(client, headers):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/terminal?token=pytest-secret", headers=headers) as ws:
            ws.receive_text()


def test_ws_console_commands(client, monkeypatch):
    from synapse_shield import train

    get_storage().ban_ip("192.0.2.200", duration_sec=60, reason="ws-test")
    outcomes = iter([{"success": True, "samples": 12, "loss": 0.1234}, {"success": False, "error": "no data"}])
    monkeypatch.setattr(train, "retrain_fc2", lambda: next(outcomes))

    with client.websocket_connect("/ws/terminal?token=pytest-secret", headers=WS_HEADERS) as ws:
        assert "Cyber-Console" in ws.receive_text()
        ws.receive_text()

        def cmd(text):
            ws.send_text(text)
            return ws.receive_text()

        assert "Available commands" in cmd("help")
        assert cmd("cls") == "[CLEAR]"
        assert cmd("status").startswith("[STATUS] Total Req:")
        assert "192.0.2.200" in cmd("ban list")
        assert "removed from quarantine" in cmd("unban 192.0.2.200")
        assert ws.send_text("retrain") is None and "[RETRAIN]" in ws.receive_text()
        assert "Örneklem: 12" in ws.receive_text()
        ws.send_text("retrain")
        ws.receive_text()
        assert "no data" in ws.receive_text()
        assert "purged" in cmd("clear logs")
        assert "No IPs are currently banned" in cmd("ban list")
        assert "Unknown command" in cmd("rm -rf /")
    assert get_storage().is_ip_banned("192.0.2.200") is False


def test_ws_console_reports_backend_errors(client, monkeypatch):
    def broken():
        raise RuntimeError("db offline")

    with client.websocket_connect("/ws/terminal?token=pytest-secret", headers=WS_HEADERS) as ws:
        ws.receive_text()
        ws.receive_text()
        monkeypatch.setattr(main, "get_connection", broken)
        monkeypatch.setattr(main, "fetch_logs_summary", lambda limit: broken())

        class BrokenStorage:
            def unban_ip(self, ip):
                broken()

        monkeypatch.setattr(main, "get_storage", lambda: BrokenStorage())
        for command in ("clear logs", "status", "ban list", "unban 1.2.3.4"):
            ws.send_text(command)
            assert ws.receive_text().startswith("[ERROR]"), command


# --------------------------------------------------------------------------------------------
# Dataset collection, metrics, rate limiter, static routes
# --------------------------------------------------------------------------------------------


def test_collect_dataset_limits(client):
    assert client.post("/api/collect_dataset", json={}).status_code == 401
    big = b"{" + b" " * 524300 + b"}"
    assert client.post("/api/collect_dataset", content=big, headers=ADMIN).status_code == 413
    assert client.post("/api/collect_dataset", content=b"{nope", headers=ADMIN).status_code == 400
    r = client.post("/api/collect_dataset", json={"mouse_movements": [{"x": 1, "y": 2, "t": 3}]}, headers=ADMIN)
    assert r.json()["status"] == "success"


def test_metrics_endpoint(client, monkeypatch):
    assert client.get("/metrics").status_code == 401, "live counters must not be public"
    assert client.get("/metrics", headers={"X-Admin-Secret": "wrong"}).status_code == 401
    m = client.get("/metrics", headers=ADMIN).json()
    assert m["status"] == "ok"
    from synapse_shield import synapse_core_rs

    if synapse_core_rs is None:
        return

    def broken():
        raise RuntimeError("stats unavailable")

    monkeypatch.setattr(synapse_core_rs, "get_state_engine_stats_rs", broken, raising=False)
    assert client.get("/metrics", headers=ADMIN).json()["error"] == "stats unavailable"


def test_challenge_rate_limiter_lru_eviction():
    lim = main.LRUTokenBucket(maxsize=2)
    a = lim.get_bucket("a")
    lim.get_bucket("b")
    assert lim.get_bucket("a") is a  # hit moves "a" to most-recent
    lim.get_bucket("c")  # evicts least-recent "b"
    assert list(lim.cache) == ["a", "c"]


def test_challenge_endpoint_rate_limits_per_ip(client, monkeypatch):
    monkeypatch.setattr(main, "_challenge_limiter", main.LRUTokenBucket())
    codes = [client.get("/api/challenge").status_code for _ in range(int(main._CHALLENGE_RATE_LIMIT) + 1)]
    assert codes[:-1] == [200] * int(main._CHALLENGE_RATE_LIMIT)
    assert codes[-1] == 429


def test_static_routes_and_missing_files(client, monkeypatch, tmp_path):
    assert client.get("/health").json() == {"status": "ok"}
    for path in ("/", "/store", "/static/synapse-sdk.js"):
        assert client.get(path).status_code == 200
    monkeypatch.setattr(main, "STATIC_DIR", str(tmp_path))
    assert "index.html missing" in client.get("/").text
    assert "store.html missing" in client.get("/store").text
    assert client.get("/static/synapse-sdk.js").status_code == 404
