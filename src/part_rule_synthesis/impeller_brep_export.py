from __future__ import annotations

from pathlib import Path
from typing import Any

from part_rule_synthesis.impeller_cad_payload import knot_values_and_multiplicities
from part_rule_synthesis.occt_compat import int_array, real_array


def write_trimmed_brep_step(
    step_path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    from OCP.BRep import BRep_Builder
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    faces: list[tuple[Any, dict[str, Any]]] = []
    face_regions: list[dict[str, Any]] = []
    for surface_index, surface in enumerate(surface_graph.get("surfaces", [])):
        surface_id = str(surface.get("id", f"surface_{surface_index}"))
        cad_surface = surface.get("cad_surface")
        if cad_surface is None:
            raise ValueError(f"{surface_id} missing cad_surface")

        face = _make_bspline_face(cad_surface)
        faces.append((face, surface))
        face_regions.append(
            {
                "brep_face_id": f"face_{surface_index:04d}",
                "surface_graph_id": surface_id,
                "feature_id": surface.get("feature_id"),
                "role": surface.get("role"),
                "cad_surface_type": cad_surface.get("surface_type"),
            }
        )

    if not faces:
        raise ValueError("surface graph brep export produced no faces")

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face, _surface in faces:
        builder.Add(compound, face)

    writer = STEPControl_Writer()
    schema_key = "write.step.schema"
    schema_value = "AP214IS"
    previous_schema = Interface_Static.CVal_s(schema_key)
    try:
        if not Interface_Static.SetCVal_s(schema_key, schema_value):
            raise RuntimeError(f"OCCT STEP schema setup failed for {schema_value}")

        transfer_status = writer.Transfer(compound, STEPControl_AsIs)
        if transfer_status != IFSelect_RetDone:
            raise RuntimeError(f"OCCT STEP transfer failed with status {transfer_status}")

        write_status = writer.Write(str(step_path))
        if write_status != IFSelect_RetDone:
            raise RuntimeError(f"OCCT STEP write failed with status {write_status}")
    finally:
        Interface_Static.SetCVal_s(schema_key, previous_schema)

    return {
        "source": "surface_graph",
        "view": view_id,
        "solid_name": solid_name,
        "export_exactness": "surface_graph_trimmed_nurbs_step",
        "step_writer": "occt_stepcontrol_writer",
        "brep_face_count": len(faces),
        "shell_count": 0,
        "sewing_status": "not_attempted",
        "face_regions": face_regions,
        "limitations": ["initial_faces_are_unsewn"],
    }


def _make_bspline_face(cad_surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

    surface_type = cad_surface.get("surface_type")
    if surface_type != "bspline_surface":
        raise ValueError(f"unsupported cad_surface surface_type {surface_type!r}")

    surface = _make_bspline_surface(cad_surface)
    return BRepBuilderAPI_MakeFace(surface, 1.0e-6).Face()


def _make_bspline_surface(cad_surface: dict[str, Any]):
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array2OfReal

    control_points = cad_surface["control_points"]
    weights = cad_surface.get("weights")
    u_count = len(control_points)
    v_count = len(control_points[0])

    poles = TColgp_Array2OfPnt(1, u_count, 1, v_count)
    for u_index, row in enumerate(control_points, start=1):
        for v_index, point in enumerate(row, start=1):
            poles.SetValue(
                u_index,
                v_index,
                gp_Pnt(float(point[0]), float(point[1]), float(point[2])),
            )

    knot_values_u, knot_multiplicities_u = knot_values_and_multiplicities(cad_surface["knots_u"])
    knot_values_v, knot_multiplicities_v = knot_values_and_multiplicities(cad_surface["knots_v"])
    u_knots = real_array(knot_values_u)
    v_knots = real_array(knot_values_v)
    u_multiplicities = int_array(knot_multiplicities_u)
    v_multiplicities = int_array(knot_multiplicities_v)

    degree_u = int(cad_surface["degree_u"])
    degree_v = int(cad_surface["degree_v"])
    if weights is None:
        return Geom_BSplineSurface(
            poles,
            u_knots,
            v_knots,
            u_multiplicities,
            v_multiplicities,
            degree_u,
            degree_v,
            False,
            False,
        )

    occt_weights = TColStd_Array2OfReal(1, u_count, 1, v_count)
    for u_index, row in enumerate(weights, start=1):
        for v_index, weight in enumerate(row, start=1):
            occt_weights.SetValue(u_index, v_index, float(weight))

    return Geom_BSplineSurface(
        poles,
        occt_weights,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        degree_u,
        degree_v,
        False,
        False,
    )
