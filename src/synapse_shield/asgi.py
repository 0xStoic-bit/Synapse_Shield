"""
Synapse Shield - Universal ASGI 3.0 Middleware
Zero-dependency, high-performance bot mitigation middleware adhering to the ASGI 3.0 specification.
Compatible with Litestar, FastAPI, Starlette, Quart, Falcon, BlackSheep, and raw ASGI servers.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from synapse_shield.core import (
    MAX_PAYLOAD_SIZE,
    evaluate_synapse_request,
    resolve_client_ip,
)


class SynapseShieldASGIMiddleware:
    """
    Standard ASGI 3.0 Universal Middleware for Synapse Shield.

    Features:
    - Zero framework dependencies.
    - 256 KB memory DoS protection (413 Payload Too Large).
    - Stream replay safety (replayable_receive closure).
    - Reverse Proxy IP Resolution (X-Forwarded-For / CF-Connecting-IP).
    - Primary support for X-Synapse-Token HTTP header.
    - Shadow Mode (dry-run without blocking).
    - Injects telemetry into scope['state']['synapse_telemetry'].

    Usage:
        app = Litestar(...) # or FastAPI, Quart, etc.
        app = SynapseShieldASGIMiddleware(
            app,
            protected_paths=["/api/auth", "/checkout"],
            max_risk_score=50.0,
            accessibility_mode=False,
            mode="enforce",
        )
    """

    def __init__(
        self,
        app: Any,
        protected_paths: list[str] | None = None,
        max_risk_score: float = 50.0,
        accessibility_mode: bool = False,
        mode: str = "enforce",
    ) -> None:
        self.app = app
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score
        self.accessibility_mode = accessibility_mode
        self.mode = mode

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if self.protected_paths and not any(path.startswith(p) for p in self.protected_paths):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        # Extract client IP with Reverse Proxy Support
        client = scope.get("client")
        client_host = client[0] if client else "127.0.0.1"
        client_ip = resolve_client_ip(client_host, scope.get("headers", []))

        # Extract Headers (User-Agent, X-Synapse-Token, PoW)
        user_agent = "unknown"
        token = None
        pow_nonce = None
        pow_salt = None

        for header_name, header_val in scope.get("headers", []):
            h_name = header_name.lower()
            if h_name == b"user-agent":
                user_agent = header_val.decode("utf-8", errors="ignore")
            elif h_name == b"x-synapse-token":
                token = header_val.decode("utf-8", errors="ignore")
            elif h_name == b"x-synapse-pow-nonce":
                pow_nonce = header_val.decode("utf-8", errors="ignore")
            elif h_name == b"x-synapse-pow-salt":
                pow_salt = header_val.decode("utf-8", errors="ignore")

        # Buffer raw body chunks with strict 256 KB DoS cap
        body_bytes = bytearray()
        received_messages = []
        more_body = True

        while more_body:
            message = await receive()
            received_messages.append(message)

            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                body_bytes.extend(chunk)

                # 🛡️ 256 KB memory exhaustion protection
                if len(body_bytes) > MAX_PAYLOAD_SIZE:
                    await self._send_json_error(
                        send, 413, {"error": "Payload Too Large: Maximum allowed size is 256 KB"}
                    )
                    return

                more_body = message.get("more_body", False)
            elif message["type"] == "http.disconnect":
                return

        # Construct replayable receive callable for downstream
        replay_index = 0

        async def replayable_receive() -> dict[str, Any]:
            nonlocal replay_index
            if replay_index < len(received_messages):
                msg = received_messages[replay_index]
                replay_index += 1
                return msg
            return await receive()

        body_json: dict[str, Any] = {}
        if body_bytes:
            try:
                parsed = json.loads(body_bytes.decode("utf-8"))
                if isinstance(parsed, dict):
                    body_json = parsed
            except Exception:
                await self._send_json_error(send, 400, {"error": "Invalid JSON body format."})
                return

        # Fallback to JSON body if not present in headers
        if not token:
            token = body_json.get("token")
        if not pow_nonce:
            pow_nonce = body_json.get("pow_nonce")
        if not pow_salt:
            pow_salt = body_json.get("pow_salt")

        decision = await evaluate_synapse_request(
            client_ip=client_ip,
            user_agent=user_agent,
            token=token,
            max_risk_score=self.max_risk_score,
            accessibility_mode=self.accessibility_mode,
            mode=self.mode,
            pow_nonce=str(pow_nonce) if pow_nonce else None,
            pow_salt=str(pow_salt) if pow_salt else None,
        )

        if not decision.allowed:
            await self._send_json_error(send, decision.status_code, decision.to_dict(), extra_headers=decision.headers)
            return

        # Propagate telemetry to ASGI scope state
        if "state" not in scope:
            scope["state"] = {}
        if isinstance(scope["state"], dict):
            scope["state"]["synapse_telemetry"] = decision.telemetry
            scope["state"]["synapse_decision"] = decision

        # Hand off to downstream with stream replay capability
        await self.app(scope, replayable_receive, send)

    async def _send_json_error(
        self,
        send: Callable,
        status: int,
        data: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        payload = json.dumps(data).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("utf-8")),
        ]
        if extra_headers:
            for k, v in extra_headers.items():
                headers.append((k.lower().encode("latin1"), str(v).encode("latin1")))

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
                "more_body": False,
            }
        )
