from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


SUPPORTED_TREATMENTS = {"none", "chamfer", "fillet"}
SUPPORTED_OVERRIDE_KEYS = {"enabled", "treatment", "radius_mm"}
SUPPORTED_CONTINUITIES = {"G0", "G1", "G2"}


class TransitionPolicyError(ValueError):
    pass


def resolve_transition_policies(
    edge_families: dict[str, Any],
    parameters: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_overrides = _normalize_overrides(overrides)
    policies: dict[str, dict[str, Any]] = {}

    for edge_family_id, edge_family in edge_families.items():
        if not isinstance(edge_family, Mapping):
            raise TransitionPolicyError(f"edge family {edge_family_id} must be an object")
        policy_id = f"{edge_family_id}.default"
        treatment = _validate_treatment(policy_id, edge_family.get("default_treatment"))
        continuity = _validate_continuity(policy_id, edge_family.get("default_continuity"), treatment)
        radius_parameter = edge_family.get("default_radius_parameter")
        if not isinstance(radius_parameter, str):
            raise TransitionPolicyError(f"edge family {edge_family_id} default_radius_parameter must be a string")
        if radius_parameter not in parameters:
            raise TransitionPolicyError(
                f"edge family {edge_family_id} radius parameter not found: {radius_parameter}"
            )
        radius_mm = _validate_radius(policy_id, parameters[radius_parameter])
        policies[policy_id] = _policy(
            policy_id=policy_id,
            edge_family=edge_family_id,
            treatment=treatment,
            continuity=continuity,
            radius_mm=radius_mm,
            maps_to_parameters=[radius_parameter],
            overrides=[],
        )

    for policy_id, override in normalized_overrides.items():
        if policy_id not in policies:
            raise TransitionPolicyError(f"unknown transition policy: {policy_id}")
        if not isinstance(override, Mapping):
            raise TransitionPolicyError(f"transition policy {policy_id} override must be an object")
        unknown_keys = sorted(set(override) - SUPPORTED_OVERRIDE_KEYS)
        if unknown_keys:
            raise TransitionPolicyError(
                f"unknown transition override field for {policy_id}: {', '.join(unknown_keys)}"
            )

        policy = dict(policies[policy_id])
        applied_overrides = []
        enabled_overridden = "enabled" in override
        if enabled_overridden:
            policy["enabled"] = _validate_enabled(policy_id, override["enabled"])
            applied_overrides.append("enabled")
        if "treatment" in override:
            policy["treatment"] = _validate_treatment(policy_id, override["treatment"])
            applied_overrides.append("treatment")
        if "radius_mm" in override:
            policy["radius_mm"] = _validate_radius(policy_id, override["radius_mm"])
            applied_overrides.append("radius_mm")
        policy["overrides"] = applied_overrides
        _apply_treatment(policy, enabled_overridden=enabled_overridden)
        policies[policy_id] = policy

    for policy in policies.values():
        _validate_active_policy_radius(policy)

    return policies


def _normalize_overrides(overrides: dict[str, Any] | None) -> Mapping[str, Any]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise TransitionPolicyError("transition overrides must be an object")
    return overrides


def _policy(
    *,
    policy_id: str,
    edge_family: str,
    treatment: str,
    continuity: str | None,
    radius_mm: float,
    maps_to_parameters: list[str],
    overrides: list[str],
) -> dict[str, Any]:
    policy = {
        "policy_id": policy_id,
        "edge_family": edge_family,
        "enabled": True,
        "treatment": treatment,
        "radius_mm": radius_mm,
        "requested_continuity": continuity,
        "continuity": _continuity_for_treatment(treatment, continuity),
        "applies_to": "all_pattern_instances",
        "maps_to_parameters": maps_to_parameters,
        "overrides": overrides,
    }
    _apply_treatment(policy)
    return policy


def _apply_treatment(policy: dict[str, Any], enabled_overridden: bool = False) -> None:
    treatment = policy["treatment"]
    policy["continuity"] = _continuity_for_treatment(treatment, policy.get("requested_continuity"))
    if treatment == "none":
        policy["enabled"] = False
        policy["radius_mm"] = 0.0
    elif not enabled_overridden:
        policy["enabled"] = True


def _validate_active_policy_radius(policy: dict[str, Any]) -> None:
    if policy["enabled"] and policy["treatment"] != "none" and policy["radius_mm"] <= 0.0:
        raise TransitionPolicyError(
            f"positive transition radius required for {policy['policy_id']}: {policy['radius_mm']}"
        )


def _validate_treatment(policy_id: str, treatment: Any) -> str:
    if treatment not in SUPPORTED_TREATMENTS:
        raise TransitionPolicyError(f"unsupported transition treatment for {policy_id}: {treatment}")
    return str(treatment)


def _validate_continuity(policy_id: str, continuity: Any, treatment: str) -> str | None:
    if continuity is None:
        return None
    if continuity not in SUPPORTED_CONTINUITIES:
        raise TransitionPolicyError(f"unsupported transition continuity for {policy_id}: {continuity}")
    if treatment == "chamfer" and continuity != "G0":
        raise TransitionPolicyError(f"chamfer transition continuity for {policy_id} must be G0")
    if treatment == "none" and continuity != "G0":
        raise TransitionPolicyError(f"disabled transition continuity for {policy_id} must be G0")
    return str(continuity)


def _continuity_for_treatment(treatment: str, requested_continuity: str | None) -> str:
    if treatment == "none":
        return "G0"
    if treatment == "chamfer":
        return "G0"
    return requested_continuity or "G1"


def _validate_enabled(policy_id: str, enabled: Any) -> bool:
    if type(enabled) is not bool:
        raise TransitionPolicyError(f"enabled override must be a boolean for {policy_id}")
    return enabled


def _validate_radius(policy_id: str, radius_mm: Any) -> float:
    if type(radius_mm) is bool:
        raise TransitionPolicyError(f"transition radius for {policy_id} must be numeric")
    try:
        radius = float(radius_mm)
    except (TypeError, ValueError) as exc:
        raise TransitionPolicyError(f"transition radius for {policy_id} must be numeric") from exc
    if not math.isfinite(radius):
        raise TransitionPolicyError(f"finite transition radius required for {policy_id}: {radius}")
    if radius < 0.0:
        raise TransitionPolicyError(f"negative transition radius for {policy_id}: {radius}")
    return radius
