import math
from pathlib import Path

import pytest

from part_rule_synthesis.impeller_bounded_brep_export import (
    BOUNDED_STEP_EXACTNESS,
    DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS,
    FINITE_REIMPORT_BBOX_MAX_SPAN_MM,
    _bbox_passes_exactness_gate,
    bounded_step_contains_no_unbounded_plane_marker,
    make_annular_plane_face,
    reimport_step_bbox,
    write_bounded_brep_step,
)


def test_make_annular_plane_face_returns_bounded_annular_face():
    surface = _annular_surface()

    face, metadata = make_annular_plane_face(surface)

    assert not face.IsNull()
    assert metadata["bounded"] is True
    assert metadata["outer_radius_mm"] == 50.0
    assert metadata["inner_radius_mm"] == 20.0
    assert metadata["loop_count"] == 2


def test_annular_plane_face_has_two_wires_and_expected_area():
    face, _metadata = make_annular_plane_face(_annular_surface())

    assert _wire_count(face) == 2
    assert _surface_area(face) == pytest.approx(
        math.pi * (50.0**2 - 20.0**2),
        rel=1.0e-5,
    )


def test_circular_plane_face_has_one_wire_when_inner_radius_is_omitted():
    surface = _annular_surface(inner_radius_mm=None)

    face, metadata = make_annular_plane_face(surface)

    assert _wire_count(face) == 1
    assert metadata["loop_count"] == 1
    assert _surface_area(face) == pytest.approx(math.pi * 50.0**2, rel=1.0e-5)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("outer_radius_mm", 0.0, "outer_radius_mm must be positive"),
        ("outer_radius_mm", -1.0, "outer_radius_mm must be positive"),
        ("inner_radius_mm", -1.0, "inner_radius_mm must be non-negative"),
        ("inner_radius_mm", 50.0, "inner_radius_mm must be less than outer_radius_mm"),
        ("inner_radius_mm", 51.0, "inner_radius_mm must be less than outer_radius_mm"),
        ("outer_radius_mm", float("nan"), "outer_radius_mm must be finite"),
        ("outer_radius_mm", float("inf"), "outer_radius_mm must be finite"),
        ("outer_radius_mm", float("-inf"), "outer_radius_mm must be finite"),
        ("inner_radius_mm", float("nan"), "inner_radius_mm must be finite"),
        ("inner_radius_mm", float("inf"), "inner_radius_mm must be finite"),
        ("inner_radius_mm", float("-inf"), "inner_radius_mm must be finite"),
    ],
)
def test_make_annular_plane_face_rejects_invalid_radii(field: str, value: float, match: str):
    surface = _annular_surface(**{field: value})

    with pytest.raises(ValueError, match=match):
        make_annular_plane_face(surface)


def test_write_bounded_brep_step_exports_annular_plane_without_unbounded_marker(tmp_path: Path):
    step_path = tmp_path / "bounded_annular.step"
    surface_graph = _surface_graph(_annular_surface())

    manifest = write_bounded_brep_step(step_path, "impeller", surface_graph)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert step_path.stat().st_size > 1024
    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is True
    assert manifest["source"] == "surface_graph"
    assert manifest["view"] == "cad_review_360"
    assert manifest["solid_name"] == "impeller"
    assert manifest["export_exactness"] == BOUNDED_STEP_EXACTNESS
    assert manifest["target_exactness"] == BOUNDED_STEP_EXACTNESS
    assert manifest["bounded_face_count"] == 1
    assert manifest["sewing_status"] == "not_attempted"
    assert manifest["open_edge_count"] is None
    assert manifest["reimport_bbox"]["x_span_mm"] == pytest.approx(100.0, abs=1.0e-3)
    assert manifest["reimport_bbox"]["y_span_mm"] == pytest.approx(100.0, abs=1.0e-3)
    assert manifest["reimport_bbox"]["z_span_mm"] <= 1.0
    assert {"name": "finite_reimport_bbox", "status": "PASS"} in manifest["validation_checks"]
    assert manifest["face_regions"][0]["surface_graph_id"] == "inner_hub_bottom_face"
    assert "ADVANCED_FACE" in text
    assert "PLANE" in text
    assert "TRIANGULATED_FACE_SET" not in text


def test_write_bounded_brep_step_reimported_bounds_stay_near_outer_radius(tmp_path: Path):
    step_path = tmp_path / "bounded_annular.step"

    write_bounded_brep_step(step_path, "impeller", _surface_graph(_annular_surface()))

    bbox = reimport_step_bbox(step_path)
    assert bbox["x_min"] == pytest.approx(-50.0, abs=1.0e-3)
    assert bbox["y_min"] == pytest.approx(-50.0, abs=1.0e-3)
    assert bbox["z_min"] == pytest.approx(3.0, abs=1.0e-3)
    assert bbox["x_max"] == pytest.approx(50.0, abs=1.0e-3)
    assert bbox["y_max"] == pytest.approx(50.0, abs=1.0e-3)
    assert bbox["z_max"] == pytest.approx(3.0, abs=1.0e-3)
    assert bbox["x_span_mm"] <= 310.0
    assert bbox["y_span_mm"] <= 310.0
    assert bbox["z_span_mm"] <= 1.0
    assert all(math.isfinite(value) for value in bbox.values())


def test_write_bounded_brep_step_uses_surface_graph_id_when_id_is_missing(tmp_path: Path):
    surface = _annular_surface(surface_graph_id="fallback_annular_face")
    del surface["id"]

    manifest = write_bounded_brep_step(tmp_path / "bounded_annular.step", "impeller", _surface_graph(surface))

    assert manifest["face_regions"][0]["surface_graph_id"] == "fallback_annular_face"


def test_bounded_step_marker_check_rejects_scientific_notation_huge_plane_marker(tmp_path: Path):
    step_path = tmp_path / "legacy_unbounded.step"
    step_path.write_text(
        "ISO-10303-21;\nDATA;\n#1=CARTESIAN_POINT('',(1.E+04,-1.E4,0.));\nENDSEC;\n",
        encoding="utf-8",
    )

    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is False


@pytest.mark.parametrize(
    "marker",
    ["10000", "-10000", "10000.", "-10000.", "1.E+04", "-1.E+04", "1.E4"],
)
def test_bounded_step_marker_check_rejects_huge_plane_marker_forms(tmp_path: Path, marker: str):
    step_path = tmp_path / "legacy_unbounded.step"
    step_path.write_text(f"CARTESIAN_POINT('',({marker},0.,0.));", encoding="utf-8")

    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is False


def test_write_bounded_brep_step_rejects_unsupported_surface_kind(tmp_path: Path):
    surface = _annular_surface(kind="nurbs_revolve_surface")

    with pytest.raises(
        ValueError,
        match="unsupported bounded brep surface kind: nurbs_revolve_surface",
    ):
        write_bounded_brep_step(tmp_path / "unsupported.step", "impeller", _surface_graph(surface))


def test_write_bounded_brep_step_rejects_empty_surface_graph(tmp_path: Path):
    with pytest.raises(ValueError, match="surface graph bounded brep export produced no faces"):
        write_bounded_brep_step(tmp_path / "empty.step", "impeller", {"surfaces": [], "edges": []})


def test_reimport_step_bbox_rejects_unreadable_step_file(tmp_path: Path):
    step_path = tmp_path / "not_step.step"
    step_path.write_text("not a STEP file", encoding="utf-8")

    with pytest.raises(RuntimeError, match="OCCT STEP read failed"):
        reimport_step_bbox(step_path)


def test_reimport_step_bbox_rejects_empty_step_without_shapes(tmp_path: Path):
    step_path = tmp_path / "empty.step"
    step_path.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="OCCT STEP transfer produced no shapes"):
        reimport_step_bbox(step_path)


def test_bbox_exactness_gate_rejects_nonfinite_values():
    bbox = _bbox(
        x_span_mm=100.0,
        y_span_mm=float("nan"),
        z_span_mm=0.0,
    )

    assert _bbox_passes_exactness_gate(bbox) is False


def test_bbox_exactness_gate_rejects_large_spans():
    bbox = _bbox(x_span_mm=FINITE_REIMPORT_BBOX_MAX_SPAN_MM, y_span_mm=100.0, z_span_mm=0.0)

    assert _bbox_passes_exactness_gate(bbox) is False


def test_write_bounded_brep_step_marks_large_reimport_bbox_diagnostic(tmp_path: Path, monkeypatch):
    large_bbox = _bbox(x_span_mm=FINITE_REIMPORT_BBOX_MAX_SPAN_MM, y_span_mm=100.0, z_span_mm=0.0)

    monkeypatch.setattr(
        "part_rule_synthesis.impeller_bounded_brep_export.reimport_step_bbox",
        lambda _path: large_bbox,
    )

    manifest = write_bounded_brep_step(tmp_path / "large.step", "impeller", _surface_graph(_annular_surface()))

    assert manifest["export_exactness"] == DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
    assert {"name": "finite_reimport_bbox", "status": "FAIL"} in manifest["validation_checks"]


def test_write_bounded_brep_step_rejects_transition_resolved_validation_failures(
    tmp_path: Path,
    monkeypatch,
):
    large_bbox = _bbox(x_span_mm=FINITE_REIMPORT_BBOX_MAX_SPAN_MM, y_span_mm=100.0, z_span_mm=0.0)
    surface_graph = {
        **_surface_graph(_annular_surface()),
        "transition_geometry_status": "resolved_trimmed_surface_graph",
    }

    monkeypatch.setattr(
        "part_rule_synthesis.impeller_bounded_brep_export.reimport_step_bbox",
        lambda _path: large_bbox,
    )

    with pytest.raises(RuntimeError, match="finite_reimport_bbox"):
        write_bounded_brep_step(tmp_path / "transition_large.step", "impeller", surface_graph)


def _annular_surface(**overrides):
    surface = {
        "id": "inner_hub_bottom_face",
        "kind": "annular_plane_surface",
        "feature_id": "hub",
        "role": "inner_hub_bottom",
        "inner_radius_mm": 20.0,
        "outer_radius_mm": 50.0,
        "z_mm": 3.0,
    }
    surface.update(overrides)
    return surface


def _surface_graph(surface):
    return {"surfaces": [surface], "edges": []}


def _bbox(**overrides):
    bbox = {
        "x_min": -50.0,
        "x_max": 50.0,
        "y_min": -50.0,
        "y_max": 50.0,
        "z_min": 0.0,
        "z_max": 0.0,
        "x_span_mm": 100.0,
        "y_span_mm": 100.0,
        "z_span_mm": 0.0,
    }
    bbox.update(overrides)
    return bbox


def _wire_count(shape):
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, TopAbs_WIRE)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _surface_area(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, properties)
    return properties.Mass()
