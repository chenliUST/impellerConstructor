# Impeller V1.1.6 R13 Verification Evidence

Date: 2026-07-17

## Retained Full Audit: R13.1

The latest uninterrupted complete workflow is retained locally at:

```text
runs/v116-r13-1-bounded-acceptance-20260717/
  step_reconstruction_audits/step-audit-ea69ab6203724a27/
```

- Source SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`.
- Implementation revision: `axis_first_triangle_surface_r13_1`.
- Workflow status: `PASS`; algorithm status: `REJECTED`.
- Disposition: `review_only_not_promotable`; acceptance: `NOT_EVALUATED`.
- Reconstructed material surfaces: `83`.
- Ledger: `82 EVALUATED`, `1 EXCLUDED_NOT_EVALUATED`, `0 unresolved`.
- The excluded surface is `mounting_bore_inner_wall_surface` with reason
  `v116_shaft_interface_spline_unsupported`.
- All 82 evaluated surface ids have nonzero heatmap triangle membership. The
  excluded bore has zero heatmap triangles.
- Heatmap coverage includes 13 each of pressure, suction, LE, TE, root, and
  open-tip surfaces, plus hub support and three review-only hub closure faces.
- Reconstruction-to-source RMS is about `5.243 mm`; P95 is about `12.633 mm`.
  These poor values are retained as rejected diagnostic evidence.

R13.1 used the previous root mapping and old v4/v1 artifact contracts. It is not
evidence that R13.2 geometry or contracts passed a complete audit.

## R13.2 Geometry Probe

The R13.2 geometry-only probe consumes the exact R13.1 parameter mapping and
source SHA, applies the current dense review sampling, and constructs the
surface graph without running the expensive deviation stage:

```text
runs/v116-r13-2b-geometry-probe-20260717/geometry-probe-summary.json
```

The complete 84-surface probe after metric support-boundary intersection and
cap arc-length reparameterization reports:

- surface graph `PASS` with `84` surfaces;
- all `13` root surfaces report quality `PASS`;
- all roots use endpoint policy `metric_support_boundary_intersection`;
- two cap segments per root are arc-length reparameterized;
- every root reports `foldover_count = 0`;
- the complete graph has zero triangle below `1e-8 mm^2`;
- global minimum triangle area is `1.1699487675918494e-6 mm^2`.

The probe is geometry-only. A fresh R13.2 full deviation audit remains a
verification gate, and no R13.1 numeric deviation is relabeled as R13.2.

## Verification Commands

Completed during R13.2 iteration:

```text
python -m pytest tests/test_impeller_v11_6_adaptive_extension.py -q
16 passed

python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -q \
  -k "hub_passage_patch_family or hub_shared_support or hub_singleton_area_groups"
3 passed

python -m pytest tests/test_impeller_v11_root_attachment_surface.py -q
11 passed

python -m pytest tests/test_impeller_v11_6_comparison_scope.py -q
13 passed

python -m pytest tests/test_impeller_v11_6_deviation.py \
  tests/test_impeller_v11_6_comparison_scope.py \
  tests/test_impeller_v11_6_axis_first_contract.py -q
68 passed
```

Additional backend, frontend, build, and source-bound audit gates are recorded
below after completion in the current worktree.

```text
python -m pytest tests/test_impeller_v11_6_step_audit.py \
  tests/test_impeller_v11_6_step_api.py -q
46 passed, 1 skipped

python -m pytest tests/test_impeller_v11_root_attachment_surface.py \
  tests/test_impeller_v11_6_attachment_measurement.py -q
25 passed

python -m pytest tests/test_impeller_v11_6_adaptive_extension.py \
  tests/test_impeller_v11_6_exact_support_authority.py \
  tests/test_impeller_v11_6_meridional_mapping.py -q
28 passed

python -m pytest tests/test_impeller_v11_6_deviation.py \
  tests/test_impeller_v11_6_comparison_scope.py \
  tests/test_impeller_v11_6_axis_first_contract.py -q
68 passed

python -m pytest tests/test_impeller_v11_6_support_recovery.py \
  tests/test_impeller_v11_6_section_loops.py \
  tests/test_impeller_v11_6_v112_mapping.py -q
104 passed

python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -q
41 passed

python -m pytest tests/test_impeller_v11_2_active_span_policy.py -q
7 passed

python -m pytest tests/test_impeller_v11_six_face_surface_family.py \
  tests/test_impeller_v11_mesh_and_export_contract.py -q
20 passed
```

The disjoint backend matrix totals `339 passed, 1 skipped`.

```text
cd frontend
npm.cmd test -- --runInBand
251 passed

npm.cmd run build
frontend build check passed

python -m ruff check <changed R13 Python modules and tests>
All checks passed

git diff --check
PASS (line-ending conversion warnings only)
```

The adaptive reconstruction path keeps the measured minimum-thickness field
adjustable. Only the frozen V1.1.2 compatibility metric is restored to its
historical value; no R13 adaptive minimum is hard-coded.

The mocked WebGL contracts were supplemented with a real-browser replay of the
retained R13.1 audit using the current R13.2 frontend:

- desktop viewport `1440 x 900`: source, reconstruction, and heatmap canvases
  all rendered nonblank at `720 x 338` CSS pixels with nonzero per-channel
  variation; the report showed workflow `PASS`, algorithm `REJECTED`, and
  `NOT PROMOTABLE` as separate states;
- narrow viewport `390 x 844`: all three canvases stack at `390 x 300`, the
  report follows below them, document width remains `390`, and no alert or
  white-screen state is present;
- responsive CSS no longer forces a hidden `900px` comparison workspace; the
  full narrow layout is vertically scrollable;
- the replay remains R13.1 numeric evidence. It validates the current viewer
  contract but does not replace a fresh R13.2 deviation audit.

## Remaining Non-Promotion Gates

- Source pressure and suction sides still compare against a shared
  per-instance material-boundary union rather than unique authenticated faces.
- Source LE/TE records remain synthetic measurement closures unless an
  independently authenticated degree-3-or-higher curve is recovered.
- Review-only hub material closures still use a broad component union; exact
  local masks for holes, spline cuts, bottom and boss features are incomplete.
- Dense fixed review sampling passes the current graph but is not yet the
  planned chordal-error/normal-angle adaptive tessellator.
- A fresh uninterrupted R13.2 full STEP deviation audit has not been run.
