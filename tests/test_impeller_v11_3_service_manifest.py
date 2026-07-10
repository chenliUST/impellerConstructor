from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph
from part_rule_synthesis.service import RuleSynthesisService


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def graph_for(preset_id: str = "radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_service_manifest_separates_runtime_and_geometry_versions(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_1")
    manifest = service.instantiate(engine.engine_id, {}).manifest

    assert manifest["runtime_release_version"] == "1.1.3"
    assert manifest["parameter_inspection_contract_version"] == "1.1.3"
    assert manifest["geometry_patch_version"] == "1.1.2"
    assert (
        manifest["geometry"]["surface_graph"]["canonical_nurbs_parameterization"]["canonical_payload_version"]
        == "1.1.2"
    )
    assert manifest["generation_id"] == manifest["parameter_inspection"]["generation_id"]


def test_validation_rejects_missing_surface_reference():
    graph = graph_for()
    surface_id = next(iter(graph["parameter_inspection"]["surface_references"]))
    del graph["parameter_inspection"]["surface_references"][surface_id]

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_surface_reference_missing" in reasons


def test_validation_rejects_generation_mismatch():
    graph = graph_for()
    graph["parameter_inspection"]["generation_id"] = "stale"

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_generation_id_mismatch" in reasons


def test_validation_rejects_geometry_mutation_with_stored_generation_ids():
    graph = deepcopy(graph_for())
    graph["surfaces"][0]["uv_grid"][0][0][0] += 0.125

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_generation_id_mismatch" in reasons


def test_validation_rejects_non_mapping_surface_references():
    graph = graph_for()
    graph["parameter_inspection"]["surface_references"] = []

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_contract_unsupported" in reasons


def test_validation_rejects_non_mapping_span_stations():
    graph = graph_for()
    graph["parameter_inspection"]["span_stations"] = []

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_contract_unsupported" in reasons


def test_validation_rejects_non_mapping_section_loops():
    graph = graph_for()
    graph["parameter_inspection"]["section_loops"] = []

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_contract_unsupported" in reasons


def test_validation_rejects_malformed_section_loop_entry():
    graph = graph_for()
    loop_id = next(iter(graph["parameter_inspection"]["section_loops"]))
    graph["parameter_inspection"]["section_loops"][loop_id] = []

    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

    assert "parameter_inspection_contract_unsupported" in reasons


def test_validation_rejects_malformed_nested_contract_values():
    baseline = graph_for()
    loop_id = next(iter(baseline["parameter_inspection"]["section_loops"]))

    for malformed_station_id in ([], {}):
        graph = deepcopy(baseline)
        graph["parameter_inspection"]["section_loops"][loop_id]["span_station_id"] = malformed_station_id

        reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}

        assert "parameter_inspection_contract_unsupported" in reasons


def test_all_active_presets_expose_service_inspection_contracts(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    for preset_id in ACTIVE_PRESETS:
        engine = service.synthesize("impeller", preset_id=preset_id)
        manifest = service.instantiate(engine.engine_id, {}).manifest

        assert manifest["parameter_inspection_contract_version"] == "1.1.3", preset_id
        assert manifest["parameter_inspection"]["generation_id"] == manifest["generation_id"], preset_id
