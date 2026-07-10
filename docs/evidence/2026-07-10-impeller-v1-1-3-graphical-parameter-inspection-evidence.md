# Impeller V1.1.3 Graphical Parameter Inspection Evidence

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

Acceptance fix commit: `a4f64f0 fix: close inspection acceptance regressions`

## Version Contract

```text
runtime_release_version = 1.1.3
parameter_inspection_contract_version = 1.1.3
geometry_version = 1.1
geometry_patch_version = 1.1.2
canonical_payload_version = 1.1.2
```

V1.1.3 is a runtime and read-only inspection release. Geometry and canonical semantics remain V1.1.2.

## Clean Services

Existing listeners were inspected through `Get-NetTCPConnection` and `Win32_Process`; only processes whose command lines matched the project Uvicorn and Python HTTP server commands were stopped.

```text
backend  = http://127.0.0.1:8061  PID 1000   /api/presets/impeller = HTTP 200
frontend = http://127.0.0.1:5199  PID 28804  / = HTTP 200
```

## Browser And Pixel Acceptance

The supplied runtime had Playwright 1.61.1 but its pnpm hoist link and Chromium revision were absent. Existing bundled packages were used by setting `NODE_PATH`; Chromium revision 1228 was installed with the bundled Playwright CLI. No project dependency was added.

Successful smoke command:

```powershell
$env:CODEX_NODE_MODULES='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:NODE_PATH='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\node_modules'
& 'C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' frontend/scripts/parameter-inspection-visual-smoke.cjs
```

Final result after the visual fix:

```text
parameter inspection desktop 3D: PASS
parameter inspection desktop Quad: PASS
parameter inspection narrow S-Q: PASS
inspection renderer count: 1
inspection scene surface count: 101
browser device pixel ratio: 1
inspection canvas non-background ratio: 0.1440
wall time: 167.7s
```

The PNG threshold was `nonBackgroundRatio >= 0.05`; observed `0.1440` passed.

Screenshots:

```text
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-3d.png
docs/evidence/assets/v1.1.3-parameter-inspection/desktop-quad.png
docs/evidence/assets/v1.1.3-parameter-inspection/narrow-s-q.png
```

Visual inspection observations:

- Desktop 3D: nonblank generated impeller, centered framing, readable toolbar, and orange selected-object outlines over the green generated surfaces.
- Desktop Quad: four distinct panes are visible: perspective 3D, meridional R-Z, S-Q, and top. The geometric panes retain the same orange selection treatment and expose unobscured maximize controls.
- Narrow S-Q: the toolbar wraps coherently, key parameter rows remain readable, the actual selected loop is present, and continuity metrics use a separate lower rail with no annotation overlap.

## Five Active Presets

A fresh graph audit compiled each unchanged active ID and validated its parameter-inspection contract:

```text
radial_open_reference_v1_1: PASS; runtime=1.1.3; geometry=1.1.2; canonical=1.1.2; contract=1.1.3; surfaces=102; generation_match=True
radial_closed_reference_v1_1: PASS; runtime=1.1.3; geometry=1.1.2; canonical=1.1.2; contract=1.1.3; surfaces=81; generation_match=True
nasa_stage37_stator_ring_v1_1: PASS; runtime=1.1.3; geometry=1.1.2; canonical=1.1.2; contract=1.1.3; surfaces=285; generation_match=True
rr_ultrafan_cti_fan_v1_1: PASS; runtime=1.1.3; geometry=1.1.2; canonical=1.1.2; contract=1.1.3; surfaces=114; generation_match=True
public_rocket_turbopump_inducer_v1_1: PASS; runtime=1.1.3; geometry=1.1.2; canonical=1.1.2; contract=1.1.3; surfaces=24; generation_match=True
```

No alias or new active preset ID was introduced.

## Backend Regression Matrix

```powershell
python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `15 passed in 483.00s (0:08:02)`.

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Result: `24 passed in 244.39s (0:04:04)`.

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
```

Result: `37 passed in 11.67s`.

```powershell
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Result after the helper-surface compatibility fix: `34 passed in 348.44s (0:05:48)`.

```powershell
python -m pytest tests/test_impeller_geometry_validation.py tests/test_impeller_bounded_brep_export.py -q
```

Result: `55 passed in 4.02s`.

Required backend matrix total: `165 passed, 0 failed`.

Additional API acceptance command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_acceptance.py -q
```

Result: `38 passed in 431.78s (0:07:11)`.

## Frontend Regression Suite

```powershell
Set-Location frontend
npm.cmd test
```

Result:

```text
tests 176
suites 17
pass 176
fail 0
duration_ms 296.4956
```

## Acceptance Defects And Fixes

1. The required health URL `/api/presets/impeller` returned 404 because only `/api/impeller-presets` existed. A red API test was added, and the existing handler now serves both routes.
2. Narrow S-Q continuity labels occupied the same top lanes as parameter annotations. A red component test was added, metrics moved to a bounded lower rail, the focused frontend suite passed 9/9, and fresh PNGs were regenerated and inspected.
3. The new generation hash made an established V1.1 helper-surface UV exemption fail. A red contract test was added; helper/reference UV sampling is now canonicalized out of the hash while manufactured geometry remains generation-sensitive.

## Residual Limitations

- The smoke covers the active open preset in headless Chromium at device pixel ratio 1; all five presets are covered by backend contract/service tests, not five separate browser screenshots.
- S is normalized while Q is millimetric in the current generated loop payload. The approved equal-aspect S-Q fit therefore produces a slender loop for the open preset.
- Review-grade sampled geometry, exact CAD sewing, solver-ready volume meshes, and manufacturing certification remain outside V1.1.3.
