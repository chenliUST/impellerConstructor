from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def _runtime(preset_id: str):
    return compile_impeller_runtime_preset(preset_id)


def _defaults(runtime):
    return {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }


def _parameters(runtime):
    return {name: spec["default"] for name, spec in runtime["parameters"].items()}


def _profile_sample(profile, s):
    scaled = max(0.0, min(1.0, float(s))) * (len(profile) - 1)
    left_index = min(int(math.floor(scaled)), len(profile) - 1)
    right_index = min(left_index + 1, len(profile) - 1)
    fraction = scaled - left_index
    return [
        profile[left_index][axis] + fraction * (profile[right_index][axis] - profile[left_index][axis])
        for axis in (0, 1)
    ]


def _support_metrics(defaults, streamwise_interval):
    hub = defaults["hub_profile_rz_mm"]
    tip = defaults["tip_or_shroud_profile_rz_mm"]
    root_offset = float(defaults.get("root_blade_lift_mm", 0.0))
    tip_offset = (
        float(defaults.get("shroud_blade_inset_mm", 0.0))
        if defaults.get("tip_attachment_mode") == "closed_shroud_attachment"
        else 0.0
    )
    angles = []
    active_heights = []
    for index in range(17):
        s = streamwise_interval[0] + index * (streamwise_interval[1] - streamwise_interval[0]) / 16
        hub_point = _profile_sample(hub, s)
        tip_point = _profile_sample(tip, s)
        before = _profile_sample(hub, max(0.0, s - 1.0e-4))
        after = _profile_sample(hub, min(1.0, s + 1.0e-4))
        tangent = [after[0] - before[0], after[1] - before[1]]
        span = [tip_point[0] - hub_point[0], tip_point[1] - hub_point[1]]
        denominator = math.hypot(*tangent) * math.hypot(*span)
        cosine = sum(a * b for a, b in zip(tangent, span)) / denominator
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
        active_heights.append(math.hypot(*span) - root_offset - tip_offset)
    return angles, active_heights


def test_v114_runtime_identity_keeps_canonical_math_version():
    for preset_id in ACTIVE_PRESETS:
        runtime = _runtime(preset_id)
        assert runtime["runtime_release_version"] == "1.1.5"
        assert runtime["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"


def test_first_two_presets_have_reviewable_span_height_and_orientation():
    for preset_id in ACTIVE_PRESETS[:2]:
        runtime = _runtime(preset_id)
        defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
        angles, active_heights = _support_metrics(defaults, defaults["main_streamwise_interval_s"])
        lower, upper = defaults["blade_hub_angle_contract_deg"]
        assert min(angles) >= lower, (preset_id, min(angles))
        assert max(angles) <= upper, (preset_id, max(angles))
        assert min(active_heights) >= defaults["minimum_active_blade_height_mm"], (
            preset_id,
            min(active_heights),
        )
        family = build_v11_blade_to_blade_loop_family(_parameters(runtime), _defaults(runtime))
        assert family["support_profile_contract_metrics"]["status"] == "PASS"


def test_canonical_splitter_tracks_requested_main_passage_fraction():
    runtime = _runtime("radial_open_reference_v1_1")
    defaults = _defaults(runtime)
    family = build_v11_blade_to_blade_loop_family(_parameters(runtime), defaults)
    metrics = family["metrics"]

    assert metrics["splitter_positioning_status"] == "PASS"
    assert metrics["splitter_passage_fraction_min"] >= 0.42
    assert metrics["splitter_passage_fraction_max"] <= 0.58
