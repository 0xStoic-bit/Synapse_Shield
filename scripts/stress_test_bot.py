#!/usr/bin/env python3
"""
Asynchronous Stress-Testing Script for Protected API Endpoint
Tests various attack scenarios against http://127.0.0.1:8000/api/score
"""

import asyncio
import time
import json
import random
import string
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from httpx import AsyncClient, Timeout, Limits
import statistics

# Configuration
API_URL = "http://127.0.0.1:8000/api/score"
TIMEOUT_SECONDS = 10.0
MAX_CONNECTIONS = 50
MAX_KEEPALIVE = 20

# Sample valid token (would typically be intercepted from a legitimate request)
# This is a placeholder - you'd need to capture a real valid token
VALID_TOKEN = "valid_challenge_token_abc123xyz789"

# Mock payload templates
BASE_PAYLOAD = {
    "data": "test_data",
    "timestamp": None  # Will be filled dynamically
}

class StressTester:
    def __init__(self):
        self.results = {
            "scenario_a": [],
            "scenario_b": [],
            "scenario_c": []
        }
        self.request_count = 0
        
    def generate_random_payload(self) -> Dict:
        """Generate a random payload without challenge token"""
        payload = BASE_PAYLOAD.copy()
        payload["timestamp"] = datetime.utcnow().isoformat()
        payload["data"] = ''.join(random.choices(string.ascii_letters + string.digits, k=50))
        payload["random_id"] = ''.join(random.choices(string.digits, k=10))
        return payload

    def create_payload_with_token(self, token: str) -> Dict:
        """Create a payload with a challenge token"""
        payload = self.generate_random_payload()
        payload["challenge_token"] = token
        return payload

    async def send_request(self, client: AsyncClient, payload: Dict, scenario: str) -> Dict:
        """Send a single POST request and record metrics"""
        start_time = time.perf_counter()
        try:
            response = await client.post(
                API_URL,
                json=payload,
                timeout=TIMEOUT_SECONDS
            )
            elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
            
            result = {
                "status_code": response.status_code,
                "latency_ms": elapsed_time,
                "scenario": scenario,
                "request_id": self.request_count,
                "success": response.status_code < 400
            }
            
            # Print immediately for real-time monitoring
            print(f"  [#{self.request_count:04d}] Status: {response.status_code} | "
                  f"Latency: {elapsed_time:.2f}ms | Scenario: {scenario}")
            
            self.request_count += 1
            return result
            
        except Exception as e:
            elapsed_time = (time.perf_counter() - start_time) * 1000
            result = {
                "status_code": 0,
                "latency_ms": elapsed_time,
                "scenario": scenario,
                "request_id": self.request_count,
                "success": False,
                "error": str(e)
            }
            print(f"  [#{self.request_count:04d}] ERROR: {str(e)[:50]} | "
                  f"Latency: {elapsed_time:.2f}ms | Scenario: {scenario}")
            self.request_count += 1
            return result

    async def scenario_a_no_token(self, client: AsyncClient, num_requests: int = 10):
        """
        Scenario A: Send raw JSON payloads without cryptographic challenge token
        Expecting: 403 Forbidden / 400 Bad Request
        """
        print("\n" + "="*60)
        print(f"SCENARIO A: No Challenge Token (Sending {num_requests} requests)")
        print("="*60)
        
        tasks = []
        for _ in range(num_requests):
            payload = self.generate_random_payload()
            tasks.append(self.send_request(client, payload, "A_NoToken"))
        
        results = await asyncio.gather(*tasks)
        self.results["scenario_a"].extend(results)
        return results

    async def scenario_b_high_frequency(self, client: AsyncClient):
        """
        Scenario B: High-frequency burst attack - 15 rapid requests in under 500ms
        Testing the Poisson rate anomaly filter
        Expecting: 403 Forbidden (rate limit detected)
        """
        print("\n" + "="*60)
        print("SCENARIO B: High-Frequency Burst Attack (15 requests in <500ms)")
        print("="*60)
        
        start_time = time.perf_counter()
        
        # Create 15 tasks to be executed almost simultaneously
        tasks = []
        for i in range(15):
            payload = self.generate_random_payload()
            tasks.append(self.send_request(client, payload, "B_Burst"))
        
        # Execute all tasks concurrently (will be within ~100ms)
        results = await asyncio.gather(*tasks)
        
        total_time = (time.perf_counter() - start_time) * 1000
        print(f"\n  ⚡ Burst completed in: {total_time:.2f}ms")
        print(f"  📊 Average latency: {statistics.mean([r['latency_ms'] for r in results]):.2f}ms")
        
        self.results["scenario_b"].extend(results)
        return results

    async def scenario_c_replay_attack(self, client: AsyncClient):
        """
        Scenario C: Intercept one valid token and replay it 5 times consecutively
        Testing Replay Attack defense
        Expecting: 403 Forbidden (replay detected)
        """
        print("\n" + "="*60)
        print(f"SCENARIO C: Token Replay Attack (Replaying token 5 times)")
        print(f"Token: {VALID_TOKEN[:20]}...")
        print("="*60)
        
        # First, simulate intercepting a valid token by making one legitimate request
        # (In reality, this token would be captured from a real user session)
        print("  [*] Intercepting valid token...")
        legitimate_payload = self.create_payload_with_token(VALID_TOKEN)
        first_result = await self.send_request(client, legitimate_payload, "C_Intercept")
        
        if first_result["status_code"] == 200:
            print(f"  ✓ Token appears valid (Status: {first_result['status_code']})")
        else:
            print(f"  ⚠ Token might be invalid (Status: {first_result['status_code']})")
        
        # Now replay the same token 5 times
        print("  [*] Replaying token 5 times...")
        replay_tasks = []
        for i in range(5):
            replay_payload = self.create_payload_with_token(VALID_TOKEN)
            replay_tasks.append(
                self.send_request(client, replay_payload, f"C_Replay_{i+1}")
            )
        
        replay_results = await asyncio.gather(*replay_tasks)
        
        # Combine results
        all_results = [first_result] + list(replay_results)
        self.results["scenario_c"].extend(all_results)
        
        # Count successes/failures for replay
        replay_successes = sum(1 for r in replay_results if r["status_code"] == 200)
        print(f"\n  🔄 Replay Results: {replay_successes}/5 requests succeeded")
        if replay_successes > 0:
            print("  ❌ WARNING: Replay attack partially succeeded!")
        else:
            print("  ✅ Replay attack successfully blocked!")
        
        return all_results

    async def run_all_scenarios(self):
        """Run all test scenarios with a shared HTTP client"""
        # Configure client for high-performance async requests
        limits = Limits(max_connections=MAX_CONNECTIONS, 
                       max_keepalive_connections=MAX_KEEPALIVE)
        timeout = Timeout(timeout=TIMEOUT_SECONDS)
        
        async with AsyncClient(
            limits=limits,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Stress-Testing)"}
        ) as client:
            # Run scenarios sequentially to measure independently
            await self.scenario_a_no_token(client, num_requests=10)
            await asyncio.sleep(1)  # Brief pause to prevent overlap
            
            await self.scenario_b_high_frequency(client)
            await asyncio.sleep(1)
            
            await self.scenario_c_replay_attack(client)

    def print_summary(self):
        """Print comprehensive test summary with statistics"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        for scenario_name, results in self.results.items():
            if not results:
                continue
                
            status_codes = [r["status_code"] for r in results]
            latencies = [r["latency_ms"] for r in results]
            success_count = sum(1 for r in results if r["success"])
            
            # Count status code distribution
            status_counts = {}
            for code in status_codes:
                status_counts[code] = status_counts.get(code, 0) + 1
            
            print(f"\n📊 {scenario_name.upper().replace('_', ' ')}:")
            print(f"  Total Requests: {len(results)}")
            print(f"  Successes (2xx): {success_count}")
            print(f"  Failures: {len(results) - success_count}")
            print(f"  Status Code Distribution: {status_counts}")
            print(f"  Latency - Min: {min(latencies):.2f}ms")
            print(f"            Max: {max(latencies):.2f}ms")
            print(f"            Avg: {statistics.mean(latencies):.2f}ms")
            if len(latencies) > 1:
                print(f"            Std Dev: {statistics.stdev(latencies):.2f}ms")

async def main():
    """Main entry point"""
    print("🚀 Protected API Stress-Testing Script")
    print(f"📍 Target: {API_URL}")
    print(f"⏱  Timeout: {TIMEOUT_SECONDS}s")
    print("📋 Scenarios:")
    print("  A. No Challenge Token (expect 403/400)")
    print("  B. High-Frequency Burst (expect 403)")
    print("  C. Token Replay (expect 403)")
    print("-"*60)
    
    tester = StressTester()
    start_time = time.time()
    
    try:
        await tester.run_all_scenarios()
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
    
    total_time = time.time() - start_time
    tester.print_summary()
    print(f"\n⏱  Total test duration: {total_time:.2f}s")
    print("✅ Testing complete!")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
