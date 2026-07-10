from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph
from part_rule_synthesis.service import RuleSynthesisService

ACTIVE_V11_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def _graph(preset_id: str = "radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_v112_surface_graph_preserves_v11_face_family_roles():
    graph = _graph()
    roles = {surface["role"] for surface in graph["surfaces"]}

    assert graph["geometry_patch_version"] == "1.1.2"
    assert graph["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
    assert graph["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"
    assert "blade_pressure" in roles
    assert "blade_suction" in roles
    assert "blade_leading_edge" in roles
    assert "blade_trailing_edge" in roles
    assert "root_to_hub_attachment" in roles
    assert "open_tip_dome" in roles


def test_v112_service_manifest_exposes_canonical_parameterization(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_1")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]

    assert manifest["geometry_patch_version"] == "1.1.2"
    assert graph["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"
    assert graph["canonical_metrics"]["thickness_min_mm"] > 0.0
    assert manifest["geometry_validation_status"] == "PASS"


def test_v112_service_retranslates_canonical_payload_from_instantiated_scalar_edits(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_1")
    baseline = service.instantiate(engine.engine_id, {}).manifest["geometry"]["surface_graph"]
    edited = service.instantiate(engine.engine_id, {"blade_thickness_mm": 32.0}).manifest["geometry"]["surface_graph"]

    assert edited["canonical_metrics"]["thickness_max_mm"] != baseline["canonical_metrics"]["thickness_max_mm"]
    assert edited["canonical_metrics"]["thickness_max_mm"] == 32.0
    assert _first_loop_side_thickness(edited) > _first_loop_side_thickness(baseline)


def test_v112_validation_rejects_infeasible_active_span_offsets():
    graph = _graph()
    graph["blade_to_blade_loop_family"]["active_span_policy_metrics"]["offset_feasibility_status"] = "FAIL"

    assert "v1_1_2_active_span_offset_infeasible" in _failure_reasons(graph)


def test_v112_validation_rejects_invalid_canonical_nurbs_fields():
    graph = _graph()
    graph["canonical_nurbs_parameterization"]["thickness_field"] = {"kind": "nurbs_surface", "control_points": "bad"}

    assert "v1_1_2_invalid_canonical_nurbs_field" in _failure_reasons(graph)


def test_v112_validation_rejects_population_mismatch():
    graph = _graph()
    graph["canonical_nurbs_parameterization"]["blade_population"]["splitter_blade_count"] += 1

    assert "v1_1_2_population_mismatch" in _failure_reasons(graph)


def test_v112_validation_rejects_unresolved_cap_sagitta():
    graph = _graph()
    graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]["segments"]["leading_edge"]["canonical_curve"][
        "resolved_sagitta_mm"
    ] = 0.0

    assert "v1_1_2_cap_sagitta_unresolved" in _failure_reasons(graph)


def test_all_active_v112_preset_graphs_validate_pass():
    for preset_id in ACTIVE_V11_PRESETS:
        graph = _graph(preset_id)
        assert validate_v11_surface_graph(graph) == [], preset_id


def _failure_reasons(graph):
    return {failure["reason"] for failure in validate_v11_surface_graph(graph)}


def _first_loop_side_thickness(graph):
    loop = graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]
    pressure = loop["segments"]["pressure_side"]["points_s_q"]
    suction = loop["segments"]["suction_side"]["points_s_q"]
    sample_index = len(pressure) // 2
    return suction[sample_index][1] - pressure[sample_index][1]
