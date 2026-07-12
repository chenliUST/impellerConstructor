from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.api import create_app
from part_rule_synthesis.service import ModelRun, RuleSynthesisService


def test_review_summary_skips_full_manifest_transport_and_requests_review_only(tmp_path, monkeypatch):
    observed = {}

    def fake_instantiate(self, engine_id, parameters, **kwargs):
        observed.update(kwargs)
        return ModelRun(
            run_id="run-review",
            engine_id=engine_id,
            manifest={
                "run_id": "run-review",
                "engine_id": engine_id,
                "part_family": "impeller",
                "preset_id": "nasa_stage37_stator_ring_v1_1",
                "dsl_version": "1.1",
                "runtime_release_version": "1.1.5",
                "geometry_patch_version": "1.1.2",
                "generation_id": "generation-review",
                "geometry": {"surface_graph": {"surfaces": ["large-payload"]}},
                "parameter_inspection": {"large": "payload"},
                "exports": {"step": "large.step"},
            },
        )

    monkeypatch.setattr(RuleSynthesisService, "instantiate", fake_instantiate)
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/rule-engines/engine-review/instantiate",
        json={"parameters": {}, "geometry_stage": "edge_closures", "response_mode": "review_summary"},
    )

    assert response.status_code == 200
    assert observed["review_only"] is True
    manifest = response.json()["manifest"]
    assert manifest["runtime_release_version"] == "1.1.5"
    assert manifest["geometry_patch_version"] == "1.1.2"
    assert "geometry" not in manifest
    assert "parameter_inspection" not in manifest
    assert "exports" not in manifest
