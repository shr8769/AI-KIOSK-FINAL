import asyncio
import base64
import json
import websockets
import sqlite3
from datetime import datetime

async def test_audio_pipeline():
    session_id = "demo_session_id"
    db_path = "./data/kiosk.db"
    
    # 1. Seed session in SQLite
    # print(f"Seeding session {session_id} in {db_path}...")
    # conn = sqlite3.connect(db_path)
    # cursor = conn.cursor()
    # cursor.execute(
    #     "INSERT OR IGNORE INTO sessions (session_id, created_at, status, metadata) VALUES (?,?,?,?)",
    #     (session_id, datetime.utcnow().isoformat(), "active", "{}"),
    # )
    # conn.commit()
    # conn.close()

    url = f"ws://localhost:8000/ws/session/{session_id}"
    print(f"Connecting to {url}...")
    
    # 1-second silent WAV base64
    silent_wav_b64 = (
        "UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAAA"
    )
    
    try:
        async with websockets.connect(url) as ws:
            print("Connected successfully!")
            
            # Send audio_chunk
            message = {
                "type": "audio_chunk",
                "payload": {
                    "audio_base64": silent_wav_b64,
                    "language_hint": "en",
                    "turn_id": 1
                }
            }
            print("Sending audio_chunk...")
            await ws.send(json.dumps(message))
            
            # Read responses
            while True:
                try:
                    resp_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    resp = json.loads(resp_raw)
                    print("Received message:", resp)
                    if resp["type"] in ["answer", "error"]:
                        break
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_audio_pipeline())
