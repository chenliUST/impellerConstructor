# V1.0 Test Transcript Summary

## Baseline

- `cd frontend; npm.cmd test` before V1.0 implementation: 85 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_kernel.py tests/test_impeller_geometry_validation.py tests/test_impeller_v09_workflow.py -q`: 45 passed in 124.40s.
- Full backend pytest timed out after 184s during baseline exploration; no failure output was captured before timeout.

## Resource Tests

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_resources.py -q`: 3 passed.

## Geometry Unit Tests

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_closed_profile.py -q`: 2 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_blade_faces.py -q`: 4 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_hub_profile.py -q`: 2 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_topology_graph.py -q`: 3 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_validation.py -q`: 4 passed.

## Integration Tests

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_resources.py -q`: 8 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_surface_graph.py -q`: 15 passed after final export-routing fixes.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_kernel.py tests/test_impeller_geometry_validation.py tests/test_impeller_v09_workflow.py -q`: 45 passed after final export-routing fixes.

## Frontend Tests

- `cd frontend; npm.cmd test`: 88 passed.
- `cd frontend; npm.cmd test`: 88 passed after switching the frontend default API base to `http://127.0.0.1:8060`.

## HTTP Smoke

- API server command: `$env:PYTHONPATH='src'; python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8060`.
- `radial_open_reference_v1_0`: `geometry_validation_status = PASS`, `transition_geometry_status = topology_first_closed_nurbs_impeller_surface_graph`, `synthetic_shared_edge_count = 0`, `surface_count = 31`, exports `step,stl,obj,manifest`.
- `radial_closed_reference_v1_0`: `geometry_validation_status = PASS`, `transition_geometry_status = topology_first_closed_nurbs_impeller_surface_graph`, `synthetic_shared_edge_count = 0`, `surface_count = 31`, exports `step,stl,obj,manifest`.

## Primitive Regression Overhaul

Regression observed from frontend screenshot: V1.0 output looked like a primitive disk/plate rather than the earlier NURBS impeller. Root cause: `impeller_v10_surface_graph.py` bypassed `axisymmetric_throughflow_nurbs` and generated a separate linear hub/blade network.

Added regression test:

- `python -m pytest tests/test_impeller_v10_legacy_nurbs_reuse.py -q`
- RED: 2 failed because `hub_revolve_surface` and `tip_reference_surface` were absent from V1.0 graph.
- GREEN: 2 passed after V1.0 became an adapter over the legacy NURBS kernel.

Verification after correction:

- `python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_legacy_nurbs_reuse.py -q`: 17 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_kernel.py tests/test_impeller_geometry_validation.py tests/test_impeller_v09_workflow.py -q`: 45 passed in 145.50s.
- `cd frontend; npm.cmd test`: 88 passed.
- Open V1.0 HTTP smoke after backend restart: `geometry_validation_status = PASS`, `source_kernel = axisymmetric_throughflow_nurbs`, `surface_count = 34`, `tip_reference_surface = present`, `bore chamfers = present`, `synthetic_shared_edge_count = 0`.
- Closed V1.0 service smoke: `geometry_validation_status = PASS`, `source_kernel = axisymmetric_throughflow_nurbs`, `surface_count = 38`, `shroud/tip support = present`, `bore chamfers = present`, `synthetic_shared_edge_count = 0`.

## Topology Semantics Tightening

Added regression tests:

- `tests/test_impeller_v10_topology_semantics.py`
- `frontend/src/simulationViewModel.test.js`

RED results before implementation:

- `python -m pytest tests/test_impeller_v10_topology_semantics.py -q`: 5 failed.
  - tip reference was visible by default;
  - outer hub chamfer surfaces were present;
  - edge/tip faces had no `transition_quality` and only 3 short-direction samples;
  - root face still had role `root_annular_surface`;
  - blade transition policies were still G1.
- `cd frontend; npm.cmd test -- simulationViewModel.test.js`: 1 failed because CAD review ignored `display.visible_by_default=false`.

GREEN results after implementation:

- `python -m pytest tests/test_impeller_v10_topology_semantics.py -q`: 5 passed.
- `cd frontend; npm.cmd test -- simulationViewModel.test.js`: 89 passed.
- `python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_legacy_nurbs_reuse.py tests/test_impeller_v10_topology_semantics.py -q`: 22 passed.
- `python -m pytest tests/test_impeller_geometry_validation.py -q`: 16 passed.
- `python -m pytest tests/test_impeller_v09_workflow.py -q`: 2 passed.
- `python -m pytest tests/test_impeller_kernel.py -q`: 27 passed in 249.87s.
- `cd frontend; npm.cmd test`: 89 passed.

Implementation notes:

- V1.0 transition policy resolver now supports optional `default_continuity`; older constructors without this field keep previous G1/G0 semantics.
- V1.0 open/closed constructors set blade leading/trailing/root/tip transitions to G2 defaults.
- Hub bottom/top outer chamfers are default-disabled; mounting-bore chamfers remain enabled.
- Frontend default CAD/mesh views hide surfaces with `display.visible_by_default=false`, while `feature_debug` can still show them.

HTTP smoke after backend restart:

```text
radial_open_reference_v1_0:
  geometry_version = 1.0
  geometry_validation_status = PASS
  surface_count = 32
  has_outer_chamfer = false
  bore_chamfers = true
  tip_reference_visible = false
  blade_0_leading_edge_surface grid = 17x13
  blade_0_leading_edge_surface continuity = G2
  blade_0_root_annular_surface role = root_pedestal_ring_surface
  blade_0_root_annular_surface grid = 105x9
  synthetic_shared_edge_count = 0

radial_closed_reference_v1_0:
  geometry_version = 1.0
  geometry_validation_status = PASS
  surface_count = 36
  has_outer_chamfer = false
  bore_chamfers = true
  blade_0_leading_edge_surface grid = 17x13
  blade_0_leading_edge_surface continuity = G2
  blade_0_root_annular_surface role = root_pedestal_ring_surface
  blade_0_root_annular_surface grid = 105x9
  synthetic_shared_edge_count = 0
```

Browser smoke:

- Frontend served from `http://127.0.0.1:5201/?v=1.0.1`.
- Backend API base visible as `http://127.0.0.1:8060`.
- Default selected preset is `Topology-first open throughflow v1.0`.
- Generated manifest showed `Geom validation PASS`.
- Viewer screenshot saved to `docs/evidence/2026-07-05-impeller-v1-0-topology-first/frontend-v1-smoke.jpg`.
- Viewer screenshot region pixel sample: 18,760 sampled pixels, 2,352 non-background, 1,830 colorful.

Additional historical-resource check:

- `python -m pytest tests/test_impeller_v07_resources.py tests/test_impeller_v09_resources.py tests/test_impeller_v091_resources.py -q`: 23 passed, 2 failed.
- Both failures are in V0.7 `surface_graph_bounded_brep` export expectations (`surface_graph_trimmed_brep_step` and BREP surface filtering). They are unrelated to the V1.0 topology-semantics changes and were not fixed in this pass.

## V1.0.2 Continuous Blade Attachment Overhaul

Task-level verification during implementation:

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_resources.py -q`: 9 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_resources.py -q`: 15 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_resources.py -q`: 23 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_resources.py -q`: 35 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_resources.py -q`: 45 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_resources.py -q`: 54 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_surface_graph_integration.py -q`: 6 passed after failure propagation and runtime-default validation were added.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_validation.py -q`: 11 passed after validation gates, V1.0.2 aggregate check, and attachment-quality failure propagation were added.

Final V1.0.2 backend verification:

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_resources.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py -q`: 71 passed in 39.17s.

Final V1.0 regression verification:

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_legacy_nurbs_reuse.py tests/test_impeller_v10_topology_semantics.py -q`: 22 passed in 6.62s.

Historical regression verification:

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_geometry_validation.py -q`: 16 passed in 2.18s.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v09_workflow.py -q`: 2 passed in 16.48s.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_kernel.py -q`: 27 passed in 101.61s.

Frontend verification:

- `cd frontend; npm.cmd test`: 93 passed.

Service smoke:

- `RuleSynthesisService.synthesize("impeller", "radial_open_reference_v1_0")` then `instantiate(..., {})`: PASS.
- `RuleSynthesisService.synthesize("impeller", "radial_closed_reference_v1_0")` then `instantiate(..., {})`: PASS.

Both service smoke runs produced STEP exports and reported:

```text
geometry_version = 1.0
geometry_patch_version = 1.0.2
surface_graph_status = PASS
continuous_blade_attachment_status = PASS
geometry_validation_status = PASS
manifest.validity.status = PASS
transition_failure_count = 0
```

HTTP smoke after restarting this worktree's services:

```text
backend = http://127.0.0.1:8060
frontend = http://127.0.0.1:5201

POST /api/rule-engines/synthesize
  part_family_id = impeller
  preset_id = radial_open_reference_v1_0

POST /api/rule-engines/{engine_id}/instantiate
  parameters = {}
  geometry_stage = full

result:
  engine_id = impeller-37df34fd
  run_id = run-28f1968d8b5a
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  geometry_validation_status = PASS
  manifest.validity.status = PASS
  transition_failure_count = 0
```

## 2026-07-06 Screenshot-Driven Attachment Geometry Correction

Red tests added before production fixes:

- `test_v10_2_final_edge_caps_match_visible_g2_surface_grids`
- `test_v10_2_root_attachment_uses_final_g2_edge_caps_and_real_width`
- `test_v10_2_closed_tip_attachment_uses_final_g2_edge_caps_and_real_width`
- `test_offset_loop_on_revolved_support_clamps_small_z_overrun_with_lift_tolerance`

Observed red failures:

```text
leading root cap edge_sample != leading uv_grid[0]
root outer-inner distance min = 0.0, expected >= 0.70 * 67.2
closed tip outer-inner distance min = 0.0, expected >= 0.70 * 41.4
offset_loop_on_revolved_support() missing z_tolerance_mm
```

Task-level verification after fixes:

- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_surface_graph_integration.py -q`: 9 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_support_domain.py -q`: 13 passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py -q`: 66 passed in 44.40s.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v10_2_resources.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py tests/test_impeller_v10_resources.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_legacy_nurbs_reuse.py tests/test_impeller_v10_topology_semantics.py tests/test_impeller_geometry_validation.py -q`: 113 passed in 120.62s.
- `cd frontend; npm.cmd test`: 93 passed.

Direct service smoke:

```text
radial_open_reference_v1_0:
  engine_id = impeller-37df34fd
  run_id = run-28f1968d8b5a
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  geometry_validation_status = PASS
  manifest.validity.status = PASS
  transition_failure_count = 0
  root_width = 67.2
  root_collapse_count = 0

radial_closed_reference_v1_0:
  engine_id = impeller-36b9abf0
  run_id = run-26007b908e62
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  geometry_validation_status = PASS
  manifest.validity.status = PASS
  transition_failure_count = 0
  root_width = 67.2
  root_collapse_count = 0
  tip_width = 41.4
  tip_collapse_count = 0
```

HTTP smoke after restarting local services from this worktree:

```text
backend = http://127.0.0.1:8060
frontend = http://127.0.0.1:5201
backend_pid = 44572
frontend_pid = 42900

radial_open_reference_v1_0:
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  geometry_validation_status = PASS
  manifest.validity.status = PASS
  transition_failure_count = 0
  root_width = 67.2
  root_collapse_count = 0

radial_closed_reference_v1_0:
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  continuous_blade_attachment_status = PASS
  geometry_validation_status = PASS
  manifest.validity.status = PASS
  transition_failure_count = 0
  root_width = 67.2
  root_collapse_count = 0
  tip_width = 41.4
  tip_collapse_count = 0
```

## 2026-07-06 Six-Face Regression Fix Verification

Commands run after support-normal root lift, material-normal edge bulge, local foldover metrics, and visible root component patches:

```text
$env:PYTHONPATH='src'; python -m pytest tests\test_impeller_v10_2_surface_graph_integration.py -q
12 passed in 58.51s

$env:PYTHONPATH='src'; python -m pytest tests\test_impeller_v10_2_blade_lattice.py tests\test_impeller_v10_2_edge_g2_surfaces.py tests\test_impeller_v10_2_root_attachment.py tests\test_impeller_v10_2_closed_tip_attachment.py tests\test_impeller_v10_2_support_domain.py tests\test_impeller_v10_2_surface_graph_integration.py tests\test_impeller_v10_2_validation.py -q
69 passed in 115.46s
```

Backend restart and HTTP smoke:

```text
backend = http://127.0.0.1:8060
backend_pid = 32256

radial_open_reference_v1_0:
  geometry_version = 1.0
  geometry_validation_status = PASS
  transition_geometry_status = topology_first_closed_nurbs_impeller_surface_graph
  surface_graph_status = PASS
  geometry_patch_version = 1.0.2
  surface_count = 48
  root_component_count = 4
  root_component_max_foldover = 0
  open_tip_foldover = 0
```

## 2026-07-06 V1.0.3 Section-Loop Root Blend Verification

Commands run from:

```text
C:\Users\CHEN Li\Documents\TurboJetCase\impellerConstructor\.worktrees\impeller-v1.0-topology-first
```

Backend V1.0.3 tests:

```text
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_preset_defaults.py -q
9 passed in 61.95s

python -m pytest tests\test_impeller_v10_3_section_loop.py tests\test_impeller_v10_3_blade_faces.py tests\test_impeller_v10_3_root_blend.py tests\test_impeller_v10_3_tip_dome.py -q
80 passed in 90.50s

python -m pytest tests\test_impeller_v10_3_surface_graph.py tests\test_impeller_v10_3_validation.py -q
13 passed in 256.74s
```

V1.0.2 regression tests:

```text
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_2_blade_lattice.py tests\test_impeller_v10_2_surface_graph_integration.py tests\test_impeller_v10_2_validation.py -q
29 passed in 122.76s
```

Frontend tests after V1.0.3 curve controls, viewer overlays, and manifest label update:

```text
cd frontend
npm.cmd test
102 passed, 0 failed
```

HTTP smoke after restarting backend from this worktree:

```text
backend = http://127.0.0.1:8060
backend_pid = 26328

radial_open_reference_v1_0:
  geometry_version = 1.0
  geometry_validation_status = PASS
  transition_geometry_status = topology_first_section_loop_blade_root_blend_surface_graph
  graph_patch = 1.0.3
  graph_status = PASS
  main_blade_count = 4
  splitter_blade_count = 4
  root_component_max_foldover = 0
  tip_dome_max_foldover = 0
```

## 2026-07-06 V1.0.3 NURBS Carrier Reuse Correction

Root cause investigated before code changes:

```text
Observed frontend symptom:
  V1.0.3 open preset looked primitive/flat even though V1.0.3 topology was loaded.

Actual cause:
  The V1.0.3 section-loop kernel was active, but its initial carrier path did not reuse
  the previously validated axisymmetric throughflow NURBS hub, pressure, and suction
  surface math. The simplified mapper produced a blade pressure angular span near
  primitive behavior instead of carrier-derived wrap.

Architectural correction:
  Keep V1.0.3 section-loop topology as the owning graph.
  Use the older axisymmetric_throughflow_nurbs_kernel only as a carrier for hub support
  and pressure/suction surface rows.
  Do not copy the legacy graph or revert V1.0.3 root/tip/topology work.
```

Targeted tests:

```text
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_surface_graph.py::test_open_preset_uses_v10_3_nurbs_carrier_math_not_radial_primitives tests\test_impeller_v10_legacy_nurbs_reuse.py tests\test_impeller_v10_3_preset_defaults.py -q
6 passed in 30.43s

python -m pytest tests\test_impeller_v10_3_section_loop.py tests\test_impeller_v10_3_blade_faces.py tests\test_impeller_v10_3_root_blend.py tests\test_impeller_v10_3_tip_dome.py -q
80 passed in 86.81s

python -m pytest tests\test_impeller_v10_3_surface_graph.py -q
5 passed in 71.71s

python -m pytest tests\test_impeller_v10_3_preset_defaults.py tests\test_impeller_v10_legacy_nurbs_reuse.py -q
5 passed in 28.93s

python -m pytest tests\test_impeller_v10_3_validation.py -q
9 passed in 130.75s

python -m pytest tests\test_impeller_v10_3_resources.py -q
6 passed in 90.59s

cd frontend
npm.cmd test -- src\appModel.test.js
102 passed, 0 failed
```

Service smoke:

```text
Existing backend on 8060 was stale: it read updated JSON defaults but still had old Python modules loaded.
New backend started from this worktree:
  backend = http://127.0.0.1:8061
  frontend = http://127.0.0.1:5203
  frontend apiDefault = http://127.0.0.1:8061

radial_open_reference_v1_0 via 8061:
  geometry_patch_version = 1.0.3
  surface_graph_status = PASS
  carrier_source_kernel = axisymmetric_throughflow_nurbs_kernel
  source_math_policy = section_loop_first_nurbs_carrier_blade_faces_segmented_root_blends_open_tip_domes
  v1_0_3_transition_failure_count = 0
  pressure section_loop_source = v1_0_3_nurbs_carrier_section_lattice
  main_streamwise_start_u = 0.38
  main_streamwise_end_u = 0.62
```

## 2026-07-07 V1.0.3 Thin Long Concave-Carrier Preset Fix

Root cause fixed:

```text
V1.0.3 carrier ignored constructor profile_defaults.
The graph used V1.0.3 topology but generated hub/tip carrier profiles from scalar fallback logic.
This made the hub look conical and made frontend preset/profile values disagree with geometry.
```

Implementation summary:

```text
_v10_3_nurbs_carrier_geometry now receives profile_defaults.
Open constructor hub/tip profiles are concave NURBS carrier defaults.
Open preset is retuned to 20 mm max blade thickness and longer streamwise coverage.
V1.0 ParameterPanel is reduced to high-level required inputs.
ModelViewer renders translucent surfaces and UV row/column wires on every surface with wireframe.enabled.
Open tip reference surface remains hidden by default.
```

Targeted backend verification:

```text
python -m pytest tests\test_impeller_v10_3_preset_defaults.py tests\test_impeller_v10_3_surface_graph.py -q
8 passed in 28.72s

python -m pytest tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_validation.py -q
15 passed in 117.69s

python -m pytest tests\test_impeller_v10_3_blade_faces.py tests\test_impeller_v10_3_section_loop.py -q
39 passed in 71.22s

python -m pytest tests\test_impeller_v10_3_root_blend.py tests\test_impeller_v10_3_tip_dome.py tests\test_impeller_v10_legacy_nurbs_reuse.py -q
43 passed in 19.11s
```

Frontend verification:

```text
cd frontend
npm.cmd test -- appModel.test.js appFiles.test.js
102 passed, 0 failed
```

Service smoke:

```text
radial_open_reference_v1_0:
  geometry_version = 1.0
  geometry_patch_version = 1.0.3
  surface_graph_status = PASS
  transition_geometry_status = topology_first_section_loop_blade_root_blend_surface_graph
  geometry_validation_status = PASS

radial_closed_reference_v1_0:
  geometry_version = 1.0
  geometry_patch_version = 1.0.2
  surface_graph_status = PASS
  transition_geometry_status = topology_first_closed_nurbs_impeller_surface_graph
  geometry_validation_status = PASS
```

HTTP smoke after restarting backend on 8061:

```text
POST http://127.0.0.1:8061/api/rule-engines/synthesize
POST http://127.0.0.1:8061/api/rule-engines/{engine_id}/instantiate

radial_open_reference_v1_0:
  run_id = run-3b60138c6bcb
  geometry_version = 1.0
  geometry_patch_version = 1.0.3
  surface_graph_status = PASS
  transition_geometry_status = topology_first_section_loop_blade_root_blend_surface_graph
  validation_status = PASS
  blade_thickness_mm = 20.0
  main_streamwise_start_u = 0.2
  main_streamwise_end_u = 0.8
  hub_profile_first = {u: 0.0, r_mm: 126.0, z_mm: 118.0}
```

## 2026-07-07 Frontend Port Stale-Catalog Correction

Root cause:

```text
Multiple local frontend servers were still listening:
  5200 -> stale v0.97 appModel.js, apiDefault 8040
  5201 -> current V1.0.3 appModel.js, apiDefault 8061
  5202 -> stale v0.97 appModel.js, apiDefault 8040
  5203 -> stale v0.97 appModel.js, apiDefault 8040

The user opened a stale port, so the UI showed "B-Rep open throughflow v0.97" even though the V1.0.3 backend and source files were correct.
```

Correction:

```text
Restarted 5200, 5202, and 5203 from:
C:\Users\CHEN Li\Documents\TurboJetCase\impellerConstructor\.worktrees\impeller-v1.0-topology-first\frontend

Verified 5200, 5201, 5202, and 5203 now all serve:
  apiDefault = http://127.0.0.1:8061
  first preset id = radial_open_reference_v1_0
  first preset name = Topology-first open throughflow v1.0.3
  HasV097 = false
  HasV103 = true
```

HTTP smoke:

```text
POST http://127.0.0.1:8061/api/rule-engines/synthesize
POST http://127.0.0.1:8061/api/rule-engines/{engine_id}/instantiate

radial_open_reference_v1_0:
  run_id = run-3b60138c6bcb
  geometry_patch_version = 1.0.3
  surface_graph_status = PASS
  validation_status = PASS
  transition_geometry_status = topology_first_section_loop_blade_root_blend_surface_graph

5203 frontend probe:
  first_preset_frontend_5203 = true for "Topology-first open throughflow v1.0.3"
```

Known regression note:

```text
python -m pytest tests\test_impeller_v10_2_surface_graph_integration.py tests\test_impeller_v10_2_validation.py tests\test_impeller_v10_surface_graph.py tests\test_impeller_v10_validation.py -q
3 failed, 25 passed

Failures are confined to historical V1.0.2 open-root attachment assertions that use radial_open_reference_v1_0 as a historical fixture. The current active V1.0.3 open preset and closed V1.0.2 service smoke both pass geometry validation.
```

## 2026-07-07 V1.0.4 Spec And Plan Authoring Check

Files authored:

```text
docs/superpowers/specs/2026-07-07-impeller-v1-0-4-geometry-contract-overhaul-spec.md
docs/superpowers/plans/2026-07-07-impeller-v1-0-4-geometry-contract-overhaul-implementation.md
```

Text checks performed:

```text
rg -n "scaffold|If tests still fail|fixed values|placeholder|TBD|TODO|implement later|fill in details|scaffolding" docs/superpowers/plans/2026-07-07-impeller-v1-0-4-geometry-contract-overhaul-implementation.md docs/superpowers/specs/2026-07-07-impeller-v1-0-4-geometry-contract-overhaul-spec.md

Result after edits:
  no deferred implementation language remains in the V1.0.4 spec or plan
```

Implementation tests were not run in this authoring step. The V1.0.4 implementation plan requires the following gates during execution:

```text
python -m pytest tests/test_impeller_v10_4_resources.py -q
python -m pytest tests/test_impeller_v10_4_section_loop_contract.py -q
python -m pytest tests/test_impeller_v10_4_root_surface_contract.py -q
python -m pytest tests/test_impeller_v10_4_tip_surface_contract.py -q
python -m pytest tests/test_impeller_v10_4_hub_solid_contract.py -q
python -m pytest tests/test_impeller_v10_4_continuity_contract.py tests/test_impeller_v10_4_angle_contract.py -q
python -m pytest tests/test_impeller_v10_4_surface_graph.py -q
cd frontend; npm.cmd test
```

## 2026-07-07 Task 1 Review-Fix Verification

Review findings addressed in this pass:

- historical V1.0.2 open-preset fixture now downgrades the active open preset independent of the production patch level
- V1.0.3 resource coverage now distinguishes active V1.0.4 runtime expectations from retained V1.0.3 export-contract metadata coverage
- V1.0.4 preset-contract helper now derives expected root/tip values from `average_blade_thickness_mm` when present

Required focused checks:

```text
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_4_resources.py -q
...                                                                      [100%]
3 passed in 0.17s

python -m pytest tests/test_impeller_v10_2_resources.py -k historical -q
.                                                                        [100%]
1 passed, 9 deselected in 0.33s

python -m pytest tests/test_impeller_v10_3_resources.py -k "open_reference_routes_to_v10_3_runtime_contract or open_reference_resources_use_v10_3_export_contract_metadata" -q
..                                                                       [100%]
2 passed, 4 deselected in 0.27s
```

Additional focused regression check:

```text
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_resources.py -q
..........                                                               [100%]
10 passed in 0.60s
```

Exploratory note outside the required review-fix scope:

```text
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_3_resources.py -q
.....F                                                                   [100%]

Remaining failure:
  test_v10_3_open_service_instantiation_generates_surface_graph
  RuntimeError: geometry validation blocked validated transition bounded B-Rep export (1):
  v1_0_2_resolved_attachment_defaults_missing
```

## 2026-07-07 Task 1 Re-Review Remaining Findings Verification

Root cause addressed:

```text
The live open V1.0 preset had already moved to geometry_patch_version 1.0.4,
but two remaining regression files still treated the live preset as the old
V1.0.3 default set. Historical V1.0.3 coverage was retained by adding an
explicit historical open-runtime fixture for the old section-loop defaults.
```

Files updated in this pass:

```text
tests/impeller_v10_3_historical_fixture.py
tests/test_impeller_v10_resources.py
tests/test_impeller_v10_3_preset_defaults.py
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json
```

Required focused verification:

```text
python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_resources.py tests/test_impeller_v10_3_preset_defaults.py -q
...........                                                              [100%]
11 passed in 0.77s

python -m pytest tests/test_impeller_v10_2_resources.py -q
..........                                                               [100%]
10 passed in 1.04s
```

## 2026-07-07 Task 1 Re-Review Final Finding Verification

Root cause:

```text
The remaining V1.0.3 service-instantiation regression test still synthesized the live
`radial_open_reference_v1_0` preset and expected a historical 1.0.3 manifest/surface graph.
After Task 1 moved that live open preset to 1.0.4, the test exercised the active 1.0.4
service validation path and failed before export with:
  v1_0_2_resolved_attachment_defaults_missing
```

Correction:

```text
Keep the live preset on 1.0.4.
Run the V1.0.3 service regression through the historical V1.0.3 fixture instead.
The historical fixture now adds the attachment defaults required by the current validator,
and the service test swaps the synthesized engine's cached DSL context to that historical
runtime before calling instantiate().
```

Verification:

```text
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_3_resources.py::test_v10_3_open_service_instantiation_generates_surface_graph -q
.                                                                        [100%]
1 passed in 60.85s (0:01:00)

python -m pytest tests/test_impeller_v10_3_resources.py -q
......                                                                   [100%]
6 passed in 57.75s

python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_resources.py tests/test_impeller_v10_3_preset_defaults.py tests/test_impeller_v10_2_resources.py -q
.....................                                                    [100%]
21 passed in 1.70s
```

## 2026-07-07 V1.0.4 Task 9 Regression And Service Smoke

Backend V1.0.4 contract suite:

```text
python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_4_section_loop_contract.py tests/test_impeller_v10_4_root_surface_contract.py tests/test_impeller_v10_4_tip_surface_contract.py -q
...................                                                      [100%]
19 passed in 257.88s (0:04:17)

python -m pytest tests/test_impeller_v10_4_hub_solid_contract.py tests/test_impeller_v10_4_continuity_contract.py tests/test_impeller_v10_4_angle_contract.py tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py -q
....................                                                     [100%]
20 passed in 137.68s (0:02:17)
```

During HTTP smoke, the graph initially reported `geometry_patch_version = 1.0.4` and validation `PASS`, but still exposed the V1.0.3 `transition_geometry_status` string. The graph payload and validation allowlist were corrected so V1.0.4 reports the measured-contract status:

```text
python -m pytest tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py tests/test_impeller_geometry_validation.py -q
..........................                                               [100%]
26 passed in 40.03s
```

V1.0.3 historical regression suite:

```text
python -m pytest tests/test_impeller_v10_3_preset_defaults.py tests/test_impeller_v10_3_surface_graph.py tests/test_impeller_v10_3_validation.py -q
.................                                                        [100%]
17 passed in 82.74s (0:01:22)

python -m pytest tests/test_impeller_v10_3_root_blend.py tests/test_impeller_v10_3_tip_dome.py tests/test_impeller_v10_legacy_nurbs_reuse.py -q
...........................................                              [100%]
43 passed in 14.41s
```

Compatibility validation regression:

```text
python -m pytest tests/test_impeller_geometry_validation.py -q
.................                                                        [100%]
17 passed in 2.17s
```

Frontend regression:

```text
cd frontend
npm.cmd test

tests 108
suites 11
pass 108
fail 0
duration_ms 164.9775
```

Service restart:

```text
backend 8061 listening
frontend 5203 listening
```

HTTP smoke against `radial_open_reference_v1_0`:

```json
{
  "run_id": "run-8e1dcae6c155",
  "geometry_patch_version": "1.0.4",
  "surface_graph_status": "PASS",
  "validation_status": "PASS",
  "transition_geometry_status": "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph",
  "root_quality_status": "PASS",
  "root_min_width_mm": 10.0,
  "root_min_lift_mm": 9.731957,
  "hub_quality_status": "PASS",
  "hub_max_linear_fit_residual_mm": 28.094591
}
```

Post-documentation consistency check for root diagnostic semantics:

```text
python -m pytest tests/test_impeller_v10_4_root_surface_contract.py -q
......                                                                   [100%]
6 passed in 196.19s (0:03:16)

python -m pytest tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py -q
.........                                                                [100%]
9 passed in 82.79s (0:01:22)
```

Final HTTP smoke after adding `max_parameter_direction_flip_role`:

```json
{
  "geometry_patch_version": "1.0.4",
  "surface_graph_status": "PASS",
  "validation_status": "PASS",
  "transition_geometry_status": "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph",
  "root_quality_status": "PASS",
  "max_parameter_direction_flip_role": "diagnostic_only",
  "hub_quality_status": "PASS"
}
```
