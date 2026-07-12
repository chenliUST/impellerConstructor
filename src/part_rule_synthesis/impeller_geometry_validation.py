from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from part_rule_synthesis.impeller_v10_2_continuity_validation import (
    validate_v10_2_continuous_blade_attachment,
)
from part_rule_synthesis.impeller_v10_3_validation import validate_v10_3_surface_graph
from part_rule_synthesis.impeller_v10_4_validation import validate_v10_4_surface_graph
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph


PASS = "PASS"
FAIL = "FAIL"
V091_TRANSITION_GEOMETRY_STATUS = "topology_first_validated_transition_graph"
V10_TRANSITION_GEOMETRY_STATUS = "topology_first_closed_nurbs_impeller_surface_graph"
V10_3_TRANSITION_GEOMETRY_STATUS = "topology_first_section_loop_blade_root_blend_surface_graph"
V10_4_TRANSITION_GEOMETRY_STATUS = "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
V11_TRANSITION_GEOMETRY_STATUS = "topology_first_blade_to_blade_5_loop_surface_family_graph"
V10_TOPOLOGY_FIRST_STATUSES = {
    V10_TRANSITION_GEOMETRY_STATUS,
    V10_3_TRANSITION_GEOMETRY_STATUS,
    V10_4_TRANSITION_GEOMETRY_STATUS,
}
ROOT_LEGACY_RE = re.compile(r"^blade_\d+_root_transition_surface$")
PRESSURE_ROOT_RE = re.compile(
    r"^blade_\d+_(?:pressure_root_transition_surface|root_annular_surface_pressure_root_patch)$"
)
SUCTION_ROOT_RE = re.compile(
    r"^blade_\d+_(?:suction_root_transition_surface|root_annular_surface_suction_root_patch)$"
)
V10_BLADE_FACE_RE = re.compile(r"^blade_(\d+)_(.+)$")
V10_3_TRANSITION_FACE_FAMILIES = {
    "blade_leading_edge",
    "blade_trailing_edge",
    "blade_root",
    "blade_tip",
}


def build_geometry_validation_report(
    *,
    parameters: dict[str, Any] | None = None,
    facets: dict[str, Any] | None = None,
    transition_policies: dict[str, Any] | None = None,
    surface_graph: dict[str, Any] | None = None,
    capability_matrix_id: str = "impeller_v0_9_kernel_capabilities",
) -> dict[str, Any]:
    graph = surface_graph or {}
    policies = transition_policies or {}
    surfaces = [surface for surface in graph.get("surfaces", []) if isinstance(surface, Mapping)]
    surfaces_by_id = {str(surface.get("id")): surface for surface in surfaces if surface.get("id")}
    sites = [site for site in graph.get("edge_treatment_sites", []) if isinstance(site, Mapping)]
    sites_by_transition_surface = _sites_by_transition_surface(sites)
    transition_surfaces = [surface for surface in surfaces if _is_transition_surface(surface)]

    blocking_failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for failure in graph.get("transition_failures", []) or []:
        if isinstance(failure, Mapping):
            blocking_failures.append(
                _failure(
                    str(failure.get("reason", "transition_resolver_failure")),
                    surface_graph_id=failure.get("surface_graph_id") or failure.get("surface_id"),
                    edge_treatment_site_id=failure.get("edge_treatment_site_id"),
                    edge_family=failure.get("edge_family"),
                    transition_policy_id=failure.get("transition_policy_id"),
                    requested_radius_mm=failure.get("requested_radius_mm"),
                    suggested_max_radius_mm=failure.get("suggested_max_radius_mm"),
                    blade_index=failure.get("blade_index"),
                    stage=failure.get("stage"),
                )
            )
        else:
            blocking_failures.append(_failure("transition_resolver_failure", detail=str(failure)))

    _validate_root_transition_topology(graph, transition_surfaces, policies, blocking_failures)
    for surface in transition_surfaces:
        _validate_transition_surface(
            surface,
            policies,
            surfaces_by_id,
            sites_by_transition_surface.get(str(surface.get("id")), []),
            blocking_failures,
        )

    _validate_v091_topology_and_mesh(graph, blocking_failures)
    _validate_v10_topology_first_graph(graph, surfaces, surfaces_by_id, blocking_failures)

    v10_3_report = validate_v10_3_surface_graph(graph)
    if v10_3_report["status"] == FAIL:
        blocking_failures.extend(
            _failure(
                str(failure.get("reason", "v1_0_3_validation_failed")),
                surface_graph_id=failure.get("surface_id"),
                expected_count=failure.get("expected_count"),
                observed_count=failure.get("observed_count"),
                max_shared_edge_gap_mm=failure.get("max_shared_edge_gap_mm"),
                tolerance_mm=failure.get("tolerance_mm"),
            )
            for failure in v10_3_report["failures"]
        )

    v10_4_failures = validate_v10_4_surface_graph(graph)
    blocking_failures.extend(v10_4_failures)
    v11_failures = validate_v11_surface_graph(graph)
    blocking_failures.extend(v11_failures)

    v10_2_report = validate_v10_2_continuous_blade_attachment(graph)
    v10_2_summary = None
    if v10_2_report["status"] != "SKIP":
        blocking_failures.extend(v10_2_report["blocking_failures"])
        v10_2_summary = v10_2_report["summary"]

    blocking_failures = _dedupe_blocking_failures(blocking_failures)
    if v10_2_report["status"] != "SKIP":
        checks.append(
            {
                "check_id": "v10_2_continuous_blade_attachment",
                "status": PASS if v10_2_report["status"] == PASS else FAIL,
            }
        )
    if v10_3_report["status"] != "SKIP":
        checks.append(
            {
                "check_id": "v10_3_section_loop_root_blend",
                "status": PASS if v10_3_report["status"] == PASS else FAIL,
                "failure_count": v10_3_report["failure_count"],
            }
        )
    if graph.get("geometry_patch_version") == "1.0.4":
        checks.extend(
            [
                {
                    "check_id": "v10_4_surface_graph_contract",
                    "status": PASS if not v10_4_failures else FAIL,
                    "failure_count": len(v10_4_failures),
                },
                {
                    "check_id": "v10_4_root_quality",
                    "status": FAIL if _has_blocking_reason(blocking_failures, "v1_0_4_root_") else PASS,
                },
                {
                    "check_id": "v10_4_tip_quality",
                    "status": FAIL if _has_blocking_reason(blocking_failures, "v1_0_4_tip_") else PASS,
                },
                {
                    "check_id": "v10_4_hub_quality",
                    "status": FAIL if _has_blocking_reason(blocking_failures, "v1_0_4_hub_") else PASS,
                },
                {
                    "check_id": "v10_4_continuity_quality",
                    "status": FAIL
                    if _has_blocking_reason(blocking_failures, "v1_0_4_g2_")
                    else PASS,
                },
                {
                    "check_id": "v10_4_angle_quality",
                    "status": FAIL
                    if _has_blocking_reason(blocking_failures, "v1_0_4_blade_hub_angle_")
                    else PASS,
                },
            ]
        )
    if graph.get("geometry_patch_version") in {"1.1.0", "1.1.1", "1.1.2"}:
        checks.extend(
            [
                {
                    "check_id": "v1_1_surface_graph_contract",
                    "status": PASS if not v11_failures else FAIL,
                    "failure_count": len(v11_failures),
                },
                {
                    "check_id": "v1_1_root_quality",
                    "status": FAIL if _has_blocking_reason(blocking_failures, "v1_1_root_") else PASS,
                },
                {
                    "check_id": "v1_1_tip_quality",
                    "status": FAIL if _has_blocking_reason(blocking_failures, "v1_1_tip_") else PASS,
                },
                {
                    "check_id": "v1_1_shared_boundary_uv_contract",
                    "status": FAIL
                    if any(
                        str(failure.get("reason") or "")
                        in {"v1_1_surface_boundary_not_shared", "v1_1_surface_loft_foldover"}
                        for failure in blocking_failures
                    )
                    else PASS,
                },
            ]
        )

    for check_id, reason in [
        ("transition_convexity", "fillet_convexity_failed"),
        ("adjacent_trim_coverage", "adjacent_surface_not_trimmed"),
        ("transition_radius_sync", "transition_radius_not_synchronized"),
        ("disabled_transition_surfaces", "disabled_policy_has_transition_surface"),
        ("double_sided_root_topology", "legacy_single_root_transition_surface"),
        ("v091_transition_topology_report", "missing_transition_topology_report"),
        ("v091_required_corner_patches", "missing_required_corner_patches"),
        ("v091_boundary_node_identity", "boundary_node_identity_failed"),
        ("v091_mesh_manifoldness_report", "missing_mesh_manifoldness_report"),
        ("v091_final_mesh_free_edges", "mesh_has_free_edges"),
        ("v091_final_mesh_nonmanifold_edges", "mesh_has_nonmanifold_edges"),
        ("v091_final_mesh_zero_area_faces", "mesh_has_zero_area_faces"),
        ("v091_final_mesh_duplicate_faces", "mesh_has_duplicate_faces"),
        ("v091_final_mesh_skipped_triangles", "mesh_has_skipped_triangles"),
        ("v091_mesh_skipped_triangle_accounting", "missing_mesh_skipped_triangle_accounting"),
        ("v10_required_native_blade_faces", "v1_0_missing_named_blade_face"),
        ("v10_transition_fields_forbidden", "v1_0_transition_geometry_field_forbidden"),
        ("v10_topology_graph_present", "v1_0_topology_graph_missing"),
        ("v10_synthetic_shared_edges_forbidden", "v1_0_synthetic_shared_edge_forbidden"),
        ("v10_shared_edge_gap", "v1_0_shared_edge_gap_exceeds_tolerance"),
        ("v10_face_foldover", "v1_0_face_foldover_detected"),
        ("v10_surface_graph_nonempty", "v1_0_surface_graph_empty"),
        ("v10_shared_edges_present", "v1_0_shared_edges_missing"),
    ]:
        checks.append(
            {
                "check_id": check_id,
                "status": FAIL if any(failure["reason"] == reason for failure in blocking_failures) else PASS,
            }
        )

    status = FAIL if blocking_failures else PASS
    report = {
        "geometry_validation_status": status,
        "kernel_capability_matrix_id": capability_matrix_id,
        "capability_claim_level": "review_grade_validated" if status == PASS else "blocked_review_grade",
        "unsupported_claims": _unsupported_claims(graph),
        "parameters_observed": parameters or {},
        "facets_observed": facets or {},
        "checks": checks,
        "blocking_failures": blocking_failures,
        "transition_validation_summary": _transition_validation_summary(transition_surfaces, blocking_failures, graph),
    }
    if v10_2_summary is not None:
        report["v1_0_2_validation_summary"] = v10_2_summary
    if v10_3_report["status"] != "SKIP":
        report["v1_0_3_validation_summary"] = v10_3_report["summary"]
    return report


def _dedupe_blocking_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for failure in failures:
        key = tuple((key, repr(value)) for key, value in sorted(failure.items()) if key not in {"status", "blocking"})
        if key in seen:
            continue
        seen.add(key)
        deduped.append(failure)
    return deduped


def _has_blocking_reason(failures: list[dict[str, Any]], prefix: str) -> bool:
    return any(str(failure.get("reason") or "").startswith(prefix) for failure in failures)


def geometry_validation_blocks_export(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    return bool(report.get("blocking_failures")) or report.get("geometry_validation_status") == FAIL


def _is_transition_surface(surface: Mapping[str, Any]) -> bool:
    display = surface.get("display") if isinstance(surface.get("display"), Mapping) else {}
    face_family = str(surface.get("face_family") or "")
    if face_family in V10_3_TRANSITION_FACE_FAMILIES:
        if face_family == "blade_root":
            return (
                display.get("inspection_class") == "root_to_hub_blend"
                and display.get("aggregate_surface") is not True
                and display.get("visible_by_default") is not False
            )
        return display.get("visible_by_default", True) is not False
    return bool(
        surface.get("edge_treatment_site_id")
        or surface.get("transition_policy_id")
        or surface.get("transition_geometry")
        or "transition" in str(surface.get("role", ""))
        or "transition" in str(surface.get("id", ""))
    )


def _sites_by_transition_surface(sites: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for site in sites:
        for surface_id in site.get("transition_surface_ids", []) or []:
            result.setdefault(str(surface_id), []).append(site)
    return result


def _validate_root_transition_topology(
    graph: Mapping[str, Any],
    transition_surfaces: list[Mapping[str, Any]],
    policies: dict[str, Any],
    blocking_failures: list[dict[str, Any]],
) -> None:
    if graph.get("transition_geometry_status") in V10_TOPOLOGY_FIRST_STATUSES:
        return
    if not _policy_enabled(policies.get("blade_root_to_hub.default", {"enabled": True})):
        return
    root_surface_ids = {str(surface.get("id")) for surface in transition_surfaces}
    for surface_id in sorted(root_surface_ids):
        if ROOT_LEGACY_RE.match(surface_id):
            blocking_failures.append(_failure("legacy_single_root_transition_surface", surface_graph_id=surface_id, edge_family="blade_root_to_hub"))
    pressure_count = sum(1 for surface_id in root_surface_ids if PRESSURE_ROOT_RE.match(surface_id))
    suction_count = sum(1 for surface_id in root_surface_ids if SUCTION_ROOT_RE.match(surface_id))
    if pressure_count != suction_count or (pressure_count == 0 and any("root" in sid for sid in root_surface_ids)):
        blocking_failures.append(
            _failure(
                "missing_double_sided_root_transition_surface",
                edge_family="blade_root_to_hub",
                pressure_root_surface_count=pressure_count,
                suction_root_surface_count=suction_count,
            )
        )


def _validate_transition_surface(
    surface: Mapping[str, Any],
    policies: dict[str, Any],
    surfaces_by_id: dict[str, Mapping[str, Any]],
    sites: list[Mapping[str, Any]],
    blocking_failures: list[dict[str, Any]],
) -> None:
    surface_id = str(surface.get("id") or surface.get("surface_graph_id") or "")
    policy_id = str(surface.get("transition_policy_id") or "")
    policy = policies.get(policy_id) if policy_id else None
    if policy is not None and not _policy_enabled(policy):
        blocking_failures.append(_failure("disabled_policy_has_transition_surface", surface_graph_id=surface_id, transition_policy_id=policy_id, edge_family=surface.get("edge_family")))
        return
    if policy is not None:
        policy_radius = _float_or_none(policy.get("radius_mm"))
        surface_radius = _float_or_none(surface.get("radius_mm"))
        if policy_radius is not None and surface_radius is not None and abs(policy_radius - surface_radius) > 1.0e-6:
            blocking_failures.append(_failure("transition_radius_not_synchronized", surface_graph_id=surface_id, transition_policy_id=policy_id, requested_radius_mm=policy_radius, surface_radius_mm=surface_radius))
    quality = surface.get("transition_quality") if isinstance(surface.get("transition_quality"), Mapping) else {}
    treatment = str(surface.get("treatment") or "")
    if treatment == "fillet":
        _validate_fillet_quality(surface, quality, blocking_failures)
    elif treatment == "chamfer":
        _validate_chamfer_quality(surface, quality, blocking_failures)
    for site in sites:
        _validate_adjacent_trim(surface, site, surfaces_by_id, blocking_failures)


def _validate_fillet_quality(surface: Mapping[str, Any], quality: Mapping[str, Any], blocking_failures: list[dict[str, Any]]) -> None:
    radius = _float_or_none(surface.get("radius_mm")) or 0.0
    min_bulge = max(0.05, 0.05 * radius)
    signed_bulge = _float_or_none(quality.get("fillet_convex_signed_bulge_mm"))
    if quality.get("convexity_status") == FAIL or (signed_bulge is not None and signed_bulge < min_bulge):
        blocking_failures.append(_failure("fillet_convexity_failed", surface_graph_id=surface.get("id"), edge_family=surface.get("edge_family"), transition_policy_id=surface.get("transition_policy_id"), signed_bulge_mm=signed_bulge, minimum_signed_bulge_mm=min_bulge))


def _validate_chamfer_quality(surface: Mapping[str, Any], quality: Mapping[str, Any], blocking_failures: list[dict[str, Any]]) -> None:
    linearity = _float_or_none(quality.get("section_linearity_max_error_mm"))
    if linearity is not None and linearity > 1.0e-4:
        blocking_failures.append(_failure("chamfer_linearity_failed", surface_graph_id=surface.get("id"), edge_family=surface.get("edge_family"), transition_policy_id=surface.get("transition_policy_id"), section_linearity_max_error_mm=linearity))


def _validate_adjacent_trim(surface: Mapping[str, Any], site: Mapping[str, Any], surfaces_by_id: dict[str, Mapping[str, Any]], blocking_failures: list[dict[str, Any]]) -> None:
    site_id = str(site.get("edge_treatment_site_id") or surface.get("edge_treatment_site_id") or "")
    for adjacent_id in site.get("adjacent_surface_ids", []) or []:
        adjacent = surfaces_by_id.get(str(adjacent_id))
        if adjacent is None:
            blocking_failures.append(_failure("adjacent_surface_missing", surface_graph_id=surface.get("id"), edge_treatment_site_id=site_id, adjacent_surface_id=adjacent_id))
            continue
        if not _surface_has_trim_for_site(adjacent, site_id):
            blocking_failures.append(_failure("adjacent_surface_not_trimmed", surface_graph_id=surface.get("id"), edge_treatment_site_id=site_id, adjacent_surface_id=adjacent_id))


def _surface_has_trim_for_site(surface: Mapping[str, Any], site_id: str) -> bool:
    trimmed = surface.get("trimmed_boundaries")
    if isinstance(trimmed, Mapping):
        for value in trimmed.values():
            if isinstance(value, Mapping) and value.get("edge_treatment_site_id") == site_id:
                return True
    exclusions = surface.get("trim_exclusion_regions")
    if isinstance(exclusions, list):
        for region in exclusions:
            if isinstance(region, Mapping) and region.get("edge_treatment_site_id") == site_id:
                return True
    return False


def _validate_v091_topology_and_mesh(graph: Mapping[str, Any], blocking_failures: list[dict[str, Any]]) -> None:
    if graph.get("transition_geometry_status") != V091_TRANSITION_GEOMETRY_STATUS:
        return
    topology_report = graph.get("transition_topology_report")
    if not isinstance(topology_report, Mapping):
        blocking_failures.append(_failure("missing_transition_topology_report"))
        topology_report = {}
    if _int_or_zero(topology_report.get("corner_patch_count")) < _int_or_zero(topology_report.get("required_corner_patch_count")):
        blocking_failures.append(_failure("missing_required_corner_patches"))
    if topology_report.get("boundary_node_identity_failures"):
        blocking_failures.append(_failure("boundary_node_identity_failed"))
    mesh_report = graph.get("mesh_manifoldness_report")
    if not isinstance(mesh_report, Mapping):
        blocking_failures.append(_failure("missing_mesh_manifoldness_report", mesh_manifoldness_report_error=graph.get("mesh_manifoldness_report_error")))
        return
    for key, reason in [
        ("free_edge_count", "mesh_has_free_edges"),
        ("nonmanifold_edge_count", "mesh_has_nonmanifold_edges"),
        ("zero_area_face_count", "mesh_has_zero_area_faces"),
        ("duplicate_face_count", "mesh_has_duplicate_faces"),
        ("skipped_triangle_count", "mesh_has_skipped_triangles"),
    ]:
        if key not in mesh_report and key == "skipped_triangle_count":
            blocking_failures.append(_failure("missing_mesh_skipped_triangle_accounting"))
        elif _int_or_zero(mesh_report.get(key)) > 0:
            blocking_failures.append(_failure(reason, **{key: _int_or_zero(mesh_report.get(key))}))


def _validate_v10_topology_first_graph(
    graph: Mapping[str, Any],
    surfaces: list[Mapping[str, Any]],
    surfaces_by_id: dict[str, Mapping[str, Any]],
    blocking_failures: list[dict[str, Any]],
) -> None:
    transition_status = graph.get("transition_geometry_status")
    if transition_status not in V10_TOPOLOGY_FIRST_STATUSES:
        return
    if not surfaces:
        blocking_failures.append(_failure("v1_0_surface_graph_empty"))
    blade_indices = sorted({match.group(1) for surface_id in surfaces_by_id if (match := V10_BLADE_FACE_RE.match(surface_id))})
    required_suffixes = (
        {"pressure_surface", "suction_surface", "leading_edge_surface", "trailing_edge_surface", "tip_dome_surface", "root_annular_surface"}
        if transition_status in {V10_3_TRANSITION_GEOMETRY_STATUS, V10_4_TRANSITION_GEOMETRY_STATUS}
        else {"pressure_surface", "suction_surface", "leading_edge_surface", "trailing_edge_surface", "tip_surface", "root_annular_surface"}
    )
    for blade_index in blade_indices:
        for suffix in required_suffixes:
            surface_id = f"blade_{blade_index}_{suffix}"
            if surface_id not in surfaces_by_id:
                blocking_failures.append(_failure("v1_0_missing_named_blade_face", surface_graph_id=surface_id, blade_index=blade_index, required_face_suffix=suffix))
    for surface in surfaces:
        if "transition_geometry" in surface or "edge_treatment_site_id" in surface or "transition_policy_id" in surface:
            blocking_failures.append(_failure("v1_0_transition_geometry_field_forbidden", surface_graph_id=surface.get("id")))
        if surface.get("foldover_status") == FAIL:
            blocking_failures.append(_failure("v1_0_face_foldover_detected", surface_graph_id=surface.get("id")))
    topology_graph = graph.get("topology_graph")
    if not isinstance(topology_graph, Mapping):
        blocking_failures.append(_failure("v1_0_topology_graph_missing"))
        return
    if topology_graph.get("topology_status") == FAIL:
        blocking_failures.append(_failure("v1_0_topology_graph_failed"))
    if _int_or_zero(topology_graph.get("shared_edge_count")) <= 0:
        blocking_failures.append(_failure("v1_0_shared_edges_missing"))
    synthetic_shared_edge_count = _int_or_zero(topology_graph.get("synthetic_shared_edge_count"))
    if synthetic_shared_edge_count:
        blocking_failures.append(_failure("v1_0_synthetic_shared_edge_forbidden", synthetic_shared_edge_count=synthetic_shared_edge_count))
    max_gap = _float_or_none(topology_graph.get("max_shared_edge_gap_mm"))
    if max_gap is None or max_gap > 1.0e-9:
        blocking_failures.append(_failure("v1_0_shared_edge_gap_exceeds_tolerance", max_shared_edge_gap_mm=max_gap, tolerance_mm=1.0e-9))


def _unsupported_claims(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    if graph.get("transition_geometry_status") != V091_TRANSITION_GEOMETRY_STATUS:
        return []
    mesh_report = graph.get("mesh_manifoldness_report")
    if not isinstance(mesh_report, Mapping):
        return []
    source_patch_free_edge_count = _int_or_zero(mesh_report.get("source_patch_free_edge_count"))
    synthetic_closure_triangle_count = _int_or_zero(mesh_report.get("synthetic_closure_triangle_count"))
    if source_patch_free_edge_count <= 0 and synthetic_closure_triangle_count <= 0:
        return []
    return [{"reason": "synthetic_mesh_closure_review_caveat", "blocking": False, "source_patch_free_edge_count": source_patch_free_edge_count, "synthetic_closure_triangle_count": synthetic_closure_triangle_count, "closure_policy": mesh_report.get("closure_policy")}]


def _transition_validation_summary(transition_surfaces: list[Mapping[str, Any]], blocking_failures: list[dict[str, Any]], graph: Mapping[str, Any]) -> dict[str, Any]:
    by_family = Counter(_transition_surface_family(surface) for surface in transition_surfaces)
    failures_by_reason = Counter(failure["reason"] for failure in blocking_failures)
    summary = {
        "transition_surface_count": len(transition_surfaces),
        "transition_surface_count_by_family": dict(sorted(by_family.items())),
        "blocking_failure_count": len(blocking_failures),
        "blocking_failure_count_by_reason": dict(sorted(failures_by_reason.items())),
    }
    if graph.get("transition_geometry_status") == V091_TRANSITION_GEOMETRY_STATUS:
        topology_report = graph.get("transition_topology_report")
        if isinstance(topology_report, Mapping):
            summary.update(
                {
                    "corner_patch_count": _int_or_zero(topology_report.get("corner_patch_count")),
                    "required_corner_patch_count": _int_or_zero(topology_report.get("required_corner_patch_count")),
                    "boundary_node_identity_failure_count": len(topology_report.get("boundary_node_identity_failures") or []),
                }
            )
        mesh_report = graph.get("mesh_manifoldness_report")
        if isinstance(mesh_report, Mapping):
            summary.update(
                {
                    "mesh_free_edge_count": _int_or_zero(mesh_report.get("free_edge_count")),
                    "mesh_nonmanifold_edge_count": _int_or_zero(mesh_report.get("nonmanifold_edge_count")),
                    "mesh_zero_area_face_count": _int_or_zero(mesh_report.get("zero_area_face_count")),
                    "mesh_skipped_triangle_count": _int_or_zero(mesh_report.get("skipped_triangle_count")),
                    "singular_corner_cell_count": _int_or_zero(mesh_report.get("singular_corner_cell_count")),
                    "source_patch_free_edge_count": _int_or_zero(mesh_report.get("source_patch_free_edge_count")),
                    "synthetic_closure_triangle_count": _int_or_zero(mesh_report.get("synthetic_closure_triangle_count")),
                }
            )
    return summary


def _transition_surface_family(surface: Mapping[str, Any]) -> str:
    edge_family = surface.get("edge_family")
    if edge_family:
        return str(edge_family)
    face_family = str(surface.get("face_family") or "")
    if face_family == "blade_root":
        return "blade_root_to_hub"
    if face_family == "blade_tip":
        return "blade_tip_dome"
    if face_family == "blade_leading_edge":
        return "blade_leading_edge"
    if face_family == "blade_trailing_edge":
        return "blade_trailing_edge"
    return "unspecified"


def _policy_enabled(policy: Mapping[str, Any]) -> bool:
    return policy.get("enabled", True) is not False and policy.get("treatment") != "none"


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": FAIL,
        "blocking": True,
        "reason": reason,
        **{key: value for key, value in metadata.items() if value is not None},
    }
