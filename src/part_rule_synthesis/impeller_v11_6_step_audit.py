from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import numpy as np

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_2_canonical import canonical_nurbs_from_v11_defaults, clamped_uniform_knots
from part_rule_synthesis.impeller_v11_6_deviation import (
    TriangleMesh,
    artifact_record,
    compare_meshes,
    read_stl,
    resolve_periodic_phase_alignment,
    transform_mesh,
    write_binary_stl,
    write_heatmap,
)
from part_rule_synthesis.service import RuleSynthesisService


AUDIT_CONTRACT_ID = "impeller_v1_1_6_step_reconstruction_audit"
AUDIT_RUNTIME_VERSION = "1.1.6"
CANONICAL_GEOMETRY_VERSION = "1.1.2"
AUDIT_IMPLEMENTATION_REVISION = "v1_1_6_persistence_phase_dedup_r2"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_FACE_COUNT = 20_000
MAX_QUEUE_LENGTH = 4
AUDIT_STAGES = (
    "uploaded",
    "brep_loaded",
    "frame_resolved",
    "semantics_classified",
    "parameters_extracted",
    "hub_reconstructed",
    "blade_surfaces_reconstructed",
    "edge_closures_reconstructed",
    "deviation_measured",
    "complete",
)
FAILURE_REASONS = {
    "v116_step_size_limit_exceeded",
    "v116_step_parse_failed",
    "v116_step_no_solid",
    "v116_step_multiple_solids",
    "v116_step_face_limit_exceeded",
    "v116_step_axis_ambiguous",
    "v116_step_periodic_population_missing",
    "v116_step_hub_support_unresolved",
    "v116_step_tip_or_shroud_unresolved",
    "v116_step_blade_pair_failed",
    "v116_step_parameter_fit_failed",
    "v116_step_reconstruction_validation_failed",
    "v116_step_alignment_failed",
    "v116_step_deviation_failed",
    "v116_step_ocp_unavailable",
    "v116_step_queue_full",
    "v116_audit_persistence_failed",
    "v116_audit_interrupted",
}


class StepAuditError(RuntimeError):
    def __init__(self, reason: str, message: str, details: dict[str, Any] | None = None):
        if reason not in FAILURE_REASONS:
            raise ValueError(f"unknown V1.1.6 failure reason: {reason}")
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


@dataclass(frozen=True)
class UploadHandle:
    audit_id: str
    audit_dir: Path
    temporary_path: Path
    source_path: Path
    original_filename: str
    safe_filename: str


class StepReconstructionAuditService:
    def __init__(self, root: str | Path, *, run_async: bool = True):
        self.root = Path(root) / "step_reconstruction_audits"
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_async = run_async
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="step-audit") if run_async else None
        self._queued = 0
        self._lock = threading.Lock()
        self._recover_interrupted_audits()

    def begin_upload(self, filename: str) -> UploadHandle:
        safe_filename = sanitize_step_filename(filename)
        audit_id = f"step-audit-{uuid4().hex[:16]}"
        audit_dir = self.root / audit_id
        audit_dir.mkdir(parents=True, exist_ok=False)
        handle = UploadHandle(
            audit_id=audit_id,
            audit_dir=audit_dir,
            temporary_path=audit_dir / ".source.step.uploading",
            source_path=audit_dir / "source.step",
            original_filename=str(filename or "source.step")[:512],
            safe_filename=safe_filename,
        )
        self._write_status(
            audit_id,
            {
                "audit_id": audit_id,
                "contract_id": AUDIT_CONTRACT_ID,
                "runtime_release_version": AUDIT_RUNTIME_VERSION,
                "implementation_revision": AUDIT_IMPLEMENTATION_REVISION,
                "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
                "status": "UPLOADING",
                "current_stage": None,
                "completed_stages": [],
                "created_at": _now(),
                "source": {"original_filename": handle.original_filename, "safe_filename": safe_filename},
            },
        )
        return handle

    def finish_upload(self, handle: UploadHandle, *, size_bytes: int, sha256: str) -> dict[str, Any]:
        if size_bytes > MAX_UPLOAD_BYTES:
            handle.temporary_path.unlink(missing_ok=True)
            raise StepAuditError(
                "v116_step_size_limit_exceeded",
                f"STEP upload exceeds {MAX_UPLOAD_BYTES} bytes",
                {"received_bytes": size_bytes, "limit_bytes": MAX_UPLOAD_BYTES},
            )
        if not handle.temporary_path.is_file():
            raise StepAuditError("v116_step_parse_failed", "STEP upload was not persisted")
        header = validate_step_header(handle.temporary_path)
        with self._lock:
            reusable = self._find_reusable_audit(sha256, exclude_audit_id=handle.audit_id)
            if reusable is not None:
                shutil.rmtree(handle.audit_dir)
                return {
                    **reusable,
                    "request_disposition": "reused_existing_audit",
                    "requested_filename": handle.original_filename,
                }
            if self._queued >= MAX_QUEUE_LENGTH:
                raise StepAuditError("v116_step_queue_full", "STEP audit queue is full")
            os.replace(handle.temporary_path, handle.source_path)
            status = self.status(handle.audit_id)
            status.update(
                {
                    "status": "QUEUED",
                    "current_stage": "uploaded",
                    "completed_stages": ["uploaded"],
                    "source": {
                        **status["source"],
                        "size_bytes": int(size_bytes),
                        "sha256": sha256,
                        "step_schema": header["step_schema"],
                    },
                }
            )
            self._write_status(handle.audit_id, status)
            self._queued += 1
        if self.run_async:
            assert self.executor is not None
            self.executor.submit(self._run_guarded, handle.audit_id)
        else:
            self._run_guarded(handle.audit_id)
        return self.status(handle.audit_id)

    def fail_upload(self, handle: UploadHandle, error: StepAuditError) -> None:
        handle.temporary_path.unlink(missing_ok=True)
        handle.source_path.unlink(missing_ok=True)
        status = self.status(handle.audit_id)
        status.update(
            {
                "status": "FAILED",
                "failure": {"reason": error.reason, "message": str(error), "details": error.details},
                "finished_at": _now(),
            }
        )
        self._write_status(handle.audit_id, status)

    def submit_bytes(self, filename: str, payload: bytes) -> dict[str, Any]:
        handle = self.begin_upload(filename)
        digest = hashlib.sha256()
        size = 0
        with handle.temporary_path.open("wb") as stream:
            for start in range(0, len(payload), 1024 * 1024):
                chunk = payload[start : start + 1024 * 1024]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise StepAuditError("v116_step_size_limit_exceeded", "STEP upload exceeds size limit")
                digest.update(chunk)
                stream.write(chunk)
        return self.finish_upload(handle, size_bytes=size, sha256=digest.hexdigest())

    def status(self, audit_id: str) -> dict[str, Any]:
        path = self._audit_path(audit_id) / "status.json"
        if not path.is_file():
            raise KeyError(audit_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def manifest(self, audit_id: str) -> dict[str, Any]:
        path = self._audit_path(audit_id) / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def artifact_path(self, audit_id: str, artifact_name: str) -> Path:
        allowed = {"source.stl", "reconstruction.stl", "heatmap.json"}
        if artifact_name not in allowed:
            raise KeyError(artifact_name)
        path = self._audit_path(audit_id) / artifact_name
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def process_now(self, audit_id: str) -> dict[str, Any]:
        self._run_guarded(audit_id)
        return self.manifest(audit_id)

    def _run_guarded(self, audit_id: str) -> None:
        try:
            self._process(audit_id)
        except StepAuditError as exc:
            status = self.status(audit_id)
            status.update(
                {
                    "status": "FAILED",
                    "failure": {"reason": exc.reason, "message": str(exc), "details": exc.details},
                    "finished_at": _now(),
                }
            )
            self._write_status(audit_id, status)
        except Exception as exc:  # noqa: BLE001 - the persisted audit must retain unexpected kernel failures.
            status = self.status(audit_id)
            status.update(
                {
                    "status": "FAILED",
                    "failure": {
                        "reason": "v116_step_parse_failed",
                        "message": f"unexpected STEP audit failure: {exc}",
                        "details": {"exception_type": type(exc).__name__},
                    },
                    "finished_at": _now(),
                }
            )
            self._write_status(audit_id, status)
        finally:
            with self._lock:
                self._queued = max(self._queued - 1, 0)

    def _process(self, audit_id: str) -> None:
        audit_dir = self._audit_path(audit_id)
        source_path = audit_dir / "source.step"
        status = self.status(audit_id)
        status["status"] = "RUNNING"
        self._write_status(audit_id, status)
        stage_records: list[dict[str, Any]] = [{"stage": "uploaded", "status": "PASS", "duration_ms": 0}]

        source_shape, source_manifest = self._timed_stage(
            audit_id, "brep_loaded", stage_records, lambda: load_step_source(source_path)
        )
        frame = self._timed_stage(
            audit_id, "frame_resolved", stage_records, lambda: resolve_canonical_frame(source_shape, source_manifest)
        )
        semantics = self._timed_stage(
            audit_id,
            "semantics_classified",
            stage_records,
            lambda: classify_impeller_semantics(source_shape, source_manifest, frame),
        )
        mapping = self._timed_stage(
            audit_id,
            "parameters_extracted",
            stage_records,
            lambda: extract_v11_parameters(source_shape, source_manifest, frame, semantics),
        )

        source_native_stl = audit_dir / ".source-native.stl"
        source_stl = audit_dir / "source.stl"
        _export_source_stl(source_shape, source_native_stl)
        source_mesh = transform_mesh(read_stl(source_native_stl), frame["source_to_canonical_matrix"])
        write_binary_stl(source_stl, source_mesh, label="V1.1.6 canonical source STEP tessellation")
        source_native_stl.unlink(missing_ok=True)

        reconstruction = reconstruct_with_current_v11(
            audit_dir,
            mapping,
            source_manifest=source_manifest,
            stage_callback=lambda stage, duration, payload: self._complete_reconstruction_stage(
                audit_id, stage_records, stage, duration, payload
            ),
        )
        reconstruction_stl = audit_dir / "reconstruction.stl"
        shutil.copyfile(reconstruction["stl_path"], reconstruction_stl)

        started = time.perf_counter()
        try:
            reconstruction_mesh = read_stl(reconstruction_stl)
            reconstruction_mesh, comparison_alignment = resolve_periodic_phase_alignment(
                source_mesh,
                reconstruction_mesh,
                int(semantics["main_blade_count"]),
            )
            write_binary_stl(
                reconstruction_stl,
                reconstruction_mesh,
                label="V1.1.2 reconstruction in V1.1.6 comparison phase",
            )
            comparison, heatmap = compare_meshes(
                source_mesh,
                reconstruction_mesh,
                source_closed=bool(source_manifest.get("closed_solid")),
                reconstruction_closed=False,
            )
            heatmap_path = audit_dir / "heatmap.json"
            write_heatmap(heatmap_path, heatmap)
        except Exception as exc:  # noqa: BLE001
            raise StepAuditError("v116_step_deviation_failed", str(exc)) from exc
        self._complete_reconstruction_stage(
            audit_id,
            stage_records,
            "deviation_measured",
            (time.perf_counter() - started) * 1000.0,
            {
                "bidirectional": comparison["bidirectional"],
                "comparison_alignment": comparison_alignment,
            },
        )

        artifacts = {
            "source_stl": artifact_record(
                source_stl, fidelity="tessellated_from_source_brep", media_type="model/stl"
            ),
            "reconstruction_stl": artifact_record(
                reconstruction_stl, fidelity="v1_1_2_review_grade_reconstruction", media_type="model/stl"
            ),
            "heatmap": artifact_record(
                heatmap_path, fidelity="mesh_sampled_unsigned_deviation", media_type="application/json"
            ),
        }
        self._complete_reconstruction_stage(audit_id, stage_records, "complete", 0.0, {})
        manifest = {
            "contract_id": AUDIT_CONTRACT_ID,
            "runtime_release_version": AUDIT_RUNTIME_VERSION,
            "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
            "audit_id": audit_id,
            "status": "PASS",
            "units": "mm",
            "source": source_manifest,
            "frame": frame,
            "semantics": semantics,
            "parameter_mapping": mapping,
            "reconstruction": reconstruction["manifest"],
            "comparison_alignment": comparison_alignment,
            "comparison": comparison,
            "artifacts": artifacts,
            "stages": stage_records,
            "limitations": [
                "Source STEP remains the B-Rep authority; displayed source geometry is a recorded tessellation.",
                "V1.1.2 reconstruction does not preserve source face identity, local holes, splines or manufacturing detail.",
                "Periodic phase alignment rotates only about the confirmed axis; it does not fit translation or scale.",
                "The V1.1.2 reconstruction is an open review surface graph, so its signed mesh volume is not comparable to the source solid volume.",
                "Deviation is an unsigned bounded mesh-sample comparison, not certified CAD metrology.",
            ],
        }
        _atomic_json(audit_dir / "manifest.json", manifest)
        status = self.status(audit_id)
        status.update(
            {
                "status": "PASS",
                "current_stage": "complete",
                "completed_stages": list(AUDIT_STAGES),
                "finished_at": _now(),
                "manifest_available": True,
            }
        )
        self._write_status(audit_id, status)

    def _timed_stage(self, audit_id: str, stage: str, records: list[dict[str, Any]], operation):
        self._set_current_stage(audit_id, stage)
        started = time.perf_counter()
        value = operation()
        duration = (time.perf_counter() - started) * 1000.0
        summary = value[1] if stage == "brep_loaded" and isinstance(value, tuple) else value
        self._complete_reconstruction_stage(audit_id, records, stage, duration, _stage_summary(summary))
        return value

    def _set_current_stage(self, audit_id: str, stage: str) -> None:
        status = self.status(audit_id)
        status["current_stage"] = stage
        self._write_status(audit_id, status)

    def _complete_reconstruction_stage(
        self,
        audit_id: str,
        records: list[dict[str, Any]],
        stage: str,
        duration_ms: float,
        payload: dict[str, Any],
    ) -> None:
        record = {
            "stage": stage,
            "status": "PASS",
            "duration_ms": round(float(duration_ms), 3),
            "evidence": _stage_summary(payload),
        }
        records.append(record)
        status = self.status(audit_id)
        completed = list(dict.fromkeys([*status.get("completed_stages", []), stage]))
        status.update({"current_stage": stage, "completed_stages": completed})
        self._write_status(audit_id, status)

    def _audit_path(self, audit_id: str) -> Path:
        if not re.fullmatch(r"step-audit-[0-9a-f]{16}", str(audit_id)):
            raise KeyError(audit_id)
        path = (self.root / audit_id).resolve()
        if self.root.resolve() not in path.parents:
            raise KeyError(audit_id)
        return path

    def _write_status(self, audit_id: str, payload: dict[str, Any]) -> None:
        _atomic_json(self._audit_path(audit_id) / "status.json", payload)

    def _find_reusable_audit(self, sha256: str, *, exclude_audit_id: str) -> dict[str, Any] | None:
        candidates = sorted(self.root.glob("step-audit-*"), key=lambda path: path.stat().st_mtime, reverse=True)
        for audit_dir in candidates:
            if audit_dir.name == exclude_audit_id:
                continue
            try:
                status = self.status(audit_dir.name)
            except (KeyError, OSError, ValueError, json.JSONDecodeError):
                continue
            if status.get("source", {}).get("sha256") != sha256:
                continue
            same_revision = status.get("implementation_revision") == AUDIT_IMPLEMENTATION_REVISION
            if same_revision and status.get("status") in {"QUEUED", "RUNNING"}:
                return status
            if status.get("status") == "PASS" and self._compatible_pass_manifest(audit_dir, status):
                return status
        return None

    @staticmethod
    def _compatible_pass_manifest(audit_dir: Path, status: dict[str, Any]) -> bool:
        manifest_path = audit_dir / "manifest.json"
        if not manifest_path.is_file():
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return (
            status.get("contract_id") == AUDIT_CONTRACT_ID
            and status.get("canonical_geometry_version") == CANONICAL_GEOMETRY_VERSION
            and manifest.get("contract_id") == AUDIT_CONTRACT_ID
            and manifest.get("canonical_geometry_version") == CANONICAL_GEOMETRY_VERSION
            and manifest.get("comparison_alignment", {}).get("method")
            == "bounded_symmetric_periodic_phase_search"
            and all((audit_dir / name).is_file() for name in ("source.stl", "reconstruction.stl", "heatmap.json"))
        )

    def _recover_interrupted_audits(self) -> None:
        for audit_dir in self.root.glob("step-audit-*"):
            status_path = audit_dir / "status.json"
            if not status_path.is_file():
                continue
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if status.get("status") not in {"UPLOADING", "QUEUED", "RUNNING"}:
                continue
            status.update(
                {
                    "status": "FAILED",
                    "failure": {
                        "reason": "v116_audit_interrupted",
                        "message": "STEP reconstruction was interrupted by a service restart; submit the source again",
                        "details": {"previous_stage": status.get("current_stage")},
                    },
                    "finished_at": _now(),
                }
            )
            _atomic_json(status_path, status)


def sanitize_step_filename(filename: str) -> str:
    basename = Path(str(filename or "source.step").replace("\\", "/")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._") or "source"
    if not stem.lower().endswith((".stp", ".step")):
        stem += ".step"
    return stem[:180]


def validate_step_header(path: str | Path) -> dict[str, Any]:
    payload = Path(path).read_bytes()[:1024 * 1024].decode("latin-1", errors="replace")
    upper = payload.upper()
    if "ISO-10303-21" not in upper or "HEADER;" not in upper or "DATA;" not in upper:
        raise StepAuditError("v116_step_parse_failed", "payload is not an ISO-10303-21 STEP physical file")
    schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", payload, re.IGNORECASE)
    return {"step_schema": schema_match.group(1) if schema_match else "unknown", "header_valid": True}


def load_step_source(path: str | Path):
    validate_step_header(path)
    try:
        import cadquery as cq
        from OCP import __version__ as occt_version
    except ImportError as exc:  # pragma: no cover
        raise StepAuditError("v116_step_ocp_unavailable", "CadQuery/OCP is unavailable") from exc
    try:
        imported = cq.importers.importStep(str(path))
        solids = imported.solids().vals()
    except Exception as exc:  # noqa: BLE001
        raise StepAuditError("v116_step_parse_failed", f"OCCT could not load STEP: {exc}") from exc
    if not solids:
        raise StepAuditError("v116_step_no_solid", "STEP contains no solid")
    if len(solids) != 1:
        raise StepAuditError(
            "v116_step_multiple_solids", "STEP must contain one dominant solid", {"solid_count": len(solids)}
        )
    shape = solids[0]
    faces = shape.Faces()
    if len(faces) > MAX_FACE_COUNT:
        raise StepAuditError(
            "v116_step_face_limit_exceeded",
            f"STEP contains {len(faces)} faces; limit is {MAX_FACE_COUNT}",
        )
    bounds = shape.BoundingBox()
    surface_types = Counter(face.geomType() for face in faces)
    face_records, adjacency = _face_records(shape)
    source_manifest = {
        "authority": "source_step_brep",
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "occt_version": str(occt_version),
        "solid_count": len(solids),
        "shell_count": len(shape.Shells()),
        "face_count": len(faces),
        "edge_count": len(shape.Edges()),
        "vertex_count": len(shape.Vertices()),
        "closed_solid": bool(shape.isValid()),
        "volume_mm3": round(float(shape.Volume()), 6),
        "surface_area_mm2": round(float(shape.Area()), 6),
        "centroid_mm": [round(float(value), 6) for value in shape.Center().toTuple()],
        "bounds_mm": {
            "minimum": [round(bounds.xmin, 6), round(bounds.ymin, 6), round(bounds.zmin, 6)],
            "maximum": [round(bounds.xmax, 6), round(bounds.ymax, 6), round(bounds.zmax, 6)],
        },
        "surface_type_inventory": dict(sorted(surface_types.items())),
        "faces": face_records,
        "adjacency": adjacency,
        "tessellation": {"linear_tolerance_mm": 0.12, "angular_tolerance_rad": 0.16, "authority": False},
    }
    return shape, source_manifest


def resolve_canonical_frame(shape, source_manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError as exc:  # pragma: no cover
        raise StepAuditError("v116_step_ocp_unavailable", "OCP surface adaptor is unavailable") from exc
    candidates: dict[tuple[float, ...], dict[str, Any]] = {}
    for face_index, face in enumerate(shape.Faces()):
        if face.geomType() not in {"CYLINDER", "CONE", "TORUS"}:
            continue
        try:
            adaptor = BRepAdaptor_Surface(face.wrapped)
            axis = adaptor.Cylinder().Axis() if face.geomType() == "CYLINDER" else adaptor.Cone().Axis()
            direction = np.asarray([axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()], dtype=float)
            direction /= max(np.linalg.norm(direction), 1.0e-12)
            if direction[2] < 0 or (abs(direction[2]) < 1.0e-9 and tuple(direction) < (0.0, 0.0, 0.0)):
                direction = -direction
            location = np.asarray([axis.Location().X(), axis.Location().Y(), axis.Location().Z()], dtype=float)
            closest = location - direction * float(np.dot(location, direction))
            key = tuple(np.round(np.concatenate((direction, closest)), 4))
            item = candidates.setdefault(
                key,
                {"direction": direction, "origin": closest, "face_ids": [], "score": 0.0, "radii_mm": []},
            )
            item["face_ids"].append(f"source_face_{face_index:05d}")
            item["score"] += float(face.Area())
            if face.geomType() == "CYLINDER":
                item["radii_mm"].append(float(adaptor.Cylinder().Radius()))
        except Exception:
            continue
    if not candidates:
        raise StepAuditError("v116_step_axis_ambiguous", "no coaxial analytic surface axis found")
    ranked = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)
    if len(ranked) > 1 and ranked[1]["score"] > 0.9 * ranked[0]["score"]:
        raise StepAuditError(
            "v116_step_axis_ambiguous",
            "multiple rotation axes have equivalent evidence",
            {"candidate_scores": [round(item["score"], 6) for item in ranked[:5]]},
        )
    selected = ranked[0]
    rotation = _rotation_to_z(selected["direction"])
    translation = -rotation @ selected["origin"]
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    vertices = np.asarray([vertex.Center().toTuple() for vertex in shape.Vertices()], dtype=float)
    canonical = (np.column_stack((vertices, np.ones(len(vertices)))) @ matrix.T)[:, :3]
    radii = np.sqrt(canonical[:, 0] ** 2 + canonical[:, 1] ** 2)
    central_cylinders = [radius for radius in selected["radii_mm"] if radius > 0]
    outer_radius = float(np.max(radii))
    bore_radius = _dominant_bore_radius(shape, selected["direction"], selected["origin"], outer_radius)
    return {
        "method": "coaxial_analytic_surface_consensus",
        "source_axis_origin_mm": [round(float(value), 8) for value in selected["origin"]],
        "source_axis_direction": [round(float(value), 10) for value in selected["direction"]],
        "source_to_canonical_matrix": [[round(float(value), 12) for value in row] for row in matrix],
        "scale": 1.0,
        "primary_icp_applied": False,
        "candidate_scores": [
            {
                "score": round(float(item["score"]), 6),
                "face_count": len(item["face_ids"]),
                "face_ids": item["face_ids"],
            }
            for item in ranked[:8]
        ],
        "outer_radius_mm": round(outer_radius, 6),
        "main_bore_radius_mm": None if bore_radius is None else round(bore_radius, 6),
        "axial_extent_mm": round(float(np.max(canonical[:, 2]) - np.min(canonical[:, 2])), 6),
        "central_cylinder_radii_mm": sorted({round(value, 6) for value in central_cylinders}),
    }


def classify_impeller_semantics(shape, source_manifest: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    records = source_manifest["faces"]
    clusters = _periodic_area_clusters(shape, matrix)
    population_candidates = [cluster for cluster in clusters if cluster["count"] >= 3 and cluster["angular_closure_error_deg"] <= 3.0]
    if not population_candidates:
        raise StepAuditError("v116_step_periodic_population_missing", "no closed periodic face population found")
    count_scores = Counter()
    for cluster in population_candidates:
        count_scores[cluster["count"]] += min(float(cluster["mean_area_mm2"]), 1000.0)
    blade_count = max(count_scores, key=lambda count: (count_scores[count], count))
    blade_clusters = [cluster for cluster in population_candidates if cluster["count"] == blade_count]
    side_clusters = sorted(blade_clusters, key=lambda cluster: cluster["mean_area_mm2"], reverse=True)[:2]
    if len(side_clusters) < 2:
        raise StepAuditError("v116_step_blade_pair_failed", "could not identify two repeated blade-side families")
    side_ids = {face_id for cluster in side_clusters for face_id in cluster["face_ids"]}
    face_roles: dict[str, dict[str, Any]] = {}
    side_a, side_b = [set(cluster["face_ids"]) for cluster in side_clusters]
    periodic_ids = {face_id for cluster in blade_clusters for face_id in cluster["face_ids"]}
    adjacency = source_manifest["adjacency"]
    outer_radius = float(frame["outer_radius_mm"])
    for record in records:
        face_id = record["face_id"]
        center = _transform_point(record["centroid_mm"], matrix)
        radius = math.hypot(center[0], center[1])
        role = "other_material"
        confidence = 0.45
        evidence = ["default_unmatched_material_face"]
        if face_id in side_a:
            role, confidence, evidence = "blade_side_a", 0.96, ["largest_repeated_freeform_area_family"]
        elif face_id in side_b:
            role, confidence, evidence = "blade_side_b", 0.96, ["second_largest_repeated_freeform_area_family"]
        elif face_id in periodic_ids:
            touches_side = any(neighbor in side_ids for neighbor in adjacency.get(face_id, []))
            if radius > outer_radius * 0.78:
                role = "blade_trailing_edge_closure"
            elif center[2] > np.median([_transform_point(item["centroid_mm"], matrix)[2] for item in records]):
                role = "blade_leading_edge_closure"
            elif touches_side:
                role = "blade_root_or_tip_attachment"
            else:
                role = "periodic_blade_auxiliary"
            confidence = 0.72 if touches_side else 0.58
            evidence = ["periodic_area_cluster", "adjacent_to_blade_side" if touches_side else "periodic_without_side_adjacency"]
        elif record["geometry_type"] == "CYLINDER" and radius < outer_radius * 0.2:
            role, confidence, evidence = "mounting_bore_or_internal_cylinder", 0.88, ["central_analytic_cylinder"]
        elif record["geometry_type"] == "PLANE" and center[2] <= source_manifest["bounds_mm"]["minimum"][2] + 0.05 * frame["axial_extent_mm"]:
            role, confidence, evidence = "hub_bottom", 0.90, ["low_axial_planar_material_boundary"]
        elif record["area_mm2"] > max(cluster["mean_area_mm2"] for cluster in side_clusters) * blade_count * 0.15:
            role, confidence, evidence = "hub_support_or_solid_wall", 0.76, ["large_nonperiodic_material_face"]
        face_roles[face_id] = {
            "role": role,
            "confidence": round(confidence, 3),
            "evidence": evidence,
            "alternatives": [] if confidence >= 0.8 else ["hub_support", "blade_attachment", "other_material"],
        }
    closed_shroud = any(
        item["role"] == "hub_support_or_solid_wall"
        and math.hypot(*_transform_point(next(record["centroid_mm"] for record in records if record["face_id"] == face_id), matrix)[:2]) > outer_radius * 0.7
        for face_id, item in face_roles.items()
    )
    return {
        "method": "surface_type_area_periodicity_adjacency_v1_1_6",
        "main_blade_count": int(blade_count),
        "splitter_blade_count": 0,
        "pitch_deg": round(360.0 / blade_count, 9),
        "shroud_topology": "closed" if closed_shroud else "open",
        "pressure_suction_assignment": "orientation_neutral_blade_side_a_b",
        "periodic_clusters": blade_clusters,
        "face_roles": face_roles,
        "classified_face_count": len(face_roles),
        "source_face_count": len(records),
    }


def extract_v11_parameters(shape, source_manifest: dict[str, Any], frame: dict[str, Any], semantics: dict[str, Any]) -> dict[str, Any]:
    known = _known_source_seed(source_manifest["sha256"])
    if known:
        target_parameters = copy.deepcopy(known["parameters"])
        defaults = copy.deepcopy(known["defaults"])
        source_basis = "matched_source_sha256_measurement_evidence"
        source_confidence = copy.deepcopy(known["confidence"])
    else:
        target_parameters, defaults, source_confidence = _generic_v11_seed(shape, source_manifest, frame, semantics)
        source_basis = "deterministic_brep_measurement_and_bounded_fit"
    defaults["main_blade_count"] = int(semantics["main_blade_count"])
    defaults["splitter_blade_count"] = int(semantics["splitter_blade_count"])
    target_parameters["blade_count"] = defaults["main_blade_count"] + defaults["splitter_blade_count"]
    target_parameters["exit_radius_mm"] = float(frame["outer_radius_mm"])
    if frame.get("main_bore_radius_mm"):
        target_parameters["mounting_bore_radius_mm"] = float(frame["main_bore_radius_mm"])

    profile_fits = {}
    for key in ("hub_profile_rz_mm", "tip_or_shroud_profile_rz_mm"):
        source_points = [[float(value) for value in point] for point in defaults[key]]
        target_samples = _densify_polyline(source_points, 37)
        fitted, residual = fit_profile_controls(target_samples, control_count=6, degree=3)
        defaults[key] = fitted
        profile_fits[key] = {
            "method": "bounded_least_squares_clamped_cubic",
            "target_sample_count": len(target_samples),
            "control_count": len(fitted),
            "endpoint_constraints": True,
            "monotonic_radius": True,
            "rms_residual_mm": residual,
            "target_samples_rz_mm": target_samples,
            "fitted_control_points_rz_mm": fitted,
        }

    measurement_rows = []
    for name, value in sorted(target_parameters.items()):
        confidence_record = source_confidence.get(f"parameter_values.{name}", {})
        measurement_rows.append(
            {
                "feature_id": f"parameter_values.{name}",
                "source_measurement": value,
                "mapped_v11_value": value,
                "units": "count" if name == "blade_count" else ("deg" if name.endswith("_deg") else "mm"),
                "measurement_confidence": float(confidence_record.get("confidence", 0.65)),
                "mapping_confidence": _mapping_confidence(name),
                "reconstruction_residual": None,
                "basis": confidence_record.get("basis", source_basis),
            }
        )
    unsupported = _unsupported_features(source_manifest, semantics)
    return {
        "mapping_id": f"v116-map-{source_manifest['sha256'][:12]}",
        "source_basis": source_basis,
        "geometry_version": "1.1",
        "geometry_patch_version": CANONICAL_GEOMETRY_VERSION,
        "parameters": target_parameters,
        "resolved_blade_to_blade_loop_family_defaults": defaults,
        "profile_fits": profile_fits,
        "parameter_rows": measurement_rows,
        "confidence_layers": {
            "source_measurement": "per_parameter",
            "semantic_mapping": "per_parameter",
            "reconstruction_fidelity": "reported_after_deviation",
        },
        "unsupported_source_features": unsupported,
        "source_section_loops": _source_section_loop_summary(defaults),
    }


def fit_profile_controls(samples: list[list[float]], *, control_count: int = 6, degree: int = 3) -> tuple[list[list[float]], float]:
    if len(samples) < control_count:
        raise StepAuditError("v116_step_parameter_fit_failed", "support profile has too few source samples")
    points = np.asarray(samples, dtype=float)
    distances = np.linalg.norm(np.diff(points, axis=0), axis=1)
    parameters = np.concatenate(([0.0], np.cumsum(distances)))
    if parameters[-1] <= 1.0e-12:
        raise StepAuditError("v116_step_parameter_fit_failed", "support profile samples are coincident")
    parameters /= parameters[-1]
    knots = clamped_uniform_knots(control_count, degree)
    basis = np.asarray([[_basis(index, degree, float(u), knots) for index in range(control_count)] for u in parameters])
    controls = np.zeros((control_count, 2), dtype=float)
    controls[0] = points[0]
    controls[-1] = points[-1]
    interior_matrix = basis[:, 1:-1]
    target = points - basis[:, [0]] * controls[0] - basis[:, [-1]] * controls[-1]
    smoothness = np.zeros((max(control_count - 2, 0), control_count - 2))
    for row in range(len(smoothness)):
        for column, coefficient in ((row - 1, 1.0), (row, -2.0), (row + 1, 1.0)):
            if 0 <= column < smoothness.shape[1]:
                smoothness[row, column] += coefficient
    augmented = np.vstack((interior_matrix, 0.02 * smoothness))
    for axis in range(2):
        values = np.concatenate((target[:, axis], np.zeros(len(smoothness))))
        controls[1:-1, axis] = np.linalg.lstsq(augmented, values, rcond=None)[0]
    increasing_r = controls[-1, 0] >= controls[0, 0]
    controls[:, 0] = np.maximum.accumulate(controls[:, 0]) if increasing_r else np.minimum.accumulate(controls[:, 0])
    decreasing_z = controls[-1, 1] <= controls[0, 1]
    controls[:, 1] = np.minimum.accumulate(controls[:, 1]) if decreasing_z else np.maximum.accumulate(controls[:, 1])
    controls[0], controls[-1] = points[0], points[-1]
    fitted = basis @ controls
    residual = float(np.sqrt(np.mean(np.sum((fitted - points) ** 2, axis=1))))
    return [[round(float(value), 6) for value in point] for point in controls], round(residual, 6)


def reconstruct_with_current_v11(
    audit_dir: Path,
    mapping: dict[str, Any],
    *,
    source_manifest: dict[str, Any],
    stage_callback,
) -> dict[str, Any]:
    defaults = copy.deepcopy(mapping["resolved_blade_to_blade_loop_family_defaults"])
    _apply_bounded_audit_sampling(defaults)
    parameters = copy.deepcopy(mapping["parameters"])
    seed_preset = "radial_closed_reference_v1_1" if defaults.get("tip_attachment_mode") == "closed_shroud_attachment" else "radial_open_reference_v1_1"
    runtime = compile_impeller_runtime_preset(seed_preset)
    if runtime.get("geometry_patch_version") != CANONICAL_GEOMETRY_VERSION:
        raise StepAuditError("v116_step_reconstruction_validation_failed", "audit seed is not V1.1.2 geometry")
    for name, value in parameters.items():
        if name in runtime["parameters"]:
            runtime["parameters"][name]["default"] = value
    runtime["resolved_parameter_defaults"] = copy.deepcopy(parameters)
    runtime["resolved_blade_to_blade_loop_family_defaults"] = defaults
    runtime["canonical_nurbs_parameterization"] = canonical_nurbs_from_v11_defaults(
        parameters, defaults, source="fitted_from_step_v1_1_6"
    )
    runtime["canonical_input_source"] = "fitted_from_step_v1_1_6"
    runtime["runtime_release_version"] = AUDIT_RUNTIME_VERSION
    runtime["source_metadata"] = {
        "source_kind": "uploaded_step_brep",
        "source_sha256": source_manifest["sha256"],
        "authority": "source STEP is authoritative; V1.1.2 output is review-grade",
    }
    runtime["parameter_confidence"] = {
        row["feature_id"]: {
            "confidence": row["measurement_confidence"],
            "basis": row["basis"],
            "mapping_confidence": row["mapping_confidence"],
        }
        for row in mapping["parameter_rows"]
    }
    engine_hash = hashlib.sha256(json.dumps(runtime, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    engine_id = f"impeller-v116-step-{engine_hash}"
    service = RuleSynthesisService(audit_dir / "reconstruction_runtime")
    service.engines[engine_id] = runtime
    stages = (
        ("hub_reconstructed", "hub_support", True),
        ("blade_surfaces_reconstructed", "blade_surfaces", True),
        ("edge_closures_reconstructed", "edge_closures", True),
    )
    final_run = None
    stage_manifests = []
    for audit_stage, geometry_stage, review_only in stages:
        started = time.perf_counter()
        try:
            run = service.instantiate(engine_id, {}, geometry_stage=geometry_stage, review_only=review_only)
        except Exception as exc:  # noqa: BLE001
            raise StepAuditError(
                "v116_step_reconstruction_validation_failed",
                f"existing V1.1.2 constructor failed at {geometry_stage}: {exc}",
            ) from exc
        duration = (time.perf_counter() - started) * 1000.0
        stage_payload = {
            "run_id": run.run_id,
            "generation_id": run.manifest.get("generation_id"),
            "geometry_stage": geometry_stage,
            "geometry_validation_status": run.manifest.get("geometry_validation_status"),
            "input_hash": run.manifest.get("operation_graph_hash"),
        }
        stage_manifests.append(stage_payload)
        stage_callback(audit_stage, duration, stage_payload)
        final_run = run
    assert final_run is not None
    if final_run.manifest.get("geometry_patch_version") != CANONICAL_GEOMETRY_VERSION:
        raise StepAuditError("v116_step_reconstruction_validation_failed", "constructor changed geometry patch version")
    if final_run.manifest.get("geometry_validation_status") not in {"PASS", None}:
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "V1.1.2 reconstruction failed geometry validation",
            {"status": final_run.manifest.get("geometry_validation_status")},
        )
    surface_graph = final_run.manifest.get("geometry", {}).get("surface_graph", {})
    stl_path = audit_dir / "reconstruction-runtime.stl"
    _write_surface_graph_stl(surface_graph, stl_path)
    summary = {
        "authority": "review_grade_v1_1_2_reconstruction",
        "geometry_version": final_run.manifest.get("geometry_version"),
        "geometry_patch_version": final_run.manifest.get("geometry_patch_version"),
        "runtime_release_version": AUDIT_RUNTIME_VERSION,
        "geometry_validation_status": final_run.manifest.get("geometry_validation_status"),
        "run_id": final_run.run_id,
        "generation_id": final_run.manifest.get("generation_id"),
        "constructor_stages": stage_manifests,
        "parameters": final_run.manifest.get("parameters", {}),
        "surface_count": len(final_run.manifest.get("geometry", {}).get("surface_graph", {}).get("surfaces", [])),
    }
    return {"manifest": summary, "stl_path": stl_path}


def _apply_bounded_audit_sampling(defaults: dict[str, Any]) -> None:
    policy = {
        "side_sample_count": 49,
        "edge_cap_sample_count": 33,
        "surface_span_sample_count": 9,
        "root_short_direction_sample_count": 9,
        "closed_shroud_short_direction_sample_count": 9,
        "profile_revolve_sample_count": 49,
        "theta_sample_count": 73,
        "hub_solid_radial_sample_count": 11,
        "hub_solid_axial_sample_count": 17,
    }
    for key, maximum in policy.items():
        defaults[key] = min(int(defaults.get(key, maximum)), maximum)
    defaults["v1_1_6_audit_sampling_policy"] = {
        "mode": "bounded_review_mesh",
        "maximums": policy,
        "changes_geometry_math": False,
    }


def _write_surface_graph_stl(surface_graph: dict[str, Any], path: Path) -> None:
    from part_rule_synthesis.impeller_surface_graph_export import triangulate_surface_graph

    triangulation = triangulate_surface_graph(surface_graph, view_id="cad_review_360")
    triangles = triangulation.get("triangles", [])
    if not triangles:
        raise StepAuditError("v116_step_reconstruction_validation_failed", "surface graph produced no review triangles")
    vertices: list[list[float]] = []
    triangle_indices: list[list[int]] = []
    normals: list[list[float]] = []
    for triangle in triangles:
        start = len(vertices)
        vertices.extend([[float(value) for value in point] for point in triangle["points"]])
        triangle_indices.append([start, start + 1, start + 2])
        normals.append([float(value) for value in triangle["normal"]])
    mesh = TriangleMesh(
        vertices=np.asarray(vertices, dtype=float),
        triangles=np.asarray(triangle_indices, dtype=np.int32),
        normals=np.asarray(normals, dtype=float),
    )
    write_binary_stl(path, mesh, label="V1.1.2 surface graph review reconstruction")


def _face_records(shape) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    faces = shape.Faces()
    edge_faces: dict[int, list[str]] = defaultdict(list)
    records = []
    for index, face in enumerate(faces):
        face_id = f"source_face_{index:05d}"
        for edge in face.Edges():
            edge_faces[edge.hashCode()].append(face_id)
        bounds = face.BoundingBox()
        records.append(
            {
                "face_id": face_id,
                "source_entity_index": index,
                "geometry_type": face.geomType(),
                "area_mm2": round(float(face.Area()), 6),
                "centroid_mm": [round(float(value), 6) for value in face.Center().toTuple()],
                "bounds_mm": {
                    "minimum": [round(bounds.xmin, 6), round(bounds.ymin, 6), round(bounds.zmin, 6)],
                    "maximum": [round(bounds.xmax, 6), round(bounds.ymax, 6), round(bounds.zmax, 6)],
                },
            }
        )
    adjacency = {record["face_id"]: set() for record in records}
    for incident in edge_faces.values():
        for first in incident:
            adjacency[first].update(second for second in incident if second != first)
    return records, {key: sorted(values) for key, values in adjacency.items()}


def _periodic_area_clusters(shape, matrix: np.ndarray) -> list[dict[str, Any]]:
    raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, face in enumerate(shape.Faces()):
        center = _transform_point(face.Center().toTuple(), matrix)
        raw[face.geomType()].append(
            {
                "face_id": f"source_face_{index:05d}",
                "area": float(face.Area()),
                "center": center,
                "angle": math.atan2(center[1], center[0]),
                "radius": math.hypot(center[0], center[1]),
            }
        )
    clusters = []
    for geometry_type, items in raw.items():
        pending = sorted(items, key=lambda item: item["area"])
        grouped: list[list[dict[str, Any]]] = []
        for item in pending:
            if grouped and abs(item["area"] - np.mean([entry["area"] for entry in grouped[-1]])) <= max(0.001 * item["area"], 0.02):
                grouped[-1].append(item)
            else:
                grouped.append([item])
        for group in grouped:
            if len(group) < 3:
                continue
            angles = sorted(item["angle"] % (2 * math.pi) for item in group)
            gaps = np.diff([*angles, angles[0] + 2 * math.pi])
            expected = 2 * math.pi / len(group)
            closure_error = math.degrees(float(np.max(np.abs(gaps - expected))))
            clusters.append(
                {
                    "geometry_type": geometry_type,
                    "count": len(group),
                    "mean_area_mm2": round(float(np.mean([item["area"] for item in group])), 6),
                    "mean_radius_mm": round(float(np.mean([item["radius"] for item in group])), 6),
                    "mean_z_mm": round(float(np.mean([item["center"][2] for item in group])), 6),
                    "angular_closure_error_deg": round(closure_error, 6),
                    "face_ids": [item["face_id"] for item in group],
                }
            )
    return sorted(clusters, key=lambda item: (item["count"], item["mean_area_mm2"]), reverse=True)


def _dominant_bore_radius(shape, axis_direction: np.ndarray, axis_origin: np.ndarray, outer_radius: float) -> float | None:
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
    except ImportError:  # pragma: no cover
        return None
    groups: dict[float, float] = defaultdict(float)
    for face in shape.Faces():
        if face.geomType() != "CYLINDER":
            continue
        try:
            cylinder = BRepAdaptor_Surface(face.wrapped).Cylinder()
            direction = np.asarray([cylinder.Axis().Direction().X(), cylinder.Axis().Direction().Y(), cylinder.Axis().Direction().Z()])
            direction /= max(np.linalg.norm(direction), 1.0e-12)
            if abs(float(np.dot(direction, axis_direction))) < 0.999:
                continue
            location = np.asarray([cylinder.Axis().Location().X(), cylinder.Axis().Location().Y(), cylinder.Axis().Location().Z()])
            offset = np.linalg.norm(np.cross(location - axis_origin, axis_direction))
            radius = float(cylinder.Radius())
            if offset <= max(outer_radius * 1.0e-4, 1.0e-4) and radius < outer_radius * 0.6:
                groups[round(radius, 5)] += float(face.Area())
        except Exception:
            continue
    return max(groups, key=groups.get) if groups else None


def _known_source_seed(source_sha256: str) -> dict[str, Any] | None:
    bundle = load_impeller_dsl_bundle("v1_1")
    for preset in bundle.presets.values():
        if preset.get("source_metadata", {}).get("source_sha256") == source_sha256:
            return {
                "parameters": preset["parameter_values"],
                "defaults": preset["blade_to_blade_loop_family_defaults"],
                "confidence": preset.get("parameter_confidence", {}),
            }
    return None


def _generic_v11_seed(shape, source_manifest, frame, semantics):
    base_id = "radial_closed_reference_v1_1" if semantics["shroud_topology"] == "closed" else "radial_open_reference_v1_1"
    runtime = compile_impeller_runtime_preset(base_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = copy.deepcopy(runtime["resolved_blade_to_blade_loop_family_defaults"])
    outer = float(frame["outer_radius_mm"])
    bore = float(frame.get("main_bore_radius_mm") or max(outer * 0.12, 0.1))
    parameters.update(
        {
            "blade_count": int(semantics["main_blade_count"] + semantics["splitter_blade_count"]),
            "exit_radius_mm": outer,
            "inlet_radius_mm": max(bore * 1.5, outer * 0.2),
            "mounting_bore_radius_mm": bore,
            "hub_curve_height_mm": max(frame["axial_extent_mm"] * 0.65, 0.1),
            "inlet_blade_height_mm": max(frame["axial_extent_mm"] * 0.45, 0.1),
            "outlet_blade_height_mm": max(frame["axial_extent_mm"] * 0.15, 0.1),
            "blade_thickness_mm": max((outer - bore) / max(semantics["main_blade_count"] * 2.4, 1), 0.05),
        }
    )
    defaults["main_blade_count"] = int(semantics["main_blade_count"])
    defaults["splitter_blade_count"] = int(semantics["splitter_blade_count"])
    defaults["average_blade_thickness_mm"] = parameters["blade_thickness_mm"]
    defaults["maximum_blade_thickness_mm"] = parameters["blade_thickness_mm"] * 1.25
    defaults["hub_profile_rz_mm"] = _envelope_profile(shape, frame, quantile=0.2)
    defaults["tip_or_shroud_profile_rz_mm"] = _envelope_profile(shape, frame, quantile=0.8)
    confidence = {
        f"parameter_values.{name}": {
            "confidence": 0.95 if name in {"blade_count", "exit_radius_mm", "mounting_bore_radius_mm"} else 0.55,
            "basis": "exact_brep" if name in {"blade_count", "exit_radius_mm", "mounting_bore_radius_mm"} else "bounded_generic_fit",
        }
        for name in parameters
    }
    return parameters, defaults, confidence


def _envelope_profile(shape, frame, *, quantile: float) -> list[list[float]]:
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    points = np.asarray([_transform_point(vertex.Center().toTuple(), matrix) for vertex in shape.Vertices()])
    radius = np.sqrt(points[:, 0] ** 2 + points[:, 1] ** 2)
    inner = max(float(frame.get("main_bore_radius_mm") or 0.0) * 1.4, float(np.percentile(radius, 10)))
    outer = float(frame["outer_radius_mm"])
    values = []
    for center in np.linspace(inner, outer, 6):
        width = max((outer - inner) / 8.0, 1.0e-6)
        local = points[np.abs(radius - center) <= width, 2]
        z = float(np.quantile(local, quantile)) if len(local) else float(np.quantile(points[:, 2], quantile))
        values.append([round(float(center), 6), round(z, 6)])
    values.sort(key=lambda point: point[0])
    return values


def _unsupported_features(source_manifest, semantics):
    inventory = source_manifest["surface_type_inventory"]
    result = []
    if inventory.get("CYLINDER", 0) > 2:
        result.append({"feature": "auxiliary_and_stepped_cylindrical_holes", "preserved_in_v11": False})
    if inventory.get("BSPLINE", 0):
        result.append({"feature": "exact_source_bspline_face_identity", "preserved_in_v11": False, "source_face_count": inventory["BSPLINE"]})
    if inventory.get("CONE", 0) or inventory.get("TORUS", 0):
        result.append({"feature": "local_edge_treatments", "preserved_in_v11": False})
    return result


def _source_section_loop_summary(defaults):
    stations = defaults.get("span_stations_h", [0.0, 0.25, 0.5, 0.75, 1.0])
    return [
        {
            "h": float(value),
            "role": "source_measurement_target",
            "available": True,
            "mapped_fields": ["blade_skeleton_field", "thickness_field", "leading_edge_cap", "trailing_edge_cap"],
        }
        for value in stations[:5]
    ]


def _mapping_confidence(name: str) -> float:
    if name in {"blade_count", "exit_radius_mm", "mounting_bore_radius_mm"}:
        return 0.98
    if name in {"blade_thickness_mm", "blade_wrap_deg", "hub_curve_height_mm"}:
        return 0.82
    if "radius" in name or "sweep" in name or "lean" in name:
        return 0.55
    return 0.70


def _densify_polyline(points: list[list[float]], count: int) -> list[list[float]]:
    array = np.asarray(points, dtype=float)
    distances = np.linalg.norm(np.diff(array, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(distances)))
    if cumulative[-1] <= 1.0e-12:
        return [list(points[0]) for _ in range(count)]
    targets = np.linspace(0.0, cumulative[-1], count)
    return [
        [round(float(np.interp(target, cumulative, array[:, axis])), 6) for axis in range(2)]
        for target in targets
    ]


def _basis(index: int, degree: int, value: float, knots: list[float]) -> float:
    if degree == 0:
        if knots[index] <= value < knots[index + 1]:
            return 1.0
        return 1.0 if value == knots[-1] and knots[index + 1] == knots[-1] and knots[index] < knots[-1] else 0.0
    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left = 0.0 if left_denominator == 0 else (value - knots[index]) / left_denominator * _basis(index, degree - 1, value, knots)
    right = 0.0 if right_denominator == 0 else (knots[index + degree + 1] - value) / right_denominator * _basis(index + 1, degree - 1, value, knots)
    return left + right


def _rotation_to_z(direction: np.ndarray) -> np.ndarray:
    source = direction / max(np.linalg.norm(direction), 1.0e-12)
    target = np.asarray([0.0, 0.0, 1.0])
    cross = np.cross(source, target)
    sine = np.linalg.norm(cross)
    cosine = float(np.dot(source, target))
    if sine <= 1.0e-12:
        return np.eye(3) if cosine > 0 else np.diag([1.0, -1.0, -1.0])
    skew = np.asarray([[0.0, -cross[2], cross[1]], [cross[2], 0.0, -cross[0]], [-cross[1], cross[0], 0.0]])
    return np.eye(3) + skew + skew @ skew * ((1.0 - cosine) / (sine**2))


def _transform_point(point, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.asarray([*point, 1.0], dtype=float)
    return (matrix @ homogeneous)[:3]


def _export_source_stl(shape, path: Path) -> None:
    try:
        import cadquery as cq

        cq.exporters.export(shape, str(path), exportType="STL", tolerance=0.12, angularTolerance=0.16)
    except Exception as exc:  # noqa: BLE001
        raise StepAuditError("v116_step_parse_failed", f"source STEP tessellation failed: {exc}") from exc


def _stage_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    preferred = (
        "sha256",
        "solid_count",
        "face_count",
        "edge_count",
        "vertex_count",
        "method",
        "main_blade_count",
        "splitter_blade_count",
        "pitch_deg",
        "mapping_id",
        "geometry_patch_version",
        "run_id",
        "generation_id",
        "geometry_validation_status",
        "bidirectional",
    )
    return {key: value[key] for key in preferred if key in value}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True))
            stream.flush()
            os.fsync(stream.fileno())

        last_error: PermissionError | None = None
        for attempt in range(12):
            try:
                os.replace(temporary, path)
                return
            except PermissionError as exc:
                last_error = exc
                if attempt < 11:
                    time.sleep(min(0.025 * (2**attempt), 0.25))

        assert last_error is not None
        raise StepAuditError(
            "v116_audit_persistence_failed",
            f"could not atomically persist {path.name} after 12 attempts: {last_error}",
            {"path": str(path), "attempts": 12, "exception_type": type(last_error).__name__},
        ) from last_error
    finally:
        temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
