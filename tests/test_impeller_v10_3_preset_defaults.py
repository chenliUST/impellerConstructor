from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_3_historical_fixture import historical_v10_3_open_runtime
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_historical_v10_3_open_defaults_are_main_splitter_and_thickness_scaled():
    runtime = historical_v10_3_open_runtime()
    params = runtime["parameters"]
    defaults = runtime["resolved_section_loop_defaults"]

    assert runtime["geometry_patch_version"] == "1.0.3"
    assert params["blade_count"]["default"] == 8
    assert defaults["main_blade_count"] == 4
    assert defaults["splitter_blade_count"] == 4
    assert defaults["blade_pair_count"] == 4
    assert params["blade_thickness_mm"]["default"] == 20.0
    assert defaults["average_blade_thickness_mm"] == 20.0
    assert defaults["root_attachment_width_mm"] == 8.0
    assert defaults["root_attachment_lift_mm"] == 8.0
    assert defaults["tip_dome_height_mm"] == 12.0
    assert defaults["main_streamwise_start_u"] == 0.20
    assert defaults["main_streamwise_end_u"] == 0.80
    assert defaults["splitter_streamwise_start_u"] == 0.48
    assert defaults["splitter_streamwise_end_u"] == 0.76
    assert defaults["section_loop_sample_count"] == 33
    assert defaults["face_streamwise_sample_count"] == 41
    assert defaults["root_short_direction_sample_count"] == 17
    assert defaults["tip_dome_short_direction_sample_count"] == 17


def test_live_v10_open_parameters_keep_service_binding_shape():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_patch_version"] == "1.0.4"
    for spec in runtime["parameters"].values():
        assert isinstance(spec, dict)
        assert {"default", "min", "max"} <= set(spec)


def test_historical_v10_3_open_defaults_have_positive_support_margins():
    runtime = historical_v10_3_open_runtime()
    feasibility = runtime["v1_0_3_preset_feasibility"]

    assert runtime["geometry_patch_version"] == "1.0.3"
    assert feasibility["status"] == "PASS"
    assert feasibility["leading_edge_support_margin_mm"] > 40.0
    assert feasibility["trailing_edge_support_margin_mm"] > 40.0
    assert feasibility["root_footprint_inside_hub_domain"] is True
    assert feasibility["tip_loop_inside_tip_support_domain"] is True
