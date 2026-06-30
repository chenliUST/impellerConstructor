from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = PROJECT_ROOT / "src" / "part_rule_synthesis" / "ontology" / "impeller" / "v0_4"
DSL_ROOT = (
    PROJECT_ROOT
    / "src"
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_4"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v04_resource_files_exist_and_are_valid_json():
    ontology_files = [
        "slice.json",
        "entities.json",
        "relations.json",
        "validity_contracts.json",
        "loss_schema.json",
    ]
    dsl_files = [
        "schema.json",
        "constructors/open_impeller.json",
        "constructors/closed_impeller.json",
        "presets/radial_open_reference.json",
        "presets/radial_closed_reference.json",
        "shape_controls/default_shape_controls.json",
        "simulation_views/cfd_full_360.json",
        "simulation_views/fea_solid_schema.json",
        "aliases.json",
    ]

    for name in ontology_files:
        assert isinstance(read_json(ONTOLOGY_ROOT / name), dict), name
    for name in dsl_files:
        assert isinstance(read_json(DSL_ROOT / name), dict), name


def test_v04_schema_defines_graph_contract_design_space_and_simulation_views():
    schema = read_json(DSL_ROOT / "schema.json")

    assert schema["dsl_version"] == "0.4"
    assert schema["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert "design_space" in schema["required_sections"]
    assert "surface_graph_contract" in schema["required_sections"]
    assert "feature_graph_contract" in schema["required_sections"]
    assert "simulation_views" in schema["required_sections"]
    assert schema["patch_naming_policy"] == "group_and_instance"


def test_v04_design_space_separates_topology_and_numeric_variables():
    shape_controls = read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")

    assert shape_controls["shape_control_version"] == "0.4"
    assert "topology_variables" in shape_controls["design_space"]
    assert "design_variables" in shape_controls["design_space"]
    assert "hub_profile.control_point_count" in shape_controls["design_space"]["topology_variables"]
    assert "root_fillet.radius_mm" in shape_controls["design_space"]["design_variables"]
    assert shape_controls["campaign_freeze_rule"] == "topology_variables_immutable_inside_campaign"


def test_v04_simulation_views_define_cfd_executable_and_fea_schema_only():
    cfd = read_json(DSL_ROOT / "simulation_views" / "cfd_full_360.json")
    fea = read_json(DSL_ROOT / "simulation_views" / "fea_solid_schema.json")

    assert cfd["view_id"] == "cfd_full_360"
    assert cfd["domain_kind"] == "full_360_wetted_surface"
    assert cfd["status"] == "research_grade_executable"
    assert cfd["patch_naming"] == "group_and_instance"
    assert "mounting_bore" in cfd["feature_suppression"]["suppressed_features"]
    assert fea["view_id"] == "fea_solid"
    assert fea["status"] == "schema_only_v0_4"


def test_v04_constructors_define_feature_graph_and_boundary_guided_blades():
    open_constructor = read_json(DSL_ROOT / "constructors" / "open_impeller.json")
    closed_constructor = read_json(DSL_ROOT / "constructors" / "closed_impeller.json")

    for constructor in [open_constructor, closed_constructor]:
        assert constructor["dsl_version"] == "0.4"
        assert constructor["blade_surface_model"]["kind"] == "boundary_guided_camber_surface_with_thickness"
        assert "leading_edge_round" in constructor["feature_graph"]["blade_transition_features"]
        assert "mounting_bore" in constructor["feature_graph"]["assembly_features"]
        assert "balance_holes" in constructor["feature_graph"]["tuning_features"]

    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is False
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is True
