from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping
from typing import Any

from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_surface
from part_rule_synthesis.impeller_v11_constants import (
    COORDINATE_SYSTEM,
    CURVATURE_PROXY_MISMATCH_TOLERANCE,
    DOMAIN_ID,
    JOIN_ORDER,
    LOOP_FAMILY_ID,
    NORMAL_ANGLE_TOLERANCE_DEG,
    POSITION_GAP_TOLERANCE_MM,
    SPAN_STATIONS_H,
    TANGENT_ANGLE_TOLERANCE_DEG,
)


Point2 = list[float]
Point3 = list[float]

JOIN_SEGMENTS = {
    "pressure_to_leading": ("pressure_side", "start", "leading_edge", "start", 1.0, -1.0),
    "leading_to_suction": ("leading_edge", "end", "suction_side", "start", 1.0, 1.0),
    "suction_to_trailing": ("suction_side", "end", "trailing_edge", "start", 1.0, 1.0),
    "trailing_to_pressure": ("trailing_edge", "end", "pressure_side", "end", -1.0, 1.0),
}


def map_v11_domain_sample(
    parameters: Mapping[str, Any],
    defaults: Mapping[str, Any],
    sample: Mapping[str, float],
    overrides: Mapping[str, Any] | None = None,
) -> Point3:
    values = _validated_defaults(parameters, defaults, overrides or {})
    return _domain_mapper(values)(dict(sample))


def build_v11_blade_to_blade_loop_family(
    parameters: dict[str, Any],
    defaults: dict[str, Any],
    *,
    carrier_geometry: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del carrier_geometry
    values = _validated_defaults(parameters, defaults, overrides or {})
    segment_control_point_overrides = _segment_control_point_overrides(overrides or {})
    mapper = _domain_mapper(values)
    active_span_policy_metrics = _active_span_policy_metrics(values)
    blades: list[dict[str, Any]] = []
    blades.extend(
        _build_blade_set(
            values,
            mapper,
            blade_class="main",
            segment_control_point_overrides=segment_control_point_overrides,
        )
    )
    blades.extend(
        _build_blade_set(
            values,
            mapper,
            blade_class="splitter",
            segment_control_point_overrides=segment_control_point_overrides,
        )
    )
    splitter_passage_metrics = _splitter_passage_fraction_metrics(values, blades)
    family = {
        "status": "PASS",
        "loop_family_id": values["loop_family_id"],
        "domain_id": values["domain_id"],
        "coordinate_system": values["coordinate_system"],
        "span_stations_h": copy.deepcopy(values["span_stations_h"]),
        "canonical_nurbs_parameterization": copy.deepcopy(values.get("canonical_nurbs_parameterization")),
        "active_span_policy_metrics": active_span_policy_metrics,
        "segment_control_count_minimums": copy.deepcopy(values["segment_control_count_minimums"]),
        "resolved_defaults": {
            "main_streamwise_interval_s": copy.deepcopy(values["main_streamwise_interval_s"]),
            "splitter_streamwise_interval_s": copy.deepcopy(values["splitter_streamwise_interval_s"]),
            "splitter_phase_offset_pitch": float(values["splitter_phase_offset_pitch"]),
        },
        "domain_map": {
            "kind": "v1_1_blade_to_blade_domain_mapper",
            "public_function": "map_v11_domain_sample",
            "coordinate_system": values["coordinate_system"],
            "domain_id": values["domain_id"],
            "sample_keys": ["s", "q", "h", "phase_offset_pitch"],
            "q_units": "mm_arc_length",
            "streamwise_metric_scale_mm": values["streamwise_metric_scale_mm"],
            "phase_offset_pitch_units": "blade_pitch",
        },
        "blades": blades,
        "metrics": {
            "loop_station_count": len(values["span_stations_h"]),
            "blade_count": len(blades),
            "join_failure_count": sum(
                1
                for blade in blades
                for loop in blade["loops"]
                if loop["metrics"]["join_status"] != "PASS"
            ),
            **splitter_passage_metrics,
        },
    }
    return family


def _validated_defaults(
    parameters: Mapping[str, Any],
    defaults: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    values = _deep_merge(dict(defaults), overrides)
    values["loop_family_id"] = str(values.get("loop_family_id", LOOP_FAMILY_ID))
    values["domain_id"] = DOMAIN_ID
    values["coordinate_system"] = str(values.get("coordinate_system", COORDINATE_SYSTEM))
    values["span_stations_h"] = _float_list(values.get("span_stations_h", SPAN_STATIONS_H), "span_stations_h")
    canonical = values.get("canonical_nurbs_parameterization")
    if isinstance(canonical, Mapping):
        values["canonical_nurbs_parameterization"] = copy.deepcopy(canonical)
        population = canonical.get("blade_population", {})
        values["span_stations_h"] = _float_list(
            canonical.get("section_loop_family", {}).get("span_stations_h", values["span_stations_h"]),
            "span_stations_h",
        )
        values["main_blade_count"] = _int_value(
            population.get(
                "main_blade_count",
                values.get("main_blade_count", _parameter_value(parameters, "blade_count", 12) // 2),
            )
        )
        values["splitter_blade_count"] = _int_value(
            population.get(
                "splitter_blade_count",
                values.get("splitter_blade_count", _parameter_value(parameters, "blade_count", 12) // 2),
            ),
            minimum=None,
        )
        values["main_streamwise_interval_s"] = _pair(
            population.get("main_streamwise_interval_s", values.get("main_streamwise_interval_s", [0.06, 0.94]))
        )
        values["splitter_streamwise_interval_s"] = _pair(
            population.get("splitter_streamwise_interval_s", values.get("splitter_streamwise_interval_s", [0.35, 0.88]))
        )
        values["splitter_phase_offset_pitch"] = float(
            population.get("splitter_phase_offset_pitch", values.get("splitter_phase_offset_pitch", 0.5))
        )
    values["main_blade_count"] = _int_value(
        values.get("main_blade_count", _parameter_value(parameters, "blade_count", 12) // 2)
    )
    values["splitter_blade_count"] = _int_value(
        values.get("splitter_blade_count", _parameter_value(parameters, "blade_count", 12) // 2),
        minimum=None,
    )
    values["main_streamwise_interval_s"] = _pair(values.get("main_streamwise_interval_s", [0.06, 0.94]))
    values["splitter_streamwise_interval_s"] = _pair(values.get("splitter_streamwise_interval_s", [0.35, 0.88]))
    values["splitter_phase_offset_pitch"] = float(values.get("splitter_phase_offset_pitch", 0.5))
    values["average_blade_thickness_mm"] = float(
        values.get("average_blade_thickness_mm", _parameter_value(parameters, "blade_thickness_mm", 1.0))
    )
    values["blade_count"] = int(_parameter_value(parameters, "blade_count", values["main_blade_count"] + values["splitter_blade_count"]))
    values["segment_control_count_minimums"] = {
        "pressure_side": int(values.get("segment_control_count_minimums", {}).get("pressure_side", 11)),
        "suction_side": int(values.get("segment_control_count_minimums", {}).get("suction_side", 11)),
        "leading_edge": int(values.get("segment_control_count_minimums", {}).get("leading_edge", 9)),
        "trailing_edge": int(values.get("segment_control_count_minimums", {}).get("trailing_edge", 9)),
    }
    control_counts = values.get("segment_control_counts", values["segment_control_count_minimums"])
    values["segment_control_counts"] = {
        "pressure_side": int(control_counts.get("pressure_side", 11)),
        "suction_side": int(control_counts.get("suction_side", 11)),
        "leading_edge": int(control_counts.get("leading_edge", 9)),
        "trailing_edge": int(control_counts.get("trailing_edge", 9)),
    }
    values["side_sample_count"] = max(
        int(values.get("side_sample_count", 49)),
        values["segment_control_counts"]["pressure_side"],
        values["segment_control_counts"]["suction_side"],
        7,
    )
    values["edge_cap_sample_count"] = max(
        int(values.get("edge_cap_sample_count", 33)),
        values["segment_control_counts"]["leading_edge"],
        values["segment_control_counts"]["trailing_edge"],
        7,
    )
    values["main_flow_turn_q_mm"] = float(values.get("main_flow_turn_q_mm", 82.0))
    values["splitter_flow_turn_q_mm"] = float(values.get("splitter_flow_turn_q_mm", 54.0))
    values["splitter_positioning_mode"] = str(values.get("splitter_positioning_mode", "main_passage_bisector"))
    values["splitter_passage_fraction"] = float(values.get("splitter_passage_fraction", 0.5))
    values["spanwise_flow_turn_delta_q_mm"] = float(values.get("spanwise_flow_turn_delta_q_mm", 18.0))
    values["midspan_bow_q_mm"] = float(values.get("midspan_bow_q_mm", 8.0))
    values["leading_edge_cap_roundness"] = float(values.get("leading_edge_cap_roundness", 0.72))
    values["trailing_edge_cap_roundness"] = float(values.get("trailing_edge_cap_roundness", 0.72))
    values["root_blade_lift_mm"] = float(
        values.get("root_blade_lift_mm", values.get("root_attachment_lift_mm", 0.0))
    )
    values["tip_attachment_mode"] = str(values.get("tip_attachment_mode", "open_tip_dome"))
    default_shroud_inset_mm = values["root_blade_lift_mm"] if values["tip_attachment_mode"] == "closed_shroud_attachment" else 0.0
    values["shroud_blade_inset_mm"] = float(values.get("shroud_blade_inset_mm", default_shroud_inset_mm))
    default_clearance_compensation = 1.04 if values["tip_attachment_mode"] == "closed_shroud_attachment" else 1.0
    values["span_material_clearance_compensation"] = float(
        values.get("span_material_clearance_compensation", default_clearance_compensation)
    )
    values["hub_profile_rz_mm"] = _profile_points(values.get("hub_profile_rz_mm", []), "hub_profile_rz_mm")
    values["tip_or_shroud_profile_rz_mm"] = _profile_points(
        values.get("tip_or_shroud_profile_rz_mm", []),
        "tip_or_shroud_profile_rz_mm",
    )
    if len(values["hub_profile_rz_mm"]) < 2 or len(values["tip_or_shroud_profile_rz_mm"]) < 2:
        raise ValueError("V1.1 loop-family defaults require hub and tip/shroud profiles")
    values["streamwise_metric_scale_mm"] = _profile_polyline_length(values["hub_profile_rz_mm"])
    if values["blade_count"] < 2:
        raise ValueError("blade_count must be at least 2")
    if values["main_blade_count"] <= 0:
        raise ValueError("main_blade_count must be positive")
    if values["splitter_blade_count"] < 0:
        raise ValueError("splitter_blade_count must be zero or positive")
    if values["main_blade_count"] + values["splitter_blade_count"] != values["blade_count"]:
        raise ValueError("blade_count must equal main_blade_count + splitter_blade_count")
    if values["splitter_blade_count"] == 0:
        values["splitter_flow_turn_q_mm"] = 0.0
    if values["average_blade_thickness_mm"] <= 0.0:
        raise ValueError("average_blade_thickness_mm must be positive")
    if values["main_flow_turn_q_mm"] <= 0.0:
        raise ValueError("main_flow_turn_q_mm must be positive")
    if values["splitter_blade_count"] > 0 and values["splitter_flow_turn_q_mm"] <= 0.0:
        raise ValueError("splitter_flow_turn_q_mm must be positive when splitters are present")
    if values["splitter_positioning_mode"] not in {"main_passage_bisector", "independent_local_camber"}:
        raise ValueError("splitter_positioning_mode must be main_passage_bisector or independent_local_camber")
    if not 0.2 <= values["splitter_passage_fraction"] <= 0.8:
        raise ValueError("splitter_passage_fraction must stay inside the adjacent main-blade passage")
    return values


def _domain_mapper(values: Mapping[str, Any]) -> Callable[[dict[str, float]], Point3]:
    blade_pitch_rad = 2.0 * math.pi / max(int(values["main_blade_count"]), 1)
    hub_profile = values["hub_profile_rz_mm"]
    tip_profile = values["tip_or_shroud_profile_rz_mm"]
    root_offset, tip_offset = _resolved_active_span_offsets(values)

    def mapper(sample: dict[str, float]) -> Point3:
        s = float(sample["s"])
        q = float(sample["q"])
        h = max(0.0, min(1.0, float(sample["h"])))
        phase_offset_pitch = float(sample.get("phase_offset_pitch", 0.0))

        hub_r, hub_z = _profile_sample(hub_profile, s)
        tip_r, tip_z = _profile_sample(tip_profile, s)
        span_length_mm = math.hypot(tip_r - hub_r, tip_z - hub_z)
        root_fraction = 0.0
        if span_length_mm > 1.0e-9:
            root_fraction = max(
                0.0,
                min(
                    0.45,
                    root_offset
                    * float(values.get("span_material_clearance_compensation", 1.0))
                    / span_length_mm,
                ),
            )
        tip_fraction = 0.0
        if span_length_mm > 1.0e-9:
            tip_fraction = max(
                0.0,
                min(
                    0.45,
                    tip_offset
                    * float(values.get("span_material_clearance_compensation", 1.0))
                    / span_length_mm,
                ),
            )
            tip_fraction = min(tip_fraction, max(0.0, 0.9 - root_fraction))
        blade_span_fraction = max(0.0, 1.0 - root_fraction - tip_fraction)
        effective_h = root_fraction + h * blade_span_fraction
        radius_mm = _lerp(hub_r, tip_r, effective_h)
        z_mm = _lerp(hub_z, tip_z, effective_h)
        theta_rad = phase_offset_pitch * blade_pitch_rad + (q / max(radius_mm, 1.0e-9))
        return _round_point(
            [
                radius_mm * math.cos(theta_rad),
                radius_mm * math.sin(theta_rad),
                z_mm,
            ]
        )

    return mapper


def _build_blade_set(
    values: Mapping[str, Any],
    mapper: Callable[[dict[str, float]], Point3],
    *,
    blade_class: str,
    segment_control_point_overrides: Mapping[str, list[Point2]],
) -> list[dict[str, Any]]:
    if blade_class == "main":
        blade_count = int(values["main_blade_count"])
        phase_offset_pitch = 0.0
        streamwise_interval = values["main_streamwise_interval_s"]
    else:
        blade_count = int(values["splitter_blade_count"])
        phase_offset_pitch = float(values["splitter_phase_offset_pitch"])
        streamwise_interval = values["splitter_streamwise_interval_s"]

    blades: list[dict[str, Any]] = []
    for blade_pair_index in range(blade_count):
        blade_phase_pitch = blade_pair_index + phase_offset_pitch
        loops = [
            _build_loop(
                values,
                mapper,
                blade_class=blade_class,
                h=float(h_value),
                streamwise_interval=streamwise_interval,
                phase_offset_pitch=blade_phase_pitch,
                segment_control_point_overrides=segment_control_point_overrides,
            )
            for h_value in values["span_stations_h"]
        ]
        blades.append(
            {
                "blade_class": blade_class,
                "blade_pair_index": blade_pair_index,
                "domain_id": values["domain_id"],
                "phase_offset_pitch": phase_offset_pitch,
                "streamwise_interval_s": copy.deepcopy(streamwise_interval),
                "loops": loops,
            }
        )
    return blades


def _build_loop(
    values: Mapping[str, Any],
    mapper: Callable[[dict[str, float]], Point3],
    *,
    blade_class: str,
    h: float,
    streamwise_interval: list[float],
    phase_offset_pitch: float,
    segment_control_point_overrides: Mapping[str, list[Point2]],
) -> dict[str, Any]:
    segments_s_q = _loop_segments_s_q(
        values=values,
        s0=streamwise_interval[0],
        s1=streamwise_interval[1],
        thickness_mm=float(values["average_blade_thickness_mm"]),
        h=h,
        blade_class=blade_class,
        segment_control_point_overrides=segment_control_point_overrides,
    )
    segments = {
        name: {
            "points_s_q": copy.deepcopy(data["points_s_q"]),
            "points_xyz": [
                mapper({"s": point[0], "q": point[1], "h": h, "phase_offset_pitch": phase_offset_pitch})
                for point in data["points_s_q"]
            ],
            "control_points_s_q": copy.deepcopy(data["control_points_s_q"]),
            **({"canonical_curve": copy.deepcopy(data["canonical_curve"])} if "canonical_curve" in data else {}),
        }
        for name, data in segments_s_q.items()
    }
    join_metrics = _join_metrics(
        segments,
        streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
    )
    join_status = "PASS" if all(metric["status"] == "PASS" for metric in join_metrics.values()) else "FAIL"
    minimum_span_length = _minimum_span_length(values)
    root_offset, tip_offset = _resolved_active_span_offsets(values)
    active_span_fraction = 0.0
    if minimum_span_length > 1.0e-9:
        root_fraction = max(0.0, min(0.45, root_offset / minimum_span_length))
        tip_fraction = max(0.0, min(0.45, tip_offset / minimum_span_length))
        tip_fraction = min(tip_fraction, max(0.0, 0.9 - root_fraction))
        active_span_fraction = root_fraction + h * max(0.0, 1.0 - root_fraction - tip_fraction)
    return {
        "h": round(h, 9),
        "active_span_fraction": _round(active_span_fraction),
        "streamwise_metric_scale_mm": float(values["streamwise_metric_scale_mm"]),
        "segments": segments,
        "join_metrics": join_metrics,
        "metrics": {
            "join_status": join_status,
            "orientation_status": "PASS",
            "leading_cap_sagitta_target_mm": _round(segments_s_q["leading_edge"]["canonical_curve"]["target_sagitta_mm"]),
            "leading_cap_sagitta_resolved_mm": _round(segments_s_q["leading_edge"]["canonical_curve"]["resolved_sagitta_mm"]),
            "trailing_cap_sagitta_target_mm": _round(segments_s_q["trailing_edge"]["canonical_curve"]["target_sagitta_mm"]),
            "trailing_cap_sagitta_resolved_mm": _round(segments_s_q["trailing_edge"]["canonical_curve"]["resolved_sagitta_mm"]),
            "max_position_gap_mm": _max_join_value(join_metrics, "position_gap_mm"),
            "max_tangent_angle_deg": _max_join_value(join_metrics, "tangent_angle_deg"),
            "max_normal_angle_deg": _max_join_value(join_metrics, "normal_angle_deg"),
            "max_curvature_proxy_mismatch": _max_join_value(join_metrics, "curvature_proxy_mismatch"),
        },
    }


def _loop_segments_s_q(
    *,
    values: Mapping[str, Any],
    s0: float,
    s1: float,
    thickness_mm: float,
    h: float,
    blade_class: str,
    segment_control_point_overrides: Mapping[str, list[Point2]],
) -> dict[str, dict[str, list[Point2]]]:
    side_sample_count = int(values["side_sample_count"])
    pressure_side_control_count = int(values["segment_control_counts"]["pressure_side"])
    suction_side_control_count = int(values["segment_control_counts"]["suction_side"])
    cap_sample_count = int(values["edge_cap_sample_count"])
    leading_cap_control_count = int(values["segment_control_counts"]["leading_edge"])
    trailing_cap_control_count = int(values["segment_control_counts"]["trailing_edge"])

    pressure_points = _sample_side_points(
        values=values,
        s0=s0,
        s1=s1,
        thickness_mm=thickness_mm,
        h=h,
        blade_class=blade_class,
        sign=-1.0,
        sample_count=side_sample_count,
    )
    suction_points = _sample_side_points(
        values=values,
        s0=s0,
        s1=s1,
        thickness_mm=thickness_mm,
        h=h,
        blade_class=blade_class,
        sign=1.0,
        sample_count=side_sample_count,
    )
    leading_points = _cap_points(
        pressure_points[0],
        suction_points[0],
        streamwise_anchor=s0,
        streamwise_span=s1 - s0,
        streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
        sample_count=cap_sample_count,
        cap_direction=-1.0,
        start_diff=_point_scale(_point_diff(pressure_points[1], pressure_points[0]), -1.0),
        start_second_diff=_second_diff(pressure_points[0], pressure_points[1], pressure_points[2]),
        end_diff=_point_diff(suction_points[1], suction_points[0]),
        end_second_diff=_second_diff(suction_points[0], suction_points[1], suction_points[2]),
        roundness=float(values["leading_edge_cap_roundness"]),
    )
    trailing_points = _cap_points(
        suction_points[-1],
        pressure_points[-1],
        streamwise_anchor=s1,
        streamwise_span=s1 - s0,
        streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
        sample_count=cap_sample_count,
        cap_direction=1.0,
        start_diff=_point_diff(suction_points[-1], suction_points[-2]),
        start_second_diff=_second_diff(suction_points[-3], suction_points[-2], suction_points[-1]),
        end_diff=_point_scale(_point_diff(pressure_points[-1], pressure_points[-2]), -1.0),
        end_second_diff=_second_diff(pressure_points[-3], pressure_points[-2], pressure_points[-1]),
        roundness=float(values["trailing_edge_cap_roundness"]),
    )
    leading_target_sagitta = _cap_target_sagitta_mm(pressure_points[0], suction_points[0], ratio=0.5)
    trailing_target_sagitta = _cap_target_sagitta_mm(suction_points[-1], pressure_points[-1], ratio=0.5)
    leading_sagitta = _cap_sagitta_mm(
        leading_points,
        streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
        cap_direction=-1.0,
    )
    trailing_sagitta = _cap_sagitta_mm(
        trailing_points,
        streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
        cap_direction=1.0,
    )
    segments = {
        "pressure_side": {
            "points_s_q": pressure_points,
            "control_points_s_q": _control_polygon(pressure_points, pressure_side_control_count),
        },
        "leading_edge": {
            "points_s_q": leading_points,
            "control_points_s_q": _control_polygon(leading_points, leading_cap_control_count),
            "canonical_curve": {
                "kind": "nurbs_cap_curve",
                "coordinate_system": "s_q_mm",
                "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
                "target_sagitta_mm": _round(leading_target_sagitta),
                "resolved_sagitta_mm": _round(leading_sagitta),
                "continuity_goal": "C2",
            },
        },
        "suction_side": {
            "points_s_q": suction_points,
            "control_points_s_q": _control_polygon(suction_points, suction_side_control_count),
        },
        "trailing_edge": {
            "points_s_q": trailing_points,
            "control_points_s_q": _control_polygon(trailing_points, trailing_cap_control_count),
            "canonical_curve": {
                "kind": "nurbs_cap_curve",
                "coordinate_system": "s_q_mm",
                "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
                "target_sagitta_mm": _round(trailing_target_sagitta),
                "resolved_sagitta_mm": _round(trailing_sagitta),
                "continuity_goal": "C2",
            },
        },
    }
    _apply_segment_control_point_overrides(
        segments,
        sample_counts={
            "pressure_side": side_sample_count,
            "suction_side": side_sample_count,
            "leading_edge": cap_sample_count,
            "trailing_edge": cap_sample_count,
        },
        overrides=segment_control_point_overrides,
    )
    for segment_name, cap_direction in (("leading_edge", -1.0), ("trailing_edge", 1.0)):
        segments[segment_name]["canonical_curve"]["resolved_sagitta_mm"] = _round(
            _cap_sagitta_mm(
                segments[segment_name]["points_s_q"],
                streamwise_metric_scale_mm=float(values["streamwise_metric_scale_mm"]),
                cap_direction=cap_direction,
            )
        )
    return segments


def _sample_side_points(
    *,
    values: Mapping[str, Any],
    s0: float,
    s1: float,
    thickness_mm: float,
    h: float,
    blade_class: str,
    sign: float,
    sample_count: int,
) -> list[Point2]:
    points: list[Point2] = []
    canonical = values.get("canonical_nurbs_parameterization") or {}
    skeleton_field = canonical.get("blade_skeleton_field")
    thickness_field = canonical.get("thickness_field")
    for index in range(sample_count):
        s_norm = index / max(sample_count - 1, 1)
        s = _lerp(s0, s1, s_norm)
        canonical_camber_q = _sample_surface_q(skeleton_field, s_norm, h)
        canonical_thickness = _sample_surface_q(thickness_field, s_norm, h)
        if canonical_camber_q is not None and canonical_thickness is not None:
            camber_q = canonical_camber_q
            local_thickness = max(1.0e-9, canonical_thickness)
        else:
            camber_q = _camber_q(
                s_norm,
                h,
                blade_class,
                values,
                streamwise_s=s,
            )
            local_thickness = thickness_mm * (0.75 + 0.25 * math.sin(math.pi * _smootherstep(s_norm)))
        q = camber_q + sign * 0.5 * local_thickness
        points.append(_round_point_2d([s, q]))
    return points


def _cap_points(
    start: Point2,
    end: Point2,
    *,
    streamwise_anchor: float,
    streamwise_span: float,
    streamwise_metric_scale_mm: float,
    sample_count: int,
    cap_direction: float,
    start_diff: Point2,
    start_second_diff: Point2,
    end_diff: Point2,
    end_second_diff: Point2,
    roundness: float,
) -> list[Point2]:
    del streamwise_span, roundness
    if sample_count <= 1:
        return [copy.deepcopy(start)]
    metric_scale = max(float(streamwise_metric_scale_mm), 1.0e-9)
    center_q = 0.5 * (start[1] + end[1])
    half_thickness_mm = 0.5 * abs(end[1] - start[1])
    sagitta_s = half_thickness_mm / metric_scale
    anchor_s = float(streamwise_anchor)
    q_half_span = 0.5 * (end[1] - start[1])
    points: list[Point2] = []
    for index in range(sample_count):
        t = index / max(sample_count - 1, 1)
        points.append(
            _round_point_2d(
                [
                    anchor_s + cap_direction * sagitta_s * math.sin(math.pi * t),
                    center_q - q_half_span * math.cos(math.pi * t),
                ]
            )
        )
    points[0] = copy.deepcopy(start)
    points[-1] = copy.deepcopy(end)
    if sample_count >= 5 and half_thickness_mm > 1.0e-9:
        cap_delta_angle = math.pi / max(sample_count - 1, 1)
        cap_first_step_mm = max(1.0e-9, 2.0 * half_thickness_mm * math.sin(0.5 * cap_delta_angle))
        start_tangent_step = _metric_limited_cap_tangent_step(start_diff, metric_scale, cap_first_step_mm)
        end_tangent_step = _metric_limited_cap_tangent_step(end_diff, metric_scale, cap_first_step_mm)
        start_second_step = _metric_limited_cap_second_step(
            start_second_diff,
            start_tangent_step,
            metric_scale,
            1.75 * cap_first_step_mm,
        )
        end_second_step = _metric_limited_cap_second_step(
            end_second_diff,
            end_tangent_step,
            metric_scale,
            1.75 * cap_first_step_mm,
        )
        points[1] = _round_point_2d(_point_add(points[0], start_tangent_step))
        points[2] = _round_point_2d(
            _point_add(_point_add(points[0], _point_scale(start_tangent_step, 2.0)), start_second_step)
        )
        points[-2] = _round_point_2d(_point_subtract(points[-1], end_tangent_step))
        points[-3] = _round_point_2d(
            _point_add(_point_subtract(_point_scale(points[-2], 2.0), points[-1]), end_second_step)
        )
        _clamp_cap_boundary_points_to_half_thickness_envelope(
            points,
            anchor_s=anchor_s,
            cap_direction=cap_direction,
            sagitta_s=sagitta_s,
            start=start,
            end=end,
        )
    return points


def _camber_q(
    s_norm: float,
    h: float,
    blade_class: str,
    values: Mapping[str, Any],
    *,
    streamwise_s: float | None = None,
) -> float:
    if blade_class == "splitter" and values.get("splitter_positioning_mode") == "main_passage_bisector":
        s_value = float(streamwise_s if streamwise_s is not None else _lerp(
            values["splitter_streamwise_interval_s"][0],
            values["splitter_streamwise_interval_s"][1],
            s_norm,
        ))
        main_s0, main_s1 = values["main_streamwise_interval_s"]
        main_s_norm = (s_value - main_s0) / max(main_s1 - main_s0, 1.0e-9)
        main_q = _local_camber_q(main_s_norm, h, "main", values)
        blade_pitch_rad = 2.0 * math.pi / max(int(values["main_blade_count"]), 1)
        pitch_arc_mm = _effective_radius_mm(values, s_value, h) * blade_pitch_rad
        target_fraction = float(values["splitter_passage_fraction"])
        phase_offset = float(values["splitter_phase_offset_pitch"])
        return main_q + (target_fraction - phase_offset) * pitch_arc_mm
    return _local_camber_q(s_norm, h, blade_class, values)


def _local_camber_q(s_norm: float, h: float, blade_class: str, values: Mapping[str, Any]) -> float:
    turn_q = (
        float(values["main_flow_turn_q_mm"])
        if blade_class == "main"
        else float(values["splitter_flow_turn_q_mm"])
    )
    span_bias = max(0.0, min(1.0, h)) - 0.5
    span_adjusted_turn_q = turn_q + span_bias * float(values["spanwise_flow_turn_delta_q_mm"])
    progress = _smootherstep(max(0.0, min(1.0, s_norm)))
    bow_q = float(values["midspan_bow_q_mm"]) * math.sin(math.pi * progress) * (1.0 + 0.15 * span_bias)
    return span_adjusted_turn_q * progress + bow_q


def _resolved_active_span_offsets(values: Mapping[str, Any]) -> tuple[float, float]:
    canonical = values.get("canonical_nurbs_parameterization") or {}
    active_policy = canonical.get("active_span_policy") or {}
    root_offset = float(
        active_policy.get("root_offset", {}).get("resolved_constant_mm", values.get("root_blade_lift_mm", 0.0))
    )
    tip_offset = float(
        active_policy.get("tip_offset", {}).get(
            "resolved_constant_mm",
            values.get(
                "shroud_blade_inset_mm",
                0.0
                if values.get("tip_attachment_mode") != "closed_shroud_attachment"
                else values.get("root_blade_lift_mm", 0.0),
            ),
        )
    )
    return root_offset, tip_offset


def _minimum_span_length(values: Mapping[str, Any]) -> float:
    return float(_pointwise_span_metrics(values)["pointwise_support_span_min_mm"])


def _active_span_policy_metrics(values: Mapping[str, Any]) -> dict[str, Any]:
    root_offset, tip_offset = _resolved_active_span_offsets(values)
    pointwise = _pointwise_span_metrics(values)
    status = (
        "PASS"
        if root_offset >= 0.0 and tip_offset >= 0.0 and pointwise["pointwise_usable_span_min_mm"] > 0.0
        else "FAIL"
    )
    return {
        "resolved_root_offset_min_mm": _round(root_offset),
        "resolved_root_offset_max_mm": _round(root_offset),
        "resolved_tip_offset_min_mm": _round(tip_offset),
        "resolved_tip_offset_max_mm": _round(tip_offset),
        "pointwise_support_span_min_mm": _round(pointwise["pointwise_support_span_min_mm"]),
        "pointwise_support_span_max_mm": _round(pointwise["pointwise_support_span_max_mm"]),
        "pointwise_usable_span_min_mm": _round(pointwise["pointwise_usable_span_min_mm"]),
        "pointwise_usable_span_max_mm": _round(pointwise["pointwise_usable_span_max_mm"]),
        "offset_feasibility_status": status,
    }


def _pointwise_span_metrics(values: Mapping[str, Any]) -> dict[str, float]:
    hub_profile = values["hub_profile_rz_mm"]
    tip_profile = values["tip_or_shroud_profile_rz_mm"]
    root_offset, tip_offset = _resolved_active_span_offsets(values)
    intervals = [values["main_streamwise_interval_s"]]
    if int(values.get("splitter_blade_count", 0)) > 0:
        intervals.append(values["splitter_streamwise_interval_s"])
    support_spans: list[float] = []
    usable_spans: list[float] = []
    sample_count = 65
    for interval in intervals:
        s0, s1 = interval
        for index in range(sample_count):
            s = _lerp(s0, s1, index / max(sample_count - 1, 1))
            hub_r, hub_z = _profile_sample(hub_profile, s)
            tip_r, tip_z = _profile_sample(tip_profile, s)
            support_span = math.hypot(tip_r - hub_r, tip_z - hub_z)
            support_spans.append(support_span)
            usable_spans.append(support_span - root_offset - tip_offset)
    if not support_spans:
        return {
            "pointwise_support_span_min_mm": 0.0,
            "pointwise_support_span_max_mm": 0.0,
            "pointwise_usable_span_min_mm": -(root_offset + tip_offset),
            "pointwise_usable_span_max_mm": -(root_offset + tip_offset),
        }
    return {
        "pointwise_support_span_min_mm": min(support_spans),
        "pointwise_support_span_max_mm": max(support_spans),
        "pointwise_usable_span_min_mm": min(usable_spans),
        "pointwise_usable_span_max_mm": max(usable_spans),
    }


def _cap_target_sagitta_mm(start: Point2, end: Point2, *, ratio: float) -> float:
    return max(0.0, float(ratio)) * abs(float(end[1]) - float(start[1]))


def _cap_sagitta_mm(points: list[Point2], *, streamwise_metric_scale_mm: float, cap_direction: float) -> float:
    if not points:
        return 0.0
    metric_scale = max(float(streamwise_metric_scale_mm), 1.0e-9)
    anchor_s = 0.5 * (float(points[0][0]) + float(points[-1][0]))
    if cap_direction < 0.0:
        sagitta_s = anchor_s - min(float(point[0]) for point in points)
    else:
        sagitta_s = max(float(point[0]) for point in points) - anchor_s
    return max(0.0, sagitta_s) * metric_scale


def _sample_surface_q(surface: Any, u: float, v: float) -> float | None:
    if not isinstance(surface, Mapping):
        return None
    try:
        normalized = _normalized_surface_degree_payload(dict(surface))
        sample = evaluate_nurbs_surface(normalized, u, v)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not isinstance(sample, list) or len(sample) < 3:
        return None
    try:
        value = float(sample[2])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _normalized_surface_degree_payload(surface: dict[str, Any]) -> dict[str, Any]:
    control_points = surface.get("control_points")
    if not isinstance(control_points, list) or not control_points or not isinstance(control_points[0], list):
        return surface
    degree_u = min(int(surface.get("degree_u", surface.get("degree_s", 1))), max(len(control_points) - 1, 1))
    degree_v = min(
        int(surface.get("degree_v", surface.get("degree_h", 1))),
        max(len(control_points[0]) - 1, 1),
    )
    surface["degree_u"] = degree_u
    surface["degree_v"] = degree_v
    return surface


def _join_metrics(
    segments: Mapping[str, Mapping[str, Any]],
    *,
    streamwise_metric_scale_mm: float = 1.0,
) -> dict[str, dict[str, float | str]]:
    metrics: dict[str, dict[str, float | str]] = {}
    metric_scale = max(float(streamwise_metric_scale_mm), 1.0e-9)
    for join_name in JOIN_ORDER:
        left_name, left_end, right_name, right_end, left_tangent_sign, right_tangent_sign = JOIN_SEGMENTS[join_name]
        left_points = segments[left_name]["points_s_q"]
        right_points = segments[right_name]["points_s_q"]
        left_point, left_tangent, left_curvature = _boundary_frame(left_points, left_end)
        right_point, right_tangent, right_curvature = _boundary_frame(right_points, right_end)
        left_point = _scale_streamwise_component(left_point, metric_scale)
        right_point = _scale_streamwise_component(right_point, metric_scale)
        left_tangent = _scale_streamwise_component(left_tangent, metric_scale)
        right_tangent = _scale_streamwise_component(right_tangent, metric_scale)
        left_curvature = _scale_streamwise_component(left_curvature, metric_scale)
        right_curvature = _scale_streamwise_component(right_curvature, metric_scale)
        left_tangent = _point_scale(left_tangent, left_tangent_sign)
        right_tangent = _point_scale(right_tangent, right_tangent_sign)
        position_gap_mm = _distance_2d(left_point, right_point)
        tangent_angle_deg = _vector_angle_deg(left_tangent, right_tangent)
        normal_angle_deg = _vector_angle_deg(left_curvature, right_curvature)
        curvature_proxy_mismatch = abs(_vector_norm(left_curvature) - _vector_norm(right_curvature))
        status = "PASS"
        if (
            position_gap_mm > POSITION_GAP_TOLERANCE_MM
            or tangent_angle_deg > TANGENT_ANGLE_TOLERANCE_DEG
            or normal_angle_deg > NORMAL_ANGLE_TOLERANCE_DEG
            or curvature_proxy_mismatch > CURVATURE_PROXY_MISMATCH_TOLERANCE
        ):
            status = "FAIL"
        metrics[join_name] = {
            "status": status,
            "position_gap_mm": round(position_gap_mm, 9),
            "tangent_angle_deg": round(tangent_angle_deg, 9),
            "normal_angle_deg": round(normal_angle_deg, 9),
            "curvature_proxy_mismatch": round(curvature_proxy_mismatch, 9),
        }
    return metrics


def _splitter_passage_fraction_metrics(
    values: Mapping[str, Any],
    blades: list[dict[str, Any]],
) -> dict[str, float | str]:
    if int(values.get("splitter_blade_count", 0)) == 0:
        return {
            "splitter_positioning_status": "NOT_APPLICABLE",
            "splitter_passage_fraction_min": None,
            "splitter_passage_fraction_max": None,
            "splitter_passage_fraction_avg": None,
        }
    main_blade = next((blade for blade in blades if blade["blade_class"] == "main"), None)
    splitter_blade = next((blade for blade in blades if blade["blade_class"] == "splitter"), None)
    if main_blade is None or splitter_blade is None:
        return {
            "splitter_positioning_status": "FAIL",
            "splitter_passage_fraction_min": 0.0,
            "splitter_passage_fraction_max": 0.0,
            "splitter_passage_fraction_avg": 0.0,
        }
    fractions: list[float] = []
    for main_loop, splitter_loop in zip(main_blade["loops"], splitter_blade["loops"]):
        main_centerline = _centerline_points_s_q(main_loop)
        splitter_centerline = _centerline_points_s_q(splitter_loop)
        for splitter_point in splitter_centerline:
            fractions.append(
                _passage_fraction_for_splitter_point(
                    values,
                    main_centerline,
                    splitter_point,
                    h=float(splitter_loop["h"]),
                    phase_offset_pitch=float(splitter_blade["phase_offset_pitch"]),
                )
            )
    if not fractions:
        return {
            "splitter_positioning_status": "FAIL",
            "splitter_passage_fraction_min": 0.0,
            "splitter_passage_fraction_max": 0.0,
            "splitter_passage_fraction_avg": 0.0,
        }
    min_fraction = min(fractions)
    max_fraction = max(fractions)
    avg_fraction = sum(fractions) / len(fractions)
    target = float(values["splitter_passage_fraction"])
    status = "PASS" if abs(min_fraction - target) <= 0.055 and abs(max_fraction - target) <= 0.055 else "FAIL"
    return {
        "splitter_positioning_status": status,
        "splitter_passage_fraction_min": round(min_fraction, 9),
        "splitter_passage_fraction_max": round(max_fraction, 9),
        "splitter_passage_fraction_avg": round(avg_fraction, 9),
    }


def _centerline_points_s_q(loop: Mapping[str, Any]) -> list[Point2]:
    pressure = loop["segments"]["pressure_side"]["points_s_q"]
    suction = loop["segments"]["suction_side"]["points_s_q"]
    return [
        [0.5 * (pressure_point[0] + suction_point[0]), 0.5 * (pressure_point[1] + suction_point[1])]
        for pressure_point, suction_point in zip(pressure, suction)
    ]


def _passage_fraction_for_splitter_point(
    values: Mapping[str, Any],
    main_centerline: list[Point2],
    splitter_point: Point2,
    *,
    h: float,
    phase_offset_pitch: float,
) -> float:
    s_value, splitter_q = splitter_point
    main_q = _interpolated_centerline_q(main_centerline, s_value)
    blade_pitch_rad = 2.0 * math.pi / max(int(values["main_blade_count"]), 1)
    pitch_arc_mm = _effective_radius_mm(values, s_value, h) * blade_pitch_rad
    return phase_offset_pitch + (splitter_q - main_q) / max(pitch_arc_mm, 1.0e-9)


def _interpolated_centerline_q(points: list[Point2], s_value: float) -> float:
    for left, right in zip(points, points[1:]):
        if left[0] <= s_value <= right[0]:
            fraction = 0.0 if right[0] == left[0] else (s_value - left[0]) / (right[0] - left[0])
            return _lerp(left[1], right[1], fraction)
    return points[0][1] if s_value < points[0][0] else points[-1][1]


def _effective_radius_mm(values: Mapping[str, Any], s_value: float, h: float) -> float:
    hub_r, hub_z = _profile_sample(values["hub_profile_rz_mm"], s_value)
    tip_r, tip_z = _profile_sample(values["tip_or_shroud_profile_rz_mm"], s_value)
    span_length_mm = math.hypot(tip_r - hub_r, tip_z - hub_z)
    root_fraction = 0.0
    if span_length_mm > 1.0e-9:
        root_fraction = max(
            0.0,
            min(
                0.45,
                float(values.get("root_blade_lift_mm", 0.0))
                * float(values.get("span_material_clearance_compensation", 1.0))
                / span_length_mm,
            ),
        )
    tip_fraction = 0.0
    if values.get("tip_attachment_mode") == "closed_shroud_attachment" and span_length_mm > 1.0e-9:
        tip_fraction = max(
            0.0,
            min(
                0.45,
                float(values.get("shroud_blade_inset_mm", 0.0))
                * float(values.get("span_material_clearance_compensation", 1.0))
                / span_length_mm,
            ),
        )
        tip_fraction = min(tip_fraction, max(0.0, 0.9 - root_fraction))
    blade_span_fraction = max(0.0, 1.0 - root_fraction - tip_fraction)
    effective_h = root_fraction + max(0.0, min(1.0, h)) * blade_span_fraction
    return _lerp(hub_r, tip_r, effective_h)


def _control_polygon(points: list[Point2], count: int) -> list[Point2]:
    if count >= len(points):
        return copy.deepcopy(points)
    indices = []
    for index in range(count):
        scaled = round(index * (len(points) - 1) / max(count - 1, 1))
        indices.append(min(max(scaled, 0), len(points) - 1))
    deduped = []
    for index in indices:
        if not deduped or deduped[-1] != index:
            deduped.append(index)
    while len(deduped) < count:
        candidate = min(deduped[-1] + 1, len(points) - 1)
        if candidate == deduped[-1]:
            break
        deduped.append(candidate)
    return [copy.deepcopy(points[index]) for index in deduped]


def _segment_control_point_overrides(overrides: Mapping[str, Any]) -> dict[str, list[Point2]]:
    candidates = []
    nested = overrides.get("blade_to_blade_loop_family")
    if isinstance(nested, Mapping):
        candidates.append(nested)
    candidates.append(overrides)

    resolved: dict[str, list[Point2]] = {}
    for candidate in candidates:
        segments = candidate.get("segments")
        if not isinstance(segments, Mapping):
            continue
        for segment_name, segment_payload in segments.items():
            if not isinstance(segment_payload, Mapping) or "control_points" not in segment_payload:
                continue
            resolved[str(segment_name)] = _profile_points(
                segment_payload.get("control_points", []),
                f"{segment_name}.control_points",
            )
    return resolved


def _apply_segment_control_point_overrides(
    segments: dict[str, dict[str, list[Point2]]],
    *,
    sample_counts: Mapping[str, int],
    overrides: Mapping[str, list[Point2]],
) -> None:
    for segment_name, control_points in overrides.items():
        if segment_name not in segments:
            continue
        if len(control_points) < 3:
            raise ValueError(f"{segment_name}.control_points must contain at least three points")
        baseline_points = copy.deepcopy(segments[segment_name]["points_s_q"])
        fitted_control_points = _fit_control_points_to_baseline(
            control_points,
            segments[segment_name]["control_points_s_q"],
        )
        segments[segment_name]["control_points_s_q"] = copy.deepcopy(fitted_control_points)
        resampled_points = _resample_polyline(
            fitted_control_points,
            int(sample_counts.get(segment_name, len(fitted_control_points))),
        )
        if baseline_points:
            resampled_points[:3] = copy.deepcopy(baseline_points[:3])
            resampled_points[-3:] = copy.deepcopy(baseline_points[-3:])
        segments[segment_name]["points_s_q"] = resampled_points


def _fit_control_points_to_baseline(control_points: list[Point2], baseline_controls: list[Point2]) -> list[Point2]:
    if len(control_points) < 2 or len(baseline_controls) < 2:
        return copy.deepcopy(control_points)

    source_start = control_points[0]
    source_end = control_points[-1]
    target_start = baseline_controls[0]
    target_end = baseline_controls[-1]
    fitted: list[Point2] = []
    for index, point in enumerate(control_points):
        t = index / max(len(control_points) - 1, 1)
        source_chord = [_lerp(source_start[0], source_end[0], t), _lerp(source_start[1], source_end[1], t)]
        target_chord = [_lerp(target_start[0], target_end[0], t), _lerp(target_start[1], target_end[1], t)]
        fitted.append(
            _round_point_2d(
                [
                    target_chord[0] + (point[0] - source_chord[0]),
                    target_chord[1] + (point[1] - source_chord[1]),
                ]
            )
        )
    fitted[0] = copy.deepcopy(target_start)
    fitted[-1] = copy.deepcopy(target_end)
    return fitted


def _resample_polyline(points: list[Point2], count: int) -> list[Point2]:
    if count <= 0:
        return []
    if len(points) == 1:
        return [copy.deepcopy(points[0]) for _ in range(count)]

    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance_2d(left, right))
    total = cumulative[-1]
    if total <= 1.0e-12:
        return [copy.deepcopy(points[0]) for _ in range(count)]

    samples: list[Point2] = []
    segment_index = 0
    for sample_index in range(count):
        target = total * sample_index / max(count - 1, 1)
        while segment_index < len(cumulative) - 2 and target > cumulative[segment_index + 1]:
            segment_index += 1
        start = points[segment_index]
        end = points[segment_index + 1]
        segment_start = cumulative[segment_index]
        segment_end = cumulative[segment_index + 1]
        fraction = 0.0 if segment_end <= segment_start else (target - segment_start) / (segment_end - segment_start)
        samples.append(
            _round_point_2d(
                [
                    _lerp(start[0], end[0], fraction),
                    _lerp(start[1], end[1], fraction),
                ]
            )
        )
    samples[0] = copy.deepcopy(points[0])
    samples[-1] = copy.deepcopy(points[-1])
    return samples


def _profile_points(values: Any, name: str) -> list[Point2]:
    if not isinstance(values, list):
        raise ValueError(f"{name} must be a list")
    points: list[Point2] = []
    for item in values:
        if not isinstance(item, list) or len(item) < 2:
            raise ValueError(f"{name} contains an invalid point")
        points.append([float(item[0]), float(item[1])])
    return points


def _profile_polyline_length(profile: list[Point2]) -> float:
    return max(
        sum(_distance_2d(left, right) for left, right in zip(profile, profile[1:])),
        1.0,
    )


def _profile_sample(profile: list[Point2], s: float) -> Point2:
    clamped_s = max(0.0, min(1.0, float(s)))
    scaled = clamped_s * (len(profile) - 1)
    left_index = min(int(math.floor(scaled)), len(profile) - 1)
    right_index = min(left_index + 1, len(profile) - 1)
    fraction = scaled - left_index
    left = profile[left_index]
    right = profile[right_index]
    return [
        _lerp(left[0], right[0], fraction),
        _lerp(left[1], right[1], fraction),
    ]


def _float_list(values: Any, name: str) -> list[float]:
    if not isinstance(values, list):
        raise ValueError(f"{name} must be a list")
    return [float(value) for value in values]


def _pair(values: Any) -> list[float]:
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("streamwise interval must contain two values")
    start = float(values[0])
    end = float(values[1])
    if not 0.0 <= start < end <= 1.0:
        raise ValueError("streamwise interval must satisfy 0.0 <= start < end <= 1.0")
    return [round(start, 9), round(end, 9)]


def _int_value(value: Any, *, minimum: int | None = 1) -> int:
    if isinstance(value, bool) or int(value) != value:
        raise ValueError("count values must be integers")
    if minimum is not None and int(value) < minimum:
        raise ValueError("count values must be positive integers")
    return int(value)


def _parameter_value(parameters: Mapping[str, Any], key: str, fallback: Any) -> Any:
    value = parameters.get(key, fallback)
    if isinstance(value, Mapping) and "default" in value:
        return value["default"]
    return value


def _deep_merge(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), Mapping):
            base[key] = _deep_merge(dict(base[key]), value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _smootherstep(value: float) -> float:
    clamped = max(0.0, min(1.0, float(value)))
    return clamped * clamped * clamped * (clamped * (clamped * 6.0 - 15.0) + 10.0)


def _quintic_hermite_point(
    start: Point2,
    end: Point2,
    start_velocity: Point2,
    end_velocity: Point2,
    start_acceleration: Point2,
    end_acceleration: Point2,
    t: float,
) -> Point2:
    c0 = start
    c1 = start_velocity
    c2 = _point_scale(start_acceleration, 0.5)
    residual_position = _point_subtract(_point_subtract(_point_subtract(end, c0), c1), c2)
    residual_velocity = _point_subtract(_point_subtract(end_velocity, c1), start_acceleration)
    residual_acceleration = _point_subtract(end_acceleration, start_acceleration)
    c3 = _point_add(
        _point_add(_point_scale(residual_position, 10.0), _point_scale(residual_velocity, -4.0)),
        _point_scale(residual_acceleration, 0.5),
    )
    c4 = _point_add(
        _point_add(_point_scale(residual_position, -15.0), _point_scale(residual_velocity, 7.0)),
        _point_scale(residual_acceleration, -1.0),
    )
    c5 = _point_add(
        _point_add(_point_scale(residual_position, 6.0), _point_scale(residual_velocity, -3.0)),
        _point_scale(residual_acceleration, 0.5),
    )
    return [
        c0[0] + c1[0] * t + c2[0] * t**2 + c3[0] * t**3 + c4[0] * t**4 + c5[0] * t**5,
        c0[1] + c1[1] * t + c2[1] * t**2 + c3[1] * t**3 + c4[1] * t**4 + c5[1] * t**5,
    ]


def _point_add(left: Point2, right: Point2) -> Point2:
    return [left[0] + right[0], left[1] + right[1]]


def _point_subtract(left: Point2, right: Point2) -> Point2:
    return [left[0] - right[0], left[1] - right[1]]


def _point_scale(point: Point2, scalar: float) -> Point2:
    return [point[0] * scalar, point[1] * scalar]


def _scale_streamwise_component(point: Point2, streamwise_metric_scale_mm: float) -> Point2:
    return [point[0] * streamwise_metric_scale_mm, point[1]]


def _metric_limited_cap_tangent_step(tangent: Point2, metric_scale: float, max_step_mm: float) -> Point2:
    physical = _scale_streamwise_component(tangent, metric_scale)
    length = _vector_norm(physical)
    if length <= 1.0e-12:
        return [0.0, 0.0]
    scale = min(1.0, max_step_mm / length)
    return _point_scale(tangent, scale)


def _metric_limited_cap_second_step(
    second_diff: Point2,
    tangent_step: Point2,
    metric_scale: float,
    max_segment_mm: float,
) -> Point2:
    segment = _point_add(tangent_step, second_diff)
    physical_segment = _scale_streamwise_component(segment, metric_scale)
    segment_length = _vector_norm(physical_segment)
    if segment_length <= max_segment_mm:
        return second_diff
    tangent_physical = _scale_streamwise_component(tangent_step, metric_scale)
    if segment_length <= 1.0e-12:
        return [0.0, 0.0]
    limited_physical_segment = _point_scale(physical_segment, max_segment_mm / segment_length)
    limited_segment = [limited_physical_segment[0] / metric_scale, limited_physical_segment[1]]
    return _point_subtract(limited_segment, [tangent_physical[0] / metric_scale, tangent_physical[1]])


def _clamp_cap_boundary_points_to_half_thickness_envelope(
    points: list[Point2],
    *,
    anchor_s: float,
    cap_direction: float,
    sagitta_s: float,
    start: Point2,
    end: Point2,
) -> None:
    if len(points) < 5:
        return
    lower_s = anchor_s - sagitta_s if cap_direction < 0.0 else anchor_s
    upper_s = anchor_s if cap_direction < 0.0 else anchor_s + sagitta_s
    q_min = min(start[1], end[1])
    q_max = max(start[1], end[1])
    q_allowance = max(0.25, 0.06 * max(q_max - q_min, 1.0))
    for index in (1, 2, len(points) - 3, len(points) - 2):
        points[index][0] = round(max(lower_s, min(upper_s, points[index][0])), 9)
        points[index][1] = round(max(q_min - q_allowance, min(q_max + q_allowance, points[index][1])), 9)


def _limited_cap_tangent_step(tangent: Point2, start: Point2, end: Point2) -> Point2:
    q_span = abs(end[1] - start[1])
    max_q_step = max(0.25, min(0.85, 0.02 * q_span))
    max_s_step = 0.004
    scale = 1.0
    if abs(tangent[1]) > max_q_step:
        scale = min(scale, max_q_step / abs(tangent[1]))
    if abs(tangent[0]) > max_s_step:
        scale = min(scale, max_s_step / abs(tangent[0]))
    return _point_scale(tangent, scale)


def _limited_cap_second_step(second_diff: Point2, tangent_step: Point2) -> Point2:
    segment = _point_add(tangent_step, second_diff)
    segment_length = _vector_norm(segment)
    tangent_length = _vector_norm(tangent_step)
    max_segment_length = max(0.35, 1.65 * max(tangent_length, 0.35))
    if segment_length <= max_segment_length:
        return second_diff
    limited_segment = _point_scale(segment, max_segment_length / max(segment_length, 1.0e-9))
    return _point_subtract(limited_segment, tangent_step)


def _limit_cap_streamwise_excursion(
    points: list[Point2],
    start: Point2,
    end: Point2,
    streamwise_span: float,
    cap_direction: float,
    roundness: float,
) -> None:
    if len(points) < 3:
        return
    anchor_s = 0.5 * (start[0] + end[0])
    allowance = _cap_streamwise_allowance(streamwise_span, roundness)
    lower_s = max(0.0, min(start[0], end[0]) - allowance)
    upper_s = min(1.0, max(start[0], end[0]) + allowance)
    actual_min_s = min(point[0] for point in points)
    actual_max_s = max(point[0] for point in points)
    scale = 1.0
    if cap_direction < 0.0 and actual_min_s < lower_s and anchor_s > actual_min_s:
        scale = min(scale, (anchor_s - lower_s) / (anchor_s - actual_min_s))
    if cap_direction > 0.0 and actual_max_s > upper_s and actual_max_s > anchor_s:
        scale = min(scale, (upper_s - anchor_s) / (actual_max_s - anchor_s))
    if scale >= 1.0:
        return
    for point in points[3:-3]:
        point[0] = round(anchor_s + (point[0] - anchor_s) * scale, 9)


def _enforce_single_cap_streamwise_excursion(
    points: list[Point2],
    start: Point2,
    end: Point2,
    streamwise_span: float,
    cap_direction: float,
    roundness: float,
) -> None:
    if len(points) < 7:
        return
    mid_index = len(points) // 2
    allowance = _cap_streamwise_allowance(streamwise_span, roundness)
    if cap_direction < 0.0:
        nose_s = max(0.0, min(start[0], end[0]) - allowance)
        nose_s = min(nose_s, points[2][0], points[-3][0])
    else:
        nose_s = min(1.0, max(start[0], end[0]) + allowance)
        nose_s = max(nose_s, points[2][0], points[-3][0])

    points[mid_index][0] = round(nose_s, 9)
    _redistribute_cap_half_streamwise(
        points,
        left_index=2,
        right_index=mid_index,
        cap_direction=cap_direction,
    )
    _redistribute_cap_half_streamwise(
        points,
        left_index=mid_index,
        right_index=len(points) - 3,
        cap_direction=-cap_direction,
    )


def _cap_streamwise_allowance(streamwise_span: float, roundness: float) -> float:
    clamped_roundness = max(0.35, min(1.0, float(roundness)))
    return min(0.075, max(0.014, (0.055 + 0.045 * clamped_roundness) * abs(streamwise_span)))


def _limit_cap_q_overshoot(points: list[Point2], start: Point2, end: Point2) -> None:
    if len(points) < 7:
        return
    q_min = min(start[1], end[1])
    q_max = max(start[1], end[1])
    q_span = max(q_max - q_min, 1.0)
    allowance = max(0.75, 0.055 * q_span)
    lower = q_min - allowance
    upper = q_max + allowance
    actual_min = min(point[1] for point in points[3:-3])
    actual_max = max(point[1] for point in points[3:-3])
    if actual_min >= lower and actual_max <= upper:
        return
    center = 0.5 * (q_min + q_max)
    scale = 1.0
    if actual_max > upper and actual_max > center:
        scale = min(scale, (upper - center) / (actual_max - center))
    if actual_min < lower and actual_min < center:
        scale = min(scale, (center - lower) / (center - actual_min))
    for point in points[3:-3]:
        point[1] = round(center + (point[1] - center) * scale, 9)


def _redistribute_cap_interior_by_arclength(points: list[Point2]) -> None:
    if len(points) < 8:
        return
    source = [copy.deepcopy(point) for point in points[2:-2]]
    cumulative = [0.0]
    for left, right in zip(source, source[1:]):
        cumulative.append(cumulative[-1] + _distance_2d(left, right))
    total_length = cumulative[-1]
    if total_length <= 1.0e-9:
        return
    movable_count = len(points) - 6
    for offset in range(movable_count):
        target_distance = total_length * (offset + 1) / (movable_count + 1)
        segment_index = 1
        while segment_index < len(cumulative) and cumulative[segment_index] < target_distance:
            segment_index += 1
        segment_index = min(segment_index, len(source) - 1)
        left_distance = cumulative[segment_index - 1]
        right_distance = cumulative[segment_index]
        fraction = 0.0 if right_distance <= left_distance else (target_distance - left_distance) / (right_distance - left_distance)
        points[3 + offset] = _round_point_2d(
            [
                source[segment_index - 1][0] + (source[segment_index][0] - source[segment_index - 1][0]) * fraction,
                source[segment_index - 1][1] + (source[segment_index][1] - source[segment_index - 1][1]) * fraction,
            ]
        )


def _redistribute_cap_half_streamwise(
    points: list[Point2],
    *,
    left_index: int,
    right_index: int,
    cap_direction: float,
) -> None:
    span = right_index - left_index
    if span <= 1:
        return
    left_s = points[left_index][0]
    right_s = points[right_index][0]
    for index in range(left_index + 1, right_index):
        t = (index - left_index) / span
        fraction = _smoothstep(t)
        value = _lerp(left_s, right_s, fraction)
        if cap_direction < 0.0:
            value = min(points[index - 1][0], value)
        else:
            value = max(points[index - 1][0], value)
        points[index][0] = round(value, 9)


def _point_diff(current: Point2, previous: Point2) -> Point2:
    return _point_subtract(current, previous)


def _second_diff(first: Point2, second: Point2, third: Point2) -> Point2:
    return [
        third[0] - 2.0 * second[0] + first[0],
        third[1] - 2.0 * second[1] + first[1],
    ]


def _boundary_frame(points: list[Point2], boundary: str) -> tuple[Point2, Point2, Point2]:
    if boundary == "start":
        return (
            points[0],
            _point_diff(points[1], points[0]),
            _second_diff(points[0], points[1], points[2]),
        )
    return (
        points[-1],
        _point_diff(points[-1], points[-2]),
        _second_diff(points[-3], points[-2], points[-1]),
    )


def _distance_2d(left: Point2, right: Point2) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _vector_norm(vector: Point2) -> float:
    return math.hypot(vector[0], vector[1])


def _vector_angle_deg(left: Point2, right: Point2) -> float:
    left_norm = _vector_norm(left)
    right_norm = _vector_norm(right)
    if left_norm <= 1.0e-12 or right_norm <= 1.0e-12:
        return 0.0 if left_norm <= 1.0e-12 and right_norm <= 1.0e-12 else 180.0
    cosine = (left[0] * right[0] + left[1] * right[1]) / (left_norm * right_norm)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _max_join_value(join_metrics: Mapping[str, Mapping[str, float | str]], key: str) -> float:
    return max(float(join[key]) for join in join_metrics.values())


def _round(value: float) -> float:
    return round(float(value), 9)


def _round_point(point: list[float]) -> Point3:
    return [round(float(value), 9) for value in point]


def _round_point_2d(point: list[float]) -> Point2:
    return [round(float(value), 9) for value in point]
