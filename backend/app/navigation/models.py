from typing import List

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    name: str
    x: int
    y: int
    floor: int = 0


class Edge(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    cost: int

    class Config:
        populate_by_name = True


class GraphModel(BaseModel):
    nodes: List[Node]
    edges: List[Edge]
