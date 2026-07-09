from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph


def _surface_graph() -> dict:
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
    return {
        "transition_geometry_status": "topology_first_closed_nurbs_impeller_surface_graph",
        "surfaces": network["faces"],
        "topology_graph": topology,
    }


def test_v10_validation_passes_native_named_faces_and_shared_edges():
    report = build_geometry_validation_report(surface_graph=_surface_graph())

    assert report["geometry_validation_status"] == "PASS"


def test_v10_validation_rejects_missing_named_blade_face():
    graph = _surface_graph()
    graph["surfaces"] = [surface for surface in graph["surfaces"] if surface["id"] != "blade_0_tip_surface"]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_missing_named_blade_face" for f in report["blocking_failures"])


def test_v10_validation_rejects_legacy_transition_geometry_fields():
    graph = deepcopy(_surface_graph())
    graph["surfaces"][0]["transition_geometry"] = {"kind": "legacy_patch"}

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_transition_geometry_field_forbidden" for f in report["blocking_failures"])


def test_v10_validation_rejects_synthetic_shared_edges():
    graph = deepcopy(_surface_graph())
    graph["topology_graph"]["synthetic_shared_edge_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_synthetic_shared_edge_forbidden" for f in report["blocking_failures"])
