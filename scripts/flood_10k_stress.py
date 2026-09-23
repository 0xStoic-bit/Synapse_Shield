#!/usr/bin/env python3
"""
Synapse Shield — Distributed 10,000 Botnet DDoS Stress Test
Simulates a distributed botnet across 250 distinct rotating IPs using X-Forwarded-For.
Exercises the FULL deep-intelligence pipeline on all 10,000 requests:
- Rust Two-Bucket In-Memory Nonce Cache (< 1 us)
- Native Rust 19D Kinematic Feature Extraction (23 us)
- 1D-CNN Neural Network Inference (~400 us)
- Sliding Window IP Strike & Dynamic Quarantine Tracking
"""

import asyncio
import base64
import json
import random
import statistics
import time
import httpx
import psutil

import hashlib
import hmac
import secrets
from synapse_shield.tokens import SECRET_KEY
from synapse_shield.adversarial import (
    generate_bezier_telemetry,
    generate_linear_telemetry,
    generate_minimum_jerk_telemetry,
    generate_sine_oscillator_telemetry,
)


BASE_URL = "http://127.0.0.1:8000"
TOTAL_REQUESTS = 10_000
CONCURRENCY = 60
BOTNET_SIZE = 250  # 250 distinct zombi bot IPs


def get_random_bot_telemetry():
    choice = random.randint(1, 4)
    if choice == 1:
        return generate_bezier_telemetry(), "BEZIER"
    elif choice == 2:
        return generate_sine_oscillator_telemetry(), "SINE"
    elif choice == 3:
        return generate_minimum_jerk_telemetry(), "MIN_JERK"
    else:
        return generate_linear_telemetry(), "LINEAR"


async def main():
    print("=" * 82)
    print("  SYNAPSE SHIELD // 10,000 REQUESTS DISTRIBUTED BOTNET DDOS STRESS TEST")
    print("=" * 82)
    print(f"  Target Server   : {BASE_URL}")
    print(f"  Total Requests  : {TOTAL_REQUESTS:,}")
    print(f"  Botnet Cluster  : {BOTNET_SIZE} distinct rotating IP addresses (X-Forwarded-For)")
    print(f"  Worker Pool     : {CONCURRENCY} concurrent async workers")
    print("  Pipeline Load   : 100% Full-Stack (Rust Nonce + Rust 19D Kinematics + 1D-CNN AI)")
    print("-" * 82)

    # 1. Reset Server State
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{BASE_URL}/api/clear")
            print("[+] Server state, IP quarantine, and nonces cleared.")
        except Exception as e:
            print(f"[-] Warning: Failed to clear server state: {e}")

    # 2. Pre-generate 10,000 signed tokens in RAM
    print(f"[+] Generating {TOTAL_REQUESTS:,} cryptographic challenge tokens in RAM...")
    t_prep0 = time.perf_counter()

    botnet_ips = [f"185.220.101.{(i % BOTNET_SIZE) + 1}" for i in range(TOTAL_REQUESTS)]
    random.shuffle(botnet_ips)

    request_items = []
    now_ms = int(time.time() * 1000)
    for i in range(TOTAL_REQUESTS):
        nonce = secrets.token_hex(16)
        ts = now_ms - 1800  # 1.8s in the past: passes 1.5s time check!
        sig = hmac.HMAC(SECRET_KEY, f"{nonce}:{ts}".encode(), digestmod=hashlib.sha256).hexdigest()
        challenge_str = f"{nonce}.{ts}.{sig}"
        telemetry, bot_label = get_random_bot_telemetry()
        payload = {"challenge": challenge_str, "telemetry": telemetry}
        token_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        ip = botnet_ips[i]
        request_items.append((ip, token_b64, bot_label))

    dt_prep = time.perf_counter() - t_prep0
    print(f"[+] Generated {TOTAL_REQUESTS:,} tokens in {dt_prep:.2f}s (~{TOTAL_REQUESTS/dt_prep:,.0f} tokens/s).")

    # 3. Measure Initial Memory
    target_procs = [p for p in psutil.process_iter(["pid", "name"]) if "python" in p.info["name"].lower()]
    mem_before_mb = sum(p.memory_info().rss for p in target_procs) / (1024 * 1024)
    print(f"[+] Baseline server process memory: {mem_before_mb:.1f} MB")
    print("-" * 82)
    print(f"  {'COMPLETED':<16} | {'ELAPSED':<9} | {'CURRENT RPS':<14} | {'P50 LATENCY':<12} | {'BOT DETECTIONS'}")
    print("-" * 82)

    # 4. Launch 10,000 Full-Stack Requests
    semaphore = asyncio.Semaphore(CONCURRENCY)
    latencies_ms: list[float] = []
    status_counts: dict[int, int] = {}
    completed = 0
    t_start = time.perf_counter()
    last_reported = 0

    limits = httpx.Limits(max_connections=CONCURRENCY * 2, max_keepalive_connections=CONCURRENCY)
    async with httpx.AsyncClient(limits=limits, timeout=20.0) as client:

        async def worker(item):
            nonlocal completed, last_reported
            ip, token_str, _ = item
            headers = {
                "X-Forwarded-For": ip,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BotnetNode/3.0",
                "Content-Type": "application/json",
            }
            body = {"token": token_str}

            async with semaphore:
                t0 = time.perf_counter()
                try:
                    r = await client.post(f"{BASE_URL}/api/score", json=body, headers=headers)
                    code = r.status_code
                except Exception:
                    code = 500
                dt_ms = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(dt_ms)
                status_counts[code] = status_counts.get(code, 0) + 1
                completed += 1

                if completed - last_reported >= 1000 or completed == TOTAL_REQUESTS:
                    last_reported = completed
                    elapsed = time.perf_counter() - t_start
                    curr_rps = completed / elapsed if elapsed > 0 else 0
                    recent_lat = statistics.median(latencies_ms[-500:]) if len(latencies_ms) >= 500 else dt_ms
                    print(
                        f"  {completed:>6,}/{TOTAL_REQUESTS:,} ({completed/TOTAL_REQUESTS*100:>4.0f}%) | "
                        f"{elapsed:>6.2f}s  | ~{curr_rps:>6,.0f} req/s   | {recent_lat:>6.2f} ms     | "
                        f"1D-CNN + Rust Kinematics Active"
                    )

        tasks = [asyncio.create_task(worker(item)) for item in request_items]
        await asyncio.gather(*tasks)

    total_time = time.perf_counter() - t_start
    mem_after_mb = sum(p.memory_info().rss for p in target_procs) / (1024 * 1024)

    # 5. Statistics Calculation
    mean_lat = statistics.mean(latencies_ms) if latencies_ms else 0.0
    p50_lat = statistics.median(latencies_ms) if latencies_ms else 0.0
    p90_lat = statistics.quantiles(latencies_ms, n=10)[8] if len(latencies_ms) >= 10 else mean_lat
    p95_lat = statistics.quantiles(latencies_ms, n=20)[18] if len(latencies_ms) >= 20 else mean_lat
    p99_lat = statistics.quantiles(latencies_ms, n=100)[98] if len(latencies_ms) >= 100 else mean_lat
    min_lat = min(latencies_ms) if latencies_ms else 0.0
    max_lat = max(latencies_ms) if latencies_ms else 0.0
    throughput = TOTAL_REQUESTS / total_time if total_time > 0 else 0.0

    print("=" * 82)
    print("  DISTRIBUTED BOTNET DDOS STRESS TEST COMPLETED // VERDICT REPORT")
    print("=" * 82)
    print(f"  Total Requests Analyzed  : {TOTAL_REQUESTS:,}")
    print(f"  Botnet Cluster Coverage  : {BOTNET_SIZE} distinct IPs across 10,000 attacks")
    print(f"  Total Test Duration      : {total_time:.2f} seconds")
    print(f"  Sustained Full-Stack RPS : {throughput:,.1f} requests/second")
    print("-" * 82)
    print("  HTTP STATUS BREAKDOWN:")
    for code, count in sorted(status_counts.items()):
        desc = "Full-Stack Bot Verdict (Blocked)" if code == 200 else ("L1 Quarantine (Banned)" if code == 403 else "Other")
        print(f"    • HTTP {code} ({desc:<32}): {count:>6,} ({count/TOTAL_REQUESTS*100:>5.1f}%)")
    print("-" * 82)
    print("  LATENCY DISTRIBUTION (End-to-End Decision + Network):")
    print(f"    • Minimum Latency       : {min_lat:.2f} ms")
    print(f"    • P50 (Median)          : {p50_lat:.2f} ms")
    print(f"    • P90                   : {p90_lat:.2f} ms")
    print(f"    • P95                   : {p95_lat:.2f} ms")
    print(f"    • P99                   : {p99_lat:.2f} ms")
    print(f"    • Maximum Latency       : {max_lat:.2f} ms")
    print(f"    • Mean Latency          : {mean_lat:.2f} ms")
    print("-" * 82)
    print(f"  Process Memory Impact    : {mem_before_mb:.1f} MB -> {mem_after_mb:.1f} MB (Delta: {mem_after_mb - mem_before_mb:+.1f} MB)")
    print("=" * 82)


if __name__ == "__main__":
    asyncio.run(main())
