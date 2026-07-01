from pathlib import Path

from part_rule_synthesis.occt_compat import write_minimal_bspline_step


def test_occt_can_write_minimal_bspline_step(tmp_path: Path):
    step_path = tmp_path / "minimal_bspline.step"

    metadata = write_minimal_bspline_step(step_path)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert metadata == {
        "writer": "occt_stepcontrol_writer",
        "shape": "single_bspline_face",
        "status": "PASS",
    }
    assert step_path.stat().st_size > 1024
    assert "B_SPLINE_SURFACE" in text
    assert "ADVANCED_FACE" in text
    assert "TRIANGULATED_FACE_SET" not in text
