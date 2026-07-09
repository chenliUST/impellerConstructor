from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def _open_runtime() -> dict:
    return compile_impeller_runtime_preset("radial_open_reference_v1_0")


def _open_graph() -> dict:
    runtime = _open_runtime()
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]


def _surfaces_by_id(graph: dict) -> dict[str, dict]:
    return {surface["id"]: surface for surface in graph["surfaces"]}


def _dist(point: list[float], other: list[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(point, other)))


def _midpoint(point: list[float], other: list[float]) -> list[float]:
    return [(float(a) + float(b)) * 0.5 for a, b in zip(point, other)]


def _max_section_bulge(surface: dict) -> float:
    max_bulge = 0.0
    for section in surface["uv_grid"]:
        if len(section) < 3:
            continue
        chord_mid = _midpoint(section[0], section[-1])
        midpoint = section[len(section) // 2]
        max_bulge = max(max_bulge, _dist(midpoint, chord_mid))
    return max_bulge


def test_v10_open_tip_reference_is_construction_only_and_hidden_by_default():
    runtime = _open_runtime()
    graph = _open_graph()
    assert "blade_tip_support_surface" in runtime["display_policy"]["hide_surfaces"]
    for surface in graph["surfaces"]:
        surface_id = str(surface.get("id", ""))
        role = str(surface.get("role", ""))
        if "tip_reference" in surface_id or role in {"construction_support_only", "reference_only"}:
            assert surface.get("display", {}).get("visible_by_default") is False


def test_v10_outer_hub_chamfer_is_deferred_while_bore_chamfers_remain():
    runtime = _open_runtime()
    graph = _open_graph()
    surfaces = _surfaces_by_id(graph)

    assert "hub_chamfer_bottom_outer_surface" not in surfaces
    assert "hub_chamfer_top_cap_surface" not in surfaces
    assert "mounting_bore_inner_wall_surface" in surfaces
    assert "mounting_bore_top_edge_surface" in surfaces
    assert "mounting_bore_bottom_edge_surface" in surfaces

    assert runtime["transition_policy_defaults"]["hub_bottom_outer.default"]["enabled"] is False
    assert runtime["transition_policy_defaults"]["hub_top_outer.default"]["enabled"] is False
    assert runtime["solid_features"]["hub_chamfers"]["applies_to"] == [
        "mounting_bore_top_edge",
        "mounting_bore_bottom_edge",
    ]


def test_v10_blade_edge_patches_are_curved_multisample_surfaces():
    surfaces = _surfaces_by_id(_open_graph())

    for surface_id in ["blade_0_leading_edge_surface", "blade_0_trailing_edge_surface"]:
        surface = surfaces[surface_id]
        quality = surface["transition_quality"]
        assert quality["foldover_count"] == 0
        assert quality["min_segment_sample_count"] >= 41
        assert quality["max_segment_sample_count"] >= quality["min_segment_sample_count"]
        assert surface["wireframe"]["enabled"] is True
        assert surface["mesh"]["quad_count"] > 0
        assert len(surface["uv_grid"]) >= 40
        assert len(surface["uv_grid"][0]) >= 40

    tip = surfaces["blade_0_tip_dome_surface"]
    assert tip["transition_quality"]["foldover_count"] == 0
    assert tip["transition_quality"]["tip_dome_material_side_valid"] is True
    assert tip["wireframe"]["enabled"] is True
    assert tip["mesh"]["quad_count"] > 0
    assert _max_section_bulge(tip) >= 1.0


def test_v10_root_face_is_annular_hub_to_blade_boss_surface():
    graph = _open_graph()
    surfaces = _surfaces_by_id(graph)
    root = surfaces["blade_0_root_annular_surface"]

    assert root["role"] == "root_annular_surface"
    assert root["transition_quality"]["continuity_claim"] == "G2_TARGET_REVIEW_GRADE"
    assert root["transition_quality"]["short_direction_sample_count"] >= 21
    assert root["v1_0_4_root_quality"]["status"] == "PASS"
    assert len(root["uv_grid"]) >= 40
    assert len(root["uv_grid"][0]) >= 9
    assert len(root["edge_samples"]["hub_outer_loop"]) == len(root["edge_samples"]["blade_inner_loop"])
    assert root["display"]["inspection_class"] == "root_to_hub_blend"
    assert root["display"]["color"] == "#ff00cc"
    assert root["display"]["wire_color"] == "#fff200"
    assert root["display"]["aggregate_surface"] is True
    assert root["display"]["visible_by_default"] is False

    components = [
        surface
        for surface in graph["surfaces"]
        if surface.get("component_of") == "blade_0_root_annular_surface"
    ]
    assert {component["component_segment"] for component in components} == {
        "pressure_side",
        "leading_edge",
        "suction_side",
        "trailing_edge",
    }
    for component in components:
        assert component["display"]["visible_by_default"] is True
        assert component["transition_quality"]["continuity_claim"] == "G2_TARGET_REVIEW_GRADE"
        assert component["transition_quality"]["foldover_count"] == 0
        assert component["wireframe"]["enabled"] is True
        assert component["mesh"]["quad_count"] > 0


def test_v10_blade_transition_policy_defaults_claim_g2():
    runtime = _open_runtime()
    policies = runtime["transition_policy_defaults"]

    for policy_id in [
        "blade_leading_edge.default",
        "blade_trailing_edge.default",
        "blade_root_to_hub.default",
        "blade_tip_or_shroud.default",
    ]:
        assert policies[policy_id]["continuity"] == "G2"
