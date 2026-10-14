"""
Synapse Shield - Sanic Integration
Provides native Route Decorators and Middleware for Sanic applications.
Seamlessly works in both Sanic Native HTTP Server and ASGI modes.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from synapse_shield.core import MAX_PAYLOAD_SIZE, evaluate_synapse_request

try:
    from sanic import json as sanic_json
    from sanic.request import Request as SanicRequest
    SANIC_AVAILABLE = True
except ImportError:
    SANIC_AVAILABLE = False
    sanic_json = None
    SanicRequest = Any


def shield_protect_sanic(
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
) -> Callable:
    """
    Decorator to protect Sanic endpoints with Synapse Shield behavioral biometrics.

    Usage:
        from sanic import Sanic
        from synapse_shield.sanic import shield_protect_sanic

        app = Sanic("my_app")

        @app.post("/api/login")
        @shield_protect_sanic(max_risk_score=50.0)
        async def login(request):
            return text("Authenticated!")
    """
    if not SANIC_AVAILABLE:
        raise ImportError(
            "Sanic is required to use shield_protect_sanic. Install it via 'pip install synapse-shield[sanic]' or 'pip install sanic'"
        )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: SanicRequest, *args: Any, **kwargs: Any) -> Any:
            # 1. 256 KB Payload Size Guard
            if request.body and len(request.body) > MAX_PAYLOAD_SIZE:
                return sanic_json(
                    {"error": "Payload Too Large: Maximum allowed size is 256 KB"},
                    status=413,
                )

            # 2. Extract Client IP & User-Agent (native Sanic attributes)
            client_ip = request.remote_addr or getattr(request, "ip", "127.0.0.1") or "127.0.0.1"
            user_agent = request.headers.get("user-agent", "unknown")

            # 3. Extract JSON Body & Token
            try:
                body = request.json or {}
            except Exception:
                return sanic_json(
                    {"error": "[Synapse Shield] Missing or invalid JSON body."},
                    status=400,
                )

            token = body.get("token") if isinstance(body, dict) else None

            # 4. Centralized Evaluation
            decision = await evaluate_synapse_request(
                client_ip=client_ip,
                user_agent=user_agent,
                token=token,
                max_risk_score=max_risk_score,
                accessibility_mode=accessibility_mode,
            )

            if not decision.allowed:
                return sanic_json(decision.to_dict(), status=decision.status_code)

            # 5. Inject Telemetry into Sanic request context
            if hasattr(request, "ctx"):
                request.ctx.synapse_telemetry = decision.telemetry
                request.ctx.synapse_decision = decision

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


class SynapseSanicMiddleware:
    """
    Sanic Request Middleware for global or path-based protection.

    Usage:
        from sanic import Sanic
        from synapse_shield.sanic import SynapseSanicMiddleware

        app = Sanic("my_app")
        middleware = SynapseSanicMiddleware(
            protected_paths=["/api/auth", "/checkout"],
            max_risk_score=50.0
        )
        app.register_middleware(middleware, "request")
    """

    def __init__(
        self,
        protected_paths: list[str] | None = None,
        max_risk_score: float = 50.0,
        accessibility_mode: bool = False,
    ) -> None:
        if not SANIC_AVAILABLE:
            raise ImportError(
                "Sanic is required to use SynapseSanicMiddleware. Install it via 'pip install sanic'"
            )
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score
        self.accessibility_mode = accessibility_mode

    async def __call__(self, request: SanicRequest) -> Any:
        path = getattr(request, "path", "")
        if self.protected_paths and not any(path.startswith(p) for p in self.protected_paths):
            return None

        method = getattr(request, "method", "GET").upper()
        if method not in ("POST", "PUT", "PATCH"):
            return None

        # 256 KB Check
        if request.body and len(request.body) > MAX_PAYLOAD_SIZE:
            return sanic_json(
                {"error": "Payload Too Large: Maximum allowed size is 256 KB"},
                status=413,
            )

        client_ip = request.remote_addr or getattr(request, "ip", "127.0.0.1") or "127.0.0.1"
        user_agent = request.headers.get("user-agent", "unknown")

        try:
            body = request.json or {}
        except Exception:
            return sanic_json(
                {"error": "[Synapse Shield] Missing or invalid JSON body."},
                status=400,
            )

        token = body.get("token") if isinstance(body, dict) else None

        decision = await evaluate_synapse_request(
            client_ip=client_ip,
            user_agent=user_agent,
            token=token,
            max_risk_score=self.max_risk_score,
            accessibility_mode=self.accessibility_mode,
        )

        if not decision.allowed:
            return sanic_json(decision.to_dict(), status=decision.status_code)

        if hasattr(request, "ctx"):
            request.ctx.synapse_telemetry = decision.telemetry
            request.ctx.synapse_decision = decision

        return None
