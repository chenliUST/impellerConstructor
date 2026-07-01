from pathlib import Path
import struct

from fastapi.testclient import TestClient

from part_rule_synthesis.api import app, create_app
from part_rule_synthesis.service import RuleSynthesisService


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
