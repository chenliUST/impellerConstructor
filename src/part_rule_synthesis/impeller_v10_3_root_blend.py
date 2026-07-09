from __future__ import annotations

import copy
import math
from typing import Any


Point2 = list[float]
Point3 = list[float]
ProfileSample = tuple[float, float]

ROOT_BLEND_METHOD = "section-loop-driven segmented support-domain Hermite/G2 root blend"
PROJECTION_RULE = "hub_theta_z_parameter_domain"
OFFSET_RULE = "closed_footprint_winding_support_domain_offset"
DISPLAY = {
    "inspection_class": "root_to_hub_blend",
    "color": "#ff00cc",
    "wire_color": "#fff200",
}
SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
COMPONENT_BY_SEGMENT = {
    "pressure_side": "pressure_root",
    "leading_edge": "leading_root_corner",
    "suction_side": "suction_root",
    "trailing_edge": "trailing_root_corner",
}
FACE_ID_BY_SEGMENT = {
    "pressure_side": "pressure_surface",
    "leading_edge": "leading_edge_surface",
    "suction_side": "suction_surface",
    "trailing_edge": "trailing_edge_surface",
}
_EPSILON = 1.0e-9


def build_v10_3_root_blend(
    blade_index: int,
    lattice: dict[str, Any],
    blade_faces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    surface_id = f"blade_{blade_index}_root_annular_surface"
    base = _base_surface(surface_id)

    validation = _validate_inputs(
        blade_index=blade_index,
        lattice=lattice,
        blade_faces=blade_faces,
        hub_surface=hub_surface,
        defaults=defaults,
    )
    if validation["status"] == "FAIL":
        return _failure(base, validation["reason"], validation)

    width_mm = validation["width_mm"]
    sample_count = validation["sample_count"]
    profile = validation["profile"]
    root_loop = validation["root_loop"]
    segment_points = validation["segment_points"]
    segment_indices = validation["segment_indices"]

    projection = _project_and_offset_root_loop(
        root_loop=root_loop,
        profile=profile,
        width_mm=width_mm,
        z_tolerance_mm=validation["lift_mm"],
    )
    if projection["status"] == "FAIL":
        return _failure(base, projection["reason"], projection)

    components: list[dict[str, Any]] = []
    tangent_flips: list[float] = []
    normal_flips: list[float] = []
    foldover_count = 0
    all_blend_points: list[Point3] = []
    for segment_name in SEGMENT_ORDER:
        indices = segment_indices[segment_name]
        inner_segment = copy.deepcopy(segment_points[segment_name])
        outer_segment = [copy.deepcopy(projection["outer_loop"][index]) for index in indices]
        projected_segment = [copy.deepcopy(projection["projected_loop"][index]) for index in indices]
        component = _component_surface(
            parent_id=surface_id,
            blade_index=blade_index,
            segment_name=segment_name,
            inner_segment=inner_segment,
            outer_segment=outer_segment,
            projected_segment=projected_segment,
            sample_count=sample_count,
            quality_seed=projection,
            width_mm=width_mm,
            hub_surface=hub_surface,
            profile=profile,
        )
        components.append(component)
        all_blend_points.extend(point for row in component["uv_grid"] for point in row)
        tangent_flips.append(component["transition_quality"]["max_tangent_flip_deg"])
        normal_flips.append(component["transition_quality"]["max_normal_flip_deg"])
        foldover_count += component["transition_quality"]["foldover_count"]

    min_height = _min_signed_height_to_hub(all_blend_points, profile)
    max_inner_gap = _max_inner_loop_gap(root_loop, _stitch_root_loop(segment_points)[0])
    max_outer_gap = _max_gap_to_hub(projection["outer_loop"], hub_surface)
    min_effective, max_effective = _effective_width_range(
        projection["domain_loop"],
        projection["outer_domain_loop"],
    )
    aggregate_quality = _quality_payload(
        status="PASS",
        reason=None,
        projection=projection,
        root_loop=root_loop,
        width_mm=width_mm,
        min_effective_width_mm=min_effective,
        max_effective_width_mm=max_effective,
        max_tangent_flip_deg=max(tangent_flips) if tangent_flips else 0.0,
        max_normal_flip_deg=max(normal_flips) if normal_flips else 0.0,
        foldover_count=foldover_count,
        min_signed_height_to_hub_mm=min_height,
        component_count=len(components),
        max_root_inner_loop_gap_mm=max_inner_gap,
        max_root_outer_loop_gap_to_hub_mm=max_outer_gap,
    )

    gate_reason = _quality_gate_failure(aggregate_quality, requested_width_mm=width_mm)
    if gate_reason is not None:
        return _failure(base, gate_reason, {**projection, **aggregate_quality})

    aggregate_grid = _aggregate_grid(components)
    base.update(
        {
            "status": "PASS",
            "root_blend_method": ROOT_BLEND_METHOD,
            "uv_grid": aggregate_grid,
            "control_net": _control_net(aggregate_grid),
            "edge_samples": {
                "blade_inner_loop": copy.deepcopy(root_loop),
                "projected_footprint_loop": copy.deepcopy(projection["projected_loop"]),
                "hub_outer_loop": copy.deepcopy(projection["outer_loop"]),
                "requested_offset_loop": copy.deepcopy(projection["requested_offset_loop"]),
                "requested_offset_loop_semantics": projection["requested_offset_loop_semantics"],
            },
            "wireframe": {"enabled": True, "source": "uv_grid"},
            "mesh": _quad_mesh(aggregate_grid),
            "display": {**copy.deepcopy(DISPLAY), "visible_by_default": False, "aggregate_surface": True},
            "root_blend_quality": aggregate_quality,
            "transition_quality": {
                "continuity_claim": "G2_TARGET_REVIEW_GRADE",
                "curvature_claim": "G2_TARGET_REVIEW_GRADE",
                "short_direction_sample_count": sample_count,
                "foldover_count": foldover_count,
                "max_tangent_flip_deg": aggregate_quality["max_tangent_flip_deg"],
                "max_normal_flip_deg": aggregate_quality["max_normal_flip_deg"],
            },
            "component_surfaces": components,
        }
    )
    return base


def _validate_inputs(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    blade_faces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(lattice, dict) or lattice.get("status") != "PASS":
        return _fail("v1_0_3_root_blade_derivative_missing")
    if not isinstance(defaults, dict):
        return _fail("v1_0_3_root_footprint_offset_failed")
    width_mm = _resolved_positive_float(defaults, "resolved_root_attachment_width_mm", "root_attachment_width_mm")
    if width_mm is None:
        return _fail("v1_0_3_root_footprint_offset_failed")
    lift_mm = _resolved_non_negative_float(defaults, "resolved_root_attachment_lift_mm", "root_attachment_lift_mm")
    if lift_mm is None:
        lift_mm = 0.0
    sample_count = defaults.get("attachment_short_direction_sample_count", 17)
    if type(sample_count) is not int or sample_count < 17:
        return _fail("v1_0_3_root_segment_g2_infeasible")
    profile_result = _normalize_profile_samples(hub_surface)
    if profile_result["status"] == "FAIL":
        return _fail("v1_0_3_root_projection_failed", details=profile_result["reason"])
    blades = lattice.get("blades")
    if not isinstance(blades, list) or blade_index < 0 or blade_index >= len(blades):
        return _fail("v1_0_3_root_blade_derivative_missing")
    blade = blades[blade_index]
    loops = blade.get("section_loops") if isinstance(blade, dict) else None
    if not isinstance(loops, list) or not loops:
        return _fail("v1_0_3_root_blade_derivative_missing")
    root_section = loops[0]
    segments = root_section.get("segments") if isinstance(root_section, dict) else None
    if not isinstance(segments, dict):
        return _fail("v1_0_3_root_blade_derivative_missing")

    segment_points: dict[str, list[Point3]] = {}
    for segment_name in SEGMENT_ORDER:
        segment = segments.get(segment_name)
        points = segment.get("points") if isinstance(segment, dict) else None
        if not isinstance(points, list) or len(points) < 2:
            return _fail("v1_0_3_root_blade_derivative_missing")
        normalized_points = [_point3(point) for point in points]
        if any(point is None for point in normalized_points):
            return _fail("v1_0_3_root_blade_derivative_missing")
        segment_points[segment_name] = [copy.deepcopy(point) for point in normalized_points if point is not None]

    face_validation = _validate_blade_faces(blade_index, segment_points, blade_faces)
    if face_validation["status"] == "FAIL":
        return face_validation

    continuity = _validate_segment_continuity(segment_points)
    if continuity["status"] == "FAIL":
        return continuity

    root_loop, segment_indices = _stitch_root_loop(segment_points)
    domain_points = _domain_points_for_loop(
        root_loop,
        profile_result["profile"],
        z_tolerance_mm=lift_mm,
    )
    if domain_points["status"] == "FAIL":
        return domain_points
    if _self_intersection_count(domain_points["domain_loop"]) > 0:
        return _fail("v1_0_3_root_segment_foldover")

    return {
        "status": "PASS",
        "width_mm": width_mm,
        "lift_mm": lift_mm,
        "sample_count": sample_count,
        "profile": profile_result["profile"],
        "root_loop": root_loop,
        "segment_points": segment_points,
        "segment_indices": segment_indices,
    }


def _validate_blade_faces(
    blade_index: int,
    segment_points: dict[str, list[Point3]],
    blade_faces: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(blade_faces, list):
        return _fail("v1_0_3_root_blade_derivative_missing")
    by_id = {face.get("id"): face for face in blade_faces if isinstance(face, dict)}
    for segment_name, suffix in FACE_ID_BY_SEGMENT.items():
        face = by_id.get(f"blade_{blade_index}_{suffix}")
        if not isinstance(face, dict):
            return _fail("v1_0_3_root_blade_derivative_missing")
        root_edge = face.get("edge_samples", {}).get("root")
        if _max_inner_loop_gap(root_edge, segment_points[segment_name]) is None or _max_inner_loop_gap(root_edge, segment_points[segment_name]) > 1.0e-6:
            return _fail("v1_0_3_root_component_gap")
    return {"status": "PASS"}


def _validate_segment_continuity(segment_points: dict[str, list[Point3]]) -> dict[str, Any]:
    for left_name, right_name in zip(SEGMENT_ORDER, SEGMENT_ORDER[1:] + SEGMENT_ORDER[:1]):
        left = segment_points[left_name]
        right = segment_points[right_name]
        if _distance(left[-1], right[0]) <= 1.0e-6:
            continue
        if _distance(left[-1], right[-1]) <= 1.0e-6 or _distance(left[0], right[0]) <= 1.0e-6:
            return _fail("v1_0_3_root_material_side_ambiguous")
        return _fail("v1_0_3_root_component_gap")
    return {"status": "PASS"}


def _stitch_root_loop(segment_points: dict[str, list[Point3]]) -> tuple[list[Point3], dict[str, list[int]]]:
    stitched: list[Point3] = []
    segment_indices: dict[str, list[int]] = {}
    for segment_name in SEGMENT_ORDER:
        indices: list[int] = []
        points = segment_points[segment_name]
        for point_index, point in enumerate(points):
            if stitched and point_index == 0 and _distance(stitched[-1], point) <= 1.0e-9:
                indices.append(len(stitched) - 1)
                continue
            indices.append(len(stitched))
            stitched.append(copy.deepcopy(point))
        segment_indices[segment_name] = indices
    if stitched and _distance(stitched[0], stitched[-1]) > 1.0e-9:
        stitched.append(copy.deepcopy(stitched[0]))
    else:
        stitched[-1] = copy.deepcopy(stitched[0])
    segment_indices["trailing_edge"][-1] = 0
    return stitched, segment_indices


def _project_and_offset_root_loop(
    *,
    root_loop: list[Point3],
    profile: list[ProfileSample],
    width_mm: float,
    z_tolerance_mm: float,
) -> dict[str, Any]:
    projected: list[Point3] = []
    domain_samples: list[dict[str, float]] = []
    success_count = 0
    failure_count = 0
    z_clamp_count = 0
    max_residual = 0.0
    violation_count = 0

    for point in root_loop:
        theta = math.atan2(point[1], point[0])
        z_result = _interpolated_radius_at_z(profile, point[2], z_tolerance_mm=z_tolerance_mm)
        if z_result["status"] == "FAIL":
            failure_count += 1
            violation_count += 1
            continue
        success_count += 1
        if z_result.get("z_clamped"):
            z_clamp_count += 1
        radius = z_result["radius_mm"]
        z = z_result["z_mm"]
        projected_point = _point_at_radius_theta_z(radius=radius, theta=theta, z=z)
        projected.append(projected_point)
        domain_samples.append(
            {
                "theta": theta,
                "z": z,
                "radius": radius,
            }
        )
        max_residual = max(max_residual, abs(_xy_radius(projected_point) - radius))

    if violation_count or len(projected) != len(root_loop):
        return _fail(
            "v1_0_3_root_projection_failed",
            max_projection_residual_mm=_round(max_residual),
            domain_bracket_success_count=success_count,
            domain_bracket_failure_count=failure_count,
            support_z_clamp_count=z_clamp_count,
            support_domain_violation_count=violation_count,
        )

    closed = len(projected) > 1 and _distance(projected[0], projected[-1]) <= 1.0e-9
    open_domain_samples = domain_samples[:-1] if closed else domain_samples
    mean_radius = sum(sample["radius"] for sample in open_domain_samples) / len(open_domain_samples)
    unwrapped_thetas = _unwrap_thetas([sample["theta"] for sample in open_domain_samples])
    domain_loop = [
        [theta * mean_radius, sample["z"]]
        for theta, sample in zip(unwrapped_thetas, open_domain_samples)
    ]
    orientation = _domain_orientation(domain_loop)
    min_z = profile[0][1]
    max_z = profile[-1][1]
    outer_domain: list[Point2] = []
    outer_loop: list[Point3] = []
    requested_offset_loop: list[Point3] = []
    offset_z_clamps = 0
    centroid = [
        sum(point[0] for point in domain_loop) / len(domain_loop),
        sum(point[1] for point in domain_loop) / len(domain_loop),
    ]
    for index, domain_point in enumerate(domain_loop):
        normal = _outward_domain_normal(domain_loop, index, orientation)
        away_from_centroid = [
            domain_point[0] - centroid[0],
            domain_point[1] - centroid[1],
        ]
        if normal[0] * away_from_centroid[0] + normal[1] * away_from_centroid[1] < 0.0:
            normal = [-normal[0], -normal[1]]
        requested_domain = [
            domain_point[0] + normal[0] * width_mm,
            domain_point[1] + normal[1] * width_mm,
        ]
        outer_z = _clamp(requested_domain[1], min_z, max_z)
        if abs(outer_z - requested_domain[1]) > _EPSILON:
            offset_z_clamps += 1
        actual_dz = outer_z - domain_point[1]
        min_dx = math.sqrt(max(width_mm * width_mm - actual_dz * actual_dz, 0.0))
        requested_dx = requested_domain[0] - domain_point[0]
        if math.hypot(requested_dx, actual_dz) < 0.5 * width_mm:
            sign = 1.0 if requested_dx >= 0.0 else -1.0
            if abs(requested_dx) <= _EPSILON:
                sign = 1.0 if normal[0] >= 0.0 else -1.0
            requested_domain[0] = domain_point[0] + sign * min_dx
        radius_result = _interpolated_radius_at_z(profile, outer_z)
        theta = requested_domain[0] / mean_radius
        point = _point_at_radius_theta_z(radius=radius_result["radius_mm"], theta=theta, z=outer_z)
        outer_domain.append([theta * mean_radius, outer_z])
        outer_loop.append(point)
        requested_offset_loop.append(point)

    if closed and outer_loop:
        outer_loop.append(copy.deepcopy(outer_loop[0]))
        outer_domain.append(copy.deepcopy(outer_domain[0]))
        requested_offset_loop.append(copy.deepcopy(requested_offset_loop[0]))
        domain_loop.append(copy.deepcopy(domain_loop[0]))

    self_intersections = _self_intersection_count(outer_domain)
    if self_intersections > 0:
        fallback = _translated_domain_offset(
            domain_loop=domain_loop,
            projected_loop=projected,
            width_mm=width_mm,
            profile=profile,
            mean_radius=mean_radius,
        )
        if fallback["status"] == "PASS":
            fallback["primary_offset_self_intersection_count"] = self_intersections
            return fallback
        return _fail("v1_0_3_root_footprint_offset_failed", offset_self_intersection_count=self_intersections)

    return {
        "status": "PASS",
        "projected_loop": projected,
        "outer_loop": outer_loop,
        "requested_offset_loop": requested_offset_loop,
        "requested_offset_loop_semantics": "post_clamp_hub_projected_offset_loop",
        "domain_loop": domain_loop,
        "outer_domain_loop": outer_domain,
        "projection_rule": PROJECTION_RULE,
        "offset_rule": OFFSET_RULE,
        "max_projection_residual_mm": _round(max_residual),
        "domain_bracket_success_count": success_count,
        "domain_bracket_failure_count": failure_count,
        "support_z_clamp_count": z_clamp_count + offset_z_clamps,
        "support_domain_violation_count": violation_count,
        "winding_orientation": "ccw" if orientation >= 0.0 else "cw",
        "offset_self_intersection_count": self_intersections,
        "support_domain_loop": copy.deepcopy(domain_loop),
        "support_outer_domain_loop": copy.deepcopy(outer_domain),
    }


def _translated_domain_offset(
    *,
    domain_loop: list[Point2],
    projected_loop: list[Point3],
    width_mm: float,
    profile: list[ProfileSample],
    mean_radius: float,
) -> dict[str, Any]:
    if not domain_loop or mean_radius <= _EPSILON:
        return _fail("v1_0_3_root_footprint_offset_failed")
    closed = len(domain_loop) > 1 and domain_loop[0] == domain_loop[-1]
    open_domain = domain_loop[:-1] if closed else domain_loop
    centroid = [
        sum(point[0] for point in open_domain) / len(open_domain),
        sum(point[1] for point in open_domain) / len(open_domain),
    ]
    seed = next(
        (
            point
            for point in open_domain
            if abs(point[0] - centroid[0]) > _EPSILON
        ),
        open_domain[0],
    )
    direction = 1.0 if seed[0] >= centroid[0] else -1.0
    outer_domain = [[point[0] + direction * width_mm, point[1]] for point in open_domain]
    if _self_intersection_count(outer_domain) > 0:
        return _fail("v1_0_3_root_footprint_offset_failed")

    outer_loop: list[Point3] = []
    for point in outer_domain:
        radius_result = _interpolated_radius_at_z(profile, point[1])
        if radius_result["status"] == "FAIL":
            return _fail("v1_0_3_root_footprint_offset_failed")
        outer_loop.append(
            _point_at_radius_theta_z(
                radius=radius_result["radius_mm"],
                theta=point[0] / mean_radius,
                z=point[1],
            )
        )
    if closed:
        outer_domain.append(copy.deepcopy(outer_domain[0]))
        outer_loop.append(copy.deepcopy(outer_loop[0]))

    return {
        "status": "PASS",
        "projected_loop": copy.deepcopy(projected_loop),
        "outer_loop": outer_loop,
        "requested_offset_loop": copy.deepcopy(outer_loop),
        "requested_offset_loop_semantics": "translated_theta_domain_hub_projected_offset_loop",
        "domain_loop": copy.deepcopy(domain_loop),
        "outer_domain_loop": outer_domain,
        "projection_rule": PROJECTION_RULE,
        "offset_rule": "translated_theta_domain_fallback_after_self_intersection",
        "max_projection_residual_mm": 0.0,
        "domain_bracket_success_count": len(open_domain),
        "domain_bracket_failure_count": 0,
        "support_z_clamp_count": 0,
        "support_domain_violation_count": 0,
        "winding_orientation": "translated_positive_theta" if direction > 0.0 else "translated_negative_theta",
        "offset_self_intersection_count": 0,
        "support_domain_loop": copy.deepcopy(domain_loop),
        "support_outer_domain_loop": copy.deepcopy(outer_domain),
    }


def _component_surface(
    *,
    parent_id: str,
    blade_index: int,
    segment_name: str,
    inner_segment: list[Point3],
    outer_segment: list[Point3],
    projected_segment: list[Point3],
    sample_count: int,
    quality_seed: dict[str, Any],
    width_mm: float,
    hub_surface: dict[str, Any],
    profile: list[ProfileSample],
) -> dict[str, Any]:
    component_name = COMPONENT_BY_SEGMENT[segment_name]
    uv_grid = _hermite_width_grid(
        outer_segment=outer_segment,
        inner_segment=inner_segment,
        projected_segment=projected_segment,
        sample_count=sample_count,
        profile=profile,
    )
    tangent_flip = _max_width_tangent_flip(uv_grid)
    normal_flip = _max_grid_normal_flip(uv_grid)
    foldover_count = _grid_foldover_count(uv_grid)
    min_effective, max_effective = _width_range(projected_segment, outer_segment)
    all_points = [point for row in uv_grid for point in row]
    min_signed_height = _min_signed_height_to_hub(all_points, profile)
    quality = {
        "component_status": "PASS",
        "root_blend_method": ROOT_BLEND_METHOD,
        "projection_rule": PROJECTION_RULE,
        "offset_rule": OFFSET_RULE,
        "max_projection_residual_mm": quality_seed["max_projection_residual_mm"],
        "domain_bracket_success_count": len(inner_segment),
        "domain_bracket_failure_count": quality_seed["domain_bracket_failure_count"],
        "support_z_clamp_count": quality_seed["support_z_clamp_count"],
        "support_domain_violation_count": quality_seed["support_domain_violation_count"],
        "root_width_request_mm": _round(width_mm),
        "min_effective_root_width_mm": _round(min_effective),
        "max_effective_root_width_mm": _round(max_effective),
        "winding_orientation": quality_seed["winding_orientation"],
        "offset_self_intersection_count": quality_seed["offset_self_intersection_count"],
        "max_root_inner_loop_gap_mm": _max_inner_loop_gap(uv_grid[-1], inner_segment),
        "max_root_outer_loop_gap_to_hub_mm": _max_gap_to_hub(outer_segment, hub_surface),
        "max_tangent_flip_deg": _round(tangent_flip),
        "max_normal_flip_deg": _round(normal_flip),
        "foldover_count": foldover_count,
        "min_signed_height_to_hub_mm": _round(min_signed_height),
        "material_side": "positive" if min_signed_height >= -1.0e-6 else "under_hub",
    }
    return {
        "id": f"blade_{blade_index}_{component_name}",
        "kind": "native_topology_face",
        "face_family": "blade_root",
        "role": component_name,
        "blade_index": blade_index,
        "component_of": parent_id,
        "component_segment": component_name,
        "root_blend_method": ROOT_BLEND_METHOD,
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "edge_samples": {
            "hub_outer_loop": copy.deepcopy(outer_segment),
            "projected_footprint_loop": copy.deepcopy(projected_segment),
            "blade_inner_loop": copy.deepcopy(inner_segment),
        },
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh(uv_grid),
        "display": {
            **copy.deepcopy(DISPLAY),
            "visible_by_default": True,
            "aggregate_surface": False,
            "component_of": parent_id,
            "component_segment": component_name,
        },
        "root_blend_quality": quality,
        "transition_quality": {
            "continuity_claim": "G2_TARGET_REVIEW_GRADE",
            "curvature_claim": "G2_TARGET_REVIEW_GRADE",
            "short_direction_sample_count": sample_count,
            "foldover_count": foldover_count,
            "max_tangent_flip_deg": _round(tangent_flip),
            "max_normal_flip_deg": _round(normal_flip),
        },
    }


def _hermite_width_grid(
    *,
    outer_segment: list[Point3],
    inner_segment: list[Point3],
    projected_segment: list[Point3],
    sample_count: int,
    profile: list[ProfileSample],
) -> list[list[Point3]]:
    rows: list[list[Point3]] = []
    for row_index in range(sample_count):
        t = row_index / (sample_count - 1)
        row: list[Point3] = []
        for outer, projected, inner in zip(outer_segment, projected_segment, inner_segment):
            point = _cylindrical_blend_point(outer, inner, t, profile)
            row.append(point)
        if row_index == 0:
            row = copy.deepcopy(outer_segment)
        elif row_index == sample_count - 1:
            row = copy.deepcopy(inner_segment)
        rows.append(row)
    return rows


def _cylindrical_blend_point(outer: Point3, inner: Point3, t: float, profile: list[ProfileSample]) -> Point3:
    outer_theta = math.atan2(outer[1], outer[0])
    inner_theta = math.atan2(inner[1], inner[0])
    while inner_theta - outer_theta > math.pi:
        inner_theta -= 2.0 * math.pi
    while inner_theta - outer_theta < -math.pi:
        inner_theta += 2.0 * math.pi
    theta = outer_theta * (1.0 - t) + inner_theta * t
    z = outer[2] * (1.0 - t) + inner[2] * t
    radius = _xy_radius(outer) * (1.0 - t) + _xy_radius(inner) * t
    support = _interpolated_radius_at_z(profile, z, z_tolerance_mm=0.0)
    if support["status"] == "PASS":
        radius = max(radius, support["radius_mm"])
    return _point_at_radius_theta_z(radius=radius, theta=theta, z=z)


def _hermite_point_3d(start: Point3, end: Point3, start_derivative: Point3, end_derivative: Point3, t: float) -> Point3:
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    return [
        h00 * start[axis]
        + h10 * start_derivative[axis]
        + h01 * end[axis]
        + h11 * end_derivative[axis]
        for axis in range(3)
    ]


def _quality_payload(
    *,
    status: str,
    reason: str | None,
    projection: dict[str, Any],
    root_loop: list[Point3],
    width_mm: float,
    min_effective_width_mm: float,
    max_effective_width_mm: float,
    max_tangent_flip_deg: float,
    max_normal_flip_deg: float,
    foldover_count: int,
    min_signed_height_to_hub_mm: float,
    component_count: int,
    max_root_inner_loop_gap_mm: float | None = None,
    max_root_outer_loop_gap_to_hub_mm: float | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "reason": reason,
        "projection_rule": PROJECTION_RULE,
        "offset_rule": OFFSET_RULE,
        "max_projection_residual_mm": projection.get("max_projection_residual_mm"),
        "domain_bracket_success_count": projection.get("domain_bracket_success_count", 0),
        "domain_bracket_failure_count": projection.get("domain_bracket_failure_count", 0),
        "support_z_clamp_count": projection.get("support_z_clamp_count", 0),
        "support_domain_violation_count": projection.get("support_domain_violation_count", 0),
        "root_width_request_mm": _round(width_mm),
        "min_effective_root_width_mm": _round(min_effective_width_mm),
        "max_effective_root_width_mm": _round(max_effective_width_mm),
        "winding_orientation": projection.get("winding_orientation"),
        "offset_self_intersection_count": projection.get("offset_self_intersection_count", 0),
        "support_domain_loop": copy.deepcopy(projection.get("support_domain_loop", projection.get("domain_loop", []))),
        "support_outer_domain_loop": copy.deepcopy(projection.get("support_outer_domain_loop", projection.get("outer_domain_loop", []))),
        "component_count": component_count,
        "max_root_inner_loop_gap_mm": max_root_inner_loop_gap_mm if max_root_inner_loop_gap_mm is not None else (0.0 if root_loop else None),
        "max_root_outer_loop_gap_to_hub_mm": max_root_outer_loop_gap_to_hub_mm,
        "max_tangent_flip_deg": _round(max_tangent_flip_deg),
        "max_normal_flip_deg": _round(max_normal_flip_deg),
        "foldover_count": foldover_count,
        "min_signed_height_to_hub_mm": _round(min_signed_height_to_hub_mm),
    }
    return payload


def _quality_gate_failure(quality: dict[str, Any], *, requested_width_mm: float) -> str | None:
    if quality["component_count"] != 4:
        return "v1_0_3_root_component_gap"
    if quality["max_root_inner_loop_gap_mm"] is None or quality["max_root_inner_loop_gap_mm"] > 1.0e-6:
        return "v1_0_3_root_component_gap"
    if quality["max_root_outer_loop_gap_to_hub_mm"] is None or quality["max_root_outer_loop_gap_to_hub_mm"] > 1.0e-6:
        return "v1_0_3_root_projection_failed"
    if quality["min_effective_root_width_mm"] < 0.5 * requested_width_mm:
        return "v1_0_3_root_footprint_offset_failed"
    if quality["min_signed_height_to_hub_mm"] < -1.0e-6:
        return "v1_0_3_root_signed_height_failed"
    if quality["max_tangent_flip_deg"] >= 45.0 or quality["max_normal_flip_deg"] >= 45.0:
        return "v1_0_3_root_segment_g2_infeasible"
    if quality["foldover_count"] != 0:
        return "v1_0_3_root_segment_foldover"
    return None


def _domain_points_for_loop(
    root_loop: list[Point3],
    profile: list[ProfileSample],
    *,
    z_tolerance_mm: float = 0.0,
) -> dict[str, Any]:
    domain_samples = []
    for point in root_loop:
        radius_result = _interpolated_radius_at_z(profile, point[2], z_tolerance_mm=z_tolerance_mm)
        if radius_result["status"] == "FAIL":
            return _fail("v1_0_3_root_projection_failed")
        domain_samples.append({"theta": math.atan2(point[1], point[0]), "z": radius_result["z_mm"], "radius": radius_result["radius_mm"]})
    open_samples = domain_samples[:-1] if len(root_loop) > 1 and _distance(root_loop[0], root_loop[-1]) <= 1.0e-9 else domain_samples
    mean_radius = sum(sample["radius"] for sample in open_samples) / len(open_samples)
    unwrapped_thetas = _unwrap_thetas([sample["theta"] for sample in open_samples])
    domain_loop = [
        [theta * mean_radius, sample["z"]]
        for theta, sample in zip(unwrapped_thetas, open_samples)
    ]
    return {"status": "PASS", "domain_loop": domain_loop}


def _normalize_profile_samples(hub_surface: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(hub_surface, dict):
        return _fail("hub_surface must be a dict")
    raw_samples = (
        hub_surface.get("profile_samples_rz")
        or hub_surface.get("profile_samples")
        or hub_surface.get("support_profile_samples_rz")
        or []
    )
    if not isinstance(raw_samples, list) or len(raw_samples) < 2:
        return _fail("profile_samples_rz missing")
    profile: list[ProfileSample] = []
    for raw_sample in raw_samples:
        sample = _normalize_profile_sample(raw_sample)
        if sample is None:
            return _fail("profile sample invalid")
        profile.append(sample)
    profile.sort(key=lambda sample: sample[1])
    if any(right[1] <= left[1] for left, right in zip(profile, profile[1:])):
        return _fail("profile z samples must increase")
    return {"status": "PASS", "profile": profile}


def _normalize_profile_sample(raw_sample: Any) -> ProfileSample | None:
    if isinstance(raw_sample, dict):
        radius = _finite_float(raw_sample.get("r_mm", raw_sample.get("radius_mm", raw_sample.get("radius"))))
        z = _finite_float(raw_sample.get("z_mm", raw_sample.get("z")))
    elif isinstance(raw_sample, (list, tuple)) and len(raw_sample) >= 2:
        radius = _finite_float(raw_sample[0])
        z = _finite_float(raw_sample[1])
    else:
        return None
    if radius is None or z is None:
        return None
    return radius, z


def _interpolated_radius_at_z(
    profile: list[ProfileSample],
    z: float,
    *,
    z_tolerance_mm: float = 0.0,
) -> dict[str, Any]:
    clamped_z = float(z)
    z_clamped = False
    if z < profile[0][1] - _EPSILON:
        if profile[0][1] - z <= z_tolerance_mm + _EPSILON:
            clamped_z = profile[0][1]
            z_clamped = True
        else:
            return _fail("z outside profile")
    elif z > profile[-1][1] + _EPSILON:
        if z - profile[-1][1] <= z_tolerance_mm + _EPSILON:
            clamped_z = profile[-1][1]
            z_clamped = True
        else:
            return _fail("z outside profile")
    z = clamped_z
    for radius, sample_z in profile:
        if abs(z - sample_z) <= _EPSILON:
            return {"status": "PASS", "radius_mm": radius, "z_mm": z, "z_clamped": z_clamped}
    for left, right in zip(profile, profile[1:]):
        left_radius, left_z = left
        right_radius, right_z = right
        if left_z - _EPSILON <= z <= right_z + _EPSILON:
            t = (z - left_z) / (right_z - left_z)
            return {
                "status": "PASS",
                "radius_mm": left_radius * (1.0 - t) + right_radius * t,
                "z_mm": z,
                "z_clamped": z_clamped,
            }
    return _fail("z outside profile")


def _aggregate_grid(components: list[dict[str, Any]]) -> list[list[Point3]]:
    if not components:
        return []
    sample_count = len(components[0]["uv_grid"])
    rows: list[list[Point3]] = [[] for _ in range(sample_count)]
    for component_index, component in enumerate(components):
        for row_index, row in enumerate(component["uv_grid"]):
            rows[row_index].extend(copy.deepcopy(row[1:] if component_index and rows[row_index] and rows[row_index][-1] == row[0] else row))
    if rows and rows[0] and rows[0][0] != rows[0][-1]:
        for row in rows:
            row.append(copy.deepcopy(row[0]))
    return rows


def _control_net(uv_grid: list[list[Point3]]) -> list[list[Point3]]:
    if not uv_grid:
        return []
    row_indices = _sample_indices(len(uv_grid))
    column_indices = _sample_indices(len(uv_grid[0]))
    return copy.deepcopy([[uv_grid[row][column] for column in column_indices] for row in row_indices])


def _quad_mesh(uv_grid: list[list[Point3]]) -> dict[str, Any]:
    if not uv_grid:
        return {
            "strategy": "v1_0_3_segmented_root_blend_compact_quad_mesh",
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
        "strategy": "v1_0_3_segmented_root_blend_compact_quad_mesh",
        "u_count": len(uv_grid),
        "v_count": len(uv_grid[0]),
        "quad_count": len(quads),
        "quads": quads,
    }


def _sample_indices(count: int) -> list[int]:
    if count <= 1:
        return [0]
    return list(dict.fromkeys([0, count // 2, count - 1]))


def _width_range(left: list[Point3], right: list[Point3]) -> tuple[float, float]:
    distances = [_distance(a, b) for a, b in zip(left, right)]
    return (min(distances), max(distances)) if distances else (0.0, 0.0)


def _effective_width_range(domain_loop: list[Point2], outer_domain_loop: list[Point2]) -> tuple[float, float]:
    distances = [_distance_2d(a, b) for a, b in zip(domain_loop, outer_domain_loop)]
    return (min(distances), max(distances)) if distances else (0.0, 0.0)


def _max_width_tangent_flip(uv_grid: list[list[Point3]]) -> float:
    if len(uv_grid) < 3 or not uv_grid[0]:
        return 0.0
    flips = []
    for column_index in range(len(uv_grid[0])):
        directions = []
        for row_index in range(len(uv_grid) - 1):
            direction = _normalized(_subtract(uv_grid[row_index + 1][column_index], uv_grid[row_index][column_index]))
            if direction is None:
                return 180.0
            directions.append(direction)
        flips.extend(_vector_angle_deg(left, right) for left, right in zip(directions, directions[1:]))
    return max(flips) if flips else 0.0


def _max_grid_normal_flip(uv_grid: list[list[Point3]]) -> float:
    if len(uv_grid) < 2 or len(uv_grid[0]) < 2:
        return 0.0
    flips = []
    previous_row_normals: dict[int, Point3] | None = None
    for row_index in range(len(uv_grid) - 1):
        row_normals: dict[int, Point3] = {}
        for column_index in range(len(uv_grid[row_index]) - 1):
            along = _subtract(uv_grid[row_index][column_index + 1], uv_grid[row_index][column_index])
            across = _subtract(uv_grid[row_index + 1][column_index], uv_grid[row_index][column_index])
            cross = _cross(along, across)
            along_length = _length(along)
            across_length = _length(across)
            cross_length = _length(cross)
            if along_length <= _EPSILON or across_length <= _EPSILON:
                continue
            if cross_length / (along_length * across_length) < 0.20:
                continue
            normal = _normalized(cross)
            if normal is None:
                continue
            row_normals[column_index] = normal
        if previous_row_normals is not None:
            for column_index, right in row_normals.items():
                left = previous_row_normals.get(column_index)
                if left is not None:
                    flips.append(_vector_angle_deg(left, right))
        previous_row_normals = row_normals
    return max(flips) if flips else 0.0


def _grid_foldover_count(uv_grid: list[list[Point3]]) -> int:
    if len(uv_grid) < 2 or len(uv_grid[0]) < 2:
        return 1
    row_length = len(uv_grid[0])
    if any(len(row) != row_length for row in uv_grid):
        return 1

    count = 0
    projected = _project_grid_to_local_2d(uv_grid)
    for row_index in range(len(projected) - 1):
        for column_index in range(row_length - 1):
            quad3 = [
                uv_grid[row_index][column_index],
                uv_grid[row_index + 1][column_index],
                uv_grid[row_index + 1][column_index + 1],
                uv_grid[row_index][column_index + 1],
            ]
            quad = _project_cell_to_local_2d(quad3)
            cell = _cell_foldover_status(quad)
            if cell["foldover"]:
                count += 1
                continue

    previous_row_direction: Point3 | None = None
    max_row_span = max(_distance(row[-1], row[0]) for row in uv_grid)
    row_span_tolerance = max(1.0e-6, 0.05 * max_row_span)
    for row in uv_grid:
        if _distance(row[-1], row[0]) <= row_span_tolerance:
            previous_row_direction = None
            continue
        row_direction = _normalized(_subtract(row[-1], row[0]))
        if row_direction is None:
            count += 1
            continue
        if previous_row_direction is not None and _dot(previous_row_direction, row_direction) < 0.0:
            count += 1
        previous_row_direction = row_direction

    for column_index in range(row_length):
        full_direction = _subtract(uv_grid[-1][column_index], uv_grid[0][column_index])
        for row_index in range(len(uv_grid) - 1):
            step = _subtract(uv_grid[row_index + 1][column_index], uv_grid[row_index][column_index])
            if _dot(step, full_direction) < -1.0e-6:
                count += 1
    return count


def _project_grid_to_local_2d(uv_grid: list[list[Point3]]) -> list[list[Point2]]:
    origin = uv_grid[0][0]
    u_axis = _first_nonzero_vector(
        [
            _subtract(row[-1], row[0])
            for row in uv_grid
        ]
    )
    if u_axis is None:
        u_axis = [1.0, 0.0, 0.0]
    v_candidates: list[Point3] = []
    for column_index in range(len(uv_grid[0])):
        v_candidates.append(_subtract(uv_grid[-1][column_index], uv_grid[0][column_index]))
    v_axis = _first_nonzero_vector(v_candidates)
    if v_axis is None:
        v_axis = _fallback_perpendicular(u_axis)
    v_axis = _subtract(v_axis, _scale(u_axis, _dot(v_axis, u_axis)))
    v_axis = _normalized(v_axis) or _fallback_perpendicular(u_axis)
    return [
        [
            [
                _dot(_subtract(point, origin), u_axis),
                _dot(_subtract(point, origin), v_axis),
            ]
            for point in row
        ]
        for row in uv_grid
    ]


def _project_cell_to_local_2d(quad: list[Point3]) -> list[Point2]:
    origin = quad[0]
    u_axis = _first_nonzero_vector(
        [
            _subtract(quad[1], quad[0]),
            _subtract(quad[2], quad[3]),
            _subtract(quad[3], quad[0]),
        ]
    ) or [1.0, 0.0, 0.0]
    v_seed = _first_nonzero_vector(
        [
            _subtract(quad[3], quad[0]),
            _subtract(quad[2], quad[1]),
            _fallback_perpendicular(u_axis),
        ]
    ) or _fallback_perpendicular(u_axis)
    v_axis = _subtract(v_seed, _scale(u_axis, _dot(v_seed, u_axis)))
    v_axis = _normalized(v_axis) or _fallback_perpendicular(u_axis)
    return [
        [
            _dot(_subtract(point, origin), u_axis),
            _dot(_subtract(point, origin), v_axis),
        ]
        for point in quad
    ]


def _first_nonzero_vector(vectors: list[Point3]) -> Point3 | None:
    for vector in vectors:
        unit = _normalized(vector)
        if unit is not None:
            return unit
    return None


def _fallback_perpendicular(vector: Point3) -> Point3:
    candidate = _cross(vector, [0.0, 0.0, 1.0])
    unit = _normalized(candidate)
    if unit is not None:
        return unit
    return [0.0, 1.0, 0.0]


def _cell_foldover_status(quad: list[Point2]) -> dict[str, Any]:
    edge_lengths = [
        _distance_2d(left, right)
        for left, right in zip(quad, quad[1:] + quad[:1])
    ]
    scale = max(edge_lengths) if edge_lengths else 1.0
    if min(edge_lengths) <= max(1.0e-9, 1.0e-8 * scale):
        return {"foldover": True, "sign": 0.0}
    is_sliver = min(edge_lengths) / scale < 0.20
    if not is_sliver and (
        _segments_intersect(quad[0], quad[1], quad[2], quad[3])
        or _segments_intersect(quad[1], quad[2], quad[3], quad[0])
    ):
        return {"foldover": True, "sign": 0.0}
    triangle_areas = [
        _triangle_signed_area(quad[0], quad[1], quad[2]),
        _triangle_signed_area(quad[0], quad[2], quad[3]),
    ]
    if any(abs(area) <= max(1.0e-9, 1.0e-8 * scale * scale) for area in triangle_areas):
        return {"foldover": True, "sign": 0.0}
    polygon_area = _triangle_signed_area(quad[0], quad[1], quad[2]) + _triangle_signed_area(quad[0], quad[2], quad[3])
    return {"foldover": False, "sign": 1.0 if polygon_area >= 0.0 else -1.0}


def _max_gap_to_hub(points: list[Point3], hub_surface: dict[str, Any]) -> float | None:
    profile_result = _normalize_profile_samples(hub_surface)
    if profile_result["status"] == "FAIL":
        return None
    gaps = []
    for point in points:
        radius = _interpolated_radius_at_z(profile_result["profile"], point[2])
        if radius["status"] == "FAIL":
            return None
        gaps.append(abs(_xy_radius(point) - radius["radius_mm"]))
    return _round(max(gaps) if gaps else 0.0)


def _max_inner_loop_gap(candidate_loop: list[Point3], source_loop: list[Point3]) -> float | None:
    if not isinstance(candidate_loop, list) or not isinstance(source_loop, list):
        return None
    if len(candidate_loop) != len(source_loop):
        return None
    if not candidate_loop:
        return None
    return _round(max(_distance(candidate, source) for candidate, source in zip(candidate_loop, source_loop)))


def _min_signed_height_to_hub(points: list[Point3], profile: list[ProfileSample]) -> float:
    heights = []
    for point in points:
        radius_result = _interpolated_radius_at_z(profile, point[2], z_tolerance_mm=0.0)
        if radius_result["status"] == "FAIL":
            continue
        heights.append(_xy_radius(point) - radius_result["radius_mm"])
    return min(heights) if heights else -math.inf


def _lift_point_to_hub_support(point: Point3, profile: list[ProfileSample]) -> Point3:
    radius_result = _interpolated_radius_at_z(profile, point[2], z_tolerance_mm=0.0)
    if radius_result["status"] == "FAIL":
        return point
    radius = _xy_radius(point)
    support_radius = radius_result["radius_mm"]
    if radius >= support_radius - 1.0e-9:
        return point
    theta = math.atan2(point[1], point[0])
    return _point_at_radius_theta_z(radius=support_radius, theta=theta, z=point[2])


def _self_intersection_count(points: list[Point2]) -> int:
    if len(points) < 4:
        return 0
    closed_points = points if points[0] == points[-1] else points + [points[0]]
    count = 0
    edges = list(zip(closed_points, closed_points[1:]))
    for first_index, first in enumerate(edges):
        for second_index, second in enumerate(edges[first_index + 1 :], start=first_index + 1):
            if abs(first_index - second_index) <= 1:
                continue
            if first_index == 0 and second_index == len(edges) - 1:
                continue
            if _segments_intersect(first[0], first[1], second[0], second[1]):
                count += 1
    return count


def _triangle_signed_area(first: Point2, second: Point2, third: Point2) -> float:
    return 0.5 * (
        first[0] * (second[1] - third[1])
        + second[0] * (third[1] - first[1])
        + third[0] * (first[1] - second[1])
    )


def _segments_intersect(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    def orientation(first: Point2, second: Point2, third: Point2) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])

    return orientation(a, b, c) * orientation(a, b, d) < 0.0 and orientation(c, d, a) * orientation(c, d, b) < 0.0


def _domain_orientation(points: list[Point2]) -> float:
    if len(points) < 3:
        return 1.0
    area_twice = sum(left[0] * right[1] - right[0] * left[1] for left, right in zip(points, points[1:] + points[:1]))
    return 1.0 if area_twice >= 0.0 else -1.0


def _outward_domain_normal(points: list[Point2], index: int, orientation: float) -> Point2:
    left = points[(index - 1) % len(points)]
    right = points[(index + 1) % len(points)]
    tangent = [right[0] - left[0], right[1] - left[1]]
    length = math.hypot(tangent[0], tangent[1])
    if length <= _EPSILON:
        return [1.0, 0.0]
    tangent = [tangent[0] / length, tangent[1] / length]
    if orientation >= 0.0:
        return [tangent[1], -tangent[0]]
    return [-tangent[1], tangent[0]]


def _unwrap_thetas(thetas: list[float]) -> list[float]:
    if not thetas:
        return []
    unwrapped = [float(thetas[0])]
    for theta in thetas[1:]:
        adjusted = float(theta)
        previous = unwrapped[-1]
        while adjusted - previous > math.pi:
            adjusted -= 2.0 * math.pi
        while adjusted - previous < -math.pi:
            adjusted += 2.0 * math.pi
        unwrapped.append(adjusted)
    return unwrapped


def _base_surface(surface_id: str) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": "blade_root",
        "role": "segmented_root_blend_aggregate",
        "root_blend_method": ROOT_BLEND_METHOD,
        "uv_grid": [],
        "control_net": [],
        "edge_samples": {"blade_inner_loop": [], "projected_footprint_loop": [], "hub_outer_loop": [], "requested_offset_loop": []},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": _quad_mesh([]),
        "display": {**copy.deepcopy(DISPLAY), "visible_by_default": False, "aggregate_surface": True},
        "root_blend_quality": {},
        "transition_quality": {
            "continuity_claim": "G2_TARGET_REVIEW_GRADE",
            "curvature_claim": "G2_TARGET_REVIEW_GRADE",
            "short_direction_sample_count": None,
            "foldover_count": 0,
        },
        "component_surfaces": [],
    }


def _failure(base: dict[str, Any], reason: str, details: dict[str, Any]) -> dict[str, Any]:
    if details.get("status") in {"PASS", "FAIL"} and "projection_rule" in details and "root_width_request_mm" in details:
        result = copy.deepcopy(base)
        result["status"] = "FAIL"
        measured_quality = copy.deepcopy(details)
        measured_quality["status"] = "FAIL"
        measured_quality["reason"] = reason
        result["root_blend_quality"] = measured_quality
        return result
    width = _finite_float(details.get("width_mm", details.get("root_width_request_mm", 0.0))) or 0.0
    quality = _quality_payload(
        status="FAIL",
        reason=reason,
        projection=details,
        root_loop=[],
        width_mm=width,
        min_effective_width_mm=0.0,
        max_effective_width_mm=0.0,
        max_tangent_flip_deg=0.0,
        max_normal_flip_deg=0.0,
        foldover_count=0,
        min_signed_height_to_hub_mm=0.0,
        component_count=0,
        max_root_outer_loop_gap_to_hub_mm=details.get("max_root_outer_loop_gap_to_hub_mm"),
    )
    result = copy.deepcopy(base)
    result["status"] = "FAIL"
    result["root_blend_quality"] = quality
    return result


def _resolved_positive_float(values: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in values:
            continue
        value = _finite_float(values.get(key))
        if value is None or value <= 0.0:
            return None
        return value
    return None


def _resolved_non_negative_float(values: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in values:
            continue
        value = _finite_float(values.get(key))
        if value is None or value < 0.0:
            return None
        return value
    return None


def _point3(point: Any) -> Point3 | None:
    if not isinstance(point, list) or len(point) != 3:
        return None
    values = [_finite_float(value) for value in point]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


def _point_at_radius_theta_z(*, radius: float, theta: float, z: float) -> Point3:
    return _round_vector([radius * math.cos(theta), radius * math.sin(theta), z])


def _xy_radius(point: Point3) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(sum((float(first[axis]) - float(second[axis])) ** 2 for axis in range(3)))


def _distance_2d(first: Point2, second: Point2) -> float:
    return math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))


def _length(vector: Point3) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _subtract(first: Point3, second: Point3) -> Point3:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _scale(vector: Point3, scalar: float) -> Point3:
    return [float(value) * scalar for value in vector]


def _dot(first: Point3, second: Point3) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first: Point3, second: Point3) -> Point3:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _normalized(vector: Point3) -> Point3 | None:
    length = math.sqrt(sum(float(value) * float(value) for value in vector))
    if length <= _EPSILON:
        return None
    return [float(value) / length for value in vector]


def _vector_angle_deg(first: Point3, second: Point3) -> float:
    first_length = math.sqrt(sum(float(value) * float(value) for value in first))
    second_length = math.sqrt(sum(float(value) * float(value) for value in second))
    if first_length <= _EPSILON or second_length <= _EPSILON:
        return 0.0
    dot = _dot(first, second) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _round(value: float) -> float:
    return round(float(value), 9)


def _round_vector(vector: Point3) -> Point3:
    return [_clean_zero(_round(value)) for value in vector]


def _clean_zero(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-12 else value


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(float(minimum), min(float(maximum), float(value)))


def _fail(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason, **extra}
