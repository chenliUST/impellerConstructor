from __future__ import annotations

from pathlib import Path

import pytest

from part_rule_synthesis.service import RuleSynthesisService


def test_impeller_v09_open_workflow_exports_only_after_geometry_validation_passes(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    engine = service.synthesize("impeller", "radial_open_reference_v0_9")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]
    report = manifest["geometry_validation_report"]

    assert manifest["dsl_version"] == "0.9"
    assert manifest["geometry_version"] == "0.9"
    assert manifest["transition_geometry_status"] == "validated_transition_surface_graph"
    assert manifest["mesh_strategy"] == "validated_transition_aware_surface_mesh"
    assert manifest["geometry_validation_status"] == "PASS"
    assert report["geometry_validation_status"] == "PASS"
    assert report["kernel_capability_matrix_id"] == "impeller_v0_9_kernel_capabilities"
    assert report["transition_validation_summary"]["transition_surface_count"] > 0
    assert not report["blocking_failures"]
    assert graph["transition_geometry_status"] == "validated_transition_surface_graph"

    surface_ids = {surface["id"] for surface in graph["surfaces"]}
    assert "blade_0_pressure_root_transition_surface" in surface_ids
    assert "blade_0_suction_root_transition_surface" in surface_ids
    assert "blade_0_root_transition_surface" not in surface_ids

    assert manifest["export_strategy"]["mode"] == "validated_transition_bounded_brep"
    assert set(manifest["exports"]) == {"step", "stl", "obj", "manifest"}
    assert manifest["export_manifests"]["step"]["export_exactness"] == "validated_bounded_unsewn_review_brep_step"
    assert manifest["export_manifests"]["step"]["trim_excluded_cell_count"] > 0
    assert manifest["export_manifests"]["step"]["trim_split_face_count"] > 0
    assert manifest["export_manifests"]["stl"]["mesh_type"] == "validated_transition_aware_surface_mesh"
    assert manifest["export_manifests"]["stl"]["trimmed_cell_count"] > 0
    assert any(
        region["edge_family"] == "blade_root_to_hub"
        for region in manifest["export_manifests"]["stl"]["transition_regions"]
    )


def test_impeller_v09_infeasible_transition_validation_fails_before_export(tmp_path: Path):
    model_output_root = tmp_path / "Model Output"
    service = RuleSynthesisService(tmp_path / "runs", model_output_root=model_output_root)

    engine = service.synthesize("impeller", "radial_open_reference_v0_9")
    with pytest.raises(RuntimeError, match="geometry validation.*blade_root_to_hub.*radius_exceeds_local_feasible_limit"):
        service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "fillet",
                    "radius_mm": 1000.0,
                },
            },
        )

    assert not list(model_output_root.glob("*.manifest.json"))
    assert not list(model_output_root.glob("*.step"))
