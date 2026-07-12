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

## Final Post-Review Verification

The final review fixes unify explicit inspectability across provenance, scene input, camera bounds, picking, and annotations, and make unowned hub/shroud support selection safe.

Fresh backend results after these fixes:

```text
parameter-inspection contract: 11 passed in 453.85s
service manifest group 1:       4 passed in 116.83s
service manifest group 2:       4 passed in 39.99s
service manifest group 3:       4 passed in 107.04s
service manifest group 4:       4 passed in 377.90s
fresh V1.1.3 total:            27 passed, 0 failed
```

Fresh frontend result: `188 passed, 0 failed`.

The final browser run passed desktop 3D, desktop Quad, and narrow S-Q with `101` inspectable scene surfaces and non-background ratio `0.1986`. Lifecycle instrumentation reported `createdRenderers=3`, `liveRenderers=1`, `createdContexts=3`, and `liveContexts=1` after the tested tab transitions; no concurrent context leak was observed.

The earlier 165-test geometry regression matrix and 38-test API acceptance suite remain historical relative to the final inspection-only hardening. V1.1.2 geometry construction code was not changed by the final fixes.

## Monochrome Parameter Selection Hardening

On 2026-07-11 the Parameter inspection presentation was simplified without changing the backend contract or V1.1.2 geometry:

- inspectable surfaces render white with black `EdgesGeometry` contours;
- selected parameter geometry renders black with white contours;
- UV overlays, triangle wireframe, colored support-profile overlays, and parameter leader lines are absent;
- native HTML parameter buttons replace the full-screen SVG label layer;
- clicking a parameter row exclusively highlights its generated target surfaces, and clicking it again clears the highlight.
- obsolete anchor projection, projection-error, and leader-layout code was removed after the labels became viewport-fixed controls.

Fresh frontend result: `175 passed, 0 failed`.

Fresh browser result:

```text
parameter inspection desktop 3D: PASS
parameter inspection desktop Quad: PASS
parameter inspection narrow S-Q: PASS
renderer lifecycle: created 3, live 1
context lifecycle: created 3, live 1
inspection scene surfaces: 101
visible UV overlays: 0
parameter leader elements: 0
canvas non-background ratio: 0.1595
```

The desktop 3D screenshot captures `Thickness Max` selected: the row is black/white inverted and the related blade geometry is black with white contours. The refreshed 3D, Quad, and narrow S-Q screenshots were visually inspected; no incoherent overlap or blank viewport was observed.

## Task 8 Engineering Acceptance Gate - BLOCKED (2026-07-11)

This is the latest Task 8 acceptance result and supersedes the older 3D/Quad smoke claims above for the integrated Top, Meridional, and S-Q + Blade workspace.

### Backend Regression Command

The exact brief command was run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py tests/test_impeller_v11_2_resources.py tests/test_impeller_v11_surface_family.py -q
```

Result: exit `1` before collection, `no tests ran in 0.00s`.

```text
ERROR: file or directory not found: tests/test_impeller_v11_2_resources.py
```

Both `tests/test_impeller_v11_2_resources.py` and `tests/test_impeller_v11_surface_family.py` are absent and have no history in this repository. A supplemental run substituted the current closest names, `test_impeller_v11_resources.py` and `test_impeller_v11_six_face_surface_family.py`; it timed out after `1204s` without a pytest summary and is not reported as passing.

### Frontend And HTTP Gates

```powershell
Set-Location frontend
npm.cmd test
```

Final rerun result: `196` passed, `0` failed, `20` suites, duration `295.4475ms`.

After verifying the existing listener PIDs and commands, only those listeners were stopped. Services were restarted from explicit directories in this worktree:

```text
backend  PID 39960  http://127.0.0.1:8061/api/presets/impeller = HTTP 200
frontend PID 29116  http://127.0.0.1:5199/                     = HTTP 200
served frontend/src/App.js exactly matched this worktree
```

### Playwright Gate

```powershell
$env:CODEX_NODE_MODULES='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node frontend/scripts/parameter-inspection-visual-smoke.cjs
```

The final run generated `radial_open_reference_v1_1` and selected these authoritative examples:

```text
Top:                 hub.profile.control.0.r
Meridional:          blade:blade_0:attachment:root:lift
S-Q + Blade:         blade:blade_0:station:blade_0:span_0:section:leading_edge:sagitta
renderer lifecycle:  created 2, live 1
context lifecycle:   created 2, live 1, lost 0, restored 0
live canvas elements: 1
```

Final result: exit `1`, `BLOCKED`.

- Top drawing viewport is blank: `black=0`, `red=0`, `blue=0` across `234192` drawing pixels.
- `hub.profile.control.0.r` does not include `top` in `applicable_views`, so its browser row is disabled in Top and red feature/blue ordinate evidence cannot be selected.
- Meridional root lift emits visible red endpoints (`33` pixels) and blue dimension evidence (`324` pixels), but no visible thin-black hub/blade root boundary pixels (`black=0`).
- Desktop isolated blade contains a red feature line (`9` pixels) and no orange selected material, but no red feature pixel is within `12px` of neutral blade context; the line is visibly detached.
- Narrow isolated blade repeats the detached feature result: `63` red pixels and `redNearNeutral=0`.
- Toolbar/browser/drawing boxes did not overlap in the measured desktop and narrow layouts.
- UV, triangle, leader, standalone 3D, and Quad controls were absent; one live renderer/context remained bounded.

### Retained Failure Evidence

All four screenshots were regenerated by the final smoke run and visually inspected:

```text
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-top.png
  SHA256 C60D80101D7272AA6563F2DE769F54D5515E885DAD058B4FCA2D657A936A8B14
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-meridional.png
  SHA256 B0E5039271CA378D8298630C3F2073047CB6867586CB404A02CD3518A8ECC903
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-s-q-blade.png
  SHA256 8F76AFC4F9F51C40A581F2FE8F070261E2D8A2460C86D19EBF527CEA17B96599
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/narrow-s-q-blade.png
  SHA256 5DEF9D67664E80F61A3C0DF11621DACA53540CB3960C3C2D7DC2D6E2DB80336B
```

The semantic acceptance rule is:

```text
parameter selection identifies authoritative construction evidence;
it never substitutes whole-surface material highlighting for feature geometry.
```

Task 8 did not patch the producing contract or rendering components because they are outside Task 8 ownership.
