# Task 2 Report: Integrate Runtime, Manifest, and Validation Semantics

## Scope

Base commit: `f04736d feat: add v1.1.3 parameter inspection contract`.

Implemented only the Task 2-owned production and test files:

- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `src/part_rule_synthesis/impeller_v11_validation.py`
- `src/part_rule_synthesis/service.py`
- `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- `tests/test_impeller_v11_3_service_manifest.py`

The report itself is at `.superpowers/sdd/task-2-report.md` as requested. Geometry patch and canonical payload versions remain `1.1.2`.

## RED Evidence

Added `tests/test_impeller_v11_3_service_manifest.py` before editing production code. It uses the Task 1 `graph_for` and `ACTIVE_PRESETS` shapes, explicit `RuleSynthesisService` and `validate_v11_surface_graph` imports, and covers the four test cases specified in the brief.

First command attempt:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -q
```

Result: harness command timeout after `124.031s`, while service/STEP export work was still active. This was not test output.

Rerun of the same command with the test command timeout extended to 600 seconds:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `4 failed in 137.43s (0:02:17)`, with the expected missing behavior:

- `KeyError: 'runtime_release_version'`
- missing `parameter_inspection_surface_reference_missing` validation reason
- missing `parameter_inspection_generation_id_mismatch` validation reason
- `KeyError: 'parameter_inspection_contract_version'`

## GREEN Implementation

- Runtime V1.1 defaults now expose `runtime_release_version` and `parameter_inspection_contract_version` from Task 1 constants.
- `validate_parameter_inspection_contract(surface_graph, contract)` validates contract version, graph/contract generation identity, surface reference coverage, span-station/loop references, and closed-loop status.
- `validate_v11_surface_graph` invokes that validator only for `geometry_patch_version == "1.1.2"`, immediately after canonical validation.
- V1.1 service manifests project runtime/contract versions, `generation_id`, and a deep-copied `parameter_inspection` object while retaining the existing `geometry.surface_graph` structure.

Focused GREEN command:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `4 passed in 529.29s (0:08:49)`.

## Regression Evidence

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_2_surface_graph_compatibility.py tests/test_impeller_v11_resources.py -q
```

Result: `22 passed in 805.49s (0:13:25)`.

```powershell
git diff --check
```

Result: exit code `0`; no whitespace errors. Git emitted existing working-tree CRLF conversion warnings for four modified source files.

## Self-Review

- Confirmed runtime and manifest labels are V1.1.3 while geometry patch and canonical payload labels remain V1.1.2.
- Confirmed the validator is gated to V1.1.2 and returns the exact required reason names.
- Confirmed `parameter_inspection` is deep-copied at manifest top level and `geometry.surface_graph` remains unchanged.
- Confirmed the diff is limited to the four requested production files plus the requested test file.
- No functional concerns found.

## Concern

The service-manifest tests are slow because each active-preset assertion performs complete geometry and STEP export work. The required combined regression suite passes, but needs approximately 13.5 minutes in this environment.

## Review Fix: Generation Integrity And Malformed Contracts

### Fix Details

- `validate_parameter_inspection_contract` now recomputes the generation ID from the current surface graph and requires both `surface_graph["generation_id"]` and `contract["generation_id"]` to match it. Mutating geometry without regenerating provenance now returns `parameter_inspection_generation_id_mismatch`.
- `surface_references`, `span_stations`, and `section_loops` must be mappings before traversal.
- Every section-loop entry and its `metrics` payload must be mappings before `.get()` access. Malformed structures return `parameter_inspection_contract_unsupported` instead of raising.

### Review Fix RED

Added five focused tests before changing production code, then ran:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -k "geometry_mutation or non_mapping or malformed_section_loop_entry" -q
```

Result: `5 failed, 4 deselected in 23.13s`.

- Geometry mutation produced no mismatch reason because only stored IDs were compared.
- Non-mapping `surface_references` and `span_stations` produced missing-reference reasons instead of unsupported-contract reasons.
- Non-mapping `section_loops` and a malformed loop entry raised `AttributeError` during validation.

### Review Fix GREEN

Reran the same focused command after the validator change:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -k "geometry_mutation or non_mapping or malformed_section_loop_entry" -q
```

Result: `5 passed, 4 deselected in 30.99s`.

Ran the exact requested regression command:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py tests/test_impeller_v11_3_parameter_inspection_contract.py -q
```

Result: `13 passed in 466.57s (0:07:46)`.

### Review Fix Self-Review

- Confirmed a geometry-only `uv_grid` mutation invalidates both otherwise matching stored IDs through recomputation.
- Confirmed each requested malformed collection and malformed loop entry returns a defined validation reason without throwing.
- Confirmed structurally valid contracts still use the existing specific surface, station, generation, and loop reasons.
- Confirmed review-fix code changes are limited to `impeller_v11_3_parameter_inspection.py` and `test_impeller_v11_3_service_manifest.py`.
- `git diff --check` passed; only the repository's existing LF-to-CRLF working-tree warnings were emitted.

### Review Fix Concern

No new functional concerns. The exact suite remains slow because all active service presets perform full geometry and STEP generation.

Review fix commit: `bd28ec3 fix: harden inspection contract validation`.

## Review Fix: Nested Station Identifier Types

### Fix Details

- Added `test_validation_rejects_malformed_nested_contract_values` with otherwise mapping-shaped section loops whose `span_station_id` is first `[]` and then `{}`.
- Section-loop validation now requires `span_station_id` to be a non-empty string before constructing the set of referenced station IDs.
- Invalid nested identifier types return `parameter_inspection_contract_unsupported` instead of reaching set insertion and raising `TypeError`.

### RED Evidence

Ran the single malformed-contract test before changing production code:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py::test_validation_rejects_malformed_nested_contract_values -q
```

Result: `1 failed in 7.75s`. The first case raised `TypeError: unhashable type: 'list'` in the `loop_station_ids` set comprehension.

### GREEN Evidence

Reran the single malformed-contract test after the validator change:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py::test_validation_rejects_malformed_nested_contract_values -q
```

Result: `1 passed in 10.52s`.

Ran the exact requested regression command:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py::test_validation_rejects_malformed_nested_contract_values tests/test_impeller_v11_3_parameter_inspection_contract.py -q
```

Result: `5 passed in 56.08s`.

### Self-Review

- Confirmed both unhashable nested values are exercised in the same focused regression test.
- Confirmed type and non-empty checks execute before set construction.
- Confirmed valid string station IDs retain the existing station-reference comparison behavior.
- Confirmed code/test changes remain limited to the Task 2 validator and test file.
- `git diff --check` passed; only existing LF-to-CRLF working-tree warnings were emitted.

### Concern

No functional concerns found.

Nested station identifier fix commit: `5bac741 fix: validate inspection station identifiers`.

---

# Task 2 Engineering Parameter Inspection Completion

## Scope

Base commit: `3a9600e fix: preserve legacy inspection contracts`.

Implementation commit: `fb1fc80 feat: validate engineering inspection evidence`.

Changed files:

- `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `tests/test_impeller_v11_3_engineering_inspection.py`

The implementation keeps `geometry_version` at `1.1` and the source geometry patch at `1.1.2`. Engineering records are additive, so legacy V1.1.3 contracts without `parameter_groups` and `parameters` remain valid.

## RED Evidence

Added open/closed coverage, measurement-consistency, mutation, and capability tests before implementing the new measurement path.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -q
```

Result: collection failed as expected because `_measure_dimension` did not exist.

## GREEN Evidence

Implemented geometry-derived profile controls, blade placement, spanwise pose, section control/sagitta, attachment, shroud-thickness, and result records. Added `_measure_dimension` and strict structural/reference/degenerate-baseline checks, with dimension mismatches reported as `parameter_inspection_dimension_value_mismatch`.

Focused verification:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -q
```

Result: `8 passed in 118.41s (0:01:58)`.

The focused invalid-reference and degenerate-baseline case also passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py::test_validator_rejects_invalid_parameter_groups_and_records -q
```

Result: `1 passed in 58.79s`.

## Exact Requested Backend Verification

Completed before the final focused test-only self-review addition:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `35 passed in 930.20s (0:15:30)`.

The identical command was started again after the final test-only self-review change, but the user interrupted the task before it completed. No final result was returned for that post-review run; no replacement long test was started at the user's instruction.

## Self-Review

- Parameter evidence is derived from generated support profiles, section-loop controls, attachment surfaces, and shroud surfaces, not frontend defaults.
- Control records include exactly one `control_point` primitive and one `control_coordinate` dimension.
- The manifest advertises the three additive engineering inspection capabilities without changing geometry versioning.
- Base relationship validation retains its established specific failure reasons before additive selection-scope rejection.
- `git diff --check` passed before reporting; only repository LF-to-CRLF warnings were emitted.

## Concerns

The exact backend suite is slow: the completed run took 15 minutes 30 seconds. The final exact rerun was interrupted after the focused post-review test passed, so the last completed exact result predates that test-only addition.

---

## Review Fix: Source-Bound Engineering Evidence

Review-fix implementation commit: `d83a8f0 fix: bind engineering inspection to source geometry`.

Addressed the review findings in `impeller_v11_3_parameter_inspection.py`, `service.py`, and the two Task 2 test modules:

- Closed shroud width now comes from the closed attachment's authoritative `shroud_reference_loop` and `shroud_attachment_loop` evidence. It never uses the root-only metric scale.
- Every generated control point for every section segment and station emits both `s` and `q` parameter records.
- Validation binds control, profile, station, thickness, sagitta, and attachment parameter evidence to the source contract/geometry. Self-consistent mutations that no longer match source evidence are rejected.
- Angular dimension vectors must have equal coordinate dimensions.
- The public V1.1 service manifest projects `parameter_inspection_capabilities`.

### RED Evidence

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `5 failed, 23 passed in 796.35s (0:13:16)`. The failures covered missing closed-shroud provenance, truncated controls, missing source binding, angular vector dimension acceptance, and missing public manifest capabilities.

### GREEN Evidence

Focused engineering checks after implementation:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -k "engineering_dimension_records or closed_shroud_width or section_control_parameters or self_consistent or angular_dimension" -q
```

Result: `5 passed, 7 deselected in 58.12s`.

Required focused suite:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_service_manifest.py -q
```

Result: `28 passed in 861.51s (0:14:21)`.

### Exact Suite Status

Started the required Task 2 exact suite after the focused suite passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py -q
```

The user interrupted the task before this command returned a final result. No replacement long suite was started at the user's instruction.

### Concerns

The completed focused suite takes approximately 14 minutes in this environment. The post-review exact suite is incomplete, so it has no pass/fail result for the final review-fix commit.

---

## Review Fix: Generated Graph Binding

Implementation commit: `2e1d6c1 fix: bind inspection evidence to generated graph`.

- Loop-derived section controls, pose frames, thickness, and sagittae now resolve from `surface_graph["blade_to_blade_loop_family"]`, never mutable inspection contract loops.
- Placement records validate against generated blade population and generated root-attachment directions; their source scopes are explicit.
- Shroud thickness now carries the generated inner/outer shroud surface IDs and validates against those surfaces.
- Sagitta validation now verifies the displayed polyline as well as the measured points and value.

### RED Evidence

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -k "mutable_contract_loops or placement_shroud_and_sagitta" -q
```

Result before the graph-backed implementation: `1 failed, 1 passed in 15.69s`; placement, shroud, and sagitta records were not source-bound.

### GREEN Evidence

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -k "mutable_contract_loops or placement_shroud_and_sagitta" -q
```

Result: `2 passed, 12 deselected in 19.76s`.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -q
```

Result: `14 passed in 199.31s (0:03:19)`.

### Suite Status

Per instruction, the 15-minute three-file suite was not started in this review wave. The engineering inspection file is the completed final verification.

---

## Review Fix: Deterministic Selector And Result Binding

Implementation commit: `f15cd2f fix: bind inspection selectors and results`.

- Source station, segment, and control selectors now resolve through generated graph data and must map back to the declared blade/station/loop/segment/control identity and deterministic control parameter path.
- Legacy profile curve, pose, thickness, root-offset, and join-status records now have explicit validation coverage. Join-status validates its generated status and displayed polyline.
- Placement records validate generated population/directions and their `reference_axis` primitives; shroud thickness remains source-surface bound.

### RED Evidence

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -k "selector_identity or join_results_and_placement" -q
```

Result before implementation: `1 failed, 1 passed in 28.64s`; join-result and placement feature mutations were accepted.

### GREEN Evidence

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -k "selector_identity or join_results_and_placement" -q
```

Result: `2 passed, 14 deselected in 37.76s`.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_v11_3_engineering_inspection.py -q
```

Result: `16 passed in 244.52s (0:04:04)`.

### Suite Status

Per instruction, the long three-file suite was not started in this wave.
