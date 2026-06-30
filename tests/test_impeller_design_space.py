from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_design_space import (
    build_campaign_signature,
    flatten_design_vector,
    require_campaign_compatible,
)
from part_rule_synthesis.service import RuleSynthesisService


def test_campaign_signature_freezes_topology_not_numeric_values():
    runtime = {
        "preset_id": "radial_open_reference_v0_4",
        "constructor_id": "axisymmetric_throughflow_radial_bladed.open.v0_4",
        "dsl_version": "0.4",
        "shape_control": {
            "design_space": {
                "topology_variables": [
                    "hub_profile.control_point_count",
                    "tip_profile.control_point_count",
                    "enabled_features",
                ],
                "design_variables": [
                    "hub_profile.control_points[*].r_mm",
                    "root_fillet.radius_mm",
                ],
            }
        },
    }
    profiles = {
        "hub_profile": {
            "degree": 3,
            "control_points": [[100, 50], [150, 30], [220, 10], [300, 0]],
        },
        "tip_or_shroud_profile": {
            "degree": 3,
            "control_points": [[140, 70], [180, 50], [260, 30], [340, 20]],
        },
    }
    features = {"mounting_bore": {"enabled": True}, "keyway": {"enabled": True}}

    signature = build_campaign_signature(runtime, profiles, features)

    assert signature["dsl_version"] == "0.4"
    assert signature["profile_topology"]["hub_profile"]["control_point_count"] == 4
    assert signature["profile_topology"]["tip_profile"]["control_point_count"] == 4
    assert "tip_or_shroud_profile" not in signature["profile_topology"]
    assert signature["enabled_features"] == ["keyway", "mounting_bore"]
    assert signature["design_vector_length"] == 2


def test_campaign_signature_allows_numeric_only_profile_changes():
    runtime = {
        "preset_id": "radial_open_reference_v0_4",
        "constructor_id": "axisymmetric_throughflow_radial_bladed.open.v0_4",
        "dsl_version": "0.4",
    }
    baseline_profiles = {
        "hub_profile": {
            "degree": 3,
            "control_points": [[100, 50], [150, 30], [220, 10], [300, 0]],
        },
        "tip_or_shroud_profile": {
            "degree": 3,
            "control_points": [[140, 70], [180, 50], [260, 30], [340, 20]],
        },
    }
    numeric_edit_profiles = {
        "hub_profile": {
            "degree": 3,
            "control_points": [[102, 52], [151, 33], [219, 12], [301, 1]],
        },
        "tip_or_shroud_profile": {
            "degree": 3,
            "control_points": [[141, 72], [181, 51], [261, 29], [339, 21]],
        },
    }
    features = {"mounting_bore": {"enabled": True}, "keyway": {"enabled": True}}

    baseline = build_campaign_signature(
        runtime,
        baseline_profiles,
        features,
        patch_groups=["hub_wall"],
    )
    numeric_edit = build_campaign_signature(
        runtime,
        numeric_edit_profiles,
        features,
        patch_groups=["hub_wall"],
    )

    require_campaign_compatible(baseline, numeric_edit)
    assert numeric_edit["profile_topology"] == baseline["profile_topology"]
    assert numeric_edit["enabled_features"] == baseline["enabled_features"]
    assert numeric_edit["patch_groups"] == baseline["patch_groups"]
    assert numeric_edit["design_vector_length"] == baseline["design_vector_length"]


def test_campaign_signature_detects_topology_change():
    baseline = {
        "profile_topology": {"hub_profile": {"control_point_count": 4}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
    }
    changed = {
        "profile_topology": {"hub_profile": {"control_point_count": 5}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
    }

    with pytest.raises(ValueError, match="campaign topology changed"):
        require_campaign_compatible(baseline, changed)


def test_campaign_signature_detects_design_vector_length_change():
    baseline = {
        "profile_topology": {"hub_profile": {"control_point_count": 4}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
        "design_vector_length": 18,
    }
    changed = {
        "profile_topology": {"hub_profile": {"control_point_count": 4}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
        "design_vector_length": 19,
    }

    with pytest.raises(ValueError, match="campaign topology changed: design_vector_length"):
        require_campaign_compatible(baseline, changed)


def test_flatten_design_vector_returns_stable_sorted_values():
    values = {
        "root_fillet.radius_mm": 3.0,
        "hub_profile.control_points[1].r_mm": 150.0,
        "hub_profile.control_points[0].r_mm": 100.0,
    }

    vector = flatten_design_vector(values)

    assert vector == [
        {"name": "hub_profile.control_points[0].r_mm", "value": 100.0},
        {"name": "hub_profile.control_points[1].r_mm", "value": 150.0},
        {"name": "root_fillet.radius_mm", "value": 3.0},
    ]


def test_service_manifest_adds_campaign_signature_only_for_v04(tmp_path):
    service = RuleSynthesisService(tmp_path)

    v04_engine = service.synthesize("impeller", "radial_open_reference_v0_4", {})
    v04_run = service.instantiate(v04_engine.engine_id, {})
    v04_dsl = service.engines[v04_engine.engine_id]
    signature = v04_run.manifest["campaign_signature"]
    expected_features = sorted(
        feature_id
        for feature_group in v04_dsl["feature_graph"].values()
        for feature_id in feature_group
    )
    expected_patch_groups = sorted(
        v04_dsl["simulation_views"]["cfd_full_360"]["required_patch_groups"]
    )
    expected_vector_length = len(v04_dsl["shape_control"]["optimizable_variables"])

    assert v04_run.manifest["dsl_version"] == "0.4"
    assert signature["dsl_version"] == "0.4"
    assert signature["preset_id"] == "radial_open_reference_v0_4"
    assert signature["profile_topology"]["hub_profile"]["control_point_count"] == 6
    assert signature["profile_topology"]["tip_profile"]["control_point_count"] == 6
    assert signature["profile_topology"]["blade_surface"]["guide_curve_count"] == 3
    assert signature["profile_topology"]["blade_surface"]["spanwise_layer_count"] == 4
    assert "tip_or_shroud_profile" not in signature["profile_topology"]
    assert signature["enabled_features"] == expected_features
    assert signature["patch_groups"] == expected_patch_groups
    assert signature["design_vector_length"] == expected_vector_length
    assert signature["design_vector_length"] > 0

    for preset_id, expected_dsl_version in [
        ("radial_open_reference", "0.2"),
        ("radial_open_reference_v0_3", "0.3"),
    ]:
        engine = service.synthesize("impeller", preset_id, {})
        run = service.instantiate(engine.engine_id, {})

        assert run.manifest["dsl_version"] == expected_dsl_version
        assert "campaign_signature" not in run.manifest
