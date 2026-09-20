"""
Synapse Shield - Behavioral Biometrics & Bot Mitigation Engine
"""

from .engine import analyze_behavior, poisson_anomaly_score
from .features import extract_features
from .middleware import SynapseShieldMiddleware, shield_protect
from .tokens import generate_challenge, verify_and_consume_token, verify_and_consume_pow

__version__ = "0.7.6"
__all__ = [
    "SynapseShieldMiddleware",
    "analyze_behavior",
    "extract_features",
    "generate_challenge",
    "poisson_anomaly_score",
    "shield_protect",
    "verify_and_consume_token",
    "verify_and_consume_pow",
]