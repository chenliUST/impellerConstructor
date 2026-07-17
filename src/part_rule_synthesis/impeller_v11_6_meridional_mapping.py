from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_curve
from part_rule_synthesis.impeller_v11_6_section_recovery import (
    SectionRecoveryError,
    solve_meridional_correspondence,
)


def project_rz_points_to_meridional_s(
    profile_fit: Mapping[str, Any],
    points_rz_mm: Sequence[Sequence[float]],
    *,
    tip_profile_fit: Mapping[str, Any] | None = None,
    sample_count: int = 513,
    interval_quantiles: tuple[float, float] = (0.01, 0.99),
    maximum_projection_residual_mm: float | None = None,
) -> dict[str, Any]:
    """Project R-Z evidence to an authenticated meridian or hub-tip strip."""

    try:
        count = max(33, int(sample_count))
        evidence = np.asarray(points_rz_mm, dtype=float)
        if evidence.ndim != 2 or evidence.shape[1] != 2 or len(evidence) < 1:
            return _rejected("invalid_meridional_projection_evidence")
        if not np.all(np.isfinite(evidence)):
            return _rejected("invalid_meridional_projection_evidence")
        correspondence_diagnostics: dict[str, Any] | None = None
        if tip_profile_fit is None:
            curve = _curve_descriptor(profile_fit)
            parameters = np.linspace(0.0, 1.0, count)
            samples = np.asarray(
                [evaluate_nurbs_curve(curve, float(value)) for value in parameters],
                dtype=float,
            )
            segment_lengths = np.linalg.norm(np.diff(samples, axis=0), axis=1)
            arc_length = float(np.sum(segment_lengths))
            if not np.isfinite(arc_length) or arc_length <= 1.0e-9:
                return _rejected("degenerate_meridional_profile")
            cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths))) / arc_length
            delta = evidence[:, None, :] - samples[None, :, :]
            distances = np.linalg.norm(delta, axis=2)
            nearest = np.argmin(distances, axis=1)
            projected_s = cumulative[nearest]
            residuals = distances[np.arange(len(evidence)), nearest]
            method = "nearest_projection_to_normalized_nurbs_arc_length"
        else:
            correspondence = solve_meridional_correspondence(
                profile_fit,
                tip_profile_fit,
                sample_count=max(129, min(count, 513)),
            )
            hub = np.asarray(correspondence.hub_points_rz_mm, dtype=float)
            tip = np.asarray(correspondence.tip_points_rz_mm, dtype=float)
            segment_lengths = np.linalg.norm(np.diff(hub, axis=0), axis=1)
            arc_length = float(np.sum(segment_lengths))
            if not np.isfinite(arc_length) or arc_length <= 1.0e-9:
                return _rejected("degenerate_meridional_profile")
            cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths))) / arc_length
            projections = [
                _project_point_to_support_strip(point, hub, tip, cumulative)
                for point in evidence
            ]
            projected_s = np.asarray([item[0] for item in projections], dtype=float)
            residuals = np.asarray([item[1] for item in projections], dtype=float)
            method = "nearest_projection_to_corresponded_hub_tip_support_strip"
            correspondence_diagnostics = {
                "tip_reversed": bool(correspondence.tip_reversed),
                "closest_residual_rms_mm": float(
                    correspondence.closest_residual_rms_mm
                ),
                "closest_residual_max_mm": float(
                    correspondence.closest_residual_max_mm
                ),
                "minimum_parameter_step": float(
                    correspondence.minimum_parameter_step
                ),
            }
        projected_s = np.clip(np.asarray(projected_s, dtype=float), 0.0, 1.0)
        residual_gate = (
            max(1.0, 0.25 * arc_length)
            if maximum_projection_residual_mm is None
            else float(maximum_projection_residual_mm)
        )
        if not np.isfinite(residual_gate) or residual_gate <= 0.0:
            return _rejected("invalid_meridional_projection_residual_gate")
        residual_maximum = float(np.max(residuals))
        residual_p95 = float(np.quantile(residuals, 0.95))
        if residual_maximum > residual_gate:
            return _rejected(
                "meridional_projection_residual_exceeded",
                maximum_projection_residual_mm=residual_gate,
                projection_residual_maximum_mm=residual_maximum,
                projection_residual_p95_mm=residual_p95,
                projected_point_count=int(len(evidence)),
            )
        low, high = (float(value) for value in interval_quantiles)
        if not 0.0 <= low <= high <= 1.0:
            return _rejected("invalid_meridional_interval_quantiles")
        interval = [
            float(np.quantile(projected_s, low)),
            float(np.quantile(projected_s, high)),
        ]
        if interval[1] - interval[0] <= 1.0e-6:
            return _rejected("degenerate_streamwise_interval")
    except (KeyError, TypeError, ValueError, ZeroDivisionError, SectionRecoveryError):
        return _rejected("invalid_meridional_profile_fit")
    result = {
        "status": "PASS",
        "method": method,
        "coordinate_system": "canonical_meridional_r_z_mm",
        "streamwise_interval_s": interval,
        "meridional_arc_length_mm": arc_length,
        "projection_residual_rms_mm": float(np.sqrt(np.mean(residuals**2))),
        "projection_residual_p95_mm": residual_p95,
        "projection_residual_maximum_mm": residual_maximum,
        "maximum_projection_residual_mm": residual_gate,
        "projected_point_count": int(len(evidence)),
        "profile_sample_count": count,
        "interval_quantiles": [low, high],
    }
    if correspondence_diagnostics is not None:
        result["support_correspondence"] = correspondence_diagnostics
    return result


def _curve_descriptor(profile_fit: Mapping[str, Any]) -> dict[str, Any]:
    control_points = profile_fit.get("control_points_rz_mm")
    if not isinstance(control_points, Sequence) or len(control_points) < 2:
        raise ValueError("profile has no R-Z control polygon")
    weights = profile_fit.get("weights")
    if not isinstance(weights, Sequence) or len(weights) != len(control_points):
        weights = [1.0] * len(control_points)
    knots = profile_fit.get("knots")
    if not knots:
        knots = "clamped_uniform"
    return {
        "degree": int(profile_fit.get("degree", 1)),
        "knots": knots if isinstance(knots, str) else list(knots),
        "weights": list(weights),
        "control_points": [list(point) for point in control_points],
    }


def _project_point_to_support_strip(
    point: np.ndarray,
    hub: np.ndarray,
    tip: np.ndarray,
    streamwise_s: np.ndarray,
) -> tuple[float, float]:
    best_s = 0.0
    best_distance = float("inf")
    for index in range(len(hub) - 1):
        s0 = float(streamwise_s[index])
        s1 = float(streamwise_s[index + 1])
        triangles = (
            (
                (hub[index], s0),
                (hub[index + 1], s1),
                (tip[index + 1], s1),
            ),
            (
                (hub[index], s0),
                (tip[index + 1], s1),
                (tip[index], s0),
            ),
        )
        for triangle in triangles:
            candidate_s, distance = _project_point_to_triangle(point, triangle)
            if distance < best_distance:
                best_s = candidate_s
                best_distance = distance
                if distance <= 1.0e-12:
                    return best_s, 0.0
    return best_s, best_distance


def _project_point_to_triangle(
    point: np.ndarray,
    triangle: Sequence[tuple[np.ndarray, float]],
) -> tuple[float, float]:
    a, b, c = (np.asarray(vertex[0], dtype=float) for vertex in triangle)
    s_values = [float(vertex[1]) for vertex in triangle]
    denominator = _cross_2d(b - a, c - a)
    if abs(denominator) > 1.0e-14:
        wb = _cross_2d(point - a, c - a) / denominator
        wc = _cross_2d(b - a, point - a) / denominator
        wa = 1.0 - wb - wc
        if min(wa, wb, wc) >= -1.0e-10:
            return (
                wa * s_values[0] + wb * s_values[1] + wc * s_values[2],
                0.0,
            )

    candidates = (
        _project_point_to_segment(point, a, b, s_values[0], s_values[1]),
        _project_point_to_segment(point, b, c, s_values[1], s_values[2]),
        _project_point_to_segment(point, c, a, s_values[2], s_values[0]),
    )
    return min(candidates, key=lambda item: (item[1], item[0]))


def _project_point_to_segment(
    point: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    first_s: float,
    second_s: float,
) -> tuple[float, float]:
    vector = second - first
    length_sq = float(np.dot(vector, vector))
    fraction = (
        0.0
        if length_sq <= 1.0e-18
        else float(np.clip(np.dot(point - first, vector) / length_sq, 0.0, 1.0))
    )
    projection = first + fraction * vector
    return (
        first_s + fraction * (second_s - first_s),
        float(np.linalg.norm(point - projection)),
    )


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _rejected(reason: str, **details: Any) -> dict[str, Any]:
    return {
        "status": "REJECTED",
        "failure_reason": reason,
        "method": "nearest_projection_to_normalized_nurbs_arc_length",
        "coordinate_system": "canonical_meridional_r_z_mm",
        **details,
    }
