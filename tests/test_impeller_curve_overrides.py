from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


PARAMS = {
    "blade_count": 4,
    "inlet_radius_mm": 180.0,
    "exit_radius_mm": 620.0,
    "inlet_blade_height_mm": 150.0,
    "outlet_blade_height_mm": 72.0,
    "hub_curve_height_mm": 82.0,
    "mounting_bore_radius_mm": 40.0,
    "blade_wrap_deg": 118.0,
    "blade_lean_deg": 8.0,
    "leading_edge_lean_deg": 12.0,
    "trailing_edge_lean_deg": -8.0,
    "leading_edge_sweep_mm": 30.0,
    "trailing_edge_sweep_mm": -45.0,
    "blade_thickness_mm": 18.0,
}

FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
}


def test_axisymmetric_kernel_applies_valid_profile_overrides():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS)
    hub = baseline["kernel"]["meridional_profiles"]["hub"]
    tip = baseline["kernel"]["meridional_profiles"]["tip_or_shroud"]
    edited_hub = {
        **hub,
        "control_points": [
            [point[0], point[1] + (12.0 if index == 1 else 0.0)]
            for index, point in enumerate(hub["control_points"])
        ],
    }

    changed = build_axisymmetric_throughflow_nurbs_geometry(
        PARAMS,
        FACETS,
        profile_overrides={"hub_profile": edited_hub, "tip_or_shroud_profile": tip},
    )

    assert changed["kernel"]["meridional_profiles"]["hub"]["control_points"] == edited_hub["control_points"]
    assert changed["surface_graph"]["surfaces"][0]["profile"]["control_points"] == edited_hub["control_points"]
    assert changed["kernel"]["profile_controls"]["source"] == "user_override"


def test_axisymmetric_kernel_rejects_invalid_profile_override_radius():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS)
    hub = baseline["kernel"]["meridional_profiles"]["hub"]
    bad_hub = {**hub, "control_points": [[-1.0, 0.0], *hub["control_points"][1:]]}

    with pytest.raises(ValueError, match="positive radius"):
        build_axisymmetric_throughflow_nurbs_geometry(
            PARAMS,
            FACETS,
            profile_overrides={"hub_profile": bad_hub},
        )


def test_axisymmetric_kernel_rejects_tip_profile_intersecting_hub():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS)
    hub = baseline["kernel"]["meridional_profiles"]["hub"]
    bad_tip = {**hub, "id": "tip_or_shroud_profile"}

    with pytest.raises(ValueError, match="tip_or_shroud_profile"):
        build_axisymmetric_throughflow_nurbs_geometry(
            PARAMS,
            FACETS,
            profile_overrides={"tip_or_shroud_profile": bad_tip},
        )


def test_axisymmetric_kernel_applies_theta_thickness_and_sweep_curve_overrides():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS)
    changed = build_axisymmetric_throughflow_nurbs_geometry(
        PARAMS,
        FACETS,
        curve_overrides={
            "blade_mean": {
                "theta_center_u_curve": {
                    "coordinate_system": "u_theta_deg",
                    "control_points": [[0.0, 0.0], [0.33, -28.0], [0.66, -82.0], [1.0, -136.0]],
                },
                "span_lean_u_curve": {
                    "coordinate_system": "u_lean_deg",
                    "control_points": [[0.0, 18.0], [0.5, 4.0], [1.0, -16.0]],
                },
            },
            "blade_edges": {
                "leading_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, -0.08], [0.5, 0.0], [1.0, 0.08]],
                },
                "trailing_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, 0.1], [0.5, 0.0], [1.0, -0.1]],
                },
            },
            "thickness": {
                "thickness_u_curve": {
                    "coordinate_system": "u_thickness_mm",
                    "control_points": [[0.0, 26.0], [0.5, 20.0], [1.0, 12.0]],
                }
            },
        },
    )

    assert changed["sampled_blades"][0]["mean_surface"][20][8] != baseline["sampled_blades"][0]["mean_surface"][20][8]
    assert changed["sampled_blades"][0]["pressure_surface"][0][0] != baseline["sampled_blades"][0]["pressure_surface"][0][0]
    assert changed["sampled_blades"][0]["leading_edge_boundary"][-1] != baseline["sampled_blades"][0]["leading_edge_boundary"][-1]
    assert changed["kernel"]["editable_curve_controls"]["blade_mean"]["theta_center_u_curve"]["source"] == "user_override"


def test_axisymmetric_kernel_rejects_non_monotone_curve_override():
    with pytest.raises(ValueError, match="monotone"):
        build_axisymmetric_throughflow_nurbs_geometry(
            PARAMS,
            FACETS,
            curve_overrides={
                "blade_mean": {
                    "theta_center_u_curve": {
                        "coordinate_system": "u_theta_deg",
                        "control_points": [[0.0, 0.0], [0.7, -50.0], [0.5, -80.0], [1.0, -118.0]],
                    }
                }
            },
        )


def test_axisymmetric_kernel_filters_surfaces_by_generation_stage():
    hub_only = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, geometry_stage="hub_support")
    blades = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, geometry_stage="blade_surfaces")
    full = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, geometry_stage="edge_closures")

    hub_roles = {surface["role"] for surface in hub_only["surface_graph"]["surfaces"]}
    blade_roles = {surface["role"] for surface in blades["surface_graph"]["surfaces"]}
    full_kinds = {surface["kind"] for surface in full["surface_graph"]["surfaces"]}

    assert "blade_pressure" not in hub_roles
    assert "blade_pressure" in blade_roles
    assert "edge_closure_surface" not in {surface["kind"] for surface in blades["surface_graph"]["surfaces"]}
    assert "edge_closure_surface" in full_kinds
    assert hub_only["construction_lines"]["blade_u"] == []
    assert blades["construction_lines"]["blade_edges"] == []
    assert full["construction_lines"]["blade_edges"]


def test_axisymmetric_kernel_preserves_blade_boundary_conformance_with_overrides():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(
        PARAMS,
        FACETS,
        curve_overrides={
            "blade_edges": {
                "leading_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, -0.04], [0.5, 0.0], [1.0, 0.04]],
                },
                "trailing_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, 0.04], [0.5, 0.0], [1.0, -0.04]],
                },
            }
        },
    )
    first_blade = geometry["sampled_blades"][0]

    assert first_blade["pressure_surface"][0][0] == first_blade["pressure_hub_boundary"][0]
    assert first_blade["pressure_surface"][0][-1] == first_blade["pressure_tip_boundary"][0]
    assert geometry["validity"]["status"] == "PASS"
