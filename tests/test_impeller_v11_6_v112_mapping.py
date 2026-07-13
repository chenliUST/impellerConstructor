from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset  # noqa: E402
from part_rule_synthesis.impeller_v11_2_canonical import (  # noqa: E402
    canonical_nurbs_from_v11_defaults,
    clamped_uniform_knots,
    evaluate_nurbs_curve,
    evaluate_nurbs_surface,
)
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (  # noqa: E402
    build_v11_blade_to_blade_loop_family,
)
from part_rule_synthesis.impeller_v11_6_section_recovery import (  # noqa: E402
    SectionSegmentMeasurement,
    fit_nurbs_measurement_curve,
)
import part_rule_synthesis.impeller_v11_6_v112_mapping as mapping_module  # noqa: E402
from part_rule_synthesis.impeller_v11_6_v112_mapping import (  # noqa: E402
    CANONICAL_STATIONS_H,
    GEOMETRY_PATCH_VERSION,
    MEASUREMENT_SCHEMA_VERSION,
    V112MappingError,
    V112MappingTolerances,
    adapt_task3_frame_for_mapping,
    adapt_task7_segment_for_mapping,
    map_measurements_to_v112,
)


ACTIVE_V112_PRESETS = (
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
)

_COMMON_REJECTION_EVIDENCE_KEYS = {
    "frame",
    "provenance",
    "promotion",
    "tolerances",
    "solver",
    "bounds",
    "candidate",
    "objective_terms",
    "passed_terms",
    "failed_terms",
    "passing_terms",
    "failing_terms",
}


def test_exact_five_and_nine_station_measurements_map_to_same_fixed_v112_payload():
    five = map_measurements_to_v112(
        _measurement_bundle(station_count=5), tolerances=V112MappingTolerances()
    )
    nine = map_measurements_to_v112(
        _measurement_bundle(station_count=9), tolerances=V112MappingTolerances()
    )

    assert five["mapping_status"] == "PASS"
    assert five["geometry_patch_version"] == "1.1.2"
    assert five["resolved_blade_to_blade_loop_family_defaults"]["span_stations_h"] == list(
        CANONICAL_STATIONS_H
    )
    assert nine["resolved_blade_to_blade_loop_family_defaults"]["span_stations_h"] == list(
        CANONICAL_STATIONS_H
    )
    assert five["canonical_payload_hash_sha256"] == nine["canonical_payload_hash_sha256"]
    assert five["constructor_input_hash_sha256"] == nine["constructor_input_hash_sha256"]
    assert five["tolerances"]["mean_thickness_mm"] == nine["tolerances"]["mean_thickness_mm"]
    assert five["tolerances"]["span_quadrature_weights"] == [0.125, 0.25, 0.25, 0.25, 0.125]
    assert five["five_station_resampling_report"]["families"]["main"]["source_station_count"] == 5
    assert nine["five_station_resampling_report"]["families"]["main"]["source_station_count"] == 9
    assert all(term["gate"]["status"] == "PASS" for term in five["objective_terms"].values())


def test_fixed_five_station_gates_are_station_count_invariant_and_adaptive_loss_is_diagnostic():
    failures = []
    for station_count in (5, 9):
        bundle = _measurement_bundle(station_count=station_count)
        mid = next(
            station
            for station in bundle["section_families"]["main"]["stations"]
            if station["h"] == pytest.approx(0.5)
        )
        mid["camber"]["samples"][3]["q_mm"] += 8.0
        with pytest.raises(V112MappingError) as captured:
            map_measurements_to_v112(bundle, tolerances={})
        failures.append(captured.value.details["failed_terms"])
    assert failures[0] == failures[1]
    assert "camber" in failures[0]

    adaptive_only = _measurement_bundle(station_count=9)
    adaptive_only["section_families"]["main"]["stations"][1]["camber"]["samples"][3][
        "q_mm"
    ] += 4.0
    result = map_measurements_to_v112(adaptive_only, tolerances={})
    assert result["mapping_status"] == "PASS"
    assert result["five_station_resampling_report"]["adaptive_station_loss"]["camber_rms_mm"] > 0.0
    assert result["five_station_resampling_report"]["adaptive_station_loss"]["used_for_promotion"] is False


def test_adaptive_terminal_samples_cannot_change_promoted_constructor_or_hashes():
    baseline_bundle = _measurement_bundle(
        station_count=9, mode="closed", main_count=6, splitter_count=6
    )
    mutated_bundle = copy.deepcopy(baseline_bundle)
    for family in mutated_bundle["section_families"].values():
        for station in family["stations"]:
            if station["h"] in {0.125, 0.375, 0.625, 0.875}:
                samples = station["camber"]["samples"]
                samples[0]["q_mm"] += 20.0
                samples[-1]["q_mm"] -= 20.0

    baseline = map_measurements_to_v112(baseline_bundle, tolerances={})
    mutated = map_measurements_to_v112(mutated_bundle, tolerances={})

    assert mutated["parameters"] == baseline["parameters"]
    assert mutated["resolved_blade_to_blade_loop_family_defaults"] == baseline[
        "resolved_blade_to_blade_loop_family_defaults"
    ]
    assert mutated["constructor_input_hash_sha256"] == baseline[
        "constructor_input_hash_sha256"
    ]
    assert mutated["canonical_payload_hash_sha256"] == baseline[
        "canonical_payload_hash_sha256"
    ]
    assert mutated["five_station_resampling_report"]["adaptive_station_loss"][
        "camber_rms_mm"
    ] > baseline["five_station_resampling_report"]["adaptive_station_loss"][
        "camber_rms_mm"
    ]


def test_edge_promotion_uses_only_fixed_five_stations_and_adaptive_edges_are_diagnostic():
    baseline = map_measurements_to_v112(
        _measurement_bundle(station_count=9), tolerances={}
    )
    adaptive_only = _measurement_bundle(station_count=9)
    target = adaptive_only["section_families"]["main"]["stations"][1][
        "decomposition"
    ]["segments"]["leading_edge"]["nurbs_target"]
    target["control_points_local_mm"][len(target["control_points_local_mm"]) // 2][
        0
    ] -= 4.0
    target["sample_points_local_mm"] = _evaluate_target_samples(
        target, len(target["sample_points_local_mm"])
    )
    _refresh_edge_fit_evidence(
        adaptive_only["section_families"]["main"]["stations"][1][
            "decomposition"
        ]["segments"]["leading_edge"],
        "leading_edge",
    )

    result = map_measurements_to_v112(adaptive_only, tolerances={})

    assert result["mapping_status"] == "PASS"
    assert result["constructor_input_hash_sha256"] == baseline[
        "constructor_input_hash_sha256"
    ]
    edge = result["objective_terms"]["edge_curves"]
    assert {record["h"] for record in edge["records"]} == set(CANONICAL_STATIONS_H)
    assert edge["gate"] == baseline["objective_terms"]["edge_curves"]["gate"]
    adaptive_loss = result["five_station_resampling_report"][
        "adaptive_station_loss"
    ]
    assert adaptive_loss["edge_maximum_bidirectional_hausdorff_mm"] > baseline[
        "five_station_resampling_report"
    ]["adaptive_station_loss"]["edge_maximum_bidirectional_hausdorff_mm"]
    assert adaptive_loss["used_for_promotion"] is False


def test_mapping_is_deterministic_under_input_order_source_sha_and_initial_guess_changes():
    source = _measurement_bundle(station_count=7)
    first = map_measurements_to_v112(
        source,
        tolerances={},
        initial_guess={
            "source_preset_id": "seed-a",
            "parameters": {"blade_wrap_deg": -120.0, "blade_thickness_mm": 9.0},
            "defaults": {"main_flow_turn_q_mm": 35.0},
        },
    )

    reordered = copy.deepcopy(source)
    reordered["provenance"]["source_sha256"] = "b" * 64
    reordered["provenance"]["source_entity_ids"].reverse()
    reordered["section_families"]["main"]["stations"].reverse()
    for station in reordered["section_families"]["main"]["stations"]:
        station["camber"]["samples"].reverse()
        station["pose"]["samples"].reverse()
        station["normal_thickness"]["samples"].reverse()
    second = map_measurements_to_v112(
        reordered,
        tolerances={},
        initial_guess={
            "source_preset_id": "seed-b",
            "parameters": {"blade_wrap_deg": 140.0, "blade_thickness_mm": 2.0},
            "defaults": {"main_flow_turn_q_mm": 5.0},
        },
    )

    assert first["parameters"] == second["parameters"]
    assert first["resolved_blade_to_blade_loop_family_defaults"] == second[
        "resolved_blade_to_blade_loop_family_defaults"
    ]
    assert first["canonical_payload_hash_sha256"] == second["canonical_payload_hash_sha256"]
    assert first["constructor_input_hash_sha256"] == second["constructor_input_hash_sha256"]
    assert first["provenance"]["source"]["source_sha256"] != second["provenance"]["source"]["source_sha256"]


def test_orientation_neutral_side_swap_is_geometry_invariant():
    original = _measurement_bundle(station_count=5)
    swapped = copy.deepcopy(original)
    for family in swapped["section_families"].values():
        for station in family["stations"]:
            segments = station["decomposition"]["segments"]
            segments["side_a"], segments["side_b"] = segments["side_b"], segments["side_a"]

    first = map_measurements_to_v112(original, tolerances={})
    second = map_measurements_to_v112(swapped, tolerances={})

    assert first["constructor_input_hash_sha256"] == second["constructor_input_hash_sha256"]
    assert first["canonical_payload_hash_sha256"] == second["canonical_payload_hash_sha256"]
    assert all(
        station["decomposition"]["pressure_suction_assigned"] is False
        for station in swapped["section_families"]["main"]["stations"]
    )


def test_uniform_thickness_change_only_updates_documented_coupled_fields():
    baseline_bundle = _measurement_bundle(station_count=5)
    thicker_bundle = _measurement_bundle(station_count=5, average_thickness_mm=5.0, maximum_thickness_mm=6.0)
    baseline = map_measurements_to_v112(baseline_bundle, tolerances={})
    thicker = map_measurements_to_v112(thicker_bundle, tolerances={})

    changed_parameters = {
        key
        for key in baseline["parameters"]
        if baseline["parameters"][key] != thicker["parameters"][key]
    }
    assert changed_parameters <= {
        "blade_thickness_mm",
        "leading_edge_radius_mm",
        "trailing_edge_radius_mm",
    }
    changed_defaults = {
        key
        for key in baseline["resolved_blade_to_blade_loop_family_defaults"]
        if baseline["resolved_blade_to_blade_loop_family_defaults"][key]
        != thicker["resolved_blade_to_blade_loop_family_defaults"][key]
    }
    assert changed_defaults <= {
        "average_blade_thickness_mm",
        "maximum_blade_thickness_mm",
    }
    assert thicker["parameters"]["blade_thickness_mm"] > baseline["parameters"]["blade_thickness_mm"]


def test_objective_terms_persist_bounded_station_evidence_not_only_counts():
    result = map_measurements_to_v112(_measurement_bundle(station_count=9), tolerances={})

    for role in ("camber", "pose", "normal_thickness"):
        term = result["objective_terms"][role]
        assert term["records"]
        assert "records" not in term["target"]
        assert "records" not in term["fitted"]
        assert "records" not in term["residual"]
        assert all(
            {
                "family",
                "h",
                "s",
                "role",
                "target",
                "fitted",
                "unit",
                "weight",
                "residual",
                "gate",
                "source_ids",
            }
            <= record.keys()
            for record in term["records"]
        )
        assert term["weight"]["span_rule"] == "fixed_five_station_trapezoidal_endpoint_half_weight"

    edge = result["objective_terms"]["edge_curves"]
    assert edge["records"]
    assert edge["fitted"]["generation_authority"] == "build_v11_blade_to_blade_loop_family"
    assert all(
        {
            "family",
            "h",
            "role",
            "target",
            "fitted",
            "unit",
            "weight",
            "residual",
            "gate",
            "source_ids",
        }
        <= record.keys()
        for record in edge["records"]
    )
    assert all(record["target"] for record in edge["records"])
    assert all(record["fitted"] for record in edge["records"])
    required_promotion_evidence = {
        "method",
        "tolerance",
        "confidence",
        "frame",
        "units",
        "source_ids",
        "provenance",
    }
    assert all(
        required_promotion_evidence <= term.keys()
        for term in result["objective_terms"].values()
    )
    assert all(
        required_promotion_evidence <= record.keys()
        for term in result["objective_terms"].values()
        for record in term.get("records", [])
    )
    assert "records" not in edge["residual"]
    assert "records" not in result["objective_terms"]["attachment"]["fitted"]
    assert all(
        required_promotion_evidence <= record.keys()
        for records in _serialized_record_lists(result)
        for record in records
    )
    assert all(
        {"source_edge_ids", "source_face_ids"} <= record.keys()
        for records in _serialized_record_lists(result)
        for record in records
    )
    assert all(
        {
            "controls",
            "knots",
            "weights",
            "target_nurbs_authorities",
        }
        <= record.keys()
        for record in edge["records"]
    )
    assert all(
        {
            "degree",
            "controls",
            "control_points_local_mm",
            "knots",
            "weights",
            "fit_evidence",
        }
        <= authority.keys()
        for record in edge["records"]
        for authority in record["target_nurbs_authorities"]
    )


def test_edge_samples_must_match_the_authoritative_nurbs_curve():
    bundle = _measurement_bundle(station_count=5)
    target = bundle["section_families"]["main"]["stations"][0][
        "decomposition"
    ]["segments"]["leading_edge"]["nurbs_target"]
    target["sample_points_local_mm"][len(target["sample_points_local_mm"]) // 2][
        0
    ] += 2.0

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


def test_edge_nurbs_authority_is_bound_to_its_task7_source_segment_points():
    bundle = _measurement_bundle(station_count=5)
    segment = bundle["section_families"]["main"]["stations"][0][
        "decomposition"
    ]["segments"]["leading_edge"]
    segment["points_sq_mm"][len(segment["points_sq_mm"]) // 2][0] += 6.0

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"
    assert "Task 7 source segment" in str(captured.value)


def test_real_task7_section_fit_passes_through_mapping_adapter():
    bundle = _measurement_bundle(station_count=5)
    source = bundle["section_families"]["main"]["stations"][0][
        "decomposition"
    ]["segments"]["leading_edge"]
    points_sq = tuple(tuple(point) for point in source["points_sq_mm"])
    points_xyz = tuple((point[0], point[1], 0.0) for point in points_sq)
    source_edge_ids = tuple(source["source_edge_ids"])
    source_face_ids = ("task7-source-face-distinct",)
    fit = fit_nurbs_measurement_curve(
        points_xyz,
        points_sq,
        segment_name="leading_edge",
        source_edge_ids=source_edge_ids,
        maximum_control_count=len(points_sq),
    )
    task7_segment = SectionSegmentMeasurement(
        name="leading_edge",
        points_xyz_mm=points_xyz,
        points_sq_mm=points_sq,
        source_edge_ids=source_edge_ids,
        source_face_ids=source_face_ids,
        fit=fit,
    )
    adapted = adapt_task7_segment_for_mapping(
        task7_segment,
        fit_tolerance_mm=0.15,
    )
    assert adapted["source_edge_ids"] == list(source_edge_ids)
    assert adapted["source_face_ids"] == list(source_face_ids)
    assert set(adapted["source_ids"]) == set(source_edge_ids) | set(
        source_face_ids
    )
    source.clear()
    source.update(adapted)
    bundle["frame"]["axis_consensus"]["selected_cluster"]["tolerance"][
        "line_distance_mm"
    ] = 0.15

    result = map_measurements_to_v112(bundle, tolerances={})

    assert result["mapping_status"] == "PASS"
    edge_term = result["objective_terms"]["edge_curves"]
    record = next(
        item
        for item in edge_term["records"]
        if item["h"] == 0.0 and item["role"] == "leading_edge"
    )
    authority = record["target_nurbs_authorities"][0]
    assert set(source_edge_ids) <= set(edge_term["source_edge_ids"])
    assert source_face_ids[0] in edge_term["source_face_ids"]
    assert record["source_edge_ids"] == list(source_edge_ids)
    assert record["source_face_ids"] == list(source_face_ids)
    assert set(record["source_ids"]) == set(source_edge_ids) | set(source_face_ids)
    assert authority["source_edge_ids"] == list(source_edge_ids)
    assert authority["source_face_ids"] == list(source_face_ids)
    assert authority["fit_evidence"]["source_edge_ids"] == list(source_edge_ids)
    assert "source_face_ids" not in authority["fit_evidence"]
    assert authority["degree"] == fit.degree
    assert len(authority["controls"]) == len(fit.control_points_sq_mm)
    assert all(
        actual == pytest.approx(expected, abs=1.0e-9)
        for actual, expected in zip(
            authority["controls"], fit.control_points_sq_mm
        )
    )
    assert authority["fit_evidence"]["residual"]["maximum_mm"] == pytest.approx(
        fit.residual_max_mm, abs=1.0e-9
    )


def test_knot_local_two_mm_edge_excursion_cannot_false_pass_between_uniform_samples():
    bundle = _measurement_bundle(station_count=5)
    segment = bundle["section_families"]["main"]["stations"][2][
        "decomposition"
    ]["segments"]["leading_edge"]
    baseline = copy.deepcopy(segment["nurbs_target"])
    baseline_parameters = sorted(set(float(value) for value in baseline["knots"]))
    center = 0.5 * (32.0 / 64.0 + 33.0 / 64.0)
    half_width = 1.0e-5
    parameters = sorted(
        set(
            baseline_parameters
            + [center - half_width, center, center + half_width]
        )
    )
    source_points = [
        evaluate_nurbs_curve(
            {
                "degree": baseline["degree"],
                "knots": baseline["knots"],
                "weights": baseline["weights"],
                "control_points": baseline["control_points_local_mm"],
            },
            parameter,
        )
        for parameter in parameters
    ]
    source_points[parameters.index(center)][0] -= 2.0
    _replace_edge_target(
        segment,
        source_points,
        "leading_edge",
        parameters=parameters,
    )

    old_uniform = _evaluate_target_samples(baseline, 65)
    adversarial_uniform = _evaluate_target_samples(segment["nurbs_target"], 65)
    assert max(
        math.dist(left, right)
        for left, right in zip(old_uniform, adversarial_uniform)
    ) < 2.0e-6

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_mapping_residual_exceeded"
    edge_term = captured.value.details["objective_terms"]["edge_curves"]
    record = next(
        item
        for item in edge_term["records"]
        if item["h"] == 0.5 and item["role"] == "leading_edge"
    )
    certificate = record["distance_certificate"]
    assert certificate["method"].startswith("deterministic_knot_split")
    assert certificate["lower_bound_mm"] > edge_term["gate"][
        "bidirectional_hausdorff_limit_mm"
    ]
    assert certificate["gate_status"] == "FAIL"


def test_equivalent_edge_radius_and_constructor_hash_have_one_nurbs_authority():
    original = _measurement_bundle(station_count=5)
    resampled = copy.deepcopy(original)
    for family in resampled["section_families"].values():
        for station in family["stations"]:
            for edge_name in ("leading_edge", "trailing_edge"):
                target = station["decomposition"]["segments"][edge_name][
                    "nurbs_target"
                ]
                target["sample_points_local_mm"] = _evaluate_target_samples(
                    target, 33
                )

    first = map_measurements_to_v112(original, tolerances={})
    second = map_measurements_to_v112(resampled, tolerances={})

    assert first["parameters"]["leading_edge_radius_mm"] == second["parameters"][
        "leading_edge_radius_mm"
    ]
    assert first["parameters"]["trailing_edge_radius_mm"] == second["parameters"][
        "trailing_edge_radius_mm"
    ]
    assert first["constructor_input_hash_sha256"] == second[
        "constructor_input_hash_sha256"
    ]


@pytest.mark.parametrize(
    ("mode", "main_count", "splitter_count"),
    (("open", 7, 0), ("closed", 6, 6)),
)
def test_open_main_only_and_closed_splitter_material_truth(
    mode: str, main_count: int, splitter_count: int
):
    result = map_measurements_to_v112(
        _measurement_bundle(
            station_count=5,
            mode=mode,
            main_count=main_count,
            splitter_count=splitter_count,
        ),
        tolerances={},
    )
    defaults = result["resolved_blade_to_blade_loop_family_defaults"]

    assert result["parameters"]["blade_count"] == main_count + splitter_count
    assert defaults["main_blade_count"] == main_count
    assert defaults["splitter_blade_count"] == splitter_count
    if mode == "open":
        assert defaults["tip_attachment_mode"] == "open_tip_dome"
        assert "shroud_blade_inset_mm" not in defaults
        assert "hood_wall_thickness_mm" not in result["parameters"]
    else:
        assert defaults["tip_attachment_mode"] == "closed_shroud_attachment"
        assert defaults["shroud_blade_inset_mm"] > 0.0
        assert result["parameters"]["hood_wall_thickness_mm"] > 0.0


@pytest.mark.parametrize(
    "mutation",
    (
        lambda bundle: bundle.update({"surface_authority": "v1.2"}),
        lambda bundle: bundle["section_families"]["main"]["stations"][0]["decomposition"].update(
            {"direct_curve_constructor_mode_v1_2": True}
        ),
    ),
)
def test_unknown_and_v12_only_measurement_fields_are_rejected(mutation):
    bundle = _measurement_bundle(station_count=5)
    mutation(bundle)

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_forbidden_parameter"


def test_direct_source_edge_curve_cannot_be_promoted_to_constructor_input():
    bundle = _measurement_bundle(station_count=5)
    target = bundle["section_families"]["main"]["stations"][0]["decomposition"]["segments"]["leading_edge"]["nurbs_target"]
    target["measurement_target_only"] = False
    target["constructor_direct_curve_mode"] = True

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


@pytest.mark.parametrize("failed_term", ("supports", "camber", "pose", "normal_thickness", "edge_curves"))
def test_independent_residual_gates_reject_unrepresentable_measurements(failed_term: str):
    bundle = _measurement_bundle(station_count=5)
    if failed_term == "supports":
        bundle["support_fits"]["hub"]["residual_rms_mm"] = 2.0
    elif failed_term == "camber":
        bundle["section_families"]["main"]["stations"][2]["camber"]["samples"][3]["q_mm"] += 8.0
    elif failed_term == "pose":
        bundle["section_families"]["main"]["stations"][2]["pose"]["samples"][3]["theta_deg"] += 12.0
    elif failed_term == "normal_thickness":
        bundle["section_families"]["main"]["stations"][2]["normal_thickness"]["samples"][3]["thickness_mm"] += 8.0
    else:
        target = bundle["section_families"]["main"]["stations"][2]["decomposition"]["segments"]["leading_edge"]["nurbs_target"]
        for point in target["control_points_local_mm"]:
            point[0] -= 8.0 * math.sin(math.pi * target["control_points_local_mm"].index(point) / (len(target["control_points_local_mm"]) - 1))
        target["sample_points_local_mm"] = _evaluate_target_samples(
            target, len(target["sample_points_local_mm"])
        )
        _refresh_edge_fit_evidence(
            bundle["section_families"]["main"]["stations"][2][
                "decomposition"
            ]["segments"]["leading_edge"],
            "leading_edge",
        )

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_mapping_residual_exceeded"
    assert failed_term in captured.value.details["failed_terms"]


def test_residual_rejection_retains_all_preceding_mapping_evidence():
    bundle = _measurement_bundle(station_count=5)
    bundle["section_families"]["main"]["stations"][2]["camber"]["samples"][3][
        "q_mm"
    ] += 8.0

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    details = captured.value.details
    assert {
        "frame",
        "provenance",
        "promotion",
        "tolerances",
        "solver",
        "bounds",
        "candidate",
        "objective_terms",
        "passed_terms",
        "failed_terms",
        "passing_terms",
        "failing_terms",
    } <= details.keys()
    assert details["frame"]["coordinate_system"] == "canonical_axis_frame_xyz_mm"
    assert details["solver"]["success"] is True
    assert details["bounds"]
    assert details["candidate"]["five_station_resampling_report"]
    assert set(details["objective_terms"]) == set(details["passing_terms"]) | set(
        details["failing_terms"]
    )
    assert "camber" in details["failed_terms"]
    assert "camber" in details["failing_terms"]
    assert details["passing_terms"]


def test_solve_time_mapping_error_retains_common_and_partial_evidence(monkeypatch):
    original = mapping_module._MappingContext.residual_vector

    def fail_normal_thickness(self, vector, *, roles=None):
        if roles == {"normal_thickness"}:
            raise V112MappingError(
                "v116_v112_mapping_residual_exceeded",
                "forced normal-thickness solve failure",
                {"failing_sample": {"h": 0.5, "s": 0.5}},
            )
        return original(self, vector, roles=roles)

    monkeypatch.setattr(
        mapping_module._MappingContext,
        "residual_vector",
        fail_normal_thickness,
    )

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(
            _measurement_bundle(station_count=5), tolerances={}
        )

    details = captured.value.details
    assert {
        "frame",
        "provenance",
        "promotion",
        "tolerances",
        "solver",
        "bounds",
        "candidate",
        "objective_terms",
        "passed_terms",
        "failed_terms",
        "passing_terms",
        "failing_terms",
    } <= details.keys()
    assert details["solver"]["success"] is False
    assert details["solver"]["status"] == "EXCEPTION"
    assert details["solver"]["current_objective"] == "normal_thickness"
    assert details["candidate"]["partial_vector"]
    assert details["candidate"]["completed_groups"]
    assert details["passed_terms"] == ["camber"]
    assert details["failed_terms"] == ["normal_thickness"]
    assert details["passing_terms"]["camber"]["method"]
    assert details["failing_terms"]["normal_thickness"]["tolerance"]
    assert details["failing_sample"] == {"h": 0.5, "s": 0.5}


def test_generic_solver_exception_is_wrapped_with_stable_partial_evidence(monkeypatch):
    original = mapping_module._MappingContext._solve_group

    def fail_normal_thickness(self, role, index_array, vector):
        if role == "normal_thickness":
            raise RuntimeError("forced generic solver failure")
        return original(self, role, index_array, vector)

    monkeypatch.setattr(
        mapping_module._MappingContext,
        "_solve_group",
        fail_normal_thickness,
    )

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(
            _measurement_bundle(station_count=5), tolerances={}
        )

    details = captured.value.details
    assert captured.value.reason == "v116_v112_mapping_solver_exception"
    assert _COMMON_REJECTION_EVIDENCE_KEYS <= details.keys()
    assert details["exception_type"] == "builtins.RuntimeError"
    assert details["exception_message"] == "forced generic solver failure"
    assert details["solver"]["status"] == "EXCEPTION"
    assert details["solver"]["current_objective"] == "normal_thickness"
    assert details["solver"]["current_vector"] == details["candidate"][
        "partial_vector"
    ]
    assert details["passed_terms"] == ["camber"]
    assert details["failed_terms"] == ["normal_thickness"]
    assert details["failing_terms"]["normal_thickness"]["residual"][
        "objective_value"
    ] == details["solver"]["current_objective_value"]


def test_unsuccessful_solver_result_retains_vector_objective_and_term_inventory(
    monkeypatch,
):
    retained_vector = None

    def fail_with_result(self, initial):
        nonlocal retained_vector
        retained_vector = initial.copy()
        retained_vector[0] += 0.125
        return mapping_module._BoundedSolveResult(
            x=retained_vector,
            success=False,
            status=0,
            message="normal_thickness: forced unsuccessful result",
            nfev=7,
            cost=0.75,
            optimality=0.25,
            groups=(
                {
                    "objective": "camber",
                    "variable_names": [
                        "main_flow_turn_q_mm",
                        "spanwise_flow_turn_delta_q_mm",
                        "midspan_bow_q_mm",
                    ],
                    "nfev": 3,
                    "cost": 0.25,
                    "status": 1,
                },
            ),
            current_objective="normal_thickness",
            current_objective_value=0.5,
        )

    monkeypatch.setattr(
        mapping_module._MappingContext,
        "solve",
        fail_with_result,
    )

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(
            _measurement_bundle(station_count=5), tolerances={}
        )

    details = captured.value.details
    assert captured.value.reason == "v116_v112_mapping_solver_failed"
    assert _COMMON_REJECTION_EVIDENCE_KEYS <= details.keys()
    assert retained_vector is not None
    assert details["solver"]["success"] is False
    assert details["solver"]["current_vector"] == pytest.approx(retained_vector)
    assert details["solver"]["current_objective"] == "normal_thickness"
    assert details["solver"]["current_objective_value"] == 0.5
    assert details["candidate"]["partial_vector"] == pytest.approx(
        retained_vector
    )
    assert details["candidate"]["partial_values"]
    assert set(details["objective_terms"]) == {"camber", "normal_thickness"}
    assert details["passed_terms"] == ["camber"]
    assert details["failed_terms"] == ["normal_thickness"]
    assert details["passing_terms"]["camber"]["residual"]["cost"] == 0.25
    assert details["failing_terms"]["normal_thickness"]["residual"][
        "objective_value"
    ] == 0.5


def test_edge_gate_rejects_semicircle_proxy_instead_of_comparing_against_one():
    bundle = _measurement_bundle(station_count=5)
    station = bundle["section_families"]["main"]["stations"][2]
    thickness = station["normal_thickness"]["samples"][0]["thickness_mm"]
    _replace_edge_target(
        station["decomposition"]["segments"]["leading_edge"],
        _semicircle_proxy_cap(thickness, leading=True),
        "leading_edge",
    )

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_mapping_residual_exceeded"
    assert "edge_curves" in captured.value.details["failed_terms"]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda bundle: (
            bundle["populations"]["main"].update({"count": 65, "pitch_deg": 360.0 / 65}),
        ),
        lambda bundle: bundle["topology"]["material_measurements"]["mounting_bore_radius_mm"].update(
            {"value": 4000.0}
        ),
        lambda bundle: bundle["topology"]["material_measurements"]["hub_wall_thickness_mm"].update(
            {"value": 0.0}
        ),
    ),
)
def test_runtime_parameter_limits_and_material_domain_are_hard_gates(mutation):
    bundle = _measurement_bundle(station_count=5)
    mutation(bundle)

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason in {
        "v116_v112_parameter_limit_failed",
        "v116_v112_material_domain_failed",
    }


def test_tolerance_overrides_can_tighten_but_relaxed_runs_are_non_promotable():
    exact = map_measurements_to_v112(
        _measurement_bundle(station_count=5),
        tolerances={
            "hub_rms_floor_mm": 0.05,
            "hub_rms_diameter_ratio": 0.0005,
        },
    )
    assert exact["mapping_status"] == "PASS"
    assert exact["promotion"]["promotable"] is True

    relaxed_bundle = _measurement_bundle(station_count=5)
    relaxed_bundle["support_fits"]["hub"]["residual_rms_mm"] = 0.15
    diagnostic = map_measurements_to_v112(
        relaxed_bundle,
        tolerances={"hub_rms_floor_mm": 0.20},
    )
    assert diagnostic["mapping_status"] == "DIAGNOSTIC_ONLY"
    assert diagnostic["promotion"]["promotable"] is False
    assert diagnostic["promotion"]["loosened_fields"] == ["hub_rms_floor_mm"]


@pytest.mark.parametrize(
    "matrix",
    (
        [[2.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        [[1.0, 0.2, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        [[-1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.1, 1.0]],
    ),
)
def test_frame_rejects_scale_shear_reflection_and_non_homogeneous_last_row(matrix):
    bundle = _measurement_bundle(station_count=5)
    bundle["frame"]["source_to_canonical_matrix"] = matrix

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


def test_frame_requires_task3_axis_consensus_evidence():
    bundle = _measurement_bundle(station_count=5)
    del bundle["frame"]["axis_consensus"]

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


def test_frame_rejects_unknown_unauthenticated_task3_evidence_fields():
    bundle = _measurement_bundle(station_count=5)
    bundle["frame"]["axis_consensus"]["selected_cluster"]["review_note"] = "not authenticated"

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


def test_strict_frame_adapter_accepts_the_real_task3_result_without_fixture_extension(
    tmp_path,
):
    from part_rule_synthesis.impeller_v11_6_source_frame import (
        resolve_canonical_frame,
    )
    from part_rule_synthesis.impeller_v11_6_step_audit import load_step_source
    from step_fixtures import write_axis_first_impeller_step

    path = write_axis_first_impeller_step(
        tmp_path / "mapping-frame.step",
        blade_count=7,
        root_blend_radius_mm=0.18,
    )
    shape, source = load_step_source(path)
    task3_frame = resolve_canonical_frame(shape, source)

    assert "coordinate_system" not in task3_frame
    assert "units" not in task3_frame
    assert "source_tolerance_mm" not in task3_frame
    adapted = adapt_task3_frame_for_mapping(task3_frame)
    selected = task3_frame["axis_consensus"]["selected_cluster"]
    assert adapted["coordinate_system"] == "canonical_axis_frame_xyz_mm"
    assert adapted["units"] == selected["units"]["linear"] == "mm"
    assert adapted["source_tolerance_mm"] == selected["tolerance"][
        "line_distance_mm"
    ]

    bundle = _measurement_bundle(station_count=5, main_count=7)
    bundle["frame"] = task3_frame
    result = map_measurements_to_v112(bundle, tolerances={})
    assert result["provenance"]["frame"] == adapted


def test_task3_frame_adapter_rejects_unknown_fields_without_relaxing_schema():
    bundle = _measurement_bundle(station_count=5)
    bundle["frame"]["fixture_only_units"] = "mm"

    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(bundle, tolerances={})

    assert captured.value.reason == "v116_v112_measurement_schema_invalid"


def test_missing_material_measurement_and_material_topology_conflict_are_terminal():
    missing = _measurement_bundle(station_count=5)
    del missing["topology"]["material_measurements"]["hub_bottom_thickness_mm"]
    with pytest.raises(V112MappingError) as captured_missing:
        map_measurements_to_v112(missing, tolerances={})
    assert captured_missing.value.reason == "v116_v112_material_measurement_missing"

    false_shroud = _measurement_bundle(station_count=5)
    false_shroud["topology"]["material_shroud"] = True
    with pytest.raises(V112MappingError) as captured_topology:
        map_measurements_to_v112(false_shroud, tolerances={})
    assert captured_topology.value.reason == "v116_v112_topology_failed"


def test_canonical_payload_hash_regenerates_and_mapping_does_not_mutate_old_presets():
    before = {
        preset_id: compile_impeller_runtime_preset(preset_id)
        for preset_id in ACTIVE_V112_PRESETS
    }
    result = map_measurements_to_v112(_measurement_bundle(station_count=5), tolerances={})
    after = {
        preset_id: compile_impeller_runtime_preset(preset_id)
        for preset_id in ACTIVE_V112_PRESETS
    }
    regenerated = canonical_nurbs_from_v11_defaults(
        result["parameters"],
        result["resolved_blade_to_blade_loop_family_defaults"],
        source="v116_bounded_measurement_mapping",
    )

    assert result["geometry_patch_version"] == GEOMETRY_PATCH_VERSION
    assert regenerated == result["regenerated_canonical_payload"]
    assert before == after
    assert all(runtime["geometry_patch_version"] == "1.1.2" for runtime in after.values())


def test_initial_guess_rejects_non_v112_fields():
    with pytest.raises(V112MappingError) as captured:
        map_measurements_to_v112(
            _measurement_bundle(station_count=5),
            tolerances={},
            initial_guess={
                "parameters": {"surface_authority": "v1.2"},
                "defaults": {},
            },
        )
    assert captured.value.reason == "v116_v112_forbidden_parameter"


def _measurement_bundle(
    *,
    station_count: int,
    mode: str = "open",
    main_count: int = 7,
    splitter_count: int = 0,
    average_thickness_mm: float = 4.0,
    maximum_thickness_mm: float = 5.0,
) -> dict:
    parameters, defaults = _constructor_seed(
        mode=mode,
        main_count=main_count,
        splitter_count=splitter_count,
        average_thickness_mm=average_thickness_mm,
        maximum_thickness_mm=maximum_thickness_mm,
    )
    canonical = canonical_nurbs_from_v11_defaults(
        parameters, defaults, source="synthetic_measurement_authority"
    )
    generated_family = _fixture_loop_family(parameters, defaults)
    h_values = [index / (station_count - 1) for index in range(station_count)]
    section_families = {
        "main": _section_family("main", h_values, canonical, generated_family),
    }
    splitter = None
    if splitter_count:
        splitter = {
            "count": splitter_count,
            "pitch_deg": 360.0 / splitter_count,
            "phase_deg": 0.5 * (360.0 / main_count),
            "streamwise_interval_s": [0.34, 0.88],
            "source_ids": ["splitter-population"],
        }
        section_families["splitter"] = _section_family(
            "splitter", h_values, canonical, generated_family
        )

    material = {
        "mounting_bore_radius_mm": _material(4.0, "bore"),
        "root_fillet_radius_mm": _material(1.2, "root-fillet"),
        "tip_edge_radius_mm": _material(1.0, "tip-edge"),
        "hub_wall_thickness_mm": _material(3.0, "hub-wall"),
        "hub_bottom_thickness_mm": _material(4.0, "hub-bottom"),
        "hub_top_cap_thickness_mm": _material(2.0, "hub-cap"),
        "hub_chamfer_radius_mm": _material(0.5, "hub-chamfer"),
    }
    attachments = {
        "root": _attachment(1.5, 3.5, "root-attachment", material_side=1),
    }
    if mode == "closed":
        material.update(
            {
                "hood_wall_thickness_mm": _material(2.5, "shroud-wall"),
                "hood_chamfer_radius_mm": _material(0.4, "shroud-chamfer"),
            }
        )
        attachments["shroud"] = _attachment(
            1.0, 3.0, "shroud-attachment", material_side=-1
        )

    return {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "frame": {
            "source_to_canonical_matrix": [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            "method": "deterministic_analytic_axis_consensus_r3",
            "source_axis_origin_mm": [0.0, 0.0, 0.0],
            "source_axis_direction": [0.0, 0.0, 1.0],
            "scale": 1.0,
            "primary_icp_applied": False,
            "handedness": "right_handed",
            "axis_consensus": {
                "tolerance": {
                    "line_distance_mm": 0.01,
                    "clustering_line_distance_mm": 0.01,
                    "angular_deg": 0.05,
                },
                "selected_cluster": {
                    "score": 1.0,
                    "score_components": {
                        "analytic_area_mm2": 100.0,
                        "analytic_feature_count": 2,
                        "periodic_closure_support": 1.0,
                        "normalized_analytic_area": 1.0,
                        "normalized_feature_count": 1.0,
                        "normalized_periodic_closure": 1.0,
                    },
                    "confidence": {
                        "level": "ranked_analytic_consensus_candidate",
                        "combined_score": 1.0,
                        "independent_score_components": True,
                    },
                    "coordinate_frame": "source_cartesian_mm",
                    "units": {"linear": "mm", "angular": "deg", "area": "mm2"},
                    "tolerance": {"line_distance_mm": 0.01, "angular_deg": 0.05},
                    "source_entity_ids": ["face-axis"],
                    "face_ids": ["face-axis"],
                    "edge_ids": [],
                    "face_count": 1,
                    "line_origin_mm": [0.0, 0.0, 0.0],
                    "line_direction": [0.0, 0.0, 1.0],
                    "residual": {
                        "line_rms_mm": 0.001,
                        "line_max_mm": 0.001,
                        "angular_spread_deg": 0.001,
                    },
                    "provenance": {
                        "authority": "uploaded_step_brep",
                        "source_entity_ids": ["face-axis"],
                        "candidate_method": "analytic_surface_and_circular_edge_axis_extraction",
                    },
                },
                "residual": {
                    "line_rms_mm": 0.001,
                    "line_max_mm": 0.001,
                    "angular_spread_deg": 0.001,
                },
                "direction_resolution": {
                    "method": "radial_weighted_axial_asymmetry",
                    "normalized_moment": 0.1,
                },
                "rejected_alternatives": [],
            },
            "candidate_scores": [],
            "outer_radius_mm": 51.5,
            "main_bore_radius_mm": 4.0,
            "axial_extent_mm": 35.0,
            "central_cylinder_radii_mm": [4.0, 12.0],
        },
        "provenance": {
            "source_sha256": "a" * 64,
            "source_entity_ids": ["solid-1", "face-hub", "face-tip"],
            "algorithm_version": "axis_first_section_periodic_r3",
            "source_preset_id": "comparison-only-seed",
        },
        "topology": {
            "mode": mode,
            "outer_diameter_mm": 103.0,
            "material_shroud": mode == "closed",
            "material_measurements": material,
            "source_ids": ["solid-1"],
        },
        "support_fits": {
            "hub": {
                "control_points_rz_mm": copy.deepcopy(defaults["hub_profile_rz_mm"]),
                "residual_rms_mm": 0.01,
                "source_ids": ["face-hub"],
                "fit_status": "PASS",
                "measurement_authority": "occt_trimmed_brep_measurement",
            },
            "tip_or_shroud": {
                "control_points_rz_mm": copy.deepcopy(defaults["tip_or_shroud_profile_rz_mm"]),
                "residual_rms_mm": 0.015,
                "source_ids": ["face-tip"],
                "fit_status": "PASS",
                "measurement_authority": "occt_trimmed_brep_measurement",
            },
        },
        "populations": {
            "main": {
                "count": main_count,
                "pitch_deg": 360.0 / main_count,
                "phase_deg": 0.0,
                "streamwise_interval_s": [0.05, 0.95],
                "source_ids": ["main-population"],
            },
            "splitter": splitter,
            "relative_phase_pitch": 0.0 if splitter is None else 0.5,
            "closure_pass": True,
            "collision_free": True,
            "phase_consistent": True,
            "source_ids": ["periodic-analysis"],
        },
        "section_families": section_families,
        "attachments": attachments,
    }


def _constructor_seed(
    *,
    mode: str,
    main_count: int,
    splitter_count: int,
    average_thickness_mm: float,
    maximum_thickness_mm: float,
) -> tuple[dict, dict]:
    parameters = {
        "blade_count": main_count + splitter_count,
        "blade_thickness_mm": average_thickness_mm,
        "blade_wrap_deg": 82.0,
        "blade_lean_deg": 5.0,
        "leading_edge_lean_deg": 2.0,
        "trailing_edge_lean_deg": -3.0,
        "leading_edge_sweep_mm": 1.0,
        "trailing_edge_sweep_mm": -1.0,
    }
    defaults = {
        "hub_profile_rz_mm": [
            [12.0, 30.0],
            [15.0, 25.0],
            [20.0, 18.0],
            [30.0, 8.0],
            [42.0, 2.0],
            [51.5, 0.0],
        ],
        "tip_or_shroud_profile_rz_mm": [
            [20.0, 35.0],
            [23.0, 30.0],
            [29.0, 24.0],
            [38.0, 16.0],
            [47.0, 10.0],
            [52.0, 7.0],
        ],
        "span_stations_h": list(CANONICAL_STATIONS_H),
        "main_blade_count": main_count,
        "splitter_blade_count": splitter_count,
        "main_streamwise_interval_s": [0.05, 0.95],
        "splitter_streamwise_interval_s": [0.34, 0.88],
        "splitter_phase_offset_pitch": 0.0 if splitter_count == 0 else 0.5,
        "splitter_positioning_mode": "main_passage_bisector",
        "splitter_passage_fraction": 0.5,
        "average_blade_thickness_mm": average_thickness_mm,
        "maximum_blade_thickness_mm": maximum_thickness_mm,
        "root_attachment_width_mm": 3.5,
        "root_attachment_lift_mm": 1.5,
        "root_blade_lift_mm": 1.5,
        "main_flow_turn_q_mm": 18.0,
        "splitter_flow_turn_q_mm": 18.0 if splitter_count else 0.0,
        "spanwise_flow_turn_delta_q_mm": 4.0,
        "midspan_bow_q_mm": 2.0,
        "leading_edge_cap_roundness": 0.56,
        "trailing_edge_cap_roundness": 0.54,
        "tip_attachment_mode": "open_tip_dome" if mode == "open" else "closed_shroud_attachment",
    }
    if mode == "closed":
        defaults["shroud_attachment_width_mm"] = 3.0
        defaults["shroud_blade_inset_mm"] = 1.0
    return parameters, defaults


def _section_family(
    name: str,
    h_values: list[float],
    canonical: dict,
    generated_family: dict,
) -> dict:
    stations = []
    for station_index, h in enumerate(h_values):
        s_values = [index / 8 for index in range(9)]
        camber = [
            {
                "s": s,
                "q_mm": evaluate_nurbs_surface(canonical["blade_skeleton_field"], s, h)[2],
            }
            for s in s_values
        ]
        pose = [
            {
                "s": s,
                "theta_deg": _evaluate_fixture_field(canonical["pose_field"], s, h)[2],
            }
            for s in s_values
        ]
        thickness = [
            {
                "s": s,
                "thickness_mm": evaluate_nurbs_surface(canonical["thickness_field"], s, h)[2],
                "inside_source_loop": True,
            }
            for s in s_values
        ]
        side_a = [
            [
                evaluate_nurbs_surface(canonical["blade_skeleton_field"], s, h)[0],
                camber[index]["q_mm"] - 0.5 * thickness[index]["thickness_mm"],
            ]
            for index, s in enumerate(s_values)
        ]
        side_b = [
            [
                evaluate_nurbs_surface(canonical["blade_skeleton_field"], s, h)[0],
                camber[index]["q_mm"] + 0.5 * thickness[index]["thickness_mm"],
            ]
            for index, s in enumerate(s_values)
        ]
        leading_cap = _generated_cap_at_h(generated_family, name, h, "leading_edge")
        trailing_cap = _generated_cap_at_h(generated_family, name, h, "trailing_edge")
        station_source = f"{name}-station-{station_index}"
        stations.append(
            {
                "h": h,
                "source_ids": [station_source],
                "decomposition": {
                    "segments": {
                        "side_a": {
                            "points_sq_mm": side_a,
                            "source_ids": [f"{station_source}-side-a"],
                        },
                        "side_b": {
                            "points_sq_mm": side_b,
                            "source_ids": [f"{station_source}-side-b"],
                        },
                        "leading_edge": _edge_segment(
                            leading_cap,
                            "leading_edge",
                            f"{station_source}-leading",
                        ),
                        "trailing_edge": _edge_segment(
                            trailing_cap,
                            "trailing_edge",
                            f"{station_source}-trailing",
                        ),
                    },
                    "pressure_suction_assigned": False,
                    "direct_curve_constructor_mode": False,
                    "source_ids": [f"{station_source}-loop"],
                },
                "camber": {
                    "samples": camber,
                    "source_ids": [f"{station_source}-camber"],
                },
                "pose": {
                    "samples": pose,
                    "source_ids": [f"{station_source}-pose"],
                },
                "normal_thickness": {
                    "samples": thickness,
                    "source_ids": [f"{station_source}-thickness"],
                    "method": "camber_normal_line_intersections",
                },
            }
        )
    return {
        "population": name,
        "stations": stations,
        "source_ids": [f"{name}-representative"],
    }


def _semicircle_proxy_cap(
    thickness_mm: float, *, leading: bool, count: int = 49
) -> list[list[float]]:
    half = 0.5 * thickness_mm
    direction = -1.0 if leading else 1.0
    return [
        [
            direction * half * math.sin(math.pi * index / (count - 1)),
            -half * math.cos(math.pi * index / (count - 1)),
        ]
        for index in range(count)
    ]


def _evaluate_fixture_field(surface: dict, s: float, h: float) -> list[float]:
    grid = surface["control_points"]
    if len(grid) >= int(surface["degree_u"]) + 1:
        return evaluate_nurbs_surface(surface, s, h)
    transposed = copy.deepcopy(surface)
    transposed["control_points"] = [
        [grid[h_index][s_index] for h_index in range(len(grid))]
        for s_index in range(len(grid[0]))
    ]
    transposed["weights"] = [
        [surface["weights"][h_index][s_index] for h_index in range(len(grid))]
        for s_index in range(len(grid[0]))
    ]
    transposed["knots_u"] = "clamped_uniform"
    transposed["knots_v"] = "clamped_uniform"
    return evaluate_nurbs_surface(transposed, s, h)


def _edge_segment(
    samples: list[list[float]], segment_name: str, source_edge_id: str
) -> dict:
    return {
        "points_sq_mm": copy.deepcopy(samples),
        "source_ids": [source_edge_id],
        "source_edge_ids": [source_edge_id],
        "source_face_ids": [],
        "nurbs_target": _nurbs_target(
            samples,
            segment_name=segment_name,
            source_edge_ids=[source_edge_id],
        ),
    }


def _nurbs_target(
    samples: list[list[float]],
    *,
    segment_name: str,
    source_edge_ids: list[str],
    parameters: list[float] | None = None,
) -> dict:
    controls = copy.deepcopy(samples)
    degree = 1
    knots = (
        clamped_uniform_knots(len(controls), degree)
        if parameters is None
        else [0.0, 0.0, *parameters[1:-1], 1.0, 1.0]
    )
    target = {
        "degree": degree,
        "knots": knots,
        "weights": [1.0] * len(controls),
        "control_points_local_mm": controls,
        "sample_points_local_mm": copy.deepcopy(samples),
        "measurement_target_only": True,
        "constructor_direct_curve_mode": False,
    }
    if parameters is not None:
        target["sample_points_local_mm"] = _evaluate_target_samples(
            target, max(9, len(controls))
        )
    target["fit_evidence"] = _edge_fit_evidence(
        target,
        segment_name=segment_name,
        source_edge_ids=source_edge_ids,
        source_points=controls,
    )
    return target


def _replace_edge_target(
    segment: dict,
    samples: list[list[float]],
    segment_name: str,
    *,
    parameters: list[float] | None = None,
) -> None:
    segment["points_sq_mm"] = copy.deepcopy(samples)
    segment["nurbs_target"] = _nurbs_target(
        samples,
        segment_name=segment_name,
        source_edge_ids=segment["source_edge_ids"],
        parameters=parameters,
    )


def _refresh_edge_fit_evidence(segment: dict, segment_name: str) -> None:
    target = segment["nurbs_target"]
    source_points = copy.deepcopy(target["control_points_local_mm"])
    segment["points_sq_mm"] = source_points
    target["fit_evidence"] = _edge_fit_evidence(
        target,
        segment_name=segment_name,
        source_edge_ids=segment["source_edge_ids"],
        source_points=source_points,
    )


def _edge_fit_evidence(
    target: dict,
    *,
    segment_name: str,
    source_edge_ids: list[str],
    source_points: list[list[float]],
) -> dict:
    source_ids = sorted(source_edge_ids)
    authority = {
        "degree": target["degree"],
        "knots": target["knots"],
        "weights": target["weights"],
        "control_points": target["control_points_local_mm"],
    }
    return {
        "method": "endpoint_constrained_chord_length_least_squares",
        "source_edge_ids": source_ids,
        "source_points_local_mm": copy.deepcopy(source_points),
        "residual": {
            "rms_mm": 0.0,
            "maximum_mm": 0.0,
            "source_to_fit_maximum_mm": 0.0,
            "fit_to_source_maximum_mm": 0.0,
        },
        "tolerance_mm": 0.01,
        "coordinate_frame": "section_local_s_q",
        "units": {
            "coordinates": "mm",
            "residual": "mm",
            "parameter": "normalized_0_1",
        },
        "provenance": {
            "authority": "impeller_v11_6_section_recovery.fit_nurbs_measurement_curve",
            "source_segment_name": segment_name,
            "source_edge_ids": source_ids,
            "source_points_sha256": _test_stable_hash(source_points),
            "nurbs_authority_sha256": hashlib.sha256(
                json.dumps(
                    authority, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
        },
    }


def _serialized_record_lists(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "records" and isinstance(nested, list):
                yield nested
            yield from _serialized_record_lists(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _serialized_record_lists(nested)


def _test_stable_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _evaluate_target_samples(target: dict, count: int) -> list[list[float]]:
    curve = {
        "degree": target["degree"],
        "knots": target["knots"],
        "weights": target["weights"],
        "control_points": target["control_points_local_mm"],
    }
    return [
        evaluate_nurbs_curve(curve, index / (count - 1))
        for index in range(count)
    ]


@lru_cache(maxsize=16)
def _cached_fixture_loop_family(parameters_json: str, defaults_json: str) -> dict:
    import json

    return build_v11_blade_to_blade_loop_family(
        json.loads(parameters_json), json.loads(defaults_json)
    )


def _fixture_loop_family(parameters: dict, defaults: dict) -> dict:
    import json

    return _cached_fixture_loop_family(
        json.dumps(parameters, sort_keys=True, separators=(",", ":")),
        json.dumps(defaults, sort_keys=True, separators=(",", ":")),
    )


def _generated_cap_at_h(
    family: dict, population: str, h: float, edge_name: str
) -> list[list[float]]:
    blade = next(item for item in family["blades"] if item["blade_class"] == population)
    loops = sorted(blade["loops"], key=lambda item: item["h"])
    if h <= loops[0]["h"]:
        lower = upper = loops[0]
    elif h >= loops[-1]["h"]:
        lower = upper = loops[-1]
    else:
        lower, upper = next(
            (left, right)
            for left, right in zip(loops, loops[1:])
            if left["h"] <= h <= right["h"]
        )
    alpha = 0.0 if upper["h"] == lower["h"] else (h - lower["h"]) / (upper["h"] - lower["h"])
    lower_points = _local_cap_points(lower, edge_name)
    upper_points = _local_cap_points(upper, edge_name)
    return [
        [
            (1.0 - alpha) * left[0] + alpha * right[0],
            (1.0 - alpha) * left[1] + alpha * right[1],
        ]
        for left, right in zip(lower_points, upper_points)
    ]


def _local_cap_points(loop: dict, edge_name: str) -> list[list[float]]:
    points = loop["segments"][edge_name]["points_s_q"]
    anchor_s = 0.5 * (points[0][0] + points[-1][0])
    anchor_q = 0.5 * (points[0][1] + points[-1][1])
    scale = loop["streamwise_metric_scale_mm"]
    return [[(point[0] - anchor_s) * scale, point[1] - anchor_q] for point in points]


def _material(value: float, source_id: str) -> dict:
    return {
        "value": value,
        "unit": "mm",
        "source_ids": [source_id],
        "measured": True,
    }


def _attachment(lift: float, width: float, source_id: str, *, material_side: int) -> dict:
    return {
        "lift_samples_mm": [0.98 * lift, lift, 1.02 * lift],
        "width_samples_mm": [0.98 * width, width, 1.02 * width],
        "source_ids": [source_id],
        "source_measurement": True,
        "promotable": True,
        "material_side": material_side,
    }
