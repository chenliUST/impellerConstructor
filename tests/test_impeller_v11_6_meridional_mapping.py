import sys
from pathlib import Path

# ruff: noqa: E402

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_meridional_mapping import (
    project_rz_points_to_meridional_s,
)


def test_streamwise_interval_uses_normalized_meridional_arc_length():
    profile = {
        "degree": 1,
        "knots": [0.0, 0.0, 0.5, 1.0, 1.0],
        "weights": [1.0, 1.0, 1.0],
        "control_points_rz_mm": [[10.0, 100.0], [10.0, 0.0], [100.0, 0.0]],
    }
    result = project_rz_points_to_meridional_s(
        profile,
        [[10.0, 50.0], [55.0, 0.0]],
        sample_count=1001,
        interval_quantiles=(0.0, 1.0),
    )

    assert result["status"] == "PASS"
    assert result["method"] == "nearest_projection_to_normalized_nurbs_arc_length"
    assert result["streamwise_interval_s"] == pytest.approx(
        [50.0 / 190.0, 145.0 / 190.0], abs=0.003
    )
    assert result["meridional_arc_length_mm"] == pytest.approx(190.0, abs=0.05)
    assert result["projection_residual_p95_mm"] < 0.05


def test_streamwise_projection_rejects_degenerate_or_out_of_domain_evidence():
    profile = {
        "degree": 1,
        "knots": [0.0, 0.0, 1.0, 1.0],
        "weights": [1.0, 1.0],
        "control_points_rz_mm": [[10.0, 0.0], [10.0, 0.0]],
    }
    result = project_rz_points_to_meridional_s(profile, [[10.0, 0.0]])
    assert result["status"] == "REJECTED"
    assert result["failure_reason"] == "degenerate_meridional_profile"


def test_streamwise_projection_rejects_evidence_outside_support_distance_gate():
    profile = {
        "degree": 1,
        "knots": [0.0, 0.0, 1.0, 1.0],
        "weights": [1.0, 1.0],
        "control_points_rz_mm": [[10.0, 0.0], [20.0, 10.0]],
    }

    result = project_rz_points_to_meridional_s(
        profile,
        [[1000.0, 1000.0], [1001.0, 1001.0]],
        maximum_projection_residual_mm=25.0,
        interval_quantiles=(0.0, 1.0),
    )

    assert result["status"] == "REJECTED"
    assert result["failure_reason"] == "meridional_projection_residual_exceeded"


def test_support_strip_projection_accepts_blade_points_between_corresponded_profiles():
    hub = {
        "degree": 1,
        "knots": [0.0, 0.0, 0.2, 1.0, 1.0],
        "control_points_rz_mm": [[10.0, 100.0], [10.0, 20.0], [90.0, 0.0]],
    }
    tip = {
        "degree": 1,
        "knots": [0.0, 0.0, 0.8, 1.0, 1.0],
        "control_points_rz_mm": [[30.0, 100.0], [100.0, 80.0], [110.0, 0.0]],
    }

    result = project_rz_points_to_meridional_s(
        hub,
        [[20.0, 90.0], [55.0, 50.0], [100.0, 10.0]],
        tip_profile_fit=tip,
        maximum_projection_residual_mm=1.0,
        interval_quantiles=(0.0, 1.0),
    )

    assert result["status"] == "PASS"
    assert result["method"] == (
        "nearest_projection_to_corresponded_hub_tip_support_strip"
    )
    assert result["projection_residual_maximum_mm"] < 1.0
    assert result["streamwise_interval_s"][0] < result["streamwise_interval_s"][1]


def test_support_strip_projection_clamps_roundoff_to_closed_unit_interval():
    hub = {"control_points_rz_mm": [[10.0, 0.0], [20.0, 0.0]]}
    tip = {"control_points_rz_mm": [[10.0, 10.0], [20.0, 10.0]]}

    result = project_rz_points_to_meridional_s(
        hub,
        [[10.0, 5.0], [20.0, 5.0]],
        tip_profile_fit=tip,
        maximum_projection_residual_mm=1.0,
        interval_quantiles=(0.0, 1.0),
    )

    assert result["status"] == "PASS"
    assert result["streamwise_interval_s"] == [0.0, 1.0]


def test_support_strip_projection_rejects_mirrored_evidence_outside_flowpath():
    hub = {"control_points_rz_mm": [[20.0, 80.0], [40.0, 0.0]]}
    tip = {"control_points_rz_mm": [[40.0, 80.0], [70.0, 0.0]]}

    result = project_rz_points_to_meridional_s(
        hub,
        [[-45.0, 70.0], [-65.0, 10.0]],
        tip_profile_fit=tip,
        maximum_projection_residual_mm=2.0,
        interval_quantiles=(0.0, 1.0),
    )

    assert result["status"] == "REJECTED"
    assert result["failure_reason"] == "meridional_projection_residual_exceeded"
