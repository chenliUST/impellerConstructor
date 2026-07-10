# Task 7 Report: V1.1.3 Inspection Hardening And Evidence

## Status

Implementation and the verification scope requested on 2026-07-10 are complete. Fresh frontend tests and browser smoke pass. The full 165-test backend matrix is recorded as a pre-hardening result and was not rerun by final instruction; a post-hardening combined backend command was interrupted without a final result.

## Commits

```text
31e780e fix: harden v1.1.3 inspection contract
bb2e7f3 fix: complete v1.1.3 inspection hardening
69a8f71 fix: finalize inspection smoke evidence
```

## Implemented Findings

1. Generation provenance covers all source fields that affect visible/inspectable evidence. Manufactured hub/shroud roles are included; only explicit hidden reference-only helper UV sampling may be exempt. Derived inspection content and `generation_id` are excluded from hash input.
2. S-Q contracts retain normalized source values and expose units, deterministic geometry-derived `streamwise_metric_scale_mm`, and metric display points/controls. Equal-aspect display uses `S (mm)` and `Q (mm)`.
3. A pure reducer normalizes relational selection across blades, stations, loops, segments, controls, surface families, and tabs. Toolbar blade/station selectors and geometric/S-Q highlights are synchronized.
4. Backend and frontend perform deep contract validation, exact surface-set equality, bidirectional blade/station/loop checks, closure checks, and stable explicit failure rendering.
5. Default key annotations cover core resolved dimension, population, pose, and profile evidence in 3D, Top, and Meridional. Actual support profile/control geometry is rendered when present. The exact badge is `Resolved manifest | runtime 1.1.3 | geometry 1.1.2`.
6. Backend control points carry authoritative content-stable IDs and ownership. Frontend consumes those IDs directly, with uniqueness/ownership and reorder tests.
7. Preset summary versions are corrected and renderer instrumentation measures actual constructed renderers and contexts.

V1.1.2 geometry construction semantics were not changed.

## Test-Driven Coverage

Focused tests were added before implementation for visible hub/shroud and loop/control generation mutations, explicit hidden helper exemption, physical S-Q derivation, relational selection, malformed contracts, key annotations/badge, stable control IDs, and renderer/context instrumentation.

Fresh post-hardening backend focused results:

```text
provenance/units/control subset: 5 passed, 5 deselected in 113.78s (0:01:53)
resolved dimensions/pose:        1 passed in 6.47s
loop orientation/nonclosure:     2 passed in 26.64s
```

The combined command below was interrupted before a pytest summary and is not claimed green:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py tests/test_acceptance.py -q
```

Historical pre-hardening backend results retained from the prior Task 7 run:

```text
V1.1.3 contract/service: 15 passed in 483.00s (0:08:02)
V1.1.2 regressions:      24 passed in 244.39s (0:04:04)
V1.1 regressions:        37 passed in 11.67s
surface/export:          34 passed in 348.44s (0:05:48)
geometry/export:         55 passed in 4.02s
matrix total:           165 passed, 0 failed
API acceptance:          38 passed in 431.78s (0:07:11)
```

Fresh focused frontend command:

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

Fresh full frontend command: `cd frontend; npm.cmd test`

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

## Browser Smoke

Latest exact result:

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

Duration: `143.3s`; required non-background ratio: `>= 0.05`. There is no latest smoke failure. Reruns were required while actual renderer/context construction instrumentation and narrow S-Q annotation separation were corrected.

The final smoke covers cross-blade and span-station selection, `All` annotations, desktop 3D/Quad, narrow S-Q bounds, and actual renderer/context counts.

Refreshed evidence:

```text
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-3d.png
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-quad.png
docs/evidence/assets/v1.1.3-parameter-inspection/narrow-s-q.png
```

The three final images were visually inspected. No further visual iteration was performed after the user's stop instruction.

## Services

Confirmed after final verification:

```text
backend  PID 31836  http://127.0.0.1:8061  /api/presets/impeller = HTTP 200
frontend PID 30920  http://127.0.0.1:5199  / = HTTP 200
```

Both listeners are running from this worktree. Unrelated pytest processes in another worktree were left untouched.

## Evidence Files

```text
docs/evidence/2026-07-10-impeller-v1-1-3-semantic-change-log.md
docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md
docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md
docs/version-history.md
```

## Residual Risk

- The full backend matrix is not fresh relative to `31e780e`/`bb2e7f3`; only the listed focused backend checks are fresh after hardening.
- The interrupted post-hardening combined backend command has no pass/fail summary.
- Browser smoke covers one open preset and DPR 1; broader preset behavior remains primarily contract-test evidence.
- Geometry remains review-grade sampled V1.1.2 geometry, outside production CAD, solver mesh, and manufacturing certification claims.

## Final Review Closure

The last two review findings were resolved in `4cf26c7`:

- explicit noninspectable helper surfaces are excluded consistently from scene input, camera bounds, picking, and annotations;
- visible unowned hub/shroud support selection clears blade-owned dependent identities and retains a deterministic S-Q fallback.

Fresh final verification:

```text
contract file:             11 passed in 453.85s
service groups 1-4:         4 + 4 + 4 + 4 passed
service group 3:            4 passed in 107.04s
service group 4:            4 passed in 377.90s
frontend:                  188 passed, 0 failed
browser 3D/Quad/narrow S-Q: PASS
scene surfaces:            101
non-background ratio:      0.1986
renderer lifecycle:        created 3, live 1
context lifecycle:         created 3, live 1
```

The browser services were refreshed from the final worktree before the last smoke run. The historical 165-test geometry matrix is not relabeled as post-hardening evidence.

## Monochrome Inspection Follow-Up

The 2026-07-11 frontend-only follow-up removes UV and leader clutter and adds direct parameter-to-surface selection. Verification: `187` frontend tests passed; desktop 3D, Quad, and narrow S-Q browser smoke passed; `101` surfaces rendered; UV overlay and leader counts were both zero; non-background ratio was `0.1595`. The screenshots were visually inspected after regeneration.
