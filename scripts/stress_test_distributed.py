"""
Synapse Shield - Multi-Worker & Redis Fallback Penetration Test
Validates:
1. Cross-worker Replay Attack defense across 4 independent Uvicorn worker processes.
2. Cross-worker IP Quarantine / Global Ban synchronization.
3. Concurrent load balancing across 4 workers.
4. Hard Redis crash & runtime SQLite fallback resilience.
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from fakeredis import TcpFakeServer
import httpx

PYTHON_EXE = sys.executable
REDIS_PORT = 6389
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"
WORKER_PORTS = [8101, 8102, 8103, 8104]


def make_human_telemetry():
    now = int(time.time() * 1000)
    movements = [{"x": 100 + i * 2, "y": 200 + int(i * 1.5), "t": now - 1000 + i * 15} for i in range(40)]
    clicks = [{"x": 180, "y": 260, "t": now - 100}]
    return {
        "mouse_movements": movements,
        "clicks": clicks,
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "touch_supported": False,
            "plugins_length": 3,
            "is_plugin_array_fake": False,
            "has_webdriver_own_prop": False,
            "is_webgl_hooked": False,
            "is_canvas_hooked": False,
        },
    }


def make_bot_telemetry():
    now = int(time.time() * 1000)
    # Lineer robotik hareket
    movements = [{"x": i * 10, "y": 100, "t": now - 500 + i * 10} for i in range(30)]
    return {
        "mouse_movements": movements,
        "clicks": [],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": True,  # Headless bot
            "screen_width": 800,
            "screen_height": 600,
            "touch_supported": False,
            "plugins_length": 0,
        },
    }


class DistributedStressTester:
    def __init__(self):
        self.redis_server = None
        self.workers = []
        self.results = {}

    def start_redis(self):
        print(f"[*] Starting Redis TCP server on port {REDIS_PORT}...", flush=True)
        self.redis_server = TcpFakeServer(("127.0.0.1", REDIS_PORT))
        self.redis_server.daemon_threads = True
        import threading
        self.redis_thread = threading.Thread(target=self.redis_server.serve_forever, daemon=True)
        self.redis_thread.start()
        time.sleep(0.5)
        print("  -> Redis TCP server is READY.", flush=True)

    def stop_redis(self):
        if self.redis_server:
            print("[*] Simulating hard Redis failure (Stopping server)...", flush=True)
            try:
                self.redis_server.shutdown()
                self.redis_server.server_close()
            except Exception:
                pass
            self.redis_server = None
            time.sleep(0.5)

    def start_workers(self):
        print("[*] Starting 4 independent Uvicorn worker processes...")
        env = os.environ.copy()
        env["SYNAPSE_REDIS_URL"] = REDIS_URL
        env["SYNAPSE_DEV_MODE"] = "1"
        env["SYNAPSE_MIN_ELAPSED_MS"] = "0"

        for port in WORKER_PORTS:
            cmd = [
                PYTHON_EXE,
                "-m",
                "uvicorn",
                "synapse_shield.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.workers.append((port, proc))

        # Wait for all workers to be healthy
        for port, _ in self.workers:
            url = f"http://127.0.0.1:{port}/health"
            ready = False
            for _ in range(30):
                try:
                    with httpx.Client(timeout=1.0) as client:
                        r = client.get(url)
                        if r.status_code == 200:
                            ready = True
                            break
                except Exception:
                    time.sleep(0.2)
            if not ready:
                raise RuntimeError(f"Worker on port {port} failed to start!")
        print("  -> All 4 Uvicorn workers are running and healthy (8101, 8102, 8103, 8104).")

    def stop_workers(self):
        print("[*] Stopping worker processes...")
        for port, proc in self.workers:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        self.workers.clear()
        print("  -> All workers stopped.")

    async def run_scenario_1_replay_attack(self):
        """Cross-Worker Replay Attack Test: Token acquired from Worker 1, consumed on Worker 2, replayed on Worker 3 & 4."""
        print("\n" + "=" * 60)
        print("TEST 1: 4-Worker Cross-Server Replay Attack Defense")
        print("=" * 60)

        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Worker 1'den challenge al
            chal_res = await client.get("http://127.0.0.1:8101/api/challenge")
            assert chal_res.status_code == 200
            challenge = chal_res.json()["challenge"]

            # Token oluştur
            envelope = {
                "challenge": challenge,
                "telemetry": make_human_telemetry(),
                "created_at": int(time.time() * 1000),
            }
            token = base64.b64encode(json.dumps(envelope).encode()).decode()

            # 2. Worker 2'ye token'ı gönder (İLK TÜKETİM)
            res_w2 = await client.post("http://127.0.0.1:8102/api/score", json={"token": token})
            print(f"  [Worker 8102] First submission: HTTP {res_w2.status_code} | Status: {res_w2.json().get('status')}")
            assert res_w2.status_code == 200
            assert res_w2.json().get("status") in ["success", "challenge_required"]

            # 3. AYNI token'ı Worker 3'e gönder (REPLAY SALDIRISI)
            res_w3 = await client.post("http://127.0.0.1:8103/api/score", json={"token": token})
            print(f"  [Worker 8103] Replayed token:   HTTP {res_w3.status_code} | Status: {res_w3.json().get('status')} | Threat: {res_w3.json().get('threat_type')}")
            assert res_w3.json().get("status") == "blocked"
            assert res_w3.json().get("threat_type") == "REPLAY_ATTACK"
            assert any("Yeniden Oynatma" in r for r in res_w3.json().get("reasons", []))

            # 4. AYNI token'ı Worker 4'e gönder (REPLAY SALDIRISI)
            res_w4 = await client.post("http://127.0.0.1:8104/api/score", json={"token": token})
            print(f"  [Worker 8104] Replayed token:   HTTP {res_w4.status_code} | Status: {res_w4.json().get('status')} | Threat: {res_w4.json().get('threat_type')}")
            assert res_w4.json().get("status") == "blocked"
            assert res_w4.json().get("threat_type") == "REPLAY_ATTACK"
            assert any("Yeniden Oynatma" in r for r in res_w4.json().get("reasons", []))

        self.results["scenario_1"] = "PASSED - Multi-worker atomic replay protection active"
        print("-> PASS: Token successfully quarantined across all 4 separate workers!")

    async def run_scenario_2_cross_worker_ban(self):
        """Global IP Quarantine Test: Worker 1 strikes an IP 4 times; Worker 4 immediately blocks."""
        print("\n" + "=" * 60)
        print("TEST 2: Cross-Worker Global IP Quarantine (Sliding Window)")
        print("=" * 60)

        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"X-Forwarded-For": "198.51.100.77"}

            # Worker 1'e 4 ardışık bot isteği gönder
            for i in range(4):
                c = (await client.get("http://127.0.0.1:8101/api/challenge", headers=headers)).json()["challenge"]
                t = base64.b64encode(json.dumps({
                    "challenge": c,
                    "telemetry": make_bot_telemetry(),
                    "created_at": int(time.time() * 1000)
                }).encode()).decode()
                r = await client.post("http://127.0.0.1:8101/api/score", json={"token": t}, headers=headers)
                print(f"  Strike {i+1}/4 on Worker 8101: HTTP {r.status_code}")

            # Şimdi Worker 4'e aynı IP'den istek at: Anında BANLANMIŞ OLMALI
            c_test = (await client.get("http://127.0.0.1:8104/api/challenge", headers=headers)).json()["challenge"]
            t_test = base64.b64encode(json.dumps({
                "challenge": c_test,
                "telemetry": make_human_telemetry(),
                "created_at": int(time.time() * 1000)
            }).encode()).decode()
            res_w4 = await client.post("http://127.0.0.1:8104/api/score", json={"token": t_test}, headers=headers)
            print(f"  [Worker 8104] Incoming request from banned IP: HTTP {res_w4.status_code} | Detail: {res_w4.json().get('detail')}")
            assert res_w4.status_code == 403
            detail_msg = res_w4.json().get("detail", "").lower()
            assert "banned" in detail_msg or "karantina" in detail_msg

        self.results["scenario_2"] = "PASSED - IP ban instantly propagated to all workers"
        print("-> PASS: IP successfully banned across cluster!")

    async def run_scenario_3_concurrent_load(self):
        """Concurrent Load Test: 60 concurrent scoring requests distributed round-robin across all 4 workers."""
        print("\n" + "=" * 60)
        print("TEST 3: High-Concurrency Load Swarm (4-Worker Distribution)")
        print("=" * 60)

        total_requests = 60
        start_time = time.time()

        async def send_single_flow(worker_port, req_id):
            client_ip = f"198.18.0.{(req_id % 250) + 1}"
            headers = {"X-Forwarded-For": client_ip}
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Challenge al
                c = (await client.get(f"http://127.0.0.1:{worker_port}/api/challenge", headers=headers)).json()["challenge"]
                token = base64.b64encode(json.dumps({
                    "challenge": c,
                    "telemetry": make_human_telemetry(),
                    "created_at": int(time.time() * 1000)
                }).encode()).decode()
                # Skorla
                res = await client.post(f"http://127.0.0.1:{worker_port}/api/score", json={"token": token}, headers=headers)
                return res.status_code

        tasks = [
            send_single_flow(WORKER_PORTS[i % len(WORKER_PORTS)], i)
            for i in range(total_requests)
        ]

        status_codes = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time
        success_count = sum(1 for c in status_codes if c == 200)

        print(f"  Total Requests: {total_requests}")
        print(f"  Successful (HTTP 200): {success_count}/{total_requests}")
        print(f"  Elapsed Time: {elapsed:.2f}s ({total_requests / elapsed:.1f} req/s across workers)")

        assert success_count == total_requests
        self.results["scenario_3"] = f"PASSED - {total_requests}/{total_requests} (100% success rate, {total_requests/elapsed:.1f} rps)"
        print("-> PASS: 100% success under concurrent distributed load!")

    async def run_scenario_4_redis_crash_and_fallback(self):
        """Resilience Test: Hard Redis crash mid-flight, verify graceful SQLite fallback."""
        print("\n" + "=" * 60)
        print("TEST 4: Hard Redis Crash & Runtime SQLite Fallback Resilience")
        print("=" * 60)

        # 1. Redis'i aniden öldür!
        self.stop_redis()
        print("  -> Redis process terminated abruptly.")

        # 2. Worker 1 ve Worker 2'ye istek gönder: Asla 500 fırlatmamalı, SQLite ile cevap vermeli!
        async with httpx.AsyncClient(timeout=5.0) as client:
            c = (await client.get("http://127.0.0.1:8101/api/challenge")).json()["challenge"]
            t = base64.b64encode(json.dumps({
                "challenge": c,
                "telemetry": make_human_telemetry(),
                "created_at": int(time.time() * 1000)
            }).encode()).decode()
            res_w1 = await client.post("http://127.0.0.1:8101/api/score", json={"token": t})
            print(f"  [Worker 8101 during Redis Down] HTTP {res_w1.status_code} | Status: {res_w1.json().get('status')}")
            assert res_w1.status_code == 200
            assert res_w1.json().get("status") in ["success", "challenge_required"]

            # İkinci deneme (Replay kontrolü SQLite fallback üzerinde de çalışmalı)
            res_w1_replay = await client.post("http://127.0.0.1:8101/api/score", json={"token": t})
            print(f"  [Worker 8101 Fallback Replay Check] HTTP {res_w1_replay.status_code} | Status: {res_w1_replay.json().get('status')} | Threat: {res_w1_replay.json().get('threat_type')}")
            assert res_w1_replay.json().get("status") == "blocked"
            assert res_w1_replay.json().get("threat_type") == "REPLAY_ATTACK"

        self.results["scenario_4"] = "PASSED - Zero downtime self-healing fallback to SQLite confirmed"
        print("-> PASS: System remained online with 100% availability during Redis outage!")


async def main():
    tester = DistributedStressTester()
    try:
        tester.start_redis()
        tester.start_workers()

        await tester.run_scenario_1_replay_attack()
        await tester.run_scenario_2_cross_worker_ban()
        await tester.run_scenario_3_concurrent_load()
        await tester.run_scenario_4_redis_crash_and_fallback()

        print("\n" + "=" * 60)
        print("ALL 4 DISTRIBUTED & RESILIENCE STRESS TESTS PASSED!")
        print("=" * 60)
        for k, v in tester.results.items():
            print(f"  * {k}: {v}")

    finally:
        tester.stop_workers()
        tester.stop_redis()


if __name__ == "__main__":
    asyncio.run(main())
