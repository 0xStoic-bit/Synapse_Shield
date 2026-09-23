#!/usr/bin/env python3
"""
Synapse Shield — Adversarial Attack & Bot Simulation CLI (v0.8.0)
Usage:
    python scripts/attack_sim.py --bot bezier --requests 50
    python scripts/attack_sim.py --bot sine --requests 100
    python scripts/attack_sim.py --bot human --requests 20
    python scripts/attack_sim.py --bot replay --requests 30
    python scripts/attack_sim.py --bot linear --requests 40
    python scripts/attack_sim.py --bot jerk --requests 50
"""

import argparse
import base64
import json
import statistics
import time
import urllib.request
import urllib.error

from synapse_shield.adversarial import (
    generate_bezier_telemetry,
    generate_linear_telemetry,
    generate_minimum_jerk_telemetry,
    generate_sine_oscillator_telemetry,
    generate_synthetic_human_telemetry,
)


# Terminal ANSI Colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"


def print_banner(bot_type: str, count: int, base_url: str):
    print(f"\n{BOLD}{CYAN}================================================================================{RESET}")
    print(f"{BOLD}{CYAN}  SYNAPSE SHIELD // ADVERSARIAL STRESS & ATTACK SIMULATOR [v0.8.0]{RESET}")
    print(f"{BOLD}{CYAN}================================================================================{RESET}")
    print(f"  Target Server   : {BOLD}{base_url}{RESET}")
    print(f"  Active Bot Mode : {BOLD}{YELLOW}{bot_type.upper()}{RESET}")
    print(f"  Total Requests  : {BOLD}{count}{RESET}")
    print(f"{CYAN}--------------------------------------------------------------------------------{RESET}")
    print(f"  {'#':<4} | {'HTTP':<4} | {'STATUS':<10} | {'RISK':<8} | {'CLASSIFICATION / DEFENSE TRIGGER':<35} | {'LATENCY':<10}")
    print(f"{CYAN}--------------------------------------------------------------------------------{RESET}")


def get_telemetry_for_bot(bot_type: str) -> dict:
    if bot_type == "bezier":
        return generate_bezier_telemetry()
    elif bot_type == "sine":
        return generate_sine_oscillator_telemetry(frequency_hz=10.0)
    elif bot_type == "linear":
        return generate_linear_telemetry()
    elif bot_type == "jerk":
        return generate_minimum_jerk_telemetry()
    elif bot_type == "human":
        return generate_synthetic_human_telemetry()
    else:
        return generate_bezier_telemetry()


def fetch_challenge(base_url: str) -> str | None:
    try:
        req = urllib.request.Request(f"{base_url}/api/challenge", headers={"User-Agent": "AttackSim/1.0"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("challenge")
    except Exception:
        return None


def clear_server_state(base_url: str):
    """Resets IP bans and state engine before test run."""
    try:
        req = urllib.request.Request(f"{base_url}/api/clear", method="POST")
        with urllib.request.urlopen(req, timeout=3.0):
            pass
    except Exception:
        pass


def run_simulation(bot_type: str, requests_count: int, base_url: str, delay_sec: float, auto_clear: bool):
    if auto_clear:
        clear_server_state(base_url)

    print_banner(bot_type, requests_count, base_url)

    cached_replay_token = None
    latencies_ms = []
    allowed_count = 0
    blocked_count = 0
    banned_count = 0
    strike_count = 0

    t_start = time.perf_counter()

    for idx in range(1, requests_count + 1):
        # 1. Challenge & Token Handling
        if bot_type == "replay":
            if cached_replay_token is None:
                chal = fetch_challenge(base_url)
                if not chal:
                    print(f"  {idx:<4} | {RED}ERR {RESET} | Connection failed to {base_url}")
                    continue
                time.sleep(1.6)
                telemetry = generate_synthetic_human_telemetry()
                payload = {"challenge": chal, "telemetry": telemetry}
                cached_replay_token = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
            token_str = cached_replay_token
        else:
            chal = fetch_challenge(base_url)
            if not chal:
                print(f"  {idx:<4} | {RED}ERR {RESET} | Could not reach server at {base_url}")
                continue

            # Humans and compliant bots wait realistic 1.6s
            if bot_type == "human":
                time.sleep(1.6)
            elif delay_sec > 0:
                time.sleep(delay_sec)

            telemetry = get_telemetry_for_bot(bot_type)
            payload = {"challenge": chal, "telemetry": telemetry}
            token_str = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

        # 2. Fire Request to /api/score
        post_data = json.dumps({"token": token_str}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/score",
            data=post_data,
            headers={"Content-Type": "application/json", "User-Agent": f"AttackSim-{bot_type.upper()}/1.0"},
        )

        req_t0 = time.perf_counter()
        http_code = 0
        response_body = {}

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                http_code = resp.status
                response_body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            http_code = e.code
            try:
                response_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                response_body = {"detail": str(e.reason)}
        except Exception as e:
            http_code = 500
            response_body = {"detail": str(e)}

        latency_ms = (time.perf_counter() - req_t0) * 1000.0
        latencies_ms.append(latency_ms)

        # 3. Analyze Verdict
        risk = response_body.get("bot_score", 0.0)
        classification = response_body.get("classification", "Unknown")
        threat = response_body.get("threat_type", "")
        status_field = response_body.get("status", "")

        is_banned = http_code == 403 and ("banned" in str(response_body).lower() or "quarantine" in str(response_body).lower())
        is_bot = classification == "Bot" or status_field == "blocked" or is_banned

        if is_banned:
            banned_count += 1
            blocked_count += 1
            status_str = f"{RED}BANNED{RESET}"
            risk_str = f"{RED}100.0%{RESET}"
            detail_str = f"{RED}403 FORBIDDEN (Rust L1 Ban Cache){RESET}"
        elif is_bot:
            blocked_count += 1
            strike_count += 1
            status_str = f"{YELLOW}BLOCKED{RESET}"
            risk_str = f"{YELLOW}%{risk:.1f}{RESET}"
            if strike_count <= 3:
                detail_str = f"{YELLOW}BOT DETECTED (Strike {strike_count}/4: {threat}){RESET}"
            elif strike_count == 4:
                detail_str = f"{RED}BOT DETECTED (Strike 4/4 -> BAN TRIGGERED!){RESET}"
            else:
                detail_str = f"{RED}BOT DETECTED ({threat}){RESET}"
        else:
            allowed_count += 1
            status_str = f"{GREEN}ALLOW{RESET}"
            risk_str = f"{GREEN}%{risk:.1f}{RESET}"
            detail_str = f"{GREEN}GENUINE HUMAN (Passed){RESET}"

        lat_color = GREEN if latency_ms < 1.0 else (YELLOW if latency_ms < 5.0 else RED)
        lat_str = f"{lat_color}{latency_ms:.2f} ms{RESET}"

        print(f"  {idx:<4} | {http_code:<4} | {status_str:<19} | {risk_str:<17} | {detail_str:<44} | {lat_str}")

        if delay_sec > 0 and bot_type != "human":
            time.sleep(delay_sec)

    # Summary
    total_time = time.perf_counter() - t_start
    mean_lat = statistics.mean(latencies_ms) if latencies_ms else 0.0
    p50_lat = statistics.median(latencies_ms) if latencies_ms else 0.0
    p95_lat = statistics.quantiles(latencies_ms, n=20)[18] if len(latencies_ms) >= 20 else mean_lat
    rps = requests_count / total_time if total_time > 0 else 0.0

    print(f"{CYAN}================================================================================{RESET}")
    print(f"  {BOLD}SIMULATION SUMMARY // VERDICT REPORT{RESET}")
    print(f"{CYAN}--------------------------------------------------------------------------------{RESET}")
    print(f"  Total Requests Sent : {BOLD}{requests_count}{RESET} across {total_time:.2f}s (~{rps:.1f} req/s)")
    print(f"  Allowed (Humans)    : {GREEN}{BOLD}{allowed_count}{RESET}")
    print(f"  Blocked (Bots)      : {YELLOW}{BOLD}{blocked_count}{RESET}")
    print(f"  L1 Banned Hits      : {RED}{BOLD}{banned_count}{RESET}")
    print(f"  Latency Profile     : Mean = {mean_lat:.2f} ms | P50 = {p50_lat:.2f} ms | P95 = {p95_lat:.2f} ms")
    print(f"{CYAN}================================================================================{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Synapse Shield Adversarial Bot & Stress Simulator")
    parser.add_argument(
        "--bot",
        choices=["bezier", "sine", "linear", "jerk", "human", "replay"],
        default="bezier",
        help="Bot pattern or legitimate human profile to simulate",
    )
    parser.add_argument("--requests", type=int, default=30, help="Total number of requests to fire")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="Base URL of Synapse Shield server")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between requests in seconds")
    parser.add_argument("--clear", action="store_true", help="Clear IP bans before starting simulation")

    args = parser.parse_args()
    run_simulation(
        bot_type=args.bot,
        requests_count=args.requests,
        base_url=args.url.rstrip("/"),
        delay_sec=args.delay,
        auto_clear=args.clear,
    )


if __name__ == "__main__":
    main()
