"""
Unit and regression tests for Synapse Shield v1.0.1 security vulnerabilities fixes:
1. Mobile touch_supported: true Bypass Remediation (Capacitive verification, zero-variance radius trap, swipe kinematics).
2. Gray Area PoW (Proof-of-Work) Exploitation Remediation (Hard bot violation veto, narrowed 35<=score<55 range, IP-bound salt).
3. "Golden Trajectory" (Trajectory Replay + Jitter) & Relative Timestamp Bounds (Fuzzy kinematic similarity delta < 0.015, click-to-cursor distance > 50px, relative timestamp validation).
4. White-Box Static Threshold Jitter (Secret-keyed dynamic jitter within ±5%).
5. Storage Bot Strike Count & train.py Anti-Poisoning Filter (Atomic request count, bot strike penalty, per-IP sample capping <= 3).
"""

import base64
import json
import sqlite3
from unittest.mock import patch


from synapse_shield.core import evaluate_synapse_request_sync
from synapse_shield.engine import (
    _get_dynamic_threshold,
    analyze_behavior,
)
from synapse_shield.storage import get_storage
from synapse_shield.tokens import (
    generate_challenge,
    generate_pow_salt,
    verify_and_consume_token,
    verify_pow_salt,
)
from synapse_shield.train import load_training_data


# ---------------------------------------------------------------------------
# Vulnerability 1: Mobile touch_supported: true Bypass
# ---------------------------------------------------------------------------


def test_v1_spoofed_touch_supported_without_capacitive_data():
    """
    Desktop bot setting touch_supported=True on mouse movements without capacitive radius (r > 0)
    must trigger +75.0 penalty, set is_touch=False, and execute all desktop kinematic filters.
    """
    linear_points = [{"x": i * 15, "y": i * 15, "t": 1000 + i * 20} for i in range(20)]
    telemetry = {
        "mouse_movements": linear_points,
        "clicks": [{"x": linear_points[-1]["x"], "y": linear_points[-1]["y"], "t": 1450}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": True,  # Spoofed flag
            "max_touch_points": 5,
            "plugins_length": 3,
        },
    }

    score, classification, reasons, details = analyze_behavior(telemetry)
    assert any("Spoofed touch_supported flag" in r for r in reasons)
    assert any("Euclidean straight-line trajectory" in r for r in reasons)
    assert classification == "Bot"
    assert score >= 75.0
    assert details["threat_type"] in ("LINEAR_MACRO", "UNKNOWN_ANOMALY")


def test_v1_constant_touch_radius_trap():
    """
    Bot providing constant radius r=12.0 (touch_radius_var < 1e-6) must not receive -15.0 bonus,
    and must receive +55.0 synthetic touch penalty.
    """
    touch_moves = [
        {"x": 100 + i * 10, "y": 200 + (i % 3) * 5, "t": 1000 + i * 30, "r": 12.0, "f": 0.5}
        for i in range(10)
    ]
    telemetry = {
        "mouse_movements": touch_moves,
        "clicks": [{"x": touch_moves[-1]["x"], "y": touch_moves[-1]["y"], "t": 1350}],
        "browser": {
            "webdriver": False,
            "screen_width": 390,
            "screen_height": 844,
            "touch_supported": True,
            "max_touch_points": 5,
        },
    }

    score, classification, reasons, _ = analyze_behavior(telemetry)
    assert any("Synthetic touch emulation detected: Zero contact radius variance" in r for r in reasons)
    assert not any("Capacitive human touch contact verified" in r for r in reasons)
    assert score >= 55.0


def test_v1_genuine_capacitive_touch_verified():
    """
    Genuine human touch with micro-variations in contact radius (variance >= 1e-6) receives -15.0 bonus.
    """
    radii = [10.2, 11.5, 12.1, 10.8, 11.9, 12.4]
    touch_moves = [
        {"x": 100 + i * 10, "y": 200 + (i % 3) * 5, "t": 1000 + i * 30, "r": radii[i], "f": 0.5}
        for i in range(len(radii))
    ]
    telemetry = {
        "mouse_movements": touch_moves,
        "clicks": [{"x": touch_moves[-1]["x"], "y": touch_moves[-1]["y"], "t": 1200}],
        "browser": {
            "webdriver": False,
            "screen_width": 390,
            "screen_height": 844,
            "touch_supported": True,
            "max_touch_points": 5,
        },
    }

    _score, _classification, reasons, _ = analyze_behavior(telemetry)
    assert any("Capacitive human touch contact verified" in r for r in reasons)


def test_v1_mobile_swipe_straightness_enforced():
    """
    Mobile swipe trajectory with straightness > 0.995 and mouse_points >= 5 must be penalized
    even when touch_supported is True and capacitive data is present.
    """
    radii = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0]
    swipe_moves = [
        {"x": 100, "y": 100 + i * 20, "t": 1000 + i * 25, "r": radii[i], "f": 0.5}
        for i in range(len(radii))
    ]
    telemetry = {
        "mouse_movements": swipe_moves,
        "clicks": [{"x": swipe_moves[-1]["x"], "y": swipe_moves[-1]["y"], "t": 1200}],
        "browser": {
            "webdriver": False,
            "screen_width": 390,
            "screen_height": 844,
            "touch_supported": True,
            "max_touch_points": 5,
        },
    }

    score, classification, reasons, _ = analyze_behavior(telemetry)
    assert any("Euclidean straight-line trajectory detected" in r for r in reasons)
    assert classification == "Bot"


# ---------------------------------------------------------------------------
# Vulnerability 2: Gray Area PoW Exploitation Remediation
# ---------------------------------------------------------------------------


def test_v2_hard_bot_violation_vetoes_pow_zero_interaction():
    """
    A request with zero user interaction (total_interactive_events == 0) must be denied PoW redemption.
    """
    ch = generate_challenge()
    telemetry = {
        "mouse_movements": [],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "is_webgl_hooked": True,
        },
    }
    env = {"challenge": ch["challenge"], "telemetry": telemetry}
    token = base64.b64encode(json.dumps(env).encode()).decode()

    decision = evaluate_synapse_request_sync(
        client_ip="10.0.0.1",
        user_agent="Mozilla/5.0",
        token=token,
        enable_pow=True,
    )
    # Zero interaction is a hard bot violation -> action must not be 'challenge'
    assert decision.action != "challenge"


def test_v2_hard_bot_violation_vetoes_pow_macro_teleport():
    """
    Macro teleportation (1 <= mouse_points <= 2 before interaction) must be denied PoW redemption.
    """
    ch = generate_challenge()
    telemetry = {
        "mouse_movements": [
            {"x": 100, "y": 100, "t": 1000},
            {"x": 500, "y": 500, "t": 1010},
        ],
        "clicks": [{"x": 500, "y": 500, "t": 1020}],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
        },
    }
    env = {"challenge": ch["challenge"], "telemetry": telemetry}
    token = base64.b64encode(json.dumps(env).encode()).decode()

    decision = evaluate_synapse_request_sync(
        client_ip="10.0.0.2",
        user_agent="Mozilla/5.0",
        token=token,
        enable_pow=True,
    )
    assert decision.action != "challenge"


def test_v2_pow_salt_bound_to_ip():
    """
    PoW salt signed for IP A must fail verification when presented by IP B.
    """
    ip_a = "192.168.1.100"
    ip_b = "192.168.1.200"

    salt_a = generate_pow_salt(client_ip=ip_a)

    assert verify_pow_salt(salt_a, client_ip=ip_a) is True
    assert verify_pow_salt(salt_a, client_ip=ip_b) is False
    assert verify_pow_salt(salt_a, client_ip=None) is False


def test_v2_pow_gray_area_narrowed_range():
    """
    Bot scores >= 55.0 must not be issued PoW challenges (range narrowed to 35 <= score < 55).
    """
    ch = generate_challenge()
    linear_points = [{"x": i * 15, "y": i * 15, "t": 1000 + i * 20} for i in range(20)]
    telemetry = {
        "mouse_movements": linear_points,
        "clicks": [{"x": linear_points[-1]["x"], "y": linear_points[-1]["y"], "t": 1450}],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
    }
    env = {"challenge": ch["challenge"], "telemetry": telemetry}
    token = base64.b64encode(json.dumps(env).encode()).decode()

    decision = evaluate_synapse_request_sync(
        client_ip="10.0.0.3",
        user_agent="Mozilla/5.0",
        token=token,
        enable_pow=True,
    )
    assert decision.action == "block"
    assert decision.bot_score >= 55.0


# ---------------------------------------------------------------------------
# Vulnerability 3: Fuzzy Kinematic Similarity, Click Alignment & Relative Timestamps
# ---------------------------------------------------------------------------


def test_v3_fuzzy_kinematic_similarity_session_invariance():
    """
    Attacker replaying identical kinetic template with added coordinate jitter (delta < 0.015)
    across 3 requests in a session must trigger +70.0 risk and Session Behavioral Invariance.
    """
    session_history = [
        {"avg_jerk": 0.0001500, "straightness": 0.9450, "total_distance": 250.0},
        {"avg_jerk": 0.0001503, "straightness": 0.9452, "total_distance": 250.2},
        {"avg_jerk": 0.0001501, "straightness": 0.9449, "total_distance": 249.9},
    ]

    telemetry = {
        "mouse_movements": [{"x": 100 + i * 10, "y": 100 + i * 5, "t": 1000 + i * 25} for i in range(15)],
        "clicks": [{"x": 240, "y": 170, "t": 1400}],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
    }

    score, classification, reasons, details = analyze_behavior(telemetry, session_history=session_history)
    assert any("High fuzzy kinematic similarity detected across session requests" in r for r in reasons)
    assert classification == "Bot"
    assert score >= 70.0


def test_v3_click_to_cursor_spatial_misalignment():
    """
    Telemetry where click coordinate is > 50px away from the last mouse position
    must trigger +65.0 penalty for Trajectory Replay Bot.
    """
    moves = [{"x": 100 + i * 5, "y": 200 + i * 5, "t": 1000 + i * 30} for i in range(20)]
    misaligned_click = [{"x": 800.0, "y": 600.0, "t": 1700}]

    telemetry = {
        "mouse_movements": moves,
        "clicks": misaligned_click,
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
    }

    score, classification, reasons, _ = analyze_behavior(telemetry)
    assert any("Click-to-cursor spatial misalignment" in r for r in reasons)
    assert score >= 65.0
    assert classification == "Bot"


def test_v3_relative_timestamp_bounds():
    """
    Relative timestamps with negative values (min_t < 0) or max_t > elapsed_ms + 500
    must be rejected with Relative Timestamp Anomaly.
    """
    ch = generate_challenge()
    tok_nonce = ch["challenge"]

    bad_telemetry_neg = {
        "mouse_movements": [{"x": 10, "y": 10, "t": -100}],
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
    }
    env_neg = {"challenge": tok_nonce, "telemetry": bad_telemetry_neg}
    tok_str_neg = base64.b64encode(json.dumps(env_neg).encode()).decode()

    valid_neg, reason_neg, _ = verify_and_consume_token(tok_str_neg)
    assert valid_neg is False
    assert "Relative Timestamp Anomaly" in reason_neg or "Zaman manipülasyonu" in reason_neg


# ---------------------------------------------------------------------------
# Vulnerability 4: Secret-Keyed Dynamic Threshold Jitter
# ---------------------------------------------------------------------------


def test_v4_secret_keyed_threshold_jitter():
    """
    Critical decision thresholds must be shifted deterministically within ±5% based on SECRET_KEY.
    """
    base_straightness = 0.985
    base_jerk = 0.00008

    dynamic_straightness = _get_dynamic_threshold(base_straightness, "straightness", spread_pct=0.05)
    dynamic_jerk = _get_dynamic_threshold(base_jerk, "avg_jerk", spread_pct=0.05)

    assert 0.985 * 0.95 <= dynamic_straightness <= 0.985 * 1.05
    assert 0.00008 * 0.95 <= dynamic_jerk <= 0.00008 * 1.05
    assert dynamic_straightness == _get_dynamic_threshold(base_straightness, "straightness", spread_pct=0.05)


# ---------------------------------------------------------------------------
# Vulnerability 5: Storage Bot Strike Count & train.py Anti-Poisoning Filter
# ---------------------------------------------------------------------------


def test_v5_storage_bot_strike_count_and_ip_penalty():
    """
    Storage must track bot strikes, provide get_bot_strike_count(ip, window_sec),
    and set is_ip_penalized=True when strikes >= 1.
    """
    storage = get_storage()
    test_ip = "192.0.2.77"

    storage.clear_all()
    assert storage.get_bot_strike_count(test_ip, window_sec=60) == 0

    storage.record_bot_strike(test_ip, threshold=4, window_sec=60)
    assert storage.get_bot_strike_count(test_ip, window_sec=60) >= 1

    telemetry = {
        "mouse_movements": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
    }
    score, _, reasons, _ = analyze_behavior(telemetry, is_ip_penalized=True)
    assert score >= 40.0
    assert any("IP address is temporarily penalized" in r for r in reasons)


def test_v5_train_per_ip_sample_capping(tmp_path):
    """
    load_training_data must cap samples per IP to <= 3 to prevent model poisoning
    even if an attacker logs 10,000 requests from the same IP.
    """
    db_file = str(tmp_path / "test_synapse.db")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ip TEXT,
            user_agent TEXT,
            bot_score REAL,
            classification TEXT,
            threat_type TEXT DEFAULT 'UNKNOWN',
            reasons TEXT,
            features TEXT,
            telemetry TEXT
        )
    """)

    attacker_ip = "198.51.100.1"
    clean_sample_telemetry = json.dumps({
        "mouse_movements": [{"x": 10 * i, "y": 10 * i, "t": 1000 + i * 20} for i in range(10)],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080},
    })
    for _ in range(50):
        cursor.execute(
            """INSERT INTO logs (timestamp, ip, bot_score, classification, threat_type, reasons, features, telemetry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "2026-10-21 12:00:00",
                attacker_ip,
                95.0,
                "Bot",
                "LINEAR_MACRO",
                json.dumps(["Linear straight line"]),
                "{}",
                clean_sample_telemetry,
            ),
        )
    conn.commit()
    conn.close()

    with patch("synapse_shield.train.DB_FILE", db_file):
        x_data, y_data = load_training_data(limit=1000, bootstrap=False, include_adversarial=False)
        bot_samples = [x for x, y in zip(x_data, y_data) if y == 1.0]
        assert len(bot_samples) == 3
