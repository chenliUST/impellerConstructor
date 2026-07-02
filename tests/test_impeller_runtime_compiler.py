from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from part_rule_synthesis.impeller_dsl_resources import _validate_bundle, load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_load_impeller_dsl_bundle_returns_slice_schema_constructors_presets_and_aliases():
    bundle = load_impeller_dsl_bundle()

    assert bundle.slice["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert bundle.shape_control_schema["default_stage"] == 1
    assert "hub_meridional_profile" in bundle.shape_controls["target_entities"]
    assert bundle.schema["dsl_version"] == "0.2"
    assert "axisymmetric_throughflow_radial_bladed.open" in bundle.constructors
    assert "axisymmetric_throughflow_radial_bladed.closed" in bundle.constructors
    assert "radial_open_reference" in bundle.presets
    assert bundle.aliases["axisymmetric_nurbs_open_throughflow_study"] == "radial_open_reference"


def test_load_impeller_dsl_bundle_v03_coexists_with_v02_resources():
    bundle = load_impeller_dsl_bundle("v0_3")

    assert bundle.slice["ontology_version"] == "0.3"
    assert bundle.schema["dsl_version"] == "0.3"
    assert "axisymmetric_throughflow_radial_bladed.open.v0_3" in bundle.constructors
    assert "axisymmetric_throughflow_radial_bladed.closed.v0_3" in bundle.constructors
    assert "radial_open_reference_v0_3" in bundle.presets
    assert bundle.presets["radial_open_reference_v0_3"]["constructor_id"].endswith(".v0_3")
    assert bundle.shape_controls["shape_control_version"] == "0.3"
    assert "hub_material_solid" in bundle.shape_controls["target_entities"]
    assert "hub_meridional_profile" in bundle.shape_controls["policies"]


def test_load_impeller_dsl_bundle_v04_exposes_design_space_and_simulation_views():
    bundle = load_impeller_dsl_bundle("v0_4")

    assert bundle.slice["ontology_version"] == "0.4"
    assert bundle.schema["dsl_version"] == "0.4"
    assert "axisymmetric_throughflow_radial_bladed.open.v0_4" in bundle.constructors
    assert "radial_open_reference_v0_4" in bundle.presets
    assert bundle.shape_controls["shape_control_version"] == "0.4"
    assert "design_space" in bundle.shape_controls
    assert "simulation_views" in bundle.schema["required_sections"]
    assert set(bundle.simulation_views) == {"cfd_full_360", "fea_solid"}
    assert {
        view_id: view["view_id"] for view_id, view in bundle.simulation_views.items()
    } == {
        "cfd_full_360": "cfd_full_360",
        "fea_solid": "fea_solid",
    }


def test_load_impeller_dsl_bundle_v05_exposes_export_contracts():
    bundle = load_impeller_dsl_bundle("v0_5")

    assert bundle.slice["ontology_version"] == "0.4"
    assert bundle.schema["dsl_version"] == "0.5"
    assert "axisymmetric_throughflow_radial_bladed.open.v0_5" in bundle.constructors
    assert "radial_open_reference_v0_5" in bundle.presets
    assert bundle.shape_controls["shape_control_version"] == "0.5"
    assert "export_contracts" in bundle.schema["required_sections"]
    assert set(bundle.export_contracts) == {"surface_graph_faithful"}
    assert bundle.export_contracts["surface_graph_faithful"]["mode"] == "surface_graph_faithful"
    assert bundle.export_contracts["surface_graph_faithful"]["default_view"] == "cad_review_360"


def test_load_impeller_dsl_bundle_v04_rejects_missing_simulation_view_refs():
    bundle = load_impeller_dsl_bundle("v0_4")
    constructors = deepcopy(bundle.constructors)
    constructor = constructors["axisymmetric_throughflow_radial_bladed.open.v0_4"]
    constructor["simulation_views"]["cfd_full_360"]["view_ref"] = "simulation_views/missing.json"
    broken_bundle = replace(bundle, constructors=constructors)

    with pytest.raises(ValueError, match="simulation view ref"):
        _validate_bundle(broken_bundle)


def test_compile_impeller_runtime_preset_resolves_legacy_alias_and_preserves_api_fields():
    runtime = compile_impeller_runtime_preset("axisymmetric_nurbs_open_throughflow_study")

    assert runtime["version"] == "0.2.0"
    assert runtime["part_family"] == "impeller"
    assert runtime["preset_id"] == "radial_open_reference"
    assert runtime["legacy_preset_id"] == "axisymmetric_nurbs_open_throughflow_study"
    assert runtime["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert runtime["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert runtime["facets"]["flow_topology"] == "radial"
    assert runtime["facets"]["shroud_topology"] == "open"
    assert runtime["shape_control"]["optimization_stage"] == 1
    assert runtime["shape_control"]["locked_topology"] is True
    assert "hub_base_radius" in {handle["id"] for handle in runtime["shape_control"]["semantic_handles"]}
    assert "blade_boundaries" in runtime["dsl_sections"]
    assert "leading_edge_lean_deg" in runtime["parameters"]
    assert "trailing_edge_lean_deg" in runtime["parameters"]


def test_compile_impeller_runtime_preset_v03_exposes_material_domain_controls():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_3")

    assert runtime["version"] == "0.3.0"
    assert runtime["preset_id"] == "radial_open_reference_v0_3"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open.v0_3"
    assert runtime["dsl_sections"]["dsl_version"] == "0.3"
    assert runtime["display_policy"]["hide_surfaces"] == ["blade_tip_support_surface"]
    assert runtime["material_domain"]["hub"]["kind"] == "capped_revolved_solid_with_bore"
    assert "hub_wall_thickness_mm" in runtime["parameters"]
    assert runtime["parameters"]["hub_wall_thickness_mm"]["min"] > 0.0
    assert runtime["shape_control"]["optimization_stage"] == 2
    assert "hub_wall_thickness_mm" in {
        variable["id"] for variable in runtime["shape_control"]["editable_variables"]
    }


def test_compile_impeller_runtime_preset_v04_exposes_graph_contracts():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_4")

    assert runtime["version"] == "0.4.0"
    assert runtime["preset_id"] == "radial_open_reference_v0_4"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open.v0_4"
    assert runtime["dsl_sections"]["dsl_version"] == "0.4"
    assert runtime["shape_control"]["shape_control_version"] == "0.4"
    assert set(runtime["simulation_views"]) == {"cad_review_360", "cfd_full_360", "fea_solid"}
    assert runtime["simulation_views"]["cad_review_360"]["domain_kind"] == "full_360_solid_or_surface"
    assert runtime["simulation_views"]["cfd_full_360"]["domain_kind"] == "full_360_wetted_surface"
    assert runtime["simulation_views"]["fea_solid"]["view_id"] == "fea_solid"
    assert runtime["feature_graph"]["assembly_features"]["mounting_bore"]["kind"] == "axisymmetric_subtractive_cylinder"
    assert {
        "simulation_views.cad_review_360",
        "simulation_views.cfd_full_360",
        "simulation_views.fea_solid",
    } <= set(runtime["selected_rules"])


def test_compile_impeller_runtime_preset_v05_exposes_surface_graph_export_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_5")

    assert runtime["version"] == "0.5.0"
    assert runtime["preset_id"] == "radial_open_reference_v0_5"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open.v0_5"
    assert runtime["dsl_sections"]["dsl_version"] == "0.5"
    assert runtime["export_contract"]["mode"] == "surface_graph_faithful"
    assert runtime["export_contract"]["default_view"] == "cad_review_360"
    assert runtime["export_contract"]["step_exactness"] == "surface_graph_mesh_step"
    assert "export_contract.surface_graph_faithful" in runtime["selected_rules"]


def test_compile_impeller_runtime_preset_rejects_unknown_preset():
    with pytest.raises(ValueError, match="unknown impeller preset"):
        compile_impeller_runtime_preset("not_a_preset")
