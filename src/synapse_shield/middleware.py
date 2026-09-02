"""
Synapse Shield - Drop-in FastAPI / Python Middleware
Provides two integration methods:
  1. @shield_protect decorator for individual routes
  2. SynapseShieldMiddleware class for global path-based protection
"""

from functools import wraps
import asyncio
import json
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from synapse_shield.engine import analyze_behavior
import time
from synapse_shield.tokens import verify_and_consume_token
try:
    from synapse_shield.metrics import METRICS_ENABLED, synapse_requests_total, synapse_inference_latency_seconds
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

            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            token = body.get("token")
            if not token:
                raise HTTPException(status_code=403, detail="[Synapse Shield] Missing token.")

            is_valid, reason, telemetry = verify_and_consume_token(token)
            if not is_valid:
                raise HTTPException(status_code=403, detail=f"[Synapse Shield] Token Error: {reason}")

            # İzolasyon (Decoupling) -> Telemetry'yi state'e koy
            request.state.telemetry = telemetry

            start_time = time.perf_counter()
            bot_score, classification, reasons, _ = await asyncio.to_thread(
                analyze_behavior, telemetry, 1, False, accessibility_mode
            )
            latency = time.perf_counter() - start_time
            
            if METRICS_ENABLED:
                synapse_inference_latency_seconds.observe(latency)

            if bot_score >= max_risk_score:
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

    def __init__(self, app, protected_paths: list = None, max_risk_score: float = 50.0, accessibility_mode: bool = False):
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
            return JSONResponse(
                status_code=403,
                content={"error": f"[Synapse Shield] Token Error: {reason}"}
            )

        request.state.telemetry = telemetry

        start_time = time.perf_counter()
        bot_score, classification, reasons, _ = await asyncio.to_thread(
            analyze_behavior, telemetry, 1, False, self.accessibility_mode
        )
        latency = time.perf_counter() - start_time
        
        if METRICS_ENABLED:
            synapse_inference_latency_seconds.observe(latency)

        if bot_score >= self.max_risk_score:
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
