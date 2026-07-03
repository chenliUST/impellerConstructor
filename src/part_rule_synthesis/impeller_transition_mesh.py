from __future__ import annotations

import math
from collections import Counter
from typing import Any

from part_rule_synthesis.impeller_surface_graph_export import (
    _has_rectangular_quad_grid,
    _point,
    _surface_visible_in_view,
    _triangle_normal,
)


def build_transition_aware_mesh(
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    triangles: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    included_surface_ids: list[str] = []
    excluded_surface_ids: list[str] = []
    surface_lookup = _surface_lookup(surface_graph)
    site_lookup = _edge_treatment_site_lookup(surface_graph)
    edge_lookup = _edge_transition_lookup(surface_graph)

    for surface in surface_graph.get("surfaces", []):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or "")
        if not _surface_visible_in_view(surface, view_id):
            excluded_surface_ids.append(surface_id)
            continue
        grid = surface.get("uv_grid", [])
        if not _has_rectangular_quad_grid(grid):
            excluded_surface_ids.append(surface_id)
            continue

        start = len(triangles)
        v_count = len(grid[0])
        for u_index in range(len(grid) - 1):
            for v_index in range(v_count - 1):
                a = _point(grid[u_index][v_index])
                b = _point(grid[u_index + 1][v_index])
                c = _point(grid[u_index + 1][v_index + 1])
                d = _point(grid[u_index][v_index + 1])
                for points in [(a, b, d), (b, c, d)]:
                    normal = _triangle_normal(*points)
                    if normal is None:
                        skipped.append(
                            {
                                "surface_graph_id": surface_id,
                                "u_index": u_index,
                                "v_index": v_index,
                                "reason": "degenerate_triangle",
                            }
                        )
                        continue
                    triangles.append(
                        {
                            "points": [list(point) for point in points],
                            "normal": list(normal),
                            "surface_graph_id": surface_id,
                            "feature_id": str(surface.get("feature_id") or ""),
                            "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                        }
                    )
        count = len(triangles) - start
        if count > 0:
            included_surface_ids.append(surface_id)
            regions.append(
                {
                    "surface_graph_id": surface_id,
                    "feature_id": str(surface.get("feature_id") or ""),
                    "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                    "triangle_start": start,
                    "triangle_count": count,
                }
            )

    skipped_reasons = Counter(item["reason"] for item in skipped)
    transition_regions = _transition_regions(
        regions,
        triangles,
        surface_lookup,
        site_lookup,
        edge_lookup,
    )
    return {
        "mesh_type": "transition_aware_surface_mesh",
        "source": "transition_resolved_surface_graph",
        "view": view_id,
        "triangles": triangles,
        "triangle_count": len(triangles),
        "triangle_regions": regions,
        "transition_regions": transition_regions,
        "included_surface_ids": included_surface_ids,
        "excluded_surface_ids": excluded_surface_ids,
        "skipped_triangle_count": len(skipped),
        "skipped_triangle_reasons": dict(sorted(skipped_reasons.items())),
        "skipped_triangles": skipped,
    }


def _transition_regions(
    triangle_regions: list[dict[str, Any]],
    triangles: list[dict[str, Any]],
    surface_lookup: dict[str, dict[str, Any]],
    site_lookup: dict[str, dict[str, Any]],
    edge_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for region in triangle_regions:
        surface_id = region["surface_graph_id"]
        surface = surface_lookup.get(surface_id, {})
        site = site_lookup.get(surface_id, {})
        edge = edge_lookup.get(surface_id, {})
        edge_family = str(surface.get("edge_family") or site.get("edge_family") or edge.get("edge_family") or "")
        transition_policy_id = str(
            surface.get("transition_policy_id")
            or site.get("transition_policy_id")
            or edge.get("transition_policy_id")
            or ""
        )
        if not edge_family and not transition_policy_id:
            continue
        treatment = str(surface.get("treatment") or site.get("treatment") or "")
        region_triangles = triangles[
            region["triangle_start"] : region["triangle_start"] + region["triangle_count"]
        ]
        regions.append(
            {
                "surface_graph_id": surface_id,
                "feature_id": region["feature_id"],
                "role": region["role"],
                "triangle_start": region["triangle_start"],
                "triangle_count": region["triangle_count"],
                "edge_treatment_site_id": str(
                    surface.get("edge_treatment_site_id") or site.get("edge_treatment_site_id") or ""
                ),
                "edge_family": edge_family,
                "transition_policy_id": transition_policy_id,
                "treatment": treatment,
                "radius_mm": _optional_float(surface.get("radius_mm", site.get("radius_mm"))),
                "quality": _quality_metrics(region_triangles),
            }
        )
    return regions


def _quality_metrics(triangles: list[dict[str, Any]]) -> dict[str, Any]:
    edge_lengths = [
        edge_length
        for triangle in triangles
        for edge_length in _triangle_edge_lengths(triangle["points"])
    ]
    aspect_ratios = [
        _triangle_aspect_ratio(triangle["points"])
        for triangle in triangles
    ]
    return {
        "max_aspect_ratio": max(aspect_ratios) if aspect_ratios else 0.0,
        "min_edge_length_mm": min(edge_lengths) if edge_lengths else 0.0,
        "max_edge_length_mm": max(edge_lengths) if edge_lengths else 0.0,
        "boundary_mismatch_max_mm": None,
        "boundary_mismatch_status": "not_evaluated",
    }


def _triangle_edge_lengths(points: list[list[float]]) -> list[float]:
    first, second, third = (_point(point) for point in points)
    return [
        _distance(first, second),
        _distance(second, third),
        _distance(third, first),
    ]


def _triangle_aspect_ratio(points: list[list[float]]) -> float:
    lengths = _triangle_edge_lengths(points)
    shortest = min(lengths)
    if shortest <= 1.0e-12:
        return 0.0
    return max(lengths) / shortest


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(
        (second[0] - first[0]) ** 2
        + (second[1] - first[1]) ** 2
        + (second[2] - first[2]) ** 2
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _surface_lookup(surface_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(surface.get("id") or surface.get("surface_graph_id") or ""): surface
        for surface in surface_graph.get("surfaces", [])
        if isinstance(surface, dict)
    }


def _edge_treatment_site_lookup(surface_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for site in surface_graph.get("edge_treatment_sites", []):
        if not isinstance(site, dict):
            continue
        transition_surface_ids = site.get("transition_surface_ids", [])
        if not isinstance(transition_surface_ids, list):
            continue
        for surface_id in transition_surface_ids:
            lookup.setdefault(str(surface_id), site)
    return lookup


def _edge_transition_lookup(surface_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for edge in surface_graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        transition_surface_ids = edge.get("transition_surface_ids", [])
        if not isinstance(transition_surface_ids, list):
            continue
        for surface_id in transition_surface_ids:
            lookup.setdefault(str(surface_id), edge)
    return lookup
