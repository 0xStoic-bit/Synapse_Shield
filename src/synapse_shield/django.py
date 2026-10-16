"""
Synapse Shield - Django Middleware Integration
Enterprise bot mitigation and behavioral biometrics middleware for Django applications.
"""

from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from synapse_shield.core import (
    MAX_PAYLOAD_SIZE,
    evaluate_synapse_request_sync,
    resolve_client_ip,
)


class SynapseShieldMiddleware(MiddlewareMixin):
    """
    Production-ready Django middleware for Synapse Shield.

    Configuration in settings.py:
        MIDDLEWARE = [
            ...
            'synapse_shield.django.SynapseShieldMiddleware',
        ]

        SYNAPSE_SHIELD_PROTECTED_PATHS = ['/api/auth', '/checkout']
        SYNAPSE_SHIELD_MAX_RISK = 50.0
        SYNAPSE_SHIELD_ACCESSIBILITY = False
        SYNAPSE_SHIELD_MODE = 'enforce'  # or 'shadow'
    """

    def __init__(self, get_response: Any = None) -> None:
        super().__init__(get_response)
        from django.conf import settings

        self.protected_paths = getattr(settings, "SYNAPSE_SHIELD_PROTECTED_PATHS", [])
        self.max_risk_score = getattr(settings, "SYNAPSE_SHIELD_MAX_RISK", 50.0)
        self.accessibility_mode = getattr(settings, "SYNAPSE_SHIELD_ACCESSIBILITY", False)
        self.mode = getattr(settings, "SYNAPSE_SHIELD_MODE", "enforce")

    def process_request(self, request: Any) -> JsonResponse | None:
        if not self.protected_paths:
            return None

        if not any(request.path.startswith(p) for p in self.protected_paths):
            return None

        if request.method not in ("POST", "PUT", "PATCH"):
            return None

        # 1. 256 KB Memory DoS Protection
        if request.body and len(request.body) > MAX_PAYLOAD_SIZE:
            return JsonResponse(
                {"error": "Payload Too Large: Maximum allowed size is 256 KB"},
                status=413,
            )

        # 2. Extract Client IP with Reverse Proxy Support
        remote_addr = request.META.get("REMOTE_ADDR", "127.0.0.1")
        client_ip = resolve_client_ip(remote_addr, request.META)
        user_agent = request.META.get("HTTP_USER_AGENT", "unknown")

        # 3. Extract Token (Header priority, then JSON body)
        token = request.META.get("HTTP_X_SYNAPSE_TOKEN")
        pow_nonce = request.META.get("HTTP_X_SYNAPSE_POW_NONCE")
        pow_salt = request.META.get("HTTP_X_SYNAPSE_POW_SALT")

        body_json: dict[str, Any] = {}
        if request.body:
            try:
                parsed = json.loads(request.body)
                if isinstance(parsed, dict):
                    body_json = parsed
            except Exception:
                return JsonResponse(
                    {"error": "[Synapse Shield] Missing or invalid behavioral telemetry payload."},
                    status=403,
                )

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
            max_risk_score=self.max_risk_score,
            accessibility_mode=self.accessibility_mode,
            mode=self.mode,
            pow_nonce=str(pow_nonce) if pow_nonce else None,
            pow_salt=str(pow_salt) if pow_salt else None,
        )

        if not decision.allowed:
            resp = JsonResponse(decision.to_dict(), status=decision.status_code)
            for hk, hv in decision.headers.items():
                resp[hk] = hv
            return resp

        # Attach telemetry to request for downstream views
        request.synapse_telemetry = decision.telemetry
        request.synapse_decision = decision
        return None

    def process_response(self, request: Any, response: Any) -> Any:
        decision = getattr(request, "synapse_decision", None)
        if decision and hasattr(decision, "headers"):
            for hk, hv in decision.headers.items():
                response[hk] = hv
        return response
