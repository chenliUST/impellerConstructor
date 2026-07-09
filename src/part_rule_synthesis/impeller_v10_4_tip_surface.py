from __future__ import annotations

import copy
import math
from typing import Any


def upgrade_tip_surface_contract(
    tip_surface: dict[str, Any],
    *,
    area_ratio_limit: float = 1.15,
) -> dict[str, Any]:
    tip = copy.deepcopy(tip_surface)
    boundary = tip.get("edge_samples", {}).get("tip_section_loop") or []
    grid = tip.get("uv_grid") or []
    boundary_gap = _max_loop_gap(grid[0] if grid else [], boundary)
    basis = _domain_basis(boundary, grid)
    boundary_2d = _project_points(boundary, basis)
    initial_outside_count = _outside_loop_count(grid, boundary_2d, basis)
    if initial_outside_count and _can_rebuild_bounded_grid(tip, boundary, grid, boundary_gap):
        repaired_grid = _bounded_grid(boundary, grid, boundary_2d, basis)
        if _outside_loop_count(repaired_grid, boundary_2d, basis) == 0:
            tip["uv_grid"] = repaired_grid
            tip.setdefault("edge_samples", {})["tip_crest_curve"] = copy.deepcopy(repaired_grid[-1])
            if "control_net" in tip:
                tip["control_net"] = _control_net(repaired_grid)
            grid = repaired_grid

    boundary_area = abs(_area_2d(boundary_2d))
    max_row_area = max(
        [abs(_area_2d(_project_points(row, basis))) for row in grid if len(row) >= 3]
        or [0.0]
    )
    ratio = max_row_area / max(boundary_area, 1.0e-9)
    outside_count = _outside_loop_count(grid, boundary_2d, basis)
    foldover = int(tip.get("transition_quality", {}).get("foldover_count") or 0)
    status = (
        "PASS"
        if boundary_gap <= 1.0e-6
        and ratio <= area_ratio_limit
        and outside_count == 0
        and foldover == 0
        else "FAIL"
    )
    tip["v1_0_4_tip_quality"] = {
        "status": status,
        "reason": None
        if status == "PASS"
        else _reason(boundary_gap, ratio, area_ratio_limit, outside_count, foldover),
        "tip_boundary_gap_mm": round(boundary_gap, 9),
        "tip_area_ratio": round(ratio, 9),
        "tip_area_ratio_limit": area_ratio_limit,
        "outside_loop_sample_count": outside_count,
        "foldover_count": foldover,
    }
    tip["geometry_patch_version"] = "1.0.4"
    return tip


def build_v10_4_tip_surface(
    tip_surface: dict[str, Any],
    *,
    area_ratio_limit: float = 1.15,
) -> dict[str, Any]:
    return upgrade_tip_surface_contract(tip_surface, area_ratio_limit=area_ratio_limit)


def _reason(
    boundary_gap: float,
    ratio: float,
    limit: float,
    outside_count: int,
    foldover: int,
) -> str:
    if boundary_gap > 1.0e-6:
        return "v1_0_4_tip_boundary_mismatch"
    if ratio > limit:
        return "v1_0_4_tip_area_exceeds_limit"
    if outside_count:
        return "v1_0_4_tip_exceeds_loop_domain"
    if foldover:
        return "v1_0_4_tip_foldover"
    return "v1_0_4_tip_contract_failed"


def _can_rebuild_bounded_grid(
    tip: dict[str, Any],
    boundary: list[list[float]],
    grid: list[list[list[float]]],
    boundary_gap: float,
) -> bool:
    quality = tip.get("tip_dome_quality", {})
    return (
        quality.get("status") == "PASS"
        and bool(quality.get("tip_dome_contraction_rule"))
        and boundary_gap <= 1.0e-6
        and len(boundary) >= 4
        and len(grid) >= 3
        and all(len(row) == len(boundary) for row in grid)
        and len(tip.get("edge_samples", {}).get("tip_crest_curve") or []) == len(boundary)
    )


def _bounded_grid(
    boundary: list[list[float]],
    grid: list[list[list[float]]],
    boundary_2d: list[list[float]],
    basis: dict[str, list[float]],
) -> list[list[list[float]]]:
    loop = _open_2d_loop(boundary_2d)
    edges = _loop_edges(loop)
    bounds = _loop_bounds(loop)
    anchor = _interior_anchor_2d(loop, edges, bounds)
    if anchor is None:
        return grid

    row_count = len(grid)
    normal = _normalized(_cross(basis["u_axis"], basis["v_axis"])) or [0.0, 0.0, 1.0]
    repaired: list[list[list[float]]] = [copy.deepcopy(boundary)]
    for row_index, row in enumerate(grid[1:], start=1):
        fraction = row_index / (row_count - 1)
        repaired_row = []
        row_2d = _project_points(row, basis)
        for column_index, point in enumerate(row):
            boundary_point = boundary[column_index]
            boundary_point_2d = boundary_2d[column_index]
            target_2d = _bounded_point_2d(
                row_2d[column_index],
                boundary_point_2d,
                anchor,
                edges,
                bounds,
                fraction,
            )
            height = _dot(_subtract(point, boundary_point), normal)
            offset = _add(
                _scale(basis["u_axis"], target_2d[0] - boundary_point_2d[0]),
                _scale(basis["v_axis"], target_2d[1] - boundary_point_2d[1]),
            )
            repaired_row.append(_add(_add(boundary_point, offset), _scale(normal, height)))
        repaired_row[-1] = copy.deepcopy(repaired_row[0])
        repaired.append(repaired_row)
    return repaired


def _bounded_point_2d(
    point: list[float],
    boundary_point: list[float],
    anchor: list[float],
    edges: list[tuple[list[float], list[float]]],
    bounds: tuple[float, float, float, float],
    fraction: float,
) -> list[float]:
    if _point_inside_or_on_loop_edges(point, edges, bounds, tolerance=1.0e-6):
        return point

    base_fraction = max(0.0, min(0.92, 0.92 * fraction))
    for scale in [1.0, 0.75, 0.5, 0.25, 0.1, 0.02, 0.0]:
        step = base_fraction * scale
        candidate = [
            float(boundary_point[0]) + (float(anchor[0]) - float(boundary_point[0])) * step,
            float(boundary_point[1]) + (float(anchor[1]) - float(boundary_point[1])) * step,
        ]
        if _point_inside_or_on_loop_edges(candidate, edges, bounds, tolerance=1.0e-6):
            return candidate
    return boundary_point


def _interior_anchor_2d(
    loop: list[list[float]],
    edges: list[tuple[list[float], list[float]]],
    bounds: tuple[float, float, float, float],
) -> list[float] | None:
    if len(loop) < 3:
        return None
    min_x, max_x, min_y, max_y = bounds
    if max_x <= min_x or max_y <= min_y:
        return None

    xs = [float(point[0]) for point in loop]
    ys = [float(point[1]) for point in loop]
    candidates = [[sum(xs) / len(xs), sum(ys) / len(ys)]]
    steps = 31
    for x_index in range(steps):
        x = min_x + (max_x - min_x) * (x_index + 0.5) / steps
        for y_index in range(steps):
            y = min_y + (max_y - min_y) * (y_index + 0.5) / steps
            candidates.append([x, y])

    best_point: list[float] | None = None
    best_distance = -math.inf
    for candidate in candidates:
        if not _point_inside_or_on_loop_edges(candidate, edges, bounds, tolerance=1.0e-6):
            continue
        distance = _distance_to_loop_edges(candidate, edges)
        if distance > best_distance:
            best_distance = distance
            best_point = candidate
    return best_point


def _distance_to_loop_edges(point: list[float], edges: list[tuple[list[float], list[float]]]) -> float:
    return min(_distance_to_2d_segment(point, left, right) for left, right in edges)


def _distance_to_2d_segment(point: list[float], left: list[float], right: list[float]) -> float:
    segment_x = float(right[0]) - float(left[0])
    segment_y = float(right[1]) - float(left[1])
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared <= 1.0e-18:
        return _distance_2d(point, left)
    t = (
        (float(point[0]) - float(left[0])) * segment_x
        + (float(point[1]) - float(left[1])) * segment_y
    ) / length_squared
    t = max(0.0, min(1.0, t))
    projection = [float(left[0]) + t * segment_x, float(left[1]) + t * segment_y]
    return _distance_2d(point, projection)


def _max_loop_gap(left: list[list[float]], right: list[list[float]]) -> float:
    if not left or not right or len(left) != len(right):
        return math.inf
    return max(_distance(a, b) for a, b in zip(left, right))


def _distance(left: list[float], right: list[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)) ** 0.5


def _area_2d(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    closed = points if points[0] == points[-1] else [*points, points[0]]
    for left, right in zip(closed, closed[1:]):
        area += float(left[0]) * float(right[1]) - float(right[0]) * float(left[1])
    return 0.5 * area


def _outside_loop_count(
    grid: list[list[list[float]]],
    boundary_2d: list[list[float]],
    basis: dict[str, list[float]],
) -> int:
    if len(boundary_2d) < 3:
        return 1
    loop = _open_2d_loop(boundary_2d)
    if len(loop) < 3:
        return 1
    edges = _loop_edges(loop)
    bounds = _loop_bounds(loop)
    count = 0
    for row in grid:
        for point in _project_points(row, basis):
            if not _point_inside_or_on_loop_edges(point, edges, bounds, tolerance=1.0e-6):
                count += 1
    return count


def _open_2d_loop(points: list[list[float]]) -> list[list[float]]:
    if len(points) >= 2 and _distance_2d(points[0], points[-1]) <= 1.0e-9:
        return points[:-1]
    return points


def _point_inside_or_on_loop(
    point: list[float],
    loop: list[list[float]],
    *,
    tolerance: float,
) -> bool:
    return _point_inside_or_on_loop_edges(point, _loop_edges(loop), _loop_bounds(loop), tolerance=tolerance)


def _point_inside_or_on_loop_edges(
    point: list[float],
    edges: list[tuple[list[float], list[float]]],
    bounds: tuple[float, float, float, float],
    *,
    tolerance: float,
) -> bool:
    min_x, max_x, min_y, max_y = bounds
    if (
        float(point[0]) < min_x - tolerance
        or float(point[0]) > max_x + tolerance
        or float(point[1]) < min_y - tolerance
        or float(point[1]) > max_y + tolerance
    ):
        return False
    if any(_point_on_2d_segment(point, left, right, tolerance) for left, right in edges):
        return True

    x = float(point[0])
    y = float(point[1])
    inside = False
    for left, right in edges:
        left_y = float(left[1])
        right_y = float(right[1])
        if (left_y > y) == (right_y > y):
            continue
        left_x = float(left[0])
        right_x = float(right[0])
        x_intersection = left_x + (y - left_y) * (right_x - left_x) / (right_y - left_y)
        if x < x_intersection:
            inside = not inside
    return inside


def _loop_edges(loop: list[list[float]]) -> list[tuple[list[float], list[float]]]:
    return list(zip(loop, [*loop[1:], loop[0]]))


def _loop_bounds(loop: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in loop]
    ys = [float(point[1]) for point in loop]
    return min(xs), max(xs), min(ys), max(ys)


def _point_on_2d_segment(
    point: list[float],
    left: list[float],
    right: list[float],
    tolerance: float,
) -> bool:
    segment_x = float(right[0]) - float(left[0])
    segment_y = float(right[1]) - float(left[1])
    point_x = float(point[0]) - float(left[0])
    point_y = float(point[1]) - float(left[1])
    segment_length = math.hypot(segment_x, segment_y)
    if segment_length <= tolerance:
        return _distance_2d(point, left) <= tolerance
    cross = point_x * segment_y - point_y * segment_x
    if abs(cross) > tolerance * segment_length:
        return False
    dot = point_x * segment_x + point_y * segment_y
    return -tolerance * segment_length <= dot <= segment_length * segment_length + tolerance * segment_length


def _distance_2d(left: list[float], right: list[float]) -> float:
    return math.hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1]))


def _domain_basis(points: list[list[float]], grid: list[list[list[float]]]) -> dict[str, list[float]]:
    origin = copy.deepcopy(points[0]) if points else [0.0, 0.0, 0.0]
    normal = _dome_lift_direction(points, grid) or _normalized(_newell_normal(points)) or [0.0, 0.0, 1.0]
    u_axis = _first_nonzero_edge(points) or [1.0, 0.0, 0.0]
    u_axis = _normalized(_subtract(u_axis, _scale(normal, _dot(u_axis, normal)))) or [1.0, 0.0, 0.0]
    v_axis = _normalized(_cross(normal, u_axis)) or [0.0, 1.0, 0.0]
    return {"origin": origin, "u_axis": u_axis, "v_axis": v_axis}


def _dome_lift_direction(
    boundary: list[list[float]],
    grid: list[list[list[float]]],
) -> list[float] | None:
    if len(boundary) < 3 or len(grid) < 2 or not grid[-1]:
        return None
    return _normalized(_subtract(_centroid(grid[-1]), _centroid(boundary)))


def _project_points(points: list[list[float]], basis: dict[str, list[float]]) -> list[list[float]]:
    origin = basis["origin"]
    u_axis = basis["u_axis"]
    v_axis = basis["v_axis"]
    return [
        [
            _dot(_subtract(point, origin), u_axis),
            _dot(_subtract(point, origin), v_axis),
        ]
        for point in points
    ]


def _newell_normal(points: list[list[float]]) -> list[float]:
    normal = [0.0, 0.0, 0.0]
    if len(points) < 3:
        return normal
    closed = points if points[0] == points[-1] else [*points, points[0]]
    for left, right in zip(closed, closed[1:]):
        normal[0] += (left[1] - right[1]) * (left[2] + right[2])
        normal[1] += (left[2] - right[2]) * (left[0] + right[0])
        normal[2] += (left[0] - right[0]) * (left[1] + right[1])
    return normal


def _centroid(points: list[list[float]]) -> list[float]:
    open_points = points[:-1] if points and points[0] == points[-1] else points
    count = max(len(open_points), 1)
    return [
        sum(float(point[axis]) for point in open_points) / count
        for axis in range(3)
    ]


def _first_nonzero_edge(points: list[list[float]]) -> list[float] | None:
    for left, right in zip(points, points[1:]):
        edge = _subtract(right, left)
        if _length(edge) > 1.0e-9:
            return edge
    return None


def _subtract(left: list[float], right: list[float]) -> list[float]:
    return [float(a) - float(b) for a, b in zip(left, right)]


def _scale(vector: list[float], scalar: float) -> list[float]:
    return [float(value) * float(scalar) for value in vector]


def _add(left: list[float], right: list[float]) -> list[float]:
    return [float(a) + float(b) for a, b in zip(left, right)]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _normalized(vector: list[float]) -> list[float] | None:
    length = _length(vector)
    if length <= 1.0e-9:
        return None
    return [float(value) / length for value in vector]


def _control_net(uv_grid: list[list[list[float]]]) -> list[list[list[float]]]:
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy([[uv_grid[row][column] for column in column_indices] for row in row_indices])


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    return list(dict.fromkeys([0, count // 2, count - 1]))
