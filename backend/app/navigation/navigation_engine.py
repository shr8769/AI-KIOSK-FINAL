import os
from typing import Any, Dict, List, Optional

from .astar import AStar
from .graph_loader import GraphLoader
from .models import Node


class NavigationEngine:
    def __init__(self, graph_path: Optional[str] = None):
        if not graph_path:
            graph_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "..",
                    "knowledge",
                    "sources",
                    "navigation",
                    "navigation_graph.json",
                )
            )
        self.loader = GraphLoader(graph_path)
        self.astar = AStar(self.loader)

    def generate_turn_instructions(self, path: List[Node]) -> List[str]:
        if not path:
            return []

        if len(path) == 1:
            return [f"You are already at {path[0].name}."]

        instructions = [f"Start from {path[0].name}"]

        for i in range(1, len(path) - 1):
            instructions.append(f"Walk to {path[i].name}")

        instructions.append(f"Proceed towards {path[-1].name}")
        instructions.append("Destination reached")

        return instructions

    def generate_route(self, destination_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given the destination metadata (from navigation_locations.json),
        computes the path from KIOSK to the destination's graph_node,
        and constructs the payload to be saved in Redis.
        """
        destination_name = destination_metadata.get("name", "Unknown Destination")
        target_node_id = destination_metadata.get("graph_node")

        if not target_node_id:
            return {
                "destination": destination_name,
                "path": [],
                "estimated_distance": 0,
                "estimated_walk_time": "0 min",
                "directions": ["Destination not found on graph."]
            }

        start_node_id = "KIOSK"

        path_nodes, total_cost = self.astar.find_path(start_node_id, target_node_id)

        # Format the path array for the frontend payload
        path_payload = [
            {"id": node.id, "name": node.name, "x": node.x, "y": node.y}
            for node in path_nodes
        ]

        instructions = self.generate_turn_instructions(path_nodes)

        # Simple estimation: 80 units ~ 1 min walking
        est_minutes = max(1, round(total_cost / 80))

        return {
            "destination": destination_name,
            "path": path_payload,
            "estimated_distance": int(total_cost),
            "estimated_walk_time": f"{est_minutes} min",
            "directions": instructions
        }


# Singleton instance
navigation_engine = NavigationEngine()
