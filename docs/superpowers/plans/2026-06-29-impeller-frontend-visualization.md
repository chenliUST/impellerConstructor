# Impeller Frontend Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React frontend for generating, viewing, and comparing impeller variants from the existing deterministic rule engine.

**Architecture:** Add a standalone `frontend/` app that calls the existing FastAPI API and renders returned STL files with Three.js. Keep presets in frontend data for v0.1 and make only minimal backend changes for local browser access and visual parameter range support.

**Tech Stack:** FastAPI, pytest, React browser ESM, Node built-in tests, Three.js, STLLoader, OrbitControls.

---

## File Structure

- Modify: `src/part_rule_synthesis/api.py`
  Add CORS middleware so a local browser frontend can call the API.
- Modify: `src/part_rule_synthesis/service.py`
  Loosen visual exploration bounds for `blade_count` while preserving current defaults.
- Modify: `tests/test_acceptance.py`
  Add backend tests for CORS and frontend visual parameter compatibility.
- Create: `frontend/package.json`
  Defines static dev, build-check, and Node test scripts.
- Create: `frontend/index.html`
  Browser ESM HTML entrypoint.
- Create: `frontend/src/main.jsx`
  React bootstrap.
- Create: `frontend/src/App.jsx`
  Application shell and state orchestration.
- Create: `frontend/src/appModel.js`
  Presets, parameter schema, payload builders, and export URL helpers.
- Create: `frontend/src/appModel.test.js`
  Unit tests for frontend model helpers.
- Create: `frontend/src/apiClient.js`
  Thin API client around FastAPI endpoints.
- Create: `frontend/src/components/PresetList.jsx`
  Preset selector.
- Create: `frontend/src/components/ParameterPanel.jsx`
  Numeric parameter controls.
- Create: `frontend/src/components/ModelViewer.jsx`
  Three.js STL viewer.
- Create: `frontend/src/components/ManifestPanel.jsx`
  Manifest and export display.
- Create: `frontend/src/styles.css`
  Dense engineering UI styling.

### Task 1: Backend Browser Compatibility

**Files:**
- Modify: `tests/test_acceptance.py`
- Modify: `src/part_rule_synthesis/api.py`
- Modify: `src/part_rule_synthesis/service.py`

- [ ] **Step 1: Write failing backend tests**

Add tests that require local browser CORS and an expanded visual blade-count range:

```python
def test_acceptance_api_allows_vite_frontend_cors_preflight(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    response = client.options(
        "/api/rule-engines/synthesize",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_acceptance_impeller_visual_frontend_can_generate_larger_blade_count(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "centrifugal_impeller"},
    ).json()["engine_id"]

    manifest = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"blade_count": 10, "blade_curve_gain": 1.8, "hub_curve_height_mm": 180.0}},
    ).json()["manifest"]

    assert manifest["parameters"]["blade_count"] == 10
    assert manifest["geometry"]["blade_surface_count"] == 10
    assert "curved_hub_surface" in manifest["geometry"]["cad_features"]
```

- [ ] **Step 2: Run backend tests and verify failure**

Run:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m pytest tests/test_acceptance.py::test_acceptance_api_allows_vite_frontend_cors_preflight tests/test_acceptance.py::test_acceptance_impeller_visual_frontend_can_generate_larger_blade_count -q
```

Expected: CORS test fails before middleware exists, and blade-count test fails with `blade_count out of range`.

- [ ] **Step 3: Implement minimal backend change**

Add `CORSMiddleware` in `api.py` and change the centrifugal impeller `blade_count` max in `service.py` from `7` to `16`.

- [ ] **Step 4: Verify backend tests pass**

Run:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m pytest tests/test_acceptance.py::test_acceptance_api_allows_vite_frontend_cors_preflight tests/test_acceptance.py::test_acceptance_impeller_visual_frontend_can_generate_larger_blade_count -q
```

Expected: `2 passed`.

### Task 2: Frontend Model Layer

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/appModel.test.js`
- Create: `frontend/src/appModel.js`

- [ ] **Step 1: Scaffold package and write failing frontend tests**

Create a frontend package and tests that import missing helpers from `appModel.js`.

```javascript
import { buildInstantiatePayload, exportUrl, parameterSchema, presets } from "./appModel";

test("presets expose bounded impeller parameters", () => {
  expect(presets.length).toBeGreaterThanOrEqual(4);
  for (const preset of presets) {
    const payload = buildInstantiatePayload(preset.parameters);
    expect(payload.parameters.blade_count).toBeGreaterThanOrEqual(parameterSchema.blade_count.min);
    expect(payload.parameters.blade_count).toBeLessThanOrEqual(parameterSchema.blade_count.max);
    expect(payload.parameters.exit_radius_mm).toBeGreaterThan(payload.parameters.inlet_radius_mm);
  }
});

test("exportUrl builds API export paths", () => {
  expect(exportUrl("http://127.0.0.1:8000", "run-abc", "stl")).toBe(
    "http://127.0.0.1:8000/api/model-runs/run-abc/exports/stl"
  );
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd frontend
npm test -- --run
```

Expected: fails because `appModel.js` or its exports do not exist.

- [ ] **Step 3: Implement model helpers**

Create `appModel.js` with preset definitions, parameter schema, clamping, payload building, and export URL construction.

- [ ] **Step 4: Verify frontend model tests pass**

Run:

```powershell
cd frontend
npm test -- --run
```

Expected: model tests pass.

### Task 3: React UI and Three.js Viewer

**Files:**
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/apiClient.js`
- Create: `frontend/src/components/PresetList.jsx`
- Create: `frontend/src/components/ParameterPanel.jsx`
- Create: `frontend/src/components/ModelViewer.jsx`
- Create: `frontend/src/components/ManifestPanel.jsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Implement API client**

Create a client with `synthesizeImpeller(apiBase)`, `instantiate(apiBase, engineId, parameters)`, and `getExportUrl(apiBase, runId, format)`.

- [ ] **Step 2: Implement stateful App shell**

Use the first preset as initial state, call synthesis once, call instantiate on Generate, and store returned manifest plus STL URL.

- [ ] **Step 3: Implement parameter and preset controls**

Render preset buttons and numeric controls from `parameterSchema`; changing a preset replaces parameter state.

- [ ] **Step 4: Implement Three.js viewer**

Load STL with `STLLoader`, frame camera to geometry bounds, use `OrbitControls`, and switch visibility between shaded mesh and wireframe mesh.

- [ ] **Step 5: Implement manifest panel**

Show run id, validation status, source references, export links, parameters, and operation graph.

- [ ] **Step 6: Style the interface**

Create a dense engineering layout with left controls, central viewer, and right manifest panel. Keep all text inside responsive containers.

### Task 4: Build and Visual Verification

**Files:**
- Modify as needed only if verification exposes concrete issues.

- [ ] **Step 1: Run full Python tests**

Run:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests and build**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: unit tests pass and the build-check script succeeds.

- [ ] **Step 3: Start backend and frontend dev servers**

Run backend:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8000
```

Run frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Expected: backend serves API on `http://127.0.0.1:8000`, frontend serves UI on `http://127.0.0.1:5173`.

- [ ] **Step 4: Verify manually in browser**

Open `http://127.0.0.1:5173`, generate at least the reference preset and one high-curvature preset, then verify shaded, wireframe, and combined modes visibly render the STL.
