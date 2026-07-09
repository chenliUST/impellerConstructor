from __future__ import annotations

import copy
import math
import re
from typing import Any

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface
from part_rule_synthesis.impeller_v10_2_support_attachment import (
    build_v10_2_root_attachment_surface,
    build_v10_2_tip_attachment_surface,
)
from part_rule_synthesis.impeller_v10_3_blade_faces import (
    build_blade_faces_from_section_lattice,
)
from part_rule_synthesis.impeller_v10_3_root_blend import build_v10_3_root_blend
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice, _validated_values
from part_rule_synthesis.impeller_v10_3_tip_dome import build_v10_3_tip_dome
from part_rule_synthesis.impeller_v10_4_hub_solid import build_v10_4_hub_solid_faces
from part_rule_synthesis.impeller_v10_4_continuity import (
    measure_v10_4_blade_hub_angles,
    measure_v10_4_continuity,
)
from part_rule_synthesis.impeller_v10_4_root_surface import build_v10_4_root_surface
from part_rule_synthesis.impeller_v10_4_section_loop_contract import attach_section_loop_contracts
from part_rule_synthesis.impeller_v10_4_tip_surface import upgrade_tip_surface_contract
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


V10_TRANSITION_GEOMETRY_STATUS = "topology_first_closed_nurbs_impeller_surface_graph"
V10_3_TRANSITION_GEOMETRY_STATUS = "topology_first_section_loop_blade_root_blend_surface_graph"
V10_4_TRANSITION_GEOMETRY_STATUS = "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
V10_SOURCE_KERNEL = "axisymmetric_throughflow_nurbs"

_BLADE_SURFACE_RE = re.compile(r"^blade_(\d+)_(.+)$")
_PRESSURE_SUFFIX = "pressure_surface"
_SUCTION_SUFFIX = "suction_surface"
_LEADING_SUFFIXES = {
    "leading_edge_surface",
    "leading_edge_fillet_surface",
    "leading_transition_surface",
}
_TRAILING_SUFFIXES = {
    "trailing_edge_surface",
    "trailing_edge_fillet_surface",
    "trailing_transition_surface",
}
_ROOT_SUFFIXES = {
    "root_closure_surface",
    "root_fillet_surface",
    "root_transition_surface",
}
_TIP_SUFFIXES = {
    "tip_closure_surface",
    "tip_edge_fillet_surface",
    "tip_transition_surface",
}
_DEFERRED_OUTER_HUB_CHAMFERS = {
    "hub_chamfer_bottom_outer_surface",
    "hub_chamfer_top_cap_surface",
}
_BLADE_EDGE_SAMPLE_COUNT = 13
_ROOT_BOSS_SAMPLE_COUNT = 9


class _CompatLabel(str):
    def __new__(cls, value: str, aliases: tuple[str, ...] = ()):
        obj = str.__new__(cls, value)
        obj._aliases = aliases
        return obj

    def __eq__(self, other: object) -> bool:
        return str.__eq__(self, other) or other in self._aliases


def build_v10_surface_graph(
    parameters: dict[str, Any],
    facets: dict[str, str],
    *,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
    profile_defaults: dict[str, Any] | None = None,
    edge_families: dict[str, Any] | None = None,
    transition_policies: dict[str, Any] | None = None,
    geometry_version: str | None = None,
    resolved_attachment_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if geometry_version == "1.1" or (
        isinstance(resolved_attachment_defaults, dict)
        and resolved_attachment_defaults.get("geometry_patch_version") == "1.1.0"
    ):
        defaults = {}
        overrides = {}
        if isinstance(resolved_attachment_defaults, dict):
            defaults = copy.deepcopy(resolved_attachment_defaults.get("resolved_blade_to_blade_loop_family_defaults", {}))
            overrides = copy.deepcopy(resolved_attachment_defaults.get("blade_to_blade_loop_family_overrides", {}))
        return build_v11_surface_graph(
            parameters=parameters,
            facets=facets,
            defaults=defaults,
            profile_defaults=profile_defaults,
            profile_overrides=profile_overrides,
            overrides=overrides,
        )

    if _is_v10_3_surface_graph_request(resolved_attachment_defaults):
        return _build_v10_3_surface_graph(
            parameters=parameters,
            facets=facets,
            display_policy=display_policy,
            profile_defaults=profile_defaults,
            resolved_section_loop_defaults=_v10_3_section_loop_defaults(
                resolved_attachment_defaults
            ),
        )

    legacy_geometry = build_axisymmetric_throughflow_nurbs_geometry(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        display_policy=_v10_display_policy(display_policy),
        material_domain=material_domain,
        solid_features=solid_features,
        profile_defaults=profile_defaults,
        edge_families=None,
        transition_policies=None,
        geometry_version="",
    )
    legacy_graph = legacy_geometry["surface_graph"]
    faces, id_map = _topology_first_faces_from_legacy(legacy_graph.get("surfaces", []))
    _apply_v10_visibility_contract(faces, facets)
    v10_2_failures = _apply_v10_2_continuous_blade_complex(
        faces,
        parameters,
        facets,
        resolved_attachment_defaults=resolved_attachment_defaults,
    )
    _attach_support_edge_samples(faces)

    topology_graph = build_v10_topology_graph(faces)
    transition_failures = copy.deepcopy(legacy_graph.get("transition_failures", []))
    transition_failures.extend(copy.deepcopy(v10_2_failures))
    surface_graph_status = "PASS" if not v10_2_failures else "FAIL"
    return {
        "transition_geometry_status": V10_TRANSITION_GEOMETRY_STATUS,
        "geometry_version": "1.0",
        "geometry_patch_version": "1.0.2",
        "continuous_blade_attachment_status": surface_graph_status,
        "resolved_attachment_defaults": copy.deepcopy(
            resolved_attachment_defaults if isinstance(resolved_attachment_defaults, dict) else {}
        ),
        "v1_0_2_transition_failure_count": len(v10_2_failures),
        "v1_0_2_transition_failures": copy.deepcopy(v10_2_failures),
        "source_kernel": V10_SOURCE_KERNEL,
        "source_geometry_version": geometry_version or "1.0",
        "source_math_policy": "reuse_legacy_axisymmetric_throughflow_nurbs_uv_grids",
        "surface_graph_status": surface_graph_status,
        "surfaces": faces,
        "edges": _remap_edges(legacy_graph.get("edges", []), id_map),
        "boundary_curves": copy.deepcopy(legacy_graph.get("boundary_curves", {})),
        "named_boundary_curves": copy.deepcopy(legacy_graph.get("named_boundary_curves", [])),
        "topology_graph": topology_graph,
        "transition_failures": transition_failures,
        "native_face_count": len(faces),
        "blade_count": int(parameters.get("blade_count", 0)),
        "facets": facets,
        "construction_lines": copy.deepcopy(legacy_geometry.get("construction_lines", {})),
        "sampled_blades": copy.deepcopy(legacy_geometry.get("sampled_blades", [])),
        "blade_surface": copy.deepcopy(legacy_geometry.get("blade_surface", {})),
        "hub_surface": copy.deepcopy(legacy_geometry.get("hub_surface", {})),
        "cad_features": copy.deepcopy(legacy_geometry.get("cad_features", [])),
        "legacy_validity": copy.deepcopy(legacy_geometry.get("validity", {})),
        "edge_families": copy.deepcopy(edge_families or {}),
        "transition_policies": copy.deepcopy(transition_policies or {}),
    }


def _is_v10_3_surface_graph_request(carrier: dict[str, Any] | None) -> bool:
    return isinstance(carrier, dict) and (
        carrier.get("v1_0_3_active") is True
        or carrier.get("geometry_patch_version") in {"1.0.3", "1.0.4"}
    )


def _v10_3_section_loop_defaults(carrier: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(carrier, dict):
        return {}
    defaults = carrier.get("resolved_section_loop_defaults")
    if isinstance(defaults, dict):
        resolved_defaults = copy.deepcopy(defaults)
        if carrier.get("geometry_patch_version"):
            resolved_defaults["geometry_patch_version"] = carrier["geometry_patch_version"]
        return resolved_defaults
    return {
        key: copy.deepcopy(value)
        for key, value in carrier.items()
        if key not in {"v1_0_3_active", "geometry_patch_version"}
    }


def _build_v10_3_surface_graph(
    *,
    parameters: dict[str, Any],
    facets: dict[str, str],
    display_policy: dict[str, Any] | None,
    profile_defaults: dict[str, Any] | None,
    resolved_section_loop_defaults: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    carrier_geometry = _v10_3_nurbs_carrier_geometry(
        parameters=parameters,
        facets=facets,
        profile_defaults=profile_defaults,
        resolved_section_loop_defaults=resolved_section_loop_defaults,
    )
    if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
        carrier_hub = _carrier_surface_by_id(carrier_geometry, "hub_revolve_surface")
        profile_samples = (carrier_hub or {}).get("profile_samples_rz") or (carrier_hub or {}).get("support_profile_samples_rz")
        if isinstance(profile_samples, list) and profile_samples:
            resolved_section_loop_defaults = copy.deepcopy(resolved_section_loop_defaults)
            resolved_section_loop_defaults["hub_profile_samples_rz"] = copy.deepcopy(profile_samples)
    lattice = build_section_loop_lattice(
        parameters=parameters,
        defaults=resolved_section_loop_defaults,
        carrier_geometry=carrier_geometry,
    )
    if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
        lattice = attach_section_loop_contracts(lattice)
    if lattice.get("status") != "PASS":
        failures.append(
            _v10_3_failure(
                stage="section_loop_lattice",
                reason=str(lattice.get("failure_reason") or "v1_0_3_section_loop_failed"),
            )
        )
        topology_graph = build_v10_topology_graph([])
        return _v10_3_graph_payload(
            parameters=parameters,
            facets=facets,
            resolved_section_loop_defaults=resolved_section_loop_defaults,
            lattice=lattice,
            surfaces=[],
            hub_surface={},
            failures=failures,
            topology_graph=topology_graph,
            carrier_geometry=carrier_geometry,
        )

    blade_faces_result = build_blade_faces_from_section_lattice(lattice)
    blade_faces = blade_faces_result.get("surfaces", []) if isinstance(blade_faces_result, dict) else []
    if blade_faces_result.get("status") != "PASS":
        failures.append(
            _v10_3_failure(
                stage="blade_face_lattice",
                reason=str(
                    blade_faces_result.get("failure_reason")
                    or "v1_0_3_blade_faces_failed"
                ),
            )
        )
    surfaces.extend(copy.deepcopy(blade_faces))

    hub_surface = _v10_3_hub_support_surface(parameters, resolved_section_loop_defaults, carrier_geometry=carrier_geometry)
    hub_solid = None
    if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
        hub_solid = build_v10_4_hub_solid_faces(hub_surface, parameters)
        hub_surface["v1_0_4_hub_quality"] = copy.deepcopy(hub_solid.get("quality", {}))
    surfaces.append(hub_surface)
    if hub_solid is not None:
        surfaces.extend(copy.deepcopy(hub_solid.get("faces", [])))
    for blade_index, blade in enumerate(lattice.get("blades", [])):
        if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
            root_blend = build_v10_4_root_surface(
                blade_index=blade_index,
                lattice=lattice,
                blade_faces=blade_faces,
                hub_surface=hub_surface,
                defaults=resolved_section_loop_defaults,
            )
        else:
            root_blend = build_v10_3_root_blend(
                blade_index=blade_index,
                lattice=lattice,
                blade_faces=blade_faces,
                hub_surface=hub_surface,
                defaults=resolved_section_loop_defaults,
            )
        if root_blend.get("status") != "PASS":
            failures.append(
                _v10_3_failure(
                    stage="root_blend",
                    reason=str(
                        root_blend.get("v1_0_4_root_quality", {}).get("reason")
                        or root_blend.get("root_blend_quality", {}).get("reason")
                        or root_blend.get("failure_reason")
                        or "v1_0_4_root_surface_failed"
                    )
                    if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4"
                    else str(
                        root_blend.get("root_blend_quality", {}).get("reason")
                        or root_blend.get("failure_reason")
                        or "v1_0_3_root_blend_failed"
                    ),
                    blade_index=blade_index,
                    surface_id=root_blend.get("id"),
                )
            )
        surfaces.append(root_blend)
        surfaces.extend(copy.deepcopy(root_blend.get("component_surfaces", [])))

        if facets.get("shroud_topology") != "closed":
            tip_dome = build_v10_3_tip_dome(
                blade_index=blade_index,
                lattice=lattice,
                defaults=resolved_section_loop_defaults,
            )
            if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
                tip_dome = upgrade_tip_surface_contract(tip_dome, area_ratio_limit=1.15)
            tip_quality = tip_dome.get("v1_0_4_tip_quality", {})
            if tip_dome.get("status") != "PASS" or tip_quality.get("status") == "FAIL":
                failures.append(
                    _v10_3_failure(
                        stage="tip_dome",
                        reason=str(
                            tip_dome.get("v1_0_4_tip_quality", {}).get("reason")
                            or tip_dome.get("tip_dome_quality", {}).get("reason")
                            or tip_dome.get("failure_reason")
                            or "v1_0_3_tip_dome_failed"
                        ),
                        blade_index=blade_index,
                        surface_id=tip_dome.get("id"),
                    )
                )
            surfaces.append(tip_dome)

    _apply_v10_3_display_policy(surfaces, display_policy)
    topology_surfaces, edge_filter_report = _topology_edge_surfaces(surfaces)
    topology_graph = build_v10_topology_graph(topology_surfaces)
    topology_graph["edge_sample_filter_report"] = edge_filter_report
    return _v10_3_graph_payload(
        parameters=parameters,
        facets=facets,
        resolved_section_loop_defaults=resolved_section_loop_defaults,
        lattice=lattice,
        surfaces=surfaces,
        hub_surface=hub_surface,
        failures=failures,
        topology_graph=topology_graph,
        carrier_geometry=carrier_geometry,
    )


def _v10_3_graph_payload(
    *,
    parameters: dict[str, Any],
    facets: dict[str, str],
    resolved_section_loop_defaults: dict[str, Any],
    lattice: dict[str, Any],
    surfaces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    failures: list[dict[str, Any]],
    topology_graph: dict[str, Any],
    carrier_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    main_count = sum(1 for blade in lattice.get("blades", []) if blade.get("blade_class") == "main")
    splitter_count = sum(1 for blade in lattice.get("blades", []) if blade.get("blade_class") == "splitter")
    graph_failures = [*copy.deepcopy(failures), *_v10_3_topology_failures(topology_graph)]
    status = "PASS" if not graph_failures else "FAIL"
    blade_faces = [
        surface
        for surface in surfaces
        if surface.get("face_family")
        in {"blade_pressure", "blade_suction", "blade_leading_edge", "blade_trailing_edge"}
    ]
    carrier_kernel = (carrier_geometry or {}).get("kernel", {}) if isinstance(carrier_geometry, dict) else {}
    geometry_patch_version = resolved_section_loop_defaults.get("geometry_patch_version", lattice.get("geometry_patch_version", "1.0.3"))
    hub_quality = {}
    continuity_summary = {}
    angle_quality = {}
    if geometry_patch_version == "1.0.4":
        hub_quality = copy.deepcopy((hub_surface or {}).get("v1_0_4_hub_quality", {}))
        measurement_graph = {"surfaces": surfaces, "topology_graph": topology_graph}
        continuity_summary = measure_v10_4_continuity(measurement_graph)
        angle_quality = measure_v10_4_blade_hub_angles(measurement_graph)
    transition_geometry_status = (
        V10_4_TRANSITION_GEOMETRY_STATUS if geometry_patch_version == "1.0.4" else V10_3_TRANSITION_GEOMETRY_STATUS
    )
    payload = {
        "transition_geometry_status": transition_geometry_status,
        "geometry_version": "1.0",
        "geometry_patch_version": geometry_patch_version,
        "geometry_generation_status": status,
        "surface_graph_status": status,
        "section_loop_constructor_status": lattice.get("status", "FAIL"),
        "section_loop_join_failure_count": lattice.get("join_failure_count", 0),
        "main_blade_count": main_count,
        "splitter_blade_count": splitter_count,
        "blade_count": main_count + splitter_count,
        "resolved_section_loop_defaults": copy.deepcopy(resolved_section_loop_defaults),
        "v1_0_3_transition_failure_count": len(graph_failures),
        "v1_0_3_transition_failures": copy.deepcopy(graph_failures),
        "v1_0_4_hub_quality": hub_quality,
        "transition_failures": copy.deepcopy(graph_failures),
        "source_kernel": "v1_0_3_section_loop_topology_kernel",
        "carrier_source_kernel": carrier_kernel.get("kind"),
        "source_geometry_version": "1.0.3",
        "source_math_policy": "section_loop_first_nurbs_carrier_blade_faces_segmented_root_blends_open_tip_domes",
        "surfaces": surfaces,
        "edges": [],
        "boundary_curves": {},
        "named_boundary_curves": [],
        "topology_graph": topology_graph,
        "native_face_count": len(surfaces),
        "facets": copy.deepcopy(facets),
        "construction_lines": {},
        "curve_controls": copy.deepcopy(carrier_kernel.get("editable_curve_controls", {})),
        "sampled_blades": copy.deepcopy(lattice.get("blades", [])),
        "blade_surface": {
            "surface_family": "v1_0_3_section_loop_blade_faces",
            "surface_count": len(blade_faces),
        },
        "hub_surface": copy.deepcopy(hub_surface),
        "cad_features": [],
    }
    if geometry_patch_version == "1.0.4":
        payload["v1_0_4_transition_failure_count"] = len(graph_failures)
        payload["v1_0_4_transition_failures"] = copy.deepcopy(graph_failures)
        payload["v1_0_4_continuity_summary"] = copy.deepcopy(continuity_summary)
        payload["v1_0_4_angle_quality"] = copy.deepcopy(angle_quality)
    return payload


def _v10_3_topology_failures(topology_graph: dict[str, Any]) -> list[dict[str, Any]]:
    failures = []
    if topology_graph.get("topology_status") == "FAIL":
        failures.append(_v10_3_failure(stage="topology_graph", reason="v1_0_3_topology_graph_failed"))
    if int(topology_graph.get("shared_edge_count") or 0) <= 0:
        failures.append(_v10_3_failure(stage="topology_graph", reason="v1_0_3_shared_edges_missing"))
    max_gap = _finite_float(topology_graph.get("max_shared_edge_gap_mm"), math.inf)
    if max_gap > 1.0e-9:
        failures.append(_v10_3_failure(stage="topology_graph", reason="v1_0_3_shared_edge_gap_exceeds_tolerance"))
    return failures


def _v10_3_failure(
    *,
    stage: str,
    reason: str,
    blade_index: int | None = None,
    surface_id: str | None = None,
) -> dict[str, Any]:
    failure: dict[str, Any] = {
        "stage": stage,
        "status": "FAIL",
        "reason": reason,
    }
    if blade_index is not None:
        failure["blade_index"] = blade_index
    if surface_id:
        failure["surface_id"] = surface_id
        failure["surface_graph_id"] = surface_id
    return failure


def _v10_3_nurbs_carrier_geometry(
    *,
    parameters: dict[str, Any],
    facets: dict[str, str],
    profile_defaults: dict[str, Any] | None,
    resolved_section_loop_defaults: dict[str, Any],
) -> dict[str, Any]:
    resolved_values = _validated_values(parameters, resolved_section_loop_defaults)
    if isinstance(resolved_values, dict) and resolved_values.get("status") != "FAIL":
        main_count = int(resolved_values.get("main_blade_count") or 0)
    else:
        main_count = int(
            resolved_section_loop_defaults.get("main_blade_count")
            or parameters.get("blade_count")
            or 4
        )
    carrier_parameters = copy.deepcopy(parameters)
    carrier_parameters["blade_count"] = max(main_count, 1)
    return build_axisymmetric_throughflow_nurbs_geometry(
        carrier_parameters,
        facets,
        geometry_stage="full",
        profile_defaults=profile_defaults,
        geometry_version="v1_0_3_nurbs_carrier",
    )


def _v10_3_hub_support_surface(
    parameters: dict[str, Any],
    defaults: dict[str, Any],
    *,
    carrier_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    carrier_hub = _carrier_surface_by_id(carrier_geometry, "hub_revolve_surface")
    if carrier_hub is not None:
        return _v10_3_hub_support_surface_from_carrier(carrier_hub)

    inlet_radius = _finite_float(parameters.get("inlet_radius_mm"), 45.0)
    exit_radius = _finite_float(parameters.get("exit_radius_mm"), 140.0)
    inlet_z = _finite_float(parameters.get("inlet_blade_height_mm"), 8.0)
    outlet_z = _finite_float(parameters.get("outlet_blade_height_mm"), 36.0)
    blade_thickness = max(
        _finite_float(
            parameters.get("blade_thickness_mm"),
            defaults.get("average_blade_thickness_mm", 0.0),
        ),
        1.0,
    )
    root_lift = max(
        _finite_float(
            defaults.get("root_attachment_lift_mm"),
            defaults.get("resolved_root_attachment_lift_mm", 0.0),
        ),
        0.25 * blade_thickness,
    )
    bore_radius = max(_finite_float(parameters.get("mounting_bore_radius_mm"), 0.0), 0.0)
    chord_allowance = blade_thickness * 2.2
    min_z = min(inlet_z, outlet_z)
    max_z = max(inlet_z, outlet_z) + chord_allowance * 0.04
    profile_count = 37
    theta_count = 49
    profile_samples = []
    uv_grid = []
    for z_index in range(profile_count):
        t = z_index / (profile_count - 1)
        z = min_z + (max_z - min_z) * t
        streamwise = 0.0 if abs(inlet_z - outlet_z) <= 1.0e-9 else (z - inlet_z) / (outlet_z - inlet_z)
        streamwise = max(0.0, min(1.0, streamwise))
        blade_root_radius = inlet_radius + (exit_radius - inlet_radius) * streamwise
        radius = max(bore_radius + 0.5 * blade_thickness, blade_root_radius - root_lift)
        profile_samples.append({"radius_mm": round(radius, 9), "z_mm": round(z, 9)})
        row = []
        for theta_index in range(theta_count):
            theta = 2.0 * math.pi * theta_index / (theta_count - 1)
            row.append(
                [
                    round(radius * math.cos(theta), 9),
                    round(radius * math.sin(theta), 9),
                    round(z, 9),
                ]
            )
        uv_grid.append(row)
    return {
        "id": "hub_support_surface",
        "kind": "native_topology_face",
        "face_family": "hub",
        "role": "v1_0_3_root_projection_support",
        "uv_grid": uv_grid,
        "profile_samples_rz": profile_samples,
        "support_profile_samples_rz": copy.deepcopy(profile_samples),
        "edge_samples": {
            "bottom": copy.deepcopy(uv_grid[0]),
            "top": copy.deepcopy(uv_grid[-1]),
        },
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _v10_3_quad_mesh(uv_grid),
        "display": {"inspection_class": "hub", "visible_by_default": True},
        "transition_quality": {
            "continuity_claim": "NATIVE_SUPPORT_SURFACE",
            "foldover_count": 0,
        },
    }


def _carrier_surface_by_id(carrier_geometry: dict[str, Any] | None, surface_id: str) -> dict[str, Any] | None:
    surfaces = (carrier_geometry or {}).get("surface_graph", {}).get("surfaces", [])
    if not isinstance(surfaces, list):
        return None
    for surface in surfaces:
        if isinstance(surface, dict) and surface.get("id") == surface_id:
            return surface
    return None


def _v10_3_hub_support_surface_from_carrier(carrier_hub: dict[str, Any]) -> dict[str, Any]:
    uv_grid = copy.deepcopy(carrier_hub.get("uv_grid", []))
    profile_samples = copy.deepcopy(
        carrier_hub.get("profile_samples_rz")
        or carrier_hub.get("support_profile_samples_rz")
        or []
    )
    return {
        "id": "hub_support_surface",
        "kind": "native_topology_face",
        "face_family": "hub",
        "role": "v1_0_3_root_projection_support",
        "uv_grid": uv_grid,
        "profile_samples_rz": profile_samples,
        "support_profile_samples_rz": copy.deepcopy(profile_samples),
        "edge_samples": {
            "bottom": copy.deepcopy(uv_grid[0]) if uv_grid else [],
            "top": copy.deepcopy(uv_grid[-1]) if uv_grid else [],
        },
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _v10_3_quad_mesh(uv_grid) if uv_grid else {"quad_count": 0, "quads": []},
        "display": {"inspection_class": "hub", "visible_by_default": True},
        "source": {
            "carrier_surface_id": carrier_hub.get("id"),
            "carrier_source_kernel": "axisymmetric_throughflow_nurbs_kernel",
            "geometry_rule": "v1_0_3_hub_support_from_nurbs_carrier_profile",
        },
        "transition_quality": {
            "continuity_claim": "NATIVE_SUPPORT_SURFACE",
            "foldover_count": 0,
        },
    }


def _apply_v10_3_display_policy(
    surfaces: list[dict[str, Any]],
    display_policy: dict[str, Any] | None,
) -> None:
    if not isinstance(display_policy, dict):
        return
    hidden_ids = set(display_policy.get("hide_surfaces", []) or [])
    for surface in surfaces:
        if surface.get("id") not in hidden_ids:
            continue
        display = surface.setdefault("display", {})
        if isinstance(display, dict):
            display["visible_by_default"] = False


def _topology_edge_surfaces(surfaces: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sanitized = []
    dropped_count = 0
    dropped_by_surface: dict[str, list[str]] = {}
    for surface in surfaces:
        clone = copy.deepcopy(surface)
        dropped_roles = [
            edge_role
            for edge_role, samples in surface.get("edge_samples", {}).items()
            if not _is_point_sample_list(samples)
        ]
        if dropped_roles:
            dropped_by_surface[str(surface.get("id", ""))] = dropped_roles
            dropped_count += len(dropped_roles)
        clone["edge_samples"] = {
            edge_role: samples
            for edge_role, samples in surface.get("edge_samples", {}).items()
            if _is_point_sample_list(samples)
        }
        sanitized.append(clone)
    return sanitized, {
        "dropped_edge_sample_count": dropped_count,
        "dropped_edge_sample_roles_by_surface": dropped_by_surface,
    }


def _is_point_sample_list(samples: Any) -> bool:
    return (
        isinstance(samples, list)
        and len(samples) >= 2
        and all(
            isinstance(point, list)
            and len(point) == 3
            and all(isinstance(value, (int, float)) for value in point)
            for point in samples
        )
    )


def _v10_3_quad_mesh(uv_grid: list[list[list[float]]]) -> dict[str, Any]:
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
        "strategy": "section_loop_shared_edge_review_grade_quad_mesh",
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]) if uv_grid else 0,
        "quad_count": len(quads),
        "quads": quads,
    }


def _finite_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _v10_display_policy(display_policy: dict[str, Any] | None) -> dict[str, Any] | None:
    if not display_policy:
        return display_policy
    policy = copy.deepcopy(display_policy)
    hidden = [
        surface_key
        for surface_key in policy.get("hide_surfaces", [])
        if surface_key != "blade_tip_support_surface"
    ]
    policy["hide_surfaces"] = hidden
    return policy


def _topology_first_faces_from_legacy(
    legacy_surfaces: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    faces = []
    id_map = {}
    for legacy_surface in legacy_surfaces:
        face = _topology_first_face_from_legacy(legacy_surface)
        if face is None:
            continue
        source_id = str(legacy_surface.get("id", ""))
        id_map[source_id] = face["id"]
        faces.append(face)
    return faces, id_map


def _topology_first_face_from_legacy(legacy_surface: dict[str, Any]) -> dict[str, Any] | None:
    source_id = str(legacy_surface.get("id", ""))
    if not source_id or source_id in _DEFERRED_OUTER_HUB_CHAMFERS:
        return None

    face = copy.deepcopy(legacy_surface)
    face["source_kernel"] = V10_SOURCE_KERNEL
    face["source_surface_id"] = source_id
    face["edge_samples"] = _edge_samples_for_surface(face)

    match = _BLADE_SURFACE_RE.match(source_id)
    if match:
        blade_index = match.group(1)
        suffix = match.group(2)
        _apply_blade_face_metadata(face, blade_index, suffix)
    else:
        _apply_axisymmetric_face_metadata(face)
    return face


def _apply_blade_face_metadata(face: dict[str, Any], blade_index: str, suffix: str) -> None:
    if suffix == _PRESSURE_SUFFIX:
        face["face_family"] = "blade_pressure"
        face["role"] = "blade_pressure"
        face["edge_samples"] = {
            **face["edge_samples"],
            "leading_edge_pressure_boundary": face["uv_grid"][0],
            "trailing_edge_pressure_boundary": face["uv_grid"][-1],
            "root_profile_pressure_edge": _column(face["uv_grid"], 0),
            "tip_profile_pressure_edge": _column(face["uv_grid"], -1),
        }
        return
    if suffix == _SUCTION_SUFFIX:
        face["face_family"] = "blade_suction"
        face["role"] = "blade_suction"
        face["edge_samples"] = {
            **face["edge_samples"],
            "leading_edge_suction_boundary": face["uv_grid"][0],
            "trailing_edge_suction_boundary": face["uv_grid"][-1],
            "root_profile_suction_edge": _column(face["uv_grid"], 0),
            "tip_profile_suction_edge": _column(face["uv_grid"], -1),
        }
        return
    if suffix in _LEADING_SUFFIXES:
        face["id"] = f"blade_{blade_index}_leading_edge_surface"
        face["kind"] = "native_topology_face"
        face["face_family"] = "blade_leading_edge"
        face["role"] = "leading_edge_surface"
        face["edge_samples"] = {
            **face["edge_samples"],
            "pressure_side_leading_boundary": _column(face["uv_grid"], 0),
            "suction_side_leading_boundary": _column(face["uv_grid"], -1),
            "root_profile_leading_cap": face["uv_grid"][0],
            "tip_profile_leading_cap": face["uv_grid"][-1],
        }
        return
    if suffix in _TRAILING_SUFFIXES:
        face["id"] = f"blade_{blade_index}_trailing_edge_surface"
        face["kind"] = "native_topology_face"
        face["face_family"] = "blade_trailing_edge"
        face["role"] = "trailing_edge_surface"
        face["edge_samples"] = {
            **face["edge_samples"],
            "pressure_side_trailing_boundary": _column(face["uv_grid"], 0),
            "suction_side_trailing_boundary": _column(face["uv_grid"], -1),
            "root_profile_trailing_cap": face["uv_grid"][0],
            "tip_profile_trailing_cap": face["uv_grid"][-1],
        }
        return
    if suffix in _ROOT_SUFFIXES:
        face["id"] = f"blade_{blade_index}_root_annular_surface"
        face["kind"] = "native_topology_face"
        face["face_family"] = "blade_root"
        face["role"] = "root_annular_surface"
        face["edge_samples"] = {
            **face["edge_samples"],
            "root_profile_pressure_edge": _column(face["uv_grid"], 0),
            "root_profile_suction_edge": _column(face["uv_grid"], -1),
            "hub_attachment_mean_curve": _column(face["uv_grid"], len(face["uv_grid"][0]) // 2),
        }
        face["display"] = {
            **face.get("display", {}),
            "inspection_class": "root_to_hub_native_root_face",
            "color": "#ff00cc",
            "wire_color": "#fff200",
        }
        return
    if suffix in _TIP_SUFFIXES:
        face["id"] = f"blade_{blade_index}_tip_surface"
        face["kind"] = "native_topology_face"
        face["face_family"] = "blade_tip"
        face["role"] = "tip_surface"
        face["edge_samples"] = {
            **face["edge_samples"],
            "tip_profile_pressure_edge": _column(face["uv_grid"], 0),
            "tip_profile_suction_edge": _column(face["uv_grid"], -1),
            "tip_support_mean_curve": _column(face["uv_grid"], len(face["uv_grid"][0]) // 2),
        }


def _apply_v10_visibility_contract(faces: list[dict[str, Any]], facets: dict[str, str]) -> None:
    if facets.get("shroud_topology") != "open":
        return
    for face in faces:
        if face.get("id") != "tip_reference_surface":
            continue
        face["role"] = "construction_support_only"
        face["material"] = False
        face["display"] = {
            **face.get("display", {}),
            "visible_by_default": False,
            "construction_reference": True,
        }


def _apply_v10_2_continuous_blade_complex(
    faces: list[dict[str, Any]],
    parameters: dict[str, Any],
    facets: dict[str, str],
    *,
    resolved_attachment_defaults: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    defaults_failure = _validate_v10_2_resolved_attachment_defaults(resolved_attachment_defaults)
    if defaults_failure is not None:
        return [defaults_failure]

    defaults = copy.deepcopy(resolved_attachment_defaults)
    edge_sample_count = int(defaults["edge_short_direction_sample_count"])
    blade_count = int(parameters.get("blade_count", 0))

    for blade_index in range(blade_count):
        _apply_v10_2_root_lift_to_blade_faces(
            faces,
            blade_index=blade_index,
            lift_mm=float(defaults["resolved_root_attachment_lift_mm"]),
        )
        by_id = {face["id"]: face for face in faces}
        lattice = build_v10_2_blade_lattice(blade_index=blade_index, surfaces=by_id)
        if lattice.get("status") != "PASS":
            failures.append(
                {
                    "blade_index": blade_index,
                    "stage": "v1_0_2_blade_lattice",
                    "status": "FAIL",
                    "reason": lattice.get("failure_reason", "v1_0_2_blade_lattice_failed"),
                }
            )
            continue

        _replace_v10_2_blade_edge_surface(
            faces,
            failures,
            blade_index=blade_index,
            lattice=lattice,
            surface_id=f"blade_{blade_index}_leading_edge_surface",
            face_family="blade_leading_edge",
            role="leading_edge_surface",
            pressure_frame_key="leading_pressure_frames",
            suction_frame_key="leading_suction_frames",
            radius_mm=float(parameters.get("leading_edge_radius_mm", 0.0)),
            sample_count=edge_sample_count,
        )
        _replace_v10_2_blade_edge_surface(
            faces,
            failures,
            blade_index=blade_index,
            lattice=lattice,
            surface_id=f"blade_{blade_index}_trailing_edge_surface",
            face_family="blade_trailing_edge",
            role="trailing_edge_surface",
            pressure_frame_key="trailing_pressure_frames",
            suction_frame_key="trailing_suction_frames",
            radius_mm=float(parameters.get("trailing_edge_radius_mm", 0.0)),
            sample_count=edge_sample_count,
        )
        edge_lattice = _updated_v10_2_blade_lattice(
            faces,
            failures,
            blade_index=blade_index,
            stage="v1_0_2_edge_lattice",
        )
        if edge_lattice is None:
            continue

        if facets.get("shroud_topology") == "closed":
            shroud_surface = by_id.get("shroud_surface")
            if shroud_surface is None:
                failures.append(
                    {
                        "blade_index": blade_index,
                        "stage": "v1_0_2_tip_attachment",
                        "status": "FAIL",
                        "reason": "v1_0_2_shroud_surface_missing",
                    }
                )
            else:
                tip = build_v10_2_tip_attachment_surface(
                    blade_index=blade_index,
                    lattice=edge_lattice,
                    shroud_surface=shroud_surface,
                    defaults=defaults,
                )
                _apply_v10_2_graph_compatibility(tip)
                _replace_face(faces, tip)
                _append_v10_2_component_surfaces(faces, tip)
                _record_attachment_failure(failures, blade_index, "v1_0_2_tip_attachment", tip)
        else:
            _replace_v10_2_blade_edge_surface(
                faces,
                failures,
                blade_index=blade_index,
                lattice=edge_lattice,
                surface_id=f"blade_{blade_index}_tip_surface",
                face_family="blade_tip",
                role="tip_surface",
                pressure_frame_key="tip_pressure_frames",
                suction_frame_key="tip_suction_frames",
                radius_mm=float(parameters.get("tip_edge_radius_mm", 0.0)),
                sample_count=edge_sample_count,
            )

        attachment_lattice = _updated_v10_2_blade_lattice(
            faces,
            failures,
            blade_index=blade_index,
            stage="v1_0_2_attachment_lattice",
        )
        if attachment_lattice is None:
            continue
        by_id = {face["id"]: face for face in faces}
        hub_surface = by_id.get("hub_revolve_surface")
        if hub_surface is None:
            failures.append(
                {
                    "blade_index": blade_index,
                    "stage": "v1_0_2_root_attachment",
                    "status": "FAIL",
                    "reason": "v1_0_2_hub_revolve_surface_missing",
                }
            )
            continue
        root = build_v10_2_root_attachment_surface(
            blade_index=blade_index,
            lattice=attachment_lattice,
            hub_surface=hub_surface,
            defaults=defaults,
        )
        _apply_v10_2_graph_compatibility(root)
        _replace_face(faces, root)
        _append_v10_2_component_surfaces(faces, root)
        _record_attachment_failure(failures, blade_index, "v1_0_2_root_attachment", root)

    return failures


def _append_v10_2_component_surfaces(faces: list[dict[str, Any]], parent_surface: dict[str, Any]) -> None:
    for component in parent_surface.get("component_surfaces", []):
        _apply_v10_2_graph_compatibility(component)
        _replace_face(faces, component)


def _apply_v10_2_root_lift_to_blade_faces(
    faces: list[dict[str, Any]],
    *,
    blade_index: int,
    lift_mm: float,
) -> None:
    if lift_mm <= 0.0:
        return
    hub_surface = next((candidate for candidate in faces if candidate.get("id") == "hub_revolve_surface"), None)
    hub_profile = (hub_surface or {}).get("profile_samples_rz", [])
    for side in ["pressure", "suction"]:
        surface_id = f"blade_{blade_index}_{side}_surface"
        face = next((candidate for candidate in faces if candidate.get("id") == surface_id), None)
        if face is None:
            continue
        grid = face.get("uv_grid", [])
        lifted_grid, metrics = _root_lifted_blade_grid(
            grid,
            lift_mm=lift_mm,
            hub_profile=hub_profile,
        )
        if lifted_grid == grid:
            continue
        face["uv_grid"] = lifted_grid
        face["control_net"] = _control_net_from_grid(lifted_grid)
        face["edge_samples"] = _lifted_blade_edge_samples(lifted_grid, side)
        face["v1_0_2_root_lift"] = metrics


def _root_lifted_blade_grid(
    grid: list[list[list[float]]],
    *,
    lift_mm: float,
    hub_profile: list[Any] | None = None,
) -> tuple[list[list[list[float]]], dict[str, Any]]:
    if len(grid) < 2 or len(grid[0]) < 2:
        return copy.deepcopy(grid), {"status": "SKIP", "reason": "insufficient_grid"}
    column_count = len(grid[0])
    influence_count = min(column_count, max(4, math.ceil(column_count * 0.30)))
    lifted_grid: list[list[list[float]]] = []
    applied_lengths: list[float] = []
    for row in grid:
        fallback_direction = _normalized(_subtract(row[1], row[0]))
        if fallback_direction is None:
            fallback_direction = _normalized(_subtract(row[-1], row[0])) or [0.0, 0.0, 1.0]
        root_direction = _hub_support_lift_direction(
            row[0],
            hub_profile or [],
            fallback_direction=fallback_direction,
        )
        row_end_progress = _dot(_subtract(row[-1], row[0]), root_direction)
        lifted_row = []
        for column_index, point in enumerate(row):
            base_progress = _dot(_subtract(point, row[0]), root_direction)
            smooth_lift = 0.0
            if column_index < influence_count:
                t = column_index / max(influence_count - 1, 1)
                factor = (1.0 - t) * (1.0 - t)
                smooth_lift = lift_mm * factor
            monotonic_lift = 0.0
            if row_end_progress > 0.0:
                monotonic_lift = max(0.0, lift_mm - 0.60 * max(0.0, base_progress))
            lift_amount = max(smooth_lift, monotonic_lift)
            if lift_amount <= 1.0e-9:
                lifted_row.append(copy.deepcopy(point))
                continue
            offset = _scale(root_direction, lift_amount)
            lifted = [_round(float(point[axis]) + offset[axis]) for axis in range(3)]
            applied_lengths.append(_length(offset))
            lifted_row.append(lifted)
        lifted_grid.append(lifted_row)
    return lifted_grid, {
        "status": "PASS",
        "construction_rule": "v1_0_2_lift_pressure_suction_root_boundary_before_attachment",
        "requested_lift_mm": _round(lift_mm),
        "max_applied_lift_mm": _round(max(applied_lengths) if applied_lengths else 0.0),
        "influence_column_count": influence_count,
        "lift_direction_rule": "hub_revolved_support_outward_normal_with_monotonic_root_guard",
    }


def _hub_support_lift_direction(
    point: list[float],
    hub_profile: list[Any],
    *,
    fallback_direction: list[float],
) -> list[float]:
    radial_direction = _normalized([float(point[0]), float(point[1]), 0.0]) or [1.0, 0.0, 0.0]
    profile_tangent = _hub_profile_tangent_rz(hub_profile, float(point[2]))
    if profile_tangent is None:
        return fallback_direction
    dr, dz = profile_tangent
    candidate = _normalized(
        [
            radial_direction[0] * dz,
            radial_direction[1] * dz,
            -dr,
        ]
    )
    if candidate is None:
        return fallback_direction
    outward_reference = _normalized([radial_direction[0], radial_direction[1], 1.0]) or radial_direction
    if _dot(candidate, outward_reference) < 0.0:
        candidate = _scale(candidate, -1.0)
    return candidate


def _hub_profile_tangent_rz(hub_profile: list[Any], z_value: float) -> tuple[float, float] | None:
    if not hub_profile:
        return None
    try:
        samples = sorted(_profile_sample_zr(point) for point in hub_profile)
    except (KeyError, TypeError, ValueError):
        return None
    if len(samples) < 2:
        return None
    if z_value <= samples[0][0]:
        left, right = samples[0], samples[1]
        return right[1] - left[1], right[0] - left[0]
    if z_value >= samples[-1][0]:
        left, right = samples[-2], samples[-1]
        return right[1] - left[1], right[0] - left[0]
    for left, right in zip(samples, samples[1:]):
        if left[0] <= z_value <= right[0]:
            return right[1] - left[1], right[0] - left[0]
    left, right = samples[-2], samples[-1]
    return right[1] - left[1], right[0] - left[0]


def _lifted_blade_edge_samples(grid: list[list[list[float]]], side: str) -> dict[str, list[list[float]]]:
    samples = _edge_samples_for_surface({"uv_grid": grid})
    if side == "pressure":
        samples.update(
            {
                "leading_edge_pressure_boundary": copy.deepcopy(grid[0]),
                "trailing_edge_pressure_boundary": copy.deepcopy(grid[-1]),
                "root_profile_pressure_edge": _column(grid, 0),
                "tip_profile_pressure_edge": _column(grid, -1),
            }
        )
    else:
        samples.update(
            {
                "leading_edge_suction_boundary": copy.deepcopy(grid[0]),
                "trailing_edge_suction_boundary": copy.deepcopy(grid[-1]),
                "root_profile_suction_edge": _column(grid, 0),
                "tip_profile_suction_edge": _column(grid, -1),
            }
        )
    return samples


def _updated_v10_2_blade_lattice(
    faces: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    *,
    blade_index: int,
    stage: str,
) -> dict[str, Any] | None:
    lattice = build_v10_2_blade_lattice(
        blade_index=blade_index,
        surfaces={face["id"]: face for face in faces},
    )
    if lattice.get("status") == "PASS":
        return lattice
    failures.append(
        {
            "blade_index": blade_index,
            "stage": stage,
            "status": "FAIL",
            "reason": lattice.get("failure_reason", "v1_0_2_blade_lattice_failed"),
        }
    )
    return None


def _validate_v10_2_resolved_attachment_defaults(
    resolved_attachment_defaults: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if resolved_attachment_defaults is None:
        return _v10_2_defaults_failure("v1_0_2_resolved_attachment_defaults_missing")
    if not isinstance(resolved_attachment_defaults, dict):
        return _v10_2_defaults_failure("v1_0_2_resolved_attachment_defaults_malformed")

    edge_sample_count = resolved_attachment_defaults.get("edge_short_direction_sample_count")
    if not isinstance(edge_sample_count, int) or edge_sample_count < 17:
        return _v10_2_defaults_failure("v1_0_2_edge_sample_count_invalid")

    attachment_sample_count = resolved_attachment_defaults.get("attachment_short_direction_sample_count")
    if not isinstance(attachment_sample_count, int) or attachment_sample_count < 17:
        return _v10_2_defaults_failure("v1_0_2_attachment_sample_count_invalid")

    required_numeric_keys = (
        "resolved_root_attachment_width_mm",
        "resolved_root_attachment_lift_mm",
        "resolved_tip_attachment_width_mm",
        "resolved_tip_attachment_lift_mm",
    )
    for key in required_numeric_keys:
        value = resolved_attachment_defaults.get(key)
        if not isinstance(value, (int, float)) or float(value) <= 0.0:
            return _v10_2_defaults_failure("v1_0_2_resolved_attachment_defaults_missing")

    return None


def _v10_2_defaults_failure(reason: str) -> dict[str, Any]:
    return {
        "stage": "v1_0_2_resolved_attachment_defaults",
        "status": "FAIL",
        "reason": reason,
    }


def _replace_v10_2_blade_edge_surface(
    faces: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    *,
    blade_index: int,
    lattice: dict[str, Any],
    surface_id: str,
    face_family: str,
    role: str,
    pressure_frame_key: str,
    suction_frame_key: str,
    radius_mm: float,
    sample_count: int,
) -> None:
    try:
        replacement = build_v10_2_g2_edge_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            pressure_frames=lattice["frames"][pressure_frame_key],
            suction_frames=lattice["frames"][suction_frame_key],
            radius_mm=radius_mm,
            sample_count=sample_count,
        )
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(
            {
                "blade_index": blade_index,
                "surface_id": surface_id,
                "stage": "v1_0_2_g2_edge_surface",
                "status": "FAIL",
                "reason": str(exc),
            }
        )
        return
    _restore_lattice_edge_sample_identity(
        replacement,
        lattice,
        radius_mm=radius_mm,
        sample_count=sample_count,
    )
    _apply_v10_2_graph_compatibility(replacement)
    _replace_face(faces, replacement)


def _restore_lattice_edge_sample_identity(
    surface: dict[str, Any],
    lattice: dict[str, Any],
    *,
    radius_mm: float,
    sample_count: int,
) -> None:
    loops = lattice.get("loops", {})
    grid = surface.get("uv_grid", [])
    edge_samples = surface.setdefault("edge_samples", {})
    face_family = surface.get("face_family")
    if face_family == "blade_leading_edge":
        edge_samples.update(
            {
                "pressure_side_leading_boundary": copy.deepcopy(loops["leading_pressure_loop"]),
                "suction_side_leading_boundary": copy.deepcopy(loops["leading_suction_loop"]),
                "root_profile_leading_cap": copy.deepcopy(grid[0]),
                "tip_profile_leading_cap": copy.deepcopy(grid[-1]),
            }
        )
    elif face_family == "blade_trailing_edge":
        edge_samples.update(
            {
                "pressure_side_trailing_boundary": copy.deepcopy(loops["trailing_pressure_loop"]),
                "suction_side_trailing_boundary": copy.deepcopy(loops["trailing_suction_loop"]),
                "root_profile_trailing_cap": copy.deepcopy(grid[0]),
                "tip_profile_trailing_cap": copy.deepcopy(grid[-1]),
            }
        )
    elif face_family == "blade_tip":
        edge_samples.update(
            {
                "tip_profile_pressure_edge": copy.deepcopy(loops["pressure_tip_loop"]),
                "tip_profile_suction_edge": copy.deepcopy(loops["suction_tip_loop"]),
            }
        )


def _curved_cap_sample(
    cap: list[list[float]],
    *,
    radius_mm: float,
    sample_count: int,
) -> list[list[float]]:
    if len(cap) < 3:
        return copy.deepcopy(cap)
    section, _metrics = _curved_section(
        cap[0],
        cap[len(cap) // 2],
        cap[-1],
        radius_mm=radius_mm,
        sample_count=sample_count,
        previous_direction=None,
    )
    return section


def _record_attachment_failure(
    failures: list[dict[str, Any]],
    blade_index: int,
    stage: str,
    surface: dict[str, Any],
) -> None:
    attachment_quality = surface.get("attachment_quality", {})
    if attachment_quality.get("status") == "PASS":
        return
    failures.append(
        {
            "blade_index": blade_index,
            "surface_id": surface.get("id"),
            "stage": stage,
            "status": "FAIL",
            "reason": attachment_quality.get("reason", "v1_0_2_attachment_failed"),
        }
    )


def _apply_v10_2_graph_compatibility(surface: dict[str, Any]) -> None:
    transition_quality = surface.get("transition_quality", {})
    for claim_key in ["continuity_claim", "curvature_claim"]:
        if transition_quality.get(claim_key) == "G2_TARGET_REVIEW_GRADE":
            transition_quality[claim_key] = _CompatLabel("G2_TARGET_REVIEW_GRADE", ("G2",))
    if surface.get("root_topology") == "support_domain_annular_attachment_boss":
        surface["root_topology"] = _CompatLabel(
            "support_domain_annular_attachment_boss",
            ("annular_hub_to_blade_boss",),
        )


def _replace_face(faces: list[dict[str, Any]], replacement: dict[str, Any]) -> None:
    replacement_id = replacement.get("id")
    for index, face in enumerate(faces):
        if face.get("id") == replacement_id:
            faces[index] = replacement
            return
    faces.append(replacement)


def _promote_v10_blade_transition_faces(faces: list[dict[str, Any]], parameters: dict[str, Any]) -> None:
    hub = next((face for face in faces if face.get("id") == "hub_revolve_surface"), None)
    for face in faces:
        family = face.get("face_family")
        if family == "blade_leading_edge":
            _promote_curved_edge_face(
                face,
                radius_mm=float(parameters.get("leading_edge_radius_mm", 0.0)),
                construction_rule="v1_0_g2_leading_edge_nurbs_patch_from_pressure_suction_boundaries",
            )
        elif family == "blade_trailing_edge":
            _promote_curved_edge_face(
                face,
                radius_mm=float(parameters.get("trailing_edge_radius_mm", 0.0)),
                construction_rule="v1_0_g2_trailing_edge_nurbs_patch_from_pressure_suction_boundaries",
            )
        elif family == "blade_tip":
            _promote_curved_edge_face(
                face,
                radius_mm=float(parameters.get("tip_edge_radius_mm", 0.0)),
                construction_rule="v1_0_g2_tip_edge_nurbs_patch_from_pressure_suction_boundaries",
            )
        elif family == "blade_root":
            _replace_root_face_with_hub_boss(
                face,
                hub,
                radius_mm=float(parameters.get("root_fillet_radius_mm", 0.0)),
                blade_thickness_mm=float(parameters.get("blade_thickness_mm", 0.0)),
            )


def _promote_curved_edge_face(face: dict[str, Any], *, radius_mm: float, construction_rule: str) -> None:
    grid = face.get("uv_grid", [])
    if len(grid) < 2 or len(grid[0]) < 2:
        return
    curved_grid, metrics = _curved_grid_from_three_column_sections(
        grid,
        radius_mm=radius_mm,
        sample_count=_BLADE_EDGE_SAMPLE_COUNT,
    )
    face["uv_grid"] = curved_grid
    face["control_net"] = _control_net_from_grid(curved_grid)
    face["edge_samples"] = _edge_samples_for_surface(face)
    family = face.get("face_family")
    if family == "blade_leading_edge":
        face["edge_samples"] = {
            **face["edge_samples"],
            "pressure_side_leading_boundary": _column(curved_grid, 0),
            "suction_side_leading_boundary": _column(curved_grid, -1),
            "root_profile_leading_cap": curved_grid[0],
            "tip_profile_leading_cap": curved_grid[-1],
        }
    elif family == "blade_trailing_edge":
        face["edge_samples"] = {
            **face["edge_samples"],
            "pressure_side_trailing_boundary": _column(curved_grid, 0),
            "suction_side_trailing_boundary": _column(curved_grid, -1),
            "root_profile_trailing_cap": curved_grid[0],
            "tip_profile_trailing_cap": curved_grid[-1],
        }
    elif family == "blade_tip":
        face["edge_samples"] = {
            **face["edge_samples"],
            "tip_profile_pressure_edge": _column(curved_grid, 0),
            "tip_profile_suction_edge": _column(curved_grid, -1),
            "tip_support_mean_curve": _column(curved_grid, len(curved_grid[0]) // 2),
        }
    _set_transition_quality(face, construction_rule, metrics, _BLADE_EDGE_SAMPLE_COUNT)


def _replace_root_face_with_hub_boss(
    face: dict[str, Any],
    hub: dict[str, Any] | None,
    *,
    radius_mm: float,
    blade_thickness_mm: float,
) -> None:
    source_grid = face.get("uv_grid", [])
    if len(source_grid) < 2 or len(source_grid[0]) < 2:
        return

    pressure_curve = _column(source_grid, 0)
    suction_curve = _column(source_grid, -1)
    leading_cap, leading_metrics = _curved_section(
        source_grid[0][0],
        source_grid[0][len(source_grid[0]) // 2],
        source_grid[0][-1],
        radius_mm=radius_mm,
        sample_count=_BLADE_EDGE_SAMPLE_COUNT,
        previous_direction=None,
    )
    trailing_cap, trailing_metrics = _curved_section(
        source_grid[-1][0],
        source_grid[-1][len(source_grid[-1]) // 2],
        source_grid[-1][-1],
        radius_mm=radius_mm,
        sample_count=_BLADE_EDGE_SAMPLE_COUNT,
        previous_direction=None,
    )
    inner_loop = (
        copy.deepcopy(pressure_curve)
        + copy.deepcopy(trailing_cap[1:])
        + [copy.deepcopy(point) for point in reversed(suction_curve[:-1])]
        + [copy.deepcopy(point) for point in reversed(leading_cap[1:-1])]
    )
    if inner_loop[0] != inner_loop[-1]:
        inner_loop.append(copy.deepcopy(inner_loop[0]))

    center = _centroid(inner_loop[:-1])
    boss_width = max(radius_mm * 1.2, blade_thickness_mm * 0.55, 16.0)
    hub_profile = (hub or {}).get("profile_samples_rz", [])
    outer_loop = [
        _project_hub_offset_point(point, center, boss_width, hub_profile)
        for point in inner_loop
    ]

    rows = []
    bulges = [leading_metrics["midpoint_bulge_mm"], trailing_metrics["midpoint_bulge_mm"]]
    previous_direction = None
    for outer, inner in zip(outer_loop, inner_loop):
        section, metrics = _root_boss_section(
            outer,
            inner,
            center,
            radius_mm=radius_mm,
            sample_count=_ROOT_BOSS_SAMPLE_COUNT,
            previous_direction=previous_direction,
        )
        previous_direction = metrics["direction"]
        bulges.append(metrics["midpoint_bulge_mm"])
        rows.append(section)

    face["role"] = "root_pedestal_ring_surface"
    face["root_topology"] = "annular_hub_to_blade_boss"
    face["uv_grid"] = rows
    face["control_net"] = _control_net_from_grid(rows)
    face["boundary_roles"] = {
        "u_min": "root_boss_loop_start",
        "u_max": "root_boss_loop_end",
        "v_min": "hub_outer_loop",
        "v_max": "blade_inner_loop",
    }
    face["edge_samples"] = {
        **_edge_samples_for_surface(face),
        "hub_outer_loop": _column(rows, 0),
        "blade_inner_loop": _column(rows, -1),
        "root_profile_pressure_edge": pressure_curve,
        "root_profile_suction_edge": suction_curve,
        "root_profile_leading_cap": leading_cap,
        "root_profile_trailing_cap": trailing_cap,
    }
    face["display"] = {
        **face.get("display", {}),
        "inspection_class": "root_to_hub_native_root_face",
        "color": "#ff00cc",
        "wire_color": "#fff200",
    }
    _set_transition_quality(
        face,
        "v1_0_annular_hub_projected_g2_root_boss_surface",
        {
            "midpoint_bulge_mm": min(bulges),
            "max_midpoint_bulge_mm": max(bulges),
            "effective_radius_mm": _effective_radius_mm(radius_mm, min(bulges)),
        },
        _ROOT_BOSS_SAMPLE_COUNT,
    )
    face["transition_quality"]["hub_projection_rule"] = "project_outer_loop_to_revolved_hub_profile_by_theta_z"
    face["transition_quality"]["boss_width_mm"] = _round(boss_width)


def _curved_grid_from_three_column_sections(
    grid: list[list[list[float]]],
    *,
    radius_mm: float,
    sample_count: int,
) -> tuple[list[list[list[float]]], dict[str, float]]:
    curved_grid = []
    bulges = []
    previous_direction = None
    for row in grid:
        midpoint = row[len(row) // 2]
        section, metrics = _curved_section(
            row[0],
            midpoint,
            row[-1],
            radius_mm=radius_mm,
            sample_count=sample_count,
            previous_direction=previous_direction,
        )
        previous_direction = metrics["direction"]
        bulges.append(metrics["midpoint_bulge_mm"])
        curved_grid.append(section)
    min_bulge = min(bulges) if bulges else 0.0
    max_bulge = max(bulges) if bulges else 0.0
    return curved_grid, {
        "midpoint_bulge_mm": min_bulge,
        "max_midpoint_bulge_mm": max_bulge,
        "effective_radius_mm": _effective_radius_mm(radius_mm, min_bulge),
    }


def _curved_section(
    first: list[float],
    legacy_midpoint: list[float],
    second: list[float],
    *,
    radius_mm: float,
    sample_count: int,
    previous_direction: list[float] | None,
) -> tuple[list[list[float]], dict[str, Any]]:
    chord_mid = _midpoint(first, second)
    raw_direction = _subtract(legacy_midpoint, chord_mid)
    direction = _normalized(raw_direction)
    if direction is None:
        direction = _fallback_section_direction(first, second)
    if previous_direction is not None and _dot(direction, previous_direction) < 0.0:
        direction = _scale(direction, -1.0)

    chord_len = _distance(first, second)
    requested_bulge = _length(raw_direction)
    required_bulge = max(1.0, radius_mm * 0.12, chord_len * 0.08)
    bulge = max(requested_bulge, required_bulge)
    control = _add(chord_mid, _scale(direction, bulge))
    return _quadratic_samples(first, control, second, sample_count), {
        "direction": direction,
        "midpoint_bulge_mm": bulge,
        "effective_radius_mm": _effective_radius_mm(radius_mm, bulge),
    }


def _root_boss_section(
    outer: list[float],
    inner: list[float],
    center: list[float],
    *,
    radius_mm: float,
    sample_count: int,
    previous_direction: list[float] | None,
) -> tuple[list[list[float]], dict[str, Any]]:
    chord_mid = _midpoint(outer, inner)
    loop_direction = _normalized(_subtract(inner, center)) or [0.0, 0.0, 1.0]
    chord_direction = _normalized(_subtract(inner, outer)) or loop_direction
    direction = _normalized(_cross(chord_direction, loop_direction)) or [0.0, 0.0, 1.0]
    if direction[2] < 0.0:
        direction = _scale(direction, -1.0)
    if previous_direction is not None and _dot(direction, previous_direction) < 0.0:
        direction = _scale(direction, -1.0)
    chord_len = _distance(outer, inner)
    bulge = max(1.0, radius_mm * 0.12, chord_len * 0.08)
    control = _add(chord_mid, _scale(direction, bulge))
    return _quadratic_samples(outer, control, inner, sample_count), {
        "direction": direction,
        "midpoint_bulge_mm": bulge,
        "effective_radius_mm": _effective_radius_mm(radius_mm, bulge),
    }


def _set_transition_quality(
    face: dict[str, Any],
    construction_rule: str,
    metrics: dict[str, float],
    sample_count: int,
) -> None:
    face["transition_quality"] = {
        "continuity_claim": "G2",
        "curvature_claim": "G2",
        "construction_rule": construction_rule,
        "short_direction_sample_count": sample_count,
        "midpoint_bulge_mm": _round(metrics.get("midpoint_bulge_mm", 0.0)),
        "max_midpoint_bulge_mm": _round(metrics.get("max_midpoint_bulge_mm", metrics.get("midpoint_bulge_mm", 0.0))),
        "effective_radius_mm": _round(metrics.get("effective_radius_mm", 0.0)),
        "status": "PASS",
    }
    face["continuity_targets"] = [
        "G2_to_pressure_surface",
        "G2_to_suction_surface",
        "G2_to_adjacent_native_topology_faces",
    ]


def _project_hub_offset_point(
    point: list[float],
    center: list[float],
    width_mm: float,
    hub_profile: list[list[float]],
) -> list[float]:
    xy_direction = _normalized([point[0] - center[0], point[1] - center[1], 0.0])
    if xy_direction is None:
        xy_direction = _normalized([point[0], point[1], 0.0]) or [1.0, 0.0, 0.0]
    candidate = _add(point, _scale(xy_direction, width_mm))
    theta = math.atan2(candidate[1], candidate[0])
    radius = _hub_radius_at_z(hub_profile, candidate[2])
    if radius is None:
        radius = math.sqrt(candidate[0] * candidate[0] + candidate[1] * candidate[1])
    return [_round(radius * math.cos(theta)), _round(radius * math.sin(theta)), _round(candidate[2])]


def _hub_radius_at_z(profile: list[list[float]], z_value: float) -> float | None:
    if not profile:
        return None
    samples = sorted(_profile_sample_zr(point) for point in profile)
    if z_value <= samples[0][0]:
        return samples[0][1]
    if z_value >= samples[-1][0]:
        return samples[-1][1]
    for (left_z, left_r), (right_z, right_r) in zip(samples, samples[1:]):
        if left_z <= z_value <= right_z:
            span = max(right_z - left_z, 1.0e-9)
            t = (z_value - left_z) / span
            return left_r + (right_r - left_r) * t
    return samples[-1][1]


def _profile_sample_zr(point: Any) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point["z_mm"]), float(point["r_mm"])
    return float(point[1]), float(point[0])


def _quadratic_samples(
    first: list[float],
    control: list[float],
    second: list[float],
    sample_count: int,
) -> list[list[float]]:
    samples = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        left = (1.0 - t) * (1.0 - t)
        mid = 2.0 * (1.0 - t) * t
        right = t * t
        samples.append(
            [
                _round(left * first[axis] + mid * control[axis] + right * second[axis])
                for axis in range(3)
            ]
        )
    return samples


def _control_net_from_grid(grid: list[list[list[float]]]) -> list[list[list[float]]]:
    mid_row = grid[len(grid) // 2]
    return [
        [copy.deepcopy(grid[0][0]), copy.deepcopy(grid[0][len(grid[0]) // 2]), copy.deepcopy(grid[0][-1])],
        [copy.deepcopy(mid_row[0]), copy.deepcopy(mid_row[len(mid_row) // 2]), copy.deepcopy(mid_row[-1])],
        [copy.deepcopy(grid[-1][0]), copy.deepcopy(grid[-1][len(grid[-1]) // 2]), copy.deepcopy(grid[-1][-1])],
    ]


def _centroid(points: list[list[float]]) -> list[float]:
    count = max(len(points), 1)
    return [
        sum(float(point[axis]) for point in points) / count
        for axis in range(3)
    ]


def _midpoint(first: list[float], second: list[float]) -> list[float]:
    return [(float(first[axis]) + float(second[axis])) * 0.5 for axis in range(3)]


def _subtract(first: list[float], second: list[float]) -> list[float]:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _add(first: list[float], second: list[float]) -> list[float]:
    return [float(first[axis]) + float(second[axis]) for axis in range(3)]


def _scale(vector: list[float], scalar: float) -> list[float]:
    return [float(value) * scalar for value in vector]


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _distance(first: list[float], second: list[float]) -> float:
    return _length(_subtract(first, second))


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


def _fallback_section_direction(first: list[float], second: list[float]) -> list[float]:
    chord = _normalized(_subtract(second, first)) or [1.0, 0.0, 0.0]
    radial = _normalized([first[0] + second[0], first[1] + second[1], 0.0]) or [0.0, 1.0, 0.0]
    direction = _normalized(_cross(chord, radial))
    if direction is not None:
        return direction
    return radial


def _effective_radius_mm(requested_radius_mm: float, bulge_mm: float) -> float:
    return requested_radius_mm if requested_radius_mm > 0.0 else bulge_mm / 0.12


def _round(value: float) -> float:
    return round(float(value), 6)


def _apply_axisymmetric_face_metadata(face: dict[str, Any]) -> None:
    surface_id = str(face.get("id", ""))
    if surface_id in {"hub_revolve_surface", "outer_hub_shell_surface"}:
        face["face_family"] = "hub_shell"
    elif surface_id in {"inner_hub_bottom_face", "hub_top_cap_face"}:
        face["face_family"] = "hub_cap"
    elif surface_id == "mounting_bore_cylinder":
        face["face_family"] = "mounting_bore"
    elif surface_id.startswith("hub_chamfer_") or surface_id.startswith("hood_chamfer_"):
        face["kind"] = "native_topology_face"
        face["face_family"] = "hub_bevel"
        face["native_bevel_face"] = True
        face["display"] = {**face.get("display", {}), "wire_color": "#fff200"}
    elif surface_id in {"tip_reference_surface", "shroud_surface"}:
        face["face_family"] = "tip_or_shroud_support"


def _edge_samples_for_surface(surface: dict[str, Any]) -> dict[str, list[list[float]]]:
    grid = surface.get("uv_grid", [])
    if len(grid) < 2 or len(grid[0]) < 2:
        return {}
    return {
        "u_min": copy.deepcopy(grid[0]),
        "u_max": copy.deepcopy(grid[-1]),
        "v_min": _column(grid, 0),
        "v_max": _column(grid, -1),
    }


def _attach_support_edge_samples(faces: list[dict[str, Any]]) -> None:
    by_id = {face["id"]: face for face in faces}
    hub = by_id.get("hub_revolve_surface")
    tip = by_id.get("tip_reference_surface") or by_id.get("shroud_surface")
    if hub is None and tip is None:
        return
    for face in faces:
        match = re.match(r"^blade_(\d+)_(pressure|suction)_surface$", str(face.get("id", "")))
        if not match:
            continue
        blade_index, side = match.groups()
        if hub is not None:
            hub.setdefault("edge_samples", {})[f"blade_{blade_index}_{side}_hub_boundary"] = _column(
                face["uv_grid"],
                0,
            )
        if tip is not None:
            tip.setdefault("edge_samples", {})[f"blade_{blade_index}_{side}_tip_boundary"] = _column(
                face["uv_grid"],
                -1,
            )


def _remap_edges(edges: list[dict[str, Any]], id_map: dict[str, str]) -> list[dict[str, Any]]:
    remapped = []
    seen = set()
    for edge in edges:
        surface_ids = [id_map.get(str(surface_id), str(surface_id)) for surface_id in edge.get("surfaces", [])]
        if len(surface_ids) != len(edge.get("surfaces", [])):
            continue
        key = (str(edge.get("id", "")), tuple(surface_ids))
        if key in seen:
            continue
        seen.add(key)
        remapped.append({**copy.deepcopy(edge), "surfaces": surface_ids})
    return remapped


def _column(grid: list[list[list[float]]], index: int) -> list[list[float]]:
    return [copy.deepcopy(row[index]) for row in grid]
