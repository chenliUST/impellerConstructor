from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_4_validation import validate_v10_4_surface_graph


def _base_graph() -> dict:
    return {
        "geometry_patch_version": "1.0.4",
        "surfaces": [
            {
                "id": "blade_0_root_annular_surface",
                "v1_0_4_root_quality": {"status": "PASS"},
            },
            {
                "id": "blade_0_tip_dome_surface",
                "role": "open_tip_dome",
                "v1_0_4_tip_quality": {"status": "PASS"},
            },
        ],
        "v1_0_4_hub_quality": {"status": "PASS"},
        "v1_0_4_continuity_summary": {"status": "PASS"},
        "v1_0_4_angle_quality": {"status": "PASS"},
    }


def _graph() -> dict:
    return copy.deepcopy(_base_graph())


def test_v10_4_validation_passes_default_open_graph():
    failures = validate_v10_4_surface_graph(_base_graph())

    assert failures == []


def test_v10_4_validation_rejects_missing_root_quality():
    graph = _graph()
    root = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_annular_surface")
    root.pop("v1_0_4_root_quality", None)

    failures = validate_v10_4_surface_graph(graph)

    assert any(failure["reason"] == "v1_0_4_root_quality_missing" for failure in failures)


def test_v10_4_validation_rejects_failed_tip_quality():
    graph = _graph()
    tip = next(surface for surface in graph["surfaces"] if surface.get("role") == "open_tip_dome")
    tip["v1_0_4_tip_quality"]["status"] = "FAIL"
    tip["v1_0_4_tip_quality"]["reason"] = "v1_0_4_tip_area_exceeds_limit"

    failures = validate_v10_4_surface_graph(graph)

    assert any(failure["reason"] == "v1_0_4_tip_area_exceeds_limit" for failure in failures)


def test_v10_4_validation_rejects_failed_hub_quality():
    graph = _graph()
    graph["v1_0_4_hub_quality"]["status"] = "FAIL"
    graph["v1_0_4_hub_quality"]["reason"] = "v1_0_4_hub_profile_conical_fallback"

    failures = validate_v10_4_surface_graph(graph)

    assert any(
        failure["reason"] == "v1_0_4_hub_profile_conical_fallback"
        for failure in failures
    )


def test_v10_4_validation_rejects_failed_continuity_summary():
    graph = _graph()
    graph["v1_0_4_continuity_summary"]["status"] = "FAIL"
    graph["v1_0_4_continuity_summary"]["reason"] = "v1_0_4_measured_g2_continuity_failed"

    failures = validate_v10_4_surface_graph(graph)

    assert any(
        failure["reason"] == "v1_0_4_measured_g2_continuity_failed"
        for failure in failures
    )


def test_v10_4_validation_rejects_failed_angle_quality():
    graph = _graph()
    graph["v1_0_4_angle_quality"]["status"] = "FAIL"
    graph["v1_0_4_angle_quality"]["reason"] = "v1_0_4_blade_hub_angle_out_of_range"

    failures = validate_v10_4_surface_graph(graph)

    assert any(
        failure["reason"] == "v1_0_4_blade_hub_angle_out_of_range"
        for failure in failures
    )


def test_v10_4_validation_skips_non_v10_4_graph():
    graph = _graph()
    graph["geometry_patch_version"] = "1.0.3"
    graph.pop("v1_0_4_hub_quality", None)

    failures = validate_v10_4_surface_graph(graph)

    assert graph["geometry_patch_version"] == "1.0.3"
    assert failures == []
