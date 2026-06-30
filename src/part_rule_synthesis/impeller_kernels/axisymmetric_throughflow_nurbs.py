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
) -> dict[str, Any]:
    params = _normalized_parameters(parameters)
    resolved_facets = _normalized_facets(facets)
    hub_profile, tip_profile = _profile_definitions(params, resolved_facets)
    hub_curve = _sample_profile_curve(hub_profile, SURFACE_U_COUNT)
    tip_curve = _sample_profile_curve(tip_profile, SURFACE_U_COUNT)
    sampled_blades = _pattern_blades(params, resolved_facets, hub_profile, tip_profile)
    surface_graph = _surface_graph(params, resolved_facets, hub_profile, tip_profile, sampled_blades)
    construction_lines = _construction_lines(surface_graph, sampled_blades)
    validity = _validity_report(surface_graph, sampled_blades, construction_lines)
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


def _profile_definitions(
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


def _nurbs_curve(curve_id: str, control_points: list[list[float]]) -> dict[str, Any]:
    degree = 3
    return {
        "id": curve_id,
        "kind": "nurbs_curve",
        "degree": degree,
        "control_points": [[_round(point[0]), _round(point[1])] for point in control_points],
        "weights": [1.0 for _ in control_points],
        "knots": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0],
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
    basis = _cubic_basis(u)
    denominator = sum(basis[index] * weights[index] for index in range(4))
    r = sum(basis[index] * weights[index] * points[index][0] for index in range(4)) / denominator
    z = sum(basis[index] * weights[index] * points[index][1] for index in range(4)) / denominator
    return [r, z]


def _pattern_blades(
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    blades = []
    for blade_index in range(int(params["blade_count"])):
        base_angle = 2.0 * math.pi * blade_index / int(params["blade_count"])
        blades.append(_blade_surfaces(blade_index, base_angle, params, facets, hub_profile, tip_profile))
    return blades


def _blade_surfaces(
    blade_index: int,
    base_angle: float,
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
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
            pressure_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, 1.0))
            suction_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, -1.0))
            mean_row.append(_blade_point(hub_profile, tip_profile, u, v, base_angle, params, facets, 0.0))
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
    side: float,
) -> list[float]:
    support_u = _support_u(u, v, params)
    hub = _profile_point(hub_profile, support_u)
    tip = _profile_point(tip_profile, support_u)
    r = (1.0 - v) * hub[0] + v * tip[0]
    z = (1.0 - v) * hub[1] + v * tip[1]
    theta = _theta_field(u, v, base_angle, params, facets)
    if side:
        theta += side * _half_thickness_theta(params, u, r)
    return _polar_point(r, theta, z)


def _support_u(u: float, v: float, params: dict[str, float]) -> float:
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
) -> float:
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


def _half_thickness_theta(params: dict[str, float], u: float, radius: float) -> float:
    thickness = params["blade_thickness_mm"] * (1.0 - 0.45 * _smoothstep(u))
    return (thickness * 0.5) / max(radius, 1.0)


def _surface_graph(
    params: dict[str, float],
    facets: dict[str, str],
    hub_profile: dict[str, Any],
    tip_profile: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
) -> dict[str, Any]:
    surfaces = [
        {
            "id": "hub_revolve_surface",
            "kind": "nurbs_revolve_surface",
            "role": "hub",
            "ontology_id": "hub_support_surface",
            "material": True,
            "profile": hub_profile,
            "uv_grid": _revolve_grid(hub_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(hub_profile, SURFACE_U_COUNT),
            "display": {"color": "#7a946f", "opacity": 0.9},
            "boundary_ids": ["hub_inlet_circle", "hub_outlet_circle"],
        }
    ]
    surfaces.extend(_hub_solid_surfaces(params, hub_profile))
    tip_surface_id = "shroud_surface" if facets["shroud_topology"] == "closed" else "tip_reference_surface"
    surfaces.append(
        {
            "id": tip_surface_id,
            "kind": "nurbs_revolve_surface",
            "role": "front_shroud_inner_surface" if facets["shroud_topology"] == "closed" else "reference_only",
            "display_role": "shroud" if facets["shroud_topology"] == "closed" else "open_tip_reference",
            "ontology_id": "blade_tip_support_surface",
            "material": facets["shroud_topology"] == "closed",
            "profile": tip_profile,
            "uv_grid": _revolve_grid(tip_profile, SURFACE_U_COUNT, SURFACE_V_COUNT),
            "profile_samples_rz": _profile_samples_rz(tip_profile, SURFACE_U_COUNT),
            "display": {
                "color": "#9db7c5" if facets["shroud_topology"] == "closed" else "#c8c08d",
                "opacity": 0.34 if facets["shroud_topology"] == "open" else 0.72,
            },
            "boundary_ids": ["tip_inlet_circle", "tip_outlet_circle"],
        }
    )

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
    return {
        "surfaces": surfaces,
        "edges": edges,
        "boundary_curves": boundary_curves,
        "named_boundary_curves": named_boundary_curves,
    }


def _hub_solid_surfaces(params: dict[str, float], hub_profile: dict[str, Any]) -> list[dict[str, Any]]:
    control_points = hub_profile["control_points"]
    bottom = min(control_points, key=lambda point: point[1])
    top = max(control_points, key=lambda point: point[1])
    bore_radius = min(params["mounting_bore_radius_mm"], bottom[0] * 0.72, top[0] * 0.86)
    outer_profile = {
        **hub_profile,
        "id": "outer_hub_shell_profile",
        "control_points": [point[:] for point in hub_profile["control_points"]],
        "weights": hub_profile["weights"][:],
        "knots": hub_profile["knots"][:],
    }
    return [
        {
            "id": "outer_hub_shell_surface",
            "kind": "nurbs_revolve_surface",
            "role": "outer_hub_shell",
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
            "inner_radius_mm": _round(bore_radius),
            "outer_radius_mm": _round(bottom[0]),
            "z_mm": _round(bottom[1]),
            "uv_grid": _annular_plane_grid(bore_radius, bottom[0], bottom[1], 8, SURFACE_V_COUNT),
            "display": {"color": "#6d7f6a", "opacity": 0.82},
            "boundary_ids": ["mounting_bore_bottom_circle", "outer_hub_bottom_circle"],
        },
        {
            "id": "mounting_bore_cylinder",
            "kind": "cylindrical_surface",
            "role": "mounting_bore",
            "radius_mm": _round(bore_radius),
            "z_min_mm": _round(bottom[1]),
            "z_max_mm": _round(top[1]),
            "uv_grid": _cylinder_grid(bore_radius, bottom[1], top[1], SURFACE_U_COUNT, SURFACE_V_COUNT),
            "display": {"color": "#4b5563", "opacity": 0.86},
            "boundary_ids": ["mounting_bore_bottom_circle", "mounting_bore_top_circle"],
        },
    ]


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
        if surface["id"] == "hub_revolve_surface":
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


def _validity_report(
    surface_graph: dict[str, Any],
    sampled_blades: list[dict[str, Any]],
    construction_lines: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    topology_checks = [
        _check_boundary_column(sampled_blades, "pressure_surface", "pressure_hub_boundary", 0, "pressure_surface_hub_conformance"),
        _check_boundary_column(sampled_blades, "suction_surface", "suction_hub_boundary", 0, "suction_surface_hub_conformance"),
        _check_boundary_column(sampled_blades, "pressure_surface", "pressure_tip_boundary", -1, "pressure_surface_tip_conformance"),
        _check_boundary_column(sampled_blades, "suction_surface", "suction_tip_boundary", -1, "suction_surface_tip_conformance"),
        _check_blade_edge_surfaces_present(surface_graph, sampled_blades),
        _check_blade_surface_closure_candidate(surface_graph, sampled_blades),
        _check_every_surface_has_uv_lines(surface_graph, construction_lines),
    ]
    geometry_checks = [
        _check_finite_surface_points(surface_graph),
        _check_positive_radii(surface_graph),
        _check_hub_profile_bottom_radius_larger(surface_graph),
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
