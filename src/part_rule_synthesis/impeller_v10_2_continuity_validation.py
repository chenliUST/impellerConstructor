from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
_V10_2_PATCH_VERSION = "1.0.2"


def validate_v10_2_continuous_blade_attachment(surface_graph: dict[str, Any]) -> dict[str, Any]:
    if surface_graph.get("geometry_patch_version") != _V10_2_PATCH_VERSION:
        return {"status": SKIP, "blocking_failures": [], "summary": {}}

    failures: list[dict[str, Any]] = []
    surfaces = [
        surface
        for surface in surface_graph.get("surfaces", [])
        if isinstance(surface, Mapping)
    ]

    _append_graph_level_transition_failures(surface_graph, failures)
    root_count = 0
    closed_tip_count = 0
    transition_surface_count = 0
    for surface in surfaces:
        role = str(surface.get("role") or "")
        if _is_root_attachment(surface):
            root_count += 1
            _append_root_failures(surface, failures)
        if role == "tip_to_shroud_attachment_surface":
            closed_tip_count += 1
            _append_tip_failures(surface, failures)
        if _is_v10_2_transition_surface(surface):
            transition_surface_count += 1
            transition_quality = (
                surface.get("transition_quality") if isinstance(surface.get("transition_quality"), Mapping) else {}
            )
            attachment_quality = (
                surface.get("attachment_quality") if isinstance(surface.get("attachment_quality"), Mapping) else {}
            )
            foldover_count = _first_present_count(
                surface.get("foldover_count"),
                attachment_quality.get("foldover_count"),
            )
            foldover_statuses = {
                str(surface.get("foldover_status") or ""),
                str(transition_quality.get("foldover_status") or ""),
                str(attachment_quality.get("foldover_status") or ""),
            }
            if FAIL in foldover_statuses or _positive_count(foldover_count):
                failures.append(
                    _failure(
                        "v1_0_2_transition_foldover",
                        surface_graph_id=surface.get("id"),
                        foldover_count=foldover_count,
                    )
                )

    status = PASS if not failures else FAIL
    return {
        "status": status,
        "blocking_failures": failures,
        "summary": {
            "continuous_blade_attachment_status": status,
            "blocking_failure_count": len(failures),
            "root_attachment_surface_count": root_count,
            "closed_tip_attachment_surface_count": closed_tip_count,
            "transition_surface_count": transition_surface_count,
        },
    }


def _append_root_failures(surface: Mapping[str, Any], failures: list[dict[str, Any]]) -> None:
    _append_attachment_failures(
        surface,
        failures,
        inner_loop_mismatch_reason="v1_0_2_root_inner_loop_mismatch",
        support_domain_violation_reason="v1_0_2_root_support_domain_violation",
    )


def _append_tip_failures(surface: Mapping[str, Any], failures: list[dict[str, Any]]) -> None:
    _append_attachment_failures(
        surface,
        failures,
        inner_loop_mismatch_reason="v1_0_2_tip_inner_loop_mismatch",
        support_domain_violation_reason="v1_0_2_tip_support_domain_violation",
    )


def _append_attachment_failures(
    surface: Mapping[str, Any],
    failures: list[dict[str, Any]],
    *,
    inner_loop_mismatch_reason: str,
    support_domain_violation_reason: str,
) -> None:
    edge_samples = surface.get("edge_samples") if isinstance(surface.get("edge_samples"), Mapping) else {}
    inner_loop = edge_samples.get("blade_inner_loop") if isinstance(edge_samples, Mapping) else None
    uv_inner_loop = _column(surface.get("uv_grid"), -1)
    if not _points_equal(inner_loop, uv_inner_loop):
        failures.append(_failure(inner_loop_mismatch_reason, surface_graph_id=surface.get("id")))

    attachment_quality = (
        surface.get("attachment_quality") if isinstance(surface.get("attachment_quality"), Mapping) else {}
    )
    if attachment_quality.get("status") == FAIL:
        failures.append(
            _failure(
                str(attachment_quality.get("reason") or "v1_0_2_attachment_quality_failed"),
                surface_graph_id=surface.get("id"),
            )
        )
    if _positive_count(attachment_quality.get("support_domain_violation_count")):
        failures.append(
            _failure(
                support_domain_violation_reason,
                surface_graph_id=surface.get("id"),
                support_domain_violation_count=attachment_quality.get("support_domain_violation_count"),
            )
        )
    if _positive_count(attachment_quality.get("foldover_count")):
        failures.append(
            _failure(
                "v1_0_2_transition_foldover",
                surface_graph_id=surface.get("id"),
                foldover_count=attachment_quality.get("foldover_count"),
            )
        )


def _append_graph_level_transition_failures(
    surface_graph: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    for failure in surface_graph.get("v1_0_2_transition_failures", []) or []:
        if isinstance(failure, Mapping):
            failures.append(
                _failure(
                    str(failure.get("reason", "v1_0_2_transition_failure")),
                    surface_graph_id=failure.get("surface_id") or failure.get("surface_graph_id"),
                    blade_index=failure.get("blade_index"),
                    stage=failure.get("stage"),
                )
            )
        else:
            failures.append(_failure("v1_0_2_transition_failure", detail=str(failure)))


def _is_root_attachment(surface: Mapping[str, Any]) -> bool:
    return (
        surface.get("role") == "root_pedestal_ring_surface"
        or surface.get("root_topology") == "support_domain_annular_attachment_boss"
    )


def _is_v10_2_transition_surface(surface: Mapping[str, Any]) -> bool:
    return bool(
        surface.get("transition_quality")
        or surface.get("face_family") in {"blade_leading_edge", "blade_trailing_edge", "blade_tip"}
        or surface.get("role") in {
            "leading_edge_surface",
            "trailing_edge_surface",
            "tip_surface",
            "tip_to_shroud_attachment_surface",
            "root_pedestal_ring_surface",
        }
    )


def _column(value: Any, index: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    column = []
    for row in value:
        if not isinstance(row, list) or not row:
            return []
        try:
            column.append(row[index])
        except IndexError:
            return []
    return column


def _points_equal(first: Any, second: Any) -> bool:
    if not isinstance(first, list) or not isinstance(second, list):
        return False
    if len(first) != len(second):
        return False
    return all(_point_equal(a, b) for a, b in zip(first, second))


def _point_equal(first: Any, second: Any) -> bool:
    if not isinstance(first, list) or not isinstance(second, list):
        return first == second
    if len(first) != len(second):
        return False
    for left, right in zip(first, second):
        try:
            if abs(float(left) - float(right)) > 1.0e-9:
                return False
        except (TypeError, ValueError):
            if left != right:
                return False
    return True


def _positive_count(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _first_present_count(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": FAIL,
        "blocking": True,
        "reason": reason,
        **{key: value for key, value in metadata.items() if value is not None},
    }
