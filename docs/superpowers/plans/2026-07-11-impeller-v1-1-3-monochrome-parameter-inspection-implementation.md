# Impeller V1.1.3 Monochrome Parameter Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the colored UV-heavy Parameter inspection presentation with white surfaces, black necessary contours, and clickable parameter rows that highlight related generated geometry without leader lines.

**Architecture:** Keep the existing V1.1.3 inspection contract and selection reducer. Add target surface ids to frontend annotation records, keep one local active-annotation id in the workspace, remove leader rendering from the existing overlay, and restyle the existing Three.js surface group in `InspectionScene` with `EdgesGeometry` contours.

**Tech Stack:** React with `React.createElement`, Three.js, Node test runner, Playwright smoke script.

## Global Constraints

- Do not change V1.1.2 geometry construction, V1.1.3 backend contracts, preset ids, mesh generation, or exports.
- Add no dependency and no new rendering subsystem.
- Parameter inspection must not display UV lines or mesh triangle wireframe.
- Ordinary geometry is white fill with black contour; selected geometry is black fill with white contour.
- Parameter rows use exclusive toggle selection and have no model leader lines.
- Preserve keyboard accessibility and read-only behavior.

---

### Task 1: Resolve Parameter Rows To Generated Surfaces

**Files:**
- Modify: `frontend/src/parameterInspectionModel.js`
- Test: `frontend/src/parameterInspectionModel.test.js`

**Interfaces:**
- Produces: every annotation returned by `annotationsForView(...)` has `targetSurfaceIds: string[]`.
- Consumes: existing `model.indices.surfaces`, `model.indices.blades`, `selection.bladeId`, and `surfaceForSegment(...)` relationships.

- [ ] **Step 1: Add failing annotation-target tests**

Add assertions covering:

```javascript
const rootOffset = annotationsForView(model, "meridional", "key", selection)
  .find((item) => item.id === "meridional:root_offset_mm");
assert.deepEqual(rootOffset.targetSurfaceIds, ["blade_0_root_attachment_surface"]);

const bladeCount = annotationsForView(model, "top", "key", selection)
  .find((item) => item.id === "top:main_blade_count");
assert.ok(bladeCount.targetSurfaceIds.length > model.indices.blades.blade_0.surface_ids.length);

const hubProfile = annotationsForView(model, "meridional", "key", selection)
  .find((item) => item.id === "meridional:hub_profile");
assert.ok(hubProfile.targetSurfaceIds.every((id) => model.indices.surfaces[id].blade_instance_id == null));
```

Also assert section segment annotations resolve to the selected blade's matching pressure/suction/leading/trailing surface and target arrays contain unique inspectable ids only.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
cd frontend
node --test src/parameterInspectionModel.test.js
```

Expected: FAIL because `targetSurfaceIds` is absent.

- [ ] **Step 3: Attach target ids in the existing annotation builders**

Extend the existing record constructor only:

```javascript
function annotation({
  id,
  level,
  label,
  requestedValue,
  resolvedValue,
  unit = "",
  requestedUnit = unit,
  anchor,
  selection = null,
  metrics = null,
  targetSurfaceIds = [],
}) {
  return {
    id,
    level,
    label,
    requestedValue,
    resolvedValue,
    unit,
    requestedUnit,
    value: formatAnnotationValue(requestedValue, resolvedValue, requestedUnit, unit),
    anchor,
    selection,
    metrics,
    targetSurfaceIds: [...new Set(targetSurfaceIds)],
  };
}
```

Each calling builder must filter candidates with `model.indices.surfaces[surfaceId]?.inspectable === true` before passing them to `annotation()`; `annotation()` only deduplicates the already validated ids.

Use these exact policies:

```text
surface annotation              -> [surface.surface_id]
station annotation              -> owning blade.surface_ids
thickness/pose dimension        -> selected blade.surface_ids
root_offset_mm                  -> selected blade surfaces with face_family blade_root
tip_offset_mm                   -> selected blade surfaces with face_family blade_tip
counts/pitch/splitter fraction  -> every blade-owned inspectable surface
hub profile                     -> inspectable unowned surfaces matching hub role/family
tip or shroud profile           -> inspectable unowned surfaces matching tip/shroud role/family
S-Q section segment             -> surfaceForSegment(...) on selected blade
```

Use small local array filters; do not introduce a target-rule registry.

- [ ] **Step 4: Run focused model tests and verify GREEN**

Run:

```powershell
cd frontend
node --test src/parameterInspectionModel.test.js
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/parameterInspectionModel.js frontend/src/parameterInspectionModel.test.js
git commit -m "feat: map inspection parameters to geometry"
```

---

### Task 2: Make Parameter Rows Clickable And Remove Leaders

**Files:**
- Modify: `frontend/src/components/ParameterAnnotationOverlay.js`
- Modify: `frontend/src/components/SectionLoopInspectionView.test.js`
- Modify: `frontend/src/components/ParameterInspectionWorkspace.js`
- Modify: `frontend/src/components/ParameterInspectionWorkspace.test.js`
- Modify: `frontend/src/components/InspectionScene.js`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: annotation `id`, `selected`, and `targetSurfaceIds` from Task 1.
- Produces: `ParameterAnnotationOverlay({ annotations, selectedAnnotationId, onSelectAnnotation, ... })`.
- Produces: workspace-local `activeAnnotationId: string | null`.

- [ ] **Step 1: Add failing overlay behavior tests**

Assert the rendered overlay:

```javascript
assert.equal(collectElements(tree, (node) => node.type === "line").length, 0);
assert.equal(collectElements(tree, (node) => node.props?.role === "button").length, 1);
assert.equal(button.props["aria-pressed"], true);
button.props.onClick();
assert.equal(selectedId, "top:main_blade_count");
```

Trigger `Enter` and Space through `onKeyDown`, verify `preventDefault()`, and assert rows without targets have no button role or click callback.

- [ ] **Step 2: Add failing workspace selection tests**

Assert source/behavior contracts for:

```text
first parameter click     -> active id and annotation target ids drive InspectionScene
second parameter click    -> replaces active id
same parameter click      -> clears active id
surface/blade/station/tab -> clears active id
```

The selected row id must be passed to full and S-Q overlays.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
cd frontend
node --test src/components/SectionLoopInspectionView.test.js src/components/ParameterInspectionWorkspace.test.js
```

Expected: FAIL because leaders still render and annotation click state is absent.

- [ ] **Step 4: Delete leader rendering and add accessible row selection**

In `ParameterAnnotationOverlay`, remove the `<line className="inspection-leader">` element. Give only actionable annotation groups:

```javascript
const actionable = annotation.targetSurfaceIds?.length > 0;
const active = selectedAnnotationId === annotation.id;

h("g", {
  role: actionable ? "button" : undefined,
  tabIndex: actionable ? 0 : undefined,
  "aria-pressed": actionable ? active : undefined,
  onClick: actionable ? () => onSelectAnnotation?.(annotation) : undefined,
  onKeyDown: actionable ? (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelectAnnotation?.(annotation);
    }
  } : undefined,
});
```

Layout parameter rows by slots only. Do not require projected geometry anchors and do not emit projection errors for labels that no longer connect to geometry.

- [ ] **Step 5: Add the minimal workspace state**

Use one state value:

```javascript
const [activeAnnotationId, setActiveAnnotationId] = useState(null);
const activeAnnotation = Object.values(annotationsByView)
  .flat()
  .find((item) => item.id === activeAnnotationId);
const displayedSurfaceIds = activeAnnotation?.targetSurfaceIds?.length
  ? activeAnnotation.targetSurfaceIds
  : selectedSurfaceIds;
```

Toggle with:

```javascript
function handleAnnotationSelection(annotation) {
  setActiveAnnotationId((current) => current === annotation.id ? null : annotation.id);
}
```

Call `setActiveAnnotationId(null)` before surface, blade, station, and tab changes. Pass `displayedSurfaceIds` to `InspectionScene`. Pass `selectedAnnotationId` and `onSelectAnnotation` to every full, Quad, and S-Q overlay.

- [ ] **Step 6: Remove obsolete leader CSS and enable row pointer input**

Delete `.inspection-leader` rules. Add pointer and focus styling only to actionable rows:

```css
.inspection-label-action {
  cursor: pointer;
  pointer-events: auto;
}

.inspection-label-action:focus-visible .inspection-label-region {
  stroke: #000;
  stroke-width: 2;
  outline: none;
}

.inspection-label-action[aria-pressed="true"] .inspection-label-region {
  fill: #111;
  stroke: #111;
}

.inspection-label-action[aria-pressed="true"] .inspection-label {
  fill: #fff;
  stroke: #111;
}
```

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```powershell
cd frontend
node --test src/components/SectionLoopInspectionView.test.js src/components/ParameterInspectionWorkspace.test.js src/components/InspectionScene.test.js
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add frontend/src/components/ParameterAnnotationOverlay.js frontend/src/components/SectionLoopInspectionView.test.js frontend/src/components/ParameterInspectionWorkspace.js frontend/src/components/ParameterInspectionWorkspace.test.js frontend/src/components/InspectionScene.js frontend/src/styles.css
git commit -m "feat: select geometry from inspection parameters"
```

---

### Task 3: Render Monochrome Surfaces And Necessary Contours

**Files:**
- Modify: `frontend/src/components/InspectionScene.js`
- Modify: `frontend/src/components/InspectionScene.test.js`

**Interfaces:**
- Consumes: existing meshes created by `createSurfaceGraphGroup(...)`.
- Produces: one `LineSegments(EdgesGeometry)` contour sibling per inspectable mesh with `userData.isInspectionContour = true` and the same `surfaceId`.

- [ ] **Step 1: Add failing monochrome rendering tests**

Assert the source/scene contract includes:

```text
THREE.EdgesGeometry(mesh.geometry, 35)
ordinary mesh color #ffffff
selected mesh color #111111
ordinary contour color #111111
selected contour color #ffffff
depthTest true
isSurfaceUvWire visible false
no WireframeGeometry in Parameter inspection contour construction
```

Also assert changing `selectedSurfaceIds` updates both mesh and matching contour material without rebuilding the scene.

- [ ] **Step 2: Run focused scene tests and verify RED**

Run:

```powershell
cd frontend
node --test src/components/InspectionScene.test.js
```

Expected: FAIL because the scene still uses colored materials and UV overlays.

- [ ] **Step 3: Restyle the installed scene once**

Immediately after `createSurfaceGraphGroup(...)`:

```javascript
const meshes = [];
group.traverse((child) => {
  if (child.isMesh && child.userData.surfaceId) meshes.push(child);
  if (child.isLineSegments && child.userData.isSurfaceUvWire) child.visible = false;
});

for (const mesh of meshes) {
  forEachMaterial(mesh.material, (material) => {
    material.color.set("#ffffff");
    material.emissive.set("#000000");
    material.emissiveIntensity = 0;
    material.opacity = 1;
    material.transparent = false;
    material.userData.inspectionBaseColor = "#ffffff";
  });
  const contour = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 35),
    new THREE.LineBasicMaterial({ color: "#111111", depthTest: true, depthWrite: false }),
  );
  contour.userData.isInspectionContour = true;
  contour.userData.surfaceId = mesh.userData.surfaceId;
  contour.userData.layer = mesh.userData.layer;
  group.add(contour);
}
```

`disposeObject(group)` already owns and disposes the added geometry/material; do not add a second cleanup path.

- [ ] **Step 4: Update selection and visibility in place**

In the existing selection effect:

```javascript
if (child.isMesh && child.userData.surfaceId) {
  const selected = selectedSurfaceIdSet.has(child.userData.surfaceId);
  forEachMaterial(child.material, (material) => material.color.set(selected ? "#111111" : "#ffffff"));
}
if (child.isLineSegments && child.userData.isInspectionContour) {
  child.material.color.set(selectedSurfaceIdSet.has(child.userData.surfaceId) ? "#ffffff" : "#111111");
}
```

In the visibility effect, force UV wire false and contour visibility to follow its layer:

```javascript
if (child.userData.isSurfaceUvWire) child.visible = false;
if (child.userData.isInspectionContour) child.visible = visibleLayers[child.userData.layer] !== false;
```

- [ ] **Step 5: Run focused scene tests and verify GREEN**

Run:

```powershell
cd frontend
node --test src/components/InspectionScene.test.js
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/InspectionScene.js frontend/src/components/InspectionScene.test.js
git commit -m "feat: render monochrome inspection contours"
```

---

### Task 4: Regression And Visual Acceptance

**Files:**
- Modify: `frontend/scripts/parameter-inspection-visual-smoke.cjs`
- Modify: `docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md`
- Modify: `docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md`
- Modify: `docs/evidence/assets/v1.1.3-parameter-inspection/desktop-3d.png`
- Modify: `docs/evidence/assets/v1.1.3-parameter-inspection/desktop-quad.png`
- Modify: `docs/evidence/assets/v1.1.3-parameter-inspection/narrow-s-q.png`

**Interfaces:**
- Consumes: final local services at `http://127.0.0.1:8061` and `http://127.0.0.1:5199`.

- [ ] **Step 1: Extend browser smoke interaction**

After generation and opening Parameter inspection:

```javascript
const parameterRow = page.locator('[data-annotation-id="3d:thickness_max_mm"]');
await parameterRow.click();
assert.equal(await parameterRow.getAttribute("aria-pressed"), "true");
assert.ok(Number(await workspace.getAttribute("data-selected-surface-count")) > 0);
await parameterRow.click();
assert.equal(await parameterRow.getAttribute("aria-pressed"), "false");
assert.equal(await page.locator(".inspection-leader").count(), 0);
```

Expose `data-annotation-id` on actionable rows and an inspection scene data attribute proving UV overlay count is zero. Do not inspect Three.js internals from Playwright.

- [ ] **Step 2: Run full frontend regression**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all tests PASS.

- [ ] **Step 3: Restart only stale project services if required**

Verify listeners first. Restart only processes whose command line matches this worktree's Uvicorn/static-server commands. Keep both services hidden and leave unrelated worktrees untouched.

- [ ] **Step 4: Run Playwright smoke and regenerate evidence**

Run the existing bundled runtime command recorded in `.superpowers/sdd/task-7-report.md`:

```powershell
$env:CODEX_NODE_MODULES='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:NODE_PATH='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\node_modules'
& 'C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' frontend/scripts/parameter-inspection-visual-smoke.cjs
```

Expected: desktop 3D, desktop Quad, and narrow S-Q PASS; zero leader lines; zero visible UV overlays; annotation toggle PASS; one live renderer/context.

- [ ] **Step 5: Inspect all refreshed screenshots**

Confirm visually:

```text
white surfaces and black necessary contours
no internal UV grid
no parameter-to-model lines
selected parameter row and inverted selected geometry are legible
no overlap or clipping regression in Quad or narrow S-Q
```

- [ ] **Step 6: Update evidence and run final checks**

Record exact test/smoke outputs and the deliberate choice to use `EdgesGeometry` instead of a silhouette post-process.

Run:

```powershell
git diff --check
git status --short
```

- [ ] **Step 7: Commit**

```powershell
git add frontend/scripts/parameter-inspection-visual-smoke.cjs docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md docs/evidence/assets/v1.1.3-parameter-inspection
git commit -m "test: verify monochrome parameter inspection"
```
