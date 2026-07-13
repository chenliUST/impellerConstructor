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
