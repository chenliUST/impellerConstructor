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

Plan and evidence:

```text
docs/superpowers/plans/2026-07-12-impeller-v1-1-5-engineering-drawing-fidelity-implementation.md
docs/evidence/2026-07-12-impeller-v1-1-5-semantic-change-log.md
docs/evidence/2026-07-12-impeller-v1-1-5-insight-log.md
docs/evidence/2026-07-12-impeller-v1-1-5-verification-evidence.md
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
