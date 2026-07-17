from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any


_POPULATION_METHOD = "periodic_connected_face_components_v1_1_6"
_BLADE_SIDE_MEDOID_METHOD = (
    "minimum_total_symmetric_blade_side_surface_sample_residual_after_cyclic_alignment"
)
_GENERIC_MEDOID_METHOD = (
    "minimum_total_symmetric_surface_sample_residual_after_cyclic_alignment"
)
_COLLISION_METHOD = "source_topology_separation_with_angular_envelope_warning"
_STRICT_FACE_FIELDS = frozenset(
    {
        "source_face_id",
        "signature_hash",
        "area_mm2",
        "centroid_angle_deg",
        "canonical_surface_samples_mm",
        "streamwise_bounds_mm",
        "streamwise_coordinate",
        "radial_bounds_mm",
        "axial_bounds_mm",
        "wrap_deg",
        "wrap_evidence",
        "angular_span_deg",
        "angular_span_evidence",
        "is_periodic",
        "blade_related",
        "periodic_membership",
        "coarse_component",
        "source_frame_phase_deg",
        "canonical_frame_phase_deg",
        "phase_frame_evidence",
    }
)


class PeriodicBladeRecoveryError(ValueError):
    """A deterministic periodic-population recovery failure."""

    def __init__(
        self, reason: str, message: str, *, evidence: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.evidence = dict(evidence or {})


@dataclass(frozen=True)
class _Face:
    face_id: str
    signature: str
    area_mm2: float
    instance_angle_deg: float
    source_frame_phase_deg: float
    canonical_frame_phase_deg: float
    phase_frame_evidence: dict[str, Any]
    samples_mm: tuple[tuple[float, float, float], ...]
    streamwise_bounds_mm: tuple[float, float]
    radial_bounds_mm: tuple[float, float]
    axial_bounds_mm: tuple[float, float]
    wrap_deg: float
    angular_span_deg: float
    is_periodic: bool
    blade_related: bool
    periodic_group_id: str | None
    coarse_component_id: str
    coarse_component_evidence: dict[str, Any]
    periodic_seed_certified: bool


def recover_periodic_blade_populations(
    face_signatures: Sequence[Mapping[str, Any]],
    adjacency: Mapping[str, Iterable[str]],
    *,
    minimum_instance_count: int = 3,
    minimum_component_face_count: int = 4,
    closure_tolerance_deg: float = 0.5,
    collision_tolerance_deg: float = 1.0e-6,
    sample_limit_per_component: int = 256,
) -> dict[str, Any]:
    """Recover main and optional splitter populations from canonical face evidence.

    ``face_signatures`` must use the strict schema emitted by
    ``impeller_v11_6_source_frame.coarse_periodic_face_partition``. Missing
    membership or geometry evidence is a contract error, never inferred here.
    """

    _validate_options(
        minimum_instance_count=minimum_instance_count,
        minimum_component_face_count=minimum_component_face_count,
        closure_tolerance_deg=closure_tolerance_deg,
        collision_tolerance_deg=collision_tolerance_deg,
        sample_limit_per_component=sample_limit_per_component,
    )
    components, rejected = _build_components_with_rejections(
        face_signatures,
        adjacency,
        minimum_instance_count=minimum_instance_count,
        minimum_component_face_count=minimum_component_face_count,
    )
    groups = _group_equivalent_components(components)
    population_groups = [
        group for group in groups if len(group) >= minimum_instance_count
    ]
    rejected["unmatched_component_ids"] = sorted(
        component["source_component_id"]
        for group in groups
        if len(group) < minimum_instance_count
        for component in group
    )
    if not population_groups:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_population_ambiguous",
            "no repeated connected blade-face component population was recovered",
            evidence=rejected,
        )
    if len(population_groups) > 2:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_population_ambiguous",
            "more than two blade-related periodic component populations were recovered",
            evidence={
                **rejected,
                "candidate_population_sizes": sorted(
                    len(group) for group in population_groups
                ),
            },
        )

    provisional = [
        estimate_periodic_population(
            group,
            population_id=f"candidate_{index}",
            closure_tolerance_deg=closure_tolerance_deg,
            sample_limit_per_component=sample_limit_per_component,
        )
        for index, group in enumerate(population_groups)
    ]
    main, splitter, classification_evidence = _classify_populations(provisional)
    _name_population(main, "main")
    if splitter is not None:
        _name_population(splitter, "splitter")
    _set_relative_phase(
        main,
        splitter,
        consistency_tolerance_deg=closure_tolerance_deg,
    )

    populations = [main] if splitter is None else [main, splitter]
    collision_diagnostics = measure_cyclic_collision_diagnostics(
        populations,
        adjacency=adjacency,
        collision_tolerance_deg=collision_tolerance_deg,
    )
    closure_diagnostics = {
        "all_populations_closed": all(
            population["closure"]["within_tolerance"] for population in populations
        ),
        "maximum_gap_residual_deg": _round(
            max(
                population["closure"]["maximum_gap_residual_deg"]
                for population in populations
            ),
            9,
        ),
        "maximum_closure_residual_deg": _round(
            max(
                population["closure"]["closure_residual_deg"]
                for population in populations
            ),
            9,
        ),
        "tolerance_deg": _round(closure_tolerance_deg, 9),
    }
    return {
        "method": _POPULATION_METHOD,
        "main_blade_count": int(main["count"]),
        "splitter_blade_count": 0 if splitter is None else int(splitter["count"]),
        "main": main,
        "splitter": splitter,
        "populations": populations,
        "classification_evidence": classification_evidence,
        "closure_diagnostics": closure_diagnostics,
        "collision_diagnostics": collision_diagnostics,
        "rejected": rejected,
        "input_face_count": len(face_signatures),
        "connected_component_count": len(components),
    }


def build_periodic_face_components(
    face_signatures: Sequence[Mapping[str, Any]],
    adjacency: Mapping[str, Iterable[str]],
    *,
    minimum_instance_count: int = 3,
    minimum_component_face_count: int = 4,
) -> list[dict[str, Any]]:
    """Build complete connected blade components; incomplete faces are omitted."""

    components, _ = _build_components_with_rejections(
        face_signatures,
        adjacency,
        minimum_instance_count=minimum_instance_count,
        minimum_component_face_count=minimum_component_face_count,
    )
    return components


def estimate_periodic_population(
    components: Sequence[Mapping[str, Any]],
    *,
    population_id: str = "candidate",
    closure_tolerance_deg: float = 0.5,
    sample_limit_per_component: int = 256,
) -> dict[str, Any]:
    """Measure one already-grouped periodic component population."""

    if len(components) < 2:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_population_ambiguous",
            "periodic population measurement requires at least two connected instances",
        )
    ordered_components = sorted(
        components, key=lambda item: str(item["source_component_id"])
    )
    angles = [float(component["instance_angle_deg"]) for component in ordered_components]
    lattice = _measure_lattice(angles, closure_tolerance_deg)
    source_lattice = _measure_lattice(
        [float(component["source_frame_phase_deg"]) for component in ordered_components],
        closure_tolerance_deg,
    )
    if not lattice["closure"]["within_tolerance"]:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_population_ambiguous",
            "candidate periodic component population does not close on a full circular lattice",
            evidence={
                "population_id": population_id,
                "source_component_ids": sorted(
                    str(component["source_component_id"])
                    for component in ordered_components
                ),
                "closure": lattice["closure"],
            },
        )
    medoid = select_population_medoid(
        ordered_components,
        sample_limit_per_component=sample_limit_per_component,
        sample_field="representative_surface_samples_mm",
        selection_method=_BLADE_SIDE_MEDOID_METHOD,
    )
    representative_id = medoid["source_component_id"]
    representative = next(
        component
        for component in ordered_components
        if component["source_component_id"] == representative_id
    )

    instances = []
    for component in sorted(
        ordered_components,
        key=lambda item: (
            _normalize_angle(float(item["instance_angle_deg"])),
            str(item["source_component_id"]),
        ),
    ):
        angle_deg = _normalize_angle(float(component["instance_angle_deg"]))
        lattice_index, expected_angle_deg, residual_deg = _nearest_lattice_site(
            angle_deg,
            lattice["phase_deg"],
            lattice["nominal_pitch_deg"],
            len(ordered_components),
        )
        rotation_deg = _normalize_angle(
            angle_deg - float(representative["instance_angle_deg"])
        )
        instances.append(
            {
                "population_id": population_id,
                "source_component_id": component["source_component_id"],
                "source_component_evidence": dict(
                    component["source_component_evidence"]
                ),
                "source_face_ids": list(component["source_face_ids"]),
                "face_count": int(component["face_count"]),
                "component_completeness": dict(
                    component["component_completeness"]
                ),
                "measured_angle_deg": _round(angle_deg, 9),
                "canonical_frame_phase_deg": _round(
                    float(component["canonical_frame_phase_deg"]), 9
                ),
                "source_frame_phase_deg": _round(
                    float(component["source_frame_phase_deg"]), 9
                ),
                "lattice_index": lattice_index,
                "expected_angle_deg": _round(expected_angle_deg, 9),
                "pitch_residual_deg": _round(residual_deg, 9),
                "rotation_from_representative_deg": _round(rotation_deg, 9),
                "transform_from_representative": _rotation_z_matrix(rotation_deg),
                "residual_to_representative_mm": medoid["residuals_to_instances_mm"][
                    component["source_component_id"]
                ],
                "representative_fit_basis": "authenticated_blade_side_pair",
                "representative_fit_sample_count": int(
                    component["representative_surface_sample_count"]
                ),
                "aligned_surface_sample_count": int(component["surface_sample_count"]),
                "angular_span_deg": _round(float(component["angular_span_deg"]), 9),
                "angular_envelope_deg": dict(component["angular_envelope_deg"]),
                "radial_support_range_mm": list(component["radial_support_range_mm"]),
                "axial_support_range_mm": list(component["axial_support_range_mm"]),
            }
        )

    return {
        "population_id": population_id,
        "classification": "unclassified",
        "count": len(ordered_components),
        "pitch_deg": lattice["pitch_deg"],
        "nominal_pitch_deg": lattice["nominal_pitch_deg"],
        "phase_deg": lattice["phase_deg"],
        "canonical_frame_phase_deg": lattice["phase_deg"],
        "source_frame_phase_deg": source_lattice["phase_deg"],
        "phase_frame_evidence": dict(ordered_components[0]["phase_frame_evidence"]),
        "phase_relative_to_main_deg": None,
        "passage_bisector_deviation_deg": None,
        "streamwise_extent_mm": _round(
            median(
                float(component["streamwise_extent_mm"])
                for component in ordered_components
            ),
            6,
        ),
        "inlet_location_mm": _round(
            median(
                float(component["inlet_location_mm"])
                for component in ordered_components
            ),
            6,
        ),
        "radial_support_range_mm": _median_range(
            ordered_components, "radial_support_range_mm"
        ),
        "axial_support_range_mm": _median_range(
            ordered_components, "axial_support_range_mm"
        ),
        "wrap_deg": _round(
            median(float(component["wrap_deg"]) for component in ordered_components), 9
        ),
        "face_role_signature": ordered_components[0]["face_role_signature"],
        "adjacency_graph_signature": ordered_components[0]["adjacency_graph_signature"],
        "source_component_ids": sorted(
            component["source_component_id"] for component in ordered_components
        ),
        "representative": {
            "population_id": population_id,
            "source_component_id": representative_id,
            "source_component_evidence": dict(
                representative["source_component_evidence"]
            ),
            "source_face_ids": list(representative["source_face_ids"]),
            "face_count": int(representative["face_count"]),
            "component_completeness": dict(
                representative["component_completeness"]
            ),
            "selection_method": medoid["selection_method"],
            "selection_surface_role": "authenticated_blade_side_pair",
            "selection_surface_sample_count": int(
                representative["representative_surface_sample_count"]
            ),
            "total_medoid_residual_mm": medoid["total_residual_mm"],
            "pairwise_residuals_mm": medoid["pairwise_residuals_mm"],
            "aligned_surface_sample_count": int(representative["surface_sample_count"]),
            "lattice_index": medoid["lattice_index"],
            "measured_angle_deg": _round(
                float(representative["instance_angle_deg"]), 9
            ),
            "aligned_geometry_digest": medoid["aligned_geometry_digest"],
            "tie_break_method": medoid["tie_break_method"],
        },
        "instances": instances,
        "closure": lattice["closure"],
    }


def select_population_medoid(
    components: Sequence[Mapping[str, Any]],
    *,
    sample_limit_per_component: int = 256,
    sample_field: str = "surface_samples_mm",
    selection_method: str = _GENERIC_MEDOID_METHOD,
) -> dict[str, Any]:
    """Select the cyclically aligned surface-sample medoid deterministically."""

    if not components:
        raise PeriodicBladeRecoveryError(
            "v116_representative_blade_selection_failed",
            "representative selection requires at least one periodic component",
        )
    aligned: dict[str, list[tuple[float, float, float]]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for component in components:
        component_id = str(component["source_component_id"])
        if component_id in by_id:
            raise PeriodicBladeRecoveryError(
                "v116_representative_blade_selection_failed",
                f"duplicate periodic component id: {component_id}",
            )
        samples = component.get(sample_field)
        if not isinstance(samples, Sequence) or not samples:
            raise PeriodicBladeRecoveryError(
                "v116_representative_blade_selection_failed",
                (
                    f"periodic component {component_id} has no canonical "
                    f"{sample_field} samples"
                ),
            )
        normalized_samples = [
            _point(sample, f"surface sample for {component_id}") for sample in samples
        ]
        aligned[component_id] = _bounded_samples(
            [
                _rotate_point_about_z(sample, -float(component["instance_angle_deg"]))
                for sample in normalized_samples
            ],
            sample_limit_per_component,
        )
        by_id[component_id] = component

    component_ids = sorted(aligned)
    residuals: dict[tuple[str, str], float] = {}
    totals = {component_id: 0.0 for component_id in component_ids}
    for first_index, first_id in enumerate(component_ids):
        for second_id in component_ids[first_index + 1 :]:
            residual = _symmetric_sample_rms(aligned[first_id], aligned[second_id])
            residuals[(first_id, second_id)] = residual
            totals[first_id] += residual
            totals[second_id] += residual
    lattice = _measure_lattice(
        [
            float(by_id[component_id]["instance_angle_deg"])
            for component_id in component_ids
        ],
        360.0,
    )
    tie_breaks = {}
    for component_id in component_ids:
        lattice_index, _, _ = _nearest_lattice_site(
            float(by_id[component_id]["instance_angle_deg"]),
            float(lattice["phase_deg"]),
            float(lattice["nominal_pitch_deg"]),
            len(component_ids),
        )
        geometry_key = tuple(
            tuple(round(coordinate, 12) for coordinate in point)
            for point in aligned[component_id]
        )
        tie_breaks[component_id] = {
            "key": (round(totals[component_id], 12), lattice_index, geometry_key),
            "lattice_index": lattice_index,
            "aligned_geometry_digest": hashlib.sha256(
                _stable_json(geometry_key).encode("utf-8")
            ).hexdigest(),
        }
    best_key = min(item["key"] for item in tie_breaks.values())
    best_ids = [
        component_id
        for component_id, item in tie_breaks.items()
        if item["key"] == best_key
    ]
    if len(best_ids) != 1:
        raise PeriodicBladeRecoveryError(
            "v116_representative_blade_selection_failed",
            "medoid tie remains ambiguous after canonical lattice and geometry tie-breaks",
            evidence={"tied_lattice_index": tie_breaks[best_ids[0]]["lattice_index"]},
        )
    representative_id = best_ids[0]
    residuals_to_instances = {}
    pairwise_residuals = []
    for component_id in component_ids:
        if component_id == representative_id:
            residual = 0.0
        else:
            key = tuple(sorted((representative_id, component_id)))
            residual = residuals[key]
        residuals_to_instances[component_id] = _round(residual, 6)
        pairwise_residuals.append(
            {
                "source_component_id": component_id,
                "residual_mm": _round(residual, 6),
            }
        )
    return {
        "source_component_id": representative_id,
        "selection_method": selection_method,
        "total_residual_mm": _round(totals[representative_id], 6),
        "pairwise_residuals_mm": pairwise_residuals,
        "residuals_to_instances_mm": residuals_to_instances,
        "lattice_index": tie_breaks[representative_id]["lattice_index"],
        "aligned_geometry_digest": tie_breaks[representative_id][
            "aligned_geometry_digest"
        ],
        "tie_break_method": "total_residual_then_canonical_lattice_index_then_aligned_geometry",
    }


def measure_cyclic_collision_diagnostics(
    populations: Sequence[Mapping[str, Any]],
    *,
    adjacency: Mapping[str, Iterable[str]] | None = None,
    collision_tolerance_deg: float = 1.0e-6,
) -> dict[str, Any]:
    """Authenticate source separation and retain swept-envelope warnings."""

    instances = [
        instance for population in populations for instance in population["instances"]
    ]
    envelope_warnings = []
    clearances = []
    for first_index, first in enumerate(instances):
        for second in instances[first_index + 1 :]:
            if not _ranges_overlap(
                first["radial_support_range_mm"], second["radial_support_range_mm"]
            ):
                continue
            if not _ranges_overlap(
                first["axial_support_range_mm"], second["axial_support_range_mm"]
            ):
                continue
            separation = abs(
                _wrap(
                    float(second["measured_angle_deg"])
                    - float(first["measured_angle_deg"]),
                    360.0,
                )
            )
            half_width = 0.5 * (
                float(first["angular_span_deg"]) + float(second["angular_span_deg"])
            )
            clearance = separation - half_width
            clearances.append(clearance)
            if clearance < -collision_tolerance_deg:
                envelope_warnings.append(
                    {
                        "first_population_id": first["population_id"],
                        "first_source_component_id": first["source_component_id"],
                        "second_population_id": second["population_id"],
                        "second_source_component_id": second["source_component_id"],
                        "center_separation_deg": _round(separation, 9),
                        "angular_clearance_deg": _round(clearance, 9),
                    }
                )
    envelope_warnings.sort(
        key=lambda item: (
            item["angular_clearance_deg"],
            item["first_source_component_id"],
            item["second_source_component_id"],
        )
    )
    minimum_clearance = None if not clearances else _round(min(clearances), 9)
    topology_contacts = _source_topology_contact_pairs(instances, adjacency)
    topology_checked = adjacency is not None
    collision_status = "FAIL" if topology_contacts else "UNKNOWN"
    return {
        "method": _COLLISION_METHOD,
        "collision_status": collision_status,
        "collision_free": False if topology_contacts else None,
        "collision_count": len(topology_contacts),
        "collisions": topology_contacts,
        "source_topology_separation_checked": topology_checked,
        "source_topology_separated": topology_checked and not topology_contacts,
        "source_topology_contact_pairs": topology_contacts,
        "diagnostic_collision_free": not envelope_warnings,
        "angular_envelope_warning_count": len(envelope_warnings),
        "angular_envelope_warnings": envelope_warnings,
        "minimum_angular_clearance_deg": minimum_clearance,
        "tolerance_deg": _round(collision_tolerance_deg, 9),
        "diagnostic_scope": (
            "exact source-face topology separation; circular swept envelopes are warnings only"
        ),
        "exact_brep_collision_checked": False,
        "exact_brep_collision_free": None,
        "maturity_claim": "source_topology_authenticated_collision_state_unknown_without_exact_solid_intersection",
    }


def _source_topology_contact_pairs(
    instances: Sequence[Mapping[str, Any]],
    adjacency: Mapping[str, Iterable[str]] | None,
) -> list[dict[str, Any]]:
    if adjacency is None:
        return []
    graph = _normalize_adjacency(adjacency)
    contacts = []
    for first_index, first in enumerate(instances):
        first_faces = {str(value) for value in first["source_face_ids"]}
        for second in instances[first_index + 1 :]:
            second_faces = {str(value) for value in second["source_face_ids"]}
            shared = sorted(
                [face_id, neighbor]
                for face_id in first_faces
                for neighbor in graph.get(face_id, set()).intersection(second_faces)
            )
            if shared:
                contacts.append(
                    {
                        "first_source_component_id": first["source_component_id"],
                        "second_source_component_id": second["source_component_id"],
                        "shared_adjacency_pairs": shared,
                    }
                )
    contacts.sort(
        key=lambda item: (
            item["first_source_component_id"],
            item["second_source_component_id"],
        )
    )
    return contacts


def _build_components_with_rejections(
    face_signatures: Sequence[Mapping[str, Any]],
    adjacency: Mapping[str, Iterable[str]],
    *,
    minimum_instance_count: int,
    minimum_component_face_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if minimum_instance_count < 2:
        raise ValueError("minimum_instance_count must be at least two")
    if minimum_component_face_count < 4:
        raise ValueError("minimum_component_face_count must be at least four")

    normalized_adjacency = _normalize_adjacency(adjacency)
    faces = [
        _normalize_face(record, index=index)
        for index, record in enumerate(face_signatures)
    ]
    by_id: dict[str, _Face] = {}
    for face in faces:
        if face.face_id in by_id:
            raise ValueError(f"duplicate face id: {face.face_id}")
        by_id[face.face_id] = face
    candidate_ids = {
        face.face_id
        for face in faces
        if face.is_periodic
        and face.blade_related
        and face.angular_span_deg < 300.0
    }
    graph = {face_id: set() for face_id in candidate_ids}
    for face_id in sorted(candidate_ids):
        for neighbor in normalized_adjacency.get(face_id, set()):
            if (
                neighbor in candidate_ids
                and by_id[face_id].coarse_component_id
                == by_id[neighbor].coarse_component_id
            ):
                graph[face_id].add(neighbor)
                graph[neighbor].add(face_id)

    raw_components = []
    pending = set(candidate_ids)
    while pending:
        seed = min(pending)
        queue = deque([seed])
        pending.remove(seed)
        component_ids = []
        while queue:
            current = queue.popleft()
            component_ids.append(current)
            for neighbor in sorted(graph[current]):
                if neighbor in pending:
                    pending.remove(neighbor)
                    queue.append(neighbor)
        raw_components.append(sorted(component_ids))

    singleton_component_face_ids = sorted(
        component[0] for component in raw_components if len(component) == 1
    )
    undersized_component_face_ids = sorted(
        component
        for component in raw_components
        if 1 < len(component) < minimum_component_face_count
    )
    eligible = [
        _component_record([by_id[face_id] for face_id in component], graph)
        for component in raw_components
        if len(component) >= minimum_component_face_count
    ]
    eligible.sort(key=lambda component: component["source_component_id"])
    rejected = {
        "isolated_face_ids": singleton_component_face_ids,
        "singleton_component_face_ids": singleton_component_face_ids,
        "undersized_component_face_ids": undersized_component_face_ids,
        "nonperiodic_or_nonblade_face_ids": sorted(set(by_id) - candidate_ids),
        "unmatched_component_ids": [],
    }
    return eligible, rejected


def _component_record(
    faces: Sequence[_Face], graph: Mapping[str, set[str]]
) -> dict[str, Any]:
    ordered = sorted(faces, key=lambda face: face.face_id)
    face_ids = [face.face_id for face in ordered]
    coarse_component_ids = {face.coarse_component_id for face in ordered}
    if len(coarse_component_ids) != 1:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            "connected periodic faces do not share one source-frame component",
            evidence={
                "source_face_ids": face_ids,
                "coarse_component_ids": sorted(coarse_component_ids),
            },
        )
    source_component_id = next(iter(coarse_component_ids))
    source_component_evidence = dict(ordered[0].coarse_component_evidence)
    if set(source_component_evidence["source_entity_ids"]) != set(face_ids):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            "source-frame component membership differs from Task 5 adjacency component",
            evidence={
                "source_component_id": source_component_id,
                "task5_source_face_ids": face_ids,
                "source_frame_entity_ids": source_component_evidence[
                    "source_entity_ids"
                ],
            },
        )
    samples = sorted(sample for face in ordered for sample in face.samples_mm)
    node_degree_signature = sorted(
        len(graph.get(face.face_id, set()) & set(face_ids)) for face in ordered
    )
    by_id = {face.face_id: face for face in ordered}
    edge_count = 0
    for face in ordered:
        for neighbor in sorted(graph.get(face.face_id, set())):
            if neighbor in by_id and face.face_id < neighbor:
                edge_count += 1
    ordered_by_area = sorted(
        ordered, key=lambda face: (-face.area_mm2, face.face_id)
    )
    side_face_ids = sorted(face.face_id for face in ordered_by_area[:2])
    representative_samples = sorted(
        sample
        for face in ordered_by_area[:2]
        for sample in face.samples_mm
    )
    # The two largest authenticated faces are the pressure/suction material
    # sides.  Root and edge transition patches can cross a periodic seam in
    # their parameterization, so their circular sample envelope is not a valid
    # blade-collision proxy.  Use the side pair that defines the actual blade
    # occupancy while retaining every component face for topology/provenance.
    angular_envelope = _component_angular_envelope(
        [by_id[face_id] for face_id in side_face_ids]
    )
    angle_deg = float(angular_envelope["center_angle_deg"])
    root_edge_face_ids = sorted(set(face_ids) - set(side_face_ids))
    component_completeness = {
        "status": (
            "COMPLETE"
            if len(side_face_ids) == 2 and len(root_edge_face_ids) >= 2
            else "INCOMPLETE"
        ),
        "minimum_face_count": 4,
        "face_count": len(ordered),
        "blade_side_face_ids": side_face_ids,
        "root_edge_face_ids": root_edge_face_ids,
        "checks": {
            "two_large_blade_side_faces": len(side_face_ids) == 2,
            "root_edge_closure_face_count_at_least_two": len(root_edge_face_ids)
            >= 2,
        },
        "role_method": "two_largest_local_faces_then_exact_adjacent_root_edge_faces",
    }
    upstream_completeness = source_component_evidence.get("component_completeness")
    if upstream_completeness is not None and upstream_completeness != component_completeness:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            "source-frame and periodic component completeness evidence disagree",
            evidence={
                "source_component_id": source_component_id,
                "source_frame_component_completeness": upstream_completeness,
                "periodic_component_completeness": component_completeness,
            },
        )
    if component_completeness["status"] != "COMPLETE":
        raise PeriodicBladeRecoveryError(
            "v116_representative_blade_selection_failed",
            "periodic component is incomplete for closed section provenance",
            evidence={
                "source_component_id": source_component_id,
                "component_completeness": component_completeness,
            },
        )
    role_signature = [
        ["blade_side", len(side_face_ids)],
        ["blade_root_or_edge", len(root_edge_face_ids)],
    ]
    graph_payload = {
        "face_count": len(ordered),
        "node_degree_sequence": node_degree_signature,
        "edge_count": edge_count,
    }
    return {
        "source_component_id": source_component_id,
        "source_component_evidence": source_component_evidence,
        "source_face_ids": face_ids,
        "face_count": len(ordered),
        "component_completeness": component_completeness,
        "seed_rotational_group_ids": list(
            source_component_evidence.get("seed_rotational_group_ids", [])
        ),
        "authenticated_population_count": source_component_evidence.get(
            "authenticated_population_count"
        ),
        "face_role_signature": role_signature,
        "source_face_signature_inventory": sorted(
            Counter(face.signature for face in ordered).items()
        ),
        "adjacency_graph_signature": hashlib.sha256(
            json.dumps(graph_payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
        "instance_angle_deg": _round(angle_deg, 12),
        "canonical_frame_phase_deg": _round(angle_deg, 12),
        "source_frame_phase_deg": _round(
            _weighted_angle_mean(
                [face.source_frame_phase_deg for face in ordered],
                [face.area_mm2 for face in ordered],
            ),
            12,
        ),
        "phase_frame_evidence": dict(ordered[0].phase_frame_evidence),
        "surface_samples_mm": [list(point) for point in samples],
        "surface_sample_count": len(samples),
        "representative_surface_samples_mm": [
            list(point) for point in representative_samples
        ],
        "representative_surface_sample_count": len(representative_samples),
        "streamwise_extent_mm": _round(
            max(face.streamwise_bounds_mm[1] for face in ordered)
            - min(face.streamwise_bounds_mm[0] for face in ordered),
            6,
        ),
        "inlet_location_mm": _round(
            min(face.streamwise_bounds_mm[0] for face in ordered), 6
        ),
        "radial_support_range_mm": [
            _round(min(face.radial_bounds_mm[0] for face in ordered), 6),
            _round(max(face.radial_bounds_mm[1] for face in ordered), 6),
        ],
        "axial_support_range_mm": [
            _round(min(face.axial_bounds_mm[0] for face in ordered), 6),
            _round(max(face.axial_bounds_mm[1] for face in ordered), 6),
        ],
        "wrap_deg": _round(median(face.wrap_deg for face in ordered), 9),
        "angular_span_deg": angular_envelope["span_deg"],
        "angular_envelope_deg": angular_envelope,
        "total_face_area_mm2": _round(sum(face.area_mm2 for face in ordered), 6),
    }


def _component_angular_envelope(faces: Sequence[_Face]) -> dict[str, Any]:
    reference_deg = _weighted_angle_mean(
        [face.instance_angle_deg for face in faces],
        [max(face.area_mm2, 1.0e-12) for face in faces],
    )
    intervals = []
    for face in faces:
        center_offset = _wrap(face.instance_angle_deg - reference_deg, 360.0)
        half_span = 0.5 * face.angular_span_deg
        intervals.append((center_offset - half_span, center_offset + half_span))
    lower_offset = min(interval[0] for interval in intervals)
    upper_offset = max(interval[1] for interval in intervals)
    span_deg = min(360.0, upper_offset - lower_offset)
    center_offset = 0.5 * (lower_offset + upper_offset)
    center_deg = _normalize_angle(reference_deg + center_offset)
    start_deg = _normalize_angle(center_deg - 0.5 * span_deg)
    end_deg = _normalize_angle(center_deg + 0.5 * span_deg)
    return {
        "method": "circular_union_of_face_center_offsets_and_spans",
        "center_angle_deg": _round(center_deg, 9),
        "start_angle_deg": _round(start_deg, 9),
        "end_angle_deg": _round(end_deg, 9),
        "span_deg": _round(span_deg, 9),
        "wraps_zero": bool(span_deg < 360.0 and start_deg > end_deg),
        "face_interval_count": len(intervals),
    }


def _group_equivalent_components(
    components: Sequence[Mapping[str, Any]],
) -> list[list[dict[str, Any]]]:
    authenticated: dict[tuple[tuple[str, ...], int], list[dict[str, Any]]] = defaultdict(list)
    remaining = []
    for component in components:
        group_ids = component.get("seed_rotational_group_ids")
        population_count = component.get("authenticated_population_count")
        if (
            isinstance(group_ids, list)
            and group_ids
            and all(isinstance(item, str) and item for item in group_ids)
            and isinstance(population_count, int)
            and not isinstance(population_count, bool)
            and population_count >= 2
        ):
            authenticated[(tuple(sorted(group_ids)), population_count)].append(
                dict(component)
            )
        else:
            remaining.append(component)

    groups: list[list[dict[str, Any]]] = []
    for key, group in sorted(authenticated.items()):
        if len(group) > key[1]:
            raise PeriodicBladeRecoveryError(
                "v116_periodic_face_signature_contract_invalid",
                "authenticated seed population contains more components than its measured count",
                evidence={
                    "seed_rotational_group_ids": list(key[0]),
                    "authenticated_population_count": key[1],
                    "source_component_ids": sorted(
                        item["source_component_id"] for item in group
                    ),
                },
            )
        groups.append(sorted(group, key=_component_intrinsic_sort_key))

    fallback_groups: list[list[dict[str, Any]]] = []
    for raw_component in sorted(remaining, key=_component_intrinsic_sort_key):
        component = dict(raw_component)
        compatible = [
            group
            for group in fallback_groups
            if all(_components_equivalent(component, member) for member in group)
        ]
        if not compatible:
            fallback_groups.append([component])
            continue
        selected = min(
            compatible,
            key=lambda group: (
                max(
                    _component_similarity_distance(component, member)
                    for member in group
                ),
                tuple(_component_intrinsic_sort_key(member) for member in group),
            ),
        )
        selected.append(component)

    groups.extend(fallback_groups)

    for group in groups:
        group.sort(key=_component_intrinsic_sort_key)
    groups.sort(
        key=lambda group: tuple(_component_intrinsic_sort_key(item) for item in group)
    )
    return groups


def _component_intrinsic_sort_key(component: Mapping[str, Any]) -> tuple[Any, ...]:
    aligned_samples = sorted(
        _rotate_point_about_z(
            _point(point, "component surface sample"),
            -float(component["instance_angle_deg"]),
        )
        for point in component["surface_samples_mm"]
    )
    return (
        _stable_json(component["face_role_signature"]),
        str(component["adjacency_graph_signature"]),
        round(float(component["streamwise_extent_mm"]), 9),
        round(float(component["inlet_location_mm"]), 9),
        tuple(round(float(value), 9) for value in component["radial_support_range_mm"]),
        tuple(round(float(value), 9) for value in component["axial_support_range_mm"]),
        round(float(component["wrap_deg"]), 9),
        round(_normalize_angle(float(component["instance_angle_deg"])), 9),
        tuple(tuple(round(value, 9) for value in point) for point in aligned_samples),
    )


def _component_similarity_distance(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> float:
    values = [
        abs(
            float(first["streamwise_extent_mm"]) - float(second["streamwise_extent_mm"])
        ),
        abs(float(first["inlet_location_mm"]) - float(second["inlet_location_mm"])),
        abs(float(first["wrap_deg"]) - float(second["wrap_deg"])),
    ]
    for key in ("radial_support_range_mm", "axial_support_range_mm"):
        values.extend(
            abs(float(left) - float(right))
            for left, right in zip(first[key], second[key], strict=True)
        )
    return max(values)


def _components_equivalent(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    if first["face_role_signature"] != second["face_role_signature"]:
        return False
    if first["adjacency_graph_signature"] != second["adjacency_graph_signature"]:
        return False
    comparisons = (
        (
            float(first["streamwise_extent_mm"]),
            float(second["streamwise_extent_mm"]),
            0.05,
            0.08,
        ),
        (
            float(first["inlet_location_mm"]),
            float(second["inlet_location_mm"]),
            0.05,
            0.02,
        ),
        (float(first["wrap_deg"]), float(second["wrap_deg"]), 0.25, 0.08),
    )
    if any(
        not _close(left, right, absolute, relative)
        for left, right, absolute, relative in comparisons
    ):
        return False
    for key in ("radial_support_range_mm", "axial_support_range_mm"):
        if any(
            not _close(float(left), float(right), 0.05, 0.02)
            for left, right in zip(first[key], second[key], strict=True)
        ):
            return False
    return True


def _measure_lattice(angles: Sequence[float], tolerance_deg: float) -> dict[str, Any]:
    normalized = sorted(_normalize_angle(angle) for angle in angles)
    count = len(normalized)
    nominal_pitch = 360.0 / count
    gaps = [normalized[index + 1] - normalized[index] for index in range(count - 1)] + [
        normalized[0] + 360.0 - normalized[-1]
    ]
    pitch_deg = median(gaps)
    phase_candidates = [
        _normalize_period(angle - index * nominal_pitch, nominal_pitch)
        for index, angle in enumerate(normalized)
    ]
    phase_deg = _circular_mean_mod(phase_candidates, nominal_pitch)
    gap_residuals = [gap - nominal_pitch for gap in gaps]
    maximum_gap_residual = max(abs(value) for value in gap_residuals)
    rms_gap_residual = math.sqrt(sum(value * value for value in gap_residuals) / count)
    closure_residual = abs(count * pitch_deg - 360.0)
    return {
        "pitch_deg": _round(pitch_deg, 9),
        "nominal_pitch_deg": _round(nominal_pitch, 9),
        "phase_deg": _round(phase_deg, 9),
        "closure": {
            "measured_gaps_deg": [_round(value, 9) for value in gaps],
            "minimum_gap_deg": _round(min(gaps), 9),
            "maximum_gap_deg": _round(max(gaps), 9),
            "pitch_rms_residual_deg": _round(rms_gap_residual, 9),
            "maximum_gap_residual_deg": _round(maximum_gap_residual, 9),
            "closure_residual_deg": _round(closure_residual, 9),
            "tolerance_deg": _round(tolerance_deg, 9),
            "within_tolerance": maximum_gap_residual <= tolerance_deg
            and closure_residual <= tolerance_deg,
        },
    }


def _classify_populations(
    populations: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    if len(populations) == 1:
        return (
            populations[0],
            None,
            {
                "method": "single_connected_periodic_family_is_main",
                "splitter_fabricated": False,
            },
        )
    first, second = populations
    basis = None
    first_extent = float(first["streamwise_extent_mm"])
    second_extent = float(second["streamwise_extent_mm"])
    if not _close(first_extent, second_extent, 0.05, 0.05):
        main, splitter = (
            (first, second) if first_extent > second_extent else (second, first)
        )
        basis = "greater_streamwise_extent"
    else:
        first_inlet = float(first["inlet_location_mm"])
        second_inlet = float(second["inlet_location_mm"])
        if not _close(first_inlet, second_inlet, 0.05, 0.02):
            main, splitter = (
                (first, second) if first_inlet < second_inlet else (second, first)
            )
            basis = "earlier_inlet_location"
        else:
            first_support = _support_extent(first)
            second_support = _support_extent(second)
            if not _close(first_support, second_support, 0.05, 0.03):
                main, splitter = (
                    (first, second)
                    if first_support > second_support
                    else (second, first)
                )
                basis = "greater_radial_axial_support_range"
            else:
                raise PeriodicBladeRecoveryError(
                    "v116_periodic_population_ambiguous",
                    "main and splitter populations are indistinguishable by extent, inlet, and support range",
                    evidence={
                        "first_population_id": first["population_id"],
                        "second_population_id": second["population_id"],
                    },
                )
    return (
        main,
        splitter,
        {
            "method": "streamwise_extent_then_inlet_then_support_range",
            "main_selection_basis": basis,
            "main_streamwise_extent_mm": main["streamwise_extent_mm"],
            "splitter_streamwise_extent_mm": splitter["streamwise_extent_mm"],
            "main_inlet_location_mm": main["inlet_location_mm"],
            "splitter_inlet_location_mm": splitter["inlet_location_mm"],
        },
    )


def _name_population(population: dict[str, Any], name: str) -> None:
    population["population_id"] = name
    population["classification"] = name
    population["representative"]["population_id"] = name
    for index, instance in enumerate(population["instances"]):
        instance["population_id"] = name
        instance["instance_id"] = f"{name}_instance_{index:04d}"


def _set_relative_phase(
    main: dict[str, Any],
    splitter: dict[str, Any] | None,
    *,
    consistency_tolerance_deg: float,
) -> None:
    main["phase_relative_to_main_deg"] = 0.0
    main["relative_phase_evidence"] = {
        "status": "reference_population",
        "scalar_phase_defined": True,
        "offset_distribution_deg": [0.0],
        "tolerance_deg": _round(consistency_tolerance_deg, 9),
        "source_frame_phase_relative_to_main_deg": 0.0,
        "canonical_frame_phase_relative_to_main_deg": 0.0,
        "handedness": main["phase_frame_evidence"]["handedness"],
        "source_axis_direction": main["phase_frame_evidence"]["source_axis_direction"],
        "transform_rule": main["phase_frame_evidence"]["transform_rule"],
    }
    if splitter is None:
        return
    main_pitch = float(main["nominal_pitch_deg"])
    offsets = sorted(
        _normalize_period(
            float(instance["measured_angle_deg"]) - float(main["phase_deg"]), main_pitch
        )
        for instance in splitter["instances"]
    )
    relative_phase = _circular_mean_mod(offsets, main_pitch)
    source_offsets = sorted(
        _normalize_period(
            float(instance["source_frame_phase_deg"])
            - float(main["source_frame_phase_deg"]),
            main_pitch,
        )
        for instance in splitter["instances"]
    )
    source_relative_phase = _circular_mean_mod(source_offsets, main_pitch)
    residuals = [_wrap(offset - relative_phase, main_pitch) for offset in offsets]
    maximum_residual = max(abs(residual) for residual in residuals)
    scalar_phase_defined = maximum_residual <= consistency_tolerance_deg
    splitter["relative_phase_evidence"] = {
        "status": (
            "lattice_consistent_scalar"
            if scalar_phase_defined
            else "ambiguous_offset_distribution"
        ),
        "scalar_phase_defined": scalar_phase_defined,
        "main_lattice_pitch_deg": _round(main_pitch, 9),
        "offset_distribution_deg": [_round(offset, 9) for offset in offsets],
        "offset_residuals_deg": [_round(residual, 9) for residual in residuals],
        "maximum_offset_residual_deg": _round(maximum_residual, 9),
        "tolerance_deg": _round(consistency_tolerance_deg, 9),
        "source_frame_phase_relative_to_main_deg": _round(
            source_relative_phase, 9
        ),
        "canonical_frame_phase_relative_to_main_deg": _round(relative_phase, 9),
        "source_frame_offset_distribution_deg": [
            _round(offset, 9) for offset in source_offsets
        ],
        "handedness": splitter["phase_frame_evidence"]["handedness"],
        "source_axis_direction": splitter["phase_frame_evidence"][
            "source_axis_direction"
        ],
        "transform_rule": splitter["phase_frame_evidence"]["transform_rule"],
    }
    if not scalar_phase_defined:
        splitter["phase_relative_to_main_deg"] = None
        splitter["passage_bisector_deviation_deg"] = None
        return
    splitter["phase_relative_to_main_deg"] = _round(relative_phase, 9)
    splitter["passage_bisector_deviation_deg"] = _round(
        _wrap(relative_phase - 0.5 * main_pitch, main_pitch), 9
    )


def _normalize_face(record: Mapping[str, Any], *, index: int) -> _Face:
    if not isinstance(record, Mapping):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face signature at index {index} must be a mapping",
        )
    missing = sorted(_STRICT_FACE_FIELDS - record.keys())
    if missing:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face signature at index {index} is missing strict Task 5 fields: {', '.join(missing)}",
            evidence={"record_index": index, "missing_fields": missing},
        )

    face_id = str(record["source_face_id"])
    signature = str(record["signature_hash"])
    if not face_id or not signature:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face signature at index {index} requires non-empty source_face_id and signature_hash",
        )
    area = _number(record["area_mm2"], f"area for {face_id}")
    if area <= 0.0:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"area for {face_id} must be positive",
        )
    if record["streamwise_coordinate"] != "canonical_radius_mm":
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face {face_id} uses unsupported streamwise coordinate; expected canonical_radius_mm",
        )

    samples_value = record["canonical_surface_samples_mm"]
    if (
        not isinstance(samples_value, Sequence)
        or isinstance(samples_value, (str, bytes))
        or not samples_value
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face {face_id} requires non-empty canonical surface samples",
        )
    samples = tuple(
        sorted(
            _point(point, f"canonical surface sample for {face_id}")
            for point in samples_value
        )
    )

    is_periodic = record["is_periodic"]
    blade_related = record["blade_related"]
    if not isinstance(is_periodic, bool) or not isinstance(blade_related, bool):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"periodic and blade-related membership for {face_id} must be boolean",
        )
    membership = record["periodic_membership"]
    if not isinstance(membership, Mapping):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"periodic_membership for {face_id} must be a mapping",
        )
    membership_missing = sorted(
        {"status", "group_id", "closure_within_tolerance", "method"} - membership.keys()
    )
    if membership_missing:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"periodic_membership for {face_id} is missing: {', '.join(membership_missing)}",
        )
    group_id = membership["group_id"]
    closure_accepted = membership["closure_within_tolerance"]
    if is_periodic and blade_related:
        if (
            membership["status"] != "accepted_periodic_blade_related"
            or not isinstance(group_id, str)
            or not group_id
            or closure_accepted is not True
        ):
            raise PeriodicBladeRecoveryError(
                "v116_periodic_face_signature_contract_invalid",
                f"face {face_id} lacks accepted upstream periodic blade membership and closure evidence",
            )
    elif group_id is not None or closure_accepted is not False:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"non-candidate face {face_id} carries inconsistent accepted periodic membership",
        )
    for evidence_field in ("wrap_evidence", "angular_span_evidence"):
        evidence = record[evidence_field]
        if not isinstance(evidence, Mapping) or not str(evidence.get("method", "")):
            raise PeriodicBladeRecoveryError(
                "v116_periodic_face_signature_contract_invalid",
                f"{evidence_field} for {face_id} requires an explicit method",
            )

    coarse_component = _normalize_coarse_component_evidence(
        record["coarse_component"],
        face_id=face_id,
        require_measured_residual=is_periodic and blade_related,
    )

    angular_span = _number(record["angular_span_deg"], f"angular span for {face_id}")
    if not 0.0 <= angular_span <= 360.0:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"angular span for {face_id} must be within [0, 360] degrees",
        )
    phase_frame_evidence = _normalize_phase_frame_evidence(
        record["phase_frame_evidence"], face_id=face_id
    )
    canonical_phase = _normalize_angle(
        _number(record["canonical_frame_phase_deg"], f"canonical phase for {face_id}")
    )
    legacy_phase = _normalize_angle(
        _number(record["centroid_angle_deg"], f"angle for {face_id}")
    )
    if abs(_wrap(canonical_phase - legacy_phase, 360.0)) > 1.0e-7:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"canonical and legacy phase disagree for {face_id}",
        )
    seed_certification = record.get("periodic_seed_certification")
    periodic_seed_certified = bool(
        isinstance(seed_certification, Mapping)
        and seed_certification.get("status") == "ACCEPTED"
        and seed_certification.get("accepted_as_periodic_blade_seed") is True
        and seed_certification.get("classification")
        == "authenticated_periodic_blade_face_seed"
        and isinstance(seed_certification.get("source_entity_ids"), Sequence)
        and face_id in seed_certification["source_entity_ids"]
    )
    return _Face(
        face_id=face_id,
        signature=signature,
        area_mm2=area,
        instance_angle_deg=canonical_phase,
        source_frame_phase_deg=_normalize_angle(
            _number(record["source_frame_phase_deg"], f"source phase for {face_id}")
        ),
        canonical_frame_phase_deg=canonical_phase,
        phase_frame_evidence=phase_frame_evidence,
        samples_mm=samples,
        streamwise_bounds_mm=_strict_bounds(
            record["streamwise_bounds_mm"], f"streamwise bounds for {face_id}"
        ),
        radial_bounds_mm=_strict_bounds(
            record["radial_bounds_mm"], f"radial bounds for {face_id}"
        ),
        axial_bounds_mm=_strict_bounds(
            record["axial_bounds_mm"], f"axial bounds for {face_id}"
        ),
        wrap_deg=_number(record["wrap_deg"], f"wrap for {face_id}"),
        angular_span_deg=angular_span,
        is_periodic=is_periodic,
        blade_related=blade_related,
        periodic_group_id=group_id,
        coarse_component_id=coarse_component["source_component_id"],
        coarse_component_evidence=coarse_component,
        periodic_seed_certified=periodic_seed_certified,
    )


def _normalize_coarse_component_evidence(
    value: Any, *, face_id: str, require_measured_residual: bool
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"face {face_id} requires typed source-frame component evidence",
        )
    required = {
        "source_component_id",
        "source_entity_ids",
        "confidence",
        "coordinate_frame",
        "units",
        "tolerance",
        "residual",
        "provenance",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component evidence for {face_id} is missing: {', '.join(missing)}",
        )
    component_id = value["source_component_id"]
    source_ids = value["source_entity_ids"]
    if not isinstance(component_id, str) or not component_id:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component id for {face_id} must be non-empty",
        )
    if (
        not isinstance(source_ids, Sequence)
        or isinstance(source_ids, (str, bytes))
        or not source_ids
        or any(not isinstance(item, str) or not item for item in source_ids)
        or face_id not in source_ids
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component for {face_id} requires exact non-empty source entity ids",
        )
    confidence = value["confidence"]
    units = value["units"]
    tolerance = value["tolerance"]
    residual = value["residual"]
    provenance = value["provenance"]
    if (
        not isinstance(confidence, Mapping)
        or confidence.get("level") != "deterministic_topology_component"
        or confidence.get("status") != "ACCEPTED"
        or not isinstance(confidence.get("score"), (int, float))
        or isinstance(confidence.get("score"), bool)
        or not math.isfinite(float(confidence["score"]))
        or not 0.0 <= float(confidence["score"]) <= 1.0
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component confidence for {face_id} is missing",
        )
    if value["coordinate_frame"] != "canonical_cylindrical_r_theta_z":
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component frame for {face_id} is unsupported",
        )
    if not isinstance(units, Mapping) or units.get("linear") != "mm":
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component units for {face_id} are invalid",
        )
    if (
        not isinstance(tolerance, Mapping)
        or not tolerance
        or any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            or float(item) <= 0.0
            for item in tolerance.values()
        )
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component tolerance for {face_id} is missing",
        )
    if not isinstance(residual, Mapping) or not residual:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component residual for {face_id} is missing",
        )
    numeric_residuals = [
        float(item)
        for item in residual.values()
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    ]
    if (
        require_measured_residual
        and (
            not numeric_residuals
            or not all(math.isfinite(item) for item in numeric_residuals)
        )
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component residual for {face_id} requires finite measurements",
        )
    if numeric_residuals and not all(math.isfinite(item) for item in numeric_residuals):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component residual for {face_id} contains non-finite values",
        )
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("authority") != "uploaded_step_brep_topology"
        or set(provenance.get("source_entity_ids", ())) != set(source_ids)
        or _contains_placeholder(provenance)
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"coarse component provenance for {face_id} is invalid",
        )
    return {
        "source_component_id": component_id,
        "source_entity_ids": sorted(set(source_ids)),
        "confidence": dict(confidence),
        "coordinate_frame": value["coordinate_frame"],
        "units": dict(units),
        "tolerance": dict(tolerance),
        "residual": dict(residual),
        "provenance": dict(provenance),
        **(
            {"component_completeness": dict(value["component_completeness"])}
            if isinstance(value.get("component_completeness"), Mapping)
            else {}
        ),
        **(
            {
                "seed_rotational_group_ids": sorted(
                    set(value["seed_rotational_group_ids"])
                ),
                "authenticated_population_count": int(
                    value["authenticated_population_count"]
                ),
            }
            if isinstance(value.get("seed_rotational_group_ids"), Sequence)
            and not isinstance(value.get("seed_rotational_group_ids"), (str, bytes))
            and value.get("seed_rotational_group_ids")
            and isinstance(value.get("authenticated_population_count"), int)
            else {}
        ),
    }


def _normalize_phase_frame_evidence(value: Any, *, face_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"phase frame evidence for {face_id} is missing",
        )
    matrix = value.get("source_to_canonical_matrix")
    if (
        value.get("handedness") != "right_handed"
        or value.get("transform_rule")
        != "source_axis_local_basis_then_rigid_source_to_canonical"
        or not isinstance(value.get("source_axis_origin_mm"), Sequence)
        or len(value["source_axis_origin_mm"]) != 3
        or not isinstance(value.get("source_axis_direction"), Sequence)
        or len(value["source_axis_direction"]) != 3
        or not isinstance(matrix, Sequence)
        or len(matrix) != 4
        or any(not isinstance(row, Sequence) or len(row) != 4 for row in matrix)
    ):
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"phase frame evidence for {face_id} is invalid",
        )
    numeric_matrix = [[_number(item, f"phase transform for {face_id}") for item in row] for row in matrix]
    rotation = numeric_matrix[:3]
    determinant = (
        rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )
    if abs(determinant - 1.0) > 1.0e-7:
        raise PeriodicBladeRecoveryError(
            "v116_periodic_face_signature_contract_invalid",
            f"phase transform for {face_id} is not right-handed",
        )
    return {
        "source_axis_origin_mm": [float(item) for item in value["source_axis_origin_mm"]],
        "source_axis_direction": [float(item) for item in value["source_axis_direction"]],
        "source_to_canonical_matrix": numeric_matrix,
        "handedness": value["handedness"],
        "source_frame_handedness": value.get("source_frame_handedness", "right_handed"),
        "source_frame_phase_rule": value.get(
            "source_frame_phase_rule", "source_global_xy_azimuth_about_axis_origin"
        ),
        "canonical_frame_phase_rule": value.get(
            "canonical_frame_phase_rule", "canonical_xy_azimuth_about_positive_z"
        ),
        "transform_rule": value["transform_rule"],
    }


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "placeholder" in value.strip().lower()
    if isinstance(value, Mapping):
        return any(
            (str(key).lower() == "placeholder" and item is not False)
            or _contains_placeholder(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_placeholder(item) for item in value)
    return False


def _normalize_adjacency(adjacency: Mapping[str, Iterable[str]]) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = {}
    for raw_face_id, raw_neighbors in adjacency.items():
        face_id = str(raw_face_id)
        normalized.setdefault(face_id, set())
        for raw_neighbor in raw_neighbors:
            neighbor = str(raw_neighbor)
            if neighbor == face_id:
                continue
            normalized[face_id].add(neighbor)
            normalized.setdefault(neighbor, set()).add(face_id)
    return normalized


def _validate_options(**options: float | int) -> None:
    if options["minimum_instance_count"] < 2:
        raise ValueError("minimum_instance_count must be at least two")
    if options["minimum_component_face_count"] < 4:
        raise ValueError("minimum_component_face_count must be at least four")
    if options["closure_tolerance_deg"] < 0.0:
        raise ValueError("closure_tolerance_deg must be non-negative")
    if options["collision_tolerance_deg"] < 0.0:
        raise ValueError("collision_tolerance_deg must be non-negative")
    if options["sample_limit_per_component"] < 1:
        raise ValueError("sample_limit_per_component must be positive")


def _nearest_lattice_site(
    angle_deg: float,
    phase_deg: float,
    pitch_deg: float,
    count: int,
) -> tuple[int, float, float]:
    candidates = [
        (_normalize_angle(phase_deg + index * pitch_deg), index)
        for index in range(count)
    ]
    expected, index = min(
        candidates, key=lambda item: (abs(_wrap(angle_deg - item[0], 360.0)), item[1])
    )
    return index, expected, _wrap(angle_deg - expected, 360.0)


def _median_range(components: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    return [
        _round(median(float(component[key][index]) for component in components), 6)
        for index in range(2)
    ]


def _support_extent(population: Mapping[str, Any]) -> float:
    radial = population["radial_support_range_mm"]
    axial = population["axial_support_range_mm"]
    return float(radial[1]) - float(radial[0]) + float(axial[1]) - float(axial[0])


def _ranges_overlap(first: Sequence[float], second: Sequence[float]) -> bool:
    return min(float(first[1]), float(second[1])) >= max(
        float(first[0]), float(second[0])
    )


def _close(first: float, second: float, absolute: float, relative: float) -> bool:
    return abs(first - second) <= max(
        absolute, relative * max(abs(first), abs(second), 1.0)
    )


def _weighted_angle_mean(
    angles_deg: Sequence[float], weights: Sequence[float]
) -> float:
    x = sum(
        weight * math.cos(math.radians(angle))
        for angle, weight in zip(angles_deg, weights, strict=True)
    )
    y = sum(
        weight * math.sin(math.radians(angle))
        for angle, weight in zip(angles_deg, weights, strict=True)
    )
    if math.hypot(x, y) <= 1.0e-12:
        return _normalize_angle(min(angles_deg))
    return _normalize_angle(math.degrees(math.atan2(y, x)))


def _circular_mean_mod(values: Sequence[float], period: float) -> float:
    if not values:
        raise ValueError("circular mean requires at least one value")
    angles = [
        2.0 * math.pi * _normalize_period(value, period) / period for value in values
    ]
    x = sum(math.cos(angle) for angle in angles)
    y = sum(math.sin(angle) for angle in angles)
    if math.hypot(x, y) <= 1.0e-12:
        return _normalize_period(min(values), period)
    return _normalize_period(period * math.atan2(y, x) / (2.0 * math.pi), period)


def _bounded_samples(
    samples: Sequence[tuple[float, float, float]],
    limit: int,
) -> list[tuple[float, float, float]]:
    points = list(samples)
    if len(points) <= limit:
        return points

    centroid = tuple(
        math.fsum(point[axis] for point in points) / len(points)
        for axis in range(3)
    )
    centroid_distances = [
        _squared_distance(point, centroid) for point in points
    ]
    seed = min(
        range(len(points)), key=lambda index: (centroid_distances[index], index)
    )
    selected = [seed]
    selected_set = {seed}
    nearest_selected = [
        _squared_distance(point, points[seed]) for point in points
    ]
    while len(selected) < limit:
        candidate = max(
            (index for index in range(len(points)) if index not in selected_set),
            key=lambda index: (
                nearest_selected[index],
                centroid_distances[index],
                -index,
            ),
        )
        selected.append(candidate)
        selected_set.add(candidate)
        for index, point in enumerate(points):
            nearest_selected[index] = min(
                nearest_selected[index],
                _squared_distance(point, points[candidate]),
            )
    return [points[index] for index in selected]


def _squared_distance(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    return sum((first[axis] - second[axis]) ** 2 for axis in range(3))


def _symmetric_sample_rms(
    first: Sequence[tuple[float, float, float]],
    second: Sequence[tuple[float, float, float]],
) -> float:
    first_squared = [_nearest_squared_distance(point, second) for point in first]
    second_squared = [_nearest_squared_distance(point, first) for point in second]
    return math.sqrt(
        sum(first_squared + second_squared) / (len(first_squared) + len(second_squared))
    )


def _nearest_squared_distance(
    point: tuple[float, float, float],
    candidates: Sequence[tuple[float, float, float]],
) -> float:
    return min(
        (point[0] - candidate[0]) ** 2
        + (point[1] - candidate[1]) ** 2
        + (point[2] - candidate[2]) ** 2
        for candidate in candidates
    )


def _rotate_point_about_z(
    point: tuple[float, float, float], angle_deg: float
) -> tuple[float, float, float]:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        cosine * point[0] - sine * point[1],
        sine * point[0] + cosine * point[1],
        point[2],
    )


def _rotation_z_matrix(angle_deg: float) -> list[list[float]]:
    angle = math.radians(angle_deg)
    cosine = _round(math.cos(angle), 12)
    sine = _round(math.sin(angle), 12)
    return [
        [cosine, _round(-sine, 12), 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _strict_bounds(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError(f"{label} must contain [minimum, maximum]")
    first = _number(value[0], label)
    second = _number(value[1], label)
    if first > second:
        raise ValueError(f"{label} must be ordered [minimum, maximum]")
    return first, second


def _point(value: Any, label: str) -> tuple[float, float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 3
    ):
        raise ValueError(f"{label} must contain three coordinates")
    return tuple(_number(coordinate, label) for coordinate in value)  # type: ignore[return-value]


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_angle(angle_deg: float) -> float:
    return _normalize_period(angle_deg, 360.0)


def _normalize_period(value: float, period: float) -> float:
    normalized = value % period
    return 0.0 if math.isclose(normalized, period, abs_tol=1.0e-12) else normalized


def _wrap(value: float, period: float) -> float:
    wrapped = (value + 0.5 * period) % period - 0.5 * period
    return (
        0.5 * period
        if math.isclose(wrapped, -0.5 * period, abs_tol=1.0e-12)
        else wrapped
    )


def _round(value: float, digits: int) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0.0 else rounded
