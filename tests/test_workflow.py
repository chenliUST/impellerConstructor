from pathlib import Path
import struct

from fastapi.testclient import TestClient
import pytest

from part_rule_synthesis.api import app, create_app
from part_rule_synthesis.service import RuleSynthesisService


V05_HUB_CONTROL_POINTS = [
    [150.0, 400.0],
    [170.0, 250.0],
    [220.0, 150.0],
    [330.0, 50.0],
    [480.0, 10.0],
    [580.0, 0.0],
]

V05_TIP_CONTROL_POINTS = [
    [230.0, 401.0],
    [250.0, 270.0],
    [310.0, 170.0],
    [400.0, 90.0],
    [490.0, 50.0],
    [581.0, 30.0],
]


def test_rotor_and_ngv_rule_engines_export_and_handle_feedback(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    rotor = service.synthesize("turbine_rotor")
    ngv = service.synthesize("ngv_ring")

    rotor_run = service.instantiate(rotor.engine_id, {"blade_count": 18, "hub_radius_mm": 18.0})
    ngv_run = service.instantiate(ngv.engine_id, {"vane_count": 21, "inner_radius_mm": 34.0})

    assert rotor_run.manifest["part_family"] == "turbine_rotor"
    assert rotor_run.manifest["exports"]["step"].endswith(".step")
    assert rotor_run.manifest["validation"]["status"] == "PASS"
    assert rotor_run.manifest["geometry"]["airfoil"]["authority"] == "inferred"
    assert rotor_run.manifest["geometry"]["airfoil"]["curve"]["degree"] == 3
    assert rotor_run.manifest["geometry"]["airfoil"]["curve"]["control_points"]
    assert rotor_run.manifest["operation_graph_hash"] == service.instantiate(
        rotor.engine_id, {"blade_count": 18, "hub_radius_mm": 18.0}
    ).manifest["operation_graph_hash"]

    assert ngv_run.manifest["part_family"] == "ngv_ring"
    assert "vane_bridges_inner_outer_rings" in ngv_run.manifest["validation"]["checks"]

    issue = service.ingest_feedback(
        rotor_run.run_id,
        "human",
        "叶片没有正确长在轮毂上",
        affected_feature="blade_root",
    )
    patch = service.propose_patch(issue.issue_id)
    assert issue.classification == "rule_patch"
    assert issue.expected_relation == "embedded_contact(blade_root, hub.outer_surface)"
    assert patch.patch_type == "rule_patch"
    assert "embedded_contact" in patch.dsl_diff

    gap = service.ingest_feedback(
        rotor_run.run_id,
        "human",
        "需要燕尾榫叶根，但是当前primitive无法表达",
    )
    gap_patch = service.propose_patch(gap.issue_id)
    assert gap.classification == "primitive_gap"
    assert gap_patch.patch_type == "primitive_gap"
    assert gap_patch.approval_required is True


def test_api_first_service_exposes_synthesis_instantiation_and_feedback(tmp_path: Path):
    assert app.title == "Part Rule Synthesis"

    client = TestClient(create_app(tmp_path))

    response = client.post("/api/rule-engines/synthesize", json={"part_family_id": "turbine_rotor"})
    assert response.status_code == 200
    engine_id = response.json()["engine_id"]

    run_response = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"blade_count": 18, "hub_radius_mm": 18.0}},
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    feedback_response = client.post(
        f"/api/model-runs/{run_id}/feedback",
        json={
            "source": "human",
            "raw_feedback": "blade root only touches the hub surface",
            "affected_feature": "blade_root",
        },
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json()["classification"] == "rule_patch"

    patch_response = client.post(f"/api/feedback/{feedback_response.json()['issue_id']}/propose-patch")
    assert patch_response.status_code == 200
    assert patch_response.json()["patch_type"] == "rule_patch"

    assert client.get(f"/api/model-runs/{run_id}/exports/step").status_code == 200
    assert client.get(f"/api/model-runs/{run_id}/exports/stl").status_code == 200

    patch_id = patch_response.json()["patch_id"]
    validate_response = client.post(f"/api/rule-patches/{patch_id}/validate")
    assert validate_response.status_code == 200
    assert validate_response.json()["status"] == "PASS"

    approve_response = client.post(f"/api/rule-patches/{patch_id}/approve")
    assert approve_response.status_code == 200
    assert approve_response.json()["approval_status"] == "approved"


def test_api_v06_export_route_serves_model_output_files_with_filenames(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_response = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference_v0_6"},
    )
    assert engine_response.status_code == 200

    run_response = client.post(
        f"/api/rule-engines/{engine_response.json()['engine_id']}/instantiate",
        json={"parameters": {}},
    )
    assert run_response.status_code == 200
    manifest = run_response.json()["manifest"]

    for export_format in ["step", "stl", "mesh_step", "manifest"]:
        export_response = client.get(f"/api/model-runs/{manifest['run_id']}/exports/{export_format}")

        assert export_response.status_code == 200
        assert Path(manifest["exports"][export_format]).name in export_response.headers["content-disposition"]


def test_api_export_route_returns_404_when_manifest_file_is_missing(tmp_path: Path):
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    engine_response = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference_v0_6"},
    )
    assert engine_response.status_code == 200

    run_response = client.post(
        f"/api/rule-engines/{engine_response.json()['engine_id']}/instantiate",
        json={"parameters": {}},
    )
    assert run_response.status_code == 200
    manifest = run_response.json()["manifest"]
    Path(manifest["exports"]["step"]).unlink()

    export_response = client.get(f"/api/model-runs/{manifest['run_id']}/exports/step")

    assert export_response.status_code == 404
    assert export_response.json()["detail"] == "export file missing"


def test_impeller_interactive_instantiation_writes_real_cad_exports(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "axisymmetric_nurbs_open_throughflow_study")
    run = service.instantiate(engine.engine_id, {})

    assert run.manifest["export_strategy"] == {
        "mode": "cadquery_sync",
        "cad_exports": "completed",
        "reason": "impeller exports are generated as analysis-review STEP/STL files",
    }
    assert run.manifest["geometry"]["surface_graph"]["surfaces"]
    step_path = Path(run.manifest["exports"]["step"])
    stl_path = Path(run.manifest["exports"]["stl"])
    assert step_path.stat().st_size > 4096
    assert stl_path.stat().st_size > 4096
    step_text = step_path.read_text(encoding="utf-8", errors="ignore")
    stl_bytes = stl_path.read_bytes()
    assert "CARTESIAN_POINT" in step_text
    assert "exact CAD export deferred" not in step_text
    triangle_count = struct.unpack("<I", stl_bytes[80:84])[0]
    assert triangle_count > 0
    assert len(stl_bytes) == 84 + triangle_count * 50


def test_impeller_cad_exports_follow_profile_overrides(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "axisymmetric_nurbs_open_throughflow_study")
    baseline = service.instantiate(engine.engine_id, {"blade_count": 3})
    hub = baseline.manifest["geometry_kernel"]["meridional_profiles"]["hub"]
    tip = baseline.manifest["geometry_kernel"]["meridional_profiles"]["tip_or_shroud"]
    edited_tip = {
        **tip,
        "control_points": [[point[0], point[1] + 42.0] for point in tip["control_points"]],
    }

    changed = service.instantiate(
        engine.engine_id,
        {"blade_count": 3},
        profile_overrides={"hub_profile": hub, "tip_or_shroud_profile": edited_tip},
    )

    baseline_bounds = _binary_stl_bounds(Path(baseline.manifest["exports"]["stl"]))
    changed_bounds = _binary_stl_bounds(Path(changed.manifest["exports"]["stl"]))
    assert changed_bounds["z_max"] > baseline_bounds["z_max"] + 30.0


def test_impeller_v05_exports_are_surface_graph_faithful_with_region_provenance(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    for preset_id in ["radial_open_reference_v0_5", "radial_closed_reference_v0_5"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest
        surface_graph = manifest["geometry"]["surface_graph"]
        surface_ids = {
            surface["id"]
            for surface in surface_graph["surfaces"]
            if len(surface.get("uv_grid", [])) >= 2 and len(surface.get("uv_grid", [[]])[0]) >= 2
        }
        stl_manifest = manifest["export_manifests"]["stl"]
        step_manifest = manifest["export_manifests"]["step"]
        first_blade = manifest["geometry"]["sampled_blades"][0]

        assert manifest["export_strategy"] == {
            "mode": "surface_graph_faithful",
            "cad_exports": "completed",
            "source": "geometry.surface_graph",
            "view": "cad_review_360",
            "reason": "STL/STEP are generated from selected surface_graph uv_grid samples",
        }
        assert manifest["parameters"]["blade_count"] == 12
        assert manifest["geometry_kernel"]["meridional_profiles"]["hub"]["control_points"] == V05_HUB_CONTROL_POINTS
        assert manifest["geometry_kernel"]["meridional_profiles"]["tip_or_shroud"]["control_points"] == V05_TIP_CONTROL_POINTS
        assert _max_line_deviation(first_blade["leading_edge_boundary"]) <= 2.0e-6
        assert _max_line_deviation(first_blade["trailing_edge_boundary"]) <= 2.0e-6
        assert stl_manifest["source"] == "surface_graph"
        assert stl_manifest["export_exactness"] == "surface_graph_sampled_mesh"
        assert stl_manifest["surface_count"] == len(surface_ids)
        assert set(stl_manifest["included_surface_ids"]) == surface_ids
        assert stl_manifest["triangle_count"] > 0
        assert {region["surface_graph_id"] for region in stl_manifest["triangle_regions"]} == surface_ids
        assert any(region["role"] == "blade_leading_edge_closure" for region in stl_manifest["triangle_regions"])
        assert any(region["role"] == "blade_tip_closure" for region in stl_manifest["triangle_regions"])
        assert step_manifest["source"] == "surface_graph"
        assert step_manifest["export_exactness"] == "surface_graph_mesh_step"
        assert step_manifest["step_representation"] == "ap242_triangulated_face_set"
        assert step_manifest["vertex_count"] > 0
        assert step_manifest["face_count"] == stl_manifest["triangle_count"]
        assert step_manifest["face_regions"] == stl_manifest["triangle_regions"]
        assert Path(manifest["exports"]["stl"]).stat().st_size > 4096
        assert Path(manifest["exports"]["step"]).stat().st_size > 4096


def test_impeller_v06_exports_brep_step_and_model_output_files(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_6")

    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["dsl_version"] == "0.6"
    assert "edge_families" not in manifest["geometry"]
    assert "transition_policies" not in manifest["geometry"]
    assert "edge_families" not in manifest["geometry_kernel"]
    assert "transition_policies" not in manifest["geometry_kernel"]
    assert manifest["export_strategy"]["mode"] == "surface_graph_brep"
    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["export_exactness"] == "surface_graph_support_face_brep_step"
    assert step_manifest["target_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert step_manifest["limitations"] == [
        "initial_faces_are_unsewn",
        "trim_loops_not_consumed",
        "cad_edge_wires_not_consumed",
    ]
    assert manifest["export_manifests"]["mesh_step"]["export_exactness"] == "surface_graph_mesh_step"
    assert manifest["export_manifests"]["stl"]["export_exactness"] == "surface_graph_sampled_mesh"
    assert manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"] > 0

    step_path = Path(manifest["exports"]["step"])
    stl_path = Path(manifest["exports"]["stl"])
    mesh_step_path = Path(manifest["exports"]["mesh_step"])
    manifest_copy = Path(manifest["exports"]["manifest"])

    assert step_path.parent.name == "Model Output"
    assert step_path.suffix == ".step"
    assert stl_path.suffix == ".stl"
    assert mesh_step_path.name.endswith(".mesh.step")
    assert manifest_copy.name.endswith(".manifest.json")
    assert step_path.exists()
    assert stl_path.exists()
    assert mesh_step_path.exists()
    assert manifest_copy.exists()

    step_text = step_path.read_text(encoding="utf-8", errors="ignore")
    assert "ADVANCED_FACE" in step_text
    assert "TRIANGULATED_FACE_SET" not in step_text


def test_impeller_v07_exports_bounded_step_and_no_default_mesh_step(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_7")

    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["dsl_version"] == "0.7"
    assert manifest["export_strategy"]["mode"] == "surface_graph_bounded_brep"
    assert manifest["export_strategy"]["cad_exports"] == "completed"
    assert manifest["export_strategy"]["coverage_status"] == "partial_supported_surfaces"
    assert manifest["export_strategy"]["cad_export_scope"] == "supported_bounded_brep_surfaces"
    assert manifest["export_strategy"]["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["target_exactness"] == "surface_graph_trimmed_brep_step"
    surface_count = len(manifest["geometry"]["surface_graph"]["surfaces"])
    annular_plane_surfaces = [
        surface
        for surface in manifest["geometry"]["surface_graph"]["surfaces"]
        if surface.get("kind") == "annular_plane_surface"
    ]
    assert step_manifest["coverage_status"] == "partial_supported_surfaces"
    assert step_manifest["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    assert step_manifest["total_surface_count"] == surface_count
    assert step_manifest["supported_surface_count"] == len(annular_plane_surfaces)
    assert step_manifest["unsupported_surface_count"] == surface_count - len(annular_plane_surfaces)
    assert step_manifest["bounded_face_count"] == step_manifest["supported_surface_count"]
    reimport_bbox = step_manifest["reimport_bbox"]
    assert max(reimport_bbox["x_span_mm"], reimport_bbox["y_span_mm"], reimport_bbox["z_span_mm"]) < 5000.0
    assert {"name": "finite_reimport_bbox", "status": "PASS"} in step_manifest["validation_checks"]
    assert step_manifest["export_exactness"] == "surface_graph_trimmed_brep_step"
    if len(annular_plane_surfaces) >= 2:
        assert step_manifest["bounded_face_count"] >= 2
    else:
        # The current V0.7 bounded writer only promotes supported annular plane surfaces.
        assert step_manifest["bounded_face_count"] > 0
    assert set(manifest["exports"]) == {"step", "stl", "obj", "manifest"}
    assert "mesh_step" not in manifest["exports"]
    assert manifest["export_manifests"]["stl"]["export_exactness"] == "surface_graph_sampled_mesh"
    assert manifest["export_manifests"]["obj"]["export_exactness"] == "surface_graph_obj_mesh"

    step_path = Path(manifest["exports"]["step"])
    obj_path = Path(manifest["exports"]["obj"])
    assert step_path.exists()
    assert obj_path.exists()
    step_text = step_path.read_text(encoding="utf-8", errors="ignore")
    obj_text = obj_path.read_text(encoding="utf-8")
    assert "ADVANCED_FACE" in step_text
    assert "TRIANGULATED_FACE_SET" not in step_text
    assert "10000" not in step_text
    assert "\nv " in obj_text
    assert "\nf " in obj_text


def test_impeller_v07_open_and_closed_workflows_include_transitions_bounded_step_and_obj(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    for preset_id in ["radial_open_reference_v0_7", "radial_closed_reference_v0_7"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest

        assert manifest["dsl_version"] == "0.7"
        assert manifest["transition_policies"]
        assert manifest["edge_families"]
        assert manifest["geometry"]["transition_policies"]
        assert manifest["geometry"]["edge_families"]
        assert set(manifest["exports"]) == {"step", "stl", "obj", "manifest"}
        for export_path in manifest["exports"].values():
            assert Path(export_path).exists()

        step_manifest = manifest["export_manifests"]["step"]
        assert step_manifest["bounded_face_count"] > 0
        assert step_manifest["reimport_bbox"]
        assert {"name": "finite_reimport_bbox", "status": "PASS"} in step_manifest["validation_checks"]

        obj_manifest = manifest["export_manifests"]["obj"]
        assert obj_manifest["triangle_count"] > 0

        mesh_manifest = manifest["simulation_manifests"]["cfd_surface_mesh"]
        obj_transition_regions = obj_manifest["transition_regions"]
        mesh_transition_regions = mesh_manifest["transition_regions"]
        assert obj_transition_regions
        assert len(obj_transition_regions) == len(mesh_transition_regions)
        assert {region["surface_graph_id"] for region in obj_transition_regions} == {
            region["surface_graph_id"] for region in mesh_transition_regions
        }


def test_impeller_v08_open_workflow_exports_transition_resolved_artifacts(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    engine = service.synthesize("impeller", "radial_open_reference_v0_8")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]

    assert manifest["dsl_version"] == "0.8"
    assert manifest["geometry_version"] == "0.8"
    assert manifest["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert graph["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert manifest["mesh_strategy"] == "transition_aware_surface_mesh"
    assert manifest["unsupported_transition_count"] == 0
    assert manifest["transition_failure_count"] == 0

    mesh_manifest = manifest["simulation_manifests"]["cfd_surface_mesh"]
    assert mesh_manifest["mesh_type"] == "transition_aware_surface_mesh"
    assert any(region["edge_family"] == "blade_root_to_hub" for region in mesh_manifest["transition_regions"])

    for export_key in ["stl", "obj"]:
        export_manifest = manifest["export_manifests"][export_key]
        assert export_manifest["mesh_type"] == "transition_aware_surface_mesh"
        assert any(region["edge_family"] == "blade_root_to_hub" for region in export_manifest["transition_regions"])

    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["export_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
    assert step_manifest["target_exactness"] == "transition_resolved_trimmed_brep_step"
    assert step_manifest["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert step_manifest["coverage_status"] == "complete_transition_resolved_surface_graph"
    assert step_manifest["cad_export_scope"] == "all_transition_resolved_surface_graph_cad_surfaces"
    assert any(region.get("edge_family") == "blade_root_to_hub" for region in step_manifest["face_regions"])
    assert manifest["export_strategy"]["mode"] == "transition_resolved_bounded_brep"
    assert manifest["export_strategy"]["step_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
    assert manifest["export_strategy"]["target_step_exactness"] == "transition_resolved_trimmed_brep_step"
    assert set(manifest["exports"]) == {"step", "stl", "obj", "manifest"}
    for export_path in manifest["exports"].values():
        assert Path(export_path).exists()


def test_impeller_v08_infeasible_transition_override_fails_before_export(tmp_path: Path):
    model_output_root = tmp_path / "Model Output"
    service = RuleSynthesisService(tmp_path / "runs", model_output_root=model_output_root)

    engine = service.synthesize("impeller", "radial_open_reference_v0_8")
    with pytest.raises(RuntimeError, match="transition failures.*blade_root_to_hub.*radius_exceeds_local_feasible_limit"):
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


def test_api_default_v06_exports_copy_to_cwd_model_output(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PART_RULE_SYNTHESIS_ROOT", raising=False)
    monkeypatch.delenv("PART_RULE_SYNTHESIS_MODEL_OUTPUT_DIR", raising=False)
    client = TestClient(create_app())

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference_v0_6"},
    ).json()["engine_id"]
    manifest = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    step_path = Path(manifest["exports"]["step"])
    assert step_path.parent == tmp_path / "Model Output"
    assert step_path.name.startswith("radial_open_reference_v0_6-run-")
    assert step_path.exists()


def test_impeller_v06_open_and_closed_workflows_include_brep_mesh_and_fillets(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    for preset_id in ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest
        surfaces = {surface["id"]: surface for surface in manifest["geometry"]["surface_graph"]["surfaces"]}

        assert manifest["dsl_version"] == "0.6"
        assert manifest["parameters"]["blade_count"] == 12
        step_manifest = manifest["export_manifests"]["step"]
        assert step_manifest["export_exactness"] == "surface_graph_support_face_brep_step"
        assert step_manifest["target_exactness"] == "surface_graph_trimmed_nurbs_step"
        assert {
            "initial_faces_are_unsewn",
            "trim_loops_not_consumed",
            "cad_edge_wires_not_consumed",
        } <= set(step_manifest["limitations"])
        assert manifest["export_manifests"]["mesh_step"]["export_exactness"] == "surface_graph_mesh_step"
        assert manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"] > 0
        assert "blade_0_root_fillet_surface" in surfaces
        assert surfaces["blade_0_root_fillet_surface"]["radius_mm"] == manifest["parameters"]["root_fillet_radius_mm"]
        assert Path(manifest["exports"]["step"]).exists()
        assert Path(manifest["exports"]["mesh_step"]).exists()
        assert Path(manifest["exports"]["stl"]).exists()


def _binary_stl_bounds(path: Path) -> dict[str, float]:
    data = path.read_bytes()
    triangle_count = struct.unpack("<I", data[80:84])[0]
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for triangle_index in range(triangle_count):
        offset = 84 + triangle_index * 50 + 12
        for vertex_index in range(3):
            x, y, z = struct.unpack("<fff", data[offset + vertex_index * 12 : offset + vertex_index * 12 + 12])
            xs.append(x)
            ys.append(y)
            zs.append(z)
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
        "z_min": min(zs),
        "z_max": max(zs),
    }


def _max_line_deviation(points: list[list[float]]) -> float:
    start = points[0]
    end = points[-1]
    axis = [end[index] - start[index] for index in range(3)]
    axis_length = sum(value * value for value in axis) ** 0.5
    if axis_length == 0.0:
        return 0.0
    maximum = 0.0
    for point in points[1:-1]:
        offset = [point[index] - start[index] for index in range(3)]
        cross = [
            offset[1] * axis[2] - offset[2] * axis[1],
            offset[2] * axis[0] - offset[0] * axis[2],
            offset[0] * axis[1] - offset[1] * axis[0],
        ]
        maximum = max(maximum, (sum(value * value for value in cross) ** 0.5) / axis_length)
    return maximum
