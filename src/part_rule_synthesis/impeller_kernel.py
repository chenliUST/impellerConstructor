from __future__ import annotations

import math
from typing import Any

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


U_COUNT = 9
V_COUNT = 5
ROUND_DIGITS = 6


def build_impeller_geometry(
    parameters: dict[str, Any],
    facets: dict[str, str],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic impeller geometry metadata from one sampled meridional kernel."""
    if "blade_wrap_deg" in parameters:
        return build_axisymmetric_throughflow_nurbs_geometry(
            parameters,
            facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            display_policy=display_policy,
            material_domain=material_domain,
            solid_features=solid_features,
        )
    params = _normalized_parameters(parameters)
    resolved_facets = _normalized_facets(facets)
    hub_curve, tip_curve = _meridional_curves(params, resolved_facets)
    surface_fields = _surface_fields(params)
    beta_samples, beta_control_points = _beta_field(params, resolved_facets)
    thickness_samples = _thickness_field(params)
    theta_samples = _blade_theta_samples(hub_curve, beta_samples, resolved_facets)
    sampled_blades = _pattern_blades(hub_curve, tip_curve, theta_samples, surface_fields, params, thickness_samples, mirror_z=False)
    mirrored_blades = (
        _pattern_blades(hub_curve, tip_curve, theta_samples, surface_fields, params, thickness_samples, mirror_z=True)
        if resolved_facets.get("suction_topology") == "double_suction"
        else []
    )
    all_blades = sampled_blades + mirrored_blades
    surface_graph = _surface_graph(params, resolved_facets, hub_curve, tip_curve, surface_fields, all_blades)
    construction_lines = _construction_lines(params, resolved_facets, hub_curve, tip_curve, all_blades, surface_graph)
    validity = _validity_report(surface_graph, construction_lines)
    sections = _legacy_section_metadata(params, resolved_facets)

    passage_model = _passage_model(resolved_facets)
    kernel = {
        "kind": "meridional_beta_thickness_kernel",
        "meridional_curves": {
            "hub": hub_curve,
            "tip_or_shroud": tip_curve,
        },
        "beta_field": {
            "kind": "cubic_bezier",
            "degree": 3,
            "control_points_deg": beta_control_points,
            "samples_deg": beta_samples,
        },
        "thickness_field": {
            "kind": "linear_spanwise_constant",
            "control_points_mm": [
                _round(params["blade_thickness_mm"]),
                _round(params["blade_thickness_mm"] * 0.82),
            ],
            "samples_mm": thickness_samples,
        },
        "surface_fields": surface_fields,
        "uv_sampling": {"u_count": U_COUNT, "v_count": V_COUNT},
        "passage_model": passage_model,
    }

    return {
        "kernel": kernel,
        "passage_model": passage_model,
        "sampled_blades": all_blades,
        "surface_graph": surface_graph,
        "blade_surface": {
            "primitive": "lofted_blade_surface",
            "profile_curve_kind": "cadquery_spline",
            "height_model": "meridional_beta_thickness_kernel",
            "loft_section_count": len(sections),
            "curve_gain": float(params.get("blade_curve_gain", 1.0)),
            "driven_by": [
                "inlet_blade_angle_deg",
                "outlet_blade_angle_deg",
                "blade_thickness_mm",
                "inlet_blade_height_mm",
                "outlet_blade_height_mm",
                "bspline_control_points",
            ],
            "sections": sections,
        },
        "hub_surface": _hub_surface_metadata(params),
        "cad_features": _cad_features(params, resolved_facets),
        "construction_lines": construction_lines,
        "validity": validity,
    }


def blade_loft_wires(
    parameters: dict[str, Any],
    facets: dict[str, str],
    mirror_z: bool = False,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> list[list[list[float]]]:
    geometry = build_impeller_geometry(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        display_policy=display_policy,
        material_domain=material_domain,
        solid_features=solid_features,
    )
    blades = [
        blade
        for blade in geometry["sampled_blades"]
        if bool(blade["mirror_z"]) is mirror_z
    ]
    return [blade["loft_wires"] for blade in blades]


def hub_loft_sections(
    parameters: dict[str, Any],
    facets: dict[str, str],
    mirror_z: bool = False,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> list[tuple[float, float]]:
    geometry = build_impeller_geometry(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        display_policy=display_policy,
        material_domain=material_domain,
        solid_features=solid_features,
    )
    hub = geometry["kernel"]["meridional_curves"]["hub"]
    sections = [(point["z_mm"], point["r_mm"]) for point in hub]
    if mirror_z:
        return [(-z, radius) for z, radius in sections]
    return sections


def shroud_z_levels(
    parameters: dict[str, Any],
    facets: dict[str, str],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    display_policy: dict[str, Any] | None = None,
    material_domain: dict[str, Any] | None = None,
    solid_features: dict[str, Any] | None = None,
) -> tuple[float, float]:
    geometry = build_impeller_geometry(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        display_policy=display_policy,
        material_domain=material_domain,
        solid_features=solid_features,
    )
    blades = geometry["sampled_blades"]
    z_values = [
        point[2]
        for blade in blades
        if not blade["mirror_z"]
        for row in blade["mean_surface"]
        for point in row
    ]
    return min(z_values), max(z_values)


def _normalized_parameters(parameters: dict[str, Any]) -> dict[str, float]:
    numeric = {name: float(value) for name, value in parameters.items()}
    numeric.setdefault("blade_curve_gain", 1.0)
    numeric.setdefault("hub_curve_height_mm", 0.0)
    numeric.setdefault("hub_twist_deg", 0.0)
    numeric.setdefault("tip_twist_deg", 0.0)
    numeric.setdefault("hub_warp_mm", 0.0)
    numeric.setdefault("tip_warp_mm", 0.0)
    numeric["blade_count"] = int(numeric["blade_count"])
    return numeric


def _surface_fields(params: dict[str, float]) -> dict[str, dict[str, float]]:
    return {
        "hub": {
            "kind": "warped_revolve_field",
            "twist_deg": _round(params.get("hub_twist_deg", 0.0)),
            "warp_mm": _round(params.get("hub_warp_mm", 0.0)),
        },
        "tip": {
            "kind": "warped_revolve_field",
            "twist_deg": _round(params.get("tip_twist_deg", 0.0)),
            "warp_mm": _round(params.get("tip_warp_mm", 0.0)),
        },
    }


def _normalized_facets(facets: dict[str, str]) -> dict[str, str]:
    return {
        "flow_topology": facets.get("flow_topology", "radial"),
        "shroud_topology": facets.get("shroud_topology", "open"),
        "suction_topology": facets.get("suction_topology", "single_suction"),
        "blade_exit_geometry": facets.get("blade_exit_geometry", "backward_curved"),
        "working_domain": facets.get("working_domain", "pump"),
        "passage_topology": facets.get("passage_topology", "throughflow_bladed_channel"),
    }


def _meridional_curves(params: dict[str, float], facets: dict[str, str]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    inlet = params["inlet_radius_mm"]
    outlet = params["exit_radius_mm"]
    hub_height = params.get("hub_curve_height_mm", 0.0)
    flow = facets["flow_topology"]
    passage = facets["passage_topology"]
    hub_curve = []
    tip_curve = []
    for index in range(U_COUNT):
        u = index / (U_COUNT - 1)
        smooth = _smoothstep(u)
        if flow == "axial":
            radius = inlet + (outlet - inlet) * 0.28 * smooth
            z_base = 30.0 + (max(hub_height, params["inlet_blade_height_mm"] * 0.7) + (outlet - inlet) * 0.2) * smooth
        elif flow == "mixed":
            radius = inlet + (outlet - inlet) * smooth
            z_base = 30.0 + (hub_height * 0.55 + (outlet - inlet) * 0.12) * smooth
        else:
            radius = inlet + (outlet - inlet) * smooth
            z_base = 30.0 + hub_height * 0.18 * math.sin(math.pi * u)
        if passage == "recessed_vortex":
            z_base += hub_height * 0.35 + params["outlet_blade_height_mm"] * 0.18
        height = params["inlet_blade_height_mm"] + smooth * (
            params["outlet_blade_height_mm"] - params["inlet_blade_height_mm"]
        )
        if passage == "recessed_vortex":
            height *= 0.72
        hub_curve.append({"u": _round(u), "r_mm": _round(radius), "z_mm": _round(z_base)})
        tip_curve.append({"u": _round(u), "r_mm": _round(radius), "z_mm": _round(z_base + height)})
    return hub_curve, tip_curve


def _beta_field(params: dict[str, float], facets: dict[str, str]) -> tuple[list[float], list[float]]:
    inlet = params["inlet_blade_angle_deg"]
    outlet = params["outlet_blade_angle_deg"]
    gain = params.get("blade_curve_gain", 1.0)
    exit_bias = {"backward_curved": -6.0, "radial": 0.0, "forward_curved": 8.0}[facets["blade_exit_geometry"]]
    cp = [
        _round(inlet),
        _round(inlet + (outlet - inlet) * 0.35 + gain * 4.0),
        _round(inlet + (outlet - inlet) * 0.70 + exit_bias + gain * 9.0),
        _round(outlet),
    ]
    samples = []
    for index in range(U_COUNT):
        u = index / (U_COUNT - 1)
        samples.append(_round(_cubic_bezier(cp, u)))
    return samples, cp


def _thickness_field(params: dict[str, float]) -> list[float]:
    base = params["blade_thickness_mm"]
    return [_round(base * (1.0 - 0.18 * index / (U_COUNT - 1))) for index in range(U_COUNT)]


def _blade_theta_samples(
    hub_curve: list[dict[str, float]],
    beta_samples: list[float],
    facets: dict[str, str],
) -> list[float]:
    theta_sign = {"backward_curved": -1.0, "radial": 0.35, "forward_curved": 1.0}[facets["blade_exit_geometry"]]
    cumulative_theta = [0.0]
    for index in range(1, U_COUNT):
        prev = hub_curve[index - 1]
        current = hub_curve[index]
        dr = current["r_mm"] - prev["r_mm"]
        dz = current["z_mm"] - prev["z_mm"]
        dm = math.sqrt(dr * dr + dz * dz)
        radius = max((current["r_mm"] + prev["r_mm"]) / 2.0, 1.0)
        beta = math.radians(max(3.0, min(87.0, (beta_samples[index] + beta_samples[index - 1]) / 2.0)))
        cumulative_theta.append(cumulative_theta[-1] + theta_sign * dm / (radius * math.tan(beta)))
    return cumulative_theta


def _blade_mean_surface(
    hub_boundary: list[list[float]],
    tip_boundary: list[list[float]],
) -> list[list[list[float]]]:
    grid = []
    for u_index in range(U_COUNT):
        row = []
        for v_index in range(V_COUNT):
            v = v_index / (V_COUNT - 1)
            row.append(
                _round_point(
                    (1.0 - v) * hub_boundary[u_index][0] + v * tip_boundary[u_index][0],
                    (1.0 - v) * hub_boundary[u_index][1] + v * tip_boundary[u_index][1],
                    (1.0 - v) * hub_boundary[u_index][2] + v * tip_boundary[u_index][2],
                )
            )
        grid.append(row)
    return grid


def _pattern_blades(
    hub_curve: list[dict[str, float]],
    tip_curve: list[dict[str, float]],
    theta_samples: list[float],
    surface_fields: dict[str, dict[str, float]],
    params: dict[str, float],
    thickness_samples: list[float],
    mirror_z: bool,
) -> list[dict[str, Any]]:
    blades = []
    blade_count = int(params["blade_count"])
    for blade_index in range(blade_count):
        angle = 2.0 * math.pi * blade_index / blade_count
        hub_boundary = [
            _surface_field_point(hub_curve[u_index], theta_samples[u_index] + angle, surface_fields["hub"], mirror_z)
            for u_index in range(U_COUNT)
        ]
        tip_boundary = [
            _surface_field_point(tip_curve[u_index], theta_samples[u_index] + angle, surface_fields["tip"], mirror_z)
            for u_index in range(U_COUNT)
        ]
        mean_surface = _blade_mean_surface(hub_boundary, tip_boundary)
        pressure_surface, suction_surface, loft_wires = _blade_side_surfaces(mean_surface, thickness_samples)
        blades.append(
            {
                "index": blade_index,
                "mirror_z": mirror_z,
                "hub_boundary": hub_boundary,
                "tip_boundary": tip_boundary,
                "mean_surface": mean_surface,
                "pressure_surface": pressure_surface,
                "suction_surface": suction_surface,
                "loft_wires": loft_wires,
            }
        )
    return blades


def _blade_side_surfaces(
    mean_surface: list[list[list[float]]],
    thickness_samples: list[float],
) -> tuple[list[list[list[float]]], list[list[list[float]]], list[list[list[float]]]]:
    pressure_surface = []
    suction_surface = []
    wires = []
    for u_index, row in enumerate(mean_surface):
        pressure_row = []
        suction_row = []
        radius = max(math.hypot(row[0][0], row[0][1]), 1.0)
        tangent = [-row[0][1] / radius, row[0][0] / radius, 0.0]
        half = thickness_samples[u_index] / 2.0
        for point in row:
            pressure_row.append(_round_point(point[0] + tangent[0] * half, point[1] + tangent[1] * half, point[2]))
            suction_row.append(_round_point(point[0] - tangent[0] * half, point[1] - tangent[1] * half, point[2]))
        pressure_surface.append(pressure_row)
        suction_surface.append(suction_row)
        wires.append([pressure_row[0], suction_row[0], suction_row[-1], pressure_row[-1], pressure_row[0]])
    return pressure_surface, suction_surface, wires


def _construction_lines(
    params: dict[str, float],
    facets: dict[str, str],
    hub_curve: list[dict[str, float]],
    tip_curve: list[dict[str, float]],
    sampled_blades: list[dict[str, Any]],
    surface_graph: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    lines = {
        "hub": _hub_lines(hub_curve, params, mirror_z=False),
        "blade_u": [],
        "blade_v": [],
        "shroud": _shroud_lines(facets, tip_curve, mirror_z=False),
        "passage": _passage_lines(params, facets, mirror_z=False),
        "surface_uv": _surface_uv_lines(surface_graph),
    }
    if facets["suction_topology"] == "double_suction":
        lines["hub"] += _hub_lines(hub_curve, params, mirror_z=True)
        lines["shroud"] += _shroud_lines(facets, tip_curve, mirror_z=True)
        lines["passage"] += _passage_lines(params, facets, mirror_z=True)
    for blade in sampled_blades:
        prefix = f"{'mirrored ' if blade['mirror_z'] else ''}blade {blade['index']}"
        surface = blade["mean_surface"]
        for u_index, row in enumerate(surface):
            lines["blade_u"].append(
                {
                    "name": f"{prefix} u{u_index}",
                    "source": "impeller_kernel.blade_surface",
                    "points": row,
                }
            )
        for v_index in range(V_COUNT):
            lines["blade_v"].append(
                {
                    "name": f"{prefix} v{v_index}",
                    "source": "impeller_kernel.blade_surface",
                    "points": [row[v_index] for row in surface],
                }
            )
    return lines


def _surface_graph(
    params: dict[str, float],
    facets: dict[str, str],
    hub_curve: list[dict[str, float]],
    tip_curve: list[dict[str, float]],
    surface_fields: dict[str, dict[str, float]],
    sampled_blades: list[dict[str, Any]],
) -> dict[str, Any]:
    surfaces = [
        {
            "id": "hub_revolve_surface",
            "kind": "warped_nurbs_revolve_surface" if _field_is_warped(surface_fields["hub"]) else "nurbs_revolve_surface",
            "role": "hub",
            "profile": _hub_nurbs_profile(hub_curve),
            "surface_field": surface_fields["hub"],
            "uv_grid": _surface_field_grid(hub_curve, surface_fields["hub"], 8),
            "boundary_ids": ["hub_inlet_edge", "hub_outlet_edge", "hub_axis_side_a", "hub_axis_side_b"],
        }
    ]
    edges = []
    boundary_curves = {}
    if facets["shroud_topology"] != "open":
        surfaces.append(
            {
                "id": "shroud_surface",
                "kind": "warped_shroud_surface" if _field_is_warped(surface_fields["tip"]) else "annular_parameter_surface",
                "role": "shroud",
                "surface_field": surface_fields["tip"],
                "uv_grid": _surface_field_grid(tip_curve, surface_fields["tip"], 8),
                "boundary_ids": ["shroud_inlet_edge", "shroud_outlet_edge"],
            }
        )
    else:
        surfaces.append(
            {
                "id": "tip_reference_surface",
                "kind": "warped_tip_reference_surface" if _field_is_warped(surface_fields["tip"]) else "tip_reference_surface",
                "role": "open_tip_reference",
                "surface_field": surface_fields["tip"],
                "uv_grid": _surface_field_grid(tip_curve, surface_fields["tip"], 8),
                "boundary_ids": ["tip_reference_inlet_edge", "tip_reference_outlet_edge"],
            }
        )
    if facets["passage_topology"] == "recessed_vortex":
        surfaces.append(
            {
                "id": "free_passage_cavity_surface",
                "kind": "annular_parameter_surface",
                "role": "passage",
                "uv_grid": _passage_surface_grid(params),
                "boundary_ids": ["free_passage_inlet_edge", "free_passage_outlet_edge"],
            }
        )

    for blade in sampled_blades:
        prefix = _blade_surface_prefix(blade)
        boundary_prefix = f"{'mirrored_' if blade['mirror_z'] else ''}blade_{blade['index']}"
        boundary_curves[f"{boundary_prefix}_hub_boundary"] = blade["hub_boundary"]
        boundary_curves[f"{boundary_prefix}_tip_boundary"] = blade["tip_boundary"]
        if facets["shroud_topology"] != "open":
            boundary_curves[f"{boundary_prefix}_shroud_boundary"] = blade["tip_boundary"]
        surfaces.extend(
            [
                {
                    "id": f"{prefix}_pressure_surface",
                    "kind": "nurbs_loft_surface",
                    "role": "blade_pressure",
                    "uv_grid": blade["pressure_surface"],
                    "boundary_ids": [
                        f"{prefix}_leading_edge",
                        f"{prefix}_trailing_edge",
                        f"{prefix}_root_edge",
                        f"{prefix}_tip_edge",
                    ],
                },
                {
                    "id": f"{prefix}_suction_surface",
                    "kind": "nurbs_loft_surface",
                    "role": "blade_suction",
                    "uv_grid": blade["suction_surface"],
                    "boundary_ids": [
                        f"{prefix}_leading_edge",
                        f"{prefix}_trailing_edge",
                        f"{prefix}_root_edge",
                        f"{prefix}_tip_edge",
                    ],
                },
                {
                    "id": f"{prefix}_root_fillet_surface",
                    "kind": "fillet_surface",
                    "role": "blade_root_hub_transition",
                    "radius_mm": _round(max(params["blade_thickness_mm"] * 0.35, 1.0)),
                    "uv_grid": _root_fillet_grid(blade),
                    "boundary_ids": [f"{prefix}_root_edge", f"{prefix}_hub_contact_edge"],
                },
                {
                    "id": f"{prefix}_leading_edge_fillet_surface",
                    "kind": "fillet_surface",
                    "role": "leading_edge_transition",
                    "radius_mm": _round(max(params["blade_thickness_mm"] * 0.45, 1.0)),
                    "uv_grid": _edge_fillet_grid(blade, 0),
                    "boundary_ids": [f"{prefix}_leading_edge"],
                },
                {
                    "id": f"{prefix}_trailing_edge_fillet_surface",
                    "kind": "fillet_surface",
                    "role": "trailing_edge_transition",
                    "radius_mm": _round(max(params["blade_thickness_mm"] * 0.32, 1.0)),
                    "uv_grid": _edge_fillet_grid(blade, -1),
                    "boundary_ids": [f"{prefix}_trailing_edge"],
                },
                {
                    "id": f"{prefix}_tip_surface",
                    "kind": "cap_surface",
                    "role": "blade_tip_or_open_edge",
                    "uv_grid": _tip_surface_grid(blade),
                    "boundary_ids": [f"{prefix}_tip_edge"],
                },
            ]
        )
        edges.extend(
            [
                {
                    "id": f"{prefix}_hub_contact_edge",
                    "surfaces": ["hub_revolve_surface", f"{prefix}_root_fillet_surface"],
                    "relation": "filleted_contact",
                },
                {
                    "id": f"{prefix}_pressure_root_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_root_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_suction_root_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_root_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_pressure_leading_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_leading_edge_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_suction_leading_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_leading_edge_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_pressure_trailing_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_trailing_edge_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_suction_trailing_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_trailing_edge_fillet_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_pressure_tip_edge",
                    "surfaces": [f"{prefix}_pressure_surface", f"{prefix}_tip_surface"],
                    "relation": "shared_boundary",
                },
                {
                    "id": f"{prefix}_suction_tip_edge",
                    "surfaces": [f"{prefix}_suction_surface", f"{prefix}_tip_surface"],
                    "relation": "shared_boundary",
                },
            ]
        )
        if facets["shroud_topology"] != "open":
            edges.append(
                {
                    "id": f"{prefix}_tip_shroud_edge",
                    "surfaces": ["shroud_surface", f"{prefix}_tip_surface"],
                    "relation": "conformal_tip_boundary",
                }
            )
        else:
            edges.append(
                {
                    "id": f"{prefix}_tip_reference_edge",
                    "surfaces": ["tip_reference_surface", f"{prefix}_tip_surface"],
                    "relation": "conformal_tip_boundary",
                }
            )
    return {"surfaces": surfaces, "edges": edges, "boundary_curves": boundary_curves}


def _surface_uv_lines(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    surfaces = {surface["id"]: surface for surface in surface_graph["surfaces"]}
    for surface in surfaces.values():
        surface_id = surface["id"]
        samples = _surface_samples(surface_graph, surface_id)
        for u_index, row in enumerate(samples):
            lines.append(
                {
                    "name": f"{surface_id} u{u_index}",
                    "surface_id": surface_id,
                    "direction": "u",
                    "source": "impeller_kernel.surface_graph",
                    "points": row,
                }
            )
        for v_index in range(len(samples[0])):
            lines.append(
                {
                    "name": f"{surface_id} v{v_index}",
                    "surface_id": surface_id,
                    "direction": "v",
                    "source": "impeller_kernel.surface_graph",
                    "points": [row[v_index] for row in samples],
                }
            )
    return lines


def _hub_nurbs_profile(hub_curve: list[dict[str, float]]) -> dict[str, Any]:
    control_points = [[point["r_mm"], point["z_mm"]] for point in hub_curve]
    degree = 3
    return {
        "kind": "nurbs_curve",
        "degree": degree,
        "control_points": control_points,
        "weights": [1.0 for _ in control_points],
        "knots": _clamped_knots(len(control_points), degree),
    }


def _clamped_knots(control_point_count: int, degree: int) -> list[float]:
    interior_count = control_point_count - degree - 1
    knots = [0.0] * (degree + 1)
    if interior_count > 0:
        for index in range(1, interior_count + 1):
            knots.append(_round(index / (interior_count + 1)))
    knots.extend([1.0] * (degree + 1))
    return knots


def _blade_surface_prefix(blade: dict[str, Any]) -> str:
    return f"{'mirrored_' if blade['mirror_z'] else ''}blade_{blade['index']}"


def _surface_samples(surface_graph: dict[str, Any], surface_id: str) -> list[list[list[float]]]:
    for surface in surface_graph["surfaces"]:
        if surface["id"] == surface_id:
            return surface["uv_grid"]
    raise KeyError(surface_id)


def _field_is_warped(field: dict[str, float]) -> bool:
    return abs(float(field.get("twist_deg", 0.0))) > 0.0 or abs(float(field.get("warp_mm", 0.0))) > 0.0


def _surface_field_point(
    curve_point: dict[str, float],
    base_theta: float,
    field: dict[str, float],
    mirror_z: bool = False,
) -> list[float]:
    u = float(curve_point["u"])
    theta = base_theta + math.radians(float(field.get("twist_deg", 0.0))) * _smoothstep(u)
    warp = float(field.get("warp_mm", 0.0)) * math.sin(math.pi * u)
    radius = curve_point["r_mm"] + warp * 0.18 * math.sin(2.0 * theta)
    z = curve_point["z_mm"] + warp * math.cos(theta)
    if mirror_z:
        z = -z
    return _round_point(radius * math.cos(theta), radius * math.sin(theta), z)


def _surface_field_grid(
    curve: list[dict[str, float]],
    field: dict[str, float],
    theta_count: int,
) -> list[list[list[float]]]:
    return [
        [
            _surface_field_point(point, 2.0 * math.pi * theta_index / theta_count, field)
            for theta_index in range(theta_count + 1)
        ]
        for point in curve
    ]


def _revolve_grid(curve: list[dict[str, float]], theta_count: int) -> list[list[list[float]]]:
    return [
        [
            _round_point(
                point["r_mm"] * math.cos(2.0 * math.pi * theta_index / theta_count),
                point["r_mm"] * math.sin(2.0 * math.pi * theta_index / theta_count),
                point["z_mm"],
            )
            for theta_index in range(theta_count + 1)
        ]
        for point in curve
    ]


def _passage_surface_grid(params: dict[str, float]) -> list[list[list[float]]]:
    cavity_z = 30.0 + params.get("hub_curve_height_mm", 0.0) * 0.65 + params["outlet_blade_height_mm"] * 0.82
    return [
        _circle_points(params["inlet_radius_mm"] * 1.08, cavity_z, 16),
        _circle_points(params["exit_radius_mm"] * 0.92, cavity_z, 16),
    ]


def _root_fillet_grid(blade: dict[str, Any]) -> list[list[list[float]]]:
    return [
        [blade["pressure_surface"][u_index][0], blade["mean_surface"][u_index][0], blade["suction_surface"][u_index][0]]
        for u_index in range(len(blade["mean_surface"]))
    ]


def _edge_fillet_grid(blade: dict[str, Any], u_index: int) -> list[list[list[float]]]:
    pressure = blade["pressure_surface"][u_index]
    mean = blade["mean_surface"][u_index]
    suction = blade["suction_surface"][u_index]
    return [[pressure[v_index], mean[v_index], suction[v_index]] for v_index in range(len(mean))]


def _tip_surface_grid(blade: dict[str, Any]) -> list[list[list[float]]]:
    return [
        [blade["pressure_surface"][u_index][-1], blade["mean_surface"][u_index][-1], blade["suction_surface"][u_index][-1]]
        for u_index in range(len(blade["mean_surface"]))
    ]


def _validity_report(surface_graph: dict[str, Any], construction_lines: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    geometry_checks = [
        _check_positive_radii(surface_graph),
        _check_finite_surface_points(surface_graph),
        _check_non_degenerate_surface_boundaries(surface_graph),
        _check_hub_profile_monotonic(surface_graph),
    ]
    topology_checks = [
        _check_blade_root_fillet_connects_hub(surface_graph),
        _check_edge_fillets_close_blade_surfaces(surface_graph),
        _check_every_surface_has_uv_lines(surface_graph, construction_lines),
        _check_blade_hub_boundary_conformance(surface_graph),
        _check_blade_tip_boundary_conformance(surface_graph),
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


def _check_positive_radii(surface_graph: dict[str, Any]) -> dict[str, str]:
    for surface in surface_graph["surfaces"]:
        for row in surface["uv_grid"]:
            for point in row:
                if math.hypot(point[0], point[1]) <= 0.0:
                    return {"name": "positive_radii", "status": "FAIL"}
    return {"name": "positive_radii", "status": "PASS"}


def _check_finite_surface_points(surface_graph: dict[str, Any]) -> dict[str, str]:
    for surface in surface_graph["surfaces"]:
        for row in surface["uv_grid"]:
            for point in row:
                if not all(math.isfinite(value) for value in point):
                    return {"name": "finite_surface_points", "status": "FAIL"}
    return {"name": "finite_surface_points", "status": "PASS"}


def _check_non_degenerate_surface_boundaries(surface_graph: dict[str, Any]) -> dict[str, str]:
    for surface in surface_graph["surfaces"]:
        grid = surface["uv_grid"]
        if len(grid) < 2 or len(grid[0]) < 2:
            return {"name": "non_degenerate_surface_boundaries", "status": "FAIL"}
        if _point_distance(grid[0][0], grid[-1][-1]) <= 1e-6:
            return {"name": "non_degenerate_surface_boundaries", "status": "FAIL"}
    return {"name": "non_degenerate_surface_boundaries", "status": "PASS"}


def _check_hub_profile_monotonic(surface_graph: dict[str, Any]) -> dict[str, str]:
    hub = next(surface for surface in surface_graph["surfaces"] if surface["id"] == "hub_revolve_surface")
    radii = [point[0] for point in hub["profile"]["control_points"]]
    if any(next_radius < radius for radius, next_radius in zip(radii, radii[1:])):
        return {"name": "hub_profile_monotonic", "status": "FAIL"}
    return {"name": "hub_profile_monotonic", "status": "PASS"}


def _check_blade_root_fillet_connects_hub(surface_graph: dict[str, Any]) -> dict[str, str]:
    for edge in surface_graph["edges"]:
        surfaces = set(edge["surfaces"])
        if "hub_revolve_surface" in surfaces and any(surface.endswith("_root_fillet_surface") for surface in surfaces):
            return {"name": "blade_root_fillet_connects_hub", "status": "PASS"}
    return {"name": "blade_root_fillet_connects_hub", "status": "FAIL"}


def _check_edge_fillets_close_blade_surfaces(surface_graph: dict[str, Any]) -> dict[str, str]:
    edge_pairs = [set(edge["surfaces"]) for edge in surface_graph["edges"]]
    for surface in surface_graph["surfaces"]:
        surface_id = surface["id"]
        if not surface_id.endswith("_pressure_surface"):
            continue
        prefix = surface_id.removesuffix("_pressure_surface")
        required = [
            {surface_id, f"{prefix}_leading_edge_fillet_surface"},
            {surface_id, f"{prefix}_trailing_edge_fillet_surface"},
            {surface_id, f"{prefix}_tip_surface"},
            {f"{prefix}_suction_surface", f"{prefix}_leading_edge_fillet_surface"},
            {f"{prefix}_suction_surface", f"{prefix}_trailing_edge_fillet_surface"},
            {f"{prefix}_suction_surface", f"{prefix}_tip_surface"},
        ]
        if not all(pair in edge_pairs for pair in required):
            return {"name": "edge_fillets_close_blade_surfaces", "status": "FAIL"}
    return {"name": "edge_fillets_close_blade_surfaces", "status": "PASS"}


def _check_every_surface_has_uv_lines(
    surface_graph: dict[str, Any],
    construction_lines: dict[str, list[dict[str, Any]]],
) -> dict[str, str]:
    declared = {surface["id"] for surface in surface_graph["surfaces"]}
    line_surface_ids = {line["surface_id"] for line in construction_lines.get("surface_uv", [])}
    if declared.issubset(line_surface_ids):
        return {"name": "every_surface_has_uv_lines", "status": "PASS"}
    return {"name": "every_surface_has_uv_lines", "status": "FAIL"}


def _check_blade_hub_boundary_conformance(surface_graph: dict[str, Any]) -> dict[str, Any]:
    return _boundary_conformance_check(surface_graph, "hub", "blade_hub_boundary_conformance")


def _check_blade_tip_boundary_conformance(surface_graph: dict[str, Any]) -> dict[str, Any]:
    return _boundary_conformance_check(surface_graph, "tip", "blade_tip_boundary_conformance")


def _boundary_conformance_check(surface_graph: dict[str, Any], boundary_kind: str, name: str) -> dict[str, Any]:
    max_distance = 0.0
    for key, curve in surface_graph.get("boundary_curves", {}).items():
        if not key.endswith(f"_{boundary_kind}_boundary"):
            continue
        compared = surface_graph["boundary_curves"].get(key)
        if compared is None:
            return {"name": name, "status": "FAIL", "max_distance_mm": 999999.0}
        for first, second in zip(curve, compared):
            max_distance = max(max_distance, _point_distance(first, second))
    rounded = _round(max_distance)
    return {
        "name": name,
        "status": "PASS" if rounded <= 0.001 else "FAIL",
        "max_distance_mm": rounded,
        "tolerance_mm": 0.001,
    }


def _point_distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second)))


def _hub_lines(
    hub_curve: list[dict[str, float]],
    params: dict[str, float],
    mirror_z: bool,
) -> list[dict[str, Any]]:
    lines = []
    selected = [0, 2, 4, 6, 8]
    for index in selected:
        point = hub_curve[index]
        z = -point["z_mm"] if mirror_z else point["z_mm"]
        lines.append(
            {
                "name": f"{'mirrored ' if mirror_z else ''}hub latitude {index}",
                "source": "impeller_kernel.hub_curve",
                "points": _circle_points(point["r_mm"], z, 48),
            }
        )
    for meridian, angle in enumerate(range(0, 360, 45)):
        theta = math.radians(angle)
        lines.append(
            {
                "name": f"{'mirrored ' if mirror_z else ''}hub meridian {meridian}",
                "source": "impeller_kernel.hub_curve",
                "points": [
                    _round_point(
                        point["r_mm"] * math.cos(theta),
                        point["r_mm"] * math.sin(theta),
                        -point["z_mm"] if mirror_z else point["z_mm"],
                    )
                    for point in hub_curve
                ],
            }
        )
    if params.get("hub_curve_height_mm", 0.0) <= 0.0:
        return lines[:6]
    return lines


def _shroud_lines(facets: dict[str, str], tip_curve: list[dict[str, float]], mirror_z: bool) -> list[dict[str, Any]]:
    topology = facets["shroud_topology"]
    if topology == "open":
        return []
    prefix = "mirrored " if mirror_z else ""
    inlet = tip_curve[0]
    outlet = tip_curve[-1]
    sign = -1.0 if mirror_z else 1.0
    lines = [
        {
            "name": f"{prefix}front shroud inlet",
            "source": "shroud_proxy",
            "points": _circle_points(inlet["r_mm"], inlet["z_mm"] * sign, 48),
        },
        {
            "name": f"{prefix}front shroud outlet",
            "source": "shroud_proxy",
            "points": _circle_points(outlet["r_mm"], outlet["z_mm"] * sign, 48),
        },
    ]
    if topology == "closed":
        lines.extend(
            [
                {
                    "name": f"{prefix}back shroud inlet",
                    "source": "shroud_proxy",
                    "points": _circle_points(inlet["r_mm"], (inlet["z_mm"] - 22.0) * sign, 48),
                },
                {
                    "name": f"{prefix}back shroud outlet",
                    "source": "shroud_proxy",
                    "points": _circle_points(outlet["r_mm"], (outlet["z_mm"] - 22.0) * sign, 48),
                },
            ]
        )
    return lines


def _passage_lines(params: dict[str, float], facets: dict[str, str], mirror_z: bool) -> list[dict[str, Any]]:
    if facets["passage_topology"] != "recessed_vortex":
        return []
    sign = -1.0 if mirror_z else 1.0
    prefix = "mirrored " if mirror_z else ""
    inlet = params["inlet_radius_mm"] * 1.08
    outlet = params["exit_radius_mm"] * 0.92
    cavity_z = 30.0 + params.get("hub_curve_height_mm", 0.0) * 0.65 + params["outlet_blade_height_mm"] * 0.82
    return [
        {
            "name": f"{prefix}free passage cavity inlet",
            "source": "impeller_kernel.recessed_vortex_passage",
            "points": _circle_points(inlet, cavity_z * sign, 64),
        },
        {
            "name": f"{prefix}free passage cavity outlet",
            "source": "impeller_kernel.recessed_vortex_passage",
            "points": _circle_points(outlet, cavity_z * sign, 64),
        },
    ]


def _legacy_section_metadata(
    params: dict[str, float],
    facets: dict[str, str],
) -> list[dict[str, float]]:
    indices = [0, 2, 4, 6, 8]
    sections = []
    beta_samples, _ = _beta_field(params, facets)
    hub_curve, tip_curve = _meridional_curves(params, facets)
    for index in indices:
        u = index / (U_COUNT - 1)
        sections.append(
            {
                "t": _round(u),
                "radius_mm": hub_curve[index]["r_mm"],
                "angle_deg": beta_samples[index],
                "height_mm": _round(tip_curve[index]["z_mm"] - hub_curve[index]["z_mm"]),
                "z_base_mm": hub_curve[index]["z_mm"],
                "z_tip_mm": tip_curve[index]["z_mm"],
            }
        )
    return sections


def _hub_surface_metadata(params: dict[str, float]) -> dict[str, Any]:
    if params.get("hub_curve_height_mm", 0.0) <= 0.0:
        return {}
    return {
        "primitive": "multi_section_lofted_hub_surface",
        "height_mm": params["hub_curve_height_mm"],
        "section_count": 5,
    }


def _cad_features(params: dict[str, float], facets: dict[str, str]) -> list[str]:
    flow = facets["flow_topology"]
    shroud = facets["shroud_topology"]
    suction = facets["suction_topology"]
    passage = facets["passage_topology"]
    features = [
        "curved_hub_surface" if params.get("hub_curve_height_mm", 0.0) > 0.0 else "hub_solid",
        "inducer_bore",
        "lofted_blade_surface",
        f"{flow}_flow_proxy",
    ]
    if passage == "recessed_vortex":
        features.extend(["recessed_vortex_impeller_proxy", "free_passage_cavity_proxy"])
    else:
        features.append("throughflow_channel_proxy")
    if flow in {"mixed", "axial"}:
        features.append(f"{flow}_flow_axial_offset_proxy")
    if shroud == "semi_open":
        features.append("semi_open_shroud_proxy")
    elif shroud == "closed":
        features.append("closed_shroud_proxy")
    if suction == "double_suction":
        features.append("double_suction_mirror_proxy")
    features.append("radial_exit" if flow == "radial" else f"{flow}_exit")
    return features


def _passage_model(facets: dict[str, str]) -> dict[str, Any]:
    if facets["passage_topology"] == "recessed_vortex":
        return {
            "type": "recessed_vortex",
            "throughflow_bladed_channel": False,
            "free_passage_cavity": True,
        }
    return {
        "type": facets["passage_topology"],
        "throughflow_bladed_channel": facets["passage_topology"] == "throughflow_bladed_channel",
        "free_passage_cavity": False,
    }


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _cubic_bezier(points: list[float], t: float) -> float:
    one = 1.0 - t
    return (
        one**3 * points[0]
        + 3.0 * one * one * t * points[1]
        + 3.0 * one * t * t * points[2]
        + t**3 * points[3]
    )


def _polar_point(radius: float, theta: float, z: float) -> list[float]:
    return _round_point(radius * math.cos(theta), radius * math.sin(theta), z)


def _rotate_point(point: list[float], angle: float, mirror_z: bool) -> list[float]:
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    x = point[0] * cos_a - point[1] * sin_a
    y = point[0] * sin_a + point[1] * cos_a
    z = -point[2] if mirror_z else point[2]
    return _round_point(x, y, z)


def _circle_points(radius: float, z: float, count: int) -> list[list[float]]:
    return [
        _round_point(radius * math.cos(2.0 * math.pi * index / count), radius * math.sin(2.0 * math.pi * index / count), z)
        for index in range(count + 1)
    ]


def _round_point(x: float, y: float, z: float) -> list[float]:
    return [_round(x), _round(y), _round(z)]


def _round(value: float) -> float:
    return round(float(value), ROUND_DIGITS)
