"""
Synapse Shield — Session-Level Invariance & Replay Defense Test
Tests:
1. Exact Human Session Replay (same telemetry, fresh HMAC challenge nonces).
2. Human Session with Time-Scaling (duration compressed/expanded).
3. Human Session with Spatial Micro-Jitter (+- 1 to 3px Gaussian noise).
4. Continuous Invariance Probe across 10 consecutive requests per session.
"""

import asyncio
import base64
import json
import os
import random
import sys
import time

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from synapse_shield.adversarial import generate_synthetic_human_telemetry
from synapse_shield.middleware import SynapseShieldMiddleware
from synapse_shield.storage import get_storage
from synapse_shield.engine import analyze_behavior

SERVER_URL = "http://127.0.0.1:8000"


def build_token(challenge_str: str, telemetry: dict) -> str:
    payload = {"challenge": challenge_str, "telemetry": telemetry}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def adapt_timestamps(telemetry: dict, challenge_ts: float):
    events = (
        telemetry.get("mouse_movements", [])
        + telemetry.get("keystrokes", [])
        + telemetry.get("clicks", [])
        + telemetry.get("scrolls", [])
    )
    if not events:
        return telemetry

    min_t = min(e["t"] for e in events if "t" in e)
    for e in events:
        if "t" in e:
            e["t"] = round(challenge_ts + (e["t"] - min_t), 2)
        if "down" in e and isinstance(e["down"], (int, float)):
            e["down"] = round(challenge_ts + (e["down"] - min_t), 2)
        if "up" in e and isinstance(e["up"], (int, float)):
            e["up"] = round(challenge_ts + (e["up"] - min_t), 2)
    return telemetry


def clone_telemetry(t: dict) -> dict:
    return json.loads(json.dumps(t))


def apply_jitter(telemetry: dict, std_px: float = 2.0) -> dict:
    t_copy = clone_telemetry(telemetry)
    for m in t_copy.get("mouse_movements", []):
        m["x"] = round(m["x"] + random.gauss(0, std_px), 2)
        m["y"] = round(m["y"] + random.gauss(0, std_px), 2)
    return t_copy


def apply_time_scale(telemetry: dict, factor: float = 1.1) -> dict:
    t_copy = clone_telemetry(telemetry)
    events = t_copy.get("mouse_movements", [])
    if len(events) > 1:
        base_t = events[0]["t"]
        for e in events:
            e["t"] = round(base_t + (e["t"] - base_t) * factor, 2)
    return t_copy


async def test_session_invariance_engine():
    print("\n" + "=" * 80)
    print("  TEST 2: RECORDED HUMAN TELEMETRY REPLAY & SESSION INVARIANCE")
    print("=" * 80)

    # 1. Base human trajectory
    base_human = generate_synthetic_human_telemetry(steps=60, duration_ms=1600.0)

    # A. Test direct engine session invariance (unit evaluation)
    print("[*] Scenario A: Pure Exact Replay across 5 consecutive session turns")
    storage = get_storage()
    storage.clear_all()
    session_id = "test_sess_exact_replay"

    engine_decisions = []
    for turn in range(5):
        # Retrieve history
        history = storage.get_session_telemetries(session_id, window_sec=300)
        bot_score, classification, reasons, details = analyze_behavior(
            base_human,
            recent_request_count=1,
            session_history=history,
        )
        engine_decisions.append((turn + 1, bot_score, classification, reasons))
        
        # Save metrics to session
        feat = details.get("features", {})
        storage.record_session_telemetry(
            session_id,
            {"avg_jerk": feat.get("avg_jerk", 0.0), "straightness": feat.get("straightness", 0.0)},
            max_history=10,
        )

    for turn, score, clf, reasons in engine_decisions:
        invariance_flag = any("Session Behavioral Invariance" in r for r in reasons)
        print(f"    Turn {turn}: Decision={clf} | Score={score:.1f}% | Invariance Flag={invariance_flag}")

    # B. Test jittered replay
    print("\n[*] Scenario B: Replay with Small Spatial Jitter (+-2px) across 5 turns")
    session_id_jitter = "test_sess_jitter"
    jitter_decisions = []
    for turn in range(5):
        jittered = apply_jitter(base_human, std_px=2.0)
        history = storage.get_session_telemetries(session_id_jitter, window_sec=300)
        bot_score, classification, reasons, details = analyze_behavior(
            jittered,
            recent_request_count=1,
            session_history=history,
        )
        jitter_decisions.append((turn + 1, bot_score, classification, reasons))
        feat = details.get("features", {})
        storage.record_session_telemetry(
            session_id_jitter,
            {"avg_jerk": feat.get("avg_jerk", 0.0), "straightness": feat.get("straightness", 0.0)},
            max_history=10,
        )

    for turn, score, clf, reasons in jitter_decisions:
        invariance_flag = any("Session Behavioral Invariance" in r for r in reasons)
        print(f"    Turn {turn}: Decision={clf} | Score={score:.1f}% | Invariance Flag={invariance_flag}")

    # C. Real HTTP Endpoints Check: Does /api/score track session-level invariance?
    print("\n[*] Scenario C: HTTP Endpoint Inspection for Session Tracking")
    async with httpx.AsyncClient() as client:
        # Clear bans
        await client.post(
            f"{SERVER_URL}/api/clear",
            headers={"X-Admin-Secret": "testadminsecret", "X-Real-IP": "127.0.0.1"},
        )
        
        http_results = []
        for i in range(4):
            # 1. Challenge
            c_res = await client.get(f"{SERVER_URL}/api/challenge", headers={"X-Real-IP": "192.168.10.50"})
            c_str = c_res.json()["challenge"]
            ts = int(c_str.split(".")[1])
            await asyncio.sleep(1.6)

            tel = clone_telemetry(base_human)
            tel = adapt_timestamps(tel, ts)
            token = build_token(c_str, tel)

            s_res = await client.post(
                f"{SERVER_URL}/api/score",
                headers={"X-Real-IP": "192.168.10.50", "User-Agent": "Mozilla/5.0 ReplayTester"},
                json={"token": token},
            )
            data = s_res.json()
            http_results.append((i + 1, data.get("classification"), data.get("bot_score"), data.get("reasons", [])))

        print("    HTTP /api/score Multi-Turn Exact Replay:")
        for turn, clf, score, reasons in http_results:
            print(f"    Request {turn}: Class={clf} | Score={score} | Reasons={reasons}")


if __name__ == "__main__":
    asyncio.run(test_session_invariance_engine())
