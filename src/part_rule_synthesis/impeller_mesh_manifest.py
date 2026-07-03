from __future__ import annotations

import math
from typing import Any

from part_rule_synthesis.impeller_surface_graph_export import triangulate_surface_graph


def build_surface_mesh_manifest(
    surface_graph: dict[str, Any],
    view_id: str = "cfd_full_360",
) -> dict[str, Any]:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
    triangles = triangulation["triangles"]
    areas = [_triangle_area(triangle["points"]) for triangle in triangles]
    aspect_ratios = [_triangle_aspect_ratio(triangle["points"]) for triangle in triangles]

    return {
        "source": "surface_graph",
        "view": view_id,
        "mesh_type": "surface_triangles",
        "triangle_count": triangulation["triangle_count"],
        "degenerate_triangle_count": triangulation["skipped_triangle_count"],
        "quality_metrics": {
            "min_area": min(areas) if areas else 0.0,
            "max_area": max(areas) if areas else 0.0,
            "max_aspect_ratio": max(aspect_ratios) if aspect_ratios else 0.0,
        },
        "patch_regions": [
            {
                "surface_graph_id": region["surface_graph_id"],
                "feature_id": region["feature_id"],
                "role": region["role"],
                "triangle_start": region["triangle_start"],
                "triangle_count": region["triangle_count"],
            }
            for region in triangulation["triangle_regions"]
        ],
        "transition_regions": build_transition_regions(surface_graph, triangulation["triangle_regions"]),
    }


def build_transition_regions(
    surface_graph: dict[str, Any],
    triangle_regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    surface_lookup = _surface_lookup(surface_graph)
    edge_lookup = _edge_transition_lookup(surface_graph)
    regions: list[dict[str, Any]] = []
    for region in triangle_regions:
        surface_id = region["surface_graph_id"]
        surface = surface_lookup.get(surface_id, {})
        edge_metadata = edge_lookup.get(surface_id, {})
        edge_family = str(surface.get("edge_family") or edge_metadata.get("edge_family") or "")
        transition_policy_id = str(
            surface.get("transition_policy_id") or edge_metadata.get("transition_policy_id") or ""
        )
        if not edge_family and not transition_policy_id:
            continue
        regions.append(
            {
                "surface_graph_id": surface_id,
                "feature_id": region["feature_id"],
                "role": region["role"],
                "edge_family": edge_family,
                "transition_policy_id": transition_policy_id,
                "triangle_start": region["triangle_start"],
                "triangle_count": region["triangle_count"],
            }
        )
    return regions


def _triangle_area(points: list[list[float]]) -> float:
    first, second, third = (_point(point) for point in points)
    ab = _vector(first, second)
    ac = _vector(first, third)
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * _length(cross)


def _triangle_aspect_ratio(points: list[list[float]]) -> float:
    first, second, third = (_point(point) for point in points)
    edges = [
        _distance(first, second),
        _distance(second, third),
        _distance(third, first),
    ]
    shortest = min(edges)
    if shortest <= 1.0e-12:
        return 0.0
    return max(edges) / shortest


def _point(value: list[float]) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _vector(first: tuple[float, float, float], second: tuple[float, float, float]) -> tuple[float, float, float]:
    return (second[0] - first[0], second[1] - first[1], second[2] - first[2])


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return _length(_vector(first, second))


def _length(vector: tuple[float, float, float]) -> float:
    return math.sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2])


def _surface_lookup(surface_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(surface.get("id") or surface.get("surface_graph_id") or ""): surface
        for surface in surface_graph.get("surfaces", [])
        if isinstance(surface, dict)
    }


def _edge_transition_lookup(surface_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for edge in surface_graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_family = str(edge.get("edge_family") or "")
        transition_policy_id = str(edge.get("transition_policy_id") or "")
        if not edge_family and not transition_policy_id:
            continue
        transition_surface_ids = edge.get("transition_surface_ids", [])
        if not isinstance(transition_surface_ids, list):
            continue
        for surface_id in transition_surface_ids:
            lookup.setdefault(
                str(surface_id),
                {
                    "edge_family": edge_family,
                    "transition_policy_id": transition_policy_id,
                },
            )
    return lookup
