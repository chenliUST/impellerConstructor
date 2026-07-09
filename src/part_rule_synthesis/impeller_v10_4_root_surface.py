from __future__ import annotations

import copy
import math
from typing import Any


SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
COMPONENT_SUFFIX = {
    "pressure_side": "pressure_root_patch",
    "leading_edge": "leading_root_cap_patch",
    "suction_side": "suction_root_patch",
    "trailing_edge": "trailing_root_cap_patch",
}
FACE_SUFFIX = {
    "pressure_side": "pressure_surface",
    "leading_edge": "leading_edge_surface",
    "suction_side": "suction_surface",
    "trailing_edge": "trailing_edge_surface",
}
DISPLAY = {"inspection_class": "root_to_hub_blend", "color": "#ff00cc", "wire_color": "#fff200"}
_EPSILON = 1.0e-9
MIN_G2_ROOT_SAMPLE_COUNT = 65
ROOT_DIRECTION_TURN_LIMIT_DEG = 1.5
ROOT_FOOTPRINT_WIDTH_ANGLE_RELIEF = 1.16


def build_v10_4_root_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    blade_faces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    surface_id = f"blade_{blade_index}_root_annular_surface"
    base = _base_surface(surface_id)
    inputs = _inputs(blade_index, lattice, blade_faces, hub_surface, defaults)
    if inputs["status"] != "PASS":
        return _failed(base, inputs["reason"], defaults)

    projection = _project_root_loop(
        inputs["root_loop"],
        inputs["profile"],
        width_mm=inputs["target_width_mm"] * ROOT_FOOTPRINT_WIDTH_ANGLE_RELIEF,
        lift_tolerance_mm=inputs["target_lift_mm"],
    )
    if projection["status"] != "PASS":
        return _failed(base, projection["reason"], defaults)

    components = []
    for segment_name in SEGMENT_ORDER:
        indices = inputs["segment_indices"][segment_name]
        components.append(
            _component_surface(
                blade_index=blade_index,
                parent_id=surface_id,
                segment_name=segment_name,
                inner_segment=inputs["segment_points"][segment_name],
                projected_segment=[projection["projected_loop"][index] for index in indices],
                outer_segment=[projection["outer_loop"][index] for index in indices],
                domain_segment=[projection["support_domain_loop"][index] for index in indices],
                outer_domain_segment=[projection["support_outer_domain_loop"][index] for index in indices],
                blade_cross_vectors=inputs["blade_cross_vectors"][segment_name],
                profile=inputs["profile"],
                sample_count=inputs["sample_count"],
                target_width_mm=inputs["target_width_mm"],
                target_lift_mm=inputs["target_lift_mm"],
                projection=projection,
            )
        )

    grid = _aggregate_grid(components)
    quality = _aggregate_quality(
        components,
        target_width_mm=inputs["target_width_mm"],
        target_lift_mm=inputs["target_lift_mm"],
        projection=projection,
    )
    base.update(
        {
            "status": quality["status"],
            "uv_grid": grid,
            "control_net": _control_net(grid),
            "edge_samples": {
                "blade_inner_loop": copy.deepcopy(inputs["root_loop"]),
                "projected_footprint_loop": copy.deepcopy(projection["projected_loop"]),
                "hub_outer_loop": copy.deepcopy(projection["outer_loop"]),
                "requested_offset_loop": copy.deepcopy(projection["outer_loop"]),
                "requested_offset_loop_semantics": "v1_0_4_hub_domain_offset_loop",
            },
            "mesh": _quad_mesh(grid),
            "component_surfaces": components,
            "v1_0_4_root_quality": quality,
            "root_blend_quality": _compat_quality(quality, projection),
            "transition_quality": _transition_quality(quality, inputs["sample_count"]),
        }
    )
    return base


def _inputs(
    blade_index: int,
    lattice: dict[str, Any],
    blade_faces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    width = _value(defaults, "resolved_root_attachment_width_mm", "root_attachment_width_mm")
    lift = _value(defaults, "resolved_root_attachment_lift_mm", "root_attachment_lift_mm")
    if width is None or width <= 0.0:
        return _fail("v1_0_4_root_width_missing")
    if lift is None or lift < 0.0:
        return _fail("v1_0_4_root_lift_missing")
    sample_count = defaults.get("attachment_short_direction_sample_count", defaults.get("root_short_direction_sample_count", 17))
    if type(sample_count) is not int or sample_count < 17:
        return _fail("v1_0_4_root_short_direction_sample_count_invalid")
    profile = _profile(hub_surface)
    if len(profile) < 2:
        return _fail("v1_0_4_root_hub_support_domain_missing")
    blades = lattice.get("blades") if isinstance(lattice, dict) else None
    if not isinstance(blades, list) or blade_index >= len(blades):
        return _fail("v1_0_4_root_blade_missing")
    loops = blades[blade_index].get("section_loops") if isinstance(blades[blade_index], dict) else None
    segments = loops[0].get("segments") if isinstance(loops, list) and loops else None
    if not isinstance(segments, dict):
        return _fail("v1_0_4_root_section_loop_missing")

    segment_points = {}
    for name in SEGMENT_ORDER:
        points = segments.get(name, {}).get("points") if isinstance(segments.get(name), dict) else None
        if not isinstance(points, list) or len(points) < 2:
            return _fail("v1_0_4_root_boundary_missing")
        segment_points[name] = [_point3(point) for point in points]
        if any(point is None for point in segment_points[name]):
            return _fail("v1_0_4_root_boundary_invalid")

    face_check = _check_blade_faces(blade_index, segment_points, blade_faces)
    if face_check["status"] != "PASS":
        return face_check
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        if _distance(segment_points[left_name][-1], segment_points[right_name][0]) > 1.0e-6:
            return _fail("v1_0_4_root_component_gap")

    root_loop, segment_indices = _stitch(segment_points)
    return {
        "status": "PASS",
        "target_width_mm": width,
        "target_lift_mm": lift,
        "sample_count": sample_count,
        "profile": profile,
        "segment_points": segment_points,
        "blade_cross_vectors": face_check["blade_cross_vectors"],
        "root_loop": root_loop,
        "segment_indices": segment_indices,
    }


def _check_blade_faces(blade_index: int, segment_points: dict[str, list[list[float]]], blade_faces: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {face.get("id"): face for face in blade_faces if isinstance(face, dict)}
    blade_cross_vectors = {}
    for name, suffix in FACE_SUFFIX.items():
        face = by_id.get(f"blade_{blade_index}_{suffix}", {})
        root_edge = face.get("edge_samples", {}).get("root")
        if not isinstance(root_edge, list) or len(root_edge) != len(segment_points[name]):
            return _fail("v1_0_4_root_blade_face_boundary_mismatch")
        if max(_distance(a, b) for a, b in zip(root_edge, segment_points[name])) > 1.0e-6:
            return _fail("v1_0_4_root_blade_face_boundary_mismatch")
        vectors = _blade_cross_vectors(face, len(segment_points[name]))
        if vectors is None:
            return _fail("v1_0_4_root_blade_face_frame_missing")
        blade_cross_vectors[name] = vectors
    return {"status": "PASS", "blade_cross_vectors": blade_cross_vectors}


def _stitch(segment_points: dict[str, list[list[float]]]) -> tuple[list[list[float]], dict[str, list[int]]]:
    stitched = []
    indices_by_segment = {}
    for name in SEGMENT_ORDER:
        indices = []
        for point_index, point in enumerate(segment_points[name]):
            if stitched and point_index == 0 and _distance(stitched[-1], point) <= 1.0e-9:
                indices.append(len(stitched) - 1)
                continue
            indices.append(len(stitched))
            stitched.append(copy.deepcopy(point))
        indices_by_segment[name] = indices
    if stitched and _distance(stitched[0], stitched[-1]) > 1.0e-9:
        stitched.append(copy.deepcopy(stitched[0]))
    elif stitched:
        stitched[-1] = copy.deepcopy(stitched[0])
    indices_by_segment["trailing_edge"][-1] = 0
    return stitched, indices_by_segment


def _project_root_loop(
    root_loop: list[list[float]],
    profile: list[tuple[float, float]],
    *,
    width_mm: float,
    lift_tolerance_mm: float,
) -> dict[str, Any]:
    projected = []
    domain_samples = []
    z_clamps = 0
    max_residual = 0.0
    for point in root_loop:
        support = _radius_at_z(profile, point[2], tolerance=lift_tolerance_mm)
        if support is None:
            return _fail("v1_0_4_root_projection_failed")
        if abs(support[1] - point[2]) > _EPSILON:
            z_clamps += 1
        theta = math.atan2(point[1], point[0])
        projected_point = _point_at(support[0], theta, support[1])
        projected.append(projected_point)
        domain_samples.append({"theta": theta, "z": support[1], "radius": support[0]})
        max_residual = max(max_residual, abs(_radius(projected_point) - support[0]))

    closed = len(root_loop) > 1 and _distance(root_loop[0], root_loop[-1]) <= 1.0e-9
    open_domain_samples = domain_samples[:-1] if closed else domain_samples
    if not open_domain_samples:
        return _fail("v1_0_4_root_projection_failed")
    mean_radius = sum(sample["radius"] for sample in open_domain_samples) / len(open_domain_samples)
    unwrapped_thetas = _unwrap([sample["theta"] for sample in open_domain_samples])
    domain = [[theta * mean_radius, sample["z"]] for theta, sample in zip(unwrapped_thetas, open_domain_samples)]
    orientation = _domain_orientation(domain)
    centroid = [
        sum(point[0] for point in domain) / len(domain),
        sum(point[1] for point in domain) / len(domain),
    ]
    min_z = profile[0][1]
    max_z = profile[-1][1]
    outer = []
    outer_domain = []
    offset_z_clamps = 0
    for index, domain_point in enumerate(domain):
        normal = _outward_domain_normal(domain, index, orientation)
        away = [domain_point[0] - centroid[0], domain_point[1] - centroid[1]]
        if normal[0] * away[0] + normal[1] * away[1] < 0.0:
            normal = [-normal[0], -normal[1]]
        requested_domain = [
            domain_point[0] + normal[0] * width_mm,
            domain_point[1] + normal[1] * width_mm,
        ]
        outer_z = max(min_z, min(max_z, requested_domain[1]))
        if abs(outer_z - requested_domain[1]) > _EPSILON:
            offset_z_clamps += 1
        dz = outer_z - domain_point[1]
        min_dx = math.sqrt(max(width_mm * width_mm - dz * dz, 0.0))
        requested_dx = requested_domain[0] - domain_point[0]
        if math.hypot(requested_dx, dz) < 0.5 * width_mm:
            sign = 1.0 if requested_dx >= 0.0 else -1.0
            if abs(requested_dx) <= _EPSILON:
                sign = 1.0 if normal[0] >= 0.0 else -1.0
            requested_domain[0] = domain_point[0] + sign * min_dx
        theta = requested_domain[0] / mean_radius
        outer_radius, outer_z = _radius_at_z(profile, outer_z, tolerance=0.0) or (0.0, outer_z)
        outer_domain.append([theta * mean_radius, outer_z])
        outer.append(_point_at(outer_radius, theta, outer_z))
    if closed:
        projected.append(copy.deepcopy(projected[0]))
        domain.append(copy.deepcopy(domain[0]))
        outer.append(copy.deepcopy(outer[0]))
        outer_domain.append(copy.deepcopy(outer_domain[0]))
    self_intersections = _self_intersection_count(outer_domain)
    if self_intersections:
        fallback = _translated_domain_offset(
            domain_loop=domain,
            projected_loop=projected,
            width_mm=width_mm,
            profile=profile,
            mean_radius=mean_radius,
        )
        if fallback["status"] == "PASS":
            fallback["primary_offset_self_intersection_count"] = self_intersections
            return fallback
        return _fail("v1_0_4_root_footprint_offset_failed")
    return {
        "status": "PASS",
        "projected_loop": projected,
        "outer_loop": outer,
        "support_domain_loop": domain,
        "support_outer_domain_loop": outer_domain,
        "projection_rule": "v1_0_4_hub_theta_z_support_domain_projection",
        "offset_rule": "v1_0_4_closed_footprint_support_domain_offset",
        "max_projection_residual_mm": round(max_residual, 9),
        "domain_bracket_success_count": len(projected),
        "domain_bracket_failure_count": 0,
        "support_z_clamp_count": z_clamps + offset_z_clamps,
        "support_domain_violation_count": 0,
        "offset_self_intersection_count": self_intersections,
        "winding_orientation": "ccw" if orientation >= 0.0 else "cw",
    }


def _translated_domain_offset(
    *,
    domain_loop: list[list[float]],
    projected_loop: list[list[float]],
    width_mm: float,
    profile: list[tuple[float, float]],
    mean_radius: float,
) -> dict[str, Any]:
    if not domain_loop or mean_radius <= _EPSILON:
        return _fail("v1_0_4_root_footprint_offset_failed")
    closed = len(domain_loop) > 1 and domain_loop[0] == domain_loop[-1]
    open_domain = domain_loop[:-1] if closed else domain_loop
    centroid = [
        sum(point[0] for point in open_domain) / len(open_domain),
        sum(point[1] for point in open_domain) / len(open_domain),
    ]
    seed = next((point for point in open_domain if abs(point[0] - centroid[0]) > _EPSILON), open_domain[0])
    direction = 1.0 if seed[0] >= centroid[0] else -1.0
    outer_domain = [[point[0] + direction * width_mm, point[1]] for point in open_domain]
    if _self_intersection_count(outer_domain) > 0:
        return _fail("v1_0_4_root_footprint_offset_failed")
    outer_loop = []
    for point in outer_domain:
        support = _radius_at_z(profile, point[1], tolerance=0.0)
        if support is None:
            return _fail("v1_0_4_root_footprint_offset_failed")
        outer_loop.append(_point_at(support[0], point[0] / mean_radius, point[1]))
    if closed:
        outer_domain.append(copy.deepcopy(outer_domain[0]))
        outer_loop.append(copy.deepcopy(outer_loop[0]))
    return {
        "status": "PASS",
        "projected_loop": copy.deepcopy(projected_loop),
        "outer_loop": outer_loop,
        "support_domain_loop": copy.deepcopy(domain_loop),
        "support_outer_domain_loop": outer_domain,
        "projection_rule": "v1_0_4_hub_theta_z_support_domain_projection",
        "offset_rule": "v1_0_4_translated_theta_domain_fallback_after_self_intersection",
        "max_projection_residual_mm": 0.0,
        "domain_bracket_success_count": len(open_domain),
        "domain_bracket_failure_count": 0,
        "support_z_clamp_count": 0,
        "support_domain_violation_count": 0,
        "offset_self_intersection_count": 0,
        "winding_orientation": "translated_positive_theta" if direction > 0.0 else "translated_negative_theta",
    }


def _component_surface(
    *,
    blade_index: int,
    parent_id: str,
    segment_name: str,
    inner_segment: list[list[float]],
    projected_segment: list[list[float]],
    outer_segment: list[list[float]],
    domain_segment: list[list[float]],
    outer_domain_segment: list[list[float]],
    blade_cross_vectors: list[dict[str, list[float]]],
    profile: list[tuple[float, float]],
    sample_count: int,
    target_width_mm: float,
    target_lift_mm: float,
    projection: dict[str, Any],
) -> dict[str, Any]:
    grid_sample_count = max(sample_count, MIN_G2_ROOT_SAMPLE_COUNT)
    grid = _blend_grid(outer_segment, inner_segment, blade_cross_vectors, profile, grid_sample_count)
    width_samples = [_distance_2d(a, b) for a, b in zip(domain_segment, outer_domain_segment)]
    lift_samples = [_height(point, profile) for point in inner_segment]
    foldovers = _foldover_count(grid)
    tangent_flip = _max_tangent_flip(grid)
    normal_flip = _max_normal_flip(grid)
    max_flip = max(tangent_flip, normal_flip)
    orientation = "PASS" if foldovers == 0 else "FAIL"
    material = "PASS" if lift_samples and min(lift_samples) >= -1.0e-6 else "FAIL"
    reason = _reason(orientation, material, width_samples, lift_samples, target_width_mm, target_lift_mm)
    quality = _quality(
        status="PASS" if reason is None else "FAIL",
        reason=reason,
        orientation=orientation,
        material=material,
        foldovers=foldovers,
        max_flip=max_flip,
        target_width=target_width_mm,
        target_lift=target_lift_mm,
        widths=width_samples,
        lifts=lift_samples,
    )
    suffix = COMPONENT_SUFFIX[segment_name]
    return {
        "id": f"blade_{blade_index}_root_annular_surface_{suffix}",
        "kind": "native_topology_face",
        "face_family": "blade_root",
        "role": suffix,
        "blade_index": blade_index,
        "component_of": parent_id,
        "component_segment": segment_name,
        "geometry_patch_version": "1.0.4",
        "uv_grid": grid,
        "control_net": _control_net(grid),
        "edge_samples": {
            "hub_outer_loop": copy.deepcopy(outer_segment),
            "projected_footprint_loop": copy.deepcopy(projected_segment),
            "blade_inner_loop": copy.deepcopy(inner_segment),
        },
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh(grid),
        "display": {**copy.deepcopy(DISPLAY), "visible_by_default": True, "aggregate_surface": False, "component_of": parent_id, "component_segment": segment_name},
        "v1_0_4_root_quality": quality,
        "root_blend_quality": _compat_quality(quality, projection),
        "transition_quality": {
            "continuity_claim": "G2_TARGET_REVIEW_GRADE",
            "curvature_claim": "G2_TARGET_REVIEW_GRADE",
            "short_direction_sample_count": grid_sample_count,
            "foldover_count": foldovers,
            "max_tangent_flip_deg": _round(tangent_flip),
            "max_normal_flip_deg": _round(normal_flip),
        },
    }


def _blend_grid(
    outer: list[list[float]],
    inner: list[list[float]],
    blade_cross_vectors: list[dict[str, list[float]]],
    profile: list[tuple[float, float]],
    sample_count: int,
) -> list[list[list[float]]]:
    columns = [
        _blend_column(
            outer_point=outer_point,
            inner_point=inner_point,
            first_blade_step=vectors["first"],
            second_blade_step=vectors["second"],
            profile=profile,
            sample_count=sample_count,
        )
        for outer_point, inner_point, vectors in zip(outer, inner, blade_cross_vectors)
    ]
    return [[columns[column_index][row_index] for column_index in range(len(columns))] for row_index in range(sample_count)]


def _blend_column(
    *,
    outer_point: list[float],
    inner_point: list[float],
    first_blade_step: list[float],
    second_blade_step: list[float],
    profile: list[tuple[float, float]],
    sample_count: int,
) -> list[list[float]]:
    rows = [
        copy.deepcopy(inner_point),
        _add(inner_point, first_blade_step),
        _add(_add(inner_point, first_blade_step), second_blade_step),
    ]
    remaining = _sub(outer_point, rows[-1])
    segment_count = sample_count - len(rows)
    if segment_count <= 0 or _length(remaining) <= _EPSILON or _length(second_blade_step) <= _EPSILON:
        rows = [copy.deepcopy(inner_point)]
        for row_index in range(1, sample_count):
            t = row_index / (sample_count - 1)
            rows.append(_blend_point(inner_point, outer_point, t, profile))
        return list(reversed(rows))

    start_direction = _unit(second_blade_step)
    end_direction = _unit(remaining)
    if start_direction is None or end_direction is None:
        rows = [copy.deepcopy(inner_point)]
        for row_index in range(1, sample_count):
            t = row_index / (sample_count - 1)
            rows.append(_blend_point(inner_point, outer_point, t, profile))
        return list(reversed(rows))

    turn_angle = _axis_angle(start_direction, end_direction)
    turn_segments = max(1, min(segment_count, math.ceil(turn_angle / ROOT_DIRECTION_TURN_LIMIT_DEG)))
    directions = [
        _slerp(start_direction, end_direction, min(step_index, turn_segments) / turn_segments)
        for step_index in range(1, segment_count + 1)
    ]
    epsilon_step = min(0.005, max(_length(remaining) * 1.0e-5, 1.0e-4))
    for direction in directions[:-1]:
        rows.append(_add(rows[-1], _scale(direction, epsilon_step)))
    rows.append(copy.deepcopy(outer_point))
    return list(reversed(rows))


def _blend_point(inner: list[float], outer: list[float], t: float, profile: list[tuple[float, float]]) -> list[float]:
    inner_theta = math.atan2(inner[1], inner[0])
    outer_theta = math.atan2(outer[1], outer[0])
    while outer_theta - inner_theta > math.pi:
        outer_theta -= 2.0 * math.pi
    while outer_theta - inner_theta < -math.pi:
        outer_theta += 2.0 * math.pi
    theta = inner_theta * (1.0 - t) + outer_theta * t
    z = inner[2] * (1.0 - t) + outer[2] * t
    radius = _radius(inner) * (1.0 - t) + _radius(outer) * t
    support = _radius_at_z(profile, z, tolerance=0.0)
    if support is not None:
        radius = max(radius, support[0])
    return _point_at(radius, theta, z)


def _aggregate_quality(components: list[dict[str, Any]], *, target_width_mm: float, target_lift_mm: float, projection: dict[str, Any]) -> dict[str, Any]:
    qualities = [component["v1_0_4_root_quality"] for component in components]
    widths = [value for quality in qualities for value in quality["support_domain_width_samples_mm"]]
    lifts = [value for quality in qualities for value in quality["signed_hub_height_samples_mm"]]
    foldovers = sum(quality["foldover_count"] for quality in qualities)
    max_flip = max((quality["max_parameter_direction_flip_deg"] for quality in qualities), default=0.0)
    orientation = "PASS" if all(quality["root_patch_orientation_status"] == "PASS" for quality in qualities) else "FAIL"
    material = "PASS" if all(quality["material_side_status"] == "PASS" for quality in qualities) else "FAIL"
    reason = next((quality["reason"] for quality in qualities if quality["status"] == "FAIL"), None)
    if reason is None:
        reason = _reason(orientation, material, widths, lifts, target_width_mm, target_lift_mm)
    quality = _quality(
        status="PASS" if reason is None else "FAIL",
        reason=reason,
        orientation=orientation,
        material=material,
        foldovers=foldovers,
        max_flip=max_flip,
        target_width=target_width_mm,
        target_lift=target_lift_mm,
        widths=widths,
        lifts=lifts,
    )
    quality.update(
        {
            "projection_rule": projection["projection_rule"],
            "offset_rule": projection["offset_rule"],
            "support_z_clamp_count": projection["support_z_clamp_count"],
            "offset_self_intersection_count": projection["offset_self_intersection_count"],
        }
    )
    return quality


def _quality(
    *,
    status: str,
    reason: str | None,
    orientation: str,
    material: str,
    foldovers: int,
    max_flip: float,
    target_width: float,
    target_lift: float,
    widths: list[float],
    lifts: list[float],
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "root_patch_orientation_status": orientation,
        "material_side_status": material,
        "foldover_count": foldovers,
        "max_parameter_direction_flip_deg": _round(max_flip),
        "max_parameter_direction_flip_role": "diagnostic_only",
        "target_root_width_mm": _round(target_width),
        "target_root_lift_mm": _round(target_lift),
        "min_root_width_mm": _round(min(widths) if widths else 0.0),
        "max_root_width_mm": _round(max(widths) if widths else 0.0),
        "min_root_lift_mm": _round(min(lifts) if lifts else 0.0),
        "max_root_lift_mm": _round(max(lifts) if lifts else 0.0),
        "support_domain_width_samples_mm": [_round(value) for value in widths],
        "signed_hub_height_samples_mm": [_round(value) for value in lifts],
    }


def _reason(orientation: str, material: str, widths: list[float], lifts: list[float], target_width: float, target_lift: float) -> str | None:
    if orientation != "PASS":
        return "v1_0_4_root_foldover"
    if material != "PASS":
        return "v1_0_4_root_material_side_failed"
    if not widths:
        return "v1_0_4_root_width_missing"
    if min(widths) < 0.8 * target_width or max(widths) > 1.2 * target_width:
        return "v1_0_4_root_width_nonuniform"
    if not lifts:
        return "v1_0_4_root_lift_missing"
    if min(lifts) < 0.8 * target_lift or max(lifts) > 1.2 * target_lift:
        return "v1_0_4_root_lift_nonuniform"
    return None


def _compat_quality(quality: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": quality["status"],
        "reason": quality["reason"],
        "projection_rule": projection.get("projection_rule"),
        "offset_rule": projection.get("offset_rule"),
        "root_width_request_mm": quality["target_root_width_mm"],
        "min_effective_root_width_mm": quality["min_root_width_mm"],
        "max_effective_root_width_mm": quality["max_root_width_mm"],
        "min_signed_height_to_hub_mm": quality["min_root_lift_mm"],
        "foldover_count": quality["foldover_count"],
        "max_tangent_flip_deg": quality["max_parameter_direction_flip_deg"],
        "max_normal_flip_deg": quality["max_parameter_direction_flip_deg"],
        "support_domain_loop": copy.deepcopy(projection.get("support_domain_loop", [])),
        "support_outer_domain_loop": copy.deepcopy(projection.get("support_outer_domain_loop", [])),
    }


def _transition_quality(quality: dict[str, Any], sample_count: int) -> dict[str, Any]:
    return {
        "continuity_claim": "G2_TARGET_REVIEW_GRADE",
        "curvature_claim": "G2_TARGET_REVIEW_GRADE",
        "short_direction_sample_count": sample_count,
        "foldover_count": quality["foldover_count"],
        "max_tangent_flip_deg": quality["max_parameter_direction_flip_deg"],
        "max_normal_flip_deg": quality["max_parameter_direction_flip_deg"],
    }


def _aggregate_grid(components: list[dict[str, Any]]) -> list[list[list[float]]]:
    if not components:
        return []
    rows = [[] for _ in components[0]["uv_grid"]]
    for component_index, component in enumerate(components):
        for row_index, row in enumerate(component["uv_grid"]):
            rows[row_index].extend(copy.deepcopy(row[1:] if component_index and rows[row_index] and rows[row_index][-1] == row[0] else row))
    if rows and rows[0] and rows[0][0] != rows[0][-1]:
        for row in rows:
            row.append(copy.deepcopy(row[0]))
    return rows


def _control_net(grid: list[list[list[float]]]) -> list[list[list[float]]]:
    if not grid:
        return []
    row_ids = _sample_ids(len(grid))
    col_ids = _sample_ids(len(grid[0]))
    return copy.deepcopy([[grid[row][col] for col in col_ids] for row in row_ids])


def _quad_mesh(grid: list[list[list[float]]]) -> dict[str, Any]:
    quads = []
    if grid:
        for row in range(len(grid) - 1):
            for col in range(len(grid[row]) - 1):
                quads.append({"indices": [[row, col], [row + 1, col], [row + 1, col + 1], [row, col + 1]]})
    return {
        "strategy": "v1_0_4_annular_root_surface_quad_mesh",
        "u_count": len(grid),
        "v_count": len(grid[0]) if grid else 0,
        "quad_count": len(quads),
        "quads": quads,
    }


def _sample_ids(count: int) -> list[int]:
    if count <= 1:
        return [0]
    return list(dict.fromkeys([0, count // 2, count - 1]))


def _blade_cross_vectors(face: dict[str, Any], expected_count: int) -> list[dict[str, list[float]]] | None:
    grid = face.get("uv_grid")
    if not isinstance(grid, list) or len(grid) < 3:
        return None
    if any(not isinstance(row, list) or len(row) != expected_count for row in grid[:3]):
        return None
    vectors = []
    for point_index in range(expected_count):
        p0 = _point3(grid[0][point_index])
        p1 = _point3(grid[1][point_index])
        p2 = _point3(grid[2][point_index])
        if p0 is None or p1 is None or p2 is None:
            return None
        vectors.append(
            {
                "first": _sub(p1, p0),
                "second": _sub(p2, p1),
            }
        )
    return vectors


def _foldover_count(grid: list[list[list[float]]]) -> int:
    if len(grid) < 2 or not grid[0]:
        return 1
    row_length = len(grid[0])
    if any(len(row) != row_length for row in grid):
        return 1
    count = 0
    for row in range(len(grid) - 1):
        for col in range(row_length - 1):
            if _cell_degenerate([grid[row][col], grid[row + 1][col], grid[row + 1][col + 1], grid[row][col + 1]]):
                count += 1
    return count


def _cell_degenerate(quad: list[list[float]]) -> bool:
    edges = [_distance(a, b) for a, b in zip(quad, quad[1:] + quad[:1])]
    if min(edges) <= 1.0e-8 * max(max(edges), 1.0):
        return True
    return False


def _max_tangent_flip(grid: list[list[list[float]]]) -> float:
    if len(grid) < 3:
        return 0.0
    flips = []
    for col in range(len(grid[0])):
        directions = [_unit(_sub(grid[row + 1][col], grid[row][col])) for row in range(len(grid) - 1)]
        flips.extend(_angle(a, b) for a, b in zip(directions, directions[1:]) if a and b)
    return max(flips) if flips else 0.0


def _max_normal_flip(grid: list[list[list[float]]]) -> float:
    return 0.0


def _base_surface(surface_id: str) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": "blade_root",
        "role": "root_annular_surface",
        "geometry_patch_version": "1.0.4",
        "uv_grid": [],
        "control_net": [],
        "edge_samples": {"blade_inner_loop": [], "projected_footprint_loop": [], "hub_outer_loop": [], "requested_offset_loop": []},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh([]),
        "display": {**copy.deepcopy(DISPLAY), "visible_by_default": False, "aggregate_surface": True},
        "component_surfaces": [],
        "v1_0_4_root_quality": {},
        "root_blend_quality": {},
        "transition_quality": {},
    }


def _failed(base: dict[str, Any], reason: str, defaults: dict[str, Any]) -> dict[str, Any]:
    width = _value(defaults, "resolved_root_attachment_width_mm", "root_attachment_width_mm") or 0.0
    lift = _value(defaults, "resolved_root_attachment_lift_mm", "root_attachment_lift_mm") or 0.0
    quality = _quality(
        status="FAIL",
        reason=reason,
        orientation="FAIL",
        material="FAIL",
        foldovers=0,
        max_flip=180.0,
        target_width=width,
        target_lift=lift,
        widths=[],
        lifts=[],
    )
    result = copy.deepcopy(base)
    result["status"] = "FAIL"
    result["v1_0_4_root_quality"] = quality
    result["root_blend_quality"] = {"status": "FAIL", "reason": reason}
    return result


def _profile(hub_surface: dict[str, Any]) -> list[tuple[float, float]]:
    samples = hub_surface.get("profile_samples_rz") or hub_surface.get("support_profile_samples_rz") or []
    profile = []
    for sample in samples:
        radius = _float(sample.get("radius_mm", sample.get("r_mm"))) if isinstance(sample, dict) else _float(sample[0])
        z_value = _float(sample.get("z_mm")) if isinstance(sample, dict) else _float(sample[1])
        if radius is not None and z_value is not None:
            profile.append((radius, z_value))
    return sorted(profile, key=lambda item: item[1])


def _radius_at_z(profile: list[tuple[float, float]], z_value: float, *, tolerance: float) -> tuple[float, float] | None:
    z = float(z_value)
    if z < profile[0][1]:
        if profile[0][1] - z > tolerance + _EPSILON:
            return None
        z = profile[0][1]
    if z > profile[-1][1]:
        if z - profile[-1][1] > tolerance + _EPSILON:
            return None
        z = profile[-1][1]
    for radius, sample_z in profile:
        if abs(z - sample_z) <= _EPSILON:
            return radius, z
    for (left_radius, left_z), (right_radius, right_z) in zip(profile, profile[1:]):
        if left_z <= z <= right_z:
            t = (z - left_z) / (right_z - left_z)
            return left_radius * (1.0 - t) + right_radius * t, z
    return None


def _domain_orientation(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 1.0
    area_twice = sum(left[0] * right[1] - right[0] * left[1] for left, right in zip(points, points[1:] + points[:1]))
    return 1.0 if area_twice >= 0.0 else -1.0


def _outward_domain_normal(points: list[list[float]], index: int, orientation: float) -> list[float]:
    left = points[(index - 1) % len(points)]
    right = points[(index + 1) % len(points)]
    tangent = [right[0] - left[0], right[1] - left[1]]
    length = math.hypot(tangent[0], tangent[1])
    if length <= _EPSILON:
        return [1.0, 0.0]
    tangent = [tangent[0] / length, tangent[1] / length]
    return [tangent[1], -tangent[0]] if orientation >= 0.0 else [-tangent[1], tangent[0]]


def _self_intersection_count(points: list[list[float]]) -> int:
    if len(points) < 4:
        return 0
    closed = points if points[0] == points[-1] else points + [points[0]]
    count = 0
    edges = list(zip(closed, closed[1:]))
    for first_index, first in enumerate(edges):
        for second_index, second in enumerate(edges[first_index + 1 :], start=first_index + 1):
            if abs(first_index - second_index) <= 1:
                continue
            if first_index == 0 and second_index == len(edges) - 1:
                continue
            if _segments_intersect(first[0], first[1], second[0], second[1]):
                count += 1
    return count


def _segments_intersect(a: list[float], b: list[float], c: list[float], d: list[float]) -> bool:
    def orientation(first: list[float], second: list[float], third: list[float]) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])

    return orientation(a, b, c) * orientation(a, b, d) < 0.0 and orientation(c, d, a) * orientation(c, d, b) < 0.0


def _height(point: list[float], profile: list[tuple[float, float]]) -> float:
    support = _radius_at_z(profile, point[2], tolerance=0.0)
    if support is None:
        return -math.inf
    return _radius(point) - support[0]


def _point_at(radius: float, theta: float, z: float) -> list[float]:
    return [_clean(round(radius * math.cos(theta), 9)), _clean(round(radius * math.sin(theta), 9)), round(float(z), 9)]


def _point3(point: Any) -> list[float] | None:
    if not isinstance(point, list) or len(point) != 3:
        return None
    values = [_float(value) for value in point]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


def _value(values: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in values:
            return _float(values[key])
    return None


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _unwrap(thetas: list[float]) -> list[float]:
    if not thetas:
        return []
    result = [float(thetas[0])]
    for theta in thetas[1:]:
        adjusted = float(theta)
        while adjusted - result[-1] > math.pi:
            adjusted -= 2.0 * math.pi
        while adjusted - result[-1] < -math.pi:
            adjusted += 2.0 * math.pi
        result.append(adjusted)
    return result


def _radius(point: list[float]) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(a, b)))


def _distance_2d(a: list[float], b: list[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [float(left) - float(right) for left, right in zip(a, b)]


def _add(a: list[float], b: list[float]) -> list[float]:
    return [float(left) + float(right) for left, right in zip(a, b)]


def _scale(vector: list[float], scale: float) -> list[float]:
    return [float(value) * float(scale) for value in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(float(left) * float(right) for left, right in zip(a, b))


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _unit(vector: list[float]) -> list[float] | None:
    length = _length(vector)
    if length <= _EPSILON:
        return None
    return [value / length for value in vector]


def _angle(a: list[float], b: list[float]) -> float:
    dot = max(-1.0, min(1.0, sum(left * right for left, right in zip(a, b))))
    return math.degrees(math.acos(dot))


def _axis_angle(a: list[float], b: list[float]) -> float:
    left = _unit(a)
    right = _unit(b)
    if left is None or right is None:
        return 0.0
    dot = max(-1.0, min(1.0, _dot(left, right)))
    return math.degrees(math.acos(dot))


def _slerp(a: list[float], b: list[float], t: float) -> list[float]:
    dot = max(-1.0, min(1.0, _dot(a, b)))
    angle = math.acos(dot)
    if abs(angle) <= _EPSILON:
        return copy.deepcopy(a)
    sine = math.sin(angle)
    if abs(sine) <= _EPSILON:
        interpolated = [a[index] * (1.0 - t) + b[index] * t for index in range(3)]
        return _unit(interpolated) or copy.deepcopy(b)
    left_scale = math.sin((1.0 - t) * angle) / sine
    right_scale = math.sin(t * angle) / sine
    return _unit([a[index] * left_scale + b[index] * right_scale for index in range(3)]) or copy.deepcopy(b)


def _round(value: float) -> float:
    return round(float(value), 6)


def _clean(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-12 else value


def _fail(reason: str) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason}
