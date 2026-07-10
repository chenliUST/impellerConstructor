from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_3_parameter_inspection import parameter_inspection_generation_id
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def graph_for(preset_id="radial_open_reference_v1_1", edits=None):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    parameters.update(edits or {})
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_contract_has_release_and_geometry_provenance():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    assert contract["contract_version"] == "1.1.3"
    assert contract["source_geometry_patch_version"] == "1.1.2"
    assert contract["source_canonical_payload_version"] == "1.1.2"
    assert contract["generation_id"] == graph["generation_id"]


def test_contract_references_existing_surfaces_and_actual_loops():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    surface_ids = {surface["id"] for surface in graph["surfaces"]}
    assert set(contract["surface_references"]) == surface_ids
    station = next(iter(contract["span_stations"].values()))
    loop = contract["section_loops"][station["section_loop_id"]]
    assert loop["source_blade_index"] == station["source_blade_index"]
    assert loop["source_loop_index"] == station["source_loop_index"]
    assert set(loop["segment_references"]) == {
        "pressure_side", "suction_side", "leading_edge", "trailing_edge"
    }
    thickness = contract["resolved_dimensions"]["thickness_min_mm"]
    assert thickness["unit"] == "mm"
    assert thickness["requested_value"] is not None
    assert thickness["resolved_value"] == graph["canonical_metrics"]["thickness_min_mm"]


def test_generation_id_is_deterministic_and_geometry_sensitive():
    baseline_a = graph_for()
    baseline_b = graph_for()
    edited = deepcopy(baseline_a)
    edited["surfaces"][0]["uv_grid"][0][0][0] += 0.125
    assert baseline_a["generation_id"] == baseline_b["generation_id"]
    assert parameter_inspection_generation_id(edited) != baseline_a["generation_id"]


def test_all_active_presets_emit_contracts():
    for preset_id in ACTIVE_PRESETS:
        graph = graph_for(preset_id)
        assert graph["parameter_inspection"]["contract_version"] == "1.1.3", preset_id
        assert graph["parameter_inspection"]["blade_instances"], preset_id
