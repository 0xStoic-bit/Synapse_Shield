"""
Regression tests for the two review findings that were deferred from the first pass:
#6 (HTTP DELETE bypassed every adapter) and #9 (main.py gateway parity, open /metrics, raw IP in logs).
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import MagicMock

import pytest

from synapse_shield import core
from synapse_shield.tokens import generate_challenge

from test_framework_contract import HUMAN_TELEMETRY


def _token() -> str:
    env = {"challenge": generate_challenge()["challenge"], "telemetry": HUMAN_TELEMETRY}
    return base64.b64encode(json.dumps(env).encode()).decode()


# --- #6: DELETE ------------------------------------------------------------------------------------------------
def test_protected_methods_include_delete():
    assert core.PROTECTED_METHODS == ("POST", "PUT", "PATCH", "DELETE")


def test_every_adapter_uses_the_shared_method_list():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "src" / "synapse_shield"
    for name in ("asgi", "django", "flask", "litestar", "middleware", "sanic"):
        src = (root / f"{name}.py").read_text(encoding="utf-8")
        assert "not in PROTECTED_METHODS" in src, name
        assert '("POST", "PUT", "PATCH")' not in src, name


def _flask():
    flask = pytest.importorskip("flask")
    from synapse_shield.flask import SynapseFlaskMiddleware

    app = flask.Flask(f"del_{uuid.uuid4().hex}")

    @app.route("/api/account/<int:i>", methods=["GET", "DELETE"])
    def acct(i):
        return "ok"

    SynapseFlaskMiddleware(app, protected_paths=["/api/account"])
    c = app.test_client()
    return (
        lambda **kw: c.delete("/api/account/1", **kw).status_code,
        lambda: c.get("/api/account/1").status_code,
    )


def _fastapi():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse_shield.middleware import SynapseShieldMiddleware

    app = FastAPI()
    app.add_api_route("/api/account/{i}", lambda i: {"ok": True}, methods=["GET", "DELETE"])
    app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api/account"])
    c = TestClient(app)
    return (
        lambda **kw: c.delete("/api/account/1", **kw).status_code,
        lambda: c.get("/api/account/1").status_code,
    )


def _asgi():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse_shield.asgi import SynapseShieldASGIMiddleware

    app = FastAPI()
    app.add_api_route("/api/account/{i}", lambda i: {"ok": True}, methods=["GET", "DELETE"])
    c = TestClient(SynapseShieldASGIMiddleware(app, protected_paths=["/api/account"]))
    return (
        lambda **kw: c.delete("/api/account/1", **kw).status_code,
        lambda: c.get("/api/account/1").status_code,
    )


def _litestar():
    pytest.importorskip("litestar")
    from litestar import Litestar, delete, get
    from litestar.middleware import DefineMiddleware
    from litestar.testing import TestClient

    from synapse_shield.litestar import LitestarSynapseMiddleware

    @delete("/api/account/1", status_code=200)
    async def d() -> dict:
        return {"ok": True}

    @get("/api/account/1")
    async def g() -> dict:
        return {"ok": True}

    app = Litestar([d, g], middleware=[DefineMiddleware(LitestarSynapseMiddleware, protected_paths=["/api/account"])])
    c = TestClient(app)
    return (
        lambda **kw: c.delete("/api/account/1", **kw).status_code,
        lambda: c.get("/api/account/1").status_code,
    )


@pytest.mark.parametrize("factory", [_flask, _fastapi, _asgi, _litestar], ids=["flask", "fastapi", "asgi", "litestar"])
def test_delete_without_a_token_is_rejected_and_with_one_is_allowed(factory):
    delete, get = factory()
    assert get() == 200, "GET stays unprotected"
    assert delete() == 403, "token-less DELETE on a protected path must be blocked"
    assert delete(headers={"X-Synapse-Token": "garbage"}) == 403
    assert delete(headers={"X-Synapse-Token": _token()}) == 200, "DELETE carries its token in the header"
    assert delete(headers={"X-Synapse-Token": _token()}) == 200


def test_django_delete_is_protected():
    pytest.importorskip("django")
    from django.conf import settings

    if not settings.configured:
        settings.configure(SYNAPSE_SHIELD_PROTECTED_PATHS=["/api/protected"], SYNAPSE_SHIELD_MAX_RISK=50.0)
    from synapse_shield.django import SynapseShieldMiddleware as DjangoMiddleware

    mw = DjangoMiddleware(get_response=lambda r: "OK")
    mw.protected_paths = ["/api/account"]
    req = MagicMock(path="/api/account/1", method="DELETE", body=b"", META={"REMOTE_ADDR": "127.0.0.1"})
    resp = mw.process_request(req)
    assert resp is not None and resp.status_code == 403


def test_sanic_delete_is_protected():
    pytest.importorskip("sanic")
    pytest.importorskip("sanic_testing")
    import asyncio

    from test_framework_contract import _sanic_app
    from sanic_testing.testing import SanicASGITestClient

    app = _sanic_app(protected_paths=["/mw"])
    c = SanicASGITestClient(app)

    async def go():
        _, resp = await c.delete("/mw/login")
        return resp.status

    assert asyncio.run(go()) in (403, 405), "never a pass-through 200"


# --- #9: main.py gateway ----------------------------------------------------------------------------------------
ADMIN = {"X-Admin-Secret": "pytest-secret"}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from synapse_shield import main

    return TestClient(main.app)


def test_metrics_requires_the_admin_secret(client):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-Admin-Secret": "nope"}).status_code == 401
    assert client.get("/metrics", headers=ADMIN).status_code == 200


def test_gateway_session_id_is_bound_to_the_user_agent(monkeypatch, client):
    import synapse_shield.main as gw

    seen = []

    class Spy:
        def get_session_telemetries(self, session_id, window_sec):
            seen.append(session_id)
            return []

        def __getattr__(self, name):
            return getattr(gw_storage, name)

    gw_storage = gw.get_storage()
    monkeypatch.setattr(gw, "get_storage", lambda: Spy())
    for ua in ("Mozilla/5.0 (iPhone)", "Mozilla/5.0 (Pixel)"):
        client.post("/api/score", json={"token": _token()}, headers={"User-Agent": ua})
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(s.startswith("ip_") and len(s.rsplit("_", 1)[1]) == 16 for s in seen)


@pytest.mark.parametrize("score,diff", [(40.0, 4), (45.0, 5), (54.0, 5)])
def test_gateway_pow_difficulty_is_risk_adaptive(monkeypatch, client, score, diff):
    import synapse_shield.main as gw

    monkeypatch.setattr(
        gw, "analyze_behavior",
        lambda *a, **k: (score, "Human", ["x"], {"features": {"total_interactive_events": 9, "mouse_points": 9}}),
    )
    r = client.post("/api/score", json={"token": _token()}, headers={"User-Agent": "ua-pow"}).json()
    assert r["status"] == "challenge_required" and r["pow_difficulty"] == diff
    assert r["pow_salt"].split(".")[2] == str(diff), "the signed salt carries the same difficulty"


def test_gateway_accepts_header_token(client):
    r = client.post("/api/score", json={}, headers={"X-Synapse-Token": _token(), "User-Agent": "ua-h"})
    assert r.status_code == 200 and r.json()["status"] == "success"
    assert client.post("/api/score", json={}).status_code == 403


def test_gateway_rejects_non_object_json(client):
    assert client.post("/api/score", content="[1,2]", headers={"Content-Type": "application/json"}).status_code == 400


@pytest.mark.parametrize("mode", ["strict", "hash"])
def test_raw_ip_never_reaches_logs_websocket_or_webhooks(monkeypatch, mode):
    import synapse_shield.main as gw

    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", mode)
    raw = "203.0.113.77"

    stored = {}
    conn = MagicMock()
    cur = conn.cursor.return_value

    def capture(sql, params=()):
        if "INSERT INTO logs" in sql:
            stored["ip"] = params[1]

    cur.execute.side_effect = capture
    monkeypatch.setattr(gw, "get_connection", lambda: conn)
    gw.save_log(raw, "ua", 10.0, "Human", "CLEAN_HUMAN", [], {}, {})
    assert raw not in str(stored["ip"]) and stored["ip"] == gw.mask_ip(raw)

    sent = []

    class Cur:
        def execute(self, *a, **k):
            return self

        def fetchone(self):
            return ("https://discord.com/api/webhooks/1/x", "", "")

    class Conn:
        def cursor(self):
            return Cur()

        def close(self):
            pass

    monkeypatch.setattr(gw, "get_connection", lambda: Conn())
    monkeypatch.setattr(gw, "validate_webhook_url", lambda url: None)
    monkeypatch.setattr(gw.urllib.request, "urlopen",
                        lambda req, timeout=None: sent.append(req.data.decode("utf-8")))
    gw.send_webhook_notification(raw, "BOT", 90.0, ["r"])
    assert sent, "the webhook must actually be sent for this test to mean anything"
    assert all(raw not in payload for payload in sent)
