"""
Synapse Shield — Professional Locust Load Testing & Adversarial Bot Simulation Suite
Simulates realistic production traffic mixing genuine humans with aggressive bot attacks:
1. LegitimateHumanUser (Weight: 6) - Natural Fitts deceleration, human jitter, 1.8s wait
2. ReplayAttackBot (Weight: 2)     - Re-uses already consumed challenge tokens (Rust Two-Bucket target)
3. SyntheticLinearBot (Weight: 1)  - Mechanical mouse movements (straightness = 1.0, jerk = 0)
4. RapidFloodBot (Weight: 1)       - High-frequency brute force flood (DDoS / IP ban target)
"""

import base64
import json
import time
from locust import HttpUser, between, constant, task
from synapse_shield.adversarial import (
    generate_synthetic_human_telemetry,
    generate_bezier_telemetry,
)


class LegitimateHumanUser(HttpUser):
    """Simulates a genuine human visitor browsing with realistic biometric telemetry."""

    weight = 6
    wait_time = between(1.7, 2.5)

    @task
    def verify_clean_human(self):
        # 1. Fetch challenge token
        resp = self.client.get("/api/challenge", name="1. Challenge Request (Human)")
        if resp.status_code != 200:
            return
        data = resp.json()
        challenge = data.get("challenge")
        if not challenge:
            return

        # 2. Simulate human reading/interaction time
        time.sleep(1.6)

        # 3. Assemble biometric payload
        telemetry = generate_synthetic_human_telemetry()
        payload = {"challenge": challenge, "telemetry": telemetry}
        token_str = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

        # 4. Submit for verification
        with self.client.post(
            "/api/score",
            json={"token": token_str},
            name="2. Decision Scoring (Human)",
            catch_response=True,
        ) as score_resp:
            if score_resp.status_code == 200:
                body = score_resp.json()
                if body.get("classification") == "Human":
                    score_resp.success()
                else:
                    score_resp.failure(f"Unexpected classification: {body.get('classification')}")
            else:
                score_resp.failure(f"Expected HTTP 200, got {score_resp.status_code}")


class ReplayAttackBot(HttpUser):
    """Simulates an attacker re-playing already consumed tokens to bypass challenge limits."""

    weight = 2
    wait_time = between(0.2, 0.8)

    @task
    def replay_stolen_token(self):
        # 1. Fetch challenge
        resp = self.client.get("/api/challenge", name="1. Challenge Request (Bot)")
        if resp.status_code != 200:
            return
        challenge = resp.json().get("challenge")
        if not challenge:
            return

        time.sleep(1.6)
        telemetry = generate_synthetic_human_telemetry()
        payload = {"challenge": challenge, "telemetry": telemetry}
        token_str = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

        # 2. First consumption (valid)
        self.client.post("/api/score", json={"token": token_str}, name="2. Token Consume (Valid)")

        # 3. Replay attack: Fire the exact same token a 2nd time!
        with self.client.post(
            "/api/score",
            json={"token": token_str},
            name="3. Replay Attack Flood (Rust Two-Bucket Block)",
            catch_response=True,
        ) as replay_resp:
            if replay_resp.status_code in (200, 403):
                body = replay_resp.json() if replay_resp.content else {}
                if body.get("status") == "blocked" or "Replay" in str(body):
                    replay_resp.success()  # Successfully blocked by Rust Two-Bucket!
                else:
                    replay_resp.failure("Replay attack was NOT blocked by Synapse Shield!")
            else:
                replay_resp.failure(f"Unexpected status: {replay_resp.status_code}")


class SyntheticLinearBot(HttpUser):
    """Simulates an automated script with mathematical/bezier trajectories."""

    weight = 1
    wait_time = between(1.6, 2.0)

    @task
    def submit_robotic_telemetry(self):
        resp = self.client.get("/api/challenge", name="1. Challenge Request (Bot)")
        if resp.status_code != 200:
            return
        challenge = resp.json().get("challenge")
        if not challenge:
            return

        time.sleep(1.6)
        telemetry = generate_bezier_telemetry()
        payload = {"challenge": challenge, "telemetry": telemetry}
        token_str = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

        with self.client.post(
            "/api/score",
            json={"token": token_str},
            name="4. Robotic Curve Attack (CNN Block)",
            catch_response=True,
        ) as bot_resp:
            if bot_resp.status_code in (200, 403):
                body = bot_resp.json() if bot_resp.content else {}
                if body.get("classification") == "Bot" or body.get("status") == "blocked":
                    bot_resp.success()  # Successfully detected as Bot!
                else:
                    bot_resp.failure("Bot trajectory evaded 1D-CNN detection!")


class RapidFloodBot(HttpUser):
    """Simulates high-frequency flood attack targeting DoS & triggering IP quarantine."""

    weight = 1
    wait_time = constant(0.02)

    @task
    def rapid_burst(self):
        with self.client.post(
            "/api/score",
            json={"token": "forged_malicious_token_flood"},
            name="5. Brute Force Flood (L1 Ban Block)",
            catch_response=True,
        ) as flood_resp:
            if flood_resp.status_code in (400, 403):
                flood_resp.success()  # Successfully rejected
            else:
                flood_resp.failure(f"Unchecked flood: {flood_resp.status_code}")
