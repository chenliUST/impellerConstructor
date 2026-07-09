from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PASS = "PASS"
PATCH_VERSION = "1.0.4"
VALIDATION_STAGE = "v1_0_4_validation"


def validate_v10_4_surface_graph(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    if surface_graph.get("geometry_patch_version") != PATCH_VERSION:
        return []

    surfaces = [surface for surface in surface_graph.get("surfaces", []) if isinstance(surface, Mapping)]
    failures: list[dict[str, Any]] = []

    root_surfaces = [
        surface
        for surface in surfaces
        if str(surface.get("id") or "").endswith("root_annular_surface")
    ]
    failures.extend(
        _validate_surface_qualities(
            surfaces=root_surfaces,
            quality_key="v1_0_4_root_quality",
            missing_reason="v1_0_4_root_quality_missing",
        )
    )

    tip_surfaces = [surface for surface in surfaces if surface.get("role") == "open_tip_dome"]
    failures.extend(
        _validate_surface_qualities(
            surfaces=tip_surfaces,
            quality_key="v1_0_4_tip_quality",
            missing_reason="v1_0_4_tip_quality_missing",
        )
    )

    failures.extend(
        _validate_graph_quality(
            payload=surface_graph.get("v1_0_4_hub_quality"),
            missing_reason="v1_0_4_hub_quality_missing",
        )
    )
    failures.extend(
        _validate_graph_quality(
            payload=surface_graph.get("v1_0_4_continuity_summary"),
            missing_reason="v1_0_4_g2_continuity_failed",
        )
    )
    failures.extend(
        _validate_graph_quality(
            payload=surface_graph.get("v1_0_4_angle_quality"),
            missing_reason="v1_0_4_blade_hub_angle_out_of_range",
        )
    )
    return failures


def _validate_surface_qualities(
    *,
    surfaces: list[Mapping[str, Any]],
    quality_key: str,
    missing_reason: str,
) -> list[dict[str, Any]]:
    if not surfaces:
        return [_failure(missing_reason)]

    failures: list[dict[str, Any]] = []
    for surface in surfaces:
        quality = surface.get(quality_key)
        if not isinstance(quality, Mapping):
            failures.append(_failure(missing_reason, surface_graph_id=surface.get("id")))
            continue
        if quality.get("status") != PASS:
            failures.append(
                _failure(
                    str(quality.get("reason") or missing_reason),
                    surface_graph_id=surface.get("id"),
                )
            )
    return failures


def _validate_graph_quality(
    *,
    payload: Any,
    missing_reason: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [_failure(missing_reason)]
    if payload.get("status") == PASS:
        return []
    return [_failure(str(payload.get("reason") or missing_reason))]


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "blocking": True,
        "stage": VALIDATION_STAGE,
        "reason": reason,
        **{key: value for key, value in metadata.items() if value is not None},
    }
