from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from part_rule_synthesis.impeller_v11_4_engineering_drawing import (
    SEGMENT_ORDER,
    _all_dimensions,
    _blade_3d_callouts,
    _circle,
    _dimension,
    _finite,
    _loop_for_station,
    _meridional_dimensions,
    _note,
    _passage_dimension,
    _points,
    _profile_control_record,
    _representative_instances,
    _station_for_role,
    _support_radii,
    _top_cut_lines,
    _xy,
    _z_max,
    _z_min,
)


CONTRACT_VERSION = "1.1.5"
SPAN_ROLES = (
    ("active_root", 0.0),
    ("h_0_25", 0.25),
    ("midspan", 0.5),
    ("h_0_75", 0.75),
    ("active_tip", 1.0),
)
PRESENTATION_MODES = {
    "dimensioned_on_drawing",
    "listed_in_construction_table",
    "reported_as_quality_evidence",
    "not_applicable",
}


def build_engineering_drawing_contract(
    surface_graph: Mapping[str, Any],
    *,
    preset_id: str | None = None,
) -> dict[str, Any]:
    inspection = surface_graph.get("parameter_inspection", {})
    canonical = surface_graph.get("canonical_nurbs_parameterization", {})
    instances = inspection.get("blade_instances", {})
    representative = _representative_instances(instances)
    surfaces = list(surface_graph.get("surfaces", []))
    radii = _support_radii(surfaces)
    diameter = max(2.0 * radii["outer"], 1.0)
    tolerance = max(0.02, min(0.10, diameter / 10000.0))

    top = _top_view(surface_graph, inspection, instances, representative, surfaces, radii)
    meridional = _meridional_view(surface_graph, inspection, surfaces, radii, tolerance)
    s_q = _s_q_view(inspection, representative, surfaces)
    tables = _construction_tables(surface_graph, inspection, canonical, s_q)
    registry = _construction_registry(canonical)
    return {
        "contract_version": CONTRACT_VERSION,
        "generation_id": surface_graph.get("generation_id"),
        "geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "canonical_payload_version": canonical.get("canonical_payload_version"),
        "preset_id": preset_id,
        "units": "mm",
        "sampling_policy": {
            "kind": "adaptive_nurbs_drawing_sampling",
            "minimum_samples_per_curve": 129,
            "maximum_samples_per_curve": 1025,
            "maximum_chord_error_mm": tolerance,
        },
        "line_policy": {
            "visible_outline_mm": 0.5,
            "secondary_outline_mm": 0.25,
            "construction_mm": 0.25,
            "hidden_line_mm": 0.25,
            "section_hatch_angle_deg": 45.0,
            "screen_dimension_color": "#175ea8",
            "print_color": "#000000",
        },
        "views": {"top": top, "meridional": meridional, "s_q": s_q},
        "construction_tables": tables,
        "construction_parameter_registry": registry,
    }


def engineering_drawing_view(contract: Mapping[str, Any], view_id: str) -> dict[str, Any]:
    if view_id not in {"top", "meridional", "s_q"}:
        raise ValueError(f"unsupported engineering drawing view: {view_id}")
    table_ids = {
        "top": ("general_population", "blade_sections"),
        "meridional": ("support_profiles", "attachments"),
        "s_q": ("blade_sections", "pose_twist", "quality_constraints"),
    }[view_id]
    tables = contract.get("construction_tables", {})
    return {
        "contract_version": contract.get("contract_version"),
        "generation_id": contract.get("generation_id"),
        "geometry_patch_version": contract.get("geometry_patch_version"),
        "preset_id": contract.get("preset_id"),
        "units": contract.get("units"),
        "view_id": view_id,
        "view": contract.get("views", {}).get(view_id, {}),
        "construction_tables": {table_id: tables.get(table_id, {}) for table_id in table_ids},
        "registry_summary": {
            "record_count": len(contract.get("construction_parameter_registry", {}).get("records", [])),
            "unaccounted_parameter_ids": contract.get("construction_parameter_registry", {}).get(
                "unaccounted_parameter_ids", []
            ),
        },
    }


def validate_engineering_drawing_contract(
    surface_graph: Mapping[str, Any], contract: Mapping[str, Any]
) -> list[dict[str, str]]:
    if contract.get("contract_version") != CONTRACT_VERSION:
        return [{"reason": "engineering_drawing_contract_unsupported"}]
    if contract.get("generation_id") != surface_graph.get("generation_id"):
        return [{"reason": "engineering_drawing_generation_id_mismatch"}]
    views = contract.get("views")
    if not isinstance(views, Mapping) or set(views) != {"top", "meridional", "s_q"}:
        return [{"reason": "engineering_drawing_contract_unsupported"}]
    top_paths = views["top"].get("surface_projection_paths", [])
    if not top_paths or any(path.get("source_kind") != "surface_projection" for path in top_paths):
        return [{"reason": "engineering_drawing_top_surface_projection_missing"}]
    if {circle.get("id") for circle in views["top"].get("circles", [])} < {
        "hub_top_outer",
        "hub_top_inner",
        "mounting_bore",
    }:
        return [{"reason": "engineering_drawing_hub_topology_missing"}]
    for row in views["s_q"].get("blade_rows", []):
        if [section.get("station_role") for section in row.get("sections", [])] != [item[0] for item in SPAN_ROLES]:
            return [{"reason": "engineering_drawing_five_span_sections_missing"}]
        if len(row.get("overlay_loops_xyz", [])) != 5:
            return [{"reason": "engineering_drawing_xyz_overlay_missing"}]
    meridional = views["meridional"]
    if not meridional.get("profiles") or not meridional.get("control_polygons"):
        return [{"reason": "engineering_drawing_meridional_evidence_missing"}]
    if not meridional.get("material_regions") or not meridional.get("side_view", {}).get(
        "surface_projection_paths"
    ):
        return [{"reason": "engineering_drawing_section_or_side_view_missing"}]
    registry = contract.get("construction_parameter_registry", {})
    if registry.get("unaccounted_parameter_ids"):
        return [{"reason": "engineering_drawing_parameter_unaccounted"}]
    if any(record.get("presentation_mode") not in PRESENTATION_MODES for record in registry.get("records", [])):
        return [{"reason": "engineering_drawing_parameter_presentation_invalid"}]
    for dimension in _all_dimensions(views):
        if dimension.get("kind") == "note":
            continue
        if len(dimension.get("witness_points", [])) < 2 or not dimension.get("source_feature_ids"):
            return [{"reason": "engineering_drawing_dimension_evidence_missing"}]
        if "viewport" in dimension:
            return [{"reason": "engineering_drawing_viewport_dimension_forbidden"}]
    return []


def _top_view(
    surface_graph: Mapping[str, Any],
    inspection: Mapping[str, Any],
    instances: Mapping[str, Any],
    representative: Mapping[str, Mapping[str, Any]],
    surfaces: Sequence[Mapping[str, Any]],
    radii: Mapping[str, float],
) -> dict[str, Any]:
    surface_by_id = {surface.get("id"): surface for surface in surfaces}
    shrouded = any(surface.get("role") == "shroud_support" for surface in surfaces)
    projection_paths = []
    for instance in instances.values():
        for surface_id in instance.get("surface_ids", []):
            surface = surface_by_id.get(surface_id)
            if not surface:
                continue
            for boundary_index, boundary in enumerate(_surface_boundary_curves(surface)):
                points = _smooth_sampled_curve([_xy(point) for point in boundary], 257)
                if len(points) < 2:
                    continue
                projection_paths.append(
                    {
                        "id": f"{surface_id}:top_boundary:{boundary_index}",
                        "source_kind": "surface_projection",
                        "source_surface_id": surface_id,
                        "blade_instance_id": instance.get("blade_instance_id"),
                        "blade_class": instance.get("blade_class"),
                        "face_family": surface.get("face_family"),
                        "line_role": "hidden_outline" if shrouded else "visible_outline",
                        "points": points,
                    }
                )

    hub_inner, hub_outer = _hub_top_radii(surfaces, radii)
    circles = [
        _circle("outer_diameter", radii["outer"], "visible_outline"),
        _circle("hub_top_outer", hub_outer, "visible_outline"),
        _circle("hub_top_inner", hub_inner, "visible_outline"),
        _circle("mounting_bore", radii["bore"], "visible_outline"),
    ]
    cross_sections = []
    for blade_class in ("main", "splitter"):
        instance = representative.get(blade_class)
        if not instance:
            continue
        for role in ("active_root", "midspan", "active_tip"):
            station = _station_for_role(inspection, instance, role)
            cross_sections.append(_section_record(inspection, station, role, blade_class))

    population = surface_graph.get("canonical_nurbs_parameterization", {}).get("blade_population", {})
    outer = radii["outer"]
    bore = radii["bore"]
    pitch = float(
        inspection.get("resolved_dimensions", {}).get("angular_pitch_deg", {}).get("resolved_value", 0.0)
    )
    dimensions = [
        _dimension("overall_diameter", "diameter", f"\u00d8 {2 * outer:.1f}", 2 * outer, "mm", [[-outer, 0], [outer, 0]], ["outer_diameter"]),
        _dimension("mounting_bore_diameter", "diameter", f"\u00d8 {2 * bore:.1f}", 2 * bore, "mm", [[-bore, 0], [bore, 0]], ["mounting_bore"]),
        _dimension(
            "main_blade_pitch",
            "angular",
            f"PITCH {pitch:.2f}\u00b0",
            pitch,
            "deg",
            [[0, 0], [outer * 0.72, 0], [outer * 0.72 * math.cos(math.radians(pitch)), outer * 0.72 * math.sin(math.radians(pitch))]],
            ["axis", "blade_population"],
        ),
        _note(
            "blade_population",
            f"Z MAIN {int(population.get('main_blade_count', 0))} | Z SPLITTER {int(population.get('splitter_blade_count', 0))}",
        ),
    ]
    passage = _passage_dimension(inspection, instances)
    if passage:
        dimensions.append(passage)
    return {
        "projection": "orthographic_top_surface_projection",
        "surface_projection_paths": projection_paths,
        "circles": circles,
        "centerlines": [
            {"id": "horizontal_axis", "points": [[-outer * 1.08, 0], [outer * 1.08, 0]]},
            {"id": "vertical_axis", "points": [[0, -outer * 1.08], [0, outer * 1.08]]},
        ],
        "cut_lines": _top_cut_lines(outer),
        "cross_sections": cross_sections,
        "dimensions": dimensions,
    }


def _meridional_view(
    surface_graph: Mapping[str, Any],
    inspection: Mapping[str, Any],
    surfaces: Sequence[Mapping[str, Any]],
    radii: Mapping[str, float],
    tolerance: float,
) -> dict[str, Any]:
    support_profiles = surface_graph.get("canonical_nurbs_parameterization", {}).get("support_profiles", {})
    profiles = []
    for role, profile_name in (("hub", "hub_profile"), ("tip_or_shroud", "tip_or_shroud_profile")):
        profile = support_profiles.get(profile_name, {})
        points, measured_error = _adaptive_nurbs_sample(profile, tolerance)
        profiles.append(
            {
                "id": f"{role}_actual",
                "role": role,
                "source_kind": "evaluated_nurbs_curve",
                "points_r_z": points,
                "sampling": {
                    "sample_count": len(points),
                    "maximum_chord_error_mm": measured_error,
                    "tolerance_mm": tolerance,
                },
            }
        )
    controls = [
        _profile_control_record("hub", support_profiles.get("hub_profile", {})),
        _profile_control_record("tip_or_shroud", support_profiles.get("tip_or_shroud_profile", {})),
    ]
    hub_points = profiles[0]["points_r_z"]
    tip_points = profiles[1]["points_r_z"]
    material_regions = _material_regions(surfaces, hub_points, tip_points, radii)
    material_paths = [
        {"id": f"{region['id']}:boundary", "role": region["role"], "points_r_z": region["points_r_z"]}
        for region in material_regions
    ]
    return {
        "projection": "axisymmetric_section_r_z",
        "profiles": profiles,
        "material_paths": material_paths,
        "material_regions": material_regions,
        "control_polygons": controls,
        "centerlines": [
            {"id": "rotation_axis", "points_r_z": [[0, _z_min(hub_points, tip_points)], [0, _z_max(hub_points, tip_points)]]}
        ],
        "side_view": _side_view(surfaces),
        "dimensions": _meridional_dimensions(inspection, hub_points, tip_points, radii),
    }


def _s_q_view(
    inspection: Mapping[str, Any],
    representative: Mapping[str, Mapping[str, Any]],
    surfaces: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    surface_by_id = {surface.get("id"): surface for surface in surfaces}
    rows = []
    for blade_class in ("main", "splitter"):
        instance = representative.get(blade_class)
        if not instance:
            continue
        sections = []
        overlay_loops = []
        for role, target_h in SPAN_ROLES:
            station = _station_for_target_h(inspection, instance, target_h)
            section = _section_record(inspection, station, role, blade_class)
            sections.append(section)
            overlay_loops.append(
                {
                    "station_role": role,
                    "station_id": station.get("span_station_id"),
                    "h": station.get("h"),
                    "segments": [
                        {"feature_class": segment["feature_class"], "points_xyz": segment["points_xyz"]}
                        for segment in section["segments"]
                    ],
                }
            )
        midspan = sections[2]
        rows.append(
            {
                "blade_class": blade_class,
                "blade_instance_id": instance.get("blade_instance_id"),
                "sections": sections,
                "segments": midspan["segments"],
                "dimensions": midspan["dimensions"],
                "continuity": midspan["continuity"],
                "surface_ids": list(instance.get("surface_ids", [])),
                "representative_surfaces": [
                    surface_by_id[surface_id]
                    for surface_id in instance.get("surface_ids", [])
                    if surface_id in surface_by_id
                ],
                "overlay_loops_xyz": overlay_loops,
                "callouts": _blade_3d_callouts(inspection, blade_class),
            }
        )
    return {"projection": "five_span_s_q_plus_isometric", "blade_rows": rows, "dimensions": []}


def _section_record(
    inspection: Mapping[str, Any],
    station: Mapping[str, Any],
    role: str,
    blade_class: str,
) -> dict[str, Any]:
    loop = _loop_for_station(inspection, station)
    segments = []
    for name in SEGMENT_ORDER:
        segment = loop.get("segment_references", {}).get(name, {})
        segments.append(
            {
                "id": segment.get("section_segment_id"),
                "feature_class": name,
                "points_s_q_mm": _smooth_sampled_curve(_points(segment.get("display_points_s_q_mm", []), 2), 257),
                "control_points_s_q_mm": _points(segment.get("display_control_points_s_q_mm", []), 2),
                "points_xyz": _smooth_sampled_curve(_points(segment.get("points_xyz", []), 3), 257),
            }
        )
    return {
        "blade_class": blade_class,
        "station_role": role,
        "station_id": station.get("span_station_id"),
        "h": station.get("h"),
        "active_span_fraction": station.get("active_span_fraction"),
        "segments": segments,
        "dimensions": _section_dimensions(loop),
        "continuity": {
            "status": loop.get("metrics", {}).get("join_status"),
            "max_position_gap_mm": loop.get("metrics", {}).get("max_position_gap_mm"),
            "max_tangent_angle_deg": loop.get("metrics", {}).get("max_tangent_angle_deg"),
            "max_curvature_proxy_mismatch": loop.get("metrics", {}).get("max_curvature_proxy_mismatch"),
        },
    }


def _section_dimensions(loop: Mapping[str, Any]) -> list[dict[str, Any]]:
    from part_rule_synthesis.impeller_v11_4_engineering_drawing import _sq_dimensions

    return _sq_dimensions(loop)


def _construction_registry(canonical: Mapping[str, Any]) -> dict[str, Any]:
    records = []
    for parameter_id, value in _flatten_mapping(canonical):
        if parameter_id.startswith("blade_population"):
            mode, destination = "dimensioned_on_drawing", "top"
        elif parameter_id.startswith("metrics") or parameter_id.startswith("sampling_policy"):
            mode, destination = "reported_as_quality_evidence", "quality_constraints"
        elif parameter_id.startswith("attachment_policy") and value in (False, "disabled"):
            mode, destination = "not_applicable", "attachments"
        else:
            mode, destination = "listed_in_construction_table", _table_for_parameter(parameter_id)
        records.append(
            {
                "parameter_id": parameter_id,
                "value": value,
                "presentation_mode": mode,
                "destination": destination,
                "reason": "disabled by resolved topology" if mode == "not_applicable" else None,
            }
        )
    return {
        "records": records,
        "unaccounted_parameter_ids": [
            record["parameter_id"] for record in records if record["presentation_mode"] not in PRESENTATION_MODES
        ],
    }


def _construction_tables(
    surface_graph: Mapping[str, Any],
    inspection: Mapping[str, Any],
    canonical: Mapping[str, Any],
    s_q: Mapping[str, Any],
) -> dict[str, Any]:
    population = canonical.get("blade_population", {})
    support_profiles = canonical.get("support_profiles", {})
    blade_rows = []
    for row in s_q.get("blade_rows", []):
        for section in row.get("sections", []):
            metrics = {item["id"]: item.get("value") for item in section.get("dimensions", [])}
            blade_rows.append(
                {
                    "blade_class": row.get("blade_class"),
                    "station_role": section.get("station_role"),
                    "h": section.get("h"),
                    "streamwise_extent_mm": metrics.get("streamwise_extent"),
                    "thickness_0_1_mm": metrics.get("thickness_0.1"),
                    "thickness_0_5_mm": metrics.get("thickness_0.5"),
                    "thickness_0_9_mm": metrics.get("thickness_0.9"),
                    "maximum_thickness_mm": metrics.get("maximum_thickness"),
                    "leading_sagitta_mm": metrics.get("leading_sagitta"),
                    "trailing_sagitta_mm": metrics.get("trailing_sagitta"),
                    "continuity": section.get("continuity"),
                }
            )
    attachment_rows_raw = [
        {
            "parameter_id": parameter.get("parameter_id"),
            "label": parameter.get("label"),
            "value": parameter.get("resolved_value"),
            "unit": parameter.get("unit"),
        }
        for parameter in inspection.get("parameters", [])
        if "attachment:" in str(parameter.get("parameter_id")) or "shroud.thickness" in str(parameter.get("parameter_id"))
    ]
    attachment_rows_by_value: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in attachment_rows_raw:
        key = (row.get("label"), row.get("value"), row.get("unit"))
        if key not in attachment_rows_by_value:
            attachment_rows_by_value[key] = {**row, "occurrence_count": 1}
        else:
            attachment_rows_by_value[key]["occurrence_count"] += 1
    attachment_rows = list(attachment_rows_by_value.values())
    return {
        "general_population": {
            "title": "General / Population",
            "rows": [{"parameter": key, "value": value} for key, value in population.items()],
        },
        "support_profiles": {
            "title": "Support Profile NURBS",
            "rows": [
                {
                    "profile": name,
                    "degree": profile.get("degree"),
                    "knots": profile.get("knots"),
                    "weights": profile.get("weights"),
                    "control_points_r_z": profile.get("control_points"),
                }
                for name, profile in support_profiles.items()
            ],
        },
        "blade_sections": {"title": "Blade Sections", "rows": blade_rows},
        "pose_twist": {
            "title": "Skeleton / Pose / Thickness Fields",
            "rows": [
                {"field": field_name, **dict(canonical.get(field_name, {}))}
                for field_name in ("blade_skeleton_field", "pose_field", "thickness_field")
            ],
        },
        "attachments": {
            "title": "Root / Shroud Attachments",
            "policy": canonical.get("attachment_policy", {}),
            "rows": attachment_rows,
        },
        "quality_constraints": {
            "title": "Quality / Constraints",
            "rows": [
                {"metric": key, "value": value}
                for key, value in {
                    **canonical.get("metrics", {}),
                    **surface_graph.get("v1_1_loop_family_metrics", {}),
                }.items()
            ],
        },
    }


def _surface_boundary_curves(surface: Mapping[str, Any]) -> list[list[list[float]]]:
    grid = surface.get("uv_grid", [])
    if not _rectangular_grid(grid):
        return []
    last_row = len(grid) - 1
    last_column = len(grid[0]) - 1
    face_family = str(surface.get("face_family", ""))
    if face_family in {"blade_pressure", "blade_suction"}:
        candidates = [grid[0], grid[last_row]]
    else:
        candidates = [grid[0], grid[last_row], [row[0] for row in grid], [row[last_column] for row in grid]]
    return [[list(point) for point in curve if _finite(point, 3)] for curve in candidates]


def _hub_top_radii(
    surfaces: Sequence[Mapping[str, Any]], radii: Mapping[str, float]
) -> tuple[float, float]:
    annulus = next((surface for surface in surfaces if surface.get("id") == "hub_top_annulus_surface"), None)
    points = [
        point
        for row in (annulus or {}).get("uv_grid", [])
        for point in row
        if _finite(point, 3)
    ]
    radial = [math.hypot(float(point[0]), float(point[1])) for point in points]
    return (
        min(radial, default=radii["hub_eye"]),
        max(radial, default=max(radii["hub_eye"], radii["bore"])),
    )


def _material_regions(
    surfaces: Sequence[Mapping[str, Any]],
    hub_points: Sequence[Sequence[float]],
    tip_points: Sequence[Sequence[float]],
    radii: Mapping[str, float],
) -> list[dict[str, Any]]:
    hub_material_points = [
        point
        for surface in surfaces
        if surface.get("role") == "hub_support"
        for row in surface.get("uv_grid", [])
        for point in row
        if _finite(point, 3)
    ]
    bottom_z = min((float(point[2]) for point in hub_material_points), default=min(point[1] for point in hub_points))
    hub_polygon = [list(point) for point in hub_points]
    hub_polygon.extend(
        [
            [float(hub_points[-1][0]), bottom_z],
            [radii["bore"], bottom_z],
            [radii["bore"], float(hub_points[0][1])],
            [float(hub_points[0][0]), float(hub_points[0][1])],
        ]
    )
    regions = [{"id": "hub_material", "role": "hub_material", "closed": True, "points_r_z": hub_polygon}]
    outer_surface = next((surface for surface in surfaces if surface.get("id") == "shroud_outer_material_surface"), None)
    if outer_surface:
        outer = _smooth_sampled_curve(
            [
                [math.hypot(float(row[0][0]), float(row[0][1])), float(row[0][2])]
                for row in outer_surface.get("uv_grid", [])
                if row and _finite(row[0], 3)
            ],
            257,
        )
        if outer:
            regions.append(
                {
                    "id": "shroud_material",
                    "role": "shroud_material",
                    "closed": True,
                    "points_r_z": [list(point) for point in tip_points] + list(reversed(outer)) + [list(tip_points[0])],
                }
            )
    return regions


def _side_view(surfaces: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    paths = []
    for surface in surfaces:
        if surface.get("display", {}).get("reference_only"):
            continue
        if surface.get("role") not in {
            "hub_support",
            "shroud_support",
            "mounting_bore",
            "blade_pressure",
            "blade_suction",
            "blade_leading_edge",
            "blade_trailing_edge",
            "open_tip_dome",
            "root_to_hub_attachment",
            "tip_to_shroud_attachment",
        }:
            continue
        for index, boundary in enumerate(_surface_boundary_curves(surface)):
            points = _smooth_sampled_curve([[float(point[0]), float(point[2])] for point in boundary], 129)
            if len(points) > 1:
                paths.append(
                    {
                        "id": f"{surface.get('id')}:side:{index}",
                        "source_kind": "surface_projection",
                        "source_surface_id": surface.get("id"),
                        "points_x_z": points,
                    }
                )
    return {"projection": "orthographic_side_x_z", "surface_projection_paths": paths}


def _adaptive_nurbs_sample(
    profile: Mapping[str, Any], tolerance: float
) -> tuple[list[list[float]], float]:
    degree = int(profile.get("degree", 1))
    controls = _points(profile.get("control_points", []), 2)
    weights = [float(value) for value in profile.get("weights", [1.0] * len(controls))]
    knots = [float(value) for value in profile.get("knots", [])]
    if not controls or len(weights) != len(controls) or len(knots) != len(controls) + degree + 1:
        return _smooth_sampled_curve(controls, 129), tolerance
    start = knots[degree]
    end = knots[-degree - 1]
    parameters = [start + (end - start) * index / 128 for index in range(129)]
    points = [_rational_curve_point(controls, weights, knots, degree, value) for value in parameters]
    maximum_error = 0.0
    while len(points) < 1025:
        additions = []
        for index in range(len(parameters) - 1):
            mid_parameter = (parameters[index] + parameters[index + 1]) / 2
            midpoint = _rational_curve_point(controls, weights, knots, degree, mid_parameter)
            error = _point_to_segment_distance(midpoint, points[index], points[index + 1])
            maximum_error = max(maximum_error, error)
            if error > tolerance:
                additions.append((index + 1, mid_parameter, midpoint))
        if not additions:
            break
        for index, parameter, point in reversed(additions[: 1025 - len(points)]):
            parameters.insert(index, parameter)
            points.insert(index, point)
    measured = 0.0
    for index in range(len(parameters) - 1):
        midpoint = _rational_curve_point(controls, weights, knots, degree, (parameters[index] + parameters[index + 1]) / 2)
        measured = max(measured, _point_to_segment_distance(midpoint, points[index], points[index + 1]))
    return points, measured


def _rational_curve_point(
    controls: Sequence[Sequence[float]],
    weights: Sequence[float],
    knots: Sequence[float],
    degree: int,
    parameter: float,
) -> list[float]:
    basis = [_basis_function(index, degree, parameter, knots) for index in range(len(controls))]
    denominator = sum(basis[index] * weights[index] for index in range(len(controls)))
    if abs(denominator) <= 1.0e-12:
        return list(controls[-1] if parameter >= knots[-degree - 1] else controls[0])
    return [
        sum(basis[index] * weights[index] * float(controls[index][axis]) for index in range(len(controls))) / denominator
        for axis in range(2)
    ]


def _basis_function(index: int, degree: int, parameter: float, knots: Sequence[float]) -> float:
    if degree == 0:
        if knots[index] <= parameter < knots[index + 1]:
            return 1.0
        if parameter == knots[-1] and knots[index + 1] == knots[-1]:
            return 1.0
        return 0.0
    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left = 0.0 if left_denominator == 0 else (parameter - knots[index]) / left_denominator * _basis_function(index, degree - 1, parameter, knots)
    right = 0.0 if right_denominator == 0 else (knots[index + degree + 1] - parameter) / right_denominator * _basis_function(index + 1, degree - 1, parameter, knots)
    return left + right


def _smooth_sampled_curve(points: Sequence[Sequence[float]], count: int) -> list[list[float]]:
    clean = [list(map(float, point)) for point in points if len(point) >= 2 and all(math.isfinite(float(value)) for value in point)]
    if len(clean) < 2:
        return clean
    if len(clean) == 2:
        return [
            [clean[0][axis] + (clean[1][axis] - clean[0][axis]) * index / (count - 1) for axis in range(len(clean[0]))]
            for index in range(count)
        ]
    result = []
    for sample_index in range(count):
        scaled = sample_index * (len(clean) - 1) / (count - 1)
        index = min(int(math.floor(scaled)), len(clean) - 2)
        t = scaled - index
        p0 = clean[max(index - 1, 0)]
        p1 = clean[index]
        p2 = clean[index + 1]
        p3 = clean[min(index + 2, len(clean) - 1)]
        result.append(
            [
                0.5
                * (
                    2 * p1[axis]
                    + (-p0[axis] + p2[axis]) * t
                    + (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis]) * t * t
                    + (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]) * t * t * t
                )
                for axis in range(len(p1))
            ]
        )
    return result


def _point_to_segment_distance(point, start, end) -> float:
    vector = [end[axis] - start[axis] for axis in range(2)]
    denominator = sum(value * value for value in vector)
    if denominator <= 1.0e-18:
        return math.dist(point, start)
    t = max(0.0, min(1.0, sum((point[axis] - start[axis]) * vector[axis] for axis in range(2)) / denominator))
    projection = [start[axis] + t * vector[axis] for axis in range(2)]
    return math.dist(point, projection)


def _station_for_target_h(
    inspection: Mapping[str, Any], instance: Mapping[str, Any], target_h: float
) -> Mapping[str, Any]:
    stations = [
        inspection.get("span_stations", {}).get(station_id, {})
        for station_id in instance.get("span_station_ids", [])
    ]
    stations = [station for station in stations if station]
    return min(stations, key=lambda station: abs(float(station.get("h", 0.0)) - target_h)) if stations else {}


def _flatten_mapping(value: Any, prefix: str = ""):
    if isinstance(value, Mapping):
        for key in sorted(value):
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_mapping(value[key], next_prefix)
        return
    yield prefix, value


def _table_for_parameter(parameter_id: str) -> str:
    if parameter_id.startswith("support_profiles"):
        return "support_profiles"
    if parameter_id.startswith(("blade_skeleton_field", "pose_field", "thickness_field")):
        return "pose_twist"
    if parameter_id.startswith(("active_span_policy", "attachment_policy")):
        return "attachments"
    if parameter_id.startswith("section_loop_family"):
        return "blade_sections"
    return "general_population"


def _rectangular_grid(grid: Any) -> bool:
    return (
        isinstance(grid, list)
        and len(grid) >= 2
        and isinstance(grid[0], list)
        and len(grid[0]) >= 2
        and all(isinstance(row, list) and len(row) == len(grid[0]) for row in grid)
    )
