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
    edge_treatment_site_id: str
    edge_family: str
    transition_policy_id: str
    treatment: Treatment
    radius_mm: float
    adjacent_surface_ids: list[str]
    transition_surface_ids: list[str]
    feature_id: str

    @property
    def site_id(self) -> str:
        return self.edge_treatment_site_id

    @property
    def transition_surface_id(self) -> str:
        return self.transition_surface_ids[0]


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

    return _resolve_v08_transition_geometry(surface_graph, transition_policies)


def _resolve_v08_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    surfaces = [_copy_surface(surface) for surface in surface_graph.get("surfaces", [])]
    resolved_graph = {
        **surface_graph,
        "surfaces": surfaces,
        "transition_geometry_status": "resolved_trimmed_surface_graph",
    }
    policy = transition_policies.get("blade_root_to_hub.default")
    site_dicts: list[dict[str, Any]] = []
    transition_failures: list[dict[str, Any]] = []

    if _policy_enabled(policy):
        surface_by_id = {surface["id"]: surface for surface in surfaces}
        for blade_index in _blade_indices_from_pressure_surfaces(surfaces):
            try:
                site_dicts.append(_resolve_blade_root_site(surface_by_id, blade_index, policy))
            except (KeyError, TypeError, ValueError) as exc:
                transition_failures.append(
                    {
                        "edge_treatment_site_id": f"blade_{blade_index}.root_to_hub",
                        "edge_family": "blade_root_to_hub",
                        "transition_policy_id": str(policy.get("policy_id", "blade_root_to_hub.default")),
                        "status": "FAIL",
                        "reason": str(exc),
                    }
                )
    else:
        _remove_surfaces_by_edge_family(surfaces, "blade_root_to_hub")

    quality_checks = [
        {
            "check_id": "transition_geometry_resolver_invoked",
            "status": "PASS",
        },
        {
            "check_id": "required_transition_geometry_resolved",
            "status": "PASS" if not transition_failures else "FAIL",
        },
    ]
    return TransitionResolution(
        surface_graph=resolved_graph,
        edge_treatment_sites=[
            EdgeTreatmentSite(
                edge_treatment_site_id=site["edge_treatment_site_id"],
                edge_family=site["edge_family"],
                transition_policy_id=site["transition_policy_id"],
                treatment=site["treatment"],
                radius_mm=site["radius_mm"],
                adjacent_surface_ids=list(site["adjacent_surface_ids"]),
                transition_surface_ids=list(site["transition_surface_ids"]),
                feature_id=site["transition_surface_ids"][0],
            )
            for site in site_dicts
        ],
        transition_failures=transition_failures,
        quality_checks=quality_checks,
    )


def _resolve_blade_root_site(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    pressure_id = f"blade_{blade_index}_pressure_surface"
    suction_id = f"blade_{blade_index}_suction_surface"
    root_id = f"blade_{blade_index}_root_transition_surface"
    hub_id = "hub_revolve_surface"
    site_id = f"blade_{blade_index}.root_to_hub"

    pressure = surface_by_id[pressure_id]
    suction = surface_by_id[suction_id]
    root = surface_by_id[root_id]
    hub = surface_by_id[hub_id]
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported blade root treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))
    trim_fraction = _trim_fraction_for_radius(radius)

    pressure_grid = pressure["uv_grid"]
    suction_grid = suction["uv_grid"]
    pressure_trim = _offset_boundary_toward_next_v(
        pressure_grid,
        trim_fraction,
        surface_id=pressure_id,
    )
    suction_trim = _offset_boundary_toward_next_v(
        suction_grid,
        trim_fraction,
        surface_id=suction_id,
    )
    if len(pressure_trim) != len(suction_trim):
        raise ValueError(
            f"{pressure_id} and {suction_id} uv_grid u row counts must match"
        )

    if treatment == "chamfer":
        root_grid = [
            [
                [point[0], point[1], point[2]]
                for point in build_chamfer_section(
                    first_trim_point=first,
                    second_trim_point=second,
                    sample_count=3,
                ).points
            ]
            for first, second in zip(pressure_trim, suction_trim)
        ]
    else:
        root_grid = [
            [
                [point[0], point[1], point[2]]
                for point in _fillet_section_between_trim_points(
                    first_trim_point=first,
                    second_trim_point=second,
                    radius_mm=radius,
                    sample_count=5,
                ).points
            ]
            for first, second in zip(pressure_trim, suction_trim)
        ]

    _replace_first_v_column(pressure_grid, pressure_trim)
    _replace_first_v_column(suction_grid, suction_trim)
    root["uv_grid"] = root_grid
    root["edge_treatment_site_id"] = site_id
    root["edge_family"] = "blade_root_to_hub"
    root["transition_policy_id"] = str(policy.get("policy_id", "blade_root_to_hub.default"))
    root["treatment"] = treatment
    root["radius_mm"] = radius
    root["transition_geometry"] = f"resolved_{treatment}_patch"
    root["role"] = "blade_root_chamfer" if treatment == "chamfer" else "blade_root_fillet"
    root["transition_quality"] = _transition_grid_quality(root_grid)

    _mark_trimmed_boundary(pressure, "hub_root", site_id)
    _mark_trimmed_boundary(suction, "hub_root", site_id)
    _mark_trimmed_boundary(hub, f"blade_{blade_index}_root", site_id)
    return {
        "edge_treatment_site_id": site_id,
        "edge_family": "blade_root_to_hub",
        "transition_policy_id": root["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [pressure_id, suction_id, hub_id],
        "transition_surface_ids": [root_id],
    }


def _copy_surface(surface: dict[str, Any]) -> dict[str, Any]:
    copied = {**surface}
    if "uv_grid" in copied:
        copied["uv_grid"] = _copy_uv_grid(copied["uv_grid"])
    if "display" in copied:
        copied["display"] = dict(copied["display"])
    return copied


def _copy_uv_grid(uv_grid: Any) -> Any:
    if not isinstance(uv_grid, list):
        return uv_grid

    copied_grid = []
    for row in uv_grid:
        if not isinstance(row, list):
            copied_grid.append(row)
            continue
        copied_grid.append([
            list(point) if isinstance(point, (list, tuple)) else point
            for point in row
        ])
    return copied_grid


def _policy_enabled(policy: dict[str, Any] | None) -> bool:
    return bool(
        policy
        and policy.get("enabled")
        and policy.get("treatment") != "none"
        and float(policy.get("radius_mm", 0.0)) > 0.0
    )


def _trim_fraction_for_radius(radius_mm: float) -> float:
    return max(0.02, min(0.35, radius_mm / 120.0))


def _offset_boundary_toward_next_v(
    grid: list[list[list[float]]],
    fraction: float,
    *,
    surface_id: str,
) -> list[Point3]:
    if not isinstance(grid, list) or not grid:
        raise ValueError(f"{surface_id} uv_grid must contain at least 1 u row")

    boundary = []
    for row_index, row in enumerate(grid):
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError(
                f"{surface_id} uv_grid row {row_index} must contain at least 2 v points"
            )
        boundary.append(
            _lerp_point(
                _point3_from_grid_point(
                    row[0],
                    surface_id=surface_id,
                    row_index=row_index,
                    point_index=0,
                ),
                _point3_from_grid_point(
                    row[1],
                    surface_id=surface_id,
                    row_index=row_index,
                    point_index=1,
                ),
                fraction,
            )
        )
    return boundary


def _point3_from_grid_point(
    point: Any,
    *,
    surface_id: str,
    row_index: int,
    point_index: int,
) -> Point3:
    if not isinstance(point, (list, tuple)) or len(point) < 3:
        raise ValueError(
            f"{surface_id} uv_grid row {row_index} point {point_index} must contain 3 coordinates"
        )
    return (float(point[0]), float(point[1]), float(point[2]))


def _replace_first_v_column(grid: list[list[list[float]]], boundary: list[Point3]) -> None:
    for row, point in zip(grid, boundary):
        row[0] = [point[0], point[1], point[2]]


def _mark_trimmed_boundary(surface: dict[str, Any], key: str, site_id: str) -> None:
    trimmed = dict(surface.get("trimmed_boundaries", {}))
    trimmed[key] = {"edge_treatment_site_id": site_id}
    surface["trimmed_boundaries"] = trimmed


def _remove_surfaces_by_edge_family(surfaces: list[dict[str, Any]], edge_family: str) -> None:
    surfaces[:] = [surface for surface in surfaces if surface.get("edge_family") != edge_family]


def _blade_indices_from_pressure_surfaces(surfaces: list[dict[str, Any]]) -> list[int]:
    indices = []
    for surface in surfaces:
        surface_id = str(surface.get("id", ""))
        prefix = "blade_"
        suffix = "_pressure_surface"
        if surface_id.startswith(prefix) and surface_id.endswith(suffix):
            indices.append(int(surface_id[len(prefix):-len(suffix)]))
    return sorted(indices)


def _fillet_section_between_trim_points(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    radius_mm: float,
    sample_count: int,
) -> TransitionSection:
    if sample_count < 3:
        raise ValueError("fillet section sample_count must be at least 3")
    chord = _subtract(second_trim_point, first_trim_point)
    chord_length = _norm(chord)
    if chord_length <= 1.0e-9:
        raise ValueError("fillet section endpoints must be distinct")
    bump = min(float(radius_mm), chord_length * 0.5) * 0.25
    radial = _unit_xy_midpoint_direction(first_trim_point, second_trim_point)
    points = []
    for t in _sample_parameters(sample_count):
        base = _lerp_point(first_trim_point, second_trim_point, t)
        offset = math.sin(math.pi * t) * bump
        points.append(
            (
                base[0] + radial[0] * offset,
                base[1] + radial[1] * offset,
                base[2],
            )
        )
    points[0] = first_trim_point
    points[-1] = second_trim_point
    return TransitionSection(
        treatment="fillet",
        radius_mm=float(radius_mm),
        points=points,
        quality={
            "max_mid_section_bump": bump,
            "sample_count": sample_count,
        },
    )


def _unit_xy_midpoint_direction(first: Point3, second: Point3) -> Point3:
    midpoint = (
        (first[0] + second[0]) * 0.5,
        (first[1] + second[1]) * 0.5,
        0.0,
    )
    length = math.hypot(midpoint[0], midpoint[1])
    if length <= 1.0e-9:
        return (1.0, 0.0, 0.0)
    return (midpoint[0] / length, midpoint[1] / length, 0.0)


def _transition_grid_quality(grid: list[list[list[float]]]) -> dict[str, Any]:
    return {
        "u_count": len(grid),
        "v_count": len(grid[0]) if grid else 0,
        "has_resolved_patch": bool(grid),
    }


def _sample_parameters(sample_count: int) -> list[float]:
    return [index / (sample_count - 1) for index in range(sample_count)]


def _shortest_angle_delta(start_angle: float, end_angle: float) -> float:
    return (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi


def _lerp(first: float, second: float, t: float) -> float:
    return first + (second - first) * t


def _lerp_point(first: Point3, second: Point3, t: float) -> Point3:
    return (
        _lerp(first[0], second[0], t),
        _lerp(first[1], second[1], t),
        _lerp(first[2], second[2], t),
    )


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
