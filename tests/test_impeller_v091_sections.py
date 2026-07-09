from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_transition_sections import (
    build_chamfer_section,
    build_fillet_section,
)


def _subtract(first, second):
    return tuple(first[index] - second[index] for index in range(3))


def _cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _dot(first, second):
    return sum(first[index] * second[index] for index in range(3))


def _turn_sign(points, tangent):
    signed_turn = 0.0
    for before, point, after in zip(points, points[1:], points[2:]):
        incoming = _subtract(point, before)
        outgoing = _subtract(after, point)
        signed_turn += _dot(_cross(incoming, outgoing), tangent)
    assert not math.isclose(signed_turn, 0.0)
    return 1 if signed_turn > 0.0 else -1


def test_fillet_section_has_requested_radius_and_minimum_samples():
    section = build_fillet_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        radius_mm=4.0,
        sample_count=9,
        convexity_sign=1,
    )

    assert section["treatment"] == "fillet"
    assert len(section["points"]) >= 9
    assert section["quality"]["section_sample_count"] == len(section["points"])
    assert math.isclose(section["quality"]["included_angle_deg"], 90.0)
    assert section["quality"]["radius_max_error_mm"] <= 1.0e-6
    assert section["quality"]["convexity_sign"] == 1
    assert math.isclose(section["quality"]["trim_distance_mm"], 4.0)


def test_fillet_section_projects_retained_directions_perpendicular_to_tangent():
    section = build_fillet_section(
        edge_point=(1.0, 2.0, 3.0),
        tangent=(0.0, 0.0, 2.0),
        first_retained_direction=(1.0, 0.0, 10.0),
        second_retained_direction=(0.0, 1.0, -7.0),
        radius_mm=3.0,
        sample_count=3,
        convexity_sign=-1,
    )

    assert len(section["points"]) == 9
    assert section["points"][0] == (4.0, 2.0, 3.0)
    assert section["points"][-1] == (1.0, 5.0, 3.0)
    assert section["quality"]["radius_max_error_mm"] <= 1.0e-6
    assert section["quality"]["convexity_sign"] == -1


def test_fillet_convexity_sign_controls_section_orientation():
    negative_section = build_fillet_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        radius_mm=2.0,
        sample_count=9,
        convexity_sign=-1,
    )
    positive_section = build_fillet_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        radius_mm=2.0,
        sample_count=9,
        convexity_sign=1,
    )

    assert negative_section["points"] != positive_section["points"]
    assert _turn_sign(negative_section["points"], (0.0, 0.0, 1.0)) == -1
    assert _turn_sign(positive_section["points"], (0.0, 0.0, 1.0)) == 1
    assert negative_section["quality"]["convexity_sign"] == -1
    assert positive_section["quality"]["convexity_sign"] == 1


def test_chamfer_section_moves_along_retained_side_directions():
    section = build_chamfer_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        distance_mm=2.0,
    )

    assert section["treatment"] == "chamfer"
    assert section["points"][0] == (2.0, 0.0, 0.0)
    assert section["points"][-1] == (0.0, 2.0, 0.0)
    assert section["quality"]["section_sample_count"] == 2
    assert section["quality"]["direction_sign"] == 1
    assert math.isclose(section["quality"]["section_linearity_max_error_mm"], 0.0)
    assert math.isclose(section["quality"]["distance_mm"], 2.0)


def test_chamfer_section_projects_directions_and_signs_relative_to_tangent():
    positive_section = build_chamfer_section(
        edge_point=(1.0, 2.0, 3.0),
        tangent=(0.0, 0.0, 5.0),
        first_retained_direction=(1.0, 0.0, 10.0),
        second_retained_direction=(0.0, 1.0, -7.0),
        distance_mm=2.0,
    )
    negative_section = build_chamfer_section(
        edge_point=(1.0, 2.0, 3.0),
        tangent=(0.0, 0.0, -5.0),
        first_retained_direction=(1.0, 0.0, 10.0),
        second_retained_direction=(0.0, 1.0, -7.0),
        distance_mm=2.0,
    )

    assert positive_section["points"] == [(3.0, 2.0, 3.0), (1.0, 4.0, 3.0)]
    assert negative_section["points"] == [(3.0, 2.0, 3.0), (1.0, 4.0, 3.0)]
    assert positive_section["quality"]["direction_sign"] == 1
    assert negative_section["quality"]["direction_sign"] == -1


@pytest.mark.parametrize(
    ("radius_mm", "first_direction", "second_direction"),
    [
        (0.0, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (1.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (1.0, (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        (1.0, (0.0, 0.0, 3.0), (0.0, 1.0, 0.0)),
    ],
)
def test_fillet_section_rejects_invalid_inputs(radius_mm, first_direction, second_direction):
    with pytest.raises(ValueError):
        build_fillet_section(
            edge_point=(0.0, 0.0, 0.0),
            tangent=(0.0, 0.0, 1.0),
            first_retained_direction=first_direction,
            second_retained_direction=second_direction,
            radius_mm=radius_mm,
            sample_count=9,
            convexity_sign=1,
        )


def test_fillet_section_rejects_zero_tangent():
    with pytest.raises(ValueError):
        build_fillet_section(
            edge_point=(0.0, 0.0, 0.0),
            tangent=(0.0, 0.0, 0.0),
            first_retained_direction=(1.0, 0.0, 0.0),
            second_retained_direction=(0.0, 1.0, 0.0),
            radius_mm=1.0,
            sample_count=9,
            convexity_sign=1,
        )


@pytest.mark.parametrize("angle_deg", [0.5, 179.5])
def test_fillet_section_rejects_practically_degenerate_included_angles(angle_deg):
    angle_rad = math.radians(angle_deg)

    with pytest.raises(ValueError):
        build_fillet_section(
            edge_point=(0.0, 0.0, 0.0),
            tangent=(0.0, 0.0, 1.0),
            first_retained_direction=(1.0, 0.0, 0.0),
            second_retained_direction=(math.cos(angle_rad), math.sin(angle_rad), 0.0),
            radius_mm=1.0,
            sample_count=9,
            convexity_sign=1,
        )


@pytest.mark.parametrize("distance_mm", [0.0, -1.0])
def test_chamfer_section_rejects_non_positive_distance(distance_mm):
    with pytest.raises(ValueError):
        build_chamfer_section(
            edge_point=(0.0, 0.0, 0.0),
            tangent=(0.0, 0.0, 1.0),
            first_retained_direction=(1.0, 0.0, 0.0),
            second_retained_direction=(0.0, 1.0, 0.0),
            distance_mm=distance_mm,
        )


@pytest.mark.parametrize(
    ("tangent", "first_direction", "second_direction"),
    [
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, 1.0), (0.0, 0.0, 3.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (-2.0, 0.0, 0.0)),
    ],
)
def test_chamfer_section_rejects_degenerate_frame_inputs(
    tangent,
    first_direction,
    second_direction,
):
    with pytest.raises(ValueError):
        build_chamfer_section(
            edge_point=(0.0, 0.0, 0.0),
            tangent=tangent,
            first_retained_direction=first_direction,
            second_retained_direction=second_direction,
            distance_mm=1.0,
        )
