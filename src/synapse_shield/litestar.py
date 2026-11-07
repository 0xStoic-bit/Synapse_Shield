"""
Synapse Shield - Litestar Integration
Provides idiomatic Litestar Route Guards and Middleware.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from synapse_shield.core import PROTECTED_METHODS, MAX_PAYLOAD_SIZE, evaluate_synapse_request, resolve_client_ip

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler
    from litestar.types import Receive, Scope, Send

try:
    from litestar.exceptions import HTTPException, NotAuthorizedException, PermissionDeniedException
    from litestar.middleware.base import AbstractMiddleware
    LITESTAR_AVAILABLE = True
except ImportError:
    LITESTAR_AVAILABLE = False
    AbstractMiddleware = object
    class NotAuthorizedException(Exception):
        def __init__(self, detail: Any = None, *args: Any, **kwargs: Any) -> None:
            super().__init__(detail, *args)
            self.detail = detail

    class HTTPException(Exception):
        def __init__(self, detail: Any = None, *args: Any, status_code: int = 500, headers: Any = None, **kwargs: Any) -> None:
            super().__init__(detail, *args)
            self.detail = detail
            self.status_code = status_code
            self.headers = headers

    class PermissionDeniedException(Exception):
        def __init__(self, detail: Any = None, *args: Any, **kwargs: Any) -> None:
            super().__init__(detail, *args)
            self.detail = detail


def synapse_guard(
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
    enable_pow: bool = False,
) -> Callable:
    """
    Idiomatic Litestar Guard to protect specific routes or controllers.

    Usage:
        from litestar import post
        from synapse_shield.litestar import synapse_guard

        @post("/api/checkout", guards=[synapse_guard(max_risk_score=40.0, mode="enforce")])
        async def checkout(data: dict) -> dict:
            return {"status": "success"}
    """
    if not LITESTAR_AVAILABLE:
        raise ImportError(
            "Litestar is required to use synapse_guard. Install it via 'pip install synapse-shield[litestar]' or 'pip install litestar'"
        )

    async def guard(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
        client_host = connection.client.host if connection.client else "127.0.0.1"
        client_ip = resolve_client_ip(client_host, connection.headers)
        user_agent = connection.headers.get("user-agent", "unknown")

        declared_length = connection.headers.get("content-length")
        if declared_length and declared_length.isdigit() and int(declared_length) > MAX_PAYLOAD_SIZE:
            raise HTTPException(
                status_code=413, detail={"error": "Payload Too Large: Maximum allowed size is 256 KB"}
            )

        token = connection.headers.get("x-synapse-token")
        pow_nonce = connection.headers.get("x-synapse-pow-nonce")
        pow_salt = connection.headers.get("x-synapse-pow-salt")

        if (not token or not pow_nonce) and hasattr(connection, "json") and callable(connection.json):
            try:
                raw_body = b""
                try:
                    raw_body = await connection.body()
                except Exception:
                    raw_body = b""
                if isinstance(raw_body, (bytes, bytearray)) and len(raw_body) > MAX_PAYLOAD_SIZE:
                    raise HTTPException(
                        status_code=413, detail={"error": "Payload Too Large: Maximum allowed size is 256 KB"}
                    )
                body = await connection.json()
                if isinstance(body, dict):
                    if not token:
                        token = body.get("token")
                    if not pow_nonce:
                        pow_nonce = body.get("pow_nonce")
                    if not pow_salt:
                        pow_salt = body.get("pow_salt")
            except HTTPException:
                raise
            except Exception:
                pass

        decision = await evaluate_synapse_request(
            client_ip=client_ip,
            user_agent=user_agent,
            token=token,
            max_risk_score=max_risk_score,
            accessibility_mode=accessibility_mode,
            mode=mode,
            pow_nonce=str(pow_nonce) if pow_nonce else None,
            pow_salt=str(pow_salt) if pow_salt else None,
            enable_pow=enable_pow,
        )

        if not decision.allowed:
            if decision.status_code == 429:
                # Proof-of-work challenge: the client must see 429 + challenge body, not a 403 denial.
                raise HTTPException(
                    status_code=429, detail=decision.to_dict(), headers=decision.headers
                )
            raise PermissionDeniedException(detail=decision.to_dict())

        # Attach telemetry to connection state for downstream route access
        connection.state.synapse_telemetry = decision.telemetry
        connection.state.synapse_decision = decision

    return guard


class LitestarSynapseMiddleware(AbstractMiddleware):
    """
    Idiomatic Litestar application/router middleware.

    Usage:
        from litestar import Litestar
        from litestar.middleware import DefineMiddleware
        from synapse_shield.litestar import LitestarSynapseMiddleware

        app = Litestar(
            route_handlers=[...],
            middleware=[
                DefineMiddleware(
                    LitestarSynapseMiddleware,
                    protected_paths=["/api/auth", "/checkout"],
                    max_risk_score=50.0,
                    mode="enforce"
                )
            ]
        )
    """

    def __init__(
        self,
        app: Any,
        protected_paths: list[str] | None = None,
        max_risk_score: float = 50.0,
        accessibility_mode: bool = False,
        mode: str = "enforce",
        enable_pow: bool = False,
    ) -> None:
        if not LITESTAR_AVAILABLE:
            raise ImportError(
                "Litestar is required to use LitestarSynapseMiddleware. Install it via 'pip install litestar'"
            )
        super().__init__(app)
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score
        self.accessibility_mode = accessibility_mode
        self.mode = mode
        self.enable_pow = enable_pow
        # Built once, not per request.
        from synapse_shield.asgi import SynapseShieldASGIMiddleware

        self._asgi_handler = SynapseShieldASGIMiddleware(
            self.app,
            protected_paths=self.protected_paths,
            max_risk_score=self.max_risk_score,
            accessibility_mode=self.accessibility_mode,
            mode=self.mode,
            enable_pow=self.enable_pow,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if self.protected_paths and not any(path.startswith(p) for p in self.protected_paths):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in PROTECTED_METHODS:
            await self.app(scope, receive, send)
            return

        # Use universal ASGI replayable engine
        await self._asgi_handler(scope, receive, send)
