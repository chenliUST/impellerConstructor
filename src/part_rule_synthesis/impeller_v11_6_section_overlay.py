from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np


CONTRACT_ID = "impeller_v1_1_6_section_overlay_r16_1"


class SectionOverlayError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason


def build_section_overlay_contract(
    mapping: Mapping[str, Any],
    surface_graph: Mapping[str, Any],
    *,
    generated_to_comparison_matrix: Sequence[Sequence[float]],
) -> dict[str, Any]:
    source_network = _source_network(mapping)
    generated_network = _generated_network(surface_graph)
    alignment = _matrix(generated_to_comparison_matrix)

    source_stations = []
    source_conformance_roles = {}
    for population, family in sorted(source_network["populations"].items()):
        for station in sorted(family["stations"], key=lambda item: float(item["active_h"])):
            station_key = (str(population), round(float(station["active_h"]), 9))
            source_roles = _source_curve_roles(station)
            source_conformance_roles[station_key] = source_roles
            station_record = {
                    "loop_id": _loop_id("source", population, station["active_h"]),
                    "source_loop_id": str(
                        station.get("source_loop_id")
                        or _loop_id("source", population, station["active_h"])
                    ),
                    "population": str(population),
                    "active_h": float(station["active_h"]),
                    "coordinate_frame": "canonical_comparison_frame_xyz_mm",
                    "authority": "authenticated_step_exact_section_loop",
                    "status": "AVAILABLE",
                    "support_profile_rz_mm": [
                        [float(value) for value in point]
                        for point in station.get("support_profile_rz_mm", ())
                    ],
                    "source_face_ids": _source_face_ids(station),
                    "points_xyz_mm": _points(
                        station["canonical_loop_points_xyz_mm"],
                        "source canonical loop",
                    ).tolist(),
                    "curve_roles": source_roles,
                    "source_tolerance_mm": float(
                        station.get("source_tolerance_mm", 0.0)
                    ),
                }
            source_stations.append(station_record)

    generated_stations = []
    generated_conformance_roles = {}
    for station in generated_network["generated_section_loops"]:
        population = str(station["population"])
        active_h = float(station["active_h"])
        station_key = (population, round(active_h, 9))
        generated_conformance_roles[station_key] = _generated_curve_roles(
            station, np.eye(4)
        )
        generated_stations.append(
            {
                "loop_id": _loop_id("generated", population, active_h),
                "population": population,
                "active_h": active_h,
                "coordinate_frame": "canonical_comparison_frame_xyz_mm",
                "authority": "reconstructed_surface_carrier_intersection",
                "status": "AVAILABLE",
                "points_xyz_mm": _transform(
                    _points(station["points_xyz_mm"], "generated surface intersection"),
                    alignment,
                ).tolist(),
                "curve_roles": _generated_curve_roles(station, alignment),
            }
        )

    source_keys = {_key(station) for station in source_stations}
    generated_keys = {_key(station) for station in generated_stations}
    if source_keys != generated_keys:
        raise SectionOverlayError(
            "v116_section_overlay_station_mismatch",
            "source and generated overlays do not expose the same population/span stations",
        )

    source_by_key = {_key(station): station for station in source_stations}
    generated_by_key = {_key(station): station for station in generated_stations}
    station_residuals = []
    for station_key in sorted(source_keys):
        source_station = source_by_key[station_key]
        generated_station = generated_by_key[station_key]
        source_roles = source_conformance_roles[station_key]
        generated_roles = generated_conformance_roles[station_key]
        if set(source_roles) != set(generated_roles):
            raise SectionOverlayError(
                "v116_section_overlay_role_mismatch",
                "source and generated overlays expose different curve roles",
            )
        role_residuals = {
            role: _bidirectional_polyline_residual(
                np.asarray(source_roles[role], dtype=float),
                np.asarray(generated_roles[role], dtype=float),
            )
            for role in sorted(source_roles)
        }
        maximum = max(
            residual["hausdorff_max_mm"] for residual in role_residuals.values()
        )
        residual_record = {
            "population": station_key[0],
            "active_h": station_key[1],
            "role_residuals": role_residuals,
            "hausdorff_max_mm": maximum,
            "source_tolerance_mm": source_station["source_tolerance_mm"],
        }
        source_station["generated_conformance"] = residual_record
        generated_station["source_conformance"] = residual_record
        station_residuals.append(residual_record)

    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "coordinate_frame": "canonical_comparison_frame_xyz_mm",
        "conformance_coordinate_frame": (
            "canonical_axis_frame_before_periodic_display_alignment"
        ),
        "source_alignment_applied": "source_to_canonical_once_upstream",
        "generated_alignment_applied": "canonical_to_periodic_comparison_once",
        "generated_to_comparison_matrix": alignment.tolist(),
        "source": {
            "status": "AVAILABLE",
            "authority": "authenticated_step_exact_section_loop",
            "stations": source_stations,
        },
        "generated": {
            "status": "AVAILABLE",
            "authority": "reconstructed_surface_carrier_intersection",
            "stations": generated_stations,
        },
        "station_residuals": station_residuals,
        "maximum_station_hausdorff_mm": max(
            record["hausdorff_max_mm"] for record in station_residuals
        ),
    }


def _source_network(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    provenance = mapping.get("section_provenance")
    network = provenance.get("direct_section_curve_network") if isinstance(provenance, Mapping) else None
    if not isinstance(network, Mapping) or network.get("status") != "PASS":
        raise SectionOverlayError(
            "v116_section_overlay_source_missing",
            "mapping lacks a passing direct source section curve network",
        )
    return network


def _generated_network(surface_graph: Mapping[str, Any]) -> Mapping[str, Any]:
    network = surface_graph.get("direct_section_curve_network")
    if not isinstance(network, Mapping):
        raise SectionOverlayError(
            "v116_section_overlay_generated_missing",
            "surface graph lacks generated carrier intersections",
        )
    loops = network.get("generated_section_loops")
    if not isinstance(loops, list) or not loops:
        raise SectionOverlayError(
            "v116_section_overlay_generated_missing",
            "surface graph generated no carrier intersections",
        )
    return network


def _matrix(value: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or np.any(~np.isfinite(matrix)):
        raise SectionOverlayError(
            "v116_section_overlay_frame_invalid",
            "generated comparison transform must be a finite 4x4 matrix",
        )
    return matrix


def _points(value: Any, name: str) -> np.ndarray:
    points = np.asarray(value, dtype=float)
    if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] != 3 or np.any(~np.isfinite(points)):
        raise SectionOverlayError(
            "v116_section_overlay_curve_invalid",
            f"{name} must contain at least two finite XYZ points",
        )
    return points


def _transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=float)])
    return (matrix @ homogeneous.T).T[:, :3]


def _key(station: Mapping[str, Any]) -> tuple[str, float]:
    return str(station["population"]), round(float(station["active_h"]), 9)


def _loop_id(authority: str, population: str, active_h: Any) -> str:
    return f"{authority}:{population}:h_{float(active_h):.9f}"


def _source_face_ids(station: Mapping[str, Any]) -> list[str]:
    curves = station.get("curves")
    if not isinstance(curves, Mapping):
        return []
    return sorted(
        {
            str(source_id)
            for curve in curves.values()
            if isinstance(curve, Mapping)
            for source_id in curve.get("source_face_ids", ())
        }
    )


def _source_curve_roles(station: Mapping[str, Any]) -> dict[str, list[list[float]]]:
    curves = station.get("curves")
    if not isinstance(curves, Mapping):
        return {
            "loop": _points(
                station["canonical_loop_points_xyz_mm"], "source canonical loop"
            ).tolist()
        }
    return {
        str(role): _points(curve["canonical_points_xyz_mm"], f"source {role}").tolist()
        for role, curve in sorted(curves.items())
        if isinstance(curve, Mapping)
    }


def _generated_curve_roles(
    station: Mapping[str, Any], alignment: np.ndarray
) -> dict[str, list[list[float]]]:
    rows = station.get("surface_curve_rows")
    if not isinstance(rows, Mapping):
        return {
            "loop": _transform(
                _points(station["points_xyz_mm"], "generated surface intersection"),
                alignment,
            ).tolist()
        }
    return {
        str(role): _transform(
            _points(points, f"generated {role}"), alignment
        ).tolist()
        for role, points in sorted(rows.items())
    }


def _bidirectional_polyline_residual(
    first: np.ndarray, second: np.ndarray
) -> dict[str, float]:
    first_to_second = _point_to_polyline_distances(first, second)
    second_to_first = _point_to_polyline_distances(second, first)
    return {
        "source_to_generated_max_mm": float(np.max(first_to_second)),
        "generated_to_source_max_mm": float(np.max(second_to_first)),
        "hausdorff_max_mm": float(
            max(np.max(first_to_second), np.max(second_to_first))
        ),
    }


def _point_to_polyline_distances(
    points: np.ndarray, polyline: np.ndarray
) -> np.ndarray:
    segments = polyline[1:] - polyline[:-1]
    lengths_sq = np.sum(segments * segments, axis=1)
    distances = []
    for point in points:
        fractions = np.divide(
            np.sum((point - polyline[:-1]) * segments, axis=1),
            lengths_sq,
            out=np.zeros_like(lengths_sq),
            where=lengths_sq > 1.0e-18,
        )
        fractions = np.clip(fractions, 0.0, 1.0)
        projections = polyline[:-1] + fractions[:, None] * segments
        distances.append(float(np.min(np.linalg.norm(projections - point, axis=1))))
    return np.asarray(distances, dtype=float)
