import asyncio
import httpx

async def run_tests():
    base_url = "http://127.0.0.1:8000"
    
    async with httpx.AsyncClient(base_url=base_url) as client:
        print("=== Test 1: Rate Limiting on /api/challenge ===")
        success_count = 0
        ratelimit_count = 0
        
        # We configured 30 req/min. Let's send 35 requests.
        for i in range(35):
            r = await client.get("/api/challenge")
            if r.status_code == 200:
                success_count += 1
            elif r.status_code == 429:
                ratelimit_count += 1
            else:
                print(f"Unexpected status: {r.status_code}")
                
        print(f"Challenge requests - Success: {success_count}, Rate Limited: {ratelimit_count}")
        if ratelimit_count > 0:
            print("=> Rate limiting is working as expected (429 Too Many Requests).\n")
        else:
            print("=> ERROR: Rate limiting failed!\n")

        print("=== Test 2: IP Masking & Logs Auth ===")
        r3 = await client.get("/api/logs")
        print(f"GET /api/logs: {r3.status_code}")
        if r3.status_code == 200:
            data = r3.json()
            logs = data.get("logs", [])
            if logs:
                print(f"Sample IP from logs: {logs[0].get('ip')}")
                if "*" in logs[0].get('ip'):
                    print("=> IP Masking is working as expected (e.g. 192.168.1.*).")
                else:
                    print("=> ERROR: IP Masking is not applied.")
            else:
                print("=> No logs available to check IP masking. Please generate some traffic first.")
        else:
            print("=> ERROR: Could not fetch logs.")

if __name__ == "__main__":
    asyncio.run(run_tests())
