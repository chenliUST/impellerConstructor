from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


def test_loop_joins_report_c2_pass_metrics():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    failures = validate_v11_loop_family(family)

    assert failures == []
    first_loop = family["blades"][0]["loops"][0]
    for join in [
        "pressure_to_leading",
        "leading_to_suction",
        "suction_to_trailing",
        "trailing_to_pressure",
    ]:
        metrics = first_loop["join_metrics"][join]
        assert metrics["status"] == "PASS"
        assert metrics["position_gap_mm"] <= 1e-6
        assert metrics["tangent_angle_deg"] <= 2.0
        assert metrics["curvature_proxy_mismatch"] <= 0.25

    segments = first_loop["segments"]
    assert segments["pressure_side"]["points_s_q"][0] == pytest.approx(segments["leading_edge"]["points_s_q"][0])
    assert segments["leading_edge"]["points_s_q"][-1] == pytest.approx(segments["suction_side"]["points_s_q"][0])
    assert segments["suction_side"]["points_s_q"][-1] == pytest.approx(segments["trailing_edge"]["points_s_q"][0])
    assert segments["trailing_edge"]["points_s_q"][-1] == pytest.approx(segments["pressure_side"]["points_s_q"][-1])


def test_edge_cap_pressure_side_tangents_follow_closed_loop_orientation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    streamwise_metric_scale_mm = _profile_length_mm(
        runtime["resolved_blade_to_blade_loop_family_defaults"]["hub_profile_rz_mm"]
    )
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    for blade in family["blades"]:
        for loop in blade["loops"]:
            segments = loop["segments"]
            pressure = segments["pressure_side"]["points_s_q"]
            leading = segments["leading_edge"]["points_s_q"]
            trailing = segments["trailing_edge"]["points_s_q"]

            pressure_start_tangent = _scale_streamwise(_diff(pressure[1], pressure[0]), streamwise_metric_scale_mm)
            leading_start_tangent = _scale_streamwise(_diff(leading[1], leading[0]), streamwise_metric_scale_mm)
            assert _vector_angle_deg(leading_start_tangent, _negate(pressure_start_tangent)) <= 2.0

            pressure_end_tangent = _scale_streamwise(_diff(pressure[-1], pressure[-2]), streamwise_metric_scale_mm)
            trailing_end_tangent = _scale_streamwise(_diff(trailing[-1], trailing[-2]), streamwise_metric_scale_mm)
            assert _vector_angle_deg(trailing_end_tangent, _negate(pressure_end_tangent)) <= 2.0


def test_edge_caps_do_not_have_internal_segment_spikes_or_excess_overshoot():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    for blade in family["blades"]:
        for loop in blade["loops"]:
            for segment_name in ["leading_edge", "trailing_edge"]:
                points = loop["segments"][segment_name]["points_s_q"]
                segment_lengths = [
                    _vector_length(_diff(points[index], points[index - 1]))
                    for index in range(1, len(points))
                ]
                median_length = sorted(segment_lengths)[len(segment_lengths) // 2]
                assert max(segment_lengths) <= 2.25 * median_length

                q_values = [point[1] for point in points]
                q_start = points[0][1]
                q_end = points[-1][1]
                q_min = min(q_start, q_end)
                q_max = max(q_start, q_end)
                q_span = max(q_max - q_min, 1.0)
                excess_overshoot = max(q_min - min(q_values), max(q_values) - q_max, 0.0)
                assert excess_overshoot <= max(1.0, 0.08 * q_span)


def test_edge_caps_have_single_streamwise_excursion_without_sawtooth():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    for blade in family["blades"]:
        for loop in blade["loops"]:
            for segment_name in ["leading_edge", "trailing_edge"]:
                s_values = [point[0] for point in loop["segments"][segment_name]["points_s_q"]]
                assert _direction_change_count(s_values) <= 1


def test_edge_caps_default_to_half_local_thickness_sagitta():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    streamwise_metric_scale_mm = _profile_length_mm(defaults["hub_profile_rz_mm"])
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        defaults,
    )

    for blade in family["blades"]:
        for loop in blade["loops"]:
            for segment_name, direction in [("leading_edge", -1.0), ("trailing_edge", 1.0)]:
                points = loop["segments"][segment_name]["points_s_q"]
                local_thickness_mm = abs(points[-1][1] - points[0][1])
                anchor_s = 0.5 * (points[0][0] + points[-1][0])
                if direction < 0.0:
                    sagitta_mm = (anchor_s - min(point[0] for point in points)) * streamwise_metric_scale_mm
                    opposite_bulge_mm = max(point[0] - anchor_s for point in points) * streamwise_metric_scale_mm
                else:
                    sagitta_mm = (max(point[0] for point in points) - anchor_s) * streamwise_metric_scale_mm
                    opposite_bulge_mm = max(anchor_s - point[0] for point in points) * streamwise_metric_scale_mm

                assert sagitta_mm == pytest.approx(0.5 * local_thickness_mm, rel=0.18, abs=0.75)
                assert opposite_bulge_mm <= 1.0e-6


def test_main_loop_centerline_has_smooth_turn_and_spanwise_angle_variation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    blade = next(item for item in family["blades"] if item["blade_class"] == "main")
    hub_loop = blade["loops"][0]
    tip_loop = blade["loops"][-1]

    hub_centerline = _centerline_q_samples(hub_loop)
    tip_centerline = _centerline_q_samples(tip_loop)

    assert hub_centerline[-1] - hub_centerline[0] >= 72.0
    assert tip_centerline[-1] - tip_centerline[0] >= 72.0
    assert all(right > left for left, right in zip(hub_centerline, hub_centerline[1:]))
    assert all(right > left for left, right in zip(tip_centerline, tip_centerline[1:]))
    assert abs(tip_centerline[-1] - hub_centerline[-1]) >= 14.0


def test_edge_caps_use_dense_control_polygons_for_round_leading_and_trailing_edges():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    for blade in family["blades"]:
        for loop in blade["loops"]:
            assert len(loop["segments"]["leading_edge"]["control_points_s_q"]) >= 13
            assert len(loop["segments"]["trailing_edge"]["control_points_s_q"]) >= 13


def test_loop_validator_rejects_insufficient_controls():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = dict(runtime["resolved_blade_to_blade_loop_family_defaults"])
    defaults["segment_control_count_minimums"] = {
        "pressure_side": 20,
        "suction_side": 20,
        "leading_edge": 20,
        "trailing_edge": 20,
    }
    family = build_v11_blade_to_blade_loop_family(runtime["parameters"], defaults)

    failures = validate_v11_loop_family(family)

    assert any(failure["reason"] == "v1_1_loop_control_count_insufficient" for failure in failures)


def test_loop_validator_detects_measured_c2_failure_after_cap_mutation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    broken = copy.deepcopy(family)
    leading = broken["blades"][0]["loops"][0]["segments"]["leading_edge"]["points_s_q"]
    leading[1][1] += 8.0

    failures = validate_v11_loop_family(broken)

    assert any(failure["reason"] == "v1_1_loop_join_c2_failed" for failure in failures)


def _diff(current, previous):
    return [current[0] - previous[0], current[1] - previous[1]]


def _negate(vector):
    return [-vector[0], -vector[1]]


def _vector_angle_deg(left, right):
    left_norm = (left[0] * left[0] + left[1] * left[1]) ** 0.5
    right_norm = (right[0] * right[0] + right[1] * right[1]) ** 0.5
    if left_norm <= 1.0e-12 or right_norm <= 1.0e-12:
        return 0.0
    cosine = (left[0] * right[0] + left[1] * right[1]) / (left_norm * right_norm)
    cosine = max(-1.0, min(1.0, cosine))
    return __import__("math").degrees(__import__("math").acos(cosine))


def _vector_length(vector):
    return (vector[0] * vector[0] + vector[1] * vector[1]) ** 0.5


def _scale_streamwise(vector, streamwise_metric_scale_mm):
    return [vector[0] * streamwise_metric_scale_mm, vector[1]]


def _profile_length_mm(profile):
    return sum(
        ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
        for left, right in zip(profile, profile[1:])
    )


def _direction_change_count(values):
    changes = 0
    previous_sign = 0
    for current, next_value in zip(values, values[1:]):
        delta = next_value - current
        sign = 1 if delta > 1.0e-7 else -1 if delta < -1.0e-7 else 0
        if previous_sign and sign and sign != previous_sign:
            changes += 1
        if sign:
            previous_sign = sign
    return changes


def _centerline_q_samples(loop):
    pressure = loop["segments"]["pressure_side"]["points_s_q"]
    suction = loop["segments"]["suction_side"]["points_s_q"]
    indices = [0, len(pressure) // 4, len(pressure) // 2, (3 * len(pressure)) // 4, len(pressure) - 1]
    return [
        0.5 * (pressure[index][1] + suction[index][1])
        for index in indices
    ]
