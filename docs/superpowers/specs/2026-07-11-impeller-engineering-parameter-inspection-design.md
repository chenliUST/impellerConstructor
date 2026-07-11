# Impeller Engineering Parameter Inspection Design

**Date:** 2026-07-11
**Status:** Approved for implementation planning
**Scope:** Frontend inspection UX plus authoritative backend `parameter_inspection` evidence
**Geometry:** Preserve V1.1.2 construction semantics

## 1. Goal

Replace the current card-like Parameter Inspection presentation with a professional, read-only engineering inspection workspace. A selected parameter must identify its actual construction feature and dimension, not highlight an entire blade or hub surface.

The release must:

- render thin monochrome context contours without UV or triangle lines;
- render selected construction features and control points in red;
- render engineering dimensions, extension lines, arrows, angle arcs, and text in blue;
- expose the currently missing blade-section controls, transition-curve controls, sagitta values, pose controls, and attachment dimensions;
- synchronize an S-Q engineering view with an isolated 3D blade view;
- keep all controls outside the drawing and avoid obscuring geometry;
- remain read-only.

This work extends the current inspection contract. It does not create a general Drawing DSL.

## 2. Locked Decisions

1. Backend geometry is authoritative; frontend code must not infer engineering meaning from surface roles.
2. Extend `parameter_inspection`; do not introduce an independent drawing ontology.
3. Keep only `Top`, `Meridional`, and `S-Q + Blade` views.
4. Remove standalone `3D` and `Quad` inspection tabs.
5. `S-Q + Blade` uses an approximately 60/40 side-by-side layout.
6. Parameter groups are collapsible. Each NURBS control point is individually selectable inside its owning curve group.
7. Only the selected parameter is dimensioned. With no selection, only necessary context contours are visible.
8. Selection is exclusive and toggleable.
9. The workspace is read-only; no drag or value editing is included.
10. Red denotes selected construction geometry. Blue denotes dimensions. Black denotes context.

## 3. Responsibility Boundary

### 3.1 Backend

The backend owns:

- parameter identity and grouping;
- requested and resolved values;
- construction-feature geometry;
- dimension semantics and measurement anchors;
- view applicability;
- selection ownership;
- measurement consistency with generated geometry.

### 3.2 Frontend

The frontend owns:

- orthographic projection;
- equal-aspect drawing scale;
- SVG dimension layout;
- label collision handling;
- compact parameter navigation;
- synchronized selection across 2D and 3D;
- visual styling.

The frontend must not recompute blade thickness, root lift, sagitta, curvature continuity, pitch, profile coordinates, or other authoritative engineering values.

## 4. Inspection Contract

Each inspectable parameter record must expose:

```json
{
  "parameter_id": "...",
  "group_id": "...",
  "label": "...",
  "requested_value": 0.0,
  "resolved_value": 0.0,
  "unit": "mm",
  "applicable_views": ["s_q", "blade_3d"],
  "feature_geometry": [],
  "dimension_definition": null,
  "selection_scope": {}
}
```

`parameter_id` must be stable within a generated manifest and deterministic for content-equivalent generation.

### 4.1 Feature Geometry

Use a small shared primitive vocabulary:

- `nurbs_curve`
- `polyline`
- `control_point`
- `point`
- `local_frame`
- `reference_axis`

Each primitive includes an id, finite model-space or domain-space coordinates, owning entity ids, and view applicability. NURBS definitions include degree, knots, weights, and control points where those values are part of the constructor contract.

### 4.2 Dimension Definitions

Supported engineering dimensions:

- `linear`
- `radial`
- `diameter`
- `angular`
- `arc_height`
- `ordinate`
- `control_coordinate`

A dimension definition carries measurement points, baseline or reference direction, projection plane, unit, precision, and resolved value. It describes engineering meaning, not screen coordinates.

Examples:

- local blade thickness: pressure and suction points plus the local thickness normal;
- leading/trailing sagitta: endpoint chord plus transition-curve apex;
- root lift: hub support point, blade-side root boundary point, and local support normal;
- pose angle: local reference axis and selected station frame direction;
- profile control: control point plus R/Z ordinate baselines.

### 4.3 Validation

Normal inspection requires:

- unique parameter and primitive ids;
- finite coordinates and values;
- valid group, blade, station, segment, and feature references;
- nondegenerate dimensions;
- agreement between dimension value and authoritative resolved value within declared tolerance;
- at least one applicable view;
- deterministic ordering.

Invalid authoritative evidence fails contract resolution instead of being guessed by the frontend.

## 5. Parameter Coverage

### 5.1 Hub

- meridional NURBS degree, knots, and weights;
- every profile control point R/Z coordinate;
- hub bottom thickness;
- mounting bore diameter and key axial dimensions.

### 5.2 Tip And Shroud

- open tip-reference or closed shroud profile definition;
- every profile control point R/Z coordinate;
- closed shroud inner/outer profile and material thickness;
- applicable clearance and attachment dimensions.

### 5.3 Blade Placement

- main and splitter population;
- angular pitch and phase;
- splitter passage-centering constraint;
- main and splitter streamwise extents.

### 5.4 Spanwise Pose

- all five span stations;
- authoritative station pose parameters;
- sweep, lean, stagger, or the existing canonical equivalents;
- spanwise twist and pose NURBS control points.

### 5.5 Section Loop

- pressure-side NURBS definition and controls;
- suction-side NURBS definition and controls;
- leading-edge NURBS definition, controls, and sagitta;
- trailing-edge NURBS definition, controls, and sagitta;
- local thickness-distribution controls;
- tangent and curvature evidence at all four joins;
- C2/G2 measured results.

### 5.6 Attachments

- root width and lift/height;
- hub-side and blade-side attachment boundaries;
- local support frame and normal;
- closed shroud attachment width and lift/height using the same semantic model.

Derived quality values remain available under a collapsed `Inspection Results` group and are not presented as constructor inputs.

## 6. Workspace Layout

### 6.1 Toolbar

A single compact row, approximately 32 px high, contains:

- `Top`, `Meridional`, and `S-Q + Blade` tabs;
- Blade selector;
- Station selector where applicable;
- current parameter/feature context.

It stays outside the drawing and never overlays geometry.

### 6.2 Parameter Browser

The narrow parameter browser is grouped by geometry and owning curve. Groups are collapsed by default. Expanding a NURBS curve reveals its degree/knots/weights and individual control points.

Click behavior:

- click selects one parameter;
- click selected parameter clears it;
- changing blade or station preserves the parameter type when an equivalent parameter exists;
- otherwise selection clears;
- unavailable parameters are disabled and state their applicable views.

### 6.3 Views

`Top` and `Meridional` are SVG engineering views.

`S-Q + Blade` contains:

- left: equal-aspect S-Q engineering drawing, about 60%;
- right: isolated current blade in Three.js, about 40%.

Both panes share the same selected `parameter_id`. Selecting leading-edge sagitta, for example, shows the chord, apex, controls, and sagitta dimension in S-Q while the 3D pane highlights only the corresponding leading-edge construction curve.

## 7. Drawing Language

### 7.1 Context

- white background;
- thin black visible contours;
- no UV lines;
- no triangle mesh;
- no shaded surface selection;
- no parameter-to-image leader lines.

### 7.2 Selected Feature

- red curve, point, control polygon, local frame, or measurement helper;
- no entire-face material change;
- control points use compact red markers with visible selection hierarchy.

### 7.3 Dimensions

- blue extension lines, dimension lines, arrows, angle arcs, baselines, and text;
- standard engineering placement outside the measured geometry where possible;
- readable fixed-size text independent of viewport width;
- concise units and precision from the contract.

If available space is insufficient, retain the dimension line and value while suppressing secondary descriptive text. Critical contours must not be covered.

## 8. Feature-Specific Presentation

- Profile control point: red profile/control polygon; blue R/Z ordinate dimensions.
- Blade thickness: red pressure/suction sample points and thickness normal; blue double-arrow dimension.
- Edge sagitta: red NURBS edge and apex; blue reference chord and sagitta dimension.
- Pose angle: red local frame direction; blue datum line and angle arc.
- Root lift: red hub-side and blade-side boundaries plus support normal; blue normal-distance dimension.
- C2/G2 join: red tangent and curvature comb at the selected join; measured values in a compact external status strip.

## 9. Degradation Rules

- Missing feature geometry: show `geometry unavailable`; do not infer.
- Missing dimension definition: feature may highlight, but no dimension is drawn.
- Parameter not applicable to active view: disable it with view applicability.
- Invalid references or nonfinite geometry: reject the inspection contract.
- Text collision: hide secondary text before moving any label across critical geometry.

## 10. Testing And Evidence

### 10.1 Backend

- complete parameter-group coverage;
- deterministic ids and ordering;
- reference and finite-coordinate validation;
- dimension values match generated geometry and resolved parameters;
- section-loop controls, edge sagittae, pose controls, and attachment dimensions are present.

### 10.2 Frontend

- projection and equal-aspect drawing tests;
- dimension primitive tests for linear, angular, arc-height, ordinate, and control-coordinate cases;
- exclusive selection and cross-pane synchronization;
- grouped control-point navigation;
- no whole-face selection material changes;
- red feature, blue dimension, black context style contract;
- no UV, triangle, or leader rendering.

### 10.3 Browser Acceptance

Capture desktop and narrow evidence for all three views. Acceptance requires:

- compact controls outside the drawing;
- no incoherent overlap;
- selected geometry is a construction feature, not a whole surface;
- S-Q and blade 3D remain synchronized;
- dimensions are readable and use the approved visual language;
- all viewports are nonblank;
- renderer/context lifecycle remains bounded.

## 11. Explicit Non-Goals

- parameter editing;
- control-point dragging;
- complete ISO/ASME drawing compliance;
- GD&T and tolerance authoring;
- title blocks, sheets, or drawing export;
- a general Drawing DSL;
- changes to V1.1.2 impeller geometry construction.

These capabilities may be introduced later after the inspection contract proves stable.
