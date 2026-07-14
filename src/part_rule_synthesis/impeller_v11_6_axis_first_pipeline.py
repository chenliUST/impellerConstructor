from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from part_rule_synthesis import impeller_v11_6_section_recovery as section_recovery
from part_rule_synthesis import impeller_v11_6_support_recovery as support_recovery
from part_rule_synthesis.impeller_v11_6_v112_mapping import (
    MEASUREMENT_SCHEMA_VERSION,
    V112MappingError,
    V112MappingTolerances,
    adapt_task7_segment_for_mapping,
    map_measurements_to_v112,
)


ALGORITHM_VERSION = "axis_first_measurement_bundle_task9_r3"
_STABLE_REASONS = {
    "v116_hub_support_classification_failed",
    "v116_hub_profile_fit_failed",
    "v116_tip_reference_inference_failed",
    "v116_shroud_topology_ambiguous",
    "v116_periodic_population_ambiguous",
    "v116_representative_blade_selection_failed",
    "v116_section_intersection_failed",
    "v116_section_loop_open",
    "v116_section_loop_correspondence_failed",
    "v116_section_tangent_flip_detected",
    "v116_thickness_field_invalid",
    "v116_root_attachment_measurement_failed",
    "v116_v112_mapping_residual_exceeded",
    "v116_false_material_surface_forbidden",
}
_TASK8_RECONSTRUCTION_EVIDENCE_BASIS = (
    "v116_axis_first_periodic_material_evidence_v1"
)


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
    except (support_recovery.SupportRecoveryError, section_recovery.SectionRecoveryError) as exc:
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
        raise AxisFirstPipelineError(
            "v116_v112_mapping_residual_exceeded",
            str(exc),
            stage="v112_mapping",
            evidence={
                "upstream_reason": exc.reason,
                "mapping_details": copy.deepcopy(exc.details),
            },
            details={"completed_stages": list(result.stage_evidence)},
        ) from exc

    parameters = mapped["parameters"]
    unsupported_audit = _unsupported_source_feature_audit(
        result.section_evidence,
        result.measurements,
    )
    support_payload = _jsonable(result.support_evidence)
    periodic_payload = _jsonable(result.periodic_evidence)
    source_sha256 = str(result.measurements["provenance"]["source_sha256"])
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
    if len(edge_id_by_index) != edge_index.Extent():
        raise AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "source edge inventory is incomplete relative to OCCT topology",
            stage="source_inventory",
            evidence={
                "inventory_edge_count": len(edge_id_by_index),
                "occt_edge_count": int(edge_index.Extent()),
            },
        )
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
    assignments = _semantic_assignments(inventory, semantics, topology)
    partition = support_recovery.authenticate_occt_semantic_partition(
        inventory["shape"], face_assignments=assignments
    )
    matrix = frame["source_to_canonical_matrix"]
    tolerance = _source_tolerance(frame)
    hub_ids = list(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
    hub_samples = [
        support_recovery.sample_occt_face_meridional_paths(
            inventory["faces_by_id"][hub_id],
            source_face_id=hub_id,
            source_solid=inventory["shape"],
            semantic_partition_evidence=partition,
            source_to_canonical_matrix=matrix,
            source_tolerance_mm=tolerance,
            trace_count=9,
            samples_per_trace=65,
        )
        for hub_id in hub_ids
    ]
    hub_fit = _fit_authenticated_support(
        hub_samples,
        outer_diameter_mm=2.0 * float(frame["outer_radius_mm"]),
        semantic_role="hub_profile",
        minimum_radius_mm=min(
            float(instance["radial_support_range_mm"][0])
            for population in semantics["periodic_population_recovery"]["populations"]
            for instance in population["instances"]
        ),
    )

    if topology["mode"] == "open":
        tip_support, topology_result = _recover_open_tip(
            inventory, frame, semantics, topology
        )
    else:
        tip_support, topology_result = _recover_closed_shroud(
            inventory, frame, semantics, topology, partition
        )
    return {
        "status": "PASS",
        "topology": topology_result,
        "topology_mode": topology["mode"],
        "semantic_partition_digest": partition["partition_digest"],
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
            if support_ids.intersection(adjacency.get(face_id, ()))
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
    hub_group = groups[0]
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
    comparable_groups = [
        item
        for item in groups[1:]
        if item["periodic_instance_ids"] == hub_group["periodic_instance_ids"]
        and item["shared_contact_length_mm"]
        >= 0.5 * hub_group["shared_contact_length_mm"]
    ]
    mode = "closed" if comparable_groups else "open"
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
        elif face_id == topology.get("inner_shroud_face_id"):
            role, flowpath = "inner_shroud_flowpath_support", True
        elif face_id == topology.get("outer_shroud_face_id"):
            role = "outer_shroud_material_support"
        elif face_id in attachment_faces:
            role, flowpath = "periodic_blade_tip_attachment", True
        elif face_id in open_caps:
            role, flowpath = "periodic_blade_tip_cap", True
        elif instance_id is not None:
            role, flowpath = "periodic_blade_side", True
        assignments[face_id] = {
            "shape": face,
            "role": role,
            "alternatives": [],
            "periodic_instance_id": instance_id,
            "periodic_blade_related": instance_id is not None,
            "flowpath_adjacent": flowpath,
            "root_blend": False,
            "hole_boundary": (
                face_id not in support_boundary_ids
                and "bore"
                in semantics["face_roles"].get(face_id, {}).get("role", "")
            ),
            "local_edge_treatment": False,
        }
    return assignments


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
            adjacent_id, edge_id, edge = _cap_shared_edge(
                inventory, cap_id, set(instance["source_face_ids"])
            )
            loop_id = f"{instance_id}_open_tip_loop"
            records.append(
                {
                    "periodic_instance_id": instance_id,
                    "tip_cap_face_id": cap_id,
                    "shared_edge_loops": [
                        {
                            "loop_id": loop_id,
                            "source_edge_ids": [edge_id],
                            "adjacent_periodic_faces": [
                                {
                                    "face_id": adjacent_id,
                                    "face_role": "side",
                                    "periodic_instance_id": instance_id,
                                }
                            ],
                        }
                    ],
                }
            )
            expected[instance_id] = [loop_id]
            face_shapes[cap_id] = cap
            face_shapes[adjacent_id] = inventory["faces_by_id"][adjacent_id]
            edge_shapes[edge_id] = edge
            edge_evidence.append(
                support_recovery.sample_occt_edge_meridional_path(
                    edge,
                    source_edge_id=edge_id,
                    source_solid=inventory["shape"],
                    source_to_canonical_matrix=frame["source_to_canonical_matrix"],
                    source_tolerance_mm=_source_tolerance(frame),
                )
            )
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
    result = {
        "status": "PASS",
        "closure_pass": bool(recovery["closure_diagnostics"]["all_populations_closed"]),
        "collision_free": bool(recovery["collision_diagnostics"]["collision_free"]),
        "phase_consistent": True,
        "source_ids": sorted(
            {
                face_id
                for population in recovery["populations"]
                for instance in population["instances"]
                for face_id in instance["source_face_ids"]
            }
        ),
        "source_linear_tolerance_mm": source_tolerance_mm,
        "measurement_tolerance_mm": representative_fit_tolerance_mm,
        "generated_rigid_transform_tolerance_mm": source_tolerance_mm,
        "representative_fit_ceiling_mm": representative_fit_ceiling_mm,
        "measurement_tolerance_basis": (
            "maximum_authenticated_periodic_representative_fit_residual"
        ),
        "pattern_population_evidence": copy.deepcopy(recovery),
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
            hub_id = support["support_face_ids"]["hub_face_id"]
            support_bound = [
                item
                for item in population["instances"]
                if any(
                    hub_id
                    in inventory["source_manifest"]["adjacency"].get(
                        face_id, ()
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
                        "hub_face_id": hub_id,
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
        radial = instance["radial_support_range_mm"]
        outer_radius = float(frame["outer_radius_mm"])
        interval = [
            max(0.0, min(0.95, float(radial[0]) / max(abs(outer_radius), 1.0e-9))),
            max(0.05, min(1.0, float(radial[1]) / max(abs(outer_radius), 1.0e-9))),
        ]
        if interval[1] <= interval[0]:
            interval = [0.05, 0.95]
        result[name] = {
            "count": int(population["count"]),
            "pitch_deg": float(population["pitch_deg"]),
            "phase_deg": float(population["phase_deg"]),
            "phase_relative_to_main_deg": float(population["phase_relative_to_main_deg"]),
            "streamwise_interval_s": interval,
            "source_ids": sorted(instance["source_face_ids"]),
            "representative_instance": copy.deepcopy(instance),
            "angular_sector_deg": (
                float(instance["angular_envelope_deg"]["start_angle_deg"]),
                float(instance["angular_envelope_deg"]["end_angle_deg"]),
            ),
        }
    return result


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
    return {
        "status": "PASS",
        "section_families": families,
        "section_loop_records": loop_records,
        "attachment_records": attachment_records,
        "attachments": attachments,
        "measurement_authority": "occt_revolved_meridional_surfaces",
    }


def _section_family(inventory, frame, support, name, population, attachments):
    """Section a representative blade with ordered revolved support surfaces.

    The station parameter is normalized only after sectioning.  Its geometry is
    always the measured hub-to-tip meridional interpolation, never an axial
    plane or a centroid/bounding-box envelope.
    """
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    instance = population["representative_instance"]
    allowed = sorted(instance["source_face_ids"])
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
    raw_root, raw_tip = _measured_active_span_interval(
        hub["control_points_rz_mm"], tip["control_points_rz_mm"], tolerance,
        root_evidence, tip_evidence,
        root_attachment=attachments["root"],
        tip_attachment=attachments.get("shroud"),
    )
    root_evidence = {
        **root_evidence,
        "h": raw_root,
        "measured_attachment_lift_mm": float(attachments["root"].lift_mm),
        "retained_source_edge_ids": list(attachments["root"].retained_source_edge_ids),
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
    correspondence = section_recovery.solve_meridional_correspondence(hub, tip)

    def section_at(raw_h: float):
        key = round(float(raw_h), 12)
        if key in cache:
            return cache[key]
        profile = section_recovery.build_ordered_span_profiles(
            correspondence, [0.0, float(raw_h), 1.0]
        )[1]
        section_profile, extension_margin = _extended_section_profile(
            profile.points_rz_mm,
            tolerance,
            support_profiles_rz_mm=(
                hub["control_points_rz_mm"],
                tip["control_points_rz_mm"],
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
        prior = cache[sorted(cache)[-1]][1].accepted_loop if cache else None
        try:
            result = section_recovery.section_source_solid(
                inventory["shape"],
                surface,
                angular_sector_deg=population["angular_sector_deg"],
                angular_source_to_canonical_matrix=matrix,
                source_faces_by_id=inventory["faces_by_id"],
                allowed_source_face_ids=allowed,
                source_face_roles=role_map,
                local_projector=projector,
                section_normal_xyz=normal_source,
                source_tolerance_mm=tolerance,
                edge_sample_count=65,
                reference_loop=prior,
                source_shape_scope="complete_source_shape",
            )
        except section_recovery.SectionRecoveryError as exc:
            exc.details.update(
                {
                    "raw_span_h": float(raw_h),
                    "active_span_interval_h": [float(raw_root), float(raw_tip)],
                    "representative_source_face_ids": list(allowed),
                }
            )
            raise
        decomposition = section_recovery.decompose_section_loop(
            result.accepted_loop,
            maximum_control_count=25,
        )
        _assert_section_segment_fit_quality(decomposition, tolerance, raw_h)
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
        return cache[key]

    def metric_sampler(raw_h: float) -> Mapping[str, Any]:
        _profile, result, decomposition, thickness, _margin = section_at(raw_h)
        return _preliminary_section_metrics(result.accepted_loop, decomposition, thickness)

    lattice = section_recovery.build_adaptive_span_profiles(
        hub,
        tip,
        metric_sampler,
        active_root_h=raw_root,
        active_tip_h=raw_tip,
        active_root_evidence=root_evidence,
        active_tip_evidence=tip_evidence,
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
    span_width = raw_tip - raw_root
    for station_index, station in enumerate(lattice.stations):
        profile, result, decomposition, thickness, extension_margin = section_at(
            station.h
        )
        if station_index == 0:
            mapped_h = 0.0
        elif station_index == len(lattice.stations) - 1:
            mapped_h = 1.0
        else:
            mapped_h = (float(station.h) - raw_root) / span_width
        loop = result.accepted_loop
        output_stations.append(_station_for_mapping(mapped_h, loop, decomposition, thickness, frame))
        records.append(
            {
                "population": name,
                "h": mapped_h,
                "support_span_h": float(station.h),
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
            }
        )
    return (
        {
            "population": name,
            "stations": output_stations,
            "source_ids": allowed,
        },
        records,
    )


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
        raise section_recovery.SectionRecoveryError(
            "v116_thickness_field_invalid",
            "blade sides have no common streamwise domain",
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
            hit_a, hit_b = section_recovery._opposite_side_normal_hits(  # noqa: SLF001
                point, normal, side_a, side_b
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
    for fraction in requested_s:
        point, normal = section_recovery._camber_point_and_normal(  # noqa: SLF001
            camber_fit, float(fraction)
        )
        hit_a, hit_b = section_recovery._opposite_side_normal_hits(  # noqa: SLF001
            point, normal, side_a, side_b
        )
        point_a, parameter_a, lambda_a = hit_a
        point_b, parameter_b, lambda_b = hit_b
        thickness = abs(lambda_a - lambda_b)
        inside = all(
            section_recovery._point_in_polygon(  # noqa: SLF001
                (1.0 - alpha) * point_a + alpha * point_b, polygon
            )
            for alpha in (0.25, 0.5, 0.75)
        )
        if not math.isfinite(thickness) or thickness <= 1.0e-12 or not inside:
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
                inside_source_loop=True,
            )
        )
    _assert_monotone_thickness_correspondence(samples)
    return section_recovery.ThicknessField(
        loop_id=loop.loop_id, samples=tuple(samples), camber_fit=camber_fit
    )


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


def _station_for_mapping(h, loop, decomposition, thickness, frame):
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
    return {
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
                    "inside_source_loop": bool(sample.inside_source_loop),
                }
                for sample in samples
            ],
            "source_ids": source_ids,
            "method": thickness.method,
        },
    }


def _assert_section_segment_fit_quality(decomposition, fit_tolerance, h):
    for segment in decomposition.segments:
        if segment.fit.residual_max_mm <= fit_tolerance + 1.0e-12:
            continue
        raise AxisFirstPipelineError(
            "v116_v112_mapping_residual_exceeded",
            "measured section-segment NURBS fit exceeds source tolerance",
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
    root_lift = max(float(value) for value in root_attachment.lift_samples_mm)
    root_boundary_margin = max(
        4.0 * float(tolerance_mm),
        0.10 * float(root_attachment.attachment_width_mm),
    )
    root_clearance = (root_lift + root_boundary_margin) / minimum_span
    tip_lift = (
        0.0
        if tip_attachment is None
        else max(float(value) for value in tip_attachment.lift_samples_mm)
    )
    tip_width = float(
        root_attachment.attachment_width_mm
        if tip_attachment is None
        else tip_attachment.attachment_width_mm
    )
    tip_boundary_margin = max(4.0 * float(tolerance_mm), 0.10 * tip_width)
    tip_clearance = (tip_lift + tip_boundary_margin) / minimum_span
    if root_clearance >= 0.25 or tip_clearance >= 0.25:
        raise AxisFirstPipelineError(
            "v116_span_surface_ordering_failed",
            "source support separation cannot provide a blade-body section clearance",
            stage="exact_sections",
            evidence={
                "minimum_support_separation_mm": minimum_span,
                "source_tolerance_mm": tolerance_mm,
                "root_attachment_lift_mm": float(root_attachment.lift_mm),
                "root_attachment_maximum_lift_mm": root_lift,
                "root_attachment_width_mm": float(
                    root_attachment.attachment_width_mm
                ),
                "root_boundary_margin_mm": root_boundary_margin,
                "tip_attachment_width_mm": tip_width,
                "tip_boundary_margin_mm": tip_boundary_margin,
                "tip_attachment_lift_mm": (
                    None if tip_attachment is None else float(tip_attachment.lift_mm)
                ),
                "root_source_edge_ids": root["source_edge_ids"],
                "tip_source_edge_ids": tip["source_edge_ids"],
            },
        )
    root_h = max(root_clearance, tolerance_clearance)
    tip_h = 1.0 - max(tip_clearance, tolerance_clearance)
    if not 0.0 < root_h < tip_h < 1.0:
        raise AxisFirstPipelineError(
            "v116_span_surface_ordering_failed",
            "measured attachment clearances leave no ordered blade-body span",
            stage="exact_sections",
            evidence={
                "active_root_h": root_h,
                "active_tip_h": tip_h,
                "minimum_support_separation_mm": minimum_span,
            },
        )
    return root_h, tip_h


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
    inventory, frame, population, topology, *, include_shroud
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
        )
    return result


def _measure_attachment_between_supports(
    inventory, frame, component_ids, support_ids, *, upper, kind
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
    return function(
        footprint,
        retained,
        local_span_directions_xyz=local_span_directions,
        paired_footprint_points_xyz_mm=paired_footprint,
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
        "phase_consistent": periodic["phase_consistent"],
        "source_ids": periodic["source_ids"],
    }
    if periodic["splitter"] is not None:
        main_pitch = float(periodic["main"]["pitch_deg"])
        relative = float(periodic["splitter"]["phase_relative_to_main_deg"]) / main_pitch
        populations["relative_phase_pitch"] = relative % 1.0
    source_ids = sorted(inventory["faces_by_id"])
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
        "section_families": copy.deepcopy(sections["section_families"]),
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
    bore = cylinders[0]
    if len(cylinders) > 1 and abs(cylinders[1]["radius_mm"] - bore["radius_mm"]) <= tolerance:
        _material_failure(
            "mounting_bore_radius_mm",
            "the smallest authenticated coaxial cylinder radius is not unique",
            {"coaxial_cylinder_candidates": cylinders},
        )

    bore_caps = _perpendicular_plane_neighbors(
        inventory, bore["face_id"], axis, tolerance
    )
    if len(bore_caps) != 2:
        _material_failure(
            "mounting_bore_radius_mm",
            "the bore does not terminate at exactly two authenticated perpendicular planes",
            {"bore": bore, "bore_cap_candidates": bore_caps},
        )
    bore_caps.sort(key=lambda item: item["axis_parameter_mm"])
    outer_low, outer_high = bore_caps

    core_candidates = []
    for candidate in cylinders[1:]:
        caps = _perpendicular_plane_neighbors(
            inventory, candidate["face_id"], axis, tolerance
        )
        if len(caps) != 2:
            continue
        caps.sort(key=lambda item: item["axis_parameter_mm"])
        if (
            outer_low["axis_parameter_mm"] + tolerance
            < caps[0]["axis_parameter_mm"]
            < caps[1]["axis_parameter_mm"]
            < outer_high["axis_parameter_mm"] - tolerance
        ):
            core_candidates.append({**candidate, "cap_planes": caps})
    if len(core_candidates) != 1:
        _material_failure(
            "hub_wall_thickness_mm",
            "exact bore-to-core material wall relationship is missing or ambiguous",
            {
                "bore": bore,
                "outer_bore_cap_face_ids": [
                    outer_low["face_id"],
                    outer_high["face_id"],
                ],
                "nested_coaxial_core_candidates": core_candidates,
            },
        )
    core = core_candidates[0]
    inner_low, inner_high = core["cap_planes"]
    wall = float(core["radius_mm"] - bore["radius_mm"])
    bottom = float(
        inner_low["axis_parameter_mm"] - outer_low["axis_parameter_mm"]
    )
    top = float(
        outer_high["axis_parameter_mm"] - inner_high["axis_parameter_mm"]
    )
    if min(wall, bottom, top) <= tolerance:
        _material_failure(
            "hub_wall_thickness_mm",
            "authenticated nested material distances are not positive",
            {"wall_mm": wall, "bottom_mm": bottom, "top_mm": top},
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
        inventory, bore, bore_caps, tolerance_mm=tolerance
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
            },
        ),
        "hub_wall_thickness_mm": _material_record(
            wall,
            "coaxial_cylinder_radial_face_distance",
            sorted(set(bore["source_ids"]) | set(core["source_ids"])),
            {
                "inner_radius_mm": bore["radius_mm"],
                "outer_radius_mm": core["radius_mm"],
                "paired_face_ids": [bore["face_id"], core["face_id"]],
            },
        ),
        "hub_bottom_thickness_mm": _material_record(
            bottom,
            "parallel_material_plane_distance",
            [outer_low["face_id"], inner_low["face_id"]],
            {
                "axis_parameters_mm": [
                    outer_low["axis_parameter_mm"],
                    inner_low["axis_parameter_mm"],
                ],
                "material_orientation": "canonical_axis_low_side",
            },
        ),
        "hub_top_cap_thickness_mm": _material_record(
            top,
            "parallel_material_plane_distance",
            [inner_high["face_id"], outer_high["face_id"]],
            {
                "axis_parameters_mm": [
                    inner_high["axis_parameter_mm"],
                    outer_high["axis_parameter_mm"],
                ],
                "material_orientation": "canonical_axis_high_side",
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
                "radius_mm": radius,
                "axis_residual_mm": line_residual,
                "axis_alignment": angular_alignment,
                "circular_source_edge_ids": sorted(circular_ids),
                "source_ids": [face_id, *sorted(circular_ids)],
            }
        )
    return sorted(records, key=lambda item: (item["radius_mm"], item["face_id"]))


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
            component = set(instance["source_face_ids"])
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


def _measure_bore_edge_treatment(inventory, bore, bore_caps, *, tolerance_mm):
    bore_face_id = bore["face_id"]
    direct_edges = set()
    exhaustive_faces = {bore_face_id}
    for cap in bore_caps:
        exhaustive_faces.add(cap["face_id"])
        direct_edges.update(
            _face_edge_ids(inventory, bore_face_id)
            & _face_edge_ids(inventory, cap["face_id"])
        )
    adjacent_faces = set(
        inventory["source_manifest"]["adjacency"].get(bore_face_id, ())
    )
    exhaustive_faces.update(adjacent_faces)
    treatment_faces = {
        face_id
        for face_id in adjacent_faces
        if face_id not in {cap["face_id"] for cap in bore_caps}
        and inventory["faces_by_id"][face_id].geomType() in {"CONE", "TORUS"}
    }
    if treatment_faces:
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


def _attachment_for_mapping(record):
    source_ids = sorted(
        set(record.source_face_ids)
        | set(record.footprint_source_edge_ids)
        | set(record.retained_source_edge_ids)
        | set(record.span_direction_source_ids)
    )
    width = float(record.attachment_width_mm)
    return {
        "lift_samples_mm": [float(value) for value in record.lift_samples_mm],
        "width_samples_mm": [width, width, width],
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
            component_ids = set(instance["source_face_ids"])
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
    component_ids = set(instance["source_face_ids"])
    hub_support_ids = set(
        topology.get("hub_support_face_ids", [topology["hub_face_id"]])
    )
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


def _cap_shared_edge(inventory, cap_id, component_ids):
    choices = []
    for adjacent_id in sorted(component_ids - {cap_id}):
        for edge_id in sorted(
            _face_edge_ids(inventory, cap_id).intersection(
                _face_edge_ids(inventory, adjacent_id)
            )
        ):
            edge = inventory["edges_by_id"][edge_id]
            choices.append((-float(edge.Length()), adjacent_id, edge_id, edge))
    if not choices:
        raise AxisFirstPipelineError(
            "v116_tip_reference_inference_failed",
            "open tip cap has no exact shared edge with its periodic component",
            stage="support_recovery",
            evidence={"tip_cap_face_id": cap_id},
        )
    _, adjacent_id, edge_id, edge = min(choices)
    return adjacent_id, edge_id, edge


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
