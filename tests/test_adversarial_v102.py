"""
Adversarial Penetration and Bypass Verification Suite for Synapse Shield v0.10.2
Simulated Red Team Council:
- Opus 5 (Adversarial Threat Modeler / Attack Hypotheses)
- Argon (Blue Team Lead Architect / Defensive Layer Analysis)
- Flash (Implementation & Automated Pytest Verification)

Tested Attack Surfaces:
1. Bézier / Minimum-Jerk synthetic mouse curve with Gaussian micro-jitter
2. Fast-token submission and future/past timestamp boundary manipulation
3. Robotic fixed-dwell keystroke generator evading Zero-PII masking
4. Browser anti-stealth and prototype hook tampering detection
5. Multi-turn session behavioral invariance across consecutive requests
6. Dynamic Proof-of-Work (PoW) salt forgery and difficulty tampering
"""

import base64
import json
from fastapi.testclient import TestClient

from synapse_shield.main import app
from synapse_shield.tokens import (
    generate_challenge,
    generate_pow_salt,
    verify_pow_salt,
)
from synapse_shield.core import evaluate_synapse_request_sync
from synapse_shield.storage import get_storage

client = TestClient(app)


def _build_token(challenge_obj: dict | str, telemetry: dict) -> str:
    challenge_str = challenge_obj["challenge"] if isinstance(challenge_obj, dict) else challenge_obj
    envelope = {"challenge": challenge_str, "telemetry": telemetry}
    return base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")


# ============================================================================
# Vector 1: Synthetic Bézier / Minimum-Jerk Mouse Trajectory with Noise
# ============================================================================
def test_vector1_bezier_synthetic_mouse_detection():
    """
    Opus 5 Hypothesis:
    An advanced scraper generates a 3rd-order cubic Bézier curve between (50, 50)
    and (600, 400) with small random Gaussian jitter to simulate human tremor.

    Argon Defense:
    Synapse Shield's Kinematics (Jerk analysis d3x/dt3, spectral purity, and
    terminal deceleration) checks whether the movement obeys biological Fitts' Law.
    Mathematical polynomial curves exhibit unnatural spectral purity or zero jerk variance.
    """
    client_ip = "192.168.10.55"
    chal = generate_challenge(client_ip=client_ip, user_agent="Mozilla/5.0 Chrome/120.0")

    p0 = (50, 50)
    p1 = (200, 100)
    p2 = (400, 350)
    p3 = (600, 400)

    n_points = 45
    t_start = 1000
    points = []
    for i in range(n_points):
        t = i / (n_points - 1)
        bx = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
        by = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
        points.append({
            "x": round(bx, 2),
            "y": round(by, 2),
            "t": t_start + int(t * 1600)
        })

    telemetry = {
        "mouse_movements": points,
        "clicks": [{"x": 600, "y": 400, "t": t_start + 1650}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
        }
    }

    token = _build_token(chal, telemetry)
    decision = evaluate_synapse_request_sync(
        client_ip=client_ip,
        user_agent="Mozilla/5.0 Chrome/120.0",
        token=token,
        max_risk_score=50.0
    )

    # Bot score must be elevated or reasons flagged
    assert decision.bot_score >= 30.0 or decision.classification == "Bot" or not decision.allowed


# ============================================================================
# Vector 2: Fast-Time Submission & Timestamp Boundary Probe
# ============================================================================
def test_vector2_timestamp_boundary_tampering(monkeypatch):
    """
    Opus 5 Hypothesis:
    Bot submits token with an elapsed time < 1500ms or future timestamp to bypass checks.

    Argon Defense:
    Tokens require challenge_ts > SYNAPSE_MIN_ELAPSED_MS (1500ms). Fast tokens are
    flagged with TOKEN_FAST_SUBMISSION / Time Manipulation.
    """
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "1500")
    client_ip = "192.168.10.56"

    # Fast Token: challenge created now, token submitted immediately (elapsed < 1500ms)
    chal_fast = generate_challenge(client_ip=client_ip, user_agent="Mozilla/5.0")
    token_fast = _build_token(chal_fast, {
        "mouse_movements": [{"x": 100, "y": 100, "t": 100}, {"x": 200, "y": 200, "t": 400}],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080}
    })

    dec_fast = evaluate_synapse_request_sync(
        client_ip=client_ip,
        user_agent="Mozilla/5.0",
        token=token_fast,
        max_risk_score=50.0
    )
    assert dec_fast.allowed is False
    assert dec_fast.status_code == 403
    assert any("TOKEN" in r or "Zaman" in r or "FAST" in r for r in dec_fast.reasons)


# ============================================================================
# Vector 3: Robotic Fixed-Dwell Keystroke Generator
# ============================================================================
def test_vector3_robotic_fixed_dwell_keystrokes():
    """
    Opus 5 Hypothesis:
    Bot simulates keyboard typing by issuing keys with constant dwell time (e.g. exactly 50ms)
    and constant intervals (dt = 120ms) to bypass Zero-PII mask.

    Argon Defense:
    Rust SIMD and Python features compute key_interval_var and IME majority dwell check.
    Zero variance in key intervals triggers robotic keystroke penalty (+40 to +60 risk).
    """
    client_ip = "192.168.10.57"
    chal = generate_challenge(client_ip=client_ip, user_agent="Mozilla/5.0")

    base_t = 1000
    keystrokes = []
    for i in range(12):
        t_down = base_t + (i * 120)
        t_up = t_down + 50  # Exactly 50ms every single time
        keystrokes.append({
            "key": "masked",
            "down": t_down,
            "up": t_up,
            "dwell": 50,
            "is_freq_digraph": False
        })

    telemetry = {
        "mouse_movements": [{"x": 100 + i, "y": 100, "t": base_t + i * 100} for i in range(15)],
        "clicks": [],
        "keystrokes": keystrokes,
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
        }
    }

    token = _build_token(chal, telemetry)
    decision = evaluate_synapse_request_sync(
        client_ip=client_ip,
        user_agent="Mozilla/5.0",
        token=token,
        max_risk_score=50.0
    )

    assert decision.bot_score >= 35.0 or decision.classification == "Bot"
    assert any("key" in r.lower() or "keystroke" in r.lower() or "interval" in r.lower() or "dwell" in r.lower() or "robotic" in r.lower() for r in decision.reasons) or decision.classification == "Bot"


# ============================================================================
# Vector 4: Browser Anti-Stealth Prototype Hooking
# ============================================================================
def test_vector4_browser_tamper_and_hook_detection():
    """
    Opus 5 Hypothesis:
    Puppeteer-Stealth bot spoofs plugins and screen, but hooks WebGL and Canvas
    via JavaScript Proxy/Object.defineProperty.

    Argon Defense:
    anti_tamper telemetry detects is_webgl_hooked=True and has_webdriver_own_prop=True.
    Hard tampering triggers immediate +100 risk score and BLOCK action.
    """
    client_ip = "192.168.10.58"
    chal = generate_challenge(client_ip=client_ip, user_agent="Mozilla/5.0")

    telemetry = {
        "mouse_movements": [{"x": 100 + i * 10, "y": 150 + i * 5, "t": 1000 + i * 50} for i in range(25)],
        "clicks": [{"x": 350, "y": 275, "t": 2250}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "is_webgl_hooked": True,            # Tamper flag!
            "has_webdriver_own_prop": True,     # Tamper flag!
            "is_plugin_array_fake": True,       # Tamper flag!
        }
    }

    token = _build_token(chal, telemetry)
    decision = evaluate_synapse_request_sync(
        client_ip=client_ip,
        user_agent="Mozilla/5.0",
        token=token,
        max_risk_score=50.0
    )

    assert decision.allowed is False
    assert decision.classification == "Bot"
    assert decision.bot_score >= 80.0
    assert any("tamper" in r.lower() or "webdriver" in r.lower() or "stealth" in r.lower() or "hook" in r.lower() for r in decision.reasons)


# ============================================================================
# Vector 5: Multi-Turn Session Behavioral Invariance
# ============================================================================
def test_vector5_session_behavioral_invariance():
    """
    Opus 5 Hypothesis:
    Bot repeats the identical trajectory across multiple requests within a 300s session
    hoping each single request looks 'clean'.

    Argon Defense:
    Multi-turn session history computes variance of avg_jerk, total_distance, and straightness.
    Zero variance across turns triggers Session Behavioral Invariance (+75 Risk).
    """
    client_ip = "192.168.10.59"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    storage = get_storage()
    storage.unban_ip(client_ip)

    pts = [{"x": 200 + i * 5, "y": 300, "t": 1000 + i * 40} for i in range(20)]
    telemetry = {
        "mouse_movements": pts,
        "clicks": [{"x": 300, "y": 300, "t": 1800}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
        }
    }

    decisions = []
    for _ in range(4):
        chal = generate_challenge(client_ip=client_ip, user_agent=ua)
        token = _build_token(chal, telemetry)
        dec = evaluate_synapse_request_sync(
            client_ip=client_ip,
            user_agent=ua,
            token=token,
            max_risk_score=50.0
        )
        decisions.append(dec)

    last_dec = decisions[-1]
    assert last_dec.bot_score >= 35.0 or last_dec.classification == "Bot"
    assert any("invariance" in r.lower() or "session" in r.lower() or "repeat" in r.lower() for r in last_dec.reasons) or last_dec.classification == "Bot"


# ============================================================================
# Vector 6: Dynamic Proof-of-Work Salt Forgery & Difficulty Tampering
# ============================================================================
def test_vector6_dynamic_pow_salt_tampering():
    """
    Opus 5 Hypothesis:
    Bot intercepted a gray-area PoW challenge with difficulty=4.
    Bot modifies the salt string to claim difficulty=1 or forges the signature
    to solve with minimal CPU.

    Argon Defense:
    Salt contains HMAC-SHA256 signature binding client_ip, difficulty, and expiration.
    Tampered salt fails signature verification immediately.
    """
    client_ip = "198.51.100.88"
    valid_salt = generate_pow_salt(client_ip, difficulty=4)
    assert verify_pow_salt(valid_salt, client_ip) is True

    # 1. Tamper difficulty from 4 to 1
    parts = valid_salt.split(".")
    tampered_diff = f"{parts[0]}.{parts[1]}.1.{parts[3]}"
    assert verify_pow_salt(tampered_diff, client_ip) is False

    # 2. Tamper IP address
    assert verify_pow_salt(valid_salt, "203.0.113.99") is False

    # 3. Forged signature attempt
    forged_salt = f"{parts[0]}.{parts[1]}.4.abcdef0123456789abcdef0123456789"
    assert verify_pow_salt(forged_salt, client_ip) is False
