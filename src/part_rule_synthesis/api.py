from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from part_rule_synthesis.service import IMPELLER_PRESETS, ONTOLOGY, PRIMITIVES, RuleSynthesisService


class SynthesizeRequest(BaseModel):
    part_family_id: str
    preset_id: str | None = None
    facets: dict[str, str] = Field(default_factory=dict)


class InstantiateRequest(BaseModel):
    parameters: dict[str, float | int] = Field(default_factory=dict)
    profile_overrides: dict[str, Any] | None = None
    curve_overrides: dict[str, Any] | None = None
    section_loop_overrides: dict[str, Any] | None = None
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None
    transition_overrides: dict[str, Any] | None = None
    geometry_stage: str = "full"


class FeedbackRequest(BaseModel):
    source: str
    raw_feedback: str
    affected_feature: str = ""


def create_app(root: Path | None = None) -> FastAPI:
    service_root = root or Path(os.environ.get("PART_RULE_SYNTHESIS_ROOT", Path(gettempdir()) / "part-rule-synthesis"))
    model_output_root = None
    if root is None:
        model_output_root = Path(os.environ.get("PART_RULE_SYNTHESIS_MODEL_OUTPUT_DIR", Path.cwd() / "Model Output"))
    service = RuleSynthesisService(service_root, model_output_root=model_output_root)
    app = FastAPI(title="Part Rule Synthesis", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5180",
            "http://127.0.0.1:5180",
        ],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]+$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ontology")
    def ontology():
        return ONTOLOGY

    @app.get("/api/primitives")
    def primitives():
        return PRIMITIVES

    @app.get("/api/impeller-presets")
    def impeller_presets():
        return {
            "presets": [
                {
                    "preset_id": preset_id,
                    "part_family_id": "impeller",
                    "name": preset["name"],
                    "summary": preset["summary"],
                    "facets": preset["facets"],
                    "parameters": preset["parameters"],
                }
                for preset_id, preset in IMPELLER_PRESETS.items()
            ]
        }

    @app.post("/api/rule-engines/synthesize")
    def synthesize(request: SynthesizeRequest):
        try:
            return asdict(service.synthesize(request.part_family_id, request.preset_id, request.facets))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/rule-engines/{engine_id}/instantiate")
    def instantiate(engine_id: str, request: InstantiateRequest):
        try:
            run = service.instantiate(
                engine_id,
                request.parameters,
                profile_overrides=request.profile_overrides,
                curve_overrides=request.curve_overrides,
                section_loop_overrides=request.section_loop_overrides,
                blade_to_blade_loop_family_overrides=request.blade_to_blade_loop_family_overrides,
                transition_overrides=request.transition_overrides,
                geometry_stage=request.geometry_stage,
            )
            return {"run_id": run.run_id, "manifest": run.manifest}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/model-runs/{run_id}/manifest")
    def manifest(run_id: str):
        run = service.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return run.manifest

    @app.get("/api/model-runs/{run_id}/exports/{export_format}")
    def export(run_id: str, export_format: str):
        run = service.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        path = run.manifest["exports"].get(export_format)
        if not path:
            raise HTTPException(status_code=404, detail="unknown export")
        path = Path(path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="export file missing")
        return FileResponse(path, filename=path.name)

    @app.post("/api/model-runs/{run_id}/feedback")
    def feedback(run_id: str, request: FeedbackRequest):
        try:
            return asdict(
                service.ingest_feedback(
                    run_id,
                    request.source,
                    request.raw_feedback,
                    request.affected_feature,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/feedback/{issue_id}/propose-patch")
    def propose_patch(issue_id: str):
        try:
            return asdict(service.propose_patch(issue_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown issue") from exc

    @app.post("/api/rule-patches/{patch_id}/validate")
    def validate_patch(patch_id: str):
        try:
            return service.validate_patch(patch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown patch") from exc

    @app.post("/api/rule-patches/{patch_id}/approve")
    def approve_patch(patch_id: str):
        try:
            return service.approve_patch(patch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown patch") from exc

    return app


app = create_app()
