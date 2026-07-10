import asyncio
import sys
import os
import time
import uuid
from sqlalchemy import text
from sqlalchemy.future import select

# Add repository root and backend to path
repo_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "backend"))

from backend.app.core.config import settings
from backend.app.main import app
from fastapi.testclient import TestClient
from database.postgres.connection import create_async_engine, async_sessionmaker, AsyncSession
from database.models.models import User, Session, Memory

# Target Database URL
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async def cleanup_test_data(engine):
    """Ensure test runs are completely fresh and repeatable."""
    async with engine.begin() as conn:
        print("Cleaning up existing test data for 'usr_runtime_999'...")
        await conn.execute(text("DELETE FROM memories WHERE user_id = 'usr_runtime_999';"))
        await conn.execute(text("DELETE FROM sessions WHERE user_id = 'usr_runtime_999';"))
        await conn.execute(text("DELETE FROM users WHERE user_id = 'usr_runtime_999';"))
    print("[OK] Cleanup completed.")

async def verify_runtime():
    print("====================================================")
    print("FR-9 LONG-TERM MEMORY RUNTIME AUTOMATION TEST")
    print("====================================================\n")

    steps_status = {}
    latencies = {}

    # 1. Database Connection and Cleanup
    t_start = time.perf_counter()
    try:
        engine = create_async_engine(database_url, echo=False)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))
            print("[OK] 1. Connect to PostgreSQL: SUCCESS")
            steps_status["1. DB Connection"] = "PASS"
    except Exception as e:
        print(f"[FAIL] 1. Connect to PostgreSQL: FAILED ({e})")
        return
    latencies["DB Connection"] = time.perf_counter() - t_start

    await cleanup_test_data(engine)

    import httpx
    # Instantiate AsyncClient
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        user_id = "usr_runtime_999"
        user_name = "Automated Runtime User"

        # 2. Test Auto User and Session Creation on Detection
        t_start = time.perf_counter()
        session_id = None
        try:
            response = await client.post("/api/v1/detect", json={
                "camera_id": "cam_front_01",
                "confidence": 0.98,
                "bounding_box": {"x": 12, "y": 34, "w": 56, "h": 78},
                "user_id": user_id,
                "name": user_name
            })
            assert response.status_code == 200
            res_data = response.json()
            session_id = res_data["session_id"]
            greeting = res_data["greeting_text"]
            print(f"[OK] 2. POST /detect (New User) resolved:")
            print(f"     Session ID: {session_id}")
            print(f"     Greeting  : \"{greeting}\"")
            
            # Verify DB insertions
            AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
            async with AsyncSessionLocal() as db:
                user_res = await db.execute(select(User).filter(User.user_id == user_id))
                db_user = user_res.scalar()
                sess_res = await db.execute(select(Session).filter(Session.session_id == session_id))
                db_sess = sess_res.scalar()
                
                assert db_user is not None, "User row was not automatically created."
                assert db_sess is not None, "Session row was not automatically created."
                assert db_user.name == user_name, "User name is incorrect."
                
                print(f"     [DB VERIFY] User '{db_user.name}' and Session '{db_sess.session_id}' exist in DB.")
                steps_status["2. Auto-create User & Session"] = "PASS"
        except Exception as e:
            steps_status["2. Auto-create User & Session"] = "FAIL"
            print(f"[FAIL] 2. Auto-create User & Session: {e}")
            await engine.dispose()
            return
        latencies["Auto-creation & Load"] = time.perf_counter() - t_start

        # 3. Simulate Conversation turns (5 turns to trigger automatic memory creation)
        print("\nSimulating 5 conversation turns to trigger auto-summarization...")
        t_start = time.perf_counter()
        queries = [
            "What are the admissions criteria for B.Tech CSE?",
            "When is the application registration deadline for PESSAT?",
            "Can you tell me about the tuition fees for B.Tech?",
            "Where is the admissions office block located?",
            "How can I book a hostel room on campus?"
        ]
        try:
            for idx, q in enumerate(queries):
                print(f"     Turn #{idx+1} Query: \"{q}\"")
                resp = await client.post("/api/v1/rag", json={
                    "session_id": session_id,
                    "query": q,
                    "domain": "admissions",
                    "language": "en"
                })
                assert resp.status_code == 200
                
            # Verify memories table contains the auto-summarized turn
            async with AsyncSessionLocal() as db:
                mem_res = await db.execute(select(Memory).filter(Memory.user_id == user_id))
                memories = mem_res.scalars().all()
                
                # Assert memory exists
                assert len(memories) >= 1, "Memory was not automatically created after 5 turns."
                print(f"[OK] 3. Auto Memory Storage: SUCCESS")
                print(f"     Memory Saved ID: {memories[0].memory_id}")
                print(f"     Memory Content : \"{memories[0].content}\"")
                print(f"     Memory Topic   : \"{memories[0].topic}\"")
                steps_status["3. Auto Summarize & Store Memory"] = "PASS"
        except Exception as e:
            steps_status["3. Auto Summarize & Store Memory"] = "FAIL"
            import traceback
            traceback.print_exc()
            print(f"[FAIL] 3. Auto Summarize & Store Memory: {e}")
            await engine.dispose()
            return
        latencies["5-Turn Dialog & Memory Archive"] = time.perf_counter() - t_start

        # 4. Verify context injection on new session
        print("\nSimulating a new session detection to verify past memory injection...")
        t_start = time.perf_counter()
        try:
            # Call /detect again with the same user ID to trigger loading of past memories
            response2 = await client.post("/api/v1/detect", json={
                "camera_id": "cam_front_01",
                "confidence": 0.99,
                "bounding_box": {},
                "user_id": user_id,
                "name": user_name
            })
            assert response2.status_code == 200
            res2_data = response2.json()
            new_greeting = res2_data["greeting_text"]
            print(f"[OK] 4. Greeting context injection resolved:")
            print(f"     New Session ID: {res2_data['session_id']}")
            print(f"     New Greeting  : \"{new_greeting}\"")
            assert "Loaded Context:" in new_greeting or "past memories" in new_greeting.lower(), "Past memories context was not injected into greeting."
            steps_status["4. Greeting Memory Injection"] = "PASS"
        except Exception as e:
            steps_status["4. Greeting Memory Injection"] = "FAIL"
            print(f"[FAIL] 4. Greeting Memory Injection: {e}")
        latencies["Greeting Context Injection"] = time.perf_counter() - t_start

        # 5. Verify pgvector top-k similarity retrieval
        print("\nExecuting similarity retrieval check...")
        t_start = time.perf_counter()
        try:
            # Query matching "hostel booking room rules"
            search_resp = await client.get(f"/api/v1/memory/{user_id}", params={
                "query": "hostel room booking and rules",
                "limit": 2
            })
            assert search_resp.status_code == 200
            matches = search_resp.json()
            print(f"[OK] 5. pgvector Similarity Search resolved:")
            for idx, match in enumerate(matches):
                print(f"     Match #{idx+1}: Content=\"{match['content']}\" (Topic: {match['topic']})")
            assert len(matches) > 0, "No similarity search matches returned."
            steps_status["5. pgvector Similarity Retrieval"] = "PASS"
        except Exception as e:
            steps_status["5. pgvector Similarity Retrieval"] = "FAIL"
            print(f"[FAIL] 5. pgvector Similarity Retrieval: {e}")
        latencies["pgvector Similarity Search"] = time.perf_counter() - t_start

    # Clean up test user data again
    await cleanup_test_data(engine)
    await engine.dispose()

    # Summarize report
    overall_pass = all(v == "PASS" for v in steps_status.values())
    print("\n" + "="*50)
    print("RUNTIME VERIFICATION SUMMARY")
    print("="*50)
    print(f"OVERALL STATUS: {'PASS' if overall_pass else 'FAIL'}")
    print("-"*50)
    for step, status in steps_status.items():
        print(f"  {step:<35}: {status}")
    print("-"*50)
    print("LATENCIES:")
    for op, elapsed in latencies.items():
        print(f"  {op:<30}: {elapsed:.4f}s")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(verify_runtime())
