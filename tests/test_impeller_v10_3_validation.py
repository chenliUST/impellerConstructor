from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_v10_3_validation import validate_v10_3_surface_graph
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from tests.impeller_v10_3_historical_fixture import historical_v10_3_open_runtime


def _graph() -> dict:
    runtime = historical_v10_3_open_runtime()
    params = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", params, runtime["facets"], dsl_context=runtime)
    return metadata["surface_graph"]


def _visible_root(graph: dict) -> dict:
    return next(
        surface
        for surface in graph["surfaces"]
        if surface.get("face_family") == "blade_root"
        and surface.get("display", {}).get("inspection_class") == "root_to_hub_blend"
        and surface.get("display", {}).get("aggregate_surface") is not True
        and surface.get("display", {}).get("visible_by_default") is not False
    )


def test_v10_3_validation_passes_default_open_graph():
    report = validate_v10_3_surface_graph(_graph())

    assert report["status"] == "PASS"
    assert report["failure_count"] == 0
    assert report["summary"]["visible_root_component_count"] == 32
    assert report["summary"]["tip_dome_count"] == 8


def test_v10_3_validation_skips_non_v10_3_graph():
    report = validate_v10_3_surface_graph({"geometry_patch_version": "1.0.2", "surfaces": []})

    assert report["status"] == "SKIP"
    assert report["failure_count"] == 0


def test_v10_3_validation_fails_visible_root_foldover():
    graph = copy.deepcopy(_graph())
    root = _visible_root(graph)
    root["transition_quality"]["foldover_count"] = 1

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_root_segment_foldover" for failure in report["failures"])


def test_v10_3_validation_fails_missing_root_quality_metrics():
    graph = copy.deepcopy(_graph())
    root = _visible_root(graph)
    root.pop("transition_quality", None)
    root.pop("root_blend_quality", None)

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_root_quality_metric_missing" for failure in report["failures"])


def test_v10_3_validation_fails_visible_root_aggregate():
    graph = copy.deepcopy(_graph())
    aggregate = next(
        surface
        for surface in graph["surfaces"]
        if surface.get("face_family") == "blade_root"
        and surface.get("display", {}).get("aggregate_surface") is True
    )
    aggregate["display"]["visible_by_default"] = True

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(
        failure["reason"] == "v1_0_3_root_aggregate_visibility_failed"
        for failure in report["failures"]
    )


def test_v10_3_validation_fails_missing_tip_dome():
    graph = copy.deepcopy(_graph())
    graph["surfaces"] = [
        surface
        for surface in graph["surfaces"]
        if surface.get("role") != "open_tip_dome"
    ]

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_tip_dome_missing" for failure in report["failures"])


def test_v10_3_validation_fails_hidden_tip_domes():
    graph = copy.deepcopy(_graph())
    for surface in graph["surfaces"]:
        if surface.get("role") == "open_tip_dome":
            surface.setdefault("display", {})["visible_by_default"] = False

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_tip_dome_missing" for failure in report["failures"])


def test_v10_3_validation_fails_missing_root_components():
    graph = copy.deepcopy(_graph())
    graph["surfaces"] = [
        surface
        for surface in graph["surfaces"]
        if not (
            surface.get("face_family") == "blade_root"
            and surface.get("display", {}).get("aggregate_surface") is not True
        )
    ]

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_root_components_missing" for failure in report["failures"])


def test_v10_3_validation_fails_missing_topology_graph_and_integrates_with_report():
    graph = copy.deepcopy(_graph())
    graph.pop("topology_graph", None)

    report = validate_v10_3_surface_graph(graph)
    integrated = build_geometry_validation_report(surface_graph=graph)

    assert report["status"] == "FAIL"
    assert any(failure["reason"] == "v1_0_3_topology_graph_missing" for failure in report["failures"])
    assert integrated["geometry_validation_status"] == "FAIL"
    assert any(
        failure["reason"] == "v1_0_3_topology_graph_missing"
        for failure in integrated["blocking_failures"]
    )
    assert any(
        check["check_id"] == "v10_3_section_loop_root_blend" and check["status"] == "FAIL"
        for check in integrated["checks"]
    )
