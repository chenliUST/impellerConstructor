from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_2_historical_fixture import historical_v10_2_runtime
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import _v10_2_attachment_defaults
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


V10_2_PRESET_IDS = [
    "radial_closed_reference_v1_0",
]
V10_2_TRANSITION_STATUSES = {
    "topology_first_continuous_blade_attachment_surface_graph",
    "topology_first_closed_nurbs_impeller_surface_graph",
}
G2_FILLET_POLICIES = [
    "blade_leading_edge.default",
    "blade_trailing_edge.default",
    "blade_root_to_hub.default",
    "blade_tip_or_shroud.default",
]


def test_v10_presets_compile_with_v10_2_resource_contract():
    for preset_id in V10_2_PRESET_IDS:
        runtime = compile_impeller_runtime_preset(preset_id)

        assert runtime["geometry_version"] == "1.0"
        assert runtime["geometry_patch_version"] == "1.0.2"
        assert runtime["continuous_blade_attachment_status"] == "configured"
        assert runtime["preset_feasibility_status"] == "PASS"
        assert runtime["preset_default_violation_count"] == 0
        assert runtime["transition_geometry_status"] in V10_2_TRANSITION_STATUSES


def test_v10_open_preset_routes_to_v10_3_surface_graph_not_v10_2_attachment():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.4"
    assert "resolved_attachment_defaults" not in runtime
    assert "continuous_blade_attachment_status" not in runtime
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert runtime["export_contract"]["implementation_status"] == "surface_graph_builder_available"
    assert runtime["export_contract"]["current_geometry_generation_status"] == "PASS"


def test_historical_v10_2_open_fixture_does_not_carry_v10_3_export_contract():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    production_runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_patch_version"] == "1.0.2"
    assert runtime["transition_geometry_status"] == "topology_first_closed_nurbs_impeller_surface_graph"
    assert runtime["mesh_strategy"] != "section_loop_shared_edge_review_grade_quad_mesh"
    assert runtime["export_contract"]["mode"] == "topology_first_closed_nurbs_impeller_surface_graph"
    assert runtime["export_contract"].get("deferred_reason") != "v1_0_3_surface_graph_builder_pending"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_kernel_capabilities"
    assert "section_loop_blade_root_blend_surface_graph" not in repr(runtime["selected_rules"])
    assert "section_loop_blade_root_blend_surface_graph" in repr(production_runtime["selected_rules"])
    assert production_runtime["geometry_patch_version"] == "1.0.4"


def test_v10_presets_keep_g2_blade_transition_defaults():
    for preset_id in V10_2_PRESET_IDS:
        runtime = compile_impeller_runtime_preset(preset_id)
        policies = runtime["transition_policy_defaults"]

        for policy_id in G2_FILLET_POLICIES:
            policy = policies[policy_id]
            assert policy["enabled"] is True
            assert policy["treatment"] == "fillet"
            assert policy["continuity"] == "G2"


def test_v10_presets_resolve_positive_attachment_defaults():
    for preset_id in V10_2_PRESET_IDS:
        runtime = compile_impeller_runtime_preset(preset_id)
        resolved = runtime["resolved_attachment_defaults"]
        margins = resolved["resolved_support_domain_margins"]

        assert resolved["resolved_blade_count"] >= 2
        assert resolved["resolved_blade_thickness_mm"] > 0
        assert resolved["resolved_root_attachment_width_mm"] > 0
        assert resolved["resolved_root_attachment_lift_mm"] > 0
        assert resolved["resolved_tip_attachment_width_mm"] > 0
        assert resolved["resolved_tip_attachment_lift_mm"] > 0
        assert margins["minimum_pitch_margin_mm"] >= 0
        assert margins["hub_material_margin_mm"] >= 0


def test_v10_closed_preset_keeps_closed_shroud_feasibility_constraint():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")
    resolved = runtime["resolved_attachment_defaults"]

    assert "closed_shroud_material_supports_tip_attachment_lift" in runtime["preset_feasibility_constraints"]
    assert resolved["resolved_support_domain_margins"]["shroud_material_margin_mm"] >= 0
    assert resolved["not_applicable_constraints"] == {}


def test_v10_attachment_defaults_report_constructor_rule_strings_and_samples():
    bundle = load_impeller_dsl_bundle("v1_0")
    constructor = bundle.constructors["axisymmetric_throughflow_radial_bladed.closed.v1_0"]
    defaults = constructor["v1_0_2_attachment_defaults"]
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")
    resolved = runtime["resolved_attachment_defaults"]

    assert resolved["edge_short_direction_sample_count"] == defaults["edge_short_direction_sample_count"]
    assert (
        resolved["attachment_short_direction_sample_count"]
        == defaults["attachment_short_direction_sample_count"]
    )
    assert resolved["source_rule_strings"] == {
        "root_attachment_width_rule": defaults["root_attachment_width_rule"],
        "root_attachment_lift_rule": defaults["root_attachment_lift_rule"],
        "tip_attachment_width_rule": defaults["tip_attachment_width_rule"],
        "tip_attachment_lift_rule": defaults["tip_attachment_lift_rule"],
    }


def test_v10_attachment_defaults_fail_blade_count_below_two_without_pitch_clamp():
    bundle = load_impeller_dsl_bundle("v1_0")
    preset = copy.deepcopy(bundle.presets["radial_open_reference_v1_0"])
    constructor = bundle.constructors[preset["constructor_id"]]
    preset["parameter_values"]["blade_count"] = 1

    resolved = _v10_2_attachment_defaults(preset["parameter_values"], constructor)
    margins = resolved["resolved_support_domain_margins"]

    assert margins["blade_count_minimum_margin"] == -1
    assert "blade_count_below_minimum_two" in resolved["preset_default_violation_reasons"]
    assert resolved["preset_feasibility_status"] == "FAIL"
    assert resolved["preset_default_violation_count"] >= 1


def test_v10_2_metadata_does_not_leak_to_v0_91_runtime():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_91")

    assert "geometry_patch_version" not in runtime
    assert "resolved_attachment_defaults" not in runtime
    assert "continuous_blade_attachment_status" not in runtime
    assert "preset_feasibility_status" not in runtime
    assert "preset_default_violation_count" not in runtime
    assert "preset_feasibility_constraints" not in runtime
    assert "preset_adjusted_defaults" not in runtime


def test_v10_presets_disable_hub_outer_chamfer_defaults():
    for preset_id in V10_2_PRESET_IDS:
        runtime = compile_impeller_runtime_preset(preset_id)
        policies = runtime["transition_policy_defaults"]

        assert policies["hub_bottom_outer.default"]["enabled"] is False
        assert policies["hub_top_outer.default"]["enabled"] is False
