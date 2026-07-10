from __future__ import annotations

import sys
from copy import deepcopy
from math import dist
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    build_parameter_inspection_contract,
    parameter_inspection_generation_id,
    validate_parameter_inspection_contract,
)
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def graph_for(preset_id: str = "radial_open_reference_v1_1") -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def thickness_parameter(contract: dict) -> dict:
    return next(item for item in contract["parameters"] if item["parameter_id"].endswith("thickness"))


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

    parameter = thickness_parameter(contract)
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


def test_station_thickness_measures_generated_pressure_and_suction_samples():
    contract = graph_for()["parameter_inspection"]
    parameter = thickness_parameter(contract)
    loop = contract["section_loops"][parameter["selection_scope"]["section_loop_id"]]
    pressure = loop["segment_references"]["pressure_side"]["display_points_s_q_mm"]
    suction = loop["segment_references"]["suction_side"]["display_points_s_q_mm"]
    expected_endpoints = [pressure[len(pressure) // 2], suction[len(suction) // 2]]
    definition = parameter["dimension_definition"]

    assert definition["measurement_points"] == expected_endpoints
    assert parameter["resolved_value"] == dist(*expected_endpoints)
    assert {tuple(point) for point in expected_endpoints} <= {
        tuple(feature["coordinates"])
        for feature in parameter["feature_geometry"]
        if feature["kind"] == "point"
    }


def test_validator_rejects_invalid_parameter_groups_and_records():
    graph = graph_for()
    contract = graph["parameter_inspection"]

    mutations = [
        lambda value: value["parameter_groups"][0].pop("label"),
        lambda value: value["parameters"][0].pop("label"),
        lambda value: value["parameters"][0].pop("selection_scope"),
        lambda value: value["parameters"][0].update(group_id="unknown"),
        lambda value: value["parameters"][1].update(parameter_id=value["parameters"][0]["parameter_id"]),
        lambda value: value["parameters"][0].update(applicable_views=[]),
        lambda value: value["parameters"][0]["feature_geometry"][0].update(kind="surface"),
        lambda value: value["parameters"][0]["feature_geometry"][0].update(id=value["parameters"][1]["feature_geometry"][0]["id"]),
        lambda value: value["parameters"][0].update(resolved_value=float("nan")),
        lambda value: value["parameters"][0]["feature_geometry"][0]["control_points"][0].__setitem__(0, float("nan")),
        lambda value: thickness_parameter(value)["dimension_definition"].update(kind="unsupported"),
        lambda value: thickness_parameter(value)["dimension_definition"].pop("measurement_points"),
        lambda value: thickness_parameter(value)["dimension_definition"]["measurement_points"][1].append(0.0),
    ]

    for mutate in mutations:
        malformed = deepcopy(contract)
        mutate(malformed)
        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_empty_blade_station_list_emits_a_valid_contract_without_root_attachment():
    graph = graph_for()
    graph["blade_to_blade_loop_family"]["blades"][0]["loops"] = []
    graph["generation_id"] = parameter_inspection_generation_id(graph)
    contract = build_parameter_inspection_contract(graph)

    graph["parameter_inspection"] = contract
    assert contract["blade_instances"]["blade_0"]["span_station_ids"] == []
    assert not any(
        parameter["parameter_id"] == "blade:blade_0:attachment:root_offset"
        for parameter in contract["parameters"]
    )
    assert validate_parameter_inspection_contract(graph, contract) == []


def test_validator_accepts_legacy_contract_without_additive_engineering_records():
    graph = graph_for()
    legacy_contract = deepcopy(graph["parameter_inspection"])
    del legacy_contract["parameter_groups"]
    del legacy_contract["parameters"]

    assert validate_parameter_inspection_contract(graph, legacy_contract) == []

    malformed_contract = deepcopy(graph["parameter_inspection"])
    del malformed_contract["parameters"]
    assert validate_parameter_inspection_contract(graph, malformed_contract) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]
