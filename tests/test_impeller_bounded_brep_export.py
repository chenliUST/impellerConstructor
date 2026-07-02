from pathlib import Path

from part_rule_synthesis.impeller_bounded_brep_export import (
    BOUNDED_STEP_EXACTNESS,
    DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS,
    bounded_step_contains_no_unbounded_plane_marker,
    make_annular_plane_face,
    write_bounded_brep_step,
)


def test_make_annular_plane_face_returns_bounded_annular_face():
    surface = {
        "id": "inner_hub_bottom_face",
        "kind": "annular_plane_surface",
        "inner_radius_mm": 20.0,
        "outer_radius_mm": 50.0,
        "z_mm": 3.0,
    }

    face, metadata = make_annular_plane_face(surface)

    assert not face.IsNull()
    assert metadata["bounded"] is True
    assert metadata["outer_radius_mm"] == 50.0
    assert metadata["inner_radius_mm"] == 20.0
    assert metadata["loop_count"] == 2


def test_write_bounded_brep_step_exports_annular_plane_without_unbounded_marker(tmp_path: Path):
    step_path = tmp_path / "bounded_annular.step"
    surface_graph = {
        "surfaces": [
            {
                "id": "inner_hub_bottom_face",
                "kind": "annular_plane_surface",
                "feature_id": "hub",
                "role": "inner_hub_bottom",
                "inner_radius_mm": 20.0,
                "outer_radius_mm": 50.0,
                "z_mm": 3.0,
            }
        ],
        "edges": [],
    }

    manifest = write_bounded_brep_step(step_path, "impeller", surface_graph)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert step_path.stat().st_size > 1024
    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is True
    assert manifest["source"] == "surface_graph"
    assert manifest["view"] == "cad_review_360"
    assert manifest["solid_name"] == "impeller"
    assert manifest["export_exactness"] == DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
    assert manifest["target_exactness"] == BOUNDED_STEP_EXACTNESS
    assert manifest["bounded_face_count"] == 1
    assert manifest["sewing_status"] == "not_attempted"
    assert manifest["open_edge_count"] is None
    assert manifest["face_regions"][0]["surface_graph_id"] == "inner_hub_bottom_face"
    assert "ADVANCED_FACE" in text
    assert "PLANE" in text
    assert "TRIANGULATED_FACE_SET" not in text
