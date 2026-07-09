from __future__ import annotations

import copy
import math
import sys
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (
    build_v11_blade_to_blade_loop_family,
    map_v11_domain_sample,
)
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


def test_main_and_splitter_share_domain_with_different_s_interval_and_phase():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        defaults,
    )

    main = next(blade for blade in family["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in family["blades"] if blade["blade_class"] == "splitter")

    assert main["domain_id"] == splitter["domain_id"] == "v1_1_blade_to_blade_s_q_domain"
    assert main["streamwise_interval_s"] == defaults["main_streamwise_interval_s"]
    assert splitter["streamwise_interval_s"] == defaults["splitter_streamwise_interval_s"]
    assert splitter["phase_offset_pitch"] == defaults["splitter_phase_offset_pitch"]
    assert len([blade for blade in family["blades"] if blade["blade_class"] == "main"]) == defaults["main_blade_count"]
    assert len([blade for blade in family["blades"] if blade["blade_class"] == "splitter"]) == defaults["splitter_blade_count"]


def test_splitter_half_pitch_phase_is_reflected_in_mapped_points():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = runtime["parameters"]
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    main = next(blade for blade in family["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in family["blades"] if blade["blade_class"] == "splitter")
    main_loop = main["loops"][2]
    main_point_s_q = main_loop["segments"]["pressure_side"]["points_s_q"][24]

    main_point = map_v11_domain_sample(
        parameters,
        defaults,
        {"s": main_point_s_q[0], "q": main_point_s_q[1], "h": main_loop["h"], "phase_offset_pitch": 0.0},
    )
    splitter_point = map_v11_domain_sample(
        parameters,
        defaults,
        {
            "s": main_point_s_q[0],
            "q": main_point_s_q[1],
            "h": main_loop["h"],
            "phase_offset_pitch": splitter["phase_offset_pitch"],
        },
    )

    main_theta = math.atan2(main_point[1], main_point[0])
    splitter_theta = math.atan2(splitter_point[1], splitter_point[0])
    theta_delta = abs((splitter_theta - main_theta + math.pi) % (2.0 * math.pi) - math.pi)
    expected_theta_delta = defaults["splitter_phase_offset_pitch"] * (2.0 * math.pi / defaults["main_blade_count"])

    assert theta_delta == pytest.approx(expected_theta_delta, abs=0.03)


def test_splitter_centerline_bisects_adjacent_main_passage_across_span():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = runtime["parameters"]
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    main = next(blade for blade in family["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in family["blades"] if blade["blade_class"] == "splitter")
    all_fractions = []
    for main_loop, splitter_loop in zip(main["loops"], splitter["loops"]):
        main_centerline = _centerline_points(main_loop)
        splitter_centerline = _centerline_points(splitter_loop)
        for splitter_point in splitter_centerline:
            passage_fraction = _splitter_passage_fraction(
                defaults,
                main_centerline,
                splitter_point,
                h=splitter_loop["h"],
                phase_offset_pitch=splitter["phase_offset_pitch"],
            )
            all_fractions.append(passage_fraction)

    assert min(all_fractions) >= 0.45
    assert max(all_fractions) <= 0.55
    assert sum(all_fractions) / len(all_fractions) == pytest.approx(0.5, abs=0.02)
    assert family["metrics"]["splitter_passage_fraction_min"] >= 0.45
    assert family["metrics"]["splitter_passage_fraction_max"] <= 0.55


def test_main_blade_passages_cover_full_360_degrees():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = runtime["parameters"]
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    main_blades = [blade for blade in family["blades"] if blade["blade_class"] == "main"]
    sample = {
        "s": 0.5,
        "q": 0.0,
        "h": 0.5,
    }
    reference = map_v11_domain_sample(parameters, defaults, {**sample, "phase_offset_pitch": 0.0})
    reference_theta = math.atan2(reference[1], reference[0])
    theta_offsets = []
    for blade in main_blades:
        point = map_v11_domain_sample(
            parameters,
            defaults,
            {**sample, "phase_offset_pitch": float(blade["blade_pair_index"])},
        )
        theta = math.atan2(point[1], point[0])
        theta_offsets.append((theta - reference_theta + 2.0 * math.pi) % (2.0 * math.pi))

    theta_offsets = sorted(theta_offsets)
    blade_pitch_rad = 2.0 * math.pi / defaults["main_blade_count"]

    assert theta_offsets == pytest.approx(
        [index * blade_pitch_rad for index in range(defaults["main_blade_count"])],
        abs=0.03,
    )


def test_loop_validation_rejects_splitter_phase_offset_pitch_mutation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    splitter = next(blade for blade in broken["blades"] if blade["blade_class"] == "splitter")
    splitter["phase_offset_pitch"] = 0.42

    failures = validate_v11_loop_family(broken)

    assert any(
        failure["reason"] == "v1_1_main_splitter_phase_failed" for failure in failures
    )


@pytest.mark.parametrize(
    "domain_map,description",
    [
        (lambda sample: sample, "callable"),
        ({"kind": "wrong_kind"}, "malformed"),
    ],
)
def test_loop_validation_rejects_invalid_domain_map(domain_map, description):
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    broken["domain_map"] = domain_map

    failures = validate_v11_loop_family(broken)

    assert any(
        failure["reason"] == "v1_1_loop_orientation_failed" for failure in failures
    ), description


@pytest.mark.parametrize(
    "field,value,description",
    [
        ("q_units", "degrees", "q units mutation"),
        ("phase_offset_pitch_units", "radians", "phase offset pitch units mutation"),
    ],
)
def test_loop_validation_rejects_invalid_domain_map_units(field, value, description):
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    broken["domain_map"][field] = value

    failures = validate_v11_loop_family(broken)

    assert any(
        failure["reason"] == "v1_1_loop_orientation_failed" for failure in failures
    ), description


def test_loop_validation_rejects_streamwise_interval_mutation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    main = next(blade for blade in broken["blades"] if blade["blade_class"] == "main")
    main["streamwise_interval_s"] = [0.1, 0.9]

    failures = validate_v11_loop_family(broken)

    assert any(failure["reason"] == "v1_1_loop_station_knot_mismatch" for failure in failures)


def test_loop_validation_rejects_malformed_domain_map_sample_keys():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    broken["domain_map"]["sample_keys"] = ["s", "q", "h"]

    failures = validate_v11_loop_family(broken)

    assert any(
        failure["reason"] == "v1_1_loop_orientation_failed"
        and failure.get("component") == "domain_map"
        and failure.get("field") == "sample_keys"
        for failure in failures
    )


def test_loop_validation_rejects_splitter_streamwise_interval_mutation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    broken = copy.deepcopy(family)

    splitter = next(blade for blade in broken["blades"] if blade["blade_class"] == "splitter")
    splitter["streamwise_interval_s"] = [0.1, 0.99]

    failures = validate_v11_loop_family(broken)

    assert any(
        failure["reason"] == "v1_1_loop_station_knot_mismatch"
        and failure.get("blade_class") == "splitter"
        and failure.get("streamwise_interval_s") == [0.1, 0.99]
        for failure in failures
    )


def test_closed_v111_loop_family_accepts_zero_splitters():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")

    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    classes = Counter(blade["blade_class"] for blade in family["blades"])

    assert family["status"] == "PASS"
    assert classes == {"main": 12}
    assert family["metrics"]["blade_count"] == 12
    assert family["metrics"]["splitter_positioning_status"] == "NOT_APPLICABLE"
    assert family["metrics"]["splitter_passage_fraction_min"] is None
    assert family["metrics"]["splitter_passage_fraction_max"] is None
    assert family["metrics"]["splitter_passage_fraction_avg"] is None
    assert validate_v11_loop_family(family) == []


def _centerline_points(loop):
    pressure = loop["segments"]["pressure_side"]["points_s_q"]
    suction = loop["segments"]["suction_side"]["points_s_q"]
    return [
        [0.5 * (pressure_point[0] + suction_point[0]), 0.5 * (pressure_point[1] + suction_point[1])]
        for pressure_point, suction_point in zip(pressure, suction)
    ]


def _splitter_passage_fraction(defaults, main_centerline, splitter_point, *, h, phase_offset_pitch):
    s_value, splitter_q = splitter_point
    main_q = _interpolate_q(main_centerline, s_value)
    radius_mm = _effective_radius_mm(defaults, s_value, h)
    blade_pitch_rad = 2.0 * math.pi / defaults["main_blade_count"]
    pitch_arc_mm = radius_mm * blade_pitch_rad
    return phase_offset_pitch + (splitter_q - main_q) / pitch_arc_mm


def _interpolate_q(points, s_value):
    for left, right in zip(points, points[1:]):
        if left[0] <= s_value <= right[0]:
            fraction = 0.0 if right[0] == left[0] else (s_value - left[0]) / (right[0] - left[0])
            return left[1] + (right[1] - left[1]) * fraction
    return points[0][1] if s_value < points[0][0] else points[-1][1]


def _effective_radius_mm(defaults, s_value, h):
    hub_r, hub_z = _profile_sample(defaults["hub_profile_rz_mm"], s_value)
    tip_r, tip_z = _profile_sample(defaults["tip_or_shroud_profile_rz_mm"], s_value)
    span_length_mm = math.hypot(tip_r - hub_r, tip_z - hub_z)
    root_fraction = 0.0
    if span_length_mm > 1.0e-9:
        root_fraction = max(0.0, min(0.45, defaults.get("root_blade_lift_mm", 0.0) / span_length_mm))
    effective_h = root_fraction + h * max(0.0, 1.0 - root_fraction)
    return hub_r + (tip_r - hub_r) * effective_h


def _profile_sample(profile, s_value):
    clamped_s = max(0.0, min(1.0, float(s_value)))
    scaled = clamped_s * (len(profile) - 1)
    left_index = min(int(math.floor(scaled)), len(profile) - 1)
    right_index = min(left_index + 1, len(profile) - 1)
    fraction = scaled - left_index
    left = profile[left_index]
    right = profile[right_index]
    return [
        left[0] + (right[0] - left[0]) * fraction,
        left[1] + (right[1] - left[1]) * fraction,
    ]
