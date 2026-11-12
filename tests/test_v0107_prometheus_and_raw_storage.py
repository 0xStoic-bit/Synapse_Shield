"""Prometheus exposition on the server + zero-raw-storage default for the log table."""

from __future__ import annotations

import base64
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from synapse_shield import main
from synapse_shield.main import app

ADMIN = {"X-Admin-Secret": "pytest-secret"}
client = TestClient(app, client=("127.0.0.1", 50001))


def _score(ip: str, telemetry: dict):
    h = {"x-forwarded-for": ip, "User-Agent": "pytest-v0107"}
    ch = client.get("/api/challenge", headers=h).json()["challenge"]
    env = {"challenge": ch, "telemetry": telemetry, "created_at": int(time.time() * 1000)}
    tok = base64.b64encode(json.dumps(env).encode()).decode()
    return client.post("/api/score", json={"token": tok}, headers=h), h, tok


def _linear_bot():
    t = int(time.time() * 1000)
    return {"mouse_movements": [{"x": 50 + i * 30, "y": 50 + i * 20, "t": t + i * 20} for i in range(25)]}


def _last_log_telemetry() -> str:
    time.sleep(0.3)
    con = sqlite3.connect(main.DB_FILE)
    try:
        return con.execute("SELECT telemetry FROM logs ORDER BY id DESC LIMIT 1").fetchone()[0]
    finally:
        con.close()


def test_raw_telemetry_not_persisted_by_default(monkeypatch):
    monkeypatch.delenv("SYNAPSE_STORE_RAW_TELEMETRY", raising=False)
    r, *_ = _score("10.77.0.1", _linear_bot())
    assert r.status_code == 200
    assert json.loads(_last_log_telemetry()) == {}


def test_raw_telemetry_opt_in(monkeypatch):
    monkeypatch.setenv("SYNAPSE_STORE_RAW_TELEMETRY", "1")
    r, *_ = _score("10.77.0.2", _linear_bot())
    assert r.status_code == 200
    assert "mouse_movements" in json.loads(_last_log_telemetry())


def test_train_skips_rows_without_raw_traces(monkeypatch, tmp_path):
    from synapse_shield import train

    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE logs (id INTEGER PRIMARY KEY, classification TEXT, telemetry TEXT, threat_type TEXT, "
        "reasons TEXT, features TEXT, ip TEXT, bot_score REAL)"
    )
    con.execute("INSERT INTO logs VALUES (1,'Bot','{}','X','[]','{}','1.1.1.1',100)")
    con.commit()
    con.close()
    monkeypatch.setattr(train, "DB_FILE", str(db))
    X, Y = train.load_training_data(include_adversarial=False, bootstrap=False)
    # The empty-trace bot row must not become a training sample (no bot labels at all); with zero
    # real humans, retrain falls back to its synthetic human bootstrap.
    assert 1.0 not in list(Y)


@pytest.mark.skipif(not main.prom.METRICS_ENABLED, reason="prometheus_client not installed")
def test_prometheus_exposition_is_admin_only_and_counts_requests():
    assert client.get("/metrics/prometheus").status_code == 401
    r, *_ = _score("10.77.0.3", _linear_bot())
    assert r.json()["decision"] == "block"

    p = client.get("/metrics/prometheus", headers=ADMIN)
    assert p.status_code == 200 and p.headers["content-type"].startswith("text/plain")
    assert "# HELP synapse_requests_total" in p.text
    assert 'synapse_requests_total{classification="Bot",status="block"}' in p.text


@pytest.mark.skipif(not main.prom.METRICS_ENABLED, reason="prometheus_client not installed")
def test_metrics_negotiates_prometheus_text_for_scrapers_and_json_otherwise():
    scrape = client.get("/metrics", headers={**ADMIN, "Accept": "application/openmetrics-text;version=1.0.0,text/plain;q=0.5"})
    assert "# HELP synapse_requests_total" in scrape.text
    plain = client.get("/metrics", headers=ADMIN)
    assert plain.headers["content-type"].startswith("application/json") and plain.json()["status"] == "ok"
