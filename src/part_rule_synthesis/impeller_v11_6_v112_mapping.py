from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import lru_cache
from statistics import median
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from part_rule_synthesis.impeller_v11_2_canonical import (
    MATH_PARAMETERIZATION,
    canonical_nurbs_from_v11_defaults,
    evaluate_nurbs_curve,
    evaluate_nurbs_surface,
)
from part_rule_synthesis.impeller_runtime_compiler import IMPELLER_PARAMETER_LIMITS
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (
    build_v11_blade_to_blade_loop_family,
)
from part_rule_synthesis.impeller_v11_6_section_recovery import (
    SectionSegmentMeasurement,
)


MEASUREMENT_SCHEMA_VERSION = "v1.1.6_axis_first_measurement_bundle_r1"
MAPPING_VERSION = "v1.1.6_bounded_to_v1.1.2_r1"
GEOMETRY_PATCH_VERSION = "1.1.2"
CANONICAL_STATIONS_H = (0.0, 0.25, 0.5, 0.75, 1.0)
CANONICAL_INPUT_SOURCE = "v116_bounded_measurement_mapping"

RUNTIME_PARAMETER_KEYS = frozenset(
    {
        "blade_count",
        "inlet_radius_mm",
        "exit_radius_mm",
        "inlet_blade_height_mm",
        "outlet_blade_height_mm",
        "hub_curve_height_mm",
        "mounting_bore_radius_mm",
        "blade_wrap_deg",
        "blade_lean_deg",
        "leading_edge_lean_deg",
        "trailing_edge_lean_deg",
        "leading_edge_sweep_mm",
        "trailing_edge_sweep_mm",
        "inlet_blade_angle_deg",
        "outlet_blade_angle_deg",
        "blade_thickness_mm",
        "root_fillet_radius_mm",
        "leading_edge_radius_mm",
        "trailing_edge_radius_mm",
        "tip_edge_radius_mm",
        "hub_wall_thickness_mm",
        "hub_bottom_thickness_mm",
        "hub_top_cap_thickness_mm",
        "hub_chamfer_radius_mm",
        "hood_wall_thickness_mm",
        "hood_chamfer_radius_mm",
    }
)

DEFAULT_KEYS = frozenset(
    {
        "loop_family_id",
        "coordinate_system",
        "span_stations_h",
        "main_blade_count",
        "splitter_blade_count",
        "main_streamwise_interval_s",
        "splitter_streamwise_interval_s",
        "splitter_phase_offset_pitch",
        "splitter_positioning_mode",
        "splitter_passage_fraction",
        "maximum_blade_thickness_mm",
        "average_blade_thickness_mm",
        "root_attachment_width_mm",
        "root_attachment_lift_mm",
        "root_blade_lift_mm",
        "main_flow_turn_q_mm",
        "splitter_flow_turn_q_mm",
        "spanwise_flow_turn_delta_q_mm",
        "midspan_bow_q_mm",
        "leading_edge_cap_roundness",
        "trailing_edge_cap_roundness",
        "tip_attachment_mode",
        "shroud_attachment_width_mm",
        "shroud_blade_inset_mm",
        "segment_control_count_minimums",
        "segment_control_counts",
        "side_sample_count",
        "edge_cap_sample_count",
        "surface_span_sample_count",
        "root_short_direction_sample_count",
        "closed_shroud_short_direction_sample_count",
        "profile_revolve_sample_count",
        "theta_sample_count",
        "hub_solid_radial_sample_count",
        "hub_solid_axial_sample_count",
        "hub_profile_rz_mm",
        "tip_or_shroud_profile_rz_mm",
        "blade_hub_angle_contract_deg",
        "minimum_active_blade_height_mm",
        "enforce_support_profile_contract",
    }
)

_COMMON_MATERIAL_KEYS = frozenset(
    {
        "mounting_bore_radius_mm",
        "root_fillet_radius_mm",
        "tip_edge_radius_mm",
        "hub_wall_thickness_mm",
        "hub_bottom_thickness_mm",
        "hub_top_cap_thickness_mm",
        "hub_chamfer_radius_mm",
    }
)
_CLOSED_MATERIAL_KEYS = frozenset(
    {"hood_wall_thickness_mm", "hood_chamfer_radius_mm"}
)
_SEGMENT_NAMES = frozenset(
    {"side_a", "side_b", "leading_edge", "trailing_edge"}
)
_EPSILON = 1.0e-12
_TASK7_EDGE_FIT_METHOD = "endpoint_constrained_chord_length_least_squares"
_TASK7_EDGE_COORDINATE_FRAME = "section_local_s_q"
_TASK7_EDGE_UNITS = {
    "coordinates": "mm",
    "residual": "mm",
    "parameter": "normalized_0_1",
}
_TASK7_EDGE_PROVENANCE_AUTHORITY = (
    "impeller_v11_6_section_recovery.fit_nurbs_measurement_curve"
)
_CURVE_DISTANCE_METHOD = (
    "deterministic_knot_split_lipschitz_branch_and_bound_upper_certificate"
)
_CURVE_DISTANCE_CONVERGENCE_MM = 0.0025
_CURVE_DISTANCE_MAX_SUBDIVISIONS = 32768
_TASK3_RAW_FRAME_KEYS = frozenset(
    {
        "method",
        "source_axis_origin_mm",
        "source_axis_direction",
        "source_to_canonical_matrix",
        "scale",
        "primary_icp_applied",
        "handedness",
        "axis_consensus",
        "candidate_scores",
        "outer_radius_mm",
        "main_bore_radius_mm",
        "axial_extent_mm",
        "central_cylinder_radii_mm",
    }
)


class V112MappingError(ValueError):
    def __init__(
        self,
        reason: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


@dataclass(frozen=True)
class _BoundedSolveResult:
    x: np.ndarray
    success: bool
    status: int
    message: str
    nfev: int
    cost: float
    optimality: float
    groups: tuple[dict[str, Any], ...]
    current_objective: str | None = None
    current_objective_value: float | None = None


@dataclass(frozen=True)
class V112MappingTolerances:
    hub_rms_floor_mm: float = 0.10
    hub_rms_diameter_ratio: float = 0.001
    tip_rms_floor_mm: float = 0.20
    tip_rms_diameter_ratio: float = 0.002
    thickness_rms_floor_mm: float = 0.15
    thickness_rms_mean_ratio: float = 0.03
    camber_rms_floor_mm: float = 0.20
    camber_rms_mean_thickness_ratio: float = 0.04
    pose_rms_limit_deg: float = 1.0
    pose_max_limit_deg: float = 3.0
    edge_hausdorff_floor_mm: float = 0.20
    edge_hausdorff_mean_thickness_ratio: float = 0.05
    attachment_relative_limit: float = 0.10

    @classmethod
    def from_value(
        cls, value: V112MappingTolerances | Mapping[str, Any]
    ) -> V112MappingTolerances:
        if isinstance(value, cls):
            result = value
        elif isinstance(value, Mapping):
            _require_keys(value, set(cls.__dataclass_fields__), set(), "tolerances")
            result = cls(**{key: float(item) for key, item in value.items()})
        else:
            raise V112MappingError(
                "v116_v112_measurement_schema_invalid",
                "tolerances must be V112MappingTolerances or a mapping",
            )
        for key, number in asdict(result).items():
            if not math.isfinite(number) or number <= 0.0:
                raise V112MappingError(
                    "v116_v112_measurement_schema_invalid",
                    f"tolerances.{key} must be finite and positive",
                )
        return result

    def as_contract(
        self, outer_diameter_mm: float, mean_thickness_mm: float
    ) -> dict[str, float]:
        return _tolerance_contract(self, outer_diameter_mm, mean_thickness_mm)

    def promotion_contract(self) -> dict[str, Any]:
        specification = asdict(type(self)())
        supplied = asdict(self)
        loosened = sorted(
            key
            for key, value in supplied.items()
            if value > specification[key] + 1.0e-15
        )
        tightened = sorted(
            key
            for key, value in supplied.items()
            if value < specification[key] - 1.0e-15
        )
        return {
            "promotable": not loosened,
            "policy": "specification_values_are_promotion_maxima",
            "loosened_fields": loosened,
            "tightened_fields": tightened,
            "diagnostic_only_when_loosened": True,
        }


def adapt_task3_frame_for_mapping(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Project the strict Task 3 frame result into the mapping frame contract."""

    raw = _require_mapping(frame, "frame")
    _require_keys(raw, set(_TASK3_RAW_FRAME_KEYS), set(_TASK3_RAW_FRAME_KEYS), "frame")
    consensus = _require_mapping(raw["axis_consensus"], "frame.axis_consensus")
    selected = _require_mapping(
        consensus.get("selected_cluster"),
        "frame.axis_consensus.selected_cluster",
    )
    selected_units = _require_mapping(
        selected.get("units"), "frame.axis_consensus.selected_cluster.units"
    )
    selected_tolerance = _require_mapping(
        selected.get("tolerance"),
        "frame.axis_consensus.selected_cluster.tolerance",
    )
    if selected.get("coordinate_frame") != "source_cartesian_mm":
        _schema_error(
            "frame.axis_consensus.selected_cluster must use source_cartesian_mm"
        )
    if selected_units.get("linear") != "mm":
        _schema_error(
            "frame.axis_consensus.selected_cluster linear units must be mm"
        )
    source_tolerance_mm = _positive(
        selected_tolerance.get("line_distance_mm"),
        "frame.axis_consensus.selected_cluster.tolerance.line_distance_mm",
    )
    adapted = deepcopy(dict(raw))
    adapted.update(
        {
            "coordinate_system": "canonical_axis_frame_xyz_mm",
            "units": "mm",
            "source_tolerance_mm": source_tolerance_mm,
        }
    )
    return adapted


def adapt_task7_segment_for_mapping(
    segment: SectionSegmentMeasurement,
    *,
    fit_tolerance_mm: float,
) -> dict[str, Any]:
    """Project a strict Task 7 edge measurement into the mapping segment contract."""

    if not isinstance(segment, SectionSegmentMeasurement):
        _schema_error("segment must be a Task 7 SectionSegmentMeasurement")
    if segment.name not in {"leading_edge", "trailing_edge"}:
        _schema_error("Task 7 mapping adapters accept only leading_edge or trailing_edge")
    fit = segment.fit
    if fit.segment_name != segment.name:
        _schema_error("Task 7 segment and NURBS fit names must match")
    source_edge_ids = sorted(set(segment.source_edge_ids))
    source_face_ids = sorted(set(segment.source_face_ids))
    if not source_edge_ids or source_edge_ids != sorted(set(fit.source_edge_ids)):
        _schema_error("Task 7 segment and NURBS fit source edge ids must match")
    if set(source_edge_ids) & set(source_face_ids):
        _schema_error("Task 7 source face and edge ids must remain distinct")
    if fit.measurement_target_only is not True or fit.constructor_direct_curve_mode is not False:
        _schema_error("Task 7 edge fit must remain measurement-only")
    tolerance_mm = _positive(fit_tolerance_mm, "fit_tolerance_mm")
    residual = {
        "rms_mm": float(fit.residual_rms_mm),
        "maximum_mm": float(fit.residual_max_mm),
        "source_to_fit_maximum_mm": float(fit.residual_source_to_fit_max_sq_mm),
        "fit_to_source_maximum_mm": float(fit.residual_fit_to_source_max_sq_mm),
    }
    if residual["maximum_mm"] > tolerance_mm + 1.0e-12:
        _schema_error("Task 7 edge fit residual exceeds fit_tolerance_mm")

    source_points = [list(point) for point in segment.points_sq_mm]
    target: dict[str, Any] = {
        "degree": int(fit.degree),
        "knots": list(fit.knots),
        "weights": [1.0] * len(fit.control_points_sq_mm),
        "control_points_local_mm": [
            list(point) for point in fit.control_points_sq_mm
        ],
        "sample_points_local_mm": [],
        "measurement_target_only": True,
        "constructor_direct_curve_mode": False,
    }
    sample_count = max(9, int(fit.fit_sample_count))
    target["sample_points_local_mm"] = _sample_source_nurbs_curve(
        target, sample_count
    )
    nurbs_digest = hashlib.sha256(
        _authoritative_nurbs_json(target).encode("utf-8")
    ).hexdigest()
    target["fit_evidence"] = {
        "method": _TASK7_EDGE_FIT_METHOD,
        "source_edge_ids": source_edge_ids,
        "source_points_local_mm": deepcopy(source_points),
        "residual": residual,
        "tolerance_mm": tolerance_mm,
        "coordinate_frame": _TASK7_EDGE_COORDINATE_FRAME,
        "units": deepcopy(_TASK7_EDGE_UNITS),
        "provenance": {
            "authority": _TASK7_EDGE_PROVENANCE_AUTHORITY,
            "source_segment_name": segment.name,
            "source_edge_ids": source_edge_ids,
            "source_points_sha256": _stable_hash(source_points),
            "nurbs_authority_sha256": nurbs_digest,
        },
    }
    return {
        "points_sq_mm": source_points,
        "source_ids": sorted(set(source_edge_ids) | set(source_face_ids)),
        "source_edge_ids": source_edge_ids,
        "source_face_ids": source_face_ids,
        "nurbs_target": target,
    }


def map_measurements_to_v112(
    measurements: Mapping[str, Any],
    *,
    tolerances: V112MappingTolerances | Mapping[str, Any],
    initial_guess: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map axis-first STEP measurements into the frozen V1.1.2 constructor domain."""

    policy = V112MappingTolerances.from_value(tolerances)
    promotion = policy.promotion_contract()
    try:
        bundle = _validate_and_normalize_bundle(measurements)
    except V112MappingError as exc:
        exc.details = {
            **exc.details,
            "promotion": promotion,
            "tolerances": asdict(policy),
            "input_frame_unvalidated": deepcopy(measurements.get("frame"))
            if isinstance(measurements, Mapping)
            else None,
            "input_provenance_unvalidated": deepcopy(
                measurements.get("provenance")
            )
            if isinstance(measurements, Mapping)
            else None,
        }
        raise
    context = _MappingContext(bundle, policy)
    bounds = context.bounds_contract()
    try:
        guess = _validate_initial_guess(initial_guess)
    except V112MappingError as exc:
        exc.details = _rejection_evidence(
            bundle=bundle,
            promotion=promotion,
            tolerances=context.tolerance_contract,
            solver={
                "method": "scipy.optimize.least_squares.trf",
                "status": "NOT_RUN",
                "reason": "initial_guess_validation_failed",
            },
            bounds=bounds,
            existing=exc.details,
        )
        raise

    x0 = context.initial_vector(guess)
    try:
        solution = context.solve(x0)
    except Exception as caught:
        exc = _solver_mapping_error(caught)
        partial = _solve_partial_evidence(exc.details, x0)
        _complete_solver_rejection(
            exc=exc,
            context=context,
            bundle=bundle,
            promotion=promotion,
            bounds=bounds,
            initial=x0,
            partial=partial,
            initial_guess_supplied=initial_guess is not None,
        )
        if exc is caught:
            raise
        raise exc from caught
    solver = _solver_contract(solution, initial_guess is not None)
    if not solution.success or not np.all(np.isfinite(solution.x)):
        exc = V112MappingError(
            "v116_v112_mapping_solver_failed",
            "bounded V1.1.2 least-squares mapping did not converge",
        )
        _complete_solver_rejection(
            exc=exc,
            context=context,
            bundle=bundle,
            promotion=promotion,
            bounds=bounds,
            initial=x0,
            partial=_solve_result_partial(solution),
            initial_guess_supplied=initial_guess is not None,
            solver=solver,
        )
        raise exc

    parameters, defaults = context.constructor_inputs(solution.x)
    candidate: dict[str, Any] = {
        "parameters": deepcopy(parameters),
        "resolved_blade_to_blade_loop_family_defaults": deepcopy(defaults),
    }
    try:
        _assert_output_whitelists(parameters, defaults)
        _assert_output_limits_and_material_domain(
            parameters, defaults, bundle["topology"]
        )
        canonical = canonical_nurbs_from_v11_defaults(
            parameters,
            defaults,
            source=CANONICAL_INPUT_SOURCE,
        )
    except V112MappingError as exc:
        exc.details = _rejection_evidence(
            bundle=bundle,
            promotion=promotion,
            tolerances=context.tolerance_contract,
            solver=solver,
            bounds=bounds,
            candidate=candidate,
            existing=exc.details,
        )
        raise
    if canonical.get("canonical_payload_version") != GEOMETRY_PATCH_VERSION:
        raise V112MappingError(
            "v116_v112_canonical_patch_mismatch",
            "the regenerated canonical payload is not geometry patch 1.1.2",
            _rejection_evidence(
                bundle=bundle,
                promotion=promotion,
                tolerances=context.tolerance_contract,
                solver=solver,
                bounds=bounds,
                candidate=candidate,
            ),
        )

    objective_terms = context.objective_terms(parameters, defaults, canonical)
    five_station = context.five_station_report(canonical, parameters, defaults)
    canonical_hash = _stable_hash(canonical)
    candidate.update(
        {
            "regenerated_canonical_payload": canonical,
            "canonical_payload_hash_sha256": canonical_hash,
            "five_station_resampling_report": five_station,
        }
    )
    failed_terms = [
        name
        for name, term in objective_terms.items()
        if term["gate"]["status"] != "PASS"
    ]
    passed_terms = [name for name in objective_terms if name not in failed_terms]
    if failed_terms:
        raise V112MappingError(
            "v116_v112_mapping_residual_exceeded",
            "measured STEP evidence is outside the bounded V1.1.2 representation",
            _rejection_evidence(
                bundle=bundle,
                promotion=promotion,
                tolerances=context.tolerance_contract,
                solver=solver,
                bounds=bounds,
                candidate=candidate,
                objective_terms=objective_terms,
                passed_terms=passed_terms,
                failed_terms=failed_terms,
            ),
        )

    regenerated = canonical_nurbs_from_v11_defaults(
        deepcopy(parameters),
        deepcopy(defaults),
        source=CANONICAL_INPUT_SOURCE,
    )
    if _stable_hash(regenerated) != canonical_hash:
        raise V112MappingError(
            "v116_v112_canonical_hash_mismatch",
            "regenerating the V1.1.2 canonical payload changed its hash",
            _rejection_evidence(
                bundle=bundle,
                promotion=promotion,
                tolerances=context.tolerance_contract,
                solver=solver,
                bounds=bounds,
                candidate=candidate,
                objective_terms=objective_terms,
                passed_terms=list(objective_terms),
            ),
        )
    constructor_hash = _stable_hash(
        {
            "geometry_patch_version": GEOMETRY_PATCH_VERSION,
            "parameters": parameters,
            "defaults": defaults,
            "canonical_payload": canonical,
        }
    )

    return {
        "mapping_status": "PASS" if promotion["promotable"] else "DIAGNOSTIC_ONLY",
        "promotion": promotion,
        "mapping_version": MAPPING_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "geometry_patch_version": GEOMETRY_PATCH_VERSION,
        "math_parameterization": MATH_PARAMETERIZATION,
        "parameters": parameters,
        "resolved_blade_to_blade_loop_family_defaults": defaults,
        "regenerated_canonical_payload": canonical,
        "canonical_payload_hash_sha256": canonical_hash,
        "constructor_input_hash_sha256": constructor_hash,
        "five_station_resampling_report": five_station,
        "objective_terms": objective_terms,
        "tolerances": context.tolerance_contract,
        "solver": solver,
        "bounds": bounds,
        "representational_losses": [
            {
                "feature": "leading_and_trailing_edge_source_nurbs",
                "source_role": "measurement_target_only",
                "v112_representation": "thickness_driven_nurbs_cap_intent",
                "direct_curve_constructor_mode": False,
            },
            {
                "feature": "cap_roundness",
                "policy": "frozen_v1_1_2_release_default",
                "leading_edge_cap_roundness": defaults["leading_edge_cap_roundness"],
                "trailing_edge_cap_roundness": defaults["trailing_edge_cap_roundness"],
                "geometry_sensitivity": "not_independently_identifiable_in_v1_1_2",
            },
            {
                "feature": "adaptive_span_lattice",
                "source_station_count_by_family": {
                    name: len(family["stations"])
                    for name, family in bundle["section_families"].items()
                },
                "constructor_stations_h": list(CANONICAL_STATIONS_H),
            },
        ],
        "provenance": {
            "source": deepcopy(bundle["provenance"]),
            "frame": deepcopy(bundle["frame"]),
            "measurement_source_ids": context.all_source_ids,
            "initial_guess_source_preset_id": (
                None if guess is None else guess.get("source_preset_id")
            ),
            "canonical_hash_excludes_source_identity": True,
        },
    }


def _solver_contract(
    solution: _BoundedSolveResult, initial_guess_supplied: bool
) -> dict[str, Any]:
    return {
        "method": "scipy.optimize.least_squares.trf",
        "success": bool(solution.success),
        "status": int(solution.status),
        "message": str(solution.message),
        "nfev": int(solution.nfev),
        "cost": _round(float(solution.cost), 12),
        "optimality": _round(float(solution.optimality), 12),
        "station_quadrature_normalized": True,
        "initial_guess_role": "solver_initialization_only",
        "initial_guess_supplied": initial_guess_supplied,
        "groups": list(solution.groups),
        "current_vector": np.asarray(solution.x, dtype=float).tolist(),
        "current_objective": solution.current_objective,
        "current_objective_value": solution.current_objective_value,
    }


def _solve_partial_evidence(
    details: Mapping[str, Any], initial: np.ndarray
) -> dict[str, Any]:
    raw = details.get("solve_partial", {})
    partial = deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
    partial.setdefault("completed_groups", [])
    partial.setdefault(
        "current_objective",
        _next_solver_objective(partial["completed_groups"]),
    )
    partial.setdefault("vector", np.asarray(initial, dtype=float).tolist())
    partial.setdefault("nfev", 0)
    partial.setdefault("cost", 0.0)
    partial.setdefault("optimality", 0.0)
    partial.setdefault("current_objective_value", partial["cost"])
    return partial


def _solve_result_partial(solution: _BoundedSolveResult) -> dict[str, Any]:
    completed_groups = deepcopy(list(solution.groups))
    current_objective = solution.current_objective or _next_solver_objective(
        completed_groups
    )
    objective_value = (
        float(solution.cost)
        if solution.current_objective_value is None
        else float(solution.current_objective_value)
    )
    return {
        "current_objective": current_objective,
        "completed_groups": completed_groups,
        "vector": np.asarray(solution.x, dtype=float).tolist(),
        "nfev": int(solution.nfev),
        "cost": float(solution.cost),
        "optimality": float(solution.optimality),
        "current_objective_value": objective_value,
    }


def _next_solver_objective(completed_groups: Sequence[Mapping[str, Any]]) -> str:
    completed = {str(group.get("objective")) for group in completed_groups}
    return next(
        (
            role
            for role in ("camber", "normal_thickness", "pose")
            if role not in completed
        ),
        "solver",
    )


def _solver_mapping_error(caught: Exception) -> V112MappingError:
    if isinstance(caught, V112MappingError):
        return caught
    return V112MappingError(
        "v116_v112_mapping_solver_exception",
        "bounded V1.1.2 least-squares mapping raised an unexpected exception",
        {
            "exception_type": f"{type(caught).__module__}.{type(caught).__qualname__}",
            "exception_message": str(caught),
        },
    )


def _solver_exception_contract(
    exc: V112MappingError,
    partial: Mapping[str, Any],
    initial_guess_supplied: bool,
) -> dict[str, Any]:
    return {
        "method": "scipy.optimize.least_squares.trf",
        "success": False,
        "status": "EXCEPTION",
        "message": str(exc),
        "reason": exc.reason,
        "nfev": int(partial["nfev"]),
        "cost": _round(float(partial["cost"]), 12),
        "optimality": _round(float(partial["optimality"]), 12),
        "station_quadrature_normalized": True,
        "initial_guess_role": "solver_initialization_only",
        "initial_guess_supplied": initial_guess_supplied,
        "groups": deepcopy(list(partial["completed_groups"])),
        "current_objective": str(partial["current_objective"]),
        "current_objective_value": _round(
            float(partial["current_objective_value"]), 12
        ),
        "current_vector": deepcopy(list(partial["vector"])),
        "partial_result_retained": True,
    }


def _complete_solver_rejection(
    *,
    exc: V112MappingError,
    context: _MappingContext,
    bundle: Mapping[str, Any],
    promotion: Mapping[str, Any],
    bounds: Mapping[str, Any],
    initial: np.ndarray,
    partial: Mapping[str, Any],
    initial_guess_supplied: bool,
    solver: Mapping[str, Any] | None = None,
) -> None:
    objective_terms = context.solver_failure_terms(partial, exc)
    passed_terms = [
        name
        for name, term in objective_terms.items()
        if term["gate"]["status"] == "PASS"
    ]
    failed_terms = [name for name in objective_terms if name not in passed_terms]
    exc.details = _rejection_evidence(
        bundle=bundle,
        promotion=promotion,
        tolerances=context.tolerance_contract,
        solver=(
            deepcopy(dict(solver))
            if solver is not None
            else _solver_exception_contract(
                exc, partial, initial_guess_supplied
            )
        ),
        bounds=bounds,
        candidate=context.partial_solver_candidate(initial, partial),
        objective_terms=objective_terms,
        passed_terms=passed_terms,
        failed_terms=failed_terms,
        existing=exc.details,
    )


def _rejection_evidence(
    *,
    bundle: Mapping[str, Any],
    promotion: Mapping[str, Any],
    tolerances: Mapping[str, Any],
    solver: Mapping[str, Any],
    bounds: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
    objective_terms: Mapping[str, Any] | None = None,
    passed_terms: Sequence[str] = (),
    failed_terms: Sequence[str] = (),
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    terms = dict(objective_terms or {})
    passed = list(passed_terms)
    failed = list(failed_terms)
    return {
        **deepcopy(dict(existing or {})),
        "frame": deepcopy(bundle["frame"]),
        "provenance": deepcopy(bundle["provenance"]),
        "promotion": deepcopy(dict(promotion)),
        "tolerances": deepcopy(dict(tolerances)),
        "solver": deepcopy(dict(solver)),
        "bounds": deepcopy(dict(bounds)),
        "candidate": deepcopy(dict(candidate or {})),
        "objective_terms": deepcopy(terms),
        "passed_terms": passed,
        "failed_terms": failed,
        "passing_terms": {name: deepcopy(terms[name]) for name in passed},
        "failing_terms": {name: deepcopy(terms[name]) for name in failed},
    }


def _tolerance_contract(
    policy: V112MappingTolerances, outer_diameter_mm: float, mean_thickness_mm: float
) -> dict[str, float]:
    values = asdict(policy)
    values.update(
        {
            "hub_rms_limit_mm": max(
                policy.hub_rms_floor_mm,
                policy.hub_rms_diameter_ratio * outer_diameter_mm,
            ),
            "tip_rms_limit_mm": max(
                policy.tip_rms_floor_mm,
                policy.tip_rms_diameter_ratio * outer_diameter_mm,
            ),
            "thickness_rms_limit_mm": max(
                policy.thickness_rms_floor_mm,
                policy.thickness_rms_mean_ratio * mean_thickness_mm,
            ),
            "camber_rms_limit_mm": max(
                policy.camber_rms_floor_mm,
                policy.camber_rms_mean_thickness_ratio * mean_thickness_mm,
            ),
            "edge_hausdorff_limit_mm": max(
                policy.edge_hausdorff_floor_mm,
                policy.edge_hausdorff_mean_thickness_ratio * mean_thickness_mm,
            ),
        }
    )
    return {key: _round(value, 12) for key, value in values.items()}


class _MappingContext:
    _VARIABLE_NAMES = (
        "main_flow_turn_q_mm",
        "spanwise_flow_turn_delta_q_mm",
        "midspan_bow_q_mm",
        "average_blade_thickness_mm",
        "maximum_thickness_delta_mm",
        "blade_wrap_deg",
        "blade_lean_deg",
        "leading_edge_lean_deg",
        "trailing_edge_lean_deg",
        "leading_edge_sweep_mm",
        "trailing_edge_sweep_mm",
    )

    def __init__(
        self, bundle: dict[str, Any], policy: V112MappingTolerances
    ) -> None:
        self.bundle = bundle
        self.policy = policy
        self.topology = bundle["topology"]
        self.outer_diameter_mm = float(self.topology["outer_diameter_mm"])
        self.mean_thickness_mm = _fixed_measurement_mean_thickness(bundle)
        self.tolerance_contract = policy.as_contract(
            self.outer_diameter_mm, self.mean_thickness_mm
        )
        self.tolerance_contract.update(
            {
                "mean_thickness_mm": _round(self.mean_thickness_mm, 12),
                "mean_thickness_source": "fixed_v1_1_2_five_station_span_quadrature",
                "span_quadrature_rule": "trapezoidal_endpoint_half_weight",
                "span_quadrature_weights": _station_quadrature_weights(
                    [{"h": h} for h in CANONICAL_STATIONS_H]
                ),
            }
        )
        self.lower_bounds = np.asarray(
            [1.0e-6, -5000.0, -5000.0, 1.0, 0.0, -240.0, -60.0, -60.0, -60.0, -300.0, -300.0],
            dtype=float,
        )
        self.upper_bounds = np.asarray(
            [5000.0, 5000.0, 5000.0, 120.0, 119.0, 240.0, 60.0, 60.0, 60.0, 300.0, 300.0],
            dtype=float,
        )
        self.all_source_ids = sorted(
            {
                source_id
                for source_id in _collect_source_ids(bundle)
            }
        )

    def initial_vector(self, guess: dict[str, Any] | None) -> np.ndarray:
        main_stations = _fixed_solver_stations(
            self.bundle["section_families"]["main"]["stations"]
        )
        endpoint_q = [
            max(station["camber"]["samples"], key=lambda sample: sample["s"])["q_mm"]
            for station in main_stations
        ]
        root_q = endpoint_q[0]
        tip_q = endpoint_q[-1]
        thickness_values = [
            sample["thickness_mm"]
            for family in self.bundle["section_families"].values()
            for station in _fixed_solver_stations(family["stations"])
            for sample in station["normal_thickness"]["samples"]
        ]
        values = {
            "main_flow_turn_q_mm": max(float(np.mean(endpoint_q)), 1.0e-6),
            "spanwise_flow_turn_delta_q_mm": float(tip_q - root_q),
            "midspan_bow_q_mm": 0.0,
            "average_blade_thickness_mm": float(np.mean(thickness_values)),
            "maximum_thickness_delta_mm": max(
                float(np.max(thickness_values) - np.mean(thickness_values)), 0.0
            ),
            "blade_wrap_deg": 0.0,
            "blade_lean_deg": 0.0,
            "leading_edge_lean_deg": 0.0,
            "trailing_edge_lean_deg": 0.0,
            "leading_edge_sweep_mm": 0.0,
            "trailing_edge_sweep_mm": 0.0,
        }
        del guess
        if abs(values["midspan_bow_q_mm"]) < 0.5:
            values["midspan_bow_q_mm"] = 1.0
        values.update(self._measured_pose_initialization())
        vector = np.asarray([values[name] for name in self._VARIABLE_NAMES], dtype=float)
        return np.minimum(np.maximum(vector, self.lower_bounds), self.upper_bounds)

    def _measured_pose_initialization(self) -> dict[str, float]:
        stations = _fixed_solver_stations(
            self.bundle["section_families"]["main"]["stations"]
        )
        root = min(stations, key=lambda station: station["h"])
        tip = max(stations, key=lambda station: station["h"])
        target = np.asarray(
            [
                _interpolate_samples(root["pose"]["samples"], 0.0, "theta_deg"),
                _interpolate_samples(tip["pose"]["samples"], 0.0, "theta_deg"),
                _interpolate_samples(root["pose"]["samples"], 0.5, "theta_deg"),
                _interpolate_samples(tip["pose"]["samples"], 0.5, "theta_deg"),
                _interpolate_samples(root["pose"]["samples"], 1.0, "theta_deg"),
                _interpolate_samples(tip["pose"]["samples"], 1.0, "theta_deg"),
            ],
            dtype=float,
        )
        coefficients = np.asarray(
            [
                [0.0, 0.0, 1.0, 0.0, 0.05, 0.0],
                [0.0, 1.0, 1.0, 0.0, 0.0, 0.0],
                [-0.42, 1.0, 0.0, 0.0, 0.0, 0.0],
                [-0.32, 1.0, 0.0, 0.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0, 0.0, 0.0, 0.05],
                [-0.83, 0.0, 0.0, 1.0, 0.0, 0.0],
            ],
            dtype=float,
        )
        solved, _, _, _ = np.linalg.lstsq(coefficients, target, rcond=None)
        return dict(
            zip(
                (
                    "blade_wrap_deg",
                    "blade_lean_deg",
                    "leading_edge_lean_deg",
                    "trailing_edge_lean_deg",
                    "leading_edge_sweep_mm",
                    "trailing_edge_sweep_mm",
                ),
                (float(value) for value in solved),
            )
        )

    def solve(self, initial: np.ndarray) -> _BoundedSolveResult:
        vector = np.asarray(initial, dtype=float).copy()
        groups = (
            ("camber", (0, 1, 2)),
            ("normal_thickness", (3, 4)),
            ("pose", (5, 6, 7, 8, 9, 10)),
        )
        reports: list[dict[str, Any]] = []
        total_cost = 0.0
        maximum_optimality = 0.0
        total_nfev = 0
        for role, indices in groups:
            index_array = np.asarray(indices, dtype=int)
            try:
                solved = self._solve_group(role, index_array, vector)
            except Exception as caught:
                exc = _solver_mapping_error(caught)
                exc.details = {
                    **exc.details,
                    "solve_partial": {
                        "current_objective": role,
                        "completed_groups": deepcopy(reports),
                        "vector": vector.tolist(),
                        "nfev": total_nfev,
                        "cost": total_cost,
                        "optimality": maximum_optimality,
                        "current_objective_value": total_cost,
                    },
                }
                if exc is caught:
                    raise
                raise exc from caught
            if not solved.success or not np.all(np.isfinite(solved.x)):
                failure_vector = vector.copy()
                failure_subvector = np.asarray(solved.x, dtype=float)
                if failure_subvector.shape == index_array.shape and np.all(
                    np.isfinite(failure_subvector)
                ):
                    failure_vector[index_array] = failure_subvector
                return _BoundedSolveResult(
                    x=failure_vector,
                    success=False,
                    status=int(solved.status),
                    message=f"{role}: {solved.message}",
                    nfev=total_nfev + int(solved.nfev),
                    cost=total_cost + float(solved.cost),
                    optimality=max(maximum_optimality, float(solved.optimality)),
                    groups=tuple(reports),
                    current_objective=role,
                    current_objective_value=float(solved.cost),
                )
            vector[index_array] = solved.x
            total_cost += float(solved.cost)
            total_nfev += int(solved.nfev)
            maximum_optimality = max(maximum_optimality, float(solved.optimality))
            reports.append(
                {
                    "objective": role,
                    "variable_names": [self._VARIABLE_NAMES[index] for index in indices],
                    "nfev": int(solved.nfev),
                    "cost": _round(float(solved.cost), 12),
                    "status": int(solved.status),
                }
            )
        return _BoundedSolveResult(
            x=vector,
            success=True,
            status=1,
            message="independent bounded objective blocks converged",
            nfev=total_nfev,
            cost=total_cost,
            optimality=maximum_optimality,
            groups=tuple(reports),
        )

    def _solve_group(
        self, role: str, index_array: np.ndarray, vector: np.ndarray
    ) -> Any:
        if role == "pose":
            matrix, target = self._pose_linear_system(vector, index_array)

            def residual(subvector: np.ndarray) -> np.ndarray:
                return matrix @ subvector - target

        else:

            def residual(subvector: np.ndarray) -> np.ndarray:
                candidate = vector.copy()
                candidate[index_array] = subvector
                return self.residual_vector(candidate, roles={role})

        return least_squares(
            residual,
            vector[index_array],
            bounds=(self.lower_bounds[index_array], self.upper_bounds[index_array]),
            method="trf",
            x_scale="jac",
            ftol=1.0e-12,
            xtol=1.0e-12,
            gtol=1.0e-12,
            diff_step=1.0e-4,
            max_nfev=400,
        )

    def partial_solver_candidate(
        self, initial: np.ndarray, partial: Mapping[str, Any]
    ) -> dict[str, Any]:
        vector = np.asarray(partial["vector"], dtype=float)
        candidate: dict[str, Any] = {
            "stage": "bounded_solver",
            "variable_names": list(self._VARIABLE_NAMES),
            "initial_vector": np.asarray(initial, dtype=float).tolist(),
            "partial_vector": vector.tolist(),
            "partial_values": dict(zip(self._VARIABLE_NAMES, vector.tolist())),
            "completed_groups": deepcopy(list(partial["completed_groups"])),
            "current_objective": str(partial["current_objective"]),
        }
        try:
            parameters, defaults = self.constructor_inputs(vector)
        except V112MappingError as exc:
            candidate["constructor_input_error"] = {
                "reason": exc.reason,
                "message": str(exc),
                "details": deepcopy(exc.details),
            }
        else:
            candidate["parameters"] = parameters
            candidate["resolved_blade_to_blade_loop_family_defaults"] = defaults
        return candidate

    def solver_failure_terms(
        self, partial: Mapping[str, Any], exc: V112MappingError
    ) -> dict[str, Any]:
        terms: dict[str, Any] = {}
        for report in partial["completed_groups"]:
            role = str(report["objective"])
            terms[role] = _term(
                target={"objective": role, "completion": "bounded_convergence"},
                fitted=deepcopy(report),
                unit="normalized_residual",
                weight="independent_bounded_objective_block",
                residual={
                    "cost": report["cost"],
                    "nfev": report["nfev"],
                },
                gate={"solver_completed": True, "status": "PASS"},
                source_ids=_source_ids_for_role(self.bundle, role),
            )
        failed_role = str(partial["current_objective"])
        terms[failed_role] = _term(
            target={"objective": failed_role, "completion": "bounded_convergence"},
            fitted={
                "completed": False,
                "partial_vector_retained": True,
            },
            unit="normalized_residual",
            weight="independent_bounded_objective_block",
            residual={
                "reason": exc.reason,
                "message": str(exc),
                "objective_value": partial["current_objective_value"],
            },
            gate={"solver_completed": False, "status": "FAIL"},
            source_ids=(
                _source_ids_for_role(self.bundle, failed_role)
                if failed_role in {"camber", "normal_thickness", "pose"}
                else self.all_source_ids
            ),
        )
        return self._self_contained_promotion_terms(terms)

    def _pose_linear_system(
        self, vector: np.ndarray, pose_indices: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        base = vector.copy()
        base[pose_indices] = 0.0
        base_parameters, base_defaults = self.constructor_inputs(base, rounded=False)
        base_field = canonical_nurbs_from_v11_defaults(
            base_parameters, base_defaults, source=CANONICAL_INPUT_SOURCE
        )["pose_field"]
        basis_fields = []
        for index in pose_indices:
            probe = base.copy()
            probe[index] = 1.0
            parameters, defaults = self.constructor_inputs(probe, rounded=False)
            basis_fields.append(
                canonical_nurbs_from_v11_defaults(
                    parameters, defaults, source=CANONICAL_INPUT_SOURCE
                )["pose_field"]
            )

        rows: list[list[float]] = []
        targets: list[float] = []
        family_count = len(self.bundle["section_families"])
        for family in self.bundle["section_families"].values():
            solver_stations = _fixed_solver_stations(family["stations"])
            weights = _station_quadrature_weights(solver_stations)
            for station, station_weight in zip(solver_stations, weights):
                samples = station["pose"]["samples"]
                sample_weight = math.sqrt(
                    station_weight / max(len(samples) * family_count, 1)
                )
                for sample in samples:
                    baseline = _evaluate_field(
                        base_field, sample["s"], station["h"]
                    )[2]
                    rows.append(
                        [
                            sample_weight
                            * (
                                _evaluate_field(
                                    field, sample["s"], station["h"]
                                )[2]
                                - baseline
                            )
                            for field in basis_fields
                        ]
                    )
                    targets.append(
                        sample_weight * (sample["theta_deg"] - baseline)
                    )
        return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)

    def residual_vector(
        self, vector: Sequence[float], *, roles: set[str] | None = None
    ) -> np.ndarray:
        active_roles = roles or {"camber", "pose", "normal_thickness"}
        parameters, defaults = self.constructor_inputs(vector, rounded=False)
        canonical = canonical_nurbs_from_v11_defaults(
            parameters, defaults, source=CANONICAL_INPUT_SOURCE
        )
        residuals: list[float] = []
        family_count = len(self.bundle["section_families"])
        for family in self.bundle["section_families"].values():
            solver_stations = _fixed_solver_stations(family["stations"])
            station_weights = _station_quadrature_weights(solver_stations)
            for station, station_weight in zip(solver_stations, station_weights):
                h = station["h"]
                for role, target, prediction, scale in (
                    (
                        "camber",
                        station["camber"]["samples"],
                        canonical["blade_skeleton_field"],
                        self.tolerance_contract["camber_rms_limit_mm"],
                    ),
                    (
                        "pose",
                        station["pose"]["samples"],
                        canonical["pose_field"],
                        self.policy.pose_rms_limit_deg,
                    ),
                    (
                        "thickness",
                        station["normal_thickness"]["samples"],
                        canonical["thickness_field"],
                        self.tolerance_contract["thickness_rms_limit_mm"],
                    ),
                ):
                    normalized_role = "normal_thickness" if role == "thickness" else role
                    if normalized_role not in active_roles:
                        continue
                    weight = math.sqrt(
                        station_weight / max(len(target) * family_count, 1)
                    )
                    for sample in target:
                        fitted = _evaluate_field(
                            prediction, sample["s"], h
                        )[2]
                        target_value = (
                            sample["q_mm"]
                            if role == "camber"
                            else sample["theta_deg"]
                            if role == "pose"
                            else sample["thickness_mm"]
                        )
                        residuals.append(weight * (fitted - target_value) / scale)

        if not residuals:
            return np.asarray([1.0e6], dtype=float)
        return np.asarray(residuals, dtype=float)

    def constructor_inputs(
        self, vector: Sequence[float], *, rounded: bool = True
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        values = dict(zip(self._VARIABLE_NAMES, [float(item) for item in vector]))
        average_thickness = values["average_blade_thickness_mm"]
        maximum_thickness = average_thickness + values["maximum_thickness_delta_mm"]
        if maximum_thickness > 120.0 + 1.0e-8:
            raise V112MappingError(
                "v116_v112_mapping_residual_exceeded",
                "mapped maximum blade thickness exceeds the V1.1.2 mapping bound",
                {"maximum_blade_thickness_mm": maximum_thickness},
            )
        hub_points = self.bundle["support_fits"]["hub"]["control_points_rz_mm"]
        tip_points = self.bundle["support_fits"]["tip_or_shroud"]["control_points_rz_mm"]
        root = self.bundle["attachments"]["root"]
        shroud = self.bundle["attachments"].get("shroud")
        populations = self.bundle["populations"]
        main = populations["main"]
        splitter = populations.get("splitter")
        material = self.topology["material_measurements"]

        inlet_height = _distance(hub_points[0], tip_points[0])
        outlet_height = _distance(hub_points[-1], tip_points[-1])
        main_family = self.bundle["section_families"]["main"]
        splitter_turn = (
            0.0
            if splitter is None
            else _mean_terminal_camber(
                self.bundle["section_families"]["splitter"]["stations"]
            )
        )
        edge_radii = _equivalent_edge_radii(self.bundle["section_families"])
        parameters: dict[str, Any] = {
            "blade_count": int(main["count"] + (0 if splitter is None else splitter["count"])),
            "inlet_radius_mm": float(hub_points[0][0]),
            "exit_radius_mm": float(hub_points[-1][0]),
            "inlet_blade_height_mm": inlet_height,
            "outlet_blade_height_mm": outlet_height,
            "hub_curve_height_mm": max(point[1] for point in hub_points)
            - min(point[1] for point in hub_points),
            "mounting_bore_radius_mm": _material_value(material, "mounting_bore_radius_mm"),
            "blade_wrap_deg": values["blade_wrap_deg"],
            "blade_lean_deg": values["blade_lean_deg"],
            "leading_edge_lean_deg": values["leading_edge_lean_deg"],
            "trailing_edge_lean_deg": values["trailing_edge_lean_deg"],
            "leading_edge_sweep_mm": values["leading_edge_sweep_mm"],
            "trailing_edge_sweep_mm": values["trailing_edge_sweep_mm"],
            "inlet_blade_angle_deg": _terminal_camber_angle(main_family, leading=True, support_points=hub_points),
            "outlet_blade_angle_deg": _terminal_camber_angle(main_family, leading=False, support_points=hub_points),
            "blade_thickness_mm": average_thickness,
            "root_fillet_radius_mm": _material_value(material, "root_fillet_radius_mm"),
            "leading_edge_radius_mm": edge_radii["leading_edge"],
            "trailing_edge_radius_mm": edge_radii["trailing_edge"],
            "tip_edge_radius_mm": _material_value(material, "tip_edge_radius_mm"),
            "hub_wall_thickness_mm": _material_value(material, "hub_wall_thickness_mm"),
            "hub_bottom_thickness_mm": _material_value(material, "hub_bottom_thickness_mm"),
            "hub_top_cap_thickness_mm": _material_value(material, "hub_top_cap_thickness_mm"),
            "hub_chamfer_radius_mm": _material_value(material, "hub_chamfer_radius_mm"),
        }
        if self.topology["mode"] == "closed":
            parameters.update(
                {
                    "hood_wall_thickness_mm": _material_value(material, "hood_wall_thickness_mm"),
                    "hood_chamfer_radius_mm": _material_value(material, "hood_chamfer_radius_mm"),
                }
            )

        defaults: dict[str, Any] = {
            "loop_family_id": "v1_1_6_measured_to_v1_1_2_loop_family",
            "coordinate_system": "blade_to_blade_s_q_mm",
            "span_stations_h": list(CANONICAL_STATIONS_H),
            "main_blade_count": int(main["count"]),
            "splitter_blade_count": 0 if splitter is None else int(splitter["count"]),
            "main_streamwise_interval_s": list(main["streamwise_interval_s"]),
            "splitter_streamwise_interval_s": (
                [0.35, 0.88]
                if splitter is None
                else list(splitter["streamwise_interval_s"])
            ),
            "splitter_phase_offset_pitch": float(populations["relative_phase_pitch"]),
            "splitter_positioning_mode": "main_passage_bisector",
            "splitter_passage_fraction": 0.5,
            "maximum_blade_thickness_mm": maximum_thickness,
            "average_blade_thickness_mm": average_thickness,
            "root_attachment_width_mm": float(median(root["width_samples_mm"])),
            "root_attachment_lift_mm": float(median(root["lift_samples_mm"])),
            "root_blade_lift_mm": float(median(root["lift_samples_mm"])),
            "main_flow_turn_q_mm": values["main_flow_turn_q_mm"],
            "splitter_flow_turn_q_mm": splitter_turn,
            "spanwise_flow_turn_delta_q_mm": values["spanwise_flow_turn_delta_q_mm"],
            "midspan_bow_q_mm": values["midspan_bow_q_mm"],
            "leading_edge_cap_roundness": 0.56,
            "trailing_edge_cap_roundness": 0.54,
            "tip_attachment_mode": (
                "open_tip_dome"
                if self.topology["mode"] == "open"
                else "closed_shroud_attachment"
            ),
            "segment_control_count_minimums": {
                "pressure_side": 15,
                "suction_side": 15,
                "leading_edge": 17,
                "trailing_edge": 17,
            },
            "segment_control_counts": {
                "pressure_side": 15,
                "suction_side": 15,
                "leading_edge": 17,
                "trailing_edge": 17,
            },
            "side_sample_count": 73,
            "edge_cap_sample_count": 49,
            "surface_span_sample_count": 13,
            "root_short_direction_sample_count": 9,
            "closed_shroud_short_direction_sample_count": 9,
            "profile_revolve_sample_count": 73,
            "theta_sample_count": 97,
            "hub_solid_radial_sample_count": 13,
            "hub_solid_axial_sample_count": 25,
            "hub_profile_rz_mm": deepcopy(hub_points),
            "tip_or_shroud_profile_rz_mm": deepcopy(tip_points),
            "blade_hub_angle_contract_deg": [0.0, 180.0],
            "minimum_active_blade_height_mm": 1.0,
            "enforce_support_profile_contract": False,
        }
        if shroud is not None:
            defaults["shroud_attachment_width_mm"] = float(
                median(shroud["width_samples_mm"])
            )
            defaults["shroud_blade_inset_mm"] = float(
                median(shroud["lift_samples_mm"])
            )

        if rounded:
            parameters = _round_tree_digits(parameters, 6)
            defaults = _round_tree_digits(defaults, 6)
        return parameters, defaults

    def objective_terms(
        self,
        parameters: Mapping[str, Any],
        defaults: Mapping[str, Any],
        canonical: Mapping[str, Any],
    ) -> dict[str, Any]:
        terms: dict[str, Any] = {}
        hub = self.bundle["support_fits"]["hub"]
        tip = self.bundle["support_fits"]["tip_or_shroud"]
        terms["supports"] = _term(
            target={
                "hub_control_points_rz_mm": hub["control_points_rz_mm"],
                "tip_or_shroud_control_points_rz_mm": tip["control_points_rz_mm"],
            },
            fitted={
                "hub_control_points_rz_mm": defaults["hub_profile_rz_mm"],
                "tip_or_shroud_control_points_rz_mm": defaults["tip_or_shroud_profile_rz_mm"],
            },
            unit="mm",
            weight="source_profile_fit_residual",
            residual={
                "hub_rms_mm": hub["residual_rms_mm"],
                "tip_rms_mm": tip["residual_rms_mm"],
            },
            gate={
                "hub_limit_mm": self.tolerance_contract["hub_rms_limit_mm"],
                "tip_limit_mm": self.tolerance_contract["tip_rms_limit_mm"],
                "status": "PASS"
                if hub["residual_rms_mm"] <= self.tolerance_contract["hub_rms_limit_mm"]
                and tip["residual_rms_mm"] <= self.tolerance_contract["tip_rms_limit_mm"]
                else "FAIL",
            },
            source_ids=hub["source_ids"] + tip["source_ids"],
        )

        sample_records = self._fixed_sample_records(canonical)
        for name in ("camber", "pose", "normal_thickness"):
            records = sample_records[name]
            residuals = [record["residual"] for record in records]
            weights = [record["weight"] for record in records]
            rms = _weighted_rms(residuals, weights)
            maximum = max((abs(value) for value in residuals), default=0.0)
            if name == "camber":
                limit = self.tolerance_contract["camber_rms_limit_mm"]
                status = "PASS" if rms <= limit else "FAIL"
                gate = {"rms_limit_mm": limit, "status": status}
                unit = "mm"
            elif name == "pose":
                status = (
                    "PASS"
                    if rms <= self.policy.pose_rms_limit_deg
                    and maximum <= self.policy.pose_max_limit_deg
                    else "FAIL"
                )
                gate = {
                    "rms_limit_deg": self.policy.pose_rms_limit_deg,
                    "maximum_limit_deg": self.policy.pose_max_limit_deg,
                    "status": status,
                }
                unit = "deg"
            else:
                limit = self.tolerance_contract["thickness_rms_limit_mm"]
                inside = all(
                    sample["inside_source_loop"]
                    and sample["thickness_mm"] > 0.0
                    for family in self.bundle["section_families"].values()
                    for station in family["stations"]
                    for sample in station["normal_thickness"]["samples"]
                )
                status = "PASS" if rms <= limit and inside else "FAIL"
                gate = {
                    "rms_limit_mm": limit,
                    "all_normal_hits_positive_inside_material": inside,
                    "status": status,
                }
                unit = "mm"
            evidence_records = []
            for record in records:
                local_limit = (
                    self.policy.pose_max_limit_deg
                    if name == "pose"
                    else self.tolerance_contract["camber_rms_limit_mm"]
                    if name == "camber"
                    else self.tolerance_contract["thickness_rms_limit_mm"]
                )
                evidence_records.append(
                    {
                        "family": record["family"],
                        "h": record["h"],
                        "s": record["s"],
                        "role": name,
                        "target": record["target"],
                        "fitted": record["fitted"],
                        "unit": unit,
                        "weight": record["weight"],
                        "residual": record["residual"],
                        "gate": {
                            "absolute_limit": local_limit,
                            "status": (
                                "PASS"
                                if abs(record["residual"]) <= local_limit
                                else "FAIL"
                            ),
                        },
                        "source_ids": record["source_ids"],
                    }
                )
            terms[name] = _term(
                target={
                    "authority": "fixed_five_station_resampled_source_measurements",
                    "record_count": len(evidence_records),
                },
                fitted={
                    "authority": "regenerated_v1_1_2_canonical_field",
                    "record_count": len(evidence_records),
                },
                unit=unit,
                weight={
                    "span_rule": "fixed_five_station_trapezoidal_endpoint_half_weight",
                    "span_weights": self.tolerance_contract["span_quadrature_weights"],
                    "streamwise_rule": "equal_samples_within_station",
                    "family_rule": "equal_representative_families",
                },
                residual={
                    "rms": rms,
                    "maximum": maximum,
                },
                gate=gate,
                source_ids=_source_ids_for_role(self.bundle, name),
                records=evidence_records,
            )

        edge_records = self._edge_residual_records(parameters, defaults)
        edge_maximum = max(
            (record["bidirectional_hausdorff_mm"] for record in edge_records),
            default=0.0,
        )
        edge_limit = self.tolerance_contract["edge_hausdorff_limit_mm"]
        edge_evidence_records = [
            {
                "family": record["family"],
                "h": record["h"],
                "role": record["edge"],
                "target": record["target_points_local_mm"],
                "fitted": record["fitted_points_local_mm"],
                "unit": "mm",
                "weight": record["weight"],
                "residual": record["bidirectional_hausdorff_mm"],
                "gate": {
                    "bidirectional_hausdorff_limit_mm": edge_limit,
                    "status": (
                        "PASS"
                        if record["bidirectional_hausdorff_mm"] <= edge_limit
                        else "FAIL"
                    ),
                },
                "source_ids": record["source_ids"],
                "distance_certificate": record["distance_certificate"],
                "target_nurbs_authorities": record[
                    "target_nurbs_authorities"
                ],
                "controls": record["controls"],
                "knots": record["knots"],
                "weights": record["weights"],
                "source_edge_ids": record["source_edge_ids"],
                "source_face_ids": record["source_face_ids"],
            }
            for record in edge_records
        ]
        terms["edge_curves"] = _term(
            target={
                "source_nurbs_role": "measurement_target_only",
                "authority": "nurbs_controls_knots_weights",
                "record_count": len(edge_evidence_records),
            },
            fitted={
                "generation_authority": "build_v11_blade_to_blade_loop_family",
                "v112_cap_policy": "generated_c2_nurbs_cap",
                "direct_curve_constructor_mode": False,
                "record_count": len(edge_evidence_records),
            },
            unit="mm",
            weight={
                "station_rule": "fixed_five_station_trapezoidal_endpoint_half_weight",
                "edge_rule": "equal_leading_trailing",
                "metric": "certified_continuous_bidirectional_curve_distance_upper_mm",
            },
            residual={
                "maximum_bidirectional_hausdorff_mm": edge_maximum,
            },
            gate={
                "bidirectional_hausdorff_limit_mm": edge_limit,
                "status": "PASS" if edge_maximum <= edge_limit else "FAIL",
            },
            source_ids=_source_ids_for_role(self.bundle, "edge_curves"),
            records=edge_evidence_records,
        )

        root = self.bundle["attachments"]["root"]
        shroud = self.bundle["attachments"].get("shroud")
        attachment_records = [
            _attachment_residual_record(
                "root",
                root,
                defaults["root_attachment_lift_mm"],
                defaults["root_attachment_width_mm"],
                self.policy.attachment_relative_limit,
            )
        ]
        if shroud is not None:
            attachment_records.append(
                _attachment_residual_record(
                    "shroud",
                    shroud,
                    defaults["shroud_blade_inset_mm"],
                    defaults["shroud_attachment_width_mm"],
                    self.policy.attachment_relative_limit,
                )
            )
        attachment_status = (
            "PASS"
            if all(record["status"] == "PASS" for record in attachment_records)
            else "FAIL"
        )
        terms["root_tip_offsets"] = _term(
            target={
                "root_lift_median_mm": median(root["lift_samples_mm"]),
                "tip_lift_median_mm": (
                    0.0 if shroud is None else median(shroud["lift_samples_mm"])
                ),
            },
            fitted={
                "root_offset_mm": defaults["root_blade_lift_mm"],
                "tip_offset_mm": defaults.get("shroud_blade_inset_mm", 0.0),
            },
            unit="mm",
            weight="hard_material_boundary",
            residual={"active_span_minimum_mm": self._active_span_minimum(defaults)},
            gate={
                "strictly_positive_active_span": self._active_span_minimum(defaults) > 0.0,
                "status": "PASS" if self._active_span_minimum(defaults) > 0.0 else "FAIL",
            },
            source_ids=root["source_ids"] + ([] if shroud is None else shroud["source_ids"]),
        )
        terms["attachment"] = _term(
            target={"measurement_count": len(attachment_records)},
            fitted={"record_count": len(attachment_records)},
            unit="relative",
            weight="source_median",
            residual={
                "maximum_relative": max(
                    max(record["lift_relative"], record["width_relative"])
                    for record in attachment_records
                )
            },
            gate={
                "relative_limit": self.policy.attachment_relative_limit,
                "status": attachment_status,
            },
            source_ids=root["source_ids"] + ([] if shroud is None else shroud["source_ids"]),
            records=attachment_records,
        )

        populations = self.bundle["populations"]
        main_count = populations["main"]["count"]
        splitter = populations.get("splitter")
        splitter_count = 0 if splitter is None else splitter["count"]
        exact_count = int(parameters["blade_count"]) == main_count + splitter_count
        hard_pass = (
            exact_count
            and populations["closure_pass"]
            and populations["collision_free"]
            and populations["phase_consistent"]
        )
        terms["periodicity"] = _term(
            target={
                "main_blade_count": main_count,
                "splitter_blade_count": splitter_count,
                "relative_phase_pitch": populations["relative_phase_pitch"],
            },
            fitted={
                "blade_count": parameters["blade_count"],
                "main_blade_count": defaults["main_blade_count"],
                "splitter_blade_count": defaults["splitter_blade_count"],
                "relative_phase_pitch": defaults["splitter_phase_offset_pitch"],
            },
            unit="count_and_pitch_fraction",
            weight="hard_constraint",
            residual={
                "count_difference": parameters["blade_count"] - main_count - splitter_count,
                "phase_difference_pitch": defaults["splitter_phase_offset_pitch"]
                - populations["relative_phase_pitch"],
            },
            gate={
                "counts_exact": exact_count,
                "phase_consistent": populations["phase_consistent"],
                "closure_pass": populations["closure_pass"],
                "collision_free": populations["collision_free"],
                "status": "PASS" if hard_pass else "FAIL",
            },
            source_ids=populations["source_ids"],
        )
        return self._self_contained_promotion_terms(terms)

    def _self_contained_promotion_terms(
        self, terms: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        methods = {
            "supports": "authenticated_trimmed_brep_support_fit_gate",
            "camber": "fixed_five_station_weighted_residual_gate",
            "pose": "fixed_five_station_weighted_residual_gate",
            "normal_thickness": "fixed_five_station_weighted_residual_gate",
            "edge_curves": _CURVE_DISTANCE_METHOD,
            "root_tip_offsets": "active_material_span_boundary_gate",
            "attachment": "source_attachment_median_relative_residual_gate",
            "periodicity": "exact_count_phase_and_collision_gate",
        }
        provenance = {
            "source_sha256": self.bundle["provenance"]["source_sha256"],
            "algorithm_version": self.bundle["provenance"]["algorithm_version"],
        }
        result = deepcopy(dict(terms))
        for name, term in result.items():
            status = term["gate"]["status"]
            term_source_edge_ids = sorted(
                {
                    source_id
                    for record in term.get("records", [])
                    for source_id in record.get("source_edge_ids", [])
                }
            )
            term_source_face_ids = sorted(
                {
                    source_id
                    for record in term.get("records", [])
                    for source_id in record.get("source_face_ids", [])
                }
            )
            source_ids = sorted(
                set(term["source_ids"])
                | set(term_source_edge_ids)
                | set(term_source_face_ids)
            )
            term_frame = _promotion_frame(
                self.bundle["frame"],
                coordinate_system=(
                    _TASK7_EDGE_COORDINATE_FRAME
                    if name == "edge_curves"
                    else None
                ),
            )
            term.update(
                {
                    "method": methods.get(name, "bounded_solver_objective_block"),
                    "tolerance": {
                        key: deepcopy(value)
                        for key, value in term["gate"].items()
                        if key != "status"
                    },
                    "confidence": {
                        "level": "authenticated_promotion_gate_evidence",
                        "gate_status": status,
                        "aggregate_score_used": False,
                    },
                    "frame": term_frame,
                    "units": _promotion_units(term["unit"]),
                    "source_ids": source_ids,
                    "source_edge_ids": term_source_edge_ids,
                    "source_face_ids": term_source_face_ids,
                    "provenance": {
                        **provenance,
                        "source_ids": source_ids,
                        "source_edge_ids": term_source_edge_ids,
                        "source_face_ids": term_source_face_ids,
                    },
                }
            )
            for record in term.get("records", []):
                record_source_edge_ids = sorted(
                    set(record.get("source_edge_ids", []))
                )
                record_source_face_ids = sorted(
                    set(record.get("source_face_ids", []))
                )
                record_source_ids = sorted(
                    set(record.get("source_ids", source_ids))
                    | set(record_source_edge_ids)
                    | set(record_source_face_ids)
                )
                record_status = record.get("gate", {}).get(
                    "status", record.get("status", status)
                )
                record_unit = record.get("unit", term["unit"])
                record.setdefault(
                    "method", methods.get(name, "bounded_solver_objective_block")
                )
                record.setdefault(
                    "tolerance",
                    {
                        key: deepcopy(value)
                        for key, value in record.get("gate", term["gate"]).items()
                        if key != "status"
                    },
                )
                record.setdefault(
                    "confidence",
                    {
                        "level": "authenticated_promotion_record",
                        "gate_status": record_status,
                        "aggregate_score_used": False,
                    },
                )
                record.setdefault("frame", deepcopy(term_frame))
                record.setdefault("units", _promotion_units(record_unit))
                record["source_ids"] = record_source_ids
                record["source_edge_ids"] = record_source_edge_ids
                record["source_face_ids"] = record_source_face_ids
                record_provenance = deepcopy(record.get("provenance", provenance))
                record_provenance.update(
                    {
                        "source_ids": record_source_ids,
                        "source_edge_ids": record_source_edge_ids,
                        "source_face_ids": record_source_face_ids,
                    }
                )
                record["provenance"] = record_provenance
        return result

    def _fixed_sample_records(
        self, canonical: Mapping[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {
            "camber": [],
            "pose": [],
            "normal_thickness": [],
        }
        field_by_role = {
            "camber": canonical["blade_skeleton_field"],
            "pose": canonical["pose_field"],
            "normal_thickness": canonical["thickness_field"],
        }
        key_by_role = {
            "camber": "q_mm",
            "pose": "theta_deg",
            "normal_thickness": "thickness_mm",
        }
        family_count = len(self.bundle["section_families"])
        for family_name, family in self.bundle["section_families"].items():
            stations = _fixed_solver_stations(family["stations"])
            station_weights = _station_quadrature_weights(stations)
            for station, station_weight in zip(stations, station_weights):
                h = float(station["h"])
                for role in result:
                    samples = station[role]["samples"]
                    weight = station_weight / max(family_count * len(samples), 1)
                    value_key = key_by_role[role]
                    for sample in samples:
                        target = float(sample[value_key])
                        fitted = float(
                            _evaluate_field(field_by_role[role], sample["s"], h)[2]
                        )
                        result[role].append(
                            {
                                "family": family_name,
                                "h": h,
                                "s": float(sample["s"]),
                                "target": target,
                                "fitted": fitted,
                                "residual": fitted - target,
                                "weight": weight,
                                "source_ids": sorted(station[role]["source_ids"]),
                            }
                        )
        return result

    def _edge_residual_records(
        self,
        parameters: Mapping[str, Any],
        defaults: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        generated = _generation_bound_loop_family(parameters, defaults)
        representative: dict[str, dict[str, Any]] = {}
        for blade in generated["blades"]:
            representative.setdefault(blade["blade_class"], blade)
        records: list[dict[str, Any]] = []
        family_count = len(self.bundle["section_families"])
        for population_name, family in self.bundle["section_families"].items():
            generated_blade = representative[population_name]
            station_weights = _station_quadrature_weights(
                [{"h": h} for h in CANONICAL_STATIONS_H]
            )
            for h, station_weight in zip(CANONICAL_STATIONS_H, station_weights):
                for edge_name in ("leading_edge", "trailing_edge"):
                    target_curve = _source_edge_curve_at_h(
                        family["stations"], h, edge_name
                    )
                    fitted = _generated_cap_polyline_at_h(
                        generated_blade,
                        h,
                        edge_name,
                    )
                    certificate = _certified_curve_to_polyline_distance(
                        target_curve,
                        fitted,
                        gate_limit_mm=self.tolerance_contract[
                            "edge_hausdorff_limit_mm"
                        ],
                    )
                    authorities = _source_curve_authorities(target_curve)
                    records.append(
                        {
                            "family": population_name,
                            "h": h,
                            "edge": edge_name,
                            "target_points_local_mm": _source_curve_display_points(
                                target_curve
                            ),
                            "fitted_points_local_mm": fitted,
                            "bidirectional_hausdorff_mm": _round(
                                certificate["upper_bound_mm"], 12
                            ),
                            "distance_certificate": certificate,
                            "target_nurbs_authorities": authorities,
                            "controls": [
                                authority["controls"] for authority in authorities
                            ],
                            "knots": [
                                authority["knots"] for authority in authorities
                            ],
                            "weights": [
                                authority["weights"] for authority in authorities
                            ],
                            "weight": station_weight
                            / max(family_count * 2, 1),
                            "source_ids": target_curve["source_ids"],
                            "source_edge_ids": target_curve["source_edge_ids"],
                            "source_face_ids": target_curve["source_face_ids"],
                        }
                    )
        return records

    def _active_span_minimum(self, defaults: Mapping[str, Any]) -> float:
        hub = np.asarray(defaults["hub_profile_rz_mm"], dtype=float)
        tip = np.asarray(defaults["tip_or_shroud_profile_rz_mm"], dtype=float)
        root_offset = float(defaults["root_blade_lift_mm"])
        tip_offset = float(defaults.get("shroud_blade_inset_mm", 0.0))
        distances = np.linalg.norm(tip - hub, axis=1) - root_offset - tip_offset
        return _round(float(np.min(distances)), 12)

    def five_station_report(
        self,
        canonical: Mapping[str, Any],
        parameters: Mapping[str, Any],
        defaults: Mapping[str, Any],
    ) -> dict[str, Any]:
        families: dict[str, Any] = {}
        for name, family in self.bundle["section_families"].items():
            station_reports = []
            for h in CANONICAL_STATIONS_H:
                camber_residuals = _resampled_station_residuals(
                    family["stations"],
                    h,
                    "camber",
                    lambda s: _evaluate_field(
                        canonical["blade_skeleton_field"], s, h
                    )[2],
                )
                thickness_residuals = _resampled_station_residuals(
                    family["stations"],
                    h,
                    "normal_thickness",
                    lambda s: _evaluate_field(
                        canonical["thickness_field"], s, h
                    )[2],
                )
                pose_residuals = _resampled_station_residuals(
                    family["stations"],
                    h,
                    "pose",
                    lambda s: _evaluate_field(
                        canonical["pose_field"], s, h
                    )[2],
                )
                station_reports.append(
                    {
                        "h": h,
                        "camber_rms_mm": _rms(camber_residuals),
                        "normal_thickness_rms_mm": _rms(thickness_residuals),
                        "pose_rms_deg": _rms(pose_residuals),
                    }
                )
            families[name] = {
                "source_station_count": len(family["stations"]),
                "canonical_station_count": 5,
                "stations": station_reports,
            }
        return {
            "method": "linear_h_interpolation_to_fixed_v1_1_2_stations",
            "canonical_stations_h": list(CANONICAL_STATIONS_H),
            "span_quadrature_rule": "trapezoidal_endpoint_half_weight",
            "span_quadrature_weights": self.tolerance_contract[
                "span_quadrature_weights"
            ],
            "families": families,
            "adaptive_station_loss": self._adaptive_station_loss(
                canonical, parameters, defaults
            ),
        }

    def _adaptive_station_loss(
        self,
        canonical: Mapping[str, Any],
        parameters: Mapping[str, Any],
        defaults: Mapping[str, Any],
    ) -> dict[str, Any]:
        values: dict[str, list[float]] = {
            "camber": [],
            "pose": [],
            "normal_thickness": [],
        }
        weights: dict[str, list[float]] = {name: [] for name in values}
        field_by_role = {
            "camber": canonical["blade_skeleton_field"],
            "pose": canonical["pose_field"],
            "normal_thickness": canonical["thickness_field"],
        }
        key_by_role = {
            "camber": "q_mm",
            "pose": "theta_deg",
            "normal_thickness": "thickness_mm",
        }
        family_count = len(self.bundle["section_families"])
        for family in self.bundle["section_families"].values():
            stations = family["stations"]
            station_weights = _station_quadrature_weights(stations)
            for station, station_weight in zip(stations, station_weights):
                for role in values:
                    samples = station[role]["samples"]
                    sample_weight = station_weight / max(family_count * len(samples), 1)
                    for sample in samples:
                        fitted = _evaluate_field(
                            field_by_role[role], sample["s"], station["h"]
                        )[2]
                        values[role].append(fitted - sample[key_by_role[role]])
                        weights[role].append(sample_weight)
        adaptive_edge_residuals = self._adaptive_edge_residuals(parameters, defaults)
        return {
            "method": "adaptive_source_station_quadrature_diagnostic",
            "used_for_promotion": False,
            "camber_rms_mm": _weighted_rms(values["camber"], weights["camber"]),
            "pose_rms_deg": _weighted_rms(values["pose"], weights["pose"]),
            "normal_thickness_rms_mm": _weighted_rms(
                values["normal_thickness"], weights["normal_thickness"]
            ),
            "edge_maximum_bidirectional_hausdorff_mm": max(
                adaptive_edge_residuals, default=0.0
            ),
            "edge_rms_bidirectional_hausdorff_mm": _rms(
                adaptive_edge_residuals
            ),
            "edge_curve_distance_method": _CURVE_DISTANCE_METHOD,
            "edge_curve_distance_convergence_tolerance_mm": (
                _CURVE_DISTANCE_CONVERGENCE_MM
            ),
        }

    def _adaptive_edge_residuals(
        self,
        parameters: Mapping[str, Any],
        defaults: Mapping[str, Any],
    ) -> list[float]:
        generated = _generation_bound_loop_family(parameters, defaults)
        representative: dict[str, dict[str, Any]] = {}
        for blade in generated["blades"]:
            representative.setdefault(blade["blade_class"], blade)
        residuals = []
        for family_name, family in self.bundle["section_families"].items():
            generated_blade = representative[family_name]
            for station in family["stations"]:
                h = float(station["h"])
                for edge_name in ("leading_edge", "trailing_edge"):
                    target_curve = _source_edge_curve_at_h(
                        [station], h, edge_name
                    )
                    fitted = _generated_cap_polyline_at_h(
                        generated_blade, h, edge_name
                    )
                    certificate = _certified_curve_to_polyline_distance(
                        target_curve,
                        fitted,
                        gate_limit_mm=self.tolerance_contract[
                            "edge_hausdorff_limit_mm"
                        ],
                    )
                    residuals.append(certificate["upper_bound_mm"])
        return residuals

    def bounds_contract(self) -> dict[str, list[float]]:
        return {
            name: [_round(lower, 12), _round(upper, 12)]
            for name, lower, upper in zip(
                self._VARIABLE_NAMES, self.lower_bounds, self.upper_bounds
            )
        }


def _validate_and_normalize_bundle(measurements: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(measurements, Mapping):
        _schema_error("measurements must be a mapping")
    _require_keys(
        measurements,
        {
            "schema_version",
            "frame",
            "provenance",
            "topology",
            "support_fits",
            "populations",
            "section_families",
            "attachments",
        },
        {
            "schema_version",
            "frame",
            "provenance",
            "topology",
            "support_fits",
            "populations",
            "section_families",
            "attachments",
        },
        "measurements",
    )
    if measurements["schema_version"] != MEASUREMENT_SCHEMA_VERSION:
        _schema_error("unsupported measurement schema_version")
    bundle = _normalize_input_sequences(deepcopy(dict(measurements)))
    bundle["frame"] = adapt_task3_frame_for_mapping(bundle["frame"])
    _validate_frame(bundle["frame"])
    _validate_provenance(bundle["provenance"])
    _validate_topology(bundle["topology"])
    _validate_support_fits(bundle["support_fits"])
    _validate_populations(bundle["populations"])
    _validate_section_families(
        bundle["section_families"],
        bundle["populations"],
        source_tolerance_mm=float(bundle["frame"]["source_tolerance_mm"]),
    )
    _validate_attachments(bundle["attachments"], bundle["topology"])
    return _normalized_bundle_order(bundle)


def _normalize_input_sequences(bundle: dict[str, Any]) -> dict[str, Any]:
    def normalize_source_ids(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {
                    "source_ids",
                    "source_entity_ids",
                    "source_face_ids",
                    "source_edge_ids",
                    "face_ids",
                    "edge_ids",
                } and _is_sequence(item):
                    value[key] = sorted(str(entry) for entry in item)
                else:
                    normalize_source_ids(item)
        elif isinstance(value, list):
            for item in value:
                normalize_source_ids(item)

    normalize_source_ids(bundle)
    families = bundle.get("section_families")
    if isinstance(families, Mapping):
        for family in families.values():
            if not isinstance(family, dict) or not _is_sequence(family.get("stations")):
                continue
            family["stations"] = sorted(
                family["stations"],
                key=lambda station: float(station.get("h", math.inf))
                if isinstance(station, Mapping)
                else math.inf,
            )
            for station in family["stations"]:
                if not isinstance(station, dict):
                    continue
                for role in ("camber", "pose", "normal_thickness"):
                    record = station.get(role)
                    if isinstance(record, dict) and _is_sequence(record.get("samples")):
                        record["samples"] = sorted(
                            record["samples"],
                            key=lambda sample: float(sample.get("s", math.inf))
                            if isinstance(sample, Mapping)
                            else math.inf,
                        )
    return bundle


def _validate_frame(frame: Any) -> None:
    _require_mapping(frame, "frame")
    required = {
        "coordinate_system",
        "source_to_canonical_matrix",
        "units",
        "source_tolerance_mm",
        "method",
        "source_axis_origin_mm",
        "source_axis_direction",
        "scale",
        "primary_icp_applied",
        "handedness",
        "axis_consensus",
        "candidate_scores",
        "outer_radius_mm",
        "main_bore_radius_mm",
        "axial_extent_mm",
        "central_cylinder_radii_mm",
    }
    _require_keys(
        frame,
        required,
        required,
        "frame",
    )
    if frame["coordinate_system"] != "canonical_axis_frame_xyz_mm" or frame["units"] != "mm":
        _schema_error("frame must use canonical_axis_frame_xyz_mm and mm")
    matrix = frame["source_to_canonical_matrix"]
    if (
        not _is_sequence(matrix)
        or len(matrix) != 4
        or any(not _is_sequence(row) or len(row) != 4 for row in matrix)
    ):
        _schema_error("frame.source_to_canonical_matrix must be finite 4x4")
    numeric_matrix = np.asarray(
        [
            [_finite(value, "frame.source_to_canonical_matrix") for value in row]
            for row in matrix
        ],
        dtype=float,
    )
    if not np.allclose(numeric_matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-10, rtol=0.0):
        _schema_error("frame.source_to_canonical_matrix must have homogeneous last row [0,0,0,1]")
    rotation = numeric_matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1.0e-9, rtol=0.0):
        _schema_error("frame.source_to_canonical_matrix rotation must be orthonormal without scale or shear")
    determinant = float(np.linalg.det(rotation))
    if not math.isclose(determinant, 1.0, abs_tol=1.0e-9, rel_tol=0.0):
        _schema_error("frame.source_to_canonical_matrix must be a right-handed rigid transform with det +1")
    _positive(frame["source_tolerance_mm"], "frame.source_tolerance_mm")
    if not str(frame["method"]).startswith("deterministic_analytic_axis_consensus"):
        _schema_error("frame.method must bind the Task 3 deterministic analytic axis consensus")
    if not math.isclose(_finite(frame["scale"], "frame.scale"), 1.0, abs_tol=1.0e-12):
        _schema_error("frame.scale must equal 1.0")
    if frame["primary_icp_applied"] is not False or frame["handedness"] != "right_handed":
        _schema_error("frame must preserve Task 3 no-primary-ICP right-handed evidence")
    origin = np.asarray(_point(frame["source_axis_origin_mm"], 3, "frame.source_axis_origin_mm"))
    direction = np.asarray(_point(frame["source_axis_direction"], 3, "frame.source_axis_direction"))
    if not math.isclose(float(np.linalg.norm(direction)), 1.0, abs_tol=1.0e-9):
        _schema_error("frame.source_axis_direction must be unit length")
    transformed_direction = rotation @ direction
    transformed_origin = rotation @ origin + numeric_matrix[:3, 3]
    if not np.allclose(transformed_direction, [0.0, 0.0, 1.0], atol=1.0e-8, rtol=0.0):
        _schema_error("frame transform must map the Task 3 source axis to canonical +Z")
    if not np.allclose(transformed_origin, [0.0, 0.0, 0.0], atol=1.0e-8, rtol=0.0):
        _schema_error("frame transform must map the Task 3 source axis origin to canonical origin")
    consensus = _validate_task3_axis_consensus(frame["axis_consensus"])
    candidates = frame["candidate_scores"]
    if not _is_sequence(candidates):
        _schema_error("frame.candidate_scores must be an ordered sequence")
    for index, candidate in enumerate(candidates):
        _validate_task3_axis_cluster(candidate, f"frame.candidate_scores[{index}]")
    _positive(frame["outer_radius_mm"], "frame.outer_radius_mm")
    if frame["main_bore_radius_mm"] is not None:
        _positive(frame["main_bore_radius_mm"], "frame.main_bore_radius_mm")
    _positive(frame["axial_extent_mm"], "frame.axial_extent_mm")
    central_radii = frame["central_cylinder_radii_mm"]
    if not _is_sequence(central_radii):
        _schema_error("frame.central_cylinder_radii_mm must be a sequence")
    for index, radius in enumerate(central_radii):
        _positive(radius, f"frame.central_cylinder_radii_mm[{index}]")
    selected = consensus["selected_cluster"]
    selected_origin = np.asarray(selected["line_origin_mm"], dtype=float)
    selected_direction = np.asarray(selected["line_direction"], dtype=float)
    line_distance = float(np.linalg.norm(np.cross(origin - selected_origin, selected_direction)))
    if line_distance > float(consensus["tolerance"]["line_distance_mm"]) + 1.0e-12:
        _schema_error("frame source axis origin is not on the selected Task 3 axis line")
    if not math.isclose(
        abs(float(np.dot(direction, selected_direction))),
        1.0,
        abs_tol=1.0e-9,
    ):
        _schema_error("frame source axis direction is not collinear with selected Task 3 evidence")


def _validate_task3_axis_consensus(value: Any) -> Mapping[str, Any]:
    path = "frame.axis_consensus"
    consensus = _require_mapping(value, path)
    keys = {
        "tolerance",
        "selected_cluster",
        "residual",
        "direction_resolution",
        "rejected_alternatives",
    }
    _require_keys(consensus, keys, keys, path)
    _validate_task3_consensus_tolerance(consensus["tolerance"], f"{path}.tolerance")
    selected = _validate_task3_axis_cluster(
        consensus["selected_cluster"], f"{path}.selected_cluster"
    )
    _validate_task3_axis_residual(consensus["residual"], f"{path}.residual")
    if _round_tree(consensus["residual"]) != _round_tree(selected["residual"]):
        _schema_error("frame.axis_consensus residual must match selected cluster residual")
    direction = _require_mapping(
        consensus["direction_resolution"], f"{path}.direction_resolution"
    )
    direction_keys = {"method", "normalized_moment"}
    _require_keys(direction, direction_keys, direction_keys, f"{path}.direction_resolution")
    if direction["method"] not in {
        "radial_weighted_axial_asymmetry",
        "world_lexicographic_fallback_for_axially_symmetric_source",
    }:
        _schema_error("frame.axis_consensus.direction_resolution.method is not Task 3 evidence")
    _nonnegative(
        direction["normalized_moment"],
        f"{path}.direction_resolution.normalized_moment",
    )
    rejected = consensus["rejected_alternatives"]
    if not _is_sequence(rejected):
        _schema_error(f"{path}.rejected_alternatives must be a sequence")
    for index, candidate in enumerate(rejected):
        _validate_task3_axis_cluster(candidate, f"{path}.rejected_alternatives[{index}]")
    return consensus


def _validate_task3_axis_cluster(value: Any, path: str) -> Mapping[str, Any]:
    cluster = _require_mapping(value, path)
    keys = {
        "score",
        "score_components",
        "confidence",
        "coordinate_frame",
        "units",
        "tolerance",
        "source_entity_ids",
        "face_ids",
        "edge_ids",
        "face_count",
        "line_origin_mm",
        "line_direction",
        "residual",
        "provenance",
    }
    _require_keys(cluster, keys, keys, path)
    _nonnegative(cluster["score"], f"{path}.score")
    score_components = _require_mapping(cluster["score_components"], f"{path}.score_components")
    component_keys = {
        "analytic_area_mm2",
        "analytic_feature_count",
        "periodic_closure_support",
        "normalized_analytic_area",
        "normalized_feature_count",
        "normalized_periodic_closure",
    }
    _require_keys(score_components, component_keys, component_keys, f"{path}.score_components")
    for key in component_keys:
        _nonnegative(score_components[key], f"{path}.score_components.{key}")
    confidence = _require_mapping(cluster["confidence"], f"{path}.confidence")
    confidence_keys = {"level", "combined_score", "independent_score_components"}
    _require_keys(confidence, confidence_keys, confidence_keys, f"{path}.confidence")
    if (
        confidence["level"] != "ranked_analytic_consensus_candidate"
        or confidence["independent_score_components"] is not True
    ):
        _schema_error(f"{path}.confidence is not authenticated Task 3 evidence")
    _nonnegative(confidence["combined_score"], f"{path}.confidence.combined_score")
    if cluster["coordinate_frame"] != "source_cartesian_mm" or cluster["units"] != {
        "linear": "mm",
        "angular": "deg",
        "area": "mm2",
    }:
        _schema_error(f"{path} coordinate frame or units are not Task 3 values")
    _validate_task3_cluster_tolerance(cluster["tolerance"], f"{path}.tolerance")
    source_ids = _source_ids(cluster["source_entity_ids"], f"{path}.source_entity_ids")
    face_ids = _source_ids(cluster["face_ids"], f"{path}.face_ids", allow_empty=True)
    edge_ids = _source_ids(cluster["edge_ids"], f"{path}.edge_ids", allow_empty=True)
    if not set(face_ids + edge_ids).issubset(source_ids):
        _schema_error(f"{path} face/edge ids must be owned by source_entity_ids")
    face_count = cluster["face_count"]
    if isinstance(face_count, bool) or not isinstance(face_count, int) or face_count < 0:
        _schema_error(f"{path}.face_count must be a nonnegative integer")
    _point(cluster["line_origin_mm"], 3, f"{path}.line_origin_mm")
    direction = np.asarray(_point(cluster["line_direction"], 3, f"{path}.line_direction"))
    if not math.isclose(float(np.linalg.norm(direction)), 1.0, abs_tol=1.0e-9):
        _schema_error(f"{path}.line_direction must be unit length")
    _validate_task3_axis_residual(cluster["residual"], f"{path}.residual")
    provenance = _require_mapping(cluster["provenance"], f"{path}.provenance")
    provenance_keys = {"authority", "source_entity_ids", "candidate_method"}
    _require_keys(provenance, provenance_keys, provenance_keys, f"{path}.provenance")
    if (
        provenance["authority"] != "uploaded_step_brep"
        or provenance["candidate_method"]
        != "analytic_surface_and_circular_edge_axis_extraction"
        or _source_ids(provenance["source_entity_ids"], f"{path}.provenance.source_entity_ids")
        != source_ids
    ):
        _schema_error(f"{path}.provenance is not bound to its Task 3 source ids")
    return cluster


def _validate_task3_consensus_tolerance(value: Any, path: str) -> None:
    tolerance = _require_mapping(value, path)
    keys = {"line_distance_mm", "clustering_line_distance_mm", "angular_deg"}
    _require_keys(tolerance, keys, keys, path)
    for key in keys:
        _positive(tolerance[key], f"{path}.{key}")


def _validate_task3_cluster_tolerance(value: Any, path: str) -> None:
    tolerance = _require_mapping(value, path)
    keys = {"line_distance_mm", "angular_deg"}
    _require_keys(tolerance, keys, keys, path)
    for key in keys:
        _positive(tolerance[key], f"{path}.{key}")


def _validate_task3_axis_residual(value: Any, path: str) -> None:
    residual = _require_mapping(value, path)
    keys = {"line_rms_mm", "line_max_mm", "angular_spread_deg"}
    _require_keys(residual, keys, keys, path)
    for key in keys:
        _nonnegative(residual[key], f"{path}.{key}")


def _validate_provenance(provenance: Any) -> None:
    _require_mapping(provenance, "provenance")
    _require_keys(
        provenance,
        {"source_sha256", "source_entity_ids", "algorithm_version", "source_preset_id"},
        {"source_sha256", "source_entity_ids", "algorithm_version"},
        "provenance",
    )
    digest = str(provenance["source_sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
        _schema_error("provenance.source_sha256 must be a 64-character hex digest")
    _source_ids(provenance["source_entity_ids"], "provenance.source_entity_ids")
    if not str(provenance["algorithm_version"]).strip():
        _schema_error("provenance.algorithm_version is required")


def _validate_topology(topology: Any) -> None:
    _require_mapping(topology, "topology")
    _require_keys(
        topology,
        {"mode", "outer_diameter_mm", "material_shroud", "material_measurements", "source_ids"},
        {"mode", "outer_diameter_mm", "material_shroud", "material_measurements", "source_ids"},
        "topology",
    )
    mode = topology["mode"]
    if mode not in {"open", "closed"}:
        _schema_error("topology.mode must be open or closed")
    if not isinstance(topology["material_shroud"], bool):
        _schema_error("topology.material_shroud must be boolean")
    if topology["material_shroud"] != (mode == "closed"):
        raise V112MappingError(
            "v116_v112_topology_failed",
            "open topology cannot contain a material shroud and closed topology requires one",
        )
    _positive(topology["outer_diameter_mm"], "topology.outer_diameter_mm")
    _source_ids(topology["source_ids"], "topology.source_ids")
    material = topology["material_measurements"]
    _require_mapping(material, "topology.material_measurements")
    required = set(_COMMON_MATERIAL_KEYS)
    if mode == "closed":
        required.update(_CLOSED_MATERIAL_KEYS)
    _require_keys(material, required, required, "topology.material_measurements")
    for name, record in material.items():
        _validate_material_measurement(record, f"topology.material_measurements.{name}")


def _validate_material_measurement(record: Any, path: str) -> None:
    _require_mapping(record, path)
    _require_keys(record, {"value", "unit", "source_ids", "measured"}, {"value", "unit", "source_ids", "measured"}, path)
    _nonnegative(record["value"], f"{path}.value")
    if record["unit"] != "mm" or record["measured"] is not True:
        raise V112MappingError(
            "v116_v112_material_measurement_missing",
            f"{path} must be an explicit measured millimetric material feature",
        )
    _source_ids(record["source_ids"], f"{path}.source_ids")


def _validate_support_fits(supports: Any) -> None:
    _require_mapping(supports, "support_fits")
    _require_keys(supports, {"hub", "tip_or_shroud"}, {"hub", "tip_or_shroud"}, "support_fits")
    for name, fit in supports.items():
        path = f"support_fits.{name}"
        _require_mapping(fit, path)
        _require_keys(
            fit,
            {"control_points_rz_mm", "residual_rms_mm", "source_ids", "fit_status", "measurement_authority"},
            {"control_points_rz_mm", "residual_rms_mm", "source_ids", "fit_status", "measurement_authority"},
            path,
        )
        points = fit["control_points_rz_mm"]
        if not _is_sequence(points) or len(points) != 6:
            _schema_error(f"{path}.control_points_rz_mm must contain six controls")
        for index, point in enumerate(points):
            _point(point, 2, f"{path}.control_points_rz_mm[{index}]")
        _nonnegative(fit["residual_rms_mm"], f"{path}.residual_rms_mm")
        _source_ids(fit["source_ids"], f"{path}.source_ids")
        if fit["fit_status"] != "PASS" or fit["measurement_authority"] != "occt_trimmed_brep_measurement":
            _schema_error(f"{path} lacks promoted source B-Rep measurement authority")


def _validate_populations(populations: Any) -> None:
    _require_mapping(populations, "populations")
    _require_keys(
        populations,
        {"main", "splitter", "relative_phase_pitch", "closure_pass", "collision_free", "phase_consistent", "source_ids"},
        {"main", "splitter", "relative_phase_pitch", "closure_pass", "collision_free", "phase_consistent", "source_ids"},
        "populations",
    )
    main = populations["main"]
    _validate_population(main, "populations.main")
    splitter = populations["splitter"]
    if splitter is not None:
        _validate_population(splitter, "populations.splitter")
    for key in ("closure_pass", "collision_free", "phase_consistent"):
        if not isinstance(populations[key], bool) or not populations[key]:
            raise V112MappingError(
                "v116_v112_topology_failed",
                f"populations.{key} must be true",
            )
    relative_phase = _finite(populations["relative_phase_pitch"], "populations.relative_phase_pitch")
    if splitter is None and abs(relative_phase) > 1.0e-12:
        _schema_error("relative_phase_pitch must be zero without splitters")
    if splitter is not None and not 0.0 <= relative_phase < 1.0:
        _schema_error("relative_phase_pitch must be in [0, 1)")
    _source_ids(populations["source_ids"], "populations.source_ids")


def _validate_population(population: Any, path: str) -> None:
    _require_mapping(population, path)
    _require_keys(
        population,
        {"count", "pitch_deg", "phase_deg", "streamwise_interval_s", "source_ids"},
        {"count", "pitch_deg", "phase_deg", "streamwise_interval_s", "source_ids"},
        path,
    )
    count = population["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        _schema_error(f"{path}.count must be a positive integer")
    pitch = _positive(population["pitch_deg"], f"{path}.pitch_deg")
    if abs(pitch - 360.0 / count) > 1.0e-6:
        raise V112MappingError(
            "v116_v112_topology_failed",
            f"{path}.pitch_deg does not close its measured population",
        )
    _finite(population["phase_deg"], f"{path}.phase_deg")
    interval = population["streamwise_interval_s"]
    if not _is_sequence(interval) or len(interval) != 2:
        _schema_error(f"{path}.streamwise_interval_s must be a pair")
    start = _finite(interval[0], f"{path}.streamwise_interval_s[0]")
    end = _finite(interval[1], f"{path}.streamwise_interval_s[1]")
    if not 0.0 <= start < end <= 1.0:
        _schema_error(f"{path}.streamwise_interval_s must satisfy 0 <= start < end <= 1")
    _source_ids(population["source_ids"], f"{path}.source_ids")


def _validate_section_families(
    families: Any,
    populations: Mapping[str, Any],
    *,
    source_tolerance_mm: float,
) -> None:
    _require_mapping(families, "section_families")
    expected = {"main"}
    if populations["splitter"] is not None:
        expected.add("splitter")
    _require_keys(families, expected, expected, "section_families")
    for name, family in families.items():
        path = f"section_families.{name}"
        _require_mapping(family, path)
        _require_keys(family, {"population", "stations", "source_ids"}, {"population", "stations", "source_ids"}, path)
        if family["population"] != name:
            _schema_error(f"{path}.population must equal its family key")
        _source_ids(family["source_ids"], f"{path}.source_ids")
        stations = family["stations"]
        if not _is_sequence(stations) or not 5 <= len(stations) <= 9:
            _schema_error(f"{path}.stations must contain 5 to 9 adaptive stations")
        for index, station in enumerate(stations):
            _validate_station(
                station,
                f"{path}.stations[{index}]",
                source_tolerance_mm=source_tolerance_mm,
            )
        ordered_h = sorted(float(station["h"]) for station in stations)
        if ordered_h[0] != 0.0 or ordered_h[-1] != 1.0:
            _schema_error(f"{path}.stations must include active root h=0 and active tip h=1")
        if any(right - left <= 1.0e-9 for left, right in zip(ordered_h, ordered_h[1:])):
            _schema_error(f"{path}.stations must have unique increasing h values")


def _validate_station(
    station: Any, path: str, *, source_tolerance_mm: float
) -> None:
    _require_mapping(station, path)
    _require_keys(
        station,
        {"h", "source_ids", "decomposition", "camber", "pose", "normal_thickness"},
        {"h", "source_ids", "decomposition", "camber", "pose", "normal_thickness"},
        path,
    )
    h = _finite(station["h"], f"{path}.h")
    if not 0.0 <= h <= 1.0:
        _schema_error(f"{path}.h must be in [0, 1]")
    _source_ids(station["source_ids"], f"{path}.source_ids")
    decomposition = station["decomposition"]
    _require_mapping(decomposition, f"{path}.decomposition")
    _require_keys(
        decomposition,
        {"segments", "pressure_suction_assigned", "direct_curve_constructor_mode", "source_ids"},
        {"segments", "pressure_suction_assigned", "direct_curve_constructor_mode", "source_ids"},
        f"{path}.decomposition",
    )
    if decomposition["pressure_suction_assigned"] is not False or decomposition["direct_curve_constructor_mode"] is not False:
        _schema_error(f"{path}.decomposition must remain orientation-neutral and measurement-only")
    _source_ids(decomposition["source_ids"], f"{path}.decomposition.source_ids")
    segments = decomposition["segments"]
    _require_mapping(segments, f"{path}.decomposition.segments")
    _require_keys(segments, set(_SEGMENT_NAMES), set(_SEGMENT_NAMES), f"{path}.decomposition.segments")
    for name, segment in segments.items():
        _validate_segment(
            segment,
            name,
            f"{path}.decomposition.segments.{name}",
            source_tolerance_mm=source_tolerance_mm,
        )
    _validate_sample_series(station["camber"], "q_mm", f"{path}.camber")
    _validate_sample_series(station["pose"], "theta_deg", f"{path}.pose")
    _validate_thickness_series(station["normal_thickness"], f"{path}.normal_thickness")


def _validate_segment(
    segment: Any, name: str, path: str, *, source_tolerance_mm: float
) -> None:
    _require_mapping(segment, path)
    allowed = {"points_sq_mm", "source_ids"}
    if name in {"leading_edge", "trailing_edge"}:
        allowed.update({"nurbs_target", "source_edge_ids", "source_face_ids"})
    _require_keys(segment, allowed, allowed, path)
    points = segment["points_sq_mm"]
    if not _is_sequence(points) or len(points) < 2:
        _schema_error(f"{path}.points_sq_mm must contain at least two points")
    for index, point in enumerate(points):
        _point(point, 2, f"{path}.points_sq_mm[{index}]")
    segment_source_ids = _source_ids(segment["source_ids"], f"{path}.source_ids")
    if "nurbs_target" in segment:
        segment_source_edge_ids = _source_ids(
            segment["source_edge_ids"], f"{path}.source_edge_ids"
        )
        segment_source_face_ids = _source_ids(
            segment["source_face_ids"],
            f"{path}.source_face_ids",
            allow_empty=True,
        )
        if set(segment_source_edge_ids) & set(segment_source_face_ids):
            _schema_error(f"{path} source face and edge ids must remain distinct")
        if sorted(set(segment_source_ids)) != sorted(
            set(segment_source_edge_ids) | set(segment_source_face_ids)
        ):
            _schema_error(
                f"{path}.source_ids must be the union of distinct face and edge ids"
            )
        _validate_nurbs_target(
            segment["nurbs_target"],
            f"{path}.nurbs_target",
            source_tolerance_mm=source_tolerance_mm,
            segment_name=name,
            segment_points=points,
            segment_source_edge_ids=segment_source_edge_ids,
        )


def _validate_nurbs_target(
    target: Any,
    path: str,
    *,
    source_tolerance_mm: float,
    segment_name: str,
    segment_points: Sequence[Sequence[float]],
    segment_source_edge_ids: Sequence[str],
) -> None:
    _require_mapping(target, path)
    _require_keys(
        target,
        {
            "degree",
            "knots",
            "weights",
            "control_points_local_mm",
            "sample_points_local_mm",
            "measurement_target_only",
            "constructor_direct_curve_mode",
            "fit_evidence",
        },
        {
            "degree",
            "knots",
            "weights",
            "control_points_local_mm",
            "sample_points_local_mm",
            "measurement_target_only",
            "constructor_direct_curve_mode",
            "fit_evidence",
        },
        path,
    )
    if target["measurement_target_only"] is not True or target["constructor_direct_curve_mode"] is not False:
        _schema_error(f"{path} must be measurement-only and cannot request a direct curve constructor")
    degree = target["degree"]
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 1:
        _schema_error(f"{path}.degree must be a positive integer")
    controls = target["control_points_local_mm"]
    samples = target["sample_points_local_mm"]
    if not _is_sequence(controls) or len(controls) < degree + 1:
        _schema_error(f"{path}.control_points_local_mm is too short for its degree")
    if not _is_sequence(samples) or len(samples) < 9:
        _schema_error(f"{path}.sample_points_local_mm must contain at least nine points")
    for label, points in (("control_points_local_mm", controls), ("sample_points_local_mm", samples)):
        for index, point in enumerate(points):
            _point(point, 2, f"{path}.{label}[{index}]")
    weights = target["weights"]
    if not _is_sequence(weights) or len(weights) != len(controls):
        _schema_error(f"{path}.weights must match control point count")
    for index, value in enumerate(weights):
        _positive(value, f"{path}.weights[{index}]")
    knots = target["knots"]
    if not _is_sequence(knots) or len(knots) != len(controls) + degree + 1:
        _schema_error(f"{path}.knots has the wrong length")
    previous = -math.inf
    for index, value in enumerate(knots):
        current = _finite(value, f"{path}.knots[{index}]")
        if current < previous:
            _schema_error(f"{path}.knots must be nondecreasing")
        previous = current
    if (
        any(abs(float(value)) > 1.0e-12 for value in knots[: degree + 1])
        or any(abs(float(value) - 1.0) > 1.0e-12 for value in knots[-degree - 1 :])
    ):
        _schema_error(f"{path}.knots must be clamped to the normalized [0, 1] domain")
    authoritative_samples = _sample_source_nurbs_curve(target, len(samples))
    sample_residual = max(
        _distance(actual, expected)
        for actual, expected in zip(samples, authoritative_samples)
    )
    if sample_residual > source_tolerance_mm + 1.0e-9:
        _schema_error(
            f"{path}.sample_points_local_mm must be evaluated from the authoritative NURBS curve"
        )

    evidence = _require_mapping(target["fit_evidence"], f"{path}.fit_evidence")
    evidence_keys = {
        "method",
        "source_edge_ids",
        "source_points_local_mm",
        "residual",
        "tolerance_mm",
        "coordinate_frame",
        "units",
        "provenance",
    }
    _require_keys(evidence, evidence_keys, evidence_keys, f"{path}.fit_evidence")
    if evidence["method"] != _TASK7_EDGE_FIT_METHOD:
        _schema_error(f"{path}.fit_evidence.method is not the strict Task 7 fit method")
    evidence_source_ids = _source_ids(
        evidence["source_edge_ids"], f"{path}.fit_evidence.source_edge_ids"
    )
    if evidence_source_ids != sorted(set(segment_source_edge_ids)):
        _schema_error(f"{path}.fit_evidence.source_edge_ids must match the source segment")
    source_points = evidence["source_points_local_mm"]
    if not _is_sequence(source_points) or len(source_points) < 2:
        _schema_error(f"{path}.fit_evidence.source_points_local_mm is required")
    for index, point in enumerate(source_points):
        _point(point, 2, f"{path}.fit_evidence.source_points_local_mm[{index}]")
    if _stable_hash(source_points) != _stable_hash(segment_points):
        _schema_error(
            f"{path}.fit_evidence.source_points_local_mm must match the Task 7 source segment"
        )
    fit_tolerance_mm = _positive(
        evidence["tolerance_mm"], f"{path}.fit_evidence.tolerance_mm"
    )
    if fit_tolerance_mm > source_tolerance_mm + 1.0e-12:
        _schema_error(f"{path}.fit_evidence.tolerance_mm exceeds the source tolerance")
    if evidence["coordinate_frame"] != _TASK7_EDGE_COORDINATE_FRAME:
        _schema_error(f"{path}.fit_evidence.coordinate_frame is not Task 7 local S-Q")
    units = _require_mapping(evidence["units"], f"{path}.fit_evidence.units")
    _require_keys(
        units,
        set(_TASK7_EDGE_UNITS),
        set(_TASK7_EDGE_UNITS),
        f"{path}.fit_evidence.units",
    )
    if dict(units) != _TASK7_EDGE_UNITS:
        _schema_error(f"{path}.fit_evidence.units must use Task 7 normalized S-Q millimetres")

    residual = _require_mapping(evidence["residual"], f"{path}.fit_evidence.residual")
    residual_keys = {
        "rms_mm",
        "maximum_mm",
        "source_to_fit_maximum_mm",
        "fit_to_source_maximum_mm",
    }
    _require_keys(
        residual, residual_keys, residual_keys, f"{path}.fit_evidence.residual"
    )
    residual_values = {
        key: _nonnegative(value, f"{path}.fit_evidence.residual.{key}")
        for key, value in residual.items()
    }
    if residual_values["maximum_mm"] + 1.0e-12 < max(
        residual_values["rms_mm"],
        residual_values["source_to_fit_maximum_mm"],
        residual_values["fit_to_source_maximum_mm"],
    ):
        _schema_error(f"{path}.fit_evidence.residual.maximum_mm is inconsistent")
    if residual_values["maximum_mm"] > fit_tolerance_mm + 1.0e-12:
        _schema_error(f"{path}.fit_evidence.residual exceeds its fit tolerance")

    provenance = _require_mapping(
        evidence["provenance"], f"{path}.fit_evidence.provenance"
    )
    provenance_keys = {
        "authority",
        "source_segment_name",
        "source_edge_ids",
        "source_points_sha256",
        "nurbs_authority_sha256",
    }
    _require_keys(
        provenance,
        provenance_keys,
        provenance_keys,
        f"{path}.fit_evidence.provenance",
    )
    nurbs_digest = hashlib.sha256(
        _authoritative_nurbs_json(target).encode("utf-8")
    ).hexdigest()
    if (
        provenance["authority"] != _TASK7_EDGE_PROVENANCE_AUTHORITY
        or provenance["source_segment_name"] != segment_name
        or _source_ids(
            provenance["source_edge_ids"],
            f"{path}.fit_evidence.provenance.source_edge_ids",
        )
        != evidence_source_ids
        or provenance["source_points_sha256"] != _stable_hash(source_points)
        or provenance["nurbs_authority_sha256"] != nurbs_digest
    ):
        _schema_error(f"{path}.fit_evidence.provenance does not authenticate its Task 7 fit")

    fit_curve = {
        "components": [
            {"coefficient": 1.0, "station_h": None, "target": target}
        ],
        "source_ids": evidence_source_ids,
    }
    fit_certificate = _certified_curve_to_polyline_distance(
        fit_curve,
        source_points,
        gate_limit_mm=fit_tolerance_mm,
        convergence_mm=min(_CURVE_DISTANCE_CONVERGENCE_MM, 0.25 * fit_tolerance_mm),
    )
    if fit_certificate["upper_bound_mm"] > fit_tolerance_mm + 1.0e-12:
        _schema_error(f"{path} is not within tolerance of its authenticated Task 7 source segment")


def _validate_sample_series(record: Any, value_key: str, path: str) -> None:
    _require_mapping(record, path)
    _require_keys(record, {"samples", "source_ids"}, {"samples", "source_ids"}, path)
    _source_ids(record["source_ids"], f"{path}.source_ids")
    samples = record["samples"]
    if not _is_sequence(samples) or len(samples) < 5:
        _schema_error(f"{path}.samples must contain at least five samples")
    previous = -math.inf
    for index, sample in enumerate(samples):
        sample_path = f"{path}.samples[{index}]"
        _require_mapping(sample, sample_path)
        _require_keys(sample, {"s", value_key}, {"s", value_key}, sample_path)
        s = _finite(sample["s"], f"{sample_path}.s")
        _finite(sample[value_key], f"{sample_path}.{value_key}")
        if not 0.0 <= s <= 1.0 or s <= previous:
            _schema_error(f"{path}.samples must have unique increasing s in [0, 1]")
        previous = s


def _validate_thickness_series(record: Any, path: str) -> None:
    _require_mapping(record, path)
    _require_keys(record, {"samples", "source_ids", "method"}, {"samples", "source_ids", "method"}, path)
    if record["method"] != "camber_normal_line_intersections":
        _schema_error(f"{path}.method must use camber-normal intersections")
    _source_ids(record["source_ids"], f"{path}.source_ids")
    samples = record["samples"]
    if not _is_sequence(samples) or len(samples) < 5:
        _schema_error(f"{path}.samples must contain at least five samples")
    previous = -math.inf
    for index, sample in enumerate(samples):
        sample_path = f"{path}.samples[{index}]"
        _require_mapping(sample, sample_path)
        _require_keys(sample, {"s", "thickness_mm", "inside_source_loop"}, {"s", "thickness_mm", "inside_source_loop"}, sample_path)
        s = _finite(sample["s"], f"{sample_path}.s")
        _positive(sample["thickness_mm"], f"{sample_path}.thickness_mm")
        if sample["inside_source_loop"] is not True:
            raise V112MappingError(
                "v116_v112_mapping_residual_exceeded",
                f"{sample_path} is not a positive material-domain normal hit",
            )
        if not 0.0 <= s <= 1.0 or s <= previous:
            _schema_error(f"{path}.samples must have unique increasing s in [0, 1]")
        previous = s


def _validate_attachments(attachments: Any, topology: Mapping[str, Any]) -> None:
    _require_mapping(attachments, "attachments")
    expected = {"root"}
    if topology["mode"] == "closed":
        expected.add("shroud")
    _require_keys(attachments, expected, expected, "attachments")
    for name, record in attachments.items():
        path = f"attachments.{name}"
        _require_mapping(record, path)
        _require_keys(
            record,
            {"lift_samples_mm", "width_samples_mm", "source_ids", "source_measurement", "promotable", "material_side"},
            {"lift_samples_mm", "width_samples_mm", "source_ids", "source_measurement", "promotable", "material_side"},
            path,
        )
        for key in ("lift_samples_mm", "width_samples_mm"):
            values = record[key]
            if not _is_sequence(values) or len(values) < 3:
                _schema_error(f"{path}.{key} must contain at least three source samples")
            for index, value in enumerate(values):
                _positive(value, f"{path}.{key}[{index}]")
        if record["source_measurement"] is not True or record["promotable"] is not True:
            raise V112MappingError(
                "v116_v112_material_measurement_missing",
                f"{path} lacks promotable source adjacency measurement",
            )
        if record["material_side"] not in {-1, 1}:
            _schema_error(f"{path}.material_side must be -1 or 1")
        _source_ids(record["source_ids"], f"{path}.source_ids")


def _validate_initial_guess(initial_guess: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if initial_guess is None:
        return None
    _require_mapping(initial_guess, "initial_guess")
    _require_keys(initial_guess, {"parameters", "defaults", "source_preset_id"}, set(), "initial_guess")
    result = deepcopy(dict(initial_guess))
    parameters = result.get("parameters", {})
    defaults = result.get("defaults", {})
    _require_mapping(parameters, "initial_guess.parameters")
    _require_mapping(defaults, "initial_guess.defaults")
    forbidden_parameters = set(parameters) - RUNTIME_PARAMETER_KEYS
    forbidden_defaults = set(defaults) - DEFAULT_KEYS
    if forbidden_parameters or forbidden_defaults:
        raise V112MappingError(
            "v116_v112_forbidden_parameter",
            "initial_guess contains non-V1.1.2 parameters",
            {
                "forbidden_parameters": sorted(forbidden_parameters),
                "forbidden_defaults": sorted(forbidden_defaults),
            },
        )
    return result


def _normalized_bundle_order(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(bundle)
    normalized["provenance"]["source_entity_ids"] = sorted(
        set(normalized["provenance"]["source_entity_ids"])
    )
    for name in sorted(normalized["section_families"]):
        family = normalized["section_families"][name]
        family["stations"] = sorted(family["stations"], key=lambda station: station["h"])
        for station in family["stations"]:
            for role, value_key in (("camber", "q_mm"), ("pose", "theta_deg")):
                station[role]["samples"] = sorted(
                    station[role]["samples"], key=lambda sample: sample["s"]
                )
            station["normal_thickness"]["samples"] = sorted(
                station["normal_thickness"]["samples"], key=lambda sample: sample["s"]
            )
    normalized["section_families"] = {
        name: normalized["section_families"][name]
        for name in sorted(normalized["section_families"], key=lambda item: (item != "main", item))
    }
    return normalized


def _assert_output_whitelists(
    parameters: Mapping[str, Any], defaults: Mapping[str, Any]
) -> None:
    forbidden_parameters = set(parameters) - RUNTIME_PARAMETER_KEYS
    forbidden_defaults = set(defaults) - DEFAULT_KEYS
    if forbidden_parameters or forbidden_defaults:
        raise V112MappingError(
            "v116_v112_forbidden_parameter",
            "mapping attempted to emit a non-V1.1.2 constructor field",
            {
                "forbidden_parameters": sorted(forbidden_parameters),
                "forbidden_defaults": sorted(forbidden_defaults),
            },
        )
    if tuple(defaults.get("span_stations_h", ())) != CANONICAL_STATIONS_H:
        raise V112MappingError(
            "v116_v112_forbidden_parameter",
            "adaptive measurement stations cannot replace the fixed V1.1.2 stations",
        )


def _assert_output_limits_and_material_domain(
    parameters: Mapping[str, Any],
    defaults: Mapping[str, Any],
    topology: Mapping[str, Any],
) -> None:
    violations: list[dict[str, Any]] = []
    for name, value in parameters.items():
        limits = IMPELLER_PARAMETER_LIMITS.get(name)
        if limits is None:
            violations.append({"field": name, "reason": "missing_runtime_limit"})
            continue
        numeric = float(value)
        if numeric < float(limits["min"]) or numeric > float(limits["max"]):
            violations.append(
                {
                    "field": name,
                    "value": numeric,
                    "minimum": float(limits["min"]),
                    "maximum": float(limits["max"]),
                }
            )
    blade_count = parameters.get("blade_count")
    if isinstance(blade_count, bool) or int(blade_count) != float(blade_count):
        violations.append({"field": "blade_count", "reason": "integer_required"})
    main_count = defaults.get("main_blade_count")
    splitter_count = defaults.get("splitter_blade_count")
    for name, value in (
        ("main_blade_count", main_count),
        ("splitter_blade_count", splitter_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            violations.append({"field": name, "reason": "nonnegative_integer_required"})
    if (
        isinstance(main_count, int)
        and isinstance(splitter_count, int)
        and int(parameters["blade_count"]) != main_count + splitter_count
    ):
        violations.append(
            {
                "field": "blade_count",
                "reason": "population_sum_mismatch",
                "main_blade_count": main_count,
                "splitter_blade_count": splitter_count,
            }
        )
    if violations:
        raise V112MappingError(
            "v116_v112_parameter_limit_failed",
            "mapped V1.1.2 output violates runtime parameter limits",
            {"violations": violations},
        )

    positive_defaults = (
        "average_blade_thickness_mm",
        "maximum_blade_thickness_mm",
        "root_attachment_width_mm",
        "root_attachment_lift_mm",
        "root_blade_lift_mm",
    )
    if topology["mode"] == "closed":
        positive_defaults += (
            "shroud_attachment_width_mm",
            "shroud_blade_inset_mm",
        )
    material_failures = [
        name
        for name in positive_defaults
        if not math.isfinite(float(defaults.get(name, 0.0)))
        or float(defaults.get(name, 0.0)) <= 0.0
    ]
    hub = np.asarray(defaults["hub_profile_rz_mm"], dtype=float)
    tip = np.asarray(defaults["tip_or_shroud_profile_rz_mm"], dtype=float)
    if hub.shape != (6, 2) or tip.shape != (6, 2) or not np.all(np.isfinite([hub, tip])):
        material_failures.append("support_profile_control_domain")
    else:
        bore = float(parameters["mounting_bore_radius_mm"])
        wall = float(parameters["hub_wall_thickness_mm"])
        if bore + wall >= float(np.min(hub[:, 0])):
            material_failures.append("mounting_bore_plus_wall_inside_hub_support")
        root_offset = float(defaults["root_blade_lift_mm"])
        tip_offset = float(defaults.get("shroud_blade_inset_mm", 0.0))
        if np.any(np.linalg.norm(tip - hub, axis=1) - root_offset - tip_offset <= 0.0):
            material_failures.append("positive_active_span")
    if material_failures:
        raise V112MappingError(
            "v116_v112_material_domain_failed",
            "mapped V1.1.2 output violates the material-domain contract",
            {"failed_constraints": sorted(set(material_failures))},
        )


def _term(
    *,
    target: Any,
    fitted: Any,
    unit: str,
    weight: Any,
    residual: Any,
    gate: Mapping[str, Any],
    source_ids: Sequence[str],
    records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
        "target": _round_tree(target),
        "fitted": _round_tree(fitted),
        "unit": unit,
        "weight": weight,
        "residual": _round_tree(residual),
        "gate": _round_tree(dict(gate)),
        "source_ids": sorted(set(str(value) for value in source_ids)),
    }
    if records is not None:
        result["records"] = _round_tree(list(records))
    return result


def _promotion_frame(
    frame: Mapping[str, Any], *, coordinate_system: str | None = None
) -> dict[str, Any]:
    selected = frame["axis_consensus"]["selected_cluster"]
    return {
        "coordinate_system": coordinate_system or frame["coordinate_system"],
        "parent_coordinate_system": frame["coordinate_system"],
        "source_to_canonical_matrix": deepcopy(frame["source_to_canonical_matrix"]),
        "source_axis_origin_mm": deepcopy(frame["source_axis_origin_mm"]),
        "source_axis_direction": deepcopy(frame["source_axis_direction"]),
        "task3_method": frame["method"],
        "task3_source_entity_ids": deepcopy(selected["source_entity_ids"]),
    }


def _promotion_units(unit: str) -> dict[str, str]:
    return {
        "target": str(unit),
        "fitted": str(unit),
        "residual": str(unit),
    }


def _attachment_residual_record(
    name: str,
    measurement: Mapping[str, Any],
    fitted_lift: float,
    fitted_width: float,
    limit: float,
) -> dict[str, Any]:
    target_lift = float(median(measurement["lift_samples_mm"]))
    target_width = float(median(measurement["width_samples_mm"]))
    lift_relative = abs(fitted_lift - target_lift) / max(target_lift, _EPSILON)
    width_relative = abs(fitted_width - target_width) / max(target_width, _EPSILON)
    return {
        "attachment": name,
        "target_lift_mm": target_lift,
        "fitted_lift_mm": fitted_lift,
        "target_width_mm": target_width,
        "fitted_width_mm": fitted_width,
        "lift_relative": lift_relative,
        "width_relative": width_relative,
        "status": "PASS" if max(lift_relative, width_relative) <= limit else "FAIL",
        "source_ids": sorted(measurement["source_ids"]),
    }


def _resampled_station_residuals(
    stations: Sequence[Mapping[str, Any]],
    h: float,
    role: str,
    fitted_at_s: Any,
) -> list[float]:
    lower, upper = _bracketing_stations(stations, h)
    lower_samples = lower[role]["samples"]
    upper_samples = upper[role]["samples"]
    value_key = "q_mm" if role == "camber" else "theta_deg" if role == "pose" else "thickness_mm"
    s_values = sorted(
        set(sample["s"] for sample in lower_samples)
        | set(sample["s"] for sample in upper_samples)
    )
    alpha = 0.0 if upper["h"] == lower["h"] else (h - lower["h"]) / (upper["h"] - lower["h"])
    residuals = []
    for s in s_values:
        lower_value = _interpolate_samples(lower_samples, s, value_key)
        upper_value = _interpolate_samples(upper_samples, s, value_key)
        target = (1.0 - alpha) * lower_value + alpha * upper_value
        residuals.append(float(fitted_at_s(s)) - target)
    return residuals


def _fixed_solver_stations(
    stations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for h in CANONICAL_STATIONS_H:
        lower, upper = _bracketing_stations(stations, h)
        alpha = (
            0.0
            if upper["h"] == lower["h"]
            else (h - lower["h"]) / (upper["h"] - lower["h"])
        )
        station: dict[str, Any] = {
            "h": h,
            "source_ids": sorted(
                set(lower.get("source_ids", ())) | set(upper.get("source_ids", ()))
            ),
        }
        for role, value_key in (
            ("camber", "q_mm"),
            ("pose", "theta_deg"),
            ("normal_thickness", "thickness_mm"),
        ):
            lower_samples = lower[role]["samples"]
            upper_samples = upper[role]["samples"]
            s_values = sorted(
                set(sample["s"] for sample in lower_samples)
                | set(sample["s"] for sample in upper_samples)
            )
            samples = []
            for s in s_values:
                value = (1.0 - alpha) * _interpolate_samples(
                    lower_samples, s, value_key
                ) + alpha * _interpolate_samples(upper_samples, s, value_key)
                sample = {"s": s, value_key: value}
                if role == "normal_thickness":
                    sample["inside_source_loop"] = True
                samples.append(sample)
            station[role] = {
                "samples": samples,
                "source_ids": sorted(
                    set(lower[role].get("source_ids", ()))
                    | set(upper[role].get("source_ids", ()))
                ),
            }
        result.append(station)
    return result


def _bracketing_stations(
    stations: Sequence[Mapping[str, Any]], h: float
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    ordered = sorted(stations, key=lambda station: station["h"])
    if h <= ordered[0]["h"]:
        return ordered[0], ordered[0]
    if h >= ordered[-1]["h"]:
        return ordered[-1], ordered[-1]
    for lower, upper in zip(ordered, ordered[1:]):
        if lower["h"] <= h <= upper["h"]:
            return lower, upper
    return ordered[-1], ordered[-1]


def _interpolate_samples(samples: Sequence[Mapping[str, Any]], s: float, key: str) -> float:
    ordered = sorted(samples, key=lambda sample: sample["s"])
    if s <= ordered[0]["s"]:
        return float(ordered[0][key])
    if s >= ordered[-1]["s"]:
        return float(ordered[-1][key])
    for left, right in zip(ordered, ordered[1:]):
        if left["s"] <= s <= right["s"]:
            alpha = (s - left["s"]) / max(right["s"] - left["s"], _EPSILON)
            return (1.0 - alpha) * float(left[key]) + alpha * float(right[key])
    return float(ordered[-1][key])


def _station_quadrature_weights(stations: Sequence[Mapping[str, Any]]) -> list[float]:
    h_values = [float(station["h"]) for station in stations]
    if len(h_values) < 2:
        return [1.0]
    weights = []
    for index, h in enumerate(h_values):
        if index == 0:
            weights.append(0.5 * (h_values[1] - h))
        elif index == len(h_values) - 1:
            weights.append(0.5 * (h - h_values[index - 1]))
        else:
            weights.append(0.5 * (h_values[index + 1] - h_values[index - 1]))
    total = sum(weights)
    return [_round(weight / max(total, _EPSILON), 12) for weight in weights]


def _fixed_measurement_mean_thickness(bundle: Mapping[str, Any]) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    families = bundle["section_families"]
    family_weight = 1.0 / max(len(families), 1)
    for family in families.values():
        fixed = _fixed_solver_stations(family["stations"])
        for station, station_weight in zip(fixed, _station_quadrature_weights(fixed)):
            samples = station["normal_thickness"]["samples"]
            sample_weight = family_weight * station_weight / max(len(samples), 1)
            for sample in samples:
                weighted_sum += sample_weight * float(sample["thickness_mm"])
                weight_sum += sample_weight
    return float(weighted_sum / max(weight_sum, _EPSILON))


def _evaluate_field(surface: Mapping[str, Any], s: float, h: float) -> list[float]:
    grid = surface["control_points"]
    degree_s = int(surface.get("degree_u", surface.get("degree_s", 1)))
    degree_h = int(surface.get("degree_v", surface.get("degree_h", 1)))
    if len(grid) >= degree_s + 1 and len(grid[0]) >= degree_h + 1:
        return evaluate_nurbs_surface(dict(surface), s, h)
    if len(grid) >= degree_h + 1 and len(grid[0]) >= degree_s + 1:
        transposed = deepcopy(dict(surface))
        transposed["control_points"] = [
            [deepcopy(grid[h_index][s_index]) for h_index in range(len(grid))]
            for s_index in range(len(grid[0]))
        ]
        weights = surface.get("weights")
        if weights:
            transposed["weights"] = [
                [float(weights[h_index][s_index]) for h_index in range(len(weights))]
                for s_index in range(len(weights[0]))
            ]
        transposed["degree_u"] = degree_s
        transposed["degree_v"] = degree_h
        transposed["knots_u"] = "clamped_uniform"
        transposed["knots_v"] = "clamped_uniform"
        return evaluate_nurbs_surface(transposed, s, h)
    raise V112MappingError(
        "v116_v112_canonical_patch_mismatch",
        "V1.1.2 canonical field control net is incompatible with its degrees",
    )


def _generation_bound_loop_family(
    parameters: Mapping[str, Any], defaults: Mapping[str, Any]
) -> dict[str, Any]:
    return _cached_generation_bound_loop_family(
        json.dumps(_round_tree(parameters), sort_keys=True, separators=(",", ":")),
        json.dumps(_round_tree(defaults), sort_keys=True, separators=(",", ":")),
    )


@lru_cache(maxsize=32)
def _cached_generation_bound_loop_family(
    parameters_json: str, defaults_json: str
) -> dict[str, Any]:
    return build_v11_blade_to_blade_loop_family(
        json.loads(parameters_json),
        json.loads(defaults_json),
    )


def _sample_source_nurbs_curve(
    target: Mapping[str, Any], sample_count: int
) -> list[list[float]]:
    parameters = tuple(
        index / max(sample_count - 1, 1) for index in range(sample_count)
    )
    return _evaluate_cached_source_nurbs(target, parameters)


def _authoritative_nurbs_json(target: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "degree": int(target["degree"]),
            "knots": list(target["knots"]),
            "weights": list(target["weights"]),
            "control_points": deepcopy(target["control_points_local_mm"]),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _evaluate_cached_source_nurbs(
    target: Mapping[str, Any], parameters: tuple[float, ...]
) -> list[list[float]]:
    return [
        list(point)
        for point in _cached_source_nurbs_evaluations(
            _authoritative_nurbs_json(target), parameters
        )
    ]


@lru_cache(maxsize=2048)
def _cached_source_nurbs_evaluations(
    curve_json: str, parameters: tuple[float, ...]
) -> tuple[tuple[float, ...], ...]:
    curve = json.loads(curve_json)
    return tuple(
        tuple(evaluate_nurbs_curve(curve, value)) for value in parameters
    )


def _source_edge_curve_at_h(
    stations: Sequence[Mapping[str, Any]], h: float, edge_name: str
) -> dict[str, Any]:
    lower, upper = _bracketing_stations(stations, h)
    lower_segment = lower["decomposition"]["segments"][edge_name]
    upper_segment = upper["decomposition"]["segments"][edge_name]
    lower_h = float(lower["h"])
    upper_h = float(upper["h"])
    alpha = 0.0 if upper_h == lower_h else (h - lower_h) / (upper_h - lower_h)
    components = [
        {
            "coefficient": 1.0 - alpha,
            "station_h": lower_h,
            "target": lower_segment["nurbs_target"],
            "source_edge_ids": lower_segment["source_edge_ids"],
            "source_face_ids": lower_segment["source_face_ids"],
        }
    ]
    if upper_h != lower_h:
        components.append(
            {
                "coefficient": alpha,
                "station_h": upper_h,
                "target": upper_segment["nurbs_target"],
                "source_edge_ids": upper_segment["source_edge_ids"],
                "source_face_ids": upper_segment["source_face_ids"],
            }
        )
    active_components = [
        component
        for component in components
        if float(component["coefficient"]) > _EPSILON
    ]
    source_edge_ids = sorted(
        {
            source_id
            for component in active_components
            for source_id in component["source_edge_ids"]
        }
    )
    source_face_ids = sorted(
        {
            source_id
            for component in active_components
            for source_id in component["source_face_ids"]
        }
    )
    return {
        "components": active_components,
        "source_edge_ids": source_edge_ids,
        "source_face_ids": source_face_ids,
        "source_ids": sorted(set(source_edge_ids) | set(source_face_ids)),
    }


def _source_curve_intervals(
    curve: Mapping[str, Any],
) -> list[tuple[float, float]]:
    parameters = {0.0, 1.0}
    for component in curve["components"]:
        parameters.update(
            float(value)
            for value in component["target"]["knots"]
            if 0.0 <= float(value) <= 1.0
        )
    ordered = sorted(parameters)
    return [
        (left, right)
        for left, right in zip(ordered, ordered[1:])
        if right - left > _EPSILON
    ]


def _evaluate_source_curve(curve: Mapping[str, Any], parameter: float) -> np.ndarray:
    value = np.zeros(2, dtype=float)
    for component in curve["components"]:
        point = _evaluate_cached_source_nurbs(
            component["target"], (float(parameter),)
        )[0]
        value += float(component["coefficient"]) * np.asarray(point, dtype=float)
    return value


def _source_curve_speed_bound(
    curve: Mapping[str, Any], start: float, end: float
) -> float:
    return sum(
        float(component["coefficient"])
        * _nurbs_speed_bound(component["target"], start, end)
        for component in curve["components"]
    )


def _nurbs_speed_bound(
    target: Mapping[str, Any], start: float, end: float
) -> float:
    degree = int(target["degree"])
    knots = np.asarray(target["knots"], dtype=float)
    controls = np.asarray(target["control_points_local_mm"], dtype=float)
    weights = np.asarray(target["weights"], dtype=float)
    midpoint = 0.5 * (float(start) + float(end))
    origin = controls[0]
    homogeneous_points = weights[:, None] * (controls - origin)

    numerator_derivatives = []
    weight_derivatives = []
    for index in range(len(controls) - 1):
        denominator = knots[index + degree + 1] - knots[index + 1]
        if denominator <= _EPSILON:
            numerator_derivatives.append(np.zeros(2, dtype=float))
            weight_derivatives.append(0.0)
            continue
        scale = degree / denominator
        numerator_derivatives.append(
            scale * (homogeneous_points[index + 1] - homogeneous_points[index])
        )
        weight_derivatives.append(scale * (weights[index + 1] - weights[index]))

    active = _active_basis_indices(knots, degree, len(controls), midpoint)
    derivative_knots = knots[1:-1]
    derivative_active = _active_basis_indices(
        derivative_knots,
        degree - 1,
        len(numerator_derivatives),
        midpoint,
    )
    minimum_weight = float(np.min(weights[active]))
    maximum_weight = float(np.max(weights[active]))
    numerator_bound = max(
        float(np.linalg.norm(homogeneous_points[index])) for index in active
    )
    numerator_derivative_bound = max(
        float(np.linalg.norm(numerator_derivatives[index]))
        for index in derivative_active
    )
    weight_derivative_bound = max(
        abs(float(weight_derivatives[index])) for index in derivative_active
    )
    return (
        numerator_derivative_bound * maximum_weight
        + numerator_bound * weight_derivative_bound
    ) / (minimum_weight * minimum_weight)


def _active_basis_indices(
    knots: np.ndarray, degree: int, control_count: int, parameter: float
) -> list[int]:
    active = [
        index
        for index in range(control_count)
        if knots[index] <= parameter < knots[index + degree + 1]
    ]
    if not active and abs(parameter - 1.0) <= 1.0e-12:
        active = [control_count - 1]
    if not active:
        raise V112MappingError(
            "v116_v112_measurement_schema_invalid",
            "NURBS authority has no active basis on its normalized domain",
        )
    return active


def _source_curve_as_polyline(
    curve: Mapping[str, Any],
) -> list[list[float]] | None:
    components = curve["components"]
    first = components[0]["target"]
    first_knots = [float(value) for value in first["knots"]]
    control_count = len(first["control_points_local_mm"])
    controls = np.zeros((control_count, 2), dtype=float)
    for component in components:
        target = component["target"]
        weights = np.asarray(target["weights"], dtype=float)
        if (
            int(target["degree"]) != 1
            or len(target["control_points_local_mm"]) != control_count
            or [float(value) for value in target["knots"]] != first_knots
            or float(np.max(weights) - np.min(weights)) > 1.0e-12
        ):
            return None
        controls += float(component["coefficient"]) * np.asarray(
            target["control_points_local_mm"], dtype=float
        )
    return controls.tolist()


def _source_curve_display_points(curve: Mapping[str, Any]) -> list[list[float]]:
    polyline = _source_curve_as_polyline(curve)
    if polyline is not None:
        return _round_tree_digits(polyline, 9)
    parameters = set()
    for start, end in _source_curve_intervals(curve):
        parameters.update(
            (start, 0.75 * start + 0.25 * end, 0.5 * (start + end), 0.25 * start + 0.75 * end, end)
        )
    return [
        [_round(float(value), 9) for value in _evaluate_source_curve(curve, parameter)]
        for parameter in sorted(parameters)
    ]


def _source_curve_authorities(curve: Mapping[str, Any]) -> list[dict[str, Any]]:
    authorities = []
    for component in curve["components"]:
        target = component["target"]
        controls = deepcopy(target["control_points_local_mm"])
        authorities.append(
            {
                "interpolation_coefficient": _round(
                    float(component["coefficient"]), 12
                ),
                "source_station_h": component["station_h"],
                "degree": int(target["degree"]),
                "controls": controls,
                "control_points_local_mm": controls,
                "knots": deepcopy(target["knots"]),
                "weights": deepcopy(target["weights"]),
                "fit_evidence": deepcopy(target["fit_evidence"]),
                "source_edge_ids": deepcopy(component["source_edge_ids"]),
                "source_face_ids": deepcopy(component["source_face_ids"]),
                "source_ids": sorted(
                    set(component["source_edge_ids"])
                    | set(component["source_face_ids"])
                ),
            }
        )
    return authorities


def _generated_cap_polyline_at_h(
    blade: Mapping[str, Any], h: float, edge_name: str
) -> list[list[float]]:
    loops = sorted(blade["loops"], key=lambda loop: float(loop["h"]))
    lower, upper = _bracketing_stations(loops, h)
    lower_points = _generated_cap_local_points(lower, edge_name)
    if float(lower["h"]) == float(upper["h"]):
        return _round_tree_digits(lower_points, 9)
    upper_points = _generated_cap_local_points(upper, edge_name)
    count = max(len(lower_points), len(upper_points))
    lower_points = _resample_polyline(lower_points, count)
    upper_points = _resample_polyline(upper_points, count)
    alpha = (h - float(lower["h"])) / (float(upper["h"]) - float(lower["h"]))
    return [
        [
            _round((1.0 - alpha) * left[0] + alpha * right[0], 9),
            _round((1.0 - alpha) * left[1] + alpha * right[1], 9),
        ]
        for left, right in zip(lower_points, upper_points)
    ]


def _certified_curve_to_polyline_distance(
    curve: Mapping[str, Any],
    polyline: Sequence[Sequence[float]],
    *,
    gate_limit_mm: float,
    convergence_mm: float = _CURVE_DISTANCE_CONVERGENCE_MM,
) -> dict[str, Any]:
    fitted = np.asarray(polyline, dtype=float)
    if fitted.ndim != 2 or fitted.shape[0] < 2 or fitted.shape[1] != 2:
        _schema_error("edge comparison polyline must contain at least two local S-Q points")
    exact_polyline = _source_curve_as_polyline(curve)
    if exact_polyline is not None and _same_polyline_geometry(exact_polyline, fitted):
        directed = {
            "lower_bound_mm": 0.0,
            "upper_bound_mm": 0.0,
            "convergence_gap_mm": 0.0,
            "subdivision_count": 0,
            "evaluation_count": 0,
            "converged": True,
            "decision_certified": True,
        }
        target_to_fitted = dict(directed)
        fitted_to_target = dict(directed)
    else:
        target_to_fitted = _directed_curve_distance_bounds(
            intervals=_source_curve_intervals(curve),
            evaluate=lambda parameter: _evaluate_source_curve(curve, parameter),
            speed_bound=lambda start, end: _source_curve_speed_bound(
                curve, start, end
            ),
            point_distance_bounds=lambda point: (
                _point_to_polyline_distance(point, fitted),
                _point_to_polyline_distance(point, fitted),
                1,
            ),
            gate_limit_mm=gate_limit_mm,
            convergence_mm=convergence_mm,
        )
        fitted_to_target = _directed_curve_distance_bounds(
            intervals=[(float(index), float(index + 1)) for index in range(len(fitted) - 1)],
            evaluate=lambda parameter: _evaluate_polyline_parameter(fitted, parameter),
            speed_bound=lambda start, end: _polyline_speed_bound(fitted, start, end),
            point_distance_bounds=lambda point: _point_to_source_curve_distance_bounds(
                point, curve, convergence_mm=max(0.25 * convergence_mm, 1.0e-6)
            ),
            gate_limit_mm=gate_limit_mm,
            convergence_mm=convergence_mm,
        )
    lower = max(
        target_to_fitted["lower_bound_mm"],
        fitted_to_target["lower_bound_mm"],
    )
    upper = max(
        target_to_fitted["upper_bound_mm"],
        fitted_to_target["upper_bound_mm"],
    )
    return _round_tree(
        {
            "method": _CURVE_DISTANCE_METHOD,
            "metric": "continuous_bidirectional_curve_distance_upper_mm",
            "gate_limit_mm": gate_limit_mm,
            "convergence_tolerance_mm": convergence_mm,
            "lower_bound_mm": lower,
            "upper_bound_mm": upper,
            "convergence_gap_mm": max(0.0, upper - lower),
            "converged": target_to_fitted["converged"]
            and fitted_to_target["converged"],
            "decision_certified": upper <= gate_limit_mm or lower > gate_limit_mm,
            "gate_status": "PASS" if upper <= gate_limit_mm else "FAIL",
            "target_to_fitted": target_to_fitted,
            "fitted_to_target": fitted_to_target,
        }
    )


def _directed_curve_distance_bounds(
    *,
    intervals: Sequence[tuple[float, float]],
    evaluate: Callable[[float], np.ndarray],
    speed_bound: Callable[[float, float], float],
    point_distance_bounds: Callable[[np.ndarray], tuple[float, float, int]],
    gate_limit_mm: float,
    convergence_mm: float,
) -> dict[str, Any]:
    evaluation_count = 0

    def state(start: float, end: float) -> dict[str, float]:
        nonlocal evaluation_count
        midpoint = 0.5 * (start + end)
        point = evaluate(midpoint)
        lower, upper, evaluations = point_distance_bounds(point)
        evaluation_count += evaluations
        radius = speed_bound(start, end) * 0.5 * (end - start)
        return {
            "start": start,
            "end": end,
            "lower": lower,
            "upper": upper + radius,
        }

    states = [state(start, end) for start, end in intervals]
    subdivisions = 0
    converged = False
    while states:
        lower = max(item["lower"] for item in states)
        upper = max(item["upper"] for item in states)
        if upper - lower <= convergence_mm:
            converged = True
            break
        if upper <= gate_limit_mm or lower > gate_limit_mm:
            break
        if subdivisions >= _CURVE_DISTANCE_MAX_SUBDIVISIONS:
            break
        index = max(range(len(states)), key=lambda item: states[item]["upper"])
        selected = states.pop(index)
        midpoint = 0.5 * (selected["start"] + selected["end"])
        if midpoint <= selected["start"] or midpoint >= selected["end"]:
            states.append(selected)
            break
        states.extend(
            (
                state(selected["start"], midpoint),
                state(midpoint, selected["end"]),
            )
        )
        subdivisions += 1
    lower = max((item["lower"] for item in states), default=0.0)
    upper = max((item["upper"] for item in states), default=0.0)
    return _round_tree(
        {
            "lower_bound_mm": lower,
            "upper_bound_mm": upper,
            "convergence_gap_mm": max(0.0, upper - lower),
            "subdivision_count": subdivisions,
            "evaluation_count": evaluation_count,
            "converged": converged,
            "decision_certified": upper <= gate_limit_mm or lower > gate_limit_mm,
        }
    )


def _point_to_source_curve_distance_bounds(
    point: np.ndarray,
    curve: Mapping[str, Any],
    *,
    convergence_mm: float,
) -> tuple[float, float, int]:
    exact_polyline = _source_curve_as_polyline(curve)
    if exact_polyline is not None:
        distance = _point_to_polyline_distance(
            point, np.asarray(exact_polyline, dtype=float)
        )
        return distance, distance, 1

    def state(start: float, end: float) -> dict[str, float]:
        midpoint = 0.5 * (start + end)
        distance = float(np.linalg.norm(point - _evaluate_source_curve(curve, midpoint)))
        radius = _source_curve_speed_bound(curve, start, end) * 0.5 * (end - start)
        return {
            "start": start,
            "end": end,
            "lower": max(0.0, distance - radius),
            "upper": distance,
        }

    states = [state(start, end) for start, end in _source_curve_intervals(curve)]
    subdivisions = 0
    while states:
        lower = min(item["lower"] for item in states)
        upper = min(item["upper"] for item in states)
        if upper - lower <= convergence_mm:
            return lower, upper, len(states) + 2 * subdivisions
        if subdivisions >= _CURVE_DISTANCE_MAX_SUBDIVISIONS:
            return lower, upper, len(states) + 2 * subdivisions
        candidates = [
            (index, item)
            for index, item in enumerate(states)
            if item["lower"] < upper - convergence_mm
        ]
        if not candidates:
            return lower, upper, len(states) + 2 * subdivisions
        index, selected = min(candidates, key=lambda item: item[1]["lower"])
        states.pop(index)
        midpoint = 0.5 * (selected["start"] + selected["end"])
        if midpoint <= selected["start"] or midpoint >= selected["end"]:
            states.append(selected)
            return lower, upper, len(states) + 2 * subdivisions
        states.extend(
            (
                state(selected["start"], midpoint),
                state(midpoint, selected["end"]),
            )
        )
        subdivisions += 1
    return 0.0, math.inf, 0


def _evaluate_polyline_parameter(polyline: np.ndarray, parameter: float) -> np.ndarray:
    index = min(max(int(math.floor(parameter)), 0), len(polyline) - 2)
    fraction = min(max(parameter - index, 0.0), 1.0)
    return (1.0 - fraction) * polyline[index] + fraction * polyline[index + 1]


def _polyline_speed_bound(
    polyline: np.ndarray, start: float, end: float
) -> float:
    index = min(max(int(math.floor(0.5 * (start + end))), 0), len(polyline) - 2)
    return float(np.linalg.norm(polyline[index + 1] - polyline[index]))


def _point_to_polyline_distance(point: np.ndarray, polyline: np.ndarray) -> float:
    starts = polyline[:-1]
    vectors = polyline[1:] - starts
    squared_lengths = np.sum(vectors * vectors, axis=1)
    fractions = np.divide(
        np.sum((point - starts) * vectors, axis=1),
        squared_lengths,
        out=np.zeros_like(squared_lengths),
        where=squared_lengths > _EPSILON,
    )
    fractions = np.clip(fractions, 0.0, 1.0)
    projections = starts + fractions[:, None] * vectors
    return float(np.min(np.linalg.norm(projections - point, axis=1)))


def _same_polyline_geometry(
    first: Sequence[Sequence[float]], second: np.ndarray
) -> bool:
    left = np.asarray(first, dtype=float)
    return left.shape == second.shape and (
        bool(np.allclose(left, second, rtol=0.0, atol=1.0e-9))
        or bool(np.allclose(left[::-1], second, rtol=0.0, atol=1.0e-9))
    )


def _source_edge_at_h(
    stations: Sequence[Mapping[str, Any]],
    h: float,
    edge_name: str,
    sample_count: int,
) -> tuple[list[list[float]], list[str]]:
    lower, upper = _bracketing_stations(stations, h)
    lower_segment = lower["decomposition"]["segments"][edge_name]
    upper_segment = upper["decomposition"]["segments"][edge_name]
    lower_points = _sample_source_nurbs_curve(
        lower_segment["nurbs_target"], sample_count
    )
    upper_points = _sample_source_nurbs_curve(
        upper_segment["nurbs_target"], sample_count
    )
    alpha = (
        0.0
        if float(upper["h"]) == float(lower["h"])
        else (h - float(lower["h"]))
        / (float(upper["h"]) - float(lower["h"]))
    )
    points = [
        [
            _round((1.0 - alpha) * left[0] + alpha * right[0], 9),
            _round((1.0 - alpha) * left[1] + alpha * right[1], 9),
        ]
        for left, right in zip(lower_points, upper_points)
    ]
    source_ids = sorted(
        set(lower_segment["source_ids"]) | set(upper_segment["source_ids"])
    )
    return points, source_ids


def _generated_cap_local_points(
    loop: Mapping[str, Any], edge_name: str
) -> list[list[float]]:
    points = loop["segments"][edge_name]["points_s_q"]
    anchor_s = 0.5 * (float(points[0][0]) + float(points[-1][0]))
    anchor_q = 0.5 * (float(points[0][1]) + float(points[-1][1]))
    scale = float(loop["streamwise_metric_scale_mm"])
    return [
        [(float(point[0]) - anchor_s) * scale, float(point[1]) - anchor_q]
        for point in points
    ]


def _resample_polyline(points: Sequence[Sequence[float]], count: int) -> list[list[float]]:
    source = np.asarray(points, dtype=float)
    segments = np.linalg.norm(np.diff(source, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(segments)))
    if cumulative[-1] <= _EPSILON:
        return [source[0].tolist() for _ in range(count)]
    targets = np.linspace(0.0, cumulative[-1], count)
    result = []
    for target in targets:
        index = min(int(np.searchsorted(cumulative, target, side="right") - 1), len(source) - 2)
        fraction = (target - cumulative[index]) / max(cumulative[index + 1] - cumulative[index], _EPSILON)
        result.append(((1.0 - fraction) * source[index] + fraction * source[index + 1]).tolist())
    return result


def _equivalent_edge_radii(
    families: Mapping[str, Mapping[str, Any]]
) -> dict[str, float]:
    radii: dict[str, list[float]] = {"leading_edge": [], "trailing_edge": []}
    for family in families.values():
        for h in CANONICAL_STATIONS_H:
            for edge_name in radii:
                points, _ = _source_edge_at_h(
                    family["stations"], h, edge_name, 129
                )
                chord = _distance(points[0], points[-1])
                midpoint = 0.5 * (np.asarray(points[0]) + np.asarray(points[-1]))
                sagitta = max(float(np.linalg.norm(np.asarray(point) - midpoint)) for point in points)
                if sagitta > _EPSILON:
                    radii[edge_name].append(chord * chord / (8.0 * sagitta) + 0.5 * sagitta)
    return {
        name: _round(min(max(float(median(values)), 0.0), 200.0), 6)
        for name, values in radii.items()
    }


def _terminal_camber_angle(
    family: Mapping[str, Any], *, leading: bool, support_points: Sequence[Sequence[float]]
) -> float:
    scale = sum(
        _distance(left, right) for left, right in zip(support_points, support_points[1:])
    )
    angles = []
    for station in _fixed_solver_stations(family["stations"]):
        samples = station["camber"]["samples"]
        left, right = (samples[0], samples[1]) if leading else (samples[-2], samples[-1])
        ds = (right["s"] - left["s"]) * max(scale, 1.0)
        dq = right["q_mm"] - left["q_mm"]
        angles.append(math.degrees(math.atan2(dq, ds)))
    return _round(min(max(float(median(angles)), -89.0), 89.0), 6)


def _mean_terminal_camber(stations: Sequence[Mapping[str, Any]]) -> float:
    fixed_stations = _fixed_solver_stations(stations)
    return _round(
        float(
            np.mean(
                [
                    max(station["camber"]["samples"], key=lambda sample: sample["s"])["q_mm"]
                    for station in fixed_stations
                ]
            )
        ),
        6,
    )


def _source_ids_for_role(bundle: Mapping[str, Any], role: str) -> list[str]:
    ids: set[str] = set()
    for family in bundle["section_families"].values():
        for station in family["stations"]:
            if role == "edge_curves":
                for edge_name in ("leading_edge", "trailing_edge"):
                    segment = station["decomposition"]["segments"][edge_name]
                    ids.update(segment["source_edge_ids"])
                    ids.update(segment["source_face_ids"])
            elif role == "normal_thickness":
                ids.update(station["normal_thickness"]["source_ids"])
            else:
                ids.update(station[role]["source_ids"])
    return sorted(ids)


def _collect_source_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {
                "source_ids",
                "source_entity_ids",
                "source_edge_ids",
                "source_face_ids",
            } and _is_sequence(item):
                result.extend(str(entry) for entry in item)
            else:
                result.extend(_collect_source_ids(item))
    elif _is_sequence(value):
        for item in value:
            result.extend(_collect_source_ids(item))
    return result


def _material_value(material: Mapping[str, Any], name: str) -> float:
    return float(material[name]["value"])


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _round_tree(value: Any) -> Any:
    return _round_tree_digits(value, 9)


def _round_tree_digits(value: Any, digits: int) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _round_tree_digits(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_tree_digits(item, digits) for item in value]
    if isinstance(value, tuple):
        return [_round_tree_digits(item, digits) for item in value]
    if isinstance(value, float):
        return _round(value, digits)
    if isinstance(value, np.generic):
        return _round(float(value), digits)
    return value


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return _round(math.sqrt(sum(float(value) ** 2 for value in values) / len(values)), 12)


def _weighted_rms(values: Sequence[float], weights: Sequence[float]) -> float:
    if not values:
        return 0.0
    total = sum(float(weight) for weight in weights)
    return _round(
        math.sqrt(
            sum(float(weight) * float(value) ** 2 for value, weight in zip(values, weights))
            / max(total, _EPSILON)
        ),
        12,
    )


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(first, second)))


def _point(value: Any, dimensions: int, path: str) -> list[float]:
    if not _is_sequence(value) or len(value) != dimensions:
        _schema_error(f"{path} must contain {dimensions} finite coordinates")
    return [_finite(item, path) for item in value]


def _source_ids(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    if not _is_sequence(value) or (not value and not allow_empty):
        qualifier = "a sequence" if allow_empty else "a non-empty sequence"
        _schema_error(f"{path} must be {qualifier}")
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        _schema_error(f"{path} contains an empty source id")
    return result


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _schema_error(f"{path} must be a mapping")
    return value


def _require_keys(
    value: Mapping[str, Any], allowed: set[str], required: set[str], path: str
) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        reason = (
            "v116_v112_forbidden_parameter"
            if any(
                token in str(key).lower()
                for key in unknown
                for token in ("surface_authority", "direct_curve", "v1_2", "pcurve", "trim")
            )
            else "v116_v112_measurement_schema_invalid"
        )
        raise V112MappingError(
            reason,
            f"{path} contains unsupported fields",
            {"unknown_fields": sorted(unknown)},
        )
    if missing:
        material_missing = "material_measurements" in path or path.startswith("attachments")
        raise V112MappingError(
            "v116_v112_material_measurement_missing"
            if material_missing
            else "v116_v112_measurement_schema_invalid",
            f"{path} is missing required fields",
            {"missing_fields": sorted(missing)},
        )


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool):
        _schema_error(f"{path} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError):
        _schema_error(f"{path} must be finite")
    if not math.isfinite(result):
        _schema_error(f"{path} must be finite")
    return result


def _positive(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result <= 0.0:
        _schema_error(f"{path} must be positive")
    return result


def _nonnegative(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result < 0.0:
        _schema_error(f"{path} must be nonnegative")
    return result


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _schema_error(message: str) -> None:
    raise V112MappingError("v116_v112_measurement_schema_invalid", message)


def _round(value: float, digits: int = 9) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded
