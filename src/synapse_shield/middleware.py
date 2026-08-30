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
try:
    from .engine import analyze_behavior
except ImportError:
    from engine import analyze_behavior

def shield_protect(max_risk_score: float = 50.0):
    """
    Decorator to protect any FastAPI endpoint with Synapse Shield behavioral biometrics.
    Usage:
        @app.post("/login")
        @shield_protect(max_risk_score=50.0)
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

            # Extract telemetry from header or body
            telemetry = None
            try:
                body = await request.json()
                telemetry = body.get("telemetry") or body
            except Exception:
                pass

            if not telemetry:
                raise HTTPException(status_code=403, detail="[Synapse Shield] Missing behavioral telemetry payload.")

            bot_score, classification, reasons, _ = await asyncio.to_thread(analyze_behavior, telemetry)

            if bot_score >= max_risk_score:
                raise HTTPException(
                    status_code=403, 
                    detail={
                        "error": "Access Denied by Synapse Shield",
                        "classification": classification,
                        "bot_score": f"{bot_score}%",
                        "reasons": reasons
                    }
                )

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

    def __init__(self, app, protected_paths: list = None, max_risk_score: float = 50.0):
        super().__init__(app)
        self.protected_paths = protected_paths or []
        self.max_risk_score = max_risk_score

    async def dispatch(self, request, call_next):
        # Sadece korunan path'leri kontrol et
        if not any(request.url.path.startswith(p) for p in self.protected_paths):
            return await call_next(request)

        # Sadece state-changing HTTP method'larını kontrol et (GET/HEAD/OPTIONS atla)
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # Body'yi oku — Starlette dahili olarak cache'ler
        try:
            body_bytes = await request.body()
            body = json.loads(body_bytes)
            telemetry = body.get("telemetry") or body
        except Exception:
            return JSONResponse(
                status_code=403,
                content={"error": "[Synapse Shield] Missing or invalid behavioral telemetry payload."}
            )

        bot_score, classification, reasons, _ = await asyncio.to_thread(
            analyze_behavior, telemetry
        )

        if bot_score >= self.max_risk_score:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access Denied by Synapse Shield",
                    "classification": classification,
                    "bot_score": f"{bot_score}%",
                    "reasons": reasons,
                }
            )

        return await call_next(request)
