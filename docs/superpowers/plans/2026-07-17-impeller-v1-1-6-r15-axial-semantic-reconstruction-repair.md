# Impeller V1.1.6 R15 Axial-Semantic Reconstruction Repair

Date: 2026-07-17

Execution status: complete. The checklist below is the approved implementation
contract; measured outcomes are recorded in
`docs/evidence/2026-07-17-impeller-v1-1-6-r15-verification-evidence.md`.

## Objective

Eliminate the gross cylindrical reconstruction failure by making canonical-axis
polarity, support-profile endpoint roles, hub-solid closure, comparison-camera
framing, and audit acceptance status obey one explicit V1.1.2 axial semantic
contract.

R15 is a correctness repair. It does not change the V1.1.2 blade mathematics,
add unsupported STEP features, or relax measured residual gates.

## Confirmed Failure Chain

The completed R13.2 KS007G23B audit used a canonical frame in which the
large-radius backplate side was assigned to positive Z. The recovered hub
profile therefore ran from approximately `(R=12.5, Z=4.95)` to
`(R=51.38, Z=29.95)`, opposite the V1.1.2 constructor contract:

- profile start: small-radius eye at high Z;
- profile end: large-radius backplate at low Z.

The profile was copied into `hub_profile_rz_mm` without an endpoint-role gate.
The adaptive hub closure then placed the bottom below the minimum profile Z but
extended the outer wall to the high-Z large-radius endpoint. This created an
approximately 30.75 mm-high outer cylinder that occluded the blade surfaces.

The surface graph still contained the pressure, suction, leading, trailing,
root, and tip surfaces. The old result was process-complete but already marked
`axis_first_algorithm_status=REJECTED`, `promotable=false`.

## Release Boundary

- Runtime release remains `1.1.6`.
- Canonical geometry remains `1.1.2`.
- Audit implementation revision becomes
  `axis_first_triangle_surface_r15_3`.
- The authoritative source remains the uploaded STEP B-Rep transformed through
  one right-handed source-to-canonical matrix.
- R14 deviation checkpoints remain exact performance artifacts but are not
  reusable by R15 because canonical coordinates change.
- Spline grooves, three auxiliary holes, the non-planar source bottom boss, and
  other unsupported features remain explicitly excluded from reconstruction
  and corresponding-surface acceptance.

## Mandatory Precondition: Freeze R14

- [ ] Allow `step-audit-058a9e65e2d341d3` to finish without restarting the
  current backend.
- [ ] Record its elapsed time, per-surface progress, peak memory, checkpoint
  size, and final status in the R14 verification evidence.
- [ ] Retain its artifacts as performance evidence only; label its geometry as
  affected by the axial-semantic defect.
- [ ] Run the R14 verification commands already listed in the R14 plan.
- [ ] Commit R14 independently with a clean evidence boundary.
- [ ] Start R15 in a clean follow-on commit or worktree. Do not mix R15 geometry
  results into the R14 performance baseline.

## 1. Canonical Axis Polarity

### Contract

The rotation axis remains an undirected analytic line until polarity is
resolved. For a radial throughflow impeller, canonical positive Z must point
from the large-radius backplate toward the small-radius eye. Equivalently, the
radial-weighted axial moment must place the large-radius material on the
negative-Z side.

### Implementation

- [ ] Change axis-direction resolution in
  `impeller_v11_6_source_frame.py` to evaluate both axis signs and select the
  sign compatible with the V1.1.2 support-profile orientation.
- [ ] Record direction evidence as
  `small_radius_eye_positive_z_from_radial_weighted_axial_asymmetry`, including
  signed and absolute normalized moments.
- [ ] Preserve a right-handed, rigid, determinant `+1` transform. Reversing Z
  must also choose the corresponding transverse basis; reflections are
  forbidden.
- [ ] For sources with insufficient radial asymmetry, use authenticated support
  endpoint evidence. If neither sign has a unique semantic score, reject with
  `v116_axis_direction_semantics_ambiguous`; do not use a silent world-axis
  fallback for promotable reconstruction.
- [ ] Update frame-schema allowlists and cache validation for the new direction
  evidence.

### Tests

- [ ] First failing test: the KS-like radial fixture resolves to a frame where
  the eye is above the backplate in canonical Z.
- [ ] Rigidly rotated and translated copies produce identical canonical
  signatures and profiles.
- [ ] Opposite source world-axis orientation produces the same canonical frame.
- [ ] Symmetric/ambiguous fixtures fail with the stable ambiguity reason.
- [ ] Matrix orthonormality and determinant remain within `1e-12`.

## 2. Support-Profile Endpoint Authority

### Contract

Hub and tip/shroud profiles must carry named endpoint roles rather than relying
on list order, axial extrema, or radius extrema alone:

- `eye_inlet_small_radius`;
- `backplate_exit_large_radius`.

For radial presets and recovered radial sources:

- eye radius is smaller than backplate radius;
- eye Z is greater than backplate Z;
- hub and tip/shroud profiles use the same streamwise direction;
- profile sample order is monotone in semantic streamwise parameter, even when
  local R or Z is not strictly monotone.

### Implementation

- [ ] Extend recovered support evidence with endpoint ids, source face/edge
  provenance, canonical coordinates, and endpoint-role confidence.
- [ ] Validate endpoint roles before copying controls into V1.1.2 defaults.
- [ ] Add failure reasons:
  - `v116_support_profile_orientation_failed`;
  - `v116_support_profile_endpoint_role_missing`;
  - `v116_support_profile_streamwise_mismatch`.
- [ ] Reject before surface construction when any profile violates the
  contract. Do not reverse a profile silently inside the constructor.
- [ ] Include `canonical_axial_semantics` and endpoint records in the audit and
  Geometric Manifest provenance.

### Tests

- [ ] Reversed hub controls fail before reconstruction.
- [ ] Reversed tip controls fail before reconstruction.
- [ ] Hub and tip with opposite streamwise order fail.
- [ ] Valid curved and locally non-monotone NURBS profiles remain accepted when
  their named endpoint roles and parameter direction are correct.

## 3. Hub-Solid Closure Repair

### Contract

Hub closure must consume authenticated endpoint roles:

- top annulus at the eye endpoint;
- bottom annulus below the backplate endpoint by measured bottom thickness;
- outer cylindrical wall only from the backplate endpoint to that bottom
  annulus;
- mounting-bore wall from the eye-side material limit to the bottom annulus.

No closure face may span the complete meridional flowpath merely because an
endpoint was misclassified.

### Implementation

- [ ] Replace independent `min/max(R/Z)` closure selection in
  `impeller_v11_surface_family.py` with named endpoint records.
- [ ] Calculate `solid_bottom_z = backplate_z - hub_bottom_thickness_mm`.
- [ ] Add pre-export quality gates:
  - outer-wall axial height equals measured bottom thickness within tolerance;
  - outer-wall radius equals the backplate endpoint radius;
  - top annulus radius/Z equals the eye endpoint;
  - closure faces share their expected endpoint rings;
  - no hub closure point exceeds the semantic support-plus-bottom material
    domain.
- [ ] Fail with `v116_hub_closure_endpoint_semantics_failed` instead of emitting
  review geometry when these checks fail.
- [ ] Keep the unsupported source bottom boss excluded from acceptance; do not
  approximate it as a planar certified match.

### Tests

- [ ] Reproduce the old reversed profile and assert that construction fails
  instead of producing a 30 mm cylinder.
- [ ] For the valid KS-like profile, outer-wall height is the configured bottom
  thickness within `0.01 mm`.
- [ ] Hub closure ring gaps are below the existing surface-graph tolerance.
- [ ] Historical V1.1 open/closed presets retain their expected hub solids.

## 4. Reconstruction and Audit Status Contracts

- [ ] Bump the implementation revision to
  `axis_first_triangle_surface_r15_3`; invalidate R13/R14/R15.0/R15.1/R15.2 full-audit and
  deviation checkpoint reuse where canonical mesh fingerprints change.
- [ ] Separate process status from geometry disposition in API/UI payloads:
  - `process_status: COMPLETE|RUNNING|FAILED`;
  - `geometry_status: ACCEPTED|REJECTED|REVIEW_ONLY`;
  - `promotable: boolean`.
- [ ] A completed rejected audit remains inspectable, but the UI must never show
  a standalone green `PASS` that can be read as geometric acceptance.
- [ ] Persist the first rejecting gate and its measured evidence.
- [ ] Add a manifest invariant that every reconstructed material surface uses
  `canonical_axis_frame_xyz_mm` with the declared axial semantics.

## 5. Same-World Comparison Rendering

### Contract

Source, reconstruction, and heatmap panes are views of one canonical world, not
three independently framed objects.

### Implementation

- [ ] Continue serving source STL in canonical coordinates.
- [ ] Compute one comparison framing sphere from canonical source bounds and
  apply its center, scale, camera direction, near/far planes, and target to all
  three panes.
- [ ] Remove per-pane recentering and scale normalization from synchronized
  comparison cameras.
- [ ] Preserve interactive source-camera control while applying the same camera
  transform to reconstruction and heatmap.
- [ ] Display a persistent `GEOMETRY REJECTED - REVIEW ONLY` banner for rejected
  completed audits.
- [ ] Keep Geometric Manifest rendering as semitransparent shade plus UV
  iso-lines; triangle edges remain forbidden.

### Tests

- [ ] Deliberately translated reconstruction remains visibly translated rather
  than being auto-centered over the source.
- [ ] All pane cameras have the same world target and distance scale.
- [ ] Rejected audits render the rejection banner and do not show acceptance
  `PASS` styling.
- [ ] Browser screenshot verifies that a valid reconstruction shows blade
  surfaces rather than an occluding hub cylinder.

## 6. Heatmap and Surface Coverage

- [ ] Recompute all supported reconstructed hub and blade material surfaces in
  the corrected canonical frame.
- [ ] Include every reconstructed pressure, suction, leading, trailing, root,
  tip, and supported hub face in the surface ledger and heatmap.
- [ ] Continue excluding the spline-modified bore cylinder, unsupported holes,
  key/spline grooves, and non-reconstructed bottom-boss faces with explicit
  source-face provenance and exclusion reasons.
- [ ] Assert that every heatmap triangle references a supported reconstructed
  surface id and its corresponding source region.
- [ ] Preserve the millimetric color bar and exact corresponding-surface
  distance definition from R14.

## 7. KS007G23B End-to-End Acceptance

Run a fresh audit after R15 is loaded. Do not reuse the active R14 audit.

### Structural gates

- [ ] Canonical hub endpoint order is small-radius/high-Z to
  large-radius/low-Z.
- [ ] Hub outer-wall height is no greater than measured bottom thickness plus
  `0.05 mm`.
- [ ] No reconstructed surface creates an outer cylinder spanning the
  meridional flowpath.
- [ ] Expected main blade instance and six-face surface counts are present.
- [ ] Pressure/suction/edge/root/tip surfaces remain inside the declared
  hub-to-tip material domain.
- [ ] Source, reconstruction, and heatmap artifact bounds use the same
  canonical frame.

### Measurement gates

- [ ] Report per-role median, P95, and maximum deviation for hub and every blade
  face family.
- [ ] Compare against retained R13.2 values, but do not claim acceptance merely
  because aggregate P95 improves.
- [ ] Existing mapping residual gates for camber, pose, normal thickness, edge
  curves, periodicity, topology, and material domain remain unchanged.
- [ ] If those gates still fail, R15 is accepted only as a gross-geometry repair
  and the audit remains `REVIEW_ONLY`/`REJECTED`.

### Visual gates

- [ ] Review canonical top, meridional, oblique top, and underside views.
- [ ] Blades are visible as six-face surface families and are not hidden by an
  erroneous hub closure.
- [ ] Representative blue loop evidence lies on its corresponding blade after
  periodic phase alignment.
- [ ] Heatmap contains a labelled mm color bar and no unsupported bore/bottom
  features disguised as measured matches.

## 8. Verification Commands

Iterate with the narrowest groups, then run all applicable gates:

```powershell
python -m pytest tests/test_impeller_v11_6_source_frame.py -q
python -m pytest tests/test_impeller_v11_6_v112_mapping.py -q
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_6_axis_first_pipeline.py -q
python -m pytest tests/test_impeller_v11_6_step_audit.py tests/test_impeller_v11_6_axis_first_contract.py -q
python -m pytest tests/test_impeller_v11_6_deviation.py -q
python -m ruff check src/part_rule_synthesis tests
cd frontend
npm.cmd test
npm.cmd run build
```

The final evidence must record exact test counts, durations, Python/NumPy/OCCT
and browser versions, tolerance values, audit id, artifact hashes, checkpoint
reuse status, screenshots, and remaining rejection reasons.

## 9. Documentation and Evidence

- [ ] Add an R15 semantic change log describing the canonical-axis polarity and
  endpoint-role contract.
- [ ] Add an insight log documenting why radial-weighted geometric asymmetry is
  not sufficient without constructor semantics.
- [ ] Add verification evidence with R13.2/R14/R15 artifact comparisons.
- [ ] Update `docs/version-history.md` only after the fresh R15 audit and tests
  complete.
- [ ] Preserve old rejected artifacts; never relabel them as R15 output.

## Non-Goals

- Exact analytic CAD/B-Rep reconstruction or certification.
- New geometry for spline grooves, auxiliary holes, keyways, or bottom bosses.
- Relaxing V1.1.2 residual or topology gates to force a PASS.
- Replacing the five-/adaptive-station blade mathematics beyond fixes required
  to obey the existing canonical coordinate contract.
- Further deviation-performance optimization beyond the separately frozen R14
  work.
