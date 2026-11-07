"""
Framework adapter security contract.

Every first-party integration (Flask, Sanic, Litestar — decorator/guard and middleware) must
enforce the same cryptographic + behavioral gate as the FastAPI reference server. These tests
drive each adapter through its framework's *real* request pipeline (no MagicMock requests), so a
regression in header/body token extraction, payload limits, replay protection, shadow mode or
telemetry injection fails here for that framework specifically.

Contract (per adapter):
  1. No token                 -> 403 BLOCK
  2. Valid human token        -> 200 ALLOW, X-Synapse-Decision: allow, telemetry injected
  3. Same token replayed      -> 403 BLOCK (single-use nonce)
  4. Token in header          -> accepted (header has priority over body)
  5. Webdriver bot token      -> 403 BLOCK
  6. Shadow mode + bot token  -> 200, X-Synapse-Decision: shadow-block
  7. Payload > 256 KB         -> 413
  8. Middleware only: unprotected paths and safe methods (GET) pass through untouched
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid

import pytest

from fastapi import Request as FastAPIRequest

from synapse_shield.core import MAX_PAYLOAD_SIZE
from synapse_shield.tokens import generate_challenge

HUMAN_TELEMETRY = {
    "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
    "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20 + (i * 7) % 5} for i in range(20)],
}
BOT_TELEMETRY = {"browser": {"webdriver": True}}
OVERSIZED = {"blob": "X" * (MAX_PAYLOAD_SIZE + 1024)}


def make_token(human: bool = True) -> str:
    envelope = {
        "challenge": generate_challenge()["challenge"],
        "telemetry": HUMAN_TELEMETRY if human else BOT_TELEMETRY,
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()


def _error_text(body: object) -> str:
    return json.dumps(body) if not isinstance(body, str) else body


# --------------------------------------------------------------------------------------------
# Flask
# --------------------------------------------------------------------------------------------


@pytest.fixture
def flask_client():
    flask = pytest.importorskip("flask")
    from flask import g, jsonify

    from synapse_shield.flask import SynapseFlaskMiddleware, shield_protect_flask

    app = flask.Flask(f"flask_contract_{uuid.uuid4().hex}")

    @app.route("/deco", methods=["POST"])
    @shield_protect_flask()
    def deco():
        return jsonify({"ok": True, "has_telemetry": g.synapse_telemetry is not None})

    @app.route("/deco-shadow", methods=["POST"])
    @shield_protect_flask(mode="shadow")
    def deco_shadow():
        return jsonify({"ok": True})

    @app.route("/mw/login", methods=["GET", "POST"])
    def mw_login():
        return jsonify({"ok": True, "has_telemetry": getattr(g, "synapse_telemetry", None) is not None})

    @app.route("/public", methods=["POST"])
    def public():
        return jsonify({"ok": True})

    SynapseFlaskMiddleware(app, protected_paths=["/mw"])
    return app.test_client()


@pytest.mark.parametrize("path", ["/deco", "/mw/login"])
def test_flask_contract(flask_client, path):
    c = flask_client
    r = c.post(path, json={})
    assert r.status_code == 403
    assert "Missing token" in r.get_json()["error"]

    tok = make_token()
    r = c.post(path, json={"token": tok})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["has_telemetry"] is True
    if path == "/deco":
        assert r.headers.get("X-Synapse-Decision") == "allow"

    r = c.post(path, json={"token": tok})
    assert r.status_code == 403, "replayed token must be rejected"

    r = c.post(path, json={"x": 1}, headers={"X-Synapse-Token": make_token()})
    assert r.status_code == 200

    r = c.post(path, json={"token": make_token(human=False)})
    assert r.status_code == 403

    r = c.post(path, json=OVERSIZED)
    assert r.status_code == 413


def test_flask_shadow_and_passthrough(flask_client):
    c = flask_client
    r = c.post("/deco-shadow", json={"token": make_token(human=False)})
    assert r.status_code == 200
    assert r.headers.get("X-Synapse-Decision") == "shadow-block"

    # Middleware: unprotected path and safe method are not gated.
    assert c.post("/public", json={}).status_code == 200
    r = c.get("/mw/login")
    assert r.status_code == 200
    assert r.get_json()["has_telemetry"] is False

    # Non-JSON body falls back to header-only token extraction.
    r = c.post("/mw/login", data="plain text", content_type="text/plain")
    assert r.status_code == 403


def test_flask_middleware_init_app_factory_pattern():
    flask = pytest.importorskip("flask")
    from synapse_shield.flask import SynapseFlaskMiddleware

    mw = SynapseFlaskMiddleware(protected_paths=["/api"], max_risk_score=10.0)
    assert mw.app is None
    app = flask.Flask(f"factory_{uuid.uuid4().hex}")

    @app.route("/api/x", methods=["POST"])
    def x():
        return "ok"

    mw.init_app(app)
    assert app.test_client().post("/api/x", json={}).status_code == 403


@pytest.mark.parametrize("paths", [None, []])
def test_empty_protected_paths_protect_every_mutating_route_in_all_adapters(paths):
    """Fail-safe, identical semantics everywhere: no protected_paths = protect every POST/PUT/PATCH.

    Previously Flask, FastAPI and Django protected NOTHING when the list was empty while Sanic,
    Litestar and raw ASGI protected EVERYTHING, so adding the middleware without paths silently
    disabled protection on half of the integrations.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Flask
    flask = pytest.importorskip("flask")
    from synapse_shield.flask import SynapseFlaskMiddleware

    fapp = flask.Flask(f"nopaths_{uuid.uuid4().hex}")

    @fapp.route("/anything", methods=["GET", "POST"])
    def anything():
        return "ok"

    SynapseFlaskMiddleware(fapp, protected_paths=paths)
    fc = fapp.test_client()
    assert fc.post("/anything", json={}).status_code == 403
    assert fc.get("/anything").status_code == 200

    # FastAPI / Starlette
    from synapse_shield.middleware import SynapseShieldMiddleware

    api = FastAPI()
    api.add_api_route("/anything", lambda: {"ok": True}, methods=["GET", "POST"])
    api.add_middleware(SynapseShieldMiddleware, protected_paths=paths)
    ac = TestClient(api)
    assert ac.post("/anything", json={}).status_code == 403
    assert ac.get("/anything").status_code == 200

    # Raw ASGI
    from synapse_shield.asgi import SynapseShieldASGIMiddleware

    raw = FastAPI()
    raw.add_api_route("/anything", lambda: {"ok": True}, methods=["GET", "POST"])
    rc = TestClient(SynapseShieldASGIMiddleware(raw, protected_paths=paths))
    assert rc.post("/anything", json={}).status_code == 403
    assert rc.get("/anything").status_code == 200

    # Litestar
    pytest.importorskip("litestar")
    from litestar import Litestar, get, post
    from litestar.middleware import DefineMiddleware
    from litestar.testing import TestClient as LitestarClient

    from synapse_shield.litestar import LitestarSynapseMiddleware

    @post("/anything", status_code=200)
    async def l_post() -> dict:
        return {"ok": True}

    @get("/anything")
    async def l_get() -> dict:
        return {"ok": True}

    lapp = Litestar(route_handlers=[l_post, l_get],
                    middleware=[DefineMiddleware(LitestarSynapseMiddleware, protected_paths=paths)])
    with LitestarClient(lapp) as lc:
        assert lc.post("/anything", json={}).status_code == 403
        assert lc.get("/anything").status_code == 200

    # Sanic (optional dependency: skip only this adapter when it is not installed)
    try:
        import sanic  # noqa: F401
        from sanic_testing.testing import SanicASGITestClient
    except ImportError:
        SanicASGITestClient = None
    if SanicASGITestClient is not None:
        sc = SanicASGITestClient(_sanic_app(protected_paths=paths))
        assert _sanic_post(sc, "/public", json={}).status == 403
        assert _sanic_get(sc, "/mw/login").status == 200

    # Django
    pytest.importorskip("django")
    from unittest.mock import MagicMock

    from django.conf import settings

    if not settings.configured:
        # Same global settings as tests/test_frameworks.py, so test order never matters.
        settings.configure(SYNAPSE_SHIELD_PROTECTED_PATHS=["/api/protected"], SYNAPSE_SHIELD_MAX_RISK=50.0)
    from synapse_shield.django import SynapseShieldMiddleware as DjangoMiddleware

    dmw = DjangoMiddleware(get_response=lambda r: "OK")
    dmw.protected_paths = paths or []
    req = MagicMock(path="/anything", method="POST", body=b"{}", META={"REMOTE_ADDR": "127.0.0.1"})
    assert dmw.process_request(req).status_code == 403
    assert dmw.process_request(MagicMock(path="/anything", method="GET")) is None


# --------------------------------------------------------------------------------------------
# Sanic
# --------------------------------------------------------------------------------------------


def _sanic_app(**mw_kwargs):
    sanic = pytest.importorskip("sanic")
    pytest.importorskip("sanic_testing")
    from sanic import json as sjson

    from synapse_shield.sanic import SynapseSanicMiddleware, shield_protect_sanic

    app = sanic.Sanic(f"sanic_contract_{uuid.uuid4().hex}")

    @app.post("/deco")
    @shield_protect_sanic()
    async def deco(request):
        return sjson({"ok": True, "has_telemetry": request.ctx.synapse_telemetry is not None})

    @app.post("/deco-shadow")
    @shield_protect_sanic(mode="shadow")
    async def deco_shadow(request):
        return sjson({"ok": True})

    @app.route("/mw/login", methods=["GET", "POST"])
    async def mw_login(request):
        return sjson({"ok": True, "has_telemetry": getattr(request.ctx, "synapse_telemetry", None) is not None})

    @app.post("/public")
    async def public(request):
        return sjson({"ok": True})

    app.register_middleware(SynapseSanicMiddleware(**mw_kwargs), "request")
    return app


def _sanic_post(client, path, **kw):
    async def go():
        _, resp = await client.post(path, **kw)
        return resp

    return asyncio.run(go())


def _sanic_get(client, path):
    async def go():
        _, resp = await client.get(path)
        return resp

    return asyncio.run(go())


@pytest.fixture
def sanic_client():
    pytest.importorskip("sanic")
    pytest.importorskip("sanic_testing")
    app = _sanic_app(protected_paths=["/mw"])
    from sanic_testing.testing import SanicASGITestClient

    return SanicASGITestClient(app)


@pytest.mark.parametrize("path", ["/deco", "/mw/login"])
def test_sanic_contract(sanic_client, path):
    c = sanic_client
    r = _sanic_post(c, path, json={})
    assert r.status == 403
    assert "Missing token" in _error_text(r.json)

    tok = make_token()
    r = _sanic_post(c, path, json={"token": tok})
    assert r.status == 200, r.text
    assert r.json["has_telemetry"] is True
    if path == "/deco":
        assert r.headers.get("x-synapse-decision") == "allow"

    r = _sanic_post(c, path, json={"token": tok})
    assert r.status == 403, "replayed token must be rejected"

    r = _sanic_post(c, path, json={"x": 1}, headers={"X-Synapse-Token": make_token()})
    assert r.status == 200

    r = _sanic_post(c, path, json={"token": make_token(human=False)})
    assert r.status == 403
    assert r.headers.get("x-synapse-decision") is not None

    r = _sanic_post(c, path, json=OVERSIZED)
    assert r.status == 413


def test_sanic_shadow_and_passthrough(sanic_client):
    c = sanic_client
    r = _sanic_post(c, "/deco-shadow", json={"token": make_token(human=False)})
    assert r.status == 200
    assert r.headers.get("x-synapse-decision") == "shadow-block"

    assert _sanic_post(c, "/public", json={}).status == 200
    r = _sanic_get(c, "/mw/login")
    assert r.status == 200
    assert r.json["has_telemetry"] is False

    # Malformed JSON body must not crash the adapter: it is treated as "no body token".
    r = _sanic_post(c, "/mw/login", content="{not json", headers={"content-type": "application/json"})
    assert r.status == 403


def test_sanic_middleware_without_paths_protects_everything():
    """No protected_paths = protect every mutating route (same semantics as every other adapter)."""
    pytest.importorskip("sanic")
    pytest.importorskip("sanic_testing")
    from sanic_testing.testing import SanicASGITestClient

    app = _sanic_app()
    c = SanicASGITestClient(app)
    assert _sanic_post(c, "/public", json={}).status == 403


def test_sanic_unavailable_raises_import_error(monkeypatch):
    import synapse_shield.sanic as sanic_mod

    monkeypatch.setattr(sanic_mod, "SANIC_AVAILABLE", False)
    with pytest.raises(ImportError, match="Sanic is required"):
        sanic_mod.shield_protect_sanic()
    with pytest.raises(ImportError, match="Sanic is required"):
        sanic_mod.SynapseSanicMiddleware()


def test_sanic_old_json_signature_fallback(monkeypatch):
    """Older Sanic `json()` helpers have no `headers=` kwarg; the adapter must still block."""
    pytest.importorskip("sanic")
    import synapse_shield.sanic as sanic_mod

    calls = []

    def legacy_json(body, status=200):
        calls.append(status)
        return {"body": body, "status": status}

    monkeypatch.setattr(sanic_mod, "sanic_json", legacy_json)

    class Req:
        body = b"{}"
        remote_addr = "127.0.0.1"
        headers = {"user-agent": "legacy"}
        json = {}
        path = "/x"
        method = "POST"

        class ctx:
            pass

    @sanic_mod.shield_protect_sanic()
    async def handler(request):  # pragma: no cover - must not be reached
        return "reached"

    res = asyncio.run(handler(Req()))
    assert res["status"] == 403
    res = asyncio.run(sanic_mod.SynapseSanicMiddleware()(Req()))
    assert res["status"] == 403
    assert calls == [403, 403]


# --------------------------------------------------------------------------------------------
# FastAPI / Starlette (middleware.py)
# --------------------------------------------------------------------------------------------


@pytest.fixture
def fastapi_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse_shield.middleware import SynapseShieldMiddleware, shield_protect

    app = FastAPI()

    @app.post("/deco")
    @shield_protect()
    async def deco(request: FastAPIRequest):
        return {"ok": True, "has_telemetry": request.state.synapse_telemetry is not None}

    @app.post("/deco-positional")
    @shield_protect()
    async def deco_positional(request: FastAPIRequest):
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("plain")

    @app.post("/deco-shadow")
    @shield_protect(mode="shadow")
    async def deco_shadow(request: FastAPIRequest):
        return {"ok": True}

    @app.api_route("/mw/login", methods=["GET", "POST"])
    async def mw_login(request: FastAPIRequest):
        return {"ok": True, "has_telemetry": getattr(request.state, "synapse_telemetry", None) is not None}

    @app.post("/public")
    async def public():
        return {"ok": True}

    app.add_middleware(SynapseShieldMiddleware, protected_paths=["/mw"])
    return TestClient(app)


@pytest.mark.parametrize("path", ["/deco", "/mw/login"])
def test_fastapi_contract(fastapi_client, path):
    c = fastapi_client
    r = c.post(path, json={})
    assert r.status_code == 403
    assert "Missing token" in r.text

    tok = make_token()
    r = c.post(path, json={"token": tok})
    assert r.status_code == 200, r.text
    assert r.json()["has_telemetry"] is True
    assert r.headers.get("x-synapse-decision") == "allow"

    r = c.post(path, json={"token": tok})
    assert r.status_code == 403, "replayed token must be rejected"

    r = c.post(path, json={"x": 1}, headers={"X-Synapse-Token": make_token()})
    assert r.status_code == 200

    r = c.post(path, json={"token": make_token(human=False)})
    assert r.status_code == 403

    r = c.post(path, json=OVERSIZED)
    assert r.status_code == 413

    r = c.post(path, content=b"{broken", headers={"content-type": "application/json"})
    assert r.status_code == 400

    # Token in header + unparsable body: body is ignored, token decides. A fresh User-Agent starts
    # a new session: re-sending identical telemetry in one session is (correctly) flagged as
    # "Session Behavioral Invariance".
    hdrs = {"content-type": "application/json", "X-Synapse-Token": make_token(), "User-Agent": "fresh-session"}
    r = c.post(path, content=b"{broken", headers=hdrs)
    assert r.status_code == 200, r.text


def test_fastapi_shadow_passthrough_and_response_headers(fastapi_client):
    c = fastapi_client
    r = c.post("/deco-shadow", json={"token": make_token(human=False)})
    assert r.status_code == 200 and r.headers.get("x-synapse-decision") == "shadow-block"
    r = c.post("/deco-positional", json={"token": make_token()})
    assert r.text == "plain" and r.headers.get("x-synapse-decision") == "allow"
    assert c.post("/public", json={}).status_code == 200
    r = c.get("/mw/login")
    assert r.status_code == 200 and r.json()["has_telemetry"] is False


def test_fastapi_decorator_without_request_param_is_a_500():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse_shield.middleware import shield_protect

    app = FastAPI()

    @app.post("/broken")
    @shield_protect()
    async def broken():
        return {"ok": True}

    r = TestClient(app).post("/broken", json={})
    assert r.status_code == 500 and "Request object not found" in r.text


def test_fastapi_unavailable_raises_import_error(monkeypatch):
    import synapse_shield.middleware as mw

    monkeypatch.setattr(mw, "FASTAPI_AVAILABLE", False)
    with pytest.raises(ImportError):
        mw.shield_protect()
    with pytest.raises(ImportError):
        mw.SynapseShieldMiddleware(app=None)


# --------------------------------------------------------------------------------------------
# Litestar
# --------------------------------------------------------------------------------------------


@pytest.fixture
def litestar_client():
    pytest.importorskip("litestar")
    from litestar import Litestar, Request, get, post
    from litestar.middleware import DefineMiddleware
    from litestar.testing import TestClient

    from synapse_shield.litestar import LitestarSynapseMiddleware, synapse_guard

    @post("/guard", guards=[synapse_guard()], status_code=200)
    async def guarded(request: Request) -> dict:
        return {"ok": True, "has_telemetry": getattr(request.state, "synapse_telemetry", None) is not None}

    @post("/guard-shadow", guards=[synapse_guard(mode="shadow")], status_code=200)
    async def guarded_shadow(request: Request) -> dict:
        return {"ok": True}

    @post("/mw/login", status_code=200)
    async def mw_login(request: Request) -> dict:
        return {"ok": True, "has_telemetry": "synapse_telemetry" in request.scope.get("state", {})}

    @get("/mw/login")
    async def mw_login_get() -> dict:
        return {"ok": True}

    @post("/public", status_code=200)
    async def public() -> dict:
        return {"ok": True}

    app = Litestar(
        route_handlers=[guarded, guarded_shadow, mw_login, mw_login_get, public],
        middleware=[DefineMiddleware(LitestarSynapseMiddleware, protected_paths=["/mw"])],
    )
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", ["/guard", "/mw/login"])
def test_litestar_contract(litestar_client, path):
    c = litestar_client
    r = c.post(path, json={})
    assert r.status_code == 403
    assert "Missing token" in r.text

    tok = make_token()
    r = c.post(path, json={"token": tok})
    assert r.status_code == 200, r.text
    assert r.json()["has_telemetry"] is True

    r = c.post(path, json={"token": tok})
    assert r.status_code == 403, "replayed token must be rejected"

    r = c.post(path, json={"x": 1}, headers={"X-Synapse-Token": make_token()})
    assert r.status_code == 200

    r = c.post(path, json={"token": make_token(human=False)})
    assert r.status_code == 403


def test_litestar_middleware_payload_limit_and_passthrough(litestar_client):
    c = litestar_client
    assert c.post("/mw/login", json=OVERSIZED).status_code == 413
    assert c.post("/public", json={}).status_code == 200
    assert c.get("/mw/login").status_code == 200


def test_litestar_guard_shadow_mode(litestar_client):
    r = litestar_client.post("/guard-shadow", json={"token": make_token(human=False)})
    assert r.status_code == 200


def test_litestar_unavailable_raises_import_error(monkeypatch):
    import synapse_shield.litestar as ls_mod

    monkeypatch.setattr(ls_mod, "LITESTAR_AVAILABLE", False)
    with pytest.raises(ImportError, match="Litestar is required"):
        ls_mod.synapse_guard()
    with pytest.raises(ImportError, match="Litestar is required"):
        ls_mod.LitestarSynapseMiddleware(app=None)
