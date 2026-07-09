from __future__ import annotations

import math
import sys
import copy
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import (
    _bind_parameters,
    _geometry_kernel_metadata,
    _geometry_metadata,
    _v10_3_geometry_bootstrap_metadata,
)


@lru_cache(maxsize=1)
def _base_graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def _graph() -> dict:
    return copy.deepcopy(_base_graph())


def test_v10_4_section_loops_are_closed_ordered_and_single_loop():
    graph = _graph()
    blade = graph["sampled_blades"][0]
    root_loop = blade["section_loops"][0]
    quality = root_loop["v1_0_4_section_loop_quality"]

    assert root_loop["segment_order"] == ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
    assert quality["status"] == "PASS"
    assert quality["max_closure_gap_mm"] <= 1.0e-6
    assert quality["orientation"] == "ccw_material_outward"
    assert quality["reason"] is None
    assert quality["max_join_tangent_angle_deg"] <= 2.0
    assert quality["max_join_curvature_proxy_mismatch"] <= 0.25
    assert len(root_loop["closed_loop_points"]) >= 4 * 9


def test_v10_4_section_loop_uses_s_camber_offset_contract():
    graph = _graph()
    blade = graph["sampled_blades"][0]
    mid_loop = blade["section_loops"][len(blade["section_loops"]) // 2]
    pressure = mid_loop["segments"]["pressure_side"]["points"]
    suction = mid_loop["segments"]["suction_side"]["points"]
    thicknesses = [
        _distance(left, right)
        for left, right in zip(reversed(pressure), suction)
    ]
    contract = mid_loop["v1_0_4_section_loop_constructor"]

    assert mid_loop["source"] == "v1_0_4_s_camber_normal_offset_section_loop"
    assert contract["construction"] == "s_camber_normal_offset_c2_loop"
    assert contract["pressure_suction_source"] == "same_mean_camber_normal_offset"
    assert contract["join_continuity_intent"] == "C2"
    assert mid_loop["metrics"]["s_camber_inflection_count"] >= 1
    assert mid_loop["metrics"]["s_camber_amplitude_mm"] <= 0.95 * mid_loop["metrics"]["max_thickness_mm"]
    assert min(thicknesses) > 0.0
    assert max(thicknesses) / min(thicknesses) < 2.25
    assert mid_loop["metrics"]["pressure_suction_parallelism_status"] == "PASS"


def test_v10_4_section_loop_rejects_wrong_segment_order():
    from part_rule_synthesis.impeller_v10_4_section_loop_contract import measure_section_loop_contract

    bad_loop = {
        "segment_order": ["pressure_side", "suction_side", "leading_edge", "trailing_edge"],
        "segments": {
            "pressure_side": {"points": [[0.0, -1.0, 0.0], [1.0, -1.0, 0.0]]},
            "leading_edge": {"points": [[0.0, -1.0, 0.0], [0.0, 1.0, 0.0]]},
            "suction_side": {"points": [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]},
            "trailing_edge": {"points": [[1.0, 1.0, 0.0], [1.0, -1.0, 0.0]]},
        },
    }

    quality = measure_section_loop_contract(bad_loop)

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_section_loop_order_invalid"


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((left[axis] - right[axis]) ** 2 for axis in range(3)))


def test_v10_4_section_loop_rejects_real_eight_degree_join_kink():
    from part_rule_synthesis.impeller_v10_4_section_loop_contract import SEGMENT_ORDER, measure_section_loop_contract

    eight_deg = math.radians(8.0)
    kinked_loop = {
        "segment_order": SEGMENT_ORDER,
        "segments": {
            "pressure_side": {
                "points": [[0.0, -2.0, 0.0], [1.0, -2.0, 0.0], [3.0, -1.0, 0.0], [4.0, -1.0, 0.0], [4.0, 0.0, 0.0]]
            },
            "leading_edge": {
                "points": [
                    [4.0, 0.0, 0.0],
                    [4.0 - math.sin(eight_deg), math.cos(eight_deg), 0.0],
                    [3.0, 2.0, 0.0],
                    [1.0, 2.0, 0.0],
                    [0.0, 2.0, 0.0],
                ]
            },
            "suction_side": {
                "points": [[0.0, 2.0, 0.0], [-1.0, 2.0, 0.0], [-3.0, 1.0, 0.0], [-4.0, 1.0, 0.0], [-4.0, 0.0, 0.0]]
            },
            "trailing_edge": {
                "points": [[-4.0, 0.0, 0.0], [-4.0, -1.0, 0.0], [-3.0, -2.0, 0.0], [-1.0, -2.0, 0.0], [0.0, -2.0, 0.0]]
            },
        },
    }

    quality = measure_section_loop_contract(kinked_loop)

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_section_loop_g2_measurement_failed"
    assert quality["max_join_tangent_angle_deg"] > 2.0


def test_v10_4_service_kernel_metadata_preserves_patch_version():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})

    kernel = _geometry_kernel_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)

    assert runtime["geometry_patch_version"] == "1.0.4"
    assert kernel["geometry_patch_version"] == "1.0.4"
    assert kernel["surface_graph_status"] in {"PASS", "FAIL", "DEFERRED"}


def test_v10_4_bootstrap_metadata_preserves_deferred_patch_scoping():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})

    bootstrap = _v10_3_geometry_bootstrap_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        runtime,
    )

    assert bootstrap["geometry_patch_version"] == "1.0.4"
    assert bootstrap["geometry_generation_status"] == "DEFERRED"
    assert bootstrap["deferred_reason"] == "v1_0_4_surface_graph_builder_pending"
    assert bootstrap["surface_graph"]["geometry_patch_version"] == "1.0.4"
    assert bootstrap["surface_graph"]["surface_graph_status"] == "DEFERRED"
    assert bootstrap["surface_graph"]["deferred_reason"] == "v1_0_4_surface_graph_builder_pending"
    assert bootstrap["validity"]["geometry_checks"][0]["reason"] == "v1_0_4_surface_graph_builder_pending"
