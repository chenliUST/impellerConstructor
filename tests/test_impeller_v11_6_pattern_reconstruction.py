from __future__ import annotations

# ruff: noqa: E402

import copy
import hashlib
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import pytest

import part_rule_synthesis.impeller_v11_6_pattern_reconstruction as pattern_reconstruction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_6_axis_first_pipeline import (
    preserve_task8_reconstruction_authority,
    task8_reconstruction_evidence_hash,
)
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    build_parameter_inspection_contract,
    parameter_inspection_generation_id,
)
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph
from part_rule_synthesis.impeller_v11_6_pattern_reconstruction import (
    PatternReconstructionError,
    _measure_graph_collision_diagnostics,
    _surface_family_envelope,
    validate_and_decorate_pattern_reconstruction,
    validate_mapped_pattern_reconstruction,
)
from part_rule_synthesis.impeller_v11_6_step_audit import (
    _material_export_surface_graph,
    load_step_source,
)
from part_rule_synthesis.impeller_surface_graph_export import (
    triangulate_surface_graph,
)
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from step_fixtures import write_periodic_impeller_step


_SOURCE_SHA256 = "b" * 64
_UNSEALED_SOURCE_SOLID_ID = "unsealed-source-solid"


@lru_cache(maxsize=None)
def _runtime_graph(preset_id: str) -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def _rotation_z(angle_deg: float) -> list[list[float]]:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _rotate_point(point: list[float], angle_deg: float) -> list[float]:
    transform = _rotation_z(angle_deg)
    return [
        transform[row][0] * point[0]
        + transform[row][1] * point[1]
        + transform[row][2] * point[2]
        for row in range(3)
    ]


def _inject_authoritative_uv_overlap(graph: dict) -> None:
    population = graph["canonical_nurbs_parameterization"]["blade_population"]
    pitch = 360.0 / population["main_blade_count"]
    pressure_surfaces = {
        surface["blade_pair_index"]: surface
        for surface in graph["surfaces"]
        if surface.get("blade_class") == "main"
        and surface.get("role") == "blade_pressure"
    }
    representative_point = list(pressure_surfaces[0]["uv_grid"][0][0])
    for index, surface in sorted(pressure_surfaces.items()):
        surface["uv_grid"][0][0] = _rotate_point(
            representative_point, index * pitch
        )
        surface["uv_grid"][0][1] = _rotate_point(
            representative_point, (index + 1) * pitch
        )
    graph["generation_id"] = parameter_inspection_generation_id(graph)
    graph["parameter_inspection"] = build_parameter_inspection_contract(graph)


def _periodic_evidence(graph: dict, *, angular_span_deg: float = 1.0) -> dict:
    population_contract = graph["canonical_nurbs_parameterization"]["blade_population"]
    main_count = population_contract["main_blade_count"]
    splitter_count = population_contract["splitter_blade_count"]
    main_pitch = 360.0 / main_count
    splitter_phase = population_contract["splitter_phase_offset_pitch"] * main_pitch
    populations = [
        _population("main", main_count, phase_deg=0.0, angular_span_deg=angular_span_deg)
    ]
    if splitter_count:
        populations.append(
            _population(
                "splitter",
                splitter_count,
                phase_deg=splitter_phase,
                angular_span_deg=angular_span_deg,
            )
        )
    _bind_generated_envelopes(graph, populations)
    collision = {
        "method": "angular_sector_overlap_with_radial_axial_support",
        "collision_free": True,
        "collision_count": 0,
        "collision_status": "PASS",
        "source_topology_separated": True,
        "exact_brep_collision_checked": True,
        "exact_brep_collision_free": True,
        "minimum_angular_clearance_deg": None,
        "tolerance_deg": 1.0e-6,
        "collisions": [],
    }
    evidence = {
        "method": "periodic_connected_face_components_v1_1_6",
        "measurement_tolerance_mm": 1.0e-6,
        "main_blade_count": main_count,
        "splitter_blade_count": splitter_count,
        "main": populations[0],
        "splitter": populations[1] if splitter_count else None,
        "populations": populations,
        "closure_diagnostics": {
            "all_populations_closed": True,
            "maximum_gap_residual_deg": 0.0,
            "maximum_closure_residual_deg": 0.0,
            "tolerance_deg": 1.0e-6,
        },
        "collision_diagnostics": collision,
    }
    return evidence


def _population(
    blade_class: str,
    count: int,
    *,
    phase_deg: float,
    angular_span_deg: float,
) -> dict:
    pitch = 360.0 / count
    representative_component_id = f"source_{blade_class}_component_0000"
    representative_face_ids = [
        f"source_{blade_class}_0000_pressure",
        f"source_{blade_class}_0000_suction",
        f"source_{blade_class}_0000_leading",
        f"source_{blade_class}_0000_trailing",
    ]
    instances = []
    for index in range(count):
        measured_angle = (phase_deg + index * pitch) % 360.0
        source_component_id = f"source_{blade_class}_component_{index:04d}"
        source_face_ids = [
            f"source_{blade_class}_{index:04d}_{role}"
            for role in ("pressure", "suction", "leading", "trailing")
        ]
        component_evidence = _component_evidence(
            blade_class,
            index,
            count,
            source_component_id,
            source_face_ids,
        )
        instances.append(
            {
                "population_id": blade_class,
                "instance_id": f"{blade_class}_instance_{index:04d}",
                "source_component_id": source_component_id,
                "source_face_ids": source_face_ids,
                "source_component_evidence": component_evidence,
                "measured_angle_deg": measured_angle,
                "lattice_index": index,
                "expected_angle_deg": measured_angle,
                "pitch_residual_deg": 0.0,
                "rotation_from_representative_deg": index * pitch,
                "transform_from_representative": _rotation_z(index * pitch),
                "residual_to_representative_mm": 0.0,
                "angular_span_deg": angular_span_deg,
                "angular_envelope_deg": {
                    "method": "fixture_replaced_from_authoritative_graph",
                    "span_deg": angular_span_deg,
                },
                "radial_support_range_mm": [10.0, 50.0],
                "axial_support_range_mm": [0.0, 30.0],
            }
        )
    return {
        "population_id": blade_class,
        "classification": blade_class,
        "count": count,
        "pitch_deg": pitch,
        "nominal_pitch_deg": pitch,
        "phase_deg": phase_deg,
        "representative": {
            "population_id": blade_class,
            "source_component_id": representative_component_id,
            "source_face_ids": representative_face_ids,
            "source_component_evidence": copy.deepcopy(
                instances[0]["source_component_evidence"]
            ),
            "lattice_index": 0,
            "measured_angle_deg": phase_deg,
        },
        "instances": instances,
        "closure": {
            "within_tolerance": True,
            "maximum_gap_residual_deg": 0.0,
            "closure_residual_deg": 0.0,
        },
    }


def _component_evidence(
    blade_class: str,
    index: int,
    count: int,
    component_id: str,
    source_face_ids: list[str],
) -> dict:
    provenance = {
        "authority": "uploaded_step_brep_topology",
        "source_solid_shape_identity": _UNSEALED_SOURCE_SOLID_ID,
        "source_sha256": _SOURCE_SHA256,
        "source_entity_ids": list(source_face_ids),
        "signature_hashes": [],
        "digest_basis": "trusted_source_component_membership_v1",
        "component_digest_sha256": "0" * 64,
    }
    evidence = {
        "source_component_id": component_id,
        "source_entity_ids": list(source_face_ids),
        "confidence": {
            "level": "deterministic_topology_component",
            "score": 1.0,
            "status": "ACCEPTED",
        },
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm", "angular": "deg"},
        "tolerance": {
            "shared_edge_identity_tolerance_mm": 1.0e-12,
            "signature_linear_quantization_mm": 0.001,
        },
        "residual": {"transformed_sample_mm": 0.0},
        "component_completeness": {
            "status": "COMPLETE",
            "face_count": len(source_face_ids),
        },
        "seed_rotational_group_ids": [f"{blade_class}_rotational_group"],
        "authenticated_population_count": count,
        "provenance": provenance,
    }
    return evidence


def _authoritative_solid_subset(manifest: dict) -> dict:
    return {
        "authority": "source_step_brep",
        "source_sha256": manifest["sha256"],
        "solid_count": manifest["solid_count"],
        "shell_count": manifest["shell_count"],
        "face_count": manifest["face_count"],
        "edge_count": manifest["edge_count"],
        "vertex_count": manifest["vertex_count"],
        "closed_solid": manifest["closed_solid"],
        "volume_mm3": float(manifest["volume_mm3"]),
        "surface_area_mm2": float(manifest["surface_area_mm2"]),
        "centroid_mm": [float(value) for value in manifest["centroid_mm"]],
        "bounds_mm": {
            "minimum": [float(value) for value in manifest["bounds_mm"]["minimum"]],
            "maximum": [float(value) for value in manifest["bounds_mm"]["maximum"]],
        },
        "surface_type_inventory": dict(
            sorted(manifest["surface_type_inventory"].items())
        ),
        "faces": sorted(
            manifest["faces"],
            key=lambda face: (
                face["source_entity_index"],
                face["face_id"],
            ),
        ),
        "adjacency": {
            face_id: sorted(neighbors)
            for face_id, neighbors in sorted(manifest["adjacency"].items())
        },
    }


def _derived_source_solid_identity(manifest: dict) -> str:
    return "source-solid-sha256:" + _digest(
        {
            "digest_basis": "load_step_source_solid_shape_identity_v1",
            **_authoritative_solid_subset(manifest),
        }
    )


def _trusted_manifest_digest(manifest: dict) -> str:
    return _digest(
        {
            "digest_basis": "load_step_source_authoritative_solid_subset_v1",
            **_authoritative_solid_subset(manifest),
            "source_solid_shape_identity": _derived_source_solid_identity(manifest),
        }
    )


def _trusted_face_signatures(manifest: dict) -> dict[str, str]:
    return {
        face["face_id"]: _digest(
            {
                "digest_basis": "trusted_source_face_record_with_adjacency_v1",
                "source_sha256": manifest["sha256"],
                "source_solid_shape_identity": _derived_source_solid_identity(
                    manifest
                ),
                "face": face,
                "adjacent_face_ids": sorted(manifest["adjacency"][face["face_id"]]),
            }
        )
        for face in manifest["faces"]
    }


def _component_digest_basis(evidence: dict, trusted_manifest: dict) -> dict:
    source_ids = sorted(evidence["source_entity_ids"])
    membership = set(source_ids)
    signatures = _trusted_face_signatures(trusted_manifest)
    return {
        "digest_basis": "trusted_source_component_membership_v1",
        "trusted_source_manifest_digest_sha256": _trusted_manifest_digest(
            trusted_manifest
        ),
        "source_sha256": trusted_manifest["sha256"],
        "source_solid_shape_identity": _derived_source_solid_identity(
            trusted_manifest
        ),
        "source_component_id": evidence["source_component_id"],
        "source_entity_ids": source_ids,
        "face_signature_sha256_by_id": {
            face_id: signatures[face_id] for face_id in source_ids
        },
        "component_adjacency": {
            face_id: [
                neighbor
                for neighbor in sorted(trusted_manifest["adjacency"][face_id])
                if neighbor in membership
            ]
            for face_id in source_ids
        },
    }


def _seal_component_evidence(evidence: dict, trusted_manifest: dict) -> None:
    provenance = evidence["provenance"]
    basis = _component_digest_basis(evidence, trusted_manifest)
    provenance.update(
        {
            "source_solid_shape_identity": _derived_source_solid_identity(
                trusted_manifest
            ),
            "source_sha256": trusted_manifest["sha256"],
            "source_entity_ids": list(evidence["source_entity_ids"]),
            "signature_hashes": sorted(
                basis["face_signature_sha256_by_id"].values()
            ),
            "digest_basis": "trusted_source_component_membership_v1",
            "component_digest_sha256": _digest(basis),
        }
    )


def _periodic_source_ids(evidence: dict) -> list[str]:
    return sorted(
        face_id
        for population in evidence["populations"]
        for instance in population["instances"]
        for face_id in instance["source_face_ids"]
    )


def _periodic_digest_population(population: dict) -> dict:
    return {
        "population_id": population["population_id"],
        "count": population["count"],
        "pitch_deg": float(population["pitch_deg"]),
        "phase_deg": float(population["phase_deg"]) % 360.0,
        "representative": {
            "source_component_id": population["representative"][
                "source_component_id"
            ],
            "source_face_ids": sorted(
                population["representative"]["source_face_ids"]
            ),
            "lattice_index": population["representative"]["lattice_index"],
        },
        "instances": [
            {
                "instance_id": instance["instance_id"],
                "source_component_id": instance["source_component_id"],
                "source_face_ids": sorted(instance["source_face_ids"]),
                "lattice_index": instance["lattice_index"],
                "phase_deg": float(instance["measured_angle_deg"]) % 360.0,
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


def _seal_periodic_evidence(evidence: dict, trusted_manifest: dict) -> None:
    for population in evidence["populations"]:
        for instance in population["instances"]:
            component = instance["source_component_evidence"]
            component["source_component_id"] = instance["source_component_id"]
            component["source_entity_ids"] = list(instance["source_face_ids"])
            component["provenance"]["source_entity_ids"] = list(
                instance["source_face_ids"]
            )
            _seal_component_evidence(component, trusted_manifest)
        representative_index = population["representative"]["lattice_index"]
        population["representative"]["source_component_evidence"] = copy.deepcopy(
            population["instances"][representative_index]["source_component_evidence"]
        )
    _seal_population_digest(evidence, trusted_manifest)


def _seal_population_digest(evidence: dict, trusted_manifest: dict) -> None:
    provenance = {
        "authentication_status": "PASS",
        "authority": "uploaded_step_brep_topology",
        "source_sha256": trusted_manifest["sha256"],
        "source_solid_shape_identity": _derived_source_solid_identity(
            trusted_manifest
        ),
        "source_entity_ids": _periodic_source_ids(evidence),
        "digest_basis": "trusted_source_periodic_population_v1",
    }
    evidence["provenance"] = provenance
    provenance["population_digest_sha256"] = _digest(
        {
            "digest_basis": "trusted_source_periodic_population_v1",
            "trusted_source_manifest_digest_sha256": _trusted_manifest_digest(
                trusted_manifest
            ),
            "method": "periodic_connected_face_components_v1_1_6",
            "populations": [
                _periodic_digest_population(population)
                for population in evidence["populations"]
            ],
        }
    )


def _bind_generated_envelopes(graph: dict, populations: list[dict]) -> None:
    by_blade: dict[tuple[str, int], list[dict]] = {}
    for surface in graph["surfaces"]:
        blade_class = surface.get("blade_class")
        if blade_class in {"main", "splitter"}:
            by_blade.setdefault(
                (blade_class, surface["blade_pair_index"]), []
            ).append(surface)
    for population in populations:
        blade_class = population["classification"]
        for instance in population["instances"]:
            envelope = _graph_envelope(
                by_blade[(blade_class, instance["lattice_index"])]
            )
            instance["angular_span_deg"] = envelope["span_deg"]
            instance["angular_envelope_deg"] = {
                "method": "authoritative_v112_blade_surface_uv_grid_circular_envelope",
                "span_deg": envelope["span_deg"],
            }
            instance["radial_support_range_mm"] = envelope["radial_range_mm"]
            instance["axial_support_range_mm"] = envelope["axial_range_mm"]


def _graph_envelope(surfaces: list[dict]) -> dict:
    points = [
        point
        for surface in surfaces
        for row in surface["uv_grid"]
        for point in row
    ]
    radii = [math.hypot(point[0], point[1]) for point in points]
    collision_points = [
        point
        for surface in surfaces
        if surface["role"]
        not in {"root_to_hub_attachment", "closed_shroud_attachment"}
        for row in surface["uv_grid"]
        for point in row
    ]
    local_spans = _local_collision_spans(collision_points)
    return {
        "span_deg": max(local_spans),
        "radial_range_mm": [min(radii), max(radii)],
        "axial_range_mm": [
            min(point[2] for point in points),
            max(point[2] for point in points),
        ],
    }


def _local_collision_spans(points: list[list[float]]) -> list[float]:
    radii = [math.hypot(point[0], point[1]) for point in points]
    r_min, r_max = min(radii), max(radii)
    z_min = min(point[2] for point in points)
    z_max = max(point[2] for point in points)
    grouped: dict[tuple[int, int], list[float]] = {}
    for point, radius in zip(points, radii):
        key = (
            min(63, int((radius - r_min) / max(r_max - r_min, 1.0e-12) * 64)),
            min(15, int((point[2] - z_min) / max(z_max - z_min, 1.0e-12) * 16)),
        )
        grouped.setdefault(key, []).append(
            math.degrees(math.atan2(point[1], point[0])) % 360.0
        )
    spans = []
    for angles in grouped.values():
        angles.sort()
        gaps = [
            (
                angles[index + 1] - angle
                if index + 1 < len(angles)
                else angles[0] + 360.0 - angle
            )
            for index, angle in enumerate(angles)
        ]
        spans.append(360.0 - max(gaps))
    return spans


def _digest(value: dict) -> str:
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _different_sha256(value: str) -> str:
    replacement = "0" if value[0] != "0" else "1"
    return replacement + value[1:]


def _provenance(source_entity_ids: list[str]) -> dict:
    return {
        "authentication_status": "PASS",
        "authority": "authenticated_source_topology",
        "source_solid_id": _UNSEALED_SOURCE_SOLID_ID,
        "source_sha256": _SOURCE_SHA256,
        "source_entity_ids": list(source_entity_ids),
        "digest_basis": "trusted_source_support_payload_v1",
        "evidence_digest_sha256": "0" * 64,
    }


def _attachment(instance_ids: list[str], prefix: str) -> dict:
    by_instance = {
        instance_id: [f"{prefix}-face-{index:04d}"]
        for index, instance_id in enumerate(instance_ids)
    }
    source_ids = [face_id for face_ids in by_instance.values() for face_id in face_ids]
    return {
        "instance_ids": instance_ids,
        "source_face_ids_by_instance": by_instance,
        "attachment_authority": "authenticated_shared_topology",
        "provenance": _provenance(source_ids),
    }


def _open_support(periodic: dict) -> dict:
    instance_ids = [
        instance["instance_id"]
        for population in periodic["populations"]
        for instance in population["instances"]
    ]
    hub_attachment = _attachment(instance_ids, "hub-attachment")
    all_source_ids = [
        "hub-source-face",
        "tip-reference-source-face",
        *hub_attachment["provenance"]["source_entity_ids"],
        *_periodic_source_ids(periodic),
    ]
    return {
        "status": "PASS",
        "authority": "authenticated_topology_support_v1_1_6",
        "mode": "open",
        "provenance": _provenance(all_source_ids),
        "hub_support": {
            "status": "PASS",
            "semantic_role": "hub_support",
            "material": True,
            "source_face_ids": ["hub-source-face"],
            "blade_attachment": hub_attachment,
            "provenance": _provenance(["hub-source-face"]),
        },
        "material_shroud": None,
        "open_tip_reference": {
            "status": "PASS",
            "semantic_role": "open_tip_reference",
            "material": False,
            "render_default": "hidden",
            "export_default": "excluded",
            "source_face_ids": ["tip-reference-source-face"],
            "provenance": _provenance(["tip-reference-source-face"]),
        },
    }


def _trusted_source_manifest(periodic: dict, support: dict) -> dict:
    source_ids = set(_periodic_source_ids(periodic))

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "source_face_ids" and isinstance(item, list):
                    source_ids.update(item)
                elif key == "source_face_ids_by_instance" and isinstance(item, dict):
                    source_ids.update(
                        face_id
                        for face_ids in item.values()
                        for face_id in face_ids
                    )
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(support)
    ordered_ids = sorted(source_ids)
    adjacency = {face_id: [] for face_id in ordered_ids}
    for population in periodic["populations"]:
        for instance in population["instances"]:
            component_ids = instance["source_face_ids"]
            for first, second in zip(component_ids, component_ids[1:]):
                adjacency[first].append(second)
                adjacency[second].append(first)
    faces = []
    for index, face_id in enumerate(ordered_ids):
        coordinate = float(index)
        faces.append(
            {
                "face_id": face_id,
                "source_entity_index": index,
                "geometry_type": "BSPLINE",
                "area_mm2": coordinate + 1.0,
                "centroid_mm": [coordinate, 0.25 * coordinate, 0.0],
                "bounds_mm": {
                    "minimum": [coordinate, 0.25 * coordinate, 0.0],
                    "maximum": [coordinate + 0.5, 0.25 * coordinate + 0.5, 0.5],
                },
            }
        )
    return {
        "authority": "source_step_brep",
        "sha256": _SOURCE_SHA256,
        "occt_version": "7.8.1",
        "solid_count": 1,
        "shell_count": 1,
        "face_count": len(faces),
        "edge_count": max(1, len(faces) * 2),
        "vertex_count": max(1, len(faces) * 2 + 1),
        "closed_solid": True,
        "volume_mm3": float(len(faces) * 10),
        "surface_area_mm2": float(sum(face["area_mm2"] for face in faces)),
        "centroid_mm": [0.5 * len(faces), 0.125 * len(faces), 0.25],
        "bounds_mm": {
            "minimum": [0.0, 0.0, 0.0],
            "maximum": [float(len(faces)), 0.25 * len(faces) + 0.5, 0.5],
        },
        "surface_type_inventory": {"BSPLINE": len(faces)},
        "faces": faces,
        "adjacency": {
            face_id: sorted(set(neighbors))
            for face_id, neighbors in adjacency.items()
        },
        "tessellation": {
            "linear_tolerance_mm": 0.12,
            "angular_tolerance_rad": 0.16,
            "authority": False,
        },
    }


def _trusted_periodic_partition(periodic: dict, source_manifest: dict) -> dict:
    return {
        "authority": "canonical_periodic_recovery_v1_1_6",
        "source_sha256": source_manifest["sha256"],
        "source_solid_shape_identity": _derived_source_solid_identity(
            source_manifest
        ),
        "method": "periodic_connected_face_components_v1_1_6",
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


def _trusted_material_partition(support: dict, source_manifest: dict) -> dict:
    hub = support["hub_support"]
    partition = {
        "authority": "canonical_support_recovery_v1_1_6",
        "source_sha256": source_manifest["sha256"],
        "source_solid_shape_identity": _derived_source_solid_identity(
            source_manifest
        ),
        "mode": support["mode"],
        "hub_support_face_ids": list(hub["source_face_ids"]),
        "hub_attachment_face_ids_by_instance": copy.deepcopy(
            hub["blade_attachment"]["source_face_ids_by_instance"]
        ),
    }
    if support["mode"] == "open":
        partition.update(
            {
                "open_tip_reference_face_ids": list(
                    support["open_tip_reference"]["source_face_ids"]
                ),
                "material_shroud": None,
            }
        )
    else:
        shroud = support["material_shroud"]
        partition.update(
            {
                "open_tip_reference_face_ids": None,
                "material_shroud": {
                    "source_face_ids": list(shroud["source_face_ids"]),
                    "inner_flowpath_face_ids": list(
                        shroud["inner_flowpath_face_ids"]
                    ),
                    "outer_material_face_ids": list(
                        shroud["outer_material_face_ids"]
                    ),
                    "blade_attachment_face_ids_by_instance": copy.deepcopy(
                        shroud["blade_attachment"][
                            "source_face_ids_by_instance"
                        ]
                    ),
                    "finite_thickness": copy.deepcopy(
                        shroud["finite_thickness"]
                    ),
                },
            }
        )
    return partition


def _trusted_authority(
    periodic: dict, support: dict, source_manifest: dict
) -> dict[str, dict]:
    return {
        "source_topology_manifest": source_manifest,
        "periodic_partition_manifest": _trusted_periodic_partition(
            periodic, source_manifest
        ),
        "material_support_manifest": _trusted_material_partition(
            support, source_manifest
        ),
    }


def _validate_case(graph: dict, periodic: dict, support: dict, authority: dict):
    return validate_and_decorate_pattern_reconstruction(
        graph,
        periodic,
        support,
        trusted_source_topology_manifest=authority["source_topology_manifest"],
        trusted_periodic_partition_manifest=authority[
            "periodic_partition_manifest"
        ],
        trusted_material_support_manifest=authority["material_support_manifest"],
    )


def _seal_support_record(record: dict, trusted_manifest: dict) -> None:
    provenance = record["provenance"]
    provenance.update(
        {
            "authentication_status": "PASS",
            "authority": "authenticated_source_topology",
            "source_solid_id": _derived_source_solid_identity(trusted_manifest),
            "source_sha256": trusted_manifest["sha256"],
            "digest_basis": "trusted_source_support_payload_v1",
        }
    )
    provenance["evidence_digest_sha256"] = _digest(
        {
            "digest_basis": "trusted_source_support_payload_v1",
            "trusted_source_manifest_digest_sha256": _trusted_manifest_digest(
                trusted_manifest
            ),
            "source_sha256": provenance["source_sha256"],
            "source_solid_shape_identity": provenance["source_solid_id"],
            "source_entity_ids": sorted(provenance["source_entity_ids"]),
            "evidence_payload": {
                key: copy.deepcopy(value)
                for key, value in record.items()
                if key != "provenance"
            },
        }
    )


def _seal_support_evidence(support: dict, trusted_manifest: dict) -> None:
    for key in ("hub_support", "open_tip_reference", "material_shroud"):
        record = support.get(key)
        if not isinstance(record, dict):
            continue
        attachment = record.get("blade_attachment")
        if isinstance(attachment, dict) and isinstance(
            attachment.get("provenance"), dict
        ):
            _seal_support_record(attachment, trusted_manifest)
        if isinstance(record.get("provenance"), dict):
            _seal_support_record(record, trusted_manifest)
    support["provenance"]["source_entity_ids"] = sorted(
        face["face_id"] for face in trusted_manifest["faces"]
    )
    _seal_support_record(support, trusted_manifest)


def _open_case(graph: dict) -> tuple[dict, dict, dict]:
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    authority = _trusted_authority(periodic, support, source_manifest)
    _seal_periodic_evidence(periodic, source_manifest)
    _seal_support_evidence(support, source_manifest)
    return periodic, support, authority


def _case_from_production_source_manifest(
    graph: dict, source_manifest: dict
) -> tuple[dict, dict, dict]:
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    synthetic_manifest = _trusted_source_manifest(periodic, support)
    synthetic_ids = [face["face_id"] for face in synthetic_manifest["faces"]]
    production_ids = [face["face_id"] for face in source_manifest["faces"]]
    assert len(production_ids) >= len(synthetic_ids)
    replacements = dict(zip(synthetic_ids, production_ids))

    def replace(value: object) -> object:
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str):
            return replacements.get(value, value)
        return value

    periodic = replace(periodic)
    support = replace(support)
    assert isinstance(periodic, dict)
    assert isinstance(support, dict)
    periodic["main"] = periodic["populations"][0]
    periodic["splitter"] = (
        periodic["populations"][1]
        if periodic["splitter_blade_count"]
        else None
    )
    authority = _trusted_authority(periodic, support, source_manifest)
    _seal_periodic_evidence(periodic, source_manifest)
    _seal_support_evidence(support, source_manifest)
    return periodic, support, authority


def test_open_n_plus_zero_decorates_every_blade_surface_and_freezes_manifest():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    graph_before = copy.deepcopy(graph)
    periodic_before = copy.deepcopy(periodic)
    support_before = copy.deepcopy(support)
    trusted_before = copy.deepcopy(trusted_authority)

    decorated, manifest = _validate_case(graph, periodic, support, trusted_authority)

    assert manifest["status"] == "PASS"
    assert manifest["pattern"]["main_blade_count"] == 3
    assert manifest["pattern"]["splitter_blade_count"] == 0
    assert manifest["material"]["material_shroud"] is None
    assert manifest["material"]["material_shroud_area_mm2"] is None
    assert manifest["pattern"]["collision_fidelity"] == (
        "sampled_v112_uv_grid_not_cad_certified"
    )
    assert manifest["pattern"]["source_topology_separated"] is True
    assert manifest["pattern"]["exact_brep_collision_checked"] is True
    assert manifest["pattern"]["exact_brep_collision_free"] is True
    assert "v1_1_6_pattern_material" not in graph
    assert graph == graph_before
    assert periodic == periodic_before
    assert support == support_before
    assert trusted_authority == trusted_before
    blade_surfaces = [surface for surface in decorated["surfaces"] if "blade_class" in surface]
    assert blade_surfaces
    assert all(surface["periodic_pattern_binding"]["population_id"] == "main" for surface in blade_surfaces)
    assert all(surface["material"] is True for surface in blade_surfaces)
    tip_reference = next(
        surface for surface in decorated["surfaces"] if surface["role"] == "open_tip_reference"
    )
    assert tip_reference["material"] is False
    assert tip_reference["render_default"] == "hidden"
    assert tip_reference["export_default"] == "excluded"
    tip_domes = [surface for surface in decorated["surfaces"] if surface["role"] == "open_tip_dome"]
    assert len(tip_domes) == 3
    assert all(surface["material"] is True for surface in tip_domes)
    with pytest.raises(TypeError):
        manifest["status"] = "FAIL"
    with pytest.raises(TypeError):
        manifest["pattern"]["populations"][0]["count"] = 99


def test_pattern_decoration_copy_on_write_does_not_clone_dense_geometry():
    grid = [[[float(u), float(v), 0.0] for v in range(97)] for u in range(49)]
    graph = {
        "surfaces": [
            {
                "id": "blade_0_pressure_surface",
                "uv_grid": grid,
                "display": {"visible_by_default": True},
            }
        ]
    }

    decorated = pattern_reconstruction._copy_surface_graph_for_pattern_decoration(
        graph
    )

    assert decorated is not graph
    assert decorated["surfaces"] is not graph["surfaces"]
    assert decorated["surfaces"][0] is not graph["surfaces"][0]
    assert decorated["surfaces"][0]["display"] is not graph["surfaces"][0]["display"]
    assert decorated["surfaces"][0]["uv_grid"] is grid


def test_pattern_decoration_preserves_non_material_topological_seams():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    seam = next(
        surface
        for surface in graph["surfaces"]
        if surface.get("blade_class") == "main"
        and surface.get("blade_pair_index") == 0
        and surface.get("role") == "blade_leading_edge"
    )
    seam["material"] = False
    seam["render_default"] = "hidden"
    seam["export_default"] = "excluded"
    seam["source"] = {"authority": "authenticated_step_shared_seam"}
    seam["fidelity"] = "topological_shared_seam_no_finite_face"
    graph["topology_graph"] = build_v10_topology_graph(graph["surfaces"])
    graph["parameter_inspection"] = build_parameter_inspection_contract(graph)
    graph["generation_id"] = graph["parameter_inspection"]["generation_id"]
    periodic, support, trusted_authority = _open_case(graph)

    decorated, _manifest = _validate_case(
        graph, periodic, support, trusted_authority
    )

    decorated_seam = next(
        surface
        for surface in decorated["surfaces"]
        if surface.get("id") == seam["id"]
    )
    assert decorated_seam["periodic_pattern_binding"]["population_id"] == "main"
    assert decorated_seam["material"] is False
    assert decorated_seam["render_default"] == "hidden"
    assert decorated_seam["export_default"] == "excluded"
    assert decorated_seam["source"]["authority"] == (
        "authenticated_step_shared_seam"
    )
    assert decorated_seam["fidelity"] == "topological_shared_seam_no_finite_face"


def test_open_tip_reference_may_be_fitted_from_periodic_material_tip_cap():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    tip_cap_face_id = periodic["main"]["instances"][0]["source_face_ids"][-1]
    support["open_tip_reference"]["source_face_ids"] = [tip_cap_face_id]
    support["open_tip_reference"]["provenance"]["source_entity_ids"] = [
        tip_cap_face_id
    ]
    source_manifest = _trusted_source_manifest(periodic, support)
    authority = _trusted_authority(periodic, support, source_manifest)
    _seal_periodic_evidence(periodic, source_manifest)
    _seal_support_evidence(support, source_manifest)

    decorated, manifest = _validate_case(graph, periodic, support, authority)

    assert list(
        manifest["material"]["open_tip_reference"]["source_face_ids"]
    ) == [tip_cap_face_id]
    reference = next(
        surface
        for surface in decorated["surfaces"]
        if surface["role"] == "open_tip_reference"
    )
    assert reference["material"] is False
    assert reference["export_default"] == "excluded"


def _task8_mapping(periodic: dict, material_partition: dict, source_manifest: dict):
    mapping = {
        "periodic_provenance": {
            "measurement_tolerance_mm": periodic["measurement_tolerance_mm"],
            "source_linear_tolerance_mm": periodic.get(
                "source_linear_tolerance_mm",
                periodic["measurement_tolerance_mm"],
            ),
            "pattern_population_evidence": periodic,
        },
        "support_recovery": {
            "pattern_material_partition": material_partition,
        },
    }
    mapping["task8_reconstruction_evidence_hash_sha256"] = (
        task8_reconstruction_evidence_hash(
            mapping["support_recovery"],
            mapping["periodic_provenance"],
            source_manifest["sha256"],
        )
    )
    return mapping


def _task8_authority(mapping: dict, source_manifest: dict):
    return preserve_task8_reconstruction_authority(
        mapping, source_manifest["sha256"]
    )


def test_mapped_adapter_seals_task8_population_and_material_evidence(monkeypatch):
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )
    completion_calls = 0
    original_completion = pattern_reconstruction._completed_v112_graph

    def count_completion(surface_graph):
        nonlocal completion_calls
        completion_calls += 1
        return original_completion(surface_graph)

    monkeypatch.setattr(
        pattern_reconstruction,
        "_completed_v112_graph",
        count_completion,
    )

    decorated, manifest = validate_mapped_pattern_reconstruction(
        graph,
        mapping,
        source_manifest,
        task8_recovery_authority=_task8_authority(mapping, source_manifest),
    )

    assert manifest["status"] == "PASS"
    assert manifest["pattern"]["main_blade_count"] == 3
    assert manifest["pattern"]["splitter_blade_count"] == 0
    assert manifest["material"]["material_shroud"] is None
    assert decorated["v1_1_6_pattern_material"]["status"] == "PASS"
    assert completion_calls == 1


def test_mapped_adapter_measures_generated_collision_only_once(monkeypatch):
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )
    original = pattern_reconstruction._measure_graph_collision_diagnostics
    call_count = 0

    def measured_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        pattern_reconstruction,
        "_measure_graph_collision_diagnostics",
        measured_once,
    )

    validate_mapped_pattern_reconstruction(
        graph,
        mapping,
        source_manifest,
        task8_recovery_authority=_task8_authority(mapping, source_manifest),
    )

    assert call_count == 1


def test_mapped_adapter_rejects_task8_source_collision_before_graph_collision():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    periodic["collision_diagnostics"].update(
        {
            "collision_free": False,
            "collision_count": 1,
            "collisions": [{"first": "source-main-0", "second": "source-main-1"}],
        }
    )
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )

    with pytest.raises(PatternReconstructionError) as raised:
        validate_mapped_pattern_reconstruction(
            graph,
            mapping,
            source_manifest,
            task8_recovery_authority=_task8_authority(
                mapping, source_manifest
            ),
        )

    assert raised.value.reason == "v116_pattern_collision"


def test_mapped_adapter_allows_explicit_unknown_source_collision_for_review_only_graph():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    periodic["collision_diagnostics"].update(
        {
            "collision_status": "UNKNOWN",
            "collision_free": None,
            "collision_count": 0,
            "collisions": [],
            "source_topology_separated": True,
            "exact_brep_collision_checked": False,
            "exact_brep_collision_free": None,
        }
    )
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )

    decorated, manifest = validate_mapped_pattern_reconstruction(
        graph,
        mapping,
        source_manifest,
        task8_recovery_authority=_task8_authority(mapping, source_manifest),
    )

    assert manifest["status"] == "REVIEW_ONLY"
    assert manifest["pattern"]["source_collision_status"] == "UNKNOWN"
    assert (
        manifest["pattern"]["collision_status"]
        == "SOURCE_UNKNOWN_RECONSTRUCTED_SAMPLE_PASS"
    )
    assert decorated["v1_1_6_pattern_material"]["status"] == "REVIEW_ONLY"


def test_mapped_adapter_rejects_legacy_collision_free_boolean_without_exact_evidence():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    diagnostics = periodic["collision_diagnostics"]
    for key in (
        "collision_status",
        "source_topology_separated",
        "exact_brep_collision_checked",
        "exact_brep_collision_free",
    ):
        diagnostics.pop(key)
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )

    with pytest.raises(PatternReconstructionError) as raised:
        validate_mapped_pattern_reconstruction(
            graph,
            mapping,
            source_manifest,
            task8_recovery_authority=_task8_authority(mapping, source_manifest),
        )

    assert raised.value.reason == "v116_pattern_evidence_invalid"


def test_open_mapped_adapter_excludes_tip_reference_from_real_triangulation():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _open_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    mapping = _task8_mapping(
        periodic,
        _trusted_material_partition(support, source_manifest),
        source_manifest,
    )
    decorated, _ = validate_mapped_pattern_reconstruction(
        graph,
        mapping,
        source_manifest,
        task8_recovery_authority=_task8_authority(mapping, source_manifest),
    )

    triangulation = triangulate_surface_graph(
        _material_export_surface_graph(decorated),
        view_id="cad_review_360",
    )

    assert "tip_reference_surface" not in triangulation["included_surface_ids"]
    assert triangulation["triangles"]


def test_production_load_step_source_manifest_derives_solid_identity(tmp_path):
    step_path = write_periodic_impeller_step(
        tmp_path / "task9-loader-source.step", blade_count=8
    )
    _, source_manifest = load_step_source(step_path)
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _case_from_production_source_manifest(
        graph, source_manifest
    )
    assert "source_solid_shape_identity" not in source_manifest
    assert {
        "authority",
        "sha256",
        "occt_version",
        "solid_count",
        "shell_count",
        "face_count",
        "edge_count",
        "vertex_count",
        "closed_solid",
        "volume_mm3",
        "surface_area_mm2",
        "centroid_mm",
        "bounds_mm",
        "surface_type_inventory",
        "faces",
        "adjacency",
        "tessellation",
    } == set(source_manifest)

    _, manifest = _validate_case(
        graph, periodic, support, trusted_authority
    )

    expected_identity = _derived_source_solid_identity(source_manifest)
    assert manifest["pattern"]["source_provenance"][
        "source_solid_shape_identity"
    ] == expected_identity
    assert manifest["material"]["source_solid_id"] == expected_identity


def test_trusted_source_manifest_rejects_nonclosed_solid():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    trusted_authority["source_topology_manifest"]["closed_solid"] = False

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_trusted_source_manifest_invalid"


def test_main_plus_splitter_matches_generated_class_pair_and_representative_family():
    graph = copy.deepcopy(_runtime_graph("radial_open_reference_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)

    decorated, manifest = _validate_case(graph, periodic, support, trusted_authority)

    assert [population["population_id"] for population in manifest["pattern"]["populations"]] == [
        "main",
        "splitter",
    ]
    for surface in decorated["surfaces"]:
        if surface.get("blade_class") not in {"main", "splitter"}:
            continue
        binding = surface["periodic_pattern_binding"]
        assert binding["population_id"] == surface["blade_class"]
        assert binding["lattice_index"] == surface["blade_pair_index"]
        assert binding["source_representative_component_id"].startswith(
            f"source_{surface['blade_class']}_component_"
        )
        assert binding["source_representative_face_ids"]
        assert binding["generated_surface_residual_mm"] <= 1.0e-6


def test_transform_mutation_is_rejected_as_non_rigid_z_rotation():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    periodic["main"]["instances"][1]["transform_from_representative"][0][3] = 0.25
    _seal_periodic_evidence(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_pattern_transform_invalid"


def test_exact_population_count_mismatch_is_rejected():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    periodic["main_blade_count"] += 1
    _seal_periodic_evidence(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_pattern_count_mismatch"


def test_recomputed_collision_rejects_false_collision_free_claim():
    graph = copy.deepcopy(_runtime_graph("radial_open_reference_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    periodic["collision_diagnostics"]["collision_free"] = False
    periodic["collision_diagnostics"]["collision_count"] = 1
    _seal_periodic_evidence(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_pattern_collision"


def test_tiny_supplied_angular_spans_cannot_understate_graph_collision_envelope():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    for instance in periodic["main"]["instances"]:
        instance["angular_span_deg"] = 1.0e-9
        instance["angular_envelope_deg"]["span_deg"] = 1.0e-9
    _seal_periodic_evidence(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_pattern_envelope_invalid"


def test_authoritative_uv_grid_overlap_rejects_supplied_pass_diagnostics():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    _inject_authoritative_uv_overlap(graph)
    periodic, support, trusted_authority = _open_case(graph)
    assert periodic["collision_diagnostics"]["collision_free"] is True
    assert periodic["collision_diagnostics"]["collision_count"] == 0

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_pattern_collision"
    assert raised.value.details["recomputed"]["collision_count"] > 0
    assert raised.value.details["recomputed"]["fidelity"] == (
        "sampled_v112_uv_grid_not_cad_certified"
    )


def test_global_collision_grid_keeps_angular_overlap_separated_in_physical_rz():
    populations = [
        {
            "instances": [
                {
                    "source_component_id": "component-a",
                    "collision_samples": [
                        {"radius_mm": 10.0, "axial_mm": 0.0, "angle_deg": 15.0}
                    ],
                },
                {
                    "source_component_id": "component-b",
                    "collision_samples": [
                        {"radius_mm": 30.0, "axial_mm": 8.0, "angle_deg": 15.0}
                    ],
                },
            ]
        }
    ]

    diagnostics = _measure_graph_collision_diagnostics(
        populations, collision_tolerance_deg=1.0e-6
    )

    assert diagnostics["collision_free"] is True
    assert diagnostics["collision_count"] == 0
    assert diagnostics["physical_grid"]["radial_range_mm"] == [10.0, 30.0]
    assert diagnostics["physical_grid"]["axial_range_mm"] == [0.0, 8.0]


def test_global_collision_grid_detects_true_physical_sample_overlap():
    populations = [
        {
            "instances": [
                {
                    "source_component_id": "component-a",
                    "collision_samples": [
                        {"radius_mm": 20.0, "axial_mm": 4.0, "angle_deg": 27.0}
                    ],
                },
                {
                    "source_component_id": "component-b",
                    "collision_samples": [
                        {"radius_mm": 20.0, "axial_mm": 4.0, "angle_deg": 27.0}
                    ],
                },
            ]
        }
    ]

    diagnostics = _measure_graph_collision_diagnostics(
        populations, collision_tolerance_deg=1.0e-6
    )

    assert diagnostics["collision_free"] is False
    assert diagnostics["collision_count"] == 1
    assert diagnostics["collisions"][0]["cell_index"] == [0, 0]


def test_collision_broad_phase_refines_separated_samples_inside_one_coarse_cell():
    populations = [
        {
            "instances": [
                {
                    "source_component_id": "component-a",
                    "collision_samples": [
                        {"radius_mm": 0.0, "axial_mm": 0.0, "angle_deg": 0.0},
                        {"radius_mm": 0.10, "axial_mm": 15.10, "angle_deg": 0.0},
                        {"radius_mm": 0.10, "axial_mm": 15.90, "angle_deg": 20.0},
                    ],
                },
                {
                    "source_component_id": "component-b",
                    "collision_samples": [
                        {"radius_mm": 64.0, "axial_mm": 16.0, "angle_deg": 100.0},
                        {"radius_mm": 0.90, "axial_mm": 15.10, "angle_deg": 10.0},
                        {"radius_mm": 0.90, "axial_mm": 15.90, "angle_deg": 10.0},
                    ],
                },
            ]
        }
    ]

    diagnostics = _measure_graph_collision_diagnostics(
        populations, collision_tolerance_deg=1.0e-6
    )

    assert diagnostics["collision_free"] is True
    assert diagnostics["collision_count"] == 0
    assert diagnostics["broad_phase_candidate_count"] == 1
    assert diagnostics["refined_candidate_count"] == 0


def test_collision_narrow_phase_rejects_projected_overlap_between_separated_surfaces():
    first_grid = [
        [[10.0, 0.0, 0.0], [11.0, 0.0, 0.0]],
        [[10.0, 1.0, 0.0], [11.0, 1.0, 0.0]],
    ]
    second_grid = [
        [[10.0, 0.0, 0.05], [11.0, 0.0, 0.05]],
        [[10.0, 1.0, 0.05], [11.0, 1.0, 0.05]],
    ]
    populations = [
        {
            "instances": [
                {
                    "source_component_id": "component-a",
                    "collision_samples": [
                        {"radius_mm": 0.0, "axial_mm": -8.0, "angle_deg": 180.0}
                    ]
                    + [
                        {
                            "radius_mm": math.hypot(point[0], point[1]),
                            "axial_mm": point[2],
                            "angle_deg": math.degrees(math.atan2(point[1], point[0])),
                        }
                        for row in first_grid
                        for point in row
                    ],
                    "collision_surface_grids": [first_grid],
                },
                {
                    "source_component_id": "component-b",
                    "collision_samples": [
                        {"radius_mm": 20.0, "axial_mm": 8.0, "angle_deg": 180.0}
                    ]
                    + [
                        {
                            "radius_mm": math.hypot(point[0], point[1]),
                            "axial_mm": point[2],
                            "angle_deg": math.degrees(math.atan2(point[1], point[0])),
                        }
                        for row in second_grid
                        for point in row
                    ],
                    "collision_surface_grids": [second_grid],
                },
            ]
        }
    ]

    diagnostics = _measure_graph_collision_diagnostics(
        populations, collision_tolerance_deg=1.0e-6
    )

    assert diagnostics["collision_free"] is True
    assert diagnostics["collision_count"] == 0
    assert diagnostics["narrow_phase_method"] == "sampled_uv_triangle_sat"


def test_collision_narrow_phase_detects_intersecting_surface_triangles():
    grid = [
        [[10.0, 0.0, 0.0], [11.0, 0.0, 0.0]],
        [[10.0, 1.0, 0.0], [11.0, 1.0, 0.0]],
    ]
    samples = [
        {
            "radius_mm": math.hypot(point[0], point[1]),
            "axial_mm": point[2],
            "angle_deg": math.degrees(math.atan2(point[1], point[0])),
        }
        for row in grid
        for point in row
    ]
    populations = [
        {
            "instances": [
                {
                    "source_component_id": "component-a",
                    "collision_samples": samples,
                    "collision_surface_grids": [grid],
                },
                {
                    "source_component_id": "component-b",
                    "collision_samples": samples,
                    "collision_surface_grids": [grid],
                },
            ]
        }
    ]

    diagnostics = _measure_graph_collision_diagnostics(
        populations, collision_tolerance_deg=1.0e-6
    )

    assert diagnostics["collision_free"] is False
    assert diagnostics["collision_count"] == 1
    assert diagnostics["collisions"][0]["narrow_phase"] == "triangle_sat"


def test_collision_envelope_excludes_non_material_sharp_seam_placeholders():
    material_grid = [
        [[10.0, 0.0, 0.0], [11.0, 0.0, 0.0]],
        [[10.0, 1.0, 0.0], [11.0, 1.0, 0.0]],
    ]
    placeholder_grid = [
        [[10.0, -10.0, 0.0], [11.0, -10.0, 0.0]],
        [[10.0, 10.0, 0.0], [11.0, 10.0, 0.0]],
    ]
    envelope = _surface_family_envelope(
        {
            ("blade_pressure", "side"): {
                "role": "blade_pressure",
                "material": True,
                "uv_grid": material_grid,
            },
            ("blade_leading_edge", "sharp_seam"): {
                "role": "blade_leading_edge",
                "material": False,
                "export_default": "excluded",
                "uv_grid": placeholder_grid,
            },
        }
    )

    assert len(envelope["collision_samples"]) == 4
    assert len(envelope["collision_surface_grids"]) == 1


def test_well_formed_face_signature_mutation_is_recomputed_from_trusted_face():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    component_provenance = periodic["main"]["instances"][1][
        "source_component_evidence"
    ]["provenance"]
    component_provenance["signature_hashes"][0] = _different_sha256(
        component_provenance["signature_hashes"][0]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_periodic_provenance_invalid"


def test_well_formed_component_digest_mutation_is_recomputed_from_trusted_faces():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    component_provenance = periodic["main"]["instances"][1][
        "source_component_evidence"
    ]["provenance"]
    component_provenance["component_digest_sha256"] = _different_sha256(
        component_provenance["component_digest_sha256"]
    )
    _seal_population_digest(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_periodic_provenance_invalid"


def test_well_formed_population_digest_mutation_is_recomputed_from_trusted_components():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    provenance = periodic["provenance"]
    provenance["population_digest_sha256"] = _different_sha256(
        provenance["population_digest_sha256"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_periodic_provenance_invalid"


def test_resigned_swapped_component_faces_fail_independent_periodic_partition():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    first = periodic["main"]["instances"][1]
    second = periodic["main"]["instances"][2]
    first["source_face_ids"][0], second["source_face_ids"][0] = (
        second["source_face_ids"][0],
        first["source_face_ids"][0],
    )
    _seal_periodic_evidence(
        periodic, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_periodic_provenance_invalid"


def test_fabricated_component_face_ids_fail_authenticated_source_inventory_membership():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    instance = periodic["main"]["instances"][1]
    original_face_id = instance["source_face_ids"][0]
    fabricated_face_id = "fabricated-source-face"
    fabricated_manifest = copy.deepcopy(
        trusted_authority["source_topology_manifest"]
    )
    fabricated_face = next(
        face
        for face in fabricated_manifest["faces"]
        if face["face_id"] == original_face_id
    )
    fabricated_face["face_id"] = fabricated_face_id
    fabricated_manifest["adjacency"][fabricated_face_id] = fabricated_manifest[
        "adjacency"
    ].pop(original_face_id)
    for neighbors in fabricated_manifest["adjacency"].values():
        if original_face_id in neighbors:
            neighbors[neighbors.index(original_face_id)] = fabricated_face_id
    instance["source_face_ids"][0] = fabricated_face_id
    component = instance["source_component_evidence"]
    component["source_entity_ids"][0] = fabricated_face_id
    component["provenance"]["source_entity_ids"][0] = fabricated_face_id
    _seal_periodic_evidence(periodic, fabricated_manifest)
    _seal_support_evidence(support, fabricated_manifest)

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_periodic_provenance_invalid"
