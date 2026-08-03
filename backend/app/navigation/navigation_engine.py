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

        instructions = []
        start_floor = getattr(path[0], 'floor', 0)
        floor_names = {0: "Ground Floor", 1: "1st Floor", 2: "2nd Floor", 3: "3rd Floor", 4: "4th Floor"}
        start_floor_name = floor_names.get(start_floor, f"Floor {start_floor}")
        instructions.append(f"Start from {path[0].name} on the {start_floor_name}")

        i = 1
        while i < len(path):
            curr_node = path[i-1]
            next_node = path[i]
            curr_floor = getattr(curr_node, 'floor', 0)
            next_floor = getattr(next_node, 'floor', 0)

            # Check if this is the start of a vertical floor transition (Lift / Stairs)
            if curr_floor != next_floor:
                transit_type = "Lift" if "lift" in next_node.name.lower() or "lift" in curr_node.name.lower() else "Stairs"

                # Consume all consecutive nodes that are part of this lift/stairs vertical movement
                final_floor = next_floor
                while i < len(path) - 1:
                    lookahead_curr = path[i]
                    lookahead_next = path[i+1]
                    if (transit_type.lower() in lookahead_next.name.lower() or transit_type.lower() in lookahead_curr.name.lower()) and getattr(lookahead_curr, 'floor', 0) != getattr(lookahead_next, 'floor', 0):
                        final_floor = getattr(lookahead_next, 'floor', 0)
                        i += 1
                    else:
                        break

                dest_floor_name = floor_names.get(final_floor, f"Floor {final_floor}")
                instructions.append(f"Take the {transit_type} to the {dest_floor_name}")
            else:
                if i < len(path) - 1:
                    if "junction" not in next_node.name.lower() and "corner" not in next_node.name.lower():
                        instructions.append(f"Walk to {next_node.name}")
                    else:
                        if not instructions or "Continue down the corridor" not in instructions[-1]:
                            instructions.append("Continue down the corridor")

            i += 1

        instructions.append(f"Proceed towards {path[-1].name}")
        instructions.append("Destination reached")

        return instructions

    def generate_route(self, destination_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given the destination metadata (from navigation_locations.json),
        computes the path from KIOSK to the destination's graph_node,
        and constructs the payload to be saved in Redis.
        """
        destination_name = destination_metadata.get("destination_name", destination_metadata.get("name", "Unknown Destination"))
        target_node_id = destination_metadata.get("graph_node")

        if not target_node_id:
            # Fallback: attempt to find the node by destination name
            for node in self.loader.graph.nodes:
                if node.name.lower() == destination_name.lower() or node.id.lower() == destination_name.lower():
                    target_node_id = node.id
                    break

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
            {"id": node.id, "name": node.name, "x": node.x, "y": node.y, "floor": getattr(node, 'floor', 0)}
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
