from __future__ import annotations

import math
import json
import sys
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_support_recovery import (  # noqa: E402
    SupportRecoveryError,
    adapt_tip_cap_topology_evidence,
    authenticate_occt_semantic_partition,
    authenticate_open_tip_population_contract,
    decide_shroud_topology,
    evaluate_profile_rz,
    fit_hub_profile,
    recover_open_tip_reference,
    sample_occt_edge_meridional_path,
    sample_occt_face_meridional_paths,
    serialize_support_fit_for_v112_mapping,
    validate_hub_tip_correspondence,
    verify_support_result_manifest_projection,
)


def _semantic_partition(source_solid, selected: list[dict]):
    assignments = {}
    for index, face in enumerate(source_solid.Faces()):
        match = next(
            (
                record
                for record in selected
                if face.wrapped.IsSame(record["shape"].wrapped)
            ),
            None,
        )
        source_id = match["source_id"] if match else f"source-boundary-{index}"
        role = match["role"] if match else "source_material_boundary"
        assignments[source_id] = {
            "shape": face,
            "role": role,
            "alternatives": [],
            "periodic_instance_id": match.get("periodic_instance_id") if match else None,
            "periodic_blade_related": bool(match and match.get("periodic_blade_related")),
            "flowpath_adjacent": bool(match and match.get("flowpath_adjacent")),
            "root_blend": False,
            "hole_boundary": False,
            "local_edge_treatment": False,
        }
    return authenticate_occt_semantic_partition(source_solid, face_assignments=assignments)


def _support_path(sample_count: int, *, z_offset_mm: float = 0.0) -> list[list[float]]:
    values = np.linspace(0.0, 1.0, sample_count)
    return [
        [
            12.5 + 38.5 * math.sin(math.pi * value / 2.0),
            25.0 * math.cos(math.pi * value / 2.0) + z_offset_mm,
        ]
        for value in values
    ]


def _tip_cap_adjacencies(count: int = 3) -> list[dict]:
    return [
        {
            "periodic_instance_id": f"blade-{index}",
            "tip_cap_face_id": f"tip-cap-{index}",
            "shared_edge_loops": [
                {
                    "loop_id": f"tip-loop-{index}",
                    "source_edge_ids": [f"tip-edge-a-{index}", f"tip-edge-b-{index}"],
                    "adjacent_periodic_faces": [
                        {
                            "face_id": f"pressure-{index}",
                            "face_role": "side",
                            "periodic_instance_id": f"blade-{index}",
                        },
                        {
                            "face_id": f"trailing-edge-{index}",
                            "face_role": "edge",
                            "periodic_instance_id": f"blade-{index}",
                        },
                    ],
                }
            ],
        }
        for index in range(count)
    ]


def test_arc_length_weighted_fit_is_invariant_to_tessellation_density():
    coarse = fit_hub_profile(
        [_support_path(41)],
        source_face_ids=["hub-face"],
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
    )
    dense = fit_hub_profile(
        [_support_path(401)],
        source_face_ids=["hub-face"],
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
    )

    parameters = np.linspace(0.0, 1.0, 101)
    coarse_points = np.asarray(evaluate_profile_rz(coarse["control_points_rz_mm"], parameters))
    dense_points = np.asarray(evaluate_profile_rz(dense["control_points_rz_mm"], parameters))

    assert np.max(np.linalg.norm(coarse_points - dense_points, axis=1)) < 0.015
    assert coarse["fit_method"] == "arc_length_weighted_robust_constrained_clamped_cubic"
    assert coarse["weighting"] == "meridional_arc_length_voronoi"
    assert coarse["control_count"] == 6
    assert coarse["degree"] == 3
    assert coarse["endpoint_constraints"] is True
    assert coarse["global_vertex_envelope_fallback_used"] is False
    assert coarse["acceptance"]["status"] == "PASS"
    assert coarse["acceptance"]["promoted_pass_eligible"] is False
    assert coarse["parameterization"] == "global_radial_ordered_meridional_arc_length"
    assert coarse["weights"] == [1.0] * 6
    assert coarse["weights_assumption"] == "v1_1_2_explicit_all_one"
    assert coarse["provenance"]["coordinate_frame"] == "canonical_axis_frame_rz_mm"
    assert coarse["provenance"]["source_to_canonical_transform"] == np.eye(4).tolist()
    assert coarse["provenance"]["projection_fidelity"] == "sampled_projection_not_exact_brep"
    assert coarse["provenance"]["material_domain_explicit"] is True
    assert coarse["accepted_samples"][0]["source_entity_id"] == "hub-face"


def test_split_adjacent_paths_share_one_global_parameterization():
    complete_path = _support_path(161)
    split_paths = [complete_path[:81], complete_path[80:]]
    common = {
        "endpoints_rz_mm": ([12.5, 25.0], [51.0, 0.0]),
        "outer_diameter_mm": 103.2,
        "material_domain_rz_mm": ((12.0, 52.0), (-0.5, 25.5)),
    }

    complete = fit_hub_profile([complete_path], source_face_ids=["hub-complete"], **common)
    split = fit_hub_profile(split_paths, source_face_ids=["hub-first", "hub-second"], **common)
    parameters = np.linspace(0.0, 1.0, 101)
    complete_points = np.asarray(evaluate_profile_rz(complete["control_points_rz_mm"], parameters))
    split_points = np.asarray(evaluate_profile_rz(split["control_points_rz_mm"], parameters))

    assert np.max(np.linalg.norm(complete_points - split_points, axis=1)) < 0.02
    assert split["path_parameter_ranges"][0][0] == pytest.approx(0.0)
    assert 0.1 < split["path_parameter_ranges"][0][1] < 0.9
    assert split["path_parameter_ranges"][0][1] == pytest.approx(
        split["path_parameter_ranges"][1][0]
    )
    assert split["path_parameter_ranges"][1][1] == pytest.approx(1.0)


def test_duplicate_paths_do_not_multiply_fit_weight():
    baseline_path = _support_path(101)
    offset_path = _support_path(101, z_offset_mm=0.04)
    common = {
        "endpoints_rz_mm": ([12.5, 25.0], [51.0, 0.0]),
        "outer_diameter_mm": 103.2,
        "material_domain_rz_mm": ((12.0, 52.0), (-0.5, 25.5)),
    }
    baseline = fit_hub_profile(
        [baseline_path, offset_path],
        source_face_ids=["hub-a", "hub-b"],
        **common,
    )
    duplicated = fit_hub_profile(
        [baseline_path, baseline_path, baseline_path, offset_path],
        source_face_ids=["hub-a", "hub-a-copy-1", "hub-a-copy-2", "hub-b"],
        **common,
    )

    assert duplicated["control_points_rz_mm"] == baseline["control_points_rz_mm"]
    assert duplicated["duplicate_path_normalization"]["duplicate_path_count"] == 2
    assert duplicated["duplicate_path_normalization"]["effective_path_count"] == 2


def test_duplicate_paths_use_explicit_geometry_within_source_tolerance():
    source_tolerance_mm = 1.0e-3
    first = _support_path(101, z_offset_mm=0.00049)
    second = _support_path(101, z_offset_mm=0.00051)

    fit = fit_hub_profile(
        [first, second],
        source_face_ids=["hub-a", "hub-b"],
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
        source_tolerance_mm=source_tolerance_mm,
    )

    normalization = fit["duplicate_path_normalization"]
    assert normalization["method"] == "explicit_resampled_geometric_max_rms_comparison"
    assert normalization["effective_path_count"] == 1
    assert normalization["duplicate_path_count"] == 1
    assert normalization["maximum_distance_limit_mm"] == source_tolerance_mm
    assert normalization["rms_distance_limit_mm"] == source_tolerance_mm


def test_hub_fit_rejects_local_feature_evidence_and_preserves_ordering():
    clean_paths = [_support_path(121, z_offset_mm=offset) for offset in (-0.01, 0.0, 0.01, 0.0)]
    local_feature_path = _support_path(121, z_offset_mm=3.5)

    fit = fit_hub_profile(
        [*clean_paths, local_feature_path],
        source_face_ids=["hub-a", "hub-b", "hub-c", "hub-d", "root-blend"],
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 29.0)),
    )

    controls = np.asarray(fit["control_points_rz_mm"])
    assert np.all(np.diff(controls[:, 0]) >= -1.0e-9)
    assert fit["constraints"]["axial_order"] == "unconstrained"
    assert fit["constraints"]["satisfied"] is True
    assert fit["rejected_sample_count"] > 0
    assert "root-blend" in fit["rejected_source_ids"]
    assert fit["residuals"]["orthogonal_rms_mm"] <= fit["acceptance"]["rms_limit_mm"]
    assert fit["residuals"]["orthogonal_p95_mm"] < 0.1


def test_open_tip_reference_is_non_material_hidden_and_excluded():
    paths = [_support_path(101, z_offset_mm=offset) for offset in (-0.01, 0.0, 0.01)]
    tip_cap_adjacencies = _tip_cap_adjacencies()
    topology = decide_shroud_topology(
        blade_tip_cap_adjacencies=tip_cap_adjacencies,
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
        source_body_is_closed=True,
    )
    tip = recover_open_tip_reference(
        paths,
        source_edge_ids=["tip-edge-a-0", "tip-edge-a-1", "tip-edge-a-2"],
        blade_tip_cap_adjacencies=tip_cap_adjacencies,
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
    )

    assert topology["status"] == "PASS"
    assert topology["decision"] == "open"
    assert topology["material_shroud"] is None
    assert topology["tip_cap_evidence"]["material"] is True
    assert topology["tip_cap_evidence"]["source_caps_material"] is True
    assert topology["tip_cap_evidence"]["shared_adjacency_loop_count"] == 3
    assert topology["source_body_is_closed"] is True
    assert tip["semantic_role"] == "open_tip_reference"
    assert tip["material"] is False
    assert tip["source_tip_caps"]["material"] is True
    assert tip["source_tip_caps"]["shared_edge_loop_ids"] == [
        "tip-loop-0",
        "tip-loop-1",
        "tip-loop-2",
    ]
    assert tip["source_tip_caps"]["shared_source_edge_ids"] == [
        "tip-edge-a-0",
        "tip-edge-a-1",
        "tip-edge-a-2",
        "tip-edge-b-0",
        "tip-edge-b-1",
        "tip-edge-b-2",
    ]
    assert tip["render_default"] == "hidden"
    assert tip["export_default"] == "excluded"
    assert tip["display_policy"]["construction_overlay_only"] is True
    assert tip["profile_fit"]["acceptance"]["status"] == "PASS"
    assert tip["profile_fit"]["global_vertex_envelope_fallback_used"] is False


def test_open_tip_reference_rejects_paths_not_owned_by_shared_tip_cap_loops():
    with pytest.raises(SupportRecoveryError) as caught:
        recover_open_tip_reference(
            [_support_path(51), _support_path(51)],
            source_edge_ids=["unrelated-edge-0", "unrelated-edge-1"],
            blade_tip_cap_adjacencies=_tip_cap_adjacencies(2),
            endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
            outer_diameter_mm=103.2,
        )

    assert caught.value.reason == "v116_tip_reference_inference_failed"


def test_open_tip_reference_requires_fitted_edges_from_every_periodic_instance():
    with pytest.raises(SupportRecoveryError) as caught:
        recover_open_tip_reference(
            [_support_path(51), _support_path(51)],
            source_edge_ids=["tip-edge-a-0", "tip-edge-b-0"],
            blade_tip_cap_adjacencies=_tip_cap_adjacencies(3),
            endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
            outer_diameter_mm=103.2,
            material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
        )

    assert caught.value.reason == "v116_tip_reference_inference_failed"
    assert caught.value.details["fitted_periodic_instance_ids"] == ["blade-0"]


def test_open_tip_promotes_only_when_every_typed_population_loop_is_fitted():
    cq = pytest.importorskip("cadquery")
    from part_rule_synthesis.impeller_v11_6_v112_mapping import _validate_support_fits
    blades = [
        cq.Workplane("XY").box(10.0, 1.0, 2.0).translate((15.0, y, 1.0)).val()
        for y in (-3.0, 3.0)
    ]
    source = cq.Compound.makeCompound(blades)
    records = []
    face_shapes = {}
    edge_shapes = {}
    edge_evidence = []
    expected_loops = {}
    for index, blade in enumerate(blades):
        instance_id = f"blade-{index}"
        cap = max(blade.Faces(), key=lambda face: face.Center().z)
        edge = max(cap.Edges(), key=lambda candidate: candidate.Length())
        adjacent = next(
            face
            for face in blade.Faces()
            if not face.wrapped.IsSame(cap.wrapped)
            and any(candidate.wrapped.IsSame(edge.wrapped) for candidate in face.Edges())
        )
        cap_id = f"tip-cap-{index}"
        adjacent_id = f"side-{index}"
        edge_id = f"tip-edge-{index}"
        loop_id = f"tip-loop-{index}"
        records.append(
            {
                "periodic_instance_id": instance_id,
                "tip_cap_face_id": cap_id,
                "shared_edge_loops": [
                    {
                        "loop_id": loop_id,
                        "source_edge_ids": [edge_id],
                        "adjacent_periodic_faces": [
                            {
                                "face_id": adjacent_id,
                                "face_role": "side",
                                "periodic_instance_id": instance_id,
                            }
                        ],
                    }
                ],
            }
        )
        face_shapes[cap_id] = cap
        face_shapes[adjacent_id] = adjacent
        edge_shapes[edge_id] = edge
        expected_loops[instance_id] = [loop_id]
        edge_evidence.append(
            sample_occt_edge_meridional_path(
                edge,
                source_edge_id=edge_id,
                source_solid=source,
            )
        )
    population = authenticate_open_tip_population_contract(
        source,
        topology_records=records,
        expected_instance_loop_ids=expected_loops,
        source_face_shapes=face_shapes,
        source_edge_shapes=edge_shapes,
    )
    tip = recover_open_tip_reference(
        source_edge_evidence=edge_evidence,
        periodic_population_evidence=population,
        outer_diameter_mm=50.0,
    )

    assert tip["profile_fit"]["acceptance"]["promoted_pass_eligible"] is True
    assert tip["source_tip_caps"]["covers_every_expected_shared_loop"] is True
    mapped_tip = serialize_support_fit_for_v112_mapping(tip)
    _validate_support_fits({"hub": mapped_tip, "tip_or_shroud": mapped_tip})

    with pytest.raises(SupportRecoveryError, match="every periodic blade instance"):
        recover_open_tip_reference(
            source_edge_evidence=edge_evidence[:1],
            periodic_population_evidence=population,
            outer_diameter_mm=50.0,
        )

def test_tip_cap_adapter_rejects_edge_loop_identifier_conflation():
    records = _tip_cap_adjacencies(2)
    records[0]["shared_edge_loops"][0]["source_edge_ids"] = ["tip-loop-0"]

    with pytest.raises(SupportRecoveryError) as caught:
        adapt_tip_cap_topology_evidence(records)

    assert caught.value.reason == "v116_tip_cap_topology_invalid"


def test_tip_cap_adapter_requires_adjacent_periodic_face_instance_ownership():
    records = _tip_cap_adjacencies(2)
    records[0]["shared_edge_loops"][0]["adjacent_periodic_faces"][0][
        "periodic_instance_id"
    ] = "blade-1"

    with pytest.raises(SupportRecoveryError) as caught:
        adapt_tip_cap_topology_evidence(records)

    assert caught.value.reason == "v116_tip_cap_topology_invalid"


def test_tip_cap_adapter_rejects_adjacent_face_reused_by_another_instance():
    records = _tip_cap_adjacencies(2)
    records[1]["shared_edge_loops"][0]["adjacent_periodic_faces"][0]["face_id"] = "pressure-0"

    with pytest.raises(SupportRecoveryError) as caught:
        adapt_tip_cap_topology_evidence(records)

    assert caught.value.reason == "v116_tip_cap_topology_invalid"
    assert "adjacent face" in str(caught.value)


@pytest.mark.parametrize(
    ("operation", "expected_name"),
    [
        (
            lambda: fit_hub_profile(
                [_support_path(41)],
                source_face_ids="hub-face",
                endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
                outer_diameter_mm=103.2,
                material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
            ),
            "source_entity_ids",
        ),
        (
            lambda: fit_hub_profile(
                [_support_path(41)],
                source_face_ids=["hub-face"],
                endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
                outer_diameter_mm=103.2,
                material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
                source_to_canonical_matrix="identity",
            ),
            "source_to_canonical_matrix",
        ),
        (
            lambda: adapt_tip_cap_topology_evidence("tip-cap-records"),
            "records",
        ),
    ],
)
def test_support_recovery_rejects_bare_string_collections_and_provenance(operation, expected_name):
    with pytest.raises(ValueError, match=expected_name):
        operation()


def test_tip_cap_adapter_rejects_bare_string_nested_id_collection():
    records = _tip_cap_adjacencies(2)
    records[0]["shared_edge_loops"][0]["source_edge_ids"] = "tip-edge-a-0"

    with pytest.raises(SupportRecoveryError) as caught:
        adapt_tip_cap_topology_evidence(records)

    assert caught.value.reason == "v116_tip_cap_topology_invalid"
    assert "source_edge_ids" in str(caught.value)


def test_support_fit_fails_when_the_orthogonal_residual_gate_is_exceeded():
    incompatible = _support_path(81)
    for index in range(1, len(incompatible) - 1):
        incompatible[index][1] += 0.8 if index % 2 else -0.8

    with pytest.raises(SupportRecoveryError) as caught:
        fit_hub_profile(
            [incompatible],
            source_face_ids=["damaged-hub"],
            endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
            outer_diameter_mm=20.0,
            material_domain_rz_mm=((12.0, 52.0), (-2.0, 27.0)),
        )

    assert caught.value.reason == "v116_hub_profile_fit_failed"


def test_promoted_support_fit_requires_explicit_material_domain():
    with pytest.raises(SupportRecoveryError) as caught:
        fit_hub_profile(
            [_support_path(41)],
            source_face_ids=["hub-face"],
            endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
            outer_diameter_mm=103.2,
        )

    assert caught.value.reason == "v116_hub_profile_fit_failed"
    assert "explicit material domain" in str(caught.value)


def test_profile_fit_does_not_force_unsupported_axial_monotonicity():
    values = np.linspace(0.0, 1.0, 161)
    path = [
        [12.5 + 38.5 * value, 25.0 * (1.0 - value) + 4.0 * math.sin(2.0 * math.pi * value)]
        for value in values
    ]

    fit = fit_hub_profile(
        [path],
        source_face_ids=["non-axial-monotone-hub"],
        endpoints_rz_mm=(path[0], path[-1]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-1.0, 28.0)),
    )
    axial_differences = np.diff(np.asarray(fit["control_points_rz_mm"])[:, 1])

    assert np.any(axial_differences > 0.0)
    assert np.any(axial_differences < 0.0)
    assert fit["constraints"]["axial_order"] == "unconstrained"
    assert fit["constraints"]["satisfied"] is True


def test_hub_tip_correspondence_is_monotone_and_non_crossing_without_axial_assumption():
    hub = [
        [12.5, 25.0],
        [20.0, 17.0],
        [27.0, 20.0],
        [36.0, 10.0],
        [44.0, 12.0],
        [51.0, 0.0],
    ]
    tip = [[radius + 5.0, axial + 4.0] for radius, axial in hub]
    correspondence = [[value, value] for value in np.linspace(0.0, 1.0, 17)]

    evidence = validate_hub_tip_correspondence(hub, tip, correspondence=correspondence)

    assert evidence["status"] == "PASS"
    assert evidence["flowwise_order_preserved"] is True
    assert evidence["support_curves_non_crossing"] is True
    assert evidence["span_segments_non_crossing"] is True
    assert evidence["axial_monotonicity_required"] is False


def test_hub_tip_correspondence_rejects_crossed_span_mapping():
    hub = [[10.0 + 8.0 * index, 0.0] for index in range(6)]
    tip = [[10.0 + 8.0 * index, 10.0] for index in range(6)]
    crossed = [[0.0, 0.0], [0.25, 0.75], [0.75, 0.25], [1.0, 1.0]]

    with pytest.raises(SupportRecoveryError) as caught:
        validate_hub_tip_correspondence(hub, tip, correspondence=crossed)

    assert caught.value.reason == "v116_support_correspondence_invalid"


def test_hub_tip_correspondence_rejects_geometrically_crossing_supports():
    hub = [[10.0 + 8.0 * index, 0.0] for index in range(6)]
    crossing_tip = [
        [10.0, 10.0],
        [18.0, 10.0],
        [26.0, -10.0],
        [34.0, -10.0],
        [42.0, 10.0],
        [50.0, 10.0],
    ]

    with pytest.raises(SupportRecoveryError) as caught:
        validate_hub_tip_correspondence(hub, crossing_tip)

    assert caught.value.reason == "v116_support_correspondence_invalid"
    assert caught.value.details["support_curves_non_crossing"] is False


def test_hub_tip_correspondence_dense_checks_interpolated_minimum_span():
    hub = [[10.0 + 8.0 * index, 0.0] for index in range(6)]
    tip = [
        [10.0, 10.0],
        [18.0, 0.1],
        [26.0, 0.1],
        [34.0, 0.1],
        [42.0, 0.1],
        [50.0, 10.0],
    ]

    with pytest.raises(SupportRecoveryError) as caught:
        validate_hub_tip_correspondence(
            hub,
            tip,
            correspondence=[[0.0, 0.0], [1.0, 1.0]],
            minimum_span_mm=1.0,
        )

    assert caught.value.reason == "v116_support_correspondence_invalid"
    assert caught.value.details["minimum_measured_span_mm"] < 1.0


def test_sparse_correspondence_rejects_dense_connector_crossing_regression():
    hub = [
        [0, -6.279345],
        [37.554318, -12.180174],
        [73.636749, -15.618527],
        [74.686, 17.577593],
        [74.917747, -2.013854],
        [100, -18.335394],
    ]
    tip = [
        [0, 42.670761],
        [21.703929, 64.072735],
        [34.284364, 50.616124],
        [37.665092, 42.313945],
        [55.032708, 67.170233],
        [100, 67.203716],
    ]

    with pytest.raises(SupportRecoveryError) as caught:
        validate_hub_tip_correspondence(
            hub,
            tip,
            correspondence=[[0.0, 0.0], [1.0, 1.0]],
            intersection_tolerance_mm=1.0e-9,
        )

    assert caught.value.reason == "v116_support_correspondence_invalid"
    assert caught.value.details["span_segments_non_crossing"] is False
    assert caught.value.details["dense_connector_sample_count"] == 513


def test_occt_edge_and_face_helpers_emit_meridional_brep_evidence():
    cq = pytest.importorskip("cadquery")

    edge = cq.Edge.makeLine(cq.Vector(12.5, 0.0, 25.0), cq.Vector(51.0, 0.0, 0.0))
    edge_evidence = sample_occt_edge_meridional_path(edge, source_edge_id="tip-edge", sample_count=17)

    assert edge_evidence["source_edge_id"] == "tip-edge"
    assert edge_evidence["sampling_authority"] == "occt_brep_curve"
    assert edge_evidence["coordinate_frame"] == "canonical_axis_frame_xyz_mm"
    assert edge_evidence["source_to_canonical_transform"] == np.eye(4).tolist()
    assert edge_evidence["source_tolerance_mm"] > 0.0
    assert edge_evidence["points_rz_mm"][0] == pytest.approx([12.5, 25.0])
    assert edge_evidence["points_rz_mm"][-1] == pytest.approx([51.0, 0.0])
    assert edge_evidence["meridional_arc_length_mm"] > 40.0

    cylinder = cq.Workplane("XY").circle(10.0).extrude(5.0).val()
    side = next(face for face in cylinder.Faces() if face.geomType() == "CYLINDER")
    face_evidence = sample_occt_face_meridional_paths(
        side,
        source_face_id="hub-cylinder",
        trace_count=5,
        samples_per_trace=11,
    )

    assert face_evidence["source_face_id"] == "hub-cylinder"
    assert face_evidence["sampling_authority"] == "occt_trimmed_face_classifier"
    assert face_evidence["projection_fidelity"] == "sampled_projection_not_exact_brep"
    assert face_evidence["material_uv_domain_validation"] == "BRepClass_FaceClassifier"
    assert len(face_evidence["paths_rz_mm"]) == 5
    assert all(len(path) == 11 for path in face_evidence["paths_rz_mm"])
    assert all(abs(point[0] - 10.0) < 1.0e-8 for path in face_evidence["paths_rz_mm"] for point in path)
    assert all(abs(normal[2]) < 1.0e-6 for trace in face_evidence["normals_xyz"] for normal in trace)


def test_only_authenticated_trimmed_face_evidence_can_promote_hub_fit():
    cq = pytest.importorskip("cadquery")
    cone = cq.Solid.makeCone(20.0, 10.0, 20.0)
    face = next(candidate for candidate in cone.Faces() if candidate.geomType() == "CONE")
    evidence = sample_occt_face_meridional_paths(
        face,
        source_face_id="hub-cone",
        source_solid=cone,
        semantic_partition_evidence=_semantic_partition(
            cone,
            [{
                "source_id": "hub-cone",
                "shape": face,
                "role": "hub_flowpath_support",
                "flowpath_adjacent": True,
            }],
        ),
        trace_count=5,
        samples_per_trace=41,
    )
    promoted = fit_hub_profile(
        source_face_evidence=[evidence],
        outer_diameter_mm=40.0,
        material_domain_rz_mm=((9.0, 21.0), (-1.0, 21.0)),
    )
    fabricated = fit_hub_profile(
        [_support_path(41)],
        source_face_ids=["not-a-brep-face"],
        endpoints_rz_mm=([12.5, 25.0], [51.0, 0.0]),
        outer_diameter_mm=103.2,
        material_domain_rz_mm=((12.0, 52.0), (-0.5, 25.5)),
        source_sampling_authority="occt_trimmed_face_classifier",
    )

    assert promoted["acceptance"]["promoted_pass_eligible"] is True
    assert promoted["provenance"]["authenticated_occt_trimmed_material_domain"] is True
    assert promoted["provenance"]["source_face_ids"] == ["hub-cone"]
    assert promoted["provenance"]["material_uv_domain_validation"] == "BRepClass_FaceClassifier"
    assert fabricated["acceptance"]["promoted_pass_eligible"] is False
    assert fabricated["provenance"]["authenticated_occt_trimmed_material_domain"] is False


def test_periodic_blade_side_cone_cannot_promote_as_hub_support():
    cq = pytest.importorskip("cadquery")
    cone = cq.Solid.makeCone(20.0, 10.0, 20.0)
    face = next(candidate for candidate in cone.Faces() if candidate.geomType() == "CONE")
    evidence = sample_occt_face_meridional_paths(
        face,
        source_face_id="periodic-blade-side-0",
        source_solid=cone,
        semantic_partition_evidence=_semantic_partition(
            cone,
            [{
                "source_id": "periodic-blade-side-0",
                "shape": face,
                "role": "periodic_blade_side",
                "periodic_instance_id": "blade-0",
                "periodic_blade_related": True,
                "flowpath_adjacent": True,
            }],
        ),
    )

    with pytest.raises((SupportRecoveryError, ValueError)):
        fit_hub_profile(
            source_face_evidence=[evidence],
            outer_diameter_mm=40.0,
            material_domain_rz_mm=((-1000.0, 1000.0), (-1000.0, 1000.0)),
        )


def test_support_mapping_serializer_emits_only_task8_schema_fields():
    cq = pytest.importorskip("cadquery")
    from part_rule_synthesis.impeller_v11_6_v112_mapping import _validate_support_fits

    cone = cq.Solid.makeCone(20.0, 10.0, 20.0)
    face = next(candidate for candidate in cone.Faces() if candidate.geomType() == "CONE")
    evidence = sample_occt_face_meridional_paths(
        face,
        source_face_id="hub-cone",
        source_solid=cone,
        semantic_partition_evidence=_semantic_partition(
            cone,
            [{
                "source_id": "hub-cone",
                "shape": face,
                "role": "hub_flowpath_support",
                "flowpath_adjacent": True,
            }],
        ),
    )
    rich = fit_hub_profile(source_face_evidence=[evidence], outer_diameter_mm=40.0)
    mapped = serialize_support_fit_for_v112_mapping(rich)

    assert set(mapped) == {
        "control_points_rz_mm",
        "residual_rms_mm",
        "source_ids",
        "fit_status",
        "measurement_authority",
    }
    _validate_support_fits({"hub": mapped, "tip_or_shroud": mapped})
    serialized = json.dumps(rich, sort_keys=True)
    assert "payload_digest_sha256" in serialized
    manifest_projection = json.loads(serialized)
    assert verify_support_result_manifest_projection(manifest_projection) is True

    fabricated = dict(rich)
    with pytest.raises(ValueError, match="authenticated result capability"):
        serialize_support_fit_for_v112_mapping(fabricated)
    with pytest.raises(ValueError, match="authenticated result capability"):
        serialize_support_fit_for_v112_mapping(manifest_projection)


def test_source_solid_semantic_partition_is_unique_and_conflicting_reissue_fails():
    cq = pytest.importorskip("cadquery")
    source = cq.Solid.makeCone(20.0, 10.0, 20.0)
    face = next(candidate for candidate in source.Faces() if candidate.geomType() == "CONE")
    _semantic_partition(
        source,
        [{
            "source_id": "hub",
            "shape": face,
            "role": "hub_flowpath_support",
            "flowpath_adjacent": True,
        }],
    )

    with pytest.raises(SupportRecoveryError) as caught:
        _semantic_partition(
            source,
            [{
                "source_id": "blade-side",
                "shape": face,
                "role": "periodic_blade_side",
                "periodic_instance_id": "blade-0",
                "periodic_blade_related": True,
                "flowpath_adjacent": True,
            }],
        )

    assert caught.value.reason == "v116_source_partition_conflict"


def test_trimmed_annular_face_sampling_excludes_uv_hole():
    cq = pytest.importorskip("cadquery")

    annulus = cq.Workplane("XY").circle(10.0).circle(4.0).extrude(1.0).faces(">Z").val()
    evidence = sample_occt_face_meridional_paths(
        annulus,
        source_face_id="annular-face",
        trace_count=9,
        samples_per_trace=81,
        source_tolerance_mm=1.0e-7,
    )
    radii = [
        math.hypot(point[0], point[1])
        for path in evidence["paths_xyz_mm"]
        for point in path
    ]

    assert radii
    assert min(radii) >= 4.0 - 1.0e-7
    assert max(radii) <= 10.0 + 1.0e-7
    assert evidence["discarded_outside_uv_sample_count"] > 0
    assert set(evidence["accepted_classifier_states"]) <= {"IN", "ON"}
