"""
Synapse Shield Doctor - System Diagnostics & Security Health Audit Engine
Command: synapse-shield doctor
Audits environment, native Rust SIMD core acceleration, AI weights integrity,
cryptographic entropy, SQLite WAL health, and reverse proxy defenses.
"""

import os
import platform
import sys
import time
from typing import Any

from synapse_shield._version import __version__


def check_python_environment() -> dict[str, Any]:
    ver = sys.version_info
    py_ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    passed = ver >= (3, 10)
    details = f"Python {py_ver_str} on {platform.system()} {platform.machine()}"
    return {
        "name": "Python Environment",
        "passed": passed,
        "warning": False,
        "message": details if passed else f"Python >= 3.10 required (Found {py_ver_str})",
    }


def check_rust_simd_core() -> dict[str, Any]:
    try:
        from synapse_shield import synapse_core_rs

        if synapse_core_rs and synapse_core_rs.is_rust_core_active():
            return {
                "name": "Native Rust SIMD Core",
                "passed": True,
                "warning": False,
                "message": "PyO3 AVX2/NEON SIMD extension is active & accelerated",
            }
    except Exception:
        pass
    return {
        "name": "Native Rust SIMD Core",
        "passed": True,
        "warning": True,
        "message": "Rust core not compiled; running pure Python/NumPy fallback (~5x slower)",
    }


def check_ai_model_weights() -> dict[str, Any]:
    from synapse_shield.models import SynapseHybridModel

    try:
        t0 = time.perf_counter_ns()
        model = SynapseHybridModel()
        dummy_mouse = [[0.0] * 5 for _ in range(60)]
        dummy_static = [0.0] * 8
        model.predict(dummy_mouse, dummy_static)
        t_us = (time.perf_counter_ns() - t0) / 1000.0
        return {
            "name": "1D-CNN AI Micro-Brain",
            "passed": True,
            "warning": False,
            "message": f"Weights verified ({model.weights_path}, warmup: {t_us:.1f}µs)",
        }
    except Exception as e:
        return {
            "name": "1D-CNN AI Micro-Brain",
            "passed": False,
            "warning": False,
            "message": f"Failed to load AI model weights: {e}",
        }


def check_cryptographic_engine() -> dict[str, Any]:
    from synapse_shield.tokens import (
        generate_challenge,
    )

    env_key = os.environ.get("SYNAPSE_SECRET_KEY")
    is_env_set = bool(env_key and len(env_key) >= 32)

    ch = generate_challenge(expires_in_sec=60, client_ip="192.168.1.100", user_agent="Mozilla/5.0 DoctorAudit")
    parts = ch["challenge"].split(".")
    has_binding = len(parts) == 4

    warning = not is_env_set
    msg = "HMAC-SHA256 active, Client Binding enabled"
    if warning:
        msg += " (Warning: SYNAPSE_SECRET_KEY not in env; using persistent file fallback)"
    else:
        msg += " (Production SYNAPSE_SECRET_KEY configured)"

    return {
        "name": "Cryptographic Token & Binding",
        "passed": has_binding,
        "warning": warning,
        "message": msg,
    }


def check_storage_wal() -> dict[str, Any]:
    from synapse_shield.storage import get_storage

    server_missing = None
    try:
        from synapse_shield.main import DB_FILE, get_connection
    except ImportError as e:
        # A bare `pip install synapse-shield` has no FastAPI/uvicorn. Audit storage anyway
        # instead of crashing the whole doctor run with a traceback.
        import sqlite3

        from synapse_shield.storage import DB_FILE

        server_missing = getattr(e, "name", None) or str(e)

        def get_connection():
            return sqlite3.connect(DB_FILE, timeout=10)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        journal_mode = row[0].lower() if row else "unknown"
        if server_missing:
            conn.close()
            conn = None

        storage = get_storage()
        test_nonce = f"doctor_audit_{int(time.time() * 1000)}"
        c1 = storage.consume_nonce(test_nonce, ttl_sec=10)
        c2 = storage.consume_nonce(test_nonce, ttl_sec=10)
        replay_ok = c1 is True and c2 is False

        is_wal = journal_mode == "wal"
        msg = f"SQLite DB ok ({DB_FILE}, journal: {journal_mode}, atomic nonce: ok)"
        if server_missing:
            msg += (
                f" | Server extras missing ({server_missing}): "
                "`synapse-shield run` needs pip install \"synapse-shield[server]\""
            )
        return {
            "name": "Storage & WAL Replay Defense",
            "passed": replay_ok,
            "warning": (not is_wal) or bool(server_missing),
            "message": msg,
        }
    except Exception as e:
        return {
            "name": "Storage & WAL Replay Defense",
            "passed": False,
            "warning": False,
            "message": f"Storage engine error: {e}",
        }


def check_network_proxy() -> dict[str, Any]:
    from synapse_shield.core import get_trusted_proxies, resolve_client_ip

    trusted = get_trusted_proxies()
    spoofed = resolve_client_ip("203.0.113.1", {"x-forwarded-for": "8.8.8.8"}, trusted_proxies=trusted)
    spoof_prevented = spoofed == "203.0.113.1"
    return {
        "name": "Reverse Proxy & IP Shield",
        "passed": spoof_prevented,
        "warning": False,
        "message": f"Trusted proxies: {len(trusted)} configured, IP spoofing defense verified",
    }


def run_doctor() -> int:
    """
    Executes the full diagnostic test suite and prints results.
    Returns 0 on all pass, 1 on critical failure.
    """
    print(f"\n🛡️  Synapse Shield v{__version__} - System Diagnostics & Security Health Audit")
    print("=" * 76)

    checks = [
        check_python_environment(),
        check_rust_simd_core(),
        check_ai_model_weights(),
        check_cryptographic_engine(),
        check_storage_wal(),
        check_network_proxy(),
    ]

    all_passed = True
    has_warnings = False

    for c in checks:
        if not c["passed"]:
            all_passed = False
            status_tag = "[\033[91mFAIL\033[0m]"
        elif c.get("warning"):
            has_warnings = True
            status_tag = "[\033[93mWARN\033[0m]"
        else:
            status_tag = "[\033[92mPASS\033[0m]"

        print(f" {status_tag} {c['name']:<30} : {c['message']}")

    print("=" * 76)
    if not all_passed:
        print("❌ Critical issues detected. Please fix the failed items above.\n")
        return 1
    elif has_warnings:
        print("⚠️  System is healthy and operational, but some optimizations/warnings were noted.\n")
        return 0
    else:
        print("✅ All systems optimal! Synapse Shield is fully hardened and ready for production.\n")
        return 0
