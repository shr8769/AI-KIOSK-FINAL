import asyncio
import sys

async def test_ws():
    try:
        import websockets
    except ImportError:
        print("websockets not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
        import websockets
        
    url = "ws://localhost:8000/ws/session/demo_session_id"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url) as ws:
            print("Connected successfully!")
            await ws.send('{"type": "ping"}')
            resp = await ws.recv()
            print("Received:", resp)
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
