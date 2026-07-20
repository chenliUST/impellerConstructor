from __future__ import annotations

import math
from typing import Any

Point3 = tuple[float, float, float]
_EDGE_MATCH_TOLERANCE_MM = 1.0e-9


def build_v10_topology_graph(faces: list[dict[str, Any]]) -> dict[str, Any]:
    edge_records = _edge_records(faces)
    matched_pairs = []
    max_gap = 0.0
    endpoint_index: dict[tuple[int, int, int, int], list[int]] = {}
    candidate_pair_count = 0

    for second_index, second in enumerate(edge_records):
        candidate_indices: set[int] = set()
        for endpoint in (second["samples"][0], second["samples"][-1]):
            key = _endpoint_bin(endpoint)
            for x_offset in (-1, 0, 1):
                for y_offset in (-1, 0, 1):
                    for z_offset in (-1, 0, 1):
                        candidate_indices.update(
                            endpoint_index.get(
                                (
                                    len(second["samples"]),
                                    key[0] + x_offset,
                                    key[1] + y_offset,
                                    key[2] + z_offset,
                                ),
                                (),
                            )
                        )
        for first_index in sorted(candidate_indices):
            first = edge_records[first_index]
            if first["face_id"] == second["face_id"]:
                continue
            candidate_pair_count += 1
            match = _match_edges(first["samples"], second["samples"])
            if match is None:
                continue
            max_gap = max(max_gap, match["max_gap_mm"])
            matched_pairs.append((first_index, second_index, match))
        start_bin = _endpoint_bin(second["samples"][0])
        endpoint_index.setdefault(
            (len(second["samples"]), *start_bin), []
        ).append(second_index)

    shared_edges = []
    for first_index, second_index, match in sorted(matched_pairs):
        first = edge_records[first_index]
        second = edge_records[second_index]
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
        "edge_record_count": len(edge_records),
        "candidate_pair_count": candidate_pair_count,
        "exhaustive_pair_count": len(edge_records) * (len(edge_records) - 1) // 2,
        "matching_strategy": "endpoint_spatial_index_then_full_sample_gate",
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
    if forward_gap <= _EDGE_MATCH_TOLERANCE_MM:
        return {"orientation": "same", "max_gap_mm": forward_gap}
    if reverse_gap <= _EDGE_MATCH_TOLERANCE_MM:
        return {"orientation": "reversed", "max_gap_mm": reverse_gap}
    return None


def _endpoint_bin(point: Point3) -> tuple[int, int, int]:
    return tuple(
        math.floor(float(coordinate) / _EDGE_MATCH_TOLERANCE_MM)
        for coordinate in point
    )


def _max_gap(first: list[Point3], second: list[Point3]) -> float:
    return max(_distance(a, b) for a, b in zip(first, second))


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )
