from __future__ import annotations

# ruff: noqa: E402

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis.api import create_app
from step_fixtures import write_periodic_impeller_step


def test_step_upload_rejects_non_step_payload_with_stable_reason(tmp_path):
    client = TestClient(create_app(tmp_path / "service"))
    response = client.post(
        "/api/step-reconstruction-audits?filename=bad.bin",
        content=b"not a STEP physical file",
        headers={"Content-Type": "application/step"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "v116_step_parse_failed"


def test_step_upload_returns_202_and_persists_recoverable_status(tmp_path):
    app = create_app(tmp_path / "service")
    audit_service = app.state.step_reconstruction_audits
    audit_service._run_guarded = lambda audit_id: None
    client = TestClient(app)
    step_path = write_periodic_impeller_step(tmp_path / "periodic.step", blade_count=8)

    response = client.post(
        "/api/step-reconstruction-audits?filename=../../periodic.step",
        content=step_path.read_bytes(),
        headers={"Content-Type": "application/step"},
    )

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "QUEUED"
    assert accepted["source"]["safe_filename"] == "periodic.step"
    audit_id = accepted["audit_id"]
    status = client.get(f"/api/step-reconstruction-audits/{audit_id}")
    assert status.status_code == 200
    assert status.json()["source"]["sha256"]
    assert status.json()["algorithm_revision"] == "axis_first_section_periodic_r3"
    assert status.json()["canonical_geometry_version"] == "1.1.2"
    assert status.json()["legacy_workflow_status"] == "PENDING"
    assert status.json()["axis_first_algorithm_status"] == "INCOMPLETE"
    assert status.json()["promotable"] is False
    assert status.json()["algorithm_readiness"]["algorithm_ready"] is False
    assert status.json()["algorithm_readiness"]["cache_reusable"] is False
    assert client.get(f"/api/step-reconstruction-audits/{audit_id}/manifest").status_code == 409
    assert client.get(f"/api/step-reconstruction-audits/{audit_id}/artifacts/../../source.step").status_code == 404


def test_duplicate_step_upload_reuses_the_active_audit(tmp_path):
    app = create_app(tmp_path / "service")
    audit_service = app.state.step_reconstruction_audits
    audit_service._run_guarded = lambda audit_id: None
    client = TestClient(app)
    step_path = write_periodic_impeller_step(tmp_path / "periodic.step", blade_count=8)
    payload = step_path.read_bytes()

    first = client.post(
        "/api/step-reconstruction-audits?filename=periodic.step",
        content=payload,
        headers={"Content-Type": "application/step"},
    )
    second = client.post(
        "/api/step-reconstruction-audits?filename=periodic-copy.step",
        content=payload,
        headers={"Content-Type": "application/step"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["audit_id"] == first.json()["audit_id"]
    assert second.json()["request_disposition"] == "reused_existing_audit"
    assert len(list(audit_service.root.glob("step-audit-*"))) == 1


def test_step_artifact_endpoint_uses_hash_cache_header(tmp_path):
    app = create_app(tmp_path / "service")
    service = app.state.step_reconstruction_audits
    handle = service.begin_upload("part.step")
    artifact = handle.audit_dir / "source.stl"
    artifact.write_bytes(b"solid source\nendsolid source\n")
    client = TestClient(app)

    response = client.get(f"/api/step-reconstruction-audits/{handle.audit_id}/artifacts/source.stl")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["etag"].startswith('"')
