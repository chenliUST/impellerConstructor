# Impeller V1.1.6 R14 Deviation Performance Hardening

Date: 2026-07-17

## Objective

Reduce the wall-clock cost and restart risk of the exact corresponding-surface
deviation stage without changing V1.1.2 geometry, semantic surface ownership,
sampling density, distance definition, or heatmap values.

## Measured Baseline

The uninterrupted local audit `step-audit-e798baae387d48f7` completed with:

| Stage | Duration |
| --- | ---: |
| B-Rep load | 49.299 s |
| frame resolution | 88.981 s |
| semantic classification | 10.108 s |
| parameter extraction | 411.877 s |
| three reconstruction stages | 613.120 s |
| corresponding-surface deviation and artifacts | 5,363.615 s |

The deviation stage is therefore the primary optimization target. The retained
audit remains R13.2 evidence and is not relabeled as R14.

## Implementation

- [x] Build each source triangle acceleration index once and reuse it.
- [x] Fuse reconstruction-centroid and reconstruction-vertex forward queries.
- [x] Run independent semantic surface pairs with bounded parallel workers.
- [x] Preserve sorted deterministic result assembly.
- [x] Persist exact per-surface directional arrays in content-addressed
  checkpoints.
- [x] Load checkpoints before building acceleration indexes.
- [x] Invalidate only the surface whose source or reconstruction mesh changes.
- [x] Persist surface-level heartbeat and progress evidence.
- [x] Prevent unrelated import processes from marking live workers interrupted.
- [x] Version the audit implementation and checkpoint contracts.
- [x] Run a fresh uninterrupted R14 KS007G23B audit and record real wall time,
  observed peak memory, cache size, and artifact disposition. Browser geometry
  review identified the separately planned R15 axial-semantic defect; R14 is
  retained as performance evidence only.

## Safety Constraints

- A checkpoint key includes contract revision, semantic role, source mesh
  fingerprint, and reconstruction mesh fingerprint.
- Cached arrays must have exact expected lengths and finite values.
- Cache failure degrades to exact recomputation; it cannot fail the audit.
- Parallel execution uses the same exact triangle-distance termination rule.
- The default is two surface workers on this 16 GB workstation; the bounded
  environment override is `V116_DEVIATION_MAX_WORKERS=1..4`.
- Full-audit reuse still requires source hash, implementation revision,
  manifest digest, and artifact integrity checks.

## Acceptance

- Serial, parallel, cold-cache, and warm-cache outputs compare equal.
- A warm cache performs zero triangle-index builds and zero distance queries.
- Changing one surface invalidates only that surface.
- Live workers survive startup recovery; dead workers are explicitly failed.
- Targeted backend and API contracts pass, Ruff passes, and no historical audit
  is promoted to the new revision.
