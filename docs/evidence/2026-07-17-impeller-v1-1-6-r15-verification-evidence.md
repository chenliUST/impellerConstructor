# Impeller V1.1.6 R15 Verification Evidence

Date: 2026-07-17

## Environment

- Python: 3.12.10
- NumPy: 2.4.6
- SciPy: 1.18.0
- CadQuery: 2.8.0
- OCP/OCCT binding: 7.9.3.1
- Browser: Microsoft Edge WebView2 150.0.4078.65
- Canonical geometry: V1.1.2
- Audit implementation: `axis_first_triangle_surface_r15_3`

## Focused Verification

```text
python -m pytest tests/test_impeller_v11_6_source_frame.py \
  tests/test_impeller_v11_6_v112_mapping.py -q
83 passed in 136.92 s

python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py \
  tests/test_impeller_v11_6_exact_support_authority.py \
  tests/test_impeller_v11_six_face_surface_family.py -q
59 passed in 517.60 s

python -m pytest tests/test_impeller_v11_6_step_audit.py \
  tests/test_impeller_v11_6_axis_first_contract.py \
  tests/test_impeller_v11_6_step_api.py -q
108 passed, 1 skipped in 57.62 s

python -m pytest tests/test_impeller_v11_6_deviation.py \
  tests/test_impeller_v11_6_comparison_scope.py \
  tests/test_impeller_v11_6_regional_deviation.py -q
62 passed in 1.59 s

python -m pytest tests/test_impeller_v11_6_periodic_blades.py \
  tests/test_impeller_v11_6_support_recovery.py -q
55 passed in 11.09 s
```

The representative exact STEP mapping regression passes in 273.06 seconds. It
asserts the endpoint-correct canonical frame, exact section provenance, root
lift, and the unchanged review-only residual rejection.

## Frontend and Static Gates

```text
python -m ruff check <R15 changed Python modules and tests>
All checks passed

cd frontend
npm.cmd test
253 passed in 4.87 s

npm.cmd run build
frontend build check passed
```

The repository-wide Ruff command reports 180 historical findings in unchanged
legacy modules and tests. R15 does not mix that pre-existing cleanup into this
geometry repair; every Python file touched by R15 passes Ruff.

## Structural Evidence

- Canonical polarity on the conical radial fixture resolves to source direction
  `[0, 0, -1]`, origin `[0, 0, 34]`, and determinant `+1`.
- The canonical support order is small-radius/high-Z eye to
  large-radius/low-Z backplate.
- Reversed hub, reversed tip, opposite streamwise order, and missing endpoint
  roles fail before reconstruction with stable reasons.
- A valid adaptive hub closure reports a 0.5 mm outer-wall axial height for a
  0.5 mm configured bottom thickness. Reversed endpoint semantics fail instead
  of producing a flowpath-height cylinder.
- Comparison-scope tests require each supported hub closure and blade
  pressure/suction/leading/trailing/root/tip surface to have an explicit ledger
  disposition. Spline-modified bore and unsupported source features remain
  explicitly not evaluated.
- Camera tests deliberately translate reconstruction and heatmap bounds and
  confirm that all panes retain the source canonical camera rather than
  recentering independently.
- Completed rejected manifests show `process_status=COMPLETE`,
  `geometry_status=REJECTED`, and a persistent review-only banner.

## Fresh KS007G23B Audit

- Current audit id: `step-audit-e27b4c0e7c854c88`
- Diagnostic rejected audits:
  `step-audit-e739d4c66a084dce` (R15.0 periodic sampling),
  `step-audit-3b709d9b09b04b68` (R15.1 mixed full-component medoid), and
  `step-audit-fd94bd26f7134e0a` (R15.2 material terminal polarity).
- Source SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`
- Source bytes: 5,583,108
- Checkpoint reuse: none from R14; canonical revision changed.
- Created: `2026-07-17T17:07:45.979705+00:00`.
- Finished: `2026-07-17T18:36:21.768849+00:00`.
- Wall time: approximately 5,315.8 seconds (88 minutes 36 seconds).
- Process status: `COMPLETE` (`status=PASS`).
- Geometry and axis-first algorithm status: `REJECTED`.
- Disposition: review-only, non-promotable.
- Exact corresponding-surface progress: `82/82`; no R14 checkpoint hit.
- Reconstructed Geometric Manifest surface count: `82` (13 six-face blades
  and four supported hub material surfaces).

Measured stage durations were 19.211 s for B-Rep load, 45.147 s for frame
resolution, 9.001 s for semantic classification, 366.242 s for parameter
extraction, 171.781 s for hub reconstruction, 175.610 s for blade surfaces,
160.381 s for edge closures, and 4,213.427 s for deviation and artifacts.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `geometric-manifest.json` | 40,166,086 | `5bc1047461abde45f77b98e6fa525115c65bc76b67310ce54f615c564ae937ef` |
| `heatmap.json` | 201,858,958 | `e6d949ce63356649da9bb8c48987153884421efab464cfe208fdf6dacdf4aad7` |
| `reconstruction.stl` | 39,219,284 | `ab7134479e708ff3596dacb2ce3c81e10c3100c853b71bcbfc69950000c41cc2` |
| `source.stl` | 51,017,434 | `8e099d36795fe7b5037072223699a55210def3990513391cf3a173878e46d8aa` |

The authenticated backplate endpoint is at canonical Z 6.550002 mm. The hub
outer closure spans Z 0.800002 to 6.550002 mm at radius 51.376731 mm: exactly
the measured 5.75 mm bottom thickness, rather than the approximately 30 mm
meridional-flowpath cylinder produced by the reversed R14 endpoint semantics.

### Exact deviation

| Direction | Revision | Median mm | P95 mm | Maximum mm |
| --- | --- | ---: | ---: | ---: |
| reconstruction to source | R14 | 0.880663 | 10.802197 | 31.593204 |
| reconstruction to source | R15.3 | 0.861267 | 7.238329 | 19.001629 |
| source to reconstruction | R14 | 4.875178 | 46.662457 | 47.153285 |
| source to reconstruction | R15.3 | 5.375357 | 53.430378 | 55.444529 |
| symmetric fixed-weight | R14 | 2.877921 | 28.732327 | 39.373244 |
| symmetric fixed-weight | R15.3 | 3.118312 | 30.334353 | 37.223079 |

R15 repairs the gross closure geometry but does not claim an aggregate
metrology improvement: the forward distribution improves while the reverse
and symmetric distributions remain poor. This is consistent with a corrected
constructor domain whose current V1.1.2 blade and source-region mapping still
fails measured residual gates.

The heatmap direction is reconstruction to corresponding source. Blade-family
rows below report the minimum-to-maximum range across the 13 instances; hub
rows are individual surfaces.

| Surface family | Median mm | P95 mm | Maximum mm |
| --- | ---: | ---: | ---: |
| pressure | 0.608455-0.623587 | 4.738321-4.749121 | 7.401820-7.435295 |
| suction | 0.452971-0.463127 | 4.173169-4.191127 | 7.015369-7.066430 |
| leading edge | 9.840070-9.840164 | 18.188705-18.188801 | 19.001534-19.001629 |
| trailing edge | 1.095093 | 1.994882-1.994883 | 2.190850-2.190851 |
| root attachment | 0.514253-0.514435 | 1.862555-1.863025 | 2.850189-2.851881 |
| open tip dome | 1.839834-1.840707 | 6.790646-6.793644 | 7.673004-7.677501 |
| hub support | 0.049088 | 2.115175 | 6.929995 |
| hub top annulus | 2.475746 | 3.736230 | 4.056849 |
| hub bottom annulus | 3.412804 | 5.077767 | 5.363580 |
| hub bottom outer wall | 2.087202 | 4.656028 | 4.895515 |

The leading-edge family is the dominant remaining representation error. The
mapping rejects `camber`, `pose`, `normal_thickness`, `edge_curves`, and
`periodicity`; support, root/tip offsets, and attachment terms pass. Exact
B-Rep collision remains unmeasured (`UNKNOWN`), so periodic topology cannot be
promoted even though sampled collision checks pass.

### Visual evidence

Screenshot:
`docs/evidence/assets/v1.1.6-r15-axial-semantic-repair/ks007g23b-r15-audit.png`.

- Source, reconstruction, and heatmap rotate synchronously in one canonical
  world; no pane independently recenters the geometry.
- The reconstruction visibly contains all 13 blades and no longer presents as
  an occluding hub cylinder.
- The reconstruction uses translucent Geometric Manifest shade, UV iso-lines,
  and semantic boundaries; triangle-edge wireframe is not used.
- The heatmap contains a labelled millimetric color bar. The displayed P95
  color maximum is 7.234 mm and values up to 19.199 mm are explicitly clipped.
- The UI keeps the completed result inspectable while displaying
  `GEOMETRY REJECTED - REVIEW ONLY`; process completion is not styled as
  geometry acceptance.

R14 audit `step-audit-058a9e65e2d341d3` remains performance evidence and is
not relabeled as R15 output.
