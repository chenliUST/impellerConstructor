from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = PROJECT_ROOT / "src" / "part_rule_synthesis" / "ontology" / "impeller" / "v0_4"
DSL_ROOT = (
    PROJECT_ROOT
    / "src"
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_4"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v04_resource_files_exist_and_are_valid_json():
    ontology_files = [
        "slice.json",
        "entities.json",
        "relations.json",
        "validity_contracts.json",
        "loss_schema.json",
    ]
    dsl_files = [
        "schema.json",
        "constructors/open_impeller.json",
        "constructors/closed_impeller.json",
        "presets/radial_open_reference.json",
        "presets/radial_closed_reference.json",
        "shape_controls/default_shape_controls.json",
        "simulation_views/cfd_full_360.json",
        "simulation_views/fea_solid_schema.json",
        "aliases.json",
    ]

    for name in ontology_files:
        assert isinstance(read_json(ONTOLOGY_ROOT / name), dict), name
    for name in dsl_files:
        assert isinstance(read_json(DSL_ROOT / name), dict), name


def test_v04_schema_defines_graph_contract_design_space_and_simulation_views():
    schema = read_json(DSL_ROOT / "schema.json")

    assert schema["dsl_version"] == "0.4"
    assert schema["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert "design_space" in schema["required_sections"]
    assert "surface_graph_contract" in schema["required_sections"]
    assert "feature_graph_contract" in schema["required_sections"]
    assert "simulation_views" in schema["required_sections"]
    assert schema["patch_naming_policy"] == "group_and_instance"


def test_v04_design_space_separates_topology_and_numeric_variables():
    shape_controls = read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")

    assert shape_controls["shape_control_version"] == "0.4"
    assert "topology_variables" in shape_controls["design_space"]
    assert "design_variables" in shape_controls["design_space"]
    assert "hub_profile.control_point_count" in shape_controls["design_space"]["topology_variables"]
    assert "root_fillet.radius_mm" in shape_controls["design_space"]["design_variables"]
    assert shape_controls["campaign_freeze_rule"] == "topology_variables_immutable_inside_campaign"


def test_v04_simulation_views_define_cfd_executable_and_fea_schema_only():
    cfd = read_json(DSL_ROOT / "simulation_views" / "cfd_full_360.json")
    fea = read_json(DSL_ROOT / "simulation_views" / "fea_solid_schema.json")

    assert cfd["view_id"] == "cfd_full_360"
    assert cfd["domain_kind"] == "full_360_wetted_surface"
    assert cfd["status"] == "research_grade_executable"
    assert cfd["patch_naming"] == "group_and_instance"
    assert "mounting_bore" in cfd["feature_suppression"]["suppressed_features"]
    assert fea["view_id"] == "fea_solid"
    assert fea["status"] == "schema_only_v0_4"


def test_v04_constructors_define_feature_graph_and_boundary_guided_blades():
    open_constructor = read_json(DSL_ROOT / "constructors" / "open_impeller.json")
    closed_constructor = read_json(DSL_ROOT / "constructors" / "closed_impeller.json")

    for constructor in [open_constructor, closed_constructor]:
        assert constructor["dsl_version"] == "0.4"
        assert constructor["blade_surface_model"]["kind"] == "boundary_guided_camber_surface_with_thickness"
        assert "leading_edge_round" in constructor["feature_graph"]["blade_transition_features"]
        assert "mounting_bore" in constructor["feature_graph"]["assembly_features"]
        assert "balance_holes" in constructor["feature_graph"]["tuning_features"]

    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is False
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is True


def test_v04_shape_control_targets_resolve_to_constructor_vocabulary():
    shape_controls = read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")
    constructors = [
        read_json(DSL_ROOT / "constructors" / "open_impeller.json"),
        read_json(DSL_ROOT / "constructors" / "closed_impeller.json"),
    ]
    legacy_transition_targets = {
        "leading_edge_closure_surface",
        "trailing_edge_closure_surface",
        "root_closure_or_fillet_surface",
        "tip_closure_or_shroud_join_surface",
    }
    v04_transition_targets = {
        "leading_edge_transition",
        "trailing_edge_transition",
        "root_transition",
        "tip_transition",
    }
    target_entities = set(shape_controls["target_entities"])
    carried_forward = set(shape_controls["carried_forward_from_v0_3"])

    assert not (target_entities & legacy_transition_targets)
    assert not (carried_forward & legacy_transition_targets)
    assert v04_transition_targets <= target_entities
    assert v04_transition_targets <= carried_forward

    allowed_targets = set(shape_controls["material_domain_controls"])
    for constructor in constructors:
        allowed_targets.update(constructor["support_surfaces"])
        allowed_targets.update(
            surface["source_profile"]
            for surface in constructor["support_surfaces"].values()
            if "source_profile" in surface
        )
        allowed_targets.update(constructor["blade_surface_model"]["output_surfaces"])
        allowed_targets.update(boundary["id"] for boundary in constructor["blade_boundaries"].values())
        allowed_targets.add(constructor["blade_profile"]["thickness_field"])
        allowed_targets.add("blade_mean_surface")
        feature_graph = constructor["feature_graph"]
        allowed_targets.update(feature_graph["blade_transition_features"])
        allowed_targets.update(feature_graph["assembly_features"])
        allowed_targets.update(feature_graph["tuning_features"])

    assert target_entities - allowed_targets == set()
    assert carried_forward - allowed_targets == set()


def test_v04_cfd_patch_groups_define_source_roles():
    cfd = read_json(DSL_ROOT / "simulation_views" / "cfd_full_360.json")

    assert set(cfd["patch_group_sources"]) == set(cfd["required_patch_groups"])
    for group_id in cfd["required_patch_groups"]:
        sources = cfd["patch_group_sources"][group_id]
        assert isinstance(sources, list), group_id
        assert sources, group_id
        assert all(isinstance(source, str) and source for source in sources), group_id


def test_v04_supersedes_paths_resolve_from_declaring_file():
    for root in [ONTOLOGY_ROOT, DSL_ROOT]:
        for path in root.rglob("*.json"):
            resource = read_json(path)
            supersedes = resource.get("supersedes")
            if supersedes is None:
                continue
            superseded_path = (path.parent / supersedes).resolve()
            assert superseded_path.exists(), f"{path.relative_to(PROJECT_ROOT)} -> {supersedes}"
