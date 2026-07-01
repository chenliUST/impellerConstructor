from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


PARAMS = {
    "blade_count": 3,
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
    "root_fillet_radius_mm": 3.0,
    "hub_wall_thickness_mm": 18.0,
    "hub_bottom_thickness_mm": 24.0,
    "hub_top_cap_thickness_mm": 8.0,
    "hub_chamfer_radius_mm": 3.0,
    "hood_wall_thickness_mm": 12.0,
    "hood_chamfer_radius_mm": 3.0,
}

FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
    "blade_exit_geometry": "backward_curved",
}


def clamped_curve(points):
    degree = 3
    interior_count = len(points) - degree - 1
    if interior_count <= 0:
        knots = [0, 0, 0, 0, 1, 1, 1, 1]
    else:
        interiors = [(index + 1) / (interior_count + 1) for index in range(interior_count)]
        knots = [0, 0, 0, 0, *interiors, 1, 1, 1, 1]
    return {
        "kind": "nurbs_curve",
        "degree": degree,
        "coordinate_system": "rz_meridional_mm",
        "control_points": points,
        "weights": [1.0] * len(points),
        "knots": knots,
    }


def test_kernel_accepts_six_point_hub_and_tip_profiles():
    profiles = {
        "hub_profile": clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    geometry = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)

    hub_surface = next(surface for surface in geometry["surface_graph"]["surfaces"] if surface["id"] == "hub_revolve_surface")
    assert hub_surface["profile"]["control_points"] == profiles["hub_profile"]["control_points"]
    assert geometry["kernel"]["meridional_curves"]["hub"][0]["r_mm"] == profiles["hub_profile"]["control_points"][0][0]
    assert geometry["kernel"]["meridional_curves"]["hub"][0]["z_mm"] == profiles["hub_profile"]["control_points"][0][1]
    assert geometry["kernel"]["meridional_curves"]["hub"][-1]["r_mm"] == profiles["hub_profile"]["control_points"][-1][0]
    assert geometry["kernel"]["meridional_curves"]["hub"][-1]["z_mm"] == profiles["hub_profile"]["control_points"][-1][1]
    assert (
        geometry["kernel"]["meridional_curves"]["tip_or_shroud"][0]["r_mm"]
        == profiles["tip_or_shroud_profile"]["control_points"][0][0]
    )
    assert (
        geometry["kernel"]["meridional_curves"]["tip_or_shroud"][-1]["z_mm"]
        == profiles["tip_or_shroud_profile"]["control_points"][-1][1]
    )
    assert geometry["validity"]["status"] == "PASS"


def test_kernel_uses_declared_profile_interior_knots():
    hub = clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]])
    tip = clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]])
    open_uniform = build_axisymmetric_throughflow_nurbs_geometry(
        PARAMS,
        FACETS,
        profile_overrides={"hub_profile": hub, "tip_or_shroud_profile": tip},
    )
    custom_knots = build_axisymmetric_throughflow_nurbs_geometry(
        PARAMS,
        FACETS,
        profile_overrides={
            "hub_profile": {**hub, "knots": [0, 0, 0, 0, 0.2, 0.75, 1, 1, 1, 1]},
            "tip_or_shroud_profile": tip,
        },
    )

    assert custom_knots["kernel"]["meridional_curves"]["hub"][20] != open_uniform["kernel"]["meridional_curves"]["hub"][20]


def test_kernel_rejects_invalid_knot_count_for_variable_profile():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "knots": [0, 0, 0, 0, 1, 1, 1, 1],
        },
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    try:
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)
    except ValueError as exc:
        assert "knot count" in str(exc)
    else:
        raise AssertionError("expected invalid knot count to fail")


def test_kernel_rejects_non_integer_profile_degree():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "degree": 3.5,
        },
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    with pytest.raises(ValueError, match="degree"):
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)


def test_kernel_rejects_endpoint_values_in_interior_knots():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "knots": [0, 0, 0, 0, 0, 0.5, 1, 1, 1, 1],
        },
        "tip_or_shroud_profile": {
            **clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
            "knots": [0, 0, 0, 0, 0, 0.5, 1, 1, 1, 1],
        },
    }

    with pytest.raises(ValueError, match="interior knots"):
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)


def test_kernel_rejects_string_profile_weights():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "weights": "111111",
        },
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    with pytest.raises(ValueError, match="weights"):
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)


def test_kernel_rejects_string_profile_knots():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "knots": "0000001111",
        },
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    with pytest.raises(ValueError, match="knots"):
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)
