# Version History

This repository keeps previous impeller DSL versions in source control and in versioned resource folders. The goal is to preserve the research trail: observed loss, revised semantics, new DSL contracts, and implementation behavior should remain auditable.

Current latest development line: `v1_1`. V1.1 is the blade-to-blade loop surface-family constructor line. V1.0 is preserved as the topology-first native face constructor line. V0.9/V0.91 remain the transition-validity research baselines.

## Git Milestones

| Milestone | Commit | Description |
| --- | --- | --- |
| Baseline | `bdb60d2` | Initial part-rule-synthesis project baseline. |
| v0.2 slice | `2d3957b` | First focused axisymmetric throughflow impeller DSL/runtime/frontend metadata path. |
| v0.3 runtime | `7afb0d2` | Solid hub/hood, profile/curve overrides, staged geometry, and frontend workflow. |
| v0.4 graph contract | `f74eb06` | Design-space campaign signatures, variable profile topology, surface/feature graph, CFD full-360 manifest, and frontend CFD view. |
| v0.5 export contract | local implementation | Surface-graph-faithful STL/STEP export contract with region provenance. |
| v0.6 B-Rep evidence line | local implementation | Graph-derived unsewn NURBS/analytic B-Rep support-face STEP export, CFD surface mesh inspection manifest, Model Output artifacts, and explicit fillet/blend controls. |
| v0.7 bounded transition line | current branch | Bounded B-Rep face export, edge-family transition policies, OBJ mesh artifacts, mesh overlay inspection, and OCCT reimport bounding-box gate. |
| v1.0 topology-first constructor | current worktree | Native named blade edge, root, hub, bore, and bevel faces with shared-edge topology identity and V1.0 validation gates. |
| v1.1 blade-to-blade surface family | current worktree | Five span-station blade-to-blade loop family, main/splitter passage-bisector semantics, half-thickness edge caps, explicit V1.1 hub solid review faces, and shared-boundary UV mesh contracts. |

Version tags:

```text
impeller-dsl-v0.2 -> 2d3957b
impeller-dsl-v0.3 -> 7afb0d2
impeller-dsl-v0.4 -> f74eb06
```

The rollback tags currently cover v0.2 through v0.4. V0.5, V0.6, and V0.7 are preserved as versioned resource folders and implementation evidence in the current repository line.

## v0.2

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2
src/part_rule_synthesis/ontology/impeller/v0_2
```

Primary preset ids:

```text
radial_open_reference
radial_closed_reference
```

Purpose:

- Establish a narrow `AxisymmetricThroughflowRadialBladedImpeller` slice.
- Move from ad hoc impeller parameters into JSON DSL and ontology resources.
- Expose constructor metadata and validity contracts in run manifests.
- Keep the legacy `radial_open_reference` alias usable.

## v0.3

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3
src/part_rule_synthesis/ontology/impeller/v0_3
```

Primary preset ids:

```text
radial_open_reference_v0_3
radial_closed_reference_v0_3
```

Purpose:

- Add finite hub solid and finite hood shell semantics.
- Add hub/hood thickness and chamfer parameters.
- Add profile curve overrides and blade curve overrides.
- Add staged generation for hub, blades, and edge closures.
- Add frontend editors for meridional profiles and blade intrinsic curves.
- Produce v0.3 video sweep evidence.

## v0.4

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4
src/part_rule_synthesis/ontology/impeller/v0_4
```

Primary preset ids:

```text
radial_open_reference_v0_4
radial_closed_reference_v0_4
```

Purpose:

- Add optimization-ready design space and campaign signatures.
- Freeze topology separately from numeric design values.
- Support variable NURBS profile control topology.
- Add surface/feature graph contracts around generated sampled geometry.
- Add CFD full-360 manifest with patch groups and patch instances.
- Add frontend CAD review, CFD full-360, and feature-debug simulation views.

Known boundary:

- v0.4 emits research-grade sampled geometry.
- Sampled blend/fillet surfaces are labeled, not exact industrial B-Rep fillets.
- CFD manifest generation does not yet invoke a mesher or solver.
- Periodic single-passage CFD, FEA solid adapters, and CAM/DFMA feedback loops are future layers.

## v0.5

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5
```

Primary preset ids:

```text
radial_open_reference_v0_5
radial_closed_reference_v0_5
```

Purpose:

- Preserve the v0.4 surface/feature graph and CFD full-360 semantics.
- Add `export_contracts/surface_graph_faithful.json`.
- Route v0.5 STL/STEP exports through `manifest.geometry.surface_graph`.
- Add `export_manifests` with exactness labels and region provenance.
- Make exported triangles/faces traceable to `surface_graph_id`, feature, and role.

Known boundary:

- STL is a sampled mesh projection of `surface_graph`.
- STEP is a graph-derived faceted surface shell labeled `surface_graph_mesh_step`.
- v0.5 does not claim exact analytic B-Rep surfaces, OCCT sewing/healing, or solver-ready meshes.

## v0.6

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6
```

Primary preset ids:

```text
radial_open_reference_v0_6
radial_closed_reference_v0_6
```

Purpose:

- Preserve the v0.5 surface-graph source of truth.
- Add graph-derived unsewn NURBS/analytic B-Rep support-face STEP export.
- Add CFD surface mesh inspection manifests and Model Output artifact copies.
- Add explicit fillet/blend controls while keeping export exactness labels honest.

Known boundary:

- STEP exactness is `surface_graph_support_face_brep_step`.
- `surface_graph_trimmed_nurbs_step` remains a target label, not the current implementation.
- Trim loops and `cad_edge` wires are not consumed into true trimmed faces.
- V0.6 does not claim watertight sewing, manufacturing CAD certification, universal CAD healing, or solver-ready CFD volume meshes.

## v0.7

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7
```

Primary preset ids:

```text
radial_open_reference_v0_7
radial_closed_reference_v0_7
```

Purpose:

- Advance from V0.6 support-face evidence to bounded B-Rep face export for supported surface families.
- Add edge-family transition policies and carry transition provenance through generated geometry, OBJ exports, and CFD surface mesh manifests.
- Add OBJ mesh artifacts for mesh review and frontend mesh overlay inspection.
- Add an OCCT reimport bounding-box gate for finite bounded STEP faces.

Known boundary:

- Bounded faces are unsewn and partially scoped to supported annular face families.
- OBJ and STL remain sampled mesh review artifacts, not manufacturing CAD.
- V0.7 does not claim sewn-solid certification, solver-ready CFD volume meshes, production meshing adapters, or manufacturing validation.

## V1.0 Topology-First Closed NURBS Impeller Constructor

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0
```

Primary preset ids:

```text
radial_open_reference_v1_0
radial_closed_reference_v1_0
```

Purpose:

- Replace post-generated edge treatments with native named blade, root, hub, bore, and bevel faces.
- Generate pressure, suction, leading-edge, trailing-edge, tip, and root faces as first-class topology faces.
- Generate hub bottom, mounting bore, and bevel/chamfer faces directly from the hub profile.
- Add shared-edge topology identity with zero synthetic shared edges for the V1.0 sampled review graph.
- Route the first two frontend throughflow presets to V1.0.

Known boundary:

- V1.0 remains sampled review-grade geometry.
- Exact sewn OCCT B-Rep solids, production meshing, and solver-ready CFD remain future integration work.

## V1.1 Blade-To-Blade Loop Surface-Family Constructor

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1
```

Primary preset ids:

```text
radial_open_reference_v1_1
radial_closed_reference_v1_1
radial_open_high_twist_thin_reference_v1_1
```

Purpose:

- Replace V1.0.4 local section-loop semantics with an unwrapped blade-to-blade domain `D_h = (s, q, h)`.
- Generate five span-station loop families at `h = 0.00, 0.25, 0.50, 0.75, 1.00`.
- Generate pressure, suction, leading-edge, trailing-edge, root attachment, and tip/shroud attachment surfaces from shared loop boundaries.
- Position splitter blades by the adjacent main-blade passage bisector rather than by an independently reset local camber curve.
- Define leading/trailing edge caps in physical `s_mm-q_mm` space with default sagitta equal to half local blade thickness.
- Emit explicit hub support/material review faces, including annulus, bottom, outer wall, and mounting bore surfaces.
- Keep frontend edits routed through `profile_overrides` for meridional profiles and `blade_to_blade_loop_family_overrides` for loop-family controls.

Known boundary:

- V1.1 remains sampled review-grade geometry.
- It does not yet claim exact sewn OCCT solids, certified manufacturing CAD, solver-ready CFD volume meshes, or automatic expert-rule patching.
- The V1.1 ontology slice is currently encoded through DSL schema, constructor classification/material-domain contracts, export contracts, and capability matrices; there is no separate `src/part_rule_synthesis/ontology/impeller/v1_1` resource folder yet.

Evidence:

```text
docs/evidence/2026-07-08-impeller-v1-1-milestone-summary.md
docs/evidence/2026-07-08-impeller-v1-1-preset-hub-solid-display-evidence.md
docs/evidence/2026-07-08-impeller-v1-1-1-viewer-preset-parameter-overhaul-evidence.md
```

### V1.1.1 - Viewer, Preset, And Parameter Overhaul

- Clarifies shaded/wireframe/combined viewer semantics.
- Makes CFD360 mesh inspection use all visible sampled surfaces instead of only transition regions.
- Narrows the active V1.1 catalog to five representative presets: open throughflow, closed throughflow, NASA Stage 37 stator ring, RR UltraFan CTi fan, and public rocket turbopump inducer.
- Adds zero-splitter closed preset support.
- Moves V1.1 frontend parameter visibility and order to preset-owned `editable_parameters`.
- Raises the RR UltraFan CTi fan review sampling density enough for bounded STEP export fit validation without changing its shape parameters.

### V1.1.2 - Canonical NURBS Parameterization

- Keeps the V1.1 blade-to-blade S-Q-H surface-family constructor but adds a canonical NURBS input layer.
- Separates universal construction parameters from preset seeds and derived frontend handles.
- Defines active blade span through root/tip offset policy instead of implying that `h = 0` is the raw hub support surface.
- Reclassifies leading and trailing edges as NURBS cap curves with rounded-cap intent and measured continuity, not semicircle primitives.
- Requires all five active V1.1 presets to translate into `canonical_nurbs_parameterization`.
- Adds a frontend `Parameter views` tab for generated-model multi-view annotations of resolved canonical parameters.
- Surfaces canonical payload and metrics in runtime, surface graph, service manifest, and frontend preset defaults.
- Uses pointwise active-span feasibility as the canonical diagnostic rule.
- Scales bounded BREP fit tolerance by sampled grid resolution for large review-grade twisted surfaces while preserving finite-grid validation.

Evidence and spec:

```text
docs/superpowers/specs/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-spec.md
docs/evidence/2026-07-10-impeller-v1-1-2-semantic-change-log.md
docs/evidence/2026-07-10-impeller-v1-1-2-insight-log.md
docs/evidence/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-evidence.md
```

### V1.1.3 - Graphical Parameter Inspection

- Separates the runtime release and inspection contract (`1.1.3`) from the unchanged geometry patch and canonical payload (`1.1.2`).
- Replaces the text-only Parameter views presentation with read-only full-size 3D, Top, Meridional, and S-Q views plus a maximizable Quad overview.
- Uses one shared WebGL renderer and generated scene for all geometric inspection viewports.
- Adds generated-geometry selection, deterministic annotation levels, S-Q section-loop/control inspection, and explicit stale-generation rejection.
- Hardens provenance across all visible/inspectable source evidence while retaining only explicit hidden reference-helper UV exemptions.
- Resolves S-Q to physical millimetric display coordinates, with source coordinates and geometry-derived scale retained in the contract.
- Adds authoritative stable control-point IDs, deep bidirectional contract validation, and relationship-aware blade/station/segment selection.
- Adds default key annotations in 3D, Top, and Meridional views, including real support profile/control geometry when supplied.
- Reports the exact badge `Resolved manifest | runtime 1.1.3 | geometry 1.1.2` and instruments actual renderer/context construction.
- Keeps all five active V1.1 preset IDs and V1.1.2 geometry assertions unchanged.

Evidence and design:

```text
docs/superpowers/specs/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-design.md
docs/evidence/2026-07-10-impeller-v1-1-3-semantic-change-log.md
docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md
docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md
```

### V1.1.4 - Preset Hardening And Review Workspace

- Keeps the canonical NURBS parameterization at `1.1.2` while advancing the runtime
  and resolved inspection contract to `1.1.4`.
- Corrects canonical splitter placement at the same physical streamwise coordinate
  as adjacent main blades and blocks failed passage positioning.
- Fixes no-splitter inspection semantics and engineering angular tolerance so all
  five representative presets instantiate through the service.
- Raises the open tip and closed shroud flowpath profiles in the first two presets.
- Adds sampled support-profile angle and active-height gates for the first two
  review presets.
- Replaces the active parameter editor with a full-width, preset-only CAD Review
  and Engineering Drawing workspace.
- Separates preset-only instantiation from the historical parameter editor payload,
  preventing the first preset defaults from contaminating no-splitter presets.
- Adds a generation-bound semantic Engineering Drawing contract with Top plus
  active-root/midspan/active-tip sections, NURBS meridional construction evidence,
  and S-Q plus shared-renderer representative blade views.
- Removes CFD full-360, CFD mesh, feature-debug, parameter, transition and curve
  editing controls from the active frontend while retaining historical source files.

Spec and evidence:

```text
docs/superpowers/specs/2026-07-12-impeller-v1-1-4-review-workspace-and-preset-hardening-spec.md
docs/superpowers/plans/2026-07-12-impeller-v1-1-4-review-workspace-and-preset-hardening-implementation.md
docs/evidence/2026-07-12-impeller-v1-1-4-semantic-change-log.md
docs/evidence/2026-07-12-impeller-v1-1-4-insight-log.md
docs/evidence/2026-07-12-impeller-v1-1-4-verification-evidence.md
```

### V1.1.5 - Engineering Drawing Fidelity

- Advances the runtime and Engineering Drawing contract to `1.1.5` while keeping
  canonical geometry at `1.1.2` and Parameter Inspection at `1.1.4`.
- Replaces section-loop Top outlines with dense resolved blade-surface projections
  and restores explicit hub-top and mounting-bore topology.
- Shows main and splitter root/mid/tip sections in Top, five span stations in S-Q,
  and matching XYZ loop overlays on enlarged high-DPI blade scenes.
- Evaluates actual rational NURBS support profiles separately from dashed control
  polygons and adds section material hatching plus an orthographic side view.
- Adds six construction tables and a validated registry covering every canonical
  parameter leaf.
- Adds cached per-view drawing endpoints so the read-only frontend does not mount
  the complete drawing payload at once.
- Adds compact Drawing-mode instantiation and representative-blade view payloads,
  preventing public presets from transporting full repeated surface graphs.
- Replaces variadic drawing-bounds reduction with an iterative accumulator so
  high-blade-count public presets cannot overflow the JavaScript call stack.
- Adds the drawing-derived `ks007g23b_turbine_impeller_v1_1` review preset as an
  explicit approximation with per-parameter confidence and source provenance;
  it does not claim reconstruction of the referenced but unavailable 3D model.
- Adds a separate `ks007g23b_step_reconstructed_v1_1` review preset after the
  source STEP became available. Exact B-Rep measurements, improved confidence,
  and V1.1 reduction losses remain explicit; the drawing preset is preserved.

Plan and evidence:

```text
docs/superpowers/plans/2026-07-12-impeller-v1-1-5-engineering-drawing-fidelity-implementation.md
docs/evidence/2026-07-12-impeller-v1-1-5-semantic-change-log.md
docs/evidence/2026-07-12-impeller-v1-1-5-insight-log.md
docs/evidence/2026-07-12-impeller-v1-1-5-verification-evidence.md
```

### V1.1.6 - STEP Reconstruction Audit

- Adds bounded raw STEP upload, persistent audit stages and explicit stable
  failures without changing the V1.1.2 geometry constructor.
- Treats the imported STEP B-Rep as source authority and records exact topology,
  units, bounds, analytic/freeform surface inventory and source hashes.
- Resolves the rotation frame from coaxial analytic surfaces and classifies
  periodic blade-side, closure, support, bore and material face evidence with
  source face ids and confidence.
- Maps measured evidence into existing V1.1.2 parameters. Six-pole support
  profiles are fitted from dense targets with endpoint and monotonicity
  constraints; sampled source points are not relabeled as NURBS poles.
- Runs hub support, blade surfaces and edge closures through the unchanged
  V1.1.2 service path and preserves each generation id, input hash and validation
  result.
- Adds bounded bidirectional mesh-sample deviation, silhouettes, section
  residuals and a per-vertex heatmap. These are review diagnostics, not certified
  CAD metrology.
- Adds a read-only four-pane frontend with synchronized Source STEP,
  Reconstruction, Heatmap and parameter/deviation report views using one WebGL
  renderer for the three geometry panes.
- Hardens Windows audit-status persistence with unique temporary files, durable
  flush and bounded replace retries after a reproduced transient sharing lock.
- Resolves the periodic zero-angle gauge by a recorded one-pitch axial phase
  search; translation, scale fitting and free ICP remain disabled.
- Deduplicates identical active/completed STEP audits by source SHA and disables
  repeated frontend submission while an audit is queued or running.
- Marks restart-orphaned work explicitly and loads a reused PASS manifest
  immediately instead of leaving the reconstruction panes empty.
- Keeps customer STEP and generated heavy geometry outside source control.
- R8 adds a separately labeled `v1.1.6_adaptive_review_extension_r1` that uses
  5 to 9 source-driven stations without changing the frozen V1.1.2 preset path.
- R8 replaces global nearest-mesh comparison with explicit role-corresponding
  directional distributions and excludes unsupported keyway, auxiliary-hole,
  bottom-boss and unresolved-closure geometry from metric contribution.
- R8 emits a generation-bound Geometric Manifest with translucent sampled
  surfaces, true UV curves and an explicitly millimetric directional heatmap.
- Post-review R9 evidence corrects the numerical primitive from nearest
  centroid/vertex samples to exact point-to-triangle distances on the retained
  tessellation, requires topology and periodic-role scope coverage, and keeps
  completed rejected audits reusable without making them promotable.
- Post-review R10 fixes symmetric metrics to use equal independent directional
  weights, binds blade comparisons per periodic instance, reports unresolved
  LE/TE ownership as `PARTIAL_REVIEW`, rejects main-field reuse for splitters,
  and binds audit cache reuse to the completed manifest digest.
- Post-review R11 moves periodic instance assignment after global phase
  alignment, keeps main/splitter lattice identity independent, closes the
  status/manifest/source cache-identity chain, and makes all comparison-pane
  artifact requests and status polling abortable.
- Post-review R12 binds the assignment to authenticated population lattice
  indexes, requires exact per-population count/membership/index sets, and
  excludes partially owned LE/TE evidence only from the incomplete population
  instead of applying a complete-family shift modulo a smaller subset.
- Final audit `step-audit-7ba8024c586d41fc` completed all workflow stages in
  `740.961 s` with V1.1.2 geometry validation `PASS`. Comparison scope remains
  `PARTIAL_REVIEW` because LE/TE ownership is unresolved; mapping remains a
  rejected review candidate, so the result is review-only, non-promotable and
  acceptance remains unevaluated.
- R13.2 keeps V1.1.2 frozen while correcting adaptive root endpoint collapse by
  intersecting the metric S-Q footprint with the authenticated support domain
  and reparameterizing LE/TE root caps by arc length.
- R13.2 requires complete periodic hub-passage ownership across singleton area
  groups and inventories every reconstructed material surface in a per-surface
  comparison ledger. The spline-affected mounting bore remains explicitly
  `NOT_EVALUATED`.
- A geometry-only KS007G23B probe passes with `84` surfaces, all `13` root
  patches passing, no foldovers and zero triangle below `1e-8 mm^2`. Backend
  verification totals `339 passed, 1 skipped`; frontend totals `251 passed` and
  the production build check passes.
- R13.2 remains `review_only_not_promotable`: exact source PS/SS and LE/TE
  ownership, local unsupported-feature masks, browser pixel evidence and a
  fresh full R13.2 deviation audit remain open.
- R14.0 keeps V1.1.2 geometry and exact corresponding-surface metrics frozen
  while reusing triangle indexes, fusing exact queries, and running independent
  surface pairs with bounded parallel workers.
- R14.0 adds content-addressed per-surface deviation checkpoints and live-worker
  ownership heartbeats. A restart resumes only byte-identical source and
  reconstruction surface pairs; changed surfaces are recomputed.
- The retained R13.2 audit measured about 89 minutes in deviation versus about
  10 minutes across the three reconstruction stages. An eight-surface benchmark
  reduced 7.35 seconds serial to 4.98 seconds cold and 0.42 seconds warm with
  equal outputs.
- Fresh R14 audit `step-audit-058a9e65e2d341d3` completed `82/82` exact
  surface comparisons in about 74.4 minutes total. Its complete deviation and
  artifact stage took 3651.36 seconds versus 5363.62 seconds for R13.2, a 31.9%
  reduction, and wrote 82 exact checkpoints totalling 40,455,892 bytes.
- R14 remains performance evidence only. Its process status is `PASS`, while
  its axis-first geometry status is `REJECTED`, non-promotable. Visual review
  found a canonical-axis polarity defect that reverses the V1.1.2 support
  endpoint semantics and produces an oversized hub outer wall; R15 owns that
  correction.
- R15.3 defines canonical positive Z from the large-radius backplate toward the
  small-radius eye, carries named support endpoints through mapping and hub
  closure, and limits the outer closure wall to the measured 5.75 mm bottom
  thickness. Source, reconstruction and heatmap now share one canonical
  camera, while process completion and geometry acceptance are reported
  separately.
- Fresh audit `step-audit-e27b4c0e7c854c88` completed `82/82` exact surface
  comparisons in about 88.6 minutes. The 82-surface reconstruction visibly
  retains all 13 blades and no longer collapses behind an oversized cylinder.
  It remains correctly `REJECTED`, review-only and non-promotable because
  camber, pose, normal-thickness, edge-curve and periodicity mapping gates fail
  and exact periodic collision is still unknown.

Spec, plan and evidence:

```text
docs/superpowers/specs/2026-07-13-impeller-v1-1-6-step-reconstruction-audit-spec.md
docs/superpowers/plans/2026-07-13-impeller-v1-1-6-step-reconstruction-audit-implementation.md
docs/evidence/2026-07-13-impeller-v1-1-6-step-reconstruction-audit/README.md
docs/evidence/2026-07-16-impeller-v1-1-6-r8-verification-evidence.md
docs/evidence/2026-07-17-impeller-v1-1-6-r13-semantic-change-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r13-insight-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r13-verification-evidence.md
docs/superpowers/plans/2026-07-17-impeller-v1-1-6-r14-deviation-performance-hardening.md
docs/evidence/2026-07-17-impeller-v1-1-6-r14-semantic-change-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r14-insight-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r14-verification-evidence.md
docs/superpowers/plans/2026-07-17-impeller-v1-1-6-r15-axial-semantic-reconstruction-repair.md
docs/evidence/2026-07-17-impeller-v1-1-6-r15-semantic-change-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r15-insight-log.md
docs/evidence/2026-07-17-impeller-v1-1-6-r15-verification-evidence.md
```

## How To Run A Specific Version

In Python tests or scripts:

```python
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("runs"))
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_7")
run = service.instantiate(engine.engine_id, {})
manifest = run.manifest
```

Change `preset_id` to one of the version-specific ids above to select earlier versions.

## Compatibility Rule

Do not mutate old version folders to express new semantics. If a natural-language loss record changes the meaning of a feature, create a new DSL version or an explicit patch file so earlier research evidence remains reproducible.
