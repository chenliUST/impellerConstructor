from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network
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
