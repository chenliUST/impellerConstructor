from __future__ import annotations

import copy
import math
from typing import Any


def build_v10_4_hub_solid_faces(
    hub_surface: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    profile = _profile(hub_surface)
    bore_radius = _finite_float(parameters.get("mounting_bore_radius_mm"), 40.0)
    if bore_radius <= 0.0:
        bore_radius = 40.0

    main = copy.deepcopy(hub_surface)
    main["id"] = "hub_main_revolve_surface"
    main["role"] = "hub_main_revolve_surface"
    main["face_family"] = "hub"
    main["geometry_patch_version"] = "1.0.4"
    main["wireframe"] = {"enabled": True, "source": "uv_grid"}
    main["mesh"] = _quad_mesh(main.get("uv_grid", []), strategy="v1_0_4_hub_main_revolve_quad_mesh")
    main["display"] = {
        **copy.deepcopy(main.get("display", {})),
        "inspection_class": "hub",
        "visible_by_default": True,
    }

    quality = _hub_quality(profile)
    main["v1_0_4_hub_quality"] = copy.deepcopy(quality)
    if profile:
        main["profile_samples_rz"] = _profile_dicts(profile)
        main["support_profile_samples_rz"] = _profile_dicts(profile)

    faces = [main]
    if profile:
        bottom = profile[0]
        top = profile[-1]
        faces.extend(
            [
                _cap_face("hub_top_cap_surface", top, bore_radius),
                _cap_face("hub_bottom_cap_surface", bottom, bore_radius),
                _bore_wall(profile, bore_radius),
                _bore_edge("mounting_bore_top_edge_surface", top, bore_radius),
                _bore_edge("mounting_bore_bottom_edge_surface", bottom, bore_radius),
            ]
        )
    else:
        faces.extend(
            [
                _empty_surface("hub_top_cap_surface", "hub_cap"),
                _empty_surface("hub_bottom_cap_surface", "hub_cap"),
                _empty_bore_wall(bore_radius),
                _empty_surface("mounting_bore_top_edge_surface", "mounting_bore"),
                _empty_surface("mounting_bore_bottom_edge_surface", "mounting_bore"),
            ]
        )

    return {"faces": faces, "quality": quality}


def _hub_quality(profile: list[tuple[float, float]]) -> dict[str, Any]:
    residual = _linear_fit_residual(profile)
    status = "PASS" if residual >= 12.0 else "FAIL"
    return {
        "status": status,
        "reason": None if status == "PASS" else "v1_0_4_hub_profile_conical_fallback",
        "hub_profile_concavity_status": status,
        "hub_profile_conical_fallback": status != "PASS",
        "max_linear_fit_residual_mm": round(residual, 6),
        "profile_sample_count": len(profile),
    }


def _linear_fit_residual(profile: list[tuple[float, float]]) -> float:
    if len(profile) < 3:
        return 0.0
    count = len(profile)
    sum_z = sum(z_value for _, z_value in profile)
    sum_radius = sum(radius for radius, _ in profile)
    sum_zz = sum(z_value * z_value for _, z_value in profile)
    sum_zr = sum(z_value * radius for radius, z_value in profile)
    denominator = count * sum_zz - sum_z * sum_z
    if abs(denominator) <= 1.0e-9:
        return 0.0
    slope = (count * sum_zr - sum_z * sum_radius) / denominator
    intercept = (sum_radius - slope * sum_z) / count
    return max(abs(radius - (slope * z_value + intercept)) for radius, z_value in profile)


def _cap_face(surface_id: str, profile_point: tuple[float, float], bore_radius: float) -> dict[str, Any]:
    outer_radius, z_value = profile_point
    inner_radius = min(bore_radius, outer_radius)
    grid = []
    for radial_index in range(9):
        fraction = radial_index / 8
        radius = inner_radius + (outer_radius - inner_radius) * fraction
        grid.append(_circle_row(radius, z_value, 49))
    face = _surface(surface_id, "hub_cap", grid)
    face["edge_samples"] = {
        "mounting_bore_circle": copy.deepcopy(grid[0]),
        "outer_hub_circle": copy.deepcopy(grid[-1]),
    }
    return face


def _bore_wall(profile: list[tuple[float, float]], bore_radius: float) -> dict[str, Any]:
    z_values = [z_value for _, z_value in profile]
    z_min = min(z_values)
    z_max = max(z_values)
    grid = []
    for z_index in range(17):
        z_value = z_min + (z_max - z_min) * z_index / 16
        grid.append(_circle_row(bore_radius, z_value, 49))
    face = _surface("mounting_bore_inner_wall_surface", "mounting_bore", grid)
    face["edge_samples"] = {
        "bottom": copy.deepcopy(grid[0]),
        "top": copy.deepcopy(grid[-1]),
    }
    face["v1_0_4_bore_quality"] = {
        "status": "PASS",
        "reason": None,
        "radius_mm": round(bore_radius, 6),
        "z_min_mm": round(z_min, 6),
        "z_max_mm": round(z_max, 6),
    }
    return face


def _bore_edge(surface_id: str, profile_point: tuple[float, float], bore_radius: float) -> dict[str, Any]:
    _, z_value = profile_point
    edge_width = max(1.0, bore_radius * 0.025)
    grid = []
    for radial_index in range(3):
        radius = bore_radius + edge_width * radial_index / 2
        grid.append(_circle_row(radius, z_value, 49))
    face = _surface(surface_id, "mounting_bore", grid)
    face["edge_samples"] = {
        "mounting_bore_circle": copy.deepcopy(grid[0]),
        "relief_outer_circle": copy.deepcopy(grid[-1]),
    }
    return face


def _surface(surface_id: str, family: str, uv_grid: list[list[list[float]]]) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "role": surface_id,
        "face_family": family,
        "geometry_patch_version": "1.0.4",
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "edge_samples": {},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh(uv_grid, strategy="v1_0_4_hub_solid_quad_mesh"),
        "display": {"inspection_class": family, "visible_by_default": True},
    }


def _empty_surface(surface_id: str, family: str) -> dict[str, Any]:
    return _surface(surface_id, family, [])


def _empty_bore_wall(bore_radius: float) -> dict[str, Any]:
    face = _empty_surface("mounting_bore_inner_wall_surface", "mounting_bore")
    face["v1_0_4_bore_quality"] = {
        "status": "FAIL",
        "reason": "v1_0_4_hub_profile_missing",
        "radius_mm": round(bore_radius, 6),
    }
    return face


def _circle_row(radius: float, z_value: float, sample_count: int) -> list[list[float]]:
    return [
        [
            _clean(round(radius * math.cos(2.0 * math.pi * index / (sample_count - 1)), 9)),
            _clean(round(radius * math.sin(2.0 * math.pi * index / (sample_count - 1)), 9)),
            round(z_value, 9),
        ]
        for index in range(sample_count)
    ]


def _quad_mesh(uv_grid: list[list[list[float]]], *, strategy: str) -> dict[str, Any]:
    quads = []
    if uv_grid:
        for row_index in range(len(uv_grid) - 1):
            for column_index in range(len(uv_grid[row_index]) - 1):
                quads.append(
                    {
                        "indices": [
                            [row_index, column_index],
                            [row_index + 1, column_index],
                            [row_index + 1, column_index + 1],
                            [row_index, column_index + 1],
                        ]
                    }
                )
    return {
        "strategy": strategy,
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]) if uv_grid else 0,
        "quad_count": len(quads),
        "quads": quads,
    }


def _control_net(uv_grid: list[list[list[float]]]) -> list[list[list[float]]]:
    if not uv_grid:
        return []
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy([[uv_grid[row][column] for column in column_indices] for row in row_indices])


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    return list(dict.fromkeys([0, count // 2, count - 1]))


def _profile(hub_surface: dict[str, Any]) -> list[tuple[float, float]]:
    raw_samples = (
        hub_surface.get("profile_samples_rz")
        or hub_surface.get("support_profile_samples_rz")
        or []
    )
    profile: list[tuple[float, float]] = []
    for sample in raw_samples:
        if isinstance(sample, dict):
            radius = _finite_float(sample.get("radius_mm", sample.get("r_mm")), math.nan)
            z_value = _finite_float(sample.get("z_mm"), math.nan)
        else:
            radius = _finite_float(sample[0] if len(sample) > 0 else math.nan, math.nan)
            z_value = _finite_float(sample[1] if len(sample) > 1 else math.nan, math.nan)
        if math.isfinite(radius) and math.isfinite(z_value):
            profile.append((radius, z_value))
    return sorted(profile, key=lambda point: point[1])


def _profile_dicts(profile: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [
        {"radius_mm": round(radius, 9), "r_mm": round(radius, 9), "z_mm": round(z_value, 9)}
        for radius, z_value in profile
    ]


def _finite_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clean(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-12 else value
