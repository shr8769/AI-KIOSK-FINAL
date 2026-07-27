import json
import os
from typing import Dict

from .models import Edge, GraphModel, Node


class GraphLoader:
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.graph = None
        self.node_map: Dict[str, Node] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.json_path):
            import logging
            logging.getLogger(__name__).warning(f"Graph file not found: {self.json_path}. Initializing empty graph.")
            self.graph = GraphModel(nodes=[], edges=[])
            return

        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.graph = GraphModel(**data)

        for node in self.graph.nodes:
            self.node_map[node.id] = node

    def get_node(self, node_id: str) -> Node:
        return self.node_map.get(node_id)

    def get_neighbors(self, node_id: str) -> Dict[str, Edge]:
        neighbors = {}
        for edge in self.graph.edges:
            if edge.from_node == node_id:
                neighbors[edge.to_node] = edge
        return neighbors
