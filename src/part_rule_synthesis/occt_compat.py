from __future__ import annotations

from pathlib import Path


def write_minimal_bspline_step(path: Path) -> dict[str, str]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TColgp import TColgp_Array2OfPnt

    poles = TColgp_Array2OfPnt(1, 4, 1, 4)
    for u_index in range(1, 5):
        for v_index in range(1, 5):
            poles.SetValue(
                u_index,
                v_index,
                gp_Pnt(float(u_index - 1), float(v_index - 1), 0.1 * (u_index - 1) * (v_index - 1)),
            )

    u_knots = _real_array([0.0, 1.0])
    v_knots = _real_array([0.0, 1.0])
    u_multiplicities = _int_array([4, 4])
    v_multiplicities = _int_array([4, 4])
    surface = Geom_BSplineSurface(
        poles,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        3,
        3,
        False,
        False,
    )
    face = BRepBuilderAPI_MakeFace(surface, 1.0e-6).Face()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    writer.Transfer(face, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP write failed with status {status}")
    return {"writer": "occt_stepcontrol_writer", "shape": "single_bspline_face", "status": "PASS"}


def _real_array(values: list[float]):
    from OCP.TColStd import TColStd_Array1OfReal

    result = TColStd_Array1OfReal(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, float(value))
    return result


def _int_array(values: list[int]):
    from OCP.TColStd import TColStd_Array1OfInteger

    result = TColStd_Array1OfInteger(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, int(value))
    return result
