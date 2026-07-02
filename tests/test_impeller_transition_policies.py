from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_transition_policies import (
    TransitionPolicyError,
    resolve_transition_policies,
)


def test_resolve_transition_policies_builds_defaults_from_edge_families_and_parameters():
    policies = resolve_transition_policies(
        {
            "blade_root_to_hub": {
                "default_treatment": "fillet",
                "default_radius_parameter": "root_fillet_radius_mm",
            },
            "mounting_bore_top": {
                "default_treatment": "chamfer",
                "default_radius_parameter": "hub_chamfer_radius_mm",
            },
            "blade_tip_or_shroud": {
                "default_treatment": "none",
                "default_radius_parameter": "tip_edge_radius_mm",
            },
        },
        {
            "root_fillet_radius_mm": 8.0,
            "hub_chamfer_radius_mm": 3.0,
            "tip_edge_radius_mm": 2.0,
        },
    )

    assert policies["blade_root_to_hub.default"] == {
        "policy_id": "blade_root_to_hub.default",
        "edge_family": "blade_root_to_hub",
        "enabled": True,
        "treatment": "fillet",
        "radius_mm": 8.0,
        "continuity": "G1",
        "applies_to": "all_pattern_instances",
        "maps_to_parameters": ["root_fillet_radius_mm"],
        "overrides": [],
    }
    assert policies["mounting_bore_top.default"]["treatment"] == "chamfer"
    assert policies["mounting_bore_top.default"]["continuity"] == "G0"
    assert policies["mounting_bore_top.default"]["radius_mm"] == 3.0
    assert policies["blade_tip_or_shroud.default"]["enabled"] is False
    assert policies["blade_tip_or_shroud.default"]["treatment"] == "none"
    assert policies["blade_tip_or_shroud.default"]["radius_mm"] == 0.0
    assert policies["blade_tip_or_shroud.default"]["continuity"] == "G0"


def test_resolve_transition_policies_applies_treatment_and_radius_override():
    policies = resolve_transition_policies(
        {
            "blade_root_to_hub": {
                "default_treatment": "fillet",
                "default_radius_parameter": "root_fillet_radius_mm",
            }
        },
        {"root_fillet_radius_mm": 8.0},
        overrides={
            "blade_root_to_hub.default": {
                "treatment": "chamfer",
                "radius_mm": 6.0,
            }
        },
    )

    policy = policies["blade_root_to_hub.default"]
    assert policy["enabled"] is True
    assert policy["treatment"] == "chamfer"
    assert policy["radius_mm"] == 6.0
    assert policy["continuity"] == "G0"
    assert policy["overrides"] == ["treatment", "radius_mm"]


def test_resolve_transition_policies_rejects_unknown_policy_override():
    with pytest.raises(TransitionPolicyError, match="unknown transition policy"):
        resolve_transition_policies(
            {
                "blade_root_to_hub": {
                    "default_treatment": "fillet",
                    "default_radius_parameter": "root_fillet_radius_mm",
                }
            },
            {"root_fillet_radius_mm": 8.0},
            overrides={"blade_tip_or_shroud.default": {"treatment": "chamfer"}},
        )


def test_resolve_transition_policies_rejects_non_object_override():
    with pytest.raises(TransitionPolicyError, match="override must be an object"):
        resolve_transition_policies(
            {
                "blade_root_to_hub": {
                    "default_treatment": "fillet",
                    "default_radius_parameter": "root_fillet_radius_mm",
                }
            },
            {"root_fillet_radius_mm": 8.0},
            overrides={"blade_root_to_hub.default": "chamfer"},
        )


def test_resolve_transition_policies_rejects_unsupported_treatment_override():
    with pytest.raises(TransitionPolicyError, match="unsupported transition treatment"):
        resolve_transition_policies(
            {
                "blade_root_to_hub": {
                    "default_treatment": "fillet",
                    "default_radius_parameter": "root_fillet_radius_mm",
                }
            },
            {"root_fillet_radius_mm": 8.0},
            overrides={"blade_root_to_hub.default": {"treatment": "blend"}},
        )


def test_resolve_transition_policies_rejects_negative_radius_override():
    with pytest.raises(TransitionPolicyError, match="negative transition radius"):
        resolve_transition_policies(
            {
                "blade_root_to_hub": {
                    "default_treatment": "fillet",
                    "default_radius_parameter": "root_fillet_radius_mm",
                }
            },
            {"root_fillet_radius_mm": 8.0},
            overrides={"blade_root_to_hub.default": {"radius_mm": -1.0}},
        )
