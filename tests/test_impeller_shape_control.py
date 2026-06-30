from __future__ import annotations

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_shape_control import normalize_shape_control_space


def test_shape_control_space_exposes_required_target_entities_and_stage_one_locks():
    bundle = load_impeller_dsl_bundle()

    space = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)

    assert space["schema_version"] == "0.2"
    assert space["optimization_stage"] == 1
    assert space["locked_topology"] is True
    assert "hub_meridional_profile" in space["active_policies"]
    assert "blade_tip_meridional_profile" in space["active_policies"]
    assert "leading_edge_boundary" in space["active_policies"]
    assert "trailing_edge_boundary" in space["active_policies"]
    assert "blade_mean_surface" in space["active_policies"]
    assert "blade_thickness_distribution" in space["active_policies"]


def test_shape_control_space_separates_semantic_handles_from_direct_variables():
    bundle = load_impeller_dsl_bundle()

    space = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)

    semantic_ids = {handle["id"] for handle in space["semantic_handles"]}
    variable_ids = {variable["id"] for variable in space["editable_variables"]}

    assert "hub_base_radius" in semantic_ids
    assert "hub_nose_radius" in semantic_ids
    assert "hub_cp_0_r" in variable_ids
    assert "hub_cp_0_z" in variable_ids
    assert space["optimizable_variables"]
    assert all(variable["topology_locked"] for variable in space["editable_variables"])
