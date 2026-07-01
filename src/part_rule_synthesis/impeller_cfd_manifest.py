from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_graph_contract import estimate_surface_area, wetted_surfaces


CFD_ROLE_TO_GROUP = {
    "blade_pressure": "blade_pressure_wall",
    "blade_suction": "blade_suction_wall",
    "leading_edge_transition": "leading_edge_wall",
    "trailing_edge_transition": "trailing_edge_wall",
    "root_transition": "root_fillet_wall",
    "tip_transition": "tip_fillet_wall",
    "hub_wall": "hub_wall",
    "tip_or_shroud_wall": "tip_or_shroud_wall",
    "inlet_patch": "inlet_patch",
    "outlet_patch": "outlet_patch",
}

SURFACE_SOURCE_ALIASES = {
    "pressure_surface": {"blade_pressure"},
    "suction_surface": {"blade_suction"},
    "hub_support_surface": {"hub_support_surface", "hub_wall"},
    "blade_tip_support_surface": {
        "blade_tip_support_surface",
        "front_shroud_inner_surface",
        "shroud_surface",
        "tip_or_shroud_wall",
    },
}


def build_cfd_full_360_manifest(
    surface_graph: dict[str, Any],
    simulation_view: dict[str, Any],
    blade_count: int,
) -> dict[str, Any]:
    suppressed = set(simulation_view.get("feature_suppression", {}).get("suppressed_features", []))
    surfaces = wetted_surfaces(surface_graph.get("surfaces", []), suppressed_features=suppressed)
    boundary_curves = [
        curve
        for curve in surface_graph.get("named_boundary_curves", [])
        if curve.get("feature_id") not in suppressed
    ]
    patch_group_sources = simulation_view.get("patch_group_sources", {})
    patch_groups: dict[str, dict[str, Any]] = {
        group: {"type": _patch_group_type(group), "instances": []}
        for group in simulation_view.get("required_patch_groups", [])
    }
    topology = _infer_topology(surfaces)
    contributions: list[dict[str, Any]] = []
    assigned_surface_ids: set[str] = set()
    seen_contributions: set[tuple[str, str, str]] = set()

    for group, source_spec in patch_group_sources.items():
        patch_groups.setdefault(group, {"type": _patch_group_type(group), "instances": []})
        for source_token in _source_tokens(source_spec, topology):
            for contribution in _resolve_source_token(group, source_token, surfaces, boundary_curves):
                key = (contribution["group"], contribution["source_type"], contribution["source_id"])
                if key in seen_contributions:
                    continue
                seen_contributions.add(key)
                contributions.append(contribution)
                if contribution["source_type"] == "surface":
                    assigned_surface_ids.add(contribution["source_id"])

    unmapped_instances = []
    for surface in surfaces:
        surface_id = surface["id"]
        if surface_id in assigned_surface_ids:
            continue
        group = CFD_ROLE_TO_GROUP.get(surface.get("cfd_role"))
        if group:
            patch_groups.setdefault(group, {"type": _patch_group_type(group), "instances": []})
            key = (group, "surface", surface_id)
            if key not in seen_contributions:
                seen_contributions.add(key)
                contributions.append(_surface_contribution(group, surface.get("cfd_role"), surface))
                assigned_surface_ids.add(surface_id)
            continue
        unmapped_instances.append(
            {
                "surface_graph_id": surface_id,
                "cfd_role": surface.get("cfd_role"),
                "surface_role": surface.get("role"),
            }
        )

    patch_instances: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    for contribution in contributions:
        source_id = contribution["source_id"]
        source_counts[source_id] = source_counts.get(source_id, 0) + 1

    for contribution in sorted(
        contributions,
        key=lambda item: (item["group"], item["source_type"], item["source_id"], item["source_token"]),
    ):
        group = contribution["group"]
        source_id = contribution["source_id"]
        instance_id = f"{group}:{source_id}" if source_counts[source_id] > 1 else source_id
        patch_groups.setdefault(group, {"type": _patch_group_type(group), "instances": []})
        patch_groups[group]["instances"].append(instance_id)
        patch_instances[instance_id] = _patch_instance_metadata(contribution)

    for group in patch_groups.values():
        group["instances"].sort()
    failures = [
        f"missing_patch_group_instances:{group_id}"
        for group_id, group in patch_groups.items()
        if not group["instances"]
    ]
    failures.extend(
        f"unmapped_cfd_role:{item['cfd_role']}:{item['surface_graph_id']}"
        for item in unmapped_instances
    )
    return {
        "domain_kind": "full_360_wetted_surface",
        "status": "research_grade_executable",
        "blade_count": int(blade_count),
        "feature_suppression": simulation_view.get("feature_suppression", {}),
        "patch_groups": patch_groups,
        "patch_instances": patch_instances,
        "mesh_hints": simulation_view.get("mesh_hints", {}),
        "validity": {
            "status": "FAIL" if failures else "PASS",
            "failures": failures,
            "patch_group_count": len(patch_groups),
            "patch_instance_count": len(patch_instances),
            "unmapped_instances": unmapped_instances,
        },
    }


def _patch_group_type(group: str) -> str:
    if group in {"inlet_patch", "outlet_patch"}:
        return group.replace("_patch", "")
    return "wall"


def _infer_topology(surfaces: list[dict[str, Any]]) -> str:
    for surface in surfaces:
        if surface.get("id") == "shroud_surface":
            return "closed"
        if surface.get("ontology_id") == "blade_tip_support_surface" and surface.get("material") is True:
            return "closed"
    return "open"


def _source_tokens(source_spec: Any, topology: str) -> list[str]:
    if isinstance(source_spec, dict):
        return _as_source_tokens(source_spec.get(topology, []))
    return _as_source_tokens(source_spec)


def _as_source_tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _resolve_source_token(
    group: str,
    source_token: str,
    surfaces: list[dict[str, Any]],
    boundary_curves: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contributions = [
        _surface_contribution(group, source_token, surface)
        for surface in sorted(surfaces, key=lambda item: item["id"])
        if _surface_matches_token(surface, source_token)
    ]
    contributions.extend(
        _boundary_curve_contribution(group, source_token, curve)
        for curve in sorted(boundary_curves, key=lambda item: item["id"])
        if _boundary_curve_matches_token(curve, source_token)
    )
    return contributions


def _surface_matches_token(surface: dict[str, Any], source_token: str) -> bool:
    values = {source_token, *SURFACE_SOURCE_ALIASES.get(source_token, set())}
    return any(surface.get(field) in values for field in ("cfd_role", "role", "ontology_id", "id", "feature_id"))


def _boundary_curve_matches_token(curve: dict[str, Any], source_token: str) -> bool:
    return any(curve.get(field) == source_token for field in ("role", "ontology_id", "id", "name", "feature_id"))


def _surface_contribution(group: str, source_token: str | None, surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "group": group,
        "source_type": "surface",
        "source_token": source_token or "",
        "source_id": surface["id"],
        "source": surface,
    }


def _boundary_curve_contribution(group: str, source_token: str, curve: dict[str, Any]) -> dict[str, Any]:
    return {
        "group": group,
        "source_type": "boundary_curve",
        "source_token": source_token,
        "source_id": curve["id"],
        "source": curve,
    }


def _patch_instance_metadata(contribution: dict[str, Any]) -> dict[str, Any]:
    source = contribution["source"]
    source_type = contribution["source_type"]
    source_id = contribution["source_id"]
    metadata = {
        "group": contribution["group"],
        "source_type": source_type,
        "source_token": contribution["source_token"],
        "patch_group_source": contribution["source_token"],
        "resolved_from": f"{source_type}:{source_id}",
    }
    if source_type == "surface":
        metadata.update(
            {
                "source_feature": source.get("feature_id"),
                "surface_graph_id": source_id,
                "surface_role": source.get("role"),
                "area_estimate_mm2": estimate_surface_area(source),
            }
        )
    else:
        metadata.update(
            {
                "boundary_curve_id": source_id,
                "boundary_curve_role": source.get("role"),
                "source_feature": source.get("feature_id"),
            }
        )
    return metadata
