# Impeller V1.1.3 Graphical Parameter Inspection Evidence

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

Hardening commits:

```text
31e780e fix: harden v1.1.3 inspection contract
bb2e7f3 fix: complete v1.1.3 inspection hardening
69a8f71 fix: finalize inspection smoke evidence
```

## Version Contract

```text
runtime_release_version = 1.1.3
parameter_inspection_contract_version = 1.1.3
geometry_version = 1.1
geometry_patch_version = 1.1.2
canonical_payload_version = 1.1.2
```

V1.1.3 changes runtime and read-only inspection behavior only. V1.1.2 geometry construction and canonical semantics remain authoritative.

## Independently Reviewed Findings Addressed

- Provenance now hashes all visible/inspectable source evidence, including hub/shroud surfaces and loop/control data. Only explicitly hidden, reference-only helper UV sampling is exempt, and hash input is non-self-referential.
- Each S-Q loop exposes source coordinates, physical coordinate units, a geometry-derived streamwise metric scale, and metric display points. Equal-aspect display labels both axes in millimetres.
- A pure relationship-aware selection reducer synchronizes blade, station, segment, control, and face-family state across tabs and views.
- Backend and frontend validators deeply reject malformed containers, nested records, unequal surface sets, invalid references, duplicate/foreign controls, and nonclosed loops through explicit failure states.
- Default key annotations cover core dimension/population/pose/profile evidence in 3D, Top, and Meridional. Meridional support geometry is rendered only when supplied by the contract.
- Backend control-point records have authoritative stable IDs; frontend code consumes them without index-derived IDs.
- The preset summary and workspace badge report runtime/inspection 1.1.3 and canonical/geometry 1.1.2.

## Fresh Post-Hardening Backend Checks

Focused provenance, physical display, and stable-control subset:

```text
5 passed, 5 deselected in 113.78s (0:01:53)
```

Resolved dimension/population/pose evidence:

```text
1 passed in 6.47s
```

Corrected loop orientation and nonclosed-loop rejection:

```text
2 passed in 26.64s
```

The requested combined V1.1.3/service/acceptance command was started after the hardening commits but interrupted before pytest produced a final result. It is not reported as passing.

## Historical Backend Matrix

The following fresh results were recorded by Task 7 before the hardening commits and were not rerun under the user's final instruction:

```text
V1.1.3 contract/service group: 15 passed in 483.00s (0:08:02)
V1.1.2 regression group:      24 passed in 244.39s (0:04:04)
V1.1 regression group:        37 passed in 11.67s
surface/export group:         34 passed in 348.44s (0:05:48)
geometry/export group:        55 passed in 4.02s
historical matrix total:     165 passed, 0 failed
API acceptance:               38 passed in 431.78s (0:07:11)
```

## Fresh Frontend Verification

Focused command:

```powershell
node --test src/parameterInspectionModel.test.js src/inspectionSceneModel.test.js src/components/ParameterInspectionWorkspace.test.js src/components/InspectionScene.test.js src/components/SectionLoopInspectionView.test.js
```

```text
tests 60
suites 6
pass 60
fail 0
cancelled 0
skipped 0
todo 0
duration_ms 187.0399
```

Full command: `cd frontend; npm.cmd test`

```text
tests 185
suites 17
pass 185
fail 0
cancelled 0
skipped 0
todo 0
duration_ms 269.8592
```

## Browser And Pixel Acceptance

The final bundled Node/Playwright smoke result was:

```text
parameter inspection desktop 3D: PASS
parameter inspection desktop Quad: PASS
narrow toolbar bounds: {"workspaceBox":{"x":14,"y":502.09375,"width":740,"height":730.1875},"annotationBox":{"x":91.59375,"y":647.09375,"width":653.40625,"height":30},"sectionPaneBox":{"x":15,"y":679.65625,"width":738,"height":551.625}}
parameter inspection narrow S-Q: PASS
inspection renderer count: 1
inspection context count: 1
inspection scene surface count: 101
browser device pixel ratio: 1
inspection canvas non-background ratio: 0.1979
```

Duration: `143.3s`. Pixel threshold: `nonBackgroundRatio >= 0.05`.

The smoke exercised cross-blade and span-station selection, the `All` annotation level, measured renderer/context construction, desktop 3D and Quad, and narrow S-Q bounds. It was rerun while renderer instrumentation and narrow annotation separation were corrected; the latest run has no failure.

Refreshed and visually inspected artifacts:

```text
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-3d.png
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-quad.png
docs/evidence/assets/v1.1.3-parameter-inspection/narrow-s-q.png
```

Desktop 3D is nonblank and framed with synchronized selected-surface highlighting. Quad contains four distinct panes with unobscured controls. Narrow S-Q keeps the annotation and continuity rails separate and inside the workspace.

## Final Services

Confirmed from this worktree after verification:

```text
backend  PID 31836  http://127.0.0.1:8061  /api/presets/impeller = HTTP 200
frontend PID 30920  http://127.0.0.1:5199  / = HTTP 200
```

## Residual Risk

- The full 165-test backend matrix is historical relative to the hardening commits; the post-hardening combined command was interrupted and has no final result.
- Browser smoke covers the active open preset in headless Chromium at device pixel ratio 1; backend contract tests provide broader preset coverage.
- Review-grade sampled geometry, sewn production CAD, solver-ready volume meshes, and manufacturing certification remain outside V1.1.3.
