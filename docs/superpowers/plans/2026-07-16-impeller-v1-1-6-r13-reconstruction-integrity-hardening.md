# Impeller V1.1.6 R13 Reconstruction Integrity Hardening Plan

**Status:** in progress; R13.2 geometry hardening under verification
**Target:** V1.1.6 adaptive STEP reconstruction review extension
**Canonical geometry authority:** frozen V1.1.2 contracts plus explicitly
versioned V1.1.6 source-derived review fields
**Reference audit:** `step-audit-7ba8024c586d41fc`
**Maturity boundary:** review-grade diagnostic reconstruction; not certified
CAD or B-Rep metrology

## Goal

Correct the geometry, comparison-scope, and rendering defects exposed by the
KS007G23B R12 review:

- leading/trailing edge targets must become construction authority rather than
  metadata-only measurements;
- root attachments must not collapse, fold, or leave the active blade span
  disconnected from the hub;
- hub comparison must cover the complete periodic passage ring or use an
  explicit angular mask;
- exact recovered NURBS profiles must remain authoritative through
  construction, meshing, inspection, and rendering;
- heatmaps and translucent review rendering must not make existing geometry
  appear deleted;
- the splined shaft interface, including the nominal mounting-bore cylinder,
  must be excluded from deviation acceptance until that feature family is
  modeled.

R13 remains within V1.1.6. It corrects the reverse-engineering and review path;
it does not start a new universal impeller geometry version.

## Execution Preconditions

- Inventory and checkpoint the existing R8-R12 worktree changes before R13
  implementation; do not reset or overwrite them.
- Keep legacy V1.1.2 preset and constructor outputs byte-compatible. New source-
  derived NURBS and attachment behavior is selected only by the versioned
  V1.1.6 adaptive reconstruction path.
- Use the uploaded STEP B-Rep as source authority and retain every extraction,
  fit, reduction, exclusion, and tessellation provenance record.
- Do not promote R12 workflow completion evidence into an R13 acceptance claim.

## Confirmed R12 Failure Evidence

- Mapping status is `REJECTED_REVIEW_CANDIDATE`; workflow completion `PASS` is
  not geometry acceptance.
- Leading-edge bidirectional Hausdorff residual reaches about `6.93 mm` because
  source cap targets are not consumed by the constructor.
- Periodic angular RMS is about `12.56 deg`, close to half of the `27.69 deg`
  pitch, so representative source loops do not overlay the reconstructed blade.
- Hub source classification selects 11 of 13 passage faces and omits two
  approximately opposed sectors.
- Root attachment samples are clamped to support endpoints; its smallest review
  triangle is about `4.16e-8 mm^2`, indicating near-collapse.
- The fitted cubic support NURBS is later evaluated as a control polygon. The
  resulting profile differs by as much as about `4.66 mm` and introduces tangent
  jumps.
- Heatmap geometry omits unresolved leading/trailing closures and several hub
  solid faces. Transparent manifest surfaces use `depthWrite: false`, allowing
  overlap ordering to resemble missing geometry.

## Contract Changes

### Comparison scope

R13 requires a face-complete comparison ledger. Every surface emitted by the
Geometric Manifest must have one and only one disposition:

- `EVALUATED`: authenticated source correspondence, per-face metrics, and
  heatmap triangles exist;
- `EXCLUDED_NOT_EVALUATED`: the surface belongs to an explicitly unsupported
  feature family and retains source ids and an exclusion reason;
- `FAILED_UNRESOLVED`: a surface should be supported by the current geometry
  rules but correspondence could not be established. This fails comparison
  completeness and keeps the audit non-promotable.

Supported deviation roles after R13 therefore include every face representable
by the current geometry rules:

- hub flowpath support;
- hub top/bottom annuli, shoulders, and outer material walls where the source
  domain corresponds to the current hub-solid rules;
- pressure and suction sides of every reconstructed blade instance;
- root-to-hub attachment;
- leading- and trailing-edge closures of every reconstructed blade instance;
- open tip surfaces or all supported closed-shroud attachment/material faces.

Source holes, spline cuts, bosses, or other excluded subdomains intersecting an
otherwise supported hub face are removed with explicit face-domain masks. The
remaining supported domain is still evaluated and reports its measured coverage
fraction. A whole face may not be dropped merely because one excluded feature
cuts it.

The following are explicitly excluded:

- spline grooves and the complete shaft-interface surface family;
- the nominal mounting-bore cylinder affected by the spline grooves;
- three auxiliary holes;
- unsupported nonplanar bottom and bottom boss geometry;
- balancing details and unresolved closure faces.

The shaft-interface reason code is
`v116_shaft_interface_spline_unsupported`. Its status is `NOT_EVALUATED`; it
must contribute no triangles, samples, minima, maxima, percentiles, or aggregate
weights to deviation results. It may still be rendered as neutral source or
review geometry with an explicit unsupported label.

Deviation data is stored and filterable per `surface_id`, not only per broad
family. Family and global summaries are derived from the complete per-surface
ledger. Missing eligible faces are comparison failures, never silently absent
heatmap regions.

### Geometry authority

- Recovered NURBS degree, knots, weights, and control points form one immutable
  authority record.
- Hub/tip revolve construction, blade span mapping, root support projection,
  tessellation, and inspection must evaluate that same record.
- Linear interpolation of NURBS controls is forbidden except for an explicitly
  labeled control-polygon drawing overlay.
- Review sampling density may change tessellation but may not change the
  geometry authority hash.

### Review rendering

- The complete reconstruction remains visible as a neutral base mesh.
- Heatmap color is an overlay only on evaluated triangles.
- Unsupported and unresolved regions remain visible in neutral gray and are
  labeled `NOT_EVALUATED`; they do not disappear.
- The Geometric Manifest uses a depth-correct shaded pass and a separate UV-line
  pass. Transparency must not be the only depth representation.

## Task 1: Freeze the R12 Reproduction and Add Failing Tests

- [x] Retain compact hashes and metrics from
  `step-audit-7ba8024c586d41fc`; do not commit the external STEP or full heatmap.
- [x] Add a fixture for 13 passage hub faces where two seam-adjacent faces have
  different areas.
- [x] Add a root fixture whose requested attachment width exits the valid
  `s` domain near both LE and TE.
- [x] Add edge fixtures proving metadata-only source caps do not alter current
  generated geometry.
- [x] Add frontend fixtures showing evaluated and excluded triangles together.
- [ ] Record all initial failures before implementation.

Primary tests:

- `tests/test_impeller_v11_6_comparison_scope.py`
- `tests/test_impeller_v11_6_support_recovery.py`
- `tests/test_impeller_v11_6_attachment_measurement.py`
- `tests/test_impeller_v11_root_attachment_surface.py`
- `frontend/src/components/StepComparisonScene.test.js`

## Task 2: Correct Comparison Scope and Shaft-Interface Exclusion

- [x] Build the face-complete comparison ledger directly from every Geometric
  Manifest `surface_id`.
- [x] Require explicit `EVALUATED`, `EXCLUDED_NOT_EVALUATED`, or
  `FAILED_UNRESOLVED` disposition for every reconstructed surface.
- [x] Generate per-face triangle membership, coverage, directional statistics,
  and heatmap records before aggregating by family.
- [x] Remove `mounting_bore` from the supported comparison contract.
- [ ] Classify bore cylinder, spline lands/flanks, and coupled shaft-interface
  faces into one excluded semantic family.
- [x] Preserve source face ids, exclusion reasons, units, and provenance.
- [x] Ensure excluded shaft-interface triangles are absent from the heatmap and
  all directional and aggregate deviation populations.
- [x] Report the shaft interface as `NOT_EVALUATED`, never zero-error or PASS.
- [x] Update the spec, known limitations, API contract tests, and report labels.

Required assertions:

- ledger surface count equals Geometric Manifest surface count;
- every current-rule hub and blade face has heatmap membership unless it carries
  an approved exclusion reason;
- one missing eligible blade or hub face fails comparison completeness;
- shaft-interface heatmap triangle count is zero;
- metric sample count is unchanged when excluded spline/bore tessellation is
  refined;
- source and reconstruction views still render the excluded geometry neutrally.

## Task 3: Recover Complete Hub Passage Ownership

- [x] Replace area-only completion with periodic angular-domain coverage.
- [x] Require one authenticated hub passage region for every expected periodic
  passage when the source contains a complete ring.
- [x] Include the two seam-adjacent KS007G23B hub faces currently omitted.
- [x] If coverage remains partial, emit exact angular masks and compare only
  within those masks.
- [x] Forbid a full 360-degree reconstructed hub from being compared with a
  partial source ring.
- [x] Separate `hub fit quality` from `hub source coverage quality` in the
  report.
- [ ] Establish source correspondence for hub top annulus, supported bottom
  annulus domains, shoulders, and outer walls in addition to the flowpath.
- [ ] Subtract auxiliary-hole, shaft-interface, and unsupported boss domains
  without discarding the remaining supported portion of the owning hub face.
- [x] Emit one heatmap region and one metric record per reconstructed hub
  surface id.

Acceptance:

- complete KS007G23B case reports `13/13` hub passage coverage;
- every supported hub-solid face has nonzero evaluated coverage and a visible
  heatmap; excluded subdomains remain neutral;
- no two opposed false-red sectors remain;
- partial fixtures remain `PARTIAL_REVIEW` with visible neutral unmeasured
  sectors.

## Task 4: Restore Exact NURBS Evaluation Authority

- [x] Introduce one structured NURBS evaluator for recovered meridional curves
  and adaptive scalar/vector fields.
- [x] Route hub and tip/shroud surfaces, span mapping, root support projection,
  and review tessellation through it.
- [x] Retain the control polygon only as drawing evidence.
- [x] Remove or quarantine `_sample_profile_rz` and `_profile_sample_rz`
  control-polyline interpolation from geometry construction.
- [ ] Emit the authority hash and evaluator revision in the Geometric Manifest.

Acceptance:

- generated support samples agree with direct NURBS evaluation within
  `1e-6 mm` at identical parameters;
- no control-point tangent discontinuity is introduced;
- review tessellation chordal error is at most `0.03 mm` after Task 8;
- changing display density leaves the authority hash unchanged.

## Task 5: Rebuild Root Attachment Without Domain Clamping

- [x] Remove hard clamping of offset footprint parameters to `s=0` or `s=1`.
- [x] Compute a feasible attachment-width field from local blade thickness,
  support curvature, available streamwise domain, and measured source width.
- [x] Taper attachment width smoothly near LE/TE where the full width is not
  feasible.
- [x] Trim the support footprint at real intersections instead of collapsing
  samples to endpoints.
- [ ] Construct dedicated LE-root and TE-root corner patches where required.
- [ ] Bind the elevated active-root blade loop, root inner boundary, and hub
  outer boundary as shared topology edges.
- [x] Reject foldover, repeated endpoint runs, material-side inversion, or
  unsupported extrapolation.

Acceptance:

- endpoint-collapse count is zero;
- foldover and orientation mismatch counts are zero;
- shared-edge coordinate gap is at most `0.03 mm`;
- root patch Jacobian sign is consistent;
- minimum-to-median cell-area ratio passes a bounded non-collapse gate;
- hub, root, and blade-side role-isolation renders contain no uncovered strip.

## Task 6: Make Source LE/TE Curves Construction Authority

- [ ] Re-identify PS/SS/LE/TE landmarks on every source section loop.
- [ ] Verify each edge target excludes neighboring PS/SS curve portions and is
  expressed in the correct local section frame.
- [ ] Fit degree-3 or higher NURBS edge curves at all adaptive span stations.
- [ ] Share endpoint position, tangent, and curvature constraints with PS/SS.
- [ ] Loft leading- and trailing-edge surfaces through the complete station
  family.
- [ ] Remove the generic thickness-ratio cap fallback from accepted adaptive
  reconstruction.
- [ ] Reject ambiguous edge ownership instead of silently generating a cap.
- [ ] Emit per-instance, per-surface LE and TE comparison regions after ownership
  is resolved; family-only edge summaries are insufficient.

Acceptance:

- no adaptive reconstruction reports a generated generic cap as a measured
  source edge;
- maximum edge bidirectional Hausdorff residual is at most `0.20 mm` or twice
  the retained source tessellation tolerance, whichever is larger;
- endpoint tangent and curvature gates pass at every station;
- thin-edge and high-curvature regression fixtures remain spike-free.

## Task 7: Correct Periodic Blade Identity and Loop Overlays

- [ ] Resolve source representative instance and reconstructed instance identity
  after global phase alignment, independently per population.
- [ ] Verify phase, cyclic shift, and source-loop frame exactly once.
- [ ] Draw source and reconstructed section loops as paired evidence with
  distinct colors and labels.
- [ ] When mapping is rejected, label loops `UNALIGNED REVIEW EVIDENCE` and do
  not present them as model geometry.

Acceptance:

- accepted periodic angular RMS is below `1 deg` and well below one-quarter
  pitch;
- source and reconstructed representative loops overlay the same blade;
- rejected mapping remains visibly rejected in the UI and report.

## Task 8: Improve Geometry Tessellation and Display Fidelity

This task starts only after Tasks 4-7 pass. Increasing samples must not hide
incorrect geometry.

- [ ] Tessellate NURBS surfaces adaptively by chordal error and normal-angle
  error.
- [ ] Use denser review defaults for support, blade side, edge, root, and tip
  surfaces without changing authority.
- [ ] Reduce source STEP display tessellation tolerance and record the chosen
  values in the manifest.
- [ ] Add geometry-versus-display diagnostics reporting chordal and normal-angle
  maxima.
- [ ] Keep export, comparison, UV inspection, and shade derived from the same
  surface authority.

Initial review targets:

- support: at least `129 x 181` samples when adaptive refinement does not demand
  more;
- blade sides: at least `33 x 129`;
- edge surfaces: at least `33 x 65`;
- root attachment: at least `17 x 257`, subject to the non-collapse gate;
- source display: chordal tolerance at most `0.03 mm`, angular tolerance at most
  `0.04 rad`.

These are review-density defaults, not universal geometry parameters.

## Task 9: Make Heatmap and Manifest Rendering Truthful

- [x] Render a complete neutral reconstruction base in the heatmap pane.
- [x] Overlay evaluated heatmap triangles without removing unsupported roles.
- [x] Provide filters for individual surface ids as well as hub/blade role
  families and global coverage.
- [ ] Show excluded regions in gray with a `NOT_EVALUATED` legend entry.
- [x] Add an opaque depth pre-pass or equivalent depth-correct manifest shading.
- [x] Draw translucent shade and UV lines in separate passes.
- [ ] Add role-isolation controls for hub, blade sides, edges, root, and tip.
- [ ] Add a topology-gap overlay for shared-edge gaps, foldovers, and degenerate
  cells.
- [ ] Ensure camera rotation does not change whether a surface appears present.

Frontend screenshot gates:

- complete hub remains visible in global and filtered heatmap views;
- every eligible hub, pressure, suction, LE, TE, root, and tip/shroud surface can
  be selected individually and displays its own error field;
- unsupported bore/spline area is gray, not colored and not missing;
- LE/TE remain visible even when their deviation status is `NOT_EVALUATED`;
- opaque role-isolation views show no false transparency holes;
- UV lines remain attached to their owning surface.

## Task 10: API, Status, and Evidence Semantics

- [x] Version the comparison and heatmap contracts for the R13 scope change.
- [x] Separate workflow status, mapping status, comparison-scope status, and
  acceptance status in API and UI.
- [x] Prevent a prominent workflow `PASS` from obscuring mapping `REJECTED`.
- [x] Include per-role `evaluated`, `excluded`, and `unresolved` triangle/sample
  counts.
- [x] Include a per-surface coverage table whose rows reconcile exactly with the
  Geometric Manifest surface list.
- [x] Record all tolerances, authority hashes, source face ids, angular masks,
  and exclusion reasons.
- [x] Update semantic change log, insight log, known limitations, version history,
  and compact verification evidence only after tests pass.

## Verification Matrix

Backend iteration suites:

```powershell
python -m pytest tests/test_impeller_v11_6_comparison_scope.py -q
python -m pytest tests/test_impeller_v11_6_support_recovery.py tests/test_impeller_v11_6_meridional_mapping.py -q
python -m pytest tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_6_attachment_measurement.py -q
python -m pytest tests/test_impeller_v11_6_section_recovery.py tests/test_impeller_v11_6_v112_mapping.py -q
python -m pytest tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_step_audit.py -q
python -m pytest tests/test_impeller_v11_6_step_api.py -q
```

Frontend gates:

```powershell
cd frontend
npm.cmd test -- --runInBand
npm.cmd run build
```

End-to-end gate:

- Run one fresh, uninterrupted KS007G23B audit with a new algorithm revision.
- Verify artifact hashes and bind status to that exact audit and source SHA.
- Capture source, neutral reconstruction, Geometric Manifest, global heatmap,
  role-isolation, and report screenshots.
- Record directional and per-role metrics without comparing them numerically to
  the obsolete global nearest-mesh baseline.
- Preserve a rejected result as rejected if any mapping or topology gate fails.

## Promotion Gate

R13 is complete only when all of the following are true:

- exact NURBS authority is consumed end to end;
- KS007G23B hub coverage is `13/13` or explicitly masked as partial;
- every surface supported by the current geometry rules is individually
  evaluated and visible in the heatmap; no eligible surface is silently omitted;
- root endpoint collapse, foldover, and shared-edge gap gates pass;
- measured LE/TE curves construct the actual closure surfaces;
- periodic representative loops align to the correct blade;
- spline-affected shaft interface and mounting bore are `NOT_EVALUATED` and
  contribute no deviation samples;
- full neutral geometry remains visible under every heatmap filter;
- geometry defects and transparency artifacts are distinguishable in role
  isolation views;
- backend tests, frontend tests, production build, and a fresh audit pass their
  declared gates;
- the worktree state and remaining unrelated changes are explicitly inventoried.

Failure of any gate keeps the result `review_only_not_promotable`.
