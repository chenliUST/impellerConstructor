from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import (
    _v10_4_preset_contract,
    compile_impeller_runtime_preset,
)


def test_v10_4_open_runtime_reports_geometry_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.4"
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert runtime["mesh_strategy"] == "v1_0_4_surface_uv_and_review_quad_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_4_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_4_golden_cases"


def test_v10_4_open_preset_contract_defaults_are_reviewable():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    params = runtime["parameters"]
    defaults = runtime["resolved_section_loop_defaults"]
    contract = runtime["v1_0_4_preset_contract"]
    profile_defaults = runtime["profile_defaults"]

    assert params["blade_count"]["default"] == 12
    assert params["blade_thickness_mm"]["default"] == 40.0
    assert params["inlet_blade_height_mm"]["default"] == 170.0
    assert params["outlet_blade_height_mm"]["default"] == 30.0
    assert defaults["main_blade_count"] == 6
    assert defaults["splitter_blade_count"] == 6
    assert defaults["average_blade_thickness_mm"] == 40.0
    assert defaults["root_attachment_width_mm"] == 20.0
    assert defaults["root_attachment_lift_mm"] == 20.0
    assert defaults["tip_dome_height_mm"] == 12.0
    assert defaults["main_streamwise_start_u"] == 0.08
    assert defaults["main_streamwise_end_u"] == 0.92
    assert defaults["splitter_streamwise_start_u"] == 0.40
    assert defaults["splitter_streamwise_end_u"] == 0.82
    assert profile_defaults["hub_profile"]["control_points"] == [
        [150, 400],
        [170, 250],
        [220, 150],
        [330, 50],
        [480, 10],
        [580, 0],
    ]
    assert profile_defaults["tip_or_shroud_profile"]["control_points"] == [
        [230, 401],
        [250, 270],
        [310, 170],
        [400, 90],
        [490, 50],
        [581, 30],
    ]
    assert contract["blade_hub_angle_range_deg"] == [60.0, 120.0]


def test_v10_4_preset_contract_uses_average_blade_thickness_when_present():
    contract = _v10_4_preset_contract(
        {"blade_thickness_mm": {"default": 20.0}},
        {"average_blade_thickness_mm": 24.0},
    )

    assert contract["expected_root_width_mm"] == 12.0
    assert contract["expected_root_lift_mm"] == 12.0
    assert contract["expected_tip_dome_height_mm"] == 12.0
