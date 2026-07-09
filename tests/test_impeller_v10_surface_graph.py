from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def test_v10_open_runtime_generates_current_v10_surface_graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    graph = metadata["surface_graph"]

    assert graph["geometry_patch_version"] == "1.0.4"
    assert (
        graph["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert graph["surface_graph_status"] == "PASS"
    assert graph["section_loop_constructor_status"] == "PASS"
    assert graph["v1_0_4_transition_failure_count"] == 0
    assert graph["surfaces"]
    assert graph["main_blade_count"] == 6
    assert graph["splitter_blade_count"] == 6
