import asyncio
import os
from riar.pipeline import RIARPipeline
from langchain_community.chat_models import ChatOllama
import chromadb
from chromadb.utils import embedding_functions

async def test_routing():
    print("Initializing components...")
    db_path = os.path.join("knowledge", "vectorstore")
    client = chromadb.PersistentClient(path=db_path)
    
    class MockEncoder:
        def encode(self, texts):
            # Return dummy embeddings (1 per text)
            return [[0.1] * 384 for _ in texts]
            
    emb_mock = MockEncoder()
    
    llm = ChatOllama(model="qwen3:latest", temperature=0)
    
    pipeline = RIARPipeline(
        vector_store=client,
        llm_client=llm,
        embedding_model=emb_mock
    )
    
    queries = [
        "What is the Microsoft eligibility criteria?", # Used to hit Admissions AND Placements
        "Tell me about the criteria", # Highly ambiguous
        "Where is the health center?" # Clear navigation
    ]
    
    for query in queries:
        print(f"\n--- Testing Query: '{query}' ---")
        result = pipeline.run(query=query, session_history=[])
        
        print(f"Ambiguous? {result.ambiguity_detected}")
        if result.ambiguity_detected:
            print(f"Type: {result.ambiguity_type}")
            print(f"Clarification Q: {result.clarification_question}")
        else:
            print(f"Selected Domain: {result.selected_domain}")

if __name__ == "__main__":
    asyncio.run(test_routing())
