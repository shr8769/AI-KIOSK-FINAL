import os
import json
from typing import List, Dict, Any

class NavigationAgent:
    """
    Agent handling location and navigation-related queries using Deterministic Alias Matching.
    Unlike other domain agents, this agent returns STRICT JSON metadata
    about the location so the Coordinator can generate a QR session.
    """
    def __init__(self, client: Any = None, db_path: str = None):
        self.collection_name = "navigation"
        self.locations = []
        knowledge_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge"))
        loc_file = os.path.join(knowledge_dir, "sources", "navigation", "navigation_locations.json")
        try:
            with open(loc_file, "r", encoding="utf-8") as f:
                self.locations = json.load(f)
        except Exception as e:
            print(f"[Warning] Could not load navigation locations: {e}")

    def get_domain(self) -> str:
        return self.collection_name

    def retrieve(self, query: str) -> list:
        """
        Retrieves matching location metadata structured similarly to base agent retrieval.
        Allows coordinator to route dynamic query matches to the navigation agent.
        """
        query_lower = query.lower()
        best_match = None
        for loc in self.locations:
            for alias in loc.get("aliases", []):
                if alias.lower() in query_lower:
                    best_match = loc
                    break
            if best_match:
                break
                
        if best_match:
            name = best_match.get("name", "Unknown")
            building = best_match.get("building", "Unknown")
            floor = str(best_match.get("floor", "0"))
            room = best_match.get("room", "Unknown")
            return [{
                "id": f"navigation_{name.lower().replace(' ', '_')}",
                "document": f"Topic: Navigation\nQuestion: Where is {name}?\nAnswer: The {name} is located in {building}, Floor {floor}, Room {room}.",
                "question": f"Where is {name}?",
                "answer": json.dumps({
                    "destination_name": name,
                    "building": building,
                    "floor": floor,
                    "room": room,
                    "map_coords": best_match.get("map_coords", {"x": 0, "y": 0}),
                    "directions": best_match.get("directions", [])
                }),
                "metadata": {"category": "navigation", "topic": name},
                "distance": 0.0,
                "keyword_score": 10.0,
                "combined_score": 10.0,
                "retrieval_source": "alias_matching"
            }]
        return []

    def answer(self, query: str, routing_confidence: float = 1.0) -> str:
        """
        Bypasses LLM generation. Uses deterministic substring alias matching to
        find the canonical location.
        """
        best_match = None
        try:
            # If the RIAR EntityResolver passed a pre-resolved location dictionary, use it directly.
            # We used Python's str(dict) which uses single quotes, so use ast.literal_eval.
            import ast
            parsed_query = ast.literal_eval(query)
            if isinstance(parsed_query, dict) and "id" in parsed_query:
                best_match = parsed_query
        except Exception:
            pass

        if not best_match:
            query_lower = query.lower()
            for loc in self.locations:
                for alias in loc.get("aliases", []):
                    # Ensure the alias is treated as a distinct word/phrase
                    if alias.lower() in query_lower:
                        best_match = loc
                        # Break out of inner loop
                        break
                if best_match:
                    # Break out of outer loop
                    break
                    
            if not best_match:
                return json.dumps({"error": "Location not found in directory"})
            
        result = {
            "destination_name": best_match.get("name", "Unknown"),
            "building": best_match.get("building", "Unknown"),
            "floor": str(best_match.get("floor", "0")),
            "room": best_match.get("room", "Unknown"),
            "map_coords": best_match.get("map_coords", {"x": 0, "y": 0}),
            "directions": best_match.get("directions", [])
        }
        
        return json.dumps(result)

if __name__ == "__main__":
    print("====================================")
    print("Navigation Agent Ready (Deterministic Mode)")
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
