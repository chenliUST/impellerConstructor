from pathlib import Path

import pytest

from part_rule_synthesis.impeller_brep_export import write_trimmed_brep_step


def test_write_trimmed_brep_step_exports_bspline_face(tmp_path: Path):
    step_path = tmp_path / "brep.step"

    manifest = write_trimmed_brep_step(step_path, "impeller", _single_bspline_surface_graph())
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert manifest["source"] == "surface_graph"
    assert manifest["export_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert manifest["step_writer"] == "occt_stepcontrol_writer"
    assert manifest["brep_face_count"] == 1
    assert manifest["sewing_status"] == "not_attempted"
    assert manifest["face_regions"] == [
        {
            "brep_face_id": "face_0000",
            "surface_graph_id": "surface_0",
            "feature_id": "blade_00",
            "role": "blade_pressure",
            "cad_surface_type": "bspline_surface",
        }
    ]
    assert "B_SPLINE_SURFACE" in text
    assert "ADVANCED_FACE" in text
    assert "TRIANGULATED_FACE_SET" not in text


def test_write_trimmed_brep_step_rejects_missing_cad_surface(tmp_path: Path):
    step_path = tmp_path / "missing.step"
    graph = {"surfaces": [{"id": "surface_0", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]}]}

    with pytest.raises(ValueError, match="surface_0 missing cad_surface"):
        write_trimmed_brep_step(step_path, "impeller", graph)

    assert not step_path.exists()


def _single_bspline_surface_graph():
    control_points = [
        [[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0]],
        [[1, 0, 0], [1, 1, 0.2], [1, 2, 0.2], [1, 3, 0]],
        [[2, 0, 0], [2, 1, 0.2], [2, 2, 0.2], [2, 3, 0]],
        [[3, 0, 0], [3, 1, 0], [3, 2, 0], [3, 3, 0]],
    ]
    return {
        "surfaces": [
            {
                "id": "surface_0",
                "feature_id": "blade_00",
                "role": "blade_pressure",
                "cad_surface": {
                    "surface_type": "bspline_surface",
                    "degree_u": 3,
                    "degree_v": 3,
                    "control_points": control_points,
                    "weights": [[1, 1, 1, 1] for _ in range(4)],
                    "knots_u": [0, 0, 0, 0, 1, 1, 1, 1],
                    "knots_v": [0, 0, 0, 0, 1, 1, 1, 1],
                    "trim_loops": [{"orientation": "outer", "edges": []}],
                },
            }
        ],
        "edges": [],
    }
