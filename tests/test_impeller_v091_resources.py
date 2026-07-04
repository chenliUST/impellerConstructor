from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis import impeller_dsl_resources
from part_rule_synthesis import service as service_module
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import RuleSynthesisService

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


def test_v091_lineage_points_to_v09_resources():
    bundle = load_impeller_dsl_bundle("v0_91")

    assert bundle.schema["supersedes"] == "../v0_9/schema.json"
    assert (
        bundle.constructors["axisymmetric_throughflow_radial_bladed.open.v0_91"]["supersedes"]
        == "../../v0_9/constructors/open_impeller.json"
    )
    assert (
        bundle.constructors["axisymmetric_throughflow_radial_bladed.closed.v0_91"]["supersedes"]
        == "../../v0_9/constructors/closed_impeller.json"
    )
    assert (
        bundle.presets["radial_open_reference_v0_91"]["supersedes"]
        == "../../v0_9/presets/radial_open_reference.json"
    )
    assert (
        bundle.presets["radial_closed_reference_v0_91"]["supersedes"]
        == "../../v0_9/presets/radial_closed_reference.json"
    )
    changelog = (RESOURCE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Supersedes: `v0_9`" in changelog


def test_v091_bundle_applies_research_registry_validation(monkeypatch):
    original_loader = impeller_dsl_resources._load_json_directory_by_id

    def missing_v091_capability_matrix(path: Path, id_field: str):
        loaded = original_loader(path, id_field)
        if "v0_91" in path.parts and path.name == "capability_matrices":
            return {}
        return loaded

    monkeypatch.setattr(
        impeller_dsl_resources,
        "_load_json_directory_by_id",
        missing_v091_capability_matrix,
    )

    with pytest.raises(ValueError, match="impeller v0.91 missing kernel capability matrix"):
        load_impeller_dsl_bundle("v0_91")


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


def test_v091_service_blocks_until_corner_patch_solver_exists(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    engine = service.synthesize("impeller", "radial_open_reference_v0_91")

    with pytest.raises(RuntimeError, match="geometry validation.*missing_required_corner_transition_patches"):
        service.instantiate(engine.engine_id, {})


def test_v091_service_export_strategy_recognizes_topology_first_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_91")

    strategy = service_module._export_strategy("impeller", dsl_context=runtime, export_manifests={})

    assert strategy["mode"] == "topology_first_transition_bounded_brep"
    assert strategy["step_exactness"] == "validated_bounded_unsewn_review_brep_step"
    assert strategy["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert strategy["coverage_status"] == "complete_topology_first_validated_transition_graph"
    assert (
        strategy["cad_export_scope"]
        == "all_topology_first_validated_transition_graph_cad_surfaces"
    )
    assert strategy["unsupported_surface_policy"] == "fail_export"


def test_v091_topology_first_export_rejects_missing_validation_report(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    writer_calls = []

    def fake_bounded_brep(step_path, solid_name, surface_graph, view_id="cad_review_360"):
        writer_calls.append("step")
        Path(step_path).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        return {
            "source": "surface_graph",
            "view": view_id,
            "export_exactness": "surface_graph_bounded_unsewn_brep_step",
            "validation_checks": [],
        }

    def fake_graph_exports(mesh_step_path, stl_path, solid_name, surface_graph, view_id="cad_review_360"):
        writer_calls.append("mesh")
        Path(mesh_step_path).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        Path(stl_path).write_text("solid impeller\nendsolid impeller\n", encoding="utf-8")
        return {"stl": {"source": "surface_graph", "export_exactness": "surface_graph_sampled_mesh"}}

    def fake_obj_export(obj_path, solid_name, surface_graph, view_id="cad_review_360"):
        writer_calls.append("obj")
        Path(obj_path).write_text("v 0 0 0\n", encoding="utf-8")
        return {"source": "surface_graph", "export_exactness": "surface_graph_obj_mesh"}

    monkeypatch.setattr(service_module, "write_bounded_brep_step", fake_bounded_brep)
    monkeypatch.setattr(service_module, "write_surface_graph_exports", fake_graph_exports)
    monkeypatch.setattr(service_module, "write_surface_graph_obj", fake_obj_export)

    with pytest.raises(RuntimeError, match="geometry validation report.*PASS"):
        service_module._write_exports(
            run_dir,
            "impeller",
            {},
            dsl_context={
                "preset_id": "radial_open_reference_v0_91",
                "export_contract": {
                    "mode": "topology_first_transition_bounded_brep",
                    "default_view": "cad_review_360",
                },
            },
            geometry_metadata={"surface_graph": {"surfaces": [{"id": "hub", "kind": "annular_plane_surface"}]}},
        )

    assert writer_calls == []


def test_v091_resources_do_not_retain_v09_transition_identifiers():
    resource_text = "\n".join(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if '"supersedes"' not in line and not line.startswith("Supersedes:")
        )
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
