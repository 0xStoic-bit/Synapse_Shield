"""
Synapse Shield - Behavioral Biometrics & Bot Mitigation Engine
"""

from .engine import SynapseEngine, analyze_behavior, poisson_anomaly_score
from .features import extract_features
from .middleware import shield_protect
from .tokens import generate_challenge, verify_and_consume_token

__version__ = "0.3.0"
__all__ = [
    "SynapseEngine",
    "analyze_behavior",
    "poisson_anomaly_score",
    "extract_features",
    "shield_protect",
    "generate_challenge",
    "verify_and_consume_token",
]