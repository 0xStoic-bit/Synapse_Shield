"""
Type stubs for the native Rust acceleration extension (synapse_core_rs).
Provides microsecond SIMD kinematic feature extraction, rotating two-bucket nonce cache,
and sub-microsecond in-memory L1 IP quarantine checks.
"""

from typing import Any

def is_rust_core_active() -> bool:
    """Return True if native Rust SIMD core is compiled and active."""
    ...

def get_core_version() -> str:
    """Return the version string of the compiled Rust core."""
    ...

def extract_features_rs(telemetry: dict[str, Any]) -> dict[str, Any]:
    """
    Extract 19D kinematic features, curvature metrics, and keystroke dynamics in Rust.
    """
    ...

def evaluate_curvature_naturalness_rs(trajectory: list[dict[str, Any]]) -> float:
    """
    Evaluate biological naturalness of curvature across mouse trajectory points.
    Returns naturalness score between 0.0 (synthetic/linear) and 1.0 (biological).
    """
    ...

def evaluate_curvature_zerocopy_rs(points: list[tuple[float, float, float]]) -> float:
    """
    Zero-copy curvature evaluation from tuple triples (x, y, timestamp_ms).
    """
    ...

def evaluate_keystroke_dynamics_rs(keystrokes: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Evaluate flight time, dwell time, and digraph entropy from keystroke events.
    """
    ...

def consume_nonce_rs(nonce: str, ttl_sec: int = 120) -> bool:
    """
    Record and consume a cryptographic nonce in the rotating Two-Bucket O(1) cache.
    Returns True if nonce is valid and fresh, False if already consumed (Replay Attack).
    """
    ...

def is_ip_banned_rs(ip: str) -> bool:
    """
    Check if an IP address is actively quarantined in the sub-microsecond L1 cache.
    """
    ...

def ban_ip_rs(ip: str, duration_sec: int) -> None:
    """
    Quarantine an IP address for duration_sec seconds in the Rust L1 cache.
    """
    ...

def unban_ip_rs(ip: str) -> None:
    """
    Remove an IP address from the Rust L1 quarantine cache.
    """
    ...

def hydrate_bans_rs(bans: list[tuple[str, int]]) -> None:
    """
    Hydrate active IP bans from persistent SQLite storage into the Rust L1 RAM cache.
    """
    ...

def clear_state_engine_rs() -> None:
    """
    Clear all nonces and active IP bans from the Rust state engine.
    """
    ...

def get_state_engine_stats_rs() -> dict[str, int]:
    """
    Return telemetry metrics: current_bucket_nonces, previous_bucket_nonces, active_ip_bans.
    """
    ...
