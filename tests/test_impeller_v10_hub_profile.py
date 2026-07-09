from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_hub_profile import build_v10_hub_revolve_faces


def test_v10_hub_profile_outputs_named_bevel_faces():
    hub = build_v10_hub_revolve_faces(
        outer_radius_mm=580.0,
        bore_radius_mm=40.0,
        height_mm=420.0,
        bottom_bevel_mm=24.0,
        bore_top_bevel_mm=18.0,
        bore_bottom_bevel_mm=18.0,
        theta_samples=17,
    )

    face_ids = {face["id"] for face in hub["faces"]}

    assert hub["hub_profile_status"] == "PASS"
    assert {
        "hub_main_revolve_surface",
        "hub_top_face",
        "hub_bottom_face",
        "hub_bottom_outer_bevel_surface",
        "mounting_bore_cylinder_surface",
        "mounting_bore_top_bevel_surface",
        "mounting_bore_bottom_bevel_surface",
    }.issubset(face_ids)


def test_v10_hub_profile_rejects_bevel_larger_than_radius_domain():
    hub = build_v10_hub_revolve_faces(
        outer_radius_mm=50.0,
        bore_radius_mm=40.0,
        height_mm=420.0,
        bottom_bevel_mm=24.0,
        bore_top_bevel_mm=18.0,
        bore_bottom_bevel_mm=18.0,
        theta_samples=17,
    )

    assert hub["hub_profile_status"] == "FAIL"
    assert hub["failure_reason"] == "v1_0_hub_profile_segment_failed"
