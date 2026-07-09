from __future__ import annotations

import copy
import math
from typing import Any


Point2 = list[float]
Point3 = list[float]

SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
DISPLAY = {
    "inspection_class": "open_tip_dome",
    "color": "#21c7ff",
    "wire_color": "#073447",
    "visible_by_default": True,
}
MESH_STRATEGY = "section_loop_shared_edge_review_grade_quad_mesh"
MAX_SHORT_DIRECTION_SAMPLE_COUNT = 65
MAX_BOUNDARY_SAMPLE_COUNT = 256
_EPSILON = 1.0e-9


def build_v10_3_tip_dome(*, blade_index: int, lattice: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    surface_id = f"blade_{blade_index}_tip_dome_surface"
    base = _base_surface(surface_id)
    validation = _validate_inputs(blade_index=blade_index, lattice=lattice, defaults=defaults)
    if validation["status"] == "FAIL":
        return _failure(base, validation["reason"], validation)

    boundary_loop = validation["boundary_loop"]
    lift_direction = validation["lift_direction"]
    height_mm = validation["height_mm"]
    sample_count = validation["sample_count"]

    dome_grid = _stable_dome_grid(
        boundary_loop=boundary_loop,
        lift_direction=lift_direction,
        height_mm=height_mm,
        sample_count=sample_count,
    )
    uv_grid = dome_grid["uv_grid"]
    foldover_count = _grid_foldover_count(uv_grid)
    min_signed_height = _min_signed_height(uv_grid, boundary_loop, lift_direction)
    boundary_gap = _max_loop_gap(uv_grid[0], boundary_loop)
    material_side_valid = min_signed_height > 0.0 and validation["material_side_valid"]

    quality = {
        "status": "PASS",
        "reason": None,
        "tip_dome_boundary_gap_mm": boundary_gap,
        "requested_tip_dome_height_mm": _round(height_mm),
        "min_signed_dome_height_mm": _round(min_signed_height),
        "tip_dome_foldover_count": foldover_count,
        "foldover_count": foldover_count,
        "tip_dome_material_side_valid": material_side_valid,
        "height_to_average_thickness_ratio": _round(height_mm / validation["average_thickness_mm"]),
        "short_direction_sample_count": sample_count,
        "boundary_sample_count": len(boundary_loop),
        "crest_sample_count": len(uv_grid[-1]),
        "tip_dome_contraction_factor": dome_grid["contraction_factor"],
        "tip_dome_contraction_rule": dome_grid["contraction_rule"],
        "source_loop_id": validation["source_loop_id"],
        "source_segment_order": copy.deepcopy(SEGMENT_ORDER),
    }
    gate_reason = _quality_gate_failure(quality)
    if gate_reason is not None:
        quality["status"] = "FAIL"
        quality["reason"] = gate_reason
        return _failure(base, gate_reason, quality)

    base.update(
        {
            "status": "PASS",
            "blade_index": blade_index,
            "blade_class": validation["blade_class"],
            "blade_pair_index": validation["blade_pair_index"],
            "uv_grid": copy.deepcopy(uv_grid),
            "control_net": _control_net(uv_grid),
            "edge_samples": {
                "tip_section_loop": copy.deepcopy(boundary_loop),
                "tip_crest_curve": copy.deepcopy(uv_grid[-1]),
            },
            "wireframe": {"enabled": True, "source": "uv_grid"},
            "mesh": _quad_mesh(uv_grid),
            "display": copy.deepcopy(DISPLAY),
            "source": {
                "section_loop_family_id": validation["section_loop_family_id"],
                "section_loop_source": validation["section_loop_source"],
                "source_loop_id": validation["source_loop_id"],
                "segment_source": "section_loop_segments",
                "segment_order": copy.deepcopy(SEGMENT_ORDER),
                "boundary_loop": "blade_tip_section_loop",
            },
            "tip_dome_quality": quality,
            "transition_quality": {
                "continuity_claim": "G1_TARGET_REVIEW_GRADE_OPEN_TIP_DOME",
                "curvature_claim": "REVIEW_GRADE_CURVED_DOME_SAMPLE_GRID",
                "foldover_count": foldover_count,
                "tip_dome_material_side_valid": material_side_valid,
                "source_loop_id": validation["source_loop_id"],
            },
        }
    )
    return copy.deepcopy(base)


def _validate_inputs(*, blade_index: int, lattice: Any, defaults: Any) -> dict[str, Any]:
    if not isinstance(lattice, dict):
        return _fail("v1_0_3_tip_section_lattice_malformed")
    if lattice.get("status") != "PASS":
        return _fail("v1_0_3_tip_section_lattice_failed")
    if not isinstance(defaults, dict):
        return _fail("v1_0_3_tip_dome_height_invalid")

    height_mm = _positive_float(defaults.get("tip_dome_height_mm"))
    if height_mm is None:
        return _fail("v1_0_3_tip_dome_height_invalid")
    average_thickness_mm = _positive_float(defaults.get("average_blade_thickness_mm"))
    if average_thickness_mm is None:
        return _fail("v1_0_3_tip_dome_height_invalid")
    sample_count = defaults.get("tip_dome_short_direction_sample_count", 17)
    if type(sample_count) is not int or sample_count < 3 or sample_count > MAX_SHORT_DIRECTION_SAMPLE_COUNT:
        return _fail("v1_0_3_tip_dome_sample_count_invalid")

    blades = lattice.get("blades")
    if type(blade_index) is not int or blade_index < 0:
        return _fail("v1_0_3_tip_blade_missing")
    if not isinstance(blades, list) or blade_index < 0 or blade_index >= len(blades):
        return _fail("v1_0_3_tip_blade_missing")
    blade = blades[blade_index]
    if not isinstance(blade, dict):
        return _fail("v1_0_3_tip_blade_missing")
    loops = blade.get("section_loops")
    if not isinstance(loops, list) or not loops:
        return _fail("v1_0_3_tip_section_loop_malformed")

    tip_loop = loops[-1]
    if not isinstance(tip_loop, dict):
        return _fail("v1_0_3_tip_section_loop_malformed")
    segments = tip_loop.get("segments")
    if not isinstance(segments, dict):
        return _fail("v1_0_3_tip_section_loop_malformed")

    segment_points: dict[str, list[Point3]] = {}
    for segment_name in SEGMENT_ORDER:
        segment = segments.get(segment_name)
        points = segment.get("points") if isinstance(segment, dict) else None
        if not isinstance(points, list) or len(points) < 2:
            return _fail("v1_0_3_tip_section_loop_malformed")
        normalized_points = [_point3(point) for point in points]
        if any(point is None for point in normalized_points):
            return _fail("v1_0_3_tip_section_loop_malformed")
        segment_points[segment_name] = [point for point in normalized_points if point is not None]

    if _validate_segment_continuity(segment_points)["status"] == "FAIL":
        return _fail("v1_0_3_tip_section_loop_malformed")
    boundary_loop = _stitch_tip_loop(segment_points)
    if len(boundary_loop) > MAX_BOUNDARY_SAMPLE_COUNT:
        return _fail(
            "v1_0_3_tip_dome_boundary_sample_count_exceeded",
            boundary_sample_count=len(boundary_loop),
            boundary_sample_count_limit=MAX_BOUNDARY_SAMPLE_COUNT,
        )
    declared_loop = tip_loop.get("closed_loop_points")
    if declared_loop is not None:
        normalized_declared = _point_loop(declared_loop)
        if normalized_declared is None or normalized_declared != boundary_loop:
            return _fail("v1_0_3_tip_section_loop_malformed")

    frame = tip_loop.get("coordinate_frame")
    if not isinstance(frame, dict):
        return _fail("v1_0_3_tip_section_loop_malformed")
    lift_direction = _point3(frame.get("material_normal"))
    span_tangent = _point3(frame.get("span_tangent"))
    if lift_direction is None or span_tangent is None:
        return _fail("v1_0_3_tip_section_loop_malformed")
    unit_lift = _normalized(lift_direction)
    if unit_lift is None or _dot(unit_lift, span_tangent) <= 0.0:
        return _fail("v1_0_3_tip_material_side_ambiguous")
    boundary_foldover_count = _loop_self_intersection_count(boundary_loop, unit_lift)
    if boundary_foldover_count > 0:
        return _fail(
            "v1_0_3_tip_dome_foldover",
            boundary_foldover_count=boundary_foldover_count,
        )

    return {
        "status": "PASS",
        "height_mm": height_mm,
        "average_thickness_mm": average_thickness_mm,
        "sample_count": sample_count,
        "boundary_loop": copy.deepcopy(boundary_loop),
        "lift_direction": unit_lift,
        "material_side_valid": True,
        "blade_class": blade.get("blade_class"),
        "blade_pair_index": blade.get("blade_pair_index"),
        "section_loop_family_id": blade.get("section_loop_family_id", tip_loop.get("section_loop_family_id")),
        "section_loop_source": _section_loop_source(blade, tip_loop),
        "source_loop_id": _loop_id(tip_loop),
    }


def _stable_dome_grid(
    *,
    boundary_loop: list[Point3],
    lift_direction: Point3,
    height_mm: float,
    sample_count: int,
) -> dict[str, Any]:
    candidates = [0.42, 0.30, 0.20, 0.10, 0.02, 0.0]
    last_grid: list[list[Point3]] = []
    for contraction_factor in candidates:
        uv_grid = _dome_grid(
            boundary_loop=boundary_loop,
            lift_direction=lift_direction,
            height_mm=height_mm,
            sample_count=sample_count,
            contraction_factor=contraction_factor,
        )
        last_grid = uv_grid
        if _grid_foldover_count(uv_grid) == 0:
            return {
                "uv_grid": uv_grid,
                "contraction_factor": contraction_factor,
                "contraction_rule": "largest_nonfolding_contraction_candidate",
            }
    return {
        "uv_grid": last_grid,
        "contraction_factor": candidates[-1],
        "contraction_rule": "all_contraction_candidates_folded",
    }


def _dome_grid(
    *,
    boundary_loop: list[Point3],
    lift_direction: Point3,
    height_mm: float,
    sample_count: int,
    contraction_factor: float = 0.42,
) -> list[list[Point3]]:
    centroid = _centroid(boundary_loop)
    grid: list[list[Point3]] = []
    for row_index in range(sample_count):
        fraction = row_index / (sample_count - 1)
        lift = height_mm * math.sin(0.5 * math.pi * fraction)
        contraction = contraction_factor * (1.0 - math.cos(0.5 * math.pi * fraction))
        row: list[Point3] = []
        for point in boundary_loop:
            radial = _subtract(point, centroid)
            radial_in_lift = _scale(lift_direction, _dot(radial, lift_direction))
            planar_radial = _subtract(radial, radial_in_lift)
            lifted = _add(point, _scale(lift_direction, lift))
            domed = _subtract(lifted, _scale(planar_radial, contraction))
            row.append(_round_vector(domed))
        row[-1] = copy.deepcopy(row[0])
        grid.append(row)
    grid[0] = copy.deepcopy(boundary_loop)
    return grid


def _section_loop_source(blade: dict[str, Any], tip_loop: dict[str, Any]) -> str:
    blade_source = blade.get("source")
    if isinstance(blade_source, str):
        return blade_source
    loop_source = tip_loop.get("source")
    if loop_source == "v1_0_3_nurbs_carrier_section_loop":
        return "v1_0_3_nurbs_carrier_section_lattice"
    if isinstance(loop_source, str):
        return loop_source
    return "v1_0_3_section_lattice"


def _stitch_tip_loop(segment_points: dict[str, list[Point3]]) -> list[Point3]:
    stitched: list[Point3] = []
    for segment_name in SEGMENT_ORDER:
        points = segment_points[segment_name]
        for point_index, point in enumerate(points):
            if stitched and point_index == 0 and _distance(stitched[-1], point) <= 1.0e-9:
                continue
            stitched.append(copy.deepcopy(point))
    if stitched and _distance(stitched[0], stitched[-1]) > 1.0e-9:
        stitched.append(copy.deepcopy(stitched[0]))
    else:
        stitched[-1] = copy.deepcopy(stitched[0])
    return stitched


def _validate_segment_continuity(segment_points: dict[str, list[Point3]]) -> dict[str, Any]:
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left = segment_points[left_name]
        right = segment_points[right_name]
        if _distance(left[-1], right[0]) <= 1.0e-6:
            continue
        return _fail("v1_0_3_tip_section_loop_malformed")
    return {"status": "PASS"}


def _grid_foldover_count(uv_grid: list[list[Point3]]) -> int:
    if len(uv_grid) < 2 or not uv_grid[0] or len(uv_grid[0]) < 4:
        return 1
    row_length = len(uv_grid[0])
    if any(len(row) != row_length for row in uv_grid):
        return 1

    count = 0
    for row_index in range(len(uv_grid) - 1):
        for column_index in range(row_length - 1):
            quad = [
                uv_grid[row_index][column_index],
                uv_grid[row_index + 1][column_index],
                uv_grid[row_index + 1][column_index + 1],
                uv_grid[row_index][column_index + 1],
            ]
            if _cell_foldover(quad):
                count += 1
    return count


def _loop_self_intersection_count(points: list[Point3], lift_direction: Point3) -> int:
    projected = _project_loop_to_2d(points, lift_direction)
    if len(projected) < 4:
        return 1
    count = 0
    open_projected = projected[:-1] if _points_close_2d(projected[0], projected[-1]) else projected
    for first_index, first_point in enumerate(open_projected):
        for second_index, second_point in enumerate(open_projected[first_index + 1 :], start=first_index + 1):
            if _points_close_2d(first_point, second_point):
                count += 1
    edges = list(zip(projected, projected[1:]))
    for first_index, first_edge in enumerate(edges):
        for second_index, second_edge in enumerate(edges[first_index + 1 :], start=first_index + 1):
            if abs(first_index - second_index) <= 1:
                continue
            if first_index == 0 and second_index == len(edges) - 1:
                continue
            if _segments_intersect_or_touch(first_edge[0], first_edge[1], second_edge[0], second_edge[1]):
                count += 1
    return count


def _project_loop_to_2d(points: list[Point3], lift_direction: Point3) -> list[Point2]:
    closed_points = points if points and points[0] == points[-1] else points + [copy.deepcopy(points[0])]
    origin = closed_points[0]
    u_axis = _first_nonzero_vector(
        [
            _subtract(right, left)
            for left, right in zip(closed_points, closed_points[1:])
        ]
    )
    if u_axis is None:
        return []
    v_axis = _normalized(_cross(lift_direction, u_axis))
    if v_axis is None:
        v_axis = _fallback_perpendicular(u_axis)
    return [
        [
            _dot(_subtract(point, origin), u_axis),
            _dot(_subtract(point, origin), v_axis),
        ]
        for point in closed_points
    ]


def _cell_foldover(quad: list[Point3]) -> bool:
    projected = _project_cell_to_2d(quad)
    edge_lengths = [
        _distance_2d(left, right)
        for left, right in zip(projected, projected[1:] + projected[:1])
    ]
    scale = max(edge_lengths) if edge_lengths else 1.0
    if min(edge_lengths) <= max(1.0e-9, 1.0e-8 * scale):
        return True
    if (
        _segments_intersect(projected[0], projected[1], projected[2], projected[3])
        or _segments_intersect(projected[1], projected[2], projected[3], projected[0])
    ):
        return True
    areas = [
        _triangle_signed_area(projected[0], projected[1], projected[2]),
        _triangle_signed_area(projected[0], projected[2], projected[3]),
    ]
    return any(abs(area) <= max(1.0e-9, 1.0e-8 * scale * scale) for area in areas)


def _project_cell_to_2d(quad: list[Point3]) -> list[Point2]:
    origin = quad[0]
    u_axis = _first_nonzero_vector(
        [
            _subtract(quad[3], quad[0]),
            _subtract(quad[2], quad[1]),
            _subtract(quad[1], quad[0]),
        ]
    ) or [1.0, 0.0, 0.0]
    v_seed = _first_nonzero_vector(
        [
            _subtract(quad[1], quad[0]),
            _subtract(quad[2], quad[3]),
            _fallback_perpendicular(u_axis),
        ]
    ) or _fallback_perpendicular(u_axis)
    v_axis = _subtract(v_seed, _scale(u_axis, _dot(v_seed, u_axis)))
    v_axis = _normalized(v_axis) or _fallback_perpendicular(u_axis)
    return [
        [
            _dot(_subtract(point, origin), u_axis),
            _dot(_subtract(point, origin), v_axis),
        ]
        for point in quad
    ]


def _quad_mesh(uv_grid: list[list[Point3]]) -> dict[str, Any]:
    if not uv_grid:
        return {
            "strategy": MESH_STRATEGY,
            "u_count": 0,
            "v_count": 0,
            "quad_count": 0,
            "quads": [],
        }
    quads = []
    for row_index in range(len(uv_grid) - 1):
        for column_index in range(len(uv_grid[row_index]) - 1):
            quads.append(
                {
                    "indices": [
                        [row_index, column_index],
                        [row_index + 1, column_index],
                        [row_index + 1, column_index + 1],
                        [row_index, column_index + 1],
                    ]
                }
            )
    return {
        "strategy": MESH_STRATEGY,
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]),
        "quad_count": len(quads),
        "quads": quads,
    }


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    if not uv_grid:
        return []
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy([[uv_grid[row][column] for column in column_indices] for row in row_indices])


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    return list(dict.fromkeys([0, count // 2, count - 1]))


def _quality_gate_failure(quality: dict[str, Any]) -> str | None:
    if quality["tip_dome_boundary_gap_mm"] > 1.0e-6:
        return "v1_0_3_tip_dome_boundary_gap"
    if quality["min_signed_dome_height_mm"] <= 0.0:
        return "v1_0_3_tip_dome_material_side_failed"
    if quality["tip_dome_foldover_count"] != 0:
        return "v1_0_3_tip_dome_foldover"
    if not quality["tip_dome_material_side_valid"]:
        return "v1_0_3_tip_dome_material_side_failed"
    return None


def _base_surface(surface_id: str) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": "blade_tip",
        "role": "open_tip_dome",
        "uv_grid": [],
        "control_net": [],
        "edge_samples": {"tip_section_loop": [], "tip_crest_curve": []},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh([]),
        "display": copy.deepcopy(DISPLAY),
        "tip_dome_quality": {},
        "transition_quality": {
            "continuity_claim": "G1_TARGET_REVIEW_GRADE_OPEN_TIP_DOME",
            "curvature_claim": "REVIEW_GRADE_CURVED_DOME_SAMPLE_GRID",
            "foldover_count": 0,
        },
    }


def _failure(base: dict[str, Any], reason: str, details: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    result["status"] = "FAIL"
    quality = copy.deepcopy(details)
    quality["status"] = "FAIL"
    quality["reason"] = reason
    result["tip_dome_quality"] = quality
    return result


def _min_signed_height(uv_grid: list[list[Point3]], boundary_loop: list[Point3], lift_direction: Point3) -> float:
    heights = [
        _dot(_subtract(point, boundary), lift_direction)
        for row in uv_grid[1:]
        for point, boundary in zip(row, boundary_loop)
    ]
    return min(heights) if heights else -math.inf


def _max_loop_gap(left: list[Point3], right: list[Point3]) -> float:
    if len(left) != len(right) or not left:
        return math.inf
    return _round(max(_distance(left_point, right_point) for left_point, right_point in zip(left, right)))


def _centroid(points: list[Point3]) -> Point3:
    open_points = points[:-1] if points and points[0] == points[-1] else points
    return [
        sum(point[axis] for point in open_points) / len(open_points)
        for axis in range(3)
    ]


def _point_loop(points: Any) -> list[Point3] | None:
    if not isinstance(points, list):
        return None
    normalized = [_point3(point) for point in points]
    if any(point is None for point in normalized):
        return None
    return [point for point in normalized if point is not None]


def _point3(point: Any) -> Point3 | None:
    if not isinstance(point, list) or len(point) != 3:
        return None
    values = [_finite_float(value) for value in point]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


def _positive_float(value: Any) -> float | None:
    result = _finite_float(value)
    if result is None or result <= 0.0:
        return None
    return result


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _loop_id(section_loop: dict[str, Any]) -> str:
    blade_class = section_loop.get("blade_class", "blade")
    blade_pair_index = section_loop.get("blade_pair_index", "unknown")
    section_index = section_loop.get("section_index", "unknown")
    return f"{blade_class}_blade_{blade_pair_index}_section_loop_{section_index}"


def _first_nonzero_vector(vectors: list[Point3]) -> Point3 | None:
    for vector in vectors:
        unit = _normalized(vector)
        if unit is not None:
            return unit
    return None


def _fallback_perpendicular(vector: Point3) -> Point3:
    candidate = _cross(vector, [0.0, 0.0, 1.0])
    unit = _normalized(candidate)
    if unit is not None:
        return unit
    return [0.0, 1.0, 0.0]


def _segments_intersect(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    def orientation(first: Point2, second: Point2, third: Point2) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])

    return orientation(a, b, c) * orientation(a, b, d) < 0.0 and orientation(c, d, a) * orientation(c, d, b) < 0.0


def _segments_intersect_or_touch(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    first = _orientation_2d(a, b, c)
    second = _orientation_2d(a, b, d)
    third = _orientation_2d(c, d, a)
    fourth = _orientation_2d(c, d, b)
    if first * second < 0.0 and third * fourth < 0.0:
        return True
    return (
        abs(first) <= _EPSILON and _point_on_segment_2d(c, a, b)
        or abs(second) <= _EPSILON and _point_on_segment_2d(d, a, b)
        or abs(third) <= _EPSILON and _point_on_segment_2d(a, c, d)
        or abs(fourth) <= _EPSILON and _point_on_segment_2d(b, c, d)
    )


def _orientation_2d(first: Point2, second: Point2, third: Point2) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])


def _point_on_segment_2d(point: Point2, start: Point2, end: Point2) -> bool:
    return (
        min(start[0], end[0]) - _EPSILON <= point[0] <= max(start[0], end[0]) + _EPSILON
        and min(start[1], end[1]) - _EPSILON <= point[1] <= max(start[1], end[1]) + _EPSILON
        and abs(_orientation_2d(start, end, point)) <= _EPSILON
    )


def _triangle_signed_area(first: Point2, second: Point2, third: Point2) -> float:
    return 0.5 * (
        first[0] * (second[1] - third[1])
        + second[0] * (third[1] - first[1])
        + third[0] * (first[1] - second[1])
    )


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(sum((float(first[axis]) - float(second[axis])) ** 2 for axis in range(3)))


def _distance_2d(first: Point2, second: Point2) -> float:
    return math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))


def _points_close_2d(first: Point2, second: Point2) -> bool:
    return _distance_2d(first, second) <= _EPSILON


def _add(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) + float(second[axis]) for axis in range(3)]


def _subtract(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _scale(vector: Point3, scalar: float) -> Point3:
    return [float(value) * float(scalar) for value in vector]


def _dot(first: Point3, second: Point3) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first: Point3, second: Point3) -> Point3:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _normalized(vector: Point3) -> Point3 | None:
    length = math.sqrt(sum(float(value) * float(value) for value in vector))
    if length <= _EPSILON:
        return None
    return [float(value) / length for value in vector]


def _round(value: float) -> float:
    return round(float(value), 9)


def _round_vector(vector: Point3) -> Point3:
    return [_clean_zero(_round(value)) for value in vector]


def _clean_zero(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-12 else value


def _fail(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason, **extra}
