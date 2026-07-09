from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network


def test_v10_blade_face_network_has_required_named_faces():
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=7,
        sample_count=13,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )

    face_ids = {face["id"] for face in network["faces"]}

    assert network["blade_face_network_status"] == "PASS"
    assert {
        "blade_0_pressure_surface",
        "blade_0_suction_surface",
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_tip_surface",
        "blade_0_root_annular_surface",
    }.issubset(face_ids)
    assert network["closed_profile_count"] == 7


def test_v10_blade_face_network_has_no_transition_geometry_fields():
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=5,
        sample_count=9,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )

    assert all("transition_geometry" not in face for face in network["faces"])
