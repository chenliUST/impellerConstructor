from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np


_EPSILON = 1.0e-12
_POINT_DIGITS = 12
_SEGMENT_ROLES = ("side_a", "side_b", "leading_edge", "trailing_edge")


class SectionRecoveryError(ValueError):
    def __init__(self, reason: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


@dataclass(frozen=True)
class LocalSectionFrame:
    origin_xyz: tuple[float, float, float]
    s_axis_xyz: tuple[float, float, float]
    q_axis_xyz: tuple[float, float, float]
    normal_xyz: tuple[float, float, float]

    def __post_init__(self) -> None:
        origin = _point(self.origin_xyz, 3, "origin_xyz")
        normal = _unit(self.normal_xyz, "normal_xyz")
        s_axis = np.asarray(_point(self.s_axis_xyz, 3, "s_axis_xyz"), dtype=float)
        s_axis -= float(np.dot(s_axis, normal)) * normal
        s_axis = _unit(s_axis, "s_axis_xyz")
        q_axis = np.cross(normal, s_axis)
        requested_q = np.asarray(_point(self.q_axis_xyz, 3, "q_axis_xyz"), dtype=float)
        if float(np.dot(q_axis, requested_q)) < 0.0:
            s_axis = -s_axis
            q_axis = -q_axis
        object.__setattr__(self, "origin_xyz", tuple(float(value) for value in origin))
        object.__setattr__(self, "s_axis_xyz", tuple(float(value) for value in s_axis))
        object.__setattr__(self, "q_axis_xyz", tuple(float(value) for value in q_axis))
        object.__setattr__(self, "normal_xyz", tuple(float(value) for value in normal))

    def project(self, point_xyz: Sequence[float]) -> tuple[float, float]:
        delta = np.asarray(_point(point_xyz, 3, "point_xyz"), dtype=float) - np.asarray(
            self.origin_xyz, dtype=float
        )
        return (
            float(np.dot(delta, np.asarray(self.s_axis_xyz, dtype=float))),
            float(np.dot(delta, np.asarray(self.q_axis_xyz, dtype=float))),
        )


@dataclass(frozen=True)
class MeridionalCorrespondence:
    hub_parameters: tuple[float, ...]
    tip_parameters: tuple[float, ...]
    hub_points_rz_mm: tuple[tuple[float, float], ...]
    tip_points_rz_mm: tuple[tuple[float, float], ...]
    tip_reversed: bool
    closest_residual_rms_mm: float
    closest_residual_max_mm: float
    minimum_parameter_step: float
    method: str = "arc_length_closest_monotone_isotonic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "hub_parameters": list(self.hub_parameters),
            "tip_parameters": list(self.tip_parameters),
            "hub_points_rz_mm": [list(point) for point in self.hub_points_rz_mm],
            "tip_points_rz_mm": [list(point) for point in self.tip_points_rz_mm],
            "tip_reversed": self.tip_reversed,
            "residuals": {
                "closest_rms_mm": self.closest_residual_rms_mm,
                "closest_maximum_mm": self.closest_residual_max_mm,
            },
            "minimum_parameter_step": self.minimum_parameter_step,
            "flowwise_order_preserved": self.minimum_parameter_step > 0.0,
        }


@dataclass(frozen=True)
class SpanStation:
    h: float
    metrics: Mapping[str, Any]
    refinement_reasons: tuple[str, ...]
    initial: bool


@dataclass(frozen=True)
class SpanProfile:
    h: float
    points_rz_mm: tuple[tuple[float, float], ...]
    refinement_reasons: tuple[str, ...] = ()
    construction: str = "meridional_correspondence_interpolation"


@dataclass(frozen=True)
class AdaptiveSpanLattice:
    correspondence: MeridionalCorrespondence
    stations: tuple[SpanStation, ...]
    profiles: tuple[SpanProfile, ...]
    maximum_station_count: int
    active_root_evidence: Mapping[str, Any]
    active_tip_evidence: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "station_count": len(self.stations),
            "maximum_station_count": self.maximum_station_count,
            "ordered": all(
                self.stations[index].h < self.stations[index + 1].h
                for index in range(len(self.stations) - 1)
            ),
            "stations": [
                {
                    "h": station.h,
                    "metrics": _json_value(station.metrics),
                    "refinement_reasons": list(station.refinement_reasons),
                    "initial": station.initial,
                }
                for station in self.stations
            ],
            "profiles": [
                {
                    "h": profile.h,
                    "points_rz_mm": [list(point) for point in profile.points_rz_mm],
                    "refinement_reasons": list(profile.refinement_reasons),
                    "construction": profile.construction,
                }
                for profile in self.profiles
            ],
            "active_span": {
                "root": _json_value(self.active_root_evidence),
                "tip": _json_value(self.active_tip_evidence),
            },
            "correspondence": self.correspondence.as_dict(),
        }


@dataclass(frozen=True)
class SectionEdge:
    edge_id: str
    points_xyz_mm: tuple[tuple[float, float, float], ...]
    points_sq_mm: tuple[tuple[float, float], ...] = ()
    source_face_ids: tuple[str, ...] = ()
    source_roles: tuple[str, ...] = ()
    provenance_available: bool = False
    exact_curve: bool = False
    source_curve_exact: bool = False
    sampled_display_only: bool = True
    topology_start_vertex_id: str | None = None
    topology_end_vertex_id: str | None = None
    topology_endpoint_residual_mm: float = 0.0
    parameter_direction_reversed: bool = False
    source_parameter_face_id: str | None = None
    source_face_parameter_uv: tuple[tuple[float, float], ...] = ()
    source_face_parameter_residual_max_mm: float = 0.0
    source_surface_parameter_authority: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_face_ids": list(self.source_face_ids),
            "source_roles": list(self.source_roles),
            "points_xyz_mm": [list(point) for point in self.points_xyz_mm],
            "points_sq_mm": [list(point) for point in self.points_sq_mm],
            "provenance_available": self.provenance_available,
            "occt_exact_topology": bool(
                self.topology_start_vertex_id and self.topology_end_vertex_id
            ),
            "occt_exact_curve": self.source_curve_exact,
            "sampled_display_only": self.sampled_display_only,
            "display_polyline_exact": self.exact_curve,
            "topology_start_vertex_id": self.topology_start_vertex_id,
            "topology_end_vertex_id": self.topology_end_vertex_id,
            "topology_endpoint_residual_mm": self.topology_endpoint_residual_mm,
            "parameter_direction_reversed": self.parameter_direction_reversed,
            "source_parameter_face_id": self.source_parameter_face_id,
            "source_face_parameter_uv": [
                list(point) for point in self.source_face_parameter_uv
            ],
            "source_face_parameter_residual_max_mm": (
                self.source_face_parameter_residual_max_mm
            ),
            "source_surface_parameter_authority": _json_value(
                self.source_surface_parameter_authority
            ),
        }


@dataclass(frozen=True)
class SectionLoop:
    loop_id: str
    edges: tuple[SectionEdge, ...]
    points_xyz_mm: tuple[tuple[float, float, float], ...]
    points_sq_mm: tuple[tuple[float, float], ...]
    orientation: str
    start_landmark: str
    closure_gap_mm: float
    self_intersection_count: int
    section_normal_xyz: tuple[float, float, float]
    material_side: int
    source_face_ids: tuple[str, ...]
    source_edge_ids: tuple[str, ...]
    source_tolerance_mm: float
    source_kind: str
    orientation_evidence: Mapping[str, Any]
    healing_gaps_mm: tuple[float, ...] = ()
    healing_total_mm: float = 0.0
    source_wire_exact: bool = False
    display_polyline_exact: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "source_kind": self.source_kind,
            "source_face_ids": list(self.source_face_ids),
            "source_edge_ids": list(self.source_edge_ids),
            "edges": [edge.as_dict() for edge in self.edges],
            "points_xyz_mm": [list(point) for point in self.points_xyz_mm],
            "points_sq_mm": [list(point) for point in self.points_sq_mm],
            "orientation": self.orientation,
            "start_landmark": self.start_landmark,
            "closure_gap_mm": self.closure_gap_mm,
            "healing_gaps_mm": list(self.healing_gaps_mm),
            "healing_total_mm": self.healing_total_mm,
            "source_wire_exact": self.source_wire_exact,
            "display_polyline_exact": self.display_polyline_exact,
            "self_intersection_count": self.self_intersection_count,
            "section_normal_xyz": list(self.section_normal_xyz),
            "material_side": self.material_side,
            "source_tolerance_mm": self.source_tolerance_mm,
            "orientation_evidence": _json_value(self.orientation_evidence),
        }


@dataclass(frozen=True)
class ExactSectionResult:
    accepted_loop: SectionLoop
    additional_loops: tuple[SectionLoop, ...]
    rejected_edges: tuple[Mapping[str, Any], ...]
    operation: str = "OCCT_BRepAlgoAPI_Section"
    source_shape_scope: str = "complete_source_shape"
    mesh_used: bool = False
    source_brep_exact: bool = True
    display_samples_exact: bool = False
    wire_assembly_method: str = "occt_shared_vertex_topology"
    landmark_tracking: Mapping[str, Any] | None = None
    cutter_boundary_clearance_deg: float | None = None
    cutter_boundary_clearance_verified: bool = False

    def as_dict(self) -> dict[str, Any]:
        loops = (self.accepted_loop,) + self.additional_loops
        return {
            "operation": self.operation,
            "source_shape_scope": self.source_shape_scope,
            "mesh_used": self.mesh_used,
            "source_brep_exact": self.source_brep_exact,
            "display_samples_exact": self.display_samples_exact,
            "wire_assembly_method": self.wire_assembly_method,
            "landmark_tracking": _json_value(self.landmark_tracking),
            "cutter_boundary_clearance_deg": self.cutter_boundary_clearance_deg,
            "cutter_boundary_clearance_verified": self.cutter_boundary_clearance_verified,
            "source_edge_records": [
                edge.as_dict() for loop in loops for edge in loop.edges
            ],
            "accepted_loop": self.accepted_loop.as_dict(),
            "additional_loops": [loop.as_dict() for loop in self.additional_loops],
            "rejected_edges": [_json_value(record) for record in self.rejected_edges],
        }


@dataclass(frozen=True)
class OrientationAlignment:
    corrected_points_sq_mm: tuple[tuple[float, float], ...]
    reversed: bool
    circular_shift: int
    forward_score: float
    reverse_score: float
    tangent_mismatch_deg: float
    corrected_loop: SectionLoop | None = None


@dataclass(frozen=True)
class NurbsCurveFit:
    segment_name: str
    degree: int
    knots: tuple[float, ...]
    control_points_xyz_mm: tuple[tuple[float, float, float], ...]
    control_points_sq_mm: tuple[tuple[float, float], ...]
    source_edge_ids: tuple[str, ...]
    residual_rms_mm: float
    residual_p95_mm: float
    residual_max_mm: float
    residual_source_to_fit_max_sq_mm: float
    residual_fit_to_source_max_sq_mm: float
    residual_source_to_fit_max_xyz_mm: float
    residual_fit_to_source_max_xyz_mm: float
    residual_parameter_matched_max_sq_mm: float
    edge_sag_sq_mm: float
    edge_sag_xyz_mm: float
    source_sample_count: int
    fit_sample_count: int
    start_tangent_sq: tuple[float, float]
    end_tangent_sq: tuple[float, float]
    start_curvature_per_mm: float
    end_curvature_per_mm: float
    knot_strategy: str
    measurement_target_only: bool = True
    constructor_direct_curve_mode: bool = False


@dataclass(frozen=True)
class SectionSegmentMeasurement:
    name: str
    points_xyz_mm: tuple[tuple[float, float, float], ...]
    points_sq_mm: tuple[tuple[float, float], ...]
    source_edge_ids: tuple[str, ...]
    source_face_ids: tuple[str, ...]
    fit: NurbsCurveFit
    source_parameter_face_id: str | None = None
    source_face_parameter_uv: tuple[tuple[float, float], ...] = ()
    source_face_parameter_residual_max_mm: float = 0.0
    source_surface_parameter_authority: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LoopDecomposition:
    loop_id: str
    segments: tuple[SectionSegmentMeasurement, ...]
    landmark_method: str
    landmarks_sq_mm: Mapping[str, tuple[float, float]]
    pressure_suction_assigned: bool = False
    direct_curve_constructor_mode: bool = False

    def segment(self, name: str) -> SectionSegmentMeasurement:
        for segment in self.segments:
            if segment.name == name:
                return segment
        raise KeyError(name)


@dataclass(frozen=True)
class ThicknessSample:
    s: float
    camber_sq_mm: tuple[float, float]
    normal_sq: tuple[float, float]
    side_a_sq_mm: tuple[float, float]
    side_b_sq_mm: tuple[float, float]
    side_a_parameter: float
    side_b_parameter: float
    thickness_mm: float
    inside_source_loop: bool
    measurement_method: str = "camber_normal_line_intersections"
    normal_line_residual_mm: float = 0.0


@dataclass(frozen=True)
class ThicknessField:
    loop_id: str
    samples: tuple[ThicknessSample, ...]
    camber_fit: NurbsCurveFit
    method: str = "camber_normal_line_intersections"
    index_pairing_used: bool = False
    radial_distance_used: bool = False
    fallback_sample_count: int = 0
    correspondence_monotone: bool = True

    @property
    def minimum_mm(self) -> float:
        return min(sample.thickness_mm for sample in self.samples)

    @property
    def maximum_mm(self) -> float:
        return max(sample.thickness_mm for sample in self.samples)

    @property
    def mean_mm(self) -> float:
        return float(np.mean([sample.thickness_mm for sample in self.samples]))


@dataclass(frozen=True)
class AttachmentMeasurement:
    attachment_kind: str
    lift_mm: float
    attachment_width_mm: float
    local_span_direction_xyz: tuple[float, float, float]
    material_side: int
    lift_samples_mm: tuple[float, ...]
    width_samples_mm: tuple[float, ...]
    streamwise_samples_s: tuple[float, ...]
    source_face_ids: tuple[str, ...]
    footprint_source_edge_ids: tuple[str, ...]
    retained_source_edge_ids: tuple[str, ...]
    span_direction_source_ids: tuple[str, ...]
    termination_source_edge_ids: tuple[str, ...]
    local_span_directions_xyz: tuple[tuple[float, float, float], ...]
    provenance_kind: str
    adjacency_evidence: Mapping[str, tuple[str, ...]]
    termination_point_count: int
    span_direction_evidence: tuple[Mapping[str, Any], ...] = ()
    span_direction_angular_residual_max_deg: float = 0.0
    span_direction_angular_tolerance_deg: float = 0.0
    source_measurement: bool = True
    promotable: bool = True
    footprint_source: str = "source_adjacency_boundary"
    retained_boundary_source: str = "source_retained_blade_boundary"
    width_method: str = "support_tangent_plane_caliper"
    correspondence_method: str = "nearest_support_tangent_projection"
    copied_from_preset: bool = False
    footprint_points_xyz_mm: tuple[tuple[float, float, float], ...] = ()
    retained_points_xyz_mm: tuple[tuple[float, float, float], ...] = ()
    paired_footprint_points_xyz_mm: tuple[tuple[float, float, float], ...] = ()
    footprint_points_canonical_rz_mm: tuple[tuple[float, float], ...] = ()
    retained_points_canonical_rz_mm: tuple[tuple[float, float], ...] = ()
    retained_point_source_edge_ids: tuple[str, ...] = ()
    retained_streamwise_samples_s: tuple[float, ...] = ()
    retained_streamwise_projection_residual_max_mm: float = 0.0
    retained_streamwise_projection_method: str = ""
    termination_points_xyz_mm: tuple[tuple[float, float, float], ...] = ()
    termination_points_canonical_rz_mm: tuple[tuple[float, float], ...] = ()
    termination_streamwise_samples_s: tuple[float, ...] = ()


def solve_meridional_correspondence(
    hub_profile: Mapping[str, Any] | Sequence[Sequence[float]],
    tip_profile: Mapping[str, Any] | Sequence[Sequence[float]],
    *,
    sample_count: int = 129,
    closest_weight: float = 0.65,
    arc_length_weight: float = 0.35,
) -> MeridionalCorrespondence:
    count = int(sample_count)
    if count < 9:
        raise ValueError("sample_count must be at least 9")
    if closest_weight < 0.0 or arc_length_weight < 0.0 or closest_weight + arc_length_weight <= 0.0:
        raise ValueError("correspondence weights must be nonnegative with a positive sum")

    hub = _profile_points(hub_profile, count)
    tip_forward = _profile_points(tip_profile, count)
    if _support_polylines_intersect(hub, tip_forward):
        raise SectionRecoveryError(
            "v116_span_surface_ordering_failed",
            "hub and tip support curves intersect or overlap before correspondence",
            {"support_intersection": True},
        )
    forward_cost = _endpoint_pair_cost(hub, tip_forward)
    reverse_cost = _endpoint_pair_cost(hub, tip_forward[::-1])
    tip_reversed = reverse_cost + 1.0e-12 < forward_cost
    tip = tip_forward[::-1].copy() if tip_reversed else tip_forward

    hub_parameters = np.linspace(0.0, 1.0, count)
    tip_parameters = np.linspace(0.0, 1.0, count)
    distances = np.linalg.norm(hub[:, None, :] - tip[None, :, :], axis=2)
    nearest_indices = np.argmin(distances, axis=1)
    nearest_parameters = tip_parameters[nearest_indices]
    weight_sum = closest_weight + arc_length_weight
    targets = (
        closest_weight * nearest_parameters + arc_length_weight * hub_parameters
    ) / weight_sum
    targets[0] = 0.0
    targets[-1] = 1.0
    monotone = _isotonic_non_decreasing(targets)
    strict_fraction = 1.0e-7
    phi = (1.0 - strict_fraction) * monotone + strict_fraction * hub_parameters
    phi[0] = 0.0
    phi[-1] = 1.0
    matched_tip = _interpolate_polyline_by_fraction(tip, phi)
    span_lengths = np.linalg.norm(matched_tip - hub, axis=1)
    if float(np.min(span_lengths)) <= 1.0e-7:
        raise SectionRecoveryError(
            "v116_span_surface_ordering_failed",
            "hub and tip supports touch or coincide in the measured flowpath",
            {"minimum_span_mm": float(np.min(span_lengths))},
        )

    minimum_step = float(np.min(np.diff(phi)))
    if minimum_step <= 0.0:
        raise SectionRecoveryError(
            "v116_span_surface_ordering_failed",
            "hub-to-tip correspondence does not preserve strict flowwise order",
            {"minimum_parameter_step": minimum_step},
        )
    _reject_crossing_span_connectors(hub, matched_tip)

    matched_distance = np.linalg.norm(matched_tip - hub, axis=1)
    nearest_distance = np.min(distances, axis=1)
    residual = np.maximum(0.0, matched_distance - nearest_distance)
    return MeridionalCorrespondence(
        hub_parameters=tuple(_round(value) for value in hub_parameters),
        tip_parameters=tuple(_round(value) for value in phi),
        hub_points_rz_mm=_tuple_points(hub, 2),
        tip_points_rz_mm=_tuple_points(matched_tip, 2),
        tip_reversed=tip_reversed,
        closest_residual_rms_mm=_round(math.sqrt(float(np.mean(residual**2)))),
        closest_residual_max_mm=_round(float(np.max(residual))),
        minimum_parameter_step=_round(minimum_step),
    )


def select_adaptive_span_stations(
    metric_sampler: Callable[[float], Mapping[str, Any]] | None = None,
    *,
    active_root_h: float | None = None,
    active_tip_h: float | None = None,
    active_root_evidence: Mapping[str, Any] | None = None,
    active_tip_evidence: Mapping[str, Any] | None = None,
    known_source_face_ids: Sequence[str] | set[str] | None = None,
    known_source_edge_ids: Sequence[str] | set[str] | None = None,
    thresholds: Mapping[str, float] | None = None,
    maximum_station_count: int = 9,
) -> tuple[SpanStation, ...]:
    root_evidence = _validated_active_span_evidence(
        active_root_evidence,
        "root",
        active_root_h,
        known_source_face_ids=known_source_face_ids,
        known_source_edge_ids=known_source_edge_ids,
    )
    tip_evidence = _validated_active_span_evidence(
        active_tip_evidence,
        "tip",
        active_tip_h,
        known_source_face_ids=known_source_face_ids,
        known_source_edge_ids=known_source_edge_ids,
    )
    root = float(root_evidence["h"])
    tip = float(tip_evidence["h"])
    maximum = int(maximum_station_count)
    if not (0.0 <= root < tip <= 1.0):
        raise ValueError("active span endpoints must satisfy 0 <= root < tip <= 1")
    if maximum < 5 or maximum > 9:
        raise ValueError("maximum_station_count must be between 5 and 9")
    sampler = metric_sampler or (lambda _h: {})
    limits = {str(key): _positive(value, f"thresholds[{key}]") for key, value in (thresholds or {}).items()}

    if root < 0.25 < 0.5 < 0.75 < tip:
        initial_values = [root, 0.25, 0.5, 0.75, tip]
    else:
        initial_values = list(np.linspace(root, tip, 5))
    metrics: dict[float, Mapping[str, Any]] = {}
    reasons: dict[float, tuple[str, ...]] = {}
    initial_set = {_hkey(value) for value in initial_values}

    def measured(value: float) -> Mapping[str, Any]:
        key = _hkey(value)
        if key not in metrics:
            record = sampler(float(value))
            if not isinstance(record, Mapping):
                raise TypeError("metric_sampler must return a mapping")
            metrics[key] = dict(record)
        return metrics[key]

    values = sorted(float(value) for value in initial_values)
    for value in values:
        measured(value)
        reasons[_hkey(value)] = ("initial_lattice",)

    while len(values) < maximum and limits:
        candidates: list[tuple[float, float, tuple[str, ...]]] = []
        for lower, upper in zip(values[:-1], values[1:]):
            midpoint = 0.5 * (lower + upper)
            lower_metrics = measured(lower)
            upper_metrics = measured(upper)
            midpoint_metrics = measured(midpoint)
            scores: list[tuple[str, float]] = []
            for name, limit in limits.items():
                if name not in lower_metrics or name not in upper_metrics or name not in midpoint_metrics:
                    continue
                delta = _metric_refinement_error(
                    lower_metrics[name], midpoint_metrics[name], upper_metrics[name]
                )
                if delta > limit:
                    scores.append((name, delta / limit))
            if scores:
                ordered = sorted(scores, key=lambda item: (-item[1], item[0]))
                candidates.append(
                    (
                        max(score for _, score in ordered),
                        midpoint,
                        tuple(name for name, _ in ordered),
                    )
                )
        if not candidates:
            break
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        available = maximum - len(values)
        added = 0
        for _score, midpoint, refinement_reasons in candidates:
            if added >= available or any(abs(midpoint - value) <= 1.0e-12 for value in values):
                continue
            values.append(midpoint)
            reasons[_hkey(midpoint)] = refinement_reasons
            added += 1
        if not added:
            break
        values.sort()

    return tuple(
        SpanStation(
            h=_round(value),
            metrics=metrics[_hkey(value)],
            refinement_reasons=reasons[_hkey(value)],
            initial=_hkey(value) in initial_set,
        )
        for value in values
    )


def build_ordered_span_profiles(
    correspondence: MeridionalCorrespondence,
    span_values: Sequence[float],
    *,
    beta: Callable[[float, float], float] | None = None,
    refinement_reasons: Mapping[float, Sequence[str]] | None = None,
) -> tuple[SpanProfile, ...]:
    values = [float(value) for value in span_values]
    if not values or any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        raise ValueError("span_values must contain finite values in [0,1]")
    if any(values[index] >= values[index + 1] for index in range(len(values) - 1)):
        raise SectionRecoveryError(
            "v116_span_surface_ordering_failed", "span station values must be strictly increasing"
        )
    hub = np.asarray(correspondence.hub_points_rz_mm, dtype=float)
    tip = np.asarray(correspondence.tip_points_rz_mm, dtype=float)
    u_values = np.asarray(correspondence.hub_parameters, dtype=float)
    vectors = tip - hub
    profiles: list[SpanProfile] = []
    previous_beta: np.ndarray | None = None
    for h in values:
        beta_values = np.asarray(
            [beta(h, float(u)) if beta is not None else h for u in u_values], dtype=float
        )
        if not np.all(np.isfinite(beta_values)) or np.any(beta_values < -1.0e-12) or np.any(
            beta_values > 1.0 + 1.0e-12
        ):
            raise SectionRecoveryError(
                "v116_span_surface_ordering_failed", "span interpolation beta leaves [0,1]"
            )
        if previous_beta is not None and np.any(beta_values <= previous_beta + 1.0e-12):
            raise SectionRecoveryError(
                "v116_span_surface_ordering_failed",
                "span interpolation beta is not strictly monotone across stations",
            )
        points = hub + beta_values[:, None] * vectors
        if profiles:
            previous_points = np.asarray(profiles[-1].points_rz_mm, dtype=float)
            minimum_separation = float(np.min(np.linalg.norm(points - previous_points, axis=1)))
            if minimum_separation <= 1.0e-9:
                raise SectionRecoveryError(
                    "v116_span_surface_ordering_failed",
                    "adjacent meridional span profiles touch or coincide",
                    {"minimum_separation_mm": minimum_separation},
                )
        if _polyline_self_intersections(points):
            raise SectionRecoveryError(
                "v116_span_surface_ordering_failed", "a meridional span profile self-intersects"
            )
        if profiles and _open_polylines_intersect(
            np.asarray(profiles[-1].points_rz_mm, dtype=float), points
        ):
            raise SectionRecoveryError(
                "v116_span_surface_ordering_failed", "adjacent meridional span profiles intersect"
            )
        reason_values = ()
        if refinement_reasons:
            for key, item in refinement_reasons.items():
                if abs(float(key) - h) <= 1.0e-10:
                    reason_values = tuple(str(value) for value in item)
                    break
        profiles.append(
            SpanProfile(
                h=_round(h),
                points_rz_mm=_tuple_points(points, 2),
                refinement_reasons=reason_values,
            )
        )
        previous_beta = beta_values
    return tuple(profiles)


def build_adaptive_span_profiles(
    hub_profile: Mapping[str, Any] | Sequence[Sequence[float]],
    tip_profile: Mapping[str, Any] | Sequence[Sequence[float]],
    metric_sampler: Callable[[float], Mapping[str, Any]] | None = None,
    *,
    active_root_h: float | None = None,
    active_tip_h: float | None = None,
    active_root_evidence: Mapping[str, Any] | None = None,
    active_tip_evidence: Mapping[str, Any] | None = None,
    known_source_face_ids: Sequence[str] | set[str] | None = None,
    known_source_edge_ids: Sequence[str] | set[str] | None = None,
    thresholds: Mapping[str, float] | None = None,
    maximum_station_count: int = 9,
    correspondence_sample_count: int = 129,
) -> AdaptiveSpanLattice:
    root_evidence = _validated_active_span_evidence(
        active_root_evidence,
        "root",
        active_root_h,
        known_source_face_ids=known_source_face_ids,
        known_source_edge_ids=known_source_edge_ids,
    )
    tip_evidence = _validated_active_span_evidence(
        active_tip_evidence,
        "tip",
        active_tip_h,
        known_source_face_ids=known_source_face_ids,
        known_source_edge_ids=known_source_edge_ids,
    )
    correspondence = solve_meridional_correspondence(
        hub_profile, tip_profile, sample_count=correspondence_sample_count
    )
    stations = select_adaptive_span_stations(
        metric_sampler,
        active_root_h=float(root_evidence["h"]),
        active_tip_h=float(tip_evidence["h"]),
        active_root_evidence=root_evidence,
        active_tip_evidence=tip_evidence,
        known_source_face_ids=known_source_face_ids,
        known_source_edge_ids=known_source_edge_ids,
        thresholds=thresholds,
        maximum_station_count=maximum_station_count,
    )
    profiles = build_ordered_span_profiles(
        correspondence,
        [station.h for station in stations],
        refinement_reasons={station.h: station.refinement_reasons for station in stations},
    )
    return AdaptiveSpanLattice(
        correspondence=correspondence,
        stations=stations,
        profiles=profiles,
        maximum_station_count=maximum_station_count,
        active_root_evidence=root_evidence,
        active_tip_evidence=tip_evidence,
    )


def make_occt_revolved_measurement_surface(
    profile: SpanProfile | Sequence[Sequence[float]],
    *,
    tolerance_mm: float = 1.0e-6,
    angular_sector_deg: tuple[float, float] | None = None,
) -> Any:
    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.Geom import Geom_SurfaceOfRevolution
        from OCP.GeomAPI import GeomAPI_PointsToBSpline
        from OCP.GeomAbs import GeomAbs_C2
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
    except ImportError as exc:
        raise SectionRecoveryError(
            "v116_section_intersection_failed", "OCP measurement-surface support is unavailable"
        ) from exc
    points = np.asarray(
        profile.points_rz_mm if isinstance(profile, SpanProfile) else profile, dtype=float
    )
    _validate_points(points, 2, "profile")
    array = TColgp_Array1OfPnt(1, len(points))
    for index, (radius, axial) in enumerate(points, start=1):
        array.SetValue(index, gp_Pnt(float(radius), 0.0, float(axial)))
    builder = GeomAPI_PointsToBSpline(array, 3, 8, GeomAbs_C2, tolerance_mm)
    curve = builder.Curve()
    surface = Geom_SurfaceOfRevolution(
        curve,
        gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
    )
    if angular_sector_deg is None:
        return surface
    first_deg, last_deg, _margin = _expanded_angular_sector_bounds_deg(
        angular_sector_deg
    )
    first_angle = math.radians(first_deg)
    last_angle = math.radians(last_deg)
    return BRepBuilderAPI_MakeFace(
        surface,
        first_angle,
        last_angle,
        float(curve.FirstParameter()),
        float(curve.LastParameter()),
        float(tolerance_mm),
    ).Face()


def _expanded_angular_sector_bounds_deg(
    angular_sector_deg: Sequence[float],
) -> tuple[float, float, float]:
    start = _normalize_degrees(float(angular_sector_deg[0]))
    extent = (
        _normalize_degrees(float(angular_sector_deg[1])) - start
    ) % 360.0
    if extent <= 1.0e-9:
        raise ValueError("angular_sector_deg must define a nonzero sector")
    margin = max(1.0, 0.1 * extent)
    return start - margin, start + extent + margin, margin


def _minimum_angular_cutter_boundary_clearance_deg(
    points_xyz_mm: Sequence[Sequence[float]],
    angular_sector_deg: Sequence[float],
) -> float:
    points = np.asarray(points_xyz_mm, dtype=float)
    _validate_points(points, 3, "points_xyz_mm", minimum=1)
    first_deg, last_deg, _margin = _expanded_angular_sector_bounds_deg(
        angular_sector_deg
    )
    angles = np.degrees(np.arctan2(points[:, 1], points[:, 0]))

    def circular_distance(values: np.ndarray, boundary: float) -> np.ndarray:
        return np.abs((values - boundary + 180.0) % 360.0 - 180.0)

    return float(
        min(
            np.min(circular_distance(angles, first_deg)),
            np.min(circular_distance(angles, last_deg)),
        )
    )


def section_source_solid(
    source_shape: Any,
    measurement_surface: Any,
    *,
    angular_sector_deg: tuple[float, float] | None = None,
    angular_source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_faces_by_id: Mapping[str, Any] | None = None,
    source_edges_by_id: Mapping[str, Any] | None = None,
    source_face_edge_ids: Mapping[str, Sequence[str]] | None = None,
    allowed_source_face_ids: Sequence[str] | None = None,
    source_face_roles: Mapping[str, str] | None = None,
    local_frame: LocalSectionFrame | None = None,
    local_projector: Callable[[Sequence[float]], Sequence[float]] | None = None,
    section_normal_xyz: Sequence[float] = (0.0, 0.0, 1.0),
    material_side: int = 1,
    source_tolerance_mm: float = 0.02,
    edge_sample_count: int = 17,
    reference_loop: SectionLoop | None = None,
    source_shape_scope: str = "complete_source_shape",
    accept_authenticated_open_side_pair: bool = False,
) -> ExactSectionResult:
    try:
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Face
    except ImportError as exc:
        raise SectionRecoveryError(
            "v116_section_intersection_failed", "OCP exact section support is unavailable"
        ) from exc

    tolerance = _positive(source_tolerance_mm, "source_tolerance_mm")
    count = int(edge_sample_count)
    if count < 3:
        raise ValueError("edge_sample_count must be at least 3")
    if not source_faces_by_id or not allowed_source_face_ids:
        raise SectionRecoveryError(
            "v116_section_intersection_failed",
            "full-source sectioning requires an explicit face inventory and population allow-list",
            {
                "source_face_map_present": bool(source_faces_by_id),
                "allow_list_present": bool(allowed_source_face_ids),
            },
        )
    supported_scopes = {
        "complete_source_shape",
        "authenticated_representative_face_compound",
        "authenticated_representative_sewn_shell",
        "authenticated_representative_individual_faces",
    }
    if source_shape_scope not in supported_scopes:
        raise ValueError(
            "source_shape_scope must be complete_source_shape, "
            "authenticated_representative_face_compound or "
            "authenticated_representative_sewn_shell or "
            "authenticated_representative_individual_faces"
        )
    face_records = [
        (str(face_id), _wrapped(face))
        for face_id, face in (source_faces_by_id or {}).items()
    ]
    face_lookup = dict(face_records)
    source_surface_authority_cache: dict[str, Mapping[str, Any] | None] = {}
    allowed = {str(value) for value in allowed_source_face_ids or ()}
    unknown_allowed = sorted(
        allowed.difference(face_id for face_id, _face in face_records)
    )
    if unknown_allowed:
        raise SectionRecoveryError(
            "v116_section_intersection_failed",
            "population allow-list references faces outside the complete source inventory",
            {"unknown_allowed_source_face_ids": unknown_allowed},
        )
    role_map = {
        str(key): _canonical_segment_role(value)
        for key, value in (source_face_roles or {}).items()
    }
    if source_shape_scope == "complete_source_shape":
        source = _wrapped(source_shape)
    elif source_shape_scope == "authenticated_representative_face_compound":
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for face_id, face in face_records:
            if face_id in allowed:
                builder.Add(compound, face)
        source = compound
    elif source_shape_scope == "authenticated_representative_sewn_shell":
        sewing = BRepBuilderAPI_Sewing(tolerance, True, True, True, False)
        for face_id, face in face_records:
            if face_id in allowed:
                sewing.Add(face)
        sewing.Perform()
        source = sewing.SewedShape()
        if source.IsNull():
            raise SectionRecoveryError(
                "v116_section_intersection_failed",
                "authenticated representative faces could not be sewn into a source shell",
                {"allowed_source_face_ids": sorted(allowed)},
            )
    surface = _wrapped(measurement_surface)
    explicit_section_edges: list[tuple[Any, str]] = []
    operation = None
    if source_shape_scope == "authenticated_representative_individual_faces":
        builder = BRep_Builder()
        section_shape = TopoDS_Compound()
        builder.MakeCompound(section_shape)
        for face_id, face in face_records:
            if face_id not in allowed:
                continue
            if (
                accept_authenticated_open_side_pair
                and role_map.get(face_id) not in {"side_a", "side_b"}
            ):
                continue
            face_operation = BRepAlgoAPI_Section(face, surface, False)
            face_operation.ComputePCurveOn1(True)
            face_operation.Approximation(False)
            face_operation.Build()
            if not face_operation.IsDone():
                raise SectionRecoveryError(
                    "v116_section_intersection_failed",
                    "OCCT failed to section an authenticated representative face",
                    {"source_face_id": face_id},
                )
            face_explorer = TopExp_Explorer(face_operation.Shape(), TopAbs_EDGE)
            while face_explorer.More():
                section_edge = TopoDS.Edge_s(face_explorer.Current())
                builder.Add(section_shape, section_edge)
                explicit_section_edges.append((section_edge, face_id))
                face_explorer.Next()
    else:
        operation = BRepAlgoAPI_Section(source, surface, False)
        operation.ComputePCurveOn1(True)
        operation.Approximation(False)
        operation.Build()
        if not operation.IsDone():
            raise SectionRecoveryError(
                "v116_section_intersection_failed",
                f"OCCT failed to section {source_shape_scope}",
            )
        section_shape = operation.Shape()

    angular_matrix = None
    if angular_source_to_canonical_matrix is not None:
        angular_matrix = np.asarray(
            angular_source_to_canonical_matrix, dtype=float
        )
        if angular_matrix.shape != (4, 4) or not np.all(np.isfinite(angular_matrix)):
            raise ValueError(
                "angular_source_to_canonical_matrix must be a finite 4x4 transform"
            )
    raw_edges: list[dict[str, Any]] = []
    rejected: list[Mapping[str, Any]] = []
    unresolved: list[Mapping[str, Any]] = []
    minimum_cutter_clearance_deg = math.inf
    explorer = TopExp_Explorer(section_shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        adaptor = BRepAdaptor_Curve(edge)
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        parameters = np.linspace(first, last, count)
        points = np.asarray(
            [
                [
                    float(adaptor.Value(float(parameter)).X()),
                    float(adaptor.Value(float(parameter)).Y()),
                    float(adaptor.Value(float(parameter)).Z()),
                ]
                for parameter in parameters
            ],
            dtype=float,
        )
        first_vertex = TopExp.FirstVertex_s(edge, True)
        last_vertex = TopExp.LastVertex_s(edge, True)
        first_vertex_point = BRep_Tool.Pnt_s(first_vertex)
        last_vertex_point = BRep_Tool.Pnt_s(last_vertex)
        first_xyz = np.asarray(
            [
                float(first_vertex_point.X()),
                float(first_vertex_point.Y()),
                float(first_vertex_point.Z()),
            ],
            dtype=float,
        )
        last_xyz = np.asarray(
            [
                float(last_vertex_point.X()),
                float(last_vertex_point.Y()),
                float(last_vertex_point.Z()),
            ],
            dtype=float,
        )
        direct_residual = float(
            np.linalg.norm(points[0] - first_xyz)
            + np.linalg.norm(points[-1] - last_xyz)
        )
        reversed_residual = float(
            np.linalg.norm(points[-1] - first_xyz)
            + np.linalg.norm(points[0] - last_xyz)
        )
        if reversed_residual + 1.0e-12 < direct_residual:
            points = points[::-1].copy()
        if source_shape_scope == "authenticated_representative_individual_faces":
            face_ids = tuple(
                sorted(
                    face_id
                    for section_edge, face_id in explicit_section_edges
                    if section_edge.IsSame(edge)
                )
            )
            provenance_available = bool(face_ids)
        else:
            ancestor = TopoDS_Face()
            provenance_available = bool(
                operation is not None
                and operation.HasAncestorFaceOn1(edge, ancestor)
            )
            face_ids = tuple(
                sorted(
                    face_id
                    for face_id, face in face_records
                    if provenance_available and ancestor.IsSame(face)
                )
            )
        angular_points = points
        if angular_matrix is not None:
            homogeneous = np.column_stack([points, np.ones(len(points))])
            angular_points = (angular_matrix @ homogeneous.T).T[:, :3]
        angle = _circular_mean_deg(
            [
                math.degrees(math.atan2(point[1], point[0]))
                for point in angular_points
            ]
        )
        fingerprint = _edge_fingerprint(points, face_ids)
        if not provenance_available or not face_ids:
            unresolved.append(
                {
                    "fingerprint": fingerprint,
                    "reason": "source_face_ancestor_missing",
                    "source_face_ids": list(face_ids),
                }
            )
            explorer.Next()
            continue
        if angular_sector_deg is not None and set(face_ids).issubset(allowed):
            clearance = _minimum_angular_cutter_boundary_clearance_deg(
                angular_points, angular_sector_deg
            )
            minimum_cutter_clearance_deg = min(
                minimum_cutter_clearance_deg, clearance
            )
            minimum_radius = max(
                float(np.min(np.linalg.norm(angular_points[:, :2], axis=1))),
                tolerance,
            )
            angular_tolerance_deg = math.degrees(tolerance / minimum_radius)
            if clearance <= max(1.0e-7, angular_tolerance_deg):
                raise SectionRecoveryError(
                    "v116_section_intersection_failed",
                    "allowed source section contacts the bounded angular cutter",
                    {
                        "fingerprint": fingerprint,
                        "source_face_ids": list(face_ids),
                        "cutter_boundary_clearance_deg": clearance,
                        "required_clearance_deg": max(
                            1.0e-7, angular_tolerance_deg
                        ),
                    },
                )
        if (
            angular_sector_deg is not None
            and source_shape_scope == "complete_source_shape"
            and not _angle_in_sector(angle, angular_sector_deg, 1.0e-7)
        ):
            rejected.append(
                {
                    "fingerprint": fingerprint,
                    "reason": "outside_angular_sector",
                    "angle_deg": angle,
                    "source_face_ids": list(face_ids),
                }
            )
            explorer.Next()
            continue
        if not set(face_ids).issubset(allowed):
            rejected.append(
                {
                    "fingerprint": fingerprint,
                    "reason": "source_face_provenance_not_allowed",
                    "source_face_ids": list(face_ids),
                }
            )
            explorer.Next()
            continue
        source_roles = tuple(
            sorted(
                {
                    role_map[face_id]
                    for face_id in face_ids
                    if face_id in role_map
                }
            )
        )
        parameter_face_id = face_ids[0] if len(face_ids) == 1 else None
        parameter_uv: tuple[tuple[float, float], ...] = ()
        parameter_residual = 0.0
        surface_parameter_authority = None
        if parameter_face_id is not None:
            parameter_uv, parameter_residual = _source_face_parameter_samples(
                face_lookup[parameter_face_id],
                points,
                tolerance=tolerance,
            )
            if set(source_roles).intersection({"side_a", "side_b"}):
                if parameter_face_id not in source_surface_authority_cache:
                    source_surface_authority_cache[parameter_face_id] = (
                        _source_face_bspline_parameter_authority(
                            face_lookup[parameter_face_id],
                            source_face_id=parameter_face_id,
                            source_edges_by_id={
                                edge_id: source_edges_by_id[edge_id]
                                for edge_id in (
                                    source_face_edge_ids or {}
                                ).get(parameter_face_id, ())
                                if source_edges_by_id is not None
                                and edge_id in source_edges_by_id
                            },
                        )
                    )
                surface_parameter_authority = source_surface_authority_cache[
                    parameter_face_id
                ]
        if (
            accept_authenticated_open_side_pair
            and set(source_roles).intersection({"side_a", "side_b"})
            and (not parameter_uv or surface_parameter_authority is None)
        ):
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed",
                "an authenticated blade-side section lacks source-face UV witnesses",
                {
                    "fingerprint": fingerprint,
                    "source_face_ids": list(face_ids),
                    "source_roles": list(source_roles),
                    "source_surface_parameter_authority_available": bool(
                        surface_parameter_authority
                    ),
                },
            )
        raw_edges.append(
            {
                "fingerprint": fingerprint,
                "points": points,
                "source_face_ids": face_ids,
                "source_roles": source_roles,
                "provenance_available": provenance_available,
                "first_vertex": first_vertex,
                "last_vertex": last_vertex,
                "topology_endpoint_residual_mm": min(
                    direct_residual, reversed_residual
                ),
                "parameter_direction_reversed": bool(
                    reversed_residual + 1.0e-12 < direct_residual
                ),
                "source_parameter_face_id": parameter_face_id,
                "source_face_parameter_uv": parameter_uv,
                "source_face_parameter_residual_max_mm": parameter_residual,
                "source_surface_parameter_authority": surface_parameter_authority,
            }
        )
        explorer.Next()

    if unresolved:
        raise SectionRecoveryError(
            "v116_section_intersection_failed",
            "one or more exact section edges cannot be resolved to the complete source face inventory",
            {
                "unresolved_section_edge_count": len(unresolved),
                "unresolved_section_edges": list(unresolved),
            },
        )
    if not raw_edges:
        raise SectionRecoveryError(
            "v116_section_intersection_failed",
            "the exact full-source section produced no edges in the requested population sector",
            {"rejected_edges": list(rejected)},
        )
    raw_edges.sort(key=lambda record: record["fingerprint"])
    topology_vertices: list[Any] = []

    def topology_vertex_id(vertex: Any) -> str:
        for vertex_index, existing in enumerate(topology_vertices):
            if vertex.IsSame(existing):
                return f"occt_vertex_{vertex_index:03d}"
        topology_vertices.append(vertex)
        return f"occt_vertex_{len(topology_vertices) - 1:03d}"

    preserve_shared_topology = (
        source_shape_scope != "authenticated_representative_individual_faces"
    )
    edges = tuple(
        SectionEdge(
            edge_id=f"source_section_edge_{index:03d}",
            points_xyz_mm=_tuple_points(record["points"], 3),
            source_face_ids=record["source_face_ids"],
            source_roles=record["source_roles"],
            provenance_available=record["provenance_available"],
            exact_curve=False,
            source_curve_exact=True,
            sampled_display_only=True,
            topology_start_vertex_id=(
                topology_vertex_id(record["first_vertex"])
                if preserve_shared_topology
                else None
            ),
            topology_end_vertex_id=(
                topology_vertex_id(record["last_vertex"])
                if preserve_shared_topology
                else None
            ),
            topology_endpoint_residual_mm=_round(
                record["topology_endpoint_residual_mm"]
            ),
            parameter_direction_reversed=record["parameter_direction_reversed"],
            source_parameter_face_id=record["source_parameter_face_id"],
            source_face_parameter_uv=record["source_face_parameter_uv"],
            source_face_parameter_residual_max_mm=_round(
                record["source_face_parameter_residual_max_mm"]
            ),
            source_surface_parameter_authority=record[
                "source_surface_parameter_authority"
            ],
        )
        for index, record in enumerate(raw_edges)
    )
    if (
        accept_authenticated_open_side_pair
        and source_shape_scope == "authenticated_representative_individual_faces"
    ):
        accepted_loop = select_authenticated_open_side_pair(
            edges,
            source_tolerance_mm=tolerance,
            local_frame=local_frame,
            local_projector=local_projector,
            section_normal_xyz=section_normal_xyz,
            material_side=material_side,
        )
        return ExactSectionResult(
            accepted_loop=accepted_loop,
            additional_loops=(),
            rejected_edges=tuple(rejected),
            source_shape_scope=source_shape_scope,
            wire_assembly_method=(
                "independent_exact_side_curves_with_review_only_endpoint_bridges"
            ),
            cutter_boundary_clearance_deg=(
                None
                if not math.isfinite(minimum_cutter_clearance_deg)
                else minimum_cutter_clearance_deg
            ),
            cutter_boundary_clearance_verified=(
                angular_sector_deg is None
                or math.isfinite(minimum_cutter_clearance_deg)
            ),
        )
    try:
        loops = order_section_edges(
            edges,
            source_tolerance_mm=tolerance,
            local_frame=local_frame,
            local_projector=local_projector,
            section_normal_xyz=section_normal_xyz,
            material_side=material_side,
            source_kind=(
                "occt_exact_full_source_section"
                if source_shape_scope == "complete_source_shape"
                else (
                    "occt_exact_authenticated_face_compound_section"
                    if source_shape_scope
                    == "authenticated_representative_face_compound"
                    else (
                        "occt_exact_authenticated_sewn_shell_section"
                        if source_shape_scope
                        == "authenticated_representative_sewn_shell"
                        else "occt_exact_authenticated_individual_face_section"
                    )
                )
            ),
            allow_open_auxiliary_components=True,
        )
    except SectionRecoveryError as exc:
        exc.details.update(
            {
                "source_shape_scope": source_shape_scope,
                "raw_section_edge_count": len(raw_edges),
                "raw_section_source_face_ids": sorted(
                    {
                        face_id
                        for record in raw_edges
                        for face_id in record["source_face_ids"]
                    }
                ),
                "rejected_edges": list(rejected),
                "representative_instance_already_authenticated": (
                    source_shape_scope != "complete_source_shape"
                ),
            }
        )
        raise
    if not loops:
        raise SectionRecoveryError(
            "v116_section_loop_open", "the filtered exact section contains no closed contour"
        )
    sector_center = _sector_center_deg(angular_sector_deg) if angular_sector_deg is not None else None
    ranked = sorted(loops, key=lambda loop: _loop_selection_key(loop, sector_center, allowed))
    accepted_loop = _canonicalize_section_loop(ranked[0])
    landmark_tracking = None
    if reference_loop is not None:
        alignment = align_loop_orientation(reference_loop, accepted_loop)
        if alignment.corrected_loop is None:
            raise SectionRecoveryError(
                "v116_section_orientation_alignment_conflict",
                "section-loop alignment did not produce a provenance-preserving loop",
                {"reference_loop_id": reference_loop.loop_id},
            )
        accepted_loop = alignment.corrected_loop
        landmark_tracking = track_section_family_landmarks(
            (reference_loop, accepted_loop), alignments=(alignment,)
        )
    return ExactSectionResult(
        accepted_loop=accepted_loop,
        additional_loops=tuple(ranked[1:]),
        rejected_edges=tuple(rejected),
        source_shape_scope=source_shape_scope,
        landmark_tracking=landmark_tracking,
        cutter_boundary_clearance_deg=(
            None
            if not math.isfinite(minimum_cutter_clearance_deg)
            else minimum_cutter_clearance_deg
        ),
        cutter_boundary_clearance_verified=(
            angular_sector_deg is None
            or math.isfinite(minimum_cutter_clearance_deg)
        ),
    )


def section_full_source_solid(*args: Any, **kwargs: Any) -> ExactSectionResult:
    return section_source_solid(*args, **kwargs)


def order_section_edges(
    edges: Sequence[SectionEdge | Mapping[str, Any]],
    *,
    source_tolerance_mm: float,
    local_frame: LocalSectionFrame | None = None,
    local_projector: Callable[[Sequence[float]], Sequence[float]] | None = None,
    section_normal_xyz: Sequence[float] = (0.0, 0.0, 1.0),
    material_side: int = 1,
    source_kind: str = "ordered_source_section",
    allow_open_auxiliary_components: bool = False,
) -> tuple[SectionLoop, ...]:
    tolerance = _positive(source_tolerance_mm, "source_tolerance_mm")
    if material_side not in (-1, 1):
        raise ValueError("material_side must be -1 or 1")
    normalized = tuple(_section_edge(edge, index) for index, edge in enumerate(edges))
    if not normalized:
        return ()
    topology_flags = [
        edge.topology_start_vertex_id is not None and edge.topology_end_vertex_id is not None
        for edge in normalized
    ]
    if any(topology_flags) and not all(topology_flags):
        raise SectionRecoveryError(
            "v116_section_loop_open",
            "section edge set mixes OCCT topology edges with geometry-only edges",
        )
    if all(topology_flags):
        edge_vertices = [
            (str(edge.topology_start_vertex_id), str(edge.topology_end_vertex_id))
            for edge in normalized
        ]
        vertex_points: dict[str, np.ndarray] = {}
        for edge, (first_vertex, last_vertex) in zip(normalized, edge_vertices):
            vertex_points.setdefault(first_vertex, np.asarray(edge.points_xyz_mm[0], dtype=float))
            vertex_points.setdefault(last_vertex, np.asarray(edge.points_xyz_mm[-1], dtype=float))
        source_wire_exact = True
    else:
        edge_vertices, vertex_points = _cluster_geometry_endpoints(normalized, tolerance)
        source_wire_exact = False
    vertex_edges: dict[str, list[int]] = {}
    for edge_index, (first, second) in enumerate(edge_vertices):
        vertex_edges.setdefault(first, []).append(edge_index)
        vertex_edges.setdefault(second, []).append(edge_index)

    unvisited = set(range(len(normalized)))
    components: list[list[int]] = []
    while unvisited:
        seed = min(unvisited, key=lambda index: _edge_sort_key(normalized[index]))
        stack = [seed]
        component: set[int] = set()
        while stack:
            edge_index = stack.pop()
            if edge_index in component:
                continue
            component.add(edge_index)
            for vertex in edge_vertices[edge_index]:
                stack.extend(vertex_edges.get(vertex, ()))
        unvisited.difference_update(component)
        components.append(sorted(component, key=lambda index: _edge_sort_key(normalized[index])))

    loops: list[SectionLoop] = []
    discarded_open_components: list[dict[str, Any]] = []
    for component_index, component in enumerate(components):
        component_vertices = {vertex for index in component for vertex in edge_vertices[index]}
        bad_vertices = [
            vertex
            for vertex in component_vertices
            if sum(
                2 if edge_vertices[index][0] == edge_vertices[index][1] == vertex else 1
                for index in component
                if vertex in edge_vertices[index]
            )
            != 2
        ]
        if bad_vertices:
            if allow_open_auxiliary_components:
                discarded_open_components.append(
                    {
                        "component_index": component_index,
                        "component_edge_count": len(component),
                        "open_vertex_count": len(bad_vertices),
                        "vertex_degrees": sorted(
                            sum(
                                2
                                if edge_vertices[index][0]
                                == edge_vertices[index][1]
                                == vertex
                                else 1
                                for index in component
                                if vertex in edge_vertices[index]
                            )
                            for vertex in component_vertices
                        ),
                        "source_face_ids": sorted(
                            {
                                source_face_id
                                for index in component
                                for source_face_id in normalized[index].source_face_ids
                            }
                        ),
                        "source_roles": sorted(
                            {
                                source_role
                                for index in component
                                for source_role in normalized[index].source_roles
                            }
                        ),
                        "open_vertices_xyz_mm": [
                            [
                                _round(float(value))
                                for value in vertex_points[vertex]
                            ]
                            for vertex in sorted(
                                bad_vertices,
                                key=lambda item: _point_sort_key(vertex_points[item]),
                            )
                        ],
                        "edges": [
                            {
                                "edge_id": normalized[index].edge_id,
                                "source_face_ids": list(
                                    normalized[index].source_face_ids
                                ),
                                "source_roles": list(normalized[index].source_roles),
                                "start_xyz_mm": [
                                    _round(float(value))
                                    for value in normalized[index].points_xyz_mm[0]
                                ],
                                "end_xyz_mm": [
                                    _round(float(value))
                                    for value in normalized[index].points_xyz_mm[-1]
                                ],
                            }
                            for index in component
                        ],
                    }
                )
                continue
            raise SectionRecoveryError(
                "v116_section_loop_open",
                "section edges do not form a closed degree-two contour within source tolerance",
                {"open_vertex_count": len(bad_vertices), "component_edge_count": len(component)},
            )
        start_vertex = min(
            component_vertices, key=lambda vertex: _point_sort_key(vertex_points[vertex])
        )
        ordered_indices: list[int] = []
        ordered_edges: list[SectionEdge] = []
        current_vertex = start_vertex
        previous_edge: int | None = None
        while len(ordered_indices) < len(component):
            candidates = [
                index
                for index in vertex_edges[current_vertex]
                if index in component and index != previous_edge and index not in ordered_indices
            ]
            if not candidates:
                break
            edge_index = min(candidates, key=lambda index: _edge_sort_key(normalized[index]))
            edge = normalized[edge_index]
            first_vertex, second_vertex = edge_vertices[edge_index]
            points = np.asarray(edge.points_xyz_mm, dtype=float)
            if first_vertex == current_vertex:
                next_vertex = second_vertex
                ordered_edge = edge
            else:
                points = points[::-1]
                next_vertex = first_vertex
                ordered_edge = replace(
                    edge,
                    topology_start_vertex_id=edge.topology_end_vertex_id,
                    topology_end_vertex_id=edge.topology_start_vertex_id,
                )
            ordered_indices.append(edge_index)
            ordered_edges.append(
                replace(ordered_edge, points_xyz_mm=_tuple_points(points, 3))
            )
            previous_edge = edge_index
            current_vertex = next_vertex
        if len(ordered_indices) != len(component) or current_vertex != start_vertex:
            raise SectionRecoveryError(
                "v116_section_loop_open", "section contour traversal did not close"
            )
        raw_healing_gaps = tuple(
            float(
                np.linalg.norm(
                    np.asarray(ordered_edges[index].points_xyz_mm[-1], dtype=float)
                    - np.asarray(ordered_edges[(index + 1) % len(ordered_edges)].points_xyz_mm[0], dtype=float)
                )
            )
            for index in range(len(ordered_edges))
        )
        closure_gap = max(raw_healing_gaps, default=0.0)
        if closure_gap > tolerance:
            raise SectionRecoveryError(
                "v116_section_loop_open",
                f"section loop junction gap {closure_gap:.6f} mm exceeds source tolerance {tolerance:.6f} mm",
                {
                    "healing_gaps_mm": list(raw_healing_gaps),
                    "ordered_edges": [
                        {
                            "edge_id": edge.edge_id,
                            "topology_start_vertex_id": edge.topology_start_vertex_id,
                            "topology_end_vertex_id": edge.topology_end_vertex_id,
                            "sample_start_xyz_mm": list(edge.points_xyz_mm[0]),
                            "sample_end_xyz_mm": list(edge.points_xyz_mm[-1]),
                            "topology_endpoint_residual_mm": (
                                edge.topology_endpoint_residual_mm
                            ),
                            "parameter_direction_reversed": (
                                edge.parameter_direction_reversed
                            ),
                        }
                        for edge in ordered_edges
                    ],
                },
            )
        healed_edges: list[SectionEdge] = []
        for index, edge in enumerate(ordered_edges):
            points = np.asarray(edge.points_xyz_mm, dtype=float).copy()
            if index:
                points[0] = np.asarray(healed_edges[-1].points_xyz_mm[-1], dtype=float)
            healed_edges.append(replace(edge, points_xyz_mm=_tuple_points(points, 3)))
        if healed_edges:
            last_points = np.asarray(healed_edges[-1].points_xyz_mm, dtype=float).copy()
            last_points[-1] = np.asarray(healed_edges[0].points_xyz_mm[0], dtype=float)
            healed_edges[-1] = replace(
                healed_edges[-1], points_xyz_mm=_tuple_points(last_points, 3)
            )
        ordered_edges = healed_edges
        points_xyz = _concatenate_edge_points(ordered_edges)
        projector, normal = _section_projector(
            points_xyz,
            local_frame=local_frame,
            local_projector=local_projector,
            section_normal_xyz=section_normal_xyz,
        )
        points_sq = np.asarray([projector(point) for point in points_xyz], dtype=float)
        area = _signed_polygon_area(points_sq)
        desired_sign = float(material_side)
        reversed_for_material = area * desired_sign < 0.0
        if reversed_for_material:
            ordered_edges = [
                replace(
                    edge,
                    points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
                    source_face_parameter_uv=tuple(
                        reversed(edge.source_face_parameter_uv)
                    ),
                    topology_start_vertex_id=edge.topology_end_vertex_id,
                    topology_end_vertex_id=edge.topology_start_vertex_id,
                )
                for edge in reversed(ordered_edges)
            ]
            points_xyz = points_xyz[::-1].copy()
            points_sq = points_sq[::-1].copy()
        ordered_edges = [
            replace(
                edge,
                points_sq_mm=_tuple_points(
                    np.asarray([projector(point) for point in edge.points_xyz_mm], dtype=float), 2
                ),
            )
            for edge in ordered_edges
        ]
        start_edge_index = min(
            range(len(ordered_edges)),
            key=lambda index: _point_sort_key(ordered_edges[index].points_sq_mm[0]),
        )
        ordered_edges = (
            ordered_edges[start_edge_index:] + ordered_edges[:start_edge_index]
        )
        points_xyz = _concatenate_edge_points(ordered_edges)
        points_sq = _concatenate_edge_local_points(ordered_edges)
        tangent_flips = detect_tangent_flips(points_sq)
        if tangent_flips:
            raise SectionRecoveryError(
                "v116_section_tangent_flip_detected",
                "section loop contains a 180-degree tangent flip",
                {"sample_indices": list(tangent_flips)},
            )
        intersection_count = _closed_polyline_self_intersection_count(points_sq)
        if intersection_count:
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed",
                "section loop self-intersects in local (S,Q)",
                {"self_intersection_count": intersection_count},
            )
        source_faces = tuple(sorted({value for edge in ordered_edges for value in edge.source_face_ids}))
        loops.append(
            SectionLoop(
                loop_id=f"source_section_loop_{component_index:03d}",
                edges=tuple(ordered_edges),
                points_xyz_mm=_tuple_points(points_xyz, 3),
                points_sq_mm=_tuple_points(points_sq, 2),
                orientation="counterclockwise" if material_side > 0 else "clockwise",
                start_landmark="minimum_streamwise_coordinate",
                closure_gap_mm=_round(closure_gap),
                self_intersection_count=intersection_count,
                section_normal_xyz=tuple(float(value) for value in normal),
                material_side=material_side,
                source_face_ids=source_faces,
                source_edge_ids=tuple(edge.edge_id for edge in ordered_edges),
                source_tolerance_mm=_round(tolerance),
                source_kind=source_kind,
                orientation_evidence={
                    "rule": "signed_local_area_matches_material_side",
                    "reversed": reversed_for_material,
                    "signed_area_sq_mm2": _round(_signed_polygon_area(points_sq)),
                },
                healing_gaps_mm=tuple(_round(value) for value in raw_healing_gaps),
                healing_total_mm=_round(sum(raw_healing_gaps)),
                source_wire_exact=source_wire_exact,
                display_polyline_exact=False,
            )
        )
    if allow_open_auxiliary_components and not loops and discarded_open_components:
        raise SectionRecoveryError(
            "v116_section_loop_open",
            "the filtered exact section contains only open components",
            {"open_components": discarded_open_components},
        )
    return tuple(sorted(loops, key=lambda loop: _loop_geometry_key(loop.points_xyz_mm)))


def make_section_loop(
    points_sq_mm: Sequence[Sequence[float]],
    *,
    points_xyz_mm: Sequence[Sequence[float]] | None = None,
    loop_id: str = "source_section_loop",
    source_tolerance_mm: float = 0.02,
    material_side: int = 1,
    source_face_ids: Sequence[str] = (),
    source_edge_ids: Sequence[str] = (),
    source_kind: str = "pure_geometry_section_loop",
) -> SectionLoop:
    sq = np.asarray(points_sq_mm, dtype=float)
    _validate_points(sq, 2, "points_sq_mm", minimum=4)
    if np.linalg.norm(sq[0] - sq[-1]) > _EPSILON:
        sq = np.vstack([sq, sq[0]])
    xyz = (
        np.column_stack([sq[:, 0], sq[:, 1], np.zeros(len(sq))])
        if points_xyz_mm is None
        else np.asarray(points_xyz_mm, dtype=float)
    )
    if len(xyz) == len(sq) - 1:
        xyz = np.vstack([xyz, xyz[0]])
    _validate_points(xyz, 3, "points_xyz_mm", minimum=5)
    if len(xyz) != len(sq):
        raise ValueError("points_xyz_mm and points_sq_mm must have matching lengths")
    if material_side not in (-1, 1):
        raise ValueError("material_side must be -1 or 1")
    reversed_for_material = _signed_polygon_area(sq) * material_side < 0.0
    if reversed_for_material:
        sq = sq[::-1].copy()
        xyz = xyz[::-1].copy()
    start_index = _deterministic_loop_start(sq)
    sq = _rotate_closed(sq, start_index)
    xyz = _rotate_closed(xyz, start_index)
    tangent_flips = detect_tangent_flips(sq)
    if tangent_flips:
        raise SectionRecoveryError(
            "v116_section_tangent_flip_detected",
            "section loop contains a 180-degree tangent flip",
            {"sample_indices": list(tangent_flips)},
        )
    intersections = _closed_polyline_self_intersection_count(sq)
    if intersections:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "section loop self-intersects in local (S,Q)",
            {"self_intersection_count": intersections},
        )
    edge_ids = tuple(str(value) for value in source_edge_ids) or (f"{loop_id}_edge",)
    edge = SectionEdge(
        edge_id=edge_ids[0],
        points_xyz_mm=_tuple_points(xyz, 3),
        points_sq_mm=_tuple_points(sq, 2),
        source_face_ids=tuple(sorted(str(value) for value in source_face_ids)),
        exact_curve=False,
    )
    return SectionLoop(
        loop_id=str(loop_id),
        edges=(edge,),
        points_xyz_mm=_tuple_points(xyz, 3),
        points_sq_mm=_tuple_points(sq, 2),
        orientation="counterclockwise" if material_side > 0 else "clockwise",
        start_landmark="minimum_streamwise_coordinate",
        closure_gap_mm=0.0,
        self_intersection_count=0,
        section_normal_xyz=(0.0, 0.0, 1.0),
        material_side=material_side,
        source_face_ids=tuple(sorted(str(value) for value in source_face_ids)),
        source_edge_ids=edge_ids,
        source_tolerance_mm=_round(_positive(source_tolerance_mm, "source_tolerance_mm")),
        source_kind=source_kind,
        orientation_evidence={
            "rule": "signed_local_area_matches_material_side",
            "reversed": reversed_for_material,
            "signed_area_sq_mm2": _round(_signed_polygon_area(sq)),
        },
    )


def detect_tangent_flips(
    points_sq_mm: Sequence[Sequence[float]], *, threshold_deg: float = 175.0
) -> tuple[int, ...]:
    points = np.asarray(points_sq_mm, dtype=float)
    _validate_points(points, 2, "points_sq_mm", minimum=4)
    if not 90.0 < float(threshold_deg) <= 180.0:
        raise ValueError("threshold_deg must be in (90,180]")
    unique = points[:-1] if np.linalg.norm(points[0] - points[-1]) <= 1.0e-10 else points
    segments = np.roll(unique, -1, axis=0) - unique
    lengths = np.linalg.norm(segments, axis=1)
    flips: list[int] = []
    for index in range(len(segments)):
        previous = segments[index - 1]
        current = segments[index]
        if lengths[index - 1] <= _EPSILON or lengths[index] <= _EPSILON:
            flips.append(index)
            continue
        cosine = float(np.dot(previous, current) / (lengths[index - 1] * lengths[index]))
        angle = math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0))))
        if angle >= threshold_deg:
            flips.append(index)
    return tuple(flips)


def track_section_family_landmarks(
    loops: Sequence[SectionLoop],
    *,
    sample_count: int = 128,
    alignments: Sequence[OrientationAlignment] | None = None,
) -> dict[str, Any]:
    if len(loops) < 2:
        raise ValueError("at least two section loops are required for family landmark tracking")
    if alignments is not None and len(alignments) != len(loops) - 1:
        raise ValueError("alignments must contain one record for each candidate loop")
    reference = loops[0]
    reference_decomposition = decompose_section_loop(reference)
    records: list[dict[str, Any]] = []
    for index, candidate in enumerate(loops[1:]):
        alignment = (
            alignments[index]
            if alignments is not None
            else align_loop_orientation(reference, candidate, sample_count=sample_count)
        )
        corrected = alignment.corrected_loop
        if corrected is None:
            raise SectionRecoveryError(
                "v116_section_orientation_alignment_conflict",
                "cross-station tracking requires a complete corrected SectionLoop",
                {"candidate_loop_id": candidate.loop_id},
            )
        if corrected.points_sq_mm != candidate.points_sq_mm:
            candidate = corrected
        decomposition = decompose_section_loop(corrected)
        records.append(
            {
                "reference_loop_id": reference.loop_id,
                "candidate_loop_id": corrected.loop_id,
                "reversed": alignment.reversed,
                "circular_shift": alignment.circular_shift,
                "tangent_mismatch_deg": alignment.tangent_mismatch_deg,
                "forward_score": alignment.forward_score,
                "reverse_score": alignment.reverse_score,
                "corrected_applied": bool(
                    alignment.reversed or alignment.circular_shift
                ),
                "corrected_orientation": corrected.orientation,
                "corrected_points_sq_mm": [list(point) for point in corrected.points_sq_mm],
                "corrected_points_xyz_mm": [list(point) for point in corrected.points_xyz_mm],
                "corrected_source_edge_ids": list(corrected.source_edge_ids),
                "corrected_edge_face_ids": {
                    edge.edge_id: list(edge.source_face_ids) for edge in corrected.edges
                },
                "source_face_ids": list(corrected.source_face_ids),
                "landmark_method": decomposition.landmark_method,
                "landmarks_sq_mm": _json_value(decomposition.landmarks_sq_mm),
                "decomposition_input_points_sq_mm": [
                    list(point) for point in corrected.points_sq_mm
                ],
            }
        )
    return {
        "method": "cross_station_orientation_and_four_segment_landmark_tracking",
        "reference_loop_id": reference.loop_id,
        "reference_source_face_ids": list(reference.source_face_ids),
        "reference_landmark_method": reference_decomposition.landmark_method,
        "reference_landmarks_sq_mm": _json_value(reference_decomposition.landmarks_sq_mm),
        "records": records,
        "promotable": all(bool(record["source_face_ids"]) for record in records)
        and bool(reference.source_face_ids),
    }


def align_loop_orientation(
    reference: SectionLoop | Sequence[Sequence[float]],
    candidate: SectionLoop | Sequence[Sequence[float]],
    *,
    sample_count: int = 128,
) -> OrientationAlignment:
    reference_points = np.asarray(
        reference.points_sq_mm if isinstance(reference, SectionLoop) else reference,
        dtype=float,
    )
    candidate_points = np.asarray(
        candidate.points_sq_mm if isinstance(candidate, SectionLoop) else candidate,
        dtype=float,
    )
    tangent_flips = detect_tangent_flips(candidate_points)
    if tangent_flips:
        raise SectionRecoveryError(
            "v116_section_tangent_flip_detected",
            "candidate loop contains a local 180-degree tangent flip",
            {"sample_indices": list(tangent_flips)},
        )
    count = int(sample_count)
    if count < 16:
        raise ValueError("sample_count must be at least 16")
    ref = _resample_closed_polyline(reference_points, count, include_closure=False)
    cand = _resample_closed_polyline(candidate_points, count, include_closure=False)
    ref_normalized = _normalize_loop_for_correspondence(ref)
    forward_normalized = _normalize_loop_for_correspondence(cand)
    reverse_points = cand[::-1].copy()
    reverse_normalized = _normalize_loop_for_correspondence(reverse_points)
    forward_score, forward_shift, forward_tangent = _orientation_hypothesis_score(
        ref_normalized, forward_normalized
    )
    reverse_score, reverse_shift, reverse_tangent = _orientation_hypothesis_score(
        ref_normalized, reverse_normalized
    )
    use_reverse = reverse_score + 1.0e-12 < forward_score
    selected = reverse_points if use_reverse else cand
    shift = reverse_shift if use_reverse else forward_shift
    selected = np.roll(selected, shift, axis=0)
    selected = np.vstack([selected, selected[0]])
    corrected_loop = None
    corrected_points = _tuple_points(selected, 2)
    if isinstance(reference, SectionLoop) and isinstance(candidate, SectionLoop):
        corrected_loop = _apply_section_loop_alignment(
            reference,
            candidate,
            reversed_order=use_reverse,
            circular_shift=int(shift),
            corrected_resampled_sq=selected,
            sample_count=count,
            forward_score=forward_score,
            reverse_score=reverse_score,
            tangent_mismatch_deg=reverse_tangent if use_reverse else forward_tangent,
        )
        corrected_points = corrected_loop.points_sq_mm
    return OrientationAlignment(
        corrected_points_sq_mm=corrected_points,
        reversed=use_reverse,
        circular_shift=int(shift),
        forward_score=_round(forward_score),
        reverse_score=_round(reverse_score),
        tangent_mismatch_deg=_round(reverse_tangent if use_reverse else forward_tangent),
        corrected_loop=corrected_loop,
    )


def _apply_section_loop_alignment(
    reference: SectionLoop,
    candidate: SectionLoop,
    *,
    reversed_order: bool,
    circular_shift: int,
    corrected_resampled_sq: np.ndarray,
    sample_count: int,
    forward_score: float,
    reverse_score: float,
    tangent_mismatch_deg: float,
) -> SectionLoop:
    edges = list(candidate.edges)
    if not edges or any(not edge.points_sq_mm for edge in edges):
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "aligned source loop lacks complete edge-local coordinates",
            {"candidate_loop_id": candidate.loop_id},
        )
    if reversed_order:
        edges = [
            replace(
                edge,
                points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
                points_sq_mm=tuple(reversed(edge.points_sq_mm)),
                source_face_parameter_uv=tuple(
                    reversed(edge.source_face_parameter_uv)
                ),
                topology_start_vertex_id=edge.topology_end_vertex_id,
                topology_end_vertex_id=edge.topology_start_vertex_id,
            )
            for edge in reversed(edges)
        ]

    selected_start = corrected_resampled_sq[0]
    start_distances = [
        float(
            np.linalg.norm(
                np.asarray(edge.points_sq_mm[0], dtype=float) - selected_start
            )
        )
        for edge in edges
    ]
    start_edge_index = min(
        range(len(edges)), key=lambda index: (start_distances[index], edges[index].edge_id)
    )
    total_length = sum(
        _polyline_length(np.asarray(edge.points_sq_mm, dtype=float)) for edge in edges
    )
    alignment_tolerance = max(
        2.5 * total_length / max(sample_count, 1),
        10.0 * candidate.source_tolerance_mm,
        1.0e-8,
    )
    if start_distances[start_edge_index] > alignment_tolerance:
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "pointwise circular shift does not coincide with a source-edge boundary",
            {
                "candidate_loop_id": candidate.loop_id,
                "circular_shift": circular_shift,
                "nearest_edge_boundary_residual_mm": start_distances[start_edge_index],
                "alignment_tolerance_mm": alignment_tolerance,
            },
        )
    edges = edges[start_edge_index:] + edges[:start_edge_index]

    for index, edge in enumerate(edges):
        following = edges[(index + 1) % len(edges)]
        gap = float(
            np.linalg.norm(
                np.asarray(edge.points_xyz_mm[-1], dtype=float)
                - np.asarray(following.points_xyz_mm[0], dtype=float)
            )
        )
        topology_ids_present = bool(
            edge.topology_end_vertex_id and following.topology_start_vertex_id
        )
        topology_matches = (
            edge.topology_end_vertex_id == following.topology_start_vertex_id
            if topology_ids_present
            else True
        )
        if gap > candidate.source_tolerance_mm or not topology_matches:
            raise SectionRecoveryError(
                "v116_section_orientation_alignment_conflict",
                "aligned edge order does not preserve the exact source wire",
                {
                    "candidate_loop_id": candidate.loop_id,
                    "edge_id": edge.edge_id,
                    "following_edge_id": following.edge_id,
                    "junction_gap_mm": gap,
                    "topology_matches": topology_matches,
                },
            )

    points_xyz = _concatenate_edge_points(edges)
    points_sq = _concatenate_edge_local_points(edges)
    source_face_ids = tuple(
        sorted({face_id for edge in edges for face_id in edge.source_face_ids})
    )
    if source_face_ids != tuple(sorted(candidate.source_face_ids)) or {
        edge.edge_id for edge in edges
    } != set(candidate.source_edge_ids):
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "alignment changed source edge or face provenance",
            {"candidate_loop_id": candidate.loop_id},
        )
    signed_area = _signed_polygon_area(points_sq)
    if signed_area * candidate.material_side <= 0.0:
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "cross-station reversal conflicts with the source material-side orientation",
            {
                "candidate_loop_id": candidate.loop_id,
                "reference_loop_id": reference.loop_id,
                "reversed": reversed_order,
                "signed_area_sq_mm2": signed_area,
                "material_side": candidate.material_side,
            },
        )
    actual_resampled = _resample_closed_polyline(
        points_sq, sample_count, include_closure=False
    )
    target_resampled = corrected_resampled_sq[:-1]
    residual = float(np.max(np.linalg.norm(actual_resampled - target_resampled, axis=1)))
    if residual > alignment_tolerance:
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "edge-preserving alignment does not reproduce the measured pointwise shift",
            {
                "candidate_loop_id": candidate.loop_id,
                "alignment_residual_mm": residual,
                "alignment_tolerance_mm": alignment_tolerance,
            },
        )
    tangent_flips = detect_tangent_flips(points_sq)
    if tangent_flips:
        raise SectionRecoveryError(
            "v116_section_orientation_alignment_conflict",
            "aligned source loop contains a tangent flip",
            {"sample_indices": list(tangent_flips)},
        )
    return replace(
        candidate,
        edges=tuple(edges),
        points_xyz_mm=_tuple_points(points_xyz, 3),
        points_sq_mm=_tuple_points(points_sq, 2),
        orientation=(
            "counterclockwise" if candidate.material_side > 0 else "clockwise"
        ),
        source_face_ids=source_face_ids,
        source_edge_ids=tuple(edge.edge_id for edge in edges),
        orientation_evidence={
            **dict(candidate.orientation_evidence),
            "cross_station_alignment_applied": True,
            "reference_loop_id": reference.loop_id,
            "reversed": reversed_order,
            "circular_shift": circular_shift,
            "edge_circular_shift": start_edge_index,
            "forward_score": _round(forward_score),
            "reverse_score": _round(reverse_score),
            "tangent_mismatch_deg": _round(tangent_mismatch_deg),
            "alignment_residual_mm": _round(residual),
            "source_edge_provenance_preserved": True,
            "material_side_preserved": True,
        },
    )


def _canonicalize_section_loop(loop: SectionLoop) -> SectionLoop:
    edges = list(loop.edges)
    reverse = _signed_polygon_area(np.asarray(loop.points_sq_mm, dtype=float)) * loop.material_side < 0.0
    if reverse:
        edges = [
            replace(
                edge,
                points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
                points_sq_mm=tuple(reversed(edge.points_sq_mm)),
                source_face_parameter_uv=tuple(
                    reversed(edge.source_face_parameter_uv)
                ),
                topology_start_vertex_id=edge.topology_end_vertex_id,
                topology_end_vertex_id=edge.topology_start_vertex_id,
            )
            for edge in reversed(edges)
        ]
    if not edges or any(not edge.points_sq_mm for edge in edges):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "production loop edges lack local coordinates required for orientation normalization",
            {"loop_id": loop.loop_id},
        )
    start_edge_index = min(
        range(len(edges)), key=lambda index: _point_sort_key(edges[index].points_sq_mm[0])
    )
    edges = edges[start_edge_index:] + edges[:start_edge_index]
    points_xyz = _concatenate_edge_points(edges)
    points_sq = _concatenate_edge_local_points(edges)
    tangent_flips = detect_tangent_flips(points_sq)
    if tangent_flips:
        raise SectionRecoveryError(
            "v116_section_tangent_flip_detected",
            "canonical production loop contains a local 180-degree tangent flip",
            {"sample_indices": list(tangent_flips), "loop_id": loop.loop_id},
        )
    return replace(
        loop,
        edges=tuple(edges),
        points_xyz_mm=_tuple_points(points_xyz, 3),
        points_sq_mm=_tuple_points(points_sq, 2),
        orientation="counterclockwise" if loop.material_side > 0 else "clockwise",
        source_edge_ids=tuple(edge.edge_id for edge in edges),
        orientation_evidence={
            **dict(loop.orientation_evidence),
            "canonical_edge_order_applied": True,
            "canonical_reversed": reverse,
        },
    )


def decompose_section_loop(
    loop: SectionLoop,
    *,
    landmark_indices: Mapping[str, int] | None = None,
    maximum_control_count: int = 8,
) -> LoopDecomposition:
    role_segments = _segments_from_source_roles(loop)
    if role_segments is not None:
        raw_segments = role_segments
        method = "source_face_adjacency"
    else:
        partial_role_segments = _segments_from_authenticated_side_roles(loop)
        if partial_role_segments is not None:
            raw_segments = partial_role_segments
            method = "partial_source_face_adjacency"
        elif _is_two_authenticated_side_curve_loop(loop):
            raw_segments = _segments_from_landmarks_or_geometry(
                loop, landmark_indices
            )
            method = "two_authenticated_side_curves_streamwise_landmarks"
        else:
            authenticated_side_roles = sorted(
                {
                    role
                    for edge in loop.edges
                    for role in edge.source_roles
                    if role in {"side_a", "side_b"}
                }
            )
            if authenticated_side_roles:
                raise SectionRecoveryError(
                    "v116_section_loop_correspondence_failed",
                    "authenticated side provenance does not form one complete side_a/side_b partition",
                    {
                        "authenticated_side_roles": authenticated_side_roles,
                        "source_edge_roles": {
                            edge.edge_id: list(edge.source_roles)
                            for edge in loop.edges
                        },
                    },
                )
            raw_segments = _segments_from_landmarks_or_geometry(loop, landmark_indices)
            method = "explicit_landmarks" if landmark_indices is not None else "streamwise_extrema_tangent_continuity"

    measurements: list[SectionSegmentMeasurement] = []
    for name in _SEGMENT_ROLES:
        record = raw_segments[name]
        fit = fit_nurbs_measurement_curve(
            record["points_xyz_mm"],
            record["points_sq_mm"],
            segment_name=name,
            source_edge_ids=record["source_edge_ids"],
            maximum_control_count=maximum_control_count,
            fit_tolerance_mm=loop.source_tolerance_mm,
            allow_source_polyline_nurbs=(
                loop.source_wire_exact
                and loop.source_kind
                in {
                    "occt_exact_full_source_section",
                    "occt_exact_authenticated_face_compound_section",
                }
            ),
        )
        measurements.append(
            SectionSegmentMeasurement(
                name=name,
                points_xyz_mm=_tuple_points(record["points_xyz_mm"], 3),
                points_sq_mm=_tuple_points(record["points_sq_mm"], 2),
                source_edge_ids=tuple(record["source_edge_ids"]),
                source_face_ids=tuple(record["source_face_ids"]),
                fit=fit,
            )
        )
    side_a = next(item for item in measurements if item.name == "side_a")
    side_b = next(item for item in measurements if item.name == "side_b")
    landmarks = {
        "leading_side_a": side_a.points_sq_mm[0],
        "trailing_side_a": side_a.points_sq_mm[-1],
        "leading_side_b": side_b.points_sq_mm[0],
        "trailing_side_b": side_b.points_sq_mm[-1],
    }
    return LoopDecomposition(
        loop_id=loop.loop_id,
        segments=tuple(measurements),
        landmark_method=method,
        landmarks_sq_mm=landmarks,
    )


def decompose_authenticated_open_side_pair(
    loop: SectionLoop,
    *,
    maximum_control_count: int = 49,
) -> LoopDecomposition:
    """Fit exact PS/SS curves and explicit review-only endpoint bridges."""

    if loop.source_kind != "occt_exact_authenticated_open_side_pair":
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "open-side decomposition requires authenticated side-pair authority",
        )
    by_role = {
        role: tuple(
            edge
            for edge in loop.edges
            if edge.source_roles == (role,)
        )
        for role in ("side_a", "side_b")
    }
    if any(not edges for edges in by_role.values()):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "open-side decomposition lacks one connected exact chain for each blade side",
        )
    records: dict[str, dict[str, Any]] = {}
    for role in ("side_a", "side_b"):
        edges = by_role[role]
        parameter_face_ids = {edge.source_parameter_face_id for edge in edges}
        uv_available = [bool(edge.source_face_parameter_uv) for edge in edges]
        if any(uv_available) and (
            not all(uv_available)
            or len(parameter_face_ids) != 1
            or None in parameter_face_ids
        ):
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed",
                f"{role} does not retain one source-face parameter authority",
                {
                    "role": role,
                    "source_parameter_face_ids": sorted(
                        str(value) for value in parameter_face_ids
                    ),
                },
            )
        has_parameter_authority = all(uv_available)
        surface_authorities = [
            edge.source_surface_parameter_authority for edge in edges
        ]
        if any(authority is not None for authority in surface_authorities) and not all(
            authority is not None for authority in surface_authorities
        ):
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed",
                f"{role} source-surface authority is incomplete across its edge chain",
                {"role": role},
            )
        records[role] = {
            "points_xyz_mm": _concatenate_edge_points(edges),
            "points_sq_mm": _concatenate_edge_local_points(edges),
            "source_face_parameter_uv": (
                _concatenate_edge_parameter_uv(edges)
                if has_parameter_authority
                else ()
            ),
            "source_parameter_face_id": (
                next(iter(parameter_face_ids)) if has_parameter_authority else None
            ),
            "source_face_parameter_residual_max_mm": max(
                edge.source_face_parameter_residual_max_mm for edge in edges
            ),
            "source_surface_parameter_authority": surface_authorities[0],
            "source_edge_ids": tuple(edge.edge_id for edge in edges),
            "source_face_ids": tuple(
                sorted(
                    {
                        face_id
                        for edge in edges
                        for face_id in edge.source_face_ids
                    }
                )
            ),
        }
    side_a_xyz = np.asarray(records["side_a"]["points_xyz_mm"], dtype=float)
    side_b_xyz = np.asarray(records["side_b"]["points_xyz_mm"], dtype=float)
    side_a_sq = np.asarray(records["side_a"]["points_sq_mm"], dtype=float)
    side_b_sq = np.asarray(records["side_b"]["points_sq_mm"], dtype=float)
    bridge_faces = tuple(sorted(set(loop.source_face_ids)))
    records["leading_edge"] = {
        "points_xyz_mm": np.vstack([side_b_xyz[0], side_a_xyz[0]]),
        "points_sq_mm": np.vstack([side_b_sq[0], side_a_sq[0]]),
        "source_edge_ids": ("review_bridge_leading_endpoint_witnesses",),
        "source_face_ids": bridge_faces,
        "source_face_parameter_uv": (),
        "source_parameter_face_id": None,
        "source_face_parameter_residual_max_mm": 0.0,
        "source_surface_parameter_authority": None,
    }
    records["trailing_edge"] = {
        "points_xyz_mm": np.vstack([side_a_xyz[-1], side_b_xyz[-1]]),
        "points_sq_mm": np.vstack([side_a_sq[-1], side_b_sq[-1]]),
        "source_edge_ids": ("review_bridge_trailing_endpoint_witnesses",),
        "source_face_ids": bridge_faces,
        "source_face_parameter_uv": (),
        "source_parameter_face_id": None,
        "source_face_parameter_residual_max_mm": 0.0,
        "source_surface_parameter_authority": None,
    }
    measurements = []
    for name in _SEGMENT_ROLES:
        record = records[name]
        fit = fit_nurbs_measurement_curve(
            record["points_xyz_mm"],
            record["points_sq_mm"],
            segment_name=name,
            source_edge_ids=record["source_edge_ids"],
            maximum_control_count=maximum_control_count,
            fit_tolerance_mm=loop.source_tolerance_mm,
            allow_source_polyline_nurbs=(
                name in {"side_a", "side_b"}
                and isinstance(record["source_surface_parameter_authority"], Mapping)
                and bool(
                    record["source_surface_parameter_authority"].get(
                        "trim_boundary_uv_paths"
                    )
                )
            ),
        )
        measurements.append(
            SectionSegmentMeasurement(
                name=name,
                points_xyz_mm=_tuple_points(record["points_xyz_mm"], 3),
                points_sq_mm=_tuple_points(record["points_sq_mm"], 2),
                source_edge_ids=tuple(record["source_edge_ids"]),
                source_face_ids=tuple(record["source_face_ids"]),
                fit=fit,
                source_parameter_face_id=record["source_parameter_face_id"],
                source_face_parameter_uv=(
                    ()
                    if not len(record["source_face_parameter_uv"])
                    else _tuple_points(record["source_face_parameter_uv"], 2)
                ),
                source_face_parameter_residual_max_mm=float(
                    record["source_face_parameter_residual_max_mm"]
                ),
                source_surface_parameter_authority=record[
                    "source_surface_parameter_authority"
                ],
            )
        )
    return LoopDecomposition(
        loop_id=loop.loop_id,
        segments=tuple(measurements),
        landmark_method="authenticated_open_side_pair_endpoint_witness_bridges",
        landmarks_sq_mm={
            "leading_side_a": tuple(float(value) for value in side_a_sq[0]),
            "trailing_side_a": tuple(float(value) for value in side_a_sq[-1]),
            "leading_side_b": tuple(float(value) for value in side_b_sq[0]),
            "trailing_side_b": tuple(float(value) for value in side_b_sq[-1]),
        },
        pressure_suction_assigned=False,
        direct_curve_constructor_mode=True,
    )


def _is_two_authenticated_side_curve_loop(loop: SectionLoop) -> bool:
    return bool(
        len(loop.edges) == 2
        and sorted(edge.source_roles for edge in loop.edges)
        == [("side_a",), ("side_b",)]
    )


def fit_nurbs_measurement_curve(
    points_xyz_mm: Sequence[Sequence[float]],
    points_sq_mm: Sequence[Sequence[float]],
    *,
    segment_name: str,
    source_edge_ids: Sequence[str] = (),
    maximum_control_count: int = 8,
    fit_tolerance_mm: float | None = None,
    allow_source_polyline_nurbs: bool = False,
) -> NurbsCurveFit:
    xyz = np.asarray(points_xyz_mm, dtype=float)
    sq = np.asarray(points_sq_mm, dtype=float)
    _validate_points(xyz, 3, "points_xyz_mm", minimum=2)
    _validate_points(sq, 2, "points_sq_mm", minimum=2)
    if len(xyz) != len(sq):
        raise ValueError("3D and local segment samples must have matching lengths")
    maximum = max(2, int(maximum_control_count))
    tolerance = (
        None
        if fit_tolerance_mm is None
        else _positive(fit_tolerance_mm, "fit_tolerance_mm")
    )
    parameters = _chord_parameters(sq)

    def candidate(
        *, degree: int, interpolate_polyline: bool, knot_strategy: str
    ) -> NurbsCurveFit:
        if interpolate_polyline:
            control_count = len(sq)
            knots = np.concatenate(
                [np.asarray([0.0, 0.0]), parameters[1:-1], np.asarray([1.0, 1.0])]
            )
            controls_sq = sq.copy()
            controls_xyz = xyz.copy()
        else:
            control_count = min(maximum, len(sq))
            control_count = max(degree + 1, control_count)
            knots = (
                _averaged_approximation_knots(
                    parameters, control_count=control_count, degree=degree
                )
                if knot_strategy == "chord_parameter_averaged_knots"
                else _clamped_uniform_knots(control_count, degree)
            )
            basis = _basis_matrix(parameters, control_count, degree, knots)
            controls_sq = _fit_endpoint_constrained_controls(basis, sq)
            controls_xyz = _fit_endpoint_constrained_controls(basis, xyz)
        dense_count = min(1025, max(257, 8 * len(sq)))
        dense_parameters = np.linspace(0.0, 1.0, dense_count)
        dense_basis = _basis_matrix(
            dense_parameters, control_count, degree, knots
        )
        dense_sq = dense_basis @ controls_sq
        dense_xyz = dense_basis @ controls_xyz
        source_to_fit_sq = _points_to_polyline_distances(sq, dense_sq)
        fit_to_source_sq = _points_to_polyline_distances(dense_sq, sq)
        source_to_fit_xyz = _points_to_polyline_distances(xyz, dense_xyz)
        fit_to_source_xyz = _points_to_polyline_distances(dense_xyz, xyz)
        parameter_matched_sq = np.linalg.norm(
            dense_sq
            - _evaluate_polyline_at_parameters(sq, parameters, dense_parameters),
            axis=1,
        )
        if interpolate_polyline:
            # The degree-one candidate is exactly the source polyline.  A
            # finite display sampling must not turn omitted source vertices
            # into a false source-to-fit residual.
            source_to_fit_sq = np.zeros(len(sq), dtype=float)
            source_to_fit_xyz = np.zeros(len(xyz), dtype=float)
        residuals = np.concatenate(
            [
                source_to_fit_sq,
                fit_to_source_sq,
                source_to_fit_xyz,
                fit_to_source_xyz,
                parameter_matched_sq,
            ]
        )
        dense_tangent = np.gradient(dense_sq, dense_parameters, axis=0)
        start_tangent = _unit(dense_tangent[0], "start_tangent_sq")
        end_tangent = _unit(dense_tangent[-1], "end_tangent_sq")
        curvature = _sample_curvature(dense_sq, dense_parameters)
        return NurbsCurveFit(
            segment_name=str(segment_name),
            degree=degree,
            knots=tuple(_round(value) for value in knots),
            control_points_xyz_mm=_tuple_points(controls_xyz, 3),
            control_points_sq_mm=_tuple_points(controls_sq, 2),
            source_edge_ids=tuple(
                sorted(str(value) for value in source_edge_ids)
            ),
            residual_rms_mm=_round(math.sqrt(float(np.mean(residuals**2)))),
            residual_p95_mm=_round(float(np.percentile(residuals, 95))),
            residual_max_mm=_round(float(np.max(residuals))),
            residual_source_to_fit_max_sq_mm=_round(
                float(np.max(source_to_fit_sq))
            ),
            residual_fit_to_source_max_sq_mm=_round(
                float(np.max(fit_to_source_sq))
            ),
            residual_source_to_fit_max_xyz_mm=_round(
                float(np.max(source_to_fit_xyz))
            ),
            residual_fit_to_source_max_xyz_mm=_round(
                float(np.max(fit_to_source_xyz))
            ),
            residual_parameter_matched_max_sq_mm=_round(
                float(np.max(parameter_matched_sq))
            ),
            edge_sag_sq_mm=_round(_polyline_sag(sq)),
            edge_sag_xyz_mm=_round(_polyline_sag(xyz)),
            source_sample_count=len(sq),
            fit_sample_count=dense_count,
            start_tangent_sq=(float(start_tangent[0]), float(start_tangent[1])),
            end_tangent_sq=(float(end_tangent[0]), float(end_tangent[1])),
            start_curvature_per_mm=_round(float(curvature[0])),
            end_curvature_per_mm=_round(float(curvature[-1])),
            knot_strategy=knot_strategy,
        )

    degree = min(3, len(sq) - 1)
    uniform = candidate(
        degree=degree,
        interpolate_polyline=False,
        knot_strategy="clamped_uniform_knots",
    )
    primary_candidates = [uniform]
    control_count = min(maximum, len(sq))
    if (
        degree + 1 < control_count < len(sq)
        and np.all(np.diff(parameters) > 1.0e-12)
    ):
        primary_candidates.append(
            candidate(
                degree=degree,
                interpolate_polyline=False,
                knot_strategy="chord_parameter_averaged_knots",
            )
        )
    primary = min(
        primary_candidates,
        key=lambda fit: (fit.residual_max_mm, fit.residual_rms_mm),
    )
    if (
        tolerance is None
        or primary.residual_max_mm <= tolerance
        or not allow_source_polyline_nurbs
    ):
        return primary
    linear = candidate(
        degree=1,
        interpolate_polyline=True,
        knot_strategy="source_polyline_degree_one",
    )
    return min(
        (primary, linear),
        key=lambda fit: (fit.residual_max_mm, fit.residual_rms_mm, -fit.degree),
    )


def _averaged_approximation_knots(
    parameters: Sequence[float], *, control_count: int, degree: int
) -> np.ndarray:
    values = np.asarray(parameters, dtype=float)
    if (
        values.ndim != 1
        or len(values) < control_count
        or np.any(np.diff(values) <= 0.0)
        or not math.isclose(values[0], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(values[-1], 1.0, rel_tol=0.0, abs_tol=1.0e-12)
    ):
        raise ValueError("parameters must be strictly increasing from zero to one")
    if control_count < degree + 1:
        raise ValueError("control_count must be at least degree + 1")
    values = values.copy()
    values[0] = 0.0
    values[-1] = 1.0
    interior_count = control_count - degree - 1
    knots = np.concatenate(
        [np.zeros(degree + 1), np.empty(interior_count), np.ones(degree + 1)]
    )
    if not interior_count:
        return knots
    step = len(values) / (control_count - degree)
    for offset in range(1, interior_count + 1):
        location = offset * step
        index = min(max(1, int(math.floor(location))), len(values) - 1)
        alpha = location - math.floor(location)
        knots[degree + offset] = (
            (1.0 - alpha) * values[index - 1] + alpha * values[index]
        )
    return knots


def _evaluate_polyline_at_parameters(
    points: np.ndarray, parameters: np.ndarray, query: np.ndarray
) -> np.ndarray:
    unique_parameters, indices = np.unique(parameters, return_index=True)
    unique_points = points[indices]
    if len(unique_parameters) < 2:
        return np.repeat(unique_points[:1], len(query), axis=0)
    return np.column_stack(
        [
            np.interp(query, unique_parameters, unique_points[:, coordinate])
            for coordinate in range(points.shape[1])
        ]
    )


def measure_camber_normal_thickness(
    loop: SectionLoop,
    decomposition: LoopDecomposition | None = None,
    *,
    sample_s: Sequence[float] | None = None,
    camber_iterations: int = 4,
) -> ThicknessField:
    decomposition = decomposition or decompose_section_loop(loop)
    side_a_segment = decomposition.segment("side_a")
    side_b_segment = decomposition.segment("side_b")
    side_a = _orient_side_le_to_te(np.asarray(side_a_segment.points_sq_mm, dtype=float))
    side_b = _orient_side_le_to_te(np.asarray(side_b_segment.points_sq_mm, dtype=float))
    requested_s = np.asarray(
        list(sample_s) if sample_s is not None else np.linspace(0.05, 0.95, 19), dtype=float
    )
    if requested_s.ndim != 1 or not len(requested_s) or not np.all(np.isfinite(requested_s)):
        raise ValueError("sample_s must contain finite values")
    if np.any(requested_s <= 0.0) or np.any(requested_s >= 1.0) or np.any(np.diff(requested_s) <= 0.0):
        raise ValueError("sample_s must be strictly increasing inside (0,1)")

    fit_s = np.unique(
        np.concatenate([np.asarray([0.0, 1.0]), np.linspace(0.02, 0.98, 65), requested_s])
    )
    lower_s = max(float(np.min(side_a[:, 0])), float(np.min(side_b[:, 0])))
    upper_s = min(float(np.max(side_a[:, 0])), float(np.max(side_b[:, 0])))
    if upper_s - lower_s <= _EPSILON:
        raise SectionRecoveryError(
            "v116_thickness_field_invalid", "blade sides have no common streamwise domain"
        )
    seed_points = []
    for fraction in fit_s:
        streamwise = lower_s + float(fraction) * (upper_s - lower_s)
        point_a = _polyline_point_at_streamwise(side_a, streamwise)
        point_b = _polyline_point_at_streamwise(side_b, streamwise)
        seed_points.append(0.5 * (point_a + point_b))
    camber_points = np.asarray(seed_points, dtype=float)

    camber_fit: NurbsCurveFit | None = None
    for _iteration in range(max(1, int(camber_iterations))):
        camber_xyz = np.column_stack([camber_points, np.zeros(len(camber_points))])
        camber_fit = fit_nurbs_measurement_curve(
            camber_xyz,
            camber_points,
            segment_name="camber",
            maximum_control_count=min(10, len(camber_points)),
        )
        updated = []
        for fraction in fit_s:
            point, normal = _camber_point_and_normal(camber_fit, float(fraction))
            hit_a, hit_b = _opposite_side_normal_hits(point, normal, side_a, side_b)
            updated.append(0.5 * (hit_a[0] + hit_b[0]))
        updated_points = np.asarray(updated, dtype=float)
        if float(np.max(np.linalg.norm(updated_points - camber_points, axis=1))) <= 1.0e-8:
            camber_points = updated_points
            break
        camber_points = updated_points
    camber_xyz = np.column_stack([camber_points, np.zeros(len(camber_points))])
    camber_fit = fit_nurbs_measurement_curve(
        camber_xyz,
        camber_points,
        segment_name="camber",
        maximum_control_count=min(10, len(camber_points)),
    )

    polygon = np.asarray(loop.points_sq_mm, dtype=float)
    samples: list[ThicknessSample] = []
    for fraction in requested_s:
        point, normal = _camber_point_and_normal(camber_fit, float(fraction))
        hit_a, hit_b = _opposite_side_normal_hits(point, normal, side_a, side_b)
        point_a, parameter_a, lambda_a = hit_a
        point_b, parameter_b, lambda_b = hit_b
        thickness = abs(lambda_a - lambda_b)
        inside = all(
            _point_in_polygon((1.0 - alpha) * point_a + alpha * point_b, polygon)
            for alpha in (0.25, 0.5, 0.75)
        )
        if not math.isfinite(thickness) or thickness <= _EPSILON or not inside:
            raise SectionRecoveryError(
                "v116_thickness_field_invalid",
                "camber-normal thickness must be positive and remain inside the source loop",
                {"s": float(fraction), "thickness_mm": float(thickness), "inside": inside},
            )
        samples.append(
            ThicknessSample(
                s=_round(float(fraction)),
                camber_sq_mm=(float(point[0]), float(point[1])),
                normal_sq=(float(normal[0]), float(normal[1])),
                side_a_sq_mm=(float(point_a[0]), float(point_a[1])),
                side_b_sq_mm=(float(point_b[0]), float(point_b[1])),
                side_a_parameter=_round(parameter_a),
                side_b_parameter=_round(parameter_b),
                thickness_mm=_round(thickness),
                inside_source_loop=True,
            )
        )
    parameters_a = np.asarray([sample.side_a_parameter for sample in samples], dtype=float)
    parameters_b = np.asarray([sample.side_b_parameter for sample in samples], dtype=float)
    if np.any(np.diff(parameters_a) < -1.0e-6) or np.any(np.diff(parameters_b) < -1.0e-6):
        raise SectionRecoveryError(
            "v116_thickness_field_invalid",
            "camber-normal side correspondence is not monotone",
            {
                "side_a_parameters": parameters_a.tolist(),
                "side_b_parameters": parameters_b.tolist(),
            },
        )
    return ThicknessField(loop_id=loop.loop_id, samples=tuple(samples), camber_fit=camber_fit)


def _verify_attachment_topology_evidence(
    *,
    source_shape: Any,
    source_edges_by_id: Mapping[str, Any],
    source_faces_by_id: Mapping[str, Any],
    source_face_ids: Sequence[str],
    footprint_source_edge_ids: Sequence[str],
    retained_source_edge_ids: Sequence[str],
    termination_source_edge_ids: Sequence[str],
    span_direction_source_ids: Sequence[str],
    footprint_boundary_xyz_mm: np.ndarray,
    retained_boundary_xyz_mm: np.ndarray,
    paired_footprint_points_xyz_mm: np.ndarray | None,
    termination_boundary_xyz_mm: Sequence[Sequence[float]] | None,
    tolerance_mm: float,
    asserted_adjacency: Mapping[str, Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.gp import gp_Pnt
    except ImportError as exc:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "OCCT topology is required for promotable attachment measurement",
        ) from exc

    source = _wrapped(source_shape)
    edge_map = {str(key): _wrapped(value) for key, value in source_edges_by_id.items()}
    face_map = {str(key): _wrapped(value) for key, value in source_faces_by_id.items()}

    def source_contains(candidate: Any, shape_type: Any) -> bool:
        explorer = TopExp_Explorer(source, shape_type)
        while explorer.More():
            if explorer.Current().IsSame(candidate):
                return True
            explorer.Next()
        return False

    if not span_direction_source_ids or any(
        source_id not in edge_map for source_id in span_direction_source_ids
    ):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "local span direction must be authenticated by source B-Rep edge tangents",
            {"span_direction_source_ids": list(span_direction_source_ids)},
        )
    requested_edges = tuple(
        dict.fromkeys(
            footprint_source_edge_ids
            + retained_source_edge_ids
            + termination_source_edge_ids
            + span_direction_source_ids
        )
    )
    if any(edge_id not in edge_map for edge_id in requested_edges):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "attachment provenance references an unknown source edge",
        )
    if any(not source_contains(edge_map[edge_id], TopAbs_EDGE) for edge_id in requested_edges):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "attachment provenance edge is not part of the source B-Rep",
        )
    if any(face_id not in face_map for face_id in source_face_ids) or any(
        not source_contains(face_map[face_id], TopAbs_FACE) for face_id in source_face_ids
    ):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "attachment provenance face is not part of the source B-Rep",
        )
    actual_adjacency: dict[str, tuple[str, ...]] = {}
    for edge_id in requested_edges:
        edge = edge_map[edge_id]
        adjacent: list[str] = []
        for face_id in source_face_ids:
            explorer = TopExp_Explorer(face_map[face_id], TopAbs_EDGE)
            while explorer.More():
                if explorer.Current().IsSame(edge):
                    adjacent.append(face_id)
                    break
                explorer.Next()
        actual_adjacency[edge_id] = tuple(sorted(adjacent))
        if len(adjacent) < 2:
            raise SectionRecoveryError(
                "v116_root_attachment_measurement_failed",
                "attachment boundary edge lacks two source-face ancestors",
                {"edge_id": edge_id, "adjacent_source_face_ids": adjacent},
            )
        if edge_id in asserted_adjacency and tuple(sorted(asserted_adjacency[edge_id])) != tuple(
            sorted(adjacent)
        ):
            raise SectionRecoveryError(
                "v116_root_attachment_measurement_failed",
                "asserted attachment adjacency disagrees with the source B-Rep",
                {"edge_id": edge_id},
            )

    def assert_points_on_edges(
        points: Sequence[Sequence[float]], edge_ids: Sequence[str], boundary: str
    ) -> None:
        distances = []
        for coordinates in np.asarray(points, dtype=float):
            vertex = BRepBuilderAPI_MakeVertex(
                gp_Pnt(*(float(value) for value in coordinates))
            ).Vertex()
            candidates = []
            for edge_id in edge_ids:
                operation = BRepExtrema_DistShapeShape(vertex, edge_map[edge_id])
                operation.Perform()
                if operation.IsDone():
                    candidates.append(float(operation.Value()))
            if not candidates:
                raise SectionRecoveryError(
                    "v116_root_attachment_measurement_failed",
                    f"{boundary} exact point-to-edge distance could not be evaluated",
                )
            distances.append(min(candidates))
        allowed_distance = max(10.0 * tolerance_mm, 1.0e-5)
        maximum = float(np.max(distances))
        if maximum > allowed_distance:
            raise SectionRecoveryError(
                "v116_root_attachment_measurement_failed",
                f"{boundary} samples are not on their claimed source edges",
                {"maximum_residual_mm": maximum},
            )

    assert_points_on_edges(
        footprint_boundary_xyz_mm, footprint_source_edge_ids, "footprint boundary"
    )
    assert_points_on_edges(
        retained_boundary_xyz_mm, retained_source_edge_ids, "retained blade boundary"
    )
    if paired_footprint_points_xyz_mm is not None:
        assert_points_on_edges(
            paired_footprint_points_xyz_mm,
            footprint_source_edge_ids,
            "paired footprint boundary",
        )
    if termination_boundary_xyz_mm is None:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "attachment termination boundary is missing",
        )
    termination = np.asarray(termination_boundary_xyz_mm, dtype=float)
    _validate_points(termination, 3, "termination_boundary_xyz_mm", minimum=2)
    assert_points_on_edges(termination, termination_source_edge_ids, "termination boundary")
    return actual_adjacency


def _measure_occt_span_directions(
    *,
    retained_points_xyz_mm: np.ndarray,
    expected_directions_xyz: np.ndarray,
    source_edges_by_id: Mapping[str, Any],
    span_direction_source_ids: Sequence[str],
    angular_tolerance_deg: float,
    validate_expected_directions: bool,
    source_distance_tolerance_mm: float,
) -> tuple[np.ndarray, tuple[Mapping[str, Any], ...], float]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.TopoDS import TopoDS
    except ImportError as exc:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "OCCT edge geometry is required for local span-direction measurement",
        ) from exc

    sampled_edges: list[tuple[str, np.ndarray, np.ndarray, np.ndarray]] = []
    for source_id in span_direction_source_ids:
        adaptor = BRepAdaptor_Curve(TopoDS.Edge_s(_wrapped(source_edges_by_id[source_id])))
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        parameters = np.linspace(first, last, 129)
        points = np.asarray(
            [
                [
                    float(adaptor.Value(float(parameter)).X()),
                    float(adaptor.Value(float(parameter)).Y()),
                    float(adaptor.Value(float(parameter)).Z()),
                ]
                for parameter in parameters
            ],
            dtype=float,
        )
        sampled_edges.append((str(source_id), parameters, points, np.asarray([first, last])))

    measured: list[np.ndarray] = []
    records: list[Mapping[str, Any]] = []
    residuals: list[float] = []
    for point, expected in zip(retained_points_xyz_mm, expected_directions_xyz):
        expected_unit = _unit(expected, "expected_local_span_direction_xyz")
        candidates: list[tuple[float, str, float, np.ndarray, np.ndarray]] = []
        for source_id, parameters, samples, bounds in sampled_edges:
            sample_index = int(np.argmin(np.linalg.norm(samples - point, axis=1)))
            parameter = float(parameters[sample_index])
            step = max(abs(float(bounds[1] - bounds[0])) * 1.0e-5, 1.0e-9)
            low = max(float(bounds[0]), parameter - step)
            high = min(float(bounds[1]), parameter + step)
            adaptor = BRepAdaptor_Curve(
                TopoDS.Edge_s(_wrapped(source_edges_by_id[source_id]))
            )
            low_point = adaptor.Value(low)
            high_point = adaptor.Value(high)
            tangent = _unit(
                np.asarray(
                    [
                        float(high_point.X() - low_point.X()),
                        float(high_point.Y() - low_point.Y()),
                        float(high_point.Z() - low_point.Z()),
                    ]
                ),
                "source_span_edge_tangent",
            )
            if float(np.dot(tangent, expected_unit)) < 0.0:
                tangent = -tangent
            sample = samples[sample_index]
            distance = float(np.linalg.norm(sample - point))
            candidates.append((distance, source_id, parameter, sample, tangent))
        distance, source_id, parameter, sample, tangent = min(
            candidates, key=lambda item: (item[0], item[1], item[2])
        )
        cosine = float(np.clip(np.dot(tangent, expected_unit), -1.0, 1.0))
        measured_angle = math.degrees(math.acos(cosine))
        residual = measured_angle if validate_expected_directions else 0.0
        if distance > source_distance_tolerance_mm:
            raise SectionRecoveryError(
                "v116_root_attachment_measurement_failed",
                "retained attachment sample is not on its authenticated span-direction edge",
                {
                    "source_entity_id": source_id,
                    "source_distance_mm": distance,
                    "source_distance_tolerance_mm": source_distance_tolerance_mm,
                },
            )
        measured.append(tangent)
        residuals.append(residual)
        records.append(
            {
                "source_entity_id": source_id,
                "source_geometry": "occt_edge_tangent",
                "sample_xyz_mm": [_round(value) for value in sample],
                "retained_sample_xyz_mm": [_round(value) for value in point],
                "source_parameter": _round(parameter),
                "source_distance_mm": _round(distance),
                "measured_direction_xyz": [_round(value) for value in tangent],
                "expected_direction_xyz": [_round(value) for value in expected_unit],
                "angular_residual_deg": _round(residual),
                "orientation_hint_angle_deg": _round(measured_angle),
                "angular_tolerance_deg": _round(angular_tolerance_deg),
                "comparison": (
                    "caller_direction_validation"
                    if validate_expected_directions
                    else "source_geometry_authoritative_no_caller_override"
                ),
            }
        )
    maximum = max(residuals, default=math.inf)
    if not math.isfinite(maximum) or maximum > angular_tolerance_deg:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "caller local span direction disagrees with authenticated OCCT edge tangents",
            {
                "angular_residual_max_deg": maximum,
                "angular_tolerance_deg": angular_tolerance_deg,
                "span_direction_evidence": list(records),
            },
        )
    return np.asarray(measured), tuple(records), maximum


def measure_attachment(
    footprint_boundary_xyz_mm: Sequence[Sequence[float]],
    retained_blade_boundary_xyz_mm: Sequence[Sequence[float]],
    *,
    local_span_direction_xyz: Sequence[float] | None = None,
    local_span_directions_xyz: Sequence[Sequence[float]] | None = None,
    paired_footprint_points_xyz_mm: Sequence[Sequence[float]] | None = None,
    support_normal_directions_xyz: Sequence[Sequence[float]] | None = None,
    streamwise_parameters_s: Sequence[float] | None = None,
    material_side: int = 1,
    attachment_kind: str = "root",
    width_direction_xyz: Sequence[float] | None = None,
    source_face_ids: Sequence[str] = (),
    footprint_source_edge_ids: Sequence[str] = (),
    retained_source_edge_ids: Sequence[str] = (),
    span_direction_source_ids: Sequence[str] = (),
    termination_boundary_xyz_mm: Sequence[Sequence[float]] | None = None,
    termination_source_edge_ids: Sequence[str] = (),
    source_adjacency: Mapping[str, Sequence[str]] | None = None,
    source_shape: Any | None = None,
    source_edges_by_id: Mapping[str, Any] | None = None,
    source_faces_by_id: Mapping[str, Any] | None = None,
    provenance_kind: str | None = None,
    allow_synthetic: bool = False,
    tolerance_mm: float = 1.0e-6,
    span_direction_angular_tolerance_deg: float = 5.0,
    span_direction_method: str = "source_edge_tangent",
) -> AttachmentMeasurement:
    footprint = np.asarray(footprint_boundary_xyz_mm, dtype=float)
    retained = np.asarray(retained_blade_boundary_xyz_mm, dtype=float)
    paired_footprint = (
        None
        if paired_footprint_points_xyz_mm is None
        else np.asarray(paired_footprint_points_xyz_mm, dtype=float)
    )
    support_normals = (
        None
        if support_normal_directions_xyz is None
        else np.asarray(support_normal_directions_xyz, dtype=float)
    )
    streamwise_parameters = (
        None
        if streamwise_parameters_s is None
        else np.asarray(streamwise_parameters_s, dtype=float)
    )
    _validate_points(footprint, 3, "footprint_boundary_xyz_mm", minimum=3)
    _validate_points(retained, 3, "retained_blade_boundary_xyz_mm", minimum=3)
    if paired_footprint is not None:
        _validate_points(
            paired_footprint,
            3,
            "paired_footprint_points_xyz_mm",
            minimum=3,
        )
        if paired_footprint.shape != retained.shape:
            raise ValueError(
                "paired_footprint_points_xyz_mm must match retained boundary samples"
            )
    if support_normals is not None:
        if paired_footprint is None:
            raise ValueError(
                "support_normal_directions_xyz requires paired footprint points"
            )
        if support_normals.shape != retained.shape:
            raise ValueError(
                "support_normal_directions_xyz must match retained boundary samples"
            )
        support_normals = np.asarray(
            [_unit(value, "support_normal_directions_xyz") for value in support_normals]
        )
    if streamwise_parameters is not None:
        if streamwise_parameters.shape != (len(retained),):
            raise ValueError(
                "streamwise_parameters_s must match retained boundary samples"
            )
        if (
            not np.all(np.isfinite(streamwise_parameters))
            or np.any(streamwise_parameters < 0.0)
            or np.any(streamwise_parameters > 1.0)
        ):
            raise ValueError("streamwise_parameters_s must be finite in [0, 1]")
    if material_side not in (-1, 1):
        raise ValueError("material_side must be -1 or 1")
    tolerance = _positive(tolerance_mm, "tolerance_mm")
    angular_tolerance = _positive(
        span_direction_angular_tolerance_deg,
        "span_direction_angular_tolerance_deg",
    )
    if span_direction_method not in {
        "source_edge_tangent",
        "authenticated_boundary_normal",
    }:
        raise ValueError("unsupported span_direction_method")
    if angular_tolerance > 90.0:
        raise ValueError("span_direction_angular_tolerance_deg must not exceed 90")
    face_ids = tuple(sorted({str(value) for value in source_face_ids if str(value)}))
    footprint_edge_ids = tuple(
        sorted({str(value) for value in footprint_source_edge_ids if str(value)})
    )
    retained_edge_ids = tuple(
        sorted({str(value) for value in retained_source_edge_ids if str(value)})
    )
    span_source_ids = tuple(
        sorted({str(value) for value in span_direction_source_ids if str(value)})
    )
    termination_edge_ids = tuple(
        sorted({str(value) for value in termination_source_edge_ids if str(value)})
    )
    footprint_set = set(footprint_edge_ids)
    retained_set = set(retained_edge_ids)
    termination_set = set(termination_edge_ids)
    span_set = set(span_source_ids)
    if footprint_set.intersection(retained_set):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "footprint and retained attachment boundaries must be disjoint",
        )
    forbidden_termination_overlap = footprint_set | retained_set | span_set
    termination_overlap = termination_set.intersection(
        forbidden_termination_overlap
    )
    if termination_overlap:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            "termination connectors overlap forbidden attachment boundary evidence",
            {"overlapping_source_edge_ids": sorted(termination_overlap)},
        )
    adjacency = {
        str(key): tuple(sorted({str(value) for value in values if str(value)}))
        for key, values in (source_adjacency or {}).items()
    }
    required_edges = footprint_edge_ids + retained_edge_ids + termination_edge_ids
    topology_verified = False
    if source_shape is not None and source_edges_by_id and source_faces_by_id and required_edges:
        adjacency = _verify_attachment_topology_evidence(
            source_shape=source_shape,
            source_edges_by_id=source_edges_by_id,
            source_faces_by_id=source_faces_by_id,
            source_face_ids=face_ids,
            footprint_source_edge_ids=footprint_edge_ids,
            retained_source_edge_ids=retained_edge_ids,
            termination_source_edge_ids=termination_edge_ids,
            span_direction_source_ids=span_source_ids,
            footprint_boundary_xyz_mm=footprint,
            retained_boundary_xyz_mm=retained,
            paired_footprint_points_xyz_mm=paired_footprint,
            termination_boundary_xyz_mm=termination_boundary_xyz_mm,
            tolerance_mm=tolerance,
            asserted_adjacency=adjacency,
        )
        topology_verified = True
    topology_evidence = (
        provenance_kind == "occt_source_adjacency"
        and topology_verified
        and bool(face_ids)
        and bool(footprint_edge_ids)
        and bool(retained_edge_ids)
        and bool(span_source_ids)
        and bool(termination_edge_ids)
        and termination_boundary_xyz_mm is not None
        and (
            span_direction_method != "authenticated_boundary_normal"
            or paired_footprint is not None
        )
        and all(
            edge_id in adjacency
            and len(adjacency[edge_id]) >= 2
            and set(adjacency[edge_id]).issubset(face_ids)
            for edge_id in required_edges
        )
    )
    if not topology_evidence and not allow_synthetic:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            f"{attachment_kind} attachment lacks OCCT adjacency provenance",
            {
                "source_face_ids": list(face_ids),
                "footprint_source_edge_ids": list(footprint_edge_ids),
                "retained_source_edge_ids": list(retained_edge_ids),
                "span_direction_source_ids": list(span_source_ids),
                "termination_source_edge_ids": list(termination_edge_ids),
                "provenance_kind": provenance_kind,
                "topology_verified": topology_verified,
            },
        )
    if (
        topology_evidence
        and span_direction_method == "authenticated_boundary_normal"
        and paired_footprint is not None
    ):
        expected_spans = np.asarray(
            [
                _unit(
                    point - source_point,
                    "authenticated_boundary_normal",
                )
                for point, source_point in zip(retained, paired_footprint)
            ]
        )
        if local_span_directions_xyz is not None:
            asserted = np.asarray(local_span_directions_xyz, dtype=float)
            if asserted.shape != retained.shape:
                raise ValueError(
                    "local_span_directions_xyz must match retained boundary samples"
                )
            asserted = np.asarray(
                [_unit(value, "local_span_directions_xyz") for value in asserted]
            )
            if np.any(np.sum(asserted * expected_spans, axis=1) < 1.0 - 1.0e-8):
                raise SectionRecoveryError(
                    "v116_root_attachment_measurement_failed",
                    "caller boundary directions disagree with exact source point pairs",
                )
    elif local_span_directions_xyz is not None:
        span_directions = np.asarray(local_span_directions_xyz, dtype=float)
        if span_directions.shape != retained.shape:
            raise ValueError("local_span_directions_xyz must match retained boundary samples")
        expected_spans = np.asarray(
            [float(material_side) * _unit(value, "local_span_directions_xyz") for value in span_directions]
        )
    elif local_span_direction_xyz is not None and allow_synthetic:
        base_span = float(material_side) * _unit(
            local_span_direction_xyz, "local_span_direction_xyz"
        )
        expected_spans = np.repeat(base_span[None, :], len(retained), axis=0)
    elif topology_evidence:
        footprint_closed = (
            footprint
            if np.linalg.norm(footprint[0] - footprint[-1]) <= 1.0e-10
            else np.vstack([footprint, footprint[0]])
        )
        expected_spans = np.asarray(
            [
                _unit(
                    point - _nearest_point_on_polyline(point, footprint_closed),
                    "source_attachment_span_direction",
                )
                for point in retained
            ]
        )
    else:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            f"{attachment_kind} attachment requires measured local span directions",
        )
    span_direction_evidence: tuple[Mapping[str, Any], ...] = ()
    angular_residual_max = 0.0
    if topology_evidence and span_direction_method == "source_edge_tangent":
        assert source_edges_by_id is not None
        spans, span_direction_evidence, angular_residual_max = _measure_occt_span_directions(
            retained_points_xyz_mm=retained,
            expected_directions_xyz=expected_spans,
            source_edges_by_id=source_edges_by_id,
            span_direction_source_ids=span_source_ids,
            angular_tolerance_deg=angular_tolerance,
            validate_expected_directions=local_span_directions_xyz is not None,
            source_distance_tolerance_mm=max(10.0 * tolerance, 1.0e-5),
        )
    elif topology_evidence:
        spans = expected_spans
        span_direction_evidence = tuple(
            {
                "source_entity_ids": list(
                    dict.fromkeys((*footprint_edge_ids, *retained_edge_ids))
                ),
                "source_geometry": "paired_authenticated_boundary_points",
                "footprint_sample_xyz_mm": [
                    _round(value) for value in source_point
                ],
                "retained_sample_xyz_mm": [_round(value) for value in point],
                "measured_direction_xyz": [_round(value) for value in direction],
                "angular_residual_deg": 0.0,
                "angular_tolerance_deg": _round(angular_tolerance),
                "comparison": "exact_boundary_pair_direction",
            }
            for point, source_point, direction in zip(
                retained,
                paired_footprint
                if paired_footprint is not None
                else np.repeat(footprint[:1], len(retained), axis=0),
                spans,
            )
        )
        angular_residual_max = 0.0
    else:
        spans = expected_spans
    promotable_evidence = topology_evidence and bool(span_direction_evidence)
    mean_span = _unit(np.mean(spans, axis=0), "mean_local_span_direction_xyz")
    lift_samples = []
    local_width_samples = []
    for index, (point_xyz, span) in enumerate(zip(retained, spans)):
        if paired_footprint is not None:
            source_point = paired_footprint[index]
        else:
            plane_u, plane_v = _plane_basis(span, width_direction_xyz)
            footprint_uv = np.column_stack(
                [footprint @ plane_u, footprint @ plane_v]
            )
            point_uv = np.asarray([point_xyz @ plane_u, point_xyz @ plane_v])
            footprint_uv_closed, footprint_xyz_closed = _ensure_closed_pair(
                footprint_uv, footprint
            )
            source_point = _nearest_point_on_projected_polyline(
                point_uv, footprint_uv_closed, footprint_xyz_closed
            )
        delta = point_xyz - source_point
        if support_normals is not None:
            normal = support_normals[index]
            if float(np.dot(delta, normal)) < 0.0:
                normal = -normal
            lift = float(np.dot(delta, normal))
            tangent = delta - lift * normal
            local_width_samples.append(float(np.linalg.norm(tangent)))
        else:
            lift = float(np.dot(delta, span))
        lift_samples.append(lift)
    lifts = np.asarray(lift_samples, dtype=float)
    if not np.all(np.isfinite(lifts)) or float(np.median(lifts)) <= tolerance or np.any(lifts < -tolerance):
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            f"{attachment_kind} retained blade boundary is not above its source attachment blend",
            {"lift_samples_mm": lifts.tolist(), "material_side": material_side},
        )
    if support_normals is not None:
        widths = np.asarray(local_width_samples, dtype=float)
        if (
            not np.all(np.isfinite(widths))
            or float(np.median(widths)) <= tolerance
            or np.any(widths < -tolerance)
        ):
            raise SectionRecoveryError(
                "v116_root_attachment_measurement_failed",
                f"{attachment_kind} local attachment width is not positive",
                {"width_samples_mm": widths.tolist()},
            )
        width = float(np.median(widths))
        width_method = "paired_boundary_support_normal_decomposition"
    elif width_direction_xyz is not None:
        width_axis = np.asarray(_point(width_direction_xyz, 3, "width_direction_xyz"), dtype=float)
        width_axis -= float(np.dot(width_axis, mean_span)) * mean_span
        width_axis = _unit(width_axis, "width_direction_xyz")
        coordinates = footprint @ width_axis
        width = float(np.max(coordinates) - np.min(coordinates))
        width_method = "explicit_support_tangent_direction_extent"
    else:
        plane_u, plane_v = _plane_basis(mean_span, None)
        footprint_uv = np.column_stack([footprint @ plane_u, footprint @ plane_v])
        width = _minimum_caliper_width(footprint_uv)
        width_method = "support_tangent_plane_minimum_caliper"
    if support_normals is None:
        widths = np.repeat(float(width), len(retained))
    if streamwise_parameters is None:
        streamwise_parameters = np.linspace(0.0, 1.0, len(retained))
    if not math.isfinite(width) or width <= tolerance:
        raise SectionRecoveryError(
            "v116_root_attachment_measurement_failed",
            f"{attachment_kind} attachment width is not positive",
            {"attachment_width_mm": width},
        )
    return AttachmentMeasurement(
        attachment_kind=str(attachment_kind),
        lift_mm=_round(float(np.median(lifts))),
        attachment_width_mm=_round(width),
        local_span_direction_xyz=tuple(float(value) for value in mean_span),
        material_side=material_side,
        lift_samples_mm=tuple(_round(value) for value in lifts),
        width_samples_mm=tuple(_round(value) for value in widths),
        streamwise_samples_s=tuple(
            _round(value) for value in streamwise_parameters
        ),
        source_face_ids=face_ids,
        footprint_source_edge_ids=footprint_edge_ids,
        retained_source_edge_ids=retained_edge_ids,
        span_direction_source_ids=span_source_ids,
        termination_source_edge_ids=termination_edge_ids,
        local_span_directions_xyz=_tuple_points(spans, 3),
        provenance_kind=(
            "occt_source_adjacency" if promotable_evidence else "synthetic_caller_arrays"
        ),
        adjacency_evidence=adjacency,
        termination_point_count=(
            len(termination_boundary_xyz_mm) if termination_boundary_xyz_mm is not None else 0
        ),
        span_direction_evidence=span_direction_evidence,
        span_direction_angular_residual_max_deg=_round(angular_residual_max),
        span_direction_angular_tolerance_deg=_round(angular_tolerance),
        source_measurement=promotable_evidence,
        promotable=promotable_evidence,
        footprint_source=(
            "source_adjacency_boundary" if promotable_evidence else "synthetic_caller_array"
        ),
        retained_boundary_source=(
            "source_retained_blade_boundary" if promotable_evidence else "synthetic_caller_array"
        ),
        width_method=width_method,
        footprint_points_xyz_mm=_tuple_points(footprint, 3),
        retained_points_xyz_mm=_tuple_points(retained, 3),
        paired_footprint_points_xyz_mm=(
            () if paired_footprint is None else _tuple_points(paired_footprint, 3)
        ),
        termination_points_xyz_mm=(
            ()
            if termination_boundary_xyz_mm is None
            else _tuple_points(
                np.asarray(termination_boundary_xyz_mm, dtype=float), 3
            )
        ),
    )


def select_authenticated_open_side_pair(
    edges: Sequence[SectionEdge],
    *,
    source_tolerance_mm: float,
    local_frame: LocalSectionFrame | None = None,
    local_projector: Callable[[Sequence[float]], Sequence[float]] | None = None,
    section_normal_xyz: Sequence[float] = (0.0, 0.0, 1.0),
    material_side: int = 1,
) -> SectionLoop:
    """Select the principal exact side curves without inventing a closed wire."""

    tolerance = _positive(source_tolerance_mm, "source_tolerance_mm")
    candidates = {
        role: [edge for edge in edges if edge.source_roles == (role,)]
        for role in ("side_a", "side_b")
    }
    if any(not values for values in candidates.values()):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "an authenticated open section requires one exact curve for each blade side",
            {
                "available_source_roles": sorted(
                    {role for edge in edges for role in edge.source_roles}
                )
            },
        )

    all_points = np.vstack(
        [
            np.asarray(edge.points_xyz_mm, dtype=float)
            for role in ("side_a", "side_b")
            for edge in candidates[role]
        ]
    )
    projector, normal = _section_projector(
        all_points,
        local_frame=local_frame,
        local_projector=local_projector,
        section_normal_xyz=section_normal_xyz,
    )
    oriented_by_role: dict[str, tuple[SectionEdge, ...]] = {}
    chain_evidence = {}
    for role in ("side_a", "side_b"):
        chain, evidence = _principal_connected_side_chain(
            candidates[role], tolerance=tolerance, role=role
        )
        points_sq = np.asarray(
            [projector(point) for point in _concatenate_edge_points(chain)],
            dtype=float,
        )
        if points_sq[0, 0] > points_sq[-1, 0]:
            chain = tuple(
                replace(
                    edge,
                    points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
                    source_face_parameter_uv=tuple(
                        reversed(edge.source_face_parameter_uv)
                    ),
                    topology_start_vertex_id=edge.topology_end_vertex_id,
                    topology_end_vertex_id=edge.topology_start_vertex_id,
                )
                for edge in reversed(chain)
            )
        oriented = []
        for edge in chain:
            edge_xyz = np.asarray(edge.points_xyz_mm, dtype=float)
            edge_sq = np.asarray([projector(point) for point in edge_xyz], dtype=float)
            oriented.append(
                replace(
                    edge,
                    points_xyz_mm=_tuple_points(edge_xyz, 3),
                    points_sq_mm=_tuple_points(edge_sq, 2),
                )
            )
        oriented_by_role[role] = tuple(oriented)
        chain_evidence[role] = evidence
    side_a_edges = oriented_by_role["side_a"]
    side_b_edges = oriented_by_role["side_b"]
    side_a_xyz = _concatenate_edge_points(side_a_edges)
    side_b_xyz = _concatenate_edge_points(side_b_edges)
    side_a_sq = _concatenate_edge_local_points(side_a_edges)
    side_b_sq = _concatenate_edge_local_points(side_b_edges)
    leading_gap = float(np.linalg.norm(side_a_xyz[0] - side_b_xyz[0]))
    trailing_gap = float(np.linalg.norm(side_a_xyz[-1] - side_b_xyz[-1]))
    side_a_length = _polyline_length(side_a_xyz)
    side_b_length = _polyline_length(side_b_xyz)
    shorter_side_length = min(side_a_length, side_b_length)
    side_length_ratio = shorter_side_length / max(side_a_length, side_b_length)
    maximum_endpoint_gap_ratio = max(leading_gap, trailing_gap) / max(
        shorter_side_length, _EPSILON
    )
    if side_length_ratio < 0.5 or maximum_endpoint_gap_ratio > 0.5:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "authenticated side chains do not cover corresponding blade extents",
            {
                "side_a_length_mm": side_a_length,
                "side_b_length_mm": side_b_length,
                "side_length_ratio": side_length_ratio,
                "leading_endpoint_gap_mm": leading_gap,
                "trailing_endpoint_gap_mm": trailing_gap,
                "maximum_endpoint_gap_ratio": maximum_endpoint_gap_ratio,
                "side_chain_selection": chain_evidence,
            },
        )
    polygon_xyz = np.vstack([side_a_xyz, side_b_xyz[::-1], side_a_xyz[:1]])
    polygon_sq = np.vstack(
        [
            side_a_sq,
            side_b_sq[::-1],
            side_a_sq[:1],
        ]
    )
    signed_area = _signed_polygon_area(polygon_sq)
    selected_edges = side_a_edges + side_b_edges
    return SectionLoop(
        loop_id="authenticated_open_side_pair",
        edges=selected_edges,
        points_xyz_mm=_tuple_points(polygon_xyz, 3),
        points_sq_mm=_tuple_points(polygon_sq, 2),
        orientation="counterclockwise" if signed_area >= 0.0 else "clockwise",
        start_landmark="leading_side_a",
        closure_gap_mm=max(leading_gap, trailing_gap),
        self_intersection_count=_closed_polyline_self_intersection_count(polygon_sq),
        section_normal_xyz=tuple(float(value) for value in normal),
        material_side=int(material_side),
        source_face_ids=tuple(
            sorted(
                {
                    face_id
                    for edge in selected_edges
                    for face_id in edge.source_face_ids
                }
            )
        ),
        source_edge_ids=tuple(edge.edge_id for edge in selected_edges),
        source_tolerance_mm=tolerance,
        source_kind="occt_exact_authenticated_open_side_pair",
        orientation_evidence={
            "method": "longest_authenticated_curve_per_side_in_physical_s",
            "leading_endpoint_gap_mm": leading_gap,
            "trailing_endpoint_gap_mm": trailing_gap,
            "endpoint_bridges_are_geometry_authority": False,
            "physical_s_is_curve_parameter": False,
            "curve_parameter_authority": "source_curve_chord_length_u",
            "side_chain_selection": chain_evidence,
        },
        source_wire_exact=False,
        display_polyline_exact=False,
    )


def _principal_connected_side_chain(
    edges: Sequence[SectionEdge], *, tolerance: float, role: str
) -> tuple[tuple[SectionEdge, ...], dict[str, Any]]:
    """Return the longest well-covered open path for one blade side."""

    edge_vertices, vertex_points = _cluster_geometry_endpoints(edges, tolerance)
    vertex_edges: dict[str, list[int]] = {}
    for edge_index, vertices in enumerate(edge_vertices):
        for vertex in vertices:
            vertex_edges.setdefault(vertex, []).append(edge_index)
    unvisited = set(range(len(edges)))
    component_indices = []
    while unvisited:
        seed = min(unvisited, key=lambda index: _edge_sort_key(edges[index]))
        stack = [seed]
        component = set()
        while stack:
            edge_index = stack.pop()
            if edge_index in component:
                continue
            component.add(edge_index)
            for vertex in edge_vertices[edge_index]:
                stack.extend(vertex_edges.get(vertex, ()))
        unvisited.difference_update(component)
        component_indices.append(component)

    valid_components = []
    rejected_components = []
    for component in component_indices:
        vertices = {vertex for index in component for vertex in edge_vertices[index]}
        degrees = {
            vertex: sum(
                2 if edge_vertices[index][0] == edge_vertices[index][1] == vertex else 1
                for index in component
                if vertex in edge_vertices[index]
            )
            for vertex in vertices
        }
        endpoints = [vertex for vertex, degree in degrees.items() if degree == 1]
        if len(endpoints) < 2:
            rejected_components.append(
                {
                    "edge_ids": sorted(edges[index].edge_id for index in component),
                    "vertex_degrees": sorted(degrees.values()),
                    "reason": "component_has_no_open_path",
                }
            )
            continue
        path = _longest_component_open_path(
            edges,
            edge_vertices=edge_vertices,
            vertex_edges=vertex_edges,
            vertex_points=vertex_points,
            component=component,
            endpoints=endpoints,
        )
        if path is None:
            rejected_components.append(
                {
                    "edge_ids": sorted(edges[index].edge_id for index in component),
                    "vertex_degrees": sorted(degrees.values()),
                    "reason": "open_path_traversal_failed",
                }
            )
            continue
        length, ordered, selected_indices = path
        valid_components.append(
            (
                float(length),
                tuple(ordered),
                sorted(
                    edges[index].edge_id
                    for index in component.difference(selected_indices)
                ),
            )
        )
    if not valid_components:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"authenticated {role} section edges do not form an open unbranched chain",
            {
                "role": role,
                "candidate_edge_ids": sorted(edge.edge_id for edge in edges),
                "rejected_components": rejected_components,
            },
        )
    valid_components.sort(
        key=lambda item: (
            -item[0],
            tuple(edge.edge_id for edge in item[1]),
        )
    )
    selected_length, selected, discarded_branch_edge_ids = valid_components[0]
    total_candidate_length = sum(
        _polyline_length(np.asarray(edge.points_xyz_mm, dtype=float))
        for edge in edges
    )
    selected_coverage_ratio = selected_length / max(total_candidate_length, _EPSILON)
    authenticated_trim_surface_available = all(
        isinstance(edge.source_surface_parameter_authority, Mapping)
        and bool(
            edge.source_surface_parameter_authority.get("trim_boundary_uv_paths")
        )
        for edge in selected
    )
    if selected_coverage_ratio < 0.75 and not authenticated_trim_surface_available:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"authenticated {role} principal chain omits significant source sections",
            {
                "role": role,
                "candidate_edge_ids": sorted(edge.edge_id for edge in edges),
                "selected_edge_ids": [edge.edge_id for edge in selected],
                "selected_length_mm": selected_length,
                "total_candidate_length_mm": total_candidate_length,
                "selected_coverage_ratio": selected_coverage_ratio,
                "minimum_selected_coverage_ratio": 0.75,
                "rejected_components": rejected_components,
            },
        )
    return selected, {
        "method": "longest_connected_unbranched_source_section_chain",
        "candidate_edge_count": len(edges),
        "connected_component_count": len(component_indices),
        "selected_edge_ids": [edge.edge_id for edge in selected],
        "selected_length_mm": selected_length,
        "total_candidate_length_mm": total_candidate_length,
        "selected_coverage_ratio": selected_coverage_ratio,
        "selected_coverage_gate_applied": not authenticated_trim_surface_available,
        "alternative_intersections_are_geometry_authority": False,
        "authenticated_trim_surface_available": authenticated_trim_surface_available,
        "discarded_component_lengths_mm": [
            length for length, _component, _discarded in valid_components[1:]
        ],
        "discarded_branch_edge_ids": discarded_branch_edge_ids,
        "rejected_components": rejected_components,
    }


def _longest_component_open_path(
    edges: Sequence[SectionEdge],
    *,
    edge_vertices: Sequence[tuple[str, str]],
    vertex_edges: Mapping[str, Sequence[int]],
    vertex_points: Mapping[str, np.ndarray],
    component: set[int],
    endpoints: Sequence[str],
) -> tuple[float, tuple[SectionEdge, ...], set[int]] | None:
    endpoint_set = set(endpoints)
    candidates = []

    def walk(
        start: str,
        current: str,
        visited_vertices: set[str],
        used_edges: set[int],
        ordered: list[SectionEdge],
        length: float,
    ) -> None:
        if current in endpoint_set and current != start and ordered:
            canonical = tuple(ordered)
            first_point = np.asarray(canonical[0].points_xyz_mm[0], dtype=float)
            last_point = np.asarray(canonical[-1].points_xyz_mm[-1], dtype=float)
            if _point_sort_key(first_point) > _point_sort_key(last_point):
                canonical = tuple(
                    _reverse_section_edge(edge) for edge in reversed(canonical)
                )
            candidates.append((float(length), canonical, set(used_edges)))
        for edge_index in sorted(
            (
                index
                for index in vertex_edges.get(current, ())
                if index in component and index not in used_edges
            ),
            key=lambda index: _edge_sort_key(edges[index]),
        ):
            first, second = edge_vertices[edge_index]
            next_vertex = second if first == current else first
            if next_vertex in visited_vertices:
                continue
            edge = (
                edges[edge_index]
                if first == current
                else _reverse_section_edge(edges[edge_index])
            )
            edge_length = _polyline_length(
                np.asarray(edge.points_xyz_mm, dtype=float)
            )
            walk(
                start,
                next_vertex,
                visited_vertices | {next_vertex},
                used_edges | {edge_index},
                [*ordered, edge],
                length + edge_length,
            )

    for start in sorted(endpoints, key=lambda value: _point_sort_key(vertex_points[value])):
        walk(start, start, {start}, set(), [], 0.0)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            -item[0],
            tuple(edge.edge_id for edge in item[1]),
        )
    )
    return candidates[0]


def _reverse_section_edge(edge: SectionEdge) -> SectionEdge:
    return replace(
        edge,
        points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
        source_face_parameter_uv=tuple(reversed(edge.source_face_parameter_uv)),
        topology_start_vertex_id=edge.topology_end_vertex_id,
        topology_end_vertex_id=edge.topology_start_vertex_id,
    )


def measure_root_attachment(*args: Any, **kwargs: Any) -> AttachmentMeasurement:
    kwargs = dict(kwargs)
    kwargs.setdefault("attachment_kind", "root")
    kwargs.setdefault("material_side", 1)
    return measure_attachment(*args, **kwargs)


def measure_shroud_attachment(*args: Any, **kwargs: Any) -> AttachmentMeasurement:
    kwargs = dict(kwargs)
    kwargs.setdefault("attachment_kind", "shroud")
    if "material_side" in kwargs and kwargs["material_side"] != -1:
        raise ValueError("shroud attachment requires material_side=-1")
    kwargs["material_side"] = -1
    return measure_attachment(*args, **kwargs)


def _profile_points(profile: Mapping[str, Any] | Sequence[Sequence[float]], count: int) -> np.ndarray:
    value: Any = profile
    if isinstance(value, Mapping) and "profile_fit" in value:
        value = value["profile_fit"]
    if isinstance(value, Mapping):
        if "control_points_rz_mm" in value:
            controls = np.asarray(value["control_points_rz_mm"], dtype=float)
            degree = int(value.get("degree", min(3, len(controls) - 1)))
            knots = np.asarray(
                value.get("knots", _clamped_uniform_knots(len(controls), degree)), dtype=float
            )
            points = _basis_matrix(np.linspace(0.0, 1.0, max(count, 4 * len(controls))), len(controls), degree, knots) @ controls
        else:
            for key in ("points_rz_mm", "samples_rz_mm", "meridional_points_rz_mm"):
                if key in value:
                    points = np.asarray(value[key], dtype=float)
                    break
            else:
                raise ValueError("profile mapping requires controls or meridional points")
    else:
        points = np.asarray(value, dtype=float)
    _validate_points(points, 2, "profile", minimum=2)
    return _resample_open_polyline(points, count)


def _endpoint_pair_cost(first: np.ndarray, second: np.ndarray) -> float:
    scale = max(_polyline_length(first), _polyline_length(second), 1.0)
    endpoint = float(np.linalg.norm(first[0] - second[0]) + np.linalg.norm(first[-1] - second[-1]))
    tangent_first = _unit(first[min(3, len(first) - 1)] - first[0], "profile_tangent")
    tangent_second = _unit(second[min(3, len(second) - 1)] - second[0], "profile_tangent")
    return endpoint / scale + (1.0 - float(np.dot(tangent_first, tangent_second)))


def _isotonic_non_decreasing(values: np.ndarray) -> np.ndarray:
    blocks: list[list[float]] = []
    for index, value in enumerate(values):
        blocks.append([float(value), 1.0, float(index), float(index)])
        while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
            right = blocks.pop()
            left = blocks.pop()
            weight = left[1] + right[1]
            blocks.append(
                [
                    (left[0] * left[1] + right[0] * right[1]) / weight,
                    weight,
                    left[2],
                    right[3],
                ]
            )
    result = np.empty(len(values), dtype=float)
    for mean, _weight, start, end in blocks:
        result[int(start) : int(end) + 1] = mean
    result[0] = 0.0
    result[-1] = 1.0
    return np.maximum.accumulate(np.clip(result, 0.0, 1.0))


def _reject_crossing_span_connectors(hub: np.ndarray, tip: np.ndarray) -> None:
    for index in range(len(hub) - 1):
        for other in range(index + 1, len(hub)):
            if _segments_intersect_2d(hub[index], tip[index], hub[other], tip[other], strict=True):
                raise SectionRecoveryError(
                    "v116_span_surface_ordering_failed",
                    "hub-to-tip meridional correspondence contains crossing span connectors",
                    {"connector_indices": [index, other]},
                )


def _support_polylines_intersect(first: np.ndarray, second: np.ndarray) -> bool:
    return any(
        _segments_intersect_2d(first_start, first_end, second_start, second_end, strict=False)
        for first_start, first_end in zip(first[:-1], first[1:])
        for second_start, second_end in zip(second[:-1], second[1:])
    )


def _validated_active_span_evidence(
    evidence: Mapping[str, Any] | None,
    boundary: str,
    requested_h: float | None,
    *,
    known_source_face_ids: Sequence[str] | set[str] | None,
    known_source_edge_ids: Sequence[str] | set[str] | None,
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"active {boundary} must come from measured source-boundary evidence",
            {"boundary": boundary, "evidence_present": False},
        )
    record = dict(evidence)
    try:
        h = float(record["h"])
        tolerance = float(record["tolerance_mm"])
        residual = float(record["residual_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"active {boundary} evidence is incomplete",
            {"boundary": boundary},
        ) from exc
    source_face_ids = _typed_source_ids(record.get("source_face_ids"), "source_face_ids")
    source_edge_ids = _typed_source_ids(record.get("source_edge_ids"), "source_edge_ids")
    known_faces = set(_typed_source_ids(known_source_face_ids, "known_source_face_ids"))
    known_edges = set(_typed_source_ids(known_source_edge_ids, "known_source_edge_ids"))
    unknown_faces = sorted(set(source_face_ids).difference(known_faces))
    unknown_edges = sorted(set(source_edge_ids).difference(known_edges))
    source_ids = tuple(sorted(set(source_face_ids + source_edge_ids)))
    method = str(record.get("method", "")).strip()
    if (
        not math.isfinite(h)
        or not 0.0 <= h <= 1.0
        or not math.isfinite(tolerance)
        or tolerance <= 0.0
        or not math.isfinite(residual)
        or residual < 0.0
        or residual > tolerance
        or not source_face_ids
        or not source_edge_ids
        or not known_faces
        or not known_edges
        or unknown_faces
        or unknown_edges
        or not method
    ):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"active {boundary} evidence is not promotable source measurement",
            {
                "boundary": boundary,
                "h": h,
                "tolerance_mm": tolerance,
                "residual_mm": residual,
                "source_ids": list(source_ids),
                "unknown_source_face_ids": unknown_faces,
                "unknown_source_edge_ids": unknown_edges,
                "method": method,
            },
        )
    if requested_h is not None and abs(float(requested_h) - h) > 1.0e-12:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"requested active {boundary} conflicts with measured evidence",
            {"requested_h": float(requested_h), "measured_h": h},
        )
    record["h"] = _round(h)
    record["tolerance_mm"] = _round(tolerance)
    record["residual_mm"] = _round(residual)
    record["source_ids"] = list(source_ids)
    record["source_face_ids"] = list(source_face_ids)
    record["source_edge_ids"] = list(source_edge_ids)
    record["authenticated_source_inventory"] = {
        "authority": "complete_source_brep_inventory",
        "matched_source_face_ids": list(source_face_ids),
        "matched_source_edge_ids": list(source_edge_ids),
    }
    return record


def _typed_source_ids(values: Any, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (Sequence, set, frozenset)):
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            f"{field} must be an explicit sequence of source entity ids",
            {"field": field},
        )
    identifiers = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    return identifiers


def _metric_refinement_error(lower: Any, midpoint: Any, upper: Any) -> float:
    first = np.asarray(lower, dtype=float)
    middle = np.asarray(midpoint, dtype=float)
    last = np.asarray(upper, dtype=float)
    if first.shape != middle.shape or first.shape != last.shape or not all(
        np.all(np.isfinite(item)) for item in (first, middle, last)
    ):
        raise ValueError("adaptive metrics must have matching finite numeric shapes")
    endpoint_delta = float(np.linalg.norm(last - first))
    interpolation_residual = float(np.linalg.norm(middle - 0.5 * (first + last)))
    absolute_residual = max(
        float(np.linalg.norm(first)),
        float(np.linalg.norm(middle)),
        float(np.linalg.norm(last)),
    )
    return max(absolute_residual, endpoint_delta, 2.0 * interpolation_residual)


def _section_edge(value: SectionEdge | Mapping[str, Any], index: int) -> SectionEdge:
    if isinstance(value, SectionEdge):
        edge = value
    elif isinstance(value, Mapping):
        local_points = value.get("points_sq_mm")
        edge = SectionEdge(
            edge_id=str(value.get("edge_id", f"section_edge_{index:03d}")),
            points_xyz_mm=_tuple_points(np.asarray(value["points_xyz_mm"], dtype=float), 3),
            points_sq_mm=_tuple_points(np.asarray(local_points, dtype=float), 2)
            if local_points is not None and len(local_points)
            else (),
            source_face_ids=tuple(sorted(str(item) for item in value.get("source_face_ids", ()))),
            source_roles=tuple(sorted(_canonical_segment_role(item) for item in value.get("source_roles", ()))),
            provenance_available=bool(value.get("provenance_available", False)),
            exact_curve=bool(value.get("exact_curve", False)),
            source_curve_exact=bool(value.get("source_curve_exact", False)),
            sampled_display_only=bool(value.get("sampled_display_only", True)),
            topology_start_vertex_id=(
                str(value["topology_start_vertex_id"])
                if value.get("topology_start_vertex_id") is not None
                else None
            ),
            topology_end_vertex_id=(
                str(value["topology_end_vertex_id"])
                if value.get("topology_end_vertex_id") is not None
                else None
            ),
            source_parameter_face_id=(
                str(value["source_parameter_face_id"])
                if value.get("source_parameter_face_id") is not None
                else None
            ),
            source_face_parameter_uv=(
                _tuple_points(
                    np.asarray(value.get("source_face_parameter_uv"), dtype=float),
                    2,
                )
                if value.get("source_face_parameter_uv")
                else ()
            ),
            source_face_parameter_residual_max_mm=float(
                value.get("source_face_parameter_residual_max_mm", 0.0)
            ),
            source_surface_parameter_authority=(
                dict(value["source_surface_parameter_authority"])
                if isinstance(
                    value.get("source_surface_parameter_authority"), Mapping
                )
                else None
            ),
        )
    else:
        raise TypeError("section edges must be SectionEdge objects or mappings")
    points = np.asarray(edge.points_xyz_mm, dtype=float)
    _validate_points(points, 3, f"edges[{index}].points_xyz_mm", minimum=2)
    if not edge.edge_id:
        raise ValueError("edge_id must be nonempty")
    return edge


def _cluster_geometry_endpoints(
    edges: Sequence[SectionEdge], tolerance: float
) -> tuple[list[tuple[str, str]], dict[str, np.ndarray]]:
    """Geometry-only fallback for tests; production STEP edges use OCCT vertex ids."""
    cell_size = max(float(tolerance), 1.0e-12)
    bins: dict[tuple[int, int, int], list[str]] = {}
    points_by_id: dict[str, np.ndarray] = {}

    def vertex_id(point: Sequence[float]) -> str:
        value = np.asarray(point, dtype=float)
        cell = tuple(int(math.floor(coordinate / cell_size)) for coordinate in value)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for candidate in bins.get(
                        (cell[0] + dx, cell[1] + dy, cell[2] + dz), ()
                    ):
                        if float(np.linalg.norm(value - points_by_id[candidate])) <= tolerance:
                            return candidate
        identifier = f"geometry_vertex_{len(points_by_id):03d}"
        points_by_id[identifier] = value
        bins.setdefault(cell, []).append(identifier)
        return identifier

    pairs = [
        (vertex_id(edge.points_xyz_mm[0]), vertex_id(edge.points_xyz_mm[-1]))
        for edge in edges
    ]
    return pairs, points_by_id


def _section_projector(
    points_xyz: np.ndarray,
    *,
    local_frame: LocalSectionFrame | None,
    local_projector: Callable[[Sequence[float]], Sequence[float]] | None,
    section_normal_xyz: Sequence[float],
) -> tuple[Callable[[Sequence[float]], tuple[float, float]], np.ndarray]:
    if local_projector is not None:
        normal = _unit(section_normal_xyz, "section_normal_xyz")

        def project(point: Sequence[float]) -> tuple[float, float]:
            return _point(local_projector(point), 2, "local_projector result")

        return project, normal
    if local_frame is not None:
        return local_frame.project, np.asarray(local_frame.normal_xyz, dtype=float)
    unique = points_xyz[:-1] if np.linalg.norm(points_xyz[0] - points_xyz[-1]) <= 1.0e-10 else points_xyz
    centered = unique - np.mean(unique, axis=0)
    _u, _singular, vectors = np.linalg.svd(centered, full_matrices=False)
    normal = _unit(section_normal_xyz, "section_normal_xyz")
    s_axis = vectors[0] - float(np.dot(vectors[0], normal)) * normal
    if float(np.linalg.norm(s_axis)) <= 1.0e-9:
        s_axis = vectors[1] - float(np.dot(vectors[1], normal)) * normal
    s_axis = _unit(s_axis, "derived_s_axis")
    q_axis = np.cross(normal, s_axis)
    if _point_sort_key(s_axis) > _point_sort_key(-s_axis):
        s_axis = -s_axis
        q_axis = -q_axis
    origin = np.mean(unique, axis=0)
    frame = LocalSectionFrame(tuple(origin), tuple(s_axis), tuple(q_axis), tuple(normal))
    return frame.project, normal


def _segments_from_source_roles(loop: SectionLoop) -> dict[str, dict[str, Any]] | None:
    role_edges: dict[str, list[SectionEdge]] = {name: [] for name in _SEGMENT_ROLES}
    for edge in loop.edges:
        if len(edge.source_roles) != 1 or edge.source_roles[0] not in role_edges:
            return None
        role_edges[edge.source_roles[0]].append(edge)
    if any(not values for values in role_edges.values()):
        return None
    frame: LocalSectionFrame | None = None
    result: dict[str, dict[str, Any]] = {}
    for name, edges in role_edges.items():
        points_xyz = _concatenate_edge_points(edges)
        if all(edge.points_sq_mm for edge in edges):
            points_sq = _concatenate_edge_local_points(edges)
        else:
            if frame is None:
                frame = _frame_from_loop(loop)
            points_sq = np.asarray([frame.project(point) for point in points_xyz], dtype=float)
        result[name] = {
            "points_xyz_mm": points_xyz,
            "points_sq_mm": points_sq,
            "source_edge_ids": tuple(edge.edge_id for edge in edges),
            "source_face_ids": tuple(sorted({item for edge in edges for item in edge.source_face_ids})),
        }
    return _orient_decomposed_segments(result)


def _segments_from_authenticated_side_roles(
    loop: SectionLoop,
) -> dict[str, dict[str, Any]] | None:
    """Keep exact side boundaries while classifying only the two closure arcs."""
    labels: list[str | None] = []
    for edge in loop.edges:
        if len(edge.source_roles) > 1:
            return None
        label = edge.source_roles[0] if edge.source_roles else None
        if label not in {None, "side_a", "side_b"}:
            return None
        labels.append(label)
    if not labels or set(labels) != {None, "side_a", "side_b"}:
        return None

    start = next(
        (
            index
            for index, label in enumerate(labels)
            if label != labels[index - 1]
        ),
        None,
    )
    if start is None:
        return None
    ordered = list(loop.edges[start:]) + list(loop.edges[:start])
    ordered_labels = labels[start:] + labels[:start]
    runs: list[tuple[str | None, list[SectionEdge]]] = []
    for label, edge in zip(ordered_labels, ordered):
        if not runs or runs[-1][0] != label:
            runs.append((label, [edge]))
        else:
            runs[-1][1].append(edge)
    if len(runs) != 4:
        return None
    if [label for label, _edges in runs].count("side_a") != 1:
        return None
    if [label for label, _edges in runs].count("side_b") != 1:
        return None
    if [label for label, _edges in runs].count(None) != 2:
        return None

    frame: LocalSectionFrame | None = None

    def record(edges: Sequence[SectionEdge]) -> dict[str, Any]:
        nonlocal frame
        points_xyz = _concatenate_edge_points(edges)
        if all(edge.points_sq_mm for edge in edges):
            points_sq = _concatenate_edge_local_points(edges)
        else:
            if frame is None:
                frame = _frame_from_loop(loop)
            points_sq = np.asarray(
                [frame.project(point) for point in points_xyz], dtype=float
            )
        return {
            "points_xyz_mm": points_xyz,
            "points_sq_mm": points_sq,
            "source_edge_ids": tuple(edge.edge_id for edge in edges),
            "source_face_ids": tuple(
                sorted({item for edge in edges for item in edge.source_face_ids})
            ),
        }

    result = {
        label: record(edges)
        for label, edges in runs
        if label in {"side_a", "side_b"}
    }
    closures = [record(edges) for label, edges in runs if label is None]
    closures.sort(
        key=lambda value: float(np.mean(np.asarray(value["points_sq_mm"])[:, 0]))
    )
    result["leading_edge"] = closures[0]
    result["trailing_edge"] = closures[1]
    return _orient_decomposed_segments(result)


def _segments_from_landmarks_or_geometry(
    loop: SectionLoop, landmark_indices: Mapping[str, int] | None
) -> dict[str, dict[str, Any]]:
    sq, xyz = _resample_closed_pair(loop.points_sq_mm, loop.points_xyz_mm, 257)
    unique_sq = sq[:-1]
    unique_xyz = xyz[:-1]
    if landmark_indices is not None:
        required = {
            "leading_side_a",
            "trailing_side_a",
            "trailing_side_b",
            "leading_side_b",
        }
        if set(landmark_indices) != required:
            raise ValueError(f"landmark_indices must contain exactly {sorted(required)}")
        scaled = {
            name: int(round(int(index) % (len(loop.points_sq_mm) - 1) * len(unique_sq) / (len(loop.points_sq_mm) - 1)))
            % len(unique_sq)
            for name, index in landmark_indices.items()
        }
        side_a_indices = _circular_index_path(scaled["leading_side_a"], scaled["trailing_side_a"], len(unique_sq))
        trailing_indices = _circular_index_path(scaled["trailing_side_a"], scaled["trailing_side_b"], len(unique_sq))
        side_b_loop = _circular_index_path(scaled["trailing_side_b"], scaled["leading_side_b"], len(unique_sq))
        leading_indices = _circular_index_path(scaled["leading_side_b"], scaled["leading_side_a"], len(unique_sq))
        role_indices = {
            "side_a": side_a_indices,
            "side_b": list(reversed(side_b_loop)),
            "leading_edge": leading_indices,
            "trailing_edge": trailing_indices,
        }
    else:
        tangent = np.roll(unique_sq, -1, axis=0) - np.roll(unique_sq, 1, axis=0)
        tangent_alignment = np.abs(tangent[:, 0]) / np.maximum(np.linalg.norm(tangent, axis=1), _EPSILON)
        leading_center = int(np.argmin(unique_sq[:, 0]))
        trailing_center = int(np.argmax(unique_sq[:, 0]))
        boundaries = []
        for center in (leading_center, trailing_center):
            for direction in (-1, 1):
                selected = None
                for step in range(1, max(3, len(unique_sq) // 4)):
                    index = (center + direction * step) % len(unique_sq)
                    if tangent_alignment[index] >= 0.72:
                        selected = index
                        break
                boundaries.append(selected if selected is not None else (center + direction * len(unique_sq) // 16) % len(unique_sq))
        boundary_values = sorted(set(boundaries))
        if len(boundary_values) != 4:
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed", "four distinct side/edge landmarks were not found"
            )
        arcs = [
            _circular_index_path(boundary_values[index], boundary_values[(index + 1) % 4], len(unique_sq))
            for index in range(4)
        ]
        role_indices: dict[str, list[int]] = {}
        side_candidates = []
        for indices in arcs:
            index_set = set(indices)
            if leading_center in index_set:
                role_indices["leading_edge"] = indices
            elif trailing_center in index_set:
                role_indices["trailing_edge"] = indices
            else:
                side_candidates.append(indices)
        if set(role_indices) != {"leading_edge", "trailing_edge"} or len(side_candidates) != 2:
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed", "streamwise edge landmarks are ambiguous"
            )
        side_candidates.sort(key=lambda indices: -float(np.mean(unique_sq[indices, 1])))
        role_indices["side_a"] = side_candidates[0]
        role_indices["side_b"] = side_candidates[1]

    result = {}
    for name, indices in role_indices.items():
        result[name] = {
            "points_xyz_mm": unique_xyz[indices],
            "points_sq_mm": unique_sq[indices],
            "source_edge_ids": loop.source_edge_ids,
            "source_face_ids": loop.source_face_ids,
        }
    return _orient_decomposed_segments(result)


def _orient_decomposed_segments(
    segments: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    for name in ("side_a", "side_b"):
        points = np.asarray(segments[name]["points_sq_mm"], dtype=float)
        if points[0, 0] > points[-1, 0]:
            segments[name]["points_sq_mm"] = points[::-1]
            segments[name]["points_xyz_mm"] = np.asarray(segments[name]["points_xyz_mm"], dtype=float)[::-1]
    side_a = np.asarray(segments["side_a"]["points_sq_mm"], dtype=float)
    side_b = np.asarray(segments["side_b"]["points_sq_mm"], dtype=float)
    if float(np.mean(side_a[:, 1])) < float(np.mean(side_b[:, 1])):
        segments["side_a"], segments["side_b"] = segments["side_b"], segments["side_a"]
        side_a, side_b = side_b, side_a
    for name, start, end in (
        ("leading_edge", side_b[0], side_a[0]),
        ("trailing_edge", side_a[-1], side_b[-1]),
    ):
        points = np.asarray(segments[name]["points_sq_mm"], dtype=float)
        forward = float(np.linalg.norm(points[0] - start) + np.linalg.norm(points[-1] - end))
        reverse_cost = float(np.linalg.norm(points[-1] - start) + np.linalg.norm(points[0] - end))
        if reverse_cost < forward:
            segments[name]["points_sq_mm"] = points[::-1]
            segments[name]["points_xyz_mm"] = np.asarray(segments[name]["points_xyz_mm"], dtype=float)[::-1]
    return segments


def _camber_point_and_normal(fit: NurbsCurveFit, parameter: float) -> tuple[np.ndarray, np.ndarray]:
    value = float(np.clip(parameter, 0.0, 1.0))
    step = 1.0e-4
    low = max(0.0, value - step)
    high = min(1.0, value + step)
    points = _evaluate_fit_sq(fit, np.asarray([low, value, high]))
    tangent = points[-1] - points[0]
    tangent = _unit(tangent, "camber_tangent")
    normal = np.asarray([-tangent[1], tangent[0]], dtype=float)
    return points[1], normal


def _opposite_side_normal_hits(
    point: np.ndarray, normal: np.ndarray, side_a: np.ndarray, side_b: np.ndarray
) -> tuple[tuple[np.ndarray, float, float], tuple[np.ndarray, float, float]]:
    hits_a = _line_polyline_intersections(point, normal, side_a)
    hits_b = _line_polyline_intersections(point, normal, side_b)
    candidates = [
        (first, second)
        for first in hits_a
        for second in hits_b
        if first[2] * second[2] <= 1.0e-10 and abs(first[2] - second[2]) > _EPSILON
    ]
    if not candidates:
        raise SectionRecoveryError(
            "v116_thickness_field_invalid",
            "a fitted camber normal does not intersect opposite source sides",
            {"camber_sq_mm": point.tolist(), "normal_sq": normal.tolist()},
        )
    return min(candidates, key=lambda pair: (abs(pair[0][2]) + abs(pair[1][2]), pair[0][1], pair[1][1]))


def paired_source_curve_witnesses(
    point: np.ndarray,
    normal: np.ndarray,
    side_a: np.ndarray,
    side_b: np.ndarray,
    *,
    fraction: float,
) -> tuple[tuple[np.ndarray, float, float], tuple[np.ndarray, float, float]]:
    """Return a bounded, symmetric witness pair for derived thickness only.

    A twisted source section can locally turn back in physical S, so a fitted
    camber normal is not guaranteed to intersect both source sides.  The source
    side curves remain geometry authority; this fallback only supplies a
    deterministic thickness witness for adaptive inspection metrics.
    """
    target = np.asarray(point, dtype=float)
    direction = _unit(np.asarray(normal, dtype=float), "normal")
    first_side = np.asarray(side_a, dtype=float)
    second_side = np.asarray(side_b, dtype=float)
    _validate_points(first_side, 2, "side_a", minimum=2)
    _validate_points(second_side, 2, "side_b", minimum=2)
    value = float(np.clip(fraction, 0.0, 1.0))
    anchor_a = _polyline_point_at_arc_fraction(first_side, value)
    anchor_b = _polyline_point_at_arc_fraction(second_side, value)
    nearest_b = _nearest_point_on_polyline_window(
        anchor_a, second_side, center=value, half_window=0.20
    )
    nearest_a = _nearest_point_on_polyline_window(
        anchor_b, first_side, center=value, half_window=0.20
    )
    candidates = (
        ((anchor_a, value), (anchor_b, value)),
        ((anchor_a, value), nearest_b),
        (nearest_a, (anchor_b, value)),
    )
    scale = max(
        float(np.linalg.norm(anchor_a - anchor_b)),
        1.0e-6,
    )

    def score(candidate):
        (candidate_a, parameter_a), (candidate_b, parameter_b) = candidate
        midpoint = 0.5 * (candidate_a + candidate_b)
        separation = float(np.linalg.norm(candidate_a - candidate_b))
        regularization = scale * (
            abs(float(parameter_a) - value) + abs(float(parameter_b) - value)
        )
        return (
            float(np.linalg.norm(midpoint - target))
            + 0.10 * separation
            + 0.35 * regularization,
            regularization,
            parameter_a,
            parameter_b,
        )

    (point_a, parameter_a), (point_b, parameter_b) = min(candidates, key=score)
    if float(np.linalg.norm(point_a - point_b)) <= _EPSILON:
        raise SectionRecoveryError(
            "v116_thickness_field_invalid",
            "paired source-curve thickness witnesses collapse",
            {"fraction": value},
        )
    lambda_a = float(np.dot(point_a - target, direction))
    lambda_b = float(np.dot(point_b - target, direction))
    return (
        (point_a, float(parameter_a), lambda_a),
        (point_b, float(parameter_b), lambda_b),
    )


def _polyline_point_at_arc_fraction(
    polyline: np.ndarray, fraction: float
) -> np.ndarray:
    cumulative = _cumulative_lengths(polyline)
    total = float(cumulative[-1])
    if total <= _EPSILON:
        return np.asarray(polyline[0], dtype=float).copy()
    target = float(np.clip(fraction, 0.0, 1.0)) * total
    index = min(int(np.searchsorted(cumulative, target, side="right")) - 1, len(polyline) - 2)
    index = max(0, index)
    segment_length = float(cumulative[index + 1] - cumulative[index])
    local = 0.0 if segment_length <= _EPSILON else (target - cumulative[index]) / segment_length
    return polyline[index] + float(np.clip(local, 0.0, 1.0)) * (
        polyline[index + 1] - polyline[index]
    )


def _nearest_point_on_polyline_window(
    point: np.ndarray,
    polyline: np.ndarray,
    *,
    center: float,
    half_window: float,
) -> tuple[np.ndarray, float]:
    cumulative = _cumulative_lengths(polyline)
    total = max(float(cumulative[-1]), _EPSILON)
    lower = max(0.0, float(center) - float(half_window))
    upper = min(1.0, float(center) + float(half_window))
    candidates = []
    for index, (first, second) in enumerate(zip(polyline[:-1], polyline[1:])):
        start_parameter = float(cumulative[index] / total)
        end_parameter = float(cumulative[index + 1] / total)
        if end_parameter < lower or start_parameter > upper:
            continue
        segment = second - first
        length_sq = float(np.dot(segment, segment))
        local = (
            0.0
            if length_sq <= _EPSILON
            else float(np.dot(point - first, segment) / length_sq)
        )
        local = float(np.clip(local, 0.0, 1.0))
        parameter = start_parameter + local * (end_parameter - start_parameter)
        if not lower <= parameter <= upper:
            parameter = float(np.clip(parameter, lower, upper))
            span = max(end_parameter - start_parameter, _EPSILON)
            local = float(np.clip((parameter - start_parameter) / span, 0.0, 1.0))
        witness = first + local * segment
        candidates.append((float(np.linalg.norm(witness - point)), parameter, witness))
    if not candidates:
        witness = _polyline_point_at_arc_fraction(polyline, center)
        return witness, float(np.clip(center, 0.0, 1.0))
    _distance, parameter, witness = min(candidates, key=lambda item: (item[0], item[1]))
    return witness, float(parameter)


def _line_polyline_intersections(
    point: np.ndarray, direction: np.ndarray, polyline: np.ndarray
) -> list[tuple[np.ndarray, float, float]]:
    cumulative = _cumulative_lengths(polyline)
    total = max(float(cumulative[-1]), _EPSILON)
    hits = []
    for index, (first, second) in enumerate(zip(polyline[:-1], polyline[1:])):
        segment = second - first
        matrix = np.column_stack([direction, -segment])
        determinant = float(np.linalg.det(matrix))
        if abs(determinant) <= 1.0e-10:
            continue
        line_parameter, segment_parameter = np.linalg.solve(matrix, first - point)
        if -1.0e-9 <= segment_parameter <= 1.0 + 1.0e-9:
            bounded = float(np.clip(segment_parameter, 0.0, 1.0))
            hit = first + bounded * segment
            arc_parameter = (cumulative[index] + bounded * np.linalg.norm(segment)) / total
            hits.append((hit, float(arc_parameter), float(line_parameter)))
    unique: list[tuple[np.ndarray, float, float]] = []
    for hit in sorted(hits, key=lambda item: (abs(item[2]), item[1])):
        if not any(np.linalg.norm(hit[0] - existing[0]) <= 1.0e-8 for existing in unique):
            unique.append(hit)
    return unique


def _polyline_point_at_streamwise(polyline: np.ndarray, streamwise: float) -> np.ndarray:
    candidates = []
    for first, second in zip(polyline[:-1], polyline[1:]):
        delta = second[0] - first[0]
        if abs(delta) <= _EPSILON:
            continue
        parameter = (streamwise - first[0]) / delta
        if -1.0e-9 <= parameter <= 1.0 + 1.0e-9:
            candidates.append(first + float(np.clip(parameter, 0.0, 1.0)) * (second - first))
    if not candidates:
        index = int(np.argmin(np.abs(polyline[:, 0] - streamwise)))
        return polyline[index].copy()
    return np.mean(np.asarray(candidates), axis=0)


def _frame_from_loop(loop: SectionLoop) -> LocalSectionFrame:
    xyz = np.asarray(loop.points_xyz_mm, dtype=float)
    sq = np.asarray(loop.points_sq_mm, dtype=float)
    unique_xyz = xyz[:-1]
    unique_sq = sq[:-1]
    design = np.column_stack([unique_sq[:, 0], unique_sq[:, 1], np.ones(len(unique_sq))])
    coefficients, *_ = np.linalg.lstsq(design, unique_xyz, rcond=None)
    return LocalSectionFrame(
        origin_xyz=tuple(coefficients[2]),
        s_axis_xyz=tuple(coefficients[0]),
        q_axis_xyz=tuple(coefficients[1]),
        normal_xyz=loop.section_normal_xyz,
    )


def _evaluate_fit_sq(fit: NurbsCurveFit, parameters: np.ndarray) -> np.ndarray:
    controls = np.asarray(fit.control_points_sq_mm, dtype=float)
    return _basis_matrix(parameters, len(controls), fit.degree, fit.knots) @ controls


def _fit_endpoint_constrained_controls(basis: np.ndarray, points: np.ndarray) -> np.ndarray:
    control_count = basis.shape[1]
    controls = np.zeros((control_count, points.shape[1]), dtype=float)
    controls[0] = points[0]
    controls[-1] = points[-1]
    if control_count == 2:
        return controls
    interior = basis[:, 1:-1]
    right_hand = points - basis[:, [0]] * controls[0] - basis[:, [-1]] * controls[-1]
    controls[1:-1], *_ = np.linalg.lstsq(interior, right_hand, rcond=None)
    return controls


def _basis_matrix(
    parameters: Sequence[float] | np.ndarray,
    control_count: int,
    degree: int,
    knots: Sequence[float] | np.ndarray,
) -> np.ndarray:
    values = np.asarray(parameters, dtype=float)
    knot_values = np.asarray(knots, dtype=float)
    matrix = np.zeros((len(values), control_count), dtype=float)
    for row, value in enumerate(values):
        for index in range(control_count):
            matrix[row, index] = _basis(index, degree, float(value), knot_values, control_count)
    return matrix


def _basis(index: int, degree: int, value: float, knots: np.ndarray, control_count: int) -> float:
    if degree == 0:
        if (knots[index] <= value < knots[index + 1]) or (
            value == 1.0 and index == control_count - 1
        ):
            return 1.0
        return 0.0
    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left = 0.0
    right = 0.0
    if left_denominator > _EPSILON:
        left = (value - knots[index]) / left_denominator * _basis(
            index, degree - 1, value, knots, control_count
        )
    if right_denominator > _EPSILON:
        right = (knots[index + degree + 1] - value) / right_denominator * _basis(
            index + 1, degree - 1, value, knots, control_count
        )
    return left + right


def _clamped_uniform_knots(control_count: int, degree: int) -> np.ndarray:
    if control_count < degree + 1:
        raise ValueError("control_count must be at least degree + 1")
    interior_count = control_count - degree - 1
    interior = np.linspace(0.0, 1.0, interior_count + 2)[1:-1] if interior_count else np.asarray([])
    return np.concatenate([np.zeros(degree + 1), interior, np.ones(degree + 1)])


def _sample_curvature(points: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    first = np.gradient(points, parameters, axis=0)
    second = np.gradient(first, parameters, axis=0)
    numerator = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
    denominator = np.maximum(np.linalg.norm(first, axis=1) ** 3, _EPSILON)
    return numerator / denominator


def _nearest_distances(points: np.ndarray, targets: np.ndarray) -> np.ndarray:
    result = np.empty(len(points), dtype=float)
    batch = 256
    for start in range(0, len(points), batch):
        block = points[start : start + batch]
        result[start : start + len(block)] = np.sqrt(
            np.min(np.sum((block[:, None, :] - targets[None, :, :]) ** 2, axis=2), axis=1)
        )
    return result


def _points_to_polyline_distances(points: np.ndarray, polyline: np.ndarray) -> np.ndarray:
    values = np.asarray(points, dtype=float)
    curve = np.asarray(polyline, dtype=float)
    if len(curve) < 2:
        return np.linalg.norm(values - curve[0], axis=1)
    starts = curve[:-1]
    vectors = curve[1:] - starts
    squared_lengths = np.sum(vectors * vectors, axis=1)
    result = np.full(len(values), np.inf, dtype=float)
    for offset in range(0, len(values), 256):
        block = values[offset : offset + 256]
        delta = block[:, None, :] - starts[None, :, :]
        parameters = np.divide(
            np.sum(delta * vectors[None, :, :], axis=2),
            squared_lengths[None, :],
            out=np.zeros((len(block), len(vectors)), dtype=float),
            where=squared_lengths[None, :] > _EPSILON,
        )
        parameters = np.clip(parameters, 0.0, 1.0)
        projections = starts[None, :, :] + parameters[:, :, None] * vectors[None, :, :]
        result[offset : offset + len(block)] = np.sqrt(
            np.min(np.sum((block[:, None, :] - projections) ** 2, axis=2), axis=1)
        )
    return result


def _polyline_sag(points: np.ndarray) -> float:
    values = np.asarray(points, dtype=float)
    return float(
        np.max(_points_to_polyline_distances(values, np.asarray([values[0], values[-1]])))
    )


def _minimum_caliper_width(points: np.ndarray) -> float:
    hull = _convex_hull_2d(points)
    if len(hull) < 3:
        return 0.0
    widths = []
    for first, second in zip(hull, np.roll(hull, -1, axis=0)):
        edge = second - first
        if float(np.linalg.norm(edge)) <= _EPSILON:
            continue
        normal = _unit(np.asarray([-edge[1], edge[0]]), "caliper_normal")
        values = hull @ normal
        widths.append(float(np.max(values) - np.min(values)))
    return min((value for value in widths if value > _EPSILON), default=0.0)


def _convex_hull_2d(points: np.ndarray) -> np.ndarray:
    unique = sorted({(float(point[0]), float(point[1])) for point in points})
    if len(unique) <= 1:
        return np.asarray(unique, dtype=float)

    def cross(origin: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
            second[0] - origin[0]
        )

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def _nearest_point_on_projected_polyline(
    point_uv: np.ndarray, polyline_uv: np.ndarray, polyline_xyz: np.ndarray
) -> np.ndarray:
    best: tuple[float, int, float] | None = None
    for index, (first, second) in enumerate(zip(polyline_uv[:-1], polyline_uv[1:])):
        vector = second - first
        denominator = float(np.dot(vector, vector))
        parameter = 0.0 if denominator <= _EPSILON else float(np.dot(point_uv - first, vector) / denominator)
        parameter = float(np.clip(parameter, 0.0, 1.0))
        distance = float(np.linalg.norm(point_uv - (first + parameter * vector)))
        candidate = (distance, index, parameter)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    _distance, index, parameter = best
    return polyline_xyz[index] + parameter * (polyline_xyz[index + 1] - polyline_xyz[index])


def _nearest_point_on_polyline(point: np.ndarray, polyline: np.ndarray) -> np.ndarray:
    best: tuple[float, int, float] | None = None
    for index, (first, second) in enumerate(zip(polyline[:-1], polyline[1:])):
        vector = second - first
        denominator = float(np.dot(vector, vector))
        parameter = (
            0.0
            if denominator <= _EPSILON
            else float(np.dot(point - first, vector) / denominator)
        )
        parameter = float(np.clip(parameter, 0.0, 1.0))
        distance = float(np.linalg.norm(point - (first + parameter * vector)))
        candidate = (distance, index, parameter)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise ValueError("polyline must contain at least two points")
    _distance, index, parameter = best
    return polyline[index] + parameter * (polyline[index + 1] - polyline[index])


def _plane_basis(
    normal: np.ndarray, preferred_axis: Sequence[float] | None
) -> tuple[np.ndarray, np.ndarray]:
    if preferred_axis is not None:
        first = np.asarray(_point(preferred_axis, 3, "width_direction_xyz"), dtype=float)
        first -= float(np.dot(first, normal)) * normal
        first = _unit(first, "width_direction_xyz")
    else:
        candidates = np.eye(3)
        first = min(candidates, key=lambda axis: abs(float(np.dot(axis, normal))))
        first = _unit(first - float(np.dot(first, normal)) * normal, "support_tangent_axis")
    second = _unit(np.cross(normal, first), "support_tangent_axis")
    return first, second


def _ensure_closed_pair(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if np.linalg.norm(first[0] - first[-1]) <= 1.0e-10:
        return first, second
    return np.vstack([first, first[0]]), np.vstack([second, second[0]])


def _resample_closed_pair(
    points_sq: Sequence[Sequence[float]], points_xyz: Sequence[Sequence[float]], count: int
) -> tuple[np.ndarray, np.ndarray]:
    sq = np.asarray(points_sq, dtype=float)
    xyz = np.asarray(points_xyz, dtype=float)
    if np.linalg.norm(sq[0] - sq[-1]) > _EPSILON:
        sq = np.vstack([sq, sq[0]])
        xyz = np.vstack([xyz, xyz[0]])
    cumulative = _cumulative_lengths(sq)
    target = np.linspace(0.0, cumulative[-1], count)
    resampled_sq = np.column_stack([np.interp(target, cumulative, sq[:, axis]) for axis in range(2)])
    resampled_xyz = np.column_stack([np.interp(target, cumulative, xyz[:, axis]) for axis in range(3)])
    return resampled_sq, resampled_xyz


def _resample_closed_polyline(
    points: np.ndarray, count: int, *, include_closure: bool
) -> np.ndarray:
    values = points
    if np.linalg.norm(values[0] - values[-1]) > _EPSILON:
        values = np.vstack([values, values[0]])
    cumulative = _cumulative_lengths(values)
    target = np.linspace(0.0, cumulative[-1], count + int(include_closure), endpoint=include_closure)
    return np.column_stack([np.interp(target, cumulative, values[:, axis]) for axis in range(values.shape[1])])


def _resample_open_polyline(points: np.ndarray, count: int) -> np.ndarray:
    cumulative = _cumulative_lengths(points)
    if cumulative[-1] <= _EPSILON:
        raise ValueError("polyline length must be positive")
    target = np.linspace(0.0, cumulative[-1], count)
    return np.column_stack([np.interp(target, cumulative, points[:, axis]) for axis in range(points.shape[1])])


def _interpolate_polyline_by_fraction(points: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    cumulative = _cumulative_lengths(points)
    target = parameters * cumulative[-1]
    return np.column_stack([np.interp(target, cumulative, points[:, axis]) for axis in range(points.shape[1])])


def _normalize_loop_for_correspondence(points: np.ndarray) -> np.ndarray:
    centered = points - np.mean(points, axis=0)
    scale = math.sqrt(float(np.mean(np.sum(centered**2, axis=1))))
    if scale <= _EPSILON:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed", "section loop has zero local scale"
        )
    return centered / scale


def _orientation_hypothesis_score(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, int, float]:
    best: tuple[float, int, float] | None = None
    reference_tangent = np.roll(reference, -1, axis=0) - np.roll(reference, 1, axis=0)
    reference_tangent /= np.maximum(np.linalg.norm(reference_tangent, axis=1)[:, None], _EPSILON)
    for shift in range(len(candidate)):
        shifted = np.roll(candidate, shift, axis=0)
        point_rms = math.sqrt(float(np.mean(np.sum((reference - shifted) ** 2, axis=1))))
        tangent = np.roll(shifted, -1, axis=0) - np.roll(shifted, 1, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:, None], _EPSILON)
        cosine = np.sum(reference_tangent * tangent, axis=1)
        angles = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        tangent_mismatch = float(np.mean(angles))
        score = point_rms + tangent_mismatch / 180.0
        candidate_score = (score, shift, tangent_mismatch)
        if best is None or candidate_score < best:
            best = candidate_score
    assert best is not None
    return best


def _closed_polyline_self_intersection_count(points: np.ndarray) -> int:
    values = points if np.linalg.norm(points[0] - points[-1]) <= 1.0e-10 else np.vstack([points, points[0]])
    count = 0
    segment_count = len(values) - 1
    for first in range(segment_count):
        for second in range(first + 1, segment_count):
            if second in (first, first + 1) or (first == 0 and second == segment_count - 1):
                continue
            if _segments_intersect_2d(
                values[first], values[first + 1], values[second], values[second + 1], strict=True
            ):
                count += 1
    return count


def _polyline_self_intersections(points: np.ndarray) -> int:
    count = 0
    for first in range(len(points) - 1):
        for second in range(first + 2, len(points) - 1):
            if _segments_intersect_2d(
                points[first], points[first + 1], points[second], points[second + 1], strict=True
            ):
                count += 1
    return count


def _open_polylines_intersect(first: np.ndarray, second: np.ndarray) -> bool:
    for first_start, first_end in zip(first[:-1], first[1:]):
        for second_start, second_end in zip(second[:-1], second[1:]):
            if _segments_intersect_2d(first_start, first_end, second_start, second_end, strict=True):
                return True
    return False


def _segments_intersect_2d(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
    *,
    strict: bool,
) -> bool:
    def cross(first: np.ndarray, second: np.ndarray) -> float:
        return float(first[0] * second[1] - first[1] * second[0])

    first_vector = first_end - first_start
    second_vector = second_end - second_start
    denominator = cross(first_vector, second_vector)
    if abs(denominator) <= 1.0e-12:
        if abs(cross(second_start - first_start, first_vector)) > 1.0e-10:
            return False
        dominant = int(np.argmax(np.abs(first_vector)))
        if abs(float(first_vector[dominant])) <= _EPSILON:
            return float(np.linalg.norm(first_start - second_start)) <= 1.0e-10
        first_min, first_max = sorted((float(first_start[dominant]), float(first_end[dominant])))
        second_min, second_max = sorted((float(second_start[dominant]), float(second_end[dominant])))
        overlap = min(first_max, second_max) - max(first_min, second_min)
        return overlap > (1.0e-9 if strict else -1.0e-9)
    delta = second_start - first_start
    first_parameter = cross(delta, second_vector) / denominator
    second_parameter = cross(delta, first_vector) / denominator
    margin = 1.0e-9 if strict else -1.0e-9
    return margin < first_parameter < 1.0 - margin and margin < second_parameter < 1.0 - margin


def _point_in_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    values = polygon if np.linalg.norm(polygon[0] - polygon[-1]) <= 1.0e-10 else np.vstack([polygon, polygon[0]])
    inside = False
    x, y = float(point[0]), float(point[1])
    for first, second in zip(values[:-1], values[1:]):
        y_crosses = (first[1] > y) != (second[1] > y)
        if y_crosses:
            x_intersection = (second[0] - first[0]) * (y - first[1]) / (second[1] - first[1]) + first[0]
            if x < x_intersection:
                inside = not inside
    return inside


def _edge_fingerprint(points: np.ndarray, face_ids: Sequence[str]) -> tuple[Any, ...]:
    endpoints = sorted((_point_sort_key(points[0]), _point_sort_key(points[-1])))
    return (tuple(endpoints), _round(_polyline_length(points)), tuple(face_ids))


def _edge_sort_key(edge: SectionEdge) -> tuple[Any, ...]:
    points = np.asarray(edge.points_xyz_mm, dtype=float)
    return _edge_fingerprint(points, edge.source_face_ids) + (edge.edge_id,)


def _loop_geometry_key(points: Sequence[Sequence[float]]) -> tuple[Any, ...]:
    values = np.asarray(points, dtype=float)
    return (_point_sort_key(np.mean(values[:-1], axis=0)), _round(_polyline_length(values)))


def _loop_selection_key(
    loop: SectionLoop, sector_center_deg: float | None, allowed: set[str]
) -> tuple[Any, ...]:
    provenance_misses = len(allowed.difference(loop.source_face_ids)) if allowed else 0
    if sector_center_deg is None:
        angle_distance = 0.0
    else:
        points = np.asarray(loop.points_xyz_mm, dtype=float)
        angle = _circular_mean_deg([math.degrees(math.atan2(point[1], point[0])) for point in points[:-1]])
        angle_distance = abs(_wrap_degrees(angle - sector_center_deg))
    return provenance_misses, angle_distance, loop.loop_id


def _angle_in_sector(angle_deg: float, sector: tuple[float, float], tolerance: float) -> bool:
    start = _normalize_degrees(float(sector[0]))
    end = _normalize_degrees(float(sector[1]))
    angle = _normalize_degrees(angle_deg)
    if start <= end:
        return start - tolerance <= angle <= end + tolerance
    return angle >= start - tolerance or angle <= end + tolerance


def _sector_center_deg(sector: tuple[float, float]) -> float:
    start = _normalize_degrees(float(sector[0]))
    extent = (_normalize_degrees(float(sector[1])) - start) % 360.0
    return _normalize_degrees(start + 0.5 * extent)


def _circular_mean_deg(values: Sequence[float]) -> float:
    radians = np.radians(np.asarray(values, dtype=float))
    return _normalize_degrees(math.degrees(math.atan2(float(np.mean(np.sin(radians))), float(np.mean(np.cos(radians))))))


def _canonical_segment_role(value: Any) -> str:
    text = str(value).strip().lower()
    aliases = {
        "pressure": "side_a",
        "pressure_side": "side_a",
        "suction": "side_b",
        "suction_side": "side_b",
        "le": "leading_edge",
        "leading": "leading_edge",
        "leading_edge_closure": "leading_edge",
        "te": "trailing_edge",
        "trailing": "trailing_edge",
        "trailing_edge_closure": "trailing_edge",
    }
    result = aliases.get(text, text)
    if result not in _SEGMENT_ROLES:
        raise ValueError(f"unsupported section segment role: {value!r}")
    return result


def _concatenate_edge_points(edges: Sequence[SectionEdge]) -> np.ndarray:
    chunks = []
    for index, edge in enumerate(edges):
        points = np.asarray(edge.points_xyz_mm, dtype=float)
        chunks.append(points if index == 0 else points[1:])
    return np.vstack(chunks)


def _concatenate_edge_local_points(edges: Sequence[SectionEdge]) -> np.ndarray:
    chunks = []
    for index, edge in enumerate(edges):
        points = np.asarray(edge.points_sq_mm, dtype=float)
        chunks.append(points if index == 0 else points[1:])
    return np.vstack(chunks)


def _concatenate_edge_parameter_uv(edges: Sequence[SectionEdge]) -> np.ndarray:
    face_ids = {edge.source_parameter_face_id for edge in edges}
    if len(face_ids) != 1 or None in face_ids:
        raise SectionRecoveryError(
            "v116_section_loop_correspondence_failed",
            "a direct side chain must remain on one authenticated source face",
            {"source_parameter_face_ids": sorted(str(value) for value in face_ids)},
        )
    chunks = []
    for index, edge in enumerate(edges):
        points = np.asarray(edge.source_face_parameter_uv, dtype=float)
        if points.shape != (len(edge.points_xyz_mm), 2) or np.any(~np.isfinite(points)):
            raise SectionRecoveryError(
                "v116_section_loop_correspondence_failed",
                "source-face UV witnesses do not match the ordered section edge",
                {
                    "edge_id": edge.edge_id,
                    "uv_shape": list(points.shape),
                    "point_count": len(edge.points_xyz_mm),
                },
            )
        chunks.append(points if index == 0 else points[1:])
    return np.vstack(chunks)


def _source_face_parameter_samples(
    face: Any,
    points_xyz_mm: np.ndarray,
    *,
    tolerance: float,
) -> tuple[tuple[tuple[float, float], ...], float]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.ShapeAnalysis import ShapeAnalysis_Surface
        from OCP.gp import gp_Pnt

        adaptor = BRepAdaptor_Surface(_wrapped(face))
        analysis = ShapeAnalysis_Surface(adaptor.Surface().Surface())
        uv_values = []
        residuals = []
        for point in np.asarray(points_xyz_mm, dtype=float):
            uv = analysis.ValueOfUV(
                gp_Pnt(*[float(value) for value in point]),
                max(float(tolerance), 1.0e-9),
            )
            u_value = float(uv.X())
            v_value = float(uv.Y())
            projected = adaptor.Value(u_value, v_value)
            projected_xyz = np.asarray(
                [projected.X(), projected.Y(), projected.Z()], dtype=float
            )
            uv_values.append((u_value, v_value))
            residuals.append(float(np.linalg.norm(projected_xyz - point)))
        return tuple(uv_values), max(residuals, default=0.0)
    except Exception:
        return (), math.inf


def _source_face_bspline_parameter_authority(
    face: Any,
    *,
    source_face_id: str,
    source_edges_by_id: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepTools import BRepTools

        wrapped = _wrapped(face)
        surface = BRepAdaptor_Surface(wrapped).BSpline()
        controls = []
        weights = []
        for u_index in range(1, int(surface.NbUPoles()) + 1):
            control_row = []
            weight_row = []
            for v_index in range(1, int(surface.NbVPoles()) + 1):
                point = surface.Pole(u_index, v_index)
                control_row.append(
                    [float(point.X()), float(point.Y()), float(point.Z())]
                )
                weight_row.append(float(surface.Weight(u_index, v_index)))
            controls.append(control_row)
            weights.append(weight_row)
        bounds = [float(value) for value in BRepTools.UVBounds_s(wrapped)]
        trim_boundary_uv_paths = _source_face_trim_boundary_uv_paths(
            face,
            source_edges_by_id=source_edges_by_id,
        )
        if not trim_boundary_uv_paths:
            return None
        return {
            "authority": "authenticated_step_underlying_rational_bspline_surface",
            "source_face_id": str(source_face_id),
            "coordinate_frame": "source_step_xyz_mm",
            "u_degree": int(surface.UDegree()),
            "v_degree": int(surface.VDegree()),
            "u_knots": [
                float(surface.UKnot(index))
                for index in range(1, int(surface.NbUKnots()) + 1)
            ],
            "v_knots": [
                float(surface.VKnot(index))
                for index in range(1, int(surface.NbVKnots()) + 1)
            ],
            "u_multiplicities": [
                int(surface.UMultiplicity(index))
                for index in range(1, int(surface.NbUKnots()) + 1)
            ],
            "v_multiplicities": [
                int(surface.VMultiplicity(index))
                for index in range(1, int(surface.NbVKnots()) + 1)
            ],
            "control_points_source_xyz_mm": controls,
            "weights": weights,
            "trim_uv_bounds": bounds,
            "trim_boundary_uv_paths": trim_boundary_uv_paths,
            "u_periodic": bool(surface.IsUPeriodic()),
            "v_periodic": bool(surface.IsVPeriodic()),
        }
    except Exception:
        return None


def _source_face_trim_boundary_uv_paths(
    face: Any,
    *,
    source_edges_by_id: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import (
        BRepAdaptor_Curve,
        BRepAdaptor_Curve2d,
        BRepAdaptor_Surface,
    )
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    paths = []
    failed_edge_count = 0
    face_adaptor = BRepAdaptor_Surface(_wrapped(face))
    explorer = TopExp_Explorer(_wrapped(face), TopAbs_EDGE)
    edge_index = 0
    while explorer.More():
        try:
            edge = TopoDS.Edge_s(explorer.Current())
            is_degenerate = bool(BRep_Tool.Degenerated_s(edge))
            is_periodic_parameter_seam = bool(
                not is_degenerate
                and BRep_Tool.IsClosed_s(edge, _wrapped(face))
            )
            source_edge_id = next(
                (
                    str(candidate_id)
                    for candidate_id, candidate in (source_edges_by_id or {}).items()
                    if edge.IsSame(_wrapped(candidate))
                ),
                None,
            )
            if source_edge_id is None and not is_degenerate:
                raise ValueError(
                    "non-degenerate STEP trim edge lacks authenticated source identity"
                )
            adaptor = BRepAdaptor_Curve(edge)
            curve2d = BRepAdaptor_Curve2d(edge, _wrapped(face))
            first = float(adaptor.FirstParameter())
            last = float(adaptor.LastParameter())
            first2d = float(curve2d.FirstParameter())
            last2d = float(curve2d.LastParameter())
            fractions, pcurve_chord_error_bound = (
                _adaptive_face_pcurve_sample_fractions(
                    curve2d,
                    face_adaptor,
                    first_parameter=first2d,
                    last_parameter=last2d,
                    chord_tolerance_mm=0.01,
                    base_segment_count=16,
                    maximum_depth=4,
                )
            )
            source_points = np.asarray(
                [
                    [
                        float(adaptor.Value(float(parameter)).X()),
                        float(adaptor.Value(float(parameter)).Y()),
                        float(adaptor.Value(float(parameter)).Z()),
                    ]
                    for parameter in first + fractions * (last - first)
                ],
                dtype=float,
            )
            uv_points = np.asarray(
                [
                    [
                        float(curve2d.Value(float(parameter)).X()),
                        float(curve2d.Value(float(parameter)).Y()),
                    ]
                    for parameter in first2d + fractions * (last2d - first2d)
                ],
                dtype=float,
            )
            surface_points = np.asarray(
                [
                    [
                        float(face_adaptor.Value(float(uv[0]), float(uv[1])).X()),
                        float(face_adaptor.Value(float(uv[0]), float(uv[1])).Y()),
                        float(face_adaptor.Value(float(uv[0]), float(uv[1])).Z()),
                    ]
                    for uv in uv_points
                ],
                dtype=float,
            )
            forward_endpoint_gap = float(
                np.linalg.norm(surface_points[0] - source_points[0])
                + np.linalg.norm(surface_points[-1] - source_points[-1])
            )
            reverse_endpoint_gap = float(
                np.linalg.norm(surface_points[0] - source_points[-1])
                + np.linalg.norm(surface_points[-1] - source_points[0])
            )
            if reverse_endpoint_gap < forward_endpoint_gap:
                source_points = source_points[::-1].copy()
            residual = max(
                float(
                    np.max(
                        _points_to_polyline_distances(surface_points, source_points)
                    )
                ),
                float(
                    np.max(
                        _points_to_polyline_distances(source_points, surface_points)
                    )
                ),
            )
            source_edge_tolerance = float(BRep_Tool.Tolerance_s(edge))
            vertex_tolerances = []
            vertex_explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
            while vertex_explorer.More():
                vertex_tolerances.append(
                    float(
                        BRep_Tool.Tolerance_s(
                            TopoDS.Vertex_s(vertex_explorer.Current())
                        )
                    )
                )
                vertex_explorer.Next()
            residual_tolerance = max(
                1.0e-3,
                3.0 * source_edge_tolerance,
            )
            if (
                uv_points.shape != (len(source_points), 2)
                or np.any(~np.isfinite(uv_points))
                or not math.isfinite(residual)
                or residual > residual_tolerance
            ):
                raise ValueError("face-specific STEP p-curve residual exceeds tolerance")
            paths.append(
                {
                    "boundary_path_id": f"trim_boundary_{edge_index:03d}",
                    **({"source_edge_id": source_edge_id} if source_edge_id else {}),
                    "topology_boundary_kind": (
                        "degenerate_trim_seam"
                        if is_degenerate
                        else "periodic_parameter_seam"
                        if is_periodic_parameter_seam
                        else "material_shared_edge"
                    ),
                    "source_edge_identity_status": (
                        "DEGENERATE_FACE_LOCAL"
                        if is_degenerate and source_edge_id is None
                        else "AUTHENTICATED"
                    ),
                    "source_points_xyz_mm": source_points.tolist(),
                    "uv": uv_points.tolist(),
                    "projection_residual_max_mm": float(residual),
                    "projection_residual_tolerance_mm": residual_tolerance,
                    "source_pcurve_chord_error_bound_mm": float(
                        pcurve_chord_error_bound
                    ),
                    "source_pcurve_chord_tolerance_mm": 0.01,
                    "source_pcurve_sample_count": int(len(fractions)),
                    "source_edge_tolerance_mm": source_edge_tolerance,
                    "source_vertex_tolerances_mm": vertex_tolerances,
                    "uv_authority": "face_specific_oriented_step_pcurve",
                }
            )
        except Exception:
            failed_edge_count += 1
        edge_index += 1
        explorer.Next()
    return paths if failed_edge_count == 0 and len(paths) == edge_index else []


def _adaptive_face_pcurve_sample_fractions(
    curve2d: Any,
    face_adaptor: Any,
    *,
    first_parameter: float,
    last_parameter: float,
    chord_tolerance_mm: float,
    base_segment_count: int,
    maximum_depth: int,
) -> tuple[np.ndarray, float]:
    value_cache: dict[float, np.ndarray] = {}

    def physical_point(fraction: float) -> np.ndarray:
        key = float(fraction)
        cached = value_cache.get(key)
        if cached is not None:
            return cached
        parameter = first_parameter + key * (last_parameter - first_parameter)
        uv = curve2d.Value(float(parameter))
        point = face_adaptor.Value(float(uv.X()), float(uv.Y()))
        result = np.asarray(
            [float(point.X()), float(point.Y()), float(point.Z())], dtype=float
        )
        value_cache[key] = result
        return result

    def point_to_segment_distance(
        point: np.ndarray, first_point: np.ndarray, last_point: np.ndarray
    ) -> float:
        vector = last_point - first_point
        length_squared = float(np.dot(vector, vector))
        if length_squared <= 1.0e-24:
            return float(np.linalg.norm(point - first_point))
        parameter = float(np.dot(point - first_point, vector) / length_squared)
        projection = first_point + min(1.0, max(0.0, parameter)) * vector
        return float(np.linalg.norm(point - projection))

    retained = set(float(value) for value in np.linspace(0.0, 1.0, base_segment_count + 1))
    pending = [
        (first_fraction, last_fraction, 0)
        for first_fraction, last_fraction in zip(
            sorted(retained)[:-1], sorted(retained)[1:], strict=True
        )
    ]
    maximum_error = 0.0
    while pending:
        first_fraction, last_fraction, depth = pending.pop()
        first_point = physical_point(first_fraction)
        last_point = physical_point(last_fraction)
        probes = np.linspace(first_fraction, last_fraction, 5)[1:-1]
        errors = [
            point_to_segment_distance(
                physical_point(float(probe)), first_point, last_point
            )
            for probe in probes
        ]
        segment_error = max(errors, default=0.0)
        maximum_error = max(maximum_error, segment_error)
        if segment_error <= chord_tolerance_mm:
            continue
        if depth >= maximum_depth:
            raise ValueError(
                "face-specific STEP p-curve exceeds adaptive chord tolerance"
            )
        midpoint = 0.5 * (first_fraction + last_fraction)
        retained.add(midpoint)
        pending.extend(
            (
                (first_fraction, midpoint, depth + 1),
                (midpoint, last_fraction, depth + 1),
            )
        )
    fractions = np.asarray(sorted(retained), dtype=float)
    certified_error = 0.0
    for first_fraction, last_fraction in zip(
        fractions[:-1], fractions[1:], strict=True
    ):
        first_point = physical_point(float(first_fraction))
        last_point = physical_point(float(last_fraction))
        probes = np.linspace(first_fraction, last_fraction, 5)[1:-1]
        certified_error = max(
            certified_error,
            max(
                (
                    point_to_segment_distance(
                        physical_point(float(probe)), first_point, last_point
                    )
                    for probe in probes
                ),
                default=0.0,
            ),
        )
    return fractions, certified_error


def _rotate_closed(points: np.ndarray, start_index: int) -> np.ndarray:
    unique = points[:-1]
    rotated = np.roll(unique, -int(start_index), axis=0)
    return np.vstack([rotated, rotated[0]])


def _deterministic_loop_start(points_sq: np.ndarray) -> int:
    unique = points_sq[:-1]
    return min(range(len(unique)), key=lambda index: (_round(unique[index, 0]), _round(unique[index, 1]), index))


def _signed_polygon_area(points: np.ndarray) -> float:
    values = points[:-1] if np.linalg.norm(points[0] - points[-1]) <= 1.0e-10 else points
    return 0.5 * float(np.sum(values[:, 0] * np.roll(values[:, 1], -1) - np.roll(values[:, 0], -1) * values[:, 1]))


def _circular_index_path(start: int, end: int, count: int) -> list[int]:
    result = [int(start) % count]
    while result[-1] != int(end) % count:
        result.append((result[-1] + 1) % count)
        if len(result) > count + 1:
            raise RuntimeError("circular index path did not terminate")
    return result


def _orient_side_le_to_te(points: np.ndarray) -> np.ndarray:
    return points if points[0, 0] <= points[-1, 0] else points[::-1].copy()


def _chord_parameters(points: np.ndarray) -> np.ndarray:
    cumulative = _cumulative_lengths(points)
    if cumulative[-1] <= _EPSILON:
        raise ValueError("curve samples must span a positive length")
    return cumulative / cumulative[-1]


def _cumulative_lengths(points: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])


def _polyline_length(points: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


def _validate_points(
    points: np.ndarray, dimension: int, name: str, *, minimum: int = 2
) -> None:
    if points.ndim != 2 or points.shape[1] != dimension or len(points) < minimum or not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must contain at least {minimum} finite {dimension}D points")


def _point(value: Sequence[float], dimension: int, name: str) -> tuple[float, ...]:
    array = np.asarray(value, dtype=float)
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite {dimension}D point")
    return tuple(float(item) for item in array)


def _unit(value: Sequence[float] | np.ndarray, name: str) -> np.ndarray:
    vector = np.asarray(value, dtype=float)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite vector")
    length = float(np.linalg.norm(vector))
    if length <= _EPSILON:
        raise ValueError(f"{name} must have positive length")
    return vector / length


def _positive(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _tuple_points(points: np.ndarray | Sequence[Sequence[float]], dimension: int) -> tuple[tuple[float, ...], ...]:
    array = np.asarray(points, dtype=float)
    _validate_points(array, dimension, "points")
    return tuple(tuple(_round(value) for value in point) for point in array)


def _point_sort_key(point: Sequence[float]) -> tuple[float, ...]:
    return tuple(_round(value) for value in point)


def _hkey(value: float) -> float:
    return round(float(value), 14)


def _normalize_degrees(value: float) -> float:
    return float(value) % 360.0


def _wrap_degrees(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _round(value: Any) -> float:
    return round(float(value), _POINT_DIGITS)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _wrapped(shape: Any) -> Any:
    return getattr(shape, "wrapped", shape)
