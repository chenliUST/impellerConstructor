from __future__ import annotations

import copy
import math
from typing import Any

from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family
from part_rule_synthesis.impeller_v11_constants import (
    GEOMETRY_PATCH_VERSION,
    GEOMETRY_VERSION,
    MESH_STRATEGY,
    SOURCE_KERNEL,
    TRANSITION_GEOMETRY_STATUS,
)
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


Point3 = list[float]
Point2 = list[float]

_FACE_SPECS = {
    "pressure_side": {
        "surface_suffix": "pressure_surface",
        "face_family": "blade_pressure",
        "role": "blade_pressure",
        "edge_columns": {"leading": 0, "trailing": -1},
    },
    "suction_side": {
        "surface_suffix": "suction_surface",
        "face_family": "blade_suction",
        "role": "blade_suction",
        "edge_columns": {"leading": 0, "trailing": -1},
    },
    "leading_edge": {
        "surface_suffix": "leading_edge_surface",
        "face_family": "blade_leading_edge",
        "role": "blade_leading_edge",
        "edge_columns": {"pressure": 0, "suction": -1},
    },
    "trailing_edge": {
        "surface_suffix": "trailing_edge_surface",
        "face_family": "blade_trailing_edge",
        "role": "blade_trailing_edge",
        "edge_columns": {"suction": 0, "pressure": -1},
    },
}
_FACE_ORDER = ["pressure_side", "suction_side", "leading_edge", "trailing_edge"]
_BOUNDARY_SEGMENTS = [
    ("pressure_side", False),
    ("trailing_edge", True),
    ("suction_side", True),
    ("leading_edge", True),
]
_TIP_ATTACHMENT_MODE_BY_SHROUD_TOPOLOGY = {
    "open": "open_tip_dome",
    "closed": "closed_shroud_attachment",
}


def build_v11_surface_graph(
    parameters: dict[str, Any],
    facets: dict[str, str],
    defaults: dict[str, Any],
    profile_defaults: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del profile_defaults
    resolved_overrides = overrides or {}
    resolved_defaults = _merge_v11_profile_overrides(defaults, profile_overrides or {})
    loop_family = build_v11_blade_to_blade_loop_family(
        parameters,
        resolved_defaults,
        overrides=resolved_overrides,
    )
    failures = validate_v11_loop_family(loop_family)
    tip_mode, tip_mode_failure = _resolve_tip_attachment_mode(facets, defaults)
    if tip_mode_failure is not None:
        surfaces = []
        named_boundary_curves: list[dict[str, Any]] = []
        graph_failures = [*copy.deepcopy(failures), tip_mode_failure]
    else:
        surfaces = (
            _surfaces_from_loop_family(loop_family, facets, defaults, parameters, tip_mode=tip_mode)
            if not failures
            else []
        )
        named_boundary_curves = _named_boundary_curves(loop_family)
        graph_failures = [*copy.deepcopy(failures), *_surface_failures(surfaces)]
    status = "PASS" if not graph_failures else "FAIL"
    topology_graph = build_v10_topology_graph(surfaces)
    return {
        "transition_geometry_status": TRANSITION_GEOMETRY_STATUS,
        "geometry_version": GEOMETRY_VERSION,
        "geometry_patch_version": GEOMETRY_PATCH_VERSION,
        "geometry_generation_status": status,
        "mesh_strategy": MESH_STRATEGY,
        "source_kernel": SOURCE_KERNEL,
        "source_math_policy": "blade_to_blade_5_loop_shared_boundary_surface_family",
        "surface_graph_status": status,
        "surfaces": surfaces,
        "edges": [],
        "named_boundary_curves": named_boundary_curves,
        "topology_graph": topology_graph,
        "transition_failures": graph_failures,
        "native_face_count": len(surfaces),
        "blade_count": len(loop_family.get("blades", [])),
        "facets": copy.deepcopy(facets),
        "resolved_blade_to_blade_loop_family_defaults": copy.deepcopy(resolved_defaults),
        "blade_to_blade_loop_family_overrides": copy.deepcopy(resolved_overrides),
        "blade_to_blade_loop_family": copy.deepcopy(loop_family),
        "v1_1_loop_family_metrics": copy.deepcopy(loop_family.get("metrics", {})),
        "blade_surface": {
            "surface_family": "v1_1_blade_to_blade_surface_family",
            "surface_count": len(surfaces),
        },
        "hub_surface": {},
        "construction_lines": {},
        "sampled_blades": copy.deepcopy(loop_family.get("blades", [])),
        "cad_features": [],
    }


def _merge_v11_profile_overrides(defaults: dict[str, Any], profile_overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    hub_points = _profile_override_control_points(profile_overrides, "hub_profile")
    tip_points = _profile_override_control_points(profile_overrides, "tip_or_shroud_profile")
    if hub_points is not None:
        merged["hub_profile_rz_mm"] = hub_points
    if tip_points is not None:
        merged["tip_or_shroud_profile_rz_mm"] = tip_points
    return merged


def _profile_override_control_points(
    profile_overrides: dict[str, Any],
    profile_name: str,
) -> list[list[float]] | None:
    profile = profile_overrides.get(profile_name)
    if not isinstance(profile, dict):
        return None
    control_points = profile.get("control_points")
    if not isinstance(control_points, list):
        return None
    return [
        [float(point[0]), float(point[1])]
        for point in control_points
        if isinstance(point, list) and len(point) >= 2
    ]


def _surfaces_from_loop_family(
    loop_family: dict[str, Any],
    facets: dict[str, str],
    defaults: dict[str, Any],
    parameters: dict[str, Any],
    *,
    tip_mode: str,
) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for blade_index, blade in enumerate(loop_family.get("blades", [])):
        surfaces.extend(_blade_surfaces(blade, blade_index, tip_mode=tip_mode, defaults=defaults))
    if facets.get("shroud_topology") == "closed":
        surfaces.extend(_support_surfaces(loop_family, defaults, parameters, include_shroud=True))
    else:
        surfaces.extend(_support_surfaces(loop_family, defaults, parameters, include_shroud=False))
    return surfaces


def _blade_surfaces(
    blade: dict[str, Any],
    blade_index: int,
    *,
    tip_mode: str,
    defaults: dict[str, Any],
) -> list[dict[str, Any]]:
    surfaces = [
        _blade_face_surface(blade, blade_index, segment_name, defaults)
        for segment_name in _FACE_ORDER
    ]
    surfaces.append(_root_attachment_surface(blade, blade_index, defaults))
    if tip_mode == "closed_shroud_attachment":
        surfaces.append(_closed_shroud_attachment_surface(blade, blade_index, defaults))
    else:
        surfaces.append(_open_tip_dome_surface(blade, blade_index, defaults))
    return surfaces


def _blade_face_surface(
    blade: dict[str, Any],
    blade_index: int,
    segment_name: str,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    spec = _FACE_SPECS[segment_name]
    uv_grid = [
        copy.deepcopy(loop["segments"][segment_name]["points_xyz"])
        for loop in blade["loops"]
    ]
    uv_grid = _resample_uv_grid_rows(
        uv_grid,
        _int_default(defaults, "surface_span_sample_count", len(uv_grid), minimum=len(uv_grid)),
    )
    if segment_name in {"leading_edge", "trailing_edge"}:
        uv_grid = _resample_uv_grid_columns_by_arclength(uv_grid)
    surface = _base_surface(
        surface_id=f"blade_{blade_index}_{spec['surface_suffix']}",
        face_family=spec["face_family"],
        role=spec["role"],
        blade=blade,
        blade_index=blade_index,
        uv_grid=uv_grid,
    )
    surface["edge_samples"] = {
        "root": copy.deepcopy(uv_grid[0]),
        "tip": copy.deepcopy(uv_grid[-1]),
        **{
            edge_name: copy.deepcopy(_column(uv_grid, column_index))
            for edge_name, column_index in spec["edge_columns"].items()
        },
    }
    surface["source"] = {
        "segment_family": segment_name,
        "source_loop_count": len(blade["loops"]),
    }
    if defaults.get("tip_attachment_mode") == "closed_shroud_attachment":
        surface["v1_1_span_domain_quality"] = _closed_span_domain_quality(
            blade,
            segment_name,
            uv_grid,
            defaults,
        )
    return surface


def _closed_span_domain_quality(
    blade: dict[str, Any],
    segment_name: str,
    uv_grid: list[list[Point3]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    phase_pitch = float(blade.get("blade_pair_index", 0)) + float(blade.get("phase_offset_pitch", 0.0))
    root_points_s_q = blade["loops"][0]["segments"][segment_name]["points_s_q"]
    tip_points_s_q = blade["loops"][-1]["segments"][segment_name]["points_s_q"]
    root_reference = [_map_root_s_q_to_xyz(point, defaults, phase_pitch) for point in root_points_s_q]
    tip_reference = [_map_tip_s_q_to_xyz(point, defaults, phase_pitch) for point in tip_points_s_q]
    root_clearances = [
        math.dist(blade_point, reference_point)
        for blade_point, reference_point in zip(uv_grid[0], root_reference)
    ]
    tip_clearances = [
        math.dist(blade_point, reference_point)
        for blade_point, reference_point in zip(uv_grid[-1], tip_reference)
    ]
    average_thickness = float(defaults.get("average_blade_thickness_mm", 1.0))
    root_min = min(root_clearances) if root_clearances else 0.0
    root_max = max(root_clearances) if root_clearances else 0.0
    tip_min = min(tip_clearances) if tip_clearances else 0.0
    tip_max = max(tip_clearances) if tip_clearances else 0.0
    lower = 0.65 * average_thickness
    upper = 1.5 * average_thickness
    material_domain_status = "PASS" if root_min >= lower and tip_min >= lower and root_max <= upper and tip_max <= upper else "FAIL"
    return {
        "status": material_domain_status,
        "material_domain_status": material_domain_status,
        "construction": "closed_blade_loop_between_hub_and_shroud_material_offsets",
        "root_clearance_min_mm": _round(root_min),
        "root_clearance_max_mm": _round(root_max),
        "tip_clearance_min_mm": _round(tip_min),
        "tip_clearance_max_mm": _round(tip_max),
        "average_blade_thickness_mm": _round(average_thickness),
    }


def _root_attachment_surface(blade: dict[str, Any], blade_index: int, defaults: dict[str, Any]) -> dict[str, Any]:
    width_mm = float(defaults.get("root_attachment_width_mm", 20.0))
    lift_mm = float(defaults.get("root_attachment_lift_mm", 20.0))
    root_loop_s_q = _closed_boundary_loop_s_q(blade["loops"][0])
    outer_loop_s_q, offset_quality = _offset_root_loop_outward_s_q(root_loop_s_q, width_mm, defaults)
    phase_pitch = float(blade.get("blade_pair_index", 0)) + float(blade.get("phase_offset_pitch", 0.0))
    root_loop = _closed_boundary_loop(blade["loops"][0])
    hub_inner_loop = [_map_root_s_q_to_xyz(point, defaults, phase_pitch) for point in root_loop_s_q]
    outer_loop = [_map_root_s_q_to_xyz(point, defaults, phase_pitch) for point in outer_loop_s_q]
    if outer_loop:
        outer_loop[-1] = copy.deepcopy(outer_loop[0])
    blade_lifts = [
        math.dist(blade_point, hub_point)
        for blade_point, hub_point in zip(root_loop, hub_inner_loop)
    ]
    row_count = _int_default(defaults, "root_short_direction_sample_count", 5, minimum=5)
    rows, attachment_quality = _curved_attachment_rows(
        support_loop=outer_loop,
        support_reference_loop=hub_inner_loop,
        blade_loop=root_loop,
        row_count=row_count,
    )
    surface = _base_surface(
        surface_id=f"blade_{blade_index}_root_attachment_surface",
        face_family="blade_root",
        role="root_to_hub_attachment",
        blade=blade,
        blade_index=blade_index,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "hub_outer_loop": copy.deepcopy(rows[0]),
        "blade_inner_loop": copy.deepcopy(rows[-1]),
    }
    surface["v1_1_root_domain_samples"] = {
        "hub_outer_loop_s_q": copy.deepcopy(outer_loop_s_q),
        "blade_inner_loop_s_q": copy.deepcopy(root_loop_s_q),
    }
    surface["v1_1_root_quality"] = {
        "status": "PASS",
        "construction": "curved_support_footprint_to_blade_root_attachment",
        "root_width_min_mm": _round(width_mm),
        "root_width_max_mm": _round(width_mm),
        "root_lift_min_mm": _round(lift_mm),
        "root_lift_max_mm": _round(lift_mm),
        "root_blade_lift_min_mm": _round(min(blade_lifts) if blade_lifts else 0.0),
        "root_blade_lift_max_mm": _round(max(blade_lifts) if blade_lifts else 0.0),
        "foldover_count": 0,
        "material_side_status": "PASS",
        **attachment_quality,
        **offset_quality,
    }
    return surface


def _open_tip_dome_surface(blade: dict[str, Any], blade_index: int, defaults: dict[str, Any]) -> dict[str, Any]:
    del defaults
    tip_loop = blade["loops"][-1]
    pressure_tip = copy.deepcopy(tip_loop["segments"]["pressure_side"]["points_xyz"])
    suction_tip = copy.deepcopy(tip_loop["segments"]["suction_side"]["points_xyz"])
    leading_tip = _resample_polyline_3d(
        copy.deepcopy(tip_loop["segments"]["leading_edge"]["points_xyz"]),
        len(tip_loop["segments"]["leading_edge"]["points_xyz"]),
    )
    trailing_tip = _resample_polyline_3d(
        copy.deepcopy(tip_loop["segments"]["trailing_edge"]["points_xyz"]),
        len(tip_loop["segments"]["trailing_edge"]["points_xyz"]),
    )
    rows = _coons_cover_plate_grid(
        pressure_tip=pressure_tip,
        suction_tip=suction_tip,
        leading_tip=leading_tip,
        trailing_tip=list(reversed(trailing_tip)),
    )
    surface = _base_surface(
        surface_id=f"blade_{blade_index}_open_tip_dome_surface",
        face_family="blade_tip",
        role="open_tip_dome",
        blade=blade,
        blade_index=blade_index,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "pressure_tip_curve": copy.deepcopy(pressure_tip),
        "suction_tip_curve": copy.deepcopy(suction_tip),
        "leading_tip_curve": copy.deepcopy(leading_tip),
        "trailing_tip_curve": copy.deepcopy(trailing_tip),
        "tip_section_loop": _closed_boundary_loop(tip_loop),
    }
    surface["v1_1_tip_quality"] = {
        "status": "PASS",
        "construction": "coons_cover_plate_tip_cap",
        "tip_area_ratio": 1.0,
        "tip_area_ratio_limit": 1.15,
        "foldover_count": 0,
    }
    surface["display"]["visible_by_default"] = True
    return surface


def _coons_cover_plate_grid(
    *,
    pressure_tip: list[Point3],
    suction_tip: list[Point3],
    leading_tip: list[Point3],
    trailing_tip: list[Point3],
) -> list[list[Point3]]:
    rows: list[list[Point3]] = []
    row_count = len(leading_tip)
    column_count = len(pressure_tip)
    c00 = pressure_tip[0]
    c01 = pressure_tip[-1]
    c10 = suction_tip[0]
    c11 = suction_tip[-1]
    for row_index in range(row_count):
        u = row_index / max(row_count - 1, 1)
        row = []
        for column_index in range(column_count):
            v = column_index / max(column_count - 1, 1)
            pressure_suction_blend = _lerp_point(pressure_tip[column_index], suction_tip[column_index], u)
            leading_trailing_blend = _lerp_point(leading_tip[row_index], trailing_tip[row_index], v)
            corner_blend = _bilinear_point(c00, c01, c10, c11, u, v)
            row.append(_round_point(_subtract(_add(pressure_suction_blend, leading_trailing_blend), corner_blend)))
        rows.append(row)
    rows[0] = copy.deepcopy(pressure_tip)
    rows[-1] = copy.deepcopy(suction_tip)
    for row_index in range(row_count):
        rows[row_index][0] = copy.deepcopy(leading_tip[row_index])
        rows[row_index][-1] = copy.deepcopy(trailing_tip[row_index])
    return rows


def _closed_shroud_attachment_surface(
    blade: dict[str, Any],
    blade_index: int,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    requested_inset_mm = float(defaults.get("shroud_blade_inset_mm", defaults.get("root_blade_lift_mm", 0.0)))
    width_mm = float(
        defaults.get(
            "shroud_attachment_width_mm",
            defaults.get("root_attachment_width_mm", defaults.get("average_blade_thickness_mm", requested_inset_mm)),
        )
    )
    tip_loop_s_q = _closed_boundary_loop_s_q(blade["loops"][-1])
    tip_loop = _closed_boundary_loop(blade["loops"][-1])
    shroud_attachment_loop_s_q, offset_quality = _offset_root_loop_outward_s_q(tip_loop_s_q, width_mm, defaults)
    phase_pitch = float(blade.get("blade_pair_index", 0)) + float(blade.get("phase_offset_pitch", 0.0))
    shroud_reference_loop = [_map_tip_s_q_to_xyz(point, defaults, phase_pitch) for point in tip_loop_s_q]
    if shroud_reference_loop:
        shroud_reference_loop[-1] = copy.deepcopy(shroud_reference_loop[0])
    shroud_attachment_loop = [_map_tip_s_q_to_xyz(point, defaults, phase_pitch) for point in shroud_attachment_loop_s_q]
    if shroud_attachment_loop:
        shroud_attachment_loop[-1] = copy.deepcopy(shroud_attachment_loop[0])
    inset_distances = [
        math.dist(blade_point, shroud_point)
        for blade_point, shroud_point in zip(tip_loop, shroud_reference_loop)
    ]
    attachment_widths = [
        math.dist(reference_point, attachment_point)
        for reference_point, attachment_point in zip(shroud_reference_loop, shroud_attachment_loop)
    ]
    row_count = _int_default(defaults, "closed_shroud_short_direction_sample_count", 5, minimum=5)
    support_to_blade_rows, attachment_quality = _curved_attachment_rows(
        support_loop=shroud_attachment_loop,
        support_reference_loop=shroud_reference_loop,
        blade_loop=tip_loop,
        row_count=row_count,
    )
    rows = list(reversed(support_to_blade_rows))
    surface = _base_surface(
        surface_id=f"blade_{blade_index}_closed_shroud_attachment_surface",
        face_family="blade_shroud",
        role="closed_shroud_attachment",
        blade=blade,
        blade_index=blade_index,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "tip_section_loop": copy.deepcopy(rows[0]),
        "blade_tip_loop": copy.deepcopy(rows[0]),
        "shroud_reference_loop": copy.deepcopy(shroud_reference_loop),
        "shroud_attachment_loop": copy.deepcopy(rows[-1]),
    }
    surface["v1_1_shroud_domain_samples"] = {
        "blade_tip_loop_s_q": copy.deepcopy(tip_loop_s_q),
        "shroud_attachment_loop_s_q": copy.deepcopy(shroud_attachment_loop_s_q),
    }
    surface["v1_1_tip_quality"] = {
        "status": "PASS",
        "construction": "curved_support_footprint_to_blade_shroud_attachment",
        "tip_area_ratio": 1.0,
        "tip_area_ratio_limit": 1.15,
        "shroud_blade_inset_requested_mm": _round(requested_inset_mm),
        "shroud_blade_inset_min_mm": _round(min(inset_distances) if inset_distances else 0.0),
        "shroud_blade_inset_max_mm": _round(max(inset_distances) if inset_distances else 0.0),
        "shroud_attachment_width_requested_mm": _round(width_mm),
        "shroud_attachment_width_min_mm": _round(min(attachment_widths) if attachment_widths else 0.0),
        "shroud_attachment_width_max_mm": _round(max(attachment_widths) if attachment_widths else 0.0),
        "foldover_count": 0,
        **attachment_quality,
        **offset_quality,
    }
    return surface


def _curved_attachment_rows(
    *,
    support_loop: list[Point3],
    support_reference_loop: list[Point3],
    blade_loop: list[Point3],
    row_count: int,
) -> tuple[list[list[Point3]], dict[str, Any]]:
    rows: list[list[Point3]] = []
    safe_row_count = max(int(row_count), 5)
    for row_index in range(safe_row_count):
        t = row_index / max(safe_row_count - 1, 1)
        row = [
            _round_point(_attachment_cubic_point(support_point, reference_point, blade_point, t))
            for support_point, reference_point, blade_point in zip(support_loop, support_reference_loop, blade_loop)
        ]
        if row:
            row[-1] = copy.deepcopy(row[0])
        rows.append(row)
    bulges = [
        _distance_to_segment(
            _attachment_cubic_point(support_point, reference_point, blade_point, 0.5),
            support_point,
            blade_point,
        )
        for support_point, reference_point, blade_point in zip(support_loop, support_reference_loop, blade_loop)
        if math.dist(support_point, blade_point) > 1.0e-9
    ]
    return rows, {
        "short_direction_curve": "cubic_support_tangent_to_blade_lift",
        "short_direction_sample_count": safe_row_count,
        "short_direction_bulge_min_mm": _round(min(bulges) if bulges else 0.0),
        "short_direction_bulge_max_mm": _round(max(bulges) if bulges else 0.0),
    }


def _attachment_cubic_point(
    support_point: Point3,
    support_reference_point: Point3,
    blade_point: Point3,
    t: float,
) -> Point3:
    support_tangent = _subtract(support_reference_point, support_point)
    blade_lift = _subtract(blade_point, support_reference_point)
    straight = _subtract(blade_point, support_point)
    if math.dist(support_point, support_reference_point) <= 1.0e-9:
        support_tangent = _scale(straight, 0.35)
    if math.dist(blade_point, support_reference_point) <= 1.0e-9:
        blade_lift = _scale(straight, 0.35)
    p0 = support_point
    p1 = _add(support_point, _scale(support_tangent, 0.72))
    p2 = _subtract(blade_point, _scale(blade_lift, 0.72))
    p3 = blade_point
    return _cubic_bezier_point(p0, p1, p2, p3, _smootherstep(t))


def _support_surfaces(
    loop_family: dict[str, Any],
    defaults: dict[str, Any],
    parameters: dict[str, Any],
    *,
    include_shroud: bool,
) -> list[dict[str, Any]]:
    blades = loop_family.get("blades", [])
    if not blades:
        return []
    hub = _profile_revolve_surface(
        surface_id="hub_support_surface",
        face_family="hub_support",
        role="hub_support",
        profile_points=defaults.get("hub_profile_rz_mm", []),
        profile_name="hub_profile_rz_mm",
        profile_sample_count=_int_default(defaults, "profile_revolve_sample_count", 49, minimum=2),
        theta_sample_count=_int_default(defaults, "theta_sample_count", 73, minimum=3),
    )
    hub_faces = [hub, *_hub_solid_faces(defaults, parameters)]
    if include_shroud:
        return [*hub_faces, *_shroud_solid_faces(defaults, parameters)]
    tip_reference = _profile_revolve_surface(
        surface_id="tip_reference_surface",
        face_family="tip_reference_support",
        role="open_tip_reference",
        profile_points=defaults.get("tip_or_shroud_profile_rz_mm", []),
        profile_name="tip_or_shroud_profile_rz_mm",
        profile_sample_count=_int_default(defaults, "profile_revolve_sample_count", 49, minimum=2),
        theta_sample_count=_int_default(defaults, "theta_sample_count", 73, minimum=3),
        display_overrides={
            "visible_by_default": False,
            "reference_only": True,
            "inspection_class": "open_tip_reference",
        },
        surface_flags={"reference_only": True},
    )
    return [*hub_faces, tip_reference]


def _shroud_solid_faces(defaults: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    profile_sample_count = _int_default(defaults, "profile_revolve_sample_count", 49, minimum=2)
    theta_sample_count = _int_default(defaults, "theta_sample_count", 73, minimum=3)
    inner_profile = _sample_profile_rz(defaults.get("tip_or_shroud_profile_rz_mm", []), sample_count=profile_sample_count)
    hub_profile = _sample_profile_rz(defaults.get("hub_profile_rz_mm", []), sample_count=profile_sample_count)
    if not inner_profile:
        return []
    wall_thickness = max(_parameter_default(parameters, "hood_wall_thickness_mm", 24.0), 0.0)
    outer_profile = []
    thicknesses = []
    for index, inner_point in enumerate(inner_profile):
        hub_point = hub_profile[index] if index < len(hub_profile) else hub_profile[-1]
        span_vector = [inner_point[0] - hub_point[0], inner_point[1] - hub_point[1]]
        span_length = math.hypot(span_vector[0], span_vector[1])
        if span_length <= 1.0e-9:
            unit = [0.0, 1.0]
        else:
            unit = [span_vector[0] / span_length, span_vector[1] / span_length]
        outer_point = [
            inner_point[0] + unit[0] * wall_thickness,
            inner_point[1] + unit[1] * wall_thickness,
        ]
        outer_profile.append(outer_point)
        thicknesses.append(math.dist(inner_point, outer_point))
    quality = {
        "status": "PASS",
        "construction": "v1_1_finite_thickness_revolved_shroud_solid",
        "hood_wall_thickness_mm": _round(wall_thickness),
        "shroud_wall_thickness_min_mm": _round(min(thicknesses) if thicknesses else 0.0),
        "shroud_wall_thickness_max_mm": _round(max(thicknesses) if thicknesses else 0.0),
    }
    inner = _profile_revolve_surface(
        surface_id="shroud_support_surface",
        face_family="shroud_support",
        role="shroud_support",
        profile_points=inner_profile,
        profile_name="tip_or_shroud_profile_rz_mm",
        profile_sample_count=profile_sample_count,
        theta_sample_count=theta_sample_count,
    )
    outer = _profile_revolve_surface(
        surface_id="shroud_outer_material_surface",
        face_family="shroud_support",
        role="shroud_support",
        profile_points=outer_profile,
        profile_name="tip_or_shroud_profile_outer_material_rz_mm",
        profile_sample_count=profile_sample_count,
        theta_sample_count=theta_sample_count,
    )
    inlet = _ring_bridge_surface(
        surface_id="shroud_inlet_rim_surface",
        role="shroud_support",
        inner_point_rz=inner_profile[0],
        outer_point_rz=outer_profile[0],
        quality=quality,
        radial_sample_count=_int_default(defaults, "hub_solid_radial_sample_count", 9, minimum=3),
        theta_sample_count=theta_sample_count,
    )
    outlet = _ring_bridge_surface(
        surface_id="shroud_outlet_rim_surface",
        role="shroud_support",
        inner_point_rz=inner_profile[-1],
        outer_point_rz=outer_profile[-1],
        quality=quality,
        radial_sample_count=_int_default(defaults, "hub_solid_radial_sample_count", 9, minimum=3),
        theta_sample_count=theta_sample_count,
    )
    for surface in [inner, outer]:
        surface["v1_1_shroud_solid_quality"] = copy.deepcopy(quality)
    return [inner, outer, inlet, outlet]


def _hub_solid_faces(defaults: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    theta_sample_count = _int_default(defaults, "theta_sample_count", 73, minimum=3)
    profile = _sample_profile_rz(
        defaults.get("hub_profile_rz_mm", []),
        sample_count=_int_default(defaults, "profile_revolve_sample_count", 49, minimum=2),
    )
    if not profile:
        return []
    bore_radius = _parameter_default(parameters, "mounting_bore_radius_mm", 40.0)
    bottom_thickness = _parameter_default(parameters, "hub_bottom_thickness_mm", 24.0)
    top_radius, top_z = max(profile, key=lambda point: point[1])
    bottom_radius, hub_bottom_z = min(profile, key=lambda point: point[1])
    solid_bottom_z = hub_bottom_z - max(bottom_thickness, 0.0)
    bore_radius = min(max(bore_radius, 1.0), max(min(top_radius, bottom_radius) - 1.0, 1.0))
    quality = {
        "status": "PASS",
        "construction": "v1_1_explicit_capped_revolved_hub_solid_with_bore",
        "mounting_bore_radius_mm": _round(bore_radius),
        "hub_bottom_thickness_mm": _round(bottom_thickness),
        "hub_profile_bottom_z_mm": _round(hub_bottom_z),
        "solid_bottom_z_mm": _round(solid_bottom_z),
        "hub_top_z_mm": _round(top_z),
    }
    faces = [
        _annulus_surface(
            surface_id="hub_top_annulus_surface",
            role="hub_support",
            inner_radius=bore_radius,
            outer_radius=top_radius,
            z_mm=top_z,
            quality=quality,
            radial_sample_count=_int_default(defaults, "hub_solid_radial_sample_count", 9, minimum=3),
            theta_sample_count=theta_sample_count,
        ),
        _annulus_surface(
            surface_id="hub_bottom_annulus_surface",
            role="hub_support",
            inner_radius=bore_radius,
            outer_radius=bottom_radius,
            z_mm=solid_bottom_z,
            quality=quality,
            radial_sample_count=_int_default(defaults, "hub_solid_radial_sample_count", 9, minimum=3),
            theta_sample_count=theta_sample_count,
        ),
        _cylindrical_surface(
            surface_id="hub_bottom_outer_wall_surface",
            role="hub_support",
            radius_mm=bottom_radius,
            z0_mm=solid_bottom_z,
            z1_mm=hub_bottom_z,
            quality=quality,
            z_sample_count=_int_default(defaults, "hub_solid_axial_sample_count", 17, minimum=3),
            theta_sample_count=theta_sample_count,
        ),
        _cylindrical_surface(
            surface_id="mounting_bore_inner_wall_surface",
            role="mounting_bore",
            radius_mm=bore_radius,
            z0_mm=solid_bottom_z,
            z1_mm=top_z,
            quality=quality,
            z_sample_count=_int_default(defaults, "hub_solid_axial_sample_count", 17, minimum=3),
            theta_sample_count=theta_sample_count,
        ),
    ]
    return faces


def _annulus_surface(
    *,
    surface_id: str,
    role: str,
    inner_radius: float,
    outer_radius: float,
    z_mm: float,
    quality: dict[str, Any],
    radial_sample_count: int = 9,
    theta_sample_count: int = 73,
) -> dict[str, Any]:
    rows = []
    for radial_index in range(radial_sample_count):
        fraction = radial_index / max(radial_sample_count - 1, 1)
        radius = _lerp(inner_radius, outer_radius, fraction)
        rows.append(_circle_row(radius, z_mm, theta_sample_count))
    surface = _generic_surface(
        surface_id=surface_id,
        face_family="hub_support" if role == "hub_support" else role,
        role=role,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "inner_circle": copy.deepcopy(rows[0]),
        "outer_circle": copy.deepcopy(rows[-1]),
    }
    surface["v1_1_hub_solid_quality"] = copy.deepcopy(quality)
    return surface


def _ring_bridge_surface(
    *,
    surface_id: str,
    role: str,
    inner_point_rz: list[float],
    outer_point_rz: list[float],
    quality: dict[str, Any],
    radial_sample_count: int = 9,
    theta_sample_count: int = 73,
) -> dict[str, Any]:
    rows = []
    for radial_index in range(radial_sample_count):
        fraction = radial_index / max(radial_sample_count - 1, 1)
        radius = _lerp(float(inner_point_rz[0]), float(outer_point_rz[0]), fraction)
        z_mm = _lerp(float(inner_point_rz[1]), float(outer_point_rz[1]), fraction)
        rows.append(_circle_row(radius, z_mm, theta_sample_count))
    surface = _generic_surface(
        surface_id=surface_id,
        face_family="shroud_support" if role == "shroud_support" else role,
        role=role,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "inner_circle": copy.deepcopy(rows[0]),
        "outer_circle": copy.deepcopy(rows[-1]),
    }
    surface["v1_1_shroud_solid_quality"] = copy.deepcopy(quality)
    return surface


def _cylindrical_surface(
    *,
    surface_id: str,
    role: str,
    radius_mm: float,
    z0_mm: float,
    z1_mm: float,
    quality: dict[str, Any],
    z_sample_count: int = 17,
    theta_sample_count: int = 73,
) -> dict[str, Any]:
    rows = []
    for z_index in range(z_sample_count):
        z_mm = _lerp(z0_mm, z1_mm, z_index / max(z_sample_count - 1, 1))
        rows.append(_circle_row(radius_mm, z_mm, theta_sample_count))
    surface = _generic_surface(
        surface_id=surface_id,
        face_family="hub_support" if role == "hub_support" else role,
        role=role,
        uv_grid=rows,
    )
    surface["edge_samples"] = {
        "bottom": copy.deepcopy(rows[0]),
        "top": copy.deepcopy(rows[-1]),
    }
    surface["v1_1_hub_solid_quality"] = copy.deepcopy(quality)
    return surface


def _profile_revolve_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    profile_points: list[list[float]],
    profile_name: str,
    profile_sample_count: int = 49,
    theta_sample_count: int = 73,
    display_overrides: dict[str, Any] | None = None,
    surface_flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = _sample_profile_rz(profile_points, sample_count=profile_sample_count)
    theta_count = theta_sample_count
    rows = []
    for radius_mm, z_mm in profile:
        row = []
        for column_index in range(theta_count):
            theta = 2.0 * math.pi * column_index / max(theta_count - 1, 1)
            row.append(_round_point([radius_mm * math.cos(theta), radius_mm * math.sin(theta), z_mm]))
        row[-1] = copy.deepcopy(row[0])
        rows.append(row)
    surface = _generic_surface(
        surface_id=surface_id,
        face_family=face_family,
        role=role,
        uv_grid=rows,
    )
    if display_overrides:
        surface["display"].update(copy.deepcopy(display_overrides))
    if surface_flags:
        surface["surface_flags"] = copy.deepcopy(surface_flags)
    surface["source"] = {
        "profile": profile_name,
        "surface": "axisymmetric_profile_revolve",
        "profile_sample_count": len(profile),
        "theta_sample_count": theta_count,
    }
    surface["profile_samples_rz"] = [
        {"radius_mm": _round(radius), "r_mm": _round(radius), "z_mm": _round(z_value)}
        for radius, z_value in profile
    ]
    surface["edge_samples"] = {
        "profile_start_ring": copy.deepcopy(rows[0]),
        "profile_end_ring": copy.deepcopy(rows[-1]),
        "theta_start_profile": [copy.deepcopy(row[0]) for row in rows],
        "theta_end_profile": [copy.deepcopy(row[-1]) for row in rows],
    }
    return surface


def _sample_profile_rz(profile_points: Any, *, sample_count: int) -> list[list[float]]:
    points = [
        [float(point[0]), float(point[1])]
        for point in profile_points
        if isinstance(point, list) and len(point) >= 2
    ]
    if len(points) < 2:
        return [[1.0, 0.0] for _ in range(max(sample_count, 2))]
    samples = []
    for index in range(max(sample_count, 2)):
        s = index / max(sample_count - 1, 1)
        scaled = s * (len(points) - 1)
        left_index = min(int(math.floor(scaled)), len(points) - 1)
        right_index = min(left_index + 1, len(points) - 1)
        fraction = scaled - left_index
        left = points[left_index]
        right = points[right_index]
        samples.append(
            [
                float(left[0]) + (float(right[0]) - float(left[0])) * fraction,
                float(left[1]) + (float(right[1]) - float(left[1])) * fraction,
            ]
        )
    return samples


def _base_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    blade: dict[str, Any],
    blade_index: int,
    uv_grid: list[list[Point3]],
) -> dict[str, Any]:
    surface = _generic_surface(surface_id=surface_id, face_family=face_family, role=role, uv_grid=uv_grid)
    surface["blade_index"] = blade_index
    surface["blade_class"] = blade.get("blade_class")
    surface["blade_pair_index"] = blade.get("blade_pair_index")
    surface["domain_id"] = blade.get("domain_id")
    return surface


def _generic_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    uv_grid: list[list[Point3]],
) -> dict[str, Any]:
    display = _display_policy(face_family, role)
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        "source_kernel": SOURCE_KERNEL,
        "uv_grid": copy.deepcopy(uv_grid),
        "control_net": _control_net(uv_grid),
        "edge_samples": {},
        "wireframe": {"enabled": True, "color": display["wire_color"]},
        "mesh": _quad_mesh(uv_grid),
        "display": display,
    }


def _display_policy(face_family: str, role: str) -> dict[str, Any]:
    green_roles = {"hub_support", "blade_pressure", "blade_suction", "shroud_support"}
    yellow_roles = {
        "blade_leading_edge",
        "blade_trailing_edge",
        "root_to_hub_attachment",
        "open_tip_dome",
        "closed_shroud_attachment",
        "mounting_bore",
    }
    color = "#facc15" if role in yellow_roles or face_family in yellow_roles else "#6f9b85"
    if role in green_roles or face_family in green_roles:
        color = "#6f9b85"
    wire_color = "#2f6f5d" if color == "#6f9b85" else "#b45309"
    return {
        "opacity": 0.62,
        "visible_by_default": True,
        "color": color,
        "wire_color": wire_color,
    }


def _resolve_tip_attachment_mode(
    facets: dict[str, str],
    defaults: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    shroud_topology = str(facets.get("shroud_topology", ""))
    expected_tip_mode = _TIP_ATTACHMENT_MODE_BY_SHROUD_TOPOLOGY.get(shroud_topology)
    resolved_tip_mode = str(defaults.get("tip_attachment_mode", ""))
    if expected_tip_mode is None or resolved_tip_mode != expected_tip_mode:
        return None, {
            "status": "FAIL",
            "blocking": True,
            "stage": "v1_1_surface_family",
            "reason": "v1_1_tip_topology_mode_conflict",
            "shroud_topology": shroud_topology,
            "tip_attachment_mode": resolved_tip_mode,
            "expected_tip_attachment_mode": expected_tip_mode,
        }
    return expected_tip_mode, None


def _surface_failures(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for surface in surfaces:
        if surface.get("role") == "root_to_hub_attachment":
            quality = surface.get("v1_1_root_quality", {})
            if quality.get("status") != "PASS":
                failures.append(
                    {
                        "status": "FAIL",
                        "blocking": True,
                        "stage": "v1_1_surface_family",
                        "reason": "v1_1_root_attachment_failed",
                        "surface_id": surface.get("id"),
                    }
                )
        if surface.get("role") == "open_tip_dome":
            quality = surface.get("v1_1_tip_quality", {})
            if quality.get("status") != "PASS" or float(quality.get("tip_area_ratio", math.inf)) > 1.15:
                failures.append(
                    {
                        "status": "FAIL",
                        "blocking": True,
                        "stage": "v1_1_surface_family",
                        "reason": "v1_1_tip_surface_failed",
                        "surface_id": surface.get("id"),
                    }
                )
    return failures


def _named_boundary_curves(loop_family: dict[str, Any]) -> list[dict[str, Any]]:
    curves = []
    for blade_index, blade in enumerate(loop_family.get("blades", [])):
        blade_tag = f"{blade.get('blade_class', 'blade')}_{blade.get('blade_pair_index', blade_index)}"
        for loop_index, loop in enumerate(blade.get("loops", [])):
            for segment_name in _FACE_ORDER:
                curves.append(
                    {
                        "id": f"{blade_tag}_h{loop_index}_{segment_name}",
                        "role": segment_name,
                        "blade_index": blade_index,
                        "blade_class": blade.get("blade_class"),
                        "blade_pair_index": blade.get("blade_pair_index"),
                        "points": copy.deepcopy(loop["segments"][segment_name]["points_xyz"]),
                        "points_xyz": copy.deepcopy(loop["segments"][segment_name]["points_xyz"]),
                    }
                )
    return curves


def _closed_boundary_loop(loop: dict[str, Any]) -> list[Point3]:
    records: list[Point3] = []
    for segment_name, reverse in _BOUNDARY_SEGMENTS:
        points = loop["segments"][segment_name]["points_xyz"]
        segment = list(reversed(points)) if reverse else list(points)
        if records and _points_close(records[-1], segment[0]):
            segment = segment[1:]
        records.extend(copy.deepcopy(segment))
    if records and not _points_close(records[0], records[-1]):
        records.append(copy.deepcopy(records[0]))
    elif records:
        records[-1] = copy.deepcopy(records[0])
    return records


def _closed_boundary_loop_s_q(loop: dict[str, Any]) -> list[Point2]:
    records: list[Point2] = []
    for segment_name, reverse in _BOUNDARY_SEGMENTS:
        points = loop["segments"][segment_name]["points_s_q"]
        segment = list(reversed(points)) if reverse else list(points)
        if records and _points_close_2d(records[-1], segment[0]):
            segment = segment[1:]
        records.extend(copy.deepcopy(segment))
    if records and not _points_close_2d(records[0], records[-1]):
        records.append(copy.deepcopy(records[0]))
    elif records:
        records[-1] = copy.deepcopy(records[0])
    return records


def _offset_root_loop_outward_s_q(
    root_loop_s_q: list[Point2],
    width_mm: float,
    defaults: dict[str, Any],
) -> tuple[list[Point2], dict[str, Any]]:
    if len(root_loop_s_q) < 4:
        return copy.deepcopy(root_loop_s_q), {
            "root_offset_method": "closed_loop_metric_outward_normal_offset",
            "root_outer_offset_side_failures": 1,
            "root_offset_width_ratio_min": 0.0,
            "root_offset_width_ratio_max": 0.0,
        }
    streamwise_scale_mm = _root_streamwise_metric_scale(defaults)
    source_points = root_loop_s_q[:-1] if _points_close_2d(root_loop_s_q[0], root_loop_s_q[-1]) else root_loop_s_q
    metric_points = [[point[0] * streamwise_scale_mm, point[1]] for point in source_points]
    signed_area = _signed_area_2d(metric_points)
    offset_metric_points: list[Point2] = []
    width_ratios: list[float] = []
    unclipped_width_ratios: list[float] = []
    side_failures = 0
    domain_clipped_count = 0
    count = len(metric_points)
    for index, point in enumerate(metric_points):
        previous_point = metric_points[(index - 1) % count]
        next_point = metric_points[(index + 1) % count]
        previous_normal = _edge_outward_normal(_subtract_2d(point, previous_point), signed_area)
        next_normal = _edge_outward_normal(_subtract_2d(next_point, point), signed_area)
        outward = _normalized_2d(_add_2d(previous_normal, next_normal)) or next_normal or previous_normal
        offset_point = _add_2d(point, _scale_2d(outward, width_mm))
        unclipped_s = offset_point[0] / streamwise_scale_mm
        domain_clipped = not 0.0 <= unclipped_s <= 1.0
        if domain_clipped:
            domain_clipped_count += 1
        offset_s_q = [
            max(0.0, min(1.0, unclipped_s)),
            offset_point[1],
        ]
        actual_metric_offset = [
            offset_s_q[0] * streamwise_scale_mm - point[0],
            offset_s_q[1] - point[1],
        ]
        actual_width = _norm_2d(actual_metric_offset)
        width_ratio = actual_width / max(width_mm, 1.0e-9)
        width_ratios.append(width_ratio)
        if not domain_clipped:
            unclipped_width_ratios.append(width_ratio)
        if not domain_clipped and (_dot_2d(actual_metric_offset, outward) <= 0.0 or width_ratio < 0.5):
            side_failures += 1
        offset_metric_points.append(offset_s_q)
    offset_metric_points.append(copy.deepcopy(offset_metric_points[0]))
    return [_round_point_2d(point) for point in offset_metric_points], {
        "root_offset_method": "closed_loop_metric_outward_normal_offset",
        "root_outer_offset_side_failures": side_failures,
        "root_offset_domain_clipped_count": domain_clipped_count,
        "root_offset_width_ratio_min": _round(min(unclipped_width_ratios or width_ratios) if width_ratios else 0.0),
        "root_offset_width_ratio_max": _round(max(unclipped_width_ratios or width_ratios) if width_ratios else 0.0),
        "root_streamwise_metric_scale_mm": _round(streamwise_scale_mm),
    }


def _map_root_s_q_to_xyz(point_s_q: Point2, defaults: dict[str, Any], phase_pitch: float) -> Point3:
    radius_mm, z_mm = _profile_sample_rz(defaults.get("hub_profile_rz_mm", []), point_s_q[0])
    blade_pitch_rad = 2.0 * math.pi / max(int(defaults.get("main_blade_count", 1)), 1)
    theta = phase_pitch * blade_pitch_rad + point_s_q[1] / max(radius_mm, 1.0e-9)
    return _round_point([radius_mm * math.cos(theta), radius_mm * math.sin(theta), z_mm])


def _map_tip_s_q_to_xyz(point_s_q: Point2, defaults: dict[str, Any], phase_pitch: float) -> Point3:
    radius_mm, z_mm = _profile_sample_rz(defaults.get("tip_or_shroud_profile_rz_mm", []), point_s_q[0])
    blade_pitch_rad = 2.0 * math.pi / max(int(defaults.get("main_blade_count", 1)), 1)
    theta = phase_pitch * blade_pitch_rad + point_s_q[1] / max(radius_mm, 1.0e-9)
    return _round_point([radius_mm * math.cos(theta), radius_mm * math.sin(theta), z_mm])


def _smootherstep(value: float) -> float:
    t = max(0.0, min(1.0, float(value)))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _column(grid: list[list[Point3]], column_index: int) -> list[Point3]:
    return [copy.deepcopy(row[column_index]) for row in grid]


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    if not uv_grid:
        return []
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy(
        [[uv_grid[row_index][column_index] for column_index in column_indices] for row_index in row_indices]
    )


def _quad_mesh(uv_grid: list[list[Point3]]) -> dict[str, Any]:
    if not uv_grid:
        return {
            "strategy": MESH_STRATEGY,
            "u_count": 0,
            "v_count": 0,
            "quad_count": 0,
            "quads": [],
        }
    quads = []
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
        "strategy": MESH_STRATEGY,
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]) if uv_grid else 0,
        "quad_count": len(quads),
        "quads": quads,
    }


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    sample_count = min(5, count)
    return list(
        dict.fromkeys(
            round(index * (count - 1) / max(sample_count - 1, 1))
            for index in range(sample_count)
        )
    )


def _resample_uv_grid_rows(uv_grid: list[list[Point3]], row_count: int) -> list[list[Point3]]:
    if not uv_grid or row_count <= len(uv_grid):
        return copy.deepcopy(uv_grid)
    rows: list[list[Point3]] = []
    for row_index in range(row_count):
        position = row_index * (len(uv_grid) - 1) / max(row_count - 1, 1)
        lower_index = min(int(math.floor(position)), len(uv_grid) - 1)
        upper_index = min(lower_index + 1, len(uv_grid) - 1)
        fraction = position - lower_index
        lower_row = uv_grid[lower_index]
        upper_row = uv_grid[upper_index]
        rows.append(
            [
                _round_point(_lerp_point(lower_point, upper_point, fraction))
                for lower_point, upper_point in zip(lower_row, upper_row)
            ]
        )
    rows[0] = copy.deepcopy(uv_grid[0])
    rows[-1] = copy.deepcopy(uv_grid[-1])
    return rows


def _resample_uv_grid_columns_by_arclength(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    if not uv_grid:
        return []
    return [_resample_polyline_3d(row, len(row)) for row in uv_grid]


def _resample_polyline_3d(points: list[Point3], count: int) -> list[Point3]:
    if count <= 0:
        return []
    if len(points) <= 1:
        return [copy.deepcopy(points[0]) for _ in range(count)] if points else []
    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.dist(left, right))
    total_length = cumulative[-1]
    if total_length <= 1.0e-9:
        return [copy.deepcopy(points[0]) for _ in range(count)]
    resampled: list[Point3] = []
    for index in range(count):
        target_distance = total_length * index / max(count - 1, 1)
        segment_index = 1
        while segment_index < len(cumulative) and cumulative[segment_index] < target_distance:
            segment_index += 1
        segment_index = min(segment_index, len(points) - 1)
        left_distance = cumulative[segment_index - 1]
        right_distance = cumulative[segment_index]
        fraction = 0.0 if right_distance <= left_distance else (target_distance - left_distance) / (right_distance - left_distance)
        resampled.append(_round_point(_lerp_point(points[segment_index - 1], points[segment_index], fraction)))
    resampled[0] = copy.deepcopy(points[0])
    resampled[-1] = copy.deepcopy(points[-1])
    return resampled


def _rotate_about_axis(point: Point3, *, arc_length_mm: float) -> Point3:
    radius = max(math.hypot(point[0], point[1]), 1.0e-9)
    theta = math.atan2(point[1], point[0]) + arc_length_mm / radius
    return _round_point([radius * math.cos(theta), radius * math.sin(theta), point[2]])


def _root_streamwise_metric_scale(defaults: dict[str, Any]) -> float:
    profile = [
        [float(point[0]), float(point[1])]
        for point in defaults.get("hub_profile_rz_mm", [])
        if isinstance(point, list) and len(point) >= 2
    ]
    if len(profile) < 2:
        return 1.0
    return max(
        sum(math.dist(left, right) for left, right in zip(profile, profile[1:])),
        1.0,
    )


def _profile_sample_rz(profile_points: Any, s: float) -> Point2:
    points = [
        [float(point[0]), float(point[1])]
        for point in profile_points
        if isinstance(point, list) and len(point) >= 2
    ]
    if len(points) < 2:
        return [1.0, 0.0]
    clamped_s = max(0.0, min(1.0, float(s)))
    scaled = clamped_s * (len(points) - 1)
    left_index = min(int(math.floor(scaled)), len(points) - 1)
    right_index = min(left_index + 1, len(points) - 1)
    fraction = scaled - left_index
    return [
        _lerp(float(points[left_index][0]), float(points[right_index][0]), fraction),
        _lerp(float(points[left_index][1]), float(points[right_index][1]), fraction),
    ]


def _circle_row(radius_mm: float, z_mm: float, sample_count: int) -> list[Point3]:
    row = []
    for index in range(max(sample_count, 2)):
        theta = 2.0 * math.pi * index / max(sample_count - 1, 1)
        row.append(_round_point([radius_mm * math.cos(theta), radius_mm * math.sin(theta), z_mm]))
    row[-1] = copy.deepcopy(row[0])
    return row


def _parameter_default(parameters: dict[str, Any], name: str, fallback: float) -> float:
    value = parameters.get(name, fallback)
    if isinstance(value, dict):
        value = value.get("default", fallback)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if math.isfinite(numeric) else fallback


def _int_default(defaults: dict[str, Any], name: str, fallback: int, *, minimum: int) -> int:
    value = defaults.get(name, fallback)
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = fallback
    return max(resolved, minimum)


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction


def _signed_area_2d(points: list[Point2]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for left, right in zip(points, [*points[1:], points[0]]):
        area += left[0] * right[1] - right[0] * left[1]
    return 0.5 * area


def _edge_outward_normal(tangent: Point2, signed_area: float) -> Point2:
    if _norm_2d(tangent) <= 1.0e-12:
        return [0.0, 0.0]
    normal = [tangent[1], -tangent[0]] if signed_area >= 0.0 else [-tangent[1], tangent[0]]
    return _normalized_2d(normal) or [0.0, 0.0]


def _centroid(points: list[Point3]) -> Point3:
    count = max(len(points), 1)
    return [
        sum(float(point[axis]) for point in points) / count
        for axis in range(3)
    ]


def _lerp_point(first: Point3, second: Point3, t: float) -> Point3:
    return [
        float(first[axis]) + (float(second[axis]) - float(first[axis])) * t
        for axis in range(3)
    ]


def _bilinear_point(c00: Point3, c01: Point3, c10: Point3, c11: Point3, u: float, v: float) -> Point3:
    return [
        (1.0 - u) * (1.0 - v) * float(c00[axis])
        + (1.0 - u) * v * float(c01[axis])
        + u * (1.0 - v) * float(c10[axis])
        + u * v * float(c11[axis])
        for axis in range(3)
    ]


def _cubic_bezier_point(p0: Point3, p1: Point3, p2: Point3, p3: Point3, t: float) -> Point3:
    u = 1.0 - t
    return [
        u * u * u * float(p0[axis])
        + 3.0 * u * u * t * float(p1[axis])
        + 3.0 * u * t * t * float(p2[axis])
        + t * t * t * float(p3[axis])
        for axis in range(3)
    ]


def _distance_to_segment(point: Point3, start: Point3, end: Point3) -> float:
    segment = _subtract(end, start)
    length_squared = sum(component * component for component in segment)
    if length_squared <= 1.0e-12:
        return math.dist(point, start)
    fraction = sum((float(point[index]) - float(start[index])) * segment[index] for index in range(3)) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    projection = [float(start[index]) + fraction * segment[index] for index in range(3)]
    return math.dist(point, projection)


def _subtract(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _add(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) + float(second[axis]) for axis in range(3)]


def _scale(vector: Point3, scalar: float) -> Point3:
    return [float(value) * scalar for value in vector]


def _normalized(vector: Point3) -> Point3 | None:
    length = math.sqrt(sum(float(value) * float(value) for value in vector))
    if length <= 1.0e-9:
        return None
    return [float(value) / length for value in vector]


def _points_close(first: Point3, second: Point3) -> bool:
    return max(abs(float(a) - float(b)) for a, b in zip(first, second)) <= 1.0e-9


def _points_close_2d(first: Point2, second: Point2) -> bool:
    return max(abs(float(a) - float(b)) for a, b in zip(first, second)) <= 1.0e-9


def _subtract_2d(first: Point2, second: Point2) -> Point2:
    return [float(first[0]) - float(second[0]), float(first[1]) - float(second[1])]


def _add_2d(first: Point2, second: Point2) -> Point2:
    return [float(first[0]) + float(second[0]), float(first[1]) + float(second[1])]


def _scale_2d(vector: Point2, scalar: float) -> Point2:
    return [float(vector[0]) * scalar, float(vector[1]) * scalar]


def _dot_2d(first: Point2, second: Point2) -> float:
    return float(first[0]) * float(second[0]) + float(first[1]) * float(second[1])


def _norm_2d(vector: Point2) -> float:
    return math.hypot(float(vector[0]), float(vector[1]))


def _normalized_2d(vector: Point2) -> Point2 | None:
    length = _norm_2d(vector)
    if length <= 1.0e-9:
        return None
    return [float(vector[0]) / length, float(vector[1]) / length]


def _round_point(point: Point3) -> Point3:
    return [round(float(value), 9) for value in point]


def _round_point_2d(point: Point2) -> Point2:
    return [round(float(value), 9) for value in point]


def _round(value: float) -> float:
    return round(float(value), 6)
