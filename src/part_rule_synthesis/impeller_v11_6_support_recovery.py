from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np
from scipy.optimize import minimize

from .impeller_v11_2_canonical import clamped_uniform_knots


V112_PROFILE_CONTROL_COUNT = 6
V112_PROFILE_DEGREE = 3
_EPSILON = 1.0e-12
_DEFAULT_SOURCE_TOLERANCE_MM = 1.0e-7
_TIP_ADJACENT_FACE_ROLES = {"side", "edge"}
_DENSE_CORRESPONDENCE_SAMPLE_COUNT = 4097
_DENSE_CONNECTOR_SAMPLE_COUNT = 513
_DUPLICATE_PATH_SAMPLE_COUNT = 257
_MINIMUM_THICKNESS_SAMPLES_PER_PAIR = 2
_MAX_AUTHENTICATED_SUPPORT_CLIPPED_RADIAL_FRACTION = 0.25
_EVIDENCE_SECRET = secrets.token_bytes(32)
_PARTITION_DIGEST_BY_SOURCE_SOLID: dict[str, str] = {}
_SOURCE_SOLID_IDENTITIES_BY_HASH: dict[int, list[tuple[Any, str]]] = {}
_HUB_SUPPORT_ROLE = "hub_flowpath_support"
_INNER_SHROUD_ROLE = "inner_shroud_flowpath_support"
_OUTER_SHROUD_ROLE = "outer_shroud_material_support"
_EXCLUDED_HUB_FLAGS = (
    "periodic_blade_related",
    "root_blend",
    "hole_boundary",
    "local_edge_treatment",
)


class SupportRecoveryError(ValueError):
    def __init__(self, reason: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


class _AuthenticatedOcctEvidence(Mapping[str, Any]):
    """Tamper-evident evidence emitted only after OCCT evaluation/classification."""

    __slots__ = ("__digest", "__kind", "__payload")

    def __init__(self, kind: str, payload: Mapping[str, Any]) -> None:
        self.__kind = kind
        self.__payload = deepcopy(dict(payload))
        self.__digest = _evidence_digest(kind, self.__payload)

    def __getitem__(self, key: str) -> Any:
        return deepcopy(self.__payload[key])

    def __iter__(self):
        return iter(self.__payload)

    def __len__(self) -> int:
        return len(self.__payload)

    def _verified_payload(self, kind: str) -> dict[str, Any]:
        if kind != self.__kind or not hmac.compare_digest(
            self.__digest,
            _evidence_digest(self.__kind, self.__payload),
        ):
            raise ValueError(f"authenticated OCCT {kind} evidence is invalid or was modified")
        return deepcopy(self.__payload)

    def _canonical_digest(self, kind: str) -> str:
        self._verified_payload(kind)
        return _canonical_payload_digest(self.__payload)


class _AuthenticatedSupportResult(dict[str, Any]):
    """JSON-safe, externally immutable result with a module-private capability proof."""

    __slots__ = ("__capability", "__digest")

    def __init__(self, capability: str, payload: Mapping[str, Any]) -> None:
        projection = deepcopy(dict(payload))
        if "authenticated_result_projection" in projection:
            raise ValueError("authenticated_result_projection is reserved")
        projection_digest = _canonical_payload_digest(projection)
        projection["authenticated_result_projection"] = {
            "capability": capability,
            "payload_digest_sha256": projection_digest,
            "digest_basis": "all_fields_except_authenticated_result_projection",
        }
        dict.__init__(self, projection)
        self.__capability = capability
        self.__digest = _evidence_digest(
            f"support_result:{capability}",
            {key: value for key, value in dict.items(self)},
        )

    def __setitem__(self, key: str, value: Any) -> None:
        raise TypeError("authenticated support results are immutable")

    def __getitem__(self, key: str) -> Any:
        return deepcopy(dict.__getitem__(self, key))

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self:
            return deepcopy(default)
        return self[key]

    def items(self):
        return deepcopy({key: value for key, value in dict.items(self)}).items()

    def values(self):
        return deepcopy({key: value for key, value in dict.items(self)}).values()

    def __delitem__(self, key: str) -> None:
        raise TypeError("authenticated support results are immutable")

    def clear(self) -> None:
        raise TypeError("authenticated support results are immutable")

    def pop(self, key: str, default: Any = None) -> Any:
        raise TypeError("authenticated support results are immutable")

    def popitem(self) -> tuple[str, Any]:
        raise TypeError("authenticated support results are immutable")

    def setdefault(self, key: str, default: Any = None) -> Any:
        raise TypeError("authenticated support results are immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("authenticated support results are immutable")

    def __ior__(self, other: Any):
        raise TypeError("authenticated support results are immutable")

    def _verified_payload(self, allowed_capabilities: set[str]) -> dict[str, Any]:
        payload = {key: value for key, value in dict.items(self)}
        projection = payload.get("authenticated_result_projection")
        digest_basis = {
            key: value for key, value in payload.items() if key != "authenticated_result_projection"
        }
        if (
            self.__capability not in allowed_capabilities
            or not isinstance(projection, Mapping)
            or projection.get("capability") != self.__capability
            or projection.get("payload_digest_sha256")
            != _canonical_payload_digest(digest_basis)
            or not hmac.compare_digest(
                self.__digest,
                _evidence_digest(f"support_result:{self.__capability}", payload),
            )
        ):
            raise ValueError("support result capability or evidence digest is invalid")
        return deepcopy(payload)


def _evidence_digest(kind: str, payload: Mapping[str, Any]) -> bytes:
    serialized = json.dumps(
        {"kind": kind, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(_EVIDENCE_SECRET, serialized, hashlib.sha256).digest()


def _canonical_payload_digest(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def authenticate_occt_semantic_partition(
    source_solid: Any,
    *,
    face_assignments: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Freeze the one Task 3 semantic partition for an OCCT source solid."""

    if not isinstance(face_assignments, Mapping) or not face_assignments:
        raise ValueError("face_assignments must be a non-empty mapping")
    solid_identity = _shape_identity(source_solid, "source_solid")
    source_face_identities = {
        _shape_identity(face, "source face") for face in _iter_source_subshapes(source_solid, "FACE")
    }
    assignments_by_identity: dict[str, dict[str, Any]] = {}
    assignments_by_source_id: dict[str, dict[str, Any]] = {}
    for raw_source_id, raw_assignment in face_assignments.items():
        source_id = _non_empty_string(raw_source_id, "face assignment source id")
        if not isinstance(raw_assignment, Mapping):
            raise ValueError(f"face_assignments[{source_id}] must be a mapping")
        required = {
            "shape",
            "role",
            "alternatives",
            "periodic_instance_id",
            "periodic_blade_related",
            "flowpath_adjacent",
            "root_blend",
            "hole_boundary",
            "local_edge_treatment",
        }
        if set(raw_assignment) != required:
            raise ValueError(f"face_assignments[{source_id}] has incomplete partition fields")
        face = raw_assignment["shape"]
        face_identity = _assert_source_subshape(source_solid, face, "FACE")
        if face_identity in assignments_by_identity:
            raise SupportRecoveryError(
                "v116_source_partition_conflict",
                "one OCCT face identity cannot receive multiple semantic assignments",
                {
                    "first_source_id": assignments_by_identity[face_identity]["source_face_id"],
                    "second_source_id": source_id,
                },
            )
        role = _non_empty_string(raw_assignment["role"], "role")
        alternatives = sorted(
            _identifier_sequence(raw_assignment["alternatives"], "alternatives", require_unique=True)
        )
        if role in alternatives:
            raise ValueError("partition alternatives cannot repeat the selected role")
        periodic_blade_related = _strict_bool(
            raw_assignment["periodic_blade_related"],
            "periodic_blade_related",
        )
        raw_instance_id = raw_assignment["periodic_instance_id"]
        periodic_instance_id = (
            None
            if raw_instance_id is None
            else _non_empty_string(raw_instance_id, "periodic_instance_id")
        )
        if periodic_blade_related != (periodic_instance_id is not None):
            raise ValueError(
                "periodic blade partition assignments require exactly one periodic_instance_id"
            )
        classification = {
            "semantic_role": role,
            "classification_authority": "task3_source_solid_semantic_partition",
            "periodic_instance_id": periodic_instance_id,
            "periodic_blade_related": periodic_blade_related,
            "flowpath_adjacent": _strict_bool(
                raw_assignment["flowpath_adjacent"],
                "flowpath_adjacent",
            ),
            "root_blend": _strict_bool(raw_assignment["root_blend"], "root_blend"),
            "hole_boundary": _strict_bool(
                raw_assignment["hole_boundary"],
                "hole_boundary",
            ),
            "local_edge_treatment": _strict_bool(
                raw_assignment["local_edge_treatment"],
                "local_edge_treatment",
            ),
        }
        record = {
            "source_face_id": source_id,
            "source_face_shape_identity": face_identity,
            "semantic_classification": classification,
            "alternatives": alternatives,
        }
        assignments_by_identity[face_identity] = record
        assignments_by_source_id[source_id] = record
    if set(assignments_by_identity) != source_face_identities:
        raise SupportRecoveryError(
            "v116_source_partition_incomplete",
            "Task 3 semantic partition must assign every source-solid face exactly once",
            {
                "source_face_count": len(source_face_identities),
                "assigned_face_count": len(assignments_by_identity),
            },
        )
    payload = {
        "source_solid_shape_identity": solid_identity,
        "assignments_by_identity": assignments_by_identity,
        "assignments_by_source_id": assignments_by_source_id,
        "authority": "immutable_task3_source_solid_semantic_partition",
    }
    partition_digest = _canonical_payload_digest(payload)
    previous_digest = _PARTITION_DIGEST_BY_SOURCE_SOLID.get(solid_identity)
    if previous_digest is not None and previous_digest != partition_digest:
        raise SupportRecoveryError(
            "v116_source_partition_conflict",
            "a conflicting Task 3 semantic partition was already frozen for this source solid",
            {"source_solid_shape_identity": solid_identity},
        )
    _PARTITION_DIGEST_BY_SOURCE_SOLID[solid_identity] = partition_digest
    payload["partition_digest"] = partition_digest
    return _AuthenticatedOcctEvidence("semantic_partition", payload)


def authenticate_occt_face_semantics(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
    raise ValueError(
        "per-face semantic self-signing is forbidden; use authenticate_occt_semantic_partition"
    )


def authenticate_open_tip_population_contract(
    source_solid: Any,
    *,
    topology_records: Sequence[Mapping[str, Any]],
    expected_instance_loop_ids: Mapping[str, Sequence[str]],
    source_face_shapes: Mapping[str, Any],
    source_edge_shapes: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Bind the expected open-tip population to one OCCT source inventory."""

    normalized = adapt_tip_cap_topology_evidence(topology_records)
    expected = _normalize_instance_loop_contract(expected_instance_loop_ids)
    actual = {
        record["periodic_instance_id"]: sorted(
            loop["loop_id"] for loop in record["shared_edge_loops"]
        )
        for record in normalized["records"]
    }
    if actual != expected:
        raise SupportRecoveryError(
            "v116_tip_cap_topology_invalid",
            "independent periodic population contract does not match tip-cap shared loops",
            {"expected": expected, "actual": actual},
        )
    solid_identity = _shape_identity(source_solid, "source_solid")
    face_shapes = _strict_shape_mapping(source_face_shapes, "source_face_shapes")
    edge_shapes = _strict_shape_mapping(source_edge_shapes, "source_edge_shapes")
    required_face_ids = set(normalized["tip_cap_face_ids"]) | set(
        normalized["adjacent_periodic_face_ids"]
    )
    required_edge_ids = set(normalized["shared_source_edge_ids"])
    if set(face_shapes) != required_face_ids or set(edge_shapes) != required_edge_ids:
        raise SupportRecoveryError(
            "v116_tip_cap_topology_invalid",
            "typed open-tip inventory must cover every expected face and shared edge exactly",
        )
    face_identities = {
        source_id: _assert_source_subshape(source_solid, shape, "FACE")
        for source_id, shape in face_shapes.items()
    }
    edge_identities = {
        source_id: _assert_source_subshape(source_solid, shape, "EDGE")
        for source_id, shape in edge_shapes.items()
    }
    for record in normalized["records"]:
        cap_face = face_shapes[record["tip_cap_face_id"]]
        for loop in record["shared_edge_loops"]:
            adjacent_faces = [
                face_shapes[face_record["face_id"]]
                for face_record in loop["adjacent_periodic_faces"]
            ]
            for edge_id in loop["source_edge_ids"]:
                edge = edge_shapes[edge_id]
                try:
                    _assert_source_subshape(cap_face, edge, "EDGE")
                    if not any(
                        _subshape_is_owned_by(face, edge, "EDGE") for face in adjacent_faces
                    ):
                        raise SupportRecoveryError(
                            "v116_tip_cap_topology_invalid",
                            "shared tip edge is not adjacent to a periodic side/edge face",
                        )
                except SupportRecoveryError as exc:
                    raise SupportRecoveryError(
                        "v116_tip_cap_topology_invalid",
                        "declared tip loop is not a shared OCCT cap/periodic-face boundary",
                        {"source_edge_id": edge_id, "cause": str(exc)},
                    ) from exc
    if len(set(face_identities.values())) != len(face_identities) or len(
        set(edge_identities.values())
    ) != len(edge_identities):
        raise SupportRecoveryError(
            "v116_tip_cap_topology_invalid",
            "tip-cap source ids must have globally unique OCCT subshape ownership",
        )
    payload = {
        "source_solid_shape_identity": solid_identity,
        "expected_instance_loop_ids": expected,
        "topology_records": normalized["records"],
        "source_face_shape_identities": face_identities,
        "source_edge_shape_identities": edge_identities,
        "authority": "occt_source_solid_periodic_tip_population",
    }
    payload["population_digest"] = _canonical_payload_digest(payload)
    return _AuthenticatedOcctEvidence("open_tip_population", payload)


def authenticate_closed_shroud_topology(
    source_solid: Any,
    *,
    semantic_partition_evidence: Mapping[str, Any],
    inner_flowpath_faces: Mapping[str, Any],
    outer_material_faces: Mapping[str, Any],
    paired_face_ids: Sequence[Sequence[str]],
    blade_tip_attachment_chains: Mapping[str, Mapping[str, Any]],
    expected_blade_instances: Sequence[str],
    thickness_sample_evidence: Sequence[Mapping[str, Any]],
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    closure_coverage_minimum: float = 0.98,
) -> Mapping[str, Any]:
    """Derive closed-shroud topology claims from one OCCT source-solid inventory."""

    solid_identity = _shape_identity(source_solid, "source_solid")
    if not _source_shape_is_closed(source_solid):
        raise SupportRecoveryError(
            "v116_shroud_topology_ambiguous",
            "closed-shroud evidence requires a valid closed source solid",
        )
    partition = _authenticated_semantic_partition(semantic_partition_evidence)
    if partition["source_solid_shape_identity"] != solid_identity:
        raise SupportRecoveryError(
            "v116_support_source_identity_invalid",
            "closed-shroud topology and semantic partition must bind the same source solid",
        )
    inner = _strict_shape_mapping(inner_flowpath_faces, "inner_flowpath_faces")
    outer = _strict_shape_mapping(outer_material_faces, "outer_material_faces")
    if not isinstance(blade_tip_attachment_chains, Mapping):
        raise ValueError("blade_tip_attachment_chains must be a mapping")
    expected_ids = sorted(
        _identifier_sequence(
            expected_blade_instances,
            "expected_blade_instances",
            require_unique=True,
        )
    )
    if sorted(blade_tip_attachment_chains) != expected_ids or len(expected_ids) < 2:
        raise SupportRecoveryError(
            "v116_shroud_topology_ambiguous",
            "typed shared-edge attachment chains must cover every expected periodic blade instance",
        )
    pairs = _face_pairs(paired_face_ids, "paired_face_ids")
    if {pair[0] for pair in pairs} != set(inner) or {pair[1] for pair in pairs} != set(outer):
        raise SupportRecoveryError(
            "v116_shroud_topology_ambiguous",
            "typed inner/outer faces require one complete declared pairing",
        )
    inner_identities = {
        source_id: _assert_source_subshape(source_solid, shape, "FACE")
        for source_id, shape in inner.items()
    }
    outer_identities = {
        source_id: _assert_source_subshape(source_solid, shape, "FACE")
        for source_id, shape in outer.items()
    }
    owned_identities = [*inner_identities.values(), *outer_identities.values()]
    if len(set(owned_identities)) != len(owned_identities):
        raise SupportRecoveryError(
            "v116_shroud_topology_ambiguous",
            "one OCCT face cannot be aliased into multiple shroud face-pair owners",
        )
    for source_id, identity in inner_identities.items():
        assignment = partition["assignments_by_identity"].get(identity)
        classification = (assignment or {}).get("semantic_classification", {})
        if (
            not isinstance(assignment, Mapping)
            or assignment.get("source_face_id") != source_id
            or classification.get("semantic_role") != _INNER_SHROUD_ROLE
            or classification.get("flowpath_adjacent") is not True
            or classification.get("periodic_blade_related") is not False
        ):
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "inner shroud support is not certified by the source-solid semantic partition",
                {"source_face_id": source_id},
            )
    for source_id, identity in outer_identities.items():
        assignment = partition["assignments_by_identity"].get(identity)
        classification = (assignment or {}).get("semantic_classification", {})
        if (
            not isinstance(assignment, Mapping)
            or assignment.get("source_face_id") != source_id
            or classification.get("semantic_role") != _OUTER_SHROUD_ROLE
            or classification.get("periodic_blade_related") is not False
        ):
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "outer shroud support is not certified by the source-solid semantic partition",
                {"source_face_id": source_id},
            )
    attachment_chains: dict[str, dict[str, str]] = {}
    tip_face_identities: set[str] = set()
    shared_edge_identities: set[str] = set()
    for instance_id in expected_ids:
        raw_chain = blade_tip_attachment_chains[instance_id]
        if not isinstance(raw_chain, Mapping):
            raise ValueError(f"blade_tip_attachment_chains[{instance_id}] must be a mapping")
        required = {
            "tip_face_id",
            "tip_face",
            "inner_shroud_face_id",
            "shared_edge_id",
            "shared_edge",
        }
        if set(raw_chain) != required:
            raise ValueError(
                f"blade_tip_attachment_chains[{instance_id}] has incomplete adjacency fields"
            )
        tip_face_id = _non_empty_string(raw_chain["tip_face_id"], "tip_face_id")
        inner_face_id = _non_empty_string(
            raw_chain["inner_shroud_face_id"],
            "inner_shroud_face_id",
        )
        edge_id = _non_empty_string(raw_chain["shared_edge_id"], "shared_edge_id")
        if inner_face_id not in inner:
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "blade-tip attachment chain references an unpaired inner shroud face",
                {"periodic_instance_id": instance_id},
            )
        tip_face = raw_chain["tip_face"]
        shared_edge = raw_chain["shared_edge"]
        tip_identity = _assert_source_subshape(source_solid, tip_face, "FACE")
        edge_identity = _assert_source_subshape(source_solid, shared_edge, "EDGE")
        inner_face = inner[inner_face_id]
        if not (
            _subshape_is_owned_by(tip_face, shared_edge, "EDGE")
            and _subshape_is_owned_by(inner_face, shared_edge, "EDGE")
            and _edge_has_distinct_end_vertices(shared_edge)
        ):
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "blade-tip face and inner shroud face do not share the declared OCCT edge identity",
                {"periodic_instance_id": instance_id, "shared_edge_id": edge_id},
            )
        assignment = partition["assignments_by_identity"].get(tip_identity)
        classification = (assignment or {}).get("semantic_classification", {})
        if (
            not isinstance(assignment, Mapping)
            or assignment.get("source_face_id") != tip_face_id
            or classification.get("semantic_role") != "periodic_blade_tip_attachment"
            or classification.get("periodic_instance_id") != instance_id
            or classification.get("periodic_blade_related") is not True
            or classification.get("flowpath_adjacent") is not True
        ):
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "attachment face is not a typed periodic blade-tip face in the Task 3 partition",
                {"periodic_instance_id": instance_id, "tip_face_id": tip_face_id},
            )
        if (
            tip_identity in tip_face_identities
            or edge_identity in shared_edge_identities
            or tip_identity in set(owned_identities)
        ):
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "blade attachment chains require unique tip-face and shared-edge ownership",
                {"periodic_instance_id": instance_id},
            )
        tip_face_identities.add(tip_identity)
        shared_edge_identities.add(edge_identity)
        attachment_chains[instance_id] = {
            "tip_face_id": tip_face_id,
            "tip_face_shape_identity": tip_identity,
            "inner_shroud_face_id": inner_face_id,
            "inner_shroud_face_shape_identity": inner_identities[inner_face_id],
            "shared_edge_id": edge_id,
            "shared_edge_shape_identity": edge_identity,
            "adjacency_authority": "occt_exact_shared_edge_identity",
        }
    matrix = _transform_matrix(source_to_canonical_matrix)
    coverage_minimum = float(closure_coverage_minimum)
    if not math.isfinite(coverage_minimum) or not 0.0 < coverage_minimum <= 1.0:
        raise ValueError("closure_coverage_minimum must be finite and in (0,1]")
    inner_coverages = {
        source_id: _occt_face_circumferential_coverage(shape)
        for source_id, shape in inner.items()
    }
    outer_coverages = {
        source_id: _occt_face_circumferential_coverage(shape)
        for source_id, shape in outer.items()
    }
    inner_coverage = min(inner_coverages.values())
    outer_coverage = min(outer_coverages.values())
    circumference_closed = bool(
        inner_coverage >= coverage_minimum and outer_coverage >= coverage_minimum
    )
    thickness_records = _authenticated_thickness_inputs(thickness_sample_evidence)
    expected_pair_identities = {
        (inner_identities[inner_id], outer_identities[outer_id])
        for inner_id, outer_id in pairs
    }
    observed_pair_identities = {
        (record.get("inner_face_shape_identity"), record.get("outer_face_shape_identity"))
        for record in thickness_records
    }
    thickness_bound = bool(
        thickness_records
        and all(
            record.get("source_solid_shape_identity") == solid_identity
            and record.get("faces_are_source_solid_subshapes") is True
            for record in thickness_records
        )
        and observed_pair_identities == expected_pair_identities
    )
    normals_consistent = bool(
        thickness_bound and _thickness_material_normals_consistent(thickness_records)
    )
    payload = {
        "source_solid_shape_identity": solid_identity,
        "semantic_partition_digest": partition["partition_digest"],
        "source_body_is_closed": True,
        "inner_face_shape_identities": inner_identities,
        "outer_face_shape_identities": outer_identities,
        "blade_tip_attachment_chains": attachment_chains,
        "paired_face_ids": pairs,
        "expected_blade_instance_ids": expected_ids,
        "inner_circumferential_coverage": inner_coverage,
        "outer_circumferential_coverage": outer_coverage,
        "inner_face_coverages": inner_coverages,
        "outer_face_coverages": outer_coverages,
        "circumference_closed": circumference_closed,
        "material_side_normals_consistent": normals_consistent,
        "thickness_sample_ids": [record["sample_id"] for record in thickness_records],
        "thickness_bound_to_face_identities": thickness_bound,
        "source_to_canonical_transform": matrix.tolist(),
        "authority": "occt_source_solid_closed_shroud_topology",
    }
    payload["topology_digest"] = _canonical_payload_digest(payload)
    return _AuthenticatedOcctEvidence("closed_shroud_topology", payload)


def fit_hub_profile(
    sample_paths_rz_mm: Sequence[Sequence[Sequence[float]]] = (),
    *,
    source_face_ids: Sequence[str] = (),
    source_face_evidence: Sequence[Mapping[str, Any]] = (),
    endpoints_rz_mm: Sequence[Sequence[float]] | None = None,
    outer_diameter_mm: float,
    material_domain_rz_mm: Sequence[Sequence[float]] | None = None,
    coordinate_frame: str = "canonical_axis_frame_rz_mm",
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
    source_sampling_authority: str = "caller_supplied_sample_paths",
    minimum_radius_mm: float | None = None,
) -> dict[str, Any]:
    authenticated = _authenticated_face_profile_inputs(
        source_face_evidence,
        expected_semantic_roles={_HUB_SUPPORT_ROLE},
        require_hub_candidate=True,
    )
    if authenticated is not None:
        if sample_paths_rz_mm or source_face_ids:
            raise ValueError(
                "source_face_evidence cannot be combined with caller sample paths or face ids"
            )
        projected = _radially_order_authenticated_support_paths(
            authenticated,
            minimum_radius_mm=minimum_radius_mm,
            failure_reason="v116_hub_profile_fit_failed",
        )
        sample_paths_rz_mm = projected["paths_rz_mm"]
        source_face_ids = projected["path_source_ids"]
        coordinate_frame = authenticated["coordinate_frame"]
        source_to_canonical_matrix = authenticated["source_to_canonical_transform"]
        source_tolerance_mm = authenticated["source_tolerance_mm"]
        source_sampling_authority = "occt_trimmed_face_classifier"
        # Promoted fits are bounded by the material-domain classifier that
        # produced the authenticated samples. Caller bounds and endpoints are
        # diagnostic-only and must not steer certified source measurement.
        material_domain_rz_mm = projected["material_domain_rz_mm"]
        endpoints_rz_mm = None
        authenticated_provenance = projected["provenance"]
    else:
        authenticated_provenance = None
    return fit_robust_constrained_cubic_profile(
        sample_paths_rz_mm,
        source_entity_ids=source_face_ids,
        endpoints_rz_mm=endpoints_rz_mm,
        material_domain_rz_mm=material_domain_rz_mm,
        rms_limit_mm=max(0.10, 0.001 * _positive_finite(outer_diameter_mm, "outer_diameter_mm")),
        semantic_role="hub_profile",
        failure_reason="v116_hub_profile_fit_failed",
        coordinate_frame=coordinate_frame,
        source_to_canonical_matrix=source_to_canonical_matrix,
        source_tolerance_mm=source_tolerance_mm,
        source_sampling_authority=source_sampling_authority,
        promoted_pass_eligible=authenticated is not None,
        authenticated_provenance=authenticated_provenance,
    )


def recover_open_tip_reference(
    sample_paths_rz_mm: Sequence[Sequence[Sequence[float]]] = (),
    *,
    source_edge_ids: Sequence[str] = (),
    source_edge_evidence: Sequence[Mapping[str, Any]] = (),
    blade_tip_cap_adjacencies: Sequence[Mapping[str, Any]] = (),
    periodic_population_evidence: Mapping[str, Any] | None = None,
    endpoints_rz_mm: Sequence[Sequence[float]] | None = None,
    outer_diameter_mm: float,
    material_domain_rz_mm: Sequence[Sequence[float]] | None = None,
    coordinate_frame: str = "canonical_axis_frame_rz_mm",
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
    source_sampling_authority: str = "caller_supplied_sample_paths",
) -> dict[str, Any]:
    population_payload = _authenticated_open_tip_population(periodic_population_evidence)
    if population_payload is not None:
        tip_cap_evidence = adapt_tip_cap_topology_evidence(population_payload["topology_records"])
        expected_loop_contract = {
            instance_id: set(loop_ids)
            for instance_id, loop_ids in population_payload["expected_instance_loop_ids"].items()
        }
    else:
        tip_cap_evidence = adapt_tip_cap_topology_evidence(blade_tip_cap_adjacencies)
        expected_loop_contract = {
            record["periodic_instance_id"]: {
                loop["loop_id"] for loop in record["shared_edge_loops"]
            }
            for record in tip_cap_evidence["records"]
        }
    if not tip_cap_evidence["repeated_shared_adjacency"]:
        raise SupportRecoveryError(
            "v116_tip_reference_inference_failed",
            "open tip recovery requires repeated material tip-cap faces joined to "
            "periodic blade faces by shared edge loops",
            {"tip_cap_evidence": tip_cap_evidence},
        )
    authenticated_edges = _authenticated_edge_profile_inputs(source_edge_evidence)
    if authenticated_edges is not None:
        if sample_paths_rz_mm or source_edge_ids:
            raise ValueError(
                "source_edge_evidence cannot be combined with caller sample paths or edge ids"
            )
        sample_paths_rz_mm = authenticated_edges["paths_rz_mm"]
        source_edge_ids = authenticated_edges["source_edge_ids"]
        coordinate_frame = authenticated_edges["coordinate_frame"]
        source_to_canonical_matrix = authenticated_edges["source_to_canonical_transform"]
        source_tolerance_mm = authenticated_edges["source_tolerance_mm"]
        source_sampling_authority = "occt_brep_curve"
        edge_points = np.asarray(
            [point for path in sample_paths_rz_mm for point in path],
            dtype=float,
        )
        padding = max(source_tolerance_mm, 1.0e-6)
        material_domain_rz_mm = (
            (
                float(np.min(edge_points[:, 0]) - padding),
                float(np.max(edge_points[:, 0]) + padding),
            ),
            (
                float(np.min(edge_points[:, 1]) - padding),
                float(np.max(edge_points[:, 1]) + padding),
            ),
        )
        endpoints_rz_mm = None
    fitted_edge_ids = _identifier_sequence(source_edge_ids, "source_edge_ids")
    shared_source_edge_ids = set(tip_cap_evidence["shared_source_edge_ids"])
    edge_ownership = {
        edge_id: {
            "periodic_instance_id": record["periodic_instance_id"],
            "loop_id": loop["loop_id"],
        }
        for record in tip_cap_evidence["records"]
        for loop in record["shared_edge_loops"]
        for edge_id in loop["source_edge_ids"]
    }
    fitted_instances = {
        edge_ownership[edge_id]["periodic_instance_id"]
        for edge_id in fitted_edge_ids
        if edge_id in edge_ownership
    }
    fitted_loops_by_instance: dict[str, set[str]] = {}
    for edge_id in fitted_edge_ids:
        ownership = edge_ownership.get(edge_id)
        if ownership is not None:
            fitted_loops_by_instance.setdefault(ownership["periodic_instance_id"], set()).add(
                ownership["loop_id"]
            )
    expected_instances = set(tip_cap_evidence["periodic_instance_ids"])
    expected_loops_covered = bool(
        expected_instances == set(expected_loop_contract)
        and all(
            fitted_loops_by_instance.get(instance_id, set()) == loop_ids
            for instance_id, loop_ids in expected_loop_contract.items()
        )
    )
    source_solid_matches = bool(
        population_payload is not None
        and authenticated_edges is not None
        and authenticated_edges["source_solid_shape_identity"]
        == population_payload["source_solid_shape_identity"]
    )
    if (
        len(set(fitted_edge_ids)) < 2
        or not set(fitted_edge_ids) <= shared_source_edge_ids
        or fitted_instances != expected_instances
        or not expected_loops_covered
        or (population_payload is not None and not source_solid_matches)
    ):
        raise SupportRecoveryError(
            "v116_tip_reference_inference_failed",
            "open tip profile paths must cover shared tip-cap loops for every periodic blade instance",
            {
                "source_edge_ids": fitted_edge_ids,
                "shared_source_edge_ids": sorted(shared_source_edge_ids),
                "fitted_periodic_instance_ids": sorted(fitted_instances),
                "expected_periodic_instance_ids": sorted(expected_instances),
                "fitted_loop_ids_by_instance": {
                    key: sorted(value) for key, value in fitted_loops_by_instance.items()
                },
                "expected_loop_ids_by_instance": {
                    key: sorted(value) for key, value in expected_loop_contract.items()
                },
                "source_solid_matches": source_solid_matches,
            },
        )

    fit = fit_robust_constrained_cubic_profile(
        sample_paths_rz_mm,
        source_entity_ids=fitted_edge_ids,
        endpoints_rz_mm=endpoints_rz_mm,
        material_domain_rz_mm=material_domain_rz_mm,
        rms_limit_mm=max(0.20, 0.002 * _positive_finite(outer_diameter_mm, "outer_diameter_mm")),
        semantic_role="open_tip_reference",
        failure_reason="v116_tip_reference_inference_failed",
        coordinate_frame=coordinate_frame,
        source_to_canonical_matrix=source_to_canonical_matrix,
        source_tolerance_mm=source_tolerance_mm,
        source_sampling_authority=source_sampling_authority,
        promoted_pass_eligible=bool(
            population_payload is not None
            and authenticated_edges is not None
            and expected_loops_covered
            and source_solid_matches
        ),
        authenticated_provenance=(authenticated_edges or {}).get("provenance"),
    )
    authenticated_fit_payload = (
        fit._verified_payload({"v112_support_fit"})
        if isinstance(fit, _AuthenticatedSupportResult)
        else None
    )
    result = {
        "status": "PASS",
        "semantic_role": "open_tip_reference",
        "material": False,
        "render_default": "hidden",
        "export_default": "excluded",
        "display_policy": {
            "render_default": "hidden",
            "construction_overlay_only": True,
            "material_style_forbidden": True,
        },
        "export_policy": {
            "export_default": "excluded",
            "material_export_forbidden": True,
        },
        "source_tip_caps": {
            "semantic_role": "per_blade_tip_cap",
            "material": True,
            "source_face_ids": tip_cap_evidence["tip_cap_face_ids"],
            "shared_edge_loop_ids": tip_cap_evidence["shared_edge_loop_ids"],
            "shared_source_edge_ids": tip_cap_evidence["shared_source_edge_ids"],
            "periodic_instance_ids": tip_cap_evidence["periodic_instance_ids"],
            "topology_records": tip_cap_evidence["records"],
            "fitted_edge_ownership": {
                edge_id: edge_ownership[edge_id] for edge_id in fitted_edge_ids
            },
            "fitted_periodic_instance_ids": sorted(fitted_instances),
            "covers_expected_periodic_instances": True,
            "covers_every_expected_shared_loop": expected_loops_covered,
            "population_contract_authority": (
                "authenticated_occt_periodic_tip_population"
                if population_payload is not None
                else "legacy_unpromotable_topology_records"
            ),
        },
        "profile_fit": authenticated_fit_payload or fit,
    }
    if authenticated_fit_payload is not None:
        result["evidence_digests"] = {
            "population_contract_digest": population_payload["population_digest"],
            "source_solid_shape_identity": population_payload["source_solid_shape_identity"],
            "profile_fit_digest": _canonical_payload_digest(authenticated_fit_payload),
        }
        return _AuthenticatedSupportResult("open_tip_reference", result)
    return result


def fit_robust_constrained_cubic_profile(
    sample_paths_rz_mm: Sequence[Sequence[Sequence[float]]],
    *,
    source_entity_ids: Sequence[str],
    endpoints_rz_mm: Sequence[Sequence[float]] | None = None,
    material_domain_rz_mm: Sequence[Sequence[float]] | None = None,
    rms_limit_mm: float,
    semantic_role: str,
    failure_reason: str,
    maximum_iterations: int = 20,
    coordinate_frame: str = "canonical_axis_frame_rz_mm",
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
    source_sampling_authority: str = "caller_supplied_sample_paths",
    promoted_pass_eligible: bool = False,
    authenticated_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tolerance = _positive_finite(source_tolerance_mm, "source_tolerance_mm")
    frame = _non_empty_string(coordinate_frame, "coordinate_frame")
    authority = _non_empty_string(source_sampling_authority, "source_sampling_authority")
    transform = _transform_matrix(source_to_canonical_matrix)
    prepared = _prepare_profile_evidence(
        sample_paths_rz_mm,
        source_entity_ids=source_entity_ids,
        endpoints_rz_mm=endpoints_rz_mm,
        failure_reason=failure_reason,
        source_tolerance_mm=tolerance,
    )
    points = prepared["points"]
    parameters = prepared["parameters"]
    arc_weights = prepared["arc_weights"]
    start, end = prepared["endpoints"]
    material_domain = _material_domain(material_domain_rz_mm, failure_reason)
    _validate_endpoint_constraints(start, end, material_domain, failure_reason)

    knots = clamped_uniform_knots(V112_PROFILE_CONTROL_COUNT, V112_PROFILE_DEGREE)
    basis = _basis_matrix(parameters, V112_PROFILE_CONTROL_COUNT, V112_PROFILE_DEGREE, knots)
    robust_weights = np.ones(len(points), dtype=float)
    controls = np.linspace(start, end, V112_PROFILE_CONTROL_COUNT)
    previous_controls: np.ndarray | None = None
    profile_length = float(np.sum(arc_weights))

    for iteration in range(maximum_iterations):
        fit_weights = arc_weights * robust_weights
        if float(np.sum(fit_weights)) <= _EPSILON:
            raise SupportRecoveryError(failure_reason, "robust profile fit rejected all support evidence")
        controls = _solve_constrained_controls(
            basis,
            points,
            fit_weights,
            start,
            end,
            material_domain,
            failure_reason,
        )
        residual_vectors = basis @ controls - points
        parameter_residuals = np.linalg.norm(residual_vectors, axis=1)
        scale = max(
            _weighted_percentile(parameter_residuals, arc_weights, 0.5),
            profile_length * 1.0e-9,
            1.0e-9,
        )
        huber_cutoff = 1.5 * scale
        updated_weights = np.ones_like(robust_weights)
        outlier_mask = parameter_residuals > huber_cutoff
        updated_weights[outlier_mask] = huber_cutoff / np.maximum(parameter_residuals[outlier_mask], _EPSILON)
        if previous_controls is not None and float(np.max(np.abs(controls - previous_controls))) <= 1.0e-9:
            robust_weights = updated_weights
            break
        previous_controls = controls.copy()
        robust_weights = updated_weights
    else:
        iteration = maximum_iterations - 1

    curve_samples = np.asarray(evaluate_profile_rz(controls, np.linspace(0.0, 1.0, 4097)))
    orthogonal_residuals = _nearest_curve_distances(points, curve_samples)
    rejected_mask = robust_weights < 0.5
    inlier_mask = ~rejected_mask
    inlier_weight = float(np.sum(arc_weights[inlier_mask]))
    total_weight = float(np.sum(arc_weights))
    if inlier_weight <= _EPSILON or inlier_weight < 0.5 * total_weight:
        raise SupportRecoveryError(
            failure_reason,
            "robust profile fit retained insufficient arc-length evidence",
            {"retained_arc_length_fraction": _round(inlier_weight / max(total_weight, _EPSILON))},
        )

    inlier_residuals = orthogonal_residuals[inlier_mask]
    inlier_weights = arc_weights[inlier_mask]
    rms = math.sqrt(float(np.average(inlier_residuals**2, weights=inlier_weights)))
    p95 = _weighted_percentile(inlier_residuals, inlier_weights, 0.95)
    maximum = float(np.max(inlier_residuals))
    all_rms = math.sqrt(float(np.average(orthogonal_residuals**2, weights=arc_weights)))
    limit = _positive_finite(rms_limit_mm, "rms_limit_mm")
    if rms > limit:
        raise SupportRecoveryError(
            failure_reason,
            f"{semantic_role} orthogonal RMS {rms:.6f} mm exceeds {limit:.6f} mm",
            {
                "orthogonal_rms_mm": _round(rms),
                "rms_limit_mm": _round(limit),
                "control_points_rz_mm": _rounded_points(controls),
            },
        )

    rejected_samples = []
    for index in np.flatnonzero(rejected_mask):
        rejected_samples.append(
            {
                "source_entity_id": prepared["sample_source_ids"][int(index)],
                "path_index": prepared["sample_path_indices"][int(index)],
                "sample_index": prepared["sample_local_indices"][int(index)],
                "global_parameter": _round(parameters[index]),
                "point_rz_mm": [_round(value) for value in points[index]],
                "orthogonal_residual_mm": _round(orthogonal_residuals[index]),
                "robust_weight": _round(robust_weights[index]),
            }
        )
    rejected_source_ids = sorted({record["source_entity_id"] for record in rejected_samples})
    accepted_samples = []
    for index in np.flatnonzero(inlier_mask):
        accepted_samples.append(
            {
                "source_entity_id": prepared["sample_source_ids"][int(index)],
                "path_index": prepared["sample_path_indices"][int(index)],
                "sample_index": prepared["sample_local_indices"][int(index)],
                "global_parameter": _round(parameters[index]),
                "point_rz_mm": [_round(value) for value in points[index]],
                "arc_length_weight_mm": _round(arc_weights[index]),
                "projection_fidelity": "sampled_projection_not_exact_brep",
            }
        )
    result = {
        "status": "PASS",
        "semantic_role": semantic_role,
        "fit_method": "arc_length_weighted_robust_constrained_clamped_cubic",
        "weighting": "meridional_arc_length_voronoi",
        "parameterization": "global_radial_ordered_meridional_arc_length",
        "path_parameter_ranges": prepared["path_parameter_ranges"],
        "control_count": V112_PROFILE_CONTROL_COUNT,
        "degree": V112_PROFILE_DEGREE,
        "knots": knots,
        "weights": [1.0] * V112_PROFILE_CONTROL_COUNT,
        "weights_assumption": "v1_1_2_explicit_all_one",
        "control_points_rz_mm": _rounded_points(controls),
        "endpoint_constraints": True,
        "constraints": {
            "radial_order": "nondecreasing",
            "axial_order": "unconstrained",
            "axial_monotonicity_required": False,
            "material_domain_rz_mm": [[_round(value) for value in bounds] for bounds in material_domain],
            "satisfied": _controls_satisfy_constraints(controls, material_domain),
        },
        "source_entity_ids": sorted(set(prepared["path_source_ids"])),
        "sample_path_count": len(prepared["path_lengths"]),
        "sample_count": len(points),
        "accepted_sample_count": int(np.count_nonzero(inlier_mask)),
        "accepted_samples": accepted_samples,
        "rejected_sample_count": int(np.count_nonzero(rejected_mask)),
        "rejected_source_ids": rejected_source_ids,
        "rejected_samples": rejected_samples,
        "meridional_arc_length_mm": _round(total_weight),
        "duplicate_path_normalization": prepared["duplicate_path_normalization"],
        "provenance": {
            "coordinate_frame": frame,
            "source_to_canonical_transform": transform.tolist(),
            "source_tolerance_mm": _round(tolerance),
            "source_sampling_authority": authority,
            "projection_fidelity": "sampled_projection_not_exact_brep",
            "accepted_sample_provenance_recorded": True,
            "material_domain_explicit": True,
            "authenticated_occt_trimmed_material_domain": bool(promoted_pass_eligible),
            **dict(authenticated_provenance or {}),
        },
        "residuals": {
            "definition": "orthogonal_nearest_point_on_fitted_profile",
            "orthogonal_rms_mm": _round(rms),
            "orthogonal_p95_mm": _round(p95),
            "orthogonal_maximum_mm": _round(maximum),
            "all_sample_orthogonal_rms_mm": _round(all_rms),
        },
        "robust_iterations": iteration + 1,
        "global_vertex_envelope_fallback_used": False,
        "acceptance": {
            "status": "PASS",
            "rms_limit_mm": _round(limit),
            "promoted_pass_eligible": bool(promoted_pass_eligible),
            "fallback_policy": "source_classified_brep_evidence_required",
            "material_domain_policy": "explicit_material_domain_required",
        },
    }
    if promoted_pass_eligible:
        return _AuthenticatedSupportResult("v112_support_fit", result)
    return result


def evaluate_profile_rz(
    control_points_rz_mm: Sequence[Sequence[float]],
    parameters: Sequence[float] | np.ndarray,
) -> list[list[float]]:
    controls = np.asarray(control_points_rz_mm, dtype=float)
    if controls.shape != (V112_PROFILE_CONTROL_COUNT, 2) or not np.all(np.isfinite(controls)):
        raise ValueError("control_points_rz_mm must contain six finite (R,Z) points")
    values = np.asarray(parameters, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)) or np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("parameters must be finite values in [0,1]")
    knots = clamped_uniform_knots(V112_PROFILE_CONTROL_COUNT, V112_PROFILE_DEGREE)
    return (_basis_matrix(values, V112_PROFILE_CONTROL_COUNT, V112_PROFILE_DEGREE, knots) @ controls).tolist()


def validate_hub_tip_correspondence(
    hub_control_points_rz_mm: Sequence[Sequence[float]],
    tip_control_points_rz_mm: Sequence[Sequence[float]],
    *,
    correspondence: Sequence[Sequence[float]] | None = None,
    minimum_span_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
    intersection_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
) -> dict[str, Any]:
    minimum_span = _positive_finite(minimum_span_mm, "minimum_span_mm")
    tolerance = _positive_finite(intersection_tolerance_mm, "intersection_tolerance_mm")
    if correspondence is None:
        values = np.linspace(0.0, 1.0, 65)
        mapping = np.column_stack((values, values))
    else:
        raw_mapping = _strict_sequence(correspondence, "correspondence")
        try:
            for index, pair in enumerate(raw_mapping):
                pair_values = _strict_sequence(pair, f"correspondence[{index}]")
                if len(pair_values) != 2:
                    raise ValueError
            mapping = np.asarray(raw_mapping, dtype=float)
        except (TypeError, ValueError) as exc:
            raise SupportRecoveryError(
                "v116_support_correspondence_invalid",
                "hub-tip correspondence must contain numeric (hub_u, tip_v) pairs",
            ) from exc
    if (
        mapping.ndim != 2
        or mapping.shape[1:] != (2,)
        or len(mapping) < 2
        or not np.all(np.isfinite(mapping))
        or np.any(mapping < 0.0)
        or np.any(mapping > 1.0)
    ):
        raise SupportRecoveryError(
            "v116_support_correspondence_invalid",
            "hub-tip correspondence must contain finite (hub_u, tip_v) pairs in [0,1]",
        )
    endpoint_tolerance = 1.0e-9
    flowwise_order_preserved = bool(
        np.all(np.diff(mapping[:, 0]) > 0.0)
        and np.all(np.diff(mapping[:, 1]) > 0.0)
        and np.allclose(mapping[0], [0.0, 0.0], atol=endpoint_tolerance)
        and np.allclose(mapping[-1], [1.0, 1.0], atol=endpoint_tolerance)
    )
    if not flowwise_order_preserved:
        raise SupportRecoveryError(
            "v116_support_correspondence_invalid",
            "hub-tip correspondence must preserve strict endpoint-to-endpoint flowwise order",
        )

    dense_hub_parameters = np.linspace(0.0, 1.0, _DENSE_CORRESPONDENCE_SAMPLE_COUNT)
    dense_tip_parameters = np.interp(dense_hub_parameters, mapping[:, 0], mapping[:, 1])
    dense_corresponding_hub = np.asarray(
        evaluate_profile_rz(hub_control_points_rz_mm, dense_hub_parameters)
    )
    dense_corresponding_tip = np.asarray(
        evaluate_profile_rz(tip_control_points_rz_mm, dense_tip_parameters)
    )
    dense_span_lengths = np.linalg.norm(dense_corresponding_tip - dense_corresponding_hub, axis=1)
    dense_values = np.linspace(0.0, 1.0, 257)
    dense_hub = np.asarray(evaluate_profile_rz(hub_control_points_rz_mm, dense_values))
    dense_tip = np.asarray(evaluate_profile_rz(tip_control_points_rz_mm, dense_values))
    support_curves_non_crossing = not _polylines_intersect(dense_hub, dense_tip, tolerance)
    connector_indices = np.linspace(
        0,
        len(dense_corresponding_hub) - 1,
        _DENSE_CONNECTOR_SAMPLE_COUNT,
        dtype=int,
    )
    connector_hub = dense_corresponding_hub[connector_indices]
    connector_tip = dense_corresponding_tip[connector_indices]
    span_segments_non_crossing = not _span_segments_cross_bounded(
        connector_hub,
        connector_tip,
        tolerance,
    )
    positive_separation = bool(
        np.all(np.isfinite(dense_span_lengths)) and np.all(dense_span_lengths > minimum_span)
    )
    if not (support_curves_non_crossing and span_segments_non_crossing and positive_separation):
        raise SupportRecoveryError(
            "v116_support_correspondence_invalid",
            "hub-tip supports or correspondence span segments cross or lose positive separation",
            {
                "support_curves_non_crossing": support_curves_non_crossing,
                "span_segments_non_crossing": span_segments_non_crossing,
                "minimum_measured_span_mm": _round(float(np.min(dense_span_lengths))),
                "minimum_required_span_mm": _round(minimum_span),
                "dense_correspondence_sample_count": len(dense_span_lengths),
                "dense_connector_sample_count": len(connector_hub),
            },
        )
    return {
        "status": "PASS",
        "method": "strict_monotone_parameter_correspondence_with_meridional_segment_intersection",
        "flowwise_order_preserved": True,
        "support_curves_non_crossing": True,
        "span_segments_non_crossing": True,
        "positive_span_separation": True,
        "minimum_span_mm": _round(float(np.min(dense_span_lengths))),
        "minimum_span_evaluation": "dense_interpolated_hub_tip_correspondence",
        "dense_correspondence_sample_count": len(dense_span_lengths),
        "dense_connector_sample_count": len(connector_hub),
        "correspondence": [[_round(value) for value in pair] for pair in mapping],
        "axial_monotonicity_required": False,
    }


def decide_shroud_topology(
    *,
    blade_tip_cap_adjacencies: Sequence[Mapping[str, Any]] = (),
    inner_flowpath_face_ids: Sequence[str] = (),
    outer_material_face_ids: Sequence[str] = (),
    paired_face_ids: Sequence[Sequence[str]] = (),
    thickness_samples_mm: Sequence[float] = (),
    thickness_sample_face_pairs: Sequence[Sequence[str]] = (),
    thickness_sample_evidence: Sequence[Mapping[str, Any]] = (),
    inner_profile_evidence: Sequence[Mapping[str, Any]] = (),
    outer_profile_evidence: Sequence[Mapping[str, Any]] = (),
    inner_circumferential_coverage: float = 0.0,
    outer_circumferential_coverage: float = 0.0,
    circumference_closed: bool = False,
    blade_tip_attachment_instance_ids: Sequence[str] = (),
    material_side_normals_consistent: bool = False,
    expected_blade_instances: int | Sequence[str] | None = None,
    source_body_is_closed: bool | None = None,
    candidate_face_metadata: Sequence[Mapping[str, Any]] = (),
    closure_coverage_minimum: float = 0.98,
    topology_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    circumference_closed = _strict_bool(circumference_closed, "circumference_closed")
    material_side_normals_consistent = _strict_bool(
        material_side_normals_consistent,
        "material_side_normals_consistent",
    )
    declared_source_body_closed = (
        None
        if source_body_is_closed is None
        else _strict_bool(source_body_is_closed, "source_body_is_closed")
    )
    source_body_is_closed = bool(declared_source_body_closed)
    inner_ids = _unique_strings(inner_flowpath_face_ids, "inner_flowpath_face_ids")
    outer_ids = _unique_strings(outer_material_face_ids, "outer_material_face_ids")
    attachments = _unique_strings(
        blade_tip_attachment_instance_ids,
        "blade_tip_attachment_instance_ids",
    )
    pairs = _face_pairs(paired_face_ids, "paired_face_ids")
    authenticated_thickness_records = _authenticated_thickness_inputs(thickness_sample_evidence)
    if authenticated_thickness_records:
        if thickness_samples_mm or thickness_sample_face_pairs:
            raise ValueError(
                "thickness_sample_evidence cannot be combined with legacy scalar thickness inputs"
            )
        thickness = np.asarray(
            [record["thickness_mm"] for record in authenticated_thickness_records],
            dtype=float,
        )
        sample_face_pairs = [
            [record["inner_face_id"], record["outer_face_id"]]
            for record in authenticated_thickness_records
        ]
        thickness_authenticated = True
    else:
        thickness = _numeric_sequence(thickness_samples_mm, "thickness_samples_mm")
        sample_face_pairs = _face_pairs(
            thickness_sample_face_pairs,
            "thickness_sample_face_pairs",
            allow_duplicates=True,
        )
        thickness_authenticated = False
    candidate_records = _mapping_sequence(candidate_face_metadata, "candidate_face_metadata")
    tip_cap_evidence = _tip_cap_evidence(blade_tip_cap_adjacencies)
    expected_instance_ids, expected_instance_count = _expected_instance_contract(expected_blade_instances)
    topology_payload = _authenticated_closed_shroud_topology(topology_evidence)
    if topology_payload is not None:
        typed_inner_ids = sorted(topology_payload["inner_face_shape_identities"])
        typed_outer_ids = sorted(topology_payload["outer_face_shape_identities"])
        typed_pairs = [list(pair) for pair in topology_payload["paired_face_ids"]]
        typed_attachments = sorted(topology_payload["expected_blade_instance_ids"])
        for plain, typed, name in (
            (inner_ids, typed_inner_ids, "inner_flowpath_face_ids"),
            (outer_ids, typed_outer_ids, "outer_material_face_ids"),
            (pairs, typed_pairs, "paired_face_ids"),
            (attachments, typed_attachments, "blade_tip_attachment_instance_ids"),
        ):
            if plain and plain != typed:
                raise ValueError(f"{name} conflicts with authenticated closed-shroud topology")
        if expected_instance_ids is not None and expected_instance_ids != typed_attachments:
            raise ValueError("expected_blade_instances conflicts with authenticated topology")
        inner_ids = typed_inner_ids
        outer_ids = typed_outer_ids
        pairs = typed_pairs
        attachments = typed_attachments
        expected_instance_ids = typed_attachments
        expected_instance_count = len(typed_attachments)
        source_body_is_closed = bool(
            topology_payload["source_body_is_closed"]
            and declared_source_body_closed is not False
        )
        inner_circumferential_coverage = topology_payload["inner_circumferential_coverage"]
        outer_circumferential_coverage = topology_payload["outer_circumferential_coverage"]
        circumference_closed = bool(topology_payload["circumference_closed"])
        material_side_normals_consistent = bool(
            topology_payload["material_side_normals_consistent"]
        )
    inner_profile = _fit_authenticated_support_profile(
        inner_profile_evidence,
        semantic_role="inner_shroud_flowpath_profile",
        expected_source_role=_INNER_SHROUD_ROLE,
    )
    outer_profile = _fit_authenticated_support_profile(
        outer_profile_evidence,
        semantic_role="outer_shroud_material_profile",
        expected_source_role=_OUTER_SHROUD_ROLE,
    )
    topology_solid_identity = (
        topology_payload["source_solid_shape_identity"] if topology_payload is not None else None
    )
    profile_evidence_complete = bool(
        inner_profile is not None
        and outer_profile is not None
        and set(inner_profile["source_entity_ids"]) == set(inner_ids)
        and set(outer_profile["source_entity_ids"]) == set(outer_ids)
        and topology_payload is not None
        and inner_profile["provenance"].get("source_solid_shape_identity")
        == topology_solid_identity
        and outer_profile["provenance"].get("source_solid_shape_identity")
        == topology_solid_identity
    )
    finite_positive_thickness = bool(
        len(thickness) and np.all(np.isfinite(thickness)) and np.all(thickness > _EPSILON)
    )
    distinct_inner_outer_faces = bool(inner_ids and outer_ids and set(inner_ids).isdisjoint(outer_ids))
    paired_material_faces = bool(
        distinct_inner_outer_faces
        and pairs
        and len(pairs) == len(inner_ids) == len(outer_ids)
        and {pair[0] for pair in pairs} == set(inner_ids)
        and {pair[1] for pair in pairs} == set(outer_ids)
        and all(pair[0] != pair[1] for pair in pairs)
    )
    coverage_minimum = float(closure_coverage_minimum)
    if not math.isfinite(coverage_minimum) or not 0.0 < coverage_minimum <= 1.0:
        raise ValueError("closure_coverage_minimum must be finite and in (0,1]")
    inner_coverage = _coverage_value(inner_circumferential_coverage)
    outer_coverage = _coverage_value(outer_circumferential_coverage)
    bounded_coverage = bool(
        _coverage_bounded(inner_coverage)
        and _coverage_bounded(outer_coverage)
    )
    circumferential_faces = bool(
        bounded_coverage
        and circumference_closed
        and _coverage_complete(inner_coverage, coverage_minimum)
        and _coverage_complete(outer_coverage, coverage_minimum)
    )
    attachments_cover_expected = bool(
        expected_instance_count is not None
        and len(attachments) == expected_instance_count
        and (
            expected_instance_ids is None
            or set(attachments) == set(expected_instance_ids)
        )
    )
    repeated_attachment = bool(len(attachments) >= 2 and attachments_cover_expected)
    declared_pair_keys = {tuple(pair) for pair in pairs}
    associated_sample_pairs = sample_face_pairs
    association_method = (
        "authenticated_occt_sample_to_face_pair_association"
        if thickness_authenticated
        else "legacy_unpromotable_scalar_association"
    )
    associated_pair_keys = [tuple(pair) for pair in associated_sample_pairs]
    thickness_samples_associated = bool(
        len(associated_sample_pairs) == len(thickness)
        and len(thickness)
        and all(pair in declared_pair_keys for pair in associated_pair_keys)
    )
    thickness_evidence_covers_pairs = bool(
        thickness_samples_associated and set(associated_pair_keys) == declared_pair_keys
    )
    pair_sample_counts = {
        pair: associated_pair_keys.count(pair)
        for pair in declared_pair_keys
    }
    adequate_thickness_samples = bool(
        thickness_evidence_covers_pairs
        and all(
            count >= _MINIMUM_THICKNESS_SAMPLES_PER_PAIR
            for count in pair_sample_counts.values()
        )
    )
    independent_thickness_samples = _independent_thickness_coverage(
        authenticated_thickness_records,
        declared_pair_keys,
    )
    continuous_finite_thickness_shell = bool(
        inner_ids
        and outer_ids
        and paired_material_faces
        and finite_positive_thickness
        and thickness_samples_associated
        and thickness_evidence_covers_pairs
        and adequate_thickness_samples
        and thickness_authenticated
        and independent_thickness_samples
        and profile_evidence_complete
        and circumferential_faces
        and topology_payload is not None
        and topology_payload["thickness_bound_to_face_identities"] is True
    )
    closed_complete = bool(
        continuous_finite_thickness_shell
        and repeated_attachment
        and material_side_normals_consistent
        and source_body_is_closed
        and topology_payload is not None
    )
    repeated_tip_caps = tip_cap_evidence["repeated_shared_adjacency"]
    tip_cap_instance_ids = tip_cap_evidence["periodic_instance_ids"]
    tip_caps_cover_expected = bool(
        expected_instance_count is not None
        and len(tip_cap_instance_ids) == expected_instance_count
        and (
            expected_instance_ids is None
            or set(tip_cap_instance_ids) == set(expected_instance_ids)
        )
    )
    complete_open_tip_cap_evidence = bool(
        repeated_tip_caps and tip_caps_cover_expected and bounded_coverage
    )
    conflict = closed_complete and repeated_tip_caps
    partial_closed_evidence = bool(
        inner_ids
        or outer_ids
        or pairs
        or len(thickness)
        or circumference_closed
        or attachments
        or sample_face_pairs
        or not bounded_coverage
        or (math.isfinite(inner_coverage) and inner_coverage > 0.0)
        or (math.isfinite(outer_coverage) and outer_coverage > 0.0)
    )

    checks = {
        "inner_circumferential_flowpath_face": bool(inner_ids),
        "outer_circumferential_material_face": bool(outer_ids),
        "distinct_inner_outer_faces": distinct_inner_outer_faces,
        "paired_material_faces": paired_material_faces,
        "finite_positive_thickness": finite_positive_thickness,
        "thickness_samples_associated_with_face_pairs": thickness_samples_associated,
        "thickness_evidence_covers_all_face_pairs": thickness_evidence_covers_pairs,
        "adequate_thickness_samples_per_face_pair": adequate_thickness_samples,
        "authenticated_occt_thickness_evidence": thickness_authenticated,
        "independent_thickness_samples_per_face_pair": independent_thickness_samples,
        "inner_outer_profile_evidence_complete": profile_evidence_complete,
        "bounded_circumferential_coverage": bounded_coverage,
        "continuous_full_circumference": circumferential_faces,
        "repeated_blade_tip_attachment": repeated_attachment,
        "attachments_cover_expected_blade_instances": attachments_cover_expected,
        "material_side_normals_consistent": bool(material_side_normals_consistent),
        "continuous_finite_thickness_shroud": continuous_finite_thickness_shell,
        "repeated_per_blade_tip_cap_adjacency": repeated_tip_caps,
        "tip_caps_cover_expected_blade_instances": tip_caps_cover_expected,
        "complete_per_instance_tip_cap_evidence": complete_open_tip_cap_evidence,
        "conflicting_open_and_closed_evidence": conflict,
        "decisive_closed_evidence_complete": closed_complete,
        "authenticated_occt_closed_topology": topology_payload is not None,
        "source_body_closed_from_typed_topology": bool(
            topology_payload is not None and source_body_is_closed
        ),
    }
    base = {
        "algorithm": "topology_adjacency_finite_thickness_evidence_v1_1_6",
        "source_body_is_closed": source_body_is_closed,
        "tip_cap_evidence": tip_cap_evidence,
        "evidence_checks": checks,
        "candidate_face_metadata": [dict(record) for record in candidate_records],
        "closed_topology_evidence": deepcopy(topology_payload),
        "ignored_candidate_metrics": sorted(
            {
                key
                for record in candidate_records
                for key in ("area_mm2", "outer_radius_mm", "centroid_radius_mm")
                if key in record
            }
        ),
    }
    if closed_complete and not conflict:
        support = _closed_shroud_record(
            inner_ids,
            outer_ids,
            pairs,
            thickness,
            associated_sample_pairs,
            authenticated_thickness_records,
            association_method,
            inner_coverage,
            outer_coverage,
            attachments,
            expected_instance_ids,
            expected_instance_count,
            inner_profile,
            outer_profile,
            topology_payload,
        )
        return {
            **base,
            "status": "PASS",
            "decision": "closed",
            "failure_reason": None,
            "material_shroud": support,
            "tip_reference_or_shroud": support,
        }
    if complete_open_tip_cap_evidence and not partial_closed_evidence:
        return {
            **base,
            "status": "PASS",
            "decision": "open",
            "failure_reason": None,
            "material_shroud": None,
            "tip_reference_or_shroud": None,
        }
    return {
        **base,
        "status": "FAIL",
        "decision": "ambiguous",
        "failure_reason": "v116_shroud_topology_ambiguous",
        "material_shroud": None,
        "tip_reference_or_shroud": None,
    }


def serialize_support_fit_for_v112_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project a rich Task 4 record onto the strict Task 8 support-fit schema."""

    if not isinstance(record, _AuthenticatedSupportResult):
        raise ValueError("support record must carry a module-authenticated result capability")
    payload = record._verified_payload(
        {"v112_support_fit", "open_tip_reference", "closed_shroud"}
    )
    capability = payload["authenticated_result_projection"]["capability"]
    if capability == "open_tip_reference":
        fit = payload.get("profile_fit")
        digests = payload.get("evidence_digests")
        if (
            not isinstance(fit, Mapping)
            or not isinstance(digests, Mapping)
            or digests.get("profile_fit_digest") != _canonical_payload_digest(fit)
            or not _valid_sha256(digests.get("population_contract_digest"))
            or fit.get("provenance", {}).get("source_solid_shape_identity")
            != digests.get("source_solid_shape_identity")
        ):
            raise ValueError("open-tip capability has inconsistent source/topology evidence digests")
    elif capability == "closed_shroud":
        fit = payload.get("inner_flowpath", {}).get("profile_fit")
        outer_fit = payload.get("outer_material", {}).get("profile_fit")
        digests = payload.get("evidence_digests")
        if (
            not isinstance(fit, Mapping)
            or not isinstance(outer_fit, Mapping)
            or not isinstance(digests, Mapping)
            or digests.get("inner_profile_fit_digest") != _canonical_payload_digest(fit)
            or digests.get("outer_profile_fit_digest") != _canonical_payload_digest(outer_fit)
            or not _valid_sha256(digests.get("topology_digest"))
            or _PARTITION_DIGEST_BY_SOURCE_SOLID.get(
                digests.get("source_solid_shape_identity")
            )
            != digests.get("semantic_partition_digest")
            or fit.get("provenance", {}).get("source_solid_shape_identity")
            != digests.get("source_solid_shape_identity")
            or outer_fit.get("provenance", {}).get("source_solid_shape_identity")
            != digests.get("source_solid_shape_identity")
        ):
            raise ValueError("closed-shroud capability has inconsistent source/partition/topology digests")
    else:
        fit = payload
        provenance = fit.get("provenance", {})
        if (
            _PARTITION_DIGEST_BY_SOURCE_SOLID.get(
                provenance.get("source_solid_shape_identity")
            )
            != provenance.get("semantic_partition_digest")
        ):
            raise ValueError("support capability has an unknown source-solid partition digest")
    if not isinstance(fit, Mapping):
        raise ValueError("support record does not contain a profile fit")
    acceptance = fit.get("acceptance")
    provenance = fit.get("provenance")
    residuals = fit.get("residuals")
    if not isinstance(acceptance, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("support fit lacks acceptance or provenance")
    if not isinstance(residuals, Mapping):
        raise ValueError("support fit lacks measured residuals")
    if (
        acceptance.get("status") != "PASS"
        or acceptance.get("promoted_pass_eligible") is not True
        or provenance.get("authenticated_occt_trimmed_material_domain") is not True
    ):
        raise SupportRecoveryError(
            "v116_v112_measurement_schema_invalid",
            "only promoted OCCT trimmed B-Rep support fits can enter V1.1.2 mapping",
        )
    source_ids = provenance.get("source_face_ids", fit.get("source_entity_ids"))
    return {
        "control_points_rz_mm": deepcopy(fit["control_points_rz_mm"]),
        "residual_rms_mm": float(residuals["orthogonal_rms_mm"]),
        "source_ids": _identifier_sequence(source_ids, "source_ids", require_unique=True),
        "fit_status": "PASS",
        "measurement_authority": "occt_trimmed_brep_measurement",
    }


def _valid_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def serialize_support_fits_for_v112_mapping(
    *,
    hub: Mapping[str, Any],
    tip_or_shroud: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "hub": serialize_support_fit_for_v112_mapping(hub),
        "tip_or_shroud": serialize_support_fit_for_v112_mapping(tip_or_shroud),
    }


def verify_support_result_manifest_projection(record: Mapping[str, Any]) -> bool:
    """Verify JSON projection integrity; this does not grant serializer capability."""

    if not isinstance(record, Mapping):
        return False
    projection = record.get("authenticated_result_projection")
    if not isinstance(projection, Mapping):
        return False
    basis = {
        key: value for key, value in record.items() if key != "authenticated_result_projection"
    }
    return bool(
        projection.get("capability")
        in {"v112_support_fit", "open_tip_reference", "closed_shroud"}
        and projection.get("digest_basis")
        == "all_fields_except_authenticated_result_projection"
        and projection.get("payload_digest_sha256") == _canonical_payload_digest(basis)
    )


def sample_occt_edge_meridional_path(
    edge: Any,
    *,
    source_edge_id: str,
    source_solid: Any | None = None,
    sample_count: int = 65,
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
) -> dict[str, Any]:
    source_id = _non_empty_string(source_edge_id, "source_edge_id")
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
    except ImportError as exc:
        raise SupportRecoveryError("v116_step_ocp_unavailable", "OCP curve sampling is unavailable") from exc
    count = _sample_count(sample_count)
    tolerance = _positive_finite(source_tolerance_mm, "source_tolerance_mm")
    matrix = _transform_matrix(source_to_canonical_matrix)
    solid_identity = None
    edge_identity = None
    if source_solid is not None:
        solid_identity = _shape_identity(source_solid, "source_solid")
        edge_identity = _assert_source_subshape(source_solid, edge, "EDGE")
    adaptor = BRepAdaptor_Curve(_wrapped(edge))
    first = float(adaptor.FirstParameter())
    last = float(adaptor.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or last <= first:
        raise SupportRecoveryError("v116_tip_reference_inference_failed", "OCCT edge has no finite parameter range")
    points_xyz = [
        _transform_occt_point(adaptor.Value(float(value)), matrix)
        for value in np.linspace(first, last, count)
    ]
    points_rz = [_project_rz(point) for point in points_xyz]
    return _AuthenticatedOcctEvidence("edge_curve", {
        "source_edge_id": source_id,
        "source_solid_shape_identity": solid_identity,
        "source_edge_shape_identity": edge_identity,
        "source_edge_is_source_solid_subshape": edge_identity is not None,
        "sampling_authority": "occt_brep_curve",
        "projection_fidelity": "sampled_projection_not_exact_brep",
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "units": "mm",
        "source_to_canonical_transform": matrix.tolist(),
        "source_tolerance_mm": _round(tolerance),
        "parameter_sampling": "uniform_occt_parameter_with_meridional_arc_length_fit_weights",
        "points_xyz_mm": points_xyz,
        "points_rz_mm": points_rz,
        "sample_count": count,
        "meridional_arc_length_mm": _round(_polyline_length(np.asarray(points_rz))),
    })


def sample_occt_face_meridional_paths(
    face: Any,
    *,
    source_face_id: str,
    source_solid: Any | None = None,
    semantic_classification: Mapping[str, Any] | None = None,
    semantic_classification_evidence: Mapping[str, Any] | None = None,
    semantic_partition_evidence: Mapping[str, Any] | None = None,
    trace_count: int = 9,
    samples_per_trace: int = 65,
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
) -> dict[str, Any]:
    source_id = _non_empty_string(source_face_id, "source_face_id")
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepClass import BRepClass_FaceClassifier
        from OCP.BRepTools import BRepTools
        from OCP.gp import gp_Pnt2d
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
    except ImportError as exc:
        raise SupportRecoveryError("v116_step_ocp_unavailable", "OCP surface sampling is unavailable") from exc
    trace_total = _sample_count(trace_count, minimum=2)
    point_total = _sample_count(samples_per_trace)
    tolerance = _positive_finite(source_tolerance_mm, "source_tolerance_mm")
    matrix = _transform_matrix(source_to_canonical_matrix)
    solid_identity = None
    face_identity = None
    classification_authenticated = False
    classification = _normalize_face_semantic_classification(semantic_classification)
    if source_solid is not None:
        solid_identity = _shape_identity(source_solid, "source_solid")
        face_identity = _assert_source_subshape(source_solid, face, "FACE")
    partition_digest = None
    if semantic_classification_evidence is not None:
        raise ValueError(
            "per-face semantic evidence is forbidden; provide semantic_partition_evidence"
        )
    if semantic_partition_evidence is not None:
        if semantic_classification is not None:
            raise ValueError("semantic_partition_evidence cannot be combined with a plain classification")
        partition = _authenticated_semantic_partition(semantic_partition_evidence)
        assignment = partition["assignments_by_source_id"].get(source_id)
        if (
            solid_identity is None
            or partition["source_solid_shape_identity"] != solid_identity
            or not isinstance(assignment, Mapping)
            or assignment["source_face_shape_identity"] != face_identity
        ):
            raise SupportRecoveryError(
                "v116_support_source_identity_invalid",
                "Task 3 partition assignment does not match the sampled source-solid face",
            )
        classification = assignment["semantic_classification"]
        classification_authenticated = True
        partition_digest = partition["partition_digest"]
    wrapped_face = _wrapped(face)
    u_first, u_last, v_first, v_last = [float(value) for value in BRepTools.UVBounds_s(wrapped_face)]
    if not all(math.isfinite(value) for value in (u_first, u_last, v_first, v_last)):
        raise SupportRecoveryError("v116_hub_support_classification_failed", "OCCT face has non-finite UV bounds")
    if u_last <= u_first or v_last <= v_first:
        raise SupportRecoveryError("v116_hub_support_classification_failed", "OCCT face has a degenerate UV domain")
    adaptor = BRepAdaptor_Surface(wrapped_face)
    orientation = -1.0 if wrapped_face.Orientation() == TopAbs_REVERSED else 1.0

    families = []
    for varying_axis in ("u", "v"):
        paths = []
        normals = []
        paths_xyz = []
        uv_paths = []
        state_paths = []
        discarded_outside = 0
        discarded_short = 0
        fixed_first, fixed_last = (
            (v_first, v_last) if varying_axis == "u" else (u_first, u_last)
        )
        fixed_step = (fixed_last - fixed_first) / trace_total
        fixed_values = fixed_first + fixed_step * (
            np.arange(trace_total, dtype=float) + 0.5
        )
        varying_values = (
            np.linspace(u_first, u_last, point_total)
            if varying_axis == "u"
            else np.linspace(v_first, v_last, point_total)
        )
        for fixed in fixed_values:
            path = []
            trace_normals = []
            trace_xyz = []
            trace_uv = []
            trace_states = []

            def flush_trace() -> None:
                nonlocal path, trace_normals, trace_xyz, trace_uv, trace_states, discarded_short
                if len(path) >= 2:
                    paths.append(path)
                    normals.append(trace_normals)
                    paths_xyz.append(trace_xyz)
                    uv_paths.append(trace_uv)
                    state_paths.append(trace_states)
                else:
                    discarded_short += len(path)
                path = []
                trace_normals = []
                trace_xyz = []
                trace_uv = []
                trace_states = []

            for varying in varying_values:
                u_value, v_value = (
                    (float(varying), float(fixed))
                    if varying_axis == "u"
                    else (float(fixed), float(varying))
                )
                classifier = BRepClass_FaceClassifier(
                    wrapped_face,
                    gp_Pnt2d(u_value, v_value),
                    tolerance,
                )
                state = classifier.State()
                if state not in (TopAbs_IN, TopAbs_ON):
                    discarded_outside += 1
                    flush_trace()
                    continue
                point, normal = _surface_point_and_normal(
                    adaptor,
                    u_value,
                    v_value,
                    (u_first, u_last, v_first, v_last),
                    matrix,
                    orientation,
                )
                path.append(_project_rz(point))
                trace_normals.append(normal)
                trace_xyz.append(point)
                trace_uv.append([u_value, v_value])
                trace_states.append("IN" if state == TopAbs_IN else "ON")
            flush_trace()
        lengths = [_polyline_length(np.asarray(path)) for path in paths]
        measurable_lengths = [value for value in lengths if value > _EPSILON]
        score = float(np.median(measurable_lengths)) if measurable_lengths else 0.0
        families.append(
            (
                score,
                varying_axis,
                paths,
                normals,
                paths_xyz,
                uv_paths,
                state_paths,
                lengths,
                discarded_outside,
                discarded_short,
            )
        )
    (
        _,
        varying_axis,
        paths,
        normals,
        paths_xyz,
        uv_paths,
        state_paths,
        lengths,
        discarded_outside,
        discarded_short,
    ) = max(families, key=lambda item: item[0])
    if max(lengths) <= _EPSILON:
        raise SupportRecoveryError(
            "v116_hub_support_classification_failed",
            "OCCT face does not contain a measurable meridional trace",
        )
    all_rz_points = np.asarray([point for path in paths for point in path], dtype=float)
    domain_padding = max(tolerance, 1.0e-9)
    classified_domain = [
        [
            float(np.min(all_rz_points[:, axis]) - domain_padding),
            float(np.max(all_rz_points[:, axis]) + domain_padding),
        ]
        for axis in range(2)
    ]
    return _AuthenticatedOcctEvidence("trimmed_face", {
        "source_face_id": source_id,
        "source_solid_shape_identity": solid_identity,
        "source_face_shape_identity": face_identity,
        "source_face_is_source_solid_subshape": face_identity is not None,
        "semantic_classification": classification,
        "semantic_classification_authenticated": classification_authenticated,
        "semantic_partition_digest": partition_digest,
        "sampling_authority": "occt_trimmed_face_classifier",
        "projection_fidelity": "sampled_projection_not_exact_brep",
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "units": "mm",
        "source_to_canonical_transform": matrix.tolist(),
        "source_tolerance_mm": _round(tolerance),
        "parameter_family": f"{varying_axis}_varies",
        "trim_domain": "classified_material_uv_domain_with_uv_bounds_candidate_grid",
        "material_uv_domain_validation": "BRepClass_FaceClassifier",
        "classified_material_domain_rz_mm": classified_domain,
        "paths_rz_mm": paths,
        "paths_xyz_mm": paths_xyz,
        "uv_paths": uv_paths,
        "normals_xyz": normals,
        "classifier_state_paths": state_paths,
        "accepted_classifier_states": sorted({state for trace in state_paths for state in trace}),
        "discarded_outside_uv_sample_count": discarded_outside,
        "discarded_short_segment_sample_count": discarded_short,
        "trace_arc_lengths_mm": [_round(value) for value in lengths],
        "trace_count": len(paths),
        "candidate_trace_count": trace_total,
        "samples_per_trace": point_total,
    })


def sample_occt_shroud_thickness(
    inner_face: Any,
    outer_face: Any,
    *,
    inner_face_id: str,
    outer_face_id: str,
    source_solid: Any | None = None,
    normalized_uv_stations: Sequence[Sequence[float]],
    source_to_canonical_matrix: Sequence[Sequence[float]] | None = None,
    source_tolerance_mm: float = _DEFAULT_SOURCE_TOLERANCE_MM,
) -> list[Mapping[str, Any]]:
    """Measure paired material faces at explicit normalized OCCT UV stations."""

    inner_id = _non_empty_string(inner_face_id, "inner_face_id")
    outer_id = _non_empty_string(outer_face_id, "outer_face_id")
    if inner_id == outer_id:
        raise ValueError("inner_face_id and outer_face_id must be distinct")
    stations = _strict_sequence(normalized_uv_stations, "normalized_uv_stations")
    if len(stations) < _MINIMUM_THICKNESS_SAMPLES_PER_PAIR:
        raise ValueError("normalized_uv_stations requires at least two independent stations")
    tolerance = _positive_finite(source_tolerance_mm, "source_tolerance_mm")
    matrix = _transform_matrix(source_to_canonical_matrix)
    solid_identity = None
    inner_identity = None
    outer_identity = None
    if source_solid is not None:
        solid_identity = _shape_identity(source_solid, "source_solid")
        inner_identity = _assert_source_subshape(source_solid, inner_face, "FACE")
        outer_identity = _assert_source_subshape(source_solid, outer_face, "FACE")
        if inner_identity == outer_identity:
            raise ValueError("inner and outer shroud faces must be distinct OCCT subshapes")
    records: list[Mapping[str, Any]] = []
    seen_stations: set[tuple[float, float]] = set()
    for index, raw_station in enumerate(stations):
        station = _strict_sequence(raw_station, f"normalized_uv_stations[{index}]")
        if len(station) != 2:
            raise ValueError(f"normalized_uv_stations[{index}] must contain (u,v)")
        u_fraction, v_fraction = [float(value) for value in station]
        if (
            not math.isfinite(u_fraction)
            or not math.isfinite(v_fraction)
            or not 0.0 <= u_fraction <= 1.0
            or not 0.0 <= v_fraction <= 1.0
        ):
            raise ValueError("normalized UV stations must be finite values in [0,1]")
        station_key = (round(u_fraction, 12), round(v_fraction, 12))
        if station_key in seen_stations:
            raise ValueError("normalized_uv_stations must identify independent sample sites")
        seen_stations.add(station_key)
        inner_sample = _sample_occt_face_normalized_uv(
            inner_face,
            u_fraction,
            v_fraction,
            matrix,
            tolerance,
        )
        outer_sample = _sample_occt_face_normalized_uv(
            outer_face,
            u_fraction,
            v_fraction,
            matrix,
            tolerance,
        )
        inner_point = np.asarray(inner_sample["point_xyz_mm"], dtype=float)
        outer_point = np.asarray(outer_sample["point_xyz_mm"], dtype=float)
        thickness = float(np.linalg.norm(outer_point - inner_point))
        if not math.isfinite(thickness) or thickness <= tolerance:
            raise SupportRecoveryError(
                "v116_shroud_topology_ambiguous",
                "paired shroud faces do not provide positive finite thickness",
            )
        payload = {
            "sample_id": f"{inner_id}->{outer_id}@{u_fraction:.12g},{v_fraction:.12g}",
            "inner_face_id": inner_id,
            "outer_face_id": outer_id,
            "source_solid_shape_identity": solid_identity,
            "inner_face_shape_identity": inner_identity,
            "outer_face_shape_identity": outer_identity,
            "faces_are_source_solid_subshapes": bool(inner_identity and outer_identity),
            "normalized_uv_station": [u_fraction, v_fraction],
            "circumferential_station": u_fraction,
            "meridional_station": v_fraction,
            "inner_uv": inner_sample["uv"],
            "outer_uv": outer_sample["uv"],
            "inner_point_xyz_mm": inner_sample["point_xyz_mm"],
            "outer_point_xyz_mm": outer_sample["point_xyz_mm"],
            "inner_normal_xyz": inner_sample["normal_xyz"],
            "outer_normal_xyz": outer_sample["normal_xyz"],
            "inner_classifier_state": inner_sample["classifier_state"],
            "outer_classifier_state": outer_sample["classifier_state"],
            "thickness_mm": thickness,
            "sampling_authority": "occt_paired_trimmed_face_evaluation",
            "coordinate_frame": "canonical_axis_frame_xyz_mm",
            "units": "mm",
            "source_to_canonical_transform": matrix.tolist(),
            "source_tolerance_mm": tolerance,
        }
        records.append(_AuthenticatedOcctEvidence("shroud_thickness", payload))
    return records


def _sample_occt_face_normalized_uv(
    face: Any,
    u_fraction: float,
    v_fraction: float,
    matrix: np.ndarray,
    tolerance: float,
) -> dict[str, Any]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepClass import BRepClass_FaceClassifier
        from OCP.BRepTools import BRepTools
        from OCP.gp import gp_Pnt2d
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
    except ImportError as exc:
        raise SupportRecoveryError("v116_step_ocp_unavailable", "OCP surface sampling is unavailable") from exc
    wrapped_face = _wrapped(face)
    bounds = tuple(float(value) for value in BRepTools.UVBounds_s(wrapped_face))
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise SupportRecoveryError("v116_shroud_topology_ambiguous", "shroud face has invalid UV bounds")
    u_first, u_last, v_first, v_last = bounds
    u_value = u_first + u_fraction * (u_last - u_first)
    v_value = v_first + v_fraction * (v_last - v_first)
    state = BRepClass_FaceClassifier(
        wrapped_face,
        gp_Pnt2d(u_value, v_value),
        tolerance,
    ).State()
    if state not in (TopAbs_IN, TopAbs_ON):
        raise SupportRecoveryError(
            "v116_shroud_topology_ambiguous",
            "shroud thickness station lies outside the trimmed material domain",
        )
    adaptor = BRepAdaptor_Surface(wrapped_face)
    orientation = -1.0 if wrapped_face.Orientation() == TopAbs_REVERSED else 1.0
    point, normal = _surface_point_and_normal(
        adaptor,
        u_value,
        v_value,
        bounds,
        matrix,
        orientation,
    )
    return {
        "uv": [u_value, v_value],
        "point_xyz_mm": point,
        "normal_xyz": normal,
        "classifier_state": "IN" if state == TopAbs_IN else "ON",
    }


def _prepare_profile_evidence(
    sample_paths_rz_mm: Sequence[Sequence[Sequence[float]]],
    *,
    source_entity_ids: Sequence[str],
    endpoints_rz_mm: Sequence[Sequence[float]] | None,
    failure_reason: str,
    source_tolerance_mm: float,
) -> dict[str, Any]:
    raw_paths = _strict_sequence(sample_paths_rz_mm, "sample_paths_rz_mm")
    paths = []
    for index, raw_path in enumerate(raw_paths):
        _strict_sequence(raw_path, f"sample_paths_rz_mm[{index}]")
        path = np.asarray(raw_path, dtype=float)
        if path.ndim != 2 or path.shape[1:] != (2,) or len(path) < 2 or not np.all(np.isfinite(path)):
            raise SupportRecoveryError(
                failure_reason,
                f"support path {index} must contain at least two finite (R,Z) samples",
            )
        if np.any(path[:, 0] < 0.0):
            raise SupportRecoveryError(failure_reason, "meridional radius cannot be negative")
        paths.append(path)
    if not paths:
        raise SupportRecoveryError(failure_reason, "support profile has no source paths")
    path_source_ids = _identifier_sequence(source_entity_ids, "source_entity_ids")
    if len(path_source_ids) == 1 and len(paths) > 1:
        path_source_ids *= len(paths)
    if len(path_source_ids) != len(paths) or any(not value for value in path_source_ids):
        raise ValueError("source_entity_ids must identify every sample path")

    explicit_endpoints = None
    if endpoints_rz_mm is not None:
        raw_endpoints = _strict_sequence(endpoints_rz_mm, "endpoints_rz_mm")
        for index, point in enumerate(raw_endpoints):
            _strict_sequence(point, f"endpoints_rz_mm[{index}]")
        explicit_endpoints = np.asarray(endpoints_rz_mm, dtype=float)
        if explicit_endpoints.shape != (2, 2) or not np.all(np.isfinite(explicit_endpoints)):
            raise ValueError("endpoints_rz_mm must contain two finite (R,Z) points")
    oriented_paths = []
    for path in paths:
        if explicit_endpoints is None:
            reverse = path[-1, 0] < path[0, 0]
        else:
            forward_cost = np.linalg.norm(path[0] - explicit_endpoints[0]) + np.linalg.norm(
                path[-1] - explicit_endpoints[1]
            )
            reverse_cost = np.linalg.norm(path[-1] - explicit_endpoints[0]) + np.linalg.norm(
                path[0] - explicit_endpoints[1]
            )
            reverse = reverse_cost < forward_cost
        oriented_paths.append(path[::-1].copy() if reverse else path.copy())
    for index, path in enumerate(oriented_paths):
        if np.any(np.diff(path[:, 0]) < -source_tolerance_mm):
            raise SupportRecoveryError(
                failure_reason,
                f"support path {index} does not preserve global radial order",
            )
    if explicit_endpoints is None:
        all_points = np.vstack(oriented_paths)
        start_radius = float(np.min(all_points[:, 0]))
        end_radius = float(np.max(all_points[:, 0]))
        start_candidates = all_points[np.abs(all_points[:, 0] - start_radius) <= source_tolerance_mm]
        end_candidates = all_points[np.abs(all_points[:, 0] - end_radius) <= source_tolerance_mm]
        start = np.median(start_candidates, axis=0)
        end = np.median(end_candidates, axis=0)
    else:
        start, end = explicit_endpoints

    duplicate_resample_count = max(
        _DUPLICATE_PATH_SAMPLE_COUNT,
        max(len(path) for path in oriented_paths),
    )
    duplicate_groups, group_by_path = _duplicate_path_groups(
        oriented_paths,
        source_tolerance_mm,
        duplicate_resample_count,
    )
    representative_paths = [oriented_paths[group[0]] for group in duplicate_groups]
    radial_grid, global_parameters = _global_reference_parameterization(
        representative_paths,
        start,
        end,
        source_tolerance_mm,
        failure_reason,
    )

    points = []
    parameters = []
    arc_weights = []
    path_lengths = []
    sample_source_ids = []
    sample_path_indices = []
    sample_local_indices = []
    for path_index, (path, source_id) in enumerate(zip(oriented_paths, path_source_ids, strict=True)):
        segments = np.linalg.norm(np.diff(path, axis=0), axis=1)
        length = float(np.sum(segments))
        if length <= _EPSILON:
            raise SupportRecoveryError(failure_reason, f"support path {path_index} is coincident")
        cumulative = np.interp(path[:, 0], radial_grid[:, 0], global_parameters)
        weights = np.zeros(len(path), dtype=float)
        weights[0] = 0.5 * segments[0]
        weights[-1] = 0.5 * segments[-1]
        if len(path) > 2:
            weights[1:-1] = 0.5 * (segments[:-1] + segments[1:])
        weights /= len(duplicate_groups[group_by_path[path_index]])
        points.extend(path)
        parameters.extend(cumulative)
        arc_weights.extend(weights)
        path_lengths.append(length)
        sample_source_ids.extend([source_id] * len(path))
        sample_path_indices.extend([path_index] * len(path))
        sample_local_indices.extend(range(len(path)))
    return {
        "points": np.asarray(points),
        "parameters": np.asarray(parameters),
        "arc_weights": np.asarray(arc_weights),
        "path_lengths": path_lengths,
        "path_source_ids": path_source_ids,
        "sample_source_ids": sample_source_ids,
        "sample_path_indices": sample_path_indices,
        "sample_local_indices": sample_local_indices,
        "endpoints": (np.asarray(start), np.asarray(end)),
        "path_parameter_ranges": [
            [_round(values[0]), _round(values[-1])]
            for values in (
                np.interp(path[:, 0], radial_grid[:, 0], global_parameters)
                for path in oriented_paths
            )
        ],
        "duplicate_path_normalization": {
            "method": "explicit_resampled_geometric_max_rms_comparison",
            "source_tolerance_mm": _round(source_tolerance_mm),
            "maximum_distance_limit_mm": _round(source_tolerance_mm),
            "rms_distance_limit_mm": _round(source_tolerance_mm),
            "resample_count": duplicate_resample_count,
            "clustering": "deterministic_complete_link_input_order",
            "input_path_count": len(oriented_paths),
            "effective_path_count": len(duplicate_groups),
            "duplicate_path_count": len(oriented_paths) - len(duplicate_groups),
            "groups": [
                {
                    "path_indices": group,
                    "source_entity_ids": [path_source_ids[index] for index in group],
                    "multiplicity": len(group),
                }
                for group in duplicate_groups
            ],
        },
    }


def _authenticated_face_profile_inputs(
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    expected_semantic_roles: set[str] | None = None,
    require_hub_candidate: bool = False,
) -> dict[str, Any] | None:
    raw_records = _strict_sequence(evidence_records, "source_face_evidence")
    if not raw_records:
        return None
    payloads = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, _AuthenticatedOcctEvidence):
            raise ValueError(
                f"source_face_evidence[{index}] must be emitted by "
                "sample_occt_face_meridional_paths"
            )
        payloads.append(record._verified_payload("trimmed_face"))
    frames = {payload["coordinate_frame"] for payload in payloads}
    transforms = {
        json.dumps(payload["source_to_canonical_transform"], separators=(",", ":"))
        for payload in payloads
    }
    authorities = {payload["sampling_authority"] for payload in payloads}
    classifiers = {payload["material_uv_domain_validation"] for payload in payloads}
    solid_identities = {payload.get("source_solid_shape_identity") for payload in payloads}
    partition_digests = {payload.get("semantic_partition_digest") for payload in payloads}
    if (
        frames != {"canonical_axis_frame_xyz_mm"}
        or len(transforms) != 1
        or authorities != {"occt_trimmed_face_classifier"}
        or classifiers != {"BRepClass_FaceClassifier"}
        or None in solid_identities
        or len(solid_identities) != 1
        or not all(payload.get("source_face_is_source_solid_subshape") is True for payload in payloads)
        or not all(payload.get("semantic_classification_authenticated") is True for payload in payloads)
        or None in partition_digests
        or len(partition_digests) != 1
    ):
        raise ValueError("source_face_evidence has inconsistent OCCT frame or classifier provenance")
    paths: list[list[list[float]]] = []
    path_source_ids: list[str] = []
    for payload in payloads:
        source_id = _non_empty_string(payload["source_face_id"], "source_face_id")
        classification = payload.get("semantic_classification")
        if not isinstance(classification, Mapping):
            raise ValueError("source_face_evidence lacks typed semantic classification")
        if expected_semantic_roles is not None and classification.get("semantic_role") not in expected_semantic_roles:
            raise ValueError("source_face_evidence semantic role is not valid for this support")
        if require_hub_candidate and not _classification_is_valid_hub_candidate(classification):
            raise SupportRecoveryError(
                "v116_hub_support_classification_failed",
                "hub support must be non-periodic, flowpath-adjacent and exclude local blade features",
                {"source_face_id": source_id, "classification": dict(classification)},
            )
        accepted_states = set(payload["accepted_classifier_states"])
        if not accepted_states or not accepted_states <= {"IN", "ON"}:
            raise ValueError("source_face_evidence contains non-material UV samples")
        for path in payload["paths_rz_mm"]:
            paths.append(path)
            path_source_ids.append(source_id)
    return {
        "paths_rz_mm": paths,
        "path_source_ids": path_source_ids,
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "source_to_canonical_transform": payloads[0]["source_to_canonical_transform"],
        "source_tolerance_mm": max(float(payload["source_tolerance_mm"]) for payload in payloads),
        "source_solid_shape_identity": next(iter(solid_identities)),
        "material_domain_rz_mm": _union_classified_material_domains(payloads),
        "provenance": {
            "source_face_ids": sorted({payload["source_face_id"] for payload in payloads}),
            "units": "mm",
            "material_uv_domain_validation": "BRepClass_FaceClassifier",
            "trim_domain": "classified_material_uv_domain_with_uv_bounds_candidate_grid",
            "accepted_classifier_states": sorted(
                {state for payload in payloads for state in payload["accepted_classifier_states"]}
            ),
            "discarded_outside_uv_sample_count": sum(
                int(payload["discarded_outside_uv_sample_count"]) for payload in payloads
            ),
            "authenticated_evidence_record_count": len(payloads),
            "source_solid_shape_identity": next(iter(solid_identities)),
            "semantic_partition_digest": next(iter(partition_digests)),
            "source_face_shape_identities": sorted(
                payload["source_face_shape_identity"] for payload in payloads
            ),
            "semantic_classifications": [
                deepcopy(payload["semantic_classification"]) for payload in payloads
            ],
        },
    }


def _authenticated_semantic_partition(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, _AuthenticatedOcctEvidence):
        raise ValueError(
            "semantic_partition_evidence must be emitted by authenticate_occt_semantic_partition"
        )
    payload = evidence._verified_payload("semantic_partition")
    registered_digest = _PARTITION_DIGEST_BY_SOURCE_SOLID.get(
        payload.get("source_solid_shape_identity")
    )
    if (
        payload.get("authority") != "immutable_task3_source_solid_semantic_partition"
        or payload.get("partition_digest")
        != _canonical_payload_digest(
            {key: value for key, value in payload.items() if key != "partition_digest"}
        )
        or registered_digest != payload.get("partition_digest")
    ):
        raise ValueError("semantic partition lacks canonical Task 3 source authority")
    return payload


def _fit_authenticated_support_profile(
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    semantic_role: str,
    expected_source_role: str,
) -> dict[str, Any] | None:
    authenticated = _authenticated_face_profile_inputs(
        evidence_records,
        expected_semantic_roles={expected_source_role},
    )
    if authenticated is None:
        return None
    projected = _radially_order_authenticated_support_paths(
        authenticated,
        failure_reason="v116_shroud_topology_ambiguous",
    )
    points = np.asarray(
        [point for path in projected["paths_rz_mm"] for point in path],
        dtype=float,
    )
    tolerance = authenticated["source_tolerance_mm"]
    material_domain = projected["material_domain_rz_mm"]
    return fit_robust_constrained_cubic_profile(
        projected["paths_rz_mm"],
        source_entity_ids=projected["path_source_ids"],
        material_domain_rz_mm=material_domain,
        rms_limit_mm=max(0.2, 0.002 * float(np.max(points[:, 0]) * 2.0)),
        semantic_role=semantic_role,
        failure_reason="v116_shroud_topology_ambiguous",
        coordinate_frame=authenticated["coordinate_frame"],
        source_to_canonical_matrix=authenticated["source_to_canonical_transform"],
        source_tolerance_mm=tolerance,
        source_sampling_authority="occt_trimmed_face_classifier",
        promoted_pass_eligible=True,
        authenticated_provenance=projected["provenance"],
    )


def _radially_order_authenticated_support_paths(
    authenticated: Mapping[str, Any],
    *,
    failure_reason: str,
    minimum_radius_mm: float | None = None,
) -> dict[str, Any]:
    tolerance = float(authenticated["source_tolerance_mm"])
    minimum = None
    if minimum_radius_mm is not None:
        minimum = float(minimum_radius_mm)
        if not math.isfinite(minimum) or minimum < 0.0:
            raise ValueError("minimum_radius_mm must be finite and nonnegative")
    ordered_paths = []
    source_ids = []
    reversed_path_indices = []
    split_path_indices = []
    excluded_below_minimum_path_count = 0
    discarded_sample_count = 0
    maximum_clipped_radial_fraction = 0.0
    for index, (path, source_id) in enumerate(
        zip(
            authenticated["paths_rz_mm"],
            authenticated["path_source_ids"],
            strict=True,
        )
    ):
        points = np.asarray(path, dtype=float)
        if len(points) < 2:
            continue
        radial_steps = np.diff(points[:, 0])
        signed_steps = [
            (step_index, 1 if value > 0.0 else -1)
            for step_index, value in enumerate(radial_steps)
            if abs(float(value)) > tolerance
        ]
        sign_changes = [
            signed_steps[position][0]
            for position in range(1, len(signed_steps))
            if signed_steps[position][1] != signed_steps[position - 1][1]
        ]
        if len(sign_changes) > 1:
            raise SupportRecoveryError(
                failure_reason,
                "authenticated support trace is not monotone in source order",
                {
                    "path_index": index,
                    "source_entity_id": str(source_id),
                    "minimum_radial_step_mm": float(np.min(radial_steps)),
                    "maximum_radial_step_mm": float(np.max(radial_steps)),
                    "source_order_sign_change_count": len(sign_changes),
                },
            )
        branches = [points]
        if sign_changes:
            pivot = sign_changes[0]
            branches = [points[: pivot + 1], points[pivot:]]
            split_path_indices.append(index)
        for branch in branches:
            if len(branch) < 2:
                continue
            branch_steps = np.diff(branch[:, 0])
            if np.all(branch_steps <= tolerance) and np.any(
                branch_steps < -tolerance
            ):
                branch = branch[::-1].copy()
                reversed_path_indices.append(index)
            if np.any(np.diff(branch[:, 0]) < -tolerance):
                raise SupportRecoveryError(
                    failure_reason,
                    "authenticated support branch is not monotone after source-order split",
                    {"path_index": index, "source_entity_id": str(source_id)},
                )
            observed_minimum = float(np.min(branch[:, 0]))
            observed_maximum = float(np.max(branch[:, 0]))
            if minimum is not None and observed_maximum < minimum - tolerance:
                excluded_below_minimum_path_count += 1
                discarded_sample_count += len(branch)
                continue
            if minimum is not None and observed_minimum < minimum - tolerance:
                radial_span = observed_maximum - observed_minimum
                clipped_fraction = (
                    1.0
                    if radial_span <= tolerance
                    else (minimum - observed_minimum) / radial_span
                )
                maximum_clipped_radial_fraction = max(
                    maximum_clipped_radial_fraction, clipped_fraction
                )
                if (
                    clipped_fraction
                    > _MAX_AUTHENTICATED_SUPPORT_CLIPPED_RADIAL_FRACTION
                ):
                    raise SupportRecoveryError(
                        failure_reason,
                        "requested support radius would truncate authenticated source evidence",
                        {
                            "path_index": index,
                            "source_entity_id": str(source_id),
                            "minimum_radius_mm": minimum,
                            "observed_minimum_radius_mm": observed_minimum,
                            "observed_maximum_radius_mm": observed_maximum,
                            "clipped_radial_fraction": clipped_fraction,
                            "maximum_allowed_clipped_radial_fraction": (
                                _MAX_AUTHENTICATED_SUPPORT_CLIPPED_RADIAL_FRACTION
                            ),
                        },
                    )
                mask = branch[:, 0] >= minimum - tolerance
                discarded_sample_count += int(np.count_nonzero(~mask))
                branch = branch[mask]
            if len(branch) < 2:
                continue
            ordered_paths.append(branch.tolist())
            source_ids.append(str(source_id))
    if not ordered_paths:
        raise SupportRecoveryError(
            failure_reason,
            "authenticated support samples do not span the requested radial material domain",
            {"minimum_radius_mm": minimum_radius_mm},
        )
    material_domain = [
        [float(bound[0]), float(bound[1])]
        for bound in authenticated["material_domain_rz_mm"]
    ]
    retained_minimum_radius = min(
        float(point[0]) for path in ordered_paths for point in path
    )
    if minimum is not None:
        material_domain[0][0] = max(
            float(material_domain[0][0]), retained_minimum_radius
        )
    provenance = {
        **deepcopy(authenticated["provenance"]),
        "projection_method": "source_order_monotone_meridional_trace_validation",
        "projection_preserves_source_adjacency": True,
        "reversed_path_indices": reversed_path_indices,
        "split_at_single_radial_turning_point_path_indices": split_path_indices,
        "minimum_radius_mm": minimum,
        "effective_retained_minimum_radius_mm": retained_minimum_radius,
        "discarded_below_minimum_radius_sample_count": discarded_sample_count,
        "excluded_below_minimum_path_count": excluded_below_minimum_path_count,
        "maximum_clipped_radial_fraction": maximum_clipped_radial_fraction,
        "maximum_allowed_clipped_radial_fraction": (
            _MAX_AUTHENTICATED_SUPPORT_CLIPPED_RADIAL_FRACTION
        ),
    }
    return {
        "paths_rz_mm": ordered_paths,
        "path_source_ids": source_ids,
        "material_domain_rz_mm": material_domain,
        "provenance": provenance,
    }


def _authenticated_edge_profile_inputs(
    evidence_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    raw_records = _strict_sequence(evidence_records, "source_edge_evidence")
    if not raw_records:
        return None
    payloads = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, _AuthenticatedOcctEvidence):
            raise ValueError(
                f"source_edge_evidence[{index}] must be emitted by "
                "sample_occt_edge_meridional_path"
            )
        payloads.append(record._verified_payload("edge_curve"))
    solid_identities = {payload.get("source_solid_shape_identity") for payload in payloads}
    transforms = {
        json.dumps(payload["source_to_canonical_transform"], separators=(",", ":"))
        for payload in payloads
    }
    if (
        None in solid_identities
        or len(solid_identities) != 1
        or len(transforms) != 1
        or not all(payload.get("source_edge_is_source_solid_subshape") is True for payload in payloads)
        or any(payload.get("sampling_authority") != "occt_brep_curve" for payload in payloads)
    ):
        raise ValueError("source_edge_evidence is not bound to one OCCT source-solid inventory")
    source_edge_ids = [
        _non_empty_string(payload["source_edge_id"], "source_edge_id") for payload in payloads
    ]
    if len(set(source_edge_ids)) != len(source_edge_ids):
        raise ValueError("source_edge_evidence requires unique source edge ids")
    return {
        "paths_rz_mm": [payload["points_rz_mm"] for payload in payloads],
        "source_edge_ids": source_edge_ids,
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "source_to_canonical_transform": payloads[0]["source_to_canonical_transform"],
        "source_tolerance_mm": max(float(payload["source_tolerance_mm"]) for payload in payloads),
        "source_solid_shape_identity": next(iter(solid_identities)),
        "provenance": {
            "source_edge_ids": sorted(source_edge_ids),
            "source_edge_shape_identities": sorted(
                payload["source_edge_shape_identity"] for payload in payloads
            ),
            "source_solid_shape_identity": next(iter(solid_identities)),
            "units": "mm",
            "measurement_authority": "occt_brep_curve",
        },
    }


def _authenticated_open_tip_population(
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    if not isinstance(evidence, _AuthenticatedOcctEvidence):
        raise ValueError(
            "periodic_population_evidence must be emitted by "
            "authenticate_open_tip_population_contract"
        )
    payload = evidence._verified_payload("open_tip_population")
    if (
        payload.get("authority") != "occt_source_solid_periodic_tip_population"
        or payload.get("population_digest")
        != _canonical_payload_digest(
            {key: value for key, value in payload.items() if key != "population_digest"}
        )
    ):
        raise ValueError("periodic_population_evidence lacks OCCT source authority")
    return payload


def _authenticated_closed_shroud_topology(
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    if not isinstance(evidence, _AuthenticatedOcctEvidence):
        raise ValueError(
            "topology_evidence must be emitted by authenticate_closed_shroud_topology"
        )
    payload = evidence._verified_payload("closed_shroud_topology")
    if (
        payload.get("authority") != "occt_source_solid_closed_shroud_topology"
        or payload.get("topology_digest")
        != _canonical_payload_digest(
            {key: value for key, value in payload.items() if key != "topology_digest"}
        )
        or _PARTITION_DIGEST_BY_SOURCE_SOLID.get(
            payload.get("source_solid_shape_identity")
        )
        != payload.get("semantic_partition_digest")
    ):
        raise ValueError("topology_evidence lacks OCCT source authority")
    return payload


def _authenticated_thickness_inputs(
    evidence_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    raw_records = _strict_sequence(evidence_records, "thickness_sample_evidence")
    payloads: list[dict[str, Any]] = []
    sample_ids: set[str] = set()
    for index, record in enumerate(raw_records):
        if not isinstance(record, _AuthenticatedOcctEvidence):
            raise ValueError(
                f"thickness_sample_evidence[{index}] must be emitted by "
                "sample_occt_shroud_thickness"
            )
        payload = record._verified_payload("shroud_thickness")
        sample_id = _non_empty_string(payload.get("sample_id"), "sample_id")
        if sample_id in sample_ids:
            raise ValueError("thickness_sample_evidence contains duplicate sample ids")
        sample_ids.add(sample_id)
        inner_id = _non_empty_string(payload.get("inner_face_id"), "inner_face_id")
        outer_id = _non_empty_string(payload.get("outer_face_id"), "outer_face_id")
        if inner_id == outer_id:
            raise ValueError("thickness evidence requires distinct inner and outer faces")
        station = np.asarray(payload.get("normalized_uv_station"), dtype=float)
        inner_point = np.asarray(payload.get("inner_point_xyz_mm"), dtype=float)
        outer_point = np.asarray(payload.get("outer_point_xyz_mm"), dtype=float)
        thickness = float(payload.get("thickness_mm", math.nan))
        tolerance = float(payload.get("source_tolerance_mm", math.nan))
        if (
            station.shape != (2,)
            or not np.all(np.isfinite(station))
            or np.any(station < 0.0)
            or np.any(station > 1.0)
            or inner_point.shape != (3,)
            or outer_point.shape != (3,)
            or not np.all(np.isfinite(inner_point))
            or not np.all(np.isfinite(outer_point))
            or not math.isfinite(thickness)
            or thickness <= 0.0
            or not math.isfinite(tolerance)
            or tolerance <= 0.0
            or payload.get("inner_classifier_state") not in {"IN", "ON"}
            or payload.get("outer_classifier_state") not in {"IN", "ON"}
            or payload.get("sampling_authority") != "occt_paired_trimmed_face_evaluation"
            or payload.get("coordinate_frame") != "canonical_axis_frame_xyz_mm"
            or payload.get("units") != "mm"
        ):
            raise ValueError("thickness_sample_evidence contains malformed or non-finite evidence")
        measured = float(np.linalg.norm(outer_point - inner_point))
        if abs(measured - thickness) > max(tolerance, measured * 1.0e-9):
            raise ValueError("thickness_sample_evidence distance does not match its witness points")
        payloads.append(payload)
    return payloads


def _independent_thickness_coverage(
    records: Sequence[Mapping[str, Any]],
    declared_pair_keys: set[tuple[str, str]],
) -> bool:
    if not records or not declared_pair_keys:
        return False
    for pair in declared_pair_keys:
        pair_records = [
            record
            for record in records
            if (record["inner_face_id"], record["outer_face_id"]) == pair
        ]
        if len(pair_records) < _MINIMUM_THICKNESS_SAMPLES_PER_PAIR:
            return False
        sites = {
            tuple(round(float(value), 12) for value in record["normalized_uv_station"])
            for record in pair_records
        }
        inner_points = {
            tuple(round(float(value), 9) for value in record["inner_point_xyz_mm"])
            for record in pair_records
        }
        outer_points = {
            tuple(round(float(value), 9) for value in record["outer_point_xyz_mm"])
            for record in pair_records
        }
        if (
            len(sites) < _MINIMUM_THICKNESS_SAMPLES_PER_PAIR
            or len(inner_points) < _MINIMUM_THICKNESS_SAMPLES_PER_PAIR
            or len(outer_points) < _MINIMUM_THICKNESS_SAMPLES_PER_PAIR
        ):
            return False
    return True


def _duplicate_path_groups(
    paths: Sequence[np.ndarray],
    source_tolerance_mm: float,
    resample_count: int,
) -> tuple[list[list[int]], dict[int, int]]:
    resampled = [
        _resample_polyline(path, resample_count)
        for path in paths
    ]

    def equivalent(first_index: int, second_index: int) -> bool:
        distances = np.linalg.norm(resampled[first_index] - resampled[second_index], axis=1)
        maximum = float(np.max(distances))
        rms = math.sqrt(float(np.mean(distances**2)))
        return maximum <= source_tolerance_mm and rms <= source_tolerance_mm

    groups: list[list[int]] = []
    for path_index in range(len(paths)):
        matching_group = next(
            (
                group
                for group in groups
                if all(equivalent(path_index, member_index) for member_index in group)
            ),
            None,
        )
        if matching_group is None:
            groups.append([path_index])
        else:
            matching_group.append(path_index)
    group_by_path = {
        path_index: group_index
        for group_index, group in enumerate(groups)
        for path_index in group
    }
    return groups, group_by_path


def _global_reference_parameterization(
    representative_paths: Sequence[np.ndarray],
    start: np.ndarray,
    end: np.ndarray,
    source_tolerance_mm: float,
    failure_reason: str,
) -> tuple[np.ndarray, np.ndarray]:
    if end[0] <= start[0] + source_tolerance_mm:
        raise SupportRecoveryError(
            failure_reason,
            "global support parameterization requires increasing radial endpoints",
        )
    collapsed_paths = [_radially_unique_path(path, source_tolerance_mm) for path in representative_paths]
    sample_count = max(257, max(len(path) for path in collapsed_paths))
    radial_values = np.linspace(float(start[0]), float(end[0]), sample_count)
    axial_values = []
    for radius in radial_values:
        candidates = [
            float(np.interp(radius, path[:, 0], path[:, 1]))
            for path in collapsed_paths
            if path[0, 0] - source_tolerance_mm <= radius <= path[-1, 0] + source_tolerance_mm
        ]
        if not candidates:
            raise SupportRecoveryError(
                failure_reason,
                "support paths do not form one globally ordered endpoint-to-endpoint domain",
            )
        axial_values.append(float(np.median(candidates)))
    axial_values[0] = float(start[1])
    axial_values[-1] = float(end[1])
    reference = np.column_stack((radial_values, np.asarray(axial_values)))
    segment_lengths = np.linalg.norm(np.diff(reference, axis=0), axis=1)
    total_length = float(np.sum(segment_lengths))
    if total_length <= _EPSILON:
        raise SupportRecoveryError(failure_reason, "global support reference path is coincident")
    parameters = np.concatenate(([0.0], np.cumsum(segment_lengths))) / total_length
    return reference, parameters


def _radially_unique_path(path: np.ndarray, tolerance: float) -> np.ndarray:
    radii = []
    axial = []
    start = 0
    while start < len(path):
        stop = start + 1
        while stop < len(path) and abs(path[stop, 0] - path[start, 0]) <= tolerance:
            stop += 1
        radii.append(float(np.mean(path[start:stop, 0])))
        axial.append(float(np.mean(path[start:stop, 1])))
        start = stop
    result = np.column_stack((radii, axial))
    if len(result) < 2 or np.any(np.diff(result[:, 0]) <= 0.0):
        raise ValueError("support path must span at least two distinct radial positions")
    return result


def _resample_polyline(path: np.ndarray, count: int) -> np.ndarray:
    segments = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(segments)))
    if cumulative[-1] <= _EPSILON:
        return np.repeat(path[:1], count, axis=0)
    targets = np.linspace(0.0, float(cumulative[-1]), count)
    return np.column_stack(
        [np.interp(targets, cumulative, path[:, axis]) for axis in range(path.shape[1])]
    )


def _material_domain(
    raw_domain: Sequence[Sequence[float]] | None,
    failure_reason: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    if raw_domain is None:
        raise SupportRecoveryError(
            failure_reason,
            "promoted support recovery requires an explicit material domain",
        )
    domain_values = _strict_sequence(raw_domain, "material_domain_rz_mm")
    for index, bounds in enumerate(domain_values):
        _strict_sequence(bounds, f"material_domain_rz_mm[{index}]")
    domain = np.asarray(raw_domain, dtype=float)
    if domain.shape != (2, 2) or not np.all(np.isfinite(domain)) or np.any(domain[:, 1] <= domain[:, 0]):
        raise SupportRecoveryError(
            failure_reason,
            "material_domain_rz_mm must contain increasing finite R and Z bounds",
        )
    return ((float(domain[0, 0]), float(domain[0, 1])), (float(domain[1, 0]), float(domain[1, 1])))


def _validate_endpoint_constraints(
    start: np.ndarray,
    end: np.ndarray,
    material_domain: tuple[tuple[float, float], tuple[float, float]],
    failure_reason: str,
) -> None:
    if end[0] <= start[0]:
        raise SupportRecoveryError(failure_reason, "V1.1.2 support profile endpoints must increase in radius")
    for axis, point_name in enumerate(("radius", "axial")):
        lower, upper = material_domain[axis]
        if not lower <= start[axis] <= upper or not lower <= end[axis] <= upper:
            raise SupportRecoveryError(failure_reason, f"profile endpoint violates the {point_name} material domain")


def _solve_constrained_controls(
    basis: np.ndarray,
    points: np.ndarray,
    weights: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    material_domain: tuple[tuple[float, float], tuple[float, float]],
    failure_reason: str,
) -> np.ndarray:
    controls = np.zeros((V112_PROFILE_CONTROL_COUNT, 2), dtype=float)
    controls[0] = start
    controls[-1] = end
    normalized_weights = weights / float(np.sum(weights))
    second_difference = np.zeros((V112_PROFILE_CONTROL_COUNT - 2, V112_PROFILE_CONTROL_COUNT))
    for index in range(V112_PROFILE_CONTROL_COUNT - 2):
        second_difference[index, index : index + 3] = (1.0, -2.0, 1.0)
    difference = np.zeros((V112_PROFILE_CONTROL_COUNT - 1, V112_PROFILE_CONTROL_COUNT))
    for index in range(V112_PROFILE_CONTROL_COUNT - 1):
        difference[index, index : index + 2] = (-1.0, 1.0)

    for axis in range(2):
        fixed = np.zeros(V112_PROFILE_CONTROL_COUNT)
        fixed[0], fixed[-1] = start[axis], end[axis]
        design = basis[:, 1:-1]
        offset = basis @ fixed
        smooth_design = second_difference[:, 1:-1]
        smooth_offset = second_difference @ fixed
        direction = 1.0 if axis == 0 else 0.0
        constraint_matrix = direction * difference[:, 1:-1]
        constraint_offset = direction * (difference @ fixed)

        def objective(interior: np.ndarray) -> float:
            residual = design @ interior + offset - points[:, axis]
            smooth = smooth_design @ interior + smooth_offset
            return float(np.dot(normalized_weights, residual**2) + 1.0e-6 * np.mean(smooth**2))

        def gradient(interior: np.ndarray) -> np.ndarray:
            residual = design @ interior + offset - points[:, axis]
            smooth = smooth_design @ interior + smooth_offset
            data_gradient = 2.0 * (design.T @ (normalized_weights * residual))
            smooth_gradient = 2.0e-6 * (smooth_design.T @ smooth) / len(smooth)
            return data_gradient + smooth_gradient

        constraints = []
        if direction:
            constraints.append(
                {
                    "type": "ineq",
                    "fun": lambda interior, matrix=constraint_matrix, offset_value=constraint_offset: (
                        matrix @ interior + offset_value
                    ),
                    "jac": lambda interior, matrix=constraint_matrix: matrix,
                }
            )
        initial = np.linspace(start[axis], end[axis], V112_PROFILE_CONTROL_COUNT)[1:-1]
        result = minimize(
            objective,
            initial,
            jac=gradient,
            bounds=[material_domain[axis]] * (V112_PROFILE_CONTROL_COUNT - 2),
            constraints=constraints,
            method="SLSQP",
            options={"ftol": 1.0e-12, "maxiter": 500, "disp": False},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise SupportRecoveryError(
                failure_reason,
                f"constrained cubic profile solve failed on axis {axis}: {result.message}",
            )
        controls[1:-1, axis] = result.x
    return controls


def _controls_satisfy_constraints(
    controls: np.ndarray,
    material_domain: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    radial_ok = bool(np.all(np.diff(controls[:, 0]) >= -1.0e-8))
    bounds_ok = all(
        material_domain[axis][0] - 1.0e-8 <= float(np.min(controls[:, axis]))
        and float(np.max(controls[:, axis])) <= material_domain[axis][1] + 1.0e-8
        for axis in range(2)
    )
    return radial_ok and bounds_ok


def _basis_matrix(parameters: np.ndarray, point_count: int, degree: int, knots: Sequence[float]) -> np.ndarray:
    return np.asarray(
        [
            [_basis(index, degree, float(value), knots, point_count) for index in range(point_count)]
            for value in parameters
        ],
        dtype=float,
    )


def _basis(index: int, degree: int, value: float, knots: Sequence[float], point_count: int) -> float:
    if degree == 0:
        if knots[index] <= value < knots[index + 1]:
            return 1.0
        return 1.0 if value == 1.0 and index == point_count - 1 else 0.0
    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left = 0.0
    right = 0.0
    if left_denominator > _EPSILON:
        left = (value - knots[index]) / left_denominator * _basis(index, degree - 1, value, knots, point_count)
    if right_denominator > _EPSILON:
        right = (knots[index + degree + 1] - value) / right_denominator * _basis(
            index + 1,
            degree - 1,
            value,
            knots,
            point_count,
        )
    return left + right


def _nearest_curve_distances(points: np.ndarray, curve_samples: np.ndarray) -> np.ndarray:
    distances = np.empty(len(points), dtype=float)
    for start in range(0, len(points), 256):
        chunk = points[start : start + 256]
        squared = np.sum((chunk[:, None, :] - curve_samples[None, :, :]) ** 2, axis=2)
        distances[start : start + len(chunk)] = np.sqrt(np.min(squared, axis=1))
    return distances


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, fraction: float) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    ordered_weights = weights[order]
    cumulative = np.cumsum(ordered_weights)
    target = min(max(float(fraction), 0.0), 1.0) * float(cumulative[-1])
    index = min(int(np.searchsorted(cumulative, target, side="left")), len(ordered_values) - 1)
    return float(ordered_values[index])


def adapt_tip_cap_topology_evidence(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw_records = _strict_sequence(records, "records")
    normalized = []
    for record_index, record in enumerate(raw_records):
        if not isinstance(record, Mapping):
            _raise_tip_topology_error(record_index, "tip-cap record must be a mapping")
        try:
            instance_id = _non_empty_string(
                record.get("periodic_instance_id"),
                "periodic_instance_id",
            )
            tip_cap_face_id = _non_empty_string(
                record.get("tip_cap_face_id"),
                "tip_cap_face_id",
            )
        except ValueError as exc:
            _raise_tip_topology_error(record_index, str(exc))
        raw_loops = record.get("shared_edge_loops", ())
        try:
            raw_loops = _strict_sequence(raw_loops, "shared_edge_loops")
        except ValueError as exc:
            _raise_tip_topology_error(record_index, str(exc))
        if len(raw_loops) == 0:
            _raise_tip_topology_error(record_index, "tip-cap face requires a shared edge loop")
        loops = []
        for loop_index, raw_loop in enumerate(raw_loops):
            if not isinstance(raw_loop, Mapping):
                _raise_tip_topology_error(record_index, "shared edge loop must be a mapping", loop_index)
            try:
                loop_id = _non_empty_string(raw_loop.get("loop_id"), "loop_id")
                source_edge_ids = _identifier_sequence(
                    raw_loop.get("source_edge_ids", ()),
                    "source_edge_ids",
                    require_unique=True,
                )
            except ValueError as exc:
                _raise_tip_topology_error(record_index, str(exc), loop_index)
            raw_faces = raw_loop.get("adjacent_periodic_faces", ())
            if not source_edge_ids:
                _raise_tip_topology_error(
                    record_index,
                    "shared edge loop requires a distinct loop id and source edge ids",
                    loop_index,
                )
            if loop_id in source_edge_ids:
                _raise_tip_topology_error(
                    record_index,
                    "edge ids and loop ids are distinct topology identifiers",
                    loop_index,
                )
            try:
                raw_faces = _strict_sequence(raw_faces, "adjacent_periodic_faces")
            except ValueError as exc:
                _raise_tip_topology_error(record_index, str(exc), loop_index)
            if len(raw_faces) == 0:
                _raise_tip_topology_error(
                    record_index,
                    "shared edge loop requires an adjacent periodic side or edge face",
                    loop_index,
                )
            adjacent_faces = []
            for raw_face in raw_faces:
                if not isinstance(raw_face, Mapping):
                    _raise_tip_topology_error(record_index, "adjacent face must be a mapping", loop_index)
                try:
                    face_id = _non_empty_string(raw_face.get("face_id"), "face_id")
                    face_role = _non_empty_string(raw_face.get("face_role"), "face_role")
                    face_instance_id = _non_empty_string(
                        raw_face.get("periodic_instance_id"),
                        "periodic_instance_id",
                    )
                except ValueError as exc:
                    _raise_tip_topology_error(record_index, str(exc), loop_index)
                if (
                    face_id == tip_cap_face_id
                    or face_role not in _TIP_ADJACENT_FACE_ROLES
                    or face_instance_id != instance_id
                ):
                    _raise_tip_topology_error(
                        record_index,
                        "adjacent face must be a distinct periodic side/edge face owned by the same instance",
                        loop_index,
                    )
                adjacent_faces.append(
                    {
                        "face_id": face_id,
                        "face_role": face_role,
                        "periodic_instance_id": face_instance_id,
                    }
                )
            adjacent_faces.sort(key=lambda item: (item["face_role"], item["face_id"]))
            loops.append(
                {
                    "loop_id": loop_id,
                    "source_edge_ids": source_edge_ids,
                    "adjacent_periodic_faces": adjacent_faces,
                }
            )
        loops.sort(key=lambda item: item["loop_id"])
        normalized.append(
            {
                "periodic_instance_id": instance_id,
                "tip_cap_face_id": tip_cap_face_id,
                "shared_edge_loops": loops,
            }
        )
    normalized.sort(key=lambda record: (record["periodic_instance_id"], record["tip_cap_face_id"]))
    instance_ids = [record["periodic_instance_id"] for record in normalized]
    tip_cap_face_ids = [record["tip_cap_face_id"] for record in normalized]
    shared_edge_loop_ids = [
        loop["loop_id"] for record in normalized for loop in record["shared_edge_loops"]
    ]
    shared_source_edge_ids = [
        edge_id
        for record in normalized
        for loop in record["shared_edge_loops"]
        for edge_id in loop["source_edge_ids"]
    ]
    adjacent_face_ids = [
        face["face_id"]
        for record in normalized
        for loop in record["shared_edge_loops"]
        for face in loop["adjacent_periodic_faces"]
    ]
    all_owned_face_ids = [*tip_cap_face_ids, *adjacent_face_ids]
    if (
        len(set(instance_ids)) != len(instance_ids)
        or len(set(tip_cap_face_ids)) != len(tip_cap_face_ids)
        or len(set(shared_edge_loop_ids)) != len(shared_edge_loop_ids)
        or len(set(shared_source_edge_ids)) != len(shared_source_edge_ids)
        or len(set(adjacent_face_ids)) != len(adjacent_face_ids)
        or len(set(all_owned_face_ids)) != len(all_owned_face_ids)
        or set(shared_edge_loop_ids) & set(shared_source_edge_ids)
    ):
        raise SupportRecoveryError(
            "v116_tip_cap_topology_invalid",
            "tip-cap instances, adjacent faces, loops and source edges require distinct topology ownership",
        )
    repeated = bool(
        len(instance_ids) >= 2
        and len(tip_cap_face_ids) >= 2
        and len(shared_edge_loop_ids) >= 2
        and len(shared_source_edge_ids) >= 2
    )
    return {
        "method": "cap_face_to_shared_edge_loop_to_periodic_face_instance_ownership",
        "semantic_role": "per_blade_tip_cap",
        "material": bool(normalized),
        "source_caps_material": bool(normalized),
        "records": normalized,
        "invalid_record_indices": [],
        "periodic_instance_ids": sorted(instance_ids),
        "tip_cap_face_ids": sorted(tip_cap_face_ids),
        "shared_edge_loop_ids": sorted(shared_edge_loop_ids),
        "shared_source_edge_ids": sorted(shared_source_edge_ids),
        "adjacent_periodic_face_ids": sorted(adjacent_face_ids),
        "shared_adjacency_loop_count": len(shared_edge_loop_ids),
        "repeated_shared_adjacency": repeated,
        "topological_free_edge_required": False,
        "edge_loop_identifier_conflation": False,
    }


def _tip_cap_evidence(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        return adapt_tip_cap_topology_evidence(records)
    except SupportRecoveryError as exc:
        return {
            "method": "cap_face_to_shared_edge_loop_to_periodic_face_instance_ownership",
            "semantic_role": "per_blade_tip_cap",
            "material": False,
            "source_caps_material": False,
            "records": [],
            "invalid_record_indices": [exc.details.get("record_index", 0)],
            "periodic_instance_ids": [],
            "tip_cap_face_ids": [],
            "shared_edge_loop_ids": [],
            "shared_source_edge_ids": [],
            "adjacent_periodic_face_ids": [],
            "shared_adjacency_loop_count": 0,
            "repeated_shared_adjacency": False,
            "topological_free_edge_required": False,
            "edge_loop_identifier_conflation": "edge ids and loop ids" in str(exc),
            "validation_error": str(exc),
        }


def _raise_tip_topology_error(record_index: int, message: str, loop_index: int | None = None) -> None:
    details = {"record_index": record_index}
    if loop_index is not None:
        details["loop_index"] = loop_index
    raise SupportRecoveryError("v116_tip_cap_topology_invalid", message, details)


def _closed_shroud_record(
    inner_ids: list[str],
    outer_ids: list[str],
    pairs: list[list[str]],
    thickness: np.ndarray,
    thickness_sample_face_pairs: list[list[str]],
    thickness_sample_records: list[dict[str, Any]],
    thickness_association_method: str,
    inner_coverage: float,
    outer_coverage: float,
    attachments: list[str],
    expected_instance_ids: list[str] | None,
    expected_instance_count: int | None,
    inner_profile: dict[str, Any],
    outer_profile: dict[str, Any],
    topology_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(inner_profile, _AuthenticatedSupportResult) or not isinstance(
        outer_profile,
        _AuthenticatedSupportResult,
    ):
        raise ValueError("closed shroud profiles require authenticated support capabilities")
    inner_profile_payload = inner_profile._verified_payload({"v112_support_fit"})
    outer_profile_payload = outer_profile._verified_payload({"v112_support_fit"})
    thickness_by_face_pair = []
    for pair in pairs:
        pair_samples = np.asarray(
            [
                thickness[index]
                for index, sample_pair in enumerate(thickness_sample_face_pairs)
                if sample_pair == pair
            ],
            dtype=float,
        )
        pair_records = [
            record
            for record in thickness_sample_records
            if [record["inner_face_id"], record["outer_face_id"]] == pair
        ]
        thickness_by_face_pair.append(
            {
                "inner_face_id": pair[0],
                "outer_face_id": pair[1],
                "samples_mm": [_round(value) for value in pair_samples],
                "sample_count": len(pair_samples),
                "minimum_mm": _round(float(np.min(pair_samples))),
                "mean_mm": _round(float(np.mean(pair_samples))),
                "maximum_mm": _round(float(np.max(pair_samples))),
                "finite_positive": True,
                "adequate_coverage": True,
                "sample_records": pair_records,
            }
        )
    result = {
        "semantic_role": "closed_shroud",
        "material": True,
        "render_default": "material",
        "export_default": "included",
        "inner_flowpath": {
            "source_face_ids": inner_ids,
            "circumferential_coverage": _round(inner_coverage),
            "profile_fit": inner_profile_payload,
        },
        "outer_material": {
            "source_face_ids": outer_ids,
            "circumferential_coverage": _round(outer_coverage),
            "profile_fit": outer_profile_payload,
        },
        "paired_face_ids": pairs,
        "thickness": {
            "samples_mm": [_round(value) for value in thickness],
            "sample_face_pairs": thickness_sample_face_pairs,
            "sample_records": thickness_sample_records,
            "sample_count": len(thickness),
            "minimum_mm": _round(float(np.min(thickness))),
            "mean_mm": _round(float(np.mean(thickness))),
            "maximum_mm": _round(float(np.max(thickness))),
            "finite_positive": True,
            "association_method": thickness_association_method,
            "sampling_authority": "authenticated_occt_paired_face_evaluation",
            "coordinate_frame": "canonical_axis_frame_xyz_mm",
            "units": "mm",
            "minimum_samples_per_face_pair": _MINIMUM_THICKNESS_SAMPLES_PER_PAIR,
            "covers_all_face_pairs": True,
            "adequate_samples_per_face_pair": True,
            "by_face_pair": thickness_by_face_pair,
        },
        "blade_tip_attachment": {
            "periodic_instance_ids": attachments,
            "instance_count": len(attachments),
            "expected_periodic_instance_ids": expected_instance_ids,
            "expected_instance_count": expected_instance_count,
            "covers_expected_instances": True,
            "repeated": True,
            "adjacency_chains": deepcopy(topology_payload["blade_tip_attachment_chains"]),
            "adjacency_authority": "occt_exact_shared_edge_identity",
        },
        "evidence_digests": {
            "source_solid_shape_identity": topology_payload["source_solid_shape_identity"],
            "semantic_partition_digest": topology_payload["semantic_partition_digest"],
            "topology_digest": topology_payload["topology_digest"],
            "inner_profile_fit_digest": _canonical_payload_digest(inner_profile_payload),
            "outer_profile_fit_digest": _canonical_payload_digest(outer_profile_payload),
        },
    }
    return _AuthenticatedSupportResult("closed_shroud", result)


def _face_pairs(
    values: Sequence[Sequence[str]],
    name: str,
    *,
    allow_duplicates: bool = False,
) -> list[list[str]]:
    raw_pairs = _strict_sequence(values, name)
    pairs = []
    for index, value in enumerate(raw_pairs):
        pair_values = _strict_sequence(value, f"{name}[{index}]")
        if len(pair_values) != 2:
            raise ValueError(f"{name}[{index}] must contain exactly two face ids")
        pair = [
            _non_empty_string(pair_values[0], f"{name}[{index}][0]"),
            _non_empty_string(pair_values[1], f"{name}[{index}][1]"),
        ]
        if not allow_duplicates and pair in pairs:
            raise ValueError(f"{name} must contain unique face pairs")
        pairs.append(pair)
    return pairs


def _expected_instance_contract(
    value: int | Sequence[str] | None,
) -> tuple[list[str] | None, int | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        raise ValueError("expected_blade_instances must be a positive count or instance id sequence")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("expected_blade_instances must be positive")
        return None, value
    if isinstance(value, (str, bytes)):
        raise ValueError("expected_blade_instances must be a positive count or instance id sequence")
    raw_ids = _identifier_sequence(
        value,
        "expected_blade_instances",
        require_unique=True,
    )
    ids = sorted(raw_ids)
    if not ids:
        raise ValueError("expected_blade_instances must contain unique non-empty instance ids")
    return ids, len(ids)


def _coverage_bounded(value: float) -> bool:
    return math.isfinite(value) and 0.0 <= value <= 1.0


def _coverage_complete(value: float, minimum: float) -> bool:
    return _coverage_bounded(value) and value >= minimum


def _coverage_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _strict_sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be a sequence, not a bare string")
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            raise ValueError(f"{name} must be a sequence")
        return value
    if not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence")
    return value


def _strict_shape_mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result: dict[str, Any] = {}
    for key, shape in value.items():
        source_id = _non_empty_string(key, f"{name} key")
        if shape is None:
            raise ValueError(f"{name}[{source_id}] must contain an OCCT shape")
        result[source_id] = shape
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _normalize_instance_loop_contract(value: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("expected_instance_loop_ids must be a non-empty mapping")
    return {
        _non_empty_string(instance_id, "periodic instance id"): sorted(
            _identifier_sequence(loop_ids, "expected loop ids", require_unique=True)
        )
        for instance_id, loop_ids in value.items()
    }


def _normalize_face_semantic_classification(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if value is None:
        return {
            "semantic_role": "unclassified",
            "classification_authority": "none",
            "periodic_blade_related": False,
            "flowpath_adjacent": False,
            "root_blend": False,
            "hole_boundary": False,
            "local_edge_treatment": False,
        }
    if not isinstance(value, Mapping):
        raise ValueError("semantic_classification must be a mapping")
    required = {
        "semantic_role",
        "classification_authority",
        "periodic_blade_related",
        "flowpath_adjacent",
        "root_blend",
        "hole_boundary",
        "local_edge_treatment",
    }
    if set(value) != required:
        raise ValueError(
            "semantic_classification must contain only role, authority and exclusion flags"
        )
    result = {
        "semantic_role": _non_empty_string(value["semantic_role"], "semantic_role"),
        "classification_authority": _non_empty_string(
            value["classification_authority"],
            "classification_authority",
        ),
    }
    for key in sorted(required - {"semantic_role", "classification_authority"}):
        result[key] = _strict_bool(value[key], key)
    return result


def _classification_is_valid_hub_candidate(classification: Mapping[str, Any]) -> bool:
    return bool(
        classification.get("semantic_role") == _HUB_SUPPORT_ROLE
        and classification.get("classification_authority")
        == "task3_source_solid_semantic_partition"
        and classification.get("flowpath_adjacent") is True
        and all(classification.get(flag) is False for flag in _EXCLUDED_HUB_FLAGS)
    )


def _union_classified_material_domains(
    payloads: Sequence[Mapping[str, Any]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    domains = np.asarray(
        [payload["classified_material_domain_rz_mm"] for payload in payloads],
        dtype=float,
    )
    if domains.ndim != 3 or domains.shape[1:] != (2, 2) or not np.all(np.isfinite(domains)):
        raise ValueError("source_face_evidence has invalid classified material domains")
    return (
        (float(np.min(domains[:, 0, 0])), float(np.max(domains[:, 0, 1]))),
        (float(np.min(domains[:, 1, 0])), float(np.max(domains[:, 1, 1]))),
    )


def _shape_identity(shape: Any, name: str) -> str:
    wrapped = _wrapped(shape)
    try:
        raw_hash = shape.hashCode() if hasattr(shape, "hashCode") else hash(wrapped)
    except Exception as exc:
        raise ValueError(f"{name} does not expose stable OCCT shape identity") from exc
    numeric_hash = int(raw_hash) & ((1 << 64) - 1)
    base = f"occt-shape-{numeric_hash:016x}"
    if name != "source_solid":
        return base
    bucket = _SOURCE_SOLID_IDENTITIES_BY_HASH.setdefault(numeric_hash, [])
    for existing, identity in bucket:
        if wrapped.IsSame(existing):
            return identity
    identity = base if not bucket else f"{base}-{len(bucket):02d}"
    bucket.append((wrapped, identity))
    return identity


def _assert_source_subshape(source_shape: Any, candidate: Any, kind: str) -> str:
    candidate_wrapped = _wrapped(candidate)
    for subshape in _iter_source_subshapes(source_shape, kind):
        wrapped = _wrapped(subshape)
        try:
            if wrapped.IsSame(candidate_wrapped):
                return _shape_identity(candidate, f"source {kind.lower()}")
        except Exception:
            if _shape_identity(subshape, "source subshape") == _shape_identity(
                candidate,
                "candidate subshape",
            ):
                return _shape_identity(candidate, f"source {kind.lower()}")
    raise SupportRecoveryError(
        "v116_support_source_identity_invalid",
        f"candidate {kind.lower()} is not a subshape of the authenticated source solid",
    )


def _subshape_is_owned_by(source_shape: Any, candidate: Any, kind: str) -> bool:
    try:
        _assert_source_subshape(source_shape, candidate, kind)
    except SupportRecoveryError:
        return False
    return True


def _edge_has_distinct_end_vertices(edge: Any) -> bool:
    if hasattr(edge, "Vertices"):
        vertices = list(edge.Vertices())
    else:
        try:
            from OCP.TopAbs import TopAbs_VERTEX
            from OCP.TopExp import TopExp_Explorer
        except ImportError:
            return False
        explorer = TopExp_Explorer(_wrapped(edge), TopAbs_VERTEX)
        vertices = []
        while explorer.More():
            vertices.append(explorer.Current())
            explorer.Next()
    identities = {_shape_identity(vertex, "edge vertex") for vertex in vertices}
    return len(identities) >= 2


def _same_occt_shape(first: Any, second: Any) -> bool:
    try:
        return bool(_wrapped(first).IsSame(_wrapped(second)))
    except Exception:
        return _shape_identity(first, "first shape") == _shape_identity(second, "second shape")


def _iter_source_subshapes(source_shape: Any, kind: str) -> list[Any]:
    method_name = "Faces" if kind == "FACE" else "Edges"
    if hasattr(source_shape, method_name):
        return list(getattr(source_shape, method_name)())
    try:
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
    except ImportError as exc:
        raise SupportRecoveryError(
            "v116_step_ocp_unavailable",
            "OCP topology inventory is unavailable",
        ) from exc
    explorer = TopExp_Explorer(_wrapped(source_shape), TopAbs_FACE if kind == "FACE" else TopAbs_EDGE)
    result = []
    while explorer.More():
        result.append(explorer.Current())
        explorer.Next()
    return result


def _source_shape_is_closed(source_shape: Any) -> bool:
    wrapped = _wrapped(source_shape)
    try:
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.TopAbs import TopAbs_SOLID
    except ImportError:
        return False
    solids = list(source_shape.Solids()) if hasattr(source_shape, "Solids") else []
    if solids:
        return len(solids) == 1 and bool(solids[0].isValid())
    try:
        return wrapped.ShapeType() == TopAbs_SOLID and bool(BRepCheck_Analyzer(wrapped).IsValid())
    except Exception:
        return False


def _occt_face_circumferential_coverage(face: Any) -> float:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_Circle
    except ImportError as exc:
        raise SupportRecoveryError(
            "v116_step_ocp_unavailable",
            "OCP surface coverage evaluation is unavailable",
        ) from exc
    wrapped = _wrapped(face)
    adaptor = BRepAdaptor_Surface(wrapped)
    u_first, u_last, v_first, v_last = [float(value) for value in BRepTools.UVBounds_s(wrapped)]
    candidates = []
    if adaptor.IsUPeriodic():
        period = float(adaptor.UPeriod())
        if period > _EPSILON:
            candidates.append((u_last - u_first) / period)
    if adaptor.IsVPeriodic():
        period = float(adaptor.VPeriod())
        if period > _EPSILON:
            candidates.append((v_last - v_first) / period)
    if not candidates:
        for edge in _iter_source_subshapes(face, "EDGE"):
            curve = BRepAdaptor_Curve(_wrapped(edge))
            if curve.GetType() != GeomAbs_Circle:
                continue
            parameter_span = abs(
                float(curve.LastParameter()) - float(curve.FirstParameter())
            )
            if math.isfinite(parameter_span):
                candidates.append(parameter_span / (2.0 * math.pi))
    if not candidates:
        return 0.0
    return min(1.0, max(0.0, max(candidates)))


def _thickness_material_normals_consistent(records: Sequence[Mapping[str, Any]]) -> bool:
    for record in records:
        inner = np.asarray(record["inner_point_xyz_mm"], dtype=float)
        outer = np.asarray(record["outer_point_xyz_mm"], dtype=float)
        direction = outer - inner
        length = float(np.linalg.norm(direction))
        if length <= _EPSILON:
            return False
        direction /= length
        inner_normal = np.asarray(record["inner_normal_xyz"], dtype=float)
        outer_normal = np.asarray(record["outer_normal_xyz"], dtype=float)
        if (
            float(np.dot(inner_normal, direction)) >= -0.25
            or float(np.dot(outer_normal, direction)) <= 0.25
            or float(np.dot(inner_normal, outer_normal)) >= -0.25
        ):
            return False
    return True


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    result = value.strip()
    if not result:
        raise ValueError(f"{name} must be a non-empty string")
    return result


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")
    return value


def _identifier_sequence(
    values: Sequence[Any] | None,
    name: str,
    *,
    require_unique: bool = False,
) -> list[str]:
    if values is None:
        return []
    raw_values = _strict_sequence(values, name)
    identifiers = [
        _non_empty_string(value, f"{name}[{index}]")
        for index, value in enumerate(raw_values)
    ]
    if require_unique and len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{name} must contain unique ids")
    return identifiers


def _unique_strings(values: Sequence[Any] | None, name: str) -> list[str]:
    identifiers = _identifier_sequence(values, name, require_unique=True)
    return sorted(identifiers)


def _mapping_sequence(values: Sequence[Any], name: str) -> list[Mapping[str, Any]]:
    raw_values = _strict_sequence(values, name)
    records = []
    for index, value in enumerate(raw_values):
        if not isinstance(value, Mapping):
            raise ValueError(f"{name}[{index}] must be a mapping")
        records.append(value)
    return records


def _numeric_sequence(values: Sequence[Any], name: str) -> np.ndarray:
    raw_values = _strict_sequence(values, name)
    try:
        result = np.asarray(raw_values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values") from exc
    if result.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional sequence")
    return result


def _sample_count(value: int, *, minimum: int = 3) -> int:
    count = int(value)
    if count < minimum:
        raise ValueError(f"sample count must be at least {minimum}")
    return count


def _transform_matrix(value: Sequence[Sequence[float]] | None) -> np.ndarray:
    if value is None:
        matrix = np.eye(4)
    else:
        raw_matrix = _strict_sequence(value, "source_to_canonical_matrix")
        for index, row in enumerate(raw_matrix):
            _strict_sequence(row, f"source_to_canonical_matrix[{index}]")
        try:
            matrix = np.asarray(raw_matrix, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("source_to_canonical_matrix must be a finite 4x4 matrix") from exc
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError("source_to_canonical_matrix must be a finite 4x4 matrix")
    return matrix


def _wrapped(shape: Any) -> Any:
    return getattr(shape, "wrapped", shape)


def _transform_occt_point(point: Any, matrix: np.ndarray) -> list[float]:
    source = np.asarray([float(point.X()), float(point.Y()), float(point.Z()), 1.0])
    transformed = matrix @ source
    if abs(transformed[3]) <= _EPSILON:
        raise ValueError("source_to_canonical_matrix produced an invalid homogeneous point")
    return [float(value) for value in transformed[:3] / transformed[3]]


def _surface_point_and_normal(
    adaptor: Any,
    u_value: float,
    v_value: float,
    bounds: tuple[float, float, float, float],
    matrix: np.ndarray,
    orientation: float,
) -> tuple[list[float], list[float]]:
    u_first, u_last, v_first, v_last = bounds
    u_step = max((u_last - u_first) * 1.0e-6, 1.0e-9)
    v_step = max((v_last - v_first) * 1.0e-6, 1.0e-9)
    u_low, u_high = max(u_first, u_value - u_step), min(u_last, u_value + u_step)
    v_low, v_high = max(v_first, v_value - v_step), min(v_last, v_value + v_step)
    point = _transform_occt_point(adaptor.Value(u_value, v_value), matrix)
    u_before = np.asarray(_transform_occt_point(adaptor.Value(u_low, v_value), matrix))
    u_after = np.asarray(_transform_occt_point(adaptor.Value(u_high, v_value), matrix))
    v_before = np.asarray(_transform_occt_point(adaptor.Value(u_value, v_low), matrix))
    v_after = np.asarray(_transform_occt_point(adaptor.Value(u_value, v_high), matrix))
    normal = np.cross(u_after - u_before, v_after - v_before) * orientation
    norm = float(np.linalg.norm(normal))
    if norm > _EPSILON:
        normal /= norm
    else:
        normal[:] = 0.0
    return point, [float(value) for value in normal]


def _project_rz(point_xyz: Sequence[float]) -> list[float]:
    return [float(math.hypot(point_xyz[0], point_xyz[1])), float(point_xyz[2])]


def _polyline_length(points: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


def _polylines_intersect(first: np.ndarray, second: np.ndarray, tolerance: float) -> bool:
    for first_index in range(len(first) - 1):
        for second_index in range(len(second) - 1):
            if _segments_intersect(
                first[first_index],
                first[first_index + 1],
                second[second_index],
                second[second_index + 1],
                tolerance,
            ):
                return True
    return False


def _span_segments_cross_bounded(
    hub_points: np.ndarray,
    tip_points: np.ndarray,
    tolerance: float,
) -> bool:
    if len(hub_points) != len(tip_points) or len(hub_points) > _DENSE_CONNECTOR_SAMPLE_COUNT:
        raise ValueError("dense connector intersection input exceeds its fixed bound")
    for first_index in range(len(hub_points)):
        for second_index in range(first_index + 1, len(hub_points)):
            if _segments_intersect(
                hub_points[first_index],
                tip_points[first_index],
                hub_points[second_index],
                tip_points[second_index],
                tolerance,
            ):
                return True
    return False


def _segments_intersect(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
    tolerance: float,
) -> bool:
    if (
        max(first_start[0], first_end[0]) + tolerance < min(second_start[0], second_end[0])
        or max(second_start[0], second_end[0]) + tolerance < min(first_start[0], first_end[0])
        or max(first_start[1], first_end[1]) + tolerance < min(second_start[1], second_end[1])
        or max(second_start[1], second_end[1]) + tolerance < min(first_start[1], first_end[1])
    ):
        return False

    def orientation(start: np.ndarray, end: np.ndarray, point: np.ndarray) -> float:
        first = end - start
        second = point - start
        return float(first[0] * second[1] - first[1] * second[0])

    values = (
        orientation(first_start, first_end, second_start),
        orientation(first_start, first_end, second_end),
        orientation(second_start, second_end, first_start),
        orientation(second_start, second_end, first_end),
    )
    scale = max(
        float(np.linalg.norm(first_end - first_start)),
        float(np.linalg.norm(second_end - second_start)),
        1.0,
    )
    angular_tolerance = tolerance * scale
    return bool(
        min(values[0], values[1]) <= angular_tolerance
        and max(values[0], values[1]) >= -angular_tolerance
        and min(values[2], values[3]) <= angular_tolerance
        and max(values[2], values[3]) >= -angular_tolerance
    )


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _rounded_points(points: np.ndarray) -> list[list[float]]:
    return [[_round(value) for value in point] for point in points]


def _round(value: float) -> float:
    return round(float(value), 9)
