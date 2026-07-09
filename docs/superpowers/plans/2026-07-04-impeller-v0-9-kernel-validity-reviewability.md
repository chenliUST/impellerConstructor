# V0.9 Kernel Validity And Reviewability Implementation Plan

Date: 2026-07-04

## Summary

V0.9 turns the V0.8 transition semantic failures into measurable kernel validity
checks. The implementation order is test-first: make the current failure class
detectable, fix transition construction, then connect validation results to export,
batch regression, evidence, and frontend review metadata.

The core topology change is that `blade_root_to_hub` no longer treats one
`blade_i_root_transition_surface` as a successful root blend. V0.9 requires separate
per-blade side surfaces:

- `blade_i_pressure_root_transition_surface`
- `blade_i_suction_root_transition_surface`

V0.2-V0.8 remain historical and loadable.

## Implementation Tasks

1. Add the V0.9 resource line and interface contract.
2. Add geometry validation reports and export blocking.
3. Correct transition construction semantics with double-sided root topology.
4. Add trim exclusion support for mesh/STL/OBJ/STEP review exports.
5. Add export gates, batch regression, and evidence summaries.
6. Add minimal frontend V0.9 routing and validation display.
7. Verify with targeted unit/workflow tests, frontend tests/build, and repository
   verification scripts.

## Required Verification

- `python -m pytest tests/test_impeller_v09_resources.py -q`
- `python -m pytest tests/test_impeller_transition_geometry.py tests/test_impeller_geometry_validation.py -q`
- `python -m pytest tests/test_impeller_transition_mesh.py tests/test_impeller_bounded_brep_export.py -q`
- `python -m pytest tests/test_workflow.py -q`
- `npm.cmd test`
- `npm.cmd run build`
- `.\scripts\verify_repository.ps1 -Mode fast`
- `.\scripts\verify_repository.ps1 -Mode full`

## Delivery Notes

Large binary review artifacts remain in `Model Output/`. Git evidence is limited to
JSON/text summaries, version docs, registries, and issue-linkage schemas.
