# Impeller V1.1.3 Monochrome Parameter Inspection Design

**Date:** 2026-07-11

## Goal

Make Parameter inspection visually quiet and directly selectable: white surfaces, black necessary contours, no UV grid, no parameter-to-model leader lines, and parameter rows that highlight their related generated geometry.

## Scope

This is a frontend inspection-layer hardening change. It does not change V1.1.2 geometry construction, the V1.1.3 backend inspection contract, preset ids, mesh generation, or export behavior.

## Rendering

- Render inspectable surfaces with an opaque or near-opaque white material.
- Do not show `isSurfaceUvWire` overlays in Parameter inspection.
- Add black contour overlays with `THREE.EdgesGeometry` over the existing generated surface geometry.
- Use an angle threshold so smooth tessellation and UV subdivisions do not become visible lines.
- Render ordinary geometry with white fill and black contour.
- Highlight selected geometry by inversion: black fill and white contour. Do not restore the former green/orange inspection palette in this workspace.
- Preserve depth testing so hidden contours do not show through the part.

This is a white-surface/black-contour technical view, not a transparent triangle wireframe and not a screen-space silhouette post-process.

## Parameter Interaction

- Parameter rows remain visible according to the existing `key`, `selected`, and `all` levels.
- Remove every SVG leader line between a parameter row and geometry.
- Parameter rows are keyboard-accessible buttons.
- Clicking a row selects it exclusively; clicking it again clears it.
- Clicking another row replaces the active parameter.
- Clicking geometry, changing blade, changing station, or changing inspection tab clears the active parameter row.
- The selected row uses a restrained inverted/high-contrast state.

Parameter-row selection is separate from the existing geometry-selection record. The workspace stores only the active annotation id. Highlight surface ids are derived from the selected annotation and temporarily take priority over ordinary geometry selection. This avoids expanding the backend contract or adding another selection ontology.

## Geometry Targets

- Surface annotation: that exact surface.
- Section segment: the corresponding pressure, suction, leading-edge, or trailing-edge surface on the selected blade.
- Thickness and blade pose: all surfaces of the selected blade.
- Root offset: root surfaces of the selected blade.
- Tip offset: tip or shroud-attachment surfaces of the selected blade.
- Hub profile: inspectable hub support/material surfaces.
- Tip or shroud profile: inspectable tip-reference or shroud support/material surfaces.
- Blade counts, angular pitch, and splitter passage fraction: all blade-owned surfaces.

If a row has no valid target surfaces, it remains readable but is not interactive. No guessed geometric anchor is created.

## Components

- `parameterInspectionModel.js`: attach deterministic target surface ids to annotations.
- `ParameterAnnotationOverlay.js`: render clickable rows without leaders and report annotation clicks.
- `ParameterInspectionWorkspace.js`: own the active annotation id, toggle it, clear it on navigation, and choose annotation targets over normal selection targets.
- `InspectionScene.js`: apply monochrome materials and contour visibility in Parameter inspection.

Reuse the existing surface group, selection reducer, annotation filtering, and Three.js installation. Add no dependency and no new rendering subsystem.

## Tests

- Parameter annotations resolve to the intended surface ids.
- Clicking a row selects it, selecting another replaces it, and clicking it again clears it.
- Geometry and navigation actions clear parameter selection.
- Annotation markup contains no leader line and remains keyboard accessible.
- Parameter inspection hides UV overlays.
- Surface material is monochrome and selected geometry uses the specified highlight.
- Contours use `EdgesGeometry`, remain depth-tested, and do not expose mesh triangle wireframe.
- Full frontend regression and Playwright screenshots cover desktop 3D, meridional, Quad, and narrow S-Q.

## Acceptance

1. No internal UV grid appears in 3D, Top, Meridional, or geometric Quad panes.
2. The part reads as white surfaces with black necessary contours.
3. No line connects a parameter row to the model.
4. Clicking a parameter row highlights only its corresponding geometry.
5. Row selection is exclusive and toggleable.
6. Existing model picking, blade/station navigation, S-Q controls, and read-only guarantees remain functional.
