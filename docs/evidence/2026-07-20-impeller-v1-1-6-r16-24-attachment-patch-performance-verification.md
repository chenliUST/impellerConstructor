# Impeller V1.1.6 R16.24 Attachment Patch And Performance Verification

Date: 2026-07-20

## Scope

R16.24 keeps runtime V1.1.6 and canonical geometry V1.1.2. It hardens the
review-grade STEP reconstruction path in four bounded areas:

- authenticated trim-edge provenance for fallback patch partitions;
- independent regular-edge and endpoint-corner continuity evidence;
- indexed shared-edge topology construction without exhaustive pair scans;
- bounded-memory inspection and pattern decoration for dense sampled graphs.

This evidence does not promote sampled surfaces to certified B-Rep and does
not add unsupported spline, auxiliary-hole, keyway, bore-spline, or bottom-boss
semantics.

## Exact STEP Patch Evidence

Selected authenticated STEP faces were sampled directly from
`KS007G23B.stp` before the full audit:

| Source face | Trim paths | Path sample counts | Patch count | Partition | Pcurve bound (mm) | Total boundary bound (mm) |
| --- | ---: | --- | ---: | --- | ---: | ---: |
| `source_face_00063` | 3 | 17, 35, 33 | 64 | polygon fallback | 0.0096656530 | 0.0439048850 |
| `source_face_00069` | 6 | 17, 17, 61, 17, 40, 17 | 4 | radial | 0.0097459209 | below 0.05 |
| `source_face_00087` | 6 | 17, 17, 61, 17, 40, 17 | 4 | radial | 0.0097459209 | below 0.05 |
| `source_face_00129` | 3 | 17, 35, 33 | 64 | polygon fallback | bounded | below 0.05 |
| `source_face_00229` | 3 | 17, 35, 33 | 64 | polygon fallback | bounded | below 0.05 |

Polygon-fallback subpatches now retain a source edge id only when their edge
lies on the actual simplified STEP trim path. Ear-clip diagonals and center
spokes are explicitly classified as `internal_patch_edge`.

## Continuity Contract

The attachment topology contract now reports regular shared-edge continuity
separately from endpoint corner coupling:

- `regular_edge_continuity_status`;
- `corner_g1_measurement_status`;
- `corner_g2_measurement_status`;
- `corner_coupling_status`;
- `max_endpoint_corner_curvature_proxy_mismatch`.

Overall continuity passes only when both the regular-edge and corner contracts
pass. A 90-degree endpoint witness therefore cannot be hidden by a passing
interior shared edge.

## Performance Changes

1. The generic V1.0 topology graph uses an endpoint spatial index before the
   unchanged full-sample `1e-9 mm` match gate. A 1000-edge disjoint fixture
   produces zero exact edge comparisons.
2. Attachment topology candidates are grouped by blade class and periodic
   instance before source identity and geometric gap checks.
3. Exact trimmed patch materialization reuses rigid-transform-invariant quality
   evidence and does not clone stale source `uv_grid`, edge samples, or quality
   payloads into every periodic instance.
4. Direct replacement uses copy-on-write surface records; unmodified dense
   geometry arrays are read-only shared.
5. Parameter-inspection generation ids preserve the legacy digest byte
   semantics while using shallow surface records and streaming JSON hashing.
6. Pattern/material decoration uses copy-on-write surface records and validates
   a mapped V1.1.2 graph once instead of twice.
7. Environment-gated timing output tolerates a detached stdout pipe and cannot
   abort reconstruction.

## Optimization Baseline

The pre-optimization R14 diagnostic audit
`step-audit-16eaaab2946f43a2` provided these timings:

| Stage | Time |
| --- | ---: |
| copy-on-write graph setup | 0.000386 s |
| exact representative patch templates (93 surfaces) | 10.367239 s |
| materialize 13 periodic instances | 91.838348 s |
| attachment topology | 1.309156 s |
| legacy topology graph | 0.176513 s |
| parameter inspection and generation id | 302.916578 s |
| direct replacement total | 396.351932 s |

R14 was stopped after more than 31 minutes with no audit-stage advance and a
private working set near 15 GB. It is recorded as
`v116_audit_interrupted`, not as passing evidence. The two whole-graph copy
hotspots identified by this run were removed before the optimized audit.

## Optimized Full Audit

Audit: `step-audit-9141bbd5805f4c31`

The audit reached a terminal state in approximately 15 minutes 22 seconds.

| Contract | Result |
| --- | --- |
| process status | `PASS` / `COMPLETE` |
| direct geometry validation | `PASS` |
| comparison scope | `PASS`, complete coverage |
| material surface meshes | 1,214 |
| material triangles | 617,360 |
| reconstructed surface count | 1,215 |
| final geometry disposition | `REJECTED`, review-only, not promotable |

The final rejection is intentional. Parameter mapping still fails camber,
pose, normal-thickness, edge-curve, and periodicity terms, and no approved
corresponding-surface baseline exists. Process completion is not presented as
geometry acceptance.

### Full-audit timings

| Stage | Time |
| --- | ---: |
| B-Rep load | 16.429693 s |
| frame resolution | 38.819282 s |
| semantic classification | 8.900056 s |
| parameter extraction | 99.664654 s |
| initial V1.1.2 full graph | 90.615201 s |
| R16.24 direct replacement | 195.426144 s |
| independent direct geometry validation | 92.993340 s |
| periodic/material validation | 101.930805 s |
| review STL write | 4.539256 s |
| comparison preprocessing | 50.896277 s |
| corresponding-surface deviation | 199.951488 s |

The optimized parameter-inspection generation step took 93.743427 seconds,
down from 302.916578 seconds. Direct replacement took 195.426144 seconds,
down from 396.351932 seconds. Sampled process observation during the run
showed approximately 7.9 GB private memory rather than the R14 peak near
15 GB. The Windows in-process stage field reported zero and is not used as
memory acceptance evidence.

### Topology and continuity evidence

- 2,029,105 exhaustive attachment pairs were reduced to 14,950 geometric
  candidates across 13 semantic groups.
- 312 source-identity shared edges were matched.
- Maximum coordinate gap was `0.0001905804 mm`.
- Orientation mismatch count was zero.
- Regular-edge and corner continuity both measured `FAIL`, while topological
  attachment status measured `PASS`.
- Maximum normal angles were `89.230357 deg` on edge interiors and
  `89.706184 deg` at endpoints.

These failures are retained as measured source/reconstruction properties. For
example, the authenticated pressure-to-tip source edge is position-coincident
but approximately orthogonal. R16.24 does not relabel such a source edge G1 or
G2 merely because its coordinates sew.

### Deviation evidence

- Semantic triangle coverage: 1.0.
- Distance queries: 89, compared with legacy count 201.
- Periodic normalized reuse: 45 of 65 requested aliases.
- Periodic reuse rejections: 15; rejected aliases were computed directly.
- Reconstruction to corresponding source: median `0.020858 mm`,
  P95 `1.611107 mm`, maximum `5.363580 mm`.
- Corresponding source to reconstruction: median `0.038996 mm`,
  P95 `4.488178 mm`, maximum `8.740445 mm`.
- Symmetric review distribution: median `0.029927 mm`,
  P95 `3.049643 mm`, maximum `7.052013 mm`.

The largest remaining deviation cost is `hub_material_closure`, approximately
109.500 seconds. It uses 52,479 forward samples, 220,279 reverse samples, and
34,560 reconstruction triangles. This is recorded as the next bounded
performance target; tolerances were not reduced in R16.24.

## Verification Commands

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v11_6_section_curve_surfaces.py tests/test_impeller_v11_6_section_curve_authority.py -q
python -m pytest tests/test_impeller_v11_6_deviation.py tests/test_impeller_v11_6_comparison_scope.py tests/test_impeller_v11_6_step_audit.py -q
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py tests/test_impeller_v11_6_section_loops.py tests/test_impeller_v11_6_pattern_reconstruction.py -q
cd frontend
npm.cmd test
```

Verification result:

- section surfaces, curve authority, and inspection: 89 passed;
- pattern/material and generic topology: 32 passed;
- deviation, comparison scope, and audit: 84 passed, 1 skipped;
- axis-first, section loops, overlays, and decomposition: 162 passed;
- frontend Node tests: 255 passed;
- Python compilation and `git diff --check`: passed.
