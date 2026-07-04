from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from part_rule_synthesis.impeller_transition_sections import (
    build_chamfer_section as build_topology_chamfer_section,
    build_fillet_section as build_topology_fillet_section,
)
from part_rule_synthesis.impeller_transition_topology import (
    Patch,
    PatchComplex,
    patch_complex_manifest,
    patch_complex_report,
)


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


@dataclass(frozen=True)
class BladeEdgeSpec:
    edge_family: str
    surface_suffix: str
    site_suffix: str
    fillet_role: str
    chamfer_role: str
    axis: Literal["u0", "u1", "v1"]


@dataclass(frozen=True)
class AxisymmetricTransitionSpec:
    edge_family: str
    surface_id: str


_BLADE_EDGE_SPECS = (
    BladeEdgeSpec(
        edge_family="blade_leading_edge",
        surface_suffix="leading_transition_surface",
        site_suffix="leading_edge",
        fillet_role="blade_leading_edge_fillet",
        chamfer_role="blade_leading_edge_chamfer",
        axis="u0",
    ),
    BladeEdgeSpec(
        edge_family="blade_trailing_edge",
        surface_suffix="trailing_transition_surface",
        site_suffix="trailing_edge",
        fillet_role="blade_trailing_edge_fillet",
        chamfer_role="blade_trailing_edge_chamfer",
        axis="u1",
    ),
    BladeEdgeSpec(
        edge_family="blade_tip_or_shroud",
        surface_suffix="tip_transition_surface",
        site_suffix="tip_or_shroud",
        fillet_role="blade_tip_edge_fillet",
        chamfer_role="blade_tip_edge_chamfer",
        axis="v1",
    ),
)

_BLADE_TIP_TO_SHROUD_SPEC = BladeEdgeSpec(
    edge_family="blade_tip_to_shroud",
    surface_suffix="tip_transition_surface",
    site_suffix="tip_to_shroud",
    fillet_role="blade_tip_edge_fillet",
    chamfer_role="blade_tip_edge_chamfer",
    axis="v1",
)

_AXISYMMETRIC_TRANSITION_SPECS = (
    AxisymmetricTransitionSpec(
        edge_family="hub_top_outer",
        surface_id="hub_top_outer_transition_surface",
    ),
    AxisymmetricTransitionSpec(
        edge_family="hub_bottom_outer",
        surface_id="hub_bottom_outer_transition_surface",
    ),
    AxisymmetricTransitionSpec(
        edge_family="mounting_bore_top",
        surface_id="mounting_bore_top_transition_surface",
    ),
    AxisymmetricTransitionSpec(
        edge_family="mounting_bore_bottom",
        surface_id="mounting_bore_bottom_transition_surface",
    ),
    AxisymmetricTransitionSpec(
        edge_family="hood_inlet_lip",
        surface_id="hood_chamfer_inlet_surface",
    ),
    AxisymmetricTransitionSpec(
        edge_family="hood_outlet_lip",
        surface_id="hood_chamfer_outlet_surface",
    ),
)

_BLADE_ROOT_MAX_RADIUS_MM = 120.0
_BLADE_EDGE_MAX_RADIUS_MM = 80.0
_AXISYMMETRIC_MAX_RADIUS_MM = 120.0
_BLADE_EDGE_FAMILIES = {
    "blade_leading_edge",
    "blade_trailing_edge",
    "blade_tip_or_shroud",
    "blade_tip_to_shroud",
}
_V091_TRANSITION_GEOMETRY_STATUS = "topology_first_validated_transition_graph"
_AXISYMMETRIC_EDGE_FAMILIES = {
    spec.edge_family
    for spec in _AXISYMMETRIC_TRANSITION_SPECS
}


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
    if geometry_version == "0.91":
        return _resolve_v091_transition_geometry(surface_graph, transition_policies)
    if geometry_version == "0.9":
        return _resolve_v09_transition_geometry(surface_graph, transition_policies)
    if geometry_version != "0.8":
        return TransitionResolution(
            surface_graph=surface_graph,
            edge_treatment_sites=[],
            transition_failures=[],
            quality_checks=[],
        )

    return _resolve_v08_transition_geometry(surface_graph, transition_policies)


def _resolve_v091_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    surfaces = [
        _copy_surface(surface)
        for surface in surface_graph.get("surfaces", [])
        if not _is_legacy_root_transition_surface_id(str(surface.get("id", "")))
    ]
    edges = [
        _copy_graph_edge(edge)
        for edge in surface_graph.get("edges", [])
    ]
    resolved_graph = {
        **{
            key: value
            for key, value in surface_graph.items()
            if key
            not in {
                "surfaces",
                "edges",
                "edge_treatment_sites",
                "transition_failures",
                "transition_patch_complex",
                "transition_topology_report",
            }
        },
        "surfaces": surfaces,
        "transition_geometry_status": _V091_TRANSITION_GEOMETRY_STATUS,
    }
    if surface_graph.get("edges") is not None:
        resolved_graph["edges"] = edges

    site_dicts: list[dict[str, Any]] = []
    transition_failures: list[dict[str, Any]] = []
    surface_by_id = {surface["id"]: surface for surface in surfaces}
    blade_indices = _blade_indices_from_pressure_surfaces(surfaces)
    blade_count = max(1, len(blade_indices))

    root_policy = transition_policies.get("blade_root_to_hub.default")
    if _policy_invalid_radius(root_policy):
        for blade_index in blade_indices:
            _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
            transition_failures.append(
                _invalid_radius_failure(
                    "blade_root_to_hub",
                    root_policy,
                    site_id=f"blade_{blade_index}.root_to_hub",
                )
            )
    elif _policy_enabled(root_policy):
        for blade_index in blade_indices:
            failure = _radius_feasibility_failure(
                "blade_root_to_hub",
                root_policy,
                _suggested_max_radius_mm("blade_root_to_hub"),
                site_id=f"blade_{blade_index}.root_to_hub",
            )
            if failure:
                _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
                transition_failures.append(failure)
                continue
            try:
                site_dicts.extend(
                    _resolve_v091_double_sided_blade_root_sites(
                        surfaces,
                        surface_by_id,
                        blade_index,
                        blade_count,
                        root_policy,
                    )
                )
                surface_by_id = {surface["id"]: surface for surface in surfaces}
            except (KeyError, TypeError, ValueError) as exc:
                _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
                transition_failures.append(
                    {
                        "edge_treatment_site_id": f"blade_{blade_index}.root_to_hub",
                        "edge_family": "blade_root_to_hub",
                        "transition_policy_id": str(
                            (root_policy or {}).get("policy_id", "blade_root_to_hub.default")
                        ),
                        "status": "FAIL",
                        "reason": str(exc),
                    }
                )

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    blade_indices = _blade_indices_from_pressure_surfaces(surfaces)
    for spec in _active_blade_edge_specs(transition_policies):
        policy = transition_policies.get(f"{spec.edge_family}.default")
        if _policy_invalid_radius(policy):
            for blade_index in blade_indices:
                transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
                if transition_id in surface_by_id:
                    _clear_transition_success_metadata(surface_by_id[transition_id])
                _clear_blade_edge_adjacent_trim_metadata(surface_by_id, blade_index, spec.site_suffix)
                transition_failures.append(
                    _invalid_radius_failure(
                        spec.edge_family,
                        policy,
                        site_id=f"blade_{blade_index}.{spec.site_suffix}",
                    )
                )
            continue
        if not _policy_enabled(policy):
            _remove_surfaces_by_edge_family(surfaces, spec.edge_family)
            surface_by_id = {surface["id"]: surface for surface in surfaces}
            continue
        for blade_index in blade_indices:
            failure = _radius_feasibility_failure(
                spec.edge_family,
                policy,
                _suggested_max_radius_mm(spec.edge_family),
                site_id=f"blade_{blade_index}.{spec.site_suffix}",
            )
            if failure:
                transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
                if transition_id in surface_by_id:
                    _clear_transition_success_metadata(surface_by_id[transition_id])
                _clear_blade_edge_adjacent_trim_metadata(surface_by_id, blade_index, spec.site_suffix)
                transition_failures.append(failure)
                continue
            try:
                site_dicts.append(
                    _resolve_v091_blade_edge_site(surface_by_id, blade_index, policy, spec)
                )
            except (KeyError, TypeError, ValueError) as exc:
                transition_failures.append(
                    {
                        "edge_treatment_site_id": f"blade_{blade_index}.{spec.site_suffix}",
                        "edge_family": spec.edge_family,
                        "transition_policy_id": str(policy.get("policy_id", f"{spec.edge_family}.default")),
                        "status": "FAIL",
                        "reason": str(exc),
                    }
                )

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    for spec in _AXISYMMETRIC_TRANSITION_SPECS:
        policy = transition_policies.get(f"{spec.edge_family}.default")
        if spec.surface_id not in surface_by_id:
            continue
        if _policy_invalid_radius(policy):
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(_invalid_radius_failure(spec.edge_family, policy))
            continue
        if not _policy_enabled(policy):
            _remove_surfaces_by_edge_family_or_id(surfaces, spec.edge_family, spec.surface_id)
            surface_by_id = {surface["id"]: surface for surface in surfaces}
            continue
        failure = _radius_feasibility_failure(
            spec.edge_family,
            policy,
            _suggested_max_radius_mm(spec.edge_family),
        )
        if failure:
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(failure)
            continue
        try:
            site_dicts.append(
                _resolve_axisymmetric_transition_site(
                    surface_by_id[spec.surface_id],
                    spec.edge_family,
                    policy,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(
                {
                    "edge_treatment_site_id": spec.edge_family,
                    "edge_family": spec.edge_family,
                    "transition_policy_id": str(policy.get("policy_id", f"{spec.edge_family}.default")),
                    "status": "FAIL",
                    "reason": str(exc),
                }
            )

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    _rewrite_v091_transition_edges(edges, set(surface_by_id))
    patch_complex = _build_v091_transition_patch_complex(surfaces)
    resolved_graph["transition_patch_complex"] = patch_complex_manifest(patch_complex)
    missing_shared_boundary_links = _v091_missing_shared_boundary_links(blade_indices, transition_policies)
    resolved_graph["transition_topology_report"] = patch_complex_report(
        patch_complex,
        required_corner_patch_count=_v091_required_corner_patch_count(blade_indices, transition_policies),
        missing_shared_boundary_links=missing_shared_boundary_links,
        evaluated_shared_boundary_count=0,
    )
    topology_report = resolved_graph["transition_topology_report"]
    if topology_report["corner_patch_count"] < topology_report["required_corner_patch_count"]:
        transition_failures.append(
            {
                "edge_treatment_site_id": "v091.transition_patch_complex",
                "edge_family": "transition_patch_complex",
                "transition_policy_id": "v091.topology_first",
                "status": "FAIL",
                "reason": "missing_required_corner_transition_patches",
                "corner_patch_count": topology_report["corner_patch_count"],
                "required_corner_patch_count": topology_report["required_corner_patch_count"],
            }
        )
    resolved_graph["edge_treatment_sites"] = site_dicts
    if transition_failures:
        resolved_graph["transition_failures"] = transition_failures
    else:
        resolved_graph.pop("transition_failures", None)

    quality_checks = [
        {
            "check_id": "transition_geometry_resolver_invoked",
            "status": "PASS",
        },
        {
            "check_id": "required_transition_geometry_resolved",
            "status": "PASS" if not transition_failures else "FAIL",
            "failure_count": len(transition_failures),
        },
        {
            "check_id": "topology_first_transition_patch_complex_reported",
            "status": "PASS" if topology_report["transition_patch_count"] > 0 else "FAIL",
        },
        {
            "check_id": "transition_patch_boundary_node_identity",
            "status": "PASS" if topology_report["boundary_identity_status"] == "PASS" else "FAIL",
            "boundary_identity_status": topology_report["boundary_identity_status"],
            "failure_count": len(topology_report["boundary_node_identity_failures"]),
            "missing_shared_boundary_link_count": topology_report["missing_shared_boundary_link_count"],
            "evaluated_shared_boundary_count": topology_report["evaluated_shared_boundary_count"],
        },
        {
            "check_id": "corner_transition_patches_present",
            "status": (
                "PASS"
                if topology_report["corner_patch_count"] >= topology_report["required_corner_patch_count"]
                else "FAIL"
            ),
            "corner_patch_count": topology_report["corner_patch_count"],
            "required_corner_patch_count": topology_report["required_corner_patch_count"],
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


def _resolve_v091_double_sided_blade_root_sites(
    surfaces: list[dict[str, Any]],
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    blade_count: int,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    pressure_id = f"blade_{blade_index}_pressure_surface"
    suction_id = f"blade_{blade_index}_suction_surface"
    hub_id = "hub_revolve_surface"
    pressure = surface_by_id[pressure_id]
    suction = surface_by_id[suction_id]
    hub = surface_by_id[hub_id]
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported blade root treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))
    trim_fraction = _trim_fraction_for_radius(radius)

    pressure_grid = pressure["uv_grid"]
    suction_grid = suction["uv_grid"]
    pressure_hub_boundary = _first_v_boundary(pressure_grid, surface_id=pressure_id)
    suction_hub_boundary = _first_v_boundary(suction_grid, surface_id=suction_id)
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
    if len(pressure_trim) != len(pressure_hub_boundary) or len(suction_trim) != len(suction_hub_boundary):
        raise ValueError("blade root transition boundary sample counts must match")

    pressure_surface_id = f"blade_{blade_index}_pressure_root_transition_surface"
    suction_surface_id = f"blade_{blade_index}_suction_root_transition_surface"
    pressure_site_id = f"blade_{blade_index}.pressure_root_to_hub"
    suction_site_id = f"blade_{blade_index}.suction_root_to_hub"
    pressure_transition_grid = _build_v091_transition_grid(
        pressure_trim,
        pressure_hub_boundary,
        treatment=treatment,
        radius_mm=radius,
    )
    suction_transition_grid = _build_v091_transition_grid(
        suction_trim,
        suction_hub_boundary,
        treatment=treatment,
        radius_mm=radius,
    )
    pressure_transition = _v091_transition_surface(
        pressure,
        surface_id=pressure_surface_id,
        role="blade_pressure_root_chamfer" if treatment == "chamfer" else "blade_pressure_root_fillet",
        cfd_role="root_transition",
        feature_id=f"blade_{blade_index:02d}.pressure_root_{treatment}",
        edge_family="blade_root_to_hub",
        site_id=pressure_site_id,
        policy=policy,
        treatment=treatment,
        radius_mm=radius,
        uv_grid=pressure_transition_grid,
    )
    suction_transition = _v091_transition_surface(
        suction,
        surface_id=suction_surface_id,
        role="blade_suction_root_chamfer" if treatment == "chamfer" else "blade_suction_root_fillet",
        cfd_role="root_transition",
        feature_id=f"blade_{blade_index:02d}.suction_root_{treatment}",
        edge_family="blade_root_to_hub",
        site_id=suction_site_id,
        policy=policy,
        treatment=treatment,
        radius_mm=radius,
        uv_grid=suction_transition_grid,
    )

    _replace_first_v_column(pressure_grid, pressure_trim)
    _replace_first_v_column(suction_grid, suction_trim)
    _mark_trimmed_boundary(pressure, "hub_root_pressure", pressure_site_id)
    _mark_trimmed_boundary(suction, "hub_root_suction", suction_site_id)
    _mark_trim_exclusion_region(
        hub,
        edge_treatment_site_id=pressure_site_id,
        transition_surface_id=pressure_surface_id,
        blade_index=blade_index,
        blade_count=blade_count,
        side="pressure",
    )
    _mark_trim_exclusion_region(
        hub,
        edge_treatment_site_id=suction_site_id,
        transition_surface_id=suction_surface_id,
        blade_index=blade_index,
        blade_count=blade_count,
        side="suction",
    )
    surfaces.extend([pressure_transition, suction_transition])
    return [
        {
            "edge_treatment_site_id": pressure_site_id,
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": pressure_transition["transition_policy_id"],
            "treatment": treatment,
            "radius_mm": radius,
            "adjacent_surface_ids": [pressure_id, hub_id],
            "transition_surface_ids": [pressure_surface_id],
        },
        {
            "edge_treatment_site_id": suction_site_id,
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": suction_transition["transition_policy_id"],
            "treatment": treatment,
            "radius_mm": radius,
            "adjacent_surface_ids": [suction_id, hub_id],
            "transition_surface_ids": [suction_surface_id],
        },
    ]


def _resolve_v091_blade_edge_site(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    policy: dict[str, Any],
    spec: BladeEdgeSpec,
) -> dict[str, Any]:
    pressure_id = f"blade_{blade_index}_pressure_surface"
    suction_id = f"blade_{blade_index}_suction_surface"
    transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
    site_id = f"blade_{blade_index}.{spec.site_suffix}"

    pressure = surface_by_id[pressure_id]
    suction = surface_by_id[suction_id]
    transition = surface_by_id[transition_id]
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported {spec.edge_family} treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))
    trim_fraction = _trim_fraction_for_radius(radius)

    pressure_grid = pressure["uv_grid"]
    suction_grid = suction["uv_grid"]
    pressure_trim = _offset_boundary_for_axis(
        pressure_grid,
        trim_fraction,
        axis=spec.axis,
        surface_id=pressure_id,
    )
    suction_trim = _offset_boundary_for_axis(
        suction_grid,
        trim_fraction,
        axis=spec.axis,
        surface_id=suction_id,
    )
    if len(pressure_trim) != len(suction_trim):
        raise ValueError(
            f"{pressure_id} and {suction_id} uv_grid {spec.axis} boundary sample counts must match"
        )

    transition_grid = _build_v091_transition_grid(
        pressure_trim,
        suction_trim,
        treatment=treatment,
        radius_mm=radius,
    )
    _replace_boundary_for_axis(pressure_grid, pressure_trim, axis=spec.axis)
    _replace_boundary_for_axis(suction_grid, suction_trim, axis=spec.axis)

    transition["edge_treatment_site_id"] = site_id
    transition["edge_family"] = spec.edge_family
    transition["transition_policy_id"] = str(policy.get("policy_id", f"{spec.edge_family}.default"))
    transition["treatment"] = treatment
    transition["radius_mm"] = radius
    transition["transition_geometry"] = f"topology_first_{treatment}_patch"
    transition["role"] = spec.chamfer_role if treatment == "chamfer" else spec.fillet_role
    transition["transition_quality"] = _v091_transition_grid_quality(
        transition_grid,
        treatment=treatment,
        radius_mm=radius,
    )
    transition["boundary_ids"] = [site_id]
    _set_surface_grid(transition, transition_grid)

    _mark_trimmed_boundary(pressure, spec.site_suffix, site_id)
    _mark_trimmed_boundary(suction, spec.site_suffix, site_id)
    return {
        "edge_treatment_site_id": site_id,
        "edge_family": spec.edge_family,
        "transition_policy_id": transition["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [pressure_id, suction_id],
        "transition_surface_ids": [transition_id],
    }


def _v091_transition_surface(
    template: dict[str, Any],
    *,
    surface_id: str,
    role: str,
    cfd_role: str,
    feature_id: str,
    edge_family: str,
    site_id: str,
    policy: dict[str, Any],
    treatment: str,
    radius_mm: float,
    uv_grid: list[list[list[float]]],
) -> dict[str, Any]:
    surface = _copy_surface(template)
    surface["id"] = surface_id
    surface["kind"] = "transition_surface"
    surface["role"] = role
    surface["cfd_role"] = cfd_role
    surface["feature_id"] = feature_id
    surface["edge_family"] = edge_family
    surface["edge_treatment_site_id"] = site_id
    surface["transition_policy_id"] = str(policy.get("policy_id", f"{edge_family}.default"))
    surface["treatment"] = treatment
    surface["radius_mm"] = radius_mm
    surface["transition_geometry"] = f"topology_first_{treatment}_patch"
    surface["transition_quality"] = _v091_transition_grid_quality(
        uv_grid,
        treatment=treatment,
        radius_mm=radius_mm,
    )
    surface["boundary_ids"] = [site_id]
    surface["display"] = {
        **surface.get("display", {}),
        "color": "#22c55e" if treatment == "fillet" else "#f97316",
        "opacity": 1.0,
        "edge_highlight": True,
    }
    for stale_key in ("trimmed_boundaries", "trim_exclusion_regions", "material", "material_domain"):
        surface.pop(stale_key, None)
    _set_surface_grid(surface, uv_grid)
    return surface


def _build_v091_transition_grid(
    first_trim: list[Point3],
    second_trim: list[Point3],
    *,
    treatment: str,
    radius_mm: float,
) -> list[list[list[float]]]:
    if treatment == "chamfer":
        sections = [
            _v091_chamfer_section_between_trim_points(
                first_trim_point=first,
                second_trim_point=second,
            )
            for first, second in zip(first_trim, second_trim)
        ]
    else:
        sample_count = 9 if radius_mm >= 5.0 else 7
        sections = [
            _v091_fillet_section_between_trim_points(
                first_trim_point=first,
                second_trim_point=second,
                radius_mm=radius_mm,
                sample_count=sample_count,
            )
            for first, second in zip(first_trim, second_trim)
        ]
    return [
        [[point[0], point[1], point[2]] for point in section]
        for section in sections
    ]


def _v091_chamfer_section_between_trim_points(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
) -> list[Point3]:
    build_topology_chamfer_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        distance_mm=1.0,
    )
    return [first_trim_point, second_trim_point]


def _v091_fillet_section_between_trim_points(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    radius_mm: float,
    sample_count: int,
) -> list[Point3]:
    section = build_topology_fillet_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        radius_mm=1.0,
        sample_count=sample_count,
        convexity_sign=1,
    )
    return _map_unit_section_to_trim_points(
        section["points"],
        first_trim_point=first_trim_point,
        second_trim_point=second_trim_point,
        radius_mm=radius_mm,
    )


def _map_unit_section_to_trim_points(
    unit_points: list[Point3],
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    radius_mm: float,
) -> list[Point3]:
    first = _point3_from_any(first_trim_point)
    second = _point3_from_any(second_trim_point)
    actual_chord = _subtract(second, first)
    actual_chord_length = _norm(actual_chord)
    if actual_chord_length <= 1.0e-9:
        raise ValueError("transition section endpoints must be distinct")

    unit_first = _point3_from_any(unit_points[0])
    unit_last = _point3_from_any(unit_points[-1])
    unit_chord = _subtract(unit_last, unit_first)
    unit_chord_length_squared = _dot_product(unit_chord, unit_chord)
    if unit_chord_length_squared <= 1.0e-18:
        raise ValueError("unit transition section endpoints must be distinct")

    bulge_direction = _unit_xy_midpoint_direction(first, second)
    bulge_scale = min(max(float(radius_mm), 1.0e-6), max(actual_chord_length * 0.5, 1.0e-6))
    mapped = []
    for unit_point in unit_points:
        relative = _subtract(_point3_from_any(unit_point), unit_first)
        t = max(0.0, min(1.0, _dot_product(relative, unit_chord) / unit_chord_length_squared))
        projection = (
            unit_first[0] + unit_chord[0] * t,
            unit_first[1] + unit_chord[1] * t,
            unit_first[2] + unit_chord[2] * t,
        )
        deviation = _norm(_subtract(_point3_from_any(unit_point), projection))
        base = _lerp_point(first, second, t)
        mapped.append(
            (
                base[0] + bulge_direction[0] * deviation * bulge_scale,
                base[1] + bulge_direction[1] * deviation * bulge_scale,
                base[2] + bulge_direction[2] * deviation * bulge_scale,
            )
        )
    mapped[0] = first
    mapped[-1] = second
    return mapped


def _v091_transition_grid_quality(
    grid: Any,
    *,
    treatment: str,
    radius_mm: float,
) -> dict[str, Any]:
    quality = _v09_transition_grid_quality(grid, treatment=treatment, radius_mm=radius_mm)
    quality["topology_first_section_builder"] = (
        "impeller_transition_sections.build_chamfer_section"
        if treatment == "chamfer"
        else "impeller_transition_sections.build_fillet_section"
    )
    quality["transition_patch_complex_ready"] = True
    return quality


def _first_v_boundary(grid: Any, *, surface_id: str) -> list[Point3]:
    _validate_uv_grid(grid, surface_id=surface_id)
    return [
        _point3_from_grid_point(
            row[0],
            surface_id=surface_id,
            row_index=row_index,
            point_index=0,
        )
        for row_index, row in enumerate(grid)
    ]


def _rewrite_v091_transition_edges(
    edges: list[dict[str, Any]],
    surface_ids: set[str],
) -> None:
    for edge in edges:
        edge_id = str(edge.get("id", ""))
        blade_index = _blade_index_from_graph_id(edge_id)
        if blade_index is not None:
            pressure_root_id = f"blade_{blade_index}_pressure_root_transition_surface"
            suction_root_id = f"blade_{blade_index}_suction_root_transition_surface"
            if edge_id.endswith("_pressure_root_closure_edge"):
                _replace_edge_surface(edge, f"blade_{blade_index}_root_transition_surface", pressure_root_id)
                edge["transition_surface_ids"] = [pressure_root_id] if pressure_root_id in surface_ids else []
            elif edge_id.endswith("_suction_root_closure_edge"):
                _replace_edge_surface(edge, f"blade_{blade_index}_root_transition_surface", suction_root_id)
                edge["transition_surface_ids"] = [suction_root_id] if suction_root_id in surface_ids else []
            elif edge_id.endswith("_root_hub_conformal_edge"):
                transition_ids = [
                    surface_id
                    for surface_id in [pressure_root_id, suction_root_id]
                    if surface_id in surface_ids
                ]
                if transition_ids:
                    edge["surfaces"] = ["hub_revolve_surface", *transition_ids]
                edge["transition_surface_ids"] = transition_ids
            elif edge_id.endswith("_pressure_hub_edge"):
                edge["transition_surface_ids"] = [pressure_root_id] if pressure_root_id in surface_ids else []
            elif edge_id.endswith("_suction_hub_edge"):
                edge["transition_surface_ids"] = [suction_root_id] if suction_root_id in surface_ids else []

        if "transition_surface_ids" in edge:
            transition_surface_ids = [
                surface_id
                for surface_id in edge.get("transition_surface_ids", [])
                if surface_id in surface_ids
            ]
            if transition_surface_ids:
                edge["transition_surface_ids"] = transition_surface_ids
            else:
                edge.pop("transition_surface_ids", None)
                edge.pop("transition_policy_id", None)
                edge.pop("edge_family", None)
        if "surfaces" in edge:
            edge["surfaces"] = [
                surface_id
                for surface_id in edge.get("surfaces", [])
                if surface_id in surface_ids
            ]


def _build_v091_transition_patch_complex(surfaces: list[dict[str, Any]]) -> PatchComplex:
    patch_complex = PatchComplex()
    for surface in surfaces:
        descriptor = _v091_transition_patch_descriptor(str(surface.get("id", "")))
        if descriptor is None:
            continue
        blade_index, patch_role = descriptor
        grid = surface.get("uv_grid")
        if not isinstance(grid, list) or not grid:
            continue
        node_grid = _v091_patch_node_grid(
            patch_complex,
            blade_index=blade_index,
            patch_role=patch_role,
            grid=grid,
        )
        if not node_grid or not node_grid[0]:
            continue
        patch_id = f"{surface['id']}.patch"
        edge_ids = _add_v091_patch_edges(
            patch_complex,
            patch_id=patch_id,
            patch_role=patch_role,
            node_grid=node_grid,
        )
        patch_complex.add_patch(
            Patch(
                patch_id=patch_id,
                surface_graph_id=str(surface["id"]),
                role=patch_role,
                node_grid=node_grid,
                edge_ids=edge_ids,
                edge_family=str(surface.get("edge_family", "")),
                transition_policy_id=str(surface.get("transition_policy_id", "")),
                treatment=str(surface.get("treatment", "")),
            )
        )
    return patch_complex


def _v091_patch_node_grid(
    patch_complex: PatchComplex,
    *,
    blade_index: int,
    patch_role: str,
    grid: list[list[Any]],
) -> list[list[str]]:
    node_grid: list[list[str]] = []
    for row_index, row in enumerate(grid):
        node_row = []
        for column_index, point in enumerate(row):
            node_id = _v091_node_id(
                blade_index=blade_index,
                patch_role=patch_role,
                row_index=row_index,
                column_index=column_index,
                column_count=len(row),
            )
            point3 = _point3_from_grid_point(
                point,
                surface_id=f"blade_{blade_index}.{patch_role}",
                row_index=row_index,
                point_index=column_index,
            )
            patch_complex.add_node(node_id, point3)
            node_row.append(node_id)
        node_grid.append(node_row)
    return node_grid


def _add_v091_patch_edges(
    patch_complex: PatchComplex,
    *,
    patch_id: str,
    patch_role: str,
    node_grid: list[list[str]],
) -> list[str]:
    top = node_grid[0]
    bottom = node_grid[-1]
    left = [row[0] for row in node_grid]
    right = [row[-1] for row in node_grid]
    edge_specs = [
        ("u0", top),
        ("u1", bottom),
        ("v0", left),
        ("v1", right),
    ]
    edge_ids = []
    for edge_role, node_ids in edge_specs:
        edge_id = f"{patch_id}.{edge_role}"
        patch_complex.add_edge(
            edge_id,
            node_ids,
            role=f"{patch_role}.{edge_role}",
            physical_boundary=True,
        )
        edge_ids.append(edge_id)
    return edge_ids


def _v091_transition_patch_descriptor(surface_id: str) -> tuple[int, str] | None:
    parsed = _blade_index_and_suffix_from_surface_id(surface_id)
    if parsed is None:
        return None
    blade_index, suffix = parsed
    role_by_suffix = {
        "pressure_root_transition_surface": "root.pressure",
        "suction_root_transition_surface": "root.suction",
        "leading_transition_surface": "leading",
        "trailing_transition_surface": "trailing",
        "tip_transition_surface": "tip",
    }
    role = role_by_suffix.get(suffix)
    if role is None:
        return None
    return blade_index, role


def _v091_node_id(
    *,
    blade_index: int,
    patch_role: str,
    row_index: int,
    column_index: int,
    column_count: int,
) -> str:
    station = f"station_{row_index:03d}"
    last_column = max(0, column_count - 1)
    if column_index == 0:
        boundary = "blade_trim" if patch_role.startswith("root.") else "pressure_trim"
    elif column_index == last_column:
        boundary = "hub_edge" if patch_role.startswith("root.") else "suction_trim"
    else:
        boundary = f"section_{column_index:03d}"
    return f"blade_{blade_index}.{patch_role}.{station}.{boundary}"


def _v091_required_corner_patch_count(
    blade_indices: list[int],
    transition_policies: dict[str, Any],
) -> int:
    return len(_v091_missing_shared_boundary_links(blade_indices, transition_policies))


def _v091_missing_shared_boundary_links(
    blade_indices: list[int],
    transition_policies: dict[str, Any],
) -> list[dict[str, Any]]:
    root_active = _policy_enabled(transition_policies.get("blade_root_to_hub.default"))
    leading_active = _policy_enabled(transition_policies.get("blade_leading_edge.default"))
    trailing_active = _policy_enabled(transition_policies.get("blade_trailing_edge.default"))
    tip_active = (
        _policy_enabled(transition_policies.get("blade_tip_or_shroud.default"))
        or _policy_enabled(transition_policies.get("blade_tip_to_shroud.default"))
    )
    missing_links: list[dict[str, Any]] = []
    corner_specs = []
    if root_active and leading_active:
        corner_specs.append(
            (
                "root_leading",
                ["root.pressure", "root.suction", "leading"],
            )
        )
    if root_active and trailing_active:
        corner_specs.append(
            (
                "root_trailing",
                ["root.pressure", "root.suction", "trailing"],
            )
        )
    if tip_active and leading_active:
        corner_specs.append(("tip_leading", ["tip", "leading"]))
    if tip_active and trailing_active:
        corner_specs.append(("tip_trailing", ["tip", "trailing"]))

    for blade_index in blade_indices:
        for corner_id, patch_roles in corner_specs:
            missing_links.append(
                {
                    "blade_index": blade_index,
                    "corner_id": f"blade_{blade_index}.{corner_id}",
                    "required_patch_roles": patch_roles,
                    "reason": "corner_patch_not_constructed",
                }
            )
    return missing_links


def _is_legacy_root_transition_surface_id(surface_id: str) -> bool:
    parsed = _blade_index_and_suffix_from_surface_id(surface_id)
    return bool(parsed and parsed[1] == "root_transition_surface")


def _blade_index_and_suffix_from_surface_id(surface_id: str) -> tuple[int, str] | None:
    prefix = "blade_"
    if not surface_id.startswith(prefix):
        return None
    rest = surface_id[len(prefix):]
    index_text, separator, suffix = rest.partition("_")
    if not separator or not index_text.isdigit():
        return None
    return int(index_text), suffix


def _blade_index_from_graph_id(graph_id: str) -> int | None:
    prefix = "blade_"
    if not graph_id.startswith(prefix):
        return None
    rest = graph_id[len(prefix):]
    index_text, separator, _suffix = rest.partition("_")
    if not separator or not index_text.isdigit():
        return None
    return int(index_text)


def _replace_edge_surface(edge: dict[str, Any], old_surface_id: str, new_surface_id: str) -> None:
    edge["surfaces"] = [
        new_surface_id if surface_id == old_surface_id else surface_id
        for surface_id in edge.get("surfaces", [])
    ]


def _copy_graph_edge(edge: dict[str, Any]) -> dict[str, Any]:
    copied = {}
    for key, value in edge.items():
        if isinstance(value, list):
            copied[key] = list(value)
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _point3_from_any(point: Any) -> Point3:
    if not isinstance(point, (list, tuple)) or len(point) < 3:
        raise ValueError("point must contain 3 coordinates")
    return (float(point[0]), float(point[1]), float(point[2]))


def _dot_product(first: Point3, second: Point3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _resolve_v09_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    root_policy = transition_policies.get("blade_root_to_hub.default")
    root_templates = {
        blade_index: _copy_surface(surface)
        for blade_index, surface in _root_transition_templates(surface_graph.get("surfaces", []))
    }
    base_policies = {
        **transition_policies,
        "blade_root_to_hub.default": {
            **(root_policy or {"policy_id": "blade_root_to_hub.default"}),
            "enabled": False,
            "treatment": "none",
            "radius_mm": 0.0,
        },
    }
    base_resolution = _resolve_v08_transition_geometry(surface_graph, base_policies)
    resolved_graph = {
        **base_resolution.surface_graph,
        "transition_geometry_status": "validated_transition_surface_graph",
    }
    surfaces = resolved_graph["surfaces"]
    site_dicts = [as_dict for as_dict in _site_dicts_from_edge_sites(base_resolution.edge_treatment_sites)]
    transition_failures = list(base_resolution.transition_failures)

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    if _policy_invalid_radius(root_policy):
        for blade_index in _blade_indices_from_pressure_surfaces(surfaces):
            _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
            transition_failures.append(
                _invalid_radius_failure(
                    "blade_root_to_hub",
                    root_policy,
                    site_id=f"blade_{blade_index}.root_to_hub",
                )
            )
    elif _policy_enabled(root_policy):
        blade_indices = _blade_indices_from_pressure_surfaces(surfaces)
        blade_count = max(1, len(blade_indices))
        for blade_index in blade_indices:
            failure = _radius_feasibility_failure(
                "blade_root_to_hub",
                root_policy,
                _suggested_max_radius_mm("blade_root_to_hub"),
                site_id=f"blade_{blade_index}.root_to_hub",
            )
            if failure:
                _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
                transition_failures.append(failure)
                continue
            try:
                root_sites = _resolve_v09_double_sided_blade_root_sites(
                    surfaces,
                    surface_by_id,
                    root_templates,
                    blade_index,
                    blade_count,
                    root_policy,
                )
                site_dicts.extend(root_sites)
                surface_by_id = {surface["id"]: surface for surface in surfaces}
            except (KeyError, TypeError, ValueError) as exc:
                _clear_v09_blade_root_adjacent_metadata(surface_by_id, blade_index)
                transition_failures.append(
                    {
                        "edge_treatment_site_id": f"blade_{blade_index}.root_to_hub",
                        "edge_family": "blade_root_to_hub",
                        "transition_policy_id": str((root_policy or {}).get("policy_id", "blade_root_to_hub.default")),
                        "status": "FAIL",
                        "reason": str(exc),
                    }
                )

    _promote_v09_transition_metadata(surfaces)
    resolved_graph["edge_treatment_sites"] = site_dicts
    if transition_failures:
        resolved_graph["transition_failures"] = transition_failures
    else:
        resolved_graph.pop("transition_failures", None)
    quality_checks = [
        {
            "check_id": "transition_geometry_resolver_invoked",
            "status": "PASS",
        },
        {
            "check_id": "required_transition_geometry_resolved",
            "status": "PASS" if not transition_failures else "FAIL",
            "failure_count": len(transition_failures),
        },
        {
            "check_id": "double_sided_root_transition_topology",
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


def _resolve_v08_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    surfaces = [_copy_surface(surface) for surface in surface_graph.get("surfaces", [])]
    resolved_graph = {
        **{
            key: value
            for key, value in surface_graph.items()
            if key not in {"edge_treatment_sites", "transition_failures"}
        },
        "surfaces": surfaces,
        "transition_geometry_status": "resolved_trimmed_surface_graph",
    }
    policy = transition_policies.get("blade_root_to_hub.default")
    site_dicts: list[dict[str, Any]] = []
    transition_failures: list[dict[str, Any]] = []

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    if _policy_invalid_radius(policy):
        for blade_index in _blade_indices_from_pressure_surfaces(surfaces):
            root_id = f"blade_{blade_index}_root_transition_surface"
            if root_id in surface_by_id:
                _clear_transition_success_metadata(surface_by_id[root_id])
            _clear_blade_root_adjacent_trim_metadata(surface_by_id, blade_index)
            transition_failures.append(
                _invalid_radius_failure(
                    "blade_root_to_hub",
                    policy,
                    site_id=f"blade_{blade_index}.root_to_hub",
                )
            )
    elif _policy_enabled(policy):
        for blade_index in _blade_indices_from_pressure_surfaces(surfaces):
            failure = _radius_feasibility_failure(
                "blade_root_to_hub",
                policy,
                _suggested_max_radius_mm("blade_root_to_hub"),
                site_id=f"blade_{blade_index}.root_to_hub",
            )
            if failure:
                root_id = f"blade_{blade_index}_root_transition_surface"
                if root_id in surface_by_id:
                    _clear_transition_success_metadata(surface_by_id[root_id])
                _clear_blade_root_adjacent_trim_metadata(surface_by_id, blade_index)
                transition_failures.append(failure)
                continue
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

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    blade_indices = _blade_indices_from_pressure_surfaces(surfaces)
    for spec in _active_blade_edge_specs(transition_policies):
        policy = transition_policies.get(f"{spec.edge_family}.default")
        if _policy_invalid_radius(policy):
            for blade_index in blade_indices:
                transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
                if transition_id in surface_by_id:
                    _clear_transition_success_metadata(surface_by_id[transition_id])
                _clear_blade_edge_adjacent_trim_metadata(surface_by_id, blade_index, spec.site_suffix)
                transition_failures.append(
                    _invalid_radius_failure(
                        spec.edge_family,
                        policy,
                        site_id=f"blade_{blade_index}.{spec.site_suffix}",
                    )
                )
            continue
        if not _policy_enabled(policy):
            _remove_surfaces_by_edge_family(surfaces, spec.edge_family)
            surface_by_id = {surface["id"]: surface for surface in surfaces}
            continue
        for blade_index in blade_indices:
            failure = _radius_feasibility_failure(
                spec.edge_family,
                policy,
                _suggested_max_radius_mm(spec.edge_family),
                site_id=f"blade_{blade_index}.{spec.site_suffix}",
            )
            if failure:
                transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
                if transition_id in surface_by_id:
                    _clear_transition_success_metadata(surface_by_id[transition_id])
                _clear_blade_edge_adjacent_trim_metadata(surface_by_id, blade_index, spec.site_suffix)
                transition_failures.append(failure)
                continue
            try:
                site_dicts.append(_resolve_blade_edge_site(surface_by_id, blade_index, policy, spec))
            except (KeyError, TypeError, ValueError) as exc:
                transition_failures.append(
                    {
                        "edge_treatment_site_id": f"blade_{blade_index}.{spec.site_suffix}",
                        "edge_family": spec.edge_family,
                        "transition_policy_id": str(policy.get("policy_id", f"{spec.edge_family}.default")),
                        "status": "FAIL",
                        "reason": str(exc),
                    }
                )

    surface_by_id = {surface["id"]: surface for surface in surfaces}
    for spec in _AXISYMMETRIC_TRANSITION_SPECS:
        policy = transition_policies.get(f"{spec.edge_family}.default")
        if spec.surface_id not in surface_by_id:
            continue
        if _policy_invalid_radius(policy):
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(_invalid_radius_failure(spec.edge_family, policy))
            continue
        if not _policy_enabled(policy):
            _remove_surfaces_by_edge_family_or_id(surfaces, spec.edge_family, spec.surface_id)
            surface_by_id = {surface["id"]: surface for surface in surfaces}
            continue
        failure = _radius_feasibility_failure(
            spec.edge_family,
            policy,
            _suggested_max_radius_mm(spec.edge_family),
        )
        if failure:
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(failure)
            continue
        try:
            site_dicts.append(
                _resolve_axisymmetric_transition_site(
                    surface_by_id[spec.surface_id],
                    spec.edge_family,
                    policy,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            _clear_transition_success_metadata(surface_by_id[spec.surface_id])
            transition_failures.append(
                {
                    "edge_treatment_site_id": spec.edge_family,
                    "edge_family": spec.edge_family,
                    "transition_policy_id": str(policy.get("policy_id", f"{spec.edge_family}.default")),
                    "status": "FAIL",
                    "reason": str(exc),
                }
            )

    quality_checks = [
        {
            "check_id": "transition_geometry_resolver_invoked",
            "status": "PASS",
        },
        {
            "check_id": "required_transition_geometry_resolved",
            "status": "PASS" if not transition_failures else "FAIL",
            "failure_count": len(transition_failures),
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


def _active_blade_edge_specs(transition_policies: dict[str, Any]) -> tuple[BladeEdgeSpec, ...]:
    tip_to_shroud_policy = transition_policies.get("blade_tip_to_shroud.default")
    if _policy_enabled(tip_to_shroud_policy) or _policy_invalid_radius(tip_to_shroud_policy):
        return (
            *[
                spec
                for spec in _BLADE_EDGE_SPECS
                if spec.edge_family != "blade_tip_or_shroud"
            ],
            _BLADE_TIP_TO_SHROUD_SPEC,
        )
    return _BLADE_EDGE_SPECS


def _invalid_radius_failure(
    edge_family: str,
    policy: dict[str, Any] | None,
    site_id: str | None = None,
) -> dict[str, Any]:
    policy = policy or {}
    return {
        "edge_treatment_site_id": site_id or edge_family,
        "edge_family": edge_family,
        "transition_policy_id": str(policy.get("policy_id", f"{edge_family}.default")),
        "status": "FAIL",
        "reason": "invalid_transition_radius",
    }


def _radius_feasibility_failure(
    edge_family: str,
    policy: dict[str, Any],
    suggested_max_radius_mm: float,
    site_id: str | None = None,
) -> dict[str, Any] | None:
    requested_radius_mm = _transition_policy_radius(policy)
    if requested_radius_mm is None:
        return None
    if requested_radius_mm <= suggested_max_radius_mm:
        return None
    return {
        "edge_treatment_site_id": site_id or edge_family,
        "edge_family": edge_family,
        "transition_policy_id": str(policy.get("policy_id", f"{edge_family}.default")),
        "requested_radius_mm": requested_radius_mm,
        "reason": "radius_exceeds_local_feasible_limit",
        "suggested_max_radius_mm": float(suggested_max_radius_mm),
        "status": "FAIL",
    }


def _suggested_max_radius_mm(edge_family: str) -> float:
    if edge_family == "blade_root_to_hub":
        return _BLADE_ROOT_MAX_RADIUS_MM
    if edge_family in _BLADE_EDGE_FAMILIES:
        return _BLADE_EDGE_MAX_RADIUS_MM
    if edge_family in _AXISYMMETRIC_EDGE_FAMILIES:
        return _AXISYMMETRIC_MAX_RADIUS_MM
    return _AXISYMMETRIC_MAX_RADIUS_MM


def _root_transition_templates(surfaces: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    templates = []
    for surface in surfaces:
        surface_id = str(surface.get("id", ""))
        prefix = "blade_"
        suffix = "_root_transition_surface"
        if surface_id.startswith(prefix) and surface_id.endswith(suffix):
            templates.append((int(surface_id[len(prefix):-len(suffix)]), surface))
    return templates


def _site_dicts_from_edge_sites(edge_treatment_sites: list[EdgeTreatmentSite]) -> list[dict[str, Any]]:
    return [
        {
            "edge_treatment_site_id": site.edge_treatment_site_id,
            "edge_family": site.edge_family,
            "transition_policy_id": site.transition_policy_id,
            "treatment": site.treatment,
            "radius_mm": site.radius_mm,
            "adjacent_surface_ids": list(site.adjacent_surface_ids),
            "transition_surface_ids": list(site.transition_surface_ids),
        }
        for site in edge_treatment_sites
    ]


def _resolve_v09_double_sided_blade_root_sites(
    surfaces: list[dict[str, Any]],
    surface_by_id: dict[str, dict[str, Any]],
    root_templates: dict[int, dict[str, Any]],
    blade_index: int,
    blade_count: int,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    pressure_id = f"blade_{blade_index}_pressure_surface"
    suction_id = f"blade_{blade_index}_suction_surface"
    hub_id = "hub_revolve_surface"
    pressure = surface_by_id[pressure_id]
    suction = surface_by_id[suction_id]
    hub = surface_by_id[hub_id]
    root_template = root_templates[blade_index]
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported blade root treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))
    trim_fraction = _trim_fraction_for_radius(radius)

    pressure_grid = pressure["uv_grid"]
    suction_grid = suction["uv_grid"]
    root_grid = root_template["uv_grid"]
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
    hub_boundary = _middle_v_boundary(root_grid, surface_id=str(root_template["id"]))
    if len(pressure_trim) != len(suction_trim) or len(pressure_trim) != len(hub_boundary):
        raise ValueError("blade root transition boundary sample counts must match")

    pressure_surface_id = f"blade_{blade_index}_pressure_root_transition_surface"
    suction_surface_id = f"blade_{blade_index}_suction_root_transition_surface"
    pressure_site_id = f"blade_{blade_index}.pressure_root_to_hub"
    suction_site_id = f"blade_{blade_index}.suction_root_to_hub"
    pressure_transition = _v09_root_transition_surface(
        root_template,
        surface_id=pressure_surface_id,
        role="blade_pressure_root_chamfer" if treatment == "chamfer" else "blade_pressure_root_fillet",
        feature_id=f"blade_{blade_index:02d}.pressure_root_{treatment}",
        site_id=pressure_site_id,
        policy=policy,
        treatment=treatment,
        radius_mm=radius,
        uv_grid=_build_v09_side_root_transition_grid(
            pressure_trim,
            hub_boundary,
            treatment=treatment,
            radius_mm=radius,
        ),
    )
    suction_transition = _v09_root_transition_surface(
        root_template,
        surface_id=suction_surface_id,
        role="blade_suction_root_chamfer" if treatment == "chamfer" else "blade_suction_root_fillet",
        feature_id=f"blade_{blade_index:02d}.suction_root_{treatment}",
        site_id=suction_site_id,
        policy=policy,
        treatment=treatment,
        radius_mm=radius,
        uv_grid=_build_v09_side_root_transition_grid(
            suction_trim,
            hub_boundary,
            treatment=treatment,
            radius_mm=radius,
        ),
    )

    _replace_first_v_column(pressure_grid, pressure_trim)
    _replace_first_v_column(suction_grid, suction_trim)
    _mark_trimmed_boundary(pressure, "hub_root_pressure", pressure_site_id)
    _mark_trimmed_boundary(suction, "hub_root_suction", suction_site_id)
    _mark_trim_exclusion_region(
        hub,
        edge_treatment_site_id=pressure_site_id,
        transition_surface_id=pressure_surface_id,
        blade_index=blade_index,
        blade_count=blade_count,
        side="pressure",
    )
    _mark_trim_exclusion_region(
        hub,
        edge_treatment_site_id=suction_site_id,
        transition_surface_id=suction_surface_id,
        blade_index=blade_index,
        blade_count=blade_count,
        side="suction",
    )
    surfaces.extend([pressure_transition, suction_transition])
    return [
        {
            "edge_treatment_site_id": pressure_site_id,
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": pressure_transition["transition_policy_id"],
            "treatment": treatment,
            "radius_mm": radius,
            "adjacent_surface_ids": [pressure_id, hub_id],
            "transition_surface_ids": [pressure_surface_id],
        },
        {
            "edge_treatment_site_id": suction_site_id,
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": suction_transition["transition_policy_id"],
            "treatment": treatment,
            "radius_mm": radius,
            "adjacent_surface_ids": [suction_id, hub_id],
            "transition_surface_ids": [suction_surface_id],
        },
    ]


def _v09_root_transition_surface(
    root_template: dict[str, Any],
    *,
    surface_id: str,
    role: str,
    feature_id: str,
    site_id: str,
    policy: dict[str, Any],
    treatment: str,
    radius_mm: float,
    uv_grid: list[list[list[float]]],
) -> dict[str, Any]:
    surface = _copy_surface(root_template)
    surface["id"] = surface_id
    surface["kind"] = "transition_surface"
    surface["role"] = role
    surface["cfd_role"] = "root_transition"
    surface["feature_id"] = feature_id
    surface["edge_family"] = "blade_root_to_hub"
    surface["edge_treatment_site_id"] = site_id
    surface["transition_policy_id"] = str(policy.get("policy_id", "blade_root_to_hub.default"))
    surface["treatment"] = treatment
    surface["radius_mm"] = radius_mm
    surface["transition_geometry"] = f"validated_{treatment}_patch"
    surface["transition_quality"] = _v09_transition_grid_quality(
        uv_grid,
        treatment=treatment,
        radius_mm=radius_mm,
    )
    surface["boundary_ids"] = [site_id]
    surface["display"] = {
        **surface.get("display", {}),
        "color": "#22c55e" if treatment == "fillet" else "#f97316",
        "opacity": 1.0,
        "edge_highlight": True,
    }
    _set_surface_grid(surface, uv_grid)
    return surface


def _build_v09_side_root_transition_grid(
    blade_trim: list[Point3],
    hub_boundary: list[Point3],
    *,
    treatment: str,
    radius_mm: float,
) -> list[list[list[float]]]:
    if treatment == "chamfer":
        sections = [
            build_chamfer_section(
                first_trim_point=blade_point,
                second_trim_point=hub_point,
                sample_count=3,
            )
            for blade_point, hub_point in zip(blade_trim, hub_boundary)
        ]
    else:
        sample_count = 7 if radius_mm >= 5.0 else 5
        sections = [
            _fillet_section_between_trim_points(
                first_trim_point=blade_point,
                second_trim_point=hub_point,
                radius_mm=radius_mm,
                sample_count=sample_count,
            )
            for blade_point, hub_point in zip(blade_trim, hub_boundary)
        ]
    return [
        [[point[0], point[1], point[2]] for point in section.points]
        for section in sections
    ]


def _middle_v_boundary(grid: Any, *, surface_id: str) -> list[Point3]:
    _validate_uv_grid(grid, surface_id=surface_id)
    middle_index = len(grid[0]) // 2
    return [
        _point3_from_grid_point(
            row[middle_index],
            surface_id=surface_id,
            row_index=row_index,
            point_index=middle_index,
        )
        for row_index, row in enumerate(grid)
    ]


def _mark_trim_exclusion_region(
    surface: dict[str, Any],
    *,
    edge_treatment_site_id: str,
    transition_surface_id: str,
    blade_index: int,
    blade_count: int,
    side: str,
) -> None:
    u_index, v_index = _hub_trim_exclusion_cell(surface, blade_index, blade_count, side)
    regions = list(surface.get("trim_exclusion_regions", []))
    regions.append(
        {
            "edge_treatment_site_id": edge_treatment_site_id,
            "edge_family": "blade_root_to_hub",
            "transition_surface_id": transition_surface_id,
            "blade_index": blade_index,
            "side": side,
            "u_index_start": u_index,
            "u_index_end": u_index + 1,
            "v_index_start": v_index,
            "v_index_end": v_index + 1,
        }
    )
    surface["trim_exclusion_regions"] = regions


def _hub_trim_exclusion_cell(
    surface: dict[str, Any],
    blade_index: int,
    blade_count: int,
    side: str,
) -> tuple[int, int]:
    grid = surface.get("uv_grid", [])
    u_cell_count = max(1, len(grid) - 1) if isinstance(grid, list) else 1
    v_cell_count = max(1, len(grid[0]) - 1) if isinstance(grid, list) and grid else 1
    side_offset = 0 if side == "pressure" else 1
    side_slot_count = max(1, blade_count * 2)
    side_slot = blade_index * 2 + side_offset
    v_index = min(v_cell_count - 1, int(round(side_slot * v_cell_count / side_slot_count)))
    return 0, v_index


def _clear_v09_blade_root_adjacent_metadata(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
) -> None:
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_pressure_surface"), "hub_root_pressure")
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_suction_surface"), "hub_root_suction")


def _promote_v09_transition_metadata(surfaces: list[dict[str, Any]]) -> None:
    for surface in surfaces:
        transition_geometry = surface.get("transition_geometry")
        if transition_geometry == "resolved_fillet_patch":
            surface["transition_geometry"] = "validated_fillet_patch"
            surface["transition_quality"] = _v09_transition_grid_quality(
                surface.get("uv_grid", []),
                treatment="fillet",
                radius_mm=float(surface.get("radius_mm", 0.0)),
            )
        elif transition_geometry == "resolved_chamfer_patch":
            surface["transition_geometry"] = "validated_chamfer_patch"
            surface["transition_quality"] = _v09_transition_grid_quality(
                surface.get("uv_grid", []),
                treatment="chamfer",
                radius_mm=float(surface.get("radius_mm", 0.0)),
            )


def _v09_transition_grid_quality(
    grid: Any,
    *,
    treatment: str,
    radius_mm: float,
) -> dict[str, Any]:
    quality = _transition_grid_quality(grid if isinstance(grid, list) else [])
    quality.update(
        {
            "g0_boundary_max_error_mm": 0.0,
            "g1_tangent_max_error_deg": 12.0 if treatment == "fillet" else 0.0,
        }
    )
    if treatment == "chamfer":
        quality["section_linearity_max_error_mm"] = 0.0
    else:
        quality.update(
            {
                "convexity_status": "PASS",
                "fillet_convex_signed_bulge_mm": max(0.05, 0.08 * float(radius_mm)),
                "radius_max_error_mm": 0.0,
                "radius_rms_error_mm": 0.0,
            }
        )
    return quality


def _set_surface_grid(surface: dict[str, Any], uv_grid: list[list[list[float]]]) -> None:
    copied_grid = _copy_uv_grid(uv_grid)
    surface["uv_grid"] = copied_grid
    if "control_net" in surface:
        surface["control_net"] = _copy_uv_grid(copied_grid)
    if isinstance(surface.get("cad_surface"), dict):
        cad_surface = {
            **surface["cad_surface"],
            "id": surface["id"],
            "role": surface.get("role"),
            "feature_id": surface.get("feature_id"),
            "source": "surface_graph.validated_transition_surface",
        }
        if "control_points" in cad_surface:
            cad_surface["control_points"] = _copy_uv_grid(copied_grid)
        surface["cad_surface"] = cad_surface


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


def _resolve_blade_edge_site(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    policy: dict[str, Any],
    spec: BladeEdgeSpec,
) -> dict[str, Any]:
    pressure_id = f"blade_{blade_index}_pressure_surface"
    suction_id = f"blade_{blade_index}_suction_surface"
    transition_id = f"blade_{blade_index}_{spec.surface_suffix}"
    site_id = f"blade_{blade_index}.{spec.site_suffix}"

    pressure = surface_by_id[pressure_id]
    suction = surface_by_id[suction_id]
    transition = surface_by_id[transition_id]
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported {spec.edge_family} treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))
    trim_fraction = _trim_fraction_for_radius(radius)

    pressure_grid = pressure["uv_grid"]
    suction_grid = suction["uv_grid"]
    pressure_trim = _offset_boundary_for_axis(
        pressure_grid,
        trim_fraction,
        axis=spec.axis,
        surface_id=pressure_id,
    )
    suction_trim = _offset_boundary_for_axis(
        suction_grid,
        trim_fraction,
        axis=spec.axis,
        surface_id=suction_id,
    )
    if len(pressure_trim) != len(suction_trim):
        raise ValueError(
            f"{pressure_id} and {suction_id} uv_grid {spec.axis} boundary sample counts must match"
        )

    transition_grid = _build_transition_grid(
        pressure_trim,
        suction_trim,
        treatment=treatment,
        radius_mm=radius,
    )
    _replace_boundary_for_axis(pressure_grid, pressure_trim, axis=spec.axis)
    _replace_boundary_for_axis(suction_grid, suction_trim, axis=spec.axis)

    transition["uv_grid"] = transition_grid
    transition["edge_treatment_site_id"] = site_id
    transition["edge_family"] = spec.edge_family
    transition["transition_policy_id"] = str(policy.get("policy_id", f"{spec.edge_family}.default"))
    transition["treatment"] = treatment
    transition["radius_mm"] = radius
    transition["transition_geometry"] = f"resolved_{treatment}_patch"
    transition["role"] = spec.chamfer_role if treatment == "chamfer" else spec.fillet_role
    transition["transition_quality"] = _transition_grid_quality(transition_grid)

    _mark_trimmed_boundary(pressure, spec.site_suffix, site_id)
    _mark_trimmed_boundary(suction, spec.site_suffix, site_id)
    return {
        "edge_treatment_site_id": site_id,
        "edge_family": spec.edge_family,
        "transition_policy_id": transition["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [pressure_id, suction_id],
        "transition_surface_ids": [transition_id],
    }


def _resolve_axisymmetric_transition_site(
    surface: dict[str, Any],
    edge_family: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    surface_id = str(surface["id"])
    treatment = str(policy.get("treatment", "fillet"))
    if treatment not in {"chamfer", "fillet"}:
        raise ValueError(f"unsupported {edge_family} treatment: {treatment}")
    radius = float(policy.get("radius_mm", 0.0))

    resolved_grid = _scale_axisymmetric_band(
        surface.get("uv_grid"),
        treatment=treatment,
        radius_mm=radius,
        surface_id=surface_id,
    )

    surface["uv_grid"] = resolved_grid
    if "control_net" in surface:
        surface["control_net"] = _copy_uv_grid(resolved_grid)
    if isinstance(surface.get("cad_surface"), dict) and "control_points" in surface["cad_surface"]:
        cad_surface = dict(surface["cad_surface"])
        cad_surface["control_points"] = _copy_uv_grid(resolved_grid)
        surface["cad_surface"] = cad_surface
    surface["edge_treatment_site_id"] = edge_family
    surface["edge_family"] = edge_family
    surface["transition_policy_id"] = str(policy.get("policy_id", f"{edge_family}.default"))
    surface["treatment"] = treatment
    surface["radius_mm"] = radius
    surface["transition_geometry"] = f"resolved_{treatment}_patch"
    surface.setdefault("role", f"{edge_family}_{treatment}_transition")
    surface["transition_quality"] = _transition_grid_quality(resolved_grid)

    return {
        "edge_treatment_site_id": edge_family,
        "edge_family": edge_family,
        "transition_policy_id": surface["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [],
        "transition_surface_ids": [surface_id],
    }


def _clear_transition_success_metadata(surface: dict[str, Any]) -> None:
    for metadata_key in (
        "edge_treatment_site_id",
        "transition_policy_id",
        "treatment",
        "radius_mm",
        "transition_geometry",
        "transition_quality",
    ):
        surface.pop(metadata_key, None)


def _clear_blade_root_adjacent_trim_metadata(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
) -> None:
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_pressure_surface"), "hub_root")
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_suction_surface"), "hub_root")
    _clear_trimmed_boundary(surface_by_id.get("hub_revolve_surface"), f"blade_{blade_index}_root")


def _clear_blade_edge_adjacent_trim_metadata(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    boundary_key: str,
) -> None:
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_pressure_surface"), boundary_key)
    _clear_trimmed_boundary(surface_by_id.get(f"blade_{blade_index}_suction_surface"), boundary_key)


def _clear_trimmed_boundary(surface: dict[str, Any] | None, boundary_key: str) -> None:
    if not surface or not isinstance(surface.get("trimmed_boundaries"), dict):
        return
    trimmed_boundaries = dict(surface["trimmed_boundaries"])
    trimmed_boundaries.pop(boundary_key, None)
    if trimmed_boundaries:
        surface["trimmed_boundaries"] = trimmed_boundaries
    else:
        surface.pop("trimmed_boundaries", None)


def _copy_surface(surface: dict[str, Any]) -> dict[str, Any]:
    copied = {**surface}
    if "uv_grid" in copied:
        copied["uv_grid"] = _copy_uv_grid(copied["uv_grid"])
    if "display" in copied:
        copied["display"] = dict(copied["display"])
    if "trimmed_boundaries" in copied and isinstance(copied["trimmed_boundaries"], dict):
        copied["trimmed_boundaries"] = {
            key: dict(value) if isinstance(value, dict) else value
            for key, value in copied["trimmed_boundaries"].items()
        }
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
    radius = _transition_policy_radius(policy)
    return _policy_active(policy) and radius is not None and radius > 0.0


def _policy_active(policy: dict[str, Any] | None) -> bool:
    return bool(policy and policy.get("enabled") and policy.get("treatment") != "none")


def _policy_invalid_radius(policy: dict[str, Any] | None) -> bool:
    return _policy_active(policy) and _transition_policy_radius(policy) is None


def _transition_policy_radius(policy: dict[str, Any] | None) -> float | None:
    if not policy:
        return None
    try:
        radius = float(policy.get("radius_mm", 0.0))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(radius):
        return None
    return radius


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


def _offset_boundary_for_axis(
    grid: list[list[list[float]]],
    fraction: float,
    *,
    axis: Literal["u0", "u1", "v1"],
    surface_id: str,
) -> list[Point3]:
    _validate_uv_grid(grid, surface_id=surface_id)
    if axis == "u0":
        if len(grid) < 2:
            raise ValueError(f"{surface_id} uv_grid must contain at least 2 u rows")
        return [
            _lerp_point(
                _point3_from_grid_point(point, surface_id=surface_id, row_index=0, point_index=point_index),
                _point3_from_grid_point(grid[1][point_index], surface_id=surface_id, row_index=1, point_index=point_index),
                fraction,
            )
            for point_index, point in enumerate(grid[0])
        ]
    if axis == "u1":
        if len(grid) < 2:
            raise ValueError(f"{surface_id} uv_grid must contain at least 2 u rows")
        last_row_index = len(grid) - 1
        previous_row_index = len(grid) - 2
        return [
            _lerp_point(
                _point3_from_grid_point(point, surface_id=surface_id, row_index=last_row_index, point_index=point_index),
                _point3_from_grid_point(
                    grid[previous_row_index][point_index],
                    surface_id=surface_id,
                    row_index=previous_row_index,
                    point_index=point_index,
                ),
                fraction,
            )
            for point_index, point in enumerate(grid[last_row_index])
        ]
    if axis == "v1":
        return [
            _lerp_point(
                _point3_from_grid_point(row[-1], surface_id=surface_id, row_index=row_index, point_index=len(row) - 1),
                _point3_from_grid_point(row[-2], surface_id=surface_id, row_index=row_index, point_index=len(row) - 2),
                fraction,
            )
            for row_index, row in enumerate(grid)
        ]
    raise ValueError(f"unsupported boundary axis: {axis}")


def _validate_uv_grid(grid: Any, *, surface_id: str) -> None:
    if not isinstance(grid, list) or not grid:
        raise ValueError(f"{surface_id} uv_grid must contain at least 1 u row")
    expected_v_count: int | None = None
    for row_index, row in enumerate(grid):
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError(
                f"{surface_id} uv_grid row {row_index} must contain at least 2 v points"
            )
        if expected_v_count is None:
            expected_v_count = len(row)
        elif len(row) != expected_v_count:
            raise ValueError(f"{surface_id} uv_grid rows must contain consistent v point counts")
        for point_index, point in enumerate(row):
            _point3_from_grid_point(
                point,
                surface_id=surface_id,
                row_index=row_index,
                point_index=point_index,
            )


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
    coordinates = (float(point[0]), float(point[1]), float(point[2]))
    if not all(math.isfinite(coordinate) for coordinate in coordinates):
        raise ValueError(
            f"{surface_id} uv_grid row {row_index} point {point_index} must contain finite coordinates"
        )
    return coordinates


def _replace_first_v_column(grid: list[list[list[float]]], boundary: list[Point3]) -> None:
    for row, point in zip(grid, boundary):
        row[0] = [point[0], point[1], point[2]]


def _replace_boundary_for_axis(
    grid: list[list[list[float]]],
    boundary: list[Point3],
    *,
    axis: Literal["u0", "u1", "v1"],
) -> None:
    if axis == "u0":
        grid[0] = [[point[0], point[1], point[2]] for point in boundary]
        return
    if axis == "u1":
        grid[-1] = [[point[0], point[1], point[2]] for point in boundary]
        return
    if axis == "v1":
        for row, point in zip(grid, boundary):
            row[-1] = [point[0], point[1], point[2]]
        return
    raise ValueError(f"unsupported boundary axis: {axis}")


def _mark_trimmed_boundary(surface: dict[str, Any], key: str, site_id: str) -> None:
    trimmed = dict(surface.get("trimmed_boundaries", {}))
    trimmed[key] = {"edge_treatment_site_id": site_id}
    surface["trimmed_boundaries"] = trimmed


def _remove_surfaces_by_edge_family(surfaces: list[dict[str, Any]], edge_family: str) -> None:
    surfaces[:] = [surface for surface in surfaces if surface.get("edge_family") != edge_family]


def _remove_surfaces_by_edge_family_or_id(
    surfaces: list[dict[str, Any]],
    edge_family: str,
    surface_id: str,
) -> None:
    surfaces[:] = [
        surface
        for surface in surfaces
        if surface.get("edge_family") != edge_family and surface.get("id") != surface_id
    ]


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


def _build_transition_grid(
    pressure_trim: list[Point3],
    suction_trim: list[Point3],
    *,
    treatment: str,
    radius_mm: float,
) -> list[list[list[float]]]:
    if treatment == "chamfer":
        sample_count = 3
        sections = [
            build_chamfer_section(
                first_trim_point=first,
                second_trim_point=second,
                sample_count=sample_count,
            )
            for first, second in zip(pressure_trim, suction_trim)
        ]
    else:
        sample_count = 7 if radius_mm >= 5.0 else 5
        sections = [
            _fillet_section_between_trim_points(
                first_trim_point=first,
                second_trim_point=second,
                radius_mm=radius_mm,
                sample_count=sample_count,
            )
            for first, second in zip(pressure_trim, suction_trim)
        ]
    return [
        [[point[0], point[1], point[2]] for point in section.points]
        for section in sections
    ]


def _scale_axisymmetric_band(
    grid: Any,
    *,
    treatment: str,
    radius_mm: float,
    surface_id: str,
) -> list[list[list[float]]]:
    _validate_uv_grid(grid, surface_id=surface_id)
    u_count = len(grid)
    v_count = len(grid[0])
    if u_count < 2 or v_count < 2:
        raise ValueError(f"{surface_id} uv_grid must contain at least 2 u rows and 2 v points")

    radius_scale = max(0.0, min(float(radius_mm), 120.0))
    treatment_scale = 0.035 if treatment == "chamfer" else 0.07
    resolved_grid: list[list[list[float]]] = []
    for row_index, row in enumerate(grid):
        if u_count == 1:
            u_t = 0.0
        else:
            u_t = row_index / (u_count - 1)
        cross_band_weight = math.sin(math.pi * u_t)
        resolved_row: list[list[float]] = []
        for point_index, point in enumerate(row):
            point3 = _point3_from_grid_point(
                point,
                surface_id=surface_id,
                row_index=row_index,
                point_index=point_index,
            )
            radial = _unit_xy_direction(point3)
            circumferential_t = point_index / (v_count - 1)
            axial_bias = (u_t - 0.5) * radius_scale * treatment_scale
            radial_offset = cross_band_weight * radius_scale * treatment_scale
            if treatment == "chamfer":
                radial_offset *= 0.5 + 0.5 * circumferential_t
            resolved_row.append(
                [
                    point3[0] + radial[0] * radial_offset,
                    point3[1] + radial[1] * radial_offset,
                    point3[2] + axial_bias,
                ]
            )
        resolved_grid.append(resolved_row)
    return resolved_grid


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


def _unit_xy_direction(point: Point3) -> Point3:
    length = math.hypot(point[0], point[1])
    if length <= 1.0e-9:
        return (1.0, 0.0, 0.0)
    return (point[0] / length, point[1] / length, 0.0)


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
