from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.service import (
    _bind_parameters,
    _geometry_metadata,
    _normalize_transition_overrides,
)


def _geometry_for_v08(
    transition_overrides: dict | None = None,
    *,
    preset_name: str = "radial_open_reference_v0_8",
) -> dict:
    runtime = compile_impeller_runtime_preset(preset_name)
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    normalized_overrides = _normalize_transition_overrides(transition_overrides)
    transition_policies = resolve_transition_policies(
        edge_families,
        parameters,
        normalized_overrides,
    )
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )


def test_transition_aware_mesh_reports_blade_root_transition_quality():
    surface_graph = _geometry_for_v08()["surface_graph"]

    mesh = build_transition_aware_mesh(surface_graph)

    root_regions = [
        region
        for region in mesh["transition_regions"]
        if region["edge_family"] == "blade_root_to_hub"
    ]
    assert mesh["mesh_type"] == "transition_aware_surface_mesh"
    assert mesh["source"] == "transition_resolved_surface_graph"
    assert mesh["triangle_count"] > 0
    assert root_regions
    assert root_regions[0]["surface_graph_id"] == "blade_0_root_transition_surface"
    assert root_regions[0]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert root_regions[0]["transition_policy_id"] == "blade_root_to_hub.default"
    assert root_regions[0]["treatment"] == "fillet"
    assert root_regions[0]["radius_mm"] == 8.0
    assert root_regions[0]["quality"]["max_aspect_ratio"] > 0
    assert root_regions[0]["quality"]["boundary_mismatch_max_mm"] is None
    assert root_regions[0]["quality"]["boundary_mismatch_status"] == "not_evaluated"


def test_transition_aware_mesh_accounts_for_all_triangles_and_skips():
    surface_graph = _geometry_for_v08()["surface_graph"]

    mesh = build_transition_aware_mesh(surface_graph)

    assert mesh["triangle_count"] == sum(
        region["triangle_count"]
        for region in mesh["triangle_regions"]
    )
    if mesh["skipped_triangle_count"]:
        assert mesh["skipped_triangle_reasons"]
    else:
        assert mesh["skipped_triangle_reasons"] == {}


def test_transition_aware_mesh_reports_closed_hood_and_tip_transitions():
    surface_graph = _geometry_for_v08(preset_name="radial_closed_reference_v0_8")["surface_graph"]

    mesh = build_transition_aware_mesh(surface_graph)

    edge_families = {
        region["edge_family"]
        for region in mesh["transition_regions"]
    }
    assert "hood_inlet_lip" in edge_families
    assert "hood_outlet_lip" in edge_families
    assert "blade_tip_or_shroud" in edge_families


def test_validated_transition_mesh_skips_trim_excluded_cells():
    surface_graph = {
        "transition_geometry_status": "validated_transition_surface_graph",
        "surfaces": [
            {
                "id": "hub_revolve_surface",
                "role": "hub",
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                ],
                "trim_exclusion_regions": [
                    {
                        "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                        "edge_family": "blade_root_to_hub",
                        "transition_surface_id": "blade_0_pressure_root_transition_surface",
                        "u_index_start": 0,
                        "u_index_end": 1,
                        "v_index_start": 0,
                        "v_index_end": 1,
                    }
                ],
            },
            {
                "id": "blade_0_pressure_root_transition_surface",
                "role": "blade_pressure_root_fillet",
                "edge_family": "blade_root_to_hub",
                "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "uv_grid": [
                    [[0.0, 0.0, 0.2], [1.0, 0.0, 0.2]],
                    [[0.0, 1.0, 0.2], [1.0, 1.0, 0.2]],
                ],
            },
        ],
        "edge_treatment_sites": [
            {
                "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "adjacent_surface_ids": ["hub_revolve_surface"],
                "transition_surface_ids": ["blade_0_pressure_root_transition_surface"],
            }
        ],
    }

    mesh = build_transition_aware_mesh(surface_graph)

    assert mesh["mesh_type"] == "validated_transition_aware_surface_mesh"
    assert mesh["trimmed_cell_count"] == 1
    assert mesh["trimmed_cell_regions"] == [
        {
            "surface_graph_id": "hub_revolve_surface",
            "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
            "edge_family": "blade_root_to_hub",
            "transition_surface_id": "blade_0_pressure_root_transition_surface",
            "u_index_start": 0,
            "u_index_end": 1,
            "v_index_start": 0,
            "v_index_end": 1,
            "cell_count": 1,
        }
    ]
    assert all(triangle["surface_graph_id"] != "hub_revolve_surface" for triangle in mesh["triangles"])
    assert any(
        region["surface_graph_id"] == "blade_0_pressure_root_transition_surface"
        for region in mesh["triangle_regions"]
    )
