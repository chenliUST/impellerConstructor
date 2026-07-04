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
    triangulation = _mesh_for_surface_graph(surface_graph, view_id)
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
    source = triangulation.get("source", "surface_graph")
    transition_regions = triangulation.get("transition_regions")
    if transition_regions is None:
        transition_regions = build_transition_regions(surface_graph, triangulation["triangle_regions"])
    return {
        "source": source,
        "view": view_id,
        "solid_name": solid_name,
        **({"mesh_type": triangulation["mesh_type"]} if "mesh_type" in triangulation else {}),
        **(
            {"mesh_manifoldness_report": triangulation["mesh_manifoldness_report"]}
            if "mesh_manifoldness_report" in triangulation
            else {}
        ),
        **(
            {
                "source_patch_incidence_report": triangulation["source_patch_incidence_report"],
                "final_mesh_incidence_report": triangulation["final_mesh_incidence_report"],
                "mesh_closure_report": triangulation["mesh_closure_report"],
                "mesh_closure_regions": triangulation.get("mesh_closure_regions", []),
            }
            if "source_patch_incidence_report" in triangulation
            else {}
        ),
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
        "transition_regions": transition_regions,
    }


def _mesh_for_surface_graph(surface_graph: dict[str, Any], view_id: str) -> dict[str, Any]:
    if surface_graph.get("transition_geometry_status") == "topology_first_validated_transition_graph":
        from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh

        return build_patch_mesh(surface_graph, view_id=view_id)
    if surface_graph.get("transition_geometry_status") == "resolved_trimmed_surface_graph":
        from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh

        return build_transition_aware_mesh(surface_graph, view_id=view_id)
    return triangulate_surface_graph(surface_graph, view_id=view_id)


def _obj_float(value: Any) -> str:
    return f"{float(value):.9g}"
