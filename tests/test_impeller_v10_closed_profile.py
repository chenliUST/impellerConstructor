from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_closed_profile import build_closed_blade_section_profile


def test_v10_closed_profile_has_named_pressure_suction_and_edge_cap_curves():
    profile = build_closed_blade_section_profile(
        station_index=0,
        station_count=5,
        center=(300.0, 0.0, 100.0),
        tangent=(0.0, 1.0, 0.0),
        radial=(1.0, 0.0, 0.0),
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
        sample_count=17,
    )

    assert profile["closed_profile_status"] == "PASS"
    assert set(profile["curves"]) == {
        "pressure_side_curve",
        "leading_edge_cap_curve",
        "suction_side_curve",
        "trailing_edge_cap_curve",
    }
    assert profile["max_closure_gap_mm"] <= 1.0e-9
    assert len(profile["closed_loop"]) > 20


def test_v10_closed_profile_rejects_non_positive_thickness():
    profile = build_closed_blade_section_profile(
        station_index=0,
        station_count=5,
        center=(300.0, 0.0, 100.0),
        tangent=(0.0, 1.0, 0.0),
        radial=(1.0, 0.0, 0.0),
        thickness_mm=0.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
        sample_count=17,
    )

    assert profile["closed_profile_status"] == "FAIL"
    assert profile["failure_reason"] == "v1_0_closed_blade_profile_failed"
