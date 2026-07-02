from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


BOUNDED_STEP_EXACTNESS = "surface_graph_trimmed_brep_step"
DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS = "surface_graph_bounded_unsewn_brep_step"
_STEP_NUMBER_PATTERN = re.compile(
    r"(?<![#A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?(?![A-Za-z0-9_.])"
)


def make_annular_plane_face(surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.Geom import Geom_Plane
    from OCP.gp import gp_Ax2, gp_Ax3, gp_Circ, gp_Dir, gp_Pnt

    outer_radius = _finite_radius(surface["outer_radius_mm"], "outer_radius_mm")
    inner_radius_value = surface.get("inner_radius_mm")
    inner_radius = (
        None
        if inner_radius_value is None
        else _finite_radius(inner_radius_value, "inner_radius_mm")
    )
    z = float(surface.get("z_mm", 0.0))

    if outer_radius <= 0.0:
        raise ValueError("annular plane outer_radius_mm must be positive")
    if inner_radius is not None and inner_radius < 0.0:
        raise ValueError("annular plane inner_radius_mm must be non-negative")
    if inner_radius is not None and inner_radius >= outer_radius:
        raise ValueError("annular plane inner_radius_mm must be less than outer_radius_mm")

    circle_axis = gp_Ax2(gp_Pnt(0.0, 0.0, z), gp_Dir(0.0, 0.0, 1.0))
    outer_wire = BRepBuilderAPI_MakeWire(
        BRepBuilderAPI_MakeEdge(gp_Circ(circle_axis, outer_radius)).Edge()
    ).Wire()
    plane_axis = gp_Ax3(
        gp_Pnt(0.0, 0.0, z),
        gp_Dir(0.0, 0.0, 1.0),
        gp_Dir(1.0, 0.0, 0.0),
    )
    face_maker = BRepBuilderAPI_MakeFace(Geom_Plane(plane_axis), outer_wire, True)

    loop_count = 1
    if inner_radius is not None and inner_radius > 0.0:
        inner_wire = BRepBuilderAPI_MakeWire(
            BRepBuilderAPI_MakeEdge(gp_Circ(circle_axis, inner_radius)).Edge()
        ).Wire()
        inner_wire.Reverse()
        face_maker.Add(inner_wire)
        loop_count = 2

    if not face_maker.IsDone():
        raise RuntimeError("OCCT failed to build bounded annular plane face")

    face = face_maker.Face()
    if face.IsNull():
        raise RuntimeError("OCCT built a null bounded annular plane face")

    return face, {
        "bounded": True,
        "outer_radius_mm": outer_radius,
        "inner_radius_mm": inner_radius,
        "z_mm": z,
        "loop_count": loop_count,
    }


def write_bounded_brep_step(
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

    faces: list[Any] = []
    face_regions: list[dict[str, Any]] = []
    for surface_index, surface in enumerate(surface_graph.get("surfaces", [])):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or f"surface_{surface_index}")
        kind = surface.get("kind")
        if kind != "annular_plane_surface":
            raise ValueError(f"unsupported bounded brep surface kind: {kind}")

        face, face_metadata = make_annular_plane_face(surface)
        faces.append(face)
        face_regions.append(
            {
                "brep_face_id": f"face_{surface_index:04d}",
                "surface_graph_id": surface_id,
                "feature_id": surface.get("feature_id"),
                "role": surface.get("role"),
                "kind": kind,
                **face_metadata,
            }
        )

    if not faces:
        raise ValueError("surface graph bounded brep export produced no faces")

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face in faces:
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
        "export_exactness": DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS,
        "target_exactness": BOUNDED_STEP_EXACTNESS,
        "step_writer": "occt_stepcontrol_writer",
        "bounded_face_count": len(faces),
        "sewing_status": "not_attempted",
        "open_edge_count": None,
        "face_regions": face_regions,
    }


def bounded_step_contains_no_unbounded_plane_marker(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in _STEP_NUMBER_PATTERN.finditer(text):
        if abs(float(match.group(0))) == 10000.0:
            return False
    return True


def _finite_radius(value: Any, field_name: str) -> float:
    radius = float(value)
    if not math.isfinite(radius):
        raise ValueError(f"annular plane {field_name} must be finite")
    return radius
