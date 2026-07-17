# Impeller V1.1.6 R16 Section-Curve Authority Reconstruction Repair

Date: 2026-07-18

Execution status: proposed implementation plan. No R16 implementation work has
started.

## Goal

Replace the lossy STEP-section-to-scalar-field reconstruction path with a
source-conforming section-curve authority. Correct the globally distorted blade
shape, the artificial common-Z cutoff, the incomplete active-span section
family, and the misleading source/reconstruction loop overlays without
regressing the completed R15 axis-polarity, support-profile, hub-closure,
deviation-performance, or frontend-status work.

## Release And Branch Boundary

- Runtime release remains `1.1.6`.
- Canonical geometry contract remains `1.1.2` for historical presets.
- STEP reconstruction receives a new opt-in geometry patch and audit
  implementation revision, provisionally
  `axis_first_section_curve_authority_r16_1`.
- R16 is not a new public geometry version. It is a reconstruction-algorithm
  revision inside V1.1.6.
- Historical V1.1/V1.1.2 preset construction remains on the existing scalar
  field path. Direct section-curve authority is enabled only for an
  authenticated STEP reconstruction payload.
- The dirty R15 branch must first be checkpointed with its tests and evidence.
  R16 implementation then starts on a follow-on branch/worktree such as
  `fix/v1.1.6-r16-section-curve-authority`.
- Do not rewrite or relabel the completed R15 audit. Retain
  `step-audit-e27b4c0e7c854c88` as the rejected defect baseline.

## Confirmed Failure Chain

The exact STEP section curves are broadly representative of the source blade,
but the current mapping does not use them as construction curves.

1. Exact section points are measured in physical meridional arc length
   `S_physical_mm` and circumferential arc length `Q_physical_mm`.
2. `_station_for_mapping` discards the physical camber S coordinate and stores
   only normalized sample fractions plus Q and thickness.
3. The adaptive extension independently renormalizes each station to `[0, 1]`.
4. The V1.1.2 constructor maps every station back onto the complete support
   profile `[0, 1]`, forces pressure and suction sides to share identical
   streamwise endpoints, and applies measured normal thickness only in Q.
5. The downstream surface family faithfully lofts those already-invalid loop
   rows, so the surface is globally distorted before meshing or rendering.

Measured R15 evidence that R16 must preserve as regression fixtures:

- active-root physical body interval: approximately `0.109 .. 0.944` of the
  local support profile, currently expanded to `0 .. 1`;
- active-tip physical body interval: approximately `0.303 .. 0.954`, currently
  expanded to `0 .. 1`;
- pressure/suction leading endpoint streamwise stagger grows from about
  `2.550 mm` at active root to `8.141 mm` at active tip, currently collapsed to
  zero;
- source-to-generated leading-region R-Z error is approximately `8.1 .. 9.1
  mm`;
- the global active-root support fraction `0.3411` is derived from a minimum
  support separation and therefore places some sections several millimetres
  above the actual local root boundary;
- the adaptive NURBS scalar fields interpolate their own samples to better than
  `5e-7`, proving that the primary error is coordinate semantics and lost
  geometry, not a U/V control-net transpose;
- source loop overlays are still in source coordinates while source mesh and
  reconstructed geometry are canonical; the displayed blue loops are source
  evidence reused in the reconstruction pane, not reconstructed-surface
  intersections.

## Architecture

Introduce a V1.1.6-only `direct_section_curve_network` reconstruction mode.
The authoritative reconstruction chain becomes:

```text
STEP B-Rep
  -> canonical frame
  -> authenticated support surfaces and attachment boundaries
  -> S-dependent active-span carriers H_root(S), H_tip(S)
  -> exact PS/SS/LE/TE section curves with physical S-Q and XYZ provenance
  -> compatible NURBS curve network
  -> pressure/suction/edge surfaces interpolating that network
  -> root/tip attachments from the actual retained boundaries
  -> corresponding-surface deviation
```

Camber, normal thickness, and pose remain useful derived parameters and
inspection evidence. They stop being the geometry authority for STEP
reconstruction.

## Task 0: Freeze R15 And Establish Failing Regressions

- [ ] Record the current branch, commit, dirty-file inventory, audit id,
  artifact hashes, implementation revision, source tolerance, elapsed time,
  and rejection reasons.
- [ ] Preserve canonical source STEP/STL, R15 reconstruction STL, Geometric
  Manifest, heatmap, and the four screenshots exposing blade distortion.
- [ ] Add a compact deterministic KS section fixture derived from the existing
  audit. Store only the minimum curve/support evidence needed by tests, not the
  complete external STEP model.
- [ ] Add first-failing regression tests for:
  - physical S-coordinate retention;
  - nonzero PS/SS leading endpoint stagger;
  - local active-root position;
  - canonical source-loop overlay;
  - generated-loop overlay being a true reconstructed-surface intersection;
  - no artificial shared leading-edge plane.
- [ ] Checkpoint R15 independently before creating the R16 implementation
  branch/worktree.

## Task 1: Explicit Curve Coordinate And Provenance Contract

Extend each section-curve record with:

- `coordinate_frame`: `source_step_xyz_mm` or
  `canonical_axis_frame_xyz_mm`;
- immutable source XYZ points and canonical XYZ points;
- `s_physical_mm`, `q_physical_mm`, and normalized display parameter `u` as
  separate fields;
- carrier profile id and carrier parameter/witness for every point;
- raw support-span position and active-span coordinate;
- curve role, source face ids, source edge ids, material orientation, degree,
  knots, weights, and fit residual;
- separate start/end witness records for pressure and suction sides;
- explicit closure classification:
  `sharp_shared_seam`, `finite_edge_face`, or `measured_transition_curve`.

Implementation rules:

- [ ] Transform exact section curves to canonical coordinates once in the
  backend. Do not make the frontend infer or apply frame transforms.
- [ ] Never overwrite source-frame points; preserve both forms with provenance.
- [ ] Stop discarding `camber_sq_mm[0]` and side endpoint S coordinates in
  `_station_for_mapping`.
- [ ] Stop interpreting normalized sample fraction as support-profile
  parameter.
- [ ] Reject incomplete frame or carrier provenance with stable reasons instead
  of silently normalizing.

Tests:

- [ ] The current `+6.550302 mm` canonical Z translation is applied exactly
  once.
- [ ] Canonical source loops lie on their STEP section edges within source
  tolerance.
- [ ] Rigidly transformed copies recover the same canonical curve signatures.
- [ ] Round-trip `XYZ -> carrier S-Q -> XYZ` residual stays within
  `max(source_tolerance_mm, 0.05 mm)`.

## Task 2: S-Dependent Active Span Authority

Replace the global active interval with two bounded fields:

```text
H_root(S) = retained blade-body boundary above the hub attachment
H_tip(S)  = retained blade-body boundary below the open tip or shroud attachment
H(S, eta) = H_root(S) + eta * (H_tip(S) - H_root(S))
```

- [ ] Recover root and tip attachment boundaries along authenticated support
  correspondence rather than dividing maximum lift by global minimum support
  separation.
- [ ] Fit positive, ordered NURBS curves for `H_root(S)` and `H_tip(S)`.
- [ ] Preserve local lift in millimetres and its support-fraction form; neither
  representation may be reconstructed from a global scalar.
- [ ] Generate each interior measurement carrier from `H(S, eta)`, so the
  carrier follows the physical blade body instead of a constant support
  fraction.
- [ ] Start with root, midspan, and tip carriers, then adaptively insert stations
  where curve shape, thickness, endpoint stagger, or surface interpolation
  error exceeds tolerance.
- [ ] Make maximum station count configurable and evidence-driven. Do not hard
  code five or nine as mathematical authority.
- [ ] Reject crossed or vanishing active spans before STEP sectioning.

Tests:

- [ ] Root carrier offset matches measured local root lift across S within
  `max(2 * source_tolerance_mm, 0.10 mm)`.
- [ ] Tip carrier matches open-tip/shroud witnesses with the same bound.
- [ ] `H_root(S) < H_tip(S)` at all certified samples and extrema.
- [ ] Adaptive refinement is deterministic and converges on a synthetic
  twisted blade with known boundaries.

## Task 3: Preserve Full Section-Loop Geometry

- [ ] Keep exact pressure and suction section curves in physical coordinates;
  do not reconstruct them as `camber Q +/- thickness/2`.
- [ ] Preserve independent PS and SS streamwise ranges and endpoint stagger.
- [ ] Use chord-length or centripetal curve parameters only as local NURBS
  parameters. Do not substitute them for physical support S.
- [ ] Normalize orientation consistently from leading to trailing while
  retaining material-side evidence.
- [ ] For two-edge STEP loops, keep the two side curves and sharp shared seams.
  Do not steal portions of the side curves to manufacture finite LE/TE arcs.
- [ ] For sources with real finite edge faces, section and fit those faces as
  independent edge curves.
- [ ] For rounded source closures without a separately classified face, retain
  the measured closure curve directly and its side-boundary derivatives.
- [ ] Use degree elevation and knot insertion to make each role's curve family
  compatible without changing its geometry.

Required KS regression witnesses:

- [ ] active-root PS/SS LE S stagger remains approximately `2.550 mm`;
- [ ] active-tip stagger remains approximately `8.141 mm`;
- [ ] no constructor step collapses either value to zero;
- [ ] pressure and suction endpoint R-Z positions remain within the section
  fitting tolerance.

## Task 4: Direct Section-Curve Surface Construction

Add a versioned builder, provisionally
`impeller_v11_6_section_curve_surfaces.py`.

- [ ] Build pressure and suction surfaces by constrained skinning/lofting
  through the compatible canonical section curves.
- [ ] Interpolate the retained section curves exactly in the span direction.
- [ ] Use bounded smoothing only between measured carriers; smoothing may not
  move an authoritative section curve.
- [ ] Preserve shared boundary nodes and orientation between pressure, suction,
  leading, trailing, root, and tip roles.
- [ ] Construct finite leading/trailing surfaces only when the source topology
  supplies finite closure curves. Represent sharp seams as shared topology, not
  zero-area decorative faces reported as fillets.
- [ ] Generate the open-tip cap or shroud attachment from the actual terminal
  section boundary.
- [ ] Attach root surfaces to the actual `H_root(S)` blade boundary and measured
  hub attachment boundary.
- [ ] Publish the curve network, section interpolation residuals, boundary gaps,
  foldover count, and surface-normal orientation in the Geometric Manifest.
- [ ] Keep the existing V1.1.2 loop/surface builder untouched for historical
  preset synthesis. Select the direct builder only through the authenticated
  R16 reconstruction contract.

Tests:

- [ ] Every generated surface intersects each authoritative carrier in its
  corresponding measured curve within
  `max(2 * source_tolerance_mm, 0.10 mm)` bidirectional Hausdorff distance.
- [ ] Shared-edge coordinate gap is no greater than `0.05 mm`.
- [ ] Surface grids contain no foldovers, row reversals, or normal flips.
- [ ] Pressure/suction leading endpoints retain their independent S positions.
- [ ] A synthetic source with a sharp leading seam creates no artificial cap;
  a source with a finite rounded edge creates a finite edge surface.

## Task 5: Derived Parametric Fields Without Geometry Loss

Camber, normal thickness, and pose are retained for inspection and future
editing, but become derived evidence in direct reconstruction mode.

- [ ] Derive camber from corresponding PS/SS points on the reconstructed
  section curves.
- [ ] Derive thickness along the true S-Q normal, retaining both S and Q
  components of the offset.
- [ ] Derive pose from the physical-metric camber tangent.
- [ ] Mark field authority as `derived_from_direct_section_curve_network`.
- [ ] Remove any direct-mode geometry path that applies measured normal
  thickness as a pure Q offset.
- [ ] Add a validation gate ensuring the derived fields regenerate the measured
  witnesses only when explicitly using a lossless normal-offset formulation.
- [ ] Continue exposing the fields in manifests and drawings; do not silently
  remove the current semantic vocabulary.

## Task 6: Separate Flowpath Endpoints From Hub Material Closure

- [ ] Retain R15 support endpoint roles, but stop using the flowpath eye endpoint
  as an implicit universal blade-leading and hub-solid top plane.
- [ ] Add separate semantic witnesses for:
  - hub flowpath eye endpoint;
  - hub material eye/boss top;
  - mounting-bore material limits;
  - blade leading boundary.
- [ ] Build the supported hub material only from those named witnesses.
- [ ] Continue excluding unsupported spline-groove details and the deferred
  non-planar bottom boss from acceptance.
- [ ] Add a gate that detects an unexplained high population of unrelated
  surface boundaries on one common Z plane.
- [ ] Require the generated blade leading-boundary R-Z envelope to match source
  witnesses rather than the hub profile endpoint.

## Task 7: Truthful Source And Reconstruction Overlays

- [ ] Red overlay: canonical exact STEP section curves.
- [ ] Blue overlay: actual intersections of reconstructed surfaces with the
  same authoritative carriers.
- [ ] Never reuse source loops as reconstructed loops.
- [ ] Label every overlay with population, eta/H station, coordinate frame,
  curve role, and residual.
- [ ] Default to representative-blade overlays; allow station selection without
  duplicating all periodic instances.
- [ ] Preserve semitransparent Geometric Manifest shade plus UV lines for the
  reconstructed model.
- [ ] Keep source, reconstruction, and heatmap cameras in the same canonical
  world as established by R15.

Frontend tests:

- [ ] A translated source-frame loop cannot be rendered without a backend
  canonical transform.
- [ ] Toggling source and reconstructed loops produces geometrically distinct
  buffers and ids.
- [ ] Blue reconstructed loops lie on the rendered reconstructed surfaces.
- [ ] A missing generated intersection is shown as unavailable, not replaced by
  a source loop.

## Task 8: Staged Geometry And Deviation Gates

Run inexpensive conformance gates before full corresponding-surface deviation:

1. source section-to-B-Rep exactness;
2. carrier round-trip and endpoint witnesses;
3. generated section-to-source curve conformance;
4. shared boundary, orientation, and foldover checks;
5. regional sampled surface deviation;
6. full corresponding-surface heatmap.

- [ ] Abort before expensive edge closure/deviation when a curve-network gate
  fails.
- [ ] Cache exact STEP sections and compatible curve networks by source hash,
  frame hash, carrier hash, and algorithm revision.
- [ ] Invalidate R15 geometry and deviation checkpoints for R16.
- [ ] Continue calculating and displaying every supported reconstructed hub and
  blade face.
- [ ] Continue excluding spline-modified bore faces, unsupported auxiliary
  holes, and the deferred bottom boss with explicit provenance.
- [ ] Keep the heatmap colour bar in millimetres and report per-role median,
  P95, maximum, and triangle count.

## Task 9: Acceptance Tests

### Deterministic geometry gates

- [ ] No per-station physical streamwise interval is silently expanded to
  `[0, 1]`.
- [ ] No pressure/suction endpoint stagger is collapsed unless the source
  witness is itself coincident.
- [ ] No normal thickness is applied as a Q-only offset in direct mode.
- [ ] Every section and surface declares one coordinate frame and one geometry
  authority.
- [ ] No artificial common-Z cutoff is present across hub, pressure, suction,
  and root surfaces.

### KS007G23B gates

- [ ] Leading-region source-to-generated R-Z error falls from approximately
  `8.1 .. 9.1 mm` to no more than `0.25 mm` at authoritative section witnesses.
- [ ] Section-curve bidirectional Hausdorff distance is no more than
  `max(2 * source_tolerance_mm, 0.10 mm)`.
- [ ] Pressure and suction blade-side regional P95 is no more than `0.50 mm`.
- [ ] Leading-edge regional P95 is no more than `0.75 mm`, with unsupported
  source features excluded explicitly rather than hidden.
- [ ] Root and tip attachment errors are reported separately and may not be
  averaged into the blade-side result.
- [ ] Source and generated overlay residuals shown in the UI match backend
  witness calculations.

### Regression gates

- [ ] Historical V1.1 open and closed representative presets remain unchanged
  in scalar-field mode.
- [ ] Existing R15 canonical-axis, support-profile, hub-closure, status, camera,
  and heatmap tests remain passing.
- [ ] Rigid source transformations produce identical canonical reconstruction
  signatures.
- [ ] Main-only and main-plus-splitter synthetic sources retain independent
  section networks and periodic pattern provenance.
- [ ] Frontend tests and production build pass without white-screen or excessive
  buffer duplication regressions.

## Task 10: Performance Budget

- [ ] Record per-stage wall time, peak memory, cache hit/miss status, station
  count, curve count, and generated triangle count.
- [ ] Use adaptive station insertion rather than globally increasing all
  section and mesh resolutions.
- [ ] Reuse exact section curves when only visualization or deviation settings
  change.
- [ ] Reuse direct surface geometry when only heatmap region selection changes.
- [ ] Full R16 audit wall time may not exceed the frozen R15 baseline by more
  than 25% without a documented accuracy justification.
- [ ] UI polling and service restart must not invalidate completed section or
  surface checkpoints.

## Verification Commands

Iterate with narrow groups first, then run all applicable gates:

```powershell
python -m pytest tests/test_impeller_v11_6_section_recovery.py -q
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -q
python -m pytest tests/test_impeller_v11_6_adaptive_extension.py -q
python -m pytest tests/test_impeller_v11_6_v112_mapping.py -q
python -m pytest tests/test_impeller_v11_6_section_curve_surfaces.py -q
python -m pytest tests/test_impeller_v11_six_face_surface_family.py -q
python -m pytest tests/test_impeller_v11_6_deviation.py -q
python -m pytest tests/test_impeller_v11_6_step_audit.py tests/test_impeller_v11_6_axis_first_contract.py -q
python -m ruff check src/part_rule_synthesis tests
cd frontend
npm.cmd test
npm.cmd run build
```

The fresh KS audit must record audit id, source and canonical hashes, section
carrier definitions, curve-network hash, exact tolerance values, station count,
surface conformance metrics, per-role deviation, performance measurements, and
screenshots from matched top, meridional, leading-edge close-up, root close-up,
and overlay views.

## Documentation And Evidence

- [ ] Add an R16 semantic change log documenting the authority transition from
  scalar fields to direct section curves for STEP reconstruction.
- [ ] Add an insight log documenting why independently normalized section
  coordinates cannot preserve a three-dimensional blade family.
- [ ] Add a contract migration note explaining that historical presets remain
  scalar-field driven.
- [ ] Add a reproducible R15-versus-R16 evidence index with identical cameras
  and heatmap scales.
- [ ] Update `docs/version-history.md` only after fresh R16 tests and audit
  artifacts are verified.
- [ ] Keep all rejected R15 evidence identifiable as rejected; do not overwrite
  it with R16 artifacts.

## Review Checkpoints

Stop for review after each checkpoint before continuing:

1. canonical source loops and physical S witnesses overlay the STEP correctly;
2. `H_root(S)`/`H_tip(S)` carriers cover the real blade body;
3. one representative blade's direct PS/SS surfaces conform before periodic
   patterning;
4. LE/TE and root/tip topology close without artificial planes;
5. all 13 instances pattern correctly;
6. regional deviation and full heatmap pass their staged gates;
7. frontend overlays display source and generated evidence truthfully.

## Non-Goals

- Reconstructing spline grooves, auxiliary holes, or the deferred non-planar
  bottom boss.
- Claiming certified analytic B-Rep output from sampled review geometry.
- Replacing the scalar-field constructor used by historical presets.
- Hiding unsupported source faces or failed gates to improve aggregate metrics.
- Increasing mesh density as a substitute for correcting section coordinates
  and surface authority.
