from __future__ import annotations

import sys
from copy import deepcopy
from math import hypot
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    build_parameter_inspection_contract,
    parameter_inspection_generation_id,
)
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def graph_for(preset_id="radial_open_reference_v1_1", edits=None):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    parameters.update(edits or {})
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_contract_has_release_and_geometry_provenance():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    assert contract["contract_version"] == "1.1.3"
    assert contract["source_geometry_patch_version"] == "1.1.2"
    assert contract["source_canonical_payload_version"] == "1.1.2"
    assert contract["generation_id"] == graph["generation_id"]


def test_contract_references_existing_surfaces_and_actual_loops():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    surface_ids = {surface["id"] for surface in graph["surfaces"]}
    assert set(contract["surface_references"]) == surface_ids
    station = next(iter(contract["span_stations"].values()))
    loop = contract["section_loops"][station["section_loop_id"]]
    assert loop["source_blade_index"] == station["source_blade_index"]
    assert loop["source_loop_index"] == station["source_loop_index"]
    assert set(loop["segment_references"]) == {
        "pressure_side", "suction_side", "leading_edge", "trailing_edge"
    }
    thickness = contract["resolved_dimensions"]["thickness_min_mm"]
    assert thickness["unit"] == "mm"
    assert thickness["requested_value"] is not None
    assert thickness["resolved_value"] == graph["canonical_metrics"]["thickness_min_mm"]


def test_generation_id_is_deterministic_and_geometry_sensitive():
    baseline_a = graph_for()
    baseline_b = graph_for()
    edited = deepcopy(baseline_a)
    edited["surfaces"][0]["uv_grid"][0][0][0] += 0.125
    assert baseline_a["generation_id"] == baseline_b["generation_id"]
    assert parameter_inspection_generation_id(edited) != baseline_a["generation_id"]


def test_generation_id_ignores_reference_only_helper_sampling():
    graph = graph_for()
    edited = deepcopy(graph)
    helper = next(surface for surface in edited["surfaces"] if surface["id"] == "tip_reference_surface")
    helper["uv_grid"] = []

    assert parameter_inspection_generation_id(edited) == graph["generation_id"]


def test_generation_id_hashes_visible_hub_and_shroud_sampling():
    for preset_id, role in (
        ("radial_open_reference_v1_1", "hub_support"),
        ("radial_closed_reference_v1_1", "shroud_support"),
    ):
        graph = graph_for(preset_id)
        edited = deepcopy(graph)
        surface = next(
            surface
            for surface in edited["surfaces"]
            if surface.get("role") == role and surface.get("display", {}).get("visible_by_default") is True
        )
        surface["uv_grid"][0][0][0] += 0.125

        assert parameter_inspection_generation_id(edited) != graph["generation_id"], preset_id


def test_generation_id_hashes_section_samples_and_controls_without_self_reference():
    graph = graph_for()
    loop_edited = deepcopy(graph)
    loop_edited["blade_to_blade_loop_family"]["blades"][0]["loops"][0]["segments"]["pressure_side"][
        "points_s_q"
    ][1][1] += 0.125
    control_edited = deepcopy(graph)
    control_edited["blade_to_blade_loop_family"]["blades"][0]["loops"][0]["segments"]["pressure_side"][
        "control_points_s_q"
    ][1][1] += 0.125
    self_reference_edited = deepcopy(graph)
    self_reference_edited["generation_id"] = "stale"
    self_reference_edited["parameter_inspection"]["generation_id"] = "also-stale"

    assert parameter_inspection_generation_id(loop_edited) != graph["generation_id"]
    assert parameter_inspection_generation_id(control_edited) != graph["generation_id"]
    assert parameter_inspection_generation_id(self_reference_edited) == graph["generation_id"]


def test_reference_uv_exemption_requires_explicit_hidden_reference_metadata():
    graph = graph_for()
    edited = deepcopy(graph)
    helper = next(surface for surface in edited["surfaces"] if surface["id"] == "tip_reference_surface")
    helper["uv_grid"] = []
    helper["surface_flags"].pop("reference_only")
    helper["display"].pop("reference_only")

    assert parameter_inspection_generation_id(edited) != graph["generation_id"]


def test_section_loop_exposes_physical_display_units_and_authoritative_scale():
    graph = graph_for()
    source_loop = graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]
    station = next(iter(graph["parameter_inspection"]["span_stations"].values()))
    loop = graph["parameter_inspection"]["section_loops"][station["section_loop_id"]]
    hub_controls = graph["canonical_nurbs_parameterization"]["support_profiles"]["hub_profile"]["control_points"]
    profile_polyline_length = sum(
        hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(hub_controls, hub_controls[1:])
    )

    assert loop["source_coordinate_units"] == {"s": "normalized", "q": "mm"}
    assert loop["display_coordinate_units"] == {"s": "mm", "q": "mm"}
    assert loop["streamwise_metric_scale_mm"] == source_loop["streamwise_metric_scale_mm"]
    assert loop["streamwise_metric_scale_mm"] == profile_polyline_length
    segment = loop["segment_references"]["pressure_side"]
    assert segment["display_points_s_q_mm"][0] == [
        segment["points_s_q"][0][0] * loop["streamwise_metric_scale_mm"],
        segment["points_s_q"][0][1],
    ]


def test_control_point_ids_are_authoritative_unique_and_stable_under_reorder():
    graph = graph_for()
    baseline = build_parameter_inspection_contract(graph)
    reordered_graph = deepcopy(graph)
    source_controls = reordered_graph["blade_to_blade_loop_family"]["blades"][0]["loops"][0]["segments"][
        "pressure_side"
    ]["control_points_s_q"]
    source_controls.reverse()
    reordered = build_parameter_inspection_contract(reordered_graph)
    baseline_loop = next(iter(baseline["section_loops"].values()))
    reordered_loop = next(iter(reordered["section_loops"].values()))
    baseline_records = baseline_loop["segment_references"]["pressure_side"]["control_points"]
    reordered_records = reordered_loop["segment_references"]["pressure_side"]["control_points"]

    assert len({record["control_point_id"] for record in baseline_records}) == len(baseline_records)
    assert {
        tuple(record["coordinates_s_q"]): record["control_point_id"] for record in baseline_records
    } == {
        tuple(record["coordinates_s_q"]): record["control_point_id"] for record in reordered_records
    }
    assert all(
        record["section_segment_id"] == baseline_loop["segment_references"]["pressure_side"]["section_segment_id"]
        for record in baseline_records
    )


def test_all_active_presets_emit_contracts():
    for preset_id in ACTIVE_PRESETS:
        graph = graph_for(preset_id)
        assert graph["parameter_inspection"]["contract_version"] == "1.1.3", preset_id
        assert graph["parameter_inspection"]["blade_instances"], preset_id
