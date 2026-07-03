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


def test_mesh_manifest_reports_transition_regions():
    surface_graph = {
        "surfaces": [
            {
                "id": "blade_0_root_transition_surface",
                "feature_id": "blade_00.root_transition",
                "role": "blade_root_fillet",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ]
    }

    manifest = build_surface_mesh_manifest(surface_graph)

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


def test_mesh_manifest_reports_surface_with_only_edge_family_as_transition_region():
    surface_graph = {
        "surfaces": [
            {
                "id": "edge_family_only_surface",
                "feature_id": "hub.blend",
                "role": "sampled_transition",
                "edge_family": "hub_top_outer",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ]
    }

    manifest = build_surface_mesh_manifest(surface_graph)

    assert manifest["transition_regions"] == [
        {
            "surface_graph_id": "edge_family_only_surface",
            "feature_id": "hub.blend",
            "role": "sampled_transition",
            "edge_family": "hub_top_outer",
            "transition_policy_id": "",
            "triangle_start": 0,
            "triangle_count": 2,
        }
    ]


def test_mesh_manifest_reports_surface_with_only_transition_policy_as_transition_region():
    surface_graph = {
        "surfaces": [
            {
                "id": "policy_only_surface",
                "feature_id": "front_hood.transition",
                "role": "sampled_transition",
                "transition_policy_id": "hood_outlet_lip.default",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ]
    }

    manifest = build_surface_mesh_manifest(surface_graph)

    assert manifest["transition_regions"] == [
        {
            "surface_graph_id": "policy_only_surface",
            "feature_id": "front_hood.transition",
            "role": "sampled_transition",
            "edge_family": "",
            "transition_policy_id": "hood_outlet_lip.default",
            "triangle_start": 0,
            "triangle_count": 2,
        }
    ]


def test_mesh_manifest_excludes_regions_without_surface_or_edge_transition_metadata():
    surface_graph = {
        "surfaces": [
            {
                "id": "plain_surface",
                "feature_id": "blade_00",
                "role": "blade_pressure",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ],
        "edges": [
            {
                "id": "plain_edge",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "transition_surface_ids": ["missing_surface"],
            }
        ],
    }

    manifest = build_surface_mesh_manifest(surface_graph)

    assert manifest["transition_regions"] == []


def test_mesh_manifest_uses_edge_metadata_when_transition_surface_lacks_copied_metadata():
    surface_graph = {
        "surfaces": [
            _quad_surface("blade_pressure_surface", feature_id="blade_00", role="blade_pressure"),
            _quad_surface(
                "blade_0_root_transition_surface",
                x_offset=2,
                feature_id="blade_00.root_transition",
                role="blade_root_fillet",
            ),
        ],
        "edges": [
            {
                "id": "root_edge",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "transition_surface_ids": ["blade_0_root_transition_surface"],
            }
        ],
    }

    manifest = build_surface_mesh_manifest(surface_graph)

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


def test_mesh_manifest_prefers_surface_transition_metadata_over_edge_metadata():
    surface_graph = {
        "surfaces": [
            {
                "id": "blade_0_root_transition_surface",
                "feature_id": "blade_00.root_transition",
                "role": "blade_root_fillet",
                "edge_family": "surface_family",
                "transition_policy_id": "surface.policy",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ],
        "edges": [
            {
                "id": "root_edge",
                "edge_family": "edge_family",
                "transition_policy_id": "edge.policy",
                "transition_surface_ids": ["blade_0_root_transition_surface"],
            }
        ],
    }

    manifest = build_surface_mesh_manifest(surface_graph)

    assert manifest["transition_regions"][0]["edge_family"] == "surface_family"
    assert manifest["transition_regions"][0]["transition_policy_id"] == "surface.policy"


def _quad_surface(surface_id: str, *, x_offset: int = 0, feature_id: str, role: str) -> dict:
    return {
        "id": surface_id,
        "feature_id": feature_id,
        "role": role,
        "uv_grid": [
            [[x_offset + 0, 0, 0], [x_offset + 0, 1, 0]],
            [[x_offset + 1, 0, 0], [x_offset + 1, 1, 0]],
        ],
    }
