from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from part_rule_synthesis.impeller_v11_6_axis_first_pipeline import (
    task8_reconstruction_evidence_hash,
)
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph


_GEOMETRY_PATCH_VERSION = "1.1.2"
_PERIODIC_METHOD = "periodic_connected_face_components_v1_1_6"
_PERIODIC_PROVENANCE_AUTHORITY = "uploaded_step_brep_topology"
_TRUSTED_SOURCE_AUTHORITY = "source_step_brep"
_TRUSTED_PERIODIC_AUTHORITY = "canonical_periodic_recovery_v1_1_6"
_TRUSTED_MATERIAL_AUTHORITY = "canonical_support_recovery_v1_1_6"
_TRUSTED_SOURCE_DIGEST_BASIS = "load_step_source_authoritative_solid_subset_v1"
_SOURCE_SOLID_IDENTITY_BASIS = "load_step_source_solid_shape_identity_v1"
_FACE_SIGNATURE_BASIS = "trusted_source_face_record_with_adjacency_v1"
_COMPONENT_DIGEST_BASIS = "trusted_source_component_membership_v1"
_PERIODIC_DIGEST_BASIS = "trusted_source_periodic_population_v1"
_SUPPORT_DIGEST_BASIS = "trusted_source_support_payload_v1"
_COLLISION_FIDELITY = "sampled_v112_uv_grid_not_cad_certified"
_BLADE_CLASSES = ("main", "splitter")
_SHROUD_ROLES = frozenset({"shroud_support", "closed_shroud_attachment"})
_SHA256_LENGTH = 64
_COLLISION_RADIAL_CELL_COUNT = 64
_COLLISION_AXIAL_CELL_COUNT = 16
_COLLISION_REFINEMENT_DIVISIONS = 8
_COLLISION_TRIANGLE_HASH_CELL_MM = 1.0
_COLLISION_TRIANGLE_TOLERANCE_MM = 1.0e-7


class PatternReconstructionError(ValueError):
    """A fail-closed V1.1.6 pattern or material contract violation."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


def validate_mapped_pattern_reconstruction(
    surface_graph: Mapping[str, Any],
    mapping: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    *,
    task8_recovery_authority: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Bind Task 8 source evidence to an instantiated V1.1.2 surface graph."""

    graph = _completed_v112_graph(surface_graph)
    trusted_source = _trusted_source_topology(source_manifest)
    task8_authority = _validate_task8_evidence_authority(
        mapping,
        task8_recovery_authority,
        trusted_source,
    )
    periodic = _mapped_periodic_evidence(graph, mapping, trusted_source)
    material_partition = _mapped_material_partition(mapping, trusted_source)
    trusted_periodic = _periodic_partition_manifest(
        _mapping(
            task8_authority["periodic_provenance"].get(
                "pattern_population_evidence"
            ),
            "Task 8 authority periodic populations",
        ),
        trusted_source,
    )
    trusted_material_partition = copy.deepcopy(
        dict(
            _mapping(
                task8_authority["support_recovery"].get(
                    "pattern_material_partition"
                ),
                "Task 8 authority material partition",
            )
        )
    )
    trusted_material = {
        **trusted_material_partition,
        "authority": _TRUSTED_MATERIAL_AUTHORITY,
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
    }
    support = _mapped_support_evidence(material_partition, trusted_source)
    return validate_and_decorate_pattern_reconstruction(
        graph,
        periodic,
        support,
        trusted_source_topology_manifest=source_manifest,
        trusted_periodic_partition_manifest=trusted_periodic,
        trusted_material_support_manifest=trusted_material,
        _validated_graph=graph,
    )


def _mapped_periodic_evidence(
    graph: Mapping[str, Any],
    mapping: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
) -> dict[str, Any]:
    mapped = _mapping(mapping.get("periodic_provenance"), "mapping.periodic_provenance")
    periodic = copy.deepcopy(
        _mapping(
            mapped.get("pattern_population_evidence"),
            "mapping.periodic_provenance.pattern_population_evidence",
        )
    )
    periodic["measurement_tolerance_mm"] = _positive_finite(
        mapped.get("measurement_tolerance_mm"),
        "mapping.periodic_provenance.measurement_tolerance_mm",
    )
    periodic["generated_rigid_transform_tolerance_mm"] = _positive_finite(
        mapped.get(
            "generated_rigid_transform_tolerance_mm",
            mapped.get("source_linear_tolerance_mm"),
        ),
        "mapping.periodic_provenance.generated_rigid_transform_tolerance_mm",
    )
    source_collision = copy.deepcopy(
        dict(
            _mapping(
                periodic.get("collision_diagnostics"),
                "mapping source collision diagnostics",
            )
        )
    )
    source_collision_state = _declared_source_collision_state(source_collision)
    if source_collision_state == "FAIL":
        raise PatternReconstructionError(
            "v116_pattern_collision",
            "Task 8 source periodic populations contain a measured collision",
            details={"source_collision_diagnostics": source_collision},
        )
    if source_collision_state == "INVALID":
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid",
            "Task 8 source collision diagnostics are internally inconsistent",
            details={"source_collision_diagnostics": source_collision},
        )
    periodic["source_collision_diagnostics"] = source_collision
    periodic["source_collision_state"] = source_collision_state
    generated = _generated_blade_surfaces(graph)
    populations = periodic.get("populations")
    if periodic.get("method") != _PERIODIC_METHOD or not _is_sequence(populations):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid",
            "Task 8 mapping lacks complete measured periodic populations",
        )

    by_class: dict[str, dict[str, Any]] = {}
    digest_populations = []
    for raw_population in populations:
        population = dict(_mapping(raw_population, "mapped periodic population"))
        blade_class = population.get("classification")
        if blade_class not in _BLADE_CLASSES or blade_class in by_class:
            raise PatternReconstructionError(
                "v116_pattern_evidence_invalid",
                "mapped periodic populations contain duplicate or unknown classes",
            )
        instances = population.get("instances")
        if not _is_sequence(instances):
            raise PatternReconstructionError(
                "v116_pattern_evidence_invalid",
                f"mapped {blade_class} population has no instances",
            )
        sealed_instances = []
        for raw_instance in instances:
            instance = copy.deepcopy(dict(_mapping(raw_instance, "mapped instance")))
            index = _nonnegative_int(
                instance.get("lattice_index"), f"mapped {blade_class} lattice index"
            )
            try:
                envelope = _surface_family_envelope(
                    generated[blade_class][index],
                    include_collision_geometry=False,
                )
            except KeyError as exc:
                raise PatternReconstructionError(
                    "v116_pattern_count_mismatch",
                    f"mapped {blade_class} instance has no generated V1.1.2 family",
                ) from exc
            _seal_component_evidence(instance, trusted_source)
            instance["source_collision_envelope"] = {
                "angular_span_deg": instance.get("angular_span_deg"),
                "angular_envelope_deg": copy.deepcopy(
                    instance.get("angular_envelope_deg")
                ),
                "radial_support_range_mm": copy.deepcopy(
                    instance.get("radial_support_range_mm")
                ),
                "axial_support_range_mm": copy.deepcopy(
                    instance.get("axial_support_range_mm")
                ),
            }
            instance["collision_envelope_authority"] = (
                "instantiated_v112_surface_graph_uv_grid"
            )
            instance["angular_span_deg"] = envelope["span_deg"]
            instance["angular_envelope_deg"] = {
                "method": envelope["method"],
                "span_deg": envelope["span_deg"],
            }
            instance["radial_support_range_mm"] = list(envelope["radial_range_mm"])
            instance["axial_support_range_mm"] = list(envelope["axial_range_mm"])
            sealed_instances.append(instance)
        sealed_instances.sort(key=lambda item: item["lattice_index"])
        population["instances"] = sealed_instances
        representative = dict(
            _mapping(population.get("representative"), "mapped representative")
        )
        representative_instance = next(
            (
                instance
                for instance in sealed_instances
                if instance["source_component_id"]
                == representative.get("source_component_id")
            ),
            None,
        )
        if representative_instance is None:
            raise PatternReconstructionError(
                "v116_pattern_instance_contract_invalid",
                f"mapped {blade_class} representative is absent from its population",
            )
        representative["source_component_evidence"] = copy.deepcopy(
            representative_instance["source_component_evidence"]
        )
        population["representative"] = representative
        by_class[blade_class] = population
        digest_populations.append(_periodic_digest_population(population))

    periodic["populations"] = [
        by_class[name] for name in _BLADE_CLASSES if name in by_class
    ]
    periodic["main"] = by_class.get("main")
    periodic["splitter"] = by_class.get("splitter")
    collision_tolerance = _positive_finite(
        _mapping(
            periodic.get("collision_diagnostics"), "mapped collision diagnostics"
        ).get("tolerance_deg"),
        "mapped collision tolerance",
    )
    periodic["collision_diagnostics"] = {
        "collision_status": "PENDING_GENERATED_GRAPH_VALIDATION",
        "collision_free": None,
        "collision_count": 0,
        "collisions": [],
        "tolerance_deg": collision_tolerance,
        "measurement_authority": (
            "deferred_to_single_validate_populations_generated_graph_pass"
        ),
    }
    source_ids = sorted(
        face_id
        for population in periodic["populations"]
        for instance in population["instances"]
        for face_id in instance["source_face_ids"]
    )
    periodic["provenance"] = {
        "authentication_status": "PASS",
        "authority": _PERIODIC_PROVENANCE_AUTHORITY,
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "source_entity_ids": source_ids,
        "digest_basis": _PERIODIC_DIGEST_BASIS,
        "population_digest_sha256": _payload_digest(
            {
                "digest_basis": _PERIODIC_DIGEST_BASIS,
                "trusted_source_manifest_digest_sha256": trusted_source[
                    "manifest_digest_sha256"
                ],
                "method": _PERIODIC_METHOD,
                "populations": digest_populations,
            }
        ),
    }
    return periodic


def _validate_task8_evidence_authority(
    mapping: Mapping[str, Any],
    authority_value: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
) -> dict[str, Any]:
    authority = copy.deepcopy(
        dict(_mapping(authority_value, "Task 8 recovery authority"))
    )
    if (
        authority.get("authority") != "axis_first_task8_recovery_result"
        or authority.get("source_sha256") != trusted_source["source_sha256"]
    ):
        raise PatternReconstructionError(
            "v116_task8_evidence_untrusted",
            "Task 8 recovery authority is absent or bound to another source",
        )
    authority_support = _mapping(
        authority.get("support_recovery"), "Task 8 authority support recovery"
    )
    authority_periodic = _mapping(
        authority.get("periodic_provenance"),
        "Task 8 authority periodic provenance",
    )
    expected = task8_reconstruction_evidence_hash(
        authority_support,
        authority_periodic,
        trusted_source["source_sha256"],
    )
    mapping_support = _mapping(
        mapping.get("support_recovery"), "mapping.support_recovery"
    )
    mapping_periodic = _mapping(
        mapping.get("periodic_provenance"), "mapping.periodic_provenance"
    )
    if (
        authority.get("evidence_hash_sha256") != expected
        or mapping.get("task8_reconstruction_evidence_hash_sha256") != expected
        or mapping_support != authority_support
        or mapping_periodic != authority_periodic
    ):
        raise PatternReconstructionError(
            "v116_task8_evidence_untrusted",
            "candidate mapping differs from the independently retained Task 8 recovery",
            details={
                "authority_sha256": authority.get("evidence_hash_sha256"),
                "mapping_sha256": mapping.get(
                    "task8_reconstruction_evidence_hash_sha256"
                ),
                "expected_sha256": expected,
            },
        )
    return authority


def _seal_component_evidence(
    instance: dict[str, Any], trusted_source: Mapping[str, Any]
) -> None:
    source_component_id = _identifier(
        instance.get("source_component_id"), "mapped source_component_id"
    )
    source_face_ids = _identifiers(
        instance.get("source_face_ids"), "mapped source_face_ids"
    )
    evidence = copy.deepcopy(
        dict(
            _mapping(
                instance.get("source_component_evidence"),
                "mapped source_component_evidence",
            )
        )
    )
    evidence["source_component_id"] = source_component_id
    evidence["source_entity_ids"] = list(source_face_ids)
    basis = _trusted_component_digest_basis(
        trusted_source,
        source_component_id=source_component_id,
        source_face_ids=source_face_ids,
    )
    evidence["provenance"] = {
        "authority": _PERIODIC_PROVENANCE_AUTHORITY,
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "source_sha256": trusted_source["source_sha256"],
        "source_entity_ids": list(source_face_ids),
        "signature_hashes": sorted(
            basis["face_signature_sha256_by_id"].values()
        ),
        "digest_basis": _COMPONENT_DIGEST_BASIS,
        "component_digest_sha256": _payload_digest(basis),
    }
    instance["source_component_evidence"] = evidence


def _periodic_digest_population(population: Mapping[str, Any]) -> dict[str, Any]:
    representative = _mapping(population.get("representative"), "representative")
    return {
        "population_id": population["population_id"],
        "count": int(population["count"]),
        "pitch_deg": float(population["pitch_deg"]),
        "phase_deg": _normalized_angle(float(population["phase_deg"])),
        "representative": {
            "source_component_id": representative["source_component_id"],
            "source_face_ids": sorted(representative["source_face_ids"]),
            "lattice_index": int(representative["lattice_index"]),
        },
        "instances": [
            {
                "instance_id": instance["instance_id"],
                "source_component_id": instance["source_component_id"],
                "source_face_ids": sorted(instance["source_face_ids"]),
                "lattice_index": int(instance["lattice_index"]),
                "phase_deg": _normalized_angle(float(instance["measured_angle_deg"])),
                "transform_from_representative": [
                    [float(value) for value in row]
                    for row in instance["transform_from_representative"]
                ],
                "component_digest_sha256": instance[
                    "source_component_evidence"
                ]["provenance"]["component_digest_sha256"],
            }
            for instance in sorted(
                population["instances"], key=lambda item: item["lattice_index"]
            )
        ],
    }


def _periodic_partition_manifest(
    periodic: Mapping[str, Any], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "authority": _TRUSTED_PERIODIC_AUTHORITY,
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "method": _PERIODIC_METHOD,
        "main_blade_count": periodic["main_blade_count"],
        "splitter_blade_count": periodic["splitter_blade_count"],
        "populations": [
            {
                "population_id": population["population_id"],
                "count": population["count"],
                "representative_source_component_id": population[
                    "representative"
                ]["source_component_id"],
                "instances": [
                    {
                        "instance_id": instance["instance_id"],
                        "source_component_id": instance["source_component_id"],
                        "source_face_ids": list(instance["source_face_ids"]),
                        "lattice_index": instance["lattice_index"],
                    }
                    for instance in population["instances"]
                ],
            }
            for population in periodic["populations"]
        ],
    }


def _mapped_material_partition(
    mapping: Mapping[str, Any], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    recovery = _mapping(mapping.get("support_recovery"), "mapping.support_recovery")
    partition = copy.deepcopy(
        dict(
            _mapping(
                recovery.get("pattern_material_partition"),
                "mapping.support_recovery.pattern_material_partition",
            )
        )
    )
    mode = partition.get("mode")
    if mode not in {"open", "closed"}:
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "mapped material partition requires open or closed mode",
        )
    source_ids = set(trusted_source["faces_by_id"])
    hub_ids = _identifiers(
        partition.get("hub_support_face_ids"),
        "mapping hub_support_face_ids",
    )
    hub_attachments = _mapping(
        partition.get("hub_attachment_face_ids_by_instance"),
        "mapping hub attachments",
    )
    normalized_hub_attachments = {
        str(instance_id): _identifiers(face_ids, "mapping hub attachment faces")
        for instance_id, face_ids in hub_attachments.items()
    }
    partition["hub_support_face_ids"] = hub_ids
    partition["hub_attachment_face_ids_by_instance"] = (
        normalized_hub_attachments
    )
    declared_ids = set(hub_ids)
    declared_ids.update(
        face_id
        for face_ids in normalized_hub_attachments.values()
        for face_id in face_ids
    )
    if mode == "open":
        open_tip_ids = _identifiers(
            partition.get("open_tip_reference_face_ids"),
            "mapping open tip reference faces",
        )
        partition["open_tip_reference_face_ids"] = open_tip_ids
        declared_ids.update(open_tip_ids)
    else:
        shroud = _mapping(partition.get("material_shroud"), "mapped material shroud")
        shroud = copy.deepcopy(dict(shroud))
        for key in (
            "source_face_ids",
            "inner_flowpath_face_ids",
            "outer_material_face_ids",
        ):
            shroud[key] = _identifiers(
                shroud.get(key), f"mapping material shroud {key}"
            )
        shroud_attachments = _mapping(
            shroud.get("blade_attachment_face_ids_by_instance"),
            "mapping shroud attachments",
        )
        shroud["blade_attachment_face_ids_by_instance"] = {
            str(instance_id): _identifiers(
                face_ids, "mapping shroud attachment faces"
            )
            for instance_id, face_ids in shroud_attachments.items()
        }
        shroud["finite_thickness"] = _finite_thickness(
            shroud.get("finite_thickness"), shroud
        )
        partition["material_shroud"] = shroud
        declared_ids.update(shroud["source_face_ids"])
        declared_ids.update(
            face_id
            for face_ids in shroud[
                "blade_attachment_face_ids_by_instance"
            ].values()
            for face_id in face_ids
        )
    if not declared_ids or not declared_ids.issubset(source_ids):
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "mapped material partition is not contained in the trusted STEP source",
        )
    return partition


def _mapped_support_evidence(
    partition: Mapping[str, Any], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    hub_attachment = _mapped_attachment(
        partition["hub_attachment_face_ids_by_instance"], trusted_source
    )
    hub = {
        "status": "PASS",
        "semantic_role": "hub_support",
        "material": True,
        "source_face_ids": list(partition["hub_support_face_ids"]),
        "blade_attachment": hub_attachment,
    }
    _seal_support_record(hub, hub["source_face_ids"], trusted_source)
    evidence: dict[str, Any] = {
        "status": "PASS",
        "authority": "authenticated_topology_support_v1_1_6",
        "mode": partition["mode"],
        "hub_support": hub,
    }
    if partition["mode"] == "open":
        reference = {
            "status": "PASS",
            "semantic_role": "open_tip_reference",
            "material": False,
            "render_default": "hidden",
            "export_default": "excluded",
            "source_face_ids": list(partition["open_tip_reference_face_ids"]),
        }
        _seal_support_record(reference, reference["source_face_ids"], trusted_source)
        evidence.update({"material_shroud": None, "open_tip_reference": reference})
    else:
        partition_shroud = _mapping(
            partition.get("material_shroud"), "mapped material shroud"
        )
        shroud_attachment = _mapped_attachment(
            partition_shroud["blade_attachment_face_ids_by_instance"],
            trusted_source,
        )
        shroud = {
            "status": "PASS",
            "semantic_role": "closed_shroud",
            "material": True,
            "source_face_ids": list(partition_shroud["source_face_ids"]),
            "inner_flowpath_face_ids": list(
                partition_shroud["inner_flowpath_face_ids"]
            ),
            "outer_material_face_ids": list(
                partition_shroud["outer_material_face_ids"]
            ),
            "finite_thickness": copy.deepcopy(
                partition_shroud["finite_thickness"]
            ),
            "blade_attachment": shroud_attachment,
        }
        _seal_support_record(shroud, shroud["source_face_ids"], trusted_source)
        evidence.update({"open_tip_reference": None, "material_shroud": shroud})
    _seal_support_record(evidence, sorted(trusted_source["faces_by_id"]), trusted_source)
    return evidence


def _mapped_attachment(
    by_instance: Mapping[str, Sequence[str]], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    by_instance = _mapping(by_instance, "mapped attachment by instance")
    normalized = {
        str(instance_id): _identifiers(face_ids, "mapped attachment faces")
        for instance_id, face_ids in sorted(by_instance.items())
    }
    attachment = {
        "instance_ids": sorted(normalized),
        "source_face_ids_by_instance": normalized,
        "attachment_authority": "authenticated_shared_topology",
    }
    _seal_support_record(
        attachment,
        sorted(face_id for face_ids in normalized.values() for face_id in face_ids),
        trusted_source,
    )
    return attachment


def _seal_support_record(
    record: dict[str, Any],
    source_face_ids: Sequence[str],
    trusted_source: Mapping[str, Any],
) -> None:
    provenance = {
        "authentication_status": "PASS",
        "authority": "authenticated_source_topology",
        "source_solid_id": trusted_source["source_solid_shape_identity"],
        "source_sha256": trusted_source["source_sha256"],
        "source_entity_ids": sorted(source_face_ids),
        "digest_basis": _SUPPORT_DIGEST_BASIS,
    }
    record["provenance"] = provenance
    provenance["evidence_digest_sha256"] = _payload_digest(
        {
            "digest_basis": _SUPPORT_DIGEST_BASIS,
            "trusted_source_manifest_digest_sha256": trusted_source[
                "manifest_digest_sha256"
            ],
            "source_sha256": provenance["source_sha256"],
            "source_solid_shape_identity": provenance["source_solid_id"],
            "source_entity_ids": provenance["source_entity_ids"],
            "evidence_payload": _without_provenance(record),
        }
    )


def validate_and_decorate_pattern_reconstruction(
    surface_graph: Mapping[str, Any],
    periodic_population_evidence: Mapping[str, Any],
    topology_support_evidence: Mapping[str, Any],
    *,
    trusted_source_topology_manifest: Mapping[str, Any],
    trusted_periodic_partition_manifest: Mapping[str, Any],
    trusted_material_support_manifest: Mapping[str, Any],
    _validated_graph: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Validate Task9 periodic/material evidence against a completed V1.1.2 graph.

    Geometry is never constructed here. The returned graph uses copy-on-write
    surface records whose existing blade surfaces are decorated with measured
    population provenance. Large immutable geometry arrays remain shared.
    The second return value is recursively immutable. Source identity crosses an
    explicit trust boundary through a canonical ``load_step_source`` topology
    subset. Solid identity is derived from source SHA, solid topology/measurements,
    face records, and symmetric adjacency; it is never supplied by the caller.
    Collision checks sample authoritative V1.1.2 ``uv_grid`` points; they are not
    CAD/B-Rep intersection certification.
    """

    graph = (
        _validated_graph
        if _validated_graph is not None
        else _completed_v112_graph(surface_graph)
    )
    periodic = _mapping(periodic_population_evidence, "periodic_population_evidence")
    trusted_source = _trusted_source_topology(trusted_source_topology_manifest)
    trusted_periodic = _trusted_periodic_partition(
        trusted_periodic_partition_manifest, trusted_source
    )
    trusted_material = _trusted_material_partition(
        trusted_material_support_manifest,
        trusted_source,
        trusted_periodic,
    )
    periodic_provenance = _validate_periodic_provenance(periodic, trusted_source)
    tolerance_mm = _positive_finite(
        periodic.get("measurement_tolerance_mm"),
        "periodic_population_evidence.measurement_tolerance_mm",
    )
    generated_tolerance_mm = _positive_finite(
        periodic.get("generated_rigid_transform_tolerance_mm", tolerance_mm),
        "periodic_population_evidence.generated_rigid_transform_tolerance_mm",
    )
    angular_tolerance_deg = _angular_tolerance(periodic)
    blade_surfaces = _generated_blade_surfaces(graph)
    expected_counts = _expected_population_counts(graph)
    population_records, surface_bindings, instance_ids = _validate_populations(
        graph=graph,
        periodic=periodic,
        blade_surfaces=blade_surfaces,
        expected_counts=expected_counts,
        tolerance_mm=tolerance_mm,
        generated_tolerance_mm=generated_tolerance_mm,
        angular_tolerance_deg=angular_tolerance_deg,
        periodic_provenance=periodic_provenance,
        trusted_source=trusted_source,
        trusted_periodic=trusted_periodic,
    )
    source_collision_diagnostics = _mapping(
        periodic.get(
            "source_collision_diagnostics",
            periodic.get("collision_diagnostics"),
        ),
        "periodic_population_evidence.source_collision_diagnostics",
    )
    source_collision_state = _declared_source_collision_state(
        source_collision_diagnostics
    )
    material_record = _validate_material_topology(
        graph,
        topology_support_evidence,
        instance_ids=instance_ids,
        periodic_provenance=periodic_provenance,
        trusted_source=trusted_source,
        trusted_material=trusted_material,
    )

    decorated = _copy_surface_graph_for_pattern_decoration(graph)
    decorated_by_id = {
        surface.get("id"): surface for surface in decorated.get("surfaces", [])
    }
    for surface_id, binding in surface_bindings.items():
        surface = decorated_by_id[surface_id]
        surface["periodic_pattern_binding"] = copy.deepcopy(binding)
        if _is_non_material_topological_seam(surface):
            continue
        surface["material"] = True
        surface["render_default"] = "material"
        surface["export_default"] = "included"

    _decorate_material_surfaces(decorated, material_record)
    manifest_payload = {
        "contract": "impeller_v1_1_6_periodic_pattern_material",
        "status": "PASS" if source_collision_state == "PASS" else "REVIEW_ONLY",
        "geometry_patch_version": _GEOMETRY_PATCH_VERSION,
        "source_generation_id": graph.get("generation_id"),
        "pattern": {
            "method": periodic["method"],
            "measurement_tolerance_mm": tolerance_mm,
            "generated_rigid_transform_tolerance_mm": generated_tolerance_mm,
            "angular_tolerance_deg": angular_tolerance_deg,
            "main_blade_count": expected_counts["main"],
            "splitter_blade_count": expected_counts["splitter"],
            "populations": population_records,
            "surface_bindings": [
                {"surface_id": surface_id, **copy.deepcopy(binding)}
                for surface_id, binding in sorted(surface_bindings.items())
            ],
            "closure_status": "PASS",
            "collision_status": (
                "PASS"
                if source_collision_state == "PASS"
                else "SOURCE_UNKNOWN_RECONSTRUCTED_SAMPLE_PASS"
            ),
            "source_collision_status": source_collision_state,
            "source_topology_separated": source_collision_diagnostics.get(
                "source_topology_separated"
            ),
            "exact_brep_collision_checked": source_collision_diagnostics.get(
                "exact_brep_collision_checked"
            ),
            "exact_brep_collision_free": source_collision_diagnostics.get(
                "exact_brep_collision_free"
            ),
            "collision_fidelity": _COLLISION_FIDELITY,
            "trusted_periodic_partition_digest_sha256": trusted_periodic[
                "partition_digest_sha256"
            ],
            "source_provenance": copy.deepcopy(periodic_provenance),
        },
        "material": {
            **material_record,
            "trusted_material_partition_digest_sha256": trusted_material[
                "partition_digest_sha256"
            ],
        },
    }
    manifest_payload["manifest_digest_sha256"] = _payload_digest(manifest_payload)
    decorated["v1_1_6_pattern_material"] = {
        "status": manifest_payload["status"],
        "manifest_digest_sha256": manifest_payload["manifest_digest_sha256"],
        "pattern_fidelity": "measured_rigid_cyclic_validation",
        "collision_fidelity": _COLLISION_FIDELITY,
        "material_fidelity": "authenticated_topology_support_validation",
    }
    return decorated, _freeze(manifest_payload)


def _copy_surface_graph_for_pattern_decoration(
    surface_graph: Mapping[str, Any],
) -> dict[str, Any]:
    decorated = dict(surface_graph)
    decorated["surfaces"] = []
    for raw_surface in surface_graph.get("surfaces", ()):
        surface = dict(raw_surface)
        display = raw_surface.get("display")
        if isinstance(display, Mapping):
            surface["display"] = copy.deepcopy(dict(display))
        decorated["surfaces"].append(surface)
    return decorated


def _is_non_material_topological_seam(surface: Mapping[str, Any]) -> bool:
    source = surface.get("source")
    return bool(
        surface.get("material") is False
        and surface.get("export_default") == "excluded"
        and surface.get("fidelity") == "topological_shared_seam_no_finite_face"
        and isinstance(source, Mapping)
        and source.get("authority") == "authenticated_step_shared_seam"
    )


def _completed_v112_graph(surface_graph: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(surface_graph, "surface_graph")
    graph = candidate if isinstance(candidate, dict) else dict(candidate)
    failures = validate_v11_surface_graph(graph)
    if (
        graph.get("geometry_patch_version") != _GEOMETRY_PATCH_VERSION
        or graph.get("geometry_generation_status") != "PASS"
        or graph.get("surface_graph_status") != "PASS"
        or graph.get("transition_failures")
        or failures
    ):
        raise PatternReconstructionError(
            "v116_pattern_graph_invalid",
            "pattern validation requires a completed, passing V1.1.2 surface graph",
            details={
                "geometry_patch_version": graph.get("geometry_patch_version"),
                "geometry_generation_status": graph.get("geometry_generation_status"),
                "surface_graph_status": graph.get("surface_graph_status"),
                "validation_failures": failures,
            },
        )
    surfaces = graph.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise PatternReconstructionError(
            "v116_pattern_graph_invalid",
            "completed V1.1.2 graph has no surface inventory",
        )
    return graph


def _generated_blade_surfaces(
    graph: Mapping[str, Any],
) -> dict[str, dict[int, dict[tuple[str, str], Mapping[str, Any]]]]:
    grouped: dict[str, dict[int, dict[tuple[str, str], Mapping[str, Any]]]] = {
        blade_class: defaultdict(dict) for blade_class in _BLADE_CLASSES
    }
    seen_ids: set[str] = set()
    for surface in graph["surfaces"]:
        if not isinstance(surface, Mapping):
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid", "surface inventory contains a non-mapping record"
            )
        surface_id = _identifier(surface.get("id"), "surface.id")
        if surface_id in seen_ids:
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid", f"duplicate surface id: {surface_id}"
            )
        seen_ids.add(surface_id)
        blade_class = surface.get("blade_class")
        if blade_class is None:
            continue
        if blade_class not in _BLADE_CLASSES:
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid",
                f"unsupported generated blade class: {blade_class}",
            )
        pair_index = surface.get("blade_pair_index")
        if isinstance(pair_index, bool) or not isinstance(pair_index, int) or pair_index < 0:
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid",
                f"surface {surface_id} has an invalid blade_pair_index",
            )
        role = _identifier(surface.get("role"), f"{surface_id}.role")
        family = _identifier(surface.get("face_family"), f"{surface_id}.face_family")
        family_key = (role, family)
        if family_key in grouped[blade_class][pair_index]:
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid",
                f"blade {blade_class}[{pair_index}] repeats surface family {family_key}",
            )
        _surface_points(surface, surface_id)
        grouped[blade_class][pair_index][family_key] = surface
    return grouped


def _expected_population_counts(graph: Mapping[str, Any]) -> dict[str, int]:
    canonical = _mapping(
        graph.get("canonical_nurbs_parameterization"),
        "surface_graph.canonical_nurbs_parameterization",
    )
    population = _mapping(
        canonical.get("blade_population"),
        "canonical_nurbs_parameterization.blade_population",
    )
    return {
        "main": _nonnegative_int(population.get("main_blade_count"), "main_blade_count"),
        "splitter": _nonnegative_int(
            population.get("splitter_blade_count"), "splitter_blade_count"
        ),
    }


def _trusted_source_topology(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the independently trusted ``load_step_source`` manifest.

    The derived solid identity hashes authoritative source and solid fields through
    ``surface_type_inventory``, plus normalized face records and adjacency. The
    environment-specific ``occt_version`` and non-authoritative ``tessellation``
    display settings are deliberately outside that canonical identity subset.
    """

    if not isinstance(value, Mapping):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology manifest must be a mapping",
        )
    source_sha256 = _sha256_for_reason(
        value.get("sha256"),
        "trusted source topology sha256",
        "v116_trusted_source_manifest_invalid",
    )
    raw_faces = value.get("faces")
    if value.get("authority") != _TRUSTED_SOURCE_AUTHORITY or not _is_sequence(raw_faces):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology must use the source STEP B-Rep authority and face records",
        )

    faces: list[dict[str, Any]] = []
    face_ids: set[str] = set()
    entity_indices: set[int] = set()
    for raw_face in raw_faces:
        if not isinstance(raw_face, Mapping):
            raise PatternReconstructionError(
                "v116_trusted_source_manifest_invalid",
                "trusted source topology contains a non-mapping face record",
            )
        face_id = _identifier_for_reason(
            raw_face.get("face_id"),
            "trusted source face_id",
            "v116_trusted_source_manifest_invalid",
        )
        entity_index = _nonnegative_int_for_reason(
            raw_face.get("source_entity_index"),
            f"trusted source face {face_id} source_entity_index",
            "v116_trusted_source_manifest_invalid",
        )
        if face_id in face_ids or entity_index in entity_indices:
            raise PatternReconstructionError(
                "v116_trusted_source_manifest_invalid",
                "trusted source topology face ids and entity indices must be unique",
            )
        face_ids.add(face_id)
        entity_indices.add(entity_index)
        bounds = raw_face.get("bounds_mm")
        if not isinstance(bounds, Mapping):
            raise PatternReconstructionError(
                "v116_trusted_source_manifest_invalid",
                f"trusted source face {face_id} has no canonical bounds",
            )
        minimum = _trusted_vector(bounds.get("minimum"), f"{face_id}.bounds_mm.minimum")
        maximum = _trusted_vector(bounds.get("maximum"), f"{face_id}.bounds_mm.maximum")
        if any(lower > upper for lower, upper in zip(minimum, maximum)):
            raise PatternReconstructionError(
                "v116_trusted_source_manifest_invalid",
                f"trusted source face {face_id} has inverted bounds",
            )
        faces.append(
            {
                "face_id": face_id,
                "source_entity_index": entity_index,
                "geometry_type": _identifier_for_reason(
                    raw_face.get("geometry_type"),
                    f"trusted source face {face_id} geometry_type",
                    "v116_trusted_source_manifest_invalid",
                ),
                "area_mm2": _positive_finite_for_reason(
                    raw_face.get("area_mm2"),
                    f"trusted source face {face_id} area_mm2",
                    "v116_trusted_source_manifest_invalid",
                ),
                "centroid_mm": _trusted_vector(
                    raw_face.get("centroid_mm"), f"{face_id}.centroid_mm"
                ),
                "bounds_mm": {"minimum": minimum, "maximum": maximum},
            }
        )
    if not faces or _nonnegative_int_for_reason(
        value.get("face_count"),
        "trusted source topology face_count",
        "v116_trusted_source_manifest_invalid",
    ) != len(faces):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology face_count does not match its face inventory",
        )

    raw_adjacency = value.get("adjacency")
    if not isinstance(raw_adjacency, Mapping) or set(raw_adjacency) != face_ids:
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology adjacency must cover every face exactly",
        )
    adjacency: dict[str, list[str]] = {}
    for face_id in sorted(face_ids):
        neighbors = _trusted_identifier_sequence(
            raw_adjacency[face_id], f"trusted source adjacency for {face_id}"
        )
        if face_id in neighbors or not set(neighbors).issubset(face_ids):
            raise PatternReconstructionError(
                "v116_trusted_source_manifest_invalid",
                f"trusted source adjacency for {face_id} contains an invalid face",
            )
        adjacency[face_id] = sorted(neighbors)
    if any(
        face_id not in adjacency[neighbor]
        for face_id, neighbors in adjacency.items()
        for neighbor in neighbors
    ):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology adjacency must be symmetric",
        )

    ordered_faces = sorted(
        faces, key=lambda face: (face["source_entity_index"], face["face_id"])
    )
    solid_count = _nonnegative_int_for_reason(
        value.get("solid_count"),
        "trusted source topology solid_count",
        "v116_trusted_source_manifest_invalid",
    )
    shell_count = _nonnegative_int_for_reason(
        value.get("shell_count"),
        "trusted source topology shell_count",
        "v116_trusted_source_manifest_invalid",
    )
    edge_count = _nonnegative_int_for_reason(
        value.get("edge_count"),
        "trusted source topology edge_count",
        "v116_trusted_source_manifest_invalid",
    )
    vertex_count = _nonnegative_int_for_reason(
        value.get("vertex_count"),
        "trusted source topology vertex_count",
        "v116_trusted_source_manifest_invalid",
    )
    closed_solid = value.get("closed_solid")
    if (
        solid_count != 1
        or shell_count < 1
        or edge_count < 1
        or vertex_count < 1
        or closed_solid is not True
    ):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology must describe exactly one closed STEP solid",
        )
    bounds = value.get("bounds_mm")
    if not isinstance(bounds, Mapping):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology requires canonical solid bounds",
        )
    solid_minimum = _trusted_vector(
        bounds.get("minimum"), "trusted source topology bounds_mm.minimum"
    )
    solid_maximum = _trusted_vector(
        bounds.get("maximum"), "trusted source topology bounds_mm.maximum"
    )
    if any(lower > upper for lower, upper in zip(solid_minimum, solid_maximum)):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology has inverted solid bounds",
        )
    raw_surface_inventory = value.get("surface_type_inventory")
    if not isinstance(raw_surface_inventory, Mapping) or not raw_surface_inventory:
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology requires a surface type inventory",
        )
    surface_inventory: dict[str, int] = {}
    for raw_name, raw_count in raw_surface_inventory.items():
        name = _identifier_for_reason(
            raw_name,
            "trusted source topology surface type",
            "v116_trusted_source_manifest_invalid",
        )
        surface_inventory[name] = _nonnegative_int_for_reason(
            raw_count,
            f"trusted source topology surface count {name}",
            "v116_trusted_source_manifest_invalid",
        )
    if sum(surface_inventory.values()) != len(ordered_faces):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid",
            "trusted source topology surface inventory does not match face_count",
        )

    authoritative_solid_subset = {
        "authority": _TRUSTED_SOURCE_AUTHORITY,
        "source_sha256": source_sha256,
        "solid_count": solid_count,
        "shell_count": shell_count,
        "face_count": len(ordered_faces),
        "edge_count": edge_count,
        "vertex_count": vertex_count,
        "closed_solid": closed_solid,
        "volume_mm3": _positive_finite_for_reason(
            value.get("volume_mm3"),
            "trusted source topology volume_mm3",
            "v116_trusted_source_manifest_invalid",
        ),
        "surface_area_mm2": _positive_finite_for_reason(
            value.get("surface_area_mm2"),
            "trusted source topology surface_area_mm2",
            "v116_trusted_source_manifest_invalid",
        ),
        "centroid_mm": _trusted_vector(
            value.get("centroid_mm"), "trusted source topology centroid_mm"
        ),
        "bounds_mm": {"minimum": solid_minimum, "maximum": solid_maximum},
        "surface_type_inventory": dict(sorted(surface_inventory.items())),
        "faces": ordered_faces,
        "adjacency": adjacency,
    }
    source_solid = "source-solid-sha256:" + _payload_digest(
        {
            "digest_basis": _SOURCE_SOLID_IDENTITY_BASIS,
            **authoritative_solid_subset,
        }
    )
    canonical_manifest = {
        "digest_basis": _TRUSTED_SOURCE_DIGEST_BASIS,
        **authoritative_solid_subset,
        "source_solid_shape_identity": source_solid,
    }
    face_signatures = {
        face["face_id"]: _payload_digest(
            {
                "digest_basis": _FACE_SIGNATURE_BASIS,
                "source_sha256": source_sha256,
                "source_solid_shape_identity": source_solid,
                "face": face,
                "adjacent_face_ids": adjacency[face["face_id"]],
            }
        )
        for face in ordered_faces
    }
    return {
        **canonical_manifest,
        "faces_by_id": {face["face_id"]: face for face in ordered_faces},
        "face_signature_sha256_by_id": face_signatures,
        "manifest_digest_sha256": _payload_digest(canonical_manifest),
    }


def _trusted_periodic_partition(
    value: Mapping[str, Any], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize the independent canonical periodic-recovery partition."""

    partition = _trusted_partition_mapping(value, "trusted periodic partition")
    _validate_trusted_partition_source(
        partition,
        authority=_TRUSTED_PERIODIC_AUTHORITY,
        trusted_source=trusted_source,
        name="trusted periodic partition",
    )
    if partition.get("method") != _PERIODIC_METHOD:
        raise PatternReconstructionError(
            "v116_trusted_periodic_partition_invalid",
            "trusted periodic partition has the wrong recovery method",
        )
    counts = {
        "main": _trusted_nonnegative_int(
            partition.get("main_blade_count"), "main_blade_count", "periodic"
        ),
        "splitter": _trusted_nonnegative_int(
            partition.get("splitter_blade_count"),
            "splitter_blade_count",
            "periodic",
        ),
    }
    if counts["main"] < 2:
        raise PatternReconstructionError(
            "v116_trusted_periodic_partition_invalid",
            "trusted periodic partition requires at least two main blades",
        )
    raw_populations = partition.get("populations")
    if not _is_sequence(raw_populations):
        raise PatternReconstructionError(
            "v116_trusted_periodic_partition_invalid",
            "trusted periodic populations must be a sequence",
        )
    expected_classes = ["main"] + (["splitter"] if counts["splitter"] else [])
    by_class: dict[str, Mapping[str, Any]] = {}
    for raw_population in raw_populations:
        population = _trusted_partition_mapping(raw_population, "trusted population")
        population_id = population.get("population_id")
        if population_id not in expected_classes or population_id in by_class:
            raise PatternReconstructionError(
                "v116_trusted_periodic_partition_invalid",
                "trusted periodic partition has duplicate or unexpected populations",
            )
        by_class[population_id] = population
    if sorted(by_class) != sorted(expected_classes):
        raise PatternReconstructionError(
            "v116_trusted_periodic_partition_invalid",
            "trusted periodic partition is incomplete",
        )

    normalized_populations = []
    all_face_ids: set[str] = set()
    all_component_ids: set[str] = set()
    all_instance_ids: set[str] = set()
    for blade_class in expected_classes:
        population = by_class[blade_class]
        count = counts[blade_class]
        if _trusted_nonnegative_int(
            population.get("count"), f"{blade_class}.count", "periodic"
        ) != count:
            raise PatternReconstructionError(
                "v116_trusted_periodic_partition_invalid",
                f"trusted {blade_class} partition count is inconsistent",
            )
        representative_id = _trusted_identifier(
            population.get("representative_source_component_id"),
            f"trusted {blade_class} representative component",
            "periodic",
        )
        raw_instances = population.get("instances")
        if not _is_sequence(raw_instances) or len(raw_instances) != count:
            raise PatternReconstructionError(
                "v116_trusted_periodic_partition_invalid",
                f"trusted {blade_class} partition has incomplete instances",
            )
        normalized_instances = []
        component_ids: set[str] = set()
        lattice_indices: set[int] = set()
        for raw_instance in raw_instances:
            instance = _trusted_partition_mapping(raw_instance, "trusted instance")
            instance_id = _trusted_identifier(
                instance.get("instance_id"), "trusted periodic instance_id", "periodic"
            )
            component_id = _trusted_identifier(
                instance.get("source_component_id"),
                "trusted periodic source_component_id",
                "periodic",
            )
            face_ids = sorted(
                _trusted_nonempty_identifiers(
                    instance.get("source_face_ids"),
                    "trusted periodic source_face_ids",
                    "periodic",
                )
            )
            lattice_index = _trusted_nonnegative_int(
                instance.get("lattice_index"),
                "trusted periodic lattice_index",
                "periodic",
            )
            if (
                lattice_index >= count
                or lattice_index in lattice_indices
                or instance_id in all_instance_ids
                or component_id in all_component_ids
                or all_face_ids.intersection(face_ids)
                or not set(face_ids).issubset(trusted_source["faces_by_id"])
            ):
                raise PatternReconstructionError(
                    "v116_trusted_periodic_partition_invalid",
                    "trusted periodic component ownership is invalid or not source-backed",
                )
            lattice_indices.add(lattice_index)
            component_ids.add(component_id)
            all_instance_ids.add(instance_id)
            all_component_ids.add(component_id)
            all_face_ids.update(face_ids)
            normalized_instances.append(
                {
                    "instance_id": instance_id,
                    "source_component_id": component_id,
                    "source_face_ids": face_ids,
                    "lattice_index": lattice_index,
                }
            )
        if lattice_indices != set(range(count)) or representative_id not in component_ids:
            raise PatternReconstructionError(
                "v116_trusted_periodic_partition_invalid",
                f"trusted {blade_class} lattice or representative is invalid",
            )
        normalized_populations.append(
            {
                "population_id": blade_class,
                "count": count,
                "representative_source_component_id": representative_id,
                "instances": sorted(
                    normalized_instances, key=lambda item: item["lattice_index"]
                ),
            }
        )
    normalized = {
        "authority": _TRUSTED_PERIODIC_AUTHORITY,
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "method": _PERIODIC_METHOD,
        "main_blade_count": counts["main"],
        "splitter_blade_count": counts["splitter"],
        "populations": normalized_populations,
        "source_entity_ids": sorted(all_face_ids),
    }
    normalized["partition_digest_sha256"] = _payload_digest(normalized)
    return normalized


def _trusted_material_partition(
    value: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
    trusted_periodic: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize exact support/material roles from canonical support recovery."""

    partition = _trusted_partition_mapping(value, "trusted material partition")
    _validate_trusted_partition_source(
        partition,
        authority=_TRUSTED_MATERIAL_AUTHORITY,
        trusted_source=trusted_source,
        name="trusted material partition",
    )
    mode = partition.get("mode")
    if mode not in {"open", "closed"}:
        raise PatternReconstructionError(
            "v116_trusted_material_partition_invalid",
            "trusted material partition requires open or closed mode",
        )
    instance_ids = sorted(
        instance["instance_id"]
        for population in trusted_periodic["populations"]
        for instance in population["instances"]
    )
    hub_face_ids = sorted(
        _trusted_nonempty_identifiers(
            partition.get("hub_support_face_ids"),
            "trusted hub_support_face_ids",
            "material",
        )
    )
    hub_attachments = _trusted_attachment_partition(
        partition.get("hub_attachment_face_ids_by_instance"),
        instance_ids,
        "trusted hub attachments",
    )
    normalized: dict[str, Any] = {
        "authority": _TRUSTED_MATERIAL_AUTHORITY,
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "mode": mode,
        "hub_support_face_ids": hub_face_ids,
        "hub_attachment_face_ids_by_instance": hub_attachments,
    }
    role_face_ids = set(hub_face_ids)
    non_hub_material_face_ids: set[str] = set()
    construction_evidence_face_ids: set[str] = set()
    if mode == "open":
        open_tip_ids = sorted(
            _trusted_nonempty_identifiers(
                partition.get("open_tip_reference_face_ids"),
                "trusted open_tip_reference_face_ids",
                "material",
            )
        )
        if partition.get("material_shroud") is not None:
            raise PatternReconstructionError(
                "v116_trusted_material_partition_invalid",
                "trusted open partition cannot contain a material shroud",
            )
        normalized.update(
            {
                "open_tip_reference_face_ids": open_tip_ids,
                "material_shroud": None,
            }
        )
        construction_evidence_face_ids.update(open_tip_ids)
    else:
        if partition.get("open_tip_reference_face_ids") is not None:
            raise PatternReconstructionError(
                "v116_trusted_material_partition_invalid",
                "trusted closed partition cannot contain an open-tip reference",
            )
        shroud = _trusted_partition_mapping(
            partition.get("material_shroud"), "trusted material shroud"
        )
        shroud_face_ids = sorted(
            _trusted_nonempty_identifiers(
                shroud.get("source_face_ids"),
                "trusted shroud source_face_ids",
                "material",
            )
        )
        inner_ids = sorted(
            _trusted_nonempty_identifiers(
                shroud.get("inner_flowpath_face_ids"),
                "trusted inner shroud face ids",
                "material",
            )
        )
        outer_ids = sorted(
            _trusted_nonempty_identifiers(
                shroud.get("outer_material_face_ids"),
                "trusted outer shroud face ids",
                "material",
            )
        )
        if set(inner_ids) & set(outer_ids) or set(shroud_face_ids) != set(inner_ids) | set(
            outer_ids
        ):
            raise PatternReconstructionError(
                "v116_trusted_material_partition_invalid",
                "trusted shroud roles do not form an exact material partition",
            )
        shroud_attachments = _trusted_attachment_partition(
            shroud.get("blade_attachment_face_ids_by_instance"),
            instance_ids,
            "trusted shroud attachments",
        )
        trusted_thickness = _finite_thickness(
            shroud.get("finite_thickness"), shroud
        )
        normalized.update(
            {
                "open_tip_reference_face_ids": None,
                "material_shroud": {
                    "source_face_ids": shroud_face_ids,
                    "inner_flowpath_face_ids": inner_ids,
                    "outer_material_face_ids": outer_ids,
                    "blade_attachment_face_ids_by_instance": shroud_attachments,
                    "finite_thickness": trusted_thickness,
                },
            }
        )
        role_face_ids.update(shroud_face_ids)
        non_hub_material_face_ids.update(shroud_face_ids)
    periodic_face_ids = set(trusted_periodic["source_entity_ids"])
    attachment_face_ids = {
        face_id for face_ids in hub_attachments.values() for face_id in face_ids
    }
    hub_attachment_face_ids = set(attachment_face_ids)
    if mode == "closed":
        shroud_attachment_face_ids = {
            face_id
            for face_ids in normalized["material_shroud"][
                "blade_attachment_face_ids_by_instance"
            ].values()
            for face_id in face_ids
        }
        if hub_attachment_face_ids & shroud_attachment_face_ids:
            raise PatternReconstructionError(
                "v116_trusted_material_partition_invalid",
                "trusted hub and shroud attachment ownership must be disjoint",
            )
        attachment_face_ids.update(shroud_attachment_face_ids)
    all_role_ids = (
        role_face_ids | attachment_face_ids | construction_evidence_face_ids
    )
    if (
        role_face_ids & periodic_face_ids
        or set(hub_face_ids) & non_hub_material_face_ids
        or role_face_ids & attachment_face_ids
        or construction_evidence_face_ids & role_face_ids
        or construction_evidence_face_ids & attachment_face_ids
        or not all_role_ids.issubset(trusted_source["faces_by_id"])
    ):
        raise PatternReconstructionError(
            "v116_trusted_material_partition_invalid",
            "trusted support/material ownership is ambiguous or lacks source membership",
        )
    normalized["source_entity_ids"] = sorted(all_role_ids)
    normalized["partition_digest_sha256"] = _payload_digest(normalized)
    return normalized


def _trusted_attachment_partition(
    value: Any, expected_instance_ids: Sequence[str], name: str
) -> dict[str, list[str]]:
    mapping = _trusted_partition_mapping(value, name)
    if sorted(mapping) != sorted(expected_instance_ids):
        raise PatternReconstructionError(
            "v116_trusted_material_partition_invalid",
            f"{name} must cover every trusted periodic instance",
        )
    normalized = {
        instance_id: sorted(
            _trusted_nonempty_identifiers(
                mapping[instance_id], f"{name}.{instance_id}", "material"
            )
        )
        for instance_id in sorted(expected_instance_ids)
    }
    owned = [face_id for face_ids in normalized.values() for face_id in face_ids]
    if len(owned) != len(set(owned)):
        raise PatternReconstructionError(
            "v116_trusted_material_partition_invalid",
            f"{name} must have disjoint face ownership",
        )
    return normalized


def _trusted_partition_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        reason = (
            "v116_trusted_periodic_partition_invalid"
            if "periodic" in name or "population" in name or "instance" in name
            else "v116_trusted_material_partition_invalid"
        )
        raise PatternReconstructionError(reason, f"{name} must be a mapping")
    return value


def _validate_trusted_partition_source(
    partition: Mapping[str, Any],
    *,
    authority: str,
    trusted_source: Mapping[str, Any],
    name: str,
) -> None:
    reason = (
        "v116_trusted_periodic_partition_invalid"
        if authority == _TRUSTED_PERIODIC_AUTHORITY
        else "v116_trusted_material_partition_invalid"
    )
    if (
        partition.get("authority") != authority
        or partition.get("source_sha256") != trusted_source["source_sha256"]
        or partition.get("source_solid_shape_identity")
        != trusted_source["source_solid_shape_identity"]
    ):
        raise PatternReconstructionError(
            reason, f"{name} is not bound to the trusted source solid"
        )


def _trusted_identifier(value: Any, name: str, kind: str) -> str:
    reason = (
        "v116_trusted_periodic_partition_invalid"
        if kind == "periodic"
        else "v116_trusted_material_partition_invalid"
    )
    return _identifier_for_reason(value, name, reason)


def _trusted_nonnegative_int(value: Any, name: str, kind: str) -> int:
    reason = (
        "v116_trusted_periodic_partition_invalid"
        if kind == "periodic"
        else "v116_trusted_material_partition_invalid"
    )
    return _nonnegative_int_for_reason(value, name, reason)


def _trusted_nonempty_identifiers(value: Any, name: str, kind: str) -> list[str]:
    reason = (
        "v116_trusted_periodic_partition_invalid"
        if kind == "periodic"
        else "v116_trusted_material_partition_invalid"
    )
    if not _is_sequence(value) or not value:
        raise PatternReconstructionError(reason, f"{name} must be a non-empty sequence")
    result = [_identifier_for_reason(item, name, reason) for item in value]
    if len(result) != len(set(result)):
        raise PatternReconstructionError(reason, f"{name} must contain unique ids")
    return result


def _trusted_vector(value: Any, name: str) -> list[float]:
    if not _is_sequence(value) or len(value) != 3:
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid", f"{name} must have three coordinates"
        )
    return [
        _finite_for_reason(
            coordinate, name, "v116_trusted_source_manifest_invalid"
        )
        for coordinate in value
    ]


def _trusted_identifier_sequence(value: Any, name: str) -> list[str]:
    if not _is_sequence(value):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid", f"{name} must be a sequence"
        )
    result = [
        _identifier_for_reason(
            item, name, "v116_trusted_source_manifest_invalid"
        )
        for item in value
    ]
    if len(result) != len(set(result)):
        raise PatternReconstructionError(
            "v116_trusted_source_manifest_invalid", f"{name} contains duplicate ids"
        )
    return result


def _validate_periodic_provenance(
    periodic: Mapping[str, Any], trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    provenance = _mapping(periodic.get("provenance"), "periodic_population_evidence.provenance")
    source_sha256 = _sha256(provenance.get("source_sha256"), "periodic provenance source_sha256")
    source_solid = _identifier(
        provenance.get("source_solid_shape_identity"),
        "periodic provenance source_solid_shape_identity",
    )
    source_entity_ids = _identifiers(
        provenance.get("source_entity_ids"), "periodic provenance source_entity_ids"
    )
    declared_digest = _sha256(
        provenance.get("population_digest_sha256"),
        "periodic provenance population_digest_sha256",
    )
    if (
        provenance.get("authentication_status") != "PASS"
        or provenance.get("authority") != _PERIODIC_PROVENANCE_AUTHORITY
        or provenance.get("digest_basis") != _PERIODIC_DIGEST_BASIS
        or source_sha256 != trusted_source["source_sha256"]
        or source_solid != trusted_source["source_solid_shape_identity"]
        or not set(source_entity_ids).issubset(trusted_source["faces_by_id"])
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic population evidence is not bound to the trusted source topology",
        )
    return {
        "authentication_status": "PASS",
        "authority": _PERIODIC_PROVENANCE_AUTHORITY,
        "source_sha256": source_sha256,
        "source_solid_shape_identity": source_solid,
        "source_entity_ids": source_entity_ids,
        "population_digest_sha256": declared_digest,
        "digest_basis": _PERIODIC_DIGEST_BASIS,
        "trusted_source_manifest_digest_sha256": trusted_source[
            "manifest_digest_sha256"
        ],
    }


def _validate_populations(
    *,
    graph: Mapping[str, Any],
    periodic: Mapping[str, Any],
    blade_surfaces: dict[str, dict[int, dict[tuple[str, str], Mapping[str, Any]]]],
    expected_counts: dict[str, int],
    tolerance_mm: float,
    generated_tolerance_mm: float,
    angular_tolerance_deg: float,
    periodic_provenance: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
    trusted_periodic: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    if periodic.get("method") != _PERIODIC_METHOD:
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid",
            "periodic evidence was not emitted by the measured V1.1.6 population method",
        )
    for blade_class, count_key in (
        ("main", "main_blade_count"),
        ("splitter", "splitter_blade_count"),
    ):
        measured = _nonnegative_int(periodic.get(count_key), count_key)
        generated_indices = sorted(blade_surfaces[blade_class])
        expected_indices = list(range(expected_counts[blade_class]))
        if measured != expected_counts[blade_class] or generated_indices != expected_indices:
            raise PatternReconstructionError(
                "v116_pattern_count_mismatch",
                f"{blade_class} measured/generated population does not match V1.1.2",
                details={
                    "blade_class": blade_class,
                    "measured_count": measured,
                    "expected_count": expected_counts[blade_class],
                    "generated_pair_indices": generated_indices,
                },
            )

    closure = _mapping(periodic.get("closure_diagnostics"), "closure_diagnostics")
    if closure.get("all_populations_closed") is not True:
        raise PatternReconstructionError(
            "v116_pattern_closure_invalid", "measured periodic populations are not closed"
        )

    raw_populations = periodic.get("populations")
    if not _is_sequence(raw_populations):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", "periodic populations must be a sequence"
        )
    expected_classes = ["main"] + (["splitter"] if expected_counts["splitter"] else [])
    by_class: dict[str, Mapping[str, Any]] = {}
    for raw in raw_populations:
        population = _mapping(raw, "population")
        classification = population.get("classification")
        if classification not in expected_classes or classification in by_class:
            raise PatternReconstructionError(
                "v116_pattern_evidence_invalid",
                "periodic evidence has missing, duplicate, or unexpected populations",
            )
        by_class[classification] = population
        if periodic.get(classification) != population:
            raise PatternReconstructionError(
                "v116_pattern_evidence_invalid",
                f"top-level {classification} population is inconsistent with populations",
            )
    if sorted(by_class) != sorted(expected_classes) or (
        not expected_counts["splitter"] and periodic.get("splitter") is not None
    ):
        raise PatternReconstructionError(
            "v116_pattern_count_mismatch", "periodic population classes do not match V1.1.2"
        )

    records: list[dict[str, Any]] = []
    bindings: dict[str, dict[str, Any]] = {}
    instance_ids: list[str] = []
    normalized_for_collision: list[dict[str, Any]] = []
    normalized_for_digest: list[dict[str, Any]] = []
    for blade_class in expected_classes:
        (
            record,
            population_bindings,
            ids,
            collision_population,
            digest_population,
        ) = _validate_population(
            blade_class=blade_class,
            population=by_class[blade_class],
            generated=blade_surfaces[blade_class],
            expected_count=expected_counts[blade_class],
            tolerance_mm=tolerance_mm,
            generated_tolerance_mm=generated_tolerance_mm,
            angular_tolerance_deg=angular_tolerance_deg,
            periodic_provenance=periodic_provenance,
            trusted_source=trusted_source,
        )
        records.append(record)
        bindings.update(population_bindings)
        instance_ids.extend(ids)
        normalized_for_collision.append(collision_population)
        normalized_for_digest.append(digest_population)

    all_instances = [
        instance
        for population in by_class.values()
        for instance in population["instances"]
    ]
    source_id_owners = [
        face_id for instance in all_instances for face_id in instance["source_face_ids"]
    ]
    component_id_owners = [
        instance["source_component_id"] for instance in all_instances
    ]
    if (
        len(source_id_owners) != len(set(source_id_owners))
        or len(component_id_owners) != len(set(component_id_owners))
        or len(instance_ids) != len(set(instance_ids))
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic instances require disjoint source face, component, and instance ownership",
        )
    observed_source_ids = sorted(source_id_owners)
    if observed_source_ids != sorted(periodic_provenance["source_entity_ids"]):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic source entity inventory does not equal component membership",
        )
    observed_partition = {
        "method": _PERIODIC_METHOD,
        "main_blade_count": expected_counts["main"],
        "splitter_blade_count": expected_counts["splitter"],
        "populations": [
            {
                "population_id": record["population_id"],
                "count": record["count"],
                "representative_source_component_id": record["representative"][
                    "source_component_id"
                ],
                "instances": [
                    {
                        "instance_id": instance["instance_id"],
                        "source_component_id": instance["source_component_id"],
                        "source_face_ids": sorted(instance["source_face_ids"]),
                        "lattice_index": instance["lattice_index"],
                    }
                    for instance in record["instances"]
                ],
            }
            for record in records
        ],
    }
    trusted_partition = {
        key: copy.deepcopy(trusted_periodic[key])
        for key in (
            "method",
            "main_blade_count",
            "splitter_blade_count",
            "populations",
        )
    }
    if observed_partition != trusted_partition:
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic evidence does not match the independent canonical partition",
            details={"observed": observed_partition, "trusted": trusted_partition},
        )
    expected_population_digest = _payload_digest(
        {
            "digest_basis": _PERIODIC_DIGEST_BASIS,
            "trusted_source_manifest_digest_sha256": trusted_source[
                "manifest_digest_sha256"
            ],
            "method": _PERIODIC_METHOD,
            "populations": normalized_for_digest,
        }
    )
    if periodic_provenance["population_digest_sha256"] != expected_population_digest:
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic population digest does not match trusted source-derived components",
        )

    _validate_relative_phase(graph, by_class, angular_tolerance_deg)
    recomputed_collision = _measure_graph_collision_diagnostics(
        normalized_for_collision,
        collision_tolerance_deg=_positive_finite(
            _mapping(periodic.get("collision_diagnostics"), "collision_diagnostics").get(
                "tolerance_deg"
            ),
            "collision_diagnostics.tolerance_deg",
        ),
    )
    declared_collision = _mapping(
        periodic.get(
            "source_collision_diagnostics",
            periodic.get("collision_diagnostics"),
        ),
        "source_collision_diagnostics",
    )
    declared_state = _declared_source_collision_state(declared_collision)
    if declared_state in {"FAIL", "INVALID"} or not bool(
        recomputed_collision["collision_free"]
    ):
        raise PatternReconstructionError(
            "v116_pattern_collision",
            "measured blade instances contain a cyclic angular-envelope collision",
            details={"recomputed": recomputed_collision},
        )
    return records, bindings, instance_ids


def _declared_source_collision_state(diagnostics: Mapping[str, Any]) -> str:
    count = _nonnegative_int(
        diagnostics.get("collision_count"), "source collision count"
    )
    collision_free = diagnostics.get("collision_free")
    if collision_free is False or count > 0:
        return "FAIL"
    if (
        collision_free is True
        and count == 0
        and diagnostics.get("collision_status") == "PASS"
        and diagnostics.get("source_topology_separated") is True
        and diagnostics.get("exact_brep_collision_checked") is True
        and diagnostics.get("exact_brep_collision_free") is True
    ):
        return "PASS"
    if (
        collision_free is None
        and count == 0
        and diagnostics.get("collision_status") == "UNKNOWN"
        and diagnostics.get("source_topology_separated") is True
        and diagnostics.get("exact_brep_collision_checked") is False
        and diagnostics.get("exact_brep_collision_free") is None
    ):
        return "UNKNOWN"
    return "INVALID"


def _validate_population(
    *,
    blade_class: str,
    population: Mapping[str, Any],
    generated: dict[int, dict[tuple[str, str], Mapping[str, Any]]],
    expected_count: int,
    tolerance_mm: float,
    generated_tolerance_mm: float,
    angular_tolerance_deg: float,
    periodic_provenance: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    list[str],
    dict[str, Any],
    dict[str, Any],
]:
    if population.get("population_id") != blade_class:
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{blade_class} population_id is inconsistent"
        )
    if _nonnegative_int(population.get("count"), f"{blade_class}.count") != expected_count:
        raise PatternReconstructionError(
            "v116_pattern_count_mismatch", f"{blade_class} population count mismatch"
        )
    pitch = _finite(population.get("pitch_deg"), f"{blade_class}.pitch_deg")
    nominal_pitch = _finite(
        population.get("nominal_pitch_deg"), f"{blade_class}.nominal_pitch_deg"
    )
    expected_pitch = 360.0 / expected_count
    if (
        _angle_distance(pitch, expected_pitch) > angular_tolerance_deg
        or _angle_distance(nominal_pitch, expected_pitch) > angular_tolerance_deg
    ):
        raise PatternReconstructionError(
            "v116_pattern_phase_invalid", f"{blade_class} measured pitch is inconsistent"
        )
    phase = _normalized_angle(
        _finite(population.get("phase_deg"), f"{blade_class}.phase_deg")
    )
    closure = _mapping(population.get("closure"), f"{blade_class}.closure")
    if closure.get("within_tolerance") is not True:
        raise PatternReconstructionError(
            "v116_pattern_closure_invalid", f"{blade_class} lattice does not close"
        )
    for key in ("maximum_gap_residual_deg", "closure_residual_deg"):
        if abs(_finite(closure.get(key), f"{blade_class}.closure.{key}")) > angular_tolerance_deg:
            raise PatternReconstructionError(
                "v116_pattern_closure_invalid",
                f"{blade_class} closure residual exceeds measured angular tolerance",
            )

    representative = _mapping(
        population.get("representative"), f"{blade_class}.representative"
    )
    representative_component_id = _identifier(
        representative.get("source_component_id"),
        f"{blade_class}.representative.source_component_id",
    )
    representative_face_ids = _identifiers(
        representative.get("source_face_ids"),
        f"{blade_class}.representative.source_face_ids",
    )
    representative_component_evidence = _mapping(
        representative.get("source_component_evidence"),
        f"{blade_class}.representative.source_component_evidence",
    )
    representative_index = _lattice_index(
        representative.get("lattice_index"), expected_count, blade_class
    )
    raw_instances = population.get("instances")
    if not _is_sequence(raw_instances) or len(raw_instances) != expected_count:
        raise PatternReconstructionError(
            "v116_pattern_count_mismatch", f"{blade_class} instance count mismatch"
        )
    instances_by_index: dict[int, Mapping[str, Any]] = {}
    instance_ids: list[str] = []
    for raw_instance in raw_instances:
        instance = _mapping(raw_instance, f"{blade_class}.instance")
        index = _lattice_index(instance.get("lattice_index"), expected_count, blade_class)
        if index in instances_by_index:
            raise PatternReconstructionError(
                "v116_pattern_instance_contract_invalid",
                f"{blade_class} repeats lattice index {index}",
            )
        if instance.get("population_id") != blade_class:
            raise PatternReconstructionError(
                "v116_pattern_instance_contract_invalid",
                f"{blade_class}[{index}] has an inconsistent population_id",
            )
        instance_id = _identifier(instance.get("instance_id"), f"{blade_class}.instance_id")
        if instance_id in instance_ids:
            raise PatternReconstructionError(
                "v116_pattern_instance_contract_invalid", "periodic instance ids must be unique"
            )
        instance_ids.append(instance_id)
        instances_by_index[index] = instance
    if sorted(instances_by_index) != list(range(expected_count)):
        raise PatternReconstructionError(
            "v116_pattern_instance_contract_invalid",
            f"{blade_class} does not occupy every cyclic lattice site",
        )

    representative_instance = instances_by_index[representative_index]
    if (
        representative_instance.get("source_component_id") != representative_component_id
        or list(representative_instance.get("source_face_ids", ())) != representative_face_ids
        or representative_instance.get("source_component_evidence")
        != representative_component_evidence
    ):
        raise PatternReconstructionError(
            "v116_pattern_instance_contract_invalid",
            f"{blade_class} representative source ids do not identify its lattice instance",
        )
    representative_families = generated[representative_index]
    family_signature = sorted(representative_families)
    bindings: dict[str, dict[str, Any]] = {}
    instance_records: list[dict[str, Any]] = []
    collision_instances: list[dict[str, Any]] = []
    for index in range(expected_count):
        instance = instances_by_index[index]
        measured_angle = _normalized_angle(
            _finite(instance.get("measured_angle_deg"), f"{blade_class}[{index}].measured_angle_deg")
        )
        expected_angle = _normalized_angle(phase + index * expected_pitch)
        if _angle_distance(measured_angle, expected_angle) > angular_tolerance_deg:
            raise PatternReconstructionError(
                "v116_pattern_phase_invalid",
                f"{blade_class}[{index}] does not match measured phase and pitch",
            )
        if abs(_finite(instance.get("pitch_residual_deg"), "pitch_residual_deg")) > angular_tolerance_deg:
            raise PatternReconstructionError(
                "v116_pattern_phase_invalid", f"{blade_class}[{index}] pitch residual exceeds tolerance"
            )
        transform = _rigid_z_rotation(
            instance.get("transform_from_representative"),
            f"{blade_class}[{index}].transform_from_representative",
        )
        transform_angle = _normalized_angle(math.degrees(math.atan2(transform[1][0], transform[0][0])))
        representative_angle = _normalized_angle(
            _finite(
                representative_instance.get("measured_angle_deg"),
                f"{blade_class}.representative.measured_angle_deg",
            )
        )
        expected_rotation = _normalized_angle(measured_angle - representative_angle)
        declared_rotation = _normalized_angle(
            _finite(instance.get("rotation_from_representative_deg"), "rotation_from_representative_deg")
        )
        if (
            _angle_distance(transform_angle, expected_rotation) > angular_tolerance_deg
            or _angle_distance(declared_rotation, expected_rotation) > angular_tolerance_deg
        ):
            raise PatternReconstructionError(
                "v116_pattern_transform_invalid",
                f"{blade_class}[{index}] transform does not encode its measured cyclic rotation",
            )
        source_component_id = _identifier(
            instance.get("source_component_id"), f"{blade_class}[{index}].source_component_id"
        )
        source_face_ids = _identifiers(
            instance.get("source_face_ids"), f"{blade_class}[{index}].source_face_ids"
        )
        component_provenance = _validate_component_provenance(
            instance,
            blade_class=blade_class,
            lattice_index=index,
            expected_count=expected_count,
            source_component_id=source_component_id,
            source_face_ids=source_face_ids,
            periodic_provenance=periodic_provenance,
            trusted_source=trusted_source,
        )
        residual = _finite(
            instance.get("residual_to_representative_mm"),
            f"{blade_class}[{index}].residual_to_representative_mm",
        )
        if residual < 0.0 or residual > tolerance_mm:
            raise PatternReconstructionError(
                "v116_pattern_surface_mismatch",
                f"{blade_class}[{index}] measured representative residual exceeds tolerance",
            )
        target_families = generated[index]
        if sorted(target_families) != family_signature:
            raise PatternReconstructionError(
                "v116_pattern_surface_family_mismatch",
                f"{blade_class}[{index}] does not match the representative surface family",
            )
        generated_envelope = _surface_family_envelope(target_families)
        _validate_supplied_envelope(
            instance,
            generated_envelope,
            tolerance_mm=generated_tolerance_mm,
            angular_tolerance_deg=angular_tolerance_deg,
            instance_name=f"{blade_class}[{index}]",
        )
        collision_instances.append(
            {
                "population_id": blade_class,
                "source_component_id": source_component_id,
                "measured_angle_deg": generated_envelope["center_angle_deg"],
                "angular_span_deg": generated_envelope["span_deg"],
                "radial_support_range_mm": generated_envelope["radial_range_mm"],
                "axial_support_range_mm": generated_envelope["axial_range_mm"],
                "collision_samples": generated_envelope["collision_samples"],
                "collision_surface_grids": generated_envelope[
                    "collision_surface_grids"
                ],
            }
        )
        maximum_residual = 0.0
        for family_key in family_signature:
            representative_surface = representative_families[family_key]
            target_surface = target_families[family_key]
            family_residual = _transformed_surface_residual(
                representative_surface, target_surface, transform
            )
            maximum_residual = max(maximum_residual, family_residual)
            if family_residual > generated_tolerance_mm:
                raise PatternReconstructionError(
                    "v116_pattern_surface_mismatch",
                    f"{blade_class}[{index}] surface family is not a measured rigid cyclic transform",
                    details={
                        "surface_id": target_surface["id"],
                        "residual_mm": family_residual,
                        "tolerance_mm": generated_tolerance_mm,
                    },
                )
            bindings[target_surface["id"]] = {
                "population_id": blade_class,
                "source_representative_component_id": representative_component_id,
                "source_representative_face_ids": copy.deepcopy(representative_face_ids),
                "source_instance_component_id": source_component_id,
                "source_instance_face_ids": copy.deepcopy(source_face_ids),
                "lattice_index": index,
                "phase_deg": measured_angle,
                "transform_from_representative": copy.deepcopy(transform),
                "measured_tolerance_mm": tolerance_mm,
                "generated_rigid_transform_tolerance_mm": generated_tolerance_mm,
                "generated_surface_residual_mm": family_residual,
            }
        instance_records.append(
            {
                "instance_id": instance["instance_id"],
                "source_component_id": source_component_id,
                "source_face_ids": source_face_ids,
                "lattice_index": index,
                "phase_deg": measured_angle,
                "transform_from_representative": transform,
                "maximum_generated_surface_residual_mm": maximum_residual,
                "generated_collision_envelope": {
                    key: value
                    for key, value in generated_envelope.items()
                    if key
                    not in {
                        "collision_cells",
                        "collision_samples",
                        "collision_surface_grids",
                    }
                },
                "component_digest_sha256": component_provenance[
                    "component_digest_sha256"
                ],
            }
        )
    return (
        {
            "population_id": blade_class,
            "count": expected_count,
            "pitch_deg": pitch,
            "phase_deg": phase,
            "representative": {
                "source_component_id": representative_component_id,
                "source_face_ids": representative_face_ids,
                "lattice_index": representative_index,
                "surface_family": [list(key) for key in family_signature],
            },
            "instances": instance_records,
        },
        bindings,
        instance_ids,
        {"population_id": blade_class, "instances": collision_instances},
        {
            "population_id": blade_class,
            "count": expected_count,
            "pitch_deg": pitch,
            "phase_deg": phase,
            "representative": {
                "source_component_id": representative_component_id,
                "source_face_ids": sorted(representative_face_ids),
                "lattice_index": representative_index,
            },
            "instances": [
                {
                    "instance_id": instance["instance_id"],
                    "source_component_id": instance["source_component_id"],
                    "source_face_ids": sorted(instance["source_face_ids"]),
                    "lattice_index": instance["lattice_index"],
                    "phase_deg": instance["phase_deg"],
                    "transform_from_representative": instance[
                        "transform_from_representative"
                    ],
                    "component_digest_sha256": instance[
                        "component_digest_sha256"
                    ],
                }
                for instance in instance_records
            ],
        },
    )


def _validate_component_provenance(
    instance: Mapping[str, Any],
    *,
    blade_class: str,
    lattice_index: int,
    expected_count: int,
    source_component_id: str,
    source_face_ids: list[str],
    periodic_provenance: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
) -> dict[str, Any]:
    name = f"{blade_class}[{lattice_index}].source_component_evidence"
    evidence = _mapping(instance.get("source_component_evidence"), name)
    evidence_source_ids = _identifiers(
        evidence.get("source_entity_ids"), f"{name}.source_entity_ids"
    )
    completeness = _mapping(evidence.get("component_completeness"), f"{name}.component_completeness")
    confidence = _mapping(evidence.get("confidence"), f"{name}.confidence")
    units = _mapping(evidence.get("units"), f"{name}.units")
    tolerance = _mapping(evidence.get("tolerance"), f"{name}.tolerance")
    residual = _mapping(evidence.get("residual"), f"{name}.residual")
    provenance = _mapping(evidence.get("provenance"), f"{name}.provenance")
    signature_hashes = _identifiers(
        provenance.get("signature_hashes"), f"{name}.provenance.signature_hashes"
    )
    if (
        evidence.get("source_component_id") != source_component_id
        or sorted(evidence_source_ids) != sorted(source_face_ids)
        or completeness.get("status") != "COMPLETE"
        or confidence.get("level") != "deterministic_topology_component"
        or confidence.get("status") != "ACCEPTED"
        or _finite(confidence.get("score"), f"{name}.confidence.score") != 1.0
        or evidence.get("coordinate_frame") != "canonical_cylindrical_r_theta_z"
        or units.get("linear") != "mm"
        or units.get("angular") != "deg"
        or evidence.get("authenticated_population_count") != expected_count
        or not _is_sequence(evidence.get("seed_rotational_group_ids"))
        or not evidence.get("seed_rotational_group_ids")
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0.0
            for value in tolerance.values()
        )
        or not tolerance
        or not residual
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in residual.values()
        )
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            f"{name} does not satisfy the authenticated V1.1.6 component contract",
        )
    component_digest = _sha256(
        provenance.get("component_digest_sha256"),
        f"{name}.provenance.component_digest_sha256",
    )
    digest_basis = _trusted_component_digest_basis(
        trusted_source,
        source_component_id=source_component_id,
        source_face_ids=source_face_ids,
    )
    expected_signatures = sorted(
        trusted_source["face_signature_sha256_by_id"][face_id]
        for face_id in source_face_ids
    )
    if (
        provenance.get("authority") != _PERIODIC_PROVENANCE_AUTHORITY
        or provenance.get("digest_basis") != _COMPONENT_DIGEST_BASIS
        or provenance.get("source_solid_shape_identity")
        != periodic_provenance["source_solid_shape_identity"]
        or provenance.get("source_sha256") != periodic_provenance["source_sha256"]
        or sorted(provenance.get("source_entity_ids", ()))
        != sorted(source_face_ids)
        or sorted(signature_hashes) != expected_signatures
        or component_digest != _payload_digest(digest_basis)
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            f"{name} is not bound to the authenticated source inventory",
        )
    return {**digest_basis, "component_digest_sha256": component_digest}


def _trusted_component_digest_basis(
    trusted_source: Mapping[str, Any],
    *,
    source_component_id: str,
    source_face_ids: Sequence[str],
) -> dict[str, Any]:
    """Build the canonical component payload solely from trusted face topology."""

    face_ids = sorted(source_face_ids)
    if not face_ids or not set(face_ids).issubset(trusted_source["faces_by_id"]):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic component contains faces absent from trusted source topology",
        )
    membership = set(face_ids)
    return {
        "digest_basis": _COMPONENT_DIGEST_BASIS,
        "trusted_source_manifest_digest_sha256": trusted_source[
            "manifest_digest_sha256"
        ],
        "source_sha256": trusted_source["source_sha256"],
        "source_solid_shape_identity": trusted_source[
            "source_solid_shape_identity"
        ],
        "source_component_id": source_component_id,
        "source_entity_ids": face_ids,
        "face_signature_sha256_by_id": {
            face_id: trusted_source["face_signature_sha256_by_id"][face_id]
            for face_id in face_ids
        },
        "component_adjacency": {
            face_id: [
                neighbor
                for neighbor in trusted_source["adjacency"][face_id]
                if neighbor in membership
            ]
            for face_id in face_ids
        },
    }


def _surface_family_envelope(
    families: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    include_collision_geometry: bool = True,
) -> dict[str, Any]:
    collision_surfaces = [
        surface
        for surface in families.values()
        if surface.get("material") is not False
        if surface.get("role")
        not in {"root_to_hub_attachment", "closed_shroud_attachment"}
    ]
    points = [
        [float(coordinate) for coordinate in point]
        for surface in families.values()
        for row in surface["uv_grid"]
        for point in row
    ]
    radii = [math.hypot(point[0], point[1]) for point in points]
    angles = [
        math.degrees(math.atan2(point[1], point[0])) % 360.0
        for point, radius in zip(points, radii)
        if radius > 1.0e-9
    ]
    if not angles:
        raise PatternReconstructionError(
            "v116_pattern_graph_invalid",
            "blade surface family has no off-axis points for a cyclic envelope",
        )
    angles.sort()
    gaps = [
        (
            angles[index + 1] - angle
            if index + 1 < len(angles)
            else angles[0] + 360.0 - angle,
            index,
        )
        for index, angle in enumerate(angles)
    ]
    largest_gap, gap_index = max(gaps, key=lambda item: (item[0], -item[1]))
    start = angles[(gap_index + 1) % len(angles)]
    span = max(0.0, 360.0 - largest_gap)
    center = (start + 0.5 * span) % 360.0
    collision_samples = _collision_samples(collision_surfaces)
    collision_radii = [sample["radius_mm"] for sample in collision_samples]
    collision_axial = [sample["axial_mm"] for sample in collision_samples]
    collision_cells = _collision_cells_from_samples(
        collision_samples,
        radial_range_mm=(min(collision_radii), max(collision_radii)),
        axial_range_mm=(min(collision_axial), max(collision_axial)),
    )
    envelope = {
        "method": "authoritative_v112_blade_surface_uv_grid_circular_envelope",
        "center_angle_deg": center,
        "start_angle_deg": start,
        "end_angle_deg": (start + span) % 360.0,
        "span_deg": max(cell["span_deg"] for cell in collision_cells),
        "global_wrap_span_deg": span,
        "wraps_zero": bool(span < 360.0 and start > (start + span) % 360.0),
        "radial_range_mm": [min(radii), max(radii)],
        "axial_range_mm": [
            min(point[2] for point in points),
            max(point[2] for point in points),
        ],
        "point_count": len(points),
        "collision_cells": collision_cells,
        "collision_samples": None,
        "collision_surface_grids": None,
    }
    if include_collision_geometry:
        envelope["collision_samples"] = collision_samples
        envelope["collision_surface_grids"] = [
            surface["uv_grid"] for surface in collision_surfaces
        ]
    else:
        envelope.pop("collision_samples")
        envelope.pop("collision_surface_grids")
    return envelope


def _collision_cells(surfaces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    samples = _collision_samples(surfaces)
    radii = [sample["radius_mm"] for sample in samples]
    axial = [sample["axial_mm"] for sample in samples]
    return _collision_cells_from_samples(
        samples,
        radial_range_mm=(min(radii), max(radii)),
        axial_range_mm=(min(axial), max(axial)),
    )


def _collision_samples(
    surfaces: Sequence[Mapping[str, Any]],
) -> list[dict[str, float]]:
    points = [
        [float(coordinate) for coordinate in point]
        for surface in surfaces
        for row in surface["uv_grid"]
        for point in row
    ]
    return [
        {
            "radius_mm": math.hypot(point[0], point[1]),
            "axial_mm": point[2],
            "angle_deg": math.degrees(math.atan2(point[1], point[0])) % 360.0,
        }
        for point in points
    ]


def _collision_cells_from_samples(
    samples: Sequence[Mapping[str, float]],
    *,
    radial_range_mm: tuple[float, float],
    axial_range_mm: tuple[float, float],
) -> list[dict[str, Any]]:
    r_min, r_max = radial_range_mm
    z_min, z_max = axial_range_mm
    radial_count = _COLLISION_RADIAL_CELL_COUNT
    axial_count = _COLLISION_AXIAL_CELL_COUNT
    grouped = _collision_sample_groups(
        samples,
        radial_range_mm=radial_range_mm,
        axial_range_mm=axial_range_mm,
        radial_count=radial_count,
        axial_count=axial_count,
    )
    radial_step = (r_max - r_min) / radial_count
    axial_step = (z_max - z_min) / axial_count
    cells = []
    for cell_index, cell_samples in sorted(grouped.items()):
        cell_angles = [float(sample["angle_deg"]) for sample in cell_samples]
        center, span = _circular_angle_envelope(cell_angles)
        cells.append(
            {
                "cell_index": list(cell_index),
                "center_angle_deg": center,
                "span_deg": span,
                "radial_interval_mm": [
                    r_min + cell_index[0] * radial_step,
                    r_max
                    if cell_index[0] == radial_count - 1
                    else r_min + (cell_index[0] + 1) * radial_step,
                ],
                "axial_interval_mm": [
                    z_min + cell_index[1] * axial_step,
                    z_max
                    if cell_index[1] == axial_count - 1
                    else z_min + (cell_index[1] + 1) * axial_step,
                ],
            }
        )
    return cells


def _collision_sample_groups(
    samples: Sequence[Mapping[str, float]],
    *,
    radial_range_mm: tuple[float, float],
    axial_range_mm: tuple[float, float],
    radial_count: int,
    axial_count: int,
) -> dict[tuple[int, int], list[Mapping[str, float]]]:
    r_min, r_max = radial_range_mm
    z_min, z_max = axial_range_mm
    grouped: dict[tuple[int, int], list[Mapping[str, float]]] = defaultdict(list)
    for sample in samples:
        radial_index = _collision_axis_cell_index(
            float(sample["radius_mm"]), r_min, r_max, radial_count
        )
        axial_index = _collision_axis_cell_index(
            float(sample["axial_mm"]), z_min, z_max, axial_count
        )
        grouped[(radial_index, axial_index)].append(sample)
    return grouped


def _collision_axis_cell_index(
    value: float, lower: float, upper: float, count: int
) -> int:
    normalized = (value - lower) / max(upper - lower, 1.0e-12)
    return min(count - 1, max(0, int(normalized * count)))


def _collision_cell_interval(
    index: int, lower: float, upper: float, count: int
) -> tuple[float, float]:
    step = (upper - lower) / count
    return (
        lower + index * step,
        upper if index == count - 1 else lower + (index + 1) * step,
    )


def _cell_angular_clearance(
    first_samples: Sequence[Mapping[str, float]],
    second_samples: Sequence[Mapping[str, float]],
) -> float:
    first_center, first_span = _circular_angle_envelope(
        [float(sample["angle_deg"]) for sample in first_samples]
    )
    second_center, second_span = _circular_angle_envelope(
        [float(sample["angle_deg"]) for sample in second_samples]
    )
    return _angle_distance(first_center, second_center) - 0.5 * (
        first_span + second_span
    )


def _refined_collision_cell(
    first_samples: Sequence[Mapping[str, float]],
    second_samples: Sequence[Mapping[str, float]],
    *,
    coarse_cell_index: tuple[int, int],
    radial_range_mm: tuple[float, float],
    axial_range_mm: tuple[float, float],
    collision_tolerance_deg: float,
) -> dict[str, Any] | None:
    radial_interval = _collision_cell_interval(
        coarse_cell_index[0],
        radial_range_mm[0],
        radial_range_mm[1],
        _COLLISION_RADIAL_CELL_COUNT,
    )
    axial_interval = _collision_cell_interval(
        coarse_cell_index[1],
        axial_range_mm[0],
        axial_range_mm[1],
        _COLLISION_AXIAL_CELL_COUNT,
    )
    first_groups = _collision_sample_groups(
        first_samples,
        radial_range_mm=radial_interval,
        axial_range_mm=axial_interval,
        radial_count=_COLLISION_REFINEMENT_DIVISIONS,
        axial_count=_COLLISION_REFINEMENT_DIVISIONS,
    )
    second_groups = _collision_sample_groups(
        second_samples,
        radial_range_mm=radial_interval,
        axial_range_mm=axial_interval,
        radial_count=_COLLISION_REFINEMENT_DIVISIONS,
        axial_count=_COLLISION_REFINEMENT_DIVISIONS,
    )
    best: dict[str, Any] | None = None
    for refined_index in first_groups.keys() & second_groups.keys():
        clearance = _cell_angular_clearance(
            first_groups[refined_index], second_groups[refined_index]
        )
        if clearance <= collision_tolerance_deg and (
            best is None or clearance < best["angular_clearance_deg"]
        ):
            best = {
                "refined_cell_index": list(refined_index),
                "angular_clearance_deg": clearance,
            }
    return best


def _surface_grid_triangles(
    grids: Sequence[Sequence[Sequence[Sequence[float]]]],
) -> list[tuple[tuple[float, float, float], ...]]:
    triangles: list[tuple[tuple[float, float, float], ...]] = []
    for grid in grids:
        if len(grid) < 2:
            continue
        column_count = min(len(row) for row in grid)
        if column_count < 2:
            continue
        for row_index in range(len(grid) - 1):
            for column_index in range(column_count - 1):
                first = _point3(grid[row_index][column_index])
                second = _point3(grid[row_index + 1][column_index])
                third = _point3(grid[row_index + 1][column_index + 1])
                fourth = _point3(grid[row_index][column_index + 1])
                for triangle in ((first, second, third), (first, third, fourth)):
                    if _vector_length_squared(
                        _vector_cross(
                            _vector_subtract(triangle[1], triangle[0]),
                            _vector_subtract(triangle[2], triangle[0]),
                        )
                    ) > 1.0e-20:
                        triangles.append(triangle)
    return triangles


def _point3(value: Sequence[float]) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _vector_subtract(
    first: Sequence[float], second: Sequence[float]
) -> tuple[float, float, float]:
    return (
        float(first[0]) - float(second[0]),
        float(first[1]) - float(second[1]),
        float(first[2]) - float(second[2]),
    )


def _vector_cross(
    first: Sequence[float], second: Sequence[float]
) -> tuple[float, float, float]:
    return (
        float(first[1]) * float(second[2])
        - float(first[2]) * float(second[1]),
        float(first[2]) * float(second[0])
        - float(first[0]) * float(second[2]),
        float(first[0]) * float(second[1])
        - float(first[1]) * float(second[0]),
    )


def _vector_dot(first: Sequence[float], second: Sequence[float]) -> float:
    return sum(float(left) * float(right) for left, right in zip(first, second))


def _vector_length_squared(value: Sequence[float]) -> float:
    return _vector_dot(value, value)


def _triangle_aabb(
    triangle: Sequence[Sequence[float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (
        tuple(min(float(point[axis]) for point in triangle) for axis in range(3)),
        tuple(max(float(point[axis]) for point in triangle) for axis in range(3)),
    )


def _aabbs_overlap(
    first: tuple[Sequence[float], Sequence[float]],
    second: tuple[Sequence[float], Sequence[float]],
    *,
    tolerance_mm: float,
) -> bool:
    return all(
        first[0][axis] <= second[1][axis] + tolerance_mm
        and second[0][axis] <= first[1][axis] + tolerance_mm
        for axis in range(3)
    )


def _triangle_hash_cells(
    bounds: tuple[Sequence[float], Sequence[float]],
) -> list[tuple[int, int, int]]:
    lower = [
        math.floor(
            (float(bounds[0][axis]) - _COLLISION_TRIANGLE_TOLERANCE_MM)
            / _COLLISION_TRIANGLE_HASH_CELL_MM
        )
        for axis in range(3)
    ]
    upper = [
        math.floor(
            (float(bounds[1][axis]) + _COLLISION_TRIANGLE_TOLERANCE_MM)
            / _COLLISION_TRIANGLE_HASH_CELL_MM
        )
        for axis in range(3)
    ]
    return [
        (x_index, y_index, z_index)
        for x_index in range(lower[0], upper[0] + 1)
        for y_index in range(lower[1], upper[1] + 1)
        for z_index in range(lower[2], upper[2] + 1)
    ]


def _triangles_intersect(
    first: Sequence[Sequence[float]],
    second: Sequence[Sequence[float]],
    *,
    tolerance_mm: float,
) -> bool:
    first_edges = [
        _vector_subtract(first[(index + 1) % 3], first[index])
        for index in range(3)
    ]
    second_edges = [
        _vector_subtract(second[(index + 1) % 3], second[index])
        for index in range(3)
    ]
    first_normal = _vector_cross(first_edges[0], first_edges[1])
    second_normal = _vector_cross(second_edges[0], second_edges[1])
    axes = [first_normal, second_normal]
    axes.extend(
        _vector_cross(first_edge, second_edge)
        for first_edge in first_edges
        for second_edge in second_edges
    )
    axes.extend(_vector_cross(first_normal, edge) for edge in first_edges)
    axes.extend(_vector_cross(second_normal, edge) for edge in second_edges)
    for axis in axes:
        axis_length_squared = _vector_length_squared(axis)
        if axis_length_squared <= 1.0e-24:
            continue
        first_projection = [_vector_dot(point, axis) for point in first]
        second_projection = [_vector_dot(point, axis) for point in second]
        margin = tolerance_mm * math.sqrt(axis_length_squared)
        if (
            max(first_projection) < min(second_projection) - margin
            or max(second_projection) < min(first_projection) - margin
        ):
            return False
    return True


def _triangle_mesh_intersection(
    first_triangles: Sequence[tuple[tuple[float, float, float], ...]],
    second_triangles: Sequence[tuple[tuple[float, float, float], ...]],
) -> tuple[dict[str, int] | None, int]:
    second_bounds = [_triangle_aabb(triangle) for triangle in second_triangles]
    second_hash: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for triangle_index, bounds in enumerate(second_bounds):
        for cell in _triangle_hash_cells(bounds):
            second_hash[cell].append(triangle_index)

    triangle_test_count = 0
    tested_pairs: set[tuple[int, int]] = set()
    for first_index, first_triangle in enumerate(first_triangles):
        first_bounds = _triangle_aabb(first_triangle)
        candidate_indexes = {
            second_index
            for cell in _triangle_hash_cells(first_bounds)
            for second_index in second_hash.get(cell, ())
        }
        for second_index in candidate_indexes:
            pair = (first_index, second_index)
            if pair in tested_pairs:
                continue
            tested_pairs.add(pair)
            if not _aabbs_overlap(
                first_bounds,
                second_bounds[second_index],
                tolerance_mm=_COLLISION_TRIANGLE_TOLERANCE_MM,
            ):
                continue
            triangle_test_count += 1
            if _triangles_intersect(
                first_triangle,
                second_triangles[second_index],
                tolerance_mm=_COLLISION_TRIANGLE_TOLERANCE_MM,
            ):
                return (
                    {
                        "first_triangle_index": first_index,
                        "second_triangle_index": second_index,
                    },
                    triangle_test_count,
                )
    return None, triangle_test_count


def _circular_angle_envelope(angles: Sequence[float]) -> tuple[float, float]:
    ordered = sorted(float(angle) % 360.0 for angle in angles)
    gaps = [
        (
            ordered[index + 1] - angle
            if index + 1 < len(ordered)
            else ordered[0] + 360.0 - angle,
            index,
        )
        for index, angle in enumerate(ordered)
    ]
    largest_gap, gap_index = max(gaps, key=lambda item: (item[0], -item[1]))
    start = ordered[(gap_index + 1) % len(ordered)]
    span = max(0.0, 360.0 - largest_gap)
    return (start + 0.5 * span) % 360.0, span


def _measure_graph_collision_diagnostics(
    populations: Sequence[Mapping[str, Any]],
    *,
    collision_tolerance_deg: float,
) -> dict[str, Any]:
    instances = [
        instance for population in populations for instance in population["instances"]
    ]
    samples = [
        sample for instance in instances for sample in instance["collision_samples"]
    ]
    radial_values = [float(sample["radius_mm"]) for sample in samples]
    axial_values = [float(sample["axial_mm"]) for sample in samples]
    radial_range = (min(radial_values), max(radial_values))
    axial_range = (min(axial_values), max(axial_values))
    sample_groups_by_component = {
        instance["source_component_id"]: _collision_sample_groups(
            instance["collision_samples"],
            radial_range_mm=radial_range,
            axial_range_mm=axial_range,
            radial_count=_COLLISION_RADIAL_CELL_COUNT,
            axial_count=_COLLISION_AXIAL_CELL_COUNT,
        )
        for instance in instances
    }
    cells_by_component = {
        instance["source_component_id"]: {
            tuple(cell["cell_index"]): cell
            for cell in _collision_cells_from_samples(
                instance["collision_samples"],
                radial_range_mm=radial_range,
                axial_range_mm=axial_range,
            )
        }
        for instance in instances
    }
    triangles_by_component = {
        instance["source_component_id"]: _surface_grid_triangles(
            instance.get("collision_surface_grids", ())
        )
        for instance in instances
    }
    collisions = []
    broad_phase_candidate_count = 0
    refined_candidate_count = 0
    triangle_instance_pair_count = 0
    triangle_test_count = 0
    point_fallback_pair_count = 0
    for first_index, first in enumerate(instances):
        first_cells = cells_by_component[first["source_component_id"]]
        first_groups = sample_groups_by_component[first["source_component_id"]]
        for second in instances[first_index + 1 :]:
            second_cells = cells_by_component[second["source_component_id"]]
            second_groups = sample_groups_by_component[second["source_component_id"]]
            broad_candidates = []
            for cell_index in first_cells.keys() & second_cells.keys():
                first_cell = first_cells[cell_index]
                second_cell = second_cells[cell_index]
                separation = _angle_distance(
                    first_cell["center_angle_deg"], second_cell["center_angle_deg"]
                )
                clearance = separation - 0.5 * (
                    first_cell["span_deg"] + second_cell["span_deg"]
                )
                if clearance > collision_tolerance_deg:
                    continue
                broad_phase_candidate_count += 1
                broad_candidates.append((cell_index, clearance))
            if not broad_candidates:
                continue

            first_triangles = triangles_by_component[first["source_component_id"]]
            second_triangles = triangles_by_component[second["source_component_id"]]
            if first_triangles and second_triangles:
                triangle_instance_pair_count += 1
                intersection, tested_count = _triangle_mesh_intersection(
                    first_triangles, second_triangles
                )
                triangle_test_count += tested_count
                if intersection is None:
                    continue
                refined_candidate_count += 1
                collision_cell, coarse_clearance = min(
                    broad_candidates, key=lambda item: item[1]
                )
                collisions.append(
                    {
                        "first_source_component_id": first[
                            "source_component_id"
                        ],
                        "second_source_component_id": second[
                            "source_component_id"
                        ],
                        "cell_index": list(collision_cell),
                        "coarse_angular_clearance_deg": coarse_clearance,
                        "angular_clearance_deg": coarse_clearance,
                        "narrow_phase": "triangle_sat",
                        **intersection,
                    }
                )
                continue

            point_fallback_pair_count += 1
            minimum_clearance = math.inf
            collision_cell = None
            refined_cell = None
            coarse_clearance = math.inf
            for cell_index, clearance in broad_candidates:
                refined = _refined_collision_cell(
                    first_groups[cell_index],
                    second_groups[cell_index],
                    coarse_cell_index=cell_index,
                    radial_range_mm=radial_range,
                    axial_range_mm=axial_range,
                    collision_tolerance_deg=collision_tolerance_deg,
                )
                if refined is None:
                    continue
                refined_candidate_count += 1
                if refined["angular_clearance_deg"] < minimum_clearance:
                    minimum_clearance = refined["angular_clearance_deg"]
                    coarse_clearance = clearance
                    collision_cell = cell_index
                    refined_cell = refined["refined_cell_index"]
            if minimum_clearance <= collision_tolerance_deg:
                collisions.append(
                    {
                        "first_source_component_id": first["source_component_id"],
                        "second_source_component_id": second["source_component_id"],
                        "cell_index": list(collision_cell),
                        "refined_cell_index": refined_cell,
                        "coarse_angular_clearance_deg": coarse_clearance,
                        "angular_clearance_deg": minimum_clearance,
                        "narrow_phase": "adaptive_sample_cell",
                    }
                )
    if triangle_instance_pair_count and not point_fallback_pair_count:
        narrow_phase_method = "sampled_uv_triangle_sat"
    elif triangle_instance_pair_count:
        narrow_phase_method = "sampled_uv_triangle_sat_with_point_cell_fallback"
    else:
        narrow_phase_method = "adaptive_cylindrical_sample_cells"
    return {
        "method": (
            "authoritative_v112_uv_grid_global_radial_axial_angular_cells_"
            "with_3d_narrow_phase"
        ),
        "fidelity": _COLLISION_FIDELITY,
        "narrow_phase_method": narrow_phase_method,
        "collision_free": not collisions,
        "collision_count": len(collisions),
        "collisions": collisions,
        "broad_phase_candidate_count": broad_phase_candidate_count,
        "refined_candidate_count": refined_candidate_count,
        "triangle_instance_pair_count": triangle_instance_pair_count,
        "triangle_test_count": triangle_test_count,
        "point_fallback_pair_count": point_fallback_pair_count,
        "tolerance_deg": collision_tolerance_deg,
        "scope": "blade_material_surfaces_excluding_support_joining_attachments",
        "physical_grid": {
            "coordinate_frame": "canonical_cylindrical_r_z",
            "radial_range_mm": list(radial_range),
            "axial_range_mm": list(axial_range),
            "radial_cell_count": _COLLISION_RADIAL_CELL_COUNT,
            "axial_cell_count": _COLLISION_AXIAL_CELL_COUNT,
            "local_refinement_divisions": _COLLISION_REFINEMENT_DIVISIONS,
        },
    }


def _validate_supplied_envelope(
    instance: Mapping[str, Any],
    generated: Mapping[str, Any],
    *,
    tolerance_mm: float,
    angular_tolerance_deg: float,
    instance_name: str,
) -> None:
    angular_span = _positive_finite(
        instance.get("angular_span_deg"), f"{instance_name}.angular_span_deg"
    )
    angular_envelope = _mapping(
        instance.get("angular_envelope_deg"),
        f"{instance_name}.angular_envelope_deg",
    )
    envelope_span = _positive_finite(
        angular_envelope.get("span_deg"),
        f"{instance_name}.angular_envelope_deg.span_deg",
    )
    radial = _numeric_range(
        instance.get("radial_support_range_mm"),
        f"{instance_name}.radial_support_range_mm",
    )
    axial = _numeric_range(
        instance.get("axial_support_range_mm"),
        f"{instance_name}.axial_support_range_mm",
    )
    derived_radial = generated["radial_range_mm"]
    derived_axial = generated["axial_range_mm"]
    if (
        angular_span + angular_tolerance_deg < generated["span_deg"]
        or envelope_span + angular_tolerance_deg < generated["span_deg"]
        or abs(angular_span - envelope_span) > angular_tolerance_deg
        or radial[0] > derived_radial[0] + tolerance_mm
        or radial[1] < derived_radial[1] - tolerance_mm
        or axial[0] > derived_axial[0] + tolerance_mm
        or axial[1] < derived_axial[1] - tolerance_mm
    ):
        raise PatternReconstructionError(
            "v116_pattern_envelope_invalid",
            f"{instance_name} supplied collision envelope understates authoritative V1.1.2 surfaces",
            details={"supplied": dict(instance), "generated": dict(generated)},
        )


def _validate_relative_phase(
    graph: Mapping[str, Any],
    populations: Mapping[str, Mapping[str, Any]],
    tolerance_deg: float,
) -> None:
    if "splitter" not in populations:
        return
    main = populations["main"]
    splitter = populations["splitter"]
    main_pitch = 360.0 / int(main["count"])
    canonical = graph["canonical_nurbs_parameterization"]["blade_population"]
    expected_offset = float(canonical["splitter_phase_offset_pitch"]) * main_pitch
    measured_offset = _normalized_period(
        float(splitter["phase_deg"]) - float(main["phase_deg"]), main_pitch
    )
    if abs(_wrapped_period(measured_offset - expected_offset, main_pitch)) > tolerance_deg:
        raise PatternReconstructionError(
            "v116_pattern_phase_invalid",
            "measured splitter phase does not match generated splitter phase",
        )


def _validate_material_topology(
    graph: Mapping[str, Any],
    evidence_value: Mapping[str, Any],
    *,
    instance_ids: list[str],
    periodic_provenance: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
    trusted_material: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = _mapping(evidence_value, "topology_support_evidence")
    if evidence.get("status") != "PASS" or evidence.get("authority") != "authenticated_topology_support_v1_1_6":
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "topology/support evidence is not authenticated for V1.1.6",
        )
    top_provenance = _provenance(
        evidence.get("provenance"),
        "topology_support_evidence.provenance",
        payload=_without_provenance(evidence),
        trusted_source=trusted_source,
    )
    if (
        top_provenance["source_solid_id"]
        != periodic_provenance["source_solid_shape_identity"]
        or top_provenance["source_sha256"] != periodic_provenance["source_sha256"]
        or sorted(top_provenance["source_entity_ids"])
        != sorted(trusted_source["faces_by_id"])
        or not set(periodic_provenance["source_entity_ids"]).issubset(
            set(top_provenance["source_entity_ids"])
        )
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid",
            "periodic component ids are not members of the authenticated topology source inventory",
        )
    mode = evidence.get("mode")
    graph_mode = _mapping(graph.get("facets"), "surface_graph.facets").get("shroud_topology")
    if (
        mode not in {"open", "closed"}
        or mode != graph_mode
        or mode != trusted_material["mode"]
    ):
        raise PatternReconstructionError(
            "v116_material_topology_invalid",
            "authenticated material mode does not match the generated V1.1.2 topology",
        )
    hub = _material_support(
        evidence.get("hub_support"), "hub_support", trusted_source
    )
    if hub.get("material") is not True or hub.get("semantic_role") != "hub_support":
        raise PatternReconstructionError(
            "v116_material_topology_invalid", "hub support must be authenticated material"
        )
    if sorted(hub["source_face_ids"]) != trusted_material["hub_support_face_ids"]:
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "hub support faces do not match canonical support recovery",
        )
    hub_attachment = _attachment_contract(
        hub.get("blade_attachment"),
        "hub_support.blade_attachment",
        instance_ids,
        trusted_source,
        trusted_material["hub_attachment_face_ids_by_instance"],
    )
    graph_roles = {surface.get("role") for surface in graph["surfaces"]}
    if mode == "open":
        if evidence.get("material_shroud") is not None or any(role in graph_roles for role in _SHROUD_ROLES):
            raise PatternReconstructionError(
                "v116_open_material_shroud_forbidden",
                "open topology cannot contain a material shroud role",
            )
        if "material_shroud_area_mm2" in evidence:
            raise PatternReconstructionError(
                "v116_open_material_shroud_forbidden",
                "open topology cannot declare material shroud area",
            )
        reference = _material_support(
            evidence.get("open_tip_reference"),
            "open_tip_reference",
            trusted_source,
        )
        if (
            reference.get("semantic_role") != "open_tip_reference"
            or reference.get("material") is not False
            or reference.get("render_default") != "hidden"
            or reference.get("export_default") != "excluded"
        ):
            raise PatternReconstructionError(
                "v116_material_topology_invalid",
                "open-tip reference must be non-material construction metadata",
            )
        if sorted(reference["source_face_ids"]) != trusted_material[
            "open_tip_reference_face_ids"
        ]:
            raise PatternReconstructionError(
                "v116_material_provenance_missing",
                "open-tip reference faces do not match canonical support recovery",
            )
        if "open_tip_dome" not in graph_roles:
            raise PatternReconstructionError(
                "v116_material_topology_invalid", "open blades require per-blade material tip domes"
            )
        return {
            "mode": "open",
            "source_solid_id": top_provenance["source_solid_id"],
            "hub_support": _support_manifest(hub, hub_attachment),
            "material_shroud": None,
            "material_shroud_area_mm2": None,
            "open_tip_reference": {
                "semantic_role": "open_tip_reference",
                "material": False,
                "render_default": "hidden",
                "export_default": "excluded",
                "source_face_ids": list(reference["source_face_ids"]),
            },
            "open_tip_dome": {
                "material": True,
                "instance_count": len(instance_ids),
                "render_default": "material",
                "export_default": "included",
            },
        }

    if evidence.get("open_tip_reference") is not None or "open_tip_reference" in graph_roles:
        raise PatternReconstructionError(
            "v116_material_topology_invalid", "closed topology cannot contain an open-tip reference"
        )
    shroud = _material_support(
        evidence.get("material_shroud"), "material_shroud", trusted_source
    )
    if shroud.get("material") is not True or shroud.get("semantic_role") != "closed_shroud":
        raise PatternReconstructionError(
            "v116_material_topology_invalid", "closed topology requires a material shroud"
        )
    trusted_shroud = trusted_material["material_shroud"]
    if (
        sorted(_identifiers(shroud.get("source_face_ids"), "material_shroud.source_face_ids"))
        != trusted_shroud["source_face_ids"]
        or sorted(
            _identifiers(
                shroud.get("inner_flowpath_face_ids"),
                "material_shroud.inner_flowpath_face_ids",
            )
        )
        != trusted_shroud["inner_flowpath_face_ids"]
        or sorted(
            _identifiers(
                shroud.get("outer_material_face_ids"),
                "material_shroud.outer_material_face_ids",
            )
        )
        != trusted_shroud["outer_material_face_ids"]
    ):
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "closed shroud faces do not match canonical support recovery",
        )
    thickness = _finite_thickness(shroud.get("finite_thickness"), shroud)
    if thickness != trusted_shroud["finite_thickness"]:
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            "closed shroud thickness differs from canonical Task 8 recovery",
        )
    shroud_attachment = _attachment_contract(
        shroud.get("blade_attachment"),
        "material_shroud.blade_attachment",
        instance_ids,
        trusted_source,
        trusted_shroud["blade_attachment_face_ids_by_instance"],
    )
    if not {"hub_support", "shroud_support", "closed_shroud_attachment"}.issubset(graph_roles):
        raise PatternReconstructionError(
            "v116_material_topology_invalid",
            "closed V1.1.2 graph lacks hub, finite shroud, or shroud attachments",
        )
    return {
        "mode": "closed",
        "source_solid_id": top_provenance["source_solid_id"],
        "hub_support": _support_manifest(hub, hub_attachment),
        "material_shroud": {
            **_support_manifest(shroud, shroud_attachment),
            "finite_thickness": thickness,
        },
        "open_tip_reference": None,
    }


def _material_support(
    value: Any, name: str, trusted_source: Mapping[str, Any]
) -> dict[str, Any]:
    support = dict(_mapping(value, name))
    if support.get("status") != "PASS":
        raise PatternReconstructionError(
            "v116_material_topology_invalid", f"{name} did not pass authenticated recovery"
        )
    source_face_ids = _identifiers(support.get("source_face_ids"), f"{name}.source_face_ids")
    provenance = _provenance(
        support.get("provenance"),
        f"{name}.provenance",
        payload=_without_provenance(support),
        trusted_source=trusted_source,
    )
    if sorted(source_face_ids) != sorted(provenance["source_entity_ids"]):
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            f"{name} provenance inventory does not equal its source faces",
        )
    support["source_face_ids"] = source_face_ids
    support["provenance"] = provenance
    return support


def _attachment_contract(
    value: Any,
    name: str,
    expected_instance_ids: list[str],
    trusted_source: Mapping[str, Any],
    trusted_face_ids_by_instance: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    attachment = dict(_mapping(value, name))
    instance_ids = _identifiers(attachment.get("instance_ids"), f"{name}.instance_ids")
    if sorted(instance_ids) != sorted(expected_instance_ids):
        raise PatternReconstructionError(
            "v116_attachment_contract_invalid",
            f"{name} must cover every measured periodic blade instance exactly",
        )
    by_instance = _mapping(
        attachment.get("source_face_ids_by_instance"),
        f"{name}.source_face_ids_by_instance",
    )
    if sorted(by_instance) != sorted(expected_instance_ids):
        raise PatternReconstructionError(
            "v116_attachment_contract_invalid", f"{name} provenance is incomplete"
        )
    owned: set[str] = set()
    normalized: dict[str, list[str]] = {}
    for instance_id in sorted(expected_instance_ids):
        face_ids = _identifiers(by_instance[instance_id], f"{name}.{instance_id}")
        if owned.intersection(face_ids):
            raise PatternReconstructionError(
                "v116_attachment_contract_invalid",
                f"{name} source attachment face ownership is not disjoint",
            )
        owned.update(face_ids)
        normalized[instance_id] = face_ids
    if {
        instance_id: sorted(face_ids)
        for instance_id, face_ids in normalized.items()
    } != {
        instance_id: list(trusted_face_ids_by_instance[instance_id])
        for instance_id in sorted(trusted_face_ids_by_instance)
    }:
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            f"{name} does not match canonical support attachment ownership",
        )
    provenance = _provenance(
        attachment.get("provenance"),
        f"{name}.provenance",
        payload=_without_provenance(attachment),
        trusted_source=trusted_source,
    )
    if sorted(owned) != sorted(provenance["source_entity_ids"]):
        raise PatternReconstructionError(
            "v116_material_provenance_missing", f"{name} lacks source attachment provenance"
        )
    return {
        "instance_ids": sorted(instance_ids),
        "source_face_ids_by_instance": normalized,
        "attachment_authority": attachment.get("attachment_authority"),
    }


def _finite_thickness(value: Any, shroud: Mapping[str, Any]) -> dict[str, Any]:
    try:
        thickness = _mapping(value, "material_shroud.finite_thickness")
        samples = [
            _positive_finite(item, "finite_thickness.samples_mm")
            for item in thickness.get("samples_mm", ())
        ]
    except (PatternReconstructionError, TypeError):
        raise PatternReconstructionError(
            "v116_closed_shroud_thickness_missing",
            "closed shroud requires authenticated finite positive thickness samples",
        ) from None
    pairs = thickness.get("source_face_pairs")
    if not samples or not _is_sequence(pairs) or len(pairs) != len(samples):
        raise PatternReconstructionError(
            "v116_closed_shroud_thickness_missing",
            "closed shroud thickness must bind every sample to a source face pair",
        )
    inner_ids = set(_identifiers(shroud.get("inner_flowpath_face_ids"), "inner_flowpath_face_ids"))
    outer_ids = set(_identifiers(shroud.get("outer_material_face_ids"), "outer_material_face_ids"))
    normalized_pairs: list[list[str]] = []
    for raw_pair in pairs:
        pair = _identifiers(raw_pair, "finite_thickness.source_face_pair")
        if len(pair) != 2 or pair[0] == pair[1] or pair[0] not in inner_ids or pair[1] not in outer_ids:
            raise PatternReconstructionError(
                "v116_closed_shroud_thickness_missing",
                "closed shroud thickness face pairing is incomplete or unauthenticated",
            )
        normalized_pairs.append(pair)
    minimum = _positive_finite(thickness.get("minimum_mm"), "finite_thickness.minimum_mm")
    if (
        thickness.get("finite_positive") is not True
        or abs(minimum - min(samples)) > max(1.0e-12, min(samples) * 1.0e-9)
        or thickness.get("sampling_authority") != "authenticated_paired_material_faces"
    ):
        raise PatternReconstructionError(
            "v116_closed_shroud_thickness_missing",
            "closed shroud thickness is not authenticated finite material support",
        )
    return {
        "samples_mm": samples,
        "minimum_mm": minimum,
        "source_face_pairs": normalized_pairs,
        "finite_positive": True,
        "sampling_authority": thickness["sampling_authority"],
    }


def _provenance(
    value: Any,
    name: str,
    *,
    payload: Mapping[str, Any],
    trusted_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a support digest over trusted identity plus payload sans provenance.

    The canonical payload contains the digest-basis label, trusted manifest digest,
    source SHA/solid identity, sorted source face ids, and the complete evidence
    record with only its own ``provenance`` member removed.
    """

    if not isinstance(value, Mapping):
        raise PatternReconstructionError(
            "v116_material_provenance_missing", f"{name} is not authenticated"
        )
    provenance = value
    digest = provenance.get("evidence_digest_sha256")
    if (
        provenance.get("authentication_status") != "PASS"
        or provenance.get("authority") != "authenticated_source_topology"
        or provenance.get("digest_basis") != _SUPPORT_DIGEST_BASIS
        or not isinstance(digest, str)
        or len(digest) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise PatternReconstructionError(
            "v116_material_provenance_missing", f"{name} is not authenticated"
        )
    normalized = {
        "authentication_status": "PASS",
        "authority": provenance["authority"],
        "source_solid_id": _identifier(provenance.get("source_solid_id"), f"{name}.source_solid_id"),
        "source_sha256": _sha256(
            provenance.get("source_sha256"), f"{name}.source_sha256"
        ),
        "source_entity_ids": _identifiers(
            provenance.get("source_entity_ids"), f"{name}.source_entity_ids"
        ),
        "evidence_digest_sha256": digest,
        "digest_basis": _SUPPORT_DIGEST_BASIS,
    }
    digest_basis = {
        "digest_basis": _SUPPORT_DIGEST_BASIS,
        "trusted_source_manifest_digest_sha256": trusted_source[
            "manifest_digest_sha256"
        ],
        "source_sha256": normalized["source_sha256"],
        "source_solid_shape_identity": normalized["source_solid_id"],
        "source_entity_ids": sorted(normalized["source_entity_ids"]),
        "evidence_payload": copy.deepcopy(dict(payload)),
    }
    if (
        normalized["source_sha256"] != trusted_source["source_sha256"]
        or normalized["source_solid_id"]
        != trusted_source["source_solid_shape_identity"]
        or not set(normalized["source_entity_ids"]).issubset(
            trusted_source["faces_by_id"]
        )
        or digest != _payload_digest(digest_basis)
    ):
        raise PatternReconstructionError(
            "v116_material_provenance_missing",
            f"{name} digest does not match its trusted canonical support payload",
        )
    return normalized


def _without_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(item) for key, item in value.items() if key != "provenance"}


def _support_manifest(support: Mapping[str, Any], attachment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_role": support["semantic_role"],
        "material": bool(support["material"]),
        "source_face_ids": list(support["source_face_ids"]),
        "blade_attachment": copy.deepcopy(dict(attachment)),
    }


def _decorate_material_surfaces(graph: dict[str, Any], material: Mapping[str, Any]) -> None:
    mode = material["mode"]
    for surface in graph["surfaces"]:
        role = surface.get("role")
        if role == "open_tip_reference":
            surface["material"] = False
            surface["render_default"] = "hidden"
            surface["export_default"] = "excluded"
            surface["construction_metadata"] = True
            surface.setdefault("display", {})["visible_by_default"] = False
        elif _is_non_material_topological_seam(surface):
            continue
        elif surface.get("blade_class") in _BLADE_CLASSES:
            surface["material"] = True
            surface["render_default"] = "material"
            surface["export_default"] = "included"
        elif role in {"hub_support", "mounting_bore"} or (
            mode == "closed" and role == "shroud_support"
        ):
            surface["material"] = True
            surface["render_default"] = "material"
            surface["export_default"] = "included"


def _transformed_surface_residual(
    representative: Mapping[str, Any],
    target: Mapping[str, Any],
    transform: list[list[float]],
) -> float:
    source_grid = representative["uv_grid"]
    target_grid = target["uv_grid"]
    if len(source_grid) != len(target_grid) or any(
        len(source_row) != len(target_row)
        for source_row, target_row in zip(source_grid, target_grid)
    ):
        raise PatternReconstructionError(
            "v116_pattern_surface_family_mismatch",
            "representative and instance UV grids have different topology",
        )
    maximum = 0.0
    for source_row, target_row in zip(source_grid, target_grid):
        for source_point, target_point in zip(source_row, target_row):
            transformed = [
                sum(transform[row][column] * float(source_point[column]) for column in range(3))
                + transform[row][3]
                for row in range(3)
            ]
            maximum = max(
                maximum,
                math.sqrt(sum((transformed[i] - float(target_point[i])) ** 2 for i in range(3))),
            )
    return maximum


def _surface_points(surface: Mapping[str, Any], name: str) -> None:
    grid = surface.get("uv_grid")
    if not _is_sequence(grid) or not grid:
        raise PatternReconstructionError(
            "v116_pattern_graph_invalid", f"{name} has no authoritative UV grid"
        )
    for row in grid:
        if not _is_sequence(row) or not row:
            raise PatternReconstructionError(
                "v116_pattern_graph_invalid", f"{name} has an invalid UV grid row"
            )
        for point in row:
            if not _is_sequence(point) or len(point) != 3 or not all(
                math.isfinite(float(value)) for value in point
            ):
                raise PatternReconstructionError(
                    "v116_pattern_graph_invalid", f"{name} has a non-finite UV point"
                )


def _rigid_z_rotation(value: Any, name: str) -> list[list[float]]:
    if not _is_sequence(value) or len(value) != 4:
        raise PatternReconstructionError(
            "v116_pattern_transform_invalid", f"{name} must be a 4x4 matrix"
        )
    try:
        matrix = [[float(item) for item in row] for row in value]
    except (TypeError, ValueError):
        raise PatternReconstructionError(
            "v116_pattern_transform_invalid", f"{name} must contain finite numbers"
        ) from None
    if any(len(row) != 4 for row in matrix) or not all(
        math.isfinite(item) for row in matrix for item in row
    ):
        raise PatternReconstructionError(
            "v116_pattern_transform_invalid", f"{name} must be finite and homogeneous"
        )
    tolerance = 1.0e-9
    expected_fixed = (
        abs(matrix[0][2]), abs(matrix[1][2]), abs(matrix[2][0]), abs(matrix[2][1]),
        abs(matrix[2][2] - 1.0), abs(matrix[0][3]), abs(matrix[1][3]), abs(matrix[2][3]),
        abs(matrix[3][0]), abs(matrix[3][1]), abs(matrix[3][2]), abs(matrix[3][3] - 1.0),
    )
    dot = matrix[0][0] * matrix[1][0] + matrix[0][1] * matrix[1][1]
    norm0 = matrix[0][0] ** 2 + matrix[0][1] ** 2
    norm1 = matrix[1][0] ** 2 + matrix[1][1] ** 2
    determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if (
        max(expected_fixed) > tolerance
        or abs(dot) > tolerance
        or abs(norm0 - 1.0) > tolerance
        or abs(norm1 - 1.0) > tolerance
        or abs(determinant - 1.0) > tolerance
    ):
        raise PatternReconstructionError(
            "v116_pattern_transform_invalid",
            f"{name} is not a homogeneous rigid rotation about canonical Z",
        )
    return matrix


def _angular_tolerance(periodic: Mapping[str, Any]) -> float:
    closure = _mapping(periodic.get("closure_diagnostics"), "closure_diagnostics")
    tolerance = _positive_finite(closure.get("tolerance_deg"), "closure_diagnostics.tolerance_deg")
    if tolerance >= 180.0:
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", "angular tolerance must be below 180 degrees"
        )
    return tolerance


def _lattice_index(value: Any, count: int, name: str) -> int:
    index = _nonnegative_int(value, f"{name}.lattice_index")
    if index >= count:
        raise PatternReconstructionError(
            "v116_pattern_instance_contract_invalid", f"{name} lattice index is out of range"
        )
    return index


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be a mapping"
        )
    return value


def _identifier_for_reason(value: Any, name: str, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatternReconstructionError(reason, f"{name} must be a non-empty identifier")
    return value


def _finite_for_reason(value: Any, name: str, reason: str) -> float:
    if isinstance(value, bool):
        raise PatternReconstructionError(reason, f"{name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PatternReconstructionError(reason, f"{name} must be finite") from None
    if not math.isfinite(number):
        raise PatternReconstructionError(reason, f"{name} must be finite")
    return number


def _positive_finite_for_reason(value: Any, name: str, reason: str) -> float:
    number = _finite_for_reason(value, name, reason)
    if number <= 0.0:
        raise PatternReconstructionError(reason, f"{name} must be positive")
    return number


def _nonnegative_int_for_reason(value: Any, name: str, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PatternReconstructionError(reason, f"{name} must be a non-negative integer")
    return value


def _sha256_for_reason(value: Any, name: str, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PatternReconstructionError(reason, f"{name} must be a lowercase SHA-256")
    return value


def _identifiers(value: Any, name: str) -> list[str]:
    if not _is_sequence(value) or not value:
        raise PatternReconstructionError(
            "v116_material_provenance_missing", f"{name} must be a non-empty sequence"
        )
    identifiers = [_identifier(item, name) for item in value]
    if len(set(identifiers)) != len(identifiers):
        raise PatternReconstructionError(
            "v116_material_provenance_missing", f"{name} must contain unique identifiers"
        )
    return identifiers


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be a non-empty identifier"
        )
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be finite"
        )
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be finite"
        ) from None
    if not math.isfinite(number):
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be finite"
        )
    return number


def _positive_finite(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0.0:
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be positive"
        )
    return number


def _numeric_range(value: Any, name: str) -> list[float]:
    if not _is_sequence(value) or len(value) != 2:
        raise PatternReconstructionError(
            "v116_pattern_envelope_invalid", f"{name} must be a two-value range"
        )
    result = [_finite(item, name) for item in value]
    if result[1] < result[0]:
        raise PatternReconstructionError(
            "v116_pattern_envelope_invalid", f"{name} must be ordered"
        )
    return result


def _sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PatternReconstructionError(
            "v116_periodic_provenance_invalid", f"{name} must be a lowercase SHA-256"
        )
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PatternReconstructionError(
            "v116_pattern_evidence_invalid", f"{name} must be a non-negative integer"
        )
    return value


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _normalized_angle(value: float) -> float:
    return value % 360.0


def _angle_distance(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _normalized_period(value: float, period: float) -> float:
    return value % period


def _wrapped_period(value: float, period: float) -> float:
    return (value + 0.5 * period) % period - 0.5 * period


def _payload_digest(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value
