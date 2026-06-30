from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
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


def test_compile_impeller_runtime_preset_rejects_unknown_preset():
    with pytest.raises(ValueError, match="unknown impeller preset"):
        compile_impeller_runtime_preset("not_a_preset")
