from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any


PASS = "PASS"
FAIL = "FAIL"
V091_TRANSITION_GEOMETRY_STATUS = "topology_first_validated_transition_graph"
ROOT_LEGACY_RE = re.compile(r"^blade_\d+_root_transition_surface$")
PRESSURE_ROOT_RE = re.compile(r"^blade_\d+_pressure_root_transition_surface$")
SUCTION_ROOT_RE = re.compile(r"^blade_\d+_suction_root_transition_surface$")


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
    transition_surfaces = [
        surface
        for surface in surfaces
        if _is_transition_surface(surface)
    ]

    blocking_failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for failure in graph.get("transition_failures", []) or []:
        if isinstance(failure, Mapping):
            blocking_failures.append(
                _failure(
                    str(failure.get("reason", "transition_resolver_failure")),
                    surface_graph_id=failure.get("surface_graph_id"),
                    edge_treatment_site_id=failure.get("edge_treatment_site_id"),
                    edge_family=failure.get("edge_family"),
                    transition_policy_id=failure.get("transition_policy_id"),
                    requested_radius_mm=failure.get("requested_radius_mm"),
                    suggested_max_radius_mm=failure.get("suggested_max_radius_mm"),
                )
            )
        else:
            blocking_failures.append(_failure("transition_resolver_failure", detail=str(failure)))

    _validate_root_transition_topology(
        transition_surfaces,
        policies,
        blocking_failures,
    )
    for surface in transition_surfaces:
        _validate_transition_surface(
            surface,
            policies,
            surfaces_by_id,
            sites_by_transition_surface.get(str(surface.get("id")), []),
            blocking_failures,
        )

    _validate_v091_topology_and_mesh(graph, blocking_failures)

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
    ]:
        checks.append(
            {
                "check_id": check_id,
                "status": FAIL if any(failure["reason"] == reason for failure in blocking_failures) else PASS,
            }
        )

    status = FAIL if blocking_failures else PASS
    unsupported_claims = _unsupported_claims(graph)
    summary = _transition_validation_summary(transition_surfaces, blocking_failures, graph)
    return {
        "geometry_validation_status": status,
        "kernel_capability_matrix_id": capability_matrix_id,
        "capability_claim_level": "review_grade_validated" if status == PASS else "blocked_review_grade",
        "unsupported_claims": unsupported_claims,
        "parameters_observed": parameters or {},
        "facets_observed": facets or {},
        "checks": checks,
        "blocking_failures": blocking_failures,
        "transition_validation_summary": summary,
    }


def geometry_validation_blocks_export(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    return bool(report.get("blocking_failures")) or report.get("geometry_validation_status") == FAIL


def _is_transition_surface(surface: Mapping[str, Any]) -> bool:
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
    transition_surfaces: list[Mapping[str, Any]],
    policies: dict[str, Any],
    blocking_failures: list[dict[str, Any]],
) -> None:
    active_root_policy = _policy_enabled(policies.get("blade_root_to_hub.default", {"enabled": True}))
    if not active_root_policy:
        return

    root_surface_ids = {str(surface.get("id")) for surface in transition_surfaces}
    for surface_id in sorted(root_surface_ids):
        if ROOT_LEGACY_RE.match(surface_id):
            blocking_failures.append(
                _failure(
                    "legacy_single_root_transition_surface",
                    surface_graph_id=surface_id,
                    edge_family="blade_root_to_hub",
                )
            )

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
        blocking_failures.append(
            _failure(
                "disabled_policy_has_transition_surface",
                surface_graph_id=surface_id,
                transition_policy_id=policy_id,
                edge_family=surface.get("edge_family"),
            )
        )
        return

    if policy is not None:
        policy_radius = _float_or_none(policy.get("radius_mm"))
        surface_radius = _float_or_none(surface.get("radius_mm"))
        if policy_radius is not None and surface_radius is not None and abs(policy_radius - surface_radius) > 1.0e-6:
            blocking_failures.append(
                _failure(
                    "transition_radius_not_synchronized",
                    surface_graph_id=surface_id,
                    transition_policy_id=policy_id,
                    requested_radius_mm=policy_radius,
                    surface_radius_mm=surface_radius,
                )
            )

    treatment = str(surface.get("treatment") or "")
    quality = surface.get("transition_quality") if isinstance(surface.get("transition_quality"), Mapping) else {}
    if treatment == "fillet":
        _validate_fillet_quality(surface, quality, blocking_failures)
    elif treatment == "chamfer":
        _validate_chamfer_quality(surface, quality, blocking_failures)

    for site in sites:
        _validate_adjacent_trim(surface, site, surfaces_by_id, blocking_failures)


def _validate_fillet_quality(
    surface: Mapping[str, Any],
    quality: Mapping[str, Any],
    blocking_failures: list[dict[str, Any]],
) -> None:
    radius = _float_or_none(surface.get("radius_mm")) or 0.0
    min_bulge = max(0.05, 0.05 * radius)
    convex_status = quality.get("convexity_status")
    signed_bulge = _float_or_none(quality.get("fillet_convex_signed_bulge_mm"))
    if convex_status == FAIL or (signed_bulge is not None and signed_bulge < min_bulge):
        blocking_failures.append(
            _failure(
                "fillet_convexity_failed",
                surface_graph_id=surface.get("id"),
                edge_family=surface.get("edge_family"),
                transition_policy_id=surface.get("transition_policy_id"),
                signed_bulge_mm=signed_bulge,
                minimum_signed_bulge_mm=min_bulge,
            )
        )


def _validate_chamfer_quality(
    surface: Mapping[str, Any],
    quality: Mapping[str, Any],
    blocking_failures: list[dict[str, Any]],
) -> None:
    linearity = _float_or_none(quality.get("section_linearity_max_error_mm"))
    if linearity is not None and linearity > 1.0e-4:
        blocking_failures.append(
            _failure(
                "chamfer_linearity_failed",
                surface_graph_id=surface.get("id"),
                edge_family=surface.get("edge_family"),
                transition_policy_id=surface.get("transition_policy_id"),
                section_linearity_max_error_mm=linearity,
            )
        )


def _validate_adjacent_trim(
    surface: Mapping[str, Any],
    site: Mapping[str, Any],
    surfaces_by_id: dict[str, Mapping[str, Any]],
    blocking_failures: list[dict[str, Any]],
) -> None:
    site_id = str(site.get("edge_treatment_site_id") or surface.get("edge_treatment_site_id") or "")
    for adjacent_id in site.get("adjacent_surface_ids", []) or []:
        adjacent = surfaces_by_id.get(str(adjacent_id))
        if adjacent is None:
            blocking_failures.append(
                _failure(
                    "adjacent_surface_missing",
                    surface_graph_id=surface.get("id"),
                    edge_treatment_site_id=site_id,
                    adjacent_surface_id=adjacent_id,
                )
            )
            continue
        if not _surface_has_trim_for_site(adjacent, site_id):
            blocking_failures.append(
                _failure(
                    "adjacent_surface_not_trimmed",
                    surface_graph_id=surface.get("id"),
                    edge_treatment_site_id=site_id,
                    adjacent_surface_id=adjacent_id,
                )
            )


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


def _validate_v091_topology_and_mesh(
    graph: Mapping[str, Any],
    blocking_failures: list[dict[str, Any]],
) -> None:
    if graph.get("transition_geometry_status") != V091_TRANSITION_GEOMETRY_STATUS:
        return

    topology_report = graph.get("transition_topology_report")
    if not isinstance(topology_report, Mapping):
        blocking_failures.append(_failure("missing_transition_topology_report"))
        topology_report = {}

    corner_patch_count = _int_or_zero(topology_report.get("corner_patch_count"))
    required_corner_patch_count = _int_or_zero(topology_report.get("required_corner_patch_count"))
    if corner_patch_count < required_corner_patch_count:
        blocking_failures.append(
            _failure(
                "missing_required_corner_patches",
                corner_patch_count=corner_patch_count,
                required_corner_patch_count=required_corner_patch_count,
            )
        )

    boundary_failures = topology_report.get("boundary_node_identity_failures")
    if boundary_failures:
        blocking_failures.append(
            _failure(
                "boundary_node_identity_failed",
                boundary_node_identity_failure_count=len(boundary_failures)
                if isinstance(boundary_failures, list)
                else 1,
            )
        )

    mesh_report = graph.get("mesh_manifoldness_report")
    if not isinstance(mesh_report, Mapping):
        blocking_failures.append(
            _failure(
                "missing_mesh_manifoldness_report",
                mesh_manifoldness_report_error=graph.get("mesh_manifoldness_report_error"),
            )
        )
        return

    _append_positive_count_failure(
        mesh_report,
        blocking_failures,
        "free_edge_count",
        "mesh_has_free_edges",
    )
    _append_positive_count_failure(
        mesh_report,
        blocking_failures,
        "nonmanifold_edge_count",
        "mesh_has_nonmanifold_edges",
    )
    _append_positive_count_failure(
        mesh_report,
        blocking_failures,
        "zero_area_face_count",
        "mesh_has_zero_area_faces",
    )
    _append_positive_count_failure(
        mesh_report,
        blocking_failures,
        "duplicate_face_count",
        "mesh_has_duplicate_faces",
    )
    if "skipped_triangle_count" not in mesh_report:
        blocking_failures.append(_failure("missing_mesh_skipped_triangle_accounting"))
    else:
        _append_positive_count_failure(
            mesh_report,
            blocking_failures,
            "skipped_triangle_count",
            "mesh_has_skipped_triangles",
        )


def _append_positive_count_failure(
    report: Mapping[str, Any],
    blocking_failures: list[dict[str, Any]],
    count_key: str,
    reason: str,
) -> None:
    count = _int_or_zero(report.get(count_key))
    if count > 0:
        blocking_failures.append(_failure(reason, **{count_key: count}))


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
    return [
        {
            "reason": "synthetic_mesh_closure_review_caveat",
            "blocking": False,
            "source_patch_free_edge_count": source_patch_free_edge_count,
            "synthetic_closure_triangle_count": synthetic_closure_triangle_count,
            "closure_policy": mesh_report.get("closure_policy"),
            "detail": (
                "source transition patches had free edges before synthetic review closure; "
                "final mesh manifoldness gates are evaluated after closure"
            ),
        }
    ]


def _transition_validation_summary(
    transition_surfaces: list[Mapping[str, Any]],
    blocking_failures: list[dict[str, Any]],
    graph: Mapping[str, Any],
) -> dict[str, Any]:
    by_family = Counter(str(surface.get("edge_family") or "unspecified") for surface in transition_surfaces)
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
                    "required_corner_patch_count": _int_or_zero(
                        topology_report.get("required_corner_patch_count")
                    ),
                    "boundary_node_identity_failure_count": len(
                        topology_report.get("boundary_node_identity_failures") or []
                    ),
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
                    "source_patch_free_edge_count": _int_or_zero(
                        mesh_report.get("source_patch_free_edge_count")
                    ),
                    "synthetic_closure_triangle_count": _int_or_zero(
                        mesh_report.get("synthetic_closure_triangle_count")
                    ),
                }
            )
    return summary


def _policy_enabled(policy: Mapping[str, Any]) -> bool:
    return policy.get("enabled", True) is not False and policy.get("treatment") != "none"


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
