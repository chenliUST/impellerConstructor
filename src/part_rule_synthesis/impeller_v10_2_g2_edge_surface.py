from __future__ import annotations

import copy
import math
from typing import Any


Point3 = list[float]
Frame = dict[str, list[float]]

_MIN_SHORT_DIRECTION_SAMPLES = 17
_SECTION_CONTROL_COUNT = 5
_EPSILON = 1.0e-9
_BULGE_NUMERIC_MARGIN_MM = 1.0e-6


def build_v10_2_g2_edge_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    pressure_frames: list[dict[str, list[float]]],
    suction_frames: list[dict[str, list[float]]],
    radius_mm: float,
    sample_count: int = 17,
) -> dict[str, Any]:
    if sample_count < _MIN_SHORT_DIRECTION_SAMPLES:
        raise ValueError(
            f"sample_count must be at least {_MIN_SHORT_DIRECTION_SAMPLES} for V1.0.2 edge G2 review surfaces"
        )
    if len(pressure_frames) != len(suction_frames):
        raise ValueError("pressure/suction frame count mismatch")
    if len(pressure_frames) < 2:
        raise ValueError("at least two pressure/suction frame pairs are required")
    if not math.isfinite(float(radius_mm)):
        raise ValueError("radius_mm must be finite")
    if float(radius_mm) < 0.0:
        raise ValueError("radius_mm must be non-negative")

    uv_grid: list[list[Point3]] = []
    control_net: list[list[Point3]] = []
    section_bulges: list[float] = []
    previous_bulge_direction: Point3 | None = None

    zero_curvature_proxy_input = _all_curvature_proxies_are_zero(pressure_frames, suction_frames)
    for pressure_frame, suction_frame in zip(pressure_frames, suction_frames):
        section, controls, metrics = _build_quartic_section(
            pressure_frame,
            suction_frame,
            radius_mm=float(radius_mm),
            sample_count=sample_count,
            previous_bulge_direction=previous_bulge_direction,
        )
        previous_bulge_direction = metrics["bulge_direction"]
        uv_grid.append(section)
        control_net.append(controls)
        section_bulges.append(metrics["midpoint_bulge_mm"])

    edge_samples = _edge_samples(face_family, uv_grid)
    tangent_quality = _paired_vector_quality_metrics(pressure_frames, suction_frames, "edge_tangent")
    normal_quality = _paired_vector_quality_metrics(pressure_frames, suction_frames, "material_normal")
    transition_quality = {
        "continuity_claim": "G2_TARGET_REVIEW_GRADE",
        "curvature_claim": "G2_TARGET_REVIEW_GRADE",
        "short_direction_sample_count": sample_count,
        "short_direction_control_count": _SECTION_CONTROL_COUNT,
        "min_midpoint_bulge_mm": _round(min(section_bulges)),
        "max_midpoint_bulge_mm": _round(max(section_bulges)),
        "effective_radius_mm": _round(max(float(radius_mm), max(section_bulges))),
        "max_section_tangent_flip_deg": _round(tangent_quality["conservative_max_flip_deg"]),
        "max_pressure_section_tangent_flip_deg": _round(tangent_quality["max_pressure_adjacent_flip_deg"]),
        "max_suction_section_tangent_flip_deg": _round(tangent_quality["max_suction_adjacent_flip_deg"]),
        "max_pressure_vs_suction_tangent_opposition_deg": _round(
            tangent_quality["max_pressure_vs_suction_opposition_deg"]
        ),
        "degenerate_averaged_section_tangent_count": tangent_quality["degenerate_averaged_vector_count"],
        "max_normal_flip_deg": _round(normal_quality["conservative_max_flip_deg"]),
        "max_pressure_normal_flip_deg": _round(normal_quality["max_pressure_adjacent_flip_deg"]),
        "max_suction_normal_flip_deg": _round(normal_quality["max_suction_adjacent_flip_deg"]),
        "max_pressure_vs_suction_normal_opposition_deg": _round(
            normal_quality["max_pressure_vs_suction_opposition_deg"]
        ),
        "degenerate_averaged_normal_count": normal_quality["degenerate_averaged_vector_count"],
        "foldover_count": _foldover_count(uv_grid),
        "zero_curvature_proxy_input": zero_curvature_proxy_input,
        "g2_measurement_status_by_shared_edge": {
            "pressure_shared_edge": "G2_TARGET_ONLY_NOT_KERNEL_MEASURED",
            "suction_shared_edge": "G2_TARGET_ONLY_NOT_KERNEL_MEASURED",
            "section_curvature": "REVIEW_GRADE_BEZIER_PROXY",
        },
    }

    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        "uv_grid": uv_grid,
        "control_net": control_net,
        "degree_u": 3,
        "degree_v": 4,
        "short_direction_basis": "quartic_bezier_review_grid",
        "edge_samples": edge_samples,
        "transition_quality": transition_quality,
        "display": {
            "inspection_class": "v10_2_g2_edge_surface",
            "color": "#6f8fb8",
            "wire_color": "#d6dde8",
        },
    }


def _build_quartic_section(
    pressure_frame: Frame,
    suction_frame: Frame,
    *,
    radius_mm: float,
    sample_count: int,
    previous_bulge_direction: Point3 | None,
) -> tuple[list[Point3], list[Point3], dict[str, Any]]:
    pressure_point = _point(pressure_frame, "point")
    suction_point = _point(suction_frame, "point")
    chord = _subtract(suction_point, pressure_point)
    chord_length = _length(chord)
    chord_midpoint = _midpoint(pressure_point, suction_point)
    required_midpoint_bulge = max(1.0, 0.12 * radius_mm, 0.08 * chord_length)

    bulge_direction = _section_bulge_direction(
        pressure_frame,
        suction_frame,
        chord=chord,
        previous_bulge_direction=previous_bulge_direction,
    )
    control_bulge = (required_midpoint_bulge + _BULGE_NUMERIC_MARGIN_MM) / 0.875
    tangent_bias = _section_tangent_bias(pressure_frame, suction_frame, chord, radius_mm)

    controls = [
        copy.deepcopy(pressure_point),
        _round_vector(
            _add(
                _add(_lerp(pressure_point, suction_point, 0.25), _scale(bulge_direction, control_bulge)),
                _scale(tangent_bias, -1.0),
            )
        ),
        _round_vector(_add(chord_midpoint, _scale(bulge_direction, control_bulge))),
        _round_vector(
            _add(
                _add(_lerp(pressure_point, suction_point, 0.75), _scale(bulge_direction, control_bulge)),
                tangent_bias,
            )
        ),
        copy.deepcopy(suction_point),
    ]
    samples = _quartic_bezier_samples(controls, sample_count)
    midpoint = _quartic_bezier_point(controls, 0.5)

    return samples, controls, {
        "bulge_direction": bulge_direction,
        "midpoint_bulge_mm": _distance(midpoint, chord_midpoint),
    }


def _section_bulge_direction(
    pressure_frame: Frame,
    suction_frame: Frame,
    *,
    chord: Point3,
    previous_bulge_direction: Point3 | None,
) -> Point3:
    curvature_direction = _normalized(
        _add(
            _vector(pressure_frame, "curvature_proxy", [0.0, 0.0, 0.0]),
            _vector(suction_frame, "curvature_proxy", [0.0, 0.0, 0.0]),
        )
    )
    normal_direction = _normalized(
        _add(
            _vector(pressure_frame, "material_normal", [0.0, 0.0, 1.0]),
            _vector(suction_frame, "material_normal", [0.0, 0.0, 1.0]),
        )
    )
    raw_direction = normal_direction or curvature_direction or _fallback_material_direction(chord)
    projected = _reject_from(raw_direction, chord)
    direction = _normalized(projected) or normal_direction or _fallback_material_direction(chord)
    if previous_bulge_direction is not None and _dot(direction, previous_bulge_direction) < 0.0:
        direction = _scale(direction, -1.0)
    return direction


def _section_tangent_bias(
    pressure_frame: Frame,
    suction_frame: Frame,
    chord: Point3,
    radius_mm: float,
) -> Point3:
    tangent = _normalized(
        _add(
            _vector(pressure_frame, "edge_tangent", [1.0, 0.0, 0.0]),
            _vector(suction_frame, "edge_tangent", [1.0, 0.0, 0.0]),
        )
    )
    if tangent is None:
        return [0.0, 0.0, 0.0]
    tangent = _normalized(_reject_from(tangent, chord))
    if tangent is None:
        return [0.0, 0.0, 0.0]
    magnitude = min(_length(chord) * 0.03, max(abs(radius_mm), 1.0) * 0.025)
    return _scale(tangent, magnitude)


def _quartic_bezier_samples(controls: list[Point3], sample_count: int) -> list[Point3]:
    samples = []
    for index in range(sample_count):
        if index == 0:
            samples.append(copy.deepcopy(controls[0]))
        elif index == sample_count - 1:
            samples.append(copy.deepcopy(controls[-1]))
        else:
            samples.append(_round_vector(_quartic_bezier_point(controls, index / (sample_count - 1))))
    return samples


def _quartic_bezier_point(controls: list[Point3], t: float) -> Point3:
    one_minus_t = 1.0 - t
    weights = [
        one_minus_t**4,
        4.0 * one_minus_t**3 * t,
        6.0 * one_minus_t * one_minus_t * t * t,
        4.0 * one_minus_t * t**3,
        t**4,
    ]
    return [
        sum(weights[index] * controls[index][axis] for index in range(_SECTION_CONTROL_COUNT))
        for axis in range(3)
    ]


def _edge_samples(face_family: str, uv_grid: list[list[Point3]]) -> dict[str, list[Point3]]:
    samples = {
        "pressure_boundary": _column(uv_grid, 0),
        "suction_boundary": _column(uv_grid, -1),
        "start_cap": copy.deepcopy(uv_grid[0]),
        "end_cap": copy.deepcopy(uv_grid[-1]),
        "mid_curve": _column(uv_grid, len(uv_grid[0]) // 2),
    }
    if face_family == "blade_leading_edge":
        samples.update(
            {
                "pressure_side_leading_boundary": _column(uv_grid, 0),
                "suction_side_leading_boundary": _column(uv_grid, -1),
                "root_profile_leading_cap": copy.deepcopy(uv_grid[0]),
                "tip_profile_leading_cap": copy.deepcopy(uv_grid[-1]),
            }
        )
    elif face_family == "blade_trailing_edge":
        samples.update(
            {
                "pressure_side_trailing_boundary": _column(uv_grid, 0),
                "suction_side_trailing_boundary": _column(uv_grid, -1),
                "root_profile_trailing_cap": copy.deepcopy(uv_grid[0]),
                "tip_profile_trailing_cap": copy.deepcopy(uv_grid[-1]),
            }
        )
    elif face_family == "blade_tip":
        samples.update(
            {
                "tip_profile_pressure_edge": _column(uv_grid, 0),
                "tip_profile_suction_edge": _column(uv_grid, -1),
                "tip_support_mean_curve": _column(uv_grid, len(uv_grid[0]) // 2),
            }
        )
    return samples


def _foldover_count(uv_grid: list[list[Point3]]) -> int:
    normals: list[list[Point3 | None]] = []
    for u_index in range(len(uv_grid) - 1):
        normal_row: list[Point3 | None] = []
        for v_index in range(len(uv_grid[0]) - 1):
            normal = _cross(
                _subtract(uv_grid[u_index + 1][v_index], uv_grid[u_index][v_index]),
                _subtract(uv_grid[u_index][v_index + 1], uv_grid[u_index][v_index]),
            )
            if _length(normal) <= _EPSILON:
                normal_row.append(None)
            else:
                normal_row.append(_normalized(normal))
        normals.append(normal_row)

    foldovers = 0
    for u_index, normal_row in enumerate(normals):
        for v_index, normal in enumerate(normal_row):
            if normal is None:
                foldovers += 1
                continue
            for u_step, v_step in ((1, 0), (0, 1)):
                adjacent_u = u_index + u_step
                adjacent_v = v_index + v_step
                if adjacent_u >= len(normals) or adjacent_v >= len(normal_row):
                    continue
                adjacent = normals[adjacent_u][adjacent_v]
                if adjacent is not None and _dot(normal, adjacent) < -1.0e-7:
                    foldovers += 1
    return foldovers


def _paired_vector_quality_metrics(
    pressure_frames: list[Frame],
    suction_frames: list[Frame],
    key: str,
) -> dict[str, float | int]:
    pressure_adjacent_flip = _max_adjacent_side_vector_flip_deg(pressure_frames, key)
    suction_adjacent_flip = _max_adjacent_side_vector_flip_deg(suction_frames, key)
    pressure_vs_suction_opposition = _max_paired_vector_angle_deg(pressure_frames, suction_frames, key)
    degenerate_averaged_vector_count = _degenerate_averaged_vector_count(pressure_frames, suction_frames, key)
    return {
        "max_pressure_adjacent_flip_deg": pressure_adjacent_flip,
        "max_suction_adjacent_flip_deg": suction_adjacent_flip,
        "max_pressure_vs_suction_opposition_deg": pressure_vs_suction_opposition,
        "degenerate_averaged_vector_count": degenerate_averaged_vector_count,
        "conservative_max_flip_deg": max(
            pressure_adjacent_flip,
            suction_adjacent_flip,
            pressure_vs_suction_opposition,
        ),
    }


def _max_adjacent_side_vector_flip_deg(frames: list[Frame], key: str) -> float:
    max_flip = 0.0
    previous = None
    for frame in frames:
        vector = _normalized(_vector(frame, key, [0.0, 0.0, 0.0]))
        if vector is None:
            continue
        if previous is not None:
            max_flip = max(max_flip, _angle_deg(previous, vector))
        previous = vector
    return max_flip


def _max_paired_vector_angle_deg(
    pressure_frames: list[Frame],
    suction_frames: list[Frame],
    key: str,
) -> float:
    max_angle = 0.0
    for pressure_frame, suction_frame in zip(pressure_frames, suction_frames):
        pressure_vector = _normalized(_vector(pressure_frame, key, [0.0, 0.0, 0.0]))
        suction_vector = _normalized(_vector(suction_frame, key, [0.0, 0.0, 0.0]))
        if pressure_vector is None or suction_vector is None:
            continue
        max_angle = max(max_angle, _angle_deg(pressure_vector, suction_vector))
    return max_angle


def _degenerate_averaged_vector_count(
    pressure_frames: list[Frame],
    suction_frames: list[Frame],
    key: str,
) -> int:
    degenerate_count = 0
    for pressure_frame, suction_frame in zip(pressure_frames, suction_frames):
        pressure_vector = _normalized(_vector(pressure_frame, key, [0.0, 0.0, 0.0]))
        suction_vector = _normalized(_vector(suction_frame, key, [0.0, 0.0, 0.0]))
        if (
            pressure_vector is not None
            and suction_vector is not None
            and _normalized(_add(pressure_vector, suction_vector)) is None
        ):
            degenerate_count += 1
    return degenerate_count


def _all_curvature_proxies_are_zero(pressure_frames: list[Frame], suction_frames: list[Frame]) -> bool:
    for frame in pressure_frames + suction_frames:
        if _length(_vector(frame, "curvature_proxy", [0.0, 0.0, 0.0])) > _EPSILON:
            return False
    return True


def _point(frame: Frame, key: str) -> Point3:
    value = frame.get(key)
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"frame {key} must contain three coordinates")
    point = [float(value[axis]) for axis in range(3)]
    if not all(math.isfinite(value) for value in point):
        raise ValueError(f"frame {key} must contain finite coordinates")
    return point


def _vector(frame: Frame, key: str, fallback: Point3) -> Point3:
    value = frame.get(key, fallback)
    if not isinstance(value, list) or len(value) != 3:
        return copy.deepcopy(fallback)
    vector = [float(value[axis]) for axis in range(3)]
    if not all(math.isfinite(value) for value in vector):
        return copy.deepcopy(fallback)
    return vector


def _fallback_material_direction(chord: Point3) -> Point3:
    chord_direction = _normalized(chord) or [0.0, 1.0, 0.0]
    candidate = _cross(chord_direction, [1.0, 0.0, 0.0])
    if _length(candidate) <= _EPSILON:
        candidate = _cross(chord_direction, [0.0, 0.0, 1.0])
    return _normalized(candidate) or [0.0, 0.0, 1.0]


def _column(grid: list[list[Point3]], index: int) -> list[Point3]:
    return [copy.deepcopy(row[index]) for row in grid]


def _reject_from(vector: Point3, axis: Point3) -> Point3:
    normalized_axis = _normalized(axis)
    if normalized_axis is None:
        return copy.deepcopy(vector)
    return _subtract(vector, _scale(normalized_axis, _dot(vector, normalized_axis)))


def _angle_deg(first: Point3, second: Point3) -> float:
    first_normalized = _normalized(first)
    second_normalized = _normalized(second)
    if first_normalized is None or second_normalized is None:
        return 0.0
    dot = max(-1.0, min(1.0, _dot(first_normalized, second_normalized)))
    return math.degrees(math.acos(dot))


def _distance(first: Point3, second: Point3) -> float:
    return _length(_subtract(first, second))


def _midpoint(first: Point3, second: Point3) -> Point3:
    return [(float(first[axis]) + float(second[axis])) * 0.5 for axis in range(3)]


def _lerp(first: Point3, second: Point3, t: float) -> Point3:
    return [float(first[axis]) * (1.0 - t) + float(second[axis]) * t for axis in range(3)]


def _add(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) + float(second[axis]) for axis in range(3)]


def _subtract(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _scale(vector: Point3, scalar: float) -> Point3:
    return [float(value) * scalar for value in vector]


def _dot(first: Point3, second: Point3) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first: Point3, second: Point3) -> Point3:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _length(vector: Point3) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _normalized(vector: Point3) -> Point3 | None:
    length = _length(vector)
    if length <= _EPSILON:
        return None
    return [float(value) / length for value in vector]


def _round(value: float) -> float:
    return round(float(value), 9)


def _round_vector(vector: Point3) -> Point3:
    return [_round(value) for value in vector]
