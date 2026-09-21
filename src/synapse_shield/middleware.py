"""
Synapse Shield - Drop-in FastAPI / Python Middleware
Provides two integration methods:
  1. @shield_protect decorator for individual routes
  2. SynapseShieldMiddleware class for global path-based protection
"""

import asyncio
import hashlib
import json
import time
from functools import wraps

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from synapse_shield.engine import analyze_behavior
from synapse_shield.storage import get_storage
from synapse_shield.tokens import verify_and_consume_token

try:
    from synapse_shield.metrics import (
        METRICS_ENABLED,
        synapse_inference_latency_seconds,
        synapse_requests_total,
    )
except ImportError:
    METRICS_ENABLED = False
def shield_protect(max_risk_score: float = 50.0, accessibility_mode: bool = False):
    """
    Decorator to protect any FastAPI endpoint with Synapse Shield behavioral biometrics.
    Usage:
        @app.post("/login")
        @shield_protect(max_risk_score=50.0, accessibility_mode=False)
        async def login(request: Request):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request object
            request: Request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(status_code=500, detail="Request object not found in endpoint signature")

            client_ip = request.client.host if request.client else "127.0.0.1"
            storage = get_storage()
            if storage.is_ip_banned(client_ip):
                raise HTTPException(
                    status_code=403, 
                    detail={"error": "IP address is banned by Synapse Shield.", "ip": client_ip}
                )

            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            token = body.get("token")
            if not token:
                raise HTTPException(status_code=403, detail="[Synapse Shield] Missing token.")

            is_valid, reason, telemetry = verify_and_consume_token(token)
            if not is_valid:
                if reason != "TOKEN_EXPIRED":
                    storage.record_bot_strike(client_ip)
                raise HTTPException(status_code=403, detail=f"[Synapse Shield] Token Error: {reason}")

            # İzolasyon (Decoupling) -> Telemetry'yi state'e koy
            request.state.telemetry = telemetry

            # Session Identifier & History (Client IP + User-Agent Hash)
            user_agent = request.headers.get("user-agent", "unknown")
            session_id = f"{client_ip}:{hashlib.md5(user_agent.encode()).hexdigest()[:8]}"
            session_history = storage.get_session_telemetries(session_id, window_sec=300)

            is_penalized = storage.is_ip_banned(client_ip)
            start_time = time.perf_counter()
            bot_score, classification, reasons, details = await asyncio.to_thread(
                analyze_behavior, telemetry, 1, is_penalized, accessibility_mode, session_history
            )
            latency = time.perf_counter() - start_time
            
            # Kinetik metrikleri oturum geçmişine kaydet
            features = details.get("features", {})
            storage.record_session_telemetry(
                session_id,
                {
                    "avg_jerk": features.get("avg_jerk", 0.0),
                    "straightness": features.get("straightness", 1.0),
                    "submovement_count": features.get("submovement_count", 0),
                    "spectral_purity": features.get("spectral_purity", 0.0),
                },
                max_history=10,
                window_sec=300
            )
            
            if METRICS_ENABLED:
                synapse_inference_latency_seconds.observe(latency)

            if bot_score >= max_risk_score or classification == "Bot":
                storage.record_bot_strike(client_ip)
                if METRICS_ENABLED:
                    synapse_requests_total.labels(status="block", classification=classification).inc()
                raise HTTPException(
                    status_code=403, 
                    detail={
                        "error": "Access Denied by Synapse Shield",
                        "classification": classification,
                        "bot_score": f"{bot_score}%",
                        "reasons": reasons
                    }
                )

            if METRICS_ENABLED:
                synapse_requests_total.labels(status="allow", classification=classification).inc()
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class SynapseShieldMiddleware(BaseHTTPMiddleware):
    """
    Global ASGI middleware — belirli path prefix'lerini Synapse Shield ile korur.

    Usage:
        from synapse_shield import SynapseShieldMiddleware

        app = FastAPI()
        app.add_middleware(
            SynapseShieldMiddleware,
            protected_paths=["/api/auth", "/checkout"],
            max_risk_score=50.0
        )

    NOT: Starlette BaseHTTPMiddleware request.body() çağrısını dahili olarak cache'ler,
    bu sayede downstream endpoint'ler body'yi tekrar okuyabilir. Ancak streaming
    request'lerde bu pattern uygun değildir.
    """

    def __init__(self, app, protected_paths: list | None = None, max_risk_score: float = 50.0, accessibility_mode: bool = False):
        super().__init__(app)
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score
        self.accessibility_mode = accessibility_mode

    async def dispatch(self, request, call_next):
        # Sadece korunan path'leri kontrol et
        if not any(request.url.path.startswith(p) for p in self.protected_paths):
            return await call_next(request)

        # Sadece state-changing HTTP method'larını kontrol et (GET/HEAD/OPTIONS atla)
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        storage = get_storage()
        if storage.is_ip_banned(client_ip):
            return JSONResponse(
                status_code=403,
                content={"error": "[Synapse Shield] IP address is banned.", "ip": client_ip}
            )

        try:
            body_bytes = await request.body()
            body = json.loads(body_bytes)
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "[Synapse Shield] Invalid JSON payload."}
            )

        token = body.get("token")
        if not token:
            return JSONResponse(
                status_code=403,
                content={"error": "[Synapse Shield] Missing token."}
            )

        is_valid, reason, telemetry = verify_and_consume_token(token)
        if not is_valid:
            if reason != "TOKEN_EXPIRED":
                storage.record_bot_strike(client_ip)
            return JSONResponse(
                status_code=403,
                content={"error": f"[Synapse Shield] Token Error: {reason}"}
            )

        request.state.telemetry = telemetry

        # Session Identifier & History (Client IP + User-Agent Hash)
        user_agent = request.headers.get("user-agent", "unknown")
        session_id = f"{client_ip}:{hashlib.md5(user_agent.encode()).hexdigest()[:8]}"
        session_history = storage.get_session_telemetries(session_id, window_sec=300)

        is_penalized = storage.is_ip_banned(client_ip)
        start_time = time.perf_counter()
        bot_score, classification, reasons, details = await asyncio.to_thread(
            analyze_behavior, telemetry, 1, is_penalized, self.accessibility_mode, session_history
        )
        latency = time.perf_counter() - start_time
        
        # Kinetik metrikleri oturum geçmişine kaydet
        features = details.get("features", {})
        storage.record_session_telemetry(
            session_id,
            {
                "avg_jerk": features.get("avg_jerk", 0.0),
                "straightness": features.get("straightness", 1.0),
                "submovement_count": features.get("submovement_count", 0),
                "spectral_purity": features.get("spectral_purity", 0.0),
            },
            max_history=10,
            window_sec=300
        )
        
        if METRICS_ENABLED:
            synapse_inference_latency_seconds.observe(latency)

        if bot_score >= self.max_risk_score or classification == "Bot":
            storage.record_bot_strike(client_ip)
            if METRICS_ENABLED:
                synapse_requests_total.labels(status="block", classification=classification).inc()
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access Denied by Synapse Shield",
                    "classification": classification,
                    "bot_score": f"{bot_score}%",
                    "reasons": reasons,
                }
            )

        if METRICS_ENABLED:
            synapse_requests_total.labels(status="allow", classification=classification).inc()
        return await call_next(request)
