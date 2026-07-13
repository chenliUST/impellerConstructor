# Impeller V1.1.6 Axis-First Periodic STEP Reconstruction Spec

## Status

- Proposed on 2026-07-13; not yet implemented.
- Target worktree: `impeller-ks007g23b-preset`.
- Target branch: `feature/ks007g23b-preset`.
- Runtime workflow version remains `1.1.6`.
- Canonical constructor and geometry patch remain V1.1.2.
- This document revises the reconstruction algorithm inside the existing
  `impeller_v1_1_6_step_reconstruction_audit` workflow. It does not replace or
  rewrite the already implemented upload, persistence, API, four-pane review or
  deviation-audit contracts.

## Decision

STEP reconstruction shall be axis-first, support-surface-first and
section-driven:

1. resolve the physical rotation axis;
2. recover the hub and tip/shroud meridional supports;
3. construct an adaptive family of 5 to 9 span measurement surfaces;
4. recover one representative blade loop for each periodic blade population;
5. measure side, edge and attachment geometry from those loops;
6. map the measurements into the unchanged V1.1.2 constructor;
7. reconstruct one main blade and, when present, one splitter blade;
8. create all remaining blades only through the measured cyclic patterns.

An open-impeller tip reference is construction geometry, not material. It must
never be emitted or rendered as an outer shroud.

## Problem Statement

The first V1.1.6 generic reconstruction uses several global-envelope
approximations:

- hub and tip profiles are estimated from radial vertex quantiles;
- generic blade thickness is derived from wheel radius and blade count;
- a large non-periodic face can be interpreted as evidence of a closed shroud;
- source section-loop records can describe V1.1 defaults rather than exact STEP
  intersections;
- all periodic blade faces are classified before one coherent representative
  blade body has been recovered.

These approximations can produce the observed failures:

- pressure and suction surfaces do not reproduce local source thickness;
- leading and trailing closure geometry is not tied to measured source loops;
- root height and root attachment width are not recovered from source geometry;
- an open impeller receives a non-existent material outer shroud;
- global deviation can pass a review band while feature-level geometry remains
  visibly wrong.

The source STEP B-Rep remains authoritative. A known source SHA may provide
comparison evidence, but it must not bypass deterministic measurement.

## Scope And Compatibility Boundary

### In scope

- deterministic axis and coordinate-frame recovery;
- source-face periodicity and support-region classification;
- hub NURBS meridional profile recovery;
- open tip-reference inference or closed-shroud inner-profile recovery;
- adaptive exact B-Rep sectioning at 5 to 9 source span stations;
- representative main/splitter blade selection;
- loop segmentation into side and edge curves;
- local thickness, edge shape, root lift and attachment measurement;
- bounded fitting to existing V1.1.2 fields;
- cyclic pattern reconstruction from measured count and phase;
- semantic-region deviation and reconstruction evidence;
- review overlays needed to inspect each recovered stage.

### Frozen compatibility boundary

- No V1.1.2 NURBS, blade-loop, root, tip, shroud or pattern semantics change.
- V1.1.2 continues to consume its canonical five span stations.
- The adaptive 5 to 9 STEP sections are measurement evidence. They are fitted
  into the five-station V1.1.2 representation.
- If the five-station representation cannot reproduce the source within the
  specified bounds, the audit reports representational loss. It must not add
  hidden control fields or silently invoke V1.2 mathematics.
- Existing preset ids and non-STEP synthesis behavior remain unchanged.
- Existing V1.1.6 HTTP endpoints and four review panes remain compatible.

## Authority And Fidelity

| Object | Authority | Permitted use |
| --- | --- | --- |
| Uploaded STEP B-Rep | source authority | topology, analytic surfaces, exact intersections and projection |
| Source tessellation | sampled display evidence | browser display and bounded distance sampling |
| Recovered support/loop measurements | derived source evidence | constrained V1.1.2 parameter fitting |
| V1.1.2 surface graph | review-grade reconstruction | reconstructed model, pattern and comparison |
| Heatmap mesh | sampled deviation evidence | localized inspection only |

No mesh, fitted profile or reconstructed surface may be labeled as imported
B-Rep. Every conversion records its tolerance, coordinate system and source
entity ids.

## Mathematical Domain

### Canonical frame

The resolved axis is represented by origin `O` and unit direction `a`. Source
points are transformed into a right-handed canonical frame in which `a` is the
positive `Z` axis. Cylindrical coordinates are:

```text
R = sqrt(X^2 + Y^2)
theta = atan2(Y, X)
Z = axial coordinate
```

Scale is fixed to `1.0`. Translation and rotation are allowed only through the
recorded rigid source-to-canonical transform. Primary ICP and scale fitting are
forbidden.

### Meridional supports

Hub and tip/shroud supports are fitted in the `(R,Z)` meridional plane as
clamped cubic NURBS curves:

```text
C_h(u) = hub meridional profile
C_t(v) = open tip reference or closed shroud inner profile
```

A monotone correspondence `v = phi(u)` is solved from endpoints, normalized
arc length and local closest-span evidence. It must preserve flowwise order and
must not permit crossing support curves.

### Span measurement surfaces

For a normalized span value `h`, an intermediate meridional curve is:

```text
C_hspan(u) = C_h(u) + beta(h,u) * (C_t(phi(u)) - C_h(u))
```

where `beta(0,u)=0`, `beta(1,u)=1`, and `beta` is monotone in `h`. Revolving
`C_hspan` around the resolved axis produces the source measurement surface
`S_h(u,theta)`.

The interpolation occurs in the meridional domain, not by Cartesian bounding
box interpolation. The resulting surfaces must be ordered and non-intersecting.

### Active root and active tip

The first and last blade-body measurement stations are not assumed to be
`h=0` and `h=1`:

- `h_active_root` lies above the blade-to-hub blend and is measured from the
  retained blade-side boundary;
- `h_active_tip` lies below an open tip cap or below a closed shroud attachment.

Root and tip transition regions are measured separately. This prevents a
section surface from cutting through a fillet and falsely describing it as
blade thickness.

## Reconstruction Pipeline

### Stage 1: Source topology inventory

Load the STEP through OCCT and record solids, shells, faces, wires, edges,
vertices, analytic surface types, area, volume, adjacency and tolerances. Reject
an input with no dominant connected solid or with unresolved unit scale.

The original B-Rep remains in memory for exact face projection and sectioning.
Tessellation is not used for semantic classification when an OCCT query exists.

### Stage 2: Rotation-axis consensus

Axis candidates come from:

- mounting-bore and coaxial cylindrical faces;
- coaxial cones or revolved surfaces;
- circular edge centers and normals;
- periodic face-centroid correlation as secondary evidence.

Candidates are clustered by line distance and angular difference. The selected
axis maximizes analytic area, feature count and periodic closure support. The
manifest records candidate ids, support weights, line residuals and angular
spread. Equivalent competing axes are a hard ambiguity failure.

### Stage 3: Coarse periodic and non-periodic partition

After frame resolution, face signatures are compared under rotations about the
axis. A signature includes geometry type, area, `(R,Z)` bounds, normal
distribution, adjacency degree and transformed sample residual.

This stage separates repeated blade-related faces from non-periodic hub, bore,
bottom and local mechanical features. It does not yet assign pressure/suction
or root/tip labels.

### Stage 4: Hub and tip/shroud support recovery

#### Hub

Hub candidates must be non-periodic material faces and must be adjacent to the
periodic blade-root region or to an exposed axisymmetric flowpath region.
Samples are projected into `(R,Z)` and weighted by meridional arc length so a
dense tessellation does not dominate the fit.

The hub profile is solved with robust constrained least squares:

- clamped cubic degree and V1.1.2 control count remain unchanged;
- endpoints are constrained to measured boundaries;
- radius/order and material-domain constraints are enforced;
- outliers from blade blends, holes and local edge treatments are rejected;
- RMS, P95 and maximum orthogonal projection residuals are retained.

#### Open tip reference

For an open impeller, the source solid normally has no topological free edge at
the blade tip: the tip-cap face shares its boundary with the blade sides and
edge closures. Tip evidence therefore comes from the shared adjacency edge loop
between each periodic blade side/edge component and its per-blade tip-cap
candidate face. The axisymmetric tip reference is fitted through those repeated
tip-cap loops. The cap is blade material, but the fitted reference is a
non-material support with:

```text
semantic_role = open_tip_reference
material = false
render_default = hidden
export_default = excluded
```

It may be displayed only as an explicitly labeled construction overlay.

#### Closed shroud

A closed shroud is accepted only when source topology contains all of:

- a circumferential inner flowpath face;
- a paired outer material face or other finite-thickness evidence;
- boundary/adjacency continuity around the full circumference;
- repeated blade-tip attachment adjacency;
- consistent material-side normals.

Large area, outer radius or centroid position alone is insufficient. Ambiguous
evidence leaves the audit unresolved; it must not default to closed.

### Stage 5: Periodic blade populations

Periodic connected face components, not isolated area clusters, are grouped by:

- count and pitch;
- axial/radial extent;
- streamwise length and wrap;
- face-role signature and adjacency graph;
- phase relative to the main population.

One population yields `main_blade_count=N`, `splitter_blade_count=0`. Two
populations are classified as main and splitter by measured streamwise extent,
inlet location and periodic phase. The splitter phase is measured and is not
forced to half pitch, although deviation from the passage bisector is reported.

The representative instance is the population medoid: the blade whose aligned
surface samples have the smallest total residual to all other instances. The
instance selection and periodic residuals are evidence.

### Stage 6: Adaptive source section lattice

Begin with five stations including active-root, `h=0.25`, `h=0.5`, `h=0.75`
and active-tip. Add stations up to a maximum of nine where any of these exceed
their refinement threshold:

- camber interpolation residual;
- local thickness gradient;
- twist or lean gradient;
- leading/trailing-edge curvature change;
- section-to-section correspondence residual.

Station values, refinement reason and support-surface geometry are persisted.
The same station lattice is used for main and splitter where their active span
domains overlap; population-specific active endpoints remain permitted.

### Stage 7: Exact representative-blade section loops

The uploaded source is commonly one fused solid, so a standalone representative
blade B-Rep does not exist. Each measurement surface is intersected with the
complete source solid by an OCCT section operation. Section edges are filtered
by the selected periodic population's source-face provenance and angular sector,
then ordered through topology and healed only within the recorded source
tolerance. Constructing an artificial temporary blade solid is not required.

A valid blade-body section has one closed contour in the population's angular
sector. Additional contours are retained as unsupported local-feature evidence.
Selection by screen position or largest 2D bounding box is forbidden.

Every accepted loop records:

- source face and edge ids;
- 3D and local `(S,Q)` samples;
- orientation and start landmark;
- closure gap and self-intersection count;
- section-plane normal and material side;
- correspondence to adjacent span loops.

Loops are reparameterized by common landmarks and normalized side arc length.
The algorithm must test both orientation hypotheses and choose the one with the
lowest landmark and tangent mismatch. A 180-degree tangent flip is a hard
failure, not a repairable display artifact.

### Stage 8: Loop decomposition and blade measurements

The loop is decomposed into four source curve families:

1. side A;
2. side B;
3. leading-edge closure;
4. trailing-edge closure.

Pressure/suction names are assigned only when rotation and flow-direction
evidence are available. Otherwise the geometry remains orientation-neutral
`side_a/side_b`.

Landmarks use source-face adjacency first, then streamwise extrema, curvature
peaks and tangent continuity. Each source segment is fitted as a NURBS
measurement curve with its own residual. Edge closures remain source-shaped
splines and are not assumed to be semicircles. Because the frozen V1.1.2
constructor consumes cap roundness/sagitta rather than arbitrary direct segment
curves, these NURBS curves are fitting targets and evidence. Their residual after
mapping is explicit representational loss; this workflow must not add a hidden
`direct_segment_curves` constructor path.

Local thickness is measured in the section tangent plane along the normal to a
fitted camber curve. Side correspondence minimizes normal-intersection,
monotonicity and smoothness error. It must not pair equal array indices or use
radial distance. The resulting field includes:

```text
t(s,h), camber(s,h), edge_sag_le(h), edge_sag_te(h)
```

All thickness samples must be positive and lie inside the source loop. Mean,
maximum, minimum and station residuals are reported separately.

### Stage 9: Root and tip attachment measurement

The blade-to-hub transition is identified from the adjacency chain between
retained blade sides and the recovered hub support. For each representative
blade, measure:

- hub footprint boundary;
- retained blade boundary;
- root lift along the local span direction;
- attachment width in the hub tangent plane;
- blend-section height, bulge and normal-angle change;
- leading and trailing root termination behavior.

The first blade-body loop must be above the recovered blend. A loop lying on the
hub is invalid because it collapses root lift and confounds thickness with the
attachment surface.

For a closed wheel, the blade-to-shroud attachment is measured by the same
algorithm with the material side and span direction reversed. An open wheel has
a real blade tip cap but no shroud attachment.

### Stage 10: Mapping to V1.1.2 and reconstruction

The adaptive measurements are fitted to the unchanged V1.1.2 five-station
canonical payload. The objective has separate weighted terms for:

- hub and tip/shroud meridional profiles;
- section camber and pose;
- normal thickness field;
- leading/trailing closure curves;
- active root/tip offsets;
- root/shroud attachment width and lift;
- count, pitch and family phase.

Each term retains source measurements, mapped values, bounds and residual. A
single aggregate confidence score is forbidden.

The constructor builds only one representative instance per recovered family.
All other blades are generated by the measured cyclic transform. The final
surface graph must report population id, source representative id and instance
phase for every patterned surface.

For open topology, the reconstructed material graph must contain no shroud
surface. The tip reference may remain in construction metadata only.

### Stage 11: Feature-aware deviation

Deviation is evaluated globally and by semantic region:

- hub flowpath;
- bore and hub material;
- side A and side B;
- leading and trailing closures;
- root attachment;
- open tip cap or closed shroud attachment;
- closed shroud material when present;
- unsupported local source features.

The report includes bidirectional distance, normal-angle error, top and
meridional silhouette error, per-station loop Hausdorff error and normal
thickness residual. A low global RMS cannot hide a failed thickness or false
material-surface gate.

## Manifest Delta

The existing final manifest gains an immutable
`axis_first_section_reconstruction` object:

```text
algorithm_revision
canonical_frame
support_recovery
  hub_profile
  tip_reference_or_shroud
  topology_decision
periodic_populations
  main
  splitter_optional
span_measurement_lattice
representative_blades
  source_instance
  section_loops
  side_and_edge_fits
  thickness_field
  root_attachment
v11_2_mapping
pattern_instances
regional_deviation
invariants
```

Every record carries source entity ids, units, method, tolerance, confidence,
residual and coordinate frame. The algorithm revision participates in audit
cache compatibility; a PASS result from the previous generic algorithm must not
be reused after this revision is enabled.

Compact diagnostic artifacts are:

- `axis-fit.json`;
- `support-recovery.json`;
- `periodic-populations.json`;
- `section-loop-measurements.json`;
- `mapped-v11-payload.json`;
- `regional-deviation.json`.

Large STEP and tessellation artifacts remain local and follow the existing
evidence-retention policy.

## Frontend Review Delta

The existing four-pane workspace remains. It gains read-only inspection layers:

- source pane: resolved axis, classified hub samples, tip evidence and selected
  representative blade;
- reconstruction pane: representative blade and patterned instances with
  population labels;
- heatmap pane: semantic-region filter plus global view;
- report pane: support fits, section station selector, loop/thickness plots,
  root measurements and open/closed topology evidence.

An open tip reference is hidden by default and, when enabled, is drawn as a
dashed construction surface. It must never share the shaded material style.

## Failure Reasons

The following stable reasons are required in addition to the existing V1.1.6
upload, persistence and resource failures:

- `v116_axis_consensus_failed`
- `v116_axis_consensus_ambiguous`
- `v116_hub_support_classification_failed`
- `v116_hub_profile_fit_failed`
- `v116_tip_reference_inference_failed`
- `v116_shroud_topology_ambiguous`
- `v116_span_surface_ordering_failed`
- `v116_periodic_population_ambiguous`
- `v116_representative_blade_selection_failed`
- `v116_section_intersection_failed`
- `v116_section_loop_open`
- `v116_section_loop_correspondence_failed`
- `v116_section_tangent_flip_detected`
- `v116_thickness_field_invalid`
- `v116_root_attachment_measurement_failed`
- `v116_v112_mapping_residual_exceeded`
- `v116_false_material_surface_forbidden`

A failure retains all preceding stage evidence. No failure may fall back to the
old global-envelope seed while still reporting `PASS`.

## Confidence Contract

Confidence remains layered:

1. source measurement confidence;
2. semantic classification confidence;
3. NURBS or field fit confidence;
4. V1.1.2 mapping confidence;
5. final reconstruction fidelity.

Each value includes evidence and alternatives. Known-source metadata may raise
interpretation confidence but may not replace source measurement or erase fit
residuals.

## Acceptance Criteria

Let `D` be source outer diameter and `t_mean` the measured representative mean
blade thickness.

### Geometry recovery gates

- Axis line RMS is at most `max(0.02 mm, 0.0002 D)` and candidate angular spread
  is at most `0.05 deg` for analytic CAD inputs.
- Hub profile orthogonal RMS is at most `max(0.10 mm, 0.001 D)`.
- Open tip-reference or closed inner-shroud profile RMS is at most
  `max(0.20 mm, 0.002 D)`.
- Every accepted body loop is closed within `max(0.02 mm, 0.0002 D)`, has zero
  self-intersections and has no tangent flip.
- Normal-thickness RMS is at most `max(0.15 mm, 0.03 t_mean)` and every reported
  thickness is positive.
- Root lift and attachment width are nonzero, source-measured and remain within
  `10 percent` of their source medians after V1.1.2 mapping.
- Main and splitter counts, pitch and phase reproduce the detected periodic
  populations without collision.

### Topology gates

- KS007G23B is classified as open with `13 + 0` blades.
- Its reconstruction contains no material shroud or outer-hub proxy.
- An open blade has a real tip cap and a non-material tip reference.
- A closed-fixture case contains finite-thickness shroud material and a measured
  blade-to-shroud attachment.
- Pattern instances reference exactly one representative source blade per
  population.

### Reconstruction improvement gates

Against the recorded KS007G23B generic baseline:

```text
bidirectional RMS          2.110076 mm
top silhouette Hausdorff   5.254113 mm
meridional Hausdorff      10.168447 mm
```

the promoted algorithm must:

- reduce bidirectional RMS and P95 by at least `30 percent`;
- reduce top and meridional silhouette Hausdorff error by at least `40 percent`;
- pass the thickness and false-material gates independently of global RMS;
- expose any remaining V1.1.2 representational loss by region and station.

These are engineering-preview reconstruction gates, not manufacturing
certification tolerances.

### Determinism and regression gates

- Repeating an audit with the same STEP, tolerances and algorithm revision
  produces identical classification, station lattice, mapped payload and hashes.
- Existing V1.1.2 open/closed preset geometry is byte-for-byte unaffected by the
  STEP analysis modules.
- Existing V1.1.6 upload, queue, restart recovery, deduplication and four-pane
  error handling continue to pass.
- Previous algorithm PASS caches are not reused by the new revision.

## Non-Goals

- Changing V1.1.2 or adopting V1.2 constructor mathematics.
- General-purpose reverse engineering of arbitrary rotating machinery.
- Exact reproduction of splines, bolt holes, balancing cuts and unsupported
  manufacturing details through unrelated impeller parameters.
- Automatic aerodynamic pressure/suction assignment without flow evidence.
- Claiming watertight manufacturing B-Rep, certified metrology or tolerance
  conformance from sampled deviation.
- Reconstructing every periodic blade independently when one cyclic family is
  supported by the source.

## Evidence Requirements

The milestone evidence must record:

- source SHA-256, STEP schema and OCCT/CadQuery versions;
- algorithm revision, tolerances and canonical transform;
- axis candidates and residuals;
- support sample ids, fits and topology decision;
- population counts, phases, representative ids and periodic residuals;
- all 5 to 9 source loops and their decomposition/thickness measurements;
- exact mapped V1.1.2 payload and per-term residuals;
- regional deviation and baseline comparison;
- frontend screenshots of source, reconstruction, heatmap and report;
- test commands, pass counts, skipped tests and known limitations.

Visual similarity is supporting evidence only. Promotion requires the numeric,
topological and provenance gates above.
