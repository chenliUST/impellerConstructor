# Impeller V0.9 Kernel Validity And Reviewability Design

Date: 2026-07-04

Status: Draft for review

Supersedes: V0.8 transition-resolved geometry design

## 1. Version Thesis

V0.9 is a reliability and reviewability milestone for the impeller kernel.

V0.8 made transition policies geometry-producing, but external inspection exposed a
deeper semantic loss: some fillet patches show an arc but bend inward where the intended
edge treatment should be convex, and some chamfers do not visibly trim the adjacent
surfaces that should have been cut back. This means V0.8 can satisfy local provenance,
surface-count, and export-size checks while still failing the engineering meaning of
fillet/chamfer construction.

V0.9 therefore must not be framed as broader taxonomy work or a UI pass. It is the first
version where kernel validity becomes measurable before downstream ontology expansion,
CAE claims, or expert rule feedback are allowed to grow.

The V0.9 thesis is:

```text
constructor rule -> surface_graph -> transition semantics -> mesh/export artifacts
must be validated against measurable geometry contracts and golden cases.
```

## 2. Background

V0.3 through V0.5 established staged geometry, surface graph semantics, and export
provenance. V0.6 pointed toward trimmed NURBS and B-Rep export. V0.7 introduced bounded
transition policy metadata and mesh inspection. V0.8 routed enabled fillet/chamfer
policies through generated transition surfaces, transition-aware mesh, and export
manifests.

The V0.8 failure observed in STL/STEP review is not just a rendering defect:

- A visible arc is not enough to prove a valid fillet.
- A fillet can be geometrically inverted: concave where the ontology intends convex, or
  convex where the local solid/material side requires the opposite.
- A chamfer can be inserted as an extra surface without actually trimming or suppressing
  the adjacent main-surface region.
- A transition patch can have correct ids and provenance while failing local section
  geometry.
- Bounding box, file-size, face-count, and nonzero-triangle tests cannot catch this
  class of semantic loss.

V0.9 treats these findings as kernel validity failures. The goal is to make them
observable, reproducible, and regressed by tests.

## 3. Goals

1. Define a kernel capability matrix with explicit supported, partial, research-grade,
   and unsupported claims.
2. Define 6-10 golden cases that every V0.9 build must generate, validate, export, and
   summarize.
3. Produce a geometry validation report for every generated run.
4. Add batch model generation and a regression summary that can compare many generated
   models across versions or commits.
5. Produce a STEP/STL export review package with manifest, screenshots, and import
   evidence.
6. Link expert issues back to `surface_graph_id`, `feature_id`, `edge_family`,
   `transition_policy_id`, constructor rule, and DSL variable.
7. Correct transition semantics enough that default V0.9 fillet and chamfer cases pass
   convexity, trim, continuity, and provenance gates.
8. Keep V0.2-V0.8 loadable as historical research baselines.

## 4. Non-Goals

1. No broad new impeller taxonomy.
2. No claim of industrial exact B-Rep unless the implemented writer and tests actually
   prove the claim.
3. No solver-ready CFD or production volume meshing.
4. No automatic expert-rule patching or semi-automatic ontology back-propagation.
5. No major UI redesign.
6. No arbitrary-edge interactive CAD editor.
7. No rewriting historical V0.8 artifacts to hide the transition-sign and trim failures.

## 5. Kernel Capability Matrix

V0.9 must publish a machine-readable and human-readable capability matrix. The matrix
should be committed with the V0.9 DSL resources and copied into generated evidence
packages.

Capability states:

- `supported`: implemented, covered by golden cases, validation gates, and export gates.
- `partial`: implemented for named topology families or parameter ranges; limitations are
  explicit and tested.
- `research_grade`: useful for inspection and ontology development, but not a production
  CAD/CAE guarantee.
- `unsupported`: not implemented; requests fail clearly or remain hidden from capability
  claims.

Initial V0.9 capability matrix:

| Capability | V0.9 State | Required Evidence |
| --- | --- | --- |
| Open radial impeller surface graph | supported | Golden open baseline passes geometry and export gates |
| Closed radial impeller surface graph | supported | Golden closed baseline passes geometry and export gates |
| Blade pressure/suction sampled surfaces | supported | Surface count, ids, normals, uv-grid quality, export regions |
| Hub and bore sampled surfaces | supported | Bore/hub roles, bounded face regions, no giant proxy planes |
| Blade root fillet | partial | Convexity sign, trim offsets, continuity, radius error on golden cases |
| Leading/trailing/tip edge fillets | partial | Same transition section gates as root fillet |
| Chamfer transitions | partial | Linear-section and trim-removal gates |
| Closed hood/shroud transitions | research_grade | Explicit limitation plus golden closed review artifacts |
| STEP bounded unsewn face shell | research_grade | Reimport face count, entity types, region provenance |
| STL/OBJ sampled mesh | supported for review | Triangle counts, mesh quality, transition-region coverage |
| Watertight sewn solid | unsupported | Must not be claimed in manifest |
| Exact industrial variable-radius fillets | unsupported | Must not be claimed in manifest |
| Solver-ready CFD volume mesh | unsupported | Must not be claimed in manifest |
| Automatic expert feedback rule patching | unsupported | Issue linkage only |

The generated manifest must include:

```json
{
  "kernel_capability_matrix_id": "impeller_v0_9_kernel_capabilities",
  "capability_claim_level": "review_grade_validated_surface_kernel",
  "unsupported_claims": [
    "watertight_sewn_solid",
    "industrial_exact_brep",
    "solver_ready_cfd",
    "automatic_expert_rule_patching"
  ]
}
```

## 6. Golden Cases

V0.9 must define a fixed golden case set. These are not random examples; they are
contract tests for the constructor.

Recommended initial cases:

1. `v0_9_open_default_12_blade`
   - Open radial baseline.
   - Default blade count 12.
   - Fillet enabled on root, leading, trailing, and tip edges.
2. `v0_9_closed_default_12_blade`
   - Closed radial baseline.
   - Hood/shroud transitions included.
3. `v0_9_open_chamfer_reference`
   - Root and blade edges use chamfer, not fillet.
   - Validates trimming and linear-section behavior.
4. `v0_9_open_large_root_fillet_safe_limit`
   - Root fillet radius near the feasible upper limit.
   - Must either pass with effective-radius reporting or fail before generation.
5. `v0_9_open_small_edge_fillet`
   - Small leading/trailing/tip radii.
   - Checks that patches do not collapse into degenerate slivers.
6. `v0_9_open_disabled_transitions_sharp_edges`
   - All optional transitions disabled.
   - Confirms sharp-edge semantics and no phantom fillet surfaces.
7. `v0_9_open_aggressive_wrap`
   - High blade wrap and lean within accepted design bounds.
   - Stress-tests edge sweep and transition orientation.
8. `v0_9_closed_chamfered_bore_and_hood`
   - Closed case with bore and hood chamfer transitions.
   - Checks non-blade transition families.
9. `v0_9_public_blisk_reference_review`
   - One public-data blisk approximation retained for visual comparison.
   - Must be labeled as approximation, not validated industrial geometry.
10. `v0_9_negative_infeasible_transition`
    - Deliberately infeasible radius or invalid trim geometry.
    - Must fail cleanly with diagnostic records, not emit a partial success export.

Each golden case must produce:

- manifest JSON;
- geometry validation report JSON;
- STL;
- STEP;
- mesh/OBJ where available;
- preview screenshot set;
- export import/reimport summary;
- pass/fail row in the batch regression summary.

## 7. Validation Gates

V0.9 validation must run before generation, during geometry construction, and after
generation.

### 7.1 Pre-Generation Gates

Pre-generation gates reject impossible or unsafe input before surfaces are produced:

- numeric parameters are finite and in declared units;
- radii and thickness are positive where enabled;
- blade count is an integer within declared bounds;
- hub/tip profiles do not cross;
- mounting bore radius stays inside hub material envelope;
- requested fillet/chamfer radius fits local adjacent surface span;
- transition treatment is one of `none`, `chamfer`, `fillet`;
- required golden-case facets match the declared case contract.

Pre-generation failure output must include:

```json
{
  "gate": "pre_generation",
  "status": "failed",
  "parameter_id": "root_fillet_radius_mm",
  "reason": "requested_radius_exceeds_local_trim_allowance",
  "limit_mm": 6.4,
  "requested_mm": 12.0
}
```

### 7.2 Transition Semantic Gates

These gates directly address the V0.8 failure.

For every enabled fillet:

- `fillet_convexity_status` must match the intended material side for the edge family.
- Cross-section curvature sign must be consistent across sampled stations unless a
  documented topology exception applies.
- The transition patch must lie between the two trimmed adjacent surfaces, not inside the
  removed material side.
- Both adjacent surfaces must publish trim metadata and must not retain the old covered
  region in exported review geometry.
- Effective radius must be reported and compared to requested radius.
- G0 boundary distance and approximate G1 tangent error must be measured.

For every enabled chamfer:

- Section line between trim points must be approximately straight.
- Both adjacent surfaces must be trimmed or suppressed over the replaced region.
- Chamfer normal orientation must match the material-side convention.
- Chamfer width must be nonzero and within local feasibility limits.

Required metrics:

```json
{
  "transition_validation": {
    "edge_family": "blade_root_to_hub",
    "treatment": "fillet",
    "surface_graph_id": "blade_0_root_transition_surface",
    "convexity_status": "pass",
    "trim_status": "pass",
    "g0_boundary_max_error_mm": 0.0,
    "g1_tangent_max_error_deg": 5.0,
    "effective_radius_mm": 8.0,
    "radius_max_error_mm": 0.5
  }
}
```

### 7.3 Post-Generation Gates

Post-generation gates validate the complete `surface_graph`:

- all required roles exist for the case;
- no duplicate surface ids;
- every surface has a nonempty `uv_grid` or supported analytic definition;
- no NaN, infinity, or impossible coordinate;
- no degenerate uv rows/columns above threshold;
- surface normals are consistently oriented per role;
- adjacent transition boundaries are within tolerance;
- triangle count and face count are nonzero for included surfaces;
- transition region coverage matches enabled policies;
- disabled transitions do not appear as active transition surfaces;
- validation status is `pass`, `warning`, or `fail`, never missing.

## 8. Export Gates

V0.9 export success requires more than file creation.

### 8.1 STL Gates

STL export must pass:

- binary or ASCII structure parse succeeds;
- triangle count equals manifest count;
- all golden-case required roles have nonzero triangle regions;
- transition surfaces have triangle regions when enabled;
- no triangle has NaN, infinity, or zero area above tolerance;
- bounding box is within expected model envelope;
- no proxy disk or giant placeholder plane appears.

### 8.2 STEP Gates

STEP export must pass:

- file is parseable by OCCT reimport where local dependencies allow it;
- manifest `bounded_face_count` matches reimport face count when reimport is available;
- file contains expected face/surface entities for generated surfaces;
- no `TRIANGULATED_FACE_SET` is used for the review B-Rep STEP unless the export is
  explicitly labeled as mesh STEP;
- no unbounded `10000 x 10000` plane proxy appears;
- included face regions cover all required surface roles;
- transition faces carry edge-family and transition-policy provenance.

V0.9 STEP remains a bounded, unsewn review shell unless and until sewing tests prove
watertight solid behavior. The manifest must say this explicitly:

```json
{
  "export_exactness": "validated_bounded_unsewn_review_brep_step",
  "target_exactness": "trimmed_nurbs_brep_step",
  "watertight_solid_status": "unsupported"
}
```

### 8.3 Manifest And Provenance Gates

Every export manifest must include:

- `run_id`;
- `preset_id`;
- `dsl_version`;
- `geometry_version`;
- `golden_case_id` when applicable;
- capability matrix id;
- validation report id;
- included and excluded surface ids;
- transition validation summary;
- face and triangle regions;
- expert issue link placeholders.

No V0.9 export may be marked successful if a required enabled transition has failed
convexity, trim, or boundary validation.

## 9. Batch Regression Workflow

V0.9 must introduce a batch generation workflow that can be run locally and in CI-like
verification modes.

Workflow:

```text
case registry
-> synthesize engine
-> instantiate model
-> validate geometry
-> export STL/STEP/manifest
-> optional reimport checks
-> screenshot/package evidence
-> aggregate summary
```

Batch summary fields:

```json
{
  "batch_id": "v0_9_golden_2026_07_04",
  "git_commit": "",
  "case_count": 10,
  "passed": 0,
  "warning": 0,
  "failed": 0,
  "metrics": {
    "max_transition_g0_error_mm": 0.0,
    "max_transition_g1_error_deg": 0.0,
    "max_radius_error_mm": 0.0,
    "failed_export_count": 0
  }
}
```

Batch modes:

- `golden`: run the fixed V0.9 cases.
- `sweep`: generate parameter sweeps inside declared safe envelopes.
- `negative`: verify invalid cases fail cleanly.
- `compare`: compare current results with a previous baseline manifest.

Pass/fail policy:

- Golden batch must pass before V0.9 is considered complete.
- Sweep batch may contain warnings but must not silently export invalid geometry.
- Negative batch must fail in expected places with structured diagnostics.
- Compare batch must report changed metrics, not hide drift.

## 10. Expert Feedback Integration

V0.9 does not automatically patch rules from expert feedback. It makes feedback linkable
and regression-ready.

Expert issue schema:

```json
{
  "expert_issue_id": "expert-2026-07-04-001",
  "source_artifact": "radial_open_reference_v0_9_run.step",
  "artifact_view": "cad_review_360",
  "issue_type": "incorrect_transition_convexity",
  "severity": "blocking",
  "surface_graph_id": "blade_0_root_transition_surface",
  "feature_id": "blade_0_root_transition",
  "edge_family": "blade_root_to_hub",
  "transition_policy_id": "blade_root_to_hub.default",
  "constructor_rule": "transition_resolver.blade_root_fillet",
  "dsl_variable": "root_fillet_radius_mm",
  "expected_behavior": "convex fillet on material side with adjacent hub/blade surfaces trimmed",
  "observed_behavior": "concave arc and adjacent surfaces not cut back",
  "disposition": "add_regression_case"
}
```

Disposition values:

- `add_regression_case`;
- `tighten_validation_gate`;
- `rule_candidate`;
- `documentation_limitation`;
- `not_reproducible`;
- `deferred`.

An issue becomes a regression case only when it has:

- artifact path;
- screenshot or CAD view evidence;
- surface or region provenance;
- expected behavior;
- observed behavior;
- reproduction parameters.

## 11. Evidence Package

V0.9 evidence should be written under:

```text
docs/evidence/2026-07-04-impeller-v0-9-kernel-validity-reviewability/
```

Required layout:

```text
README.md
capability_matrix/
  impeller_v0_9_kernel_capabilities.json
golden_cases/
  golden_case_registry.json
  <case_id>/
    manifest.json
    geometry_validation_report.json
    export_manifest.json
    import_check.json
    screenshots/
    expert_review_notes.md
batch_regression/
  golden_summary.json
  sweep_summary.json
  negative_summary.json
expert_issues/
  issue_registry.json
  issue-*.json
```

Large binary exports should normally remain under ignored local output directories such
as `Model Output/` unless a small artifact is explicitly needed as research evidence.
The evidence package should store enough JSON/text metadata to reproduce the run and
locate the local artifact.

## 12. Acceptance Criteria

V0.9 is complete only when all of the following are true:

1. V0.9 resource line exists with open and closed presets:
   - `radial_open_reference_v0_9`
   - `radial_closed_reference_v0_9`
2. Capability matrix is committed and included in generated manifests.
3. Golden case registry contains 6-10 cases and the default golden batch passes.
4. Geometry validation report is generated for every run.
5. Transition semantic gates catch the V0.8 failure class:
   - concave/inverted fillet where convex is required;
   - chamfer or fillet surface inserted without adjacent trim;
   - stale transition surface that does not respond to treatment/radius.
6. Default V0.9 open and closed cases have:
   - zero required transition failures;
   - nonzero transition surface regions;
   - passing convexity and trim gates for required transitions.
7. STL export parses and its triangle regions match manifest counts.
8. STEP export is parseable by available local import checks and does not collapse to
   hub-only planes, proxy disks, mesh STEP, or unbounded placeholder planes.
9. Batch regression summary reports pass/fail counts and worst geometry metrics.
10. Expert issue schema can link an exported artifact issue back to DSL variables.
11. V0.2-V0.8 historical presets remain loadable and are not relabeled as V0.9.
12. `.\scripts\verify_repository.ps1 -Mode fast` passes.
13. `.\scripts\verify_repository.ps1 -Mode full` passes when local dependencies are
    available.

## 13. Risks And Deferred Work

### Risks

- Correct convexity depends on a reliable material-side convention for every edge
  family. If the convention is ambiguous, V0.9 must fail with an explicit diagnostic
  instead of guessing.
- Trimming sampled surfaces can create gaps, overlaps, or degenerate strips near tight
  radii and aggressive blade wrap.
- STEP reimport success does not prove industrial CAD validity; it only proves the
  current review-shell contract.
- Batch sweeps can produce large evidence volume. The default committed evidence must
  stay text/JSON-first.

### Deferred Work

- Exact trimmed NURBS/B-Rep sewing is deferred to a later version.
- Watertight solid generation is deferred.
- Solver-ready CFD volume mesh generation is deferred.
- CAE solver adapters are deferred.
- Automatic or semi-automatic expert-rule back-propagation is deferred.
- Broad impeller taxonomy expansion is deferred until the V0.9 validity gates are
  stable.

## Implementation Planning Notes

The V0.9 implementation plan should start with tests and diagnostics, not new geometry
features:

1. Create the golden-case registry and validation report schema.
2. Add failing tests for inverted fillet convexity and missing adjacent trim.
3. Add transition section analyzers for fillet/chamfer geometry.
4. Correct transition construction and trimming.
5. Route validation status into STL/STEP/export manifests.
6. Add batch generation and regression summaries.
7. Write evidence package and update version docs.

The first implementation checkpoint should prove that the existing V0.8 failure is
detected before attempting to improve the geometry.
