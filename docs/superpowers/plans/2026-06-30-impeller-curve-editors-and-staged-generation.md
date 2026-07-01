# Impeller Curve Editors And Staged Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel implementation where available, or `superpowers:executing-plans` for sequential implementation. Track each checkbox as work proceeds.

**Goal:** Add deterministic frontend/backend support for editable hub/tip profile curves, editable blade/edge intrinsic curves, and staged visual generation: `Hub -> Blades -> Edges`.

**Architecture:** Keep the current `AxisymmetricThroughflowRadialBladedImpeller` construction method. The frontend edits explicit curve data and sends it as deterministic overrides. The backend validates those overrides, applies them in the current geometry kernel, and returns a stage-filtered `surface_graph` plus construction lines. The visual stage controls only what is generated/returned for inspection; it must not alter the mathematical meaning of the DSL.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, existing sampled NURBS kernel, React without JSX, Three.js viewer, SVG pointer-drag curve editors, Node test runner.

---

## Scope

This plan is interaction and deterministic geometry-input work. It does not create loss records, does not update ontology learning state, and does not change the current impeller classification slice.

The staged generation model is:

```text
hub_support
  Generate hub/support geometry only:
  inner hub solid, outer hub shell/support, mounting bore, tip/reference support curve/surface.

blade_surfaces
  Generate hub/support geometry plus blade pressure/suction surfaces.
  Also return blade boundary construction curves, but do not generate closure faces.

edge_closures
  Generate complete inspectable geometry:
  hub/support + blade pressure/suction surfaces + leading/trailing/root/tip edge closure surfaces.

full
  Backward-compatible alias for edge_closures.
```

The first implementation locks NURBS topology:

```text
degree: locked
control-point count: locked
weights: locked
knots: locked
editable values: control-point coordinates and intrinsic curve values
```

This is intentional. A future optimization phase can expose degree, knot vectors, and control-net size once the minimum deterministic loop is stable.

---

## Design Decisions

### 1. Hub And Tip Curves

Hub and tip/reference curves are edited in the front meridional R-Z plane.

Payload entities:

```json
{
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [[180, 0], [360, 60], [520, 88], [620, 82]],
      "weights": [1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 1, 1, 1, 1]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [[180, 150], [360, 188], [520, 170], [620, 154]],
      "weights": [1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 1, 1, 1, 1]
    }
  }
}
```

Backend invariant:

```text
tip_or_shroud_profile must remain outside/above hub_profile for every sampled u.
hub radius must remain positive.
mounting bore radius must remain smaller than local hub radius.
```

### 2. Blade And Edge Curves

Blade and edge curves should not be edited by arbitrary 3D dragging. They are spatial curves, but their stable design controls live in intrinsic coordinates. The UI should show a small 2D editor per intrinsic curve, with names that explain the coordinate system.

Payload entities:

```json
{
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [[0, 0], [0.33, -20], [0.66, -70], [1, -118]]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [[0, 12], [0.5, 8], [1, -8]]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [[0, -0.03], [0.5, 0], [1, 0.03]]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [[0, 0.05], [0.5, 0], [1, -0.05]]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [[0, 18], [0.5, 14], [1, 10]]
      }
    }
  }
}
```

Backend mapping:

```text
theta_center_u_curve       -> blade mean wrap theta(u)
span_lean_u_curve          -> theta offset across span v
leading_edge_sweep_v_curve -> support-surface u offset at blade u=0
trailing_edge_sweep_v_curve -> support-surface u offset at blade u=1
thickness_u_curve          -> pressure/suction angular offset from mean surface
```

The frontend can still display the resulting 3D curves on the model, but editing should happen in the intrinsic curve editors. This avoids ambiguous 3D picking and keeps the DSL directly inspectable.

### 3. Stage Semantics

Stage filtering is a backend feature. The viewer should show exactly what the backend generated for the requested stage. The frontend must not hide surfaces to simulate a generation stage because that would mask kernel failures.

---

## Backend Plan

### Task 1: Request Contract

Files:

- `src/part_rule_synthesis/api.py`
- `src/part_rule_synthesis/service.py`
- `tests/test_acceptance.py`

Steps:

- [ ] Extend `InstantiateRequest` with:
  - `profile_overrides: dict[str, Any] | None`
  - `curve_overrides: dict[str, Any] | None`
  - `geometry_stage: str = "full"`
- [ ] Pass these values through the API endpoint into `RuleSynthesisService.instantiate`.
- [ ] Extend `RuleSynthesisService.instantiate` signature with the same fields.
- [ ] Normalize stage aliases:
  - `hub -> hub_support`
  - `blades -> blade_surfaces`
  - `edges -> edge_closures`
  - `full -> edge_closures`
- [ ] Include `profile_overrides`, `curve_overrides`, and normalized `geometry_stage` in the run hash.
- [ ] Add these fields to the manifest.
- [ ] Add acceptance tests proving:
  - API/service accepts the new payload.
  - changed overrides change `run_id`.
  - invalid stage is rejected.
  - legacy `{parameters: {...}}` payload still works.

Expected manifest additions:

```json
{
  "geometry_stage": "blade_surfaces",
  "profile_overrides": {},
  "curve_overrides": {}
}
```

### Task 2: Kernel Function Signatures

Files:

- `src/part_rule_synthesis/impeller_kernel.py`
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `src/part_rule_synthesis/service.py`

Steps:

- [ ] Add optional `profile_overrides`, `curve_overrides`, and `geometry_stage` arguments to `build_impeller_geometry`.
- [ ] Pass those arguments into `build_axisymmetric_throughflow_nurbs_geometry` for `throughflow_bladed_channel`.
- [ ] Update all service metadata/export helper calls that rebuild geometry so they use the same overrides and stage.
- [ ] Preserve recessed/vortex and legacy fallback behavior without requiring these new fields.

Acceptance:

- A single instantiate request must use the same geometry inputs for:
  - exports
  - manifest metadata
  - validity metadata
  - frontend preview assets

### Task 3: Profile Override Validation

Files:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `tests/test_impeller_curve_overrides.py`

Steps:

- [ ] Rename current default profile builder to `_default_profile_definitions`.
- [ ] Add `_validated_profile_override(name, override, fallback)`.
- [ ] Validate:
  - `kind == "nurbs_curve"`
  - `degree == 3`
  - exactly 4 `[r_mm, z_mm]` control points
  - finite positive radius
  - finite z
  - 4 positive weights
  - clamped cubic knot vector
  - `coordinate_system == "rz_meridional_mm"`
- [ ] Add `_validate_tip_clearance(hub_profile, tip_profile)`.
- [ ] Emit `geometry_kernel.profile_controls` with editable entity names.
- [ ] Add tests:
  - valid hub override changes sampled hub surface points.
  - invalid negative radius is rejected.
  - tip below/intersecting hub is rejected.

### Task 4: Intrinsic Curve Override Validation

Files:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `tests/test_impeller_curve_overrides.py`

Steps:

- [ ] Add `_validated_curve_overrides(curve_overrides, params)`.
- [ ] Support the first locked curve set:
  - `blade_mean.theta_center_u_curve`
  - `blade_mean.span_lean_u_curve`
  - `blade_edges.leading_edge_sweep_v_curve`
  - `blade_edges.trailing_edge_sweep_v_curve`
  - `thickness.thickness_u_curve`
- [ ] Validate all curve control points:
  - x/t coordinate is finite, monotone, and inside `[0, 1]`.
  - value coordinate is finite.
  - thickness values are positive.
  - support offsets stay within a conservative range, e.g. `[-0.45, 0.45]`.
- [ ] Implement deterministic cubic/linear interpolation for these intrinsic curves.
- [ ] Emit `geometry_kernel.editable_curve_controls` describing coordinate systems, bounds, and current effective curves.
- [ ] Add tests:
  - theta override changes pressure/suction blade sampled points.
  - thickness override changes pressure/suction separation.
  - sweep override changes leading/trailing boundary sampled points.
  - invalid non-monotone curve is rejected.

### Task 5: Apply Intrinsic Curves In Geometry

Files:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `tests/test_impeller_curve_overrides.py`

Steps:

- [ ] Replace scalar-only theta progression with effective `theta_center(u)`:
  - fallback remains current `blade_wrap_deg` rule.
  - override uses `theta_center_u_curve`.
- [ ] Replace scalar-only lean contribution with effective `lean(u, v)`:
  - fallback remains current lean/edge-lean rule.
  - override uses `span_lean_u_curve`.
- [ ] Update support-surface sampling:
  - leading edge uses `leading_edge_sweep_v_curve` at `u=0`.
  - trailing edge uses `trailing_edge_sweep_v_curve` at `u=1`.
  - interior points blend leading/trailing offsets across `u`.
- [ ] Replace scalar-only thickness taper with effective `thickness(u)`.
- [ ] Keep `v=0` blade boundary conformed to hub surface and `v=1` conformed to tip/reference surface after all overrides.
- [ ] Add tests comparing blade boundary points against hub/tip sampled support points.

### Task 6: Stage Filtering

Files:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `tests/test_impeller_curve_overrides.py`

Steps:

- [ ] Add `_normalize_geometry_stage` at kernel boundary or reuse the service-normalized value.
- [ ] Add `_filter_surface_graph_by_stage(surface_graph, construction_lines, geometry_stage)`.
- [ ] Stage `hub_support` returns:
  - hub/support surfaces only.
  - hub/tip/reference construction lines only.
  - no blade pressure/suction surfaces.
  - no edge closure surfaces.
- [ ] Stage `blade_surfaces` returns:
  - hub/support surfaces.
  - blade pressure/suction surfaces.
  - blade boundary and UV construction lines.
  - no edge closure surfaces.
- [ ] Stage `edge_closures` returns:
  - all surfaces and construction lines.
- [ ] Add tests:
  - `hub_support` has no blade roles.
  - `blade_surfaces` has blade roles and no `edge_closure_surface`.
  - `edge_closures` has edge closure surfaces.
  - construction lines are filtered consistently with surface stage.

### Task 7: Backend Validity Metadata

Files:

- `src/part_rule_synthesis/service.py`
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `tests/test_acceptance.py`

Steps:

- [ ] Extend validity metadata with stage-aware checks:
  - `profile_validity`
  - `curve_override_validity`
  - `boundary_conformance`
  - `stage_completeness`
- [ ] Ensure invalid geometry inputs fail fast with clear messages instead of returning partial STL/STEP assets.
- [ ] Keep engineering validity explicitly out of scope for this task; if the manifest needs this field, emit `engineering_validity.status = "NOT_EVALUATED"` with a clear reason.

---

## Frontend Plan

### Task 8: API Client Payload Builder

Files:

- `frontend/src/apiClient.js`
- `frontend/src/apiClient.test.js` or `frontend/src/appModel.test.js`

Steps:

- [ ] Change `instantiateImpeller` signature to:

```js
instantiateImpeller(
  apiBase,
  engineId,
  parameters,
  profileOverrides = null,
  curveOverrides = null,
  geometryStage = "edge_closures",
)
```

- [ ] Build payload:

```json
{
  "parameters": {},
  "profile_overrides": {},
  "curve_overrides": {},
  "geometry_stage": "blade_surfaces"
}
```

- [ ] Omit null override fields or send them as `{}` consistently. Pick one policy and test it.
- [ ] Add tests proving stage and overrides are serialized.

### Task 9: Profile Editor Model

Files:

- `frontend/src/profileEditorModel.js`
- `frontend/src/profileEditorModel.test.js`

Steps:

- [ ] Create pure helpers:
  - `profilesFromManifest(manifest)`
  - `profileEditorBounds(profiles)`
  - `rzToScreen(point, bounds, viewport)`
  - `screenToRz(point, bounds, viewport)`
  - `updateControlPoint(profiles, profileId, pointIndex, rzPoint)`
  - `validateProfileOverrides(profiles)`
  - `profileOverridesPayload(profiles)`
- [ ] Validate the same minimum constraints as backend where possible:
  - positive radius
  - finite coordinates
  - 4 control points per profile
  - tip roughly outside hub at sampled points
- [ ] Add tests for coordinate round trip, point update, and invalid radius.

### Task 10: Blade Curve Editor Model

Files:

- `frontend/src/bladeCurveEditorModel.js`
- `frontend/src/bladeCurveEditorModel.test.js`

Steps:

- [ ] Create pure helpers:
  - `defaultBladeCurveControls(parameters)`
  - `curveEditorBounds(curve)`
  - `curveToScreen(point, bounds, viewport)`
  - `screenToCurvePoint(point, bounds, viewport)`
  - `updateCurvePoint(controls, group, curveId, pointIndex, point)`
  - `validateCurveOverrides(controls)`
  - `curveOverridesPayload(controls)`
- [ ] Keep control-point x/t monotone:
  - endpoint x values are locked at `0` and `1`.
  - interior x values may move only inside neighboring x bounds.
  - y/value is free within curve-specific safe bounds.
- [ ] Add tests for:
  - monotone x clamping.
  - positive thickness validation.
  - support offset bound validation.
  - deterministic payload output.

### Task 11: Generation Stage Panel

Files:

- `frontend/src/components/GenerationStagePanel.js`
- `frontend/src/App.js`
- `frontend/src/appFiles.test.js`

Steps:

- [ ] Add stage selector with three visible states:
  - `Hub`
  - `Blades`
  - `Edges`
- [ ] Store backend stage ids:
  - `hub_support`
  - `blade_surfaces`
  - `edge_closures`
- [ ] Changing stage triggers regeneration with the selected stage.
- [ ] Do not simulate stage by hiding viewer layers locally.

### Task 12: Profile Curve Editor Component

Files:

- `frontend/src/components/ProfileCurveEditor.js`
- `frontend/src/App.js`
- `frontend/src/styles.css`

Steps:

- [ ] Render hub and tip/reference NURBS control polygons in one SVG R-Z plane.
- [ ] Draw:
  - hub control polygon and handles.
  - tip/reference control polygon and handles.
  - optional sampled curve preview from manifest when available.
- [ ] Implement pointer-drag handles:
  - `pointerdown` selects `{profileId, pointIndex}`.
  - `pointermove` converts screen point to R-Z coordinate.
  - state update writes `profileOverrides`.
  - `pointerup` clears active handle.
- [ ] Provide numeric readout for selected handle:
  - `r_mm`
  - `z_mm`
- [ ] Keep reset action:
  - reset profile overrides to manifest defaults.
- [ ] Add compact CSS for SVG, handles, labels, selected handle state, and validation warning.

### Task 13: Blade And Edge Curve Editor Component

Files:

- `frontend/src/components/BladeCurveEditor.js`
- `frontend/src/App.js`
- `frontend/src/styles.css`

Steps:

- [ ] Render one small SVG editor for each intrinsic curve:
  - `theta_center_u_curve`
  - `span_lean_u_curve`
  - `leading_edge_sweep_v_curve`
  - `trailing_edge_sweep_v_curve`
  - `thickness_u_curve`
- [ ] Each editor shows:
  - curve name.
  - coordinate system.
  - min/max value labels.
  - control polygon.
  - draggable handles.
- [ ] Implement pointer-drag handles:
  - endpoint x/t values remain fixed at `0` and `1`.
  - interior x/t values are clamped between neighboring points.
  - y/value updates continuously.
- [ ] Add optional numeric input for selected handle value. This supports precise engineering adjustment after visual dragging.
- [ ] Keep reset action:
  - reset curve overrides from current scalar parameters/default rules.

### Task 14: App State Integration

Files:

- `frontend/src/App.js`
- `frontend/src/appFiles.test.js`

Steps:

- [ ] Add state:
  - `profileOverrides`
  - `curveOverrides`
  - `geometryStage`
  - optionally `selectedCurveHandle`
- [ ] Pass overrides and stage into `instantiateImpeller`.
- [ ] Reset overrides and stage when preset changes.
- [ ] Show current manifest stage and kernel editable controls in the inspector panel.
- [ ] Keep existing parameter panel, but demote shape-related scalar sliders that are superseded by curve editors:
  - keep core numeric inputs: blade count, inlet/exit radius, blade heights, bore radius.
  - keep scalar fields as fallback/default generation controls.
  - use curve editors as authoritative override when present.

### Task 15: Viewer Layer Semantics

Files:

- `frontend/src/components/ModelViewer.js`
- `frontend/src/workspaceModel.js`

Steps:

- [ ] Ensure viewer layer names match backend surface roles:
  - support/hub
  - blade pressure/suction
  - edge closures
  - construction lines
- [ ] Keep construction lines generated from backend `surface_graph` and `construction_lines`.
- [ ] Do not display STL triangle edges as construction wireframe.
- [ ] Make stage mismatch visible:
  - if stage is `hub_support`, blade layer toggles should be disabled or show zero entities.
  - if stage is `blade_surfaces`, edge closure layer should show zero entities.

---

## Verification Plan

### Backend

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
$env:PYTHONPATH='src'
python -m pytest tests -q
python -m compileall -q src scripts
```

Acceptance criteria:

- Legacy instantiate request still works.
- Override payload changes run hash.
- Invalid profile/curve override is rejected with a clear error.
- `hub_support` returns no blade surfaces.
- `blade_surfaces` returns blade surfaces and no edge closure surfaces.
- `edge_closures` returns complete surfaces.
- Blade `v=0` boundary conforms to hub support surface.
- Blade `v=1` boundary conforms to tip/reference support surface.

### Frontend

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test
npm.cmd run build
```

Acceptance criteria:

- API client serializes stage and overrides.
- Profile editor model round-trips screen/R-Z coordinates.
- Blade curve editor model clamps intrinsic curve points correctly.
- App includes generation stage panel, profile curve editor, and blade curve editor.
- Build passes without runtime import errors.

### Manual Smoke Test

Start backend:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
$env:PYTHONPATH="$PWD\src"
python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8053
```

Start frontend:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
python -m http.server 5201 -b 127.0.0.1
```

Open:

```text
http://127.0.0.1:5201
```

Manual checks:

- Select `Hub`, generate, and confirm only hub/support geometry appears.
- Select `Blades`, generate, and confirm blade pressure/suction surfaces appear without closure faces.
- Select `Edges`, generate, and confirm closure surfaces appear.
- Drag a hub/tip profile handle, regenerate, and confirm run id changes and geometry updates.
- Drag a blade intrinsic curve handle, regenerate, and confirm blade geometry updates.
- Confirm construction wireframe comes from backend construction lines, not STL triangle edges.

---

## Implementation Order

Recommended commit sequence:

1. `feat: add impeller override and stage request contract`
2. `feat: support impeller profile curve overrides`
3. `feat: support impeller intrinsic curve overrides`
4. `feat: add impeller staged geometry filtering`
5. `feat: serialize impeller override payloads in frontend`
6. `feat: add impeller curve editor models`
7. `feat: add impeller staged curve editor UI`
8. `test: verify impeller staged generation integration`

---

## Risks And Guardrails

- **Risk:** Frontend edits visually valid curves that backend rejects.
  - **Guardrail:** Mirror backend validation in frontend model, but backend remains authoritative.
- **Risk:** Stage filtering hides construction bugs.
  - **Guardrail:** Stage filtering is implemented in backend after geometry sampling; tests assert role-specific completeness.
- **Risk:** Blade/edge curve editors are confused with direct 3D geometry editing.
  - **Guardrail:** UI labels every editor by intrinsic coordinate system and sends only explicit curve overrides.
- **Risk:** Existing scalar parameters conflict with curve overrides.
  - **Guardrail:** Scalars generate defaults; overrides become authoritative only when present.

---

## Self-Review

- Covers staged model generation: `Hub -> Blades -> Edges`.
- Covers frontend drag interaction for hub/tip and blade/edge curves.
- Keeps backend deterministic and authoritative.
- Avoids ontology/loss updates in this interaction-only step.
- Preserves current construction method while making curve inputs explicit and inspectable.
- Defines concrete files, tests, commands, and acceptance criteria.
