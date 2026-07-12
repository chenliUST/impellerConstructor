from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_5_engineering_drawing import (
    build_engineering_drawing_contract,
    engineering_drawing_view,
    validate_engineering_drawing_contract,
)
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def graph_for(preset_id: str = "radial_open_reference_v1_1") -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_top_uses_surface_projection_and_has_hub_topology_and_both_blade_classes():
    graph = graph_for()
    contract = build_engineering_drawing_contract(graph, preset_id="radial_open_reference_v1_1")
    top = contract["views"]["top"]

    assert contract["contract_version"] == "1.1.5"
    assert contract["geometry_patch_version"] == "1.1.2"
    assert top["surface_projection_paths"]
    assert all(path["source_kind"] == "surface_projection" for path in top["surface_projection_paths"])
    assert not any(path.get("source_kind") == "section_loop" for path in top["surface_projection_paths"])
    assert {circle["id"] for circle in top["circles"]} >= {
        "hub_top_outer",
        "hub_top_inner",
        "mounting_bore",
    }
    assert {
        (section["blade_class"], section["station_role"])
        for section in top["cross_sections"]
    } == {
        (blade_class, role)
        for blade_class in ("main", "splitter")
        for role in ("active_root", "midspan", "active_tip")
    }


def test_meridional_uses_dense_actual_nurbs_curves_material_regions_and_side_view():
    contract = build_engineering_drawing_contract(graph_for(), preset_id="radial_open_reference_v1_1")
    view = contract["views"]["meridional"]

    assert len(view["profiles"]) == 2
    assert all(profile["source_kind"] == "evaluated_nurbs_curve" for profile in view["profiles"])
    assert all(len(profile["points_r_z"]) >= 129 for profile in view["profiles"])
    assert all(profile["sampling"]["maximum_chord_error_mm"] <= 0.1 for profile in view["profiles"])
    assert view["profiles"][0]["points_r_z"] != view["control_polygons"][0]["control_points_r_z"]
    assert view["material_regions"]
    assert all(region["closed"] is True for region in view["material_regions"])
    assert view["side_view"]["surface_projection_paths"]


def test_s_q_has_five_sections_and_xyz_overlay_loops_for_each_present_blade_class():
    contract = build_engineering_drawing_contract(graph_for(), preset_id="radial_open_reference_v1_1")
    rows = contract["views"]["s_q"]["blade_rows"]

    assert [row["blade_class"] for row in rows] == ["main", "splitter"]
    for row in rows:
        assert row["representative_surfaces"]
        assert {surface["id"] for surface in row["representative_surfaces"]} == set(row["surface_ids"])
        assert [section["station_role"] for section in row["sections"]] == [
            "active_root",
            "h_0_25",
            "midspan",
            "h_0_75",
            "active_tip",
        ]
        assert all(section["segments"] for section in row["sections"])
        assert all(
            all(segment["points_xyz"] for segment in section["segments"])
            for section in row["sections"]
        )
        assert len(row["overlay_loops_xyz"]) == 5


def test_construction_registry_accounts_for_every_canonical_leaf():
    graph = graph_for()
    contract = build_engineering_drawing_contract(graph, preset_id="radial_open_reference_v1_1")
    registry = contract["construction_parameter_registry"]

    assert registry["unaccounted_parameter_ids"] == []
    assert registry["records"]
    assert all(record["presentation_mode"] in {
        "dimensioned_on_drawing",
        "listed_in_construction_table",
        "reported_as_quality_evidence",
        "not_applicable",
    } for record in registry["records"])
    assert set(contract["construction_tables"]) == {
        "general_population",
        "support_profiles",
        "blade_sections",
        "pose_twist",
        "attachments",
        "quality_constraints",
    }
    attachment_rows = contract["construction_tables"]["attachments"]["rows"]
    assert attachment_rows
    assert all(row["occurrence_count"] >= 1 for row in attachment_rows)
    assert len(attachment_rows) < len(graph["parameter_inspection"]["blade_instances"])
    assert validate_engineering_drawing_contract(graph, contract) == []


def test_nasa_stage37_top_projection_is_independent_of_section_station_geometry():
    graph = graph_for("nasa_stage37_stator_ring_v1_1")
    contract = build_engineering_drawing_contract(graph, preset_id="nasa_stage37_stator_ring_v1_1")
    projected_blades = {
        path["blade_instance_id"]
        for path in contract["views"]["top"]["surface_projection_paths"]
        if path.get("blade_instance_id")
    }
    expected_blades = set(graph["parameter_inspection"]["blade_instances"])

    assert projected_blades == expected_blades


def test_view_payloads_are_generation_bound_and_do_not_duplicate_other_views():
    graph = graph_for()
    contract = build_engineering_drawing_contract(graph, preset_id="radial_open_reference_v1_1")
    payload = engineering_drawing_view(contract, "s_q")

    assert payload["contract_version"] == "1.1.5"
    assert payload["generation_id"] == graph["generation_id"]
    assert payload["view_id"] == "s_q"
    assert set(payload["view"]) >= {"blade_rows", "projection"}
    assert "top" not in payload and "meridional" not in payload
