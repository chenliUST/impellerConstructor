from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset

RESOURCE_ROOT = (
    SRC_ROOT
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_91"
)


def test_v091_bundle_loads_topology_first_contract():
    bundle = load_impeller_dsl_bundle("v0_91")

    assert bundle.schema["dsl_version"] == "0.91"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_91",
        "radial_closed_reference_v0_91",
    }

    contract = bundle.export_contracts["topology_first_transition_bounded_brep"]
    assert contract["contract_version"] == "0.91"
    assert contract["mode"] == "topology_first_transition_bounded_brep"
    assert contract["coverage_status"] == "complete_topology_first_validated_transition_graph"
    assert contract["mesh_strategy"] == "shared_node_transition_patch_mesh"

    matrix = bundle.capability_matrices["impeller_v0_91_kernel_capabilities"]
    assert matrix["matrix_id"] == "impeller_v0_91_kernel_capabilities"
    assert matrix["version"] == "0.91"
    assert {
        entry["status"]
        for entry in matrix["capabilities"]
    } <= {"supported", "partial", "research_grade", "unsupported"}

    registry = bundle.golden_case_registries["impeller_v0_91_golden_cases"]
    assert registry["registry_id"] == "impeller_v0_91_golden_cases"
    assert registry["version"] == "0.91"
    assert {
        case["preset_id"]
        for case in registry["cases"]
        if case["category"] == "golden"
    } >= {"radial_open_reference_v0_91", "radial_closed_reference_v0_91"}
    assert all(case["case_id"].startswith("v091_") for case in registry["cases"])


def test_v091_runtime_marks_topology_first_transition_graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_91")

    assert runtime["version"] == "0.91.0"
    assert runtime["dsl_version"] == "0.91"
    assert runtime["dsl_sections"]["dsl_version"] == "0.91"
    assert runtime["geometry_version"] == "0.91"
    assert runtime["transition_geometry_status"] == "topology_first_validated_transition_graph"
    assert runtime["mesh_strategy"] == "shared_node_transition_patch_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v0_91_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v0_91_golden_cases"
    assert runtime["edge_families"]["blade_root_to_hub"]["default_treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["mounting_bore_top.default"]["treatment"] == "chamfer"


def test_v091_resources_do_not_retain_v09_transition_identifiers():
    resource_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(RESOURCE_ROOT.rglob("*"))
        if path.suffix in {".json", ".md"}
    )

    forbidden_patterns = [
        r"v0_9(?!1)",
        r"v0\.9(?!1)",
        r"\b0\.9\b",
        r"\bv09_",
        r"radial_open_reference_v0_9(?!1)",
        r"radial_closed_reference_v0_9(?!1)",
        r"validated_transition_bounded_brep",
        r"validated_transition_surface_graph",
        r"validated_transition_aware_surface_mesh",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, resource_text) is None, pattern

    assert "0.915" not in resource_text
