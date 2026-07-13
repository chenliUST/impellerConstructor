from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    from scipy.spatial import cKDTree
except ImportError:  # pragma: no cover - CadQuery installations normally provide SciPy.
    cKDTree = None


_REGIONAL_EVIDENCE_FIELDS = frozenset(
    {
        "units",
        "coordinate_frame",
        "tessellation_tolerance_mm",
        "projection_tolerance_mm",
        "source_regions",
        "reconstruction_regions",
        "region_mappings",
        "root_gates",
        "material_checks",
        "thickness_checks",
        "stations",
        "silhouettes",
    }
)
_DIRECTIONAL_WEIGHT = 0.5


@dataclass(frozen=True)
class TriangleMesh:
    vertices: np.ndarray
    triangles: np.ndarray
    normals: np.ndarray


def read_stl(path: str | Path) -> TriangleMesh:
    payload = Path(path).read_bytes()
    if len(payload) >= 84:
        triangle_count = struct.unpack_from("<I", payload, 80)[0]
        if 84 + triangle_count * 50 == len(payload):
            return _read_binary_stl(payload, triangle_count)
    return _read_ascii_stl(payload.decode("utf-8", errors="replace"))


def write_binary_stl(path: str | Path, mesh: TriangleMesh, *, label: str = "V1.1.6 audit mesh") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    header = label.encode("ascii", errors="replace")[:80].ljust(80, b"\0")
    with target.open("wb") as stream:
        stream.write(header)
        stream.write(struct.pack("<I", int(len(mesh.triangles))))
        for index, triangle in enumerate(mesh.triangles):
            normal = mesh.normals[index] if index < len(mesh.normals) else _triangle_normal(mesh.vertices[triangle])
            stream.write(struct.pack("<3f", *[float(value) for value in normal]))
            for vertex_index in triangle:
                stream.write(struct.pack("<3f", *[float(value) for value in mesh.vertices[vertex_index]]))
            stream.write(struct.pack("<H", 0))


def transform_mesh(mesh: TriangleMesh, matrix: list[list[float]]) -> TriangleMesh:
    transform = np.asarray(matrix, dtype=float)
    if transform.shape != (4, 4):
        raise ValueError("mesh transform must be a 4x4 matrix")
    homogeneous = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices))))
    vertices = (homogeneous @ transform.T)[:, :3]
    normal_matrix = np.linalg.inv(transform[:3, :3]).T
    normals = mesh.normals @ normal_matrix.T
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals / np.maximum(lengths[:, None], 1.0e-12)
    return TriangleMesh(vertices=vertices, triangles=mesh.triangles.copy(), normals=normals)


def resolve_periodic_phase_alignment(
    source: TriangleMesh,
    reconstruction: TriangleMesh,
    periodic_count: int,
    *,
    sample_limit: int = 6000,
) -> tuple[TriangleMesh, dict[str, Any]]:
    if int(periodic_count) < 2:
        raise ValueError("periodic phase alignment requires at least two repeated blades")
    source_samples = _bounded_triangle_centroids(source, sample_limit)
    reconstruction_samples = _bounded_triangle_centroids(reconstruction, sample_limit)
    pitch_deg = 360.0 / int(periodic_count)

    def score(phase_deg: float) -> float:
        rotated = _rotate_points_about_z(reconstruction_samples, phase_deg)
        source_to_reconstruction = _nearest_distances(source_samples, rotated)
        reconstruction_to_source = _nearest_distances(rotated, source_samples)
        combined = np.concatenate((source_to_reconstruction, reconstruction_to_source))
        return float(np.sqrt(np.mean(combined**2)))

    coarse_phases = np.linspace(-0.5 * pitch_deg, 0.5 * pitch_deg, 49)
    coarse_scores = [score(float(phase)) for phase in coarse_phases]
    coarse_index = int(np.argmin(coarse_scores))
    coarse_best = float(coarse_phases[coarse_index])
    coarse_step = pitch_deg / 48.0
    fine_phases = np.linspace(coarse_best - coarse_step, coarse_best + coarse_step, 25)
    fine_scores = [score(float(phase)) for phase in fine_phases]
    phase_deg = float(fine_phases[int(np.argmin(fine_scores))])
    phase_deg = ((phase_deg + 0.5 * pitch_deg) % pitch_deg) - 0.5 * pitch_deg
    before = score(0.0)
    after = score(phase_deg)
    aligned = transform_mesh(reconstruction, _rotation_z_matrix(phase_deg))
    return aligned, {
        "method": "bounded_symmetric_periodic_phase_search",
        "rotation_about_axis_deg": round(phase_deg, 6),
        "periodic_count": int(periodic_count),
        "pitch_deg": round(pitch_deg, 9),
        "scale": 1.0,
        "translation_mm": [0.0, 0.0, 0.0],
        "primary_icp_applied": False,
        "sample_limit_per_mesh": int(sample_limit),
        "objective_rms_before_mm": round(before, 6),
        "objective_rms_after_mm": round(after, 6),
        "improvement_fraction": round(max(0.0, 1.0 - after / max(before, 1.0e-12)), 6),
    }


def compare_meshes(
    source: TriangleMesh,
    reconstruction: TriangleMesh,
    *,
    source_closed: bool = True,
    reconstruction_closed: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_samples = _triangle_centroids(source)
    reconstruction_samples = _triangle_centroids(reconstruction)
    source_to_reconstruction = _nearest_distances(source_samples, reconstruction_samples)
    reconstruction_to_source = _nearest_distances(reconstruction_samples, source_samples)
    vertex_error = _nearest_distances(reconstruction.vertices, source.vertices)

    combined = np.concatenate((source_to_reconstruction, reconstruction_to_source))
    metrics = {
        "distance_kind": "unsigned_mesh_sample_distance_mm",
        "signed_distance_available": bool(source_closed and reconstruction_closed),
        "source_to_reconstruction": _distribution(source_to_reconstruction),
        "reconstruction_to_source": _distribution(reconstruction_to_source),
        "bidirectional": _distribution(combined),
        "symmetric_chamfer_mm": round(
            float(np.mean(source_to_reconstruction) + np.mean(reconstruction_to_source)), 6
        ),
        "source_mesh": _mesh_properties(source),
        "reconstruction_mesh": _mesh_properties(reconstruction),
        "silhouettes": {
            "top_xy_hausdorff_mm": round(_projected_hausdorff(source.vertices[:, :2], reconstruction.vertices[:, :2]), 6),
            "meridional_rz_hausdorff_mm": round(
                _projected_hausdorff(_rz(source.vertices), _rz(reconstruction.vertices)), 6
            ),
        },
        "section_residuals": _section_residuals(source.vertices, reconstruction.vertices),
        "semantic_role_metrics": {
            "all_reconstruction": {
                **_distribution(reconstruction_to_source),
                "triangle_count": int(len(reconstruction.triangles)),
            }
        },
        "semantic_triangle_coverage": 1.0,
    }
    heatmap = _heatmap_payload(reconstruction, vertex_error)
    return metrics, heatmap


def write_heatmap(path: str | Path, heatmap: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(heatmap, separators=(",", ":")), encoding="utf-8")


def artifact_record(path: str | Path, *, fidelity: str, media_type: str) -> dict[str, Any]:
    target = Path(path)
    payload = target.read_bytes()
    return {
        "file_name": target.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "fidelity": fidelity,
        "media_type": media_type,
    }


def compare_regional_deviation(evidence: dict[str, Any]) -> dict[str, Any]:
    """Compare explicitly mapped semantic measurements without mesh or viewport input.

    The evidence schema deliberately contains only source/reconstruction measurement
    records.  It does not accept inferred sections, camera state, or mesh bounds:
    callers must persist the samples used for every reported metric.
    """
    if not isinstance(evidence, dict):
        raise ValueError("regional deviation evidence must be an object")
    if any(not isinstance(field, str) or not field for field in evidence):
        raise ValueError("regional deviation evidence field names must be non-empty strings")
    unexpected_fields = sorted(set(evidence) - _REGIONAL_EVIDENCE_FIELDS)
    if unexpected_fields:
        raise ValueError(
            "regional deviation evidence has unsupported top-level fields: "
            + ", ".join(unexpected_fields)
        )
    metadata = _regional_metadata(evidence)
    source_regions = _regional_records(evidence, "source_regions", "source_id")
    reconstruction_regions = _regional_records(
        evidence, "reconstruction_regions", "reconstruction_id"
    )
    mappings, mapping_failures = _regional_mappings(
        evidence, source_regions, reconstruction_regions
    )
    terminal_failures = mapping_failures + _terminal_evidence_failures(evidence)
    region_metrics = []
    global_distance_terms: list[tuple[float, float]] = []
    global_angle_terms: list[tuple[float, float]] = []

    for mapping in mappings:
        source = source_regions[mapping["source_region_id"]]
        reconstruction = reconstruction_regions[mapping["reconstruction_region_id"]]
        source_points, source_normals = _region_samples(source, "source")
        reconstruction_points, reconstruction_normals = _region_samples(
            reconstruction, "reconstruction"
        )
        source_distances, source_matches = _regional_nearest(
            source_points, reconstruction_points
        )
        reconstruction_distances, reconstruction_matches = _regional_nearest(
            reconstruction_points, source_points
        )
        source_angles = _normal_angles(source_normals, reconstruction_normals[source_matches])
        reconstruction_angles = _normal_angles(
            reconstruction_normals, source_normals[reconstruction_matches]
        )
        source_ids = [source["source_id"]]
        reconstruction_ids = [reconstruction["reconstruction_id"]]
        attributes = _metric_attributes(metadata, source_ids, reconstruction_ids)
        source_distance_metric = _metric_distribution(
            source_distances, "mm", "semantic_nearest_sample_distance", attributes
        )
        reconstruction_distance_metric = _metric_distribution(
            reconstruction_distances,
            "mm",
            "semantic_nearest_sample_distance",
            attributes,
        )
        bidirectional_distance_metric = _bidirectional_metric_distribution(
            source_distances,
            reconstruction_distances,
            "mm",
            "semantic_bidirectional_nearest_sample_distance",
            attributes,
        )
        source_angle_metric = _metric_distribution(
            source_angles, "deg", "semantic_nearest_sample_normal_angle", attributes
        )
        reconstruction_angle_metric = _metric_distribution(
            reconstruction_angles,
            "deg",
            "semantic_nearest_sample_normal_angle",
            attributes,
        )
        bidirectional_angle_metric = _bidirectional_metric_distribution(
            source_angles,
            reconstruction_angles,
            "deg",
            "semantic_bidirectional_nearest_sample_normal_angle",
            attributes,
        )
        source_contributing_sample_count = len(source_points)
        reconstruction_contributing_sample_count = len(reconstruction_points)
        effective_weight = source_contributing_sample_count * source["weight"]
        global_distance_terms.append(
            (bidirectional_distance_metric["rms"], effective_weight)
        )
        global_angle_terms.append((bidirectional_angle_metric["rms"], effective_weight))
        region_metrics.append(
            {
                "semantic_role": mapping["semantic_role"],
                "source_region_id": source["region_id"],
                "reconstruction_region_id": reconstruction["region_id"],
                "source_sample_count": source["sample_count"],
                "reconstruction_sample_count": reconstruction["sample_count"],
                "source_contributing_sample_count": source_contributing_sample_count,
                "reconstruction_contributing_sample_count": reconstruction_contributing_sample_count,
                "stored_weight": source["weight"],
                "effective_weight": _round(effective_weight),
                "distance": {
                    "source_to_reconstruction": source_distance_metric,
                    "reconstruction_to_source": reconstruction_distance_metric,
                    "bidirectional": bidirectional_distance_metric,
                },
                "normal_angle": {
                    "source_to_reconstruction": source_angle_metric,
                    "reconstruction_to_source": reconstruction_angle_metric,
                    "bidirectional": bidirectional_angle_metric,
                },
            }
        )

    station_metrics, station_failures = _station_metrics(
        evidence, source_regions, reconstruction_regions, mappings, metadata
    )
    terminal_failures.extend(station_failures)
    terminal_failures.sort(key=lambda item: (item["code"], item["id"]))
    silhouette_metrics = _silhouette_metrics(evidence, metadata)
    all_source_ids = sorted(
        {source_regions[mapping["source_region_id"]]["source_id"] for mapping in mappings}
    )
    all_reconstruction_ids = sorted(
        {
            reconstruction_regions[mapping["reconstruction_region_id"]][
                "reconstruction_id"
            ]
            for mapping in mappings
        }
    )
    global_attributes = _metric_attributes(metadata, all_source_ids, all_reconstruction_ids)
    global_metrics = {
        "distance_rms_mm": _single_metric(
            _weighted_rms(global_distance_terms),
            "mm",
            "unique_source_sample_count_weighted_region_rms",
            global_attributes,
        ),
        "normal_angle_rms_deg": _single_metric(
            _weighted_rms(global_angle_terms),
            "deg",
            "unique_source_sample_count_weighted_region_rms",
            global_attributes,
        ),
        "weight_basis": {
            "method": "unique_source_region_sample_count_times_stored_weight",
            "regions": [
                {
                    "source_region_id": item["source_region_id"],
                    "stored_sample_count": item["source_sample_count"],
                    "contributing_sample_count": item[
                        "source_contributing_sample_count"
                    ],
                    "stored_weight": item["stored_weight"],
                    "effective_weight": item["effective_weight"],
                }
                for item in region_metrics
            ],
        },
    }
    result = {
        "contract_id": "impeller_v1_1_6_regional_deviation",
        "contract_version": 1,
        "status": "terminal_failure" if terminal_failures else "accepted",
        "terminal_failures": terminal_failures,
        "units": metadata["units"],
        "coordinate_frame": metadata["coordinate_frame"],
        "tessellation_tolerance_mm": metadata["tessellation_tolerance_mm"],
        "projection_tolerance_mm": metadata["projection_tolerance_mm"],
        "regions": sorted(region_metrics, key=lambda item: item["source_region_id"]),
        "stations": station_metrics,
        "silhouettes": silhouette_metrics,
        "global": global_metrics,
        "sha256_basis": {
            "serialization": "json-sort-keys-compact-ascii",
            "excluded_fields": ["sha256"],
            "scope": "complete_regional_deviation_payload",
        },
    }
    result["sha256"] = _canonical_sha256(result)
    return result


# These names make the evidence-first contract discoverable without replacing the
# pre-existing mesh comparison API.
compare_semantic_regional_deviation = compare_regional_deviation
regional_deviation_artifact = compare_regional_deviation


def _regional_metadata(evidence: dict[str, Any]) -> dict[str, Any]:
    required = ("units", "coordinate_frame", "tessellation_tolerance_mm", "projection_tolerance_mm")
    missing = [field for field in required if field not in evidence]
    if missing:
        raise ValueError(f"regional deviation evidence missing metadata: {', '.join(missing)}")
    if evidence["units"] != "mm" or not isinstance(evidence["coordinate_frame"], str) or not evidence["coordinate_frame"]:
        raise ValueError("regional deviation evidence requires units='mm' and a coordinate frame")
    tessellation_tolerance = _finite_number(
        evidence["tessellation_tolerance_mm"], "tessellation_tolerance_mm"
    )
    projection_tolerance = _finite_number(
        evidence["projection_tolerance_mm"], "projection_tolerance_mm"
    )
    if tessellation_tolerance <= 0.0:
        raise ValueError("tessellation_tolerance_mm must be positive")
    if projection_tolerance <= 0.0:
        raise ValueError("projection_tolerance_mm must be positive")
    return {
        "units": "mm",
        "coordinate_frame": evidence["coordinate_frame"],
        "tessellation_tolerance_mm": tessellation_tolerance,
        "projection_tolerance_mm": projection_tolerance,
    }


def _regional_records(
    evidence: dict[str, Any], field: str, identifier_field: str
) -> dict[str, dict[str, Any]]:
    raw_records = evidence.get(field)
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError(f"regional deviation evidence requires non-empty {field}")
    records: dict[str, dict[str, Any]] = {}
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        required = ("region_id", "semantic_role", identifier_field, "sample_count", "weight", "samples")
        missing = [name for name in required if name not in raw_record]
        if missing:
            raise ValueError(f"{field}[{index}] missing: {', '.join(missing)}")
        region_id = raw_record["region_id"]
        if not isinstance(region_id, str) or not region_id or region_id in records:
            raise ValueError(f"{field} has duplicate or invalid region_id")
        if not isinstance(raw_record["semantic_role"], str) or not raw_record["semantic_role"]:
            raise ValueError(f"{field}[{index}] has invalid semantic_role")
        if not isinstance(raw_record[identifier_field], str) or not raw_record[identifier_field]:
            raise ValueError(f"{field}[{index}] has invalid {identifier_field}")
        sample_count = raw_record["sample_count"]
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
            raise ValueError(f"{field}[{index}] has invalid sample_count")
        weight = _finite_number(raw_record["weight"], f"{field}[{index}].weight")
        if weight <= 0.0:
            raise ValueError(f"{field}[{index}] weight must be positive")
        samples = raw_record["samples"]
        if not isinstance(samples, list) or not samples or len(samples) != sample_count:
            raise ValueError(f"{field}[{index}] sample_count does not match non-empty samples")
        records[region_id] = {
            "region_id": region_id,
            "semantic_role": raw_record["semantic_role"],
            identifier_field: raw_record[identifier_field],
            "sample_count": sample_count,
            "weight": weight,
            "samples": samples,
        }
    return records


def _regional_mappings(
    evidence: dict[str, Any], source_regions: dict[str, dict[str, Any]], reconstruction_regions: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    raw_mappings = evidence.get("region_mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise ValueError("regional deviation evidence requires non-empty region_mappings")
    mapped_source: set[str] = set()
    mapped_reconstruction: set[str] = set()
    mappings = []
    for index, mapping in enumerate(raw_mappings):
        if not isinstance(mapping, dict):
            raise ValueError(f"region_mappings[{index}] must be an object")
        required = ("source_region_id", "reconstruction_region_id", "semantic_role")
        if any(field not in mapping for field in required):
            raise ValueError(f"region_mappings[{index}] is incomplete")
        source_id = _region_identifier(
            mapping["source_region_id"],
            f"region_mappings[{index}].source_region_id",
        )
        reconstruction_id = _region_identifier(
            mapping["reconstruction_region_id"],
            f"region_mappings[{index}].reconstruction_region_id",
        )
        semantic_role = _region_identifier(
            mapping["semantic_role"],
            f"region_mappings[{index}].semantic_role",
        )
        if source_id not in source_regions or reconstruction_id not in reconstruction_regions:
            raise ValueError(f"region_mappings[{index}] references an unknown region")
        if source_id in mapped_source or reconstruction_id in mapped_reconstruction:
            raise ValueError("region_mappings must be one-to-one")
        source = source_regions[source_id]
        reconstruction = reconstruction_regions[reconstruction_id]
        if semantic_role != source["semantic_role"] or semantic_role != reconstruction["semantic_role"]:
            raise ValueError("region mapping semantic_role does not match source/reconstruction role")
        mapped_source.add(source_id)
        mapped_reconstruction.add(reconstruction_id)
        mappings.append(
            {
                "source_region_id": source_id,
                "reconstruction_region_id": reconstruction_id,
                "semantic_role": semantic_role,
            }
        )
    failures = [
        {"code": "missing_source_role_mapping", "id": region_id}
        for region_id in sorted(set(source_regions) - mapped_source)
    ]
    failures.extend(
        {"code": "missing_source_role_mapping", "id": region_id}
        for region_id in sorted(set(reconstruction_regions) - mapped_reconstruction)
    )
    return sorted(mappings, key=lambda item: item["source_region_id"]), failures


def _region_samples(record: dict[str, Any], label: str) -> tuple[np.ndarray, np.ndarray]:
    sample_records = record["samples"]
    seen: set[str] = set()
    parsed = []
    for index, sample in enumerate(sample_records):
        if not isinstance(sample, dict):
            raise ValueError(f"{label} region sample {index} must be an object")
        sample_id = sample.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen:
            raise ValueError(f"{label} region has duplicate or invalid sample_id")
        seen.add(sample_id)
        point = _point(sample.get("point_mm"), f"{label} sample {sample_id}.point_mm")
        normal = _normal(sample.get("normal"), f"{label} sample {sample_id}.normal")
        parsed.append((sample_id, point, normal))
    parsed.sort(key=lambda item: item[0])
    unique_samples = []
    seen_measurements: set[tuple[float, ...]] = set()
    for _, point, normal in parsed:
        measurement = tuple(float(value) for value in np.concatenate((point, normal)))
        if measurement in seen_measurements:
            continue
        seen_measurements.add(measurement)
        unique_samples.append((point, normal))
    return (
        np.asarray([item[0] for item in unique_samples]),
        np.asarray([item[1] for item in unique_samples]),
    )


def _terminal_evidence_failures(evidence: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    root_gates = evidence.get("root_gates")
    if not isinstance(root_gates, list) or not root_gates:
        raise ValueError("regional deviation evidence requires non-empty root_gates")
    seen_root_gates: set[str] = set()
    for gate in root_gates:
        gate_id, passed = _named_boolean(gate, "gate_id", "passed", "root_gates")
        if gate_id in seen_root_gates:
            raise ValueError("root_gates contains duplicate gate_id")
        seen_root_gates.add(gate_id)
        if not passed:
            failures.append({"code": "failed_root_gate", "id": gate_id})
    for field in ("material_checks", "thickness_checks"):
        checks = evidence.get(field)
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"regional deviation evidence requires non-empty {field}")
        seen: set[str] = set()
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get("check_id"), str) or not check["check_id"]:
                raise ValueError(f"{field} contains an invalid check_id")
            check_id = check["check_id"]
            if check_id in seen:
                raise ValueError(f"{field} contains duplicate check_id")
            seen.add(check_id)
            if field == "material_checks":
                expected = check.get("source_present")
                observed = check.get("reconstruction_present")
                if not isinstance(expected, bool) or not isinstance(observed, bool):
                    raise ValueError("material_checks require boolean source_present/reconstruction_present")
                if not expected and observed:
                    failures.append({"code": "false_material", "id": check_id})
                elif expected and not observed:
                    failures.append({"code": "missing_material", "id": check_id})
            else:
                source_thickness = _finite_number(check.get("source_thickness_mm"), f"thickness_checks.{check_id}.source_thickness_mm")
                reconstruction_thickness = _finite_number(check.get("reconstruction_thickness_mm"), f"thickness_checks.{check_id}.reconstruction_thickness_mm")
                if source_thickness <= 0.0 or reconstruction_thickness <= 0.0:
                    failures.append({"code": "nonpositive_thickness", "id": check_id})
    return sorted(failures, key=lambda item: (item["code"], item["id"]))


def _station_metrics(
    evidence: dict[str, Any],
    source_regions: dict[str, dict[str, Any]],
    reconstruction_regions: dict[str, dict[str, Any]],
    mappings: list[dict[str, str]],
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    stations = evidence.get("stations")
    if not isinstance(stations, list) or not stations:
        raise ValueError("regional deviation evidence requires non-empty stations")
    results = []
    failures = []
    seen: set[str] = set()
    approved_pairs = {
        (mapping["source_region_id"], mapping["reconstruction_region_id"]): mapping[
            "semantic_role"
        ]
        for mapping in mappings
    }
    for station in stations:
        if not isinstance(station, dict) or not isinstance(station.get("station_id"), str) or not station["station_id"]:
            raise ValueError("stations contains an invalid station_id")
        station_id = station["station_id"]
        if station_id in seen:
            raise ValueError("stations contains duplicate station_id")
        seen.add(station_id)
        source_region_id = _region_identifier(
            station.get("source_region_id"),
            f"stations.{station_id}.source_region_id",
        )
        reconstruction_region_id = _region_identifier(
            station.get("reconstruction_region_id"),
            f"stations.{station_id}.reconstruction_region_id",
        )
        if source_region_id not in source_regions or reconstruction_region_id not in reconstruction_regions:
            raise ValueError(f"station {station_id} references an unknown region")
        source = source_regions[source_region_id]
        reconstruction = reconstruction_regions[reconstruction_region_id]
        semantic_role = approved_pairs.get((source_region_id, reconstruction_region_id))
        if semantic_role is None:
            raise ValueError(
                f"station {station_id} source/reconstruction regions must use an approved region_mapping"
            )
        if (
            source["semantic_role"] != semantic_role
            or reconstruction["semantic_role"] != semantic_role
        ):
            raise ValueError(
                f"station {station_id} source/reconstruction semantic_role must match its region_mapping"
            )
        attributes = _metric_attributes(metadata, [source["source_id"]], [reconstruction["reconstruction_id"]])
        source_loop = _point_records(station.get("source_loop_samples"), f"station {station_id} source loop")
        reconstruction_loop = _point_records(station.get("reconstruction_loop_samples"), f"station {station_id} reconstruction loop")
        source_camber = _point_records(station.get("source_camber_samples"), f"station {station_id} source camber")
        reconstruction_camber = _point_records(station.get("reconstruction_camber_samples"), f"station {station_id} reconstruction camber")
        source_thickness = _thickness_records(station.get("source_normal_thickness_samples"), f"station {station_id} source thickness")
        reconstruction_thickness = _thickness_records(station.get("reconstruction_normal_thickness_samples"), f"station {station_id} reconstruction thickness")
        if any(value <= 0.0 for value in source_thickness.values()):
            failures.append({"code": "nonpositive_thickness", "id": f"{station_id}:source"})
        if any(value <= 0.0 for value in reconstruction_thickness.values()):
            failures.append({"code": "nonpositive_thickness", "id": f"{station_id}:reconstruction"})
        _same_sample_ids(source_camber, reconstruction_camber, f"station {station_id} camber")
        _same_sample_ids(source_thickness, reconstruction_thickness, f"station {station_id} thickness")
        camber_distances = np.linalg.norm(
            np.asarray([source_camber[key] for key in sorted(source_camber)])
            - np.asarray([reconstruction_camber[key] for key in sorted(source_camber)]), axis=1
        )
        thickness_residuals = np.asarray([
            reconstruction_thickness[key] - source_thickness[key] for key in sorted(source_thickness)
        ])
        hausdorff = _hausdorff(
            np.asarray(list(source_loop.values())), np.asarray(list(reconstruction_loop.values()))
        )
        results.append(
            {
                "station_id": station_id,
                "source_region_id": source_region_id,
                "reconstruction_region_id": reconstruction_region_id,
                "loop_hausdorff_mm": _single_metric(hausdorff, "mm", "explicit_station_loop_hausdorff", attributes),
                "camber_rms_mm": _single_metric(_rms(camber_distances), "mm", "paired_explicit_station_camber_rms", attributes),
                "normal_thickness_residual_rms_mm": _single_metric(_rms(thickness_residuals), "mm", "paired_explicit_station_normal_thickness_residual", attributes),
            }
        )
    return sorted(results, key=lambda item: item["station_id"]), failures


def _region_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _silhouette_metrics(evidence: dict[str, Any], metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    silhouettes = evidence.get("silhouettes")
    if not isinstance(silhouettes, dict):
        raise ValueError("regional deviation evidence requires silhouettes")
    result = {}
    for kind in ("top", "meridional"):
        silhouette = silhouettes.get(kind)
        if not isinstance(silhouette, dict):
            raise ValueError(f"silhouettes.{kind} must be an object")
        source_id = silhouette.get("source_id")
        reconstruction_id = silhouette.get("reconstruction_id")
        if not isinstance(source_id, str) or not source_id or not isinstance(reconstruction_id, str) or not reconstruction_id:
            raise ValueError(f"silhouettes.{kind} requires source_id/reconstruction_id")
        source_points = _point_records(silhouette.get("source_samples"), f"{kind} source silhouette", dimensions=2)
        reconstruction_points = _point_records(silhouette.get("reconstruction_samples"), f"{kind} reconstruction silhouette", dimensions=2)
        result[kind] = _single_metric(
            _hausdorff(np.asarray(list(source_points.values())), np.asarray(list(reconstruction_points.values()))),
            "mm",
            f"explicit_{kind}_silhouette_hausdorff",
            _metric_attributes(metadata, [source_id], [reconstruction_id]),
        )
    return result


def _point_records(raw_samples: Any, label: str, *, dimensions: int = 3) -> dict[str, np.ndarray]:
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError(f"{label} must be non-empty")
    records: dict[str, np.ndarray] = {}
    for sample in raw_samples:
        if not isinstance(sample, dict) or not isinstance(sample.get("sample_id"), str) or not sample["sample_id"]:
            raise ValueError(f"{label} has an invalid sample_id")
        sample_id = sample["sample_id"]
        if sample_id in records:
            raise ValueError(f"{label} has duplicate sample_id")
        value = sample.get("point_mm")
        if dimensions == 3:
            records[sample_id] = _point(value, f"{label}.{sample_id}.point_mm")
        else:
            records[sample_id] = _vector(value, dimensions, f"{label}.{sample_id}.point_mm")
    return {key: records[key] for key in sorted(records)}


def _thickness_records(raw_samples: Any, label: str) -> dict[str, float]:
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError(f"{label} must be non-empty")
    records = {}
    for sample in raw_samples:
        if not isinstance(sample, dict) or not isinstance(sample.get("sample_id"), str) or not sample["sample_id"]:
            raise ValueError(f"{label} has an invalid sample_id")
        sample_id = sample["sample_id"]
        if sample_id in records:
            raise ValueError(f"{label} has duplicate sample_id")
        thickness = _finite_number(sample.get("thickness_mm"), f"{label}.{sample_id}.thickness_mm")
        records[sample_id] = thickness
    return {key: records[key] for key in sorted(records)}


def _same_sample_ids(first: dict[str, Any], second: dict[str, Any], label: str) -> None:
    if set(first) != set(second):
        raise ValueError(f"{label} source/reconstruction sample ids do not match")


def _metric_attributes(metadata: dict[str, Any], source_ids: list[str], reconstruction_ids: list[str]) -> dict[str, Any]:
    return {
        "coordinate_frame": metadata["coordinate_frame"],
        "source_ids": sorted(source_ids),
        "reconstruction_ids": sorted(reconstruction_ids),
        "tessellation_tolerance_mm": _round(metadata["tessellation_tolerance_mm"]),
        "projection_tolerance_mm": _round(metadata["projection_tolerance_mm"]),
        "confidence": "explicit_measurement_evidence",
    }


def _metric_distribution(values: np.ndarray, units: str, method: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "units": units,
        "method": method,
        **attributes,
        "minimum": _round(float(np.min(values))),
        "median": _round(float(np.median(values))),
        "rms": _round(_rms(values)),
        "p95": _round(float(np.percentile(values, 95))),
        "maximum": _round(float(np.max(values))),
    }


def _bidirectional_metric_distribution(
    source_values: np.ndarray,
    reconstruction_values: np.ndarray,
    units: str,
    method: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    source_summary = _regional_distribution_summary(source_values)
    reconstruction_summary = _regional_distribution_summary(reconstruction_values)
    return {
        "units": units,
        "method": method,
        **attributes,
        "directional_aggregation": {
            "method": "independent_directional_statistics_fixed_weights",
            "source_to_reconstruction_weight": _DIRECTIONAL_WEIGHT,
            "reconstruction_to_source_weight": _DIRECTIONAL_WEIGHT,
        },
        "minimum": _round(
            _fixed_directional_mean(
                source_summary["minimum"], reconstruction_summary["minimum"]
            )
        ),
        "median": _round(
            _fixed_directional_mean(
                source_summary["median"], reconstruction_summary["median"]
            )
        ),
        "rms": _round(
            math.sqrt(
                _DIRECTIONAL_WEIGHT * source_summary["rms"] ** 2
                + _DIRECTIONAL_WEIGHT * reconstruction_summary["rms"] ** 2
            )
        ),
        "p95": _round(
            _fixed_directional_mean(
                source_summary["p95"], reconstruction_summary["p95"]
            )
        ),
        "maximum": _round(
            _fixed_directional_mean(
                source_summary["maximum"], reconstruction_summary["maximum"]
            )
        ),
    }


def _regional_distribution_summary(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)),
        "median": float(np.median(values)),
        "rms": _rms(values),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(np.max(values)),
    }


def _fixed_directional_mean(source_value: float, reconstruction_value: float) -> float:
    return (
        _DIRECTIONAL_WEIGHT * source_value
        + _DIRECTIONAL_WEIGHT * reconstruction_value
    )


def _single_metric(value: float, units: str, method: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return {"value": _round(value), "units": units, "method": method, **attributes}


def _regional_nearest(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    squared = np.sum((first[:, None, :] - second[None, :, :]) ** 2, axis=2)
    matches = np.argmin(squared, axis=1)
    return np.sqrt(squared[np.arange(len(first)), matches]), matches


def _normal_angles(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    cosines = np.clip(np.sum(first * second, axis=1), -1.0, 1.0)
    return np.degrees(np.arccos(cosines))


def _hausdorff(first: np.ndarray, second: np.ndarray) -> float:
    first_distances, _ = _regional_nearest(first, second)
    second_distances, _ = _regional_nearest(second, first)
    return float(max(np.max(first_distances), np.max(second_distances)))


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(values, dtype=float) ** 2)))


def _weighted_rms(terms: list[tuple[float, float]]) -> float:
    if not terms or any(weight <= 0.0 for _, weight in terms):
        raise ValueError("regional deviation requires positive stored metric weights")
    numerator = sum(value * value * weight for value, weight in terms)
    denominator = sum(weight for _, weight in terms)
    return math.sqrt(numerator / denominator)


def _point(value: Any, label: str) -> np.ndarray:
    return _vector(value, 3, label)


def _normal(value: Any, label: str) -> np.ndarray:
    normal = _vector(value, 3, label)
    magnitude = float(np.linalg.norm(normal))
    if magnitude <= 1.0e-12:
        raise ValueError(f"{label} must be nonzero")
    return normal / magnitude


def _vector(value: Any, dimensions: int, label: str) -> np.ndarray:
    if not isinstance(value, (list, tuple)) or len(value) != dimensions:
        raise ValueError(f"{label} must be a {dimensions}-component vector")
    parsed = np.asarray([_finite_number(item, label) for item in value], dtype=float)
    return parsed


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _named_boolean(record: Any, id_field: str, value_field: str, label: str) -> tuple[str, bool]:
    if not isinstance(record, dict) or not isinstance(record.get(id_field), str) or not record[id_field]:
        raise ValueError(f"{label} contains an invalid {id_field}")
    if not isinstance(record.get(value_field), bool):
        raise ValueError(f"{label} contains an invalid {value_field}")
    return record[id_field], record[value_field]


def _round(value: float) -> float:
    return round(float(value), 9)


def _canonical_sha256(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(serialized.encode("ascii")).hexdigest()


def _read_binary_stl(payload: bytes, triangle_count: int) -> TriangleMesh:
    vertices: list[list[float]] = []
    triangles: list[list[int]] = []
    normals: list[list[float]] = []
    offset = 84
    for triangle_index in range(triangle_count):
        values = struct.unpack_from("<12fH", payload, offset)
        normal = [float(value) for value in values[:3]]
        start = len(vertices)
        vertices.extend(
            [[float(values[3 + vertex * 3 + axis]) for axis in range(3)] for vertex in range(3)]
        )
        triangles.append([start, start + 1, start + 2])
        normals.append(normal)
        offset += 50
    return _mesh_arrays(vertices, triangles, normals)


def _read_ascii_stl(payload: str) -> TriangleMesh:
    vertices: list[list[float]] = []
    triangles: list[list[int]] = []
    normals: list[list[float]] = []
    current_normal = [0.0, 0.0, 0.0]
    current_vertices: list[list[float]] = []
    for raw_line in payload.splitlines():
        tokens = raw_line.strip().split()
        if len(tokens) == 5 and tokens[:2] == ["facet", "normal"]:
            current_normal = [float(value) for value in tokens[2:5]]
        elif len(tokens) == 4 and tokens[0] == "vertex":
            current_vertices.append([float(value) for value in tokens[1:4]])
            if len(current_vertices) == 3:
                start = len(vertices)
                vertices.extend(current_vertices)
                triangles.append([start, start + 1, start + 2])
                normals.append(current_normal)
                current_vertices = []
    if not triangles:
        raise ValueError("STL contains no triangles")
    return _mesh_arrays(vertices, triangles, normals)


def _mesh_arrays(vertices: list[list[float]], triangles: list[list[int]], normals: list[list[float]]) -> TriangleMesh:
    vertex_array = np.asarray(vertices, dtype=float)
    triangle_array = np.asarray(triangles, dtype=np.int32)
    normal_array = np.asarray(normals, dtype=float)
    lengths = np.linalg.norm(normal_array, axis=1)
    missing = lengths <= 1.0e-12
    for index in np.flatnonzero(missing):
        normal_array[index] = _triangle_normal(vertex_array[triangle_array[index]])
    lengths = np.linalg.norm(normal_array, axis=1)
    normal_array = normal_array / np.maximum(lengths[:, None], 1.0e-12)
    return TriangleMesh(vertex_array, triangle_array, normal_array)


def _triangle_normal(vertices: np.ndarray) -> np.ndarray:
    normal = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
    length = np.linalg.norm(normal)
    return normal / max(float(length), 1.0e-12)


def _triangle_centroids(mesh: TriangleMesh) -> np.ndarray:
    return np.mean(mesh.vertices[mesh.triangles], axis=1)


def _bounded_triangle_centroids(mesh: TriangleMesh, limit: int) -> np.ndarray:
    centroids = _triangle_centroids(mesh)
    if len(centroids) <= int(limit):
        return centroids
    indices = np.linspace(0, len(centroids) - 1, int(limit), dtype=np.int64)
    return centroids[indices]


def _rotate_points_about_z(points: np.ndarray, phase_deg: float) -> np.ndarray:
    angle = math.radians(float(phase_deg))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    rotated = points.copy()
    rotated[:, 0] = cosine * points[:, 0] - sine * points[:, 1]
    rotated[:, 1] = sine * points[:, 0] + cosine * points[:, 1]
    return rotated


def _rotation_z_matrix(phase_deg: float) -> list[list[float]]:
    angle = math.radians(float(phase_deg))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _nearest_distances(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    if len(first) == 0 or len(second) == 0:
        raise ValueError("deviation comparison requires non-empty meshes")
    if cKDTree is not None:
        distances, _ = cKDTree(second).query(first, k=1, workers=1)
        return np.asarray(distances, dtype=float)
    result = []
    for start in range(0, len(first), 256):  # pragma: no cover
        block = first[start : start + 256]
        squared = np.sum((block[:, None, :] - second[None, :, :]) ** 2, axis=2)
        result.extend(np.sqrt(np.min(squared, axis=1)))
    return np.asarray(result, dtype=float)


def _distribution(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {"minimum_mm": math.nan, "median_mm": math.nan, "rms_mm": math.nan, "p95_mm": math.nan, "maximum_mm": math.nan}
    return {
        "minimum_mm": round(float(np.min(finite)), 6),
        "median_mm": round(float(np.median(finite)), 6),
        "rms_mm": round(float(np.sqrt(np.mean(finite**2))), 6),
        "p95_mm": round(float(np.percentile(finite, 95)), 6),
        "maximum_mm": round(float(np.max(finite)), 6),
    }


def _mesh_properties(mesh: TriangleMesh) -> dict[str, Any]:
    triangles = mesh.vertices[mesh.triangles]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    signed_volumes = np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])) / 6.0
    return {
        "triangle_count": int(len(mesh.triangles)),
        "surface_area_mm2": round(float(np.sum(areas)), 6),
        "signed_volume_mm3": round(float(np.sum(signed_volumes)), 6),
        "centroid_mm": [round(float(value), 6) for value in np.mean(mesh.vertices, axis=0)],
    }


def _rz(vertices: np.ndarray) -> np.ndarray:
    radius = np.sqrt(vertices[:, 0] ** 2 + vertices[:, 1] ** 2)
    return np.column_stack((radius, vertices[:, 2]))


def _projected_hausdorff(first: np.ndarray, second: np.ndarray) -> float:
    return float(max(np.max(_nearest_distances(first, second)), np.max(_nearest_distances(second, first))))


def _section_residuals(source_vertices: np.ndarray, reconstruction_vertices: np.ndarray) -> list[dict[str, Any]]:
    source_rz = _rz(source_vertices)
    reconstruction_rz = _rz(reconstruction_vertices)
    source_min, source_max = float(np.min(source_rz[:, 1])), float(np.max(source_rz[:, 1]))
    results = []
    for h in (0.0, 0.25, 0.5, 0.75, 1.0):
        z = source_min + h * (source_max - source_min)
        tolerance = max((source_max - source_min) * 0.03, 1.0e-6)
        first = source_rz[np.abs(source_rz[:, 1] - z) <= tolerance]
        second = reconstruction_rz[np.abs(reconstruction_rz[:, 1] - z) <= tolerance]
        residual = None if len(first) == 0 or len(second) == 0 else round(_projected_hausdorff(first, second), 6)
        results.append({"h": h, "source_z_mm": round(z, 6), "hausdorff_mm": residual})
    return results


def _heatmap_payload(mesh: TriangleMesh, errors: np.ndarray) -> dict[str, Any]:
    finite = errors[np.isfinite(errors)]
    clip = float(np.percentile(finite, 95)) if len(finite) else 0.0
    scale = max(clip, 1.0e-12)
    colors = [_turbo_like_color(min(max(float(error) / scale, 0.0), 1.0)) for error in errors]
    return {
        "contract_id": "impeller_v1_1_6_deviation_heatmap",
        "units": "mm",
        "vertices": [[round(float(value), 6) for value in point] for point in mesh.vertices],
        "triangles": mesh.triangles.tolist(),
        "errors_mm": [round(float(value), 6) for value in errors],
        "colors_rgb": colors,
        "legend": {
            **_distribution(errors),
            "clip_p95_mm": round(clip, 6),
            "clipped_for_color_only": True,
        },
    }


def _turbo_like_color(value: float) -> list[float]:
    stops = (
        (0.0, (0.10, 0.20, 0.72)),
        (0.25, (0.00, 0.72, 0.92)),
        (0.50, (0.15, 0.82, 0.35)),
        (0.75, (0.98, 0.84, 0.08)),
        (1.0, (0.86, 0.08, 0.08)),
    )
    for index in range(len(stops) - 1):
        left_value, left_color = stops[index]
        right_value, right_color = stops[index + 1]
        if value <= right_value:
            ratio = (value - left_value) / (right_value - left_value)
            return [round(left_color[axis] + ratio * (right_color[axis] - left_color[axis]), 6) for axis in range(3)]
    return list(stops[-1][1])
