"""
Synapse Shield - Flask Integration
Route decorator and middleware for protecting Flask endpoints with behavioral biometrics.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import g, jsonify, make_response, request

from synapse_shield.core import (
    MAX_PAYLOAD_SIZE,
    evaluate_synapse_request_sync,
    resolve_client_ip,
)


def shield_protect_flask(
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
) -> Callable:
    """
    Flask route decorator to enforce Synapse Shield behavioral protection.

    Usage:
        @app.route("/login", methods=["POST"])
        @shield_protect_flask(max_risk_score=50.0, mode="enforce")
        def login():
            # g.synapse_telemetry is available
            return "OK"
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. 256 KB Memory DoS Protection
            if request.content_length and request.content_length > MAX_PAYLOAD_SIZE:
                return jsonify({"error": "Payload Too Large: Maximum allowed size is 256 KB"}), 413

            # 2. Extract Client IP with Reverse Proxy Support
            client_ip = resolve_client_ip(request.remote_addr or "127.0.0.1", request.headers)
            user_agent = request.headers.get("user-agent", "unknown")

            # 3. Extract Token & PoW (Header priority, fallback to JSON body)
            token = request.headers.get("X-Synapse-Token")
            pow_nonce = request.headers.get("X-Synapse-PoW-Nonce")
            pow_salt = request.headers.get("X-Synapse-PoW-Salt")

            body_json: dict[str, Any] = {}
            if request.is_json:
                try:
                    parsed = request.get_json(silent=True)
                    if isinstance(parsed, dict):
                        body_json = parsed
                except Exception:
                    return jsonify({"error": "[Synapse Shield] Invalid JSON payload."}), 400

            if not token:
                token = body_json.get("token")
            if not pow_nonce:
                pow_nonce = body_json.get("pow_nonce")
            if not pow_salt:
                pow_salt = body_json.get("pow_salt")

            # 4. Centralized Cryptographic & Behavioral Evaluation
            decision = evaluate_synapse_request_sync(
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
                response = jsonify(decision.to_dict())
                response.status_code = decision.status_code
                for hk, hv in decision.headers.items():
                    response.headers[hk] = hv
                return response

            # Store in Flask global application context
            g.synapse_telemetry = decision.telemetry
            g.synapse_decision = decision

            # Execute endpoint handler
            res = func(*args, **kwargs)
            response = make_response(res)
            if decision.headers:
                for hk, hv in decision.headers.items():
                    response.headers[hk] = hv
            return response

        return wrapper

    return decorator


class SynapseFlaskMiddleware:
    """
    Application-wide Flask middleware for protecting specific path prefixes.
    """

    def __init__(
        self,
        app: Any = None,
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

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        app.before_request(self._before_request)

    def _before_request(self) -> Any:
        if not self.protected_paths or not any(request.path.startswith(p) for p in self.protected_paths):
            return None

        if request.method not in ("POST", "PUT", "PATCH"):
            return None

        if request.content_length and request.content_length > MAX_PAYLOAD_SIZE:
            return jsonify({"error": "Payload Too Large: Maximum allowed size is 256 KB"}), 413

        client_ip = resolve_client_ip(request.remote_addr or "127.0.0.1", request.headers)
        user_agent = request.headers.get("user-agent", "unknown")

        token = request.headers.get("X-Synapse-Token")
        pow_nonce = request.headers.get("X-Synapse-PoW-Nonce")
        pow_salt = request.headers.get("X-Synapse-PoW-Salt")

        body_json: dict[str, Any] = {}
        if request.is_json:
            try:
                parsed = request.get_json(silent=True)
                if isinstance(parsed, dict):
                    body_json = parsed
            except Exception:
                return jsonify({"error": "[Synapse Shield] Invalid JSON payload."}), 400

        if not token:
            token = body_json.get("token")
        if not pow_nonce:
            pow_nonce = body_json.get("pow_nonce")
        if not pow_salt:
            pow_salt = body_json.get("pow_salt")

        decision = evaluate_synapse_request_sync(
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
            resp = jsonify(decision.to_dict())
            resp.status_code = decision.status_code
            for hk, hv in decision.headers.items():
                resp.headers[hk] = hv
            return resp

        g.synapse_telemetry = decision.telemetry
        g.synapse_decision = decision
        return None
