# Impeller V1.1.2 Canonical NURBS Parameterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.1.2 as a canonical NURBS parameterization layer that translates the current V1.1.1 presets into explicit support profiles, active span policy, skeleton/thickness fields, NURBS section-loop caps, and frontend generated-model parameter annotations.

**Architecture:** Add a V1.1.2 translator in front of the existing V1.1 blade-to-blade loop and surface-family builders. Keep the V1.1 S-Q-H domain and face-family surface graph stable, but make the runtime and manifest expose `canonical_nurbs_parameterization` as the source of truth. Add a frontend `Parameter views` inspection tab that reads preset defaults before generation and manifest-resolved canonical data after generation.

**Tech Stack:** Python 3.12 geometry kernel and pytest; JSON DSL resources; FastAPI service manifest path; React-free browser ESM frontend with Node built-in tests; Three.js existing viewer.

## Global Constraints

- Do not delete historical V1.0, V1.0.4, V1.1, or V1.1.1 specs, evidence, or resources.
- Preserve active preset ids: `radial_open_reference_v1_1`, `radial_closed_reference_v1_1`, `nasa_stage37_stator_ring_v1_1`, `rr_ultrafan_cti_fan_v1_1`, `public_rocket_turbopump_inducer_v1_1`.
- V1.1.2 reports `geometry_version = "1.1"` and `geometry_patch_version = "1.1.2"`.
- V1.1.2 reports `math_parameterization = "v1_1_2_canonical_nurbs_parameterization"`.
- V1.1.2 keeps `transition_geometry_status = "topology_first_blade_to_blade_5_loop_surface_family_graph"`.
- V1.1.2 remains sampled review-grade geometry; exact analytic OCCT NURBS solids are out of scope.
- Legacy V1.1 scalar fields remain compatibility inputs, but they are classified as translated handles or preset seeds.
- New production behavior must be test-first: write a failing test, verify it fails, implement minimal code, verify it passes.

---

## File Structure

Create:

- `src/part_rule_synthesis/impeller_v11_2_canonical.py` - canonical NURBS payload construction, lightweight NURBS evaluation, active span metrics, and legacy V1.1 translation helpers.
- `tests/test_impeller_v11_2_canonical_parameterization.py` - unit tests for canonical payload shape and NURBS helpers.
- `tests/test_impeller_v11_2_preset_translation.py` - runtime compiler and all-five-preset translation tests.
- `tests/test_impeller_v11_2_active_span_policy.py` - active span offset and root/shroud offset policy tests.
- `tests/test_impeller_v11_2_nurbs_loop_caps.py` - cap-curve and continuity-intent tests.
- `tests/test_impeller_v11_2_surface_graph_compatibility.py` - V1.1 surface graph compatibility and manifest tests.
- `frontend/src/parameterViewModel.js` - pure frontend model for `Parameter views` tabs and annotations.
- `frontend/src/parameterViewModel.test.js` - frontend unit tests for parameter view data.
- `frontend/src/components/ParameterViewsPanel.js` - generated-model multi-view annotation panel.
- `frontend/src/components/ParameterViewsPanel.test.js` - source/component contract tests for the panel.

Modify:

- `src/part_rule_synthesis/impeller_v11_constants.py` - bump patch and add `MATH_PARAMETERIZATION`.
- `src/part_rule_synthesis/impeller_runtime_compiler.py` - attach canonical payload and math parameterization to V1.1 runtime.
- `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py` - consume canonical skeleton/thickness/active-span data while preserving existing public function names.
- `src/part_rule_synthesis/impeller_v11_surface_family.py` - pass canonical payload into graph and surface metadata.
- `src/part_rule_synthesis/impeller_v11_validation.py` and `src/part_rule_synthesis/impeller_geometry_validation.py` - allow patch `1.1.2` and validate canonical fields.
- `src/part_rule_synthesis/service.py` - expose canonical payload and metrics in manifests and keep V1.1.2 export routing.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/*.json` - bump active preset patch version to `1.1.2` and add source classification metadata.
- `frontend/src/appModel.js` - bump frontend patch metadata, add canonical defaults for presets, export helper functions.
- `frontend/src/App.js` - integrate `ParameterViewsPanel` without creating a new geometry mutation path.
- `frontend/src/appModel.test.js`, `frontend/src/appFiles.test.js` - update patch expectations and panel import checks.
- `frontend/src/styles.css` - add compact panel styles for the annotation tab.
- `docs/evidence/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-evidence.md` - append implementation verification.

---

### Task 1: Backend Canonical NURBS Payload Module

**Files:**
- Create: `src/part_rule_synthesis/impeller_v11_2_canonical.py`
- Test: `tests/test_impeller_v11_2_canonical_parameterization.py`

**Interfaces:**
- Consumes: V1.1 runtime `parameters` and `resolved_blade_to_blade_loop_family_defaults`.
- Produces:
  - `clamped_uniform_knots(point_count: int, degree: int) -> list[float]`
  - `evaluate_nurbs_curve(curve: dict[str, Any], u: float) -> list[float]`
  - `evaluate_nurbs_surface(surface: dict[str, Any], u: float, v: float) -> list[float]`
  - `canonical_nurbs_from_v11_defaults(parameters: Mapping[str, Any], defaults: Mapping[str, Any], *, source: str = "translated_from_legacy_v1_1") -> dict[str, Any]`

- [ ] **Step 1: Write failing tests for canonical payload shape**

Add this test file:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_2_canonical import (
    canonical_nurbs_from_v11_defaults,
    clamped_uniform_knots,
    evaluate_nurbs_curve,
    evaluate_nurbs_surface,
)


def _runtime(preset_id: str = "radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    return parameters, defaults


def test_clamped_uniform_knots_match_cubic_nurbs_contract():
    assert clamped_uniform_knots(6, 3) == [0.0, 0.0, 0.0, 0.0, 0.333333, 0.666667, 1.0, 1.0, 1.0, 1.0]


def test_evaluate_nurbs_curve_uses_control_points_and_weights():
    curve = {
        "kind": "nurbs_curve",
        "degree": 1,
        "control_points": [[0.0, 0.0], [10.0, 20.0]],
        "weights": [1.0, 1.0],
        "knots": [0.0, 0.0, 1.0, 1.0],
    }

    assert evaluate_nurbs_curve(curve, 0.0) == [0.0, 0.0]
    assert evaluate_nurbs_curve(curve, 0.5) == [5.0, 10.0]
    assert evaluate_nurbs_curve(curve, 1.0) == [10.0, 20.0]


def test_evaluate_nurbs_surface_bilinear_degree_one_field():
    surface = {
        "kind": "nurbs_surface",
        "degree_u": 1,
        "degree_v": 1,
        "control_points": [
            [[0.0, 0.0, 0.0], [0.0, 1.0, 10.0]],
            [[1.0, 0.0, 20.0], [1.0, 1.0, 30.0]],
        ],
        "weights": [[1.0, 1.0], [1.0, 1.0]],
        "knots_u": [0.0, 0.0, 1.0, 1.0],
        "knots_v": [0.0, 0.0, 1.0, 1.0],
    }

    assert evaluate_nurbs_surface(surface, 0.5, 0.5) == [0.5, 0.5, 15.0]


def test_v11_defaults_translate_to_canonical_nurbs_payload():
    parameters, defaults = _runtime()
    canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)

    assert canonical["canonical_payload_version"] == "1.1.2"
    assert canonical["canonical_input_source"] == "translated_from_legacy_v1_1"
    assert canonical["support_profiles"]["hub_profile"]["kind"] == "nurbs_curve"
    assert canonical["support_profiles"]["tip_or_shroud_profile"]["kind"] == "nurbs_curve"
    assert canonical["blade_population"]["main_blade_count"] == 8
    assert canonical["blade_population"]["splitter_blade_count"] == 8
    assert canonical["blade_skeleton_field"]["kind"] == "nurbs_surface"
    assert canonical["thickness_field"]["kind"] == "nurbs_surface"
    assert canonical["section_loop_family"]["mode"] == "skeleton_thickness_caps"
    assert canonical["section_loop_family"]["segments"]["leading_edge_cap"]["kind"] == "nurbs_cap_curve"
    assert canonical["metrics"]["support_profile_control_count"]["hub_profile"] == 6
    assert canonical["metrics"]["thickness_min_mm"] > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v11_2_canonical'`.

- [ ] **Step 3: Implement the canonical module**

Create `src/part_rule_synthesis/impeller_v11_2_canonical.py` with these public functions:

```python
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any


MATH_PARAMETERIZATION = "v1_1_2_canonical_nurbs_parameterization"
CANONICAL_PAYLOAD_VERSION = "1.1.2"


def clamped_uniform_knots(point_count: int, degree: int) -> list[float]:
    if point_count <= 0:
        raise ValueError("point_count must be positive")
    safe_degree = min(max(int(degree), 1), point_count - 1)
    interior_count = point_count - safe_degree - 1
    knots = [0.0 for _ in range(safe_degree + 1)]
    for index in range(1, interior_count + 1):
        knots.append(round(index / (interior_count + 1), 6))
    knots.extend(1.0 for _ in range(safe_degree + 1))
    return knots


def evaluate_nurbs_curve(curve: dict[str, Any], u: float) -> list[float]:
    points = [[float(value) for value in point] for point in curve["control_points"]]
    weights = [float(value) for value in curve.get("weights", [1.0] * len(points))]
    degree = int(curve["degree"])
    knots = [float(value) for value in curve["knots"]]
    basis = [_basis(index, degree, _clamp01(u), knots) for index in range(len(points))]
    denominator = sum(basis[index] * weights[index] for index in range(len(points)))
    if abs(denominator) <= 1.0e-12:
        raise ValueError("NURBS curve denominator is zero")
    dimensions = len(points[0])
    return [
        _round(
            sum(basis[index] * weights[index] * points[index][axis] for index in range(len(points)))
            / denominator
        )
        for axis in range(dimensions)
    ]


def evaluate_nurbs_surface(surface: dict[str, Any], u: float, v: float) -> list[float]:
    grid = surface["control_points"]
    degree_u = int(surface["degree_u"])
    degree_v = int(surface["degree_v"])
    knots_u = [float(value) for value in surface["knots_u"]]
    knots_v = [float(value) for value in surface["knots_v"]]
    weights = surface.get("weights") or [[1.0 for _ in row] for row in grid]
    basis_u = [_basis(index, degree_u, _clamp01(u), knots_u) for index in range(len(grid))]
    basis_v = [_basis(index, degree_v, _clamp01(v), knots_v) for index in range(len(grid[0]))]
    dimensions = len(grid[0][0])
    denominator = 0.0
    numerator = [0.0 for _ in range(dimensions)]
    for i, row in enumerate(grid):
        for j, point in enumerate(row):
            coefficient = basis_u[i] * basis_v[j] * float(weights[i][j])
            denominator += coefficient
            for axis in range(dimensions):
                numerator[axis] += coefficient * float(point[axis])
    if abs(denominator) <= 1.0e-12:
        raise ValueError("NURBS surface denominator is zero")
    return [_round(value / denominator) for value in numerator]


def canonical_nurbs_from_v11_defaults(
    parameters: Mapping[str, Any],
    defaults: Mapping[str, Any],
    *,
    source: str = "translated_from_legacy_v1_1",
) -> dict[str, Any]:
    hub_points = _profile_points(defaults["hub_profile_rz_mm"])
    tip_points = _profile_points(defaults["tip_or_shroud_profile_rz_mm"])
    average_thickness = _float_default(defaults, "average_blade_thickness_mm", _parameter_value(parameters, "blade_thickness_mm", 1.0))
    maximum_thickness = _float_default(defaults, "maximum_blade_thickness_mm", max(average_thickness, _parameter_value(parameters, "blade_thickness_mm", average_thickness)))
    span_stations = [float(value) for value in defaults.get("span_stations_h", [0.0, 0.25, 0.5, 0.75, 1.0])]
    skeleton = _skeleton_field(defaults)
    thickness = _thickness_field(defaults, average_thickness, maximum_thickness)
    root_offset = _float_default(defaults, "root_blade_lift_mm", _float_default(defaults, "root_attachment_lift_mm", average_thickness))
    tip_offset = _float_default(defaults, "shroud_blade_inset_mm", 0.0) if defaults.get("tip_attachment_mode") == "closed_shroud_attachment" else 0.0
    payload = {
        "canonical_payload_version": CANONICAL_PAYLOAD_VERSION,
        "math_parameterization": MATH_PARAMETERIZATION,
        "canonical_input_source": source,
        "support_profiles": {
            "hub_profile": _nurbs_curve("hub_profile", hub_points),
            "tip_or_shroud_profile": _nurbs_curve("tip_or_shroud_profile", tip_points),
        },
        "active_span_policy": {
            "root_offset": {"mode": "thickness_ratio", "ratio_of_local_thickness": _round(root_offset / max(average_thickness, 1.0e-9)), "resolved_constant_mm": _round(root_offset)},
            "tip_offset": {"mode": "closed_shroud_thickness_ratio_or_open_zero", "ratio_of_local_thickness": _round(tip_offset / max(average_thickness, 1.0e-9)), "resolved_constant_mm": _round(tip_offset)},
            "report_resolved_offsets": True,
        },
        "blade_population": {
            "main_blade_count": int(defaults["main_blade_count"]),
            "splitter_blade_count": int(defaults.get("splitter_blade_count", 0)),
            "splitter_positioning_mode": str(defaults.get("splitter_positioning_mode", "main_passage_bisector")),
            "splitter_passage_fraction": float(defaults.get("splitter_passage_fraction", 0.5)),
            "main_streamwise_interval_s": list(defaults.get("main_streamwise_interval_s", [0.06, 0.94])),
            "splitter_streamwise_interval_s": list(defaults.get("splitter_streamwise_interval_s", [0.35, 0.88])),
            "splitter_phase_offset_pitch": float(defaults.get("splitter_phase_offset_pitch", 0.5)),
        },
        "blade_skeleton_field": skeleton,
        "thickness_field": thickness,
        "section_loop_family": {
            "mode": "skeleton_thickness_caps",
            "span_stations_h": span_stations,
            "segments": {
                "pressure_side": {"construction": "skeleton_minus_half_thickness"},
                "suction_side": {"construction": "skeleton_plus_half_thickness"},
                "leading_edge_cap": _cap_intent(defaults, "leading_edge_cap_roundness"),
                "trailing_edge_cap": _cap_intent(defaults, "trailing_edge_cap_roundness"),
            },
        },
        "attachment_policy": _attachment_policy(defaults, average_thickness),
        "pose_field": _pose_field(parameters, defaults),
        "sampling_policy": _sampling_policy(defaults),
    }
    payload["metrics"] = _canonical_metrics(payload, average_thickness, maximum_thickness)
    return payload
```

The same file must define the private helpers referenced above. Use only standard-library math and lists. For `_basis`, reuse the Cox-de Boor form already used in `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`, but keep this module self-contained.

- [ ] **Step 4: Run tests and make them pass**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/part_rule_synthesis/impeller_v11_2_canonical.py tests/test_impeller_v11_2_canonical_parameterization.py
git commit -m "feat: add v1.1.2 canonical nurbs payload"
```

---

### Task 2: Runtime Compiler And Preset Translation

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_constants.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/*.json`
- Test: `tests/test_impeller_v11_2_preset_translation.py`
- Modify tests: `tests/test_impeller_v11_resources.py`

**Interfaces:**
- Consumes: `canonical_nurbs_from_v11_defaults(...)` from Task 1.
- Produces runtime keys:
  - `geometry_patch_version == "1.1.2"`
  - `math_parameterization == "v1_1_2_canonical_nurbs_parameterization"`
  - `canonical_nurbs_parameterization`
  - `canonical_input_source == "translated_from_legacy_v1_1"`

- [ ] **Step 1: Write failing preset translation tests**

Create `tests/test_impeller_v11_2_preset_translation.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


ACTIVE_V11_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def test_all_active_v11_presets_compile_to_v112_canonical_payloads():
    for preset_id in ACTIVE_V11_PRESETS:
        runtime = compile_impeller_runtime_preset(preset_id)
        canonical = runtime["canonical_nurbs_parameterization"]

        assert runtime["geometry_version"] == "1.1"
        assert runtime["geometry_patch_version"] == "1.1.2"
        assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
        assert runtime["canonical_input_source"] == "translated_from_legacy_v1_1"
        assert canonical["canonical_payload_version"] == "1.1.2"
        assert canonical["blade_population"]["main_blade_count"] > 0
        assert canonical["blade_population"]["main_blade_count"] + canonical["blade_population"]["splitter_blade_count"] == runtime["parameters"]["blade_count"]["default"]
        assert canonical["section_loop_family"]["mode"] == "skeleton_thickness_caps"


def test_open_and_closed_translation_preserve_topology_modes():
    open_runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    closed_runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")

    assert open_runtime["canonical_nurbs_parameterization"]["attachment_policy"]["open_tip"]["enabled_when"] == "open"
    assert closed_runtime["canonical_nurbs_parameterization"]["attachment_policy"]["tip_to_shroud"]["enabled_when"] == "closed"
    assert closed_runtime["canonical_nurbs_parameterization"]["blade_population"]["splitter_blade_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_preset_translation.py -q
```

Expected: FAIL because runtime does not yet include `canonical_nurbs_parameterization`.

- [ ] **Step 3: Update constants**

Modify `src/part_rule_synthesis/impeller_v11_constants.py`:

```python
GEOMETRY_PATCH_VERSION = "1.1.2"
MATH_PARAMETERIZATION = "v1_1_2_canonical_nurbs_parameterization"
```

Keep `GEOMETRY_VERSION`, `TRANSITION_GEOMETRY_STATUS`, `MESH_STRATEGY`, and `SOURCE_KERNEL` unchanged.

- [ ] **Step 4: Update runtime compiler**

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, import:

```python
from part_rule_synthesis.impeller_v11_2_canonical import (
    MATH_PARAMETERIZATION as V11_2_MATH_PARAMETERIZATION,
    canonical_nurbs_from_v11_defaults,
)
```

Inside `_v11_runtime_defaults`, after `defaults` is validated, add:

```python
canonical = canonical_nurbs_from_v11_defaults(parameters, defaults)
```

Return these additional keys:

```python
"geometry_patch_version": preset.get("geometry_patch_version", "1.1.2"),
"math_parameterization": preset.get("math_parameterization", V11_2_MATH_PARAMETERIZATION),
"canonical_input_source": canonical["canonical_input_source"],
"canonical_nurbs_parameterization": canonical,
```

Preserve `resolved_blade_to_blade_loop_family_defaults` for compatibility.

- [ ] **Step 5: Update active V1.1 preset JSON files**

For each active file under `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets/`, set:

```json
"geometry_patch_version": "1.1.2",
"math_parameterization": "v1_1_2_canonical_nurbs_parameterization",
"canonical_input_source": "translated_from_legacy_v1_1"
```

Do not rename preset ids.

- [ ] **Step 6: Update existing V1.1 resource tests**

Update `tests/test_impeller_v11_resources.py` expected patch values from `"1.1.1"` to `"1.1.2"`, and add:

```python
assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
assert "canonical_nurbs_parameterization" in runtime
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_2_preset_translation.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```powershell
git add src/part_rule_synthesis/impeller_v11_constants.py src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/presets tests/test_impeller_v11_resources.py tests/test_impeller_v11_2_preset_translation.py
git commit -m "feat: translate v1.1 presets to v1.1.2 canonical payloads"
```

---

### Task 3: Loop Builder Uses Canonical Active Span, Skeleton, Thickness, And NURBS Caps

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`
- Test: `tests/test_impeller_v11_2_active_span_policy.py`
- Test: `tests/test_impeller_v11_2_nurbs_loop_caps.py`

**Interfaces:**
- Consumes: `defaults["canonical_nurbs_parameterization"]` when present.
- Produces:
  - loop family key `canonical_nurbs_parameterization`
  - loop family key `active_span_policy_metrics`
  - per-loop cap metadata under `segments[segment]["canonical_curve"]`
  - per-loop metrics for `leading_cap_sagitta_target_mm`, `leading_cap_sagitta_resolved_mm`, `trailing_cap_sagitta_target_mm`, `trailing_cap_sagitta_resolved_mm`

- [ ] **Step 1: Write failing active span policy tests**

Create `tests/test_impeller_v11_2_active_span_policy.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def _runtime(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    return runtime, parameters


def test_active_span_policy_offsets_root_loop_from_hub_support():
    runtime, parameters = _runtime("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    defaults = {**defaults, "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"]}
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_root_offset_max_mm"] >= metrics["resolved_root_offset_min_mm"]
    assert metrics["resolved_tip_offset_max_mm"] == 0.0
    assert family["blades"][0]["loops"][0]["h"] == 0.0
    assert family["blades"][0]["loops"][0]["active_span_fraction"] > 0.0


def test_closed_active_span_policy_offsets_tip_from_shroud_support():
    runtime, parameters = _runtime("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]
    defaults = {**defaults, "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"]}
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)

    metrics = family["active_span_policy_metrics"]
    assert metrics["resolved_root_offset_min_mm"] > 0.0
    assert metrics["resolved_tip_offset_min_mm"] > 0.0
    assert metrics["offset_feasibility_status"] == "PASS"
```

- [ ] **Step 2: Write failing cap NURBS tests**

Create `tests/test_impeller_v11_2_nurbs_loop_caps.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import build_v11_blade_to_blade_loop_family


def test_leading_and_trailing_edges_report_nurbs_cap_intent_and_sagitta():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    family = build_v11_blade_to_blade_loop_family(parameters, defaults)
    loop = family["blades"][0]["loops"][0]

    for segment_name in ["leading_edge", "trailing_edge"]:
        segment = loop["segments"][segment_name]
        assert segment["canonical_curve"]["kind"] == "nurbs_cap_curve"
        assert segment["canonical_curve"]["sagitta_policy"]["mode"] == "local_thickness_ratio"
        assert segment["canonical_curve"]["resolved_sagitta_mm"] > 0.0
        assert segment["canonical_curve"]["continuity_goal"] == "C2"

    assert loop["metrics"]["leading_cap_sagitta_resolved_mm"] > 0.0
    assert loop["metrics"]["trailing_cap_sagitta_resolved_mm"] > 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py -q
```

Expected: FAIL because `active_span_policy_metrics` and `canonical_curve` metadata do not exist.

- [ ] **Step 4: Thread canonical payload through `_validated_defaults`**

In `src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py`, import:

```python
from part_rule_synthesis.impeller_v11_2_canonical import evaluate_nurbs_surface
```

In `_validated_defaults`, add:

```python
canonical = values.get("canonical_nurbs_parameterization")
if isinstance(canonical, Mapping):
    values["canonical_nurbs_parameterization"] = copy.deepcopy(canonical)
    population = canonical.get("blade_population", {})
    values["span_stations_h"] = _float_list(
        canonical.get("section_loop_family", {}).get("span_stations_h", values["span_stations_h"]),
        "span_stations_h",
    )
    values["main_blade_count"] = _int_value(population.get("main_blade_count", values["main_blade_count"]))
    values["splitter_blade_count"] = _int_value(population.get("splitter_blade_count", values["splitter_blade_count"]), minimum=None)
    values["main_streamwise_interval_s"] = _pair(population.get("main_streamwise_interval_s", values["main_streamwise_interval_s"]))
    values["splitter_streamwise_interval_s"] = _pair(population.get("splitter_streamwise_interval_s", values["splitter_streamwise_interval_s"]))
    values["splitter_phase_offset_pitch"] = float(population.get("splitter_phase_offset_pitch", values["splitter_phase_offset_pitch"]))
```

- [ ] **Step 5: Resolve active span metrics**

Add helper:

```python
def _active_span_policy_metrics(values: Mapping[str, Any]) -> dict[str, Any]:
    canonical = values.get("canonical_nurbs_parameterization") or {}
    active_policy = canonical.get("active_span_policy") or {}
    root_offset = float(active_policy.get("root_offset", {}).get("resolved_constant_mm", values.get("root_blade_lift_mm", 0.0)))
    tip_offset = float(active_policy.get("tip_offset", {}).get("resolved_constant_mm", values.get("shroud_blade_inset_mm", 0.0 if values.get("tip_attachment_mode") != "closed_shroud_attachment" else values.get("root_blade_lift_mm", 0.0))))
    status = "PASS" if root_offset >= 0.0 and tip_offset >= 0.0 and root_offset + tip_offset < 0.9 * _minimum_span_length(values) else "FAIL"
    return {
        "resolved_root_offset_min_mm": _round(root_offset),
        "resolved_root_offset_max_mm": _round(root_offset),
        "resolved_tip_offset_min_mm": _round(tip_offset),
        "resolved_tip_offset_max_mm": _round(tip_offset),
        "offset_feasibility_status": status,
    }
```

Use this metric in `build_v11_blade_to_blade_loop_family`:

```python
active_span_policy_metrics = _active_span_policy_metrics(values)
...
"active_span_policy_metrics": active_span_policy_metrics,
```

- [ ] **Step 6: Use canonical skeleton and thickness fields**

In `_sample_side_points`, before the current scalar camber/thickness fallback, add:

```python
canonical = values.get("canonical_nurbs_parameterization") or {}
skeleton_field = canonical.get("blade_skeleton_field")
thickness_field = canonical.get("thickness_field")
if isinstance(skeleton_field, Mapping) and isinstance(thickness_field, Mapping):
    skeleton_sample = evaluate_nurbs_surface(dict(skeleton_field), s_norm, h)
    thickness_sample = evaluate_nurbs_surface(dict(thickness_field), s_norm, h)
    camber_q = float(skeleton_sample[2])
    local_thickness = max(1.0e-9, float(thickness_sample[2]))
else:
    camber_q = _camber_q(...)
    local_thickness = thickness_mm * (0.75 + 0.25 * math.sin(...))
q = camber_q + sign * 0.5 * local_thickness
```

Keep the old scalar path for legacy and malformed tests.

- [ ] **Step 7: Attach cap metadata**

In `_loop_segments_s_q`, after `leading_points` and `trailing_points`, compute:

```python
leading_sagitta = _cap_sagitta_mm(pressure_points[0], suction_points[0], float(values["streamwise_metric_scale_mm"]))
trailing_sagitta = _cap_sagitta_mm(suction_points[-1], pressure_points[-1], float(values["streamwise_metric_scale_mm"]))
```

Add `canonical_curve` to leading/trailing segment dictionaries:

```python
"canonical_curve": {
    "kind": "nurbs_cap_curve",
    "coordinate_system": "s_q_mm",
    "sagitta_policy": {"mode": "local_thickness_ratio", "ratio": 0.5},
    "resolved_sagitta_mm": _round(leading_sagitta),
    "continuity_goal": "C2",
}
```

Add loop-level metrics in `_build_loop`:

```python
"leading_cap_sagitta_resolved_mm": segments_s_q["leading_edge"]["canonical_curve"]["resolved_sagitta_mm"],
"trailing_cap_sagitta_resolved_mm": segments_s_q["trailing_edge"]["canonical_curve"]["resolved_sagitta_mm"],
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```powershell
git add src/part_rule_synthesis/impeller_v11_blade_to_blade_loop.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py
git commit -m "feat: drive v1.1 loops from canonical nurbs fields"
```

---

### Task 4: Surface Graph, Manifest, And Validation Compatibility

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v11_surface_family.py`
- Modify: `src/part_rule_synthesis/impeller_v11_validation.py`
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_v11_2_surface_graph_compatibility.py`
- Modify tests: `tests/test_impeller_v11_six_face_surface_family.py`, `tests/test_impeller_v11_mesh_and_export_contract.py`

**Interfaces:**
- Consumes: runtime graph with canonical payload.
- Produces:
  - `surface_graph["canonical_nurbs_parameterization"]`
  - `surface_graph["math_parameterization"]`
  - `surface_graph["canonical_metrics"]`
  - manifest-visible same keys under `manifest["geometry"]["surface_graph"]` and top-level `manifest["geometry_patch_version"]`.

- [ ] **Step 1: Write failing surface graph compatibility tests**

Create `tests/test_impeller_v11_2_surface_graph_compatibility.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph
from part_rule_synthesis.service import RuleSynthesisService


def _graph(preset_id: str = "radial_open_reference_v1_1"):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_v112_surface_graph_preserves_v11_face_family_roles():
    graph = _graph()
    roles = {surface["role"] for surface in graph["surfaces"]}

    assert graph["geometry_patch_version"] == "1.1.2"
    assert graph["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
    assert graph["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"
    assert "blade_pressure" in roles
    assert "blade_suction" in roles
    assert "blade_leading_edge" in roles
    assert "blade_trailing_edge" in roles
    assert "root_to_hub_attachment" in roles
    assert "open_tip_dome" in roles


def test_v112_service_manifest_exposes_canonical_parameterization(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_1")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]

    assert manifest["geometry_patch_version"] == "1.1.2"
    assert graph["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"
    assert graph["canonical_metrics"]["thickness_min_mm"] > 0.0
    assert manifest["geometry_validation_status"] == "PASS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Expected: FAIL because surface graph and manifest do not expose canonical fields yet.

- [ ] **Step 3: Update `build_v11_surface_graph` to preserve canonical fields**

In `src/part_rule_synthesis/impeller_v11_surface_family.py`, before calling the loop builder:

```python
canonical = resolved_defaults.get("canonical_nurbs_parameterization")
```

When returning graph, include:

```python
"math_parameterization": canonical.get("math_parameterization") if isinstance(canonical, dict) else "v1_1_2_canonical_nurbs_parameterization",
"canonical_nurbs_parameterization": copy.deepcopy(canonical) if isinstance(canonical, dict) else {},
"canonical_metrics": copy.deepcopy(canonical.get("metrics", {})) if isinstance(canonical, dict) else {},
```

Keep `transition_geometry_status` and face roles unchanged.

- [ ] **Step 4: Update validators for patch `1.1.2`**

In `src/part_rule_synthesis/impeller_v11_validation.py`, replace the strict equality check:

```python
if surface_graph.get("geometry_patch_version") != GEOMETRY_PATCH_VERSION:
```

with:

```python
if surface_graph.get("geometry_patch_version") not in {"1.1.0", "1.1.1", "1.1.2"}:
```

Then add V1.1.2 canonical checks only when patch is `"1.1.2"`:

```python
if surface_graph.get("geometry_patch_version") == "1.1.2":
    canonical = surface_graph.get("canonical_nurbs_parameterization")
    if not isinstance(canonical, dict):
        failures.append(_failure("v1_1_2_canonical_payload_missing"))
    elif canonical.get("canonical_payload_version") != "1.1.2":
        failures.append(_failure("v1_1_2_canonical_payload_missing"))
```

In `src/part_rule_synthesis/impeller_geometry_validation.py`, change:

```python
if graph.get("geometry_patch_version") in {"1.1.0", "1.1.1"}:
```

to:

```python
if graph.get("geometry_patch_version") in {"1.1.0", "1.1.1", "1.1.2"}:
```

- [ ] **Step 5: Update service routing allowlists**

In `src/part_rule_synthesis/service.py`, update V1.1.1 checks to include `"1.1.2"` wherever export and mesh routing currently has:

```python
surface_graph.get("geometry_patch_version") in {"1.1.0", "1.1.1"}
```

The replacement is:

```python
surface_graph.get("geometry_patch_version") in {"1.1.0", "1.1.1", "1.1.2"}
```

- [ ] **Step 6: Update existing V1.1 tests**

Update existing V1.1 tests that assert `"1.1.1"` as the current patch. Use `"1.1.2"` where they test active current presets. Keep historical V1.1.1 evidence files unchanged.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_surface_graph_compatibility.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_mesh_and_export_contract.py tests/test_impeller_geometry_validation.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add src/part_rule_synthesis/impeller_v11_surface_family.py src/part_rule_synthesis/impeller_v11_validation.py src/part_rule_synthesis/impeller_geometry_validation.py src/part_rule_synthesis/service.py tests/test_impeller_v11_2_surface_graph_compatibility.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_mesh_and_export_contract.py
git commit -m "feat: expose v1.1.2 canonical payload in surface graphs"
```

---

### Task 5: Frontend Canonical Defaults And Parameter View Model

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`
- Create: `frontend/src/parameterViewModel.js`
- Test: `frontend/src/parameterViewModel.test.js`

**Interfaces:**
- Consumes: active preset `canonicalNurbsParameterization` and generated manifest `geometry.surface_graph.canonical_nurbs_parameterization`.
- Produces:
  - `canonicalParameterizationForPreset(presetRef) -> object`
  - `resolvedCanonicalParameterization(activePreset, manifest) -> { sourceLabel, canonical }`
  - `parameterViewTabs(activePreset, manifest) -> Array<{ id, label, annotations }>`

- [ ] **Step 1: Write failing frontend model tests**

Create `frontend/src/parameterViewModel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { presets } from "./appModel.js";
import {
  parameterViewTabs,
  resolvedCanonicalParameterization,
} from "./parameterViewModel.js";

describe("V1.1.2 parameter view model", () => {
  test("uses preset canonical defaults before generation", () => {
    const preset = presets[0];
    const resolved = resolvedCanonicalParameterization(preset, null);

    assert.equal(resolved.sourceLabel, "preset defaults");
    assert.equal(resolved.canonical.canonical_payload_version, "1.1.2");
    assert.equal(resolved.canonical.math_parameterization, "v1_1_2_canonical_nurbs_parameterization");
  });

  test("uses manifest canonical data after generation", () => {
    const preset = presets[0];
    const manifest = {
      geometry: {
        surface_graph: {
          canonical_nurbs_parameterization: {
            canonical_payload_version: "1.1.2",
            math_parameterization: "v1_1_2_canonical_nurbs_parameterization",
            canonical_input_source: "translated_from_frontend_handles",
            support_profiles: { hub_profile: { control_points: [[1, 2]] }, tip_or_shroud_profile: { control_points: [[3, 4]] } },
            active_span_policy: { root_offset: { resolved_constant_mm: 14 }, tip_offset: { resolved_constant_mm: 0 } },
            blade_population: { main_blade_count: 8, splitter_blade_count: 8 },
            section_loop_family: { span_stations_h: [0, 0.25, 0.5, 0.75, 1] },
          },
        },
      },
    };

    const resolved = resolvedCanonicalParameterization(preset, manifest);
    assert.equal(resolved.sourceLabel, "resolved manifest");
    assert.equal(resolved.canonical.canonical_input_source, "translated_from_frontend_handles");
  });

  test("returns top meridional blade-to-blade and span station tabs", () => {
    const tabs = parameterViewTabs(presets[0], null);

    assert.deepEqual(tabs.map((tab) => tab.id), ["top", "meridional", "blade_to_blade", "span_station"]);
    assert.ok(tabs.every((tab) => tab.annotations.length > 0));
  });
});
```

Update `frontend/src/appModel.test.js`:

```javascript
test("v1.1.2 frontend presets expose canonical parameterization defaults", () => {
  const open = presets[0];
  assert.equal(open.geometryPatchVersion, "1.1.2");
  assert.equal(open.canonicalNurbsParameterization.canonical_payload_version, "1.1.2");
  assert.equal(open.canonicalNurbsParameterization.blade_population.main_blade_count, 8);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: FAIL because `parameterViewModel.js` and preset canonical defaults do not exist.

- [ ] **Step 3: Add frontend canonical defaults**

In `frontend/src/appModel.js`, add a helper mirroring backend translation shape:

```javascript
function v112CanonicalFromPreset({ parameters, profileOverrides, loopFamilyDefaults }) {
  const hub = profileOverrides?.hub_profile?.control_points || [];
  const tip = profileOverrides?.tip_or_shroud_profile?.control_points || [];
  return {
    canonical_payload_version: "1.1.2",
    math_parameterization: "v1_1_2_canonical_nurbs_parameterization",
    canonical_input_source: "translated_from_legacy_v1_1",
    support_profiles: {
      hub_profile: profile(hub),
      tip_or_shroud_profile: profile(tip),
    },
    active_span_policy: {
      root_offset: { mode: "thickness_ratio", resolved_constant_mm: loopFamilyDefaults.root_attachment_lift_mm || parameters.root_fillet_radius_mm || 0 },
      tip_offset: { mode: "closed_shroud_thickness_ratio_or_open_zero", resolved_constant_mm: loopFamilyDefaults.shroud_blade_inset_mm || 0 },
    },
    blade_population: { ...loopFamilyDefaults },
    section_loop_family: {
      mode: "skeleton_thickness_caps",
      span_stations_h: loopFamilyDefaults.span_stations_h || [0, 0.25, 0.5, 0.75, 1],
    },
  };
}
```

For each active preset, set:

```javascript
geometryPatchVersion: "1.1.2",
metadata: { ...v111Metadata(), geometryPatchVersion: "1.1.2", mathParameterization: "v1_1_2_canonical_nurbs_parameterization" },
canonicalNurbsParameterization: v112CanonicalFromPreset(...),
```

Keep `presetId` unchanged.

- [ ] **Step 4: Implement `parameterViewModel.js`**

Create `frontend/src/parameterViewModel.js`:

```javascript
export function resolvedCanonicalParameterization(activePreset, manifest) {
  const manifestCanonical = manifest?.geometry?.surface_graph?.canonical_nurbs_parameterization;
  if (manifestCanonical?.canonical_payload_version === "1.1.2") {
    return { sourceLabel: "resolved manifest", canonical: clonePlainObject(manifestCanonical) };
  }
  return {
    sourceLabel: "preset defaults",
    canonical: clonePlainObject(activePreset?.canonicalNurbsParameterization || {}),
  };
}

export function parameterViewTabs(activePreset, manifest) {
  const { canonical, sourceLabel } = resolvedCanonicalParameterization(activePreset, manifest);
  return [
    { id: "top", label: "Top", sourceLabel, annotations: topAnnotations(canonical) },
    { id: "meridional", label: "Meridional", sourceLabel, annotations: meridionalAnnotations(canonical) },
    { id: "blade_to_blade", label: "S-Q", sourceLabel, annotations: bladeToBladeAnnotations(canonical) },
    { id: "span_station", label: "Span", sourceLabel, annotations: spanAnnotations(canonical) },
  ];
}
```

Implement annotation helpers to return arrays of `{ label, value, kind }`:

```javascript
function topAnnotations(canonical) {
  const population = canonical?.blade_population || {};
  return [
    { kind: "population", label: "Main blades", value: population.main_blade_count ?? "unset" },
    { kind: "population", label: "Splitter blades", value: population.splitter_blade_count ?? "unset" },
    { kind: "population", label: "Splitter fraction", value: population.splitter_passage_fraction ?? "unset" },
  ];
}
```

Use similar compact helpers for support profile control counts, active span offsets, and span stations.

- [ ] **Step 5: Run frontend focused tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add frontend/src/appModel.js frontend/src/appModel.test.js frontend/src/parameterViewModel.js frontend/src/parameterViewModel.test.js
git commit -m "feat: add v1.1.2 frontend canonical parameter model"
```

---

### Task 6: Frontend Parameter Views Panel And App Integration

**Files:**
- Create: `frontend/src/components/ParameterViewsPanel.js`
- Test: `frontend/src/components/ParameterViewsPanel.test.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/appFiles.test.js`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `parameterViewTabs(activePreset, manifest)` from Task 5.
- Produces: React component `ParameterViewsPanel({ activePreset, manifest })`.
- Non-mutating: component accepts no geometry edit callbacks.

- [ ] **Step 1: Write failing component tests**

Create `frontend/src/components/ParameterViewsPanel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..", "..");
const componentPath = resolve(root, "src/components/ParameterViewsPanel.js");

describe("ParameterViewsPanel source contract", () => {
  test("component exists and renders the Parameter views tab label", () => {
    assert.equal(existsSync(componentPath), true);
    const source = readFileSync(componentPath, "utf-8");
    assert.match(source, /Parameter views/);
    assert.match(source, /parameterViewTabs/);
  });

  test("component is inspection-only and does not accept mutation callbacks", () => {
    const source = readFileSync(componentPath, "utf-8");
    assert.doesNotMatch(source, /onChange/);
    assert.doesNotMatch(source, /onParameter/);
    assert.doesNotMatch(source, /setGeometry/);
  });
});
```

Update `frontend/src/appFiles.test.js`:

```javascript
test("application includes V1.1.2 parameter views panel", () => {
  const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
  assert.match(appSource, /ParameterViewsPanel/);
  assert.match(appSource, /activePreset=\{activePreset\}/);
  assert.match(appSource, /manifest=\{manifest\}/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: FAIL because `ParameterViewsPanel.js` does not exist.

- [ ] **Step 3: Implement `ParameterViewsPanel`**

Create `frontend/src/components/ParameterViewsPanel.js`:

```javascript
import React, { useMemo, useState } from "react";

import { parameterViewTabs } from "../parameterViewModel.js?v=1.1.6";

const h = React.createElement;

export function ParameterViewsPanel({ activePreset, manifest }) {
  const tabs = useMemo(() => parameterViewTabs(activePreset, manifest), [activePreset, manifest]);
  const [selectedId, setSelectedId] = useState(tabs[0]?.id || "top");
  const selected = tabs.find((tab) => tab.id === selectedId) || tabs[0];

  return h(
    "section",
    { className: "panel-section parameter-views-panel" },
    h("div", { className: "section-title" }, "Parameter views"),
    h(
      "div",
      { className: "parameter-view-tabs" },
      tabs.map((tab) =>
        h(
          "button",
          {
            key: tab.id,
            type: "button",
            className: selected?.id === tab.id ? "active" : "",
            onClick: () => setSelectedId(tab.id),
          },
          tab.label,
        ),
      ),
    ),
    selected
      ? h(
          "div",
          { className: `parameter-view parameter-view-${selected.id}` },
          h("p", { className: "small-note" }, `Source: ${selected.sourceLabel}`),
          h(
            "dl",
            { className: "annotation-list" },
            selected.annotations.map((item) => [
              h("dt", { key: `${item.label}-label` }, item.label),
              h("dd", { key: `${item.label}-value` }, String(item.value)),
            ]),
          ),
        )
      : h("p", { className: "empty-state" }, "No canonical parameterization available."),
  );
}
```

- [ ] **Step 4: Integrate in `App.js`**

Add import:

```javascript
import { ParameterViewsPanel } from "./components/ParameterViewsPanel.js?v=1.1.6";
```

Render it in the left panel after `CurveControlPanel` and before `GeometryLayerPanel`:

```javascript
h(ParameterViewsPanel, {
  activePreset,
  manifest,
}),
```

Do not pass `onChange` or any setter.

- [ ] **Step 5: Add compact styles**

In `frontend/src/styles.css`, add:

```css
.parameter-views-panel {
  display: grid;
  gap: 10px;
}

.parameter-view-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.parameter-view-tabs button {
  min-height: 34px;
}

.parameter-view-tabs button.active {
  border-color: #0f766e;
  background: #ecfdf5;
}

.annotation-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  margin: 0;
}

.annotation-list dt,
.annotation-list dd {
  margin: 0;
  font-size: 12px;
}

.annotation-list dt {
  color: #52635e;
}
```

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```powershell
git add frontend/src/App.js frontend/src/appFiles.test.js frontend/src/components/ParameterViewsPanel.js frontend/src/components/ParameterViewsPanel.test.js frontend/src/styles.css
git commit -m "feat: add v1.1.2 parameter views panel"
```

---

### Task 7: End-To-End Verification And Evidence

**Files:**
- Modify: `docs/evidence/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-evidence.md`
- Modify: `docs/version-history.md` only if implementation details differ from the spec.

**Interfaces:**
- Consumes: tasks 1-6.
- Produces: final verification transcript and implementation evidence.

- [ ] **Step 1: Run backend V1.1.2 tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Expected: PASS.

- [ ] **Step 2: Run V1.1 regression tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run geometry validation smoke**

Run:

```powershell
python -m pytest tests/test_impeller_geometry_validation.py -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS with all Node tests.

- [ ] **Step 5: Run all-five-preset service smoke**

Run this PowerShell script from repo root:

```powershell
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

presets = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]
service = RuleSynthesisService(Path(".tmp-v112-smoke"), model_output_root=Path(".tmp-v112-smoke") / "Model Output")
for preset_id in presets:
    engine = service.synthesize("impeller", preset_id=preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]
    print(
        preset_id,
        manifest["geometry_patch_version"],
        graph["canonical_nurbs_parameterization"]["canonical_payload_version"],
        manifest["geometry_validation_status"],
        run.run_id,
    )
'@ | python -
```

Expected: five lines, each containing `1.1.2 1.1.2 PASS`.

- [ ] **Step 6: Append evidence**

Append a verification section to `docs/evidence/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-evidence.md`.

The section must include:

- the exact backend V1.1.2 pytest command from Step 1;
- the exact V1.1 regression pytest command from Step 2;
- the exact frontend `npm.cmd test` command from Step 3;
- the exact five-preset smoke command from Step 5;
- the actual stdout/stderr observed for each command in this implementation run.

Record failures exactly if any verification command fails, stop implementation, and do not claim completion. Do not replace command output with a summary-only statement such as `passed`.

- [ ] **Step 7: Check git status and commit evidence**

Run:

```powershell
git status --short --branch
git diff --check
```

Expected: only intended docs changes are unstaged or staged; `git diff --check` has no output.

Commit:

```powershell
git add docs/evidence/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-evidence.md docs/version-history.md
git commit -m "docs: record v1.1.2 canonical parameterization evidence"
```

---

## Final Verification Matrix

Run these before claiming V1.1.2 implementation complete:

```powershell
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_mesh_and_export_contract.py -q
python -m pytest tests/test_impeller_geometry_validation.py -q
cd frontend
npm.cmd test
```

Manual frontend acceptance:

- Open `http://127.0.0.1:5199`.
- Select the open V1.1 preset.
- Generate model.
- Confirm `Parameter views` appears.
- Confirm `Parameter views` shows preset defaults before generation and resolved manifest data after generation.
- Confirm the panel does not change geometry payload.
- Confirm normal viewer modes still render V1.1.1 all-surface shaded/wire/mesh behavior.

## Self-Review

Spec coverage:

- Canonical NURBS payload: Task 1.
- Preset translation and patch version: Task 2.
- Active span policy and non-raw-hub `h=0`: Task 3.
- NURBS edge caps with rounded-cap intent: Task 3.
- Surface graph and manifest compatibility: Task 4.
- Frontend multi-view parameter annotation tab: Tasks 5 and 6.
- Evidence and verification: Task 7.

Output-template scan:

- No task contains unresolved angle-bracket output markers.
- Evidence append step requires actual command output from this implementation run.

Type consistency:

- Backend canonical function names are defined in Task 1 and consumed in Tasks 2-4.
- Frontend `parameterViewTabs` and `resolvedCanonicalParameterization` are defined in Task 5 and consumed in Task 6.
- Patch version is consistently `1.1.2`.
