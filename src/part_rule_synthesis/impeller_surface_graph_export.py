from __future__ import annotations

import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any


CFD_HIDDEN_ROLES = {
    "construction_support_only",
    "reference_only",
    "mounting_bore",
    "shaft_seat",
    "keyway",
    "rear_hub_groove",
}


def write_surface_graph_exports(
    step_path: Path,
    stl_path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, dict[str, Any]]:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
    if triangulation["triangle_count"] == 0:
        raise ValueError("surface graph export produced no non-degenerate triangles")

    triangles = triangulation["triangles"]
    _write_binary_stl(stl_path, solid_name, triangles)
    _write_step_faces(step_path, triangles)

    common = {
        "source": "surface_graph",
        "view": view_id,
        "surface_count": len(triangulation["included_surface_ids"]),
        "included_surface_ids": triangulation["included_surface_ids"],
        "excluded_surface_ids": triangulation["excluded_surface_ids"],
        "skipped_triangle_count": triangulation["skipped_triangle_count"],
        "skipped_triangle_reasons": triangulation["skipped_triangle_reasons"],
    }
    return {
        "stl": {
            **common,
            "export_exactness": "surface_graph_sampled_mesh",
            "triangle_count": triangulation["triangle_count"],
            "triangle_regions": triangulation["triangle_regions"],
        },
        "step": {
            **common,
            "export_exactness": "surface_graph_mesh_step",
            "face_count": triangulation["triangle_count"],
            "face_regions": triangulation["triangle_regions"],
        },
    }


def triangulate_surface_graph(surface_graph: dict[str, Any], view_id: str = "cad_review_360") -> dict[str, Any]:
    triangles: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    included_surface_ids: list[str] = []
    excluded_surface_ids: list[str] = []

    for surface in surface_graph.get("surfaces", []):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or "")
        if not _surface_visible_in_view(surface, view_id):
            excluded_surface_ids.append(surface_id)
            continue
        grid = surface.get("uv_grid", [])
        if not _has_rectangular_quad_grid(grid):
            excluded_surface_ids.append(surface_id)
            continue

        start = len(triangles)
        v_count = len(grid[0])
        for u_index in range(len(grid) - 1):
            for v_index in range(v_count - 1):
                a = _point(grid[u_index][v_index])
                b = _point(grid[u_index + 1][v_index])
                c = _point(grid[u_index + 1][v_index + 1])
                d = _point(grid[u_index][v_index + 1])
                for points in [(a, b, d), (b, c, d)]:
                    normal = _triangle_normal(*points)
                    if normal is None:
                        skipped.append(
                            {
                                "surface_graph_id": surface_id,
                                "u_index": u_index,
                                "v_index": v_index,
                                "reason": "degenerate_triangle",
                            }
                        )
                        continue
                    triangles.append(
                        {
                            "points": [list(point) for point in points],
                            "normal": list(normal),
                            "surface_graph_id": surface_id,
                            "feature_id": str(surface.get("feature_id") or ""),
                            "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                        }
                    )
        count = len(triangles) - start
        if count > 0:
            included_surface_ids.append(surface_id)
            regions.append(
                {
                    "surface_graph_id": surface_id,
                    "feature_id": str(surface.get("feature_id") or ""),
                    "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                    "triangle_start": start,
                    "triangle_count": count,
                }
            )

    skipped_reasons = Counter(item["reason"] for item in skipped)
    return {
        "triangles": triangles,
        "triangle_count": len(triangles),
        "triangle_regions": regions,
        "included_surface_ids": included_surface_ids,
        "excluded_surface_ids": excluded_surface_ids,
        "skipped_triangle_count": len(skipped),
        "skipped_triangle_reasons": dict(sorted(skipped_reasons.items())),
        "skipped_triangles": skipped,
    }


def _surface_visible_in_view(surface: dict[str, Any], view_id: str) -> bool:
    if view_id in {"cad_review_360", "feature_debug", "feature_debug_360"}:
        return True
    if view_id != "cfd_full_360":
        return True
    roles = [surface.get("role"), surface.get("cfd_role"), surface.get("kind"), surface.get("assembly_role")]
    return not any(role in CFD_HIDDEN_ROLES for role in roles)


def _has_rectangular_quad_grid(grid: Any) -> bool:
    if not isinstance(grid, list) or len(grid) < 2:
        return False
    if not isinstance(grid[0], list) or len(grid[0]) < 2:
        return False
    v_count = len(grid[0])
    return all(isinstance(row, list) and len(row) == v_count for row in grid)


def _point(value: Any) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _triangle_normal(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    third: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    ux, uy, uz = second[0] - first[0], second[1] - first[1], second[2] - first[2]
    vx, vy, vz = third[0] - first[0], third[1] - first[1], third[2] - first[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 1.0e-9:
        return None
    return (nx / length, ny / length, nz / length)


def _write_binary_stl(path: Path, solid_name: str, triangles: list[dict[str, Any]]) -> None:
    header = f"{solid_name} surface_graph_faithful_export".encode("ascii", errors="ignore")[:80]
    with path.open("wb") as handle:
        handle.write(header.ljust(80, b" "))
        handle.write(struct.pack("<I", len(triangles)))
        for triangle in triangles:
            values = [float(value) for value in triangle["normal"]]
            for point in triangle["points"]:
                values.extend(float(value) for value in point)
            handle.write(struct.pack("<12fH", *values, 0))


def _write_step_faces(path: Path, triangles: list[dict[str, Any]]) -> None:
    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('surface_graph_mesh_step; graph-derived faceted shell'),'2;1');",
        "FILE_NAME('surface_graph_mesh_step','2026-07-01T00:00:00',('part_rule_synthesis'),('part_rule_synthesis'),'part_rule_synthesis','surface_graph_faithful_export','');",
        "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));",
        "ENDSEC;",
        "DATA;",
    ]
    next_id = 1

    def add(entity: str) -> int:
        nonlocal next_id
        entity_id = next_id
        next_id += 1
        lines.append(f"#{entity_id} = {entity};")
        return entity_id

    application_context = add("APPLICATION_CONTEXT('configuration controlled 3d designs')")
    add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,#{application_context})")
    product_context = add(f"PRODUCT_CONTEXT('',#{application_context},'mechanical')")
    product = add(f"PRODUCT('surface_graph_mesh_step','surface_graph_mesh_step','', (#{product_context}))")
    product_formation = add(f"PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',#{product},.NOT_KNOWN.)")
    product_definition_context = add(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{application_context},'design')")
    product_definition = add(f"PRODUCT_DEFINITION('','',#{product_formation},#{product_definition_context})")
    product_shape = add(f"PRODUCT_DEFINITION_SHAPE('','',#{product_definition})")
    length_unit = add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    angle_unit = add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    solid_angle_unit = add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    uncertainty = add(
        f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-6),#{length_unit},'distance_accuracy_value','')"
    )
    representation_context = add(
        "( GEOMETRIC_REPRESENTATION_CONTEXT(3) "
        f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{uncertainty})) "
        f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{length_unit},#{angle_unit},#{solid_angle_unit})) "
        "REPRESENTATION_CONTEXT('','3D') )"
    )

    face_ids = []
    for triangle in triangles:
        vertex_ids = []
        for point in triangle["points"]:
            cartesian_point = add(
                "CARTESIAN_POINT('',("
                + ",".join(_step_float(coordinate) for coordinate in point)
                + "))"
            )
            vertex_ids.append(add(f"VERTEX_POINT('',#{cartesian_point})"))
        loop = add("POLY_LOOP('',(" + ",".join(f"#{vertex_id}" for vertex_id in vertex_ids) + "))")
        bound = add(f"FACE_OUTER_BOUND('',#{loop},.T.)")
        face_ids.append(add(f"FACE('',(#{bound}))"))

    shell = add("OPEN_SHELL('',(" + ",".join(f"#{face_id}" for face_id in face_ids) + "))")
    surface_model = add(f"SHELL_BASED_SURFACE_MODEL('surface_graph_mesh_step',(#{shell}))")
    representation = add(
        f"MANIFOLD_SURFACE_SHAPE_REPRESENTATION('surface_graph_mesh_step',(#{surface_model}),#{representation_context})"
    )
    add(f"SHAPE_DEFINITION_REPRESENTATION(#{product_shape},#{representation})")

    lines.extend(["ENDSEC;", "END-ISO-10303-21;", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _step_float(value: Any) -> str:
    return f"{float(value):.9g}"
