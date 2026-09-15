import asyncio
import json
import websockets
import httpx

async def test_websocket():
    uri = "ws://127.0.0.1:8000/ws/terminal"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket.")
            
            # Read initial messages
            msg = await websocket.recv()
            print(f"Server: {msg}")
            msg = await websocket.recv()
            print(f"Server: {msg}")

            # Send 'help'
            print("Sending 'help'...")
            await websocket.send("help")
            msg = await websocket.recv()
            print(f"Server: {msg}")

            # Send 'status'
            print("Sending 'status'...")
            await websocket.send("status")
            msg = await websocket.recv()
            print(f"Server: {msg}")

            # Send a fake bot attack to trigger broadcast
            print("Simulating bot attack...")
            async with httpx.AsyncClient() as client:
                # get token
                r = await client.get("http://127.0.0.1:8000/api/challenge")
                token = r.json()["token"]
                
                # send bot payload
                payload = {
                    "token": token,
                    "mouse_movements": [], # linear, empty will be flagged as bot
                    "keystrokes": [],
                    "clicks": [],
                    "scrolls": [],
                    "browser": {"userAgent": "bot"}
                }
                await client.post("http://127.0.0.1:8000/api/score", json=payload)

            # Wait for broadcast message
            print("Waiting for broadcast...")
            msg = await websocket.recv()
            print(f"Broadcast received: {msg}")
            
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
