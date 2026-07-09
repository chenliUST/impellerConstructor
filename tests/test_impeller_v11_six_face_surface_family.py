from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import (
    compile_impeller_runtime_preset,
    impeller_json_preset_ids,
)
from part_rule_synthesis.service import _bind_parameters
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.impeller_v10_surface_graph import build_v10_surface_graph
import part_rule_synthesis.impeller_v10_surface_graph as v10_surface_graph


def _graph(preset_id: str = "radial_open_reference_v1_1") -> dict[str, object]:
    runtime = compile_impeller_runtime_preset(preset_id)
    return build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )


def _v1_1_carrier(runtime: dict[str, object]) -> dict[str, object]:
    return {
        "geometry_patch_version": runtime["geometry_patch_version"],
        "resolved_blade_to_blade_loop_family_defaults": runtime["resolved_blade_to_blade_loop_family_defaults"],
    }


def test_v11_generates_six_named_face_families_per_open_blade():
    graph = _graph()

    assert graph["geometry_version"] == "1.1"
    assert graph["geometry_patch_version"] == "1.1.1"
    assert graph["surface_graph_status"] == "PASS"

    first_blade = [
        surface
        for surface in graph["surfaces"]
        if surface.get("blade_pair_index") == 0 and surface.get("blade_class") == "main"
    ]
    roles = {surface["role"] for surface in first_blade}
    assert {
        "blade_pressure",
        "blade_suction",
        "blade_leading_edge",
        "blade_trailing_edge",
        "root_to_hub_attachment",
        "open_tip_dome",
    }.issubset(roles)


def test_v11_surfaces_have_uv_grid_and_wireframe():
    graph = _graph()

    manufactured = [
        surface
        for surface in graph["surfaces"]
        if surface.get("source_kernel") == "v1_1_blade_to_blade_surface_family_kernel"
    ]
    assert manufactured
    for surface in manufactured:
        assert len(surface.get("uv_grid", [])) >= 5
        assert len(surface["uv_grid"][0]) >= 5
        assert surface["wireframe"]["enabled"] is True


def test_v11_open_reference_uses_promoted_dense_review_sampling_without_high_twist_catalog_dependency():
    graph = _graph("radial_open_reference_v1_1")
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    preset_ids = set(impeller_json_preset_ids())

    pressure = surfaces["blade_0_pressure_surface"]
    leading = surfaces["blade_0_leading_edge_surface"]
    tip_dome = surfaces["blade_0_open_tip_dome_surface"]
    tip_reference = surfaces["tip_reference_surface"]

    assert graph["surface_graph_status"] == "PASS"
    assert "radial_open_reference_v1_1" in preset_ids
    assert "radial_open_high_twist_thin_reference_v1_1" not in preset_ids
    assert len(pressure["uv_grid"]) >= 13
    assert len(pressure["uv_grid"][0]) >= 73
    assert pressure["mesh"]["u_count"] == len(pressure["uv_grid"])
    assert pressure["mesh"]["v_count"] == len(pressure["uv_grid"][0])
    assert pressure["mesh"]["quad_count"] >= 864
    assert len(pressure["control_net"]) >= 5
    assert len(pressure["control_net"][0]) >= 5

    assert len(leading["uv_grid"]) >= 13
    assert len(leading["uv_grid"][0]) >= 49
    assert len(tip_dome["uv_grid"]) >= 49
    assert len(tip_dome["uv_grid"][0]) >= 73

    assert tip_reference["source"]["profile_sample_count"] >= 73
    assert tip_reference["source"]["theta_sample_count"] >= 97
    assert len(tip_reference["uv_grid"]) >= 73
    assert len(tip_reference["uv_grid"][0]) >= 97


def test_v11_edge_surfaces_do_not_have_endpoint_segment_length_spikes():
    graph = _graph()

    edge_surfaces = [
        surface
        for surface in graph["surfaces"]
        if surface.get("role") in {"blade_leading_edge", "blade_trailing_edge"}
    ]

    assert edge_surfaces
    for surface in edge_surfaces:
        for row in surface["uv_grid"]:
            segment_lengths = [
                math.dist(row[index], row[index - 1])
                for index in range(1, len(row))
            ]
            median_length = sorted(segment_lengths)[len(segment_lengths) // 2]
            assert max(segment_lengths) <= 2.35 * median_length


def test_v11_hub_support_is_full_profile_revolve_surface():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    hub = next(surface for surface in graph["surfaces"] if surface["id"] == "hub_support_surface")

    assert hub["source"]["profile"] == "hub_profile_rz_mm"
    assert len(hub["uv_grid"]) >= len(defaults["hub_profile_rz_mm"])
    assert len(hub["uv_grid"][0]) >= 49

    mid_row = hub["uv_grid"][len(hub["uv_grid"]) // 2]
    assert mid_row[0] == mid_row[-1]
    unwrapped = []
    previous = None
    for point in mid_row:
        theta = math.atan2(point[1], point[0])
        if previous is not None:
            while theta < previous:
                theta += 2.0 * math.pi
        unwrapped.append(theta)
        previous = theta

    assert unwrapped[-1] - unwrapped[0] == pytest.approx(2.0 * math.pi, abs=0.03)


def test_v11_hub_is_explicit_solid_with_bottom_thickness_and_mounting_bore():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    parameters = runtime["parameters"]
    bottom_thickness = parameters["hub_bottom_thickness_mm"]["default"]
    bore_radius = parameters["mounting_bore_radius_mm"]["default"]

    required = {
        "hub_support_surface",
        "hub_top_annulus_surface",
        "hub_bottom_annulus_surface",
        "hub_bottom_outer_wall_surface",
        "mounting_bore_inner_wall_surface",
    }
    assert required.issubset(surfaces)

    hub = surfaces["hub_support_surface"]
    bottom = surfaces["hub_bottom_annulus_surface"]
    bore = surfaces["mounting_bore_inner_wall_surface"]
    hub_z_values = [point[2] for row in hub["uv_grid"] for point in row]
    bottom_z_values = {round(point[2], 6) for row in bottom["uv_grid"] for point in row}
    bore_radii = [
        math.hypot(point[0], point[1])
        for row in bore["uv_grid"]
        for point in row
    ]

    assert min(bottom_z_values) == pytest.approx(min(hub_z_values) - bottom_thickness, abs=1e-6)
    assert max(bottom_z_values) == pytest.approx(min(hub_z_values) - bottom_thickness, abs=1e-6)
    assert min(bore_radii) == pytest.approx(bore_radius, abs=1e-6)
    assert max(bore_radii) == pytest.approx(bore_radius, abs=1e-6)
    assert bore["v1_1_hub_solid_quality"]["mounting_bore_radius_mm"] == pytest.approx(bore_radius)


def test_v11_surface_display_policy_uses_green_for_hub_pressure_suction_and_yellow_for_other_faces():
    graph = _graph()
    green_roles = {"hub_support", "blade_pressure", "blade_suction"}
    yellow_roles = {
        "blade_leading_edge",
        "blade_trailing_edge",
        "root_to_hub_attachment",
        "open_tip_dome",
        "mounting_bore",
    }

    for surface in graph["surfaces"]:
        role = surface.get("role")
        color = surface.get("display", {}).get("color")
        if role in green_roles:
            assert color == "#6f9b85"
        if role in yellow_roles:
            assert color == "#facc15"
        assert surface["wireframe"]["enabled"] is True


def test_v11_named_boundary_curves_use_points_field():
    graph = _graph()

    curves = graph["named_boundary_curves"]
    assert curves
    first_curve = curves[0]
    assert first_curve["points"]
    assert len(first_curve["points"]) >= 2
    assert first_curve["points_xyz"]


def test_v10_surface_graph_routes_explicit_v1_1_request():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v10_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        geometry_version="1.1",
        resolved_attachment_defaults=_v1_1_carrier(runtime),
    )

    assert graph["geometry_version"] == "1.1"
    assert graph["geometry_patch_version"] == "1.1.1"
    assert graph["surface_graph_status"] == "PASS"
    assert "open_tip_dome" in {surface["role"] for surface in graph["surfaces"]}


def test_v10_surface_graph_without_explicit_v1_1_request_uses_v10_legacy_path(monkeypatch):
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = _bind_parameters(runtime, {})
    legacy_called = {"axisymmetric_called": False}

    def _fake_axisymmetric_builder(*_args, **_kwargs):
        legacy_called["axisymmetric_called"] = True
        return {
            "surface_graph": {"surfaces": [], "transition_failures": []},
            "edges": [],
            "boundary_curves": {},
            "named_boundary_curves": [],
            "construction_lines": {},
            "sampled_blades": [],
            "blade_surface": {},
            "hub_surface": {},
            "cad_features": [],
            "validity": {},
        }

    monkeypatch.setattr(
        v10_surface_graph,
        "build_axisymmetric_throughflow_nurbs_geometry",
        _fake_axisymmetric_builder,
    )
    graph = build_v10_surface_graph(
        parameters,
        runtime["facets"],
        resolved_attachment_defaults={},
    )

    assert legacy_called["axisymmetric_called"] is True
    assert graph["geometry_version"] == "1.0"
    assert graph["geometry_patch_version"] == "1.0.2"
    assert graph["surface_graph_status"] == "FAIL"


def test_v11_profile_override_changes_surface_family_uv_grid():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    baseline = build_v10_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        geometry_version="1.1",
        resolved_attachment_defaults=_v1_1_carrier(runtime),
    )
    overridden = build_v10_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        profile_overrides={
            "hub_profile": {
                "control_points": [
                    [150, 400],
                    [170, 280],
                    [240, 170],
                    [360, 70],
                    [500, 18],
                    [580, 0],
                ]
            }
        },
        geometry_version="1.1",
        resolved_attachment_defaults=_v1_1_carrier(runtime),
    )

    baseline_surface = next(
        surface
        for surface in baseline["surfaces"]
        if surface.get("role") == "blade_pressure" and surface.get("blade_class") == "main"
    )
    overridden_surface = next(
        surface
        for surface in overridden["surfaces"]
        if surface.get("role") == "blade_pressure" and surface.get("blade_class") == "main"
    )

    assert overridden["surface_graph_status"] == "PASS"
    assert overridden_surface["uv_grid"] != baseline_surface["uv_grid"]
