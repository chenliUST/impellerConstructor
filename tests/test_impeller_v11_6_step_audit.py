from __future__ import annotations

# ruff: noqa: E402

import hashlib
import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis.impeller_v11_6_step_audit import (
    AUDIT_CONTRACT_ID,
    AUDIT_IMPLEMENTATION_REVISION,
    AUDIT_RUNTIME_VERSION,
    CANONICAL_GEOMETRY_VERSION,
    SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD,
    SOURCE_REVIEW_LINEAR_TOLERANCE_MM,
    StepAuditError,
    _apply_bounded_audit_sampling,
    _audit_artifacts_match_manifest,
    _atomic_json,
    _axis_first_cache_manifest_complete,
    _manifest_digest_matches_status,
    _validated_mapping_canonical_payload,
    classify_impeller_semantics,
    extract_v11_review_parameters,
    fit_profile_controls,
    load_step_source,
    resolve_canonical_frame,
    sanitize_step_filename,
    validate_step_header,
)
from part_rule_synthesis.impeller_v11_6_comparison_scope import (
    COMPARISON_SCOPE_CONTRACT_ID,
)
from part_rule_synthesis import impeller_runtime_compiler as compiler_module
from part_rule_synthesis import impeller_v11_6_axis_first_pipeline as axis_pipeline
from part_rule_synthesis import impeller_v11_6_step_audit as step_audit_module
from part_rule_synthesis import service as service_module
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import RuleSynthesisService
from step_fixtures import write_periodic_impeller_step


def test_v116_contract_keeps_v112_geometry_authority():
    assert AUDIT_CONTRACT_ID == "impeller_v1_1_6_step_reconstruction_audit"
    assert AUDIT_RUNTIME_VERSION == "1.1.6"
    assert CANONICAL_GEOMETRY_VERSION == "1.1.2"


def test_deviation_checkpoints_are_shared_by_exact_contract_revision(tmp_path):
    first = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    second = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )

    assert first.deviation_checkpoint_root == second.deviation_checkpoint_root
    assert first.deviation_checkpoint_root.name == (
        step_audit_module.DEVIATION_CHECKPOINT_REVISION
    )
    assert first.deviation_checkpoint_root.parent.name == (
        "step_reconstruction_cache"
    )


def test_deviation_progress_is_persisted_without_completing_the_stage(tmp_path):
    service = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    handle = service.begin_upload("progress.step")

    service._set_deviation_progress(
        handle.audit_id,
        {
            "role": "blade_pressure_surface_0001",
            "completed_surface_count": 3,
            "total_surface_count": 12,
            "duration_ms": 1250.0,
        },
    )

    status = service.status(handle.audit_id)
    assert status["status"] == "UPLOADING"
    assert status["current_stage"] == "surface_deviation"
    assert status["progress"] == {
        "phase": "surface_deviation",
        "completed_surface_count": 3,
        "total_surface_count": 12,
        "fraction_complete": 0.25,
        "last_surface_id": "blade_pressure_surface_0001",
        "last_surface_duration_ms": 1250.0,
        "updated_at": status["progress"]["updated_at"],
    }


def test_recovery_does_not_interrupt_audit_owned_by_a_live_worker(tmp_path):
    owner = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    handle = owner.begin_upload("owned.step")
    status = owner.status(handle.audit_id)
    status.update(
        {
            "status": "RUNNING",
            "worker_owner": {
                "service_instance_id": owner.instance_id,
                "pid": os.getpid(),
                "state": "RUNNING",
            },
        }
    )
    owner._write_status(handle.audit_id, status)

    observer = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    observer.recover_interrupted_audits()

    recovered = observer.status(handle.audit_id)
    assert recovered["status"] == "RUNNING"
    assert "failure" not in recovered


def test_recovery_marks_audit_owned_by_dead_worker_as_interrupted(
    tmp_path, monkeypatch
):
    owner = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    handle = owner.begin_upload("orphan.step")
    status = owner.status(handle.audit_id)
    status.update(
        {
            "status": "RUNNING",
            "current_stage": "surface_deviation",
            "worker_owner": {
                "service_instance_id": "dead-instance",
                "pid": 999_999_999,
                "state": "RUNNING",
            },
        }
    )
    owner._write_status(handle.audit_id, status)
    monkeypatch.setattr(step_audit_module, "_process_is_alive", lambda _pid: False)

    observer = step_audit_module.StepReconstructionAuditService(
        tmp_path, run_async=False
    )
    observer.recover_interrupted_audits()

    recovered = observer.status(handle.audit_id)
    assert recovered["status"] == "FAILED"
    assert recovered["failure"]["reason"] == "v116_audit_interrupted"
    assert recovered["failure"]["details"]["previous_stage"] == (
        "surface_deviation"
    )


def test_r13_review_sampling_meets_dense_surface_and_source_targets():
    defaults = {
        "side_sample_count": 7,
        "theta_sample_count": 999,
    }

    _apply_bounded_audit_sampling(defaults)

    assert defaults["side_sample_count"] == 129
    assert defaults["edge_cap_sample_count"] == 65
    assert defaults["surface_span_sample_count"] == 33
    assert defaults["root_short_direction_sample_count"] == 17
    assert defaults["profile_revolve_sample_count"] == 129
    assert defaults["theta_sample_count"] == 181
    assert defaults["v1_1_6_audit_sampling_policy"]["changes_geometry_math"] is False
    assert SOURCE_REVIEW_LINEAR_TOLERANCE_MM == pytest.approx(0.06)
    assert SOURCE_REVIEW_ANGULAR_TOLERANCE_RAD == pytest.approx(0.08)


def test_completed_rejected_review_audit_is_cacheable_but_not_promotable(tmp_path):
    required_sections = {
        "canonical_frame": {"status": "REVIEW_EVIDENCE"},
        "support_recovery": {"status": "REVIEW_EVIDENCE"},
        "periodic_populations": {"status": "REVIEW_EVIDENCE"},
        "span_measurement_lattice": {"status": "REVIEW_EVIDENCE"},
        "representative_blades": {"status": "REVIEW_EVIDENCE"},
        "v11_2_mapping": {"status": "REVIEW_EVIDENCE"},
        "pattern_instances": {"status": "REVIEW_EVIDENCE"},
        "regional_deviation": {
            "status": "CORRESPONDING_SURFACES_MEASURED_REVIEW_ONLY"
        },
        "invariants": {"canonical_geometry_version": CANONICAL_GEOMETRY_VERSION},
    }
    manifest = {
        "status": "PASS",
        "source": {"sha256": "a" * 64},
        "legacy_workflow_status": "PASS",
        "axis_first_algorithm_status": "REJECTED",
        "promotable": False,
        "reconstruction_disposition": "review_only_not_promotable",
        "parameter_mapping": {
            "mapping_status": "REJECTED_REVIEW_CANDIDATE"
        },
        "comparison_scope": {
            "contract_id": COMPARISON_SCOPE_CONTRACT_ID,
            "status": "PARTIAL_REVIEW",
            "coverage_complete": True,
        },
        "comparison": {
            "contract_id": (
                "impeller_v1_1_6_corresponding_surface_deviation_v5"
            )
        },
        "axis_first_section_reconstruction": {
            "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
            "algorithm_readiness": {
                "status": "REJECTED",
                "algorithm_ready": False,
                "cache_reusable": False,
                "failed_terms": ["camber"],
            },
            **required_sections,
        },
    }

    assert _axis_first_cache_manifest_complete(manifest) is True

    artifact_names = {
        "source_stl": "source.stl",
        "reconstruction_stl": "reconstruction.stl",
        "heatmap": "heatmap.json",
        "geometric_manifest": "geometric-manifest.json",
    }
    manifest["artifacts"] = {}
    for artifact_id, name in artifact_names.items():
        payload = f"evidence:{artifact_id}".encode()
        (tmp_path / name).write_bytes(payload)
        manifest["artifacts"][artifact_id] = {
            "file_name": name,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    assert _audit_artifacts_match_manifest(tmp_path, manifest) is True
    (tmp_path / "heatmap.json").write_bytes(b"tampered")
    assert _audit_artifacts_match_manifest(tmp_path, manifest) is False

    manifest_path = tmp_path / "manifest.json"
    _atomic_json(manifest_path, manifest)
    status = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    assert _manifest_digest_matches_status(manifest_path, status) is True
    manifest_path.write_text("{}", encoding="utf-8")
    assert _manifest_digest_matches_status(manifest_path, status) is False


def test_pass_cache_binds_status_manifest_source_and_audit_identity(
    tmp_path, monkeypatch
):
    audit_dir = tmp_path / "step-audit-0123456789abcdef"
    audit_dir.mkdir()
    source_sha256 = "a" * 64
    manifest = {
        "audit_id": audit_dir.name,
        "contract_id": AUDIT_CONTRACT_ID,
        "implementation_revision": AUDIT_IMPLEMENTATION_REVISION,
        "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
        "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "source": {"sha256": source_sha256},
        "comparison_alignment": {
            "method": "bounded_symmetric_periodic_phase_search"
        },
    }
    manifest_path = audit_dir / "manifest.json"
    _atomic_json(manifest_path, manifest)
    status = {
        "audit_id": audit_dir.name,
        "contract_id": AUDIT_CONTRACT_ID,
        "implementation_revision": AUDIT_IMPLEMENTATION_REVISION,
        "algorithm_revision": AUDIT_IMPLEMENTATION_REVISION,
        "canonical_geometry_version": CANONICAL_GEOMETRY_VERSION,
        "source": {"sha256": source_sha256},
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        step_audit_module, "_axis_first_cache_manifest_complete", lambda _: True
    )
    monkeypatch.setattr(
        step_audit_module, "_audit_artifacts_match_manifest", lambda *_: True
    )

    compatible = step_audit_module.StepReconstructionAuditService._compatible_pass_manifest
    assert compatible(audit_dir, status) is True
    assert compatible(
        audit_dir, {**status, "source": {"sha256": "b" * 64}}
    ) is False
    assert compatible(audit_dir, {**status, "audit_id": "step-audit-stale"}) is False

    manifest["audit_id"] = "step-audit-stale"
    _atomic_json(manifest_path, manifest)
    stale_status = {
        **status,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    assert compatible(audit_dir, stale_status) is False


def test_step_audit_error_contract_covers_axis_first_pipeline_failures():
    for reason in axis_pipeline._STABLE_REASONS:
        assert StepAuditError(reason, "contract probe").reason == reason


def test_step_filename_is_sanitized_without_trusting_extension():
    assert sanitize_step_filename("../../outside/part.stp") == "part.stp"
    assert sanitize_step_filename(r"C:\customer\part name.bin") == "part_name.bin.step"


def test_support_profile_is_fitted_from_dense_targets_not_copied_as_poles():
    samples = [[float(index), (5.0 - index) ** 2 * 0.2] for index in range(11)]
    controls, residual = fit_profile_controls(samples, control_count=6, degree=3)
    assert len(controls) == 6
    assert controls[0] == samples[0]
    assert controls[-1] == samples[-1]
    assert controls != samples[:6]
    assert residual >= 0.0


def test_reconstruction_uses_only_the_mapper_approved_canonical_payload():
    canonical = {
        "canonical_payload_version": "1.1.2",
        "canonical_input_source": "v116_bounded_measurement_mapping",
        "support_profiles": {"hub_profile": {"control_points": [[1.0, 2.0]]}},
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    mapping = {
        "regenerated_canonical_payload": canonical,
        "canonical_payload_hash_sha256": digest,
    }

    approved = _validated_mapping_canonical_payload(mapping)
    approved["support_profiles"]["hub_profile"]["control_points"][0][0] = 99.0
    assert canonical["support_profiles"]["hub_profile"]["control_points"][0][0] == 1.0

    tampered = dict(mapping)
    tampered["regenerated_canonical_payload"] = {
        **canonical,
        "canonical_input_source": "tampered",
    }
    with pytest.raises(StepAuditError) as caught:
        _validated_mapping_canonical_payload(tampered)
    assert caught.value.reason == "v116_step_reconstruction_validation_failed"


def test_service_consumes_mapper_approved_canonical_without_regeneration(monkeypatch):
    canonical = {
        "canonical_payload_version": "1.1.2",
        "canonical_input_source": "v116_bounded_measurement_mapping",
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    context = {
        "geometry_patch_version": "1.1.2",
        "resolved_blade_to_blade_loop_family_defaults": {},
        "canonical_nurbs_parameterization": canonical,
        "canonical_payload_authority": "v116_mapper_approved",
        "canonical_payload_hash_sha256": digest,
    }

    def forbidden_regeneration(*_args, **_kwargs):
        raise AssertionError("approved canonical payload must not be regenerated")

    monkeypatch.setattr(
        service_module,
        "canonical_nurbs_from_v11_defaults",
        forbidden_regeneration,
    )
    resolved = service_module._v11_resolved_defaults_for_instantiation(
        context,
        parameters={"blade_thickness_mm": 3.0},
        profile_overrides={},
    )

    assert resolved["canonical_nurbs_parameterization"] == canonical
    tampered = dict(context)
    tampered["canonical_payload_hash_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        service_module._v11_resolved_defaults_for_instantiation(
            tampered,
            parameters={},
            profile_overrides={},
        )
    with pytest.raises(ValueError, match="forbids geometry overrides"):
        service_module._v11_resolved_defaults_for_instantiation(
            context,
            parameters={},
            profile_overrides={},
            blade_to_blade_loop_family_overrides={
                "canonical_nurbs_parameterization": {
                    "canonical_payload_version": "1.1.2",
                    "canonical_input_source": "unapproved-override",
                }
            },
        )


def test_runtime_compiler_consumes_mapper_approved_canonical_without_regeneration(
    monkeypatch,
):
    ordinary = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    canonical = json.loads(json.dumps(ordinary["canonical_nurbs_parameterization"]))
    canonical["canonical_input_source"] = "v116-compiler-approved"
    digest = service_module._canonical_payload_sha256(canonical)

    def forbidden_regeneration(*_args, **_kwargs):
        raise AssertionError("compiler must not regenerate mapper-approved canonical")

    monkeypatch.setattr(
        compiler_module,
        "canonical_nurbs_from_v11_defaults",
        forbidden_regeneration,
    )
    runtime = compile_impeller_runtime_preset(
        "radial_open_reference_v1_1",
        mapper_approved_canonical_payload=canonical,
        mapper_approved_canonical_hash_sha256=digest,
    )

    assert runtime["canonical_nurbs_parameterization"] == canonical
    assert runtime["canonical_payload_authority"] == "v116_mapper_approved"
    assert runtime["canonical_payload_hash_sha256"] == digest

    with pytest.raises(ValueError, match="hash mismatch"):
        compile_impeller_runtime_preset(
            "radial_open_reference_v1_1",
            mapper_approved_canonical_payload=canonical,
            mapper_approved_canonical_hash_sha256="0" * 64,
        )


def test_reconstruct_passes_mapper_approved_canonical_through_runtime_compiler(
    tmp_path, monkeypatch
):
    canonical = {
        "canonical_payload_version": "1.1.2",
        "canonical_input_source": "v116-bounded-mapping",
    }
    digest = service_module._canonical_payload_sha256(canonical)
    mapping = {
        "regenerated_canonical_payload": canonical,
        "canonical_payload_hash_sha256": digest,
        "resolved_blade_to_blade_loop_family_defaults": {
            "tip_attachment_mode": "open_tip_reference",
        },
        "parameters": {},
        "parameter_rows": [],
    }
    compiled_calls = []
    instantiated_runtimes = []

    def compile_probe(preset_id, **kwargs):
        compiled_calls.append((preset_id, kwargs))
        assert kwargs["mapper_approved_canonical_payload"] == canonical
        assert kwargs["mapper_approved_canonical_hash_sha256"] == digest
        return {
            "geometry_patch_version": "1.1.2",
            "parameters": {},
            "canonical_nurbs_parameterization": canonical,
            "canonical_payload_authority": "v116_mapper_approved",
            "canonical_payload_hash_sha256": digest,
        }

    class FakeService:
        def __init__(self, _root):
            self.engines = {}

        def instantiate(self, engine_id, _parameters, **kwargs):
            instantiated_runtimes.append(self.engines[engine_id])
            return SimpleNamespace(
                run_id=f"run-{len(instantiated_runtimes)}",
                manifest={
                    "generation_id": f"generation-{len(instantiated_runtimes)}",
                    "geometry_version": "1.1",
                    "geometry_patch_version": "1.1.2",
                    "geometry_validation_status": "PASS",
                    "operation_graph_hash": kwargs["geometry_stage"],
                    "parameters": {},
                    "geometry": {"surface_graph": {"surfaces": []}},
                },
            )

    monkeypatch.setattr(
        step_audit_module, "compile_impeller_runtime_preset", compile_probe
    )
    monkeypatch.setattr(step_audit_module, "RuleSynthesisService", FakeService)
    monkeypatch.setattr(
        step_audit_module.pattern_reconstruction,
        "validate_mapped_pattern_reconstruction",
        lambda graph, _mapping, _source, **_kwargs: (
            graph,
            {"status": "PASS", "contract": "task9-test-double"},
        ),
    )
    monkeypatch.setattr(
        step_audit_module, "_write_surface_graph_stl", lambda *_args: None
    )

    result = step_audit_module.reconstruct_with_current_v11(
        tmp_path,
        mapping,
        source_manifest={"sha256": "source-sha"},
        task8_recovery_authority={"authority": "task9-test-double"},
        stage_callback=lambda *_args: None,
    )

    assert len(compiled_calls) == 1
    assert len(instantiated_runtimes) == 3
    assert all(
        runtime["canonical_nurbs_parameterization"] == canonical
        and runtime["canonical_payload_hash_sha256"] == digest
        for runtime in instantiated_runtimes
    )
    assert result["manifest"]["geometry_patch_version"] == "1.1.2"
    assert result["manifest"]["pattern_material_contract"]["status"] == "PASS"


def test_zero_measured_radius_disables_only_legacy_transition_policy():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    root_family = runtime["edge_families"]["blade_root_to_hub"]
    leading_family = runtime["edge_families"]["blade_leading_edge"]

    step_audit_module._disable_zero_radius_legacy_transition_policies(
        runtime,
        {
            root_family["default_radius_parameter"]: 0.0,
            leading_family["default_radius_parameter"]: 2.0,
        },
    )

    assert root_family["default_treatment"] == "none"
    assert root_family["default_continuity"] == "G0"
    assert leading_family["default_treatment"] != "none"
    root_policy = runtime["transition_policy_defaults"][
        "blade_root_to_hub.default"
    ]
    assert root_policy["treatment"] == "none"
    assert root_policy["continuity"] == "G0"
    assert root_policy["radius_mm"] == 0.0


def test_material_export_graph_excludes_open_tip_reference():
    graph = {
        "surfaces": [
            {"id": "hub", "role": "hub_support", "material": True},
            {
                "id": "tip-reference",
                "role": "open_tip_reference",
                "material": False,
                "export_default": "excluded",
            },
            {
                "id": "blade",
                "role": "blade_pressure",
                "material": True,
                "export_default": "included",
            },
        ]
    }

    exported = step_audit_module._material_export_surface_graph(graph)

    assert [surface["id"] for surface in exported["surfaces"]] == [
        "hub",
        "blade",
    ]


def test_geometric_manifest_preserves_uv_topology_and_applies_phase_alignment(tmp_path):
    path = tmp_path / "geometric-manifest.json"
    graph = {
        "surfaces": [
            {
                "id": "blade-pressure",
                "role": "blade_pressure",
                "face_family": "blade_pressure",
                "material": True,
                "display": {"color": "#759b7d"},
                "uv_grid": [
                    [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                    [[1.0, 1.0, 0.0], [2.0, 1.0, 0.0]],
                ],
            },
            {
                "id": "open-tip-reference",
                "role": "open_tip_reference",
                "material": False,
                "export_default": "excluded",
                "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]],
            },
        ]
    }

    step_audit_module._write_geometric_manifest(
        path,
        graph,
        alignment_matrix=step_audit_module._rotation_about_z_matrix(90.0),
        comparison_alignment={"rotation_about_axis_deg": 90.0},
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["contract_id"] == "impeller_v1_1_6_geometric_manifest_v2"
    assert payload["render_contract"]["triangle_edges_forbidden"] is True
    assert payload["surface_count"] == 1
    assert payload["surfaces"][0]["uv_grid"][0][0] == pytest.approx(
        [0.0, 1.0, 0.0]
    )


@pytest.mark.parametrize(
    ("comparison_role", "surface", "expected"),
    (
        ("hub_flowpath", {"id": "hub_support_surface", "role": "hub_support"}, True),
        ("hub_flowpath", {"id": "hub_top_annulus_surface", "role": "hub_support"}, False),
        (
            "hub_material_closure",
            {"id": "hub_top_annulus_surface", "role": "hub_support"},
            True,
        ),
        ("blade_root_attachment", {"id": "root", "role": "root_to_hub_attachment"}, True),
        ("blade_sides", {"id": "pressure", "role": "blade_pressure"}, True),
        ("blade_leading_edge", {"id": "leading", "role": "blade_leading_edge"}, True),
        ("blade_trailing_edge", {"id": "trailing", "role": "blade_trailing_edge"}, True),
        ("blade_sides", {"id": "root", "role": "root_to_hub_attachment"}, False),
        ("blade_tip_attachment", {"id": "tip-root", "role": "closed_shroud_attachment"}, True),
        ("blade_tip", {"id": "tip", "role": "open_tip_dome"}, True),
    ),
)
def test_comparison_role_mapping_is_explicit(comparison_role, surface, expected):
    assert (
        step_audit_module._surface_matches_comparison_role(surface, comparison_role)
        is expected
    )


def test_reconstruction_blade_index_is_read_from_surface_identity():
    assert step_audit_module._surface_blade_index(
        {"id": "blade_12_pressure_surface", "role": "blade_pressure"}
    ) == 12
    assert step_audit_module._surface_blade_index(
        {"id": "hub_support_surface", "role": "hub_support"}
    ) is None


def test_post_phase_instance_assignment_applies_the_best_cyclic_shift():
    records = []
    source_regions = {}
    reconstruction_regions = {}
    for population, count, phase, reconstruction_offset in (
        ("main", 4, 0.0, 1),
        ("splitter", 3, 20.0, -1),
    ):
        pitch = 360.0 / count
        for index in range(count):
            region_id = f"blade_sides::{population}-{index:02d}"
            records.append(
                {
                    "comparison_region_id": region_id,
                    "reconstruction_role": "blade_sides",
                    "periodic_instance_id": f"{population}-{index:02d}",
                    "periodic_population": population,
                    "periodic_lattice_index": index,
                    "reconstruction_blade_pair_index": index,
                }
            )
            source_regions[region_id] = _angular_triangle_mesh(
                phase + index * pitch
            )
            reconstruction_regions[region_id] = _angular_triangle_mesh(
                phase + ((index + reconstruction_offset) % count) * pitch
            )

    pairs, diagnostics = step_audit_module._phase_aligned_comparison_regions(
        source_regions,
        reconstruction_regions,
        {"included_surfaces": records},
    )

    assert diagnostics["populations"]["main"]["cyclic_shift"] == 3
    assert diagnostics["populations"]["splitter"]["cyclic_shift"] == 1
    for source, reconstructed in pairs.values():
        source_center = np.mean(source.vertices, axis=0)
        reconstruction_center = np.mean(reconstructed.vertices, axis=0)
        assert math.atan2(source_center[1], source_center[0]) == pytest.approx(
            math.atan2(reconstruction_center[1], reconstruction_center[0])
        )


def _angular_triangle_mesh(angle_deg):
    angle = math.radians(float(angle_deg))
    center = np.asarray([10.0 * math.cos(angle), 10.0 * math.sin(angle), 0.0])
    vertices = np.asarray(
        [
            center + [-0.1, -0.1, 0.0],
            center + [0.1, -0.1, 0.0],
            center + [0.0, 0.2, 0.0],
        ],
        dtype=float,
    )
    return step_audit_module.TriangleMesh(
        vertices=vertices,
        triangles=np.asarray([[0, 1, 2]], dtype=np.int32),
        normals=np.asarray([[0.0, 0.0, 1.0]], dtype=float),
    )


def test_ordinary_v112_runtime_compiler_retains_legacy_regeneration(monkeypatch):
    calls = []

    def regeneration_probe(parameters, defaults):
        calls.append((parameters, defaults))
        return {
            "canonical_payload_version": "1.1.2",
            "canonical_input_source": "ordinary-compiler",
        }

    monkeypatch.setattr(
        compiler_module,
        "canonical_nurbs_from_v11_defaults",
        regeneration_probe,
    )
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")

    assert len(calls) == 1
    assert runtime["canonical_nurbs_parameterization"]["canonical_input_source"] == (
        "ordinary-compiler"
    )
    assert "canonical_payload_authority" not in runtime


def test_ordinary_v112_service_context_retains_legacy_regeneration(monkeypatch):
    calls = []

    def regeneration_probe(parameters, defaults, *, source):
        calls.append((parameters, defaults, source))
        return {
            "canonical_payload_version": "1.1.2",
            "canonical_input_source": source,
        }

    monkeypatch.setattr(
        service_module,
        "canonical_nurbs_from_v11_defaults",
        regeneration_probe,
    )
    resolved = service_module._v11_resolved_defaults_for_instantiation(
        {
            "geometry_patch_version": "1.1.2",
            "resolved_blade_to_blade_loop_family_defaults": {},
            "canonical_input_source": "ordinary-v112-preset",
        },
        parameters={"blade_thickness_mm": 3.0},
        profile_overrides={},
    )

    assert len(calls) == 1
    assert resolved["canonical_nurbs_parameterization"] == {
        "canonical_payload_version": "1.1.2",
        "canonical_input_source": "ordinary-v112-preset",
    }


def test_service_instantiation_binds_mapper_approved_canonical_payload(
    tmp_path, monkeypatch
):
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    canonical = json.loads(
        json.dumps(runtime["canonical_nurbs_parameterization"])
    )
    canonical["canonical_input_source"] = "v116-mapper-approved-integration"
    digest = service_module._canonical_payload_sha256(canonical)
    runtime["canonical_nurbs_parameterization"] = canonical
    runtime["canonical_payload_authority"] = "v116_mapper_approved"
    runtime["canonical_payload_hash_sha256"] = digest

    def forbidden_regeneration(*_args, **_kwargs):
        raise AssertionError("service must bind the approved canonical payload")

    monkeypatch.setattr(
        service_module,
        "canonical_nurbs_from_v11_defaults",
        forbidden_regeneration,
    )
    service = RuleSynthesisService(tmp_path / "runtime")
    service.engines["v116-approved"] = runtime
    run = service.instantiate(
        "v116-approved",
        {},
        geometry_stage="hub_support",
        review_only=True,
    )

    graph_canonical = run.manifest["geometry"]["surface_graph"][
        "canonical_nurbs_parameterization"
    ]
    assert service_module._canonical_payload_sha256(graph_canonical) == digest
    assert (
        graph_canonical["canonical_input_source"]
        == "v116-mapper-approved-integration"
    )


@pytest.mark.parametrize(
    ("input_name", "input_value"),
    [
        ("parameters", {"blade_count": 8}),
        ("profile_overrides", {"hub_profile": {"control_points": []}}),
        ("curve_overrides", {"hub_curve": {"control_points": []}}),
        ("section_loop_overrides", {"side_sample_count": 17}),
        (
            "blade_to_blade_loop_family_overrides",
            {"canonical_nurbs_parameterization": {"canonical_payload_version": "1.1.2"}},
        ),
        ("transition_overrides", {"leading_edge": {"radius_mm": 2.0}}),
    ],
)
def test_mapper_approved_service_rejects_every_geometry_input(
    tmp_path, input_name, input_value
):
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    canonical = json.loads(json.dumps(runtime["canonical_nurbs_parameterization"]))
    canonical["canonical_input_source"] = "v116-frozen-runtime"
    runtime["canonical_nurbs_parameterization"] = canonical
    runtime["canonical_payload_authority"] = "v116_mapper_approved"
    runtime["canonical_payload_hash_sha256"] = (
        service_module._canonical_payload_sha256(canonical)
    )
    service = RuleSynthesisService(tmp_path / input_name)
    service.engines["v116-frozen"] = runtime
    parameters = input_value if input_name == "parameters" else {}
    keyword_inputs = {} if input_name == "parameters" else {input_name: input_value}

    with pytest.raises(ValueError, match=input_name):
        service.instantiate(
            "v116-frozen",
            parameters,
            geometry_stage="hub_support",
            review_only=True,
            **keyword_inputs,
        )


def test_atomic_json_retries_transient_windows_replace_lock_with_unique_temp(tmp_path, monkeypatch):
    destination = tmp_path / "status.json"
    real_replace = os.replace
    replace_sources: list[Path] = []

    def transiently_locked(source, target):
        replace_sources.append(Path(source))
        if len(replace_sources) < 3:
            raise PermissionError(5, "Access is denied", str(target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", transiently_locked)
    _atomic_json(destination, {"status": "RUNNING"})
    _atomic_json(destination, {"status": "PASS"})

    assert destination.read_text(encoding="utf-8").find('"PASS"') >= 0
    assert replace_sources[0] == replace_sources[1] == replace_sources[2]
    assert replace_sources[3] != replace_sources[0]
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_reports_persistence_failure_instead_of_step_parse_failure(tmp_path, monkeypatch):
    def persistently_locked(source, target):
        raise PermissionError(5, "Access is denied", str(target))

    monkeypatch.setattr(os, "replace", persistently_locked)
    monkeypatch.setattr("part_rule_synthesis.impeller_v11_6_step_audit.time.sleep", lambda _delay: None)

    with pytest.raises(StepAuditError) as raised:
        _atomic_json(tmp_path / "status.json", {"status": "RUNNING"})

    assert raised.value.reason == "v116_audit_persistence_failed"
    assert not list(tmp_path.glob("*.tmp"))


def test_synthetic_step_inventory_axis_and_periodicity(tmp_path):
    path = write_periodic_impeller_step(tmp_path / "synthetic.data", blade_count=8)
    header = validate_step_header(path)
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    semantics = classify_impeller_semantics(shape, source, frame)

    assert header["header_valid"] is True
    assert source["solid_count"] == 1
    assert source["closed_solid"] is True
    assert frame["scale"] == 1.0
    assert frame["primary_icp_applied"] is False
    assert semantics["main_blade_count"] == 8
    assert semantics["splitter_blade_count"] == 0
    assert semantics["classified_face_count"] == source["face_count"]


def test_step_audit_review_extractor_wraps_axis_pipeline_failures(monkeypatch):
    def fail(*_args, **_kwargs):
        raise step_audit_module.axis_first_pipeline.AxisFirstPipelineError(
            "v116_v112_mapping_residual_exceeded",
            "review extraction failed",
            stage="v112_mapping",
            details={"failed_terms": ["camber"]},
        )

    monkeypatch.setattr(
        step_audit_module.axis_first_pipeline,
        "extract_v11_review_parameters",
        fail,
    )

    with pytest.raises(StepAuditError) as captured:
        extract_v11_review_parameters(None, {}, {}, {})

    assert captured.value.reason == "v116_v112_mapping_residual_exceeded"
    assert captured.value.details["failed_terms"] == ["camber"]


def test_residual_rejected_candidate_has_explicit_review_disposition():
    disposition = step_audit_module._axis_first_algorithm_disposition(
        {
            "mapping_status": "REJECTED_REVIEW_CANDIDATE",
            "promotable": False,
            "failed_terms": ["camber", "edge_curves"],
            "rejection": {"reason": "v116_v112_mapping_residual_exceeded"},
        }
    )

    assert disposition["status_scope"] == "axis_first_rejected_review_candidate"
    assert disposition["axis_first_algorithm_status"] == "REJECTED"
    assert disposition["promotable"] is False
    assert disposition["reconstruction_disposition"] == "review_only_not_promotable"
    assert disposition["algorithm_readiness"]["status"] == "REJECTED"
    assert disposition["algorithm_readiness"]["failed_terms"] == [
        "camber",
        "edge_curves",
    ]


def test_acceptance_evaluation_refuses_legacy_baseline_for_corresponding_surfaces():
    evaluation = step_audit_module._evaluate_axis_first_acceptance(
        {
            "mapping_status": "REJECTED_REVIEW_CANDIDATE",
            "failed_terms": ["camber", "normal_thickness", "edge_curves"],
        },
        {
            "pattern_material_contract": {
                "status": "PASS",
                "pattern": {
                    "main_blade_count": 13,
                    "splitter_blade_count": 0,
                    "collision_status": "PASS",
                    "source_topology_separated": True,
                    "exact_brep_collision_checked": True,
                    "exact_brep_collision_free": True,
                },
                "material": {
                    "mode": "open",
                    "material_shroud": None,
                    "material_shroud_area_mm2": None,
                },
            }
        },
        {
            "contract_id": "impeller_v1_1_6_corresponding_surface_deviation_v5",
            "reconstruction_to_corresponding_source": {"rms_mm": 2.608269},
            "corresponding_source_to_reconstruction": {"rms_mm": 2.4},
            "symmetric_corresponding_sample_distribution": {"rms_mm": 2.51},
        },
    )

    assert evaluation["status"] == "NOT_EVALUATED"
    assert evaluation["promotable"] is False
    assert evaluation["topology"]["status"] == "PASS"
    assert evaluation["mapping"]["status"] == "FAIL"
    assert evaluation["comparison"]["baseline_status"] == (
        "UNAVAILABLE_NON_COMPARABLE_WITH_LEGACY_GLOBAL_METRICS"
    )


def test_acceptance_rejects_legacy_pattern_collision_pass_without_exact_evidence():
    reconstruction = {
        "pattern_material_contract": {
            "status": "PASS",
            "pattern": {
                "main_blade_count": 13,
                "splitter_blade_count": 0,
                "collision_status": "PASS",
            },
            "material": {
                "mode": "open",
                "material_shroud": None,
                "material_shroud_area_mm2": None,
            },
        }
    }

    evaluation = step_audit_module._evaluate_axis_first_acceptance(
        {"mapping_status": "PASS", "promotion": {"promotable": True}},
        reconstruction,
        {
            "contract_id": "impeller_v1_1_6_corresponding_surface_deviation_v5",
            "reconstruction_to_corresponding_source": {"rms_mm": 0.0},
        },
    )

    assert evaluation["topology"]["status"] == "FAIL"
    assert evaluation["status"] == "NOT_EVALUATED"


@pytest.mark.skipif(not os.environ.get("KS007G23B_STEP_PATH"), reason="local customer STEP not configured")
def test_optional_ks007g23b_exact_source_facts_and_mapping():
    path = Path(os.environ["KS007G23B_STEP_PATH"])
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    semantics = classify_impeller_semantics(shape, source, frame)
    mapping = extract_v11_review_parameters(shape, source, frame, semantics)

    assert (source["solid_count"], source["face_count"], source["edge_count"], source["vertex_count"]) == (1, 240, 666, 433)
    assert frame["outer_radius_mm"] == 51.6
    assert frame["main_bore_radius_mm"] == 7.9
    assert frame["axial_extent_mm"] == pytest.approx(36.5, abs=1.0e-4)
    assert semantics["main_blade_count"] == 13
    collision = semantics["periodic_population_recovery"]["collision_diagnostics"]
    assert collision["collision_free"] is None
    assert collision["collision_status"] == "UNKNOWN"
    assert collision["source_topology_separated"] is True
    assert collision["exact_brep_collision_checked"] is False
    assert mapping["mapping_status"] == "REJECTED_REVIEW_CANDIDATE"
    assert mapping["promotable"] is False
    assert set(mapping["failed_terms"]) == {
        "camber",
        "normal_thickness",
        "edge_curves",
        "periodicity",
        "pose",
    }
    assert mapping["geometry_patch_version"] == "1.1.2"
    assert mapping["support_recovery"]["hub_profile"]["accepted_sample_count"] > 6
    assert len(mapping["profile_fits"]["hub"]["control_points_rz_mm"]) == 6
    measurements = mapping["measurement_bundle"]
    tolerance = mapping["provenance"]["frame"]["source_tolerance_mm"]
    material = measurements["topology"]["material_measurements"]
    top_plane = material["hub_top_cap_thickness_mm"]["evidence"][
        "measurement_evidence"
    ]["top_material_plane"]
    bottom_plane = material["hub_bottom_thickness_mm"]["evidence"][
        "measurement_evidence"
    ]["bottom_material_plane"]
    assert top_plane["face_id"] == "source_face_00207"
    assert bottom_plane["face_id"] == "source_face_00201"
    assert top_plane["centroid_axis_offset_mm"] <= tolerance
    assert bottom_plane["centroid_axis_offset_mm"] <= tolerance
    assert {top_plane["face_id"], bottom_plane["face_id"]}.isdisjoint(
        {"source_face_00139", "source_face_00144", "source_face_00149"}
    )
