from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


ACTIVE_V11_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def test_all_active_v11_presets_compile_to_v112_canonical_payloads():
    for preset_id in ACTIVE_V11_PRESETS:
        runtime = compile_impeller_runtime_preset(preset_id)
        canonical = runtime["canonical_nurbs_parameterization"]

        assert runtime["geometry_version"] == "1.1"
        assert runtime["geometry_patch_version"] == "1.1.2"
        assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
        assert runtime["canonical_input_source"] == "translated_from_legacy_v1_1"
        assert canonical["canonical_payload_version"] == "1.1.2"
        assert canonical["blade_population"]["main_blade_count"] > 0
        assert canonical["blade_population"]["main_blade_count"] + canonical["blade_population"]["splitter_blade_count"] == runtime["parameters"]["blade_count"]["default"]
        assert canonical["section_loop_family"]["mode"] == "skeleton_thickness_caps"


def test_open_and_closed_translation_preserve_topology_modes():
    open_runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    closed_runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")

    assert open_runtime["canonical_nurbs_parameterization"]["attachment_policy"]["open_tip"]["enabled_when"] == "open"
    assert closed_runtime["canonical_nurbs_parameterization"]["attachment_policy"]["tip_to_shroud"]["enabled_when"] == "closed"
    assert closed_runtime["canonical_nurbs_parameterization"]["blade_population"]["splitter_blade_count"] == 0
