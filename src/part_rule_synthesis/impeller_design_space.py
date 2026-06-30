from __future__ import annotations

from typing import Any


def build_campaign_signature(
    runtime: dict[str, Any],
    profile_overrides: dict[str, Any] | None,
    feature_states: dict[str, Any] | None,
    patch_groups: list[str] | None = None,
) -> dict[str, Any]:
    profiles = profile_overrides or {}
    features = feature_states or {}
    profile_topology = {}
    for profile_id in ["hub_profile", "tip_or_shroud_profile"]:
        profile = profiles.get(profile_id, {})
        control_points = profile.get("control_points", [])
        profile_topology[profile_id] = {
            "degree": int(profile.get("degree", 3)),
            "control_point_count": len(control_points),
            "knot_count": len(profile.get("knots", [])),
            "weight_count": len(profile.get("weights", [])),
        }
    enabled_features = sorted(
        feature_id
        for feature_id, state in features.items()
        if _feature_enabled(state)
    )
    design_vector_length = sum(
        2 * topology["control_point_count"]
        for topology in profile_topology.values()
    ) + len(enabled_features)
    return {
        "dsl_version": str(
            runtime.get("dsl_sections", {}).get("dsl_version", runtime.get("dsl_version", ""))
        ),
        "preset_id": runtime.get("preset_id"),
        "constructor_id": runtime.get("constructor_id"),
        "profile_topology": profile_topology,
        "enabled_features": enabled_features,
        "patch_groups": sorted(patch_groups or []),
        "design_vector_length": design_vector_length,
        "freeze_rule": "topology_variables_immutable_inside_campaign",
    }


def require_campaign_compatible(previous: dict[str, Any], current: dict[str, Any]) -> None:
    for key in ["profile_topology", "enabled_features", "patch_groups"]:
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
