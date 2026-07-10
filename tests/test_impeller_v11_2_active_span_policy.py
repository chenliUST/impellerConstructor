from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family

ACTIVE_V11_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def _runtime(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    return runtime, parameters


def _defaults_with_canonical(runtime):
    return {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": deepcopy(runtime["canonical_nurbs_parameterization"]),
    }


def test_active_span_policy_offsets_root_loop_from_hub_support():
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    defaults = _defaults_with_canonical(runtime)
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_root_offset_max_mm"] >= metrics["resolved_root_offset_min_mm"]
    assert metrics["resolved_tip_offset_max_mm"] == 0.0
    assert metrics["pointwise_support_span_min_mm"] > metrics["resolved_root_offset_min_mm"]
    assert metrics["pointwise_usable_span_min_mm"] > 0.0
    assert metrics["offset_feasibility_status"] == "PASS"
    assert family["blades"][0]["loops"][0]["h"] == 0.0
    assert family["blades"][0]["loops"][0]["active_span_fraction"] > 0.0


def test_all_active_v11_presets_have_feasible_active_span_offsets():
    for preset_id in ACTIVE_V11_PRESETS:
        runtime, parameters = _runtime(preset_id)
        defaults = _defaults_with_canonical(runtime)
        family = build_v11_blade_to_blade_loop_family(parameters, defaults)

        metrics = family["active_span_policy_metrics"]
        assert metrics["pointwise_usable_span_min_mm"] > 0.0, preset_id
        assert metrics["offset_feasibility_status"] == "PASS", preset_id


def test_active_span_policy_reports_pointwise_infeasible_offsets():
    runtime, parameters = _runtime("radial_closed_reference_v1_1")
    defaults = _defaults_with_canonical(runtime)
    canonical = defaults["canonical_nurbs_parameterization"]
    canonical["active_span_policy"]["root_offset"]["resolved_constant_mm"] = 25.0
    canonical["active_span_policy"]["tip_offset"]["resolved_constant_mm"] = 25.0
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_tip_offset_min_mm"] > 0.0
    assert metrics["pointwise_support_span_min_mm"] < (
        metrics["resolved_root_offset_min_mm"] + metrics["resolved_tip_offset_min_mm"]
    )
    assert metrics["pointwise_usable_span_min_mm"] < 0.0
    assert metrics["offset_feasibility_status"] == "FAIL"


@pytest.mark.parametrize(
    ("field_name", "payload"),
    [
        ("blade_skeleton_field", {"kind": "nurbs_surface"}),
        ("thickness_field", {"control_points": "bad"}),
    ],
)
def test_malformed_canonical_surface_payloads_fall_back_to_legacy_side_sampling(field_name, payload):
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    legacy_family = build_v11_blade_to_blade_loop_family(
        parameters,
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    defaults = _defaults_with_canonical(runtime)
    defaults["canonical_nurbs_parameterization"][field_name] = payload

    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    legacy_loop = legacy_family["blades"][0]["loops"][0]
    loop = family["blades"][0]["loops"][0]
    _assert_point_sequences_match(
        loop["segments"]["pressure_side"]["points_s_q"],
        legacy_loop["segments"]["pressure_side"]["points_s_q"],
    )
    _assert_point_sequences_match(
        loop["segments"]["suction_side"]["points_s_q"],
        legacy_loop["segments"]["suction_side"]["points_s_q"],
    )


def _assert_point_sequences_match(actual, expected):
    assert len(actual) == len(expected)
    for actual_point, expected_point in zip(actual, expected):
        assert actual_point == pytest.approx(expected_point)
