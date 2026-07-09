from __future__ import annotations

import copy
import math
from typing import Any


def build_v10_2_blade_lattice(*, blade_index: int, surfaces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    surface_ids = {
        "pressure": f"blade_{blade_index}_pressure_surface",
        "suction": f"blade_{blade_index}_suction_surface",
        "leading": f"blade_{blade_index}_leading_edge_surface",
        "trailing": f"blade_{blade_index}_trailing_edge_surface",
    }
    missing_surfaces = [
        surface_id
        for surface_id in surface_ids.values()
        if surface_id not in surfaces
    ]
    if missing_surfaces:
        return _fail(f"missing required source surface(s): {', '.join(missing_surfaces)}")

    pressure = surfaces[surface_ids["pressure"]]
    suction = surfaces[surface_ids["suction"]]
    leading = surfaces[surface_ids["leading"]]
    trailing = surfaces[surface_ids["trailing"]]

    edge_specs = {
        "pressure_root_loop": (pressure, "root_profile_pressure_edge"),
        "suction_root_loop": (suction, "root_profile_suction_edge"),
        "pressure_tip_loop": (pressure, "tip_profile_pressure_edge"),
        "suction_tip_loop": (suction, "tip_profile_suction_edge"),
        "leading_pressure_loop": (pressure, "leading_edge_pressure_boundary"),
        "leading_suction_loop": (suction, "leading_edge_suction_boundary"),
        "trailing_pressure_loop": (pressure, "trailing_edge_pressure_boundary"),
        "trailing_suction_loop": (suction, "trailing_edge_suction_boundary"),
        "root_leading_cap": (leading, "root_profile_leading_cap"),
        "tip_leading_cap": (leading, "tip_profile_leading_cap"),
        "root_trailing_cap": (trailing, "root_profile_trailing_cap"),
        "tip_trailing_cap": (trailing, "tip_profile_trailing_cap"),
    }
    loops: dict[str, list[list[float]]] = {}
    for loop_name, (surface, edge_name) in edge_specs.items():
        edge = _edge_sample(surface, edge_name)
        if edge is None:
            return _fail(f"missing edge sample {edge_name!r} on surface {surface.get('id')!r}")
        loops[loop_name] = copy.deepcopy(edge)

    closed_loops = {
        "blade_exterior_root_loop": _closed_exterior_loop(
            loops["pressure_root_loop"],
            loops["root_trailing_cap"],
            loops["suction_root_loop"],
            loops["root_leading_cap"],
        ),
        "blade_exterior_tip_loop": _closed_exterior_loop(
            loops["pressure_tip_loop"],
            loops["tip_trailing_cap"],
            loops["suction_tip_loop"],
            loops["tip_leading_cap"],
        ),
    }

    frames = _build_frames(
        pressure=pressure,
        suction=suction,
        leading=leading,
        trailing=trailing,
        loops=loops,
    )
    failure_reason = frames.pop("failure_reason", None)
    if failure_reason:
        return _fail(failure_reason)

    return {
        "status": "PASS",
        "blade_index": blade_index,
        "source_surface_ids": surface_ids,
        "loops": loops,
        "closed_loops": closed_loops,
        "frames": frames,
    }


def _build_frames(
    *,
    pressure: dict[str, Any],
    suction: dict[str, Any],
    leading: dict[str, Any],
    trailing: dict[str, Any],
    loops: dict[str, list[list[float]]],
) -> dict[str, Any]:
    pressure_grid = pressure.get("uv_grid", [])
    suction_grid = suction.get("uv_grid", [])
    for surface in [pressure, suction, leading, trailing]:
        grid = surface.get("uv_grid", [])
        if len(grid) < 2 or len(grid[0]) < 2:
            return {"failure_reason": f"surface {surface.get('id')!r} has an insufficient uv_grid"}

    return {
        "leading_pressure_frames": _frames_from_loop(
            loops["leading_pressure_loop"],
            pressure_grid[1],
        ),
        "leading_suction_frames": _frames_from_loop(
            loops["leading_suction_loop"],
            suction_grid[1],
        ),
        "trailing_pressure_frames": _frames_from_loop(
            loops["trailing_pressure_loop"],
            pressure_grid[-2],
        ),
        "trailing_suction_frames": _frames_from_loop(
            loops["trailing_suction_loop"],
            suction_grid[-2],
        ),
        "tip_pressure_frames": _frames_from_loop(
            loops["pressure_tip_loop"],
            [row[-2] for row in pressure_grid],
        ),
        "tip_suction_frames": _frames_from_loop(
            loops["suction_tip_loop"],
            [row[-2] for row in suction_grid],
        ),
        "root_pressure_frames": _frames_from_loop(
            loops["pressure_root_loop"],
            [row[1] for row in pressure_grid],
        ),
        "root_suction_frames": _frames_from_loop(
            loops["suction_root_loop"],
            [row[1] for row in suction_grid],
        ),
    }


def _frames_from_loop(
    loop: list[list[float]],
    adjacent_loop: list[list[float]],
) -> list[dict[str, Any]]:
    frames = []
    previous_normal: list[float] | None = None
    for index, point in enumerate(loop):
        edge_tangent = _normalized(_finite_difference(loop, index)) or [1.0, 0.0, 0.0]
        cross_edge_tangent = _normalized(_subtract(_sample(adjacent_loop, index), point))
        if cross_edge_tangent is None:
            cross_edge_tangent = _fallback_cross_tangent(edge_tangent)
        material_normal = _normalized(_cross(edge_tangent, cross_edge_tangent))
        if material_normal is None:
            material_normal = _fallback_normal(edge_tangent, cross_edge_tangent)
        if previous_normal is not None and _dot(material_normal, previous_normal) < 0.0:
            material_normal = _scale(material_normal, -1.0)
        previous_normal = material_normal

        curvature_proxy = _normalized(_second_difference(loop, index)) or [0.0, 0.0, 0.0]
        frames.append(
            {
                "point": copy.deepcopy(point),
                "edge_tangent": _round_vector(edge_tangent),
                "cross_edge_tangent": _round_vector(cross_edge_tangent),
                "material_normal": _round_vector(material_normal),
                "curvature_proxy": _round_vector(curvature_proxy),
            }
        )
    return frames


def _closed_exterior_loop(
    pressure_loop: list[list[float]],
    trailing_cap: list[list[float]],
    suction_loop: list[list[float]],
    leading_cap: list[list[float]],
) -> list[list[float]]:
    closed_loop: list[list[float]] = []
    for segment in [
        pressure_loop,
        trailing_cap,
        list(reversed(suction_loop)),
        list(reversed(leading_cap)),
    ]:
        _append_stitched_segment(closed_loop, segment)
    if closed_loop and closed_loop[0] != closed_loop[-1]:
        closed_loop.append(copy.deepcopy(closed_loop[0]))
    return closed_loop


def _append_stitched_segment(
    stitched_loop: list[list[float]],
    segment: list[list[float]],
) -> None:
    start_index = 1 if stitched_loop and segment and stitched_loop[-1] == segment[0] else 0
    stitched_loop.extend(copy.deepcopy(point) for point in segment[start_index:])


def _edge_sample(surface: dict[str, Any], edge_name: str) -> list[list[float]] | None:
    edge_samples = surface.get("edge_samples", {})
    edge = edge_samples.get(edge_name)
    if not isinstance(edge, list) or not edge:
        return None
    return edge


def _sample(points: list[list[float]], index: int) -> list[float]:
    if not points:
        return [0.0, 0.0, 0.0]
    return points[min(index, len(points) - 1)]


def _finite_difference(points: list[list[float]], index: int) -> list[float]:
    if len(points) == 1:
        return [0.0, 0.0, 0.0]
    if index == 0:
        return _subtract(points[1], points[0])
    if index == len(points) - 1:
        return _subtract(points[-1], points[-2])
    return _subtract(points[index + 1], points[index - 1])


def _second_difference(points: list[list[float]], index: int) -> list[float]:
    if len(points) < 3:
        return [0.0, 0.0, 0.0]
    left = points[max(index - 1, 0)]
    center = points[index]
    right = points[min(index + 1, len(points) - 1)]
    return [
        float(left[axis]) - 2.0 * float(center[axis]) + float(right[axis])
        for axis in range(3)
    ]


def _column(grid: list[list[list[float]]], index: int) -> list[list[float]]:
    return [copy.deepcopy(row[index]) for row in grid]


def _subtract(first: list[float], second: list[float]) -> list[float]:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _scale(vector: list[float], scalar: float) -> list[float]:
    return [float(value) * scalar for value in vector]


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _normalized(vector: list[float]) -> list[float] | None:
    length = _length(vector)
    if length <= 1.0e-9:
        return None
    return [float(value) / length for value in vector]


def _dot(first: list[float], second: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first: list[float], second: list[float]) -> list[float]:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _fallback_cross_tangent(edge_tangent: list[float]) -> list[float]:
    radial = _normalized([edge_tangent[1], -edge_tangent[0], 0.0])
    if radial is not None:
        return radial
    return [0.0, 1.0, 0.0]


def _fallback_normal(edge_tangent: list[float], cross_edge_tangent: list[float]) -> list[float]:
    normal = _normalized(_cross(edge_tangent, _fallback_cross_tangent(cross_edge_tangent)))
    if normal is not None:
        return normal
    return [0.0, 0.0, 1.0]


def _round_vector(vector: list[float]) -> list[float]:
    return [round(float(value), 9) for value in vector]


def _fail(reason: str) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "failure_reason": reason,
    }
