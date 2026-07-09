from __future__ import annotations

import copy
import math
from typing import Any


Point3 = list[float]

FACE_SPECS = {
    "pressure_side": {
        "surface_suffix": "pressure_surface",
        "face_family": "blade_pressure",
        "role": "blade_pressure",
        "edges": {
            "trailing": 0,
            "leading": -1,
        },
    },
    "suction_side": {
        "surface_suffix": "suction_surface",
        "face_family": "blade_suction",
        "role": "blade_suction",
        "edges": {
            "leading": 0,
            "trailing": -1,
        },
    },
    "leading_edge": {
        "surface_suffix": "leading_edge_surface",
        "face_family": "blade_leading_edge",
        "role": "blade_leading_edge",
        "edges": {
            "pressure": 0,
            "suction": -1,
        },
    },
    "trailing_edge": {
        "surface_suffix": "trailing_edge_surface",
        "face_family": "blade_trailing_edge",
        "role": "blade_trailing_edge",
        "edges": {
            "suction": 0,
            "pressure": -1,
        },
    },
}
FACE_ORDER = ["pressure_side", "suction_side", "leading_edge", "trailing_edge"]


def build_blade_faces_from_section_lattice(lattice: Any) -> dict[str, Any]:
    if not isinstance(lattice, dict):
        return _malformed("lattice must be a dict")
    if lattice.get("status") != "PASS":
        return {
            "status": "FAIL",
            "reason": "v1_0_3_section_lattice_failed",
            "surfaces": [],
        }

    validation = _validate_lattice(lattice)
    if validation["status"] == "FAIL":
        return validation

    surfaces: list[dict[str, Any]] = []
    for blade_index, blade in enumerate(lattice["blades"]):
        for segment_family in FACE_ORDER:
            surfaces.append(_surface_from_segment_family(blade, segment_family, blade_index))

    return {
        "status": "PASS",
        "surface_count": len(surfaces),
        "surfaces": surfaces,
    }


def _surface_from_segment_family(
    blade: dict[str, Any],
    segment_family: str,
    blade_index: int,
) -> dict[str, Any]:
    spec = FACE_SPECS[segment_family]
    uv_grid = [
        copy.deepcopy(section_loop["segments"][segment_family]["points"])
        for section_loop in blade["section_loops"]
    ]
    face_family = spec["face_family"]
    blade_class = blade["blade_class"]
    blade_pair_index = blade["blade_pair_index"]
    source_loop_ids = [_loop_id(section_loop) for section_loop in blade["section_loops"]]
    section_loop_source = _section_loop_source(blade)
    surface_id = f"blade_{blade_index}_{spec['surface_suffix']}"

    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": spec["role"],
        "blade_index": blade_index,
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "edge_samples": _edge_samples(uv_grid, spec["edges"]),
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh(uv_grid),
        "display": {"inspection_class": face_family},
        "source": {
            "section_loop_family_id": blade["section_loop_family_id"],
            "section_loop_source": section_loop_source,
            "source_loop_ids": source_loop_ids,
            "segment_family": segment_family,
            "segment_source": "section_loop_segments",
        },
        "transition_quality": _transition_quality(blade, segment_family, source_loop_ids),
    }


def _section_loop_source(blade: dict[str, Any]) -> str:
    blade_source = blade.get("source")
    if isinstance(blade_source, str):
        return blade_source
    section_loops = blade.get("section_loops")
    if isinstance(section_loops, list) and section_loops:
        loop_source = section_loops[0].get("source") if isinstance(section_loops[0], dict) else None
        if loop_source == "v1_0_3_nurbs_carrier_section_loop":
            return "v1_0_3_nurbs_carrier_section_lattice"
        if isinstance(loop_source, str):
            return loop_source
    return "v1_0_3_section_lattice"


def _validate_lattice(lattice: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(lattice.get("blades"), list) or not lattice["blades"]:
        return _malformed("blades must be a non-empty list")
    for blade_index, blade in enumerate(lattice["blades"]):
        if not isinstance(blade, dict):
            return _malformed(f"blades[{blade_index}] must be a dict")
        for key in ["blade_class", "blade_pair_index", "section_loop_family_id", "section_loops"]:
            if key not in blade:
                return _malformed(f"blades[{blade_index}].{key} is required")
        if not isinstance(blade["section_loops"], list) or len(blade["section_loops"]) < 2:
            return _malformed(f"blades[{blade_index}].section_loops must contain at least two loops")
        segment_sample_counts: dict[str, int] = {}
        for loop_index, section_loop in enumerate(blade["section_loops"]):
            loop_path = f"blades[{blade_index}].section_loops[{loop_index}]"
            if not isinstance(section_loop, dict):
                return _malformed(f"{loop_path} must be a dict")
            if "segments" not in section_loop or not isinstance(section_loop["segments"], dict):
                return _malformed(f"{loop_path}.segments is required")
            metrics = section_loop.get("metrics", {})
            if "metrics" in section_loop and not isinstance(metrics, dict):
                return _malformed(f"{loop_path}.metrics must be a dict when present")
            if "foldover_count" in metrics:
                foldover_count = metrics["foldover_count"]
                if not _is_non_negative_int(foldover_count):
                    return _malformed(f"{loop_path}.metrics.foldover_count must be a non-negative integer")
            for segment_family in FACE_SPECS:
                segment = section_loop["segments"].get(segment_family)
                if not isinstance(segment, dict):
                    return _malformed(f"{loop_path}.segments.{segment_family} is required")
                points = segment.get("points")
                if not isinstance(points, list) or len(points) < 2:
                    return _malformed(f"{loop_path}.segments.{segment_family}.points must contain at least two samples")
                for point_index, point in enumerate(points):
                    if not _is_numeric_3d_point(point):
                        return _malformed(
                            f"{loop_path}.segments.{segment_family}.points[{point_index}] must be a numeric 3D point"
                        )
                sample_count = len(points)
                if "sample_count" in segment:
                    declared_sample_count = segment["sample_count"]
                    if not _is_positive_int(declared_sample_count):
                        return _malformed(f"{loop_path}.segments.{segment_family}.sample_count must be a positive integer")
                    if declared_sample_count != sample_count:
                        return _malformed(
                            f"{loop_path}.segments.{segment_family}.sample_count must equal points length"
                        )
                if segment_family not in segment_sample_counts:
                    segment_sample_counts[segment_family] = sample_count
                elif segment_sample_counts[segment_family] != sample_count:
                    return _malformed(
                        f"blades[{blade_index}].segments.{segment_family} must be rectangular across section loops"
                    )
    return {"status": "PASS"}


def _edge_samples(uv_grid: list[list[Point3]], edge_columns: dict[str, int]) -> dict[str, list[Point3]]:
    edges = {
        "root": copy.deepcopy(uv_grid[0]),
        "tip": copy.deepcopy(uv_grid[-1]),
    }
    for edge_name, column_index in edge_columns.items():
        edges[edge_name] = copy.deepcopy(_column(uv_grid, column_index))
    return edges


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy(
        [
            [uv_grid[row_index][column_index] for column_index in column_indices]
            for row_index in row_indices
        ]
    )


def _quad_mesh(uv_grid: list[list[Point3]]) -> dict[str, Any]:
    quads = []
    for row_index in range(len(uv_grid) - 1):
        for column_index in range(len(uv_grid[row_index]) - 1):
            indices = [
                [row_index, column_index],
                [row_index + 1, column_index],
                [row_index + 1, column_index + 1],
                [row_index, column_index + 1],
            ]
            quads.append(
                {
                    "indices": indices,
                }
            )
    return {
        "strategy": "section_loop_shared_edge_review_grade_quad_mesh",
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]) if uv_grid else 0,
        "quad_count": len(quads),
        "quads": quads,
    }


def _transition_quality(
    blade: dict[str, Any],
    segment_family: str,
    source_loop_ids: list[str],
) -> dict[str, Any]:
    loops = blade["section_loops"]
    foldover_count = sum(loop.get("metrics", {}).get("foldover_count", 0) for loop in loops)
    sample_counts = [
        len(loop["segments"][segment_family]["points"])
        for loop in loops
    ]
    return {
        "foldover_count": foldover_count,
        "has_foldover": foldover_count > 0,
        "source_loop_count": len(loops),
        "source_loop_ids": copy.deepcopy(source_loop_ids),
        "segment_family": segment_family,
        "source_segment_ids": [
            f"{loop_id}.{segment_family}"
            for loop_id in source_loop_ids
        ],
        "min_segment_sample_count": min(sample_counts),
        "max_segment_sample_count": max(sample_counts),
    }


def _column(grid: list[list[Point3]], index: int) -> list[Point3]:
    return [row[index] for row in grid]


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    middle = count // 2
    indices = [0, middle, count - 1]
    return list(dict.fromkeys(indices))


def _is_numeric_3d_point(point: Any) -> bool:
    return (
        isinstance(point, list)
        and len(point) == 3
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in point
        )
    )


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _loop_id(section_loop: dict[str, Any]) -> str:
    blade_class = section_loop.get("blade_class", "blade")
    blade_pair_index = section_loop.get("blade_pair_index", "unknown")
    section_index = section_loop.get("section_index", "unknown")
    return f"{blade_class}_blade_{blade_pair_index}_section_loop_{section_index}"


def _malformed(details: str) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "reason": "v1_0_3_section_lattice_malformed",
        "details": details,
        "surfaces": [],
    }
