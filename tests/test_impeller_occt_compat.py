from pathlib import Path

import pytest

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


def test_occt_step_schema_is_restored_after_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import OCP.Interface as interface_module

    schema_key = "write.step.schema"
    schema_state = {"current": "AP203"}
    set_values = []

    class FakeInterfaceStatic:
        @staticmethod
        def CVal_s(key: str) -> str:
            assert key == schema_key
            return schema_state["current"]

        @staticmethod
        def SetCVal_s(key: str, value: str) -> bool:
            assert key == schema_key
            set_values.append(value)
            schema_state["current"] = value
            return True

    monkeypatch.setattr(interface_module, "Interface_Static", FakeInterfaceStatic)

    write_minimal_bspline_step(tmp_path / "minimal_bspline.step")

    assert schema_state["current"] == "AP203"
    assert set_values[-2:] == ["AP214", "AP203"]


def test_occt_step_transfer_failure_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import OCP.STEPControl as step_module
    from OCP.IFSelect import IFSelect_RetDone

    class FailingTransferWriter:
        def Transfer(self, _shape, _mode):
            return "TRANSFER_FAILED"

        def Write(self, _path: str):
            return IFSelect_RetDone

    monkeypatch.setattr(step_module, "STEPControl_Writer", FailingTransferWriter)

    with pytest.raises(RuntimeError, match="OCCT STEP transfer failed with status TRANSFER_FAILED"):
        write_minimal_bspline_step(tmp_path / "minimal_bspline.step")
