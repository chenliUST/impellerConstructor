from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


BOUNDED_STEP_EXACTNESS = "surface_graph_trimmed_brep_step"
DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS = "surface_graph_bounded_unsewn_brep_step"
TRANSITION_RESOLVED_STEP_EXACTNESS = "transition_resolved_trimmed_brep_step"
TRANSITION_RESOLVED_BOUNDED_UNSEWN_EXACTNESS = "transition_resolved_bounded_unsewn_brep_step"
FINITE_REIMPORT_BBOX_MAX_SPAN_MM = 5000.0
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
        "cad_surface_type": "annular_plane",
        "outer_radius_mm": outer_radius,
        "inner_radius_mm": inner_radius,
        "z_mm": z,
        "loop_count": loop_count,
    }


def _face_from_surface_graph_surface(surface: dict[str, Any], surface_id: str):
    kind = str(surface.get("kind") or "")
    if kind == "annular_plane_surface":
        return make_annular_plane_face(surface)
    if kind == "cylindrical_surface":
        return _make_cylindrical_face(surface)
    return _make_bspline_face_from_uv_grid(surface, surface_id)


def _make_cylindrical_face(surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    cad_surface = surface.get("cad_surface") or {}
    radius = _finite_positive_float(
        surface.get("radius_mm", cad_surface.get("radius_mm")),
        "cylindrical surface radius_mm",
    )
    z_min = _finite_float(
        surface.get("z_min_mm", cad_surface.get("z_min_mm")),
        "cylindrical surface z_min_mm",
    )
    z_max = _finite_float(
        surface.get("z_max_mm", cad_surface.get("z_max_mm")),
        "cylindrical surface z_max_mm",
    )
    if z_max <= z_min:
        raise ValueError("cylindrical surface z_max_mm must be greater than z_min_mm")

    axis = gp_Ax3(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0), gp_Dir(1.0, 0.0, 0.0))
    cylinder = Geom_CylindricalSurface(axis, radius)
    face_maker = BRepBuilderAPI_MakeFace(cylinder, 0.0, 2.0 * math.pi, z_min, z_max, 1.0e-6)
    if not face_maker.IsDone():
        raise RuntimeError("OCCT failed to build bounded cylindrical face")
    face = face_maker.Face()
    if face.IsNull():
        raise RuntimeError("OCCT built a null bounded cylindrical face")

    return face, {
        "bounded": True,
        "cad_surface_type": "cylinder",
        "radius_mm": radius,
        "z_min_mm": z_min,
        "z_max_mm": z_max,
        "fit_max_error_mm": 0.0,
        "fit_rms_error_mm": 0.0,
        "source_grid_u_count": 0,
        "source_grid_v_count": 0,
        "used_grid_u_count": 0,
        "used_grid_v_count": 0,
    }


def _make_bspline_face_from_uv_grid(surface: dict[str, Any], surface_id: str):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

    uv_grid = _rectangular_uv_grid(surface.get("uv_grid"), surface_id)
    bspline_surface = _bspline_surface_from_grid(uv_grid, surface_id)
    fit = _bspline_fit_error(bspline_surface, uv_grid)
    _validate_fit_error(surface_id, fit, uv_grid)

    face_maker = BRepBuilderAPI_MakeFace(bspline_surface, 1.0e-6)
    if not face_maker.IsDone():
        raise RuntimeError(f"OCCT failed to build bounded B-spline face for {surface_id}")
    face = face_maker.Face()
    if face.IsNull():
        raise RuntimeError(f"OCCT built a null bounded B-spline face for {surface_id}")

    return face, {
        "bounded": True,
        "cad_surface_type": "bspline_surface",
        "fit_max_error_mm": fit["fit_max_error_mm"],
        "fit_rms_error_mm": fit["fit_rms_error_mm"],
        "fit_max_tolerance_mm": fit["fit_max_tolerance_mm"],
        "fit_rms_tolerance_mm": fit["fit_rms_tolerance_mm"],
        "fit_sample_count": int(fit["fit_sample_count"]),
        "source_grid_u_count": len(uv_grid),
        "source_grid_v_count": len(uv_grid[0]),
        "used_grid_u_count": len(uv_grid),
        "used_grid_v_count": len(uv_grid[0]),
    }


def _bspline_surface_from_grid(uv_grid: list[list[list[float]]], surface_id: str):
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt

    u_count = len(uv_grid)
    v_count = len(uv_grid[0])
    points = TColgp_Array2OfPnt(1, u_count, 1, v_count)
    for u_index, row in enumerate(uv_grid, start=1):
        for v_index, point in enumerate(row, start=1):
            points.SetValue(
                u_index,
                v_index,
                gp_Pnt(float(point[0]), float(point[1]), float(point[2])),
            )

    try:
        builder = GeomAPI_PointsToBSplineSurface()
        builder.Interpolate(points)
    except Exception as exc:
        raise RuntimeError(f"OCCT failed to interpolate B-spline surface for {surface_id}") from exc

    if not builder.IsDone():
        raise RuntimeError(f"OCCT B-spline interpolation did not complete for {surface_id}")
    surface = builder.Surface()
    if surface is None:
        raise RuntimeError(f"OCCT B-spline interpolation returned no surface for {surface_id}")
    return surface


def _bspline_fit_error(bspline_surface: Any, uv_grid: list[list[list[float]]]) -> dict[str, float]:
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt

    max_error = 0.0
    squared_error = 0.0
    sample_count = 0
    for u_index in _sample_indices(len(uv_grid), max_count=7):
        row = uv_grid[u_index]
        for v_index in _sample_indices(len(row), max_count=7):
            expected = row[v_index]
            expected_point = gp_Pnt(float(expected[0]), float(expected[1]), float(expected[2]))
            projector = GeomAPI_ProjectPointOnSurf(expected_point, bspline_surface)
            if projector.IsDone() and projector.NbPoints() > 0:
                error = float(projector.LowerDistance())
            else:
                u_min, u_max, v_min, v_max = bspline_surface.Bounds()
                actual = bspline_surface.Value(
                    0.5 * (u_min + u_max),
                    0.5 * (v_min + v_max),
                )
                error = math.dist(
                    [actual.X(), actual.Y(), actual.Z()],
                    [float(expected[0]), float(expected[1]), float(expected[2])],
                )
            max_error = max(max_error, error)
            squared_error += error * error
            sample_count += 1

    bbox_diagonal = _grid_bbox_diagonal(uv_grid)
    return {
        "fit_max_error_mm": max_error,
        "fit_rms_error_mm": math.sqrt(squared_error / max(1, sample_count)),
        "fit_max_tolerance_mm": max(1.0, 0.001 * bbox_diagonal),
        "fit_rms_tolerance_mm": max(0.25, 0.00025 * bbox_diagonal),
        "fit_sample_count": float(sample_count),
    }


def _validate_fit_error(surface_id: str, fit: dict[str, float], uv_grid: list[list[list[float]]]) -> None:
    if fit["fit_max_error_mm"] > fit["fit_max_tolerance_mm"]:
        raise RuntimeError(
            f"{surface_id} B-spline fit max error {fit['fit_max_error_mm']:.6g} mm exceeds "
            f"{fit['fit_max_tolerance_mm']:.6g} mm tolerance"
        )
    if fit["fit_rms_error_mm"] > fit["fit_rms_tolerance_mm"]:
        raise RuntimeError(
            f"{surface_id} B-spline fit RMS error {fit['fit_rms_error_mm']:.6g} mm exceeds "
            f"{fit['fit_rms_tolerance_mm']:.6g} mm tolerance"
        )


def _rectangular_uv_grid(value: Any, surface_id: str) -> list[list[list[float]]]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError(f"{surface_id} missing rectangular uv_grid")
    if not isinstance(value[0], list) or len(value[0]) < 2:
        raise ValueError(f"{surface_id} missing rectangular uv_grid")
    v_count = len(value[0])
    grid: list[list[list[float]]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != v_count:
            raise ValueError(f"{surface_id} missing rectangular uv_grid")
        grid.append([_point3(point, surface_id) for point in row])
    return grid


def _point3(value: Any, surface_id: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{surface_id} uv_grid points must have three coordinates")
    point = [float(coordinate) for coordinate in value]
    if not all(math.isfinite(coordinate) for coordinate in point):
        raise ValueError(f"{surface_id} uv_grid points must be finite")
    return point


def _grid_bbox_diagonal(uv_grid: list[list[list[float]]]) -> float:
    xs = [point[0] for row in uv_grid for point in row]
    ys = [point[1] for row in uv_grid for point in row]
    zs = [point[2] for row in uv_grid for point in row]
    return math.dist(
        [min(xs), min(ys), min(zs)],
        [max(xs), max(ys), max(zs)],
    )


def _sample_indices(count: int, max_count: int) -> list[int]:
    if count <= max_count:
        return list(range(count))
    indices = {
        round(index * (count - 1) / (max_count - 1))
        for index in range(max_count)
    }
    return sorted(indices)


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
    surface_kind_counts: Counter[str] = Counter()
    cad_surface_type_counts: Counter[str] = Counter()
    included_surface_ids: list[str] = []
    for surface_index, surface in enumerate(surface_graph.get("surfaces", [])):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or f"surface_{surface_index}")
        kind = str(surface.get("kind") or "missing")
        surface_kind_counts[kind] += 1

        face, face_metadata = _face_from_surface_graph_surface(surface, surface_id)
        cad_surface_type_counts[str(face_metadata["cad_surface_type"])] += 1
        faces.append(face)
        included_surface_ids.append(surface_id)
        face_regions.append(
            {
                "brep_face_id": f"face_{surface_index:04d}",
                "face_index": surface_index,
                "surface_graph_id": surface_id,
                "feature_id": surface.get("feature_id"),
                "role": surface.get("role"),
                "kind": kind,
                **_transition_region_metadata(surface),
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

    bbox = reimport_step_bbox(step_path)
    reimport_face_count = reimport_step_face_count(step_path)
    finite_bbox = _bbox_passes_exactness_gate(bbox)
    complete_coverage = len(included_surface_ids) == len(surface_graph.get("surfaces", []))
    face_count_matches = reimport_face_count == len(faces)
    transition_resolved = surface_graph.get("transition_geometry_status") == "resolved_trimmed_surface_graph"
    export_exactness = (
        TRANSITION_RESOLVED_BOUNDED_UNSEWN_EXACTNESS
        if transition_resolved
        else DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
    )
    target_exactness = TRANSITION_RESOLVED_STEP_EXACTNESS if transition_resolved else BOUNDED_STEP_EXACTNESS
    coverage_status = (
        "complete_transition_resolved_surface_graph"
        if transition_resolved
        else "complete_surface_graph_cad_surfaces"
    )
    cad_export_scope = (
        "all_transition_resolved_surface_graph_cad_surfaces"
        if transition_resolved
        else "all_surface_graph_cad_surfaces"
    )

    validation_checks = [
        {
            "name": "finite_reimport_bbox",
            "status": "PASS" if finite_bbox else "FAIL",
        },
        {
            "name": "complete_surface_coverage",
            "status": "PASS" if complete_coverage else "FAIL",
        },
        {
            "name": "reimport_face_count_matches_manifest",
            "status": "PASS" if face_count_matches else "FAIL",
        },
    ]

    return {
        "source": "surface_graph",
        "view": view_id,
        "solid_name": solid_name,
        "export_exactness": export_exactness,
        "target_exactness": target_exactness,
        **({"transition_geometry_status": surface_graph["transition_geometry_status"]} if transition_resolved else {}),
        "step_writer": "occt_stepcontrol_writer",
        "bounded_face_count": len(faces),
        "reimport_face_count": reimport_face_count,
        "bounded_brep_status": "bounded_faces_unsewn",
        "sewing_status": "not_attempted",
        "open_edge_count": None,
        "coverage_status": coverage_status,
        "cad_export_scope": cad_export_scope,
        "unsupported_surface_policy": "fail_export",
        "total_surface_count": len(surface_graph.get("surfaces", [])),
        "supported_surface_count": len(faces),
        "surface_count": len(faces),
        "unsupported_surface_count": 0,
        "surface_kind_counts": dict(sorted(surface_kind_counts.items())),
        "cad_surface_type_counts": dict(sorted(cad_surface_type_counts.items())),
        "included_surface_ids": included_surface_ids,
        "excluded_surface_ids": [],
        "reimport_bbox": bbox,
        "validation_checks": validation_checks,
        "limitations": [
            "bounded_faces_are_unsewn",
            "shared_edge_topology_not_sewn",
            "trim_loop_pcurves_not_consumed",
        ],
        "face_regions": face_regions,
    }


def _transition_region_metadata(surface: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "edge_family",
        "transition_policy_id",
        "edge_treatment_site_id",
        "treatment",
        "radius_mm",
    ]
    return {field: surface[field] for field in fields if field in surface}


def reimport_step_bbox(path: Path) -> dict[str, float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    read_status = reader.ReadFile(str(path))
    if read_status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP read failed with status {read_status}")

    try:
        transferred_root_count = reader.TransferRoots()
    except Exception as exc:
        raise RuntimeError("OCCT STEP transfer failed") from exc

    if transferred_root_count <= 0 or reader.NbShapes() <= 0:
        raise RuntimeError("OCCT STEP transfer produced no shapes")

    try:
        shape = reader.OneShape()
    except Exception as exc:
        raise RuntimeError("OCCT STEP transfer produced no usable shape") from exc

    if shape.IsNull():
        raise RuntimeError("OCCT STEP transfer produced a null shape")

    box = Bnd_Box()
    try:
        BRepBndLib.Add_s(shape, box)
    except Exception as exc:
        raise RuntimeError("OCCT STEP bbox calculation failed") from exc

    if box.IsVoid():
        raise RuntimeError("OCCT STEP bbox calculation produced a void box")

    try:
        x_min, y_min, z_min, x_max, y_max, z_max = box.Get()
    except Exception as exc:
        raise RuntimeError("OCCT STEP bbox calculation failed") from exc

    return {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": z_min,
        "z_max": z_max,
        "x_span_mm": x_max - x_min,
        "y_span_mm": y_max - y_min,
        "z_span_mm": z_max - z_min,
    }


def reimport_step_face_count(path: Path) -> int:
    shape = _reimport_step_shape(path)
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _reimport_step_shape(path: Path):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    read_status = reader.ReadFile(str(path))
    if read_status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP read failed with status {read_status}")

    try:
        transferred_root_count = reader.TransferRoots()
    except Exception as exc:
        raise RuntimeError("OCCT STEP transfer failed") from exc

    if transferred_root_count <= 0 or reader.NbShapes() <= 0:
        raise RuntimeError("OCCT STEP transfer produced no shapes")

    try:
        shape = reader.OneShape()
    except Exception as exc:
        raise RuntimeError("OCCT STEP transfer produced no usable shape") from exc

    if shape.IsNull():
        raise RuntimeError("OCCT STEP transfer produced a null shape")
    return shape


def _bbox_passes_exactness_gate(bbox: dict[str, float]) -> bool:
    if not all(math.isfinite(value) for value in bbox.values()):
        return False
    return max(bbox["x_span_mm"], bbox["y_span_mm"], bbox["z_span_mm"]) < FINITE_REIMPORT_BBOX_MAX_SPAN_MM


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


def _finite_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _finite_positive_float(value: Any, field_name: str) -> float:
    result = _finite_float(value, field_name)
    if result <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return result
