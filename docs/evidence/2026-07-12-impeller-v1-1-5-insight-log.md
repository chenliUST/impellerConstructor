# Impeller V1.1.5 Insight Log

## A Section Loop Is Not A Part Projection

The former Top sheet reused a midspan S-Q loop because it was clean and readily
available. That representation cannot show blade sweep, spanwise twist, the hub
topology, or an axial preset whose chosen station has little visible area. A part
view must project resolved surfaces; sections remain separate supporting views.

## Curve Fidelity Needs Source Fidelity And Sampling Fidelity

Increasing SVG resolution does not repair a control polygon drawn as geometry.
V1.1.5 first evaluates the rational NURBS and then samples it adaptively with an
explicit chord-error record. Dense interpolation of already sampled surface
boundaries is used only for presentation continuity and is labelled as such.

## Construction Coverage Must Be Auditable

A visually rich drawing can still omit the parameters that produced the model.
The coverage registry makes omission measurable: each canonical leaf has one
declared destination, and an unaccounted leaf fails validation. This separates
construction disclosure from visual annotation density.

## Full Contracts Are Correct But Poor UI Transport

The complete contract is useful for tests and export, but sending and mounting
every view at once increases browser memory and makes rendering failures harder to
isolate. Per-view payloads plus a run-local immutable cache preserve one semantic
source while bounding frontend work.

Public presets also demonstrated that compact view payloads are insufficient if
the instantiate response has already serialized the complete graph. Drawing-mode
instantiation therefore keeps full run evidence only on the server and returns a
small generation summary. Export work remains owned by CAD Review.

## Large Geometry Must Not Use Variadic Bounds Reduction

The 46-blade Stage 37 Top projection exceeded the JavaScript argument-stack limit
when bounds used `Math.min(...coordinates)`. The failure was deterministic but
looked like a React white-screen crash. Bounds now use an iterative constant-memory
accumulator and are tested with 250,000 points.

## 2D And 3D Sections Must Share Provenance

The five S-Q loops and the five 3D overlays are generated from the same station
records. Independent reconstruction in Three.js would create attractive but
unverifiable overlays and could silently diverge from the drawing.
