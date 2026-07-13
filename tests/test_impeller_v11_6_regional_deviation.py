from __future__ import annotations

import copy
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

from part_rule_synthesis.impeller_v11_6_deviation import compare_regional_deviation  # noqa: E402


def test_region_mapping_emits_bidirectional_metric_metadata():
    artifact = compare_regional_deviation(_evidence())

    assert artifact["status"] == "accepted"
    assert [region["semantic_role"] for region in artifact["regions"]] == [
        "blade_pressure",
        "shroud_inner",
    ]
    metric = artifact["regions"][0]["distance"]["bidirectional"]
    assert metric["units"] == "mm"
    assert metric["coordinate_frame"] == "source_impeller_xyz_mm"
    assert metric["source_ids"] == ["source-blade-pressure"]
    assert metric["reconstruction_ids"] == ["reconstruction-blade-pressure"]
    assert metric["tessellation_tolerance_mm"] == 0.02
    assert metric["projection_tolerance_mm"] == 0.01
    assert metric["confidence"] == "explicit_measurement_evidence"
    assert metric["directional_aggregation"] == {
        "method": "independent_directional_statistics_fixed_weights",
        "source_to_reconstruction_weight": 0.5,
        "reconstruction_to_source_weight": 0.5,
    }
    assert artifact["silhouettes"]["top"]["value"] == 0.0
    assert artifact["silhouettes"]["meridional"]["value"] == 0.0


def test_weighted_global_uses_unique_source_counts_and_stored_weights():
    evidence = _evidence()
    evidence["source_regions"][0]["weight"] = 1.0
    evidence["source_regions"][1]["weight"] = 3.0
    for sample in evidence["reconstruction_regions"][0]["samples"]:
        sample["point_mm"][2] += 1.0
    evidence["reconstruction_regions"][1]["samples"][0]["point_mm"][2] += 3.0

    artifact = compare_regional_deviation(evidence)

    expected = math.sqrt((2.0 * 1.0**2 + 3.0 * 3.0**2) / (2.0 + 3.0))
    assert artifact["global"]["distance_rms_mm"]["value"] == pytest.approx(expected)
    assert artifact["global"]["weight_basis"]["method"] == (
        "unique_source_region_sample_count_times_stored_weight"
    )
    assert [item["effective_weight"] for item in artifact["global"]["weight_basis"]["regions"]] == [2.0, 3.0]


def test_bidirectional_distance_and_normal_use_fixed_equal_directional_weights():
    artifact = compare_regional_deviation(_asymmetric_regional_evidence())
    blade = artifact["regions"][0]

    for metric_name in ("distance", "normal_angle"):
        metric = blade[metric_name]
        expected_rms = math.sqrt(
            0.5 * metric["source_to_reconstruction"]["rms"] ** 2
            + 0.5 * metric["reconstruction_to_source"]["rms"] ** 2
        )
        assert metric["bidirectional"]["rms"] == pytest.approx(expected_rms)
        assert metric["bidirectional"]["directional_aggregation"] == {
            "method": "independent_directional_statistics_fixed_weights",
            "source_to_reconstruction_weight": 0.5,
            "reconstruction_to_source_weight": 0.5,
        }


@pytest.mark.parametrize("region_field", ["source_regions", "reconstruction_regions"])
def test_duplicate_zero_error_samples_do_not_change_regional_or_global_metrics(region_field):
    evidence = _asymmetric_regional_evidence()
    baseline = compare_regional_deviation(evidence)
    resampled = copy.deepcopy(evidence)
    region = resampled[region_field][0]
    duplicate = copy.deepcopy(region["samples"][0])
    duplicate["sample_id"] = "duplicate-zero-error-sample"
    region["samples"].append(duplicate)
    region["sample_count"] += 1

    artifact = compare_regional_deviation(resampled)

    for metric_name in ("distance", "normal_angle"):
        assert artifact["regions"][0][metric_name]["bidirectional"] == (
            baseline["regions"][0][metric_name]["bidirectional"]
        )
    assert artifact["global"]["distance_rms_mm"]["value"] == baseline["global"][
        "distance_rms_mm"
    ]["value"]
    assert artifact["global"]["normal_angle_rms_deg"]["value"] == baseline[
        "global"
    ]["normal_angle_rms_deg"]["value"]


def test_hidden_nonpositive_thickness_is_terminal_even_when_global_distance_is_low():
    evidence = _evidence()
    evidence["thickness_checks"][0]["reconstruction_thickness_mm"] = 0.0

    artifact = compare_regional_deviation(evidence)

    assert artifact["global"]["distance_rms_mm"]["value"] == 0.0
    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [
        {"code": "nonpositive_thickness", "id": "blade-hidden-thickness"}
    ]


def test_false_open_shroud_is_terminal_even_when_regions_match():
    evidence = _evidence()
    evidence["material_checks"][0].update(
        source_present=False,
        reconstruction_present=True,
    )

    artifact = compare_regional_deviation(evidence)

    assert artifact["global"]["distance_rms_mm"]["value"] == 0.0
    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [{"code": "false_material", "id": "open-shroud"}]


def test_source_material_without_reconstruction_is_terminal_missing_material():
    evidence = _evidence()
    evidence["material_checks"][0].update(
        source_present=True,
        reconstruction_present=False,
    )

    artifact = compare_regional_deviation(evidence)

    assert artifact["global"]["distance_rms_mm"]["value"] == 0.0
    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [
        {"code": "missing_material", "id": "open-shroud"}
    ]


def test_material_absent_from_both_source_and_reconstruction_is_not_terminal():
    evidence = _evidence()
    evidence["material_checks"][0].update(
        source_present=False,
        reconstruction_present=False,
    )

    artifact = compare_regional_deviation(evidence)

    assert artifact["status"] == "accepted"
    assert artifact["terminal_failures"] == []


def test_failed_root_gate_is_terminal_even_when_global_distance_is_low():
    evidence = _evidence()
    evidence["root_gates"][0]["passed"] = False

    artifact = compare_regional_deviation(evidence)

    assert artifact["global"]["distance_rms_mm"]["value"] == 0.0
    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [
        {"code": "failed_root_gate", "id": "blade-root-continuity"}
    ]


def test_missing_mapping_and_station_thickness_are_terminal():
    evidence = _evidence()
    evidence["region_mappings"].pop()
    evidence["stations"][0]["reconstruction_normal_thickness_samples"][0]["thickness_mm"] = 0.0

    artifact = compare_regional_deviation(evidence)

    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [
        {"code": "missing_source_role_mapping", "id": "reconstruction-shroud"},
        {"code": "missing_source_role_mapping", "id": "source-shroud"},
        {"code": "nonpositive_thickness", "id": "h-0.50:reconstruction"},
    ]


def test_global_provenance_excludes_unmapped_regions_that_do_not_contribute():
    evidence = _evidence()
    evidence["region_mappings"].pop()

    artifact = compare_regional_deviation(evidence)

    for metric_name in ("distance_rms_mm", "normal_angle_rms_deg"):
        metric = artifact["global"][metric_name]
        assert metric["source_ids"] == ["source-blade-pressure"]
        assert metric["reconstruction_ids"] == ["reconstruction-blade-pressure"]
    assert artifact["status"] == "terminal_failure"
    assert artifact["terminal_failures"] == [
        {"code": "missing_source_role_mapping", "id": "reconstruction-shroud"},
        {"code": "missing_source_role_mapping", "id": "source-shroud"},
    ]


def test_normals_and_station_metrics_are_explicit_and_numeric():
    evidence = _evidence()
    for sample in evidence["reconstruction_regions"][0]["samples"]:
        sample["normal"] = [0.0, 1.0, 0.0]
    for sample in evidence["reconstruction_regions"][0]["samples"]:
        sample["point_mm"][2] += 2.0
    for sample in evidence["stations"][0]["reconstruction_loop_samples"]:
        sample["point_mm"][2] += 2.0
    for sample in evidence["stations"][0]["reconstruction_camber_samples"]:
        sample["point_mm"][2] += 3.0
    for sample in evidence["stations"][0]["reconstruction_normal_thickness_samples"]:
        sample["thickness_mm"] += 1.0

    artifact = compare_regional_deviation(evidence)
    blade = artifact["regions"][0]
    station = artifact["stations"][0]

    assert blade["normal_angle"]["bidirectional"]["rms"] == pytest.approx(90.0)
    assert station["loop_hausdorff_mm"]["value"] == 2.0
    assert station["camber_rms_mm"]["value"] == 3.0
    assert station["normal_thickness_residual_rms_mm"]["value"] == 1.0
    assert station["loop_hausdorff_mm"]["source_ids"] == ["source-blade-pressure"]


def test_artifact_is_order_invariant_and_hashed_from_the_complete_payload():
    baseline = _evidence()
    reordered = copy.deepcopy(baseline)
    for field in ("source_regions", "reconstruction_regions", "region_mappings", "root_gates", "material_checks", "thickness_checks", "stations"):
        reordered[field].reverse()
    for region in reordered["source_regions"] + reordered["reconstruction_regions"]:
        region["samples"].reverse()
    for station in reordered["stations"]:
        for field in (
            "source_loop_samples",
            "reconstruction_loop_samples",
            "source_camber_samples",
            "reconstruction_camber_samples",
            "source_normal_thickness_samples",
            "reconstruction_normal_thickness_samples",
        ):
            station[field].reverse()
    first = compare_regional_deviation(baseline)
    second = compare_regional_deviation(reordered)

    assert second == first
    assert len(first["sha256"]) == 64
    hash_basis = copy.deepcopy(first)
    actual_sha256 = hash_basis.pop("sha256")
    serialized = json.dumps(
        hash_basis,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert actual_sha256 == hashlib.sha256(serialized.encode("ascii")).hexdigest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("viewport_bounds", {"min": [-1.0] * 3, "max": [1.0] * 3}),
        ("camera", {"position": [1.0, 2.0, 3.0]}),
        ("mesh_proxy", {"vertices": [], "triangles": []}),
        ("unknown_proxy", {"kind": "review_only"}),
    ],
)
def test_top_level_schema_rejects_viewport_camera_and_unknown_proxy(field, value):
    evidence = _evidence()
    evidence[field] = value

    with pytest.raises(ValueError, match=rf"unsupported top-level fields: {field}"):
        compare_regional_deviation(evidence)


def test_station_rejects_blade_to_shroud_region_mispair():
    evidence = _evidence()
    evidence["stations"][0]["reconstruction_region_id"] = "reconstruction-shroud"

    with pytest.raises(ValueError, match="must use an approved region_mapping"):
        compare_regional_deviation(evidence)


def test_station_rejects_same_role_pair_from_different_approved_mappings():
    evidence = _evidence()
    evidence["source_regions"].append(
        _region(
            "source-blade-secondary",
            "blade_pressure",
            "source-blade-pressure-secondary",
            1.0,
            [[2.0, 0.0, 0.0]],
        )
    )
    evidence["reconstruction_regions"].append(
        _region(
            "reconstruction-blade-secondary",
            "blade_pressure",
            "reconstruction-blade-pressure-secondary",
            1.0,
            [[2.0, 0.0, 0.0]],
        )
    )
    evidence["region_mappings"].append(
        {
            "source_region_id": "source-blade-secondary",
            "reconstruction_region_id": "reconstruction-blade-secondary",
            "semantic_role": "blade_pressure",
        }
    )
    evidence["stations"][0][
        "reconstruction_region_id"
    ] = "reconstruction-blade-secondary"

    with pytest.raises(ValueError, match="must use an approved region_mapping"):
        compare_regional_deviation(evidence)


@pytest.mark.parametrize(
    "field",
    ["tessellation_tolerance_mm", "projection_tolerance_mm"],
)
@pytest.mark.parametrize(
    "value",
    [0.0, -0.01, float("nan"), float("inf"), float("-inf")],
    ids=["zero", "negative", "nan", "positive-infinity", "negative-infinity"],
)
def test_tessellation_and_projection_tolerances_must_be_finite_and_positive(field, value):
    evidence = _evidence()
    evidence[field] = value

    with pytest.raises(ValueError):
        compare_regional_deviation(evidence)


def test_top_level_schema_rejects_non_string_field_names_as_value_error():
    evidence = _evidence()
    evidence[17] = "invalid"

    with pytest.raises(ValueError, match="field names"):
        compare_regional_deviation(evidence)


@pytest.mark.parametrize("record_kind", ["mapping", "station"])
def test_unhashable_region_identifiers_fail_at_schema_boundary(record_kind):
    evidence = _evidence()
    if record_kind == "mapping":
        evidence["region_mappings"][0]["source_region_id"] = ["source-blade"]
    else:
        evidence["stations"][0]["reconstruction_region_id"] = [
            "reconstruction-blade"
        ]

    with pytest.raises(ValueError, match="non-empty string"):
        compare_regional_deviation(evidence)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence["source_regions"][0]["samples"].append(
            copy.deepcopy(evidence["source_regions"][0]["samples"][0])
        ),
        lambda evidence: evidence["source_regions"][0]["samples"][0].update(
            point_mm=[float("nan"), 0.0, 0.0]
        ),
        lambda evidence: evidence.update(root_gates=[]),
    ],
)
def test_malformed_nonfinite_duplicate_or_empty_evidence_fails_closed(mutate):
    evidence = _evidence()
    mutate(evidence)

    with pytest.raises(ValueError):
        compare_regional_deviation(evidence)


def _evidence() -> dict:
    return {
        "units": "mm",
        "coordinate_frame": "source_impeller_xyz_mm",
        "tessellation_tolerance_mm": 0.02,
        "projection_tolerance_mm": 0.01,
        "source_regions": [
            _region(
                "source-blade",
                "blade_pressure",
                "source-blade-pressure",
                1.0,
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            ),
            _region(
                "source-shroud",
                "shroud_inner",
                "source-shroud-inner",
                1.0,
                [[0.0, 2.0, 0.0]],
            ),
        ],
        "reconstruction_regions": [
            _region(
                "reconstruction-blade",
                "blade_pressure",
                "reconstruction-blade-pressure",
                1.0,
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            ),
            _region(
                "reconstruction-shroud",
                "shroud_inner",
                "reconstruction-shroud-inner",
                1.0,
                [[0.0, 2.0, 0.0]],
            ),
        ],
        "region_mappings": [
            {
                "source_region_id": "source-blade",
                "reconstruction_region_id": "reconstruction-blade",
                "semantic_role": "blade_pressure",
            },
            {
                "source_region_id": "source-shroud",
                "reconstruction_region_id": "reconstruction-shroud",
                "semantic_role": "shroud_inner",
            },
        ],
        "root_gates": [{"gate_id": "blade-root-continuity", "passed": True}],
        "material_checks": [
            {
                "check_id": "open-shroud",
                "source_present": True,
                "reconstruction_present": True,
            }
        ],
        "thickness_checks": [
            {
                "check_id": "blade-hidden-thickness",
                "source_thickness_mm": 2.0,
                "reconstruction_thickness_mm": 2.0,
            }
        ],
        "stations": [
            {
                "station_id": "h-0.50",
                "source_region_id": "source-blade",
                "reconstruction_region_id": "reconstruction-blade",
                "source_loop_samples": _points("loop", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
                "reconstruction_loop_samples": _points("loop", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
                "source_camber_samples": _points("camber", [[0.0, 0.5, 0.0], [1.0, 0.5, 0.0]]),
                "reconstruction_camber_samples": _points("camber", [[0.0, 0.5, 0.0], [1.0, 0.5, 0.0]]),
                "source_normal_thickness_samples": _thicknesses("thickness", [2.0, 2.2]),
                "reconstruction_normal_thickness_samples": _thicknesses("thickness", [2.0, 2.2]),
            }
        ],
        "silhouettes": {
            "top": {
                "source_id": "source-top-silhouette",
                "reconstruction_id": "reconstruction-top-silhouette",
                "source_samples": _points("top", [[0.0, 0.0], [1.0, 0.0]]),
                "reconstruction_samples": _points("top", [[0.0, 0.0], [1.0, 0.0]]),
            },
            "meridional": {
                "source_id": "source-meridional-silhouette",
                "reconstruction_id": "reconstruction-meridional-silhouette",
                "source_samples": _points("meridional", [[0.0, 0.0], [1.0, 1.0]]),
                "reconstruction_samples": _points("meridional", [[0.0, 0.0], [1.0, 1.0]]),
            },
        },
    }


def _asymmetric_regional_evidence() -> dict:
    evidence = _evidence()
    evidence["reconstruction_regions"][0]["samples"][1].update(
        point_mm=[1.0, 0.0, 2.0],
        normal=[0.0, 1.0, 0.0],
    )
    return evidence


def _region(region_id: str, role: str, identifier: str, weight: float, points: list[list[float]]) -> dict:
    id_field = "source_id" if region_id.startswith("source") else "reconstruction_id"
    return {
        "region_id": region_id,
        "semantic_role": role,
        id_field: identifier,
        "sample_count": len(points),
        "weight": weight,
        "samples": [
            {"sample_id": f"sample-{index}", "point_mm": point, "normal": [0.0, 0.0, 1.0]}
            for index, point in enumerate(points)
        ],
    }


def _points(prefix: str, points: list[list[float]]) -> list[dict]:
    return [{"sample_id": f"{prefix}-{index}", "point_mm": point} for index, point in enumerate(points)]


def _thicknesses(prefix: str, values: list[float]) -> list[dict]:
    return [{"sample_id": f"{prefix}-{index}", "thickness_mm": value} for index, value in enumerate(values)]
