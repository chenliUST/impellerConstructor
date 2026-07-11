# Impeller Engineering Parameter Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current card-style Parameter Inspection UI with read-only engineering views that highlight authoritative construction features in red and dimensions in blue, including synchronized S-Q and isolated-blade 3D inspection.

**Architecture:** Extend the existing V1.1.3 `parameter_inspection` payload with additive parameter groups, feature primitives, and dimension definitions while preserving V1.1.2 geometry. Parse the evidence into a frontend engineering-inspection model; render Top, Meridional, and S-Q through SVG and render one isolated blade through the existing Three.js surface-graph path. Selection is keyed by stable `parameter_id` and shared across the 2D and 3D panes.

**Tech Stack:** Python 3 geometry/evidence builders and pytest; JSON manifest contract; React without JSX; SVG; Three.js; Node test runner; Playwright browser smoke.

## Global Constraints

- Preserve V1.1.2 impeller geometry construction and export behavior.
- Extend the current V1.1.3 inspection contract additively; do not create a Drawing DSL.
- Keep only `Top`, `Meridional`, and `S-Q + Blade` inspection tabs.
- The workspace is read-only: no drag, parameter editing, or value mutation.
- Selected construction features are red; dimensions are blue; context contours are thin black lines on white.
- Do not render UV lines, triangle mesh, parameter leaders, or whole-face highlight fills.
- Show dimensions only for the one selected parameter.
- Use existing React, Three.js, SVG, Python, and Node dependencies; add no package.
- Keep parameter controls outside the drawing and prevent text from covering critical contours.

---

## File Structure

**Backend**

- Modify `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`: build and validate parameter groups, engineering feature primitives, and dimensions.
- Modify `src/part_rule_synthesis/impeller_runtime_compiler.py`: advertise engineering inspection capabilities without changing geometry version.
- Modify `tests/test_impeller_v11_3_parameter_inspection_contract.py`: retain base contract regressions and add coverage assertions.
- Create `tests/test_impeller_v11_3_engineering_inspection.py`: focused primitive, dimension, and measurement-consistency tests.

**Frontend model**

- Modify `frontend/src/parameterInspectionModel.js`: parse the additive evidence and own parameter/group selection.
- Modify `frontend/src/parameterInspectionModel.test.js`: validate groups, features, dimensions, and equivalent selection across blade/station changes.
- Create `frontend/src/engineeringDrawingModel.js`: pure projection and dimension-layout functions.
- Create `frontend/src/engineeringDrawingModel.test.js`: projection, dimension, clipping, and style tests.

**Frontend components**

- Create `frontend/src/components/ParameterFeatureBrowser.js`: compact collapsible parameter tree.
- Create `frontend/src/components/ParameterFeatureBrowser.test.js`: source-contract and interaction-state tests.
- Create `frontend/src/components/EngineeringDrawingView.js`: Top, Meridional, and S-Q SVG engineering renderer.
- Create `frontend/src/components/EngineeringDrawingView.test.js`: engineering primitive and style tests.
- Create `frontend/src/components/BladeFeatureScene.js`: isolated blade Three.js view with line/point feature highlight.
- Create `frontend/src/components/BladeFeatureScene.test.js`: isolation, no-face-highlight, and lifecycle tests.
- Modify `frontend/src/components/ParameterInspectionWorkspace.js`: three-tab shell and synchronized S-Q/3D split.
- Modify `frontend/src/components/ParameterInspectionWorkspace.test.js`: layout, tabs, selection, and no-overlay controls.
- Modify `frontend/src/styles.css`: compact engineering workspace and print-like line styling.
- Remove obsolete `frontend/src/components/InspectionScene.js`, `InspectionScene.test.js`, `ParameterAnnotationOverlay.js`, and its tests only after no remaining imports exist.

**Acceptance and evidence**

- Modify `frontend/scripts/parameter-inspection-visual-smoke.cjs`: Top, Meridional, S-Q + Blade coverage.
- Create `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/`: browser screenshots.
- Modify `docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md`: append implementation evidence.
- Modify `docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md`: record feature-level inspection lessons.

---

### Task 1: Authoritative Engineering Inspection Records

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- Test: `tests/test_impeller_v11_3_engineering_inspection.py`

**Interfaces:**
- Consumes: existing `build_parameter_inspection_contract(surface_graph: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: `parameter_groups: list[dict]`, `parameters: list[dict]`, each parameter carrying `parameter_id`, `group_id`, values, views, `feature_geometry`, `dimension_definition`, and `selection_scope`.

- [ ] **Step 1: Write failing group and primitive coverage tests**

Create a generated open-preset fixture through the same V1.1 service helper used by the existing contract test, then assert:

```python
required_groups = {
    "hub", "tip_or_shroud", "blade_placement", "spanwise_pose",
    "section_loop", "attachments", "inspection_results",
}
assert required_groups <= {group["group_id"] for group in contract["parameter_groups"]}

parameter = next(item for item in contract["parameters"] if item["parameter_id"].endswith("thickness"))
assert parameter["applicable_views"] == ["s_q", "blade_3d"]
assert {item["kind"] for item in parameter["feature_geometry"]} >= {"point", "local_frame"}
assert parameter["dimension_definition"]["kind"] == "linear"
```

Also assert all primitive ids and parameter ids are unique.

- [ ] **Step 2: Run the new test and confirm RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -q
```

Expected: FAIL because `parameter_groups` and `parameters` are absent.

- [ ] **Step 3: Add minimal record builders**

Add private builders with exact signatures:

```python
def _parameter_group(group_id: str, label: str, order: int, *, collapsed: bool = True) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "label": label,
        "order": order,
        "collapsed": collapsed,
    }

def _inspection_parameter(
    *, parameter_id: str, group_id: str, label: str,
    requested_value: Any, resolved_value: Any, unit: str,
    applicable_views: Sequence[str], feature_geometry: Sequence[Mapping[str, Any]],
    dimension_definition: Mapping[str, Any] | None,
    selection_scope: Mapping[str, Any], order: int,
) -> dict[str, Any]:
    return {
        "parameter_id": parameter_id,
        "group_id": group_id,
        "label": label,
        "requested_value": copy.deepcopy(requested_value),
        "resolved_value": copy.deepcopy(resolved_value),
        "unit": unit,
        "applicable_views": list(applicable_views),
        "feature_geometry": copy.deepcopy(list(feature_geometry)),
        "dimension_definition": copy.deepcopy(dimension_definition),
        "selection_scope": copy.deepcopy(dict(selection_scope)),
        "order": order,
    }
```

Use only the approved primitive kinds:

```python
ENGINEERING_FEATURE_KINDS = {
    "nurbs_curve", "polyline", "control_point", "point", "local_frame", "reference_axis",
}
ENGINEERING_DIMENSION_KINDS = {
    "linear", "radial", "diameter", "angular", "arc_height", "ordinate", "control_coordinate",
}
```

Build initial records from existing hub/tip profiles, blade/station/loop indices, and resolved dimensions. Preserve existing contract fields for compatibility.

- [ ] **Step 4: Run focused and historical contract tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py
git commit -m "feat: expose engineering inspection parameters"
```

---

### Task 2: Complete Constructor Parameter Coverage And Validation

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_v11_3_engineering_inspection.py`

**Interfaces:**
- Consumes: Task 1 `_inspection_parameter` and feature/dimension kind sets.
- Produces: complete records for profiles, placement, pose, section loops, controls, sagittae, attachments, and results; strict `validate_parameter_inspection_contract` failures.

- [ ] **Step 1: Add failing complete-coverage tests**

For open and closed presets assert records exist for:

```python
required_suffixes = {
    "hub.profile.degree", "hub.profile.control.0.r", "hub.profile.control.0.z",
    "blade.main.count", "blade.angular_pitch", "blade.splitter.phase",
    "pose.station.0", "section.pressure.control.0", "section.suction.control.0",
    "section.leading.sagitta", "section.trailing.sagitta",
    "attachment.root.width", "attachment.root.lift",
}
```

Closed presets must also expose `attachment.shroud.width`, `attachment.shroud.lift`, and shroud thickness. Each control-point record must reference one `control_point` primitive and one `control_coordinate` dimension.

- [ ] **Step 2: Add failing measurement-consistency tests**

Assert:

```python
assert abs(measure_dimension(parameter["dimension_definition"]) - parameter["resolved_value"]) <= parameter["dimension_definition"]["tolerance"]
```

Cover linear thickness, arc-height sagitta, angular pitch, profile control ordinate, and root lift. Mutating a point must produce `parameter_inspection_dimension_value_mismatch`.

- [ ] **Step 3: Run focused tests and confirm RED**

Run the Task 1 focused command. Expected: missing records and validator failures not yet implemented.

- [ ] **Step 4: Implement complete parameter extraction**

Use generated contract evidence, not frontend defaults. Parameter ids use deterministic scoped paths:

```text
blade:{blade_instance_id}:station:{span_station_id}:section:{segment}:control:{index}:{axis}
blade:{blade_instance_id}:station:{span_station_id}:section:{edge}:sagitta
blade:{blade_instance_id}:attachment:root:lift
```

Implement backend measurement helpers:

```python
def _measure_dimension(definition: Mapping[str, Any]) -> float:
    kind = definition["kind"]
    points = definition["measurement_points"]
    if kind in {"linear", "radial", "diameter", "ordinate", "control_coordinate"}:
        return _distance(points[0], points[1]) * (2.0 if kind == "diameter" else 1.0)
    if kind == "angular":
        return _angle_degrees(definition["reference_direction"], definition["measured_direction"])
    if kind == "arc_height":
        return _point_line_distance(points[2], points[0], points[1])
    raise ValueError("parameter_inspection_dimension_kind_unsupported")

def _validate_engineering_parameters(parameters: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for parameter in parameters:
        parameter_id = parameter.get("parameter_id")
        if not isinstance(parameter_id, str) or not parameter_id or parameter_id in seen:
            failures.append({"reason": "parameter_inspection_parameter_id_invalid", "parameter_id": parameter_id})
            continue
        seen.add(parameter_id)
        definition = parameter.get("dimension_definition")
        if definition is not None:
            measured = _measure_dimension(definition)
            tolerance = float(definition.get("tolerance", 1.0e-6))
            if abs(measured - float(parameter["resolved_value"])) > tolerance:
                failures.append({"reason": "parameter_inspection_dimension_value_mismatch", "parameter_id": parameter_id})
    return failures
```

Reject duplicate ids, nonfinite values/coordinates, unknown kinds, invalid references, degenerate baselines, empty views, and measurement mismatch.

- [ ] **Step 5: Advertise additive engineering capability**

Add runtime manifest capability without changing `geometry_version`:

```python
"parameter_inspection_capabilities": [
    "engineering_feature_geometry",
    "engineering_dimensions",
    "s_q_blade_synchronized_selection",
]
```

- [ ] **Step 6: Run backend verification**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py -q
```

Expected: PASS for open and closed presets.

- [ ] **Step 7: Commit**

```powershell
git add src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py src/part_rule_synthesis/impeller_runtime_compiler.py tests/test_impeller_v11_3_engineering_inspection.py
git commit -m "feat: validate engineering inspection evidence"
```

---

### Task 3: Frontend Engineering Inspection Model

**Files:**
- Modify: `frontend/src/parameterInspectionModel.js`
- Modify: `frontend/src/parameterInspectionModel.test.js`

**Interfaces:**
- Consumes: backend `parameter_groups` and `parameters` from Tasks 1-2.
- Produces: `engineeringParameterGroups(model, context)`, `engineeringParameterById(model, id)`, `equivalentParameterId(model, currentId, nextContext)`, and validated `model.engineeringParameters`.

- [ ] **Step 1: Write failing parsing and validation tests**

Extend the frontend fixture with one parameter of each primitive/dimension kind. Assert malformed ids, coordinates, views, references, and dimension values return `parameter_inspection_contract_unsupported`.

Assert:

```javascript
const groups = engineeringParameterGroups(model, { bladeId: "main-1", spanStationId: "h-050", viewId: "s_q" });
assert.equal(groups.find((group) => group.groupId === "section_loop").parameters.length > 0, true);
assert.equal(
  engineeringParameterById(model, "blade:main-1:station:h-050:section:leading:sagitta").dimension.kind,
  "arc_height",
);
```

- [ ] **Step 2: Write failing equivalent-selection tests**

Selecting pressure control 2 on `main-1/h-050`, then switching to `main-2/h-050`, must return the matching control-2 parameter id. Switching to a context with no equivalent must return `null`.

- [ ] **Step 3: Run frontend tests and confirm RED**

```powershell
cd frontend
node --test src/parameterInspectionModel.test.js
```

Expected: FAIL because engineering helpers are undefined.

- [ ] **Step 4: Implement minimal parser and context helpers**

Normalize records to:

```javascript
{
  id, groupId, label, requestedValue, resolvedValue, unit,
  applicableViews, features, dimension, selectionScope, order
}
```

Do not derive features from `targetSurfaceIds`. Preserve the old selection model only where still used outside the engineering workspace.

- [ ] **Step 5: Run frontend model tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/parameterInspectionModel.js frontend/src/parameterInspectionModel.test.js
git commit -m "feat: parse engineering inspection evidence"
```

---

### Task 4: Pure Engineering Drawing Projection And Dimensions

**Files:**
- Create: `frontend/src/engineeringDrawingModel.js`
- Create: `frontend/src/engineeringDrawingModel.test.js`

**Interfaces:**
- Consumes: normalized feature primitives and dimension definitions from Task 3.
- Produces:

```javascript
projectEngineeringFeature(feature, viewId, frame) -> drawing primitive | null
layoutEngineeringDimension(dimension, projectedFeatures, viewport) -> drawing primitives
engineeringDrawingBounds(contextPrimitives, selectedPrimitives) -> bounds
```

- [ ] **Step 1: Write failing projection tests**

Cover:

- Top projection `(x, y, z) -> (x, y)`;
- Meridional projection `(x, y, z) -> (hypot(x, y), z)`;
- S-Q uses metric `display_*_s_q_mm` directly;
- equal aspect ratio;
- finite-coordinate rejection.

- [ ] **Step 2: Write failing dimension-layout tests**

For `linear`, `angular`, `arc_height`, `ordinate`, and `control_coordinate`, assert output contains blue dimension/extension/arrow primitives and remains inside a padded viewport. Assert secondary note suppression occurs before any dimension crosses the context bounds.

- [ ] **Step 3: Run tests and confirm RED**

```powershell
node --test src/engineeringDrawingModel.test.js
```

Expected: module or export not found.

- [ ] **Step 4: Implement pure functions without DOM access**

Use plain objects:

```javascript
{ kind: "path", points, className: "engineering-feature-selected" }
{ kind: "dimension", line, extensions, arrows, text, className: "engineering-dimension" }
```

Use one deterministic padding constant and one label offset policy. Do not build a general constraint solver.

- [ ] **Step 5: Run tests and commit**

```powershell
node --test src/engineeringDrawingModel.test.js
git add src/engineeringDrawingModel.js src/engineeringDrawingModel.test.js
git commit -m "feat: project engineering inspection drawings"
```

---

### Task 5: Compact Parameter Browser And SVG Drawing View

**Files:**
- Create: `frontend/src/components/ParameterFeatureBrowser.js`
- Create: `frontend/src/components/ParameterFeatureBrowser.test.js`
- Create: `frontend/src/components/EngineeringDrawingView.js`
- Create: `frontend/src/components/EngineeringDrawingView.test.js`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 3 parameter groups and Task 4 projected primitives.
- Produces: `ParameterFeatureBrowser({ groups, selectedParameterId, onSelect })` and `EngineeringDrawingView({ viewId, contextPrimitives, selectedParameter })`.

- [ ] **Step 1: Write failing browser tests**

Assert groups render collapsed by default, curve groups expand, each control point is an independent button, disabled parameters expose applicable views, and clicking the active parameter calls `onSelect(null)`.

- [ ] **Step 2: Write failing drawing source-contract tests**

Assert the component renders:

```text
engineering-context        black thin paths
engineering-feature        red paths/points/control polygons
engineering-dimension      blue lines/arrows/text
```

Assert the source contains no surface material selection, UV line, triangle mesh, or leader element.

- [ ] **Step 3: Run component tests and confirm RED**

```powershell
node --test src/components/ParameterFeatureBrowser.test.js src/components/EngineeringDrawingView.test.js
```

- [ ] **Step 4: Implement the minimal components**

Use native `<details>/<summary>` for collapsible groups and native `<button>` elements for parameters. Render SVG `<path>`, `<circle>`, `<line>`, `<polygon>`, and `<text>` directly from Task 4 output. Add accessible labels and `aria-pressed`.

- [ ] **Step 5: Add compact engineering CSS**

Lock visual tokens:

```css
--engineering-context: #111111;
--engineering-feature: #c40000;
--engineering-dimension: #005ea8;
--engineering-paper: #ffffff;
```

Toolbar maximum block size: `32px`. Use 1 px context lines, 1.5-2 px selected features, and 1 px dimensions. Parameter browser must not overlap `.engineering-drawing-canvas`.

- [ ] **Step 6: Run tests and commit**

```powershell
npm.cmd test
git add src/components/ParameterFeatureBrowser.js src/components/ParameterFeatureBrowser.test.js src/components/EngineeringDrawingView.js src/components/EngineeringDrawingView.test.js src/styles.css
git commit -m "feat: render engineering parameter drawings"
```

---

### Task 6: Isolated Blade Feature Scene

**Files:**
- Create: `frontend/src/components/BladeFeatureScene.js`
- Create: `frontend/src/components/BladeFeatureScene.test.js`

**Interfaces:**
- Consumes: selected blade surface ids for context plus selected parameter `feature_geometry` applicable to `blade_3d`.
- Produces: one bounded Three.js renderer showing thin black context contours and red line/point features without changing mesh material.

- [ ] **Step 1: Write failing scene tests**

Assert:

- only the selected blade and its necessary root/tip attachment surfaces enter the group;
- all context meshes remain white and unselected;
- selected NURBS/polyline/control-point features are red line/point objects;
- UV and mesh overlays are hidden;
- renderer/context counters return to zero after cleanup.

- [ ] **Step 2: Run and confirm RED**

```powershell
node --test src/components/BladeFeatureScene.test.js
```

- [ ] **Step 3: Implement by reusing existing surface graph helpers**

Reuse `createSurfaceGraphGroup`, `surfaceGraphBounds`, and `disposeObject`. Filter graph input before group creation. Add feature lines and points in a separate `THREE.Group` with `userData.isEngineeringFeature = true`. Do not add a new renderer abstraction.

- [ ] **Step 4: Verify lifecycle and commit**

```powershell
node --test src/components/BladeFeatureScene.test.js
git add src/components/BladeFeatureScene.js src/components/BladeFeatureScene.test.js
git commit -m "feat: inspect isolated blade features"
```

---

### Task 7: Three-View Workspace And Synchronized Selection

**Files:**
- Modify: `frontend/src/components/ParameterInspectionWorkspace.js`
- Modify: `frontend/src/components/ParameterInspectionWorkspace.test.js`
- Modify: `frontend/src/styles.css`
- Delete after import audit: `frontend/src/components/InspectionScene.js`
- Delete after import audit: `frontend/src/components/InspectionScene.test.js`
- Delete after import audit: `frontend/src/components/ParameterAnnotationOverlay.js`

**Interfaces:**
- Consumes: Tasks 3, 5, and 6.
- Produces: final Top, Meridional, and S-Q + Blade inspection workspace.

- [ ] **Step 1: Write failing workspace tests**

Assert tab ids are exactly:

```javascript
["top", "meridional", "s_q_blade"]
```

Assert no standalone `3d` or `quad`; toolbar contains Blade and Station selectors; S-Q layout renders `EngineeringDrawingView` and `BladeFeatureScene` side by side; selected parameter id is passed to both; only one dimension is active.

- [ ] **Step 2: Write failing preservation/clearing tests**

Changing blade/station uses `equivalentParameterId`. Changing to an inapplicable view clears selection. Clicking the selected parameter clears it. No selection produces no red feature or blue dimension.

- [ ] **Step 3: Run and confirm RED**

```powershell
node --test src/components/ParameterInspectionWorkspace.test.js
```

- [ ] **Step 4: Implement the compact workspace**

Use one state value:

```javascript
const [selectedParameterId, setSelectedParameterId] = useState(null);
```

Remove annotation level controls, maximize buttons, old parameter rows, standalone 3D, and Quad. Keep the parameter browser outside the drawing grid.

- [ ] **Step 5: Audit and remove obsolete components**

Run:

```powershell
rg -n "InspectionScene|ParameterAnnotationOverlay" frontend/src
```

Delete files only when no production import remains. Preserve shared model helpers still used by `BladeFeatureScene`.

- [ ] **Step 6: Run full frontend tests and commit**

```powershell
cd frontend
npm.cmd test
git add src/components src/styles.css
git commit -m "feat: add engineering inspection workspace"
```

---

### Task 8: Browser Acceptance, Evidence, And Regression Gate

**Files:**
- Modify: `frontend/scripts/parameter-inspection-visual-smoke.cjs`
- Create: `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-top.png`
- Create: `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-meridional.png`
- Create: `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-s-q-blade.png`
- Create: `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/narrow-s-q-blade.png`
- Modify: `docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md`
- Modify: `docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md`

**Interfaces:**
- Consumes: completed backend and frontend implementation.
- Produces: executable acceptance proof and screenshots.

- [ ] **Step 1: Rewrite browser assertions before implementation verification**

Smoke must:

1. generate the first V1.1 preset;
2. open Top and select a hub profile control point;
3. assert red feature and blue ordinate dimension exist;
4. open Meridional and select root lift;
5. assert hub/blade root boundaries plus blue normal dimension exist;
6. open S-Q + Blade and select leading-edge sagitta;
7. assert red edge/control geometry and blue chord/sagitta exist in S-Q;
8. assert the isolated 3D blade has red feature lines and no selected mesh material;
9. assert no UV, triangle, leader, standalone 3D tab, or Quad tab;
10. assert toolbar and browser boxes do not overlap drawing boxes;
11. repeat S-Q + Blade at narrow width;
12. report renderer/context lifecycle.

- [ ] **Step 2: Run backend regression gate**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py tests/test_impeller_v11_2_resources.py tests/test_impeller_v11_surface_family.py -q
```

Expected: all pass; no V1.1.2 geometry regression.

- [ ] **Step 3: Run full frontend gate**

```powershell
cd frontend
npm.cmd test
```

Expected: zero failures.

- [ ] **Step 4: Start or confirm local services**

Backend: `http://127.0.0.1:8061`
Frontend: `http://127.0.0.1:5199`

Both must load from this worktree and return HTTP 200.

- [ ] **Step 5: Run browser smoke and inspect screenshots**

```powershell
$env:CODEX_NODE_MODULES='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node frontend/scripts/parameter-inspection-visual-smoke.cjs
```

Expected: Top, Meridional, desktop S-Q + Blade, and narrow S-Q + Blade PASS; no blank viewport; bounded renderer/context counts.

- [ ] **Step 6: Update evidence and insight logs**

Record exact commands, test counts, HTTP status, screenshot paths, selected parameter examples, and the semantic rule:

```text
parameter selection identifies authoritative construction evidence;
it never substitutes whole-surface material highlighting for feature geometry.
```

- [ ] **Step 7: Final diff review and commit**

```powershell
git diff --check
git status --short
git add frontend/scripts docs/evidence
git commit -m "test: verify engineering parameter inspection"
```

---

## Final Acceptance Checklist

- [ ] Backend emits complete authoritative parameter groups and engineering evidence.
- [ ] Section pressure/suction/leading/trailing controls and edge sagittae are inspectable.
- [ ] Hub/tip/shroud profiles and control points are inspectable.
- [ ] Pose, thickness, placement, root, and closed-shroud attachment parameters are inspectable.
- [ ] Only Top, Meridional, and S-Q + Blade tabs remain.
- [ ] S-Q and isolated blade 3D synchronize one selected parameter.
- [ ] No whole surface is highlighted.
- [ ] Context is thin black, selected feature red, dimension blue.
- [ ] No UV, triangle mesh, leader, or drawing-overlay controls remain.
- [ ] Toolbar and parameter browser do not obscure drawings.
- [ ] Workspace remains read-only.
- [ ] V1.1.2 geometry regressions pass.
- [ ] Frontend tests and browser smoke pass with retained evidence.
