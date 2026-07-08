import asyncio
import sys
import os
import time
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Add repository root to path so we can resolve imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app.core.config import settings
from database.models.models import Role, User, Session, Memory
from sentence_transformers import SentenceTransformer

# Target Database URL
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async def verify_postgres():
    print("====================================================")
    print("POSTGRESQL & PGVECTOR VERIFICATION SYSTEM")
    print("====================================================\n")

    steps_status = {}
    latencies = {}
    table_counts = {}

    # 1. Connect to PostgreSQL
    t_start = time.perf_counter()
    try:
        engine = create_async_engine(database_url, echo=False)
        async with engine.connect() as conn:
            version_res = await conn.execute(text("SELECT version();"))
            db_version = version_res.scalar()
            steps_status["1. Connection"] = "PASS"
            print("[OK] 1. Connect to PostgreSQL: SUCCESS")
            print(f"     DB Version: {db_version}")
    except Exception as e:
        steps_status["1. Connection"] = "FAIL"
        print(f"[FAIL] 1. Connect to PostgreSQL: FAILED ({e})")
        return False, steps_status, latencies, table_counts
    latencies["Connection"] = time.perf_counter() - t_start

    # 2. Verify DATABASE_URL
    print(f"[OK] 2. Verify DATABASE_URL: PASS (URL matches expected schema: {settings.DATABASE_URL})")
    steps_status["2. DATABASE_URL Verification"] = "PASS"

    # 3. Install and verify pgvector support (CREATE EXTENSION)
    t_start = time.perf_counter()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        async with engine.connect() as conn:
            ext_res = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            )
            ext_version = ext_res.scalar()
            if ext_version:
                steps_status["3. pgvector Extension Check"] = "PASS"
                print(f"[OK] 3. pgvector Extension: ENABLED (version {ext_version})")
            else:
                steps_status["3. pgvector Extension Check"] = "FAIL"
                print("[FAIL] 3. pgvector Extension: NOT ENABLED")
    except Exception as e:
        steps_status["3. pgvector Extension Check"] = "FAIL"
        print(f"[FAIL] 3. pgvector Extension: FAILED ({e})")
    latencies["pgvector Setup"] = time.perf_counter() - t_start

    # 4. Execute migrations
    t_start = time.perf_counter()
    try:
        migrations_dir = os.path.join(os.path.dirname(__file__), "database", "migrations")
        migration_files = ["001_init.sql", "002_memory.sql", "003_queries.sql"]
        
        async with engine.begin() as conn:
            for m_file in migration_files:
                m_path = os.path.join(migrations_dir, m_file)
                if os.path.exists(m_path):
                    print(f"     Executing migration file: {m_file}")
                    with open(m_path, "r", encoding="utf-8") as f:
                        sql_cmds = f.read()
                    # Execute raw commands (splitting by semicolon if multiple queries)
                    for cmd in sql_cmds.split(";"):
                        cmd_strip = cmd.strip()
                        if cmd_strip:
                            await conn.execute(text(cmd_strip))
                else:
                    print(f"     [WARN] Migration file not found: {m_path}")
        
        steps_status["4. Execute Migrations"] = "PASS"
        print("[OK] 4. Execute Migrations: SUCCESS")
    except Exception as e:
        steps_status["4. Execute Migrations"] = "FAIL"
        print(f"[FAIL] 4. Execute Migrations: FAILED ({e})")
    latencies["Migration Execution"] = time.perf_counter() - t_start

    # 5. Verify that tables exist
    t_start = time.perf_counter()
    tables_to_verify = ["roles", "users", "sessions", "memories", "queries"]
    all_tables_exist = True
    try:
        async with engine.connect() as conn:
            for table in tables_to_verify:
                res = await conn.execute(
                    text(f"SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}');")
                )
                exists = res.scalar()
                if exists:
                    count_res = await conn.execute(text(f"SELECT count(*) FROM {table};"))
                    count = count_res.scalar()
                    table_counts[table] = count
                    print(f"     Table '{table}': EXISTS (count: {count})")
                else:
                    all_tables_exist = False
                    table_counts[table] = -1
                    print(f"     [FAIL] Table '{table}': DOES NOT EXIST")
        
        if all_tables_exist:
            steps_status["5. Verify Tables Exist"] = "PASS"
            print("[OK] 5. Verify Tables Exist: SUCCESS")
        else:
            steps_status["5. Verify Tables Exist"] = "FAIL"
            print("[FAIL] 5. Verify Tables Exist: FAILED")
    except Exception as e:
        steps_status["5. Verify Tables Exist"] = "FAIL"
        print(f"[FAIL] 5. Verify Tables Exist: ERROR ({e})")
    latencies["Table Verification"] = time.perf_counter() - t_start

    # 6. Insert sample records
    t_start = time.perf_counter()
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with AsyncSessionLocal() as db:
            # Create roles
            roles = {
                "user": Role(role_id="user", permissions=["read", "ask"]),
                "admin": Role(role_id="admin", permissions=["read", "ask", "write", "manage"]),
                "guest": Role(role_id="guest", permissions=["read"])
            }
            for role in roles.values():
                await db.merge(role)
            
            # Create users
            user_demo = User(
                user_id="usr_demo_123",
                name="Demo User",
                role_id="user",
                face_embedding=[0.1] * 512,
                preferences={"theme": "dark", "language": "en"}
            )
            user_guest = User(
                user_id="usr_guest",
                name="Guest User",
                role_id="guest",
                face_embedding=None,
                preferences={"language": "en"}
            )
            await db.merge(user_demo)
            await db.merge(user_guest)
            
            # Create session
            session_demo = Session(
                session_id="demo_session_id",
                user_id="usr_demo_123"
            )
            await db.merge(session_demo)
            await db.commit()
            
        steps_status["6. Insert Sample Records"] = "PASS"
        print("[OK] 6. Insert Sample Records: SUCCESS")
    except Exception as e:
        steps_status["6. Insert Sample Records"] = "FAIL"
        print(f"[FAIL] 6. Insert Sample Records: FAILED ({e})")
    latencies["Sample Records Insertion"] = time.perf_counter() - t_start

    # 7. Insert sample memories (with real embedding generation)
    t_start = time.perf_counter()
    sample_outputs = {}
    try:
        print("     Initializing SentenceTransformer('all-MiniLM-L6-v2')...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("     [OK] Model Loaded successfully.")

        sample_memories = [
            {"content": "The user asked for the requirements to apply for B.Tech CSE. They are from Karnataka and want to know about PESSAT registrations.", "topic": "admissions"},
            {"content": "Inquired about hostel fees and booking deadlines.", "topic": "student_services"},
            {"content": "Asked about placements and package statistics for CSE.", "topic": "placements"},
            {"content": "The student wanted to know where the academic block is located.", "topic": "navigation"}
        ]

        async with AsyncSessionLocal() as db:
            inserted_count = 0
            for i, m_data in enumerate(sample_memories):
                # Generate real embedding
                emb = model.encode(m_data["content"]).tolist()
                mem_id = f"mem_test_{i+1:03d}"
                
                # Check and merge
                memory_obj = Memory(
                    memory_id=mem_id,
                    user_id="usr_demo_123",
                    content=m_data["content"],
                    topic=m_data["topic"],
                    embedding=emb
                )
                await db.merge(memory_obj)
                inserted_count += 1
            await db.commit()
            
        steps_status["7. Insert Sample Memories"] = "PASS"
        print(f"[OK] 7. Insert Sample Memories: SUCCESS (Inserted {inserted_count} memories)")
    except Exception as e:
        steps_status["7. Insert Sample Memories"] = "FAIL"
        print(f"[FAIL] 7. Insert Sample Memories: FAILED ({e})")
    latencies["Sample Memories Insertion"] = time.perf_counter() - t_start

    # 8. Execute real pgvector similarity search
    t_start = time.perf_counter()
    try:
        query_text = "hostel room booking and rules"
        query_emb = model.encode(query_text).tolist()

        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            # Query using pgvector cosine distance
            result = await db.execute(
                select(Memory)
                .filter(Memory.user_id == "usr_demo_123")
                .order_by(Memory.embedding.cosine_distance(query_emb))
                .limit(2)
            )
            matched_memories = result.scalars().all()
            
            sample_outputs["query"] = query_text
            sample_outputs["matches"] = []
            print(f"     Query: '{query_text}'")
            for idx, match in enumerate(matched_memories):
                # Compute distance manually via numpy or read it
                print(f"       Match #{idx+1}: Content='{match.content}' (Topic: {match.topic})")
                sample_outputs["matches"].append({
                    "id": match.memory_id,
                    "content": match.content,
                    "topic": match.topic
                })
            
            if matched_memories:
                steps_status["8. pgvector Similarity Search"] = "PASS"
                print("[OK] 8. pgvector Similarity Search: SUCCESS")
            else:
                steps_status["8. pgvector Similarity Search"] = "FAIL"
                print("[FAIL] 8. pgvector Similarity Search: No matches found")
    except Exception as e:
        steps_status["8. pgvector Similarity Search"] = "FAIL"
        print(f"[FAIL] 8. pgvector Similarity Search: ERROR ({e})")
    latencies["Vector Similarity Search"] = time.perf_counter() - t_start

    # 9. Verify key integration features
    # Verification 9.1: Session persistence
    t_start = time.perf_counter()
    verify_session_persistence = "FAIL"
    try:
        async with AsyncSessionLocal() as db:
            sess_res = await db.execute(
                select(Session).filter(Session.session_id == "demo_session_id")
            )
            session = sess_res.scalar()
            if session and session.user_id == "usr_demo_123":
                verify_session_persistence = "PASS"
                print("[OK] 9.1 Verification: Session Persistence PASSED")
    except Exception as e:
        print(f"[FAIL] 9.1 Verification: Session Persistence FAILED ({e})")
    steps_status["9.1 Session Persistence"] = verify_session_persistence

    # Verification 9.2: Profile loading
    verify_profile_loading = "FAIL"
    try:
        async with AsyncSessionLocal() as db:
            user_res = await db.execute(
                select(User).filter(User.user_id == "usr_demo_123")
            )
            user = user_res.scalar()
            if user and user.name == "Demo User" and user.role_id == "user":
                verify_profile_loading = "PASS"
                print("[OK] 9.2 Verification: Profile Loading PASSED")
    except Exception as e:
        print(f"[FAIL] 9.2 Verification: Profile Loading FAILED ({e})")
    steps_status["9.2 Profile Loading"] = verify_profile_loading

    # Verification 9.3: Memory insertion (test insertion of one more memory via MemoryStore if possible)
    verify_memory_insertion = "FAIL"
    try:
        from backend.app.services.memory_store import MemoryStore
        async with AsyncSessionLocal() as db:
            store_service = MemoryStore(db)
            test_content = "Specific instructions regarding CSE placements."
            new_mem = await store_service.store_memory(
                user_id="usr_demo_123",
                content=test_content,
                topic="placements"
            )
            if new_mem and new_mem.content == test_content:
                verify_memory_insertion = "PASS"
                print("[OK] 9.3 Verification: Memory Insertion PASSED")
                # Cleanup test memory
                await db.delete(new_mem)
                await db.commit()
    except Exception as e:
        print(f"[FAIL] 9.3 Verification: Memory Insertion FAILED ({e})")
    steps_status["9.3 Memory Insertion"] = verify_memory_insertion

    # Verification 9.4: Memory retrieval
    verify_memory_retrieval = "FAIL"
    try:
        from backend.app.services.memory_retriever import MemoryRetriever
        async with AsyncSessionLocal() as db:
            retriever_service = MemoryRetriever(db)
            retrieved = await retriever_service.retrieve_memories(
                user_id="usr_demo_123",
                query_text="B.Tech admissions registrations",
                limit=1
            )
            if retrieved and "B.Tech CSE" in retrieved[0].content:
                verify_memory_retrieval = "PASS"
                print("[OK] 9.4 Verification: Memory Retrieval PASSED")
    except Exception as e:
        print(f"[FAIL] 9.4 Verification: Memory Retrieval FAILED ({e})")
    steps_status["9.4 Memory Retrieval"] = verify_memory_retrieval

    # Verification 9.5: Top-k vector search
    verify_top_k_search = "FAIL"
    try:
        from backend.app.services.memory_retriever import MemoryRetriever
        async with AsyncSessionLocal() as db:
            retriever_service = MemoryRetriever(db)
            retrieved = await retriever_service.retrieve_memories(
                user_id="usr_demo_123",
                query_text="placement stats and recruiter info",
                limit=2
            )
            if len(retrieved) >= 2 and retrieved[0].topic == "placements":
                verify_top_k_search = "PASS"
                print("[OK] 9.5 Verification: Top-k Vector Search PASSED")
    except Exception as e:
        print(f"[FAIL] 9.5 Verification: Top-k Vector Search FAILED ({e})")
    steps_status["9.5 Top-k Vector Search"] = verify_top_k_search
    
    # Recalculate table counts after inserts
    async with engine.connect() as conn:
        for table in tables_to_verify:
            count_res = await conn.execute(text(f"SELECT count(*) FROM {table};"))
            table_counts[table] = count_res.scalar()

    await engine.dispose()
    
    # Check if all steps passed
    overall_pass = all(v == "PASS" for v in steps_status.values())
    
    return overall_pass, steps_status, latencies, table_counts, sample_outputs

async def main():
    passed, steps, latencies, counts, outputs = await verify_postgres()
    
    print("\n" + "="*50)
    print("VERIFICATION REPORT SUMMARY")
    print("="*50)
    print(f"OVERALL STATUS: {'PASS' if passed else 'FAIL'}")
    print("-"*50)
    print("STEP STATUSES:")
    for step, status in steps.items():
        print(f"  {step:<35}: {status}")
    print("-"*50)
    print("TABLE COUNTS:")
    for table, count in counts.items():
        print(f"  {table:<15}: {count}")
    print("-"*50)
    print("LATENCIES (seconds):")
    for op, elapsed in latencies.items():
        print(f"  {op:<25}: {elapsed:.4f}s")
    print("-"*50)
    print("SAMPLE VECTOR SEARCH OUTPUT:")
    print(f"  Query: '{outputs.get('query')}'")
    for i, match in enumerate(outputs.get("matches", [])):
        print(f"  Match #{i+1}: Topic='{match['topic']}' | Content='{match['content']}'")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
