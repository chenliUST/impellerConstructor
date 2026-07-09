from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph, _map_root_s_q_to_xyz


def test_root_attachment_width_lift_are_bounded_by_half_thickness_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    roots = [
        surface for surface in graph["surfaces"] if surface.get("role") == "root_to_hub_attachment"
    ]

    assert roots
    average_thickness = runtime["resolved_blade_to_blade_loop_family_defaults"]["average_blade_thickness_mm"]
    for root in roots:
        quality = root["v1_1_root_quality"]
        assert quality["status"] == "PASS"
        assert 0.55 * average_thickness <= quality["root_width_min_mm"] <= 1.5 * average_thickness
        assert 0.75 * average_thickness <= quality["root_lift_min_mm"] <= 1.35 * average_thickness
        assert quality["foldover_count"] == 0
        assert quality["material_side_status"] == "PASS"


def test_root_attachment_outer_loop_uses_closed_footprint_outward_offset():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    roots = [
        surface for surface in graph["surfaces"] if surface.get("role") == "root_to_hub_attachment"
    ]

    assert roots
    for root in roots:
        quality = root["v1_1_root_quality"]
        assert quality["root_offset_method"] == "closed_loop_metric_outward_normal_offset"
        assert quality["root_outer_offset_side_failures"] == 0
        assert quality["root_offset_width_ratio_min"] >= 0.65
        assert quality["root_offset_width_ratio_max"] <= 1.35


def test_open_reference_root_attachment_inner_loop_is_lifted_blade_foot_not_hub_loop():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    root = surfaces["blade_0_root_attachment_surface"]
    pressure = surfaces["blade_0_pressure_surface"]

    phase_pitch = 0.0
    hub_inner_loop = [
        _map_root_s_q_to_xyz(point, defaults, phase_pitch)
        for point in root["v1_1_root_domain_samples"]["blade_inner_loop_s_q"]
    ]
    blade_inner_loop = root["edge_samples"]["blade_inner_loop"]
    blade_lift = [
        math.dist(blade_point, hub_point)
        for blade_point, hub_point in zip(blade_inner_loop, hub_inner_loop)
    ]

    assert root["uv_grid"][-1] == blade_inner_loop
    assert blade_inner_loop[0] == pressure["edge_samples"]["root"][0]
    assert min(blade_lift) >= 0.75 * defaults["average_blade_thickness_mm"]
    assert max(blade_lift) <= 1.35 * defaults["average_blade_thickness_mm"]
    assert root["v1_1_root_quality"]["root_blade_lift_min_mm"] >= 0.75 * defaults["average_blade_thickness_mm"]
    assert root["v1_1_root_quality"]["root_blade_lift_max_mm"] <= 1.35 * defaults["average_blade_thickness_mm"]


def test_root_attachment_short_direction_is_curved_not_a_chamfer_plane():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        defaults,
    )
    root = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_attachment_surface")
    quality = root["v1_1_root_quality"]

    assert quality["construction"] == "curved_support_footprint_to_blade_root_attachment"
    assert quality["short_direction_bulge_min_mm"] >= max(1.0, 0.08 * defaults["average_blade_thickness_mm"])
    assert _short_direction_bulge_min(root["uv_grid"]) >= max(1.0, 0.08 * defaults["average_blade_thickness_mm"])


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
