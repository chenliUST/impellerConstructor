from __future__ import annotations

import sys
from pathlib import Path

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
        assert segment["canonical_curve"]["kind"] == "nurbs_cap_curve"
        assert segment["canonical_curve"]["sagitta_policy"]["mode"] == "local_thickness_ratio"
        assert segment["canonical_curve"]["resolved_sagitta_mm"] > 0.0
        assert segment["canonical_curve"]["continuity_goal"] == "C2"

    assert loop["metrics"]["leading_cap_sagitta_resolved_mm"] > 0.0
    assert loop["metrics"]["trailing_cap_sagitta_resolved_mm"] > 0.0
