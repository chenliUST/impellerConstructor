from __future__ import annotations

import math
from typing import Any

Point3 = tuple[float, float, float]
PointRZ = tuple[float, float]


def build_v10_hub_revolve_faces(
    *,
    outer_radius_mm: float,
    bore_radius_mm: float,
    height_mm: float,
    bottom_bevel_mm: float,
    bore_top_bevel_mm: float,
    bore_bottom_bevel_mm: float,
    theta_samples: int = 33,
) -> dict[str, Any]:
    if not _valid_domain(
        outer_radius_mm=outer_radius_mm,
        bore_radius_mm=bore_radius_mm,
        height_mm=height_mm,
        bottom_bevel_mm=bottom_bevel_mm,
        bore_top_bevel_mm=bore_top_bevel_mm,
        bore_bottom_bevel_mm=bore_bottom_bevel_mm,
        theta_samples=theta_samples,
    ):
        return {
            "hub_profile_status": "FAIL",
            "failure_reason": "v1_0_hub_profile_segment_failed",
            "faces": [],
            "profile_segments": {},
        }

    outer_radius = float(outer_radius_mm)
    bore_radius = float(bore_radius_mm)
    height = float(height_mm)
    bottom_bevel = float(bottom_bevel_mm)
    bore_top_bevel = float(bore_top_bevel_mm)
    bore_bottom_bevel = float(bore_bottom_bevel_mm)

    profile_segments = {
        "hub_main_revolve_surface": [(outer_radius, bottom_bevel), (outer_radius, height)],
        "hub_top_face": [(bore_radius + bore_top_bevel, height), (outer_radius, height)],
        "hub_bottom_face": [(bore_radius + bore_bottom_bevel, 0.0), (outer_radius - bottom_bevel, 0.0)],
        "hub_bottom_outer_bevel_surface": [
            (outer_radius - bottom_bevel, 0.0),
            (outer_radius, bottom_bevel),
        ],
        "mounting_bore_cylinder_surface": [
            (bore_radius, bore_bottom_bevel),
            (bore_radius, height - bore_top_bevel),
        ],
        "mounting_bore_top_bevel_surface": [
            (bore_radius, height - bore_top_bevel),
            (bore_radius + bore_top_bevel, height),
        ],
        "mounting_bore_bottom_bevel_surface": [
            (bore_radius, bore_bottom_bevel),
            (bore_radius + bore_bottom_bevel, 0.0),
        ],
    }

    faces = [
        _face(
            face_id="hub_main_revolve_surface",
            face_family="hub_shell",
            role="outer_hub_shell",
            profile_segment_rz=profile_segments["hub_main_revolve_surface"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "hub_bottom_outer_bevel", "u_max": "hub_top_outer_edge"},
        ),
        _face(
            face_id="hub_top_face",
            face_family="hub_cap",
            role="hub_top_face",
            profile_segment_rz=profile_segments["hub_top_face"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "mounting_bore_top_bevel", "u_max": "hub_top_outer_edge"},
        ),
        _face(
            face_id="hub_bottom_face",
            face_family="hub_cap",
            role="hub_bottom_face",
            profile_segment_rz=profile_segments["hub_bottom_face"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "mounting_bore_bottom_bevel", "u_max": "hub_bottom_outer_bevel"},
        ),
        _face(
            face_id="hub_bottom_outer_bevel_surface",
            face_family="hub_bevel",
            role="hub_bottom_outer_bevel",
            profile_segment_rz=profile_segments["hub_bottom_outer_bevel_surface"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "hub_bottom_face", "u_max": "outer_hub_shell"},
            native_bevel_face=True,
        ),
        _face(
            face_id="mounting_bore_cylinder_surface",
            face_family="mounting_bore",
            role="mounting_bore_cylinder",
            profile_segment_rz=profile_segments["mounting_bore_cylinder_surface"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "mounting_bore_bottom_bevel", "u_max": "mounting_bore_top_bevel"},
        ),
        _face(
            face_id="mounting_bore_top_bevel_surface",
            face_family="hub_bevel",
            role="mounting_bore_top_bevel",
            profile_segment_rz=profile_segments["mounting_bore_top_bevel_surface"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "mounting_bore_cylinder", "u_max": "hub_top_face"},
            native_bevel_face=True,
        ),
        _face(
            face_id="mounting_bore_bottom_bevel_surface",
            face_family="hub_bevel",
            role="mounting_bore_bottom_bevel",
            profile_segment_rz=profile_segments["mounting_bore_bottom_bevel_surface"],
            theta_samples=theta_samples,
            boundary_roles={"u_min": "mounting_bore_cylinder", "u_max": "hub_bottom_face"},
            native_bevel_face=True,
        ),
    ]

    return {
        "hub_profile_status": "PASS",
        "profile_segments": profile_segments,
        "faces": faces,
    }


def _valid_domain(
    *,
    outer_radius_mm: float,
    bore_radius_mm: float,
    height_mm: float,
    bottom_bevel_mm: float,
    bore_top_bevel_mm: float,
    bore_bottom_bevel_mm: float,
    theta_samples: int,
) -> bool:
    if theta_samples < 5 or outer_radius_mm <= 0.0 or bore_radius_mm <= 0.0 or height_mm <= 0.0:
        return False
    if any(value < 0.0 for value in [bottom_bevel_mm, bore_top_bevel_mm, bore_bottom_bevel_mm]):
        return False
    radial_domain = outer_radius_mm - bore_radius_mm
    if radial_domain <= 0.0:
        return False
    if 2.0 * max(bottom_bevel_mm, bore_top_bevel_mm, bore_bottom_bevel_mm) >= radial_domain:
        return False
    if bore_top_bevel_mm + bore_bottom_bevel_mm >= height_mm:
        return False
    if bottom_bevel_mm >= outer_radius_mm:
        return False
    return True


def _face(
    *,
    face_id: str,
    face_family: str,
    role: str,
    profile_segment_rz: list[PointRZ],
    theta_samples: int,
    boundary_roles: dict[str, str],
    native_bevel_face: bool = False,
) -> dict[str, Any]:
    uv_grid = _revolve_profile_segment(profile_segment_rz, theta_samples)
    face = {
        "id": face_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "degree_u": 1,
        "degree_v": 3,
        "profile_segment_rz": profile_segment_rz,
        "boundary_roles": boundary_roles,
        "continuity_targets": ["G1_profile_tangent_target"],
    }
    if native_bevel_face:
        face["native_bevel_face"] = True
        face["display"] = {"inspection_class": "native_hub_bevel", "wire_color": "#fff200"}
    return face


def _revolve_profile_segment(profile_segment_rz: list[PointRZ], theta_samples: int) -> list[list[Point3]]:
    return [
        [_cylindrical_point(radius, theta_index, theta_samples, z_value) for theta_index in range(theta_samples)]
        for radius, z_value in profile_segment_rz
    ]


def _cylindrical_point(radius: float, theta_index: int, theta_samples: int, z_value: float) -> Point3:
    theta = 2.0 * math.pi * theta_index / (theta_samples - 1)
    return (radius * math.cos(theta), radius * math.sin(theta), z_value)


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    first_row = uv_grid[0]
    last_row = uv_grid[-1]
    return [
        [first_row[0], first_row[len(first_row) // 2], first_row[-1]],
        [last_row[0], last_row[len(last_row) // 2], last_row[-1]],
    ]
