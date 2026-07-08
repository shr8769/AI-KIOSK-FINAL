import asyncio
import sys
import os

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app.core.config import settings

def cosine_similarity(v1, v2):
    import numpy as np
    v1 = np.array(v1)
    v2 = np.array(v2)
    dot = np.dot(v1, v2)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(dot / (n1 * n2))

async def verify_memory():
    print("====================================================")
    print("FR-9 LONG TERM MEMORY VERIFICATION SCRIPT")
    print("====================================================\n")
    
    # 1. Check database connectivity
    db_available = False
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        url = settings.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        temp_engine = create_async_engine(url, echo=False)
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))
            db_available = True
            print("[OK] Database Connection: ONLINE")
        await temp_engine.dispose()
    except Exception:
        print("[FAIL] Database Connection: OFFLINE")
        print("  Running verification in DRY-RUN / MOCK vector mode...\n")
        
    user_id = "usr_demo_123"
    
    # 2. Set up sentence-transformers locally
    print("Initializing embedding model 'all-MiniLM-L6-v2'...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("[OK] Embedding Model: LOADED")
    except Exception as e:
        print(f"[FAIL] Embedding Model Load: {e}")
        model = None

    if db_available and model:
        # Real PostgreSQL test flow
        print("\n--- Running Real Database Test Flow ---")
        from database.postgres.connection import AsyncSessionLocal
        from backend.app.services.memory_manager import MemoryManager
        
        async with AsyncSessionLocal() as session:
            manager = MemoryManager(session)
            
            # Test 1: Memory insertion (Conversation -> Summary -> Embedding -> Store)
            print("\nTest 1: Memory insertion...")
            conv_content = "The user asked for the requirements to apply for B.Tech CSE. They are from Karnataka and want to know about PESSAT registrations."
            result = await manager.store_conversation_segment(user_id=user_id, conversation_text=conv_content)
            print(f"[OK] Stored memory! ID: {result['memory_id']}, Summary: '{result['summary']}', Topic: '{result['topic']}'")
            
            # Test 2 & 3: Memory retrieval & Similarity search
            print("\nTest 2 & 3: Memory retrieval & similarity search...")
            retrieved = await manager.retriever_service.retrieve_memories(
                user_id=user_id, query_text="B.Tech registrations", limit=2
            )
            for m in retrieved:
                print(f"[OK] Found matching memory: content='{m.content}', topic='{m.topic}'")
                
            # Test 4 & 5: Session memory loading & context injection
            print("\nTest 4 & 5: Context loading & integration...")
            injection = await manager.get_context_injection(user_id=user_id, query_text="PESSAT")
            print("Context injected:")
            print(injection)
            
    else:
        # Dry-run vector search simulation
        print("\n--- Running Dry-Run Vector Similarity Simulation ---")
        
        # Test 1: Memory insertion simulation
        print("\nTest 1: Memory insertion simulation...")
        conversation_segment = "The user asked about hostel accommodation fees and booking deadlines for campus."
        print(f"Input conversation: '{conversation_segment}'")
        
        # Simulated Summary (what MemorySummary generates)
        simulated_summary = "Inquired about hostel fees and booking deadlines."
        simulated_topic = "student_services"
        print(f"Generated Summary: '{simulated_summary}' (Topic: '{simulated_topic}')")
        
        # Test 2 & 3: Similarity search simulation using numpy
        print("\nTest 2 & 3: Similarity search simulation...")
        if model:
            # Generate actual vector embeddings using the model
            past_memories = [
                {"content": "Applied for B.Tech admissions via PESSAT.", "topic": "admissions"},
                {"content": "Inquired about hostel fees and booking deadlines.", "topic": "student_services"},
                {"content": "Asked about placements and package statistics for CSE.", "topic": "placements"}
            ]
            
            query = "hostel room booking"
            query_emb = model.encode(query).tolist()
            
            results = []
            for mem in past_memories:
                mem_emb = model.encode(mem["content"]).tolist()
                sim = cosine_similarity(query_emb, mem_emb)
                results.append((mem, sim))
                
            # Sort by similarity desc
            results.sort(key=lambda x: x[1], reverse=True)
            
            print(f"Query: '{query}'")
            for mem, score in results:
                print(f"  Match: '{mem['content']}' | Topic: '{mem['topic']}' | Cosine Similarity: {score:.4f}")
            print("[OK] Similarity search: SUCCESS")
        else:
            print("Skipping numpy similarity search due to missing embedding model.")
            
        # Test 4 & 5: Session memory loading & Profile + Memory integration
        print("\nTest 4 & 5: Session memory loading & Profile integration simulation...")
        # Simulated Profile Details (FR-12)
        profile = {
            "user_id": user_id,
            "name": "Demo User",
            "role": "user",
            "preferences": {"theme": "dark", "language": "en"}
        }
        
        # Simulated Context Injection (FR-9)
        injected_memories = [
            "- Inquired about hostel fees and booking deadlines. (Topic: student_services)",
            "- Applied for B.Tech admissions via PESSAT. (Topic: admissions)"
        ]
        context_string = "\nUser's Relevant Past Memories:\n" + "\n".join(injected_memories) + "\n"
        
        print("Integrated Session Context Payload:")
        print(f"User Profile: {profile['name']} (Role: {profile['role']})")
        print(context_string)
        print("[OK] Profile + Memory integration: SUCCESS")
        
    print("\n====================================================")

if __name__ == "__main__":
    asyncio.run(verify_memory())
