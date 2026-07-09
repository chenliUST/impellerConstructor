from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from impeller_v10_2_historical_fixture import historical_v10_2_graph
from part_rule_synthesis.impeller_v10_2_continuity_validation import (
    validate_v10_2_continuous_blade_attachment,
)


def _v10_2_graph(preset_id: str = "radial_open_reference_v1_0") -> dict[str, Any]:
    return historical_v10_2_graph(preset_id)


def _surface(graph: dict[str, Any], surface_id: str) -> dict[str, Any]:
    return next(surface for surface in graph["surfaces"] if surface["id"] == surface_id)


def _has_failure(report: dict[str, Any], reason: str) -> bool:
    return any(failure["reason"] == reason for failure in report["blocking_failures"])


def _check_status(report: dict[str, Any], check_id: str) -> str | None:
    for check in report["checks"]:
        if check["check_id"] == check_id:
            return check["status"]
    return None


def test_v10_2_validation_helper_skips_non_v10_2_graph():
    report = validate_v10_2_continuous_blade_attachment(
        {"geometry_patch_version": "1.0.1", "surfaces": []}
    )

    assert report == {"status": "SKIP", "blocking_failures": [], "summary": {}}


def test_v10_2_validation_passes_complete_continuous_attachment_graph():
    report = build_geometry_validation_report(surface_graph=_v10_2_graph())

    assert report["geometry_validation_status"] == "PASS"
    assert report["v1_0_2_validation_summary"]["continuous_blade_attachment_status"] == "PASS"


def test_v10_2_validation_rejects_root_inner_loop_mismatch():
    graph = copy.deepcopy(_v10_2_graph())
    root = _surface(graph, "blade_0_root_annular_surface")
    root["edge_samples"]["blade_inner_loop"][0] = [999.0, 999.0, 999.0]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_root_inner_loop_mismatch")
    assert _check_status(report, "v10_2_continuous_blade_attachment") == "FAIL"


def test_v10_2_validation_rejects_failed_attachment_quality_without_graph_level_failure():
    graph = copy.deepcopy(_v10_2_graph())
    root = _surface(graph, "blade_0_root_annular_surface")
    root["attachment_quality"]["status"] = "FAIL"
    root["attachment_quality"]["reason"] = "v1_0_2_root_attachment_projection_failed"
    graph["v1_0_2_transition_failures"] = []
    graph["transition_failures"] = []

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_root_attachment_projection_failed")
    assert _check_status(report, "v10_2_continuous_blade_attachment") == "FAIL"


def test_v10_2_validation_rejects_root_support_domain_violation():
    graph = copy.deepcopy(_v10_2_graph())
    root = _surface(graph, "blade_0_root_annular_surface")
    root["attachment_quality"]["support_domain_violation_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_root_support_domain_violation")


def test_v10_2_validation_rejects_closed_tip_inner_loop_mismatch():
    graph = copy.deepcopy(_v10_2_graph("radial_closed_reference_v1_0"))
    tip = _surface(graph, "blade_0_tip_surface")
    tip["edge_samples"]["blade_inner_loop"][0] = [999.0, 999.0, 999.0]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_tip_inner_loop_mismatch")


def test_v10_2_validation_rejects_closed_tip_support_domain_violation():
    graph = copy.deepcopy(_v10_2_graph("radial_closed_reference_v1_0"))
    tip = _surface(graph, "blade_0_tip_surface")
    tip["attachment_quality"]["support_domain_violation_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_tip_support_domain_violation")


def test_v10_2_validation_rejects_transition_foldover_count():
    graph = copy.deepcopy(_v10_2_graph())
    transition = _surface(graph, "blade_0_leading_edge_surface")
    transition["foldover_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_transition_foldover")


def test_v10_2_validation_rejects_attachment_transition_quality_foldover_count():
    graph = copy.deepcopy(_v10_2_graph())
    root = _surface(graph, "blade_0_root_annular_surface")
    root["attachment_quality"]["foldover_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_transition_foldover")


def test_v10_2_validation_rejects_explicit_transition_quality_foldover_status():
    graph = copy.deepcopy(_v10_2_graph())
    transition = _surface(graph, "blade_0_trailing_edge_surface")
    transition["transition_quality"]["foldover_status"] = "FAIL"

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_transition_foldover")


def test_v10_2_validation_rejects_graph_level_transition_failures():
    graph = copy.deepcopy(_v10_2_graph())
    failure = {
        "blade_index": 0,
        "surface_id": "blade_0_root_annular_surface",
        "stage": "v1_0_2_root_attachment",
        "status": "FAIL",
        "reason": "v1_0_2_resolved_attachment_defaults_missing",
    }
    graph["v1_0_2_transition_failures"] = [failure]
    graph["transition_failures"] = [
        {
            "blade_index": 0,
            "surface_id": "blade_0_root_annular_surface",
            "stage": "v1_0_2_root_attachment",
            "status": "FAIL",
            "reason": "v1_0_2_resolved_attachment_defaults_missing",
        }
    ]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert _has_failure(report, "v1_0_2_resolved_attachment_defaults_missing")
    matching_failures = [
        failure
        for failure in report["blocking_failures"]
        if failure["reason"] == "v1_0_2_resolved_attachment_defaults_missing"
    ]
    assert len(matching_failures) == 1
