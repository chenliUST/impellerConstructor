from __future__ import annotations

from typing import Any


def knot_values_and_multiplicities(knots: list[float]) -> tuple[list[float], list[int]]:
    values: list[float] = []
    multiplicities: list[int] = []

    for knot in knots:
        value = _float_value(knot)
        if values and value == values[-1]:
            multiplicities[-1] += 1
            continue
        values.append(value)
        multiplicities.append(1)

    return values, multiplicities


def clamped_open_uniform_knots(point_count: int, degree: int) -> list[float]:
    if point_count < 2:
        raise ValueError("point_count must be at least 2")
    if degree < 1:
        raise ValueError("degree must be at least 1")
    if degree >= point_count:
        raise ValueError("degree must be less than point_count")

    interior_count = point_count - degree - 1
    interiors = [
        _float_value(index / (interior_count + 1))
        for index in range(1, interior_count + 1)
    ]
    return [0.0] * (degree + 1) + interiors + [1.0] * (degree + 1)


def bspline_surface_payload_from_control_net(surface: dict[str, Any]) -> dict[str, Any]:
    control_net = surface.get("control_net")
    if not _is_rectangular_control_net(control_net):
        raise ValueError("surface control_net must be a rectangular grid")

    control_points = [
        [_point3(point) for point in row]
        for row in control_net
    ]
    degree_u = int(surface.get("degree_u", 3))
    degree_v = int(surface.get("degree_v", 3))
    knots_u = clamped_open_uniform_knots(len(control_points), degree_u)
    knots_v = clamped_open_uniform_knots(len(control_points[0]), degree_v)
    knot_values_u, knot_multiplicities_u = knot_values_and_multiplicities(knots_u)
    knot_values_v, knot_multiplicities_v = knot_values_and_multiplicities(knots_v)

    return {
        "surface_type": "bspline_surface",
        "id": surface.get("id"),
        "role": surface.get("role"),
        "feature_id": surface.get("feature_id"),
        "degree_u": degree_u,
        "degree_v": degree_v,
        "control_points": control_points,
        "weights": [
            [1.0 for _point in row]
            for row in control_points
        ],
        "knots_u": knots_u,
        "knots_v": knots_v,
        "knot_values_u": knot_values_u,
        "knot_multiplicities_u": knot_multiplicities_u,
        "knot_values_v": knot_values_v,
        "knot_multiplicities_v": knot_multiplicities_v,
        "trim_loops": surface.get("trim_loops", [{"orientation": "outer", "edges": []}]),
        "source": "surface_graph.control_net",
    }


def plane_surface_payload(origin: list[float], normal: list[float], u_dir: list[float], v_dir: list[float]) -> dict[str, Any]:
    return {
        "surface_type": "plane",
        "origin": [round(float(value), 6) for value in origin],
        "normal": [round(float(value), 6) for value in normal],
        "u_dir": [round(float(value), 6) for value in u_dir],
        "v_dir": [round(float(value), 6) for value in v_dir],
        "trim_loops": [{"orientation": "outer", "edges": []}],
    }


def cylinder_surface_payload(radius: float, z_min: float, z_max: float) -> dict[str, Any]:
    return {
        "surface_type": "cylinder",
        "radius_mm": round(float(radius), 6),
        "z_min_mm": round(float(z_min), 6),
        "z_max_mm": round(float(z_max), 6),
        "axis": "z",
        "trim_loops": [{"orientation": "outer", "edges": []}],
    }


def boundary_edge_payload(
    edge_id: str,
    points: list[list[float]],
    surface_uv: dict[str, list[list[float]]] | None = None,
) -> dict[str, Any]:
    degree = min(3, len(points) - 1)
    control_points = [_point3(point) for point in points]
    knots = clamped_open_uniform_knots(len(control_points), degree)
    knot_values, knot_multiplicities = knot_values_and_multiplicities(knots)
    cad_edge: dict[str, Any] = {
        "curve_type": "bspline_curve",
        "degree": degree,
        "control_points": control_points,
        "weights": [1.0 for _point in control_points],
        "knots": knots,
        "knot_values": knot_values,
        "knot_multiplicities": knot_multiplicities,
        "source": "surface_graph.control_net",
    }

    if surface_uv:
        cad_edge["surface_uv"] = {
            surface_id: _pcurve_payload(uv_points)
            for surface_id, uv_points in surface_uv.items()
        }

    return {
        "id": edge_id,
        "cad_edge": cad_edge,
    }


def _pcurve_payload(points: list[list[float]]) -> dict[str, Any]:
    degree = min(3, len(points) - 1)
    control_points = [_point2(point) for point in points]
    knots = clamped_open_uniform_knots(len(control_points), degree)
    knot_values, knot_multiplicities = knot_values_and_multiplicities(knots)
    return {
        "curve_type": "bspline_pcurve",
        "degree": degree,
        "control_points": control_points,
        "weights": [1.0 for _point in control_points],
        "knots": knots,
        "knot_values": knot_values,
        "knot_multiplicities": knot_multiplicities,
    }


def _is_rectangular_control_net(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 2:
        return False
    if not isinstance(value[0], list) or len(value[0]) < 2:
        return False
    row_length = len(value[0])
    return all(isinstance(row, list) and len(row) == row_length for row in value)


def _point3(value: Any) -> list[float]:
    if len(value) != 3:
        raise ValueError("3D control points must have exactly three coordinates")
    return [_float_value(coordinate) for coordinate in value]


def _point2(value: Any) -> list[float]:
    if len(value) != 2:
        raise ValueError("surface UV control points must have exactly two coordinates")
    return [_float_value(coordinate) for coordinate in value]


def _float_value(value: Any) -> float:
    rounded = round(float(value), 6)
    if rounded == 0.0:
        return 0.0
    return rounded
