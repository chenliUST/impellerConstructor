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


def test_chamfer_section_moves_along_retained_side_directions():
    section = build_chamfer_section(
        edge_point=(0.0, 0.0, 0.0),
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


@pytest.mark.parametrize(
    ("radius_mm", "first_direction", "second_direction"),
    [
        (0.0, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (1.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (1.0, (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
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


@pytest.mark.parametrize("distance_mm", [0.0, -1.0])
def test_chamfer_section_rejects_non_positive_distance(distance_mm):
    with pytest.raises(ValueError):
        build_chamfer_section(
            edge_point=(0.0, 0.0, 0.0),
            first_retained_direction=(1.0, 0.0, 0.0),
            second_retained_direction=(0.0, 1.0, 0.0),
            distance_mm=distance_mm,
        )
