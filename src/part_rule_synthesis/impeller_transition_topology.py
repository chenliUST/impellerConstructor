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


def patch_complex_manifest(patch_complex: PatchComplex) -> dict:
    return {
        "schema_version": "0.91",
        "nodes": {
            node_id: {
                "point": [node.point[0], node.point[1], node.point[2]],
            }
            for node_id, node in sorted(patch_complex.nodes.items())
        },
        "edges": {
            edge_id: {
                "node_ids": list(edge.node_ids),
                "role": edge.role,
                "adjacent_patch_ids": list(edge.adjacent_patch_ids),
                "physical_boundary": edge.physical_boundary,
            }
            for edge_id, edge in sorted(patch_complex.edges.items())
        },
        "patches": {
            patch_id: {
                "surface_graph_id": patch.surface_graph_id,
                "role": patch.role,
                "node_grid": [list(row) for row in patch.node_grid],
                "edge_ids": list(patch.edge_ids),
                "edge_family": patch.edge_family,
                "transition_policy_id": patch.transition_policy_id,
                "treatment": patch.treatment,
            }
            for patch_id, patch in sorted(patch_complex.patches.items())
        },
    }


def patch_complex_report(
    patch_complex: PatchComplex,
    *,
    required_corner_patch_count: int = 0,
    missing_shared_boundary_links: list[dict] | None = None,
    evaluated_shared_boundary_count: int = 0,
) -> dict:
    corner_patch_count = sum(
        1
        for patch in patch_complex.patches.values()
        if "corner" in patch.role
    )
    transition_patch_count = len(patch_complex.patches) - corner_patch_count
    boundary_failures = list(patch_complex.boundary_node_identity_failures)
    missing_links = list(missing_shared_boundary_links or [])
    if boundary_failures:
        boundary_identity_status = "FAIL"
    elif missing_links or evaluated_shared_boundary_count == 0:
        boundary_identity_status = "NOT_EVALUATED"
    else:
        boundary_identity_status = "PASS"
    return {
        "transition_patch_count": transition_patch_count,
        "corner_patch_count": corner_patch_count,
        "required_corner_patch_count": required_corner_patch_count,
        "node_count": len(patch_complex.nodes),
        "edge_count": len(patch_complex.edges),
        "patch_count": len(patch_complex.patches),
        "boundary_identity_status": boundary_identity_status,
        "evaluated_shared_boundary_count": evaluated_shared_boundary_count,
        "missing_shared_boundary_link_count": len(missing_links),
        "missing_shared_boundary_links": missing_links,
        "boundary_node_identity_failures": boundary_failures,
    }


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
