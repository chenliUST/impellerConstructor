from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.impeller_v11_2_canonical import clamped_uniform_knots
from part_rule_synthesis.impeller_v11_6_comparison_scope import (
    COMPARISON_SCOPE_CONTRACT_ID,
    build_reconstruction_surface_comparison_ledger,
)
from part_rule_synthesis import impeller_v11_6_source_frame as source_frame
from part_rule_synthesis import impeller_v11_6_periodic_blades as periodic_blades
from part_rule_synthesis import impeller_v11_6_axis_first_pipeline as axis_first_pipeline
from part_rule_synthesis import impeller_v11_6_pattern_reconstruction as pattern_reconstruction
from part_rule_synthesis.impeller_v11_6_deviation import (
    TriangleMesh,
    artifact_record,
    combine_triangle_meshes,
    compare_corresponding_mesh_regions,
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
AUDIT_IMPLEMENTATION_REVISION = "axis_first_triangle_surface_r13_2"
SOURCE_REVIEW_LINEAR_TOLERANCE_MM = 0.06
SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD = 0.08
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
    "v116_step_comparison_scope_failed",
    "v116_step_ocp_unavailable",
    "v116_step_queue_full",
    "v116_audit_persistence_failed",
    "v116_audit_interrupted",
    "v116_axis_consensus_failed",
    "v116_axis_consensus_ambiguous",
    "v116_source_sampling_budget_exceeded",
    "v116_source_sampling_extrema_not_converged",
    "v116_hub_support_classification_failed",
    "v116_hub_profile_fit_failed",
    "v116_tip_reference_inference_failed",
    "v116_shroud_topology_ambiguous",
    "v116_span_surface_ordering_failed",
    "v116_periodic_population_ambiguous",
    "v116_periodic_face_signature_contract_invalid",
    "v116_representative_blade_selection_failed",
    "v116_section_intersection_failed",
    "v116_section_loop_open",
    "v116_section_loop_correspondence_failed",
    "v116_section_tangent_flip_detected",
    "v116_thickness_field_invalid",
    "v116_root_attachment_measurement_failed",
    "v116_v112_canonical_hash_mismatch",
    "v116_v112_canonical_patch_mismatch",
    "v116_v112_forbidden_parameter",
    "v116_v112_mapping_solver_exception",
    "v116_v112_mapping_solver_failed",
    "v116_v112_material_domain_failed",
    "v116_v112_material_measurement_missing",
    "v116_v112_measurement_schema_invalid",
    "v116_v112_parameter_limit_failed",
    "v116_v112_topology_failed",
    "v116_v112_mapping_residual_exceeded",
    "v116_false_material_surface_forbidden",
}

_FINAL_AXIS_FIRST_SECTIONS = (
    "support_recovery",
    "span_measurement_lattice",
    "representative_blades",
    "v11_2_mapping",
    "pattern_instances",
    "regional_deviation",
)
_KS007G23B_SOURCE_SHA256 = (
    "1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5"
)
def _staged_axis_first_algorithm_readiness() -> dict[str, Any]:
    return {
        "status": "INCOMPLETE",
        "algorithm_ready": False,
        "cache_reusable": False,
        "completed_contract_sections": [
            "canonical_frame",
            "coarse_topology_partition",
        ],
        "missing_required_sections": list(_FINAL_AXIS_FIRST_SECTIONS),
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
                "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
                "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
                "algorithm_readiness": _staged_axis_first_algorithm_readiness(),
                "legacy_workflow_status": "PENDING",
                "axis_first_algorithm_status": "INCOMPLETE",
                "promotable": False,
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
        allowed = {
            "source.stl",
            "reconstruction.stl",
            "heatmap.json",
            "geometric-manifest.json",
        }
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
            lambda: extract_v11_review_parameters(
                source_shape, source_manifest, frame, semantics
            ),
        )
        task8_recovery_authority = (
            axis_first_pipeline.preserve_task8_reconstruction_authority(
                mapping, source_manifest["sha256"]
            )
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
            task8_recovery_authority=task8_recovery_authority,
            stage_callback=lambda stage, duration, payload: self._complete_reconstruction_stage(
                audit_id, stage_records, stage, duration, payload
            ),
        )
        reconstruction_stl = audit_dir / "reconstruction.stl"
        shutil.copyfile(reconstruction["stl_path"], reconstruction_stl)

        started = time.perf_counter()
        try:
            comparison_scope = copy.deepcopy(mapping.get("comparison_scope", {}))
            if (
                not isinstance(comparison_scope, Mapping)
                or comparison_scope.get("status") not in {"PASS", "PARTIAL_REVIEW"}
                or comparison_scope.get("coverage_complete") is not True
            ):
                raise StepAuditError(
                    "v116_step_comparison_scope_failed",
                    "source faces do not have a complete supported/excluded comparison partition",
                    {"comparison_scope": copy.deepcopy(comparison_scope)},
                )
            reconstruction_mesh = read_stl(reconstruction_stl)
            source_regions = _source_comparison_region_meshes(
                source_shape,
                source_manifest,
                comparison_scope,
                frame["source_to_canonical_matrix"],
            )
            reconstruction_regions = _reconstruction_comparison_region_meshes(
                reconstruction["surface_graph"], comparison_scope
            )
            surface_ledger = build_reconstruction_surface_comparison_ledger(
                reconstruction["surface_graph"], comparison_scope
            )
            comparison_scope["reconstruction_surface_ledger"] = copy.deepcopy(
                surface_ledger
            )
            comparison_scope["surface_coverage_complete"] = bool(
                surface_ledger.get("comparison_coverage_complete")
            )
            _, comparison_alignment = resolve_periodic_phase_alignment(
                combine_triangle_meshes(list(source_regions.values())),
                combine_triangle_meshes(list(reconstruction_regions.values())),
                int(semantics["main_blade_count"]),
            )
            alignment_matrix = _rotation_about_z_matrix(
                float(comparison_alignment["rotation_about_axis_deg"])
            )
            reconstruction_mesh = transform_mesh(
                reconstruction_mesh, alignment_matrix
            )
            aligned_reconstruction_regions = {
                role: transform_mesh(reconstructed, alignment_matrix)
                for role, reconstructed in reconstruction_regions.items()
            }
            _, instance_alignment = _phase_aligned_comparison_regions(
                source_regions,
                aligned_reconstruction_regions,
                comparison_scope,
            )
            comparison_alignment["periodic_instance_alignment"] = instance_alignment
            aligned_surface_meshes = {
                surface_id: transform_mesh(mesh, alignment_matrix)
                for surface_id, mesh in _reconstruction_surface_comparison_meshes(
                    reconstruction["surface_graph"], surface_ledger
                ).items()
            }
            surface_pairs, surface_ledger = _surface_comparison_pairs(
                source_regions,
                aligned_surface_meshes,
                surface_ledger,
                comparison_scope,
                instance_alignment,
            )
            comparison_scope["reconstruction_surface_ledger"] = copy.deepcopy(
                surface_ledger
            )
            write_binary_stl(
                reconstruction_stl,
                reconstruction_mesh,
                label=(
                    f"{reconstruction['manifest']['reconstruction_variant']} "
                    "in V1.1.6 corresponding-surface phase"
                ),
            )
            comparison, heatmap = compare_corresponding_mesh_regions(surface_pairs)
            comparison["scope"] = copy.deepcopy(comparison_scope)
            comparison["surface_ledger"] = copy.deepcopy(surface_ledger)
            comparison["alignment_applied_to"] = (
                "supported_reconstruction_regions_and_full_review_mesh"
            )
            heatmap_path = audit_dir / "heatmap.json"
            write_heatmap(heatmap_path, heatmap)
            geometric_manifest_path = audit_dir / "geometric-manifest.json"
            _write_geometric_manifest(
                geometric_manifest_path,
                reconstruction["surface_graph"],
                alignment_matrix=alignment_matrix,
                comparison_alignment=comparison_alignment,
                surface_ledger=surface_ledger,
                reconstruction_variant=reconstruction["manifest"][
                    "reconstruction_variant"
                ],
            )
        except StepAuditError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StepAuditError("v116_step_deviation_failed", str(exc)) from exc
        self._complete_reconstruction_stage(
            audit_id,
            stage_records,
            "deviation_measured",
            (time.perf_counter() - started) * 1000.0,
            {
                "reconstruction_to_corresponding_source": comparison[
                    "reconstruction_to_corresponding_source"
                ],
                "comparison_alignment": comparison_alignment,
            },
        )

        artifacts = {
            "source_stl": artifact_record(
                source_stl, fidelity="tessellated_from_source_brep", media_type="model/stl"
            ),
            "reconstruction_stl": artifact_record(
                reconstruction_stl,
                fidelity=reconstruction["manifest"]["reconstruction_variant"],
                media_type="model/stl",
            ),
            "heatmap": artifact_record(
                heatmap_path,
                fidelity=(
                    "corresponding_reconstruction_samples_to_source_triangle_"
                    "surfaces_unsigned_deviation"
                ),
                media_type="application/json",
            ),
            "geometric_manifest": artifact_record(
                geometric_manifest_path,
                fidelity=(
                    "sampled_"
                    + reconstruction["manifest"]["reconstruction_variant"]
                    + "_surface_graph_manifest"
                ),
                media_type="application/json",
            ),
        }
        self._complete_reconstruction_stage(audit_id, stage_records, "complete", 0.0, {})
        axis_first_manifest = _axis_first_section_reconstruction_manifest(
            frame=frame,
            semantics=semantics,
            mapping=mapping,
            reconstruction=reconstruction["manifest"],
            comparison=comparison,
        )
        disposition = _axis_first_algorithm_disposition(mapping)
        acceptance_evaluation = (
            _evaluate_axis_first_acceptance(
                mapping, reconstruction["manifest"], comparison
            )
            if source_manifest.get("sha256") == _KS007G23B_SOURCE_SHA256
            else None
        )
        manifest = {
            "contract_id": AUDIT_CONTRACT_ID,
            "runtime_release_version": AUDIT_RUNTIME_VERSION,
            "implementation_revision": AUDIT_IMPLEMENTATION_REVISION,
            "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
            "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
            "audit_id": audit_id,
            "status": "PASS",
            "status_scope": disposition["status_scope"],
            "legacy_workflow_status": "PASS",
            "axis_first_algorithm_status": disposition[
                "axis_first_algorithm_status"
            ],
            "promotable": disposition["promotable"],
            "reconstruction_disposition": disposition[
                "reconstruction_disposition"
            ],
            "algorithm_readiness": copy.deepcopy(
                axis_first_manifest["algorithm_readiness"]
            ),
            "units": "mm",
            "source": source_manifest,
            "frame": frame,
            "semantics": semantics,
            "parameter_mapping": mapping,
            "reconstruction": reconstruction["manifest"],
            "comparison_alignment": comparison_alignment,
            "comparison_scope": copy.deepcopy(comparison_scope),
            "comparison": comparison,
            "acceptance_evaluation": acceptance_evaluation,
            "axis_first_section_reconstruction": axis_first_manifest,
            "artifacts": artifacts,
            "stages": stage_records,
            "limitations": [
                "Source STEP remains the B-Rep authority; displayed source geometry is a recorded tessellation.",
                "V1.1.2 reconstruction does not preserve source face identity, local holes, splines or manufacturing detail.",
                "When enabled, the V1.1.6 adaptive review extension changes station, thickness, pose and attachment fields while retaining V1.1.2 as the base geometry contract.",
                "Periodic phase alignment rotates only about the confirmed axis; it does not fit translation or scale.",
                "The V1.1.2 reconstruction is an open review surface graph, so its signed mesh volume is not comparable to the source solid volume.",
                "Deviation is an unsigned reconstruction-to-corresponding-source bounded mesh-sample comparison, not certified CAD metrology.",
                "Keyways, splines, auxiliary holes, non-planar hub-bottom relief and bosses are explicitly outside the V1.1.2 comparison scope.",
                "A rejected review candidate is retained only to diagnose frozen V1.1.2 representational loss; it is not an accepted constructor mapping.",
            ],
        }
        manifest_path = audit_dir / "manifest.json"
        _atomic_json(manifest_path, manifest)
        manifest_sha256 = _file_sha256(manifest_path)
        status = self.status(audit_id)
        status.update(
            {
                "status": "PASS",
                "legacy_workflow_status": "PASS",
                "axis_first_algorithm_status": disposition[
                    "axis_first_algorithm_status"
                ],
                "promotable": disposition["promotable"],
                "reconstruction_disposition": disposition[
                    "reconstruction_disposition"
                ],
                "current_stage": "complete",
                "completed_stages": list(AUDIT_STAGES),
                "finished_at": _now(),
                "manifest_available": True,
                "manifest_sha256": manifest_sha256,
                "algorithm_readiness": copy.deepcopy(
                    axis_first_manifest["algorithm_readiness"]
                ),
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
            same_revision = (
                status.get("implementation_revision") == AUDIT_IMPLEMENTATION_REVISION
                and status.get("algorithm_revision") == AUDIT_IMPLEMENTATION_REVISION
            )
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
            status.get("audit_id") == audit_dir.name
            and manifest.get("audit_id") == audit_dir.name
            and status.get("source", {}).get("sha256")
            == manifest.get("source", {}).get("sha256")
            and status.get("contract_id") == AUDIT_CONTRACT_ID
            and status.get("implementation_revision") == AUDIT_IMPLEMENTATION_REVISION
            and status.get("algorithm_revision") == AUDIT_IMPLEMENTATION_REVISION
            and status.get("canonical_geometry_version") == CANONICAL_GEOMETRY_VERSION
            and manifest.get("contract_id") == AUDIT_CONTRACT_ID
            and manifest.get("implementation_revision") == AUDIT_IMPLEMENTATION_REVISION
            and manifest.get("algorithm_revision") == AUDIT_IMPLEMENTATION_REVISION
            and manifest.get("canonical_geometry_version") == CANONICAL_GEOMETRY_VERSION
            and _manifest_digest_matches_status(manifest_path, status)
            and _axis_first_cache_manifest_complete(manifest)
            and manifest.get("comparison_alignment", {}).get("method")
            == "bounded_symmetric_periodic_phase_search"
            and _audit_artifacts_match_manifest(audit_dir, manifest)
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
        "tessellation": {
            "linear_tolerance_mm": SOURCE_REVIEW_LINEAR_TOLERANCE_MM,
            "angular_tolerance_rad": SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD,
            "authority": False,
            "purpose": "r13_dense_review_and_corresponding_surface_deviation",
        },
    }
    return shape, source_manifest


def resolve_canonical_frame(shape, source_manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        frame = source_frame.resolve_canonical_frame(shape, source_manifest)
        frame["coarse_topology_partition"] = source_frame.coarse_periodic_face_partition(
            shape, source_manifest, frame
        )
        direction = np.asarray(frame["source_axis_direction"], dtype=float)
        origin = np.asarray(frame["source_axis_origin_mm"], dtype=float)
        bore_radius = _dominant_bore_radius(shape, direction, origin, float(frame["outer_radius_mm"]))
        if bore_radius is not None:
            frame["main_bore_radius_mm"] = round(bore_radius, 6)
        return frame
    except source_frame.AxisConsensusError as exc:
        raise StepAuditError(exc.reason, str(exc), exc.details) from exc


def classify_impeller_semantics(shape, source_manifest: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    records = source_manifest["faces"]
    partition = frame.get("coarse_topology_partition")
    if not isinstance(partition, dict):
        partition = source_frame.coarse_periodic_face_partition(
            shape, source_manifest, frame
        )
        frame["coarse_topology_partition"] = partition
    try:
        populations = periodic_blades.recover_periodic_blade_populations(
            partition.get("face_signatures", ()), source_manifest.get("adjacency", {})
        )
    except periodic_blades.PeriodicBladeRecoveryError as exc:
        reason = (
            exc.reason
            if exc.reason in FAILURE_REASONS
            else "v116_periodic_population_ambiguous"
        )
        raise StepAuditError(
            reason,
            str(exc),
            {"upstream_reason": exc.reason, **dict(exc.evidence)},
        ) from exc

    signature_by_id = {
        item["source_face_id"]: item for item in partition["face_signatures"]
    }
    population_face_ids = {
        face_id
        for population in populations["populations"]
        for instance in population["instances"]
        for face_id in instance["source_face_ids"]
    }
    signature_areas: dict[str, list[float]] = defaultdict(list)
    for face_id in population_face_ids:
        signature = signature_by_id[face_id]
        signature_areas[signature["signature_hash"]].append(
            float(signature["area_mm2"])
        )
    side_signatures = [
        signature_hash
        for signature_hash, _areas in sorted(
            signature_areas.items(),
            key=lambda item: (-float(np.mean(item[1])), item[0]),
        )[:2]
    ]
    if not side_signatures:
        raise StepAuditError(
            "v116_step_blade_pair_failed",
            "strict periodic components do not contain a blade-side signature family",
        )
    side_a_signature = side_signatures[0]
    side_b_signature = side_signatures[1] if len(side_signatures) > 1 else None
    side_ids = {
        face_id
        for face_id in population_face_ids
        if signature_by_id[face_id]["signature_hash"] in side_signatures
    }
    face_roles: dict[str, dict[str, Any]] = {}
    periodic_ids = population_face_ids
    adjacency = source_manifest["adjacency"]
    outer_radius = float(frame["outer_radius_mm"])
    max_side_area = max(
        float(signature_by_id[face_id]["area_mm2"]) for face_id in side_ids
    )
    for record in records:
        face_id = record["face_id"]
        center = _transform_point(record["centroid_mm"], matrix)
        radius = math.hypot(center[0], center[1])
        role = "other_material"
        confidence = 0.45
        evidence = ["default_unmatched_material_face"]
        signature_hash = signature_by_id[face_id]["signature_hash"]
        if face_id in periodic_ids and signature_hash == side_a_signature:
            role, confidence, evidence = "blade_side_a", 0.96, ["largest_repeated_freeform_area_family"]
        elif (
            face_id in periodic_ids
            and side_b_signature is not None
            and signature_hash == side_b_signature
        ):
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
        elif record["area_mm2"] > max_side_area * populations["main_blade_count"] * 0.15:
            role, confidence, evidence = "hub_support_or_solid_wall", 0.76, ["large_nonperiodic_material_face"]
        face_roles[face_id] = {
            "role": role,
            "confidence": round(confidence, 3),
            "evidence": evidence,
            "alternatives": [] if confidence >= 0.8 else ["hub_support", "blade_attachment", "other_material"],
        }
    return {
        "method": "surface_type_area_periodicity_adjacency_v1_1_6",
        "main_blade_count": int(populations["main_blade_count"]),
        "splitter_blade_count": int(populations["splitter_blade_count"]),
        "pitch_deg": float(populations["main"]["pitch_deg"]),
        "splitter_phase_deg": (
            None
            if populations["splitter"] is None
            else populations["splitter"]["phase_relative_to_main_deg"]
        ),
        "shroud_topology": "undetermined",
        "shroud_topology_status": "pending_authenticated_support_recovery",
        "pressure_suction_assignment": (
            "orientation_neutral_blade_side_a_b"
            if side_b_signature is not None
            else "pending_representative_blade_surface_pair_recovery"
        ),
        "periodic_clusters": populations["populations"],
        "periodic_population_recovery": populations,
        "face_roles": face_roles,
        "classified_face_count": len(face_roles),
        "source_face_count": len(records),
    }


def extract_v11_parameters(shape, source_manifest: dict[str, Any], frame: dict[str, Any], semantics: dict[str, Any]) -> dict[str, Any]:
    try:
        return axis_first_pipeline.extract_v11_parameters(
            shape, source_manifest, frame, semantics
        )
    except axis_first_pipeline.AxisFirstPipelineError as exc:
        raise StepAuditError(exc.reason, str(exc), copy.deepcopy(exc.details)) from exc


def extract_v11_review_parameters(
    shape,
    source_manifest: dict[str, Any],
    frame: dict[str, Any],
    semantics: dict[str, Any],
) -> dict[str, Any]:
    try:
        return axis_first_pipeline.extract_v11_review_parameters(
            shape, source_manifest, frame, semantics
        )
    except axis_first_pipeline.AxisFirstPipelineError as exc:
        raise StepAuditError(exc.reason, str(exc), copy.deepcopy(exc.details)) from exc


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
    task8_recovery_authority: Mapping[str, Any],
    stage_callback,
) -> dict[str, Any]:
    canonical = _validated_mapping_canonical_payload(mapping)
    defaults = copy.deepcopy(mapping["resolved_blade_to_blade_loop_family_defaults"])
    adaptive_extension = defaults.get("v116_step_reconstruction_extension")
    reconstruction_variant = (
        "v1.1.6_adaptive_review_extension_r1"
        if isinstance(adaptive_extension, Mapping)
        and adaptive_extension.get("status") == "PASS"
        else "frozen_v1.1.2_review_baseline"
    )
    _apply_bounded_audit_sampling(defaults)
    parameters = copy.deepcopy(mapping["parameters"])
    seed_preset = "radial_closed_reference_v1_1" if defaults.get("tip_attachment_mode") == "closed_shroud_attachment" else "radial_open_reference_v1_1"
    runtime = compile_impeller_runtime_preset(
        seed_preset,
        mapper_approved_canonical_payload=canonical,
        mapper_approved_canonical_hash_sha256=mapping[
            "canonical_payload_hash_sha256"
        ],
    )
    if runtime.get("geometry_patch_version") != CANONICAL_GEOMETRY_VERSION:
        raise StepAuditError("v116_step_reconstruction_validation_failed", "audit seed is not V1.1.2 geometry")
    for name, value in parameters.items():
        if name in runtime["parameters"]:
            runtime["parameters"][name]["default"] = value
    _disable_zero_radius_legacy_transition_policies(runtime, parameters)
    runtime["resolved_parameter_defaults"] = copy.deepcopy(parameters)
    runtime["resolved_blade_to_blade_loop_family_defaults"] = defaults
    runtime["canonical_input_source"] = canonical.get(
        "canonical_input_source", "v116_bounded_measurement_mapping"
    )
    runtime["runtime_release_version"] = AUDIT_RUNTIME_VERSION
    runtime["source_metadata"] = {
        "source_kind": "uploaded_step_brep",
        "source_sha256": source_manifest["sha256"],
        "authority": "source STEP is authoritative; V1.1.2 output is review-grade",
        "base_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "reconstruction_variant": reconstruction_variant,
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
        validation_report = copy.deepcopy(
            final_run.manifest.get("geometry_validation_report", {})
        )
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "V1.1.2 reconstruction failed geometry validation",
            {
                "status": final_run.manifest.get("geometry_validation_status"),
                "geometry_validation_report": validation_report,
            },
        )
    surface_graph = final_run.manifest.get("geometry", {}).get("surface_graph", {})
    try:
        surface_graph, pattern_manifest = (
            pattern_reconstruction.validate_mapped_pattern_reconstruction(
                surface_graph,
                mapping,
                source_manifest,
                task8_recovery_authority=task8_recovery_authority,
            )
        )
    except pattern_reconstruction.PatternReconstructionError as exc:
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            f"V1.1.6 periodic/material reconstruction failed: {exc}",
            {"upstream_reason": exc.reason, **copy.deepcopy(exc.details)},
        ) from exc
    stl_path = audit_dir / "reconstruction-runtime.stl"
    _write_surface_graph_stl(surface_graph, stl_path)
    summary = {
        "authority": "review_grade_step_reconstruction",
        "base_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "reconstruction_variant": reconstruction_variant,
        "geometry_version": final_run.manifest.get("geometry_version"),
        "geometry_patch_version": final_run.manifest.get("geometry_patch_version"),
        "runtime_release_version": AUDIT_RUNTIME_VERSION,
        "geometry_validation_status": final_run.manifest.get("geometry_validation_status"),
        "run_id": final_run.run_id,
        "generation_id": final_run.manifest.get("generation_id"),
        "constructor_stages": stage_manifests,
        "parameters": final_run.manifest.get("parameters", {}),
        "surface_count": len(surface_graph.get("surfaces", [])),
        "pattern_material_contract": axis_first_pipeline._jsonable(pattern_manifest),
    }
    return {
        "manifest": summary,
        "stl_path": stl_path,
        "surface_graph": surface_graph,
    }


def _axis_first_algorithm_disposition(mapping: Mapping[str, Any]) -> dict[str, Any]:
    mapping_status = mapping.get("mapping_status")
    if mapping_status == "REJECTED_REVIEW_CANDIDATE":
        failed_terms = copy.deepcopy(list(mapping.get("failed_terms", ())))
        rejection = copy.deepcopy(dict(mapping.get("rejection", {})))
        return {
            "status_scope": "axis_first_rejected_review_candidate",
            "axis_first_algorithm_status": "REJECTED",
            "promotable": False,
            "reconstruction_disposition": "review_only_not_promotable",
            "algorithm_readiness": {
                "status": "REJECTED",
                "algorithm_ready": False,
                "cache_reusable": False,
                "completed_contract_sections": [
                    "canonical_frame",
                    "support_recovery",
                    "periodic_populations",
                    "span_measurement_lattice",
                    "representative_blades",
                    "v11_2_mapping",
                    "pattern_instances",
                    "corresponding_surface_deviation",
                ],
                "missing_required_sections": [
                    "accepted_corresponding_surface_baseline"
                ],
                "rejection_reason": rejection.get(
                    "reason", "v116_v112_mapping_residual_exceeded"
                ),
                "failed_terms": failed_terms,
            },
        }
    return {
        "status_scope": "axis_first_algorithm_staged",
        "axis_first_algorithm_status": "INCOMPLETE",
        "promotable": False,
        "reconstruction_disposition": "staged_not_promotable",
        "algorithm_readiness": _staged_axis_first_algorithm_readiness(),
    }


def _evaluate_axis_first_acceptance(
    mapping: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    pattern_contract = reconstruction.get("pattern_material_contract", {})
    pattern = pattern_contract.get("pattern", {})
    material = pattern_contract.get("material", {})
    topology_pass = bool(
        pattern_contract.get("status") == "PASS"
        and pattern.get("main_blade_count") == 13
        and pattern.get("splitter_blade_count") == 0
        and pattern.get("collision_status") == "PASS"
        and pattern.get("source_topology_separated") is True
        and pattern.get("exact_brep_collision_checked") is True
        and pattern.get("exact_brep_collision_free") is True
        and material.get("mode") == "open"
        and material.get("material_shroud") is None
        and material.get("material_shroud_area_mm2") in {None, 0, 0.0}
    )
    mapping_pass = bool(
        mapping.get("mapping_status") == "PASS"
        and mapping.get("promotion", {}).get("promotable") is True
    )
    return {
        "contract": "ks007g23b_axis_first_acceptance_v2_corresponding_surface_review",
        "status": "NOT_EVALUATED",
        "promotable": False,
        "topology": {
            "status": "PASS" if topology_pass else "FAIL",
            "expected": {"mode": "open", "main": 13, "splitter": 0},
            "material_shroud_forbidden": True,
        },
        "mapping": {
            "status": "PASS" if mapping_pass else "FAIL",
            "mapping_status": mapping.get("mapping_status"),
            "failed_terms": copy.deepcopy(list(mapping.get("failed_terms", ()))),
        },
        "comparison": {
            "contract_id": comparison.get("contract_id"),
            "status": "MEASURED_REVIEW_ONLY",
            "reconstruction_to_corresponding_source": copy.deepcopy(
                comparison.get("reconstruction_to_corresponding_source", {})
            ),
            "corresponding_source_to_reconstruction": copy.deepcopy(
                comparison.get("corresponding_source_to_reconstruction", {})
            ),
            "symmetric_corresponding_sample_distribution": copy.deepcopy(
                comparison.get("symmetric_corresponding_sample_distribution", {})
            ),
            "baseline_status": "UNAVAILABLE_NON_COMPARABLE_WITH_LEGACY_GLOBAL_METRICS",
            "reason": (
                "the previous baseline included unsupported local features and global "
                "silhouettes; a new corresponding-surface baseline has not been approved"
            ),
        },
    }
def _disable_zero_radius_legacy_transition_policies(
    runtime: dict[str, Any], parameters: Mapping[str, Any]
) -> None:
    """Keep legacy policy validation from overriding canonical V1.1.2 geometry."""

    for family in runtime.get("edge_families", {}).values():
        radius_parameter = family.get("default_radius_parameter")
        radius = parameters.get(radius_parameter)
        if (
            isinstance(radius, (int, float))
            and not isinstance(radius, bool)
            and float(radius) <= 0.0
        ):
            family["default_treatment"] = "none"
            family["default_continuity"] = "G0"
    resolved_parameters = {
        name: specification.get("default")
        for name, specification in runtime.get("parameters", {}).items()
    }
    resolved_parameters.update(parameters)
    runtime["transition_policy_defaults"] = resolve_transition_policies(
        runtime.get("edge_families", {}),
        resolved_parameters,
    )


def _canonical_payload_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_mapping_canonical_payload(mapping: Mapping[str, Any]) -> dict[str, Any]:
    canonical = mapping.get("regenerated_canonical_payload")
    expected = mapping.get("canonical_payload_hash_sha256")
    if not isinstance(canonical, Mapping) or not isinstance(expected, str):
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "mapping lacks an approved canonical payload and hash",
        )
    if canonical.get("canonical_payload_version") != CANONICAL_GEOMETRY_VERSION:
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "approved canonical payload is not geometry patch V1.1.2",
        )
    actual = _canonical_payload_hash(canonical)
    if actual != expected:
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "approved canonical payload hash does not match the mapper evidence",
            {"expected_sha256": expected, "actual_sha256": actual},
        )
    return copy.deepcopy(dict(canonical))


def _apply_bounded_audit_sampling(defaults: dict[str, Any]) -> None:
    policy = {
        "side_sample_count": 129,
        "edge_cap_sample_count": 65,
        "surface_span_sample_count": 33,
        "root_short_direction_sample_count": 17,
        "closed_shroud_short_direction_sample_count": 17,
        "profile_revolve_sample_count": 129,
        "theta_sample_count": 181,
        "hub_solid_radial_sample_count": 33,
        "hub_solid_axial_sample_count": 33,
    }
    for key, review_count in policy.items():
        defaults[key] = review_count
    defaults["v1_1_6_audit_sampling_policy"] = {
        "mode": "r13_dense_review_mesh",
        "resolved_counts": policy,
        "source_linear_tolerance_mm": SOURCE_REVIEW_LINEAR_TOLERANCE_MM,
        "source_angular_tolerance_rad": SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD,
        "changes_geometry_math": False,
    }


def _write_surface_graph_stl(surface_graph: dict[str, Any], path: Path) -> None:
    from part_rule_synthesis.impeller_surface_graph_export import triangulate_surface_graph

    triangulation = triangulate_surface_graph(
        _material_export_surface_graph(surface_graph),
        view_id="cad_review_360",
    )
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


def _material_export_surface_graph(surface_graph: Mapping[str, Any]) -> dict[str, Any]:
    graph = copy.deepcopy(dict(surface_graph))
    graph["surfaces"] = [
        surface
        for surface in graph.get("surfaces", [])
        if surface.get("export_default") != "excluded"
        and surface.get("material") is not False
    ]
    return graph


def _write_geometric_manifest(
    path: Path,
    surface_graph: Mapping[str, Any],
    *,
    alignment_matrix,
    comparison_alignment: Mapping[str, Any],
    surface_ledger: Mapping[str, Any] | None = None,
    reconstruction_variant: str = "frozen_v1.1.2_review_baseline",
) -> None:
    matrix = np.asarray(alignment_matrix, dtype=float)
    ledger_by_surface = {
        str(record.get("surface_id")): dict(record)
        for record in (surface_ledger or {}).get("surfaces", ())
        if isinstance(record, Mapping) and record.get("surface_id")
    }
    surfaces = []
    for surface in _material_export_surface_graph(surface_graph).get(
        "surfaces", ()
    ):
        uv_grid = surface.get("uv_grid")
        if not isinstance(uv_grid, list) or len(uv_grid) < 2:
            continue
        transformed_rows = []
        for row in uv_grid:
            if not isinstance(row, list) or len(row) < 2:
                transformed_rows = []
                break
            transformed_rows.append(
                [
                    [round(float(value), 6) for value in _transform_point(point, matrix)]
                    for point in row
                ]
            )
        if not transformed_rows:
            continue
        surfaces.append(
            {
                "id": str(surface.get("id", "")),
                "role": str(surface.get("role", "")),
                "face_family": str(surface.get("face_family", "")),
                "material": surface.get("material", True) is not False,
                "uv_grid": transformed_rows,
                "display": copy.deepcopy(dict(surface.get("display", {}))),
                "comparison": copy.deepcopy(
                    ledger_by_surface.get(
                        str(surface.get("id", "")),
                        {
                            "disposition": "FAILED_UNRESOLVED",
                            "reason": "surface_comparison_ledger_missing",
                        },
                    )
                ),
            }
        )
    if not surfaces:
        raise StepAuditError(
            "v116_step_reconstruction_validation_failed",
            "surface graph produced no Geometric Manifest surfaces",
        )
    payload = {
        "contract_id": "impeller_v1_1_6_geometric_manifest_v2",
        "runtime_release_version": AUDIT_RUNTIME_VERSION,
        "base_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "reconstruction_variant": str(reconstruction_variant),
        "geometry_patch_version": CANONICAL_GEOMETRY_VERSION,
        "coordinate_system": "canonical_axis_frame_xyz_mm",
        "units": "mm",
        "fidelity": "sampled_review_grade_surface_graph_not_certified_brep",
        "render_contract": {
            "shade": "semi_transparent_surface_graph",
            "wire": "uv_iso_lines_only",
            "triangle_edges_forbidden": True,
        },
        "comparison_alignment": copy.deepcopy(dict(comparison_alignment)),
        "surface_comparison_ledger": copy.deepcopy(dict(surface_ledger or {})),
        "surface_count": len(surfaces),
        "surfaces": surfaces,
    }
    _atomic_json(path, payload)


def _source_comparison_region_meshes(
    shape,
    source_manifest: Mapping[str, Any],
    comparison_scope: Mapping[str, Any],
    source_to_canonical_matrix,
) -> dict[str, TriangleMesh]:
    face_records = {
        str(record["face_id"]): int(record["source_entity_index"])
        for record in source_manifest.get("faces", ())
    }
    faces = shape.Faces()
    grouped_ids: dict[str, list[str]] = defaultdict(list)
    for record in comparison_scope.get("included_surfaces", ()):
        grouped_ids[
            str(record.get("comparison_region_id") or record["reconstruction_role"])
        ].append(
            str(record["source_face_id"])
        )
    tessellation = source_manifest.get("tessellation", {})
    linear_tolerance = float(tessellation.get("linear_tolerance_mm", 0.12))
    angular_tolerance = float(tessellation.get("angular_tolerance_rad", 0.16))
    result = {}
    for role, source_ids in sorted(grouped_ids.items()):
        missing = sorted(set(source_ids) - set(face_records))
        if missing:
            raise StepAuditError(
                "v116_step_comparison_scope_failed",
                f"comparison role {role} references unknown source faces",
                {"role": role, "missing_source_face_ids": missing},
            )
        native = _tessellate_cadquery_faces(
            [faces[face_records[source_id]] for source_id in source_ids],
            linear_tolerance=linear_tolerance,
            angular_tolerance=angular_tolerance,
        )
        result[role] = transform_mesh(native, source_to_canonical_matrix)
    if not result:
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "comparison scope contains no supported source regions",
        )
    return result


def _reconstruction_comparison_region_meshes(
    surface_graph: Mapping[str, Any], comparison_scope: Mapping[str, Any]
) -> dict[str, TriangleMesh]:
    region_records = {}
    for record in comparison_scope.get("included_surfaces", ()):
        region_id = str(
            record.get("comparison_region_id") or record["reconstruction_role"]
        )
        region_records.setdefault(region_id, record)
    result = {}
    for region_id, record in sorted(region_records.items()):
        role = str(record["reconstruction_role"])
        blade_index = record.get("reconstruction_blade_index")
        blade_class = record.get("periodic_population")
        blade_pair_index = record.get("reconstruction_blade_pair_index")
        selected = [
            surface
            for surface in _material_export_surface_graph(surface_graph).get(
                "surfaces", ()
            )
            if _surface_matches_comparison_role(surface, role)
            and (
                blade_pair_index is None
                or (
                    str(surface.get("blade_class", "")) == str(blade_class)
                    and surface.get("blade_pair_index") == int(blade_pair_index)
                )
                or (
                    surface.get("blade_class") is None
                    and blade_index is not None
                    and _surface_blade_index(surface) == int(blade_index)
                )
            )
        ]
        if not selected:
            raise StepAuditError(
                "v116_step_comparison_scope_failed",
                f"V1.1.2 reconstruction has no counterpart for source region {region_id}",
                {
                    "comparison_region_id": region_id,
                    "reconstruction_role": role,
                    "reconstruction_blade_index": blade_index,
                    "periodic_population": blade_class,
                    "reconstruction_blade_pair_index": blade_pair_index,
                },
            )
        graph = copy.deepcopy(dict(surface_graph))
        graph["surfaces"] = copy.deepcopy(selected)
        result[region_id] = _surface_graph_triangle_mesh(graph)
    return result


def _reconstruction_surface_comparison_meshes(
    surface_graph: Mapping[str, Any], surface_ledger: Mapping[str, Any]
) -> dict[str, TriangleMesh]:
    evaluated_ids = {
        str(record["surface_id"])
        for record in surface_ledger.get("surfaces", ())
        if record.get("disposition") == "EVALUATED"
    }
    material_surfaces = {
        str(surface.get("id", "")): surface
        for surface in _material_export_surface_graph(surface_graph).get(
            "surfaces", ()
        )
    }
    missing = sorted(evaluated_ids - set(material_surfaces))
    if missing:
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "surface ledger references unavailable reconstruction surfaces",
            {"missing_surface_ids": missing},
        )
    result = {}
    for surface_id in sorted(evaluated_ids):
        graph = copy.deepcopy(dict(surface_graph))
        graph["surfaces"] = [copy.deepcopy(material_surfaces[surface_id])]
        result[surface_id] = _surface_graph_triangle_mesh(graph)
    return result


def _surface_comparison_pairs(
    source_regions: Mapping[str, TriangleMesh],
    reconstruction_surfaces: Mapping[str, TriangleMesh],
    surface_ledger: Mapping[str, Any],
    comparison_scope: Mapping[str, Any],
    instance_alignment: Mapping[str, Any],
) -> tuple[dict[str, tuple[TriangleMesh, TriangleMesh]], dict[str, Any]]:
    reconstruction_to_source = {
        str(key): str(value)
        for key, value in instance_alignment.get(
            "reconstruction_to_source_region_ids", {}
        ).items()
    }
    source_faces_by_region: dict[str, list[str]] = defaultdict(list)
    for record in comparison_scope.get("included_surfaces", ()):
        region_id = str(
            record.get("comparison_region_id") or record.get("reconstruction_role")
        )
        source_faces_by_region[region_id].append(str(record["source_face_id"]))

    updated_records = []
    pairs: dict[str, tuple[TriangleMesh, TriangleMesh]] = {}
    for raw_record in surface_ledger.get("surfaces", ()):
        record = copy.deepcopy(dict(raw_record))
        if record.get("disposition") != "EVALUATED":
            updated_records.append(record)
            continue
        surface_id = str(record["surface_id"])
        reconstruction_region_id = str(record["comparison_region_id"])
        source_region_id = reconstruction_to_source.get(
            reconstruction_region_id, reconstruction_region_id
        )
        if (
            source_region_id not in source_regions
            or surface_id not in reconstruction_surfaces
        ):
            record.update(
                {
                    "disposition": "FAILED_UNRESOLVED",
                    "reason": "aligned_surface_correspondence_unresolved",
                    "aligned_source_comparison_region_id": source_region_id,
                }
            )
            updated_records.append(record)
            continue
        record["aligned_source_comparison_region_id"] = source_region_id
        record["source_face_ids"] = sorted(source_faces_by_region[source_region_id])
        pairs[surface_id] = (
            source_regions[source_region_id],
            reconstruction_surfaces[surface_id],
        )
        updated_records.append(record)

    updated = copy.deepcopy(dict(surface_ledger))
    updated["surfaces"] = updated_records
    updated["evaluated_surface_count"] = sum(
        record.get("disposition") == "EVALUATED" for record in updated_records
    )
    updated["excluded_surface_count"] = sum(
        record.get("disposition") == "EXCLUDED_NOT_EVALUATED"
        for record in updated_records
    )
    updated["unresolved_surface_count"] = sum(
        record.get("disposition") == "FAILED_UNRESOLVED"
        for record in updated_records
    )
    updated["comparison_coverage_complete"] = (
        updated["unresolved_surface_count"] == 0
    )
    updated["status"] = (
        "PASS" if updated["comparison_coverage_complete"] else "REJECTED"
    )
    if not pairs:
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "surface comparison ledger contains no evaluated surface pairs",
            {"surface_ledger": updated},
        )
    return pairs, updated


def _paired_comparison_regions(
    source_regions: Mapping[str, TriangleMesh],
    reconstruction_regions: Mapping[str, TriangleMesh],
) -> dict[str, tuple[TriangleMesh, TriangleMesh]]:
    source_roles = set(source_regions)
    reconstruction_roles = set(reconstruction_regions)
    if source_roles != reconstruction_roles:
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "source and reconstruction comparison roles do not match",
            {
                "source_only_roles": sorted(source_roles - reconstruction_roles),
                "reconstruction_only_roles": sorted(
                    reconstruction_roles - source_roles
                ),
            },
        )
    return {
        role: (source_regions[role], reconstruction_regions[role])
        for role in sorted(source_roles)
    }


def _phase_aligned_comparison_regions(
    source_regions: Mapping[str, TriangleMesh],
    reconstruction_regions: Mapping[str, TriangleMesh],
    comparison_scope: Mapping[str, Any],
) -> tuple[dict[str, tuple[TriangleMesh, TriangleMesh]], dict[str, Any]]:
    """Apply one cyclic instance offset per blade population after phase alignment."""

    base_pairs = _paired_comparison_regions(source_regions, reconstruction_regions)
    records = {
        str(record.get("comparison_region_id") or record["reconstruction_role"]): record
        for record in comparison_scope.get("included_surfaces", ())
    }
    periodic_records = [
        record
        for region_id, record in records.items()
        if region_id in source_regions
        and record.get("periodic_instance_id") not in {None, ""}
    ]
    if not periodic_records:
        return base_pairs, {
            "method": "no_periodic_instance_regions",
            "populations": {},
            "reconstruction_to_source_region_ids": {
                region_id: region_id for region_id in base_pairs
            },
        }

    result = {
        region_id: pair
        for region_id, pair in base_pairs.items()
        if records.get(region_id, {}).get("periodic_instance_id") in {None, ""}
    }
    nonperiodic_assignments = {region_id: region_id for region_id in result}
    diagnostics: dict[str, Any] = {}
    reconstruction_to_source = dict(nonperiodic_assignments)
    populations = sorted(
        {str(record.get("periodic_population", "periodic")) for record in periodic_records}
    )
    for population in populations:
        population_records = [
            record
            for record in periodic_records
            if str(record.get("periodic_population", "periodic")) == population
        ]
        roles = sorted({str(record["reconstruction_role"]) for record in population_records})
        reference_role = "blade_sides" if "blade_sides" in roles else roles[0]
        reference_records = [
            record
            for record in population_records
            if record["reconstruction_role"] == reference_role
        ]
        shift, score = _best_periodic_cyclic_shift(
            source_regions, reconstruction_regions, reference_records
        )
        population_count = len(reference_records)
        role_counts = {}
        for role in roles:
            role_records = sorted(
                (record for record in population_records if record["reconstruction_role"] == role),
                key=lambda record: (
                    int(record.get("periodic_lattice_index", 0)),
                    str(record.get("periodic_instance_id", "")),
                ),
            )
            reconstruction_order = sorted(
                role_records,
                key=lambda record: int(record.get("reconstruction_blade_pair_index", 0)),
            )
            if (
                len(role_records) != population_count
                or len(reconstruction_order) != population_count
            ):
                raise StepAuditError(
                    "v116_step_comparison_scope_failed",
                    f"periodic comparison role {role} lacks complete population coverage",
                    {
                        "periodic_population": population,
                        "reference_instance_count": population_count,
                        "role_instance_count": len(role_records),
                    },
                )
            for index, source_record in enumerate(role_records):
                source_region_id = str(source_record["comparison_region_id"])
                reconstructed_record = reconstruction_order[(index + shift) % len(reconstruction_order)]
                reconstructed_region_id = str(reconstructed_record["comparison_region_id"])
                result[source_region_id] = (
                    source_regions[source_region_id],
                    reconstruction_regions[reconstructed_region_id],
                )
                reconstruction_to_source[reconstructed_region_id] = source_region_id
            role_counts[role] = len(role_records)
        diagnostics[population] = {
            "method": "post_phase_cyclic_angular_centroid_assignment",
            "reference_role": reference_role,
            "cyclic_shift": shift,
            "angular_rms_rad": round(math.sqrt(score), 12),
            "role_instance_counts": role_counts,
        }
    if set(result) != set(source_regions):
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "post-phase periodic instance assignment is incomplete",
            {"missing_region_ids": sorted(set(source_regions) - set(result))},
        )
    return result, {
        "method": "independent_population_cyclic_assignment",
        "populations": diagnostics,
        "reconstruction_to_source_region_ids": reconstruction_to_source,
    }


def _best_periodic_cyclic_shift(
    source_regions: Mapping[str, TriangleMesh],
    reconstruction_regions: Mapping[str, TriangleMesh],
    records: list[Mapping[str, Any]],
) -> tuple[int, float]:
    source_order = sorted(
        records,
        key=lambda record: (
            int(record.get("periodic_lattice_index", 0)),
            str(record.get("periodic_instance_id", "")),
        ),
    )
    reconstruction_order = sorted(
        records,
        key=lambda record: int(record.get("reconstruction_blade_pair_index", 0)),
    )
    if not source_order:
        raise StepAuditError(
            "v116_step_comparison_scope_failed",
            "periodic comparison population has no instance regions",
        )
    source_angles = [
        _mesh_angular_centroid(source_regions[str(record["comparison_region_id"])])
        for record in source_order
    ]
    reconstruction_angles = [
        _mesh_angular_centroid(
            reconstruction_regions[str(record["comparison_region_id"])]
        )
        for record in reconstruction_order
    ]
    scores = []
    for shift in range(len(source_order)):
        residuals = [
            _wrapped_angle_difference(
                source_angles[index],
                reconstruction_angles[(index + shift) % len(reconstruction_order)],
            )
            for index in range(len(source_order))
        ]
        scores.append(float(np.mean(np.square(residuals))))
    best = int(np.argmin(scores))
    return best, scores[best]


def _mesh_angular_centroid(mesh: TriangleMesh) -> float:
    center = np.mean(np.asarray(mesh.vertices, dtype=float), axis=0)
    return math.atan2(float(center[1]), float(center[0]))


def _wrapped_angle_difference(first: float, second: float) -> float:
    return (float(first) - float(second) + math.pi) % (2.0 * math.pi) - math.pi


def _surface_matches_comparison_role(
    surface: Mapping[str, Any], comparison_role: str
) -> bool:
    surface_id = str(surface.get("id", ""))
    role = str(surface.get("role", ""))
    if comparison_role == "hub_flowpath":
        return surface_id == "hub_support_surface"
    if comparison_role == "hub_material_closure":
        return surface_id in {
            "hub_top_annulus_surface",
            "hub_bottom_annulus_surface",
            "hub_bottom_outer_wall_surface",
        }
    if comparison_role == "shroud_inner_flowpath":
        return surface_id == "shroud_support_surface"
    if comparison_role == "shroud_outer_material":
        return surface_id == "shroud_outer_material_surface"
    if comparison_role == "mounting_bore":
        return surface_id == "mounting_bore_inner_wall_surface"
    if comparison_role == "blade_sides":
        return role in {"blade_pressure", "blade_suction"}
    if comparison_role == "blade_leading_edge":
        return role == "blade_leading_edge"
    if comparison_role == "blade_trailing_edge":
        return role == "blade_trailing_edge"
    if comparison_role == "blade_root_attachment":
        return role == "root_to_hub_attachment"
    if comparison_role == "blade_tip_attachment":
        return role == "closed_shroud_attachment"
    if comparison_role == "blade_tip":
        return role == "open_tip_dome"
    return False


def _surface_blade_index(surface: Mapping[str, Any]) -> int | None:
    value = surface.get("blade_index")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    match = re.match(r"blade_(\d+)_", str(surface.get("id", "")))
    return None if match is None else int(match.group(1))


def _tessellate_cadquery_faces(
    faces, *, linear_tolerance: float, angular_tolerance: float
) -> TriangleMesh:
    meshes = []
    for face in faces:
        vectors, raw_triangles = face.tessellate(
            linear_tolerance, angular_tolerance
        )
        vertices = np.asarray(
            [
                vector.toTuple() if hasattr(vector, "toTuple") else vector
                for vector in vectors
            ],
            dtype=float,
        )
        triangles = np.asarray(raw_triangles, dtype=np.int32)
        if len(vertices) == 0 or len(triangles) == 0:
            continue
        normals = np.asarray(
            [
                _triangle_normal_from_points(vertices[triangle])
                for triangle in triangles
            ],
            dtype=float,
        )
        meshes.append(TriangleMesh(vertices, triangles, normals))
    if not meshes:
        raise ValueError("supported source faces produced no tessellation")
    return combine_triangle_meshes(meshes)


def _surface_graph_triangle_mesh(surface_graph: Mapping[str, Any]) -> TriangleMesh:
    from part_rule_synthesis.impeller_surface_graph_export import (
        triangulate_surface_graph,
    )

    triangulation = triangulate_surface_graph(
        dict(surface_graph), view_id="cad_review_360"
    )
    triangles = triangulation.get("triangles", ())
    if not triangles:
        raise ValueError("supported reconstruction surfaces produced no triangles")
    vertices = []
    triangle_indices = []
    normals = []
    for triangle in triangles:
        start = len(vertices)
        vertices.extend(
            [[float(value) for value in point] for point in triangle["points"]]
        )
        triangle_indices.append([start, start + 1, start + 2])
        normals.append([float(value) for value in triangle["normal"]])
    return TriangleMesh(
        np.asarray(vertices, dtype=float),
        np.asarray(triangle_indices, dtype=np.int32),
        np.asarray(normals, dtype=float),
    )


def _triangle_normal_from_points(points: np.ndarray) -> np.ndarray:
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    length = float(np.linalg.norm(normal))
    return normal / max(length, 1.0e-12)


def _rotation_about_z_matrix(angle_deg: float) -> list[list[float]]:
    angle = math.radians(float(angle_deg))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


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

        cq.exporters.export(
            shape,
            str(path),
            exportType="STL",
            tolerance=SOURCE_REVIEW_LINEAR_TOLERANCE_MM,
            angularTolerance=SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD,
        )
    except Exception as exc:  # noqa: BLE001
        raise StepAuditError("v116_step_parse_failed", f"source STEP tessellation failed: {exc}") from exc


def _axis_first_section_reconstruction_manifest(
    *,
    frame: dict[str, Any],
    semantics: dict[str, Any],
    mapping: dict[str, Any],
    reconstruction: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    consensus = frame.get("axis_consensus", {})
    selected = consensus.get("selected_cluster", {})
    if not selected and frame.get("candidate_scores"):
        selected = frame["candidate_scores"][0]
    source_entity_ids = selected.get("source_entity_ids", selected.get("face_ids", []))
    tolerance = consensus.get(
        "tolerance",
        {"line_distance_mm": max(0.02, 0.0002 * 2.0 * float(frame["outer_radius_mm"])), "angular_deg": 0.05},
    )
    residual = consensus.get(
        "residual",
        {"line_rms_mm": 0.0, "angular_spread_deg": 0.0},
    )
    partition = frame.get("coarse_topology_partition", {})
    measurements = mapping.get("measurement_bundle", {})
    support = mapping.get("support_recovery", {})
    periodic = mapping.get("periodic_provenance", {})
    sections = mapping.get("section_provenance", {})
    disposition = _axis_first_algorithm_disposition(mapping)
    pattern_contract = reconstruction.get("pattern_material_contract", {})
    pattern = pattern_contract.get("pattern", {})
    return {
        "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
        "contract_phase": disposition["status_scope"],
        "algorithm_readiness": copy.deepcopy(
            disposition["algorithm_readiness"]
        ),
        "canonical_frame": {
            "coordinate_frame": "source_to_canonical_positive_z_axis",
            "axis": {
                "origin_mm": frame["source_axis_origin_mm"],
                "direction": frame["source_axis_direction"],
                "source_entity_ids": list(source_entity_ids),
                "confidence": selected.get(
                    "confidence",
                    {
                        "level": "analytic_axis_consensus",
                        "score": selected.get("score"),
                    },
                ),
                "coordinate_frame": "source_cartesian_mm",
                "units": "mm",
                "method": frame["method"],
                "tolerance": tolerance,
                "residual": residual,
                "provenance": {
                    "authority": "uploaded_step_brep",
                    "source_entity_ids": list(source_entity_ids),
                    "selection_method": frame["method"],
                },
            },
            "source_to_canonical_matrix": frame["source_to_canonical_matrix"],
            "scale": frame["scale"],
            "primary_icp_applied": frame["primary_icp_applied"],
        },
        "support_recovery": {
            "status": support.get("status", "FAILED"),
            "topology_mode": support.get("topology_mode"),
            "support_face_ids": support.get("support_face_ids", {}),
            "profile_fits": mapping.get("profile_fits", {}),
            "source_sha256": measurements.get("provenance", {}).get("source_sha256"),
        },
        "periodic_populations": {
            "status": periodic.get("status", "FAILED"),
            "main": {
                "count": (periodic.get("main") or {}).get("count"),
                "pitch_deg": (periodic.get("main") or {}).get("pitch_deg"),
                "source_ids": (periodic.get("main") or {}).get("source_ids", []),
            },
            "splitter_optional": {
                "count": (periodic.get("splitter") or {}).get("count", 0),
                "source_ids": (periodic.get("splitter") or {}).get("source_ids", []),
            },
            "closure_pass": periodic.get("closure_pass"),
            "collision_free": periodic.get("collision_free"),
        },
        "span_measurement_lattice": {
            "status": sections.get("status", "FAILED"),
            "station_count_by_population": {
                name: len(family.get("stations", []))
                for name, family in measurements.get("section_families", {}).items()
            },
            "source_section_loop_count": len(sections.get("section_loop_records", [])),
            "measurement_authority": sections.get("measurement_authority"),
        },
        "representative_blades": {
            "status": periodic.get("status", "FAILED"),
            "source_ids": periodic.get("source_ids", []),
        },
        "v11_2_mapping": {
            "status": mapping.get("mapping_status", "FAILED"),
            "mapping_id": mapping.get("mapping_id"),
            "geometry_patch_version": mapping.get("geometry_patch_version"),
            "source_sha256": measurements.get("provenance", {}).get("source_sha256"),
            "promotion_contract": mapping.get("promotion_contract", {}),
        },
        "pattern_instances": {
            "status": pattern_contract.get("status", "FAILED"),
            "method": pattern.get("method"),
            "main_blade_count": pattern.get("main_blade_count"),
            "splitter_blade_count": pattern.get("splitter_blade_count"),
            "closure_status": pattern.get("closure_status"),
            "collision_status": pattern.get("collision_status"),
            "populations": copy.deepcopy(pattern.get("populations", [])),
            "surface_count": reconstruction.get("surface_count"),
        },
        "regional_deviation": {
            "status": "CORRESPONDING_SURFACES_MEASURED_REVIEW_ONLY",
            "contract_id": comparison.get("contract_id"),
            "comparison_direction": comparison.get("comparison_direction"),
            "reconstruction_to_corresponding_source": copy.deepcopy(
                comparison.get("reconstruction_to_corresponding_source", {})
            ),
            "corresponding_source_to_reconstruction": copy.deepcopy(
                comparison.get("corresponding_source_to_reconstruction", {})
            ),
            "symmetric_corresponding_sample_distribution": copy.deepcopy(
                comparison.get("symmetric_corresponding_sample_distribution", {})
            ),
            "regions": copy.deepcopy(comparison.get("regions", {})),
            "scope": copy.deepcopy(comparison.get("scope", {})),
            "mapping_failed_terms": copy.deepcopy(
                list(mapping.get("failed_terms", ()))
            ),
        },
        "invariants": {
            "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
            "source_authority": "uploaded_step_brep",
            "scale_fixed": frame.get("scale") == 1.0,
            "primary_icp_forbidden": not frame.get("primary_icp_applied", False),
            "coarse_face_accounting_complete": partition.get("invariants", {}).get(
                "all_source_faces_accounted_for", False
            ),
        },
    }


def _axis_first_cache_manifest_complete(manifest: dict[str, Any]) -> bool:
    source_sha256 = manifest.get("source", {}).get("sha256")
    if not _is_sha256(source_sha256):
        return False
    axis_status = manifest.get("axis_first_algorithm_status")
    if not (
        manifest.get("status") == "PASS"
        and manifest.get("legacy_workflow_status") == "PASS"
        and axis_status in {"PASS", "REJECTED"}
    ):
        return False
    payload = manifest.get("axis_first_section_reconstruction")
    if not isinstance(payload, dict) or payload.get("algorithm_revision") != AUDIT_IMPLEMENTATION_REVISION:
        return False
    readiness = payload.get("algorithm_readiness", {})
    if not isinstance(readiness, dict):
        return False
    required_sections = {
        "canonical_frame",
        "support_recovery",
        "periodic_populations",
        "span_measurement_lattice",
        "representative_blades",
        "v11_2_mapping",
        "pattern_instances",
        "regional_deviation",
        "invariants",
    }
    if not required_sections <= payload.keys():
        return False
    if axis_status == "REJECTED":
        return _completed_rejected_review_manifest(manifest, payload, readiness)
    comparison_scope = manifest.get("comparison_scope", {})
    if not (
        manifest.get("promotable") is True
        and isinstance(comparison_scope, dict)
        and comparison_scope.get("contract_id") == COMPARISON_SCOPE_CONTRACT_ID
        and comparison_scope.get("status") == "PASS"
        and comparison_scope.get("comparison_coverage_complete") is True
        and readiness.get("status") == "READY"
        and readiness.get("algorithm_ready") is True
        and readiness.get("cache_reusable") is True
    ):
        return False
    canonical_frame = payload.get("canonical_frame", {})
    axis = canonical_frame.get("axis", {})
    matrix = np.asarray(
        canonical_frame.get("source_to_canonical_matrix", []), dtype=float
    )
    axis_matrix = np.asarray(axis.get("source_to_canonical_matrix", []), dtype=float)
    if not (
        _valid_cache_evidence_record(axis, source_sha256)
        and _valid_rigid_homogeneous_transform(matrix)
        and _valid_rigid_homogeneous_transform(axis_matrix)
        and hmac.compare_digest(matrix.tobytes(), axis_matrix.tobytes())
        and payload.get("invariants", {}).get("canonical_geometry_version")
        == CANONICAL_GEOMETRY_VERSION
    ):
        return False
    support = payload["support_recovery"]
    periodic = payload["periodic_populations"]
    lattice = payload["span_measurement_lattice"]
    representatives = payload["representative_blades"]
    mapping = payload["v11_2_mapping"]
    pattern = payload["pattern_instances"]
    deviation = payload["regional_deviation"]
    return bool(
        _valid_support_cache_section(support, source_sha256)
        and _valid_periodic_cache_section(periodic, source_sha256)
        and _valid_lattice_cache_section(lattice, source_sha256)
        and _valid_representative_cache_section(
            representatives, lattice, periodic, source_sha256
        )
        and _valid_mapping_cache_section(mapping, periodic, source_sha256)
        and _valid_pattern_cache_section(pattern, periodic, source_sha256)
        and _valid_deviation_cache_section(deviation, source_sha256)
    )


def _completed_rejected_review_manifest(
    manifest: dict[str, Any],
    payload: dict[str, Any],
    readiness: dict[str, Any],
) -> bool:
    mapping = manifest.get("parameter_mapping", {})
    scope = manifest.get("comparison_scope", {})
    comparison = manifest.get("comparison", {})
    evidence_sections = (
        "canonical_frame",
        "support_recovery",
        "periodic_populations",
        "span_measurement_lattice",
        "representative_blades",
        "v11_2_mapping",
        "pattern_instances",
        "regional_deviation",
        "invariants",
    )
    return bool(
        manifest.get("promotable") is False
        and manifest.get("reconstruction_disposition")
        == "review_only_not_promotable"
        and readiness.get("status") == "REJECTED"
        and readiness.get("algorithm_ready") is False
        and isinstance(readiness.get("failed_terms"), list)
        and readiness["failed_terms"]
        and isinstance(mapping, dict)
        and mapping.get("mapping_status") == "REJECTED_REVIEW_CANDIDATE"
        and isinstance(scope, dict)
        and scope.get("contract_id") == COMPARISON_SCOPE_CONTRACT_ID
        and scope.get("status") in {"PASS", "PARTIAL_REVIEW"}
        and scope.get("coverage_complete") is True
        and isinstance(comparison, dict)
        and comparison.get("contract_id")
        == "impeller_v1_1_6_corresponding_surface_deviation_v5"
        and payload.get("regional_deviation", {}).get("status")
        in {"PASS", "CORRESPONDING_SURFACES_MEASURED_REVIEW_ONLY"}
        and all(
            isinstance(payload.get(section), dict) and bool(payload[section])
            for section in evidence_sections
        )
        and not _contains_placeholder(payload)
    )


def _audit_artifacts_match_manifest(
    audit_dir: Path, manifest: dict[str, Any]
) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    required = {
        "source_stl": "source.stl",
        "reconstruction_stl": "reconstruction.stl",
        "heatmap": "heatmap.json",
        "geometric_manifest": "geometric-manifest.json",
    }
    for artifact_id, expected_name in required.items():
        record = artifacts.get(artifact_id)
        if not isinstance(record, dict) or record.get("file_name") != expected_name:
            return False
        path = audit_dir / expected_name
        if not path.is_file() or path.stat().st_size != record.get("size_bytes"):
            return False
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not hmac.compare_digest(digest, str(record.get("sha256", ""))):
            return False
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_digest_matches_status(
    manifest_path: Path, status: Mapping[str, Any]
) -> bool:
    expected = status.get("manifest_sha256")
    return bool(
        _is_sha256(expected)
        and hmac.compare_digest(_file_sha256(manifest_path), str(expected))
    )


def _valid_cache_section(section: Any) -> bool:
    return bool(
        isinstance(section, dict)
        and section.get("status") == "PASS"
        and _valid_confidence(section.get("confidence"))
        and isinstance(section.get("validation"), dict)
        and section["validation"].get("status") == "PASS"
        and not _contains_placeholder(section)
    )


def _valid_cache_evidence_record(record: Any, source_sha256: str) -> bool:
    if not isinstance(record, dict):
        return False
    source_ids = record.get("source_entity_ids")
    provenance = record.get("provenance")
    return bool(
        isinstance(source_ids, list)
        and source_ids
        and all(isinstance(item, str) and item for item in source_ids)
        and len(source_ids) == len(set(source_ids))
        and _valid_confidence(record.get("confidence"))
        and isinstance(record.get("coordinate_frame"), str)
        and record["coordinate_frame"]
        and _valid_units(record.get("units"))
        and _finite_metric_tree(record.get("tolerance"), positive=True)
        and _finite_metric_tree(record.get("residual"))
        and _is_sha256(record.get("evidence_hash"))
        and hmac.compare_digest(
            record["evidence_hash"], _canonical_evidence_hash(record)
        )
        and isinstance(provenance, dict)
        and provenance.get("authority") in _CACHE_AUTHORITY_ALLOWLIST
        and provenance.get("source_sha256") == source_sha256
        and set(provenance.get("source_entity_ids", ())) == set(source_ids)
        and not _contains_placeholder(record)
    )


def _valid_support_cache_section(section: Any, source_sha256: str) -> bool:
    if not _valid_cache_section(section):
        return False
    profiles = [section.get("hub_profile"), section.get("tip_reference_or_shroud")]
    topology = section.get("topology_decision")
    return bool(
        all(
            _valid_cache_evidence_record(record, source_sha256)
            and _finite_point_table(record.get("control_points_rz_mm"), 2)
            for record in profiles
        )
        and _valid_cache_evidence_record(topology, source_sha256)
        and topology.get("decision") in {"open", "closed"}
    )


def _valid_periodic_cache_section(section: Any, source_sha256: str) -> bool:
    if not _valid_cache_section(section):
        return False
    main = section.get("main")
    splitter = section.get("splitter_optional")
    if not isinstance(main, dict) or not isinstance(splitter, dict):
        return False
    main_count = main.get("count")
    splitter_count = splitter.get("count")
    if (
        not isinstance(main_count, int)
        or isinstance(main_count, bool)
        or main_count < 2
        or not isinstance(splitter_count, int)
        or isinstance(splitter_count, bool)
        or splitter_count < 0
        or not _finite_positive(main.get("pitch_deg"))
    ):
        return False
    records = main.get("component_records", []) + splitter.get(
        "component_records", []
    )
    if not (
        len(records) == main_count + splitter_count
        and len({record.get("source_component_id") for record in records})
        == len(records)
        and all(
            _valid_periodic_component_cache_record(record, source_sha256)
            for record in records
        )
    ):
        return False
    for population, count in ((main, main_count), (splitter, splitter_count)):
        representative_id = population.get("representative_component_id")
        component_ids = {
            record["source_component_id"]
            for record in population.get("component_records", [])
        }
        if count and representative_id not in component_ids:
            return False
        if not count and representative_id is not None:
            return False
    return True


def _valid_periodic_component_cache_record(
    record: Any, source_sha256: str
) -> bool:
    if not _valid_cache_evidence_record(record, source_sha256):
        return False
    source_ids = record["source_entity_ids"]
    source_face_ids = record.get("source_face_ids")
    completeness = record.get("component_completeness")
    if not (
        isinstance(source_face_ids, list)
        and set(source_face_ids) == set(source_ids)
        and len(source_face_ids) == len(set(source_face_ids))
        and len(source_face_ids) >= 4
        and record.get("face_count") == len(source_face_ids)
        and isinstance(completeness, dict)
        and completeness.get("status") == "COMPLETE"
    ):
        return False
    side_ids = completeness.get("blade_side_face_ids")
    root_edge_ids = completeness.get("root_edge_face_ids")
    return bool(
        isinstance(side_ids, list)
        and len(side_ids) == 2
        and isinstance(root_edge_ids, list)
        and len(root_edge_ids) >= 2
        and set(side_ids).isdisjoint(root_edge_ids)
        and set(side_ids) | set(root_edge_ids) == set(source_face_ids)
    )


def _valid_lattice_cache_section(section: Any, source_sha256: str) -> bool:
    if not _valid_cache_section(section):
        return False
    stations = section.get("stations")
    if not isinstance(stations, list) or not 5 <= len(stations) <= 9:
        return False
    h_values = [station.get("h") for station in stations]
    return bool(
        all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in h_values)
        and all(0.0 <= float(value) <= 1.0 for value in h_values)
        and all(float(left) < float(right) for left, right in zip(h_values, h_values[1:]))
        and all(_valid_cache_evidence_record(station, source_sha256) for station in stations)
    )


def _valid_representative_cache_section(
    section: Any, lattice: dict[str, Any], periodic: dict[str, Any], source_sha256: str
) -> bool:
    if not _valid_cache_section(section):
        return False
    loops = section.get("section_loops")
    if not isinstance(loops, list) or not loops:
        return False
    expected_h = {round(float(item["h"]), 12) for item in lattice["stations"]}
    populations = {"main"}
    if periodic["splitter_optional"]["count"]:
        populations.add("splitter")
    actual = {
        (item.get("population"), round(float(item.get("h", math.nan)), 12))
        for item in loops
        if isinstance(item, dict)
    }
    selected_components: dict[str, tuple[str, set[str]]] = {}
    for population_name, population_record in (
        ("main", periodic["main"]),
        ("splitter", periodic["splitter_optional"]),
    ):
        if not population_record["count"]:
            continue
        representative_id = population_record.get("representative_component_id")
        representative = next(
            (
                record
                for record in population_record.get("component_records", [])
                if record.get("source_component_id") == representative_id
            ),
            None,
        )
        if representative is None:
            return False
        selected_components[population_name] = (
            representative_id,
            set(representative.get("source_face_ids", [])),
        )
    return bool(
        actual == {(population, h) for population in populations for h in expected_h}
        and all(_valid_cache_evidence_record(item, source_sha256) for item in loops)
        and all(
            isinstance(item.get("source_face_ids"), list)
            and item["source_face_ids"]
            and len(item["source_face_ids"])
            == len(set(item["source_face_ids"]))
            and set(item.get("source_entity_ids", []))
            == set(item["source_face_ids"])
            and item.get("population") in selected_components
            and item.get("representative_source_component_id")
            == selected_components[item["population"]][0]
            and set(item["source_face_ids"])
            <= selected_components[item["population"]][1]
            for item in loops
        )
    )


def _valid_mapping_cache_section(
    section: Any, periodic: dict[str, Any], source_sha256: str
) -> bool:
    if not _valid_cache_section(section):
        return False
    parameters = section.get("mapped_parameters")
    terms = section.get("mapping_terms")
    expected_count = periodic["main"]["count"] + periodic["splitter_optional"]["count"]
    return bool(
        isinstance(parameters, dict)
        and parameters.get("blade_count") == expected_count
        and isinstance(terms, list)
        and terms
        and all(
            _valid_cache_evidence_record(term, source_sha256)
            and math.isfinite(float(term.get("target")))
            and math.isfinite(float(term.get("fitted")))
            for term in terms
        )
    )


def _valid_pattern_cache_section(
    section: Any, periodic: dict[str, Any], source_sha256: str
) -> bool:
    if not _valid_cache_section(section):
        return False
    instances = section.get("instances")
    expected_count = periodic["main"]["count"] + periodic["splitter_optional"]["count"]
    keys = [
        (item.get("population"), item.get("lattice_index"))
        for item in instances or []
        if isinstance(item, dict)
    ]
    return bool(
        isinstance(instances, list)
        and len(instances) == expected_count
        and len(set(keys)) == expected_count
        and all(_valid_cache_evidence_record(item, source_sha256) for item in instances)
    )


def _valid_deviation_cache_section(section: Any, source_sha256: str) -> bool:
    if not _valid_cache_section(section):
        return False
    regions = section.get("regions")
    return bool(
        isinstance(regions, list)
        and regions
        and all(
            _valid_cache_evidence_record(item, source_sha256)
            and math.isfinite(float(item.get("rms_mm")))
            for item in regions
        )
    )


def _valid_units(value: Any) -> bool:
    return bool(
        (isinstance(value, str) and value)
        or (
            isinstance(value, dict)
            and value
            and all(isinstance(item, str) and item for item in value.values())
        )
    )


def _finite_metric_tree(value: Any, *, positive: bool = False) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    leaves: list[float] = []

    def collect(item: Any) -> bool:
        if isinstance(item, bool):
            return False
        if isinstance(item, (int, float)):
            number = float(item)
            leaves.append(number)
            return math.isfinite(number) and (not positive or number > 0.0)
        if isinstance(item, dict) and item:
            return all(collect(nested) for nested in item.values())
        return False

    return collect(value) and bool(leaves)


_CACHE_AUTHORITY_ALLOWLIST = frozenset(
    {
        "uploaded_step_brep",
        "uploaded_step_brep_topology",
        "uploaded_step_brep_section",
        "v11_2_canonical_mapping",
        "generation_bound_deviation",
    }
)
_CACHE_CONFIDENCE_LEVELS = frozenset(
    {"measured", "analytic_consensus", "deterministic_topology_component", "validated_fit"}
)
_CACHE_CONFIDENCE_STATUSES = frozenset({"PASS", "ACCEPTED", "MEASURED", "VALIDATED"})


def _valid_confidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    score = value.get("score")
    return bool(
        value.get("level") in _CACHE_CONFIDENCE_LEVELS
        and value.get("status") in _CACHE_CONFIDENCE_STATUSES
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
        and 0.0 <= float(score) <= 1.0
    )


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "placeholder" in value.strip().lower()
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(
            (str(key).lower() == "placeholder" and item is not False)
            or _contains_placeholder(item)
            for key, item in value.items()
        )
    return False


def _canonical_evidence_hash(record: dict[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "evidence_hash"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_rigid_homogeneous_transform(matrix: np.ndarray) -> bool:
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        return False
    if not np.allclose(
        matrix[3], np.asarray([0.0, 0.0, 0.0, 1.0]), atol=1.0e-12, rtol=0.0
    ):
        return False
    rotation = matrix[:3, :3]
    return bool(
        np.allclose(rotation.T @ rotation, np.eye(3), atol=1.0e-10, rtol=0.0)
        and math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1.0e-10)
    )


def _finite_point_table(value: Any, width: int) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(point, list)
            and len(point) == width
            and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
                for item in point
            )
            for point in value
        )
    )


def _finite_positive(value: Any) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


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
        "mapping_status",
        "source_basis",
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
            stream.write(
                json.dumps(
                    payload,
                    default=_json_manifest_value,
                    indent=2,
                    sort_keys=True,
                )
            )
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


def _json_manifest_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
