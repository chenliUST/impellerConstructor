from __future__ import annotations

import copy
import sys
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


@lru_cache(maxsize=1)
def _base_graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]


def _graph() -> dict:
    return copy.deepcopy(_base_graph())


def test_v10_4_open_surface_graph_passes_contracts():
    graph = _base_graph()
    report = build_geometry_validation_report(surface_graph=graph)

    assert graph["geometry_patch_version"] == "1.0.4"
    assert (
        graph["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert graph["surface_graph_status"] == "PASS"
    assert graph["v1_0_4_transition_failure_count"] == 0
    assert report["geometry_validation_status"] == "PASS"
    assert any(
        check["check_id"] == "v10_4_surface_graph_contract" and check["status"] == "PASS"
        for check in report["checks"]
    )


def test_v10_4_geometry_validation_report_blocks_failed_root_quality():
    graph = copy.deepcopy(_graph())
    root = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_annular_surface")
    root["v1_0_4_root_quality"]["status"] = "FAIL"
    root["v1_0_4_root_quality"]["reason"] = "v1_0_4_root_foldover"

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(
        failure["reason"] == "v1_0_4_root_foldover"
        for failure in report["blocking_failures"]
    )
