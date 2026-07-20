from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.interpolate import PchipInterpolator

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    MeridionalCorrespondence,
    solve_meridional_correspondence,
)


CONTRACT_ID = "impeller_v1_1_6_direct_section_curve_network_r16_1"
SOURCE_FRAME = "source_step_xyz_mm"
CANONICAL_FRAME = "canonical_axis_frame_xyz_mm"

_ROLE_BY_SEGMENT = {
    "side_a": "side_a",
    "side_b": "side_b",
    "leading_edge": "leading_edge",
    "trailing_edge": "trailing_edge",
}


class SectionCurveAuthorityError(ValueError):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.details = dict(details or {})


def solve_boundary_guided_meridional_correspondence(
    hub_profile_rz_mm: Sequence[Sequence[float]],
    tip_profile_rz_mm: Sequence[Sequence[float]],
    *,
    streamwise_anchors: Sequence[Sequence[float]],
    sample_count: int = 129,
) -> MeridionalCorrespondence:
    """Pair hub and tip meridians using authenticated blade-side boundaries."""

    hub = _points(hub_profile_rz_mm, 2, "hub_profile_rz_mm")
    tip = _points(tip_profile_rz_mm, 2, "tip_profile_rz_mm")
    anchors = np.asarray(streamwise_anchors, dtype=float)
    if (
        anchors.ndim != 2
        or anchors.shape[1] != 2
        or len(anchors) < 3
        or np.any(~np.isfinite(anchors))
        or np.any(anchors < 0.0)
        or np.any(anchors > 1.0)
    ):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "source-side streamwise correspondence requires at least three finite anchors",
        )
    order = np.argsort(anchors[:, 0], kind="stable")
    anchors = anchors[order]
    unique_hub, inverse = np.unique(np.round(anchors[:, 0], 12), return_inverse=True)
    mapped_tip = np.zeros(len(unique_hub), dtype=float)
    for index in range(len(unique_hub)):
        mapped_tip[index] = float(np.median(anchors[inverse == index, 1]))
    if len(unique_hub) < 3 or np.any(np.diff(unique_hub) <= 1.0e-9):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "source-side streamwise anchors do not span an ordered hub interval",
        )
    mapped_tip = _strict_monotone_unit_values(mapped_tip)
    count = max(17, int(sample_count))
    hub_u = np.linspace(0.0, 1.0, count)
    interpolator = PchipInterpolator(unique_hub, mapped_tip, extrapolate=True)
    tip_u = np.clip(interpolator(hub_u), 0.0, 1.0)
    tip_u = _strict_monotone_unit_values(tip_u)
    hub_points = _sample_polyline_by_normalized_arc(hub, hub_u)
    tip_points = _sample_polyline_by_normalized_arc(tip, tip_u)
    minimum_step = float(np.min(np.diff(tip_u)))
    anchor_fit = np.interp(unique_hub, hub_u, tip_u)
    anchor_residual = np.abs(anchor_fit - mapped_tip)
    return MeridionalCorrespondence(
        hub_parameters=tuple(float(value) for value in hub_u),
        tip_parameters=tuple(float(value) for value in tip_u),
        hub_points_rz_mm=tuple(tuple(float(value) for value in point) for point in hub_points),
        tip_points_rz_mm=tuple(tuple(float(value) for value in point) for point in tip_points),
        tip_reversed=False,
        closest_residual_rms_mm=float(
            math.sqrt(float(np.mean(anchor_residual**2)))
        ),
        closest_residual_max_mm=float(np.max(anchor_residual)),
        minimum_parameter_step=minimum_step,
        method="source_side_boundary_guided_monotone_pchip",
    )


def _strict_monotone_unit_values(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    result = np.maximum.accumulate(result)
    epsilon = 1.0e-9
    for index in range(1, len(result)):
        result[index] = max(result[index], result[index - 1] + epsilon)
    span = result[-1] - result[0]
    if span <= epsilon:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "source-side streamwise anchors collapse the tip correspondence",
        )
    if result[-1] > 1.0:
        result = result[0] + (result - result[0]) * (1.0 - result[0]) / span
    return np.clip(result, 0.0, 1.0)


def _sample_polyline_by_normalized_arc(
    points: np.ndarray, parameters: np.ndarray
) -> np.ndarray:
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = float(np.sum(lengths))
    if total <= 1.0e-12:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "meridional support profile has zero arc length",
        )
    cumulative = np.concatenate(([0.0], np.cumsum(lengths))) / total
    return np.column_stack(
        [np.interp(parameters, cumulative, points[:, axis]) for axis in range(2)]
    )


@dataclass(frozen=True)
class ActiveSpanField:
    streamwise_u: tuple[float, ...]
    hub_points_rz_mm: tuple[tuple[float, float], ...]
    tip_points_rz_mm: tuple[tuple[float, float], ...]
    root_h: tuple[float, ...]
    tip_h: tuple[float, ...]
    root_lift_mm: tuple[float, ...]
    tip_lift_mm: tuple[float, ...]
    root_width_mm: tuple[float, ...]
    tip_width_mm: tuple[float, ...]
    retained_root_boundary_points_rz_mm: tuple[tuple[float, float], ...]
    retained_tip_boundary_points_rz_mm: tuple[tuple[float, float], ...]
    root_carrier_clearance_mm: tuple[float, ...]
    tip_carrier_clearance_mm: tuple[float, ...]
    root_carrier_clearance_cap_mm: tuple[float, ...]
    tip_carrier_clearance_cap_mm: tuple[float, ...]
    active_root_points_rz_mm: tuple[tuple[float, float], ...]
    active_tip_points_rz_mm: tuple[tuple[float, float], ...]
    root_boundary_authority: str
    tip_boundary_authority: str
    root_carrier_clearance_authority: str
    tip_carrier_clearance_authority: str
    requested_streamwise_interval_s: tuple[float, float]
    boundary_constrained_streamwise_interval_s: tuple[float, float]
    resolved_streamwise_interval_s: tuple[float, float]
    streamwise_boundary_clearance_mm: float
    streamwise_boundary_clearance_s: float
    root_projection_residual_max_mm: float
    tip_projection_residual_max_mm: float
    projection_residual_gate_mm: float
    source_tolerance_mm: float
    support_correspondence_method: str

    def beta(self, active_h: float, streamwise_u: float) -> float:
        eta = _unit(active_h, "active_h")
        u = _unit(streamwise_u, "streamwise_u")
        root = float(np.interp(u, self.streamwise_u, self.root_h))
        tip = float(np.interp(u, self.streamwise_u, self.tip_h))
        return root + eta * (tip - root)

    def profile_rz_mm(self, active_h: float) -> tuple[tuple[float, float], ...]:
        eta = _unit(active_h, "active_h")
        root = np.asarray(self.active_root_points_rz_mm, dtype=float)
        tip = np.asarray(self.active_tip_points_rz_mm, dtype=float)
        points = root + eta * (tip - root)
        return tuple(tuple(float(value) for value in point) for point in points)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": "impeller_v1_1_6_s_dependent_active_span_r16_1",
            "coordinate_system": "authenticated_meridional_support_correspondence",
            "streamwise_u": list(self.streamwise_u),
            "hub_points_rz_mm": [list(point) for point in self.hub_points_rz_mm],
            "tip_points_rz_mm": [list(point) for point in self.tip_points_rz_mm],
            "root_h": list(self.root_h),
            "tip_h": list(self.tip_h),
            "root_lift_mm": list(self.root_lift_mm),
            "tip_lift_mm": list(self.tip_lift_mm),
            "root_width_mm": list(self.root_width_mm),
            "tip_width_mm": list(self.tip_width_mm),
            "retained_root_boundary_points_rz_mm": [
                list(point) for point in self.retained_root_boundary_points_rz_mm
            ],
            "retained_tip_boundary_points_rz_mm": [
                list(point) for point in self.retained_tip_boundary_points_rz_mm
            ],
            "root_carrier_clearance_mm": list(self.root_carrier_clearance_mm),
            "tip_carrier_clearance_mm": list(self.tip_carrier_clearance_mm),
            "root_carrier_clearance_cap_mm": list(
                self.root_carrier_clearance_cap_mm
            ),
            "tip_carrier_clearance_cap_mm": list(
                self.tip_carrier_clearance_cap_mm
            ),
            "active_root_points_rz_mm": [
                list(point) for point in self.active_root_points_rz_mm
            ],
            "active_tip_points_rz_mm": [
                list(point) for point in self.active_tip_points_rz_mm
            ],
            "root_boundary_authority": self.root_boundary_authority,
            "tip_boundary_authority": self.tip_boundary_authority,
            "root_carrier_clearance_authority": (
                self.root_carrier_clearance_authority
            ),
            "tip_carrier_clearance_authority": self.tip_carrier_clearance_authority,
            "requested_streamwise_interval_s": list(
                self.requested_streamwise_interval_s
            ),
            "boundary_constrained_streamwise_interval_s": list(
                self.boundary_constrained_streamwise_interval_s
            ),
            "resolved_streamwise_interval_s": list(
                self.resolved_streamwise_interval_s
            ),
            "streamwise_boundary_clearance_mm": (
                self.streamwise_boundary_clearance_mm
            ),
            "streamwise_boundary_clearance_s": self.streamwise_boundary_clearance_s,
            "streamwise_boundary_clearance_authority": (
                "four_source_tolerances_inside_termination_boundary"
                if self.streamwise_boundary_clearance_mm > 0.0
                else "no_attachment_termination_boundary"
            ),
            "root_projection_residual_max_mm": self.root_projection_residual_max_mm,
            "tip_projection_residual_max_mm": self.tip_projection_residual_max_mm,
            "projection_residual_gate_mm": self.projection_residual_gate_mm,
            "source_tolerance_mm": self.source_tolerance_mm,
            "support_correspondence_method": self.support_correspondence_method,
            "measurement_authority": "retained_boundary_on_authenticated_support_correspondence",
        }


def build_station_curve_authority(
    *,
    population: str,
    active_h: float,
    support_span_h: float,
    support_profile_rz_mm: Sequence[Sequence[float]],
    loop: Any,
    decomposition: Any,
    frame: Mapping[str, Any],
) -> dict[str, Any]:
    matrix = _rigid_matrix(frame.get("source_to_canonical_matrix"))
    source_loop = _points(loop.points_xyz_mm, 3, "loop.points_xyz_mm")
    canonical_loop = _transform_points(source_loop, matrix)
    curves: dict[str, Any] = {}
    for segment in decomposition.segments:
        try:
            role = _ROLE_BY_SEGMENT[str(segment.name)]
        except KeyError as exc:
            raise SectionCurveAuthorityError(
                "v116_section_curve_role_invalid",
                f"unsupported section segment {segment.name!r}",
            ) from exc
        source_xyz = _points(segment.points_xyz_mm, 3, f"{segment.name}.points_xyz_mm")
        points_sq = _points(segment.points_sq_mm, 2, f"{segment.name}.points_sq_mm")
        control_source = _points(
            segment.fit.control_points_xyz_mm,
            3,
            f"{segment.name}.fit.control_points_xyz_mm",
        )
        parameter_face_id = getattr(segment, "source_parameter_face_id", None)
        raw_parameter_uv = getattr(segment, "source_face_parameter_uv", ())
        parameter_uv = (
            np.asarray(raw_parameter_uv, dtype=float)
            if raw_parameter_uv
            else np.empty((0, 2), dtype=float)
        )
        if len(parameter_uv) and (
            parameter_uv.shape != (len(source_xyz), 2)
            or np.any(~np.isfinite(parameter_uv))
            or not parameter_face_id
        ):
            raise SectionCurveAuthorityError(
                "v116_section_curve_source_parameter_invalid",
                f"{segment.name} source-face UV witnesses do not match curve samples",
            )
        if role in {"side_a", "side_b"} and points_sq[0, 0] > points_sq[-1, 0]:
            source_xyz = source_xyz[::-1]
            points_sq = points_sq[::-1]
            control_source = control_source[::-1]
            parameter_uv = parameter_uv[::-1]
        canonical_xyz = _transform_points(source_xyz, matrix)
        canonical_controls = _transform_points(control_source, matrix)
        curve_u = _chord_parameters(canonical_xyz)
        endpoint_bridge = bool(
            getattr(loop, "source_kind", "")
            == "occt_exact_authenticated_open_side_pair"
            and role in {"leading_edge", "trailing_edge"}
        )
        curve_record = {
            "role": role,
            "source_segment_name": str(segment.name),
            "coordinate_frame": CANONICAL_FRAME,
            "source_coordinate_frame": SOURCE_FRAME,
            "source_points_xyz_mm": source_xyz.tolist(),
            "canonical_points_xyz_mm": canonical_xyz.tolist(),
            "s_physical_mm": points_sq[:, 0].tolist(),
            "q_physical_mm": points_sq[:, 1].tolist(),
            "u": curve_u.tolist(),
            "carrier_witnesses": [
                {
                    "u": float(u),
                    "s_physical_mm": float(point_sq[0]),
                    "q_physical_mm": float(point_sq[1]),
                    "support_span_h": float(support_span_h),
                }
                for u, point_sq in zip(curve_u, points_sq, strict=True)
            ],
            "start_witness": _endpoint_witness(points_sq[0], canonical_xyz[0]),
            "end_witness": _endpoint_witness(points_sq[-1], canonical_xyz[-1]),
            "nurbs": {
                "degree": int(segment.fit.degree),
                "knots": [float(value) for value in segment.fit.knots],
                "weights": [1.0] * len(canonical_controls),
                "source_control_points_xyz_mm": control_source.tolist(),
                "canonical_control_points_xyz_mm": canonical_controls.tolist(),
                "fit_residual_max_mm": float(segment.fit.residual_max_mm),
                "knot_strategy": str(segment.fit.knot_strategy),
                "measurement_fit_only": True,
                "geometry_authority": "exact_source_curve_samples",
            },
            "source_face_ids": sorted({str(value) for value in segment.source_face_ids}),
            "source_edge_ids": sorted({str(value) for value in segment.source_edge_ids}),
            "geometry_authority": (
                "review_only_endpoint_witness_bridge"
                if endpoint_bridge
                else "authenticated_step_exact_section_curve"
            ),
            "source_curvature_authority": not endpoint_bridge,
        }
        if len(parameter_uv):
            curve_record["source_face_parameter"] = {
                "face_id": str(parameter_face_id),
                "uv": parameter_uv.tolist(),
                "projection_residual_max_mm": float(
                    getattr(
                        segment,
                        "source_face_parameter_residual_max_mm",
                        0.0,
                    )
                ),
                "authority": "authenticated_step_source_face_parameter",
            }
            source_surface = getattr(
                segment, "source_surface_parameter_authority", None
            )
            if isinstance(source_surface, Mapping):
                curve_record["source_face_surface"] = (
                    _canonical_source_face_surface(
                        source_surface,
                        matrix,
                        expected_face_id=str(parameter_face_id),
                    )
                )
        curves[role] = curve_record
    if not {"side_a", "side_b"}.issubset(curves):
        raise SectionCurveAuthorityError(
            "v116_section_curve_role_invalid",
            "a direct section station requires independent pressure and suction curves",
        )
    side_a = curves["side_a"]
    side_b = curves["side_b"]
    endpoint_stagger = {
        "side_b_minus_side_a_leading_s_mm": float(
            side_b["s_physical_mm"][0] - side_a["s_physical_mm"][0]
        ),
        "side_b_minus_side_a_trailing_s_mm": float(
            side_b["s_physical_mm"][-1] - side_a["s_physical_mm"][-1]
        ),
    }
    return {
        "contract_id": CONTRACT_ID,
        "authority": "authenticated_step_exact_section_curves",
        "source_loop_id": str(
            getattr(loop, "loop_id", f"{population}:h_{float(active_h):.9f}")
        ),
        "population": str(population),
        "active_h": _unit(active_h, "active_h"),
        "support_span_h": _unit(support_span_h, "support_span_h"),
        "carrier_profile_id": f"{population}-active-{float(active_h):.9f}",
        "support_profile_rz_mm": _points(
            support_profile_rz_mm, 2, "support_profile_rz_mm"
        ).tolist(),
        "source_loop_points_xyz_mm": source_loop.tolist(),
        "canonical_loop_points_xyz_mm": canonical_loop.tolist(),
        "curves": curves,
        "endpoint_stagger": endpoint_stagger,
        "aerodynamic_role_status": "UNRESOLVED_SIDE_A_SIDE_B_ONLY",
        "closure_classification": _closure_classification(loop),
        "material_side": int(loop.material_side),
        "source_tolerance_mm": float(loop.source_tolerance_mm),
    }


def build_derived_field_evidence(thickness_field: Any) -> dict[str, Any]:
    samples = tuple(getattr(thickness_field, "samples", ()))
    if len(samples) < 3:
        raise SectionCurveAuthorityError(
            "v116_section_curve_derived_field_invalid",
            "direct section derived fields require at least three thickness witnesses",
        )
    camber = np.asarray([sample.camber_sq_mm for sample in samples], dtype=float)
    if camber.shape != (len(samples), 2) or np.any(~np.isfinite(camber)):
        raise SectionCurveAuthorityError(
            "v116_section_curve_derived_field_invalid",
            "direct section camber witnesses must be finite physical S-Q points",
        )
    records = []
    for index, sample in enumerate(samples):
        low = camber[max(0, index - 1)]
        high = camber[min(len(camber) - 1, index + 1)]
        tangent = high - low
        length = float(np.linalg.norm(tangent))
        if length <= 1.0e-12:
            raise SectionCurveAuthorityError(
                "v116_section_curve_derived_field_invalid",
                "direct section camber contains a zero physical-metric tangent",
            )
        tangent /= length
        normal = np.asarray(sample.normal_sq, dtype=float)
        if normal.shape != (2,) or np.any(~np.isfinite(normal)):
            raise SectionCurveAuthorityError(
                "v116_section_curve_derived_field_invalid",
                "direct section thickness normal must retain finite S and Q components",
            )
        records.append(
            {
                "u": float(sample.s),
                "camber_sq_mm": [float(value) for value in sample.camber_sq_mm],
                "normal_sq": [float(value) for value in normal],
                "thickness_mm": float(sample.thickness_mm),
                "pose_tangent_sq": [float(value) for value in tangent],
                "pose_theta_deg": float(
                    math.degrees(math.atan2(tangent[1], tangent[0]))
                ),
                "side_a_parameter": float(sample.side_a_parameter),
                "side_b_parameter": float(sample.side_b_parameter),
                "inside_source_loop": bool(
                    getattr(sample, "inside_source_loop", True)
                ),
                "measurement_method": str(
                    getattr(
                        sample,
                        "measurement_method",
                        "camber_normal_line_intersections",
                    )
                ),
                "normal_line_residual_mm": float(
                    getattr(sample, "normal_line_residual_mm", 0.0)
                ),
            }
        )
    return {
        "authority": "derived_from_direct_section_curve_network",
        "geometry_authority": False,
        "measurement_method": str(
            getattr(
                thickness_field,
                "method",
                "camber_normal_line_intersections",
            )
        ),
        "fallback_sample_count": int(
            getattr(thickness_field, "fallback_sample_count", 0)
        ),
        "correspondence_monotone": bool(
            getattr(thickness_field, "correspondence_monotone", True)
        ),
        "normal_offset_formulation": "physical_s_q_two_component",
        "q_only_offset_forbidden": True,
        "samples": records,
    }


def build_active_span_field(
    hub_profile_rz_mm: Sequence[Sequence[float]],
    tip_profile_rz_mm: Sequence[Sequence[float]],
    *,
    root_attachment: Any,
    tip_attachment: Any | None,
    source_tolerance_mm: float,
    sample_count: int = 129,
    streamwise_interval_s: Sequence[float] = (0.0, 1.0),
    support_correspondence: MeridionalCorrespondence | None = None,
) -> ActiveSpanField:
    tolerance = _positive(source_tolerance_mm, "source_tolerance_mm")
    correspondence = (
        solve_meridional_correspondence(
            hub_profile_rz_mm,
            tip_profile_rz_mm,
            sample_count=max(17, int(sample_count)),
        )
        if support_correspondence is None
        else support_correspondence
    )
    full_hub = np.asarray(correspondence.hub_points_rz_mm, dtype=float)
    full_tip = np.asarray(correspondence.tip_points_rz_mm, dtype=float)
    full_u = np.asarray(correspondence.hub_parameters, dtype=float)
    interval = np.asarray(streamwise_interval_s, dtype=float)
    if (
        interval.shape != (2,)
        or np.any(~np.isfinite(interval))
        or not 0.0 <= interval[0] < interval[1] <= 1.0
    ):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "streamwise_interval_s must define an ordered interval in [0, 1]",
        )
    requested_interval = (float(interval[0]), float(interval[1]))
    boundary_ranges = [
        value
        for value in (
            _attachment_boundary_range(root_attachment),
            _attachment_boundary_range(tip_attachment),
        )
        if value is not None
    ]
    if boundary_ranges:
        interval[0] = max(interval[0], *(value[0] for value in boundary_ranges))
        interval[1] = min(interval[1], *(value[1] for value in boundary_ranges))
    boundary_constrained_interval = (float(interval[0]), float(interval[1]))
    hub_arc_length_mm = float(
        np.sum(np.linalg.norm(np.diff(full_hub, axis=0), axis=1))
    )
    if not np.isfinite(hub_arc_length_mm) or hub_arc_length_mm <= 1.0e-9:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "authenticated hub support has no measurable meridional arc length",
        )
    streamwise_clearance_mm = 4.0 * tolerance if boundary_ranges else 0.0
    streamwise_clearance_s = streamwise_clearance_mm / hub_arc_length_mm
    if boundary_ranges:
        interval[0] += streamwise_clearance_s
        interval[1] -= streamwise_clearance_s
    if interval[1] - interval[0] <= 1.0e-6:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "attachment evidence leaves no ordered blade-body streamwise interval",
        )
    resolved_interval = (float(interval[0]), float(interval[1]))
    u = np.linspace(resolved_interval[0], resolved_interval[1], len(full_u))
    hub = np.column_stack(
        [np.interp(u, full_u, full_hub[:, column]) for column in range(2)]
    )
    tip = np.column_stack(
        [np.interp(u, full_u, full_tip[:, column]) for column in range(2)]
    )
    support_span = np.linalg.norm(tip - hub, axis=1)
    if np.any(support_span <= 8.0 * tolerance):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "authenticated hub and tip supports leave no measurable local span",
        )
    root_lift = _attachment_field(root_attachment, "lift_samples_mm", u, default=0.0)
    root_width = _attachment_field(root_attachment, "width_samples_mm", u, default=0.0)
    tip_lift = _attachment_field(tip_attachment, "lift_samples_mm", u, default=0.0)
    tip_width = _attachment_field(tip_attachment, "width_samples_mm", u, default=0.0)
    measured_root = _attachment_boundary_h_envelope(
        root_attachment,
        u,
        full_u,
        full_hub,
        full_tip,
        boundary="root",
        outside_support_tolerance_mm=max(4.0 * tolerance, 0.10),
    )
    root_projection_residual_max = 0.0
    if measured_root is None:
        root_base_h = np.maximum(root_lift / support_span, 0.0)
        root_boundary = hub + root_base_h[:, None] * (tip - hub)
        root_authority = "attachment_lift_fallback"
    else:
        root_base_h, root_projection_residual_max = measured_root
        root_boundary = hub + root_base_h[:, None] * (tip - hub)
        root_authority = "source_retained_blade_boundary_support_envelope"
    measured_tip = _attachment_boundary_h_envelope(
        tip_attachment,
        u,
        full_u,
        full_hub,
        full_tip,
        boundary="tip",
        outside_support_tolerance_mm=max(4.0 * tolerance, 0.10),
    )
    tip_projection_residual_max = 0.0
    if measured_tip is None:
        tip_base_h = 1.0 - np.maximum(tip_lift / support_span, 0.0)
        tip_boundary = hub + tip_base_h[:, None] * (tip - hub)
        tip_authority = "authenticated_tip_support_with_attachment_lift"
    else:
        tip_base_h, tip_projection_residual_max = measured_tip
        tip_boundary = hub + tip_base_h[:, None] * (tip - hub)
        tip_authority = "source_retained_blade_boundary_support_envelope"
    active_vector = tip_boundary - root_boundary
    active_length = np.linalg.norm(active_vector, axis=1)
    if np.any(active_length <= 8.0 * tolerance):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained root and tip boundaries leave no measurable active span",
        )
    root_clearance_cap = 0.10 * active_length
    tip_clearance_cap = 0.10 * active_length
    root_clearance = np.minimum(
        np.maximum(4.0 * tolerance, 0.25 * np.maximum(root_width, 0.0)),
        root_clearance_cap,
    )
    tip_clearance = np.minimum(
        np.maximum(4.0 * tolerance, 0.25 * np.maximum(tip_width, 0.0)),
        tip_clearance_cap,
    )
    direction = active_vector / active_length[:, None]
    active_root = root_boundary + root_clearance[:, None] * direction
    active_tip = tip_boundary - tip_clearance[:, None] * direction
    support_vector = tip - hub
    support_length_sq = np.sum(support_vector * support_vector, axis=1)
    root_h = np.sum((active_root - hub) * support_vector, axis=1) / support_length_sq
    tip_h = np.sum((active_tip - hub) * support_vector, axis=1) / support_length_sq
    projection_gate = max(
        5.0 * tolerance,
        float(np.max(root_width, initial=0.0)) + 4.0 * tolerance,
        float(np.max(tip_width, initial=0.0)) + 4.0 * tolerance,
        0.10,
    )
    root_projection_residual = np.asarray([root_projection_residual_max])
    tip_projection_residual = np.asarray([tip_projection_residual_max])
    if (
        float(np.max(root_projection_residual)) > projection_gate
        or float(np.max(tip_projection_residual)) > projection_gate
    ):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained attachment boundary is inconsistent with support correspondence: "
            f"root residual {float(np.max(root_projection_residual)):.6f} mm, "
            f"tip residual {float(np.max(tip_projection_residual)):.6f} mm, "
            f"gate {projection_gate:.6f} mm",
        )
    if np.any(root_h >= tip_h - 1.0e-9):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "local root and tip carrier fields cross or collapse",
        )
    return ActiveSpanField(
        streamwise_u=tuple(float(value) for value in u),
        hub_points_rz_mm=tuple(tuple(float(value) for value in point) for point in hub),
        tip_points_rz_mm=tuple(tuple(float(value) for value in point) for point in tip),
        root_h=tuple(float(value) for value in root_h),
        tip_h=tuple(float(value) for value in tip_h),
        root_lift_mm=tuple(float(value) for value in root_lift),
        tip_lift_mm=tuple(float(value) for value in tip_lift),
        root_width_mm=tuple(float(value) for value in root_width),
        tip_width_mm=tuple(float(value) for value in tip_width),
        retained_root_boundary_points_rz_mm=tuple(
            tuple(float(value) for value in point) for point in root_boundary
        ),
        retained_tip_boundary_points_rz_mm=tuple(
            tuple(float(value) for value in point) for point in tip_boundary
        ),
        root_carrier_clearance_mm=tuple(float(value) for value in root_clearance),
        tip_carrier_clearance_mm=tuple(float(value) for value in tip_clearance),
        root_carrier_clearance_cap_mm=tuple(
            float(value) for value in root_clearance_cap
        ),
        tip_carrier_clearance_cap_mm=tuple(
            float(value) for value in tip_clearance_cap
        ),
        active_root_points_rz_mm=tuple(
            tuple(float(value) for value in point) for point in active_root
        ),
        active_tip_points_rz_mm=tuple(
            tuple(float(value) for value in point) for point in active_tip
        ),
        root_boundary_authority=root_authority,
        tip_boundary_authority=tip_authority,
        root_carrier_clearance_authority=(
            "max_four_source_tolerances_or_quarter_local_attachment_width_"
            "capped_by_active_span"
        ),
        tip_carrier_clearance_authority=(
            "max_four_source_tolerances_or_quarter_local_attachment_width_"
            "capped_by_active_span"
        ),
        requested_streamwise_interval_s=requested_interval,
        boundary_constrained_streamwise_interval_s=boundary_constrained_interval,
        resolved_streamwise_interval_s=resolved_interval,
        streamwise_boundary_clearance_mm=streamwise_clearance_mm,
        streamwise_boundary_clearance_s=streamwise_clearance_s,
        root_projection_residual_max_mm=float(np.max(root_projection_residual)),
        tip_projection_residual_max_mm=float(np.max(tip_projection_residual)),
        projection_residual_gate_mm=projection_gate,
        source_tolerance_mm=tolerance,
        support_correspondence_method=str(correspondence.method),
    )


def _attachment_boundary_range(
    attachment: Any | None,
) -> tuple[float, float] | None:
    if attachment is None:
        return None
    ranges: list[tuple[str, float, float]] = []
    retained_name = (
        "retained_streamwise_samples_s"
        if _attribute(attachment, "retained_streamwise_samples_s", ())
        else "streamwise_samples_s"
    )
    for name in ("termination_streamwise_samples_s", retained_name):
        samples = np.asarray(_attribute(attachment, name, ()), dtype=float)
        if samples.size:
            if samples.ndim != 1 or np.any(~np.isfinite(samples)):
                raise SectionCurveAuthorityError(
                    "v116_active_span_carrier_invalid",
                    f"{name} must contain finite scalar parameters",
                )
            ranges.append((name, float(np.min(samples)), float(np.max(samples))))
    if not ranges:
        return None
    low = max(value[1] for value in ranges)
    high = min(value[2] for value in ranges)
    if high - low <= 1.0e-6:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "attachment termination and retained material boundaries do not overlap",
            details={
                "attachment_streamwise_ranges": [
                    {"authority": name, "streamwise_range_s": [start, end]}
                    for name, start, end in ranges
                ]
            },
        )
    return low, high


def _attachment_boundary_h_envelope(
    attachment: Any | None,
    query_u: np.ndarray,
    support_u: np.ndarray,
    hub_points_rz_mm: np.ndarray,
    tip_points_rz_mm: np.ndarray,
    *,
    boundary: str,
    outside_support_tolerance_mm: float = 0.0,
) -> tuple[np.ndarray, float] | None:
    if attachment is None:
        return None
    if boundary not in {"root", "tip"}:
        raise ValueError("boundary must be root or tip")
    points = np.asarray(
        _attribute(attachment, "retained_points_canonical_rz_mm", ()), dtype=float
    )
    sample_u = np.asarray(
        _attribute(attachment, "retained_streamwise_samples_s", ())
        or _attribute(attachment, "streamwise_samples_s", ()),
        dtype=float,
    )
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        return None
    if sample_u.shape != (len(points),):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained boundary points require matching streamwise parameters",
        )
    edge_ids = tuple(
        str(value)
        for value in _attribute(attachment, "retained_point_source_edge_ids", ())
    )
    if len(edge_ids) != len(points):
        edge_ids = ("retained_boundary",) * len(points)
    local_hub = np.column_stack(
        [np.interp(sample_u, support_u, hub_points_rz_mm[:, column]) for column in range(2)]
    )
    local_tip = np.column_stack(
        [np.interp(sample_u, support_u, tip_points_rz_mm[:, column]) for column in range(2)]
    )
    support_vector = local_tip - local_hub
    support_length_sq = np.sum(support_vector * support_vector, axis=1)
    if np.any(support_length_sq <= 1.0e-18):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained boundary cannot be projected onto a collapsed support connector",
        )
    sample_h = np.sum((points - local_hub) * support_vector, axis=1) / support_length_sq
    projected = local_hub + sample_h[:, None] * support_vector
    residual_max = float(np.max(np.linalg.norm(points - projected, axis=1)))
    candidates: list[np.ndarray] = []
    for edge_id in sorted(set(edge_ids)):
        indices = np.asarray(
            [index for index, value in enumerate(edge_ids) if value == edge_id],
            dtype=int,
        )
        edge_u = sample_u[indices]
        edge_h = sample_h[indices]
        order = np.argsort(edge_u, kind="stable")
        edge_u = edge_u[order]
        edge_h = edge_h[order]
        unique_u, inverse = np.unique(np.round(edge_u, 10), return_inverse=True)
        if len(unique_u) < 2:
            continue
        grouped_h = np.zeros(len(unique_u), dtype=float)
        for group in range(len(unique_u)):
            values = edge_h[inverse == group]
            grouped_h[group] = (
                float(np.max(values)) if boundary == "root" else float(np.min(values))
            )
        values = np.full(len(query_u), np.nan, dtype=float)
        inside = (query_u >= unique_u[0] - 1.0e-10) & (
            query_u <= unique_u[-1] + 1.0e-10
        )
        if len(unique_u) >= 3:
            values[inside] = PchipInterpolator(unique_u, grouped_h)(
                np.clip(query_u[inside], unique_u[0], unique_u[-1])
            )
        else:
            values[inside] = np.interp(query_u[inside], unique_u, grouped_h)
        candidates.append(values)
    if not candidates:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained boundary edge chains are insufficient for an S-dependent field",
        )
    candidate_matrix = np.vstack(candidates)
    envelope = np.full(len(query_u), np.nan, dtype=float)
    covered = np.any(np.isfinite(candidate_matrix), axis=0)
    if boundary == "root":
        envelope[covered] = np.nanmax(candidate_matrix[:, covered], axis=0)
    else:
        envelope[covered] = np.nanmin(candidate_matrix[:, covered], axis=0)
    if np.any(~covered):
        global_u, global_h = _material_side_envelope_samples(
            sample_u, sample_h, boundary=boundary
        )
        missing_u = query_u[~covered]
        if (
            len(global_u) < 2
            or missing_u[0] < global_u[0] - 1.0e-10
            or missing_u[-1] > global_u[-1] + 1.0e-10
        ):
            raise SectionCurveAuthorityError(
                "v116_active_span_carrier_invalid",
                "retained boundary edge chains do not cover the blade streamwise interval",
                details=_attachment_coverage_details(
                    boundary=boundary,
                    query_u=query_u,
                    missing_u=missing_u,
                    sample_u=sample_u,
                    edge_ids=edge_ids,
                    support_u=support_u,
                    hub_points_rz_mm=hub_points_rz_mm,
                ),
            )
        interpolator = (
            PchipInterpolator(global_u, global_h)
            if len(global_u) >= 3
            else None
        )
        envelope[~covered] = (
            interpolator(missing_u)
            if interpolator is not None
            else np.interp(missing_u, global_u, global_h)
        )
    if np.any(~np.isfinite(envelope)):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "retained boundary edge chains do not cover the blade streamwise interval",
            details=_attachment_coverage_details(
                boundary=boundary,
                query_u=query_u,
                missing_u=query_u[~np.isfinite(envelope)],
                sample_u=sample_u,
                edge_ids=edge_ids,
                support_u=support_u,
                hub_points_rz_mm=hub_points_rz_mm,
            ),
        )
    query_hub = np.column_stack(
        [
            np.interp(query_u, support_u, hub_points_rz_mm[:, column])
            for column in range(2)
        ]
    )
    query_tip = np.column_stack(
        [
            np.interp(query_u, support_u, tip_points_rz_mm[:, column])
            for column in range(2)
        ]
    )
    query_support_length = np.linalg.norm(query_tip - query_hub, axis=1)
    outside_gate = max(0.0, float(outside_support_tolerance_mm))
    root_outside_mm = float(
        np.max(np.maximum(-envelope, 0.0) * query_support_length)
    )
    tip_outside_mm = float(
        np.max(np.maximum(envelope - 1.0, 0.0) * query_support_length)
    )
    if boundary == "root" and root_outside_mm > outside_gate + 1.0e-9:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "root retained-boundary envelope lies outside the hub support",
            details={
                "outside_support_maximum_mm": root_outside_mm,
                "outside_support_tolerance_mm": outside_gate,
            },
        )
    if boundary == "tip" and tip_outside_mm > outside_gate + 1.0e-9:
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            "tip retained-boundary envelope lies outside the tip support",
            details={
                "outside_support_maximum_mm": tip_outside_mm,
                "outside_support_tolerance_mm": outside_gate,
            },
        )
    return envelope, residual_max


def _attachment_coverage_details(
    *,
    boundary: str,
    query_u: np.ndarray,
    missing_u: np.ndarray,
    sample_u: np.ndarray,
    edge_ids: Sequence[str],
    support_u: np.ndarray,
    hub_points_rz_mm: np.ndarray,
) -> dict[str, Any]:
    query = np.asarray(query_u, dtype=float)
    missing = np.asarray(missing_u, dtype=float)
    samples = np.asarray(sample_u, dtype=float)
    retained_min = float(np.min(samples))
    retained_max = float(np.max(samples))
    requested_min = float(np.min(query))
    requested_max = float(np.max(query))
    leading_gap_s = max(0.0, retained_min - requested_min)
    trailing_gap_s = max(0.0, requested_max - retained_max)
    edge_ranges = []
    for edge_id in sorted(set(edge_ids)):
        values = samples[
            np.asarray([value == edge_id for value in edge_ids], dtype=bool)
        ]
        edge_ranges.append(
            {
                "source_edge_id": str(edge_id),
                "point_count": int(len(values)),
                "streamwise_range_s": [
                    float(np.min(values)),
                    float(np.max(values)),
                ],
            }
        )
    return {
        "boundary_role": boundary,
        "requested_streamwise_interval_s": [requested_min, requested_max],
        "retained_global_streamwise_range_s": [retained_min, retained_max],
        "missing_streamwise_range_s": (
            [float(np.min(missing)), float(np.max(missing))]
            if len(missing)
            else None
        ),
        "uncovered_query_sample_count": int(len(missing)),
        "retained_point_count": int(len(samples)),
        "source_edge_ranges": edge_ranges,
        "topology_gap_s": {
            "leading": leading_gap_s,
            "trailing": trailing_gap_s,
        },
        "topology_gap_mm": {
            "leading": _support_interval_length_mm(
                requested_min,
                retained_min,
                support_u,
                hub_points_rz_mm,
            ),
            "trailing": _support_interval_length_mm(
                retained_max,
                requested_max,
                support_u,
                hub_points_rz_mm,
            ),
        },
    }


def _support_interval_length_mm(
    start_u: float,
    end_u: float,
    support_u: np.ndarray,
    points_rz_mm: np.ndarray,
) -> float:
    if end_u <= start_u:
        return 0.0
    u = np.asarray(support_u, dtype=float)
    points = np.asarray(points_rz_mm, dtype=float)
    cumulative = np.concatenate(
        ([0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
    )
    start_length = float(np.interp(start_u, u, cumulative))
    end_length = float(np.interp(end_u, u, cumulative))
    return max(0.0, end_length - start_length)


def _material_side_envelope_samples(
    sample_u: np.ndarray, sample_h: np.ndarray, *, boundary: str
) -> tuple[np.ndarray, np.ndarray]:
    rounded_u = np.round(np.asarray(sample_u, dtype=float), 10)
    unique_u, inverse = np.unique(rounded_u, return_inverse=True)
    envelope = np.zeros(len(unique_u), dtype=float)
    for group in range(len(unique_u)):
        values = np.asarray(sample_h, dtype=float)[inverse == group]
        envelope[group] = (
            float(np.max(values)) if boundary == "root" else float(np.min(values))
        )
    return unique_u, envelope


def _attachment_field(
    attachment: Any | None,
    name: str,
    query_u: np.ndarray,
    *,
    default: float,
) -> np.ndarray:
    if attachment is None:
        return np.full(len(query_u), float(default), dtype=float)
    values = np.asarray(_attribute(attachment, name, ()), dtype=float)
    sample_u = np.asarray(_attribute(attachment, "streamwise_samples_s", ()), dtype=float)
    if not len(values):
        return np.full(len(query_u), float(default), dtype=float)
    if len(sample_u) != len(values):
        sample_u = np.linspace(0.0, 1.0, len(values))
    order = np.argsort(sample_u)
    sample_u = sample_u[order]
    values = values[order]
    if np.any(~np.isfinite(values)) or np.any(values < 0.0):
        raise SectionCurveAuthorityError(
            "v116_active_span_carrier_invalid",
            f"{name} must contain finite nonnegative measurements",
        )
    return np.interp(query_u, sample_u, values)


def _attribute(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _closure_classification(loop: Any) -> str:
    if (
        getattr(loop, "source_kind", "")
        == "occt_exact_authenticated_open_side_pair"
    ):
        evidence = getattr(loop, "orientation_evidence", {})
        tolerance = float(getattr(loop, "source_tolerance_mm", 0.0))
        endpoint_gaps = (
            float(evidence.get("leading_endpoint_gap_mm", math.inf)),
            float(evidence.get("trailing_endpoint_gap_mm", math.inf)),
        )
        if max(endpoint_gaps) <= tolerance:
            return "sharp_shared_seam"
        return "endpoint_witness_bridge_review_only"
    edges = tuple(getattr(loop, "edges", ()))
    if len(edges) <= 2:
        return "sharp_shared_seam"
    roles = {
        str(role)
        for edge in edges
        for role in getattr(edge, "source_roles", ())
    }
    if roles.intersection({"leading_edge", "trailing_edge"}):
        return "finite_edge_face"
    return "measured_transition_curve"


def _endpoint_witness(point_sq: np.ndarray, point_xyz: np.ndarray) -> dict[str, Any]:
    return {
        "s_physical_mm": float(point_sq[0]),
        "q_physical_mm": float(point_sq[1]),
        "canonical_xyz_mm": [float(value) for value in point_xyz],
    }


def _rigid_matrix(value: Any) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or np.any(~np.isfinite(matrix)):
        raise SectionCurveAuthorityError(
            "v116_section_curve_frame_invalid",
            "source_to_canonical_matrix must be a finite 4x4 matrix",
        )
    rotation = matrix[:3, :3]
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-8) or not math.isclose(
        abs(float(np.linalg.det(rotation))), 1.0, rel_tol=0.0, abs_tol=1.0e-8
    ):
        raise SectionCurveAuthorityError(
            "v116_section_curve_frame_invalid",
            "source_to_canonical_matrix must contain a rigid rotation",
        )
    return matrix


def _transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=float)])
    return (matrix @ homogeneous.T).T[:, :3]


def _canonical_source_face_surface(
    source: Mapping[str, Any],
    matrix: np.ndarray,
    *,
    expected_face_id: str,
) -> dict[str, Any]:
    if str(source.get("source_face_id", "")) != expected_face_id:
        raise SectionCurveAuthorityError(
            "v116_section_curve_source_parameter_invalid",
            "source surface authority does not match the section-curve face",
        )
    controls = np.asarray(source.get("control_points_source_xyz_mm"), dtype=float)
    weights = np.asarray(source.get("weights"), dtype=float)
    if (
        controls.ndim != 3
        or controls.shape[2] != 3
        or weights.shape != controls.shape[:2]
        or np.any(~np.isfinite(controls))
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0.0)
    ):
        raise SectionCurveAuthorityError(
            "v116_section_curve_source_parameter_invalid",
            "source surface control net or weights are invalid",
        )
    canonical = _transform_points(controls.reshape(-1, 3), matrix).reshape(
        controls.shape
    )
    trim_boundaries = []
    for value in source.get("trim_boundary_uv_paths", ()):
        record = dict(value)
        source_points = np.asarray(record.get("source_points_xyz_mm"), dtype=float)
        if (
            source_points.ndim == 2
            and source_points.shape[0] >= 2
            and source_points.shape[1] == 3
            and np.all(np.isfinite(source_points))
        ):
            record["canonical_points_xyz_mm"] = _transform_points(
                source_points, matrix
            ).tolist()
        trim_boundaries.append(record)
    return {
        **dict(source),
        "canonical_control_points_xyz_mm": canonical.tolist(),
        "trim_boundary_uv_paths": trim_boundaries,
        "canonical_coordinate_frame": CANONICAL_FRAME,
        "geometry_authority": "authenticated_step_underlying_rational_bspline_surface",
    }


def _chord_parameters(points: np.ndarray) -> np.ndarray:
    distances = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(distances)])
    if cumulative[-1] <= 1.0e-12:
        raise SectionCurveAuthorityError(
            "v116_section_curve_degenerate",
            "section curve points are coincident",
        )
    return cumulative / cumulative[-1]


def _points(value: Any, width: int, name: str) -> np.ndarray:
    points = np.asarray(value, dtype=float)
    if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] != width or np.any(~np.isfinite(points)):
        raise SectionCurveAuthorityError(
            "v116_section_curve_contract_invalid",
            f"{name} must contain at least two finite {width}D points",
        )
    return points


def _unit(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise SectionCurveAuthorityError(
            "v116_section_curve_contract_invalid",
            f"{name} must be finite in [0, 1]",
        )
    return result


def _positive(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise SectionCurveAuthorityError(
            "v116_section_curve_contract_invalid",
            f"{name} must be finite and positive",
        )
    return result
