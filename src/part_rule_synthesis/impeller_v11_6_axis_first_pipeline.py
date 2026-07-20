from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping, NoReturn, Sequence

import numpy as np

from part_rule_synthesis import impeller_v11_6_section_recovery as section_recovery
from part_rule_synthesis import impeller_v11_6_section_curve_authority as section_curve_authority
from part_rule_synthesis import impeller_v11_6_support_recovery as support_recovery
from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_curve
from part_rule_synthesis.impeller_v11_6_comparison_scope import (
    build_supported_surface_comparison_scope,
)
from part_rule_synthesis.impeller_v11_6_meridional_mapping import (
    project_rz_points_to_meridional_s,
)
from part_rule_synthesis.impeller_v11_6_v112_mapping import (
    MEASUREMENT_SCHEMA_VERSION,
    V112MappingError,
    V112MappingTolerances,
    adapt_task7_segment_for_mapping,
    map_measurements_to_v112,
    map_measurements_to_v112_review,
)


ALGORITHM_VERSION = "axis_first_measurement_bundle_task9_r3"
_STABLE_REASONS = {
    "v116_hub_support_classification_failed",
    "v116_hub_support_circumferential_coverage_incomplete",
    "v116_hub_profile_fit_failed",
    "v116_tip_reference_inference_failed",
    "v116_shroud_topology_ambiguous",
    "v116_periodic_population_ambiguous",
    "v116_representative_blade_selection_failed",
    "v116_section_intersection_failed",
    "v116_section_loop_open",
    "v116_section_loop_correspondence_failed",
    "v116_section_tangent_flip_detected",
    "v116_span_surface_ordering_failed",
    "v116_thickness_field_invalid",
    "v116_root_attachment_measurement_failed",
    "v116_v112_canonical_hash_mismatch",
    "v116_v112_canonical_patch_mismatch",
    "v116_v112_forbidden_parameter",
    "v116_v112_mapping_solver_exception",
    "v116_v112_mapping_solver_failed",
    "v116_v112_material_domain_failed",
    "v116_v112_material_measurement_missing",
    "v116_v112_measurement_schema_invalid",
    "v116_v112_parameter_limit_failed",
    "v116_v112_topology_failed",
    "v116_v112_mapping_residual_exceeded",
    "v116_false_material_surface_forbidden",
    "v116_support_profile_orientation_failed",
    "v116_support_profile_endpoint_role_missing",
    "v116_support_profile_streamwise_mismatch",
    "v116_hub_closure_endpoint_semantics_failed",
    "v116_active_span_carrier_invalid",
}
_TASK8_RECONSTRUCTION_EVIDENCE_BASIS = (
    "v116_axis_first_periodic_material_evidence_v1"
)
_HUB_SUPPORT_MINIMUM_NORMALIZED_PITCH_COVERAGE = 0.8
_HUB_SUPPORT_PROFILE_SAMPLE_COUNT = 4097


class AxisFirstPipelineError(RuntimeError):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        stage: str,
        evidence: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason if reason in _STABLE_REASONS else _stage_reason(stage)
        self.stage = stage
        self.details = {
            **copy.deepcopy(dict(details or {})),
            "failed_stage": stage,
            "failure_evidence": copy.deepcopy(dict(evidence or {})),
        }


@dataclass(frozen=True)
class MeasurementBundleResult:
    measurements: dict[str, Any]
    support_evidence: dict[str, Any]
    periodic_evidence: dict[str, Any]
    section_evidence: dict[str, Any]
    stage_evidence: tuple[dict[str, Any], ...]


def stable_measurement_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def task8_reconstruction_evidence_hash(
    support_recovery_payload: Mapping[str, Any],
    periodic_provenance_payload: Mapping[str, Any],
    source_sha256: str,
) -> str:
    """Bind Task 9 inputs to the exact Task 8 recovery result."""

    return stable_measurement_hash(
        {
            "basis": _TASK8_RECONSTRUCTION_EVIDENCE_BASIS,
            "source_sha256": str(source_sha256),
            "support_recovery": copy.deepcopy(dict(support_recovery_payload)),
            "periodic_provenance": copy.deepcopy(
                dict(periodic_provenance_payload)
            ),
        }
    )


def preserve_task8_reconstruction_authority(
    mapping: Mapping[str, Any], source_sha256: str
) -> dict[str, Any]:
    """Capture Task 8 recovery separately before Task 9 consumes its mapping."""

    support_payload = copy.deepcopy(
        dict(mapping.get("support_recovery", {}))
    )
    periodic_payload = copy.deepcopy(
        dict(mapping.get("periodic_provenance", {}))
    )
    evidence_hash = task8_reconstruction_evidence_hash(
        support_payload,
        periodic_payload,
        source_sha256,
    )
    if mapping.get("task8_reconstruction_evidence_hash_sha256") != evidence_hash:
        raise AxisFirstPipelineError(
            "v116_v112_mapping_residual_exceeded",
            "Task 8 mapping evidence seal is inconsistent before handoff",
            stage="v112_mapping",
            evidence={"source_sha256": source_sha256},
        )
    return {
        "authority": "axis_first_task8_recovery_result",
        "source_sha256": str(source_sha256),
        "support_recovery": support_payload,
        "periodic_provenance": periodic_payload,
        "evidence_hash_sha256": evidence_hash,
    }


def build_measurement_bundle(
    source_shape: Any,
    source_manifest: Mapping[str, Any],
    frame: Mapping[str, Any],
    semantics: Mapping[str, Any],
) -> MeasurementBundleResult:
    completed: list[dict[str, Any]] = []
    try:
        inventory = _source_inventory(source_shape, source_manifest, frame, semantics)
        completed.append(_stage_record("source_inventory", inventory["provenance"]))

        support = _recover_support_evidence(inventory, frame, semantics)
        completed.append(_stage_record("support_recovery", support))

        periodic = _recover_periodic_evidence(
            inventory, frame, semantics, support=support
        )
        completed.append(_stage_record("periodic_representatives", periodic))

        sections = _recover_section_evidence(inventory, frame, support, periodic)
        completed.append(_stage_record("exact_sections", sections))

        measurements = _assemble_measurements(
            inventory, frame, support, periodic, sections
        )
        completed.append(_stage_record("measurement_bundle", measurements))
    except AxisFirstPipelineError as exc:
        exc.details["completed_stages"] = copy.deepcopy(completed)
        raise
    except (
        support_recovery.SupportRecoveryError,
        section_recovery.SectionRecoveryError,
        section_curve_authority.SectionCurveAuthorityError,
    ) as exc:
        stage = _exception_stage(exc)
        raise AxisFirstPipelineError(
            getattr(exc, "reason", _stage_reason(stage)),
            str(exc),
            stage=stage,
            evidence=getattr(exc, "details", {}),
            details={"completed_stages": copy.deepcopy(completed)},
        ) from exc
    except Exception as exc:
        stage = _next_stage(completed)
        raise AxisFirstPipelineError(
            _stage_reason(stage),
            str(exc),
            stage=stage,
            evidence={"exception_type": type(exc).__name__},
            details={"completed_stages": copy.deepcopy(completed)},
        ) from exc
    return MeasurementBundleResult(
        measurements=measurements,
        support_evidence=support,
        periodic_evidence=periodic,
        section_evidence=sections,
        stage_evidence=tuple(completed),
    )


def extract_v11_parameters(
    source_shape: Any,
    source_manifest: Mapping[str, Any],
    frame: Mapping[str, Any],
    semantics: Mapping[str, Any],
    *,
    tolerances: V112MappingTolerances | Mapping[str, Any] | None = None,
    initial_guess: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = build_measurement_bundle(source_shape, source_manifest, frame, semantics)
    try:
        mapped = map_measurements_to_v112(
            result.measurements,
            tolerances=V112MappingTolerances() if tolerances is None else tolerances,
            initial_guess=initial_guess,
        )
    except V112MappingError as exc:
        _raise_mapping_error(exc, result)
    return _enrich_mapping(mapped, result)


def extract_v11_review_parameters(
    source_shape: Any,
    source_manifest: Mapping[str, Any],
    frame: Mapping[str, Any],
    semantics: Mapping[str, Any],
    *,
    tolerances: V112MappingTolerances | Mapping[str, Any] | None = None,
    initial_guess: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a strict mapping or a clearly rejected, review-only candidate."""

    result = build_measurement_bundle(source_shape, source_manifest, frame, semantics)
    try:
        mapped = map_measurements_to_v112_review(
            result.measurements,
            tolerances=V112MappingTolerances() if tolerances is None else tolerances,
            initial_guess=initial_guess,
        )
    except V112MappingError as exc:
        _raise_mapping_error(exc, result)
    return _enrich_mapping(mapped, result)


def _raise_mapping_error(
    exc: V112MappingError, result: MeasurementBundleResult
) -> NoReturn:
    raise AxisFirstPipelineError(
        exc.reason,
        str(exc),
        stage="v112_mapping",
        evidence={
            "upstream_reason": exc.reason,
            "mapping_details": copy.deepcopy(exc.details),
        },
        details={"completed_stages": list(result.stage_evidence)},
    ) from exc


def _enrich_mapping(
    mapped: dict[str, Any], result: MeasurementBundleResult
) -> dict[str, Any]:

    parameters = mapped["parameters"]
    unsupported_audit = _unsupported_source_feature_audit(
        result.section_evidence,
        result.measurements,
    )
    support_payload = _jsonable(result.support_evidence)
    periodic_payload = _jsonable(result.periodic_evidence)
    main_count = int((periodic_payload.get("main") or {}).get("count", 0))
    splitter_count = int((periodic_payload.get("splitter") or {}).get("count", 0))
    comparison_scope = build_supported_surface_comparison_scope(
        support_payload.get("source_face_semantics", ()),
        measurements=result.measurements,
        topology_mode=str(support_payload.get("topology_mode", "")),
        expected_periodic_instance_count=main_count + splitter_count,
        periodic_populations=(
            periodic_payload.get("pattern_population_evidence", {}).get(
                "populations", ()
            )
        ),
    )
    source_sha256 = str(result.measurements["provenance"]["source_sha256"])
    direct_network = result.section_evidence.get("direct_section_curve_network")
    direct_populations = (
        direct_network.get("populations", {})
        if isinstance(direct_network, Mapping)
        else {}
    )
    direct_stations = [
        station
        for family in direct_populations.values()
        for station in family["stations"]
    ]
    if direct_stations:
        endpoint_witnesses = _semantic_endpoint_witnesses(
            result.support_evidence,
            result.measurements["topology"]["material_measurements"],
            result.section_evidence,
            source_tolerance_mm=max(
                float(station["source_tolerance_mm"])
                for station in direct_stations
            ),
        )
    else:
        endpoint_witnesses = {
            "contract_id": "impeller_v1_1_6_semantic_endpoint_witnesses_r16_1",
            "status": "NOT_AVAILABLE_LEGACY_MEASUREMENT_BUNDLE",
            "coordinate_frame": "canonical_axis_frame_xyz_mm",
            "blade_leading_boundary_witnesses": [],
        }
    mapped.update(
        {
            "mapping_id": "v116-axis-first-" + mapped["constructor_input_hash_sha256"][:12]
            if "constructor_input_hash_sha256" in mapped
            else "v116-axis-first-measurement",
            "source_basis": "authenticated_occt_axis_first_measurements",
            "geometry_version": "1.1",
            "measurement_bundle": copy.deepcopy(result.measurements),
            "support_recovery": support_payload,
            "periodic_provenance": periodic_payload,
            "task8_reconstruction_evidence_hash_sha256": (
                task8_reconstruction_evidence_hash(
                    support_payload,
                    periodic_payload,
                    source_sha256,
                )
            ),
            "section_provenance": _jsonable(result.section_evidence),
            "semantic_endpoint_witnesses": _jsonable(endpoint_witnesses),
            "pipeline_stages": list(result.stage_evidence),
            "profile_fits": copy.deepcopy(result.measurements["support_fits"]),
            "source_section_loops": copy.deepcopy(
                result.section_evidence["section_loop_records"]
            ),
            "parameter_rows": _parameter_rows_from_mapping(
                parameters,
                mapped.get("objective_terms", {}),
                result.measurements,
            ),
            "confidence_layers": {
                "source_measurement": "authenticated_occt_entity_evidence",
                "semantic_mapping": "per_objective_term",
                "v112_mapping": mapped.get("mapping_status", "PASS"),
                "reconstruction_fidelity": "reported_after_deviation",
            },
            "unsupported_source_features": unsupported_audit["features"],
            "unsupported_source_feature_audit": unsupported_audit,
            "comparison_scope": comparison_scope,
        }
    )
    return mapped


def _source_inventory(source_shape, source_manifest, frame, semantics) -> dict[str, Any]:
    face_records = list(source_manifest.get("faces", ()))
    faces = list(source_shape.Faces())
    if not face_records or len(face_records) != len(faces):
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "source manifest face inventory does not match the OCCT source shape",
            stage="source_inventory",
            evidence={
                "manifest_face_count": len(face_records),
                "shape_face_count": len(faces),
            },
        )
    faces_by_id = {
        str(record["face_id"]): face
        for record, face in zip(face_records, faces, strict=True)
    }
    records_by_id = {str(record["face_id"]): dict(record) for record in face_records}
    edges_by_id = {
        f"source_edge_{index:05d}": edge
        for index, edge in enumerate(source_shape.Edges())
    }
    face_edge_ids, edge_face_ids = _build_exact_incidence_index(
        source_shape, faces_by_id, edges_by_id
    )
    periodic = semantics.get("periodic_population_recovery", {})
    instances = [
        instance
        for population in periodic.get("populations", ())
        for instance in population.get("instances", ())
    ]
    instance_by_face: dict[str, str] = {}
    for instance in instances:
        for face_id in instance["source_face_ids"]:
            if face_id in instance_by_face:
                raise AxisFirstPipelineError(
                    "v116_periodic_population_ambiguous",
                    "one source face belongs to multiple periodic instances",
                    stage="source_inventory",
                    evidence={"source_face_id": face_id},
                )
            instance_by_face[str(face_id)] = str(instance["instance_id"])
    return {
        "shape": source_shape,
        "source_manifest": copy.deepcopy(dict(source_manifest)),
        "faces_by_id": faces_by_id,
        "records_by_id": records_by_id,
        "edges_by_id": edges_by_id,
        "face_edge_ids": face_edge_ids,
        "edge_face_ids": edge_face_ids,
        "instance_by_face": instance_by_face,
        "semantics": copy.deepcopy(dict(semantics)),
        "provenance": {
            "authority": "uploaded_step_brep",
            "source_sha256": str(source_manifest["sha256"]),
            "source_entity_ids": sorted(faces_by_id),
            "face_count": len(faces_by_id),
            "edge_count": len(edges_by_id),
            "frame_method": frame.get("method"),
        },
    }


def _build_exact_incidence_index(source_shape, faces_by_id, edges_by_id):
    """Index exact source face-edge incidence once using OCCT shape identity."""

    try:
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError as exc:  # pragma: no cover - OCCT fixture tests cover this.
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "OCCT topology indexing is required for source inventory",
            stage="source_inventory",
            evidence={"exception_type": type(exc).__name__},
        ) from exc
    edge_index = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(source_shape.wrapped, TopAbs_EDGE, edge_index)
    edge_id_by_index: dict[int, str] = {}
    for edge_id, edge in edges_by_id.items():
        index = int(edge_index.FindIndex(edge.wrapped))
        if index <= 0 or index in edge_id_by_index:
            raise AxisFirstPipelineError(
                "v116_hub_support_classification_failed",
                "source edge inventory cannot be mapped uniquely to OCCT topology",
                stage="source_inventory",
                evidence={"source_edge_id": edge_id, "occt_index": index},
            )
        edge_id_by_index[index] = edge_id
    # MapShapes also retains degenerate edge subshapes that CadQuery omits from
    # both Shape.Edges() and Face.Edges(). They do not participate in semantic
    # face adjacency. Every edge that a face exposes is still checked below.
    face_edge_ids: dict[str, tuple[str, ...]] = {}
    edge_face_ids: dict[str, list[str]] = {
        edge_id: [] for edge_id in edges_by_id
    }
    for face_id, face in faces_by_id.items():
        identifiers = []
        for edge in face.Edges():
            index = int(edge_index.FindIndex(edge.wrapped))
            edge_id = edge_id_by_index.get(index)
            if edge_id is None:
                raise AxisFirstPipelineError(
                    "v116_hub_support_classification_failed",
                    "source face references an edge outside the OCCT inventory",
                    stage="source_inventory",
                    evidence={"source_face_id": face_id, "occt_edge_index": index},
                )
            identifiers.append(edge_id)
            edge_face_ids[edge_id].append(face_id)
        face_edge_ids[face_id] = tuple(sorted(set(identifiers)))
    return (
        face_edge_ids,
        {
            edge_id: tuple(sorted(set(face_ids)))
            for edge_id, face_ids in edge_face_ids.items()
        },
    )


def _recover_support_evidence(inventory, frame, semantics) -> dict[str, Any]:
    topology = _classify_support_topology(inventory, frame, semantics)
    matrix = frame["source_to_canonical_matrix"]
    tolerance = _source_tolerance(frame)
    minimum_radius_mm = min(
        float(instance["radial_support_range_mm"][0])
        for population in semantics["periodic_population_recovery"]["populations"]
        for instance in population["instances"]
    )
    initial_hub_ids = list(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
    initial_coverage = topology.get(
        "hub_support_initial_periodic_coverage", {}
    )
    preliminary_samples = _sample_hub_source_faces(
        inventory,
        frame,
        initial_hub_ids,
        trace_count=7,
        samples_per_trace=49,
    )
    if initial_coverage.get("mode") == "periodic_passage_patches":
        preliminary_fit = _fit_preliminary_hub_support(
            preliminary_samples,
            frame,
            minimum_radius_mm=minimum_radius_mm,
        )
        deficient_instances = _initial_hub_coverage_deficiencies(
            topology,
            preliminary_samples,
        )
        candidate_ids = _hub_source_union_candidate_ids(
            inventory,
            semantics,
            topology,
            deficient_instances,
        )
    else:
        preliminary_fit = None
        candidate_ids = []
    preliminary_samples.update(
        _sample_hub_source_faces(
            inventory,
            frame,
            candidate_ids,
            trace_count=7,
            samples_per_trace=49,
        )
    )
    if preliminary_fit is None:
        p95_limit, maximum_limit = 1.0, 1.0
        profile_control_points_rz_mm = []
    else:
        p95_limit, maximum_limit = _hub_profile_conformance_limits(
            preliminary_fit,
            frame,
        )
        profile_control_points_rz_mm = preliminary_fit[
            "control_points_rz_mm"
        ]
    topology = _select_profile_conformant_hub_source_union(
        inventory,
        topology,
        sample_records_by_face=preliminary_samples,
        profile_control_points_rz_mm=profile_control_points_rz_mm,
        profile_p95_limit_mm=p95_limit,
        profile_maximum_limit_mm=maximum_limit,
    )

    assignments = _semantic_assignments(inventory, semantics, topology)
    partition = support_recovery.authenticate_occt_semantic_partition(
        inventory["shape"], face_assignments=assignments
    )
    hub_ids = list(topology["hub_support_face_ids"])
    hub_samples = _sample_hub_source_faces(
        inventory,
        frame,
        hub_ids,
        semantic_partition_evidence=partition,
        trace_count=9,
        samples_per_trace=65,
    )
    hub_fit = _fit_authenticated_support(
        [hub_samples[hub_id] for hub_id in hub_ids],
        outer_diameter_mm=2.0 * float(frame["outer_radius_mm"]),
        semantic_role="hub_profile",
        minimum_radius_mm=minimum_radius_mm,
    )

    if topology["mode"] == "open":
        tip_support, topology_result = _recover_open_tip(
            inventory, frame, semantics, topology
        )
    else:
        tip_support, topology_result = _recover_closed_shroud(
            inventory, frame, semantics, topology, partition
        )
    closure_classification = _refine_periodic_closure_assignments(
        assignments,
        inventory,
        semantics,
        topology,
        matrix=matrix,
        hub_profile_rz_mm=hub_fit["control_points_rz_mm"],
    )
    return {
        "status": "PASS",
        "topology": topology_result,
        "topology_mode": topology["mode"],
        "semantic_partition_digest": partition["partition_digest"],
        "source_face_semantics": _serialize_source_face_semantics(
            assignments, inventory, semantics
        ),
        "periodic_closure_classification": closure_classification,
        "hub_profile": hub_fit,
        "tip_reference_or_shroud": tip_support,
        "mapping_fits": {
            "hub": _serialize_support_record(hub_fit),
            "tip_or_shroud": _serialize_support_record(tip_support),
        },
        "support_face_ids": copy.deepcopy(topology),
        "pattern_material_partition": _pattern_material_partition(
            inventory,
            semantics,
            topology,
            tip_support,
        ),
    }


def _serialize_source_face_semantics(assignments, inventory, semantics):
    role_hints = semantics.get("face_roles", {})
    records = []
    for source_face_id in sorted(assignments):
        assignment = assignments[source_face_id]
        source_record = inventory["records_by_id"].get(source_face_id, {})
        hint = role_hints.get(source_face_id, {})
        geometry_type = source_record.get("geometry_type")
        if geometry_type is None:
            geometry_type = assignment["shape"].geomType()
        records.append(
            {
                "source_face_id": source_face_id,
                "semantic_role": str(assignment["role"]),
                "source_role_hint": str(hint.get("role", "")),
                "geometry_type": str(geometry_type),
                "periodic_instance_id": assignment["periodic_instance_id"],
                "periodic_blade_related": bool(
                    assignment["periodic_blade_related"]
                ),
                "flowpath_adjacent": bool(assignment["flowpath_adjacent"]),
                "hole_boundary": bool(assignment["hole_boundary"]),
            }
        )
    return records


def _pattern_material_partition(inventory, semantics, topology, tip_support):
    populations = semantics["periodic_population_recovery"]["populations"]
    instances = [
        instance for population in populations for instance in population["instances"]
    ]
    hub_ids = sorted(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
    partition = {
        "mode": topology["mode"],
        "hub_support_face_ids": hub_ids,
        "hub_attachment_face_ids_by_instance": _attachment_faces_by_instance(
            inventory, instances, hub_ids
        ),
    }
    if topology["mode"] == "open":
        partition.update(
            {
                "open_tip_reference_face_ids": sorted(
                    tip_support["source_tip_caps"]["source_face_ids"]
                ),
                "material_shroud": None,
            }
        )
        return partition

    inner_ids = sorted(tip_support["inner_flowpath"]["source_face_ids"])
    outer_ids = sorted(tip_support["outer_material"]["source_face_ids"])
    thickness = tip_support["thickness"]
    partition.update(
        {
            "open_tip_reference_face_ids": None,
            "material_shroud": {
                "source_face_ids": sorted({*inner_ids, *outer_ids}),
                "inner_flowpath_face_ids": inner_ids,
                "outer_material_face_ids": outer_ids,
                "blade_attachment_face_ids_by_instance": (
                    _attachment_faces_by_instance(inventory, instances, inner_ids)
                ),
                "finite_thickness": {
                    "samples_mm": [float(value) for value in thickness["samples_mm"]],
                    "minimum_mm": float(thickness["minimum_mm"]),
                    "source_face_pairs": copy.deepcopy(
                        thickness["sample_face_pairs"]
                    ),
                    "finite_positive": bool(thickness["finite_positive"]),
                    "sampling_authority": "authenticated_paired_material_faces",
                    "source_sampling_authority": thickness["sampling_authority"],
                },
            },
        }
    )
    return partition


def _attachment_faces_by_instance(inventory, instances, support_face_ids):
    support_ids = set(support_face_ids)
    adjacency = inventory["source_manifest"]["adjacency"]
    result = {}
    for instance in instances:
        candidates = [
            face_id
            for face_id in instance["source_face_ids"]
            if face_id not in support_ids
            and support_ids.intersection(adjacency.get(face_id, ()))
        ]
        if not candidates:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "periodic instance has no exact attachment face on its support",
                stage="support_recovery",
                evidence={
                    "instance_id": instance["instance_id"],
                    "support_face_ids": sorted(support_ids),
                },
            )
        result[str(instance["instance_id"])] = sorted(candidates)
    return result


def _classify_support_topology(inventory, frame, semantics) -> dict[str, Any]:
    """Classify supports from source adjacency, never from an axial envelope.

    A support may be planar, conical, freeform, or an OCCT revolved surface.  Its
    admissibility comes from its non-periodic identity and repeated blade-contact
    topology; surface type is retained as evidence rather than used as a proxy.
    """
    periodic_ids = set(inventory["instance_by_face"])
    side_ids = {
        face_id
        for population in semantics["periodic_population_recovery"]["populations"]
        for instance in population["instances"]
        for face_id in instance["component_completeness"]["blade_side_face_ids"]
    }
    adjacency = inventory["source_manifest"]["adjacency"]
    records = inventory["records_by_id"]
    supported_types = {
        "PLANE",
        "CYLINDER",
        "CONE",
        "BSPLINE",
        "REVOLUTION",
        "REVOLVED",
    }
    candidates: list[dict[str, Any]] = []
    for face_id, record in records.items():
        if face_id in periodic_ids or str(record["geometry_type"]).upper() not in supported_types:
            continue
        periodic_neighbors = len(set(adjacency.get(face_id, ())) & periodic_ids)
        if periodic_neighbors:
            adjacent_periodic = set(adjacency.get(face_id, ())) & periodic_ids
            candidates.append(
                {
                    "face_id": face_id,
                    "periodic_neighbor_count": periodic_neighbors,
                    "blade_side_neighbor_count": len(
                        adjacent_periodic & side_ids
                    ),
                    "area_mm2": float(record["area_mm2"]),
                    "geometry_type": str(record["geometry_type"]),
                    "adjacent_periodic_face_ids": sorted(adjacent_periodic),
                    "shared_contact_length_mm": _shared_contact_length(
                        inventory, face_id, adjacent_periodic
                    ),
                }
            )
    if not candidates:
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "no supported non-periodic source face is adjacent to the blade population",
            stage="support_recovery",
            evidence={"supported_geometry_types": sorted(supported_types)},
        )
    candidates.sort(key=lambda item: item["face_id"])
    groups: list[dict[str, Any]] = []
    for candidate in candidates:
        group = next(
            (
                item
                for item in groups
                if item["geometry_type"] == candidate["geometry_type"]
                and abs(item["mean_area_mm2"] - candidate["area_mm2"])
                <= max(0.02, 0.001 * candidate["area_mm2"])
            ),
            None,
        )
        if group is None:
            group = {
                "geometry_type": candidate["geometry_type"],
                "mean_area_mm2": candidate["area_mm2"],
                "member_face_ids": [],
                "adjacent_periodic_face_ids": set(),
                "periodic_instance_ids": set(),
                "member_periodic_instance_ids": {},
                "member_contact_length_mm": {},
                "member_area_mm2": {},
                "shared_contact_length_mm": 0.0,
                "total_area_mm2": 0.0,
            }
            groups.append(group)
        group["member_face_ids"].append(candidate["face_id"])
        group["adjacent_periodic_face_ids"].update(
            candidate["adjacent_periodic_face_ids"]
        )
        group["periodic_instance_ids"].update(
            inventory["instance_by_face"][face_id]
            for face_id in candidate["adjacent_periodic_face_ids"]
        )
        group["member_periodic_instance_ids"][candidate["face_id"]] = sorted(
            {
                inventory["instance_by_face"][face_id]
                for face_id in candidate["adjacent_periodic_face_ids"]
            }
        )
        group["member_contact_length_mm"][candidate["face_id"]] = float(
            candidate["shared_contact_length_mm"]
        )
        group["member_area_mm2"][candidate["face_id"]] = float(
            candidate["area_mm2"]
        )
        group["shared_contact_length_mm"] += candidate[
            "shared_contact_length_mm"
        ]
        group["total_area_mm2"] += candidate["area_mm2"]
        group["mean_area_mm2"] = group["total_area_mm2"] / len(
            group["member_face_ids"]
        )
    groups.sort(
        key=lambda item: (
            -len(item["periodic_instance_ids"]),
            -item["shared_contact_length_mm"],
            -item["total_area_mm2"],
            item["geometry_type"],
            item["member_face_ids"],
        )
    )
    expected_instance_ids = {
        str(instance["instance_id"])
        for population in semantics["periodic_population_recovery"]["populations"]
        for instance in population["instances"]
    }
    hub_group = _select_complete_hub_group(groups, expected_instance_ids)
    representative_faces = {
        face_id
        for population in semantics["periodic_population_recovery"]["populations"]
        if population["classification"] == "main"
        for face_id in population["representative"]["source_face_ids"]
    }
    hub_members = [
        item
        for item in candidates
        if item["face_id"] in hub_group["member_face_ids"]
        and representative_faces.intersection(item["adjacent_periodic_face_ids"])
    ]
    if not hub_members:
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "winning hub support group does not contact the representative blade",
            stage="support_recovery",
            evidence={"hub_support_face_ids": hub_group["member_face_ids"]},
        )
    hub = sorted(
        hub_members,
        key=lambda item: (-item["shared_contact_length_mm"], item["face_id"]),
    )[0]
    selected_hub_faces = set(hub_group["member_face_ids"])
    comparable_groups = [
        item
        for item in groups
        if selected_hub_faces.isdisjoint(item["member_face_ids"])
        and item["periodic_instance_ids"] == expected_instance_ids
        and item["shared_contact_length_mm"]
        >= 0.5 * hub_group["shared_contact_length_mm"]
    ]
    mode = "closed" if comparable_groups else "open"
    population_instance_ids = {
        str(population["classification"]): sorted(
            str(instance["instance_id"])
            for instance in population["instances"]
        )
        for population in semantics["periodic_population_recovery"]["populations"]
    }
    initial_periodic_coverage = copy.deepcopy(
        hub_group.get("periodic_passage_face_coverage", {})
    )
    initial_periodic_coverage["population_instance_ids"] = (
        population_instance_ids
    )
    serialized_groups = [
        {
            **{
                key: value
                for key, value in item.items()
                if key not in {"adjacent_periodic_face_ids", "periodic_instance_ids"}
            },
            "member_face_ids": sorted(item["member_face_ids"]),
            "adjacent_periodic_face_ids": sorted(
                item["adjacent_periodic_face_ids"]
            ),
            "periodic_instance_ids": sorted(item["periodic_instance_ids"]),
        }
        for item in groups
    ]
    result: dict[str, Any] = {
        "mode": mode,
        "hub_face_id": hub["face_id"],
        "hub_support_face_ids": sorted(hub_group["member_face_ids"]),
        "hub_support_initial_periodic_coverage": initial_periodic_coverage,
        "support_candidates": copy.deepcopy(candidates),
        "support_candidate_groups": serialized_groups,
        "classification_authority": (
            "authenticated_nonperiodic_periodic_adjacency_contact_length_groups"
        ),
    }
    if mode == "closed":
        inner_group = comparable_groups[0]
        inner_candidates = [
            item
            for item in candidates
            if item["face_id"] in inner_group["member_face_ids"]
            and representative_faces.intersection(item["adjacent_periodic_face_ids"])
        ]
        inner = sorted(
            inner_candidates,
            key=lambda item: (-item["shared_contact_length_mm"], item["face_id"]),
        )[0]
        inner_id = inner["face_id"]
        outer_candidates = _reachable_nonperiodic_support_faces(
            inventory,
            start_face_id=inner_id,
            forbidden_face_ids=set(hub_group["member_face_ids"]),
        )
        if not outer_candidates:
            raise AxisFirstPipelineError(
                "v116_shroud_topology_ambiguous",
                "inner shroud has no topology-connected outer material support",
                stage="support_recovery",
                evidence={"inner_shroud_face_id": inner_id},
            )
        result.update(
            {
                "inner_shroud_face_id": inner_id,
                "outer_shroud_face_id": outer_candidates[0],
            }
        )
    else:
        result["open_tip_caps"] = _tip_cap_face_ids(
            inventory,
            semantics,
            hub_face_ids=result["hub_support_face_ids"],
        )
    return result


def _shared_contact_length(inventory, support_face_id, periodic_face_ids):
    support_edges = _face_edge_ids(inventory, support_face_id)
    periodic_edges = set().union(
        *(_face_edge_ids(inventory, face_id) for face_id in periodic_face_ids)
    )
    return float(
        sum(
            inventory["edges_by_id"][edge_id].Length()
            for edge_id in support_edges.intersection(periodic_edges)
        )
    )


def _semantic_assignments(inventory, semantics, topology) -> dict[str, Any]:
    instance_by_face = inventory["instance_by_face"]
    open_caps = set(topology.get("open_tip_caps", {}).values())
    instances = [
        instance
        for population in semantics["periodic_population_recovery"]["populations"]
        for instance in population["instances"]
    ]
    authenticated_side_faces = {
        face_id
        for instance in instances
        for face_id in instance["component_completeness"]["blade_side_face_ids"]
    }
    hub_support_ids = set(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
    adjacency = inventory["source_manifest"]["adjacency"]
    root_attachment_faces = set()
    for instance in instances:
        side_faces = set(
            instance["component_completeness"]["blade_side_face_ids"]
        )
        candidates = {
            face_id
            for face_id in instance["source_face_ids"]
            if face_id not in authenticated_side_faces
            and face_id not in hub_support_ids
            and hub_support_ids.intersection(adjacency.get(face_id, ()))
        }
        dual_side_candidates = {
            face_id
            for face_id in candidates
            if len(side_faces.intersection(adjacency.get(face_id, ()))) >= 2
        }
        root_attachment_faces.update(dual_side_candidates or candidates)
    attachment_faces = set()
    if topology["mode"] == "closed":
        inner_id = topology["inner_shroud_face_id"]
        for population in semantics["periodic_population_recovery"]["populations"]:
            for instance in population["instances"]:
                attachment_faces.add(
                    _attachment_face_for_support(inventory, instance, inner_id)
                )
    assignments = {}
    support_boundary_ids = set(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    ) | {
        topology.get("inner_shroud_face_id"),
        topology.get("outer_shroud_face_id"),
    }
    for face_id, face in inventory["faces_by_id"].items():
        instance_id = instance_by_face.get(face_id)
        role = "source_material_boundary"
        flowpath = False
        if face_id in topology.get(
            "hub_support_face_ids", [topology["hub_face_id"]]
        ):
            role, flowpath = "hub_flowpath_support", True
            instance_id = None
        elif face_id == topology.get("inner_shroud_face_id"):
            role, flowpath = "inner_shroud_flowpath_support", True
        elif face_id == topology.get("outer_shroud_face_id"):
            role = "outer_shroud_material_support"
        elif face_id in attachment_faces:
            role, flowpath = "periodic_blade_tip_attachment", True
        elif face_id in open_caps:
            role, flowpath = "periodic_blade_tip_cap", True
        elif face_id in root_attachment_faces:
            role, flowpath = "periodic_blade_root_attachment", True
        elif face_id in authenticated_side_faces:
            role, flowpath = "periodic_blade_side", True
        elif instance_id is not None:
            role = "periodic_blade_unclassified_closure"
        assignments[face_id] = {
            "shape": face,
            "role": role,
            "alternatives": [],
            "periodic_instance_id": instance_id,
            "periodic_blade_related": instance_id is not None,
            "flowpath_adjacent": flowpath,
            "root_blend": face_id in root_attachment_faces,
            "hole_boundary": (
                face_id not in support_boundary_ids
                and "bore"
                in semantics["face_roles"].get(face_id, {}).get("role", "")
            ),
            "local_edge_treatment": False,
        }
    return assignments


def _refine_periodic_closure_assignments(
    assignments,
    inventory,
    semantics,
    topology,
    *,
    matrix,
    hub_profile_rz_mm,
) -> dict[str, Any]:
    """Split authenticated periodic closure faces at the two streamwise ends."""

    evidence = {}
    populations = semantics["periodic_population_recovery"]["populations"]
    for population in populations:
        for instance in population["instances"]:
            instance_id = str(instance["instance_id"])
            side_face_ids = set(
                instance["component_completeness"]["blade_side_face_ids"]
            )
            candidates = []
            rejected = []
            for face_id in instance["source_face_ids"]:
                assignment = assignments[face_id]
                if assignment["role"] != "periodic_blade_unclassified_closure":
                    continue
                if not side_face_ids.intersection(
                    inventory["source_manifest"]["adjacency"].get(face_id, ())
                ):
                    continue
                try:
                    streamwise_s = _closure_meridional_s(
                        inventory,
                        face_id,
                        side_face_ids,
                        matrix,
                        hub_profile_rz_mm,
                    )
                except AxisFirstPipelineError as exc:
                    rejected.append(
                        {
                            "source_face_id": face_id,
                            "reason": exc.reason,
                        }
                    )
                    continue
                candidates.append((float(streamwise_s), face_id))
            candidates.sort(key=lambda item: (item[0], item[1]))
            if len(candidates) < 2:
                evidence[instance_id] = {
                    "status": "UNRESOLVED",
                    "reason": "fewer_than_two_authenticated_streamwise_closure_faces",
                    "candidate_source_face_ids": [
                        face_id for _value, face_id in candidates
                    ],
                    "rejected_candidates": rejected,
                }
                continue
            gaps = [
                right[0] - left[0]
                for left, right in zip(candidates, candidates[1:])
            ]
            split_index = max(
                range(len(gaps)), key=lambda index: (gaps[index], -index)
            ) + 1
            leading = candidates[:split_index]
            trailing = candidates[split_index:]
            if not leading or not trailing or gaps[split_index - 1] <= 1.0e-9:
                evidence[instance_id] = {
                    "status": "UNRESOLVED",
                    "reason": "streamwise_closure_partition_ambiguous",
                    "candidate_source_face_ids": [
                        face_id for _value, face_id in candidates
                    ],
                    "streamwise_s_mm": {
                        face_id: value for value, face_id in candidates
                    },
                    "rejected_candidates": rejected,
                }
                continue
            for _value, face_id in leading:
                assignments[face_id].update(
                    {
                        "role": "periodic_blade_leading_edge",
                        "flowpath_adjacent": True,
                        "local_edge_treatment": True,
                    }
                )
            for _value, face_id in trailing:
                assignments[face_id].update(
                    {
                        "role": "periodic_blade_trailing_edge",
                        "flowpath_adjacent": True,
                        "local_edge_treatment": True,
                    }
                )
            evidence[instance_id] = {
                "status": "PASS",
                "method": "exact_shared_boundary_hub_meridional_s_partition",
                "leading_edge_source_face_ids": [
                    face_id for _value, face_id in leading
                ],
                "trailing_edge_source_face_ids": [
                    face_id for _value, face_id in trailing
                ],
                "streamwise_s_mm": {
                    face_id: value for value, face_id in candidates
                },
                "separation_gap_mm": gaps[split_index - 1],
                "rejected_candidates": rejected,
            }
    return evidence


def _recover_open_tip(inventory, frame, semantics, topology):
    records = []
    expected = {}
    face_shapes: dict[str, Any] = {}
    edge_shapes: dict[str, Any] = {}
    edge_evidence = []
    cap_by_instance = topology["open_tip_caps"]
    for population in semantics["periodic_population_recovery"]["populations"]:
        for instance in population["instances"]:
            instance_id = str(instance["instance_id"])
            cap_id = cap_by_instance[instance_id]
            cap = inventory["faces_by_id"][cap_id]
            side_edge_groups = _cap_shared_side_edge_groups(
                inventory,
                cap_id,
                set(
                    instance["component_completeness"]["blade_side_face_ids"]
                ),
            )
            loops = []
            loop_ids = []
            for group_index, (adjacent_id, edge_ids) in enumerate(
                side_edge_groups
            ):
                loop_id = f"{instance_id}_open_tip_side_{group_index:02d}"
                loop_ids.append(loop_id)
                loops.append(
                    {
                        "loop_id": loop_id,
                        "source_edge_ids": list(edge_ids),
                        "adjacent_periodic_faces": [
                            {
                                "face_id": adjacent_id,
                                "face_role": "side",
                                "periodic_instance_id": instance_id,
                            }
                        ],
                    }
                )
                face_shapes[adjacent_id] = inventory["faces_by_id"][adjacent_id]
                for edge_id in edge_ids:
                    edge = inventory["edges_by_id"][edge_id]
                    edge_shapes[edge_id] = edge
                    edge_evidence.append(
                        support_recovery.sample_occt_edge_meridional_path(
                            edge,
                            source_edge_id=edge_id,
                            source_solid=inventory["shape"],
                            source_to_canonical_matrix=frame[
                                "source_to_canonical_matrix"
                            ],
                            source_tolerance_mm=_source_tolerance(frame),
                        )
                    )
            records.append(
                {
                    "periodic_instance_id": instance_id,
                    "tip_cap_face_id": cap_id,
                    "shared_edge_loops": loops,
                }
            )
            expected[instance_id] = loop_ids
            face_shapes[cap_id] = cap
    population_evidence = support_recovery.authenticate_open_tip_population_contract(
        inventory["shape"],
        topology_records=records,
        expected_instance_loop_ids=expected,
        source_face_shapes=face_shapes,
        source_edge_shapes=edge_shapes,
    )
    tip = support_recovery.recover_open_tip_reference(
        source_edge_evidence=edge_evidence,
        periodic_population_evidence=population_evidence,
        outer_diameter_mm=2.0 * float(frame["outer_radius_mm"]),
    )
    topology_result = support_recovery.decide_shroud_topology(
        blade_tip_cap_adjacencies=records,
        expected_blade_instances=sorted(expected),
        source_body_is_closed=bool(inventory["source_manifest"].get("closed_solid")),
    )
    if (
        topology_result["status"] != "PASS"
        or topology_result["decision"] != "open"
        or topology_result["material_shroud"] is not None
        or tip.get("material") is not False
    ):
        raise AxisFirstPipelineError(
            "v116_false_material_surface_forbidden",
            "authenticated open-tip evidence did not produce a non-material reference",
            stage="support_recovery",
            evidence={"topology": topology_result},
        )
    return tip, topology_result


def _recover_closed_shroud(inventory, frame, semantics, topology, partition):
    inner_id = topology["inner_shroud_face_id"]
    outer_id = topology["outer_shroud_face_id"]
    inner_face = inventory["faces_by_id"][inner_id]
    outer_face = inventory["faces_by_id"][outer_id]
    matrix = frame["source_to_canonical_matrix"]
    tolerance = _source_tolerance(frame)
    inner_profile = support_recovery.sample_occt_face_meridional_paths(
        inner_face,
        source_face_id=inner_id,
        source_solid=inventory["shape"],
        semantic_partition_evidence=partition,
        source_to_canonical_matrix=matrix,
        source_tolerance_mm=tolerance,
        trace_count=9,
        samples_per_trace=65,
    )
    outer_profile = support_recovery.sample_occt_face_meridional_paths(
        outer_face,
        source_face_id=outer_id,
        source_solid=inventory["shape"],
        semantic_partition_evidence=partition,
        source_to_canonical_matrix=matrix,
        source_tolerance_mm=tolerance,
        trace_count=9,
        samples_per_trace=65,
    )
    thickness = _sample_shroud_thickness_bounded(
        inner_face=inner_face,
        outer_face=outer_face,
        inner_id=inner_id,
        outer_id=outer_id,
        source_shape=inventory["shape"],
        matrix=matrix,
        tolerance=tolerance,
    )
    chains = {}
    expected = []
    for population in semantics["periodic_population_recovery"]["populations"]:
        for instance in population["instances"]:
            instance_id = str(instance["instance_id"])
            expected.append(instance_id)
            face_id = _attachment_face_for_support(inventory, instance, inner_id)
            edge_id, edge = _shared_edge_between_ids(inventory, face_id, inner_id)
            chains[instance_id] = {
                "tip_face_id": face_id,
                "tip_face": inventory["faces_by_id"][face_id],
                "inner_shroud_face_id": inner_id,
                "shared_edge_id": edge_id,
                "shared_edge": edge,
            }
    authenticated = support_recovery.authenticate_closed_shroud_topology(
        inventory["shape"],
        semantic_partition_evidence=partition,
        inner_flowpath_faces={inner_id: inner_face},
        outer_material_faces={outer_id: outer_face},
        paired_face_ids=((inner_id, outer_id),),
        blade_tip_attachment_chains=chains,
        expected_blade_instances=expected,
        thickness_sample_evidence=thickness,
        source_to_canonical_matrix=matrix,
    )
    try:
        result = support_recovery.decide_shroud_topology(
            topology_evidence=authenticated,
            inner_profile_evidence=[inner_profile],
            outer_profile_evidence=[outer_profile],
            thickness_sample_evidence=thickness,
            expected_blade_instances=expected,
        )
    except (ValueError, support_recovery.SupportRecoveryError) as exc:
        raise AxisFirstPipelineError(
            "v116_shroud_topology_ambiguous",
            f"authenticated closed-shroud recovery failed: {exc}",
            stage="support_recovery",
            evidence={
                "inner_shroud_face_id": inner_id,
                "outer_shroud_face_id": outer_id,
                "expected_blade_instances": sorted(expected),
            },
        ) from exc
    if result.get("status") != "PASS" or result.get("decision") != "closed":
        raise AxisFirstPipelineError(
            "v116_shroud_topology_ambiguous",
            "authenticated closed-shroud evidence did not pass the strict topology gate",
            stage="support_recovery",
            evidence={"topology_result": _jsonable(result)},
        )
    closed_support = result["tip_reference_or_shroud"]
    return closed_support, result


def _sample_shroud_thickness_bounded(
    *, inner_face, outer_face, inner_id, outer_id, source_shape, matrix, tolerance
):
    fractions = (0.15, 0.3, 0.5, 0.7, 0.85)
    candidates = [(u, v) for u in fractions for v in fractions]
    last_error = None
    for first_index, first in enumerate(candidates):
        for second in candidates[first_index + 1 :]:
            if first[0] == second[0] or first[1] == second[1]:
                continue
            try:
                return support_recovery.sample_occt_shroud_thickness(
                    inner_face,
                    outer_face,
                    inner_face_id=inner_id,
                    outer_face_id=outer_id,
                    source_solid=source_shape,
                    normalized_uv_stations=(first, second),
                    source_to_canonical_matrix=matrix,
                    source_tolerance_mm=tolerance,
                )
            except support_recovery.SupportRecoveryError as exc:
                last_error = exc
    raise AxisFirstPipelineError(
        "v116_shroud_topology_ambiguous",
        "no two independent normalized UV stations lie in both shroud material faces",
        stage="support_recovery",
        evidence={"upstream_error": None if last_error is None else str(last_error)},
    )


def _fit_authenticated_support(
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    outer_diameter_mm: float,
    semantic_role: str,
    minimum_radius_mm: float | None = None,
) -> dict[str, Any]:
    evidence_records = (
        [evidence] if isinstance(evidence, Mapping) else list(evidence)
    )
    if not evidence_records:
        raise AxisFirstPipelineError(
            "v116_hub_profile_fit_failed",
            f"{semantic_role} has no authenticated support faces",
            stage="support_recovery",
        )
    if semantic_role != "hub_profile":
        raise AxisFirstPipelineError(
            "v116_hub_profile_fit_failed",
            f"unsupported authenticated support role: {semantic_role}",
            stage="support_recovery",
        )
    try:
        return support_recovery.fit_hub_profile(
            source_face_evidence=evidence_records,
            outer_diameter_mm=outer_diameter_mm,
            minimum_radius_mm=minimum_radius_mm,
        )
    except (ValueError, support_recovery.SupportRecoveryError) as exc:
        raise AxisFirstPipelineError(
            "v116_hub_profile_fit_failed",
            f"authenticated hub support fit failed: {exc}",
            stage="support_recovery",
            evidence={
                "source_face_ids": [
                    str(record.get("source_face_id", ""))
                    for record in evidence_records
                ],
                "minimum_radius_mm_diagnostic": minimum_radius_mm,
            },
        ) from exc


def _serialize_support_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return support_recovery.serialize_support_fit_for_v112_mapping(record)


def _recover_periodic_evidence(
    inventory, frame, semantics, *, support=None
) -> dict[str, Any]:
    recovery = semantics.get("periodic_population_recovery")
    if not isinstance(recovery, Mapping) or not recovery.get("main"):
        raise AxisFirstPipelineError(
            "v116_periodic_population_ambiguous",
            "Task 5 periodic population evidence is missing",
            stage="periodic_representatives",
        )
    source_tolerance_mm = _source_tolerance(frame)
    support_topology = support["support_face_ids"] if support is not None else {}
    support_source_ids = _topology_material_support_face_ids(support_topology)
    coarse_periodic_source_ids = {
        str(face_id)
        for population in recovery["populations"]
        for instance in population["instances"]
        for face_id in instance["source_face_ids"]
    }
    maximum_representative_residual_mm = max(
        float(instance["residual_to_representative_mm"])
        for population in recovery["populations"]
        for instance in population["instances"]
    )
    representative_fit_tolerance_mm, representative_fit_ceiling_mm = (
        _bounded_representative_fit_tolerance(
            frame, maximum_representative_residual_mm
        )
    )
    pattern_population_evidence = _periodic_recovery_without_support_faces(
        recovery,
        support_topology,
    )
    result = {
        "status": "PASS",
        "closure_pass": bool(recovery["closure_diagnostics"]["all_populations_closed"]),
        "collision_status": recovery["collision_diagnostics"]["collision_status"],
        "collision_free": recovery["collision_diagnostics"]["collision_free"],
        "source_topology_separated": recovery["collision_diagnostics"][
            "source_topology_separated"
        ],
        "exact_brep_collision_checked": recovery["collision_diagnostics"][
            "exact_brep_collision_checked"
        ],
        "exact_brep_collision_free": recovery["collision_diagnostics"][
            "exact_brep_collision_free"
        ],
        "phase_consistent": True,
        "source_ids": sorted(coarse_periodic_source_ids - support_source_ids),
        "coarse_periodic_source_ids": sorted(coarse_periodic_source_ids),
        "excluded_support_source_face_ids": sorted(
            coarse_periodic_source_ids & support_source_ids
        ),
        "source_linear_tolerance_mm": source_tolerance_mm,
        "measurement_tolerance_mm": representative_fit_tolerance_mm,
        "generated_rigid_transform_tolerance_mm": source_tolerance_mm,
        "representative_fit_ceiling_mm": representative_fit_ceiling_mm,
        "measurement_tolerance_basis": (
            "maximum_authenticated_periodic_representative_fit_residual"
        ),
        "pattern_population_evidence": pattern_population_evidence,
        "coarse_pattern_population_evidence": copy.deepcopy(recovery),
    }
    for name in ("main", "splitter"):
        population = recovery.get(name)
        if population is None:
            result[name] = None
            continue
        representative = population.get("representative")
        component_id = representative.get("source_component_id") if isinstance(representative, Mapping) else None
        instance = next(
            (
                item
                for item in population["instances"]
                if item["source_component_id"] == component_id
            ),
            population["instances"][0],
        )
        if support is not None:
            support_ids = set(
                support["support_face_ids"].get("hub_support_face_ids", ())
            )
            if not support_ids:
                support_ids = {
                    str(support["support_face_ids"]["hub_face_id"])
                }
            support_bound = [
                item
                for item in population["instances"]
                if any(
                    support_ids.intersection(
                        inventory["source_manifest"]["adjacency"].get(
                            face_id, ()
                        )
                    )
                    for face_id in item["source_face_ids"]
                )
            ]
            if not support_bound:
                raise AxisFirstPipelineError(
                    "v116_representative_blade_selection_failed",
                    f"{name} population is not bound to the selected support sector",
                    stage="periodic_representatives",
                    evidence={
                        "hub_support_face_ids": sorted(support_ids),
                        "candidate_instance_ids": [
                            item["instance_id"] for item in support_bound
                        ],
                    },
                )
            if instance not in support_bound:
                instance = min(
                    support_bound, key=lambda item: str(item["instance_id"])
                )
        completeness = instance.get("component_completeness", {})
        if completeness.get("status") != "COMPLETE":
            raise AxisFirstPipelineError(
                "v116_representative_blade_selection_failed",
                f"{name} representative component is incomplete",
                stage="periodic_representatives",
                evidence={"component": instance},
            )
        if support is None:
            raise AxisFirstPipelineError(
                "v116_representative_blade_selection_failed",
                "streamwise blade bounds require an authenticated meridional support",
                stage="periodic_representatives",
                evidence={"population": name},
            )
        interval_evidence = project_rz_points_to_meridional_s(
            support["mapping_fits"]["hub"],
            _representative_meridional_points(
                inventory,
                frame,
                instance,
                source_face_ids=completeness["blade_side_face_ids"],
            ),
            tip_profile_fit=support["mapping_fits"]["tip_or_shroud"],
            maximum_projection_residual_mm=_support_projection_residual_gate_mm(
                support, frame
            ),
        )
        if interval_evidence.get("status") != "PASS":
            raise AxisFirstPipelineError(
                "v116_representative_blade_selection_failed",
                "representative blade cannot be bounded on normalized meridional arc length",
                stage="periodic_representatives",
                evidence={
                    "population": name,
                    "projection": interval_evidence,
                    "source_face_ids": sorted(instance["source_face_ids"]),
                },
            )
        interval = list(interval_evidence["streamwise_interval_s"])
        angular_sector, sector_evidence = _measurement_sector_from_envelope(
            instance["angular_envelope_deg"],
            pitch_deg=float(population["pitch_deg"]),
        )
        representative_instance = _periodic_instance_without_support_faces(
            instance,
            support_topology,
        )
        result[name] = {
            "count": int(population["count"]),
            "pitch_deg": float(population["pitch_deg"]),
            "phase_deg": float(population["phase_deg"]),
            "phase_relative_to_main_deg": float(population["phase_relative_to_main_deg"]),
            "streamwise_interval_s": interval,
            "streamwise_interval_evidence": interval_evidence,
            "source_ids": list(representative_instance["source_face_ids"]),
            "representative_instance": representative_instance,
            "angular_sector_deg": angular_sector,
            "angular_sector_evidence": sector_evidence,
        }
    return result


def _periodic_instance_without_support_faces(instance, topology):
    sanitized = copy.deepcopy(dict(instance))
    support_ids = _topology_material_support_face_ids(topology)
    coarse_ids = [str(face_id) for face_id in instance.get("source_face_ids", ())]
    excluded = sorted(set(coarse_ids).intersection(support_ids))
    sanitized["coarse_source_face_ids"] = coarse_ids
    sanitized["excluded_support_source_face_ids"] = excluded
    sanitized["source_face_ids"] = [
        face_id for face_id in coarse_ids if face_id not in support_ids
    ]
    completeness = sanitized.get("component_completeness")
    if isinstance(completeness, Mapping):
        completeness = copy.deepcopy(dict(completeness))
        for key, value in list(completeness.items()):
            if (
                key.endswith("_face_ids")
                and isinstance(value, Sequence)
                and not isinstance(value, (str, bytes))
            ):
                completeness[key] = [
                    str(face_id)
                    for face_id in value
                    if str(face_id) not in support_ids
                ]
        sanitized["component_completeness"] = completeness
    return sanitized


def _periodic_recovery_without_support_faces(recovery, topology):
    sanitized = copy.deepcopy(dict(recovery))

    def sanitize_population(population):
        if not isinstance(population, Mapping):
            return population
        result = copy.deepcopy(dict(population))
        instances = result.get("instances")
        if (
            isinstance(instances, Sequence)
            and not isinstance(instances, (str, bytes))
        ):
            result["instances"] = [
                _periodic_instance_without_support_faces(instance, topology)
                for instance in instances
            ]
        representative = result.get("representative")
        if isinstance(representative, Mapping):
            result["representative"] = _periodic_instance_without_support_faces(
                representative,
                topology,
            )
        return result

    populations = sanitized.get("populations")
    if (
        isinstance(populations, Sequence)
        and not isinstance(populations, (str, bytes))
    ):
        sanitized["populations"] = [
            sanitize_population(population) for population in populations
        ]
    for name in ("main", "splitter"):
        if sanitized.get(name) is not None:
            sanitized[name] = sanitize_population(sanitized[name])
    return sanitized


def _representative_meridional_points(
    inventory, frame, instance, *, source_face_ids=None
):
    matrix = frame["source_to_canonical_matrix"]
    points = set()
    selected_ids = (
        instance["source_face_ids"]
        if source_face_ids is None
        else source_face_ids
    )
    for source_face_id in selected_ids:
        face = inventory["faces_by_id"][source_face_id]
        for vertex in face.Vertices():
            _add_meridional_point(points, vertex.Center().toTuple(), matrix)
        for edge in face.Edges():
            try:
                edge_points, _parameters = edge.sample(17)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
            for point in edge_points:
                coordinates = point.toTuple() if hasattr(point, "toTuple") else point
                _add_meridional_point(points, coordinates, matrix)
    return [list(point) for point in sorted(points)]


def _add_meridional_point(points, coordinates, matrix):
    point = _transform_point(coordinates, matrix)
    points.add(
        (
            round(float(math.hypot(point[0], point[1])), 9),
            round(float(point[2]), 9),
        )
    )


def _support_projection_residual_gate_mm(support, frame):
    mapping_fits = support.get("mapping_fits", {})
    hub = mapping_fits.get("hub", {})
    tip = mapping_fits.get("tip_or_shroud", {})
    hub_controls = hub.get("control_points_rz_mm")
    tip_controls = tip.get("control_points_rz_mm")
    if hub_controls is None or tip_controls is None:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "authenticated support profiles cannot define a projection residual gate",
            stage="periodic_representatives",
        )
    try:
        correspondence = section_recovery.solve_meridional_correspondence(hub, tip)
    except section_recovery.SectionRecoveryError as exc:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "authenticated support profiles have no ordered meridional correspondence",
            stage="periodic_representatives",
            evidence={"correspondence_failure": exc.reason},
        ) from exc
    hub_points = np.asarray(correspondence.hub_points_rz_mm, dtype=float)
    tip_points = np.asarray(correspondence.tip_points_rz_mm, dtype=float)
    spans = np.linalg.norm(tip_points - hub_points, axis=1)
    minimum_span = float(np.min(spans))
    source_tolerance = _source_tolerance(frame)
    fit_residual = max(
        float(hub.get("residual_rms_mm", 0.0)),
        float(tip.get("residual_rms_mm", 0.0)),
    )
    gate = max(
        10.0 * source_tolerance,
        4.0 * fit_residual,
        0.005 * minimum_span,
    )
    if (
        not math.isfinite(gate)
        or gate <= 0.0
        or not math.isfinite(minimum_span)
        or minimum_span <= 0.0
        or gate >= 0.25 * minimum_span
    ):
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "authenticated support profiles produced an invalid projection residual gate",
            stage="periodic_representatives",
            evidence={
                "minimum_support_span_mm": minimum_span,
                "fit_residual_rms_mm": fit_residual,
                "candidate_gate_mm": gate,
            },
        )
    return gate


def _measurement_sector_from_envelope(envelope, *, pitch_deg):
    start = float(envelope["start_angle_deg"])
    end = float(envelope["end_angle_deg"])
    span = float(envelope["span_deg"])
    pitch = float(pitch_deg)
    if not 0.0 < span < 300.0 or not 0.0 < pitch <= 120.0:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "representative angular envelope cannot define a bounded measurement sector",
            stage="periodic_representatives",
            evidence={"angular_envelope_deg": dict(envelope), "pitch_deg": pitch},
        )
    measurement_span = span + 2.0 * pitch
    if measurement_span >= 300.0:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "representative measurement sector leaves no stable periodic seam",
            stage="periodic_representatives",
            evidence={
                "angular_envelope_deg": dict(envelope),
                "pitch_deg": pitch,
                "measurement_span_deg": measurement_span,
            },
        )
    sector = (start - pitch, end + pitch)
    return sector, {
        "method": "representative_side_envelope_plus_one_pitch_each_side",
        "raw_envelope_deg": [start, end],
        "raw_span_deg": span,
        "margin_each_side_deg": pitch,
        "measurement_span_deg": measurement_span,
    }


def _select_complete_hub_group(groups, expected_instance_ids):
    """Complete the strongest support family without mixing surface types.

    Periodic instance adjacency alone is insufficient for a hub split into one
    passage patch per blade pitch: a small seam patch can close the instance-id
    set while other passage patches are still missing.  Dense periodic seeds
    therefore require both instance coverage and one retained patch per pitch.
    """

    if not groups or not expected_instance_ids:
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "hub support selection requires candidates and periodic instances",
            stage="support_recovery",
        )
    seed = max(
        groups,
        key=lambda item: (
            float(item["shared_contact_length_mm"]),
            len(item["periodic_instance_ids"]),
            float(item["total_area_mm2"]),
            tuple(sorted(item["member_face_ids"])),
        ),
    )
    selected = copy.deepcopy(seed)
    selected["member_face_ids"] = list(seed["member_face_ids"])
    selected["adjacent_periodic_face_ids"] = set(
        seed["adjacent_periodic_face_ids"]
    )
    selected["periodic_instance_ids"] = set(seed["periodic_instance_ids"])
    remaining = [item for item in groups if item is not seed]
    expected_instance_ids = set(expected_instance_ids)
    expected_patch_count = len(expected_instance_ids)
    compatible_groups = [
        item for item in groups if item["geometry_type"] == seed["geometry_type"]
    ]
    compatible_member_instances = {
        face_id: instance_ids
        for item in compatible_groups
        for face_id, instance_ids in _hub_group_member_instances(item).items()
    }
    passage_member_instances = {
        face_id: instance_ids
        for face_id, instance_ids in compatible_member_instances.items()
        if 0 < len(instance_ids) <= 2
    }
    periodic_passage_mode = (
        len(passage_member_instances) >= expected_patch_count
        and not any(
            instance_ids == expected_instance_ids
            for instance_ids in passage_member_instances.values()
        )
    )

    if periodic_passage_mode:
        compatible_areas = [
            float(area)
            for item in compatible_groups
            for area in (item.get("member_area_mm2") or {}).values()
            if float(area) > 0.0
        ]
        reference_area_mm2 = (
            float(np.median(compatible_areas))
            if compatible_areas
            else float(seed["mean_area_mm2"])
        )
        face_records = _hub_passage_face_records(
            compatible_groups,
            expected_instance_ids,
            seed_mean_area_mm2=reference_area_mm2,
        )
        ownership = _match_hub_passage_faces(
            face_records,
            expected_instance_ids,
        )
        if set(ownership) != expected_instance_ids:
            raise AxisFirstPipelineError(
                "v116_hub_support_classification_failed",
                "hub support patches cannot be assigned one-to-one to every periodic pitch",
                stage="support_recovery",
                evidence={
                    "geometry_type": seed["geometry_type"],
                    "matched_periodic_instance_ids": sorted(ownership),
                    "missing_periodic_instance_ids": sorted(
                        expected_instance_ids - set(ownership)
                    ),
                    "candidate_face_ids": sorted(face_records),
                    "candidate_instance_ownership": {
                        face_id: sorted(record["periodic_instance_ids"])
                        for face_id, record in face_records.items()
                    },
                },
            )
        retained_face_ids = sorted(set(ownership.values()))
        selected = _merge_hub_groups_for_faces(
            compatible_groups,
            retained_face_ids,
        )
        selected["periodic_passage_face_coverage"] = {
            "mode": "periodic_passage_patches",
            "ownership_authority": "one_face_per_periodic_instance_bipartite_match",
            "expected_count": expected_patch_count,
            "observed_count": len(retained_face_ids),
            "instance_to_face_id": {
                instance_id: ownership[instance_id]
                for instance_id in sorted(ownership)
            },
            "complete": len(retained_face_ids) == expected_patch_count,
        }
        return selected

    def _selected_patch_count():
        return len(set(selected["member_face_ids"]))

    def _selection_incomplete():
        instances_incomplete = (
            selected["periodic_instance_ids"] != expected_instance_ids
        )
        return instances_incomplete

    while _selection_incomplete():
        missing = expected_instance_ids - selected["periodic_instance_ids"]
        compatible = []
        for item in remaining:
            item_instances = set(item["periodic_instance_ids"])
            if item["geometry_type"] != selected["geometry_type"]:
                continue
            if not item_instances.issubset(expected_instance_ids):
                continue
            if missing and not missing.intersection(item_instances):
                continue
            compatible.append(item)
        if not compatible:
            message = (
                "strongest hub support family does not provide one retained "
                "passage patch per periodic pitch"
                if periodic_passage_mode and not missing
                else "strongest hub support family does not cover every periodic instance"
            )
            raise AxisFirstPipelineError(
                "v116_hub_support_classification_failed",
                message,
                stage="support_recovery",
                evidence={
                    "geometry_type": selected["geometry_type"],
                    "hub_support_face_ids": sorted(selected["member_face_ids"]),
                    "missing_periodic_instance_ids": sorted(missing),
                    "periodic_passage_mode": periodic_passage_mode,
                    "expected_passage_patch_count": expected_patch_count,
                    "observed_passage_patch_count": _selected_patch_count(),
                },
            )
        addition = max(
            compatible,
            key=lambda item: (
                len(missing.intersection(item["periodic_instance_ids"])),
                float(item["shared_contact_length_mm"])
                / max(1, len(set(item["member_face_ids"]))),
                float(item["total_area_mm2"]),
                tuple(sorted(item["member_face_ids"])),
            ),
        )
        remaining.remove(addition)
        selected["member_face_ids"].extend(addition["member_face_ids"])
        selected["adjacent_periodic_face_ids"].update(
            addition["adjacent_periodic_face_ids"]
        )
        selected["periodic_instance_ids"].update(
            addition["periodic_instance_ids"]
        )
        selected["shared_contact_length_mm"] += addition[
            "shared_contact_length_mm"
        ]
        selected["total_area_mm2"] += addition["total_area_mm2"]
    selected["member_face_ids"] = sorted(set(selected["member_face_ids"]))
    selected["mean_area_mm2"] = selected["total_area_mm2"] / len(
        selected["member_face_ids"]
    )
    selected["periodic_passage_face_coverage"] = {
        "mode": (
            "shared_support_patch"
        ),
        "expected_count": (
            None
        ),
        "observed_count": len(selected["member_face_ids"]),
        "complete": (
            selected["periodic_instance_ids"] == expected_instance_ids
            and (
                True
            )
        ),
    }
    return selected


def _hub_group_member_instances(group):
    mapping = group.get("member_periodic_instance_ids")
    if isinstance(mapping, dict) and mapping:
        return {
            str(face_id): set(instance_ids)
            for face_id, instance_ids in mapping.items()
        }
    member_face_ids = [str(face_id) for face_id in group.get("member_face_ids", ())]
    aggregate = set(group.get("periodic_instance_ids", ()))
    if len(member_face_ids) == 1:
        return {member_face_ids[0]: aggregate}
    return {}


def _hub_passage_face_records(
    groups,
    expected_instance_ids,
    *,
    seed_mean_area_mm2,
):
    records = {}
    expected_instance_ids = set(expected_instance_ids)
    minimum_area = max(0.0, 0.2 * float(seed_mean_area_mm2))
    maximum_area = 3.0 * float(seed_mean_area_mm2)
    for group in groups:
        instances_by_face = _hub_group_member_instances(group)
        contact_by_face = group.get("member_contact_length_mm") or {}
        area_by_face = group.get("member_area_mm2") or {}
        fallback_contact = float(group.get("shared_contact_length_mm", 0.0)) / max(
            len(group.get("member_face_ids", ())), 1
        )
        fallback_area = float(group.get("mean_area_mm2", 0.0))
        for face_id, instance_ids in instances_by_face.items():
            instance_ids = set(instance_ids) & expected_instance_ids
            area_mm2 = float(area_by_face.get(face_id, fallback_area))
            if not instance_ids or len(instance_ids) > 2:
                continue
            if not minimum_area <= area_mm2 <= maximum_area:
                continue
            records[face_id] = {
                "periodic_instance_ids": instance_ids,
                "contact_length_mm": float(
                    contact_by_face.get(face_id, fallback_contact)
                ),
                "area_mm2": area_mm2,
            }
    return records


def _match_hub_passage_faces(face_records, expected_instance_ids):
    ordered_instances = sorted(
        expected_instance_ids,
        key=lambda instance_id: (
            sum(
                instance_id in record["periodic_instance_ids"]
                for record in face_records.values()
            ),
            instance_id,
        ),
    )
    face_to_instance = {}

    def assign(instance_id, visited_faces):
        candidates = sorted(
            (
                (face_id, record)
                for face_id, record in face_records.items()
                if instance_id in record["periodic_instance_ids"]
            ),
            key=lambda item: (
                len(item[1]["periodic_instance_ids"]),
                -item[1]["contact_length_mm"],
                -item[1]["area_mm2"],
                item[0],
            ),
        )
        for face_id, _record in candidates:
            if face_id in visited_faces:
                continue
            visited_faces.add(face_id)
            previous = face_to_instance.get(face_id)
            if previous is None or assign(previous, visited_faces):
                face_to_instance[face_id] = instance_id
                return True
        return False

    for instance_id in ordered_instances:
        assign(instance_id, set())
    return {
        instance_id: face_id
        for face_id, instance_id in face_to_instance.items()
    }


def _merge_hub_groups_for_faces(groups, retained_face_ids):
    retained = set(retained_face_ids)
    result = {
        "geometry_type": groups[0]["geometry_type"],
        "member_face_ids": sorted(retained),
        "adjacent_periodic_face_ids": set(),
        "periodic_instance_ids": set(),
        "member_periodic_instance_ids": {},
        "member_contact_length_mm": {},
        "member_area_mm2": {},
        "shared_contact_length_mm": 0.0,
        "total_area_mm2": 0.0,
    }
    for group in groups:
        member_instances = _hub_group_member_instances(group)
        contact_by_face = group.get("member_contact_length_mm") or {}
        area_by_face = group.get("member_area_mm2") or {}
        fallback_contact = float(group.get("shared_contact_length_mm", 0.0)) / max(
            len(group.get("member_face_ids", ())), 1
        )
        fallback_area = float(group.get("mean_area_mm2", 0.0))
        for face_id in set(group.get("member_face_ids", ())) & retained:
            instance_ids = set(member_instances.get(face_id, ()))
            contact = float(contact_by_face.get(face_id, fallback_contact))
            area = float(area_by_face.get(face_id, fallback_area))
            result["member_periodic_instance_ids"][face_id] = sorted(instance_ids)
            result["member_contact_length_mm"][face_id] = contact
            result["member_area_mm2"][face_id] = area
            result["periodic_instance_ids"].update(instance_ids)
            result["shared_contact_length_mm"] += contact
            result["total_area_mm2"] += area
        result["adjacent_periodic_face_ids"].update(
            group.get("adjacent_periodic_face_ids", ())
        )
    result["mean_area_mm2"] = result["total_area_mm2"] / max(len(retained), 1)
    return result


def _select_profile_conformant_hub_source_union(
    inventory,
    topology,
    *,
    sample_records_by_face,
    profile_control_points_rz_mm,
    profile_p95_limit_mm,
    profile_maximum_limit_mm,
    minimum_normalized_pitch_coverage=(
        _HUB_SUPPORT_MINIMUM_NORMALIZED_PITCH_COVERAGE
    ),
):
    """Complete a split hub support without absorbing blade-root geometry."""

    updated = copy.deepcopy(dict(topology))
    minimum_ratio = float(minimum_normalized_pitch_coverage)
    if not 0.0 < minimum_ratio <= 1.0:
        raise ValueError("minimum_normalized_pitch_coverage must be in (0,1]")
    initial_coverage = updated.get("hub_support_initial_periodic_coverage", {})
    if initial_coverage.get("mode") != "periodic_passage_patches":
        return _select_shared_profile_conformant_hub_source_union(
            inventory,
            updated,
            sample_records_by_face=sample_records_by_face,
            profile_control_points_rz_mm=profile_control_points_rz_mm,
            profile_p95_limit_mm=profile_p95_limit_mm,
            profile_maximum_limit_mm=profile_maximum_limit_mm,
            minimum_coverage_ratio=minimum_ratio,
        )

    instance_to_face = {
        str(instance_id): str(face_id)
        for instance_id, face_id in initial_coverage.get(
            "instance_to_face_id", {}
        ).items()
    }
    expected_count = int(initial_coverage.get("expected_count", 0))
    if not instance_to_face or len(instance_to_face) != expected_count:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support has no complete initial periodic ownership map",
            stage="support_recovery",
            evidence={
                "expected_periodic_instance_count": expected_count,
                "owned_periodic_instance_count": len(instance_to_face),
            },
        )

    initial_support_face_ids = set(updated["hub_support_face_ids"])
    support_face_ids = set(initial_support_face_ids)
    missing_samples = sorted(support_face_ids - set(sample_records_by_face))
    if missing_samples:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support coverage lacks sampled source faces",
            stage="support_recovery",
            evidence={"missing_sample_source_face_ids": missing_samples},
        )
    intervals_by_face = {
        face_id: _hub_face_angular_intervals_deg(sample_records_by_face[face_id])
        for face_id in sample_records_by_face
    }
    faces_by_instance = {
        instance_id: [face_id]
        for instance_id, face_id in instance_to_face.items()
    }
    initial_covered = {
        instance_id: _angular_union_length_deg(
            [
                interval
                for face_id in face_ids
                for interval in intervals_by_face[face_id]
            ]
        )
        for instance_id, face_ids in faces_by_instance.items()
    }
    reference_coverage_deg = float(np.median(list(initial_covered.values())))
    if not math.isfinite(reference_coverage_deg) or reference_coverage_deg <= 0.0:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support periodic pitch coverage has no finite reference span",
            stage="support_recovery",
            evidence={"initial_covered_angle_deg": initial_covered},
        )
    population_instance_ids = _hub_coverage_population_instance_ids(
        updated,
        instance_to_face,
    )
    population_by_instance = {
        instance_id: population
        for population, instance_ids in population_instance_ids.items()
        for instance_id in instance_ids
    }
    population_gates = {}
    for population, instance_ids in population_instance_ids.items():
        values = [initial_covered[instance_id] for instance_id in instance_ids]
        reference = float(np.median(values))
        if not math.isfinite(reference) or reference <= 0.0:
            raise AxisFirstPipelineError(
                "v116_hub_support_circumferential_coverage_incomplete",
                "hub support population has no finite angular coverage reference",
                stage="support_recovery",
                evidence={
                    "population": population,
                    "initial_covered_angle_deg": {
                        instance_id: initial_covered[instance_id]
                        for instance_id in instance_ids
                    },
                },
            )
        expected_pitch = 360.0 / float(len(instance_ids))
        population_gates[population] = {
            "instance_ids": list(instance_ids),
            "reference_covered_angle_deg": reference,
            "expected_pitch_angle_deg": expected_pitch,
            "minimum_absolute_pitch_coverage_deg": (
                minimum_ratio * expected_pitch
            ),
        }

    controls = np.asarray(profile_control_points_rz_mm, dtype=float)
    profile = np.asarray(
        support_recovery.evaluate_profile_rz(
            controls,
            np.linspace(
                0.0,
                1.0,
                _HUB_SUPPORT_PROFILE_SAMPLE_COUNT,
            ),
        ),
        dtype=float,
    )
    p95_limit = float(profile_p95_limit_mm)
    maximum_limit = float(profile_maximum_limit_mm)
    if (
        not math.isfinite(p95_limit)
        or not math.isfinite(maximum_limit)
        or p95_limit <= 0.0
        or maximum_limit < p95_limit
    ):
        raise ValueError("hub profile conformance limits are invalid")

    adjacency = inventory["source_manifest"]["adjacency"]
    support_owner_by_face = {
        face_id: instance_id for instance_id, face_id in instance_to_face.items()
    }
    support_geometry_types = {
        str(inventory["records_by_id"][face_id]["geometry_type"]).upper()
        for face_id in initial_support_face_ids
    }
    protected_attachment_face_ids = _protected_periodic_root_attachment_face_ids(
        inventory,
        updated,
    )
    expected_instances = set(instance_to_face)
    accepted_candidates = {}
    rejected_candidates = {}
    for face_id in sorted(set(sample_records_by_face) - support_face_ids):
        record = inventory["records_by_id"].get(face_id, {})
        geometry_type = str(record.get("geometry_type", "")).upper()
        adjacent_initial_support_ids = initial_support_face_ids.intersection(
            adjacency.get(face_id, ())
        )
        owners = _hub_candidate_instance_ids(
            inventory,
            face_id,
            support_owner_by_face=support_owner_by_face,
        ) & expected_instances
        if face_id in protected_attachment_face_ids:
            rejected_candidates[face_id] = {
                "reason": "periodic_root_attachment_protected",
                "geometry_type": geometry_type,
                "periodic_instance_ids": sorted(owners),
                "adjacent_initial_support_face_ids": sorted(
                    adjacent_initial_support_ids
                ),
            }
            continue
        if len(owners) > 1:
            rejected_candidates[face_id] = {
                "reason": "adjacent_support_owner_ambiguous",
                "geometry_type": geometry_type,
                "periodic_instance_ids": sorted(owners),
                "adjacent_initial_support_face_ids": sorted(
                    adjacent_initial_support_ids
                ),
            }
            continue
        if (
            geometry_type not in support_geometry_types
            or not owners
            or not adjacent_initial_support_ids
        ):
            rejected_candidates[face_id] = {
                "reason": (
                    "initial_support_adjacency_failed"
                    if not adjacent_initial_support_ids
                    else "support_type_or_periodic_ownership_failed"
                ),
                "geometry_type": geometry_type,
                "periodic_instance_ids": sorted(owners),
                "adjacent_initial_support_face_ids": sorted(
                    adjacent_initial_support_ids
                ),
            }
            continue
        rz_points = _hub_sample_points(sample_records_by_face[face_id], "paths_rz_mm", 2)
        distances = _nearest_profile_sample_distances(rz_points, profile)
        p95 = float(np.quantile(distances, 0.95))
        maximum = float(np.max(distances))
        evidence = {
            "periodic_instance_ids": sorted(owners),
            "adjacent_initial_support_face_ids": sorted(
                adjacent_initial_support_ids
            ),
            "profile_distance_p95_mm": round(p95, 9),
            "profile_distance_maximum_mm": round(maximum, 9),
            "sample_count": len(rz_points),
        }
        if p95 > p95_limit or maximum > maximum_limit:
            rejected_candidates[face_id] = {
                **evidence,
                "reason": "profile_conformance_failed",
            }
            continue
        accepted_candidates[face_id] = evidence

    promoted = []

    def coverage_state():
        covered = {
            instance_id: _angular_union_length_deg(
                [
                    interval
                    for face_id in face_ids
                    for interval in intervals_by_face[face_id]
                ]
            )
            for instance_id, face_ids in faces_by_instance.items()
        }
        normalized = {
            instance_id: value
            / population_gates[population_by_instance[instance_id]][
                "reference_covered_angle_deg"
            ]
            for instance_id, value in covered.items()
        }
        absolute_pitch_coverage = {
            instance_id: value
            / population_gates[population_by_instance[instance_id]][
                "expected_pitch_angle_deg"
            ]
            for instance_id, value in covered.items()
        }
        deficient = {
            instance_id
            for instance_id, ratio in normalized.items()
            if (
                ratio + 1.0e-12 < minimum_ratio
                or covered[instance_id] + 1.0e-12
                < population_gates[population_by_instance[instance_id]][
                    "minimum_absolute_pitch_coverage_deg"
                ]
            )
        }
        return covered, normalized, absolute_pitch_coverage, deficient

    covered, normalized, absolute_pitch_coverage, deficient = coverage_state()
    while deficient:
        viable = []
        for face_id, evidence in accepted_candidates.items():
            if face_id in promoted:
                continue
            if not initial_support_face_ids.intersection(
                adjacency.get(face_id, ())
            ):
                continue
            owners = set(evidence["periodic_instance_ids"]) & deficient
            total_gain = 0.0
            for instance_id in owners:
                before = covered[instance_id]
                after = _angular_union_length_deg(
                    [
                        interval
                        for owned_face_id in [
                            *faces_by_instance[instance_id],
                            face_id,
                        ]
                        for interval in intervals_by_face[owned_face_id]
                    ]
                )
                total_gain += max(0.0, after - before)
            if total_gain > 1.0e-9:
                viable.append(
                    (
                        total_gain,
                        -float(evidence["profile_distance_p95_mm"]),
                        -float(evidence["profile_distance_maximum_mm"]),
                        face_id,
                        owners,
                    )
                )
        if not viable:
            break
        _gain, _p95, _maximum, selected_face_id, owners = max(viable)
        promoted.append(selected_face_id)
        support_face_ids.add(selected_face_id)
        for instance_id in owners:
            faces_by_instance[instance_id].append(selected_face_id)
        covered, normalized, absolute_pitch_coverage, deficient = coverage_state()

    per_instance = {
        instance_id: {
            "population": population_by_instance[instance_id],
            "source_face_ids": sorted(faces_by_instance[instance_id]),
            "covered_angle_deg": round(covered[instance_id], 9),
            "normalized_coverage": round(normalized[instance_id], 9),
            "absolute_pitch_coverage": round(
                absolute_pitch_coverage[instance_id], 9
            ),
            "complete": instance_id not in deficient,
        }
        for instance_id in sorted(faces_by_instance)
    }
    evidence = {
        "contract_id": "impeller_v1_1_6_hub_support_source_union_r16_23",
        "status": "PASS" if not deficient else "REJECTED",
        "coverage_mode": (
            "every_periodic_pitch_absolute_and_population_relative_angular_support"
        ),
        "coverage_definition": (
            "every periodic pitch retains both the bounded fraction of its "
            "absolute pitch angle and the bounded fraction of the population-"
            "median bare-hub angular support; blade attachment cutouts are not "
            "misreported as missing hub"
        ),
        "initial_source_face_ids": sorted(updated["hub_support_face_ids"]),
        "promoted_source_face_ids": sorted(promoted),
        "final_source_face_ids": sorted(support_face_ids),
        "reference_covered_angle_deg": round(reference_coverage_deg, 9),
        "population_gates": {
            population: {
                **gate,
                "reference_covered_angle_deg": round(
                    gate["reference_covered_angle_deg"], 9
                ),
                "expected_pitch_angle_deg": round(
                    gate["expected_pitch_angle_deg"], 9
                ),
                "minimum_absolute_pitch_coverage_deg": round(
                    gate["minimum_absolute_pitch_coverage_deg"], 9
                ),
            }
            for population, gate in sorted(population_gates.items())
        },
        "minimum_normalized_pitch_coverage": minimum_ratio,
        "profile_conformance_limits_mm": {
            "p95": p95_limit,
            "maximum": maximum_limit,
        },
        "accepted_candidates": copy.deepcopy(accepted_candidates),
        "rejected_candidates": rejected_candidates,
        "per_instance": per_instance,
        "expected_periodic_instance_count": expected_count,
        "covered_periodic_instance_count": expected_count - len(deficient),
        "full_revolution_covered": not deficient,
    }
    unique_expected_pitches = {
        round(gate["expected_pitch_angle_deg"], 12)
        for gate in population_gates.values()
    }
    unique_minimum_coverage = {
        round(gate["minimum_absolute_pitch_coverage_deg"], 12)
        for gate in population_gates.values()
    }
    evidence["expected_pitch_angle_deg"] = (
        next(iter(unique_expected_pitches))
        if len(unique_expected_pitches) == 1
        else None
    )
    evidence["minimum_absolute_pitch_coverage_deg"] = (
        next(iter(unique_minimum_coverage))
        if len(unique_minimum_coverage) == 1
        else None
    )
    if deficient:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "profile-conformant hub support faces do not cover every periodic pitch",
            stage="support_recovery",
            evidence={
                **evidence,
                "deficient_periodic_instance_ids": sorted(deficient),
            },
        )
    updated["hub_support_face_ids"] = sorted(support_face_ids)
    updated["hub_support_source_union"] = evidence
    updated["classification_authority"] = (
        str(updated.get("classification_authority", ""))
        + "_plus_profile_conformant_split_face_union"
    )
    return updated


def _select_shared_profile_conformant_hub_source_union(
    inventory,
    topology,
    *,
    sample_records_by_face,
    profile_control_points_rz_mm,
    profile_p95_limit_mm,
    profile_maximum_limit_mm,
    minimum_coverage_ratio,
):
    initial_support_ids = set(topology["hub_support_face_ids"])
    missing_samples = sorted(initial_support_ids - set(sample_records_by_face))
    if missing_samples:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "shared hub support coverage lacks sampled source faces",
            stage="support_recovery",
            evidence={"missing_sample_source_face_ids": missing_samples},
        )
    intervals_by_face = {
        face_id: _hub_face_angular_intervals_deg(sample)
        for face_id, sample in sample_records_by_face.items()
    }
    support_ids = set(initial_support_ids)
    minimum_absolute_coverage_deg = float(minimum_coverage_ratio) * 360.0
    p95_limit = float(profile_p95_limit_mm)
    maximum_limit = float(profile_maximum_limit_mm)
    adjacency = inventory["source_manifest"]["adjacency"]
    support_geometry_types = {
        str(inventory["records_by_id"][face_id]["geometry_type"]).upper()
        for face_id in initial_support_ids
    }
    protected_attachment_ids = _protected_periodic_root_attachment_face_ids(
        inventory,
        topology,
    )
    candidate_face_ids = sorted(
        set(sample_records_by_face) - initial_support_ids
    )
    if candidate_face_ids:
        controls = np.asarray(profile_control_points_rz_mm, dtype=float)
        profile = np.asarray(
            support_recovery.evaluate_profile_rz(
                controls,
                np.linspace(0.0, 1.0, _HUB_SUPPORT_PROFILE_SAMPLE_COUNT),
            ),
            dtype=float,
        )
    else:
        profile = None
    accepted_candidates = {}
    rejected_candidates = {}
    for face_id in candidate_face_ids:
        geometry_type = str(
            inventory["records_by_id"].get(face_id, {}).get(
                "geometry_type", ""
            )
        ).upper()
        adjacent_initial_support_ids = initial_support_ids.intersection(
            adjacency.get(face_id, ())
        )
        if face_id in protected_attachment_ids:
            rejected_candidates[face_id] = {
                "reason": "periodic_root_attachment_protected",
                "geometry_type": geometry_type,
                "adjacent_initial_support_face_ids": sorted(
                    adjacent_initial_support_ids
                ),
            }
            continue
        if (
            geometry_type not in support_geometry_types
            or not adjacent_initial_support_ids
        ):
            rejected_candidates[face_id] = {
                "reason": (
                    "initial_support_adjacency_failed"
                    if not adjacent_initial_support_ids
                    else "support_type_failed"
                ),
                "geometry_type": geometry_type,
                "adjacent_initial_support_face_ids": sorted(
                    adjacent_initial_support_ids
                ),
            }
            continue
        rz_points = _hub_sample_points(
            sample_records_by_face[face_id], "paths_rz_mm", 2
        )
        distances = _nearest_profile_sample_distances(rz_points, profile)
        p95 = float(np.quantile(distances, 0.95))
        maximum = float(np.max(distances))
        candidate_evidence = {
            "adjacent_initial_support_face_ids": sorted(
                adjacent_initial_support_ids
            ),
            "profile_distance_p95_mm": round(p95, 9),
            "profile_distance_maximum_mm": round(maximum, 9),
            "sample_count": len(rz_points),
        }
        if p95 > p95_limit or maximum > maximum_limit:
            rejected_candidates[face_id] = {
                **candidate_evidence,
                "reason": "profile_conformance_failed",
            }
            continue
        accepted_candidates[face_id] = candidate_evidence

    def covered_angle_deg():
        return _angular_union_length_deg(
            [
                interval
                for face_id in support_ids
                for interval in intervals_by_face[face_id]
            ]
        )

    covered = covered_angle_deg()
    promoted = []
    while covered + 1.0e-12 < minimum_absolute_coverage_deg:
        viable = []
        for face_id, candidate_evidence in accepted_candidates.items():
            if face_id in promoted:
                continue
            after = _angular_union_length_deg(
                [
                    interval
                    for owned_face_id in [*support_ids, face_id]
                    for interval in intervals_by_face[owned_face_id]
                ]
            )
            gain = after - covered
            if gain > 1.0e-9:
                viable.append(
                    (
                        gain,
                        -float(candidate_evidence["profile_distance_p95_mm"]),
                        -float(
                            candidate_evidence["profile_distance_maximum_mm"]
                        ),
                        face_id,
                    )
                )
        if not viable:
            break
        _gain, _p95, _maximum, selected_face_id = max(viable)
        promoted.append(selected_face_id)
        support_ids.add(selected_face_id)
        covered = covered_angle_deg()

    complete = covered + 1.0e-12 >= minimum_absolute_coverage_deg
    evidence = {
        "contract_id": "impeller_v1_1_6_hub_support_source_union_r16_23",
        "status": "PASS" if complete else "REJECTED",
        "coverage_mode": "shared_support_absolute_angular_support",
        "coverage_definition": (
            "the exact trimmed boundary union of shared hub support faces "
            "must cover the bounded fraction of a full revolution"
        ),
        "initial_source_face_ids": sorted(initial_support_ids),
        "promoted_source_face_ids": sorted(promoted),
        "final_source_face_ids": sorted(support_ids),
        "covered_angle_deg": round(covered, 9),
        "expected_full_revolution_deg": 360.0,
        "minimum_absolute_coverage_deg": round(
            minimum_absolute_coverage_deg, 9
        ),
        "accepted_candidates": copy.deepcopy(accepted_candidates),
        "rejected_candidates": rejected_candidates,
        "profile_conformance_limits_mm": {
            "p95": p95_limit,
            "maximum": maximum_limit,
        },
        "full_revolution_covered": complete,
    }
    if not complete:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "shared hub support faces do not cover the full revolution",
            stage="support_recovery",
            evidence=evidence,
        )
    updated = copy.deepcopy(dict(topology))
    updated["hub_support_face_ids"] = sorted(support_ids)
    updated["hub_support_source_union"] = evidence
    updated["classification_authority"] = (
        str(updated.get("classification_authority", ""))
        + "_plus_profile_conformant_split_face_union"
    )
    return updated


def _hub_candidate_instance_ids(
    inventory,
    face_id,
    *,
    support_owner_by_face=None,
):
    support_owners = {
        str(support_owner_by_face[neighbor])
        for neighbor in inventory["source_manifest"]["adjacency"].get(
            face_id, ()
        )
        if support_owner_by_face is not None
        and neighbor in support_owner_by_face
    }
    if support_owners:
        return support_owners
    direct = inventory["instance_by_face"].get(face_id)
    if direct is not None:
        return {str(direct)}
    return {
        str(inventory["instance_by_face"][neighbor])
        for neighbor in inventory["source_manifest"]["adjacency"].get(
            face_id, ()
        )
        if neighbor in inventory["instance_by_face"]
    }


def _hub_sample_points(sample_record, key, dimension):
    points = np.asarray(
        [point for path in sample_record.get(key, ()) for point in path],
        dtype=float,
    )
    if (
        points.ndim != 2
        or points.shape[1:] != (dimension,)
        or len(points) < 2
        or not np.all(np.isfinite(points))
    ):
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support source face has no finite coverage samples",
            stage="support_recovery",
            evidence={"sample_key": key},
        )
    return points


def _hub_face_angular_intervals_deg(sample_record):
    if sample_record.get("coverage_points_xyz_mm") is not None:
        points = np.asarray(sample_record["coverage_points_xyz_mm"], dtype=float)
        if (
            points.ndim != 2
            or points.shape[1:] != (3,)
            or len(points) < 2
            or not np.all(np.isfinite(points))
        ):
            raise AxisFirstPipelineError(
                "v116_hub_support_circumferential_coverage_incomplete",
                "hub support face has invalid exact boundary samples",
                stage="support_recovery",
            )
    else:
        points = _hub_sample_points(sample_record, "paths_xyz_mm", 3)
    angles = np.sort(
        np.mod(np.degrees(np.arctan2(points[:, 1], points[:, 0])), 360.0)
    )
    if len(angles) == 2 and math.isclose(angles[0], angles[1], abs_tol=1.0e-12):
        return [(float(angles[0]), float(angles[0]))]
    wrapped = np.concatenate((angles, [angles[0] + 360.0]))
    gaps = np.diff(wrapped)
    gap_index = int(np.argmax(gaps))
    start = float(angles[(gap_index + 1) % len(angles)])
    span = max(0.0, 360.0 - float(gaps[gap_index]))
    end = start + span
    if end <= 360.0:
        return [(start, end)]
    return [(start, 360.0), (0.0, end - 360.0)]


def _angular_union_length_deg(intervals):
    normalized = []
    for start, end in intervals:
        first = min(max(float(start), 0.0), 360.0)
        second = min(max(float(end), 0.0), 360.0)
        if second > first:
            normalized.append((first, second))
    merged = []
    for start, end in sorted(normalized):
        if merged and start <= merged[-1][1] + 1.0e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return float(sum(end - start for start, end in merged))


def _nearest_profile_sample_distances(points, profile_samples):
    distances = np.empty(len(points), dtype=float)
    for start in range(0, len(points), 256):
        chunk = points[start : start + 256]
        squared = np.sum(
            (chunk[:, None, :] - profile_samples[None, :, :]) ** 2,
            axis=2,
        )
        distances[start : start + len(chunk)] = np.sqrt(
            np.min(squared, axis=1)
        )
    return distances


def _sample_hub_source_faces(
    inventory,
    frame,
    source_face_ids,
    *,
    semantic_partition_evidence=None,
    trace_count,
    samples_per_trace,
):
    result = {}
    for face_id in sorted(set(source_face_ids)):
        options = {}
        if semantic_partition_evidence is not None:
            options["semantic_partition_evidence"] = semantic_partition_evidence
        sampled = support_recovery.sample_occt_face_meridional_paths(
            inventory["faces_by_id"][face_id],
            source_face_id=face_id,
            source_solid=inventory["shape"],
            source_to_canonical_matrix=frame["source_to_canonical_matrix"],
            source_tolerance_mm=_source_tolerance(frame),
            trace_count=trace_count,
            samples_per_trace=samples_per_trace,
            **options,
        )
        if semantic_partition_evidence is None:
            sampled = dict(sampled)
            sampled["coverage_points_xyz_mm"] = _canonical_face_boundary_points(
                inventory, frame, face_id
            )
        result[face_id] = sampled
    return result


def _canonical_face_boundary_points(inventory, frame, face_id):
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    face = inventory["faces_by_id"][face_id]
    points = []
    for vertex in face.Vertices():
        points.append(_transform_point(vertex.Center().toTuple(), matrix))
    failed_edge_indices = []
    for edge_index, edge in enumerate(face.Edges()):
        try:
            edge_points, _parameters = edge.sample(65)
            if len(edge_points) < 2:
                raise ValueError("exact edge returned fewer than two samples")
            transformed_edge_points = []
            for point in edge_points:
                coordinates = point.toTuple() if hasattr(point, "toTuple") else point
                transformed = _transform_point(coordinates, matrix)
                if not np.all(np.isfinite(transformed)):
                    raise ValueError("exact edge returned non-finite samples")
                transformed_edge_points.append(transformed)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            failed_edge_indices.append(edge_index)
            continue
        points.extend(transformed_edge_points)
    if failed_edge_indices:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support exact boundary sampling failed",
            stage="support_recovery",
            evidence={
                "source_face_id": face_id,
                "failed_edge_indices": failed_edge_indices,
            },
        )
    if len(points) < 2:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support face has no exact boundary samples",
            stage="support_recovery",
            evidence={"source_face_id": face_id},
        )
    return points


def _fit_preliminary_hub_support(
    samples_by_face,
    frame,
    *,
    minimum_radius_mm,
):
    paths = []
    path_source_ids = []
    for face_id in sorted(samples_by_face):
        for path in samples_by_face[face_id]["paths_rz_mm"]:
            paths.append(path)
            path_source_ids.append(face_id)
    points = np.asarray(
        [point for path in paths for point in path],
        dtype=float,
    )
    if points.ndim != 2 or points.shape[1:] != (2,) or len(points) < 6:
        raise AxisFirstPipelineError(
            "v116_hub_profile_fit_failed",
            "preliminary hub support has insufficient meridional evidence",
            stage="support_recovery",
            evidence={"sample_count": len(points)},
        )
    tolerance = _source_tolerance(frame)
    padding = max(tolerance, 1.0e-6)
    material_domain = (
        (
            float(np.min(points[:, 0]) - padding),
            float(np.max(points[:, 0]) + padding),
        ),
        (
            float(np.min(points[:, 1]) - padding),
            float(np.max(points[:, 1]) + padding),
        ),
    )
    try:
        return support_recovery.fit_hub_profile(
            paths,
            source_face_ids=path_source_ids,
            outer_diameter_mm=2.0 * float(frame["outer_radius_mm"]),
            material_domain_rz_mm=material_domain,
            coordinate_frame="canonical_axis_frame_xyz_mm",
            source_to_canonical_matrix=frame["source_to_canonical_matrix"],
            source_tolerance_mm=tolerance,
            source_sampling_authority=(
                "occt_trimmed_face_classifier_preliminary_union_fit"
            ),
            minimum_radius_mm=minimum_radius_mm,
        )
    except (ValueError, support_recovery.SupportRecoveryError) as exc:
        raise AxisFirstPipelineError(
            "v116_hub_profile_fit_failed",
            f"preliminary hub source-union fit failed: {exc}",
            stage="support_recovery",
            evidence={"source_face_ids": sorted(samples_by_face)},
        ) from exc


def _hub_coverage_population_instance_ids(topology, instance_to_face):
    coverage = topology["hub_support_initial_periodic_coverage"]
    raw = coverage.get("population_instance_ids")
    if not isinstance(raw, Mapping) or not raw:
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support coverage lacks population-specific instance ownership",
            stage="support_recovery",
            evidence={"periodic_instance_ids": sorted(instance_to_face)},
        )
    expected_ids = set(instance_to_face)
    result = {}
    observed_ids = set()
    duplicate_ids = set()
    for population, raw_instance_ids in raw.items():
        if (
            not isinstance(raw_instance_ids, Sequence)
            or isinstance(raw_instance_ids, (str, bytes))
        ):
            instance_ids = []
        else:
            instance_ids = [str(value) for value in raw_instance_ids]
        duplicate_ids.update(observed_ids.intersection(instance_ids))
        observed_ids.update(instance_ids)
        result[str(population)] = sorted(set(instance_ids))
    if (
        any(not instance_ids for instance_ids in result.values())
        or duplicate_ids
        or observed_ids != expected_ids
    ):
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "hub support population ownership is incomplete or overlapping",
            stage="support_recovery",
            evidence={
                "expected_periodic_instance_ids": sorted(expected_ids),
                "observed_periodic_instance_ids": sorted(observed_ids),
                "duplicate_periodic_instance_ids": sorted(duplicate_ids),
                "population_instance_ids": result,
            },
        )
    return result


def _initial_hub_coverage_deficiencies(topology, samples_by_face):
    coverage = topology["hub_support_initial_periodic_coverage"]
    instance_to_face = coverage["instance_to_face_id"]
    expected_count = int(coverage["expected_count"])
    missing_face_ids = sorted(
        str(face_id)
        for face_id in instance_to_face.values()
        if str(face_id) not in samples_by_face
    )
    if (
        expected_count <= 0
        or len(instance_to_face) != expected_count
        or missing_face_ids
    ):
        raise AxisFirstPipelineError(
            "v116_hub_support_circumferential_coverage_incomplete",
            "initial hub support has no complete sampled periodic ownership map",
            stage="support_recovery",
            evidence={
                "expected_periodic_instance_count": expected_count,
                "owned_periodic_instance_count": len(instance_to_face),
                "missing_sample_source_face_ids": missing_face_ids,
            },
        )
    covered = {
        str(instance_id): _angular_union_length_deg(
            _hub_face_angular_intervals_deg(samples_by_face[str(face_id)])
        )
        for instance_id, face_id in instance_to_face.items()
    }
    population_instance_ids = _hub_coverage_population_instance_ids(
        topology,
        {str(key): str(value) for key, value in instance_to_face.items()},
    )
    minimum_ratio = _HUB_SUPPORT_MINIMUM_NORMALIZED_PITCH_COVERAGE
    deficient = set()
    for population, instance_ids in population_instance_ids.items():
        reference = float(
            np.median([covered[instance_id] for instance_id in instance_ids])
        )
        if not math.isfinite(reference) or reference <= 0.0:
            raise AxisFirstPipelineError(
                "v116_hub_support_circumferential_coverage_incomplete",
                "initial hub support population has no finite angular coverage reference",
                stage="support_recovery",
                evidence={
                    "population": population,
                    "initial_covered_angle_deg": {
                        instance_id: covered[instance_id]
                        for instance_id in instance_ids
                    },
                },
            )
        minimum_absolute_coverage = minimum_ratio * (
            360.0 / len(instance_ids)
        )
        deficient.update(
            instance_id
            for instance_id in instance_ids
            if (
                covered[instance_id] / reference + 1.0e-12 < minimum_ratio
                or covered[instance_id] + 1.0e-12
                < minimum_absolute_coverage
            )
        )
    return deficient


def _hub_source_union_candidate_ids(
    inventory,
    semantics,
    topology,
    deficient_instance_ids,
):
    support_ids = set(topology["hub_support_face_ids"])
    support_types = {
        str(inventory["records_by_id"][face_id]["geometry_type"]).upper()
        for face_id in support_ids
    }
    side_ids = {
        str(face_id)
        for population in semantics["periodic_population_recovery"]["populations"]
        for instance in population["instances"]
        for face_id in instance["component_completeness"]["blade_side_face_ids"]
    }
    support_owner_by_face = {
        str(face_id): str(instance_id)
        for instance_id, face_id in topology[
            "hub_support_initial_periodic_coverage"
        ]["instance_to_face_id"].items()
    }
    return sorted(
        face_id
        for face_id, record in inventory["records_by_id"].items()
        if face_id not in support_ids
        and face_id not in side_ids
        and support_ids.intersection(
            inventory["source_manifest"]["adjacency"].get(face_id, ())
        )
        and str(record["geometry_type"]).upper() in support_types
        and _hub_candidate_instance_ids(
            inventory,
            face_id,
            support_owner_by_face=support_owner_by_face,
        ).intersection(deficient_instance_ids)
    )


def _protected_periodic_root_attachment_face_ids(inventory, topology):
    semantics = inventory.get("semantics", {})
    recovery = semantics.get("periodic_population_recovery", {})
    adjacency = inventory["source_manifest"]["adjacency"]
    support_ids = set(topology["hub_support_face_ids"])
    protected = set()
    for population in recovery.get("populations", ()):
        for instance in population.get("instances", ()):
            completeness = instance.get("component_completeness", {})
            side_ids = {
                str(face_id)
                for face_id in completeness.get("blade_side_face_ids", ())
            }
            for raw_face_id in instance.get("source_face_ids", ()):
                face_id = str(raw_face_id)
                if face_id in side_ids or face_id in support_ids:
                    continue
                neighbors = {
                    str(neighbor) for neighbor in adjacency.get(face_id, ())
                }
                if (
                    support_ids.intersection(neighbors)
                    and side_ids.intersection(neighbors)
                ):
                    protected.add(face_id)
    return protected


def _hub_profile_conformance_limits(preliminary_fit, frame):
    residuals = preliminary_fit.get("residuals", {})
    p95 = float(residuals.get("orthogonal_p95_mm", 0.0))
    tolerance = _source_tolerance(frame)
    outer_diameter = 2.0 * abs(float(frame["outer_radius_mm"]))
    p95_limit = max(
        10.0 * tolerance,
        4.0 * p95,
        0.001 * outer_diameter,
    )
    maximum_limit = max(
        3.0 * p95_limit,
        0.003 * outer_diameter,
    )
    return p95_limit, maximum_limit


def _bounded_representative_fit_tolerance(frame, observed_residual_mm):
    source_tolerance_mm = _source_tolerance(frame)
    outer_diameter_mm = 2.0 * abs(float(frame["outer_radius_mm"]))
    ceiling_mm = max(
        50.0 * source_tolerance_mm,
        0.001 * outer_diameter_mm,
    )
    observed = float(observed_residual_mm)
    if not math.isfinite(observed) or observed < 0.0 or observed > ceiling_mm:
        raise AxisFirstPipelineError(
            "v116_periodic_population_ambiguous",
            "periodic representative fit exceeds the independent review-grade ceiling",
            stage="periodic_representatives",
            evidence={
                "observed_residual_mm": observed,
                "ceiling_mm": ceiling_mm,
                "source_linear_tolerance_mm": source_tolerance_mm,
                "outer_diameter_mm": outer_diameter_mm,
            },
        )
    return max(source_tolerance_mm, observed), ceiling_mm


def _recover_section_evidence(inventory, frame, support, periodic) -> dict[str, Any]:
    topology = support["support_face_ids"]
    families = {}
    loop_records = []
    attachment_records = {}
    for name in ("main", "splitter"):
        population = periodic.get(name)
        if population is None:
            continue
        attachment_record = _measure_family_attachments(
            inventory,
            frame,
            population,
            topology,
            support_profiles=support["mapping_fits"],
            include_shroud=topology["mode"] == "closed",
        )
        attachment_records[name] = attachment_record
        family, records = _section_family(
            inventory,
            frame,
            support,
            name,
            population,
            attachment_record,
        )
        families[name] = family
        loop_records.extend(records)
    primary = attachment_records["main"]
    attachments = {"root": _attachment_for_mapping(primary["root"])}
    if topology["mode"] == "closed":
        attachments["shroud"] = _attachment_for_mapping(primary["shroud"])
    direct_populations = {}
    for name in families:
        population_records = [
            record for record in loop_records if record["population"] == name
        ]
        if not population_records:
            continue
        direct_populations[name] = {
            "population": name,
            "active_span_authority": copy.deepcopy(
                population_records[0]["direct_active_span_authority"]
            ),
            "section_extraction_performance": copy.deepcopy(
                families[name]["section_extraction_performance"]
            ),
            "stations": [
                copy.deepcopy(record["direct_section_curve_authority"])
                for record in population_records
            ],
        }
    return {
        "status": "PASS",
        "section_families": families,
        "section_loop_records": loop_records,
        "attachment_records": attachment_records,
        "attachments": attachments,
        "measurement_authority": "occt_revolved_meridional_surfaces",
        "direct_section_curve_network": {
            "contract_id": section_curve_authority.CONTRACT_ID,
            "implementation_revision": "axis_first_section_curve_authority_r16_22",
            "status": "PASS",
            "construction_usage": "step_reconstruction_only",
            "historical_preset_mapping_unchanged": True,
            "derived_field_policy": {
                "authority": "derived_from_direct_section_curve_network",
                "geometry_authority": False,
                "q_only_normal_thickness_offset_forbidden": True,
            },
            "populations": direct_populations,
        },
    }


def _section_family(inventory, frame, support, name, population, attachments):
    """Section a representative blade with ordered revolved support surfaces.

    The station parameter is normalized only after sectioning.  Its geometry is
    always the measured hub-to-tip meridional interpolation, never an axial
    plane or a centroid/bounding-box envelope.
    """
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    instance = population["representative_instance"]
    support_topology = support["support_face_ids"]
    hub_source_ids = support_topology.get("hub_support_face_ids")
    if hub_source_ids is None:
        legacy_hub_face_id = support_topology.get("hub_face_id")
        hub_source_ids = [] if legacy_hub_face_id is None else [legacy_hub_face_id]
    hub_support_ids = set(hub_source_ids)
    allowed = sorted(set(instance["source_face_ids"]) - hub_support_ids)
    center_deg = float(instance["angular_envelope_deg"]["center_angle_deg"])
    hub = support["mapping_fits"]["hub"]
    tip = support["mapping_fits"]["tip_or_shroud"]
    role_map = _representative_face_roles(
        inventory,
        instance,
        matrix,
        topology=support["support_face_ids"],
        hub_profile_rz_mm=hub["control_points_rz_mm"],
    )
    tolerance = _source_tolerance(frame)
    root_evidence, tip_evidence = _active_span_evidence_from_adjacency(
        inventory, population, support["support_face_ids"], tolerance
    )
    raw_root, raw_tip, active_span_contract = _measured_active_span_interval(
        hub["control_points_rz_mm"], tip["control_points_rz_mm"], tolerance,
        root_evidence, tip_evidence,
        root_attachment=attachments["root"],
        tip_attachment=attachments.get("shroud"),
    )
    root_evidence = {
        **root_evidence,
        "h": raw_root,
        "measured_attachment_lift_mm": (
            None
            if attachments["root"] is None
            else float(attachments["root"].lift_mm)
        ),
        "retained_source_edge_ids": (
            list(root_evidence.get("source_edge_ids", ()))
            if attachments["root"] is None
            else list(attachments["root"].retained_source_edge_ids)
        ),
    }
    tip_evidence = {
        **tip_evidence,
        "h": raw_tip,
        "measured_attachment_lift_mm": (
            0.0 if attachments.get("shroud") is None
            else float(attachments["shroud"].lift_mm)
        ),
    }
    cache: dict[float, tuple[Any, Any, Any, Any, float]] = {}
    section_timings: list[dict[str, Any]] = []
    section_cache_stats = {"call_count": 0, "hit_count": 0}
    direct_hub_profile_rz_mm = _evaluated_support_profile_rz(hub)
    direct_tip_profile_rz_mm = _evaluated_support_profile_rz(tip)
    (
        boundary_guided_correspondence,
        direct_tip_boundary,
        boundary_guided_evidence,
    ) = _source_side_boundary_guided_correspondence(
        inventory,
        frame,
        instance,
        role_map,
        topology=support["support_face_ids"],
        hub_profile=hub,
        tip_profile=tip,
        hub_points_rz_mm=direct_hub_profile_rz_mm,
        tip_points_rz_mm=direct_tip_profile_rz_mm,
        root_attachment=attachments["root"],
        tip_attachment=attachments.get("shroud"),
        tolerance_mm=tolerance,
    )
    direct_active_span = section_curve_authority.build_active_span_field(
        direct_hub_profile_rz_mm,
        direct_tip_profile_rz_mm,
        root_attachment=attachments["root"],
        tip_attachment=direct_tip_boundary,
        source_tolerance_mm=tolerance,
        streamwise_interval_s=population["streamwise_interval_s"],
        support_correspondence=boundary_guided_correspondence,
    )
    surface_patch_partition = _authenticated_representative_surface_patch_partition(
        inventory,
        instance,
        support.get("source_face_semantics", ()),
        matrix,
    )
    root_surface_patches = surface_patch_partition["root"]
    tip_surface_patches = surface_patch_partition["tip"]
    leading_edge_surface_patches = surface_patch_partition["leading_edge"]
    trailing_edge_surface_patches = surface_patch_partition["trailing_edge"]

    def section_at_resolved(active_h: float):
        section_cache_stats["call_count"] += 1
        key = round(float(active_h), 12)
        if key in cache:
            section_cache_stats["hit_count"] += 1
            return cache[key]
        started = time.perf_counter()
        nearest = (
            min(cache, key=lambda cached_h: abs(cached_h - key))
            if cache
            else None
        )
        prior = cache[nearest][1].accepted_loop if nearest is not None else None
        profile = section_recovery.SpanProfile(
            h=float(active_h),
            points_rz_mm=direct_active_span.profile_rz_mm(active_h),
            refinement_reasons=(),
            construction="s_dependent_active_span_exact",
        )
        section_profile, extension_margin = _extended_section_profile(
            profile.points_rz_mm,
            tolerance,
            support_profiles_rz_mm=(
                direct_hub_profile_rz_mm,
                direct_tip_profile_rz_mm,
            ),
        )
        surface = _measurement_surface_in_source_frame(
            section_recovery.make_occt_revolved_measurement_surface(
                section_profile,
                tolerance_mm=tolerance,
                angular_sector_deg=population["angular_sector_deg"],
            ),
            matrix,
        )
        projector, normal_source = _meridional_unwrapped_projector(
            profile.points_rz_mm, matrix, center_deg
        )
        try:
            result = section_recovery.section_source_solid(
                inventory["shape"],
                surface,
                angular_sector_deg=population["angular_sector_deg"],
                angular_source_to_canonical_matrix=matrix,
                source_faces_by_id=inventory["faces_by_id"],
                source_edges_by_id=inventory.get("edges_by_id"),
                source_face_edge_ids=inventory.get("face_edge_ids"),
                allowed_source_face_ids=allowed,
                source_face_roles=role_map,
                local_projector=projector,
                section_normal_xyz=normal_source,
                source_tolerance_mm=tolerance,
                edge_sample_count=129,
                reference_loop=prior,
                source_shape_scope="authenticated_representative_individual_faces",
                accept_authenticated_open_side_pair=True,
            )
        except section_recovery.SectionRecoveryError as exc:
            exc.details.update(
                {
                    "active_span_eta": float(active_h),
                    "legacy_support_span_interval_h": [
                        float(raw_root),
                        float(raw_tip),
                    ],
                    "representative_source_face_ids": list(allowed),
                }
            )
            raise exc
        decomposition = _decompose_measured_section_loop(
            result.accepted_loop,
            tolerance,
        )
        _assert_section_segment_fit_quality(decomposition, tolerance, active_h)
        thickness = _measure_section_thickness(
            result.accepted_loop, decomposition, sample_s=np.linspace(0.05, 0.95, 9)
        )
        cache[key] = (
            profile,
            result,
            decomposition,
            thickness,
            extension_margin,
        )
        section_timings.append(
            {
                "active_h": float(active_h),
                "duration_ms": (time.perf_counter() - started) * 1000.0,
                "source_loop_point_count": len(
                    getattr(result.accepted_loop, "points_xyz_mm", ())
                ),
                "source_edge_count": len(
                    getattr(result.accepted_loop, "source_edge_ids", ())
                ),
            }
        )
        return cache[key]

    resolved_root_eta, resolved_tip_eta, carrier_interval_evidence = (
        _resolve_measurement_carrier_interval(section_at_resolved)
    )
    direct_active_span_authority = {
        **direct_active_span.as_dict(),
        "source_side_boundary_correspondence": copy.deepcopy(
            boundary_guided_evidence
        ),
        "measurement_carrier_eta_interval": [
            resolved_root_eta,
            resolved_tip_eta,
        ],
        "measurement_carrier_interval_evidence": copy.deepcopy(
            carrier_interval_evidence
        ),
        "root_surface_patches": copy.deepcopy(root_surface_patches),
        "root_surface_patch_authority": (
            "authenticated_source_faces_adjacent_to_hub_support"
            if root_surface_patches
            else "unavailable_use_bounded_review_fallback"
        ),
        "tip_surface_patches": copy.deepcopy(tip_surface_patches),
        "tip_surface_patch_authority": (
            "authenticated_periodic_blade_tip_semantic_faces"
            if tip_surface_patches
            else "unavailable_use_bounded_review_fallback"
        ),
        "leading_edge_surface_patches": copy.deepcopy(
            leading_edge_surface_patches
        ),
        "leading_edge_surface_patch_authority": (
            "authenticated_periodic_blade_leading_edge_semantic_faces"
            if leading_edge_surface_patches
            else "authenticated_sharp_shared_seam_without_finite_face"
        ),
        "trailing_edge_surface_patches": copy.deepcopy(
            trailing_edge_surface_patches
        ),
        "trailing_edge_surface_patch_authority": (
            "authenticated_periodic_blade_trailing_edge_semantic_faces"
            if trailing_edge_surface_patches
            else "authenticated_sharp_shared_seam_without_finite_face"
        ),
    }


    def resolved_eta(active_h: float) -> float:
        eta = float(active_h)
        return resolved_root_eta + eta * (resolved_tip_eta - resolved_root_eta)

    station_resolutions: dict[float, dict[str, Any]] = {}

    def section_at(active_h: float):
        requested = resolved_eta(active_h)
        result, actual, evidence = _resolve_interior_measurement_carrier(
            section_at_resolved,
            requested_active_h=requested,
            lower_active_h=resolved_root_eta,
            upper_active_h=resolved_tip_eta,
        )
        station_resolutions[round(float(active_h), 12)] = evidence
        return result

    def metric_sampler(active_h: float) -> Mapping[str, Any]:
        _profile, result, decomposition, thickness, _margin = section_at(active_h)
        return _preliminary_section_metrics(result.accepted_loop, decomposition, thickness)

    normalized_root_evidence = {
        **root_evidence,
        "h": 0.0,
        "method": f"{root_evidence.get('method', 'measured_attachment')}_as_local_active_span_root",
    }
    normalized_tip_evidence = {
        **tip_evidence,
        "h": 1.0,
        "method": f"{tip_evidence.get('method', 'measured_attachment')}_as_local_active_span_tip",
    }
    stations = section_recovery.select_adaptive_span_stations(
        metric_sampler,
        active_root_h=0.0,
        active_tip_h=1.0,
        active_root_evidence=normalized_root_evidence,
        active_tip_evidence=normalized_tip_evidence,
        known_source_face_ids=set(inventory["faces_by_id"]),
        known_source_edge_ids=set(inventory["edges_by_id"]),
        thresholds={
            "mean_thickness_mm": max(0.05, 8.0 * tolerance),
            "camber_turn_deg": 0.75,
            "edge_curvature_per_mm": 0.02,
        },
        maximum_station_count=9,
    )
    output_stations, records = [], []
    for station in stations:
        profile, result, decomposition, thickness, extension_margin = section_at(
            station.h
        )
        mapped_h = float(station.h)
        carrier_resolution = station_resolutions[round(mapped_h, 12)]
        actual_eta = float(carrier_resolution["resolved_active_span_eta"])
        local_support_h = float(
            np.median(
                [
                    direct_active_span.beta(actual_eta, float(u))
                    for u in direct_active_span.streamwise_u
                ]
            )
        )
        loop = result.accepted_loop
        output_stations.append(
            _station_for_mapping(
                mapped_h,
                loop,
                decomposition,
                thickness,
                frame,
                support_span_h=local_support_h,
            )
        )
        direct_station = section_curve_authority.build_station_curve_authority(
            population=name,
            active_h=mapped_h,
            support_span_h=local_support_h,
            support_profile_rz_mm=profile.points_rz_mm,
            loop=loop,
            decomposition=decomposition,
            frame=frame,
        )
        direct_station["derived_fields"] = (
            section_curve_authority.build_derived_field_evidence(thickness)
        )
        requested_eta = float(carrier_resolution["requested_active_span_eta"])
        actual_resolved_eta = float(
            carrier_resolution["resolved_active_span_eta"]
        )
        direct_station["carrier_resolution"] = {
            "requested_local_active_h": mapped_h,
            "requested_active_span_eta": requested_eta,
            "resolved_active_span_eta": actual_resolved_eta,
            "delta_active_span_eta": actual_resolved_eta - requested_eta,
            "method": profile.construction,
            "station_search": copy.deepcopy(carrier_resolution),
        }
        records.append(
            {
                "population": name,
                "h": mapped_h,
                "support_span_h": local_support_h,
                "active_span_eta": mapped_h,
                "resolved_active_span_eta": actual_eta,
                "support_profile_rz_mm": [list(point) for point in profile.points_rz_mm],
                "section_surface_tangent_extension_mm": extension_margin,
                "source_face_ids": list(loop.source_face_ids),
                "source_edge_ids": list(loop.source_edge_ids),
                "canonical_angular_sector_deg": list(
                    population["angular_sector_deg"]
                ),
                "section_population_filter": "exact_source_face_allow_list",
                "closure_gap_mm": float(loop.closure_gap_mm),
                "self_intersection_count": int(loop.self_intersection_count),
                "exact_section": result.as_dict(),
                "decomposition": _decomposition_summary(decomposition),
                "preliminary_metrics": dict(station.metrics),
                "normal_thickness": {
                    "minimum_mm": thickness.minimum_mm,
                    "maximum_mm": thickness.maximum_mm,
                    "mean_mm": thickness.mean_mm,
                },
                "canonical_source_loop_points_xyz_mm": copy.deepcopy(
                    direct_station["canonical_loop_points_xyz_mm"]
                ),
                "direct_section_curve_authority": direct_station,
                "direct_active_span_authority": {
                    **copy.deepcopy(direct_active_span_authority),
                },
            }
        )
    return (
        {
            "population": name,
            "stations": output_stations,
            "source_ids": allowed,
            "active_span_contract": active_span_contract,
            "section_extraction_performance": {
                "exact_section_evaluation_count": len(cache),
                "final_station_count": len(stations),
                "direct_curve_count": sum(
                    len(
                        record["direct_section_curve_authority"].get(
                            "curves", {}
                        )
                    )
                    for record in records
                ),
                "section_request_count": section_cache_stats["call_count"],
                "cache_hit_count": section_cache_stats["hit_count"],
                "cache_scope": "in_process_population_station_cache",
                "station_resolutions": [
                    copy.deepcopy(station_resolutions[key])
                    for key in sorted(station_resolutions)
                ],
                "station_timings": sorted(
                    section_timings, key=lambda record: record["active_h"]
                ),
            },
        },
        records,
    )


def _authenticated_representative_root_surface_patches(
    inventory: Mapping[str, Any],
    instance: Mapping[str, Any],
    role_map: Mapping[str, str],
    topology: Mapping[str, Any],
    source_to_canonical_matrix: np.ndarray,
) -> list[dict[str, Any]]:
    raw_support_ids = topology.get("hub_support_face_ids")
    if isinstance(raw_support_ids, Sequence) and not isinstance(
        raw_support_ids, (str, bytes)
    ):
        support_ids = {str(face_id) for face_id in raw_support_ids}
    elif topology.get("hub_face_id") is not None:
        support_ids = {str(topology["hub_face_id"])}
    else:
        return []
    adjacency = inventory.get("source_manifest", {}).get("adjacency")
    if not isinstance(adjacency, Mapping):
        return []
    candidates = [
        str(face_id)
        for face_id in instance["source_face_ids"]
        if role_map.get(str(face_id)) not in {"side_a", "side_b"}
        and support_ids.intersection(adjacency.get(str(face_id), ()))
    ]
    return _canonical_source_surface_patches(
        inventory,
        candidates,
        source_to_canonical_matrix,
    )


def _authenticated_representative_surface_patch_partition(
    inventory: Mapping[str, Any],
    instance: Mapping[str, Any],
    source_face_semantics: Sequence[Mapping[str, Any]],
    source_to_canonical_matrix: np.ndarray,
) -> dict[str, list[dict[str, Any]]]:
    """Partition finite representative closure faces by authenticated semantics."""

    semantic_role_by_partition = {
        "root": {"periodic_blade_root_attachment"},
        "tip": {
            "periodic_blade_tip_cap",
            "periodic_blade_tip_attachment",
        },
        "leading_edge": {"periodic_blade_leading_edge"},
        "trailing_edge": {"periodic_blade_trailing_edge"},
    }
    instance_id = str(instance.get("instance_id", ""))
    component_face_ids = {
        str(face_id) for face_id in instance.get("source_face_ids", ())
    }
    face_ids_by_partition = {
        partition: [] for partition in semantic_role_by_partition
    }
    assigned_face_ids: set[str] = set()
    for raw_record in source_face_semantics:
        record = dict(raw_record)
        face_id = str(record.get("source_face_id", ""))
        if not face_id or face_id not in component_face_ids:
            continue
        record_instance_id = str(record.get("periodic_instance_id", ""))
        if instance_id and record_instance_id != instance_id:
            continue
        semantic_role = str(record.get("semantic_role", ""))
        matching = [
            partition
            for partition, roles in semantic_role_by_partition.items()
            if semantic_role in roles
        ]
        if not matching:
            continue
        if face_id in assigned_face_ids or len(matching) != 1:
            raise AxisFirstPipelineError(
                "v116_periodic_closure_partition_ambiguous",
                "a finite periodic closure face has ambiguous semantic ownership",
                stage="exact_sections",
                evidence={
                    "instance_id": instance_id,
                    "source_face_id": face_id,
                    "semantic_role": semantic_role,
                    "matching_partitions": matching,
                },
            )
        assigned_face_ids.add(face_id)
        face_ids_by_partition[matching[0]].append(face_id)
    return {
        partition: _canonical_source_surface_patches(
            inventory,
            face_ids,
            source_to_canonical_matrix,
        )
        for partition, face_ids in face_ids_by_partition.items()
    }


def _authenticated_representative_tip_surface_patches(
    inventory: Mapping[str, Any],
    instance: Mapping[str, Any],
    role_map: Mapping[str, str],
    topology: Mapping[str, Any],
    source_to_canonical_matrix: np.ndarray,
) -> list[dict[str, Any]]:
    if topology.get("mode") != "open":
        return []
    side_ids = {
        str(face_id)
        for face_id in instance["source_face_ids"]
        if role_map.get(str(face_id)) in {"side_a", "side_b"}
    }
    if len(side_ids) != 2:
        return []
    adjacency = inventory.get("source_manifest", {}).get("adjacency")
    if not isinstance(adjacency, Mapping):
        return []
    support_ids = _topology_material_support_face_ids(topology)
    candidates = []
    for raw_face_id in instance["source_face_ids"]:
        face_id = str(raw_face_id)
        if face_id in side_ids:
            continue
        neighbors = {str(value) for value in adjacency.get(face_id, ())}
        if side_ids.issubset(neighbors) and not support_ids.intersection(neighbors):
            candidates.append(face_id)
    return _canonical_source_surface_patches(
        inventory,
        candidates,
        source_to_canonical_matrix,
    )


def _topology_material_support_face_ids(topology: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in (
        "hub_support_face_ids",
        "hub_face_id",
        "inner_shroud_face_id",
        "outer_shroud_face_id",
    ):
        value = topology.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            result.update(str(face_id) for face_id in value)
        elif value is not None:
            result.add(str(value))
    return result


def _canonical_source_surface_patches(
    inventory: Mapping[str, Any],
    face_ids: Sequence[str],
    source_to_canonical_matrix: np.ndarray,
) -> list[dict[str, Any]]:
    patches = []
    for face_id in sorted({str(value) for value in face_ids}):
        source_edge_kwargs = {}
        if (
            isinstance(inventory.get("edges_by_id"), Mapping)
            and isinstance(inventory.get("face_edge_ids"), Mapping)
        ):
            source_edge_kwargs["source_edges_by_id"] = {
                edge_id: inventory["edges_by_id"][edge_id]
                for edge_id in inventory["face_edge_ids"].get(face_id, ())
            }
        raw = section_recovery._source_face_bspline_parameter_authority(
            inventory["faces_by_id"][face_id],
            source_face_id=face_id,
            **source_edge_kwargs,
        )
        if not isinstance(raw, Mapping):
            continue
        patches.append(
            section_curve_authority._canonical_source_face_surface(
                raw,
                source_to_canonical_matrix,
                expected_face_id=face_id,
            )
        )
    return patches


def _resolve_interior_measurement_carrier(
    section_sampler,
    *,
    requested_active_h,
    lower_active_h,
    upper_active_h,
):
    lower = float(lower_active_h)
    upper = float(upper_active_h)
    requested = float(requested_active_h)
    if not lower <= requested <= upper or upper - lower <= 1.0e-9:
        raise ValueError("requested_active_h must lie inside an ordered interval")
    boundary_reasons = {
        "v116_section_intersection_failed",
        "v116_section_loop_open",
        "v116_section_loop_correspondence_failed",
    }
    offsets = (
        0.0,
        -1.0 / 128.0,
        1.0 / 128.0,
        -1.0 / 64.0,
        1.0 / 64.0,
        -1.0 / 32.0,
        1.0 / 32.0,
        -0.05,
        0.05,
    )
    candidates = []
    for offset in offsets:
        candidate = requested + offset
        if candidate < lower - 1.0e-12 or candidate > upper + 1.0e-12:
            continue
        candidate = min(max(candidate, lower), upper)
        if not any(abs(candidate - value) <= 1.0e-12 for value in candidates):
            candidates.append(candidate)
    rejected = []
    last_error = None
    for candidate in candidates:
        try:
            result = section_sampler(candidate)
        except section_recovery.SectionRecoveryError as exc:
            if exc.reason not in boundary_reasons:
                raise
            last_error = exc
            rejected.append(
                {
                    "active_span_eta": float(candidate),
                    "reason": str(exc.reason),
                    "details": copy.deepcopy(exc.details),
                }
            )
            continue
        return result, float(candidate), {
            "method": "nearest_valid_two_sided_station_bounded_search",
            "requested_active_span_eta": requested,
            "resolved_active_span_eta": float(candidate),
            "delta_active_span_eta": float(candidate - requested),
            "maximum_search_delta_active_span_eta": 0.05,
            "rejected_candidates": rejected,
            "status": "PASS",
        }
    assert last_error is not None
    last_error.details.update(
        {
            "requested_active_span_eta": requested,
            "interior_measurement_carrier_candidates": candidates,
            "interior_measurement_carrier_rejections": rejected,
        }
    )
    raise last_error


def _resolve_measurement_carrier_interval(section_sampler):
    boundary_reasons = {
        "v116_section_intersection_failed",
        "v116_section_loop_open",
        "v116_section_loop_correspondence_failed",
    }
    root_candidates = (0.0, 0.015625, 0.03125, 0.0625, 0.125, 0.25, 0.375)
    tip_candidates = (1.0, 0.984375, 0.96875, 0.9375, 0.875, 0.75, 0.625)

    def resolve(side, candidates):
        rejected = []
        last_error = None
        for candidate in candidates:
            try:
                section_sampler(float(candidate))
            except section_recovery.SectionRecoveryError as exc:
                if exc.reason not in boundary_reasons:
                    raise
                last_error = exc
                rejected.append(
                    {
                        "active_span_eta": float(candidate),
                        "reason": str(exc.reason),
                        "details": copy.deepcopy(exc.details),
                    }
                )
                continue
            return float(candidate), {
                "side": side,
                "resolved_active_span_eta": float(candidate),
                "rejected_candidates": rejected,
                "status": "PASS",
            }
        assert last_error is not None
        last_error.details.update(
            {
                "measurement_carrier_side": side,
                "measurement_carrier_candidates": list(candidates),
                "measurement_carrier_rejections": rejected,
            }
        )
        raise last_error

    root, root_evidence = resolve("root", root_candidates)
    tip, tip_evidence = resolve("tip", tip_candidates)
    if root >= tip - 1.0e-9:
        raise section_recovery.SectionRecoveryError(
            "v116_span_surface_ordering_failed",
            "closed blade-body measurement carriers cross or collapse",
            {
                "resolved_root_active_span_eta": root,
                "resolved_tip_active_span_eta": tip,
            },
        )
    return root, tip, {
        "authority": "nearest_exact_two_sided_blade_body_section",
        "root": root_evidence,
        "tip": tip_evidence,
        "resolved_active_span_eta_interval": [root, tip],
    }


def _measure_section_thickness(
    loop: section_recovery.SectionLoop,
    decomposition: section_recovery.LoopDecomposition,
    *,
    sample_s: Sequence[float],
    camber_iterations: int = 4,
) -> section_recovery.ThicknessField:
    """Measure only the retained blade-body interior of staggered side loops.

    Some exact STEP section loops have streamwise-staggered side endpoints
    because the leading/trailing closures own the terminal material.  Endpoint
    camber normals are then closure measurements, not blade-body thickness
    measurements.  This routine keeps the same exact side-intersection method
    as Task 7 while fitting the camber curve over the authenticated common
    side-interior domain.
    """
    side_a_segment = decomposition.segment("side_a")
    side_b_segment = decomposition.segment("side_b")
    side_a = section_recovery._orient_side_le_to_te(  # noqa: SLF001
        np.asarray(side_a_segment.points_sq_mm, dtype=float)
    )
    side_b = section_recovery._orient_side_le_to_te(  # noqa: SLF001
        np.asarray(side_b_segment.points_sq_mm, dtype=float)
    )
    requested_s = np.asarray(list(sample_s), dtype=float)
    if (
        requested_s.ndim != 1
        or not len(requested_s)
        or not np.all(np.isfinite(requested_s))
        or np.any(requested_s <= 0.0)
        or np.any(requested_s >= 1.0)
        or np.any(np.diff(requested_s) <= 0.0)
    ):
        raise ValueError("sample_s must be strictly increasing inside (0,1)")

    lower_s = max(float(np.min(side_a[:, 0])), float(np.min(side_b[:, 0])))
    upper_s = min(float(np.max(side_a[:, 0])), float(np.max(side_b[:, 0])))
    if upper_s - lower_s <= 1.0e-12:
        return _paired_source_thickness_field(
            loop,
            side_a,
            side_b,
            requested_s,
            method="paired_source_curve_witnesses_no_common_physical_s_domain",
        )

    fit_s = np.unique(
        np.concatenate([np.linspace(0.02, 0.98, 65), requested_s])
    )
    camber_points = _seed_camber_points(side_a, side_b, fit_s, lower_s, upper_s)
    camber_fit: section_recovery.NurbsCurveFit | None = None
    for _iteration in range(max(1, int(camber_iterations))):
        camber_fit = section_recovery.fit_nurbs_measurement_curve(
            np.column_stack([camber_points, np.zeros(len(camber_points))]),
            camber_points,
            segment_name="camber",
            maximum_control_count=min(10, len(camber_points)),
        )
        updated = []
        for fraction in fit_s:
            point, normal = section_recovery._camber_point_and_normal(  # noqa: SLF001
                camber_fit, float(fraction)
            )
            hit_a, hit_b, _method = _section_thickness_witness_pair(
                point,
                normal,
                side_a,
                side_b,
                fraction=float(fraction),
            )
            updated.append(0.5 * (hit_a[0] + hit_b[0]))
        updated_points = np.asarray(updated, dtype=float)
        if (
            float(np.max(np.linalg.norm(updated_points - camber_points, axis=1)))
            <= 1.0e-8
        ):
            camber_points = updated_points
            break
        camber_points = updated_points

    camber_fit = section_recovery.fit_nurbs_measurement_curve(
        np.column_stack([camber_points, np.zeros(len(camber_points))]),
        camber_points,
        segment_name="camber",
        maximum_control_count=min(10, len(camber_points)),
    )
    polygon = np.asarray(loop.points_sq_mm, dtype=float)
    samples: list[section_recovery.ThicknessSample] = []
    fallback_sample_count = 0
    for fraction in requested_s:
        point, normal = section_recovery._camber_point_and_normal(  # noqa: SLF001
            camber_fit, float(fraction)
        )
        hit_a, hit_b, measurement_method = _section_thickness_witness_pair(
            point,
            normal,
            side_a,
            side_b,
            fraction=float(fraction),
        )
        point_a, parameter_a, lambda_a = hit_a
        point_b, parameter_b, lambda_b = hit_b
        fallback = measurement_method == "paired_source_curve_witnesses"
        thickness = (
            float(np.linalg.norm(point_a - point_b))
            if fallback
            else abs(lambda_a - lambda_b)
        )
        inside = all(
            section_recovery._point_in_polygon(  # noqa: SLF001
                (1.0 - alpha) * point_a + alpha * point_b, polygon
            )
            for alpha in (0.25, 0.5, 0.75)
        )
        if (
            not fallback
            and (
                not math.isfinite(thickness)
                or thickness <= 1.0e-12
                or not inside
            )
        ):
            hit_a, hit_b = section_recovery.paired_source_curve_witnesses(
                point,
                normal,
                side_a,
                side_b,
                fraction=float(fraction),
            )
            point_a, parameter_a, lambda_a = hit_a
            point_b, parameter_b, lambda_b = hit_b
            measurement_method = "paired_source_curve_witnesses"
            fallback = True
            thickness = float(np.linalg.norm(point_a - point_b))
            inside = all(
                section_recovery._point_in_polygon(  # noqa: SLF001
                    (1.0 - alpha) * point_a + alpha * point_b,
                    polygon,
                )
                for alpha in (0.25, 0.5, 0.75)
            )
        if fallback:
            fallback_sample_count += 1
            point = 0.5 * (point_a + point_b)
            side_vector = point_a - point_b
            thickness = float(np.linalg.norm(side_vector))
            normal = side_vector / max(thickness, 1.0e-18)
        if (
            not math.isfinite(thickness)
            or thickness <= 1.0e-12
            or (not inside and not fallback)
        ):
            raise section_recovery.SectionRecoveryError(
                "v116_thickness_field_invalid",
                "camber-normal thickness must be positive and remain inside the source loop",
                {
                    "s": float(fraction),
                    "thickness_mm": float(thickness),
                    "inside": inside,
                },
            )
        samples.append(
            section_recovery.ThicknessSample(
                s=round(float(fraction), 12),
                camber_sq_mm=(float(point[0]), float(point[1])),
                normal_sq=(float(normal[0]), float(normal[1])),
                side_a_sq_mm=(float(point_a[0]), float(point_a[1])),
                side_b_sq_mm=(float(point_b[0]), float(point_b[1])),
                side_a_parameter=round(float(parameter_a), 12),
                side_b_parameter=round(float(parameter_b), 12),
                thickness_mm=round(float(thickness), 12),
                inside_source_loop=bool(inside),
                measurement_method=measurement_method,
                normal_line_residual_mm=round(
                    abs(float(lambda_a + lambda_b)), 12
                ),
            )
        )
    correspondence_monotone = _thickness_correspondence_is_monotone(samples)
    if not fallback_sample_count:
        _assert_monotone_thickness_correspondence(samples)
    return section_recovery.ThicknessField(
        loop_id=loop.loop_id,
        samples=tuple(samples),
        camber_fit=camber_fit,
        method=(
            "camber_normal_with_paired_source_witness_fallback"
            if fallback_sample_count
            else "camber_normal_line_intersections"
        ),
        fallback_sample_count=fallback_sample_count,
        correspondence_monotone=correspondence_monotone,
    )


def _paired_source_thickness_field(
    loop,
    side_a,
    side_b,
    requested_s,
    *,
    method,
):
    polygon = np.asarray(loop.points_sq_mm, dtype=float)
    samples = []
    camber_points = []
    for fraction in np.asarray(requested_s, dtype=float):
        point_a = section_recovery._polyline_point_at_arc_fraction(  # noqa: SLF001
            side_a, float(fraction)
        )
        point_b = section_recovery._polyline_point_at_arc_fraction(  # noqa: SLF001
            side_b, float(fraction)
        )
        vector = point_a - point_b
        thickness = float(np.linalg.norm(vector))
        if not math.isfinite(thickness) or thickness <= 1.0e-12:
            raise section_recovery.SectionRecoveryError(
                "v116_thickness_field_invalid",
                "paired source-curve thickness witnesses collapse",
                {"fraction": float(fraction)},
            )
        midpoint = 0.5 * (point_a + point_b)
        normal = vector / thickness
        inside = all(
            section_recovery._point_in_polygon(  # noqa: SLF001
                (1.0 - alpha) * point_a + alpha * point_b,
                polygon,
            )
            for alpha in (0.25, 0.5, 0.75)
        )
        camber_points.append(midpoint)
        samples.append(
            section_recovery.ThicknessSample(
                s=round(float(fraction), 12),
                camber_sq_mm=(float(midpoint[0]), float(midpoint[1])),
                normal_sq=(float(normal[0]), float(normal[1])),
                side_a_sq_mm=(float(point_a[0]), float(point_a[1])),
                side_b_sq_mm=(float(point_b[0]), float(point_b[1])),
                side_a_parameter=round(float(fraction), 12),
                side_b_parameter=round(float(fraction), 12),
                thickness_mm=round(thickness, 12),
                inside_source_loop=bool(inside),
                measurement_method="paired_source_curve_witnesses",
                normal_line_residual_mm=0.0,
            )
        )
    camber = np.asarray(camber_points, dtype=float)
    camber_fit = section_recovery.fit_nurbs_measurement_curve(
        np.column_stack([camber, np.zeros(len(camber))]),
        camber,
        segment_name="camber",
        maximum_control_count=min(10, len(camber)),
    )
    return section_recovery.ThicknessField(
        loop_id=loop.loop_id,
        samples=tuple(samples),
        camber_fit=camber_fit,
        method=str(method),
        fallback_sample_count=len(samples),
        correspondence_monotone=True,
    )


def _section_thickness_witness_pair(
    point: np.ndarray,
    normal: np.ndarray,
    side_a: np.ndarray,
    side_b: np.ndarray,
    *,
    fraction: float,
):
    try:
        hit_a, hit_b = section_recovery._opposite_side_normal_hits(  # noqa: SLF001
            point, normal, side_a, side_b
        )
        return hit_a, hit_b, "camber_normal_line_intersections"
    except section_recovery.SectionRecoveryError as error:
        if error.reason != "v116_thickness_field_invalid":
            raise
    hit_a, hit_b = section_recovery.paired_source_curve_witnesses(
        point,
        normal,
        side_a,
        side_b,
        fraction=fraction,
    )
    return hit_a, hit_b, "paired_source_curve_witnesses"


def _seed_camber_points(
    side_a: np.ndarray,
    side_b: np.ndarray,
    fit_s: np.ndarray,
    lower_s: float,
    upper_s: float,
) -> np.ndarray:
    seed_points = []
    for fraction in fit_s:
        streamwise = lower_s + float(fraction) * (upper_s - lower_s)
        point_a = section_recovery._polyline_point_at_streamwise(  # noqa: SLF001
            side_a, streamwise
        )
        point_b = section_recovery._polyline_point_at_streamwise(  # noqa: SLF001
            side_b, streamwise
        )
        seed_points.append(0.5 * (point_a + point_b))
    return np.asarray(seed_points, dtype=float)


def _assert_monotone_thickness_correspondence(
    samples: Sequence[section_recovery.ThicknessSample],
) -> None:
    parameters_a = np.asarray(
        [sample.side_a_parameter for sample in samples], dtype=float
    )
    parameters_b = np.asarray(
        [sample.side_b_parameter for sample in samples], dtype=float
    )
    if np.any(np.diff(parameters_a) < -1.0e-6) or np.any(
        np.diff(parameters_b) < -1.0e-6
    ):
        raise section_recovery.SectionRecoveryError(
            "v116_thickness_field_invalid",
            "camber-normal side correspondence is not monotone",
            {
                "side_a_parameters": parameters_a.tolist(),
                "side_b_parameters": parameters_b.tolist(),
            },
        )


def _thickness_correspondence_is_monotone(
    samples: Sequence[section_recovery.ThicknessSample],
) -> bool:
    parameters_a = np.asarray(
        [sample.side_a_parameter for sample in samples], dtype=float
    )
    parameters_b = np.asarray(
        [sample.side_b_parameter for sample in samples], dtype=float
    )
    return bool(
        np.all(np.diff(parameters_a) >= -1.0e-6)
        and np.all(np.diff(parameters_b) >= -1.0e-6)
    )


def _extended_section_profile(
    profile_rz_mm, tolerance_mm, *, support_profiles_rz_mm=()
):
    """Extend the cutter to the authenticated support-endpoint envelope."""
    points = np.asarray(profile_rz_mm, dtype=float)
    if len(points) < 2:
        raise AxisFirstPipelineError(
            "v116_section_intersection_failed",
            "support-derived section profile has fewer than two points",
            stage="exact_sections",
        )
    start_tangent = points[1] - points[0]
    end_tangent = points[-1] - points[-2]
    start_tangent /= max(float(np.linalg.norm(start_tangent)), 1.0e-18)
    end_tangent /= max(float(np.linalg.norm(end_tangent)), 1.0e-18)
    support_profiles = [
        np.asarray(support_profile, dtype=float)
        for support_profile in support_profiles_rz_mm
    ]
    if support_profiles and any(
        support_profile.ndim != 2
        or support_profile.shape[1] != 2
        or len(support_profile) < 2
        for support_profile in support_profiles
    ):
        raise AxisFirstPipelineError(
            "v116_section_intersection_failed",
            "section cutter support profiles are not valid meridional curves",
            stage="exact_sections",
        )
    start_extension = max(
        [
            float(np.dot(points[0] - support_profile[0], start_tangent))
            for support_profile in support_profiles
        ]
        + [0.0]
    )
    end_extension = max(
        [
            float(np.dot(support_profile[-1] - points[-1], end_tangent))
            for support_profile in support_profiles
        ]
        + [0.0]
    )
    margin = max(start_extension, end_extension) + 8.0 * float(tolerance_mm)
    extended = np.vstack(
        [
            points[0] - margin * start_tangent,
            points,
            points[-1] + margin * end_tangent,
        ]
    )
    if float(np.min(extended[:, 0])) <= 0.0:
        raise AxisFirstPipelineError(
            "v116_section_intersection_failed",
            "sectioning margin would cross the canonical rotation axis",
            stage="exact_sections",
            evidence={"section_surface_tangent_extension_mm": margin},
        )
    return [tuple(float(value) for value in point) for point in extended], margin


def _station_for_mapping(
    h,
    loop,
    decomposition,
    thickness,
    frame,
    *,
    support_span_h=None,
):
    segments = {}
    fit_tolerance = _source_tolerance(frame)
    _assert_section_segment_fit_quality(decomposition, fit_tolerance, h)
    for segment in decomposition.segments:
        segments[segment.name] = adapt_task7_segment_for_mapping(
            segment,
            fit_tolerance_mm=fit_tolerance,
        )
    samples = list(thickness.samples)
    source_ids = sorted(set(loop.source_face_ids) | set(loop.source_edge_ids))
    pose_samples = []
    camber_points = np.asarray([sample.camber_sq_mm for sample in samples], dtype=float)
    for index, sample in enumerate(samples):
        low = camber_points[max(index - 1, 0)]
        high = camber_points[min(index + 1, len(camber_points) - 1)]
        tangent = high - low
        pose_samples.append(
            {
                "s": float(sample.s),
                "theta_deg": math.degrees(math.atan2(float(tangent[1]), float(tangent[0]))),
            }
        )
    station = {
        "h": float(h),
        "source_ids": source_ids,
        "decomposition": {
            "segments": segments,
            "pressure_suction_assigned": False,
            "direct_curve_constructor_mode": False,
            "source_ids": source_ids,
        },
        "camber": {
            "samples": [
                {"s": float(sample.s), "q_mm": float(sample.camber_sq_mm[1])}
                for sample in samples
            ],
            "source_ids": source_ids,
        },
        "pose": {"samples": pose_samples, "source_ids": source_ids},
        "normal_thickness": {
            "samples": [
                {
                    "s": float(sample.s),
                    "thickness_mm": float(sample.thickness_mm),
                    "inside_source_loop": bool(
                        sample.inside_source_loop
                        or (
                            sample.measurement_method
                            == "paired_source_curve_witnesses"
                            and thickness.correspondence_monotone
                        )
                    ),
                }
                for sample in samples
            ],
            "source_ids": source_ids,
            # The frozen V1.1.2 review schema has one allowed enum. R16 keeps
            # the truthful per-sample method in direct_section_curve_network.
            "method": "camber_normal_line_intersections",
        },
    }
    if support_span_h is not None:
        station["support_span_h"] = float(support_span_h)
    return station


def _assert_section_segment_fit_quality(decomposition, fit_tolerance, h):
    for segment in decomposition.segments:
        if segment.fit.residual_max_mm <= fit_tolerance + 1.0e-12:
            continue
        raise AxisFirstPipelineError(
            "v116_v112_mapping_residual_exceeded",
            "measured section-segment NURBS fit exceeds source tolerance: "
            f"{segment.name} residual {segment.fit.residual_max_mm:.6f} mm > "
            f"{fit_tolerance:.6f} mm with "
            f"{len(segment.fit.control_points_sq_mm)} controls",
            stage="exact_sections",
            evidence={
                "h": float(h),
                "segment_name": segment.name,
                "fit_tolerance_mm": fit_tolerance,
                "fit_residual_rms_mm": float(segment.fit.residual_rms_mm),
                "fit_residual_maximum_mm": float(segment.fit.residual_max_mm),
                "source_to_fit_maximum_sq_mm": float(
                    segment.fit.residual_source_to_fit_max_sq_mm
                ),
                "fit_to_source_maximum_sq_mm": float(
                    segment.fit.residual_fit_to_source_max_sq_mm
                ),
                "source_to_fit_maximum_xyz_mm": float(
                    segment.fit.residual_source_to_fit_max_xyz_mm
                ),
                "fit_to_source_maximum_xyz_mm": float(
                    segment.fit.residual_fit_to_source_max_xyz_mm
                ),
                "source_edge_ids": list(segment.source_edge_ids),
                "source_sample_count": int(segment.fit.source_sample_count),
                "control_count": len(segment.fit.control_points_sq_mm),
            },
        )


def _reachable_nonperiodic_support_faces(inventory, *, start_face_id, forbidden_face_ids):
    """Return topology-connected support candidates without axial/bbox ranking."""
    records = inventory["records_by_id"]
    periodic = set(inventory["instance_by_face"])
    adjacency = inventory["source_manifest"]["adjacency"]
    supported = {
        "PLANE",
        "CYLINDER",
        "CONE",
        "BSPLINE",
        "REVOLUTION",
        "REVOLVED",
    }
    pending = [str(start_face_id)]
    visited = set(pending)
    candidates = []
    while pending:
        current = pending.pop(0)
        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor in visited or neighbor in periodic or neighbor in forbidden_face_ids:
                continue
            visited.add(neighbor)
            pending.append(neighbor)
            record = records[neighbor]
            if str(record["geometry_type"]).upper() in supported:
                candidates.append((-float(record["area_mm2"]), neighbor))
    return [face_id for _area, face_id in sorted(candidates)]


def _active_span_evidence_from_adjacency(inventory, population, topology, tolerance_mm):
    component_ids = set(population["representative_instance"]["source_face_ids"])
    root_ids = [
        face_id
        for face_id in topology.get(
            "hub_support_face_ids", [topology["hub_face_id"]]
        )
        if _shared_component_support_edges(inventory, component_ids, face_id)
    ]
    root_edges = sorted(
        {
            edge_id
            for face_id in root_ids
            for edge_id in _shared_component_support_edges(
                inventory, component_ids, face_id
            )
        }
    )
    if not root_edges:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "representative blade has no exact hub-support boundary chain",
            stage="exact_sections",
            evidence={"hub_support_face_ids": root_ids},
        )
    if topology["mode"] == "closed":
        tip_id = topology["inner_shroud_face_id"]
        tip_edges = _shared_component_support_edges(inventory, component_ids, tip_id)
    else:
        tip_id = topology["open_tip_caps"][str(population["representative_instance"]["instance_id"])]
        tip_edges = _shared_component_support_edges(inventory, component_ids, tip_id)
    if not tip_edges:
        raise AxisFirstPipelineError(
            "v116_section_intersection_failed",
            "representative blade has no exact active-tip adjacency chain",
            stage="exact_sections",
            evidence={"tip_support_face_id": tip_id},
        )
    return (
        {
            "source_face_ids": root_ids,
            "source_edge_ids": root_edges,
            "tolerance_mm": tolerance_mm,
            "residual_mm": 0.0,
            "method": "retained_root_boundary_on_authenticated_support_adjacency",
            "source_measurement": True,
            "above_transition": True,
        },
        {
            "source_face_ids": [tip_id],
            "source_edge_ids": tip_edges,
            "tolerance_mm": tolerance_mm,
            "residual_mm": 0.0,
            "method": "retained_tip_boundary_on_authenticated_support_adjacency",
            "source_measurement": True,
            "above_transition": True,
        },
    )


def _measured_active_span_interval(
    hub_points,
    tip_points,
    tolerance_mm,
    root,
    tip,
    *,
    root_attachment,
    tip_attachment,
):
    correspondence = section_recovery.solve_meridional_correspondence(hub_points, tip_points)
    hub = np.asarray(correspondence.hub_points_rz_mm, dtype=float)
    shroud = np.asarray(correspondence.tip_points_rz_mm, dtype=float)
    minimum_span = float(np.min(np.linalg.norm(shroud - hub, axis=1)))
    tolerance_clearance = 4.0 * float(tolerance_mm) / minimum_span
    attachment_measurement_available = root_attachment is not None
    root_lift = (
        0.0
        if root_attachment is None
        else max(float(value) for value in root_attachment.lift_samples_mm)
    )
    root_width = (
        0.0
        if root_attachment is None
        else float(root_attachment.attachment_width_mm)
    )
    root_boundary_margin = max(4.0 * float(tolerance_mm), 0.10 * root_width)
    root_clearance = (root_lift + root_boundary_margin) / minimum_span
    tip_lift = (
        0.0
        if tip_attachment is None
        else max(float(value) for value in tip_attachment.lift_samples_mm)
    )
    tip_width = float(
        root_width
        if tip_attachment is None
        else tip_attachment.attachment_width_mm
    )
    tip_boundary_margin = max(4.0 * float(tolerance_mm), 0.10 * tip_width)
    tip_clearance = (tip_lift + tip_boundary_margin) / minimum_span
    root_h = max(root_clearance, tolerance_clearance)
    tip_h = 1.0 - max(tip_clearance, tolerance_clearance)
    active_span_mm = (tip_h - root_h) * minimum_span
    thickness_proxy_mm = min(
        root_lift,
        root_lift if tip_attachment is None else tip_lift,
    )
    minimum_measurable_span_mm = max(
        8.0 * float(tolerance_mm),
        0.25 * thickness_proxy_mm,
    )
    if (
        not 0.0 < root_h < tip_h < 1.0
        or active_span_mm < minimum_measurable_span_mm
    ):
        raise AxisFirstPipelineError(
            "v116_span_surface_ordering_failed",
            "measured attachment clearances leave no ordered blade-body span",
            stage="exact_sections",
            evidence={
                "active_root_h": root_h,
                "active_tip_h": tip_h,
                "minimum_support_separation_mm": minimum_span,
                "active_span_mm": active_span_mm,
                "minimum_measurable_active_span_mm": minimum_measurable_span_mm,
                "local_thickness_proxy_mm": thickness_proxy_mm,
            },
        )
    source_ids = sorted(
        {
            str(source_id)
            for record in (root, tip)
            if isinstance(record, Mapping)
            for key in ("source_ids", "source_face_ids", "source_edge_ids")
            for source_id in record.get(key, ())
        }
    )
    return root_h, tip_h, {
        "active_root_h": float(root_h),
        "active_tip_h": float(tip_h),
        "minimum_support_separation_mm": minimum_span,
        "active_span_mm": active_span_mm,
        "minimum_measurable_active_span_mm": minimum_measurable_span_mm,
        "local_thickness_proxy_mm": thickness_proxy_mm,
        "source_tolerance_mm": float(tolerance_mm),
        "measurement_authority": (
            "attachment_clearance_on_authenticated_meridional_supports"
            if attachment_measurement_available
            else "authenticated_boundary_tolerance_clearance_without_attachment_measurement"
        ),
        "source_ids": source_ids,
    }


def _source_side_boundary_guided_correspondence(
    inventory,
    frame,
    instance,
    role_map,
    *,
    topology,
    hub_profile,
    tip_profile,
    hub_points_rz_mm,
    tip_points_rz_mm,
    root_attachment,
    tip_attachment,
    tolerance_mm,
):
    fallback = section_recovery.solve_meridional_correspondence(
        hub_points_rz_mm,
        tip_points_rz_mm,
        sample_count=129,
    )
    if root_attachment is None:
        return fallback, tip_attachment, {
            "status": "FALLBACK",
            "reason": "root_attachment_boundary_unavailable",
            "method": fallback.method,
        }
    side_faces = {
        role: face_id
        for face_id, role in role_map.items()
        if role in {"side_a", "side_b"}
    }
    if set(side_faces) != {"side_a", "side_b"}:
        return fallback, tip_attachment, {
            "status": "FALLBACK",
            "reason": "authenticated_side_face_roles_incomplete",
            "method": fallback.method,
        }
    root_boundary_ids = set(root_attachment.retained_source_edge_ids)
    if topology["mode"] == "closed":
        return fallback, tip_attachment, {
            "status": "FALLBACK",
            "reason": "closed_shroud_boundary_guide_deferred",
            "method": fallback.method,
        }
    else:
        tip_face_id = topology["open_tip_caps"][str(instance["instance_id"])]
        tip_boundary_ids = set(inventory["face_edge_ids"][tip_face_id])

    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    anchors = []
    tip_points_all = []
    tip_point_edge_ids = []
    source_edge_ids = set()
    side_evidence = []
    root_streamwise_authorities = set()

    def canonical_rz(points):
        result = []
        for point in points:
            canonical = _transform_point(point, matrix)
            result.append(
                [float(math.hypot(canonical[0], canonical[1])), float(canonical[2])]
            )
        return result

    def boundary_samples(edge_ids):
        points = []
        point_edge_ids = []
        for edge_id in sorted(edge_ids):
            samples = _sample_exact_edge_points(
                inventory["edges_by_id"][edge_id], 65
            )
            points.extend(samples)
            point_edge_ids.extend([edge_id] * len(samples))
        return points, point_edge_ids

    def projected_s(profile, points_rz, *, topology_authenticated=False):
        strict_gate = max(
            10.0 * float(tolerance_mm),
            4.0 * float(profile.get("residual_rms_mm", 0.0)),
            0.10,
        )
        projection = project_rz_points_to_meridional_s(
            profile,
            points_rz,
            interval_quantiles=(0.0, 1.0),
            maximum_projection_residual_mm=(
                None if topology_authenticated else strict_gate
            ),
        )
        if projection.get("status") != "PASS":
            raise AxisFirstPipelineError(
                "v116_active_span_carrier_invalid",
                "source blade-side boundary cannot be projected to its support meridian",
                stage="exact_sections",
                evidence={"projection": projection},
            )
        return np.asarray(projection["projected_s"], dtype=float), projection

    for role in ("side_a", "side_b"):
        side_face_id = side_faces[role]
        side_edge_ids = set(inventory["face_edge_ids"][side_face_id])
        root_ids = sorted(side_edge_ids & root_boundary_ids)
        tip_ids = sorted(side_edge_ids & tip_boundary_ids)
        if not root_ids or not tip_ids:
            return fallback, tip_attachment, {
                "status": "FALLBACK",
                "reason": "side_boundary_shared_edges_incomplete",
                "role": role,
                "root_source_edge_ids": root_ids,
                "tip_source_edge_ids": tip_ids,
                "method": fallback.method,
            }
        retained_point_ids = tuple(
            str(value)
            for value in getattr(
                root_attachment, "retained_point_source_edge_ids", ()
            )
        )
        paired_footprint = np.asarray(
            getattr(root_attachment, "paired_footprint_points_xyz_mm", ()),
            dtype=float,
        )
        authenticated_root_s = np.asarray(
            getattr(root_attachment, "retained_streamwise_samples_s", ())
            or getattr(root_attachment, "streamwise_samples_s", ()),
            dtype=float,
        )
        root_indices = [
            index
            for index, edge_id in enumerate(retained_point_ids)
            if edge_id in set(root_ids)
        ]
        if paired_footprint.shape == (len(retained_point_ids), 3) and len(
            root_indices
        ) >= 3:
            root_points = paired_footprint[root_indices].tolist()
            if authenticated_root_s.shape == (len(retained_point_ids),):
                root_s = authenticated_root_s[root_indices]
                if np.any(~np.isfinite(root_s)) or np.any(
                    (root_s < 0.0) | (root_s > 1.0)
                ):
                    raise AxisFirstPipelineError(
                        "v116_active_span_carrier_invalid",
                        "authenticated root streamwise witnesses are outside [0, 1]",
                        stage="exact_sections",
                        evidence={
                            "role": role,
                            "root_source_edge_ids": root_ids,
                            "streamwise_samples_s": root_s.tolist(),
                        },
                    )
                root_streamwise_authority = (
                    "authenticated_retained_boundary_streamwise_samples"
                )
            else:
                root_s = None
                root_streamwise_authority = "reprojected_root_boundary_fallback"
        else:
            root_points, _root_point_ids = boundary_samples(root_ids)
            root_s = None
            root_streamwise_authority = "reprojected_root_boundary_fallback"
        tip_points, tip_point_ids = boundary_samples(tip_ids)
        root_rz = canonical_rz(root_points)
        tip_rz = canonical_rz(tip_points)
        if root_s is None:
            root_s, root_projection = projected_s(hub_profile, root_rz)
            root_streamwise_delta_max = None
        else:
            root_projection = project_rz_points_to_meridional_s(
                hub_profile,
                root_rz,
                interval_quantiles=(0.0, 1.0),
            )
            reprojected = np.asarray(
                root_projection.get("projected_s", ()), dtype=float
            )
            root_streamwise_delta_max = (
                float(np.max(np.abs(reprojected - root_s)))
                if reprojected.shape == root_s.shape
                else None
            )
        tip_s, tip_projection = projected_s(
            tip_profile, tip_rz, topology_authenticated=True
        )
        root_streamwise_authorities.add(root_streamwise_authority)
        root_s = np.sort(root_s)
        tip_s = np.sort(tip_s)
        quantiles = np.linspace(0.0, 1.0, 33)
        paired_root = np.quantile(root_s, quantiles)
        paired_tip = np.quantile(tip_s, quantiles)
        anchors.extend(zip(paired_root.tolist(), paired_tip.tolist()))
        tip_points_all.extend(tip_rz)
        tip_point_edge_ids.extend(tip_point_ids)
        source_edge_ids.update(root_ids)
        source_edge_ids.update(tip_ids)
        side_evidence.append(
            {
                "role": role,
                "source_face_id": side_face_id,
                "root_source_edge_ids": root_ids,
                "tip_source_edge_ids": tip_ids,
                "root_streamwise_range_s": [
                    float(np.min(root_s)),
                    float(np.max(root_s)),
                ],
                "tip_streamwise_range_s": [
                    float(np.min(tip_s)),
                    float(np.max(tip_s)),
                ],
                "root_projection_residual_maximum_mm": float(
                    root_projection.get("projection_residual_maximum_mm", 0.0)
                ),
                "root_streamwise_authority": root_streamwise_authority,
                "root_streamwise_reprojection_delta_maximum": (
                    root_streamwise_delta_max
                ),
                "tip_projection_residual_maximum_mm": float(
                    tip_projection["projection_residual_maximum_mm"]
                ),
                "tip_streamwise_authority": (
                    "exact_side_tip_cap_shared_edge_with_reference_profile_projection"
                ),
            }
        )

    correspondence = (
        section_curve_authority.solve_boundary_guided_meridional_correspondence(
            hub_points_rz_mm,
            tip_points_rz_mm,
            streamwise_anchors=anchors,
            sample_count=129,
        )
    )
    tip_native_s, _tip_projection = projected_s(
        tip_profile, tip_points_all, topology_authenticated=True
    )
    tip_to_hub = np.interp(
        tip_native_s,
        np.asarray(correspondence.tip_parameters, dtype=float),
        np.asarray(correspondence.hub_parameters, dtype=float),
    )
    tip_boundary = {
        "retained_points_canonical_rz_mm": tip_points_all,
        "streamwise_samples_s": tip_to_hub.tolist(),
        "retained_point_source_edge_ids": tip_point_edge_ids,
        "lift_samples_mm": [0.0] * len(tip_points_all),
        "width_samples_mm": [0.0] * len(tip_points_all),
    }
    return correspondence, tip_boundary, {
        "status": "PASS",
        "method": correspondence.method,
        "source_edge_ids": sorted(source_edge_ids),
        "anchor_count": len(anchors),
        "root_streamwise_authority": (
            next(iter(root_streamwise_authorities))
            if len(root_streamwise_authorities) == 1
            else "mixed_authenticated_and_reprojected_root_boundaries"
        ),
        "tip_streamwise_authority": (
            "exact_side_tip_cap_shared_edge_with_reference_profile_projection"
        ),
        "side_boundaries": side_evidence,
        "tip_boundary_point_count": len(tip_points_all),
    }


def _measurement_surface_in_source_frame(surface, source_to_canonical):
    """Move a canonical meridional surface back to the immutable source B-Rep frame."""
    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf
    except ImportError as exc:
        raise AxisFirstPipelineError(
            "v116_section_intersection_failed",
            "OCP transform support is unavailable for meridional sectioning",
            stage="exact_sections",
        ) from exc
    inverse = np.linalg.inv(np.asarray(source_to_canonical, dtype=float))
    transform = gp_Trsf()
    transform.SetValues(*[float(value) for value in inverse[:3, :4].reshape(-1)])
    wrapped = getattr(surface, "wrapped", surface)
    if hasattr(wrapped, "ShapeType"):
        operation = BRepBuilderAPI_Transform(wrapped, transform, True)
        operation.Build()
        if not operation.IsDone():
            raise AxisFirstPipelineError(
                "v116_section_intersection_failed",
                "OCP failed to transform the bounded measurement surface",
                stage="exact_sections",
            )
        return operation.Shape()
    copied = surface.Copy()
    copied.Transform(transform)
    return copied


def _meridional_unwrapped_projector(profile_rz_mm, source_to_canonical, center_deg):
    profile = np.asarray(profile_rz_mm, dtype=float)
    segments = np.diff(profile, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    matrix = np.asarray(source_to_canonical, dtype=float)
    inverse_rotation = np.linalg.inv(matrix[:3, :3])
    center = math.radians(float(center_deg))

    def project(point_source):
        point = _transform_point(point_source, matrix)
        radius = math.hypot(float(point[0]), float(point[1]))
        rz = np.asarray([radius, float(point[2])], dtype=float)
        starts = profile[:-1]
        raw_fractions = np.sum((rz - starts) * segments, axis=1) / np.maximum(
            lengths**2, 1.0e-18
        )
        fractions = np.clip(raw_fractions, 0.0, 1.0)
        if len(fractions) == 1:
            fractions[0] = raw_fractions[0]
        else:
            fractions[0] = min(float(raw_fractions[0]), 1.0)
            fractions[-1] = max(float(raw_fractions[-1]), 0.0)
        candidates = starts + fractions[:, None] * segments
        index = int(np.argmin(np.linalg.norm(candidates - rz, axis=1)))
        s = cumulative[index] + fractions[index] * lengths[index]
        theta = math.atan2(float(point[1]), float(point[0]))
        delta = (theta - center + math.pi) % (2.0 * math.pi) - math.pi
        return float(s), float(radius * delta)

    tangent = segments[len(segments) // 2] / max(lengths[len(lengths) // 2], 1.0e-12)
    normal_canonical = np.asarray([-tangent[1], 0.0, tangent[0]], dtype=float)
    normal_source = inverse_rotation @ normal_canonical
    return project, normal_source


def _preliminary_section_metrics(loop, decomposition, thickness):
    side_a = decomposition.segment("side_a").points_sq_mm
    side_b = decomposition.segment("side_b").points_sq_mm
    q_values = [point[1] for point in (*side_a, *side_b)]
    curvature = [
        abs(segment.fit.start_curvature_per_mm)
        for segment in decomposition.segments
    ] + [abs(segment.fit.end_curvature_per_mm) for segment in decomposition.segments]
    return {
        "mean_thickness_mm": float(thickness.mean_mm),
        "camber_turn_deg": math.degrees(
            math.atan2(max(q_values) - min(q_values), max(1.0e-9, max(point[0] for point in (*side_a, *side_b)) - min(point[0] for point in (*side_a, *side_b))))
        ),
        "edge_curvature_per_mm": float(max(curvature)),
        "closure_gap_mm": float(loop.closure_gap_mm),
    }


def _measure_family_attachments(
    inventory,
    frame,
    population,
    topology,
    *,
    support_profiles,
    include_shroud,
):
    instance = population["representative_instance"]
    component_ids = set(instance["source_face_ids"])
    root = _measure_attachment_between_supports(
        inventory,
        frame,
        component_ids,
        topology.get("hub_support_face_ids", [topology["hub_face_id"]]),
        upper=True,
        kind="root",
        support_profile=support_profiles["hub"],
    )
    result = {"root": root}
    if include_shroud:
        result["shroud"] = _measure_attachment_between_supports(
            inventory,
            frame,
            component_ids,
            [topology["inner_shroud_face_id"]],
            upper=False,
            kind="shroud",
            support_profile=support_profiles["tip_or_shroud"],
        )
    return result


def _measure_attachment_between_supports(
    inventory,
    frame,
    component_ids,
    support_ids,
    *,
    upper,
    kind,
    support_profile,
):
    support_ids = tuple(sorted(set(support_ids)))
    component_edges = _component_edge_ids(inventory, component_ids)
    support_edge_ids = set().union(
        *(set(inventory["face_edge_ids"][face_id]) for face_id in support_ids)
    )
    footprint_ids = sorted(component_edges & support_edge_ids)
    if not footprint_ids:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            f"{kind} support has no exact shared boundary with representative blade",
            stage="exact_sections",
            evidence={"support_face_ids": list(support_ids)},
        )
    retained_ids, termination_ids, span_ids = _attachment_adjacency_chains(
        inventory, component_edges, footprint_ids, support_ids
    )
    if not retained_ids or not span_ids or not termination_ids:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            f"{kind} attachment lacks a complete source adjacency chain",
            stage="exact_sections",
            evidence={
                "footprint_source_edge_ids": footprint_ids,
                "retained_source_edge_ids": retained_ids,
                "span_direction_source_ids": span_ids,
                "termination_source_edge_ids": termination_ids,
            },
        )
    footprint = _boundary_curve_points(inventory, footprint_ids, sample_count=33)
    retained, retained_point_edge_ids = _boundary_interior_points(
        inventory, retained_ids, sample_count=5, with_edge_ids=True
    )
    termination = _boundary_vertices(inventory, termination_ids, minimum=2)
    footprint_candidates = _attachment_footprint_candidates(
        inventory, retained_ids, footprint_ids, support_ids
    )
    local_span_directions, paired_footprint = _boundary_pair_directions(
        inventory,
        retained,
        footprint_ids,
        candidate_footprint_edge_ids=[
            footprint_candidates[edge_id] for edge_id in retained_point_edge_ids
        ],
    )
    support_normals, streamwise_parameters = _support_profile_sample_frames(
        frame["source_to_canonical_matrix"],
        support_profile,
        paired_footprint,
        retained,
    )
    face_ids = sorted(
        set(component_ids)
        | set(support_ids)
        | {
            face_id
            for edge_id in footprint_ids + retained_ids + termination_ids
            for face_id in _edge_adjacent_face_ids(inventory, edge_id)
        }
    )
    function = (
        section_recovery.measure_root_attachment
        if kind == "root"
        else section_recovery.measure_shroud_attachment
    )
    measurement = function(
        footprint,
        retained,
        local_span_directions_xyz=local_span_directions,
        paired_footprint_points_xyz_mm=paired_footprint,
        support_normal_directions_xyz=support_normals,
        streamwise_parameters_s=streamwise_parameters,
        width_direction_xyz=None,
        source_face_ids=face_ids,
        footprint_source_edge_ids=footprint_ids,
        retained_source_edge_ids=retained_ids,
        span_direction_source_ids=span_ids,
        termination_boundary_xyz_mm=termination,
        termination_source_edge_ids=termination_ids,
        source_shape=inventory["shape"],
        source_edges_by_id=inventory["edges_by_id"],
        source_faces_by_id=inventory["faces_by_id"],
        provenance_kind="occt_source_adjacency",
        span_direction_method="authenticated_boundary_normal",
        tolerance_mm=max(_source_tolerance(frame), 1.0e-6),
    )
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)

    def canonical_rz(points):
        result = []
        for point in np.asarray(points, dtype=float):
            canonical = _transform_point(point, matrix)
            result.append(
                (
                    float(math.hypot(canonical[0], canonical[1])),
                    float(canonical[2]),
                )
            )
        return tuple(result)

    retained_rz = canonical_rz(retained)
    retained_projection = project_rz_points_to_meridional_s(
        support_profile,
        retained_rz,
        interval_quantiles=(0.0, 1.0),
    )
    if retained_projection.get("status") != "PASS":
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            f"{kind} retained boundary cannot be placed on meridional S",
            stage="exact_sections",
            evidence={"projection": retained_projection},
        )

    termination_rz = canonical_rz(termination)
    termination_projection = project_rz_points_to_meridional_s(
        support_profile,
        termination_rz,
        interval_quantiles=(0.0, 1.0),
        maximum_projection_residual_mm=max(
            10.0 * _source_tolerance(frame),
            4.0 * float(support_profile.get("residual_rms_mm", 0.0)),
            0.05,
            1.5 * float(measurement.lift_mm),
            1.5 * float(measurement.attachment_width_mm),
        ),
    )
    if termination_projection.get("status") != "PASS":
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            f"{kind} termination boundary cannot be placed on meridional S",
            stage="exact_sections",
            evidence={"projection": termination_projection},
        )


    return replace(
        measurement,
        footprint_points_canonical_rz_mm=canonical_rz(paired_footprint),
        retained_points_canonical_rz_mm=retained_rz,
        retained_point_source_edge_ids=tuple(
            str(value) for value in retained_point_edge_ids
        ),
        retained_streamwise_samples_s=tuple(
            float(value) for value in retained_projection["projected_s"]
        ),
        retained_streamwise_projection_residual_max_mm=float(
            retained_projection["projection_residual_maximum_mm"]
        ),
        retained_streamwise_projection_method=(
            "topology_authenticated_retained_edge_nearest_meridian_projection"
        ),
        termination_points_canonical_rz_mm=termination_rz,
        termination_streamwise_samples_s=tuple(
            float(value) for value in termination_projection["projected_s"]
        ),
    )


def _assemble_measurements(inventory, frame, support, periodic, sections):
    topology_mode = support["topology_mode"]
    topology_ids = support["support_face_ids"]
    material = _material_measurements(
        inventory, frame, topology_ids, sections, support
    )
    populations = {
        "main": _population_for_mapping(periodic["main"]),
        "splitter": _population_for_mapping(periodic["splitter"]),
        "relative_phase_pitch": 0.0,
        "closure_pass": periodic["closure_pass"],
        "collision_free": periodic["collision_free"],
        "collision_status": periodic["collision_status"],
        "source_topology_separated": periodic["source_topology_separated"],
        "exact_brep_collision_checked": periodic["exact_brep_collision_checked"],
        "exact_brep_collision_free": periodic["exact_brep_collision_free"],
        "phase_consistent": periodic["phase_consistent"],
        "source_ids": periodic["source_ids"],
    }
    if periodic["splitter"] is not None:
        main_pitch = float(periodic["main"]["pitch_deg"])
        relative = float(periodic["splitter"]["phase_relative_to_main_deg"]) / main_pitch
        populations["relative_phase_pitch"] = relative % 1.0
    source_ids = sorted(inventory["faces_by_id"])
    section_families = copy.deepcopy(sections["section_families"])
    for family in section_families.values():
        family.pop("section_extraction_performance", None)
    return {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "frame": _mapping_frame(frame),
        "provenance": {
            "source_sha256": inventory["source_manifest"]["sha256"],
            "source_entity_ids": source_ids,
            "algorithm_version": ALGORITHM_VERSION,
        },
        "topology": {
            "mode": topology_mode,
            "outer_diameter_mm": 2.0 * float(frame["outer_radius_mm"]),
            "material_shroud": topology_mode == "closed",
            "material_measurements": material,
            "source_ids": sorted(
                set(
                    topology_ids.get(
                        "hub_support_face_ids", [topology_ids["hub_face_id"]]
                    )
                )
                | {
                    value
                    for key, value in topology_ids.items()
                    if key.endswith("shroud_face_id")
                }
            ),
        },
        "support_fits": copy.deepcopy(support["mapping_fits"]),
        "populations": populations,
        "section_families": section_families,
        "attachments": copy.deepcopy(sections["attachments"]),
    }


def _material_measurements(inventory, frame, topology, sections, support):
    axis = _source_axis(frame)
    tolerance = _source_tolerance(frame)
    cylinders = _authenticated_coaxial_cylinders(
        inventory, axis, float(frame["outer_radius_mm"]), tolerance
    )
    if not cylinders:
        _material_failure(
            "mounting_bore_radius_mm",
            "no coaxial analytic cylinder with matching circular source edges",
            {"coaxial_cylinder_candidates": []},
        )
    caps_by_cylinder = {
        candidate["face_id"]: _perpendicular_plane_neighbors_for_cylinder(
            inventory, candidate, axis, tolerance
        )
        for candidate in cylinders
    }
    bore = _select_mounting_bore_group(
        cylinders,
        frame,
        tolerance,
        caps_by_cylinder=caps_by_cylinder,
    )

    bore_caps = caps_by_cylinder[bore["face_id"]]
    bore_caps.sort(key=lambda item: item["axis_parameter_mm"])
    bore_axis_limits, bore_axis_limit_edge_ids = _coaxial_cylinder_axis_limits(
        inventory,
        bore,
        axis,
    )

    core_candidates = []
    for candidate in cylinders:
        if candidate is bore:
            continue
        caps = caps_by_cylinder[candidate["face_id"]]
        if len(caps) != 2:
            continue
        caps.sort(key=lambda item: item["axis_parameter_mm"])
        if len(bore_caps) == 2 and (
            bore_caps[0]["axis_parameter_mm"] + tolerance
            < caps[0]["axis_parameter_mm"]
            < caps[1]["axis_parameter_mm"]
            < bore_caps[1]["axis_parameter_mm"] - tolerance
        ):
            core_candidates.append({**candidate, "cap_planes": caps})
    if len(bore_caps) == 2 and len(core_candidates) == 1:
        outer_low, outer_high = bore_caps
        core = core_candidates[0]
        inner_low, inner_high = core["cap_planes"]
        wall = float(core["radius_mm"] - bore["radius_mm"])
        bottom = float(
            inner_low["axis_parameter_mm"] - outer_low["axis_parameter_mm"]
        )
        top = float(
            outer_high["axis_parameter_mm"] - inner_high["axis_parameter_mm"]
        )
        material_distance_evidence = {
            "method": "nested_coaxial_cylinder_and_parallel_caps",
            "core": core,
            "bottom_plane_pair": [outer_low, inner_low],
            "top_plane_pair": [inner_high, outer_high],
            "bottom_source_face_ids": [
                outer_low["face_id"],
                inner_low["face_id"],
            ],
            "top_source_face_ids": [
                inner_high["face_id"],
                outer_high["face_id"],
            ],
            "bottom_axis_parameters_mm": [
                outer_low["axis_parameter_mm"],
                inner_low["axis_parameter_mm"],
            ],
            "top_axis_parameters_mm": [
                inner_high["axis_parameter_mm"],
                outer_high["axis_parameter_mm"],
            ],
            "wall_source_ids": sorted(
                set(bore["source_ids"]) | set(core["source_ids"])
            ),
        }
    else:
        (
            wall,
            bottom,
            top,
            material_distance_evidence,
        ) = _measure_support_bound_hub_material(
            inventory,
            frame,
            bore,
            support,
            axis,
            tolerance,
        )
    if min(wall, bottom, top) <= tolerance:
        _material_failure(
            "hub_wall_thickness_mm",
            "authenticated nested material distances are not positive",
            {
                "wall_mm": wall,
                "bottom_mm": bottom,
                "top_mm": top,
                "measurement_evidence": material_distance_evidence,
            },
        )

    root_radius = _measure_transition_radius(
        inventory,
        topology,
        transition_kind="root",
        tolerance_mm=tolerance,
    )
    tip_radius = _measure_transition_radius(
        inventory,
        topology,
        transition_kind="tip",
        tolerance_mm=tolerance,
    )
    chamfer = _measure_bore_edge_treatment(
        inventory,
        bore,
        bore_caps,
        tolerance_mm=tolerance,
        material_distance_evidence=material_distance_evidence,
        axis=axis,
    )
    result = {
        "mounting_bore_radius_mm": _material_record(
            bore["radius_mm"],
            "coaxial_cylinder_and_circular_edges",
            bore["source_ids"],
            {
                "analytic_surface": "CYLINDER",
                "axis_residual_mm": bore["axis_residual_mm"],
                "circular_source_edge_ids": bore["circular_source_edge_ids"],
                "canonical_axis_limits_mm": list(bore_axis_limits),
                "axis_limit_source_edge_ids": bore_axis_limit_edge_ids,
                "cap_source_face_ids": [
                    str(item["face_id"]) for item in bore_caps
                ],
            },
        ),
        "hub_wall_thickness_mm": _material_record(
            wall,
            "coaxial_cylinder_radial_face_distance",
            material_distance_evidence["wall_source_ids"],
            {
                "inner_radius_mm": bore["radius_mm"],
                "outer_radius_mm": bore["radius_mm"] + wall,
                "bore_face_ids": list(bore["face_ids"]),
                "measurement_evidence": material_distance_evidence,
            },
        ),
        "hub_bottom_thickness_mm": _material_record(
            bottom,
            "parallel_material_plane_distance",
            material_distance_evidence["bottom_source_face_ids"],
            {
                "axis_parameters_mm": material_distance_evidence[
                    "bottom_axis_parameters_mm"
                ],
                "material_orientation": "canonical_axis_low_side",
                "measurement_evidence": material_distance_evidence,
            },
        ),
        "hub_top_cap_thickness_mm": _material_record(
            top,
            "parallel_material_plane_distance",
            material_distance_evidence["top_source_face_ids"],
            {
                "axis_parameters_mm": material_distance_evidence[
                    "top_axis_parameters_mm"
                ],
                "material_orientation": "canonical_axis_high_side",
                "measurement_evidence": material_distance_evidence,
            },
        ),
        "root_fillet_radius_mm": root_radius,
        "tip_edge_radius_mm": tip_radius,
        "hub_chamfer_radius_mm": chamfer,
    }
    if topology["mode"] == "closed":
        result.update(
            _measure_closed_shroud_material(
                inventory, frame, topology, support, tolerance
            )
        )
    return result


def _material_record(value, method, source_ids, evidence):
    return {
        "value": float(value),
        "unit": "mm",
        "source_ids": sorted(set(source_ids)),
        "measured": True,
        "measurement_authority": "occt_exact_brep_feature_measurement",
        "method": method,
        "evidence": copy.deepcopy(dict(evidence)),
    }


def _material_failure(field, message, evidence):
    raise AxisFirstPipelineError(
        "v116_v112_mapping_residual_exceeded",
        message,
        stage="measurement_bundle",
        evidence={
            "material_field": field,
            **copy.deepcopy(dict(evidence)),
            "forbidden_authorities": [
                "bounding_box_extent",
                "preset_default",
                "implicit_zero",
            ],
        },
    )


def _source_axis(frame):
    origin = np.asarray(frame["source_axis_origin_mm"], dtype=float)
    direction = np.asarray(frame["source_axis_direction"], dtype=float)
    direction /= max(float(np.linalg.norm(direction)), 1.0e-18)
    return origin, direction


def _coaxial_cylinder_axis_limits(inventory, cylinder, axis):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "mounting_bore_radius_mm",
            "OCP curve adaptor is unavailable for bore material limits",
            {"exception_type": type(exc).__name__},
        )
    origin, direction = axis
    witnesses = []
    for edge_id in cylinder.get("circular_source_edge_ids", ()):
        edge = inventory["edges_by_id"].get(edge_id)
        if edge is None or edge.geomType() != "CIRCLE":
            continue
        circle = BRepAdaptor_Curve(edge.wrapped).Circle()
        center = np.asarray(circle.Location().Coord(), dtype=float)
        witnesses.append(
            (
                float(np.dot(center - origin, direction)),
                str(edge_id),
            )
        )
    if len(witnesses) < 2:
        _material_failure(
            "mounting_bore_radius_mm",
            "authenticated bore cylinder lacks two independent axial edge limits",
            {
                "bore_face_ids": list(cylinder.get("face_ids", ())),
                "circular_source_edge_ids": list(
                    cylinder.get("circular_source_edge_ids", ())
                ),
                "axis_limit_witnesses": witnesses,
            },
        )
    witnesses.sort()
    return (
        (float(witnesses[0][0]), float(witnesses[-1][0])),
        [witnesses[0][1], witnesses[-1][1]],
    )


def _authenticated_coaxial_cylinders(inventory, axis, outer_radius, tolerance):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "mounting_bore_radius_mm",
            "OCP analytic measurement adaptors are unavailable",
            {"exception_type": type(exc).__name__},
        )
    origin, direction = axis
    records = []
    for face_id, face in inventory["faces_by_id"].items():
        if face_id in inventory["instance_by_face"] or face.geomType() != "CYLINDER":
            continue
        adaptor = BRepAdaptor_Surface(face.wrapped)
        cylinder = adaptor.Cylinder()
        cylinder_axis = cylinder.Axis()
        candidate_direction = np.asarray(
            [
                cylinder_axis.Direction().X(),
                cylinder_axis.Direction().Y(),
                cylinder_axis.Direction().Z(),
            ],
            dtype=float,
        )
        candidate_origin = np.asarray(
            [
                cylinder_axis.Location().X(),
                cylinder_axis.Location().Y(),
                cylinder_axis.Location().Z(),
            ],
            dtype=float,
        )
        angular_alignment = abs(float(np.dot(candidate_direction, direction)))
        line_residual = float(
            np.linalg.norm(np.cross(candidate_origin - origin, direction))
        )
        radius = float(cylinder.Radius())
        if (
            angular_alignment < math.cos(math.radians(0.05))
            or line_residual > tolerance
            or not tolerance < radius < 0.6 * outer_radius
        ):
            continue
        circular_ids = []
        for edge_id in _face_edge_ids(inventory, face_id):
            edge = inventory["edges_by_id"][edge_id]
            if edge.geomType() != "CIRCLE":
                continue
            circle = BRepAdaptor_Curve(edge.wrapped).Circle()
            if abs(float(circle.Radius()) - radius) <= tolerance:
                circular_ids.append(edge_id)
        if len(circular_ids) < 2:
            continue
        records.append(
            {
                "face_id": face_id,
                "face_ids": [face_id],
                "radius_mm": radius,
                "axis_residual_mm": line_residual,
                "axis_alignment": angular_alignment,
                "analytic_area_mm2": float(
                    inventory["records_by_id"][face_id]["area_mm2"]
                ),
                "circular_source_edge_ids": sorted(circular_ids),
                "source_ids": [face_id, *sorted(circular_ids)],
            }
        )
    return _group_coaxial_cylinder_records(records, tolerance)


def _group_coaxial_cylinder_records(records, tolerance):
    groups = []
    for record in sorted(records, key=lambda item: (item["radius_mm"], item["face_id"])):
        group = next(
            (
                candidate
                for candidate in groups
                if abs(candidate["radius_mm"] - record["radius_mm"]) <= tolerance
            ),
            None,
        )
        if group is None:
            groups.append(copy.deepcopy(record))
            continue
        group["face_ids"] = sorted(
            set(group["face_ids"]) | set(record["face_ids"])
        )
        group["face_id"] = group["face_ids"][0]
        group["axis_residual_mm"] = max(
            group["axis_residual_mm"], record["axis_residual_mm"]
        )
        group["axis_alignment"] = min(
            group["axis_alignment"], record["axis_alignment"]
        )
        group["analytic_area_mm2"] += record["analytic_area_mm2"]
        group["circular_source_edge_ids"] = sorted(
            set(group["circular_source_edge_ids"])
            | set(record["circular_source_edge_ids"])
        )
        group["source_ids"] = sorted(
            set(group["source_ids"]) | set(record["source_ids"])
        )
    return sorted(groups, key=lambda item: (item["radius_mm"], item["face_id"]))


def _select_mounting_bore_group(
    cylinders, frame, tolerance, *, caps_by_cylinder=None
):
    caps_by_cylinder = caps_by_cylinder or {}
    nested_bore_candidates = []
    for candidate in cylinders:
        caps = sorted(
            caps_by_cylinder.get(candidate["face_id"], ()),
            key=lambda item: item["axis_parameter_mm"],
        )
        if len(caps) != 2:
            continue
        for core in cylinders:
            if core is candidate or core["radius_mm"] <= candidate["radius_mm"]:
                continue
            core_caps = sorted(
                caps_by_cylinder.get(core["face_id"], ()),
                key=lambda item: item["axis_parameter_mm"],
            )
            if len(core_caps) != 2:
                continue
            if (
                caps[0]["axis_parameter_mm"] + tolerance
                < core_caps[0]["axis_parameter_mm"]
                < core_caps[1]["axis_parameter_mm"]
                < caps[1]["axis_parameter_mm"] - tolerance
            ):
                nested_bore_candidates.append(candidate)
                break
    if len(nested_bore_candidates) == 1:
        return nested_bore_candidates[0]
    if len(nested_bore_candidates) > 1:
        _material_failure(
            "mounting_bore_radius_mm",
            "multiple coaxial cylinder families enclose nested material cores",
            {"nested_bore_candidates": nested_bore_candidates},
        )

    target = frame.get("main_bore_radius_mm")
    if target is None:
        _material_failure(
            "mounting_bore_radius_mm",
            "axis consensus did not identify an area-dominant coaxial bore radius",
            {"coaxial_cylinder_candidates": cylinders},
        )
    candidates = [
        item
        for item in cylinders
        if abs(float(item["radius_mm"]) - float(target)) <= tolerance
    ]
    if len(candidates) != 1:
        _material_failure(
            "mounting_bore_radius_mm",
            "axis-consensus bore radius does not resolve one geometric cylinder family",
            {
                "axis_consensus_bore_radius_mm": target,
                "coaxial_cylinder_candidates": cylinders,
            },
        )
    return candidates[0]


def _perpendicular_plane_neighbors_for_cylinder(
    inventory, cylinder, axis, tolerance
):
    by_face_id = {}
    for face_id in cylinder["face_ids"]:
        for record in _perpendicular_plane_neighbors(
            inventory, face_id, axis, tolerance
        ):
            by_face_id[record["face_id"]] = record
    return list(by_face_id.values())


def _perpendicular_plane_neighbors(inventory, face_id, axis, tolerance):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "hub_bottom_thickness_mm",
            "OCP analytic measurement adaptors are unavailable",
            {"exception_type": type(exc).__name__},
        )
    origin, direction = axis
    result = []
    for adjacent_id in inventory["source_manifest"]["adjacency"].get(face_id, ()):
        adjacent = inventory["faces_by_id"][adjacent_id]
        if adjacent.geomType() != "PLANE":
            continue
        plane = BRepAdaptor_Surface(adjacent.wrapped).Plane()
        plane_axis = plane.Axis()
        normal = np.asarray(
            [
                plane_axis.Direction().X(),
                plane_axis.Direction().Y(),
                plane_axis.Direction().Z(),
            ],
            dtype=float,
        )
        if abs(float(np.dot(normal, direction))) < math.cos(math.radians(0.05)):
            continue
        location = np.asarray(
            [
                plane_axis.Location().X(),
                plane_axis.Location().Y(),
                plane_axis.Location().Z(),
            ],
            dtype=float,
        )
        result.append(
            {
                "face_id": adjacent_id,
                "axis_parameter_mm": float(np.dot(location - origin, direction)),
                "parallel_residual": float(
                    1.0 - abs(float(np.dot(normal, direction)))
                ),
                "source_edge_ids": sorted(
                    _face_edge_ids(inventory, face_id)
                    & _face_edge_ids(inventory, adjacent_id)
                ),
            }
        )
    return result


def _measure_transition_radius(
    inventory, topology, *, transition_kind, tolerance_mm
):
    semantics = inventory["semantics"]
    adjacency = inventory["source_manifest"]["adjacency"]
    measured = []
    exhaustive_edges = set()
    exhaustive_faces = set()
    direct_sharp_edges = set()
    required_direct_boundaries = 0
    authenticated_direct_boundaries = 0
    for population in semantics["periodic_population_recovery"]["populations"]:
        for instance in population["instances"]:
            component = set(instance["source_face_ids"]) - (
                _topology_material_support_face_ids(topology)
            )
            side_ids = set(
                instance["component_completeness"]["blade_side_face_ids"]
            )
            if transition_kind == "root":
                support_ids = topology.get(
                    "hub_support_face_ids", [topology["hub_face_id"]]
                )
                bound_supports = [
                    support_id
                    for support_id in support_ids
                    if any(
                        support_id in adjacency.get(face_id, ())
                        for face_id in component
                    )
                ]
                if not bound_supports:
                    _material_failure(
                        "root_fillet_radius_mm",
                        "periodic blade is not bound to an authenticated hub support sector",
                        {
                            "instance_id": instance["instance_id"],
                            "hub_support_face_ids": sorted(support_ids),
                        },
                    )
                contact_faces = {
                    face_id
                    for face_id in component
                    if set(bound_supports).intersection(adjacency.get(face_id, ()))
                }
                transition_faces = {
                    face_id
                    for face_id in contact_faces - side_ids
                    if len(side_ids.intersection(adjacency.get(face_id, ()))) < 2
                    and inventory["faces_by_id"][face_id].geomType()
                    in {"CYLINDER", "TORUS"}
                }
                for side_id in side_ids:
                    required_direct_boundaries += 1
                    direct = set().union(
                        *(
                            _face_edge_ids(inventory, support_id)
                            & _face_edge_ids(inventory, side_id)
                            for support_id in bound_supports
                        )
                    )
                    if direct:
                        authenticated_direct_boundaries += 1
                        direct_sharp_edges.update(direct)
                exhaustive_faces.update({*bound_supports, *contact_faces, *side_ids})
                for support_id in bound_supports:
                    exhaustive_edges.update(
                        _shared_component_support_edges(
                            inventory, component, support_id
                        )
                    )
            else:
                cap_id = topology.get("open_tip_caps", {}).get(
                    str(instance["instance_id"])
                )
                if cap_id is None:
                    _material_failure(
                        "tip_edge_radius_mm",
                        "tip-edge curvature requires authenticated open tip caps",
                        {"instance_id": instance["instance_id"]},
                    )
                cap_neighbors = set(adjacency.get(cap_id, ())) & component
                transition_faces = {
                    face_id
                    for face_id in cap_neighbors - side_ids
                    if len(side_ids.intersection(adjacency.get(face_id, ()))) == 1
                }
                for side_id in side_ids:
                    required_direct_boundaries += 1
                    direct = (
                        _face_edge_ids(inventory, cap_id)
                        & _face_edge_ids(inventory, side_id)
                    )
                    if direct:
                        authenticated_direct_boundaries += 1
                        direct_sharp_edges.update(direct)
                exhaustive_faces.update({cap_id, *cap_neighbors, *side_ids})
                exhaustive_edges.update(_face_edge_ids(inventory, cap_id))
            for face_id in sorted(transition_faces):
                value = _analytic_curvature_radius(
                    inventory["faces_by_id"][face_id]
                )
                if value is not None:
                    measured.append((value, face_id))

    field = (
        "root_fillet_radius_mm"
        if transition_kind == "root"
        else "tip_edge_radius_mm"
    )
    if (
        required_direct_boundaries > 0
        and authenticated_direct_boundaries == required_direct_boundaries
        and exhaustive_edges
        and exhaustive_faces
    ):
        exhaustive = sorted(exhaustive_faces | exhaustive_edges)
        return _material_record(
            0.0,
            "exhaustive_topology_absence",
            exhaustive,
            {
                "absence_proven": True,
                "transition_kind": transition_kind,
                "authenticated_direct_boundary_count": authenticated_direct_boundaries,
                "direct_sharp_source_edge_ids": sorted(direct_sharp_edges),
                "exhaustive_source_ids": exhaustive,
            },
        )
    if measured:
        values = np.asarray([item[0] for item in measured], dtype=float)
        if float(np.max(values) - np.min(values)) > tolerance_mm:
            _material_failure(
                field,
                "periodic transition curvature radii are inconsistent",
                {
                    "curvature_radius_by_face_mm": {
                        face_id: value for value, face_id in measured
                    }
                },
            )
        return _material_record(
            float(np.mean(values)),
            "analytic_transition_surface_curvature",
            [face_id for _value, face_id in measured],
            {
                "transition_kind": transition_kind,
                "curvature_radius_by_face_mm": {
                    face_id: value for value, face_id in measured
                },
            },
        )
    if not exhaustive_edges or not exhaustive_faces:
        _material_failure(
            field,
            "transition radius is neither analytically measured nor exhaustively absent",
            {
                "direct_source_edge_ids": sorted(direct_sharp_edges),
                "exhaustive_source_edge_ids": sorted(exhaustive_edges),
                "exhaustive_source_face_ids": sorted(exhaustive_faces),
            },
        )
    exhaustive = sorted(exhaustive_faces | exhaustive_edges)
    return _material_record(
        0.0,
        "exhaustive_topology_absence",
        exhaustive,
        {
            "absence_proven": True,
            "transition_kind": transition_kind,
            "direct_sharp_source_edge_ids": sorted(direct_sharp_edges),
            "exhaustive_incident_face_geometry_types": {
                face_id: inventory["faces_by_id"][face_id].geomType()
                for face_id in sorted(exhaustive_faces)
            },
            "exhaustive_source_ids": exhaustive,
        },
    )


def _analytic_curvature_radius(face):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError:  # pragma: no cover
        return None
    adaptor = BRepAdaptor_Surface(face.wrapped)
    if face.geomType() == "CYLINDER":
        return float(adaptor.Cylinder().Radius())
    if face.geomType() == "TORUS":
        return float(adaptor.Torus().MinorRadius())
    return None


def _measure_bore_edge_treatment(
    inventory,
    bore,
    bore_caps,
    *,
    tolerance_mm,
    material_distance_evidence=None,
    axis=None,
):
    bore_face_ids = set(bore["face_ids"])
    direct_edges = set()
    exhaustive_faces = set(bore_face_ids)
    for cap in bore_caps:
        exhaustive_faces.add(cap["face_id"])
        for bore_face_id in bore_face_ids:
            direct_edges.update(
                _face_edge_ids(inventory, bore_face_id)
                & _face_edge_ids(inventory, cap["face_id"])
            )
    adjacent_faces = set().union(
        *(
            set(inventory["source_manifest"]["adjacency"].get(face_id, ()))
            for face_id in bore_face_ids
        )
    )
    exhaustive_faces.update(adjacent_faces)
    treatment_faces = {
        face_id
        for face_id in adjacent_faces
        if face_id not in {cap["face_id"] for cap in bore_caps}
        and inventory["faces_by_id"][face_id].geomType() in {"CONE", "TORUS"}
    }
    if treatment_faces:
        if (
            material_distance_evidence
            and material_distance_evidence.get("method")
            == "support_bound_axisymmetric_material_envelope"
            and axis is not None
        ):
            return _measure_coaxial_bore_opening_treatment(
                inventory,
                bore,
                treatment_faces,
                material_distance_evidence,
                axis,
                tolerance_mm,
            )
        _material_failure(
            "hub_chamfer_radius_mm",
            "bore edge treatment is present but lacks an unambiguous scalar curvature authority",
            {"treatment_source_face_ids": sorted(treatment_faces)},
        )
    if len(direct_edges) < 2:
        _material_failure(
            "hub_chamfer_radius_mm",
            "bore edge treatment absence is not proven at both material caps",
            {"direct_source_edge_ids": sorted(direct_edges)},
        )
    exhaustive = sorted(exhaustive_faces | direct_edges)
    return _material_record(
        0.0,
        "exhaustive_topology_absence",
        exhaustive,
        {
            "absence_proven": True,
            "transition_kind": "hub_bore_chamfer",
            "direct_sharp_source_edge_ids": sorted(direct_edges),
            "exhaustive_source_ids": exhaustive,
        },
    )


def _measure_closed_shroud_material(
    inventory, frame, topology, support, tolerance_mm
):
    inner_id = topology["inner_shroud_face_id"]
    outer_id = topology["outer_shroud_face_id"]
    inner = inventory["faces_by_id"][inner_id]
    outer = inventory["faces_by_id"][outer_id]
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "hood_wall_thickness_mm",
            "OCP analytic measurement adaptors are unavailable",
            {"exception_type": type(exc).__name__},
        )
    inner_adaptor = BRepAdaptor_Surface(inner.wrapped)
    outer_adaptor = BRepAdaptor_Surface(outer.wrapped)
    if inner.geomType() == outer.geomType() == "CYLINDER":
        inner_radius = float(inner_adaptor.Cylinder().Radius())
        outer_radius = float(outer_adaptor.Cylinder().Radius())
        method = "paired_coaxial_cylinder_radial_distance"
    elif inner.geomType() == outer.geomType() == "CONE":
        inner_cone = inner_adaptor.Cone()
        outer_cone = outer_adaptor.Cone()
        if abs(float(inner_cone.SemiAngle() - outer_cone.SemiAngle())) > math.radians(0.05):
            _material_failure(
                "hood_wall_thickness_mm",
                "paired shroud cones do not share an analytic semi-angle",
                {"inner_face_id": inner_id, "outer_face_id": outer_id},
            )
        inner_radius = float(inner_cone.RefRadius())
        outer_radius = float(outer_cone.RefRadius())
        method = "paired_coaxial_cone_radial_distance"
    elif inner.geomType() == outer.geomType() == "PLANE":
        inner_plane = inner_adaptor.Plane()
        outer_plane = outer_adaptor.Plane()
        inner_normal = np.asarray(
            inner_plane.Axis().Direction().Coord(), dtype=float
        )
        outer_normal = np.asarray(
            outer_plane.Axis().Direction().Coord(), dtype=float
        )
        if abs(abs(float(np.dot(inner_normal, outer_normal))) - 1.0) > 1.0e-8:
            _material_failure(
                "hood_wall_thickness_mm",
                "paired shroud planes are not parallel",
                {"inner_face_id": inner_id, "outer_face_id": outer_id},
            )
        inner_location = np.asarray(inner_plane.Location().Coord(), dtype=float)
        outer_location = np.asarray(outer_plane.Location().Coord(), dtype=float)
        thickness = abs(float(np.dot(outer_location - inner_location, inner_normal)))
        inner_radius = 0.0
        outer_radius = thickness
        method = "paired_parallel_plane_normal_distance"
    else:
        _material_failure(
            "hood_wall_thickness_mm",
            "closed shroud supports lack a representable exact analytic wall pair",
            {
                "inner_face_id": inner_id,
                "inner_geometry_type": inner.geomType(),
                "outer_face_id": outer_id,
                "outer_geometry_type": outer.geomType(),
            },
        )
    thickness = (
        thickness
        if inner.geomType() == outer.geomType() == "PLANE"
        else abs(outer_radius - inner_radius)
    )
    if thickness <= tolerance_mm:
        _material_failure(
            "hood_wall_thickness_mm",
            "paired shroud material faces have no positive wall distance",
            {"inner_radius_mm": inner_radius, "outer_radius_mm": outer_radius},
        )
    chamfer = _measure_closed_shroud_chamfer_absence(
        inventory, inner_id, outer_id
    )
    return {
        "hood_wall_thickness_mm": _material_record(
            thickness,
            method,
            [inner_id, outer_id],
            {
                "inner_radius_mm": inner_radius,
                "outer_radius_mm": outer_radius,
            },
        ),
        "hood_chamfer_radius_mm": chamfer,
    }


def _measure_closed_shroud_chamfer_absence(inventory, inner_id, outer_id):
    adjacency = inventory["source_manifest"]["adjacency"]
    common_boundary_faces = sorted(
        set(adjacency.get(inner_id, ())).intersection(
            adjacency.get(outer_id, ())
        )
    )
    if len(common_boundary_faces) != 2:
        _material_failure(
            "hood_chamfer_radius_mm",
            "closed shroud does not have exactly two direct inner-to-outer material boundaries",
            {
                "inner_shroud_face_id": inner_id,
                "outer_shroud_face_id": outer_id,
                "common_boundary_source_face_ids": common_boundary_faces,
            },
        )
    treatment_faces = sorted(
        face_id
        for face_id in common_boundary_faces
        if inventory["faces_by_id"][face_id].geomType() in {"CONE", "TORUS"}
    )
    if treatment_faces:
        _material_failure(
            "hood_chamfer_radius_mm",
            "closed-shroud edge treatment is present and cannot be represented as proven zero",
            {"treatment_source_face_ids": treatment_faces},
        )
    direct_edges = set()
    for boundary_id in common_boundary_faces:
        inner_edges = _face_edge_ids(inventory, inner_id).intersection(
            _face_edge_ids(inventory, boundary_id)
        )
        outer_edges = _face_edge_ids(inventory, outer_id).intersection(
            _face_edge_ids(inventory, boundary_id)
        )
        if not inner_edges or not outer_edges:
            _material_failure(
                "hood_chamfer_radius_mm",
                "closed-shroud boundary lacks direct sharp edges to both material supports",
                {"boundary_source_face_id": boundary_id},
            )
        direct_edges.update(inner_edges)
        direct_edges.update(outer_edges)
    exhaustive = sorted(
        {inner_id, outer_id, *common_boundary_faces, *direct_edges}
    )
    return _material_record(
        0.0,
        "exhaustive_topology_absence",
        exhaustive,
        {
            "absence_proven": True,
            "transition_kind": "shroud_chamfer",
            "boundary_source_face_ids": common_boundary_faces,
            "direct_sharp_source_edge_ids": sorted(direct_edges),
            "exhaustive_source_ids": exhaustive,
        },
    )


def _mapping_frame(frame):
    keys = {
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
    missing = sorted(keys.difference(frame))
    if missing:
        raise AxisFirstPipelineError(
            "v116_axis_consensus_failed",
            "Task 3 frame lacks strict mapping fields",
            stage="measurement_bundle",
            evidence={"missing_fields": missing},
        )
    return {key: copy.deepcopy(frame[key]) for key in sorted(keys)}


def _parameter_rows_from_mapping(parameters, objective_terms, measurements):
    material = (
        measurements.get("topology", {}).get("material_measurements", {})
        if isinstance(measurements, Mapping)
        else {}
    )
    populations = measurements.get("populations", {}) if isinstance(measurements, Mapping) else {}
    term_by_parameter = {
        "blade_count": "periodicity",
        "blade_wrap_deg": "pose",
        "blade_lean_deg": "pose",
        "leading_edge_lean_deg": "pose",
        "trailing_edge_lean_deg": "pose",
        "leading_edge_sweep_mm": "pose",
        "trailing_edge_sweep_mm": "pose",
        "inlet_blade_angle_deg": "pose",
        "outlet_blade_angle_deg": "pose",
        "blade_thickness_mm": "normal_thickness",
        "leading_edge_radius_mm": "edge_curves",
        "trailing_edge_radius_mm": "edge_curves",
    }
    rows = []
    for name, value in sorted(parameters.items()):
        source_measurement = None
        measurement_confidence = None
        source_ids = []
        basis = "bounded_v112_mapping_from_authenticated_occt_evidence"
        objective_term_id = term_by_parameter.get(name, "supports")
        if name in material:
            record = material[name]
            if record.get("measurement_authority") == "occt_exact_brep_feature_measurement":
                source_measurement = record.get("value")
                measurement_confidence = 1.0
                source_ids = list(record.get("source_ids", ()))
                basis = "occt_exact_brep_feature_measurement"
                objective_term_id = "material_measurement"
        elif name == "blade_count" and isinstance(populations, Mapping):
            main = populations.get("main")
            splitter = populations.get("splitter")
            if isinstance(main, Mapping):
                source_measurement = int(main["count"]) + (
                    0 if not isinstance(splitter, Mapping) else int(splitter["count"])
                )
                measurement_confidence = 1.0
                source_ids = list(populations.get("source_ids", ()))
                basis = "authenticated_periodic_population_count"
        term = objective_terms.get(objective_term_id, {}) if isinstance(objective_terms, Mapping) else {}
        residual = (
            0.0
            if source_measurement is not None
            else copy.deepcopy(term.get("residual"))
        )
        rows.append(
            {
                "feature_id": f"parameter_values.{name}",
                "source_measurement": source_measurement,
                "mapped_v11_value": value,
                "units": "count"
                if name == "blade_count"
                else ("deg" if name.endswith("_deg") else "mm"),
                "measurement_confidence": measurement_confidence,
                "mapping_confidence": None,
                "mapping_gate_status": term.get("gate", {}).get("status"),
                "objective_term_id": objective_term_id,
                "reconstruction_residual": residual,
                "basis": basis,
                "source_ids": sorted(set(str(item) for item in source_ids)),
            }
        )
    return rows


def _population_for_mapping(population):
    if population is None:
        return None
    return {
        "count": population["count"],
        "pitch_deg": population["pitch_deg"],
        "phase_deg": population["phase_deg"],
        "streamwise_interval_s": population["streamwise_interval_s"],
        "source_ids": population["source_ids"],
    }


def _evaluated_support_profile_rz(
    profile: Mapping[str, Any], *, sample_count: int = 257
) -> list[list[float]]:
    control_points = profile.get("control_points_rz_mm", ())
    if not isinstance(control_points, Sequence) or len(control_points) < 2:
        raise AxisFirstPipelineError(
            "v116_support_profile_invalid",
            "direct active-span support lacks a valid NURBS control polygon",
            stage="exact_sections",
        )
    weights = profile.get("weights")
    if not isinstance(weights, Sequence) or len(weights) != len(control_points):
        weights = [1.0] * len(control_points)
    curve = {
        "degree": int(profile.get("degree", min(3, len(control_points) - 1))),
        "control_points": control_points,
        "weights": weights,
        "knots": profile.get("knots") or "clamped_uniform",
    }
    count = max(17, int(sample_count))
    points = [
        evaluate_nurbs_curve(curve, index / (count - 1))
        for index in range(count)
    ]
    if any(
        len(point) != 2
        or not all(math.isfinite(float(value)) for value in point)
        for point in points
    ):
        raise AxisFirstPipelineError(
            "v116_support_profile_invalid",
            "direct active-span NURBS evaluation produced invalid R-Z points",
            stage="exact_sections",
        )
    return [[float(value) for value in point] for point in points]


def _semantic_endpoint_witnesses(
    support: Mapping[str, Any],
    material: Mapping[str, Any],
    sections: Mapping[str, Any],
    *,
    source_tolerance_mm: float,
) -> dict[str, Any]:
    hub_fit = support.get("mapping_fits", {}).get("hub", {})
    eye = hub_fit.get("endpoint_roles", {}).get("eye_inlet_small_radius", {})
    eye_rz = np.asarray(eye.get("canonical_rz_mm"), dtype=float)
    if eye_rz.shape != (2,) or np.any(~np.isfinite(eye_rz)):
        raise AxisFirstPipelineError(
            "v116_hub_closure_endpoint_semantics_failed",
            "hub flowpath eye endpoint lacks a finite canonical R-Z witness",
            stage="measurement_bundle",
            evidence={"eye_endpoint": copy.deepcopy(eye)},
        )

    top_evidence = material["hub_top_cap_thickness_mm"]["evidence"]
    top_axis = np.asarray(top_evidence.get("axis_parameters_mm"), dtype=float)
    bore_evidence = material["mounting_bore_radius_mm"]["evidence"]
    bore_axis = np.asarray(bore_evidence.get("canonical_axis_limits_mm"), dtype=float)
    if top_axis.shape != (2,) or np.any(~np.isfinite(top_axis)):
        raise AxisFirstPipelineError(
            "v116_hub_closure_endpoint_semantics_failed",
            "hub material top lacks two finite axial witnesses",
            stage="measurement_bundle",
            evidence={"hub_top_cap_evidence": copy.deepcopy(top_evidence)},
        )
    if bore_axis.shape != (2,) or np.any(~np.isfinite(bore_axis)):
        raise AxisFirstPipelineError(
            "v116_hub_closure_endpoint_semantics_failed",
            "mounting bore lacks independent lower and upper material limits",
            stage="measurement_bundle",
            evidence={"mounting_bore_evidence": copy.deepcopy(bore_evidence)},
        )

    blade_witnesses = []
    direct = sections.get("direct_section_curve_network", {})
    for population, family in sorted(direct.get("populations", {}).items()):
        for station in family.get("stations", ()):
            for side_role in ("side_a", "side_b"):
                start = station.get("curves", {}).get(side_role, {}).get(
                    "start_witness", {}
                )
                xyz = np.asarray(start.get("canonical_xyz_mm"), dtype=float)
                if xyz.shape != (3,) or np.any(~np.isfinite(xyz)):
                    raise AxisFirstPipelineError(
                        "v116_direct_curve_contract_invalid",
                        "blade leading boundary lacks a canonical endpoint witness",
                        stage="measurement_bundle",
                        evidence={
                            "population": population,
                            "active_h": station.get("active_h"),
                            "side_role": side_role,
                            "start_witness": copy.deepcopy(start),
                        },
                    )
                blade_witnesses.append(
                    {
                        "population": str(population),
                        "active_h": float(station["active_h"]),
                        "side_role": side_role,
                        "canonical_xyz_mm": xyz.tolist(),
                        "source_loop_id": station.get("source_loop_id"),
                    }
                )
    if not blade_witnesses:
        raise AxisFirstPipelineError(
            "v116_direct_curve_contract_invalid",
            "direct section network has no blade leading-boundary witnesses",
            stage="measurement_bundle",
        )

    blade_z = [float(item["canonical_xyz_mm"][2]) for item in blade_witnesses]
    return {
        "contract_id": "impeller_v1_1_6_semantic_endpoint_witnesses_r16_1",
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "source_tolerance_mm": float(source_tolerance_mm),
        "hub_flowpath_eye_endpoint": {
            "canonical_rz_mm": eye_rz.tolist(),
            "source_ids": list(eye.get("source_ids", ())),
            "authority": eye.get("authority"),
        },
        "hub_material_eye_or_boss_top": {
            "canonical_z_mm": float(np.max(top_axis)),
            "canonical_axis_witnesses_mm": top_axis.tolist(),
            "source_ids": list(material["hub_top_cap_thickness_mm"].get("source_ids", ())),
            "authority": "authenticated_axis_perpendicular_material_planes",
        },
        "mounting_bore_material_limits": {
            "canonical_z_interval_mm": [float(np.min(bore_axis)), float(np.max(bore_axis))],
            "source_ids": list(material["mounting_bore_radius_mm"].get("source_ids", ())),
            "authority": "authenticated_coaxial_cylinder_end_planes",
        },
        "blade_leading_boundary": {
            "canonical_z_range_mm": [min(blade_z), max(blade_z)],
            "witnesses": blade_witnesses,
            "authority": "authenticated_step_exact_section_curve_endpoints",
        },
        "universal_common_z_plane_forbidden": True,
    }


def _support_profile_sample_frames(
    source_to_canonical,
    profile,
    paired_footprint_points_xyz_mm,
    retained_points_xyz_mm,
):
    """Resolve support-normal height separately from in-plane root width."""

    matrix = np.asarray(source_to_canonical, dtype=float)
    inverse_rotation = np.linalg.inv(matrix[:3, :3])
    if isinstance(profile, Mapping):
        control_points = profile.get("control_points_rz_mm", ())
        if "degree" not in profile and "knots" not in profile:
            profile_points = np.asarray(
                support_recovery.evaluate_profile_rz(
                    control_points, np.linspace(0.0, 1.0, 257)
                ),
                dtype=float,
            )
        else:
            weights = profile.get("weights")
            if not isinstance(weights, Sequence) or len(weights) != len(control_points):
                weights = [1.0] * len(control_points)
            knots = profile.get("knots")
            if not knots:
                knots = "clamped_uniform"
            curve = {
                "degree": int(profile.get("degree", min(3, len(control_points) - 1))),
                "control_points": control_points,
                "weights": weights,
                "knots": knots,
            }
            profile_points = np.asarray(
                [evaluate_nurbs_curve(curve, index / 256.0) for index in range(257)],
                dtype=float,
            )
    else:
        profile_points = np.asarray(profile, dtype=float)
    if (
        profile_points.ndim != 2
        or profile_points.shape[1] != 2
        or len(profile_points) < 2
    ):
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment support profile cannot provide local normals",
            stage="exact_sections",
        )
    segments = np.diff(profile_points, axis=0)
    lengths_sq = np.sum(segments * segments, axis=1)
    lengths = np.sqrt(lengths_sq)
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    total_length = max(float(cumulative[-1]), 1.0e-18)
    normals = []
    streamwise_parameters = []
    for source_point, retained_point in zip(
        paired_footprint_points_xyz_mm, retained_points_xyz_mm
    ):
        canonical_point = _transform_point(source_point, matrix)
        canonical_retained = _transform_point(retained_point, matrix)
        radius = math.hypot(float(canonical_point[0]), float(canonical_point[1]))
        rz = np.asarray([radius, float(canonical_point[2])], dtype=float)
        fractions = np.divide(
            np.sum((rz - profile_points[:-1]) * segments, axis=1),
            lengths_sq,
            out=np.zeros_like(lengths_sq),
            where=lengths_sq > 1.0e-18,
        )
        fractions = np.clip(fractions, 0.0, 1.0)
        projections = profile_points[:-1] + fractions[:, None] * segments
        segment_index = int(np.argmin(np.linalg.norm(projections - rz, axis=1)))
        tangent_rz = segments[segment_index].copy()
        tangent_rz /= max(float(np.linalg.norm(tangent_rz)), 1.0e-18)
        normal_rz = np.asarray([-tangent_rz[1], tangent_rz[0]], dtype=float)
        radial = (
            np.asarray(
                [canonical_point[0] / radius, canonical_point[1] / radius],
                dtype=float,
            )
            if radius > 1.0e-12
            else np.asarray([1.0, 0.0], dtype=float)
        )
        canonical_normal = np.asarray(
            [
                normal_rz[0] * radial[0],
                normal_rz[0] * radial[1],
                normal_rz[1],
            ],
            dtype=float,
        )
        if float(np.dot(canonical_retained - canonical_point, canonical_normal)) < 0.0:
            canonical_normal = -canonical_normal
        source_normal = inverse_rotation @ canonical_normal
        source_normal /= max(float(np.linalg.norm(source_normal)), 1.0e-18)
        normals.append([float(value) for value in source_normal])
        streamwise_parameters.append(
            float(
                (cumulative[segment_index] + fractions[segment_index] * lengths[segment_index])
                / total_length
            )
        )
    return normals, streamwise_parameters


def _attachment_for_mapping(record):
    source_ids = sorted(
        set(record.source_face_ids)
        | set(record.footprint_source_edge_ids)
        | set(record.retained_source_edge_ids)
        | set(record.span_direction_source_ids)
    )
    return {
        "lift_samples_mm": [float(value) for value in record.lift_samples_mm],
        "width_samples_mm": [float(value) for value in record.width_samples_mm],
        "streamwise_samples_s": [
            float(value) for value in record.streamwise_samples_s
        ],
        "source_ids": source_ids,
        "source_measurement": bool(record.source_measurement),
        "promotable": bool(record.promotable),
        "material_side": int(record.material_side),
    }


def _tip_cap_face_ids(inventory, semantics, *, hub_face_ids):
    """Find each open tip cap opposite the authenticated root boundary.

    The cap is the component face reached across the side-face boundary edge
    farthest in the exact wire graph from the hub-contact boundary.  This is
    invariant to rigid pose and does not use face centers or axial extrema.
    """
    result = {}
    adjacency = inventory["source_manifest"]["adjacency"]
    for population in semantics["periodic_population_recovery"]["populations"]:
        for instance in population["instances"]:
            component_ids = set(instance["source_face_ids"]) - set(
                hub_face_ids
            )
            side_ids = set(
                instance["component_completeness"]["blade_side_face_ids"]
            )
            if len(side_ids) != 2:
                raise AxisFirstPipelineError(
                    "v116_tip_reference_inference_failed",
                    "open component does not contain exactly two authenticated blade sides",
                    stage="support_recovery",
                    evidence={"instance_id": instance["instance_id"]},
                )
            root_faces = {
                face_id
                for face_id in component_ids
                if set(hub_face_ids).intersection(adjacency.get(face_id, ()))
            }
            if not root_faces:
                raise AxisFirstPipelineError(
                    "v116_tip_reference_inference_failed",
                    "open component has no exact hub-contact face set",
                    stage="support_recovery",
                    evidence={
                        "instance_id": instance["instance_id"],
                        "hub_face_ids": sorted(hub_face_ids),
                    },
                )
            shared_side_caps = {
                face_id
                for face_id in component_ids - side_ids
                if all(
                    face_id in adjacency.get(side_id, ())
                    for side_id in side_ids
                )
            }
            if len(shared_side_caps) == 1:
                result[str(instance["instance_id"])] = shared_side_caps.pop()
                continue
            if len(shared_side_caps) >= 3:
                eccentricities = {}
                for start in shared_side_caps:
                    path_distances = {start: 0}
                    path_queue = [start]
                    while path_queue:
                        current = path_queue.pop(0)
                        for neighbor in sorted(
                            shared_side_caps.intersection(
                                adjacency.get(current, ())
                            )
                        ):
                            if neighbor not in path_distances:
                                path_distances[neighbor] = (
                                    path_distances[current] + 1
                                )
                                path_queue.append(neighbor)
                    if set(path_distances) == shared_side_caps:
                        eccentricities[start] = max(path_distances.values())
                if eccentricities:
                    minimum_eccentricity = min(eccentricities.values())
                    centers = [
                        face_id
                        for face_id, value in eccentricities.items()
                        if value == minimum_eccentricity
                    ]
                    if len(centers) == 1:
                        result[str(instance["instance_id"])] = centers[0]
                        continue
            distances = {face_id: 0 for face_id in root_faces}
            queue = sorted(root_faces)
            while queue:
                current = queue.pop(0)
                for neighbor in sorted(
                    component_ids.intersection(adjacency.get(current, ()))
                ):
                    if neighbor not in distances:
                        distances[neighbor] = distances[current] + 1
                        queue.append(neighbor)
            if set(distances) != component_ids:
                raise AxisFirstPipelineError(
                    "v116_tip_reference_inference_failed",
                    "open component face graph is disconnected from its hub boundary",
                    stage="support_recovery",
                    evidence={
                        "instance_id": instance["instance_id"],
                        "unreached_source_face_ids": sorted(
                            component_ids.difference(distances)
                        ),
                    },
                )
            farthest = max(distances.values())
            candidates = {
                face_id
                for face_id, distance in distances.items()
                if distance == farthest and face_id not in side_ids
            }
            selected = _select_opposite_tip_cap(
                inventory, candidates, side_ids
            )
            if selected is not None:
                result[str(instance["instance_id"])] = selected
                continue
            if len(candidates) != 1:
                raise AxisFirstPipelineError(
                    "v116_tip_reference_inference_failed",
                    "exact component adjacency does not identify one opposite open tip cap",
                    stage="support_recovery",
                    evidence={
                        "instance_id": instance["instance_id"],
                        "hub_face_ids": sorted(hub_face_ids),
                        "root_component_face_ids": sorted(root_faces),
                        "face_graph_distance_from_root": dict(sorted(distances.items())),
                        "opposite_face_candidates": sorted(candidates),
                    },
                )
            result[str(instance["instance_id"])] = candidates.pop()
    return result


def _measure_support_bound_hub_material(
    inventory, frame, bore, support, axis, tolerance
):
    hub_fit = support.get("mapping_fits", {}).get("hub")
    if not isinstance(hub_fit, Mapping):
        _material_failure(
            "hub_wall_thickness_mm",
            "support-bound material reduction requires an authenticated hub fit",
            {"hub_support_fit": hub_fit},
        )
    hub_controls = np.asarray(hub_fit["control_points_rz_mm"], dtype=float)
    if hub_controls.shape != (6, 2) or not np.all(np.isfinite(hub_controls)):
        _material_failure(
            "hub_wall_thickness_mm",
            "authenticated hub support fit cannot define the reduced material envelope",
            {"hub_support_fit": hub_fit},
        )
    minimum_hub_radius = float(np.min(hub_controls[:, 0]))
    maximum_hub_radius = float(np.max(hub_controls[:, 0]))
    endpoint_roles = hub_fit.get("endpoint_roles")
    if not isinstance(endpoint_roles, Mapping):
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound material reduction requires named hub endpoints",
            {"endpoint_roles": endpoint_roles},
        )
    eye_role = endpoint_roles.get("eye_inlet_small_radius")
    backplate_role = endpoint_roles.get("backplate_exit_large_radius")
    if not isinstance(eye_role, Mapping) or not isinstance(backplate_role, Mapping):
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound material reduction lacks eye/backplate endpoint roles",
            {"endpoint_roles": endpoint_roles},
        )
    eye_endpoint = np.asarray(eye_role.get("canonical_rz_mm"), dtype=float)
    backplate_endpoint = np.asarray(
        backplate_role.get("canonical_rz_mm"), dtype=float
    )
    endpoint_authority_valid = (
        eye_endpoint.shape == (2,)
        and backplate_endpoint.shape == (2,)
        and np.all(np.isfinite(eye_endpoint))
        and np.all(np.isfinite(backplate_endpoint))
        and eye_role.get("authority") == "authenticated_support_fit_endpoint"
        and backplate_role.get("authority")
        == "authenticated_support_fit_endpoint"
        and int(eye_role.get("control_point_index", -1)) == 0
        and int(backplate_role.get("control_point_index", -1))
        == len(hub_controls) - 1
        and np.allclose(eye_endpoint, hub_controls[0], atol=1.0e-9, rtol=0.0)
        and np.allclose(
            backplate_endpoint, hub_controls[-1], atol=1.0e-9, rtol=0.0
        )
        and eye_endpoint[0] < backplate_endpoint[0]
        and eye_endpoint[1] > backplate_endpoint[1]
    )
    if not endpoint_authority_valid:
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound hub endpoint authority is inconsistent with eye-positive Z",
            {
                "endpoint_roles": endpoint_roles,
                "control_endpoints_rz_mm": [
                    hub_controls[0].tolist(),
                    hub_controls[-1].tolist(),
                ],
            },
        )
    hub_terminal_axis = float(backplate_endpoint[1])
    wall = minimum_hub_radius - float(bore["radius_mm"])
    if wall <= tolerance:
        _material_failure(
            "hub_wall_thickness_mm",
            "axis-consensus bore leaves no positive radial material to the hub support",
            {
                "bore_radius_mm": bore["radius_mm"],
                "minimum_hub_support_radius_mm": minimum_hub_radius,
            },
        )

    hub_source_face_ids = sorted(
        set(hub_fit["source_ids"]).intersection(inventory["faces_by_id"])
    )
    if not hub_source_face_ids:
        _material_failure(
            "hub_bottom_thickness_mm",
            "authenticated hub fit does not retain a source-face material component",
            {"hub_support_source_ids": list(hub_fit["source_ids"])},
        )
    material_component = _connected_nonperiodic_face_component(
        inventory, hub_source_face_ids
    )
    planes = [
        record
        for record in _axis_perpendicular_material_planes(inventory, axis)
        if record["face_id"] in material_component
        and record["centroid_axis_offset_mm"] <= tolerance
        and record["axis_parameter_mm"] < hub_terminal_axis - tolerance
        and record["maximum_radius_mm"] > float(bore["radius_mm"]) + tolerance
    ]
    if len(planes) < 2:
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound hub reduction lacks two authenticated back-material planes",
            {
                "hub_terminal_axis_parameter_mm": hub_terminal_axis,
                "material_plane_candidates": planes,
            },
        )
    top_candidates = [
        item
        for item in planes
        if item["maximum_radius_mm"] >= maximum_hub_radius - tolerance
    ]
    bottom_candidates = [
        item
        for item in planes
        if item["minimum_radius_mm"] <= minimum_hub_radius + tolerance
    ]
    if not top_candidates or not bottom_candidates:
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound stepped material lacks authenticated outer-top or inner-bottom terminal planes",
            {
                "material_plane_candidates": planes,
                "outer_top_candidates": top_candidates,
                "inner_bottom_candidates": bottom_candidates,
                "minimum_hub_support_radius_mm": minimum_hub_radius,
                "maximum_hub_support_radius_mm": maximum_hub_radius,
            },
        )
    first = max(top_candidates, key=lambda item: item["axis_parameter_mm"])
    last = min(bottom_candidates, key=lambda item: item["axis_parameter_mm"])
    top = float(hub_terminal_axis - first["axis_parameter_mm"])
    bottom = float(first["axis_parameter_mm"] - last["axis_parameter_mm"])
    if bottom <= tolerance:
        _material_failure(
            "hub_bottom_thickness_mm",
            "support-bound back-material planes do not define positive axial thickness",
            {"material_plane_candidates": planes},
        )
    hub_source_ids = list(hub_fit["source_ids"])
    return (
        wall,
        bottom,
        top,
        {
            "method": "support_bound_axisymmetric_material_envelope",
            "axis_semantics": "large_radius_backplate_to_small_radius_eye_positive_z",
            "bore_radius_mm": float(bore["radius_mm"]),
            "minimum_hub_support_radius_mm": minimum_hub_radius,
            "maximum_hub_support_radius_mm": maximum_hub_radius,
            "hub_terminal_axis_parameter_mm": hub_terminal_axis,
            "top_material_plane": first,
            "bottom_material_plane": last,
            "intermediate_material_planes": [
                item
                for item in sorted(
                    planes,
                    key=lambda record: record["axis_parameter_mm"],
                    reverse=True,
                )
                if item["face_id"] not in {first["face_id"], last["face_id"]}
            ],
            "wall_source_ids": sorted(set(bore["source_ids"]) | set(hub_source_ids)),
            "top_source_face_ids": sorted(
                set(hub_source_ids) | {first["face_id"]}
            ),
            "bottom_source_face_ids": [first["face_id"], last["face_id"]],
            "top_axis_parameters_mm": [hub_terminal_axis, first["axis_parameter_mm"]],
            "bottom_axis_parameters_mm": [
                first["axis_parameter_mm"],
                last["axis_parameter_mm"],
            ],
            "hub_material_component_face_ids": sorted(material_component),
            "radial_coverage_gate": {
                "outer_top_minimum_radius_mm": maximum_hub_radius - tolerance,
                "inner_bottom_maximum_radius_mm": minimum_hub_radius + tolerance,
            },
        },
    )


def _connected_nonperiodic_face_component(inventory, start_face_ids):
    face_ids = set(inventory["faces_by_id"])
    periodic_face_ids = set(inventory["instance_by_face"])
    adjacency = inventory["source_manifest"]["adjacency"]
    visited = set(start_face_ids).intersection(face_ids).difference(periodic_face_ids)
    pending = sorted(visited)
    while pending:
        current = pending.pop(0)
        for neighbor in sorted(adjacency.get(current, ())):
            if (
                neighbor in face_ids
                and neighbor not in periodic_face_ids
                and neighbor not in visited
            ):
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def _measure_coaxial_bore_opening_treatment(
    inventory,
    bore,
    treatment_face_ids,
    material_distance_evidence,
    axis,
    tolerance,
):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "hub_chamfer_radius_mm",
            "OCP analytic measurement adaptors are unavailable",
            {"exception_type": type(exc).__name__},
        )
    origin, direction = axis
    exterior_parameters = {
        float(material_distance_evidence["top_material_plane"]["axis_parameter_mm"]),
        float(material_distance_evidence["bottom_material_plane"]["axis_parameter_mm"]),
    }
    measurements = []
    for face_id in sorted(treatment_face_ids):
        face = inventory["faces_by_id"][face_id]
        if face.geomType() != "CONE":
            continue
        cone = BRepAdaptor_Surface(face.wrapped).Cone()
        cone_axis = cone.Axis()
        cone_direction = np.asarray(cone_axis.Direction().Coord(), dtype=float)
        cone_origin = np.asarray(cone_axis.Location().Coord(), dtype=float)
        if (
            abs(float(np.dot(cone_direction, direction)))
            < math.cos(math.radians(0.05))
            or float(np.linalg.norm(np.cross(cone_origin - origin, direction)))
            > tolerance
        ):
            continue
        circles = []
        for edge_id in sorted(_face_edge_ids(inventory, face_id)):
            edge = inventory["edges_by_id"][edge_id]
            if edge.geomType() != "CIRCLE":
                continue
            circle = BRepAdaptor_Curve(edge.wrapped).Circle()
            center = np.asarray(circle.Location().Coord(), dtype=float)
            circles.append(
                {
                    "edge_id": edge_id,
                    "radius_mm": float(circle.Radius()),
                    "axis_parameter_mm": float(np.dot(center - origin, direction)),
                }
            )
        bore_circles = [
            item
            for item in circles
            if abs(item["radius_mm"] - float(bore["radius_mm"])) <= tolerance
        ]
        other_circles = [
            item
            for item in circles
            if abs(item["radius_mm"] - float(bore["radius_mm"])) > tolerance
        ]
        for bore_circle in bore_circles:
            for other in other_circles:
                exterior = next(
                    (
                        value
                        for value in exterior_parameters
                        if abs(other["axis_parameter_mm"] - value) <= tolerance
                    ),
                    None,
                )
                if exterior is None:
                    continue
                measurements.append(
                    {
                        "value_mm": abs(
                            other["radius_mm"] - bore_circle["radius_mm"]
                        ),
                        "face_id": face_id,
                        "source_edge_ids": sorted(
                            {bore_circle["edge_id"], other["edge_id"]}
                        ),
                        "bore_axis_parameter_mm": bore_circle[
                            "axis_parameter_mm"
                        ],
                        "exterior_axis_parameter_mm": exterior,
                    }
                )
    if not measurements:
        _material_failure(
            "hub_chamfer_radius_mm",
            "conical bore treatment is not bound to an authenticated exterior material plane",
            {"treatment_source_face_ids": sorted(treatment_face_ids)},
        )
    values = [item["value_mm"] for item in measurements]
    if max(values) - min(values) > tolerance:
        _material_failure(
            "hub_chamfer_radius_mm",
            "exterior bore treatments do not reduce to one scalar radial width",
            {"measurements": measurements},
        )
    value = float(np.mean(values))
    source_ids = set(bore["source_ids"])
    for item in measurements:
        source_ids.add(item["face_id"])
        source_ids.update(item["source_edge_ids"])
    return _material_record(
        value,
        "coaxial_conical_bore_opening_radial_width",
        sorted(source_ids),
        {
            "measurements": measurements,
            "scalar_reduction": "equal_exterior_opening_radial_widths",
        },
    )


def _axis_perpendicular_material_planes(inventory, axis):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        _material_failure(
            "hub_bottom_thickness_mm",
            "OCP analytic measurement adaptors are unavailable",
            {"exception_type": type(exc).__name__},
        )
    origin, direction = axis
    result = []
    for face_id, face in inventory["faces_by_id"].items():
        if face_id in inventory["instance_by_face"] or face.geomType() != "PLANE":
            continue
        plane = BRepAdaptor_Surface(face.wrapped).Plane()
        normal = np.asarray(plane.Axis().Direction().Coord(), dtype=float)
        if abs(float(np.dot(normal, direction))) < math.cos(math.radians(0.05)):
            continue
        location = np.asarray(plane.Location().Coord(), dtype=float)
        centroid = np.asarray(face.Center().toTuple(), dtype=float)
        centroid_offset = centroid - origin
        centroid_radial = centroid_offset - np.dot(centroid_offset, direction) * direction
        radii = []
        for vertex in face.Vertices():
            point = np.asarray(vertex.toTuple(), dtype=float)
            offset = point - origin
            radial = offset - np.dot(offset, direction) * direction
            radii.append(float(np.linalg.norm(radial)))
        if not radii:
            continue
        result.append(
            {
                "face_id": face_id,
                "axis_parameter_mm": float(np.dot(location - origin, direction)),
                "minimum_radius_mm": min(radii),
                "maximum_radius_mm": max(radii),
                "centroid_axis_offset_mm": float(np.linalg.norm(centroid_radial)),
                "area_mm2": float(inventory["records_by_id"][face_id]["area_mm2"]),
                "source_edge_ids": sorted(_face_edge_ids(inventory, face_id)),
            }
        )
    return result


def _select_opposite_tip_cap(inventory, candidates, side_ids):
    """Select a multi-patch tip's principal cap by balanced side contact."""

    sides = sorted(side_ids)
    if len(sides) != 2:
        return None
    scored = []
    for face_id in sorted(candidates):
        contacts = [
            _shared_contact_length(inventory, face_id, {side_id})
            for side_id in sides
        ]
        if all(length > 0.0 for length in contacts):
            scored.append(
                {
                    "face_id": face_id,
                    "minimum_contact_mm": min(contacts),
                    "total_contact_mm": sum(contacts),
                }
            )
    if not scored:
        return None
    best_minimum = max(item["minimum_contact_mm"] for item in scored)
    minimum_winners = [
        item
        for item in scored
        if math.isclose(
            item["minimum_contact_mm"], best_minimum, rel_tol=1.0e-12, abs_tol=1.0e-9
        )
    ]
    best_total = max(item["total_contact_mm"] for item in minimum_winners)
    winners = [
        item
        for item in minimum_winners
        if math.isclose(
            item["total_contact_mm"], best_total, rel_tol=1.0e-12, abs_tol=1.0e-9
        )
    ]
    return winners[0]["face_id"] if len(winners) == 1 else None


def _decompose_measured_section_loop(loop, fit_tolerance):
    decomposition = None
    # Use the first source-tolerance fit in increasing complexity order.  Fit
    # error is not monotone in control count: dense uniform-knot fits can
    # oscillate between exact samples, while an intermediate budget remains
    # both smoother and more accurate.  The final budget may equal the 129
    # exact-curve display samples for a strongly curved terminal station, but
    # the direct path never activates the degree-one polyline fallback.
    for maximum_control_count in (25, 49, 65, 81, 97, 129):
        if (
            getattr(loop, "source_kind", "")
            == "occt_exact_authenticated_open_side_pair"
        ):
            decomposition = section_recovery.decompose_authenticated_open_side_pair(
                loop,
                maximum_control_count=maximum_control_count,
            )
        else:
            decomposition = section_recovery.decompose_section_loop(
                loop,
                maximum_control_count=maximum_control_count,
            )
        if all(
            segment.fit.residual_max_mm <= fit_tolerance + 1.0e-12
            for segment in decomposition.segments
        ):
            return decomposition
    return decomposition


def _representative_face_roles(
    inventory,
    instance,
    matrix,
    *,
    topology,
    hub_profile_rz_mm,
):
    """Authenticate sides; defer LE/TE labels to the exact local section loop.

    Streamwise closure faces can be split by hub booleans and edge rounds, so a
    face-level LE/TE guess is not authoritative.  Task 7 assigns those roles
    after exact section-edge ordering in local meridional S-Q with material
    orientation.  Supplying only the two authenticated side faces deliberately
    activates that source-preserving path.
    """
    completeness = instance["component_completeness"]
    side_ids = list(completeness["blade_side_face_ids"])
    if len(side_ids) != 2:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "representative component does not contain two blade sides",
            stage="exact_sections",
            evidence={"component": instance},
    )
    roles = {side_ids[0]: "side_a", side_ids[1]: "side_b"}
    hub_support_ids = set(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
    component_ids = set(instance["source_face_ids"]) - hub_support_ids
    adjacent_support_ids = {
        neighbor
        for face_id in component_ids
        for neighbor in inventory["source_manifest"]["adjacency"].get(face_id, ())
    }.intersection(hub_support_ids)
    if not adjacent_support_ids:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "representative component lacks an exact hub-support adjacency",
            stage="exact_sections",
            evidence={
                "instance_id": instance["instance_id"],
                "side_face_ids": sorted(side_ids),
                "hub_support_face_ids": sorted(hub_support_ids),
            },
        )
    return roles


def _face_edge_ids(inventory, face_id):
    return set(inventory["face_edge_ids"][face_id])


def _boundary_edge_distances(inventory, boundary_ids, seed_ids):
    """Return exact wire-graph distances from a non-empty boundary seed."""
    boundary = set(boundary_ids)
    seeds = boundary.intersection(seed_ids)
    if not seeds:
        return {}
    neighbors = {edge_id: set() for edge_id in boundary}
    for first_id in boundary:
        first = inventory["edges_by_id"][first_id]
        for second_id in boundary:
            if first_id >= second_id:
                continue
            second = inventory["edges_by_id"][second_id]
            if any(
                first_vertex.wrapped.IsSame(second_vertex.wrapped)
                for first_vertex in first.Vertices()
                for second_vertex in second.Vertices()
            ):
                neighbors[first_id].add(second_id)
                neighbors[second_id].add(first_id)
    distances = {edge_id: 0 for edge_id in seeds}
    queue = sorted(seeds)
    while queue:
        current = queue.pop(0)
        for neighbor in sorted(neighbors[current]):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances if set(distances) == boundary else {}


def _closure_meridional_s(
    inventory, closure_face_id, side_face_ids, matrix, profile_rz_mm
):
    """Order a closure by exact shared-boundary points projected on hub arc S."""
    shared_ids = sorted(
        edge_id
        for edge_id in _face_edge_ids(inventory, closure_face_id)
        if any(
            edge_id in _face_edge_ids(inventory, side_id)
            for side_id in side_face_ids
        )
    )
    if not shared_ids:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "closure face lacks exact shared edges with authenticated blade sides",
            stage="exact_sections",
            evidence={"closure_face_id": closure_face_id},
        )
    profile = np.asarray(profile_rz_mm, dtype=float)
    segments = np.diff(profile, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    if len(profile) < 2 or np.any(lengths <= 1.0e-12):
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "authenticated hub support has no usable meridional arc",
            stage="exact_sections",
            evidence={"closure_face_id": closure_face_id},
        )
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    values = []
    for edge_id in shared_ids:
        for vertex in inventory["edges_by_id"][edge_id].Vertices():
            point = _transform_point(vertex.toTuple(), matrix)
            rz = np.asarray([math.hypot(point[0], point[1]), point[2]], dtype=float)
            fractions = np.clip(
                np.sum((rz - profile[:-1]) * segments, axis=1) / (lengths**2),
                0.0,
                1.0,
            )
            candidates = profile[:-1] + fractions[:, None] * segments
            index = int(np.argmin(np.linalg.norm(candidates - rz, axis=1)))
            values.append(float(cumulative[index] + fractions[index] * lengths[index]))
    if not values:
        raise AxisFirstPipelineError(
            "v116_representative_blade_selection_failed",
            "closure shared boundary has no exact source vertices",
            stage="exact_sections",
            evidence={
                "closure_face_id": closure_face_id,
                "shared_source_edge_ids": shared_ids,
            },
        )
    return float(np.median(values))


def _decomposition_summary(decomposition):
    return {
        "landmark_method": decomposition.landmark_method,
        "segments": {
            segment.name: {
                "source_face_ids": list(segment.source_face_ids),
                "source_edge_ids": list(segment.source_edge_ids),
                "fit_residual_rms_mm": float(segment.fit.residual_rms_mm),
                "fit_residual_max_mm": float(segment.fit.residual_max_mm),
            }
            for segment in decomposition.segments
        },
    }


def _cap_shared_side_edge_groups(inventory, cap_id, side_face_ids):
    cap_edges = _face_edge_ids(inventory, cap_id)
    groups = []
    missing_side_ids = []
    for adjacent_id in sorted(side_face_ids - {cap_id}):
        shared = tuple(
            sorted(cap_edges.intersection(_face_edge_ids(inventory, adjacent_id)))
        )
        if shared:
            groups.append((adjacent_id, shared))
        else:
            missing_side_ids.append(adjacent_id)
    if not groups or missing_side_ids:
        raise AxisFirstPipelineError(
            "v116_tip_reference_inference_failed",
            "open tip cap does not own an exact shared edge chain for every "
            "authenticated blade side",
            stage="support_recovery",
            evidence={
                "tip_cap_face_id": cap_id,
                "authenticated_side_face_ids": sorted(side_face_ids),
                "missing_side_face_ids": missing_side_ids,
            },
        )
    return groups


def _attachment_face_for_support(inventory, instance, support_id):
    adjacency = inventory["source_manifest"]["adjacency"]
    candidates = [
        face_id
        for face_id in instance["source_face_ids"]
        if support_id in adjacency.get(face_id, ())
    ]
    if not candidates:
        raise AxisFirstPipelineError(
            "v116_shroud_topology_ambiguous",
            "periodic instance has no exact face adjacency to inner shroud",
            stage="support_recovery",
            evidence={"instance_id": instance["instance_id"], "support_face_id": support_id},
        )
    return min(
        candidates,
        key=lambda face_id: (
            inventory["records_by_id"][face_id]["area_mm2"], face_id
        ),
    )


def _shared_edge_between_ids(inventory, first_id, second_id):
    shared = sorted(
        _face_edge_ids(inventory, first_id).intersection(
            _face_edge_ids(inventory, second_id)
        )
    )
    if shared:
        edge_id = shared[0]
        return edge_id, inventory["edges_by_id"][edge_id]
    raise AxisFirstPipelineError(
        "v116_shroud_topology_ambiguous",
        "declared adjacent faces do not share an OCCT edge",
        stage="support_recovery",
        evidence={"first_face_id": first_id, "second_face_id": second_id},
    )


def _component_edge_ids(inventory, component_ids):
    return set().union(
        *(set(inventory["face_edge_ids"][face_id]) for face_id in component_ids)
    )


def _shared_component_support_edges(inventory, component_ids, support_id):
    return sorted(
        _component_edge_ids(inventory, component_ids).intersection(
            inventory["face_edge_ids"][support_id]
        )
    )


def _attachment_adjacency_chains(
    inventory, component_edges, footprint_ids, support_ids
):
    """Recover footprint-opposite and connector chains from exact face wires."""
    footprint = set(footprint_ids)
    supports = set(support_ids)
    vertices = {
        edge_id: {
            tuple(round(float(value), 12) for value in vertex.toTuple())
            for vertex in inventory["edges_by_id"][edge_id].Vertices()
        }
        for edge_id in component_edges
    }
    footprint_vertices = set().union(*(vertices[edge_id] for edge_id in footprint))
    attachment_faces = {
        face_id
        for edge_id in footprint
        for face_id in _edge_adjacent_face_ids(inventory, edge_id)
        if face_id not in supports
    }
    attachment_edges = set().union(
        *(set(inventory["face_edge_ids"][face_id]) for face_id in attachment_faces)
    ).intersection(component_edges)
    # These short connector edges are the leading/trailing termination
    # boundaries. Local span direction is measured from paired footprint and
    # retained boundaries, so its source chain must remain disjoint from them.
    termination_connectors = {
        edge_id
        for edge_id in attachment_edges - footprint
        if vertices[edge_id] & footprint_vertices
    }
    retained = attachment_edges - footprint - termination_connectors
    span_direction_sources = footprint | retained
    if termination_connectors.intersection(span_direction_sources):
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "termination and span-direction source chains overlap",
            stage="exact_sections",
        )
    return (
        sorted(retained),
        sorted(termination_connectors),
        sorted(span_direction_sources),
    )


def _unsupported_source_feature_audit(
    section_evidence: Mapping[str, Any],
    measurements: Mapping[str, Any],
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    rejection_counts: dict[str, int] = {}
    records = list(section_evidence.get("section_loop_records", ()))
    for record in records:
        exact = record.get("exact_section", {})
        for loop in exact.get("additional_loops", ()):
            features.append(
                {
                    "feature_id": str(
                        loop.get(
                            "loop_id",
                            f"unmapped-section-loop-{len(features):03d}",
                        )
                    ),
                    "feature_kind": "additional_exact_section_loop",
                    "population": record.get("population"),
                    "support_span_h": record.get("support_span_h"),
                    "source_face_ids": sorted(
                        {str(value) for value in loop.get("source_face_ids", ())}
                    ),
                    "source_edge_ids": sorted(
                        {str(value) for value in loop.get("source_edge_ids", ())}
                    ),
                    "mapping_status": "UNSUPPORTED_PENDING_REGIONAL_DEVIATION",
                }
            )
        for rejected in exact.get("rejected_edges", ()):
            reason = str(rejected.get("reason", "unknown"))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
    features.sort(key=lambda item: item["feature_id"])
    return {
        "status": (
            "DETECTED_PENDING_REGIONAL_DEVIATION"
            if features
            else "PARTIAL_REPRESENTATIVE_SECTION_AUDIT"
        ),
        "complete": False,
        "completion_stage": "regional_deviation",
        "coverage": "representative_population_exact_section_loops",
        "reviewed_station_count": len(records),
        "source_inventory_face_count": len(
            measurements.get("provenance", {}).get("source_entity_ids", ())
        ),
        "rejected_section_edge_counts_by_reason": dict(
            sorted(rejection_counts.items())
        ),
        "features": features,
    }


def _attachment_footprint_candidates(
    inventory, retained_ids, footprint_ids, support_ids
):
    supports = set(support_ids)
    footprint = tuple(sorted(set(footprint_ids)))
    attachment_faces = {
        face_id
        for edge_id in footprint
        for face_id in _edge_adjacent_face_ids(inventory, edge_id)
        if face_id not in supports
    }
    result = {}
    for retained_id in retained_ids:
        shared_faces = set(
            _edge_adjacent_face_ids(inventory, retained_id)
        ).intersection(attachment_faces)
        candidates = tuple(
            edge_id
            for edge_id in footprint
            if shared_faces.intersection(
                _edge_adjacent_face_ids(inventory, edge_id)
            )
        )
        if not candidates:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "retained attachment edge has no same-patch footprint boundary",
                stage="exact_sections",
                evidence={
                    "retained_source_edge_id": retained_id,
                    "attachment_source_face_ids": sorted(shared_faces),
                    "footprint_source_edge_ids": list(footprint),
                },
            )
        result[str(retained_id)] = candidates
    return result


def _edge_adjacent_face_ids(inventory, edge_id):
    return list(inventory["edge_face_ids"][edge_id])


def _boundary_vertices(inventory, edge_ids, *, minimum=3):
    points = []
    for edge_id in edge_ids:
        for vertex in inventory["edges_by_id"][edge_id].Vertices():
            point = tuple(float(value) for value in vertex.toTuple())
            if not any(np.linalg.norm(np.asarray(point) - np.asarray(other)) <= 1.0e-9 for other in points):
                points.append(point)
    if len(points) < minimum:
        for edge_id in edge_ids:
            for point in _sample_exact_edge_points(inventory["edges_by_id"][edge_id], minimum):
                if not any(
                    np.linalg.norm(np.asarray(point) - np.asarray(other)) <= 1.0e-9
                    for other in points
                ):
                    points.append(point)
    if len(points) < minimum:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            f"attachment boundary has fewer than {minimum} exact source vertices",
            stage="exact_sections",
            evidence={"source_edge_ids": list(edge_ids)},
        )
    center = np.mean(np.asarray(points), axis=0)
    return sorted(points, key=lambda point: math.atan2(point[1] - center[1], point[0] - center[0]))


def _sample_exact_edge_points(edge, count):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.TopoDS import TopoDS
    except ImportError as exc:  # pragma: no cover - covered by OCCT fixture tests when available.
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "OCCT edge sampling is required for single-edge attachment boundaries",
            stage="exact_sections",
            evidence={"exception_type": type(exc).__name__},
        ) from exc
    adaptor = BRepAdaptor_Curve(TopoDS.Edge_s(edge.wrapped))
    parameters = np.linspace(
        float(adaptor.FirstParameter()),
        float(adaptor.LastParameter()),
        max(2, int(count)),
    )
    result = []
    for parameter in parameters:
        point = adaptor.Value(float(parameter))
        result.append((float(point.X()), float(point.Y()), float(point.Z())))
    return result


def _boundary_interior_points(
    inventory, edge_ids, *, sample_count, with_edge_ids=False
):
    """Sample the active interior of exact retained curves, excluding blend terminations."""

    count = max(3, int(sample_count))
    points = []
    point_edge_ids = []
    for edge_id in edge_ids:
        edge = inventory["edges_by_id"][edge_id]
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.TopoDS import TopoDS
        except ImportError as exc:  # pragma: no cover - OCCT fixture tests cover this path.
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "OCCT retained-edge sampling is required for attachment lift",
                stage="exact_sections",
                evidence={"exception_type": type(exc).__name__},
            ) from exc
        adaptor = BRepAdaptor_Curve(TopoDS.Edge_s(edge.wrapped))
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        if not math.isfinite(first) or not math.isfinite(last) or last <= first:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "retained attachment edge has an invalid exact parameter domain",
                stage="exact_sections",
                evidence={"source_edge_id": edge_id, "first": first, "last": last},
            )
        for fraction in np.linspace(0.1, 0.9, count):
            point = adaptor.Value(first + float(fraction) * (last - first))
            candidate = (float(point.X()), float(point.Y()), float(point.Z()))
            if not any(
                np.linalg.norm(np.asarray(candidate) - np.asarray(other)) <= 1.0e-9
                for other in points
            ):
                points.append(candidate)
                point_edge_ids.append(edge_id)
    if len(points) < 3:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment retained boundary has fewer than three exact interior samples",
            stage="exact_sections",
            evidence={"source_edge_ids": list(edge_ids)},
        )
    return (points, point_edge_ids) if with_edge_ids else points


def _boundary_curve_points(inventory, edge_ids, *, sample_count):
    """Sample exact boundary edges in topological chain order.

    The result is only measurement evidence.  It preserves edge connectivity so
    downstream closest-point operations cannot introduce synthetic chords
    between arbitrarily sorted source edges.
    """

    edge_ids = tuple(sorted(set(edge_ids)))
    if not edge_ids:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment boundary has no source edges",
            stage="exact_sections",
        )
    endpoints = {
        edge_id: tuple(
            tuple(round(float(value), 12) for value in vertex.toTuple())
            for vertex in inventory["edges_by_id"][edge_id].Vertices()
        )
        for edge_id in edge_ids
    }
    if any(len(values) != 2 for values in endpoints.values()):
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment boundary contains a non-regular source edge",
            stage="exact_sections",
            evidence={"source_edge_ids": list(edge_ids)},
        )
    incidence: dict[tuple[float, float, float], list[str]] = {}
    for edge_id, values in endpoints.items():
        for value in values:
            incidence.setdefault(value, []).append(edge_id)
    if any(len(values) > 2 for values in incidence.values()):
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment boundary source edges form a branched chain",
            stage="exact_sections",
            evidence={"source_edge_ids": list(edge_ids)},
        )
    remaining = set(edge_ids)
    chains: list[list[tuple[str, bool]]] = []
    while remaining:
        component = set()
        pending = [min(remaining)]
        while pending:
            edge_id = pending.pop()
            if edge_id in component:
                continue
            component.add(edge_id)
            for vertex in endpoints[edge_id]:
                pending.extend(
                    candidate
                    for candidate in incidence[vertex]
                    if candidate in remaining and candidate not in component
                )
        component_vertices = {
            vertex for edge_id in component for vertex in endpoints[edge_id]
        }
        start_vertices = sorted(
            vertex
            for vertex in component_vertices
            if len(set(incidence[vertex]).intersection(component)) == 1
        )
        current_vertex = (
            start_vertices[0] if start_vertices else min(component_vertices)
        )
        component_remaining = set(component)
        ordered: list[tuple[str, bool]] = []
        while component_remaining:
            candidates = sorted(
                edge_id
                for edge_id in incidence[current_vertex]
                if edge_id in component_remaining
            )
            if not candidates:
                raise AxisFirstPipelineError(
                    "v116_root_attachment_measurement_failed",
                    "attachment boundary component cannot be traversed",
                    stage="exact_sections",
                    evidence={"source_edge_ids": sorted(component)},
                )
            edge_id = candidates[0]
            first, last = endpoints[edge_id]
            forward = first == current_vertex
            current_vertex = last if forward else first
            component_remaining.remove(edge_id)
            remaining.remove(edge_id)
            ordered.append((edge_id, forward))
        chains.append(ordered)
    points: list[tuple[float, float, float]] = []
    for ordered in chains:
        for edge_id, forward in ordered:
            samples = _sample_exact_edge_points(
                inventory["edges_by_id"][edge_id], max(3, int(sample_count))
            )
            if not forward:
                samples.reverse()
            for point in samples:
                if not points or np.linalg.norm(
                    np.asarray(point) - np.asarray(points[-1])
                ) > 1.0e-9:
                    points.append(point)
    if len(points) < 3:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "attachment boundary has fewer than three exact samples",
            stage="exact_sections",
            evidence={"source_edge_ids": list(edge_ids)},
        )
    return points


def _boundary_pair_directions(
    inventory,
    retained_points,
    footprint_edge_ids,
    *,
    candidate_footprint_edge_ids=None,
):
    """Measure retained-to-footprint directions using exact OCCT distance queries."""

    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt
    except ImportError as exc:  # pragma: no cover - OCCT fixture tests cover this.
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "OCCT closest-point queries are required for attachment directions",
            stage="exact_sections",
            evidence={"exception_type": type(exc).__name__},
        ) from exc
    directions = []
    source_points = []
    candidate_sets = (
        [tuple(footprint_edge_ids)] * len(retained_points)
        if candidate_footprint_edge_ids is None
        else list(candidate_footprint_edge_ids)
    )
    if len(candidate_sets) != len(retained_points):
        raise ValueError(
            "candidate_footprint_edge_ids must match retained point count"
        )
    for coordinates, candidate_edge_ids in zip(
        np.asarray(retained_points, dtype=float), candidate_sets
    ):
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(*(float(value) for value in coordinates))
        ).Vertex()
        candidates = []
        for edge_id in candidate_edge_ids:
            operation = BRepExtrema_DistShapeShape(
                vertex, inventory["edges_by_id"][edge_id].wrapped
            )
            operation.Perform()
            if not operation.IsDone() or operation.NbSolution() < 1:
                continue
            source_point = operation.PointOnShape2(1)
            point = np.asarray(
                [source_point.X(), source_point.Y(), source_point.Z()], dtype=float
            )
            candidates.append((float(operation.Value()), edge_id, point))
        if not candidates:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "attachment retained point has no exact footprint projection",
                stage="exact_sections",
                evidence={"footprint_source_edge_ids": list(footprint_edge_ids)},
            )
        _distance, _edge_id, source_point = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        direction = coordinates - source_point
        length = float(np.linalg.norm(direction))
        if length <= 1.0e-12:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "attachment retained boundary is not lifted from its footprint",
                stage="exact_sections",
                evidence={"footprint_source_edge_ids": list(footprint_edge_ids)},
            )
        directions.append(tuple(float(value) for value in direction / length))
        source_points.append(tuple(float(value) for value in source_point))
    return directions, source_points


def _local_span_directions_from_source_edges(
    inventory,
    retained_points,
    footprint_points,
    span_edge_ids,
    *,
    material_side,
):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.TopoDS import TopoDS
    except ImportError as exc:  # pragma: no cover - covered by OCCT fixture tests when available.
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "OCCT edge tangent measurement is required for attachment span directions",
            stage="exact_sections",
            evidence={"exception_type": type(exc).__name__},
        ) from exc
    footprint = np.asarray(footprint_points, dtype=float)
    edge_samples = []
    for edge_id in span_edge_ids:
        adaptor = BRepAdaptor_Curve(TopoDS.Edge_s(inventory["edges_by_id"][edge_id].wrapped))
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        parameters = np.linspace(first, last, 129)
        points = []
        for parameter in parameters:
            point = adaptor.Value(float(parameter))
            points.append(np.asarray([float(point.X()), float(point.Y()), float(point.Z())]))
        edge_samples.append((edge_id, adaptor, first, last, parameters, np.asarray(points)))
    directions = []
    for point in np.asarray(retained_points, dtype=float):
        best = None
        for edge_id, adaptor, first, last, parameters, points in edge_samples:
            sample_index = int(np.argmin(np.linalg.norm(points - point, axis=1)))
            parameter = float(parameters[sample_index])
            step = max(abs(last - first) * 1.0e-5, 1.0e-9)
            low = max(first, parameter - step)
            high = min(last, parameter + step)
            low_point = adaptor.Value(low)
            high_point = adaptor.Value(high)
            tangent = np.asarray(
                [
                    float(high_point.X() - low_point.X()),
                    float(high_point.Y() - low_point.Y()),
                    float(high_point.Z() - low_point.Z()),
                ],
                dtype=float,
            )
            length = float(np.linalg.norm(tangent))
            if length <= 1.0e-12:
                continue
            tangent /= length
            distance = float(np.linalg.norm(points[sample_index] - point))
            candidate = (distance, edge_id, parameter, tangent)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
        if best is None:
            raise AxisFirstPipelineError(
                "v116_root_attachment_measurement_failed",
                "attachment retained boundary has no source span-edge tangent",
                stage="exact_sections",
                evidence={"span_direction_source_ids": list(span_edge_ids)},
            )
        _distance, _edge_id, _parameter, tangent = best
        nearest_footprint = footprint[
            int(np.argmin(np.linalg.norm(footprint - point, axis=1)))
        ]
        outward = point - nearest_footprint
        if float(np.linalg.norm(outward)) > 1.0e-9:
            if float(np.dot(tangent, outward)) < 0.0:
                tangent = -tangent
        elif int(material_side) < 0:
            tangent = -tangent
        directions.append(tuple(float(value) for value in tangent))
    return directions


def _attachment_width_direction(points):
    values = np.asarray(points, dtype=float)
    centered = values - np.mean(values, axis=0)
    _, _, axes = np.linalg.svd(centered, full_matrices=False)
    direction = axes[0]
    if float(np.linalg.norm(direction)) <= 1.0e-12:
        raise AxisFirstPipelineError(
            "v116_root_attachment_measurement_failed",
            "single-edge attachment boundary has no measurable width direction",
            stage="exact_sections",
        )
    return tuple(float(value) for value in direction / np.linalg.norm(direction))


def _source_tolerance(frame):
    return max(
        1.0e-6,
        float(
            frame.get("axis_consensus", {})
            .get("selected_cluster", {})
            .get("tolerance", {})
            .get("line_distance_mm", 0.01)
        ),
    )


def _transform_point(point, matrix):
    vector = np.asarray([*point, 1.0], dtype=float)
    return (np.asarray(matrix, dtype=float) @ vector)[:3]


def _stage_record(stage, evidence):
    return {
        "stage": stage,
        "status": "PASS",
        "facts": _compact_stage_facts(stage, evidence),
        "evidence_hash_sha256": stable_measurement_hash(_jsonable(evidence)),
    }


def _compact_stage_facts(stage, evidence):
    """Persist inspectable source facts alongside the integrity hash."""
    if not isinstance(evidence, Mapping):
        return {}
    if stage == "source_inventory":
        return {
            "source_sha256": evidence.get("source_sha256"),
            "face_count": evidence.get("face_count"),
            "edge_count": evidence.get("edge_count"),
            "authority": evidence.get("authority"),
        }
    if stage == "support_recovery":
        topology = evidence.get("support_face_ids", {})
        return {
            "topology_mode": evidence.get("topology_mode"),
            "hub_source_face_id": topology.get("hub_face_id"),
            "tip_or_shroud_source_face_ids": evidence.get("mapping_fits", {}).get(
                "tip_or_shroud", {}
            ).get("source_ids", []),
            "semantic_partition_digest": evidence.get("semantic_partition_digest"),
        }
    if stage == "periodic_representatives":
        return {
            "main_count": (evidence.get("main") or {}).get("count"),
            "splitter_count": (evidence.get("splitter") or {}).get("count", 0),
            "closure_pass": evidence.get("closure_pass"),
            "collision_free": evidence.get("collision_free"),
            "source_ids": evidence.get("source_ids", []),
        }
    if stage == "exact_sections":
        families = evidence.get("section_families", {})
        return {
            "families": {
                name: {
                    "station_count": len(family.get("stations", [])),
                    "source_ids": family.get("source_ids", []),
                }
                for name, family in families.items()
            },
            "attachment_kinds": sorted(evidence.get("attachments", {})),
        }
    if stage == "measurement_bundle":
        return {
            "schema_version": evidence.get("schema_version"),
            "source_sha256": evidence.get("provenance", {}).get("source_sha256"),
            "topology_mode": evidence.get("topology", {}).get("mode"),
            "family_names": sorted(evidence.get("section_families", {})),
        }
    return {}


def _jsonable(value):
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items() if key != "shape"}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return type(value).__name__


def _exception_stage(exc):
    reason = getattr(exc, "reason", "")
    if "support" in reason or "hub" in reason or "shroud" in reason or "tip_reference" in reason:
        return "support_recovery"
    if "periodic" in reason or "representative" in reason:
        return "periodic_representatives"
    return "exact_sections"


def _next_stage(completed):
    names = [record["stage"] for record in completed]
    for stage in (
        "source_inventory",
        "support_recovery",
        "periodic_representatives",
        "exact_sections",
        "measurement_bundle",
    ):
        if stage not in names:
            return stage
    return "measurement_bundle"


def _stage_reason(stage):
    return {
        "source_inventory": "v116_hub_support_classification_failed",
        "support_recovery": "v116_hub_support_classification_failed",
        "periodic_representatives": "v116_periodic_population_ambiguous",
        "sections": "v116_section_intersection_failed",
        "exact_sections": "v116_section_intersection_failed",
        "measurement_bundle": "v116_v112_mapping_residual_exceeded",
        "v112_mapping": "v116_v112_mapping_residual_exceeded",
    }.get(stage, "v116_v112_mapping_residual_exceeded")
