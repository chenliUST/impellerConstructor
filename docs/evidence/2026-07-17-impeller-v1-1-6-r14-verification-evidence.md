# Impeller V1.1.6 R14 Verification Evidence

Date: 2026-07-17

## Retained Real-Audit Baseline

Local audit `step-audit-e798baae387d48f7` completed `PASS` as R13.2 evidence.
Its artifact sizes include:

- `heatmap.json`: 201,960,663 bytes;
- `manifest.json`: 49,299,277 bytes;
- `geometric-manifest.json`: 40,110,540 bytes.

The measured `deviation_measured` duration was 5,363.615 seconds. This audit is
used only as the optimization baseline.

## Deterministic Benchmark

Eight 64-by-64 sampled surfaces, with identical exact outputs:

| Mode | Time | Index builds | Queries | Cache hits |
| --- | ---: | ---: | ---: | ---: |
| serial | 7.3485 s | 9 | 16 | 0 |
| two-worker cold cache | 4.9826 s | 9 | 16 | 0 |
| two-worker warm cache | 0.4202 s | 0 | 0 | 8 |

The cold parallel run was about 1.48 times faster and the warm run about 17.5
times faster than serial. Serial, cold-parallel, and warm-cache metrics and
heatmaps compared equal as Python values.

## Verification Commands

```text
python -m pytest tests/test_impeller_v11_6_deviation.py -q
12 passed

python -m pytest tests/test_impeller_v11_6_deviation.py \
  tests/test_impeller_v11_6_step_audit.py \
  tests/test_impeller_v11_6_axis_first_contract.py \
  tests/test_impeller_v11_6_step_api.py -q
111 passed, 1 skipped

python -m ruff check <R14 changed Python modules and tests>
All checks passed

PYTHONPATH=src python -m pytest <V1.1.6 test files 1-8> -q
153 passed

PYTHONPATH=src python -m pytest <V1.1.6 test files 9-16> -q
120 passed

PYTHONPATH=src python -m pytest <V1.1.6 test files 17-24> -q
215 passed, 1 skipped
```

The complete V1.1.6 regression inventory therefore totals `488 passed, 1
skipped`. It was split because the single 24-file invocation exceeded the
604-second command limit before returning a summary.

## Fresh R14 KS007G23B Audit

Audit `step-audit-058a9e65e2d341d3` completed without restart on the local
Windows workstation:

- implementation revision: `axis_first_triangle_surface_r14_0`;
- source SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`;
- process status: `PASS`;
- surface deviation progress: `82/82`;
- axis-first geometry status: `REJECTED`;
- disposition: `review_only_not_promotable`;
- wall time from audit creation to completion: approximately `4464 s`
  (`74.4 min`);
- observed process private-memory peak during the final surface: approximately
  `13.4 GB` (diagnostic observation, not an instrumented allocation maximum);
- exact checkpoint files: `82`;
- exact checkpoint bytes: `40,455,892`.

Measured stage durations:

| Stage | Duration |
| --- | ---: |
| B-Rep load | 14.771 s |
| canonical frame | 33.884 s |
| semantic classification | 3.518 s |
| parameter extraction | 197.390 s |
| hub reconstruction | 231.601 s |
| blade reconstruction | 124.459 s |
| edge closure | 105.730 s |
| deviation and artifacts | 3651.358 s |

The R13.2 deviation baseline was `5363.615 s`; R14 reduced the complete
deviation/artifact stage by approximately `31.9%` (`1.47x`). The exact
surface-distance core reported `1595.710 s`, `164` fused directional queries,
`149` index builds, two surface workers, `82` cache writes and zero cache-write
failures. The remaining stage time is dominated by source-region preparation,
surface pairing, and large artifact assembly/serialization, so R14 does not
claim that the full stage is reduced to the exact-query duration.

The reconstructed-to-source distribution remained:

| Metric | Value |
| --- | ---: |
| minimum | 0.000000 mm |
| median | 0.880663 mm |
| P95 | 10.802197 mm |
| RMS | 4.882656 mm |
| maximum | 31.593204 mm |

Artifact hashes:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| source STL | 51,017,434 | `1d5796f019efa8bf38288dbbfa87d961ed05fab8d0c8687c19f696f230f56b6e` |
| reconstruction STL | 39,219,284 | `20a816bafcd01f212c09dd61d708734752a36ba6f01a7afd54782acb6f3d88ed` |
| Geometric Manifest | 40,110,540 | `f8ae2a420e26c56898a2a237f832a5e6851f50fcab17c971e87c25879d40ba2b` |
| heatmap | 201,960,663 | `758f2884628996a8fe3575464372128c960479e4bc865a2f1271d091b3a49f19` |

## Acceptance Boundary

R14 verifies exact-deviation performance and restart-safe checkpoint behavior;
it does not certify the reconstructed geometry. Browser review exposed an
independent canonical-axis polarity defect that reversed the recovered support
profile semantics and allowed an oversized hub outer wall to occlude the
blades. The audit was already non-promotable because camber, pose, normal
thickness, edge-curve and periodicity gates failed. The R14 artifacts are
retained as performance evidence and must not be relabeled as R15 geometry.
