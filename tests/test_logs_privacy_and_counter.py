"""Request-rate counter key, logs.user_agent privacy and periodic logs retention (network-defense, v0.10.9).

1. The live flood counter (Poisson anomaly in engine + the >100 req/10 s ban in main) is
   storage.record_and_get_request_count keyed by the RAW client IP. The old main.get_recent_request_count
   queried the `logs` table by raw IP while save_log writes the masked IP, so it could never match; it was dead
   code and is removed so nobody wires a broken counter back in.
2. logs.user_agent follows SYNAPSE_PRIVACY_MODE.
3. Retention pruning runs periodically on the write path, not only at process start.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from synapse_shield import adversarial as adv
from synapse_shield import main as main_mod
from synapse_shield import storage as storage_mod
from synapse_shield.storage import SQLiteStorageBackend, set_storage

IP = "198.51.100.23"
CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36"


@pytest.fixture
def app_sqlite(tmp_path):
    b = SQLiteStorageBackend(db_path=str(tmp_path / "rc.db"))
    previous = storage_mod._global_storage
    set_storage(b)
    main_mod._challenge_limiter.cache.clear()
    try:
        yield TestClient(main_mod.app, client=(IP, 50000)), b
    finally:
        set_storage(previous)
        main_mod._challenge_limiter.cache.clear()
        b.close()


def _score(client, ua=CHROME_WIN):
    h = {"User-Agent": ua}
    challenge = client.get("/api/challenge", headers=h).json()["challenge"]
    tel = adv.generate_linear_telemetry(start=(100.0, 100.0), end=(600.0, 400.0), steps=40, duration_ms=1000.0)
    env = {"challenge": challenge, "telemetry": tel, "created_at": int(time.time() * 1000)}
    return client.post("/api/score", json={"token": base64.b64encode(json.dumps(env).encode()).decode()}, headers=h)


def test_live_counter_counts_requests_from_one_ip(app_sqlite, monkeypatch):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "strict")
    client, backend = app_sqlite
    for _ in range(3):  # stay under the 4-strike IP ban, which rejects before counting
        assert _score(client).status_code == 200
    # 3 scored requests recorded under the raw IP; the next record is the 4th.
    assert backend.record_and_get_request_count(IP, 10) == 4
    # A neighbour in the same /24 (NAT-like sharing of the masked key) is NOT counted together.
    assert backend.record_and_get_request_count("198.51.100.99", 10) == 1


def test_logs_table_ip_never_matches_raw_ip_so_logs_cannot_be_a_counter(app_sqlite, monkeypatch):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "strict")
    client, _ = app_sqlite
    _score(client)
    time.sleep(0.3)  # save_log is a background task
    conn = main_mod.get_connection()
    assert conn.execute("SELECT COUNT(*) FROM logs WHERE ip = ?", (IP,)).fetchone()[0] == 0
    assert not hasattr(main_mod, "get_recent_request_count"), "dead, broken logs-table counter must stay removed"


@pytest.mark.parametrize(
    "ua,expected",
    [
        (CHROME_WIN, "Chrome/131 Windows"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", "Safari/17 macOS"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0", "Firefox/128 Linux"),
        ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0.1", "Edge/130 Windows"),
        ("Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36", "Chrome/131 Android"),
        ("curl/8.4.0", "curl"),
        ("python-requests/2.32.3", "python-requests"),
        ("", "Unknown"),
    ],
)
def test_strict_ua_is_coarse_family(monkeypatch, ua, expected):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "strict")
    assert main_mod.privacy_user_agent(ua) == expected


def test_hash_and_off_modes(monkeypatch):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "hash")
    h = main_mod.privacy_user_agent(CHROME_WIN)
    assert h.startswith("ua_") and len(h) == 19 and "Chrome" not in h
    assert h == main_mod.privacy_user_agent(CHROME_WIN)
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "off")
    assert main_mod.privacy_user_agent(CHROME_WIN) == CHROME_WIN
    assert len(main_mod.privacy_user_agent("x" * 5000)) == 512


def test_save_log_persists_privacy_ua(monkeypatch):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", "strict")
    main_mod.save_log(IP, CHROME_WIN, 5.0, "Human", "CLEAN_HUMAN", [], {}, {})
    row = main_mod.get_connection().execute("SELECT user_agent FROM logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "Chrome/131 Windows"


def test_retention_prune_runs_periodically_on_write_path(monkeypatch):
    monkeypatch.setenv("SYNAPSE_LOG_RETENTION_DAYS", "14")
    conn = main_mod.get_connection()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn.execute("INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, threat_type, reasons, features, telemetry) "
                 "VALUES (?, '1.2.3.*', 'x', 0, 'Human', 'T', '[]', '{}', '{}')", (old,))
    conn.commit()
    def count_old():
        return conn.execute("SELECT COUNT(*) FROM logs WHERE timestamp = ?", (old,)).fetchone()[0]

    monkeypatch.setattr(main_mod, "_last_log_prune", time.monotonic())
    assert main_mod.maybe_prune_old_records() is False  # within the interval: cheap no-op
    assert count_old() == 1

    monkeypatch.setenv("SYNAPSE_LOG_PRUNE_INTERVAL_SEC", "60")
    monkeypatch.setattr(main_mod, "_last_log_prune", time.monotonic() - 61)
    main_mod.save_log(IP, CHROME_WIN, 5.0, "Human", "CLEAN_HUMAN", [], {}, {})
    assert count_old() == 0
