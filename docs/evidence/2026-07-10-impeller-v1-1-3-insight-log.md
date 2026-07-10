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
