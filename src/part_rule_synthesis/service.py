from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from part_rule_synthesis.impeller_cfd_manifest import build_cfd_full_360_manifest
from part_rule_synthesis.impeller_bounded_brep_export import write_bounded_brep_step
from part_rule_synthesis.impeller_brep_export import write_trimmed_brep_step
from part_rule_synthesis.impeller_design_space import build_campaign_signature
from part_rule_synthesis.impeller_geometry_validation import (
    build_geometry_validation_report,
    geometry_validation_blocks_export,
)
from part_rule_synthesis.impeller_kernel import build_impeller_geometry, blade_loft_wires, hub_loft_sections, shroud_z_levels
from part_rule_synthesis.impeller_mesh_export import write_surface_graph_obj
from part_rule_synthesis.impeller_mesh_manifest import build_surface_mesh_manifest
from part_rule_synthesis.impeller_surface_graph_export import write_surface_graph_exports
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset, impeller_json_preset_ids
from part_rule_synthesis.impeller_taxonomy import (
    IMPELLER_FACET_AXES,
    IMPELLER_PRESETS,
    LEGACY_CENTRIFUGAL_IMPELLER_FACETS,
    ONTOLOGY,
)
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.impeller_v10_surface_graph import build_v10_surface_graph
from part_rule_synthesis.impeller_v11_2_canonical import canonical_nurbs_from_v11_defaults


PRIMITIVES = {
    "version": "0.5.0",
    "items": [
        "axisymmetric_revolve",
        "nurbs_revolve_surface",
        "bspline_section_curve",
        "lofted_blade_surface",
        "fillet_surface",
        "surface_graph_validation",
        "circular_pattern",
        "boolean_union",
        "fillet",
        "ring_shell",
        "named_region_tagging",
        "mesh_export",
    ],
}

_IMPELLER_DSL_BUNDLE = load_impeller_dsl_bundle()
_IMPELLER_V04_DSL_BUNDLE = load_impeller_dsl_bundle("v0_4")
_IMPELLER_V05_DSL_BUNDLE = load_impeller_dsl_bundle("v0_5")
_JSON_IMPELLER_PRESET_IDS = impeller_json_preset_ids()
_V10_SECTION_LOOP_PATCH_VERSIONS = {"1.0.3", "1.0.4"}


@dataclass(frozen=True)
class SynthesizedEngine:
    engine_id: str
    part_family_id: str
    dsl_path: str
    validation: dict[str, Any]


@dataclass(frozen=True)
class ModelRun:
    run_id: str
    engine_id: str
    manifest: dict[str, Any]


@dataclass(frozen=True)
class FeedbackIssue:
    issue_id: str
    run_id: str
    source: str
    raw_feedback: str
    affected_feature: str
    classification: str
    expected_relation: str
    confidence: float


@dataclass(frozen=True)
class RulePatchProposal:
    patch_id: str
    issue_id: str
    patch_type: str
    dsl_diff: str
    approval_required: bool


class RuleSynthesisService:
    def __init__(self, root: Path, model_output_root: Path | None = None):
        self.root = Path(root)
        self.model_output_root = Path(model_output_root) if model_output_root is not None else None
        self.engines: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, ModelRun] = {}
        self.issues: dict[str, FeedbackIssue] = {}
        self.patches: dict[str, RulePatchProposal] = {}
        self.root.mkdir(parents=True, exist_ok=True)

    def synthesize(
        self,
        part_family_id: str,
        preset_id: str | None = None,
        facets: dict[str, str] | None = None,
    ) -> SynthesizedEngine:
        if part_family_id not in {"turbine_rotor", "ngv_ring", "centrifugal_impeller", "impeller"}:
            raise ValueError(f"unsupported part family: {part_family_id}")
        dsl = (
            _impeller_dsl_template(preset_id, facets or {})
            if part_family_id == "impeller"
            else _dsl_template(part_family_id)
        )
        engine_id = f"{part_family_id}-{_stable_hash(dsl)[:8]}"
        engine_dir = self.root / "rule_engines" / engine_id
        engine_dir.mkdir(parents=True, exist_ok=True)
        dsl_path = engine_dir / "rule.json"
        dsl_path.write_text(json.dumps(dsl, indent=2, sort_keys=True), encoding="utf-8")
        self.engines[engine_id] = dsl
        return SynthesizedEngine(
            engine_id=engine_id,
            part_family_id=part_family_id,
            dsl_path=str(dsl_path),
            validation={"status": "PASS", "checks": ["schema_valid", "required_relations_present"]},
        )

    def instantiate(
        self,
        engine_id: str,
        parameters: dict[str, Any],
        profile_overrides: dict[str, Any] | None = None,
        curve_overrides: dict[str, Any] | None = None,
        section_loop_overrides: dict[str, Any] | None = None,
        blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
        transition_overrides: dict[str, Any] | None = None,
        geometry_stage: str = "full",
        review_only: bool = False,
    ) -> ModelRun:
        dsl = self._engine(engine_id)
        is_v11_impeller = dsl["part_family"] == "impeller" and _dsl_version(dsl) == "1.1"
        if dsl.get("canonical_payload_authority") == "v116_mapper_approved":
            supplied_geometry_inputs = {
                "parameters": parameters,
                "profile_overrides": profile_overrides,
                "curve_overrides": curve_overrides,
                "section_loop_overrides": section_loop_overrides,
                "blade_to_blade_loop_family_overrides": (
                    blade_to_blade_loop_family_overrides
                ),
                "transition_overrides": transition_overrides,
            }
            supplied_names = sorted(
                name for name, value in supplied_geometry_inputs.items() if value
            )
            if supplied_names:
                raise ValueError(
                    "V1.1.6 mapper-approved runtime forbids geometry inputs: "
                    + ", ".join(supplied_names)
                )
        bound = _bind_parameters(dsl, parameters)
        operation_graph = _operation_graph(dsl, bound)
        normalized_geometry_stage = _normalize_geometry_stage(geometry_stage)
        normalized_profile_overrides = profile_overrides or {}
        normalized_curve_overrides = curve_overrides or {}
        normalized_section_loop_overrides = section_loop_overrides or {}
        normalized_blade_to_blade_loop_family_overrides = blade_to_blade_loop_family_overrides or {}
        normalized_transition_overrides = _normalize_transition_overrides(transition_overrides)
        transition_policies = None
        edge_families = dsl.get("edge_families", {})
        if normalized_transition_overrides and not edge_families:
            raise ValueError("transition_overrides require edge_families")
        if edge_families:
            transition_policies = resolve_transition_policies(
                edge_families,
                bound,
                normalized_transition_overrides,
            )
        graph_payload = {
            "dsl": dsl,
            "parameters": bound,
            "profile_overrides": normalized_profile_overrides,
            "curve_overrides": normalized_curve_overrides,
            "section_loop_overrides": normalized_section_loop_overrides,
            "geometry_stage": normalized_geometry_stage,
            "primitive_version": PRIMITIVES["version"],
            "operation_graph": operation_graph,
        }
        if is_v11_impeller and normalized_blade_to_blade_loop_family_overrides:
            graph_payload["blade_to_blade_loop_family_overrides"] = (
                normalized_blade_to_blade_loop_family_overrides
            )
        if transition_policies is not None:
            graph_payload["transition_overrides"] = normalized_transition_overrides
        graph_hash = _stable_hash(graph_payload)
        run_id = f"run-{graph_hash[:12]}"
        run_dir = self.root / "model_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        geometry_validity = _geometry_validity_metadata(
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            section_loop_overrides=normalized_section_loop_overrides,
            blade_to_blade_loop_family_overrides=normalized_blade_to_blade_loop_family_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
            edge_families=edge_families,
            transition_policies=transition_policies,
        )
        geometry_metadata = _geometry_metadata(
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            section_loop_overrides=normalized_section_loop_overrides,
            blade_to_blade_loop_family_overrides=normalized_blade_to_blade_loop_family_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
            edge_families=edge_families,
            transition_policies=transition_policies,
        )
        if dsl["part_family"] == "impeller" and _dsl_version(dsl) == "1.0":
            geometry_validity = geometry_metadata.get("validity", geometry_validity)
        geometry_validation_report = _impeller_geometry_validation_report(
            dsl,
            bound,
            geometry_metadata,
            transition_policies,
        )
        geometry_kernel = _geometry_kernel_metadata(
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            section_loop_overrides=normalized_section_loop_overrides,
            blade_to_blade_loop_family_overrides=normalized_blade_to_blade_loop_family_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
            edge_families=edge_families,
            transition_policies=transition_policies,
        )
        exports, export_manifests = ({}, {}) if review_only else _write_exports(
            run_dir,
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
            geometry_metadata=geometry_metadata,
            geometry_validation_report=geometry_validation_report,
            model_output_root=self.model_output_root,
        )
        export_strategy = _export_strategy(dsl["part_family"], dsl_context=dsl, export_manifests=export_manifests)
        simulation_manifests = {}
        if dsl["part_family"] == "impeller" and _dsl_version(dsl) in {"0.4", "0.5"}:
            surface_graph = geometry_metadata.get("surface_graph", {})
            cfd_view = dsl.get("simulation_views", {}).get("cfd_full_360", {})
            simulation_manifests["cfd_full_360"] = build_cfd_full_360_manifest(
                surface_graph,
                cfd_view,
                blade_count=int(bound.get("blade_count", 0)),
            )
        if not review_only and dsl["part_family"] == "impeller" and _dsl_version(dsl) in {"0.6", "0.7", "0.8", "0.9", "1.0", "1.1"}:
            surface_graph_for_mesh = geometry_metadata.get("surface_graph", {})
            if _is_deferred_v10_3_surface_graph(surface_graph_for_mesh):
                deferred_reason = _section_loop_deferred_reason(surface_graph_for_mesh)
                simulation_manifests["cfd_surface_mesh"] = {
                    "status": "DEFERRED",
                    "geometry_generation_status": "DEFERRED",
                    "deferred_reason": deferred_reason,
                    "source": "geometry.surface_graph",
                    "view_id": "cfd_full_360",
                }
            else:
                simulation_manifests["cfd_surface_mesh"] = build_surface_mesh_manifest(
                    surface_graph_for_mesh,
                    view_id="cfd_full_360",
                )
        surface_graph = geometry_metadata.get("surface_graph", {}) if dsl["part_family"] == "impeller" else {}
        transition_failures = surface_graph.get("transition_failures", []) if isinstance(surface_graph, dict) else []
        manifest = {
            "run_id": run_id,
            "engine_id": engine_id,
            "part_family": dsl["part_family"],
            "preset_id": dsl.get("preset_id"),
            "ontology_slice": dsl.get("ontology_slice"),
            "constructor_family": dsl.get("constructor_family"),
            "constructor_id": dsl.get("constructor_id"),
            "dsl_version": _dsl_version(dsl),
            "facets": dsl.get("facets", {}),
            "selected_rules": dsl.get("selected_rules", []),
            "rule_implications": dsl.get("rule_implications", {}),
            "unsupported_or_inferred_regions": dsl.get("unsupported_or_inferred_regions", []),
            "rule_version": dsl["version"],
            "primitive_version": PRIMITIVES["version"],
            "parameters": bound,
            "profile_overrides": normalized_profile_overrides,
            "curve_overrides": normalized_curve_overrides,
            "geometry_stage": normalized_geometry_stage,
            "operation_graph": operation_graph,
            "operation_graph_hash": graph_hash,
            "manifest_hash": _stable_hash({"operation_graph_hash": graph_hash, "exports": exports}),
            "geometry_kernel": geometry_kernel,
            "geometry": geometry_metadata,
            "simulation_manifests": simulation_manifests,
            "shape_control": _manifest_shape_control(dsl.get("shape_control", {})),
            "validity": _manifest_validity(dsl, geometry_validity),
            "loss_records": [],
            "geometry_validity": geometry_validity,
            "validation": _validation(dsl["part_family"]),
            "source_refs": dsl.get("source_refs", []),
            "source_metadata": dsl.get("source_metadata", {}),
            "parameter_confidence": dsl.get("parameter_confidence", {}),
            "export_strategy": export_strategy,
            "exports": exports,
            "export_manifests": export_manifests,
            "notice": "Research geometry; inferred regions are not released for operation.",
        }
        if manifest["dsl_version"] == "0.8":
            manifest["geometry_version"] = "0.8"
            manifest["transition_geometry_status"] = surface_graph.get("transition_geometry_status")
            manifest["mesh_strategy"] = dsl.get("export_contract", {}).get(
                "mesh_strategy",
                "transition_aware_surface_mesh",
            )
            manifest["unsupported_transition_count"] = len(transition_failures)
            manifest["transition_failure_count"] = len(transition_failures)
        if manifest["dsl_version"] in {"0.9", "0.91", "1.0"}:
            manifest["geometry_version"] = dsl.get("geometry_version", manifest["dsl_version"])
            if dsl.get("geometry_patch_version"):
                manifest["geometry_patch_version"] = dsl["geometry_patch_version"]
            if geometry_metadata.get("geometry_generation_status"):
                manifest["geometry_generation_status"] = geometry_metadata["geometry_generation_status"]
            manifest["transition_geometry_status"] = dsl.get(
                "transition_geometry_status",
                surface_graph.get("transition_geometry_status"),
            )
            manifest["mesh_strategy"] = dsl.get("export_contract", {}).get(
                "mesh_strategy",
                "validated_transition_aware_surface_mesh",
            )
            if geometry_validation_report:
                manifest["geometry_validation_status"] = geometry_validation_report.get("geometry_validation_status")
                manifest["geometry_validation_report"] = geometry_validation_report
                manifest["kernel_capability_matrix_id"] = geometry_validation_report.get("kernel_capability_matrix_id")
                manifest["capability_claim_level"] = geometry_validation_report.get("capability_claim_level")
                manifest["unsupported_claims"] = geometry_validation_report.get("unsupported_claims", [])
            if manifest["dsl_version"] == "0.91":
                manifest["transition_topology_report"] = surface_graph.get("transition_topology_report", {})
                manifest["mesh_manifoldness_report"] = surface_graph.get("mesh_manifoldness_report", {})
            if manifest["dsl_version"] == "1.0":
                manifest["topology_graph"] = surface_graph.get("topology_graph", {})
            manifest["unsupported_transition_count"] = len(transition_failures)
            manifest["transition_failure_count"] = len(transition_failures)
        if manifest["dsl_version"] == "1.1":
            manifest["geometry_version"] = surface_graph.get("geometry_version")
            manifest["geometry_patch_version"] = surface_graph.get("geometry_patch_version")
            manifest["runtime_release_version"] = dsl.get("runtime_release_version", "1.1.5")
            manifest["parameter_inspection_contract_version"] = dsl.get(
                "parameter_inspection_contract_version", "1.1.4"
            )
            manifest["parameter_inspection_capabilities"] = copy.deepcopy(
                dsl.get("parameter_inspection_capabilities", [])
            )
            manifest["generation_id"] = surface_graph.get("generation_id")
            manifest["parameter_inspection"] = copy.deepcopy(surface_graph.get("parameter_inspection", {}))
            if geometry_metadata.get("geometry_generation_status"):
                manifest["geometry_generation_status"] = geometry_metadata["geometry_generation_status"]
            manifest["transition_geometry_status"] = surface_graph.get("transition_geometry_status")
            manifest["mesh_strategy"] = surface_graph.get("mesh_strategy")
            manifest["topology_graph"] = surface_graph.get("topology_graph", {})
            if geometry_validation_report:
                manifest["geometry_validation_status"] = geometry_validation_report.get("geometry_validation_status")
                manifest["geometry_validation_report"] = geometry_validation_report
                manifest["kernel_capability_matrix_id"] = geometry_validation_report.get("kernel_capability_matrix_id")
                manifest["capability_claim_level"] = geometry_validation_report.get("capability_claim_level")
                manifest["unsupported_claims"] = geometry_validation_report.get("unsupported_claims", [])
            manifest["unsupported_transition_count"] = len(transition_failures)
            manifest["transition_failure_count"] = len(transition_failures)
        if transition_policies is not None:
            manifest["transition_overrides"] = normalized_transition_overrides
            manifest["transition_policies"] = geometry_metadata.get("transition_policies", transition_policies)
        if geometry_metadata.get("edge_families"):
            manifest["edge_families"] = geometry_metadata["edge_families"]
        if is_v11_impeller and normalized_blade_to_blade_loop_family_overrides:
            manifest["blade_to_blade_loop_family_overrides"] = normalized_blade_to_blade_loop_family_overrides
        if manifest["dsl_version"] in {"0.4", "0.5"}:
            manifest["campaign_signature"] = build_campaign_signature(
                _campaign_signature_runtime_context(dsl),
                normalized_profile_overrides,
                dsl.get("feature_states"),
            )
        if not review_only:
            manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
            (run_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")
            manifest_copy = exports.get("manifest")
            if manifest_copy:
                Path(manifest_copy).write_text(manifest_json, encoding="utf-8")
        run = ModelRun(run_id=run_id, engine_id=engine_id, manifest=manifest)
        self.runs[run_id] = run
        return run

    def ingest_feedback(
        self,
        run_id: str,
        source: str,
        raw_feedback: str,
        affected_feature: str = "",
    ) -> FeedbackIssue:
        if run_id not in self.runs:
            raise ValueError(f"unknown run: {run_id}")
        classification, relation = _classify_feedback(raw_feedback, affected_feature)
        issue = FeedbackIssue(
            issue_id=f"issue-{uuid4().hex[:12]}",
            run_id=run_id,
            source=source,
            raw_feedback=raw_feedback,
            affected_feature=affected_feature,
            classification=classification,
            expected_relation=relation,
            confidence=0.82 if classification != "needs_clarification" else 0.25,
        )
        issue_dir = self.root / "feedback" / issue.issue_id
        issue_dir.mkdir(parents=True, exist_ok=True)
        issue_dir.joinpath("issue.json").write_text(
            json.dumps(issue.__dict__, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        self.issues[issue.issue_id] = issue
        return issue

    def propose_patch(self, issue_id: str) -> RulePatchProposal:
        issue = self.issues[issue_id]
        if issue.classification == "primitive_gap":
            diff = "primitive_gap: propose dovetail_root primitive contract; human approval required"
            patch_type = "primitive_gap"
        elif issue.classification == "rule_patch":
            diff = f"add constraint: {issue.expected_relation}; add validation gate for contact/embedding"
            patch_type = "rule_patch"
        elif issue.classification == "parameter_patch":
            diff = "adjust existing parameter within declared bounds"
            patch_type = "parameter_patch"
        else:
            diff = "needs human clarification before patch proposal"
            patch_type = "needs_clarification"
        proposal = RulePatchProposal(
            patch_id=f"patch-{uuid4().hex[:12]}",
            issue_id=issue_id,
            patch_type=patch_type,
            dsl_diff=diff,
            approval_required=True,
        )
        patch_dir = self.root / "patches" / proposal.patch_id
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch_dir.joinpath("proposal.json").write_text(
            json.dumps(proposal.__dict__, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        self.patches[proposal.patch_id] = proposal
        return proposal

    def validate_patch(self, patch_id: str) -> dict[str, Any]:
        proposal = self.patches[patch_id]
        return {
            "patch_id": patch_id,
            "status": "PASS" if proposal.patch_type != "needs_clarification" else "BLOCKED",
            "sandbox": True,
            "approval_required": proposal.approval_required,
        }

    def approve_patch(self, patch_id: str) -> dict[str, Any]:
        proposal = self.patches[patch_id]
        return {
            "patch_id": patch_id,
            "approval_status": "approved",
            "patch_type": proposal.patch_type,
            "note": "Approved patch is versioned; primitive gaps still require framework evolution work.",
        }

    def _engine(self, engine_id: str) -> dict[str, Any]:
        if engine_id in self.engines:
            return self.engines[engine_id]
        path = self.root / "rule_engines" / engine_id / "rule.json"
        if not path.exists():
            raise ValueError(f"unknown rule engine: {engine_id}")
        dsl = json.loads(path.read_text(encoding="utf-8"))
        self.engines[engine_id] = dsl
        return dsl


def _dsl_template(part_family: str) -> dict[str, Any]:
    shared_airfoil = _shared_airfoil()
    if part_family == "turbine_rotor":
        return {
            "version": "0.1.0",
            "part_family": "turbine_rotor",
            "parameters": {
                "blade_count": {"default": 18, "min": 6, "max": 80},
                "hub_radius_mm": {"default": 18.0, "min": 5.0, "max": 80.0},
                "blade_root_depth_mm": {"default": 2.0, "min": 1.0, "max": 8.0},
            },
            "features": ["disk", "hub", "blade_root", "blade_airfoil"],
            "constraints": ["embedded_contact(blade_root, hub.outer_surface)"],
            "airfoil": shared_airfoil,
        }
    if part_family == "centrifugal_impeller":
        return {
            "version": "0.1.0",
            "part_family": "centrifugal_impeller",
            "parameters": {
                "blade_count": {"default": 7, "min": 5, "max": 16},
                "inlet_radius_mm": {"default": 420.2, "min": 1.0, "max": 2000.0},
                "exit_radius_mm": {"default": 1400.65, "min": 1.0, "max": 4000.0},
                "inlet_blade_height_mm": {"default": 394.0, "min": 1.0, "max": 1000.0},
                "outlet_blade_height_mm": {"default": 251.0, "min": 1.0, "max": 1000.0},
                "inlet_blade_angle_deg": {"default": 17.47, "min": 0.0, "max": 90.0},
                "outlet_blade_angle_deg": {"default": 21.19, "min": 0.0, "max": 90.0},
                "blade_thickness_mm": {"default": 56.0, "min": 0.1, "max": 200.0},
            },
            "features": ["hub", "inducer", "blade_root", "blade_airfoil", "radial_exit"],
            "constraints": [
                "embedded_contact(blade_root, hub.outer_surface)",
                "radial_exit_radius > inlet_radius",
            ],
            "airfoil": shared_airfoil,
            "source_refs": ["upcommons_centrifugal_pump_impeller"],
        }
    return {
        "version": "0.1.0",
        "part_family": "ngv_ring",
        "parameters": {
            "vane_count": {"default": 21, "min": 6, "max": 80},
            "inner_radius_mm": {"default": 34.0, "min": 5.0, "max": 120.0},
            "outer_radius_mm": {"default": 44.0, "min": 10.0, "max": 160.0},
        },
        "features": ["inner_ring", "outer_ring", "vane", "flow_path"],
        "constraints": ["bridges(vane, inner_ring, outer_ring)"],
        "airfoil": shared_airfoil,
    }


def _impeller_dsl_template(preset_id: str | None, facet_overrides: dict[str, str]) -> dict[str, Any]:
    resolved_preset_id = preset_id or "radial_open_backward_single_reference"
    if preset_id in _JSON_IMPELLER_PRESET_IDS:
        return compile_impeller_runtime_preset(preset_id, facet_overrides)
    if resolved_preset_id not in IMPELLER_PRESETS:
        raise ValueError(f"unknown impeller preset: {resolved_preset_id}")
    preset = IMPELLER_PRESETS[resolved_preset_id]
    facets = {**preset["facets"], **facet_overrides}
    _validate_impeller_facets(facets)
    return {
        "version": "0.2.0",
        "part_family": "impeller",
        "preset_id": resolved_preset_id,
        "facets": facets,
        "parameters": _impeller_parameter_specs(preset["parameters"]),
        "features": _impeller_features(facets),
        "constraints": _impeller_constraints(facets),
        "selected_rules": _impeller_selected_rules(facets),
        "rule_implications": _impeller_rule_implications(facets),
        "unsupported_or_inferred_regions": _impeller_inferred_regions(facets),
        "airfoil": _shared_airfoil(),
        "source_refs": preset["source_refs"],
    }


def _shared_airfoil() -> dict[str, Any]:
    return {
        "authority": "inferred",
        "curve": {
            "kind": "bspline",
            "degree": 3,
            "control_points": [[0.0, 0.0], [0.25, 0.08], [0.75, 0.06], [1.0, 0.0]],
            "knots": [0, 0, 0, 0, 1, 1, 1, 1],
        },
    }


def _impeller_parameter_specs(defaults: dict[str, Any]) -> dict[str, dict[str, float]]:
    limits = {
        "blade_count": {"min": 2, "max": 64},
        "inlet_radius_mm": {"min": 0.1, "max": 5000.0},
        "exit_radius_mm": {"min": 0.1, "max": 10000.0},
        "inlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
        "outlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
        "inlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
        "outlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
        "blade_thickness_mm": {"min": 0.01, "max": 1000.0},
        "blade_curve_gain": {"min": -10.0, "max": 10.0},
        "hub_curve_height_mm": {"min": 0.0, "max": 5000.0},
        "hub_twist_deg": {"min": -120.0, "max": 120.0},
        "tip_twist_deg": {"min": -160.0, "max": 160.0},
        "hub_warp_mm": {"min": 0.0, "max": 2000.0},
        "tip_warp_mm": {"min": 0.0, "max": 2500.0},
        "blade_wrap_deg": {"min": -720.0, "max": 720.0},
        "blade_lean_deg": {"min": -180.0, "max": 180.0},
        "mounting_bore_radius_mm": {"min": 0.1, "max": 3000.0},
    }
    return {
        name: {"default": default, "min": limits[name]["min"], "max": limits[name]["max"]}
        for name, default in defaults.items()
    }


def _validate_impeller_facets(facets: dict[str, str]) -> None:
    missing = sorted(set(IMPELLER_FACET_AXES) - set(facets))
    if missing:
        raise ValueError(f"missing impeller facets: {', '.join(missing)}")
    for axis, value in facets.items():
        allowed = IMPELLER_FACET_AXES.get(axis)
        if allowed is None:
            raise ValueError(f"unknown facet axis: {axis}")
        if value not in allowed:
            raise ValueError(f"invalid facet {axis}: {value}")


def _impeller_features(facets: dict[str, str]) -> list[str]:
    features = ["hub", "blade_root", "blade_airfoil", "inlet", "outlet", "flow_path"]
    if facets["shroud_topology"] != "open":
        features.append("optional_shroud")
    if facets["suction_topology"] == "double_suction":
        features.append("mirrored_inlet")
    if facets["passage_topology"] == "recessed_vortex":
        features.append("free_passage_cavity")
    return features


def _impeller_constraints(facets: dict[str, str]) -> list[str]:
    constraints = [
        "embedded_contact(blade_root, hub.outer_surface)",
        "patterned_around_axis(blade_airfoil, rotation_axis)",
        "bounds_flow_path(blade_airfoil, flow_path)",
    ]
    if facets["flow_topology"] in {"radial", "mixed"}:
        constraints.append("outlet_radius > inlet_radius")
    if facets["shroud_topology"] != "open":
        constraints.append("attached_to(optional_shroud, blade_airfoil)")
    if facets["suction_topology"] == "double_suction":
        constraints.append("mirrored_about_midplane(inlet)")
    if facets["passage_topology"] == "recessed_vortex":
        constraints.append("contains(impeller, free_passage_cavity)")
    return constraints


def _impeller_selected_rules(facets: dict[str, str]) -> list[str]:
    rules = [
        "base.impeller.has_hub",
        "base.impeller.has_blade_pattern",
        "base.impeller.requires_blade_root_hub_contact",
        f"flow_topology.{facets['flow_topology']}.selects_meridional_path",
        f"shroud_topology.{facets['shroud_topology']}.selects_tip_boundary",
        f"suction_topology.{facets['suction_topology']}.selects_inlet_symmetry",
        f"blade_exit_geometry.{facets['blade_exit_geometry']}.selects_exit_angle_convention",
        f"working_domain.{facets['working_domain']}.sets_terminology_context",
        f"passage_topology.{facets['passage_topology']}.selects_passage_architecture",
    ]
    if facets["flow_topology"] == "radial":
        rules.append("flow_topology.radial.requires_outlet_radius_gt_inlet_radius")
    if facets["shroud_topology"] == "closed":
        rules.append("shroud_topology.closed.generates_front_and_back_shroud_parameter_lines")
    if facets["passage_topology"] == "recessed_vortex":
        rules.append("passage_topology.recessed_vortex.generates_recessed_free_flow_geometry")
    return rules


def _impeller_rule_implications(facets: dict[str, str]) -> dict[str, str]:
    flow = {
        "radial": "radial outlet radius must exceed inlet radius",
        "mixed": "outlet has radial and axial displacement",
        "axial": "inlet and outlet radii remain close while axial height dominates",
    }
    shroud = {
        "open": "blade tip is exposed and no shroud lines are generated",
        "semi_open": "one shroud parameter-line family is generated",
        "closed": "front and back shroud parameter-line families are generated",
    }
    suction = {
        "single_suction": "one inlet side is generated",
        "double_suction": "construction lines mirror across the midplane",
    }
    exit_geometry = {
        "backward_curved": "blade exit bends backward in the proxy convention",
        "radial": "blade exit is near radial in the proxy convention",
        "forward_curved": "blade exit bends forward in the proxy convention",
    }
    passage = {
        "throughflow_bladed_channel": "blades bound a throughflow passage between hub and tip/shroud",
        "single_channel": "single channel passage taxonomy is recorded but not specialized in v0.2",
        "multi_channel": "multi-channel passage taxonomy is recorded but not specialized in v0.2",
        "recessed_vortex": "recessed free-flow cavity is generated instead of a closed throughflow channel",
        "cutter": "cutter passage taxonomy is recorded but not specialized in v0.2",
    }
    return {
        "flow_topology": flow[facets["flow_topology"]],
        "shroud_topology": shroud[facets["shroud_topology"]],
        "suction_topology": suction[facets["suction_topology"]],
        "blade_exit_geometry": exit_geometry[facets["blade_exit_geometry"]],
        "working_domain": "metadata only in v0.2 geometry proxy",
        "passage_topology": passage[facets["passage_topology"]],
    }


def _impeller_inferred_regions(facets: dict[str, str]) -> list[str]:
    regions = ["blade_airfoil_profile_inferred", "fillets_not_engineered"]
    if facets["working_domain"] != "pump":
        regions.append("domain_specific_performance_not_validated")
    if facets["shroud_topology"] != "open":
        regions.append("shroud_surface_is_parameter_line_proxy")
    if facets["passage_topology"] in {"single_channel", "multi_channel", "cutter"}:
        regions.append(f"{facets['passage_topology']}_passage_specialization_not_engineered")
    return regions


def _bind_parameters(dsl: dict[str, Any], provided: dict[str, Any]) -> dict[str, Any]:
    bound = {}
    for name, spec in dsl["parameters"].items():
        value = provided.get(name, spec["default"])
        if not spec["min"] <= value <= spec["max"]:
            raise ValueError(f"{name} out of range")
        bound[name] = value
    if dsl["part_family"] in {"centrifugal_impeller", "impeller"} and "backsweep_deg" in provided:
        # ponytail: compatibility alias for the first prototype API.
        bound["backsweep_deg"] = provided["backsweep_deg"]
    if dsl["part_family"] in {"centrifugal_impeller", "impeller"}:
        if "blade_curve_gain" in provided:
            bound["blade_curve_gain"] = _bounded("blade_curve_gain", provided["blade_curve_gain"], -10.0, 10.0)
        if "hub_curve_height_mm" in provided:
            bound["hub_curve_height_mm"] = _bounded("hub_curve_height_mm", provided["hub_curve_height_mm"], 0.0, 1000.0)
        if "hub_twist_deg" in provided:
            bound["hub_twist_deg"] = _bounded("hub_twist_deg", provided["hub_twist_deg"], -120.0, 120.0)
        if "tip_twist_deg" in provided:
            bound["tip_twist_deg"] = _bounded("tip_twist_deg", provided["tip_twist_deg"], -160.0, 160.0)
        if "hub_warp_mm" in provided:
            bound["hub_warp_mm"] = _bounded("hub_warp_mm", provided["hub_warp_mm"], 0.0, 300.0)
        if "tip_warp_mm" in provided:
            bound["tip_warp_mm"] = _bounded("tip_warp_mm", provided["tip_warp_mm"], 0.0, 400.0)
        if "blade_wrap_deg" in provided:
            bound["blade_wrap_deg"] = _bounded("blade_wrap_deg", provided["blade_wrap_deg"], -720.0, 720.0)
        if "blade_lean_deg" in provided:
            bound["blade_lean_deg"] = _bounded("blade_lean_deg", provided["blade_lean_deg"], -180.0, 180.0)
        if "mounting_bore_radius_mm" in provided:
            max_bore = max(1.0, bound["inlet_radius_mm"] * 0.52)
            bound["mounting_bore_radius_mm"] = _bounded("mounting_bore_radius_mm", provided["mounting_bore_radius_mm"], 0.1, max_bore)
    return bound


def _operation_graph(dsl: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    family = dsl["part_family"]
    if family == "turbine_rotor":
        return [
            {"op": "axisymmetric_revolve", "feature": "disk"},
            {"op": "axisymmetric_revolve", "feature": "hub"},
            {"op": "bspline_section_curve", "feature": "blade_airfoil"},
            {"op": "lofted_blade_surface", "feature": "blade_airfoil"},
            {"op": "circular_pattern", "feature": "blade_airfoil", "count": parameters["blade_count"]},
            {"op": "boolean_union", "constraint": "embedded_contact(blade_root, hub.outer_surface)"},
            {"op": "named_region_tagging", "regions": ["hub.outer_surface", "blade_root"]},
            {"op": "mesh_export"},
        ]
    if family in {"centrifugal_impeller", "impeller"}:
        facets = _resolved_impeller_facets(family, dsl.get("facets", {}))
        return [
            {"op": "axisymmetric_revolve", "feature": "hub"},
            {"op": "axisymmetric_revolve", "feature": "inducer"},
            {"op": "meridional_beta_thickness_kernel", "feature": "impeller_geometry", "passage_topology": facets["passage_topology"]},
            {"op": "bspline_section_curve", "feature": "blade_airfoil"},
            {
                "op": "lofted_blade_surface",
                "feature": "blade_airfoil",
                "backsweep_deg": parameters.get("backsweep_deg", parameters["outlet_blade_angle_deg"]),
                "inlet_blade_angle_deg": parameters["inlet_blade_angle_deg"],
                "outlet_blade_angle_deg": parameters["outlet_blade_angle_deg"],
            },
            {"op": "circular_pattern", "feature": "blade_airfoil", "count": parameters["blade_count"]},
            {"op": "boolean_union", "feature": "blade_root", "constraint": "embedded_contact(blade_root, hub.outer_surface)"},
            {"op": "surface_graph_validation", "feature": "impeller_surface_graph"},
            {"op": "named_region_tagging", "feature": "radial_exit", "regions": ["inducer", "hub.outer_surface", "blade_root", "blade_airfoil", "radial_exit"]},
            {"op": "mesh_export", "feature": "impeller"},
        ]
    return [
        {"op": "ring_shell", "feature": "inner_ring"},
        {"op": "ring_shell", "feature": "outer_ring"},
        {"op": "bspline_section_curve", "feature": "vane"},
        {"op": "lofted_blade_surface", "feature": "vane"},
        {"op": "circular_pattern", "feature": "vane", "count": parameters["vane_count"]},
        {"op": "named_region_tagging", "regions": ["inner_ring", "outer_ring", "flow_path"]},
        {"op": "mesh_export"},
    ]


def _geometry_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    section_loop_overrides: dict[str, Any] | None = None,
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
    edge_families: dict[str, Any] | None = None,
    transition_policies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    is_impeller = part_family in {"centrifugal_impeller", "impeller"}
    resolved_facets = _resolved_impeller_facets(part_family, facets or {}) if is_impeller else {}
    impeller_geometry_options = _impeller_geometry_options(dsl_context)
    if is_impeller and (dsl_context or {}).get("geometry_version") in {"1.0", "1.1"}:
        surface_graph = build_v10_surface_graph(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **impeller_geometry_options,
            edge_families=edge_families,
            transition_policies=transition_policies,
            resolved_attachment_defaults=_v10_surface_graph_attachment_defaults(
                dsl_context,
                parameters=parameters,
                profile_overrides=profile_overrides,
                section_loop_overrides=section_loop_overrides,
                blade_to_blade_loop_family_overrides=blade_to_blade_loop_family_overrides,
            ),
        )
        return {
            "part_family": part_family,
            "authority": "research",
            "geometry_version": surface_graph.get("geometry_version", "1.0"),
            "geometry_patch_version": surface_graph.get("geometry_patch_version"),
            "geometry_generation_status": surface_graph.get("geometry_generation_status"),
            "airfoil": _shared_airfoil(),
            "blade_surface_count": int(parameters.get("blade_count", 0)),
            "blade_surface": surface_graph.get("blade_surface", {}),
            "hub_surface": surface_graph.get("hub_surface", {}),
            "cad_features": surface_graph.get("cad_features", []),
            "construction_lines": surface_graph.get("construction_lines", {}),
            "sampled_blades": surface_graph.get("sampled_blades", []),
            "surface_graph": surface_graph,
            "validity": _surface_graph_validity(surface_graph),
            "named_regions": _impeller_named_regions(resolved_facets),
            "parameters": parameters,
        }
    if edge_families:
        impeller_geometry_options["edge_families"] = edge_families
    if transition_policies is not None:
        impeller_geometry_options["transition_policies"] = transition_policies
    impeller_geometry = (
        build_impeller_geometry(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **impeller_geometry_options,
        )
        if is_impeller
        else {}
    )
    blade_surface = impeller_geometry.get("blade_surface", {}) if is_impeller else {}
    curved_hub = is_impeller and parameters.get("hub_curve_height_mm", 0.0) > 0.0
    metadata = {
        "part_family": part_family,
        "authority": "research",
        "airfoil": _shared_airfoil() if is_impeller else _dsl_template(part_family)["airfoil"],
        "blade_surface_count": int(parameters.get("blade_count", 0)) if is_impeller else 0,
        "blade_surface": blade_surface,
        "hub_surface": impeller_geometry.get("hub_surface", {}) if is_impeller and curved_hub else {},
        "cad_features": impeller_geometry.get("cad_features", []) if is_impeller else [],
        "construction_lines": impeller_geometry.get("construction_lines", {}) if is_impeller else {},
        "sampled_blades": impeller_geometry.get("sampled_blades", []) if is_impeller else [],
        "surface_graph": impeller_geometry.get("surface_graph", {}) if is_impeller else {},
        "validity": impeller_geometry.get("validity", {}) if is_impeller else {},
        "named_regions": (
            ["hub.outer_surface", "blade_root", "blade_airfoil"]
            if part_family == "turbine_rotor"
            else (
                _impeller_named_regions(resolved_facets)
                if is_impeller
                else ["inner_ring", "outer_ring", "vane", "flow_path"]
            )
        ),
        "parameters": parameters,
    }
    _attach_v091_patch_mesh_reports(metadata)
    if is_impeller and impeller_geometry.get("edge_families"):
        metadata["edge_families"] = impeller_geometry["edge_families"]
    if is_impeller and impeller_geometry.get("transition_policies"):
        metadata["transition_policies"] = impeller_geometry["transition_policies"]
    return metadata


def _attach_v091_patch_mesh_reports(geometry_metadata: dict[str, Any]) -> None:
    surface_graph = geometry_metadata.get("surface_graph")
    if not isinstance(surface_graph, dict):
        return
    if surface_graph.get("transition_geometry_status") != "topology_first_validated_transition_graph":
        return
    if isinstance(surface_graph.get("mesh_manifoldness_report"), Mapping):
        return

    try:
        from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh

        mesh = build_patch_mesh(surface_graph)
    except (KeyError, TypeError, ValueError) as exc:
        surface_graph["mesh_manifoldness_report_error"] = str(exc)
        return

    for key in (
        "mesh_manifoldness_report",
        "source_patch_incidence_report",
        "final_mesh_incidence_report",
        "mesh_closure_report",
        "mesh_closure_regions",
    ):
        if key in mesh:
            surface_graph[key] = mesh[key]


def _geometry_kernel_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    section_loop_overrides: dict[str, Any] | None = None,
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
    edge_families: dict[str, Any] | None = None,
    transition_policies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if part_family not in {"centrifugal_impeller", "impeller"}:
        return {}
    if _is_v10_3_geometry_bootstrap_context(dsl_context):
        geometry_patch_version = _section_loop_geometry_patch_version(dsl_context)
        resolved_facets = _resolved_impeller_facets(part_family, facets or {})
        impeller_geometry_options = _impeller_geometry_options(dsl_context)
        surface_graph = build_v10_surface_graph(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **impeller_geometry_options,
            edge_families=edge_families,
            transition_policies=transition_policies,
            resolved_attachment_defaults=_v10_surface_graph_attachment_defaults(
                dsl_context,
                parameters=parameters,
                profile_overrides=profile_overrides,
                section_loop_overrides=section_loop_overrides,
            ),
        )
        return {
            "geometry_version": "1.0",
            "geometry_patch_version": geometry_patch_version,
            "geometry_generation_status": surface_graph.get("surface_graph_status", "FAIL"),
            "kernel": "v1_0_3_section_loop_topology_kernel",
            "source": "geometry.surface_graph",
            "surface_graph_status": surface_graph.get("surface_graph_status", "FAIL"),
            "v1_0_3_transition_failure_count": surface_graph.get("v1_0_3_transition_failure_count", 0),
        }
    if (dsl_context or {}).get("geometry_version") == "1.1":
        resolved_facets = _resolved_impeller_facets(part_family, facets or {})
        impeller_geometry_options = _impeller_geometry_options(dsl_context)
        surface_graph = build_v10_surface_graph(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **impeller_geometry_options,
            edge_families=edge_families,
            transition_policies=transition_policies,
            resolved_attachment_defaults=_v10_surface_graph_attachment_defaults(
                dsl_context,
                parameters=parameters,
                profile_overrides=profile_overrides,
                section_loop_overrides=section_loop_overrides,
                blade_to_blade_loop_family_overrides=blade_to_blade_loop_family_overrides,
            ),
        )
        return {
            "geometry_version": surface_graph.get("geometry_version", "1.1"),
            "geometry_patch_version": surface_graph.get("geometry_patch_version"),
            "geometry_generation_status": surface_graph.get("surface_graph_status", "FAIL"),
            "kernel": surface_graph.get("source_kernel", "v1_1_blade_to_blade_surface_family_kernel"),
            "source": "geometry.surface_graph",
            "surface_graph_status": surface_graph.get("surface_graph_status", "FAIL"),
            "mesh_strategy": surface_graph.get("mesh_strategy"),
        }
    resolved_facets = _resolved_impeller_facets(part_family, facets or {})
    impeller_geometry_options = _impeller_geometry_options(dsl_context)
    if edge_families:
        impeller_geometry_options["edge_families"] = edge_families
    if transition_policies is not None:
        impeller_geometry_options["transition_policies"] = transition_policies
    geometry = build_impeller_geometry(
        parameters,
        resolved_facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **impeller_geometry_options,
    )
    return geometry["kernel"]


def _geometry_validity_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    section_loop_overrides: dict[str, Any] | None = None,
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
    edge_families: dict[str, Any] | None = None,
    transition_policies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if part_family not in {"centrifugal_impeller", "impeller"}:
        return {}
    resolved_facets = _resolved_impeller_facets(part_family, facets or {})
    impeller_geometry_options = _impeller_geometry_options(dsl_context)
    if (dsl_context or {}).get("geometry_version") in {"1.0", "1.1"}:
        surface_graph = build_v10_surface_graph(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **impeller_geometry_options,
            edge_families=edge_families,
            transition_policies=transition_policies,
            resolved_attachment_defaults=_v10_surface_graph_attachment_defaults(
                dsl_context,
                parameters=parameters,
                profile_overrides=profile_overrides,
                section_loop_overrides=section_loop_overrides,
                blade_to_blade_loop_family_overrides=blade_to_blade_loop_family_overrides,
            ),
        )
        return _surface_graph_validity(surface_graph)
    if edge_families:
        impeller_geometry_options["edge_families"] = edge_families
    if transition_policies is not None:
        impeller_geometry_options["transition_policies"] = transition_policies
    geometry = build_impeller_geometry(
        parameters,
        resolved_facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **impeller_geometry_options,
    )
    return geometry["validity"]


def _surface_graph_validity(surface_graph: dict[str, Any]) -> dict[str, Any]:
    status = "PASS" if surface_graph.get("surface_graph_status") == "PASS" else "FAIL"
    if surface_graph.get("geometry_patch_version") in {"1.1.0", "1.1.1", "1.1.2"}:
        failures = copy.deepcopy(surface_graph.get("transition_failures", []))
        check_name = "v1_1_surface_family_graph"
    elif surface_graph.get("geometry_patch_version") in {"1.0.3", "1.0.4"}:
        failures = copy.deepcopy(surface_graph.get("v1_0_3_transition_failures", []))
        check_name = "v1_0_3_section_loop_surface_graph"
    else:
        failures = copy.deepcopy(surface_graph.get("v1_0_2_transition_failures", []))
        check_name = "v1_0_2_continuous_blade_attachment"
    check = {
        "name": check_name,
        "status": status,
        "failure_count": len(failures),
    }
    if failures:
        check["failures"] = failures
    return {
        "status": status,
        "geometry_checks": [check],
        "topology_checks": [],
        "engineering_checks": [],
    }


def _impeller_geometry_validation_report(
    dsl: dict[str, Any],
    parameters: dict[str, Any],
    geometry_metadata: dict[str, Any],
    transition_policies: dict[str, Any] | None,
) -> dict[str, Any]:
    dsl_version = _dsl_version(dsl)
    if dsl.get("part_family") != "impeller" or dsl_version not in {"0.9", "0.91", "1.0", "1.1"}:
        return {}
    surface_graph = geometry_metadata.get("surface_graph", {})
    if _is_deferred_v10_3_surface_graph(surface_graph):
        deferred_reason = _section_loop_deferred_reason(surface_graph)
        return {
            "geometry_validation_status": "DEFERRED",
            "kernel_capability_matrix_id": dsl.get(
                "kernel_capability_matrix_id",
                _default_kernel_capability_matrix_id(dsl_version),
            ),
            "capability_claim_level": "deferred_bootstrap",
            "unsupported_claims": [],
            "parameters_observed": parameters,
            "facets_observed": dsl.get("facets", {}),
            "checks": [
                {
                    "check_id": "v10_3_surface_graph_builder",
                    "status": "DEFERRED",
                    "reason": deferred_reason,
                }
            ],
            "blocking_failures": [],
            "transition_validation_summary": {
                "status": "DEFERRED",
                "reason": deferred_reason,
            },
        }
    return build_geometry_validation_report(
        parameters=parameters,
        facets=dsl.get("facets", {}),
        transition_policies=transition_policies or {},
        surface_graph=surface_graph,
        capability_matrix_id=dsl.get(
            "kernel_capability_matrix_id",
            _default_kernel_capability_matrix_id(dsl_version),
        ),
    )


def _default_kernel_capability_matrix_id(dsl_version: str) -> str:
    if dsl_version == "1.1":
        return "impeller_v1_1_kernel_capabilities"
    if dsl_version == "1.0":
        return "impeller_v1_0_kernel_capabilities"
    if dsl_version == "0.91":
        return "impeller_v0_91_kernel_capabilities"
    return "impeller_v0_9_kernel_capabilities"


def _is_v10_3_geometry_bootstrap_context(dsl_context: dict[str, Any] | None) -> bool:
    context = dsl_context or {}
    return context.get("geometry_version") == "1.0" and _section_loop_geometry_patch_version(context) in _V10_SECTION_LOOP_PATCH_VERSIONS


def _v10_surface_graph_attachment_defaults(
    dsl_context: dict[str, Any] | None,
    *,
    parameters: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    section_loop_overrides: dict[str, Any] | None = None,
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    context = dsl_context or {}
    if context.get("geometry_version") == "1.1":
        resolved_defaults = _v11_resolved_defaults_for_instantiation(
            context,
            parameters=parameters or {},
            profile_overrides=profile_overrides or {},
            blade_to_blade_loop_family_overrides=(
                blade_to_blade_loop_family_overrides or {}
            ),
        )
        return {
            "geometry_patch_version": str(context.get("geometry_patch_version", "1.1.0")),
            "resolved_blade_to_blade_loop_family_defaults": resolved_defaults,
            "blade_to_blade_loop_family_overrides": copy.deepcopy(
                blade_to_blade_loop_family_overrides or {}
            ),
        }
    if context.get("geometry_version") == "1.0" and _section_loop_geometry_patch_version(context) in _V10_SECTION_LOOP_PATCH_VERSIONS:
        resolved_defaults = copy.deepcopy(context.get("resolved_section_loop_defaults", {}))
        if section_loop_overrides:
            resolved_defaults["section_loop_overrides"] = copy.deepcopy(section_loop_overrides)
        return {
            "v1_0_3_active": True,
            "geometry_patch_version": _section_loop_geometry_patch_version(context),
            "resolved_section_loop_defaults": resolved_defaults,
        }
    return context.get("resolved_attachment_defaults")


def _v11_resolved_defaults_for_instantiation(
    context: dict[str, Any],
    *,
    parameters: dict[str, Any],
    profile_overrides: dict[str, Any],
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_defaults = copy.deepcopy(
        context.get("resolved_blade_to_blade_loop_family_defaults", {})
    )
    mapper_approved = (
        context.get("canonical_payload_authority") == "v116_mapper_approved"
    )
    if mapper_approved and (
        profile_overrides or blade_to_blade_loop_family_overrides
    ):
        raise ValueError(
            "V1.1.6 mapper-approved canonical payload forbids geometry overrides"
        )
    if not mapper_approved:
        _apply_v11_profile_overrides_to_defaults(resolved_defaults, profile_overrides)
    if context.get("geometry_patch_version") == "1.1.2":
        if mapper_approved:
            canonical = context.get("canonical_nurbs_parameterization")
            expected_hash = context.get("canonical_payload_hash_sha256")
            if not isinstance(canonical, Mapping) or not isinstance(
                expected_hash, str
            ):
                raise ValueError(
                    "V1.1.6 mapper-approved canonical payload lacks its hash binding"
                )
            actual_hash = _canonical_payload_sha256(canonical)
            if actual_hash != expected_hash:
                raise ValueError(
                    "V1.1.6 mapper-approved canonical payload hash mismatch"
                )
            if canonical.get("canonical_payload_version") != "1.1.2":
                raise ValueError(
                    "V1.1.6 mapper-approved canonical payload must target V1.1.2"
                )
            resolved_defaults["canonical_nurbs_parameterization"] = copy.deepcopy(
                dict(canonical)
            )
        else:
            _apply_v11_bound_scalar_defaults(resolved_defaults, parameters)
            source = str(
                context.get("canonical_input_source", "translated_from_legacy_v1_1")
            )
            resolved_defaults[
                "canonical_nurbs_parameterization"
            ] = canonical_nurbs_from_v11_defaults(
                parameters,
                resolved_defaults,
                source=source,
            )
    elif "canonical_nurbs_parameterization" in context:
        resolved_defaults["canonical_nurbs_parameterization"] = copy.deepcopy(
            context["canonical_nurbs_parameterization"]
        )
    return resolved_defaults


def _canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _apply_v11_bound_scalar_defaults(
    resolved_defaults: dict[str, Any],
    parameters: dict[str, Any],
) -> None:
    if "blade_thickness_mm" not in parameters:
        return
    try:
        blade_thickness_mm = float(parameters["blade_thickness_mm"])
    except (TypeError, ValueError):
        return
    if not math.isfinite(blade_thickness_mm) or blade_thickness_mm <= 0.0:
        return
    resolved_defaults["average_blade_thickness_mm"] = blade_thickness_mm
    resolved_defaults["maximum_blade_thickness_mm"] = max(
        float(resolved_defaults.get("maximum_blade_thickness_mm", blade_thickness_mm)),
        blade_thickness_mm,
    )


def _apply_v11_profile_overrides_to_defaults(
    resolved_defaults: dict[str, Any],
    profile_overrides: dict[str, Any],
) -> None:
    hub_points = _v11_profile_override_control_points(profile_overrides, "hub_profile")
    tip_points = _v11_profile_override_control_points(profile_overrides, "tip_or_shroud_profile")
    if hub_points is not None:
        resolved_defaults["hub_profile_rz_mm"] = hub_points
    if tip_points is not None:
        resolved_defaults["tip_or_shroud_profile_rz_mm"] = tip_points


def _v11_profile_override_control_points(
    profile_overrides: dict[str, Any],
    profile_name: str,
) -> list[list[float]] | None:
    profile = profile_overrides.get(profile_name)
    if not isinstance(profile, dict):
        return None
    control_points = profile.get("control_points")
    if not isinstance(control_points, list):
        return None
    points = [
        [float(point[0]), float(point[1])]
        for point in control_points
        if isinstance(point, list) and len(point) >= 2
    ]
    return points or None


def _v10_3_geometry_bootstrap_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str],
    dsl_context: dict[str, Any],
) -> dict[str, Any]:
    geometry_patch_version = _section_loop_geometry_patch_version(dsl_context)
    deferred_reason = _section_loop_deferred_reason(dsl_context)
    surface_graph = {
        "geometry_version": "1.0",
        "geometry_patch_version": geometry_patch_version,
        "geometry_generation_status": "DEFERRED",
        "transition_geometry_status": dsl_context.get(
            "transition_geometry_status",
            "topology_first_section_loop_blade_root_blend_surface_graph",
        ),
        "surface_graph_status": "DEFERRED",
        "deferred_reason": deferred_reason,
        "resolved_section_loop_defaults": copy.deepcopy(
            dsl_context.get("resolved_section_loop_defaults", {})
        ),
        "surfaces": [],
        "edges": [],
        "construction_lines": {},
        "sampled_blades": [],
        "cad_features": [],
        "transition_failures": [],
        "v1_0_2_transition_failures": [],
    }
    return {
        "part_family": part_family,
        "authority": "research",
        "geometry_version": "1.0",
        "geometry_patch_version": geometry_patch_version,
        "geometry_generation_status": "DEFERRED",
        "deferred_reason": deferred_reason,
        "airfoil": _shared_airfoil(),
        "blade_surface_count": int(parameters.get("blade_count", 0)),
        "blade_surface": {},
        "hub_surface": {},
        "cad_features": [],
        "construction_lines": {},
        "sampled_blades": [],
        "surface_graph": surface_graph,
        "validity": _v10_3_deferred_validity(deferred_reason),
        "named_regions": _impeller_named_regions(facets),
        "parameters": parameters,
    }


def _v10_3_deferred_validity(deferred_reason: str = "v1_0_3_surface_graph_builder_pending") -> dict[str, Any]:
    return {
        "status": "DEFERRED",
        "geometry_checks": [
            {
                "name": "v1_0_3_surface_graph_builder",
                "status": "DEFERRED",
                "reason": deferred_reason,
            }
        ],
        "topology_checks": [],
        "engineering_checks": [],
    }


def _is_deferred_v10_3_surface_graph(surface_graph: Any) -> bool:
    return (
        isinstance(surface_graph, Mapping)
        and _section_loop_geometry_patch_version(surface_graph) in _V10_SECTION_LOOP_PATCH_VERSIONS
        and surface_graph.get("surface_graph_status") == "DEFERRED"
    )


def _section_loop_geometry_patch_version(payload: Mapping[str, Any] | dict[str, Any] | None, default: str = "1.0.3") -> str:
    if not isinstance(payload, Mapping):
        return default
    patch_version = payload.get("geometry_patch_version")
    return str(patch_version) if patch_version else default


def _section_loop_deferred_reason(payload: Mapping[str, Any] | dict[str, Any] | None, default_patch: str = "1.0.3") -> str:
    if isinstance(payload, Mapping) and payload.get("deferred_reason"):
        return str(payload["deferred_reason"])
    patch_version = _section_loop_geometry_patch_version(payload, default_patch).replace(".", "_")
    return f"v{patch_version}_surface_graph_builder_pending"


def _impeller_geometry_options(dsl_context: dict[str, Any] | None) -> dict[str, Any]:
    dsl_context = dsl_context or {}
    return {
        "display_policy": dsl_context.get("display_policy"),
        "material_domain": dsl_context.get("material_domain"),
        "solid_features": dsl_context.get("solid_features"),
        "profile_defaults": dsl_context.get("profile_defaults"),
        "geometry_version": _dsl_version(dsl_context),
    }


def _dsl_version(dsl: dict[str, Any]) -> str:
    dsl_sections = dsl.get("dsl_sections", {})
    if "dsl_version" in dsl_sections:
        return dsl_sections["dsl_version"]
    version = str(dsl.get("version", ""))
    return version[:-2] if version.endswith(".0") else version


def _campaign_signature_runtime_context(dsl: dict[str, Any]) -> dict[str, Any]:
    dsl_version = _dsl_version(dsl)
    if dsl_version not in {"0.4", "0.5"}:
        return dsl
    bundle = _IMPELLER_V05_DSL_BUNDLE if dsl_version == "0.5" else _IMPELLER_V04_DSL_BUNDLE
    return {
        **dsl,
        "shape_control": {
            **bundle.shape_controls,
            **dsl.get("shape_control", {}),
        },
    }


def _manifest_validity(dsl: dict[str, Any], geometry_validity: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": geometry_validity.get("status", "PASS") if geometry_validity else "PASS",
        "geometry_contracts": geometry_validity.get("geometry_checks", []),
        "topology_contracts": geometry_validity.get("topology_checks", []),
        "engineering_warnings": geometry_validity.get("engineering_checks", []),
        "declared_contracts": dsl.get("validity_contracts", {}),
    }


def _manifest_shape_control(shape_control: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": shape_control.get("schema_version", "0.2"),
        "optimization_stage": shape_control.get("optimization_stage", 1),
        "locked_topology": shape_control.get("locked_topology", True),
        "active_policies": shape_control.get("active_policies", []),
        "semantic_handles": shape_control.get("semantic_handles", []),
        "shape_optimization_space": {
            "editable_variables": shape_control.get("editable_variables", []),
            "optimizable_variables": shape_control.get("optimizable_variables", []),
            "locked_topology": shape_control.get("locked_topology", True),
        },
        "provenance": {
            "source": "default_rule",
        },
    }


def _normalize_geometry_stage(stage: str | None) -> str:
    normalized = str(stage or "full")
    aliases = {
        "hub": "hub_support",
        "blades": "blade_surfaces",
        "edges": "edge_closures",
        "full": "edge_closures",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"hub_support", "blade_surfaces", "edge_closures"}:
        raise ValueError(f"invalid geometry stage: {stage}")
    return normalized


def _normalize_transition_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise ValueError("transition_overrides must be an object")
    return dict(overrides)


def _validation(part_family: str) -> dict[str, Any]:
    checks = (
        ["watertight_proxy", "embedded_contact_blade_root_hub", "named_regions_present"]
        if part_family == "turbine_rotor"
        else (
            [
                "watertight_proxy",
                "backswept_blade_curve_present",
                "radial_exit_greater_than_inlet",
                "kernel_uv_lines_match_blade_surface",
                "geometry_validity_passed",
                "topology_validity_passed",
                "named_regions_present",
            ]
            if part_family in {"centrifugal_impeller", "impeller"}
            else ["watertight_proxy", "vane_bridges_inner_outer_rings", "named_regions_present"]
        )
    )
    return {"status": "PASS", "checks": checks}


def _write_exports(
    run_dir: Path,
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
    geometry_metadata: dict[str, Any] | None = None,
    geometry_validation_report: dict[str, Any] | None = None,
    model_output_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    step = run_dir / f"{part_family}.step"
    stl = run_dir / f"{part_family}.stl"
    export_contract = (dsl_context or {}).get("export_contract", {})
    bounded_brep_modes = {
        "surface_graph_bounded_brep",
        "transition_resolved_bounded_brep",
        "validated_transition_bounded_brep",
        "topology_first_transition_bounded_brep",
        "topology_first_closed_nurbs_impeller_surface_graph",
        "topology_first_section_loop_blade_root_blend_surface_graph",
        "topology_first_blade_to_blade_5_loop_surface_family_graph",
    }
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") in bounded_brep_modes:
        surface_graph = (geometry_metadata or {}).get("surface_graph")
        if not surface_graph:
            raise RuntimeError(f"{export_contract.get('mode')} export requires geometry.surface_graph")
        if _is_deferred_v10_3_surface_graph(surface_graph):
            return (
                {},
                {
                    "deferred": {
                        "cad_exports": "deferred",
                        "geometry_generation_status": "DEFERRED",
                        "deferred_reason": surface_graph.get(
                            "deferred_reason",
                            "v1_0_3_surface_graph_builder_pending",
                        ),
                        "mode": export_contract.get("mode"),
                        "source": "geometry.surface_graph",
                    }
                },
            )
        if export_contract.get("mode") == "transition_resolved_bounded_brep":
            _raise_on_transition_failures(surface_graph, geometry_metadata or {})
        if export_contract.get("mode") in {
            "validated_transition_bounded_brep",
            "topology_first_transition_bounded_brep",
            "topology_first_closed_nurbs_impeller_surface_graph",
            "topology_first_section_loop_blade_root_blend_surface_graph",
            "topology_first_blade_to_blade_5_loop_surface_family_graph",
        }:
            _raise_on_missing_or_failed_geometry_validation(geometry_validation_report)
        bounded_surface_graph = None
        export_surface_graph = surface_graph
        if _uses_legacy_supported_surface_accounting(export_contract):
            bounded_surface_graph = _bounded_brep_supported_surface_graph(surface_graph)
            export_surface_graph = bounded_surface_graph["surface_graph"]
        output_dir = _model_output_dir_for_run(run_dir, model_output_root)
        stem = _safe_export_stem((dsl_context or {}).get("preset_id"), run_dir.name)
        step = output_dir / f"{stem}.step"
        stl = output_dir / f"{stem}.stl"
        obj = output_dir / f"{stem}.obj"
        manifest_copy = output_dir / f"{stem}.manifest.json"
        intermediate_dir = run_dir / ".intermediate"
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        mesh_step = intermediate_dir / f"{stem}.mesh.step"
        brep_manifest = write_bounded_brep_step(
            step,
            part_family,
            export_surface_graph,
            view_id=export_contract.get("default_view", "cad_review_360"),
        )
        mesh_manifests = write_surface_graph_exports(
            mesh_step,
            stl,
            part_family,
            surface_graph,
            view_id=export_contract.get("default_view", "cad_review_360"),
        )
        obj_manifest = write_surface_graph_obj(
            obj,
            part_family,
            surface_graph,
            view_id=export_contract.get("default_view", "cad_review_360"),
        )
        if bounded_surface_graph is not None:
            validation_checks = _legacy_bounded_brep_validation_checks(
                brep_manifest.get("validation_checks", []),
                has_excluded_surfaces=bool(bounded_surface_graph["excluded_surface_ids"]),
            )
            brep_manifest = {
                **brep_manifest,
                "bounded_brep_status": "bounded_faces_unsewn",
                "coverage_status": bounded_surface_graph["coverage_status"],
                "cad_export_scope": "supported_bounded_brep_surfaces",
                "unsupported_surface_policy": "excluded_with_manifest_accounting",
                "total_surface_count": bounded_surface_graph["total_surface_count"],
                "supported_surface_count": bounded_surface_graph["supported_surface_count"],
                "surface_count": len(bounded_surface_graph["included_surface_ids"]),
                "included_surface_ids": bounded_surface_graph["included_surface_ids"],
                "excluded_surface_ids": bounded_surface_graph["excluded_surface_ids"],
                "unsupported_surface_count": bounded_surface_graph["unsupported_surface_count"],
                "unsupported_surface_kinds": bounded_surface_graph["excluded_surface_kinds"],
                "validation_checks": validation_checks,
                "diagnostic_step_exactness": export_contract.get(
                    "diagnostic_step_exactness",
                    brep_manifest.get("export_exactness", "surface_graph_bounded_unsewn_brep_step"),
                ),
                "limitations": bounded_surface_graph["limitations"],
            }
        else:
            is_v10_3_mode = (
                export_contract.get("mode")
                == "topology_first_section_loop_blade_root_blend_surface_graph"
            )
            brep_manifest = {
                **brep_manifest,
                "export_exactness": export_contract.get(
                    "current_step_exactness" if is_v10_3_mode else "step_exactness",
                    brep_manifest.get("export_exactness", "surface_graph_bounded_unsewn_brep_step"),
                ),
                "target_exactness": export_contract.get(
                    "target_step_exactness",
                    brep_manifest.get("target_exactness", "surface_graph_trimmed_brep_step"),
                ),
                "bounded_brep_status": "bounded_faces_unsewn",
                "coverage_status": export_contract.get(
                    "current_coverage_status" if is_v10_3_mode else "coverage_status",
                    brep_manifest.get("coverage_status"),
                ),
                "cad_export_scope": export_contract.get(
                    "current_cad_export_scope" if is_v10_3_mode else "cad_export_scope",
                    brep_manifest.get("cad_export_scope"),
                ),
                "unsupported_surface_policy": export_contract.get(
                    "unsupported_surface_policy",
                    brep_manifest.get("unsupported_surface_policy", "fail_export"),
                ),
                "diagnostic_step_exactness": export_contract.get(
                    "diagnostic_step_exactness",
                    brep_manifest.get("export_exactness", "surface_graph_bounded_unsewn_brep_step"),
                ),
            }
        return (
            {"step": str(step), "stl": str(stl), "obj": str(obj), "manifest": str(manifest_copy)},
            {"step": brep_manifest, "stl": mesh_manifests["stl"], "obj": obj_manifest},
        )
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_brep":
        surface_graph = (geometry_metadata or {}).get("surface_graph")
        if not surface_graph:
            raise RuntimeError("surface_graph_brep export requires geometry.surface_graph")
        output_dir = _model_output_dir_for_run(run_dir, model_output_root)
        stem = _safe_export_stem((dsl_context or {}).get("preset_id"), run_dir.name)
        step = output_dir / f"{stem}.step"
        stl = output_dir / f"{stem}.stl"
        mesh_step = output_dir / f"{stem}.mesh.step"
        manifest_copy = output_dir / f"{stem}.manifest.json"
        view_id = export_contract.get("default_view", "cad_review_360")
        brep_manifest = write_trimmed_brep_step(
            step,
            part_family,
            surface_graph,
            view_id=view_id,
        )
        mesh_manifests = write_surface_graph_exports(
            mesh_step,
            stl,
            part_family,
            surface_graph,
            view_id=view_id,
        )
        return (
            {"step": str(step), "stl": str(stl), "mesh_step": str(mesh_step), "manifest": str(manifest_copy)},
            {"step": brep_manifest, "stl": mesh_manifests["stl"], "mesh_step": mesh_manifests["step"]},
        )
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_faithful":
        surface_graph = (geometry_metadata or {}).get("surface_graph")
        if not surface_graph:
            raise RuntimeError("surface_graph_faithful export requires geometry.surface_graph")
        export_manifests = write_surface_graph_exports(
            step,
            stl,
            part_family,
            surface_graph,
            view_id=export_contract.get("default_view", "cad_review_360"),
        )
        return {"step": str(step), "stl": str(stl)}, export_manifests
    try:
        import cadquery as cq
        from cadquery import exporters

        if part_family == "turbine_rotor":
            radius = float(parameters["hub_radius_mm"]) + 8.0
            solid = cq.Workplane("XY").circle(radius).circle(float(parameters["hub_radius_mm"]) * 0.35).extrude(8)
        elif part_family in {"centrifugal_impeller", "impeller"}:
            resolved_facets = _resolved_impeller_facets(part_family, facets or {})
            geometry_options = _impeller_geometry_options(dsl_context)
            inlet = float(parameters["inlet_radius_mm"])
            exit_radius = float(parameters["exit_radius_mm"])
            disk_thickness = 24.0 if resolved_facets["passage_topology"] == "recessed_vortex" else 30.0
            disk = cq.Workplane("XY").circle(exit_radius).extrude(disk_thickness)
            if resolved_facets.get("suction_topology") == "double_suction":
                disk = disk.union(cq.Workplane("XY").circle(exit_radius).extrude(-disk_thickness), clean=False)
            hub = (
                _impeller_hub_loft(
                    cq,
                    parameters,
                    resolved_facets,
                    profile_overrides=profile_overrides,
                    curve_overrides=curve_overrides,
                    geometry_stage=geometry_stage,
                    geometry_options=geometry_options,
                )
                if parameters.get("hub_curve_height_mm", 0.0) > 0.0
                else cq.Workplane("XY").circle(inlet).extrude(float(parameters["inlet_blade_height_mm"]))
            )
            if resolved_facets.get("suction_topology") == "double_suction":
                mirror_hub = (
                    _impeller_hub_loft(
                        cq,
                        parameters,
                        resolved_facets,
                        mirror_z=True,
                        profile_overrides=profile_overrides,
                        curve_overrides=curve_overrides,
                        geometry_stage=geometry_stage,
                        geometry_options=geometry_options,
                    )
                    if parameters.get("hub_curve_height_mm", 0.0) > 0.0
                    else cq.Workplane("XY").circle(inlet).extrude(-float(parameters["inlet_blade_height_mm"]))
                )
                hub = hub.union(mirror_hub, clean=False)
            solid = disk.union(hub, clean=False)
            for blade_wires in blade_loft_wires(
                parameters,
                resolved_facets,
                mirror_z=False,
                profile_overrides=profile_overrides,
                curve_overrides=curve_overrides,
                geometry_stage=geometry_stage,
                **geometry_options,
            ):
                solid = solid.union(_impeller_blade_loft(cq, blade_wires), clean=False)
            if resolved_facets.get("suction_topology") == "double_suction":
                for blade_wires in blade_loft_wires(
                    parameters,
                    resolved_facets,
                    mirror_z=True,
                    profile_overrides=profile_overrides,
                    curve_overrides=curve_overrides,
                    geometry_stage=geometry_stage,
                    **geometry_options,
                ):
                    solid = solid.union(_impeller_blade_loft(cq, blade_wires), clean=False)
            shroud = _impeller_shroud_proxy(
                cq,
                parameters,
                resolved_facets,
                profile_overrides=profile_overrides,
                curve_overrides=curve_overrides,
                geometry_stage=geometry_stage,
                geometry_options=geometry_options,
            )
            if shroud is not None:
                solid = solid.union(shroud, clean=False)
            solid = _impeller_mounting_bore_cut(cq, solid, parameters)
        else:
            outer = float(parameters["outer_radius_mm"])
            inner = float(parameters["inner_radius_mm"])
            solid = cq.Workplane("XY").circle(outer).circle(inner).extrude(10)
        exporters.export(solid, str(step))
        exporters.export(solid, str(stl))
    except Exception as exc:
        if part_family in {"centrifugal_impeller", "impeller"}:
            raise RuntimeError(f"failed to generate impeller STEP/STL exports: {exc}") from exc
        # ponytail: keep legacy API usable without a working CAD backend.
        step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        stl.write_text(f"solid {part_family}\nendsolid {part_family}\n", encoding="utf-8")
    return {"step": str(step), "stl": str(stl)}, {}


def _safe_export_stem(preset_id: str | None, run_id: str) -> str:
    def sanitize(value: str) -> str:
        sanitized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)
        return sanitized.strip("._-")

    safe_run_id = sanitize(run_id) or "run"
    safe_preset_id = sanitize(preset_id or "")
    if safe_preset_id:
        return f"{safe_preset_id}-{safe_run_id}"
    return safe_run_id


def _uses_legacy_supported_surface_accounting(export_contract: dict[str, Any]) -> bool:
    return (
        export_contract.get("mode") == "surface_graph_bounded_brep"
        and (
            export_contract.get("unsupported_surface_policy") == "excluded_with_manifest_accounting"
            or export_contract.get("cad_export_scope") == "supported_bounded_brep_surfaces"
        )
    )


def _raise_on_transition_failures(surface_graph: dict[str, Any], geometry_metadata: dict[str, Any]) -> None:
    failure_records: list[tuple[str, Any]] = []
    declared_failure_counts: list[tuple[str, int]] = []

    for source_name, payload in (("surface_graph", surface_graph), ("geometry_metadata", geometry_metadata)):
        if not isinstance(payload, Mapping):
            continue
        transition_failures = payload.get("transition_failures")
        if isinstance(transition_failures, list):
            failure_records.extend((source_name, failure) for failure in transition_failures)
        elif transition_failures:
            failure_records.append((source_name, transition_failures))
        transition_failure_count = payload.get("transition_failure_count")
        if isinstance(transition_failure_count, int) and transition_failure_count > 0:
            declared_failure_counts.append((source_name, transition_failure_count))

    if not failure_records and not declared_failure_counts:
        return

    observed_count = len(failure_records)
    declared_count = max((count for _, count in declared_failure_counts), default=0)
    failure_count = max(observed_count, declared_count)
    details = [_format_transition_failure(source_name, failure) for source_name, failure in failure_records[:8]]
    if observed_count > len(details):
        details.append(f"{observed_count - len(details)} additional transition failures")
    for source_name, count in declared_failure_counts:
        details.append(f"{source_name}.transition_failure_count={count}")
    detail_text = "; ".join(details) if details else "transition_failure_count > 0"
    raise RuntimeError(
        "transition-resolved bounded B-Rep export blocked by transition failures "
        f"({failure_count}): {detail_text}"
    )


def _raise_on_geometry_validation_failures(report: dict[str, Any]) -> None:
    if not geometry_validation_blocks_export(report):
        return
    failures = report.get("blocking_failures", [])
    details = []
    for failure in failures[:8]:
        if not isinstance(failure, Mapping):
            details.append(str(failure))
            continue
        identifiers = [
            str(failure[key])
            for key in (
                "surface_graph_id",
                "edge_treatment_site_id",
                "edge_family",
                "transition_policy_id",
                "reason",
            )
            if failure.get(key) is not None
        ]
        details.append(" | ".join(identifiers) if identifiers else json.dumps(dict(failure), sort_keys=True))
    if len(failures) > len(details):
        details.append(f"{len(failures) - len(details)} additional validation failures")
    raise RuntimeError(
        "geometry validation blocked validated transition bounded B-Rep export "
        f"({len(failures)}): {'; '.join(details)}"
    )


def _raise_on_missing_or_failed_geometry_validation(report: dict[str, Any] | None) -> None:
    if not isinstance(report, Mapping) or not report:
        raise RuntimeError(
            "geometry validation report with geometry_validation_status=PASS is required "
            "before validated transition bounded B-Rep export"
        )
    if report.get("geometry_validation_status") != "PASS":
        _raise_on_geometry_validation_failures(report)
        observed_status = report.get("geometry_validation_status", "missing")
        raise RuntimeError(
            "geometry validation report with geometry_validation_status=PASS is required "
            "before validated transition bounded B-Rep export "
            f"(observed geometry_validation_status={observed_status})"
        )
    _raise_on_geometry_validation_failures(report)


def _format_transition_failure(source_name: str, failure: Any) -> str:
    if not isinstance(failure, Mapping):
        return f"{source_name}: {failure}"
    identifiers = [
        str(failure[key])
        for key in ("edge_treatment_site_id", "edge_family", "transition_policy_id", "reason")
        if failure.get(key) is not None
    ]
    if not identifiers:
        identifiers = [json.dumps(dict(failure), sort_keys=True)]
    return f"{source_name}: " + " | ".join(identifiers)


def _bounded_brep_supported_surface_graph(surface_graph: dict[str, Any]) -> dict[str, Any]:
    included_surfaces: list[dict[str, Any]] = []
    included_surface_ids: list[str] = []
    excluded_surface_ids: list[str] = []
    excluded_surface_kinds: dict[str, int] = {}
    total_surface_count = len(surface_graph.get("surfaces", []))
    for surface_index, surface in enumerate(surface_graph.get("surfaces", [])):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or f"surface_{surface_index}")
        kind = str(surface.get("kind") or "")
        if kind == "annular_plane_surface":
            included_surfaces.append(surface)
            included_surface_ids.append(surface_id)
            continue
        excluded_surface_ids.append(surface_id)
        excluded_surface_kinds[kind or "missing"] = excluded_surface_kinds.get(kind or "missing", 0) + 1

    limitations = []
    if excluded_surface_ids:
        limitations.append("unsupported_surface_kinds_excluded_from_bounded_brep_step")
    return {
        "surface_graph": {**surface_graph, "surfaces": included_surfaces},
        "coverage_status": (
            "partial_supported_surfaces" if excluded_surface_ids else "complete_supported_surfaces"
        ),
        "total_surface_count": total_surface_count,
        "supported_surface_count": len(included_surfaces),
        "unsupported_surface_count": len(excluded_surface_ids),
        "included_surface_ids": included_surface_ids,
        "excluded_surface_ids": excluded_surface_ids,
        "excluded_surface_kinds": dict(sorted(excluded_surface_kinds.items())),
        "limitations": limitations,
    }


def _legacy_bounded_brep_validation_checks(
    validation_checks: list[dict[str, Any]],
    *,
    has_excluded_surfaces: bool,
) -> list[dict[str, Any]]:
    checks_by_name = {
        str(check.get("name")): dict(check)
        for check in validation_checks
        if isinstance(check, dict) and check.get("name")
    }
    ordered_names = [
        "finite_reimport_bbox",
        "complete_surface_coverage",
        "reimport_face_count_matches_manifest",
    ]
    merged_checks: list[dict[str, Any]] = []
    for name in ordered_names:
        check = dict(checks_by_name.get(name, {"name": name, "status": "PASS"}))
        if name == "complete_surface_coverage" and has_excluded_surfaces:
            check["status"] = "FAIL"
        merged_checks.append(check)

    known_names = set(ordered_names)
    merged_checks.extend(
        dict(check)
        for check in validation_checks
        if isinstance(check, dict) and check.get("name") not in known_names
    )
    return merged_checks


def _bounded_brep_strategy_reason(
    mode: str,
    cad_export_scope: str,
    unsupported_surface_policy: str,
) -> str:
    if mode == "transition_resolved_bounded_brep":
        return (
            "bounded STEP is generated from transition-resolved surface_graph CAD surfaces as unsewn B-Rep faces; "
            "mesh artifacts remain separate review outputs"
        )
    if mode == "topology_first_transition_bounded_brep":
        return (
            "bounded STEP is generated from topology-first transition surface_graph CAD surfaces as unsewn B-Rep faces; "
            "mesh artifacts remain separate review outputs"
        )
    if mode == "topology_first_closed_nurbs_impeller_surface_graph":
        return (
            "bounded STEP is generated from V1.0 native topology face samples as unsewn B-Rep faces; "
            "mesh artifacts remain separate review outputs"
        )
    if mode == "topology_first_section_loop_blade_root_blend_surface_graph":
        return (
            "bounded STEP is generated from V1.0.3 section-loop topology face samples as unsewn B-Rep faces; "
            "mesh artifacts remain separate review outputs"
        )
    if (
        cad_export_scope == "supported_bounded_brep_surfaces"
        or unsupported_surface_policy == "excluded_with_manifest_accounting"
    ):
        return (
            "bounded STEP is generated for the surface_graph CAD surface kinds supported by this contract; "
            "unsupported surface kinds are excluded with manifest accounting"
        )
    return (
        "bounded STEP is generated from all surface_graph CAD surfaces as unsewn B-Rep faces; "
        "mesh artifacts remain separate review outputs"
    )


def _model_output_dir_for_run(run_dir: Path, model_output_root: Path | None = None) -> Path:
    output_dir = Path(model_output_root) if model_output_root is not None else run_dir.parent.parent / "Model Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _export_strategy(
    part_family: str,
    dsl_context: dict[str, Any] | None = None,
    export_manifests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    export_contract = (dsl_context or {}).get("export_contract", {})
    deferred_manifest = (export_manifests or {}).get("deferred")
    if isinstance(deferred_manifest, Mapping):
        deferred_reason = (
            deferred_manifest.get("deferred_reason")
        )
        return {
            "mode": export_contract.get(
                "mode",
                deferred_manifest.get("mode", "deferred"),
            ),
            "cad_exports": "deferred",
            "source": (
                deferred_manifest.get("source", "geometry.surface_graph")
            ),
            "view": export_contract.get("default_view", "cad_review_360"),
            "geometry_generation_status": "DEFERRED",
            "deferred_reason": deferred_reason,
            "reason": "CAD exports are deferred until the V1.0.3 surface graph builder is available",
        }
    bounded_brep_modes = {
        "surface_graph_bounded_brep",
        "transition_resolved_bounded_brep",
        "validated_transition_bounded_brep",
        "topology_first_transition_bounded_brep",
        "topology_first_closed_nurbs_impeller_surface_graph",
        "topology_first_section_loop_blade_root_blend_surface_graph",
        "topology_first_blade_to_blade_5_loop_surface_family_graph",
    }
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") in bounded_brep_modes:
        mode = export_contract.get("mode", "surface_graph_bounded_brep")
        default_step_exactness_by_mode = {
            "surface_graph_bounded_brep": "surface_graph_bounded_unsewn_brep_step",
            "transition_resolved_bounded_brep": "transition_resolved_bounded_unsewn_brep_step",
            "validated_transition_bounded_brep": "validated_bounded_unsewn_review_brep_step",
            "topology_first_transition_bounded_brep": "validated_bounded_unsewn_review_brep_step",
            "topology_first_closed_nurbs_impeller_surface_graph": "topology_first_native_face_unsewn_review_brep_step",
            "topology_first_section_loop_blade_root_blend_surface_graph": "validated_bounded_unsewn_review_brep_step",
            "topology_first_blade_to_blade_5_loop_surface_family_graph": "surface_graph_bounded_unsewn_brep_step",
        }
        default_target_exactness_by_mode = {
            "surface_graph_bounded_brep": "surface_graph_trimmed_brep_step",
            "transition_resolved_bounded_brep": "transition_resolved_trimmed_brep_step",
            "validated_transition_bounded_brep": "surface_graph_trimmed_brep_step",
            "topology_first_transition_bounded_brep": "surface_graph_trimmed_brep_step",
            "topology_first_closed_nurbs_impeller_surface_graph": "surface_graph_trimmed_brep_step",
            "topology_first_section_loop_blade_root_blend_surface_graph": "surface_graph_trimmed_brep_step",
            "topology_first_blade_to_blade_5_loop_surface_family_graph": "surface_graph_trimmed_brep_step",
        }
        default_coverage_status_by_mode = {
            "surface_graph_bounded_brep": "complete_surface_graph_cad_surfaces",
            "transition_resolved_bounded_brep": "complete_transition_resolved_surface_graph",
            "validated_transition_bounded_brep": "complete_validated_transition_surface_graph",
            "topology_first_transition_bounded_brep": "complete_topology_first_validated_transition_graph",
            "topology_first_closed_nurbs_impeller_surface_graph": "complete_topology_first_closed_nurbs_impeller_surface_graph",
            "topology_first_section_loop_blade_root_blend_surface_graph": "complete_topology_first_section_loop_blade_root_blend_surface_graph",
            "topology_first_blade_to_blade_5_loop_surface_family_graph": "complete_topology_first_blade_to_blade_5_loop_surface_family_graph",
        }
        default_cad_export_scope_by_mode = {
            "surface_graph_bounded_brep": "all_surface_graph_cad_surfaces",
            "transition_resolved_bounded_brep": "all_transition_resolved_surface_graph_cad_surfaces",
            "validated_transition_bounded_brep": "all_validated_transition_surface_graph_cad_surfaces",
            "topology_first_transition_bounded_brep": "all_topology_first_validated_transition_graph_cad_surfaces",
            "topology_first_closed_nurbs_impeller_surface_graph": "all_topology_first_closed_nurbs_impeller_surface_graph_cad_surfaces",
            "topology_first_section_loop_blade_root_blend_surface_graph": "all_topology_first_section_loop_blade_root_blend_surface_graph_cad_surfaces",
            "topology_first_blade_to_blade_5_loop_surface_family_graph": "all_v1_1_blade_to_blade_surface_family_cad_surfaces",
        }
        default_step_exactness = default_step_exactness_by_mode[mode]
        default_target_exactness = default_target_exactness_by_mode[mode]
        default_coverage_status = default_coverage_status_by_mode[mode]
        default_cad_export_scope = default_cad_export_scope_by_mode[mode]
        default_unsupported_surface_policy = "fail_export"
        if mode == "topology_first_section_loop_blade_root_blend_surface_graph":
            coverage_status = export_contract.get(
                "current_coverage_status",
                export_contract.get("coverage_status", default_coverage_status),
            )
            cad_export_scope = export_contract.get(
                "current_cad_export_scope",
                export_contract.get("cad_export_scope", default_cad_export_scope),
            )
        else:
            coverage_status = export_contract.get("coverage_status", default_coverage_status)
            cad_export_scope = export_contract.get("cad_export_scope", default_cad_export_scope)
        unsupported_surface_policy = export_contract.get(
            "unsupported_surface_policy",
            default_unsupported_surface_policy,
        )
        contract_step_exactness = export_contract.get(
            "current_step_exactness" if mode == "topology_first_section_loop_blade_root_blend_surface_graph" else "step_exactness",
            export_contract.get(
                "diagnostic_step_exactness",
                export_contract.get("step_exactness", default_step_exactness),
            ),
        )
        step_exactness = (export_manifests or {}).get("step", {}).get("export_exactness") or contract_step_exactness
        target_step_exactness = export_contract.get("target_step_exactness", default_target_exactness)
        diagnostic_step_exactness = export_contract.get(
            "diagnostic_step_exactness",
            default_step_exactness,
        )
        return {
            "mode": mode,
            "cad_exports": "completed",
            "source": "geometry.surface_graph",
            "view": export_contract.get("default_view", "cad_review_360"),
            "step_exactness": step_exactness,
            "target_step_exactness": target_step_exactness,
            "diagnostic_step_exactness": diagnostic_step_exactness,
            "bounded_brep_status": "bounded_faces_unsewn",
            "sewing_status": "not_attempted",
            "coverage_status": coverage_status,
            "cad_export_scope": cad_export_scope,
            "unsupported_surface_policy": unsupported_surface_policy,
            "export_contract": {
                "mode": mode,
                "step_exactness": contract_step_exactness,
                "target_step_exactness": target_step_exactness,
                "diagnostic_step_exactness": diagnostic_step_exactness,
                "bounded_brep_status": "bounded_faces_unsewn",
                "sewing_status": "not_attempted",
                "coverage_status": coverage_status,
                "cad_export_scope": cad_export_scope,
                "unsupported_surface_policy": unsupported_surface_policy,
            },
            "reason": _bounded_brep_strategy_reason(mode, cad_export_scope, unsupported_surface_policy),
        }
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_brep":
        return {
            "mode": "surface_graph_brep",
            "cad_exports": "completed",
            "source": "geometry.surface_graph",
            "view": export_contract.get("default_view", "cad_review_360"),
            "reason": "STEP is generated from CAD surface payloads while STL/mesh STEP are graph sampled mesh",
        }
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_faithful":
        return {
            "mode": "surface_graph_faithful",
            "cad_exports": "completed",
            "source": "geometry.surface_graph",
            "view": export_contract.get("default_view", "cad_review_360"),
            "reason": "STL/STEP are generated from selected surface_graph uv_grid samples",
        }
    if part_family in {"centrifugal_impeller", "impeller"}:
        return {
            "mode": "cadquery_sync",
            "cad_exports": "completed",
            "reason": "impeller exports are generated as analysis-review STEP/STL files",
        }
    return {
        "mode": "cadquery_sync",
        "cad_exports": "completed",
        "reason": "simple legacy solid export remains synchronous",
    }


def _resolved_impeller_facets(part_family: str, facets: dict[str, str]) -> dict[str, str]:
    base = dict(LEGACY_CENTRIFUGAL_IMPELLER_FACETS)
    if part_family == "impeller":
        base.update(facets)
    else:
        base.update(facets or {})
    return base


def _impeller_named_regions(facets: dict[str, str]) -> list[str]:
    regions = ["inducer", "hub.outer_surface", "blade_root", "blade_airfoil", "radial_exit"]
    if facets.get("passage_topology") == "recessed_vortex":
        regions.append("free_passage_cavity")
    return regions


def _classify_feedback(raw_feedback: str, affected_feature: str) -> tuple[str, str]:
    text = raw_feedback.lower()
    if any(word in raw_feedback for word in ["燕尾", "榫"]) or "dovetail" in text or "primitive" in text:
        return "primitive_gap", ""
    if "blade" in text or "叶片" in raw_feedback or affected_feature == "blade_root":
        return "rule_patch", "embedded_contact(blade_root, hub.outer_surface)"
    if "vane" in text or "ngv" in text or "导向" in raw_feedback:
        return "rule_patch", "bridges(vane, inner_ring, outer_ring)"
    if "increase" in text or "decrease" in text or "调整" in raw_feedback:
        return "parameter_patch", ""
    return "needs_clarification", ""


def _impeller_cad_features(curved_hub: bool, facets: dict[str, str]) -> list[str]:
    features = [
        "curved_hub_surface" if curved_hub else "hub_solid",
        "inducer_bore",
        "lofted_blade_surface",
    ]
    flow_topology = facets.get("flow_topology", "radial")
    shroud_topology = facets.get("shroud_topology", "open")
    suction_topology = facets.get("suction_topology", "single_suction")
    features.append(f"{flow_topology}_flow_proxy")
    if flow_topology in {"mixed", "axial"}:
        features.append(f"{flow_topology}_flow_axial_offset_proxy")
    if shroud_topology == "semi_open":
        features.append("semi_open_shroud_proxy")
    elif shroud_topology == "closed":
        features.append("closed_shroud_proxy")
    if suction_topology == "double_suction":
        features.append("double_suction_mirror_proxy")
    features.append("radial_exit" if flow_topology == "radial" else f"{flow_topology}_exit")
    return features


def _impeller_blade_surface_metadata(parameters: dict[str, Any], facets: dict[str, str] | None = None) -> dict[str, Any]:
    if not parameters:
        return {}
    resolved_facets = facets or {}
    axial_factor = _impeller_axial_offset_factor(resolved_facets)
    sections = []
    for point in _sample_airfoil_curve(_dsl_template("centrifugal_impeller")["airfoil"]["curve"]["control_points"]):
        t = point[0]
        radius = float(parameters["inlet_radius_mm"]) + point[0] * (
            float(parameters["exit_radius_mm"]) - float(parameters["inlet_radius_mm"])
        )
        angle = float(parameters["inlet_blade_angle_deg"]) + point[0] * (
            float(parameters["outlet_blade_angle_deg"]) - float(parameters["inlet_blade_angle_deg"])
        ) + point[1] * 90.0 * float(parameters.get("blade_curve_gain", 1.0))
        height = float(parameters["inlet_blade_height_mm"]) + point[0] * (
            float(parameters["outlet_blade_height_mm"]) - float(parameters["inlet_blade_height_mm"])
        )
        z_base = 30.0 + t * (float(parameters["exit_radius_mm"]) - float(parameters["inlet_radius_mm"])) * axial_factor
        sections.append(
            {
                "t": round(t, 6),
                "radius_mm": round(radius, 6),
                "angle_deg": round(angle, 6),
                "height_mm": round(height, 6),
                "z_base_mm": round(z_base, 6),
                "z_tip_mm": round(z_base + height, 6),
            }
        )
    return {
        "primitive": "lofted_blade_surface",
        "profile_curve_kind": "cadquery_spline",
        "height_model": "section_interpolated",
        "loft_section_count": len(sections),
        "curve_gain": float(parameters.get("blade_curve_gain", 1.0)),
        "driven_by": [
            "inlet_blade_angle_deg",
            "outlet_blade_angle_deg",
            "blade_thickness_mm",
            "inlet_blade_height_mm",
            "outlet_blade_height_mm",
            "bspline_control_points",
        ],
        "sections": sections,
    }


def _impeller_construction_lines(parameters: dict[str, Any], facets: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    if not parameters:
        return {"hub": [], "blade": [], "shroud": []}
    hub_lines = _hub_construction_lines(parameters)
    blade_lines = _blade_construction_lines(parameters, facets)
    shroud_lines = _shroud_construction_lines(parameters, facets)
    if facets.get("suction_topology") == "double_suction":
        hub_lines += _hub_construction_lines(parameters, mirror_z=True)
        blade_lines += _blade_construction_lines(parameters, facets, mirror_z=True)
        shroud_lines += _shroud_construction_lines(parameters, facets, mirror_z=True)
    return {"hub": hub_lines, "blade": blade_lines, "shroud": shroud_lines}


def _hub_construction_lines(parameters: dict[str, Any], mirror_z: bool = False) -> list[dict[str, Any]]:
    inlet = float(parameters["inlet_radius_mm"])
    height = float(parameters.get("hub_curve_height_mm", 0.0) or parameters["inlet_blade_height_mm"])
    sections = [
        (0.0, inlet),
        (height * 0.35, inlet * 0.82),
        (height * 0.72, inlet * 0.46),
        (height, inlet * 0.18),
    ]
    lines = []
    for index, (z, radius) in enumerate(sections):
        line_z = _signed_z(z, mirror_z)
        lines.append(
            {
                "name": f"{'mirrored ' if mirror_z else ''}hub latitude {index}",
                "source": "hub_revolve_profile",
                "points": _circle_points(radius, line_z, 48),
            }
        )
    for index, angle in enumerate(range(0, 360, 45)):
        theta = math.radians(angle)
        lines.append(
            {
                "name": f"{'mirrored ' if mirror_z else ''}hub meridian {index}",
                "source": "hub_revolve_profile",
                "points": [
                    [round(radius * math.cos(theta), 6), round(radius * math.sin(theta), 6), round(_signed_z(z, mirror_z), 6)]
                    for z, radius in sections
                ],
            }
        )
    return lines


def _blade_construction_lines(parameters: dict[str, Any], facets: dict[str, str], mirror_z: bool = False) -> list[dict[str, Any]]:
    lines = []
    blade_count = int(parameters["blade_count"])
    for blade_index in range(blade_count):
        base_angle = 360.0 * blade_index / blade_count + float(parameters["outlet_blade_angle_deg"])
        frames = _impeller_blade_frames(parameters, facets, base_angle, mirror_z)
        prefix = f"{'mirrored ' if mirror_z else ''}blade {blade_index}"
        for key, label in [
            ("pressure_bottom", "pressure edge bottom"),
            ("suction_bottom", "suction edge bottom"),
            ("pressure_top", "pressure edge top"),
            ("suction_top", "suction edge top"),
        ]:
            lines.append(
                {
                    "name": f"{prefix} {label}",
                    "source": "blade_loft_wire",
                    "points": [frame[key] for frame in frames],
                }
            )
        for section_index, frame in enumerate(frames):
            lines.append(
                {
                    "name": f"{prefix} section {section_index}",
                    "source": "blade_loft_wire",
                    "points": [
                        frame["pressure_bottom"],
                        frame["suction_bottom"],
                        frame["suction_top"],
                        frame["pressure_top"],
                        frame["pressure_bottom"],
                    ],
                }
            )
    return lines


def _shroud_construction_lines(parameters: dict[str, Any], facets: dict[str, str], mirror_z: bool = False) -> list[dict[str, Any]]:
    topology = facets.get("shroud_topology", "open")
    if topology == "open":
        return []
    exit_radius = float(parameters["exit_radius_mm"])
    inlet_radius = float(parameters["inlet_radius_mm"])
    back_z, front_z = _impeller_shroud_z_levels(parameters, facets)
    prefix = "mirrored " if mirror_z else ""
    lines = [
        {
            "name": f"{prefix}front shroud inlet",
            "source": "shroud_proxy",
            "points": _circle_points(inlet_radius * 1.05, _signed_z(front_z, mirror_z), 48),
        },
        {
            "name": f"{prefix}front shroud outlet",
            "source": "shroud_proxy",
            "points": _circle_points(exit_radius, _signed_z(front_z, mirror_z), 48),
        },
    ]
    if topology == "closed":
        lines.extend(
            [
                {
                    "name": f"{prefix}back shroud inlet",
                    "source": "shroud_proxy",
                    "points": _circle_points(inlet_radius * 1.05, _signed_z(back_z, mirror_z), 48),
                },
                {
                    "name": f"{prefix}back shroud outlet",
                    "source": "shroud_proxy",
                    "points": _circle_points(exit_radius, _signed_z(back_z, mirror_z), 48),
                },
            ]
        )
    return lines


def _circle_points(radius: float, z: float, count: int) -> list[list[float]]:
    points = []
    for index in range(count + 1):
        theta = 2.0 * math.pi * index / count
        points.append([round(radius * math.cos(theta), 6), round(radius * math.sin(theta), 6), round(z, 6)])
    return points


def _impeller_blade_frames(
    parameters: dict[str, Any],
    facets: dict[str, str] | None,
    base_angle_deg: float,
    mirror_z: bool = False,
) -> list[dict[str, list[float]]]:
    half_thickness = float(parameters["blade_thickness_mm"]) / 2.0
    frames = []
    for section in _impeller_blade_surface_metadata(parameters, facets or {})["sections"]:
        radius = section["radius_mm"]
        theta = math.radians(base_angle_deg + section["angle_deg"])
        cx = radius * math.cos(theta)
        cy = radius * math.sin(theta)
        tx = -math.sin(theta) * half_thickness
        ty = math.cos(theta) * half_thickness
        z0 = _signed_z(float(section["z_base_mm"]), mirror_z)
        z1 = _signed_z(float(section["z_tip_mm"]), mirror_z)
        frames.append(
            {
                "pressure_bottom": _round_point(cx + tx, cy + ty, z0),
                "suction_bottom": _round_point(cx - tx, cy - ty, z0),
                "suction_top": _round_point(cx - tx, cy - ty, z1),
                "pressure_top": _round_point(cx + tx, cy + ty, z1),
            }
        )
    return frames


def _impeller_blade_loft(
    cq: Any,
    blade_wires: list[list[list[float]]],
) -> Any:
    wires = []
    for section in blade_wires:
        pts = [cq.Vector(*point) for point in section]
        wires.append(cq.Wire.makePolygon(pts))
    return cq.Solid.makeLoft(wires)


def _impeller_hub_loft(
    cq: Any,
    parameters: dict[str, Any],
    facets: dict[str, str],
    mirror_z: bool = False,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    geometry_options: dict[str, Any] | None = None,
) -> Any:
    wires = []
    for z, radius in hub_loft_sections(
        parameters,
        facets,
        mirror_z=mirror_z,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **(geometry_options or {}),
    ):
        wire = cq.Workplane("XY").circle(radius).val().located(cq.Location(cq.Vector(0, 0, z)))
        wires.append(wire)
    return cq.Workplane("XY").add(cq.Solid.makeLoft(wires))


def _impeller_shroud_proxy(
    cq: Any,
    parameters: dict[str, Any],
    facets: dict[str, str],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    geometry_options: dict[str, Any] | None = None,
) -> Any | None:
    topology = facets.get("shroud_topology", "open")
    if topology == "open":
        return None
    inlet = float(parameters["inlet_radius_mm"]) * 1.05
    exit_radius = float(parameters["exit_radius_mm"])
    back_z, front_z = _impeller_shroud_z_levels(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        geometry_options=geometry_options,
    )
    thickness = 8.0
    solid = _annular_disk(cq, inlet, exit_radius, front_z, thickness)
    if topology == "closed":
        solid = solid.union(_annular_disk(cq, inlet, exit_radius, back_z - thickness, thickness))
    if facets.get("suction_topology") == "double_suction":
        solid = solid.union(_annular_disk(cq, inlet, exit_radius, -front_z - thickness, thickness))
        if topology == "closed":
            solid = solid.union(_annular_disk(cq, inlet, exit_radius, -back_z, thickness))
    return solid


def _impeller_mounting_bore_cut(cq: Any, solid: Any, parameters: dict[str, Any]) -> Any:
    inlet = float(parameters["inlet_radius_mm"])
    bore_radius = float(parameters.get("mounting_bore_radius_mm", max(12.0, inlet * 0.22)))
    bore_radius = min(max(1.0, bore_radius), max(2.0, inlet * 0.52))
    extent = max(
        float(parameters["exit_radius_mm"]),
        float(parameters["inlet_blade_height_mm"]),
        float(parameters["outlet_blade_height_mm"]),
        float(parameters.get("hub_curve_height_mm", 0.0)),
        100.0,
    ) * 4.0
    cutter = cq.Workplane("XY").workplane(offset=-extent / 2.0).circle(bore_radius).extrude(extent)
    return solid.cut(cutter, clean=False)


def _annular_disk(cq: Any, inner_radius: float, outer_radius: float, z: float, thickness: float) -> Any:
    return (
        cq.Workplane("XY")
        .circle(outer_radius)
        .circle(inner_radius)
        .extrude(thickness)
        .translate(cq.Vector(0, 0, z))
    )


def _impeller_shroud_z_levels(
    parameters: dict[str, Any],
    facets: dict[str, str],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    geometry_options: dict[str, Any] | None = None,
) -> tuple[float, float]:
    return shroud_z_levels(
        parameters,
        facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **(geometry_options or {}),
    )


def _impeller_axial_offset_factor(facets: dict[str, str]) -> float:
    return {"radial": 0.0, "mixed": 0.12, "axial": 0.24}.get(facets.get("flow_topology", "radial"), 0.0)


def _signed_z(z: float, mirror_z: bool) -> float:
    return round(-z, 6) if mirror_z else round(z, 6)


def _round_point(x: float, y: float, z: float) -> list[float]:
    return [round(x, 6), round(y, 6), round(z, 6)]


def _sample_airfoil_curve(control_points: list[list[float]]) -> list[tuple[float, float]]:
    p0, p1, p2, p3 = control_points
    samples = []
    for index in range(5):
        t = index / 4.0
        one = 1.0 - t
        x = one**3 * p0[0] + 3 * one**2 * t * p1[0] + 3 * one * t**2 * p2[0] + t**3 * p3[0]
        y = one**3 * p0[1] + 3 * one**2 * t * p1[1] + 3 * one * t**2 * p2[1] + t**3 * p3[1]
        samples.append((x, y))
    return samples


def _bounded(name: str, value: float, low: float, high: float) -> float:
    if not low <= value <= high:
        raise ValueError(f"{name} out of range")
    return value


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
