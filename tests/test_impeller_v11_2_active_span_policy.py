from __future__ import annotations

# ruff: noqa: E402

from copy import deepcopy
import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_curve
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (
    build_v11_blade_to_blade_loop_family,
    map_v11_domain_sample,
)

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
    canonical["active_span_policy"]["root_offset"]["resolved_constant_mm"] = 80.0
    canonical["active_span_policy"]["tip_offset"]["resolved_constant_mm"] = 80.0
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_tip_offset_min_mm"] > 0.0
    assert metrics["pointwise_support_span_min_mm"] < (
        metrics["resolved_root_offset_min_mm"] + metrics["resolved_tip_offset_min_mm"]
    )
    assert metrics["pointwise_usable_span_min_mm"] < 0.0
    assert metrics["offset_feasibility_status"] == "FAIL"


def test_v116_local_root_lift_field_changes_the_actual_active_span_boundary():
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    defaults = _defaults_with_canonical(runtime)
    canonical = defaults["canonical_nurbs_parameterization"]
    canonical["canonical_input_source"] = (
        "v116_adaptive_step_reconstruction_extension"
    )
    canonical["adaptive_reconstruction_extension"] = {"status": "PASS"}
    canonical["active_span_policy"]["root_offset"].update(
        {
            "mode": "v116_measured_streamwise_field",
            "local_size_field": {
                "kind": "nurbs_curve",
                "degree": 1,
                "knots": [0.0, 0.0, 1.0, 1.0],
                "weights": [1.0, 1.0],
                "control_points": [[0.0, 6.0, 4.0], [1.0, 6.0, 12.0]],
                "components": ["u", "width_mm", "lift_mm"],
            },
        }
    )
    s0, s1 = defaults["main_streamwise_interval_s"]

    start = map_v11_domain_sample(parameters, defaults, {"s": s0, "q": 0.0, "h": 0.0})
    end = map_v11_domain_sample(parameters, defaults, {"s": s1, "q": 0.0, "h": 0.0})
    hub_authority = canonical["support_profiles"]["hub_profile"]
    hub_start = evaluate_nurbs_curve(hub_authority, s0)
    hub_end = evaluate_nurbs_curve(hub_authority, s1)

    assert math.dist(start, [hub_start[0], 0.0, hub_start[1]]) == pytest.approx(4.0, abs=1.0e-5)
    assert math.dist(end, [hub_end[0], 0.0, hub_end[1]]) == pytest.approx(12.0, abs=1.0e-5)
    metrics = build_v11_blade_to_blade_loop_family(parameters, defaults)["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] == pytest.approx(4.0)
    assert metrics["resolved_root_offset_max_mm"] == pytest.approx(12.0)


def test_v116_local_root_lift_field_is_ignored_without_adaptive_opt_in():
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    defaults = _defaults_with_canonical(runtime)
    canonical = defaults["canonical_nurbs_parameterization"]
    expected = canonical["active_span_policy"]["root_offset"][
        "resolved_constant_mm"
    ]
    canonical["active_span_policy"]["root_offset"].update(
        {
            "mode": "v116_measured_streamwise_field",
            "local_size_field": {
                "kind": "nurbs_curve",
                "degree": 1,
                "knots": [0.0, 0.0, 1.0, 1.0],
                "weights": [1.0, 1.0],
                "control_points": [[0.0, 6.0, 2.0], [1.0, 6.0, 30.0]],
                "components": ["u", "width_mm", "lift_mm"],
            },
        }
    )

    metrics = build_v11_blade_to_blade_loop_family(
        parameters,
        defaults,
    )["active_span_policy_metrics"]

    assert metrics["resolved_root_offset_min_mm"] == pytest.approx(expected)
    assert metrics["resolved_root_offset_max_mm"] == pytest.approx(expected)


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


def _profile_point(points, s):
    scaled = float(s) * (len(points) - 1)
    left_index = min(int(scaled), len(points) - 1)
    right_index = min(left_index + 1, len(points) - 1)
    fraction = scaled - left_index
    return [
        points[left_index][axis]
        + (points[right_index][axis] - points[left_index][axis]) * fraction
        for axis in range(2)
    ]
