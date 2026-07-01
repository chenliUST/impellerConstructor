from __future__ import annotations

import struct
from pathlib import Path

from part_rule_synthesis.impeller_surface_graph_export import (
    triangulate_surface_graph,
    write_surface_graph_exports,
)


def test_triangulate_surface_graph_matches_frontend_quad_split():
    result = triangulate_surface_graph(_single_quad_surface_graph())

    assert result["triangle_count"] == 2
    assert result["triangles"][0]["points"] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert result["triangles"][1]["points"] == [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    assert result["triangle_regions"] == [
        {
            "surface_graph_id": "quad_surface",
            "feature_id": "blade_00",
            "role": "blade_pressure",
            "triangle_start": 0,
            "triangle_count": 2,
        }
    ]


def test_triangulate_surface_graph_skips_degenerate_triangles_with_reasons():
    result = triangulate_surface_graph(
        {
            "surfaces": [
                {
                    "id": "degenerate_surface",
                    "feature_id": "blade_00",
                    "role": "blade_pressure",
                    "uv_grid": [
                        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                        [[2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
                    ],
                }
            ]
        }
    )

    assert result["triangle_count"] == 0
    assert result["skipped_triangle_count"] == 2
    assert result["skipped_triangle_reasons"] == {"degenerate_triangle": 2}
    assert result["triangle_regions"] == []


def test_write_surface_graph_exports_writes_binary_stl_step_and_manifests(tmp_path: Path):
    step_path = tmp_path / "impeller.step"
    stl_path = tmp_path / "impeller.stl"

    manifests = write_surface_graph_exports(
        step_path,
        stl_path,
        "impeller",
        _single_quad_surface_graph(),
        view_id="cad_review_360",
    )

    stl_bytes = stl_path.read_bytes()
    stl_triangle_count = struct.unpack("<I", stl_bytes[80:84])[0]
    step_text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert stl_triangle_count == 2
    assert len(stl_bytes) == 84 + stl_triangle_count * 50
    assert "ISO-10303-21" in step_text
    assert "CARTESIAN_POINT_LIST_3D" in step_text
    assert "TRIANGULATED_FACE_SET" in step_text
    assert "VERTEX_POINT" not in step_text
    assert "cadquery proxy" not in step_text.lower()
    assert manifests["stl"]["source"] == "surface_graph"
    assert manifests["stl"]["view"] == "cad_review_360"
    assert manifests["stl"]["export_exactness"] == "surface_graph_sampled_mesh"
    assert manifests["stl"]["surface_count"] == 1
    assert manifests["stl"]["triangle_count"] == 2
    assert manifests["step"]["source"] == "surface_graph"
    assert manifests["step"]["export_exactness"] == "surface_graph_mesh_step"
    assert manifests["step"]["step_representation"] == "ap242_triangulated_face_set"
    assert manifests["step"]["vertex_count"] == 4
    assert manifests["step"]["face_count"] == 2
    assert manifests["step"]["face_regions"] == manifests["stl"]["triangle_regions"]


def _single_quad_surface_graph() -> dict:
    return {
        "surfaces": [
            {
                "id": "quad_surface",
                "feature_id": "blade_00",
                "role": "blade_pressure",
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                    [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
                ],
            }
        ]
    }
