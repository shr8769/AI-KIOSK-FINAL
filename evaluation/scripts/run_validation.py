import json
import os
import sys

# Ensure parent directory is in search path if run directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agents.coordinator.coordinator_agent import CoordinatorAgent
from app.core.dependencies import get_riar_pipeline

def main():
    dataset_path = os.path.join(os.path.dirname(__file__), "..", "datasets", "validation_queries.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        queries = json.load(f)
        
    coordinator = CoordinatorAgent()
    pipeline = get_riar_pipeline()
    
    print("=" * 60)
    print("RETRIEVAL VALIDATION SCRIPT (40 QUERIES)")
    print("=" * 60)
    
    success_count = 0
    faq_mode_count = 0
    chroma_count = 0
    
    for i, item in enumerate(queries, 1):
        query = item["query"]
        qtype = item["type"]
        print(f"\n[{i}/40] Query: '{query}' (Type: {qtype})")
        
        try:
            # 1. Pipeline
            riar_result = pipeline.run(query=query, session_history=[], language="en")
            
            if riar_result.ambiguity_detected:
                print(f"-> Ambiguous (Clarification: {riar_result.clarification_question})")
                success_count += 1
                continue
                
            target_domain = riar_result.selected_domain
            print(f"-> Selected Domain: {target_domain}")
            
            # Get raw answer directly from agent to avoid translation prints clutter
            if target_domain and target_domain in coordinator.agents:
                agent = coordinator.agents[target_domain]
                # Try to capture print output from agent.retrieve()
                docs = agent.retrieve(query)
                if not docs:
                    print("-> Retrieval: No documents found.")
                else:
                    best_doc = docs[0]
                    source = best_doc.get("retrieval_source", "unknown")
                    print(f"-> Retrieval Source: {source} (Dist: {best_doc.get('distance', 0):.4f}, Score: {best_doc.get('combined_score', 0):.4f})")
                    if source == "chromadb":
                        chroma_count += 1
                    elif source == "faq_fallback":
                        faq_mode_count += 1
                        
            success_count += 1
            
        except Exception as e:
            print(f"-> Error: {e}")
            
    print("=" * 60)
    print(f"Total Processed: {success_count}/40")
    print(f"ChromaDB Retrievals: {chroma_count}")
    print(f"FAQ Fallback Retrievals: {faq_mode_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
