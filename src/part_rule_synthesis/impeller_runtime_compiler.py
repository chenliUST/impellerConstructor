from __future__ import annotations

import math
from typing import Any

from part_rule_synthesis.impeller_dsl_resources import ImpellerDslBundle, load_impeller_dsl_bundle
from part_rule_synthesis.impeller_shape_control import normalize_shape_control_space
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.impeller_v11_2_canonical import (
    MATH_PARAMETERIZATION as V11_2_MATH_PARAMETERIZATION,
    canonical_nurbs_from_v11_defaults,
)
from part_rule_synthesis.impeller_v11_constants import SOURCE_KERNEL as V11_SOURCE_KERNEL


IMPELLER_DSL_VERSIONS = (
    "v0_2",
    "v0_3",
    "v0_4",
    "v0_5",
    "v0_6",
    "v0_7",
    "v0_8",
    "v0_9",
    "v0_91",
    "v1_0",
    "v1_1",
)

IMPELLER_PARAMETER_LIMITS: dict[str, dict[str, float]] = {
    "blade_count": {"min": 2, "max": 64},
    "inlet_radius_mm": {"min": 0.1, "max": 5000.0},
    "exit_radius_mm": {"min": 0.1, "max": 10000.0},
    "inlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
    "outlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
    "hub_curve_height_mm": {"min": 0.0, "max": 5000.0},
    "mounting_bore_radius_mm": {"min": 0.1, "max": 3000.0},
    "blade_wrap_deg": {"min": -720.0, "max": 720.0},
    "blade_lean_deg": {"min": -180.0, "max": 180.0},
    "leading_edge_lean_deg": {"min": -180.0, "max": 180.0},
    "trailing_edge_lean_deg": {"min": -180.0, "max": 180.0},
    "leading_edge_sweep_mm": {"min": -5000.0, "max": 5000.0},
    "trailing_edge_sweep_mm": {"min": -5000.0, "max": 5000.0},
    "inlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
    "outlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
    "blade_thickness_mm": {"min": 0.01, "max": 1000.0},
    "root_fillet_radius_mm": {"min": 0.0, "max": 1000.0},
    "leading_edge_radius_mm": {"min": 0.0, "max": 200.0},
    "trailing_edge_radius_mm": {"min": 0.0, "max": 200.0},
    "tip_edge_radius_mm": {"min": 0.0, "max": 200.0},
    "hub_wall_thickness_mm": {"min": 0.001, "max": 120.0},
    "hub_bottom_thickness_mm": {"min": 0.001, "max": 160.0},
    "hub_top_cap_thickness_mm": {"min": 0.001, "max": 80.0},
    "hub_chamfer_radius_mm": {"min": 0.0, "max": 30.0},
    "hood_wall_thickness_mm": {"min": 0.001, "max": 80.0},
    "hood_chamfer_radius_mm": {"min": 0.0, "max": 30.0},
}


def compile_impeller_runtime_preset(
    preset_id: str | None = None,
    facet_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    requested_preset_id = preset_id or "radial_open_reference"
    bundle, resolved_preset_id = _bundle_for_preset(requested_preset_id)
    preset = bundle.presets[resolved_preset_id]
    constructor = bundle.constructors[preset["constructor_id"]]
    parameters = preset["parameter_values"]
    facets = {**constructor["classification"], **(facet_overrides or {})}
    _validate_facets(bundle, facets)
    shape_control = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)
    shape_control["shape_control_version"] = bundle.shape_controls["shape_control_version"]
    simulation_views = _simulation_views_for_constructor(bundle, constructor)
    export_contract = _export_contract_for_constructor(bundle, constructor)
    dsl_version = str(bundle.schema["dsl_version"])
    runtime = {
        "version": f"{dsl_version}.0",
        "part_family": "impeller",
        "preset_id": resolved_preset_id,
        "legacy_preset_id": requested_preset_id if requested_preset_id != resolved_preset_id else None,
        "ontology_slice": bundle.slice["slice_id"],
        "constructor_family": bundle.slice["constructor_family"],
        "constructor_id": constructor["constructor_id"],
        "facets": facets,
        "parameters": _parameter_specs(parameters),
        "features": _features_for_constructor(constructor),
        "constraints": _constraints_for_constructor(constructor),
        "selected_rules": _selected_rules(bundle, constructor, simulation_views),
        "rule_implications": _rule_implications(constructor),
        "unsupported_or_inferred_regions": _inferred_regions(constructor),
        "dsl_sections": constructor,
        "display_policy": constructor.get("display_policy", {}),
        "material_domain": constructor.get("material_domain", {}),
        "solid_features": constructor.get("solid_features", {}),
        "profile_defaults": constructor.get("profile_defaults", {}),
        "feature_graph": constructor.get("feature_graph", {}),
        "simulation_views": simulation_views,
        "export_contract": export_contract,
        "shape_control": shape_control,
        "validity_contracts": bundle.validity_contracts,
        "loss_schema": bundle.loss_schema,
        "source_refs": preset.get("source_refs", []),
    }
    if dsl_version in {"0.7", "0.8", "0.9", "0.91", "1.0", "1.1"}:
        edge_families = constructor.get("edge_families", {})
        runtime["edge_families"] = edge_families
        runtime["transition_policy_defaults"] = resolve_transition_policies(edge_families, parameters)
    if dsl_version == "0.8":
        runtime["transition_geometry_status"] = preset.get(
            "transition_geometry_status",
            "resolved_trimmed_surface_graph",
        )
        runtime["mesh_strategy"] = export_contract.get("mesh_strategy")
    if dsl_version == "0.9":
        runtime["geometry_version"] = preset.get("geometry_version", "0.9")
        runtime["transition_geometry_status"] = preset.get(
            "transition_geometry_status",
            "validated_transition_surface_graph",
        )
        runtime["mesh_strategy"] = export_contract.get("mesh_strategy")
        runtime["kernel_capability_matrix_id"] = "impeller_v0_9_kernel_capabilities"
        runtime["golden_case_registry_id"] = "impeller_v0_9_golden_cases"
    if dsl_version == "0.91":
        runtime["dsl_version"] = "0.91"
        runtime["geometry_version"] = preset.get("geometry_version", "0.91")
        runtime["transition_geometry_status"] = preset.get(
            "transition_geometry_status",
            "topology_first_validated_transition_graph",
        )
        runtime["mesh_strategy"] = export_contract.get("mesh_strategy")
        runtime["kernel_capability_matrix_id"] = "impeller_v0_91_kernel_capabilities"
        runtime["golden_case_registry_id"] = "impeller_v0_91_golden_cases"
    if dsl_version == "1.0":
        runtime["dsl_version"] = "1.0"
        runtime["geometry_version"] = preset.get("geometry_version", "1.0")
        if facets.get("shroud_topology") == "open":
            runtime.update(_v10_3_runtime_defaults(preset, parameters, constructor, export_contract))
            if preset.get("geometry_patch_version") == "1.0.4":
                runtime["geometry_patch_version"] = "1.0.4"
                runtime["transition_geometry_status"] = (
                    "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
                )
                runtime["mesh_strategy"] = "v1_0_4_surface_uv_and_review_quad_mesh"
                runtime["kernel_capability_matrix_id"] = "impeller_v1_0_4_kernel_capabilities"
                runtime["golden_case_registry_id"] = "impeller_v1_0_4_golden_cases"
                runtime["v1_0_4_preset_contract"] = _v10_4_preset_contract(
                    parameters,
                    runtime["resolved_section_loop_defaults"],
                )
        else:
            runtime["transition_geometry_status"] = preset.get(
                "transition_geometry_status",
                "topology_first_closed_nurbs_impeller_surface_graph",
            )
            runtime["mesh_strategy"] = export_contract.get("mesh_strategy")
            runtime["kernel_capability_matrix_id"] = "impeller_v1_0_kernel_capabilities"
            runtime["golden_case_registry_id"] = "impeller_v1_0_golden_cases"
            attachment_defaults = _v10_2_attachment_defaults(parameters, constructor)
            runtime["geometry_patch_version"] = "1.0.2"
            runtime["continuous_blade_attachment_status"] = "configured"
            runtime["resolved_attachment_defaults"] = attachment_defaults
            runtime["preset_feasibility_status"] = attachment_defaults["preset_feasibility_status"]
            runtime["preset_default_violation_count"] = attachment_defaults["preset_default_violation_count"]
            runtime["preset_feasibility_constraints"] = _v10_2_feasibility_constraints(constructor)
            runtime["preset_adjusted_defaults"] = {}
    if dsl_version == "1.1":
        runtime["dsl_version"] = "1.1"
        runtime.update(_v11_runtime_defaults(preset, parameters, export_contract))
    return runtime


def compiled_impeller_presets() -> dict[str, dict[str, Any]]:
    result = {}
    for bundle in _available_bundles():
        for preset_id, preset in bundle.presets.items():
            constructor = bundle.constructors[preset["constructor_id"]]
            result[preset_id] = {
                "name": preset["display_name"],
                "summary": preset["summary"],
                "facets": constructor["classification"],
                "parameters": preset["parameter_values"],
                "constructor_id": preset["constructor_id"],
                "dsl_version": bundle.schema["dsl_version"],
            }
    return result


def impeller_json_preset_ids() -> set[str]:
    ids: set[str] = set()
    for bundle in _available_bundles():
        ids.update(bundle.presets)
        ids.update(bundle.aliases)
    return ids


def _available_bundles() -> list[ImpellerDslBundle]:
    return [load_impeller_dsl_bundle(version) for version in IMPELLER_DSL_VERSIONS]


def _bundle_for_preset(requested_preset_id: str) -> tuple[ImpellerDslBundle, str]:
    for bundle in _available_bundles():
        resolved_preset_id = bundle.aliases.get(requested_preset_id, requested_preset_id)
        if resolved_preset_id in bundle.presets:
            return bundle, resolved_preset_id
    raise ValueError(f"unknown impeller preset: {requested_preset_id}")


def _validate_facets(bundle: Any, facets: dict[str, str]) -> None:
    in_scope = bundle.slice["in_scope"]
    axis_map = {
        "part_family": "part_family",
        "flow_topology": "flow_topology",
        "passage_topology": "passage_topology",
        "shroud_topology": "shroud_topology",
        "entry_topology": "entry_topology",
        "suction_topology": "suction_topology",
        "blade_exit_geometry": "blade_exit_geometry",
        "blade_population": "blade_population",
        "working_domain": "working_domain",
    }
    for facet_name, scope_key in axis_map.items():
        if facet_name not in facets:
            raise ValueError(f"missing impeller facet: {facet_name}")
        if facets[facet_name] not in in_scope[scope_key]:
            raise ValueError(f"invalid facet {facet_name}: {facets[facet_name]}")


def _parameter_specs(values: dict[str, float | int]) -> dict[str, dict[str, float]]:
    specs = {}
    for name, default in values.items():
        limits = IMPELLER_PARAMETER_LIMITS[name]
        specs[name] = {"default": default, "min": limits["min"], "max": limits["max"]}
    return specs


def _v10_3_runtime_defaults(
    preset: dict[str, Any],
    parameters: dict[str, Any],
    constructor: dict[str, Any],
    export_contract: dict[str, Any],
) -> dict[str, Any]:
    defaults = preset.get("v1_0_3_section_loop_defaults")
    if not isinstance(defaults, dict):
        raise ValueError("missing V1.0.3 section loop defaults for open impeller preset")
    return {
        "resolved_parameter_defaults": dict(parameters),
        "geometry_patch_version": "1.0.3",
        "transition_geometry_status": preset.get(
            "transition_geometry_status",
            "topology_first_section_loop_blade_root_blend_surface_graph",
        ),
        "mesh_strategy": export_contract.get("mesh_strategy", "section_loop_shared_edge_review_grade_quad_mesh"),
        "kernel_capability_matrix_id": "impeller_v1_0_3_kernel_capabilities",
        "golden_case_registry_id": "impeller_v1_0_3_golden_cases",
        "resolved_section_loop_defaults": dict(defaults),
        "v1_0_3_preset_feasibility": _v10_3_preset_feasibility(parameters, defaults, constructor),
    }


def _v11_runtime_defaults(
    preset: dict[str, Any],
    parameters: dict[str, Any],
    export_contract: dict[str, Any],
) -> dict[str, Any]:
    defaults = preset.get("blade_to_blade_loop_family_defaults")
    if not isinstance(defaults, dict):
        raise ValueError("missing V1.1 blade-to-blade loop-family defaults")
    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)
    return {
        "resolved_parameter_defaults": dict(parameters),
        "geometry_version": "1.1",
        "geometry_patch_version": preset.get("geometry_patch_version", "1.1.2"),
        "math_parameterization": preset.get("math_parameterization", V11_2_MATH_PARAMETERIZATION),
        "source_kernel": preset.get("source_kernel", V11_SOURCE_KERNEL),
        "transition_geometry_status": preset.get(
            "transition_geometry_status",
            "topology_first_blade_to_blade_5_loop_surface_family_graph",
        ),
        "mesh_strategy": preset.get(
            "mesh_strategy",
            export_contract.get("mesh_strategy", "v1_1_1_all_surface_uv_grid_mesh"),
        ),
        "kernel_capability_matrix_id": "impeller_v1_1_kernel_capabilities",
        "golden_case_registry_id": "impeller_v1_1_golden_cases",
        "canonical_input_source": canonical["canonical_input_source"],
        "canonical_nurbs_parameterization": canonical,
        "resolved_blade_to_blade_loop_family_defaults": dict(defaults),
        "editable_parameters": list(preset.get("editable_parameters", [])),
    }


def _v10_3_preset_feasibility(
    parameters: dict[str, Any],
    defaults: dict[str, Any],
    constructor: dict[str, Any],
) -> dict[str, Any]:
    inlet_radius = float(_parameter_default(parameters, "inlet_radius_mm"))
    exit_radius = float(_parameter_default(parameters, "exit_radius_mm"))
    bore_radius = float(_parameter_default(parameters, "mounting_bore_radius_mm"))
    outlet_height = float(_parameter_default(parameters, "outlet_blade_height_mm"))
    blade_thickness = float(_parameter_default(parameters, "blade_thickness_mm"))
    hub_wall = float(_parameter_default(parameters, "hub_wall_thickness_mm"))
    root_width = float(defaults["root_attachment_width_mm"])
    root_lift = float(defaults["root_attachment_lift_mm"])
    tip_dome_height = float(defaults["tip_dome_height_mm"])

    leading_edge_margin = round(inlet_radius - bore_radius - root_width, 6)
    trailing_edge_margin = round(exit_radius - inlet_radius - root_width, 6)
    root_inside_hub = hub_wall >= root_lift + 0.25 * blade_thickness
    tip_inside_support = (
        constructor.get("support_surfaces", {})
        .get("blade_tip_support_surface", {})
        .get("material")
        is False
        and tip_dome_height <= outlet_height
    )
    status = (
        "PASS"
        if leading_edge_margin > 0.0
        and trailing_edge_margin > 0.0
        and root_inside_hub
        and tip_inside_support
        else "FAIL"
    )
    return {
        "status": status,
        "leading_edge_support_margin_mm": leading_edge_margin,
        "trailing_edge_support_margin_mm": trailing_edge_margin,
        "root_footprint_inside_hub_domain": root_inside_hub,
        "tip_loop_inside_tip_support_domain": tip_inside_support,
    }


def _v10_4_preset_contract(parameters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    thickness = float(
        defaults.get(
            "average_blade_thickness_mm",
            _parameter_default(parameters, "blade_thickness_mm"),
        )
    )
    return {
        "root_width_rule": "0.50 * average_blade_thickness_mm",
        "root_lift_rule": "0.50 * average_blade_thickness_mm",
        "tip_height_rule": "0.50 * average_blade_thickness_mm",
        "expected_root_width_mm": round(0.5 * thickness, 6),
        "expected_root_lift_mm": round(0.5 * thickness, 6),
        "expected_tip_dome_height_mm": round(0.5 * thickness, 6),
        "root_width_variation_limit_fraction": 0.20,
        "root_lift_variation_limit_fraction": 0.20,
        "tip_area_ratio_limit": 1.15,
        "blade_hub_angle_range_deg": [60.0, 120.0],
    }


def _v10_2_attachment_defaults(
    parameters: dict[str, Any],
    constructor: dict[str, Any],
) -> dict[str, Any]:
    defaults = constructor.get("v1_0_2_attachment_defaults", {})
    rule_strings = _v10_2_attachment_rule_strings(defaults)
    blade_count = int(_parameter_default(parameters, "blade_count"))
    blade_thickness = float(_parameter_default(parameters, "blade_thickness_mm"))
    root_radius = float(_parameter_default(parameters, "root_fillet_radius_mm"))
    tip_radius = float(_parameter_default(parameters, "tip_edge_radius_mm"))
    hub_wall = float(_parameter_default(parameters, "hub_wall_thickness_mm"))
    hub_bottom = float(_parameter_default(parameters, "hub_bottom_thickness_mm"))
    hood_wall = float(_parameter_default(parameters, "hood_wall_thickness_mm", 0.0))
    inlet_radius = float(_parameter_default(parameters, "inlet_radius_mm"))

    root_width = _v10_2_rule_value(
        rule_strings["root_attachment_width_rule"],
        "max(1.20 * root_fillet_radius_mm, 0.55 * blade_thickness_mm, 16.0)",
        max(1.20 * root_radius, 0.55 * blade_thickness, 16.0),
    )
    root_lift = _v10_2_rule_value(
        rule_strings["root_attachment_lift_rule"],
        "max(0.18 * root_fillet_radius_mm, 0.12 * blade_thickness_mm, 4.0)",
        max(0.18 * root_radius, 0.12 * blade_thickness, 4.0),
    )
    tip_width = _v10_2_rule_value(
        rule_strings["tip_attachment_width_rule"],
        "max(1.00 * tip_edge_radius_mm, 0.45 * blade_thickness_mm, 12.0)",
        max(1.00 * tip_radius, 0.45 * blade_thickness, 12.0),
    )
    tip_lift = _v10_2_rule_value(
        rule_strings["tip_attachment_lift_rule"],
        "max(0.16 * tip_edge_radius_mm, 0.10 * blade_thickness_mm, 3.0)",
        max(0.16 * tip_radius, 0.10 * blade_thickness, 3.0),
    )
    pitch = 2.0 * math.pi * inlet_radius / blade_count if blade_count >= 2 else 0.0
    minimum_pitch = 1.15 * (blade_thickness + 2.0 * root_width)
    has_closed_shroud_material = _v10_2_has_closed_shroud_material(constructor)

    margins = {
        "blade_count_minimum_margin": blade_count - 2,
        "minimum_pitch_margin_mm": round(pitch - minimum_pitch, 6),
        "hub_material_margin_mm": round(hub_wall - (root_lift + 0.25 * blade_thickness), 6),
        "hub_bottom_margin_mm": round(hub_bottom - max(0.30 * root_width, 8.0), 6),
    }
    not_applicable_constraints = {}
    if has_closed_shroud_material:
        margins["shroud_material_margin_mm"] = round(hood_wall - (tip_lift + 0.15 * blade_thickness), 6)
    else:
        not_applicable_constraints[
            "closed_shroud_material_supports_tip_attachment_lift"
        ] = "open_impeller_has_no_front_shroud_material"

    violation_reasons = _v10_2_violation_reasons(margins)
    violation_count = sum(1 for value in margins.values() if value < 0.0)
    return {
        "edge_short_direction_sample_count": _v10_2_sample_count(defaults, "edge_short_direction_sample_count"),
        "attachment_short_direction_sample_count": _v10_2_sample_count(
            defaults,
            "attachment_short_direction_sample_count",
        ),
        "source_rule_strings": rule_strings,
        "resolved_blade_count": blade_count,
        "resolved_blade_thickness_mm": round(blade_thickness, 6),
        "resolved_root_attachment_width_mm": round(root_width, 6),
        "resolved_root_attachment_lift_mm": round(root_lift, 6),
        "resolved_tip_attachment_width_mm": round(tip_width, 6),
        "resolved_tip_attachment_lift_mm": round(tip_lift, 6),
        "resolved_support_domain_margins": margins,
        "not_applicable_constraints": not_applicable_constraints,
        "preset_default_violation_reasons": violation_reasons,
        "preset_default_violation_count": violation_count,
        "preset_feasibility_status": "PASS" if violation_count == 0 else "FAIL",
    }


def _v10_2_feasibility_constraints(constructor: dict[str, Any]) -> list[str]:
    constraints = [
        "blade_pitch_supports_root_attachment",
        "hub_material_supports_root_attachment_lift",
        "hub_bottom_supports_root_attachment_width",
    ]
    if _v10_2_has_closed_shroud_material(constructor):
        constraints.append("closed_shroud_material_supports_tip_attachment_lift")
    return constraints


def _v10_2_has_closed_shroud_material(constructor: dict[str, Any]) -> bool:
    support = constructor.get("support_surfaces", {}).get("blade_tip_support_surface", {})
    front_shroud = constructor.get("material_domain", {}).get("front_shroud", {})
    return (
        constructor.get("classification", {}).get("shroud_topology") == "closed"
        and bool(support.get("material"))
        and front_shroud.get("kind") not in {None, "none"}
    )


def _v10_2_attachment_rule_strings(defaults: dict[str, Any]) -> dict[str, str]:
    return {
        "root_attachment_width_rule": _v10_2_required_rule(
            defaults,
            "root_attachment_width_rule",
            "max(1.20 * root_fillet_radius_mm, 0.55 * blade_thickness_mm, 16.0)",
        ),
        "root_attachment_lift_rule": _v10_2_required_rule(
            defaults,
            "root_attachment_lift_rule",
            "max(0.18 * root_fillet_radius_mm, 0.12 * blade_thickness_mm, 4.0)",
        ),
        "tip_attachment_width_rule": _v10_2_required_rule(
            defaults,
            "tip_attachment_width_rule",
            "max(1.00 * tip_edge_radius_mm, 0.45 * blade_thickness_mm, 12.0)",
        ),
        "tip_attachment_lift_rule": _v10_2_required_rule(
            defaults,
            "tip_attachment_lift_rule",
            "max(0.16 * tip_edge_radius_mm, 0.10 * blade_thickness_mm, 3.0)",
        ),
    }


def _v10_2_required_rule(defaults: dict[str, Any], key: str, expected: str) -> str:
    rule = defaults.get(key)
    if rule != expected:
        raise ValueError(f"unsupported V1.0.2 attachment rule {key}: {rule!r}")
    return rule


def _v10_2_rule_value(rule: str, expected_rule: str, value: float) -> float:
    if rule != expected_rule:
        raise ValueError(f"unsupported V1.0.2 attachment rule: {rule!r}")
    return value


def _v10_2_sample_count(defaults: dict[str, Any], key: str) -> int:
    value = defaults.get(key)
    if not isinstance(value, int) or value < 2:
        raise ValueError(f"invalid V1.0.2 attachment sample count {key}: {value!r}")
    return value


def _v10_2_violation_reasons(margins: dict[str, float]) -> list[str]:
    reason_by_margin = {
        "blade_count_minimum_margin": "blade_count_below_minimum_two",
        "minimum_pitch_margin_mm": "blade_pitch_below_root_attachment_width",
        "hub_material_margin_mm": "hub_material_below_root_attachment_lift",
        "hub_bottom_margin_mm": "hub_bottom_below_root_attachment_width",
        "shroud_material_margin_mm": "closed_shroud_material_below_tip_attachment_lift",
    }
    return [reason_by_margin[key] for key, value in margins.items() if value < 0.0]


def _parameter_default(parameters: dict[str, Any], name: str, fallback: float | int | None = None) -> Any:
    value = parameters.get(name, fallback)
    if isinstance(value, dict) and "default" in value:
        return value["default"]
    return value


def _features_for_constructor(constructor: dict[str, Any]) -> list[str]:
    features = [
        "hub_material_solid",
        "hub_support_surface",
        "blade_tip_support_surface",
        "blade_root_boundary",
        "blade_tip_boundary",
        "leading_edge_boundary",
        "trailing_edge_boundary",
        "pressure_surface",
        "suction_surface",
        "surface_graph",
    ]
    if constructor["support_surfaces"]["blade_tip_support_surface"]["material"]:
        features.append("front_shroud_material_solid")
    return features


def _constraints_for_constructor(constructor: dict[str, Any]) -> list[str]:
    constraints = [
        "conforms_to(blade_root_boundary, hub_support_surface)",
        "conforms_to(blade_tip_boundary, blade_tip_support_surface)",
        "blade_has_four_primary_boundaries",
    ]
    if constructor["support_surfaces"]["blade_tip_support_surface"]["material"]:
        constraints.append("closed_impeller_has_front_shroud_material")
    else:
        constraints.append("open_impeller_has_no_front_shroud_material")
    return constraints


def _simulation_views_for_constructor(
    bundle: ImpellerDslBundle,
    constructor: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    resolved = {}
    for view_id, view in constructor.get("simulation_views", {}).items():
        view_ref = view.get("view_ref")
        if view_ref is None:
            resolved[view_id] = view
            continue
        resolved_view_id = bundle.simulation_view_refs.get(view_ref, view_id)
        resolved[view_id] = bundle.simulation_views[resolved_view_id]
    return resolved


def _export_contract_for_constructor(
    bundle: ImpellerDslBundle,
    constructor: dict[str, Any],
) -> dict[str, Any]:
    contracts = constructor.get("export_contracts", {})
    if not contracts:
        return {}
    contract = contracts.get("surface_graph_faithful") or next(iter(contracts.values()))
    contract_ref = contract.get("contract_ref")
    if contract_ref is None:
        return contract
    contract_id = bundle.export_contract_refs[contract_ref]
    return bundle.export_contracts[contract_id]


def _selected_rules(
    bundle: Any,
    constructor: dict[str, Any],
    simulation_views: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    if bundle.schema["dsl_version"] in {"0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "0.91", "1.0", "1.1"}:
        view_ids = simulation_views or constructor.get("simulation_views", {})
        export_contract_ids = constructor.get("export_contracts", {})
        return [
            f"ontology_slice.{bundle.slice['slice_id']}",
            f"constructor_family.{bundle.slice['constructor_family']}",
            f"constructor.{constructor['constructor_id']}",
            "design_space.campaign_freeze_rule",
            "surface_graph_contract.named_surfaces_required",
            "feature_graph_contract.features_are_first_class_nodes",
            *(f"simulation_views.{view_id}" for view_id in view_ids),
            *(f"export_contract.{contract_id}" for contract_id in export_contract_ids),
        ]
    return [
        f"ontology_slice.{bundle.slice['slice_id']}",
        f"constructor_family.{bundle.slice['constructor_family']}",
        f"constructor.{constructor['constructor_id']}",
        "blade_boundaries.four_primary_boundaries_required",
        "support_surfaces.blade_tip_support_surface_role_disambiguated",
        "shape_control.stage_one_locked_topology",
    ]


def _rule_implications(constructor: dict[str, Any]) -> dict[str, str]:
    material = constructor["support_surfaces"]["blade_tip_support_surface"]["material"]
    return {
        "constructor_family": "uses axisymmetric hub and blade-tip support surfaces",
        "blade_boundaries": "root, tip, leading edge, and trailing edge are explicit DSL objects",
        "blade_tip_support_surface": "material front shroud" if material else "reference-only open tip support",
        "shape_control": "NURBS degree, control-point count, knot policy, and weights are locked in stage 1",
    }


def _inferred_regions(constructor: dict[str, Any]) -> list[str]:
    regions = ["strict_cad_brep_export_deferred"]
    if constructor["blade_edges"]["root"]["kind"] == "fillet_patch":
        regions.append("root_fillet_geometry_research_grade")
    return regions
