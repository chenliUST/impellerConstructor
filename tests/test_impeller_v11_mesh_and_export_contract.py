from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_mesh_manifest import build_surface_mesh_manifest
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph
from part_rule_synthesis.service import RuleSynthesisService


def _surface(graph: dict[str, Any], surface_id: str) -> dict[str, Any]:
    return next(surface for surface in graph["surfaces"] if surface["id"] == surface_id)


def _v11_graph() -> dict[str, Any]:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    return build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        {
            **runtime["resolved_blade_to_blade_loop_family_defaults"],
            "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
        },
    )


def _visible_manufactured_surface_ids(graph: dict[str, Any]) -> set[str]:
    return {
        str(surface["id"])
        for surface in graph["surfaces"]
        if _is_visible_manufactured_surface(surface)
    }


def _is_visible_manufactured_surface(surface: dict[str, Any]) -> bool:
    display = surface.get("display", {})
    flags = surface.get("surface_flags", {})
    if surface.get("role") == "open_tip_reference":
        return False
    if surface.get("reference_only") or display.get("reference_only") or flags.get("reference_only"):
        return False
    if display.get("visible_by_default") is False:
        return False
    return True


def _is_rectangular_grid(grid: Any) -> bool:
    if not isinstance(grid, list) or len(grid) < 2:
        return False
    if not isinstance(grid[0], list) or len(grid[0]) < 2:
        return False
    column_count = len(grid[0])
    return all(isinstance(row, list) and len(row) == column_count for row in grid)


def test_v11_service_smoke_generates_validated_open_manifest(tmp_path: Path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = {
        name: spec["default"]
        for name, spec in service.engines[engine.engine_id]["parameters"].items()
    }

    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest

    assert manifest["geometry_version"] == "1.1"
    assert manifest["geometry_patch_version"] == "1.1.2"
    assert manifest["geometry_validation_status"] == "PASS"
    assert (
        manifest["transition_geometry_status"]
        == "topology_first_blade_to_blade_5_loop_surface_family_graph"
    )
    assert manifest["mesh_strategy"] == "v1_1_1_all_surface_uv_grid_mesh"
    assert "obj" in manifest["exports"]
    assert "manifest" in manifest["exports"]
    assert Path(manifest["exports"]["obj"]).is_file()
    assert Path(manifest["exports"]["manifest"]).is_file()


def test_v11_service_accepts_frontend_segment_control_point_edit(tmp_path: Path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = {
        name: spec["default"]
        for name, spec in service.engines[engine.engine_id]["parameters"].items()
    }
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    pressure_controls = copy.deepcopy(
        family["blades"][0]["loops"][0]["segments"]["pressure_side"]["control_points_s_q"]
    )
    pressure_controls[len(pressure_controls) // 2][1] += 1.0

    run = service.instantiate(
        engine.engine_id,
        parameters,
        blade_to_blade_loop_family_overrides={
            "blade_to_blade_loop_family": {
                "segments": {
                    "pressure_side": {"control_points": pressure_controls},
                },
            },
        },
    )

    assert run.manifest["geometry_validation_status"] == "PASS"
    assert run.manifest["geometry_version"] == "1.1"
    assert (
        run.manifest["transition_geometry_status"]
        == "topology_first_blade_to_blade_5_loop_surface_family_graph"
    )
    assert "blade_to_blade_loop_family_overrides" in run.manifest
    assert Path(run.manifest["exports"]["obj"]).is_file()


def test_v11_visible_manufactured_surfaces_carry_all_surface_mesh_metadata():
    graph = _v11_graph()
    surface_ids = _visible_manufactured_surface_ids(graph)

    assert "hub_support_surface" in surface_ids
    assert "hub_top_annulus_surface" in surface_ids
    assert "hub_bottom_annulus_surface" in surface_ids
    assert "hub_bottom_outer_wall_surface" in surface_ids
    assert "mounting_bore_inner_wall_surface" in surface_ids
    assert "tip_reference_surface" not in surface_ids

    for surface in graph["surfaces"]:
        if not _is_visible_manufactured_surface(surface):
            continue
        assert _is_rectangular_grid(surface.get("uv_grid")), surface["id"]
        assert surface.get("wireframe", {}).get("enabled") is True, surface["id"]
        assert (
            surface.get("mesh", {}).get("strategy")
            == "v1_1_1_all_surface_uv_grid_mesh"
        ), surface["id"]
        assert surface.get("mesh", {}).get("quad_count", 0) > 0, surface["id"]
        assert surface.get("display", {}).get("color"), surface["id"]
        assert surface.get("display", {}).get("wire_color"), surface["id"]
        assert (
            surface.get("source_kernel")
            == "v1_1_blade_to_blade_surface_family_kernel"
        ), surface["id"]


def test_v11_cfd_surface_mesh_manifest_covers_all_visible_manufactured_surfaces(tmp_path: Path):
    graph = _v11_graph()
    expected_surface_ids = _visible_manufactured_surface_ids(graph)

    manifest = build_surface_mesh_manifest(graph, view_id="cfd_full_360")
    patch_surface_ids = {
        region["surface_graph_id"]
        for region in manifest["patch_regions"]
        if region["triangle_count"] > 0
    }

    assert expected_surface_ids <= patch_surface_ids
    assert "mounting_bore_inner_wall_surface" in patch_surface_ids
    assert "hub_top_annulus_surface" in patch_surface_ids
    assert "hub_bottom_annulus_surface" in patch_surface_ids
    assert "hub_bottom_outer_wall_surface" in patch_surface_ids
    assert "tip_reference_surface" not in patch_surface_ids

    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = {
        name: spec["default"]
        for name, spec in service.engines[engine.engine_id]["parameters"].items()
    }
    run = service.instantiate(engine.engine_id, parameters)
    service_mesh = run.manifest["simulation_manifests"]["cfd_surface_mesh"]
    service_patch_surface_ids = {
        region["surface_graph_id"]
        for region in service_mesh["patch_regions"]
        if region["triangle_count"] > 0
    }

    assert expected_surface_ids <= service_patch_surface_ids
    assert "mounting_bore_inner_wall_surface" in service_patch_surface_ids
    assert "tip_reference_surface" not in service_patch_surface_ids


def test_v11_validation_rejects_surface_without_shared_uv_wire():
    graph = _v11_graph()
    graph["surfaces"][0]["wireframe"]["enabled"] = False

    failures = validate_v11_surface_graph(graph)

    assert any(failure["reason"] == "v1_1_surface_boundary_not_shared" for failure in failures)


def test_v11_unusable_manufactured_uv_grid_fails_shared_boundary_uv_contract():
    graph = _v11_graph()
    _surface(graph, "blade_0_pressure_surface")["uv_grid"] = []

    failures = validate_v11_surface_graph(graph)
    report = build_geometry_validation_report(surface_graph=graph)

    assert any(failure["reason"] == "v1_1_surface_loft_foldover" for failure in failures)
    assert next(
        check for check in report["checks"] if check["check_id"] == "v1_1_shared_boundary_uv_contract"
    )["status"] == "FAIL"


def test_v11_closed_material_domain_failure_blocks_geometry_validation():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        {
            **runtime["resolved_blade_to_blade_loop_family_defaults"],
            "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
        },
    )
    _surface(graph, "blade_0_pressure_surface")["v1_1_span_domain_quality"]["status"] = "FAIL"
    _surface(graph, "blade_0_pressure_surface")["v1_1_span_domain_quality"]["material_domain_status"] = "FAIL"

    failures = validate_v11_surface_graph(graph)
    report = build_geometry_validation_report(surface_graph=graph)

    assert any(failure["reason"] == "v1_1_blade_loop_material_domain_failed" for failure in failures)
    assert report["geometry_validation_status"] == "FAIL"


def test_v11_helper_reference_surfaces_can_skip_wireframe_and_uv_contracts():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")

    wireframe_graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        {
            **runtime["resolved_blade_to_blade_loop_family_defaults"],
            "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
        },
    )
    _surface(wireframe_graph, "hub_support_surface").pop("wireframe")

    wireframe_failures = validate_v11_surface_graph(wireframe_graph)
    wireframe_report = build_geometry_validation_report(surface_graph=wireframe_graph)

    assert not any(
        failure["reason"] in {"v1_1_surface_boundary_not_shared", "v1_1_surface_loft_foldover"}
        for failure in wireframe_failures
    )
    assert wireframe_report["geometry_validation_status"] == "PASS"

    uv_grid_graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        {
            **runtime["resolved_blade_to_blade_loop_family_defaults"],
            "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
        },
    )
    _surface(uv_grid_graph, "tip_reference_surface")["uv_grid"] = []

    uv_grid_failures = validate_v11_surface_graph(uv_grid_graph)
    uv_grid_report = build_geometry_validation_report(surface_graph=uv_grid_graph)

    assert not any(
        failure["reason"] in {"v1_1_surface_boundary_not_shared", "v1_1_surface_loft_foldover"}
        for failure in uv_grid_failures
    )
    assert uv_grid_report["geometry_validation_status"] == "PASS"


def test_v11_transition_failures_are_reported_once_in_geometry_validation_report():
    graph = _v11_graph()
    graph["transition_failures"] = [
        {
            "reason": "v1_1_surface_boundary_not_shared",
            "surface_graph_id": "transition_surface",
            "stage": "v1_1_surface_family",
            "edge_family": "blade_pressure",
            "blade_index": 0,
        }
    ]

    report = build_geometry_validation_report(surface_graph=graph)
    reasons = [failure["reason"] for failure in report["blocking_failures"]]

    assert reasons.count("v1_1_surface_boundary_not_shared") == 1
