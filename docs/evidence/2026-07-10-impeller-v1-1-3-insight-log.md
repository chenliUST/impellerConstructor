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
