"""
Synapse Shield - Core Security Evaluation Engine
Provides framework-agnostic evaluation of incoming request telemetry,
cryptographic tokens, IP reputation, and session behavioral biometrics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any

from synapse_shield.engine import analyze_behavior
from synapse_shield.storage import get_storage
from synapse_shield.tokens import verify_and_consume_token

try:
    from synapse_shield.metrics import (
        METRICS_ENABLED,
        synapse_inference_latency_seconds,
        synapse_requests_total,
    )
except ImportError:
    METRICS_ENABLED = False

MAX_PAYLOAD_SIZE = 262_144  # 256 KB


@dataclass
class SynapseDecision:
    """
    Standardized security decision object returned by Synapse Shield.
    """
    allowed: bool
    status_code: int = 200
    error_message: str | None = None
    classification: str = "Human"
    bot_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    telemetry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to JSON-serializable dictionary."""
        if self.allowed:
            return {
                "status": "allowed",
                "classification": self.classification,
                "bot_score": f"{self.bot_score}%",
            }
        return {
            "error": self.error_message or "Access Denied by Synapse Shield",
            "classification": self.classification,
            "bot_score": f"{self.bot_score}%",
            "reasons": self.reasons,
        }


async def evaluate_synapse_request(
    client_ip: str,
    user_agent: str,
    token: str | None,
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
) -> SynapseDecision:
    """
    Unified security evaluation pipeline.
    1. Checks if client IP is currently banned.
    2. Validates cryptographic HMAC challenge token & ensures single-use consumption.
    3. Retrieves multi-turn session kinematic history.
    4. Executes biometric analysis engine (Rust SIMD / AI inference) in a threadpool.
    5. Records session metrics & strikes on malicious activity.
    6. Emits Prometheus metrics if configured.
    """
    storage = get_storage()

    # 1. IP Ban check
    if storage.is_ip_banned(client_ip):
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="IP address is banned by Synapse Shield.",
            classification="Bot",
            bot_score=100.0,
            reasons=["IP_BANNED"],
        )

    # 2. Token presence check
    if not token:
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="[Synapse Shield] Missing token.",
            classification="Bot",
            bot_score=100.0,
            reasons=["MISSING_TOKEN"],
        )

    # 3. Token cryptographic verification & replay protection
    is_valid, reason, telemetry = verify_and_consume_token(token)
    if not is_valid:
        if reason != "TOKEN_EXPIRED":
            storage.record_bot_strike(client_ip)
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message=f"[Synapse Shield] Token Error: {reason}",
            classification="Bot",
            bot_score=100.0,
            reasons=[f"TOKEN_{reason}"],
        )

    # 4. Multi-turn Session Identification & History
    session_id = f"{client_ip}:{hashlib.md5(user_agent.encode('utf-8', errors='ignore')).hexdigest()[:8]}"
    session_history = storage.get_session_telemetries(session_id, window_sec=300)

    # 5. Biometric Kinematics & AI Inference (non-blocking threadpool)
    is_penalized = storage.is_ip_banned(client_ip)
    start_time = time.perf_counter()
    bot_score, classification, reasons, details = await asyncio.to_thread(
        analyze_behavior, telemetry, 1, is_penalized, accessibility_mode, session_history
    )
    latency = time.perf_counter() - start_time

    # Record kinematic session features
    features = details.get("features", {}) if isinstance(details, dict) else {}
    storage.record_session_telemetry(
        session_id,
        {
            "avg_jerk": features.get("avg_jerk", 0.0),
            "straightness": features.get("straightness", 1.0),
            "submovement_count": features.get("submovement_count", 0),
            "spectral_purity": features.get("spectral_purity", 0.0),
        },
        max_history=10,
        window_sec=300,
    )

    if METRICS_ENABLED:
        synapse_inference_latency_seconds.observe(latency)

    # 6. Bot decision threshold
    if bot_score >= max_risk_score or classification == "Bot":
        storage.record_bot_strike(client_ip)
        if METRICS_ENABLED:
            synapse_requests_total.labels(status="block", classification=classification).inc()
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="Access Denied by Synapse Shield",
            classification=classification,
            bot_score=bot_score,
            reasons=reasons,
            telemetry=telemetry,
        )

    if METRICS_ENABLED:
        synapse_requests_total.labels(status="allow", classification=classification).inc()

    return SynapseDecision(
        allowed=True,
        classification=classification,
        bot_score=bot_score,
        telemetry=telemetry,
    )
