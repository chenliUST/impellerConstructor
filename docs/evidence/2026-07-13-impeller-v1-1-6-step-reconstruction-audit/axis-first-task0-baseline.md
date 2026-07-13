# Axis-First Task 0 Baseline

Recorded on 2026-07-13 before implementation of the axis-first algorithm.

## Repository Checkpoint

- Branch: `feature/ks007g23b-preset`
- Prior implementation checkpoint: `07a4fa8`
- Axis-first spec/plan checkpoint: `3806cf2`
- Upstream baseline before the two checkpoints: `f46629f`

The local customer/reference inputs `KS007G23B.pdf` and `KS007G23B.stp` are not
tracked. They are listed in the local Git `info/exclude` file so routine staging
cannot add them accidentally. Their content is not part of repository evidence.

## Verified Baseline

Backend command:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_ks007g23b_preset.py tests/test_impeller_v11_5_engineering_drawing.py tests/test_impeller_v11_6_step_api.py tests/test_impeller_v11_6_step_audit.py tests/test_impeller_v11_6_deviation.py -q
```

Result: `29 passed, 1 skipped in 157.60s`.

Frontend command:

```text
cd frontend
npm.cmd test
```

Result: `220 passed, 0 failed`.

## Kernel And Library Versions

- Python: workspace Python 3.12 runtime
- CadQuery: `2.8.0`
- OCP/OCCT binding: `7.9.3.1`
- NumPy: `2.4.6`
- SciPy: `1.18.0`

## Recorded Generic Reconstruction Baseline

- Bidirectional RMS: `2.110076 mm`
- Bidirectional P95: `4.819965 mm`
- Top silhouette Hausdorff: `5.254113 mm`
- Meridional silhouette Hausdorff: `10.168447 mm`

These numbers are comparison baselines, not acceptance of the visible blade
thickness, root or false-shroud behavior.

## Review Corrections Applied Before Task 1

- Open blade tips are recovered from shared tip-cap adjacency loops, not
  topological free edges.
- The complete fused source solid is sectioned; loops are filtered by periodic
  face provenance and sector because no standalone source blade solid exists.
- Source-shaped edge NURBS curves are measurement targets. V1.1.2 retains its
  cap roundness/sagitta representation and reports the remaining curve residual.
- Regression wording protects geometry/canonical hashes while allowing the
  already documented additive manifest metadata.
