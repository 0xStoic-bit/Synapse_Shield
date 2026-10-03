"""
Synapse Shield — Red Team Pure API Bypass Attack Simulation
Evaluates whether an attacker can bypass bot detection directly via the HTTP API
without running a real browser.

Tests:
1. Pure API with 1000 requests using synthetic biological human telemetry
2. Comparative attack vectors (Linear, Bezier, Sinusoidal, Minimum Jerk)
"""

import asyncio
import base64
import json
import os
import sys
import time
from collections import Counter

import httpx

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from synapse_shield.adversarial import (
    generate_bezier_telemetry,
    generate_linear_telemetry,
    generate_minimum_jerk_telemetry,
    generate_sine_oscillator_telemetry,
    generate_synthetic_human_telemetry,
)

SERVER_URL = "http://127.0.0.1:8000"


def build_token(challenge_str: str, telemetry: dict) -> str:
    payload = {
        "challenge": challenge_str,
        "telemetry": telemetry,
    }
    raw = json.dumps(payload).encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def adapt_timestamps(telemetry: dict, challenge_ts: float):
    """Aligns telemetry timestamps with the issued challenge timestamp."""
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


async def single_api_attempt(
    client: httpx.AsyncClient,
    ip: str,
    generator_func,
    generator_name: str,
    wait_sec: float = 1.6,
) -> dict:
    headers = {"X-Real-IP": ip, "User-Agent": "Synapse-RedTeam-DirectBypass/1.0"}

    # 1. /api/challenge
    try:
        t0 = time.time()
        c_res = await client.get(f"{SERVER_URL}/api/challenge", headers=headers, timeout=5.0)
        if c_res.status_code != 200:
            return {
                "vector": generator_name,
                "status_code": c_res.status_code,
                "classification": "CHALLENGE_FAILED",
                "risk": 100.0,
                "reason": f"Challenge HTTP {c_res.status_code}: {c_res.text}",
            }

        c_data = c_res.json()
        challenge_str = c_data["challenge"]
        ts = int(challenge_str.split(".")[1])

        # 2. Wait for challenge threshold (1.6s to avoid timing penalty)
        elapsed = time.time() - t0
        if elapsed < wait_sec:
            await asyncio.sleep(wait_sec - elapsed)

        # 3. Generate Telemetry & Adapt Timestamps
        tel = generator_func()
        tel = adapt_timestamps(tel, ts)

        # 4. Build Token
        token = build_token(challenge_str, tel)

        # 5. POST /api/score
        s_res = await client.post(
            f"{SERVER_URL}/api/score",
            headers=headers,
            json={"token": token},
            timeout=10.0,
        )

        if s_res.status_code == 200:
            s_data = s_res.json()
            return {
                "vector": generator_name,
                "status_code": 200,
                "classification": s_data.get("classification", "Unknown"),
                "risk": s_data.get("bot_score", 0.0),
                "status": s_data.get("status"),
                "reasons": s_data.get("reasons", []),
            }
        else:
            return {
                "vector": generator_name,
                "status_code": s_res.status_code,
                "classification": "HTTP_ERROR",
                "risk": 100.0,
                "reason": s_res.text,
            }
    except Exception as e:
        return {
            "vector": generator_name,
            "status_code": 0,
            "classification": "CLIENT_EXCEPTION",
            "risk": 100.0,
            "reason": str(e),
        }


async def run_batch(total_requests: int = 1000, concurrency: int = 40):
    print(f"\n[*] Starting Pure API Bypass Attack Simulation: {total_requests} requests (Concurrency: {concurrency})...")

    # Clear bans and logs first
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{SERVER_URL}/api/clear",
                headers={"X-Admin-Secret": "testadminsecret", "X-Real-IP": "127.0.0.1"},
                timeout=5.0,
            )
            print("[+] /api/clear executed successfully.")
        except Exception as e:
            print(f"[-] /api/clear failed: {e}")

    # Vector distribution:
    # 700 synthetic biological human, 100 linear, 100 bezier, 50 sine, 50 min_jerk
    vectors = (
        [("Synthetic_Human", generate_synthetic_human_telemetry)] * 700
        + [("Linear_Bot", generate_linear_telemetry)] * 100
        + [("Bezier_Bot", generate_bezier_telemetry)] * 100
        + [("Sine_Oscillator_Bot", generate_sine_oscillator_telemetry)] * 50
        + [("Minimum_Jerk_Bot", generate_minimum_jerk_telemetry)] * 50
    )

    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def worker(idx, vec_name, gen_func, http_client):
        # Distinct IP to simulate distributed botnet or avoid local challenge rate limits
        ip_addr = f"10.0.{idx // 250}.{1 + (idx % 250)}"
        async with semaphore:
            res = await single_api_attempt(http_client, ip_addr, gen_func, vec_name)
            return res

    start_time = time.time()
    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)) as http_client:
        tasks = [worker(i, vec_name, gen_func, http_client) for i, (vec_name, gen_func) in enumerate(vectors[:total_requests])]
        for f in asyncio.as_completed(tasks):
            r = await f
            results.append(r)
            if len(results) % 100 == 0:
                print(f"    Progress: {len(results)}/{total_requests} completed...")

    total_time = time.time() - start_time
    print(f"[+] Finished {len(results)} requests in {total_time:.2f}s ({len(results)/total_time:.1f} req/s).")

    # Group by vector
    vector_stats = {}
    for r in results:
        vec = r["vector"]
        if vec not in vector_stats:
            vector_stats[vec] = {"total": 0, "allow_human": 0, "block_bot": 0, "challenge_pow": 0, "error": 0, "risks": []}
        
        vector_stats[vec]["total"] += 1
        vector_stats[vec]["risks"].append(r.get("risk", 100.0))
        
        clf = r.get("classification")
        status = r.get("status")
        if clf == "Human":
            vector_stats[vec]["allow_human"] += 1
        elif status == "challenge_required":
            vector_stats[vec]["challenge_pow"] += 1
        elif clf == "Bot" or r.get("status_code") in (403, 400):
            vector_stats[vec]["block_bot"] += 1
        else:
            vector_stats[vec]["error"] += 1

    print("\n" + "=" * 90)
    print("  PURE API HEADLESS BYPASS ATTACK BENCHMARK (1000 REQUESTS)")
    print("=" * 90)
    print(f"{'ATTACK VECTOR':<24} | {'TOTAL':<6} | {'ALLOW (HUMAN)':<14} | {'BLOCK (BOT)':<12} | {'POW CHALLENGE':<14} | {'BYPASS RATE':<11}")
    print("-" * 90)
    for vec, st in vector_stats.items():
        bypass_pct = (st["allow_human"] / st["total"]) * 100.0 if st["total"] > 0 else 0.0
        print(f"{vec:<24} | {st['total']:<6} | {st['allow_human']:<14} | {st['block_bot']:<12} | {st['challenge_pow']:<14} | %{bypass_pct:<10.1f}")
    print("=" * 90)

    # Save results to json
    output_path = os.path.join(os.path.dirname(__file__), "..", "redteam_direct_api_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"summary": vector_stats, "details_count": len(results)}, f, indent=2)
    print(f"\n[+] Detailed results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(run_batch(1000, concurrency=50))
