from __future__ import annotations

import math
from typing import Any


SURFACE_U_COUNT = 41
SURFACE_V_COUNT = 33
BLADE_U_COUNT = 41
BLADE_V_COUNT = 17
ROUND_DIGITS = 6
CONSTRUCTION_SEQUENCE = [
    "1. Establish the shaft coordinate system: Z is the rotation axis and all meridional profiles are defined in the R-Z plane.",
    "2. Define the hub profile as a clamped cubic NURBS curve from the top eye small radius to the bottom backplate large radius.",
    "3. Revolve the hub profile 360 degrees around Z to create the hub root surface; add the bottom annular face and mounting-bore cylinder to describe the inner hub solid.",
    "4. Define the tip or shroud profile as a second clamped cubic NURBS curve above the hub profile and revolve it as the blade tip boundary reference.",
    "5. Sample conformal blade root and tip curves from the hub and tip surfaces for every blade instance.",
    "6. Build the blade mean surface between root and tip, then offset it circumferentially to create pressure and suction NURBS surface samples.",
    "7. Build blade edge closure surfaces at the leading edge, trailing edge, root edge, and tip edge so each blade is a closed solid candidate rather than two detached side faces.",
    "8. Emit shaded surfaces and construction lines from the same sampled surface graph, including dedicated visible blade edge lines.",
]


def build_axisymmetric_throughflow_nurbs_geometry(
    parameters: dict[str, Any],
    facets: dict[str, str],
    shape_control: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = _normalized_parameters(parameters)
    resolved_facets = _normalized_facets(facets)
    stage = _normalize_geometry_stage(geometry_stage)
    hub_profile, tip_profile = _profile_definitions(params, resolved_facets, profile_overrides)
    curve_controls = _validated_curve_overrides(curve_overrides, params, resolved_facets)
    hub_curve = _sample_profile_curve(hub_profile, SURFACE_U_COUNT)
    tip_curve = _sample_profile_curve(tip_profile, SURFACE_U_COUNT)
    sampled_blades = _pattern_blades(params, resolved_facets, hub_profile, tip_profile, curve_controls)
    material_domains = _material_domains(params, resolved_facets, material_domain)
    surface_graph = _surface_graph(
        params,
        resolved_facets,
        hub_profile,
        tip_profile,
        sampled_blades,
        display_policy=display_policy,
        material_domain=material_domain,
        solid_features=solid_features,
    )
    construction_lines = _construction_lines(surface_graph, sampled_blades)
    surface_graph, construction_lines = _filter_by_geometry_stage(surface_graph, construction_lines, stage)
    validity = _validity_report(
        surface_graph,
        sampled_blades,
        construction_lines,
        params,
        resolved_facets,
        stage,
        display_policy=display_policy,
        material_domain=material_domain,
    )
    passage_model = {
        "type": "throughflow_bladed_channel",
        "throughflow_bladed_channel": True,
        "free_passage_cavity": False,
    }

    return {
        "kernel": {
            "kind": "axisymmetric_throughflow_nurbs_kernel",
            "basis": "hub_tip_revolved_nurbs_profiles_with_pressure_suction_nurbs_blades",
            "construction_sequence": CONSTRUCTION_SEQUENCE,
            "hub_profile_orientation": {
                "u0": "top_eye_small_radius",
                "u1": "bottom_backplate_large_radius",
            },
            "meridional_profiles": {
                "hub": hub_profile,
                "tip_or_shroud": tip_profile,
            },
            "profile_controls": {
                "source": "user_override" if profile_overrides else "default_rule",
                "editable_entities": ["hub_profile", "tip_or_shroud_profile"],
            },
            "meridional_curves": {
                "hub": hub_curve,
                "tip_or_shroud": tip_curve,
            },
            "blade_parameterization": {
                "theta_field": "wrap_plus_spanwise_lean",
                "wrap_deg": _round(params["blade_wrap_deg"]),
                "lean_deg": _round(params["blade_lean_deg"]),
                "pressure_suction_offset": "arc_thickness_over_local_radius",
            },
            "editable_curve_controls": curve_controls,
            "thickness_field": {
                "kind": "u_tapered_constant_spanwise",
                "root_mm": _round(params["blade_thickness_mm"]),
                "trailing_edge_mm": _round(params["blade_thickness_mm"] * 0.55),
            },
            "uv_sampling": {
                "surface_u_count": SURFACE_U_COUNT,
                "surface_v_count": SURFACE_V_COUNT,
                "blade_u_count": BLADE_U_COUNT,
                "blade_v_count": BLADE_V_COUNT,
            },
            "passage_model": passage_model,
            "geometry_stage": stage,
            "material_domains": material_domains,
            "solid_features": _solid_feature_metadata(params, resolved_facets, solid_features),
        },
        "passage_model": passage_model,
        "shape_control": shape_control
        or {
            "optimization_stage": 1,
            "locked_topology": True,
            "active_policies": [],
        },
        "sampled_blades": sampled_blades,
        "surface_graph": surface_graph,
        "blade_surface": {
            "primitive": "pressure_suction_nurbs_surface_pair",
            "profile_curve_kind": "nurbs_surface",
            "height_model": "hub_tip_revolved_nurbs_profiles",
            "loft_section_count": BLADE_U_COUNT,
            "curve_gain": 1.0,
            "driven_by": [
                "hub_profile_nurbs_control_points",
                "tip_profile_nurbs_control_points",
                "blade_wrap_deg",
                "blade_lean_deg",
                "blade_thickness_mm",
            ],
            "sections": _section_metadata(hub_curve, tip_curve, params),
        },
        "hub_surface": {
            "primitive": "nurbs_profile_revolved_about_z",
            "profile": hub_profile,
            "surface_u_count": SURFACE_U_COUNT,
            "surface_v_count": SURFACE_V_COUNT,
        },
        "cad_features": _cad_features(resolved_facets),
        "construction_lines": construction_lines,
        "validity": validity,
    }


def _normalized_parameters(parameters: dict[str, Any]) -> dict[str, float]:
    numeric = {name: float(value) for name, value in parameters.items()}
    numeric.setdefault("blade_count", 7)
    numeric.setdefault("inlet_radius_mm", 180.0)
    numeric.setdefault("exit_radius_mm", 620.0)
    numeric.setdefault("inlet_blade_height_mm", 150.0)
    numeric.setdefault("outlet_blade_height_mm", 72.0)
    numeric.setdefault("hub_curve_height_mm", 82.0)
    numeric.setdefault("blade_thickness_mm", 18.0)
    numeric.setdefault("blade_wrap_deg", 110.0)
    numeric.setdefault("blade_lean_deg", 0.0)
    numeric.setdefault("leading_edge_lean_deg", numeric["blade_lean_deg"])
    numeric.setdefault("trailing_edge_lean_deg", numeric["blade_lean_deg"])
    numeric.setdefault("leading_edge_sweep_mm", 0.0)
    numeric.setdefault("trailing_edge_sweep_mm", 0.0)
    numeric.setdefault("inlet_blade_angle_deg", 21.0)
    numeric.setdefault("outlet_blade_angle_deg", 42.0)
    numeric.setdefault("mounting_bore_radius_mm", max(12.0, numeric["inlet_radius_mm"] * 0.22))
    numeric.setdefault("hub_wall_thickness_mm", 18.0)
    numeric.setdefault("hub_bottom_thickness_mm", 24.0)
    numeric.setdefault("hub_top_cap_thickness_mm", 8.0)
    numeric.setdefault("hub_chamfer_radius_mm", 3.0)
    numeric.setdefault("hood_wall_thickness_mm", 12.0)
    numeric.setdefault("hood_chamfer_radius_mm", 3.0)
    numeric["mounting_bore_radius_mm"] = min(
        max(1.0, numeric["mounting_bore_radius_mm"]),
        max(2.0, numeric["inlet_radius_mm"] * 0.52),
    )
    numeric["blade_count"] = int(numeric["blade_count"])
    return numeric


def _normalized_facets(facets: dict[str, str]) -> dict[str, str]:
    return {
        "flow_topology": facets.get("flow_topology", "radial"),
        "shroud_topology": facets.get("shroud_topology", "open"),
        "suction_topology": facets.get("suction_topology", "single_suction"),
        "blade_exit_geometry": facets.get("blade_exit_geometry", "backward_curved"),
        "working_domain": facets.get("working_domain", "pump"),
        "passage_topology": facets.get("passage_topology", "throughflow_bladed_channel"),
    }


def _material_domains(
    params: dict[str, float],
    facets: dict[str, str],
    material_domain: dict[str, Any] | None,
) -> dict[str, Any]:
    hub_domain = (material_domain or {}).get("hub", {})
    front_hood_domain = (material_domain or {}).get("front_shroud", {})
    return {
        "hub": {
            "kind": hub_domain.get("kind", "revolved_solid_with_bore"),
            "wall_thickness_mm": _round(params["hub_wall_thickness_mm"]),
            "bottom_thickness_mm": _round(params["hub_bottom_thickness_mm"]),
            "top_cap_thickness_mm": _round(params["hub_top_cap_thickness_mm"]),
            "mounting_bore_radius_mm": _round(params["mounting_bore_radius_mm"]),
            "chamfer_radius_mm": _round(params["hub_chamfer_radius_mm"]),
            "faces": [
                "hub_revolve_surface",
                "inner_hub_bottom_face",
                "hub_top_cap_face",
                "mounting_bore_cylinder",
            ],
        },
        "front_hood": (
            {
                "kind": front_hood_domain.get("kind", "finite_thickness_revolved_shell"),
                "wall_thickness_mm": _round(params["hood_wall_thickness_mm"]),
                "chamfer_radius_mm": _round(params["hood_chamfer_radius_mm"]),
                "faces": [
                    "shroud_surface",
                    "hood_outer_surface",
                    "hood_inlet_cap_surface",
                    "hood_outlet_cap_surface",
                ],
            }
            if facets["shroud_topology"] == "closed"
            else {"kind": "none"}
        ),
    }


def _solid_feature_metadata(
    params: dict[str, float],
    facets: dict[str, str],
    solid_features: dict[str, Any] | None,
) -> dict[str, Any]:
    declared = solid_features or {}
    features = {
        "hub_bore": {
            "kind": declared.get("hub_bore", {}).get("kind", "cylindrical_cut"),
            "radius_mm": _round(params["mounting_bore_radius_mm"]),
            "axis": "z",
            "extent": "through_hub_solid",
        },
        "hub_chamfers": {
            "kind": declared.get("hub_chamfers", {}).get("kind", "chamfer_or_fillet_feature_set"),
            "radius_mm": _round(params["hub_chamfer_radius_mm"]),
        },
    }
    if facets["shroud_topology"] == "closed":
        features["hood_chamfers"] = {
            "kind": declared.get("hood_chamfers", {}).get("kind", "chamfer_or_fillet_feature_set"),
            "radius_mm": _round(params["hood_chamfer_radius_mm"]),
        }
    return features


def _profile_definitions(
    params: dict[str, float],
    facets: dict[str, str],
    profile_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    default_hub, default_tip = _default_profile_definitions(params, facets)
    overrides = profile_overrides or {}
    hub = _validated_profile_override("hub_profile", overrides.get("hub_profile"), default_hub)
    tip = _validated_profile_override("tip_or_shroud_profile", overrides.get("tip_or_shroud_profile"), default_tip)
    _validate_tip_clearance(hub, tip)
    return hub, tip


def _default_profile_definitions(
    params: dict[str, float],
    facets: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    inlet = params["inlet_radius_mm"]
    outlet = params["exit_radius_mm"]
    radial_span = outlet - inlet
    hub_z = params["hub_curve_height_mm"]
    inlet_height = params["inlet_blade_height_mm"]
    outlet_height = params["outlet_blade_height_mm"]
    flow_lift = {
        "radial": 0.18,
        "mixed": 0.42,
        "axial": 0.78,
    }.get(facets["flow_topology"], 0.18)
    hub_top_z = max(hub_z, inlet_height * 0.26)
    hub_top_radius = max(params["mounting_bore_radius_mm"] * 1.55, inlet * 0.70)
    hub_bottom_radius = outlet * 0.92
    hub_cp = [
        [hub_top_radius, hub_top_z + radial_span * 0.03 * flow_lift],
        [inlet + radial_span * 0.18, hub_top_z * 0.78 + radial_span * 0.025 * flow_lift],
        [inlet + radial_span * 0.70, hub_top_z * 0.22 + radial_span * 0.012 * flow_lift],
        [hub_bottom_radius, 0.0],
    ]
    tip_cp = [
        [inlet, hub_cp[0][1] + inlet_height],
        [inlet + radial_span * 0.24, hub_cp[1][1] + inlet_height * 0.86 + radial_span * 0.025 * flow_lift],
        [inlet + radial_span * 0.72, hub_cp[2][1] + outlet_height * 1.18 + radial_span * 0.018 * flow_lift],
        [outlet, hub_cp[-1][1] + outlet_height],
    ]
    return _nurbs_curve("hub_profile", hub_cp), _nurbs_curve("tip_or_shroud_profile", tip_cp)


def _validated_profile_override(
    name: str,
    override: dict[str, Any] | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if override is None:
        return fallback
    if override.get("kind") != "nurbs_curve":
        raise ValueError(f"{name} must be kind nurbs_curve")
    degree = override.get("degree")
    if type(degree) is not int or degree != 3:
        raise ValueError(f"{name} degree must be 3")
    points = override.get("control_points")
    if not isinstance(points, list) or len(points) < degree + 1:
        raise ValueError(f"{name} must have at least {degree + 1} control points")
    cleaned_points = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"{name} control point must be [r_mm, z_mm]")
        r, z = float(point[0]), float(point[1])
        if not math.isfinite(r) or not math.isfinite(z):
            raise ValueError(f"{name} control point values must be finite")
        if r <= 0.0:
            raise ValueError(f"{name} requires positive radius")
        cleaned_points.append([_round(r), _round(z)])
    weights = [float(value) for value in override.get("weights", fallback["weights"])]
    if len(weights) != len(cleaned_points):
        raise ValueError(f"{name} weight count must match control point count")
    if any(value <= 0.0 or not math.isfinite(value) for value in weights):
        raise ValueError(f"{name} weights must be positive finite values")
    knots = [float(value) for value in override.get("knots", fallback["knots"])]
    if len(knots) != len(cleaned_points) + degree + 1:
        raise ValueError(f"{name} knot count must equal control point count + degree + 1")
    if any(not math.isfinite(value) for value in knots):
        raise ValueError(f"{name} knots must be finite")
    if any(left > right for left, right in zip(knots, knots[1:])):
        raise ValueError(f"{name} knots must be non-decreasing")
    if knots[: degree + 1] != [0.0] * (degree + 1) or knots[-(degree + 1) :] != [1.0] * (degree + 1):
        raise ValueError(f"{name} knots must be clamped to 0 and 1")
    if override.get("coordinate_system", "rz_meridional_mm") != "rz_meridional_mm":
        raise ValueError(f"{name} coordinate_system must be rz_meridional_mm")
    return {
        **fallback,
        "id": fallback["id"],
        "kind": "nurbs_curve",
        "degree": degree,
        "control_points": cleaned_points,
        "weights": [_round(value) for value in weights],
        "knots": knots,
        "coordinate_system": "rz_meridional_mm",
        "source": "user_override",
    }


def _validate_tip_clearance(hub_profile: dict[str, Any], tip_profile: dict[str, Any]) -> None:
    for index in range(SURFACE_U_COUNT):
        u = index / (SURFACE_U_COUNT - 1)
        hub = _profile_point(hub_profile, u)
        tip = _profile_point(tip_profile, u)
        if tip[0] <= hub[0] or tip[1] <= hub[1]:
            raise ValueError("tip_or_shroud_profile must remain outside and above hub_profile")


def _nurbs_curve(curve_id: str, control_points: list[list[float]]) -> dict[str, Any]:
    degree = 3
    return {
        "id": curve_id,
        "kind": "nurbs_curve",
        "degree": degree,
        "control_points": [[_round(point[0]), _round(point[1])] for point in control_points],
        "weights": [1.0 for _ in control_points],
        "knots": _clamped_open_uniform_knots(len(control_points), degree),
        "coordinate_system": "rz_meridional_mm",
    }


def _sample_profile_curve(profile: dict[str, Any], count: int) -> list[dict[str, float]]:
    return [
        {
            "u": _round(index / (count - 1)),
            "r_mm": _round(point[0]),
            "z_mm": _round(point[1]),
        }
        for index in range(count)
        for point in [_profile_point(profile, index / (count - 1))]
    ]


def _profile_point(profile: dict[str, Any], u: float) -> list[float]:
    points = profile["control_points"]
    weights = profile["weights"]
    knots = profile["knots"]
    degree = int(profile["degree"])
    clamped_u = _clamp01(u)
    basis = [_nurbs_basis(index, degree, clamped_u, knots) for index in range(len(points))]
    denominator = sum(value * weights[index] for index, value in enumerate(basis))
    if denominator <= 0.0:
        raise ValueError("profile NURBS denominator must be positive")
    r = sum(basis[index] * weights[index] * points[index][0] for index in range(len(points))) / denominator
    z = sum(basis[index] * weights[index] * points[index][1] for index in range(len(points))) / denominator
    return [r, z]


def _clamped_open_uniform_knots(point_count: int, degree: int) -> list[float]:
    interior_count = point_count - degree - 1
    if point_count < degree + 1:
        raise ValueError("control point count must be at least degree + 1")
    interiors = [(index + 1) / (interior_count + 1) for index in range(interior_count)]
    return [0.0] * (degree + 1) + interiors + [1.0] * (degree + 1)


def _nurbs_basis(i: int, degree: int, u: float, knots: list[float]) -> float:
    if degree == 0:
        if knots[i] <= u < knots[i + 1] or (u == 1.0 and knots[i] <= u <= knots[i + 1]):
            return 1.0
        return 0.0
    left_denominator = knots[i + degree] - knots[i]
    right_denominator = knots[i + degree + 1] - knots[i + 1]
    left = 0.0
    right = 0.0
    if left_denominator > 0:
        left = ((u - knots[i]) / left_denominator) * _nurbs_basis(i, degree - 1, u, knots)
    if right_denominator > 0:
        right = ((knots[i + degree + 1] - u) / right_denominator) * _nurbs_basis(
            i + 1,
            degree - 1,
            u,
            knots,
        )
    return left + right


def _validated_curve_overrides(
    curve_overrides: dict[str, Any] | None,
    params: dict[str, float],
    facets: dict[str, str],
) -> dict[str, Any]:
    controls = _default_curve_controls(params, facets)
    overrides = curve_overrides or {}
    allowed = {
        "blade_mean": {
            "theta_center_u_curve": "u_theta_deg",
            "span_lean_u_curve": "u_lean_deg",
        },
        "blade_edges": {
            "leading_edge_sweep_v_curve": "v_support_u_offset",
            "trailing_edge_sweep_v_curve": "v_support_u_offset",
        },
        "thickness": {
            "thickness_u_curve": "u_thickness_mm",
        },
    }
    for group, curves in overrides.items():
        if group not in allowed:
            raise ValueError(f"unknown curve override group: {group}")
        if not isinstance(curves, dict):
            raise ValueError(f"{group} curve overrides must be an object")
        for curve_id, curve in curves.items():
            if curve_id not in allowed[group]:
                raise ValueError(f"unknown curve override: {group}.{curve_id}")
            controls[group][curve_id] = _validated_curve_override(
                f"{group}.{curve_id}",
                curve,
                allowed[group][curve_id],
            )
    return controls


def _default_curve_controls(params: dict[str, float], facets: dict[str, str]) -> dict[str, Any]:
    exit_sign = {"backward_curved": -1.0, "radial": 0.35, "forward_curved": 1.0}.get(
        facets["blade_exit_geometry"],
        -1.0,
    )
    wrap = params["blade_wrap_deg"] * exit_sign
    leading_lean = params["leading_edge_lean_deg"]
    trailing_lean = params["trailing_edge_lean_deg"]
    mid_lean = params["blade_lean_deg"] + 0.5 * (leading_lean + trailing_lean)
    radial_span = max(params["exit_radius_mm"] - params["inlet_radius_mm"], 1.0)
    return {
        "blade_mean": {
            "theta_center_u_curve": _curve_def(
                "u_theta_deg",
                [[0.0, 0.0], [0.33, wrap * _smoothstep(0.33)], [0.66, wrap * _smoothstep(0.66)], [1.0, wrap]],
                "default_rule",
            ),
            "span_lean_u_curve": _curve_def(
                "u_lean_deg",
                [[0.0, leading_lean], [0.5, mid_lean], [1.0, trailing_lean]],
                "default_rule",
            ),
        },
        "blade_edges": {
            "leading_edge_sweep_v_curve": _curve_def(
                "v_support_u_offset",
                [[0.0, -params["leading_edge_sweep_mm"] / (2.0 * radial_span)], [0.5, 0.0], [1.0, params["leading_edge_sweep_mm"] / (2.0 * radial_span)]],
                "default_rule",
            ),
            "trailing_edge_sweep_v_curve": _curve_def(
                "v_support_u_offset",
                [[0.0, -params["trailing_edge_sweep_mm"] / (2.0 * radial_span)], [0.5, 0.0], [1.0, params["trailing_edge_sweep_mm"] / (2.0 * radial_span)]],
                "default_rule",
            ),
        },
        "thickness": {
            "thickness_u_curve": _curve_def(
                "u_thickness_mm",
                [[0.0, params["blade_thickness_mm"]], [0.5, params["blade_thickness_mm"] * (1.0 - 0.45 * _smoothstep(0.5))], [1.0, params["blade_thickness_mm"] * 0.55]],
                "default_rule",
            ),
        },
    }


def _curve_def(coordinate_system: str, control_points: list[list[float]], source: str) -> dict[str, Any]:
    return {
        "coordinate_system": coordinate_system,
        "control_points": [[_round(point[0]), _round(point[1])] for point in control_points],
        "source": source,
    }


def _validated_curve_override(name: str, curve: dict[str, Any], expected_coordinate_system: str) -> dict[str, Any]:
    if not isinstance(curve, dict):
        raise ValueError(f"{name} must be an object")
    if curve.get("coordinate_system") != expected_coordinate_system:
        raise ValueError(f"{name} coordinate_system must be {expected_coordinate_system}")
    raw_points = curve.get("control_points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise ValueError(f"{name} must have at least two control points")
    points: list[list[float]] = []
    previous_t = -1.0
    for point in raw_points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"{name} control point must be [t, value]")
        t, value = float(point[0]), float(point[1])
        if not math.isfinite(t) or not math.isfinite(value):
            raise ValueError(f"{name} control point values must be finite")
        if t < 0.0 or t > 1.0 or t <= previous_t:
            raise ValueError(f"{name} control point t values must be monotone within [0, 1]")
        if expected_coordinate_system == "u_thickness_mm" and value <= 0.0:
            raise ValueError(f"{name} thickness values must be positive")
        if expected_coordinate_system == "v_support_u_offset" and abs(value) > 0.45:
            raise ValueError(f"{name} support offsets must be within [-0.45, 0.45]")
        points.append([_round(t), _round(value)])
        previous_t = t
    return _curve_def(expected_coordinate_system, points, "user_override")


def _curve_value(curve: dict[str, Any], t: float) -> float:
    points = curve["control_points"]
    clamped_t = _clamp01(t)
    if clamped_t <= points[0][0]:
        return float(points[0][1])
    for left, right in zip(points, points[1:]):
        if clamped_t <= right[0]:
            span = max(right[0] - left[0], 1e-9)
            ratio = (clamped_t - left[0]) / span
            return float(left[1]) + (float(right[1]) - float(left[1])) * ratio
    return float(points[-1][1])


def _pattern_blades(
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
    curve_controls: dict[str, Any],
) -> list[dict[str, Any]]:
    blades = []
    for blade_index in range(int(params["blade_count"])):
        base_angle = 2.0 * math.pi * blade_index / int(params["blade_count"])
        blades.append(_blade_surfaces(blade_index, base_angle, params, facets, hub_profile, tip_profile, curve_controls))
    return blades


def _blade_surfaces(
    blade_index: int,
    base_angle: float,
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
    curve_controls: dict[str, Any],
) -> dict[str, Any]:
    pressure = []
    suction = []
    mean = []
    for u_index in range(BLADE_U_COUNT):
        u = u_index / (BLADE_U_COUNT - 1)
        pressure_row = []
        suction_row = []
        mean_row = []
        for v_index in range(BLADE_V_COUNT):
            v = v_index / (BLADE_V_COUNT - 1)
            pressure_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, curve_controls, 1.0))
            suction_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, curve_controls, -1.0))
            mean_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, curve_controls, 0.0))
        pressure.append(pressure_row)
        suction.append(suction_row)
        mean.append(mean_row)
    return {
        "index": blade_index,
        "mirror_z": False,
        "pressure_surface": pressure,
        "suction_surface": suction,
        "mean_surface": mean,
        "leading_edge_surface": _edge_closure_grid(pressure[0], mean[0], suction[0]),
        "trailing_edge_surface": _edge_closure_grid(pressure[-1], mean[-1], suction[-1]),
        "root_closure_surface": _span_closure_grid(pressure, mean, suction, 0),
        "tip_closure_surface": _span_closure_grid(pressure, mean, suction, -1),
        "pressure_hub_boundary": [row[0] for row in pressure],
        "suction_hub_boundary": [row[0] for row in suction],
        "pressure_tip_boundary": [row[-1] for row in pressure],
        "suction_tip_boundary": [row[-1] for row in suction],
        "hub_boundary": [row[0] for row in mean],
        "tip_boundary": [row[-1] for row in mean],
        "blade_root_boundary": [row[0] for row in mean],
        "blade_tip_boundary": [row[-1] for row in mean],
        "leading_edge_boundary": mean[0],
        "trailing_edge_boundary": mean[-1],
        "loft_wires": [
            [pressure[u_index][0], suction[u_index][0], suction[u_index][-1], pressure[u_index][-1], pressure[u_index][0]]
            for u_index in range(BLADE_U_COUNT)
        ],
    }


def _blade_point(
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
    u: float,
    v: float,
    base_angle: float,
    params: dict[str, float],
    facets: dict[str, str],
    curve_controls: dict[str, Any],
    side: float,
) -> list[float]:
    support_u = _support_u(u, v, params, curve_controls)
    hub = _profile_point(hub_profile, support_u)
    tip = _profile_point(tip_profile, support_u)
    r = (1.0 - v) * hub[0] + v * tip[0]
    z = (1.0 - v) * hub[1] + v * tip[1]
    theta = _theta_field(u, v, base_angle, params, facets, curve_controls)
    if side:
        theta += side * _half_thickness_theta(params, u, r, curve_controls)
    return _polar_point(r, theta, z)


def _support_u(u: float, v: float, params: dict[str, float], curve_controls: dict[str, Any]) -> float:
    edge_curves = curve_controls["blade_edges"]
    leading_curve = edge_curves["leading_edge_sweep_v_curve"]
    trailing_curve = edge_curves["trailing_edge_sweep_v_curve"]
    if leading_curve["source"] == "user_override" or trailing_curve["source"] == "user_override":
        leading_offset = _curve_value(leading_curve, v)
        trailing_offset = _curve_value(trailing_curve, v)
        return _clamp01(u + (1.0 - u) * leading_offset + u * trailing_offset)
    radial_span = max(params["exit_radius_mm"] - params["inlet_radius_mm"], 1.0)
    edge_sweep = (1.0 - u) * params["leading_edge_sweep_mm"] + u * params["trailing_edge_sweep_mm"]
    return _clamp01(u + (edge_sweep / radial_span) * (v - 0.5))


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _edge_closure_grid(
    pressure_edge: list[list[float]],
    mean_edge: list[list[float]],
    suction_edge: list[list[float]],
) -> list[list[list[float]]]:
    return [
        [pressure_point, mean_point, suction_point]
        for pressure_point, mean_point, suction_point in zip(pressure_edge, mean_edge, suction_edge)
    ]


def _span_closure_grid(
    pressure: list[list[list[float]]],
    mean: list[list[list[float]]],
    suction: list[list[list[float]]],
    span_index: int,
) -> list[list[list[float]]]:
    return [
        [pressure[u_index][span_index], mean[u_index][span_index], suction[u_index][span_index]]
        for u_index in range(len(mean))
    ]


def _theta_field(
    u: float,
    v: float,
    base_angle: float,
    params: dict[str, float],
    facets: dict[str, str],
    curve_controls: dict[str, Any],
) -> float:
    mean_curves = curve_controls["blade_mean"]
    theta_curve = mean_curves["theta_center_u_curve"]
    lean_curve = mean_curves["span_lean_u_curve"]
    if theta_curve["source"] == "user_override" or lean_curve["source"] == "user_override":
        theta = math.radians(_curve_value(theta_curve, u))
        lean = math.radians(_curve_value(lean_curve, u))
        return base_angle + theta + lean * (v - 0.5)
    exit_sign = {"backward_curved": -1.0, "radial": 0.0, "forward_curved": 1.0}.get(
        facets["blade_exit_geometry"],
        -1.0,
    )
    if exit_sign == 0.0:
        exit_sign = 0.35
    wrap = math.radians(params["blade_wrap_deg"]) * exit_sign
    lean = math.radians(params["blade_lean_deg"])
    leading_lean = math.radians(params["leading_edge_lean_deg"])
    trailing_lean = math.radians(params["trailing_edge_lean_deg"])
    edge_lean = (1.0 - u) * leading_lean + u * trailing_lean
    return base_angle + wrap * _smoothstep(u) + (lean * math.sin(math.pi * u) + edge_lean) * (v - 0.5)


def _half_thickness_theta(params: dict[str, float], u: float, radius: float, curve_controls: dict[str, Any]) -> float:
    thickness_curve = curve_controls["thickness"]["thickness_u_curve"]
    if thickness_curve["source"] == "user_override":
        thickness = _curve_value(thickness_curve, u)
        return (thickness * 0.5) / max(radius, 1.0)
    thickness = params["blade_thickness_mm"] * (1.0 - 0.45 * _smoothstep(u))
    return (thickness * 0.5) / max(radius, 1.0)


def _surface_graph(
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surfaces = [
        {
            "id": "hub_revolve_surface",
            "kind": "nurbs_revolve_surface",
            "role": "hub",
            "ontology_id": "hub_support_surface",
            "material": True,
            "material_domain": "hub",
            "profile": hub_profile,
            "uv_grid": _revolve_grid(hub_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(hub_profile, SURFACE_U_COUNT),
            "display": {"color": "#7a946f", "opacity": 0.9},
            "boundary_ids": ["hub_inlet_circle", "hub_outlet_circle"],
        }
    ]
    surfaces.extend(_hub_solid_surfaces(params, hub_profile, solid_features))
    tip_surface_id = "shroud_surface" if facets["shroud_topology"] == "closed" else "tip_reference_surface"
    surfaces.append(
        {
            "id": tip_surface_id,
            "kind": "nurbs_revolve_surface",
            "role": (
                "front_shroud_inner_surface"
                if facets["shroud_topology"] == "closed"
                else (
                    "construction_support_only"
                    if _surface_hidden_by_policy("blade_tip_support_surface", display_policy)
                    else "reference_only"
                )
            ),
            "display_role": "shroud" if facets["shroud_topology"] == "closed" else "open_tip_reference",
            "ontology_id": "blade_tip_support_surface",
            "material": facets["shroud_topology"] == "closed",
            "material_domain": "front_hood" if facets["shroud_topology"] == "closed" else None,
            "profile": tip_profile,
            "uv_grid": _revolve_grid(tip_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(tip_profile, SURFACE_U_COUNT),
            "display": {
                "color": "#9db7c5" if facets["shroud_topology"] == "closed" else "#c8c08d",
                "opacity": 0.34 if facets["shroud_topology"] == "open" else 0.72,
                "visible_by_default": not _surface_hidden_by_policy("blade_tip_support_surface", display_policy),
            },
            "boundary_ids": ["tip_inlet_circle", "tip_outlet_circle"],
        }
    )
    if facets["shroud_topology"] == "closed":
        surfaces.extend(_hood_shell_surfaces(params, tip_profile, material_domain, solid_features))

    edges = [
        {
            "id": "outer_hub_shell_bottom_edge",
            "surfaces": ["outer_hub_shell_surface", "inner_hub_bottom_face"],
            "relation": "closed_hub_solid_boundary",
        },
        {
            "id": "mounting_bore_bottom_edge",
            "surfaces": ["mounting_bore_cylinder", "inner_hub_bottom_face"],
            "relation": "closed_mounting_bore_boundary",
        },
        {
            "id": "hub_root_land_to_outer_shell",
            "surfaces": ["hub_revolve_surface", "outer_hub_shell_surface"],
            "relation": "shared_hub_shell_definition",
        },
    ]
    boundary_curves: dict[str, Any] = {}
    named_boundary_curves: list[dict[str, Any]] = []
    for blade in sampled_blades:
        prefix = f"blade_{blade['index']}"
        boundary_curves[f"{prefix}_pressure_hub_boundary"] = blade["pressure_hub_boundary"]
        boundary_curves[f"{prefix}_suction_hub_boundary"] = blade["suction_hub_boundary"]
        boundary_curves[f"{prefix}_pressure_tip_boundary"] = blade["pressure_tip_boundary"]
        boundary_curves[f"{prefix}_suction_tip_boundary"] = blade["suction_tip_boundary"]
        boundary_curves[f"{prefix}_leading_edge"] = blade["leading_edge_surface"]
        boundary_curves[f"{prefix}_trailing_edge"] = blade["trailing_edge_surface"]
        boundary_curves[f"{prefix}_root_closure"] = blade["root_closure_surface"]
        boundary_curves[f"{prefix}_tip_closure"] = blade["tip_closure_surface"]
        named_boundary_curves.extend(
            [
                {
                    "id": f"{prefix}_blade_root_boundary",
                    "role": "blade_root_boundary",
                    "blade_index": blade["index"],
                    "support_surface": "hub_revolve_surface",
                    "support_surface_ontology_id": "hub_support_surface",
                    "parameter": "v=0",
                    "points": blade["blade_root_boundary"],
                },
                {
                    "id": f"{prefix}_blade_tip_boundary",
                    "role": "blade_tip_boundary",
                    "blade_index": blade["index"],
                    "support_surface": tip_surface_id,
                    "support_surface_ontology_id": "blade_tip_support_surface",
                    "parameter": "v=1",
                    "points": blade["blade_tip_boundary"],
                },
                {
                    "id": f"{prefix}_leading_edge_boundary",
                    "role": "leading_edge_boundary",
                    "blade_index": blade["index"],
                    "parameter": "u=0",
                    "points": blade["leading_edge_boundary"],
                },
                {
                    "id": f"{prefix}_trailing_edge_boundary",
                    "role": "trailing_edge_boundary",
                    "blade_index": blade["index"],
                    "parameter": "u=1",
                    "points": blade["trailing_edge_boundary"],
                },
            ]
        )
        surfaces.extend(
            [
                {
                    "id": f"{prefix}_pressure_surface",
                    "kind": "nurbs_surface",
                    "role": "blade_pressure",
                    "degree_u": 3,
                    "degree_v": 3,
                    "control_net": _control_net_from_grid(blade["pressure_surface"]),
                    "uv_grid": blade["pressure_surface"],
                    "display": {"color": "#70a46f", "opacity": 0.9},
                    "boundary_ids": [
                        f"{prefix}_pressure_leading_edge",
                        f"{prefix}_pressure_trailing_edge",
                        f"{prefix}_pressure_hub_root",
                        f"{prefix}_pressure_tip_edge",
                    ],
                },
                {
                    "id": f"{prefix}_suction_surface",
                    "kind": "nurbs_surface",
                    "role": "blade_suction",
                    "degree_u": 3,
                    "degree_v": 3,
                    "control_net": _control_net_from_grid(blade["suction_surface"]),
                    "uv_grid": blade["suction_surface"],
                    "display": {"color": "#5f8f66", "opacity": 0.9},
                    "boundary_ids": [
                        f"{prefix}_suction_leading_edge",
                        f"{prefix}_suction_trailing_edge",
                        f"{prefix}_suction_hub_root",
                        f"{prefix}_suction_tip_edge",
                    ],
                },
                {
                    "id": f"{prefix}_leading_edge_surface",
                    "kind": "edge_closure_surface",
                    "role": "blade_leading_edge_closure",
                    "closure_model": "ruled_pressure_mean_suction",
                    "uv_grid": blade["leading_edge_surface"],
                    "display": {"color": "#f59e0b", "opacity": 1.0, "edge_highlight": True},
                    "boundary_ids": [
                        f"{prefix}_pressure_leading_edge",
                        f"{prefix}_suction_leading_edge",
                    ],
                },
                {
                    "id": f"{prefix}_trailing_edge_surface",
                    "kind": "edge_closure_surface",
                    "role": "blade_trailing_edge_closure",
                    "closure_model": "ruled_pressure_mean_suction",
                    "uv_grid": blade["trailing_edge_surface"],
                    "display": {"color": "#ef4444", "opacity": 1.0, "edge_highlight": True},
                    "boundary_ids": [
                        f"{prefix}_pressure_trailing_edge",
                        f"{prefix}_suction_trailing_edge",
                    ],
                },
                {
                    "id": f"{prefix}_root_closure_surface",
                    "kind": "edge_closure_surface",
                    "role": "blade_root_hub_closure",
                    "closure_model": "ruled_pressure_mean_suction",
                    "uv_grid": blade["root_closure_surface"],
                    "display": {"color": "#22c55e", "opacity": 1.0, "edge_highlight": True},
                    "boundary_ids": [
                        f"{prefix}_pressure_hub_root",
                        f"{prefix}_suction_hub_root",
                    ],
                },
                {
                    "id": f"{prefix}_tip_closure_surface",
                    "kind": "edge_closure_surface",
                    "role": "blade_tip_closure",
                    "closure_model": "ruled_pressure_mean_suction",
                    "uv_grid": blade["tip_closure_surface"],
                    "display": {"color": "#38bdf8", "opacity": 1.0, "edge_highlight": True},
                    "boundary_ids": [
                        f"{prefix}_pressure_tip_edge",
                        f"{prefix}_suction_tip_edge",
                    ],
                },
            ]
        )
        edges.extend(
            [
                {
                    "id": f"{prefix}_pressure_leading_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_leading_edge_surface"],
                    "relation": "closed_blade_edge",
                },
                {
                    "id": f"{prefix}_suction_leading_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_leading_edge_surface"],
                    "relation": "closed_blade_edge",
                },
                {
                    "id": f"{prefix}_pressure_trailing_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_trailing_edge_surface"],
                    "relation": "closed_blade_edge",
                },
                {
                    "id": f"{prefix}_suction_trailing_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_trailing_edge_surface"],
                    "relation": "closed_blade_edge",
                },
                {
                    "id": f"{prefix}_pressure_root_closure_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_root_closure_surface"],
                    "relation": "closed_blade_root_edge",
                },
                {
                    "id": f"{prefix}_suction_root_closure_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_root_closure_surface"],
                    "relation": "closed_blade_root_edge",
                },
                {
                    "id": f"{prefix}_pressure_tip_closure_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_tip_closure_surface"],
                    "relation": "closed_blade_tip_edge",
                },
                {
                    "id": f"{prefix}_suction_tip_closure_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_tip_closure_surface"],
                    "relation": "closed_blade_tip_edge",
                },
                {
                    "id": f"{prefix}_root_hub_conformal_edge",
                    "surfaces": ["hub_revolve_surface", f"{prefix}_root_closure_surface"],
                    "relation": "conformal_hub_boundary",
                },
                {
                    "id": f"{prefix}_tip_conformal_edge",
                    "surfaces": [tip_surface_id, f"{prefix}_tip_closure_surface"],
                    "relation": "conformal_tip_boundary",
                },
            ]
        )
        for side in ["pressure", "suction"]:
            blade_surface = f"{prefix}_{side}_surface"
            edges.extend(
                [
                    {
                        "id": f"{prefix}_{side}_hub_edge",
                        "surfaces": ["hub_revolve_surface", blade_surface],
                        "relation": "conformal_hub_boundary",
                    },
                    {
                        "id": f"{prefix}_{side}_tip_edge",
                        "surfaces": [tip_surface_id, blade_surface],
                        "relation": "conformal_tip_boundary",
                    },
                ]
            )
    surface_graph = {
        "surfaces": surfaces,
        "edges": edges,
        "boundary_curves": boundary_curves,
        "named_boundary_curves": named_boundary_curves,
    }
    return _apply_display_policy(surface_graph, display_policy)


def _hub_solid_surfaces(
    params: dict[str, float],
    hub_profile: dict[str, Any],
    solid_features: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    control_points = hub_profile["control_points"]
    bottom = min(control_points, key=lambda point: point[1])
    top = max(control_points, key=lambda point: point[1])
    bore_radius = min(params["mounting_bore_radius_mm"], bottom[0] * 0.72, top[0] * 0.86)
    chamfer = max(0.001, params.get("hub_chamfer_radius_mm", 0.0))
    outer_profile = {
        **hub_profile,
        "id": "outer_hub_shell_profile",
        "control_points": [point[:] for point in hub_profile["control_points"]],
        "weights": hub_profile["weights"][:],
        "knots": hub_profile["knots"][:],
    }
    surfaces = [
        {
            "id": "outer_hub_shell_surface",
            "kind": "nurbs_revolve_surface",
            "role": "outer_hub_shell",
            "material_domain": "hub",
            "wall_thickness_mm": _round(params["hub_wall_thickness_mm"]),
            "profile": outer_profile,
            "uv_grid": _revolve_grid(outer_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(outer_profile, SURFACE_U_COUNT),
            "display": {"color": "#78936a", "opacity": 0.48},
            "boundary_ids": ["outer_hub_top_circle", "outer_hub_bottom_circle"],
        },
        {
            "id": "inner_hub_bottom_face",
            "kind": "annular_plane_surface",
            "role": "inner_hub_bottom",
            "material_domain": "hub",
            "bottom_thickness_mm": _round(params["hub_bottom_thickness_mm"]),
            "inner_radius_mm": _round(bore_radius),
            "outer_radius_mm": _round(bottom[0]),
            "z_mm": _round(bottom[1]),
            "uv_grid": _annular_plane_grid(bore_radius, bottom[0], bottom[1], 8, SURFACE_V_COUNT),
            "display": {"color": "#6d7f6a", "opacity": 0.82},
            "boundary_ids": ["mounting_bore_bottom_circle", "outer_hub_bottom_circle"],
        },
        {
            "id": "hub_top_cap_face",
            "kind": "annular_plane_surface",
            "role": "hub_top_cap",
            "material_domain": "hub",
            "top_cap_thickness_mm": _round(params["hub_top_cap_thickness_mm"]),
            "inner_radius_mm": _round(bore_radius),
            "outer_radius_mm": _round(top[0]),
            "z_mm": _round(top[1]),
            "uv_grid": _annular_plane_grid(bore_radius, top[0], top[1], 8, SURFACE_V_COUNT),
            "display": {"color": "#768c68", "opacity": 0.82},
            "boundary_ids": ["mounting_bore_top_circle", "outer_hub_top_circle"],
        },
        {
            "id": "mounting_bore_cylinder",
            "kind": "cylindrical_surface",
            "role": "mounting_bore",
            "material_domain": "hub",
            "boolean_role": "removed_cylinder_boundary",
            "radius_mm": _round(bore_radius),
            "z_min_mm": _round(bottom[1]),
            "z_max_mm": _round(top[1]),
            "uv_grid": _cylinder_grid(bore_radius, bottom[1], top[1], SURFACE_U_COUNT, SURFACE_V_COUNT),
            "display": {"color": "#4b5563", "opacity": 0.86},
            "boundary_ids": ["mounting_bore_bottom_circle", "mounting_bore_top_circle"],
        },
        {
            "id": "hub_chamfer_bottom_outer_surface",
            "kind": "chamfer_surface",
            "role": "hub_chamfer",
            "material_domain": "hub",
            "radius_mm": _round(params["hub_chamfer_radius_mm"]),
            "uv_grid": _chamfer_band_grid(max(bore_radius, bottom[0] - chamfer), bottom[0], bottom[1], bottom[1] + chamfer),
            "display": {"color": "#91aa80", "opacity": 0.9},
            "boundary_ids": ["hub_bottom_outer_chamfer_a", "hub_bottom_outer_chamfer_b"],
        },
        {
            "id": "hub_chamfer_top_cap_surface",
            "kind": "chamfer_surface",
            "role": "hub_chamfer",
            "material_domain": "hub",
            "radius_mm": _round(params["hub_chamfer_radius_mm"]),
            "uv_grid": _chamfer_band_grid(max(bore_radius, top[0] - chamfer), top[0], top[1] - chamfer, top[1]),
            "display": {"color": "#91aa80", "opacity": 0.9},
            "boundary_ids": ["hub_top_cap_chamfer_a", "hub_top_cap_chamfer_b"],
        },
        {
            "id": "hub_chamfer_bore_top_surface",
            "kind": "chamfer_surface",
            "role": "hub_chamfer",
            "material_domain": "hub",
            "radius_mm": _round(params["hub_chamfer_radius_mm"]),
            "uv_grid": _chamfer_band_grid(bore_radius, bore_radius + chamfer, top[1] - chamfer, top[1]),
            "display": {"color": "#91aa80", "opacity": 0.86},
            "boundary_ids": ["mounting_bore_top_chamfer_a", "mounting_bore_top_chamfer_b"],
        },
        {
            "id": "hub_chamfer_bore_bottom_surface",
            "kind": "chamfer_surface",
            "role": "hub_chamfer",
            "material_domain": "hub",
            "radius_mm": _round(params["hub_chamfer_radius_mm"]),
            "uv_grid": _chamfer_band_grid(bore_radius, bore_radius + chamfer, bottom[1], bottom[1] + chamfer),
            "display": {"color": "#91aa80", "opacity": 0.86},
            "boundary_ids": ["mounting_bore_bottom_chamfer_a", "mounting_bore_bottom_chamfer_b"],
        },
    ]
    if not solid_features:
        legacy_ids = {"outer_hub_shell_surface", "inner_hub_bottom_face", "mounting_bore_cylinder"}
        return [surface for surface in surfaces if surface["id"] in legacy_ids]
    return surfaces


def _hood_shell_surfaces(
    params: dict[str, float],
    tip_profile: dict[str, Any],
    material_domain: dict[str, Any] | None,
    solid_features: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    thickness = params["hood_wall_thickness_mm"]
    chamfer = max(0.001, params.get("hood_chamfer_radius_mm", 0.0))
    inner_points = tip_profile["control_points"]
    outer_profile = {
        **tip_profile,
        "id": "hood_outer_profile",
        "control_points": [[point[0], _round(point[1] + thickness)] for point in inner_points],
        "weights": tip_profile["weights"][:],
        "knots": tip_profile["knots"][:],
    }
    inlet_inner = inner_points[0]
    outlet_inner = inner_points[-1]
    inlet_outer = outer_profile["control_points"][0]
    outlet_outer = outer_profile["control_points"][-1]
    surfaces = [
        {
            "id": "hood_outer_surface",
            "kind": "nurbs_revolve_surface",
            "role": "front_hood_outer_surface",
            "ontology_id": "front_hood_shell",
            "material": True,
            "material_domain": "front_hood",
            "wall_thickness_mm": _round(thickness),
            "profile": outer_profile,
            "uv_grid": _revolve_grid(outer_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(outer_profile, SURFACE_U_COUNT),
            "display": {"color": "#b6cbd5", "opacity": 0.68},
            "boundary_ids": ["hood_outer_inlet_circle", "hood_outer_outlet_circle"],
        },
        {
            "id": "hood_inlet_cap_surface",
            "kind": "annular_axial_cap_surface",
            "role": "hood_cap",
            "material": True,
            "material_domain": "front_hood",
            "uv_grid": _axial_cap_grid(inlet_inner[0], inlet_inner[1], inlet_outer[1], SURFACE_V_COUNT),
            "display": {"color": "#a7bfca", "opacity": 0.7},
            "boundary_ids": ["shroud_inlet_circle", "hood_outer_inlet_circle"],
        },
        {
            "id": "hood_outlet_cap_surface",
            "kind": "annular_axial_cap_surface",
            "role": "hood_cap",
            "material": True,
            "material_domain": "front_hood",
            "uv_grid": _axial_cap_grid(outlet_inner[0], outlet_inner[1], outlet_outer[1], SURFACE_V_COUNT),
            "display": {"color": "#a7bfca", "opacity": 0.7},
            "boundary_ids": ["shroud_outlet_circle", "hood_outer_outlet_circle"],
        },
        {
            "id": "hood_chamfer_outlet_surface",
            "kind": "chamfer_surface",
            "role": "hood_chamfer",
            "material": True,
            "material_domain": "front_hood",
            "radius_mm": _round(params["hood_chamfer_radius_mm"]),
            "uv_grid": _chamfer_band_grid(max(1.0, outlet_inner[0] - chamfer), outlet_inner[0], outlet_inner[1], outlet_inner[1] + chamfer),
            "display": {"color": "#c5d4da", "opacity": 0.76},
            "boundary_ids": ["hood_outlet_chamfer_a", "hood_outlet_chamfer_b"],
        },
    ]
    return surfaces


def _construction_lines(
    surface_graph: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    lines = {
        "hub": [],
        "blade_u": [],
        "blade_v": [],
        "blade_boundaries": _blade_boundary_lines(sampled_blades),
        "blade_edges": _blade_edge_lines(sampled_blades),
        "shroud": [],
        "passage": [],
        "surface_uv": _surface_uv_lines(surface_graph),
    }
    for surface in surface_graph["surfaces"]:
        if surface.get("material_domain") == "hub" or surface["id"] == "hub_revolve_surface":
            lines["hub"].extend(_sparse_surface_lines(surface))
        elif surface["id"] == "shroud_surface":
            lines["shroud"].extend(_sparse_surface_lines(surface))
    for blade in sampled_blades:
        prefix = f"blade {blade['index']}"
        for u_index in range(0, BLADE_U_COUNT, 4):
            lines["blade_u"].append(
                {
                    "name": f"{prefix} camber u{u_index}",
                    "source": "axisymmetric_throughflow_nurbs.mean_surface",
                    "points": blade["mean_surface"][u_index],
                }
            )
        for v_index in range(0, BLADE_V_COUNT, 2):
            lines["blade_v"].append(
                {
                    "name": f"{prefix} camber v{v_index}",
                    "source": "axisymmetric_throughflow_nurbs.mean_surface",
                    "points": [row[v_index] for row in blade["mean_surface"]],
                }
            )
    return lines


def _surface_uv_lines(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    lines = []
    for surface in surface_graph["surfaces"]:
        grid = surface["uv_grid"]
        for u_index in range(0, len(grid), max(1, len(grid) // 10)):
            lines.append(
                {
                    "name": f"{surface['id']} u{u_index}",
                    "surface_id": surface["id"],
                    "direction": "u",
                    "source": "axisymmetric_throughflow_nurbs.surface_graph",
                    "points": grid[u_index],
                }
            )
        for v_index in range(0, len(grid[0]), max(1, len(grid[0]) // 8)):
            lines.append(
                {
                    "name": f"{surface['id']} v{v_index}",
                    "surface_id": surface["id"],
                    "direction": "v",
                    "source": "axisymmetric_throughflow_nurbs.surface_graph",
                    "points": [row[v_index] for row in grid],
                }
            )
    return lines


def _blade_boundary_lines(sampled_blades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = []
    for blade in sampled_blades:
        blade_index = int(blade["index"])
        for role, color in [
            ("blade_root_boundary", "#22c55e"),
            ("blade_tip_boundary", "#38bdf8"),
            ("leading_edge_boundary", "#f59e0b"),
            ("trailing_edge_boundary", "#ef4444"),
        ]:
            lines.append(
                {
                    "name": f"blade {blade_index} {role}",
                    "role": role,
                    "blade_index": blade_index,
                    "source": "axisymmetric_throughflow_nurbs.named_boundary_curve",
                    "color": color,
                    "points": blade[role],
                }
            )
    return lines


def _blade_edge_lines(sampled_blades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = []
    for blade in sampled_blades:
        blade_index = int(blade["index"])
        edge_specs = [
            ("leading_edge_pressure", "leading_edge_surface", 0, "#f59e0b"),
            ("leading_edge_suction", "leading_edge_surface", -1, "#f59e0b"),
            ("trailing_edge_pressure", "trailing_edge_surface", 0, "#ef4444"),
            ("trailing_edge_suction", "trailing_edge_surface", -1, "#ef4444"),
            ("root_edge_pressure", "root_closure_surface", 0, "#22c55e"),
            ("root_edge_suction", "root_closure_surface", -1, "#22c55e"),
            ("tip_edge_pressure", "tip_closure_surface", 0, "#38bdf8"),
            ("tip_edge_suction", "tip_closure_surface", -1, "#38bdf8"),
        ]
        for role, surface_key, column_index, color in edge_specs:
            lines.append(
                {
                    "name": f"blade {blade_index} {role}",
                    "role": role,
                    "blade_index": blade_index,
                    "source": "axisymmetric_throughflow_nurbs.edge_closure_surface",
                    "surface_id": f"blade_{blade_index}_{surface_key}",
                    "color": color,
                    "points": [row[column_index] for row in blade[surface_key]],
                }
            )
    return lines


def _normalize_geometry_stage(stage: str | None) -> str:
    normalized = str(stage or "edge_closures")
    aliases = {
        "hub": "hub_support",
        "blades": "blade_surfaces",
        "edges": "edge_closures",
        "full": "edge_closures",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"hub_support", "blade_surfaces", "edge_closures"}:
        raise ValueError(f"invalid geometry stage: {stage}")
    return normalized


def _filter_by_geometry_stage(
    surface_graph: dict[str, Any],
    construction_lines: dict[str, list[dict[str, Any]]],
    geometry_stage: str,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    allowed_surfaces = [
        surface
        for surface in surface_graph["surfaces"]
        if _surface_visible_in_stage(surface, geometry_stage)
    ]
    allowed_ids = {surface["id"] for surface in allowed_surfaces}
    filtered_graph = {
        "surfaces": allowed_surfaces,
        "edges": [
            edge
            for edge in surface_graph["edges"]
            if all(surface_id in allowed_ids for surface_id in edge.get("surfaces", []))
        ],
        "boundary_curves": {} if geometry_stage == "hub_support" else _filtered_boundary_curves(surface_graph.get("boundary_curves", {}), geometry_stage),
        "named_boundary_curves": [] if geometry_stage == "hub_support" else surface_graph.get("named_boundary_curves", []),
    }
    filtered_lines = {key: list(value) for key, value in construction_lines.items()}
    filtered_lines["surface_uv"] = [
        line
        for line in construction_lines.get("surface_uv", [])
        if line.get("surface_id") in allowed_ids
    ]
    if geometry_stage == "hub_support":
        for key in ["blade_u", "blade_v", "blade_boundaries", "blade_edges"]:
            filtered_lines[key] = []
    elif geometry_stage == "blade_surfaces":
        filtered_lines["blade_edges"] = []
    return filtered_graph, filtered_lines


def _surface_visible_in_stage(surface: dict[str, Any], geometry_stage: str) -> bool:
    role = surface.get("role")
    if role in {
        "hub",
        "outer_hub_shell",
        "inner_hub_bottom",
        "hub_top_cap",
        "mounting_bore",
        "hub_chamfer",
        "reference_only",
        "construction_support_only",
        "front_shroud_inner_surface",
        "front_hood_outer_surface",
        "hood_cap",
        "hood_chamfer",
    }:
        return True
    if geometry_stage == "hub_support":
        return False
    if role in {"blade_pressure", "blade_suction"}:
        return True
    if geometry_stage == "blade_surfaces":
        return False
    return surface.get("kind") == "edge_closure_surface"


def _filtered_boundary_curves(boundary_curves: dict[str, Any], geometry_stage: str) -> dict[str, Any]:
    if geometry_stage == "edge_closures":
        return boundary_curves
    return {
        key: value
        for key, value in boundary_curves.items()
        if not key.endswith(("_leading_edge", "_trailing_edge", "_root_closure", "_tip_closure"))
    }


def _sparse_surface_lines(surface: dict[str, Any]) -> list[dict[str, Any]]:
    lines = []
    grid = surface["uv_grid"]
    for u_index in range(0, len(grid), 8):
        lines.append(
            {
                "name": f"{surface['id']} sparse u{u_index}",
                "source": "axisymmetric_throughflow_nurbs.surface_graph",
                "points": grid[u_index],
            }
        )
    return lines


def _surface_hidden_by_policy(surface_key: str, display_policy: dict[str, Any] | None) -> bool:
    hidden = set((display_policy or {}).get("hide_surfaces", []))
    return surface_key in hidden


def _apply_display_policy(surface_graph: dict[str, Any], display_policy: dict[str, Any] | None) -> dict[str, Any]:
    hidden = set((display_policy or {}).get("hide_surfaces", []))
    if not hidden:
        return surface_graph
    surfaces = [
        surface
        for surface in surface_graph["surfaces"]
        if surface["id"] not in hidden and surface.get("ontology_id") not in hidden
    ]
    visible_ids = {surface["id"] for surface in surfaces}
    return {
        **surface_graph,
        "surfaces": surfaces,
        "edges": [
            edge
            for edge in surface_graph["edges"]
            if all(surface_id in visible_ids for surface_id in edge.get("surfaces", []))
        ],
        "construction_support_surfaces": [
            surface
            for surface in surface_graph["surfaces"]
            if surface["id"] in hidden or surface.get("ontology_id") in hidden
        ],
    }


def _validity_report(
    surface_graph: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
    construction_lines: dict[str, list[dict[str, Any]]],
    params: dict[str, float],
    facets: dict[str, str],
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topology_checks = [_check_stage_completeness(surface_graph, geometry_stage)]
    if geometry_stage in {"blade_surfaces", "edge_closures"}:
        topology_checks.extend(
            [
                _check_boundary_column(sampled_blades, "pressure_surface", "pressure_hub_boundary", 0, "pressure_surface_hub_conformance"),
                _check_boundary_column(sampled_blades, "suction_surface", "suction_hub_boundary", 0, "suction_surface_hub_conformance"),
                _check_boundary_column(sampled_blades, "pressure_surface", "pressure_tip_boundary", -1, "pressure_surface_tip_conformance"),
                _check_boundary_column(sampled_blades, "suction_surface", "suction_tip_boundary", -1, "suction_surface_tip_conformance"),
            ]
        )
    if geometry_stage == "edge_closures":
        topology_checks.extend(
            [
                _check_blade_edge_surfaces_present(surface_graph, sampled_blades),
                _check_blade_surface_closure_candidate(surface_graph, sampled_blades),
            ]
        )
    topology_checks.append(_check_every_surface_has_uv_lines(surface_graph, construction_lines))
    if _requires_capped_hub(material_domain):
        topology_checks.append(_check_hub_solid_has_caps_and_bore(surface_graph))
    if _surface_hidden_by_policy("blade_tip_support_surface", display_policy):
        topology_checks.append(_check_open_tip_support_hidden_from_display_graph(surface_graph, facets))
    if facets["shroud_topology"] == "closed" and (material_domain or {}).get("front_shroud", {}).get("kind") == "finite_thickness_revolved_shell":
        topology_checks.append(_check_closed_hood_shell_surfaces_present(surface_graph))
    geometry_checks = [
        _check_finite_surface_points(surface_graph),
        _check_positive_radii(surface_graph),
        _check_hub_profile_bottom_radius_larger(surface_graph),
        _check_material_domain_positive_thickness(params, facets, material_domain),
        {
            "name": "profile_validity",
            "status": "PASS",
            "note": "hub and tip profiles were validated before sampling",
        },
        {
            "name": "curve_override_validity",
            "status": "PASS",
            "note": "intrinsic curve overrides were validated before sampling",
        },
        {
            "name": "high_density_sampling",
            "status": "PASS",
            "surface_u_count": SURFACE_U_COUNT,
            "surface_v_count": SURFACE_V_COUNT,
            "blade_u_count": BLADE_U_COUNT,
            "blade_v_count": BLADE_V_COUNT,
        },
    ]
    engineering_checks = [
        {
            "name": "engineering_rules",
            "status": "NOT_EVALUATED",
            "note": "CFD/FEA/DFMA checks are not implemented in this stage",
        }
    ]
    status = "PASS" if all(check["status"] == "PASS" for check in geometry_checks + topology_checks) else "FAIL"
    return {
        "status": status,
        "geometry_checks": geometry_checks,
        "topology_checks": topology_checks,
        "engineering_checks": engineering_checks,
    }


def _requires_capped_hub(material_domain: dict[str, Any] | None) -> bool:
    return (material_domain or {}).get("hub", {}).get("kind") == "capped_revolved_solid_with_bore"


def _check_material_domain_positive_thickness(
    params: dict[str, float],
    facets: dict[str, str],
    material_domain: dict[str, Any] | None,
) -> dict[str, Any]:
    required = [
        "hub_wall_thickness_mm",
        "hub_bottom_thickness_mm",
        "hub_top_cap_thickness_mm",
    ]
    if facets["shroud_topology"] == "closed" and (material_domain or {}).get("front_shroud", {}).get("kind") == "finite_thickness_revolved_shell":
        required.append("hood_wall_thickness_mm")
    failing = [name for name in required if params.get(name, 0.0) <= 0.0]
    return {
        "name": "material_domain_positive_thickness",
        "status": "FAIL" if failing else "PASS",
        "checked_parameters": required,
        "failing_parameters": failing,
    }


def _check_hub_solid_has_caps_and_bore(surface_graph: dict[str, Any]) -> dict[str, str]:
    surface_ids = {surface["id"] for surface in surface_graph["surfaces"]}
    required = {
        "hub_revolve_surface",
        "inner_hub_bottom_face",
        "hub_top_cap_face",
        "mounting_bore_cylinder",
    }
    return {
        "name": "hub_solid_has_caps_and_bore",
        "status": "PASS" if required.issubset(surface_ids) else "FAIL",
    }


def _check_open_tip_support_hidden_from_display_graph(
    surface_graph: dict[str, Any],
    facets: dict[str, str],
) -> dict[str, str]:
    if facets["shroud_topology"] != "open":
        return {"name": "open_tip_support_surface_hidden_from_display_graph", "status": "PASS"}
    present = any(surface.get("ontology_id") == "blade_tip_support_surface" for surface in surface_graph["surfaces"])
    return {
        "name": "open_tip_support_surface_hidden_from_display_graph",
        "status": "FAIL" if present else "PASS",
    }


def _check_closed_hood_shell_surfaces_present(surface_graph: dict[str, Any]) -> dict[str, str]:
    surface_ids = {surface["id"] for surface in surface_graph["surfaces"]}
    required = {
        "shroud_surface",
        "hood_outer_surface",
        "hood_inlet_cap_surface",
        "hood_outlet_cap_surface",
    }
    return {
        "name": "closed_hood_shell_surfaces_present",
        "status": "PASS" if required.issubset(surface_ids) else "FAIL",
    }


def _check_stage_completeness(surface_graph: dict[str, Any], geometry_stage: str) -> dict[str, Any]:
    roles = {surface["role"] for surface in surface_graph["surfaces"]}
    kinds = {surface["kind"] for surface in surface_graph["surfaces"]}
    if geometry_stage == "hub_support":
        passed = "hub" in roles and "blade_pressure" not in roles and "edge_closure_surface" not in kinds
    elif geometry_stage == "blade_surfaces":
        passed = "hub" in roles and "blade_pressure" in roles and "edge_closure_surface" not in kinds
    else:
        passed = "hub" in roles and "blade_pressure" in roles and "edge_closure_surface" in kinds
    return {
        "name": "stage_completeness",
        "status": "PASS" if passed else "FAIL",
        "geometry_stage": geometry_stage,
    }


def _check_boundary_column(
    blades: list[dict[str, Any]],
    surface_key: str,
    boundary_key: str,
    column_index: int,
    name: str,
) -> dict[str, Any]:
    max_distance = 0.0
    for blade in blades:
        for row, boundary_point in zip(blade[surface_key], blade[boundary_key]):
            max_distance = max(max_distance, _distance(row[column_index], boundary_point))
    rounded = _round(max_distance)
    return {
        "name": name,
        "status": "PASS" if rounded <= 0.001 else "FAIL",
        "max_distance_mm": rounded,
        "tolerance_mm": 0.001,
    }


def _check_every_surface_has_uv_lines(
    surface_graph: dict[str, Any],
    construction_lines: dict[str, list[dict[str, Any]]],
) -> dict[str, str]:
    declared = {surface["id"] for surface in surface_graph["surfaces"]}
    line_surface_ids = {line["surface_id"] for line in construction_lines.get("surface_uv", [])}
    return {
        "name": "every_surface_has_uv_lines",
        "status": "PASS" if declared.issubset(line_surface_ids) else "FAIL",
    }


def _check_blade_edge_surfaces_present(
    surface_graph: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
) -> dict[str, str]:
    surface_ids = {surface["id"] for surface in surface_graph["surfaces"]}
    for blade in sampled_blades:
        prefix = f"blade_{blade['index']}"
        required = {
            f"{prefix}_leading_edge_surface",
            f"{prefix}_trailing_edge_surface",
            f"{prefix}_root_closure_surface",
            f"{prefix}_tip_closure_surface",
        }
        if not required.issubset(surface_ids):
            return {"name": "blade_edge_surfaces_present", "status": "FAIL"}
    return {"name": "blade_edge_surfaces_present", "status": "PASS"}


def _check_blade_surface_closure_candidate(
    surface_graph: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
) -> dict[str, Any]:
    surfaces = {surface["id"]: surface for surface in surface_graph["surfaces"]}
    max_distance = 0.0
    for blade in sampled_blades:
        prefix = f"blade_{blade['index']}"
        pressure = surfaces[f"{prefix}_pressure_surface"]["uv_grid"]
        suction = surfaces[f"{prefix}_suction_surface"]["uv_grid"]
        leading = surfaces[f"{prefix}_leading_edge_surface"]["uv_grid"]
        trailing = surfaces[f"{prefix}_trailing_edge_surface"]["uv_grid"]
        root = surfaces[f"{prefix}_root_closure_surface"]["uv_grid"]
        tip = surfaces[f"{prefix}_tip_closure_surface"]["uv_grid"]
        pairs = [
            (leading[0][0], pressure[0][0]),
            (leading[0][-1], suction[0][0]),
            (leading[-1][0], pressure[0][-1]),
            (leading[-1][-1], suction[0][-1]),
            (trailing[0][0], pressure[-1][0]),
            (trailing[0][-1], suction[-1][0]),
            (trailing[-1][0], pressure[-1][-1]),
            (trailing[-1][-1], suction[-1][-1]),
            (root[0][0], pressure[0][0]),
            (root[0][-1], suction[0][0]),
            (root[-1][0], pressure[-1][0]),
            (root[-1][-1], suction[-1][0]),
            (tip[0][0], pressure[0][-1]),
            (tip[0][-1], suction[0][-1]),
            (tip[-1][0], pressure[-1][-1]),
            (tip[-1][-1], suction[-1][-1]),
        ]
        for first, second in pairs:
            max_distance = max(max_distance, _distance(first, second))
    rounded = _round(max_distance)
    return {
        "name": "blade_surface_closure_candidate",
        "status": "PASS" if rounded <= 0.001 else "FAIL",
        "max_distance_mm": rounded,
        "tolerance_mm": 0.001,
    }


def _check_finite_surface_points(surface_graph: dict[str, Any]) -> dict[str, str]:
    for surface in surface_graph["surfaces"]:
        for row in surface["uv_grid"]:
            for point in row:
                if not all(math.isfinite(value) for value in point):
                    return {"name": "finite_surface_points", "status": "FAIL"}
    return {"name": "finite_surface_points", "status": "PASS"}


def _check_positive_radii(surface_graph: dict[str, Any]) -> dict[str, str]:
    for surface in surface_graph["surfaces"]:
        for row in surface["uv_grid"]:
            for point in row:
                if math.hypot(point[0], point[1]) <= 0.0:
                    return {"name": "positive_radii", "status": "FAIL"}
    return {"name": "positive_radii", "status": "PASS"}


def _check_hub_profile_bottom_radius_larger(surface_graph: dict[str, Any]) -> dict[str, str]:
    hub = next(surface for surface in surface_graph["surfaces"] if surface["id"] == "hub_revolve_surface")
    control_points = hub["profile"]["control_points"]
    bottom = min(control_points, key=lambda point: point[1])
    top = max(control_points, key=lambda point: point[1])
    return {
        "name": "hub_profile_bottom_radius_larger",
        "status": "PASS" if bottom[0] > top[0] else "FAIL",
    }


def _revolve_grid(profile: dict[str, Any], u_count: int, v_count: int) -> list[list[list[float]]]:
    return [
        [
            _revolve_point(profile, u_index / (u_count - 1), 2.0 * math.pi * v_index / (v_count - 1))
            for v_index in range(v_count)
        ]
        for u_index in range(u_count)
    ]


def _revolve_point(profile: dict[str, Any], u: float, theta: float) -> list[float]:
    r, z = _profile_point(profile, u)
    return _polar_point(r, theta, z)


def _profile_samples_rz(profile: dict[str, Any], count: int) -> list[dict[str, float]]:
    samples = []
    for index in range(count):
        u = index / (count - 1)
        r, z = _profile_point(profile, u)
        samples.append({"u": _round(u), "r_mm": _round(r), "z_mm": _round(z)})
    return samples


def _annular_plane_grid(
    inner_radius: float,
    outer_radius: float,
    z: float,
    radial_count: int,
    theta_count: int,
) -> list[list[list[float]]]:
    return [
        [
            _polar_point(
                inner_radius + (outer_radius - inner_radius) * radial_index / (radial_count - 1),
                2.0 * math.pi * theta_index / (theta_count - 1),
                z,
            )
            for theta_index in range(theta_count)
        ]
        for radial_index in range(radial_count)
    ]


def _chamfer_band_grid(
    inner_radius: float,
    outer_radius: float,
    z_min: float,
    z_max: float,
) -> list[list[list[float]]]:
    return [
        [
            _polar_point(
                inner_radius + (outer_radius - inner_radius) * radial_index / 2,
                2.0 * math.pi * theta_index / (SURFACE_V_COUNT - 1),
                z_min + (z_max - z_min) * radial_index / 2,
            )
            for theta_index in range(SURFACE_V_COUNT)
        ]
        for radial_index in range(3)
    ]


def _axial_cap_grid(
    radius: float,
    z_min: float,
    z_max: float,
    theta_count: int,
) -> list[list[list[float]]]:
    return [
        [
            _polar_point(radius, 2.0 * math.pi * theta_index / (theta_count - 1), z)
            for theta_index in range(theta_count)
        ]
        for z in [z_min, z_max]
    ]


def _cylinder_grid(
    radius: float,
    z_min: float,
    z_max: float,
    z_count: int,
    theta_count: int,
) -> list[list[list[float]]]:
    return [
        [
            _polar_point(
                radius,
                2.0 * math.pi * theta_index / (theta_count - 1),
                z_min + (z_max - z_min) * z_index / (z_count - 1),
            )
            for theta_index in range(theta_count)
        ]
        for z_index in range(z_count)
    ]


def _control_net_from_grid(grid: list[list[list[float]]]) -> list[list[list[float]]]:
    u_indices = [0, len(grid) // 3, (len(grid) * 2) // 3, len(grid) - 1]
    v_indices = [0, len(grid[0]) // 3, (len(grid[0]) * 2) // 3, len(grid[0]) - 1]
    return [[grid[u_index][v_index] for v_index in v_indices] for u_index in u_indices]


def _section_metadata(
    hub_curve: list[dict[str, float]],
    tip_curve: list[dict[str, float]],
    params: dict[str, float],
) -> list[dict[str, float]]:
    sections = []
    for index in [0, 10, 20, 30, 40]:
        hub = hub_curve[index]
        tip = tip_curve[index]
        sections.append(
            {
                "t": hub["u"],
                "radius_mm": hub["r_mm"],
                "height_mm": _round(tip["z_mm"] - hub["z_mm"]),
                "z_base_mm": hub["z_mm"],
                "z_tip_mm": tip["z_mm"],
                "wrap_deg": _round(params["blade_wrap_deg"] * _smoothstep(hub["u"])),
            }
        )
    return sections


def _cad_features(facets: dict[str, str]) -> list[str]:
    features = [
        "axisymmetric_nurbs_hub_surface",
        "inner_hub_solid_with_mounting_bore",
        "outer_hub_shell_surface",
        "axisymmetric_nurbs_tip_or_shroud_surface",
        "pressure_suction_nurbs_blade_surfaces",
        "blade_edge_closure_surfaces",
        "throughflow_channel_nurbs",
        f"{facets['flow_topology']}_flow_nurbs",
    ]
    if facets["shroud_topology"] == "closed":
        features.append("closed_shroud_nurbs_surface")
    else:
        features.append("open_tip_reference_nurbs_surface")
    return features


def _cubic_basis(u: float) -> list[float]:
    one = 1.0 - u
    return [one**3, 3.0 * one * one * u, 3.0 * one * u * u, u**3]


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _polar_point(radius: float, theta: float, z: float) -> list[float]:
    return _round_point(radius * math.cos(theta), radius * math.sin(theta), z)


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second)))


def _round_point(x: float, y: float, z: float) -> list[float]:
    return [_round(x), _round(y), _round(z)]


def _round(value: float) -> float:
    return round(float(value), ROUND_DIGITS)
