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


def test_write_surface_graph_obj_uses_transition_aware_mesh_for_resolved_graph(tmp_path: Path):
    obj_path = tmp_path / "impeller.obj"

    manifest = write_surface_graph_obj(
        obj_path,
        "impeller",
        {
            **_transition_surface_graph(),
            "transition_geometry_status": "resolved_trimmed_surface_graph",
        },
        view_id="feature_debug",
    )

    assert manifest["mesh_type"] == "transition_aware_surface_mesh"
    assert manifest["source"] == "transition_resolved_surface_graph"
    assert manifest["transition_regions"][0]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert manifest["transition_regions"][0]["quality"]["max_aspect_ratio"] > 0
    assert "g blade_0_root_transition_surface" in obj_path.read_text(encoding="utf-8")


def test_write_surface_graph_obj_reports_edge_derived_transition_regions_once(tmp_path: Path):
    obj_path = tmp_path / "impeller.obj"

    manifest = write_surface_graph_obj(
        obj_path,
        "impeller",
        {
            "surfaces": [
                _quad_surface("blade_pressure_surface", feature_id="blade_00", role="blade_pressure"),
                _quad_surface(
                    "blade_0_root_transition_surface",
                    x_offset=2.0,
                    feature_id="blade_00.root_transition",
                    role="blade_root_fillet",
                ),
            ],
            "edges": [
                {
                    "id": "root_edge_a",
                    "edge_family": "blade_root_to_hub",
                    "transition_policy_id": "blade_root_to_hub.default",
                    "transition_surface_ids": ["blade_0_root_transition_surface"],
                },
                {
                    "id": "root_edge_b",
                    "edge_family": "blade_root_to_hub",
                    "transition_policy_id": "blade_root_to_hub.default",
                    "transition_surface_ids": ["blade_0_root_transition_surface"],
                },
            ],
        },
    )

    assert obj_path.read_text(encoding="utf-8").count("g blade_0_root_transition_surface") == 1
    assert manifest["triangle_count"] == 4
    assert manifest["transition_regions"] == [
        {
            "surface_graph_id": "blade_0_root_transition_surface",
            "feature_id": "blade_00.root_transition",
            "role": "blade_root_fillet",
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": "blade_root_to_hub.default",
            "triangle_start": 2,
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
                "edge_treatment_site_id": "blade_0.root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "radius_mm": 8.0,
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                    [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
                ],
            }
        ]
    }


def _quad_surface(
    surface_id: str,
    *,
    x_offset: float = 0.0,
    feature_id: str,
    role: str,
) -> dict:
    return {
        "id": surface_id,
        "feature_id": feature_id,
        "role": role,
        "uv_grid": [
            [[x_offset + 0.0, 0.0, 0.0], [x_offset + 0.0, 1.0, 0.0]],
            [[x_offset + 1.0, 0.0, 0.0], [x_offset + 1.0, 1.0, 0.0]],
        ],
    }
