from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any


MATH_PARAMETERIZATION = "v1_1_2_canonical_nurbs_parameterization"
CANONICAL_PAYLOAD_VERSION = "1.1.2"
ROUND_DIGITS = 6


def clamped_uniform_knots(point_count: int, degree: int) -> list[float]:
    if point_count <= 0:
        raise ValueError("point_count must be positive")
    safe_degree = min(max(int(degree), 1), point_count - 1)
    interior_count = point_count - safe_degree - 1
    knots = [0.0 for _ in range(safe_degree + 1)]
    for index in range(1, interior_count + 1):
        knots.append(round(index / (interior_count + 1), 6))
    knots.extend(1.0 for _ in range(safe_degree + 1))
    return knots


def evaluate_nurbs_curve(curve: dict[str, Any], u: float) -> list[float]:
    points = [[float(value) for value in point] for point in curve["control_points"]]
    weights = [float(value) for value in curve.get("weights", [1.0] * len(points))]
    degree = int(curve.get("degree", 1))
    knots = _curve_knots(curve, len(points), degree)
    basis = [_basis(index, degree, _clamp01(u), knots) for index in range(len(points))]
    denominator = sum(basis[index] * weights[index] for index in range(len(points)))
    if abs(denominator) <= 1.0e-12:
        raise ValueError("NURBS curve denominator is zero")
    dimensions = len(points[0])
    return [
        _round(
            sum(basis[index] * weights[index] * points[index][axis] for index in range(len(points)))
            / denominator
        )
        for axis in range(dimensions)
    ]


def evaluate_nurbs_surface(surface: dict[str, Any], u: float, v: float) -> list[float]:
    grid = surface["control_points"]
    degree_u = int(surface.get("degree_u", surface.get("degree_s", 1)))
    degree_v = int(surface.get("degree_v", surface.get("degree_h", 1)))
    knots_u = _surface_knots(surface, "u", len(grid), degree_u)
    knots_v = _surface_knots(surface, "v", len(grid[0]), degree_v)
    weights = surface.get("weights") or [[1.0 for _ in row] for row in grid]
    basis_u = [_basis(index, degree_u, _clamp01(u), knots_u) for index in range(len(grid))]
    basis_v = [_basis(index, degree_v, _clamp01(v), knots_v) for index in range(len(grid[0]))]
    dimensions = len(grid[0][0])
    denominator = 0.0
    numerator = [0.0 for _ in range(dimensions)]
    for i, row in enumerate(grid):
        for j, point in enumerate(row):
            coefficient = basis_u[i] * basis_v[j] * float(weights[i][j])
            denominator += coefficient
            for axis in range(dimensions):
                numerator[axis] += coefficient * float(point[axis])
    if abs(denominator) <= 1.0e-12:
        raise ValueError("NURBS surface denominator is zero")
    return [_round(value / denominator) for value in numerator]


def canonical_nurbs_from_v11_defaults(
    parameters: Mapping[str, Any],
    defaults: Mapping[str, Any],
    *,
    source: str = "translated_from_legacy_v1_1",
) -> dict[str, Any]:
    hub_points = _profile_points(defaults["hub_profile_rz_mm"])
    tip_points = _profile_points(defaults["tip_or_shroud_profile_rz_mm"])
    average_thickness = _float_default(
        defaults,
        "average_blade_thickness_mm",
        _parameter_value(parameters, "blade_thickness_mm", 1.0),
    )
    maximum_thickness = _float_default(
        defaults,
        "maximum_blade_thickness_mm",
        max(average_thickness, _parameter_value(parameters, "blade_thickness_mm", average_thickness)),
    )
    span_stations = [float(value) for value in defaults.get("span_stations_h", [0.0, 0.25, 0.5, 0.75, 1.0])]
    skeleton = _skeleton_field(defaults)
    thickness = _thickness_field(defaults, average_thickness, maximum_thickness)
    root_offset = _float_default(
        defaults,
        "root_blade_lift_mm",
        _float_default(defaults, "root_attachment_lift_mm", average_thickness),
    )
    tip_offset = (
        _float_default(defaults, "shroud_blade_inset_mm", 0.0)
        if defaults.get("tip_attachment_mode") == "closed_shroud_attachment"
        else 0.0
    )
    payload = {
        "canonical_payload_version": CANONICAL_PAYLOAD_VERSION,
        "math_parameterization": MATH_PARAMETERIZATION,
        "canonical_input_source": source,
        "support_profiles": {
            "hub_profile": _nurbs_curve("hub_profile", hub_points),
            "tip_or_shroud_profile": _nurbs_curve("tip_or_shroud_profile", tip_points),
        },
        "active_span_policy": {
            "root_offset": {
                "mode": "thickness_ratio",
                "ratio_of_local_thickness": _round(root_offset / max(average_thickness, 1.0e-9)),
                "resolved_constant_mm": _round(root_offset),
            },
            "tip_offset": {
                "mode": "closed_shroud_thickness_ratio_or_open_zero",
                "ratio_of_local_thickness": _round(tip_offset / max(average_thickness, 1.0e-9)),
                "resolved_constant_mm": _round(tip_offset),
            },
            "report_resolved_offsets": True,
        },
        "blade_population": {
            "main_blade_count": int(defaults["main_blade_count"]),
            "splitter_blade_count": int(defaults.get("splitter_blade_count", 0)),
            "splitter_positioning_mode": str(defaults.get("splitter_positioning_mode", "main_passage_bisector")),
            "splitter_passage_fraction": float(defaults.get("splitter_passage_fraction", 0.5)),
            "main_streamwise_interval_s": list(defaults.get("main_streamwise_interval_s", [0.06, 0.94])),
            "splitter_streamwise_interval_s": list(defaults.get("splitter_streamwise_interval_s", [0.35, 0.88])),
            "splitter_phase_offset_pitch": float(defaults.get("splitter_phase_offset_pitch", 0.5)),
        },
        "blade_skeleton_field": skeleton,
        "thickness_field": thickness,
        "section_loop_family": {
            "mode": "skeleton_thickness_caps",
            "span_stations_h": span_stations,
            "segments": {
                "pressure_side": {"construction": "skeleton_minus_half_thickness"},
                "suction_side": {"construction": "skeleton_plus_half_thickness"},
                "leading_edge_cap": _cap_intent(defaults, "leading_edge_cap_roundness"),
                "trailing_edge_cap": _cap_intent(defaults, "trailing_edge_cap_roundness"),
            },
        },
        "attachment_policy": _attachment_policy(defaults, average_thickness),
        "pose_field": _pose_field(parameters, defaults),
        "sampling_policy": _sampling_policy(defaults),
    }
    payload["metrics"] = _canonical_metrics(payload, average_thickness, maximum_thickness)
    return payload


def _curve_knots(curve: Mapping[str, Any], point_count: int, degree: int) -> list[float]:
    knots = curve.get("knots", "clamped_uniform")
    if knots == "clamped_uniform":
        return clamped_uniform_knots(point_count, degree)
    return [float(value) for value in knots]


def _surface_knots(surface: Mapping[str, Any], axis: str, point_count: int, degree: int) -> list[float]:
    knots = surface.get(f"knots_{axis}")
    if knots is None and axis == "u":
        knots = surface.get("knots_s")
    if knots is None and axis == "v":
        knots = surface.get("knots_h")
    if knots == "clamped_uniform" or knots is None:
        return clamped_uniform_knots(point_count, degree)
    return [float(value) for value in knots]


def _nurbs_curve(name: str, points: list[list[float]]) -> dict[str, Any]:
    degree = min(3, max(len(points) - 1, 1))
    return {
        "kind": "nurbs_curve",
        "id": name,
        "coordinate_system": "rz_meridional_mm",
        "degree": degree,
        "control_points": copy.deepcopy(points),
        "weights": [1.0 for _ in points],
        "knots": clamped_uniform_knots(len(points), degree),
    }


def _skeleton_field(defaults: Mapping[str, Any]) -> dict[str, Any]:
    s0, s1 = _streamwise_interval(defaults.get("main_streamwise_interval_s", [0.06, 0.94]))
    main_q = _float_default(defaults, "main_flow_turn_q_mm", 1.0)
    delta_q = _float_default(defaults, "spanwise_flow_turn_delta_q_mm", 0.0)
    bow_q = _float_default(defaults, "midspan_bow_q_mm", 0.0)
    s_columns = [s0, _round(_lerp(s0, s1, 0.28)), _round(_lerp(s0, s1, 0.62)), s1]
    control_points = [
        [
            [s_columns[0], 0.0, 0.0],
            [s_columns[1], 0.0, _round(main_q * 0.225)],
            [s_columns[2], 0.0, _round(main_q * 0.59375)],
            [s_columns[3], 0.0, _round(main_q)],
        ],
        [
            [s_columns[0], 0.5, _round(bow_q * 0.9)],
            [s_columns[1], 0.5, _round(main_q * 0.2875 + bow_q)],
            [s_columns[2], 0.5, _round(main_q * 0.68125 + bow_q * 1.55)],
            [s_columns[3], 0.5, _round(main_q + bow_q)],
        ],
        [
            [s_columns[0], 1.0, _round(delta_q * 0.394737)],
            [s_columns[1], 1.0, _round(main_q * 0.34375 + delta_q * 0.368421)],
            [s_columns[2], 1.0, _round(main_q * 0.78125 + delta_q)],
            [s_columns[3], 1.0, _round(main_q + delta_q)],
        ],
    ]
    return _surface(
        "s_h_q_mm",
        control_points,
        degree_s=3,
        degree_h=2,
        extra={"field_role": "blade_skeleton"},
    )


def _thickness_field(
    defaults: Mapping[str, Any],
    average_thickness: float,
    maximum_thickness: float,
) -> dict[str, Any]:
    s0, s1 = _streamwise_interval(defaults.get("main_streamwise_interval_s", [0.06, 0.94]))
    s_columns = [s0, _round(_lerp(s0, s1, 0.28)), _round(_lerp(s0, s1, 0.62)), s1]
    delta = max(maximum_thickness - average_thickness, 0.0)
    trailing = max(average_thickness * 0.55, 1.0)
    control_points = [
        [[s_columns[0], 0.0, _round(max(average_thickness - 0.30 * delta, 1.0))], [s_columns[1], 0.0, _round(maximum_thickness)], [s_columns[2], 0.0, _round(average_thickness + 0.50 * delta)], [s_columns[3], 0.0, _round(trailing)]],
        [[s_columns[0], 0.5, _round(max(average_thickness - 0.38 * delta, 1.0))], [s_columns[1], 0.5, _round(average_thickness)], [s_columns[2], 0.5, _round(max(average_thickness - 0.07 * delta, 1.0))], [s_columns[3], 0.5, _round(max(trailing - 1.0, 1.0))]],
        [[s_columns[0], 1.0, _round(max(average_thickness - 0.50 * delta, 1.0))], [s_columns[1], 1.0, _round(max(average_thickness - 0.33 * delta, 1.0))], [s_columns[2], 1.0, _round(max(average_thickness - 0.50 * delta, 1.0))], [s_columns[3], 1.0, _round(max(trailing - 2.0, 1.0))]],
    ]
    return _surface(
        "s_h_thickness_mm",
        control_points,
        degree_s=3,
        degree_h=2,
        extra={"field_role": "thickness", "minimum_thickness_mm": 1.0},
    )


def _cap_intent(defaults: Mapping[str, Any], key: str) -> dict[str, Any]:
    roundness = _float_default(defaults, key, 0.56)
    return {
        "kind": "nurbs_cap_curve",
        "roundness": _round(roundness),
        "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
        "continuity_goal": "C2",
    }


def _attachment_policy(defaults: Mapping[str, Any], average_thickness: float) -> dict[str, Any]:
    root_width = _float_default(defaults, "root_attachment_width_mm", average_thickness)
    tip_mode = str(defaults.get("tip_attachment_mode", "open_tip_dome"))
    shroud_width = _float_default(defaults, "shroud_attachment_width_mm", root_width)
    policy = {
        "root_to_hub": {
            "kind": "nurbs_ribbon",
            "support_boundary": "hub_profile",
            "blade_boundary": "active_span_h0_section_loop",
            "width_policy": {
                "mode": "thickness_ratio",
                "ratio": _round(root_width / max(average_thickness, 1.0e-9)),
            },
            "lift_policy": {"mode": "active_span_policy_root_offset"},
            "continuity_goal": "G2_measured",
        },
        "tip_to_shroud": {
            "kind": "nurbs_ribbon",
            "enabled_when": "closed",
            "support_boundary": "tip_or_shroud_profile",
            "blade_boundary": "active_span_h1_section_loop",
            "width_policy": {
                "mode": "thickness_ratio",
                "ratio": _round(shroud_width / max(average_thickness, 1.0e-9)),
            },
            "lift_policy": {"mode": "active_span_policy_tip_offset"},
            "continuity_goal": "G2_measured",
        },
        "open_tip": {
            "kind": "nurbs_cover_surface",
            "enabled_when": "open",
            "boundary": "active_span_h1_section_loop",
            "continuity_goal": "G1_measured",
            "tip_attachment_mode": tip_mode,
        },
    }
    return policy


def _pose_field(parameters: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    del defaults
    wrap_deg = _parameter_value(parameters, "blade_wrap_deg", 0.0)
    blade_lean = _parameter_value(parameters, "blade_lean_deg", 0.0)
    leading_lean = _parameter_value(parameters, "leading_edge_lean_deg", blade_lean)
    trailing_lean = _parameter_value(parameters, "trailing_edge_lean_deg", blade_lean)
    leading_sweep = _parameter_value(parameters, "leading_edge_sweep_mm", 0.0)
    trailing_sweep = _parameter_value(parameters, "trailing_edge_sweep_mm", 0.0)
    control_points = [
        [[0.0, 0.0, _round(leading_lean + leading_sweep * 0.05)], [0.5, 0.0, _round(-0.42 * wrap_deg + blade_lean)], [1.0, 0.0, _round(-wrap_deg + trailing_sweep * 0.05)]],
        [[0.0, 1.0, _round(leading_lean + blade_lean)], [0.5, 1.0, _round(-0.32 * wrap_deg + blade_lean)], [1.0, 1.0, _round(-0.83 * wrap_deg + trailing_lean)]],
    ]
    return _surface(
        "s_h_theta_offset_deg",
        control_points,
        degree_s=2,
        degree_h=1,
        extra={"field_role": "pose"},
    )


def _sampling_policy(defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile_revolve_sample_count": int(defaults.get("profile_revolve_sample_count", 73)),
        "side_sample_count": int(defaults.get("side_sample_count", 73)),
        "edge_cap_sample_count": int(defaults.get("edge_cap_sample_count", 49)),
        "surface_span_sample_count": int(defaults.get("surface_span_sample_count", 13)),
        "theta_sample_count": int(defaults.get("theta_sample_count", 97)),
        "root_short_direction_sample_count": int(defaults.get("root_short_direction_sample_count", 9)),
        "closed_shroud_short_direction_sample_count": int(defaults.get("closed_shroud_short_direction_sample_count", 9)),
    }


def _canonical_metrics(
    payload: Mapping[str, Any],
    average_thickness: float,
    maximum_thickness: float,
) -> dict[str, Any]:
    root_offset = float(payload["active_span_policy"]["root_offset"]["resolved_constant_mm"])
    tip_offset = float(payload["active_span_policy"]["tip_offset"]["resolved_constant_mm"])
    skeleton_points = payload["blade_skeleton_field"]["control_points"]
    thickness_points = payload["thickness_field"]["control_points"]
    leading_target = 0.5 * average_thickness
    trailing_target = 0.5 * average_thickness
    leading_resolved = leading_target * float(payload["section_loop_family"]["segments"]["leading_edge_cap"]["roundness"])
    trailing_resolved = trailing_target * float(payload["section_loop_family"]["segments"]["trailing_edge_cap"]["roundness"])
    thickness_values = [float(point[2]) for row in thickness_points for point in row]
    return {
        "canonical_payload_version": payload["canonical_payload_version"],
        "canonical_input_source": payload["canonical_input_source"],
        "support_profile_control_count": {
            name: len(profile["control_points"])
            for name, profile in payload["support_profiles"].items()
        },
        "active_root_offset_min_mm": _round(root_offset),
        "active_root_offset_max_mm": _round(root_offset),
        "active_tip_offset_min_mm": _round(tip_offset),
        "active_tip_offset_max_mm": _round(tip_offset),
        "skeleton_field_control_net_shape": [len(skeleton_points), len(skeleton_points[0])],
        "thickness_min_mm": _round(max(min(thickness_values), 1.0)),
        "thickness_max_mm": _round(max(max(thickness_values), maximum_thickness)),
        "loop_station_count": len(payload["section_loop_family"]["span_stations_h"]),
        "max_join_position_gap_mm": 0.0,
        "max_join_tangent_angle_deg": 0.0,
        "max_join_curvature_proxy_mismatch": 0.0,
        "leading_cap_sagitta_target_min_mm": _round(leading_target),
        "leading_cap_sagitta_resolved_min_mm": _round(leading_resolved),
        "trailing_cap_sagitta_target_min_mm": _round(trailing_target),
        "trailing_cap_sagitta_resolved_min_mm": _round(trailing_resolved),
    }


def _surface(
    coordinate_system: str,
    control_points: list[list[list[float]]],
    *,
    degree_s: int,
    degree_h: int,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    weights = [[1.0 for _ in row] for row in control_points]
    surface = {
        "kind": "nurbs_surface",
        "coordinate_system": coordinate_system,
        "degree_s": degree_s,
        "degree_h": degree_h,
        "degree_u": degree_s,
        "degree_v": degree_h,
        "control_points": copy.deepcopy(control_points),
        "weights": weights,
        "knots_s": "clamped_uniform",
        "knots_h": "clamped_uniform",
        "knots_u": clamped_uniform_knots(len(control_points), degree_s),
        "knots_v": clamped_uniform_knots(len(control_points[0]), degree_h),
    }
    if extra:
        surface.update(copy.deepcopy(dict(extra)))
    return surface


def _profile_points(raw_points: Any) -> list[list[float]]:
    points = []
    for point in raw_points:
        if not isinstance(point, list) or len(point) < 2:
            raise ValueError("profile points must be [r, z] lists")
        points.append([_round(float(point[0])), _round(float(point[1]))])
    if len(points) < 2:
        raise ValueError("profile must contain at least two points")
    return points


def _parameter_value(parameters: Mapping[str, Any], key: str, fallback: Any) -> Any:
    value = parameters.get(key, fallback)
    if isinstance(value, Mapping) and "default" in value:
        return value["default"]
    return value


def _float_default(values: Mapping[str, Any], key: str, fallback: float) -> float:
    value = values.get(key, fallback)
    if isinstance(value, Mapping) and "default" in value:
        value = value["default"]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    if not math.isfinite(numeric):
        numeric = fallback
    return numeric


def _streamwise_interval(values: Any) -> tuple[float, float]:
    if not isinstance(values, list) or len(values) != 2:
        return 0.06, 0.94
    return _round(float(values[0])), _round(float(values[1]))


def _basis(index: int, degree: int, u: float, knots: list[float]) -> float:
    last_basis_index = len(knots) - degree - 2
    if degree == 0:
        if (knots[index] <= u < knots[index + 1]) or (u >= knots[-1] and index == last_basis_index):
            return 1.0
        return 0.0
    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left_term = 0.0
    right_term = 0.0
    if left_denominator > 0.0:
        left_term = ((u - knots[index]) / left_denominator) * _basis(index, degree - 1, u, knots)
    if right_denominator > 0.0:
        right_term = ((knots[index + degree + 1] - u) / right_denominator) * _basis(index + 1, degree - 1, u, knots)
    return left_term + right_term


def _clamp01(value: float) -> float:
    clamped = max(0.0, min(1.0, float(value)))
    if clamped >= 1.0:
        return math.nextafter(1.0, 0.0)
    return clamped


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction


def _round(value: float) -> float:
    return round(float(value), ROUND_DIGITS)
