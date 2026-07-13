from __future__ import annotations

import math

import numpy as np

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    LocalSectionFrame,
    SectionEdge,
    decompose_section_loop,
    fit_nurbs_measurement_curve,
    make_section_loop,
    order_section_edges,
)


def _edge(edge_id: str, role: str, points_sq: np.ndarray) -> SectionEdge:
    points_xyz = np.column_stack([points_sq, np.zeros(len(points_sq))])
    return SectionEdge(
        edge_id=edge_id,
        points_xyz_mm=tuple(tuple(float(value) for value in point) for point in points_xyz),
        source_face_ids=(f"{role}_source_face",),
        source_roles=(role,),
    )


def _source_role_loop():
    streamwise = np.linspace(0.0, 10.0, 65)
    side_a = np.column_stack(
        [streamwise, 0.38 + 0.05 * np.sin(np.pi * streamwise / 10.0)]
    )
    side_b = np.column_stack(
        [streamwise, -0.28 + 0.03 * np.sin(np.pi * streamwise / 10.0)]
    )
    leading = np.asarray([side_b[0], (-0.18, 0.01), (-0.08, 0.27), side_a[0]])
    trailing = np.asarray([side_a[-1], (10.22, 0.31), (10.10, -0.20), side_b[-1]])
    edges = [
        _edge("source_side_a", "side_a", side_a),
        _edge("source_te", "trailing_edge", trailing),
        _edge("source_side_b", "side_b", side_b[::-1]),
        _edge("source_le", "leading_edge", leading),
    ]
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    )
    return order_section_edges(
        [edges[2], edges[0], edges[3], edges[1]],
        source_tolerance_mm=1.0e-8,
        local_frame=frame,
    )[0]


def test_source_face_adjacency_drives_four_segment_measurement_nurbs_fits():
    decomposition = decompose_section_loop(_source_role_loop())

    assert decomposition.landmark_method == "source_face_adjacency"
    assert [segment.name for segment in decomposition.segments] == [
        "side_a",
        "side_b",
        "leading_edge",
        "trailing_edge",
    ]
    assert decomposition.pressure_suction_assigned is False
    assert decomposition.direct_curve_constructor_mode is False
    for segment in decomposition.segments:
        assert segment.fit.measurement_target_only is True
        assert segment.fit.constructor_direct_curve_mode is False
        assert segment.fit.degree in (2, 3)
        assert math.isfinite(segment.fit.residual_rms_mm)
        assert math.isfinite(segment.fit.start_curvature_per_mm)
        assert math.isfinite(segment.fit.end_curvature_per_mm)
        assert segment.fit.fit_sample_count <= 1025
        assert segment.fit.source_sample_count == len(segment.points_sq_mm)
        assert segment.fit.residual_max_mm >= segment.fit.residual_source_to_fit_max_sq_mm
        assert segment.fit.residual_max_mm >= segment.fit.residual_fit_to_source_max_sq_mm
        assert segment.fit.edge_sag_sq_mm >= 0.0
        assert np.isclose(np.linalg.norm(segment.fit.start_tangent_sq), 1.0)
        assert np.isclose(np.linalg.norm(segment.fit.end_tangent_sq), 1.0)


def test_source_shaped_edge_splines_are_retained_as_targets_without_semicircle_assumption():
    decomposition = decompose_section_loop(_source_role_loop())
    leading = decomposition.segment("leading_edge")
    trailing = decomposition.segment("trailing_edge")

    assert min(point[0] for point in leading.points_sq_mm) < -0.15
    assert max(point[0] for point in trailing.points_sq_mm) > 10.20
    assert len(leading.fit.control_points_sq_mm) == len(leading.points_sq_mm)
    assert len(trailing.fit.control_points_sq_mm) == len(trailing.points_sq_mm)


def test_geometry_landmark_fallback_still_produces_four_consistently_oriented_segments():
    parameter = np.linspace(0.0, 2.0 * np.pi, 129, endpoint=False)
    loop = make_section_loop(
        np.column_stack([5.0 - 5.0 * np.cos(parameter), 0.45 * np.sin(parameter)])
    )
    decomposition = decompose_section_loop(loop)
    side_a = decomposition.segment("side_a")
    side_b = decomposition.segment("side_b")

    assert decomposition.landmark_method == "streamwise_extrema_tangent_continuity"
    assert side_a.points_sq_mm[0][0] < side_a.points_sq_mm[-1][0]
    assert side_b.points_sq_mm[0][0] < side_b.points_sq_mm[-1][0]
    assert np.mean(np.asarray(side_a.points_sq_mm)[:, 1]) > np.mean(
        np.asarray(side_b.points_sq_mm)[:, 1]
    )


def test_sparse_source_curve_fit_reports_bidirectional_sq_and_xyz_residuals_and_sag():
    sq = np.asarray([(0.0, 0.0), (1.0, 1.2), (2.0, -1.0), (3.0, 0.0)])
    xyz = np.column_stack([sq, np.asarray([0.0, 0.8, -0.6, 0.0])])
    fit = fit_nurbs_measurement_curve(
        xyz,
        sq,
        segment_name="sparse_edge",
        source_edge_ids=("edge_sparse",),
        maximum_control_count=4,
    )

    assert fit.residual_fit_to_source_max_sq_mm > 0.1
    assert fit.residual_fit_to_source_max_xyz_mm > 0.1
    assert fit.residual_max_mm == max(
        fit.residual_source_to_fit_max_sq_mm,
        fit.residual_fit_to_source_max_sq_mm,
        fit.residual_source_to_fit_max_xyz_mm,
        fit.residual_fit_to_source_max_xyz_mm,
    )
    assert fit.edge_sag_sq_mm > 1.0
    assert fit.edge_sag_xyz_mm > fit.edge_sag_sq_mm
    assert fit.fit_sample_count == 257


def test_high_resolution_fit_has_a_bounded_display_sample_budget():
    parameter = np.linspace(0.0, 1.0, 4001)
    sq = np.column_stack([20.0 * parameter, np.sin(4.0 * np.pi * parameter)])
    xyz = np.column_stack([sq, 0.2 * np.sin(2.0 * np.pi * parameter)])
    fit = fit_nurbs_measurement_curve(
        xyz,
        sq,
        segment_name="dense_side",
        maximum_control_count=8,
    )
    assert fit.source_sample_count == 4001
    assert fit.fit_sample_count == 1025
