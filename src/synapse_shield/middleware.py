"""
Synapse Shield - Drop-in FastAPI / Python Middleware
Allows developers to protect any route with a single decorator: @shield_protect
"""

from functools import wraps
from fastapi import Request, HTTPException
from .engine import analyze_behavior

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

            bot_score, classification, reasons, _ = analyze_behavior(telemetry)

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
