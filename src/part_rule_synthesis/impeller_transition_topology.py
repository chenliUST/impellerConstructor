from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class SharedNode:
    node_id: str
    point: Point3


@dataclass(eq=False)
class SharedEdge:
    edge_id: str
    node_ids: list[str]
    role: str
    adjacent_patch_ids: list[str] = field(default_factory=list)
    physical_boundary: bool = False


@dataclass(eq=False)
class Patch:
    patch_id: str
    surface_graph_id: str
    role: str
    node_grid: list[list[str]]
    edge_ids: list[str]
    edge_family: str = ""
    transition_policy_id: str = ""
    treatment: str = ""


@dataclass(eq=False)
class PatchComplex:
    nodes: dict[str, SharedNode] = field(default_factory=dict)
    edges: dict[str, SharedEdge] = field(default_factory=dict)
    patches: dict[str, Patch] = field(default_factory=dict)
    boundary_node_identity_failures: list[dict] = field(default_factory=list)
    point_tolerance: float = 1.0e-6

    def add_node(self, node_id: str, point: Point3) -> str:
        normalized_point = tuple(float(value) for value in point)
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = SharedNode(node_id=node_id, point=normalized_point)
        elif not points_within_tolerance(existing.point, normalized_point, self.point_tolerance):
            self.boundary_node_identity_failures.append(
                {"node_id": node_id, "first_point": existing.point, "second_point": normalized_point}
            )
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
        else:
            if edge.node_ids != ids and edge.node_ids != list(reversed(ids)):
                self.boundary_node_identity_failures.append(
                    {
                        "edge_id": edge_id,
                        "first_nodes": list(edge.node_ids),
                        "second_nodes": list(ids),
                    }
                )
            if edge.role != role or edge.physical_boundary != physical_boundary:
                self.boundary_node_identity_failures.append(
                    {
                        "edge_id": edge_id,
                        "first_role": edge.role,
                        "second_role": role,
                        "first_physical_boundary": edge.physical_boundary,
                        "second_physical_boundary": physical_boundary,
                    }
                )
        self._backfill_edge_adjacency(edge_id)
        return edge_id

    def add_patch(self, patch: Patch) -> None:
        existing = self.patches.get(patch.patch_id)
        if existing is not None:
            self._remove_patch_adjacency(existing)
        self.patches[patch.patch_id] = patch
        for edge_id in patch.edge_ids:
            self._add_edge_adjacency(edge_id, patch.patch_id)

    def _backfill_edge_adjacency(self, edge_id: str) -> None:
        for patch in self.patches.values():
            if edge_id in patch.edge_ids:
                self._add_edge_adjacency(edge_id, patch.patch_id)

    def _add_edge_adjacency(self, edge_id: str, patch_id: str) -> None:
        edge = self.edges.get(edge_id)
        if edge is not None and patch_id not in edge.adjacent_patch_ids:
            edge.adjacent_patch_ids.append(patch_id)

    def _remove_patch_adjacency(self, patch: Patch) -> None:
        for edge_id in patch.edge_ids:
            edge = self.edges.get(edge_id)
            if edge is not None:
                edge.adjacent_patch_ids = [
                    patch_id
                    for patch_id in edge.adjacent_patch_ids
                    if patch_id != patch.patch_id
                ]


def point_key(point: Iterable[float], tolerance: float = 1.0e-6) -> str:
    scale = 1.0 / tolerance
    return "_".join(str(round(float(value) * scale)) for value in point)


def points_within_tolerance(
    first: Iterable[float],
    second: Iterable[float],
    tolerance: float,
) -> bool:
    return all(
        abs(float(first_value) - float(second_value)) <= tolerance
        for first_value, second_value in zip(first, second, strict=True)
    )
