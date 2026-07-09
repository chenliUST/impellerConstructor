from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice
from part_rule_synthesis.impeller_v10_3_tip_dome import build_v10_3_tip_dome


SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]


def _defaults() -> dict:
    return {
        "main_blade_count": 2,
        "splitter_blade_count": 2,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 17,
        "face_streamwise_sample_count": 5,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
        "tip_dome_height_mm": 24.0,
        "tip_dome_short_direction_sample_count": 17,
    }


def _lattice() -> dict:
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    assert lattice["status"] == "PASS"
    return lattice


def _stitched_tip_loop(lattice: dict, blade_index: int = 0) -> list[list[float]]:
    tip_loop = lattice["blades"][blade_index]["section_loops"][-1]
    stitched = []
    for segment_name in SEGMENT_ORDER:
        points = tip_loop["segments"][segment_name]["points"]
        stitched.extend(points[1:] if stitched and stitched[-1] == points[0] else points)
    if stitched[0] != stitched[-1]:
        stitched.append(stitched[0])
    return stitched


def _synthetic_tip_lattice(loop: list[list[float]]) -> dict:
    segment_lengths = [3, 3, 3, len(loop) - 6]
    cursor = 0
    segments = {}
    for segment_name, segment_length in zip(SEGMENT_ORDER, segment_lengths):
        segments[segment_name] = {
            "points": copy.deepcopy(loop[cursor : cursor + segment_length]),
            "sample_count": segment_length,
        }
        cursor += segment_length - 1
    return {
        "status": "PASS",
        "blades": [
            {
                "blade_class": "main",
                "blade_pair_index": 0,
                "section_loop_family_id": "synthetic_tip_loop_family",
                "section_loops": [
                    {
                        "blade_class": "main",
                        "blade_pair_index": 0,
                        "section_index": 0,
                        "closed_loop_points": copy.deepcopy(loop),
                        "coordinate_frame": {
                            "material_normal": [0.0, 0.0, 1.0],
                            "span_tangent": [0.0, 0.0, 1.0],
                        },
                        "segments": segments,
                    }
                ],
            }
        ],
    }


def _subtract(left: list[float], right: list[float]) -> list[float]:
    return [float(left[index]) - float(right[index]) for index in range(3)]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(first, second)))


def test_open_tip_dome_boundary_uses_tip_section_loop():
    lattice = _lattice()
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=_defaults())
    expected_boundary = _stitched_tip_loop(lattice)

    assert dome["status"] == "PASS"
    assert dome["id"] == "blade_0_tip_dome_surface"
    assert dome["kind"] == "native_topology_face"
    assert dome["face_family"] == "blade_tip"
    assert dome["role"] == "open_tip_dome"
    assert dome["edge_samples"]["tip_section_loop"] == expected_boundary
    assert dome["uv_grid"][0] == expected_boundary
    assert expected_boundary == lattice["blades"][0]["section_loops"][-1]["closed_loop_points"]
    assert dome["tip_dome_quality"]["tip_dome_boundary_gap_mm"] <= 1.0e-6


def test_open_tip_dome_is_material_side_and_not_folded():
    lattice = _lattice()
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=_defaults())
    normal = lattice["blades"][0]["section_loops"][-1]["coordinate_frame"]["material_normal"]

    assert dome["tip_dome_quality"]["tip_dome_material_side_valid"] is True
    assert dome["tip_dome_quality"]["min_signed_dome_height_mm"] > 0.0
    assert dome["tip_dome_quality"]["tip_dome_foldover_count"] == 0
    assert dome["tip_dome_quality"]["foldover_count"] == 0
    assert dome["transition_quality"]["foldover_count"] == 0
    assert all(
        _dot(_subtract(point, boundary), normal) > 0.0
        for row in dome["uv_grid"][1:]
        for point, boundary in zip(row, dome["uv_grid"][0])
    )


def test_open_tip_dome_has_curved_grid_and_interior_crest_bulge():
    lattice = _lattice()
    defaults = _defaults()
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=defaults)
    uv_grid = dome["uv_grid"]
    normal = lattice["blades"][0]["section_loops"][-1]["coordinate_frame"]["material_normal"]
    mid_row = uv_grid[len(uv_grid) // 2]
    crest = dome["edge_samples"]["tip_crest_curve"]
    mid_index = len(uv_grid) // 2
    linear_fraction = mid_index / (len(uv_grid) - 1)

    assert len(uv_grid) == defaults["tip_dome_short_direction_sample_count"]
    assert crest == uv_grid[-1]
    assert crest != uv_grid[0]
    assert dome["tip_dome_quality"]["requested_tip_dome_height_mm"] == defaults["tip_dome_height_mm"]
    assert dome["tip_dome_quality"]["height_to_average_thickness_ratio"] == pytest.approx(0.75)
    for column_index, boundary_point in enumerate(uv_grid[0]):
        signed_mid_height = _dot(_subtract(mid_row[column_index], boundary_point), normal)
        signed_crest_height = _dot(_subtract(crest[column_index], boundary_point), normal)
        assert signed_crest_height == pytest.approx(defaults["tip_dome_height_mm"], abs=1.0e-6)
        assert signed_mid_height > linear_fraction * signed_crest_height


def test_open_tip_dome_mesh_wire_display_payload_is_compact():
    dome = build_v10_3_tip_dome(blade_index=3, lattice=_lattice(), defaults=_defaults())

    assert dome["wireframe"] == {"enabled": True, "source": "uv_grid"}
    assert dome["display"]["inspection_class"] == "open_tip_dome"
    assert dome["display"]["visible_by_default"] is True
    assert "color" in dome["display"]
    assert "wire_color" in dome["display"]
    assert dome["mesh"]["strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
    assert dome["mesh"]["quad_count"] == (len(dome["uv_grid"]) - 1) * (len(dome["uv_grid"][0]) - 1)
    assert all(set(quad) == {"indices"} for quad in dome["mesh"]["quads"])
    assert all("vertices" not in quad for quad in dome["mesh"]["quads"])
    assert dome["transition_quality"]["continuity_claim"] == "G1_TARGET_REVIEW_GRADE_OPEN_TIP_DOME"


@pytest.mark.parametrize(
    ("lattice_override", "defaults_override", "expected_reason"),
    [
        ({"status": "FAIL", "failure_reason": "upstream"}, None, "v1_0_3_tip_section_lattice_failed"),
        (None, {"tip_dome_height_mm": 0.0}, "v1_0_3_tip_dome_height_invalid"),
        (None, {"tip_dome_height_mm": "bad"}, "v1_0_3_tip_dome_height_invalid"),
        (None, {"tip_dome_short_direction_sample_count": 1}, "v1_0_3_tip_dome_sample_count_invalid"),
    ],
)
def test_open_tip_dome_rejects_failed_lattice_and_invalid_defaults(
    lattice_override,
    defaults_override,
    expected_reason,
):
    lattice = lattice_override if lattice_override is not None else _lattice()
    defaults = _defaults()
    if defaults_override is not None:
        defaults.update(defaults_override)

    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=defaults)

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == expected_reason
    assert dome["uv_grid"] == []
    assert dome["mesh"]["quad_count"] == 0


def test_open_tip_dome_rejects_missing_blade_and_malformed_tip_loop():
    lattice = _lattice()
    missing = build_v10_3_tip_dome(blade_index=len(lattice["blades"]), lattice=lattice, defaults=_defaults())
    malformed_lattice = copy.deepcopy(lattice)
    malformed_lattice["blades"][0]["section_loops"][-1]["segments"]["leading_edge"]["points"][0] = [1.0, 2.0]

    malformed = build_v10_3_tip_dome(blade_index=0, lattice=malformed_lattice, defaults=_defaults())

    assert missing["status"] == "FAIL"
    assert missing["tip_dome_quality"]["reason"] == "v1_0_3_tip_blade_missing"
    assert malformed["status"] == "FAIL"
    assert malformed["tip_dome_quality"]["reason"] == "v1_0_3_tip_section_loop_malformed"


@pytest.mark.parametrize("blade_index", ["0", 0.5, True, -1])
def test_open_tip_dome_rejects_malformed_blade_index_without_raising(blade_index):
    dome = build_v10_3_tip_dome(blade_index=blade_index, lattice=_lattice(), defaults=_defaults())

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_blade_missing"
    assert dome["uv_grid"] == []


def test_open_tip_dome_rejects_self_intersecting_tip_loop_before_generation():
    lattice = _lattice()
    broken = copy.deepcopy(lattice)
    tip_loop = broken["blades"][0]["section_loops"][-1]
    stitched = _stitched_tip_loop(broken)
    open_loop = stitched[:-1]
    first_quarter = len(open_loop) // 4
    second_quarter = len(open_loop) // 2
    third_quarter = (3 * len(open_loop)) // 4
    bow_tie = (
        open_loop[:first_quarter]
        + open_loop[second_quarter:third_quarter]
        + open_loop[first_quarter:second_quarter]
        + open_loop[third_quarter:]
    )
    bow_tie.append(copy.deepcopy(bow_tie[0]))
    cursor = 0
    for segment_name in SEGMENT_ORDER:
        points = tip_loop["segments"][segment_name]["points"]
        segment_length = len(points)
        tip_loop["segments"][segment_name]["points"] = copy.deepcopy(bow_tie[cursor : cursor + segment_length])
        cursor += segment_length - 1
    tip_loop["closed_loop_points"] = copy.deepcopy(bow_tie)

    dome = build_v10_3_tip_dome(blade_index=0, lattice=broken, defaults=_defaults())

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_dome_foldover"
    assert dome["uv_grid"] == []
    assert dome["mesh"]["quad_count"] == 0


def test_open_tip_dome_rejects_non_adjacent_duplicate_tip_vertex():
    loop = [
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [2.0, 1.0, 0.0],
        [1.0, 1.0, 0.0],
        [2.0, 1.0, 0.0],
        [2.0, 2.0, 0.0],
        [0.0, 2.0, 0.0],
        [0.0, 0.0, 0.0],
    ]

    dome = build_v10_3_tip_dome(blade_index=0, lattice=_synthetic_tip_lattice(loop), defaults=_defaults())

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_dome_foldover"
    assert dome["uv_grid"] == []
    assert dome["mesh"]["quad_count"] == 0


def test_open_tip_dome_rejects_colinear_overlapping_non_adjacent_edges():
    loop = [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [4.0, 2.0, 0.0],
        [3.0, 2.0, 0.0],
        [3.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 2.0, 0.0],
        [0.0, 2.0, 0.0],
        [0.0, 0.0, 0.0],
    ]

    dome = build_v10_3_tip_dome(blade_index=0, lattice=_synthetic_tip_lattice(loop), defaults=_defaults())

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_dome_foldover"
    assert dome["uv_grid"] == []
    assert dome["mesh"]["quad_count"] == 0


def test_open_tip_dome_rejects_excessive_short_direction_sample_count():
    defaults = _defaults()
    defaults["tip_dome_short_direction_sample_count"] = 66

    dome = build_v10_3_tip_dome(blade_index=0, lattice=_lattice(), defaults=defaults)

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_dome_sample_count_invalid"
    assert dome["uv_grid"] == []


def test_open_tip_dome_rejects_excessive_boundary_sample_count():
    lattice = _lattice()
    defaults = _defaults()
    defaults["section_loop_sample_count"] = 65
    dense_lattice = build_section_loop_lattice(parameters={}, defaults=defaults)
    assert dense_lattice["status"] == "PASS"

    dome = build_v10_3_tip_dome(blade_index=0, lattice=dense_lattice, defaults=defaults)

    assert dome["status"] == "FAIL"
    assert dome["tip_dome_quality"]["reason"] == "v1_0_3_tip_dome_boundary_sample_count_exceeded"
    assert dome["uv_grid"] == []
    assert lattice["status"] == "PASS"


def test_open_tip_dome_payload_does_not_alias_input_lattice():
    lattice = _lattice()
    original_lattice = copy.deepcopy(lattice)
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=_defaults())

    dome["uv_grid"][0][0][0] = -999.0
    dome["edge_samples"]["tip_section_loop"][1][1] = -888.0
    dome["edge_samples"]["tip_crest_curve"][2][2] = -777.0

    assert lattice == original_lattice
    assert dome["edge_samples"]["tip_section_loop"] != original_lattice["blades"][0]["section_loops"][-1]["closed_loop_points"]
