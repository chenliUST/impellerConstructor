from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_graph_contract import (
    estimate_surface_area,
    surface_feature_records,
    wetted_surfaces,
)
from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


BASE_PARAMS = {
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
}

BASE_FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
}


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


def test_estimate_surface_area_handles_non_square_rectangular_grid():
    surface = {
        "id": "two_quads",
        "role": "hub",
        "uv_grid": [
            [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            [[0, 1, 0], [1, 1, 0], [2, 1, 0]],
        ],
    }

    assert estimate_surface_area(surface) == 2.0


def test_estimate_surface_area_rejects_ragged_grid():
    surface = {
        "id": "ragged_grid",
        "role": "hub",
        "uv_grid": [
            [[0, 0, 0], [1, 0, 0]],
            [[0, 1, 0]],
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        estimate_surface_area(surface)

    message = str(exc_info.value)
    assert "ragged_grid" in message
    assert "rectangular" in message or "ragged" in message


def test_wetted_surfaces_excludes_construction_and_internal_assembly():
    surfaces = [
        {"id": "hub", "role": "hub", "cfd_role": "hub_wall", "material_domain": "hub", "uv_grid": []},
        {"id": "tip_reference", "role": "construction_support_only", "uv_grid": []},
        {"id": "mounting_bore", "role": "mounting_bore", "cfd_role": "mounting_bore", "material_domain": "hub", "feature_id": "mounting_bore", "uv_grid": []},
        {"id": "blade_pressure", "role": "blade_pressure", "cfd_role": "blade_pressure", "uv_grid": []},
    ]

    ids = [surface["id"] for surface in wetted_surfaces(surfaces, suppressed_features={"mounting_bore"})]

    assert ids == ["hub", "blade_pressure"]


def test_wetted_surfaces_requires_cfd_role_after_suppression():
    surfaces = [
        {"id": "hub", "role": "hub", "cfd_role": "hub_wall", "uv_grid": []},
        {"id": "outer_hub_shell", "role": "outer_hub_shell", "uv_grid": []},
        {"id": "empty_cfd_role", "role": "candidate_wall", "cfd_role": "", "uv_grid": []},
        {"id": "reference", "role": "reference_only", "cfd_role": "tip_or_shroud_wall", "uv_grid": []},
        {"id": "mounting_bore", "role": "mounting_bore", "cfd_role": "mounting_bore", "uv_grid": []},
        {"id": "blade_pressure", "role": "blade_pressure", "cfd_role": "blade_pressure", "uv_grid": []},
    ]

    ids = [surface["id"] for surface in wetted_surfaces(surfaces)]

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
        BASE_PARAMS,
        BASE_FACETS,
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


def test_wetted_surfaces_from_closed_kernel_require_cfd_roles_and_exclude_non_wetted_solids():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(
        BASE_PARAMS,
        {**BASE_FACETS, "shroud_topology": "closed"},
    )
    all_surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    wetted = wetted_surfaces(geometry["surface_graph"]["surfaces"])
    wetted_ids = {surface["id"] for surface in wetted}

    assert all(surface.get("cfd_role") for surface in wetted)
    assert {
        "outer_hub_shell_surface",
        "inner_hub_bottom_face",
        "mounting_bore_cylinder",
        "hood_outer_surface",
        "hood_inlet_cap_surface",
        "hood_outlet_cap_surface",
        "hood_chamfer_outlet_surface",
    }.isdisjoint(wetted_ids)
    assert {
        "hub_revolve_surface",
        "shroud_surface",
        "blade_0_pressure_surface",
        "blade_0_suction_surface",
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_root_closure_surface",
        "blade_0_tip_closure_surface",
    } <= wetted_ids
    assert all_surfaces["shroud_surface"]["cfd_role"] == "tip_or_shroud_wall"
    assert all_surfaces["shroud_surface"]["feature_id"] == "front_shroud"
