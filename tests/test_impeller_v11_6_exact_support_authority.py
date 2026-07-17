from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (  # noqa: E402
    _profile_sample,
    _resolved_support_profile,
)
from part_rule_synthesis.impeller_v11_surface_family import (  # noqa: E402
    _hub_solid_faces,
    _merge_v11_profile_overrides,
    _root_streamwise_metric_scale,
    _sample_profile_rz,
)


def _quadratic_profile():
    return {
        "kind": "nurbs_curve",
        "degree": 2,
        "control_points": [[0.0, 0.0], [1.0, 4.0], [2.0, 0.0]],
        "weights": [1.0, 1.0, 1.0],
        "knots": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
    }


def _adaptive_values():
    curve = _quadratic_profile()
    return {
        "hub_profile_rz_mm": curve["control_points"],
        "canonical_nurbs_parameterization": {
            "canonical_input_source": "v116_adaptive_step_reconstruction_extension",
            "adaptive_reconstruction_extension": {"status": "PASS"},
            "support_profiles": {"hub_profile": curve},
        },
    }


def test_adaptive_domain_mapping_uses_exact_support_nurbs_not_control_polygon():
    values = _adaptive_values()
    authority = _resolved_support_profile(
        values,
        canonical_name="hub_profile",
        legacy_name="hub_profile_rz_mm",
    )

    assert _profile_sample(authority, 0.5) == pytest.approx([1.0, 2.0])
    assert _profile_sample(values["hub_profile_rz_mm"], 0.5) == pytest.approx(
        [1.0, 4.0]
    )


def test_adaptive_revolve_sampling_uses_the_same_exact_nurbs_authority():
    samples = _sample_profile_rz(_quadratic_profile(), sample_count=3)

    assert samples[0] == pytest.approx([0.0, 0.0])
    assert samples[1] == pytest.approx([1.0, 2.0])
    assert samples[2] == pytest.approx([2.0, 0.0])


def test_legacy_v112_support_profile_does_not_silently_switch_authority():
    values = _adaptive_values()
    values["canonical_nurbs_parameterization"]["canonical_input_source"] = (
        "translated_from_legacy_v1_1"
    )

    authority = _resolved_support_profile(
        values,
        canonical_name="hub_profile",
        legacy_name="hub_profile_rz_mm",
    )

    assert authority is values["hub_profile_rz_mm"]


def test_legacy_root_metric_keeps_direct_control_polygon_length():
    values = _adaptive_values()
    values["canonical_nurbs_parameterization"]["canonical_input_source"] = (
        "translated_from_legacy_v1_1"
    )
    expected = sum(
        ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
        for left, right in zip(
            values["hub_profile_rz_mm"],
            values["hub_profile_rz_mm"][1:],
        )
    )

    assert _root_streamwise_metric_scale(values) == pytest.approx(expected)


def test_adaptive_exact_support_rejects_legacy_profile_override_payload():
    values = _adaptive_values()

    with pytest.raises(ValueError, match="adaptive support profiles are authoritative"):
        _merge_v11_profile_overrides(
            values,
            {"hub_profile": {"control_points": [[0.0, 0.0], [3.0, 0.0]]}},
        )


def test_adaptive_hub_solid_closes_around_profile_endpoints_without_false_top_disk():
    curve = {
        "kind": "nurbs_curve",
        "degree": 2,
        "control_points": [[1.0, 0.0], [1.5, 2.0], [3.0, 4.0]],
        "weights": [1.0, 1.0, 1.0],
        "knots": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
    }
    values = _adaptive_values()
    values["hub_profile_rz_mm"] = curve["control_points"]
    values["canonical_nurbs_parameterization"]["support_profiles"][
        "hub_profile"
    ] = curve
    values.update(
        {
            "theta_sample_count": 9,
            "profile_revolve_sample_count": 9,
            "hub_solid_radial_sample_count": 5,
            "hub_solid_axial_sample_count": 5,
        }
    )

    surfaces = {
        surface["id"]: surface
        for surface in _hub_solid_faces(
            values,
            {
                "mounting_bore_radius_mm": {"default": 0.25},
                "hub_bottom_thickness_mm": {"default": 0.5},
            },
        )
    }

    top = surfaces["hub_top_annulus_surface"]
    bottom = surfaces["hub_bottom_annulus_surface"]
    outer = surfaces["hub_bottom_outer_wall_surface"]
    bore = surfaces["mounting_bore_inner_wall_surface"]

    assert top["v1_1_hub_solid_quality"]["closure_topology"] == (
        "v116_profile_endpoint_closed_hub_solid"
    )
    assert top["edge_samples"]["outer_circle"][0] == pytest.approx(
        [1.0, 0.0, 0.0]
    )
    assert bottom["edge_samples"]["outer_circle"][0] == pytest.approx(
        [3.0, 0.0, -0.5]
    )
    assert [
        (point[0] ** 2 + point[1] ** 2) ** 0.5
        for row in outer["uv_grid"]
        for point in row
    ] == pytest.approx([3.0] * 45)
    assert min(point[2] for row in bore["uv_grid"] for point in row) == pytest.approx(
        -0.5
    )
    assert max(point[2] for row in bore["uv_grid"] for point in row) == pytest.approx(
        0.0
    )
