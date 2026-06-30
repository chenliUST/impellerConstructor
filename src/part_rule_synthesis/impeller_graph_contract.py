from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


CONSTRUCTION_ROLES = {"construction_support_only", "reference_only"}
INTERNAL_ASSEMBLY_ROLES = {"mounting_bore", "shaft_seat", "keyway", "rear_hub_groove"}


def estimate_surface_area(surface: dict[str, Any]) -> float:
    grid = surface.get("uv_grid") or []
    if len(grid) < 2 or len(grid[0]) < 2:
        return 0.0
    area = 0.0
    for u in range(len(grid) - 1):
        for v in range(len(grid[u]) - 1):
            area += _triangle_area(grid[u][v], grid[u + 1][v], grid[u][v + 1])
            area += _triangle_area(grid[u + 1][v], grid[u + 1][v + 1], grid[u][v + 1])
    return round(area, 6)


def wetted_surfaces(
    surfaces: list[dict[str, Any]],
    suppressed_features: set[str] | None = None,
) -> list[dict[str, Any]]:
    suppressed = suppressed_features or set()
    result = []
    for surface in surfaces:
        role = surface.get("role")
        feature_id = surface.get("feature_id")
        if role in CONSTRUCTION_ROLES:
            continue
        if role in INTERNAL_ASSEMBLY_ROLES:
            continue
        if feature_id in suppressed:
            continue
        result.append(surface)
    return result


def surface_feature_records(surfaces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = defaultdict(lambda: {"generated_surfaces": []})
    for surface in surfaces:
        feature_id = surface.get("feature_id")
        if not feature_id:
            continue
        records[feature_id]["generated_surfaces"].append(surface["id"])
    return dict(records)


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return 0.5 * math.sqrt(sum(value * value for value in cross))
