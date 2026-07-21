#!/usr/bin/env python3
"""
verify_pipeline.py

Verifies the complete end-to-end flow:
User Query -> Coordinator Agent -> Domain Agent -> ChromaDB Retrieval -> LLM Prompt -> Final Response.
For each step, demonstrates that the newly ingested Markdown chunks are being retrieved instead of the old synthetic FAQ entries.
"""

import os
import sys

# Monkeypatch QwenClient to bypass warmup check timeouts during initialization
from agents.llm.qwen_client import QwenClient
QwenClient.is_ollama_available = lambda self: False

from agents.coordinator.coordinator_agent import CoordinatorAgent

def verify_query(coordinator: CoordinatorAgent, query: str):
    print("\n" + "="*80)
    print(f"USER QUERY: '{query}'")
    print("="*80)
    
    # 1. Route the query
    domain, confidence, reason, matches = coordinator.route(query)
    
    print(f"1. Coordinator Routing Decision:")
    print(f"   - Selected Domain: {domain}")
    print(f"   - Confidence Score: {confidence:.4f}")
    print(f"   - Routing Reason: {reason}")
    print(f"   - Matched Keywords: {matches}")
    
    if not domain:
        print("   - No suitable domain agent found for this query.")
        return
        
    agent = coordinator.agents[domain]
    print(f"\n2. Domain Agent & ChromaDB Investigation:")
    print(f"   - Selected Agent: {agent.__class__.__name__}")
    print(f"   - Collection Queried: '{agent.collection_name}'")
    
    # 2. Retrieve candidates from ChromaDB
    try:
        candidates = agent.retrieve(query)
        print(f"   - Chunks Retrieved: {len(candidates)}")
        
        for idx, doc in enumerate(candidates, 1):
            meta = doc.get("metadata", {})
            distance = doc.get("distance", 0.0)
            sim_score = 1.0 / (1.0 + distance)
            
            # Print chunk details to verify it is the newly ingested markdown
            print(f"     [Candidate #{idx}]")
            print(f"       * Chunk ID: {doc.get('id')}")
            print(f"       * Document: {meta.get('document_name')}")
            print(f"       * Title: {meta.get('title')}")
            print(f"       * Heading: {meta.get('heading')}")
            print(f"       * Source URL: {meta.get('source_url')}")
            print(f"       * Similarity Score: {sim_score:.4f} (Distance: {distance:.4f})")
            print(f"       * Chunk Index: {meta.get('chunk_number')} of {meta.get('total_chunks')}")
            # Snippet of retrieved text
            content_snippet = doc.get("document", "").replace("\n", " ").strip()[:150]
            print(f"       * Snippet: \"{content_snippet}...\"")
            
    except Exception as e:
        print(f"   - Error during retrieval: {e}")
        
    # 3. Get final agent answer
    print(f"\n3. RAG/LLM Final Response:")
    try:
        response = agent.answer(query)
        print(f"\n{response}")
    except Exception as e:
        print(f"   - Error during answer generation: {e}")
    print("="*80)

def main():
    print("Initializing Coordinator Agent and Persistent ChromaDB client...")
    
    # Point to the active production database under knowledge/vectorstore
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "knowledge", "vectorstore"))
    coordinator = CoordinatorAgent(db_path=db_path)
    
    # Standard query list
    queries = [
        "What are the admission fee structures for B.Tech?",
        "When is the academic calendar schedule and exam timetable posted?",
        "What placements and internship recruiters visit the campus?"
    ]
    for q in queries:
        verify_query(coordinator, q)
        
    # Multi-turn Follow-up Sequence Test
    print("\n" + "="*80)
    print("RUNNING MULTI-TURN FOLLOW-UP SEQUENCE TEST")
    print("="*80)
    verify_query(coordinator, "What are the hostel accommodations?")
    # Follow-up query under same session_id should reformulate
    print("\n--- Next turn with history context ---")
    session_id = "session_multi"
    coordinator.conversations[session_id] = [{"query": "What are the hostel accommodations?", "response": "We have boys and girls hostel rooms."}]
    # Run query through coordinator.answer directly to show reformulation + response
    response_followup = coordinator.answer("What about for girls?", session_id=session_id)
    print(f"Reformulated response:\n{response_followup}")
    
    # Ambiguity Resolution Test
    print("\n" + "="*80)
    print("RUNNING AMBIGUITY RESOLUTION TEST")
    print("="*80)
    res_fee = coordinator.answer("fee")
    res_cutoff = coordinator.answer("cutoff")
    
    # Low Confidence / Contact Fallback Test
    print("\n" + "="*80)
    print("RUNNING CONTACT FALLBACK TEST")
    print("="*80)
    res_fallback = coordinator.answer("who is the chief chef at boys mess?")

if __name__ == "__main__":
    main()
