# Impeller V1.1.3 Graphical Parameter Inspection Design

**Date:** 2026-07-10

**Status:** Approved design, pending implementation plan

## 1. Purpose

V1.1.3 adds graphical parameter inspection to the generated impeller model. The central graphics workspace must show resolved parameters on actual generated geometry, not only as text summaries in the left parameter panel.

V1.1.3 is an inspection release. It does not replace or revise the V1.1.2 canonical NURBS construction rules. The release establishes a visible evidence layer that connects resolved canonical parameters, sampled surface geometry, and the user's visual review.

## 2. Problem Statement

V1.1.2 introduced a `Parameter views` panel, but the implementation only renders textual annotation lists. It does not:

- show multiple model views in the graphics workspace;
- project resolved parameters onto actual generated geometry;
- identify the blade, surface, span station, or control point to which a value belongs;
- synchronize selection across 3D, top, meridional, and S-Q views;
- prove that a displayed value comes from the resolved manifest rather than a preset seed.

The existing panel therefore does not satisfy the graphical inspection acceptance requirement and must be removed rather than extended into a second source of truth.

## 3. Release Semantics

V1.1.3 separates application capability versioning from geometry semantics:

```text
runtime_release_version = "1.1.3"
parameter_inspection_contract_version = "1.1.3"
geometry_patch_version = "1.1.2"
canonical_payload_version = "1.1.2"
```

The active preset ids remain unchanged. The frontend presentation and runtime status identify the release as V1.1.3, while the manifest explicitly preserves the V1.1.2 geometry and canonical payload versions.

This prevents a UI-only inspection release from being misrepresented as a new geometry algorithm and avoids preset-id compatibility failures.

## 4. User Entry Point

Add `Parameter inspection` beside the existing central workspace modes:

```text
CAD review
CFD full 360
CFD360 mesh
Feature debug
Parameter inspection
```

Entering `Parameter inspection` replaces the central viewer content with a dedicated inspection workspace. It does not add another panel to the left parameter column.

The old `ParameterViewsPanel`, its text-only view model, styles, and source-contract tests are removed.

## 5. Workspace Layout

The inspection workspace contains five sub-tabs:

```text
3D
Top
Meridional
S-Q
Quad
```

### 5.1 Full-size views

`3D` is the default tab and uses the full central graphics area. `Top`, `Meridional`, and `S-Q` also use the full area so dense control-point and dimension annotations remain readable.

### 5.2 Quad view

`Quad` is a 2 by 2 engineering overview:

```text
+----------------------+----------------------+
| 3D                   | Meridional R-Z       |
+----------------------+----------------------+
| S-Q section loop     | Top                  |
+----------------------+----------------------+
```

Each pane has a maximize control that opens the corresponding full-size sub-tab. Quad selection and camera-independent inspection state persist when a pane is maximized.

### 5.3 Responsive behavior

On narrow screens, Quad changes to a single-column stack with stable aspect ratios. Full-size tabs remain the primary mobile and narrow-window workflow. Labels, buttons, and dimension text must not overlap the geometry or each other.

## 6. Rendering Architecture

Use a shared-scene hybrid architecture.

### 6.1 Shared Three.js scene

The `3D`, `Top`, and `Meridional` views share:

- one parsed `surface_graph`;
- one set of geometry buffers and materials;
- one Three.js scene;
- one semantic selection state;
- separate cameras and viewport/scissor rectangles.

The 3D view uses the existing perspective interaction model. Top and meridional views use orthographic cameras with deterministic orientation and fit-to-bounds behavior.

The implementation must not create three independent copies of the generated model or three independent WebGL contexts.

### 6.2 S-Q renderer

The S-Q view uses SVG because it must show the mathematical section domain clearly. It renders:

- the actual sampled closed loop at the selected span station;
- pressure, suction, leading-edge, and trailing-edge segments;
- resolved canonical NURBS control points and control polygons;
- continuity and thickness annotations;
- selected-point and selected-segment highlights.

The actual sampled loop and canonical control geometry must be visually distinguishable.

### 6.3 Annotation overlay

Screen-space SVG or HTML overlays render dimensions, leaders, labels, continuity badges, and selection callouts over the Three.js viewports. Annotation layout is separate from geometry rendering and cannot modify geometry state.

## 7. Component Boundaries

Add a dedicated `ParameterInspectionWorkspace` rather than adding multi-camera and annotation responsibilities to `ModelViewer`.

Expected component responsibilities:

```text
ParameterInspectionWorkspace
  owns active sub-tab, annotation level, and shared selection

InspectionScene
  owns shared Three.js scene, geometry buffers, cameras, and picking

InspectionViewport
  defines a 3D, top, or meridional viewport and its annotation overlay

SectionLoopInspectionView
  renders the selected S-Q station as SVG

InspectionToolbar
  exposes sub-tabs, annotation level, reset view, and Quad maximize

parameterInspectionModel
  resolves and validates the read-only backend inspection contract
```

Each unit has a single purpose and communicates through stable data objects. Existing `ModelViewer` remains responsible for CAD, wireframe, mesh, and feature-debug workflows.

## 8. Backend Inspection Contract

The manifest adds a read-only `parameter_inspection` object with:

```text
contract_version
generation_id
source_geometry_patch_version
source_canonical_payload_version
blade_instances
surface_references
span_stations
section_loops
support_profiles
resolved_dimensions
continuity_measurements
```

All inspectable entities require stable ids:

```text
blade_instance_id
surface_id
span_station_id
section_segment_id
control_point_id
```

References point to existing `surface_graph` surfaces, sampled grids, shared boundaries, and canonical NURBS records. The contract may package lookup-friendly data, but it must not duplicate or redefine the geometry algorithm.

The frontend must not recompute authoritative thickness, attachment, curvature, or continuity metrics. It may compute screen projections, hit-test distances, and label layout only.

## 9. Data Source Rules

After generation, all displayed geometry and values come from the same resolved result:

- 3D, Top, and Meridional render the generated `surface_graph`;
- S-Q uses the resolved section-loop station and its actual sampled boundary;
- annotations use `parameter_inspection` resolved values;
- canonical control points use the resolved canonical payload referenced by the inspection contract.

Preset defaults are not displayed as if they were generated measurements. Before generation, the workspace shows an explicit empty state: `Generate a model to inspect resolved geometry.`

When both requested and resolved values exist, the label format is:

```text
requested -> resolved
```

The source badge reads:

```text
Resolved manifest | runtime 1.1.3 | geometry 1.1.2
```

## 10. Shared Selection Model

The workspace maintains one read-only selection object:

```text
blade_instance_id
surface_id
span_station_id
section_segment_id
control_point_id
```

Any field may be unset. Selecting an object in one view updates every view:

- selecting a blade highlights its surfaces and section loop;
- selecting a surface highlights its top and meridional projection;
- selecting a span station updates the S-Q loop and marks its 3D location;
- selecting a section segment highlights the corresponding surface family;
- selecting a control point highlights its S-Q handle and associated annotation.

V1.1.3 does not support dragging control points or editing parameters in the inspection workspace. Editing remains in the existing parameter and curve editors until the graphical inspection behavior has been evaluated.

## 11. Annotation Levels

The toolbar provides three annotation levels:

```text
Key
Selected
All
```

`Key` shows only primary dimensions and population/pose information. `Selected` adds detailed annotations for the current selection. `All` exposes all available control points and dimensions, subject to collision management.

Leader placement uses deterministic screen-space collision avoidance. Labels may move, but leaders must continue to identify the exact geometry point. The renderer must not silently omit a selected annotation.

## 12. View-specific Annotations

### 12.1 3D

- selected face family and surface id;
- main or splitter blade identity;
- selected span station;
- local resolved thickness;
- root or tip/shroud attachment width and lift;
- adjacent-face continuity status;
- resolved normal orientation where relevant.

### 12.2 Top

- main and splitter blade counts;
- angular pitch;
- splitter passage fraction and placement;
- blade wrap and resolved circumferential extent;
- inlet and outlet orientation;
- blade coverage envelope.

### 12.3 Meridional R-Z

- actual hub and tip/shroud support profiles;
- resolved NURBS control points and control polygons;
- active span start and end;
- root and tip offsets;
- attachment width and lift;
- hub/shroud material thickness where present;
- mounting bore dimensions where present.

### 12.4 S-Q

- actual pressure, suction, leading-edge, and trailing-edge loop segments;
- resolved NURBS control points and polygons;
- local thickness distribution;
- leading- and trailing-cap sagitta;
- position-gap, tangent-angle, and curvature-proxy measurements at all four joins;
- measured continuity status.

## 13. Visual Semantics

Semantic colors remain stable across all views:

- pressure and suction use their established green family with distinguishable shades;
- leading and trailing edges use distinct warm colors;
- root and tip/shroud attachments use their established inspection colors;
- selected geometry uses a high-contrast outline and emissive highlight;
- control points and control polygons remain visually distinct from sampled geometry.

Shaded, UV-wire, and mesh visibility continue to use the existing viewer rules. Entering parameter inspection must not alter serialized transition or geometry overrides.

## 14. Error Handling

The workspace rejects inconsistent evidence instead of mixing results.

Required error states:

```text
parameter_inspection_not_generated
parameter_inspection_contract_unsupported
parameter_inspection_generation_id_mismatch
parameter_inspection_surface_reference_missing
parameter_inspection_station_reference_missing
parameter_inspection_loop_not_closed
parameter_inspection_projection_failed
```

If the inspection contract generation id does not match the surface graph generation id, the workspace shows a stale-data error and renders neither annotations nor mixed geometry.

Missing optional measurements show `unavailable` with a reason. Missing required identity or geometry references fail the inspection view but do not crash the application or invalidate the generated model itself.

## 15. Performance and Lifecycle

- Create one WebGL renderer and one shared scene for the inspection workspace.
- Reuse surface geometries and materials across viewports.
- Use viewport/scissor rendering for 3D, Top, and Meridional.
- Dispose geometry, material, controls, observers, and animation frames when leaving the workspace.
- Recompute projections after resize without regenerating the backend model.
- Keep annotation collision work bounded to visible annotations and the active level.

## 16. Tests

### 16.1 Backend

- contract version and release/geometry version separation;
- stable ids and valid surface/station references;
- actual loop closure and section-family mapping;
- requested/resolved value provenance;
- generation-id mismatch validation;
- all five representative presets emit a valid inspection contract.

### 16.2 Frontend model and components

- old text-only `ParameterViewsPanel` is absent;
- `Parameter inspection` is a central workspace mode;
- five sub-tabs render and preserve shared selection;
- full-size 3D is the default;
- Quad uses four panes and maximize routes correctly;
- annotation levels filter deterministic annotation sets;
- frontend does not derive authoritative geometry measurements;
- stale or incomplete contracts produce explicit error states;
- leaving the workspace disposes the renderer lifecycle cleanly.

### 16.3 Visual verification

Use browser screenshots at desktop and narrow viewports to verify:

- the 3D canvas is nonblank and framed correctly;
- Quad panes contain the expected distinct views;
- labels and controls do not overlap incoherently;
- selected objects remain highlighted across tab changes;
- S-Q actual loop, NURBS controls, and continuity labels are readable;
- full-size views provide materially more inspection space than Quad;
- no extra WebGL context is created for each orthographic view.

## 17. Acceptance Criteria

V1.1.3 is accepted when:

1. the runtime identifies V1.1.3 while preserving V1.1.2 geometry and canonical semantics;
2. existing V1.1 preset ids remain valid;
3. the old text-only Parameter views panel is removed;
4. generated models expose a valid V1.1.3 parameter-inspection contract;
5. the central graphics workspace includes `Parameter inspection` with `3D`, `Top`, `Meridional`, `S-Q`, and `Quad`;
6. 3D is full-size by default and Quad panes can be maximized;
7. the three geometric views use one shared scene and actual generated surfaces;
8. S-Q shows the actual selected loop and resolved canonical controls;
9. annotations are resolved, traceable, and synchronized across views;
10. inspection remains read-only and cannot mutate geometry payloads;
11. stale or invalid evidence fails visibly without a white-screen crash;
12. V1.1.2 geometry regressions and existing CAD/CFD viewer workflows still pass.

## 18. Documentation and Evidence

Implementation must update:

- semantic change log;
- insight log explaining why text-only parameter views were insufficient;
- evidence log with contract samples, test results, and visual screenshots;
- version history;
- implementation plan and task-level verification records.

The evidence must distinguish backend contract validity, frontend interaction tests, and human-visible screenshot verification.

## 19. Non-goals

V1.1.3 does not:

- change the V1.1.2 NURBS construction equations;
- introduce new preset ids;
- allow direct control-point dragging in the inspection workspace;
- claim analytic CAD continuity beyond the existing measured contract;
- replace CAD review, CFD, mesh, feature-debug, or existing curve-editing workflows;
- add independent duplicate renderers for each view.

## 20. Design Decisions

- The user selected the shared-scene hybrid approach over independent viewers and all-SVG projection.
- The original text-only Parameter views logic is removed.
- Full-size sub-tabs coexist with a 2 by 2 Quad overview so the interactive 3D view is not permanently reduced.
- Annotation is layered as Key, Selected, and All.
- Generated evidence takes precedence over preset intent.
- Editing inside the graphical inspection workspace is deferred until the read-only panel can be evaluated in practice.
