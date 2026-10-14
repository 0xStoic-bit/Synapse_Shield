import json
from unittest.mock import MagicMock


def test_flask_middleware():
    from flask import Flask

    from synapse_shield.flask import shield_protect_flask

    app = Flask(__name__)

    @app.route("/api/test", methods=["POST"])
    @shield_protect_flask(max_risk_score=50.0)
    def test_route():
        return "OK"

    client = app.test_client()

    # Invalid telemetry payload -> 403
    res1 = client.post("/api/test", data="invalid json")
    assert res1.status_code == 403
    assert "Missing" in res1.json["error"]

    # Clean Human -> 200 OK
    res2 = client.post(
        "/api/test",
        json={
            "telemetry": {
                "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
                "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
            }
        },
    )
    assert res2.status_code == 200
    assert res2.data == b"OK"

    # Bot (Webdriver) -> 403 Blocked
    res3 = client.post("/api/test", json={"telemetry": {"browser": {"webdriver": True}}})
    assert res3.status_code == 403
    assert "Access Denied" in res3.json["error"]


def test_django_middleware():
    import pytest

    pytest.importorskip("django")
    from django.conf import settings

    from synapse_shield.django import SynapseShieldMiddleware

    if not settings.configured:
        settings.configure(SYNAPSE_SHIELD_PROTECTED_PATHS=["/api/protected"], SYNAPSE_SHIELD_MAX_RISK=50.0)

    middleware = SynapseShieldMiddleware(get_response=lambda r: "OK")

    # Mock GET request (not protected)
    req_get = MagicMock()
    req_get.path = "/api/protected"
    req_get.method = "GET"
    assert middleware.process_request(req_get) is None

    # Mock POST request (unprotected path)
    req_post_unprotected = MagicMock()
    req_post_unprotected.path = "/api/public"
    req_post_unprotected.method = "POST"
    assert middleware.process_request(req_post_unprotected) is None

    # Mock POST request (protected path, missing body)
    req_post_protected = MagicMock()
    req_post_protected.path = "/api/protected"
    req_post_protected.method = "POST"
    req_post_protected.body = b"invalid json"

    response = middleware.process_request(req_post_protected)
    assert response.status_code == 403
    assert b"Missing or invalid" in response.content

    # Clean human payload
    human_payload = {
        "telemetry": {
            "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
        }
    }
    req_post_protected.body = json.dumps(human_payload).encode()
    response2 = middleware.process_request(req_post_protected)
    assert response2 is None  # Allowed

    # Bot payload
    bot_payload = {"telemetry": {"browser": {"webdriver": True}}}
    req_post_protected.body = json.dumps(bot_payload).encode()
    response3 = middleware.process_request(req_post_protected)
    assert response3.status_code == 403
    assert b"Access Denied" in response3.content


def test_asgi_middleware_stream_replay_and_protection():
    import asyncio
    import base64
    from synapse_shield.asgi import SynapseShieldASGIMiddleware
    from synapse_shield.main import init_db
    from synapse_shield.tokens import generate_challenge

    async def _run():
        init_db()
        downstream_received_body = None

        async def mock_downstream_app(scope, receive, send):
            nonlocal downstream_received_body
            body = bytearray()
            more = True
            while more:
                msg = await receive()
                body.extend(msg.get("body", b""))
                more = msg.get("more_body", False)
            downstream_received_body = bytes(body)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"SUCCESS"})

        middleware = SynapseShieldASGIMiddleware(
            mock_downstream_app,
            protected_paths=["/protected"],
            max_risk_score=50.0,
        )

        # 1. Test 256 KB Payload Size Overflow -> 413
        huge_body = b"X" * (262_144 + 10)
        messages_huge = [
            {"type": "http.request", "body": huge_body, "more_body": False}
        ]
        sent_events_huge = []

        async def mock_receive_huge():
            return messages_huge.pop(0)

        async def mock_send_huge(event):
            sent_events_huge.append(event)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/protected/api",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"user-agent", b"pytest")],
        }

        await middleware(scope, mock_receive_huge, mock_send_huge)
        assert any(e.get("status") == 413 for e in sent_events_huge)
        assert downstream_received_body is None

        # 2. Test Valid Token & Telemetry -> Downstream successfully re-reads body!
        ch_data = generate_challenge()
        tok_envelope = {
            "challenge": ch_data["challenge"],
            "telemetry": {
                "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
                "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
            },
        }
        tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
        payload = json.dumps({"token": tok_b64, "other_field": "hello"}).encode()

        messages_valid = [
            {"type": "http.request", "body": payload, "more_body": False}
        ]
        sent_events_valid = []

        async def mock_receive_valid():
            return messages_valid.pop(0)

        async def mock_send_valid(event):
            sent_events_valid.append(event)

        await middleware(scope, mock_receive_valid, mock_send_valid)
        assert any(e.get("status") == 200 for e in sent_events_valid)
        assert downstream_received_body == payload  # Replay safety verified!
        assert "synapse_telemetry" in scope["state"]

    asyncio.run(_run())


def test_sanic_integration_mock():
    import asyncio
    import base64
    from synapse_shield.core import MAX_PAYLOAD_SIZE
    from synapse_shield.main import init_db
    from synapse_shield.tokens import generate_challenge

    async def _run():
        init_db()

        req = MagicMock()
        req.remote_addr = "127.0.0.1"
        req.headers = {"user-agent": "Sanic-Tester"}
        req.body = b"X" * (MAX_PAYLOAD_SIZE + 100)
        req.ctx = MagicMock()

        import synapse_shield.sanic as sanic_mod
        original_avail = sanic_mod.SANIC_AVAILABLE
        sanic_mod.SANIC_AVAILABLE = True
        sanic_mod.sanic_json = lambda body, status=200: {"body": body, "status": status}

        try:
            from synapse_shield.sanic import shield_protect_sanic

            @shield_protect_sanic(max_risk_score=50.0)
            async def sanic_endpoint(request):
                return "OK"

            # 1. 413 Payload too large
            res1 = await sanic_endpoint(req)
            assert res1["status"] == 413

            # 2. Valid token & human telemetry
            ch_data = generate_challenge()
            tok_envelope = {
                "challenge": ch_data["challenge"],
                "telemetry": {
                    "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
                    "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
                },
            }
            tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()

            req.body = json.dumps({"token": tok_b64}).encode()
            req.json = {"token": tok_b64}
            res2 = await sanic_endpoint(req)
            assert res2 == "OK"
            assert req.ctx.synapse_telemetry is not None
        finally:
            sanic_mod.SANIC_AVAILABLE = original_avail

    asyncio.run(_run())


def test_litestar_integration_mock():
    import asyncio
    import base64
    from synapse_shield.main import init_db
    from synapse_shield.tokens import generate_challenge

    async def _run():
        init_db()

        import synapse_shield.litestar as litestar_mod
        original_avail = litestar_mod.LITESTAR_AVAILABLE
        litestar_mod.LITESTAR_AVAILABLE = True

        try:
            from synapse_shield.litestar import synapse_guard

            guard = synapse_guard(max_risk_score=50.0)

            # Mock connection
            conn = MagicMock()
            conn.client.host = "127.0.0.1"
            conn.headers = {"user-agent": "Litestar-Tester"}
            conn.state = MagicMock()

            # Mock litestar Request
            from unittest.mock import AsyncMock
            conn.json = AsyncMock()

            ch_data = generate_challenge()
            tok_envelope = {
                "challenge": ch_data["challenge"],
                "telemetry": {
                    "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
                    "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20} for i in range(20)],
                },
            }
            tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
            conn.json.return_value = {"token": tok_b64}

            # Treat conn as Request
            litestar_mod.Request = type(conn)

            await guard(conn, None)
            assert conn.state.synapse_telemetry is not None
        finally:
            litestar_mod.LITESTAR_AVAILABLE = original_avail

    asyncio.run(_run())

