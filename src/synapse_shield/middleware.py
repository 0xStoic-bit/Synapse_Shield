"""
Synapse Shield - Drop-in FastAPI / Starlette Middleware
Provides two integration methods:
  1. @shield_protect decorator for individual routes
  2. SynapseShieldMiddleware class for global path-based protection
"""

from __future__ import annotations

from functools import wraps
import json
from typing import Any, Callable

try:
    from fastapi import HTTPException, Request
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    HTTPException = Exception  # type: ignore
    Request = Any  # type: ignore
    BaseHTTPMiddleware = object  # type: ignore
    JSONResponse = Any  # type: ignore

from synapse_shield.core import (
    MAX_PAYLOAD_SIZE,
    evaluate_synapse_request,
    resolve_client_ip,
)


def shield_protect(
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
) -> Callable:
    """
    Decorator to protect any FastAPI endpoint with Synapse Shield behavioral biometrics.

    Usage:
        @app.post("/login")
        @shield_protect(max_risk_score=50.0, mode="enforce")
        async def login(request: Request):
            telemetry = request.state.synapse_telemetry
            ...
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI and Starlette are required to use @shield_protect.")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request object
            request: Request | None = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(status_code=500, detail="Request object not found in endpoint signature")

            # 1. Client IP with Reverse Proxy Support
            client_ip = resolve_client_ip(request.client.host if request.client else "127.0.0.1", request.headers)
            user_agent = request.headers.get("user-agent", "unknown")

            # 2. Extract Token & PoW (Header priority, fallback to JSON body)
            token = request.headers.get("x-synapse-token")
            pow_nonce = request.headers.get("x-synapse-pow-nonce")
            pow_salt = request.headers.get("x-synapse-pow-salt")

            body_json: dict[str, Any] = {}
            try:
                body_bytes = await request.body()
                if len(body_bytes) > MAX_PAYLOAD_SIZE:
                    raise HTTPException(
                        status_code=413, detail={"error": "Payload Too Large: Maximum allowed size is 256 KB"}
                    )
                if body_bytes:
                    body_json = json.loads(body_bytes)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            if not token and isinstance(body_json, dict):
                token = body_json.get("token")
            if not pow_nonce and isinstance(body_json, dict):
                pow_nonce = body_json.get("pow_nonce")
            if not pow_salt and isinstance(body_json, dict):
                pow_salt = body_json.get("pow_salt")

            # 3. Centralized Evaluation Pipeline
            decision = await evaluate_synapse_request(
                client_ip=client_ip,
                user_agent=user_agent,
                token=token,
                max_risk_score=max_risk_score,
                accessibility_mode=accessibility_mode,
                mode=mode,
                pow_nonce=str(pow_nonce) if pow_nonce else None,
                pow_salt=str(pow_salt) if pow_salt else None,
            )

            if not decision.allowed:
                raise HTTPException(
                    status_code=decision.status_code,
                    detail=decision.to_dict(),
                    headers=decision.headers,
                )

            # Inject decision and telemetry into request state
            request.state.telemetry = decision.telemetry
            request.state.synapse_telemetry = decision.telemetry
            request.state.synapse_decision = decision

            response = await func(*args, **kwargs)
            if hasattr(response, "headers") and decision.headers:
                for hk, hv in decision.headers.items():
                    response.headers[hk] = hv
            elif isinstance(response, dict) and decision.headers:
                return JSONResponse(content=response, headers=decision.headers)
            return response

        return wrapper

    return decorator


class SynapseShieldMiddleware(BaseHTTPMiddleware):
    """
    Global ASGI middleware for FastAPI / Starlette.
    Protects specified path prefixes with centralized behavioral biometrics and DDoS mitigation.
    """

    def __init__(
        self,
        app: Any,
        protected_paths: list[str] | None = None,
        max_risk_score: float = 50.0,
        accessibility_mode: bool = False,
        mode: str = "enforce",
    ) -> None:
        if not FASTAPI_AVAILABLE:
            raise ImportError("Starlette is required to use SynapseShieldMiddleware.")
        super().__init__(app)
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score
        self.accessibility_mode = accessibility_mode
        self.mode = mode

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        # Check path filter
        if not any(request.url.path.startswith(p) for p in self.protected_paths):
            return await call_next(request)

        # Only protect state-changing methods
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # 1. 256 KB Memory Cap
        try:
            body_bytes = await request.body()
            if len(body_bytes) > MAX_PAYLOAD_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"error": "Payload Too Large: Maximum allowed size is 256 KB"},
                )
            body_json = json.loads(body_bytes) if body_bytes else {}
        except Exception:
            return JSONResponse(status_code=400, content={"error": "[Synapse Shield] Invalid JSON payload."})

        # 2. Extract Client IP with Reverse Proxy Support
        client_ip = resolve_client_ip(request.client.host if request.client else "127.0.0.1", request.headers)
        user_agent = request.headers.get("user-agent", "unknown")

        # 3. Extract Token & PoW (Header priority, fallback to JSON body)
        token = request.headers.get("x-synapse-token")
        pow_nonce = request.headers.get("x-synapse-pow-nonce")
        pow_salt = request.headers.get("x-synapse-pow-salt")

        if not token and isinstance(body_json, dict):
            token = body_json.get("token")
        if not pow_nonce and isinstance(body_json, dict):
            pow_nonce = body_json.get("pow_nonce")
        if not pow_salt and isinstance(body_json, dict):
            pow_salt = body_json.get("pow_salt")

        # 4. Centralized Evaluation Pipeline
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
            return JSONResponse(
                status_code=decision.status_code,
                content=decision.to_dict(),
                headers=decision.headers,
            )

        request.state.telemetry = decision.telemetry
        request.state.synapse_telemetry = decision.telemetry
        request.state.synapse_decision = decision

        response = await call_next(request)
        if hasattr(response, "headers") and decision.headers:
            for hk, hv in decision.headers.items():
                response.headers[hk] = hv
        return response
