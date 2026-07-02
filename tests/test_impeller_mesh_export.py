from pathlib import Path

from part_rule_synthesis.impeller_mesh_export import write_surface_graph_obj


def test_write_surface_graph_obj_reports_transition_regions(tmp_path: Path):
    obj_path = tmp_path / "impeller.obj"

    manifest = write_surface_graph_obj(
        obj_path,
        "impeller",
        _transition_surface_graph(),
        view_id="feature_debug",
    )

    obj_lines = obj_path.read_text(encoding="utf-8").splitlines()
    assert "o impeller_surface_graph" in obj_lines
    assert "g blade_0_root_transition_surface" in obj_lines
    assert obj_lines[-2:] == ["f 1 2 3", "f 2 4 3"]

    assert manifest["source"] == "surface_graph"
    assert manifest["view"] == "feature_debug"
    assert manifest["export_exactness"] == "surface_graph_obj_mesh"
    assert manifest["triangle_count"] == 2
    assert manifest["surface_count"] == 1
    assert manifest["transition_regions"] == [
        {
            "surface_graph_id": "blade_0_root_transition_surface",
            "feature_id": "blade_00.root_transition",
            "role": "blade_root_fillet",
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": "blade_root_to_hub.default",
            "triangle_start": 0,
            "triangle_count": 2,
        }
    ]


def _transition_surface_graph() -> dict:
    return {
        "surfaces": [
            {
                "id": "blade_0_root_transition_surface",
                "feature_id": "blade_00.root_transition",
                "role": "blade_root_fillet",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                    [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
                ],
            }
        ]
    }
