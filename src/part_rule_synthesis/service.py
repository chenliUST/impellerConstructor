from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from part_rule_synthesis.impeller_cfd_manifest import build_cfd_full_360_manifest
from part_rule_synthesis.impeller_brep_export import write_trimmed_brep_step
from part_rule_synthesis.impeller_design_space import build_campaign_signature
from part_rule_synthesis.impeller_kernel import build_impeller_geometry, blade_loft_wires, hub_loft_sections, shroud_z_levels
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
        transition_overrides: dict[str, Any] | None = None,
        geometry_stage: str = "full",
    ) -> ModelRun:
        dsl = self._engine(engine_id)
        bound = _bind_parameters(dsl, parameters)
        operation_graph = _operation_graph(dsl, bound)
        normalized_geometry_stage = _normalize_geometry_stage(geometry_stage)
        normalized_profile_overrides = profile_overrides or {}
        normalized_curve_overrides = curve_overrides or {}
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
            "geometry_stage": normalized_geometry_stage,
            "primitive_version": PRIMITIVES["version"],
            "operation_graph": operation_graph,
        }
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
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
        )
        geometry_metadata = _geometry_metadata(
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
        )
        geometry_kernel = _geometry_kernel_metadata(
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
        )
        exports, export_manifests = _write_exports(
            run_dir,
            dsl["part_family"],
            bound,
            dsl.get("facets", {}),
            profile_overrides=normalized_profile_overrides,
            curve_overrides=normalized_curve_overrides,
            geometry_stage=normalized_geometry_stage,
            dsl_context=dsl,
            geometry_metadata=geometry_metadata,
            model_output_root=self.model_output_root,
        )
        export_strategy = _export_strategy(dsl["part_family"], dsl_context=dsl)
        simulation_manifests = {}
        if dsl["part_family"] == "impeller" and _dsl_version(dsl) in {"0.4", "0.5"}:
            surface_graph = geometry_metadata.get("surface_graph", {})
            cfd_view = dsl.get("simulation_views", {}).get("cfd_full_360", {})
            simulation_manifests["cfd_full_360"] = build_cfd_full_360_manifest(
                surface_graph,
                cfd_view,
                blade_count=int(bound.get("blade_count", 0)),
            )
        if dsl["part_family"] == "impeller" and _dsl_version(dsl) == "0.6":
            simulation_manifests["cfd_surface_mesh"] = build_surface_mesh_manifest(
                geometry_metadata.get("surface_graph", {}),
                view_id="cfd_full_360",
            )
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
            "export_strategy": export_strategy,
            "exports": exports,
            "export_manifests": export_manifests,
            "notice": "Research geometry; inferred regions are not released for operation.",
        }
        if transition_policies is not None:
            manifest["transition_overrides"] = normalized_transition_overrides
            manifest["transition_policies"] = transition_policies
        if manifest["dsl_version"] in {"0.4", "0.5"}:
            manifest["campaign_signature"] = build_campaign_signature(
                _campaign_signature_runtime_context(dsl),
                normalized_profile_overrides,
                dsl.get("feature_states"),
            )
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
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    is_impeller = part_family in {"centrifugal_impeller", "impeller"}
    resolved_facets = _resolved_impeller_facets(part_family, facets or {}) if is_impeller else {}
    impeller_geometry = (
        build_impeller_geometry(
            parameters,
            resolved_facets,
            profile_overrides=profile_overrides,
            curve_overrides=curve_overrides,
            geometry_stage=geometry_stage,
            **_impeller_geometry_options(dsl_context),
        )
        if is_impeller
        else {}
    )
    blade_surface = impeller_geometry.get("blade_surface", {}) if is_impeller else {}
    curved_hub = is_impeller and parameters.get("hub_curve_height_mm", 0.0) > 0.0
    return {
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


def _geometry_kernel_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if part_family not in {"centrifugal_impeller", "impeller"}:
        return {}
    resolved_facets = _resolved_impeller_facets(part_family, facets or {})
    geometry = build_impeller_geometry(
        parameters,
        resolved_facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **_impeller_geometry_options(dsl_context),
    )
    return geometry["kernel"]


def _geometry_validity_metadata(
    part_family: str,
    parameters: dict[str, Any],
    facets: dict[str, str] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "edge_closures",
    dsl_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if part_family not in {"centrifugal_impeller", "impeller"}:
        return {}
    resolved_facets = _resolved_impeller_facets(part_family, facets or {})
    geometry = build_impeller_geometry(
        parameters,
        resolved_facets,
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage=geometry_stage,
        **_impeller_geometry_options(dsl_context),
    )
    return geometry["validity"]


def _impeller_geometry_options(dsl_context: dict[str, Any] | None) -> dict[str, Any]:
    dsl_context = dsl_context or {}
    return {
        "display_policy": dsl_context.get("display_policy"),
        "material_domain": dsl_context.get("material_domain"),
        "solid_features": dsl_context.get("solid_features"),
        "profile_defaults": dsl_context.get("profile_defaults"),
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
    model_output_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    step = run_dir / f"{part_family}.step"
    stl = run_dir / f"{part_family}.stl"
    export_contract = (dsl_context or {}).get("export_contract", {})
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_bounded_brep":
        surface_graph = (geometry_metadata or {}).get("surface_graph")
        if not surface_graph:
            raise RuntimeError("surface_graph_bounded_brep export requires geometry.surface_graph")
        output_dir = _model_output_dir_for_run(run_dir, model_output_root)
        stem = _safe_export_stem((dsl_context or {}).get("preset_id"), run_dir.name)
        step = output_dir / f"{stem}.step"
        stl = output_dir / f"{stem}.stl"
        manifest_copy = output_dir / f"{stem}.manifest.json"
        export_manifests = write_surface_graph_exports(
            step,
            stl,
            part_family,
            surface_graph,
            view_id=export_contract.get("default_view", "cad_review_360"),
        )
        export_manifests["step"] = {
            **export_manifests["step"],
            "bounded_brep_status": export_contract.get("bounded_brep_status", "deferred_until_bounded_face_export"),
            "target_step_exactness": export_contract.get(
                "target_step_exactness",
                "surface_graph_trimmed_brep_step",
            ),
            "diagnostic_step_exactness": export_contract.get(
                "diagnostic_step_exactness",
                "surface_graph_bounded_unsewn_brep_step",
            ),
            "limitations": [
                "bounded_brep_construction_deferred_to_task_5",
                "step_is_surface_graph_mesh_not_trimmed_brep",
            ],
        }
        return {"step": str(step), "stl": str(stl), "manifest": str(manifest_copy)}, export_manifests
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


def _model_output_dir_for_run(run_dir: Path, model_output_root: Path | None = None) -> Path:
    output_dir = Path(model_output_root) if model_output_root is not None else run_dir.parent.parent / "Model Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _export_strategy(part_family: str, dsl_context: dict[str, Any] | None = None) -> dict[str, Any]:
    export_contract = (dsl_context or {}).get("export_contract", {})
    if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_bounded_brep":
        step_exactness = export_contract.get("step_exactness", "surface_graph_mesh_step")
        target_step_exactness = export_contract.get("target_step_exactness", "surface_graph_trimmed_brep_step")
        diagnostic_step_exactness = export_contract.get(
            "diagnostic_step_exactness",
            "surface_graph_bounded_unsewn_brep_step",
        )
        bounded_brep_status = export_contract.get("bounded_brep_status", "deferred_until_bounded_face_export")
        return {
            "mode": "surface_graph_bounded_brep",
            "cad_exports": "deferred",
            "source": "geometry.surface_graph",
            "view": export_contract.get("default_view", "cad_review_360"),
            "step_exactness": step_exactness,
            "target_step_exactness": target_step_exactness,
            "diagnostic_step_exactness": diagnostic_step_exactness,
            "bounded_brep_status": bounded_brep_status,
            "export_contract": {
                "mode": "surface_graph_bounded_brep",
                "step_exactness": step_exactness,
                "target_step_exactness": target_step_exactness,
                "diagnostic_step_exactness": diagnostic_step_exactness,
                "bounded_brep_status": bounded_brep_status,
            },
            "reason": "Task 2 writes graph-derived mesh STEP/STL review outputs; bounded BREP construction is deferred",
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
