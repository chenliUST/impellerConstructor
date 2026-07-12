from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


CONTRACT_VERSION = "1.1.4"
SEGMENT_ORDER = ("pressure_side", "leading_edge", "suction_side", "trailing_edge")


def build_engineering_drawing_contract(
    surface_graph: Mapping[str, Any],
    *,
    preset_id: str | None = None,
) -> dict[str, Any]:
    inspection = surface_graph.get("parameter_inspection", {})
    canonical = surface_graph.get("canonical_nurbs_parameterization", {})
    population = canonical.get("blade_population", {})
    instances = inspection.get("blade_instances", {})
    representative = _representative_instances(instances)
    support_profiles = canonical.get("support_profiles", {})
    hub_profile = support_profiles.get("hub_profile", {})
    tip_profile = support_profiles.get("tip_or_shroud_profile", {})
    surfaces = list(surface_graph.get("surfaces", []))
    radii = _support_radii(surfaces)

    top = _top_view(
        inspection,
        instances,
        representative,
        population,
        radii,
    )
    meridional = _meridional_view(
        inspection,
        surfaces,
        hub_profile,
        tip_profile,
        radii,
    )
    s_q = _s_q_view(inspection, representative)
    return {
        "contract_version": CONTRACT_VERSION,
        "generation_id": surface_graph.get("generation_id"),
        "geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "preset_id": preset_id,
        "units": "mm",
        "line_policy": {
            "visible_outline_mm": 0.5,
            "secondary_outline_mm": 0.25,
            "construction_mm": 0.25,
            "screen_dimension_color": "#175ea8",
            "print_color": "#000000",
        },
        "views": {"top": top, "meridional": meridional, "s_q": s_q},
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
    top_sections = views["top"].get("cross_sections", [])
    if [item.get("station_role") for item in top_sections] != [
        "active_root",
        "midspan",
        "active_tip",
    ]:
        return [{"reason": "engineering_drawing_span_sections_missing"}]
    if not views["meridional"].get("profiles") or not views["meridional"].get("control_polygons"):
        return [{"reason": "engineering_drawing_meridional_evidence_missing"}]
    for dimension in _all_dimensions(views):
        if dimension.get("kind") == "note":
            continue
        if len(dimension.get("witness_points", [])) < 2 or not dimension.get("source_feature_ids"):
            return [{"reason": "engineering_drawing_dimension_evidence_missing"}]
        if "viewport" in dimension:
            return [{"reason": "engineering_drawing_viewport_dimension_forbidden"}]
    return []


def _top_view(
    inspection: Mapping[str, Any],
    instances: Mapping[str, Any],
    representative: Mapping[str, Mapping[str, Any]],
    population: Mapping[str, Any],
    radii: Mapping[str, float],
) -> dict[str, Any]:
    outline_paths: list[dict[str, Any]] = []
    for instance in instances.values():
        station = _station_for_role(inspection, instance, "midspan")
        loop = _loop_for_station(inspection, station)
        for name in SEGMENT_ORDER:
            segment = loop.get("segment_references", {}).get(name, {})
            points = [_xy(point) for point in segment.get("points_xyz", []) if _finite(point, 3)]
            if len(points) > 1:
                outline_paths.append(
                    {
                        "id": segment.get("section_segment_id", f"{instance.get('blade_instance_id')}:{name}"),
                        "feature_class": name,
                        "blade_class": instance.get("blade_class"),
                        "points": _downsample(points, 96),
                    }
                )

    circles = [
        _circle("outer_diameter", radii["outer"], "visible_outline"),
        _circle("mounting_bore", radii["bore"], "visible_outline"),
        _circle("hub_eye", radii["hub_eye"], "secondary_outline"),
    ]
    main = representative.get("main")
    cross_sections = []
    if main:
        for role in ("active_root", "midspan", "active_tip"):
            station = _station_for_role(inspection, main, role)
            loop = _loop_for_station(inspection, station)
            cross_sections.append(_section_record(loop, station, role))

    outer = radii["outer"]
    bore = radii["bore"]
    pitch = float(inspection.get("resolved_dimensions", {}).get("angular_pitch_deg", {}).get("resolved_value", 0.0))
    main_count = int(population.get("main_blade_count", 0))
    splitter_count = int(population.get("splitter_blade_count", 0))
    dimensions = [
        _dimension(
            "overall_diameter",
            "diameter",
            f"Ø {2.0 * outer:.1f}",
            2.0 * outer,
            "mm",
            [[-outer, 0.0], [outer, 0.0]],
            ["outer_diameter"],
        ),
        _dimension(
            "mounting_bore_diameter",
            "diameter",
            f"Ø {2.0 * bore:.1f}",
            2.0 * bore,
            "mm",
            [[-bore, 0.0], [bore, 0.0]],
            ["mounting_bore"],
        ),
        _dimension(
            "main_blade_pitch",
            "angular",
            f"PITCH {pitch:.2f}°",
            pitch,
            "deg",
            [
                [0.0, 0.0],
                [outer * 0.72, 0.0],
                [outer * 0.72 * math.cos(math.radians(pitch)), outer * 0.72 * math.sin(math.radians(pitch))],
            ],
            ["axis", "blade_population"],
        ),
        _note("blade_population", f"Z MAIN {main_count}  |  Z SPLITTER {splitter_count}"),
    ]
    passage = _passage_dimension(inspection, instances)
    if passage:
        dimensions.append(passage)
    return {
        "projection": "orthographic_top",
        "outline_paths": outline_paths,
        "circles": circles,
        "centerlines": [
            {"id": "horizontal_axis", "points": [[-outer * 1.08, 0.0], [outer * 1.08, 0.0]]},
            {"id": "vertical_axis", "points": [[0.0, -outer * 1.08], [0.0, outer * 1.08]]},
        ],
        "cut_lines": _top_cut_lines(outer),
        "cross_sections": cross_sections,
        "dimensions": dimensions,
    }


def _meridional_view(
    inspection: Mapping[str, Any],
    surfaces: Sequence[Mapping[str, Any]],
    hub_profile: Mapping[str, Any],
    tip_profile: Mapping[str, Any],
    radii: Mapping[str, float],
) -> dict[str, Any]:
    profiles = []
    for role, surface_roles in (
        ("hub", {"hub_support"}),
        ("tip_or_shroud", {"shroud_support", "open_tip_reference"}),
    ):
        surface = next(
            (item for item in surfaces if item.get("role") in surface_roles and item.get("uv_grid")),
            None,
        )
        points = _surface_meridional_curve(surface) if surface else []
        if points:
            profiles.append({"id": f"{role}_actual", "role": role, "points_r_z": points})

    control_polygons = [
        _profile_control_record("hub", hub_profile),
        _profile_control_record("tip_or_shroud", tip_profile),
    ]
    control_polygons = [item for item in control_polygons if item["control_points_r_z"]]
    material_paths = []
    for surface in surfaces:
        if surface.get("role") not in {"hub_support", "shroud_support", "mounting_bore"}:
            continue
        boundary = _surface_meridional_boundaries(surface)
        if boundary:
            material_paths.extend(
                {"id": f"{surface.get('id')}:{index}", "role": surface.get("role"), "points_r_z": path}
                for index, path in enumerate(boundary)
            )

    hub_points = profiles[0]["points_r_z"] if profiles else hub_profile.get("control_points", [])
    tip_item = next((item for item in profiles if item["role"] == "tip_or_shroud"), None)
    tip_points = tip_item["points_r_z"] if tip_item else tip_profile.get("control_points", [])
    dimensions = _meridional_dimensions(inspection, hub_points, tip_points, radii)
    return {
        "projection": "axisymmetric_section_r_z",
        "profiles": profiles,
        "material_paths": material_paths,
        "control_polygons": control_polygons,
        "centerlines": [{"id": "rotation_axis", "points_r_z": [[0.0, _z_min(hub_points, tip_points)], [0.0, _z_max(hub_points, tip_points)]]}],
        "dimensions": dimensions,
    }


def _s_q_view(
    inspection: Mapping[str, Any], representative: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    rows = []
    for blade_class in ("main", "splitter"):
        instance = representative.get(blade_class)
        if not instance:
            continue
        station = _station_for_role(inspection, instance, "midspan")
        loop = _loop_for_station(inspection, station)
        section = _section_record(loop, station, "midspan")
        rows.append(
            {
                "blade_class": blade_class,
                "blade_instance_id": instance.get("blade_instance_id"),
                "station_id": station.get("span_station_id"),
                "segments": section["segments"],
                "dimensions": _sq_dimensions(loop),
                "continuity": {
                    "status": loop.get("metrics", {}).get("join_status"),
                    "max_position_gap_mm": loop.get("metrics", {}).get("max_position_gap_mm"),
                    "max_tangent_angle_deg": loop.get("metrics", {}).get("max_tangent_angle_deg"),
                    "max_curvature_proxy_mismatch": loop.get("metrics", {}).get("max_curvature_proxy_mismatch"),
                },
                "surface_ids": list(instance.get("surface_ids", [])),
                "callouts": _blade_3d_callouts(inspection, blade_class),
            }
        )
    return {
        "projection": "blade_to_blade_s_q_plus_isometric",
        "blade_rows": rows,
        "dimensions": [],
    }


def _section_record(loop: Mapping[str, Any], station: Mapping[str, Any], role: str) -> dict[str, Any]:
    segments = []
    for name in SEGMENT_ORDER:
        segment = loop.get("segment_references", {}).get(name, {})
        segments.append(
            {
                "id": segment.get("section_segment_id"),
                "feature_class": name,
                "points_s_q_mm": _points(segment.get("display_points_s_q_mm", []), 2),
                "control_points_s_q_mm": _points(segment.get("display_control_points_s_q_mm", []), 2),
            }
        )
    return {
        "station_role": role,
        "station_id": station.get("span_station_id"),
        "h": station.get("h"),
        "active_span_fraction": station.get("active_span_fraction"),
        "segments": segments,
        "dimensions": _sq_dimensions(loop),
    }


def _sq_dimensions(loop: Mapping[str, Any]) -> list[dict[str, Any]]:
    segments = loop.get("segment_references", {})
    pressure = _points(segments.get("pressure_side", {}).get("display_points_s_q_mm", []), 2)
    suction = _points(segments.get("suction_side", {}).get("display_points_s_q_mm", []), 2)
    if not pressure or not suction:
        return []
    all_points = pressure + suction
    s_min = min(point[0] for point in all_points)
    s_max = max(point[0] for point in all_points)
    dimensions = [
        _dimension(
            "streamwise_extent",
            "linear",
            f"S {s_max - s_min:.1f}",
            s_max - s_min,
            "mm",
            [[s_min, 0.0], [s_max, 0.0]],
            [loop.get("section_loop_id", "section_loop")],
        )
    ]
    samples = []
    for fraction in (0.1, 0.5, 0.9):
        index = min(round(fraction * (min(len(pressure), len(suction)) - 1)), len(pressure) - 1, len(suction) - 1)
        p_point, s_point = pressure[index], suction[index]
        thickness = abs(s_point[1] - p_point[1])
        samples.append((thickness, p_point, s_point, fraction))
        dimensions.append(
            _dimension(
                f"thickness_{fraction:.1f}",
                "linear",
                f"t{s_point[0] / max(s_max, 1.0):.1f} {thickness:.2f}",
                thickness,
                "mm",
                [p_point, s_point],
                [segments.get("pressure_side", {}).get("section_segment_id"), segments.get("suction_side", {}).get("section_segment_id")],
            )
        )
    maximum = max(
        (
            (abs(suction[index][1] - pressure[index][1]), pressure[index], suction[index])
            for index in range(min(len(pressure), len(suction)))
        ),
        default=None,
    )
    if maximum:
        dimensions.append(
            _dimension(
                "maximum_thickness",
                "linear",
                f"t MAX {maximum[0]:.2f}",
                maximum[0],
                "mm",
                [maximum[1], maximum[2]],
                [segments.get("pressure_side", {}).get("section_segment_id"), segments.get("suction_side", {}).get("section_segment_id")],
            )
        )
    metrics = loop.get("metrics", {})
    for edge, key in (("leading", "leading_cap_sagitta_resolved_mm"), ("trailing", "trailing_cap_sagitta_resolved_mm")):
        edge_points = _points(segments.get(f"{edge}_edge", {}).get("display_points_s_q_mm", []), 2)
        if len(edge_points) >= 3:
            apex = min(edge_points, key=lambda point: point[0]) if edge == "leading" else max(edge_points, key=lambda point: point[0])
            chord_mid = [(edge_points[0][0] + edge_points[-1][0]) / 2, (edge_points[0][1] + edge_points[-1][1]) / 2]
            value = float(metrics.get(key, math.dist(apex, chord_mid)))
            dimensions.append(
                _dimension(
                    f"{edge}_sagitta",
                    "linear",
                    f"{edge.upper()} SAG {value:.2f}",
                    value,
                    "mm",
                    [chord_mid, apex],
                    [segments.get(f"{edge}_edge", {}).get("section_segment_id")],
                )
            )
    for label, fraction in (("LE", 0.04), ("MID", 0.5), ("TE", 0.96)):
        index = min(max(round(fraction * (len(pressure) - 1)), 1), len(pressure) - 2)
        before, after = pressure[index - 1], pressure[index + 1]
        angle = math.degrees(math.atan2(after[1] - before[1], after[0] - before[0]))
        dimensions.append(
            _dimension(
                f"blade_angle_{label.lower()}",
                "angular",
                f"β {label} {angle:.1f}°",
                angle,
                "deg",
                [pressure[index], before, after],
                [segments.get("pressure_side", {}).get("section_segment_id")],
            )
        )
    return dimensions


def _meridional_dimensions(
    inspection: Mapping[str, Any],
    hub: Sequence[Sequence[float]],
    tip: Sequence[Sequence[float]],
    radii: Mapping[str, float],
) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    outer = radii["outer"]
    bore = radii["bore"]
    dimensions.extend(
        [
            _dimension("meridional_outer_radius", "radial", f"R {outer:.1f}", outer, "mm", [[0.0, 0.0], [outer, 0.0]], ["outer_diameter"]),
            _dimension("meridional_bore_diameter", "diameter", f"Ø {2 * bore:.1f}", 2 * bore, "mm", [[-bore, 0.0], [bore, 0.0]], ["mounting_bore"]),
        ]
    )
    if hub and tip:
        for label, index in (("inlet", 0), ("outlet", -1)):
            hub_point = [float(hub[index][0]), float(hub[index][1])]
            tip_point = [float(tip[index][0]), float(tip[index][1])]
            height = math.dist(hub_point, tip_point)
            dimensions.append(
                _dimension(
                    f"{label}_blade_height",
                    "linear",
                    f"b {label.upper()} {height:.1f}",
                    height,
                    "mm",
                    [hub_point, tip_point],
                    ["hub_actual", "tip_or_shroud_actual"],
                )
            )
        z_values = [float(point[1]) for point in list(hub) + list(tip)]
        z_min, z_max = min(z_values), max(z_values)
        dimensions.append(
            _dimension("axial_extent", "linear", f"L {z_max - z_min:.1f}", z_max - z_min, "mm", [[0.0, z_min], [0.0, z_max]], ["hub_actual", "tip_or_shroud_actual"])
        )
    dimensions.extend(_inspection_attachment_dimensions(inspection))
    dimensions.extend(_profile_endpoint_angle_notes("hub", hub))
    dimensions.extend(_profile_endpoint_angle_notes("tip/shroud", tip))
    return dimensions


def _inspection_attachment_dimensions(inspection: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    selected: dict[str, Mapping[str, Any]] = {}
    for parameter in inspection.get("parameters", []):
        parameter_id = str(parameter.get("parameter_id", ""))
        semantic_key = next(
            (
                key
                for key in (
                    "attachment:root:lift",
                    "attachment:root:width",
                    "attachment:shroud:lift",
                    "attachment:shroud:width",
                    "shroud.thickness",
                )
                if key in parameter_id
            ),
            None,
        )
        if not semantic_key or semantic_key in selected:
            continue
        selected[semantic_key] = parameter

    for semantic_key, parameter in selected.items():
        parameter_id = str(parameter.get("parameter_id", semantic_key))
        definition = parameter.get("dimension_definition") or {}
        points = [_rz(point) for point in definition.get("measurement_points", []) if _finite(point, 2)]
        if len(points) < 2:
            continue
        value = float(parameter.get("resolved_value", 0.0))
        records.append(
            _dimension(
                parameter_id,
                "linear",
                f"{parameter.get('label', parameter_id.split(':')[-1]).upper()} {value:.2f}",
                value,
                str(parameter.get("unit", "mm")),
                points,
                [feature.get("id") for feature in parameter.get("feature_geometry", []) if feature.get("id")] or [parameter_id],
            )
        )
    return records


def _blade_3d_callouts(inspection: Mapping[str, Any], blade_class: str) -> list[dict[str, Any]]:
    dimensions = inspection.get("resolved_dimensions", {})
    return [
        {"id": f"{blade_class}_root_offset", "label": "ROOT LIFT", "value": dimensions.get("root_offset_mm", {}).get("resolved_value"), "unit": "mm"},
        {"id": f"{blade_class}_tip_offset", "label": "TIP/SHROUD OFFSET", "value": dimensions.get("tip_offset_mm", {}).get("resolved_value"), "unit": "mm"},
        {"id": f"{blade_class}_pose_range", "label": "POSE θ", "value": [dimensions.get("pose_theta_min_deg", {}).get("resolved_value"), dimensions.get("pose_theta_max_deg", {}).get("resolved_value")], "unit": "deg"},
    ]


def _representative_instances(instances: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for instance in instances.values():
        blade_class = instance.get("blade_class")
        if blade_class in {"main", "splitter"} and blade_class not in result:
            result[blade_class] = instance
    return result


def _station_for_role(
    inspection: Mapping[str, Any], instance: Mapping[str, Any], role: str
) -> Mapping[str, Any]:
    stations = [
        inspection.get("span_stations", {}).get(station_id, {})
        for station_id in instance.get("span_station_ids", [])
    ]
    stations = sorted((item for item in stations if item), key=lambda item: float(item.get("h", 0.0)))
    if not stations:
        return {}
    if role == "active_root":
        return stations[0]
    if role == "active_tip":
        return stations[-1]
    return min(stations, key=lambda item: abs(float(item.get("h", 0.0)) - 0.5))


def _loop_for_station(inspection: Mapping[str, Any], station: Mapping[str, Any]) -> Mapping[str, Any]:
    return inspection.get("section_loops", {}).get(station.get("section_loop_id"), {})


def _support_radii(surfaces: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    support_points = []
    bore_points = []
    hub_points = []
    for surface in surfaces:
        points = [point for row in surface.get("uv_grid", []) if isinstance(row, list) for point in row if _finite(point, 3)]
        if surface.get("role") in {"hub_support", "shroud_support", "open_tip_reference"}:
            support_points.extend(points)
        if surface.get("role") == "hub_support":
            hub_points.extend(points)
        if surface.get("role") == "mounting_bore":
            bore_points.extend(points)
    radial = lambda point: math.hypot(float(point[0]), float(point[1]))
    outer = max((radial(point) for point in support_points), default=1.0)
    bore = sum(radial(point) for point in bore_points) / len(bore_points) if bore_points else max(outer * 0.05, 1.0)
    hub_eye = min((radial(point) for point in hub_points if radial(point) > bore * 1.01), default=bore * 1.5)
    return {"outer": outer, "bore": bore, "hub_eye": hub_eye}


def _passage_dimension(
    inspection: Mapping[str, Any], instances: Mapping[str, Any]
) -> dict[str, Any] | None:
    mains = [item for item in instances.values() if item.get("blade_class") == "main"]
    if len(mains) < 2:
        return None
    loops = []
    for instance in mains[:2]:
        station = _station_for_role(inspection, instance, "midspan")
        loops.append(_loop_for_station(inspection, station))
    first = loops[0].get("segment_references", {}).get("suction_side", {}).get("points_xyz", [])
    second = loops[1].get("segment_references", {}).get("pressure_side", {}).get("points_xyz", [])
    if not first or not second:
        return None
    a = _xy(first[len(first) // 2])
    b = _xy(second[len(second) // 2])
    value = math.dist(a, b)
    return _dimension("mid_passage_width", "linear", f"PASSAGE {value:.1f}", value, "mm", [a, b], ["main_passage_0"])


def _top_cut_lines(radius: float) -> list[dict[str, Any]]:
    result = []
    for label, angle in (("A-A", 0.0), ("B-B", 120.0), ("C-C", 240.0)):
        direction = [math.cos(math.radians(angle)), math.sin(math.radians(angle))]
        result.append(
            {
                "id": label,
                "label": label,
                "points": [[-direction[0] * radius, -direction[1] * radius], [direction[0] * radius, direction[1] * radius]],
            }
        )
    return result


def _profile_control_record(role: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{role}_control_polygon",
        "role": role,
        "degree": profile.get("degree"),
        "knots": profile.get("knots", []),
        "weights": profile.get("weights", []),
        "control_points_r_z": _points(profile.get("control_points", []), 2),
    }


def _surface_meridional_curve(surface: Mapping[str, Any]) -> list[list[float]]:
    grid = surface.get("uv_grid", [])
    if not grid:
        return []
    return _downsample([_rz(row[0]) for row in grid if row and _finite(row[0], 3)], 180)


def _surface_meridional_boundaries(surface: Mapping[str, Any]) -> list[list[list[float]]]:
    grid = surface.get("uv_grid", [])
    if not grid or not grid[0]:
        return []
    first = [_rz(row[0]) for row in grid if row and _finite(row[0], 3)]
    last = [_rz(row[-1]) for row in grid if row and _finite(row[-1], 3)]
    return [_downsample(path, 120) for path in (first, last) if len(path) > 1]


def _profile_endpoint_angle_notes(role: str, points: Sequence[Sequence[float]]) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []
    result = []
    for label, pair in (("IN", (points[0], points[1])), ("OUT", (points[-2], points[-1]))):
        left, right = pair
        angle = math.degrees(math.atan2(float(right[1]) - float(left[1]), float(right[0]) - float(left[0])))
        result.append(_note(f"{role}_{label.lower()}_tangent", f"{role.upper()} ε {label} {angle:.1f}°"))
    return result


def _dimension(
    dimension_id: str,
    kind: str,
    label: str,
    value: float,
    unit: str,
    witness_points: Sequence[Sequence[float]],
    source_feature_ids: Sequence[str | None],
) -> dict[str, Any]:
    return {
        "id": dimension_id,
        "kind": kind,
        "label": label,
        "value": round(float(value), 6),
        "unit": unit,
        "witness_points": _points(witness_points, 2),
        "source_feature_ids": [item for item in source_feature_ids if item],
    }


def _note(note_id: str, label: str) -> dict[str, Any]:
    return {"id": note_id, "kind": "note", "label": label, "source_feature_ids": [note_id]}


def _circle(circle_id: str, radius: float, line_role: str) -> dict[str, Any]:
    return {"id": circle_id, "center": [0.0, 0.0], "radius": radius, "line_role": line_role}


def _all_dimensions(views: Mapping[str, Any]):
    for view in views.values():
        yield from view.get("dimensions", [])
        for section in view.get("cross_sections", []):
            yield from section.get("dimensions", [])
        for row in view.get("blade_rows", []):
            yield from row.get("dimensions", [])


def _points(points: Sequence[Sequence[float]], minimum: int) -> list[list[float]]:
    return [[float(value) for value in point[:minimum]] for point in points if _finite(point, minimum)]


def _xy(point: Sequence[float]) -> list[float]:
    return [float(point[0]), float(point[1])]


def _rz(point: Sequence[float]) -> list[float]:
    if len(point) >= 3:
        return [math.hypot(float(point[0]), float(point[1])), float(point[2])]
    return [float(point[0]), float(point[1])]


def _finite(point: Any, minimum: int) -> bool:
    return isinstance(point, Sequence) and len(point) >= minimum and all(
        isinstance(value, (int, float)) and math.isfinite(float(value)) for value in point[:minimum]
    )


def _downsample(points: Sequence[Sequence[float]], maximum: int) -> list[list[float]]:
    clean = [list(point) for point in points]
    if len(clean) <= maximum:
        return clean
    return [clean[round(index * (len(clean) - 1) / (maximum - 1))] for index in range(maximum)]


def _z_min(*paths: Sequence[Sequence[float]]) -> float:
    return min((float(point[1]) for path in paths for point in path), default=0.0)


def _z_max(*paths: Sequence[Sequence[float]]) -> float:
    return max((float(point[1]) for path in paths for point in path), default=1.0)
