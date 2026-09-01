from functools import wraps
from flask import request, jsonify
try:
    from .engine import analyze_behavior
except ImportError:
    from engine import analyze_behavior

def shield_protect_flask(max_risk_score: float = 50.0, accessibility_mode: bool = False):
    """
    Flask decorator to protect endpoints with Synapse Shield.
    Usage:
        @app.route("/login", methods=["POST"])
        @shield_protect_flask(max_risk_score=50.0)
        def login():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                body = request.get_json(force=True, silent=True)
                if not body:
                    raise ValueError("No JSON payload")
                telemetry = body.get("telemetry") or body
            except Exception:
                return jsonify({"error": "[Synapse Shield] Missing behavioral telemetry payload."}), 403
                
            bot_score, classification, reasons, _ = analyze_behavior(
                telemetry, 1, False, accessibility_mode
            )
            
            if bot_score >= max_risk_score:
                return jsonify({
                    "error": "Access Denied by Synapse Shield",
                    "classification": classification,
                    "bot_score": f"{bot_score}%",
                    "reasons": reasons,
                }), 403
                
            return func(*args, **kwargs)
        return wrapper
    return decorator
