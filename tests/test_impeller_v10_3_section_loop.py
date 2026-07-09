from __future__ import annotations

import sys
from pathlib import Path
import math

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_section_loop import (
    _join_status,
    _material_side_sign,
    build_section_loop_lattice,
)
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters

SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
JOIN_KEYS = [
    "pressure_to_leading",
    "leading_to_suction",
    "suction_to_trailing",
    "trailing_to_pressure",
]


def _defaults() -> dict:
    return {
        "main_blade_count": 4,
        "splitter_blade_count": 4,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 33,
        "face_streamwise_sample_count": 41,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
    }


def _vector_angle_deg(left: list[float], right: list[float]) -> float:
    left_length = math.sqrt(sum(value * value for value in left))
    right_length = math.sqrt(sum(value * value for value in right))
    dot = sum(a * b for a, b in zip(left, right)) / (left_length * right_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _subtract(left: list[float], right: list[float]) -> list[float]:
    return [left[index] - right[index] for index in range(3)]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _scale(vector: list[float], scalar: float) -> list[float]:
    return [value * scalar for value in vector]


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _normalized(vector: list[float]) -> list[float]:
    length = _length(vector)
    return [value / length for value in vector]


def _normal_component(curvature: list[float], tangent: list[float]) -> list[float]:
    unit_tangent = _normalized(tangent)
    return _subtract(curvature, _scale(unit_tangent, _dot(curvature, unit_tangent)))


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _measured_max_join_tangent_angle(loop: dict) -> float:
    segments = loop["segments"]
    angles = []
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left_points = segments[left_name]["points"]
        right_points = segments[right_name]["points"]
        incoming = _subtract(left_points[-1], left_points[-2])
        outgoing = _subtract(right_points[1], right_points[0])
        angles.append(_vector_angle_deg(incoming, outgoing))
    return max(angles)


def _measured_max_join_frame_normal_angle(loop: dict) -> float:
    segments = loop["segments"]
    angles = []
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left_normal = segments[left_name]["endpoint_frames"]["end"]["curvature_normal"]
        right_normal = segments[right_name]["endpoint_frames"]["start"]["curvature_normal"]
        angles.append(_vector_angle_deg(left_normal, right_normal))
    return max(angles)


def _max_frame_tangent_rotation_normal_angle(loop: dict) -> float:
    segments = loop["segments"]
    angles = []
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left_tangent = segments[left_name]["endpoint_frames"]["end"]["tangent"]
        right_tangent = segments[right_name]["endpoint_frames"]["start"]["tangent"]
        left_rotated = [-left_tangent[1], left_tangent[0], left_tangent[2]]
        right_rotated = [-right_tangent[1], right_tangent[0], right_tangent[2]]
        angles.append(_vector_angle_deg(left_rotated, right_rotated))
    return max(angles)


def test_section_loop_lattice_builds_main_and_splitter_blades():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())

    assert lattice["status"] == "PASS"
    assert lattice["join_failure_count"] == 0
    blades = lattice["blades"]
    assert len([blade for blade in blades if blade["blade_class"] == "main"]) == 4
    assert len([blade for blade in blades if blade["blade_class"] == "splitter"]) == 4
    assert all(blade["section_loops"] for blade in blades)


def test_section_loop_has_exactly_shared_segment_endpoints():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    segments = loop["segments"]

    assert segments["pressure_side"]["points"][-1] == segments["leading_edge"]["points"][0]
    assert segments["leading_edge"]["points"][-1] == segments["suction_side"]["points"][0]
    assert segments["suction_side"]["points"][-1] == segments["trailing_edge"]["points"][0]
    assert segments["trailing_edge"]["points"][-1] == segments["pressure_side"]["points"][0]


def test_section_loop_reports_metadata_for_downstream_surface_tasks():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    blade = lattice["blades"][0]
    loop = blade["section_loops"][0]

    assert {
        "blade_class",
        "blade_pair_index",
        "passage_index",
        "streamwise_start_u",
        "streamwise_end_u",
        "section_loop_family_id",
    } <= set(blade)
    assert blade["passage_index"] == blade["blade_pair_index"]
    assert blade["section_loop_family_id"] == "v1_0_3_default_section_loop_family"
    assert loop["section_loop_family_id"] == "v1_0_3_default_section_loop_family"
    assert isinstance(blade["theta_rad"], float)
    assert loop["segment_order"] == SEGMENT_ORDER
    assert loop["closed_loop_points"][0] == loop["closed_loop_points"][-1]
    assert loop["closed_loop_points"][0] == loop["segments"]["pressure_side"]["points"][0]


def test_section_loop_source_fields_include_coordinate_frame_and_shared_vertices():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    frame = loop["coordinate_frame"]
    vertices = loop["shared_vertices"]
    segments = loop["segments"]

    assert {
        "origin",
        "camber_tangent",
        "span_tangent",
        "thickness_direction",
        "material_normal",
    } <= set(frame)
    assert {"pressure_leading", "leading_suction", "suction_trailing", "trailing_pressure"} <= set(vertices)
    assert vertices["pressure_leading"] == segments["pressure_side"]["points"][-1]
    assert vertices["leading_suction"] == segments["leading_edge"]["points"][-1]
    assert vertices["suction_trailing"] == segments["suction_side"]["points"][-1]
    assert vertices["trailing_pressure"] == segments["trailing_edge"]["points"][-1]
    for vector_name in ["camber_tangent", "span_tangent", "thickness_direction", "material_normal"]:
        assert _length(frame[vector_name]) > 0.0


def test_segments_include_review_grade_curve_metadata_and_endpoint_frames():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]

    for segment_name in SEGMENT_ORDER:
        segment = loop["segments"][segment_name]
        assert segment["degree"] >= 3
        assert segment["control_point_count"] >= 5
        assert segment["control_point_count"] == len(segment["control_points"])
        assert segment["control_point_semantics"] == "review_grade_cubic_hermite_control_polygon"
        assert len(segment["weights"]) == segment["control_point_count"]
        assert len(segment["knots"]) >= segment["control_point_count"] + segment["degree"] + 1
        assert segment["sample_count"] == len(segment["points"])
        assert segment["sample_count"] >= 17
        assert set(segment["endpoint_frames"]) == {"start", "end"}
        for endpoint in ["start", "end"]:
            frame = segment["endpoint_frames"][endpoint]
            assert set(frame) >= {"point", "tangent", "curvature_normal"}
            assert _length(frame["tangent"]) > 0.0
            assert _length(frame["curvature_normal"]) > 0.0


def test_join_metrics_expose_full_spec_gates_for_defaults():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    metrics = loop["metrics"]
    join_metrics = loop["join_metrics"]

    assert list(join_metrics) == JOIN_KEYS
    assert metrics["join_status"] == "PASS"
    assert metrics["failure_reason"] is None
    for join_name in JOIN_KEYS:
        join = join_metrics[join_name]
        assert {
            "position_gap_mm",
            "tangent_angle_deg",
            "normal_angle_deg",
            "curvature_proxy_mismatch",
            "material_side_sign",
        } <= set(join)
        assert join["position_gap_mm"] <= 1.0e-6
        assert join["tangent_angle_deg"] <= 5.0
        assert join["normal_angle_deg"] <= 8.0
        assert join["curvature_proxy_mismatch"] <= metrics["curvature_proxy_mismatch_tolerance"]
        assert join["material_side_sign"] > 0.0


def test_material_side_sign_is_signed_and_gate_rejects_flipped_side():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    material_normal = loop["coordinate_frame"]["material_normal"]
    join = loop["join_metrics"]["pressure_to_leading"]
    tangent = loop["segments"]["pressure_side"]["endpoint_frames"]["end"]["tangent"]
    curvature_normal = loop["segments"]["leading_edge"]["endpoint_frames"]["start"]["curvature_normal"]
    flipped_curvature_normal = [-value for value in curvature_normal]

    assert _material_side_sign(tangent, curvature_normal, material_normal) == join["material_side_sign"]
    assert _material_side_sign(tangent, flipped_curvature_normal, material_normal) < 0.0

    flipped_join_metrics = {
        name: dict(values)
        for name, values in loop["join_metrics"].items()
    }
    flipped_join_metrics["pressure_to_leading"]["material_side_sign"] = _material_side_sign(
        tangent,
        flipped_curvature_normal,
        material_normal,
    )

    status = _join_status(flipped_join_metrics, [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])

    assert status["status"] == "FAIL"
    assert status["failure_reason"] == "v1_0_3_section_loop_material_side_ambiguous"


def test_leading_and_trailing_segments_are_more_curved_than_pressure_suction():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    metrics = lattice["blades"][0]["section_loops"][0]["metrics"]

    assert metrics["leading_edge_curvature_proxy_mm"] > metrics["pressure_side_curvature_proxy_mm"]
    assert metrics["trailing_edge_curvature_proxy_mm"] > metrics["suction_side_curvature_proxy_mm"]
    assert metrics["foldover_count"] == 0
    assert metrics["max_join_tangent_angle_deg"] <= 5.0
    assert metrics["max_join_normal_angle_deg"] <= 8.0


def test_reported_join_tangent_metric_bounds_independent_sample_measurement():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    measured = _measured_max_join_tangent_angle(loop)

    assert loop["metrics"]["max_join_tangent_angle_deg"] >= measured
    assert loop["metrics"]["max_join_tangent_angle_deg"] <= 5.0


def test_reported_join_normal_metric_uses_independent_curvature_proxy():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    measured = _measured_max_join_frame_normal_angle(loop)
    tangent_rotation_proxy = _max_frame_tangent_rotation_normal_angle(loop)

    assert loop["metrics"]["max_join_normal_angle_deg"] >= measured
    assert loop["metrics"]["max_join_normal_angle_deg"] != loop["metrics"]["max_join_tangent_angle_deg"]
    assert loop["metrics"]["max_join_normal_angle_deg"] != tangent_rotation_proxy
    assert loop["metrics"]["max_join_normal_angle_deg"] <= 8.0


def test_splitter_streamwise_extent_is_shorter_than_main():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    main = next(blade for blade in lattice["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in lattice["blades"] if blade["blade_class"] == "splitter")

    assert main["streamwise_start_u"] < splitter["streamwise_start_u"]
    assert main["streamwise_end_u"] > splitter["streamwise_end_u"]


def test_invalid_section_loop_inputs_fail_with_reason():
    defaults = _defaults()
    defaults["average_blade_thickness_mm"] = -1.0

    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)

    assert lattice["status"] == "FAIL"
    assert "average_blade_thickness_mm" in lattice["failure_reason"]


def test_missing_required_section_loop_default_fails_with_reason():
    defaults = _defaults()
    defaults.pop("section_loop_sample_count")

    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)

    assert lattice["status"] == "FAIL"
    assert "section_loop_sample_count" in lattice["failure_reason"]


def test_parameter_override_satisfies_missing_default_without_key_error():
    defaults = _defaults()
    defaults.pop("section_loop_sample_count")

    lattice = build_section_loop_lattice(
        parameters={"section_loop_sample_count": 33},
        defaults=defaults,
    )

    assert lattice["status"] == "PASS"
    assert lattice["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["sample_count"] == 33


def test_runtime_bound_canonical_blade_count_derives_half_passage_section_counts():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    bound = _bind_parameters(runtime, {"blade_count": 10})

    lattice = build_section_loop_lattice(
        parameters=bound,
        defaults=runtime["resolved_section_loop_defaults"],
    )

    assert lattice["status"] == "PASS"
    assert len([blade for blade in lattice["blades"] if blade["blade_class"] == "main"]) == 5
    assert len([blade for blade in lattice["blades"] if blade["blade_class"] == "splitter"]) == 5


def test_canonical_blade_count_accepts_consistent_user_edited_section_counts():
    lattice = build_section_loop_lattice(
        parameters={
            "blade_count": 10,
            "main_blade_count": 5,
            "splitter_blade_count": 5,
        },
        defaults=_defaults(),
    )

    assert lattice["status"] == "PASS"
    assert len([blade for blade in lattice["blades"] if blade["blade_class"] == "main"]) == 5
    assert len([blade for blade in lattice["blades"] if blade["blade_class"] == "splitter"]) == 5


def test_canonical_blade_count_rejects_odd_half_passage_count():
    lattice = build_section_loop_lattice(
        parameters={"blade_count": 9},
        defaults=_defaults(),
    )

    assert lattice["status"] == "FAIL"
    assert "blade_count" in lattice["failure_reason"]
    assert "even" in lattice["failure_reason"]


def test_canonical_blade_count_rejects_explicit_section_count_mismatch():
    lattice = build_section_loop_lattice(
        parameters={
            "blade_count": 10,
            "main_blade_count": 4,
            "splitter_blade_count": 4,
        },
        defaults=_defaults(),
    )

    assert lattice["status"] == "FAIL"
    assert "blade_count" in lattice["failure_reason"]


def test_canonical_blade_thickness_parameter_drives_section_geometry():
    baseline = build_section_loop_lattice(parameters={}, defaults=_defaults())
    thicker = build_section_loop_lattice(
        parameters={"blade_thickness_mm": 44.0},
        defaults=_defaults(),
    )

    assert thicker["status"] == "PASS"
    baseline_point = baseline["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["points"][0]
    thicker_point = thicker["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["points"][0]
    assert thicker_point != baseline_point


def test_explicit_average_thickness_must_match_canonical_blade_thickness():
    lattice = build_section_loop_lattice(
        parameters={
            "blade_thickness_mm": 44.0,
            "average_blade_thickness_mm": 32.0,
        },
        defaults=_defaults(),
    )

    assert lattice["status"] == "FAIL"
    assert "blade_thickness_mm" in lattice["failure_reason"]


def test_canonical_radii_and_heights_drive_mapped_section_geometry():
    baseline = build_section_loop_lattice(parameters={}, defaults=_defaults())
    edited = build_section_loop_lattice(
        parameters={
            "inlet_radius_mm": 80.0,
            "exit_radius_mm": 180.0,
            "inlet_blade_height_mm": 12.0,
            "outlet_blade_height_mm": 44.0,
        },
        defaults=_defaults(),
    )

    assert edited["status"] == "PASS"
    baseline_point = baseline["blades"][0]["section_loops"][0]["closed_loop_points"][0]
    edited_point = edited["blades"][0]["section_loops"][0]["closed_loop_points"][0]
    assert edited_point != baseline_point


def test_exit_radius_must_exceed_inlet_radius():
    lattice = build_section_loop_lattice(
        parameters={
            "inlet_radius_mm": 180.0,
            "exit_radius_mm": 120.0,
        },
        defaults=_defaults(),
    )

    assert lattice["status"] == "FAIL"
    assert "exit_radius_mm" in lattice["failure_reason"]
    assert "inlet_radius_mm" in lattice["failure_reason"]


def test_streamwise_extents_must_stay_within_unit_interval():
    negative = _defaults()
    negative["main_streamwise_start_u"] = -0.01
    above_one = _defaults()
    above_one["splitter_streamwise_end_u"] = 1.01

    negative_lattice = build_section_loop_lattice(parameters={}, defaults=negative)
    above_one_lattice = build_section_loop_lattice(parameters={}, defaults=above_one)

    assert negative_lattice["status"] == "FAIL"
    assert "0.0 <= start_u < end_u <= 1.0" in negative_lattice["failure_reason"]
    assert above_one_lattice["status"] == "FAIL"
    assert "0.0 <= start_u < end_u <= 1.0" in above_one_lattice["failure_reason"]


def test_section_loop_sample_count_below_review_minimum_fails():
    defaults = _defaults()
    defaults["section_loop_sample_count"] = 16

    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)

    assert lattice["status"] == "FAIL"
    assert "section_loop_sample_count" in lattice["failure_reason"]


def test_splitter_count_must_match_main_count_for_half_passage_phase():
    defaults = _defaults()
    defaults["splitter_blade_count"] = 3

    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)

    assert lattice["status"] == "FAIL"
    assert "splitter_blade_count" in lattice["failure_reason"]
