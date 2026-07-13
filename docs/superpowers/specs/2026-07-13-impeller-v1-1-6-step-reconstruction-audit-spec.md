# Impeller V1.1.6 STEP Reconstruction Audit Spec

## Status

- Implemented and verified on 2026-07-13.
- Target worktree: `impeller-ks007g23b-preset`.
- Target branch: `feature/ks007g23b-preset`.
- Runtime feature version: `1.1.6`.
- Canonical geometry version remains `1.1.2`.

## Goal

Add a local STEP-loading workflow that treats the imported B-Rep as source
authority, deterministically identifies impeller geometry, maps the measured
source into the existing V1.1.2 parameterization, reconstructs the wheel through
the unchanged V1.1 constructor, and presents four synchronized review panes:

1. source STEP model;
2. V1.1 reconstructed model;
3. geometric deviation heatmap;
4. semantic parameter and quality-difference report.

The workflow must expose each reconstruction stage and its evidence. It must not
silently present the reconstructed V1.1 model as imported STEP geometry.

## Compatibility Boundary

- Do not change the V1.1 blade-to-blade loop, support-profile, pose, thickness,
  root, tip, shroud or edge construction mathematics.
- Do not change canonical NURBS payload version `1.1.2`.
- Do not change existing preset ids or their historical behavior.
- V1.1.6 adds an analysis and reconstruction-audit contract around the existing
  constructor; it is not the V1.2 geometry redesign.
- The uploaded STEP remains the source authority. The V1.1 reconstruction remains
  `review-grade` even when source measurements are exact.

## Terminology

- **Source geometry**: the imported OCCT B-Rep from the uploaded STEP.
- **Source mesh**: a controlled tessellation of source geometry for browser display
  and distance sampling. It is not the source authority.
- **Semantic classification**: deterministic assignment of source faces and edges
  to hub, shroud/tip, blade sides, edge closures, attachments, bore and auxiliary
  material roles.
- **Measured source parameter**: a value calculated directly from source B-Rep.
- **Mapped V1.1 parameter**: a measured value translated into an existing V1.1.2
  field or scalar.
- **Reconstruction**: geometry instantiated by the unchanged V1.1.2 constructor.
- **Deviation**: measured distance between source and reconstructed geometry after
  the recorded deterministic frame alignment.

## Supported Input

V1.1.6 accepts a local STEP file under these bounds:

- AP203, AP214 or AP242 syntax readable by the installed OCCT build;
- one connected dominant solid and one impeller rotation axis;
- radial or mixed-flow open/closed impeller geometry compatible with the V1.1
  constructor;
- maximum upload size 100 MiB;
- maximum source face count 20,000 before explicit rejection;
- filename is display metadata only and may not control a filesystem path.

Assemblies, multiple unrelated solids, mesh-only STEP, non-impeller parts and
ambiguous axis/periodicity are rejected with explicit reasons. V1.1.6 does not
guess a usable constructor payload when required semantic evidence is absent.

## Reconstruction Stages

Every audit has an immutable input hash and a monotonic stage state:

1. `uploaded`: stream stored in the audit run directory; SHA-256 recorded.
2. `brep_loaded`: STEP read by OCCT; topology and units validated.
3. `frame_resolved`: axis, origin, handedness and source-to-canonical transform
   selected from coaxial analytic faces and periodic evidence.
4. `semantics_classified`: source face/edge role table produced.
5. `parameters_extracted`: existing V1.1.2 fields fitted with residuals.
6. `hub_reconstructed`: current constructor evaluated at `hub_support`.
7. `blade_surfaces_reconstructed`: current constructor evaluated at
   `blade_surfaces` for representative and periodic blade evidence.
8. `edge_closures_reconstructed`: current constructor evaluated at
   `edge_closures` for the final reconstructed graph.
9. `deviation_measured`: meshes aligned and bidirectional errors calculated.
10. `complete`: all review artifacts and the report contract are available.

A failed audit retains all completed stage evidence and reports one terminal
failure code. Retrying creates a new audit id rather than mutating old evidence.

## Source B-Rep Analysis

### Topology inventory

The loader records:

- STEP schema, producer metadata and source unit;
- solid, shell, face, edge and vertex counts;
- exact B-Rep area, volume, centroid and axis-aligned bounds;
- analytic face types and parameters;
- B-spline degree, knot, weight and parameter-domain summaries;
- connected-component and shared-edge adjacency data.

Exact B-Rep quantities and tessellated quantities are stored separately.

### Axis and frame resolution

Candidate rotation axes come from coaxial cylinders, cones, tori and rotational
periodicity. A candidate score includes:

- summed analytic-face area;
- coaxial bore/outer-envelope agreement;
- repeated-face rotational agreement;
- centroid and principal-axis consistency.

The selected source frame is mapped to canonical `+Z` with a rigid transform.
Scale is resolved from STEP units and is never fitted by ICP. Optional rigid ICP
may be reported as a secondary diagnostic, but primary deviation uses only the
recorded semantic frame alignment so fitting cannot hide parameter errors.

For periodic wheels, rotation about the confirmed axis is an unresolved gauge
freedom. Primary comparison therefore performs a bounded symmetric search over
one blade pitch, records the selected phase and before/after objective, and
applies only that axial rotation. Translation, scale fitting and free rigid ICP
remain forbidden in the primary result.

### Periodic blade population

The classifier groups faces by surface type, area, parameter-domain signature,
adjacency and rigid rotational equivalence. A valid population requires:

- an integer count of at least two;
- a common pitch within tolerance;
- consistent representative-face adjacency;
- full-rotation closure within angular tolerance.

Main and splitter populations are separate periodic groups. A single periodic
group maps to `main_blade_count=N`, `splitter_blade_count=0`.

### Semantic face roles

The source semantic manifest supports:

- `hub_support`;
- `shroud_support` or `open_tip_reference`;
- `blade_side_a` and `blade_side_b`;
- `blade_pressure` and `blade_suction` only when orientation evidence is sufficient;
- `leading_edge_closure` and `trailing_edge_closure`;
- `open_tip_surface` or `tip_to_shroud_attachment`;
- `root_to_hub_attachment`;
- `mounting_bore`;
- `auxiliary_hole`;
- `hub_bottom`, `hub_wall`, `hub_top_cap` and `other_material`.

Face roles carry source face ids, adjacency evidence, periodic instance id,
classification confidence and rejection alternatives. Pressure/suction and
leading/trailing labels may not be inferred solely from screen orientation.

## Mapping Into Existing V1.1.2 Geometry

### General rule

The fitter may optimize existing V1.1.2 inputs, but may not add control fields or
alter their mathematical meaning. Every mapped value reports:

- source measurement and unit;
- measurement method and source entity ids;
- measurement confidence;
- mapped V1.1 value;
- semantic mapping confidence;
- fit residual and reconstruction fidelity.

One aggregate confidence number is forbidden because it conflates these distinct
questions.

### Support profiles

Hub and tip/shroud source curves are sampled from classified B-Rep faces in the
resolved meridional frame. They are fitted to the exact current V1.1.2 support
curve representation:

- current degree and clamped knot policy remain unchanged;
- six V1.1 control points are solved by bounded least squares;
- endpoints are constrained to measured source boundaries;
- radial monotonicity and hub/tip material ordering are enforced;
- RMS, P95 and maximum chord residual are recorded.

Measured points must not be copied into the control-point array and described as
NURBS poles without performing this fit.

### Blade and pose fields

One representative source blade per population is mapped to a common physical
`(s,h)` domain using meridional stream length and normalized hub-to-tip span.
Existing V1.1 parameters are then fitted, including where applicable:

- `blade_wrap_deg`;
- `blade_lean_deg`, leading/trailing lean and sweep;
- `main_flow_turn_q_mm`, spanwise turn delta and midspan bow;
- average and maximum blade thickness;
- LE/TE cap roundness;
- root width/lift and active root offset;
- open-tip or closed-shroud attachment mode.

The objective uses five source S-Q sections at the existing V1.1 span stations,
with separate terms for camber, PS/SS separation, edge endpoints and pose. Bounds
come from the current DSL schema and material-domain constraints.

### Holes and unsupported source features

Bores and finite hub material parameters are mapped only where current V1.1
semantics exist. Auxiliary holes, splines, balancing cuts and unsupported local
features remain source-only roles and appear in the difference report. They are
not approximated by unrelated V1.1 parameters.

## Reconstruction Contract

The final constructor call uses:

- `geometry_version=1.1`;
- `geometry_patch_version=1.1.2`;
- fitted current parameters and current canonical payload;
- existing geometry stages and validation gates;
- no private STEP-specific geometry branch.

The audit manifest embeds the exact payload used for reconstruction and links it
to the resulting generation id. Rendering, report and comparison all consume
that same generation-bound graph.

## Deviation Analysis

### Geometry used

- Source distances are evaluated against the imported B-Rep or a documented
  OCCT projection routine when available.
- Reconstruction distances are evaluated against the generated V1.1 surfaces;
  a controlled comparison mesh may be used only with its tessellation tolerance
  recorded.
- Primary distance is unsigned because the review reconstruction may be an
  unsewn surface graph. Signed distance is optional and may be reported only when
  both compared domains are closed and normals are validated.

### Metrics

Global and semantic-role metrics include:

- source-to-reconstruction RMS, P95 and maximum distance;
- reconstruction-to-source RMS, P95 and maximum distance;
- bidirectional symmetric Chamfer distance;
- normal-angle mean, P95 and maximum where normals are comparable;
- source/reconstruction area, volume and centroid delta where both are valid;
- Top and Meridional silhouette Hausdorff distance;
- five-station S-Q camber and thickness residuals;
- unmatched source and reconstructed semantic roles.

All distance metrics are reported in millimetres and normalized by source outer
diameter. Review bands are descriptive, not manufacturing certification.

### Heatmap

The heatmap colors the reconstructed comparison mesh by nearest source distance.
It provides:

- fixed legend with min, median, P95 and max;
- selectable global or semantic-role scale;
- clipped color scale at P95 with above-limit points explicitly marked;
- no smoothing that changes scalar values;
- click/hover readout with source/reconstruction coordinates, distance and roles.

## API Contract

The active API adds a generation-bound audit resource:

```text
POST /api/step-reconstruction-audits?filename=<display-name>
Content-Type: application/step

GET  /api/step-reconstruction-audits/{audit_id}
GET  /api/step-reconstruction-audits/{audit_id}/manifest
GET  /api/step-reconstruction-audits/{audit_id}/artifacts/source.stl
GET  /api/step-reconstruction-audits/{audit_id}/artifacts/reconstruction.stl
GET  /api/step-reconstruction-audits/{audit_id}/artifacts/heatmap.json
```

The upload returns `202` after hashing, bounded validation and scheduling. A
single local worker executes geometry work so concurrent audits cannot exhaust
memory. Status responses expose the current stage, completed stages, progress,
elapsed time and structured failure.

Raw request bodies avoid a new multipart dependency. The backend ignores path
components in `filename`, writes only under its configured run root, and never
stores uploaded customer STEP files in the repository.

## Audit Manifest

The immutable final manifest contains:

```text
contract_id: impeller_v1_1_6_step_reconstruction_audit
runtime_version: 1.1.6
canonical_geometry_version: 1.1.2
source: hash, units, STEP metadata, topology, exact B-Rep metrics
frame: source axis, origin, handedness, rigid transform, evidence
semantics: face/edge role assignments and confidence
parameter_mapping: measurement, mapped value, confidence layers, residual
reconstruction: canonical payload, generation id, validation status
comparison: tolerances, tessellation, global and per-role metrics
artifacts: URLs, SHA-256, fidelity labels
limitations: unsupported source roles and failed/ambiguous classifications
```

## Frontend Experience

Add a third read-only workspace named `STEP Reconstruction` without restoring the
removed parameter editors.

### Input and progress

- File button accepts `.stp` and `.step`.
- The selected filename, size and SHA-256 appear before analysis begins.
- A compact stage rail shows the ten reconstruction stages.
- Failures remain visible with evidence and do not blank the application.
- Reloading an audit manifest restores the completed review without re-upload.

### Four-pane layout

The workspace is a stable 2x2 grid:

1. `Source STEP` - neutral material, source semantic-role selection.
2. `V1.1 Reconstruction` - current generated model and its fidelity label.
3. `Deviation Heatmap` - reconstruction mesh colored by source distance.
4. `Parameter / Quality Report` - searchable semantic table and global metrics.

The three geometric panes use one shared Three.js renderer with scissor viewports
to avoid WebGL-context crashes. Cameras are orthographic/perspective matched and
orbit, zoom and preset-view changes are synchronized. Geometry remains centered
in the recorded canonical frame; each pane may not independently auto-fit to a
different scale.

The report separates:

- exact source facts;
- measured source parameters;
- mapped V1.1 parameters;
- reconstructed measured values;
- source-minus-reconstruction delta;
- measurement confidence;
- semantic mapping confidence;
- geometric fit residual;
- unsupported source features.

## Failure Reasons

Required stable reasons include:

- `v116_step_size_limit_exceeded`;
- `v116_step_parse_failed`;
- `v116_step_no_solid`;
- `v116_step_multi_solid_unsupported`;
- `v116_step_face_limit_exceeded`;
- `v116_rotation_axis_ambiguous`;
- `v116_periodic_blade_population_missing`;
- `v116_hub_support_unresolved`;
- `v116_tip_or_shroud_support_unresolved`;
- `v116_blade_side_pairing_failed`;
- `v116_v11_parameter_fit_failed`;
- `v116_reconstruction_validation_failed`;
- `v116_comparison_alignment_failed`;
- `v116_deviation_measurement_failed`;
- `v116_occt_unavailable`.
- `v116_audit_persistence_failed`.

## Performance And Resource Bounds

For the supplied 5.6 MiB, 240-face KS007G23B model on the current workstation:

- upload acceptance and audit id: under 2 seconds;
- source parse and topology inventory: target under 15 seconds;
- semantic classification and parameter fit: target under 45 seconds;
- full current-rule reconstruction: target under 180 seconds;
- comparison and browser artifacts: target under 60 seconds;
- source and comparison meshes: at most 250,000 triangles per displayed LOD;
- frontend creates one live WebGL context for the entire four-pane workspace.

Timeouts are reported as stage failures with retained evidence, not generic fetch
errors.

## Acceptance Criteria

### Backend

- The supplied KS007G23B STEP loads as one source-authority solid and reports its
  known topology, `R51.6`, `36.5 mm`, `R7.9`, three `R2` holes and 13-fold pitch.
- Source face roles identify hub support, tip surface, representative blade-side
  pair, root attachments and unsupported holes with source ids.
- Six-point V1.1 support profiles are fitted, not copied, and report finite
  residuals.
- The unchanged V1.1.2 constructor produces a final generation with its current
  validation status exposed.
- Bidirectional global and per-role deviation metrics are finite and traceable to
  recorded meshes/tolerances.
- Exact source dimensions, mapping confidence and reconstruction fidelity remain
  separate in the report.

### Frontend

- Source, reconstruction, heatmap and report appear simultaneously in four panes.
- Camera interaction is synchronized and uses one WebGL renderer/context.
- Heatmap legend and point readout use millimetres and semantic role ids.
- Unsupported STEP features are visible in the report.
- Upload, processing failure and rendering failure cannot blank the page.

### Regression

- Existing V1.1.2 geometry tests remain unchanged and pass.
- Existing V1.1.5 CAD Review and Engineering Drawing remain functional.
- Existing preset generation does not invoke STEP analysis.
- Uploaded STEP and generated audit artifacts remain outside git status.

## Non-Goals

- Exact reverse engineering of arbitrary STEP into editable V1.2 geometry.
- Direct reuse of source STEP faces inside the V1.1 reconstruction.
- Modification of V1.1 geometry rules to improve the KS007G23B fit.
- CAD-certified sewing, healing or manufacturing-equivalent STEP export.
- Assembly reconstruction, automatic repair of corrupt STEP or general-purpose
  feature recognition outside the impeller domain.
- Interactive parameter dragging or automatic acceptance of a low-residual fit.

## Evidence Policy

Implementation evidence must record exact commands, OCCT/CadQuery versions,
source SHA-256, tolerances, stage durations, artifact hashes, test results and
known classification/fit limitations. Customer STEP data and ad hoc browser
captures are not committed. Only compact manifests, numeric reports and
deliberately retained screenshots may enter `docs/evidence/`.
