from __future__ import annotations

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import RuleSynthesisService


VERSION_CASES = [
    (
        "v0_2",
        "0.2",
        ["radial_open_reference", "radial_closed_reference"],
    ),
    (
        "v0_3",
        "0.3",
        ["radial_open_reference_v0_3", "radial_closed_reference_v0_3"],
    ),
    (
        "v0_4",
        "0.4",
        ["radial_open_reference_v0_4", "radial_closed_reference_v0_4"],
    ),
    (
        "v0_5",
        "0.5",
        ["radial_open_reference_v0_5", "radial_closed_reference_v0_5"],
    ),
    (
        "v0_6",
        "0.6",
        ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"],
    ),
    (
        "v0_7",
        "0.7",
        ["radial_open_reference_v0_7", "radial_closed_reference_v0_7"],
    ),
]

INSTANTIATE_LINEAGE_CASES = [
    ("0.2", "radial_open_reference"),
    ("0.4", "radial_open_reference_v0_4"),
    ("0.6", "radial_open_reference_v0_6"),
    ("0.7", "radial_open_reference_v0_7"),
]


def test_all_versioned_impeller_dsl_resources_remain_loadable_and_compilable():
    for version, expected_dsl_version, preset_ids in VERSION_CASES:
        bundle = load_impeller_dsl_bundle(version)

        assert bundle.schema["dsl_version"] == expected_dsl_version
        assert bundle.constructors
        assert bundle.presets

        for preset_id in preset_ids:
            runtime = compile_impeller_runtime_preset(preset_id)

            assert runtime["preset_id"] == preset_id
            assert runtime["dsl_sections"]["dsl_version"] == expected_dsl_version


def test_representative_versioned_impeller_presets_remain_instantiable(tmp_path):
    service = RuleSynthesisService(tmp_path)

    for expected_dsl_version, preset_id in INSTANTIATE_LINEAGE_CASES:
        engine = service.synthesize("impeller", preset_id=preset_id)
        run = service.instantiate(engine.engine_id, {})

        assert run.manifest["preset_id"] == preset_id
        assert run.manifest["dsl_version"] == expected_dsl_version
        assert run.manifest["geometry_validity"]["status"] == "PASS"

        if expected_dsl_version == "0.4":
            assert run.manifest["campaign_signature"]["dsl_version"] == expected_dsl_version
            assert run.manifest["simulation_manifests"]["cfd_full_360"]["validity"]["status"] == "PASS"
        elif expected_dsl_version in {"0.6", "0.7"}:
            assert run.manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"] > 0
        else:
            assert "campaign_signature" not in run.manifest
            assert run.manifest["simulation_manifests"] == {}
