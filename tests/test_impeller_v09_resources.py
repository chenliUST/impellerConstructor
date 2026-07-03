from __future__ import annotations

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v09_bundle_loads_validated_transition_contract_and_research_registries():
    bundle = load_impeller_dsl_bundle("v0_9")

    assert bundle.schema["dsl_version"] == "0.9"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_9",
        "radial_closed_reference_v0_9",
    }

    contract = bundle.export_contracts["validated_transition_bounded_brep"]
    assert contract["mode"] == "validated_transition_bounded_brep"
    assert contract["mesh_strategy"] == "validated_transition_aware_surface_mesh"
    assert contract["unsupported_surface_policy"] == "fail_export"

    matrix = bundle.capability_matrices["impeller_v0_9_kernel_capabilities"]
    assert matrix["matrix_id"] == "impeller_v0_9_kernel_capabilities"
    assert {
        entry["status"]
        for entry in matrix["capabilities"]
    } <= {"supported", "partial", "research_grade", "unsupported"}

    registry = bundle.golden_case_registries["impeller_v0_9_golden_cases"]
    assert 6 <= len(registry["cases"]) <= 10
    assert {
        case["preset_id"]
        for case in registry["cases"]
        if case["category"] == "golden"
    } >= {"radial_open_reference_v0_9", "radial_closed_reference_v0_9"}


def test_v09_runtime_marks_validated_transition_geometry():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_9")

    assert runtime["version"] == "0.9.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.9"
    assert runtime["geometry_version"] == "0.9"
    assert runtime["transition_geometry_status"] == "validated_transition_surface_graph"
    assert runtime["mesh_strategy"] == "validated_transition_aware_surface_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v0_9_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v0_9_golden_cases"
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
