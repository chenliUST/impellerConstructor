from part_rule_synthesis.impeller_mesh_manifest import build_surface_mesh_manifest


def test_mesh_manifest_reports_triangle_quality_and_edges():
    surface_graph = {
        "surfaces": [
            {
                "id": "quad",
                "role": "blade_pressure",
                "feature_id": "blade_00",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ]
    }

    manifest = build_surface_mesh_manifest(surface_graph, view_id="cfd_full_360")

    assert manifest["source"] == "surface_graph"
    assert manifest["mesh_type"] == "surface_triangles"
    assert manifest["triangle_count"] == 2
    assert manifest["degenerate_triangle_count"] == 0
    assert manifest["quality_metrics"]["min_area"] > 0
    assert manifest["quality_metrics"]["max_aspect_ratio"] >= 1
    assert manifest["patch_regions"][0]["surface_graph_id"] == "quad"
