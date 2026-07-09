from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from tests.impeller_v10_3_historical_fixture import historical_v10_3_open_runtime


def test_v10_open_v10_3_uses_legacy_nurbs_math_as_a_carrier_not_as_final_graph():
    runtime = historical_v10_3_open_runtime()
    parameters = _bind_parameters(runtime, {})

    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    graph = metadata["surface_graph"]

    assert graph["geometry_patch_version"] == "1.0.3"
    assert graph["surface_graph_status"] == "PASS"
    assert graph["source_kernel"] == "v1_0_3_section_loop_topology_kernel"
    assert graph["carrier_source_kernel"] == "axisymmetric_throughflow_nurbs_kernel"
    assert graph["source_math_policy"] == "section_loop_first_nurbs_carrier_blade_faces_segmented_root_blends_open_tip_domes"
    assert graph["surfaces"]


def test_v10_open_v10_3_emits_real_hub_and_blade_faces():
    runtime = historical_v10_3_open_runtime()
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    graph = metadata["surface_graph"]
    surface_ids = {surface["id"] for surface in graph["surfaces"]}

    assert graph["surface_graph_status"] == "PASS"
    assert "hub_support_surface" in surface_ids
    assert "hub_revolve_surface" not in surface_ids
    assert "blade_0_pressure_surface" in surface_ids
    assert "blade_0_tip_dome_surface" in surface_ids
    assert graph["sampled_blades"]
