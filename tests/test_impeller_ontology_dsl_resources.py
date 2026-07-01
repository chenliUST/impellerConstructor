from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = PROJECT_ROOT / "src" / "part_rule_synthesis" / "ontology" / "impeller" / "v0_2"
DSL_ROOT = (
    PROJECT_ROOT
    / "src"
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_2"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_impeller_ontology_slice_files_exist_and_are_valid_json():
    for name in [
        "slice.json",
        "entities.json",
        "relations.json",
        "shape_control_schema.json",
        "validity_contracts.json",
        "loss_schema.json",
    ]:
        data = _read_json(ONTOLOGY_ROOT / name)
        assert isinstance(data, dict)


def test_impeller_slice_names_axisymmetric_throughflow_radial_bladed_constructor():
    slice_data = _read_json(ONTOLOGY_ROOT / "slice.json")

    assert slice_data["slice_id"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert slice_data["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert slice_data["in_scope"]["flow_topology"] == ["radial"]
    assert "mixed_flow" in slice_data["out_of_scope"]
    assert "recessed_vortex" in slice_data["out_of_scope"]


def test_impeller_entities_include_tip_support_four_boundaries_and_shape_control():
    entities = _read_json(ONTOLOGY_ROOT / "entities.json")

    assert "blade_tip_support_surface" in entities["support_surfaces"]
    assert "shape_control_policy" in entities["shape_control"]
    assert "semantic_handle" in entities["shape_control"]
    assert "blade_root_boundary" in entities["blade"]
    assert "blade_tip_boundary" in entities["blade"]
    assert "leading_edge_boundary" in entities["blade"]
    assert "trailing_edge_boundary" in entities["blade"]


def test_impeller_shape_control_schema_defines_staged_nurbs_optimization():
    schema = _read_json(ONTOLOGY_ROOT / "shape_control_schema.json")

    assert schema["shape_control_schema_version"] == "0.2"
    assert schema["default_stage"] == 1
    assert [stage["stage"] for stage in schema["optimization_stages"]] == [1, 2, 3, 4]
    assert schema["optimization_stages"][0]["degree"] == "locked"
    assert schema["optimization_stages"][0]["control_point_count"] == "locked"
    assert schema["optimization_stages"][0]["knot_vector"] == "locked"
    assert schema["optimization_stages"][0]["control_point_coordinates"] == "editable_optimizable"


def test_impeller_validity_contracts_cover_geometry_topology_warnings_and_shape_control():
    contracts = _read_json(ONTOLOGY_ROOT / "validity_contracts.json")

    assert "blade_root_boundary_conforms_to_hub_support_surface" in contracts["geometry_contracts"]
    assert "blade_tip_boundary_conforms_to_blade_tip_support_surface" in contracts["geometry_contracts"]
    assert "control_net_dimension_matches_degree" in contracts["geometry_contracts"]
    assert "nurbs_knot_vector_non_decreasing" in contracts["geometry_contracts"]
    assert "blade_has_four_primary_boundaries" in contracts["topology_contracts"]
    assert "wrap_angle_plausibility" in contracts["engineering_warnings"]


def test_impeller_dsl_schema_and_constructors_encode_open_closed_tip_support_roles():
    schema = _read_json(DSL_ROOT / "schema.json")
    open_constructor = _read_json(DSL_ROOT / "constructors" / "open_impeller.json")
    closed_constructor = _read_json(DSL_ROOT / "constructors" / "closed_impeller.json")
    shape_controls = _read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")

    assert schema["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert "blade_boundaries" in schema["required_sections"]
    assert "shape_control" in schema["required_sections"]
    assert open_constructor["shape_control"]["shape_control_ref"] == "shape_controls/default_shape_controls.json"
    assert closed_constructor["shape_control"]["shape_control_ref"] == "shape_controls/default_shape_controls.json"
    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["role"] == "reference_only"
    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is False
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["role"] == "front_shroud_inner_surface"
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is True
    assert "hub_meridional_profile" in shape_controls["target_entities"]
    assert shape_controls["policies"]["hub_meridional_profile"]["representation_topology"]["knot_policy"] == (
        "clamped_uniform"
    )


def test_impeller_presets_bind_to_new_constructors_and_alias_legacy_ids():
    aliases = _read_json(DSL_ROOT / "aliases.json")
    open_preset = _read_json(DSL_ROOT / "presets" / "radial_open_reference.json")
    closed_preset = _read_json(DSL_ROOT / "presets" / "radial_closed_reference.json")

    assert open_preset["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert closed_preset["constructor_id"] == "axisymmetric_throughflow_radial_bladed.closed"
    assert aliases["legacy_preset_aliases"]["axisymmetric_nurbs_open_throughflow_study"] == "radial_open_reference"
    assert aliases["legacy_preset_aliases"]["axisymmetric_nurbs_closed_throughflow_study"] == "radial_closed_reference"
