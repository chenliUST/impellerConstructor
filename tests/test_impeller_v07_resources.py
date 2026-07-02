from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v07_bundle_loads_schema_and_transition_resources():
    bundle = load_impeller_dsl_bundle("v0_7")

    assert bundle.schema["dsl_version"] == "0.7"
    assert bundle.shape_controls["shape_control_version"] == "0.7"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_7",
        "radial_closed_reference_v0_7",
    }
    assert bundle.export_contracts["surface_graph_bounded_brep"]["mode"] == "surface_graph_bounded_brep"
    assert bundle.export_contracts["surface_graph_bounded_brep"]["step_exactness"] == "surface_graph_trimmed_brep_step"


def test_v07_runtime_exposes_edge_families_and_default_policies():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_7")

    assert runtime["version"] == "0.7.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.7"
    assert "edge_families" in runtime
    assert "transition_policy_defaults" in runtime
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["hub_top_outer.default"]["treatment"] == "fillet"
