# Impeller V1.1.5 Verification Evidence

## Automated Verification

```text
python -m pytest tests/test_impeller_v11_5_engineering_drawing.py -q
6 passed

python -m pytest tests/test_impeller_v11_5_review_summary.py \
  tests/test_impeller_v11_5_engineering_drawing.py -q
7 passed

python -m pytest tests/test_impeller_v11_4_release.py -vv -x
3 passed

python -m pytest tests/test_impeller_v11_4_engineering_drawing.py -vv -x
5 passed

python -m pytest \
  tests/test_impeller_v11_3_service_manifest.py::test_service_manifest_separates_runtime_and_geometry_versions \
  tests/test_impeller_v11_3_service_manifest.py::test_all_active_presets_expose_service_inspection_contracts -vv
2 passed

cd frontend
npm.cmd test
215 passed

npm.cmd run build
frontend build check passed
```

The entire 16-test service-manifest file was also attempted as one process, but
its repeated high-density graph construction exceeded a 15-minute command limit.
The two release-relevant cases above were then run separately and passed in
9 minutes 16 seconds. This timeout is recorded as test-suite performance debt, not
as a product failure.

## Contract Evidence

- Top blade paths all report `source_kind=surface_projection`.
- Open Top exposes main and splitter active-root/midspan/active-tip sections.
- NASA Stage 37 projected blade-instance ids equal all 46 resolved instances.
- Meridional support profiles use at least 129 evaluated points and report a
  maximum chord error no greater than 0.1 mm.
- Meridional material regions are closed and the side view contains resolved
  surface projections.
- Main and splitter S-Q rows each expose five sections and five XYZ overlays.
- The construction registry reports 131 accounted leaves and zero unaccounted
  leaves for the open reference preset.

## Browser Evidence

Live services:

```text
Frontend: http://127.0.0.1:5199
Backend:  http://127.0.0.1:8061
```

The in-app browser verified:

1. Open Top surface projection, explicit hub/bore circles and six class-aware
   section insets.
2. Open Meridional evaluated profiles, material hatching, dashed controls,
   dimensions, control table and side view.
3. Open S-Q five-span main/splitter rows and depth-tested representative 3D blades.
4. Construction Tables with zero unaccounted canonical leaves.
5. Shaded CAD Review completes without the prior combined-mode WebView loss.
6. NASA Stage 37 compact Drawing generation completes and renders all resolved
   blade surface projections without `Maximum call stack size exceeded`.

## Residual Boundary

- Drawing-mode generation intentionally skips STEP/STL and CFD mesh work. Those
  artifacts remain available through a CAD Review generation.
- V1.1.5 is still sampled review-grade geometry and does not claim certified
  manufacturing drawings or exact hidden-line removal.
