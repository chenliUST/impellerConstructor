# Impeller Ontology Rule Engine B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement ontology-driven impeller rule engine generation and expose it through the existing frontend viewer.

**Architecture:** Extend the current FastAPI service with impeller facet/preset synthesis while preserving the existing compatibility alias. Reuse the existing CAD exporter for STL/STEP, and add construction-line metadata so the frontend can render rule parameter lines independent of STL mesh triangles.

**Tech Stack:** FastAPI, Pydantic, pytest, CadQuery, React browser ESM, Three.js, Node built-in tests.

---

## Files

- Modify: `src/part_rule_synthesis/api.py`
  Add optional synthesize request fields and `/api/impeller-presets`.
- Modify: `src/part_rule_synthesis/service.py`
  Add impeller ontology facets, presets, selected rules, construction lines, and alias behavior.
- Modify: `tests/test_acceptance.py`
  Add ontology/preset/manifest acceptance tests.
- Modify: `frontend/src/appModel.js`
  Update presets to ontology impeller presets and request payload shape.
- Modify: `frontend/src/apiClient.js`
  Send preset/facets to synthesize.
- Modify: `frontend/src/App.js`
  Default auto-rotate off and pass construction lines into the viewer.
- Modify: `frontend/src/components/ModelViewer.js`
  Remove grid and replace STL triangle wireframe with construction-line rendering.
- Modify: `frontend/src/components/ManifestPanel.js`
  Show facets, selected rules, and inferred regions.
- Modify: `frontend/src/appModel.test.js`
  Test ontology payload and preset metadata.
- Modify: `frontend/src/appFiles.test.js`
  Test viewer source no longer uses `GridHelper` or material `wireframe: true`.

## Tasks

### Task 1: Backend Impeller Ontology Tests

- [ ] Write failing tests for `/api/ontology` facet axes and `/api/impeller-presets`.
- [ ] Write failing tests for synthesizing `part_family_id: "impeller"` with a radial open backward single preset.
- [ ] Write failing tests for invalid facet values and incompatible single/double suction conflicts.

### Task 2: Backend Impeller Ontology Implementation

- [ ] Add `IMPeller_FACETS` and `IMPELLER_PRESETS`.
- [ ] Extend `SynthesizeRequest` with `preset_id` and `facets`.
- [ ] Generate DSL with `part_family: "impeller"`, `preset_id`, `facets`, `selected_rules`, and `rule_implications`.
- [ ] Keep `centrifugal_impeller` as an alias to the radial reference DSL.
- [ ] Add construction lines to `geometry`.
- [ ] Verify backend tests pass.

### Task 3: Frontend Ontology Tests

- [ ] Add tests that frontend presets use `partFamilyId: "impeller"`.
- [ ] Add tests that synthesize payloads include preset and facets.
- [ ] Add source tests proving the viewer has no `GridHelper` and no STL material `wireframe: true`.

### Task 4: Frontend Ontology Observer

- [ ] Update preset data and parameter payloads.
- [ ] Update API client and App state to synthesize per preset/facet.
- [ ] Default auto-rotate to false.
- [ ] Render construction lines as `THREE.LineSegments`.
- [ ] Remove the grid plane.
- [ ] Extend manifest panel.

### Task 5: Verification

- [ ] Run `python -m pytest tests -q`.
- [ ] Run `npm.cmd test`.
- [ ] Run `npm.cmd run build`.
- [ ] Restart backend/frontend.
- [ ] Generate at least radial/open/backward and axial/closed/forward presets in the browser.
- [ ] Capture screenshots showing shaded, construction-line, and combined modes.

