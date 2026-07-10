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
    _measure_dimension,
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
        lambda value: thickness_parameter(value)["selection_scope"].update(span_station_id="missing_station"),
        lambda value: thickness_parameter(value)["dimension_definition"].update(
            measurement_points=[thickness_parameter(value)["dimension_definition"]["measurement_points"][0]] * 2
        ),
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


def test_open_and_closed_contracts_cover_constructor_parameters_with_generated_evidence():
    required_parameter_fragments = {
        "hub.profile.degree",
        "hub.profile.control.0.r",
        "hub.profile.control.0.z",
        "blade.main.count",
        "blade.angular_pitch",
        "blade.splitter.phase",
        "pose.station.0",
        "section:pressure_side:control:0",
        "section:suction_side:control:0",
        "section:leading_edge:sagitta",
        "section:trailing_edge:sagitta",
        "attachment:root:width",
        "attachment:root:lift",
    }

    for preset_id in ("radial_open_reference_v1_1", "radial_closed_reference_v1_1"):
        contract = graph_for(preset_id)["parameter_inspection"]
        parameter_ids = {parameter["parameter_id"] for parameter in contract["parameters"]}

        assert all(
            any(fragment in parameter_id for parameter_id in parameter_ids)
            for fragment in required_parameter_fragments
        ), preset_id

        control_parameters = [
            parameter
            for parameter in contract["parameters"]
            if ":control:" in parameter["parameter_id"] or ".profile.control." in parameter["parameter_id"]
        ]
        assert control_parameters, preset_id
        assert all(
            [feature["kind"] for feature in parameter["feature_geometry"]].count("control_point") == 1
            and parameter["dimension_definition"]["kind"] == "control_coordinate"
            for parameter in control_parameters
        ), preset_id

        if preset_id == "radial_closed_reference_v1_1":
            assert all(
                any(fragment in parameter_id for parameter_id in parameter_ids)
                for fragment in ("attachment:shroud:width", "attachment:shroud:lift", "shroud.thickness")
            )


def test_engineering_dimension_records_measure_generated_geometry_and_detect_mutation():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    parameter_by_fragment = {
        "thickness": thickness_parameter(contract),
        "sagitta": next(
            parameter for parameter in contract["parameters"] if ":leading_edge:sagitta" in parameter["parameter_id"]
        ),
        "angular": next(parameter for parameter in contract["parameters"] if parameter["parameter_id"] == "blade.angular_pitch"),
        "ordinate": next(
            parameter for parameter in contract["parameters"] if parameter["parameter_id"] == "hub.profile.control.0.r"
        ),
        "lift": next(parameter for parameter in contract["parameters"] if ":attachment:root:lift" in parameter["parameter_id"]),
    }

    for parameter in parameter_by_fragment.values():
        definition = parameter["dimension_definition"]
        assert abs(_measure_dimension(definition) - parameter["resolved_value"]) <= definition["tolerance"]

    malformed = deepcopy(contract)
    thickness_parameter(malformed)["dimension_definition"]["measurement_points"][1][0] += 1.0
    assert validate_parameter_inspection_contract(graph, malformed) == [
        {
            "reason": "parameter_inspection_dimension_value_mismatch",
            "parameter_id": thickness_parameter(contract)["parameter_id"],
        }
    ]


def test_runtime_advertises_additive_engineering_inspection_capabilities():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")

    assert runtime["geometry_version"] == "1.1"
    assert runtime["parameter_inspection_capabilities"] == [
        "engineering_feature_geometry",
        "engineering_dimensions",
        "s_q_blade_synchronized_selection",
    ]
