from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_2_historical_fixture import (
    historical_v10_2_graph_tuple,
    historical_v10_2_runtime,
)
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_support_domain import (
    offset_loop_on_revolved_support,
    validate_preset_feasibility,
)


def _support_surface() -> dict:
    return {
        "id": "hub_revolved_support",
        "profile_samples_rz": [
            {"r_mm": 10.0, "z_mm": 0.0},
            [11.0, 5.0],
            {"radius_mm": 12.0, "z_mm": 10.0},
        ],
    }


def _radius(point: list[float]) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _distance(first: list[float], second: list[float]) -> float:
    return sum((float(left) - float(right)) ** 2 for left, right in zip(first, second)) ** 0.5


def _open_v10_surfaces() -> dict[str, dict]:
    _graph, surfaces, _runtime = historical_v10_2_graph_tuple("radial_open_reference_v1_0")
    return surfaces


def test_offset_loop_on_revolved_support_projects_closed_loop_to_support_profile():
    inner_loop = [
        [14.0, 0.0, 0.0],
        [0.0, 14.0, 5.0],
        [-14.0, 0.0, 10.0],
        [14.0, 0.0, 0.0],
    ]

    result = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=_support_surface(),
        width_mm=2.0,
    )

    assert result["status"] == "PASS"
    assert result["offset_width_request_mm"] == 2.0
    assert result["support_domain_violation_count"] == 0
    assert result["max_projection_residual_mm"] <= 1.0e-6
    assert len(result["projected_loop"]) == len(inner_loop)
    assert result["outer_loop"] == result["projected_loop"]
    assert result["projected_loop"][0] == result["projected_loop"][-1]
    for source, projected in zip(inner_loop, result["projected_loop"]):
        assert 0.0 <= projected[2] <= 10.0
        assert _radius(projected) == pytest.approx(10.0 + projected[2] / 5.0)
        assert _distance(source, projected) > 0.0


def test_offset_loop_on_revolved_support_fails_when_profile_samples_are_missing():
    result = offset_loop_on_revolved_support(
        inner_loop=[[1.0, 0.0, 0.0]],
        support_surface={"id": "empty_support"},
        width_mm=1.0,
    )

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_2_support_profile_samples_missing"
    assert result["outer_loop"] == result["projected_loop"]


def test_offset_loop_on_revolved_support_rejects_negative_width():
    result = offset_loop_on_revolved_support(
        inner_loop=[[1.0, 0.0, 0.0]],
        support_surface=_support_surface(),
        width_mm=-0.001,
    )

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_2_support_offset_width_negative"
    assert result["outer_loop"] == result["projected_loop"]


def test_offset_loop_on_revolved_support_requested_loop_changes_with_valid_width():
    inner_loop = [[14.0, 0.0, 0.0], [0.0, 15.0, 5.0], [-16.0, 0.0, 10.0]]

    narrow = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=_support_surface(),
        width_mm=1.0,
    )
    wide = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=_support_surface(),
        width_mm=2.5,
    )

    assert narrow["status"] == "PASS"
    assert wide["status"] == "PASS"
    assert narrow["requested_offset_loop"] != wide["requested_offset_loop"]
    assert narrow["width_application_mode"] == "closed_footprint_outward_offset_in_revolved_support_domain"
    assert narrow["max_requested_offset_applied_mm"] == 1.0
    assert wide["max_requested_offset_applied_mm"] == 2.5
    for result in [narrow, wide]:
        for point in result["requested_offset_loop"]:
            assert 0.0 <= point[2] <= 10.0
            assert _radius(point) == pytest.approx(10.0 + point[2] / 5.0)
        for point in result["projected_loop"]:
            assert 0.0 <= point[2] <= 10.0
            assert _radius(point) == pytest.approx(10.0 + point[2] / 5.0)
    assert wide["outer_loop"] == wide["projected_loop"]


def test_offset_loop_on_revolved_support_fails_when_z_exceeds_profile_domain():
    result = offset_loop_on_revolved_support(
        inner_loop=[[14.0, 0.0, 10.001]],
        support_surface=_support_surface(),
        width_mm=67.2,
    )

    assert result["status"] == "FAIL"
    assert result["reason"] == "v1_0_2_support_domain_violation"
    assert result["support_domain_violation_count"] == 1
    assert result["requested_offset_loop"] == result["projected_loop"]
    assert result["outer_loop"] == result["projected_loop"]


def test_offset_loop_on_revolved_support_clamps_small_z_overrun_with_lift_tolerance():
    result = offset_loop_on_revolved_support(
        inner_loop=[[14.0, 0.0, 10.5]],
        support_surface=_support_surface(),
        width_mm=2.0,
        z_tolerance_mm=1.0,
    )

    assert result["status"] == "PASS"
    assert result["support_domain_violation_count"] == 0
    assert result["support_z_clamp_count"] == 1
    assert result["outer_loop"] == result["projected_loop"]
    assert result["projected_loop"][0][2] == 10.0
    assert _radius(result["projected_loop"][0]) == pytest.approx(12.0)


def test_offset_loop_on_revolved_support_accepts_real_v10_open_root_attachment_width():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    width = runtime["resolved_attachment_defaults"]["resolved_root_attachment_width_mm"]
    surfaces = _open_v10_surfaces()
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    result = offset_loop_on_revolved_support(
        inner_loop=lattice["closed_loops"]["blade_exterior_root_loop"],
        support_surface=surfaces["hub_revolve_surface"],
        width_mm=width,
        z_tolerance_mm=runtime["resolved_attachment_defaults"]["resolved_root_attachment_lift_mm"],
    )

    assert width > 0.0
    assert lattice["status"] == "PASS"
    assert result["status"] == "PASS"
    assert result["support_domain_violation_count"] == 0
    assert result["offset_width_request_mm"] == width
    assert result["outer_loop"] == result["projected_loop"]
    assert len(result["projected_loop"]) == len(lattice["closed_loops"]["blade_exterior_root_loop"])


def test_preset_feasibility_fails_when_pitch_is_too_small():
    result = validate_preset_feasibility(
        blade_count=12,
        blade_thickness_mm=92.0,
        root_attachment_width_mm=67.2,
        root_attachment_lift_mm=11.04,
        tip_attachment_width_mm=41.4,
        tip_attachment_lift_mm=9.2,
        root_attachment_mean_radius_mm=150.0,
        hub_wall_thickness_mm=40.0,
        hub_bottom_thickness_mm=20.16,
        hood_wall_thickness_mm=0.0,
        closed=False,
    )

    assert result["preset_feasibility_status"] == "FAIL"
    assert result["reasons"] == ["v1_0_2_preset_blade_pitch_insufficient"]


def test_preset_feasibility_rejects_blade_count_below_two_without_pitch_clamping():
    result = validate_preset_feasibility(
        blade_count=1,
        blade_thickness_mm=20.0,
        root_attachment_width_mm=16.0,
        root_attachment_lift_mm=4.0,
        tip_attachment_width_mm=12.0,
        tip_attachment_lift_mm=3.0,
        root_attachment_mean_radius_mm=500.0,
        hub_wall_thickness_mm=100.0,
        hub_bottom_thickness_mm=100.0,
        hood_wall_thickness_mm=100.0,
        closed=True,
    )

    assert result["preset_feasibility_status"] == "FAIL"
    assert result["reasons"] == ["v1_0_2_preset_blade_count_below_minimum_two"]
    assert result["blade_pitch_mm"] is None
    assert result["resolved_support_domain_margins"]["minimum_pitch_margin_mm"] is None


def test_preset_feasibility_rejects_non_integer_blade_count():
    for blade_count in (6.0, "6", True, None):
        result = validate_preset_feasibility(
            blade_count=blade_count,
            blade_thickness_mm=20.0,
            root_attachment_width_mm=16.0,
            root_attachment_lift_mm=4.0,
            tip_attachment_width_mm=12.0,
            tip_attachment_lift_mm=3.0,
            root_attachment_mean_radius_mm=500.0,
            hub_wall_thickness_mm=100.0,
            hub_bottom_thickness_mm=100.0,
            hood_wall_thickness_mm=100.0,
            closed=True,
        )

        assert result["preset_feasibility_status"] == "FAIL"
        assert result["reasons"] == ["v1_0_2_preset_blade_count_invalid"]
        assert result["resolved_support_domain_margins"]["blade_count_minimum_margin"] is None


def test_preset_feasibility_open_preset_does_not_require_shroud_margin():
    result = validate_preset_feasibility(
        blade_count=6,
        blade_thickness_mm=20.0,
        root_attachment_width_mm=16.0,
        root_attachment_lift_mm=4.0,
        tip_attachment_width_mm=12.0,
        tip_attachment_lift_mm=3.0,
        root_attachment_mean_radius_mm=500.0,
        hub_wall_thickness_mm=100.0,
        hub_bottom_thickness_mm=100.0,
        hood_wall_thickness_mm=0.0,
        closed=False,
    )

    assert result["preset_feasibility_status"] == "PASS"
    assert "shroud_material_margin_mm" not in result["resolved_support_domain_margins"]
    assert result["not_applicable_constraints"] == {
        "closed_shroud_material_supports_tip_attachment_lift": "open_impeller_has_no_front_shroud_material"
    }


def test_preset_feasibility_uses_lift_plus_blade_thickness_for_material_margins():
    result = validate_preset_feasibility(
        blade_count=6,
        blade_thickness_mm=20.0,
        root_attachment_width_mm=16.0,
        root_attachment_lift_mm=4.0,
        tip_attachment_width_mm=12.0,
        tip_attachment_lift_mm=3.0,
        root_attachment_mean_radius_mm=500.0,
        hub_wall_thickness_mm=8.5,
        hub_bottom_thickness_mm=100.0,
        hood_wall_thickness_mm=5.75,
        closed=True,
    )

    assert result["preset_feasibility_status"] == "FAIL"
    assert result["reasons"] == [
        "v1_0_2_preset_hub_material_insufficient",
        "v1_0_2_preset_shroud_material_insufficient",
    ]
    margins = result["resolved_support_domain_margins"]
    assert margins["hub_material_margin_mm"] == -0.5
    assert margins["shroud_material_margin_mm"] == -0.25


def test_preset_feasibility_closed_preset_includes_shroud_material_check():
    result = validate_preset_feasibility(
        blade_count=6,
        blade_thickness_mm=20.0,
        root_attachment_width_mm=16.0,
        root_attachment_lift_mm=4.0,
        tip_attachment_width_mm=12.0,
        tip_attachment_lift_mm=3.0,
        root_attachment_mean_radius_mm=500.0,
        hub_wall_thickness_mm=100.0,
        hub_bottom_thickness_mm=100.0,
        hood_wall_thickness_mm=1.0,
        closed=True,
    )

    assert result["preset_feasibility_status"] == "FAIL"
    assert result["reasons"] == ["v1_0_2_preset_shroud_material_insufficient"]
    assert result["resolved_support_domain_margins"]["shroud_material_margin_mm"] < 0.0
    assert result["not_applicable_constraints"] == {}
