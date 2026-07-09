from __future__ import annotations

import sys
from pathlib import Path

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
    assert canonical["section_loop_family"]["mode"] == "skeleton_thickness_caps"
    assert canonical["section_loop_family"]["segments"]["leading_edge_cap"]["kind"] == "nurbs_cap_curve"
    assert canonical["metrics"]["support_profile_control_count"]["hub_profile"] == 6
    assert canonical["metrics"]["thickness_min_mm"] > 0.0
