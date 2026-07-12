# Impeller V1.1.3 Insight Log

Date: 2026-07-10

## Insight 1: Generated Geometry Is The Evidence

Textual preset summaries cannot prove that resolved parameters are represented by generated geometry.

Inspection therefore reads the generated manifest and surface graph after synthesis instead of presenting preset seeds as resolved measurements.

## Insight 2: Geometric Views Must Share State And GPU Resources

Independent view renderers risk geometry/state drift and unnecessary GPU duplication.

The 3D, top, meridional, and geometric Quad panes use one renderer, one scene, synchronized selection, and deterministic cameras.

## Insight 3: S-Q Needs A Mathematical Renderer

S-Q is a mathematical section domain and is clearer as SVG than as an arbitrary 3D camera projection.

SVG keeps semantic segments, canonical control geometry, continuity labels, and selectable control points explicit.

## Insight 4: Inspection Precedes Editing

Read-only inspection must precede direct graphical editing so the parameter-to-geometry mapping can be evaluated first.

Existing parameter and curve editors remain the only mutation paths in V1.1.3.

## Insight 5: Provenance Follows Visible Evidence

Generation identity must change when any visible or inspectable source evidence changes. Historical UV exemptions are metadata-positive: only explicitly hidden, reference-only helper sampling may be ignored; a broad surface-role exemption hides stale manufactured evidence.

## Insight 6: Equal Aspect Requires Equal Units

Normalized streamwise coordinates and millimetric transverse coordinates cannot be fitted with a meaningful equal aspect ratio. Each loop therefore retains its source values while exposing a geometry-derived `streamwise_metric_scale_mm` and resolved metric display points.

## Insight 7: Selection Is A Relationship Transition

Inspection selection is not an arbitrary object merge. A pure reducer normalizes blade, station, loop, segment, control, and surface-family dependencies so cross-blade and cross-station changes cannot leave stale highlights.

## Insight 8: Malformed Evidence Is A First-Class State

Producer and consumer validation both check nested records, exact ID sets, closure, uniqueness, ownership, and bidirectional references. Invalid contracts become documented failure states instead of JavaScript exceptions or a blank workspace.

## Insight 9: Hash Exemption Requires Total Non-Inspectability

Ignoring a helper UV grid in provenance is valid only when that grid is also excluded from rendering, camera fitting, picking, and annotations. Otherwise the same generation ID could frame or label a different scene.

## Insight 10: Support Selection Has No Blade Owner

Hub and shroud support surfaces are legitimate selectable geometry without a `blade_instance_id`. Their selection clears blade-owned station, segment, and control identities while the mathematical S-Q view falls back to the first valid blade station.

## Insight 11: Inspection Contours Are Not UV Or Mesh Wireframe

Internal UV is useful for surface construction debugging but obscures parameter-to-geometry inspection. The quiet technical view uses the already generated surface mesh only as a shaded carrier and derives necessary boundaries with an angle-filtered `EdgesGeometry`; UV and triangle edges stay hidden.

## Insight 12: Parameter Rows Should Select Geometry, Not Point At It

Leader lines add clutter and require fragile projection/layout logic. Native HTML parameter buttons map directly to generated surface ids, preserve keyboard behavior, and highlight geometry without covering the 3D canvas with an interactive SVG layer.

## Insight 13: Selection Must Expose Authoritative Construction Evidence

Parameter selection identifies authoritative construction evidence; it never substitutes whole-surface material highlighting for feature geometry. A red primitive that is detached from its blade, a blue dimension without its black construction boundaries, or a parameter disabled in its required view is not acceptance evidence even when the DOM contains correctly colored elements.

## Insight 14: Pixel Evidence Complements DOM Contracts

Class names and computed colors prove styling intent, not visible engineering content. Task 8 therefore checks drawing-interior black/red/blue pixels and verifies that red 3D feature pixels contact neutral blade context. This caught a blank Top drawing, absent Meridional root boundaries, and detached S-Q-derived 3D feature geometry that element-count assertions alone reported as present.
