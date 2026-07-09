from __future__ import annotations

import copy
import math
from typing import Any

from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface
from part_rule_synthesis.impeller_v10_2_support_domain import offset_loop_on_revolved_support


Point3 = list[float]
Frame = dict[str, list[float]]
_EPSILON = 1.0e-9


def build_v10_2_root_attachment_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    return _build_v10_2_support_attachment_surface(
        blade_index=blade_index,
        lattice=lattice,
        support_surface=hub_surface,
        defaults=defaults,
        inner_loop_key="blade_exterior_root_loop",
        width_keys=("resolved_root_attachment_width_mm", "root_attachment_width_mm"),
        lift_keys=("resolved_root_attachment_lift_mm", "root_attachment_lift_mm"),
        width_invalid_reason="v1_0_2_root_attachment_width_invalid",
        lift_invalid_reason="v1_0_2_root_attachment_lift_invalid",
        sample_count_invalid_reason="v1_0_2_root_attachment_sample_count_invalid",
        inner_loop_missing_reason="v1_0_2_root_attachment_inner_loop_missing",
        projection_failed_reason="v1_0_2_root_attachment_projection_failed",
        surface_id=f"blade_{blade_index}_root_annular_surface",
        face_family="blade_root",
        role="root_pedestal_ring_surface",
        topology_key="root_topology",
        review_grade_geometry_note="review-grade G2-target curved annular root-to-hub attachment surface",
        outer_loop_edge_key="hub_outer_loop",
        display={
            "inspection_class": "root_to_hub_native_root_face",
            "color": "#ff00cc",
            "wire_color": "#fff200",
        },
        outer_loop_gap_quality_key="outer_loop_max_gap_to_hub_surface_mm",
        width_quality_key="root_attachment_width_mm",
        lift_quality_key="root_attachment_lift_mm",
        measurement_shared_edge_key="root_attachment",
        radius_keys=("resolved_root_fillet_radius_mm", "root_fillet_radius_mm"),
        component_segment_specs=[
            ("pressure_root", "pressure_root_loop", False),
            ("trailing_root_cap", "root_trailing_cap", False),
            ("suction_root", "suction_root_loop", True),
            ("leading_root_cap", "root_leading_cap", True),
        ],
    )


def build_v10_2_tip_attachment_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    shroud_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    return _build_v10_2_support_attachment_surface(
        blade_index=blade_index,
        lattice=lattice,
        support_surface=shroud_surface,
        defaults=defaults,
        inner_loop_key="blade_exterior_tip_loop",
        width_keys=("resolved_tip_attachment_width_mm", "tip_attachment_width_mm"),
        lift_keys=("resolved_tip_attachment_lift_mm", "tip_attachment_lift_mm"),
        width_invalid_reason="v1_0_2_tip_attachment_width_invalid",
        lift_invalid_reason="v1_0_2_tip_attachment_lift_invalid",
        sample_count_invalid_reason="v1_0_2_tip_attachment_sample_count_invalid",
        inner_loop_missing_reason="v1_0_2_tip_attachment_inner_loop_missing",
        projection_failed_reason="v1_0_2_tip_attachment_projection_failed",
        surface_id=f"blade_{blade_index}_tip_surface",
        face_family="blade_tip",
        role="tip_to_shroud_attachment_surface",
        topology_key="tip_topology",
        review_grade_geometry_note="review-grade G2-target curved annular tip-to-shroud attachment surface",
        outer_loop_edge_key="shroud_outer_loop",
        display={
            "inspection_class": "tip_to_shroud_attachment",
            "color": "#00e5ff",
            "wire_color": "#fff200",
        },
        outer_loop_gap_quality_key="outer_loop_max_gap_to_shroud_surface_mm",
        width_quality_key="tip_attachment_width_mm",
        lift_quality_key="tip_attachment_lift_mm",
        measurement_shared_edge_key="tip_attachment",
        radius_keys=("resolved_tip_edge_radius_mm", "tip_edge_radius_mm"),
        component_segment_specs=[
            ("pressure_tip", "pressure_tip_loop", False),
            ("trailing_tip_cap", "tip_trailing_cap", False),
            ("suction_tip", "suction_tip_loop", True),
            ("leading_tip_cap", "tip_leading_cap", True),
        ],
    )


def _build_v10_2_support_attachment_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    support_surface: dict[str, Any],
    defaults: dict[str, Any],
    inner_loop_key: str,
    width_keys: tuple[str, str],
    lift_keys: tuple[str, str],
    width_invalid_reason: str,
    lift_invalid_reason: str,
    sample_count_invalid_reason: str,
    inner_loop_missing_reason: str,
    projection_failed_reason: str,
    surface_id: str,
    face_family: str,
    role: str,
    topology_key: str,
    review_grade_geometry_note: str,
    outer_loop_edge_key: str,
    display: dict[str, str],
    outer_loop_gap_quality_key: str,
    width_quality_key: str,
    lift_quality_key: str,
    measurement_shared_edge_key: str,
    radius_keys: tuple[str, str],
    component_segment_specs: list[tuple[str, str, bool]] | None,
) -> dict[str, Any]:
    inner_loop = lattice.get("closed_loops", {}).get(inner_loop_key)
    failure_inner_loop = inner_loop if isinstance(inner_loop, list) else []
    width_mm = _resolved_required_positive_float(
        defaults,
        *width_keys,
    )
    lift_mm = _resolved_required_positive_float(
        defaults,
        *lift_keys,
    )
    sample_count = _resolved_attachment_sample_count(defaults)

    if width_mm is None:
        return _failure_attachment_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            topology_key=topology_key,
            outer_loop_edge_key=outer_loop_edge_key,
            display=display,
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
            measurement_shared_edge_key=measurement_shared_edge_key,
            inner_loop=failure_inner_loop,
            projection={},
            width_mm=_resolved_report_float(
                defaults,
                *width_keys,
            ),
            lift_mm=_resolved_report_float(
                defaults,
                *lift_keys,
            ),
            reason=width_invalid_reason,
        )

    if lift_mm is None:
        return _failure_attachment_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            topology_key=topology_key,
            outer_loop_edge_key=outer_loop_edge_key,
            display=display,
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
            measurement_shared_edge_key=measurement_shared_edge_key,
            inner_loop=failure_inner_loop,
            projection={},
            width_mm=width_mm,
            lift_mm=_resolved_report_float(
                defaults,
                *lift_keys,
            ),
            reason=lift_invalid_reason,
        )

    if sample_count is None:
        return _failure_attachment_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            topology_key=topology_key,
            outer_loop_edge_key=outer_loop_edge_key,
            display=display,
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
            measurement_shared_edge_key=measurement_shared_edge_key,
            inner_loop=failure_inner_loop,
            projection={},
            width_mm=width_mm,
            lift_mm=lift_mm,
            reason=sample_count_invalid_reason,
        )

    if not isinstance(inner_loop, list) or len(inner_loop) < 2:
        return _failure_attachment_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            topology_key=topology_key,
            outer_loop_edge_key=outer_loop_edge_key,
            display=display,
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
            measurement_shared_edge_key=measurement_shared_edge_key,
            inner_loop=[],
            projection={},
            width_mm=width_mm,
            lift_mm=lift_mm,
            reason=inner_loop_missing_reason,
        )

    projection = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=support_surface,
        width_mm=width_mm,
        z_tolerance_mm=lift_mm,
    )
    if projection.get("status") != "PASS":
        return _failure_attachment_surface(
            surface_id=surface_id,
            face_family=face_family,
            role=role,
            topology_key=topology_key,
            outer_loop_edge_key=outer_loop_edge_key,
            display=display,
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
            measurement_shared_edge_key=measurement_shared_edge_key,
            inner_loop=inner_loop,
            projection=projection,
            width_mm=width_mm,
            lift_mm=lift_mm,
            reason=str(projection.get("reason", projection_failed_reason)),
        )

    outer_loop = projection["outer_loop"]
    outer_frames = _frames_from_loop_pair(outer_loop, inner_loop)
    inner_frames = _frames_from_loop_pair(inner_loop, outer_loop)
    radius_mm = _resolved_radius(defaults, width_mm, *radius_keys)

    surface = build_v10_2_g2_edge_surface(
        surface_id=surface_id,
        face_family=face_family,
        role=role,
        pressure_frames=outer_frames,
        suction_frames=inner_frames,
        radius_mm=radius_mm,
        sample_count=sample_count,
    )
    surface[topology_key] = "support_domain_annular_attachment_boss"
    surface["review_grade_geometry_note"] = review_grade_geometry_note
    surface["edge_samples"].update(
        {
            outer_loop_edge_key: copy.deepcopy(outer_loop),
            "blade_inner_loop": copy.deepcopy(inner_loop),
            "requested_offset_loop": copy.deepcopy(projection.get("requested_offset_loop", [])),
        }
    )
    surface["display"] = {**copy.deepcopy(display), "visible_by_default": False, "aggregate_surface": True}
    surface["attachment_quality"] = _attachment_quality(
        projection=projection,
        width_mm=width_mm,
        lift_mm=lift_mm,
        support_domain_collapse_count=_support_domain_collapse_count(inner_loop, outer_loop),
        g2_builder_foldover_count=surface["transition_quality"]["foldover_count"],
        outer_loop_gap_quality_key=outer_loop_gap_quality_key,
        width_quality_key=width_quality_key,
        lift_quality_key=lift_quality_key,
    )
    surface["component_surfaces"] = _build_component_attachment_surfaces(
        parent_surface_id=surface_id,
        face_family=face_family,
        role=role,
        topology_key=topology_key,
        topology_value="support_domain_annular_attachment_boss",
        outer_loop_edge_key=outer_loop_edge_key,
        support_surface=support_surface,
        lattice=lattice,
        component_segment_specs=component_segment_specs or [],
        width_mm=width_mm,
        lift_mm=lift_mm,
        radius_mm=radius_mm,
        sample_count=sample_count,
        display=display,
        review_grade_geometry_note=review_grade_geometry_note,
        outer_loop_gap_quality_key=outer_loop_gap_quality_key,
        width_quality_key=width_quality_key,
        lift_quality_key=lift_quality_key,
    )
    return surface


def _build_component_attachment_surfaces(
    *,
    parent_surface_id: str,
    face_family: str,
    role: str,
    topology_key: str,
    topology_value: str,
    outer_loop_edge_key: str,
    support_surface: dict[str, Any],
    lattice: dict[str, Any],
    component_segment_specs: list[tuple[str, str, bool]],
    width_mm: float,
    lift_mm: float,
    radius_mm: float,
    sample_count: int,
    display: dict[str, str],
    review_grade_geometry_note: str,
    outer_loop_gap_quality_key: str,
    width_quality_key: str,
    lift_quality_key: str,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    loops = lattice.get("loops", {})
    for segment_name, loop_key, reverse_loop in component_segment_specs:
        raw_loop = loops.get(loop_key)
        if not isinstance(raw_loop, list) or len(raw_loop) < 2:
            continue
        inner_loop = copy.deepcopy(list(reversed(raw_loop)) if reverse_loop else raw_loop)
        projection = offset_loop_on_revolved_support(
            inner_loop=inner_loop,
            support_surface=support_surface,
            width_mm=width_mm,
            z_tolerance_mm=lift_mm,
        )
        if projection.get("status") != "PASS":
            continue
        outer_loop = projection["outer_loop"]
        component = build_v10_2_g2_edge_surface(
            surface_id=f"{parent_surface_id}_{segment_name}_patch",
            face_family=face_family,
            role=f"{role}_{segment_name}_patch",
            pressure_frames=_frames_from_loop_pair(outer_loop, inner_loop),
            suction_frames=_frames_from_loop_pair(inner_loop, outer_loop),
            radius_mm=_component_attachment_radius(radius_mm, width_mm, segment_name),
            sample_count=sample_count,
        )
        component[topology_key] = topology_value
        component["component_of"] = parent_surface_id
        component["component_segment"] = segment_name
        component["review_grade_geometry_note"] = review_grade_geometry_note
        component["edge_samples"].update(
            {
                outer_loop_edge_key: copy.deepcopy(outer_loop),
                "blade_inner_loop": copy.deepcopy(inner_loop),
                "requested_offset_loop": copy.deepcopy(projection.get("requested_offset_loop", [])),
            }
        )
        component["display"] = {
            **copy.deepcopy(display),
            "aggregate_surface": False,
            "component_of": parent_surface_id,
            "component_segment": segment_name,
        }
        component["attachment_quality"] = _attachment_quality(
            projection=projection,
            width_mm=width_mm,
            lift_mm=lift_mm,
            support_domain_collapse_count=_support_domain_collapse_count(inner_loop, outer_loop),
            g2_builder_foldover_count=component["transition_quality"]["foldover_count"],
            outer_loop_gap_quality_key=outer_loop_gap_quality_key,
            width_quality_key=width_quality_key,
            lift_quality_key=lift_quality_key,
        )
        components.append(component)
    return components


def _component_attachment_radius(radius_mm: float, width_mm: float, segment_name: str) -> float:
    if "cap" not in segment_name:
        return radius_mm
    return min(radius_mm, max(1.0, 0.15 * width_mm))


def _failure_attachment_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    topology_key: str,
    outer_loop_edge_key: str,
    display: dict[str, str],
    outer_loop_gap_quality_key: str,
    width_quality_key: str,
    lift_quality_key: str,
    measurement_shared_edge_key: str,
    inner_loop: list[Point3],
    projection: dict[str, Any],
    width_mm: float,
    lift_mm: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        topology_key: "support_domain_annular_attachment_boss",
        "uv_grid": [],
        "control_net": [],
        "edge_samples": {
            outer_loop_edge_key: copy.deepcopy(projection.get("outer_loop", [])),
            "blade_inner_loop": copy.deepcopy(inner_loop),
            "requested_offset_loop": copy.deepcopy(projection.get("requested_offset_loop", [])),
        },
        "transition_quality": {
            "continuity_claim": "G2_TARGET_REVIEW_GRADE",
            "curvature_claim": "G2_TARGET_REVIEW_GRADE",
            "short_direction_sample_count": None,
            "foldover_count": 0,
            "g2_measurement_status_by_shared_edge": {
                measurement_shared_edge_key: "NOT_BUILT_PROJECTION_FAILED",
            },
        },
        "display": copy.deepcopy(display),
        "attachment_quality": {
            "status": "FAIL",
            "reason": reason,
            "projection_reason": projection.get("reason", reason),
            "inner_loop_max_gap_to_blade_faces_mm": 0.0 if inner_loop else None,
            outer_loop_gap_quality_key: projection.get("max_projection_residual_mm"),
            width_quality_key: _round(width_mm),
            lift_quality_key: _round(lift_mm),
            "support_domain_violation_count": projection.get("support_domain_violation_count", 0),
            "foldover_count": 0,
            "support_domain_collapse_count": _failure_support_domain_collapse_count(inner_loop, projection),
            "g2_builder_global_reference_foldover_count": 0,
        },
    }


def _frames_from_loop_pair(loop: list[Point3], opposite_loop: list[Point3]) -> list[Frame]:
    frames = []
    previous_normal: Point3 | None = None
    for index, point in enumerate(loop):
        tangent = _normalized(_finite_difference(loop, index)) or [1.0, 0.0, 0.0]
        cross_tangent = _normalized(_subtract(_sample(opposite_loop, index), point))
        if cross_tangent is None:
            cross_tangent = _fallback_cross_tangent(tangent)
        normal = _normalized(_cross(tangent, cross_tangent)) or _fallback_normal(tangent, cross_tangent)
        if previous_normal is not None and _dot(normal, previous_normal) < 0.0:
            normal = _scale(normal, -1.0)
        previous_normal = normal
        curvature_proxy = _normalized(_second_difference(loop, index)) or normal
        frames.append(
            {
                "point": copy.deepcopy(point),
                "edge_tangent": _round_vector(tangent),
                "cross_edge_tangent": _round_vector(cross_tangent),
                "material_normal": _round_vector(normal),
                "curvature_proxy": _round_vector(curvature_proxy),
            }
        )
    return frames


def _attachment_quality(
    *,
    projection: dict[str, Any],
    width_mm: float,
    lift_mm: float,
    support_domain_collapse_count: int,
    g2_builder_foldover_count: int,
    outer_loop_gap_quality_key: str,
    width_quality_key: str,
    lift_quality_key: str,
) -> dict[str, Any]:
    return {
        "status": "PASS",
        "projection_status": projection.get("status"),
        "inner_loop_max_gap_to_blade_faces_mm": 0.0,
        outer_loop_gap_quality_key: projection.get("max_projection_residual_mm"),
        width_quality_key: _round(width_mm),
        lift_quality_key: _round(lift_mm),
        "support_domain_violation_count": projection.get("support_domain_violation_count", 0),
        "foldover_count": 0,
        "support_domain_collapse_count": support_domain_collapse_count,
        "g2_builder_global_reference_foldover_count": g2_builder_foldover_count,
        "support_surface_id": projection.get("support_surface_id"),
        "offset_width_request_mm": projection.get("offset_width_request_mm"),
        "max_requested_offset_applied_mm": projection.get("max_requested_offset_applied_mm"),
    }


def _support_domain_collapse_count(inner_loop: list[Point3], outer_loop: list[Point3]) -> int:
    if len(inner_loop) != len(outer_loop):
        return 1
    collapses = 0
    for inner_point, outer_point in zip(inner_loop, outer_loop):
        if _length(_subtract(outer_point, inner_point)) <= _EPSILON:
            collapses += 1
    return collapses


def _failure_support_domain_collapse_count(inner_loop: list[Point3], projection: dict[str, Any]) -> int:
    outer_loop = projection.get("outer_loop", [])
    if not outer_loop:
        return 0
    return _support_domain_collapse_count(inner_loop, outer_loop)


def _resolved_radius(defaults: dict[str, Any], width_mm: float, *keys: str) -> float:
    for key in keys:
        value = _finite_float(defaults.get(key))
        if value is not None and value >= 0.0:
            return value
    return width_mm


def _resolved_required_positive_float(defaults: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in defaults:
            continue
        value = _finite_float(defaults.get(key))
        if value is None or value <= 0.0:
            return None
        return value
    return None


def _resolved_report_float(defaults: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = _finite_float(defaults.get(key))
        if value is not None:
            return value
    return 0.0


def _resolved_attachment_sample_count(defaults: dict[str, Any]) -> int | None:
    value = defaults.get("attachment_short_direction_sample_count", 17)
    if type(value) is not int or value < 17:
        return None
    return value


def _sample(points: list[Point3], index: int) -> Point3:
    if not points:
        return [0.0, 0.0, 0.0]
    return points[min(index, len(points) - 1)]


def _finite_difference(points: list[Point3], index: int) -> Point3:
    if len(points) == 1:
        return [0.0, 0.0, 0.0]
    if index == 0:
        return _subtract(points[1], points[0])
    if index == len(points) - 1:
        return _subtract(points[-1], points[-2])
    return _subtract(points[index + 1], points[index - 1])


def _second_difference(points: list[Point3], index: int) -> Point3:
    if len(points) < 3:
        return [0.0, 0.0, 0.0]
    left = points[max(index - 1, 0)]
    center = points[index]
    right = points[min(index + 1, len(points) - 1)]
    return [
        float(left[axis]) - 2.0 * float(center[axis]) + float(right[axis])
        for axis in range(3)
    ]


def _fallback_cross_tangent(edge_tangent: Point3) -> Point3:
    radial = _normalized([edge_tangent[1], -edge_tangent[0], 0.0])
    if radial is not None:
        return radial
    return [0.0, 1.0, 0.0]


def _fallback_normal(edge_tangent: Point3, cross_edge_tangent: Point3) -> Point3:
    normal = _normalized(_cross(edge_tangent, _fallback_cross_tangent(cross_edge_tangent)))
    if normal is not None:
        return normal
    return [0.0, 0.0, 1.0]


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


def _length(vector: Point3) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _normalized(vector: Point3) -> Point3 | None:
    length = _length(vector)
    if length <= _EPSILON:
        return None
    return [float(value) / length for value in vector]


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
    return [_round(value) for value in vector]
