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


def test_leading_and_trailing_edges_report_nurbs_cap_intent_and_sagitta():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)
    loop = family["blades"][0]["loops"][0]

    for segment_name in ["leading_edge", "trailing_edge"]:
        segment = loop["segments"][segment_name]
        points = segment["points_s_q"]
        target_sagitta = 0.5 * abs(points[-1][1] - points[0][1])
        resolved_sagitta = _resolved_cap_sagitta_mm(points, loop["streamwise_metric_scale_mm"], segment_name)
        assert segment["canonical_curve"]["kind"] == "nurbs_cap_curve"
        assert segment["canonical_curve"]["sagitta_policy"]["mode"] == "local_thickness_ratio"
        assert segment["canonical_curve"]["target_sagitta_mm"] == pytest.approx(target_sagitta)
        assert segment["canonical_curve"]["resolved_sagitta_mm"] == pytest.approx(resolved_sagitta)
        assert segment["canonical_curve"]["continuity_goal"] == "C2"

    assert loop["metrics"]["leading_cap_sagitta_target_mm"] == pytest.approx(
        loop["segments"]["leading_edge"]["canonical_curve"]["target_sagitta_mm"]
    )
    assert loop["metrics"]["leading_cap_sagitta_resolved_mm"] == pytest.approx(
        loop["segments"]["leading_edge"]["canonical_curve"]["resolved_sagitta_mm"]
    )
    assert loop["metrics"]["trailing_cap_sagitta_target_mm"] == pytest.approx(
        loop["segments"]["trailing_edge"]["canonical_curve"]["target_sagitta_mm"]
    )
    assert loop["metrics"]["trailing_cap_sagitta_resolved_mm"] == pytest.approx(
        loop["segments"]["trailing_edge"]["canonical_curve"]["resolved_sagitta_mm"]
    )


def test_cap_sagitta_metadata_tracks_resolved_geometry_after_cap_override():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": deepcopy(runtime["canonical_nurbs_parameterization"]),
    }
    overrides = {
        "segments": {
            "leading_edge": {
                "control_points": [
                    [0.06, -6.4],
                    [0.045, -4.6],
                    [0.032, -1.8],
                    [0.024, 0.0],
                    [0.032, 1.8],
                    [0.045, 4.6],
                    [0.06, 6.4],
                ]
            }
        }
    }

    family = build_v11_blade_to_blade_loop_family(parameters, defaults, overrides=overrides)
    loop = family["blades"][0]["loops"][0]
    segment = loop["segments"]["leading_edge"]
    resolved_sagitta = _resolved_cap_sagitta_mm(
        segment["points_s_q"],
        loop["streamwise_metric_scale_mm"],
        "leading_edge",
    )

    assert segment["canonical_curve"]["target_sagitta_mm"] == pytest.approx(6.4, abs=1.0e-6)
    assert segment["canonical_curve"]["resolved_sagitta_mm"] == pytest.approx(resolved_sagitta)
    assert segment["canonical_curve"]["resolved_sagitta_mm"] > segment["canonical_curve"]["target_sagitta_mm"]
    assert loop["metrics"]["leading_cap_sagitta_resolved_mm"] == pytest.approx(resolved_sagitta)


def _resolved_cap_sagitta_mm(points, streamwise_metric_scale_mm, segment_name):
    anchor_s = 0.5 * (points[0][0] + points[-1][0])
    if segment_name == "leading_edge":
        return (anchor_s - min(point[0] for point in points)) * streamwise_metric_scale_mm
    return (max(point[0] for point in points) - anchor_s) * streamwise_metric_scale_mm
