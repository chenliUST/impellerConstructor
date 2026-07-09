from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PASS = "PASS"
VALIDATION_STAGE = "v1_1_validation"
_SOURCE_KERNEL = "v1_1_blade_to_blade_surface_family_kernel"
_REQUIRED_ROLES = {
    "blade_pressure",
    "blade_suction",
    "blade_leading_edge",
    "blade_trailing_edge",
    "root_to_hub_attachment",
}
_TIP_ROLES = {"open_tip_dome", "closed_shroud_attachment"}


def validate_v11_surface_graph(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    if surface_graph.get("geometry_patch_version") not in {"1.1.0", "1.1.1", "1.1.2"}:
        return []

    failures: list[dict[str, Any]] = []
    surfaces = [surface for surface in surface_graph.get("surfaces", []) if isinstance(surface, Mapping)]

    if surface_graph.get("geometry_patch_version") == "1.1.2":
        canonical = surface_graph.get("canonical_nurbs_parameterization")
        if not isinstance(canonical, dict):
            failures.append(_failure("v1_1_2_canonical_payload_missing"))
        elif canonical.get("canonical_payload_version") != "1.1.2":
            failures.append(_failure("v1_1_2_canonical_payload_missing"))

    roles = {str(surface.get("role") or "") for surface in surfaces}
    if not _REQUIRED_ROLES.issubset(roles):
        failures.append(_failure("v1_1_surface_boundary_not_shared"))
    if not roles.intersection(_TIP_ROLES):
        failures.append(_failure("v1_1_tip_surface_missing"))

    for surface in surfaces:
        surface_id = surface.get("id")

        role = str(surface.get("role") or "")
        if _is_manufactured_surface(surface):
            if not _has_minimum_uv_grid(surface.get("uv_grid")):
                failures.append(_failure("v1_1_surface_loft_foldover", surface_graph_id=surface_id))
            wireframe = surface.get("wireframe")
            if not isinstance(wireframe, Mapping) or wireframe.get("enabled") is not True:
                failures.append(_failure("v1_1_surface_boundary_not_shared", surface_graph_id=surface_id))
        if role == "root_to_hub_attachment":
            failures.extend(
                _validate_root_quality(surface.get("v1_1_root_quality"), surface_graph_id=surface_id)
            )
        if role in _TIP_ROLES:
            failures.extend(
                _validate_tip_quality(surface.get("v1_1_tip_quality"), surface_graph_id=surface_id)
            )
        if "v1_1_span_domain_quality" in surface:
            failures.extend(
                _validate_span_domain_quality(surface.get("v1_1_span_domain_quality"), surface_graph_id=surface_id)
            )

    return failures


def _has_minimum_uv_grid(uv_grid: Any) -> bool:
    if not isinstance(uv_grid, list) or len(uv_grid) < 2:
        return False
    return all(isinstance(row, list) and len(row) >= 2 for row in uv_grid)


def _is_manufactured_surface(surface: Mapping[str, Any]) -> bool:
    if surface.get("source_kernel") != _SOURCE_KERNEL:
        return False
    role = str(surface.get("role") or "")
    if role in {"open_tip_reference", "hub_support", "shroud_support"}:
        return False
    surface_flags = surface.get("surface_flags") if isinstance(surface.get("surface_flags"), Mapping) else {}
    if surface_flags.get("reference_only") is True:
        return False
    display = surface.get("display") if isinstance(surface.get("display"), Mapping) else {}
    if display.get("reference_only") is True:
        return False
    return True


def _validate_root_quality(payload: Any, *, surface_graph_id: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [_failure("v1_1_root_quality_missing", surface_graph_id=surface_graph_id)]
    if payload.get("status") != PASS:
        return [
            _failure(
                str(payload.get("reason") or "v1_1_root_material_side_failed"),
                surface_graph_id=surface_graph_id,
            )
        ]
    if payload.get("material_side_status") != PASS:
        return [_failure("v1_1_root_material_side_failed", surface_graph_id=surface_graph_id)]
    return []


def _validate_tip_quality(payload: Any, *, surface_graph_id: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [_failure("v1_1_tip_quality_missing", surface_graph_id=surface_graph_id)]
    if payload.get("status") != PASS:
        return [
            _failure(
                str(payload.get("reason") or "v1_1_tip_continuity_failed"),
                surface_graph_id=surface_graph_id,
            )
        ]
    try:
        tip_area_ratio = float(payload.get("tip_area_ratio", 1.0))
    except (TypeError, ValueError):
        tip_area_ratio = 1.0
    if tip_area_ratio > 1.15:
        return [_failure("v1_1_tip_domain_exceeded", surface_graph_id=surface_graph_id)]
    return []


def _validate_span_domain_quality(payload: Any, *, surface_graph_id: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [_failure("v1_1_blade_loop_material_domain_failed", surface_graph_id=surface_graph_id)]
    if payload.get("status") != PASS or payload.get("material_domain_status") != PASS:
        return [_failure("v1_1_blade_loop_material_domain_failed", surface_graph_id=surface_graph_id)]
    return []


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "blocking": True,
        "stage": VALIDATION_STAGE,
        "reason": reason,
        **{key: value for key, value in metadata.items() if value is not None},
    }
