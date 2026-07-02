import asyncio
import json
import uuid
import websockets
import httpx

async def test_websocket():
    # 1. Create Session
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:8000/api/v1/events", json={
            "event_type": "PERSON_DETECTED",
            "camera_id": "cam_01",
            "payload": {"confidence": 0.99}
        })
        if resp.status_code != 200:
            print(f"Failed to create session: {resp.status_code} {resp.text}")
            return
        session_id = resp.json()["session_id"]
    uri = f"ws://localhost:8000/ws/session/{session_id}"
    
    async with websockets.connect(uri, origin="http://localhost:3000") as ws:
        async def listen():
            while True:
                try:
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                    msg_type = resp.get("type")
                    if msg_type == "thinking" or msg_type == "transcript" or msg_type == "retrieving" or msg_type == "greeting":
                        pass
                    else:
                        print(f"\nServer: {msg_type}")
                        if "payload" in resp:
                            print(json.dumps(resp["payload"], indent=2))
                except TimeoutError:
                    pass
                except Exception as e:
                    print(f"Listen error: {e}")
                    break

        # Start listening task
        listener = asyncio.create_task(listen())

        print("\n--- TEST 1: Direct English ---")
        await ws.send(json.dumps({
            "type": "text_query",
            "payload": {"text": "where is the physics lab", "language_hint": "en", "turn_id": 1}
        }))
        await asyncio.sleep(2)
        
        print("\n--- TEST 2: Hindi Query ---")
        await ws.send(json.dumps({
            "type": "text_query",
            "payload": {"text": "physics lab kahan hai", "language_hint": "hi", "turn_id": 2}
        }))
        await asyncio.sleep(2)
        
        print("\n--- TEST 3: Ambiguous/Nonsense ---")
        await ws.send(json.dumps({
            "type": "text_query",
            "payload": {"text": "where is the thing", "language_hint": "en", "turn_id": 3}
        }))
        await asyncio.sleep(60)
        
        listener.cancel()

if __name__ == "__main__":
    asyncio.run(test_websocket())
