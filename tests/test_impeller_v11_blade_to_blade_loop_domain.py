from __future__ import annotations

import copy
import json
import math
import sys
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


def _runtime_defaults():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    return runtime["parameters"], runtime["resolved_blade_to_blade_loop_family_defaults"]


def test_v11_loop_family_uses_five_span_stations_and_named_segments():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    assert family["status"] == "PASS"
    assert family["coordinate_system"] == "blade_to_blade_s_q_mm"
    assert family["span_stations_h"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert family["metrics"]["loop_station_count"] == 5

    first_loop = family["blades"][0]["loops"][0]
    assert set(first_loop["segments"]) == {
        "pressure_side",
        "suction_side",
        "leading_edge",
        "trailing_edge",
    }
    json.dumps(family)


def test_v11_loop_maps_q_to_theta_offset_in_millimeters():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    p0 = map_v11_domain_sample(parameters, defaults, {"s": 0.5, "q": 0.0, "h": 0.5, "phase_offset_pitch": 0.0})
    p1 = map_v11_domain_sample(parameters, defaults, {"s": 0.5, "q": 20.0, "h": 0.5, "phase_offset_pitch": 0.0})

    r0 = math.hypot(p0[0], p0[1])
    observed_arc = r0 * abs(math.atan2(p1[1], p1[0]) - math.atan2(p0[1], p0[0]))
    assert observed_arc == pytest.approx(20.0, abs=0.35)


def test_v11_edge_caps_stay_inside_local_streamwise_domain():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    for blade in family["blades"]:
        start_s, end_s = blade["streamwise_interval_s"]
        for loop in blade["loops"]:
            leading_s = [point[0] for point in loop["segments"]["leading_edge"]["points_s_q"]]
            trailing_s = [point[0] for point in loop["segments"]["trailing_edge"]["points_s_q"]]

            assert min(leading_s) >= max(0.0, start_s - 0.06)
            assert max(trailing_s) <= min(1.0, end_s + 0.06)


def test_loop_validation_rejects_span_station_mutation():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    broken = copy.deepcopy(family)
    broken["span_stations_h"] = [0.0, 0.5, 0.75, 1.0]

    failures = validate_v11_loop_family(broken)

    assert any(failure["reason"] == "v1_1_loop_station_knot_mismatch" for failure in failures)


@pytest.mark.parametrize(
    "segment_name",
    ["pressure_side", "suction_side", "leading_edge", "trailing_edge"],
)
def test_v11_frontend_segment_control_point_override_changes_loop_samples_without_breaking_join_status(segment_name):
    parameters, defaults = _runtime_defaults()
    baseline = build_v11_blade_to_blade_loop_family(parameters, defaults)
    segment_control_points = copy.deepcopy(
        baseline["blades"][0]["loops"][0]["segments"][segment_name]["control_points_s_q"]
    )
    segment_control_points[len(segment_control_points) // 2][1] += 6.0
    override = {
        "blade_to_blade_loop_family": {
            "segments": {
                segment_name: {
                    "control_points": segment_control_points
                }
            }
        }
    }

    overridden = build_v11_blade_to_blade_loop_family(parameters, defaults, overrides=override)
    failures = validate_v11_loop_family(overridden)

    baseline_loop = baseline["blades"][0]["loops"][0]
    overridden_loop = overridden["blades"][0]["loops"][0]

    if segment_name in {"pressure_side", "suction_side"}:
        assert {failure["reason"] for failure in failures} == {"v1_1_main_splitter_passage_collision"}
    else:
        assert failures == []
    assert overridden_loop["metrics"]["join_status"] == "PASS"
    assert overridden_loop["segments"][segment_name]["points_s_q"] != baseline_loop["segments"][segment_name]["points_s_q"]
    assert overridden_loop["segments"][segment_name]["points_xyz"] != baseline_loop["segments"][segment_name]["points_xyz"]


def test_zero_splitter_defaults_reject_negative_splitter_count():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = dict(runtime["resolved_blade_to_blade_loop_family_defaults"])
    defaults["splitter_blade_count"] = -1

    with pytest.raises(ValueError, match="splitter_blade_count must be zero or positive"):
        build_v11_blade_to_blade_loop_family(runtime["parameters"], defaults)
