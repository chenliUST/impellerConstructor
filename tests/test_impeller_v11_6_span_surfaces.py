from __future__ import annotations

import numpy as np
import pytest

from part_rule_synthesis.impeller_v11_6_section_recovery import (
    SectionRecoveryError,
    build_adaptive_span_profiles,
    build_ordered_span_profiles,
    solve_meridional_correspondence,
)


def _support_profiles() -> tuple[list[list[float]], list[list[float]]]:
    parameter = np.linspace(0.0, 1.0, 33)
    hub = np.column_stack([10.0 + 8.0 * parameter, 24.0 * (1.0 - parameter)])
    tip = np.column_stack([13.0 + 10.0 * parameter, 24.0 * (1.0 - parameter) + 0.5 * parameter])
    return hub.tolist(), tip.tolist()


def _active_evidence(h: float, boundary: str) -> dict[str, object]:
    return {
        "h": h,
        "method": f"occt_retained_{boundary}_boundary_projection",
        "source_face_ids": [f"blade_{boundary}_face", f"{boundary}_blend_face"],
        "source_edge_ids": [f"{boundary}_retained_edge"],
        "tolerance_mm": 0.02,
        "residual_mm": 0.004,
    }


def _active_kwargs() -> dict[str, object]:
    return {
        "active_root_evidence": _active_evidence(0.08, "root"),
        "active_tip_evidence": _active_evidence(0.92, "tip"),
        "known_source_face_ids": {
            "blade_root_face",
            "root_blend_face",
            "blade_tip_face",
            "tip_blend_face",
        },
        "known_source_edge_ids": {"root_retained_edge", "tip_retained_edge"},
    }


def test_meridional_correspondence_is_strictly_monotone_and_resolves_tip_direction():
    hub, tip = _support_profiles()
    result = solve_meridional_correspondence(hub, list(reversed(tip)), sample_count=65)

    assert result.tip_reversed is True
    assert np.all(np.diff(result.tip_parameters) > 0.0)
    assert result.minimum_parameter_step > 0.0
    assert result.as_dict()["flowwise_order_preserved"] is True


def test_adaptive_profiles_remain_ordered_and_simple_evidence_keeps_five_stations():
    hub, tip = _support_profiles()
    result = build_adaptive_span_profiles(
        hub,
        tip,
        lambda _h: {
            "camber_residual_mm": 0.01,
            "thickness_residual_mm": 0.01,
            "twist_residual_deg": 0.1,
            "edge_curvature_residual_per_mm": 0.01,
        },
        thresholds={
            "camber_residual_mm": 0.2,
            "thickness_residual_mm": 0.2,
            "twist_residual_deg": 1.0,
            "edge_curvature_residual_per_mm": 0.1,
        },
        **_active_kwargs(),
    )

    assert len(result.stations) == 5
    span_vectors = np.asarray(result.correspondence.tip_points_rz_mm) - np.asarray(
        result.correspondence.hub_points_rz_mm
    )
    for lower, upper in zip(result.profiles[:-1], result.profiles[1:]):
        delta = np.asarray(upper.points_rz_mm) - np.asarray(lower.points_rz_mm)
        assert np.all(np.sum(delta * span_vectors, axis=1) > 0.0)


def test_high_twist_and_thickness_gradient_refine_deterministically_within_nine_stations():
    hub, tip = _support_profiles()

    def metrics(h: float) -> dict[str, float]:
        return {
            "twist_deg": 28.0 * h * h,
            "thickness_mm": 0.45 + 0.7 * h**3,
            "correspondence_mm": 0.01,
        }

    first = build_adaptive_span_profiles(
        hub,
        tip,
        metrics,
        thresholds={"twist_deg": 2.0, "thickness_mm": 0.15, "correspondence_mm": 0.05},
        **_active_kwargs(),
    )
    second = build_adaptive_span_profiles(
        hub,
        tip,
        metrics,
        thresholds={"twist_deg": 2.0, "thickness_mm": 0.15, "correspondence_mm": 0.05},
        **_active_kwargs(),
    )

    assert 5 < len(first.stations) <= 9
    assert [station.h for station in first.stations] == [station.h for station in second.stations]
    assert any(not station.initial for station in first.stations)
    assert any("twist_deg" in station.refinement_reasons for station in first.stations)


def test_constant_absolute_residuals_refine_and_lattice_persists_profiles_and_boundaries():
    hub, tip = _support_profiles()
    result = build_adaptive_span_profiles(
        hub,
        tip,
        lambda _h: {
            "correspondence_residual_mm": 10.0,
            "camber_residual_mm": 5.0,
            "thickness_residual_mm": 2.0,
            "twist_residual_deg": 3.0,
            "curvature_residual_per_mm": 0.5,
        },
        thresholds={
            "correspondence_residual_mm": 0.05,
            "camber_residual_mm": 0.1,
            "thickness_residual_mm": 0.1,
            "twist_residual_deg": 0.5,
            "curvature_residual_per_mm": 0.05,
        },
        **_active_kwargs(),
    )

    assert len(result.stations) == 9
    payload = result.as_dict()
    assert len(payload["profiles"]) == 9
    assert payload["active_span"]["root"]["source_ids"]
    assert payload["active_span"]["tip"]["h"] == pytest.approx(0.92)


def test_active_span_defaults_cannot_impersonate_measured_boundaries():
    hub, tip = _support_profiles()
    with pytest.raises(SectionRecoveryError) as caught:
        build_adaptive_span_profiles(hub, tip)
    assert caught.value.reason == "v116_section_loop_correspondence_failed"


def test_coincident_hub_and_tip_supports_are_rejected():
    hub, _tip = _support_profiles()
    with pytest.raises(SectionRecoveryError) as caught:
        solve_meridional_correspondence(hub, hub, sample_count=33)
    assert caught.value.reason == "v116_span_surface_ordering_failed"


def test_crossing_hub_and_tip_supports_are_rejected_before_correspondence():
    hub = [[10.0, 0.0], [12.0, 2.0]]
    tip = [[10.0, 2.0], [12.0, 0.0]]

    with pytest.raises(SectionRecoveryError) as caught:
        solve_meridional_correspondence(hub, tip, sample_count=10)

    assert caught.value.reason == "v116_span_surface_ordering_failed"
    assert caught.value.details["support_intersection"] is True


def test_active_span_ids_must_belong_to_authenticated_source_inventory():
    hub, tip = _support_profiles()
    evidence = _active_kwargs()
    evidence["active_root_evidence"] = {
        **_active_evidence(0.08, "root"),
        "source_face_ids": ["does_not_exist"],
    }

    with pytest.raises(SectionRecoveryError) as caught:
        build_adaptive_span_profiles(hub, tip, **evidence)

    assert caught.value.reason == "v116_section_loop_correspondence_failed"
    assert caught.value.details["unknown_source_face_ids"] == ["does_not_exist"]


def test_nonmonotone_span_interpolation_is_a_stable_failure():
    hub, tip = _support_profiles()
    correspondence = solve_meridional_correspondence(hub, tip, sample_count=33)

    with pytest.raises(SectionRecoveryError) as caught:
        build_ordered_span_profiles(
            correspondence,
            [0.2, 0.4],
            beta=lambda h, _u: 0.8 - h,
        )

    assert caught.value.reason == "v116_span_surface_ordering_failed"
