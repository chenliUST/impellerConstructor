# Impeller V1.1.6 R8 Overhaul / R12 Verification Evidence

Date: 2026-07-16

## Scope And Authority

- Source authority: uploaded `KS007G23B.stp` B-Rep.
- Source SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`.
- Frozen base geometry contract: `1.1.2`.
- Reconstruction variant: `v1.1.6_adaptive_review_extension_r1`.
- Audit revision: `axis_first_triangle_surface_r12`.
- Comparison-scope contract:
  `impeller_v1_1_6_supported_surface_comparison_scope_v5`.
- Deviation contract:
  `impeller_v1_1_6_corresponding_surface_deviation_v4`.
- Runtime: Python 3.12.10, NumPy 2.4.6, CadQuery 2.8.0, and
  cadquery-ocp 7.9.3.1.1.
- Maturity: sampled review-grade reconstruction, not certified B-Rep
  reconstruction or exact CAD metrology.

## Uninterrupted Audit

The final synchronous R12 audit completed in `740.961 s`:

```text
runs/v116-r12-acceptance-20260716/
  step_reconstruction_audits/step-audit-7ba8024c586d41fc/
```

The local runtime directory is intentionally not committed. The compact
evidence below identifies the run and generated artifacts.

- Audit workflow status: `PASS`; all ten stages completed.
- Manifest SHA-256:
  `6fd0de6ccaed12ec7e1cfe4c1fc43c6d303e3d87201d9466c017ffd6e7bd2ced`.
- Runtime geometry validation: `PASS`.
- Runtime surface count: `84`; Geometric Manifest surface count: `83`.
- Adaptive source section count: `9`, main population only.
- Population evidence: `13 main`, `0 splitter`, exact authenticated instance
  membership and lattice indexes `0..12`.
- Mapping status: `REJECTED_REVIEW_CANDIDATE`.
- Failed mapping terms: camber, pose, normal thickness, edge curves, and
  periodicity.
- Algorithm status: `REJECTED`; acceptance status: `NOT_EVALUATED`.
- Promotable: `false`; disposition: `review_only_not_promotable`.

`PASS` certifies deterministic audit execution and artifact production only.
It does not override the rejected mapping candidate or promote the result.

## Comparison Scope And Alignment

- Source partition coverage: complete, `88` included faces and `152` explicit
  exclusions.
- Comparison coverage: `PARTIAL_REVIEW`, not complete.
- Partial reason: `unresolved_blade_closure_correspondence`.
- Unsupported keyway, auxiliary holes, nonplanar bottom/boss geometry, and
  unresolved closures do not contribute to distance metrics.
- Global periodic phase: `-10.625 deg`; pitch: `27.692307692 deg`.
- Alignment objective RMS: `4.470309 mm` before and `2.136841 mm` after the
  bounded phase search.
- Post-phase population assignment: independent cyclic assignment; main shift
  `1`, angular RMS `0.219238603919 rad`.
- Complete instance metrics contain 13 blade-side, 13 root-attachment, and 13
  open-tip regions. Partial LE/TE records remain explicit exclusions.

## Corresponding-Surface Metrics

| Direction | RMS | P95 | Maximum |
| --- | ---: | ---: | ---: |
| Reconstruction to corresponding source | 3.150443 mm | 7.090844 mm | 18.399589 mm |
| Corresponding source to reconstruction | 5.351178 mm | 10.726826 mm | 13.982433 mm |
| Symmetric fixed 0.5/0.5 directional aggregation | 4.390922 mm | 8.908835 mm | 16.191011 mm |

The symmetric row combines independently normalized directional statistics; it
does not concatenate unequal tessellation populations. The heatmap remains a
separate reconstruction-vertex-to-corresponding-source-triangle view. Its P95
color clip is display-only; stored errors remain unclipped. All distances are
unsigned point-to-triangle distances on retained tessellations, not exact
B-Rep closest-point measurements.

## Artifact Inventory

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `source.stl` | 9,620,534 B | `2410b5f297aa507b9d6b4822202101e7ec27a85e2a14bca1f5746276b6397b62` |
| `reconstruction.stl` | 6,044,884 B | `7c4c2b70f43ebe573d5f121f745da4a6fc6c21ff7d3d2a517af4528ea4e71268` |
| `heatmap.json` | 26,842,415 B | `22232438149f15436ac106fb20176cc0059503de062f210249949e5eef96c9ac` |
| `geometric-manifest.json` | 6,574,176 B | `8077f22d7a6ffa0051c4e2380798e090a84c2e8d3266ba713d983865fcec952a` |

The Geometric Manifest fidelity is
`sampled_review_grade_surface_graph_not_certified_brep`. It contains
translucent shade surfaces and actual surface UV curves for review.

## Verification Commands

```text
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -q
37 passed

python -m pytest tests/test_impeller_v11_6_comparison_scope.py tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_adaptive_extension.py tests/test_impeller_v11_6_meridional_mapping.py tests/test_impeller_v11_6_support_recovery.py tests/test_impeller_v11_6_attachment_measurement.py tests/test_impeller_v11_6_attachment_support_normals.py tests/test_impeller_v11_6_v112_mapping.py -q
143 passed

python -m pytest tests/test_impeller_v11_6_step_audit.py tests/test_impeller_v11_6_axis_first_contract.py tests/test_impeller_v11_6_step_api.py -q
92 passed, 1 skipped

python -m pytest tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py -q
33 passed

cd frontend
npm.cmd test -- --runInBand
247 passed

npm.cmd run build
frontend build check passed

python -m ruff check <changed V1.1.6 Python files and tests>
All checks passed

git diff --check
passed; only existing LF-to-CRLF working-copy warnings were emitted
```

The skipped backend case is the opt-in customer STEP test guarded by
`KS007G23B_STEP_PATH`. The uninterrupted audit above executes that source
through the complete workflow and is the retained real-source evidence.

Independent backend and frontend reviews were completed after R12 corrections.
The backend review verified exact population counts, membership, lattice
indexes, per-population LE/TE exclusions, phase assignment, and cache identity.
The frontend review verified abortable serial polling, stale STL cancellation,
fixed heatmap buffers, color conversion, and directional metric labels.

## Cache Replay

A repeated upload of the same source reused
`step-audit-7ba8024c586d41fc` in `1.23 s`. Reuse required the R12 revision,
audit-directory/status/manifest identity, source SHA-256, manifest digest, and
all four artifact hashes. Reuse retained `review_only_not_promotable` and did
not change mapping or acceptance status.
