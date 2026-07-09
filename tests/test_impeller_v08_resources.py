from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v08_bundle_loads_transition_resolved_contract():
    bundle = load_impeller_dsl_bundle("v0_8")

    assert bundle.schema["dsl_version"] == "0.8"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_8",
        "radial_closed_reference_v0_8",
    }
    contract = bundle.export_contracts["transition_resolved_bounded_brep"]
    assert contract["mode"] == "transition_resolved_bounded_brep"
    assert contract["step_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
    assert contract["mesh_strategy"] == "transition_aware_surface_mesh"


def test_v08_runtime_marks_transition_resolved_geometry():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_8")

    assert runtime["version"] == "0.8.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.8"
    assert runtime["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["mounting_bore_top.default"]["treatment"] == "chamfer"
