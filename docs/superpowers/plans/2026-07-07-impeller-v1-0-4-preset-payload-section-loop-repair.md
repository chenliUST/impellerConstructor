# Impeller V1.0.4 Preset Payload Section-Loop Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep V1.0.4 as the active version while repairing the preset, frontend payload, backend payload ingestion, and section-loop constructor so the displayed controls are the geometry controls.

**Architecture:** First align frontend and DSL V1.0.4 preset defaults around the user-approved 6 main + 6 splitter impeller with curved hub/tip NURBS profiles. Then carry `section_loop_overrides` through the frontend and API into the V1.0.4 surface graph. Finally replace the free-curve section-loop prototype with an S-camber normal-offset loop that produces near-parallel pressure/suction curves and C2-intent leading/trailing caps.

**Tech Stack:** Python geometry kernel and pytest, JSON DSL resources, React frontend model/components and npm tests.

## Global Constraints

- Do not create a new version number; keep `geometry_patch_version = "1.0.4"`.
- Preserve historical V1.0.0-V1.0.3 files and behavior unless the active V1.0.4 path explicitly consumes the changed data.
- Do not solve open-tip or root quality by hiding surfaces; repair the data path and section-loop constructor.
- The open preset uses `main_blade_count = 6`, `splitter_blade_count = 6`, and review blade thickness in the `30-50 mm` range.
- Hub and tip reference profiles use the user-provided curved meridional control points.

---

### Task 1: Preset And Payload Chain

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/apiClient.js`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/components/CurveControlPanel.test.js`
- Test: `tests/test_impeller_v10_4_resources.py`

**Interfaces:**
- Produces frontend payload field `section_loop_overrides`.
- Produces backend geometry option `section_loop_overrides`.
- Produces V1.0.4 preset defaults with 6 main + 6 splitter blades and curved hub/tip profiles.

- [ ] Write failing tests that assert V1.0.4 frontend and DSL presets expose the same blade counts, profile control points, and section-loop defaults.
- [ ] Write failing tests that assert curve panel edits serialize `section_loop_overrides` and that instantiate payload includes it.
- [ ] Update frontend model and API client to preserve `section_loop_overrides`.
- [ ] Update service/runtime compiler/surface graph to pass `section_loop_overrides` into the V1.0.4 section-loop defaults.
- [ ] Update V1.0.4 open preset defaults in frontend and DSL.
- [ ] Run focused frontend and backend tests.

### Task 2: S-Camber C2-Intent Section Loop

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v10_3_section_loop.py`
- Modify: `src/part_rule_synthesis/impeller_v10_4_section_loop_contract.py`
- Test: `tests/test_impeller_v10_4_section_loop_contract.py`
- Test: `tests/test_impeller_v10_4_surface_graph.py`

**Interfaces:**
- Consumes `section_loop_overrides.blade_section_loop_template` or preset section-loop defaults.
- Produces section loops whose pressure and suction sides are generated from the same S-camber mean curve plus normal-offset thickness.
- Produces per-loop contract metadata for C2-intent joins and near-parallel side validation.

- [ ] Write failing tests for near-parallel pressure/suction curves, visible but smoothed S-camber, and leading/trailing C2 join metadata.
- [ ] Replace the V1.0.4 section-loop generation path with an S-camber normal-offset generator.
- [ ] Keep V1.0.3 historical generation untouched unless `geometry_patch_version == "1.0.4"`.
- [ ] Add failure reasons for malformed section-loop overrides and non-parallel side construction.
- [ ] Run focused backend tests.

### Task 3: Verification

**Files:**
- Test: `tests/test_impeller_v10_4_resources.py`
- Test: `tests/test_impeller_v10_4_section_loop_contract.py`
- Test: `tests/test_impeller_v10_4_surface_graph.py`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/components/CurveControlPanel.test.js`

- [ ] Run `python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_4_section_loop_contract.py tests/test_impeller_v10_4_surface_graph.py -q`.
- [ ] Run `cd frontend; npm.cmd test -- appModel CurveControlPanel`.
- [ ] If focused tests pass, instantiate `radial_open_reference_v1_0` through the local service and inspect graph metadata for V1.0.4, 6 main blades, 6 splitters, curved hub profile, and consumed section-loop contract.
