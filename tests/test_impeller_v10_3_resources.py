from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_3_historical_fixture import historical_v10_3_open_runtime
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import (
    _v10_3_runtime_defaults,
    compile_impeller_runtime_preset,
)
from part_rule_synthesis import service as service_module
from part_rule_synthesis.service import RuleSynthesisService


def test_open_reference_routes_to_v10_3_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    bundle = load_impeller_dsl_bundle("v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.4"
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert runtime["mesh_strategy"] == "v1_0_4_surface_uv_and_review_quad_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_4_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_4_golden_cases"
    assert runtime["export_contract"]["mode"] == "topology_first_section_loop_blade_root_blend_surface_graph"
    assert runtime["export_contract"]["mesh_strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
    assert "impeller_v1_0_3_kernel_capabilities" in bundle.capability_matrices
    assert "impeller_v1_0_3_golden_cases" in bundle.golden_case_registries


def test_closed_reference_remains_v10_2_until_closed_tip_spec_exists():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.2"
    assert "resolved_section_loop_defaults" not in runtime


def test_open_reference_resources_use_v10_3_export_contract_metadata():
    bundle = load_impeller_dsl_bundle("v1_0")
    preset = copy.deepcopy(bundle.presets["radial_open_reference_v1_0"])
    constructor = bundle.constructors[preset["constructor_id"]]
    export_contract = bundle.export_contracts["section_loop_blade_root_blend_surface_graph"]
    runtime = _v10_3_runtime_defaults(
        preset,
        preset["parameter_values"],
        constructor,
        export_contract,
    )

    assert preset["transition_geometry_status"] == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    assert runtime["geometry_patch_version"] == "1.0.3"
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert runtime["mesh_strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
    assert "section_loop_blade_root_blend_surface_graph" in bundle.export_contracts
    assert constructor["export_contracts"] == {
        "section_loop_blade_root_blend_surface_graph": {
            "contract_ref": "export_contracts/section_loop_blade_root_blend_surface_graph.json"
        }
    }
    assert export_contract["implementation_status"] == "surface_graph_builder_available"
    assert export_contract["current_coverage_status"] == "sampled_surface_graph_available"
    assert export_contract["current_cad_export_scope"] == "review_grade_v1_0_3_sampled_surfaces"
    assert export_contract["current_geometry_generation_status"] == "PASS"
    assert export_contract["current_cad_exports"] == "bounded_unsewn_review_surfaces"


def test_v10_3_resource_metadata_discloses_active_sampled_surface_graph():
    bundle = load_impeller_dsl_bundle("v1_0")
    matrix = bundle.capability_matrices["impeller_v1_0_3_kernel_capabilities"]
    capabilities = {entry["id"]: entry for entry in matrix["capabilities"]}

    for capability_id in [
        "surface_graph_generation",
        "section_loop_blade_face_network",
        "native_hub_bore_bevel_faces",
        "bounded_review_brep_step",
        "section_loop_shared_edge_quad_mesh",
    ]:
        capability = capabilities[capability_id]
        assert capability["status"] in {"partial", "research_grade"}
        assert "deferred" not in capability["claim"].lower()
        assert any(
            token in capability["claim"].lower()
            for token in ["surface graph", "surface_graph", "sampled", "review"]
        )


def test_v10_3_service_export_strategy_recognizes_section_loop_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    strategy = service_module._export_strategy("impeller", dsl_context=runtime, export_manifests={})

    assert strategy["mode"] == "topology_first_section_loop_blade_root_blend_surface_graph"
    assert strategy["cad_exports"] == "completed"
    assert strategy["bounded_brep_status"] == "bounded_faces_unsewn"
    assert strategy["step_exactness"] == "sampled_bounded_unsewn_review_brep_step"
    assert strategy["coverage_status"] == "sampled_surface_graph_available"
    assert strategy["cad_export_scope"] == "review_grade_v1_0_3_sampled_surfaces"


def test_v10_3_open_service_instantiation_generates_surface_graph(tmp_path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_0")
    runtime = historical_v10_3_open_runtime()
    service.engines[engine.engine_id] = runtime
    parameters = {
        name: spec["default"]
        for name, spec in runtime["parameters"].items()
    }

    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest
    surface_graph = manifest["geometry"]["surface_graph"]
    failure_reasons = [
        failure.get("reason")
        for failure in surface_graph.get("v1_0_2_transition_failures", [])
    ]

    assert manifest["geometry_version"] == "1.0"
    assert manifest["geometry_patch_version"] == "1.0.3"
    assert surface_graph["geometry_patch_version"] == "1.0.3"
    assert (
        surface_graph["transition_geometry_status"]
        == "topology_first_section_loop_blade_root_blend_surface_graph"
    )
    assert surface_graph["surface_graph_status"] == "PASS"
    assert surface_graph["section_loop_constructor_status"] == "PASS"
    assert surface_graph["main_blade_count"] == 4
    assert surface_graph["splitter_blade_count"] == 4
    assert manifest["geometry_validation_status"] == "PASS"
    assert (
        manifest["geometry_validation_report"]["transition_validation_summary"]["transition_surface_count"]
        == 56
    )
    assert "v1_0_2_resolved_attachment_defaults_missing" not in failure_reasons
    assert manifest["export_strategy"]["cad_exports"] == "completed"
    assert manifest["export_strategy"]["bounded_brep_status"] == "bounded_faces_unsewn"
    assert manifest["export_strategy"]["coverage_status"] == "sampled_surface_graph_available"
    assert all(key in manifest["exports"] for key in {"step", "stl", "obj"})
    assert all(key in manifest["export_manifests"] for key in {"step", "stl", "obj"})
    cfd_mesh = manifest["simulation_manifests"].get("cfd_surface_mesh")
    assert cfd_mesh is not None
    assert cfd_mesh["source"] == "surface_graph"
    assert cfd_mesh["triangle_count"] > 0
    assert cfd_mesh["degenerate_triangle_count"] == 0
