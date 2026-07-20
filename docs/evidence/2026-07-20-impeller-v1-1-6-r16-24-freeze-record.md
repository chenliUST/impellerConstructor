# Impeller V1.1.6 R16.24 Freeze Record

Date: 2026-07-20

## Frozen Identity

- Runtime release: `1.1.6`.
- Canonical preset geometry: frozen V1.1.2 constructor contracts.
- STEP reconstruction implementation:
  `axis_first_attachment_patch_complex_r16_24`.
- Freeze tag: `impeller-v1.1.6-r16.24-review`.
- Maturity: `review-grade` STEP reconstruction and audit baseline.

The tag is immutable project history. Any later geometry, ontology, DSL,
mapping, tolerance or acceptance change must use a later version or an
explicitly named follow-on revision. The freeze does not turn sampled review
surfaces into certified B-Rep or manufacturing CAD.

## Accepted Scope

- Authenticated direct section curves and exact trimmed STEP side faces are the
  reconstruction authority when their provenance gates pass.
- Source and canonical coordinates, physical S-Q values, active-span fields,
  closure roles, source overlays and generated intersections remain distinct.
- Complementary hub STEP faces are recovered as one semantic support union only
  after adjacency, profile-conformance and per-population 360-degree coverage
  gates pass.
- Root, tip and closure patches retain authenticated trim-edge provenance.
  Internal partition edges cannot masquerade as STEP shared edges.
- Coordinate sewing, regular-edge G1/G2 evidence and endpoint-corner coupling
  are independent measured contracts.
- Dense graph inspection, pattern decoration and deviation preprocessing use
  bounded copy-on-write and indexed paths without weakening geometric
  tolerances.
- The frontend presents Source STEP, reconstruction, scoped heatmap and audit
  evidence without relabeling workflow completion as geometry acceptance.

## Representative Audit

Audit `step-audit-9141bbd5805f4c31` is the retained R16.24 full-model evidence:

- workflow: `PASS` / `COMPLETE`;
- direct geometry validation: `PASS`;
- comparison scope: `PASS`, complete semantic coverage;
- runtime: approximately 15 minutes 22 seconds;
- reconstructed surfaces: 1,215, including 1,214 material surfaces;
- material triangles: 617,360;
- symmetric review deviation: median `0.029927 mm`, P95 `3.049643 mm`,
  maximum `7.052013 mm`;
- final disposition: `REJECTED`, review-only, non-promotable.

The rejection is retained intentionally. Parameter mapping still fails camber,
pose, normal-thickness, edge-curve and periodicity terms. Measured sharp source
edges also remain explicitly non-G1/non-G2. Visual acceptance of the current
review result does not override those gates.

## Freeze Verification

Backend command:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_topology_graph.py tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_6_axis_first_contract.py tests/test_impeller_v11_6_axis_first_pipeline.py tests/test_impeller_v11_6_comparison_scope.py tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_loop_decomposition.py tests/test_impeller_v11_6_pattern_reconstruction.py tests/test_impeller_v11_6_section_loops.py tests/test_impeller_v11_6_step_audit.py tests/test_impeller_v11_6_section_curve_authority.py tests/test_impeller_v11_6_section_curve_surfaces.py tests/test_impeller_v11_6_section_overlay.py -q --durations=15
python -m compileall -q src
```

Result: `367 passed, 1 skipped` in `755.83 s`; compilation passed.

Frontend commands:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

Result: `255 passed`; production build check passed.

Repository checks:

```powershell
git diff --check
git status --short
```

The first complete legacy-suite attempt, `python -m pytest tests -q`, exceeded
the 1,204-second orchestration timeout and was terminated without a reported
test failure. It is not claimed as a passing gate; the version-specific suite
above is the authoritative freeze gate.

## Retained Boundaries

- Exact OCCT surface identity, analytic B-Rep sewing and certified metrology
  remain out of scope.
- Spline grooves, spline-modified bore, auxiliary holes, keyways and the source
  bottom boss are unsupported and excluded where documented.
- Final parametric mapping and continuity acceptance remain open.
- `hub_material_closure` remains the largest measured deviation-cost region.
- Customer STEP input and generated heavy audit artifacts remain external to
  source control; committed evidence contains only bounded text and selected
  review images.

## Forward Integration

V1.2 and later lines must preserve the R16 authority boundaries when merging:
physical S-Q coordinates cannot be replaced by normalized display parameters,
support unions cannot bypass coverage gates, and process completion cannot be
promoted into geometry acceptance. Conflicting geometry or ontology semantics
must be resolved explicitly rather than by copying the newer-looking file.
