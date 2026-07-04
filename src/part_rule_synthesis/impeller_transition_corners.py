from __future__ import annotations

from typing import Sequence


Point3 = tuple[float, float, float]


def _lerp(first: Point3, second: Point3, t: float) -> Point3:
    return (
        first[0] + (second[0] - first[0]) * t,
        first[1] + (second[1] - first[1]) * t,
        first[2] + (second[2] - first[2]) * t,
    )


def build_coons_corner_grid(
    *,
    west: Sequence[Point3],
    east: Sequence[Point3],
    south: Sequence[Point3],
    north: Sequence[Point3],
) -> list[list[Point3]]:
    if len(south) < 2 or len(west) < 2:
        raise ValueError("corner patch boundaries must contain at least two samples")
    u_count = len(south)
    v_count = len(west)
    if len(north) != u_count or len(east) != v_count:
        raise ValueError("corner patch boundary counts do not match")

    p00 = south[0]
    p10 = south[-1]
    p01 = north[0]
    p11 = north[-1]
    grid: list[list[Point3]] = []
    for u_index in range(u_count):
        u = u_index / (u_count - 1)
        row: list[Point3] = []
        for v_index in range(v_count):
            v = v_index / (v_count - 1)
            west_east = _lerp(west[v_index], east[v_index], u)
            south_north = _lerp(south[u_index], north[u_index], v)
            bilinear = (
                p00[0] * (1.0 - u) * (1.0 - v)
                + p10[0] * u * (1.0 - v)
                + p01[0] * (1.0 - u) * v
                + p11[0] * u * v,
                p00[1] * (1.0 - u) * (1.0 - v)
                + p10[1] * u * (1.0 - v)
                + p01[1] * (1.0 - u) * v
                + p11[1] * u * v,
                p00[2] * (1.0 - u) * (1.0 - v)
                + p10[2] * u * (1.0 - v)
                + p01[2] * (1.0 - u) * v
                + p11[2] * u * v,
            )
            row.append(
                (
                    west_east[0] + south_north[0] - bilinear[0],
                    west_east[1] + south_north[1] - bilinear[1],
                    west_east[2] + south_north[2] - bilinear[2],
                )
            )
        grid.append(row)
    return grid
