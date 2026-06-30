from __future__ import annotations

from typing import Any


def normalize_shape_control_space(
    shape_control_schema: dict[str, Any],
    shape_controls: dict[str, Any],
) -> dict[str, Any]:
    default_stage = int(shape_controls.get("optimization_stage", shape_control_schema["default_stage"]))
    stage_def = next(
        stage for stage in shape_control_schema["optimization_stages"] if int(stage["stage"]) == default_stage
    )
    locked_topology = (
        stage_def["degree"] == "locked"
        and stage_def["control_point_count"] == "locked"
        and stage_def["knot_vector"] == "locked"
    )

    editable_variables: list[dict[str, Any]] = []
    optimizable_variables: list[dict[str, Any]] = []
    semantic_handles: list[dict[str, Any]] = []
    active_policies = shape_controls["policies"]

    for target_entity, policy in active_policies.items():
        topology = policy["representation_topology"]
        _validate_policy_topology(target_entity, topology)
        for variable in policy.get("control_variables", []):
            normalized_variable = {
                **variable,
                "target_entity": target_entity,
                "topology_locked": locked_topology,
            }
            if variable.get("editable", False):
                editable_variables.append(normalized_variable)
            if variable.get("optimizable", False):
                optimizable_variables.append(normalized_variable)
        for handle in policy.get("semantic_handles", []):
            semantic_handles.append({**handle, "target_entity": target_entity})

    for target_entity, material_controls in shape_controls.get("material_domain_controls", {}).items():
        for variable in material_controls.get("control_variables", []):
            normalized_variable = {
                **variable,
                "target_entity": target_entity,
                "topology_locked": locked_topology,
            }
            if variable.get("editable", False):
                editable_variables.append(normalized_variable)
            if variable.get("optimizable", False):
                optimizable_variables.append(normalized_variable)

    return {
        "schema_version": shape_controls.get("shape_control_version", shape_control_schema["shape_control_schema_version"]),
        "optimization_stage": default_stage,
        "locked_topology": locked_topology,
        "active_policies": list(active_policies.keys()),
        "semantic_handles": semantic_handles,
        "editable_variables": editable_variables,
        "optimizable_variables": optimizable_variables,
    }


def _validate_policy_topology(target_entity: str, topology: dict[str, Any]) -> None:
    degree = int(topology["degree"])
    control_point_count = int(topology["control_point_count"])
    if degree < 1:
        raise ValueError(f"{target_entity} NURBS degree must be positive")
    if control_point_count <= degree:
        raise ValueError(f"{target_entity} control point count must exceed degree")
    if topology["knot_policy"] != "clamped_uniform":
        raise ValueError(f"{target_entity} only clamped_uniform knot policy is supported in v0.2")
    if topology["weights"] != "unit":
        raise ValueError(f"{target_entity} only unit weights are supported in v0.2")
