from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh, edge_incidence_report


def test_edge_incidence_report_detects_free_and_nonmanifold_edges():
    triangles = [
        {"vertex_ids": ["a", "b", "c"]},
        {"vertex_ids": ["c", "b", "d"]},
        {"vertex_ids": ["b", "c", "e"]},
    ]

    report = edge_incidence_report(triangles, declared_open_boundary_ids=[])

    assert report["free_edge_count"] == 6
    assert report["nonmanifold_edge_count"] == 1
    assert report["nonmanifold_edges"] == [["b", "c"]]


def test_edge_incidence_report_excludes_declared_open_edges_from_free_count():
    triangles = [
        {"vertex_ids": ["a", "b", "c"]},
        {"vertex_ids": ["c", "b", "d"]},
    ]

    report = edge_incidence_report(
        triangles,
        declared_open_boundary_ids=[
            "a|b",
            "a|c",
            "b|d",
            "c|d",
        ],
    )

    assert report["free_edge_count"] == 0
    assert report["declared_open_edge_count"] == 4
    assert report["undeclared_free_edges"] == []


def test_build_patch_mesh_triangulates_closed_shared_node_cube():
    surface_graph = {
        "transition_patch_complex": {
            "nodes": {
                "n000": {"point": [0.0, 0.0, 0.0]},
                "n100": {"point": [1.0, 0.0, 0.0]},
                "n110": {"point": [1.0, 1.0, 0.0]},
                "n010": {"point": [0.0, 1.0, 0.0]},
                "n001": {"point": [0.0, 0.0, 1.0]},
                "n101": {"point": [1.0, 0.0, 1.0]},
                "n111": {"point": [1.0, 1.0, 1.0]},
                "n011": {"point": [0.0, 1.0, 1.0]},
            },
            "patches": {
                "bottom": {
                    "surface_graph_id": "bottom_surface",
                    "role": "retained_surface",
                    "node_grid": [["n000", "n010"], ["n100", "n110"]],
                    "edge_ids": [],
                },
                "top": {
                    "surface_graph_id": "top_surface",
                    "role": "corner_patch",
                    "node_grid": [["n001", "n101"], ["n011", "n111"]],
                    "edge_ids": [],
                },
                "front": {
                    "surface_graph_id": "front_surface",
                    "role": "transition_patch",
                    "node_grid": [["n000", "n100"], ["n001", "n101"]],
                    "edge_ids": [],
                },
                "back": {
                    "surface_graph_id": "back_surface",
                    "role": "transition_patch",
                    "node_grid": [["n010", "n011"], ["n110", "n111"]],
                    "edge_ids": [],
                },
                "left": {
                    "surface_graph_id": "left_surface",
                    "role": "transition_patch",
                    "node_grid": [["n000", "n001"], ["n010", "n011"]],
                    "edge_ids": [],
                },
                "right": {
                    "surface_graph_id": "right_surface",
                    "role": "transition_patch",
                    "node_grid": [["n100", "n110"], ["n101", "n111"]],
                    "edge_ids": [],
                },
            },
            "declared_open_boundary_ids": [],
        }
    }

    mesh = build_patch_mesh(surface_graph)

    assert mesh["mesh_type"] == "shared_node_transition_patch_mesh"
    assert mesh["included_surface_ids"] == [
        "bottom_surface",
        "top_surface",
        "front_surface",
        "back_surface",
        "left_surface",
        "right_surface",
    ]
    assert set(mesh["vertices"]) == {
        "n000",
        "n100",
        "n110",
        "n010",
        "n001",
        "n101",
        "n111",
        "n011",
    }
    assert mesh["triangle_count"] == 12
    assert all("vertex_ids" in triangle for triangle in mesh["triangles"])
    assert mesh["mesh_manifoldness_report"]["free_edge_count"] == 0
    assert mesh["mesh_manifoldness_report"]["nonmanifold_edge_count"] == 0
    assert mesh["mesh_manifoldness_report"]["zero_area_face_count"] == 0
