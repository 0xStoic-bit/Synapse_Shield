"""
Synapse Shield - Behavioral Biometrics & Bot Mitigation Engine
"""

from .engine import analyze_behavior, poisson_anomaly_score
from .features import extract_features
from .middleware import shield_protect, SynapseShieldMiddleware
from .tokens import generate_challenge, verify_and_consume_token

__version__ = "0.5.0"
__all__ = [
    "analyze_behavior",
    "poisson_anomaly_score",
    "extract_features",
    "shield_protect",
    "SynapseShieldMiddleware",
    "generate_challenge",
    "verify_and_consume_token",
]