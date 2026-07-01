from __future__ import annotations

from pathlib import Path

from scripts.render_impeller_parameter_diagrams import render_all_diagrams


def test_render_impeller_parameter_diagrams_from_current_kernel(tmp_path: Path):
    outputs = render_all_diagrams(tmp_path)

    expected = {
        "01_meridional_parameters.svg",
        "02_blade_uv_boundaries.svg",
        "03_blade_thickness_and_lean.svg",
        "04_open_closed_tip_support.svg",
        "impeller_parameter_geometry.md",
    }
    assert expected.issubset({path.name for path in outputs})
    for path in outputs:
        assert path.exists()
        assert path.stat().st_size > 200

    meridional = (tmp_path / "01_meridional_parameters.svg").read_text(encoding="utf-8")
    assert "Generated from axisymmetric_throughflow_nurbs" in meridional
    assert "inlet_radius_mm" in meridional
    assert "outlet_blade_height_mm" in meridional

    blade_uv = (tmp_path / "02_blade_uv_boundaries.svg").read_text(encoding="utf-8")
    assert "blade_root_boundary: v=0" in blade_uv
    assert "leading_edge_boundary: u=0" in blade_uv

    doc = (tmp_path / "impeller_parameter_geometry.md").read_text(encoding="utf-8")
    assert "Currently active kernel parameters" in doc
    assert "Currently not wired into this kernel" in doc
    assert "hub_base_radius_mm" in doc
    assert "root_fillet_radius_mm" in doc
