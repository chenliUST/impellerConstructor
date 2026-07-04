from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class SharedNode:
    node_id: str
    point: Point3


@dataclass
class SharedEdge:
    edge_id: str
    node_ids: list[str]
    role: str
    adjacent_patch_ids: list[str] = field(default_factory=list)
    physical_boundary: bool = False


@dataclass
class Patch:
    patch_id: str
    surface_graph_id: str
    role: str
    node_grid: list[list[str]]
    edge_ids: list[str]
    edge_family: str = ""
    transition_policy_id: str = ""
    treatment: str = ""


@dataclass
class PatchComplex:
    nodes: dict[str, SharedNode] = field(default_factory=dict)
    edges: dict[str, SharedEdge] = field(default_factory=dict)
    patches: dict[str, Patch] = field(default_factory=dict)
    boundary_node_identity_failures: list[dict] = field(default_factory=list)

    def add_node(self, node_id: str, point: Point3) -> str:
        existing = self.nodes.get(node_id)
        if existing is not None and existing.point != point:
            self.boundary_node_identity_failures.append(
                {"node_id": node_id, "first_point": existing.point, "second_point": point}
            )
        else:
            self.nodes[node_id] = SharedNode(node_id=node_id, point=point)
        return node_id

    def add_edge(
        self,
        edge_id: str,
        node_ids: Iterable[str],
        role: str,
        physical_boundary: bool = False,
    ) -> str:
        ids = list(node_ids)
        edge = self.edges.get(edge_id)
        if edge is None:
            self.edges[edge_id] = SharedEdge(
                edge_id=edge_id,
                node_ids=ids,
                role=role,
                physical_boundary=physical_boundary,
            )
        elif edge.node_ids != ids and edge.node_ids != list(reversed(ids)):
            self.boundary_node_identity_failures.append(
                {"edge_id": edge_id, "first_nodes": edge.node_ids, "second_nodes": ids}
            )
        return edge_id

    def add_patch(self, patch: Patch) -> None:
        self.patches[patch.patch_id] = patch
        for edge_id in patch.edge_ids:
            if edge_id in self.edges and patch.patch_id not in self.edges[edge_id].adjacent_patch_ids:
                self.edges[edge_id].adjacent_patch_ids.append(patch.patch_id)


def point_key(point: Iterable[float], tolerance: float = 1.0e-6) -> str:
    scale = 1.0 / tolerance
    return "_".join(str(round(float(value) * scale)) for value in point)
