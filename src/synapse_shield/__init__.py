"""
Synapse Shield - Behavioral Biometrics & Bot Mitigation Engine
"""

from ._version import __version__
from .core import (
    SynapseDecision,
    anonymize_ip,
    evaluate_synapse_request,
    evaluate_synapse_request_sync,
    resolve_client_ip,
)
from .engine import analyze_behavior, poisson_anomaly_score
from .features import evaluate_curvature_zerocopy, extract_features
from .middleware import SynapseShieldMiddleware, shield_protect
from .tokens import generate_challenge, verify_and_consume_token, verify_and_consume_pow
from .asgi import SynapseShieldASGIMiddleware

try:
    from . import synapse_core_rs
except ImportError:
    try:
        import synapse_core_rs
    except ImportError:
        synapse_core_rs = None

__all__ = [
    "__version__",
    "SynapseShieldMiddleware",
    "SynapseShieldASGIMiddleware",
    "SynapseDecision",
    "evaluate_synapse_request",
    "evaluate_synapse_request_sync",
    "resolve_client_ip",
    "anonymize_ip",
    "analyze_behavior",
    "extract_features",
    "evaluate_curvature_zerocopy",
    "generate_challenge",
    "poisson_anomaly_score",
    "shield_protect",
    "verify_and_consume_token",
    "verify_and_consume_pow",
    "synapse_core_rs",
]
