from __future__ import annotations

import copy
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice


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
    }


def _lattice() -> dict:
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    assert lattice["status"] == "PASS"
    return lattice


def _surfaces_by_id(result: dict) -> dict:
    return {surface["id"]: surface for surface in result["surfaces"]}


def test_blade_faces_are_built_from_four_section_segments():
    lattice = _lattice()

    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "PASS"
    assert len(result["surfaces"]) == 4 * len(lattice["blades"])
    surfaces = _surfaces_by_id(result)
    assert {
        "blade_0_pressure_surface",
        "blade_0_suction_surface",
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_3_pressure_surface",
        "blade_3_suction_surface",
        "blade_3_leading_edge_surface",
        "blade_3_trailing_edge_surface",
    } <= set(surfaces)
    pressure = surfaces["blade_0_pressure_surface"]
    source_loop = lattice["blades"][0]["section_loops"][0]
    assert pressure["uv_grid"][0] == source_loop["segments"]["pressure_side"]["points"]
    assert pressure["source"]["section_loop_family_id"] == source_loop["section_loop_family_id"]
    assert pressure["source"]["segment_family"] == "pressure_side"
    assert pressure["blade_index"] == 0


def test_incident_blade_faces_share_exact_boundaries():
    result = build_blade_faces_from_section_lattice(_lattice())
    surfaces = _surfaces_by_id(result)
    pressure = surfaces["blade_0_pressure_surface"]
    leading = surfaces["blade_0_leading_edge_surface"]
    suction = surfaces["blade_0_suction_surface"]
    trailing = surfaces["blade_0_trailing_edge_surface"]

    assert pressure["edge_samples"]["leading"] == leading["edge_samples"]["pressure"]
    assert leading["edge_samples"]["suction"] == suction["edge_samples"]["leading"]
    assert suction["edge_samples"]["trailing"] == trailing["edge_samples"]["suction"]
    assert trailing["edge_samples"]["pressure"] == pressure["edge_samples"]["trailing"]


def test_blade_faces_include_class_metadata_and_mesh_wire_contract():
    result = build_blade_faces_from_section_lattice(_lattice())
    surface = _surfaces_by_id(result)["blade_3_suction_surface"]

    assert surface["kind"] == "native_topology_face"
    assert surface["face_family"] == "blade_suction"
    assert surface["role"] == "blade_suction"
    assert surface["blade_index"] == 3
    assert surface["blade_class"] == "splitter"
    assert surface["blade_pair_index"] == 1
    assert surface["wireframe"] == {"enabled": True, "source": "uv_grid"}
    assert surface["display"]["inspection_class"] == "blade_suction"
    assert surface["mesh"]["strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
    assert surface["mesh"]["quad_count"] > 0
    assert len(surface["mesh"]["quads"]) == surface["mesh"]["quad_count"]
    assert all(set(quad) == {"indices"} for quad in surface["mesh"]["quads"])
    assert all("vertices" not in quad for quad in surface["mesh"]["quads"])
    assert len(surface["control_net"]) >= 2
    assert surface["transition_quality"]["foldover_count"] == 0
    assert surface["transition_quality"]["segment_family"] == "suction_side"
    assert surface["transition_quality"]["source_loop_count"] == len(surface["uv_grid"])


def test_failed_section_lattice_short_circuits_blade_faces():
    result = build_blade_faces_from_section_lattice(
        {"status": "FAIL", "failure_reason": "upstream_error"}
    )

    assert result == {
        "status": "FAIL",
        "reason": "v1_0_3_section_lattice_failed",
        "surfaces": [],
    }


def test_malformed_section_lattice_fails_with_clear_reason():
    result = build_blade_faces_from_section_lattice({"status": "PASS"})

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert "blades" in result["details"]
    assert result["surfaces"] == []


@pytest.mark.parametrize("lattice", [None, [], "not a lattice"])
def test_non_dict_section_lattice_fails_without_raising(lattice):
    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert result["surfaces"] == []


def test_ragged_segment_sample_counts_fail_without_raising():
    lattice = _lattice()
    segment = lattice["blades"][0]["section_loops"][1]["segments"]["pressure_side"]
    segment["points"].pop()
    segment["sample_count"] = len(segment["points"])

    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert "rectangular" in result["details"]
    assert result["surfaces"] == []


def test_invalid_segment_point_shape_fails_without_raising():
    lattice = _lattice()
    lattice["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["points"][0] = [1.0, 2.0]

    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert "numeric 3D point" in result["details"]
    assert result["surfaces"] == []


def test_malformed_segment_sample_count_fails_without_raising():
    lattice = _lattice()
    lattice["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["sample_count"] = "bad"

    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert "sample_count" in result["details"]
    assert result["surfaces"] == []


def test_malformed_foldover_count_fails_without_raising():
    lattice = _lattice()
    lattice["blades"][0]["section_loops"][0]["metrics"]["foldover_count"] = "bad"

    result = build_blade_faces_from_section_lattice(lattice)

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_3_section_lattice_malformed"
    assert "foldover_count" in result["details"]
    assert result["surfaces"] == []


def test_named_edges_match_source_segment_endpoint_columns():
    lattice = _lattice()
    result = build_blade_faces_from_section_lattice(lattice)
    surfaces = _surfaces_by_id(result)
    source_loops = lattice["blades"][0]["section_loops"]

    assert surfaces["blade_0_pressure_surface"]["edge_samples"]["trailing"] == [
        loop["segments"]["pressure_side"]["points"][0]
        for loop in source_loops
    ]
    assert surfaces["blade_0_pressure_surface"]["edge_samples"]["leading"] == [
        loop["segments"]["pressure_side"]["points"][-1]
        for loop in source_loops
    ]
    assert surfaces["blade_0_leading_edge_surface"]["edge_samples"]["pressure"] == [
        loop["segments"]["leading_edge"]["points"][0]
        for loop in source_loops
    ]
    assert surfaces["blade_0_leading_edge_surface"]["edge_samples"]["suction"] == [
        loop["segments"]["leading_edge"]["points"][-1]
        for loop in source_loops
    ]


def test_blade_face_payloads_do_not_alias_lattice_or_each_other():
    lattice = _lattice()
    original_lattice = copy.deepcopy(lattice)
    result = build_blade_faces_from_section_lattice(lattice)
    surfaces = _surfaces_by_id(result)
    pressure = surfaces["blade_0_pressure_surface"]
    leading = surfaces["blade_0_leading_edge_surface"]

    pressure["uv_grid"][0][0][0] = -999.0
    pressure["edge_samples"]["leading"][0][0] = -888.0

    assert lattice == original_lattice
    assert leading["edge_samples"]["pressure"][0] == original_lattice["blades"][0]["section_loops"][0]["segments"]["leading_edge"]["points"][0]
    assert pressure["edge_samples"]["leading"] != leading["edge_samples"]["pressure"]
