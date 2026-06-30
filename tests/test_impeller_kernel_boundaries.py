from __future__ import annotations

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


BASE_PARAMS = {
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
}

FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
}


def test_axisymmetric_kernel_emits_four_named_blade_boundaries():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(BASE_PARAMS, FACETS)
    blade = geometry["sampled_blades"][0]
    boundary_curves = geometry["surface_graph"]["named_boundary_curves"]

    assert "blade_root_boundary" in blade
    assert "blade_tip_boundary" in blade
    assert "leading_edge_boundary" in blade
    assert "trailing_edge_boundary" in blade
    assert any(curve["role"] == "blade_root_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "blade_tip_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "leading_edge_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "trailing_edge_boundary" for curve in boundary_curves)


def test_leading_edge_lean_changes_leading_edge_boundary_without_changing_blade_count():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(
        {**BASE_PARAMS, "leading_edge_lean_deg": 0.0},
        FACETS,
    )
    changed = build_axisymmetric_throughflow_nurbs_geometry(
        {**BASE_PARAMS, "leading_edge_lean_deg": 35.0},
        FACETS,
    )

    assert len(baseline["sampled_blades"]) == len(changed["sampled_blades"]) == 3
    assert baseline["sampled_blades"][0]["leading_edge_boundary"] != changed["sampled_blades"][0]["leading_edge_boundary"]


def test_trailing_edge_sweep_changes_trailing_edge_boundary():
    baseline = build_axisymmetric_throughflow_nurbs_geometry(
        {**BASE_PARAMS, "trailing_edge_sweep_mm": 0.0},
        FACETS,
    )
    changed = build_axisymmetric_throughflow_nurbs_geometry(
        {**BASE_PARAMS, "trailing_edge_sweep_mm": 90.0},
        FACETS,
    )

    assert baseline["sampled_blades"][0]["trailing_edge_boundary"] != changed["sampled_blades"][0]["trailing_edge_boundary"]


def test_axisymmetric_kernel_echoes_shape_control_stage_and_locked_topology():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(
        BASE_PARAMS,
        FACETS,
        shape_control={
            "optimization_stage": 1,
            "locked_topology": True,
            "active_policies": ["hub_meridional_profile", "blade_tip_meridional_profile"],
        },
    )

    assert geometry["shape_control"]["optimization_stage"] == 1
    assert geometry["shape_control"]["locked_topology"] is True
    assert "hub_meridional_profile" in geometry["shape_control"]["active_policies"]
