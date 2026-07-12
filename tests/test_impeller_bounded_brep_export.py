import math
from pathlib import Path

import pytest

from part_rule_synthesis.impeller_bounded_brep_export import (
    BOUNDED_STEP_EXACTNESS,
    DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS,
    FINITE_REIMPORT_BBOX_MAX_SPAN_MM,
    _bbox_passes_exactness_gate,
    _bspline_fit_tolerances,
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
    assert manifest["export_exactness"] == DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
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


def test_write_bounded_brep_step_exports_complete_mixed_surface_graph(tmp_path: Path):
    step_path = tmp_path / "complete_surface_graph.step"
    surface_graph = {
        "surfaces": [
            _annular_surface(),
            _cylindrical_surface(),
            _freeform_surface(),
        ],
        "edges": [],
    }

    manifest = write_bounded_brep_step(step_path, "impeller", surface_graph)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert manifest["export_exactness"] == DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
    assert manifest["target_exactness"] == BOUNDED_STEP_EXACTNESS
    assert manifest["coverage_status"] == "complete_surface_graph_cad_surfaces"
    assert manifest["cad_export_scope"] == "all_surface_graph_cad_surfaces"
    assert manifest["unsupported_surface_policy"] == "fail_export"
    assert manifest["total_surface_count"] == 3
    assert manifest["bounded_face_count"] == 3
    assert manifest["reimport_face_count"] == 3
    assert manifest["supported_surface_count"] == 3
    assert manifest["unsupported_surface_count"] == 0
    assert manifest["included_surface_ids"] == [
        "inner_hub_bottom_face",
        "mounting_bore_cylinder",
        "blade_0_pressure_surface",
    ]
    assert manifest["excluded_surface_ids"] == []
    assert manifest["surface_kind_counts"] == {
        "annular_plane_surface": 1,
        "cylindrical_surface": 1,
        "nurbs_surface": 1,
    }
    assert manifest["cad_surface_type_counts"] == {
        "annular_plane": 1,
        "cylinder": 1,
        "bspline_surface": 1,
    }
    assert [region["face_index"] for region in manifest["face_regions"]] == [0, 1, 2]
    assert manifest["face_regions"][2]["fit_max_error_mm"] <= 1.0
    assert manifest["face_regions"][2]["fit_rms_error_mm"] <= 0.25
    assert {"name": "complete_surface_coverage", "status": "PASS"} in manifest["validation_checks"]
    assert {"name": "reimport_face_count_matches_manifest", "status": "PASS"} in manifest["validation_checks"]
    assert "ADVANCED_FACE" in text
    assert "B_SPLINE_SURFACE" in text
    assert "CYLINDRICAL_SURFACE" in text
    assert "TRIANGULATED_FACE_SET" not in text
    assert bounded_step_contains_no_unbounded_plane_marker(step_path) is True


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


def test_bspline_fit_tolerance_uses_sample_grid_resolution_for_large_review_surfaces():
    grid = [
        [[0.0, 0.0, 0.0], [0.0, 100.0, 4.0], [0.0, 200.0, 0.0]],
        [[100.0, 0.0, 10.0], [100.0, 100.0, 25.0], [100.0, 200.0, 10.0]],
        [[200.0, 0.0, 0.0], [200.0, 100.0, 4.0], [200.0, 200.0, 0.0]],
    ]

    tolerances = _bspline_fit_tolerances(grid)

    assert tolerances["fit_grid_resolution_mm"] > 100.0
    assert tolerances["fit_max_tolerance_mm"] == pytest.approx(0.05 * tolerances["fit_grid_resolution_mm"])
    assert tolerances["fit_rms_tolerance_mm"] == pytest.approx(0.01 * tolerances["fit_grid_resolution_mm"])


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


def test_write_bounded_brep_step_rejects_freeform_surface_without_uv_grid(tmp_path: Path):
    surface = _freeform_surface()
    del surface["uv_grid"]

    with pytest.raises(
        ValueError,
        match="blade_0_pressure_surface missing rectangular uv_grid",
    ):
        write_bounded_brep_step(tmp_path / "unsupported.step", "impeller", _surface_graph(surface))


def test_bspline_grid_guard_rejects_collapsed_rows_before_occt():
    from part_rule_synthesis.impeller_bounded_brep_export import validate_bspline_grid_for_occt

    collapsed_grid = [
        [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0]],
        [[2.0, 2.0, 3.0], [2.0, 3.0, 3.0], [2.0, 4.0, 3.0]],
        [[3.0, 2.0, 3.0], [3.0, 3.0, 3.0], [3.0, 4.0, 3.0]],
    ]

    with pytest.raises(ValueError, match="collapsed row"):
        validate_bspline_grid_for_occt(collapsed_grid, "collapsed_corner")


def test_bspline_grid_guard_rejects_collapsed_columns_before_occt():
    from part_rule_synthesis.impeller_bounded_brep_export import validate_bspline_grid_for_occt

    collapsed_grid = [
        [[1.0, 2.0, 3.0], [2.0, 2.0, 3.0], [3.0, 2.0, 3.0]],
        [[1.0, 2.0, 3.0], [2.0, 3.0, 3.0], [3.0, 4.0, 3.0]],
        [[1.0, 2.0, 3.0], [2.0, 4.0, 3.0], [3.0, 6.0, 3.0]],
    ]

    with pytest.raises(ValueError, match="collapsed column"):
        validate_bspline_grid_for_occt(collapsed_grid, "collapsed_corner")


def test_bspline_grid_guard_rejects_rank_deficient_line_grid_before_occt():
    from part_rule_synthesis.impeller_bounded_brep_export import validate_bspline_grid_for_occt

    line_grid = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        [[2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [4.0, 0.0, 0.0]],
    ]

    with pytest.raises(ValueError, match="rank-deficient"):
        validate_bspline_grid_for_occt(line_grid, "line_grid")


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


def _cylindrical_surface(**overrides):
    surface = {
        "id": "mounting_bore_cylinder",
        "kind": "cylindrical_surface",
        "feature_id": "hub",
        "role": "mounting_bore",
        "radius_mm": 12.0,
        "z_min_mm": 0.0,
        "z_max_mm": 30.0,
        "cad_surface": {
            "surface_type": "cylinder",
            "radius_mm": 12.0,
            "z_min_mm": 0.0,
            "z_max_mm": 30.0,
        },
    }
    surface.update(overrides)
    return surface


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
