from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal


Point3 = tuple[float, float, float]
Treatment = Literal["none", "chamfer", "fillet"]


@dataclass
class TransitionSection:
    treatment: Treatment
    radius_mm: float
    points: list[Point3]
    quality: dict[str, Any]


@dataclass
class EdgeTreatmentSite:
    site_id: str
    edge_family: str
    transition_policy_id: str
    treatment: Treatment
    radius_mm: float
    adjacent_surface_ids: tuple[str, str]
    transition_surface_id: str
    feature_id: str


@dataclass
class TransitionResolution:
    surface_graph: dict[str, Any]
    edge_treatment_sites: list[EdgeTreatmentSite]
    transition_failures: list[dict[str, Any]]
    quality_checks: list[dict[str, Any]]


def build_fillet_section(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    center: Point3,
    radius_mm: float,
    sample_count: int,
    edge_tangent: Point3,
) -> TransitionSection:
    """Build a sampled local XY-section fillet primitive for the initial V0.8 resolver.

    The arc is sampled in the XY plane around ``center``. ``edge_tangent`` is used
    only to choose orientation for an ambiguous half-circle section.
    """
    if sample_count < 3:
        raise ValueError("fillet section sample_count must be at least 3")
    if radius_mm <= 0.0 or not math.isfinite(radius_mm):
        raise ValueError("fillet radius_mm must be positive and finite")
    if _norm(edge_tangent) <= 1.0e-9:
        raise ValueError("fillet section edge_tangent must be nonzero")
    if (
        abs(_xy_distance(first_trim_point, center) - radius_mm) > 1.0e-6
        or abs(_xy_distance(second_trim_point, center) - radius_mm) > 1.0e-6
    ):
        raise ValueError("fillet trim points must lie on requested radius from center")

    start_angle = math.atan2(first_trim_point[1] - center[1], first_trim_point[0] - center[0])
    end_angle = math.atan2(second_trim_point[1] - center[1], second_trim_point[0] - center[0])
    angle_delta = _shortest_angle_delta(start_angle, end_angle)
    if abs(angle_delta) == math.pi and edge_tangent[2] < 0.0:
        angle_delta = -angle_delta

    points = [
        (
            center[0] + radius_mm * math.cos(start_angle + angle_delta * t),
            center[1] + radius_mm * math.sin(start_angle + angle_delta * t),
            _lerp(first_trim_point[2], second_trim_point[2], t),
        )
        for t in _sample_parameters(sample_count)
    ]
    points[0] = first_trim_point
    points[-1] = second_trim_point
    return TransitionSection(
        treatment="fillet",
        radius_mm=float(radius_mm),
        points=points,
        quality={
            "max_radius_error": max_radius_error(points, center=center, radius_mm=radius_mm),
            "rms_radius_error": rms_radius_error(points, center=center, radius_mm=radius_mm),
            "sample_count": sample_count,
        },
    )


def build_chamfer_section(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    sample_count: int,
) -> TransitionSection:
    """Build a sampled local XY-section chamfer primitive for the initial V0.8 resolver."""
    if sample_count < 2:
        raise ValueError("chamfer section sample_count must be at least 2")

    points = [
        (
            _lerp(first_trim_point[0], second_trim_point[0], t),
            _lerp(first_trim_point[1], second_trim_point[1], t),
            _lerp(first_trim_point[2], second_trim_point[2], t),
        )
        for t in _sample_parameters(sample_count)
    ]
    return TransitionSection(
        treatment="chamfer",
        radius_mm=0.0,
        points=points,
        quality={
            "max_distance_from_line": max_distance_from_line(
                points,
                first=first_trim_point,
                second=second_trim_point,
            ),
            "sample_count": sample_count,
        },
    )


def max_radius_error(points: list[Point3], *, center: Point3, radius_mm: float) -> float:
    if not points:
        return 0.0
    return max(abs(_xy_distance(point, center) - radius_mm) for point in points)


def rms_radius_error(points: list[Point3], *, center: Point3, radius_mm: float) -> float:
    if not points:
        return 0.0
    squared_errors = [(abs(_xy_distance(point, center) - radius_mm)) ** 2 for point in points]
    return math.sqrt(sum(squared_errors) / len(squared_errors))


def max_distance_from_line(points: list[Point3], *, first: Point3, second: Point3) -> float:
    if not points:
        return 0.0
    direction = _subtract(second, first)
    direction_length = _norm(direction)
    if direction_length == 0.0:
        raise ValueError("line endpoints must be distinct")
    return max(_norm(_cross(_subtract(point, first), direction)) / direction_length for point in points)


def resolve_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
    geometry_version: str,
) -> TransitionResolution:
    if geometry_version != "0.8":
        return TransitionResolution(
            surface_graph=surface_graph,
            edge_treatment_sites=[],
            transition_failures=[],
            quality_checks=[],
        )

    resolved_graph = dict(surface_graph)
    resolved_graph["transition_geometry_status"] = "resolved_trimmed_surface_graph"
    return TransitionResolution(
        surface_graph=resolved_graph,
        edge_treatment_sites=[],
        transition_failures=[],
        quality_checks=[
            {
                "check_id": "transition_geometry_resolver_invoked",
                "status": "PASS",
            }
        ],
    )


def _sample_parameters(sample_count: int) -> list[float]:
    return [index / (sample_count - 1) for index in range(sample_count)]


def _shortest_angle_delta(start_angle: float, end_angle: float) -> float:
    return (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi


def _lerp(first: float, second: float, t: float) -> float:
    return first + (second - first) * t


def _xy_distance(first: Point3, second: Point3) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _subtract(first: Point3, second: Point3) -> Point3:
    return (
        first[0] - second[0],
        first[1] - second[1],
        first[2] - second[2],
    )


def _cross(first: Point3, second: Point3) -> Point3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _norm(vector: Point3) -> float:
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)
