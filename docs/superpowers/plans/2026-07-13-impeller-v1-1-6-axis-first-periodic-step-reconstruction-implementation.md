# Impeller V1.1.6 Axis-First Periodic STEP Reconstruction Implementation Plan

## Goal

Replace the V1.1.6 generic global-envelope STEP mapping with the approved
axis-first, support-surface-first, section-driven reconstruction algorithm while
preserving the V1.1.2 constructor and the existing V1.1.6 upload/review workflow.

The implementation is complete only when KS007G23B reconstructs as an open
`13 + 0` periodic wheel with measured blade thickness, no false material
shroud, feature-level deviation evidence and a demonstrable improvement over
the recorded generic baseline.

## Governing Spec

Implement:

```text
docs/superpowers/specs/
  2026-07-13-impeller-v1-1-6-axis-first-periodic-step-reconstruction-spec.md
```

The existing V1.1.6 audit spec remains authoritative for upload bounds, API,
queue/persistence behavior, four-pane workflow and evidence retention. Where the
old generic parameter-extraction method conflicts with the new spec, the new
axis-first algorithm governs.

## Baseline And Change Boundary

- Target repository: `impellerConstructor` worktree
  `impeller-ks007g23b-preset`.
- Target branch: `feature/ks007g23b-preset`.
- Runtime workflow version: `1.1.6`.
- Canonical geometry version: `1.1.2`, unchanged.
- Source authority: uploaded STEP B-Rep queried through OCCT.
- Reconstruction authority: generation-bound V1.1.2 surface graph.
- Maturity: `engineering-preview` reverse-engineering audit.

The current worktree contains uncommitted V1.1.5, KS007G23B and V1.1.6 work,
including the files that this overhaul must edit. Before implementation, create
an intentional checkpoint of that baseline or move the overhaul to a clean
worktree based on a commit containing it. Do not mix the old implementation and
the new algorithm into an unauditable single commit.

## Expected Module Boundary

Keep `impeller_v11_6_step_audit.py` as workflow orchestration and persistence.
Move geometric responsibilities into focused modules:

```text
src/part_rule_synthesis/
  impeller_v11_6_source_frame.py
  impeller_v11_6_support_recovery.py
  impeller_v11_6_periodic_blades.py
  impeller_v11_6_section_recovery.py
  impeller_v11_6_v112_mapping.py
```

Do not create a parallel constructor. These modules measure and map source
geometry; `RuleSynthesisService` remains the only reconstruction entrypoint.

## Task 0: Checkpoint And Baseline Evidence

1. Run the mandatory repository checks and inventory all current modifications.
2. Review the current V1.1.6 spec, plan, evidence and known limitations.
3. Run the current backend, frontend and KS007G23B audit commands before any
   algorithm edit.
4. Preserve the recorded baseline:

```text
bidirectional RMS          2.110076 mm
bidirectional P95          4.819965 mm
top silhouette Hausdorff   5.254113 mm
meridional Hausdorff      10.168447 mm
```

5. Checkpoint the existing V1.1.6 implementation separately. External source
   STEP/PDF files remain local unless the evidence policy and user explicitly
   authorize retention.

Required commands:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
python -m pytest tests/test_impeller_v11_6_step_api.py `
  tests/test_impeller_v11_6_step_audit.py `
  tests/test_impeller_v11_6_deviation.py -q
cd frontend
npm.cmd test
npm.cmd run build
```

Exit gate:

- baseline commit/hash and dirty-file inventory are recorded;
- tests and current known failures are recorded without claiming the old
  geometry is accepted;
- implementation starts from a recoverable checkpoint.

## Task 1: Algorithm Revision And Contract Tests

Add the new algorithm revision before implementing geometry so old cached PASS
audits cannot mask incomplete behavior.

1. Change the V1.1.6 implementation revision to a stable value such as
   `axis_first_section_periodic_r3`.
2. Add `axis_first_section_reconstruction` to the final manifest schema.
3. Add the new stable failure reasons from the spec.
4. Extend cache compatibility so only the same algorithm revision can reuse an
   active or PASS audit.
5. Preserve upload, restart recovery, status and artifact endpoint behavior.

First failing tests:

```text
tests/test_impeller_v11_6_axis_first_contract.py
tests/test_impeller_v11_6_step_api.py
```

Test cases:

- previous generic PASS manifest is not reused;
- same-source/same-revision PASS is reused;
- final manifest requires source ids, tolerances, frame and residuals;
- every new failure reason serializes through status and HTTP detail;
- canonical geometry version remains `1.1.2`.

Suggested commit:

```text
feat: version axis-first STEP reconstruction contract
```

## Task 2: Deterministic Source Fixtures

Build small OCCT/CadQuery fixtures that make each algorithm claim independently
testable. Do not use screen captures or the private KS007G23B file as the only
test oracle.

Add fixtures for:

1. open wheel, one blade population, known variable thickness;
2. open wheel with main and splitter populations and a non-half-pitch splitter;
3. closed wheel with finite-thickness shroud and blade-to-shroud attachment;
4. open wheel with a large non-periodic top/bottom face that must not be called a
   shroud;
5. rotated and translated variants of the same source;
6. root blend with known lift and attachment width;
7. intentionally ambiguous axis and intentionally open section loop failures.

Expected files:

```text
tests/step_fixtures.py
tests/test_impeller_v11_6_axis_first_fixtures.py
```

Each fixture records expected axis, profiles, count, phase, section thickness
and topology. The fixture generator must be deterministic and small enough for
routine CI.

Suggested commit:

```text
test: add deterministic STEP reconstruction fixtures
```

## Task 3: Canonical Axis And Coarse Topology Partition

Implement `impeller_v11_6_source_frame.py`.

1. Extract axis candidates from cylinders, cones, circles and revolved faces.
2. Normalize line direction before clustering; compare both sign hypotheses.
3. Cluster by angular and line-distance tolerances.
4. Score analytic area, feature count and periodic closure independently.
5. Return the rigid source-to-canonical transform with no scale or primary ICP.
6. Compute face signatures under axis rotations and partition periodic from
   non-periodic connected components.
7. Persist every candidate, score, residual and rejected alternative.

First failing tests:

```text
tests/test_impeller_v11_6_source_frame.py
```

Acceptance cases:

- transformed copies recover the same canonical frame and semantic signatures;
- bore and auxiliary holes do not create a competing winning axis;
- opposite axis directions resolve deterministically;
- equivalent axis evidence fails with `v116_axis_consensus_ambiguous`;
- analytic fixture axis meets the spec residual gate.

Suggested commit:

```text
feat: recover STEP rotation frame from analytic consensus
```

## Task 4: Hub And Tip/Shroud Support Recovery

Implement `impeller_v11_6_support_recovery.py` and remove the generic
`_envelope_profile(... quantile=...)` path from promoted reconstruction.

### Hub work

1. Select non-periodic, flowpath-adjacent hub candidate faces.
2. Exclude periodic blade faces, root blends, holes and local edge treatments.
3. Query B-Rep points/normals and reduce them into weighted `(R,Z)` evidence.
4. Fit the current six-control clamped cubic profile by robust constrained least
   squares with endpoint, order and material-domain constraints.
5. Report orthogonal RMS, P95, maximum residual and rejected samples.

### Tip/shroud work

1. Detect per-blade tip-cap candidates and their shared adjacency edge loops
   with periodic blade side/edge faces; do not require topological free edges on
   a fused source solid.
2. Fit an axisymmetric non-material tip reference from those repeated cap loops.
3. Require paired material faces, circumferential closure, finite thickness and
   repeated tip attachment before classifying a closed shroud.
4. Reject ambiguous topology instead of defaulting to closed.
5. Emit explicit `material`, display and export policy metadata.

First failing tests:

```text
tests/test_impeller_v11_6_support_recovery.py
tests/test_impeller_v11_6_shroud_topology.py
```

Required assertions:

- support fit is invariant to tessellation density;
- open fixture has `material=false` tip reference and no material shroud;
- large planar/revolved decoy face cannot trigger closed topology;
- closed fixture recovers inner and outer shroud evidence plus thickness;
- hub/tip profiles satisfy ordering and residual gates;
- no fallback to radial quantile profiles occurs on a promoted PASS path.

Suggested commit:

```text
feat: recover hub and tip supports from STEP topology
```

## Task 5: Periodic Populations And Representative Blades

Implement `impeller_v11_6_periodic_blades.py`.

1. Build connected blade-related face components from periodic signatures and
   adjacency, rather than grouping isolated equal-area faces.
2. Estimate count, pitch, phase and closure residual for each population.
3. Classify main and splitter by streamwise extent, inlet location and radial/
   axial support range.
4. Support `N + 0` without fabricating a splitter population.
5. Measure splitter phase; report its passage-bisector deviation.
6. Select the population medoid after cyclic alignment.
7. Persist source component ids and the transform for every periodic instance.

First failing tests:

```text
tests/test_impeller_v11_6_periodic_blades.py
```

Required assertions:

- single-family fixture resolves `N + 0`;
- two-family fixture resolves independent counts and measured phase;
- a shorter splitter cannot be merged into main because face areas overlap;
- representative selection is invariant to source face enumeration order;
- cyclic closure and collision checks are measurable.

Suggested commit:

```text
feat: recover periodic blade populations and medoids
```

## Task 6: Adaptive Span Surfaces And Exact Section Loops

Implement the support correspondence and sectioning part of
`impeller_v11_6_section_recovery.py`.

1. Solve a monotone hub-to-tip meridional correspondence.
2. Construct ordered intermediate revolve surfaces in the meridional domain.
3. Measure active-root and active-tip boundaries before selecting blade-body
   stations.
4. Start with five stations and refine to at most nine from measured camber,
   thickness, twist, curvature and correspondence residuals.
5. Intersect the complete fused source solid with each surface using OCCT.
6. Filter section edges by representative-population source-face provenance and
   the expected angular sector.
7. Order and heal section edges within source tolerance.
8. Select one closed contour in the expected population sector.
9. Persist 3D and local `(S,Q)` curves, source ids, orientation and closure data.

First failing tests:

```text
tests/test_impeller_v11_6_span_surfaces.py
tests/test_impeller_v11_6_section_loops.py
```

Required assertions:

- span surfaces are ordered and do not cross;
- high-twist fixture refines beyond five stations while a simple fixture does
  not;
- every accepted loop is closed and self-intersection free;
- rotated source produces identical canonical loops;
- reversing one loop is detected and corrected by explicit orientation scoring;
- a 180-degree tangent flip fails with its stable reason;
- source section records are actual intersections, not summaries of preset
  defaults.

Suggested commit:

```text
feat: intersect adaptive STEP blade section lattice
```

## Task 7: Loop Decomposition, Thickness And Attachments

Complete `impeller_v11_6_section_recovery.py`.

1. Identify side/edge landmarks from source face adjacency, then curvature and
   streamwise extrema.
2. Fit four NURBS curve segments per loop and record independent residuals.
3. Build a smooth camber correspondence and measure thickness along its local
   normal.
4. Prohibit index-to-index and radial-distance thickness shortcuts.
5. Recover leading/trailing source spline shape and sag as measurement targets;
   do not impose a semicircle and do not add a hidden direct-curve mode to the
   frozen V1.1.2 constructor.
6. Track landmarks and parameters consistently across all span stations.
7. Recover hub root footprint, retained blade boundary, local span direction,
   root lift and attachment width.
8. Reuse the attachment measurement algorithm with reversed material side for a
   closed shroud.

First failing tests:

```text
tests/test_impeller_v11_6_loop_decomposition.py
tests/test_impeller_v11_6_thickness_field.py
tests/test_impeller_v11_6_attachment_measurement.py
```

Required assertions:

- measured thickness reproduces fixture values at `s=0.1/0.5/0.9`;
- all thickness samples are positive and inside the loop;
- side correspondence remains monotone through high curvature;
- edge endpoints, tangents and source curvature are finite and consistently
  oriented;
- first blade-body loop lies above the source root blend;
- root and closed-shroud lift/width are measured rather than copied from preset
  defaults.

Suggested commit:

```text
feat: measure STEP loop thickness and blade attachments
```

## Task 8: Bounded V1.1.2 Mapping

Implement `impeller_v11_6_v112_mapping.py` and route
`extract_v11_parameters(...)` through it.

1. Convert the 5 to 9 measurement stations to the canonical V1.1.2 five-station
   domain with a bounded least-squares objective.
2. Keep independent objective terms for supports, camber, pose, normal thickness,
   edge curves, root/tip offsets, attachment and periodicity.
3. Apply DSL and material-domain bounds explicitly.
4. Store measured target, fitted value, weight and residual for every term.
5. Retain known-source values only as initial guesses or comparison evidence.
6. Fail the promoted path when the V1.1.2 representation exceeds a mandatory
   residual gate; do not invoke the old global seed.
7. Keep pressure/suction names orientation-neutral without flow evidence.

First failing tests:

```text
tests/test_impeller_v11_6_v112_mapping.py
```

Required assertions:

- source measurements, not source SHA defaults, determine the final payload;
- the same source and tolerances yield identical payload hashes;
- changing one measured thickness affects only documented coupled fields;
- five-station resampling residual is reported;
- mapping cannot add a V1.2-only parameter;
- geometry patch remains `1.1.2`.

Suggested commit:

```text
feat: fit measured STEP sections to canonical v1.1.2 payload
```

## Task 9: Representative Reconstruction And Pattern Invariants

Update `reconstruct_with_current_v11(...)` without creating a STEP-specific
constructor.

1. Instantiate the mapped payload through `RuleSynthesisService`.
2. Generate one representative main blade and optional splitter family through
   the current constructor contract.
3. Pattern surfaces using measured population count and phase.
4. Add source representative and population provenance to patterned surfaces.
5. For open topology, assert no material shroud surface exists.
6. Keep the open tip reference as construction metadata excluded from material
   mesh/export.
7. For closed topology, require finite shroud material and both hub/shroud
   attachments.
8. Run geometry validation and cyclic collision checks before deviation.

First failing tests:

```text
tests/test_impeller_v11_6_pattern_reconstruction.py
tests/test_impeller_v11_6_material_topology.py
```

Required assertions:

- open `N + 0` and main/splitter cases have exact instance counts;
- all repeated instances are rigid cyclic transforms of their representative;
- open reconstruction has zero material-shroud area;
- closed reconstruction has finite shroud thickness;
- no blade population collides after patterning;
- source and reconstruction surface provenance is complete.

Suggested commit:

```text
fix: reconstruct measured periodic blades without false shroud
```

## Task 10: Regional Deviation And Evidence Artifacts

Extend `impeller_v11_6_deviation.py` and the audit finalizer.

1. Build source/reconstruction semantic-region sample sets.
2. Compute bidirectional distance and comparable normal error per region.
3. Add per-station loop Hausdorff, camber and normal-thickness residuals.
4. Keep top and meridional silhouette metrics.
5. Make false material, invalid thickness and failed root gates terminal even if
   global RMS is low.
6. Emit the compact JSON artifacts defined by the spec with hashes and units.
7. Record tessellation/projection tolerance on every sampled metric.

First failing tests:

```text
tests/test_impeller_v11_6_regional_deviation.py
tests/test_impeller_v11_6_axis_first_manifest.py
```

Required assertions:

- every reconstructed material region maps to a source role or explicit
  unsupported role;
- global metrics equal the weighted source data, not viewport geometry;
- thickness error cannot be hidden in an aggregate role;
- artifacts are deterministic and manifest hashes match files;
- previous generic manifest fails the new completeness check.

Suggested commit:

```text
feat: report feature-aware STEP reconstruction deviation
```

## Task 11: Four-Pane Inspection Update

Update the existing frontend rather than introducing a second reconstruction
workspace.

Expected files:

```text
frontend/src/components/StepReconstructionWorkspace.js
frontend/src/components/StepComparisonScene.js
frontend/src/stepReconstructionModel.js
frontend/src/styles.css
```

1. Add optional overlays for axis, hub evidence, tip/shroud evidence, span
   surfaces, representative blade and selected source loop.
2. Add population and span-station selectors in the report pane.
3. Show measured/fitted thickness, root and support residuals.
4. Add semantic-region heatmap filtering.
5. Hide an open tip reference by default; render it dashed and unshaded when
   explicitly enabled.
6. Render only actual shroud material as shaded geometry.
7. Preserve active-audit submission guards, immediate PASS manifest loading and
   error boundaries.
8. Keep the shared renderer and dispose GPU resources when switching audits.

Frontend tests:

```text
frontend/src/stepReconstructionModel.test.js
frontend/src/components/StepReconstructionWorkspace.test.js
frontend/src/components/StepComparisonScene.test.js
```

Visual gates:

- source, reconstruction and heatmap panes are nonblank;
- open reconstruction has no visible outer shroud;
- selected section loop aligns with its representative blade;
- thickness/root values agree with manifest evidence;
- repeated tab changes and audit reloads do not blank the page;
- desktop screenshots pass at device pixel ratio 2.

Suggested commit:

```text
feat: inspect axis-first STEP reconstruction evidence
```

## Task 12: KS007G23B End-To-End Acceptance

Run the local source through the complete HTTP path. Do not bypass upload or
inject known measurements after the source-analysis stage.

Required checks:

1. axis and frame pass the analytic residual gate;
2. topology resolves `open`, `13 + 0`, pitch approximately `27.692307692 deg`;
3. hub support and open tip reference report source entity evidence;
4. between 5 and 9 source section loops are exact intersection results;
5. local thickness is positive and passes the source residual gate;
6. root lift and attachment width are measured and nonzero;
7. reconstruction has no material shroud or outer-hub proxy;
8. all 13 blades derive from one representative source blade;
9. global and regional metrics satisfy the improvement gates;
10. all four panes render the same generation-bound audit.

Expected evidence directory:

```text
docs/evidence/2026-07-13-impeller-v1-1-6-axis-first-step-reconstruction/
  README.md
  verification.txt
  acceptance-summary.json
  known-limitations.md
  source-pane.png
  reconstruction-pane.png
  heatmap-pane.png
  report-pane.png
```

Do not commit the source STEP, full heatmap or large generated meshes unless the
user explicitly approves retention. The compact summary records their local
paths, sizes and hashes.

Suggested commit:

```text
docs: record axis-first STEP reconstruction evidence
```

## Task 13: Full Regression And Promotion Gate

Run narrow tests during each task, then complete all applicable repository gates.

Backend commands:

```powershell
python -m pytest `
  tests/test_impeller_v11_6_axis_first_contract.py `
  tests/test_impeller_v11_6_source_frame.py `
  tests/test_impeller_v11_6_support_recovery.py `
  tests/test_impeller_v11_6_shroud_topology.py `
  tests/test_impeller_v11_6_periodic_blades.py `
  tests/test_impeller_v11_6_span_surfaces.py `
  tests/test_impeller_v11_6_section_loops.py `
  tests/test_impeller_v11_6_loop_decomposition.py `
  tests/test_impeller_v11_6_thickness_field.py `
  tests/test_impeller_v11_6_attachment_measurement.py `
  tests/test_impeller_v11_6_v112_mapping.py `
  tests/test_impeller_v11_6_pattern_reconstruction.py `
  tests/test_impeller_v11_6_material_topology.py `
  tests/test_impeller_v11_6_regional_deviation.py `
  tests/test_impeller_v11_6_step_api.py -q

python -m pytest `
  tests/test_impeller_v11_resources.py `
  tests/test_impeller_v11_2_canonical_parameterization.py `
  tests/test_impeller_v11_5_engineering_drawing.py -q
```

Frontend commands:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

Repository checks:

```powershell
git diff --check
powershell -ExecutionPolicy Bypass -File scripts/verify_repository.ps1 -Mode Fast
git status --short
```

Promotion requires:

- all specified tests pass or every environment skip is justified;
- exact dependency/kernel versions and tolerances are in evidence;
- KS007G23B meets topology, thickness, no-false-shroud and improvement gates;
- open, closed and main/splitter fixtures all pass;
- existing preset geometry graph, mesh, topology and canonical payload hashes
  remain unchanged; additive manifest metadata is recorded separately;
- frontend build and nonblank visual inspection pass;
- remaining changes are committed intentionally or inventoried explicitly.

## Recommended Commit Sequence

1. `feat: version axis-first STEP reconstruction contract`
2. `test: add deterministic STEP reconstruction fixtures`
3. `feat: recover STEP rotation frame from analytic consensus`
4. `feat: recover hub and tip supports from STEP topology`
5. `feat: recover periodic blade populations and medoids`
6. `feat: intersect adaptive STEP blade section lattice`
7. `feat: measure STEP loop thickness and blade attachments`
8. `feat: fit measured STEP sections to canonical v1.1.2 payload`
9. `fix: reconstruct measured periodic blades without false shroud`
10. `feat: report feature-aware STEP reconstruction deviation`
11. `feat: inspect axis-first STEP reconstruction evidence`
12. `docs: record axis-first STEP reconstruction evidence`

Each commit includes the tests and compact evidence that certify its changed
contract. Do not mark the spec implemented or update milestone maturity before
Task 13 passes.
