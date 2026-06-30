# Impeller UI Solid Hub/Hood DSL v0.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the current frontend issues as evidence, define a non-overwriting DSL v0.3 research record, then implement a UI/runtime update where curve editing is numerically inspectable, open and closed impellers are visually distinct, and hub/hood material domains are treated as finite solids with chamfers and nonzero thickness.

**Architecture:** Keep v0.2 reproducible. Add v0.3 DSL/ontology artifacts as an opt-in research version first, then update the runtime behind an explicit preset or DSL-version selection. Separate construction-support geometry from display/material geometry so open impellers can keep an internal blade-tip support surface without rendering it as a closed shroud.

**Tech Stack:** Python backend and geometry kernel in `src/part_rule_synthesis`, JSON DSL/ontology resources, React/Vite frontend in `frontend`, Vitest frontend tests, pytest backend tests.

---

## Context And Evidence

- Evidence screenshot: `docs/evidence/2026-06-30-impeller-ui-and-dsl-issues/current-open-impeller-ui-issue.png`
- Evidence note: `docs/evidence/2026-06-30-impeller-ui-and-dsl-issues/README.md`
- New DSL record: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3`
- New ontology slice: `src/part_rule_synthesis/ontology/impeller/v0_3/slice.json`
- Changelog: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/CHANGELOG.md`

Observed issues to preserve:

- Curve editor operation areas are too small for meaningful handle editing.
- Curve editor does not show numeric control-point coordinates.
- Open impeller still displays a tip reference/support surface, making it visually too close to the closed case.
- Hub appears as a surface-like object, not a real finite material solid.
- Hub and hood/shroud do not expose nonzero wall thickness or chamfer semantics.

---

## Phase 1: Freeze The Research Record

- [ ] Verify all v0.3 JSON files parse successfully.
- [ ] Verify v0.2 files remain unchanged.
- [ ] Commit the evidence screenshot, evidence README, v0.3 DSL/ontology files, v0.3 changelog, and this plan.
- [ ] Do not change runtime loading in this phase; v0.3 is a recorded design target, not the active default.

---

## Phase 2: Frontend Curve Editor Usability

- [ ] Enlarge the 2D profile editor drawing area for hub and tip/hood reference curves.
- [ ] Enlarge the 3D blade-curve editor panels enough to inspect and drag handles reliably.
- [ ] Show numeric values for editable handles:
  - selected control point index
  - `r_mm`, `z_mm` for meridional profile curves
  - blade boundary/edge control coordinates in the current blade-control coordinate frame
- [ ] Add direct numeric entry for selected control-point coordinates.
- [ ] Keep coordinate values in engineering units, not canvas pixels.
- [ ] Add frontend tests for coordinate readout formatting and edit propagation into the generation payload.

Implementation targets:

- `frontend/src/components/ProfileCurveEditor.js`
- `frontend/src/components/BladeCurveEditor.js`
- `frontend/src/profileEditorModel.js`
- `frontend/src/bladeCurveEditorModel.js`
- `frontend/src/workspaceModel.js`
- `frontend/src/styles.css`
- relevant `frontend/src/*.test.js`

---

## Phase 3: Open/Closed Display Policy

- [ ] Add a manifest/display-layer rule: construction-only support surfaces are available for validation and blade conformance but hidden from the shaded model and default layer list.
- [ ] For open impellers, hide `blade_tip_support_surface` / tip reference surface by default.
- [ ] For closed impellers, show the hood/shroud surface as material geometry.
- [ ] Keep blade tip conformance checks available in both variants.
- [ ] Add tests proving open and closed presets produce different display-layer graphs.

Implementation targets:

- `src/part_rule_synthesis/service.py`
- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `frontend/src/components/GeometryLayerPanel.js`
- `frontend/src/appModel.js`

---

## Phase 4: DSL v0.3 Runtime Loader

- [ ] Add explicit versioned DSL loading support instead of silently replacing v0.2.
- [ ] Keep existing v0.2 preset IDs working.
- [ ] Add opt-in v0.3 preset IDs:
  - `radial_open_reference_v0_3`
  - `radial_closed_reference_v0_3`
- [ ] Expose `dsl_version` in API manifest output.
- [ ] Add tests that v0.2 and v0.3 resources can coexist.

Implementation targets:

- `src/part_rule_synthesis/impeller_dsl_resources.py`
- `src/part_rule_synthesis/impeller_taxonomy.py`
- `src/part_rule_synthesis/service.py`
- `tests/test_acceptance.py`
- new focused resource-loading tests if useful

---

## Phase 5: Hub Solid Semantics

- [ ] Replace surface-like hub output with a material-domain model:
  - revolve the functional hub profile around Z
  - add bottom/backplate cap face
  - add top cap face around the inlet/bore region
  - remove the center mounting bore cylinder
  - enforce `hub_wall_thickness_mm > 0`
  - enforce `hub_bottom_thickness_mm > 0`
  - enforce `hub_top_cap_thickness_mm > 0`
- [ ] Add hub chamfer/fillet feature records:
  - bore-edge treatment
  - bottom rim treatment
  - top cap transition treatment
  - blade-root-safe exclusion so the chamfer does not erase the functional blade root boundary
- [ ] Generate construction lines for all hub-visible surfaces, not only the functional support surface.
- [ ] Add validity checks for capped hub closure and bore removal.

Implementation targets:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `src/part_rule_synthesis/geometry_validity.py` if a separate validity module is introduced
- backend tests under `tests/`

---

## Phase 6: Hood/Shroud Semantics

- [ ] For open impellers, keep hood/shroud material domain absent.
- [ ] For closed impellers, model the hood as a finite-thickness revolved shell:
  - inner reference surface
  - outer offset/material surface
  - inlet/outlet cap bands
  - nonzero `hood_wall_thickness_mm`
  - hood chamfer/fillet feature records
- [ ] Add closed-hood validity checks for wall thickness, closure, and display graph inclusion.
- [ ] Add open-vs-closed tests:
  - open has no hood material solid
  - open does not render tip reference support
  - closed renders finite hood material geometry

Implementation targets:

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `frontend/src/components/GeometryLayerPanel.js`
- backend/frontend tests

---

## Phase 7: Verification

- [ ] Run backend tests:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
python -m pytest tests -q
python -m compileall -q src scripts
```

- [ ] Run frontend tests and build:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test
npm.cmd run build
```

- [ ] Capture visual smoke screenshots:
  - open v0.3 impeller with hidden tip support and visible numeric curve editor
  - closed v0.3 impeller with finite hood shell visible
  - selected hub control point with numeric values displayed
- [ ] Compare smoke screenshots against the evidence screenshot to confirm the requested visual differences are visible.

---

## Acceptance Criteria

- v0.3 DSL/ontology artifacts exist alongside v0.2 and do not overwrite v0.2.
- Evidence screenshot and evidence README are stored under `docs/evidence`.
- Curve editors have larger handle-editing areas and visible engineering-unit numeric values.
- Open impeller no longer displays the tip reference surface as shaded material geometry.
- Closed impeller still displays the hood/shroud as material geometry.
- Hub is represented as a capped revolved solid with finite bottom/top thickness and a removed mounting bore.
- Hub and closed hood/shroud expose nonzero thickness and chamfer parameters in DSL and runtime manifest.
- Geometry validity includes at least geometric/topological checks for material-domain closure, positive thickness, bore removal, and display/material role separation.
