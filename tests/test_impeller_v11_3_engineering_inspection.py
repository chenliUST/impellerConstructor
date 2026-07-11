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


def parameter_by_id(contract: dict, parameter_id: str) -> dict:
    return next(item for item in contract["parameters"] if item["parameter_id"] == parameter_id)


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


def test_blade_features_carry_authoritative_xyz_alongside_s_q_display_geometry():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    source_loop = graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]
    station_id = contract["blade_instances"]["blade_0"]["span_station_ids"][0]
    loop = contract["section_loops"][contract["span_stations"][station_id]["section_loop_id"]]

    for segment_name, source_segment in source_loop["segments"].items():
        segment = loop["segment_references"][segment_name]
        assert segment["points_xyz"] == source_segment["points_xyz"]
        assert segment["display_points_s_q_mm"] == _metric_s_q_points_for_test(
            source_segment["points_s_q"], source_loop["streamwise_metric_scale_mm"]
        )

    sagitta = next(
        item
        for item in contract["parameters"]
        if item["parameter_id"].startswith(f"blade:blade_0:station:{station_id}")
        and item["parameter_id"].endswith(":leading_edge:sagitta")
    )
    feature = sagitta["feature_geometry"][0]
    assert feature["coordinate_system"] == "model_xyz"
    assert feature["points"] == source_loop["segments"]["leading_edge"]["points_xyz"]
    assert feature["display_points_s_q_mm"] == loop["segment_references"]["leading_edge"]["display_points_s_q_mm"]
    source_edge = source_loop["segments"]["leading_edge"]
    display_edge = loop["segment_references"]["leading_edge"]["display_points_s_q_mm"]
    sample_indices = [0, len(source_edge["points_xyz"]) - 1, len(source_edge["points_xyz"]) // 2]
    measurement_features = [
        item
        for item in sagitta["feature_geometry"]
        if item["kind"] == "point" and item["rendering_role"] == "selected_feature"
    ]
    assert [item["coordinates"] for item in measurement_features] == [
        source_edge["points_xyz"][index] for index in sample_indices
    ]
    assert [item["display_coordinates_s_q_mm"] for item in measurement_features] == [
        display_edge[index] for index in sample_indices
    ]

    thickness = thickness_parameter(contract)
    sample_index = min(
        len(source_loop["segments"]["pressure_side"]["points_xyz"]),
        len(source_loop["segments"]["suction_side"]["points_xyz"]),
    ) // 2
    selected_points = [
        feature
        for feature in thickness["feature_geometry"]
        if feature["kind"] == "point" and feature["rendering_role"] == "selected_feature"
    ]
    assert [feature["coordinates"] for feature in selected_points] == [
        source_loop["segments"]["pressure_side"]["points_xyz"][sample_index],
        source_loop["segments"]["suction_side"]["points_xyz"][sample_index],
    ]
    assert all(feature["coordinate_system"] == "model_xyz" for feature in selected_points)
    context = [
        feature
        for feature in thickness["feature_geometry"]
        if feature["rendering_role"] == "drawing_context"
    ]
    assert [(feature["source_segment_name"], feature["points"]) for feature in context] == [
        (segment_name, source_segment["points_xyz"])
        for segment_name, source_segment in source_loop["segments"].items()
    ]
    assert [feature["display_points_s_q_mm"] for feature in context] == [
        loop["segment_references"][segment_name]["display_points_s_q_mm"]
        for segment_name in source_loop["segments"]
    ]


def test_feature_coordinate_spaces_are_explicit_and_blade_applicability_requires_model_xyz():
    contract = graph_for()["parameter_inspection"]
    allowed_spaces = {"model_xyz", "s_q_mm", "profile_rz_mm"}
    allowed_roles = {"drawing_context", "selected_feature"}

    for parameter in contract["parameters"]:
        features = parameter["feature_geometry"]
        assert all(feature["coordinate_system"] in allowed_spaces for feature in features)
        assert all(feature["rendering_role"] in allowed_roles for feature in features)
        if "blade_3d" in parameter["applicable_views"]:
            selected = [feature for feature in features if feature["rendering_role"] == "selected_feature"]
            assert selected
            assert all(feature["coordinate_system"] == "model_xyz" for feature in selected)


def test_validator_rejects_view_incompatible_coordinate_spaces():
    graph = graph_for()
    contract = deepcopy(graph["parameter_inspection"])
    parameter = parameter_by_id(contract, "blade.angular_pitch")
    for feature in parameter["feature_geometry"]:
        feature["coordinate_system"] = "s_q_mm"

    assert validate_parameter_inspection_contract(graph, contract) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]


def test_attachment_parameters_expose_authoritative_boundary_context_and_selected_measurements():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    root_surface = next(surface for surface in graph["surfaces"] if surface.get("role") == "root_to_hub_attachment")
    parameter = parameter_by_id(contract, "blade:blade_0:attachment:root:lift")
    context = [
        feature for feature in parameter["feature_geometry"] if feature["rendering_role"] == "drawing_context"
    ]
    selected = [
        feature for feature in parameter["feature_geometry"] if feature["rendering_role"] == "selected_feature"
    ]

    assert [(feature["boundary_role"], feature["points"]) for feature in context] == [
        ("hub_side", root_surface["edge_samples"]["hub_outer_loop"]),
        ("blade_side", root_surface["edge_samples"]["blade_inner_loop"]),
    ]
    assert all(feature["coordinate_system"] == "model_xyz" for feature in context)
    assert [feature["coordinates"] for feature in selected] == [
        root_surface["uv_grid"][0][0],
        root_surface["uv_grid"][-1][0],
    ]


def test_top_and_meridional_context_come_from_generated_loop_and_profile_evidence():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    top_parameter = parameter_by_id(contract, "blade.main.count")
    top_context = [
        feature for feature in top_parameter["feature_geometry"] if feature["rendering_role"] == "drawing_context"
    ]
    expected_segment = graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]["segments"]["pressure_side"]

    assert top_context
    assert top_context[0]["coordinate_system"] == "model_xyz"
    assert top_context[0]["points"] == expected_segment["points_xyz"]

    profile_parameter = parameter_by_id(contract, "hub.profile.control.0.r")
    profile_context = [
        feature for feature in profile_parameter["feature_geometry"] if feature["rendering_role"] == "drawing_context"
    ]
    assert len(profile_context) == 1
    assert profile_context[0]["coordinate_system"] == "profile_rz_mm"
    assert profile_context[0]["control_points"] == contract["support_profiles"]["hub_profile"]["control_points"]


def test_validator_rejects_top_context_that_does_not_match_generated_loop_geometry():
    graph = graph_for()
    contract = deepcopy(graph["parameter_inspection"])
    parameter = parameter_by_id(contract, "blade.main.count")
    context = next(
        feature for feature in parameter["feature_geometry"] if feature["rendering_role"] == "drawing_context"
    )
    context["points"][0][0] += 123.0

    assert validate_parameter_inspection_contract(graph, contract) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]


def _metric_s_q_points_for_test(points: list[list[float]], scale: float) -> list[list[float]]:
    return [[float(point[0]) * float(scale), float(point[1])] for point in points]


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
        tuple(feature["display_coordinates_s_q_mm"])
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


def test_closed_shroud_width_is_measured_from_closed_attachment_geometry():
    contract = graph_for("radial_closed_reference_v1_1")["parameter_inspection"]
    parameter = next(
        parameter for parameter in contract["parameters"] if ":attachment:shroud:width" in parameter["parameter_id"]
    )

    assert parameter["selection_scope"]["source_attachment_measurement"] == "shroud_width"
    assert abs(_measure_dimension(parameter["dimension_definition"]) - parameter["resolved_value"]) <= parameter[
        "dimension_definition"
    ]["tolerance"]


def test_section_control_parameters_cover_every_generated_control_point():
    graph = graph_for()
    contract = graph["parameter_inspection"]

    expected_ids = set()
    for station_id, station in contract["span_stations"].items():
        blade_id = station["blade_instance_id"]
        loop = contract["section_loops"][station["section_loop_id"]]
        for segment_name, segment in loop["segment_references"].items():
            for index in range(len(segment["control_points"])):
                for axis in ("s", "q"):
                    expected_ids.add(
                        f"blade:{blade_id}:station:{station_id}:section:{segment_name}:control:{index}:{axis}"
                    )

    actual_ids = {
        parameter["parameter_id"]
        for parameter in contract["parameters"]
        if ":section:" in parameter["parameter_id"] and ":control:" in parameter["parameter_id"]
    }
    assert actual_ids == expected_ids


def test_validator_rejects_self_consistent_records_that_no_longer_match_source_geometry():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    parameter_ids = [
        next(parameter["parameter_id"] for parameter in contract["parameters"] if ":control:0:s" in parameter["parameter_id"]),
        "hub.profile.control.0.r",
        next(parameter["parameter_id"] for parameter in contract["parameters"] if ":pose.station.0" in parameter["parameter_id"]),
        next(parameter["parameter_id"] for parameter in contract["parameters"] if ":attachment:root:lift" in parameter["parameter_id"]),
    ]

    for parameter_id in parameter_ids:
        malformed = deepcopy(contract)
        parameter = next(item for item in malformed["parameters"] if item["parameter_id"] == parameter_id)
        if parameter["dimension_definition"] is None:
            parameter["resolved_value"] = float(parameter["resolved_value"]) + 0.1
            parameter["feature_geometry"][0]["origin"][0] += 0.1
        else:
            definition = parameter["dimension_definition"]
            if definition["kind"] == "control_coordinate":
                selected_feature = next(
                    feature
                    for feature in parameter["feature_geometry"]
                    if feature["rendering_role"] == "selected_feature"
                )
                selected_feature["coordinates"][0] += 1.0
                definition["measurement_points"][1][0] += 1.0
                parameter["resolved_value"] = _measure_dimension(definition)
            else:
                parameter["feature_geometry"][-1]["coordinates"][0] += 1.0
                definition["measurement_points"][1][0] += 1.0
                parameter["resolved_value"] = _measure_dimension(definition)

        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_validator_rejects_angular_dimension_vectors_with_different_dimensions():
    graph = graph_for()
    malformed = deepcopy(graph["parameter_inspection"])
    parameter = next(item for item in malformed["parameters"] if item["parameter_id"] == "blade.angular_pitch")
    parameter["dimension_definition"]["measured_direction"].append(0.0)

    assert validate_parameter_inspection_contract(graph, malformed) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]


def test_validator_binds_loop_evidence_to_generated_graph_not_mutable_contract_loops():
    graph = graph_for()
    malformed = deepcopy(graph["parameter_inspection"])
    parameter = next(item for item in malformed["parameters"] if ":control:0:s" in item["parameter_id"])
    scope = parameter["selection_scope"]
    loop = malformed["section_loops"][scope["section_loop_id"]]
    segment = next(
        segment
        for segment in loop["segment_references"].values()
        if segment["section_segment_id"] == scope["section_segment_id"]
    )
    source = next(
        record for record in segment["control_points"] if record["control_point_id"] == scope["source_control_point_id"]
    )
    source["display_coordinates_s_q_mm"][0] += 1.0
    segment["display_control_points_s_q_mm"][0][0] += 1.0
    parameter["feature_geometry"][0]["coordinates"][0] += 1.0
    parameter["dimension_definition"]["measurement_points"][1][0] += 1.0
    parameter["resolved_value"] = _measure_dimension(parameter["dimension_definition"])

    assert validate_parameter_inspection_contract(graph, malformed) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]


def test_validator_binds_placement_shroud_and_sagitta_features_to_generated_graph():
    graph = graph_for("radial_closed_reference_v1_1")
    contract = graph["parameter_inspection"]
    mutations = [
        lambda parameter: parameter.update(resolved_value=parameter["resolved_value"] + 1),
        lambda parameter: (
            parameter["feature_geometry"][1].update(direction=[0.0, 1.0]),
            parameter["dimension_definition"].update(measured_direction=[0.0, 1.0]),
            parameter.update(resolved_value=_measure_dimension(parameter["dimension_definition"])),
        ),
        lambda parameter: (
            parameter["feature_geometry"][1]["coordinates"].__setitem__(0, parameter["feature_geometry"][1]["coordinates"][0] + 1),
            parameter["dimension_definition"]["measurement_points"][1].__setitem__(0, parameter["dimension_definition"]["measurement_points"][1][0] + 1),
            parameter.update(resolved_value=_measure_dimension(parameter["dimension_definition"])),
        ),
        lambda parameter: parameter["feature_geometry"][0]["points"].__setitem__(1, [999.0, 999.0]),
    ]
    parameter_ids = [
        "blade.main.count",
        "blade.angular_pitch",
        "shroud.thickness",
        next(item["parameter_id"] for item in contract["parameters"] if ":leading_edge:sagitta" in item["parameter_id"]),
    ]

    for parameter_id, mutate in zip(parameter_ids, mutations):
        malformed = deepcopy(contract)
        mutate(next(item for item in malformed["parameters"] if item["parameter_id"] == parameter_id))
        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_validator_rejects_selector_identity_swaps_with_valid_generated_geometry():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    parameter_id = next(item["parameter_id"] for item in contract["parameters"] if ":control:0:s" in item["parameter_id"])

    for key, replacement in (
        ("source_station_index", 1),
        ("source_segment_name", "suction_side"),
        ("source_control_index", 1),
    ):
        malformed = deepcopy(contract)
        parameter = next(item for item in malformed["parameters"] if item["parameter_id"] == parameter_id)
        parameter["selection_scope"][key] = replacement
        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_validator_binds_join_results_and_placement_feature_primitives():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    mutations = [
        lambda parameter: parameter["feature_geometry"][0]["points"].__setitem__(1, [123.0, 456.0]),
        lambda parameter: parameter["feature_geometry"][0].update(direction=[0.0, 1.0]),
        lambda parameter: parameter["feature_geometry"][0].update(direction=[0.0, 1.0]),
    ]
    parameter_ids = [
        next(item["parameter_id"] for item in contract["parameters"] if item["parameter_id"].endswith("join_status")),
        "blade.main.count",
        "blade.angular_pitch",
    ]

    for parameter_id, mutate in zip(parameter_ids, mutations):
        malformed = deepcopy(contract)
        mutate(next(item for item in malformed["parameters"] if item["parameter_id"] == parameter_id))
        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_validator_rejects_cross_profile_provenance_and_degree_value_mutations():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    mutations = [
        ("hub.profile.control.0.r", lambda parameter: parameter["selection_scope"].update(source_profile_id="tip_or_shroud_profile")),
        ("hub.profile.degree", lambda parameter: parameter.update(resolved_value=parameter["resolved_value"] + 1)),
    ]

    for parameter_id, mutate in mutations:
        malformed = deepcopy(contract)
        mutate(next(item for item in malformed["parameters"] if item["parameter_id"] == parameter_id))
        assert validate_parameter_inspection_contract(graph, malformed) == [
            {"reason": "parameter_inspection_contract_unsupported"}
        ]


def test_validator_rejects_cross_blade_attachment_surface_provenance():
    graph = graph_for("radial_closed_reference_v1_1")
    contract = graph["parameter_inspection"]
    parameter = next(item for item in contract["parameters"] if ":attachment:shroud:width" in item["parameter_id"])
    malformed = deepcopy(contract)
    target = next(item for item in malformed["parameters"] if item["parameter_id"] == parameter["parameter_id"])
    target["selection_scope"]["source_attachment_surface_id"] = "blade_1_closed_shroud_attachment_surface"

    assert validate_parameter_inspection_contract(graph, malformed) == [
        {"reason": "parameter_inspection_contract_unsupported"}
    ]
