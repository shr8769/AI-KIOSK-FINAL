import heapq
import math
from typing import Dict, List, Tuple

from .graph_loader import GraphLoader
from .models import Node


class AStar:
    def __init__(self, loader: GraphLoader):
        self.loader = loader

    def heuristic(self, node_a: Node, node_b: Node) -> float:
        """3D-aware distance heuristic between two nodes."""
        xy_dist = math.sqrt((node_a.x - node_b.x) ** 2 + (node_a.y - node_b.y) ** 2)
        floor_penalty = abs(getattr(node_a, 'floor', 0) - getattr(node_b, 'floor', 0)) * 250
        return xy_dist + floor_penalty

    def find_path(self, start_id: str, goal_id: str) -> Tuple[List[Node], float]:
        """
        Runs A* search and returns a tuple of (ordered list of Nodes, total cost).
        Returns ([], 0.0) if no path is found.
        """
        start_node = self.loader.get_node(start_id)
        goal_node = self.loader.get_node(goal_id)

        if not start_node or not goal_node:
            return [], 0.0

        # open_set stores tuples of (fScore, id)
        open_set = []
        heapq.heappush(open_set, (0.0, start_id))

        came_from: Dict[str, str] = {}

        # gScore tracks cheapest path from start to n currently known
        gScore: Dict[str, float] = {start_id: 0.0}

        # fScore = gScore + heuristic
        fScore: Dict[str, float] = {start_id: self.heuristic(start_node, goal_node)}

        # Keep track of items in open_set for O(1) lookup
        in_open_set = {start_id}

        while open_set:
            _, current_id = heapq.heappop(open_set)
            in_open_set.remove(current_id)

            if current_id == goal_id:
                return self._reconstruct_path(came_from, current_id), gScore[goal_id]

            neighbors = self.loader.get_neighbors(current_id)

            for neighbor_id, edge in neighbors.items():
                tentative_gScore = gScore[current_id] + edge.cost

                if neighbor_id not in gScore or tentative_gScore < gScore[neighbor_id]:
                    # This path to neighbor is better than any previous one
                    came_from[neighbor_id] = current_id
                    gScore[neighbor_id] = tentative_gScore

                    neighbor_node = self.loader.get_node(neighbor_id)
                    fScore[neighbor_id] = tentative_gScore + self.heuristic(neighbor_node, goal_node)

                    if neighbor_id not in in_open_set:
                        heapq.heappush(open_set, (fScore[neighbor_id], neighbor_id))
                        in_open_set.add(neighbor_id)

        return [], 0.0

    def _reconstruct_path(self, came_from: Dict[str, str], current_id: str) -> List[Node]:
        path_ids = [current_id]
        while current_id in came_from:
            current_id = came_from[current_id]
            path_ids.append(current_id)
        path_ids.reverse()

        return [self.loader.get_node(nid) for nid in path_ids]
