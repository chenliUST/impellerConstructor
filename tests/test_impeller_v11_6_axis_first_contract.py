from __future__ import annotations

# ruff: noqa: E402

import json
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_step_audit import (
    AUDIT_CONTRACT_ID,
    AUDIT_IMPLEMENTATION_REVISION,
    CANONICAL_GEOMETRY_VERSION,
    FAILURE_REASONS,
    StepAuditError,
    StepReconstructionAuditService,
    _atomic_json,
    _axis_first_cache_manifest_complete,
    _axis_first_section_reconstruction_manifest,
)
from part_rule_synthesis.api import create_app


AXIS_FIRST_FAILURE_REASONS = {
    "v116_axis_consensus_failed",
    "v116_axis_consensus_ambiguous",
    "v116_hub_support_classification_failed",
    "v116_hub_profile_fit_failed",
    "v116_tip_reference_inference_failed",
    "v116_shroud_topology_ambiguous",
    "v116_span_surface_ordering_failed",
    "v116_periodic_population_ambiguous",
    "v116_representative_blade_selection_failed",
    "v116_section_intersection_failed",
    "v116_section_loop_open",
    "v116_section_loop_correspondence_failed",
    "v116_section_tangent_flip_detected",
    "v116_thickness_field_invalid",
    "v116_root_attachment_measurement_failed",
    "v116_v112_mapping_residual_exceeded",
    "v116_false_material_surface_forbidden",
}


def _cache_evidence(source_sha256: str, source_ids: list[str], **extra) -> dict:
    record = {
        "source_entity_ids": source_ids,
        "confidence": {"level": "measured", "score": 1.0, "status": "ACCEPTED"},
        "coordinate_frame": "canonical_cylindrical_r_theta_z",
        "units": {"linear": "mm"},
        "tolerance": {"linear_mm": 0.01},
        "residual": {"rms_mm": 0.001},
        "provenance": {
            "authority": "uploaded_step_brep",
            "source_sha256": source_sha256,
            "source_entity_ids": source_ids,
        },
        **extra,
    }
    record["evidence_hash"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return record


def _rehash_cache_evidence(record: dict) -> None:
    record["evidence_hash"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in record.items() if key != "evidence_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _write_pass_cache(
    service: StepReconstructionAuditService,
    *,
    audit_id: str,
    source_sha256: str,
    revision: str,
    axis_first_revision: str | None,
    complete_axis_first: bool = False,
) -> Path:
    audit_dir = service.root / audit_id
    audit_dir.mkdir()
    status = {
        "audit_id": audit_id,
        "contract_id": AUDIT_CONTRACT_ID,
        "implementation_revision": revision,
        "algorithm_revision": revision,
        "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "status": "PASS",
        "legacy_workflow_status": "PASS",
        "axis_first_algorithm_status": "PASS" if complete_axis_first else "INCOMPLETE",
        "promotable": complete_axis_first,
        "source": {"sha256": source_sha256},
    }
    manifest = {
        "contract_id": AUDIT_CONTRACT_ID,
        "implementation_revision": revision,
        "algorithm_revision": revision,
        "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "source": {"sha256": source_sha256},
        "legacy_workflow_status": "PASS",
        "axis_first_algorithm_status": "PASS" if complete_axis_first else "INCOMPLETE",
        "promotable": complete_axis_first,
        "comparison_alignment": {"method": "bounded_symmetric_periodic_phase_search"},
    }
    if axis_first_revision is not None:
        axis_first = {
            "algorithm_revision": axis_first_revision,
            "algorithm_readiness": {
                "status": "READY" if complete_axis_first else "INCOMPLETE",
                "algorithm_ready": complete_axis_first,
                "cache_reusable": complete_axis_first,
            },
            "canonical_frame": {
                "axis": _cache_evidence(
                    source_sha256,
                    ["source_face_00000"],
                    coordinate_frame="source_cartesian_mm",
                    source_to_canonical_matrix=[
                        [1.0, 0.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0, 0.0],
                        [0.0, 0.0, 1.0, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                ),
                "source_to_canonical_matrix": [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ],
            },
            "support_recovery": {},
            "periodic_populations": {},
            "span_measurement_lattice": {},
            "representative_blades": {},
            "v11_2_mapping": {},
            "pattern_instances": {},
            "regional_deviation": {},
            "invariants": {"canonical_geometry_version": "1.1.2"},
        }
        if complete_axis_first:
            station_h = [0.0, 0.25, 0.5, 0.75, 1.0]
            component_records = [
                _cache_evidence(
                    source_sha256,
                    [f"source_face_{index + 10:05d}_{face}" for face in range(4)],
                    source_component_id=f"main_component_{index:02d}",
                    source_face_ids=[
                        f"source_face_{index + 10:05d}_{face}" for face in range(4)
                    ],
                    face_count=4,
                    component_completeness={
                        "status": "COMPLETE",
                        "blade_side_face_ids": [
                            f"source_face_{index + 10:05d}_0",
                            f"source_face_{index + 10:05d}_1",
                        ],
                        "root_edge_face_ids": [
                            f"source_face_{index + 10:05d}_2",
                            f"source_face_{index + 10:05d}_3",
                        ],
                    },
                )
                for index in range(13)
            ]
            axis_first.update(
                {
                    "support_recovery": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "hub_profile": _cache_evidence(
                            source_sha256,
                            ["source_face_00001"],
                            control_points_rz_mm=[[10.0, 0.0], [50.0, 5.0]],
                        ),
                        "tip_reference_or_shroud": _cache_evidence(
                            source_sha256,
                            ["source_face_00002"],
                            control_points_rz_mm=[[12.0, 10.0], [50.0, 15.0]],
                        ),
                        "topology_decision": _cache_evidence(
                            source_sha256,
                            ["source_face_00002"],
                            decision="open",
                        ),
                    },
                    "periodic_populations": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "main": {
                            "count": 13,
                            "pitch_deg": 360.0 / 13.0,
                            "representative_component_id": "main_component_00",
                            "component_records": component_records,
                        },
                        "splitter_optional": {
                            "count": 0,
                            "representative_component_id": None,
                            "component_records": [],
                        },
                    },
                    "span_measurement_lattice": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "stations": [
                            _cache_evidence(
                                source_sha256,
                                [f"source_edge_{index:05d}"],
                                h=h,
                            )
                            for index, h in enumerate(station_h)
                        ],
                    },
                    "representative_blades": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "section_loops": [
                            _cache_evidence(
                                source_sha256,
                                ["source_face_00010_0", "source_face_00010_1"],
                                loop_id=f"main-{index}",
                                population="main",
                                h=h,
                                representative_source_component_id="main_component_00",
                                source_face_ids=[
                                    "source_face_00010_0",
                                    "source_face_00010_1",
                                ],
                            )
                            for index, h in enumerate(station_h)
                        ],
                    },
                    "v11_2_mapping": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "mapped_parameters": {"blade_count": 13},
                        "mapping_terms": [
                            _cache_evidence(
                                source_sha256,
                                ["source_face_00001"],
                                target=13.0,
                                fitted=13.0,
                            )
                        ],
                    },
                    "pattern_instances": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "instances": [
                            _cache_evidence(
                                source_sha256,
                                [f"source_face_{index + 10:05d}"],
                                population="main",
                                lattice_index=index,
                                phase_deg=index * 360.0 / 13.0,
                            )
                            for index in range(13)
                        ],
                    },
                    "regional_deviation": {
                        "status": "PASS",
                        "validation": {"status": "PASS"},
                        "regions": [
                            _cache_evidence(
                                source_sha256,
                                ["source_face_00010"],
                                region="blade_side_a",
                                rms_mm=0.1,
                            )
                        ],
                    },
                }
            )
            for section_name in (
                "support_recovery",
                "periodic_populations",
                "span_measurement_lattice",
                "representative_blades",
                "v11_2_mapping",
                "pattern_instances",
                "regional_deviation",
            ):
                axis_first[section_name]["confidence"] = {
                    "level": "validated_fit",
                    "score": 1.0,
                    "status": "PASS",
                }
        manifest["axis_first_section_reconstruction"] = axis_first
    (audit_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (audit_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for artifact_name in ("source.stl", "reconstruction.stl", "heatmap.json"):
        (audit_dir / artifact_name).write_bytes(b"cache evidence")
    return audit_dir


def test_axis_first_contract_pins_revision_failures_and_v112_authority():
    assert AUDIT_IMPLEMENTATION_REVISION == "axis_first_section_periodic_r3"
    assert AXIS_FIRST_FAILURE_REASONS <= FAILURE_REASONS
    assert CANONICAL_GEOMETRY_VERSION == "1.1.2"


def test_manifest_persistence_normalizes_numpy_brep_evidence(tmp_path):
    destination = tmp_path / "manifest.json"

    _atomic_json(
        destination,
        {
            "control_lattice": np.asarray([[1.0, 2.0], [3.0, 4.0]]),
            "residual_mm": np.float64(0.0125),
        },
    )

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "control_lattice": [[1.0, 2.0], [3.0, 4.0]],
        "residual_mm": 0.0125,
    }


@pytest.mark.parametrize("reason", sorted(AXIS_FIRST_FAILURE_REASONS))
def test_axis_first_failure_reasons_serialize_through_status(tmp_path, reason):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    handle = service.begin_upload("source.step")
    error = StepAuditError(
        reason, "stable failure", {"source_entity_ids": ["source_face_00007"]}
    )

    service.fail_upload(handle, error)

    failure = service.status(handle.audit_id)["failure"]
    assert failure == {
        "reason": reason,
        "message": "stable failure",
        "details": {"source_entity_ids": ["source_face_00007"]},
    }


@pytest.mark.parametrize("reason", sorted(AXIS_FIRST_FAILURE_REASONS))
def test_axis_first_failure_reasons_serialize_through_http_detail(tmp_path, reason):
    app = create_app(tmp_path / "service")
    service = app.state.step_reconstruction_audits

    def fail_with_axis_first_reason(_handle, *, size_bytes, sha256):
        raise StepAuditError(
            reason, "stable failure", {"size_bytes": size_bytes, "sha256": sha256}
        )

    service.finish_upload = fail_with_axis_first_reason
    client = TestClient(app)

    response = client.post(
        "/api/step-reconstruction-audits?filename=source.step",
        content=b"axis-first contract payload",
        headers={"Content-Type": "application/step"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == reason
    assert response.json()["detail"]["details"]["size_bytes"] == 27


def test_previous_generic_pass_manifest_is_not_reused(tmp_path):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    source_sha256 = "a" * 64
    _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000001",
        source_sha256=source_sha256,
        revision="v1_1_6_persistence_phase_dedup_r2",
        axis_first_revision=None,
    )

    assert (
        service._find_reusable_audit(
            source_sha256, exclude_audit_id="step-audit-ffffffffffffffff"
        )
        is None
    )


def test_same_source_same_revision_complete_pass_manifest_is_reused(tmp_path):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    source_sha256 = "b" * 64
    _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000002",
        source_sha256=source_sha256,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )

    reused = service._find_reusable_audit(
        source_sha256, exclude_audit_id="step-audit-ffffffffffffffff"
    )

    assert reused is not None
    assert reused["audit_id"] == "step-audit-0000000000000002"


def test_same_revision_placeholder_pass_manifest_is_not_reused(tmp_path):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    source_sha256 = "c" * 64
    _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000003",
        source_sha256=source_sha256,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
    )

    assert (
        service._find_reusable_audit(
            source_sha256, exclude_audit_id="step-audit-ffffffffffffffff"
        )
        is None
    )


def test_axis_first_manifest_groundwork_retains_provenance_frame_tolerance_and_residual():
    frame = {
        "method": "deterministic_analytic_axis_consensus_r3",
        "source_axis_origin_mm": [0.0, 0.0, 0.0],
        "source_axis_direction": [0.0, 0.0, 1.0],
        "source_to_canonical_matrix": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "scale": 1.0,
        "primary_icp_applied": False,
        "outer_radius_mm": 50.0,
        "axis_consensus": {
            "selected_cluster": {
                "source_entity_ids": ["source_face_00002", "source_edge_00008"]
            },
            "tolerance": {"line_distance_mm": 0.02, "angular_deg": 0.05},
            "residual": {"line_rms_mm": 0.001, "angular_spread_deg": 0.002},
        },
        "coarse_topology_partition": {
            "invariants": {"all_source_faces_accounted_for": True}
        },
    }

    payload = _axis_first_section_reconstruction_manifest(
        frame=frame,
        semantics={
            "main_blade_count": 13,
            "splitter_blade_count": 0,
            "pitch_deg": 360.0 / 13.0,
        },
        mapping={"mapping_id": "mapping", "geometry_patch_version": "1.1.2"},
        reconstruction={"surface_count": 84},
        comparison={"bidirectional": {"rms_mm": 2.0}},
    )

    axis = payload["canonical_frame"]["axis"]
    readiness = payload["algorithm_readiness"]
    assert readiness["status"] == "INCOMPLETE"
    assert readiness["algorithm_ready"] is False
    assert readiness["cache_reusable"] is False
    assert axis["source_entity_ids"] == ["source_face_00002", "source_edge_00008"]
    assert axis["confidence"]
    assert axis["coordinate_frame"] == "source_cartesian_mm"
    assert axis["units"] == "mm"
    assert axis["tolerance"]["line_distance_mm"] == 0.02
    assert axis["residual"]["line_rms_mm"] == 0.001
    assert axis["provenance"]["authority"] == "uploaded_step_brep"
    assert (
        _axis_first_cache_manifest_complete(
            {"axis_first_section_reconstruction": payload}
        )
        is False
    )


def test_final_cache_completeness_rejects_empty_or_unvalidated_required_records(
    tmp_path,
):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    audit_dir = _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000004",
        source_sha256="d" * 64,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))

    assert _axis_first_cache_manifest_complete(manifest) is True

    for section_name in (
        "support_recovery",
        "span_measurement_lattice",
        "representative_blades",
        "v11_2_mapping",
        "pattern_instances",
        "regional_deviation",
    ):
        incomplete = json.loads(json.dumps(manifest))
        incomplete["axis_first_section_reconstruction"][section_name] = {
            "status": "PASS"
        }
        assert _axis_first_cache_manifest_complete(incomplete) is False, section_name

        unvalidated = json.loads(json.dumps(manifest))
        unvalidated["axis_first_section_reconstruction"][section_name][
            "status"
        ] = "PENDING"
        assert _axis_first_cache_manifest_complete(unvalidated) is False, section_name


def test_cache_rejects_singleton_component_and_loop_outside_representative(tmp_path):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    audit_dir = _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000010",
        source_sha256="b" * 64,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    assert _axis_first_cache_manifest_complete(manifest) is True

    singleton = json.loads(json.dumps(manifest))
    component = singleton["axis_first_section_reconstruction"][
        "periodic_populations"
    ]["main"]["component_records"][0]
    component["source_entity_ids"] = ["source_face_00010_0"]
    component["source_face_ids"] = ["source_face_00010_0"]
    component["face_count"] = 1
    component["component_completeness"] = {
        "status": "INCOMPLETE",
        "blade_side_face_ids": ["source_face_00010_0"],
        "root_edge_face_ids": [],
    }
    component["provenance"]["source_entity_ids"] = ["source_face_00010_0"]
    _rehash_cache_evidence(component)
    assert _axis_first_cache_manifest_complete(singleton) is False

    unlinked = json.loads(json.dumps(manifest))
    loop = unlinked["axis_first_section_reconstruction"]["representative_blades"][
        "section_loops"
    ][0]
    loop["source_entity_ids"] = ["source_face_outside_component"]
    loop["source_face_ids"] = ["source_face_outside_component"]
    loop["provenance"]["source_entity_ids"] = ["source_face_outside_component"]
    _rehash_cache_evidence(loop)
    assert _axis_first_cache_manifest_complete(unlinked) is False

    duplicate_provenance = json.loads(json.dumps(manifest))
    duplicate_component = duplicate_provenance["axis_first_section_reconstruction"][
        "periodic_populations"
    ]["main"]["component_records"][0]
    duplicate_component["source_entity_ids"].append("source_face_00010_0")
    duplicate_component["source_face_ids"].append("source_face_00010_0")
    duplicate_component["face_count"] += 1
    duplicate_component["provenance"]["source_entity_ids"].append(
        "source_face_00010_0"
    )
    _rehash_cache_evidence(duplicate_component)
    assert _axis_first_cache_manifest_complete(duplicate_provenance) is False

    inconsistent_loop_provenance = json.loads(json.dumps(manifest))
    inconsistent_loop = inconsistent_loop_provenance[
        "axis_first_section_reconstruction"
    ]["representative_blades"]["section_loops"][0]
    inconsistent_loop["source_entity_ids"] = ["source_face_00010_0"]
    inconsistent_loop["provenance"]["source_entity_ids"] = ["source_face_00010_0"]
    _rehash_cache_evidence(inconsistent_loop)
    assert _axis_first_cache_manifest_complete(inconsistent_loop_provenance) is False


def test_cache_completeness_rejects_semantic_placeholders_and_empty_axis_evidence(
    tmp_path,
):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    audit_dir = _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000005",
        source_sha256="e" * 64,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    payload = manifest["axis_first_section_reconstruction"]
    payload["canonical_frame"]["axis"] = {
        "source_entity_ids": [],
        "confidence": {},
        "coordinate_frame": "source_cartesian_mm",
        "units": "mm",
        "tolerance": {},
        "residual": {},
        "provenance": {},
    }
    for section_name in (
        "support_recovery",
        "periodic_populations",
        "span_measurement_lattice",
        "representative_blades",
        "v11_2_mapping",
        "pattern_instances",
        "regional_deviation",
    ):
        payload[section_name] = {"status": "PASS", "placeholder": True}

    assert _axis_first_cache_manifest_complete(manifest) is False


def test_cache_recomputes_canonical_evidence_hash_and_rejects_forged_ready(tmp_path):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    audit_dir = _write_pass_cache(
        service,
        audit_id="step-audit-0000000000000006",
        source_sha256="f" * 64,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    assert _axis_first_cache_manifest_complete(manifest) is True

    forged = json.loads(json.dumps(manifest))
    forged_axis = forged["axis_first_section_reconstruction"]["canonical_frame"]["axis"]
    forged_axis["residual"]["rms_mm"] = 999.0
    assert _axis_first_cache_manifest_complete(forged) is False

    placeholder = json.loads(json.dumps(manifest))
    placeholder_axis = placeholder["axis_first_section_reconstruction"]["canonical_frame"]["axis"]
    placeholder_axis["provenance"]["authority"] = "placeholder_authority"
    placeholder_axis["evidence_hash"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in placeholder_axis.items() if key != "evidence_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert _axis_first_cache_manifest_complete(placeholder) is False

    untyped = json.loads(json.dumps(manifest))
    untyped["axis_first_section_reconstruction"]["support_recovery"]["confidence"] = {
        "level": "high"
    }
    assert _axis_first_cache_manifest_complete(untyped) is False


@pytest.mark.parametrize(
    "invalid_matrix",
    (
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.1, 1.0]],
        [[2.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        [[1.0, 0.2, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        [[-1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
    ),
)
def test_cache_rejects_non_rigid_canonical_matrix_even_with_rehashed_evidence(
    tmp_path, invalid_matrix
):
    service = StepReconstructionAuditService(tmp_path / "service", run_async=False)
    audit_dir = _write_pass_cache(
        service,
        audit_id=f"step-audit-matrix-{abs(hash(str(invalid_matrix)))}",
        source_sha256="a" * 64,
        revision=AUDIT_IMPLEMENTATION_REVISION,
        axis_first_revision=AUDIT_IMPLEMENTATION_REVISION,
        complete_axis_first=True,
    )
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    canonical = manifest["axis_first_section_reconstruction"]["canonical_frame"]
    canonical["source_to_canonical_matrix"] = invalid_matrix
    canonical["axis"]["source_to_canonical_matrix"] = invalid_matrix
    _rehash_cache_evidence(canonical["axis"])

    assert _axis_first_cache_manifest_complete(manifest) is False
