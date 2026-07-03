from __future__ import annotations

from pathlib import Path
from typing import Any

from part_rule_synthesis.impeller_mesh_manifest import build_transition_regions
from part_rule_synthesis.impeller_surface_graph_export import _deduplicated_indexed_faces, triangulate_surface_graph


def write_surface_graph_obj(
    obj_path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
    if triangulation["triangle_count"] == 0:
        raise ValueError("surface graph OBJ export produced no non-degenerate triangles")

    vertices, faces = _deduplicated_indexed_faces(triangulation["triangles"])
    lines = [
        f"# {solid_name} surface_graph_obj_mesh",
        f"o {solid_name}_surface_graph",
    ]
    for vertex in vertices:
        lines.append("v " + " ".join(_obj_float(coordinate) for coordinate in vertex))

    face_index = 0
    for region in triangulation["triangle_regions"]:
        lines.append(f"g {region['surface_graph_id']}")
        for _ in range(region["triangle_count"]):
            face = faces[face_index]
            lines.append(f"f {face[0]} {face[1]} {face[2]}")
            face_index += 1

    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "source": "surface_graph",
        "view": view_id,
        "solid_name": solid_name,
        "export_exactness": "surface_graph_obj_mesh",
        "surface_count": len(triangulation["included_surface_ids"]),
        "included_surface_ids": triangulation["included_surface_ids"],
        "excluded_surface_ids": triangulation["excluded_surface_ids"],
        "skipped_triangle_count": triangulation["skipped_triangle_count"],
        "skipped_triangle_reasons": triangulation["skipped_triangle_reasons"],
        "vertex_count": len(vertices),
        "triangle_count": triangulation["triangle_count"],
        "face_count": len(faces),
        "triangle_regions": triangulation["triangle_regions"],
        "face_regions": triangulation["triangle_regions"],
        "transition_regions": build_transition_regions(surface_graph, triangulation["triangle_regions"]),
    }


def _obj_float(value: Any) -> str:
    return f"{float(value):.9g}"
