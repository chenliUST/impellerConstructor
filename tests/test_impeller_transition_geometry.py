from __future__ import annotations

import json

import pytest

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_geometry import (
    build_chamfer_section,
    build_fillet_section,
    max_distance_from_line,
    max_radius_error,
)
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.service import (
    _bind_parameters,
    _geometry_metadata,
    _normalize_transition_overrides,
)


def _geometry_for_v08(transition_overrides: dict | None = None) -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_8")
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    normalized_overrides = _normalize_transition_overrides(transition_overrides)
    transition_policies = resolve_transition_policies(
        edge_families,
        parameters,
        normalized_overrides,
    )
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )


def _surface_by_id(geometry: dict, surface_id: str) -> dict:
    return {
        surface["id"]: surface
        for surface in geometry["surface_graph"]["surfaces"]
    }[surface_id]


def _grid_digest(surface: dict) -> str:
    return json.dumps(surface["uv_grid"], sort_keys=True)


def _assert_point_close(actual, expected, tolerance=1.0e-9):
    assert len(actual) == len(expected)
    for actual_value, expected_value in zip(actual, expected):
        assert abs(actual_value - expected_value) <= tolerance


def test_v08_manifest_marks_resolver_invocation():
    geometry = _geometry_for_v08()

    assert geometry["surface_graph"]["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    check_names = {
        check["name"]
        for check in geometry["validity"]["checks"]
    }
    assert "transition_geometry_resolver_invoked" in check_names


def test_v07_manifest_does_not_claim_transition_resolved_geometry():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_7")
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    transition_policies = resolve_transition_policies(edge_families, parameters)
    geometry = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )

    assert geometry["surface_graph"].get("transition_geometry_status") != "resolved_trimmed_surface_graph"
    assert "checks" not in geometry["validity"]


def test_v08_blade_root_radius_override_changes_transition_geometry():
    baseline = _geometry_for_v08()
    enlarged = _geometry_for_v08(
        transition_overrides={
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 20.0,
            }
        },
    )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    enlarged_root = _surface_by_id(enlarged, "blade_0_root_transition_surface")

    assert baseline_root["radius_mm"] == 8.0
    assert enlarged_root["radius_mm"] == 20.0
    assert _grid_digest(enlarged_root) != _grid_digest(baseline_root)


def test_v08_blade_root_chamfer_override_changes_transition_geometry_and_role():
    baseline = _geometry_for_v08()
    chamfered = _geometry_for_v08(
        transition_overrides={
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "chamfer",
                "radius_mm": 8.0,
            }
        },
    )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    chamfered_root = _surface_by_id(chamfered, "blade_0_root_transition_surface")

    assert baseline_root["role"] == "blade_root_fillet"
    assert chamfered_root["role"] == "blade_root_chamfer"
    assert chamfered_root["treatment"] == "chamfer"
    assert _grid_digest(chamfered_root) != _grid_digest(baseline_root)


def test_build_fillet_section_samples_requested_radius_arc():
    first_trim_point = (8.0, 0.0, 0.0)
    second_trim_point = (0.0, 8.0, 0.0)
    section = build_fillet_section(
        first_trim_point=first_trim_point,
        second_trim_point=second_trim_point,
        center=(8.0, 8.0, 0.0),
        radius_mm=8.0,
        sample_count=7,
        edge_tangent=(0.0, 0.0, 1.0),
    )

    assert len(section.points) == 7
    assert section.treatment == "fillet"
    assert section.radius_mm == 8.0
    _assert_point_close(section.points[0], first_trim_point)
    _assert_point_close(section.points[-1], second_trim_point)
    assert max_radius_error(section.points, center=(8.0, 8.0, 0.0), radius_mm=8.0) <= 1.0e-6


def test_build_fillet_section_rejects_trim_points_off_requested_radius():
    with pytest.raises(ValueError, match="fillet trim points must lie on requested radius"):
        build_fillet_section(
            first_trim_point=(9.0, 0.0, 0.0),
            second_trim_point=(0.0, 8.0, 0.0),
            center=(8.0, 8.0, 0.0),
            radius_mm=8.0,
            sample_count=7,
            edge_tangent=(0.0, 0.0, 1.0),
        )


def test_build_chamfer_section_samples_straight_line():
    section = build_chamfer_section(
        first_trim_point=(8.0, 0.0, 0.0),
        second_trim_point=(0.0, 8.0, 0.0),
        sample_count=3,
    )

    assert len(section.points) == 3
    assert section.treatment == "chamfer"
    assert max_distance_from_line(
        section.points,
        first=(8.0, 0.0, 0.0),
        second=(0.0, 8.0, 0.0),
    ) <= 1.0e-6
