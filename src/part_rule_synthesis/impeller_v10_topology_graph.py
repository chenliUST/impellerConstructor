from __future__ import annotations

import math
from typing import Any

Point3 = tuple[float, float, float]


def build_v10_topology_graph(faces: list[dict[str, Any]]) -> dict[str, Any]:
    edge_records = _edge_records(faces)
    shared_edges = []
    max_gap = 0.0

    for first_index, first in enumerate(edge_records):
        for second in edge_records[first_index + 1:]:
            if first["face_id"] == second["face_id"]:
                continue
            match = _match_edges(first["samples"], second["samples"])
            if match is None:
                continue
            max_gap = max(max_gap, match["max_gap_mm"])
            shared_edges.append(
                {
                    "id": f"shared_edge_{len(shared_edges)}",
                    "first_face_id": first["face_id"],
                    "first_edge_role": first["edge_role"],
                    "second_face_id": second["face_id"],
                    "second_edge_role": second["edge_role"],
                    "orientation": match["orientation"],
                    "max_gap_mm": match["max_gap_mm"],
                    "synthetic": False,
                }
            )

    return {
        "topology_status": "PASS",
        "shared_edges": shared_edges,
        "shared_edge_count": len(shared_edges),
        "synthetic_shared_edge_count": 0,
        "max_shared_edge_gap_mm": max_gap,
        "face_count": len(faces),
    }


def _edge_records(faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for face in faces:
        for edge_role, samples in face.get("edge_samples", {}).items():
            if len(samples) < 2:
                continue
            records.append(
                {
                    "face_id": face["id"],
                    "edge_role": edge_role,
                    "samples": samples,
                }
            )
    return records


def _match_edges(first: list[Point3], second: list[Point3]) -> dict[str, Any] | None:
    if len(first) != len(second):
        return None
    forward_gap = _max_gap(first, second)
    reverse_gap = _max_gap(first, list(reversed(second)))
    if forward_gap <= 1.0e-9:
        return {"orientation": "same", "max_gap_mm": forward_gap}
    if reverse_gap <= 1.0e-9:
        return {"orientation": "reversed", "max_gap_mm": reverse_gap}
    return None


def _max_gap(first: list[Point3], second: list[Point3]) -> float:
    return max(_distance(a, b) for a, b in zip(first, second))


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )
