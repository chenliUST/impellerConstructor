import sys
from copy import deepcopy
from pathlib import Path

# ruff: noqa: E402

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_2_canonical import (
    evaluate_nurbs_curve,
    evaluate_nurbs_surface,
)
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_2_canonical import (
    canonical_nurbs_from_v11_defaults,
)
from part_rule_synthesis.impeller_v11_6_adaptive_extension import (
    _tensor_product_field,
    build_v116_adaptive_reconstruction_extension,
)
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (
    build_v11_blade_to_blade_loop_family,
    map_v11_domain_sample,
)
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


def test_extension_preserves_measured_span_stations_and_submillimetric_thickness():
    measurements = bundle(station_count=7)
    extension = build_v116_adaptive_reconstruction_extension(measurements)

    assert extension["status"] == "PASS"
    assert extension["span_stations_h"] == pytest.approx(
        [index / 6 for index in range(7)]
    )


def test_extension_preserves_measured_active_to_support_span_mapping_as_nurbs():
    measurements = bundle(station_count=7)
    stations = measurements["section_families"]["main"]["stations"]
    for station in stations:
        station["support_span_h"] = 0.3 + 0.6 * station["h"]

    extension = build_v116_adaptive_reconstruction_extension(measurements)

    assert extension["status"] == "PASS"
    mapping = extension["source_support_span_mapping"]
    assert mapping["kind"] == "nurbs_curve"
    assert mapping["components"] == ["active_h", "support_h"]
    assert mapping["construction_usage"] == (
        "measurement_station_provenance_only"
    )
    for station in stations:
        evaluated = evaluate_nurbs_curve(mapping, station["h"])
        assert evaluated[0] == pytest.approx(station["h"], abs=1.0e-6)
        assert evaluated[1] == pytest.approx(
            station["support_span_h"], abs=1.0e-6
        )


def test_adaptive_domain_mapper_uses_local_attachment_field_not_global_measurement_span():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {
        name: specification["default"]
        for name, specification in runtime["parameters"].items()
    }
    measurements = bundle(station_count=7)
    for station in measurements["section_families"]["main"]["stations"]:
        station["support_span_h"] = 0.3 + 0.6 * station["h"]
    extension = build_v116_adaptive_reconstruction_extension(measurements)
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "v116_step_reconstruction_extension": extension,
    }
    canonical = canonical_nurbs_from_v11_defaults(
        parameters,
        defaults,
        source="v116_adaptive_step_reconstruction_extension",
    )
    defaults["canonical_nurbs_parameterization"] = canonical
    streamwise_s = 0.5
    hub = evaluate_nurbs_curve(
        canonical["support_profiles"]["hub_profile"], streamwise_s
    )
    tip = evaluate_nurbs_curve(
        canonical["support_profiles"]["tip_or_shroud_profile"], streamwise_s
    )

    active_root = map_v11_domain_sample(
        parameters,
        defaults,
        {"s": streamwise_s, "q": 0.0, "h": 0.0},
    )
    active_tip = map_v11_domain_sample(
        parameters,
        defaults,
        {"s": streamwise_s, "q": 0.0, "h": 1.0},
    )
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)
    representative = next(
        blade for blade in family["blades"] if blade["blade_class"] == "main"
    )

    root_lift_mm = evaluate_nurbs_curve(
        extension["root_attachment_field"], streamwise_s
    )[2]
    support_delta = [tip[0] - hub[0], tip[1] - hub[1]]
    support_length = float(np.linalg.norm(support_delta))
    local_root_fraction = root_lift_mm / support_length

    assert active_root == pytest.approx(
        [
            hub[0] + local_root_fraction * support_delta[0],
            0.0,
            hub[1] + local_root_fraction * support_delta[1],
        ],
        abs=1.0e-5,
    )
    assert active_tip == pytest.approx(
        [tip[0], 0.0, tip[1]],
        abs=1.0e-5,
    )
    assert representative["loops"][0]["active_span_fraction"] < 0.3
    assert representative["loops"][-1]["active_span_fraction"] == pytest.approx(1.0)


def test_extension_rejects_splitter_without_population_specific_fields():
    measurements = bundle(station_count=7)
    measurements["section_families"]["splitter"] = deepcopy(
        measurements["section_families"]["main"]
    )

    extension = build_v116_adaptive_reconstruction_extension(measurements)

    assert extension["status"] == "REJECTED"
    assert extension["failure_reason"] == (
        "adaptive_splitter_population_fields_not_implemented"
    )


def test_extension_rejects_an_explicitly_declared_empty_splitter_family():
    measurements = bundle(station_count=7)
    measurements["section_families"]["splitter"] = {"stations": []}

    extension = build_v116_adaptive_reconstruction_extension(measurements)

    assert extension["status"] == "REJECTED"
    assert extension["failure_reason"] == (
        "adaptive_splitter_population_fields_not_implemented"
    )


def test_approved_adaptive_station_contract_passes_loop_validation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {
        name: specification["default"]
        for name, specification in runtime["parameters"].items()
    }
    extension = build_v116_adaptive_reconstruction_extension(bundle(7))
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "v116_step_reconstruction_extension": extension,
    }
    defaults["canonical_nurbs_parameterization"] = canonical_nurbs_from_v11_defaults(
        parameters,
        defaults,
        source="v116_adaptive_step_reconstruction_extension",
    )

    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    assert len(family["span_stations_h"]) == 7
    assert not any(
        failure["reason"] == "v1_1_loop_station_knot_mismatch"
        for failure in validate_v11_loop_family(family)
    )


def test_adaptive_station_contract_rejects_loop_station_mutation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {
        name: specification["default"]
        for name, specification in runtime["parameters"].items()
    }
    extension = build_v116_adaptive_reconstruction_extension(bundle(7))
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "v116_step_reconstruction_extension": extension,
    }
    defaults["canonical_nurbs_parameterization"] = canonical_nurbs_from_v11_defaults(
        parameters,
        defaults,
        source="v116_adaptive_step_reconstruction_extension",
    )
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)
    family["span_stations_h"][3] += 0.01

    assert any(
        failure["reason"] == "v1_1_loop_station_knot_mismatch"
        for failure in validate_v11_loop_family(family)
    )
    assert extension["station_count"] == 7
    assert extension["minimum_thickness_mm"] == pytest.approx(0.24)
    assert extension["minimum_thickness_policy"] == (
        "positive_nurbs_control_hull_lower_bound"
    )
    assert extension["thickness_field"]["minimum_thickness_mm"] == pytest.approx(
        0.24
    )
    root_field = extension["root_attachment_field"]
    assert evaluate_nurbs_curve(root_field, 0.0)[1:] == pytest.approx([0.45, 0.6])
    assert evaluate_nurbs_curve(root_field, 0.5)[1:] == pytest.approx([0.35, 0.7])
    assert evaluate_nurbs_curve(root_field, 1.0)[1:] == pytest.approx([0.4, 0.8])

    for h in extension["span_stations_h"]:
        camber = evaluate_nurbs_surface(extension["blade_skeleton_field"], 0.5, h)
        thickness = evaluate_nurbs_surface(extension["thickness_field"], 0.5, h)
        pose = evaluate_nurbs_surface(extension["pose_field"], 0.5, h)
        assert camber[2] == pytest.approx(4.0 + 2.0 * h, abs=1.0e-5)
        assert thickness[2] == pytest.approx(0.29 + 0.04 * h, abs=1.0e-5)
        assert pose[2] == pytest.approx(20.0 + 10.0 * h, abs=1.0e-5)


def test_extension_rejects_station_counts_outside_review_contract():
    assert build_v116_adaptive_reconstruction_extension(bundle(4))[
        "failure_reason"
    ] == "adaptive_station_count_out_of_range"


@pytest.mark.parametrize("sample_count", [5, 7])
def test_tensor_product_field_has_explicit_u_h_axis_order_for_square_nets(sample_count):
    u = np.linspace(0.0, 1.0, sample_count)
    h = np.linspace(0.0, 1.0, sample_count)
    values_hu = np.asarray(
        [[10.0 * u_value + 2.0 * h_value + 0.25 for u_value in u] for h_value in h]
    )

    field = _tensor_product_field("axis_probe", h, u, values_hu, "q_mm")

    assert evaluate_nurbs_surface(field, 0.25, 0.5)[2] == pytest.approx(3.75, abs=1.0e-5)


def test_adaptive_thickness_downgrades_interpolation_before_negative_overshoot():
    measurements = bundle(station_count=6)
    samples = np.linspace(0.0, 1.0, 7)
    positive_values = [1.0, 0.05, 1.0, 0.05, 1.0, 0.05, 1.0]
    for station in measurements["section_families"]["main"]["stations"]:
        station["normal_thickness"]["samples"] = [
            {"s": float(s), "thickness_mm": value}
            for s, value in zip(samples, positive_values, strict=True)
        ]

    extension = build_v116_adaptive_reconstruction_extension(measurements)

    assert extension["status"] == "PASS"
    assert extension["thickness_field"]["positivity_resolution"] == (
        "linear_positive_control_hull_fallback"
    )
    assert extension["thickness_field"]["positivity_proof"] == (
        "positive_scalar_control_coefficients_with_positive_weights"
    )
    assert min(
        point[2]
        for row in extension["thickness_field"]["control_points"]
        for point in row
    ) > 0.0
    dense = [
        evaluate_nurbs_surface(extension["thickness_field"], u, h)[2]
        for u in np.linspace(0.0, 1.0, 65)
        for h in np.linspace(0.0, 1.0, 65)
    ]
    assert min(dense) > 0.0


def test_unverified_section_closure_is_not_promoted_to_cap_construction_target():
    first = bundle(station_count=7)
    second = deepcopy(first)
    geometry = {
        "degree": 1,
        "knots": [0.0, 0.0, 1.0, 1.0],
        "weights": [1.0, 1.0],
        "control_points_local_mm": [[0.0, 0.0], [1.0, 0.5]],
        "sample_points_local_mm": [[0.0, 0.0], [1.0, 0.5]],
        "measurement_target_only": True,
        "constructor_direct_curve_mode": False,
    }
    for measurements, source_id in ((first, "edge-a"), (second, "renamed-edge")):
        for station in measurements["section_families"]["main"]["stations"]:
            station["decomposition"] = {
                "segments": {
                    "leading_edge": {
                        "nurbs_target": {
                            **deepcopy(geometry),
                            "fit_evidence": {"source_edge_ids": [source_id]},
                        }
                    }
                }
            }

    first_extension = build_v116_adaptive_reconstruction_extension(first)
    second_extension = build_v116_adaptive_reconstruction_extension(second)

    assert first_extension["source_cap_curve_targets"] == second_extension[
        "source_cap_curve_targets"
    ]
    targets = first_extension["source_cap_curve_targets"]
    assert targets["leading_edge"] == []
    assert targets["mode"] == "authenticated_direct_cap_curves_only"
    assert targets["rejected_target_count"] == 7
    assert targets["rejected_targets"][0]["reason"] == (
        "section_closure_has_no_authenticated_direct_cap_curve"
    )


def test_authenticated_direct_cap_curve_is_copied_without_source_identity():
    measurements = bundle(station_count=7)
    geometry = {
        "degree": 3,
        "knots": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0],
        "weights": [1.0, 1.0, 1.0, 1.0],
        "control_points_local_mm": [
            [0.0, 0.0],
            [0.2, 0.1],
            [0.8, 0.4],
            [1.0, 0.5],
        ],
        "sample_points_local_mm": [[0.0, 0.0], [1.0, 0.5]],
        "measurement_target_only": False,
        "constructor_direct_curve_mode": True,
        "fit_evidence": {"source_edge_ids": ["edge-a"]},
    }
    for station in measurements["section_families"]["main"]["stations"]:
        station["decomposition"] = {
            "segments": {"leading_edge": {"nurbs_target": deepcopy(geometry)}}
        }

    extension = build_v116_adaptive_reconstruction_extension(measurements)

    targets = extension["source_cap_curve_targets"]
    assert targets["rejected_target_count"] == 0
    target = targets["leading_edge"][0]["nurbs_target"]
    assert target["degree"] == 3
    assert "fit_evidence" not in target
    assert "sample_points_local_mm" not in target
    assert "measurement_target_only" not in target
    assert "constructor_direct_curve_mode" not in target


def test_cap_target_sample_density_does_not_change_adaptive_constructor_payload():
    first = bundle(station_count=7)
    second = deepcopy(first)
    for measurements, sample_count in ((first, 9), (second, 17)):
        samples = [
            [index / (sample_count - 1), 0.5 * index / (sample_count - 1)]
            for index in range(sample_count)
        ]
        for station in measurements["section_families"]["main"]["stations"]:
            station["decomposition"] = {
                "segments": {
                    "leading_edge": {
                        "nurbs_target": {
                            "degree": 1,
                            "knots": [0.0, 0.0, 1.0, 1.0],
                            "weights": [1.0, 1.0],
                            "control_points_local_mm": [[0.0, 0.0], [1.0, 0.5]],
                            "sample_points_local_mm": samples,
                            "measurement_target_only": True,
                            "constructor_direct_curve_mode": False,
                        }
                    }
                }
            }

    assert build_v116_adaptive_reconstruction_extension(first) == (
        build_v116_adaptive_reconstruction_extension(second)
    )


def test_canonical_uses_extension_only_when_explicitly_opted_in():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {
        name: specification["default"]
        for name, specification in runtime["parameters"].items()
    }
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    legacy = canonical_nurbs_from_v11_defaults(parameters, defaults)
    extension = build_v116_adaptive_reconstruction_extension(bundle(7))
    extended_defaults = {
        **defaults,
        "v116_step_reconstruction_extension": extension,
    }

    extended = canonical_nurbs_from_v11_defaults(
        parameters,
        extended_defaults,
        source="v116_adaptive_step_reconstruction_extension",
    )

    assert extended["section_loop_family"]["span_stations_h"] == pytest.approx(
        [index / 6 for index in range(7)]
    )
    assert extended["blade_skeleton_field"] == extension["blade_skeleton_field"]
    assert extended["thickness_field"] == extension["thickness_field"]
    assert extended["pose_field"] == extension["pose_field"]
    assert extended["active_span_policy"]["root_offset"]["local_size_field"] == (
        extension["root_attachment_field"]
    )
    assert extended["attachment_policy"]["root_to_hub"]["local_size_field"] == (
        extension["root_attachment_field"]
    )
    assert extended["metrics"]["thickness_min_mm"] == pytest.approx(0.24)
    assert extended["adaptive_reconstruction_extension"]["contract_id"] == (
        "impeller_v1_1_6_adaptive_reconstruction_extension"
    )
    assert canonical_nurbs_from_v11_defaults(parameters, defaults) == legacy
    assert build_v116_adaptive_reconstruction_extension(bundle(10))[
        "failure_reason"
    ] == "adaptive_station_count_out_of_range"


def test_legacy_canonical_retains_historical_minimum_thickness_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    canonical = runtime["canonical_nurbs_parameterization"]
    control_minimum = min(
        float(point[2])
        for row in canonical["thickness_field"]["control_points"]
        for point in row
    )

    assert canonical["metrics"]["thickness_min_mm"] == pytest.approx(6.8)
    assert canonical["thickness_field"]["minimum_thickness_mm"] == pytest.approx(1.0)
    assert control_minimum == pytest.approx(6.8)


def bundle(station_count):
    stations = []
    for index in range(station_count):
        h = index / max(station_count - 1, 1)
        samples = [0.0, 0.5, 1.0]
        stations.append(
            {
                "h": h,
                "camber": {
                    "samples": [
                        {"s": s, "q_mm": 8.0 * s + 2.0 * h} for s in samples
                    ]
                },
                "normal_thickness": {
                    "samples": [
                        {"s": s, "thickness_mm": 0.24 + 0.1 * s + 0.04 * h}
                        for s in samples
                    ]
                },
                "pose": {
                    "samples": [
                        {"s": s, "theta_deg": 15.0 + 10.0 * s + 10.0 * h}
                        for s in samples
                    ]
                },
                "source_ids": [f"face-{index}"],
                "decomposition": {"segments": {}},
            }
        )
    return {
        "section_families": {"main": {"stations": stations}},
        "attachments": {
            "root": {
                "streamwise_samples_s": [0.0, 0.5, 1.0],
                "width_samples_mm": [0.45, 0.35, 0.4],
                "lift_samples_mm": [0.6, 0.7, 0.8],
            }
        },
    }
