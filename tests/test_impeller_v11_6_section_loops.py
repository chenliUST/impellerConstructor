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
    _minimum_angular_cutter_boundary_clearance_deg,
    _source_face_trim_boundary_uv_paths,
    align_loop_orientation,
    decompose_authenticated_open_side_pair,
    decompose_section_loop,
    make_section_loop,
    order_section_edges,
    section_full_source_solid,
    section_source_solid,
    select_authenticated_open_side_pair,
    track_section_family_landmarks,
)


def test_face_specific_trim_marks_non_degenerate_periodic_seam_as_face_local():
    solid = cq.Solid.makeCone(10.0, 5.0, 20.0)
    lateral = next(face for face in solid.Faces() if face.geomType() == "CONE")
    source_edges = {
        f"source_edge_{index:05d}": edge
        for index, edge in enumerate(solid.Edges())
    }

    records = _source_face_trim_boundary_uv_paths(
        lateral, source_edges_by_id=source_edges
    )

    periodic = [
        record
        for record in records
        if record["topology_boundary_kind"] == "periodic_parameter_seam"
    ]
    assert periodic
    assert all(record.get("source_edge_id") for record in periodic)
    assert all(
        record["source_pcurve_chord_error_bound_mm"]
        <= record["source_pcurve_chord_tolerance_mm"]
        for record in records
    )
    assert any(record["source_pcurve_sample_count"] > 17 for record in records)
    periodic_ids = {record["source_edge_id"] for record in periodic}
    assert not any(
        record.get("source_edge_id") in periodic_ids
        and record["topology_boundary_kind"] == "material_shared_edge"
        for record in records
    )


def test_authenticated_open_side_pair_selects_full_curves_without_claiming_closure():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    edges = (
        SectionEdge(
            "side_a_long",
            tuple((float(x), -0.5, 0.0) for x in np.linspace(0.0, 10.0, 17)),
            source_face_ids=("face_a",),
            source_roles=("side_a",),
            provenance_available=True,
            source_curve_exact=True,
        ),
        SectionEdge(
            "side_b_long",
            tuple((float(x), 0.5, 0.0) for x in np.linspace(0.5, 10.0, 17)),
            source_face_ids=("face_b",),
            source_roles=("side_b",),
            provenance_available=True,
            source_curve_exact=True,
        ),
        SectionEdge(
            "side_a_fragment",
            ((3.0, -0.5, 0.0), (4.0, -0.5, 0.0)),
            source_face_ids=("face_a",),
            source_roles=("side_a",),
            provenance_available=True,
            source_curve_exact=True,
        ),
    )

    pair = select_authenticated_open_side_pair(
        edges,
        source_tolerance_mm=1.0e-6,
        local_frame=frame,
    )
    decomposition = decompose_authenticated_open_side_pair(
        pair, maximum_control_count=17
    )

    assert pair.source_kind == "occt_exact_authenticated_open_side_pair"
    assert [edge.edge_id for edge in pair.edges] == ["side_a_long", "side_b_long"]
    assert pair.closure_gap_mm == pytest.approx(math.hypot(0.5, 1.0))
    assert decomposition.direct_curve_constructor_mode is True
    assert decomposition.segment("side_a").source_edge_ids == ("side_a_long",)
    assert decomposition.segment("side_b").source_edge_ids == ("side_b_long",)
    assert decomposition.segment("leading_edge").source_edge_ids == (
        "review_bridge_leading_endpoint_witnesses",
    )


def test_authenticated_open_side_pair_stitches_all_connected_side_fragments():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def fragment(edge_id, role, start, end, offset):
        return SectionEdge(
            edge_id,
            tuple(
                (float(x), offset, 0.0)
                for x in np.linspace(float(start), float(end), 9)
            ),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
        )

    pair = select_authenticated_open_side_pair(
        (
            fragment("side_a_second", "side_a", 5.0, 10.0, -0.5),
            fragment("side_b_first", "side_b", 0.5, 5.0, 0.5),
            fragment("side_a_first", "side_a", 0.0, 5.0, -0.5),
            fragment("side_b_second", "side_b", 5.0, 10.0, 0.5),
            fragment("side_a_isolated", "side_a", 20.0, 21.0, -0.5),
        ),
        source_tolerance_mm=1.0e-6,
        local_frame=frame,
    )
    decomposition = decompose_authenticated_open_side_pair(
        pair, maximum_control_count=17
    )

    assert [edge.edge_id for edge in pair.edges] == [
        "side_a_first",
        "side_a_second",
        "side_b_first",
        "side_b_second",
    ]
    assert decomposition.segment("side_a").source_edge_ids == (
        "side_a_first",
        "side_a_second",
    )
    assert decomposition.segment("side_b").source_edge_ids == (
        "side_b_first",
        "side_b_second",
    )
    assert decomposition.segment("side_a").points_sq_mm[0][0] == pytest.approx(0.0)
    assert decomposition.segment("side_a").points_sq_mm[-1][0] == pytest.approx(10.0)
    assert decomposition.segment("side_b").points_sq_mm[0][0] == pytest.approx(0.5)
    assert decomposition.segment("side_b").points_sq_mm[-1][0] == pytest.approx(10.0)


def test_authenticated_open_side_pair_uses_longest_path_through_minor_occt_branch():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def edge(edge_id, role, first, last):
        return SectionEdge(
            edge_id,
            tuple(
                tuple(float(value) for value in point)
                for point in np.linspace(first, last, 9)
            ),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
        )

    pair = select_authenticated_open_side_pair(
        (
            edge("side_a_first", "side_a", (0.0, -0.5, 0.0), (5.0, -0.5, 0.0)),
            edge("side_a_second", "side_a", (5.0, -0.5, 0.0), (10.0, -0.5, 0.0)),
            edge("side_a_minor_branch", "side_a", (5.0, -0.5, 0.0), (5.0, -0.3, 0.0)),
            edge("side_b", "side_b", (0.0, 0.5, 0.0), (10.0, 0.5, 0.0)),
        ),
        source_tolerance_mm=1.0e-6,
        local_frame=frame,
    )

    assert [edge.edge_id for edge in pair.edges[:2]] == [
        "side_a_first",
        "side_a_second",
    ]
    evidence = pair.orientation_evidence["side_chain_selection"]["side_a"]
    assert evidence["selected_coverage_ratio"] == pytest.approx(10.0 / 10.2)
    assert evidence["discarded_branch_edge_ids"] == ["side_a_minor_branch"]


def test_authenticated_trim_surface_downgrades_disjoint_section_intersection():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    authority = {"trim_boundary_uv_paths": [{"uv": [[0.0, 0.0], [1.0, 0.0]]}]}

    def edge(edge_id, role, start, end, offset):
        return SectionEdge(
            edge_id,
            tuple(
                (float(x), offset, 0.0)
                for x in np.linspace(float(start), float(end), 9)
            ),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
            source_surface_parameter_authority=authority,
        )

    pair = select_authenticated_open_side_pair(
        (
            edge("side_a_primary", "side_a", 0.0, 10.0, -0.5),
            edge("side_a_alternative", "side_a", 20.0, 28.0, -0.5),
            edge("side_b", "side_b", 0.0, 10.0, 0.5),
        ),
        source_tolerance_mm=1.0e-6,
        local_frame=frame,
    )

    evidence = pair.orientation_evidence["side_chain_selection"]["side_a"]
    assert [edge.edge_id for edge in pair.edges[:1]] == ["side_a_primary"]
    assert evidence["selected_coverage_ratio"] == pytest.approx(10.0 / 18.0)
    assert evidence["selected_coverage_gate_applied"] is False
    assert evidence["alternative_intersections_are_geometry_authority"] is False


def test_authenticated_open_side_pair_preserves_source_face_uv_through_chain_ordering():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def fragment(edge_id, role, start, end, offset):
        streamwise = np.linspace(float(start), float(end), 5)
        return SectionEdge(
            edge_id,
            tuple((float(value), offset, 0.0) for value in streamwise),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
            source_parameter_face_id=f"face_{role}",
            source_face_parameter_uv=tuple(
                (float(value), 0.25 if role == "side_a" else 0.75)
                for value in streamwise
            ),
            source_face_parameter_residual_max_mm=1.0e-9,
        )

    pair = select_authenticated_open_side_pair(
        (
            fragment("side_a_second", "side_a", 5.0, 10.0, -0.5),
            fragment("side_a_first_reversed", "side_a", 5.0, 0.0, -0.5),
            fragment("side_b", "side_b", 0.0, 10.0, 0.5),
        ),
        source_tolerance_mm=1.0e-6,
        local_frame=frame,
    )
    decomposition = decompose_authenticated_open_side_pair(pair)

    side_a = decomposition.segment("side_a")
    assert side_a.source_parameter_face_id == "face_side_a"
    assert np.asarray(side_a.source_face_parameter_uv)[:, 0] == pytest.approx(
        np.linspace(0.0, 10.0, 9)
    )
    assert side_a.source_face_parameter_residual_max_mm == pytest.approx(1.0e-9)


def test_authenticated_open_side_pair_rejects_a_truncated_boundary_station():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def edge(edge_id, role, first, last):
        return SectionEdge(
            edge_id,
            tuple(
                tuple(float(value) for value in point)
                for point in np.linspace(first, last, 17)
            ),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
        )

    with pytest.raises(SectionRecoveryError) as caught:
        select_authenticated_open_side_pair(
            (
                edge("side_a_long", "side_a", (0.0, -0.5, 0.0), (30.0, -0.5, 0.0)),
                edge("side_b_short", "side_b", (25.0, 0.5, 0.0), (35.0, 0.5, 0.0)),
            ),
            source_tolerance_mm=1.0e-6,
            local_frame=frame,
        )

    assert caught.value.reason == "v116_section_loop_correspondence_failed"
    assert caught.value.details["side_length_ratio"] < 0.5


def test_authenticated_open_side_pair_rejects_an_incomplete_principal_chain():
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def edge(edge_id, role, start, end, offset):
        return SectionEdge(
            edge_id,
            tuple(
                (float(x), offset, 0.0)
                for x in np.linspace(float(start), float(end), 9)
            ),
            source_face_ids=(f"face_{role}",),
            source_roles=(role,),
            provenance_available=True,
            source_curve_exact=True,
        )

    with pytest.raises(SectionRecoveryError) as caught:
        select_authenticated_open_side_pair(
            (
                edge("side_a_primary", "side_a", 0.0, 10.0, -0.5),
                edge("side_a_secondary", "side_a", 12.0, 20.0, -0.5),
                edge("side_b", "side_b", 0.0, 10.0, 0.5),
            ),
            source_tolerance_mm=1.0e-6,
            local_frame=frame,
        )

    assert caught.value.reason == "v116_section_loop_correspondence_failed"
    assert caught.value.details["selected_coverage_ratio"] < 0.75


def test_bounded_angular_cutter_clearance_uses_expanded_sector_boundaries():
    boundary_angle = math.radians(-1.0)
    boundary = [[10.0 * math.cos(boundary_angle), 10.0 * math.sin(boundary_angle), 0.0]]
    interior_angle = math.radians(5.0)
    interior = [[10.0 * math.cos(interior_angle), 10.0 * math.sin(interior_angle), 0.0]]

    assert _minimum_angular_cutter_boundary_clearance_deg(
        boundary, (0.0, 10.0)
    ) == pytest.approx(0.0, abs=1.0e-10)
    assert _minimum_angular_cutter_boundary_clearance_deg(
        interior, (0.0, 10.0)
    ) == pytest.approx(6.0)


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

    compound_result = section_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        angular_sector_deg=(350.0, 10.0),
        source_faces_by_id=source_faces,
        allowed_source_face_ids=list(source_faces),
        local_frame=frame,
        source_tolerance_mm=1.0e-6,
        edge_sample_count=5,
        source_shape_scope="authenticated_representative_face_compound",
    )
    assert compound_result.source_shape_scope == (
        "authenticated_representative_face_compound"
    )
    assert compound_result.accepted_loop.source_kind == (
        "occt_exact_authenticated_face_compound_section"
    )
    assert compound_result.accepted_loop.source_face_ids == loop.source_face_ids

    sewn_result = section_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        angular_sector_deg=(350.0, 10.0),
        source_faces_by_id=source_faces,
        allowed_source_face_ids=list(source_faces),
        local_frame=frame,
        source_tolerance_mm=1.0e-6,
        edge_sample_count=5,
        source_shape_scope="authenticated_representative_sewn_shell",
    )
    assert sewn_result.source_shape_scope == (
        "authenticated_representative_sewn_shell"
    )
    assert sewn_result.accepted_loop.source_kind == (
        "occt_exact_authenticated_sewn_shell_section"
    )
    assert sewn_result.accepted_loop.source_face_ids == loop.source_face_ids

    individual_result = section_source_solid(
        source,
        gp_Pln(gp_Pnt(0.0, 0.0, 0.5), gp_Dir(0.0, 0.0, 1.0)),
        angular_sector_deg=(350.0, 10.0),
        source_faces_by_id=source_faces,
        allowed_source_face_ids=list(source_faces),
        local_frame=frame,
        source_tolerance_mm=1.0e-6,
        edge_sample_count=5,
        source_shape_scope="authenticated_representative_individual_faces",
    )
    assert individual_result.source_shape_scope == (
        "authenticated_representative_individual_faces"
    )
    assert individual_result.accepted_loop.source_kind == (
        "occt_exact_authenticated_individual_face_section"
    )
    assert individual_result.accepted_loop.source_face_ids == loop.source_face_ids
    assert all(
        edge.topology_start_vertex_id is None
        and edge.topology_end_vertex_id is None
        for edge in individual_result.accepted_loop.edges
    )
    assert individual_result.accepted_loop.closure_gap_mm <= 1.0e-6

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


def test_authenticated_section_can_ignore_an_open_auxiliary_trace_when_a_closed_loop_exists():
    frame = LocalSectionFrame((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    auxiliary = SectionEdge(
        edge_id="auxiliary-root-trace",
        points_xyz_mm=((20.0, 0.0, 0.0), (21.0, 0.0, 0.0)),
        source_face_ids=("root-attachment",),
    )
    loops = order_section_edges(
        [*_rectangle_edges(), auxiliary],
        source_tolerance_mm=1.0e-8,
        local_frame=frame,
        allow_open_auxiliary_components=True,
    )
    assert len(loops) == 1
    assert set(loops[0].source_edge_ids) == {"edge_0", "edge_1", "edge_2", "edge_3"}
