from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.service import RuleSynthesisService


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
