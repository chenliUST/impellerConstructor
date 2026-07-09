from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
import part_rule_synthesis.impeller_v10_surface_graph as surface_graph_builder
from part_rule_synthesis.impeller_v10_4_tip_surface import upgrade_tip_surface_contract
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)[
        "surface_graph"
    ]


def test_v10_4_tip_surface_stays_inside_tip_loop_domain():
    graph = _graph()
    tip = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_tip_dome_surface")
    quality = tip["v1_0_4_tip_quality"]

    assert quality["status"] == "PASS"
    assert quality["tip_boundary_gap_mm"] <= 1.0e-6
    assert quality["tip_area_ratio"] <= 1.15
    assert quality["outside_loop_sample_count"] == 0
    assert quality["foldover_count"] == 0


def test_v10_4_tip_surface_rejects_samples_inside_bbox_but_outside_concave_loop():
    concave_loop = [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [4.0, 1.0, 0.0],
        [1.0, 1.0, 0.0],
        [1.0, 4.0, 0.0],
        [0.0, 4.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    tip = {
        "status": "PASS",
        "edge_samples": {"tip_section_loop": concave_loop},
        "uv_grid": [
            concave_loop,
            [
                [2.0, 2.0, 1.0],
                [1.333333333, 1.333333333, 1.0],
            ],
        ],
        "transition_quality": {"foldover_count": 0},
    }

    upgraded = upgrade_tip_surface_contract(tip, area_ratio_limit=2.0)
    quality = upgraded["v1_0_4_tip_quality"]

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_tip_exceeds_loop_domain"
    assert quality["outside_loop_sample_count"] > 0


def test_v10_4_tip_surface_checks_full_grid_for_certified_contracted_dome():
    concave_loop = [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [4.0, 1.0, 0.0],
        [1.0, 1.0, 0.0],
        [1.0, 4.0, 0.0],
        [0.0, 4.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    tip = {
        "status": "PASS",
        "edge_samples": {"tip_section_loop": concave_loop},
        "uv_grid": [
            concave_loop,
            [
                [2.0, 2.0, 1.0],
                [1.333333333, 1.333333333, 1.0],
            ],
        ],
        "tip_dome_quality": {
            "status": "PASS",
            "tip_dome_contraction_rule": {"method": "unit-test"},
        },
        "transition_quality": {"foldover_count": 0},
    }

    upgraded = upgrade_tip_surface_contract(tip, area_ratio_limit=2.0)
    quality = upgraded["v1_0_4_tip_quality"]

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_tip_exceeds_loop_domain"
    assert quality["outside_loop_sample_count"] > 0


def test_v10_4_tip_surface_rejects_area_ratio_above_limit():
    boundary = [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [4.0, 4.0, 0.0],
        [0.0, 4.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    tip = {
        "status": "PASS",
        "edge_samples": {"tip_section_loop": boundary},
        "uv_grid": [boundary],
        "transition_quality": {"foldover_count": 0},
    }

    upgraded = upgrade_tip_surface_contract(tip, area_ratio_limit=0.5)
    quality = upgraded["v1_0_4_tip_quality"]

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_tip_area_exceeds_limit"
    assert quality["tip_area_ratio"] > quality["tip_area_ratio_limit"]


def test_v10_4_tip_quality_failure_reason_propagates_to_graph_transition_failures(monkeypatch):
    reason = "v1_0_4_tip_area_exceeds_limit"
    original_upgrade = surface_graph_builder.upgrade_tip_surface_contract

    def fail_tip_quality(tip_surface: dict, *, area_ratio_limit: float = 1.15) -> dict:
        upgraded = original_upgrade(tip_surface, area_ratio_limit=area_ratio_limit)
        upgraded["v1_0_4_tip_quality"]["status"] = "FAIL"
        upgraded["v1_0_4_tip_quality"]["reason"] = reason
        return upgraded

    monkeypatch.setattr(surface_graph_builder, "upgrade_tip_surface_contract", fail_tip_quality)

    graph = _graph()

    assert graph["surface_graph_status"] == "FAIL"
    assert any(
        failure.get("stage") == "tip_dome"
        and failure.get("surface_id") == "blade_0_tip_dome_surface"
        and failure.get("reason") == reason
        for failure in graph["transition_failures"]
    )
