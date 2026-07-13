from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from part_rule_synthesis.service import IMPELLER_PRESETS, ONTOLOGY, PRIMITIVES, RuleSynthesisService
from part_rule_synthesis.impeller_v11_5_engineering_drawing import (
    build_engineering_drawing_contract,
    engineering_drawing_view,
    validate_engineering_drawing_contract,
)
from part_rule_synthesis.impeller_v11_6_step_audit import (
    MAX_UPLOAD_BYTES,
    StepAuditError,
    StepReconstructionAuditService,
)


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
    response_mode: str = "full"


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
    step_audits = StepReconstructionAuditService(service_root)
    engineering_drawing_cache: dict[str, dict[str, Any]] = {}
    app = FastAPI(title="Part Rule Synthesis", version="0.1.0")
    app.state.step_reconstruction_audits = step_audits
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
    @app.get("/api/presets/impeller")
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
            if request.response_mode not in {"full", "review_summary"}:
                raise ValueError(f"unsupported instantiate response_mode: {request.response_mode}")
            run = service.instantiate(
                engine_id,
                request.parameters,
                profile_overrides=request.profile_overrides,
                curve_overrides=request.curve_overrides,
                section_loop_overrides=request.section_loop_overrides,
                blade_to_blade_loop_family_overrides=request.blade_to_blade_loop_family_overrides,
                transition_overrides=request.transition_overrides,
                geometry_stage=request.geometry_stage,
                review_only=request.response_mode == "review_summary",
            )
            manifest = (
                _review_manifest_summary(run.manifest)
                if request.response_mode == "review_summary"
                else run.manifest
            )
            return {"run_id": run.run_id, "manifest": manifest}
        except ValueError as exc:
            preset_id = service.engines.get(engine_id, {}).get("preset_id")
            suffix = f" [preset_id={preset_id}]" if preset_id else ""
            raise HTTPException(status_code=400, detail=f"{exc}{suffix}") from exc

    @app.get("/api/model-runs/{run_id}/manifest")
    def manifest(run_id: str):
        run = service.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return run.manifest

    def resolved_engineering_drawing(run_id: str):
        run = service.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        graph = run.manifest.get("geometry", {}).get("surface_graph", {})
        if run.manifest.get("dsl_version") != "1.1" or not graph:
            raise HTTPException(status_code=404, detail="engineering drawing unavailable")
        contract = engineering_drawing_cache.get(run_id)
        if contract is None:
            contract = build_engineering_drawing_contract(
                graph,
                preset_id=run.manifest.get("preset_id"),
                source_metadata=run.manifest.get("source_metadata", {}),
                parameter_confidence=run.manifest.get("parameter_confidence", {}),
            )
            engineering_drawing_cache[run_id] = contract
        failures = validate_engineering_drawing_contract(graph, contract)
        if failures:
            raise HTTPException(status_code=422, detail=failures)
        return contract

    @app.get("/api/model-runs/{run_id}/engineering-drawing")
    def engineering_drawing(run_id: str):
        return resolved_engineering_drawing(run_id)

    @app.get("/api/model-runs/{run_id}/engineering-drawing/views/{view_id}")
    def engineering_drawing_view_endpoint(run_id: str, view_id: str):
        try:
            return engineering_drawing_view(resolved_engineering_drawing(run_id), view_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"unknown engineering drawing view: {view_id}") from exc

    @app.get("/api/model-runs/{run_id}/engineering-drawing/construction-tables")
    def engineering_drawing_construction_tables(run_id: str):
        contract = resolved_engineering_drawing(run_id)
        return {
            "contract_version": contract["contract_version"],
            "generation_id": contract["generation_id"],
            "preset_id": contract["preset_id"],
            "construction_tables": contract["construction_tables"],
            "construction_parameter_registry": contract["construction_parameter_registry"],
        }

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

    @app.post("/api/step-reconstruction-audits")
    async def create_step_reconstruction_audit(
        request: Request,
        filename: str = Query(default="source.step", max_length=512),
    ):
        handle = step_audits.begin_upload(filename)
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with handle.temporary_path.open("wb") as stream:
                async for chunk in request.stream():
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_BYTES:
                        raise StepAuditError(
                            "v116_step_size_limit_exceeded",
                            f"STEP upload exceeds {MAX_UPLOAD_BYTES} bytes",
                            {"received_bytes": size_bytes, "limit_bytes": MAX_UPLOAD_BYTES},
                        )
                    digest.update(chunk)
                    stream.write(chunk)
            status = step_audits.finish_upload(
                handle,
                size_bytes=size_bytes,
                sha256=digest.hexdigest(),
            )
            return JSONResponse(status_code=202, content=status)
        except StepAuditError as exc:
            step_audits.fail_upload(handle, exc)
            status_code = 413 if exc.reason == "v116_step_size_limit_exceeded" else (
                503 if exc.reason == "v116_step_queue_full" else 400
            )
            raise HTTPException(
                status_code=status_code,
                detail={"reason": exc.reason, "message": str(exc), "details": exc.details},
            ) from exc

    @app.get("/api/step-reconstruction-audits/{audit_id}")
    def step_reconstruction_audit_status(audit_id: str):
        try:
            return step_audits.status(audit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown STEP reconstruction audit") from exc

    @app.get("/api/step-reconstruction-audits/{audit_id}/manifest")
    def step_reconstruction_audit_manifest(audit_id: str):
        try:
            return step_audits.manifest(audit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown STEP reconstruction audit") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="STEP reconstruction audit is not complete") from exc

    @app.get("/api/step-reconstruction-audits/{audit_id}/artifacts/{artifact_name}")
    def step_reconstruction_audit_artifact(audit_id: str, artifact_name: str):
        try:
            path = step_audits.artifact_path(audit_id, artifact_name)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="unknown STEP reconstruction artifact") from exc
        media_types = {
            "source.stl": "model/stl",
            "reconstruction.stl": "model/stl",
            "heatmap.json": "application/json",
        }
        etag = hashlib.sha256(path.read_bytes()).hexdigest()
        return FileResponse(
            path,
            filename=path.name,
            media_type=media_types[artifact_name],
            headers={"ETag": f'"{etag}"', "Cache-Control": "public, max-age=31536000, immutable"},
        )

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


def _review_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "run_id",
        "engine_id",
        "part_family",
        "preset_id",
        "dsl_version",
        "rule_version",
        "geometry_version",
        "geometry_patch_version",
        "runtime_release_version",
        "parameter_inspection_contract_version",
        "generation_id",
        "geometry_generation_status",
        "geometry_validation_status",
        "transition_geometry_status",
        "mesh_strategy",
        "facets",
        "parameters",
        "notice",
    }
    return {key: value for key, value in manifest.items() if key in keys}
