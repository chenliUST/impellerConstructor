from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_dsl_resources import ImpellerDslBundle, load_impeller_dsl_bundle
from part_rule_synthesis.impeller_shape_control import normalize_shape_control_space


IMPELLER_DSL_VERSIONS = ("v0_2", "v0_3", "v0_4", "v0_5")

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
    facets = {**constructor["classification"], **(facet_overrides or {})}
    _validate_facets(bundle, facets)
    shape_control = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)
    shape_control["shape_control_version"] = bundle.shape_controls["shape_control_version"]
    simulation_views = _simulation_views_for_constructor(bundle, constructor)
    export_contract = _export_contract_for_constructor(bundle, constructor)
    dsl_version = str(bundle.schema["dsl_version"])
    return {
        "version": f"{dsl_version}.0",
        "part_family": "impeller",
        "preset_id": resolved_preset_id,
        "legacy_preset_id": requested_preset_id if requested_preset_id != resolved_preset_id else None,
        "ontology_slice": bundle.slice["slice_id"],
        "constructor_family": bundle.slice["constructor_family"],
        "constructor_id": constructor["constructor_id"],
        "facets": facets,
        "parameters": _parameter_specs(preset["parameter_values"]),
        "features": _features_for_constructor(constructor),
        "constraints": _constraints_for_constructor(constructor),
        "selected_rules": _selected_rules(bundle, constructor, simulation_views),
        "rule_implications": _rule_implications(constructor),
        "unsupported_or_inferred_regions": _inferred_regions(constructor),
        "dsl_sections": constructor,
        "display_policy": constructor.get("display_policy", {}),
        "material_domain": constructor.get("material_domain", {}),
        "solid_features": constructor.get("solid_features", {}),
        "feature_graph": constructor.get("feature_graph", {}),
        "simulation_views": simulation_views,
        "export_contract": export_contract,
        "shape_control": shape_control,
        "validity_contracts": bundle.validity_contracts,
        "loss_schema": bundle.loss_schema,
        "source_refs": preset.get("source_refs", []),
    }


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
    if bundle.schema["dsl_version"] in {"0.4", "0.5"}:
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
