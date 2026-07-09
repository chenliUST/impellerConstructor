from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def _runtime(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    return runtime, parameters


def test_active_span_policy_offsets_root_loop_from_hub_support():
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    defaults = {**defaults, "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"]}
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_root_offset_max_mm"] >= metrics["resolved_root_offset_min_mm"]
    assert metrics["resolved_tip_offset_max_mm"] == 0.0
    assert family["blades"][0]["loops"][0]["h"] == 0.0
    assert family["blades"][0]["loops"][0]["active_span_fraction"] > 0.0


def test_closed_active_span_policy_offsets_tip_from_shroud_support():
    runtime, parameters = _runtime("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    defaults = {**defaults, "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"]}
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_tip_offset_min_mm"] > 0.0
    assert metrics["offset_feasibility_status"] == "PASS"
