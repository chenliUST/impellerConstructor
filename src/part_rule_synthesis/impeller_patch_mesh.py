from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


V091_SHARED_NODE_PATCH_MESH_CAPABILITY = "implemented"

Point3 = tuple[float, float, float]
EdgeKey = tuple[str, str]


def build_patch_mesh(surface_graph: dict[str, Any], view_id: str = "cad_review_360") -> dict[str, Any]:
    patch_complex = surface_graph.get("transition_patch_complex")
    if not isinstance(patch_complex, Mapping):
        raise ValueError("V0.91 patch mesh requires transition_patch_complex")

    vertices = _vertices_from_complex(patch_complex)
    declared_open_edges = _declared_open_edges(patch_complex.get("declared_open_boundary_ids", []))
    triangles: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    included_surface_ids: list[str] = []

    for patch_id, patch in _iter_patches(patch_complex):
        surface_id = str(patch.get("surface_graph_id") or patch_id)
        node_grid = patch.get("node_grid")
        if not _has_rectangular_node_grid(node_grid):
            skipped.append(
                {
                    "surface_graph_id": surface_id,
                    "patch_id": patch_id,
                    "reason": "invalid_node_grid",
                }
            )
            continue

        start = len(triangles)
        row_count = len(node_grid)
        column_count = len(node_grid[0])
        for row_index in range(row_count - 1):
            for column_index in range(column_count - 1):
                a = str(node_grid[row_index][column_index])
                b = str(node_grid[row_index + 1][column_index])
                c = str(node_grid[row_index + 1][column_index + 1])
                d = str(node_grid[row_index][column_index + 1])
                for vertex_ids in ((a, b, d), (b, c, d)):
                    triangle = _triangle_from_vertex_ids(
                        vertex_ids,
                        vertices,
                        surface_graph_id=surface_id,
                        patch_id=patch_id,
                        role=str(patch.get("role", "")),
                    )
                    if triangle is None:
                        skipped.append(
                            {
                                "surface_graph_id": surface_id,
                                "patch_id": patch_id,
                                "u_index": row_index,
                                "v_index": column_index,
                                "reason": "degenerate_triangle",
                            }
                        )
                        continue
                    triangles.append(triangle)

        count = len(triangles) - start
        if count <= 0:
            continue
        included_surface_ids.append(surface_id)
        regions.append(
            {
                "surface_graph_id": surface_id,
                "patch_id": patch_id,
                "role": str(patch.get("role", "")),
                "triangle_start": start,
                "triangle_count": count,
                "edge_family": str(patch.get("edge_family", "")),
                "transition_policy_id": str(patch.get("transition_policy_id", "")),
                "treatment": str(patch.get("treatment", "")),
            }
        )

    source_patch_incidence_report = edge_incidence_report(
        triangles,
        declared_open_boundary_ids=patch_complex.get("declared_open_boundary_ids", []),
    )
    source_triangle_count = len(triangles)
    source_vertex_count = len(vertices)
    stitch_regions = _add_closed_boundary_stitches(
        triangles,
        vertices,
        declared_open_edges,
        start_region_index=len(regions),
    )
    regions.extend(stitch_regions)

    final_incidence_report = edge_incidence_report(
        triangles,
        declared_open_boundary_ids=patch_complex.get("declared_open_boundary_ids", []),
    )
    zero_area_count = sum(1 for triangle in triangles if _is_zero_area_triangle(triangle["points"]))
    source_patch_incidence_report = {
        **source_patch_incidence_report,
        "report_scope": "source_transition_patch_complex_before_synthetic_closure",
        "vertex_count": source_vertex_count,
        "face_count": source_triangle_count,
        "zero_area_face_count": sum(
            1 for triangle in triangles[:source_triangle_count] if _is_zero_area_triangle(triangle["points"])
        ),
    }
    mesh_closure_report = _mesh_closure_report(
        source_patch_incidence_report=source_patch_incidence_report,
        stitch_regions=stitch_regions,
        final_triangle_count=len(triangles),
        source_triangle_count=source_triangle_count,
    )
    report = {
        **final_incidence_report,
        "report_scope": "final_mesh_after_synthetic_closure",
        "vertex_count": len(vertices),
        "face_count": len(triangles),
        "zero_area_face_count": zero_area_count,
        "source_patch_free_edge_count": source_patch_incidence_report["free_edge_count"],
        "synthetic_closure_triangle_count": mesh_closure_report["synthetic_closure_triangle_count"],
        "closure_policy": mesh_closure_report["closure_policy"],
    }
    skipped_reasons = Counter(item["reason"] for item in skipped)
    return {
        "mesh_type": "shared_node_transition_patch_mesh",
        "source": "topology_first_transition_patch_complex",
        "view": view_id,
        "vertices": {node_id: list(point) for node_id, point in vertices.items()},
        "triangles": triangles,
        "triangle_count": len(triangles),
        "triangle_regions": regions,
        "transition_regions": _transition_regions(regions),
        "mesh_closure_regions": stitch_regions,
        "source_patch_incidence_report": source_patch_incidence_report,
        "final_mesh_incidence_report": final_incidence_report,
        "mesh_closure_report": mesh_closure_report,
        "mesh_manifoldness_report": report,
        "included_surface_ids": included_surface_ids,
        "excluded_surface_ids": [],
        "skipped_triangle_count": len(skipped),
        "skipped_triangle_reasons": dict(sorted(skipped_reasons.items())),
        "skipped_triangles": skipped,
    }


def edge_incidence_report(
    triangles: list[dict[str, Any]],
    declared_open_boundary_ids: Iterable[Any],
) -> dict[str, Any]:
    declared_open_edges = _declared_open_edges(declared_open_boundary_ids)
    edge_counts: Counter[EdgeKey] = Counter()
    duplicate_faces: Counter[tuple[str, str, str]] = Counter()
    zero_area_face_count = 0
    for triangle in triangles:
        ids = [str(vertex_id) for vertex_id in triangle.get("vertex_ids", [])]
        if len(ids) != 3:
            continue
        if len(set(ids)) < 3:
            zero_area_face_count += 1
        duplicate_faces[tuple(sorted(ids))] += 1
        for edge in _triangle_edges(ids):
            edge_counts[edge] += 1

    all_free_edges = [edge for edge, count in sorted(edge_counts.items()) if count == 1]
    declared_free_edges = [edge for edge in all_free_edges if edge in declared_open_edges]
    undeclared_free_edges = [edge for edge in all_free_edges if edge not in declared_open_edges]
    nonmanifold_edges = [edge for edge, count in sorted(edge_counts.items()) if count > 2]
    return {
        "declared_open_boundary_ids": [_edge_id(edge) for edge in sorted(declared_open_edges)],
        "edge_count": len(edge_counts),
        "free_edge_count": len(undeclared_free_edges),
        "declared_open_edge_count": len(declared_free_edges),
        "nonmanifold_edge_count": len(nonmanifold_edges),
        "duplicate_face_count": sum(count - 1 for count in duplicate_faces.values() if count > 1),
        "zero_area_face_count": zero_area_face_count,
        "free_edges": [_edge_list(edge) for edge in undeclared_free_edges[:50]],
        "undeclared_free_edges": [_edge_list(edge) for edge in undeclared_free_edges[:50]],
        "declared_open_edges": [_edge_list(edge) for edge in declared_free_edges[:50]],
        "nonmanifold_edges": [_edge_list(edge) for edge in nonmanifold_edges[:50]],
    }


def _vertices_from_complex(patch_complex: Mapping[str, Any]) -> dict[str, Point3]:
    vertices = {}
    nodes = patch_complex.get("nodes", {})
    if not isinstance(nodes, Mapping):
        raise ValueError("transition_patch_complex.nodes must be keyed by shared node id")
    for node_id, node in nodes.items():
        if not isinstance(node, Mapping) or "point" not in node:
            raise ValueError(f"transition patch node {node_id} is missing point coordinates")
        vertices[str(node_id)] = _point(node["point"])
    return vertices


def _iter_patches(patch_complex: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    patches = patch_complex.get("patches", {})
    if isinstance(patches, Mapping):
        for patch_id, patch in patches.items():
            if isinstance(patch, Mapping):
                yield str(patch_id), patch
        return
    if isinstance(patches, list):
        for index, patch in enumerate(patches):
            if not isinstance(patch, Mapping):
                continue
            yield str(patch.get("patch_id") or f"patch_{index}"), patch


def _has_rectangular_node_grid(node_grid: Any) -> bool:
    if not isinstance(node_grid, list) or len(node_grid) < 2:
        return False
    if not isinstance(node_grid[0], list) or len(node_grid[0]) < 2:
        return False
    column_count = len(node_grid[0])
    return all(isinstance(row, list) and len(row) == column_count for row in node_grid)


def _triangle_from_vertex_ids(
    vertex_ids: tuple[str, str, str],
    vertices: Mapping[str, Point3],
    *,
    surface_graph_id: str,
    patch_id: str,
    role: str,
) -> dict[str, Any] | None:
    try:
        points = [vertices[vertex_id] for vertex_id in vertex_ids]
    except KeyError as exc:
        raise ValueError(f"patch {patch_id} references missing shared node {exc.args[0]}") from exc
    normal = _triangle_normal(points[0], points[1], points[2])
    if normal is None:
        return None
    return {
        "vertex_ids": list(vertex_ids),
        "points": [list(point) for point in points],
        "normal": list(normal),
        "surface_graph_id": surface_graph_id,
        "patch_id": patch_id,
        "role": role,
    }


def _add_closed_boundary_stitches(
    triangles: list[dict[str, Any]],
    vertices: dict[str, Point3],
    declared_open_edges: set[EdgeKey],
    *,
    start_region_index: int,
) -> list[dict[str, Any]]:
    edge_counts = _edge_counts(triangles)
    free_edges = [
        edge
        for edge, count in edge_counts.items()
        if count == 1 and edge not in declared_open_edges
    ]
    oriented_edges = _oriented_edge_lookup(triangles, free_edges)
    loops = _free_edge_loops(free_edges)
    regions = []
    for loop_index, loop in enumerate(loops):
        if len(loop) < 3:
            continue
        loop_edges = {_edge_key(loop[index], loop[(index + 1) % len(loop)]) for index in range(len(loop))}
        if not loop_edges <= set(free_edges):
            continue
        centroid = _centroid(vertices[node_id] for node_id in loop)
        center_id = f"v091.boundary_stitch.{start_region_index + loop_index:04d}.center"
        vertices[center_id] = centroid
        start = len(triangles)
        surface_id = f"v091_boundary_stitch_{start_region_index + loop_index:04d}"
        for index, first in enumerate(loop):
            second = loop[(index + 1) % len(loop)]
            original_edge = _edge_key(first, second)
            existing = oriented_edges.get(original_edge)
            if existing is None:
                continue
            first_id, second_id = existing[1], existing[0]
            triangle = _triangle_from_vertex_ids(
                (first_id, second_id, center_id),
                vertices,
                surface_graph_id=surface_id,
                patch_id=surface_id,
                role="mesh_boundary_stitch",
            )
            if triangle is not None:
                triangles.append(triangle)
        count = len(triangles) - start
        if count > 0:
            regions.append(
                {
                    "surface_graph_id": surface_id,
                    "patch_id": surface_id,
                    "role": "mesh_boundary_stitch",
                    "triangle_start": start,
                    "triangle_count": count,
                    "edge_family": "mesh_boundary_stitch",
                    "transition_policy_id": "v091.shared_node_patch_mesh",
                    "treatment": "stitched_boundary",
                }
            )
    return regions


def _free_edge_loops(free_edges: list[EdgeKey]) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for first, second in free_edges:
        adjacency[first].append(second)
        adjacency[second].append(first)

    loops: list[list[str]] = []
    unused = set(free_edges)
    while unused:
        first, second = min(unused)
        unused.remove((first, second))
        ordered = [first, second]
        previous = first
        current = second
        while True:
            if current == ordered[0]:
                loops.append(ordered[:-1])
                break
            candidates = [
                vertex
                for vertex in sorted(adjacency[current])
                if _edge_key(current, vertex) in unused and vertex != previous
            ]
            if not candidates:
                break
            next_vertex = candidates[0]
            unused.remove(_edge_key(current, next_vertex))
            if next_vertex in ordered and next_vertex != ordered[0]:
                break
            ordered.append(next_vertex)
            previous, current = current, next_vertex
    return loops


def _oriented_edge_lookup(
    triangles: list[dict[str, Any]],
    target_edges: list[EdgeKey],
) -> dict[EdgeKey, tuple[str, str]]:
    targets = set(target_edges)
    oriented = {}
    for triangle in triangles:
        ids = [str(vertex_id) for vertex_id in triangle.get("vertex_ids", [])]
        for first, second in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edge = _edge_key(first, second)
            if edge in targets and edge not in oriented:
                oriented[edge] = (first, second)
    return oriented


def _transition_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "surface_graph_id": region["surface_graph_id"],
            "patch_id": region.get("patch_id", ""),
            "role": region.get("role", ""),
            "triangle_start": region["triangle_start"],
            "triangle_count": region["triangle_count"],
            "edge_family": region.get("edge_family", ""),
            "transition_policy_id": region.get("transition_policy_id", ""),
            "treatment": region.get("treatment", ""),
        }
        for region in regions
        if region.get("edge_family") or "transition" in str(region.get("role", "")) or "corner" in str(region.get("role", ""))
    ]


def _mesh_closure_report(
    *,
    source_patch_incidence_report: dict[str, Any],
    stitch_regions: list[dict[str, Any]],
    final_triangle_count: int,
    source_triangle_count: int,
) -> dict[str, Any]:
    synthetic_triangle_count = final_triangle_count - source_triangle_count
    return {
        "closure_policy": "synthetic_review_fan_caps_for_undeclared_free_edge_loops",
        "review_grade_closure": True,
        "source_patch_free_edge_count": source_patch_incidence_report["free_edge_count"],
        "synthetic_closure_region_count": len(stitch_regions),
        "synthetic_closure_triangle_count": synthetic_triangle_count,
        "synthetic_closure_surface_ids": [region["surface_graph_id"] for region in stitch_regions],
        "limitations": [
            "synthetic closure triangles are mesh review caps, not original surface_graph patches",
            "source_patch_incidence_report records pre-closure free edges for validation review",
        ],
    }


def _edge_counts(triangles: list[dict[str, Any]]) -> Counter[EdgeKey]:
    counts: Counter[EdgeKey] = Counter()
    for triangle in triangles:
        ids = [str(vertex_id) for vertex_id in triangle.get("vertex_ids", [])]
        if len(ids) == 3:
            counts.update(_triangle_edges(ids))
    return counts


def _triangle_edges(vertex_ids: list[str]) -> list[EdgeKey]:
    return [
        _edge_key(vertex_ids[0], vertex_ids[1]),
        _edge_key(vertex_ids[1], vertex_ids[2]),
        _edge_key(vertex_ids[2], vertex_ids[0]),
    ]


def _declared_open_edges(declared_open_boundary_ids: Iterable[Any]) -> set[EdgeKey]:
    declared = set()
    for value in declared_open_boundary_ids:
        edge = _coerce_edge(value)
        if edge is not None:
            declared.add(edge)
    return declared


def _coerce_edge(value: Any) -> EdgeKey | None:
    if isinstance(value, str):
        for separator in ("|", "--", ":", "/"):
            if separator in value:
                first, second = value.split(separator, 1)
                return _edge_key(first, second)
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _edge_key(str(value[0]), str(value[1]))
    if isinstance(value, Mapping):
        node_ids = value.get("node_ids") or value.get("vertex_ids")
        if isinstance(node_ids, (list, tuple)) and len(node_ids) == 2:
            return _edge_key(str(node_ids[0]), str(node_ids[1]))
    return None


def _edge_key(first: str, second: str) -> EdgeKey:
    return tuple(sorted((str(first), str(second))))  # type: ignore[return-value]


def _edge_id(edge: EdgeKey) -> str:
    return f"{edge[0]}|{edge[1]}"


def _edge_list(edge: EdgeKey) -> list[str]:
    return [edge[0], edge[1]]


def _point(value: Any) -> Point3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _centroid(points: Iterable[Point3]) -> Point3:
    total = [0.0, 0.0, 0.0]
    count = 0
    for point in points:
        total[0] += point[0]
        total[1] += point[1]
        total[2] += point[2]
        count += 1
    if count == 0:
        raise ValueError("cannot compute centroid of empty point set")
    return (total[0] / count, total[1] / count, total[2] / count)


def _triangle_normal(first: Point3, second: Point3, third: Point3) -> Point3 | None:
    ux, uy, uz = second[0] - first[0], second[1] - first[1], second[2] - first[2]
    vx, vy, vz = third[0] - first[0], third[1] - first[1], third[2] - first[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 1.0e-9:
        return None
    return (nx / length, ny / length, nz / length)


def _is_zero_area_triangle(points: list[list[float]]) -> bool:
    first, second, third = (_point(point) for point in points)
    return _triangle_normal(first, second, third) is None
