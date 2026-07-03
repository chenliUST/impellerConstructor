from __future__ import annotations

import json

import pytest

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_geometry import (
    build_chamfer_section,
    build_fillet_section,
    max_distance_from_line,
    max_radius_error,
    resolve_transition_geometry,
)
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.service import (
    _bind_parameters,
    _geometry_metadata,
    _normalize_transition_overrides,
)


def _geometry_for_v08(
    transition_overrides: dict | None = None,
    *,
    preset_name: str = "radial_open_reference_v0_8",
) -> dict:
    runtime = compile_impeller_runtime_preset(preset_name)
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


def _blade_surface_ids(geometry: dict, suffix: str) -> list[str]:
    return sorted(
        surface["id"]
        for surface in geometry["surface_graph"]["surfaces"]
        if surface["id"].startswith("blade_") and surface["id"].endswith(suffix)
    )


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


def test_v08_blade_root_infeasible_radius_records_transition_failure():
    geometry = _geometry_for_v08(
        transition_overrides={
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 1000.0,
            }
        },
    )

    graph = geometry["surface_graph"]
    failures = graph["transition_failures"]
    root_failure = failures[0]
    validity_checks = {
        check["name"]: check
        for check in geometry["validity"]["checks"]
    }
    root_surface = _surface_by_id(geometry, "blade_0_root_transition_surface")

    assert root_failure["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert root_failure["edge_family"] == "blade_root_to_hub"
    assert root_failure["transition_policy_id"] == "blade_root_to_hub.default"
    assert root_failure["requested_radius_mm"] == 1000.0
    assert root_failure["suggested_max_radius_mm"] == 120.0
    assert root_failure["reason"] == "radius_exceeds_local_feasible_limit"
    assert root_failure["status"] == "FAIL"
    assert not any(
        site["edge_family"] == "blade_root_to_hub"
        for site in graph["edge_treatment_sites"]
    )
    for metadata_key in [
        "radius_mm",
        "transition_geometry",
        "transition_quality",
        "transition_policy_id",
        "treatment",
        "edge_treatment_site_id",
    ]:
        assert metadata_key not in root_surface
    assert all(len(row) == 3 for row in root_surface["uv_grid"])
    assert validity_checks["required_transition_geometry_resolved"]["status"] == "FAIL"
    assert validity_checks["required_transition_geometry_resolved"]["failure_count"] > 0


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


def test_v08_blade_root_transition_records_site_and_trimmed_adjacency():
    geometry = _geometry_for_v08()

    graph = geometry["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    root = surfaces["blade_0_root_transition_surface"]
    pressure = surfaces["blade_0_pressure_surface"]
    suction = surfaces["blade_0_suction_surface"]
    hub = surfaces["hub_revolve_surface"]

    assert root["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert root["edge_family"] == "blade_root_to_hub"
    assert root["transition_policy_id"] == "blade_root_to_hub.default"
    assert root["transition_geometry"] == "resolved_fillet_patch"
    assert graph["edge_treatment_sites"][0]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert graph["edge_treatment_sites"][0]["transition_surface_ids"] == ["blade_0_root_transition_surface"]
    assert pressure["trimmed_boundaries"]["hub_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert suction["trimmed_boundaries"]["hub_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert hub["trimmed_boundaries"]["blade_0_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"


@pytest.mark.parametrize(
    ("policy_id", "surface_id", "baseline_radius", "override_radius"),
    [
        ("blade_leading_edge.default", "blade_0_leading_transition_surface", 3.0, 9.0),
        ("blade_trailing_edge.default", "blade_0_trailing_transition_surface", 2.0, 8.0),
        ("blade_tip_or_shroud.default", "blade_0_tip_transition_surface", 2.0, 7.0),
    ],
)
def test_v08_blade_edge_radius_overrides_change_transition_geometry(
    policy_id,
    surface_id,
    baseline_radius,
    override_radius,
):
    baseline = _geometry_for_v08()
    enlarged = _geometry_for_v08(
        transition_overrides={
            policy_id: {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": override_radius,
            }
        },
    )

    baseline_surface = _surface_by_id(baseline, surface_id)
    enlarged_surface = _surface_by_id(enlarged, surface_id)

    assert baseline_surface["radius_mm"] == baseline_radius
    assert enlarged_surface["radius_mm"] == override_radius
    assert _grid_digest(enlarged_surface) != _grid_digest(baseline_surface)


@pytest.mark.parametrize(
    ("policy_id", "surface_id", "expected_role", "radius"),
    [
        (
            "blade_leading_edge.default",
            "blade_0_leading_transition_surface",
            "blade_leading_edge_chamfer",
            3.0,
        ),
        (
            "blade_trailing_edge.default",
            "blade_0_trailing_transition_surface",
            "blade_trailing_edge_chamfer",
            2.0,
        ),
        (
            "blade_tip_or_shroud.default",
            "blade_0_tip_transition_surface",
            "blade_tip_edge_chamfer",
            2.0,
        ),
    ],
)
def test_v08_blade_edge_chamfer_overrides_change_geometry_and_role(
    policy_id,
    surface_id,
    expected_role,
    radius,
):
    baseline = _geometry_for_v08()
    chamfered = _geometry_for_v08(
        transition_overrides={
            policy_id: {
                "enabled": True,
                "treatment": "chamfer",
                "radius_mm": radius,
            }
        },
    )

    baseline_surface = _surface_by_id(baseline, surface_id)
    chamfered_surface = _surface_by_id(chamfered, surface_id)

    assert chamfered_surface["role"] == expected_role
    assert chamfered_surface["treatment"] == "chamfer"
    assert _grid_digest(chamfered_surface) != _grid_digest(baseline_surface)


def test_v08_blade_edge_transition_records_site_and_trimmed_adjacency():
    geometry = _geometry_for_v08()

    graph = geometry["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    leading = surfaces["blade_0_leading_transition_surface"]
    pressure = surfaces["blade_0_pressure_surface"]
    suction = surfaces["blade_0_suction_surface"]

    assert leading["edge_treatment_site_id"] == "blade_0.leading_edge"
    assert leading["edge_family"] == "blade_leading_edge"
    assert leading["transition_policy_id"] == "blade_leading_edge.default"
    assert leading["transition_geometry"] == "resolved_fillet_patch"
    assert leading["transition_quality"]["has_resolved_patch"]
    assert {
        "edge_treatment_site_id": "blade_0.leading_edge",
        "edge_family": "blade_leading_edge",
        "transition_policy_id": "blade_leading_edge.default",
        "treatment": "fillet",
        "radius_mm": 3.0,
        "adjacent_surface_ids": ["blade_0_pressure_surface", "blade_0_suction_surface"],
        "transition_surface_ids": ["blade_0_leading_transition_surface"],
        "feature_id": "blade_0_leading_transition_surface",
    } in graph["edge_treatment_sites"]
    assert pressure["trimmed_boundaries"]["leading_edge"]["edge_treatment_site_id"] == "blade_0.leading_edge"
    assert suction["trimmed_boundaries"]["leading_edge"]["edge_treatment_site_id"] == "blade_0.leading_edge"


@pytest.mark.parametrize(
    (
        "surface_id",
        "site_id",
        "edge_family",
        "transition_policy_id",
        "trimmed_boundary",
    ),
    [
        (
            "blade_0_trailing_transition_surface",
            "blade_0.trailing_edge",
            "blade_trailing_edge",
            "blade_trailing_edge.default",
            "trailing_edge",
        ),
        (
            "blade_0_tip_transition_surface",
            "blade_0.tip_or_shroud",
            "blade_tip_or_shroud",
            "blade_tip_or_shroud.default",
            "tip_or_shroud",
        ),
    ],
)
def test_v08_trailing_and_tip_transitions_serialize_sites_and_trimmed_adjacency(
    surface_id,
    site_id,
    edge_family,
    transition_policy_id,
    trimmed_boundary,
):
    geometry = _geometry_for_v08()

    graph = geometry["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    transition = surfaces[surface_id]
    pressure = surfaces["blade_0_pressure_surface"]
    suction = surfaces["blade_0_suction_surface"]

    assert transition["edge_treatment_site_id"] == site_id
    assert transition["edge_family"] == edge_family
    assert transition["transition_policy_id"] == transition_policy_id
    assert transition["transition_geometry"] == "resolved_fillet_patch"
    assert {
        "edge_treatment_site_id": site_id,
        "edge_family": edge_family,
        "transition_policy_id": transition_policy_id,
        "treatment": "fillet",
        "radius_mm": transition["radius_mm"],
        "adjacent_surface_ids": ["blade_0_pressure_surface", "blade_0_suction_surface"],
        "transition_surface_ids": [surface_id],
        "feature_id": surface_id,
    } in graph["edge_treatment_sites"]
    assert pressure["trimmed_boundaries"][trimmed_boundary]["edge_treatment_site_id"] == site_id
    assert suction["trimmed_boundaries"][trimmed_boundary]["edge_treatment_site_id"] == site_id


def test_v08_disabled_blade_edge_transitions_remove_surfaces_across_all_blades():
    geometry = _geometry_for_v08(
        transition_overrides={
            "blade_leading_edge.default": {
                "enabled": False,
                "treatment": "none",
                "radius_mm": 0.0,
            },
            "blade_trailing_edge.default": {
                "enabled": False,
                "treatment": "none",
                "radius_mm": 0.0,
            },
            "blade_tip_or_shroud.default": {
                "enabled": False,
                "treatment": "none",
                "radius_mm": 0.0,
            },
        }
    )

    assert _blade_surface_ids(geometry, "_leading_transition_surface") == []
    assert _blade_surface_ids(geometry, "_trailing_transition_surface") == []
    assert _blade_surface_ids(geometry, "_tip_transition_surface") == []


@pytest.mark.parametrize(
    (
        "policy_id",
        "surface_id",
        "edge_family",
        "baseline_radius",
        "override_treatment",
        "override_radius",
    ),
    [
        (
            "hub_top_outer.default",
            "hub_top_outer_transition_surface",
            "hub_top_outer",
            3.0,
            "fillet",
            10.0,
        ),
        (
            "hub_bottom_outer.default",
            "hub_bottom_outer_transition_surface",
            "hub_bottom_outer",
            3.0,
            "fillet",
            11.0,
        ),
        (
            "mounting_bore_top.default",
            "mounting_bore_top_transition_surface",
            "mounting_bore_top",
            3.0,
            "chamfer",
            7.0,
        ),
        (
            "mounting_bore_bottom.default",
            "mounting_bore_bottom_transition_surface",
            "mounting_bore_bottom",
            3.0,
            "chamfer",
            8.0,
        ),
    ],
)
def test_v08_axisymmetric_hub_and_bore_overrides_resolve_transition_geometry(
    policy_id,
    surface_id,
    edge_family,
    baseline_radius,
    override_treatment,
    override_radius,
):
    baseline = _geometry_for_v08()
    changed = _geometry_for_v08(
        transition_overrides={
            policy_id: {
                "enabled": True,
                "treatment": override_treatment,
                "radius_mm": override_radius,
            }
        }
    )

    graph = changed["surface_graph"]
    baseline_surface = _surface_by_id(baseline, surface_id)
    changed_surface = _surface_by_id(changed, surface_id)

    assert baseline_surface["radius_mm"] == baseline_radius
    assert changed_surface["edge_treatment_site_id"] == edge_family
    assert changed_surface["edge_family"] == edge_family
    assert changed_surface["transition_policy_id"] == policy_id
    assert changed_surface["treatment"] == override_treatment
    assert changed_surface["radius_mm"] == override_radius
    assert changed_surface["transition_geometry"] == f"resolved_{override_treatment}_patch"
    assert changed_surface["transition_quality"]["has_resolved_patch"]
    assert _grid_digest(changed_surface) != _grid_digest(baseline_surface)
    assert {
        "edge_treatment_site_id": edge_family,
        "edge_family": edge_family,
        "transition_policy_id": policy_id,
        "treatment": override_treatment,
        "radius_mm": override_radius,
        "adjacent_surface_ids": [],
        "transition_surface_ids": [surface_id],
        "feature_id": surface_id,
    } in graph["edge_treatment_sites"]


def test_v08_axisymmetric_infeasible_radius_records_transition_failure_without_mutation():
    geometry = _geometry_for_v08(
        transition_overrides={
            "hub_top_outer.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 1000.0,
            }
        }
    )

    graph = geometry["surface_graph"]
    failure = next(
        failure
        for failure in graph["transition_failures"]
        if failure["edge_family"] == "hub_top_outer"
    )
    validity_checks = {
        check["name"]: check
        for check in geometry["validity"]["checks"]
    }
    failed_surface = _surface_by_id(geometry, "hub_top_outer_transition_surface")

    assert failure == {
        "edge_treatment_site_id": "hub_top_outer",
        "edge_family": "hub_top_outer",
        "transition_policy_id": "hub_top_outer.default",
        "requested_radius_mm": 1000.0,
        "reason": "radius_exceeds_local_feasible_limit",
        "suggested_max_radius_mm": 120.0,
        "status": "FAIL",
    }
    for metadata_key in [
        "radius_mm",
        "transition_geometry",
        "transition_quality",
        "transition_policy_id",
        "treatment",
        "edge_treatment_site_id",
    ]:
        assert metadata_key not in failed_surface
    assert not any(
        site["edge_family"] == "hub_top_outer"
        for site in graph["edge_treatment_sites"]
    )
    assert validity_checks["required_transition_geometry_resolved"]["status"] == "FAIL"
    assert validity_checks["required_transition_geometry_resolved"]["failure_count"] > 0


def test_v08_closed_hood_defaults_resolve_transition_geometry():
    geometry = _geometry_for_v08(preset_name="radial_closed_reference_v0_8")

    graph = geometry["surface_graph"]
    inlet = _surface_by_id(geometry, "hood_chamfer_inlet_surface")
    outlet = _surface_by_id(geometry, "hood_chamfer_outlet_surface")

    for surface, surface_id, edge_family in [
        (inlet, "hood_chamfer_inlet_surface", "hood_inlet_lip"),
        (outlet, "hood_chamfer_outlet_surface", "hood_outlet_lip"),
    ]:
        assert surface["edge_treatment_site_id"] == edge_family
        assert surface["edge_family"] == edge_family
        assert surface["transition_policy_id"] == f"{edge_family}.default"
        assert surface["treatment"] == "fillet"
        assert surface["radius_mm"] == 3.0
        assert surface["transition_geometry"] == "resolved_fillet_patch"
        assert surface["transition_quality"]["has_resolved_patch"]
        assert {
            "edge_treatment_site_id": edge_family,
            "edge_family": edge_family,
            "transition_policy_id": f"{edge_family}.default",
            "treatment": "fillet",
            "radius_mm": 3.0,
            "adjacent_surface_ids": [],
            "transition_surface_ids": [surface_id],
            "feature_id": surface_id,
        } in graph["edge_treatment_sites"]


def test_v08_closed_hood_override_changes_transition_geometry():
    baseline = _geometry_for_v08(preset_name="radial_closed_reference_v0_8")
    changed = _geometry_for_v08(
        transition_overrides={
            "hood_outlet_lip.default": {
                "enabled": True,
                "treatment": "chamfer",
                "radius_mm": 9.0,
            }
        },
        preset_name="radial_closed_reference_v0_8",
    )

    baseline_outlet = _surface_by_id(baseline, "hood_chamfer_outlet_surface")
    changed_outlet = _surface_by_id(changed, "hood_chamfer_outlet_surface")

    assert changed_outlet["edge_treatment_site_id"] == "hood_outlet_lip"
    assert changed_outlet["edge_family"] == "hood_outlet_lip"
    assert changed_outlet["transition_policy_id"] == "hood_outlet_lip.default"
    assert changed_outlet["treatment"] == "chamfer"
    assert changed_outlet["radius_mm"] == 9.0
    assert changed_outlet["transition_geometry"] == "resolved_chamfer_patch"
    assert _grid_digest(changed_outlet) != _grid_digest(baseline_outlet)


def test_v08_axisymmetric_non_finite_grid_records_failure_without_success_metadata():
    surface_graph = {
        "surfaces": [
            {
                "id": "hub_top_outer_transition_surface",
                "edge_family": "hub_top_outer",
                "uv_grid": [
                    [[float("nan"), 0.0, 397.0], [148.0, 0.0, 398.0]],
                    [[149.0, 0.0, 399.0], [150.0, 0.0, 400.0]],
                ],
            }
        ],
    }

    resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies={
            "hub_top_outer.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 3.0,
            }
        },
        geometry_version="0.8",
    )

    quality_checks = {
        check["check_id"]: check["status"]
        for check in resolution.quality_checks
    }
    resolved_surface = resolution.surface_graph["surfaces"][0]

    assert resolution.transition_failures
    assert quality_checks["required_transition_geometry_resolved"] == "FAIL"
    assert "edge_treatment_site_id" not in resolved_surface
    assert "transition_quality" not in resolved_surface
    assert "transition_geometry" not in resolved_surface
    assert resolved_surface["uv_grid"] == surface_graph["surfaces"][0]["uv_grid"]


def test_v08_axisymmetric_failure_clears_stale_success_metadata():
    surface_graph = {
        "surfaces": [
            {
                "id": "hub_top_outer_transition_surface",
                "edge_family": "hub_top_outer",
                "role": "hub_top_outer_sampled_fillet_transition",
                "uv_grid": [
                    [[float("nan"), 0.0, 397.0], [148.0, 0.0, 398.0]],
                    [[149.0, 0.0, 399.0], [150.0, 0.0, 400.0]],
                ],
                "edge_treatment_site_id": "hub_top_outer",
                "transition_policy_id": "hub_top_outer.default",
                "treatment": "fillet",
                "radius_mm": 3.0,
                "transition_geometry": "resolved_fillet_patch",
                "transition_quality": {"has_resolved_patch": True},
            }
        ],
    }

    resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies={
            "hub_top_outer.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 3.0,
            }
        },
        geometry_version="0.8",
    )

    quality_checks = {
        check["check_id"]: check["status"]
        for check in resolution.quality_checks
    }
    resolved_surface = resolution.surface_graph["surfaces"][0]

    assert resolution.transition_failures
    assert quality_checks["required_transition_geometry_resolved"] == "FAIL"
    assert resolved_surface["id"] == "hub_top_outer_transition_surface"
    assert resolved_surface["edge_family"] == "hub_top_outer"
    assert resolved_surface["role"] == "hub_top_outer_sampled_fillet_transition"
    assert resolved_surface["uv_grid"] == surface_graph["surfaces"][0]["uv_grid"]
    for metadata_key in [
        "edge_treatment_site_id",
        "transition_policy_id",
        "treatment",
        "radius_mm",
        "transition_geometry",
        "transition_quality",
    ]:
        assert metadata_key not in resolved_surface


def test_v08_axisymmetric_failure_clears_stale_top_level_transition_metadata():
    surface_graph = {
        "edge_treatment_sites": [
            {
                "edge_treatment_site_id": "hub_top_outer",
                "edge_family": "hub_top_outer",
                "transition_policy_id": "hub_top_outer.default",
                "transition_surface_ids": ["hub_top_outer_transition_surface"],
            }
        ],
        "transition_failures": [
            {
                "edge_treatment_site_id": "stale",
                "status": "PASS",
            }
        ],
        "surfaces": [
            {
                "id": "hub_top_outer_transition_surface",
                "edge_family": "hub_top_outer",
                "uv_grid": [
                    [[float("nan"), 0.0, 397.0], [148.0, 0.0, 398.0]],
                    [[149.0, 0.0, 399.0], [150.0, 0.0, 400.0]],
                ],
            }
        ],
    }

    resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies={
            "hub_top_outer.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 3.0,
            }
        },
        geometry_version="0.8",
    )

    quality_checks = {
        check["check_id"]: check["status"]
        for check in resolution.quality_checks
    }

    assert resolution.transition_failures
    assert resolution.edge_treatment_sites == []
    assert quality_checks["required_transition_geometry_resolved"] == "FAIL"
    assert not resolution.surface_graph.get("edge_treatment_sites")
    assert not resolution.surface_graph.get("transition_failures")


def test_v08_axisymmetric_resolution_synchronizes_control_net_and_cad_control_points():
    geometry = _geometry_for_v08(
        transition_overrides={
            "hub_bottom_outer.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 11.0,
            }
        }
    )

    surface = _surface_by_id(geometry, "hub_bottom_outer_transition_surface")

    assert surface["transition_geometry"] == "resolved_fillet_patch"
    assert surface["uv_grid"] == surface["control_net"]
    assert surface["uv_grid"] == surface["cad_surface"]["control_points"]
    assert surface["uv_grid"] is not surface["control_net"]
    assert surface["uv_grid"] is not surface["cad_surface"]["control_points"]
    assert surface["control_net"] is not surface["cad_surface"]["control_points"]


def test_v08_disabled_axisymmetric_policy_removes_transition_surface():
    geometry = _geometry_for_v08(
        transition_overrides={
            "hub_bottom_outer.default": {
                "enabled": False,
                "treatment": "none",
                "radius_mm": 0.0,
            }
        }
    )

    graph = geometry["surface_graph"]
    surface_ids = {surface["id"] for surface in graph["surfaces"]}

    assert "hub_bottom_outer_transition_surface" not in surface_ids
    assert all(
        site["edge_family"] != "hub_bottom_outer"
        for site in graph["edge_treatment_sites"]
    )


def test_v08_closed_tip_to_shroud_policy_owns_tip_transition_surface():
    geometry = _geometry_for_v08(
        {
            "blade_tip_to_shroud.default": {
                "enabled": True,
                "treatment": "chamfer",
                "radius_mm": 9.0,
            }
        },
        preset_name="radial_closed_reference_v0_8",
    )

    graph = geometry["surface_graph"]
    tip = _surface_by_id(geometry, "blade_0_tip_transition_surface")

    assert tip["edge_treatment_site_id"] == "blade_0.tip_to_shroud"
    assert tip["edge_family"] == "blade_tip_to_shroud"
    assert tip["transition_policy_id"] == "blade_tip_to_shroud.default"
    assert tip["treatment"] == "chamfer"
    assert tip["radius_mm"] == 9.0
    assert tip["role"] == "blade_tip_edge_chamfer"
    assert tip["transition_geometry"] == "resolved_chamfer_patch"
    assert {
        "edge_treatment_site_id": "blade_0.tip_to_shroud",
        "edge_family": "blade_tip_to_shroud",
        "transition_policy_id": "blade_tip_to_shroud.default",
        "treatment": "chamfer",
        "radius_mm": 9.0,
        "adjacent_surface_ids": ["blade_0_pressure_surface", "blade_0_suction_surface"],
        "transition_surface_ids": ["blade_0_tip_transition_surface"],
        "feature_id": "blade_0_tip_transition_surface",
    } in graph["edge_treatment_sites"]
    assert all(
        site["edge_treatment_site_id"] != "blade_0.tip_or_shroud"
        for site in graph["edge_treatment_sites"]
    )


def test_v08_closed_tip_or_shroud_policy_resolves_tip_when_tip_to_shroud_disabled():
    geometry = _geometry_for_v08(preset_name="radial_closed_reference_v0_8")

    tip = _surface_by_id(geometry, "blade_0_tip_transition_surface")

    assert tip["edge_treatment_site_id"] == "blade_0.tip_or_shroud"
    assert tip["edge_family"] == "blade_tip_or_shroud"
    assert tip["transition_policy_id"] == "blade_tip_or_shroud.default"
    assert tip["treatment"] == "fillet"
    assert tip["radius_mm"] == 2.0


def test_v08_disabled_blade_root_transition_restores_sharp_boundary():
    geometry = _geometry_for_v08(
        transition_overrides={
            "blade_root_to_hub.default": {
                "enabled": False,
                "treatment": "none",
                "radius_mm": 0.0,
            }
        }
    )

    graph = geometry["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    assert not [
        surface_id
        for surface_id in surfaces
        if surface_id.startswith("blade_") and surface_id.endswith("_root_transition_surface")
    ]
    assert "hub_root" not in surfaces["blade_0_pressure_surface"].get("trimmed_boundaries", {})
    assert "hub_root" not in surfaces["blade_0_suction_surface"].get("trimmed_boundaries", {})


def test_v08_malformed_blade_root_grid_records_failure_without_partial_trim():
    surface_graph = {
        "surfaces": [
            {
                "id": "blade_0_pressure_surface",
                "uv_grid": [
                    [[10.0, 0.0, 0.0]],
                    [[10.0, 1.0, 0.0]],
                ],
            },
            {
                "id": "blade_0_suction_surface",
                "uv_grid": [
                    [[9.0, 0.0, 0.0], [8.0, 0.0, 0.0]],
                    [[9.0, 1.0, 0.0], [8.0, 1.0, 0.0]],
                ],
            },
            {
                "id": "blade_0_root_transition_surface",
                "edge_family": "blade_root_to_hub",
                "uv_grid": [],
            },
            {
                "id": "hub_revolve_surface",
                "uv_grid": [],
            },
        ],
    }

    resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies={
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 8.0,
            }
        },
        geometry_version="0.8",
    )

    surfaces = {
        surface["id"]: surface
        for surface in resolution.surface_graph["surfaces"]
    }
    assert resolution.transition_failures == [
        {
            "edge_treatment_site_id": "blade_0.root_to_hub",
            "edge_family": "blade_root_to_hub",
            "transition_policy_id": "blade_root_to_hub.default",
            "status": "FAIL",
            "reason": "blade_0_pressure_surface uv_grid row 0 must contain at least 2 v points",
        }
    ]
    assert resolution.edge_treatment_sites == []
    assert "trimmed_boundaries" not in surfaces["blade_0_pressure_surface"]
    assert "trimmed_boundaries" not in surfaces["blade_0_suction_surface"]
    assert surfaces["blade_0_pressure_surface"]["uv_grid"] == surface_graph["surfaces"][0]["uv_grid"]


@pytest.mark.parametrize("malformed_pressure_grid", [None, [None]])
def test_v08_uncopyable_blade_root_grid_records_failure_without_partial_trim(malformed_pressure_grid):
    surface_graph = {
        "surfaces": [
            {
                "id": "blade_0_pressure_surface",
                "uv_grid": malformed_pressure_grid,
            },
            {
                "id": "blade_0_suction_surface",
                "uv_grid": [
                    [[9.0, 0.0, 0.0], [8.0, 0.0, 0.0]],
                    [[9.0, 1.0, 0.0], [8.0, 1.0, 0.0]],
                ],
            },
            {
                "id": "blade_0_root_transition_surface",
                "edge_family": "blade_root_to_hub",
                "uv_grid": [],
            },
            {
                "id": "hub_revolve_surface",
                "uv_grid": [],
            },
        ],
    }

    resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies={
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "fillet",
                "radius_mm": 8.0,
            }
        },
        geometry_version="0.8",
    )

    surfaces = {
        surface["id"]: surface
        for surface in resolution.surface_graph["surfaces"]
    }
    quality_checks = {
        check["check_id"]: check["status"]
        for check in resolution.quality_checks
    }
    assert resolution.transition_failures
    assert quality_checks["required_transition_geometry_resolved"] == "FAIL"
    assert "trimmed_boundaries" not in surfaces["blade_0_pressure_surface"]
    assert "trimmed_boundaries" not in surfaces["blade_0_suction_surface"]


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
