from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_surface

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
        else:
            failures.extend(_validate_v112_canonical_contract(surface_graph, canonical))

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


def _validate_v112_canonical_contract(
    surface_graph: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    loop_family = surface_graph.get("blade_to_blade_loop_family")
    loop_family = loop_family if isinstance(loop_family, Mapping) else {}
    active_metrics = loop_family.get("active_span_policy_metrics")
    if isinstance(active_metrics, Mapping) and active_metrics.get("offset_feasibility_status") != PASS:
        failures.append(_failure("v1_1_2_active_span_offset_infeasible"))

    for field_name in ("blade_skeleton_field", "thickness_field"):
        if not _is_evaluable_canonical_field(
            canonical.get(field_name),
            require_positive_thickness=field_name == "thickness_field",
        ):
            failures.append(_failure("v1_1_2_invalid_canonical_nurbs_field", canonical_field=field_name))

    population = canonical.get("blade_population")
    if isinstance(population, Mapping):
        canonical_blade_count = _safe_int(population.get("main_blade_count")) + _safe_int(
            population.get("splitter_blade_count")
        )
        actual_blade_count = _actual_blade_count(surface_graph, loop_family)
        if canonical_blade_count != actual_blade_count:
            failures.append(
                _failure(
                    "v1_1_2_population_mismatch",
                    expected_count=canonical_blade_count,
                    observed_count=actual_blade_count,
                )
            )

    if not _caps_have_resolved_sagitta(loop_family):
        failures.append(_failure("v1_1_2_cap_sagitta_unresolved"))
    return failures


def _is_evaluable_canonical_field(payload: Any, *, require_positive_thickness: bool) -> bool:
    if not isinstance(payload, Mapping) or payload.get("kind") != "nurbs_surface":
        return False
    try:
        samples = [
            evaluate_nurbs_surface(dict(payload), u, v)
            for u, v in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0))
        ]
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    for sample in samples:
        if not isinstance(sample, list) or len(sample) < 3:
            return False
        try:
            values = [float(value) for value in sample[:3]]
        except (TypeError, ValueError):
            return False
        if not all(math.isfinite(value) for value in values):
            return False
        if require_positive_thickness and values[2] <= 0.0:
            return False
    return True


def _actual_blade_count(
    surface_graph: Mapping[str, Any],
    loop_family: Mapping[str, Any],
) -> int:
    blades = loop_family.get("blades")
    if isinstance(blades, list):
        return len(blades)
    return _safe_int(surface_graph.get("blade_count"))


def _caps_have_resolved_sagitta(loop_family: Mapping[str, Any]) -> bool:
    blades = loop_family.get("blades")
    if not isinstance(blades, list) or not blades:
        return False
    for blade in blades:
        if not isinstance(blade, Mapping):
            return False
        loops = blade.get("loops")
        if not isinstance(loops, list) or not loops:
            return False
        for loop in loops:
            if not isinstance(loop, Mapping):
                return False
            segments = loop.get("segments")
            if not isinstance(segments, Mapping):
                return False
            for segment_name in ("leading_edge", "trailing_edge"):
                segment = segments.get(segment_name)
                if not isinstance(segment, Mapping):
                    return False
                curve = segment.get("canonical_curve")
                if not isinstance(curve, Mapping) or not _positive_finite(curve.get("resolved_sagitta_mm")):
                    return False
    return True


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _positive_finite(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0.0


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
