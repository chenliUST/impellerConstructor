from __future__ import annotations

from part_rule_synthesis.impeller_graph_contract import (
    estimate_surface_area,
    surface_feature_records,
    wetted_surfaces,
)
from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


def test_estimate_surface_area_returns_positive_area_for_grid():
    surface = {
        "id": "quad",
        "role": "hub",
        "uv_grid": [
            [[0, 0, 0], [1, 0, 0]],
            [[0, 1, 0], [1, 1, 0]],
        ],
    }

    assert estimate_surface_area(surface) == 1.0


def test_wetted_surfaces_excludes_construction_and_internal_assembly():
    surfaces = [
        {"id": "hub", "role": "hub", "material_domain": "hub", "uv_grid": []},
        {"id": "tip_reference", "role": "construction_support_only", "uv_grid": []},
        {"id": "mounting_bore", "role": "mounting_bore", "material_domain": "hub", "feature_id": "mounting_bore", "uv_grid": []},
        {"id": "blade_pressure", "role": "blade_pressure", "uv_grid": []},
    ]

    ids = [surface["id"] for surface in wetted_surfaces(surfaces, suppressed_features={"mounting_bore"})]

    assert ids == ["hub", "blade_pressure"]


def test_surface_feature_records_map_feature_ids_to_generated_surfaces():
    surfaces = [
        {"id": "blade_00_root_transition", "feature_id": "blade_00.root_fillet", "role": "root_transition"},
        {"id": "blade_00_pressure_surface", "feature_id": "blade_00", "role": "blade_pressure"},
    ]

    records = surface_feature_records(surfaces)

    assert records["blade_00.root_fillet"]["generated_surfaces"] == ["blade_00_root_transition"]
    assert records["blade_00"]["generated_surfaces"] == ["blade_00_pressure_surface"]


def test_axisymmetric_kernel_surfaces_include_cfd_feature_metadata():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(
        {
            "blade_count": 1,
            "inlet_radius_mm": 180.0,
            "exit_radius_mm": 620.0,
            "inlet_blade_height_mm": 150.0,
            "outlet_blade_height_mm": 72.0,
            "hub_curve_height_mm": 82.0,
            "mounting_bore_radius_mm": 40.0,
            "blade_wrap_deg": 118.0,
            "blade_lean_deg": 8.0,
            "blade_thickness_mm": 18.0,
        },
        {
            "flow_topology": "radial",
            "shroud_topology": "open",
            "suction_topology": "single_suction",
            "blade_exit_geometry": "backward_curved",
            "working_domain": "pump",
            "passage_topology": "throughflow_bladed_channel",
        },
    )
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}

    assert surfaces["hub_revolve_surface"]["cfd_role"] == "hub_wall"
    assert surfaces["hub_revolve_surface"]["feature_id"] == "hub"
    assert surfaces["tip_reference_surface"]["cfd_role"] == "tip_or_shroud_wall"
    assert surfaces["tip_reference_surface"]["feature_id"] == "tip_reference"
    assert surfaces["blade_0_pressure_surface"]["cfd_role"] == "blade_pressure"
    assert surfaces["blade_0_pressure_surface"]["feature_id"] == "blade_00"
    assert surfaces["blade_0_suction_surface"]["cfd_role"] == "blade_suction"
    assert surfaces["blade_0_suction_surface"]["feature_id"] == "blade_00"
    assert surfaces["blade_0_leading_edge_surface"]["cfd_role"] == "leading_edge_transition"
    assert surfaces["blade_0_leading_edge_surface"]["feature_id"] == "blade_00.leading_edge_round"
    assert surfaces["blade_0_trailing_edge_surface"]["cfd_role"] == "trailing_edge_transition"
    assert surfaces["blade_0_trailing_edge_surface"]["feature_id"] == "blade_00.trailing_edge_round"
    assert surfaces["blade_0_root_closure_surface"]["cfd_role"] == "root_transition"
    assert surfaces["blade_0_root_closure_surface"]["feature_id"] == "blade_00.root_fillet"
    assert surfaces["blade_0_tip_closure_surface"]["cfd_role"] == "tip_transition"
    assert surfaces["blade_0_tip_closure_surface"]["feature_id"] == "blade_00.tip_transition"
