from pathlib import Path
import builtins

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


def test_impeller_interactive_instantiation_does_not_run_cadquery_export(tmp_path: Path, monkeypatch):
    class CadQueryImportUsed(BaseException):
        pass

    original_import = builtins.__import__

    def fail_on_cadquery_import(name, *args, **kwargs):
        if name == "cadquery" or name.startswith("cadquery."):
            raise CadQueryImportUsed("interactive impeller preview must not import CadQuery")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_cadquery_import)

    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "axisymmetric_nurbs_open_throughflow_study")
    run = service.instantiate(engine.engine_id, {})

    assert run.manifest["export_strategy"] == {
        "mode": "surface_graph_preview",
        "cad_exports": "deferred",
        "reason": "interactive preview avoids synchronous CadQuery boolean union",
    }
    assert run.manifest["geometry"]["surface_graph"]["surfaces"]
    assert Path(run.manifest["exports"]["step"]).exists()
    assert Path(run.manifest["exports"]["stl"]).exists()
