import os
import json
from typing import List, Dict, Any

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    pass

from agents.domain.base_agent import BaseAgent

class NavigationAgent(BaseAgent):
    """
    Agent handling location and navigation-related queries using ChromaDB.
    Unlike other domain agents, this agent returns STRICT JSON metadata
    about the location so the Coordinator can generate a QR session.
    """
    def __init__(self, client: Any = None, db_path: str = None):
        super().__init__(collection_name="navigation", client=client, db_path=db_path)

    def get_domain(self) -> str:
        return self.collection_name

    def answer(self, query: str, routing_confidence: float = 1.0) -> str:
        """
        Overrides the base RAG logic. We still do a vector search to find
        the exact location matching the user's query, but we instruct the LLM
        to output structured JSON parsing the metadata of the matched document.
        """
        if not self.collection:
            return json.dumps({"error": "Knowledge base not initialized"})
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=3
            )
            
            docs = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            
            if not docs:
                return json.dumps({"error": "Location not found in directory"})
                
            # Build context block
            context_blocks = []
            for d, m in zip(docs, metadatas):
                # The metadata has 'directions_json' and 'map_x', 'map_y' injected by ingest.py
                d_json = m.get("directions_json", "[]")
                block = (
                    f"Name: {m.get('name')}\n"
                    f"Building: {m.get('building')}\n"
                    f"Floor: {m.get('floor')}\n"
                    f"Room: {m.get('room')}\n"
                    f"Map X: {m.get('map_x')}\n"
                    f"Map Y: {m.get('map_y')}\n"
                    f"Directions JSON: {d_json}\n"
                    f"Document: {d}"
                )
                context_blocks.append(block)
                
            context = "\n\n---\n\n".join(context_blocks)
            
            prompt = f"""
You are the VidyaSahayak Navigation Agent.
The user is asking for directions. Identify the exact location they are looking for from the context below.

CONTEXT LOCATIONS:
{context}

USER QUERY: {query}

Based on the context, find the single best matching location.
Return ONLY a raw JSON object with the exact fields below. Do not use markdown blocks.

{{
  "destination_name": "Name of the location",
  "building": "Building Name",
  "floor": "Floor Level",
  "room": "Room Number",
  "map_coords": {{"x": 123, "y": 456}},
  "directions": ["Step 1", "Step 2"]
}}

If no matching location is found in the context, return exactly:
{{"error": "Location not found in directory"}}
"""
            # We use the BaseAgent's synthesizer to extract this JSON
            raw_text = ""
            if hasattr(self, "synthesizer"):
                if self.synthesizer.client:
                    response = self.synthesizer.client.models.generate_content(
                        model=self.synthesizer.model_name,
                        contents=prompt,
                    )
                    raw_text = response.text.strip() if response.text else ""
                elif self.synthesizer.ollama_client:
                    response = self.synthesizer.ollama_client.invoke(prompt)
                    raw_text = response.content.strip() if response and response.content else ""
            
            if not raw_text:
                return json.dumps({"error": "Failed to parse location with LLM."})
            
            # Clean up markdown if the LLM hallucinated codeblocks
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            return raw_text.strip()
            
        except Exception as e:
            return json.dumps({"error": f"Internal error: {str(e)}"})

if __name__ == "__main__":
    print("====================================")
    print("Navigation Agent Ready")
    print("Type 'exit' to quit")
    print("====================================")
    
    agent = NavigationAgent()
    
    while True:
        try:
            query = input("\nEnter your query:\n").strip()
            if query.lower() == "exit":
                break
            if not query:
                continue
                
            response = agent.answer(query)
            print(f"\nAnswer JSON:\n{response}")
        except (KeyboardInterrupt, EOFError):
            break
