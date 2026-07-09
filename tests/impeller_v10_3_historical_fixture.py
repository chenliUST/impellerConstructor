from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import (
    _v10_2_attachment_defaults,
    _v10_3_runtime_defaults,
)
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


_HISTORICAL_V10_3_SECTION_LOOP_DEFAULTS = {
    "main_blade_count": 4,
    "splitter_blade_count": 4,
    "blade_pair_count": 4,
    "average_blade_thickness_mm": 20.0,
    "root_attachment_width_mm": 8.0,
    "root_attachment_lift_mm": 8.0,
    "tip_dome_height_mm": 12.0,
    "main_streamwise_start_u": 0.20,
    "main_streamwise_end_u": 0.80,
    "splitter_streamwise_start_u": 0.48,
    "splitter_streamwise_end_u": 0.76,
    "section_loop_sample_count": 33,
    "face_streamwise_sample_count": 41,
    "root_short_direction_sample_count": 17,
    "tip_dome_short_direction_sample_count": 17,
}

_HISTORICAL_V10_3_PARAMETER_DEFAULTS = {
    "blade_count": 8,
    "inlet_radius_mm": 126.0,
    "exit_radius_mm": 600.0,
    "blade_thickness_mm": 20.0,
}


def historical_v10_3_open_runtime() -> dict[str, object]:
    bundle = load_impeller_dsl_bundle("v1_0")
    preset = copy.deepcopy(bundle.presets["radial_open_reference_v1_0"])
    constructor = copy.deepcopy(bundle.constructors[preset["constructor_id"]])
    export_contract = bundle.export_contracts["section_loop_blade_root_blend_surface_graph"]
    runtime = dict(compile_impeller_runtime_preset("radial_open_reference_v1_0"))

    preset["parameter_values"].update(_HISTORICAL_V10_3_PARAMETER_DEFAULTS)
    preset["geometry_patch_version"] = "1.0.3"
    preset["transition_geometry_status"] = "topology_first_section_loop_blade_root_blend_surface_graph"
    preset["v1_0_3_section_loop_defaults"] = dict(_HISTORICAL_V10_3_SECTION_LOOP_DEFAULTS)

    runtime.update(
        _v10_3_runtime_defaults(
            preset,
            preset["parameter_values"],
            constructor,
            export_contract,
        )
    )
    runtime["resolved_attachment_defaults"] = _v10_2_attachment_defaults(
        preset["parameter_values"],
        constructor,
    )
    for name, value in _HISTORICAL_V10_3_PARAMETER_DEFAULTS.items():
        if name in runtime["parameters"]:
            runtime["parameters"][name]["default"] = value
    runtime.pop("v1_0_4_preset_contract", None)
    return runtime
