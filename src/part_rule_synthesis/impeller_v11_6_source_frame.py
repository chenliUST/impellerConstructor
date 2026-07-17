from __future__ import annotations

import hashlib
import heapq
import json
import math
import time
from collections import Counter, defaultdict
from typing import Any

import numpy as np


AXIS_ANGULAR_TOLERANCE_DEG = 0.05
MIN_AXIS_LINE_TOLERANCE_MM = 0.02
AXIS_DIAMETER_TOLERANCE_FACTOR = 0.0002
GLOBAL_SAMPLE_BUDGET = 1_500_000
GLOBAL_SAMPLE_WALL_SECONDS = 180.0
PER_FACE_SAMPLE_BUDGET = 25_000
PER_FACE_SAMPLE_WALL_SECONDS = 20.0
MAXIMUM_CONTROL_REFINEMENT_DEPTH = 10


class AxisConsensusError(RuntimeError):
    def __init__(
        self, reason: str, message: str, details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


class _SamplingBudget:
    def __init__(self, *, maximum_samples: int, maximum_wall_seconds: float):
        self.maximum_samples = int(maximum_samples)
        self.maximum_wall_seconds = float(maximum_wall_seconds)
        self.consumed_samples = 0
        self._started_at = time.perf_counter()

    def consume(self, count: int, *, source_face_id: str) -> None:
        self.consumed_samples += int(count)
        if self.consumed_samples > self.maximum_samples:
            raise AxisConsensusError(
                "v116_source_sampling_budget_exceeded",
                "trimmed B-Rep sampling exceeded the global deterministic budget",
                {
                    "source_face_id": source_face_id,
                    **self.evidence(status="EXCEEDED"),
                    "promotable": False,
                },
            )

    def evidence(self, *, status: str = "PASS") -> dict[str, Any]:
        elapsed_seconds = max(0.0, time.perf_counter() - self._started_at)
        evidence = {
            "status": status,
            "maximum_samples": self.maximum_samples,
            "consumed_samples": self.consumed_samples,
            "maximum_wall_seconds": self.maximum_wall_seconds,
            "wall_clock_budget_enforced": False,
            "decision_basis": "deterministic_sample_count_only",
            "wall_clock_telemetry": {
                "status": "DIAGNOSTIC_ONLY",
                "elapsed_seconds": round(elapsed_seconds, 9),
                "maximum_wall_seconds": self.maximum_wall_seconds,
                "affects_certification": False,
                "affects_sampling_budget": False,
            },
        }
        return evidence


def resolve_canonical_frame(shape, source_manifest: dict[str, Any]) -> dict[str, Any]:
    raw_candidates = _extract_axis_candidates(shape)
    if not raw_candidates:
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "no cylindrical, conical, circular-edge or revolved axis evidence was found",
        )

    diameter = _source_diameter(source_manifest)
    line_tolerance = max(
        MIN_AXIS_LINE_TOLERANCE_MM, AXIS_DIAMETER_TOLERANCE_FACTOR * diameter
    )
    clusters = _cluster_axis_candidates(
        raw_candidates,
        line_tolerance_mm=line_tolerance,
        angular_tolerance_deg=AXIS_ANGULAR_TOLERANCE_DEG,
    )
    for cluster in clusters:
        cluster["periodic_closure_support"] = _periodic_closure_support(
            source_manifest.get("faces", []),
            np.asarray(cluster["line_origin"], dtype=float),
            np.asarray(cluster["line_direction"], dtype=float),
            line_tolerance,
        )
    _score_axis_clusters(clusters)
    ranked = sorted(
        clusters,
        key=lambda item: (
            -item["combined_score"],
            -item["analytic_area_mm2"],
            -item["analytic_feature_count"],
            tuple(item["line_direction"]),
            tuple(item["line_origin"]),
        ),
    )
    if not ranked or ranked[0]["analytic_feature_count"] <= 0:
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "analytic axis candidates did not form a usable cluster",
        )
    if len(ranked) > 1 and _clusters_are_equivalent(ranked[0], ranked[1]):
        raise AxisConsensusError(
            "v116_axis_consensus_ambiguous",
            "equivalent analytic evidence supports more than one physical rotation axis",
            {"competing_candidates": [_public_cluster(item) for item in ranked[:4]]},
        )

    selected = ranked[0]
    line_origin = np.asarray(selected["line_origin"], dtype=float)
    line_direction = np.asarray(selected["line_direction"], dtype=float)
    direction, direction_evidence = _resolve_axis_direction(
        shape, line_origin, line_direction
    )
    vertices = np.asarray(
        [vertex.Center().toTuple() for vertex in shape.Vertices()], dtype=float
    )
    if not len(vertices):
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "source solid has no vertices for frame origin recovery",
        )
    axial_values = (vertices - line_origin) @ direction
    axis_origin = line_origin + direction * float(np.min(axial_values))
    rotation = _rotation_to_positive_z(direction)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = -rotation @ axis_origin
    canonical = _transform_points(vertices, matrix)
    radii = np.linalg.norm(canonical[:, :2], axis=1)
    outer_radius = float(np.max(radii))
    acceptance_line_tolerance = max(
        MIN_AXIS_LINE_TOLERANCE_MM,
        AXIS_DIAMETER_TOLERANCE_FACTOR * 2.0 * outer_radius,
    )
    residual = _cluster_residual(selected)
    source_entity_ids = sorted(selected["source_entity_ids"])
    public_candidates = [_public_cluster(item) for item in ranked]
    central_radii = sorted(
        {
            round(float(candidate["radius_mm"]), 6)
            for candidate in selected["members"]
            if candidate.get("radius_mm") is not None
            and candidate["source_kind"] == "face"
        }
    )

    return {
        "method": "deterministic_analytic_axis_consensus_r3",
        "source_axis_origin_mm": _round_vector(axis_origin, 8),
        "source_axis_direction": _round_vector(direction, 10),
        "source_to_canonical_matrix": [_round_vector(row, 12) for row in matrix],
        "scale": 1.0,
        "primary_icp_applied": False,
        "handedness": "right_handed",
        "axis_consensus": {
            "tolerance": {
                "line_distance_mm": round(acceptance_line_tolerance, 9),
                "clustering_line_distance_mm": round(line_tolerance, 9),
                "angular_deg": AXIS_ANGULAR_TOLERANCE_DEG,
            },
            "selected_cluster": {
                **_public_cluster(selected),
                "source_entity_ids": source_entity_ids,
            },
            "residual": residual,
            "direction_resolution": direction_evidence,
            "rejected_alternatives": public_candidates[1:],
        },
        "candidate_scores": public_candidates,
        "outer_radius_mm": round(outer_radius, 6),
        "main_bore_radius_mm": _coaxial_bore_radius(selected, outer_radius),
        "axial_extent_mm": round(float(np.ptp(canonical[:, 2])), 6),
        "central_cylinder_radii_mm": central_radii,
    }


def coarse_periodic_face_partition(
    shape,
    source_manifest: dict[str, Any],
    frame: dict[str, Any],
) -> dict[str, Any]:
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    source_records = source_manifest.get("faces", [])
    faces = list(shape.Faces())
    if len(faces) != len(source_records):
        raise ValueError("source face records do not match the loaded B-Rep")

    sampling_budget = _SamplingBudget(
        maximum_samples=GLOBAL_SAMPLE_BUDGET,
        maximum_wall_seconds=GLOBAL_SAMPLE_WALL_SECONDS,
    )
    signatures = [
        _face_signature(
            face,
            source_records[index],
            matrix,
            source_manifest.get("adjacency", {}),
            sampling_budget=sampling_budget,
            phase_frame_evidence={
                "source_axis_origin_mm": list(frame["source_axis_origin_mm"]),
                "source_axis_direction": list(frame["source_axis_direction"]),
                "source_to_canonical_matrix": [
                    list(row) for row in frame["source_to_canonical_matrix"]
                ],
                "handedness": frame["handedness"],
                "source_frame_handedness": (
                    "right_handed"
                    if float(frame["source_axis_direction"][2]) >= 0.0
                    else "left_handed_relative_to_source_axis"
                ),
                "source_frame_phase_rule": "source_global_xy_azimuth_about_axis_origin",
                "canonical_frame_phase_rule": "canonical_xy_azimuth_about_positive_z",
                "transform_rule": "source_axis_local_basis_then_rigid_source_to_canonical",
            },
        )
        for index, face in enumerate(faces)
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signature in signatures:
        grouped[signature["signature_hash"]].append(signature)

    rotational_groups: list[dict[str, Any]] = []
    rotational_ids: set[str] = set()
    outer_radius = float(frame["outer_radius_mm"])
    for signature_hash, members in grouped.items():
        group = _periodic_signature_group(signature_hash, members, outer_radius)
        if group is None:
            continue
        rotational_groups.append(group)
        rotational_ids.update(group["member_face_ids"])
        for member in members:
            member["transformed_sample_residual_mm"] = group[
                "transformed_sample_residual_mm"
            ]
            member["residual"]["transformed_sample_mm"] = group[
                "transformed_sample_residual_mm"
            ]

    signature_by_id = {item["source_face_id"]: item for item in signatures}
    rotational_group_by_face_id = {
        face_id: group
        for group in rotational_groups
        for face_id in group["member_face_ids"]
    }
    certified_seed_ids: set[str] = set()
    for group in rotational_groups:
        seed_evidence = _authenticate_periodic_seed_group(
            group,
            [signature_by_id[face_id] for face_id in group["member_face_ids"]],
            outer_radius,
        )
        group["periodic_seed_authentication"] = seed_evidence
        for face_id in group["member_face_ids"]:
            signature_by_id[face_id]["periodic_seed_certification"] = dict(
                seed_evidence
            )
        if seed_evidence["accepted_as_periodic_blade_seed"]:
            certified_seed_ids.update(group["member_face_ids"])
    rotational_local_ids = {
        face_id
        for face_id in rotational_ids
        if _blade_local_connectivity_eligible(
            signature_by_id, rotational_group_by_face_id, face_id
        )
    }
    rotational_components = _connected_components(
        rotational_local_ids,
        source_manifest.get("adjacency", {}),
        signatures,
        classification="rotationally_repeated_candidate",
    )
    component_evidence_by_face_id: dict[str, dict[str, Any]] = {}
    for component in rotational_components:
        evidence = _blade_topology_support_evidence(
            component["face_ids"],
            signature_by_id,
            source_manifest.get("adjacency", {}),
            rotational_ids,
            outer_radius,
        )
        component["blade_topology_support"] = evidence
        for face_id in component["face_ids"]:
            component_evidence_by_face_id[face_id] = evidence
            signature_by_id[face_id]["blade_topology_support"] = evidence
    for signature in signatures:
        signature["adjacency_expansion_stop"] = _adjacency_expansion_stop(
            signature,
            is_certified_seed=signature["source_face_id"] in certified_seed_ids,
            outer_radius=outer_radius,
        )
    expansion = _expand_authenticated_periodic_seed_components(
        signatures,
        source_manifest.get("adjacency", {}),
        rotational_group_by_face_id,
        certified_seed_ids,
        outer_radius,
    )
    periodic_ids = set(expansion["periodic_face_ids"])
    expanded_membership_by_face_id = expansion.pop("membership_by_face_id")

    for signature in signatures:
        face_id = signature["source_face_id"]
        group = rotational_group_by_face_id.get(face_id)
        topology_support = component_evidence_by_face_id.get(face_id)
        seed_certification = signature.get("periodic_seed_certification")
        expanded_membership = expanded_membership_by_face_id.get(face_id)
        is_periodic_blade_face = face_id in periodic_ids
        rotational_repetition_detected = group is not None
        signature["is_periodic"] = is_periodic_blade_face
        signature["blade_related"] = is_periodic_blade_face
        signature["rotational_repetition_detected"] = (
            rotational_repetition_detected
        )
        if is_periodic_blade_face:
            membership_status = "accepted_periodic_blade_related"
        elif (
            seed_certification is not None
            and seed_certification["classification"]
            == "analytic_auxiliary_hole_population"
        ):
            membership_status = "rejected_periodic_auxiliary_hole_feature"
        elif (
            topology_support is not None
            and topology_support["classification"]
            == "auxiliary_hole_like_subtractive_feature"
        ):
            membership_status = "rejected_periodic_auxiliary_hole_feature"
        elif rotational_repetition_detected:
            membership_status = "rejected_rotational_group_without_blade_topology_support"
        else:
            membership_status = "rejected_by_coarse_periodic_partition"
        signature["periodic_membership"] = {
            "status": membership_status,
            "group_id": (
                expanded_membership["source_component_id"]
                if expanded_membership is not None
                else None
            ),
            "closure_within_tolerance": is_periodic_blade_face,
            "angular_closure_residual_deg": (
                None
                if expanded_membership is None
                else expanded_membership["angular_closure_residual_deg"]
            ),
            "method": "authenticated_seed_exact_adjacency_expansion_r4",
            "rotational_group_id": None if group is None else group["group_id"],
            "rotational_closure_within_tolerance": bool(group is not None),
            "blade_topology_support": topology_support,
            "periodic_seed_certification": seed_certification,
            "exact_source_adjacency_expansion": expanded_membership,
        }

    rotational_groups.sort(
        key=lambda item: (
            -item["count"],
            item["signature_hash"],
            tuple(item["member_face_ids"]),
        )
    )
    periodic_groups = [
        group
        for group in rotational_groups
        if set(group["member_face_ids"]) <= periodic_ids
    ]
    rejected_rotational_groups = [
        group
        for group in rotational_groups
        if not set(group["member_face_ids"]) <= periodic_ids
    ]
    all_face_ids = {record["face_id"] for record in source_records}
    nonperiodic_ids = all_face_ids - periodic_ids
    periodic_components = _connected_components(
        periodic_ids,
        source_manifest.get("adjacency", {}),
        signatures,
        classification="periodic_blade_related",
    )
    expansion_by_faces = {
        frozenset(item["source_face_ids"]): item
        for item in expansion["accepted_components"]
    }
    for component in periodic_components:
        expansion_record = expansion_by_faces.get(frozenset(component["face_ids"]))
        if expansion_record is None:
            continue
        component["seed_rotational_group_ids"] = list(
            expansion_record["seed_rotational_group_ids"]
        )
        component["authenticated_population_count"] = int(
            expansion_record["population_count"]
        )
    nonperiodic_components = _connected_components(
        nonperiodic_ids,
        source_manifest.get("adjacency", {}),
        signatures,
        classification="nonperiodic_material_or_local_feature",
    )
    component_by_face_id = {
        face_id: component
        for component in [*periodic_components, *nonperiodic_components]
        for face_id in component["face_ids"]
    }
    for signature in signatures:
        component = component_by_face_id[signature["source_face_id"]]
        signature["coarse_component"] = {
            "source_component_id": component["component_id"],
            "source_entity_ids": list(component["source_entity_ids"]),
            "confidence": dict(component["confidence"]),
            "coordinate_frame": component["coordinate_frame"],
            "units": dict(component["units"]),
            "tolerance": dict(component["tolerance"]),
            "residual": dict(component["residual"]),
            "provenance": dict(component["provenance"]),
            **(
                {
                    "component_completeness": dict(
                        component["component_completeness"]
                    )
                }
                if "component_completeness" in component
                else {}
            ),
            **(
                {
                    "seed_rotational_group_ids": list(
                        component["seed_rotational_group_ids"]
                    ),
                    "authenticated_population_count": int(
                        component["authenticated_population_count"]
                    ),
                }
                if "seed_rotational_group_ids" in component
                else {}
            ),
        }
    ordered_signatures = sorted(signatures, key=lambda item: item["source_face_id"])
    return {
        "method": "coarse_axis_rotation_face_signatures_r3",
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "tolerance": {
            "area_relative": 0.001,
            "linear_mm": round(max(0.02, outer_radius * 0.0004), 6),
            "angular_closure_deg": 0.15,
        },
        "sampling_budget": sampling_budget.evidence(),
        "face_signatures": ordered_signatures,
        "periodic_signature_groups": periodic_groups,
        "rotational_signature_groups": rotational_groups,
        "rejected_rotational_signature_groups": rejected_rotational_groups,
        "periodic_component_expansion": expansion,
        "periodic_face_ids": sorted(periodic_ids),
        "nonperiodic_face_ids": sorted(nonperiodic_ids),
        "periodic_components": periodic_components,
        "nonperiodic_components": nonperiodic_components,
        "invariants": {
            "source_face_count": len(all_face_ids),
            "periodic_face_count": len(periodic_ids),
            "nonperiodic_face_count": len(nonperiodic_ids),
            "all_source_faces_accounted_for": periodic_ids.isdisjoint(nonperiodic_ids)
            and periodic_ids | nonperiodic_ids == all_face_ids,
        },
    }


def compute_face_signatures(
    shape, source_manifest: dict[str, Any], frame: dict[str, Any]
) -> list[dict[str, Any]]:
    return coarse_periodic_face_partition(shape, source_manifest, frame)[
        "face_signatures"
    ]


def _extract_axis_candidates(shape) -> list[dict[str, Any]]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        raise AxisConsensusError(
            "v116_axis_consensus_failed", "OCP analytic adaptors are unavailable"
        ) from exc

    candidates: list[dict[str, Any]] = []
    for index, face in enumerate(shape.Faces()):
        geometry_type = face.geomType()
        if geometry_type not in {"CYLINDER", "CONE", "TORUS", "REVOLUTION"}:
            continue
        try:
            adaptor = BRepAdaptor_Surface(face.wrapped)
            surface = {
                "CYLINDER": adaptor.Cylinder,
                "CONE": adaptor.Cone,
                "TORUS": adaptor.Torus,
            }.get(geometry_type)
            axis = adaptor.AxeOfRevolution() if surface is None else surface().Axis()
            radius = (
                float(adaptor.Cylinder().Radius())
                if geometry_type == "CYLINDER"
                else None
            )
            candidates.append(
                _candidate_record(
                    source_entity_id=f"source_face_{index:05d}",
                    source_kind="face",
                    geometry_type=geometry_type,
                    axis=axis,
                    analytic_area_mm2=float(face.Area()),
                    radius_mm=radius,
                )
            )
        except Exception:
            continue
    for index, edge in enumerate(shape.Edges()):
        if edge.geomType() != "CIRCLE":
            continue
        try:
            circle = BRepAdaptor_Curve(edge.wrapped).Circle()
            candidates.append(
                _candidate_record(
                    source_entity_id=f"source_edge_{index:05d}",
                    source_kind="edge",
                    geometry_type="CIRCLE",
                    axis=circle.Axis(),
                    analytic_area_mm2=0.0,
                    radius_mm=float(circle.Radius()),
                )
            )
        except Exception:
            continue
    return candidates


def _candidate_record(
    *,
    source_entity_id: str,
    source_kind: str,
    geometry_type: str,
    axis,
    analytic_area_mm2: float,
    radius_mm: float | None,
) -> dict[str, Any]:
    direction = np.asarray(
        [axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()],
        dtype=float,
    )
    direction /= max(float(np.linalg.norm(direction)), 1.0e-15)
    location = np.asarray(
        [axis.Location().X(), axis.Location().Y(), axis.Location().Z()], dtype=float
    )
    line_origin = location - direction * float(np.dot(location, direction))
    return {
        "source_entity_id": source_entity_id,
        "source_kind": source_kind,
        "geometry_type": geometry_type,
        "line_origin": line_origin,
        "line_direction": direction,
        "analytic_area_mm2": analytic_area_mm2,
        "radius_mm": radius_mm,
    }


def _cluster_axis_candidates(
    candidates: list[dict[str, Any]],
    *,
    line_tolerance_mm: float,
    angular_tolerance_deg: float,
) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            tuple(_canonical_line_direction(item["line_direction"])),
            tuple(np.round(item["line_origin"], 9)),
            item["source_entity_id"],
        ),
    )
    clusters: list[dict[str, Any]] = []
    for candidate in ordered:
        matching = [
            cluster
            for cluster in clusters
            if _axis_angle_deg(candidate["line_direction"], cluster["line_direction"])
            <= angular_tolerance_deg
            and _line_distance(
                candidate["line_origin"],
                candidate["line_direction"],
                cluster["line_origin"],
                cluster["line_direction"],
            )
            <= line_tolerance_mm
        ]
        if matching:
            cluster = min(matching, key=lambda item: tuple(item["source_entity_ids"]))
            cluster["members"].append(candidate)
            _refresh_cluster(cluster)
        else:
            cluster = {"members": [candidate]}
            _refresh_cluster(cluster)
            clusters.append(cluster)
    for cluster in clusters:
        cluster["clustering_tolerance"] = {
            "line_distance_mm": round(float(line_tolerance_mm), 9),
            "angular_deg": round(float(angular_tolerance_deg), 9),
        }
    return clusters


def _refresh_cluster(cluster: dict[str, Any]) -> None:
    members = cluster["members"]
    reference = _canonical_line_direction(members[0]["line_direction"])
    directions = []
    origins = []
    for member in members:
        direction = np.asarray(member["line_direction"], dtype=float)
        if float(np.dot(direction, reference)) < 0.0:
            direction = -direction
        directions.append(direction)
        origins.append(np.asarray(member["line_origin"], dtype=float))
    direction = np.sum(directions, axis=0)
    direction /= max(float(np.linalg.norm(direction)), 1.0e-15)
    direction = _canonical_line_direction(direction)
    origin = np.mean(origins, axis=0)
    origin -= direction * float(np.dot(origin, direction))
    cluster.update(
        {
            "line_origin": origin,
            "line_direction": direction,
            "source_entity_ids": sorted(
                member["source_entity_id"] for member in members
            ),
            "analytic_area_mm2": float(
                sum(member["analytic_area_mm2"] for member in members)
            ),
            "analytic_feature_count": len(members),
        }
    )


def _periodic_closure_support(
    records: list[dict[str, Any]],
    origin: np.ndarray,
    direction: np.ndarray,
    line_tolerance_mm: float,
) -> float:
    basis_x, basis_y = _transverse_basis(direction)
    raw: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    for record in records:
        point = np.asarray(record["centroid_mm"], dtype=float) - origin
        x = float(np.dot(point, basis_x))
        y = float(np.dot(point, basis_y))
        radius = math.hypot(x, y)
        if radius <= line_tolerance_mm * 2.0:
            continue
        area = max(float(record["area_mm2"]), 1.0e-9)
        area_bucket = int(round(math.log(area) / math.log(1.001)))
        raw[(record["geometry_type"], area_bucket)].append((math.atan2(y, x), area))
    support = 0.0
    for values in raw.values():
        if len(values) < 3:
            continue
        angles = sorted(angle % (2.0 * math.pi) for angle, _area in values)
        gaps = np.diff([*angles, angles[0] + 2.0 * math.pi])
        expected = 2.0 * math.pi / len(values)
        error = float(np.max(np.abs(gaps - expected)))
        quality = max(0.0, 1.0 - error / max(expected * 0.08, math.radians(0.15)))
        if quality > 0.0:
            support += (
                quality
                * len(values)
                * math.sqrt(float(np.mean([area for _angle, area in values])))
            )
    return support


def _score_axis_clusters(clusters: list[dict[str, Any]]) -> None:
    max_area = max((item["analytic_area_mm2"] for item in clusters), default=1.0) or 1.0
    max_count = (
        max((item["analytic_feature_count"] for item in clusters), default=1) or 1
    )
    max_periodic = max(
        (item["periodic_closure_support"] for item in clusters), default=0.0
    )
    for cluster in clusters:
        area_score = cluster["analytic_area_mm2"] / max_area
        feature_score = cluster["analytic_feature_count"] / max_count
        periodic_score = (
            cluster["periodic_closure_support"] / max_periodic
            if max_periodic > 0.0
            else 0.0
        )
        cluster["score_components"] = {
            "analytic_area_mm2": round(cluster["analytic_area_mm2"], 6),
            "analytic_feature_count": cluster["analytic_feature_count"],
            "periodic_closure_support": round(cluster["periodic_closure_support"], 6),
            "normalized_analytic_area": round(area_score, 9),
            "normalized_feature_count": round(feature_score, 9),
            "normalized_periodic_closure": round(periodic_score, 9),
        }
        cluster["combined_score"] = (
            0.55 * area_score + 0.25 * feature_score + 0.20 * periodic_score
        )


def _clusters_are_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    area_ratio = _symmetric_ratio(
        first["analytic_area_mm2"], second["analytic_area_mm2"]
    )
    count_ratio = _symmetric_ratio(
        first["analytic_feature_count"], second["analytic_feature_count"]
    )
    periodic_ratio = _symmetric_ratio(
        first["periodic_closure_support"], second["periodic_closure_support"]
    )
    return (
        abs(first["combined_score"] - second["combined_score"]) <= 0.035
        and area_ratio >= 0.9
        and count_ratio >= 0.8
        and (
            periodic_ratio >= 0.8
            or max(
                first["periodic_closure_support"], second["periodic_closure_support"]
            )
            == 0.0
        )
    )


def _resolve_axis_direction(
    shape, line_origin: np.ndarray, direction: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    support_score = _analytic_support_endpoint_axis_score(
        shape, line_origin, direction
    )
    if support_score is not None:
        resolved = direction if support_score > 0.0 else -direction
        return resolved, {
            "method": (
                "small_radius_eye_positive_z_from_authenticated_support_endpoint_evidence"
            ),
            "normalized_moment": round(abs(support_score), 12),
            "signed_normalized_moment": round(abs(support_score), 12),
            "canonical_positive_z_role": "large_radius_backplate_to_small_radius_eye",
        }
    vertices = np.asarray(
        [vertex.Center().toTuple() for vertex in shape.Vertices()], dtype=float
    )
    relative = vertices - line_origin
    axial = relative @ direction
    radial = np.linalg.norm(relative - np.outer(axial, direction), axis=1)
    midpoint = 0.5 * (float(np.min(axial)) + float(np.max(axial)))
    axial_span = float(np.ptp(axial))
    weights = np.square(radial)
    if axial_span <= 1.0e-12 or float(np.sum(weights)) <= 1.0e-12:
        raise AxisConsensusError(
            "v116_axis_direction_semantics_ambiguous",
            "source geometry does not contain enough radial/axial asymmetry to orient canonical +Z",
            {"canonical_positive_z_role": "large_radius_backplate_to_small_radius_eye"},
        )

    order = np.argsort(axial, kind="stable")
    ordered_weights = weights[order]
    cumulative = np.cumsum(ordered_weights)
    weighted_median = float(
        axial[order][np.searchsorted(cumulative, 0.5 * float(cumulative[-1]))]
    )
    signed_asymmetry = (midpoint - weighted_median) / axial_span
    if abs(signed_asymmetry) <= 1.0e-10:
        raise AxisConsensusError(
            "v116_axis_direction_semantics_ambiguous",
            "radial-weighted source evidence cannot distinguish the eye from the backplate",
            {
                "normalized_moment": round(abs(signed_asymmetry), 12),
                "canonical_positive_z_role": (
                    "large_radius_backplate_to_small_radius_eye"
                ),
            },
        )
    resolved = direction if signed_asymmetry > 0.0 else -direction
    return resolved, {
        "method": (
            "small_radius_eye_positive_z_from_radial_weighted_axial_asymmetry"
        ),
        "normalized_moment": round(abs(signed_asymmetry), 12),
        "signed_normalized_moment": round(abs(signed_asymmetry), 12),
        "canonical_positive_z_role": "large_radius_backplate_to_small_radius_eye",
    }


def _analytic_support_endpoint_axis_score(
    shape, line_origin: np.ndarray, direction: np.ndarray
) -> float | None:
    candidates = []
    for face in shape.Faces():
        if face.geomType() != "CONE":
            continue
        vertices = np.asarray(
            [vertex.Center().toTuple() for vertex in face.Vertices()], dtype=float
        )
        if len(vertices) < 2:
            continue
        relative = vertices - line_origin
        axial = relative @ direction
        radial = np.linalg.norm(relative - np.outer(axial, direction), axis=1)
        radial_span = float(np.ptp(radial))
        axial_span = float(np.ptp(axial))
        if radial_span <= 1.0e-8 or axial_span <= 1.0e-8:
            continue
        threshold = max(1.0e-8, 0.1 * radial_span)
        small = axial[radial <= float(np.min(radial)) + threshold]
        large = axial[radial >= float(np.max(radial)) - threshold]
        if not len(small) or not len(large):
            continue
        score = (float(np.median(small)) - float(np.median(large))) / axial_span
        if abs(score) <= 1.0e-10:
            continue
        candidates.append((float(face.Area()) * radial_span, score))
    if not candidates:
        return None
    candidates.sort(key=lambda item: -item[0])
    return float(candidates[0][1])


def _cluster_residual(cluster: dict[str, Any]) -> dict[str, float]:
    origin = np.asarray(cluster["line_origin"], dtype=float)
    direction = np.asarray(cluster["line_direction"], dtype=float)
    line_values = []
    angular_values = []
    for member in cluster["members"]:
        line_values.append(
            _line_distance(
                origin, direction, member["line_origin"], member["line_direction"]
            )
        )
        angular_values.append(_axis_angle_deg(direction, member["line_direction"]))
    return {
        "line_rms_mm": round(float(np.sqrt(np.mean(np.square(line_values)))), 9),
        "line_max_mm": round(float(np.max(line_values)), 9),
        "angular_spread_deg": round(float(np.max(angular_values)), 9),
    }


def _public_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    source_ids = sorted(cluster["source_entity_ids"])
    score = round(float(cluster.get("combined_score", 0.0)), 9)
    return {
        "score": score,
        "score_components": cluster.get("score_components", {}),
        "confidence": {
            "level": "ranked_analytic_consensus_candidate",
            "combined_score": score,
            "independent_score_components": True,
        },
        "coordinate_frame": "source_cartesian_mm",
        "units": {"linear": "mm", "angular": "deg", "area": "mm2"},
        "tolerance": cluster.get(
            "clustering_tolerance",
            {
                "line_distance_mm": MIN_AXIS_LINE_TOLERANCE_MM,
                "angular_deg": AXIS_ANGULAR_TOLERANCE_DEG,
            },
        ),
        "source_entity_ids": source_ids,
        "face_ids": [
            source_id
            for source_id in source_ids
            if source_id.startswith("source_face_")
        ],
        "edge_ids": [
            source_id
            for source_id in source_ids
            if source_id.startswith("source_edge_")
        ],
        "face_count": sum(
            source_id.startswith("source_face_") for source_id in source_ids
        ),
        "line_origin_mm": _round_vector(cluster["line_origin"], 8),
        "line_direction": _round_vector(cluster["line_direction"], 10),
        "residual": _cluster_residual(cluster),
        "provenance": {
            "authority": "uploaded_step_brep",
            "source_entity_ids": source_ids,
            "candidate_method": "analytic_surface_and_circular_edge_axis_extraction",
        },
    }


def _coaxial_bore_radius(cluster: dict[str, Any], outer_radius: float) -> float | None:
    groups: dict[float, float] = defaultdict(float)
    for member in cluster["members"]:
        radius = member.get("radius_mm")
        if (
            member["source_kind"] != "face"
            or member["geometry_type"] != "CYLINDER"
            or radius is None
        ):
            continue
        if 0.0 < radius < outer_radius * 0.6:
            groups[round(float(radius), 6)] += float(member["analytic_area_mm2"])
    return round(max(groups, key=groups.get), 6) if groups else None


def _face_signature(
    face,
    record: dict[str, Any],
    matrix: np.ndarray,
    adjacency: dict[str, list[str]],
    *,
    sampling_budget: _SamplingBudget | None = None,
    phase_frame_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    center = _transform_point(record["centroid_mm"], matrix)
    try:
        if _defer_complex_bspline_interior_extrema(face, record):
            raise AxisConsensusError(
                "v116_coarse_signature_complex_surface_deferred",
                "complex B-spline interior extrema are deferred to exact representative recovery",
                {
                    "source_face_id": record["face_id"],
                    "geometry_type": record["geometry_type"],
                    "area_mm2": float(record["area_mm2"]),
                },
            )
        (
            source_points,
            extent_source_points,
            normal_points,
            source_normals,
            sampling_evidence,
        ) = _sample_trimmed_face_material_domain(
            face,
            canonical_matrix=matrix,
            source_face_id=record["face_id"],
            sampling_budget=sampling_budget,
        )
    except AxisConsensusError as exc:
        if exc.reason not in {
            "v116_coarse_signature_complex_surface_deferred",
            "v116_source_sampling_extrema_not_converged",
            "v116_source_sampling_budget_exceeded",
        }:
            raise
        (
            source_points,
            extent_source_points,
            normal_points,
            source_normals,
            sampling_evidence,
        ) = _sample_exact_trim_boundary_fallback(
            face,
            source_face_id=record["face_id"],
            source_centroid_mm=record["centroid_mm"],
            failure=exc,
            sampling_budget=sampling_budget,
        )
    canonical_points = _transform_points(source_points, matrix)
    canonical_extent_points = _transform_points(extent_source_points, matrix)
    radii = np.linalg.norm(canonical_extent_points[:, :2], axis=1)
    z_values = canonical_extent_points[:, 2]
    radial_bounds = [
        _quantize(float(np.min(radii)), 3),
        _quantize(float(np.max(radii)), 3),
    ]
    axial_bounds = [
        _quantize(float(np.min(z_values)), 3),
        _quantize(float(np.max(z_values)), 3),
    ]
    center_radius = math.hypot(center[0], center[1])
    canonical_phase_deg = _quantize(
        math.degrees(math.atan2(center[1], center[0])) % 360.0, 9
    )
    phase_frame_evidence = dict(phase_frame_evidence or {})
    source_origin = phase_frame_evidence.get("source_axis_origin_mm", [0.0, 0.0, 0.0])
    source_frame_phase_deg = _quantize(
        math.degrees(
            math.atan2(
                float(record["centroid_mm"][1]) - float(source_origin[1]),
                float(record["centroid_mm"][0]) - float(source_origin[0]),
            )
        )
        % 360.0,
        9,
    )
    rotational_surface_authority = _rotational_bspline_surface_authority(
        face,
        matrix=matrix,
        canonical_phase_deg=canonical_phase_deg,
    )
    sampling_evidence["rotational_surface_authority"] = (
        rotational_surface_authority
    )
    exact_trim_source_points = np.asarray(
        sampling_evidence.pop("exact_trim_boundary_samples_source_mm", source_points),
        dtype=float,
    )
    canonical_trim_boundary_samples = sorted(
        {
            tuple(_round_vector(point, 6))
            for point in _transform_points(exact_trim_source_points, matrix)
        }
    )
    if sampling_evidence["u_periodic"] and center_radius <= 1.0e-6:
        angular_evidence = {
            "angular_span_deg": 360.0,
            "angular_span_evidence": {
                "method": "full_periodic_trimmed_surface_about_consensus_axis",
                "start_angle_deg": 0.0,
                "end_angle_deg": 0.0,
                "sample_count": len(canonical_extent_points),
            },
            "wrap_deg": 0.0,
            "wrap_evidence": {
                "method": "coaxial_full_periodic_surface",
                "inner_sample_angle_deg": 0.0,
                "outer_sample_angle_deg": 0.0,
                "radial_extent_mm": round(float(np.ptp(radii)), 6),
            },
        }
    else:
        angular_evidence = _canonical_face_angular_evidence(
            canonical_extent_points
        )
    canonical_surface_samples = sorted(
        {tuple(_round_vector(point, 6)) for point in canonical_points}
    )
    if record["geometry_type"] == "PLANE":
        normal_points = np.asarray([record["centroid_mm"]], dtype=float)
        source_normals = np.asarray([_face_normal(face, np.eye(4))], dtype=float)
    normal_distribution = _canonical_normal_distribution(
        normal_points, source_normals, matrix
    )
    core = {
        "geometry_type": record["geometry_type"],
        "area_mm2": _quantize(float(record["area_mm2"]), 3),
        "centroid_rz_mm": [_quantize(center_radius, 3), _quantize(float(center[2]), 3)],
        "r_bounds_mm": radial_bounds,
        "z_bounds_mm": axial_bounds,
        "normal_distribution_rtz": normal_distribution,
        "adjacency_degree": len(adjacency.get(record["face_id"], [])),
        "edge_count": len(face.Edges()),
        "vertex_count": len(face.Vertices()),
    }
    signature_hash = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "source_face_id": record["face_id"],
        "source_entity_ids": [record["face_id"]],
        "method": "coarse_axis_rotation_face_signature_r3",
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm", "area": "mm2", "angular": "deg"},
        "tolerance": {
            "linear_quantization_mm": 0.001,
            "area_quantization_mm2": 0.001,
            "angular_sample_quantization_deg": 0.00001,
            "normal_component_quantization": 0.00001,
        },
        "confidence": {
            "level": "coarse_signature_evidence",
            "semantic_role_assigned": False,
        },
        "sampling_evidence": sampling_evidence,
        "residual": {"transformed_sample_mm": None},
        **core,
        "centroid_angle_deg": canonical_phase_deg,
        "source_frame_phase_deg": source_frame_phase_deg,
        "canonical_frame_phase_deg": canonical_phase_deg,
        "phase_frame_evidence": phase_frame_evidence,
        "canonical_surface_samples_mm": [
            list(point) for point in canonical_surface_samples
        ],
        "canonical_trim_boundary_samples_mm": [
            list(point) for point in canonical_trim_boundary_samples
        ],
        "streamwise_bounds_mm": list(radial_bounds),
        "streamwise_coordinate": "canonical_radius_mm",
        "radial_bounds_mm": list(radial_bounds),
        "axial_bounds_mm": list(axial_bounds),
        "angular_span_deg": angular_evidence["angular_span_deg"],
        "angular_span_evidence": angular_evidence["angular_span_evidence"],
        "wrap_deg": angular_evidence["wrap_deg"],
        "wrap_evidence": angular_evidence["wrap_evidence"],
        "signature_hash": signature_hash,
        "transformed_sample_residual_mm": None,
    }


def _defer_complex_bspline_interior_extrema(
    face, record: dict[str, Any]
) -> bool:
    if record.get("geometry_type") != "BSPLINE":
        return False
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        surface = BRepAdaptor_Surface(face.wrapped).BSpline()
        knot_complexity = int(surface.NbUKnots()) * int(surface.NbVKnots())
    except Exception:
        knot_complexity = 0
    return float(record.get("area_mm2", 0.0)) > 5.0 or knot_complexity > 24


def _rotational_bspline_surface_authority(
    face,
    *,
    matrix: np.ndarray,
    canonical_phase_deg: float,
) -> dict[str, Any] | None:
    if face.geomType() != "BSPLINE":
        return None
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        surface = BRepAdaptor_Surface(face.wrapped).BSpline()
        cosine = math.cos(math.radians(-canonical_phase_deg))
        sine = math.sin(math.radians(-canonical_phase_deg))
        control_records = []
        for u_index in range(1, surface.NbUPoles() + 1):
            for v_index in range(1, surface.NbVPoles() + 1):
                point = _transform_point(surface.Pole(u_index, v_index).Coord(), matrix)
                local_x = cosine * point[0] - sine * point[1]
                local_y = sine * point[0] + cosine * point[1]
                control_records.append(
                    (
                        int(u_index),
                        int(v_index),
                        _quantize(float(local_x), 5),
                        _quantize(float(local_y), 5),
                        _quantize(float(point[2]), 5),
                        _quantize(float(surface.Weight(u_index, v_index)), 9),
                    )
                )
        raw_u_knots = [
            float(surface.UKnot(index))
            for index in range(1, surface.NbUKnots() + 1)
        ]
        raw_v_knots = [
            float(surface.VKnot(index))
            for index in range(1, surface.NbVKnots() + 1)
        ]

        def normalized_knots(values: list[float]) -> list[float]:
            span = values[-1] - values[0]
            if abs(span) <= 1.0e-15:
                return [0.0 for _ in values]
            return [
                _quantize((value - values[0]) / span, 10) for value in values
            ]

        payload = {
            "u_degree": int(surface.UDegree()),
            "v_degree": int(surface.VDegree()),
            "u_periodic": bool(surface.IsUPeriodic()),
            "v_periodic": bool(surface.IsVPeriodic()),
            "u_knots": normalized_knots(raw_u_knots),
            "v_knots": normalized_knots(raw_v_knots),
            "u_multiplicities": [
                int(surface.UMultiplicity(index))
                for index in range(1, surface.NbUKnots() + 1)
            ],
            "v_multiplicities": [
                int(surface.VMultiplicity(index))
                for index in range(1, surface.NbVKnots() + 1)
            ],
            "control_lattice_shape": [
                int(surface.NbUPoles()),
                int(surface.NbVPoles()),
            ],
            "control_records_uv_local_xyz_weight": control_records,
            "knot_normalization": {
                "method": "affine_normalization_to_unit_interval",
                "u_transform": "(u-u_min)/(u_max-u_min)",
                "v_transform": "(v-v_min)/(v_max-v_min)",
            },
        }
    except Exception:
        return None
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return {
        "status": "PASS",
        "method": "exact_rotationally_normalized_step_bspline_control_net",
        "coordinate_frame": "canonical_cartesian_rotated_to_face_centroid_phase",
        "units": {"linear": "mm", "angular": "deg", "weight": "unitless"},
        "tolerance": {
            "control_point_quantization_mm": 1.0e-5,
            "knot_parameterization": "affine_normalized_0_to_1",
            "knot_quantization": 1.0e-10,
            "weight_quantization": 1.0e-9,
        },
        "parameterization_transform": "identity",
        "fingerprint_sha256": hashlib.sha256(encoded).hexdigest(),
        "control_point_count": len(payload["control_records_uv_local_xyz_weight"]),
        "comparison_payload": payload,
    }


def _sample_exact_trim_boundary_fallback(
    face,
    *,
    source_face_id: str,
    source_centroid_mm: list[float],
    failure: AxisConsensusError,
    sampling_budget: _SamplingBudget | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface

    boundary_points: list[list[float]] = []
    for edge in face.Edges():
        curve = BRepAdaptor_Curve(edge.wrapped)
        first = float(curve.FirstParameter())
        last = float(curve.LastParameter())
        if not np.all(np.isfinite([first, last])):
            continue
        sample_count = 129 if edge.geomType() in {"CIRCLE", "ELLIPSE"} else 65
        for parameter in np.linspace(first, last, sample_count):
            if sampling_budget is not None:
                sampling_budget.consume(1, source_face_id=source_face_id)
            point = curve.Value(float(parameter))
            boundary_points.append(
                [float(point.X()), float(point.Y()), float(point.Z())]
            )
    if not boundary_points:
        boundary_points = [
            [float(value) for value in vertex.Center().toTuple()]
            for vertex in face.Vertices()
        ]
    if not boundary_points:
        raise failure
    points = np.unique(np.asarray(boundary_points, dtype=float), axis=0)
    adaptor = BRepAdaptor_Surface(face.wrapped)
    normal_point = np.asarray([source_centroid_mm], dtype=float)
    normal = np.asarray([_face_normal(face, np.eye(4))], dtype=float)
    return (
        points,
        points,
        normal_point,
        normal,
        {
            "method": "exact_step_trim_boundary_fallback_after_uncertified_interior_extrema",
            "coordinate_frame": "source_cartesian_mm",
            "units": "mm",
            "u_periodic": bool(adaptor.IsUPeriodic()),
            "v_periodic": bool(adaptor.IsVPeriodic()),
            "independent_validation_status": "UNKNOWN",
            "material_control_bound_status": "UNKNOWN",
            "promotable": False,
            "fallback_reason": failure.reason,
            "failure_details": dict(failure.details),
            "exact_boundary_sample_count": len(points),
            "exact_trim_boundary_samples_source_mm": points.tolist(),
            "face_center_of_mass_used": False,
            "vertices_only": False,
        },
    )


def _sample_trimmed_face_material_domain(
    face,
    *,
    canonical_matrix: np.ndarray | None = None,
    source_face_id: str = "unknown_source_face",
    sampling_budget: _SamplingBudget | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
        from OCP.BRepClass import BRepClass_FaceClassifier
        from OCP.BRepTools import BRepTools
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
        from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec
    except ImportError as exc:  # pragma: no cover
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "OCP trimmed-face sampling support is unavailable",
        ) from exc

    adaptor = BRepAdaptor_Surface(face.wrapped)
    matrix = (
        np.eye(4, dtype=float)
        if canonical_matrix is None
        else np.asarray(canonical_matrix, dtype=float)
    )
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError("canonical_matrix must be a finite 4x4 rigid transform")
    u_min, u_max, v_min, v_max = (
        float(value) for value in BRepTools.UVBounds_s(face.wrapped)
    )
    if not np.all(np.isfinite([u_min, u_max, v_min, v_max])):
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "trimmed source face has an unbounded material parameter domain",
        )

    face_sample_count = 0

    def consume_sample() -> None:
        nonlocal face_sample_count
        face_sample_count += 1
        if face_sample_count > PER_FACE_SAMPLE_BUDGET:
            raise AxisConsensusError(
                "v116_source_sampling_budget_exceeded",
                "trimmed B-Rep face sampling exceeded its deterministic budget",
                {
                    "source_face_id": source_face_id,
                    "status": "EXCEEDED",
                    "maximum_samples": PER_FACE_SAMPLE_BUDGET,
                    "consumed_samples": face_sample_count,
                    "maximum_wall_seconds": PER_FACE_SAMPLE_WALL_SECONDS,
                    "wall_clock_budget_enforced": False,
                    "decision_basis": "deterministic_sample_count_only",
                    "promotable": False,
                },
            )
        if sampling_budget is not None:
            sampling_budget.consume(1, source_face_id=source_face_id)

    boundary_points: list[list[float]] = []
    dense_boundary_points: list[list[float]] = []
    for edge in face.Edges():
        curve = BRepAdaptor_Curve(edge.wrapped)
        first = float(curve.FirstParameter())
        last = float(curve.LastParameter())
        if not np.all(np.isfinite([first, last])):
            continue
        dense_count = 129 if edge.geomType() in {"CIRCLE", "ELLIPSE"} else 65
        dense_parameters = np.linspace(first, last, dense_count)
        dense_points = []
        for parameter in dense_parameters:
            consume_sample()
            point = curve.Value(float(parameter))
            dense_points.append([float(point.X()), float(point.Y()), float(point.Z())])
        dense = np.asarray(dense_points, dtype=float)
        dense_boundary_points.extend(dense.tolist())
        radii = np.linalg.norm(dense[:, :2], axis=1)
        selected_indices = {
            0,
            len(dense) - 1,
            int(np.argmin(radii)),
            int(np.argmax(radii)),
            int(np.argmin(dense[:, 2])),
            int(np.argmax(dense[:, 2])),
        }
        selected_indices.update(
            int(round(value))
            for value in np.linspace(0, len(dense) - 1, 7)
        )
        boundary_points.extend(dense[sorted(selected_indices)].tolist())

    convergence_tolerance_mm = 0.01
    maximum_refinement = 16
    surface_type = face.geomType()
    knot_evidence = _trimmed_surface_knot_evidence(
        adaptor,
        u_bounds=(u_min, u_max),
        v_bounds=(v_min, v_max),
        canonical_matrix=matrix,
    )
    u_breaks = knot_evidence["u_breaks"]
    v_breaks = knot_evidence["v_breaks"]
    boundary_uv_values = _surface_uv_values(adaptor, boundary_points)
    sample_levels: list[dict[str, Any]] = []
    previous_extrema: np.ndarray | None = (
        _canonical_rz_extrema(np.asarray(dense_boundary_points, dtype=float), matrix)
        if dense_boundary_points
        else None
    )
    material_samples: dict[tuple[float, float], tuple[list[float], list[float], bool]] = {}
    strict_interior_count = 0
    rejected_outside_uv_count = 0
    refinement_used = 0
    converged = False
    independent_extrema_delta = math.inf
    control_bound_gap = math.inf
    control_bounds: np.ndarray | None = None
    priority_refinement_evidence: dict[str, Any] | None = None
    priority_refinement_ready = False

    def evaluate_uv(u_value: float, v_value: float):
        key = (round(float(u_value), 14), round(float(v_value), 14))
        cached = material_samples.get(key)
        if cached is not None:
            return cached
        consume_sample()
        classifier = BRepClass_FaceClassifier(
            face.wrapped,
            gp_Pnt2d(float(u_value), float(v_value)),
            1.0e-9,
        )
        state = classifier.State()
        if state not in {TopAbs_IN, TopAbs_ON}:
            material_samples[key] = ([], [], False)
            return material_samples[key]
        point = adaptor.Value(float(u_value), float(v_value))
        try:
            derivative_point = gp_Pnt()
            derivative_u = gp_Vec()
            derivative_v = gp_Vec()
            adaptor.D1(
                float(u_value),
                float(v_value),
                derivative_point,
                derivative_u,
                derivative_v,
            )
            normal = np.cross(
                [derivative_u.X(), derivative_u.Y(), derivative_u.Z()],
                [derivative_v.X(), derivative_v.Y(), derivative_v.Z()],
            )
            normal /= max(float(np.linalg.norm(normal)), 1.0e-15)
        except Exception:
            normal = np.zeros(3, dtype=float)
        if face.wrapped.Orientation() == TopAbs_REVERSED:
            normal = -normal
        material_samples[key] = (
            [float(point.X()), float(point.Y()), float(point.Z())],
            normal.tolist(),
            state == TopAbs_IN,
        )
        return material_samples[key]

    for refinement in (1, 2, 4, 8, maximum_refinement):
        refinement_used = refinement
        primary_u = _span_lattice(u_breaks, refinement, phase=0.0)
        primary_v = _span_lattice(v_breaks, refinement, phase=0.0)
        validation_u = _span_lattice(u_breaks, refinement, phase=0.38196601125)
        validation_v = _span_lattice(v_breaks, refinement, phase=0.61803398875)
        primary_points: list[list[float]] = []
        validation_points: list[list[float]] = []
        level_rejected = 0
        for target, u_values, v_values in (
            (primary_points, primary_u, primary_v),
            (validation_points, validation_u, validation_v),
        ):
            for u_value in u_values:
                for v_value in v_values:
                    point, _, _ = evaluate_uv(u_value, v_value)
                    if not point:
                        level_rejected += 1
                        continue
                    target.append(point)
        if not primary_points or not validation_points:
            sample_levels.append(
                {
                    "density": max(len(primary_u), len(primary_v)),
                    "refinement_per_knot_span": refinement,
                    "primary_material_uv_count": len(primary_points),
                    "independent_validation_uv_count": len(validation_points),
                    "rejected_outside_uv_count": level_rejected,
                    "extrema_change_mm": None,
                    "independent_extrema_delta_mm": None,
                }
            )
            continue
        primary_extent = np.asarray([*primary_points, *dense_boundary_points])
        validation_extent = np.asarray([*validation_points, *dense_boundary_points])
        primary_extrema = _canonical_rz_extrema(primary_extent, matrix)
        validation_extrema = _canonical_rz_extrema(validation_extent, matrix)
        extrema = np.minimum(primary_extrema, validation_extrema)
        extrema[[1, 3]] = np.maximum(primary_extrema, validation_extrema)[[1, 3]]
        independent_extrema_delta = float(
            np.max(np.abs(primary_extrema - validation_extrema))
        )
        control_bounds = _material_domain_control_bounds(
            adaptor,
            u_breaks=u_breaks,
            v_breaks=v_breaks,
            refinement=refinement,
            evaluate_uv=evaluate_uv,
            boundary_uv_values=boundary_uv_values,
            canonical_matrix=matrix,
            consume_branch=consume_sample,
            sampled_extrema=extrema,
            tolerance_mm=convergence_tolerance_mm,
        )
        control_bound_gap = (
            0.0
            if control_bounds is None
            and knot_evidence["control_net_canonical_rz_bounds_mm"] is None
            else (
                math.inf
                if control_bounds is None
                else _control_bound_gap_mm(extrema, control_bounds)
            )
        )
        extrema_change = (
            None
            if previous_extrema is None
            else float(np.max(np.abs(extrema - previous_extrema)))
        )
        sample_levels.append(
            {
                "density": max(len(primary_u), len(primary_v)),
                "refinement_per_knot_span": refinement,
                "primary_material_uv_count": len(primary_points),
                "independent_validation_uv_count": len(validation_points),
                "rejected_outside_uv_count": level_rejected,
                "canonical_rz_extrema_mm": [round(float(item), 9) for item in extrema],
                "extrema_change_mm": None if extrema_change is None else round(extrema_change, 9),
                "independent_extrema_delta_mm": round(independent_extrema_delta, 9),
                "material_control_bounds_canonical_rz_mm": (
                    None
                    if control_bounds is None
                    else [round(float(item), 9) for item in control_bounds]
                ),
                "material_control_bound_gap_mm": (
                    None
                    if not math.isfinite(control_bound_gap)
                    else round(control_bound_gap, 9)
                ),
            }
        )
        rejected_outside_uv_count += level_rejected
        minimum_refinement = 2 if surface_type in {"BSPLINE", "BEZIER"} else 1
        stable_sample_extrema = (
            refinement >= minimum_refinement
            and extrema_change is not None
            and extrema_change <= convergence_tolerance_mm
            and independent_extrema_delta <= convergence_tolerance_mm
        )
        if stable_sample_extrema:
            if control_bound_gap <= convergence_tolerance_mm:
                converged = True
                break
            if surface_type == "BSPLINE":
                priority_refinement_ready = True
                break
        previous_extrema = extrema

    if (
        not converged
        and surface_type == "BSPLINE"
        and (
            priority_refinement_ready
            or (
                independent_extrema_delta <= convergence_tolerance_mm
                and sample_levels
                and sample_levels[-1].get("extrema_change_mm") is not None
                and float(sample_levels[-1]["extrema_change_mm"])
                <= convergence_tolerance_mm
            )
        )
    ):
        priority_refinement_evidence = _priority_refine_material_control_bounds(
            adaptor,
            u_breaks=u_breaks,
            v_breaks=v_breaks,
            evaluate_uv=evaluate_uv,
            material_samples=material_samples,
            boundary_points=dense_boundary_points,
            boundary_uv_values=boundary_uv_values,
            canonical_matrix=matrix,
            consume_branch=consume_sample,
            tolerance_mm=convergence_tolerance_mm,
            starting_depth=0,
            maximum_depth=MAXIMUM_CONTROL_REFINEMENT_DEPTH,
        )
        control_bounds = priority_refinement_evidence["control_bounds"]
        control_bound_gap = float(priority_refinement_evidence["control_bound_gap_mm"])
        refinement_used = int(priority_refinement_evidence["maximum_refinement"])
        sample_levels.append(
            {
                "mode": "priority_queue_local_knot_branch_subdivision",
                "density": refinement_used * max(len(u_breaks), len(v_breaks)),
                "refinement_per_knot_span": refinement_used,
                "canonical_rz_extrema_mm": priority_refinement_evidence[
                    "sampled_extrema_mm"
                ],
                "material_control_bounds_canonical_rz_mm": [
                    round(float(item), 9) for item in control_bounds
                ],
                "material_control_bound_gap_mm": round(control_bound_gap, 9),
                "priority_queue_iterations": priority_refinement_evidence[
                    "iterations"
                ],
                "refined_branch_count_by_depth": priority_refinement_evidence[
                    "refined_branch_count_by_depth"
                ],
            }
        )
        converged = bool(priority_refinement_evidence["converged"])

    accepted_samples = [value for value in material_samples.values() if value[0]]
    interior_points = [value[0] for value in accepted_samples]
    interior_normals = [value[1] for value in accepted_samples]
    strict_interior_count = sum(value[2] for value in accepted_samples)
    if not converged:
        raise AxisConsensusError(
            "v116_source_sampling_extrema_not_converged",
            "independent knot-span extrema validation did not converge",
            {
                "source_face_id": source_face_id,
                "sample_levels": sample_levels,
                "priority_refinement_evidence": priority_refinement_evidence,
                "convergence_tolerance_mm": convergence_tolerance_mm,
                "per_face_budget": {
                    "maximum_samples": PER_FACE_SAMPLE_BUDGET,
                    "consumed_samples": face_sample_count,
                    "maximum_wall_seconds": PER_FACE_SAMPLE_WALL_SECONDS,
                    "wall_clock_budget_enforced": False,
                    "decision_basis": "deterministic_sample_count_only",
                },
                "promotable": False,
            },
        )

    if not interior_points:
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "trimmed source face material domain produced no B-Rep surface samples",
        )
    representative_material_point = _representative_trimmed_material_point(
        face,
        adaptor,
        interior_points,
    )
    selected_indices = np.linspace(
        0, len(interior_points) - 1, min(len(interior_points), 257), dtype=int
    )
    sampled_interior_points = [interior_points[index] for index in selected_indices]
    sampled_interior_normals = [interior_normals[index] for index in selected_indices]
    all_points = np.asarray(
        [representative_material_point, *boundary_points, *sampled_interior_points],
        dtype=float,
    )
    extent_points = np.asarray(
        [representative_material_point, *interior_points, *dense_boundary_points],
        dtype=float,
    )
    unique_points = np.unique(np.round(all_points, decimals=12), axis=0)
    if len(unique_points) < 3:
        raise AxisConsensusError(
            "v116_axis_consensus_failed",
            "trimmed source face produced insufficient geometric samples",
        )
    return (
        unique_points,
        extent_points,
        np.asarray(sampled_interior_points, dtype=float),
        np.asarray(sampled_interior_normals, dtype=float),
        {
            "method": "knot_span_adaptive_trimmed_uv_with_independent_phase_validation",
            "coordinate_frame": "source_cartesian_mm",
            "units": "mm",
            "uv_bounds": [u_min, u_max, v_min, v_max],
            "refinement_per_knot_span": refinement_used,
            "uv_grid_density": sample_levels[-1]["density"],
            "sample_levels": sample_levels,
            "converged": converged,
            "independent_validation_status": "PASS",
            "independent_extrema_delta_mm": round(independent_extrema_delta, 9),
        "material_control_bound_status": "PASS",
        "promotable": True,
            "material_control_bound_gap_mm": round(control_bound_gap, 9),
            "convergence_tolerance_mm": convergence_tolerance_mm,
            "extrema_error_tolerance_mm": convergence_tolerance_mm,
            "maximum_refinement_per_knot_span": 2**MAXIMUM_CONTROL_REFINEMENT_DEPTH,
            "priority_refinement_evidence": priority_refinement_evidence,
            "knot_evidence": knot_evidence,
            "per_face_budget": {
                "status": "PASS",
                "maximum_samples": PER_FACE_SAMPLE_BUDGET,
                "consumed_samples": face_sample_count,
                "maximum_wall_seconds": PER_FACE_SAMPLE_WALL_SECONDS,
                "wall_clock_budget_enforced": False,
                "decision_basis": "deterministic_sample_count_only",
            },
            "rejected_outside_uv_count": rejected_outside_uv_count,
            "u_periodic": bool(adaptor.IsUPeriodic()),
            "v_periodic": bool(adaptor.IsVPeriodic()),
            "interior_material_sample_count": strict_interior_count,
            "material_or_boundary_uv_sample_count": len(interior_points),
            "emitted_interior_material_sample_count": len(sampled_interior_points),
            "exact_boundary_sample_count": len(boundary_points),
            "exact_trim_boundary_samples_source_mm": dense_boundary_points,
            "emitted_unique_sample_count": len(unique_points),
            "face_center_of_mass_used": False,
            "vertices_only": False,
            "classifier_tolerance": 1.0e-9,
        },
    )


def _span_lattice(
    breaks: list[float], refinement: int, *, phase: float
) -> list[float]:
    values = set(float(value) for value in breaks)
    for left, right in zip(breaks, breaks[1:]):
        if right <= left:
            continue
        if phase == 0.0:
            fractions = (index / refinement for index in range(refinement + 1))
        else:
            fractions = (
                (index + phase) / refinement for index in range(refinement)
            )
        values.update(left + (right - left) * fraction for fraction in fractions)
    return sorted(values)


def _trimmed_surface_knot_evidence(
    adaptor,
    *,
    u_bounds: tuple[float, float],
    v_bounds: tuple[float, float],
    canonical_matrix: np.ndarray,
) -> dict[str, Any]:
    u_breaks = [float(u_bounds[0]), float(u_bounds[1])]
    v_breaks = [float(v_bounds[0]), float(v_bounds[1])]
    evidence: dict[str, Any] = {
        "surface_type": str(adaptor.GetType()),
        "u_degree": None,
        "v_degree": None,
        "u_knots": [],
        "v_knots": [],
        "u_multiplicities": [],
        "v_multiplicities": [],
        "control_net_canonical_rz_bounds_mm": None,
    }
    try:
        surface = adaptor.BSpline()
        evidence["u_degree"] = int(surface.UDegree())
        evidence["v_degree"] = int(surface.VDegree())
        evidence["u_knots"] = [
            float(surface.UKnot(index)) for index in range(1, surface.NbUKnots() + 1)
        ]
        evidence["v_knots"] = [
            float(surface.VKnot(index)) for index in range(1, surface.NbVKnots() + 1)
        ]
        evidence["u_multiplicities"] = [
            int(surface.UMultiplicity(index))
            for index in range(1, surface.NbUKnots() + 1)
        ]
        evidence["v_multiplicities"] = [
            int(surface.VMultiplicity(index))
            for index in range(1, surface.NbVKnots() + 1)
        ]
        u_breaks.extend(evidence["u_knots"])
        v_breaks.extend(evidence["v_knots"])
        poles = np.asarray(
            [
                surface.Pole(u_index, v_index).Coord()
                for u_index in range(1, surface.NbUPoles() + 1)
                for v_index in range(1, surface.NbVPoles() + 1)
            ],
            dtype=float,
        )
        evidence["control_net_canonical_rz_bounds_mm"] = [
            round(float(value), 9)
            for value in _canonical_rz_extrema(poles, canonical_matrix)
        ]
    except Exception:
        pass

    def clipped(values: list[float], bounds: tuple[float, float]) -> list[float]:
        low, high = bounds
        tolerance = max(1.0, abs(low), abs(high)) * 1.0e-12
        return sorted(
            {
                min(high, max(low, float(value)))
                for value in values
                if low - tolerance <= float(value) <= high + tolerance
            }
        )

    evidence["u_breaks"] = clipped(u_breaks, u_bounds)
    evidence["v_breaks"] = clipped(v_breaks, v_bounds)
    evidence["all_trimmed_knot_span_boundaries_sampled"] = True
    return evidence


def _surface_uv_values(adaptor, points: list[list[float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    try:
        from OCP.ShapeAnalysis import ShapeAnalysis_Surface
        from OCP.gp import gp_Pnt

        analysis = ShapeAnalysis_Surface(adaptor.Surface().Surface())
        values = []
        for point in points:
            uv = analysis.ValueOfUV(gp_Pnt(*point), 1.0e-8)
            values.append((float(uv.X()), float(uv.Y())))
        return values
    except Exception:
        return []


def _refined_span_cells(
    breaks: list[float], refinement: int
) -> list[tuple[float, float]]:
    cells = []
    for left, right in zip(breaks, breaks[1:]):
        span_tolerance = max(
            1.0e-12,
            abs(float(left)) * 1.0e-12,
            abs(float(right)) * 1.0e-12,
        )
        if right - left <= span_tolerance:
            continue
        width = (right - left) / refinement
        cells.extend(
            (left + index * width, left + (index + 1) * width)
            for index in range(refinement)
        )
    return cells


def _bspline_branch_poles(branch) -> np.ndarray | None:
    u_count = int(branch.NbUPoles())
    v_count = int(branch.NbVPoles())
    if u_count <= 0 or v_count <= 0:
        return None
    poles = np.asarray(
        [
            branch.Pole(u_index, v_index).Coord()
            for u_index in range(1, u_count + 1)
            for v_index in range(1, v_count + 1)
        ],
        dtype=float,
    )
    if poles.ndim != 2 or poles.shape[1] != 3 or not np.all(np.isfinite(poles)):
        return None
    return poles


def _material_domain_control_bounds(
    adaptor,
    *,
    u_breaks: list[float],
    v_breaks: list[float],
    refinement: int,
    evaluate_uv,
    boundary_uv_values: list[tuple[float, float]],
    canonical_matrix: np.ndarray,
    consume_branch,
    sampled_extrema: np.ndarray,
    tolerance_mm: float,
) -> np.ndarray | None:
    try:
        surface = adaptor.BSpline()
    except Exception:
        return None
    branch_bounds: list[np.ndarray] = []
    maximum_depth = int(round(math.log2(refinement)))
    pending = [
        (u_left, u_right, v_left, v_right, 0)
        for u_left, u_right in _refined_span_cells(u_breaks, 1)
        for v_left, v_right in _refined_span_cells(v_breaks, 1)
    ]
    parameter_tolerance = 1.0e-12
    while pending:
        u_left, u_right, v_left, v_right, depth = pending.pop()
        probes = (
            (0.5 * (u_left + u_right), 0.5 * (v_left + v_right)),
            (u_left, v_left),
            (u_left, v_right),
            (u_right, v_left),
            (u_right, v_right),
        )
        occupied = any(
            bool(evaluate_uv(u_value, v_value)[0]) for u_value, v_value in probes
        )
        if not occupied:
            occupied = any(
                u_left - parameter_tolerance <= u_value <= u_right + parameter_tolerance
                and v_left - parameter_tolerance <= v_value <= v_right + parameter_tolerance
                for u_value, v_value in boundary_uv_values
            )
        if not occupied:
            continue
        consume_branch()
        branch = surface.Copy()
        try:
            branch.Segment(u_left, u_right, v_left, v_right)
        except Exception:
            return None
        poles = _bspline_branch_poles(branch)
        if poles is None:
            continue
        canonical = _transform_points(poles, canonical_matrix)
        x_min, y_min, z_min = np.min(canonical, axis=0)
        x_max, y_max, z_max = np.max(canonical, axis=0)
        radial_lower = math.hypot(
            0.0 if x_min <= 0.0 <= x_max else min(abs(x_min), abs(x_max)),
            0.0 if y_min <= 0.0 <= y_max else min(abs(y_min), abs(y_max)),
        )
        radial_upper = float(np.max(np.linalg.norm(canonical[:, :2], axis=1)))
        bounds = np.asarray(
            [radial_lower, radial_upper, z_min, z_max], dtype=float
        )
        if depth < maximum_depth and _control_bound_gap_mm(
            sampled_extrema, bounds
        ) > tolerance_mm:
            u_middle = 0.5 * (u_left + u_right)
            v_middle = 0.5 * (v_left + v_right)
            pending.extend(
                (u0, u1, v0, v1, depth + 1)
                for u0, u1 in ((u_left, u_middle), (u_middle, u_right))
                for v0, v1 in ((v_left, v_middle), (v_middle, v_right))
            )
        else:
            branch_bounds.append(bounds)
    if not branch_bounds:
        return None
    values = np.asarray(branch_bounds)
    return np.asarray(
        [
            float(np.min(values[:, 0])),
            float(np.max(values[:, 1])),
            float(np.min(values[:, 2])),
            float(np.max(values[:, 3])),
        ]
    )


def _control_bound_gap_mm(
    sampled_extrema: np.ndarray, possible_bounds: np.ndarray
) -> float:
    gaps = np.asarray(
        [
            sampled_extrema[0] - possible_bounds[0],
            possible_bounds[1] - sampled_extrema[1],
            sampled_extrema[2] - possible_bounds[2],
            possible_bounds[3] - sampled_extrema[3],
        ],
        dtype=float,
    )
    return float(max(0.0, np.max(gaps)))


def _priority_refine_material_control_bounds(
    adaptor,
    *,
    u_breaks: list[float],
    v_breaks: list[float],
    evaluate_uv,
    material_samples: dict[
        tuple[float, float], tuple[list[float], list[float], bool]
    ],
    boundary_points: list[list[float]],
    boundary_uv_values: list[tuple[float, float]],
    canonical_matrix: np.ndarray,
    consume_branch,
    tolerance_mm: float,
    starting_depth: int,
    maximum_depth: int,
) -> dict[str, Any]:
    surface = adaptor.BSpline()
    parameter_tolerance = 1.0e-12
    leaves: dict[
        tuple[float, float, float, float, int], np.ndarray
    ] = {}
    refined_by_depth: dict[int, int] = defaultdict(int)
    iterations = 0

    def sample_extrema() -> np.ndarray:
        points = [
            value[0] for value in material_samples.values() if value[0]
        ]
        return _canonical_rz_extrema(
            np.asarray([*points, *boundary_points], dtype=float), canonical_matrix
        )

    def occupied(u_left, u_right, v_left, v_right) -> bool:
        u_width = u_right - u_left
        v_width = v_right - v_left
        probes = (
            (0.5, 0.5),
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.38196601125, 0.61803398875),
            (0.61803398875, 0.38196601125),
        )
        if any(
            bool(
                evaluate_uv(
                    u_left + u_width * u_fraction,
                    v_left + v_width * v_fraction,
                )[0]
            )
            for u_fraction, v_fraction in probes
        ):
            return True
        return any(
            u_left - parameter_tolerance <= u_value <= u_right + parameter_tolerance
            and v_left - parameter_tolerance <= v_value <= v_right + parameter_tolerance
            for u_value, v_value in boundary_uv_values
        )

    def branch_bounds(u_left, u_right, v_left, v_right) -> np.ndarray | None:
        if not occupied(u_left, u_right, v_left, v_right):
            return None
        consume_branch()
        branch = surface.Copy()
        try:
            branch.Segment(u_left, u_right, v_left, v_right)
        except Exception:
            return None
        poles = _bspline_branch_poles(branch)
        if poles is None:
            return None
        canonical = _transform_points(poles, canonical_matrix)
        x_min, y_min, z_min = np.min(canonical, axis=0)
        x_max, y_max, z_max = np.max(canonical, axis=0)
        return np.asarray(
            [
                math.hypot(
                    0.0
                    if x_min <= 0.0 <= x_max
                    else min(abs(x_min), abs(x_max)),
                    0.0
                    if y_min <= 0.0 <= y_max
                    else min(abs(y_min), abs(y_max)),
                ),
                float(np.max(np.linalg.norm(canonical[:, :2], axis=1))),
                float(z_min),
                float(z_max),
            ],
            dtype=float,
        )

    initial_refinement = 2**starting_depth
    for u_left, u_right in _refined_span_cells(u_breaks, initial_refinement):
        for v_left, v_right in _refined_span_cells(v_breaks, initial_refinement):
            bounds = branch_bounds(u_left, u_right, v_left, v_right)
            if bounds is not None:
                leaves[(u_left, u_right, v_left, v_right, starting_depth)] = bounds

    while leaves:
        sampled = sample_extrema()
        all_bounds = np.asarray(list(leaves.values()), dtype=float)
        global_bounds = np.asarray(
            [
                np.min(all_bounds[:, 0]),
                np.max(all_bounds[:, 1]),
                np.min(all_bounds[:, 2]),
                np.max(all_bounds[:, 3]),
            ],
            dtype=float,
        )
        global_gap = _control_bound_gap_mm(sampled, global_bounds)
        if global_gap <= tolerance_mm:
            return {
                "converged": True,
                "control_bounds": global_bounds,
                "control_bound_gap_mm": round(global_gap, 9),
                "sampled_extrema_mm": [round(float(item), 9) for item in sampled],
                "iterations": iterations,
                "maximum_refinement": max(2**key[4] for key in leaves),
                "refined_branch_count_by_depth": {
                    str(depth): count for depth, count in sorted(refined_by_depth.items())
                },
            }

        active_limits = (
            (0, float(sampled[0] - global_bounds[0]), min),
            (1, float(global_bounds[1] - sampled[1]), max),
            (2, float(sampled[2] - global_bounds[2]), min),
            (3, float(global_bounds[3] - sampled[3]), max),
        )
        priority_by_key: dict[
            tuple[float, float, float, float, int], float
        ] = {}
        for bound_index, gap, selector in active_limits:
            if gap <= tolerance_mm:
                continue
            limiting_value = selector(
                float(bounds[bound_index]) for bounds in leaves.values()
            )
            comparison_tolerance = max(1.0e-12, abs(limiting_value) * 1.0e-12)
            for key, bounds in leaves.items():
                if abs(float(bounds[bound_index]) - limiting_value) <= comparison_tolerance:
                    priority_by_key[key] = max(priority_by_key.get(key, 0.0), gap)
        queue = [
            (-priority, -key[4], key)
            for key, priority in priority_by_key.items()
        ]
        heapq.heapify(queue)
        if not queue:
            break
        _, _, key = heapq.heappop(queue)
        u_left, u_right, v_left, v_right, depth = key
        if depth >= maximum_depth:
            break
        parent_bounds = leaves.pop(key)
        u_middle = 0.5 * (u_left + u_right)
        v_middle = 0.5 * (v_left + v_right)
        children = []
        subdivision_candidates = (
            tuple(
                (child_u_left, child_u_right, child_v_left, child_v_right)
                for child_u_left, child_u_right in (
                    (u_left, u_middle),
                    (u_middle, u_right),
                )
                for child_v_left, child_v_right in (
                    (v_left, v_middle),
                    (v_middle, v_right),
                )
            ),
            (
                (u_left, u_middle, v_left, v_right),
                (u_middle, u_right, v_left, v_right),
            ),
            (
                (u_left, u_right, v_left, v_middle),
                (u_left, u_right, v_middle, v_right),
            ),
        )
        for candidate_cells in subdivision_candidates:
            for (
                child_u_left,
                child_u_right,
                child_v_left,
                child_v_right,
            ) in candidate_cells:
                bounds = branch_bounds(
                    child_u_left,
                    child_u_right,
                    child_v_left,
                    child_v_right,
                )
                if bounds is None:
                    continue
                child_key = (
                    child_u_left,
                    child_u_right,
                    child_v_left,
                    child_v_right,
                    depth + 1,
                )
                leaves[child_key] = bounds
                children.append(child_key)
            if children:
                break
        if not children:
            leaves[key] = parent_bounds
            break
        refined_by_depth[depth + 1] += len(children)
        iterations += 1

    sampled = sample_extrema()
    if leaves:
        all_bounds = np.asarray(list(leaves.values()), dtype=float)
        global_bounds = np.asarray(
            [
                np.min(all_bounds[:, 0]),
                np.max(all_bounds[:, 1]),
                np.min(all_bounds[:, 2]),
                np.max(all_bounds[:, 3]),
            ]
        )
    else:
        global_bounds = sampled.copy()
    return {
        "converged": False,
        "control_bounds": global_bounds,
        "control_bound_gap_mm": round(
            _control_bound_gap_mm(sampled, global_bounds), 9
        ),
        "sampled_extrema_mm": [round(float(item), 9) for item in sampled],
        "iterations": iterations,
        "maximum_refinement": max((2**key[4] for key in leaves), default=2**starting_depth),
        "refined_branch_count_by_depth": {
            str(depth): count for depth, count in sorted(refined_by_depth.items())
        },
    }


def _canonical_rz_extrema(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    canonical = _transform_points(np.asarray(points, dtype=float), matrix)
    radii = np.linalg.norm(canonical[:, :2], axis=1)
    axial = canonical[:, 2]
    return np.asarray(
        [np.min(radii), np.max(radii), np.min(axial), np.max(axial)], dtype=float
    )


def _representative_trimmed_material_point(
    face,
    adaptor,
    interior_points: list[list[float]],
) -> list[float]:
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt, gp_Pnt2d

    vertices = np.asarray(
        [vertex.Center().toTuple() for vertex in face.Vertices()], dtype=float
    )
    target = (
        np.mean(vertices, axis=0)
        if len(vertices)
        else np.mean(np.asarray(interior_points, dtype=float), axis=0)
    )
    analysis = ShapeAnalysis_Surface(adaptor.Surface().Surface())
    uv = analysis.ValueOfUV(gp_Pnt(*[float(value) for value in target]), 1.0e-9)
    classifier = BRepClass_FaceClassifier(
        face.wrapped,
        gp_Pnt2d(float(uv.X()), float(uv.Y())),
        1.0e-9,
    )
    if classifier.State() in {TopAbs_IN, TopAbs_ON}:
        point = adaptor.Value(float(uv.X()), float(uv.Y()))
        return [float(point.X()), float(point.Y()), float(point.Z())]
    candidates = np.asarray(interior_points, dtype=float)
    closest = candidates[
        int(np.argmin(np.linalg.norm(candidates - target[None, :], axis=1)))
    ]
    return closest.tolist()


def _canonical_normal_distribution(
    source_points: np.ndarray,
    source_normals: np.ndarray,
    matrix: np.ndarray,
) -> list[float]:
    canonical_points = _transform_points(source_points, matrix)
    canonical_normals = source_normals @ matrix[:3, :3].T
    components = []
    for point, normal in zip(canonical_points, canonical_normals, strict=True):
        radius = math.hypot(float(point[0]), float(point[1]))
        if radius > 1.0e-9:
            radial = np.asarray([point[0] / radius, point[1] / radius, 0.0])
            tangent = np.asarray([-radial[1], radial[0], 0.0])
            components.append(
                [
                    float(np.dot(normal, radial)),
                    float(np.dot(normal, tangent)),
                    float(normal[2]),
                ]
            )
        else:
            components.append(
                [float(np.linalg.norm(normal[:2])), 0.0, float(normal[2])]
            )
    mean = np.mean(np.asarray(components, dtype=float), axis=0)
    return [_quantize(float(value), 5) for value in mean]


def _canonical_face_angular_evidence(canonical_points: np.ndarray) -> dict[str, Any]:
    radii = np.linalg.norm(canonical_points[:, :2], axis=1)
    usable = radii > 1.0e-9
    if not np.any(usable):
        raise ValueError(
            "canonical face samples do not define an angle about the source axis"
        )

    points = canonical_points[usable]
    sample_radii = radii[usable]
    angles_deg = [
        math.degrees(math.atan2(float(point[1]), float(point[0]))) % 360.0
        for point in points
    ]
    start_deg, end_deg, span_deg = _minimal_circular_arc_deg(angles_deg)

    radial_extent = float(np.ptp(sample_radii))
    if radial_extent <= 1.0e-9:
        wrap_deg = 0.0
        wrap_status = "measured_constant_radius"
        inner_angle_deg = outer_angle_deg = _circular_mean_deg(angles_deg)
    else:
        radial_band = max(1.0e-7, 0.001 * radial_extent)
        minimum_radius = float(np.min(sample_radii))
        maximum_radius = float(np.max(sample_radii))
        inner_angles = [
            angle
            for angle, radius in zip(angles_deg, sample_radii, strict=True)
            if radius <= minimum_radius + radial_band
        ]
        outer_angles = [
            angle
            for angle, radius in zip(angles_deg, sample_radii, strict=True)
            if radius >= maximum_radius - radial_band
        ]
        reference_angle_deg = _circular_mean_deg(angles_deg)
        inner_angle_deg = _circular_median_near_reference_deg(
            inner_angles, reference_angle_deg
        )
        outer_angle_deg = _circular_median_near_reference_deg(
            outer_angles, reference_angle_deg
        )
        wrap_deg = _wrap_degrees(outer_angle_deg - inner_angle_deg)
        wrap_status = "measured_inner_to_outer_sample_angle"

    return {
        "angular_span_deg": round(span_deg, 9),
        "angular_span_evidence": {
            "method": "minimum_circular_arc_of_canonical_face_samples",
            "start_angle_deg": round(start_deg, 9),
            "end_angle_deg": round(end_deg, 9),
            "sample_count": len(angles_deg),
        },
        "wrap_deg": round(wrap_deg, 9),
        "wrap_evidence": {
            "method": wrap_status,
            "inner_sample_angle_deg": round(inner_angle_deg, 9),
            "outer_sample_angle_deg": round(outer_angle_deg, 9),
            "radial_extent_mm": round(radial_extent, 6),
        },
    }


def _minimal_circular_arc_deg(angles_deg: list[float]) -> tuple[float, float, float]:
    normalized = sorted(angle % 360.0 for angle in angles_deg)
    if len(normalized) == 1:
        return normalized[0], normalized[0], 0.0
    gaps = [
        normalized[index + 1] - normalized[index]
        for index in range(len(normalized) - 1)
    ] + [normalized[0] + 360.0 - normalized[-1]]
    largest_gap_index = max(range(len(gaps)), key=lambda index: (gaps[index], -index))
    start_deg = normalized[(largest_gap_index + 1) % len(normalized)]
    span_deg = max(0.0, 360.0 - gaps[largest_gap_index])
    return start_deg, (start_deg + span_deg) % 360.0, span_deg


def _circular_mean_deg(angles_deg: list[float]) -> float:
    if not angles_deg:
        raise ValueError("circular mean requires canonical angular samples")
    x = sum(math.cos(math.radians(angle)) for angle in angles_deg)
    y = sum(math.sin(math.radians(angle)) for angle in angles_deg)
    if math.hypot(x, y) <= 1.0e-12:
        return min(angle % 360.0 for angle in angles_deg)
    return math.degrees(math.atan2(y, x)) % 360.0


def _circular_median_near_reference_deg(
    angles_deg: list[float], reference_deg: float
) -> float:
    if not angles_deg:
        raise ValueError("circular median requires canonical angular samples")
    offsets = sorted(_wrap_degrees(angle - reference_deg) for angle in angles_deg)
    return (reference_deg + float(np.median(offsets))) % 360.0


def _wrap_degrees(value: float) -> float:
    wrapped = (value + 180.0) % 360.0 - 180.0
    return 180.0 if math.isclose(wrapped, -180.0, abs_tol=1.0e-12) else wrapped


def _periodic_signature_group(
    signature_hash: str,
    members: list[dict[str, Any]],
    outer_radius: float,
) -> dict[str, Any] | None:
    if len(members) < 3:
        return None
    if float(np.mean([item["centroid_rz_mm"][0] for item in members])) <= max(
        0.02, outer_radius * 0.05
    ):
        return None
    sample_residual = _phase_aligned_canonical_sample_residual(members)
    if sample_residual is None:
        return None
    trim_residual = _phase_aligned_canonical_sample_residual(
        members, sample_field="canonical_trim_boundary_samples_mm"
    )
    trim_tolerance = max(0.02, outer_radius * 0.0004)
    angles = sorted(math.radians(item["centroid_angle_deg"]) for item in members)
    gaps = np.diff([*angles, angles[0] + 2.0 * math.pi])
    expected = 2.0 * math.pi / len(members)
    closure_error_deg = math.degrees(float(np.max(np.abs(gaps - expected))))
    if closure_error_deg > max(0.15, math.degrees(expected) * 0.015):
        return None
    transformed_sample_residual = sample_residual["residual_mm"]
    return {
        "group_id": f"periodic_signature_{signature_hash[:12]}",
        "signature_hash": signature_hash,
        "source_entity_ids": sorted(item["source_face_id"] for item in members),
        "method": "axis_rotation_signature_closure_r3",
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm", "angular": "deg"},
        "tolerance": {
            "angular_closure_deg": round(max(0.15, math.degrees(expected) * 0.015), 9),
            "signature_linear_quantization_mm": 0.001,
        },
        "confidence": {
            "closure_score": round(
                max(
                    0.0,
                    1.0 - closure_error_deg / max(0.15, math.degrees(expected) * 0.015),
                ),
                9,
            )
        },
        "residual": {
            "angular_closure_deg": round(closure_error_deg, 9),
            "transformed_sample_mm": transformed_sample_residual,
            "method": "symmetric_nearest_neighbor_of_phase_aligned_canonical_surface_samples",
            "canonical_surface_sample_count": sample_residual["sample_count"],
        },
        "count": len(members),
        "pitch_deg": round(360.0 / len(members), 9),
        "angular_closure_residual_deg": round(closure_error_deg, 9),
        "transformed_sample_residual_mm": transformed_sample_residual,
        "trim_boundary_authentication": {
            "status": (
                "PASS"
                if trim_residual is not None
                and trim_residual["residual_mm"] <= trim_tolerance
                else "FAIL"
            ),
            "within_tolerance": bool(
                trim_residual is not None
                and trim_residual["residual_mm"] <= trim_tolerance
            ),
            "residual_mm": (
                None if trim_residual is None else trim_residual["residual_mm"]
            ),
            "tolerance_mm": round(trim_tolerance, 9),
            "sample_count": (
                0 if trim_residual is None else trim_residual["sample_count"]
            ),
            "method": "phase_aligned_exact_step_trim_boundary",
        },
        "member_face_ids": sorted(item["source_face_id"] for item in members),
        "provenance": {
            "authority": "uploaded_step_brep_canonical_surface_samples",
            "source_entity_ids": sorted(
                item["source_face_id"] for item in members
            ),
            "coordinate_frame": "canonical_cylindrical_r_theta_z",
        },
    }


def _phase_aligned_canonical_sample_residual(
    members: list[dict[str, Any]],
    *,
    sample_field: str = "canonical_surface_samples_mm",
) -> dict[str, Any] | None:
    aligned_samples: list[np.ndarray] = []
    sample_count = 0
    for member in members:
        samples = np.asarray(member.get(sample_field, []), dtype=float)
        if samples.ndim != 2 or samples.shape[1:] != (3,) or len(samples) == 0:
            return None
        if not np.all(np.isfinite(samples)):
            return None
        angle = math.radians(-float(member["centroid_angle_deg"]))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        rotation = np.asarray(
            [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
            dtype=float,
        )
        aligned_samples.append(samples @ rotation.T)
        sample_count += len(samples)

    pairwise_residuals: list[float] = []
    for first_index, first in enumerate(aligned_samples):
        for second in aligned_samples[first_index + 1 :]:
            distances = np.linalg.norm(first[:, None, :] - second[None, :, :], axis=2)
            forward = float(np.sqrt(np.mean(np.square(np.min(distances, axis=1)))))
            reverse = float(np.sqrt(np.mean(np.square(np.min(distances, axis=0)))))
            pairwise_residuals.append(max(forward, reverse))
    residual = max(pairwise_residuals, default=0.0)
    return {
        "residual_mm": round(residual, 6),
        "sample_count": sample_count,
    }


def _connected_components(
    face_ids: set[str],
    adjacency: dict[str, list[str]],
    signatures: list[dict[str, Any]],
    *,
    classification: str,
) -> list[dict[str, Any]]:
    signature_by_id = {item["source_face_id"]: item for item in signatures}
    pending = set(face_ids)
    components: list[dict[str, Any]] = []
    while pending:
        seed = min(pending)
        stack = [seed]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in members or current not in face_ids:
                continue
            members.add(current)
            stack.extend(adjacency.get(current, []))
        pending -= members
        member_ids = sorted(members)
        digest_payload = [
            *sorted(signature_by_id[item]["signature_hash"] for item in member_ids),
            *member_ids,
        ]
        digest = hashlib.sha256("|".join(digest_payload).encode("ascii")).hexdigest()[
            :12
        ]
        component = {
                "component_id": f"face_component_{digest}",
                "method": "exact_brep_face_adjacency_connected_components_r3",
                "coordinate_frame": "canonical_cylindrical_r_theta_z",
                "units": {"linear": "mm", "angular": "deg"},
                "tolerance": {
                    "shared_edge_identity_tolerance_mm": 1.0e-12,
                    "signature_linear_quantization_mm": 0.001,
                },
                "confidence": {
                    "level": "deterministic_topology_component",
                    "score": 1.0,
                    "status": "ACCEPTED",
                    "classification": classification,
                    "all_members_accounted_for": True,
                },
                "residual": {
                    "transformed_sample_mm": _component_sample_residual(
                        member_ids, signature_by_id
                    )
                },
                "source_entity_ids": member_ids,
                "face_ids": member_ids,
                "face_count": len(member_ids),
                "signature_hashes": sorted(
                    {signature_by_id[item]["signature_hash"] for item in member_ids}
                ),
                "provenance": {
                    "authority": "uploaded_step_brep_topology",
                    "source_entity_ids": member_ids,
                    "signature_hashes": sorted(
                        {
                            signature_by_id[item]["signature_hash"]
                            for item in member_ids
                        }
                    ),
                },
            }
        if classification == "periodic_blade_related":
            component["component_completeness"] = _blade_component_completeness(
                member_ids, signature_by_id
            )
        components.append(component)
    return sorted(
        components, key=lambda item: (-item["face_count"], item["component_id"])
    )


def _expand_authenticated_periodic_seed_components(
    signatures: list[dict[str, Any]],
    adjacency: dict[str, list[str]],
    rotational_group_by_face_id: dict[str, dict[str, Any]],
    certified_seed_ids: set[str],
    outer_radius: float,
) -> dict[str, Any]:
    signature_by_id = {item["source_face_id"]: item for item in signatures}
    excluded_by_reason: dict[str, list[str]] = defaultdict(list)
    eligible_ids: set[str] = set()
    for face_id, signature in signature_by_id.items():
        reason = _blade_expansion_exclusion_reason(
            signature,
            is_certified_seed=face_id in certified_seed_ids,
            outer_radius=outer_radius,
        )
        if reason is None:
            eligible_ids.add(face_id)
        else:
            excluded_by_reason[reason].append(face_id)

    local_components = _connected_components(
        eligible_ids,
        adjacency,
        signatures,
        classification="authenticated_seed_local_adjacency_candidate",
    )
    accepted_components: list[dict[str, Any]] = []
    rejected_components: list[dict[str, Any]] = []
    resolved_cross_blade_components: list[dict[str, Any]] = []
    periodic_face_ids: set[str] = set()
    membership_by_face_id: dict[str, dict[str, Any]] = {}

    def accept_component(component: dict[str, Any]) -> bool:
        member_ids = component["face_ids"]
        component_seed_ids = sorted(set(member_ids) & certified_seed_ids)
        seed_groups = [
            rotational_group_by_face_id[face_id] for face_id in component_seed_ids
        ]
        seed_count_by_group = Counter(group["group_id"] for group in seed_groups)
        duplicate_seed_groups = sorted(
            group_id
            for group_id, count in seed_count_by_group.items()
            if count > 1
        )
        population_counts = sorted({int(group["count"]) for group in seed_groups})
        completeness = _blade_component_completeness(member_ids, signature_by_id)
        rejection_reason = None
        if not component_seed_ids:
            rejection_reason = "missing_authenticated_periodic_seed"
        elif duplicate_seed_groups:
            rejection_reason = "cross_blade_seed_merge"
        elif len(population_counts) != 1:
            rejection_reason = "mixed_periodic_population_counts"
        elif completeness["status"] != "COMPLETE":
            rejection_reason = "incomplete_blade_section_provenance"
        if rejection_reason is not None:
            rejected_components.append(
                {
                    "source_component_id": component["component_id"],
                    "source_face_ids": list(member_ids),
                    "certified_seed_face_ids": component_seed_ids,
                    "reason": rejection_reason,
                    "duplicate_seed_group_ids": duplicate_seed_groups,
                    "population_counts": population_counts,
                    "component_completeness": completeness,
                }
            )
            return False

        closure_residual = max(
            float(group["angular_closure_residual_deg"]) for group in seed_groups
        )
        component_record = {
            "source_component_id": component["component_id"],
            "source_face_ids": list(member_ids),
            "face_count": len(member_ids),
            "certified_seed_face_ids": component_seed_ids,
            "seed_rotational_group_ids": sorted(seed_count_by_group),
            "population_count": population_counts[0],
            "angular_closure_residual_deg": round(closure_residual, 9),
            "component_completeness": completeness,
            "method": "exact_brep_face_adjacency_from_authenticated_periodic_seeds",
            "provenance": {
                "authority": "uploaded_step_brep_topology_and_trim_boundaries",
                "source_entity_ids": list(member_ids),
            },
        }
        accepted_components.append(component_record)
        periodic_face_ids.update(member_ids)
        side_ids = set(completeness["blade_side_face_ids"])
        for face_id in member_ids:
            membership_by_face_id[face_id] = {
                "source_component_id": component["component_id"],
                "source_entity_ids": list(member_ids),
                "seed_source_entity_ids": component_seed_ids,
                "semantic_role": (
                    "blade_side" if face_id in side_ids else "blade_root_or_edge"
                ),
                "population_count": population_counts[0],
                "angular_closure_residual_deg": round(closure_residual, 9),
                "component_completeness": completeness,
                "method": "exact_brep_face_adjacency_from_authenticated_periodic_seeds",
            }
        return True

    for component in local_components:
        member_ids = component["face_ids"]
        component_seed_ids = sorted(set(member_ids) & certified_seed_ids)
        if not component_seed_ids:
            continue
        seed_group_counts = Counter(
            rotational_group_by_face_id[face_id]["group_id"]
            for face_id in component_seed_ids
        )
        if any(count > 1 for count in seed_group_counts.values()):
            split = _split_cross_blade_seed_component(
                member_ids,
                component_seed_ids,
                adjacency,
                signatures,
                rotational_group_by_face_id,
            )
            resolved_cross_blade_components.append(split["evidence"])
            if split["status"] != "PASS":
                rejected_components.append(
                    {
                        "source_component_id": component["component_id"],
                        "source_face_ids": list(member_ids),
                        "certified_seed_face_ids": component_seed_ids,
                        "reason": "cross_blade_seed_partition_failed",
                        "partition_evidence": split["evidence"],
                        "component_completeness": _blade_component_completeness(
                            member_ids, signature_by_id
                        ),
                    }
                )
                continue
            for split_face_ids in split["component_face_ids"]:
                split_components = _connected_components(
                    set(split_face_ids),
                    adjacency,
                    signatures,
                    classification="periodic_blade_related",
                )
                if len(split_components) != 1:
                    rejected_components.append(
                        {
                            "source_component_id": component["component_id"],
                            "source_face_ids": list(split_face_ids),
                            "certified_seed_face_ids": sorted(
                                set(split_face_ids) & certified_seed_ids
                            ),
                            "reason": "split_component_not_topologically_connected",
                        }
                    )
                    continue
                accept_component(split_components[0])
            continue
        accept_component(component)

    accepted_components.sort(key=lambda item: item["source_component_id"])
    rejected_components.sort(key=lambda item: item["source_component_id"])
    return {
        "method": "authenticated_periodic_seed_exact_adjacency_expansion_r4",
        "periodic_face_ids": sorted(periodic_face_ids),
        "accepted_components": accepted_components,
        "rejected_components": rejected_components,
        "resolved_cross_blade_components": resolved_cross_blade_components,
        "excluded_face_ids_by_reason": {
            reason: sorted(face_ids)
            for reason, face_ids in sorted(excluded_by_reason.items())
        },
        "invariants": {
            "all_selected_components_multiface": all(
                item["face_count"] >= 4 for item in accepted_components
            ),
            "all_selected_components_section_complete": all(
                item["component_completeness"]["status"] == "COMPLETE"
                for item in accepted_components
            ),
            "cross_blade_merge_count": sum(
                item["reason"]
                in {"cross_blade_seed_merge", "cross_blade_seed_partition_failed"}
                for item in rejected_components
            ),
        },
        "membership_by_face_id": membership_by_face_id,
    }


def _split_cross_blade_seed_component(
    member_ids: list[str],
    component_seed_ids: list[str],
    adjacency: dict[str, list[str]],
    signatures: list[dict[str, Any]],
    rotational_group_by_face_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    member_set = set(member_ids)
    seeds_by_group: dict[str, list[str]] = defaultdict(list)
    for face_id in component_seed_ids:
        seeds_by_group[rotational_group_by_face_id[face_id]["group_id"]].append(
            face_id
        )
    anchor_group_id, anchor_ids = min(
        seeds_by_group.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    anchor_ids = sorted(anchor_ids)
    expected_count = int(rotational_group_by_face_id[anchor_ids[0]]["count"])
    if len(anchor_ids) != expected_count:
        return {
            "status": "FAIL",
            "component_face_ids": [],
            "evidence": {
                "status": "FAIL",
                "reason": "anchor_seed_group_incomplete",
                "anchor_group_id": anchor_group_id,
                "anchor_seed_face_ids": anchor_ids,
                "expected_anchor_count": expected_count,
            },
        }

    distances_by_anchor: dict[str, dict[str, int]] = {}
    for anchor_id in anchor_ids:
        distances = {anchor_id: 0}
        queue = [anchor_id]
        for current in queue:
            for neighbor in sorted(adjacency.get(current, [])):
                if neighbor in member_set and neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        distances_by_anchor[anchor_id] = distances

    owner_by_face_id: dict[str, str | None] = {}
    tied_face_ids: set[str] = set()
    for face_id in member_ids:
        ranked = sorted(
            (
                (distances[face_id], anchor_id)
                for anchor_id, distances in distances_by_anchor.items()
                if face_id in distances
            ),
            key=lambda item: (item[0], item[1]),
        )
        if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
            owner_by_face_id[face_id] = None
            tied_face_ids.add(face_id)
        else:
            owner_by_face_id[face_id] = ranked[0][1]
    for anchor_id in anchor_ids:
        owner_by_face_id[anchor_id] = anchor_id
        tied_face_ids.discard(anchor_id)

    cross_owner_bridge_ids: set[str] = set()
    for face_id in member_ids:
        if face_id in anchor_ids or owner_by_face_id[face_id] is None:
            continue
        adjacent_owners = {
            owner_by_face_id.get(neighbor)
            for neighbor in adjacency.get(face_id, [])
            if owner_by_face_id.get(neighbor) is not None
        }
        if len(adjacent_owners) > 1:
            cross_owner_bridge_ids.add(face_id)

    blocked_ids = tied_face_ids | cross_owner_bridge_ids
    component_face_ids: list[list[str]] = []
    for anchor_id in anchor_ids:
        owned_ids = {
            face_id
            for face_id, owner in owner_by_face_id.items()
            if owner == anchor_id and face_id not in blocked_ids
        }
        connected = set()
        stack = [anchor_id]
        while stack:
            current = stack.pop()
            if current in connected or current not in owned_ids:
                continue
            connected.add(current)
            stack.extend(adjacency.get(current, []))
        component_face_ids.append(sorted(connected))

    assigned_ids = set().union(*(set(item) for item in component_face_ids))
    unassigned_ids = member_set - assigned_ids
    status = "PASS" if all(component_face_ids) else "FAIL"
    signature_by_id = {item["source_face_id"]: item for item in signatures}
    return {
        "status": status,
        "component_face_ids": component_face_ids,
        "evidence": {
            "status": status,
            "method": "exact_adjacency_multisource_seed_voronoi_with_bridge_exclusion",
            "anchor_group_id": anchor_group_id,
            "anchor_seed_face_ids": anchor_ids,
            "expected_anchor_count": expected_count,
            "component_face_counts": [len(item) for item in component_face_ids],
            "component_source_face_ids": component_face_ids,
            "tied_bridge_face_ids": sorted(tied_face_ids),
            "cross_owner_bridge_face_ids": sorted(cross_owner_bridge_ids),
            "excluded_support_face_ids": sorted(unassigned_ids),
            "excluded_support_signature_hashes": sorted(
                {signature_by_id[item]["signature_hash"] for item in unassigned_ids}
            ),
            "all_selected_faces_disjoint": sum(
                len(item) for item in component_face_ids
            )
            == len(assigned_ids),
        },
    }


def _blade_expansion_exclusion_reason(
    signature: dict[str, Any], *, is_certified_seed: bool, outer_radius: float
) -> str | None:
    semantic_stop = signature.get("adjacency_expansion_stop")
    if isinstance(semantic_stop, dict) and semantic_stop.get("excluded") is True:
        return str(semantic_stop["reason"])
    if is_certified_seed:
        return None
    certification = signature.get("periodic_seed_certification")
    if isinstance(certification, dict):
        classification = certification.get("classification")
        if classification == "analytic_auxiliary_hole_population":
            return "authenticated_auxiliary_hole_exclusion"
        if classification == "axisymmetric_support_population":
            return "authenticated_axisymmetric_support_exclusion"
    angular_span = float(signature.get("angular_span_deg", 360.0))
    if angular_span >= 300.0:
        return "axisymmetric_hub_shroud_or_support_exclusion"
    radial_min, radial_max = (
        float(value) for value in signature.get("radial_bounds_mm", (0.0, 0.0))
    )
    axial_min, axial_max = (
        float(value) for value in signature.get("axial_bounds_mm", (0.0, 0.0))
    )
    compact_analytic = (
        signature.get("geometry_type") in {"CYLINDER", "CONE", "TORUS"}
        and radial_max - radial_min < max(2.5, 0.1 * outer_radius)
        and axial_max - axial_min < max(2.5, 0.1 * outer_radius)
        and radial_max < 0.65 * outer_radius
    )
    if compact_analytic:
        return "compact_analytic_hole_exclusion"
    return None


def _adjacency_expansion_stop(
    signature: dict[str, Any], *, is_certified_seed: bool, outer_radius: float
) -> dict[str, Any]:
    """Record topology-derived faces that cannot bridge blade components."""

    if is_certified_seed:
        return {
            "excluded": False,
            "reason": None,
            "semantic_role": "authenticated_blade_seed",
            "method": "exact_adjacency_semantic_stop_classification",
        }
    certification = signature.get("periodic_seed_certification")
    topology_support = signature.get("blade_topology_support")
    classification = (
        certification.get("classification")
        if isinstance(certification, dict)
        else None
    )
    topology_classification = (
        topology_support.get("classification")
        if isinstance(topology_support, dict)
        else None
    )
    angular_span = float(signature.get("angular_span_deg", 360.0))
    geometry_type = str(signature.get("geometry_type", ""))
    radial_min, radial_max = (
        float(value) for value in signature.get("radial_bounds_mm", (0.0, 0.0))
    )
    axial_min, axial_max = (
        float(value) for value in signature.get("axial_bounds_mm", (0.0, 0.0))
    )
    compact_inner_analytic = (
        geometry_type in {"CYLINDER", "CONE", "TORUS"}
        and radial_max - radial_min < max(2.5, 0.1 * outer_radius)
        and axial_max - axial_min < max(2.5, 0.1 * outer_radius)
        and radial_max < 0.65 * outer_radius
    )
    if (
        classification == "analytic_auxiliary_hole_population"
        or topology_classification == "auxiliary_hole_like_subtractive_feature"
        or compact_inner_analytic
    ):
        role, reason = "auxiliary_hole", "authenticated_auxiliary_hole_exclusion"
    elif classification == "axisymmetric_support_population" or angular_span >= 300.0:
        role, reason = "hub_or_shroud_support", "axisymmetric_hub_shroud_or_support_exclusion"
    else:
        role, reason = "blade_local_or_unclassified", None
    return {
        "excluded": reason is not None,
        "reason": reason,
        "semantic_role": role,
        "method": "exact_adjacency_semantic_stop_classification",
        "evidence": {
            "geometry_type": geometry_type,
            "angular_span_deg": round(angular_span, 9),
            "radial_bounds_mm": [round(radial_min, 9), round(radial_max, 9)],
            "axial_bounds_mm": [round(axial_min, 9), round(axial_max, 9)],
            "periodic_seed_classification": classification,
            "topology_support_classification": topology_classification,
        },
    }


def _blade_component_completeness(
    member_ids: list[str], signature_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    ordered_by_area = sorted(
        member_ids,
        key=lambda face_id: (
            -float(signature_by_id[face_id]["area_mm2"]),
            face_id,
        ),
    )
    side_face_ids = sorted(ordered_by_area[:2]) if len(ordered_by_area) >= 2 else []
    root_edge_face_ids = sorted(set(member_ids) - set(side_face_ids))
    complete = len(side_face_ids) == 2 and len(root_edge_face_ids) >= 2
    return {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "minimum_face_count": 4,
        "face_count": len(member_ids),
        "blade_side_face_ids": side_face_ids,
        "root_edge_face_ids": root_edge_face_ids,
        "checks": {
            "two_large_blade_side_faces": len(side_face_ids) == 2,
            "root_edge_closure_face_count_at_least_two": len(root_edge_face_ids)
            >= 2,
        },
        "role_method": "two_largest_local_faces_then_exact_adjacent_root_edge_faces",
    }


def _blade_local_connectivity_eligible(
    signature_by_id: dict[str, dict[str, Any]],
    rotational_group_by_face_id: dict[str, dict[str, Any]],
    face_id: str,
) -> bool:
    signature = signature_by_id[face_id]
    group = rotational_group_by_face_id[face_id]
    angular_span = float(signature.get("angular_span_deg", 360.0))
    axisymmetric_support = angular_span >= 300.0 or (
        signature.get("geometry_type") in {"REVOLUTION", "CYLINDER", "CONE"}
        and angular_span >= max(180.0, 2.0 * (360.0 / max(int(group["count"]), 1)))
    )
    signature["blade_local_connectivity"] = {
        "eligible": not axisymmetric_support,
        "method": "exclude_axisymmetric_support_from_periodic_local_face_graph",
        "angular_span_deg": round(angular_span, 9),
        "rotational_population_count": int(group["count"]),
    }
    return not axisymmetric_support


def _authenticate_periodic_seed_group(
    group: dict[str, Any],
    members: list[dict[str, Any]],
    outer_radius: float,
) -> dict[str, Any]:
    radial_min = min(float(item["radial_bounds_mm"][0]) for item in members)
    radial_max = max(float(item["radial_bounds_mm"][1]) for item in members)
    radial_extent = radial_max - radial_min
    streamwise_extents = [
        float(item["streamwise_bounds_mm"][1])
        - float(item["streamwise_bounds_mm"][0])
        for item in members
    ]
    mean_streamwise_extent = float(np.mean(streamwise_extents))
    geometry_types = sorted({str(item["geometry_type"]) for item in members})
    analytic_cylindrical = set(geometry_types) <= {"CYLINDER", "CONE"}
    compact_inner_radial_support = (
        radial_max < 0.6 * outer_radius
        and radial_extent < max(2.0, 0.12 * outer_radius)
        and mean_streamwise_extent < max(2.0, 0.12 * outer_radius)
    )
    analytic_auxiliary_hole = analytic_cylindrical and compact_inner_radial_support
    axisymmetric_support = any(
        float(item.get("angular_span_deg", 360.0)) >= 300.0 for item in members
    )
    reaches_flowpath = radial_max >= 0.6 * outer_radius
    has_streamwise_support = radial_extent >= max(2.0, 0.12 * outer_radius)
    direct_sampling_certified = all(
        item.get("sampling_evidence", {}).get("promotable") is True
        for item in members
    )
    rotational_surface_check = _rotational_surface_authority_group_check(members)
    trim_boundary_check = group.get("trim_boundary_authentication", {})
    trim_boundary_certified = bool(
        isinstance(trim_boundary_check, dict)
        and trim_boundary_check.get("status") == "PASS"
        and trim_boundary_check.get("within_tolerance") is True
        and trim_boundary_check.get("method")
        == "phase_aligned_exact_step_trim_boundary"
        and isinstance(trim_boundary_check.get("residual_mm"), (int, float))
        and not isinstance(trim_boundary_check.get("residual_mm"), bool)
        and math.isfinite(float(trim_boundary_check["residual_mm"]))
        and isinstance(trim_boundary_check.get("tolerance_mm"), (int, float))
        and float(trim_boundary_check["tolerance_mm"]) > 0.0
        and isinstance(trim_boundary_check.get("sample_count"), int)
        and not isinstance(trim_boundary_check.get("sample_count"), bool)
        and int(trim_boundary_check["sample_count"]) > 0
        and float(trim_boundary_check["residual_mm"])
        <= float(trim_boundary_check["tolerance_mm"])
    )
    requires_exact_complex_authentication = any(
        item.get("geometry_type") == "BSPLINE" for item in members
    )
    exact_complex_authentication = bool(
        trim_boundary_certified and rotational_surface_check["within_tolerance"]
    )
    certified_sampling = bool(
        exact_complex_authentication
        if requires_exact_complex_authentication
        else direct_sampling_certified or exact_complex_authentication
    )
    accepted = bool(
        int(group["count"]) >= 3
        and certified_sampling
        and not analytic_auxiliary_hole
        and not axisymmetric_support
        and (reaches_flowpath or has_streamwise_support)
    )
    if analytic_auxiliary_hole:
        classification = "analytic_auxiliary_hole_population"
    elif axisymmetric_support:
        classification = "axisymmetric_support_population"
    elif not certified_sampling:
        classification = "uncertified_coarse_sampling_population"
    elif accepted:
        classification = "authenticated_periodic_blade_face_seed"
    else:
        classification = "insufficient_blade_support_evidence"
    return {
        "status": "ACCEPTED" if accepted else "REJECTED",
        "accepted_as_periodic_blade_seed": accepted,
        "classification": classification,
        "method": "closed_rotational_group_with_analytic_hole_and_support_exclusion",
        "confidence": {
            "level": "measured_rotational_seed_gate",
            "score": 1.0 if accepted or analytic_auxiliary_hole else 0.5,
            "status": "ACCEPTED" if accepted else "REJECTED",
        },
        "measurements": {
            "population_count": int(group["count"]),
            "geometry_types": geometry_types,
            "radial_bounds_mm": [round(radial_min, 9), round(radial_max, 9)],
            "radial_extent_mm": round(radial_extent, 9),
            "mean_streamwise_extent_mm": round(mean_streamwise_extent, 9),
            "outer_radius_mm": round(float(outer_radius), 9),
            "angular_closure_residual_deg": float(
                group["angular_closure_residual_deg"]
            ),
        },
        "checks": {
            "analytic_cylindrical": analytic_cylindrical,
            "compact_inner_radial_support": compact_inner_radial_support,
            "analytic_auxiliary_hole": analytic_auxiliary_hole,
            "axisymmetric_support": axisymmetric_support,
            "reaches_flowpath": reaches_flowpath,
            "has_streamwise_support": has_streamwise_support,
            "certified_sampling": certified_sampling,
            "direct_sampling_certified": direct_sampling_certified,
            "requires_exact_complex_authentication": (
                requires_exact_complex_authentication
            ),
            "trim_boundary_authentication": dict(trim_boundary_check),
            "rotational_surface_authority": rotational_surface_check,
        },
        "source_entity_ids": list(group["member_face_ids"]),
    }


def _rotational_surface_authority_group_check(
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    authorities = [
        item.get("sampling_evidence", {}).get("rotational_surface_authority")
        for item in members
    ]
    if not authorities or any(
        not isinstance(authority, dict) or authority.get("status") != "PASS"
        for authority in authorities
    ):
        return {
            "within_tolerance": False,
            "method": "exact_rotationally_normalized_step_bspline_control_net",
            "maximum_control_record_residual": None,
        }
    reference = authorities[0]["comparison_payload"]
    tolerance = 2.0e-5
    comparisons: list[dict[str, Any]] = []
    for member, authority in zip(members[1:], authorities[1:], strict=True):
        candidates = []
        for transform_name, payload in _surface_parameterization_variants(
            authority["comparison_payload"]
        ):
            residual = _surface_payload_residual(reference, payload)
            if residual is not None:
                candidates.append((residual, transform_name))
        if not candidates:
            return {
                "within_tolerance": False,
                "method": "exact_rotationally_normalized_step_bspline_control_lattice",
                "maximum_control_record_residual": None,
                "selected_parameterization_transforms": [],
                "comparison_records": comparisons,
            }
        residual, transform_name = min(candidates, key=lambda item: (item[0], item[1]))
        comparisons.append(
            {
                "source_face_id": member["source_face_id"],
                "selected_parameterization_transform": transform_name,
                "control_lattice_residual": round(float(residual), 9),
            }
        )
    maximum_residual = max(
        (item["control_lattice_residual"] for item in comparisons), default=0.0
    )
    return {
        "within_tolerance": maximum_residual <= tolerance,
        "method": "exact_rotationally_normalized_step_bspline_control_lattice",
        "maximum_control_record_residual": round(maximum_residual, 9),
        "selected_parameterization_transforms": [
            item["selected_parameterization_transform"] for item in comparisons
        ],
        "comparison_records": comparisons,
        "enumerated_parameterization_transforms": [
            "identity",
            "reverse_u",
            "reverse_v",
            "reverse_u_v",
            "swap_uv",
            "swap_uv_reverse_u",
            "swap_uv_reverse_v",
            "swap_uv_reverse_u_v",
        ],
        "knot_normalization": {
            "method": "affine_normalization_to_unit_interval",
            "reversal_rule": "normalized_parameter_maps_to_one_minus_parameter",
        },
        "tolerance": {
            "linear_mm": tolerance,
            "weight": tolerance,
            "normalized_knot": 1.0e-10,
        },
        "source_entity_ids": sorted(item["source_face_id"] for item in members),
    }


def _surface_parameterization_variants(
    payload: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    try:
        u_count, v_count = (int(value) for value in payload["control_lattice_shape"])
        records = np.asarray(
            payload["control_records_uv_local_xyz_weight"], dtype=float
        )
        if records.shape != (u_count * v_count, 6):
            return []
        lattice = np.empty((u_count, v_count, 4), dtype=float)
        seen: set[tuple[int, int]] = set()
        expected_indices = [
            (u_index, v_index)
            for u_index in range(1, u_count + 1)
            for v_index in range(1, v_count + 1)
        ]
        actual_indices: list[tuple[int, int]] = []
        for u_index, v_index, *values in records.tolist():
            if not float(u_index).is_integer() or not float(v_index).is_integer():
                return []
            key = (int(u_index), int(v_index))
            if key in seen or not (1 <= key[0] <= u_count and 1 <= key[1] <= v_count):
                return []
            seen.add(key)
            actual_indices.append(key)
            lattice[key[0] - 1, key[1] - 1] = values
        if (
            actual_indices != expected_indices
            or len(seen) != u_count * v_count
            or not np.all(np.isfinite(lattice))
        ):
            return []
    except (KeyError, TypeError, ValueError):
        return []

    variants = []
    for swap_uv in (False, True):
        base_lattice = lattice.transpose(1, 0, 2) if swap_uv else lattice
        base = _swap_surface_metadata(payload) if swap_uv else dict(payload)
        prefix = "swap_uv" if swap_uv else ""
        for reverse_u, reverse_v in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            transformed = base_lattice
            variant = dict(base)
            name_parts = [prefix] if prefix else []
            if reverse_u:
                transformed = transformed[::-1, :, :]
                variant = _reverse_surface_metadata(variant, "u")
                name_parts.append("reverse_u")
            if reverse_v:
                transformed = transformed[:, ::-1, :]
                variant = _reverse_surface_metadata(variant, "v")
                name_parts.append("reverse_v")
            variant["control_lattice_values_local_xyz_weight"] = transformed
            variants.append(("_".join(name_parts) or "identity", variant))
    return variants


def _swap_surface_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    swapped = dict(payload)
    for first, second in (
        ("u_degree", "v_degree"),
        ("u_periodic", "v_periodic"),
        ("u_knots", "v_knots"),
        ("u_multiplicities", "v_multiplicities"),
    ):
        swapped[first], swapped[second] = payload[second], payload[first]
    swapped["control_lattice_shape"] = list(reversed(payload["control_lattice_shape"]))
    return swapped


def _reverse_surface_metadata(payload: dict[str, Any], axis: str) -> dict[str, Any]:
    reversed_payload = dict(payload)
    knot_key = f"{axis}_knots"
    multiplicity_key = f"{axis}_multiplicities"
    reversed_payload[knot_key] = [
        round(1.0 - float(value), 10)
        for value in reversed(payload[knot_key])
    ]
    reversed_payload[multiplicity_key] = list(
        reversed(payload[multiplicity_key])
    )
    return reversed_payload


def _surface_payload_residual(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> float | None:
    exact_fields = (
        "u_degree",
        "v_degree",
        "u_periodic",
        "v_periodic",
        "u_multiplicities",
        "v_multiplicities",
        "control_lattice_shape",
    )
    if any(reference.get(field) != candidate.get(field) for field in exact_fields):
        return None
    for knot_field in ("u_knots", "v_knots"):
        first = np.asarray(reference.get(knot_field, []), dtype=float)
        second = np.asarray(candidate.get(knot_field, []), dtype=float)
        if first.shape != second.shape or not np.allclose(first, second, atol=1.0e-10, rtol=0.0):
            return None
    reference_variants = _surface_parameterization_variants(reference)
    if not reference_variants:
        return None
    reference_lattice = reference_variants[0][1][
        "control_lattice_values_local_xyz_weight"
    ]
    candidate_lattice = candidate.get("control_lattice_values_local_xyz_weight")
    if not isinstance(candidate_lattice, np.ndarray) or candidate_lattice.shape != reference_lattice.shape:
        return None
    return float(np.max(np.abs(reference_lattice - candidate_lattice)))


def _component_sample_residual(
    member_ids: list[str], signature_by_id: dict[str, dict[str, Any]]
) -> float | None:
    values = [
        signature_by_id[face_id].get("transformed_sample_residual_mm")
        for face_id in member_ids
    ]
    measured = [float(value) for value in values if value is not None]
    return round(max(measured), 6) if measured else None


def _blade_topology_support_evidence(
    member_ids: list[str],
    signature_by_id: dict[str, dict[str, Any]],
    adjacency: dict[str, list[str]],
    rotational_ids: set[str],
    outer_radius: float,
) -> dict[str, Any]:
    members = [signature_by_id[face_id] for face_id in member_ids]
    radial_min = min(float(item["radial_bounds_mm"][0]) for item in members)
    radial_max = max(float(item["radial_bounds_mm"][1]) for item in members)
    axial_min = min(float(item["axial_bounds_mm"][0]) for item in members)
    axial_max = max(float(item["axial_bounds_mm"][1]) for item in members)
    radial_extent = radial_max - radial_min
    axial_extent = axial_max - axial_min
    signature_family_count = len({item["signature_hash"] for item in members})
    internal_adjacency_pairs = {
        tuple(sorted((face_id, neighbor)))
        for face_id in member_ids
        for neighbor in adjacency.get(face_id, [])
        if neighbor in member_ids and neighbor != face_id
    }
    support_face_ids = sorted(
        {
            neighbor
            for face_id in member_ids
            for neighbor in adjacency.get(face_id, [])
            if neighbor not in rotational_ids
        }
    )
    minimum_radial_extent = max(3.0, 0.15 * outer_radius)
    minimum_outer_support_radius = 0.6 * outer_radius
    compact_local_feature = (
        radial_extent < max(2.5, 0.1 * outer_radius)
        and radial_max < minimum_outer_support_radius
        and axial_extent < max(2.5, 0.1 * outer_radius)
    )
    hole_compatible_geometry = all(
        item["geometry_type"] in {"CYLINDER", "CONE", "PLANE", "TORUS"}
        for item in members
    )
    auxiliary_hole_like = compact_local_feature and hole_compatible_geometry
    checks = {
        "connected_periodic_face_count": len(member_ids) >= 2,
        "multiple_face_signature_families": signature_family_count >= 2,
        "internal_topology_connected": len(internal_adjacency_pairs)
        >= max(1, len(member_ids) - 1),
        "nonperiodic_material_support_adjacency": bool(support_face_ids),
        "streamwise_radial_extent": radial_extent >= minimum_radial_extent,
        "outer_flowpath_support_reached": radial_max
        >= minimum_outer_support_radius,
        "not_compact_auxiliary_hole_like": not auxiliary_hole_like,
    }
    accepted = all(checks.values())
    if auxiliary_hole_like:
        classification = "auxiliary_hole_like_subtractive_feature"
    elif accepted:
        classification = "blade_related_periodic_component"
    else:
        classification = "unsupported_rotational_component"
    return {
        "method": "connected_topology_streamwise_support_and_material_adjacency_r3",
        "classification": classification,
        "accepted_as_blade_related": accepted,
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm"},
        "tolerance": {
            "minimum_radial_extent_mm": round(minimum_radial_extent, 6),
            "minimum_outer_support_radius_mm": round(
                minimum_outer_support_radius, 6
            ),
        },
        "confidence": {
            "level": "deterministic_topology_and_support_gate",
            "passed_check_count": sum(checks.values()),
            "required_check_count": len(checks),
        },
        "residual": {
            "radial_extent_margin_mm": round(
                radial_extent - minimum_radial_extent, 6
            ),
            "outer_support_margin_mm": round(
                radial_max - minimum_outer_support_radius, 6
            ),
        },
        "checks": checks,
        "measurements": {
            "radial_bounds_mm": [round(radial_min, 6), round(radial_max, 6)],
            "axial_bounds_mm": [round(axial_min, 6), round(axial_max, 6)],
            "radial_extent_mm": round(radial_extent, 6),
            "axial_extent_mm": round(axial_extent, 6),
            "signature_family_count": signature_family_count,
            "internal_adjacency_pair_count": len(internal_adjacency_pairs),
        },
        "provenance": {
            "authority": "uploaded_step_brep_topology_and_trimmed_face_samples",
            "source_entity_ids": sorted(member_ids),
            "support_face_ids": support_face_ids,
        },
    }


def _face_normal(face, matrix: np.ndarray) -> np.ndarray:
    try:
        vector = np.asarray(face.normalAt().toTuple(), dtype=float)
        normal = matrix[:3, :3] @ vector
        return normal / max(float(np.linalg.norm(normal)), 1.0e-15)
    except Exception:
        return np.zeros(3, dtype=float)


def _source_diameter(source_manifest: dict[str, Any]) -> float:
    bounds = source_manifest.get("bounds_mm", {})
    minimum = np.asarray(bounds.get("minimum", [0.0, 0.0, 0.0]), dtype=float)
    maximum = np.asarray(bounds.get("maximum", [0.0, 0.0, 0.0]), dtype=float)
    return max(float(np.linalg.norm(maximum - minimum)), 1.0)


def _canonical_line_direction(direction) -> np.ndarray:
    value = np.asarray(direction, dtype=float)
    value /= max(float(np.linalg.norm(value)), 1.0e-15)
    for component in value:
        if abs(float(component)) <= 1.0e-12:
            continue
        return value if component > 0.0 else -value
    return value


def _axis_angle_deg(first, second) -> float:
    first_value = np.asarray(first, dtype=float)
    second_value = np.asarray(second, dtype=float)
    cosine = min(1.0, max(-1.0, abs(float(np.dot(first_value, second_value)))))
    return math.degrees(math.acos(cosine))


def _line_distance(
    first_origin, first_direction, second_origin, second_direction
) -> float:
    first_origin = np.asarray(first_origin, dtype=float)
    second_origin = np.asarray(second_origin, dtype=float)
    first_direction = np.asarray(first_direction, dtype=float)
    second_direction = np.asarray(second_direction, dtype=float)
    cross = np.cross(first_direction, second_direction)
    cross_norm = float(np.linalg.norm(cross))
    delta = second_origin - first_origin
    if cross_norm <= 1.0e-12:
        return float(np.linalg.norm(np.cross(delta, first_direction)))
    return abs(float(np.dot(delta, cross / cross_norm)))


def _rotation_to_positive_z(direction: np.ndarray) -> np.ndarray:
    source = direction / max(float(np.linalg.norm(direction)), 1.0e-15)
    target = np.asarray([0.0, 0.0, 1.0])
    cross = np.cross(source, target)
    sine = float(np.linalg.norm(cross))
    cosine = float(np.dot(source, target))
    if sine <= 1.0e-12:
        return np.eye(3) if cosine > 0.0 else np.diag([1.0, -1.0, -1.0])
    skew = np.asarray(
        [
            [0.0, -cross[2], cross[1]],
            [cross[2], 0.0, -cross[0]],
            [-cross[1], cross[0], 0.0],
        ]
    )
    return np.eye(3) + skew + skew @ skew * ((1.0 - cosine) / (sine**2))


def _transverse_basis(direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    reference = np.asarray([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, direction))) > 0.9:
        reference = np.asarray([0.0, 1.0, 0.0])
    basis_x = reference - direction * float(np.dot(reference, direction))
    basis_x /= max(float(np.linalg.norm(basis_x)), 1.0e-15)
    basis_y = np.cross(direction, basis_x)
    return basis_x, basis_y


def _transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    return (homogeneous @ matrix.T)[:, :3]


def _transform_point(point, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.asarray([*point, 1.0], dtype=float)
    return (matrix @ homogeneous)[:3]


def _round_vector(values, digits: int) -> list[float]:
    return [_quantize(float(value), digits) for value in values]


def _quantize(value: float, digits: int) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0.0 else rounded


def _symmetric_ratio(first: float, second: float) -> float:
    maximum = max(float(first), float(second))
    return min(float(first), float(second)) / maximum if maximum > 0.0 else 1.0
