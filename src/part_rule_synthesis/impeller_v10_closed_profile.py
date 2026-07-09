from __future__ import annotations

import math
from typing import Any

Point3 = tuple[float, float, float]


def build_closed_blade_section_profile(
    *,
    station_index: int,
    station_count: int,
    center: Point3,
    tangent: Point3,
    radial: Point3,
    thickness_mm: float,
    leading_radius_mm: float,
    trailing_radius_mm: float,
    sample_count: int = 17,
) -> dict[str, Any]:
    if thickness_mm <= 0.0 or sample_count < 5:
        return _profile_failure(
            station_index=station_index,
            station_count=station_count,
            reason="v1_0_closed_blade_profile_failed",
        )

    tangent_unit = _normalize(tangent)
    radial_unit = _normalize(radial)
    if tangent_unit is None or radial_unit is None:
        return _profile_failure(
            station_index=station_index,
            station_count=station_count,
            reason="v1_0_closed_blade_profile_failed",
        )

    half_thickness = thickness_mm * 0.5
    leading_radius = max(float(leading_radius_mm), 0.0)
    trailing_radius = max(float(trailing_radius_mm), 0.0)
    chord_length = max(
        2.5 * thickness_mm + leading_radius + trailing_radius,
        4.0 * max(leading_radius, trailing_radius, half_thickness),
    )

    center_point = _point(center)
    leading_center = _add(center_point, _scale(radial_unit, -0.5 * chord_length))
    trailing_center = _add(center_point, _scale(radial_unit, 0.5 * chord_length))

    pressure_leading = _add(leading_center, _scale(tangent_unit, half_thickness))
    pressure_trailing = _add(trailing_center, _scale(tangent_unit, half_thickness))
    suction_trailing = _add(trailing_center, _scale(tangent_unit, -half_thickness))
    suction_leading = _add(leading_center, _scale(tangent_unit, -half_thickness))

    pressure_side = _line_points(pressure_leading, pressure_trailing, sample_count)
    trailing_cap = _cap_points(
        center=trailing_center,
        tangent_unit=tangent_unit,
        radial_unit=radial_unit,
        radius_mm=trailing_radius,
        half_thickness=half_thickness,
        start_angle=math.pi / 2.0,
        end_angle=-math.pi / 2.0,
        radial_sign=1.0,
        sample_count=sample_count,
    )
    suction_side = _line_points(suction_trailing, suction_leading, sample_count)
    leading_cap = _cap_points(
        center=leading_center,
        tangent_unit=tangent_unit,
        radial_unit=radial_unit,
        radius_mm=leading_radius,
        half_thickness=half_thickness,
        start_angle=-math.pi / 2.0,
        end_angle=math.pi / 2.0,
        radial_sign=-1.0,
        sample_count=sample_count,
    )

    closed_loop = [
        *pressure_side,
        *trailing_cap[1:],
        *suction_side[1:],
        *leading_cap[1:],
    ]
    closed_loop.append(closed_loop[0])

    closure_gaps = [
        _distance(pressure_side[-1], trailing_cap[0]),
        _distance(trailing_cap[-1], suction_side[0]),
        _distance(suction_side[-1], leading_cap[0]),
        _distance(leading_cap[-1], pressure_side[0]),
        _distance(closed_loop[-1], closed_loop[0]),
    ]

    return {
        "closed_profile_status": "PASS",
        "station_index": station_index,
        "station_count": station_count,
        "max_closure_gap_mm": max(closure_gaps),
        "curves": {
            "pressure_side_curve": pressure_side,
            "leading_edge_cap_curve": leading_cap,
            "suction_side_curve": suction_side,
            "trailing_edge_cap_curve": trailing_cap,
        },
        "closed_loop": closed_loop,
        "section_metrics": {
            "chord_length_mm": chord_length,
            "thickness_mm": thickness_mm,
            "leading_radius_mm": leading_radius,
            "trailing_radius_mm": trailing_radius,
        },
    }


def _profile_failure(*, station_index: int, station_count: int, reason: str) -> dict[str, Any]:
    return {
        "closed_profile_status": "FAIL",
        "failure_reason": reason,
        "station_index": station_index,
        "station_count": station_count,
        "curves": {},
        "closed_loop": [],
        "max_closure_gap_mm": math.inf,
    }


def _point(point: Point3) -> Point3:
    return (float(point[0]), float(point[1]), float(point[2]))


def _normalize(vector: Point3) -> Point3 | None:
    length = math.sqrt(sum(float(component) * float(component) for component in vector))
    if length <= 1.0e-12:
        return None
    return (float(vector[0]) / length, float(vector[1]) / length, float(vector[2]) / length)


def _line_points(start: Point3, end: Point3, sample_count: int) -> list[Point3]:
    return [
        _lerp(start, end, index / (sample_count - 1))
        for index in range(sample_count)
    ]


def _cap_points(
    *,
    center: Point3,
    tangent_unit: Point3,
    radial_unit: Point3,
    radius_mm: float,
    half_thickness: float,
    start_angle: float,
    end_angle: float,
    radial_sign: float,
    sample_count: int,
) -> list[Point3]:
    points = []
    for index in range(sample_count):
        fraction = index / (sample_count - 1)
        angle = start_angle + (end_angle - start_angle) * fraction
        radial_offset = radial_sign * radius_mm * abs(math.cos(angle))
        thickness_offset = half_thickness * math.sin(angle)
        points.append(
            _add(
                center,
                _add(
                    _scale(radial_unit, radial_offset),
                    _scale(tangent_unit, thickness_offset),
                ),
            )
        )
    return points


def _lerp(start: Point3, end: Point3, fraction: float) -> Point3:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
        start[2] + (end[2] - start[2]) * fraction,
    )


def _add(first: Point3, second: Point3) -> Point3:
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def _scale(vector: Point3, value: float) -> Point3:
    return (vector[0] * value, vector[1] * value, vector[2] * value)


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )
