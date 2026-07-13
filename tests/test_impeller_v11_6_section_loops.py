from __future__ import annotations

import math
from dataclasses import replace

import cadquery as cq
import numpy as np
import pytest
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    LocalSectionFrame,
    SectionEdge,
    SectionRecoveryError,
    align_loop_orientation,
    decompose_section_loop,
    make_section_loop,
    order_section_edges,
    section_full_source_solid,
    track_section_family_landmarks,
)


def _rectangle_edges(transform=lambda point: point) -> list[SectionEdge]:
    corners = [(-2.0, -0.5, 0.0), (2.0, -0.5, 0.0), (2.0, 0.5, 0.0), (-2.0, 0.5, 0.0)]
    edges = []
    for index, (first, second) in enumerate(zip(corners, corners[1:] + corners[:1])):
        samples = []
        for fraction in np.linspace(0.0, 1.0, 7):
            point = tuple((1.0 - fraction) * first[axis] + fraction * second[axis] for axis in range(3))
            samples.append(transform(point))
        edges.append(
            SectionEdge(
                edge_id=f"edge_{index}",
                points_xyz_mm=tuple(samples),
                source_face_ids=(f"face_{index}",),
            )
        )
    return edges


def test_edge_ordering_is_deterministic_under_enumeration_and_curve_direction():
    frame = LocalSectionFrame((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    first = order_section_edges(
        _rectangle_edges(), source_tolerance_mm=1.0e-8, local_frame=frame
    )[0]
    shuffled = _rectangle_edges()
    shuffled = [shuffled[2], shuffled[0], shuffled[3], shuffled[1]]
    shuffled[0] = SectionEdge(
        edge_id=shuffled[0].edge_id,
        points_xyz_mm=tuple(reversed(shuffled[0].points_xyz_mm)),
        source_face_ids=shuffled[0].source_face_ids,
    )
    second = order_section_edges(
        shuffled, source_tolerance_mm=1.0e-8, local_frame=frame
    )[0]

    assert first.points_sq_mm == second.points_sq_mm
    assert first.orientation == "counterclockwise"
    assert first.closure_gap_mm == 0.0
    assert first.self_intersection_count == 0


def test_rotated_source_has_the_same_canonical_local_loop():
    angle = math.radians(37.0)

    def rotate(point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        return (
            math.cos(angle) * x - math.sin(angle) * y + 7.0,
            math.sin(angle) * x + math.cos(angle) * y - 3.0,
            z + 2.0,
        )

    frame = LocalSectionFrame(
        rotate((0.0, 0.0, 0.0)),
        (math.cos(angle), math.sin(angle), 0.0),
        (-math.sin(angle), math.cos(angle), 0.0),
        (0.0, 0.0, 1.0),
    )
    canonical = order_section_edges(
        _rectangle_edges(),
        source_tolerance_mm=1.0e-8,
        local_frame=LocalSectionFrame(
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        ),
    )[0]
    rotated = order_section_edges(
        _rectangle_edges(rotate), source_tolerance_mm=1.0e-8, local_frame=frame
    )[0]

    assert np.allclose(rotated.points_sq_mm, canonical.points_sq_mm, atol=1.0e-10)


def test_orientation_scoring_corrects_global_reversal_and_rejects_local_tangent_flip():
    reference = make_section_loop([(-2.0, -0.5), (2.0, -0.5), (2.0, 0.5), (-2.0, 0.5)])
    reversed_candidate = list(reversed(reference.points_sq_mm[:-1]))
    alignment = align_loop_orientation(reference, reversed_candidate)

    assert alignment.reversed is True
    assert alignment.reverse_score < alignment.forward_score
    assert alignment.tangent_mismatch_deg < 1.0

    local_flip = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (-1.0, 0.0)]
    with pytest.raises(SectionRecoveryError) as caught:
        align_loop_orientation(reference, local_flip)
    assert caught.value.reason == "v116_section_tangent_flip_detected"


def test_exact_occt_helper_sections_the_complete_shape_and_retains_face_provenance():
    source = cq.Workplane("XY").box(2.0, 1.0, 1.0).translate((10.0, 0.0, 0.5)).val()
    source_faces = {f"source_face_{index}": face for index, face in enumerate(source.Faces())}
    frame = LocalSectionFrame(
        (10.0, 0.0, 0.5), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    )

    result = section_full_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        angular_sector_deg=(350.0, 10.0),
        source_faces_by_id=source_faces,
        allowed_source_face_ids=list(source_faces),
        local_frame=frame,
        source_tolerance_mm=1.0e-6,
        edge_sample_count=5,
    )

    loop = result.accepted_loop
    assert result.operation == "OCCT_BRepAlgoAPI_Section"
    assert result.source_shape_scope == "complete_source_shape"
    assert result.mesh_used is False
    assert loop.source_kind == "occt_exact_full_source_section"
    assert len(loop.edges) == 4
    assert len(loop.source_face_ids) == 4
    assert all(edge.provenance_available for edge in loop.edges)
    assert all(edge.source_curve_exact for edge in loop.edges)
    assert all(edge.exact_curve is False for edge in loop.edges)
    assert all(edge.sampled_display_only for edge in loop.edges)
    assert all(edge.topology_start_vertex_id for edge in loop.edges)
    assert loop.source_wire_exact is True
    assert loop.display_polyline_exact is False
    assert loop.closure_gap_mm <= 1.0e-6
    payload = result.as_dict()
    assert len(payload["source_edge_records"]) == 4
    assert len(payload["accepted_loop"]["edges"]) == 4
    assert all(record["source_face_ids"] for record in payload["source_edge_records"])
    assert all(record["occt_exact_topology"] for record in payload["source_edge_records"])
    assert all(record["occt_exact_curve"] for record in payload["source_edge_records"])
    assert all(record["sampled_display_only"] for record in payload["source_edge_records"])

    tracked = section_full_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        angular_sector_deg=(350.0, 10.0),
        source_faces_by_id=source_faces,
        allowed_source_face_ids=list(source_faces),
        local_frame=frame,
        source_tolerance_mm=1.0e-6,
        edge_sample_count=5,
        reference_loop=loop,
    )
    assert tracked.landmark_tracking is not None
    assert tracked.landmark_tracking["records"][0]["source_face_ids"]


def test_full_source_section_fails_closed_when_any_section_edge_has_no_known_ancestor():
    source = (
        cq.Workplane("XY")
        .box(4.0, 4.0, 2.0)
        .faces(">Z")
        .workplane()
        .hole(1.0)
        .val()
    )
    all_faces = {f"source_face_{index}": face for index, face in enumerate(source.Faces())}
    incomplete_faces = {
        face_id: face for face_id, face in all_faces.items() if face.geomType() != "CYLINDER"
    }

    with pytest.raises(SectionRecoveryError) as caught:
        section_full_source_solid(
            source,
            gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            source_faces_by_id=incomplete_faces,
            allowed_source_face_ids=list(incomplete_faces),
            source_tolerance_mm=1.0e-6,
            edge_sample_count=9,
        )

    assert caught.value.reason == "v116_section_intersection_failed"
    assert caught.value.details["unresolved_section_edge_count"] >= 1


def test_full_source_section_rejects_missing_face_map_or_allow_list():
    source = cq.Workplane("XY").box(2.0, 1.0, 1.0).val()
    plane = gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0))

    with pytest.raises(SectionRecoveryError) as caught:
        section_full_source_solid(source, plane)
    assert caught.value.reason == "v116_section_intersection_failed"
    assert caught.value.details["source_face_map_present"] is False


def test_pre_heal_junction_gaps_are_retained_instead_of_averaged_away():
    edges = _rectangle_edges()
    shifted = []
    for edge in edges:
        points = np.asarray(edge.points_xyz_mm, dtype=float)
        direction = points[1] - points[0]
        direction /= np.linalg.norm(direction)
        points[0] += 0.01 * direction
        shifted.append(
            SectionEdge(
                edge_id=edge.edge_id,
                points_xyz_mm=tuple(tuple(value) for value in points),
                source_face_ids=edge.source_face_ids,
            )
        )
    loop = order_section_edges(shifted, source_tolerance_mm=0.02)[0]

    assert loop.closure_gap_mm == pytest.approx(0.01)
    assert max(loop.healing_gaps_mm) == pytest.approx(0.01)
    assert loop.healing_total_mm == pytest.approx(0.04)
    assert loop.source_wire_exact is False

    with pytest.raises(SectionRecoveryError) as caught:
        order_section_edges(shifted, source_tolerance_mm=0.005)
    assert caught.value.reason == "v116_section_loop_open"


def test_zero_length_segment_cannot_hide_a_local_backtrack():
    reference = make_section_loop(
        [(-2.0, -0.5), (2.0, -0.5), (2.0, 0.5), (-2.0, 0.5)]
    )
    duplicated_backtrack = [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 0.0),
        (0.0, 0.0),
        (0.0, 1.0),
        (-1.0, 0.0),
    ]
    with pytest.raises(SectionRecoveryError) as caught:
        align_loop_orientation(reference, duplicated_backtrack)
    assert caught.value.reason == "v116_section_tangent_flip_detected"


def test_cross_station_landmark_tracking_records_orientation_and_source_provenance():
    first = make_section_loop(
        [(-2.0, -0.5), (2.0, -0.5), (2.0, 0.5), (-2.0, 0.5)],
        loop_id="h_020",
        source_face_ids=("blade_side_a", "blade_side_b"),
    )
    second = make_section_loop(
        [(-2.1, -0.45), (2.1, -0.45), (2.1, 0.45), (-2.1, 0.45)],
        loop_id="h_050",
        source_face_ids=("blade_side_a", "blade_side_b"),
    )
    evidence = track_section_family_landmarks((first, second), sample_count=64)

    assert evidence["method"] == "cross_station_orientation_and_four_segment_landmark_tracking"
    assert evidence["promotable"] is True
    assert evidence["records"][0]["candidate_loop_id"] == "h_050"
    assert set(evidence["records"][0]["landmarks_sq_mm"]) == {
        "leading_side_a",
        "trailing_side_a",
        "leading_side_b",
        "trailing_side_b",
    }


def test_reference_reversal_fails_when_it_conflicts_with_source_material_side():
    source = cq.Workplane("XY").box(2.0, 1.0, 1.0).translate((10.0, 0.0, 0.5)).val()
    source_faces = {f"source_face_{index}": face for index, face in enumerate(source.Faces())}
    frame = LocalSectionFrame(
        (10.0, 0.0, 0.5), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    )
    arguments = {
        "angular_sector_deg": (350.0, 10.0),
        "source_faces_by_id": source_faces,
        "allowed_source_face_ids": list(source_faces),
        "local_frame": frame,
        "source_tolerance_mm": 1.0e-6,
        "edge_sample_count": 5,
    }
    baseline = section_full_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        **arguments,
    ).accepted_loop
    reversed_reference = replace(
        baseline,
        points_xyz_mm=tuple(reversed(baseline.points_xyz_mm)),
        points_sq_mm=tuple(reversed(baseline.points_sq_mm)),
        edges=tuple(
            replace(
                edge,
                points_xyz_mm=tuple(reversed(edge.points_xyz_mm)),
                points_sq_mm=tuple(reversed(edge.points_sq_mm)),
            )
            for edge in reversed(baseline.edges)
        ),
    )

    with pytest.raises(SectionRecoveryError) as caught:
        section_full_source_solid(
            source,
            gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
            reference_loop=reversed_reference,
            **arguments,
        )

    assert caught.value.reason == "v116_section_orientation_alignment_conflict"
    assert caught.value.details["reversed"] is True


def test_real_section_alignment_returns_one_corrected_loop_for_acceptance_tracking_and_decomposition():
    source = cq.Workplane("XY").box(3.0, 1.0, 1.0).translate((10.0, 0.0, 0.5)).val()
    source_faces = {f"source_face_{index}": face for index, face in enumerate(source.Faces())}
    frame = LocalSectionFrame(
        (10.0, 0.0, 0.5), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    )
    plane = gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0))
    arguments = {
        "angular_sector_deg": (350.0, 10.0),
        "source_faces_by_id": source_faces,
        "allowed_source_face_ids": list(source_faces),
        "local_frame": frame,
        "source_tolerance_mm": 1.0e-6,
        "edge_sample_count": 9,
    }
    baseline = section_full_source_solid(source, plane, **arguments).accepted_loop
    shifted_edges = baseline.edges[1:] + baseline.edges[:1]
    shifted_xyz = np.vstack(
        [
            np.asarray(edge.points_xyz_mm, dtype=float) if index == 0 else np.asarray(edge.points_xyz_mm, dtype=float)[1:]
            for index, edge in enumerate(shifted_edges)
        ]
    )
    shifted_sq = np.vstack(
        [
            np.asarray(edge.points_sq_mm, dtype=float) if index == 0 else np.asarray(edge.points_sq_mm, dtype=float)[1:]
            for index, edge in enumerate(shifted_edges)
        ]
    )
    shifted_reference = replace(
        baseline,
        edges=shifted_edges,
        points_xyz_mm=tuple(tuple(value) for value in shifted_xyz),
        points_sq_mm=tuple(tuple(value) for value in shifted_sq),
        source_edge_ids=tuple(edge.edge_id for edge in shifted_edges),
    )

    alignment = align_loop_orientation(shifted_reference, baseline)
    assert alignment.reversed is False
    assert alignment.circular_shift != 0
    assert alignment.corrected_loop is not None

    result = section_full_source_solid(
        source,
        plane,
        reference_loop=shifted_reference,
        **arguments,
    )
    accepted = result.accepted_loop
    record = result.landmark_tracking["records"][0]
    decomposition = decompose_section_loop(accepted)

    assert alignment.corrected_points_sq_mm == alignment.corrected_loop.points_sq_mm
    assert alignment.corrected_points_sq_mm == accepted.points_sq_mm
    assert record["corrected_points_sq_mm"] == [list(point) for point in accepted.points_sq_mm]
    assert record["decomposition_input_points_sq_mm"] == [list(point) for point in accepted.points_sq_mm]
    assert tuple(record["corrected_source_edge_ids"]) == accepted.source_edge_ids
    assert {face_id for segment in decomposition.segments for face_id in segment.source_face_ids} == set(
        accepted.source_face_ids
    )
    assert accepted.material_side == baseline.material_side
    assert accepted.orientation == baseline.orientation


def test_open_edge_chain_fails_instead_of_being_reported_as_a_section_loop():
    frame = LocalSectionFrame((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    with pytest.raises(SectionRecoveryError) as caught:
        order_section_edges(
            _rectangle_edges()[:-1], source_tolerance_mm=1.0e-8, local_frame=frame
        )
    assert caught.value.reason == "v116_section_loop_open"
