from __future__ import annotations

import math
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_support_recovery import (  # noqa: E402
    SupportRecoveryError,
    authenticate_closed_shroud_topology,
    authenticate_occt_semantic_partition,
    decide_shroud_topology,
    sample_occt_face_meridional_paths,
    sample_occt_shroud_thickness,
    serialize_support_fit_for_v112_mapping,
)


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
                            "face_id": f"side-a-{index}",
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
        assignments[source_id] = {
            "shape": face,
            "role": match["role"] if match else "source_material_boundary",
            "alternatives": [],
            "periodic_instance_id": match.get("periodic_instance_id") if match else None,
            "periodic_blade_related": bool(match and match.get("periodic_blade_related")),
            "flowpath_adjacent": bool(match and match.get("flowpath_adjacent")),
            "root_blend": False,
            "hole_boundary": False,
            "local_edge_treatment": False,
        }
    return authenticate_occt_semantic_partition(source_solid, face_assignments=assignments)


def _shared_edges(first_face, second_face):
    return [
        edge
        for edge in first_face.Edges()
        if any(edge.wrapped.IsSame(other.wrapped) for other in second_face.Edges())
    ]


def _closed_occt_evidence(
    pairs: list[tuple[str, str]],
    expected_instances: list[str] | None = None,
) -> dict:
    cq = pytest.importorskip("cadquery")
    expected_instances = expected_instances or ["blade-0", "blade-1"]
    if len(pairs) == 1:
        outer_body = cq.Solid.makeCone(22.0, 12.0, 20.0)
        inner_void = cq.Solid.makeCone(20.0, 10.0, 20.0)
    else:
        outer_body = cq.Solid.makeCone(22.0, 18.0, 10.0).fuse(
            cq.Solid.makeCone(18.0, 12.0, 10.0, cq.Vector(0.0, 0.0, 10.0))
        )
        inner_void = cq.Solid.makeCone(20.0, 16.0, 10.0).fuse(
            cq.Solid.makeCone(16.0, 10.0, 10.0, cq.Vector(0.0, 0.0, 10.0))
        )
    source_solid = outer_body.cut(inner_void).Solids()[0]
    attachment_z = 10.0 if len(pairs) == 1 else 5.0
    attachment_r = 13.5 if len(pairs) == 1 else 16.5
    for index in range(len(expected_instances)):
        angle_degrees = 360.0 * index / len(expected_instances)
        tab = (
            cq.Workplane("XY")
            .box(3.0, 0.5, 2.0, centered=(False, True, True))
            .translate((attachment_r, 0.0, attachment_z))
            .val()
            .rotate((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), angle_degrees)
        )
        source_solid = source_solid.fuse(tab).Solids()[0]
    conical_faces = [face for face in source_solid.Faces() if face.geomType() == "CONE"]
    conical_faces.sort(
        key=lambda face: (
            round(face.BoundingBox().zmin, 3),
            round(face.BoundingBox().zmax, 3),
            face.BoundingBox().xmax,
        )
    )
    face_bands = {}
    for face in conical_faces:
        bounds = face.BoundingBox()
        face_bands.setdefault((round(bounds.zmin, 3), round(bounds.zmax, 3)), []).append(face)
    ordered_bands = [sorted(faces, key=lambda face: face.BoundingBox().xmax) for _, faces in sorted(face_bands.items())]
    if len(ordered_bands) != len(pairs) or any(len(faces) != 2 for faces in ordered_bands):
        raise AssertionError("closed shroud fixture did not retain paired conical support faces")
    attachment_inner_face = ordered_bands[0][0]
    attachment_faces_and_edges = []
    for face in source_solid.Faces():
        shared = _shared_edges(face, attachment_inner_face)
        if (
            face.geomType() == "PLANE"
            and abs(face.Center().z - (attachment_z + 1.0)) < 1.0e-6
            and face.Area() < 2.0
            and shared
        ):
            attachment_faces_and_edges.append((face, shared[0]))
    attachment_faces_and_edges.sort(
        key=lambda item: math.atan2(item[0].Center().y, item[0].Center().x) % (2.0 * math.pi)
    )
    assert len(attachment_faces_and_edges) == len(expected_instances)
    inner_profiles = []
    outer_profiles = []
    thickness_records = []
    inner_faces = {}
    outer_faces = {}
    for (inner_id, outer_id), (inner_face, outer_face) in zip(pairs, ordered_bands, strict=True):
        inner_faces[inner_id] = inner_face
        outer_faces[outer_id] = outer_face
    selected_partition_faces = [
        {
            "source_id": source_id,
            "shape": face,
            "role": "inner_shroud_flowpath_support",
            "flowpath_adjacent": True,
        }
        for source_id, face in inner_faces.items()
    ] + [
        {
            "source_id": source_id,
            "shape": face,
            "role": "outer_shroud_material_support",
        }
        for source_id, face in outer_faces.items()
    ]
    attachment_chains = {}
    for instance_id, (tip_face, shared_edge) in zip(
        expected_instances,
        attachment_faces_and_edges,
        strict=True,
    ):
        tip_face_id = f"tip-face-{instance_id}"
        selected_partition_faces.append(
            {
                "source_id": tip_face_id,
                "shape": tip_face,
                "role": "periodic_blade_tip_attachment",
                "periodic_instance_id": instance_id,
                "periodic_blade_related": True,
                "flowpath_adjacent": True,
            }
        )
        attachment_chains[instance_id] = {
            "tip_face_id": tip_face_id,
            "tip_face": tip_face,
            "inner_shroud_face_id": pairs[0][0],
            "shared_edge_id": f"tip-inner-edge-{instance_id}",
            "shared_edge": shared_edge,
        }
    partition = _semantic_partition(source_solid, selected_partition_faces)
    for (inner_id, outer_id), (inner_face, outer_face) in zip(pairs, ordered_bands, strict=True):
        inner_profiles.append(
            sample_occt_face_meridional_paths(
                inner_face,
                source_face_id=inner_id,
                source_solid=source_solid,
                semantic_partition_evidence=partition,
                trace_count=5,
                samples_per_trace=33,
            )
        )
        outer_profiles.append(
            sample_occt_face_meridional_paths(
                outer_face,
                source_face_id=outer_id,
                source_solid=source_solid,
                semantic_partition_evidence=partition,
                trace_count=5,
                samples_per_trace=33,
            )
        )
        thickness_records.extend(
            sample_occt_shroud_thickness(
                inner_face,
                outer_face,
                inner_face_id=inner_id,
                outer_face_id=outer_id,
                source_solid=source_solid,
                normalized_uv_stations=[(0.17, 0.25), (0.63, 0.75)],
            )
        )
    topology_evidence = authenticate_closed_shroud_topology(
        source_solid,
        semantic_partition_evidence=partition,
        inner_flowpath_faces=inner_faces,
        outer_material_faces=outer_faces,
        paired_face_ids=pairs,
        blade_tip_attachment_chains=attachment_chains,
        expected_blade_instances=expected_instances,
        thickness_sample_evidence=thickness_records,
    )
    return {
        "inner_profile_evidence": inner_profiles,
        "outer_profile_evidence": outer_profiles,
        "thickness_sample_evidence": thickness_records,
        "topology_evidence": topology_evidence,
    }


def test_large_planar_or_revolved_decoy_face_cannot_trigger_closed_topology():
    result = decide_shroud_topology(
        blade_tip_cap_adjacencies=_tip_cap_adjacencies(),
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
        source_body_is_closed=True,
        candidate_face_metadata=[
            {
                "face_id": "large-decoy",
                "surface_type": "PLANE",
                "area_mm2": 1.0e9,
                "outer_radius_mm": 1.0e5,
                "centroid_radius_mm": 9.0e4,
            },
            {
                "face_id": "revolved-decoy",
                "surface_type": "SURFACE_OF_REVOLUTION",
                "area_mm2": 8.0e8,
            },
        ],
    )

    assert result["status"] == "PASS"
    assert result["decision"] == "open"
    assert result["material_shroud"] is None
    assert result["evidence_checks"]["decisive_closed_evidence_complete"] is False
    assert result["evidence_checks"]["repeated_per_blade_tip_cap_adjacency"] is True
    assert result["tip_cap_evidence"]["source_caps_material"] is True
    assert result["source_body_is_closed"] is True
    assert result["ignored_candidate_metrics"] == ["area_mm2", "centroid_radius_mm", "outer_radius_mm"]


def test_closed_topology_requires_paired_finite_thickness_and_repeated_attachment():
    expected_instances = [f"blade-{index}" for index in range(13)]
    evidence = _closed_occt_evidence(
        [("shroud-inner", "shroud-outer")],
        expected_instances,
    )
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["shroud-inner"],
        outer_material_face_ids=["shroud-outer"],
        paired_face_ids=[("shroud-inner", "shroud-outer")],
        **evidence,
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=expected_instances,
        material_side_normals_consistent=True,
        expected_blade_instances=expected_instances,
    )

    support = result["tip_reference_or_shroud"]
    assert result["status"] == "PASS"
    assert result["decision"] == "closed"
    assert support["semantic_role"] == "closed_shroud"
    assert support["material"] is True
    assert support["inner_flowpath"]["source_face_ids"] == ["shroud-inner"]
    assert support["outer_material"]["source_face_ids"] == ["shroud-outer"]
    assert support["paired_face_ids"] == [["shroud-inner", "shroud-outer"]]
    assert support["thickness"]["finite_positive"] is True
    assert support["thickness"]["mean_mm"] > 0.0
    assert support["thickness"]["sampling_authority"] == "authenticated_occt_paired_face_evaluation"
    assert support["inner_flowpath"]["profile_fit"]["acceptance"]["promoted_pass_eligible"] is True
    assert support["outer_material"]["profile_fit"]["acceptance"]["promoted_pass_eligible"] is True
    assert support["blade_tip_attachment"]["repeated"] is True
    assert support["blade_tip_attachment"]["covers_expected_instances"] is True


def test_two_of_thirteen_tip_attachments_cannot_close_shroud():
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["shroud-inner"],
        outer_material_face_ids=["shroud-outer"],
        paired_face_ids=[("shroud-inner", "shroud-outer")],
        thickness_samples_mm=[1.2, 1.21],
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        material_side_normals_consistent=True,
        expected_blade_instances=13,
    )

    assert result["status"] == "FAIL"
    assert result["decision"] == "ambiguous"
    assert result["evidence_checks"]["attachments_cover_expected_blade_instances"] is False


def test_closed_shroud_requires_expected_instance_contract():
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["shroud-inner"],
        outer_material_face_ids=["shroud-outer"],
        paired_face_ids=[("shroud-inner", "shroud-outer")],
        thickness_samples_mm=[1.2, 1.21],
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        material_side_normals_consistent=True,
    )

    assert result["status"] == "FAIL"
    assert result["evidence_checks"]["attachments_cover_expected_blade_instances"] is False


def test_incomplete_closed_shroud_evidence_fails_as_ambiguous():
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["shroud-inner"],
        outer_material_face_ids=["shroud-outer"],
        thickness_samples_mm=[1.2],
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=0.7,
        circumference_closed=False,
        blade_tip_attachment_instance_ids=["blade-0"],
        material_side_normals_consistent=True,
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
    )

    assert result["status"] == "FAIL"
    assert result["decision"] == "ambiguous"
    assert result["failure_reason"] == "v116_shroud_topology_ambiguous"
    assert result["material_shroud"] is None
    assert result["evidence_checks"]["paired_material_faces"] is False
    assert result["evidence_checks"]["repeated_blade_tip_attachment"] is False


def test_tip_cap_candidates_without_shared_blade_adjacency_are_ambiguous():
    result = decide_shroud_topology(
        blade_tip_cap_adjacencies=[
            {
                "periodic_instance_id": "blade-0",
                "tip_cap_face_id": "tip-cap-0",
                "shared_edge_loops": [],
            },
            {
                "periodic_instance_id": "blade-1",
                "tip_cap_face_id": "tip-cap-1",
                "shared_edge_loops": [],
            },
        ],
        source_body_is_closed=True,
    )

    assert result["status"] == "FAIL"
    assert result["decision"] == "ambiguous"
    assert result["failure_reason"] == "v116_shroud_topology_ambiguous"
    assert result["tip_cap_evidence"]["topological_free_edge_required"] is False


def test_conflicting_tip_cap_and_complete_shroud_evidence_fails():
    evidence = _closed_occt_evidence([("inner", "outer")])
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        **evidence,
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        blade_tip_cap_adjacencies=_tip_cap_adjacencies(2),
        material_side_normals_consistent=True,
        expected_blade_instances=["blade-0", "blade-1"],
    )

    assert result["status"] == "FAIL"
    assert result["decision"] == "ambiguous"
    assert result["failure_reason"] == "v116_shroud_topology_ambiguous"
    assert result["evidence_checks"]["conflicting_open_and_closed_evidence"] is True


def test_zero_or_nonfinite_thickness_cannot_be_closed():
    for samples in ([0.0, 1.0], [float("nan"), 1.0], [-0.2, 1.0]):
        result = decide_shroud_topology(
            inner_flowpath_face_ids=["inner"],
            outer_material_face_ids=["outer"],
            paired_face_ids=[("inner", "outer")],
            thickness_samples_mm=samples,
            inner_circumferential_coverage=1.0,
            outer_circumferential_coverage=1.0,
            circumference_closed=True,
            blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
            material_side_normals_consistent=True,
            expected_blade_instances=["blade-0", "blade-1"],
        )

        assert result["status"] == "FAIL"
        assert result["decision"] == "ambiguous"
        assert result["evidence_checks"]["finite_positive_thickness"] is False


def test_closed_shroud_requires_distinct_fully_paired_inner_outer_faces():
    common = {
        "thickness_samples_mm": [1.0, 1.1],
        "inner_circumferential_coverage": 1.0,
        "outer_circumferential_coverage": 1.0,
        "circumference_closed": True,
        "blade_tip_attachment_instance_ids": ["blade-0", "blade-1"],
        "material_side_normals_consistent": True,
        "expected_blade_instances": ["blade-0", "blade-1"],
    }
    same_face = decide_shroud_topology(
        inner_flowpath_face_ids=["shared-face"],
        outer_material_face_ids=["shared-face"],
        paired_face_ids=[("shared-face", "shared-face")],
        **common,
    )
    incomplete_pairs = decide_shroud_topology(
        inner_flowpath_face_ids=["inner-a", "inner-b"],
        outer_material_face_ids=["outer-a", "outer-b"],
        paired_face_ids=[("inner-a", "outer-a")],
        **common,
    )

    assert same_face["status"] == "FAIL"
    assert same_face["evidence_checks"]["distinct_inner_outer_faces"] is False
    assert incomplete_pairs["status"] == "FAIL"
    assert incomplete_pairs["evidence_checks"]["paired_material_faces"] is False


@pytest.mark.parametrize("coverage", [-0.1, 1.01, float("nan")])
def test_out_of_range_circumferential_coverage_cannot_close(coverage):
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        thickness_samples_mm=[1.0],
        inner_circumferential_coverage=coverage,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        material_side_normals_consistent=True,
        expected_blade_instances=["blade-0", "blade-1"],
    )

    assert result["status"] == "FAIL"
    assert result["evidence_checks"]["bounded_circumferential_coverage"] is False


def test_open_topology_requires_complete_tip_caps_and_bounded_numeric_coverage():
    incomplete = decide_shroud_topology(
        blade_tip_cap_adjacencies=_tip_cap_adjacencies(2),
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
    )
    invalid_coverage = decide_shroud_topology(
        blade_tip_cap_adjacencies=_tip_cap_adjacencies(3),
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
        inner_circumferential_coverage=float("nan"),
    )
    partial_records = _tip_cap_adjacencies(3)
    partial_records[2]["shared_edge_loops"] = []
    partial = decide_shroud_topology(
        blade_tip_cap_adjacencies=partial_records,
        expected_blade_instances=["blade-0", "blade-1", "blade-2"],
    )

    for result in (incomplete, invalid_coverage, partial):
        assert result["status"] == "FAIL"
        assert result["decision"] == "ambiguous"
    assert incomplete["evidence_checks"]["tip_caps_cover_expected_blade_instances"] is False
    assert invalid_coverage["evidence_checks"]["bounded_circumferential_coverage"] is False
    assert partial["tip_cap_evidence"]["repeated_shared_adjacency"] is False


def test_closed_shroud_requires_pair_associated_adequate_thickness_evidence():
    pair_a = ("inner-a", "outer-a")
    pair_b = ("inner-b", "outer-b")
    common = {
        "inner_flowpath_face_ids": ["inner-a", "inner-b"],
        "outer_material_face_ids": ["outer-a", "outer-b"],
        "paired_face_ids": [pair_a, pair_b],
        "thickness_samples_mm": [1.0, 1.1, 1.2, 1.3],
        "inner_circumferential_coverage": 1.0,
        "outer_circumferential_coverage": 1.0,
        "circumference_closed": True,
        "blade_tip_attachment_instance_ids": ["blade-0", "blade-1"],
        "material_side_normals_consistent": True,
        "expected_blade_instances": ["blade-0", "blade-1"],
    }

    unassociated = decide_shroud_topology(**common)
    partial = decide_shroud_topology(
        **common,
        thickness_sample_face_pairs=[pair_a, pair_a, pair_a, pair_a],
    )
    one_per_pair = decide_shroud_topology(
        **{**common, "thickness_samples_mm": [1.0, 1.2]},
        thickness_sample_face_pairs=[pair_a, pair_b],
    )
    complete = decide_shroud_topology(
        **{
            key: value
            for key, value in common.items()
            if key != "thickness_samples_mm"
        },
        **_closed_occt_evidence([pair_a, pair_b]),
    )

    for result in (unassociated, partial, one_per_pair):
        assert result["status"] == "FAIL"
        assert result["decision"] == "ambiguous"
    assert unassociated["evidence_checks"]["thickness_samples_associated_with_face_pairs"] is False
    assert partial["evidence_checks"]["thickness_evidence_covers_all_face_pairs"] is False
    assert one_per_pair["evidence_checks"]["adequate_thickness_samples_per_face_pair"] is False
    assert complete["status"] == "PASS"
    assert complete["decision"] == "closed"
    assert len(complete["material_shroud"]["thickness"]["by_face_pair"]) == 2


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("inner_flowpath_face_ids", "inner"),
        ("outer_material_face_ids", "outer"),
        ("paired_face_ids", "inner-outer"),
        ("paired_face_ids", ["inner", "outer"]),
        ("blade_tip_attachment_instance_ids", "blade-0"),
        ("candidate_face_metadata", "face-metadata"),
        ("thickness_samples_mm", "1.0"),
        ("thickness_sample_face_pairs", "inner-outer"),
    ],
)
def test_shroud_topology_rejects_bare_string_collections_and_pairs(argument, value):
    with pytest.raises(ValueError, match=argument):
        decide_shroud_topology(**{argument: value})


@pytest.mark.parametrize("minimum", [-0.1, 0.0, 1.01, float("nan")])
def test_invalid_closure_threshold_fails(minimum):
    with pytest.raises(ValueError, match="closure_coverage_minimum"):
        decide_shroud_topology(closure_coverage_minimum=minimum)


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("circumference_closed", "false"),
        ("circumference_closed", 1),
        ("material_side_normals_consistent", float("nan")),
        ("material_side_normals_consistent", 0),
        ("source_body_is_closed", "true"),
    ],
)
def test_topology_flags_require_strict_booleans(argument, value):
    with pytest.raises(ValueError, match=argument):
        decide_shroud_topology(**{argument: value})


def test_legacy_or_fabricated_scalar_thickness_cannot_promote_closed_shroud():
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        thickness_samples_mm=[1.0, 1.1],
        thickness_sample_face_pairs=[("inner", "outer"), ("inner", "outer")],
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        material_side_normals_consistent=True,
        expected_blade_instances=["blade-0", "blade-1"],
    )

    assert result["status"] == "FAIL"
    assert result["evidence_checks"]["authenticated_occt_thickness_evidence"] is False
    assert result["evidence_checks"]["inner_outer_profile_evidence_complete"] is False


def test_closed_shroud_rejects_duplicate_authenticated_thickness_sites():
    evidence = _closed_occt_evidence([("inner", "outer")])
    duplicate = evidence["thickness_sample_evidence"][0]

    with pytest.raises(ValueError, match="duplicate sample ids"):
        decide_shroud_topology(
            inner_flowpath_face_ids=["inner"],
            outer_material_face_ids=["outer"],
            paired_face_ids=[("inner", "outer")],
            inner_circumferential_coverage=1.0,
            outer_circumferential_coverage=1.0,
            circumference_closed=True,
            blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
            material_side_normals_consistent=True,
            expected_blade_instances=["blade-0", "blade-1"],
            inner_profile_evidence=evidence["inner_profile_evidence"],
            outer_profile_evidence=evidence["outer_profile_evidence"],
            thickness_sample_evidence=[duplicate, duplicate],
        )


def test_closed_shroud_rejects_plain_partial_or_nan_thickness_evidence():
    malformed = {
        "sample_id": "fake",
        "inner_face_id": "inner",
        "outer_face_id": "outer",
        "normalized_uv_station": [0.2, float("nan")],
        "inner_point_xyz_mm": [0.0, 0.0, 0.0],
        "outer_point_xyz_mm": [1.0, 0.0, 0.0],
        "thickness_mm": 1.0,
    }

    with pytest.raises(ValueError, match="sample_occt_shroud_thickness"):
        decide_shroud_topology(thickness_sample_evidence=[malformed])


def test_closed_shroud_output_keeps_witness_coordinates_and_profile_mapping_targets():
    evidence = _closed_occt_evidence([("inner", "outer")])
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        inner_circumferential_coverage=1.0,
        outer_circumferential_coverage=1.0,
        circumference_closed=True,
        blade_tip_attachment_instance_ids=["blade-0", "blade-1"],
        material_side_normals_consistent=True,
        expected_blade_instances=["blade-0", "blade-1"],
        **evidence,
    )

    support = result["material_shroud"]
    records = support["thickness"]["sample_records"]
    assert result["status"] == "PASS"
    assert len(records) == 2
    assert records[0]["inner_point_xyz_mm"] != records[1]["inner_point_xyz_mm"]
    assert records[0]["normalized_uv_station"] != records[1]["normalized_uv_station"]
    assert records[0]["sampling_authority"] == "occt_paired_trimmed_face_evaluation"
    assert len(support["inner_flowpath"]["profile_fit"]["control_points_rz_mm"]) == 6
    assert len(support["outer_material"]["profile_fit"]["control_points_rz_mm"]) == 6
    assert support["inner_flowpath"]["profile_fit"]["residuals"]["orthogonal_rms_mm"] >= 0.0
    assert all(
        chain["adjacency_authority"] == "occt_exact_shared_edge_identity"
        for chain in support["blade_tip_attachment"]["adjacency_chains"].values()
    )


def test_closed_shroud_capability_serializes_and_adapts_to_strict_mapping_schema():
    from part_rule_synthesis.impeller_v11_6_v112_mapping import _validate_support_fits

    evidence = _closed_occt_evidence([("inner", "outer")])
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        expected_blade_instances=["blade-0", "blade-1"],
        **evidence,
    )
    support = result["material_shroud"]
    mapped = serialize_support_fit_for_v112_mapping(support)

    json.dumps(support, sort_keys=True)
    _validate_support_fits({"hub": mapped, "tip_or_shroud": mapped})
    with pytest.raises(ValueError, match="authenticated result capability"):
        serialize_support_fit_for_v112_mapping(dict(support))


def test_same_occt_face_aliases_cannot_form_multiple_shroud_pairs():
    cq = pytest.importorskip("cadquery")
    source = cq.Solid.makeCone(22.0, 12.0, 20.0).cut(
        cq.Solid.makeCone(20.0, 10.0, 20.0)
    ).Solids()[0]
    inner, outer = sorted(
        (face for face in source.Faces() if face.geomType() == "CONE"),
        key=lambda face: face.BoundingBox().xmax,
    )
    thickness = sample_occt_shroud_thickness(
        inner,
        outer,
        inner_face_id="inner-a",
        outer_face_id="outer-a",
        source_solid=source,
        normalized_uv_stations=[(0.2, 0.25), (0.7, 0.75)],
    )
    partition = _semantic_partition(
        source,
        [
            {
                "source_id": "inner-a",
                "shape": inner,
                "role": "inner_shroud_flowpath_support",
                "flowpath_adjacent": True,
            },
            {
                "source_id": "outer-a",
                "shape": outer,
                "role": "outer_shroud_material_support",
            },
        ],
    )

    with pytest.raises(SupportRecoveryError, match="aliased"):
        authenticate_closed_shroud_topology(
            source,
            semantic_partition_evidence=partition,
            inner_flowpath_faces={"inner-a": inner, "inner-b": inner},
            outer_material_faces={"outer-a": outer, "outer-b": outer},
            paired_face_ids=[("inner-a", "outer-a"), ("inner-b", "outer-b")],
            blade_tip_attachment_chains={"blade-0": {}, "blade-1": {}},
            expected_blade_instances=["blade-0", "blade-1"],
            thickness_sample_evidence=thickness,
        )


def test_thirty_degree_sector_and_plain_full_coverage_cannot_be_closed():
    cq = pytest.importorskip("cadquery")
    source = (
        cq.Workplane("XZ")
        .moveTo(10.0, 0.0)
        .lineTo(12.0, 0.0)
        .lineTo(12.0, 20.0)
        .lineTo(10.0, 20.0)
        .close()
        .revolve(30.0, (0.0, 0.0), (0.0, 1.0))
        .val()
    )
    inner, outer = sorted(
        (face for face in source.Faces() if face.geomType() == "CYLINDER"),
        key=lambda face: face.BoundingBox().xmax,
    )
    plane_faces = [face for face in source.Faces() if face.geomType() == "PLANE"]
    thickness = sample_occt_shroud_thickness(
        inner,
        outer,
        inner_face_id="inner",
        outer_face_id="outer",
        source_solid=source,
        normalized_uv_stations=[(0.2, 0.25), (0.7, 0.75)],
    )
    partition = _semantic_partition(
        source,
        [
            {
                "source_id": "inner",
                "shape": inner,
                "role": "inner_shroud_flowpath_support",
                "flowpath_adjacent": True,
            },
            {
                "source_id": "outer",
                "shape": outer,
                "role": "outer_shroud_material_support",
            },
        ],
    )
    attachment_faces = [face for face in plane_faces if _shared_edges(face, inner)]
    assert len(attachment_faces) >= 2
    attachment_chains = {
        f"blade-{index}": {
            "tip_face_id": f"shell-end-{index}",
            "tip_face": face,
            "inner_shroud_face_id": "inner",
            "shared_edge_id": f"shell-end-edge-{index}",
            "shared_edge": _shared_edges(face, inner)[0],
        }
        for index, face in enumerate(attachment_faces[:2])
    }

    with pytest.raises(SupportRecoveryError, match="not a typed periodic blade-tip face"):
        authenticate_closed_shroud_topology(
            source,
            semantic_partition_evidence=partition,
            inner_flowpath_faces={"inner": inner},
            outer_material_faces={"outer": outer},
            paired_face_ids=[("inner", "outer")],
            blade_tip_attachment_chains=attachment_chains,
            expected_blade_instances=["blade-0", "blade-1"],
            thickness_sample_evidence=thickness,
        )


def test_full_hollow_shell_end_faces_cannot_alias_blade_tip_attachments():
    cq = pytest.importorskip("cadquery")
    source = cq.Solid.makeCone(22.0, 12.0, 20.0).cut(
        cq.Solid.makeCone(20.0, 10.0, 20.0)
    ).Solids()[0]
    inner, outer = sorted(
        (face for face in source.Faces() if face.geomType() == "CONE"),
        key=lambda face: face.BoundingBox().xmax,
    )
    end_faces = [
        face
        for face in source.Faces()
        if face.geomType() == "PLANE" and _shared_edges(face, inner)
    ]
    assert len(end_faces) == 2
    selected = [
        {
            "source_id": "inner",
            "shape": inner,
            "role": "inner_shroud_flowpath_support",
            "flowpath_adjacent": True,
        },
        {
            "source_id": "outer",
            "shape": outer,
            "role": "outer_shroud_material_support",
        },
    ]
    chains = {}
    for index, face in enumerate(end_faces):
        instance_id = f"blade-{index}"
        tip_face_id = f"forged-shell-end-{index}"
        selected.append(
            {
                "source_id": tip_face_id,
                "shape": face,
                "role": "periodic_blade_tip_attachment",
                "periodic_instance_id": instance_id,
                "periodic_blade_related": True,
                "flowpath_adjacent": True,
            }
        )
        chains[instance_id] = {
            "tip_face_id": tip_face_id,
            "tip_face": face,
            "inner_shroud_face_id": "inner",
            "shared_edge_id": f"closed-circular-edge-{index}",
            "shared_edge": _shared_edges(face, inner)[0],
        }
    partition = _semantic_partition(source, selected)
    thickness = sample_occt_shroud_thickness(
        inner,
        outer,
        inner_face_id="inner",
        outer_face_id="outer",
        source_solid=source,
        normalized_uv_stations=[(0.2, 0.25), (0.7, 0.75)],
    )

    with pytest.raises(SupportRecoveryError, match="declared OCCT edge identity"):
        authenticate_closed_shroud_topology(
            source,
            semantic_partition_evidence=partition,
            inner_flowpath_faces={"inner": inner},
            outer_material_faces={"outer": outer},
            paired_face_ids=[("inner", "outer")],
            blade_tip_attachment_chains=chains,
            expected_blade_instances=["blade-0", "blade-1"],
            thickness_sample_evidence=thickness,
        )


def test_explicit_open_source_body_vetoes_closed_shroud_decision():
    evidence = _closed_occt_evidence([("inner", "outer")])
    result = decide_shroud_topology(
        inner_flowpath_face_ids=["inner"],
        outer_material_face_ids=["outer"],
        paired_face_ids=[("inner", "outer")],
        expected_blade_instances=["blade-0", "blade-1"],
        source_body_is_closed=False,
        **evidence,
    )

    assert result["status"] == "FAIL"
    assert result["evidence_checks"]["source_body_closed_from_typed_topology"] is False
