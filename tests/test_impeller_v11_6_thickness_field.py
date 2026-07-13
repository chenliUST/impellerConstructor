from __future__ import annotations

import numpy as np

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    LocalSectionFrame,
    SectionEdge,
    decompose_section_loop,
    measure_camber_normal_thickness,
    order_section_edges,
)


def _edge(edge_id: str, role: str, points_sq: np.ndarray) -> SectionEdge:
    xyz = np.column_stack([points_sq, np.zeros(len(points_sq))])
    return SectionEdge(
        edge_id=edge_id,
        points_xyz_mm=tuple(tuple(float(value) for value in point) for point in xyz),
        source_face_ids=(f"{edge_id}_face",),
        source_roles=(role,),
    )


def _normal_offset_loop(*, curved: bool):
    parameter = np.linspace(0.0, 1.0, 101)
    streamwise = 10.0 * parameter
    if curved:
        camber_q = 0.65 * np.sin(1.4 * np.pi * parameter) + 0.15 * parameter
        derivative = (0.65 * 1.4 * np.pi * np.cos(1.4 * np.pi * parameter) + 0.15) / 10.0
        thickness = np.full_like(parameter, 0.62)
    else:
        camber_q = np.zeros_like(parameter)
        derivative = np.zeros_like(parameter)
        thickness = 0.50 + 0.30 * parameter
    normal = np.column_stack([-derivative, np.ones_like(parameter)])
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    camber = np.column_stack([streamwise, camber_q])
    side_a = camber + 0.5 * thickness[:, None] * normal
    side_b = camber - 0.5 * thickness[:, None] * normal
    leading = np.asarray([side_b[0], (-0.10, 0.0), side_a[0]])
    trailing = np.asarray(
        [side_a[-1], (10.14, float(camber_q[-1])), side_b[-1]]
    )
    edges = [
        _edge("side_a", "side_a", side_a),
        _edge("trailing", "trailing_edge", trailing),
        _edge("side_b", "side_b", side_b[::-1]),
        _edge("leading", "leading_edge", leading),
    ]
    frame = LocalSectionFrame(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    )
    return order_section_edges(
        edges, source_tolerance_mm=1.0e-8, local_frame=frame
    )[0]


def test_camber_normal_thickness_reproduces_source_values_at_three_streamwise_stations():
    loop = _normal_offset_loop(curved=False)
    decomposition = decompose_section_loop(loop)
    field = measure_camber_normal_thickness(
        loop, decomposition, sample_s=[0.1, 0.5, 0.9]
    )

    expected = [0.53, 0.65, 0.77]
    assert np.allclose([sample.thickness_mm for sample in field.samples], expected, atol=0.004)
    assert field.method == "camber_normal_line_intersections"
    assert field.index_pairing_used is False
    assert field.radial_distance_used is False


def test_thickness_samples_are_positive_inside_the_loop_with_monotone_side_correspondence():
    loop = _normal_offset_loop(curved=True)
    field = measure_camber_normal_thickness(
        loop,
        decompose_section_loop(loop),
        sample_s=np.linspace(0.08, 0.92, 13),
    )

    assert all(sample.thickness_mm > 0.0 for sample in field.samples)
    assert all(sample.inside_source_loop for sample in field.samples)
    assert np.all(np.diff([sample.side_a_parameter for sample in field.samples]) >= -1.0e-6)
    assert np.all(np.diff([sample.side_b_parameter for sample in field.samples]) >= -1.0e-6)
    assert np.allclose([sample.thickness_mm for sample in field.samples], 0.62, atol=0.025)


def test_measured_thickness_is_along_the_recorded_camber_normal_not_radially():
    loop = _normal_offset_loop(curved=True)
    field = measure_camber_normal_thickness(
        loop, decompose_section_loop(loop), sample_s=[0.2, 0.5, 0.8]
    )

    for sample in field.samples:
        side_vector = np.asarray(sample.side_a_sq_mm) - np.asarray(sample.side_b_sq_mm)
        normal = np.asarray(sample.normal_sq)
        assert np.isclose(abs(np.dot(side_vector, normal)), sample.thickness_mm, atol=1.0e-8)
        assert not np.allclose(normal, (1.0, 0.0))
