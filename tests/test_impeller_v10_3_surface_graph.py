from __future__ import annotations

import sys
from pathlib import Path
import math

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from tests.impeller_v10_3_historical_fixture import historical_v10_3_open_runtime


def _graph() -> dict:
    runtime = historical_v10_3_open_runtime()
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    return metadata["surface_graph"]


def _surface(graph: dict, surface_id: str) -> dict:
    return next(surface for surface in graph["surfaces"] if surface["id"] == surface_id)


def _angle_span_deg(surface: dict) -> float:
    angles = []
    for row in surface["uv_grid"]:
        for point in row:
            angles.append(math.atan2(point[1], point[0]))
    angles.sort()
    if not angles:
        return 0.0
    largest_gap = 0.0
    for left, right in zip(angles, angles[1:]):
        largest_gap = max(largest_gap, right - left)
    largest_gap = max(largest_gap, angles[0] + 2.0 * math.pi - angles[-1])
    return math.degrees(2.0 * math.pi - largest_gap)


def _radius_z_extents(surface: dict) -> dict[str, float]:
    points = [point for row in surface["uv_grid"] for point in row]
    radii = [math.hypot(point[0], point[1]) for point in points]
    z_values = [point[2] for point in points]
    return {
        "r_min": min(radii),
        "r_max": max(radii),
        "z_min": min(z_values),
        "z_max": max(z_values),
    }


def test_open_preset_generates_v10_3_surface_graph():
    graph = _graph()
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    assert graph["geometry_version"] == "1.0"
    assert graph["geometry_patch_version"] == "1.0.3"
    assert (
        graph["transition_geometry_status"]
        == "topology_first_section_loop_blade_root_blend_surface_graph"
    )
    assert graph["surface_graph_status"] == "PASS"
    assert graph["section_loop_constructor_status"] == "PASS"
    assert graph["main_blade_count"] == 4
    assert graph["splitter_blade_count"] == 4
    assert graph["blade_surface"]["surface_count"] == 32
    assert graph["topology_graph"]["shared_edge_count"] > 0
    assert graph["topology_graph"]["max_shared_edge_gap_mm"] == 0.0
    assert "blade_0_pressure_surface" in surfaces
    assert "blade_0_suction_surface" in surfaces
    assert "blade_0_leading_edge_surface" in surfaces
    assert "blade_0_trailing_edge_surface" in surfaces
    assert "blade_0_tip_dome_surface" in surfaces
    assert any(
        surface.get("blade_index") == 0
        and surface.get("face_family") == "blade_root"
        and surface.get("display", {}).get("visible_by_default") is True
        for surface in graph["surfaces"]
    )


def test_open_preset_uses_v10_3_nurbs_carrier_math_not_radial_primitives():
    graph = _graph()
    pressure = _surface(graph, "blade_0_pressure_surface")
    suction = _surface(graph, "blade_0_suction_surface")
    hub = _surface(graph, "hub_support_surface")
    hub_extents = _radius_z_extents(hub)
    hub_profile = hub["profile_samples_rz"]

    assert graph["source_math_policy"] == "section_loop_first_nurbs_carrier_blade_faces_segmented_root_blends_open_tip_domes"
    assert pressure["source"]["section_loop_source"] == "v1_0_3_nurbs_carrier_section_lattice"
    assert _angle_span_deg(pressure) > 90.0
    assert _angle_span_deg(suction) > 90.0
    assert hub_extents["z_min"] <= 1.0
    assert hub_extents["z_max"] >= 110.0
    assert hub_extents["r_min"] < 160.0
    assert hub_extents["r_max"] > 550.0
    assert hub_profile[0]["r_mm"] == 150.0
    assert hub_profile[0]["z_mm"] == 400.0
    assert hub_profile[-1]["r_mm"] == 580.0
    assert hub_profile[-1]["z_mm"] == 0.0
    assert hub["source"]["geometry_rule"] == "v1_0_3_hub_support_from_nurbs_carrier_profile"


def test_open_preset_transition_components_have_mesh_and_wireframe():
    graph = _graph()
    transition_surfaces = [
        surface
        for surface in graph["surfaces"]
        if surface.get("face_family")
        in {
            "blade_leading_edge",
            "blade_trailing_edge",
            "blade_root",
            "blade_tip",
        }
        and surface.get("display", {}).get("visible_by_default", True) is True
    ]

    assert transition_surfaces
    for surface in transition_surfaces:
        assert surface.get("wireframe", {}).get("enabled") is True
        assert surface.get("mesh", {}).get("quad_count", 0) > 0
        assert surface.get("transition_quality", {}).get("foldover_count", 0) == 0


def test_open_tip_reference_surface_is_not_visible():
    graph = _graph()

    for surface in graph["surfaces"]:
        surface_id = str(surface.get("id", ""))
        role = str(surface.get("role", ""))
        if "tip_reference" in surface_id or role == "blade_tip_reference_surface":
            assert surface.get("display", {}).get("visible_by_default") is False


def test_v10_3_validation_counts_transition_surfaces_and_blocks_empty_graph():
    graph = _graph()
    report = build_geometry_validation_report(surface_graph=graph)
    summary = report["transition_validation_summary"]

    assert report["geometry_validation_status"] == "PASS"
    assert summary["transition_surface_count"] == 56
    assert summary["transition_surface_count_by_family"]["blade_root_to_hub"] == 32
    assert summary["transition_surface_count_by_family"]["blade_tip_dome"] == 8

    empty_report = build_geometry_validation_report(
        surface_graph={
            "transition_geometry_status": "topology_first_section_loop_blade_root_blend_surface_graph",
            "geometry_patch_version": "1.0.3",
            "surfaces": [],
        }
    )
    assert empty_report["geometry_validation_status"] == "FAIL"
    assert any(
        failure["reason"] == "v1_0_surface_graph_empty"
        for failure in empty_report["blocking_failures"]
    )
