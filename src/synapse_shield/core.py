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
import logging
import os
import time
from typing import Any

from synapse_shield.cohort import OUTCOME_LABELS, cohort_of
from synapse_shield.engine import analyze_behavior
from synapse_shield.fingerprint import trajectory_fingerprint
from synapse_shield.rules import rule_codes
from synapse_shield.storage import client_strike_key, get_storage
from synapse_shield.tokens import SECRET_KEY, generate_pow_salt, verify_and_consume_pow, verify_and_consume_token

try:
    from synapse_shield.metrics import (
        METRICS_ENABLED,
        synapse_inference_latency_seconds,
        synapse_pow_solved_total,
        synapse_replays_detected_total,
        synapse_requests_total,
        synapse_shadow_cohort_total,
        synapse_shadow_outcomes_total,
        synapse_shadow_requests_total,
        synapse_shadow_rules_total,
        synapse_trajectory_replay_total,
    )
except ImportError:
    METRICS_ENABLED = False
    synapse_inference_latency_seconds = None
    synapse_requests_total = None
    synapse_replays_detected_total = None
    synapse_pow_solved_total = None
    synapse_shadow_requests_total = None
    synapse_shadow_cohort_total = None
    synapse_shadow_outcomes_total = None
    synapse_shadow_rules_total = None
    synapse_trajectory_replay_total = None

logger = logging.getLogger("synapse_shield.core")

MAX_PAYLOAD_SIZE = 262_144  # 256 KB
# Methods that change state. DELETE has no body, so its token travels in the X-Synapse-Token header.
PROTECTED_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# IP-level 4-strike / 60 s ban counter (shared by every device behind one CGNAT / Eduroam address).
# Token failures always count (handled at the token step). A behavioural verdict counts only when it is a
# hard violation (zero interaction / scroll-only, 1-2 mouse points without touch, webdriver/stealth, session
# invariance) or its score is >= IP_STRIKE_MIN_SCORE. Borderline Bot verdicts (block threshold .. 85) still
# block the request and still give that device the 60 s +50 penalty; they just cannot lock out the whole NAT.
# Measured (p2c/strike_policy_sim.py): human requests lost to IP bans on one CGNAT IP at 120 req/min with a
# calibrated 1.4 % human Bot rate: 14.8 % (every Bot verdict) -> 0.8 % (this rule); scripted bots (linear,
# bezier, sine, minimum-jerk, stealth) are still banned after 4 requests.
IP_STRIKE_MIN_SCORE = 85.0


def counts_as_ip_strike(bot_score: float, hard_bot_violation: bool) -> bool:
    """Whether a behavioural Bot verdict feeds the IP-level ban counter (see IP_STRIKE_MIN_SCORE)."""
    return bool(hard_bot_violation) or bot_score >= IP_STRIKE_MIN_SCORE


# Single-request trajectory replay (#39-A). A recording that passed once, re-sent with a fresh token from a fresh
# IP / User-Agent, is invisible to every per-IP / per-device signal. The keyed delta fingerprint of the pointer
# path (fingerprint.py) is consumed ONLY when a request is about to be allowed: a 429 PoW challenge, an
# EXPIRED token or a block never consumes it, so the SDK retry paths (which resend the same, time-shifted
# events with a new token after a challenge / expiry) are not mistaken for a replay. A repeat within the TTL
# is a block (or shadow block) with this reason. Measured human collisions: 0 (SapiMouse 1.13 M cross-user
# + 8978 same-user pairs, 1000 simulated sessions). Like token-level replay it feeds only the IP 4-strike
# counter, not the per-device +50 penalty. SYNAPSE_TRAJECTORY_REPLAY=0 turns the check off.
# TTL 1 h (SYNAPSE_TRAJECTORY_FP_TTL): every recording in a replay library is usable at most once per hour
# across all IPs, and one key (~40 bytes) per allowed request bounds storage to one hour of allowed traffic.
TRAJECTORY_REPLAY_REASON = (
    "REPLAY_TRAJECTORY: pointer trajectory identical to one already accepted within the replay window"
)
TRAJECTORY_REPLAY_THREAT = "REPLAY_TRAJECTORY"


# Insufficient-evidence segments (keyboard-only, short pointer traces gated by #38a). Their gray-area PoW is the
# only thing between a jittered bot and an allow, so: always difficulty 5 (~1 M expected SHA-256 vs ~65 k), and a
# solved PoW removes only INSUFFICIENT_EVIDENCE_POW_DISCOUNT points instead of 20, so the gray-area bonus is not
# wiped out (short trace 45 -> 35, keyboard-only 40 -> 30). Both stay below the block threshold (50) and the
# verdict is Human, so a solver still passes: PoW adds cost, it is not a discriminator. Same rule in main.py.
INSUFFICIENT_EVIDENCE_POW_DIFFICULTY = 5
INSUFFICIENT_EVIDENCE_POW_DISCOUNT = 10.0
GRAY_AREA_POW_DISCOUNT = 20.0


def pow_challenge_difficulty(bot_score: float, insufficient_evidence: bool) -> int:
    if insufficient_evidence:
        return INSUFFICIENT_EVIDENCE_POW_DIFFICULTY
    return 5 if bot_score >= 45.0 else 4


def pow_solved_discount(insufficient_evidence: bool) -> float:
    return INSUFFICIENT_EVIDENCE_POW_DISCOUNT if insufficient_evidence else GRAY_AREA_POW_DISCOUNT


# Shape-invariance matched only against the IP-only history (#39-C, engine reason "... across IP requests").
# A whole CGNAT can share that history, so the match blocks the request but is NOT a hard violation: it does
# not feed the IP 4-strike ban (counts_as_ip_strike). IP+UA (session) invariance stays a hard violation.
IP_SHAPE_INVARIANCE_MARKER = "Same normalized trajectory shape repeated across IP requests"


def invariance_scopes(reasons: Any, threat_type: Any = None) -> tuple[bool, bool]:
    """(hard session invariance, IP-only shape invariance) from the engine reasons."""
    inv = [r for r in (reasons or []) if isinstance(r, str) and "Session Behavioral Invariance" in r]
    ip_only = [r for r in inv if IP_SHAPE_INVARIANCE_MARKER in r]
    hard = len(inv) > len(ip_only) or (not inv and threat_type == "SESSION_INVARIANCE_BOT")
    return hard, bool(ip_only)


def ip_shape_session_id(client_ip: str) -> str:
    """Storage key of the IP-only shape history (#39-C); distinct from the IP+UA session key ``ip_<ip>_<ua>``."""
    return f"ipshape_{client_ip}"


def record_ip_shape_history(storage: Any, ip_session_id: str, details: Any) -> None:
    """Append the request's shape SimHash (no kinematics, no raw path) to the IP-only history."""
    sh = details.get("shape_hash") if isinstance(details, dict) else None
    if sh:
        storage.record_session_telemetry(ip_session_id, {"sh": sh}, max_history=10, window_sec=300)


# IP+UA session history (#3G). Every final allow / block decision is recorded (a 429 PoW challenge is not: its
# retry is), tagged ``ok`` = allowed. Poisoning: two bot requests from a CGNAT IP with the victim's (common)
# User-Agent must not make the victim's next clean request trip session invariance (a hard violation). The engine
# therefore uses only ``ok`` entries for the history-only invariance window; the windows that include the current
# request (last 2 stored + current, shape SimHash) keep every entry, because they also need the victim's own
# trajectory to match the attacker's. Writing only allowed requests instead was measured (p3g/meas.py) to cut
# invariance catches of repeating template bots that wait out the 60 s penalty: allow rate 34 % -> 53 %.
# Only a real trajectory (>= 3 points, distance > 0) is stored: single taps carry placeholder values.
def record_session_history(storage: Any, session_id: str, details: Any, allowed: bool) -> None:
    feats = details.get("features", {}) if isinstance(details, dict) else {}
    if feats.get("mouse_points", 0) >= 3 and feats.get("total_distance", 0.0) > 0:
        storage.record_session_telemetry(
            session_id,
            {
                "avg_jerk": feats.get("avg_jerk", 0.0),
                "straightness": feats.get("straightness", 1.0),
                "total_distance": feats.get("total_distance", 0.0),
                "submovement_count": feats.get("submovement_count", 0),
                "spectral_purity": feats.get("spectral_purity", 0.0),
                **({"sh": details["shape_hash"]} if details.get("shape_hash") else {}),
                "ok": bool(allowed),
            },
            max_history=10,
            window_sec=300,
        )


def trajectory_replay_enabled() -> bool:
    return os.environ.get("SYNAPSE_TRAJECTORY_REPLAY", "1").lower() not in ("0", "false", "no", "off")


def trajectory_fp_ttl() -> int:
    try:
        return max(60, int(os.environ.get("SYNAPSE_TRAJECTORY_FP_TTL", "3600")))
    except ValueError:
        return 3600


def is_trajectory_replay(storage: Any, telemetry: Any, shadow: bool = False) -> bool:
    """Consume the trajectory fingerprint; True when it was already accepted within the TTL.

    Call only at the allow decision. Low-entropy / malformed trajectories are not fingerprinted (False).
    """
    if not trajectory_replay_enabled():
        return False
    fp = trajectory_fingerprint(telemetry)
    if fp is None:
        return False
    try:
        first = storage.consume_trajectory_fp(fp, ttl_sec=trajectory_fp_ttl())
    except Exception as e:  # fail-open: a storage error must not block a human as a replay
        logger.warning("consume_trajectory_fp failed (%s); trajectory replay check skipped", e)
        return False
    if first:
        return False
    if METRICS_ENABLED and synapse_trajectory_replay_total is not None:
        synapse_trajectory_replay_total.labels(mode="shadow" if shadow else "enforce").inc()
    return True


def get_trusted_proxies() -> set[str]:
    """Return set of trusted reverse proxy IP addresses or CIDR blocks."""
    raw = os.environ.get("SYNAPSE_TRUSTED_PROXIES", "127.0.0.1,::1,localhost")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def _is_ip_in_trusted(ip_str: str, trusted_raw_items: Any) -> bool:
    """Helper to check if an IP string matches trusted proxies (supports CIDR, loopback, and exact match)."""
    if not ip_str:
        return False
    ip_clean = ip_str.strip()
    if ip_clean in ("127.0.0.1", "::1", "localhost"):
        if any(item in ("127.0.0.1", "::1", "localhost") for item in trusted_raw_items):
            return True

    try:
        ip_obj = ipaddress.ip_address(ip_clean)
    except ValueError:
        return ip_clean in trusted_raw_items

    for item in trusted_raw_items:
        item_str = str(item).strip()
        if not item_str:
            continue
        if item_str == "localhost":
            if ip_obj.is_loopback:
                return True
            continue
        try:
            if "/" in item_str:
                net = ipaddress.ip_network(item_str, strict=False)
                if ip_obj in net:
                    return True
            else:
                if ip_obj == ipaddress.ip_address(item_str):
                    return True
        except ValueError:
            if ip_clean == item_str:
                return True
    return False


def _is_valid_ip(ip_str: str) -> bool:
    """Validates if a string is a syntactically valid IPv4 or IPv6 address."""
    if not ip_str:
        return False
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def resolve_client_ip(
    client_host: str,
    headers: Any,
    trusted_proxies: set[str] | None = None,
) -> str:
    """
    Safely resolve the originating client IP address behind reverse proxies (Nginx, Cloudflare, AWS ALB).
    Only trusts forwarding headers (CF-Connecting-IP, X-Real-IP, X-Forwarded-For) if client_host is
    explicitly in the trusted proxy set or CIDR blocks. Prevents IP spoofing while protecting legitimate visitors.
    """
    if trusted_proxies is None:
        trusted_proxies = get_trusted_proxies()

    client_ip = (client_host or "127.0.0.1").strip()

    if not _is_ip_in_trusted(client_ip, trusted_proxies):
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

    # 1. Cloudflare True Client IP (validated for IP format)
    cf_ip = header_dict.get("cf-connecting-ip")
    if cf_ip and _is_valid_ip(cf_ip):
        return cf_ip.strip()

    # 2. Standard single reverse proxy header (validated for IP format)
    real_ip = header_dict.get("x-real-ip")
    if real_ip and _is_valid_ip(real_ip):
        return real_ip.strip()

    # 3. Traversed X-Forwarded-For chain: client, proxy1, proxy2
    forwarded = header_dict.get("x-forwarded-for") or header_dict.get("http-x-forwarded-for")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        for ip in reversed(ips):
            if _is_valid_ip(ip) and not _is_ip_in_trusted(ip, trusted_proxies):
                return ip
        for ip in reversed(ips):
            if _is_valid_ip(ip):
                return ip

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
    cohort: dict[str, str] | None = None  # coarse {"input", "dpr"} labels; set for behavioural verdicts
    rule_codes: tuple[str, ...] = ()  # stable codes of the rules behind a shadow block

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
                if self.cohort:
                    base["cohort"] = self.cohort
                if self.rule_codes:
                    base["rule_codes"] = list(self.rule_codes)
                if self.reasons:
                    base["reasons"] = self.reasons
            return base

        return {
            "error": self.error_message or "Access Denied by Synapse Shield",
            "classification": self.classification,
            "bot_score": f"{self.bot_score}%",
            "reasons": self.reasons,
        }


def _count_shadow_cohort(action: str, features: dict[str, Any] | None) -> dict[str, str]:
    """Label a shadow verdict with its coarse input cohort and count it. Stores no trace data."""
    cohort = cohort_of(features)
    if METRICS_ENABLED and synapse_shadow_cohort_total is not None:
        synapse_shadow_cohort_total.labels(action=action, input=cohort["input"], dpr=cohort["dpr"]).inc()
    return cohort


def _count_shadow_rules(cohort: dict[str, str], reasons: list[str]) -> tuple[str, ...]:
    """Count which rules produced a shadow block, per cohort, so a broken rule shows up in one group."""
    codes = rule_codes(reasons)
    if METRICS_ENABLED and synapse_shadow_rules_total is not None:
        for code in codes:
            synapse_shadow_rules_total.labels(input=cohort["input"], dpr=cohort["dpr"], rule=code).inc()
    return codes


def report_shadow_outcome(decision: SynapseDecision, completed: bool) -> bool:
    """Join a Shadow Mode verdict with what really happened to the session (host-supplied).

    Call it when the host app knows the outcome (e.g. the login/checkout succeeded -> completed=True,
    the user gave up -> False). Only the verdict and the two coarse cohort labels are used; no pointer
    trace is read or kept. A high ``simulated_action=block`` x ``completed`` count in one cohort means
    enforcing would have blocked real users there. Returns False when there is nothing to record.
    """
    if not decision.shadow_mode or decision.cohort is None:
        return False
    if METRICS_ENABLED and synapse_shadow_outcomes_total is not None:
        synapse_shadow_outcomes_total.labels(
            simulated_action="block" if decision.action == "shadow_block" else "allow",
            input=decision.cohort["input"],
            dpr=decision.cohort["dpr"],
            outcome=OUTCOME_LABELS[0] if completed else OUTCOME_LABELS[1],
        ).inc()
    return True


def evaluate_synapse_request_sync(
    client_ip: str,
    user_agent: str,
    token: str | None,
    max_risk_score: float = 50.0,
    accessibility_mode: bool = False,
    mode: str = "enforce",
    pow_nonce: str | None = None,
    pow_salt: str | None = None,
    enable_pow: bool | None = None,
    keyboard_only_challenge: bool | None = None,
    short_trace_challenge: bool | None = None,
) -> SynapseDecision:
    """
    Synchronous core security evaluation engine.
    Used natively by synchronous frameworks (Django, Flask) and wrapped in threadpools for ASGI/FastAPI.

    ``keyboard_only_challenge`` (default on; env ``SYNAPSE_KEYBOARD_ONLY_CHALLENGE=0`` turns it off) keeps
    the gray-area PoW challenge for keyboard-only sessions even when ``enable_pow`` is off, for scores that
    would otherwise be a plain allow. It never turns a block into a challenge.
    ``short_trace_challenge`` (default on; env ``SYNAPSE_SHORT_TRACE_CHALLENGE=0``) does the same for pointer
    traces whose score the short-trace gate (engine #38a) lowered.
    """
    storage = get_storage()
    if enable_pow is None:
        enable_pow = os.environ.get("SYNAPSE_ENABLE_POW", "").lower() in ("1", "true")
    if keyboard_only_challenge is None:
        keyboard_only_challenge = os.environ.get("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "1").lower() not in (
            "0", "false", "no", "off"
        )
    if short_trace_challenge is None:
        short_trace_challenge = os.environ.get("SYNAPSE_SHORT_TRACE_CHALLENGE", "1").lower() not in (
            "0", "false", "no", "off"
        )
    is_shadow = mode.lower() == "shadow"
    client_key = client_strike_key(client_ip, user_agent)

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
    is_valid, reason, telemetry = verify_and_consume_token(token, client_ip=client_ip, user_agent=user_agent)
    if not is_valid:
        if "Replay" in reason or "Yeniden Oynatma" in reason:
            if METRICS_ENABLED and synapse_replays_detected_total is not None:
                synapse_replays_detected_total.inc()

        # Token-level failures (replay, forged signature, malformed, time-travel, relay) feed only the IP-level
        # 4-strike ban counter. They do NOT give the device (IP+UA) the 60 s +50 penalty: an SDK network retry or
        # a double submit resends the same token, and the next clean request of that real user must not be
        # penalized. The per-device penalty comes only from a behavioural verdict (step 7). Same as main.py.
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
    # Tie session to client_ip + User-Agent hash to prevent IP-wide collisions on CGNAT / Eduroam
    ua_hash = hashlib.sha256((user_agent or "unknown_ua").encode("utf-8")).hexdigest()[:16]
    session_id = f"ip_{client_ip}_{ua_hash}"
    session_history = storage.get_session_telemetries(session_id, window_sec=300)
    # #39-C: IP-only shape history (normalized-shape SimHash only). Rotating the User-Agent gives a fresh IP+UA
    # session, but not a fresh IP history. Measured NAT FP (12 SapiMouse users on one IP): 0 (p2bc/inv_meas.py).
    ip_session_id = ip_shape_session_id(client_ip)
    ip_history = storage.get_session_telemetries(ip_session_id, window_sec=300)

    # 4.5 Sliding-Window Request Frequency (Poisson Anomaly & DoS protection)
    recent_request_count = storage.record_and_get_request_count(client_ip, window_sec=10)
    max_10s_limit = int(os.environ.get("SYNAPSE_MAX_REQ_10S", "100"))
    if recent_request_count > max_10s_limit:
        storage.ban_ip(client_ip, duration_sec=900, reason=f"Extreme request frequency (DoS protection: >{max_10s_limit} req/10s)")
        return SynapseDecision(
            allowed=False,
            status_code=403,
            error_message="[Synapse Shield] Extreme request frequency detected. IP temporarily banned.",
            classification="Bot",
            bot_score=100.0,
            reasons=[f"Extreme request frequency (>{max_10s_limit} req/10s)"],
            action="block",
            headers={"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"},
        )

    # 5. Biometric Kinematics & AI Inference
    # In NAT / CGNAT environments, penalizing the whole IP pushes innocent devices into 403.
    # The short 60s "+50 risk" penalty is scoped per-client (IP + User-Agent), while the 4-strike IP ban stays IP-scoped.
    strike_count = storage.get_client_strike_count(client_key, window_sec=60)
    is_penalized = strike_count >= 1
    start_time = time.perf_counter()
    bot_score, classification, reasons, details = analyze_behavior(
        telemetry, recent_request_count, is_penalized, accessibility_mode, session_history, ip_history=ip_history
    )
    latency = time.perf_counter() - start_time

    # IP+UA session history is written at the final decision (record_session_history, below), see #3G.
    if METRICS_ENABLED and synapse_inference_latency_seconds is not None:
        synapse_inference_latency_seconds.observe(latency)

    # 6. Gray Area Proof-of-Work (Smart Challenge) Flow
    feat = details.get("features", {}) if isinstance(details, dict) else {}
    total_interactive_events = feat.get("total_interactive_events",
        feat.get("mouse_points", 0) + feat.get("key_count", 0) + feat.get("touch_event_count", 0) + feat.get("click_count", 0)
    )
    mouse_points = feat.get("mouse_points", 0)
    is_stealth = feat.get("is_stealth_automation", False) or (details.get("threat_type") == "STEALTH_AUTOMATION")
    has_invariance, ip_shape_invariance = invariance_scopes(reasons, details.get("threat_type"))
    if ip_shape_invariance and classification != "Bot":
        classification = "Bot"
        bot_score = max(bot_score, 70.0)

    hard_bot_violation = (
        total_interactive_events == 0
        or (1 <= mouse_points <= 2 and not feat.get("touch_supported", False))
        or is_stealth
        or has_invariance
    )

    # Keyboard-only sessions (no mouse, >= 3 keys, not touch) get +40 instead of +50 in engine.py so real
    # keyboard users are not hard-blocked. Without PoW that would make them a plain allow, and a jittered
    # auto-typer with them, so for this segment the challenge stays on even when enable_pow is off. It only
    # covers scores that would otherwise be allowed (below max_risk_score, not classified Bot): a session
    # that was going to be blocked is still blocked, so this can only tighten, never loosen, a decision.
    is_keyboard_only = (
        mouse_points == 0
        and feat.get("key_count", 0) >= 3
        and not feat.get("touch_supported", False)
    )
    # Same rule for short pointer traces (#38a): when the short-trace gate actually lowered the score
    # (details["short_trace_gated"]), the trace is too short to tell a humanised bot from a human, so the gray
    # area is challenged instead of allowed. Measured (p2bc/short_meas.py): see SHORT_TRACE_CHALLENGE notes.
    is_short_trace_gated = bool(details.get("short_trace_gated", False)) if isinstance(details, dict) else False
    force_insufficient_evidence_pow = (
        not enable_pow
        and ((keyboard_only_challenge and is_keyboard_only) or (short_trace_challenge and is_short_trace_gated))
        and bot_score < max_risk_score
        and classification != "Bot"
    )

    insufficient_evidence = is_keyboard_only or is_short_trace_gated
    if (
        (enable_pow or force_insufficient_evidence_pow)
        and (35.0 <= bot_score < 55.0)
        and not hard_bot_violation
        and not ip_shape_invariance
    ):
        is_pow_valid = False
        if pow_nonce and pow_salt:
            is_pow_valid = verify_and_consume_pow(pow_salt, str(pow_nonce), client_ip=client_ip)

        if is_pow_valid:
            bot_score = max(0.0, bot_score - pow_solved_discount(insufficient_evidence))
            classification = "Human"
            reasons.append("Gray area PoW Challenge successfully solved (Risk reduced).")
            if METRICS_ENABLED and synapse_pow_solved_total is not None:
                synapse_pow_solved_total.inc()
        elif not is_shadow:
            # Emit challenge request with risk-adaptive PoW difficulty
            pow_diff = pow_challenge_difficulty(bot_score, insufficient_evidence)
            challenge_salt = generate_pow_salt(client_ip=client_ip, difficulty=pow_diff)
            return SynapseDecision(
                allowed=False,
                status_code=429,
                error_message="Proof of Work Challenge Required",
                classification=classification,
                bot_score=bot_score,
                reasons=reasons,
                telemetry=telemetry,
                action="challenge",
                challenge_data={"pow_difficulty": pow_diff, "pow_salt": challenge_salt},
                headers={
                    "X-Synapse-Action": "challenge",
                    "X-Synapse-Risk-Score": f"{bot_score:.1f}%",
                    "Retry-After": "2",
                },
            )

    # 7. Final Decision Threshold
    is_mitigated = bot_score >= max_risk_score or classification == "Bot" or ip_shape_invariance

    # 7.5 Trajectory replay: consumed only on the allow path (see TRAJECTORY_REPLAY_REASON above).
    trajectory_replay = False
    if not is_mitigated and is_trajectory_replay(storage, telemetry, shadow=is_shadow):
        trajectory_replay = True
        is_mitigated = True
        bot_score = 100.0
        classification = "Bot"
        reasons.append(TRAJECTORY_REPLAY_REASON)

    # IP+UA session history: final decision only, tagged allowed / blocked (see record_session_history, #3G).
    record_session_history(storage, session_id, details, allowed=not is_mitigated)

    if is_mitigated:
        if trajectory_replay:
            # Same policy as token-level replay: IP 4-strike counter only, no per-device +50 penalty.
            storage.record_bot_strike(client_ip)
        else:
            if counts_as_ip_strike(bot_score, hard_bot_violation):
                storage.record_bot_strike(client_ip)
            storage.record_client_strike(client_key, window_sec=60)

        if is_shadow:
            if METRICS_ENABLED and synapse_shadow_requests_total is not None:
                synapse_shadow_requests_total.labels(action="block", classification=classification).inc()
            cohort = _count_shadow_cohort("block", feat)
            codes = _count_shadow_rules(cohort, reasons)
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
                cohort=cohort,
                rule_codes=codes,
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
    cohort = None
    if is_shadow:
        if METRICS_ENABLED and synapse_shadow_requests_total is not None:
            synapse_shadow_requests_total.labels(action="allow", classification=classification).inc()
        cohort = _count_shadow_cohort("allow", feat)
    elif METRICS_ENABLED and synapse_requests_total is not None:
        synapse_requests_total.labels(status="allow", classification=classification).inc()

    # IP-only shape history (#39-C) is written ONLY for allowed requests: a blocked / challenged bot on a shared
    # CGNAT IP must not be able to seed the history that the next (human) request on that IP is compared with.
    record_ip_shape_history(storage, ip_session_id, details)

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
        cohort=cohort,
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
    enable_pow: bool | None = None,
    keyboard_only_challenge: bool | None = None,
    short_trace_challenge: bool | None = None,
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
        keyboard_only_challenge=keyboard_only_challenge,
        short_trace_challenge=short_trace_challenge,
    )
