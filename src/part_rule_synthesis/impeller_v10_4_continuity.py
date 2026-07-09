from __future__ import annotations

import copy
import math
from typing import Any


ALLOWED_STATUSES = [
    "G2_MEASURED",
    "G1_MEASURED_G2_FAILED",
    "G0_ONLY_FAILED",
    "EXTRAORDINARY_VERTEX_EXCLUDED",
]

POSITION_GAP_LIMIT_MM = 1.0e-6
TANGENT_ANGLE_LIMIT_DEG = 2.0
NORMAL_ANGLE_LIMIT_DEG = 5.0
CURVATURE_PROXY_LIMIT = 0.25
BLADE_HUB_MIN_ANGLE_DEG = 60.0
BLADE_HUB_MAX_ANGLE_DEG = 120.0


def measure_v10_4_continuity(surface_graph: dict[str, Any]) -> dict[str, Any]:
    surfaces = {surface.get("id"): surface for surface in surface_graph.get("surfaces", [])}
    measurements = []
    for edge in _v10_4_blade_root_edges(surface_graph):
        first = surfaces.get(edge.get("first_face_id"))
        second = surfaces.get(edge.get("second_face_id"))
        if first is None or second is None:
            measurements.append(_failed_edge(edge, "v1_0_4_shared_edge_surface_missing"))
            continue
        measurements.append(_measure_blade_root_edge(first, second, edge))

    failures = [item for item in measurements if item["status"] != "G2_MEASURED"]
    return {
        "status": "PASS" if measurements and not failures else "FAIL",
        "reason": None if measurements and not failures else "v1_0_4_measured_g2_continuity_failed",
        "contract": "v1_0_4_blade_root_continuity_measurement",
        "measurement_strategy": "shared_edge_position_tangent_normal_curvature_from_adjacent_uv_grid_frames",
        "measured_edge_count": len(measurements),
        "max_position_gap_mm": _round(max((item["position_gap_mm"] for item in measurements), default=math.inf)),
        "max_tangent_angle_deg": _round(max((item["tangent_angle_deg"] for item in measurements), default=180.0)),
        "max_normal_angle_deg": _round(max((item["normal_angle_deg"] for item in measurements), default=180.0)),
        "max_curvature_proxy_mismatch": _round(max((item["curvature_proxy_mismatch"] for item in measurements), default=1.0)),
        "edge_measurements": measurements,
        "allowed_statuses": copy.deepcopy(ALLOWED_STATUSES),
    }


def measure_v10_4_blade_hub_angles(surface_graph: dict[str, Any]) -> dict[str, Any]:
    surfaces = {surface.get("id"): surface for surface in surface_graph.get("surfaces", [])}
    samples = []
    for edge in _v10_4_blade_root_edges(surface_graph):
        blade = surfaces.get(edge.get("first_face_id"))
        root = surfaces.get(edge.get("second_face_id"))
        if blade is None or root is None:
            continue
        samples.extend(_blade_hub_angle_samples(blade, root, edge))

    valid_samples = [
        sample
        for sample in samples
        if sample.get("status") == "PASS" and sample.get("angle_deg") is not None
    ]
    angles = [sample["angle_deg"] for sample in valid_samples]
    degenerate_sample_count = sum(1 for sample in samples if sample.get("status") == "FAIL")
    min_angle = min(angles) if angles else 0.0
    max_angle = max(angles) if angles else 180.0
    in_range = (
        bool(samples)
        and degenerate_sample_count == 0
        and bool(angles)
        and min_angle >= BLADE_HUB_MIN_ANGLE_DEG
        and max_angle <= BLADE_HUB_MAX_ANGLE_DEG
    )
    if in_range:
        reason = None
    elif degenerate_sample_count:
        reason = "v1_0_4_blade_hub_angle_degenerate_vector"
    else:
        reason = "v1_0_4_blade_hub_angle_out_of_range"
    return {
        "status": "PASS" if in_range else "FAIL",
        "reason": reason,
        "contract": "v1_0_4_blade_hub_inspection_angle",
        "measurement_strategy": "blade_root_surface_inward_tangent_to_root_patch_hub_span",
        "min_blade_hub_angle_deg": _round(min_angle),
        "max_blade_hub_angle_deg": _round(max_angle),
        "sample_count": len(samples),
        "valid_sample_count": len(valid_samples),
        "degenerate_sample_count": degenerate_sample_count,
        "angle_samples": samples,
    }


def _v10_4_blade_root_edges(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = {surface.get("id"): surface for surface in surface_graph.get("surfaces", [])}
    edges = []
    for edge in surface_graph.get("topology_graph", {}).get("shared_edges", []):
        first = surfaces.get(edge.get("first_face_id"))
        second = surfaces.get(edge.get("second_face_id"))
        if _is_blade_face(first) and _is_v10_4_root_component(second):
            if edge.get("first_edge_role") == "root" and edge.get("second_edge_role") == "blade_inner_loop":
                edges.append(edge)
        elif _is_blade_face(second) and _is_v10_4_root_component(first):
            if edge.get("second_edge_role") == "root" and edge.get("first_edge_role") == "blade_inner_loop":
                edges.append(_reversed_edge(edge))
    return edges


def _measure_blade_root_edge(first: dict[str, Any], second: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    first_samples = _edge_samples(first, edge["first_edge_role"])
    second_samples = _aligned_samples(first_samples, _edge_samples(second, edge["second_edge_role"]), edge)
    sample_count = min(len(first_samples), len(second_samples))
    if sample_count < 2:
        return _failed_edge(edge, "v1_0_4_shared_edge_samples_missing")

    first_samples = first_samples[:sample_count]
    second_samples = second_samples[:sample_count]
    position_gap = max(_distance(a, b) for a, b in zip(first_samples, second_samples))
    tangent_angle = _max_tangent_angle(first_samples, second_samples)
    first_frames = _edge_boundary_frames(first, edge["first_edge_role"], first_samples)
    second_frames = _edge_boundary_frames(second, edge["second_edge_role"], second_samples)
    normal_angle = _max_normal_angle(first_frames, second_frames)
    curvature_mismatch = _surface_curvature_proxy_mismatch(first_frames, second_frames)
    frame_sample_count = min(len(first_frames), len(second_frames))
    degenerate_frame_count = _degenerate_frame_count(first_frames, second_frames)
    status = _continuity_status(position_gap, tangent_angle, normal_angle, curvature_mismatch)
    return {
        "edge_id": edge.get("id"),
        "first_face_id": first["id"],
        "first_edge_role": edge["first_edge_role"],
        "second_face_id": second["id"],
        "second_edge_role": edge["second_edge_role"],
        "orientation": edge.get("orientation"),
        "sample_count": sample_count,
        "frame_sample_count": frame_sample_count,
        "degenerate_frame_count": degenerate_frame_count,
        "position_gap_mm": _round(position_gap),
        "tangent_angle_deg": _round(tangent_angle),
        "normal_angle_deg": _round(normal_angle),
        "normal_angle_kind": "adjacent_surface_uv_grid_frame",
        "curvature_proxy_mismatch": _round(curvature_mismatch),
        "curvature_proxy_kind": "adjacent_surface_uv_grid_cross_boundary_second_difference",
        "status": status,
        "measurement_strategy": "v1_0_4_shared_root_edge_uv_grid_frame_g2_measurement",
        "exact_g2_available": status == "G2_MEASURED",
    }


def _blade_hub_angle_samples(blade: dict[str, Any], root: dict[str, Any], edge: dict[str, Any]) -> list[dict[str, Any]]:
    blade_samples = _edge_samples(blade, edge["first_edge_role"])
    root_inner = _aligned_samples(blade_samples, _edge_samples(root, "blade_inner_loop"), edge)
    root_outer = _edge_samples(root, "hub_outer_loop")
    count = min(len(blade_samples), len(root_inner), len(root_outer))
    samples = []
    for index in range(count):
        blade_inward = _surface_inward_vector(blade, edge["first_edge_role"], blade_samples[index])
        root_to_hub = _sub(root_inner[index], root_outer[index])
        angle = _axis_angle_or_none(blade_inward, root_to_hub, bidirectional=True)
        sample_status = "PASS" if angle is not None else "FAIL"
        reason = None if angle is not None else "v1_0_4_blade_hub_angle_degenerate_vector"
        samples.append(
            {
                "interface": "blade_root_to_hub",
                "edge_id": edge.get("id"),
                "blade_face_id": blade["id"],
                "hub_face_id": root["id"],
                "blade_edge_role": edge["first_edge_role"],
                "hub_edge_role": "hub_outer_loop",
                "root_component_role": root.get("role"),
                "sample_index": index,
                "angle_deg": _round(angle) if angle is not None else None,
                "status": sample_status,
                "reason": reason,
                "blade_inward_vector_length_mm": _round(_length(blade_inward)),
                "root_to_hub_vector_length_mm": _round(_length(root_to_hub)),
                "measurement_strategy": "blade_root_inward_tangent_vs_root_component_hub_span",
            }
        )
    return samples


def _continuity_status(position_gap: float, tangent_angle: float, normal_angle: float, curvature_mismatch: float) -> str:
    if position_gap > POSITION_GAP_LIMIT_MM:
        return "G0_ONLY_FAILED"
    if tangent_angle > TANGENT_ANGLE_LIMIT_DEG:
        return "G1_MEASURED_G2_FAILED"
    if normal_angle > NORMAL_ANGLE_LIMIT_DEG or curvature_mismatch > CURVATURE_PROXY_LIMIT:
        return "G1_MEASURED_G2_FAILED"
    return "G2_MEASURED"


def _max_tangent_angle(first: list[list[float]], second: list[list[float]]) -> float:
    return max(
        (
            _axis_angle(_edge_tangent(first, index), _edge_tangent(second, index), bidirectional=True)
            for index in range(min(len(first), len(second)))
        ),
        default=180.0,
    )


def _curvature_proxy_mismatch(first: list[list[float]], second: list[list[float]]) -> float:
    mismatches = []
    for index in range(min(len(first), len(second))):
        first_curvature = _length(_second_difference(first, index))
        second_curvature = _length(_second_difference(second, index))
        denominator = max(first_curvature, second_curvature, 1.0e-9)
        mismatches.append(abs(first_curvature - second_curvature) / denominator)
    return max(mismatches) if mismatches else 1.0


def _edge_boundary_frames(
    surface: dict[str, Any],
    edge_role: str,
    aligned_samples: list[list[float]],
) -> list[dict[str, Any]]:
    grid = _surface_grid(surface)
    if grid is None or len(aligned_samples) < 2:
        return []

    candidate = _matched_grid_boundary(grid, aligned_samples)
    if candidate is None or candidate["max_gap_mm"] > POSITION_GAP_LIMIT_MM:
        return []

    frames = []
    boundary_points = candidate["points"]
    for index, point in enumerate(boundary_points):
        inward_point = _boundary_grid_point(grid, candidate, index, 1)
        tangent = _edge_tangent(boundary_points, index)
        inward = _sub(inward_point, point)
        normal = _cross(tangent, inward)
        curvature = _boundary_cross_curvature(grid, candidate, index)
        frames.append(
            {
                "surface_id": surface.get("id"),
                "edge_role": edge_role,
                "boundary": candidate["boundary"],
                "point": point,
                "tangent": tangent,
                "inward": inward,
                "normal": normal,
                "curvature": curvature,
            }
        )
    return frames


def _surface_grid(surface: dict[str, Any]) -> list[list[list[float]]] | None:
    grid = surface.get("uv_grid")
    if not isinstance(grid, list) or len(grid) < 2 or not isinstance(grid[0], list) or len(grid[0]) < 2:
        return None
    column_count = len(grid[0])
    normalized_grid = []
    for row in grid:
        if not isinstance(row, list) or len(row) != column_count:
            return None
        normalized_row = []
        for point in row:
            if not isinstance(point, list) or len(point) != 3:
                return None
            normalized_row.append([float(point[0]), float(point[1]), float(point[2])])
        normalized_grid.append(normalized_row)
    return normalized_grid


def _matched_grid_boundary(
    grid: list[list[list[float]]],
    aligned_samples: list[list[float]],
) -> dict[str, Any] | None:
    row_count = len(grid)
    column_count = len(grid[0])
    candidates = [
        ("row0", grid[0]),
        ("rowN", grid[-1]),
        ("col0", [row[0] for row in grid]),
        ("colN", [row[-1] for row in grid]),
    ]
    scored = []
    for boundary, points in candidates:
        if len(points) != len(aligned_samples):
            continue
        forward_gap = max(_distance(a, b) for a, b in zip(points, aligned_samples))
        reversed_points = list(reversed(points))
        reversed_gap = max(_distance(a, b) for a, b in zip(reversed_points, aligned_samples))
        if reversed_gap < forward_gap:
            scored.append(
                {
                    "boundary": boundary,
                    "reversed": True,
                    "points": reversed_points,
                    "max_gap_mm": reversed_gap,
                    "row_count": row_count,
                    "column_count": column_count,
                }
            )
        else:
            scored.append(
                {
                    "boundary": boundary,
                    "reversed": False,
                    "points": points,
                    "max_gap_mm": forward_gap,
                    "row_count": row_count,
                    "column_count": column_count,
                }
            )
    if not scored:
        return None
    return min(scored, key=lambda item: item["max_gap_mm"])


def _boundary_grid_point(
    grid: list[list[list[float]]],
    boundary: dict[str, Any],
    sample_index: int,
    inward_offset: int,
) -> list[float]:
    name = boundary["boundary"]
    reversed_boundary = bool(boundary["reversed"])
    row_count = boundary["row_count"]
    column_count = boundary["column_count"]
    if name == "row0":
        row_index = min(inward_offset, row_count - 1)
        column_index = column_count - 1 - sample_index if reversed_boundary else sample_index
    elif name == "rowN":
        row_index = max(row_count - 1 - inward_offset, 0)
        column_index = column_count - 1 - sample_index if reversed_boundary else sample_index
    elif name == "col0":
        row_index = row_count - 1 - sample_index if reversed_boundary else sample_index
        column_index = min(inward_offset, column_count - 1)
    else:
        row_index = row_count - 1 - sample_index if reversed_boundary else sample_index
        column_index = max(column_count - 1 - inward_offset, 0)
    return grid[row_index][column_index]


def _boundary_cross_curvature(
    grid: list[list[list[float]]],
    boundary: dict[str, Any],
    sample_index: int,
) -> list[float] | None:
    p0 = _boundary_grid_point(grid, boundary, sample_index, 0)
    p1 = _boundary_grid_point(grid, boundary, sample_index, 1)
    p2 = _boundary_grid_point(grid, boundary, sample_index, 2)
    span = _distance(p0, p1)
    if span <= 1.0e-9 or p1 == p2:
        return None
    return [
        (p2[axis] - 2.0 * p1[axis] + p0[axis]) / (span * span)
        for axis in range(3)
    ]


def _max_normal_angle(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float:
    count = min(len(first), len(second))
    if count == 0:
        return 180.0
    angles = []
    for first_frame, second_frame in zip(first[:count], second[:count]):
        if _length(first_frame["normal"]) <= 1.0e-9 or _length(second_frame["normal"]) <= 1.0e-9:
            angles.append(180.0)
        else:
            angles.append(_axis_angle(first_frame["normal"], second_frame["normal"], bidirectional=True))
    return max(angles) if angles else 180.0


def _surface_curvature_proxy_mismatch(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float:
    count = min(len(first), len(second))
    if count == 0:
        return 1.0
    mismatches = []
    for first_frame, second_frame in zip(first[:count], second[:count]):
        first_curvature = first_frame.get("curvature")
        second_curvature = second_frame.get("curvature")
        if first_curvature is None or second_curvature is None:
            mismatches.append(1.0)
            continue
        first_length = _length(first_curvature)
        second_length = _length(second_curvature)
        denominator = max(first_length, second_length, 1.0e-9)
        mismatches.append(abs(first_length - second_length) / denominator)
    return max(mismatches) if mismatches else 1.0


def _degenerate_frame_count(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> int:
    count = 0
    for frame in [*first, *second]:
        if (
            _length(frame.get("tangent", [])) <= 1.0e-9
            or _length(frame.get("inward", [])) <= 1.0e-9
            or _length(frame.get("normal", [])) <= 1.0e-9
            or frame.get("curvature") is None
        ):
            count += 1
    return count


def _surface_inward_vector(surface: dict[str, Any], edge_role: str, point: list[float]) -> list[float]:
    grid = surface.get("uv_grid", [])
    if len(grid) < 2 or not grid[0]:
        return [0.0, 0.0, 0.0]
    row, col = _closest_grid_index(grid, point)
    candidates = []
    if edge_role == "root" and row + 1 < len(grid):
        candidates.append(_sub(grid[row + 1][col], grid[row][col]))
    if edge_role == "tip" and row > 0:
        candidates.append(_sub(grid[row - 1][col], grid[row][col]))
    if edge_role in {"leading", "pressure"} and col + 1 < len(grid[row]):
        candidates.append(_sub(grid[row][col + 1], grid[row][col]))
    if edge_role in {"trailing", "suction"} and col > 0:
        candidates.append(_sub(grid[row][col - 1], grid[row][col]))
    if candidates:
        return _unit(candidates[0])
    return _nearest_nonzero_grid_vector(grid, row, col)


def _nearest_nonzero_grid_vector(grid: list[list[list[float]]], row: int, col: int) -> list[float]:
    point = grid[row][col]
    for drow, dcol in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        next_row = row + drow
        next_col = col + dcol
        if 0 <= next_row < len(grid) and 0 <= next_col < len(grid[next_row]):
            vector = _sub(grid[next_row][next_col], point)
            if _length(vector) > 1.0e-9:
                return _unit(vector)
    return [0.0, 0.0, 0.0]


def _closest_grid_index(grid: list[list[list[float]]], point: list[float]) -> tuple[int, int]:
    best = (math.inf, 0, 0)
    for row_index, row in enumerate(grid):
        for col_index, candidate in enumerate(row):
            gap = _distance(point, candidate)
            if gap < best[0]:
                best = (gap, row_index, col_index)
    return best[1], best[2]


def _aligned_samples(first: list[list[float]], second: list[list[float]], edge: dict[str, Any]) -> list[list[float]]:
    if edge.get("orientation") == "reversed":
        return list(reversed(second))
    if not first or not second:
        return second
    forward = _distance(first[0], second[0]) + _distance(first[-1], second[-1])
    reverse = _distance(first[0], second[-1]) + _distance(first[-1], second[0])
    return list(reversed(second)) if reverse < forward else second


def _edge_samples(surface: dict[str, Any], role: str) -> list[list[float]]:
    samples = surface.get("edge_samples", {}).get(role)
    if isinstance(samples, list):
        return [[float(point[0]), float(point[1]), float(point[2])] for point in samples if isinstance(point, list) and len(point) == 3]
    return []


def _edge_tangent(samples: list[list[float]], index: int) -> list[float]:
    if len(samples) < 2:
        return [0.0, 0.0, 0.0]
    previous_point = samples[max(index - 1, 0)]
    next_point = samples[min(index + 1, len(samples) - 1)]
    return _unit(_sub(next_point, previous_point))


def _second_difference(samples: list[list[float]], index: int) -> list[float]:
    previous_point = samples[max(index - 1, 0)]
    point = samples[index]
    next_point = samples[min(index + 1, len(samples) - 1)]
    return [
        next_point[axis] - 2.0 * point[axis] + previous_point[axis]
        for axis in range(3)
    ]


def _failed_edge(edge: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "edge_id": edge.get("id"),
        "first_face_id": edge.get("first_face_id"),
        "first_edge_role": edge.get("first_edge_role"),
        "second_face_id": edge.get("second_face_id"),
        "second_edge_role": edge.get("second_edge_role"),
        "orientation": edge.get("orientation"),
        "sample_count": 0,
        "frame_sample_count": 0,
        "degenerate_frame_count": 0,
        "position_gap_mm": 999.0,
        "tangent_angle_deg": 180.0,
        "normal_angle_deg": 180.0,
        "normal_angle_kind": "adjacent_surface_uv_grid_frame_unavailable",
        "curvature_proxy_mismatch": 1.0,
        "curvature_proxy_kind": "adjacent_surface_uv_grid_cross_boundary_second_difference",
        "status": "G0_ONLY_FAILED",
        "reason": reason,
        "measurement_strategy": "v1_0_4_shared_root_edge_uv_grid_frame_g2_measurement",
        "exact_g2_available": False,
    }


def _reversed_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(edge),
        "first_face_id": edge.get("second_face_id"),
        "first_edge_role": edge.get("second_edge_role"),
        "second_face_id": edge.get("first_face_id"),
        "second_edge_role": edge.get("first_edge_role"),
    }


def _is_blade_face(surface: dict[str, Any] | None) -> bool:
    return bool(surface and surface.get("face_family") in {"blade_pressure", "blade_suction", "blade_leading_edge", "blade_trailing_edge"})


def _is_v10_4_root_component(surface: dict[str, Any] | None) -> bool:
    return bool(
        surface
        and surface.get("geometry_patch_version") == "1.0.4"
        and surface.get("face_family") == "blade_root"
        and surface.get("component_of")
    )


def _axis_angle(first: list[float], second: list[float], *, bidirectional: bool) -> float:
    angle = _axis_angle_or_none(first, second, bidirectional=bidirectional)
    return angle if angle is not None else 180.0


def _axis_angle_or_none(first: list[float], second: list[float], *, bidirectional: bool) -> float | None:
    if _length(first) <= 1.0e-9 or _length(second) <= 1.0e-9:
        return None
    left = _unit(first)
    right = _unit(second)
    dot = sum(a * b for a, b in zip(left, right))
    if bidirectional:
        dot = abs(dot)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _distance(first: list[float], second: list[float]) -> float:
    return _length(_sub(first, second))


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _sub(first: list[float], second: list[float]) -> list[float]:
    return [float(left) - float(right) for left, right in zip(first, second)]


def _cross(first: list[float], second: list[float]) -> list[float]:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _unit(vector: list[float]) -> list[float]:
    length = _length(vector)
    if length <= 1.0e-9:
        return [0.0, 0.0, 0.0]
    return [float(value) / length for value in vector]


def _finite_float(*values: Any, default: float) -> float:
    for value in values:
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(result):
            return result
    return default


def _round(value: float) -> float:
    return round(float(value), 9)
