from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_3_historical_fixture import historical_v10_3_open_runtime
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_runtime_compiler import impeller_json_preset_ids


V10_STATUS = "topology_first_closed_nurbs_impeller_surface_graph"
V10_3_OPEN_STATUS = "topology_first_section_loop_blade_root_blend_surface_graph"
V10_4_OPEN_STATUS = "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
V10_MESH_STRATEGY = "topology_first_shared_edge_quad_patch_mesh"
V10_3_OPEN_MESH_STRATEGY = "section_loop_shared_edge_review_grade_quad_mesh"
V10_4_OPEN_MESH_STRATEGY = "v1_0_4_surface_uv_and_review_quad_mesh"


def test_v10_bundle_loads_topology_first_constructor_contract():
    bundle = load_impeller_dsl_bundle("v1_0")

    assert bundle.schema["dsl_version"] == "1.0"
    assert set(bundle.presets) == {
        "radial_open_reference_v1_0",
        "radial_closed_reference_v1_0",
    }
    assert bundle.capability_matrices["impeller_v1_0_kernel_capabilities"]["version"] == "1.0"
    assert bundle.golden_case_registries["impeller_v1_0_golden_cases"]["version"] == "1.0"

    contract = bundle.export_contracts["topology_first_closed_nurbs_impeller_surface_graph"]
    assert contract["contract_version"] == "1.0"
    assert contract["mode"] == "topology_first_closed_nurbs_impeller_surface_graph"
    assert contract["mesh_strategy"] == V10_MESH_STRATEGY


def test_v10_open_and_closed_presets_are_registered():
    preset_ids = impeller_json_preset_ids()

    assert "radial_open_reference_v1_0" in preset_ids
    assert "radial_closed_reference_v1_0" in preset_ids


def test_v10_open_preset_compiles_with_v10_4_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["preset_id"] == "radial_open_reference_v1_0"
    assert runtime["dsl_version"] == "1.0"
    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.4"
    assert runtime["transition_geometry_status"] == V10_4_OPEN_STATUS
    assert runtime["mesh_strategy"] == V10_4_OPEN_MESH_STRATEGY
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_4_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_4_golden_cases"
    assert runtime["facets"]["shroud_topology"] == "open"


def test_v10_closed_preset_compiles_with_v10_2_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")

    assert runtime["preset_id"] == "radial_closed_reference_v1_0"
    assert runtime["dsl_version"] == "1.0"
    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.2"
    assert runtime["transition_geometry_status"] == V10_STATUS
    assert runtime["mesh_strategy"] == V10_MESH_STRATEGY
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_golden_cases"
    assert runtime["facets"]["shroud_topology"] == "closed"


def test_historical_v10_3_open_runtime_contract_remains_available_for_regression_checks():
    runtime = historical_v10_3_open_runtime()

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.3"
    assert runtime["transition_geometry_status"] == V10_3_OPEN_STATUS
    assert runtime["mesh_strategy"] == V10_3_OPEN_MESH_STRATEGY
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_3_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_3_golden_cases"
    assert runtime["facets"]["shroud_topology"] == "open"
