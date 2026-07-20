from types import SimpleNamespace

import numpy as np
import pytest

from part_rule_synthesis.impeller_v11_6_section_curve_authority import (
    CANONICAL_FRAME,
    SectionCurveAuthorityError,
    _attachment_boundary_h_envelope,
    build_active_span_field,
    build_derived_field_evidence,
    build_station_curve_authority,
    solve_boundary_guided_meridional_correspondence,
)


def test_station_authority_preserves_physical_s_and_independent_side_endpoints():
    station = build_station_curve_authority(
        population="main",
        active_h=0.0,
        support_span_h=0.31,
        support_profile_rz_mm=((10.0, 0.0), (20.0, 3.0), (30.0, 8.0)),
        loop=_loop(),
        decomposition=_decomposition(),
        frame=_frame(),
    )

    side_a = station["curves"]["side_a"]
    side_b = station["curves"]["side_b"]
    assert side_a["coordinate_frame"] == CANONICAL_FRAME
    assert side_a["s_physical_mm"] == pytest.approx([10.0, 15.0, 20.0])
    assert side_b["s_physical_mm"] == pytest.approx([12.55, 16.0, 20.2])
    assert station["endpoint_stagger"]["side_b_minus_side_a_leading_s_mm"] == pytest.approx(2.55)
    assert station["endpoint_stagger"]["side_b_minus_side_a_trailing_s_mm"] == pytest.approx(0.2)
    assert side_a["start_witness"]["s_physical_mm"] != side_b["start_witness"]["s_physical_mm"]
    assert station["aerodynamic_role_status"] == "UNRESOLVED_SIDE_A_SIDE_B_ONLY"


def test_station_authority_applies_source_to_canonical_transform_exactly_once():
    station = build_station_curve_authority(
        population="main",
        active_h=0.5,
        support_span_h=0.6,
        support_profile_rz_mm=((10.0, 0.0), (20.0, 3.0), (30.0, 8.0)),
        loop=_loop(),
        decomposition=_decomposition(),
        frame=_frame(),
    )

    side_a = station["curves"]["side_a"]
    assert np.asarray(side_a["source_points_xyz_mm"])[:, 2] == pytest.approx([0.0, 1.0, 2.0])
    assert np.asarray(side_a["canonical_points_xyz_mm"])[:, 2] == pytest.approx(
        [6.550302, 7.550302, 8.550302]
    )
    assert np.asarray(station["canonical_loop_points_xyz_mm"])[:, 2] == pytest.approx(
        np.asarray(station["source_loop_points_xyz_mm"])[:, 2] + 6.550302
    )


def test_station_authority_publishes_authenticated_source_face_uv_witnesses():
    decomposition = _decomposition()
    for segment in decomposition.segments:
        if segment.name not in {"side_a", "side_b"}:
            continue
        segment.source_parameter_face_id = f"{segment.name}-face"
        segment.source_face_parameter_uv = (
            (0.0, 0.25),
            (0.4, 0.25),
            (1.0, 0.25),
        )
        segment.source_face_parameter_residual_max_mm = 2.0e-8

    station = build_station_curve_authority(
        population="main",
        active_h=0.5,
        support_span_h=0.6,
        support_profile_rz_mm=((10.0, 0.0), (20.0, 3.0), (30.0, 8.0)),
        loop=_loop(),
        decomposition=decomposition,
        frame=_frame(),
    )

    source_parameter = station["curves"]["side_a"]["source_face_parameter"]
    assert source_parameter["face_id"] == "side_a-face"
    assert np.allclose(
        np.asarray(source_parameter["uv"]),
        [[0.0, 0.25], [0.4, 0.25], [1.0, 0.25]],
    )
    assert source_parameter["projection_residual_max_mm"] == pytest.approx(2.0e-8)


def test_open_side_pair_with_tolerance_closed_endpoints_is_a_sharp_shared_seam():
    loop = _loop()
    loop.source_kind = "occt_exact_authenticated_open_side_pair"
    loop.orientation_evidence = {
        "leading_endpoint_gap_mm": 0.01,
        "trailing_endpoint_gap_mm": 0.015,
    }

    station = build_station_curve_authority(
        population="main",
        active_h=0.5,
        support_span_h=0.5,
        support_profile_rz_mm=((10.0, 0.0), (20.0, 3.0), (30.0, 8.0)),
        loop=loop,
        decomposition=_decomposition(),
        frame=_frame(),
    )

    assert station["closure_classification"] == "sharp_shared_seam"


def test_boundary_guided_correspondence_uses_source_side_anchors_not_nearest_points():
    hub = np.column_stack([np.linspace(10.0, 20.0, 33), np.zeros(33)])
    tip = np.column_stack(
        [np.linspace(11.0, 21.0, 33), np.linspace(8.0, 0.0, 33)]
    )

    correspondence = solve_boundary_guided_meridional_correspondence(
        hub,
        tip,
        streamwise_anchors=((0.0, 0.0), (0.5, 0.25), (1.0, 1.0)),
        sample_count=65,
    )

    assert correspondence.method == "source_side_boundary_guided_monotone_pchip"
    assert correspondence.hub_parameters[32] == pytest.approx(0.5)
    assert correspondence.tip_parameters[32] == pytest.approx(0.25, abs=1.0e-8)
    assert correspondence.minimum_parameter_step > 0.0
    assert np.asarray(correspondence.tip_points_rz_mm)[32] == pytest.approx(
        [13.5, 6.0], abs=1.0e-8
    )
    field = build_active_span_field(
        hub,
        tip,
        root_attachment=None,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        support_correspondence=correspondence,
    )
    assert field.support_correspondence_method == correspondence.method


def test_local_active_span_field_varies_with_streamwise_support_separation():
    root = SimpleNamespace(
        lift_samples_mm=(2.0, 2.0, 2.0),
        width_samples_mm=(2.0, 2.0, 2.0),
        streamwise_samples_s=(0.0, 0.5, 1.0),
    )
    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 20.0), (30.0, 30.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        sample_count=33,
    )

    assert field.root_h[0] > field.root_h[-1]
    assert all(root_h < tip_h for root_h, tip_h in zip(field.root_h, field.tip_h, strict=True))
    mid_profile = np.asarray(field.profile_rz_mm(0.5))
    hub = np.asarray(field.hub_points_rz_mm)
    tip = np.asarray(field.tip_points_rz_mm)
    expected_beta = np.asarray(
        [root_h + 0.5 * (tip_h - root_h) for root_h, tip_h in zip(field.root_h, field.tip_h, strict=True)]
    )
    assert mid_profile == pytest.approx(hub + expected_beta[:, None] * (tip - hub))
    assert field.as_dict()["measurement_authority"] == (
        "retained_boundary_on_authenticated_support_correspondence"
    )


def test_retained_root_boundary_is_authoritative_over_scalar_lift():
    root = SimpleNamespace(
        lift_samples_mm=(5.0, 5.0, 5.0),
        width_samples_mm=(3.0, 3.0, 3.0),
        streamwise_samples_s=(0.0, 0.5, 1.0),
        retained_points_canonical_rz_mm=(
            (10.0, 1.0),
            (20.0, 1.0),
            (30.0, 1.0),
        ),
        retained_point_source_edge_ids=("root-side-a",) * 3,
    )
    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        sample_count=33,
    )

    retained_root = np.asarray(field.retained_root_boundary_points_rz_mm)
    active_root = np.asarray(field.active_root_points_rz_mm)
    assert retained_root[:, 1] == pytest.approx(1.0)
    assert active_root[:, 1] == pytest.approx(1.75)
    assert np.asarray(field.root_carrier_clearance_mm) == pytest.approx(0.75)
    assert field.root_carrier_clearance_authority == (
        "max_four_source_tolerances_or_quarter_local_attachment_width_capped_by_active_span"
    )
    assert field.root_boundary_authority == (
        "source_retained_blade_boundary_support_envelope"
    )
    assert field.projection_residual_gate_mm == pytest.approx(3.04)
    assert max(field.root_h) < 0.2


def test_root_boundary_uses_material_side_envelope_across_source_edge_chains():
    root = SimpleNamespace(
        lift_samples_mm=(5.0,) * 6,
        width_samples_mm=(3.0,) * 6,
        streamwise_samples_s=(0.0, 0.5, 1.0, 0.0, 0.5, 1.0),
        retained_points_canonical_rz_mm=(
            (10.0, 1.0),
            (20.0, 1.0),
            (30.0, 1.0),
            (10.0, 2.5),
            (20.0, 2.5),
            (30.0, 2.5),
        ),
        retained_point_source_edge_ids=("root-side-a",) * 3
        + ("root-side-b",) * 3,
    )
    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        sample_count=33,
    )

    assert np.asarray(field.retained_root_boundary_points_rz_mm)[:, 1] == pytest.approx(2.5)
    assert np.asarray(field.active_root_points_rz_mm)[:, 1] == pytest.approx(3.25)
    assert max(field.root_h) < 0.4


def test_measurement_carrier_clearance_does_not_mutate_retained_boundary():
    root = SimpleNamespace(
        lift_samples_mm=(4.0, 4.0, 4.0),
        width_samples_mm=(20.0, 20.0, 20.0),
        streamwise_samples_s=(0.0, 0.5, 1.0),
        retained_points_canonical_rz_mm=(
            (10.0, 1.0),
            (20.0, 1.0),
            (30.0, 1.0),
        ),
        retained_point_source_edge_ids=("root-side-a",) * 3,
    )
    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        sample_count=33,
    )

    assert np.asarray(field.retained_root_boundary_points_rz_mm)[:, 1] == pytest.approx(1.0)
    assert np.asarray(field.active_root_points_rz_mm)[:, 1] == pytest.approx(1.9)
    assert np.asarray(field.root_carrier_clearance_mm) == pytest.approx(0.9)
    assert np.asarray(field.root_carrier_clearance_cap_mm) == pytest.approx(0.9)


def test_open_tip_boundary_preserves_bounded_physical_offset_from_reference_surface():
    def tip_attachment(z_mm):
        return SimpleNamespace(
            lift_samples_mm=(0.0, 0.0, 0.0),
            width_samples_mm=(0.0, 0.0, 0.0),
            streamwise_samples_s=(0.0, 0.5, 1.0),
            retained_points_canonical_rz_mm=(
                (10.0, z_mm),
                (20.0, z_mm),
                (30.0, z_mm),
            ),
            retained_point_source_edge_ids=("tip-side-a",) * 3,
        )

    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=None,
        tip_attachment=tip_attachment(10.05),
        source_tolerance_mm=0.02,
        sample_count=33,
    )

    assert np.asarray(field.retained_tip_boundary_points_rz_mm)[:, 1] == pytest.approx(
        10.05
    )
    assert np.asarray(field.active_tip_points_rz_mm)[:, 1] == pytest.approx(9.97)

    with pytest.raises(SectionCurveAuthorityError) as caught:
        build_active_span_field(
            ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
            ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
            root_attachment=None,
            tip_attachment=tip_attachment(10.30),
            source_tolerance_mm=0.02,
            sample_count=33,
        )
    assert caught.value.reason == "v116_active_span_carrier_invalid"


def test_retained_boundary_coverage_failure_reports_source_edge_and_metric_gaps():
    root = SimpleNamespace(
        lift_samples_mm=(1.0, 1.0, 1.0),
        width_samples_mm=(2.0, 2.0, 2.0),
        streamwise_samples_s=(0.2, 0.5, 0.8),
        termination_streamwise_samples_s=(0.0, 1.0),
        retained_points_canonical_rz_mm=(
            (12.0, 1.0),
            (20.0, 1.0),
            (28.0, 1.0),
        ),
        retained_point_source_edge_ids=("root-side-a",) * 3,
    )

    support_u = np.linspace(0.0, 1.0, 33)
    hub = np.column_stack((10.0 + 20.0 * support_u, np.zeros(33)))
    tip = hub + np.asarray([0.0, 10.0])
    with pytest.raises(SectionCurveAuthorityError) as caught:
        _attachment_boundary_h_envelope(
            root,
            support_u,
            support_u,
            hub,
            tip,
            boundary="root",
        )

    assert caught.value.reason == "v116_active_span_carrier_invalid"
    details = caught.value.details
    assert details["boundary_role"] == "root"
    assert details["requested_streamwise_interval_s"] == pytest.approx([0.0, 1.0])
    assert details["retained_global_streamwise_range_s"] == pytest.approx([0.2, 0.8])
    assert details["topology_gap_s"] == pytest.approx(
        {"leading": 0.2, "trailing": 0.2}
    )
    assert details["topology_gap_mm"] == pytest.approx(
        {"leading": 4.0, "trailing": 4.0}
    )
    assert details["source_edge_ranges"] == [
        {
            "source_edge_id": "root-side-a",
            "point_count": 3,
            "streamwise_range_s": pytest.approx([0.2, 0.8]),
        }
    ]


def test_active_span_intersects_termination_and_retained_material_ranges():
    root = SimpleNamespace(
        lift_samples_mm=(1.0, 1.0, 1.0),
        width_samples_mm=(2.0, 2.0, 2.0),
        streamwise_samples_s=(0.2, 0.5, 0.8),
        termination_streamwise_samples_s=(0.0, 1.0),
        retained_points_canonical_rz_mm=(
            (12.0, 1.0),
            (20.0, 1.0),
            (28.0, 1.0),
        ),
        retained_point_source_edge_ids=("root-side-a",) * 3,
    )

    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.01,
        sample_count=33,
        streamwise_interval_s=(0.0, 1.0),
    )

    assert field.requested_streamwise_interval_s == pytest.approx((0.0, 1.0))
    assert field.boundary_constrained_streamwise_interval_s == pytest.approx(
        (0.2, 0.8)
    )
    assert field.resolved_streamwise_interval_s == pytest.approx((0.202, 0.798))


def test_termination_boundary_receives_evidence_scaled_streamwise_clearance():
    root = SimpleNamespace(
        lift_samples_mm=(1.0, 1.0, 1.0),
        width_samples_mm=(2.0, 2.0, 2.0),
        streamwise_samples_s=(0.0, 0.5, 1.0),
        termination_streamwise_samples_s=(0.1, 0.9),
    )
    field = build_active_span_field(
        ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        ((10.0, 10.0), (20.0, 10.0), (30.0, 10.0)),
        root_attachment=root,
        tip_attachment=None,
        source_tolerance_mm=0.02,
        sample_count=33,
    )

    assert field.boundary_constrained_streamwise_interval_s == pytest.approx(
        (0.1, 0.9)
    )
    assert field.streamwise_boundary_clearance_mm == pytest.approx(0.08)
    assert field.streamwise_boundary_clearance_s == pytest.approx(0.004)
    assert field.resolved_streamwise_interval_s == pytest.approx((0.104, 0.896))
    assert field.as_dict()["streamwise_boundary_clearance_authority"] == (
        "four_source_tolerances_inside_termination_boundary"
    )


def test_direct_curve_derived_fields_retain_both_normal_components_without_authority():
    samples = tuple(
        SimpleNamespace(
            s=value,
            camber_sq_mm=(10.0 * value, value**2),
            normal_sq=(-0.2, 0.98),
            thickness_mm=2.0 + value,
            side_a_parameter=value,
            side_b_parameter=value,
        )
        for value in (0.1, 0.5, 0.9)
    )
    evidence = build_derived_field_evidence(SimpleNamespace(samples=samples))

    assert evidence["authority"] == "derived_from_direct_section_curve_network"
    assert evidence["geometry_authority"] is False
    assert evidence["q_only_offset_forbidden"] is True
    assert evidence["samples"][1]["normal_sq"] == pytest.approx([-0.2, 0.98])
    assert evidence["samples"][1]["pose_tangent_sq"][0] > 0.0


def _frame():
    return {
        "source_to_canonical_matrix": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 6.550302],
            [0.0, 0.0, 0.0, 1.0],
        ]
    }


def _fit(name, points):
    return SimpleNamespace(
        degree=2,
        knots=(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        control_points_xyz_mm=tuple(points),
        residual_max_mm=0.01,
        knot_strategy="fixture",
    )


def _segment(name, xyz, sq):
    return SimpleNamespace(
        name=name,
        points_xyz_mm=tuple(xyz),
        points_sq_mm=tuple(sq),
        source_face_ids=(f"{name}-face",),
        source_edge_ids=(f"{name}-edge",),
        fit=_fit(name, xyz),
    )


def _decomposition():
    return SimpleNamespace(
        segments=(
            _segment(
                "side_a",
                ((10.0, -1.0, 0.0), (15.0, -1.2, 1.0), (20.0, -0.8, 2.0)),
                ((10.0, -1.0), (15.0, -1.2), (20.0, -0.8)),
            ),
            _segment(
                "side_b",
                ((12.55, 1.0, 0.0), (16.0, 1.3, 1.0), (20.2, 0.9, 2.0)),
                ((12.55, 1.0), (16.0, 1.3), (20.2, 0.9)),
            ),
            _segment(
                "leading_edge",
                ((10.0, -1.0, 0.0), (11.1, 0.0, 0.0), (12.55, 1.0, 0.0)),
                ((10.0, -1.0), (11.1, 0.0), (12.55, 1.0)),
            ),
            _segment(
                "trailing_edge",
                ((20.2, 0.9, 2.0), (20.3, 0.0, 2.0), (20.0, -0.8, 2.0)),
                ((20.2, 0.9), (20.3, 0.0), (20.0, -0.8)),
            ),
        )
    )


def _loop():
    return SimpleNamespace(
        points_xyz_mm=(
            (10.0, -1.0, 0.0),
            (20.0, -0.8, 2.0),
            (20.2, 0.9, 2.0),
            (12.55, 1.0, 0.0),
            (10.0, -1.0, 0.0),
        ),
        edges=(SimpleNamespace(source_roles=("side_a",)), SimpleNamespace(source_roles=("side_b",))),
        material_side=1,
        source_tolerance_mm=0.02,
    )
