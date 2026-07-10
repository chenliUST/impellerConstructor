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
from part_rule_synthesis.impeller_v11_2_canonical import (
    canonical_nurbs_from_v11_defaults,
    clamped_uniform_knots,
    evaluate_nurbs_curve,
    evaluate_nurbs_surface,
)
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def _runtime(preset_id: str = "radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    return parameters, defaults


def test_clamped_uniform_knots_match_cubic_nurbs_contract():
    assert clamped_uniform_knots(6, 3) == [0.0, 0.0, 0.0, 0.0, 0.333333, 0.666667, 1.0, 1.0, 1.0, 1.0]


def test_evaluate_nurbs_curve_uses_control_points_and_weights():
    curve = {
        "kind": "nurbs_curve",
        "degree": 1,
        "control_points": [[0.0, 0.0], [10.0, 20.0]],
        "weights": [1.0, 1.0],
        "knots": [0.0, 0.0, 1.0, 1.0],
    }

    assert evaluate_nurbs_curve(curve, 0.0) == [0.0, 0.0]
    assert evaluate_nurbs_curve(curve, 0.5) == [5.0, 10.0]
    assert evaluate_nurbs_curve(curve, 1.0) == [10.0, 20.0]


def test_evaluate_nurbs_surface_bilinear_degree_one_field():
    surface = {
        "kind": "nurbs_surface",
        "degree_u": 1,
        "degree_v": 1,
        "control_points": [
            [[0.0, 0.0, 0.0], [0.0, 1.0, 10.0]],
            [[1.0, 0.0, 20.0], [1.0, 1.0, 30.0]],
        ],
        "weights": [[1.0, 1.0], [1.0, 1.0]],
        "knots_u": [0.0, 0.0, 1.0, 1.0],
        "knots_v": [0.0, 0.0, 1.0, 1.0],
    }

    assert evaluate_nurbs_surface(surface, 0.5, 0.5) == [0.5, 0.5, 15.0]


def test_v11_defaults_translate_to_canonical_nurbs_payload():
    parameters, defaults = _runtime()
    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)

    assert canonical["canonical_payload_version"] == "1.1.2"
    assert canonical["canonical_input_source"] == "translated_from_legacy_v1_1"
    assert canonical["support_profiles"]["hub_profile"]["kind"] == "nurbs_curve"
    assert canonical["support_profiles"]["tip_or_shroud_profile"]["kind"] == "nurbs_curve"
    assert canonical["blade_population"]["main_blade_count"] == 8
    assert canonical["blade_population"]["splitter_blade_count"] == 8
    assert canonical["blade_skeleton_field"]["kind"] == "nurbs_surface"
    assert canonical["thickness_field"]["kind"] == "nurbs_surface"
    assert canonical["blade_skeleton_field"]["weights"] == [
        [1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0],
    ]
    assert canonical["section_loop_family"]["mode"] == "skeleton_thickness_caps"
    assert canonical["section_loop_family"]["segments"]["leading_edge_cap"]["kind"] == "nurbs_cap_curve"
    assert canonical["metrics"]["support_profile_control_count"]["hub_profile"] == 6
    assert canonical["metrics"]["thickness_min_mm"] > 0.0


def test_thickness_field_uses_translated_main_streamwise_interval():
    parameters, defaults = _runtime()
    defaults["main_streamwise_interval_s"] = [0.11, 0.81]

    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)
    thickness_field = canonical["thickness_field"]
    thickness_s_values = [point[0] for row in thickness_field["control_points"] for point in row]
    unique_s_values = [row[0][0] for row in thickness_field["control_points"]]

    assert all(0.11 <= s_value <= 0.81 for s_value in thickness_s_values)
    assert unique_s_values == [0.11, 0.306, 0.544, 0.81]


def test_emitted_canonical_surfaces_are_directly_evaluable():
    parameters, defaults = _runtime()
    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)

    skeleton_sample = evaluate_nurbs_surface(canonical["blade_skeleton_field"], 0.5, 0.5)
    thickness_sample = evaluate_nurbs_surface(canonical["thickness_field"], 0.5, 0.5)

    assert skeleton_sample[0] == pytest.approx(0.5, abs=0.08)
    assert skeleton_sample[1] == pytest.approx(0.5, abs=1.0e-6)
    assert abs(skeleton_sample[2]) > 1.0
    assert thickness_sample[0] == pytest.approx(0.5, abs=0.08)
    assert thickness_sample[1] == pytest.approx(0.5, abs=1.0e-6)
    assert thickness_sample[2] > 0.0


def test_loop_builder_samples_canonical_fields_with_streamwise_u_and_span_v_axes():
    parameters, defaults = _runtime()
    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)
    canonical["blade_population"]["main_blade_count"] = 2
    canonical["blade_population"]["splitter_blade_count"] = 0
    canonical["section_loop_family"]["span_stations_h"] = [0.0, 1.0]
    canonical["blade_skeleton_field"] = _axis_probe_surface(lambda s, h: 100.0 * s + 10.0 * h)
    canonical["thickness_field"] = _axis_probe_surface(lambda _s, _h: 10.0)
    test_defaults = {
        **deepcopy(defaults),
        "canonical_nurbs_parameterization": canonical,
        "side_sample_count": 5,
        "edge_cap_sample_count": 7,
        "segment_control_counts": {
            "pressure_side": 5,
            "suction_side": 5,
            "leading_edge": 7,
            "trailing_edge": 7,
        },
        "main_blade_count": 2,
        "splitter_blade_count": 0,
    }
    test_parameters = {**parameters, "blade_count": 2}

    family = build_v11_blade_to_blade_loop_family(test_parameters, test_defaults)
    root_pressure = family["blades"][0]["loops"][0]["segments"]["pressure_side"]["points_s_q"]
    tip_pressure = family["blades"][0]["loops"][1]["segments"]["pressure_side"]["points_s_q"]

    assert tip_pressure[0][1] - root_pressure[0][1] == pytest.approx(10.0)
    assert root_pressure[-1][1] - root_pressure[0][1] == pytest.approx(100.0)


def _axis_probe_surface(q_value):
    s_values = [0.0, 0.333333, 0.666667, 1.0]
    h_values = [0.0, 0.5, 1.0]
    return {
        "kind": "nurbs_surface",
        "coordinate_system": "s_h_q_mm",
        "degree_u": 3,
        "degree_v": 2,
        "control_points": [
            [[s, h, q_value(s, h)] for h in h_values]
            for s in s_values
        ],
        "weights": [[1.0 for _ in h_values] for _ in s_values],
        "knots_u": clamped_uniform_knots(4, 3),
        "knots_v": clamped_uniform_knots(3, 2),
    }
