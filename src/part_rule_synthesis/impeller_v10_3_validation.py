from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from typing import Any


V10_3_TRANSITION_GEOMETRY_STATUS = "topology_first_section_loop_blade_root_blend_surface_graph"


def validate_v10_3_surface_graph(surface_graph: dict[str, Any]) -> dict[str, Any]:
    if surface_graph.get("geometry_patch_version") != "1.0.3":
        return {"status": "SKIP", "failure_count": 0, "failures": [], "summary": {}}

    surfaces = [surface for surface in surface_graph.get("surfaces", []) if isinstance(surface, Mapping)]
    failures: list[dict[str, Any]] = []
    if not surfaces:
        failures.append({"reason": "v1_0_3_surface_graph_empty"})
        return _report(failures, surfaces)

    counts = Counter(str(surface.get("face_family") or "") for surface in surfaces)
    for face_family, expected_count, reason in [
        ("blade_pressure", 8, "v1_0_3_pressure_surfaces_missing"),
        ("blade_suction", 8, "v1_0_3_suction_surfaces_missing"),
        ("blade_leading_edge", 8, "v1_0_3_leading_edge_surfaces_missing"),
        ("blade_trailing_edge", 8, "v1_0_3_trailing_edge_surfaces_missing"),
    ]:
        if counts[face_family] < expected_count:
            failures.append(
                {
                    "reason": reason,
                    "expected_count": expected_count,
                    "observed_count": counts[face_family],
                }
            )

    root_aggregates = [
        surface
        for surface in surfaces
        if surface.get("face_family") == "blade_root"
        and surface.get("display", {}).get("aggregate_surface") is True
    ]
    root_components = _visible_root_components(surfaces)
    if len(root_aggregates) < 8:
        failures.append(
            {
                "reason": "v1_0_3_root_aggregates_missing",
                "expected_count": 8,
                "observed_count": len(root_aggregates),
            }
        )
    for surface in root_aggregates:
        if surface.get("display", {}).get("visible_by_default") is not False:
            failures.append(
                {
                    "surface_id": surface.get("id"),
                    "reason": "v1_0_3_root_aggregate_visibility_failed",
                }
            )
    if len(root_components) < 32:
        failures.append(
            {
                "reason": "v1_0_3_root_components_missing",
                "expected_count": 32,
                "observed_count": len(root_components),
            }
        )
    tip_domes = _tip_domes(surfaces)
    if len(tip_domes) < 8:
        failures.append(
            {
                "reason": "v1_0_3_tip_dome_missing",
                "expected_count": 8,
                "observed_count": len(tip_domes),
            }
        )

    for surface in root_components:
        _validate_root_component(surface, failures)
    for surface in tip_domes:
        _validate_tip_dome(surface, failures)
    _validate_topology_graph(surface_graph.get("topology_graph"), failures)

    return _report(failures, surfaces)


def _visible_root_components(surfaces: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        surface
        for surface in surfaces
        if surface.get("face_family") == "blade_root"
        and surface.get("display", {}).get("inspection_class") == "root_to_hub_blend"
        and surface.get("display", {}).get("aggregate_surface") is not True
        and surface.get("display", {}).get("visible_by_default") is not False
    ]


def _tip_domes(surfaces: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        surface
        for surface in surfaces
        if surface.get("face_family") == "blade_tip"
        and surface.get("role") == "open_tip_dome"
        and surface.get("display", {}).get("visible_by_default", True) is not False
    ]


def _validate_root_component(surface: Mapping[str, Any], failures: list[dict[str, Any]]) -> None:
    surface_id = surface.get("id")
    transition_quality = _mapping(surface.get("transition_quality"))
    root_quality = _mapping(surface.get("root_blend_quality"))
    for key in ["foldover_count", "max_tangent_flip_deg", "max_normal_flip_deg"]:
        if key not in transition_quality:
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "v1_0_3_root_quality_metric_missing",
                    "metric": key,
                }
            )
    if "min_signed_height_to_hub_mm" not in root_quality:
        failures.append(
            {
                "surface_id": surface_id,
                "reason": "v1_0_3_root_quality_metric_missing",
                "metric": "min_signed_height_to_hub_mm",
            }
        )
    if surface.get("wireframe", {}).get("enabled") is not True:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_wireframe_missing"})
    if _int_value(surface.get("mesh", {}).get("quad_count")) <= 0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_mesh_missing"})
    if _int_value(transition_quality.get("foldover_count")) != 0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_segment_foldover"})
    if _float_value(transition_quality.get("max_tangent_flip_deg"), 0.0) >= 45.0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_tangent_flip_failed"})
    if _float_value(transition_quality.get("max_normal_flip_deg"), 0.0) >= 45.0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_normal_flip_failed"})
    if _float_value(root_quality.get("min_signed_height_to_hub_mm"), 0.0) < -1.0e-6:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_root_signed_height_failed"})


def _validate_tip_dome(surface: Mapping[str, Any], failures: list[dict[str, Any]]) -> None:
    surface_id = surface.get("id")
    transition_quality = _mapping(surface.get("transition_quality"))
    if surface.get("wireframe", {}).get("enabled") is not True:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_tip_dome_wireframe_missing"})
    if _int_value(surface.get("mesh", {}).get("quad_count")) <= 0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_tip_dome_mesh_missing"})
    if _int_value(transition_quality.get("foldover_count")) != 0:
        failures.append({"surface_id": surface_id, "reason": "v1_0_3_tip_dome_foldover"})


def _validate_topology_graph(topology_graph: Any, failures: list[dict[str, Any]]) -> None:
    if not isinstance(topology_graph, Mapping):
        failures.append({"reason": "v1_0_3_topology_graph_missing"})
        return
    if topology_graph.get("topology_status") != "PASS":
        failures.append({"reason": "v1_0_3_topology_graph_failed"})
    if _int_value(topology_graph.get("shared_edge_count")) <= 0:
        failures.append({"reason": "v1_0_3_shared_edges_missing"})
    max_gap = _float_value(topology_graph.get("max_shared_edge_gap_mm"), math.inf)
    if max_gap > 1.0e-9:
        failures.append(
            {
                "reason": "v1_0_3_shared_edge_gap_exceeds_tolerance",
                "max_shared_edge_gap_mm": max_gap,
                "tolerance_mm": 1.0e-9,
            }
        )


def _report(failures: list[dict[str, Any]], surfaces: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "summary": {
            "surface_count": len(surfaces),
            "visible_root_component_count": len(_visible_root_components(surfaces)),
            "tip_dome_count": len(_tip_domes(surfaces)),
        },
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result
