from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_v10_closed_profile import Point3, build_closed_blade_section_profile


def build_v10_blade_face_network(
    *,
    blade_index: int,
    station_count: int,
    sample_count: int,
    root_radius_mm: float,
    tip_radius_mm: float,
    root_z_mm: float,
    tip_z_mm: float,
    thickness_mm: float,
    leading_radius_mm: float,
    trailing_radius_mm: float,
) -> dict[str, Any]:
    if station_count < 2:
        return _network_failure("v1_0_blade_face_network_failed", blade_index)

    profiles = []
    for station_index in range(station_count):
        fraction = station_index / (station_count - 1)
        radius = root_radius_mm + (tip_radius_mm - root_radius_mm) * fraction
        z_value = root_z_mm + (tip_z_mm - root_z_mm) * fraction
        profile = build_closed_blade_section_profile(
            station_index=station_index,
            station_count=station_count,
            center=(radius, 0.0, z_value),
            tangent=(0.0, 1.0, 0.0),
            radial=(1.0, 0.0, 0.0),
            thickness_mm=thickness_mm,
            leading_radius_mm=leading_radius_mm,
            trailing_radius_mm=trailing_radius_mm,
            sample_count=sample_count,
        )
        if profile["closed_profile_status"] != "PASS":
            return _network_failure(profile.get("failure_reason", "v1_0_blade_face_network_failed"), blade_index)
        profiles.append(profile)

    pressure_grid = [profile["curves"]["pressure_side_curve"] for profile in profiles]
    suction_grid = [profile["curves"]["suction_side_curve"] for profile in profiles]
    leading_grid = [profile["curves"]["leading_edge_cap_curve"] for profile in profiles]
    trailing_grid = [profile["curves"]["trailing_edge_cap_curve"] for profile in profiles]
    root_loop = profiles[0]["closed_loop"]
    tip_loop = profiles[-1]["closed_loop"]
    root_face_loop = root_loop[:-1]
    tip_face_loop = tip_loop[:-1]
    root_segments = _profile_edge_segments(profiles[0])
    tip_segments = _profile_edge_segments(profiles[-1])
    root_offset = max(thickness_mm * 0.18, 1.0)
    tip_offset = max(thickness_mm * 0.18, 1.0)

    faces = [
        _face(
            face_id=f"blade_{blade_index}_pressure_surface",
            face_family="blade_pressure",
            role="pressure_surface",
            uv_grid=pressure_grid,
            boundary_roles={
                "u_min": "root_profile_pressure_edge",
                "u_max": "tip_profile_pressure_edge",
                "v_min": "leading_edge_pressure_boundary",
                "v_max": "trailing_edge_pressure_boundary",
            },
            edge_samples={
                "root_profile_pressure_edge": pressure_grid[0],
                "tip_profile_pressure_edge": pressure_grid[-1],
                "leading_edge_pressure_boundary": _column(pressure_grid, 0),
                "trailing_edge_pressure_boundary": _column(pressure_grid, -1),
            },
            continuity_targets=["G1_to_leading_edge", "G1_to_trailing_edge", "G1_to_root", "G1_to_tip"],
        ),
        _face(
            face_id=f"blade_{blade_index}_suction_surface",
            face_family="blade_suction",
            role="suction_surface",
            uv_grid=suction_grid,
            boundary_roles={
                "u_min": "root_profile_suction_edge",
                "u_max": "tip_profile_suction_edge",
                "v_min": "trailing_edge_suction_boundary",
                "v_max": "leading_edge_suction_boundary",
            },
            edge_samples={
                "root_profile_suction_edge": suction_grid[0],
                "tip_profile_suction_edge": suction_grid[-1],
                "trailing_edge_suction_boundary": _column(suction_grid, 0),
                "leading_edge_suction_boundary": _column(suction_grid, -1),
            },
            continuity_targets=["G1_to_leading_edge", "G1_to_trailing_edge", "G1_to_root", "G1_to_tip"],
        ),
        _face(
            face_id=f"blade_{blade_index}_leading_edge_surface",
            face_family="blade_leading_edge",
            role="leading_edge_surface",
            uv_grid=leading_grid,
            boundary_roles={
                "u_min": "root_profile_leading_cap",
                "u_max": "tip_profile_leading_cap",
                "v_min": "suction_side_leading_boundary",
                "v_max": "pressure_side_leading_boundary",
            },
            edge_samples={
                "root_profile_leading_cap": leading_grid[0],
                "tip_profile_leading_cap": leading_grid[-1],
                "suction_side_leading_boundary": _column(leading_grid, 0),
                "pressure_side_leading_boundary": _column(leading_grid, -1),
            },
            continuity_targets=["G1_to_pressure_surface", "G1_to_suction_surface"],
        ),
        _face(
            face_id=f"blade_{blade_index}_trailing_edge_surface",
            face_family="blade_trailing_edge",
            role="trailing_edge_surface",
            uv_grid=trailing_grid,
            boundary_roles={
                "u_min": "root_profile_trailing_cap",
                "u_max": "tip_profile_trailing_cap",
                "v_min": "pressure_side_trailing_boundary",
                "v_max": "suction_side_trailing_boundary",
            },
            edge_samples={
                "root_profile_trailing_cap": trailing_grid[0],
                "tip_profile_trailing_cap": trailing_grid[-1],
                "pressure_side_trailing_boundary": _column(trailing_grid, 0),
                "suction_side_trailing_boundary": _column(trailing_grid, -1),
            },
            continuity_targets=["G1_to_pressure_surface", "G1_to_suction_surface"],
        ),
        _face(
            face_id=f"blade_{blade_index}_tip_surface",
            face_family="blade_tip",
            role="tip_surface",
            uv_grid=[tip_face_loop, _offset_loop(tip_face_loop, (0.0, 0.0, tip_offset))],
            boundary_roles={
                "u_min": "tip_closed_profile",
                "u_max": "tip_material_side_reference",
                "v_min": "tip_loop_start",
                "v_max": "tip_loop_end",
            },
            edge_samples={
                "tip_closed_profile": tip_face_loop,
                **{f"tip_{name}": samples for name, samples in tip_segments.items()},
                **tip_segments,
            },
            continuity_targets=["G1_to_pressure_surface", "G1_to_suction_surface", "G1_to_edge_faces"],
        ),
        _face(
            face_id=f"blade_{blade_index}_root_annular_surface",
            face_family="blade_root",
            role="root_annular_surface",
            uv_grid=[root_face_loop, _offset_loop(root_face_loop, (0.0, 0.0, -root_offset))],
            boundary_roles={
                "u_min": "root_closed_profile",
                "u_max": "hub_attachment_ring",
                "v_min": "root_loop_start",
                "v_max": "root_loop_end",
            },
            edge_samples={
                "root_closed_profile": root_face_loop,
                **{f"root_{name}": samples for name, samples in root_segments.items()},
                **root_segments,
            },
            continuity_targets=["G1_to_pressure_surface", "G1_to_suction_surface", "G1_to_hub"],
            display={
                "inspection_class": "root_to_hub_native_root_face",
                "color": "#ff00cc",
                "wire_color": "#fff200",
            },
        ),
    ]

    return {
        "blade_face_network_status": "PASS",
        "blade_index": blade_index,
        "closed_profile_count": len(profiles),
        "profiles": profiles,
        "faces": faces,
    }


def _face(
    *,
    face_id: str,
    face_family: str,
    role: str,
    uv_grid: list[list[Point3]],
    boundary_roles: dict[str, str],
    edge_samples: dict[str, list[Point3]],
    continuity_targets: list[str],
    display: dict[str, Any] | None = None,
) -> dict[str, Any]:
    face = {
        "id": face_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "degree_u": 3,
        "degree_v": 3,
        "boundary_roles": boundary_roles,
        "edge_samples": edge_samples,
        "continuity_targets": continuity_targets,
    }
    if display:
        face["display"] = display
    return face


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    first_row = uv_grid[0]
    last_row = uv_grid[-1]
    return [
        [first_row[0], first_row[len(first_row) // 2], first_row[-1]],
        [last_row[0], last_row[len(last_row) // 2], last_row[-1]],
    ]


def _column(grid: list[list[Point3]], index: int) -> list[Point3]:
    return [row[index] for row in grid]


def _profile_edge_segments(profile: dict[str, Any]) -> dict[str, list[Point3]]:
    curves = profile["curves"]
    return {
        "root_profile_pressure_edge": curves["pressure_side_curve"],
        "root_profile_suction_edge": curves["suction_side_curve"],
        "root_profile_leading_cap": curves["leading_edge_cap_curve"],
        "root_profile_trailing_cap": curves["trailing_edge_cap_curve"],
    }


def _offset_loop(loop: list[Point3], offset: Point3) -> list[Point3]:
    return [
        (point[0] + offset[0], point[1] + offset[1], point[2] + offset[2])
        for point in loop
    ]


def _network_failure(reason: str, blade_index: int) -> dict[str, Any]:
    return {
        "blade_face_network_status": "FAIL",
        "failure_reason": reason,
        "blade_index": blade_index,
        "closed_profile_count": 0,
        "profiles": [],
        "faces": [],
    }
