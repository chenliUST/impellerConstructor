# Axisymmetric Throughflow NURBS Impeller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one focused impeller class whose hub and tip/shroud are NURBS profiles revolved about Z, and whose blade pressure/suction sides are high-density NURBS-like surfaces conforming to those boundary surfaces.

**Architecture:** Add a new focused kernel module and dispatch to it only when the preset parameters include `blade_wrap_deg`. Keep the existing legacy kernel available for old presets/tests, but make the frontend default to two new open/closed NURBS presets with a reduced parameter set. Render shaded geometry from `surface_graph` UV grids in the frontend so shade and construction wireframe share the same sampled surfaces.

**Tech Stack:** Python 3.12, FastAPI service layer, existing CadQuery export path, React/Three.js frontend.

---

### Task 1: Add RED backend tests

**Files:**
- Modify: `tests/test_impeller_kernel.py`
- Modify: `tests/test_acceptance.py`

- [ ] Add tests asserting the new kernel returns `axisymmetric_throughflow_nurbs_kernel`, high sampling density, NURBS profile metadata, open and closed surface roles, and exact pressure/suction boundary conformance at `v=0` and `v=1`.

- [ ] Run:

```powershell
python -m pytest tests/test_impeller_kernel.py::test_axisymmetric_nurbs_open_impeller_uses_revolved_hub_tip_and_conformal_blade_sides tests/test_impeller_kernel.py::test_axisymmetric_nurbs_closed_impeller_uses_shroud_surface_for_tip_boundary -q
```

Expected: FAIL because the new kernel and presets do not exist yet.

### Task 2: Implement the focused kernel

**Files:**
- Create: `src/part_rule_synthesis/impeller_kernels/__init__.py`
- Create: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `src/part_rule_synthesis/impeller_kernel.py`

- [ ] Implement cubic NURBS/Bezier profile evaluation for hub/tip meridional curves.
- [ ] Generate revolve grids with `surface_u_count=41`, `surface_v_count=33` for hub/tip/shroud.
- [ ] Generate blade pressure/suction grids with `blade_u_count=41`, `blade_v_count=17`.
- [ ] Ensure pressure/suction `v=0` points lie on hub revolve surface and `v=1` points lie on tip/shroud revolve surface.
- [ ] Return the existing manifest-compatible keys: `kernel`, `sampled_blades`, `surface_graph`, `construction_lines`, `validity`, `blade_surface`, `hub_surface`, `cad_features`.

### Task 3: Add taxonomy presets and parameter specs

**Files:**
- Modify: `src/part_rule_synthesis/impeller_taxonomy.py`
- Modify: `src/part_rule_synthesis/service.py`

- [ ] Add `axisymmetric_nurbs_open_throughflow_study`.
- [ ] Add `axisymmetric_nurbs_closed_throughflow_study`.
- [ ] Add numeric parameter specs for `blade_wrap_deg` and `blade_lean_deg`.
- [ ] Preserve legacy presets for compatibility.

### Task 4: Update frontend to focus the interaction

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/components/ParameterPanel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/appModel.test.js`

- [ ] Frontend presets should only expose the two new NURBS presets.
- [ ] Frontend parameter sliders should only expose key parameters: blade count, inlet/outlet radii, inlet/outlet blade heights, hub curve height, blade wrap, blade lean, blade thickness.
- [ ] Remove the facet editor from the visible first workflow.
- [ ] Render shaded surfaces from `manifest.geometry.surface_graph.surfaces[*].uv_grid` before falling back to STL.

### Task 5: Verify

**Files:**
- Test: `tests`
- Test: `frontend`

- [ ] Run backend tests:

```powershell
python -m pytest tests -q
python -m compileall -q src scripts
```

- [ ] Run frontend tests/build:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

- [ ] Start backend/frontend and visually smoke-test both new presets.
