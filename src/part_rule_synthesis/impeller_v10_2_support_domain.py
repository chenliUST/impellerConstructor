from __future__ import annotations

import math
from typing import Any


Point3 = list[float]
ProfileSample = tuple[float, float]
_EPSILON = 1.0e-9


def offset_loop_on_revolved_support(
    *,
    inner_loop: list[list[float]],
    support_surface: dict[str, Any],
    width_mm: float,
    z_tolerance_mm: float = 0.0,
) -> dict[str, Any]:
    offset_width = _finite_float(width_mm)
    if offset_width is None:
        return _projection_fail("v1_0_2_support_offset_width_invalid", width_mm=width_mm)
    if offset_width < 0.0:
        return _projection_fail("v1_0_2_support_offset_width_negative", width_mm=offset_width)
    z_tolerance = _finite_float(z_tolerance_mm)
    if z_tolerance is None or z_tolerance < 0.0:
        return _projection_fail("v1_0_2_support_z_tolerance_invalid", width_mm=offset_width)

    profile_result = _normalize_profile_samples(support_surface)
    if profile_result["status"] == "FAIL":
        return _projection_fail(profile_result["reason"], width_mm=offset_width)
    profile = profile_result["profile_samples_rz"]

    requested_offset_loop: list[Point3] = []
    projected_loop: list[Point3] = []
    max_residual = 0.0
    max_requested_offset = 0.0
    violation_count = 0
    z_clamp_count = 0
    source_samples: list[dict[str, float]] = []

    for point in inner_loop:
        normalized_point = _point3(point)
        if normalized_point is None:
            return _projection_fail("v1_0_2_support_inner_loop_point_invalid", width_mm=offset_width)
        x, y, z = normalized_point
        radius_result = _interpolated_radius_at_z(profile, z, z_tolerance_mm=z_tolerance)
        if radius_result["status"] == "FAIL":
            violation_count += 1
            requested_offset_loop.append([x, y, z])
            projected_loop.append([x, y, z])
            continue

        if radius_result.get("z_clamped"):
            z_clamp_count += 1
        source_samples.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "theta": math.atan2(y, x),
                "support_z": radius_result["z_mm"],
                "support_radius": radius_result["radius_mm"],
            }
        )

    if violation_count == 0:
        closed_source_loop = (
            len(source_samples) > 1
            and _sample_points_close(source_samples[0], source_samples[-1])
        )
        domain_samples = source_samples[:-1] if closed_source_loop else source_samples
        mean_radius = _mean([sample["support_radius"] for sample in domain_samples]) or 1.0
        unwrapped_thetas = _unwrap_thetas([sample["theta"] for sample in domain_samples])
        domain_loop = [
            [theta * mean_radius, sample["support_z"]]
            for theta, sample in zip(unwrapped_thetas, domain_samples)
        ]
        orientation = _domain_orientation(domain_loop)
        min_z = profile[0][1]
        max_z = profile[-1][1]
        for index, sample in enumerate(domain_samples):
            domain_point = domain_loop[index]
            normal = _outward_domain_normal(
                domain_loop,
                index,
                orientation,
                closed=closed_source_loop,
            )
            requested_domain = [
                domain_point[0] + normal[0] * offset_width,
                domain_point[1] + normal[1] * offset_width,
            ]
            projected_z = _clamp(requested_domain[1], min_z, max_z)
            if abs(projected_z - requested_domain[1]) > _EPSILON:
                z_clamp_count += 1
            radius_result = _interpolated_radius_at_z(profile, projected_z)
            target_radius = radius_result["radius_mm"]
            theta = requested_domain[0] / mean_radius
            projected = _point_at_radius_theta_z(
                radius=target_radius,
                theta=theta,
                z=projected_z,
            )
            requested_offset_loop.append(projected)
            projected_loop.append(projected)
            max_requested_offset = max(max_requested_offset, offset_width)
            max_residual = max(max_residual, abs(_xy_radius(projected) - target_radius))
        if closed_source_loop and projected_loop:
            requested_offset_loop.append(list(requested_offset_loop[0]))
            projected_loop.append(list(projected_loop[0]))

    result = {
        "status": "PASS" if violation_count == 0 else "FAIL",
        "requested_offset_loop": requested_offset_loop,
        "projected_loop": projected_loop,
        "outer_loop": projected_loop,
        "support_surface_id": support_surface.get("id"),
        "offset_width_request_mm": _round(offset_width),
        "width_application_mode": "closed_footprint_outward_offset_in_revolved_support_domain",
        "max_requested_offset_applied_mm": _round(max_requested_offset),
        "max_projection_residual_mm": _round(max_residual),
        "support_domain_violation_count": violation_count,
        "support_z_clamp_count": z_clamp_count,
        "z_tolerance_mm": _round(z_tolerance),
        "profile_z_bounds_mm": [_round(profile[0][1]), _round(profile[-1][1])],
    }
    if violation_count:
        result["reason"] = "v1_0_2_support_domain_violation"
        result["failure_reason"] = result["reason"]
    return result


def validate_preset_feasibility(
    *,
    blade_count: int,
    blade_thickness_mm: float,
    root_attachment_width_mm: float,
    root_attachment_lift_mm: float,
    tip_attachment_width_mm: float,
    tip_attachment_lift_mm: float,
    root_attachment_mean_radius_mm: float,
    hub_wall_thickness_mm: float,
    hub_bottom_thickness_mm: float,
    hood_wall_thickness_mm: float,
    closed: bool,
) -> dict[str, Any]:
    numeric_inputs = {
        "blade_thickness_mm": blade_thickness_mm,
        "root_attachment_width_mm": root_attachment_width_mm,
        "root_attachment_lift_mm": root_attachment_lift_mm,
        "tip_attachment_width_mm": tip_attachment_width_mm,
        "tip_attachment_lift_mm": tip_attachment_lift_mm,
        "root_attachment_mean_radius_mm": root_attachment_mean_radius_mm,
        "hub_wall_thickness_mm": hub_wall_thickness_mm,
        "hub_bottom_thickness_mm": hub_bottom_thickness_mm,
        "hood_wall_thickness_mm": hood_wall_thickness_mm,
    }
    values = {name: _finite_float(value) for name, value in numeric_inputs.items()}

    reasons: list[str] = []
    count = _integer_blade_count(blade_count)
    if count is None:
        reasons.append("v1_0_2_preset_blade_count_invalid")
    if any(value is None for value in values.values()):
        reasons.append("v1_0_2_preset_numeric_input_invalid")

    minimum_required_pitch = None
    pitch = None
    minimum_pitch_margin = None

    if reasons:
        margins = {
            "blade_count_minimum_margin": count - 2 if count is not None else None,
            "minimum_pitch_margin_mm": None,
            "hub_material_margin_mm": None,
            "hub_bottom_margin_mm": None,
        }
        not_applicable_constraints = _not_applicable_constraints(closed)
        if closed:
            margins["shroud_material_margin_mm"] = None
        return _feasibility_result(
            reasons=reasons,
            margins=margins,
            not_applicable_constraints=not_applicable_constraints,
            pitch_mm=None,
            minimum_required_pitch_mm=None,
        )

    blade_thickness = values["blade_thickness_mm"]
    root_width = values["root_attachment_width_mm"]
    root_lift = values["root_attachment_lift_mm"]
    tip_lift = values["tip_attachment_lift_mm"]
    root_mean_radius = values["root_attachment_mean_radius_mm"]
    hub_wall = values["hub_wall_thickness_mm"]
    hub_bottom = values["hub_bottom_thickness_mm"]
    hood_wall = values["hood_wall_thickness_mm"]

    minimum_required_pitch = 1.15 * (blade_thickness + 2.0 * root_width)
    if count < 2:
        reasons.append("v1_0_2_preset_blade_count_below_minimum_two")
    else:
        pitch = 2.0 * math.pi * root_mean_radius / count
        minimum_pitch_margin = pitch - minimum_required_pitch
        if minimum_pitch_margin < 0.0:
            reasons.append("v1_0_2_preset_blade_pitch_insufficient")

    hub_material_margin = hub_wall - (root_lift + 0.25 * blade_thickness)
    hub_bottom_margin = hub_bottom - max(0.30 * root_width, 8.0)
    if hub_material_margin < 0.0:
        reasons.append("v1_0_2_preset_hub_material_insufficient")
    if hub_bottom_margin < 0.0:
        reasons.append("v1_0_2_preset_hub_bottom_material_insufficient")

    margins = {
        "blade_count_minimum_margin": count - 2,
        "minimum_pitch_margin_mm": _round_or_none(minimum_pitch_margin),
        "hub_material_margin_mm": _round(hub_material_margin),
        "hub_bottom_margin_mm": _round(hub_bottom_margin),
    }
    not_applicable_constraints = _not_applicable_constraints(closed)
    if closed:
        shroud_margin = hood_wall - (tip_lift + 0.15 * blade_thickness)
        margins["shroud_material_margin_mm"] = _round(shroud_margin)
        if shroud_margin < 0.0:
            reasons.append("v1_0_2_preset_shroud_material_insufficient")

    return _feasibility_result(
        reasons=reasons,
        margins=margins,
        not_applicable_constraints=not_applicable_constraints,
        pitch_mm=_round_or_none(pitch),
        minimum_required_pitch_mm=_round_or_none(minimum_required_pitch),
    )


def _normalize_profile_samples(support_surface: dict[str, Any]) -> dict[str, Any]:
    raw_samples = (
        support_surface.get("profile_samples_rz")
        or support_surface.get("profile_samples")
        or support_surface.get("support_profile_samples_rz")
        or []
    )
    if not isinstance(raw_samples, list) or not raw_samples:
        return _fail("v1_0_2_support_profile_samples_missing")

    samples: list[ProfileSample] = []
    for raw_sample in raw_samples:
        sample = _normalize_profile_sample(raw_sample)
        if sample is None:
            return _fail("v1_0_2_support_profile_sample_invalid")
        samples.append(sample)

    samples.sort(key=lambda sample: sample[1])
    return {
        "status": "PASS",
        "profile_samples_rz": samples,
    }


def _normalize_profile_sample(raw_sample: Any) -> ProfileSample | None:
    if isinstance(raw_sample, dict):
        radius = _finite_float(
            raw_sample.get("r_mm", raw_sample.get("radius_mm", raw_sample.get("radius")))
        )
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
    clamped_z = z
    z_clamped = False
    if z < profile[0][1] - _EPSILON:
        if profile[0][1] - z <= z_tolerance_mm + _EPSILON:
            clamped_z = profile[0][1]
            z_clamped = True
        else:
            return _fail("v1_0_2_support_z_outside_profile_domain")
    elif z > profile[-1][1] + _EPSILON:
        if z - profile[-1][1] <= z_tolerance_mm + _EPSILON:
            clamped_z = profile[-1][1]
            z_clamped = True
        else:
            return _fail("v1_0_2_support_z_outside_profile_domain")

    z = clamped_z
    if z < profile[0][1] - _EPSILON or z > profile[-1][1] + _EPSILON:
        return _fail("v1_0_2_support_z_outside_profile_domain")
    for radius, sample_z in profile:
        if abs(z - sample_z) <= _EPSILON:
            return {
                "status": "PASS",
                "radius_mm": radius,
                "z_mm": z,
                "z_clamped": z_clamped,
            }
    for left, right in zip(profile, profile[1:]):
        left_radius, left_z = left
        right_radius, right_z = right
        if left_z - _EPSILON <= z <= right_z + _EPSILON:
            if abs(right_z - left_z) <= _EPSILON:
                return {
                    "status": "PASS",
                    "radius_mm": right_radius,
                }
            t = (z - left_z) / (right_z - left_z)
            return {
                "status": "PASS",
                "radius_mm": left_radius * (1.0 - t) + right_radius * t,
                "z_mm": z,
                "z_clamped": z_clamped,
            }
    return _fail("v1_0_2_support_z_outside_profile_domain")


def _feasibility_result(
    *,
    reasons: list[str],
    margins: dict[str, float | int | None],
    not_applicable_constraints: dict[str, str],
    pitch_mm: float | None,
    minimum_required_pitch_mm: float | None,
) -> dict[str, Any]:
    return {
        "preset_feasibility_status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "preset_default_violation_count": len(reasons),
        "blade_pitch_mm": pitch_mm,
        "minimum_required_pitch_mm": minimum_required_pitch_mm,
        "resolved_support_domain_margins": margins,
        "not_applicable_constraints": not_applicable_constraints,
    }


def _not_applicable_constraints(closed: bool) -> dict[str, str]:
    if closed:
        return {}
    return {
        "closed_shroud_material_supports_tip_attachment_lift": "open_impeller_has_no_front_shroud_material"
    }


def _point3(point: Any) -> Point3 | None:
    if not isinstance(point, list) or len(point) < 3:
        return None
    coordinates = [_finite_float(point[axis]) for axis in range(3)]
    if any(value is None for value in coordinates):
        return None
    return [float(value) for value in coordinates]


def _xy_radius(point: Point3) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)


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


def _domain_orientation(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 1.0
    area_twice = 0.0
    for left, right in zip(points, points[1:] + points[:1]):
        area_twice += left[0] * right[1] - right[0] * left[1]
    return 1.0 if area_twice >= 0.0 else -1.0


def _sample_points_close(left: dict[str, float], right: dict[str, float]) -> bool:
    return (
        abs(left["x"] - right["x"]) <= _EPSILON
        and abs(left["y"] - right["y"]) <= _EPSILON
        and abs(left["z"] - right["z"]) <= _EPSILON
    )


def _outward_domain_normal(
    points: list[list[float]],
    index: int,
    orientation: float,
    *,
    closed: bool = False,
) -> list[float]:
    if len(points) < 2:
        return [1.0, 0.0]
    if closed and len(points) > 2:
        left = points[(index - 1) % len(points)]
        right = points[(index + 1) % len(points)]
    else:
        left = points[max(index - 1, 0)] if index == 0 else points[index - 1]
        right = points[min(index + 1, len(points) - 1)] if index == len(points) - 1 else points[index + 1]
    tangent = [right[0] - left[0], right[1] - left[1]]
    length = math.hypot(tangent[0], tangent[1])
    if length <= _EPSILON:
        return [1.0, 0.0]
    tangent = [tangent[0] / length, tangent[1] / length]
    if orientation >= 0.0:
        return [-tangent[1], tangent[0]]
    return [tangent[1], -tangent[0]]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(float(minimum), min(float(maximum), float(value)))


def _requested_tangential_support_offset(
    *,
    radius: float,
    theta: float,
    z: float,
    width_mm: float,
) -> tuple[Point3, float]:
    if radius <= _EPSILON or width_mm <= 0.0:
        return _point_at_radius_theta_z(radius=radius, theta=theta, z=z), 0.0
    bounded_width = min(width_mm, 0.25 * 2.0 * math.pi * radius)
    requested_theta = theta + bounded_width / radius
    return _point_at_radius_theta_z(radius=radius, theta=requested_theta, z=z), bounded_width


def _point_at_radius_theta_z(
    *,
    radius: float,
    theta: float,
    z: float,
) -> Point3:
    return _round_vector([radius * math.cos(theta), radius * math.sin(theta), z])


def _integer_blade_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return _round(value)


def _round(value: float) -> float:
    return round(float(value), 9)


def _round_vector(vector: Point3) -> Point3:
    return [_clean_zero(_round(value)) for value in vector]


def _clean_zero(value: float) -> float:
    if abs(value) <= 1.0e-12:
        return 0.0
    return value


def _projection_fail(reason: str, *, width_mm: Any) -> dict[str, Any]:
    width = _finite_float(width_mm)
    return {
        "status": "FAIL",
        "reason": reason,
        "failure_reason": reason,
        "requested_offset_loop": [],
        "projected_loop": [],
        "outer_loop": [],
        "offset_width_request_mm": _round(width) if width is not None else width_mm,
        "max_projection_residual_mm": None,
        "support_domain_violation_count": 0,
    }


def _fail(reason: str) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "reason": reason,
    }
