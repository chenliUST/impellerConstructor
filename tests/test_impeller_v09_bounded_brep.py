from __future__ import annotations

from pathlib import Path

from part_rule_synthesis.impeller_bounded_brep_export import (
    bounded_step_contains_no_unbounded_plane_marker,
    write_bounded_brep_step,
)


def test_write_bounded_brep_step_splits_trim_excluded_sampled_surface(tmp_path: Path):
    step_path = tmp_path / "trim_excluded.step"
    surface = _freeform_surface()
    surface["uv_grid"] = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        [[0.0, 1.0, 0.0], [1.0, 1.0, 0.1], [2.0, 1.0, 0.0]],
        [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0]],
    ]
    surface["trim_exclusion_regions"] = [
        {
            "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
            "edge_family": "blade_root_to_hub",
            "transition_surface_id": "blade_0_pressure_root_transition_surface",
            "u_index_start": 0,
            "u_index_end": 1,
            "v_index_start": 0,
            "v_index_end": 1,
        }
    ]
    surface_graph = {
        "transition_geometry_status": "validated_transition_surface_graph",
        "surfaces": [surface],
        "edges": [],
    }

    manifest = write_bounded_brep_step(step_path, "impeller", surface_graph)

    assert manifest["export_exactness"] == "validated_bounded_unsewn_review_brep_step"
    assert manifest["coverage_status"] == "complete_validated_transition_surface_graph"
    assert manifest["total_surface_count"] == 1
    assert manifest["bounded_face_count"] == 2
    assert manifest["reimport_face_count"] == 2
    assert manifest["trim_excluded_cell_count"] == 1
    assert manifest["trim_split_face_count"] == 2
    covered_cells = set()
    for region in manifest["face_regions"]:
        for u_index in range(region["u_index_start"], region["u_index_end"]):
            for v_index in range(region["v_index_start"], region["v_index_end"]):
                covered_cells.add((u_index, v_index))
    assert covered_cells == {(0, 1), (1, 0), (1, 1)}
    assert all(region["surface_graph_id"] == "blade_0_pressure_surface" for region in manifest["face_regions"])
    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is True


def _freeform_surface(**overrides):
    uv_grid = []
    for u_index in range(4):
        row = []
        for v_index in range(4):
            x = 20.0 + u_index * 8.0
            y = -12.0 + v_index * 8.0
            z = 2.0 + 0.1 * u_index * v_index
            row.append([x, y, z])
        uv_grid.append(row)
    surface = {
        "id": "blade_0_pressure_surface",
        "kind": "nurbs_surface",
        "feature_id": "blade_0",
        "role": "blade_pressure",
        "uv_grid": uv_grid,
        "cad_surface": {
            "surface_type": "bspline_surface",
        },
    }
    surface.update(overrides)
    return surface
