# Impeller V1.1.6 STEP Reconstruction Audit Implementation Plan

Implementation status: completed and verified on 2026-07-13. Exact commands,
measured results and limitations are recorded in the milestone evidence folder.

## Goal

Implement the approved V1.1.6 STEP authority, current-rule reconstruction and
deviation-review workflow without changing V1.1.2 construction mathematics.

## Baseline And Change Boundary

- Worktree: `impeller-ks007g23b-preset`.
- Branch: `feature/ks007g23b-preset`.
- Runtime/audit contract advances to `1.1.6`.
- Canonical geometry remains `1.1.2`.
- Current dirty KS007G23B preset, confidence, drawing and evidence changes are
  part of the same pending milestone and must be preserved.
- Source authority is the uploaded STEP; generated V1.1 geometry remains
  review-grade reconstruction.

## Task 1: Contract, Version And Test Fixtures

1. Add V1.1.6 constants for audit contract id, stages, status and stable failure
   reasons.
2. Add a synthetic single-solid periodic impeller STEP fixture generator under
   tests. Do not commit the customer STEP.
3. Add a test-only environment hook for optional KS007G23B local acceptance using
   `KS007G23B_STEP_PATH`.
4. Add runtime/manifest assertions that V1.1.6 does not change canonical geometry
   version `1.1.2`.

Expected files:

```text
src/part_rule_synthesis/impeller_v11_6_step_audit.py
tests/step_fixtures.py
tests/test_impeller_v11_6_step_audit.py
```

First verification:

```text
python -m pytest tests/test_impeller_v11_6_step_audit.py -q
```

## Task 2: Bounded STEP Ingestion And Source Manifest

1. Implement streamed raw-body ingestion with filename sanitization, 100 MiB
   limit, SHA-256 and atomic storage below the service run root.
2. Validate STEP header/schema before OCCT loading.
3. Load the source with OCP/OCCT and reject no-solid, multi-solid, face-limit and
   unavailable-kernel cases explicitly.
4. Record source topology, units, area, volume, centroid, bounds, analytic surface
   inventory and B-spline summaries.
5. Tessellate source faces at a recorded tolerance and LOD triangle bound for
   display only; retain B-Rep as authority.

Tests:

- valid synthetic STEP ingestion;
- extension-independent header validation;
- path traversal filename ignored;
- size, no-solid, multi-solid and parse failures;
- deterministic source hash and topology manifest;
- uploaded file remains outside the repository.

## Task 3: Axis, Periodicity And Semantic Classification

1. Resolve the source rotation axis from coaxial analytic surfaces and periodic
   evidence; record every candidate score.
2. Build face adjacency and rotational-signature groups.
3. Detect main and splitter periodic populations independently.
4. Classify hub, shroud/open tip, blade-side pairs, LE/TE closures, root/tip
   attachments, bore, holes and other material.
5. Keep orientation-neutral `blade_side_a/b` labels when pressure/suction evidence
   is insufficient.
6. Emit per-face confidence, source entity ids and alternative classification
   reasons.

Tests:

- axis selection is invariant under rigid source transforms;
- N-fold periodicity closes at 360 degrees;
- no-splitter population maps to `N + 0`;
- ambiguous axis and missing periodic population fail deterministically;
- semantic faces preserve source ids and adjacency evidence.

Optional local gate:

```text
$env:KS007G23B_STEP_PATH='<local path>/KS007G23B.stp'
python -m pytest tests/test_impeller_v11_6_ks007g23b_local.py -q
```

## Task 4: Existing-Rule Parameter Extraction And Fit

1. Build source meridional hub and tip/shroud target curves in the canonical frame.
2. Fit the current six-control-point support curves using the current degree/knot
   policy, constrained endpoints, monotonicity and material ordering.
3. Establish a physical source `(s,h)` domain and extract five source blade loops
   for each blade population.
4. Fit only current V1.1.2 fields and scalars: skeleton turn/bow, pose, thickness,
   cap roundness, root lift/width and attachment mode.
5. Preserve exact source measurements separately from fitted values.
6. Report measurement confidence, semantic mapping confidence and reconstruction
   residual as separate fields.
7. List unsupported holes, spline, cuts and local faces without proxy parameters.

Tests:

- fitted support curves pass through constrained endpoints;
- fitting sampled points as unprocessed poles is forbidden;
- fit is deterministic from the same source hash and options;
- bounds and material-domain constraints are enforced;
- source measurement, mapped value and fidelity fields are all present;
- unsupported features cannot mutate unrelated V1.1 inputs.

## Task 5: Staged Current-Constructor Reconstruction

1. Compile an in-memory V1.1.2 runtime payload from fitted current parameters.
2. Run `hub_support`, `blade_surfaces` and `edge_closures` through the existing
   service path; do not introduce a STEP-specific geometry builder.
3. Retain generation ids, validation reports and timings for every stage.
4. Generate the final source-independent V1.1 surface graph and review STL.
5. Mark a validation failure as reconstruction evidence rather than falling back
   to proxy geometry.

Tests:

- monkeypatch/contract tests prove the existing V1.1 constructor is called;
- geometry rule modules are unchanged;
- every stage has a generation id and immutable input hash;
- failed final validation does not claim a completed reconstruction;
- historical presets bypass the audit pipeline.

## Task 6: Alignment, Deviation And Artifacts

1. Apply only the recorded source-to-canonical rigid transform for primary
   comparison; do not scale or primary-ICP-fit the source.
2. Build bounded source and reconstruction comparison meshes with recorded chord
   and angular tolerances.
3. Compute bidirectional nearest-surface distance, symmetric Chamfer, normals,
   silhouette, section, area/volume and centroid deltas where applicable.
4. Aggregate global and semantic-role metrics.
5. Generate a reconstruction heatmap mesh with unsmoothed per-vertex millimetre
   errors and P95 clipping metadata.
6. Hash every generated artifact and label its fidelity.

Expected files:

```text
src/part_rule_synthesis/impeller_v11_6_deviation.py
tests/test_impeller_v11_6_deviation.py
```

Tests:

- identical geometry gives near-zero bidirectional error;
- rigidly transformed source aligns without scale change;
- a known offset gives the expected distance;
- semantic aggregation covers every classified comparison triangle;
- open geometry does not claim signed distance;
- heatmap scalar values match numeric report values.

## Task 7: Audit Service And HTTP API

1. Add an audit store below the existing service run root and a single background
   worker with bounded queue length.
2. Add raw STEP upload, status, final manifest and artifact endpoints from the spec.
3. Persist stage transitions atomically so a browser reload can recover progress.
4. Return structured failure details and `202` for accepted work.
5. Prevent audit ids, filenames and artifact names from escaping the run root.
6. Add cache headers keyed by audit id and artifact hash.

Expected files to change:

```text
src/part_rule_synthesis/api.py
src/part_rule_synthesis/service.py
src/part_rule_synthesis/impeller_v11_6_step_audit.py
tests/test_impeller_v11_6_step_api.py
```

Verification:

```text
python -m pytest \
  tests/test_impeller_v11_6_step_audit.py \
  tests/test_impeller_v11_6_deviation.py \
  tests/test_impeller_v11_6_step_api.py -q
```

## Task 8: Four-Pane Frontend Workspace

1. Add `STEP Reconstruction` to the read-only workspace navigation.
2. Add `.stp/.step` file selection, upload, stage polling and persistent failure
   presentation.
3. Add a stable 2x2 review layout for Source, Reconstruction, Heatmap and Report.
4. Use one Three.js renderer/context with three scissor viewports and matched
   source/reconstruction/heatmap cameras.
5. Reuse STL loading for neutral source/reconstruction meshes and add a bounded
   indexed heatmap geometry loader with per-vertex colors.
6. Synchronize orbit, zoom and canonical preset views across geometry panes.
7. Add heatmap legend, semantic-role filter and point readout.
8. Render the report columns for source measurement, mapping, reconstructed value,
   delta, confidence layers and residual.
9. Keep existing CAD Review and Engineering Drawing unchanged.

Expected files:

```text
frontend/src/stepReconstructionModel.js
frontend/src/stepReconstructionModel.test.js
frontend/src/components/StepReconstructionWorkspace.js
frontend/src/components/StepComparisonScene.js
frontend/src/components/StepReconstructionWorkspace.test.js
frontend/src/App.js
frontend/src/apiClient.js
frontend/src/simulationViewModel.js
frontend/src/styles.css
```

Frontend acceptance tests:

- one live renderer/context for three geometry panes;
- source/reconstruction/heatmap camera synchronization;
- no UV lines in source and reconstruction panes;
- heatmap legend uses report min/P95/max values;
- progress and every terminal failure render without a blank page;
- unsupported feature rows remain visible;
- existing two workspaces still render.

Verification:

```text
cd frontend
npm.cmd test
npm.cmd run build
```

## Task 9: KS007G23B Acceptance And Evidence

1. Run the local KS007G23B STEP through the complete HTTP workflow.
2. Verify source facts: one solid, 240 faces, 666 edges, 433 vertices, R51.6,
   36.5 mm axial extent, R7.9 bore, three R2 holes and 13-fold pitch.
3. Capture all stage durations, fitted values, fit residuals and final deviation
   metrics.
4. Inspect Source, Reconstruction and Heatmap with synchronized Top, Meridional
   and isometric cameras.
5. Confirm that the report distinguishes exact source evidence from V1.1 mapping
   and reconstruction fidelity.
6. Record unsupported spline, holes, balancing features and source B-spline faces.
7. Keep the customer STEP and generated heavy artifacts outside git.

Evidence outputs:

```text
docs/evidence/2026-07-13-impeller-v1-1-6-step-reconstruction-audit/
  README.md
  verification.txt
  ks007g23b-audit-summary.json
  known-limitations.md
```

Only compact, redacted evidence is committed.

## Task 10: Regression And Release Gate

Run the narrow tests while iterating, then complete:

```text
python -m pytest tests/test_impeller_v11_6_step_audit.py -q
python -m pytest tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_step_api.py -q
python -m pytest tests/test_impeller_v11_resources.py tests/test_ks007g23b_preset.py -q
python -m pytest tests/test_impeller_v11_5_engineering_drawing.py tests/test_impeller_v11_5_review_summary.py -q
cd frontend
npm.cmd test
npm.cmd run build
```

Then verify:

- HTTP upload returns quickly and progresses through every stage;
- source/reconstruction artifacts have distinct fidelity labels;
- no generated file appears in git status;
- `git diff --check` passes;
- exact commands, counts, versions and known failures are written into evidence;
- repository status explicitly inventories the pre-existing KS007G23B changes.

## Commit Sequence

Use small contract-focused commits when implementation begins:

1. `test: define v1.1.6 STEP audit contracts`
2. `feat: ingest and classify STEP impeller sources`
3. `feat: fit STEP evidence to existing v1.1 parameters`
4. `feat: measure reconstruction deviation`
5. `feat: expose STEP reconstruction audit API`
6. `feat: add four-pane STEP reconstruction review`
7. `docs: record v1.1.6 acceptance evidence`

Do not commit or push during plan authoring. Do not merge V1.2 geometry-rule work
into this V1.1.6 branch.
