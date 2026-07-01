from __future__ import annotations

from typing import Any


def build_campaign_signature(
    runtime: dict[str, Any],
    profile_overrides: dict[str, Any] | None,
    feature_states: dict[str, Any] | None,
    patch_groups: list[str] | None = None,
) -> dict[str, Any]:
    profile_topology = _profile_topology(runtime, profile_overrides or {})
    enabled_features = _enabled_features(runtime, feature_states or {})
    design_vector_length = _design_vector_length(runtime.get("shape_control", {}), profile_topology)
    resolved_patch_groups = (
        sorted(patch_groups)
        if patch_groups is not None
        else _patch_groups_from_runtime(runtime)
    )
    return {
        "dsl_version": _dsl_version(runtime),
        "preset_id": runtime.get("preset_id"),
        "constructor_id": runtime.get("constructor_id"),
        "profile_topology": profile_topology,
        "enabled_features": enabled_features,
        "patch_groups": resolved_patch_groups,
        "design_vector_length": design_vector_length,
        "freeze_rule": "topology_variables_immutable_inside_campaign",
    }


def require_campaign_compatible(previous: dict[str, Any], current: dict[str, Any]) -> None:
    for key in ["profile_topology", "enabled_features", "patch_groups", "design_vector_length"]:
        if previous.get(key) != current.get(key):
            raise ValueError(f"campaign topology changed: {key}")


def flatten_design_vector(values: dict[str, float | int]) -> list[dict[str, float]]:
    return [
        {"name": name, "value": float(values[name])}
        for name in sorted(values)
    ]


def _feature_enabled(state: Any) -> bool:
    if isinstance(state, dict):
        return bool(state.get("enabled", True))
    if isinstance(state, bool):
        return state
    return True


def _dsl_version(runtime: dict[str, Any]) -> str:
    return str(
        runtime.get("dsl_sections", {}).get("dsl_version", runtime.get("dsl_version", ""))
    )


def _profile_topology(runtime: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    shape_control = runtime.get("shape_control", {})
    topology_defaults = shape_control.get("topology_defaults", {})
    optimizable_variables = _optimizable_variables(shape_control)
    v04_naming = _dsl_version(runtime) == "0.4" or "tip_profile" in topology_defaults

    tip_profile_id = "tip_profile" if v04_naming else "tip_or_shroud_profile"
    profile_topology = {
        "hub_profile": _profile_entry(
            profiles,
            topology_defaults,
            optimizable_variables,
            canonical_id="hub_profile",
            aliases=["hub_profile"],
            target_entity="hub_meridional_profile",
        ),
        tip_profile_id: _profile_entry(
            profiles,
            topology_defaults,
            optimizable_variables,
            canonical_id="tip_profile",
            aliases=["tip_profile", "tip_or_shroud_profile"],
            target_entity="blade_tip_meridional_profile",
        ),
    }
    if "blade_surface" in topology_defaults:
        profile_topology["blade_surface"] = _normalize_topology_entry(
            topology_defaults["blade_surface"]
        )
    return profile_topology


def _profile_entry(
    profiles: dict[str, Any],
    topology_defaults: dict[str, Any],
    optimizable_variables: list[dict[str, Any]],
    *,
    canonical_id: str,
    aliases: list[str],
    target_entity: str,
) -> dict[str, Any]:
    profile = next((profiles[alias] for alias in aliases if alias in profiles), None)
    if profile:
        default_degree = topology_defaults.get(canonical_id, {}).get("degree", 3)
        return {
            "degree": int(profile.get("degree", default_degree)),
            "control_point_count": len(profile.get("control_points", [])),
            "knot_count": len(profile.get("knots", [])),
            "weight_count": len(profile.get("weights", [])),
        }
    if canonical_id in topology_defaults:
        return _normalize_topology_entry(topology_defaults[canonical_id])

    inferred_count = _infer_control_point_count(optimizable_variables, target_entity)
    return {
        "degree": 3,
        "control_point_count": inferred_count,
        "knot_count": 0,
        "weight_count": 0,
    }


def _normalize_topology_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    for key in [
        "degree",
        "control_point_count",
        "guide_curve_count",
        "spanwise_layer_count",
        "knot_count",
        "weight_count",
    ]:
        if key in normalized:
            normalized[key] = int(normalized[key])
    return normalized


def _infer_control_point_count(
    optimizable_variables: list[dict[str, Any]],
    target_entity: str,
) -> int:
    indices = [
        int(variable["control_point_index"])
        for variable in optimizable_variables
        if variable.get("target_entity") == target_entity
        and variable.get("kind") == "control_point_coordinate"
        and "control_point_index" in variable
    ]
    return max(indices) + 1 if indices else 0


def _enabled_features(runtime: dict[str, Any], feature_states: dict[str, Any]) -> list[str]:
    if feature_states:
        return sorted(
            feature_id
            for feature_id, state in feature_states.items()
            if _feature_enabled(state)
        )
    feature_graph = runtime.get("feature_graph") or runtime.get("dsl_sections", {}).get(
        "feature_graph", {}
    )
    return sorted(
        feature_id
        for features in feature_graph.values()
        if isinstance(features, dict)
        for feature_id in features
    )


def _design_vector_length(
    shape_control: dict[str, Any],
    profile_topology: dict[str, Any],
) -> int:
    optimizable_variables = _optimizable_variables(shape_control)
    if optimizable_variables:
        return len(optimizable_variables)

    design_variables = shape_control.get("design_space", {}).get("design_variables")
    if isinstance(design_variables, list):
        return len(design_variables)

    return sum(
        2 * int(profile_topology.get(profile_id, {}).get("control_point_count", 0))
        for profile_id in ["hub_profile", "tip_profile", "tip_or_shroud_profile"]
    )


def _optimizable_variables(shape_control: dict[str, Any]) -> list[dict[str, Any]]:
    variables = shape_control.get("optimizable_variables")
    if isinstance(variables, list):
        return variables
    nested_variables = shape_control.get("shape_optimization_space", {}).get(
        "optimizable_variables"
    )
    return nested_variables if isinstance(nested_variables, list) else []


def _patch_groups_from_runtime(runtime: dict[str, Any]) -> list[str]:
    simulation_views = runtime.get("simulation_views") or runtime.get("dsl_sections", {}).get(
        "simulation_views", {}
    )
    cfd_view = simulation_views.get("cfd_full_360", {})
    patch_groups = cfd_view.get("required_patch_groups", [])
    return sorted(patch_groups) if isinstance(patch_groups, list) else []
