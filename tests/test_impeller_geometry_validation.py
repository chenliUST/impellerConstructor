from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_geometry_validation import (
    build_geometry_validation_report,
    geometry_validation_blocks_export,
)


def _minimal_validated_graph(*surfaces: dict) -> dict:
    return {
        "transition_geometry_status": "validated_transition_surface_graph",
        "surfaces": [
            {
                "id": "blade_0_pressure_surface",
                "role": "blade_pressure",
                "trimmed_boundaries": {
                    "hub_root_pressure": {"edge_treatment_site_id": "blade_0.pressure_root_to_hub"}
                },
            },
            {
                "id": "blade_0_suction_surface",
                "role": "blade_suction",
                "trimmed_boundaries": {
                    "hub_root_suction": {"edge_treatment_site_id": "blade_0.suction_root_to_hub"}
                },
            },
            {
                "id": "hub_revolve_surface",
                "role": "hub",
                "trim_exclusion_regions": [
                    {"edge_treatment_site_id": "blade_0.pressure_root_to_hub"},
                    {"edge_treatment_site_id": "blade_0.suction_root_to_hub"},
                ],
            },
            *surfaces,
        ],
        "edge_treatment_sites": [
            {
                "edge_treatment_site_id": "blade_0.pressure_root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "transition_surface_ids": ["blade_0_pressure_root_transition_surface"],
                "adjacent_surface_ids": ["blade_0_pressure_surface", "hub_revolve_surface"],
            },
            {
                "edge_treatment_site_id": "blade_0.suction_root_to_hub",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "treatment": "fillet",
                "transition_surface_ids": ["blade_0_suction_root_transition_surface"],
                "adjacent_surface_ids": ["blade_0_suction_surface", "hub_revolve_surface"],
            },
        ],
    }


def _valid_root_transition(surface_id: str, site_id: str) -> dict:
    return {
        "id": surface_id,
        "role": "blade_pressure_root_fillet" if "pressure" in surface_id else "blade_suction_root_fillet",
        "edge_family": "blade_root_to_hub",
        "edge_treatment_site_id": site_id,
        "transition_policy_id": "blade_root_to_hub.default",
        "treatment": "fillet",
        "radius_mm": 8.0,
        "transition_geometry": "validated_fillet_patch",
        "transition_quality": {
            "convexity_status": "PASS",
            "fillet_convex_signed_bulge_mm": 0.6,
            "radius_max_error_mm": 0.05,
            "g0_boundary_max_error_mm": 0.0,
            "g1_tangent_max_error_deg": 12.0,
        },
    }


def _default_policies(enabled: bool = True, treatment: str = "fillet", radius_mm: float = 8.0) -> dict:
    return {
        "blade_root_to_hub.default": {
            "enabled": enabled,
            "treatment": treatment,
            "radius_mm": radius_mm,
        }
    }


def test_v09_validation_passes_double_sided_root_transition_graph():
    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={"shroud_topology": "open"},
        transition_policies=_default_policies(),
        surface_graph=_minimal_validated_graph(
            _valid_root_transition(
                "blade_0_pressure_root_transition_surface",
                "blade_0.pressure_root_to_hub",
            ),
            _valid_root_transition(
                "blade_0_suction_root_transition_surface",
                "blade_0.suction_root_to_hub",
            ),
        ),
        capability_matrix_id="impeller_v0_9_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "PASS"
    assert geometry_validation_blocks_export(report) is False
    assert report["kernel_capability_matrix_id"] == "impeller_v0_9_kernel_capabilities"
    assert report["capability_claim_level"] == "review_grade_validated"
    assert report["transition_validation_summary"]["transition_surface_count"] == 2


def test_v09_validation_fails_inverted_concave_fillet():
    inverted = _valid_root_transition(
        "blade_0_pressure_root_transition_surface",
        "blade_0.pressure_root_to_hub",
    )
    inverted["transition_quality"] = {
        **inverted["transition_quality"],
        "convexity_status": "FAIL",
        "fillet_convex_signed_bulge_mm": -0.2,
    }
    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_default_policies(),
        surface_graph=_minimal_validated_graph(
            inverted,
            _valid_root_transition(
                "blade_0_suction_root_transition_surface",
                "blade_0.suction_root_to_hub",
            ),
        ),
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert geometry_validation_blocks_export(report) is True
    assert any(failure["reason"] == "fillet_convexity_failed" for failure in report["blocking_failures"])


def test_v09_validation_fails_transition_surface_without_adjacent_trim():
    graph = _minimal_validated_graph(
        _valid_root_transition(
            "blade_0_pressure_root_transition_surface",
            "blade_0.pressure_root_to_hub",
        ),
        _valid_root_transition(
            "blade_0_suction_root_transition_surface",
            "blade_0.suction_root_to_hub",
        ),
    )
    graph["surfaces"][0].pop("trimmed_boundaries")

    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_default_policies(),
        surface_graph=graph,
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "adjacent_surface_not_trimmed" for failure in report["blocking_failures"])


def test_v09_validation_fails_when_policy_radius_and_surface_radius_diverge():
    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_default_policies(radius_mm=20.0),
        surface_graph=_minimal_validated_graph(
            _valid_root_transition(
                "blade_0_pressure_root_transition_surface",
                "blade_0.pressure_root_to_hub",
            ),
            _valid_root_transition(
                "blade_0_suction_root_transition_surface",
                "blade_0.suction_root_to_hub",
            ),
        ),
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "transition_radius_not_synchronized" for failure in report["blocking_failures"])


def test_v09_validation_fails_disabled_policy_with_phantom_transition_surface():
    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 0.0},
        facets={},
        transition_policies=_default_policies(enabled=False, treatment="none", radius_mm=0.0),
        surface_graph=_minimal_validated_graph(
            _valid_root_transition(
                "blade_0_pressure_root_transition_surface",
                "blade_0.pressure_root_to_hub",
            ),
            _valid_root_transition(
                "blade_0_suction_root_transition_surface",
                "blade_0.suction_root_to_hub",
            ),
        ),
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "disabled_policy_has_transition_surface" for failure in report["blocking_failures"])


@pytest.mark.parametrize("legacy_surface_id", ["blade_0_root_transition_surface"])
def test_v09_validation_rejects_legacy_single_root_success_surface(legacy_surface_id: str):
    legacy_surface = _valid_root_transition(legacy_surface_id, "blade_0.root_to_hub")
    legacy_surface["role"] = "blade_root_fillet"
    report = build_geometry_validation_report(
        parameters={"root_fillet_radius_mm": 8.0},
        facets={},
        transition_policies=_default_policies(),
        surface_graph={
            "transition_geometry_status": "validated_transition_surface_graph",
            "surfaces": [legacy_surface],
            "edge_treatment_sites": [
                {
                    "edge_treatment_site_id": "blade_0.root_to_hub",
                    "edge_family": "blade_root_to_hub",
                    "transition_policy_id": "blade_root_to_hub.default",
                    "transition_surface_ids": [legacy_surface_id],
                    "adjacent_surface_ids": ["blade_0_pressure_surface", "blade_0_suction_surface", "hub_revolve_surface"],
                }
            ],
        },
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "legacy_single_root_transition_surface" for failure in report["blocking_failures"])
