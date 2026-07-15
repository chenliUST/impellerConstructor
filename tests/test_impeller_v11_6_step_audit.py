from __future__ import annotations

# ruff: noqa: E402

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis.impeller_v11_6_step_audit import (
    AUDIT_CONTRACT_ID,
    AUDIT_RUNTIME_VERSION,
    CANONICAL_GEOMETRY_VERSION,
    StepAuditError,
    _atomic_json,
    _validated_mapping_canonical_payload,
    classify_impeller_semantics,
    extract_v11_review_parameters,
    fit_profile_controls,
    load_step_source,
    resolve_canonical_frame,
    sanitize_step_filename,
    validate_step_header,
)
from part_rule_synthesis import impeller_runtime_compiler as compiler_module
from part_rule_synthesis import impeller_v11_6_step_audit as step_audit_module
from part_rule_synthesis import service as service_module
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import RuleSynthesisService
from step_fixtures import write_periodic_impeller_step


def test_v116_contract_keeps_v112_geometry_authority():
    assert AUDIT_CONTRACT_ID == "impeller_v1_1_6_step_reconstruction_audit"
    assert AUDIT_RUNTIME_VERSION == "1.1.6"
    assert CANONICAL_GEOMETRY_VERSION == "1.1.2"


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


def test_acceptance_evaluation_reports_regression_without_promoting_topology_pass():
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
            "bidirectional": {"rms_mm": 2.608269, "p95_mm": 6.040549},
            "silhouettes": {
                "top_xy_hausdorff_mm": 5.27592,
                "meridional_rz_hausdorff_mm": 10.184372,
            },
        },
    )

    assert evaluation["status"] == "REJECTED"
    assert evaluation["topology"]["status"] == "PASS"
    assert evaluation["mapping"]["status"] == "FAIL"
    assert evaluation["improvement"]["bidirectional_rms"]["status"] == "FAIL"
    assert evaluation["improvement"]["top_silhouette"]["status"] == "FAIL"
    assert evaluation["improvement"]["meridional_silhouette"]["status"] == "FAIL"


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
            "bidirectional": {"rms_mm": 0.0, "p95_mm": 0.0},
            "silhouettes": {
                "top_xy_hausdorff_mm": 0.0,
                "meridional_rz_hausdorff_mm": 0.0,
            },
        },
    )

    assert evaluation["topology"]["status"] == "FAIL"
    assert evaluation["status"] == "REJECTED"


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
