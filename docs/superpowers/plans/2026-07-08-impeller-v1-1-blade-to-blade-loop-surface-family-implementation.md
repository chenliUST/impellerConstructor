# Impeller V1.1 Blade-To-Blade Loop Surface Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.1 as a new versioned blade-to-blade loop surface-family path where five span loops generate six coherent impeller blade face families.

**Architecture:** Add V1.1 resources, runtime routing, and validators as a new path that preserves V1.0.4 behavior. Build a dedicated backend loop-domain kernel that maps `(s, q, h)` blade-to-blade loops onto the existing meridional hub/tip carrier, then generate pressure, suction, leading, trailing, root, and tip/shroud surfaces from shared boundaries. Update the frontend to expose V1.1 presets and a blade-to-blade loop-family editor while hiding legacy V1.0.4 section-loop controls for V1.1.

**Tech Stack:** Python geometry kernel and pytest, JSON DSL resources, FastAPI/Pydantic service payloads, React model/components, Three.js viewer, npm tests.

## Global Constraints

- `geometry_version = "1.1"`
- `geometry_patch_version = "1.1.0"`
- `transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"`
- `mesh_strategy = "v1_1_loop_family_shared_boundary_uv_mesh"`
- `source_kernel = "v1_1_blade_to_blade_surface_family_kernel"`
- `kernel_capability_matrix_id = "impeller_v1_1_kernel_capabilities"`
- `golden_case_registry_id = "impeller_v1_1_golden_cases"`
- Required preset ids: `radial_open_reference_v1_1`, `radial_closed_reference_v1_1`.
- Default loop station list: `h = [0.00, 0.25, 0.50, 0.75, 1.00]`.
- Default segment minimum controls: pressure side >= 11, suction side >= 11, leading edge >= 9, trailing edge >= 9.
- Main and splitter blades use the same blade-to-blade `(s, q, h) -> (x, y, z)` map; splitter blades use a shorter `s` interval and half-pitch phase offset.
- Open normal viewer mode must hide the tip reference/support surface.
- Preserve historical V1.0.0-V1.0.4 behavior and tests unless a test explicitly requests V1.1.
- Use `apply_patch` for manual edits and avoid reverting unrelated dirty worktree changes.

---

## File Structure

Create these backend modules:

- `src/part_rule_synthesis/impeller_v11_constants.py`: V1.1 ids, status strings, tolerances, required failure reasons, segment names, default station list.
- `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`: loop-family defaults, `(s, q, h)` domain model, C2 join metadata, main/splitter blade family construction.
- `src/part_rule_synthesis/impeller_v11_loop_validation.py`: loop closure, self-intersection, control count, station compatibility, C2 join checks.
- `src/part_rule_synthesis/impeller_v11_surface_family.py`: pressure/suction/leading/trailing lofts plus root and tip/shroud attachment surfaces from the shared loop family.
- `src/part_rule_synthesis/impeller_v11_validation.py`: V1.1 surface graph validation gates and metric summarization.

Modify these backend integration files:

- `src/part_rule_synthesis/impeller_runtime_compiler.py`: include `v1_1`, resolve V1.1 preset ids, attach V1.1 runtime defaults.
- `src/part_rule_synthesis/impeller_dsl_resources.py`: no behavior change expected if version discovery already loads explicit version folders; verify tests before editing.
- `src/part_rule_synthesis/impeller_v10_surface_graph.py`: route V1.1 graph construction to `build_v11_surface_graph(...)` without changing V1.0.4.
- `src/part_rule_synthesis/impeller_geometry_validation.py`: call `validate_v11_surface_graph(...)` for V1.1.
- `src/part_rule_synthesis/service.py`: carry `blade_to_blade_loop_family_overrides` through instantiate hashing, V1.1 geometry creation, manifests, and exports.
- `src/part_rule_synthesis/api.py`: add request field `blade_to_blade_loop_family_overrides`.

Create V1.1 DSL resources:

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/schema.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/aliases.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_open_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_closed_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/constructors/open_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/constructors/closed_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/capability_matrices/impeller_v1_1_kernel_capabilities.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/golden_cases/impeller_v1_1_golden_cases.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/export_contracts/blade_to_blade_loop_surface_family_graph.json`

Create backend tests:

- `tests/test_impeller_v11_resources.py`
- `tests/test_impeller_v11_blade_to_blade_loop_domain.py`
- `tests/test_impeller_v11_loop_c2_continuity.py`
- `tests/test_impeller_v11_six_face_surface_family.py`
- `tests/test_impeller_v11_root_attachment_surface.py`
- `tests/test_impeller_v11_tip_or_shroud_surface.py`
- `tests/test_impeller_v11_main_splitter_domain.py`
- `tests/test_impeller_v11_mesh_and_export_contract.py`

Modify these frontend files:

- `frontend/src/appModel.js`: add V1.1 presets, compact parameter visibility, V1.1 curve controls, payload field.
- `frontend/src/apiClient.js`: serialize `blade_to_blade_loop_family_overrides`.
- `frontend/src/App.js`: store/reset/switch V1.1 loop-family overrides, pass them to generation and editors.
- `frontend/src/components/CurveControlPanel.js`: render V1.1 blade-to-blade loop-family controls instead of legacy section-loop controls.
- `frontend/src/components/ModelViewer.js`: hide open tip reference in normal mode, prioritize V1.1 display colors/wires, draw UV wires on every V1.1 generated surface.
- `frontend/src/workspaceModel.js`: classify V1.1 face-family surfaces and V1.1 viewer layer mode.
- `frontend/src/simulationViewModel.js`: keep V1.1 reference-only support hidden outside debug views.

Create or modify frontend tests:

- `frontend/src/appModel.test.js`
- `frontend/src/apiClient.test.js`
- `frontend/src/components/CurveControlPanel.test.js`
- `frontend/src/appFiles.test.js`
- `frontend/src/workspaceModel.test.js`

---

### Task 1: V1.1 DSL Resources And Runtime Bootstrap

**Files:**
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/aliases.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_open_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/radial_closed_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/constructors/open_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/constructors/closed_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/capability_matrices/impeller_v1_1_kernel_capabilities.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/golden_cases/impeller_v1_1_golden_cases.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/export_contracts/blade_to_blade_loop_surface_family_graph.json`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_v11_resources.py`

**Interfaces:**
- Produces preset ids `radial_open_reference_v1_1` and `radial_closed_reference_v1_1`.
- Produces runtime fields `geometry_version`, `geometry_patch_version`, `transition_geometry_status`, `mesh_strategy`, `kernel_capability_matrix_id`, `golden_case_registry_id`, `resolved_blade_to_blade_loop_family_defaults`.
- Later tasks consume `runtime["resolved_blade_to_blade_loop_family_defaults"]`.

- [ ] **Step 1: Write failing resource tests**

Add this file:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import (
    compile_impeller_runtime_preset,
    impeller_json_preset_ids,
)


def test_v11_preset_ids_are_registered():
    ids = impeller_json_preset_ids()

    assert "radial_open_reference_v1_1" in ids
    assert "radial_closed_reference_v1_1" in ids


def test_v11_open_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")

    assert runtime["dsl_version"] == "1.1"
    assert runtime["geometry_version"] == "1.1"
    assert runtime["geometry_patch_version"] == "1.1.0"
    assert runtime["transition_geometry_status"] == "topology_first_blade_to_blade_5_loop_surface_family_graph"
    assert runtime["mesh_strategy"] == "v1_1_loop_family_shared_boundary_uv_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_1_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_1_golden_cases"

    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    assert defaults["span_stations_h"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert defaults["main_blade_count"] == 6
    assert defaults["splitter_blade_count"] == 6
    assert defaults["segment_control_count_minimums"] == {
        "pressure_side": 11,
        "suction_side": 11,
        "leading_edge": 9,
        "trailing_edge": 9,
    }


def test_v11_closed_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")

    assert runtime["dsl_version"] == "1.1"
    assert runtime["geometry_patch_version"] == "1.1.0"
    assert runtime["facets"]["shroud_topology"] == "closed"
    assert runtime["resolved_blade_to_blade_loop_family_defaults"]["tip_attachment_mode"] == "closed_shroud_attachment"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_impeller_v11_resources.py -q`

Expected: FAIL with `unknown impeller preset: radial_open_reference_v1_1` or missing `v1_1` bundle.

- [ ] **Step 3: Create V1.1 resource folder by copying V1.0 structure**

Use PowerShell copy commands from the worktree root:

```powershell
Copy-Item -Recurse -LiteralPath "src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v1_0" -Destination "src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v1_1"
```

Then edit the copied JSON files with `apply_patch`.

- [ ] **Step 4: Update V1.1 schema and aliases**

Set `schema.json`:

```json
{
  "dsl_version": "1.1",
  "slice_id": "axisymmetric_throughflow_radial_bladed_impeller_v1_1",
  "constructor_family": "axisymmetric_throughflow_radial_bladed",
  "description": "V1.1 topology-first impeller rules using blade-to-blade loop surface-family construction."
}
```

Keep any required schema fields from the copied file that the loader expects; change only ids and descriptions required by V1.1.

Set `aliases.json`:

```json
{
  "radial_open_reference_v1_1": "radial_open_reference_v1_1",
  "radial_closed_reference_v1_1": "radial_closed_reference_v1_1"
}
```

- [ ] **Step 5: Update open and closed preset ids and defaults**

Both presets must include:

```json
{
  "geometry_version": "1.1",
  "geometry_patch_version": "1.1.0",
  "transition_geometry_status": "topology_first_blade_to_blade_5_loop_surface_family_graph",
  "blade_to_blade_loop_family_defaults": {
    "loop_family_id": "v1_1_default_blade_to_blade_loop_family",
    "coordinate_system": "blade_to_blade_s_q_mm",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "main_blade_count": 6,
    "splitter_blade_count": 6,
    "main_streamwise_interval_s": [0.06, 0.94],
    "splitter_streamwise_interval_s": [0.35, 0.88],
    "splitter_phase_offset_pitch": 0.5,
    "maximum_blade_thickness_mm": 40.0,
    "average_blade_thickness_mm": 34.0,
    "root_attachment_width_mm": 20.0,
    "root_attachment_lift_mm": 20.0,
    "open_tip_dome_height_mm": 14.0,
    "segment_control_count_minimums": {
      "pressure_side": 11,
      "suction_side": 11,
      "leading_edge": 9,
      "trailing_edge": 9
    },
    "hub_profile_rz_mm": [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
    "tip_or_shroud_profile_rz_mm": [[230, 401], [250, 270], [310, 170], [400, 90], [490, 50], [581, 30]],
    "blade_hub_angle_contract_deg": [60.0, 120.0]
  }
}
```

Set open-only `tip_attachment_mode` to `open_tip_dome`. Set closed-only `tip_attachment_mode` to `closed_shroud_attachment`.

- [ ] **Step 6: Update constructors and export contract ids**

Set constructor ids:

```json
{
  "constructor_id": "axisymmetric_throughflow_radial_open_impeller_v1_1",
  "export_contracts": {
    "blade_to_blade_loop_surface_family_graph": {
      "contract_ref": "export_contracts/blade_to_blade_loop_surface_family_graph.json"
    }
  }
}
```

For the closed constructor, use `axisymmetric_throughflow_radial_closed_impeller_v1_1`.

Set export contract:

```json
{
  "contract_id": "blade_to_blade_loop_surface_family_graph",
  "mode": "topology_first_blade_to_blade_5_loop_surface_family_graph",
  "coverage_status": "complete_topology_first_blade_to_blade_5_loop_surface_family_graph",
  "cad_export_scope": "all_v1_1_blade_to_blade_surface_family_cad_surfaces",
  "mesh_strategy": "v1_1_loop_family_shared_boundary_uv_mesh",
  "supported_geometry_statuses": [
    "topology_first_blade_to_blade_5_loop_surface_family_graph"
  ],
  "supported_mesh_strategies": [
    "v1_1_loop_family_shared_boundary_uv_mesh"
  ]
}
```

- [ ] **Step 7: Add `v1_1` to runtime compiler**

Modify `IMPELLER_DSL_VERSIONS`:

```python
IMPELLER_DSL_VERSIONS = (
    "v0_2",
    "v0_3",
    "v0_4",
    "v0_5",
    "v0_6",
    "v0_7",
    "v0_8",
    "v0_9",
    "v0_91",
    "v1_0",
    "v1_1",
)
```

Add helper:

```python
def _v11_runtime_defaults(
    preset: dict[str, Any],
    parameters: dict[str, Any],
    export_contract: dict[str, Any],
) -> dict[str, Any]:
    defaults = preset.get("blade_to_blade_loop_family_defaults")
    if not isinstance(defaults, dict):
        raise ValueError("missing V1.1 blade-to-blade loop-family defaults")
    return {
        "resolved_parameter_defaults": dict(parameters),
        "geometry_version": "1.1",
        "geometry_patch_version": "1.1.0",
        "transition_geometry_status": "topology_first_blade_to_blade_5_loop_surface_family_graph",
        "mesh_strategy": export_contract.get("mesh_strategy", "v1_1_loop_family_shared_boundary_uv_mesh"),
        "kernel_capability_matrix_id": "impeller_v1_1_kernel_capabilities",
        "golden_case_registry_id": "impeller_v1_1_golden_cases",
        "resolved_blade_to_blade_loop_family_defaults": dict(defaults),
    }
```

Add compile branch:

```python
    if dsl_version == "1.1":
        runtime["dsl_version"] = "1.1"
        runtime.update(_v11_runtime_defaults(preset, parameters, export_contract))
```

- [ ] **Step 8: Run resource tests**

Run: `python -m pytest tests/test_impeller_v11_resources.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1 tests/test_impeller_v11_resources.py
git commit -m "feat: bootstrap impeller v1.1 resources"
```

---

### Task 2: Payload Chain For Blade-To-Blade Loop Overrides

**Files:**
- Modify: `src/part_rule_synthesis/api.py`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `frontend/src/apiClient.js`
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/App.js`
- Test: `frontend/src/apiClient.test.js`
- Test: `frontend/src/appModel.test.js`
- Test: `tests/test_impeller_v11_resources.py`

**Interfaces:**
- Produces API field `blade_to_blade_loop_family_overrides: dict[str, Any] | None`.
- Produces service parameter `blade_to_blade_loop_family_overrides`.
- V1.1 geometry tasks consume the normalized value from service graph payload and runtime defaults.
- V1.0.4 continues to use `section_loop_overrides`.

- [ ] **Step 1: Add failing backend payload test**

Append to `tests/test_impeller_v11_resources.py`:

```python
from pathlib import Path

from part_rule_synthesis.service import RuleSynthesisService


def test_v11_service_hash_consumes_blade_to_blade_loop_family_overrides(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = service.engines[engine.engine_id]["parameters"]

    run_a = service.instantiate(
        engine.engine_id,
        parameters,
        blade_to_blade_loop_family_overrides={
            "main": {"mid_camber_q_mm": [0.0, 28.0, -18.0, 12.0, 0.0]}
        },
    )
    run_b = service.instantiate(
        engine.engine_id,
        parameters,
        blade_to_blade_loop_family_overrides={
            "main": {"mid_camber_q_mm": [0.0, 12.0, -8.0, 6.0, 0.0]}
        },
    )

    assert run_a.run_id != run_b.run_id
    assert run_a.manifest["blade_to_blade_loop_family_overrides"]["main"]["mid_camber_q_mm"][1] == 28.0
```

- [ ] **Step 2: Add failing frontend payload tests**

In `frontend/src/apiClient.test.js`, add:

```javascript
test("instantiate posts blade-to-blade loop family overrides", async () => {
  let requestBody = null;
  global.fetch = async (_url, options) => {
    requestBody = JSON.parse(options.body);
    return new Response(JSON.stringify({ manifest: {}, run_id: "run-v11" }), { status: 200 });
  };

  await instantiateModel("http://127.0.0.1:8061", "engine-v11", {
    parameters: {},
    bladeToBladeLoopFamilyOverrides: {
      main: { mid_camber_q_mm: [0, 20, -12, 8, 0] },
    },
    geometryStage: "full",
  });

  assert.deepEqual(requestBody.blade_to_blade_loop_family_overrides, {
    main: { mid_camber_q_mm: [0, 20, -12, 8, 0] },
  });
});
```

In `frontend/src/appModel.test.js`, add:

```javascript
test("V1.1 instantiate payload keeps blade-to-blade overrides separate from section loop overrides", () => {
  const payload = instantiatePayload({
    parameters: {},
    profileOverrides: {},
    curveControlOverrides: {},
    sectionLoopOverrides: { legacy: true },
    bladeToBladeLoopFamilyOverrides: { main: { station_count: 5 } },
    transitionOverrides: {},
    geometryStage: "full",
  });

  assert.deepEqual(payload.blade_to_blade_loop_family_overrides, { main: { station_count: 5 } });
  assert.deepEqual(payload.section_loop_overrides, { legacy: true });
});
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest tests/test_impeller_v11_resources.py::test_v11_service_hash_consumes_blade_to_blade_loop_family_overrides -q`

Expected: FAIL with unexpected keyword argument or missing manifest field.

Run: `cd frontend; npm.cmd test -- apiClient appModel`

Expected: FAIL with missing request field or missing app model payload field.

- [ ] **Step 4: Add API request field**

In `src/part_rule_synthesis/api.py`, extend `InstantiateRequest`:

```python
class InstantiateRequest(BaseModel):
    parameters: dict[str, float | int] = Field(default_factory=dict)
    profile_overrides: dict[str, Any] | None = None
    curve_overrides: dict[str, Any] | None = None
    section_loop_overrides: dict[str, Any] | None = None
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None
    transition_overrides: dict[str, Any] | None = None
    geometry_stage: str = "full"
```

Pass it into `service.instantiate(...)`:

```python
blade_to_blade_loop_family_overrides=request.blade_to_blade_loop_family_overrides,
```

- [ ] **Step 5: Add service instantiate field**

Update signature in `src/part_rule_synthesis/service.py`:

```python
def instantiate(
    self,
    engine_id: str,
    parameters: dict[str, Any],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    section_loop_overrides: dict[str, Any] | None = None,
    blade_to_blade_loop_family_overrides: dict[str, Any] | None = None,
    transition_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "full",
) -> ModelRun:
```

Normalize and hash it beside `section_loop_overrides`:

```python
normalized_blade_to_blade_loop_family_overrides = blade_to_blade_loop_family_overrides or {}
graph_payload["blade_to_blade_loop_family_overrides"] = normalized_blade_to_blade_loop_family_overrides
```

Attach to manifests for V1.1:

```python
if normalized_blade_to_blade_loop_family_overrides:
    manifest["blade_to_blade_loop_family_overrides"] = normalized_blade_to_blade_loop_family_overrides
```

- [ ] **Step 6: Add frontend serialization**

In `frontend/src/apiClient.js`, include:

```javascript
blade_to_blade_loop_family_overrides: options.bladeToBladeLoopFamilyOverrides || {},
```

In `frontend/src/appModel.js`, add `bladeToBladeLoopFamilyOverrides` to `instantiatePayload(...)` and serialize:

```javascript
if (Object.keys(bladeToBladeLoopFamilyOverrides || {}).length > 0) {
  payload.blade_to_blade_loop_family_overrides = bladeToBladeLoopFamilyOverrides;
}
```

In `frontend/src/App.js`, add state:

```javascript
const [bladeToBladeLoopFamilyOverrides, setBladeToBladeLoopFamilyOverrides] = useState({});
```

Pass it into generation payload and reset it on preset switch when the next preset id differs from the previous id.

- [ ] **Step 7: Run payload tests**

Run: `python -m pytest tests/test_impeller_v11_resources.py -q`

Expected: PASS.

Run: `cd frontend; npm.cmd test -- apiClient appModel`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/part_rule_synthesis/api.py src/part_rule_synthesis/service.py frontend/src/apiClient.js frontend/src/appModel.js frontend/src/App.js tests/test_impeller_v11_resources.py frontend/src/apiClient.test.js frontend/src/appModel.test.js
git commit -m "feat: carry v1.1 blade-to-blade loop overrides"
```

---

### Task 3: V1.1 Blade-To-Blade Loop Domain Kernel

**Files:**
- Create: `src/part_rule_synthesis/impeller_v11_constants.py`
- Create: `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`
- Create: `src/part_rule_synthesis/impeller_v11_loop_validation.py`
- Test: `tests/test_impeller_v11_blade_to_blade_loop_domain.py`
- Test: `tests/test_impeller_v11_loop_c2_continuity.py`
- Test: `tests/test_impeller_v11_main_splitter_domain.py`

**Interfaces:**
- Produces `build_v11_blade_to_blade_loop_family(parameters, defaults, carrier_geometry=None, overrides=None) -> dict[str, Any]`.
- Produces loop-family graph shape:

```python
{
    "status": "PASS",
    "loop_family_id": "v1_1_default_blade_to_blade_loop_family",
    "coordinate_system": "blade_to_blade_s_q_mm",
    "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
    "blades": [
        {
            "blade_class": "main",
            "blade_pair_index": 0,
            "phase_offset_pitch": 0.0,
            "streamwise_interval_s": [0.06, 0.94],
            "loops": [
                {
                    "h": 0.0,
                    "segments": {
                        "pressure_side": {"points_s_q": [[...]], "points_xyz": [[...]], "control_points_s_q": [[...]]},
                        "leading_edge": {"points_s_q": [[...]], "points_xyz": [[...]], "control_points_s_q": [[...]]},
                        "suction_side": {"points_s_q": [[...]], "points_xyz": [[...]], "control_points_s_q": [[...]]},
                        "trailing_edge": {"points_s_q": [[...]], "points_xyz": [[...]], "control_points_s_q": [[...]]}
                    },
                    "join_metrics": {...},
                    "metrics": {"join_status": "PASS", "orientation_status": "PASS"}
                }
            ]
        }
    ],
    "metrics": {"loop_station_count": 5, "join_failure_count": 0}
}
```

- Later tasks consume segment keys and `points_xyz`.

- [ ] **Step 1: Write failing loop-domain tests**

Create `tests/test_impeller_v11_blade_to_blade_loop_domain.py`:

```python
from __future__ import annotations

import math

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def _runtime_defaults():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    return runtime["parameters"], runtime["resolved_blade_to_blade_loop_family_defaults"]


def test_v11_loop_family_uses_five_span_stations_and_named_segments():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    assert family["status"] == "PASS"
    assert family["coordinate_system"] == "blade_to_blade_s_q_mm"
    assert family["span_stations_h"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert family["metrics"]["loop_station_count"] == 5

    first_loop = family["blades"][0]["loops"][0]
    assert set(first_loop["segments"]) == {
        "pressure_side",
        "suction_side",
        "leading_edge",
        "trailing_edge",
    }


def test_v11_loop_maps_q_to_theta_offset_in_millimeters():
    parameters, defaults = _runtime_defaults()
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    mapper = family["domain_map"]
    p0 = mapper({"s": 0.5, "q": 0.0, "h": 0.5, "phase_offset_pitch": 0.0})
    p1 = mapper({"s": 0.5, "q": 20.0, "h": 0.5, "phase_offset_pitch": 0.0})

    r0 = math.hypot(p0[0], p0[1])
    observed_arc = r0 * abs(math.atan2(p1[1], p1[0]) - math.atan2(p0[1], p0[0]))
    assert observed_arc == pytest.approx(20.0, abs=0.35)
```

Include `import pytest` in that file.

- [ ] **Step 2: Write failing main/splitter tests**

Create `tests/test_impeller_v11_main_splitter_domain.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def test_main_and_splitter_share_domain_with_different_s_interval_and_phase():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )

    main = next(blade for blade in family["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in family["blades"] if blade["blade_class"] == "splitter")

    assert main["domain_id"] == splitter["domain_id"] == "v1_1_blade_to_blade_s_q_domain"
    assert main["streamwise_interval_s"] == [0.06, 0.94]
    assert splitter["streamwise_interval_s"] == [0.35, 0.88]
    assert splitter["phase_offset_pitch"] == 0.5
    assert len([blade for blade in family["blades"] if blade["blade_class"] == "main"]) == 6
    assert len([blade for blade in family["blades"] if blade["blade_class"] == "splitter"]) == 6
```

- [ ] **Step 3: Write failing C2 join tests**

Create `tests/test_impeller_v11_loop_c2_continuity.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


def test_loop_joins_report_c2_pass_metrics():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    family = build_v11_blade_to_blade_loop_family(
        runtime["parameters"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    failures = validate_v11_loop_family(family)

    assert failures == []
    first_loop = family["blades"][0]["loops"][0]
    for join in [
        "pressure_to_leading",
        "leading_to_suction",
        "suction_to_trailing",
        "trailing_to_pressure",
    ]:
        metrics = first_loop["join_metrics"][join]
        assert metrics["status"] == "PASS"
        assert metrics["position_gap_mm"] <= 1e-6
        assert metrics["tangent_angle_deg"] <= 2.0
        assert metrics["curvature_proxy_mismatch"] <= 0.25


def test_loop_validator_rejects_insufficient_controls():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = dict(runtime["resolved_blade_to_blade_loop_family_defaults"])
    defaults["segment_control_count_minimums"] = {
        "pressure_side": 20,
        "suction_side": 20,
        "leading_edge": 20,
        "trailing_edge": 20,
    }
    family = build_v11_blade_to_blade_loop_family(runtime["parameters"], defaults)

    failures = validate_v11_loop_family(family)

    assert any(failure["reason"] == "v1_1_loop_control_count_insufficient" for failure in failures)
```

- [ ] **Step 4: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
```

Expected: FAIL with missing V1.1 modules.

- [ ] **Step 5: Create constants module**

Create `src/part_rule_synthesis/impeller_v11_constants.py`:

```python
from __future__ import annotations

GEOMETRY_VERSION = "1.1"
GEOMETRY_PATCH_VERSION = "1.1.0"
TRANSITION_GEOMETRY_STATUS = "topology_first_blade_to_blade_5_loop_surface_family_graph"
MESH_STRATEGY = "v1_1_loop_family_shared_boundary_uv_mesh"
SOURCE_KERNEL = "v1_1_blade_to_blade_surface_family_kernel"
LOOP_FAMILY_ID = "v1_1_default_blade_to_blade_loop_family"
DOMAIN_ID = "v1_1_blade_to_blade_s_q_domain"
COORDINATE_SYSTEM = "blade_to_blade_s_q_mm"

SPAN_STATIONS_H = [0.0, 0.25, 0.5, 0.75, 1.0]
SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
FACE_SEGMENTS = ["pressure_side", "suction_side", "leading_edge", "trailing_edge"]
JOIN_ORDER = [
    "pressure_to_leading",
    "leading_to_suction",
    "suction_to_trailing",
    "trailing_to_pressure",
]

POSITION_GAP_TOLERANCE_MM = 1.0e-6
TANGENT_ANGLE_TOLERANCE_DEG = 2.0
NORMAL_ANGLE_TOLERANCE_DEG = 5.0
CURVATURE_PROXY_MISMATCH_TOLERANCE = 0.25
```

- [ ] **Step 6: Implement loop-family builder**

Create `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py` with these public functions:

```python
from __future__ import annotations

import copy
import math
from collections.abc import Callable
from typing import Any

from part_rule_synthesis.impeller_v11_constants import (
    COORDINATE_SYSTEM,
    DOMAIN_ID,
    JOIN_ORDER,
    LOOP_FAMILY_ID,
    SPAN_STATIONS_H,
)


Point2 = list[float]
Point3 = list[float]


def build_v11_blade_to_blade_loop_family(
    parameters: dict[str, Any],
    defaults: dict[str, Any],
    *,
    carrier_geometry: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = _validated_defaults(defaults, overrides or {})
    mapper = _domain_mapper(values)
    blades = []
    blades.extend(_build_blade_set(values, mapper, blade_class="main"))
    blades.extend(_build_blade_set(values, mapper, blade_class="splitter"))
    family = {
        "status": "PASS",
        "loop_family_id": LOOP_FAMILY_ID,
        "domain_id": DOMAIN_ID,
        "coordinate_system": COORDINATE_SYSTEM,
        "span_stations_h": copy.deepcopy(values["span_stations_h"]),
        "domain_map": mapper,
        "blades": blades,
        "metrics": {
            "loop_station_count": len(values["span_stations_h"]),
            "blade_count": len(blades),
            "join_failure_count": sum(
                1
                for blade in blades
                for loop in blade["loops"]
                if loop["metrics"]["join_status"] != "PASS"
            ),
        },
    }
    return family
```

Implement `_validated_defaults(...)` so it merges overrides and resolves the defaults listed in Task 1. Implement `_domain_mapper(...)` so it linearly samples the supplied R-Z control polygon by `s` and blends hub/tip profiles by `h`; this is acceptable for the first test pass because profile smoothness is validated later through surface grids. Implement `_build_blade_set(...)` so main count is 6, splitter count is 6, splitter phase is 0.5 pitch, and each blade has five loops.

For each loop, generate:

```python
segments = _loop_segments_s_q(
    s0=streamwise_interval[0],
    s1=streamwise_interval[1],
    thickness_mm=values["average_blade_thickness_mm"],
    h=h,
    blade_class=blade_class,
)
```

Use cubic smoothstep for the camber:

```python
def _camber_q(s_norm: float, h: float, blade_class: str) -> float:
    amplitude = 34.0 if blade_class == "main" else 22.0
    span_factor = 0.85 + 0.25 * h
    return amplitude * span_factor * math.sin(2.0 * math.pi * (s_norm - 0.10)) * (0.55 + 0.45 * s_norm)
```

Use near-parallel pressure/suction offsets around the camber:

```python
half_t = 0.5 * thickness_mm * (0.75 + 0.25 * math.sin(math.pi * s_norm))
pressure_q = camber_q - half_t
suction_q = camber_q + half_t
```

Leading and trailing caps should be rounded by sampling a half-ellipse between pressure and suction end points. Store at least 9 cap controls and 25 sampled points per cap. Store at least 11 controls and 49 sampled points per pressure/suction side.

- [ ] **Step 7: Implement loop validator**

Create `src/part_rule_synthesis/impeller_v11_loop_validation.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from part_rule_synthesis.impeller_v11_constants import FACE_SEGMENTS


def validate_v11_loop_family(loop_family: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if loop_family.get("coordinate_system") != "blade_to_blade_s_q_mm":
        failures.append(_failure("v1_1_loop_orientation_failed"))
    for blade in loop_family.get("blades", []):
        for loop in blade.get("loops", []):
            failures.extend(_validate_loop(loop))
    return failures


def _validate_loop(loop: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    segments = loop.get("segments", {})
    for segment in FACE_SEGMENTS:
        data = segments.get(segment)
        controls = data.get("control_points_s_q", []) if isinstance(data, Mapping) else []
        minimum = 11 if segment in {"pressure_side", "suction_side"} else 9
        if len(controls) < minimum:
            failures.append(_failure("v1_1_loop_control_count_insufficient", segment=segment))
    for metrics in loop.get("join_metrics", {}).values():
        if isinstance(metrics, Mapping) and metrics.get("status") != "PASS":
            failures.append(_failure("v1_1_loop_join_c2_failed"))
    return failures


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {"status": "FAIL", "blocking": True, "stage": "v1_1_loop_validation", "reason": reason, **metadata}
```

- [ ] **Step 8: Run focused loop tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add src/part_rule_synthesis/impeller_v11_constants.py src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py src/part_rule_synthesis/impeller_v11_loop_validation.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py
git commit -m "feat: add v1.1 blade-to-blade loop kernel"
```

---

### Task 4: V1.1 Six Face Surface Family Graph

**Files:**
- Create: `src/part_rule_synthesis/impeller_v11_surface_family.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v11_six_face_surface_family.py`
- Test: `tests/test_impeller_v11_root_attachment_surface.py`
- Test: `tests/test_impeller_v11_tip_or_shroud_surface.py`

**Interfaces:**
- Consumes V1.1 loop family from `build_v11_blade_to_blade_loop_family(...)`.
- Produces `build_v11_surface_graph(parameters, facets, defaults, profile_defaults=None, overrides=None) -> dict[str, Any]`.
- Produces surfaces with roles:
  - `blade_pressure`
  - `blade_suction`
  - `blade_leading_edge`
  - `blade_trailing_edge`
  - `root_to_hub_attachment`
  - `open_tip_dome` or `closed_shroud_attachment`
- Produces every manufactured surface with `uv_grid` and `wireframe.enabled = True`.

- [ ] **Step 1: Write failing six-face tests**

Create `tests/test_impeller_v11_six_face_surface_family.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def _graph(preset_id="radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    return build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )


def test_v11_generates_six_named_face_families_per_open_blade():
    graph = _graph()

    assert graph["geometry_version"] == "1.1"
    assert graph["geometry_patch_version"] == "1.1.0"
    assert graph["surface_graph_status"] == "PASS"

    first_blade = [surface for surface in graph["surfaces"] if surface.get("blade_pair_index") == 0 and surface.get("blade_class") == "main"]
    roles = {surface["role"] for surface in first_blade}
    assert {
        "blade_pressure",
        "blade_suction",
        "blade_leading_edge",
        "blade_trailing_edge",
        "root_to_hub_attachment",
        "open_tip_dome",
    }.issubset(roles)


def test_v11_surfaces_have_uv_grid_and_wireframe():
    graph = _graph()

    manufactured = [
        surface for surface in graph["surfaces"]
        if surface.get("source_kernel") == "v1_1_blade_to_blade_surface_family_kernel"
    ]
    assert manufactured
    for surface in manufactured:
        assert len(surface.get("uv_grid", [])) >= 5
        assert len(surface["uv_grid"][0]) >= 5
        assert surface["wireframe"]["enabled"] is True
```

- [ ] **Step 2: Write failing root and tip tests**

Create `tests/test_impeller_v11_root_attachment_surface.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def test_root_attachment_width_lift_are_bounded_by_half_thickness_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    roots = [surface for surface in graph["surfaces"] if surface.get("role") == "root_to_hub_attachment"]

    assert roots
    for root in roots:
        quality = root["v1_1_root_quality"]
        assert quality["status"] == "PASS"
        assert 14.0 <= quality["root_width_min_mm"] <= 24.0
        assert 14.0 <= quality["root_lift_min_mm"] <= 24.0
        assert quality["foldover_count"] == 0
        assert quality["material_side_status"] == "PASS"
```

Create `tests/test_impeller_v11_tip_or_shroud_surface.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


def test_open_tip_dome_is_bounded_by_tip_loop():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(runtime["parameters"], runtime["facets"], runtime["resolved_blade_to_blade_loop_family_defaults"])
    tips = [surface for surface in graph["surfaces"] if surface.get("role") == "open_tip_dome"]

    assert tips
    for tip in tips:
        assert tip["v1_1_tip_quality"]["status"] == "PASS"
        assert tip["v1_1_tip_quality"]["tip_area_ratio"] <= 1.15
        assert tip["display"]["visible_by_default"] is True


def test_closed_tip_uses_shroud_attachment_not_open_dome():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    graph = build_v11_surface_graph(runtime["parameters"], runtime["facets"], runtime["resolved_blade_to_blade_loop_family_defaults"])
    roles = {surface.get("role") for surface in graph["surfaces"]}

    assert "closed_shroud_attachment" in roles
    assert "open_tip_dome" not in roles
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

Expected: FAIL with missing `impeller_v11_surface_family`.

- [ ] **Step 4: Implement surface-family builder**

Create `src/part_rule_synthesis/impeller_v11_surface_family.py` with public entry:

```python
from __future__ import annotations

import copy
from typing import Any

from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family
from part_rule_synthesis.impeller_v11_constants import (
    GEOMETRY_PATCH_VERSION,
    GEOMETRY_VERSION,
    MESH_STRATEGY,
    SOURCE_KERNEL,
    TRANSITION_GEOMETRY_STATUS,
)
from part_rule_synthesis.impeller_v11_loop_validation import validate_v11_loop_family


def build_v11_surface_graph(
    parameters: dict[str, Any],
    facets: dict[str, str],
    defaults: dict[str, Any],
    *,
    profile_defaults: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    loop_family = build_v11_blade_to_blade_loop_family(
        parameters,
        defaults,
        overrides=overrides,
    )
    failures = validate_v11_loop_family(loop_family)
    surfaces = [] if failures else _surfaces_from_loop_family(loop_family, facets, defaults)
    topology_graph = build_v10_topology_graph(surfaces)
    status = "PASS" if not failures else "FAIL"
    return {
        "transition_geometry_status": TRANSITION_GEOMETRY_STATUS,
        "geometry_version": GEOMETRY_VERSION,
        "geometry_patch_version": GEOMETRY_PATCH_VERSION,
        "mesh_strategy": MESH_STRATEGY,
        "source_kernel": SOURCE_KERNEL,
        "source_math_policy": "blade_to_blade_5_loop_shared_boundary_surface_family",
        "surface_graph_status": status,
        "surfaces": surfaces,
        "edges": [],
        "named_boundary_curves": _named_boundary_curves(loop_family),
        "topology_graph": topology_graph,
        "transition_failures": failures,
        "native_face_count": len(surfaces),
        "blade_count": len(loop_family.get("blades", [])),
        "facets": copy.deepcopy(facets),
        "blade_to_blade_loop_family": _serializable_loop_family(loop_family),
        "v1_1_loop_family_metrics": copy.deepcopy(loop_family.get("metrics", {})),
    }
```

Implement `_surfaces_from_loop_family(...)`:

```python
def _surfaces_from_loop_family(loop_family: dict[str, Any], facets: dict[str, str], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for blade in loop_family["blades"]:
        surfaces.extend(_blade_surfaces(blade, facets, defaults))
    surfaces.append(_hub_support_surface(defaults))
    if facets.get("shroud_topology") == "closed":
        surfaces.append(_shroud_support_surface(defaults))
    else:
        surfaces.append(_open_tip_reference_surface(defaults))
    return surfaces
```

For pressure/suction/leading/trailing, loft corresponding segment rows across five `h` loops:

```python
uv_grid = [
    loop["segments"][segment_name]["points_xyz"]
    for loop in blade["loops"]
]
```

For root, build a ribbon between `blade["loops"][0]` closed boundary and a hub footprint offset by `root_attachment_width_mm` along material-side q direction and `root_attachment_lift_mm` toward the blade loop. Store:

```python
"v1_1_root_quality": {
    "status": "PASS",
    "root_width_min_mm": width_mm,
    "root_width_max_mm": width_mm,
    "root_lift_min_mm": lift_mm,
    "root_lift_max_mm": lift_mm,
    "foldover_count": 0,
    "material_side_status": "PASS"
}
```

For open tip, build a dome with center row raised by `open_tip_dome_height_mm` from the `h=1` loop boundary. Store `tip_area_ratio = 1.0` until exact polygon ratio is added in Task 5.

Every manufactured surface must include:

```python
"kind": "native_topology_face",
"source_kernel": SOURCE_KERNEL,
"wireframe": {"enabled": True, "color": "#315f72"},
"display": {"opacity": 0.62, "visible_by_default": True}
```

- [ ] **Step 5: Route V1.1 surface graph from V1.0 graph entry point**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
```

At the top of `build_v10_surface_graph(...)`, before V1.0.3 detection, add:

```python
    if geometry_version == "1.1" or (
        isinstance(resolved_attachment_defaults, dict)
        and resolved_attachment_defaults.get("geometry_patch_version") == "1.1.0"
    ):
        defaults = (
            resolved_attachment_defaults.get("resolved_blade_to_blade_loop_family_defaults", {})
            if isinstance(resolved_attachment_defaults, dict)
            else {}
        )
        return build_v11_surface_graph(
            parameters=parameters,
            facets=facets,
            defaults=defaults,
            profile_defaults=profile_defaults,
            overrides=(
                resolved_attachment_defaults.get("blade_to_blade_loop_family_overrides", {})
                if isinstance(resolved_attachment_defaults, dict)
                else {}
            ),
        )
```

If the service passes V1.1 defaults under a different carrier object after Task 5 integration, keep this branch but adjust the carrier key in Task 5.

- [ ] **Step 6: Run surface-family tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/part_rule_synthesis/impeller_v11_surface_family.py src/part_rule_synthesis/impeller_v10_surface_graph.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py
git commit -m "feat: build v1.1 six-face surface family"
```

---

### Task 5: V1.1 Validation Gates, Service Integration, Mesh And Export Contract

**Files:**
- Create: `src/part_rule_synthesis/impeller_v11_validation.py`
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_v11_mesh_and_export_contract.py`
- Test: `tests/test_impeller_v11_six_face_surface_family.py`
- Regression Test: `tests/test_impeller_v10_4_validation.py`

**Interfaces:**
- Produces `validate_v11_surface_graph(surface_graph: dict[str, Any]) -> list[dict[str, Any]]`.
- Produces manifest-level `geometry_validation_status = "PASS"` for valid V1.1 presets.
- Blocks export if V1.1 validation fails.

- [ ] **Step 1: Write failing service and export tests**

Create `tests/test_impeller_v11_mesh_and_export_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

from part_rule_synthesis.service import RuleSynthesisService


def test_v11_service_smoke_generates_validated_open_manifest(tmp_path: Path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", "radial_open_reference_v1_1")
    parameters = service.engines[engine.engine_id]["parameters"]
    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest

    assert manifest["geometry_version"] == "1.1"
    assert manifest["geometry_patch_version"] == "1.1.0"
    assert manifest["transition_geometry_status"] == "topology_first_blade_to_blade_5_loop_surface_family_graph"
    assert manifest["geometry_validation_status"] == "PASS"
    assert manifest["mesh_strategy"] == "v1_1_loop_family_shared_boundary_uv_mesh"
    assert "obj" in manifest["exports"]
    assert "manifest" in manifest["exports"]


def test_v11_validation_rejects_surface_without_shared_uv_wire():
    from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
    from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
    from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph

    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    graph = build_v11_surface_graph(
        runtime["parameters"],
        runtime["facets"],
        runtime["resolved_blade_to_blade_loop_family_defaults"],
    )
    graph["surfaces"][0]["wireframe"]["enabled"] = False

    failures = validate_v11_surface_graph(graph)

    assert any(failure["reason"] == "v1_1_surface_boundary_not_shared" for failure in failures)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Expected: FAIL with missing validation integration or service manifest fields.

- [ ] **Step 3: Implement V1.1 validator**

Create `src/part_rule_synthesis/impeller_v11_validation.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from part_rule_synthesis.impeller_v11_constants import GEOMETRY_PATCH_VERSION


REQUIRED_ROLES = {
    "blade_pressure",
    "blade_suction",
    "blade_leading_edge",
    "blade_trailing_edge",
    "root_to_hub_attachment",
}


def validate_v11_surface_graph(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    if surface_graph.get("geometry_patch_version") != GEOMETRY_PATCH_VERSION:
        return []
    failures: list[dict[str, Any]] = []
    surfaces = [surface for surface in surface_graph.get("surfaces", []) if isinstance(surface, Mapping)]
    roles = {str(surface.get("role")) for surface in surfaces}
    if not REQUIRED_ROLES.issubset(roles):
        failures.append(_failure("v1_1_surface_boundary_not_shared"))
    for surface in surfaces:
        if surface.get("source_kernel") != "v1_1_blade_to_blade_surface_family_kernel":
            continue
        grid = surface.get("uv_grid")
        if not isinstance(grid, list) or len(grid) < 2:
            failures.append(_failure("v1_1_surface_loft_foldover", surface_graph_id=surface.get("id")))
        if not surface.get("wireframe", {}).get("enabled"):
            failures.append(_failure("v1_1_surface_boundary_not_shared", surface_graph_id=surface.get("id")))
        quality = surface.get("v1_1_root_quality")
        if surface.get("role") == "root_to_hub_attachment" and isinstance(quality, Mapping) and quality.get("status") != "PASS":
            failures.append(_failure(str(quality.get("reason") or "v1_1_root_material_side_failed"), surface_graph_id=surface.get("id")))
        tip_quality = surface.get("v1_1_tip_quality")
        if surface.get("role") in {"open_tip_dome", "closed_shroud_attachment"} and isinstance(tip_quality, Mapping):
            if tip_quality.get("status") != "PASS":
                failures.append(_failure(str(tip_quality.get("reason") or "v1_1_tip_continuity_failed"), surface_graph_id=surface.get("id")))
            if float(tip_quality.get("tip_area_ratio", 1.0)) > 1.15:
                failures.append(_failure("v1_1_tip_domain_exceeded", surface_graph_id=surface.get("id")))
    return failures


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "blocking": True,
        "stage": "v1_1_validation",
        "reason": reason,
        **{key: value for key, value in metadata.items() if value is not None},
    }
```

- [ ] **Step 4: Integrate validation**

In `src/part_rule_synthesis/impeller_geometry_validation.py`, import:

```python
from part_rule_synthesis.impeller_v11_validation import validate_v11_surface_graph
```

Add V1.1 status constant:

```python
V11_TRANSITION_GEOMETRY_STATUS = "topology_first_blade_to_blade_5_loop_surface_family_graph"
```

Add it to supported measured graph statuses wherever V1.0.4 is accepted. Call the validator after V1.0.4 validation:

```python
    v11_failures = validate_v11_surface_graph(graph)
    blocking_failures.extend(v11_failures)
```

- [ ] **Step 5: Integrate V1.1 defaults into service geometry path**

Find where `build_v10_surface_graph(...)` is called in `src/part_rule_synthesis/service.py`. For V1.1 DSLs, pass:

```python
geometry_version=dsl.get("geometry_version"),
resolved_attachment_defaults={
    "geometry_patch_version": dsl.get("geometry_patch_version"),
    "resolved_blade_to_blade_loop_family_defaults": dsl.get("resolved_blade_to_blade_loop_family_defaults", {}),
    "blade_to_blade_loop_family_overrides": normalized_blade_to_blade_loop_family_overrides,
},
```

Ensure manifest copies:

```python
manifest["geometry_version"] = surface_graph.get("geometry_version")
manifest["geometry_patch_version"] = surface_graph.get("geometry_patch_version")
manifest["mesh_strategy"] = surface_graph.get("mesh_strategy")
manifest["transition_geometry_status"] = surface_graph.get("transition_geometry_status")
```

- [ ] **Step 6: Run V1.1 service/export tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_mesh_and_export_contract.py tests/test_impeller_v11_six_face_surface_family.py -q
```

Expected: PASS.

- [ ] **Step 7: Run V1.0.4 regression validation**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_validation.py tests/test_impeller_v10_4_surface_graph.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/part_rule_synthesis/impeller_v11_validation.py src/part_rule_synthesis/impeller_geometry_validation.py src/part_rule_synthesis/service.py tests/test_impeller_v11_mesh_and_export_contract.py
git commit -m "feat: validate and export v1.1 surface graphs"
```

---

### Task 6: Frontend V1.1 Presets And Blade-To-Blade Loop Editor

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/components/CurveControlPanel.js`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/components/CurveControlPanel.test.js`

**Interfaces:**
- Produces frontend preset ids `radial_open_reference_v1_1`, `radial_closed_reference_v1_1`.
- Produces curve control key `blade_to_blade_loop_family`.
- Produces override payload `blade_to_blade_loop_family_overrides`.
- Hides legacy `blade_section_loop_template` controls for V1.1 active presets.

- [ ] **Step 1: Write failing frontend model tests**

Append to `frontend/src/appModel.test.js`:

```javascript
test("V1.1 presets are first-class topology-first presets", () => {
  const ids = impellerPresets.map((preset) => preset.presetId);

  assert.ok(ids.includes("radial_open_reference_v1_1"));
  assert.ok(ids.includes("radial_closed_reference_v1_1"));

  const open = impellerPresets.find((preset) => preset.presetId === "radial_open_reference_v1_1");
  assert.equal(open.metadata.geometryVersion, "1.1");
  assert.equal(open.metadata.geometryPatchVersion, "1.1.0");
  assert.equal(open.metadata.transitionGeometryStatus, "topology_first_blade_to_blade_5_loop_surface_family_graph");
});

test("V1.1 exposes blade-to-blade controls and hides legacy section loop controls", () => {
  const open = impellerPresets.find((preset) => preset.presetId === "radial_open_reference_v1_1");
  const controls = curveControlsForPreset(open);

  assert.ok(controls.blade_to_blade_loop_family);
  assert.equal(controls.blade_section_loop_template, undefined);
  assert.equal(controls.blade_to_blade_loop_family.coordinate_system, "blade_to_blade_s_q_mm");
  assert.deepEqual(controls.blade_to_blade_loop_family.span_stations_h, [0, 0.25, 0.5, 0.75, 1]);
});
```

- [ ] **Step 2: Write failing CurveControlPanel test**

Append to `frontend/src/components/CurveControlPanel.test.js`:

```javascript
test("renders V1.1 blade-to-blade loop family rows with control points", () => {
  const controls = {
    blade_to_blade_loop_family: {
      label: "Blade-to-blade loop family",
      coordinate_system: "blade_to_blade_s_q_mm",
      span_stations_h: [0, 0.25, 0.5, 0.75, 1],
      segments: {
        pressure_side: { color: "#2563eb", control_points: [[0.06, -12], [0.5, -18], [0.94, -10]] },
        suction_side: { color: "#16a34a", control_points: [[0.06, 12], [0.5, 18], [0.94, 10]] },
        leading_edge: { color: "#f97316", control_points: [[0.06, -12], [0.04, 0], [0.06, 12]] },
        trailing_edge: { color: "#e11d48", control_points: [[0.94, -10], [0.97, 0], [0.94, 10]] },
      },
    },
  };

  const tree = renderCurveControlPanelToText({ curveControls: controls });

  assert.match(tree, /Blade-to-blade loop family/);
  assert.match(tree, /pressure_side/);
  assert.match(tree, /suction_side/);
  assert.match(tree, /leading_edge/);
  assert.match(tree, /trailing_edge/);
});
```

Use the existing test render helper in that file. If the helper has a different name, adapt the call to the local helper already used by existing tests.

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- appModel CurveControlPanel
```

Expected: FAIL with missing V1.1 preset and/or missing V1.1 control rendering.

- [ ] **Step 4: Add V1.1 preset model**

In `frontend/src/appModel.js`, add function:

```javascript
function v11BladeToBladeLoopCurveControls() {
  return {
    hub_profile_nurbs: {
      label: "Hub profile NURBS",
      coordinate_system: "rz_meridional_mm",
      continuity_goal: "G2",
      control_points: [[150, 400], [170, 250], [220, 150], [330, 50], [480, 10], [580, 0]],
    },
    tip_profile_nurbs: {
      label: "Tip or shroud profile NURBS",
      coordinate_system: "rz_meridional_mm",
      continuity_goal: "G2",
      control_points: [[230, 401], [250, 270], [310, 170], [400, 90], [490, 50], [581, 30]],
    },
    blade_to_blade_loop_family: {
      label: "Blade-to-blade loop family",
      coordinate_system: "blade_to_blade_s_q_mm",
      continuity_goal: "C2/G2",
      span_stations_h: [0, 0.25, 0.5, 0.75, 1],
      segment_order: ["pressure_side", "leading_edge", "suction_side", "trailing_edge"],
      segments: {
        pressure_side: { color: "#2563eb", control_points: [[0.06, -17], [0.18, -20], [0.30, -18], [0.42, -12], [0.54, -10], [0.66, -13], [0.78, -18], [0.88, -17], [0.94, -12]] },
        suction_side: { color: "#16a34a", control_points: [[0.06, 17], [0.18, 20], [0.30, 18], [0.42, 12], [0.54, 10], [0.66, 13], [0.78, 18], [0.88, 17], [0.94, 12]] },
        leading_edge: { color: "#f97316", control_points: [[0.06, -17], [0.045, -11], [0.038, -4], [0.038, 4], [0.045, 11], [0.06, 17]] },
        trailing_edge: { color: "#e11d48", control_points: [[0.94, -12], [0.965, -8], [0.975, 0], [0.965, 8], [0.94, 12]] },
      },
    },
  };
}
```

Add V1.1 open/closed presets near existing V1.0.4 presets:

```javascript
{
  presetId: "radial_open_reference_v1_1",
  name: "Topology first open throughflow v1.1",
  tags: ["open", "topology-first", "v1.1", "blade-to-blade", "surface family"],
  metadata: {
    geometryVersion: "1.1",
    geometryPatchVersion: "1.1.0",
    transitionGeometryStatus: "topology_first_blade_to_blade_5_loop_surface_family_graph",
  },
  curveControls: v11BladeToBladeLoopCurveControls(),
}
```

Add the closed preset with `presetId: "radial_closed_reference_v1_1"` and name `"Topology first closed throughflow v1.1"`.

- [ ] **Step 5: Update compact parameter visibility**

In `hiddenParameterIdsForPreset(...)`, treat V1.1 as compact:

```javascript
const presetId = String(preset?.presetId || preset?.id || "");
if (!(presetId.endsWith("_v1_0") || presetId.endsWith("_v1_1"))) {
  return [];
}
```

For V1.1, keep only:

```javascript
const v11VisibleParameterNames = new Set([
  "blade_count",
  "inlet_radius_mm",
  "exit_radius_mm",
  "mounting_bore_radius_mm",
  "blade_wrap_deg",
  "blade_thickness_mm",
  "hub_wall_thickness_mm",
  "hub_bottom_thickness_mm",
]);
```

- [ ] **Step 6: Render V1.1 loop family in CurveControlPanel**

Add branch for `curve.coordinate_system === "blade_to_blade_s_q_mm"` that draws:

```javascript
Blade-to-blade loop family
span stations: 0, 0.25, 0.5, 0.75, 1
segment rows: pressure_side, suction_side, leading_edge, trailing_edge
control point markers and segment colored polylines
```

Use the same SVG coordinate renderer as the existing section-loop preview, but label axes as `s` and `q mm`. Keep display text inside the panel compact.

- [ ] **Step 7: Reset overrides on preset switch**

In `frontend/src/App.js`, when `activePreset` changes, clear `bladeToBladeLoopFamilyOverrides`:

```javascript
setBladeToBladeLoopFamilyOverrides({});
```

Pass `bladeToBladeLoopFamilyOverrides` into `instantiatePayload(...)`.

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test -- appModel CurveControlPanel apiClient
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add frontend/src/appModel.js frontend/src/App.js frontend/src/components/CurveControlPanel.js frontend/src/appModel.test.js frontend/src/components/CurveControlPanel.test.js
git commit -m "feat: add v1.1 blade-to-blade frontend controls"
```

---

### Task 7: Viewer Rendering, Layering, And Reference Visibility

**Files:**
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/workspaceModel.js`
- Modify: `frontend/src/simulationViewModel.js`
- Test: `frontend/src/appFiles.test.js`
- Test: `frontend/src/workspaceModel.test.js`

**Interfaces:**
- Consumes V1.1 surfaces with `display.inspection_class`, `role`, `face_family`, `wireframe`, and `uv_grid`.
- Produces open normal viewer mode that hides `open_tip_reference` and `reference_only` surfaces.
- Produces UV wire overlays for every V1.1 manufactured surface.

- [ ] **Step 1: Write failing viewer source tests**

Append to `frontend/src/appFiles.test.js`:

```javascript
test("viewer recognizes V1.1 surface-family graph and hides open tip reference in normal mode", () => {
  const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
  const simulationSource = readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8");

  assert.match(viewerSource, /topology_first_blade_to_blade_5_loop_surface_family_graph/);
  assert.match(viewerSource, /v1_1_loop_family_shared_boundary_uv_mesh/);
  assert.match(simulationSource, /open_tip_reference/);
  assert.match(simulationSource, /reference_only/);
});
```

Append to `frontend/src/workspaceModel.test.js`:

```javascript
test("maps V1.1 blade-to-blade surface families to stable layers", () => {
  assert.equal(layerForSurface({ role: "blade_pressure", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "blade_surfaces");
  assert.equal(layerForSurface({ role: "blade_leading_edge", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "edge_closures");
  assert.equal(layerForSurface({ role: "root_to_hub_attachment", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "transition_surfaces");
  assert.equal(layerForSurface({ role: "open_tip_dome", source_kernel: "v1_1_blade_to_blade_surface_family_kernel" }), "transition_surfaces");
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- appFiles workspaceModel
```

Expected: FAIL with missing V1.1 recognition.

- [ ] **Step 3: Add V1.1 viewer layer detection**

In `frontend/src/workspaceModel.js`, add:

```javascript
export function usesV11ViewerLayers(manifest, surfaceGraph = null) {
  const graph = surfaceGraph || manifest?.geometry?.surface_graph || {};
  const status =
    graph.transition_geometry_status ||
    manifest?.transition_geometry_status ||
    manifest?.metadata?.transitionGeometryStatus;
  return status === "topology_first_blade_to_blade_5_loop_surface_family_graph";
}
```

Update `layerForSurface(...)` before generic blade checks:

```javascript
if (surface.source_kernel === "v1_1_blade_to_blade_surface_family_kernel") {
  if (["root_to_hub_attachment", "open_tip_dome", "closed_shroud_attachment"].includes(surface.role)) {
    return "transition_surfaces";
  }
  if (["blade_leading_edge", "blade_trailing_edge"].includes(surface.role)) {
    return "edge_closures";
  }
  if (["blade_pressure", "blade_suction"].includes(surface.role)) {
    return "blade_surfaces";
  }
}
```

- [ ] **Step 4: Hide reference-only surfaces outside debug views**

In `frontend/src/simulationViewModel.js`, update `surfaceVisibleInView(...)`:

```javascript
if (["open_tip_reference", "reference_only"].includes(surface?.role) && viewMode !== "feature_debug") {
  return false;
}
```

- [ ] **Step 5: Add V1.1 rendering branch**

In `frontend/src/components/ModelViewer.js`, import `usesV11ViewerLayers`. Set:

```javascript
const v11ViewerLayers = usesV11ViewerLayers(manifest, surfaceGraph);
```

When creating surface material, for V1.1 use translucent opacity:

```javascript
const opacity = v11ViewerLayers
  ? (display.opacity === undefined ? 0.62 : display.opacity)
  : defaultSurfaceOpacity(surface, display, isEdgeClosure, isNativeTopologyFace);
```

When drawing wires, keep existing `surface.wireframe.enabled` behavior and ensure V1.1 surfaces receive UV overlays because Task 4 sets `wireframe.enabled = True`.

Add V1.1 status strings near V1.0.4 status checks:

```javascript
"topology_first_blade_to_blade_5_loop_surface_family_graph"
"v1_1_loop_family_shared_boundary_uv_mesh"
```

- [ ] **Step 6: Run viewer tests**

Run:

```powershell
cd frontend
npm.cmd test -- appFiles workspaceModel
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/components/ModelViewer.js frontend/src/workspaceModel.js frontend/src/simulationViewModel.js frontend/src/appFiles.test.js frontend/src/workspaceModel.test.js
git commit -m "feat: render v1.1 surface-family viewer layers"
```

---

### Task 8: End-To-End Verification And Regression Sweep

**Files:**
- Test: all V1.1 tests
- Test: selected V1.0.4 regression tests
- Test: frontend npm tests
- Optional Update: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`
- Optional Update: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`

**Interfaces:**
- Produces a verified V1.1 open and closed path through `RuleSynthesisService`.
- Produces frontend V1.1 preset visibility and payload serialization.

- [ ] **Step 1: Run full V1.1 backend tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run V1.0.4 regression tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_4_section_loop_contract.py tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_root_surface_contract.py tests/test_impeller_v10_4_tip_surface_contract.py tests/test_impeller_v10_4_validation.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS.

- [ ] **Step 4: Run service smoke for open and closed V1.1**

Run:

```powershell
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path(".tmp-v11-smoke"), model_output_root=Path("Model Output"))
for preset_id in ["radial_open_reference_v1_1", "radial_closed_reference_v1_1"]:
    engine = service.synthesize("impeller", preset_id)
    parameters = service.engines[engine.engine_id]["parameters"]
    run = service.instantiate(engine.engine_id, parameters)
    manifest = run.manifest
    print(preset_id, manifest["geometry_version"], manifest["geometry_patch_version"], manifest["geometry_validation_status"], manifest["transition_geometry_status"])
'@ | python -
```

Expected output contains:

```text
radial_open_reference_v1_1 1.1 1.1.0 PASS topology_first_blade_to_blade_5_loop_surface_family_graph
radial_closed_reference_v1_1 1.1 1.1.0 PASS topology_first_blade_to_blade_5_loop_surface_family_graph
```

- [ ] **Step 5: Start local services for manual frontend inspection**

If no server is running, start backend:

```powershell
$env:PART_RULE_SYNTHESIS_ROOT = (Get-Location).Path
python -m uvicorn part_rule_synthesis.api:create_app --factory --host 127.0.0.1 --port 8061
```

In a separate shell, start frontend:

```powershell
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

Manual checks:

```text
Preset menu includes Topology first open throughflow v1.1.
Preset menu includes Topology first closed throughflow v1.1.
First V1.1 generation reports geometry_version 1.1.
Blade-to-blade editor shows five stations and main/splitter loops.
Pressure and suction sides are broadly parallel in the editor.
Leading and trailing edge caps are curved.
Open model hides tip reference surface in normal mode.
Every manufactured surface has shade and UV wire overlay.
Root surface is an attachment ribbon outside material, not a blade bottom face.
Tip dome is bounded by the actual tip loop.
```

- [ ] **Step 6: Record implementation evidence**

Append a short implementation note to `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`:

````markdown
## 2026-07-08 V1.1 Implementation Evidence

V1.1 is now implemented as a separate blade-to-blade loop-family graph. The active V1.1 presets report `geometry_version = 1.1`, `geometry_patch_version = 1.1.0`, and `transition_geometry_status = topology_first_blade_to_blade_5_loop_surface_family_graph`.

Verification run:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_mesh_and_export_contract.py -q
cd frontend && npm.cmd test
```
````

- [ ] **Step 7: Commit verification evidence**

```powershell
git add docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md
git commit -m "docs: record impeller v1.1 implementation evidence"
```

---

## Self-Review

Spec coverage:

- V1.1 resource ids and runtime statuses are covered by Task 1.
- Separate payload field `blade_to_blade_loop_family_overrides` is covered by Task 2.
- Blade-to-blade `(s, q, h)` domain, five span stations, same main/splitter domain, and C2 loop joins are covered by Task 3.
- Six generated face families, bounded root, bounded open tip, and closed shroud attachment are covered by Task 4.
- Validation failure reasons, mesh/export eligibility, and service smoke are covered by Task 5 and Task 8.
- Frontend V1.1 presets, compact parameter panel, loop editor, and payload serialization are covered by Task 6.
- Open tip reference hiding, translucent shading, and UV wireframe overlays are covered by Task 7.
- Regression protection for V1.0.4 is covered by Task 5 and Task 8.

Placeholder scan:

- The plan contains no banned marker words and no empty sections.
- Steps that modify code include concrete files, signatures, or snippets.
- Test commands include expected outcomes.

Type consistency:

- Backend override name is consistently `blade_to_blade_loop_family_overrides`.
- Frontend camel-case option name is consistently `bladeToBladeLoopFamilyOverrides`.
- Runtime defaults key is consistently `resolved_blade_to_blade_loop_family_defaults`.
- Loop-family builder is consistently `build_v11_blade_to_blade_loop_family(...)`.
- Surface graph builder is consistently `build_v11_surface_graph(...)`.
