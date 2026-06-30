# Impeller Profile Curve Editor Design

## Summary

Add an interactive 2D R-Z profile editor for the current `AxisymmetricThroughflowRadialBladedImpeller` workflow. The editor lets the user drag NURBS control points for the hub curve and the tip/reference curve in the front meridional plane, then regenerate the same existing impeller constructor with those explicit profile overrides.

This is an interaction and geometry-input feature. It is not a loss record, not a knowledge-feedback event, and not a change to the impeller construction method. The construction method remains:

```text
hub R-Z NURBS profile -> revolve around Z -> hub support surface
tip/reference R-Z NURBS profile -> revolve around Z -> blade tip support surface
blade v=0 boundary conforms to hub support surface
blade v=1 boundary conforms to tip/reference support surface
pressure/suction blade surfaces use the same existing theta/thickness logic
```

## Goals

- Expose the actual editable geometry behind the current hub and tip/reference support surfaces.
- Let the user edit control points directly instead of relying on semantic handles such as `hub_profile_convexity`.
- Keep the current constructor deterministic: the same parameters plus the same profile override payload must produce the same manifest and geometry.
- Preserve the current backend rule engine lifecycle: synthesize engine, instantiate with parameters, return manifest/surface graph.
- Keep invalid profile edits visible and explicit; do not silently repair user edits.

## Non-Goals

- Do not introduce loss capture or ontology learning.
- Do not change the blade construction equations.
- Do not implement CFD, CAM, DFMA, or engineering optimization.
- Do not add 3D draggable handles in this step.
- Do not turn semantic handles into active shape rules in this step.
- Do not allow topology edits such as changing NURBS degree, knot vector shape, or control-point count.

## User Model

The user is editing two meridional curves in a front plane:

```text
x axis: radius r_mm
y axis: height z_mm
```

The user sees:

- hub profile curve
- hub control polygon and handles `H0...H3`
- tip/reference profile curve
- tip/reference control polygon and handles `T0...T3`
- basic dimensional grid or axes in millimeters
- validity status for the profile edit

Dragging a handle changes only that handle's `[r_mm, z_mm]` coordinate. It does not directly edit blade surfaces. Blade surfaces update after the model is regenerated from the edited profiles.

## Recommended Interaction

Use a 2D SVG editor embedded in the existing frontend, likely below the numeric parameter panel or as a separate left-panel section.

The editor should support:

- pointer drag for each control point
- numeric display of the selected handle coordinates
- optional direct numeric edit of selected handle `r_mm` and `z_mm`
- visual distinction between hub and tip/reference curves
- valid/invalid state color
- reset profile overrides to generated defaults
- apply/generate flow

The first version should use explicit `Apply profile` or existing `Generate` rather than regenerating on every pointer movement. It may update the SVG curve locally while dragging, but backend regeneration should occur on mouseup with debounce or only when the user clicks `Generate`.

## Data Contract

Current instantiate payload:

```json
{
  "parameters": {
    "blade_count": 7,
    "inlet_radius_mm": 180,
    "exit_radius_mm": 620
  }
}
```

New instantiate payload:

```json
{
  "parameters": {
    "blade_count": 7,
    "inlet_radius_mm": 180,
    "exit_radius_mm": 620
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "control_points": [[126, 84.376], [259.2, 65.94], [488, 18.99], [570.4, 0]],
      "weights": [1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 1, 1, 1, 1],
      "coordinate_system": "rz_meridional_mm"
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "control_points": [[180, 234.376], [285.6, 196.92], [496.8, 105.376], [620, 72]],
      "weights": [1, 1, 1, 1],
      "knots": [0, 0, 0, 0, 1, 1, 1, 1],
      "coordinate_system": "rz_meridional_mm"
    }
  }
}
```

Only `control_points` are editable in the first version. `kind`, `degree`, `weights`, `knots`, and `coordinate_system` are carried for explicitness and validation, but remain locked.

## Backend Design

### API Layer

Modify `InstantiateRequest` in `src/part_rule_synthesis/api.py`:

```python
class InstantiateRequest(BaseModel):
    parameters: dict[str, float | int] = Field(default_factory=dict)
    profile_overrides: dict[str, Any] | None = None
```

Pass `request.profile_overrides` to `RuleSynthesisService.instantiate`.

### Service Layer

Extend the instantiate path in `src/part_rule_synthesis/service.py`:

```python
def instantiate(
    self,
    engine_id: str,
    parameters: dict[str, Any],
    profile_overrides: dict[str, Any] | None = None,
) -> ModelRun:
```

The profile override must participate in the run hash:

```python
graph_hash = _stable_hash({
    "dsl": dsl,
    "parameters": bound,
    "profile_overrides": normalized_profile_overrides,
    "primitive_version": PRIMITIVES["version"],
    "operation_graph": operation_graph,
})
```

Pass `profile_overrides` through:

- `_write_exports(...)`
- `_geometry_kernel_metadata(...)`
- `_geometry_metadata(...)`
- `_geometry_validity_metadata(...)`

Manifest should include:

```json
{
  "profile_overrides": {},
  "geometry_kernel": {
    "profile_controls": {
      "source": "default_rule | user_override",
      "editable_entities": ["hub_profile", "tip_or_shroud_profile"]
    }
  }
}
```

### Kernel Layer

Modify `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`:

```python
def build_axisymmetric_throughflow_nurbs_geometry(
    parameters: dict[str, Any],
    facets: dict[str, str],
    shape_control: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

`_profile_definitions(...)` should first generate the default hub and tip profiles exactly as it does today. Then it should replace either profile only if a valid override is supplied.

Validation rules:

- accepted keys: `hub_profile`, `tip_or_shroud_profile`
- `kind == "nurbs_curve"`
- `degree == 3`
- exactly 4 control points
- every control point is `[r_mm, z_mm]`
- all values are finite
- all radii are positive
- weights length is 4 and all weights are positive
- knots exactly match `[0, 0, 0, 0, 1, 1, 1, 1]`
- coordinate system is `rz_meridional_mm`
- sampled tip/reference curve maintains positive clearance over sampled hub curve

If validation fails, the API should return a clear `400` error. It should not clamp or silently repair the profile.

## Frontend Design

### New Model Module

Create `frontend/src/profileEditorModel.js`.

Responsibilities:

- extract default profile controls from manifest:
  - `manifest.geometry_kernel.meridional_profiles.hub`
  - `manifest.geometry_kernel.meridional_profiles.tip_or_shroud`
- map `[r,z]` to SVG coordinates and back
- update a selected control point
- validate profile override before sending
- create the `profile_overrides` payload

Key functions:

```js
export function profilesFromManifest(manifest) {}
export function profileEditorBounds(profiles) {}
export function rzToScreen(point, bounds, viewport) {}
export function screenToRz(point, bounds, viewport) {}
export function updateControlPoint(profiles, profileId, pointIndex, rzPoint) {}
export function validateProfileOverrides(profiles) {}
export function profileOverridesPayload(profiles) {}
```

### New Component

Create `frontend/src/components/ProfileCurveEditor.js`.

Responsibilities:

- render SVG axes/grid
- render hub curve and tip/reference curve
- render control polygons
- render draggable handles
- show selected handle coordinate
- show validity status
- expose reset/apply behavior

Props:

```js
export function ProfileCurveEditor({
  manifest,
  profileOverrides,
  onProfileOverridesChange,
  onResetProfileOverrides,
})
```

The component should not call the backend directly. It only changes local UI state.

### App State

Modify `frontend/src/App.js`:

```js
const [profileOverrides, setProfileOverrides] = useState(null);
```

Pass `profileOverrides` into `instantiateImpeller`.

Reset rules:

- choosing a different preset clears profile overrides
- clicking profile reset clears profile overrides
- changing numeric parameters does not automatically clear profile overrides, but validation may fail if the curves become inconsistent with new dimensions

### API Client

Modify `frontend/src/apiClient.js`:

```js
export async function instantiateImpeller(apiBase, engineId, parameters, profileOverrides = null) {
  return postJson(url, {
    parameters: buildInstantiatePayload(parameters).parameters,
    profile_overrides: profileOverrides,
  });
}
```

If `profileOverrides` is `null`, omit or send `null`.

## Viewer Relationship

The Three.js viewer remains responsible for 3D inspection. It should not own profile editing state.

The 2D editor and 3D viewer share data through the manifest:

```text
2D editor edits profile_overrides
Generate sends profile_overrides
backend returns new manifest
3D viewer renders manifest.geometry.surface_graph
2D editor refreshes generated/sampled curves from manifest
```

This keeps the interaction deterministic and prevents 3D camera state from affecting the edited geometry.

## Validity and Error Handling

Frontend validation should block obviously invalid edits:

- missing profile
- wrong control-point count
- non-finite values
- non-positive radius
- tip/reference profile intersects or falls below hub profile in sampled R-Z space

Backend validation is authoritative. If backend rejects, frontend shows the API error in the existing error banner.

Invalid frontend state should be visible:

- invalid curve or handle colored red
- `Generate` disabled or warning shown
- no automatic correction

## Testing Strategy

Backend tests:

- default instantiate still works without profile overrides
- valid hub/tip profile overrides are reflected in `geometry_kernel.meridional_profiles`
- two different profile override payloads produce different run ids
- invalid degree/control-point count/radius/tip-clearance returns `400`
- legacy preset paths still work without overrides

Frontend model tests:

- manifest profiles convert into editor state
- screen/R-Z mapping round-trips within tolerance
- dragging one handle updates only that control point
- valid profiles produce expected `profile_overrides`
- invalid tip-under-hub profile fails validation

Frontend file smoke tests:

- `ProfileCurveEditor.js` exists
- `App.js` passes `profileOverrides` to instantiate
- `apiClient.js` sends `profile_overrides`

Browser smoke test:

- open frontend
- generate default model
- drag one hub handle
- generate again
- verify manifest run id changes and surface graph renders

## Open Decisions

The following are intentionally fixed for the first implementation:

- use 2D R-Z SVG, not 3D handles
- edit control points only
- keep NURBS degree, weights, knots, and control-point count locked
- backend regeneration happens after explicit generate or debounced mouseup, not every pointer move
- no loss record or ontology update is created by this interaction

