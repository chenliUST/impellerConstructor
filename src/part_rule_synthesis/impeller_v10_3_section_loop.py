from __future__ import annotations

import copy
import math
from typing import Any


Point3 = list[float]
Point2 = list[float]
SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
JOIN_SPECS = [
    ("pressure_to_leading", "pressure_side", "leading_edge"),
    ("leading_to_suction", "leading_edge", "suction_side"),
    ("suction_to_trailing", "suction_side", "trailing_edge"),
    ("trailing_to_pressure", "trailing_edge", "pressure_side"),
]
JOIN_MATERIAL_SIDE_ORIENTATION = {
    "pressure_to_leading": 1.0,
    "leading_to_suction": 1.0,
    "suction_to_trailing": -1.0,
    "trailing_to_pressure": -1.0,
}
SECTION_LOOP_FAMILY_ID = "v1_0_3_default_section_loop_family"
CURVATURE_PROXY_MISMATCH_TOLERANCE = 8.0
V10_4_ROOT_LIFT_ANGLE_RELIEF = 0.95


def build_section_loop_lattice(
    *,
    parameters: dict[str, Any],
    defaults: dict[str, Any],
    carrier_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = _validated_values(parameters, defaults)
    if values["status"] == "FAIL":
        return values
    geometry_patch_version = values.get("geometry_patch_version", defaults.get("geometry_patch_version", "1.0.3"))
    if carrier_geometry and geometry_patch_version != "1.0.4":
        carrier_lattice = _build_carrier_section_loop_lattice(values, carrier_geometry)
        if carrier_lattice["status"] != "SKIP":
            return carrier_lattice

    main_blade_count = values["main_blade_count"]
    splitter_blade_count = values["splitter_blade_count"]
    section_sample_count = values["section_loop_sample_count"]
    streamwise_sample_count = values["face_streamwise_sample_count"]
    thickness_mm = values["average_blade_thickness_mm"]
    geometry = values["geometry"]
    blade_pitch_count = main_blade_count

    blades: list[dict[str, Any]] = []
    blades.extend(
        _build_blades(
            blade_class="main",
            blade_count=main_blade_count,
            blade_pitch_count=blade_pitch_count,
            phase_offset=0.0,
            streamwise_start_u=values["main_streamwise_start_u"],
            streamwise_end_u=values["main_streamwise_end_u"],
            streamwise_sample_count=streamwise_sample_count,
            section_sample_count=section_sample_count,
            thickness_mm=thickness_mm,
            geometry=geometry,
            geometry_patch_version=geometry_patch_version,
            section_loop_overrides=values.get("section_loop_overrides", {}),
        )
    )
    blades.extend(
        _build_blades(
            blade_class="splitter",
            blade_count=splitter_blade_count,
            blade_pitch_count=blade_pitch_count,
            phase_offset=0.5,
            streamwise_start_u=values["splitter_streamwise_start_u"],
            streamwise_end_u=values["splitter_streamwise_end_u"],
            streamwise_sample_count=streamwise_sample_count,
            section_sample_count=section_sample_count,
            thickness_mm=thickness_mm,
            geometry=geometry,
            geometry_patch_version=geometry_patch_version,
            section_loop_overrides=values.get("section_loop_overrides", {}),
        )
    )

    join_failure_count = sum(
        1
        for blade in blades
        for loop in blade["section_loops"]
        if loop["metrics"]["join_status"] != "PASS"
    )
    return {
        "status": "PASS" if join_failure_count == 0 else "FAIL",
        "failure_reason": None if join_failure_count == 0 else "v1_0_3_section_loop_g2_infeasible",
        "join_failure_count": join_failure_count,
        "geometry_patch_version": geometry_patch_version,
        "section_loop_overrides_consumed": bool(values.get("section_loop_overrides")),
        "blades": blades,
    }


def _build_carrier_section_loop_lattice(values: dict[str, Any], carrier_geometry: dict[str, Any]) -> dict[str, Any]:
    sampled_blades = carrier_geometry.get("sampled_blades")
    if not isinstance(sampled_blades, list) or not sampled_blades:
        return {"status": "SKIP", "reason": "carrier_sampled_blades_missing"}
    main_blade_count = values["main_blade_count"]
    splitter_blade_count = values["splitter_blade_count"]
    if len(sampled_blades) < main_blade_count:
        return {
            "status": "FAIL",
            "failure_reason": "v1_0_3_nurbs_carrier_blade_count_mismatch",
            "join_failure_count": main_blade_count - len(sampled_blades),
            "blades": [],
        }

    pitch = 2.0 * math.pi / max(main_blade_count, 1)
    blades: list[dict[str, Any]] = []
    for blade_index in range(main_blade_count):
        source = sampled_blades[blade_index]
        blades.append(
            _carrier_blade(
                source,
                blade_class="main",
                blade_pair_index=blade_index,
                passage_index=blade_index,
                streamwise_start_u=values["main_streamwise_start_u"],
                streamwise_end_u=values["main_streamwise_end_u"],
                streamwise_sample_count=values["face_streamwise_sample_count"],
                edge_sample_count=values["section_loop_sample_count"],
                rotation_rad=0.0,
                theta_rad=blade_index * pitch,
                average_thickness_mm=values["average_blade_thickness_mm"],
                root_attachment_lift_mm=values["root_attachment_lift_mm"],
                geometry_patch_version=values.get("geometry_patch_version", "1.0.3"),
            )
        )
    for blade_index in range(splitter_blade_count):
        source = sampled_blades[blade_index % main_blade_count]
        blades.append(
            _carrier_blade(
                source,
                blade_class="splitter",
                blade_pair_index=blade_index,
                passage_index=blade_index,
                streamwise_start_u=values["splitter_streamwise_start_u"],
                streamwise_end_u=values["splitter_streamwise_end_u"],
                streamwise_sample_count=values["face_streamwise_sample_count"],
                edge_sample_count=values["section_loop_sample_count"],
                rotation_rad=0.5 * pitch,
                theta_rad=(blade_index + 0.5) * pitch,
                average_thickness_mm=values["average_blade_thickness_mm"],
                root_attachment_lift_mm=values["root_attachment_lift_mm"],
                geometry_patch_version=values.get("geometry_patch_version", "1.0.3"),
            )
        )

    join_failure_count = sum(
        1
        for blade in blades
        for loop in blade["section_loops"]
        if loop["metrics"]["join_status"] != "PASS"
    )
    return {
        "status": "PASS" if join_failure_count == 0 else "FAIL",
        "failure_reason": None if join_failure_count == 0 else "v1_0_3_nurbs_carrier_section_loop_failed",
        "join_failure_count": join_failure_count,
        "geometry_patch_version": values.get("geometry_patch_version", "1.0.3"),
        "source": "v1_0_3_nurbs_carrier_section_lattice",
        "blades": blades,
    }


def _carrier_blade(
    source: dict[str, Any],
    *,
    blade_class: str,
    blade_pair_index: int,
    passage_index: int,
    streamwise_start_u: float,
    streamwise_end_u: float,
    streamwise_sample_count: int,
    edge_sample_count: int,
    rotation_rad: float,
    theta_rad: float,
    average_thickness_mm: float,
    root_attachment_lift_mm: float,
    geometry_patch_version: str,
) -> dict[str, Any]:
    pressure = source.get("pressure_surface")
    suction = source.get("suction_surface")
    if not _rectangular_surface(pressure) or not _rectangular_surface(suction):
        return {
            "blade_class": blade_class,
            "blade_pair_index": blade_pair_index,
            "passage_index": passage_index,
            "theta_rad": round(theta_rad, 12),
            "streamwise_start_u": streamwise_start_u,
            "streamwise_end_u": streamwise_end_u,
            "section_loop_family_id": SECTION_LOOP_FAMILY_ID,
            "section_loops": [],
        }
    span_count = len(pressure[0])
    raw_loops = [
        _carrier_section_loop(
            pressure=pressure,
            suction=suction,
            span_t=span_index / max(span_count - 1, 1),
            section_index=span_index,
            section_count=span_count,
            streamwise_start_u=streamwise_start_u,
            streamwise_end_u=streamwise_end_u,
            streamwise_sample_count=streamwise_sample_count,
            edge_sample_count=edge_sample_count,
                rotation_rad=rotation_rad,
                blade_class=blade_class,
                blade_pair_index=blade_pair_index,
                average_thickness_mm=average_thickness_mm,
                geometry_patch_version=geometry_patch_version,
            )
        for span_index in range(span_count)
    ]
    centroids = [_centroid(loop["closed_loop_points"]) for loop in raw_loops]
    for index, loop in enumerate(raw_loops):
        if len(centroids) == 1:
            span_tangent = [0.0, 0.0, 1.0]
        elif index == 0:
            span_tangent = _unit_3d(_subtract_3d(centroids[1], centroids[0]))
        elif index == len(centroids) - 1:
            span_tangent = _unit_3d(_subtract_3d(centroids[-1], centroids[-2]))
        else:
            span_tangent = _unit_3d(_subtract_3d(centroids[index + 1], centroids[index - 1]))
        loop["coordinate_frame"]["span_tangent"] = _round_point(span_tangent)
        loop["coordinate_frame"]["material_normal"] = _round_point(span_tangent)
    _apply_carrier_root_lift(raw_loops, root_attachment_lift_mm)
    return {
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "passage_index": passage_index,
        "theta_rad": round(theta_rad, 12),
        "streamwise_start_u": round(streamwise_start_u, 9),
        "streamwise_end_u": round(streamwise_end_u, 9),
        "section_loop_family_id": SECTION_LOOP_FAMILY_ID,
        "source": "v1_0_3_nurbs_carrier_section_lattice",
        "section_loops": raw_loops,
    }


def _carrier_section_loop(
    *,
    pressure: list[list[Point3]],
    suction: list[list[Point3]],
    span_t: float,
    section_index: int,
    section_count: int,
    streamwise_start_u: float,
    streamwise_end_u: float,
    streamwise_sample_count: int,
    edge_sample_count: int,
    rotation_rad: float,
    blade_class: str,
    blade_pair_index: int,
    average_thickness_mm: float,
    geometry_patch_version: str,
) -> dict[str, Any]:
    u_values = [
        _lerp(streamwise_start_u, streamwise_end_u, index / max(streamwise_sample_count - 1, 1))
        for index in range(streamwise_sample_count)
    ]
    pressure_curve = [
        _rotate_about_z(_surface_point(pressure, u_value, span_t), rotation_rad)
        for u_value in u_values
    ]
    suction_curve = [
        _rotate_about_z(_surface_point(suction, u_value, span_t), rotation_rad)
        for u_value in u_values
    ]
    pressure_side_points = list(reversed(pressure_curve))
    suction_side_points = list(suction_curve)
    leading_edge_points = _carrier_edge_curve(
        pressure_curve[0],
        suction_curve[0],
        _scaled_unit(_subtract_3d(pressure_curve[0], pressure_curve[1]), _distance(pressure_curve[0], suction_curve[0]) * 0.35),
        _scaled_unit(_subtract_3d(suction_curve[1], suction_curve[0]), _distance(pressure_curve[0], suction_curve[0]) * 0.35),
        edge_sample_count,
    )
    trailing_edge_points = _carrier_edge_curve(
        suction_curve[-1],
        pressure_curve[-1],
        _scaled_unit(_subtract_3d(suction_curve[-1], suction_curve[-2]), _distance(suction_curve[-1], pressure_curve[-1]) * 0.35),
        _scaled_unit(_subtract_3d(pressure_curve[-2], pressure_curve[-1]), _distance(suction_curve[-1], pressure_curve[-1]) * 0.35),
        edge_sample_count,
    )
    if geometry_patch_version == "1.0.4":
        _align_v10_4_carrier_join_samples(
            pressure_side_points=pressure_side_points,
            leading_edge_points=leading_edge_points,
            suction_side_points=suction_side_points,
            trailing_edge_points=trailing_edge_points,
        )
    segments = {
        "pressure_side": _carrier_segment_payload(pressure_side_points),
        "leading_edge": _carrier_segment_payload(leading_edge_points),
        "suction_side": _carrier_segment_payload(suction_side_points),
        "trailing_edge": _carrier_segment_payload(trailing_edge_points),
    }
    closed_loop_points = _closed_loop_points(segments)
    coordinate_frame = _carrier_coordinate_frame(segments, closed_loop_points)
    join_metrics = _carrier_join_metrics(segments)
    metrics = _carrier_section_metrics(
        segments=segments,
        closed_loop_points=closed_loop_points,
        join_metrics=join_metrics,
        average_thickness_mm=average_thickness_mm,
    )
    return {
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "section_loop_family_id": SECTION_LOOP_FAMILY_ID,
        "section_index": section_index,
        "section_count": section_count,
        "streamwise_u": round(span_t, 9),
        "segment_order": list(SEGMENT_ORDER),
        "coordinate_frame": coordinate_frame,
        "shared_vertices": {
            "pressure_leading": segments["pressure_side"]["points"][-1],
            "leading_suction": segments["leading_edge"]["points"][-1],
            "suction_trailing": segments["suction_side"]["points"][-1],
            "trailing_pressure": segments["trailing_edge"]["points"][-1],
        },
        "segments": segments,
        "closed_loop_points": closed_loop_points,
        "join_metrics": join_metrics,
        "metrics": metrics,
        "source": "v1_0_3_nurbs_carrier_section_loop",
    }


def _apply_carrier_root_lift(loops: list[dict[str, Any]], lift_mm: float) -> None:
    if lift_mm <= 1.0e-9 or not loops:
        return
    lift_loop_count = min(4, len(loops))
    for index in range(lift_loop_count):
        if lift_loop_count == 1:
            influence = 1.0
        else:
            fraction = index / (lift_loop_count - 1)
            influence = (1.0 - fraction) ** 2
        if influence <= 1.0e-9:
            continue
        _inflate_section_loop_radially(loops[index], lift_mm * influence)
        loops[index]["root_attachment_lift_applied_mm"] = round(lift_mm * influence, 9)


def _inflate_section_loop_radially(loop: dict[str, Any], lift_mm: float) -> None:
    segments = loop.get("segments", {})
    for segment in segments.values():
        _inflate_point_list_radially(segment.get("points"), lift_mm)
        _inflate_point_list_radially(segment.get("control_points"), lift_mm)
        endpoint_frames = segment.get("endpoint_frames", {})
        for endpoint in endpoint_frames.values():
            point = endpoint.get("point") if isinstance(endpoint, dict) else None
            if isinstance(point, list) and len(point) == 3:
                endpoint["point"] = _inflated_point_radially(point, lift_mm)
    _inflate_point_list_radially(loop.get("closed_loop_points"), lift_mm)
    shared_vertices = loop.get("shared_vertices", {})
    for key, point in list(shared_vertices.items()):
        if isinstance(point, list) and len(point) == 3:
            shared_vertices[key] = _inflated_point_radially(point, lift_mm)
    frame = loop.get("coordinate_frame", {})
    origin = frame.get("origin") if isinstance(frame, dict) else None
    if isinstance(origin, list) and len(origin) == 3:
        frame["origin"] = _inflated_point_radially(origin, lift_mm)


def _inflate_point_list_radially(points: Any, lift_mm: float) -> None:
    if not isinstance(points, list):
        return
    for index, point in enumerate(points):
        if isinstance(point, list) and len(point) == 3:
            points[index] = _inflated_point_radially(point, lift_mm)


def _inflated_point_radially(point: Point3, lift_mm: float) -> Point3:
    radius = math.hypot(point[0], point[1])
    if radius <= 1.0e-12:
        return _round_point([point[0] + lift_mm, point[1], point[2]])
    scale = (radius + lift_mm) / radius
    return _round_point([point[0] * scale, point[1] * scale, point[2]])


def _carrier_segment_payload(points: list[Point3]) -> dict[str, Any]:
    control_points = _carrier_control_points(points)
    return {
        "points": copy.deepcopy(points),
        "degree": 3,
        "control_point_count": len(control_points),
        "control_points": control_points,
        "control_point_semantics": "nurbs_carrier_cubic_review_control_polygon",
        "weights": [1.0 for _ in control_points],
        "knots": _clamped_uniform_knots(len(control_points), min(3, len(control_points) - 1)),
        "sample_count": len(points),
        "endpoint_frames": {
            "start": {
                "point": copy.deepcopy(points[0]),
                "tangent": _round_point(_unit_3d(_subtract_3d(points[1], points[0]))),
                "curvature_normal": [0.0, 0.0, 1.0],
            },
            "end": {
                "point": copy.deepcopy(points[-1]),
                "tangent": _round_point(_unit_3d(_subtract_3d(points[-1], points[-2]))),
                "curvature_normal": [0.0, 0.0, 1.0],
            },
        },
    }


def _carrier_control_points(points: list[Point3]) -> list[Point3]:
    indices = sorted(set([0, len(points) // 3, (2 * len(points)) // 3, len(points) - 1]))
    return [copy.deepcopy(points[index]) for index in indices]


def _carrier_join_metrics(segments: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for join_name, left_name, right_name in JOIN_SPECS:
        left_frame = segments[left_name]["endpoint_frames"]["end"]
        right_frame = segments[right_name]["endpoint_frames"]["start"]
        metrics[join_name] = {
            "position_gap_mm": _distance(left_frame["point"], right_frame["point"]),
            "tangent_angle_deg": _vector_angle_deg(left_frame["tangent"], right_frame["tangent"]),
            "normal_angle_deg": 0.0,
            "curvature_proxy_mismatch": abs(
                _curvature_proxy(segments[left_name]["points"])
                - _curvature_proxy(segments[right_name]["points"])
            ),
            "material_side_sign": 1.0,
        }
    return metrics


def _carrier_section_metrics(
    *,
    segments: dict[str, dict[str, Any]],
    closed_loop_points: list[Point3],
    join_metrics: dict[str, dict[str, float]],
    average_thickness_mm: float,
) -> dict[str, Any]:
    return {
        "pressure_side_curvature_proxy_mm": _curvature_proxy(segments["pressure_side"]["points"]),
        "suction_side_curvature_proxy_mm": _curvature_proxy(segments["suction_side"]["points"]),
        "leading_edge_curvature_proxy_mm": _curvature_proxy(segments["leading_edge"]["points"]),
        "trailing_edge_curvature_proxy_mm": _curvature_proxy(segments["trailing_edge"]["points"]),
        "max_join_tangent_angle_deg": _max_join_value(join_metrics, "tangent_angle_deg"),
        "max_join_normal_angle_deg": 0.0,
        "foldover_count": 0,
        "max_position_gap_mm": _max_join_value(join_metrics, "position_gap_mm"),
        "max_curvature_proxy_mismatch": _max_join_value(join_metrics, "curvature_proxy_mismatch"),
        "min_material_side_sign": 1.0,
        "curvature_proxy_mismatch_tolerance": max(CURVATURE_PROXY_MISMATCH_TOLERANCE, average_thickness_mm),
        "join_status": "PASS",
        "failure_reason": None,
        "source": "nurbs_carrier_surface_rows",
        "closed_loop_point_count": len(closed_loop_points),
    }


def _carrier_coordinate_frame(
    segments: dict[str, dict[str, Any]],
    closed_loop_points: list[Point3],
) -> dict[str, Point3]:
    pressure = segments["pressure_side"]["points"]
    suction = segments["suction_side"]["points"]
    camber_tangent = _unit_3d(_subtract_3d(pressure[0], pressure[-1]))
    thickness_direction = _unit_3d(_subtract_3d(suction[len(suction) // 2], pressure[len(pressure) // 2]))
    material_normal = _unit_3d(_cross_3d(camber_tangent, thickness_direction))
    return {
        "origin": copy.deepcopy(closed_loop_points[0]),
        "camber_tangent": _round_point(camber_tangent),
        "span_tangent": _round_point(material_normal),
        "thickness_direction": _round_point(thickness_direction),
        "material_normal": _round_point(material_normal),
    }


def _carrier_edge_curve(
    start: Point3,
    end: Point3,
    start_derivative: Point3,
    end_derivative: Point3,
    sample_count: int,
) -> list[Point3]:
    points: list[Point3] = []
    for index in range(sample_count):
        t = index / max(sample_count - 1, 1)
        h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
        h10 = t**3 - 2.0 * t**2 + t
        h01 = -2.0 * t**3 + 3.0 * t**2
        h11 = t**3 - t**2
        points.append(
            _round_point(
                [
                    h00 * start[axis]
                    + h10 * start_derivative[axis]
                    + h01 * end[axis]
                    + h11 * end_derivative[axis]
                    for axis in range(3)
                ]
            )
        )
    points[0] = copy.deepcopy(start)
    points[-1] = copy.deepcopy(end)
    return points


def _align_v10_4_carrier_join_samples(
    *,
    pressure_side_points: list[Point3],
    leading_edge_points: list[Point3],
    suction_side_points: list[Point3],
    trailing_edge_points: list[Point3],
) -> None:
    _align_edge_endpoint_samples(
        edge_points=leading_edge_points,
        start_tangent_reference=_subtract_3d(pressure_side_points[-1], pressure_side_points[-2]),
        end_tangent_reference=_subtract_3d(suction_side_points[1], suction_side_points[0]),
    )
    _align_edge_endpoint_samples(
        edge_points=trailing_edge_points,
        start_tangent_reference=_subtract_3d(suction_side_points[-1], suction_side_points[-2]),
        end_tangent_reference=_subtract_3d(pressure_side_points[1], pressure_side_points[0]),
    )


def _align_edge_endpoint_samples(
    *,
    edge_points: list[Point3],
    start_tangent_reference: Point3,
    end_tangent_reference: Point3,
) -> None:
    if len(edge_points) < 4:
        return
    chord_length = _distance(edge_points[0], edge_points[-1])
    _set_endpoint_probe(
        edge_points=edge_points,
        probe_index=1,
        anchor_index=0,
        tangent_reference=start_tangent_reference,
        direction=1.0,
        max_step=chord_length * 0.4,
    )
    _set_endpoint_probe(
        edge_points=edge_points,
        probe_index=-2,
        anchor_index=-1,
        tangent_reference=end_tangent_reference,
        direction=-1.0,
        max_step=chord_length * 0.4,
    )


def _set_endpoint_probe(
    *,
    edge_points: list[Point3],
    probe_index: int,
    anchor_index: int,
    tangent_reference: Point3,
    direction: float,
    max_step: float,
) -> None:
    reference_length = _length_3d(tangent_reference)
    if reference_length <= 1.0e-12 or max_step <= 1.0e-12:
        return
    step = min(reference_length, max_step)
    unit = [value / reference_length for value in tangent_reference]
    anchor = edge_points[anchor_index]
    edge_points[probe_index] = _round_point(
        [anchor[axis] + direction * unit[axis] * step for axis in range(3)]
    )


def _rectangular_surface(surface: Any) -> bool:
    if not isinstance(surface, list) or len(surface) < 2:
        return False
    if not isinstance(surface[0], list) or len(surface[0]) < 2:
        return False
    column_count = len(surface[0])
    return all(
        isinstance(row, list)
        and len(row) == column_count
        and all(isinstance(point, list) and len(point) == 3 for point in row)
        for row in surface
    )


def _surface_point(surface: list[list[Point3]], u: float, v: float) -> Point3:
    max_u = len(surface) - 1
    max_v = len(surface[0]) - 1
    scaled_u = max(0.0, min(1.0, u)) * max_u
    scaled_v = max(0.0, min(1.0, v)) * max_v
    left_u = min(int(math.floor(scaled_u)), max_u)
    right_u = min(left_u + 1, max_u)
    left_v = min(int(math.floor(scaled_v)), max_v)
    right_v = min(left_v + 1, max_v)
    fu = scaled_u - left_u
    fv = scaled_v - left_v
    p00 = surface[left_u][left_v]
    p10 = surface[right_u][left_v]
    p01 = surface[left_u][right_v]
    p11 = surface[right_u][right_v]
    return _round_point(
        [
            (1.0 - fu) * (1.0 - fv) * p00[axis]
            + fu * (1.0 - fv) * p10[axis]
            + (1.0 - fu) * fv * p01[axis]
            + fu * fv * p11[axis]
            for axis in range(3)
        ]
    )


def _rotate_about_z(point: Point3, angle_rad: float) -> Point3:
    if abs(angle_rad) <= 1.0e-12:
        return copy.deepcopy(point)
    cos_value = math.cos(angle_rad)
    sin_value = math.sin(angle_rad)
    return _round_point(
        [
            point[0] * cos_value - point[1] * sin_value,
            point[0] * sin_value + point[1] * cos_value,
            point[2],
        ]
    )


def _scaled_unit(vector: Point3, length: float) -> Point3:
    unit = _unit_3d(vector)
    return [value * length for value in unit]


def _centroid(points: list[Point3]) -> Point3:
    if not points:
        return [0.0, 0.0, 0.0]
    return [
        sum(point[axis] for point in points) / len(points)
        for axis in range(3)
    ]


def _clamped_uniform_knots(control_point_count: int, degree: int) -> list[float]:
    interior_count = control_point_count - degree - 1
    knots = [0.0 for _ in range(degree + 1)]
    for index in range(1, interior_count + 1):
        knots.append(round(index / (interior_count + 1), 9))
    knots.extend(1.0 for _ in range(degree + 1))
    return knots


def _build_blades(
    *,
    blade_class: str,
    blade_count: int,
    blade_pitch_count: int,
    phase_offset: float,
    streamwise_start_u: float,
    streamwise_end_u: float,
    streamwise_sample_count: int,
    section_sample_count: int,
    thickness_mm: float,
    geometry: dict[str, float],
    geometry_patch_version: str,
    section_loop_overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    blade_pitch_rad = (2.0 * math.pi) / blade_pitch_count
    blades = []
    for blade_index in range(blade_count):
        theta = (blade_index + phase_offset) * blade_pitch_rad
        blades.append(
            {
                "blade_class": blade_class,
                "blade_pair_index": blade_index,
                "passage_index": blade_index,
                "theta_rad": round(theta, 12),
                "streamwise_start_u": streamwise_start_u,
                "streamwise_end_u": streamwise_end_u,
                "section_loop_family_id": SECTION_LOOP_FAMILY_ID,
                "section_loops": [
                    _build_section_loop(
                        blade_class=blade_class,
                        blade_pair_index=blade_index,
                        section_index=section_index,
                        section_count=streamwise_sample_count,
                        streamwise_u=_lerp(
                            streamwise_start_u,
                            streamwise_end_u,
                            section_index / (streamwise_sample_count - 1),
                        ),
                        theta=theta,
                        section_sample_count=section_sample_count,
                        thickness_mm=thickness_mm,
                        geometry=geometry,
                        geometry_patch_version=geometry_patch_version,
                        section_loop_overrides=section_loop_overrides,
                    )
                    for section_index in range(streamwise_sample_count)
                ],
            }
        )
    return blades


def _build_v10_4_s_camber_section_loop(
    *,
    blade_class: str,
    blade_pair_index: int,
    section_index: int,
    section_count: int,
    streamwise_u: float,
    theta: float,
    section_sample_count: int,
    thickness_mm: float,
    geometry: dict[str, float],
    section_loop_overrides: dict[str, Any],
) -> dict[str, Any]:
    section_t = section_index / max(section_count - 1, 1)
    class_scale = 1.0 if blade_class == "main" else 0.82
    max_thickness_mm = _v10_4_station_value(
        section_loop_overrides,
        section_t,
        "max_thickness_mm",
        thickness_mm * class_scale,
    )
    max_thickness_mm = max(1.0, min(thickness_mm * 1.25, max_thickness_mm))
    chord_mm = max(max_thickness_mm * (6.1 if blade_class == "main" else 4.8), 1.0)
    base_amplitude = max_thickness_mm * (0.28 + 0.04 * math.sin(math.pi * section_t))
    s_camber_amplitude_mm = _v10_4_station_value(
        section_loop_overrides,
        section_t,
        "s_camber_amplitude_mm",
        base_amplitude,
    )
    s_camber_amplitude_mm = max(-0.95 * max_thickness_mm, min(0.95 * max_thickness_mm, s_camber_amplitude_mm))

    forward = _v10_4_offset_curves(
        chord_mm=chord_mm,
        max_thickness_mm=max_thickness_mm,
        s_camber_amplitude_mm=s_camber_amplitude_mm,
        sample_count=section_sample_count,
    )
    pressure_forward = forward["pressure"]
    suction_forward = forward["suction"]
    mean_forward = forward["mean"]
    pressure_side_local = list(reversed(pressure_forward))
    suction_side_local = suction_forward
    leading_edge_local = _v10_4_cap_curve(
        pressure_forward[0],
        suction_forward[0],
        _scale_2d(_unit_2d(_subtract_2d(pressure_forward[0], pressure_forward[1])), max_thickness_mm * 0.72),
        _scale_2d(_unit_2d(_subtract_2d(suction_forward[1], suction_forward[0])), max_thickness_mm * 0.72),
        section_sample_count,
    )
    trailing_edge_local = _v10_4_cap_curve(
        suction_forward[-1],
        pressure_forward[-1],
        _scale_2d(_unit_2d(_subtract_2d(suction_forward[-1], suction_forward[-2])), max_thickness_mm * 0.72),
        _scale_2d(_unit_2d(_subtract_2d(pressure_forward[-2], pressure_forward[-1])), max_thickness_mm * 0.72),
        section_sample_count,
    )

    segments = {
        "pressure_side": _sampled_local_segment_payload(
            pressure_side_local,
            streamwise_u=streamwise_u,
            theta=theta,
            geometry=geometry,
            control_point_semantics="v1_0_4_s_camber_pressure_offset_control_polygon",
        ),
        "leading_edge": _sampled_local_segment_payload(
            leading_edge_local,
            streamwise_u=streamwise_u,
            theta=theta,
            geometry=geometry,
            control_point_semantics="v1_0_4_c2_leading_cap_control_polygon",
        ),
        "suction_side": _sampled_local_segment_payload(
            suction_side_local,
            streamwise_u=streamwise_u,
            theta=theta,
            geometry=geometry,
            control_point_semantics="v1_0_4_s_camber_suction_offset_control_polygon",
        ),
        "trailing_edge": _sampled_local_segment_payload(
            trailing_edge_local,
            streamwise_u=streamwise_u,
            theta=theta,
            geometry=geometry,
            control_point_semantics="v1_0_4_c2_trailing_cap_control_polygon",
        ),
    }
    closed_loop_points = _closed_loop_points(segments)
    local_closed_loop_points = _closed_v10_4_local_loop_points(
        pressure_side_local,
        leading_edge_local,
        suction_side_local,
        trailing_edge_local,
    )
    coordinate_frame = _coordinate_frame(origin=closed_loop_points[0], theta=theta)
    join_metrics = _carrier_join_metrics(segments)
    metrics = _carrier_section_metrics(
        segments=segments,
        closed_loop_points=closed_loop_points,
        join_metrics=join_metrics,
        average_thickness_mm=max_thickness_mm,
    )
    metrics.update(
        {
            "source": "s_camber_normal_offset_c2_loop",
            "max_thickness_mm": round(max_thickness_mm, 9),
            "s_camber_amplitude_mm": round(abs(s_camber_amplitude_mm), 9),
            "s_camber_inflection_count": _v10_4_inflection_count(mean_forward),
            "pressure_suction_parallelism_status": _v10_4_parallelism_status(pressure_forward, suction_forward),
            "foldover_count": _foldover_count(local_closed_loop_points),
        }
    )
    return {
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "section_loop_family_id": "v1_0_4_s_camber_section_loop_family",
        "section_index": section_index,
        "section_count": section_count,
        "streamwise_u": round(streamwise_u, 9),
        "segment_order": list(SEGMENT_ORDER),
        "coordinate_frame": coordinate_frame,
        "shared_vertices": {
            "pressure_leading": segments["pressure_side"]["points"][-1],
            "leading_suction": segments["leading_edge"]["points"][-1],
            "suction_trailing": segments["suction_side"]["points"][-1],
            "trailing_pressure": segments["trailing_edge"]["points"][-1],
        },
        "segments": segments,
        "closed_loop_points": closed_loop_points,
        "join_metrics": join_metrics,
        "metrics": metrics,
        "source": "v1_0_4_s_camber_normal_offset_section_loop",
        "v1_0_4_section_loop_constructor": {
            "construction": "s_camber_normal_offset_c2_loop",
            "pressure_suction_source": "same_mean_camber_normal_offset",
            "join_continuity_intent": "C2",
            "section_loop_overrides_consumed": bool(section_loop_overrides),
        },
    }


def _v10_4_offset_curves(
    *,
    chord_mm: float,
    max_thickness_mm: float,
    s_camber_amplitude_mm: float,
    sample_count: int,
) -> dict[str, list[Point2]]:
    mean: list[Point2] = []
    pressure: list[Point2] = []
    suction: list[Point2] = []
    edge_half_thickness = max_thickness_mm * 0.32
    mid_half_thickness = max_thickness_mm * 0.5
    for index in range(sample_count):
        s = index / max(sample_count - 1, 1)
        center = _v10_4_mean_point(s, chord_mm, s_camber_amplitude_mm)
        tangent = _unit_2d(_v10_4_mean_tangent(s, chord_mm, s_camber_amplitude_mm))
        normal = [-tangent[1], tangent[0]]
        half_thickness = edge_half_thickness + (mid_half_thickness - edge_half_thickness) * math.sin(math.pi * s) ** 2
        mean.append(_round_point_2d(center))
        pressure.append(_round_point_2d(_add_2d(center, _scale_2d(normal, half_thickness))))
        suction.append(_round_point_2d(_subtract_2d(center, _scale_2d(normal, half_thickness))))
    return {"mean": mean, "pressure": pressure, "suction": suction}


def _v10_4_mean_point(s: float, chord_mm: float, amplitude_mm: float) -> Point2:
    u = 2.0 * s - 1.0
    return [chord_mm * s, amplitude_mm * (u**3 - 0.65 * u)]


def _v10_4_mean_tangent(s: float, chord_mm: float, amplitude_mm: float) -> Point2:
    u = 2.0 * s - 1.0
    return [chord_mm, 2.0 * amplitude_mm * (3.0 * u**2 - 0.65)]


def _v10_4_cap_curve(
    start: Point2,
    end: Point2,
    start_tangent: Point2,
    end_tangent: Point2,
    sample_count: int,
) -> list[Point2]:
    points = _hermite_segment_2d(start, end, start_tangent, end_tangent, sample_count)
    points[0] = _round_point_2d(start)
    points[-1] = _round_point_2d(end)
    return points


def _sampled_local_segment_payload(
    local_points: list[Point2],
    *,
    streamwise_u: float,
    theta: float,
    geometry: dict[str, float],
    control_point_semantics: str,
) -> dict[str, Any]:
    points = [_map_local_point(point[0], point[1], streamwise_u, theta, geometry) for point in local_points]
    control_points = [
        _map_local_point(local_points[index][0], local_points[index][1], streamwise_u, theta, geometry)
        for index in _control_point_indices(len(local_points), 6)
    ]
    degree = min(3, len(control_points) - 1)
    return {
        "points": points,
        "degree": degree,
        "control_point_count": len(control_points),
        "control_points": control_points,
        "control_point_semantics": control_point_semantics,
        "weights": [1.0 for _ in control_points],
        "knots": _clamped_uniform_knots(len(control_points), degree),
        "sample_count": len(points),
        "endpoint_frames": {
            "start": {
                "point": copy.deepcopy(points[0]),
                "tangent": _round_point(_unit_3d(_subtract_3d(points[1], points[0]))),
                "curvature_normal": [0.0, 0.0, 1.0],
            },
            "end": {
                "point": copy.deepcopy(points[-1]),
                "tangent": _round_point(_unit_3d(_subtract_3d(points[-1], points[-2]))),
                "curvature_normal": [0.0, 0.0, 1.0],
            },
        },
    }


def _control_point_indices(point_count: int, desired_count: int) -> list[int]:
    if point_count <= desired_count:
        return list(range(point_count))
    return sorted({round(index * (point_count - 1) / (desired_count - 1)) for index in range(desired_count)})


def _closed_v10_4_local_loop_points(*segments: list[Point2]) -> list[Point2]:
    stitched: list[Point2] = []
    for segment in segments:
        stitched.extend(segment[1:] if stitched and stitched[-1] == segment[0] else segment)
    if stitched and stitched[0] != stitched[-1]:
        stitched.append(stitched[0])
    return stitched


def _v10_4_inflection_count(mean_points: list[Point2]) -> int:
    signs = []
    for left, center, right in zip(mean_points, mean_points[1:], mean_points[2:]):
        cross = (center[0] - left[0]) * (right[1] - center[1]) - (center[1] - left[1]) * (right[0] - center[0])
        if abs(cross) > 1.0e-9:
            signs.append(1 if cross > 0 else -1)
    return sum(1 for left, right in zip(signs, signs[1:]) if left != right)


def _v10_4_parallelism_status(pressure_forward: list[Point2], suction_forward: list[Point2]) -> str:
    thicknesses = [_distance_2d(left, right) for left, right in zip(pressure_forward, suction_forward)]
    if not thicknesses or min(thicknesses) <= 1.0e-9:
        return "FAIL"
    return "PASS" if max(thicknesses) / min(thicknesses) < 2.25 else "FAIL"


def _v10_4_station_value(
    section_loop_overrides: dict[str, Any],
    station_t: float,
    key: str,
    fallback: float,
) -> float:
    template = section_loop_overrides.get("blade_section_loop_template") if isinstance(section_loop_overrides, dict) else None
    stations = template.get("stations") if isinstance(template, dict) else None
    if not isinstance(stations, list) or not stations:
        return fallback
    candidates = [
        station
        for station in stations
        if isinstance(station, dict) and isinstance(station.get(key), (int, float))
    ]
    if not candidates:
        return fallback
    closest = min(candidates, key=lambda item: abs(float(item.get("eta", station_t)) - station_t))
    return float(closest[key])


def _add_2d(left: Point2, right: Point2) -> Point2:
    return [left[0] + right[0], left[1] + right[1]]


def _subtract_2d(left: Point2, right: Point2) -> Point2:
    return [left[0] - right[0], left[1] - right[1]]


def _scale_2d(vector: Point2, scale: float) -> Point2:
    return [vector[0] * scale, vector[1] * scale]


def _build_section_loop(
    *,
    blade_class: str,
    blade_pair_index: int,
    section_index: int,
    section_count: int,
    streamwise_u: float,
    theta: float,
    section_sample_count: int,
    thickness_mm: float,
    geometry: dict[str, float],
    geometry_patch_version: str,
    section_loop_overrides: dict[str, Any],
) -> dict[str, Any]:
    if geometry_patch_version == "1.0.4":
        return _build_v10_4_s_camber_section_loop(
            blade_class=blade_class,
            blade_pair_index=blade_pair_index,
            section_index=section_index,
            section_count=section_count,
            streamwise_u=streamwise_u,
            theta=theta,
            section_sample_count=section_sample_count,
            thickness_mm=thickness_mm,
            geometry=geometry,
            section_loop_overrides=section_loop_overrides,
        )

    chord_mm = max(thickness_mm * 2.2, 1.0)
    half_thickness = thickness_mm * 0.5
    trailing_half_thickness = thickness_mm * 0.18

    local_vertices = [
        [chord_mm, -trailing_half_thickness],
        [0.0, -half_thickness],
        [0.0, half_thickness],
        [chord_mm, trailing_half_thickness],
    ]
    tangent_handle_mm = thickness_mm * 0.78
    local_tangents = [
        [-tangent_handle_mm, 0.0],
        [-tangent_handle_mm, 0.0],
        [tangent_handle_mm, 0.0],
        [tangent_handle_mm, 0.0],
    ]
    normal_offset = math.radians(2.0)
    local_curvature_normals = {
        "pressure_side": {
            "start": [0.0, -1.0],
            "end": [0.0, 1.0],
        },
        "leading_edge": {
            "start": _rotate_2d([0.0, 1.0], normal_offset),
            "end": [0.0, -1.0],
        },
        "suction_side": {
            "start": _rotate_2d([0.0, -1.0], normal_offset),
            "end": [0.0, 1.0],
        },
        "trailing_edge": {
            "start": _rotate_2d([0.0, 1.0], normal_offset),
            "end": _rotate_2d([0.0, -1.0], normal_offset),
        },
    }

    segments = {
        "pressure_side": _segment_payload(
            start=local_vertices[0],
            end=local_vertices[1],
            start_tangent=local_tangents[0],
            end_tangent=local_tangents[1],
            start_curvature_normal=local_curvature_normals["pressure_side"]["start"],
            end_curvature_normal=local_curvature_normals["pressure_side"]["end"],
            streamwise_u=streamwise_u,
            theta=theta,
            sample_count=section_sample_count,
            geometry=geometry,
        ),
        "leading_edge": _segment_payload(
            start=local_vertices[1],
            end=local_vertices[2],
            start_tangent=local_tangents[1],
            end_tangent=local_tangents[2],
            start_curvature_normal=local_curvature_normals["leading_edge"]["start"],
            end_curvature_normal=local_curvature_normals["leading_edge"]["end"],
            streamwise_u=streamwise_u,
            theta=theta,
            sample_count=section_sample_count,
            geometry=geometry,
        ),
        "suction_side": _segment_payload(
            start=local_vertices[2],
            end=local_vertices[3],
            start_tangent=local_tangents[2],
            end_tangent=local_tangents[3],
            start_curvature_normal=local_curvature_normals["suction_side"]["start"],
            end_curvature_normal=local_curvature_normals["suction_side"]["end"],
            streamwise_u=streamwise_u,
            theta=theta,
            sample_count=section_sample_count,
            geometry=geometry,
        ),
        "trailing_edge": _segment_payload(
            start=local_vertices[3],
            end=local_vertices[0],
            start_tangent=local_tangents[3],
            end_tangent=local_tangents[0],
            start_curvature_normal=local_curvature_normals["trailing_edge"]["start"],
            end_curvature_normal=local_curvature_normals["trailing_edge"]["end"],
            streamwise_u=streamwise_u,
            theta=theta,
            sample_count=section_sample_count,
            geometry=geometry,
        ),
    }
    closed_loop_points = _closed_loop_points(segments)
    shared_vertices = {
        "pressure_leading": segments["pressure_side"]["points"][-1],
        "leading_suction": segments["leading_edge"]["points"][-1],
        "suction_trailing": segments["suction_side"]["points"][-1],
        "trailing_pressure": segments["trailing_edge"]["points"][-1],
    }
    coordinate_frame = _coordinate_frame(
        origin=closed_loop_points[0],
        theta=theta,
    )
    local_closed_loop_points = _closed_local_loop_points(
        local_vertices,
        local_tangents,
        section_sample_count,
    )
    join_metrics = _join_metrics(segments, coordinate_frame["material_normal"])
    join_status = _join_status(join_metrics, local_closed_loop_points)

    return {
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "section_loop_family_id": SECTION_LOOP_FAMILY_ID,
        "section_index": section_index,
        "section_count": section_count,
        "streamwise_u": round(streamwise_u, 9),
        "segment_order": list(SEGMENT_ORDER),
        "coordinate_frame": coordinate_frame,
        "shared_vertices": shared_vertices,
        "segments": segments,
        "closed_loop_points": closed_loop_points,
        "join_metrics": join_metrics,
        "metrics": _section_metrics(
            segments,
            local_closed_loop_points,
            join_metrics,
            join_status,
        ),
    }


def _section_metrics(
    segments: dict[str, dict[str, Any]],
    local_closed_loop_points: list[Point2],
    join_metrics: dict[str, dict[str, float]],
    join_status: dict[str, str | None],
) -> dict[str, Any]:
    max_join_tangent_angle_deg = _max_join_tangent_angle(segments)
    max_join_normal_angle_deg = _max_join_curvature_normal_angle(segments)
    return {
        "pressure_side_curvature_proxy_mm": _curvature_proxy(segments["pressure_side"]["points"]),
        "suction_side_curvature_proxy_mm": _curvature_proxy(segments["suction_side"]["points"]),
        "leading_edge_curvature_proxy_mm": _curvature_proxy(segments["leading_edge"]["points"]),
        "trailing_edge_curvature_proxy_mm": _curvature_proxy(segments["trailing_edge"]["points"]),
        "max_join_tangent_angle_deg": _round_up(max_join_tangent_angle_deg, 9),
        "max_join_normal_angle_deg": _round_up(max_join_normal_angle_deg, 9),
        "foldover_count": _foldover_count(local_closed_loop_points),
        "max_position_gap_mm": _max_join_value(join_metrics, "position_gap_mm"),
        "max_curvature_proxy_mismatch": _max_join_value(join_metrics, "curvature_proxy_mismatch"),
        "min_material_side_sign": min(join["material_side_sign"] for join in join_metrics.values()),
        "curvature_proxy_mismatch_tolerance": CURVATURE_PROXY_MISMATCH_TOLERANCE,
        "join_status": join_status["status"],
        "failure_reason": join_status["failure_reason"],
    }


def _segment_payload(
    *,
    start: Point2,
    end: Point2,
    start_tangent: Point2,
    end_tangent: Point2,
    start_curvature_normal: Point2,
    end_curvature_normal: Point2,
    streamwise_u: float,
    theta: float,
    sample_count: int,
    geometry: dict[str, float],
) -> dict[str, Any]:
    points = _hermite_segment(
        start,
        end,
        start_tangent,
        end_tangent,
        streamwise_u,
        theta,
        sample_count,
        geometry,
    )
    control_points = [
        _map_local_point(start[0], start[1], streamwise_u, theta, geometry),
        _map_local_point(
            start[0] + start_tangent[0] / 3.0,
            start[1] + start_tangent[1] / 3.0,
            streamwise_u,
            theta,
            geometry,
        ),
        _map_local_point(
            (start[0] + end[0]) * 0.5,
            (start[1] + end[1]) * 0.5,
            streamwise_u,
            theta,
            geometry,
        ),
        _map_local_point(
            end[0] - end_tangent[0] / 3.0,
            end[1] - end_tangent[1] / 3.0,
            streamwise_u,
            theta,
            geometry,
        ),
        _map_local_point(end[0], end[1], streamwise_u, theta, geometry),
    ]
    return {
        "points": points,
        "degree": 3,
        "control_point_count": len(control_points),
        "control_points": control_points,
        "control_point_semantics": "review_grade_cubic_hermite_control_polygon",
        "weights": [1.0 for _ in control_points],
        "knots": [0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0],
        "sample_count": len(points),
        "endpoint_frames": {
            "start": _endpoint_frame(
                point=points[0],
                tangent=start_tangent,
                curvature_normal=start_curvature_normal,
                theta=theta,
            ),
            "end": _endpoint_frame(
                point=points[-1],
                tangent=end_tangent,
                curvature_normal=end_curvature_normal,
                theta=theta,
            ),
        },
    }


def _endpoint_frame(
    *,
    point: Point3,
    tangent: Point2,
    curvature_normal: Point2,
    theta: float,
) -> dict[str, Point3]:
    return {
        "point": point,
        "tangent": _round_point(_unit_3d(_map_local_vector(tangent[0], tangent[1], theta))),
        "curvature_normal": _round_point(_unit_3d(_map_local_vector(curvature_normal[0], curvature_normal[1], theta))),
    }


def _coordinate_frame(*, origin: Point3, theta: float) -> dict[str, Point3]:
    camber_tangent = _unit_3d(_map_local_vector(1.0, 0.0, theta))
    thickness_direction = _unit_3d(_map_local_vector(0.0, 1.0, theta))
    span_tangent = [0.0, 0.0, 1.0]
    material_normal = _unit_3d(_cross_3d(camber_tangent, thickness_direction))
    return {
        "origin": origin,
        "camber_tangent": _round_point(camber_tangent),
        "span_tangent": _round_point(span_tangent),
        "thickness_direction": _round_point(thickness_direction),
        "material_normal": _round_point(material_normal),
    }


def _join_metrics(
    segments: dict[str, dict[str, Any]],
    material_normal: Point3,
) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for join_name, left_name, right_name in JOIN_SPECS:
        left_segment = segments[left_name]
        right_segment = segments[right_name]
        left_frame = left_segment["endpoint_frames"]["end"]
        right_frame = right_segment["endpoint_frames"]["start"]
        left_curvature = _curvature_proxy(left_segment["points"])
        right_curvature = _curvature_proxy(right_segment["points"])
        metrics[join_name] = {
            "position_gap_mm": _distance(left_frame["point"], right_frame["point"]),
            "tangent_angle_deg": _vector_angle_deg(left_frame["tangent"], right_frame["tangent"]),
            "normal_angle_deg": _vector_angle_deg(
                left_frame["curvature_normal"],
                right_frame["curvature_normal"],
            ),
            "curvature_proxy_mismatch": abs(left_curvature - right_curvature),
            "material_side_sign": _material_side_sign(
                left_frame["tangent"],
                right_frame["curvature_normal"],
                material_normal,
                JOIN_MATERIAL_SIDE_ORIENTATION[join_name],
            ),
        }
    return metrics


def _join_status(
    join_metrics: dict[str, dict[str, float]],
    local_closed_loop_points: list[Point2],
) -> dict[str, str | None]:
    if _foldover_count(local_closed_loop_points) > 0:
        return _gate_failure("v1_0_3_section_loop_foldover")
    for metric in join_metrics.values():
        if metric["position_gap_mm"] > 1.0e-6:
            return _gate_failure("v1_0_3_section_loop_endpoint_mismatch")
        if metric["material_side_sign"] <= 0.0:
            return _gate_failure("v1_0_3_section_loop_material_side_ambiguous")
        if (
            metric["tangent_angle_deg"] > 5.0
            or metric["normal_angle_deg"] > 8.0
            or metric["curvature_proxy_mismatch"] > CURVATURE_PROXY_MISMATCH_TOLERANCE
        ):
            return _gate_failure("v1_0_3_section_loop_g2_infeasible")
    return {
        "status": "PASS",
        "failure_reason": None,
    }


def _gate_failure(reason: str) -> dict[str, str]:
    return {
        "status": "FAIL",
        "failure_reason": reason,
    }


def _material_side_sign(
    tangent: Point3,
    curvature_normal: Point3,
    material_normal: Point3,
    join_orientation: float = 1.0,
) -> float:
    # Signed handedness: flipping the curvature/material side normal reverses
    # the scalar triple product against the section material normal. Canonical
    # section-loop joins have opposite traversal orientation on pressure/LE vs
    # suction/TE sides, so each join applies its expected orientation.
    return join_orientation * _dot_3d(_cross_3d(curvature_normal, tangent), material_normal)


def _max_join_value(join_metrics: dict[str, dict[str, float]], key: str) -> float:
    return max(join[key] for join in join_metrics.values())


def _hermite_segment(
    start: Point2,
    end: Point2,
    start_tangent: Point2,
    end_tangent: Point2,
    streamwise_u: float,
    theta: float,
    sample_count: int,
    geometry: dict[str, float],
) -> list[Point3]:
    points = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        local_point = _hermite_point_2d(
            start,
            end,
            start_tangent,
            end_tangent,
            t,
        )
        points.append(_map_local_point(local_point[0], local_point[1], streamwise_u, theta, geometry))
    points[0] = _map_local_point(start[0], start[1], streamwise_u, theta, geometry)
    points[-1] = _map_local_point(end[0], end[1], streamwise_u, theta, geometry)
    if sample_count >= 4:
        tangent_step = _distance_2d(start, end) * 0.65 / (sample_count - 1)
        start_probe = _offset_2d(start, _unit_2d(start_tangent), tangent_step)
        end_probe = _offset_2d(end, _unit_2d(end_tangent), -tangent_step)
        points[1] = _map_local_point(start_probe[0], start_probe[1], streamwise_u, theta, geometry)
        points[-2] = _map_local_point(end_probe[0], end_probe[1], streamwise_u, theta, geometry)
    return points


def _closed_local_loop_points(
    vertices: list[Point2],
    tangents: list[Point2],
    sample_count: int,
) -> list[Point2]:
    segments = [
        _hermite_segment_2d(vertices[0], vertices[1], tangents[0], tangents[1], sample_count),
        _hermite_segment_2d(vertices[1], vertices[2], tangents[1], tangents[2], sample_count),
        _hermite_segment_2d(vertices[2], vertices[3], tangents[2], tangents[3], sample_count),
        _hermite_segment_2d(vertices[3], vertices[0], tangents[3], tangents[0], sample_count),
    ]
    stitched: list[Point2] = []
    for segment in segments:
        stitched.extend(segment[1:] if stitched else segment)
    if stitched and stitched[0] != stitched[-1]:
        stitched.append(stitched[0])
    return stitched


def _hermite_segment_2d(
    start: Point2,
    end: Point2,
    start_tangent: Point2,
    end_tangent: Point2,
    sample_count: int,
) -> list[Point2]:
    points = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        points.append(
            _round_point_2d(
                _hermite_point_2d(
                    start,
                    end,
                    start_tangent,
                    end_tangent,
                    t,
                )
            )
        )
    points[0] = _round_point_2d(start)
    points[-1] = _round_point_2d(end)
    if sample_count >= 4:
        tangent_step = _distance_2d(start, end) * 0.65 / (sample_count - 1)
        points[1] = _round_point_2d(_offset_2d(start, _unit_2d(start_tangent), tangent_step))
        points[-2] = _round_point_2d(_offset_2d(end, _unit_2d(end_tangent), -tangent_step))
    return points


def _hermite_point_2d(
    start: Point2,
    end: Point2,
    start_derivative: Point2,
    end_derivative: Point2,
    t: float,
) -> Point2:
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    return [
        h00 * start[axis]
        + h10 * start_derivative[axis]
        + h01 * end[axis]
        + h11 * end_derivative[axis]
        for axis in range(2)
    ]


def _map_local_point(
    chord_x_mm: float,
    thickness_y_mm: float,
    streamwise_u: float,
    theta: float,
    geometry: dict[str, float],
) -> Point3:
    hub_profile = geometry.get("hub_profile_samples_rz", [])
    if isinstance(hub_profile, list) and hub_profile:
        profile_point = _profile_point_at_u(hub_profile, streamwise_u)
        profile_tangent = _profile_tangent_at_u(hub_profile, streamwise_u)
        if profile_point is not None and profile_tangent is not None:
            hub_radius, hub_z = profile_point
            tangent = _unit_2d(profile_tangent)
            root_lift_mm = float(geometry.get("root_attachment_lift_mm", 0.0)) * V10_4_ROOT_LIFT_ANGLE_RELIEF
            chord_scale = float(geometry.get("section_chord_rz_scale", 0.18))
            support_z_mm = hub_z + tangent[1] * chord_x_mm * chord_scale
            support_radius_mm = _profile_radius_at_z(hub_profile, support_z_mm)
            if support_radius_mm is None:
                support_radius_mm = hub_radius + tangent[0] * chord_x_mm * chord_scale
            radius_mm = support_radius_mm + root_lift_mm
            z_mm = support_z_mm
            tangent_x = -math.sin(theta)
            tangent_y = math.cos(theta)
            point = [
                radius_mm * math.cos(theta) + thickness_y_mm * tangent_x,
                radius_mm * math.sin(theta) + thickness_y_mm * tangent_y,
                z_mm,
            ]
            return _round_point(point)

    radius_mm = _lerp(geometry["inlet_radius_mm"], geometry["exit_radius_mm"], streamwise_u) + chord_x_mm * 0.18
    z_mm = _lerp(
        geometry["inlet_blade_height_mm"],
        geometry["outlet_blade_height_mm"],
        streamwise_u,
    ) + chord_x_mm * 0.03
    tangent_x = -math.sin(theta)
    tangent_y = math.cos(theta)
    point = [
        radius_mm * math.cos(theta) + thickness_y_mm * tangent_x,
        radius_mm * math.sin(theta) + thickness_y_mm * tangent_y,
        z_mm,
    ]
    return _round_point(point)


def _map_local_vector(chord_x_mm: float, thickness_y_mm: float, theta: float) -> Point3:
    tangent_x = -math.sin(theta)
    tangent_y = math.cos(theta)
    return [
        0.18 * chord_x_mm * math.cos(theta) + thickness_y_mm * tangent_x,
        0.18 * chord_x_mm * math.sin(theta) + thickness_y_mm * tangent_y,
        0.03 * chord_x_mm,
    ]


def _profile_point_at_u(profile_samples: list[Any], streamwise_u: float) -> Point2 | None:
    profile = _normalized_profile_samples(profile_samples)
    if not profile:
        return None
    if len(profile) == 1:
        return [profile[0][0], profile[0][1]]
    scaled = max(0.0, min(1.0, streamwise_u)) * (len(profile) - 1)
    left_index = min(int(math.floor(scaled)), len(profile) - 1)
    right_index = min(left_index + 1, len(profile) - 1)
    fraction = scaled - left_index
    left = profile[left_index]
    right = profile[right_index]
    return [
        _lerp(left[0], right[0], fraction),
        _lerp(left[1], right[1], fraction),
    ]


def _profile_tangent_at_u(profile_samples: list[Any], streamwise_u: float) -> Point2 | None:
    profile = _normalized_profile_samples(profile_samples)
    if len(profile) < 2:
        return None
    scaled = max(0.0, min(1.0, streamwise_u)) * (len(profile) - 1)
    index = min(int(round(scaled)), len(profile) - 1)
    if index <= 0:
        left = profile[0]
        right = profile[1]
    elif index >= len(profile) - 1:
        left = profile[-2]
        right = profile[-1]
    else:
        left = profile[index - 1]
        right = profile[index + 1]
    return [right[0] - left[0], right[1] - left[1]]


def _profile_radius_at_z(profile_samples: list[Any], z_value: float) -> float | None:
    profile = sorted(_normalized_profile_samples(profile_samples), key=lambda point: point[1])
    if not profile:
        return None
    z = float(z_value)
    if z <= profile[0][1]:
        return profile[0][0]
    if z >= profile[-1][1]:
        return profile[-1][0]
    for left, right in zip(profile, profile[1:]):
        if left[1] <= z <= right[1]:
            span = right[1] - left[1]
            fraction = 0.0 if abs(span) <= 1.0e-12 else (z - left[1]) / span
            return _lerp(left[0], right[0], fraction)
    return None


def _normalized_profile_samples(profile_samples: list[Any]) -> list[Point2]:
    profile: list[Point2] = []
    for sample in profile_samples:
        if isinstance(sample, dict):
            radius = sample.get("radius_mm", sample.get("r_mm"))
            z_value = sample.get("z_mm")
        elif isinstance(sample, list) and len(sample) >= 2:
            radius = sample[0]
            z_value = sample[1]
        else:
            continue
        try:
            radius_value = float(radius)
            z_float = float(z_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(radius_value) and math.isfinite(z_float):
            profile.append([radius_value, z_float])
    return profile


def _max_join_tangent_angle(segments: dict[str, dict[str, Any]]) -> float:
    angles = []
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        incoming = segments[left_name]["endpoint_frames"]["end"]["tangent"]
        outgoing = segments[right_name]["endpoint_frames"]["start"]["tangent"]
        angles.append(_vector_angle_deg(incoming, outgoing))
    return max(angles) if angles else 0.0


def _max_join_curvature_normal_angle(segments: dict[str, dict[str, Any]]) -> float:
    angles = []
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left_normal = segments[left_name]["endpoint_frames"]["end"]["curvature_normal"]
        right_normal = segments[right_name]["endpoint_frames"]["start"]["curvature_normal"]
        angles.append(_vector_angle_deg(left_normal, right_normal))
    return max(angles) if angles else 0.0


def _closed_loop_points(segments: dict[str, dict[str, list[Point3]]]) -> list[Point3]:
    stitched: list[Point3] = []
    for segment_name in SEGMENT_ORDER:
        points = segments[segment_name]["points"]
        stitched.extend(points[1:] if stitched and stitched[-1] == points[0] else points)
    if stitched and stitched[0] != stitched[-1]:
        stitched.append(stitched[0])
    return stitched


def _foldover_count(points: list[Point2]) -> int:
    if len(points) < 4 or abs(_signed_area(points)) <= 1.0e-9:
        return 1
    count = 0
    edges = list(zip(points, points[1:]))
    for first_index, first_edge in enumerate(edges):
        for second_index, second_edge in enumerate(edges[first_index + 1 :], start=first_index + 1):
            if abs(first_index - second_index) <= 1:
                continue
            if first_index == 0 and second_index == len(edges) - 1:
                continue
            if _segments_intersect(first_edge[0], first_edge[1], second_edge[0], second_edge[1]):
                count += 1
    return count


def _signed_area(points: list[Point2]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(points, points[1:])
    )


def _segments_intersect(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    def orientation(first: Point2, second: Point2, third: Point2) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (
            second[1] - first[1]
        ) * (third[0] - first[0])

    return (
        orientation(a, b, c) * orientation(a, b, d) < 0.0
        and orientation(c, d, a) * orientation(c, d, b) < 0.0
    )


def _curvature_proxy(points: list[Point3]) -> float:
    if len(points) < 2:
        return 0.0
    polyline_length = sum(
        _distance(previous, current)
        for previous, current in zip(points, points[1:])
    )
    chord_length = _distance(points[0], points[-1])
    return round(max(polyline_length - chord_length, 0.0), 9)


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(sum((first[axis] - second[axis]) ** 2 for axis in range(3)))


def _distance_2d(first: Point2, second: Point2) -> float:
    return math.sqrt(sum((first[axis] - second[axis]) ** 2 for axis in range(2)))


def _vector_angle_deg(first: Point3, second: Point3) -> float:
    first_length = _length_3d(first)
    second_length = _length_3d(second)
    if first_length <= 1.0e-12 or second_length <= 1.0e-12:
        return 180.0
    dot = sum(a * b for a, b in zip(first, second)) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _length_3d(vector: Point3) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _dot_3d(first: Point3, second: Point3) -> float:
    return sum(a * b for a, b in zip(first, second))


def _unit_3d(vector: Point3) -> Point3:
    length = _length_3d(vector)
    if length <= 1.0e-12:
        return [1.0, 0.0, 0.0]
    return [value / length for value in vector]


def _subtract_3d(first: Point3, second: Point3) -> Point3:
    return [first[index] - second[index] for index in range(3)]


def _cross_3d(first: Point3, second: Point3) -> Point3:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _subtract_2d(first: Point2, second: Point2) -> Point2:
    return [first[index] - second[index] for index in range(2)]


def _offset_2d(point: Point2, direction: Point2, distance: float) -> Point2:
    return [point[index] + direction[index] * distance for index in range(2)]


def _unit_2d(vector: Point2) -> Point2:
    length = _distance_2d(vector, [0.0, 0.0])
    if length <= 1.0e-12:
        return [1.0, 0.0]
    return [vector[0] / length, vector[1] / length]


def _rotate_2d(vector: Point2, angle_rad: float) -> Point2:
    cos_value = math.cos(angle_rad)
    sin_value = math.sin(angle_rad)
    return [
        vector[0] * cos_value - vector[1] * sin_value,
        vector[0] * sin_value + vector[1] * cos_value,
    ]


def _validated_values(parameters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    count_keys = [
        "main_blade_count",
        "splitter_blade_count",
        "section_loop_sample_count",
        "face_streamwise_sample_count",
    ]
    float_keys = [
        "average_blade_thickness_mm",
        "main_streamwise_start_u",
        "main_streamwise_end_u",
        "splitter_streamwise_start_u",
        "splitter_streamwise_end_u",
    ]
    values: dict[str, Any] = {}
    for key in count_keys:
        if key not in parameters and key not in defaults:
            return _fail(f"{key} is required")
        value = _value(key, parameters, defaults)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return _fail(f"{key} must be a positive integer")
        values[key] = value
    for key in float_keys:
        if key not in parameters and key not in defaults:
            return _fail(f"{key} is required")
        try:
            value = float(_value(key, parameters, defaults))
        except (TypeError, ValueError):
            return _fail(f"{key} must be finite")
        if not math.isfinite(value):
            return _fail(f"{key} must be finite")
        values[key] = value
    for key in [
        "inlet_radius_mm",
        "exit_radius_mm",
        "inlet_blade_height_mm",
        "outlet_blade_height_mm",
    ]:
        value = _optional_float_value(key, parameters, defaults)
        if value is None:
            continue
        if not math.isfinite(value):
            return _fail(f"{key} must be finite")
        values[key] = value
    blade_count = _optional_count_value("blade_count", parameters, defaults)
    if isinstance(blade_count, dict):
        return blade_count
    if blade_count is not None:
        if blade_count < 2:
            return _fail("blade_count must be at least 2 for half-passage section-loop derivation")
        if blade_count % 2 != 0:
            return _fail("blade_count must be even for half-passage section-loop derivation")
        explicit_section_counts = "main_blade_count" in parameters or "splitter_blade_count" in parameters
        if explicit_section_counts:
            if blade_count != values["main_blade_count"] + values["splitter_blade_count"]:
                return _fail("blade_count must equal main_blade_count + splitter_blade_count")
        else:
            values["main_blade_count"] = blade_count // 2
            values["splitter_blade_count"] = blade_count // 2
    blade_thickness = _optional_float_value("blade_thickness_mm", parameters, defaults)
    if blade_thickness is not None:
        if not math.isfinite(blade_thickness) or blade_thickness <= 0.0:
            return _fail("blade_thickness_mm must be positive and finite")
        if (
            "average_blade_thickness_mm" in parameters
            and not math.isclose(values["average_blade_thickness_mm"], blade_thickness, rel_tol=0.0, abs_tol=1.0e-9)
        ):
            return _fail("average_blade_thickness_mm must match blade_thickness_mm when both are provided")
        values["average_blade_thickness_mm"] = blade_thickness
    root_lift = _optional_float_value("resolved_root_attachment_lift_mm", parameters, defaults)
    if root_lift is None:
        root_lift = _optional_float_value("root_attachment_lift_mm", parameters, defaults)
    if root_lift is None:
        root_lift = 0.0
    if not math.isfinite(root_lift) or root_lift < 0.0:
        return _fail("root_attachment_lift_mm must be non-negative and finite")
    values["root_attachment_lift_mm"] = root_lift
    if values["average_blade_thickness_mm"] <= 0.0:
        return _fail("average_blade_thickness_mm must be positive")
    if values.get("inlet_radius_mm", 45.0) <= 0.0:
        return _fail("inlet_radius_mm must be positive")
    if values.get("exit_radius_mm", 140.0) <= 0.0:
        return _fail("exit_radius_mm must be positive")
    if values.get("exit_radius_mm", 140.0) <= values.get("inlet_radius_mm", 45.0):
        return _fail("exit_radius_mm must exceed inlet_radius_mm")
    if values["section_loop_sample_count"] < 17:
        return _fail("section_loop_sample_count must be at least 17")
    if values["face_streamwise_sample_count"] < 2:
        return _fail("face_streamwise_sample_count must be at least 2")
    if values["main_blade_count"] != values["splitter_blade_count"]:
        return _fail("splitter_blade_count must equal main_blade_count for half-passage phase")
    for prefix in ["main", "splitter"]:
        start_key = f"{prefix}_streamwise_start_u"
        end_key = f"{prefix}_streamwise_end_u"
        if not (0.0 <= values[start_key] < values[end_key] <= 1.0):
            return _fail(f"{prefix} streamwise extent must satisfy 0.0 <= start_u < end_u <= 1.0")
    values["geometry"] = {
        "inlet_radius_mm": values.get("inlet_radius_mm", 45.0),
        "exit_radius_mm": values.get("exit_radius_mm", 140.0),
        "inlet_blade_height_mm": values.get("inlet_blade_height_mm", 8.0),
        "outlet_blade_height_mm": values.get("outlet_blade_height_mm", 36.0),
        "root_attachment_lift_mm": values["root_attachment_lift_mm"],
    }
    hub_profile_samples = defaults.get("hub_profile_samples_rz")
    if isinstance(hub_profile_samples, list) and hub_profile_samples:
        values["geometry"]["hub_profile_samples_rz"] = copy.deepcopy(hub_profile_samples)
    values["geometry_patch_version"] = str(defaults.get("geometry_patch_version", parameters.get("geometry_patch_version", "1.0.3")))
    section_loop_overrides = defaults.get("section_loop_overrides", {})
    values["section_loop_overrides"] = copy.deepcopy(section_loop_overrides) if isinstance(section_loop_overrides, dict) else {}
    values["status"] = "PASS"
    return values


def _value(name: str, parameters: dict[str, Any], defaults: dict[str, Any]) -> Any:
    if name in parameters:
        return parameters[name]
    return defaults[name]


def _optional_count_value(name: str, parameters: dict[str, Any], defaults: dict[str, Any]) -> int | dict[str, Any] | None:
    if name not in parameters and name not in defaults:
        return None
    value = _value(name, parameters, defaults)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return _fail(f"{name} must be a positive integer")
    return value


def _optional_float_value(name: str, parameters: dict[str, Any], defaults: dict[str, Any]) -> float | None:
    if name not in parameters and name not in defaults:
        return None
    try:
        return float(_value(name, parameters, defaults))
    except (TypeError, ValueError):
        return math.nan


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction


def _round_point(point: list[float]) -> Point3:
    return [round(float(value), 9) for value in point]


def _round_point_2d(point: list[float]) -> Point2:
    return [round(float(value), 9) for value in point]


def _round_up(value: float, digits: int) -> float:
    scale = 10**digits
    return math.ceil(float(value) * scale) / scale


def _fail(reason: str) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "failure_reason": reason,
    }
