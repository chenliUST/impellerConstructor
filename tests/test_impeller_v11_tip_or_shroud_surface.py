from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph, _map_tip_s_q_to_xyz


def test_open_tip_dome_is_bounded_by_tip_loop():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    tips = [surface for surface in graph["surfaces"] if surface.get("role") == "open_tip_dome"]

    assert tips
    for tip in tips:
        assert tip["v1_1_tip_quality"]["status"] == "PASS"
        assert tip["v1_1_tip_quality"]["tip_area_ratio"] <= 1.15
        assert tip["display"]["visible_by_default"] is True


def test_open_tip_cap_does_not_collapse_to_centroid_cone():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    tips = [surface for surface in graph["surfaces"] if surface.get("role") == "open_tip_dome"]

    assert tips
    for tip in tips:
        boundary_span = _row_spread(tip["uv_grid"][0])
        for row in tip["uv_grid"][1:]:
            assert _row_spread(row) >= 0.45 * boundary_span


def test_open_tip_cap_reuses_adjacent_tip_boundaries():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    surfaces = graph["surfaces"]

    tip = next(
        surface
        for surface in surfaces
        if surface.get("role") == "open_tip_dome"
        and surface.get("blade_class") == "main"
        and surface.get("blade_pair_index") == 0
    )
    adjacent = {
        surface["role"]: surface
        for surface in surfaces
        if surface.get("blade_class") == "main"
        and surface.get("blade_pair_index") == 0
        and surface.get("role") in {"blade_pressure", "blade_suction", "blade_leading_edge", "blade_trailing_edge"}
    }

    assert tip["edge_samples"]["pressure_tip_curve"] == adjacent["blade_pressure"]["edge_samples"]["tip"]
    assert tip["edge_samples"]["suction_tip_curve"] == adjacent["blade_suction"]["edge_samples"]["tip"]
    assert tip["edge_samples"]["leading_tip_curve"] == adjacent["blade_leading_edge"]["edge_samples"]["tip"]
    assert tip["edge_samples"]["trailing_tip_curve"] == adjacent["blade_trailing_edge"]["edge_samples"]["tip"]


def test_open_tip_reference_support_is_hidden_by_default():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    support_surfaces = [surface for surface in graph["surfaces"] if surface.get("role") == "open_tip_reference"]

    assert support_surfaces
    for surface in support_surfaces:
        assert surface["role"] == "open_tip_reference"
        assert surface["display"]["visible_by_default"] is False
        assert surface["display"]["reference_only"] is True
        assert surface["display"]["inspection_class"] == "open_tip_reference"


def test_closed_tip_uses_shroud_attachment_not_open_dome():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    roles = {surface.get("role") for surface in graph["surfaces"]}

    assert "closed_shroud_attachment" in roles
    assert "open_tip_dome" not in roles


def test_closed_shroud_support_has_finite_material_thickness():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    assert "shroud_support_surface" in surfaces
    assert "shroud_outer_material_surface" in surfaces
    assert "shroud_inlet_rim_surface" in surfaces
    assert "shroud_outlet_rim_surface" in surfaces

    quality = surfaces["shroud_outer_material_surface"]["v1_1_shroud_solid_quality"]
    requested_thickness = runtime["parameters"]["hood_wall_thickness_mm"]["default"]

    assert quality["status"] == "PASS"
    assert quality["construction"] == "v1_1_finite_thickness_revolved_shroud_solid"
    assert quality["hood_wall_thickness_mm"] == requested_thickness
    assert quality["shroud_wall_thickness_min_mm"] >= 0.95 * requested_thickness
    assert quality["shroud_wall_thickness_max_mm"] <= 1.05 * requested_thickness
    assert surfaces["shroud_outer_material_surface"]["role"] == "shroud_support"


def test_closed_blade_loop_stays_between_hub_and_shroud_material_offsets():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    pressure = surfaces["blade_0_pressure_surface"]
    shroud = surfaces["blade_0_closed_shroud_attachment_surface"]
    root = surfaces["blade_0_root_attachment_surface"]
    average_thickness = defaults["average_blade_thickness_mm"]

    assert pressure["v1_1_span_domain_quality"]["material_domain_status"] == "PASS"
    assert pressure["v1_1_span_domain_quality"]["root_clearance_min_mm"] >= 0.75 * average_thickness
    assert pressure["v1_1_span_domain_quality"]["tip_clearance_min_mm"] >= 0.75 * average_thickness
    assert root["v1_1_root_quality"]["root_width_min_mm"] <= 1.35 * average_thickness
    assert shroud["v1_1_tip_quality"]["shroud_blade_inset_max_mm"] <= 1.35 * average_thickness


def test_closed_shroud_attachment_bridges_blade_tip_to_shroud_reference_surface():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    shroud = surfaces["blade_0_closed_shroud_attachment_surface"]
    pressure = surfaces["blade_0_pressure_surface"]

    phase_pitch = 0.0
    shroud_reference_loop = [
        _map_tip_s_q_to_xyz(point, defaults, phase_pitch)
        for point in shroud["v1_1_shroud_domain_samples"]["blade_tip_loop_s_q"]
    ]
    shroud_attachment_loop = [
        _map_tip_s_q_to_xyz(point, defaults, phase_pitch)
        for point in shroud["v1_1_shroud_domain_samples"]["shroud_attachment_loop_s_q"]
    ]
    blade_tip_loop = shroud["edge_samples"]["blade_tip_loop"]
    inset_distances = [
        math.dist(blade_point, shroud_point)
        for blade_point, shroud_point in zip(blade_tip_loop, shroud_reference_loop)
    ]
    attachment_widths = [
        math.dist(reference_point, attachment_point)
        for reference_point, attachment_point in zip(shroud_reference_loop, shroud_attachment_loop)
    ]

    assert shroud["uv_grid"][0] == blade_tip_loop
    assert shroud["uv_grid"][-1] == shroud_attachment_loop
    assert blade_tip_loop[0] == pressure["edge_samples"]["tip"][0]
    assert shroud["v1_1_tip_quality"]["construction"] == "curved_support_footprint_to_blade_shroud_attachment"
    assert shroud["v1_1_tip_quality"]["shroud_attachment_width_min_mm"] >= 0.55 * defaults["average_blade_thickness_mm"]
    assert min(attachment_widths) >= 0.55 * defaults["average_blade_thickness_mm"]
    assert min(inset_distances) >= 0.75 * defaults["shroud_blade_inset_mm"]
    assert max(inset_distances) <= 1.35 * defaults["shroud_blade_inset_mm"]
    assert shroud["v1_1_tip_quality"]["shroud_blade_inset_min_mm"] >= 0.75 * defaults["shroud_blade_inset_mm"]
    assert shroud["v1_1_tip_quality"]["shroud_blade_inset_max_mm"] <= 1.35 * defaults["shroud_blade_inset_mm"]


def test_closed_shroud_attachment_short_direction_is_curved_like_root_surface():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    shroud = surfaces["blade_0_closed_shroud_attachment_surface"]
    quality = shroud["v1_1_tip_quality"]

    assert quality["construction"] == "curved_support_footprint_to_blade_shroud_attachment"
    assert quality["short_direction_bulge_min_mm"] >= max(1.0, 0.08 * defaults["average_blade_thickness_mm"])
    assert _short_direction_bulge_min(shroud["uv_grid"]) >= max(1.0, 0.08 * defaults["average_blade_thickness_mm"])


def test_tip_topology_conflict_blocks_surface_generation():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1", facet_overrides={"shroud_topology": "closed"})
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    assert graph["surface_graph_status"] == "FAIL"
    assert graph["surfaces"] == []
    assert graph["transition_failures"]
    assert graph["transition_failures"][0]["reason"] == "v1_1_tip_topology_mode_conflict"
    assert graph["transition_failures"][0]["blocking"] is True


def _row_spread(row):
    points = row[:-1] if row and row[0] == row[-1] else row
    return max(
        math.dist(left, right)
        for left in points
        for right in points
    )


def _short_direction_bulge_min(grid):
    midpoint_row = grid[len(grid) // 2]
    start_row = grid[0]
    end_row = grid[-1]
    distances = [
        _distance_to_segment(midpoint, start, end)
        for midpoint, start, end in zip(midpoint_row[:-1], start_row[:-1], end_row[:-1])
        if math.dist(start, end) > 1.0e-9
    ]
    return min(distances) if distances else 0.0


def _distance_to_segment(point, start, end):
    segment = [end[index] - start[index] for index in range(3)]
    length_squared = sum(component * component for component in segment)
    if length_squared <= 1.0e-12:
        return math.dist(point, start)
    t = sum((point[index] - start[index]) * segment[index] for index in range(3)) / length_squared
    t = max(0.0, min(1.0, t))
    projection = [start[index] + t * segment[index] for index in range(3)]
    return math.dist(point, projection)
