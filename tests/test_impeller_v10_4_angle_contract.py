from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v10_4_continuity import measure_v10_4_blade_hub_angles
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


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


def test_v10_4_blade_hub_angles_are_inspection_friendly() -> None:
    graph = _graph()
    quality = graph["v1_0_4_angle_quality"]

    assert quality["status"] == "PASS"
    assert quality["min_blade_hub_angle_deg"] >= 60.0
    assert quality["max_blade_hub_angle_deg"] <= 120.0
    assert quality["sample_count"] > 0


def test_v10_4_blade_hub_angle_quality_keeps_sample_metadata() -> None:
    graph = _graph()
    quality = graph["v1_0_4_angle_quality"]
    samples = quality["angle_samples"]

    assert len(samples) == quality["sample_count"]
    assert any(sample["interface"] == "blade_root_to_hub" for sample in samples)
    for sample in samples:
        assert sample["blade_face_id"]
        assert sample["hub_face_id"]
        assert sample["blade_edge_role"]
        assert sample["hub_edge_role"]
        assert 60.0 <= sample["angle_deg"] <= 120.0


def test_v10_4_blade_hub_angle_fails_zero_span_vectors() -> None:
    shared_loop = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
    graph = {
        "surfaces": [
            {
                "id": "blade_pressure",
                "face_family": "blade_pressure",
                "uv_grid": [
                    shared_loop,
                    [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 1.0, 0.0]],
                ],
                "edge_samples": {
                    "root": shared_loop,
                },
            },
            {
                "id": "root_patch",
                "face_family": "blade_root",
                "component_of": "blade_0_root_annular_surface",
                "geometry_patch_version": "1.0.4",
                "role": "pressure_root_patch",
                "uv_grid": [
                    shared_loop,
                    shared_loop,
                ],
                "edge_samples": {
                    "blade_inner_loop": shared_loop,
                    "hub_outer_loop": shared_loop,
                },
            },
        ],
        "topology_graph": {
            "shared_edges": [
                {
                    "id": "shared_edge_zero_span",
                    "first_face_id": "blade_pressure",
                    "first_edge_role": "root",
                    "second_face_id": "root_patch",
                    "second_edge_role": "blade_inner_loop",
                    "orientation": "same",
                }
            ]
        },
    }

    quality = measure_v10_4_blade_hub_angles(graph)

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_blade_hub_angle_degenerate_vector"
    assert quality["degenerate_sample_count"] == 3
    assert all(sample["status"] == "FAIL" for sample in quality["angle_samples"])
