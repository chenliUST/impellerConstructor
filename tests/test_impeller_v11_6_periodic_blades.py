from __future__ import annotations

# ruff: noqa: E402

import math
import copy
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_periodic_blades import (
    PeriodicBladeRecoveryError,
    _bounded_samples,
    recover_periodic_blade_populations,
    select_population_medoid,
)


_ROLES = ("side_a", "side_b", "leading_edge", "trailing_edge")
_ROLE_ANGLE_OFFSETS = {
    "side_a": -1.5,
    "side_b": 1.5,
    "leading_edge": -2.0,
    "trailing_edge": 2.0,
}


def _periodic_fixture(
    *,
    main_count: int,
    main_phase_deg: float,
    splitter_count: int = 0,
    splitter_phase_deg: float = 0.0,
    main_angle_offsets: tuple[float, ...] | None = None,
    angular_span_deg: float = 6.0,
    include_isolated_decoys: bool = False,
    shape_variation: bool = True,
) -> tuple[list[dict], dict[str, list[str]]]:
    records: list[dict] = []
    adjacency: dict[str, list[str]] = {}
    families = [
        ("main", main_count, main_phase_deg, (1.0, 11.0), 18.0),
        ("splitter", splitter_count, splitter_phase_deg, (4.0, 10.0), 10.0),
    ]
    for family, count, phase_deg, streamwise_bounds, wrap_deg in families:
        if count == 0:
            continue
        offsets = main_angle_offsets if family == "main" else None
        shape_offsets = [
            0.04 * (index - count // 2) if shape_variation else 0.0
            for index in range(count)
        ]
        for index in range(count):
            instance_angle = phase_deg + 360.0 * index / count
            if offsets is not None:
                instance_angle += offsets[index]
            face_ids = [f"{family}_{index:02d}_{role}" for role in _ROLES]
            coarse_component_id = f"coarse_{family}_{index:02d}"
            coarse_component = {
                "source_component_id": coarse_component_id,
                "source_entity_ids": face_ids,
                "confidence": {
                    "level": "deterministic_topology_component",
                    "score": 1.0,
                    "status": "ACCEPTED",
                    "all_members_accounted_for": True,
                },
                "coordinate_frame": "canonical_cylindrical_r_theta_z",
                "units": {"linear": "mm", "angular": "deg"},
                "tolerance": {
                    "shared_edge_identity_tolerance_mm": 1.0e-12,
                    "signature_linear_quantization_mm": 0.001,
                },
                "residual": {"transformed_sample_mm": 0.0},
                "provenance": {
                    "authority": "uploaded_step_brep_topology",
                    "source_entity_ids": face_ids,
                    "signature_hashes": [f"blade_{role}" for role in _ROLES],
                },
            }
            for role_index, (role, face_id) in enumerate(
                zip(_ROLES, face_ids, strict=True)
            ):
                role_angle = instance_angle + _ROLE_ANGLE_OFFSETS[role]
                radius = 30.0 + role_index * 0.4 + shape_offsets[index]
                samples = []
                for sample_index in range(2):
                    sample_angle = math.radians(role_angle + sample_index * 0.3)
                    sample_radius = radius + sample_index * 4.0
                    samples.append(
                        [
                            sample_radius * math.cos(sample_angle),
                            sample_radius * math.sin(sample_angle),
                            3.0 + role_index + shape_offsets[index],
                        ]
                    )
                records.append(
                    {
                        "source_face_id": face_id,
                        "signature_hash": f"blade_{role}",
                        "is_periodic": True,
                        "blade_related": True,
                        "periodic_membership": {
                            "status": "accepted_periodic_blade_related",
                            "group_id": f"fixture_{family}_{role}",
                            "closure_within_tolerance": True,
                            "method": "fixture_upstream_periodic_closure",
                        },
                        "coarse_component": coarse_component,
                        # Main and splitter intentionally overlap in face area.
                        "area_mm2": 20.0 if role.startswith("side") else 5.0,
                        "centroid_angle_deg": role_angle,
                        "source_frame_phase_deg": role_angle % 360.0,
                        "canonical_frame_phase_deg": role_angle % 360.0,
                        "phase_frame_evidence": {
                            "source_axis_origin_mm": [0.0, 0.0, 0.0],
                            "source_axis_direction": [0.0, 0.0, 1.0],
                            "source_to_canonical_matrix": [
                                [1.0, 0.0, 0.0, 0.0],
                                [0.0, 1.0, 0.0, 0.0],
                                [0.0, 0.0, 1.0, 0.0],
                                [0.0, 0.0, 0.0, 1.0],
                            ],
                            "handedness": "right_handed",
                            "transform_rule": "source_axis_local_basis_then_rigid_source_to_canonical",
                        },
                        "canonical_surface_samples_mm": samples,
                        "streamwise_bounds_mm": list(streamwise_bounds),
                        "streamwise_coordinate": "canonical_radius_mm",
                        "radial_bounds_mm": [20.0, 45.0],
                        "axial_bounds_mm": [2.0, 10.0],
                        "wrap_deg": wrap_deg,
                        "wrap_evidence": {"method": "fixture_measured_wrap"},
                        "angular_span_deg": angular_span_deg,
                        "angular_span_evidence": {
                            "method": "fixture_measured_face_span"
                        },
                    }
                )
            adjacency[face_ids[0]] = [face_ids[1], face_ids[2]]
            adjacency[face_ids[1]] = [face_ids[0], face_ids[3]]
            adjacency[face_ids[2]] = [face_ids[0], face_ids[3]]
            adjacency[face_ids[3]] = [face_ids[1], face_ids[2]]

    if include_isolated_decoys:
        for index in range(main_count):
            angle_deg = main_phase_deg + 360.0 * index / main_count
            radius = 15.0
            angle_rad = math.radians(angle_deg)
            face_id = f"equal_area_decoy_{index:02d}"
            records.append(
                {
                    "source_face_id": face_id,
                    "signature_hash": "blade_side_a",
                    "is_periodic": True,
                    "blade_related": True,
                    "periodic_membership": {
                        "status": "accepted_periodic_blade_related",
                        "group_id": "fixture_decoy_side_a",
                        "closure_within_tolerance": True,
                        "method": "fixture_upstream_periodic_closure",
                    },
                    "coarse_component": {
                        "source_component_id": f"coarse_decoy_{index:02d}",
                        "source_entity_ids": [face_id],
                        "confidence": {
                            "level": "deterministic_topology_component",
                            "score": 1.0,
                            "status": "ACCEPTED",
                            "all_members_accounted_for": True,
                        },
                        "coordinate_frame": "canonical_cylindrical_r_theta_z",
                        "units": {"linear": "mm", "angular": "deg"},
                        "tolerance": {
                            "shared_edge_identity_tolerance_mm": 1.0e-12,
                            "signature_linear_quantization_mm": 0.001,
                        },
                        "residual": {"transformed_sample_mm": 0.0},
                        "provenance": {
                            "authority": "uploaded_step_brep_topology",
                            "source_entity_ids": [face_id],
                            "signature_hashes": ["blade_side_a"],
                        },
                    },
                    "area_mm2": 20.0,
                    "centroid_angle_deg": angle_deg,
                    "source_frame_phase_deg": angle_deg % 360.0,
                    "canonical_frame_phase_deg": angle_deg % 360.0,
                    "phase_frame_evidence": {
                        "source_axis_origin_mm": [0.0, 0.0, 0.0],
                        "source_axis_direction": [0.0, 0.0, 1.0],
                        "source_to_canonical_matrix": [
                            [1.0, 0.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0, 0.0],
                            [0.0, 0.0, 1.0, 0.0],
                            [0.0, 0.0, 0.0, 1.0],
                        ],
                        "handedness": "right_handed",
                        "transform_rule": "source_axis_local_basis_then_rigid_source_to_canonical",
                    },
                    "canonical_surface_samples_mm": [
                        [
                            radius * math.cos(angle_rad),
                            radius * math.sin(angle_rad),
                            1.0,
                        ]
                    ],
                    "streamwise_bounds_mm": [1.0, 11.0],
                    "streamwise_coordinate": "canonical_radius_mm",
                    "radial_bounds_mm": [14.0, 16.0],
                    "axial_bounds_mm": [0.5, 1.5],
                    "wrap_deg": 0.0,
                    "wrap_evidence": {"method": "fixture_measured_wrap"},
                    "angular_span_deg": 1.0,
                    "angular_span_evidence": {"method": "fixture_measured_face_span"},
                }
            )
            adjacency[face_id] = []
    return records, adjacency


def test_fused_eight_plus_zero_excludes_hub_bridge_but_keeps_root_fillet():
    records, adjacency = _periodic_fixture(main_count=8, main_phase_deg=0.0)
    by_id = {record["source_face_id"]: record for record in records}
    hub_ids = [f"axisymmetric_hub_sector_{index:02d}" for index in range(8)]
    hub_component = {
        "source_component_id": "coarse_axisymmetric_hub_support",
        "source_entity_ids": hub_ids,
        "confidence": {
            "level": "deterministic_topology_component",
            "score": 1.0,
            "status": "ACCEPTED",
        },
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm", "angular": "deg"},
        "tolerance": {
            "shared_edge_identity_tolerance_mm": 1.0e-12,
            "signature_linear_quantization_mm": 0.001,
        },
        "residual": {"transformed_sample_mm": 0.0},
        "provenance": {
            "authority": "uploaded_step_brep_topology",
            "source_entity_ids": hub_ids,
            "signature_hashes": ["axisymmetric_hub_support"],
        },
    }
    for index in range(8):
        side_id = f"main_{index:02d}_side_a"
        side = by_id[side_id]
        root_id = f"main_{index:02d}_root_fillet"
        root = copy.deepcopy(side)
        root.update(
            {
                "source_face_id": root_id,
                "signature_hash": "blade_root_fillet",
                "area_mm2": 3.0,
                "angular_span_deg": 4.0,
                "periodic_membership": {
                    "status": "accepted_periodic_blade_related",
                    "group_id": "fixture_main_root_fillet",
                    "closure_within_tolerance": True,
                    "method": "fixture_upstream_periodic_closure",
                },
            }
        )
        component = side["coarse_component"]
        component["source_entity_ids"].append(root_id)
        component["provenance"]["source_entity_ids"].append(root_id)
        component["provenance"]["signature_hashes"].append("blade_root_fillet")
        root["coarse_component"] = component
        records.append(root)
        adjacency.setdefault(side_id, []).append(root_id)
        adjacency[root_id] = [side_id]

        hub_id = hub_ids[index]
        hub = copy.deepcopy(side)
        hub.update(
                {
                    "source_face_id": hub_id,
                    "signature_hash": "axisymmetric_hub_support",
                    "centroid_angle_deg": 45.0 * index,
                    "source_frame_phase_deg": 45.0 * index,
                    "canonical_frame_phase_deg": 45.0 * index,
                "angular_span_deg": 360.0,
                "coarse_component": hub_component,
                "periodic_membership": {
                    "status": "accepted_periodic_blade_related",
                    "group_id": "fixture_axisymmetric_hub_support",
                    "closure_within_tolerance": True,
                    "method": "fixture_upstream_periodic_closure",
                },
            }
        )
        records.append(hub)
        adjacency[hub_id] = [
            side_id,
            hub_ids[(index - 1) % 8],
            hub_ids[(index + 1) % 8],
        ]
        adjacency[side_id].append(hub_id)

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main_blade_count"] == 8
    assert result["splitter_blade_count"] == 0
    for instance in result["main"]["instances"]:
        assert any(face_id.endswith("root_fillet") for face_id in instance["source_face_ids"])
        assert not any(face_id.startswith("axisymmetric_hub") for face_id in instance["source_face_ids"])


def test_authenticated_single_face_seeds_are_not_production_components():
    records, _ = _periodic_fixture(main_count=8, main_phase_deg=0.0)
    seeds = [record for record in records if record["source_face_id"].endswith("side_a")]
    seed_ids = [record["source_face_id"] for record in seeds]
    for record in seeds:
        face_id = record["source_face_id"]
        component = record["coarse_component"]
        component["source_entity_ids"] = [face_id]
        component["provenance"]["source_entity_ids"] = [face_id]
        component["provenance"]["signature_hashes"] = [record["signature_hash"]]
        record["periodic_seed_certification"] = {
            "status": "ACCEPTED",
            "accepted_as_periodic_blade_seed": True,
            "classification": "authenticated_periodic_blade_face_seed",
            "method": "fixture_authenticated_rotational_seed",
            "source_entity_ids": seed_ids,
        }

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(
            seeds, {face_id: [] for face_id in seed_ids}
        )

    assert raised.value.reason == "v116_periodic_population_ambiguous"
    assert raised.value.evidence["singleton_component_face_ids"] == sorted(seed_ids)


def test_recovers_single_population_without_fabricating_splitters():
    records, adjacency = _periodic_fixture(
        main_count=5,
        main_phase_deg=7.0,
        include_isolated_decoys=True,
    )

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main_blade_count"] == 5
    assert result["splitter_blade_count"] == 0
    assert result["splitter"] is None
    assert all(
        component_id.startswith("coarse_main_")
        for component_id in result["main"]["source_component_ids"]
    )
    assert all(
        instance["source_component_evidence"]["provenance"]["authority"]
        == "uploaded_step_brep_topology"
        for instance in result["main"]["instances"]
    )
    assert result["main"]["pitch_deg"] == pytest.approx(72.0)
    assert result["main"]["phase_deg"] == pytest.approx(7.0)
    assert result["closure_diagnostics"]["all_populations_closed"] is True
    assert result["collision_diagnostics"]["collision_free"] is None
    assert result["collision_diagnostics"]["collision_status"] == "UNKNOWN"
    assert result["collision_diagnostics"]["source_topology_separated"] is True
    assert result["rejected"]["isolated_face_ids"] == [
        f"equal_area_decoy_{index:02d}" for index in range(5)
    ]
    population_face_ids = {
        face_id
        for instance in result["main"]["instances"]
        for face_id in instance["source_face_ids"]
    }
    assert population_face_ids.isdisjoint(result["rejected"]["isolated_face_ids"])
    assert all(
        len(instance["transform_from_representative"]) == 4
        for instance in result["main"]["instances"]
    )


def test_strict_adapter_rejects_missing_coarse_component_evidence():
    records, adjacency = _periodic_fixture(main_count=6, main_phase_deg=0.0)
    records[0].pop("coarse_component")

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(records, adjacency)

    assert raised.value.reason == "v116_periodic_face_signature_contract_invalid"


def test_separates_overlapping_area_main_and_splitter_and_measures_phase():
    records, adjacency = _periodic_fixture(
        main_count=6,
        main_phase_deg=4.0,
        splitter_count=6,
        splitter_phase_deg=39.0,
        angular_span_deg=5.0,
    )

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main_blade_count"] == 6
    assert result["splitter_blade_count"] == 6
    assert result["main"]["streamwise_extent_mm"] == pytest.approx(10.0)
    assert result["splitter"]["streamwise_extent_mm"] == pytest.approx(6.0)
    assert result["main"]["pitch_deg"] == pytest.approx(60.0)
    assert result["splitter"]["pitch_deg"] == pytest.approx(60.0)
    assert result["splitter"]["phase_relative_to_main_deg"] == pytest.approx(35.0)
    assert result["splitter"]["passage_bisector_deviation_deg"] == pytest.approx(5.0)
    assert result["collision_diagnostics"]["collision_free"] is None
    assert result["collision_diagnostics"]["collision_status"] == "UNKNOWN"
    assert result["collision_diagnostics"]["source_topology_separated"] is True


def test_unequal_six_plus_four_reports_phase_distribution_without_bisector():
    records, adjacency = _periodic_fixture(
        main_count=6,
        main_phase_deg=4.0,
        splitter_count=4,
        splitter_phase_deg=24.0,
        angular_span_deg=4.0,
    )

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main_blade_count"] == 6
    assert result["splitter_blade_count"] == 4
    assert result["splitter"]["phase_relative_to_main_deg"] is None
    assert result["splitter"]["passage_bisector_deviation_deg"] is None
    evidence = result["splitter"]["relative_phase_evidence"]
    assert evidence["status"] == "ambiguous_offset_distribution"
    assert evidence["scalar_phase_defined"] is False
    assert evidence["offset_distribution_deg"] == pytest.approx(
        [20.0, 20.0, 50.0, 50.0]
    )


def test_medoid_and_complete_result_are_invariant_to_face_enumeration_order():
    records, adjacency = _periodic_fixture(main_count=5, main_phase_deg=11.0)

    forward = recover_periodic_blade_populations(records, adjacency)
    reversed_result = recover_periodic_blade_populations(
        list(reversed(records)),
        {
            face_id: list(reversed(neighbors))
            for face_id, neighbors in reversed(list(adjacency.items()))
        },
    )

    assert reversed_result == forward
    assert forward["main"]["representative"]["source_face_ids"] == [
        f"main_02_{role}"
        for role in ("leading_edge", "side_a", "side_b", "trailing_edge")
    ]
    assert forward["main"]["representative"]["selection_method"] == (
        "minimum_total_symmetric_blade_side_surface_sample_residual_after_cyclic_alignment"
    )


def test_bounded_surface_samples_are_invariant_to_right_handed_axis_reversal():
    samples = [
        (
            float(index % 5),
            2.0 * math.sin(index * 0.31) - 0.03 * index,
            0.05 * index * index - 0.7 * index,
        )
        for index in range(37)
    ]

    selected = _bounded_samples(samples, 9)
    reversed_frame_samples = [(x, -y, -z) for x, y, z in samples]
    selected_in_reversed_frame = _bounded_samples(reversed_frame_samples, 9)

    assert selected_in_reversed_frame == [(x, -y, -z) for x, y, z in selected]


def test_representative_fit_uses_blade_sides_not_split_root_edge_sampling():
    records, adjacency = _periodic_fixture(
        main_count=5,
        main_phase_deg=7.0,
        shape_variation=False,
    )
    split_edge = next(
        record
        for record in records
        if record["source_face_id"] == "main_00_leading_edge"
    )
    split_edge["canonical_surface_samples_mm"].extend(
        [[44.0 + 0.1 * index, -12.0, 18.0] for index in range(40)]
    )

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main"]["representative"]["selection_method"] == (
        "minimum_total_symmetric_blade_side_surface_sample_residual_after_cyclic_alignment"
    )
    assert max(
        instance["residual_to_representative_mm"]
        for instance in result["main"]["instances"]
    ) == pytest.approx(0.0, abs=1.0e-6)


def test_medoid_tie_break_uses_canonical_lattice_position_after_id_relabeling():
    components = []
    for component_id, angle_deg in (
        ("z_component", 0.0),
        ("a_component", 120.0),
        ("m_component", 240.0),
    ):
        angle = math.radians(angle_deg)
        components.append(
            {
                "source_component_id": component_id,
                "instance_angle_deg": angle_deg,
                "surface_samples_mm": [
                    [10.0 * math.cos(angle), 10.0 * math.sin(angle), 2.0]
                ],
            }
        )

    forward = select_population_medoid(components)
    relabeled = select_population_medoid(
        [
            {
                **component,
                "source_component_id": {
                    "z_component": "a",
                    "a_component": "z",
                    "m_component": "m",
                }[component["source_component_id"]],
            }
            for component in components
        ]
    )

    assert forward["source_component_id"] == "z_component"
    assert relabeled["source_component_id"] == "a"
    assert forward["lattice_index"] == relabeled["lattice_index"] == 0
    assert forward["aligned_geometry_digest"] == relabeled["aligned_geometry_digest"]


def test_rejects_nonclosing_zero_ten_twenty_population():
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=0.0)
    target_angles = (0.0, 10.0, 20.0)
    for record in records:
        face_id = record["source_face_id"]
        instance_index = int(face_id.split("_")[1])
        role = face_id.split("_", 2)[2]
        changed_angle = target_angles[instance_index] + _ROLE_ANGLE_OFFSETS[role]
        record["centroid_angle_deg"] = changed_angle
        record["canonical_frame_phase_deg"] = changed_angle % 360.0
        record["source_frame_phase_deg"] = changed_angle % 360.0

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(
            records, adjacency, closure_tolerance_deg=0.5
        )

    assert raised.value.reason == "v116_periodic_population_ambiguous"
    assert raised.value.evidence["closure"]["within_tolerance"] is False


def test_topology_separation_overrides_swept_angular_envelope_warning():
    records, adjacency = _periodic_fixture(
        main_count=4,
        main_phase_deg=0.0,
        splitter_count=4,
        splitter_phase_deg=5.0,
        angular_span_deg=8.0,
    )

    result = recover_periodic_blade_populations(
        records, adjacency, closure_tolerance_deg=0.5
    )

    assert result["closure_diagnostics"]["all_populations_closed"] is True
    assert result["collision_diagnostics"]["collision_free"] is None
    assert result["collision_diagnostics"]["collision_status"] == "UNKNOWN"
    assert result["collision_diagnostics"]["diagnostic_collision_free"] is False
    assert result["collision_diagnostics"]["collision_count"] == 0
    assert result["collision_diagnostics"]["angular_envelope_warning_count"] >= 1
    assert result["collision_diagnostics"]["minimum_angular_clearance_deg"] < 0.0
    assert result["collision_diagnostics"]["source_topology_separation_checked"] is True
    assert result["collision_diagnostics"]["source_topology_separated"] is True
    assert result["collision_diagnostics"]["exact_brep_collision_checked"] is False
    assert result["collision_diagnostics"]["exact_brep_collision_free"] is None


def test_cross_component_topology_contact_remains_a_collision_failure():
    records, adjacency = _periodic_fixture(
        main_count=4,
        main_phase_deg=0.0,
        splitter_count=4,
        splitter_phase_deg=5.0,
        angular_span_deg=8.0,
    )
    first_main = "main_00_side_a"
    first_splitter = "splitter_00_side_a"
    adjacency[first_main].append(first_splitter)
    adjacency[first_splitter].append(first_main)

    result = recover_periodic_blade_populations(records, adjacency)

    diagnostics = result["collision_diagnostics"]
    assert diagnostics["collision_free"] is False
    assert diagnostics["collision_status"] == "FAIL"
    assert diagnostics["source_topology_separation_checked"] is True
    assert diagnostics["source_topology_separated"] is False
    assert diagnostics["source_topology_contact_pairs"] == [
        {
            "first_source_component_id": "coarse_main_00",
            "second_source_component_id": "coarse_splitter_00",
            "shared_adjacency_pairs": [[first_main, first_splitter]],
        }
    ]


def test_component_collision_envelope_uses_authenticated_blade_side_pair():
    records, adjacency = _periodic_fixture(
        main_count=4,
        main_phase_deg=358.0,
        angular_span_deg=8.0,
    )

    result = recover_periodic_blade_populations(records, adjacency)

    first = min(
        result["main"]["instances"],
        key=lambda item: abs(
            (item["measured_angle_deg"] - 358.0 + 180.0) % 360.0 - 180.0
        ),
    )
    assert first["measured_angle_deg"] == pytest.approx(358.0)
    assert first["angular_span_deg"] == pytest.approx(11.0)
    assert first["angular_envelope_deg"]["method"] == (
        "circular_union_of_face_center_offsets_and_spans"
    )
    assert first["angular_envelope_deg"]["wraps_zero"] is True


def test_consumes_source_frame_signature_schema_directly():
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=9.0)
    for record in records:
        instance_index = record["source_face_id"].split("_")[1]
        record["signature_hash"] += f"_source_variation_{instance_index}"
        record["coarse_component"]["seed_rotational_group_ids"] = [
            "authenticated_fixture_seed_group"
        ]
        record["coarse_component"]["authenticated_population_count"] = 3

    result = recover_periodic_blade_populations(records, adjacency)

    assert result["main_blade_count"] == 3
    assert result["main"]["pitch_deg"] == pytest.approx(120.0)
    assert result["main"]["phase_deg"] == pytest.approx(9.0)
    assert result["main"]["radial_support_range_mm"] == [20.0, 45.0]


def test_strict_adapter_rejects_aliases_and_missing_canonical_samples():
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=0.0)
    samples = records[0].pop("canonical_surface_samples_mm")
    records[0]["surface_samples_mm"] = samples

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(records, adjacency)

    assert raised.value.reason == "v116_periodic_face_signature_contract_invalid"
    assert raised.value.evidence["missing_fields"] == ["canonical_surface_samples_mm"]


@pytest.mark.parametrize(
    "invalid_case",
    ("missing_confidence_status", "nonfinite_score", "zero_tolerance", "placeholder_authority"),
)
def test_strict_component_evidence_rejects_untyped_or_placeholder_values(invalid_case):
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=0.0)
    component = records[0]["coarse_component"]
    if invalid_case == "missing_confidence_status":
        component["confidence"].pop("status")
    elif invalid_case == "nonfinite_score":
        component["confidence"]["score"] = math.nan
    elif invalid_case == "zero_tolerance":
        component["tolerance"]["shared_edge_identity_tolerance_mm"] = 0.0
    else:
        component["provenance"]["authority"] = "placeholder"

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(records, adjacency)

    assert raised.value.reason == "v116_periodic_face_signature_contract_invalid"


def test_requires_accepted_upstream_periodic_blade_membership():
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=0.0)
    for record in records:
        record["is_periodic"] = False
        record["blade_related"] = False
        record["periodic_membership"] = {
            "status": "rejected_by_coarse_periodic_partition",
            "group_id": None,
            "closure_within_tolerance": False,
            "method": "fixture_upstream_periodic_closure",
        }

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(records, adjacency)

    assert raised.value.reason == "v116_periodic_population_ambiguous"


def test_complete_linkage_does_not_chain_nontransitive_component_similarity():
    records, adjacency = _periodic_fixture(main_count=3, main_phase_deg=0.0)
    extents_mm = (10.0, 10.7, 11.4)
    for record in records:
        instance_index = int(record["source_face_id"].split("_")[1])
        record["streamwise_bounds_mm"] = [1.0, 1.0 + extents_mm[instance_index]]

    with pytest.raises(PeriodicBladeRecoveryError) as raised:
        recover_periodic_blade_populations(records, adjacency)

    assert raised.value.reason == "v116_periodic_population_ambiguous"
    assert len(raised.value.evidence["unmatched_component_ids"]) == 3
