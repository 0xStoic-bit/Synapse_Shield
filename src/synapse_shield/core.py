"""
Synapse Shield - Core Security Evaluation Engine
Provides framework-agnostic evaluation of incoming request telemetry,
cryptographic tokens, IP reputation, session behavioral biometrics,
Proof-of-Work (PoW) verification, Reverse Proxy IP resolution, and Shadow Mode.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
import hashlib
import ipaddress
import os
import time
from typing import Any

from synapse_shield.engine import analyze_behavior
from synapse_shield.storage import get_storage
from synapse_shield.tokens import SECRET_KEY, generate_pow_salt, verify_and_consume_pow, verify_and_consume_token

try:
    from synapse_shield.metrics import (
        METRICS_ENABLED,
        synapse_inference_latency_seconds,
        synapse_pow_solved_total,
        synapse_replays_detected_total,
        synapse_requests_total,
        synapse_shadow_requests_total,
    )
except ImportError:
    METRICS_ENABLED = False
    synapse_inference_latency_seconds = None
    synapse_requests_total = None
    synapse_replays_detected_total = None
    synapse_pow_solved_total = None
    synapse_shadow_requests_total = None

MAX_PAYLOAD_SIZE = 262_144  # 256 KB


def get_trusted_proxies() -> set[str]:
    """Return set of trusted reverse proxy IP addresses."""
    raw = os.environ.get("SYNAPSE_TRUSTED_PROXIES", "127.0.0.1,::1,localhost")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def resolve_client_ip(
    client_host: str,
    headers: Any,
    trusted_proxies: set[str] | None = None,
) -> str:
    """
    Safely resolve the originating client IP address behind reverse proxies (Nginx, Cloudflare, AWS ALB).
    Only trusts forwarding headers (CF-Connecting-IP, X-Real-IP, X-Forwarded-For) if client_host is
    explicitly in the trusted proxy set. Prevents IP spoofing while protecting legitimate visitors.
    """
    if trusted_proxies is None:
        trusted_proxies = get_trusted_proxies()

    client_ip = (client_host or "127.0.0.1").strip()

    if client_ip not in trusted_proxies:
        return client_ip

    header_dict: dict[str, str] = {}
    if isinstance(headers, dict):
        header_dict = {k.lower().replace("_", "-"): str(v) for k, v in headers.items()}
    elif isinstance(headers, (list, tuple)):
        # ASGI headers format: list of (bytes, bytes)
        for item in headers:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                k, v = item
                k_str = k.decode("latin1", errors="ignore").lower().replace("_", "-") if isinstance(k, bytes) else str(k).lower()
                v_str = v.decode("latin1", errors="ignore") if isinstance(v, bytes) else str(v)
                header_dict[k_str] = v_str
    elif hasattr(headers, "get"):
        # Mapping-like (Starlette / Flask / Django request.headers)
        for key in ["cf-connecting-ip", "x-real-ip", "x-forwarded-for"]:
            val = headers.get(key) or headers.get(key.upper()) or headers.get(f"HTTP_{key.upper().replace('-', '_')}")
            if val:
                header_dict[key] = str(val)

    # 1. Cloudflare True Client IP
    cf_ip = header_dict.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    # 2. Standard single reverse proxy header
    real_ip = header_dict.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # 3. Traversed X-Forwarded-For chain: client, proxy1, proxy2
    forwarded = header_dict.get("x-forwarded-for") or header_dict.get("http-x-forwarded-for")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        for ip in reversed(ips):
            if ip not in trusted_proxies:
                return ip
        if ips:
            return ips[0]

    return client_ip


def anonymize_ip(ip_str: str) -> str:
    """
    Anonymize IP address according to SYNAPSE_PRIVACY_MODE (strict, hash, or default mask).
    - 'hash': Rotating daily HMAC-SHA256 digest (Zero-PII GDPR compliant).
    - 'strict': Subnet truncation (/24 for IPv4, /64 for IPv6).
    """
    mode = os.environ.get("SYNAPSE_PRIVACY_MODE", "strict").lower()
    if mode == "hash":
        daily_salt = f"{date.today().isoformat()}:{SECRET_KEY.hex()}"
        hashed = hashlib.sha256(f"{daily_salt}:{ip_str}".encode()).hexdigest()[:16]
        return f"anon_{hashed}"

    try:
        ip = ipaddress.ip_address(ip_str)
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if ip.version == 4:
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            return f"{network.network_address.exploded.rsplit('.', 1)[0]}.*"
        else:
            network = ipaddress.ip_network(f"{ip}/64", strict=False)
            prefix = network.network_address.exploded.split(":")[:4]
            return f"{':'.join(prefix)}:*:*:*:*"
    except ValueError:
        return "unknown"


@dataclass
class SynapseDecision:
    """
    Standardized security decision object returned by Synapse Shield across all frameworks.
    """
    allowed: bool
    status_code: int = 200
    error_message: str | None = None
    classification: str = "Human"
    bot_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    telemetry: dict[str, Any] | None = None
    action: str = "allow"  # allow | block | challenge | shadow_block
    shadow_mode: bool = False
    challenge_data: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to JSON-serializable dictionary."""
        if self.action == "challenge":
            return {
                "status": "challenge_required",
                "action": "challenge",
                "classification": self.classification,
                "bot_score": f"{self.bot_score}%",
                "reasons": self.reasons,
                "pow_difficulty": self.challenge_data.get("pow_difficulty", 4) if self.challenge_data else 4,
                "pow_salt": self.challenge_data.get("pow_salt", "") if self.challenge_data else "",
            }

        if self.allowed:
            base = {
                "status": "allowed",
                "classification": self.classification,
                "bot_score": f"{self.bot_score}%",
            }
            if self.shadow_mode:
                base["shadow_mode"] = True
                base["simulated_action"] = "block" if self.action == "shadow_block" else "allow"
                if self.reasons:
                    base["reasons"] = self.reasons
            return base

        return {
            "error": self.error_message or "Access Denied by Synapse Shield",
            "classification": self.classification,
            "bot_score": f"{self.bot_score}%",
            "reasons": self.reasons,
        }


def evaluate_synapse_request_sync(
    client_ip: str,
    user_agent: str,
    token: str | None,
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
    pow_nonce: str | None = None,
    pow_salt: str | None = None,
    enable_pow: bool = False,
) -> SynapseDecision:
    """
    Synchronous core security evaluation engine.
    Used natively by synchronous frameworks (Django, Flask) and wrapped in threadpools for ASGI/FastAPI.
    """
    storage = get_storage()
    is_shadow = mode.lower() == "shadow"

    # 1. IP Ban check
    if storage.is_ip_banned(client_ip):
        if is_shadow:
            if METRICS_ENABLED and synapse_shadow_requests_total is not None:
                synapse_shadow_requests_total.labels(action="block", classification="Bot").inc()
            return SynapseDecision(
                allowed=True,
                status_code=200,
                classification="Bot",
                bot_score=100.0,
                reasons=["IP_BANNED"],
                action="shadow_block",
                shadow_mode=True,
                headers={"X-Synapse-Decision": "shadow-block", "X-Synapse-Risk-Score": "100.0%"},
            )
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="IP address is banned by Synapse Shield.",
            classification="Bot",
            bot_score=100.0,
            reasons=["IP_BANNED"],
            action="block",
            headers={"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"},
        )

    # 2. Token presence check
    if not token:
        if is_shadow:
            if METRICS_ENABLED and synapse_shadow_requests_total is not None:
                synapse_shadow_requests_total.labels(action="block", classification="Bot").inc()
            return SynapseDecision(
                allowed=True,
                status_code=200,
                classification="Bot",
                bot_score=100.0,
                reasons=["MISSING_TOKEN"],
                action="shadow_block",
                shadow_mode=True,
                headers={"X-Synapse-Decision": "shadow-block", "X-Synapse-Risk-Score": "100.0%"},
            )
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="[Synapse Shield] Missing token.",
            classification="Bot",
            bot_score=100.0,
            reasons=["MISSING_TOKEN"],
            action="block",
            headers={"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"},
        )

    # 3. Token cryptographic verification & replay protection
    is_valid, reason, telemetry = verify_and_consume_token(token)
    if not is_valid:
        if "Replay" in reason or "Yeniden Oynatma" in reason:
            if METRICS_ENABLED and synapse_replays_detected_total is not None:
                synapse_replays_detected_total.inc()

        if reason != "TOKEN_EXPIRED":
            storage.record_bot_strike(client_ip)

        if is_shadow:
            if METRICS_ENABLED and synapse_shadow_requests_total is not None:
                synapse_shadow_requests_total.labels(action="block", classification="Bot").inc()
            return SynapseDecision(
                allowed=True,
                status_code=200,
                classification="Bot",
                bot_score=100.0,
                reasons=[f"TOKEN_{reason}"],
                action="shadow_block",
                shadow_mode=True,
                headers={"X-Synapse-Decision": "shadow-block", "X-Synapse-Risk-Score": "100.0%"},
            )

        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message=f"[Synapse Shield] Token Error: {reason}",
            classification="Bot",
            bot_score=100.0,
            reasons=[f"TOKEN_{reason}"],
            action="block",
            headers={"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"},
        )

    # 4. Multi-turn Session Identification & History
    # Tie session to client_ip to prevent spoofing / rotating User-Agent to bypass session invariance
    session_id = f"ip_{client_ip}"
    session_history = storage.get_session_telemetries(session_id, window_sec=300)

    # 4.5 Sliding-Window Request Frequency (Poisson Anomaly & DoS protection)
    recent_request_count = storage.record_and_get_request_count(client_ip, window_sec=10)
    if recent_request_count > 100:
        storage.ban_ip(client_ip, duration_sec=900, reason="Extreme request frequency (DoS protection: >100 req/10s)")
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="[Synapse Shield] Extreme request frequency detected. IP temporarily banned.",
            classification="Bot",
            bot_score=100.0,
            reasons=["Extreme request frequency (>100 req/10s)"],
            action="block",
            headers={"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"},
        )

    # 5. Biometric Kinematics & AI Inference
    is_penalized = storage.is_ip_banned(client_ip)
    start_time = time.perf_counter()
    bot_score, classification, reasons, details = analyze_behavior(
        telemetry, recent_request_count, is_penalized, accessibility_mode, session_history
    )
    latency = time.perf_counter() - start_time

    # Record kinematic session features
    features = details.get("features", {}) if isinstance(details, dict) else {}
    storage.record_session_telemetry(
        session_id,
        {
            "avg_jerk": features.get("avg_jerk", 0.0),
            "straightness": features.get("straightness", 1.0),
            "total_distance": features.get("total_distance", 0.0),
            "submovement_count": features.get("submovement_count", 0),
            "spectral_purity": features.get("spectral_purity", 0.0),
        },
        max_history=10,
        window_sec=300,
    )

    if METRICS_ENABLED and synapse_inference_latency_seconds is not None:
        synapse_inference_latency_seconds.observe(latency)

    # 6. Gray Area Proof-of-Work (Smart Challenge) Flow
    feat = details.get("features", {}) if isinstance(details, dict) else {}
    total_interactive_events = feat.get("total_interactive_events",
        feat.get("mouse_points", 0) + feat.get("key_count", 0) + feat.get("touch_event_count", 0) + feat.get("click_count", 0)
    )
    mouse_points = feat.get("mouse_points", 0)
    is_stealth = feat.get("is_stealth_automation", False) or (details.get("threat_type") == "STEALTH_AUTOMATION")
    has_invariance = any("Session Behavioral Invariance" in r for r in reasons) or (details.get("threat_type") == "SESSION_INVARIANCE_BOT")

    hard_bot_violation = (
        total_interactive_events == 0
        or (1 <= mouse_points <= 2 and not feat.get("touch_supported", False))
        or is_stealth
        or has_invariance
    )

    if enable_pow and (35.0 <= bot_score < 55.0) and not hard_bot_violation:
        is_pow_valid = False
        if pow_nonce and pow_salt:
            is_pow_valid = verify_and_consume_pow(pow_salt, str(pow_nonce), client_ip=client_ip)

        if is_pow_valid:
            bot_score = max(0.0, bot_score - 20.0)
            classification = "Human"
            reasons.append("Gray area PoW Challenge successfully solved (Risk reduced).")
            if METRICS_ENABLED and synapse_pow_solved_total is not None:
                synapse_pow_solved_total.inc()
        elif not is_shadow:
            # Emit challenge request
            challenge_salt = generate_pow_salt(client_ip=client_ip)
            return SynapseDecision(
                allowed=False,
                status_code=429,
                error_message="Proof of Work Challenge Required",
                classification=classification,
                bot_score=bot_score,
                reasons=reasons,
                telemetry=telemetry,
                action="challenge",
                challenge_data={"pow_difficulty": 4, "pow_salt": challenge_salt},
                headers={
                    "X-Synapse-Action": "challenge",
                    "X-Synapse-Risk-Score": f"{bot_score:.1f}%",
                    "Retry-After": "2",
                },
            )

    # 7. Final Decision Threshold
    is_mitigated = bot_score >= max_risk_score or classification == "Bot"

    if is_mitigated:
        storage.record_bot_strike(client_ip)

        if is_shadow:
            if METRICS_ENABLED and synapse_shadow_requests_total is not None:
                synapse_shadow_requests_total.labels(action="block", classification=classification).inc()
            return SynapseDecision(
                allowed=True,
                status_code=200,
                classification=classification,
                bot_score=bot_score,
                reasons=reasons,
                telemetry=telemetry,
                action="shadow_block",
                shadow_mode=True,
                headers={
                    "X-Synapse-Decision": "shadow-block",
                    "X-Synapse-Risk-Score": f"{bot_score:.1f}%",
                },
            )

        if METRICS_ENABLED and synapse_requests_total is not None:
            synapse_requests_total.labels(status="block", classification=classification).inc()

        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="Access Denied by Synapse Shield",
            classification=classification,
            bot_score=bot_score,
            reasons=reasons,
            telemetry=telemetry,
            action="block",
            headers={
                "X-Synapse-Decision": "block",
                "X-Synapse-Risk-Score": f"{bot_score:.1f}%",
            },
        )

    # Legitimate Human
    if is_shadow:
        if METRICS_ENABLED and synapse_shadow_requests_total is not None:
            synapse_shadow_requests_total.labels(action="allow", classification=classification).inc()
    elif METRICS_ENABLED and synapse_requests_total is not None:
        synapse_requests_total.labels(status="allow", classification=classification).inc()

    return SynapseDecision(
        allowed=True,
        status_code=200,
        classification=classification,
        bot_score=bot_score,
        reasons=reasons,
        telemetry=telemetry,
        action="allow",
        shadow_mode=is_shadow,
        headers={
            "X-Synapse-Decision": "allow",
            "X-Synapse-Risk-Score": f"{bot_score:.1f}%",
        },
    )


async def evaluate_synapse_request(
    client_ip: str,
    user_agent: str,
    token: str | None,
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
    pow_nonce: str | None = None,
    pow_salt: str | None = None,
    enable_pow: bool = False,
) -> SynapseDecision:
    """
    Asynchronous wrapper for non-blocking invocation in ASGI event loops.
    """
    return await asyncio.to_thread(
        evaluate_synapse_request_sync,
        client_ip=client_ip,
        user_agent=user_agent,
        token=token,
        max_risk_score=max_risk_score,
        accessibility_mode=accessibility_mode,
        mode=mode,
        pow_nonce=pow_nonce,
        pow_salt=pow_salt,
        enable_pow=enable_pow,
    )
