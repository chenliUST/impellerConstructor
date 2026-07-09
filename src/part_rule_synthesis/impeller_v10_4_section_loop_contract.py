from __future__ import annotations

import copy
import math
from typing import Any


SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]


def measure_section_loop_contract(loop: dict[str, Any]) -> dict[str, Any]:
    if loop.get("segment_order") != SEGMENT_ORDER:
        return _fail("v1_0_4_section_loop_order_invalid")
    segments = loop.get("segments")
    if not isinstance(segments, dict):
        return _fail("v1_0_4_section_loop_segments_missing")

    segment_points: list[list[list[float]]] = []
    for name in SEGMENT_ORDER:
        points = _points(segments.get(name, {}).get("points"))
        if len(points) < 2:
            return _fail("v1_0_4_section_loop_segment_too_short")
        segment_points.append(points)

    stitched = _stitch(segment_points)
    closure_gap = _distance(stitched[0], stitched[-1])
    signed_area = _signed_area_xy(stitched)
    tangent_angle = _max_join_tangent_angle(segment_points)
    curvature_mismatch = _max_curvature_proxy_mismatch(segment_points)
    status = (
        "PASS"
        if closure_gap <= 1.0e-6
        and signed_area > 0.0
        and tangent_angle <= 2.0
        and curvature_mismatch <= 0.25
        else "FAIL"
    )
    reason = None if status == "PASS" else "v1_0_4_section_loop_g2_measurement_failed"
    return {
        "status": status,
        "reason": reason,
        "segment_order": copy.deepcopy(SEGMENT_ORDER),
        "max_closure_gap_mm": round(closure_gap, 9),
        "signed_area_mm2": round(signed_area, 9),
        "orientation": "ccw_material_outward" if signed_area > 0.0 else "invalid_or_reversed",
        "max_join_tangent_angle_deg": round(tangent_angle, 9),
        "max_join_curvature_proxy_mismatch": round(curvature_mismatch, 9),
        "closed_loop_point_count": len(stitched),
    }


def attach_section_loop_contracts(lattice: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(lattice)
    for blade in clone.get("blades", []):
        for loop in blade.get("section_loops", []):
            loop["segment_order"] = copy.deepcopy(SEGMENT_ORDER)
            loop["v1_0_4_section_loop_quality"] = measure_section_loop_contract(loop)
    return clone


def _fail(reason: str) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason}


def _points(raw: Any) -> list[list[float]]:
    if not isinstance(raw, list):
        return []
    points = []
    for point in raw:
        if isinstance(point, list) and len(point) == 3:
            points.append([float(point[0]), float(point[1]), float(point[2])])
    return points


def _stitch(segments: list[list[list[float]]]) -> list[list[float]]:
    stitched: list[list[float]] = []
    for index, segment in enumerate(segments):
        stitched.extend(segment if index == 0 else segment[1:])
    if stitched and _distance(stitched[0], stitched[-1]) > 0.0:
        stitched.append(stitched[0][:])
    return stitched


def _distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _signed_area_xy(points: list[list[float]]) -> float:
    area = 0.0
    for left, right in zip(points, points[1:]):
        area += left[0] * right[1] - right[0] * left[1]
    return 0.5 * area


def _unit(vector: list[float]) -> list[float]:
    length = max(sum(value * value for value in vector) ** 0.5, 1.0e-12)
    return [value / length for value in vector]


def _angle_deg(left: list[float], right: list[float]) -> float:
    a = _unit(left)
    b = _unit(right)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def _max_join_tangent_angle(segments: list[list[list[float]]]) -> float:
    angles = []
    for index, current in enumerate(segments):
        nxt = segments[(index + 1) % len(segments)]
        current_tangent = [current[-1][axis] - current[-2][axis] for axis in range(3)]
        next_tangent = [nxt[1][axis] - nxt[0][axis] for axis in range(3)]
        angles.append(_angle_deg(current_tangent, next_tangent))
    return max(angles) if angles else 180.0


def _curvature_proxy(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    mid = points[len(points) // 2]
    chord_mid = [(points[0][axis] + points[-1][axis]) * 0.5 for axis in range(3)]
    return _distance(mid, chord_mid)


def _max_curvature_proxy_mismatch(segments: list[list[list[float]]]) -> float:
    mismatches = []
    for index, current in enumerate(segments):
        nxt = segments[(index + 1) % len(segments)]
        scale = max(_polyline_length(current) + _polyline_length(nxt), 1.0)
        mismatches.append(abs(_curvature_proxy(current) - _curvature_proxy(nxt)) / scale)
    return max(mismatches) if mismatches else 1.0


def _polyline_length(points: list[list[float]]) -> float:
    return sum(_distance(left, right) for left, right in zip(points, points[1:]))
