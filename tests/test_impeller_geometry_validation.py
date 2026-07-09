from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import (
    build_geometry_validation_report,
    geometry_validation_blocks_export,
)
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata, _impeller_geometry_validation_report


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


def test_v10_4_root_patch_ids_preserve_double_sided_root_topology_compatibility():
    report = build_geometry_validation_report(
        transition_policies=_default_policies(),
        surface_graph={
            "surfaces": [
                {
                    "id": "blade_0_root_annular_surface_pressure_root_patch",
                    "face_family": "blade_root",
                    "display": {
                        "inspection_class": "root_to_hub_blend",
                        "visible_by_default": True,
                        "aggregate_surface": False,
                    },
                },
                {
                    "id": "blade_0_root_annular_surface_suction_root_patch",
                    "face_family": "blade_root",
                    "display": {
                        "inspection_class": "root_to_hub_blend",
                        "visible_by_default": True,
                        "aggregate_surface": False,
                    },
                },
            ],
        },
    )

    assert report["geometry_validation_status"] == "PASS"
    assert not any(
        failure["reason"] == "missing_double_sided_root_transition_surface"
        for failure in report["blocking_failures"]
    )


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


def _minimal_v091_graph(
    *,
    topology_report: dict | None = None,
    mesh_report: dict | None = None,
) -> dict:
    graph = {
        "transition_geometry_status": "topology_first_validated_transition_graph",
        "surfaces": [],
        "transition_topology_report": {
            "corner_patch_count": 6,
            "required_corner_patch_count": 6,
            "boundary_node_identity_failures": [],
        },
    }
    if topology_report is not None:
        graph["transition_topology_report"] = topology_report
    if mesh_report is not None:
        graph["mesh_manifoldness_report"] = mesh_report
    return graph


def _clean_v091_mesh_report(**overrides: int) -> dict:
    report = {
        "vertex_count": 8,
        "face_count": 12,
        "free_edge_count": 0,
        "nonmanifold_edge_count": 0,
        "duplicate_face_count": 0,
        "zero_area_face_count": 0,
        "skipped_triangle_count": 0,
        "source_patch_free_edge_count": 4,
        "synthetic_closure_triangle_count": 4,
        "closure_policy": "synthetic_review_fan_caps_for_undeclared_free_edge_loops",
    }
    report.update(overrides)
    return report


def test_v091_validation_fails_when_mesh_report_is_missing():
    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=_minimal_v091_graph(),
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert geometry_validation_blocks_export(report) is True
    assert any(failure["reason"] == "missing_mesh_manifoldness_report" for failure in report["blocking_failures"])


def test_v091_validation_fails_when_topology_report_is_missing():
    graph = _minimal_v091_graph(mesh_report=_clean_v091_mesh_report())
    graph.pop("transition_topology_report")

    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=graph,
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "missing_transition_topology_report" for failure in report["blocking_failures"])
    assert any(
        check["check_id"] == "v091_transition_topology_report" and check["status"] == "FAIL"
        for check in report["checks"]
    )


@pytest.mark.parametrize(
    ("mesh_counts", "reason"),
    [
        ({"free_edge_count": 1}, "mesh_has_free_edges"),
        ({"nonmanifold_edge_count": 1}, "mesh_has_nonmanifold_edges"),
        ({"zero_area_face_count": 1}, "mesh_has_zero_area_faces"),
        ({"duplicate_face_count": 1}, "mesh_has_duplicate_faces"),
    ],
)
def test_v091_validation_fails_on_dirty_final_mesh_counts(mesh_counts: dict, reason: str):
    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=_minimal_v091_graph(mesh_report=_clean_v091_mesh_report(**mesh_counts)),
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == reason for failure in report["blocking_failures"])
    assert any(check["status"] == "FAIL" for check in report["checks"])


def test_v091_validation_fails_when_skipped_triangle_accounting_is_missing():
    mesh_report = _clean_v091_mesh_report()
    mesh_report.pop("skipped_triangle_count")
    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=_minimal_v091_graph(mesh_report=mesh_report),
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(
        failure["reason"] == "missing_mesh_skipped_triangle_accounting"
        for failure in report["blocking_failures"]
    )
    assert any(
        check["check_id"] == "v091_mesh_skipped_triangle_accounting" and check["status"] == "FAIL"
        for check in report["checks"]
    )


def test_v091_validation_fails_on_missing_required_corner_patches():
    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=_minimal_v091_graph(
            topology_report={
                "corner_patch_count": 5,
                "required_corner_patch_count": 6,
                "boundary_node_identity_failures": [],
            },
            mesh_report=_clean_v091_mesh_report(),
        ),
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "missing_required_corner_patches" for failure in report["blocking_failures"])


def test_v091_validation_fails_on_boundary_node_identity_failures():
    report = build_geometry_validation_report(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph=_minimal_v091_graph(
            topology_report={
                "corner_patch_count": 6,
                "required_corner_patch_count": 6,
                "boundary_node_identity_failures": [{"edge_id": "edge-a"}],
            },
            mesh_report=_clean_v091_mesh_report(),
        ),
        capability_matrix_id="impeller_v0_91_kernel_capabilities",
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "boundary_node_identity_failed" for failure in report["blocking_failures"])


def test_v091_default_service_validation_passes_with_explicit_synthetic_closure_caveat():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_91")
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    transition_policies = resolve_transition_policies(edge_families, parameters, None)

    geometry = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )
    validation_report = _impeller_geometry_validation_report(
        runtime,
        parameters,
        geometry,
        transition_policies,
    )

    graph = geometry["surface_graph"]
    mesh_report = graph["mesh_manifoldness_report"]
    assert validation_report["geometry_validation_status"] == "PASS"
    assert mesh_report["free_edge_count"] == 0
    assert mesh_report["nonmanifold_edge_count"] == 0
    assert mesh_report["zero_area_face_count"] == 0
    assert mesh_report["source_patch_free_edge_count"] > 0
    assert validation_report["transition_validation_summary"]["source_patch_free_edge_count"] == mesh_report[
        "source_patch_free_edge_count"
    ]
    assert any(
        claim["reason"] == "synthetic_mesh_closure_review_caveat"
        for claim in validation_report["unsupported_claims"]
    )
