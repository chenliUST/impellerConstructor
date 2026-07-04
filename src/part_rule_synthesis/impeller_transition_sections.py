from __future__ import annotations

import math
from typing import Any, Iterable


Point3 = tuple[float, float, float]

_EPSILON = 1.0e-9
_MIN_FILLET_SAMPLE_COUNT = 9


def build_fillet_section(
    *,
    edge_point: Point3,
    tangent: Point3,
    first_retained_direction: Point3,
    second_retained_direction: Point3,
    radius_mm: float,
    sample_count: int,
    convexity_sign: int,
) -> dict[str, Any]:
    """Build a circular fillet arc in the section frame normal to the edge tangent."""
    radius = _positive_finite(radius_mm, "fillet radius_mm")
    edge = _point3(edge_point, "edge_point")
    tangent_unit = _unit_vector(tangent, "tangent")
    first_unit = _unit_vector(
        _project_perpendicular(first_retained_direction, tangent_unit),
        "first_retained_direction projected perpendicular to tangent",
    )
    second_unit = _unit_vector(
        _project_perpendicular(second_retained_direction, tangent_unit),
        "second_retained_direction projected perpendicular to tangent",
    )

    dot_directions = _clamp(_dot(first_unit, second_unit), -1.0, 1.0)
    included_angle = math.acos(dot_directions)
    if included_angle <= _EPSILON or math.pi - included_angle <= _EPSILON:
        raise ValueError("fillet retained directions must form a nondegenerate angle")

    bisector = _unit_vector(
        _add(first_unit, second_unit),
        "fillet retained direction bisector",
    )
    trim_distance = radius / math.tan(included_angle * 0.5)
    center_distance = radius / math.sin(included_angle * 0.5)
    center = _add(edge, _scale(bisector, center_distance))
    first_trim_point = _add(edge, _scale(first_unit, trim_distance))
    second_trim_point = _add(edge, _scale(second_unit, trim_distance))

    start_radius = _subtract(first_trim_point, center)
    end_radius = _subtract(second_trim_point, center)
    signed_arc_angle = math.atan2(
        _dot(_cross(start_radius, end_radius), tangent_unit),
        _dot(start_radius, end_radius),
    )
    if abs(signed_arc_angle) <= _EPSILON:
        raise ValueError("fillet arc angle is degenerate")

    points = [
        _add(center, _rotate_about_axis(start_radius, tangent_unit, signed_arc_angle * parameter))
        for parameter in _sample_parameters(max(_MIN_FILLET_SAMPLE_COUNT, int(sample_count)))
    ]
    points[0] = first_trim_point
    points[-1] = second_trim_point
    return {
        "treatment": "fillet",
        "points": points,
        "quality": {
            "section_sample_count": len(points),
            "included_angle_deg": math.degrees(included_angle),
            "radius_max_error_mm": _max_radius_error(points, center=center, radius_mm=radius),
            "convexity_sign": _sign(convexity_sign, "convexity_sign"),
            "trim_distance_mm": trim_distance,
        },
    }


def build_chamfer_section(
    *,
    edge_point: Point3,
    first_retained_direction: Point3,
    second_retained_direction: Point3,
    distance_mm: float,
) -> dict[str, Any]:
    """Build a straight chamfer segment between retained-side offset points."""
    distance = _positive_finite(distance_mm, "chamfer distance_mm")
    edge = _point3(edge_point, "edge_point")
    first_unit = _unit_vector(first_retained_direction, "first_retained_direction")
    second_unit = _unit_vector(second_retained_direction, "second_retained_direction")
    if _norm(_cross(first_unit, second_unit)) <= _EPSILON:
        raise ValueError("chamfer retained directions must not be parallel")

    first_point = _add(edge, _scale(first_unit, distance))
    second_point = _add(edge, _scale(second_unit, distance))
    points = [first_point, second_point]
    return {
        "treatment": "chamfer",
        "points": points,
        "quality": {
            "section_sample_count": len(points),
            "direction_sign": _orientation_sign(first_unit, second_unit),
            "section_linearity_max_error_mm": _max_distance_from_line(
                points,
                first=first_point,
                second=second_point,
            ),
            "distance_mm": distance,
        },
    }


def _point3(values: Iterable[float], name: str) -> Point3:
    coordinates = tuple(float(value) for value in values)
    if len(coordinates) != 3:
        raise ValueError(f"{name} must contain exactly 3 coordinates")
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError(f"{name} must contain finite coordinates")
    return coordinates


def _positive_finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return number


def _unit_vector(vector: Iterable[float], name: str) -> Point3:
    point = _point3(vector, name)
    length = _norm(point)
    if length <= _EPSILON:
        raise ValueError(f"{name} must be nonzero")
    return _scale(point, 1.0 / length)


def _project_perpendicular(vector: Iterable[float], normal: Point3) -> Point3:
    point = _point3(vector, "retained_direction")
    return _subtract(point, _scale(normal, _dot(point, normal)))


def _sign(value: int, name: str) -> int:
    number = float(value)
    if not math.isfinite(number) or number == 0.0:
        raise ValueError(f"{name} must be positive or negative")
    return 1 if number > 0.0 else -1


def _orientation_sign(first: Point3, second: Point3) -> int:
    cross = _cross(first, second)
    dominant_axis_value = max(cross, key=abs)
    return 1 if dominant_axis_value >= 0.0 else -1


def _sample_parameters(sample_count: int) -> list[float]:
    if sample_count < 2:
        raise ValueError("section sample_count must be at least 2")
    return [index / (sample_count - 1) for index in range(sample_count)]


def _max_radius_error(points: list[Point3], *, center: Point3, radius_mm: float) -> float:
    return max(abs(_norm(_subtract(point, center)) - radius_mm) for point in points)


def _max_distance_from_line(points: list[Point3], *, first: Point3, second: Point3) -> float:
    direction = _subtract(second, first)
    direction_length = _norm(direction)
    if direction_length <= _EPSILON:
        raise ValueError("line endpoints must be distinct")
    return max(
        _norm(_cross(_subtract(point, first), direction)) / direction_length
        for point in points
    )


def _rotate_about_axis(vector: Point3, axis: Point3, angle_rad: float) -> Point3:
    cos_angle = math.cos(angle_rad)
    sin_angle = math.sin(angle_rad)
    return _add(
        _add(
            _scale(vector, cos_angle),
            _scale(_cross(axis, vector), sin_angle),
        ),
        _scale(axis, _dot(axis, vector) * (1.0 - cos_angle)),
    )


def _add(first: Point3, second: Point3) -> Point3:
    return (
        first[0] + second[0],
        first[1] + second[1],
        first[2] + second[2],
    )


def _subtract(first: Point3, second: Point3) -> Point3:
    return (
        first[0] - second[0],
        first[1] - second[1],
        first[2] - second[2],
    )


def _scale(vector: Point3, scale: float) -> Point3:
    return (
        vector[0] * scale,
        vector[1] * scale,
        vector[2] * scale,
    )


def _dot(first: Point3, second: Point3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _cross(first: Point3, second: Point3) -> Point3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _norm(vector: Point3) -> float:
    return math.sqrt(_dot(vector, vector))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
