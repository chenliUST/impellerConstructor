# Task 1 Report: Backend Canonical NURBS Payload Module

Date: 2026-07-10

Base commit: `4f33a0a212ac956f329a3abca820f392827a2725`

## Scope

Owned files:

- `src/part_rule_synthesis/impeller_v11_2_canonical.py`
- `tests/test_impeller_v11_2_canonical_parameterization.py`

## Requirements Read

Read and followed:

- `C:\Users\CHEN Li\Documents\TurboJetCase\impeller-v112-hardening\.superpowers\sdd\task-1-brief.md`

Nothing in the brief was unclear, so implementation proceeded directly.

## TDD Record

### Red

Created `tests/test_impeller_v11_2_canonical_parameterization.py` exactly from the task brief.

Ran:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Observed expected failure:

- `ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v11_2_canonical'`

This confirmed the test was failing for the expected reason before production code existed.

### Green

Implemented `src/part_rule_synthesis/impeller_v11_2_canonical.py` with:

- `clamped_uniform_knots`
- `evaluate_nurbs_curve`
- `evaluate_nurbs_surface`
- `canonical_nurbs_from_v11_defaults`
- private helpers for canonical curve/surface construction, default translation, cap intent, attachment policy, pose field, sampling policy, metrics, and self-contained Cox-de Boor basis evaluation

The module translates V1.1 preset defaults into a deterministic V1.1.2 canonical payload containing:

- support-profile NURBS curves
- active span policy
- blade population metadata
- canonical blade skeleton NURBS surface
- canonical thickness NURBS surface
- section loop family with NURBS cap intent
- attachment policy
- pose field
- sampling policy
- reported metrics

First green run exposed an endpoint bug in recursive basis evaluation at `u == 1.0`. Fixed by clamping terminal parameters with `math.nextafter(1.0, 0.0)`.

Re-ran:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Observed pass:

```text
4 passed in 0.13s
```

## Implementation Notes

- Kept the module self-contained per the brief.
- Used only standard-library math, mappings, and list-based data structures.
- Added `degree_u`/`degree_v` and concrete `knots_u`/`knots_v` aliases on canonical surfaces so the public evaluator can consume canonical payload surfaces directly in later tasks while still preserving `degree_s`/`degree_h` and `knots_s`/`knots_h`.
- Preserved the exact public constants requested:
  - `MATH_PARAMETERIZATION = "v1_1_2_canonical_nurbs_parameterization"`
  - `CANONICAL_PAYLOAD_VERSION = "1.1.2"`

## Verification

Focused verification command:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Result:

- PASS
- `4 passed in 0.13s`

## Self-Review

Checked:

- test written before implementation
- failure observed for the expected reason
- public API matches the brief
- module is confined to owned file
- test file is confined to owned file
- focused verification is green

## Concerns

No blocking concerns for Task 1.

The current canonical translator is deterministic and spec-aligned for this task, but later tasks may tighten expectations around exact field shapes and downstream surface-graph consumption. The file structure leaves room for that without changing the public API.

---

## Task 1 Fix After Review

Addressed review findings in the owned Task 1 files only:

1. Generated canonical NURBS surfaces now emit explicit numeric weight grids instead of the `"all_ones"` sentinel.
2. `_thickness_field()` now derives its interior streamwise control-point stations from `main_streamwise_interval_s` using the same translated interval pattern as `_skeleton_field()`.
3. Added regression coverage for numeric surface weight grids and for translated non-default thickness-field `s` stations.

Verification run:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Observed output:

```text
.....                                                                    [100%]
5 passed in 0.21s
```
