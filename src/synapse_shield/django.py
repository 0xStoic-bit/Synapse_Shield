import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
try:
    from .engine import analyze_behavior
except ImportError:
    from engine import analyze_behavior

class SynapseShieldMiddleware(MiddlewareMixin):
    """
    Django middleware for Synapse Shield.
    Usage in settings.py:
        MIDDLEWARE = [
            ...
            'synapse_shield.django.SynapseShieldMiddleware',
        ]
        
    And define settings:
        SYNAPSE_SHIELD_PROTECTED_PATHS = ['/api/auth', '/checkout']
        SYNAPSE_SHIELD_MAX_RISK = 50.0
        SYNAPSE_SHIELD_ACCESSIBILITY = False
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        from django.conf import settings
        self.protected_paths = getattr(settings, 'SYNAPSE_SHIELD_PROTECTED_PATHS', [])
        self.max_risk_score = getattr(settings, 'SYNAPSE_SHIELD_MAX_RISK', 50.0)
        self.accessibility_mode = getattr(settings, 'SYNAPSE_SHIELD_ACCESSIBILITY', False)

    def process_request(self, request):
        if not self.protected_paths:
            return None

        if not any(request.path.startswith(p) for p in self.protected_paths):
            return None
        
        if request.method not in ("POST", "PUT", "PATCH"):
            return None
            
        try:
            body = json.loads(request.body)
            telemetry = body.get("telemetry") or body
        except Exception:
            return JsonResponse({"error": "[Synapse Shield] Missing or invalid behavioral telemetry payload."}, status=403)
            
        # Execute synchronously (Django's default blocking model)
        bot_score, classification, reasons, _ = analyze_behavior(
            telemetry, 1, False, self.accessibility_mode
        )
        
        if bot_score >= self.max_risk_score:
            return JsonResponse({
                "error": "Access Denied by Synapse Shield",
                "classification": classification,
                "bot_score": f"{bot_score}%",
                "reasons": reasons,
            }, status=403)
            
        return None
