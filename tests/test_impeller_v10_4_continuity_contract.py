from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v10_4_continuity import measure_v10_4_continuity
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from tests.impeller_v10_3_historical_fixture import historical_v10_3_open_runtime


@lru_cache(maxsize=1)
def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]


def test_v10_4_g2_claims_are_measured_or_downgraded() -> None:
    graph = _graph()
    summary = graph["v1_0_4_continuity_summary"]

    assert summary["measured_edge_count"] > 0
    assert summary["status"] == "PASS"
    assert summary["max_position_gap_mm"] <= 1.0e-6
    assert summary["max_tangent_angle_deg"] <= 2.0
    assert summary["max_normal_angle_deg"] <= 5.0
    assert summary["max_curvature_proxy_mismatch"] <= 0.25
    assert all(
        measurement["status"] == "G2_MEASURED"
        for measurement in summary["edge_measurements"]
    )
    assert summary["allowed_statuses"] == [
        "G2_MEASURED",
        "G1_MEASURED_G2_FAILED",
        "G0_ONLY_FAILED",
        "EXTRAORDINARY_VERTEX_EXCLUDED",
    ]


def test_v10_4_continuity_summary_keeps_edge_measurement_metadata() -> None:
    graph = _graph()
    summary = graph["v1_0_4_continuity_summary"]
    measurements = summary["edge_measurements"]

    assert len(measurements) == summary["measured_edge_count"]
    assert all(measurement["status"] in summary["allowed_statuses"] for measurement in measurements)
    assert any(
        measurement["first_edge_role"] == "root"
        and measurement["second_edge_role"] == "blade_inner_loop"
        for measurement in measurements
    )
    for measurement in measurements:
        assert measurement["edge_id"]
        assert measurement["first_face_id"]
        assert measurement["second_face_id"]
        assert measurement["sample_count"] > 0
        assert "measurement_strategy" in measurement
        assert measurement["normal_angle_kind"] == "adjacent_surface_uv_grid_frame"
        if measurement["status"] == "G2_MEASURED":
            assert measurement["exact_g2_available"] is True


def test_v10_4_continuity_does_not_label_root_quality_proxy_as_g2() -> None:
    graph = {
        "surfaces": [
            {
                "id": "blade_pressure",
                "face_family": "blade_pressure",
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                    [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 1.0, 0.0]],
                    [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0]],
                ],
                "edge_samples": {
                    "root": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                },
            },
            {
                "id": "root_patch",
                "face_family": "blade_root",
                "component_of": "blade_0_root_annular_surface",
                "geometry_patch_version": "1.0.4",
                "role": "pressure_root_patch",
                "v1_0_4_root_quality": {
                    "max_parameter_direction_flip_deg": 0.0,
                },
                "uv_grid": [
                    [[0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [2.0, 0.0, 2.0]],
                    [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [2.0, 0.0, 1.0]],
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                ],
                "edge_samples": {
                    "blade_inner_loop": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                },
            },
        ],
        "topology_graph": {
            "shared_edges": [
                {
                    "id": "shared_edge_proxy_case",
                    "first_face_id": "blade_pressure",
                    "first_edge_role": "root",
                    "second_face_id": "root_patch",
                    "second_edge_role": "blade_inner_loop",
                    "orientation": "same",
                }
            ]
        },
    }

    summary = measure_v10_4_continuity(graph)
    measurement = summary["edge_measurements"][0]

    assert summary["status"] == "FAIL"
    assert measurement["status"] == "G1_MEASURED_G2_FAILED"
    assert measurement["normal_angle_kind"] == "adjacent_surface_uv_grid_frame"
    assert measurement["normal_angle_deg"] > 5.0


def test_non_v10_4_surface_graph_omits_v10_4_quality_fields() -> None:
    runtime = historical_v10_3_open_runtime()
    parameters = _bind_parameters(runtime, {})
    graph = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]

    assert graph["geometry_patch_version"] == "1.0.3"
    assert "v1_0_4_continuity_summary" not in graph
    assert "v1_0_4_angle_quality" not in graph
