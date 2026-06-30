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


def build_cfd_full_360_manifest(
    surface_graph: dict[str, Any],
    simulation_view: dict[str, Any],
    blade_count: int,
) -> dict[str, Any]:
    suppressed = set(simulation_view.get("feature_suppression", {}).get("suppressed_features", []))
    surfaces = wetted_surfaces(surface_graph.get("surfaces", []), suppressed_features=suppressed)
    patch_groups: dict[str, dict[str, Any]] = {
        group: {
            "type": "wall" if group not in {"inlet_patch", "outlet_patch"} else group.replace("_patch", ""),
            "instances": [],
        }
        for group in simulation_view.get("required_patch_groups", [])
    }
    patch_instances: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        group = CFD_ROLE_TO_GROUP.get(surface.get("cfd_role"))
        if not group:
            continue
        patch_groups.setdefault(group, {"type": "wall", "instances": []})
        patch_groups[group]["instances"].append(surface["id"])
        patch_instances[surface["id"]] = {
            "group": group,
            "source_feature": surface.get("feature_id"),
            "surface_graph_id": surface["id"],
            "surface_role": surface.get("role"),
            "area_estimate_mm2": estimate_surface_area(surface),
        }
    for group in patch_groups.values():
        group["instances"].sort()
    failures = [
        f"missing_patch_group_instances:{group_id}"
        for group_id, group in patch_groups.items()
        if not group["instances"]
    ]
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
        },
    }
