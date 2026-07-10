from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def graph_for(preset_id: str = "radial_open_reference_v1_1") -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_contract_exposes_engineering_groups_and_primitives():
    contract = graph_for()["parameter_inspection"]

    required_groups = {
        "hub",
        "tip_or_shroud",
        "blade_placement",
        "spanwise_pose",
        "section_loop",
        "attachments",
        "inspection_results",
    }
    assert required_groups <= {group["group_id"] for group in contract["parameter_groups"]}

    parameter = next(item for item in contract["parameters"] if item["parameter_id"].endswith("thickness"))
    assert parameter["applicable_views"] == ["s_q", "blade_3d"]
    assert {item["kind"] for item in parameter["feature_geometry"]} >= {"point", "local_frame"}
    assert parameter["dimension_definition"]["kind"] == "linear"

    primitive_ids = [
        primitive["id"]
        for item in contract["parameters"]
        for primitive in item["feature_geometry"]
    ]
    parameter_ids = [item["parameter_id"] for item in contract["parameters"]]
    assert len(primitive_ids) == len(set(primitive_ids))
    assert len(parameter_ids) == len(set(parameter_ids))
