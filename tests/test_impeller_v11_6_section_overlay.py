import math

import numpy as np
import pytest

from part_rule_synthesis.impeller_v11_6_section_overlay import (
    SectionOverlayError,
    build_section_overlay_contract,
)


def _mapping():
    return {
        "section_provenance": {
            "direct_section_curve_network": {
                "status": "PASS",
                "populations": {
                    "main": {
                        "stations": [
                            {
                                "active_h": 0.0,
                                "canonical_loop_points_xyz_mm": [[1, 0, 2], [2, 0, 2]],
                            },
                            {
                                "active_h": 1.0,
                                "canonical_loop_points_xyz_mm": [[1, 0, 5], [2, 0, 5]],
                            },
                        ]
                    }
                },
            }
        }
    }


def _graph():
    return {
        "direct_section_curve_network": {
            "generated_section_loops": [
                {"population": "main", "active_h": 0.0, "points_xyz_mm": [[1, 0, 2], [2, 0, 2]]},
                {"population": "main", "active_h": 1.0, "points_xyz_mm": [[1, 0, 5], [2, 0, 5]]},
            ]
        }
    }


def test_overlay_keeps_display_phase_separate_from_construction_conformance():
    angle = math.pi / 2.0
    matrix = np.asarray(
        [
            [math.cos(angle), -math.sin(angle), 0, 0],
            [math.sin(angle), math.cos(angle), 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
    )

    contract = build_section_overlay_contract(
        _mapping(), _graph(), generated_to_comparison_matrix=matrix
    )

    assert contract["source"]["stations"][0]["points_xyz_mm"][0] == [1.0, 0.0, 2.0]
    assert np.allclose(
        contract["generated"]["stations"][0]["points_xyz_mm"][0],
        [0.0, 1.0, 2.0],
        atol=1.0e-12,
    )
    assert contract["source"]["stations"] is not contract["generated"]["stations"]
    assert contract["maximum_station_hausdorff_mm"] == pytest.approx(0.0)
    assert contract["conformance_coordinate_frame"] == (
        "canonical_axis_frame_before_periodic_display_alignment"
    )


def test_overlay_reports_per_role_bidirectional_residuals():
    mapping = _mapping()
    graph = _graph()
    mapping["section_provenance"]["direct_section_curve_network"]["populations"][
        "main"
    ]["stations"][0]["curves"] = {
        "side_a": {"canonical_points_xyz_mm": [[1, 0, 2], [2, 0, 2]]}
    }
    graph["direct_section_curve_network"]["generated_section_loops"][0][
        "surface_curve_rows"
    ] = {"side_a": [[1, 0.25, 2], [2, 0.25, 2]]}

    contract = build_section_overlay_contract(
        mapping, graph, generated_to_comparison_matrix=np.eye(4)
    )

    residual = contract["station_residuals"][0]["role_residuals"]["side_a"]
    assert residual["source_to_generated_max_mm"] == pytest.approx(0.25)
    assert residual["generated_to_source_max_mm"] == pytest.approx(0.25)
    assert residual["hausdorff_max_mm"] == pytest.approx(0.25)


def test_overlay_fails_closed_when_generated_intersections_are_missing():
    with pytest.raises(SectionOverlayError, match="generated carrier intersections"):
        build_section_overlay_contract(
            _mapping(), {}, generated_to_comparison_matrix=np.eye(4)
        )
