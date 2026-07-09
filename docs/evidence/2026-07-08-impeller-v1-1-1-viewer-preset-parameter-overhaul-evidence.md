# Impeller V1.1.1 Viewer, Preset, And Parameter Overhaul Evidence

Date: 2026-07-08

## Summary

V1.1.1 keeps the V1.1 blade-to-blade loop surface-family constructor and patches display semantics, all-surface mesh metadata, active preset selection, zero-splitter closed presets, and frontend parameter ownership.

## Verification

- `python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_mesh_and_export_contract.py -q`
  - `14 passed in 206.55s`
- `python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q`
  - `52 passed in 161.58s`
- `cd frontend; npm.cmd test`
  - `119 tests`, `119 passed`, `0 failed`
- Five-preset `RuleSynthesisService` smoke with `PYTHONPATH=src`
  - `radial_open_reference_v1_1`: `PASS`, `291840` CFD surface mesh triangles
  - `radial_closed_reference_v1_1`: `PASS`, `66816` CFD surface mesh triangles
  - `nasa_stage37_stator_ring_v1_1`: `PASS`, `322048` CFD surface mesh triangles
  - `rr_ultrafan_cti_fan_v1_1`: `PASS`, `255744` CFD surface mesh triangles
  - `public_rocket_turbopump_inducer_v1_1`: `PASS`, `41088` CFD surface mesh triangles

## Result

- Backend V1.1 tests: PASS
- Frontend tests: PASS
- Five-preset service smoke: PASS for all active V1.1.1 presets

## Notes

The RR UltraFan CTi fan preset needed denser V1.1.1 sampling for bounded STEP export stability. The sampling contract was raised to `side_sample_count >= 81` and `surface_span_sample_count >= 13`; the geometry shape parameters were not changed.

Final review found two metadata/viewer drift issues before completion: V1.1.1 `CFD full 360` now falls back to `cfd_surface_mesh.patch_regions` when the legacy `cfd_full_360.patch_instances` manifest is absent, and the V1.1 export contract now advertises `v1_1_1_all_surface_uv_grid_mesh`.
