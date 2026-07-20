# Impeller V1.1.6 R16.22 Verification Evidence

## Scope

This evidence verifies the R16 direct section-curve authority repair against the
`KS007G23B.stp` source. It covers:

- exact pressure/suction source-face carriers;
- semantic partition of root, tip, leading-edge, and trailing-edge faces;
- preservation of non-material sharp-seam placeholders;
- semantic-region deviation against the union of corresponding reconstruction
  patches;
- frontend loading and active-span section selection.

This remains review-grade reconstruction. Process completion is not geometry
promotion.

## Source And Run

- Branch: `fix/v1.1.6-r16-section-curve-authority`
- Baseline commit: `327e8c9 docs: plan v1.1.6 r16 section curve repair`
- Implementation revision: `axis_first_section_curve_authority_r16_22`
- Source SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`
- Audit id: `step-audit-7aedfbda8d2348f9`
- Audit directory:
  `runs/v116-r16-22-full-audit/step_reconstruction_audits/step-audit-7aedfbda8d2348f9`
- Started: `2026-07-19T10:49:01.783684+00:00`
- Finished: `2026-07-19T11:07:29.798950+00:00`
- Process status: `PASS / COMPLETE`
- Geometry and axis-first acceptance: `REJECTED`
- Disposition: `review_only_not_promotable`

The full audit was launched with:

```powershell
python tools/run_r16_audit.py `
  --root runs/v116-r16-22-full-audit `
  --source "C:\Users\CHEN Li\Documents\WeChat Files\wxid_r615kksejqyt22\FileStorage\File\2026-07\KS007G23B.stp"
```

## Authority Partition

The representative blade finite-face partition is mutually exclusive:

| Role | Authenticated source faces |
| --- | --- |
| Root | `source_face_00087`, `source_face_00091` |
| Leading edge | `source_face_00088` |
| Trailing edge | `source_face_00023`, `source_face_00024`, `source_face_00025`, `source_face_00228` |
| Tip | `source_face_00229` |

The previous contamination, where the leading-edge face entered the root set
and a trailing-edge face entered the tip set, is absent.

## Direct Surface Quality

- Pressure grid: `49 x 159`
- Suction grid: `49 x 154`
- Maximum station-incidence residual: `0.00046288253857712774 mm`
- Foldovers: `0`
- Normal flips: `0`
- Row reversals: `0`
- Span reversals: `0`
- Shared-edge maximum gap: `0 mm`
- Shared-edge orientation mismatches: `0`
- Direct surface quality: `PASS`

## Corresponding-Surface Deviation

Global reconstruction-to-source triangle-centroid metrics:

| Metric | Value |
| --- | ---: |
| Minimum | `0.000000 mm` |
| Median | `0.013598 mm` |
| P95 | `0.291107 mm` |
| RMS | `0.583822 mm` |
| Maximum | `6.517772 mm` |

Maximum P95 over the 13 periodic blade instances:

| Semantic region | Reconstruction to source | Source to reconstruction |
| --- | ---: | ---: |
| Blade sides | `0.050174 mm` | `0.037564 mm` |
| Leading edge | `0.007700 mm` | `0.007545 mm` |
| Trailing edge | `0.038333 mm` | `0.038895 mm` |
| Root attachment | `0.036091 mm` | `0.040563 mm` |
| Tip | `0.228824 mm` | `1.524034 mm` |

The surface ledger reports:

- `421` reconstruction surfaces;
- `420` evaluated material surfaces;
- `67` evaluated semantic comparison regions;
- `1` explicitly excluded non-material surface;
- `0` unresolved material surfaces;
- comparison scope:
  `semantic_source_region_to_union_of_all_corresponding_material_patches`.

## Verification Commands

```powershell
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py tests/test_impeller_v11_6_section_curve_surfaces.py tests/test_impeller_v11_6_pattern_reconstruction.py tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_step_audit.py -q
# 175 passed, 1 skipped in 307.66s

python -m pytest tests/test_impeller_v11_6_section_loops.py tests/test_impeller_v11_6_section_curve_authority.py tests/test_impeller_v11_6_section_overlay.py tests/test_impeller_v11_6_adaptive_extension.py tests/test_impeller_v11_6_v112_mapping.py tests/test_impeller_v11_6_axis_first_contract.py tests/test_impeller_v11_6_exact_support_authority.py tests/test_impeller_v11_six_face_surface_family.py -q
# 191 passed in 181.58s

python -m ruff check src/part_rule_synthesis/impeller_v11_6_axis_first_pipeline.py src/part_rule_synthesis/impeller_v11_6_section_curve_surfaces.py src/part_rule_synthesis/impeller_v11_6_pattern_reconstruction.py src/part_rule_synthesis/impeller_v11_6_step_audit.py tests/test_impeller_v11_6_axis_first_pipeline.py tests/test_impeller_v11_6_section_curve_surfaces.py tests/test_impeller_v11_6_pattern_reconstruction.py tests/test_impeller_v11_6_step_audit.py
# All checks passed

cd frontend
npm.cmd test
# 255 passed, 0 failed

npm.cmd run build
# frontend build check passed
```

The active-span frontend adapter was additionally regression tested after the
audit. Its nine authoritative stations display as `h 0.00`, `0.13`, `0.25`,
`0.38`, `0.50`, `0.63`, `0.75`, `0.88`, and `1.00`. Selecting `h 0.50`
binds `source:main:h_0.500000000` and 29 mapping evidence records.

## Artifacts

- `geometric-manifest.json`: `53,768,208` bytes
- `heatmap.json`: `96,697,510` bytes
- `manifest.json`: `118,720,645` bytes
- `reconstruction.stl`: `51,470,484` bytes
- `source.stl`: `51,017,434` bytes
- Browser overview:
  `docs/evidence/assets/r16-22/frontend-audit-overview.png`
- Browser `h 0.50` selection:
  `docs/evidence/assets/r16-22/frontend-audit-h050.png`
- Independent source/reconstruction render:
  `docs/evidence/assets/r16-22/source-reconstruction-overview.png`
- Representative six-face blade render:
  `docs/evidence/assets/r16-22/representative-blade-authority.png`

## Known Limits

- The legacy scalar camber, pose, normal-thickness, edge-curve, and periodicity
  gates still reject promotion. Exact source carrier agreement does not waive
  those contracts.
- Hub flowpath reconstruction-to-source P95 is `2.117922 mm`.
- Hub material closure remains the dominant unsupported mismatch:
  reconstruction-to-source P95 `4.864263 mm`, source-to-reconstruction P95
  `5.454027 mm`.
- The non-planar bottom boss, spline/keyway details, auxiliary holes, and spline
  bore remain outside the current V1.1.2 reconstruction vocabulary.
- The frontend audit camera uses conservative automatic framing; the independent
  VTK evidence renders are the higher-resolution geometry review artifacts.
