from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network
from part_rule_synthesis import impeller_v10_topology_graph as topology_module
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph


def test_v10_topology_graph_registers_shared_edges_from_constructor_faces():
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
    topology = build_v10_topology_graph(network["faces"])

    assert topology["topology_status"] == "PASS"
    assert topology["shared_edge_count"] >= 8
    assert topology["synthetic_shared_edge_count"] == 0
    assert topology["max_shared_edge_gap_mm"] <= 1.0e-9


def test_v10_topology_graph_endpoint_index_preserves_tolerance_boundary_matches():
    faces = [
        {
            "id": "first",
            "edge_samples": {
                "shared": [[0.49e-9, 0.0, 0.0], [1.0, 0.0, 0.0]]
            },
        },
        {
            "id": "second",
            "edge_samples": {
                "shared": [[-0.49e-9, 0.0, 0.0], [1.0, 0.0, 0.0]]
            },
        },
    ]

    topology = build_v10_topology_graph(faces)

    assert topology["shared_edge_count"] == 1
    assert topology["shared_edges"][0]["max_gap_mm"] == 0.98e-9


def test_v10_topology_graph_does_not_compare_spatially_disjoint_edges(monkeypatch):
    faces = [
        {
            "id": f"face-{index}",
            "edge_samples": {
                "edge": [
                    [10.0 * index, 0.0, 0.0],
                    [10.0 * index + 1.0, 0.0, 0.0],
                ]
            },
        }
        for index in range(1000)
    ]
    call_count = 0
    original = topology_module._match_edges

    def counted_match(first, second):
        nonlocal call_count
        call_count += 1
        return original(first, second)

    monkeypatch.setattr(topology_module, "_match_edges", counted_match)

    topology = build_v10_topology_graph(faces)

    assert topology["shared_edge_count"] == 0
    assert call_count == 0
