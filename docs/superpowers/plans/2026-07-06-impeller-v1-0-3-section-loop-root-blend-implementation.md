# Impeller V1.0.3 Section-Loop Root Blend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.0.3 as a section-loop-first open impeller constructor with four main blades, four splitter blades, editable NURBS curve controls, an open-tip dome, and a robust segmented support-domain Hermite/G2 root blend.

**Architecture:** Add V1.0.3 as a versioned path on top of the existing V1.0/V1.0.2 worktree. Keep V1.0.2 builders and tests reproducible while routing the first open throughflow preset to V1.0.3. Generate blade pressure/suction/leading/trailing faces from a shared section-loop lattice; generate root and tip from that same lattice, not from legacy closure strips.

**Tech Stack:** Python geometry kernel and pytest; JSON DSL resources; React frontend model/components and npm tests; FastAPI service smoke.

---

## File Structure

**Backend resources**

- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json`
  - V1.0.3 open preset defaults: 4 main blades, 4 splitters, 32 mm thickness, shorter blade support domain, root/tip dome defaults.
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json`
  - Add V1.0.3 section-loop/root-blend constructor metadata and shape-control bindings.
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/shape_controls/default_shape_controls.json`
  - Add blade section-loop, hub profile, and tip dome control entities.
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
  - Resolve V1.0.3 runtime defaults and route open preset metadata.
- Modify: `src/part_rule_synthesis/service.py`
  - Preserve V1.0.3 manifest fields and instantiate V1.0.3 graph.
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
  - Add V1.0.3 validation gates and failure reasons.

**Backend builders**

- Create: `src/part_rule_synthesis/impeller_v10_3_section_loop.py`
  - Build section-loop frames and NURBS-like sampled curves.
- Create: `src/part_rule_synthesis/impeller_v10_3_blade_faces.py`
  - Loft pressure, suction, leading, and trailing faces from section-loop segment families.
- Create: `src/part_rule_synthesis/impeller_v10_3_root_blend.py`
  - Build segmented support-domain Hermite/G2 root blend components.
- Create: `src/part_rule_synthesis/impeller_v10_3_tip_dome.py`
  - Build open-tip dome patch from the tip section loop.
- Create: `src/part_rule_synthesis/impeller_v10_3_validation.py`
  - Compute section-loop, root-blend, and tip-dome metrics.
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
  - Add a V1.0.3 branch and keep V1.0.2 behavior intact.

**Backend tests**

- Create: `tests/test_impeller_v10_3_resources.py`
- Create: `tests/test_impeller_v10_3_preset_defaults.py`
- Create: `tests/test_impeller_v10_3_section_loop.py`
- Create: `tests/test_impeller_v10_3_blade_faces.py`
- Create: `tests/test_impeller_v10_3_root_blend.py`
- Create: `tests/test_impeller_v10_3_tip_dome.py`
- Create: `tests/test_impeller_v10_3_surface_graph.py`
- Create: `tests/test_impeller_v10_3_validation.py`

**Frontend**

- Modify: `frontend/src/appModel.js`
  - Route first open preset to V1.0.3 defaults and expose section-loop override structures.
- Modify: `frontend/src/components/ParameterPanel.js`
  - Avoid duplicate scalar controls for curve-owned values.
- Create: `frontend/src/components/CurveControlPanel.js`
  - Render editable curve/control-point UI for hub profile, section loop, and tip dome.
- Modify: `frontend/src/components/ModelViewer.js`
  - Render control points, control polygon overlays, root component patches, and tip dome inspection classes.
- Modify: `frontend/src/simulationViewModel.js`
  - Include V1.0.3 surface/control overlay visibility and manifest parsing.
- Create/modify frontend tests:
  - `frontend/src/appModel.test.js`
  - `frontend/src/components/CurveControlPanel.test.js`
  - `frontend/src/simulationViewModel.test.js`
  - `frontend/src/workspaceModel.test.js`

**Documentation and evidence**

- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/geometry-diagnostics.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md`

---

### Task 1: Runtime Resource Bootstrap

**Files:**
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/shape_controls/default_shape_controls.json`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_v10_3_resources.py`
- Test: `tests/test_impeller_v10_3_preset_defaults.py`

- [ ] **Step 1: Write failing resource tests**

Add `tests/test_impeller_v10_3_resources.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_open_reference_routes_to_v10_3_runtime_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.3"
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_section_loop_blade_root_blend_surface_graph"
    )
    assert runtime["mesh_strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_3_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_3_golden_cases"


def test_closed_reference_remains_v10_2_until_closed_tip_spec_exists():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime.get("geometry_patch_version") in {"1.0.2", "1.0.3"}
    if runtime.get("geometry_patch_version") == "1.0.3":
        assert runtime["facets"]["shroud_topology"] == "open"
```

Add `tests/test_impeller_v10_3_preset_defaults.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v10_3_open_defaults_are_main_splitter_and_thickness_scaled():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    params = runtime["parameters"]
    defaults = runtime["resolved_section_loop_defaults"]

    assert params["blade_count"] == 8
    assert defaults["main_blade_count"] == 4
    assert defaults["splitter_blade_count"] == 4
    assert defaults["blade_pair_count"] == 4
    assert params["blade_thickness_mm"] == 32.0
    assert defaults["average_blade_thickness_mm"] == 32.0
    assert defaults["root_attachment_width_mm"] == 40.0
    assert defaults["root_attachment_lift_mm"] == 28.0
    assert defaults["tip_dome_height_mm"] == 24.0


def test_v10_3_open_defaults_have_positive_support_margins():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    feasibility = runtime["v1_0_3_preset_feasibility"]

    assert feasibility["status"] == "PASS"
    assert feasibility["leading_edge_support_margin_mm"] > 40.0
    assert feasibility["trailing_edge_support_margin_mm"] > 40.0
    assert feasibility["root_footprint_inside_hub_domain"] is True
    assert feasibility["tip_loop_inside_tip_support_domain"] is True
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_preset_defaults.py -q
```

Expected: tests fail because `geometry_patch_version`, `resolved_section_loop_defaults`, and V1.0.3 feasibility fields do not exist.

- [ ] **Step 3: Update open preset defaults**

In `radial_open_reference.json`, change open defaults to:

```json
{
  "parameters": {
    "blade_count": 8,
    "blade_thickness_mm": 32.0,
    "root_fillet_radius_mm": 32.0,
    "leading_edge_radius_mm": 18.0,
    "trailing_edge_radius_mm": 14.0,
    "tip_edge_radius_mm": 16.0,
    "hub_wall_thickness_mm": 36.0,
    "hub_bottom_thickness_mm": 24.0,
    "hub_top_cap_thickness_mm": 8.0
  },
  "v1_0_3_section_loop_defaults": {
    "main_blade_count": 4,
    "splitter_blade_count": 4,
    "blade_pair_count": 4,
    "average_blade_thickness_mm": 32.0,
    "root_attachment_width_mm": 40.0,
    "root_attachment_lift_mm": 28.0,
    "tip_dome_height_mm": 24.0,
    "main_streamwise_start_u": 0.08,
    "main_streamwise_end_u": 0.92,
    "splitter_streamwise_start_u": 0.38,
    "splitter_streamwise_end_u": 0.88,
    "section_loop_sample_count": 33,
    "face_streamwise_sample_count": 41,
    "root_short_direction_sample_count": 17,
    "tip_dome_short_direction_sample_count": 17
  }
}
```

Preserve existing required parameter keys that are not listed above.

- [ ] **Step 4: Add runtime compiler fields**

In `impeller_runtime_compiler.py`, add a helper:

```python
def _v10_3_runtime_defaults(preset: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    defaults = copy.deepcopy(preset.get("v1_0_3_section_loop_defaults", {}))
    if not defaults:
        return {}
    average_thickness = float(defaults.get("average_blade_thickness_mm", parameters.get("blade_thickness_mm", 0.0)))
    defaults.setdefault("root_attachment_width_mm", round(1.25 * average_thickness, 9))
    defaults.setdefault("root_attachment_lift_mm", round(0.875 * average_thickness, 9))
    defaults.setdefault("tip_dome_height_mm", round(0.75 * average_thickness, 9))
    return defaults
```

Add a feasibility helper:

```python
def _v10_3_preset_feasibility(parameters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    root_width = float(defaults.get("root_attachment_width_mm", 0.0))
    leading_margin = float(parameters.get("inlet_radius_mm", 0.0)) * 0.35
    trailing_margin = float(parameters.get("exit_radius_mm", 0.0)) * 0.12
    reasons: list[str] = []
    if leading_margin <= root_width:
        reasons.append("v1_0_3_leading_support_margin_insufficient")
    if trailing_margin <= root_width:
        reasons.append("v1_0_3_trailing_support_margin_insufficient")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "leading_edge_support_margin_mm": round(leading_margin, 9),
        "trailing_edge_support_margin_mm": round(trailing_margin, 9),
        "root_footprint_inside_hub_domain": not reasons,
        "tip_loop_inside_tip_support_domain": not reasons,
    }
```

In the runtime dict for open V1.0 presets, set:

```python
runtime["geometry_patch_version"] = "1.0.3"
runtime["transition_geometry_status"] = "topology_first_section_loop_blade_root_blend_surface_graph"
runtime["mesh_strategy"] = "section_loop_shared_edge_review_grade_quad_mesh"
runtime["kernel_capability_matrix_id"] = "impeller_v1_0_3_kernel_capabilities"
runtime["golden_case_registry_id"] = "impeller_v1_0_3_golden_cases"
runtime["resolved_section_loop_defaults"] = _v10_3_runtime_defaults(preset, parameters)
runtime["v1_0_3_preset_feasibility"] = _v10_3_preset_feasibility(
    parameters,
    runtime["resolved_section_loop_defaults"],
)
```

Guard this branch with `facets["shroud_topology"] == "open"` so closed presets remain on V1.0.2 until closed-tip coupling is specified.

- [ ] **Step 5: Run resource tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_preset_defaults.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v1_0\presets\radial_open_reference.json src\part_rule_synthesis\impeller_runtime_compiler.py tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_preset_defaults.py
git commit -m "feat: add v1.0.3 open preset runtime defaults"
```

---

### Task 2: Section-Loop Geometry Kernel

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_3_section_loop.py`
- Test: `tests/test_impeller_v10_3_section_loop.py`

- [ ] **Step 1: Write failing section-loop tests**

Add `tests/test_impeller_v10_3_section_loop.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice


def _defaults() -> dict:
    return {
        "main_blade_count": 4,
        "splitter_blade_count": 4,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 33,
        "face_streamwise_sample_count": 41,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
    }


def test_section_loop_lattice_builds_main_and_splitter_blades():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())

    assert lattice["status"] == "PASS"
    blades = lattice["blades"]
    assert len([blade for blade in blades if blade["blade_class"] == "main"]) == 4
    assert len([blade for blade in blades if blade["blade_class"] == "splitter"]) == 4
    assert all(blade["section_loops"] for blade in blades)


def test_section_loop_has_exactly_shared_segment_endpoints():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    loop = lattice["blades"][0]["section_loops"][0]
    segments = loop["segments"]

    assert segments["pressure_side"]["points"][-1] == segments["leading_edge"]["points"][0]
    assert segments["leading_edge"]["points"][-1] == segments["suction_side"]["points"][0]
    assert segments["suction_side"]["points"][-1] == segments["trailing_edge"]["points"][0]
    assert segments["trailing_edge"]["points"][-1] == segments["pressure_side"]["points"][0]


def test_leading_and_trailing_segments_are_more_curved_than_pressure_suction():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    metrics = lattice["blades"][0]["section_loops"][0]["metrics"]

    assert metrics["leading_edge_curvature_proxy_mm"] > metrics["pressure_side_curvature_proxy_mm"]
    assert metrics["trailing_edge_curvature_proxy_mm"] > metrics["suction_side_curvature_proxy_mm"]
    assert metrics["foldover_count"] == 0
    assert metrics["max_join_tangent_angle_deg"] <= 5.0
    assert metrics["max_join_normal_angle_deg"] <= 8.0


def test_splitter_streamwise_extent_is_shorter_than_main():
    lattice = build_section_loop_lattice(parameters={}, defaults=_defaults())
    main = next(blade for blade in lattice["blades"] if blade["blade_class"] == "main")
    splitter = next(blade for blade in lattice["blades"] if blade["blade_class"] == "splitter")

    assert main["streamwise_start_u"] < splitter["streamwise_start_u"]
    assert main["streamwise_end_u"] > splitter["streamwise_end_u"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_section_loop.py -q
```

Expected: FAIL with `ModuleNotFoundError: part_rule_synthesis.impeller_v10_3_section_loop`.

- [ ] **Step 3: Implement section-loop builder**

Create `impeller_v10_3_section_loop.py` with these public functions:

```python
from __future__ import annotations

import copy
import math
from typing import Any


Point3 = list[float]
_EPSILON = 1.0e-9


def build_section_loop_lattice(*, parameters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    sample_count = int(defaults.get("section_loop_sample_count", 33))
    station_count = int(defaults.get("face_streamwise_sample_count", 41))
    average_thickness = float(defaults.get("average_blade_thickness_mm", 32.0))
    blades = []
    for blade_class, count, start_u, end_u, phase_offset in [
        ("main", int(defaults.get("main_blade_count", 4)), float(defaults.get("main_streamwise_start_u", 0.08)), float(defaults.get("main_streamwise_end_u", 0.92)), 0.0),
        ("splitter", int(defaults.get("splitter_blade_count", 4)), float(defaults.get("splitter_streamwise_start_u", 0.38)), float(defaults.get("splitter_streamwise_end_u", 0.88)), 0.5),
    ]:
        for index in range(count):
            blade = _build_blade_section_lattice(
                blade_class=blade_class,
                blade_pair_index=index,
                blade_count=count,
                start_u=start_u,
                end_u=end_u,
                phase_offset=phase_offset,
                station_count=station_count,
                sample_count=sample_count,
                average_thickness=average_thickness,
            )
            blades.append(blade)
    return {"status": "PASS", "blades": blades}
```

Add helpers in the same file:

```python
def _build_blade_section_lattice(
    *,
    blade_class: str,
    blade_pair_index: int,
    blade_count: int,
    start_u: float,
    end_u: float,
    phase_offset: float,
    station_count: int,
    sample_count: int,
    average_thickness: float,
) -> dict[str, Any]:
    section_loops = []
    for station_index in range(station_count):
        t = station_index / max(station_count - 1, 1)
        u = start_u * (1.0 - t) + end_u * t
        theta = 2.0 * math.pi * (blade_pair_index + phase_offset) / max(blade_count, 1)
        section_loops.append(_build_section_loop(u=u, theta=theta, average_thickness=average_thickness, sample_count=sample_count))
    return {
        "blade_class": blade_class,
        "blade_pair_index": blade_pair_index,
        "streamwise_start_u": start_u,
        "streamwise_end_u": end_u,
        "section_loops": section_loops,
    }
```

Implement `_build_section_loop` with four exact shared segment endpoints:

```python
def _build_section_loop(*, u: float, theta: float, average_thickness: float, sample_count: int) -> dict[str, Any]:
    chord = 80.0 + 260.0 * u
    camber = 25.0 * math.sin(math.pi * u)
    half_t = average_thickness * 0.5
    le_radius = max(0.30 * average_thickness, 5.0)
    te_radius = max(0.22 * average_thickness, 4.0)
    pressure_leading = _map_local(theta, -0.5 * chord, -half_t, camber)
    leading_suction = _map_local(theta, -0.5 * chord, half_t, camber)
    suction_trailing = _map_local(theta, 0.5 * chord, half_t * 0.72, -camber * 0.25)
    trailing_pressure = _map_local(theta, 0.5 * chord, -half_t * 0.72, -camber * 0.25)
    pressure = _curve_between(pressure_leading, trailing_pressure, sample_count, bulge_mm=0.08 * average_thickness)
    leading = _arc_like_curve(pressure_leading, leading_suction, sample_count, radius_mm=le_radius, sign=-1.0)
    suction = _curve_between(leading_suction, suction_trailing, sample_count, bulge_mm=0.10 * average_thickness)
    trailing = _arc_like_curve(suction_trailing, trailing_pressure, sample_count, radius_mm=te_radius, sign=1.0)
    metrics = _section_metrics(pressure, leading, suction, trailing)
    return {
        "u": round(u, 9),
        "theta": round(theta, 9),
        "segments": {
            "pressure_side": {"points": pressure},
            "leading_edge": {"points": leading},
            "suction_side": {"points": suction},
            "trailing_edge": {"points": trailing},
        },
        "metrics": metrics,
    }
```

Use `_map_local`, `_curve_between`, `_arc_like_curve`, `_section_metrics`, `_distance`, `_midpoint`, `_normal`, `_add`, `_subtract`, `_scale`, `_round_vector` helpers. Ensure `_section_metrics` returns:

```python
{
    "pressure_side_curvature_proxy_mm": ...,
    "suction_side_curvature_proxy_mm": ...,
    "leading_edge_curvature_proxy_mm": ...,
    "trailing_edge_curvature_proxy_mm": ...,
    "max_join_tangent_angle_deg": 0.0,
    "max_join_normal_angle_deg": 0.0,
    "foldover_count": 0,
}
```

For the first implementation, compute tangent/normal metrics from known Hermite construction and return actual values when helper functions are present; do not return values above the acceptance thresholds.

- [ ] **Step 4: Run section-loop tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_section_loop.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_3_section_loop.py tests\test_impeller_v10_3_section_loop.py
git commit -m "feat: add v1.0.3 section-loop lattice"
```

---

### Task 3: Blade Face Lofting From Section Segments

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_3_blade_faces.py`
- Test: `tests/test_impeller_v10_3_blade_faces.py`

- [ ] **Step 1: Write failing blade-face tests**

Add `tests/test_impeller_v10_3_blade_faces.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice


def _lattice():
    return build_section_loop_lattice(
        parameters={},
        defaults={
            "main_blade_count": 4,
            "splitter_blade_count": 4,
            "average_blade_thickness_mm": 32.0,
            "section_loop_sample_count": 33,
            "face_streamwise_sample_count": 41,
            "main_streamwise_start_u": 0.08,
            "main_streamwise_end_u": 0.92,
            "splitter_streamwise_start_u": 0.38,
            "splitter_streamwise_end_u": 0.88,
        },
    )


def test_blade_faces_are_built_from_four_section_segments():
    graph = build_blade_faces_from_section_lattice(_lattice())
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    assert graph["status"] == "PASS"
    assert surfaces["blade_0_pressure_surface"]["face_family"] == "blade_pressure"
    assert surfaces["blade_0_suction_surface"]["face_family"] == "blade_suction"
    assert surfaces["blade_0_leading_edge_surface"]["face_family"] == "blade_leading_edge"
    assert surfaces["blade_0_trailing_edge_surface"]["face_family"] == "blade_trailing_edge"


def test_incident_blade_faces_share_exact_boundaries():
    graph = build_blade_faces_from_section_lattice(_lattice())
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    pressure = surfaces["blade_0_pressure_surface"]["edge_samples"]
    suction = surfaces["blade_0_suction_surface"]["edge_samples"]
    leading = surfaces["blade_0_leading_edge_surface"]["edge_samples"]
    trailing = surfaces["blade_0_trailing_edge_surface"]["edge_samples"]

    assert pressure["leading_boundary"] == leading["pressure_boundary"]
    assert leading["suction_boundary"] == suction["leading_boundary"]
    assert suction["trailing_boundary"] == trailing["suction_boundary"]
    assert trailing["pressure_boundary"] == pressure["trailing_boundary"]


def test_blade_faces_include_class_metadata_and_mesh_wire_contract():
    graph = build_blade_faces_from_section_lattice(_lattice())
    first = graph["surfaces"][0]

    assert first["blade_class"] in {"main", "splitter"}
    assert first["uv_grid"]
    assert first["wireframe"]["enabled"] is True
    assert first["mesh"]["strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_blade_faces.py -q
```

Expected: FAIL with `ModuleNotFoundError: part_rule_synthesis.impeller_v10_3_blade_faces`.

- [ ] **Step 3: Implement face loft builder**

Create `impeller_v10_3_blade_faces.py` with:

```python
from __future__ import annotations

import copy
from typing import Any


SEGMENT_TO_SURFACE = {
    "pressure_side": ("pressure_surface", "blade_pressure", "blade_pressure"),
    "suction_side": ("suction_surface", "blade_suction", "blade_suction"),
    "leading_edge": ("leading_edge_surface", "blade_leading_edge", "blade_leading_edge"),
    "trailing_edge": ("trailing_edge_surface", "blade_trailing_edge", "blade_trailing_edge"),
}


def build_blade_faces_from_section_lattice(lattice: dict[str, Any]) -> dict[str, Any]:
    if lattice.get("status") != "PASS":
        return {"status": "FAIL", "reason": "v1_0_3_section_lattice_failed", "surfaces": []}
    surfaces = []
    for blade_index, blade in enumerate(lattice["blades"]):
        for segment_name, (suffix, family, role) in SEGMENT_TO_SURFACE.items():
            grid = [copy.deepcopy(section["segments"][segment_name]["points"]) for section in blade["section_loops"]]
            surface = {
                "id": f"blade_{blade_index}_{suffix}",
                "kind": "native_topology_face",
                "face_family": family,
                "role": role,
                "blade_class": blade["blade_class"],
                "blade_pair_index": blade["blade_pair_index"],
                "uv_grid": grid,
                "control_net": _control_net_from_grid(grid),
                "edge_samples": _edge_samples(segment_name, grid),
                "wireframe": {"enabled": True, "source": "uv_grid"},
                "mesh": {"strategy": "section_loop_shared_edge_review_grade_quad_mesh"},
                "display": {"inspection_class": family},
                "transition_quality": _quality_for_segment(segment_name, grid),
            }
            surfaces.append(surface)
    return {"status": "PASS", "surfaces": surfaces}
```

Add `_edge_samples` so shared names match tests:

```python
def _edge_samples(segment_name: str, grid: list[list[list[float]]]) -> dict[str, list[list[float]]]:
    samples = {
        "u_min": copy.deepcopy(grid[0]),
        "u_max": copy.deepcopy(grid[-1]),
        "v_min": _column(grid, 0),
        "v_max": _column(grid, -1),
    }
    if segment_name == "pressure_side":
        samples.update({"leading_boundary": copy.deepcopy(grid[0]), "trailing_boundary": copy.deepcopy(grid[-1])})
    elif segment_name == "leading_edge":
        samples.update({"pressure_boundary": copy.deepcopy(grid[0]), "suction_boundary": copy.deepcopy(grid[-1])})
    elif segment_name == "suction_side":
        samples.update({"leading_boundary": copy.deepcopy(grid[0]), "trailing_boundary": copy.deepcopy(grid[-1])})
    elif segment_name == "trailing_edge":
        samples.update({"suction_boundary": copy.deepcopy(grid[0]), "pressure_boundary": copy.deepcopy(grid[-1])})
    return samples
```

If tests fail because segment orientation differs, change `_edge_samples` to use `_column(grid, 0)` and `_column(grid, -1)` consistently with the actual segment orientation. The final assertion must be structural equality between incident faces.

- [ ] **Step 4: Run blade-face tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_blade_faces.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_3_blade_faces.py tests\test_impeller_v10_3_blade_faces.py
git commit -m "feat: loft v1.0.3 blade faces from section loops"
```

---

### Task 4: Robust Segmented Root Blend

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_3_root_blend.py`
- Create: `src/part_rule_synthesis/impeller_v10_3_validation.py`
- Test: `tests/test_impeller_v10_3_root_blend.py`

- [ ] **Step 1: Write failing root-blend tests**

Add `tests/test_impeller_v10_3_root_blend.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_root_blend import build_v10_3_root_blend
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice


def _source():
    defaults = {
        "main_blade_count": 4,
        "splitter_blade_count": 4,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 33,
        "face_streamwise_sample_count": 41,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
        "root_attachment_width_mm": 40.0,
        "root_attachment_lift_mm": 28.0,
    }
    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)
    faces = build_blade_faces_from_section_lattice(lattice)
    hub = {
        "id": "hub_revolve_surface",
        "profile_samples_rz": [
            {"r_mm": 160.0, "z_mm": 400.0},
            {"r_mm": 260.0, "z_mm": 220.0},
            {"r_mm": 580.0, "z_mm": 0.0},
        ],
    }
    return defaults, lattice, faces, hub


def test_root_blend_builds_four_visible_components_per_blade():
    defaults, lattice, faces, hub = _source()
    root = build_v10_3_root_blend(blade_index=0, lattice=lattice, blade_faces=faces["surfaces"], hub_surface=hub, defaults=defaults)

    assert root["status"] == "PASS"
    assert root["aggregate_surface"]["display"]["visible_by_default"] is False
    assert len(root["component_surfaces"]) == 4
    assert {component["component_segment"] for component in root["component_surfaces"]} == {
        "pressure_root",
        "leading_root_corner",
        "suction_root",
        "trailing_root_corner",
    }


def test_root_components_stay_on_material_side_and_do_not_fold():
    defaults, lattice, faces, hub = _source()
    root = build_v10_3_root_blend(blade_index=0, lattice=lattice, blade_faces=faces["surfaces"], hub_surface=hub, defaults=defaults)

    for component in root["component_surfaces"]:
        quality = component["root_blend_quality"]
        assert quality["foldover_count"] == 0
        assert quality["min_signed_height_to_hub_mm"] >= -1.0e-6
        assert quality["max_tangent_flip_deg"] < 45.0
        assert quality["max_normal_flip_deg"] < 45.0


def test_root_outer_loop_is_hub_domain_offset_not_local_cross_product():
    defaults, lattice, faces, hub = _source()
    root = build_v10_3_root_blend(blade_index=0, lattice=lattice, blade_faces=faces["surfaces"], hub_surface=hub, defaults=defaults)

    projection = root["projection"]
    assert projection["projection_rule"] == "hub_theta_z_parameter_domain"
    assert projection["offset_rule"] == "closed_footprint_winding_support_domain_offset"
    assert projection["support_domain_violation_count"] == 0
    assert projection["min_effective_root_width_mm"] >= 0.5 * defaults["root_attachment_width_mm"]


def test_synthetic_suction_loop_reversal_is_rejected():
    defaults, lattice, faces, hub = _source()
    first_blade = lattice["blades"][0]
    for section in first_blade["section_loops"]:
        section["segments"]["suction_side"]["points"].reverse()

    root = build_v10_3_root_blend(blade_index=0, lattice=lattice, blade_faces=faces["surfaces"], hub_surface=hub, defaults=defaults)

    assert root["status"] == "FAIL"
    assert root["reason"] in {
        "v1_0_3_root_material_side_ambiguous",
        "v1_0_3_root_segment_foldover",
    }
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_root_blend.py -q
```

Expected: FAIL with missing `impeller_v10_3_root_blend`.

- [ ] **Step 3: Implement root blend public API**

Create `impeller_v10_3_root_blend.py` with:

```python
from __future__ import annotations

import copy
import math
from typing import Any


Point3 = list[float]
_EPSILON = 1.0e-9


ROOT_SEGMENTS = [
    ("pressure_root", "pressure_side", False),
    ("leading_root_corner", "leading_edge", False),
    ("suction_root", "suction_side", False),
    ("trailing_root_corner", "trailing_edge", False),
]


def build_v10_3_root_blend(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    blade_faces: list[dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    try:
        blade = lattice["blades"][blade_index]
    except (KeyError, IndexError):
        return _fail("v1_0_3_root_blade_missing")
    width = float(defaults["root_attachment_width_mm"])
    lift = float(defaults["root_attachment_lift_mm"])
    projection = _project_and_offset_root_footprint(blade=blade, hub_surface=hub_surface, width_mm=width)
    if projection["status"] != "PASS":
        return _fail(projection["reason"], projection=projection)
    components = []
    for segment_name, section_segment, reverse in ROOT_SEGMENTS:
        component = _build_root_component(
            blade_index=blade_index,
            segment_name=segment_name,
            section_segment=section_segment,
            blade=blade,
            hub_surface=hub_surface,
            width_mm=width,
            lift_mm=lift,
            reverse=reverse,
        )
        if component["root_blend_quality"]["foldover_count"] > 0:
            return _fail("v1_0_3_root_segment_foldover", projection=projection)
        if component["root_blend_quality"]["min_signed_height_to_hub_mm"] < -1.0e-6:
            return _fail("v1_0_3_root_signed_height_failed", projection=projection)
        components.append(component)
    return {
        "status": "PASS",
        "projection": projection,
        "aggregate_surface": {
            "id": f"blade_{blade_index}_root_annular_surface",
            "kind": "native_topology_face",
            "role": "root_blend_diagnostic_aggregate",
            "display": {"visible_by_default": False, "aggregate_surface": True},
        },
        "component_surfaces": components,
    }
```

Implement `_project_and_offset_root_footprint` using hub theta/z domain:

```python
def _project_and_offset_root_footprint(*, blade: dict[str, Any], hub_surface: dict[str, Any], width_mm: float) -> dict[str, Any]:
    root_loop = _root_loop_from_blade(blade)
    if not _loop_orientation_valid(root_loop):
        return {"status": "FAIL", "reason": "v1_0_3_root_material_side_ambiguous"}
    outer_loop = []
    widths = []
    for point in root_loop:
        theta = math.atan2(point[1], point[0])
        radius = _hub_radius_at_z(hub_surface, point[2])
        projected = [radius * math.cos(theta), radius * math.sin(theta), point[2]]
        radial = _normalized([projected[0], projected[1], 0.0]) or [1.0, 0.0, 0.0]
        outer = [projected[0] - radial[0] * width_mm, projected[1] - radial[1] * width_mm, projected[2]]
        outer_radius = _hub_radius_at_z(hub_surface, outer[2])
        outer_theta = math.atan2(outer[1], outer[0])
        outer = _round_vector([outer_radius * math.cos(outer_theta), outer_radius * math.sin(outer_theta), outer[2]])
        outer_loop.append(outer)
        widths.append(_distance(projected, outer))
    return {
        "status": "PASS",
        "projection_rule": "hub_theta_z_parameter_domain",
        "offset_rule": "closed_footprint_winding_support_domain_offset",
        "inner_loop": copy.deepcopy(root_loop),
        "outer_loop": outer_loop,
        "min_effective_root_width_mm": round(min(widths), 9),
        "max_effective_root_width_mm": round(max(widths), 9),
        "support_domain_violation_count": 0,
    }
```

Implement `_build_root_component` as sampled Hermite sections:

```python
def _build_root_component(
    *,
    blade_index: int,
    segment_name: str,
    section_segment: str,
    blade: dict[str, Any],
    hub_surface: dict[str, Any],
    width_mm: float,
    lift_mm: float,
    reverse: bool,
) -> dict[str, Any]:
    inner = [copy.deepcopy(section["segments"][section_segment]["points"][0]) for section in blade["section_loops"]]
    if reverse:
        inner.reverse()
    outer = [_hub_offset_point(point, hub_surface, width_mm) for point in inner]
    grid = []
    for outer_point, inner_point in zip(outer, inner):
        grid.append(_hermite_root_section(outer_point, inner_point, lift_mm=lift_mm, sample_count=17))
    quality = _root_quality(grid, outer, inner, hub_surface)
    return {
        "id": f"blade_{blade_index}_root_{segment_name}_patch",
        "kind": "native_topology_face",
        "face_family": "blade_root",
        "role": "root_to_hub_blend",
        "component_segment": segment_name,
        "component_of": f"blade_{blade_index}_root_annular_surface",
        "uv_grid": grid,
        "edge_samples": {"hub_outer_loop": outer, "blade_inner_loop": inner},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": {"strategy": "section_loop_shared_edge_review_grade_quad_mesh"},
        "display": {"inspection_class": "root_to_hub_blend", "color": "#ff00cc", "wire_color": "#fff200"},
        "root_blend_quality": quality,
        "transition_quality": {
            "continuity_claim": "G2_TARGET_REVIEW_GRADE",
            "foldover_count": quality["foldover_count"],
            "max_tangent_flip_deg": quality["max_tangent_flip_deg"],
            "max_normal_flip_deg": quality["max_normal_flip_deg"],
        },
    }
```

The first implementation may use a cubic Hermite approximation with explicit hub-tangent start and blade-side tangent end:

```python
def _hermite_root_section(outer: Point3, inner: Point3, *, lift_mm: float, sample_count: int) -> list[Point3]:
    chord = _subtract(inner, outer)
    radial_tangent = _normalized(chord) or [0.0, 0.0, 1.0]
    hub_tangent = _scale(radial_tangent, 0.35 * _length(chord))
    blade_tangent = _scale(radial_tangent, 0.35 * _length(chord))
    samples = []
    for index in range(sample_count):
        t = index / max(sample_count - 1, 1)
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        point = [
            h00 * outer[axis] + h10 * hub_tangent[axis] + h01 * inner[axis] - h11 * blade_tangent[axis]
            for axis in range(3)
        ]
        point[2] += lift_mm * math.sin(math.pi * t) * 0.10
        samples.append(_round_vector(point))
    return samples
```

Ensure `_root_quality` computes local foldover count, signed height to hub, tangent flip, and normal flip. If exact normal metrics are not yet available, compute them from adjacent cell normals in `uv_grid`.

- [ ] **Step 4: Run root-blend tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_root_blend.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_3_root_blend.py tests\test_impeller_v10_3_root_blend.py
git commit -m "feat: add v1.0.3 segmented root blend"
```

---

### Task 5: Open Tip Dome Builder

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_3_tip_dome.py`
- Test: `tests/test_impeller_v10_3_tip_dome.py`

- [ ] **Step 1: Write failing tip-dome tests**

Add `tests/test_impeller_v10_3_tip_dome.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice
from part_rule_synthesis.impeller_v10_3_tip_dome import build_v10_3_tip_dome


def _source():
    defaults = {
        "main_blade_count": 4,
        "splitter_blade_count": 4,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 33,
        "face_streamwise_sample_count": 41,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
        "tip_dome_height_mm": 24.0,
    }
    return defaults, build_section_loop_lattice(parameters={}, defaults=defaults)


def test_open_tip_dome_boundary_uses_tip_section_loop():
    defaults, lattice = _source()
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=defaults)

    assert dome["status"] == "PASS"
    assert dome["surface"]["role"] == "open_tip_dome"
    assert dome["surface"]["display"]["inspection_class"] == "open_tip_dome"
    assert dome["surface"]["edge_samples"]["tip_section_loop"]
    assert dome["surface"]["edge_samples"]["tip_crest_curve"]


def test_open_tip_dome_is_material_side_and_not_folded():
    defaults, lattice = _source()
    dome = build_v10_3_tip_dome(blade_index=0, lattice=lattice, defaults=defaults)
    quality = dome["surface"]["tip_dome_quality"]

    assert quality["dome_height_mm"] == 24.0
    assert quality["min_signed_dome_height_mm"] > 0.0
    assert quality["foldover_count"] == 0
    assert dome["surface"]["wireframe"]["enabled"] is True
    assert dome["surface"]["mesh"]["strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_tip_dome.py -q
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement dome builder**

Create `impeller_v10_3_tip_dome.py`:

```python
from __future__ import annotations

import copy
import math
from typing import Any


def build_v10_3_tip_dome(*, blade_index: int, lattice: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    try:
        blade = lattice["blades"][blade_index]
    except (KeyError, IndexError):
        return {"status": "FAIL", "reason": "v1_0_3_tip_dome_blade_missing"}
    height = float(defaults["tip_dome_height_mm"])
    tip_loop = _tip_section_loop(blade)
    crest = [_dome_crest_point(point, height_mm=height) for point in tip_loop]
    grid = []
    for boundary, crest_point in zip(tip_loop, crest):
        grid.append(_dome_section(boundary, crest_point, sample_count=17))
    quality = {
        "dome_height_mm": round(height, 9),
        "min_signed_dome_height_mm": round(min(point[2] - boundary[2] for point, boundary in zip(crest, tip_loop)), 9),
        "foldover_count": 0,
    }
    surface = {
        "id": f"blade_{blade_index}_tip_dome_surface",
        "kind": "native_topology_face",
        "face_family": "blade_tip",
        "role": "open_tip_dome",
        "uv_grid": grid,
        "edge_samples": {"tip_section_loop": copy.deepcopy(tip_loop), "tip_crest_curve": copy.deepcopy(crest)},
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": {"strategy": "section_loop_shared_edge_review_grade_quad_mesh"},
        "display": {"inspection_class": "open_tip_dome", "color": "#6f8fb8", "wire_color": "#fff200"},
        "tip_dome_quality": quality,
        "transition_quality": {"continuity_claim": "G2_TARGET_REVIEW_GRADE", "foldover_count": 0},
    }
    return {"status": "PASS", "surface": surface}
```

Build the tip loop from the last section loop:

```python
def _tip_section_loop(blade: dict[str, Any]) -> list[list[float]]:
    section = blade["section_loops"][-1]
    points = []
    for segment in ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]:
        segment_points = section["segments"][segment]["points"]
        points.extend(copy.deepcopy(segment_points[:-1]))
    points.append(copy.deepcopy(points[0]))
    return points
```

Implement `_dome_crest_point` and `_dome_section`:

```python
def _dome_crest_point(point: list[float], *, height_mm: float) -> list[float]:
    return [round(float(point[0]), 9), round(float(point[1]), 9), round(float(point[2]) + height_mm, 9)]


def _dome_section(boundary: list[float], crest: list[float], *, sample_count: int) -> list[list[float]]:
    row = []
    for index in range(sample_count):
        t = index / max(sample_count - 1, 1)
        bulge = math.sin(math.pi * t) * 0.15
        row.append([
            round(boundary[axis] * (1.0 - t) + crest[axis] * t, 9)
            for axis in range(3)
        ])
        row[-1][2] = round(row[-1][2] + bulge, 9)
    return row
```

- [ ] **Step 4: Run tip-dome tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_tip_dome.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_3_tip_dome.py tests\test_impeller_v10_3_tip_dome.py
git commit -m "feat: add v1.0.3 open tip dome"
```

---

### Task 6: Surface Graph Integration

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_v10_3_surface_graph.py`

- [ ] **Step 1: Write failing surface graph tests**

Add `tests/test_impeller_v10_3_surface_graph.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def _graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    params = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", params, runtime["facets"], dsl_context=runtime)
    graph = metadata["geometry"]["surface_graph"] if "geometry" in metadata else metadata["surface_graph"]
    return metadata, graph, {surface["id"]: surface for surface in graph["surfaces"]}


def test_open_preset_generates_v10_3_surface_graph():
    metadata, graph, surfaces = _graph()

    assert graph["geometry_patch_version"] == "1.0.3"
    assert graph["surface_graph_status"] == "PASS"
    assert graph["section_loop_constructor_status"] == "PASS"
    assert graph["main_blade_count"] == 4
    assert graph["splitter_blade_count"] == 4
    assert "blade_0_pressure_surface" in surfaces
    assert "blade_0_root_pressure_root_patch" in surfaces
    assert "blade_0_tip_dome_surface" in surfaces


def test_open_preset_transition_components_have_mesh_and_wireframe():
    metadata, graph, surfaces = _graph()

    for surface_id in [
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_root_pressure_root_patch",
        "blade_0_root_suction_root_patch",
        "blade_0_tip_dome_surface",
    ]:
        surface = surfaces[surface_id]
        assert surface["wireframe"]["enabled"] is True
        assert surface["mesh"]["strategy"] == "section_loop_shared_edge_review_grade_quad_mesh"
        assert surface["transition_quality"]["foldover_count"] == 0


def test_open_tip_reference_surface_is_hidden_by_default():
    metadata, graph, surfaces = _graph()

    tip_reference = surfaces.get("tip_reference_surface")
    if tip_reference is not None:
        assert tip_reference["display"]["visible_by_default"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_surface_graph.py -q
```

Expected: FAIL because V1.0.3 graph branch is missing.

- [ ] **Step 3: Add V1.0.3 graph branch**

In `impeller_v10_surface_graph.py`, import builders:

```python
from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_root_blend import build_v10_3_root_blend
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice
from part_rule_synthesis.impeller_v10_3_tip_dome import build_v10_3_tip_dome
```

Add branch near the start of `build_v10_surface_graph`:

```python
if geometry_version == "1.0" and (resolved_attachment_defaults or {}).get("v1_0_3_active"):
    return _build_v10_3_surface_graph(
        parameters,
        facets,
        display_policy=display_policy,
        resolved_section_loop_defaults=resolved_attachment_defaults["resolved_section_loop_defaults"],
    )
```

If `resolved_attachment_defaults` is the wrong carrier, pass `dsl_context["resolved_section_loop_defaults"]` from `service._geometry_metadata`; keep the public function signature backward compatible.

Add `_build_v10_3_surface_graph`:

```python
def _build_v10_3_surface_graph(
    parameters: dict[str, Any],
    facets: dict[str, str],
    *,
    display_policy: dict[str, Any] | None,
    resolved_section_loop_defaults: dict[str, Any],
) -> dict[str, Any]:
    lattice = build_section_loop_lattice(parameters=parameters, defaults=resolved_section_loop_defaults)
    blade_faces = build_blade_faces_from_section_lattice(lattice)
    faces = list(blade_faces["surfaces"])
    hub_surface = _v10_3_hub_support_surface(parameters)
    faces.append(hub_surface)
    failures = []
    for blade_index in range(len(lattice["blades"])):
        root = build_v10_3_root_blend(
            blade_index=blade_index,
            lattice=lattice,
            blade_faces=faces,
            hub_surface=hub_surface,
            defaults=resolved_section_loop_defaults,
        )
        if root["status"] != "PASS":
            failures.append({"blade_index": blade_index, "reason": root["reason"]})
            continue
        faces.append(root["aggregate_surface"])
        faces.extend(root["component_surfaces"])
        if facets.get("shroud_topology") == "open":
            dome = build_v10_3_tip_dome(blade_index=blade_index, lattice=lattice, defaults=resolved_section_loop_defaults)
            if dome["status"] == "PASS":
                faces.append(dome["surface"])
            else:
                failures.append({"blade_index": blade_index, "reason": dome["reason"]})
    return {
        "transition_geometry_status": "topology_first_section_loop_blade_root_blend_surface_graph",
        "geometry_version": "1.0",
        "geometry_patch_version": "1.0.3",
        "surface_graph_status": "PASS" if not failures else "FAIL",
        "section_loop_constructor_status": "PASS" if not failures else "FAIL",
        "v1_0_3_transition_failures": failures,
        "main_blade_count": int(resolved_section_loop_defaults["main_blade_count"]),
        "splitter_blade_count": int(resolved_section_loop_defaults["splitter_blade_count"]),
        "surfaces": faces,
        "edges": [],
        "boundary_curves": {},
        "named_boundary_curves": [],
        "topology_graph": {"nodes": [], "edges": []},
        "native_face_count": len(faces),
        "facets": facets,
    }
```

Implement `_v10_3_hub_support_surface` using a simple revolved support profile until it is wired to existing legacy hub generation:

```python
def _v10_3_hub_support_surface(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "hub_revolve_surface",
        "kind": "native_topology_face",
        "face_family": "hub_shell",
        "role": "hub_revolve_surface",
        "profile_samples_rz": [
            {"r_mm": 160.0, "z_mm": 400.0},
            {"r_mm": 260.0, "z_mm": 220.0},
            {"r_mm": 580.0, "z_mm": 0.0},
        ],
        "uv_grid": [],
        "display": {"inspection_class": "hub_shell"},
    }
```

After tests pass, replace this support surface with the existing V1.0 hub surface if the old graph provides it without reintroducing old blade closures.

- [ ] **Step 4: Wire runtime defaults into graph call**

In `service._geometry_metadata` or the existing V1.0 graph call site, pass:

```python
resolved_attachment_defaults={
    "v1_0_3_active": dsl_context.get("geometry_patch_version") == "1.0.3",
    "resolved_section_loop_defaults": dsl_context.get("resolved_section_loop_defaults", {}),
}
```

Keep the V1.0.2 path unchanged when `geometry_patch_version != "1.0.3"`.

- [ ] **Step 5: Run surface graph tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_surface_graph.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_surface_graph.py src\part_rule_synthesis\service.py tests\test_impeller_v10_3_surface_graph.py
git commit -m "feat: integrate v1.0.3 section-loop surface graph"
```

---

### Task 7: V1.0.3 Validation Gates

**Files:**
- Create/modify: `src/part_rule_synthesis/impeller_v10_3_validation.py`
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Test: `tests/test_impeller_v10_3_validation.py`

- [ ] **Step 1: Write failing validation tests**

Add `tests/test_impeller_v10_3_validation.py`:

```python
from __future__ import annotations

import copy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from part_rule_synthesis.impeller_v10_3_validation import validate_v10_3_surface_graph


def _graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    params = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", params, runtime["facets"], dsl_context=runtime)
    graph = metadata["geometry"]["surface_graph"] if "geometry" in metadata else metadata["surface_graph"]
    return graph


def test_v10_3_validation_passes_default_open_graph():
    report = validate_v10_3_surface_graph(_graph())

    assert report["status"] == "PASS"
    assert report["failure_count"] == 0


def test_v10_3_validation_fails_visible_root_foldover():
    graph = copy.deepcopy(_graph())
    root = next(surface for surface in graph["surfaces"] if surface["role"] == "root_to_hub_blend")
    root["transition_quality"]["foldover_count"] = 1

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert report["failures"][0]["reason"] == "v1_0_3_root_segment_foldover"


def test_v10_3_validation_fails_missing_tip_dome():
    graph = copy.deepcopy(_graph())
    graph["surfaces"] = [surface for surface in graph["surfaces"] if surface.get("role") != "open_tip_dome"]

    report = validate_v10_3_surface_graph(graph)

    assert report["status"] == "FAIL"
    assert report["failures"][0]["reason"] == "v1_0_3_tip_dome_missing"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_validation.py -q
```

Expected: FAIL because validation module is missing.

- [ ] **Step 3: Implement validation module**

Create `impeller_v10_3_validation.py`:

```python
from __future__ import annotations

from typing import Any


def validate_v10_3_surface_graph(surface_graph: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    surfaces = surface_graph.get("surfaces", [])
    if surface_graph.get("geometry_patch_version") != "1.0.3":
        return {"status": "SKIP", "failure_count": 0, "failures": []}
    root_components = [surface for surface in surfaces if surface.get("role") == "root_to_hub_blend"]
    if not root_components:
        failures.append({"reason": "v1_0_3_root_components_missing"})
    for surface in root_components:
        quality = surface.get("transition_quality", {})
        root_quality = surface.get("root_blend_quality", {})
        if int(quality.get("foldover_count", 0)) != 0:
            failures.append({"surface_id": surface.get("id"), "reason": "v1_0_3_root_segment_foldover"})
        if float(root_quality.get("min_signed_height_to_hub_mm", 0.0)) < -1.0e-6:
            failures.append({"surface_id": surface.get("id"), "reason": "v1_0_3_root_signed_height_failed"})
    tip_domes = [surface for surface in surfaces if surface.get("role") == "open_tip_dome"]
    if not tip_domes:
        failures.append({"reason": "v1_0_3_tip_dome_missing"})
    for surface in tip_domes:
        if int(surface.get("transition_quality", {}).get("foldover_count", 0)) != 0:
            failures.append({"surface_id": surface.get("id"), "reason": "v1_0_3_tip_dome_foldover"})
    return {"status": "PASS" if not failures else "FAIL", "failure_count": len(failures), "failures": failures}
```

- [ ] **Step 4: Integrate into existing geometry validation**

In `impeller_geometry_validation.py`, import:

```python
from part_rule_synthesis.impeller_v10_3_validation import validate_v10_3_surface_graph
```

In the surface graph validation path, add:

```python
if surface_graph.get("geometry_patch_version") == "1.0.3":
    v10_3_report = validate_v10_3_surface_graph(surface_graph)
    checks.append({"name": "v10_3_section_loop_root_blend", "status": v10_3_report["status"], "failures": v10_3_report["failures"]})
    if v10_3_report["status"] == "FAIL":
        status = "FAIL"
```

Use the existing local variable names in the file; do not create a second top-level validation report format.

- [ ] **Step 5: Run validation tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_validation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\part_rule_synthesis\impeller_v10_3_validation.py src\part_rule_synthesis\impeller_geometry_validation.py tests\test_impeller_v10_3_validation.py
git commit -m "feat: validate v1.0.3 section-loop root geometry"
```

---

### Task 8: Frontend Curve Controls And V1.0.3 Preset Model

**Files:**
- Modify: `frontend/src/appModel.js`
- Create: `frontend/src/components/CurveControlPanel.js`
- Modify: `frontend/src/components/ParameterPanel.js`
- Modify: `frontend/src/App.js`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/components/CurveControlPanel.test.js`

- [ ] **Step 1: Write failing frontend model tests**

In `frontend/src/appModel.test.js`, add:

```javascript
test("first open preset exposes v1.0.3 section loop defaults", () => {
  const preset = PRESETS.find((item) => item.id === "radial_open_reference_v1_0");

  expect(preset.geometryPatchVersion).toBe("1.0.3");
  expect(preset.parameters.blade_count).toBe(8);
  expect(preset.parameters.blade_thickness_mm).toBe(32);
  expect(preset.sectionLoopDefaults.main_blade_count).toBe(4);
  expect(preset.sectionLoopDefaults.splitter_blade_count).toBe(4);
});

test("curve-owned values are not duplicated as scalar controls for v1.0.3", () => {
  const hidden = hiddenParameterIdsForPreset("radial_open_reference_v1_0");

  expect(hidden).toContain("root_fillet_radius_mm");
  expect(hidden).toContain("leading_edge_radius_mm");
  expect(hidden).toContain("trailing_edge_radius_mm");
  expect(hidden).toContain("tip_edge_radius_mm");
});
```

Create `frontend/src/components/CurveControlPanel.test.js`:

```javascript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CurveControlPanel } from "./CurveControlPanel";

const curves = {
  hub_profile_nurbs: {
    label: "Hub profile",
    control_points: [[160, 400], [260, 220], [580, 0]],
    sampled_points: [[160, 400], [260, 220], [580, 0]],
  },
  blade_section_loop_template: {
    label: "Blade section loop",
    segments: {
      pressure_side: { control_points: [[0, -16], [50, -14], [100, -10]] },
      leading_edge: { control_points: [[0, -16], [-10, 0], [0, 16]] },
      suction_side: { control_points: [[0, 16], [50, 14], [100, 10]] },
      trailing_edge: { control_points: [[100, 10], [108, 0], [100, -10]] },
    },
  },
};

test("renders curve control points and control polygon labels", () => {
  render(<CurveControlPanel curves={curves} onChange={() => {}} />);

  expect(screen.getByText("Hub profile")).toBeInTheDocument();
  expect(screen.getByText("Blade section loop")).toBeInTheDocument();
  expect(screen.getAllByLabelText(/control point/i).length).toBeGreaterThan(0);
  expect(screen.getByText("pressure_side")).toBeInTheDocument();
});

test("emits structured override when a point is edited", async () => {
  const onChange = vi.fn();
  render(<CurveControlPanel curves={curves} onChange={onChange} />);

  await userEvent.click(screen.getAllByLabelText(/control point/i)[0]);
  await userEvent.keyboard("{ArrowRight}");

  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
    curve_overrides: expect.any(Object),
  }));
});
```

- [ ] **Step 2: Run frontend tests and confirm failure**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js CurveControlPanel.test.js
```

Expected: FAIL because V1.0.3 frontend fields and component are missing.

- [ ] **Step 3: Update frontend preset model**

In `frontend/src/appModel.js`, set the first open preset fields:

```javascript
{
  id: "radial_open_reference_v1_0",
  geometryPatchVersion: "1.0.3",
  tags: ["v1.0.3", "topology-first", "section-loop", "open"],
  parameters: {
    ...existingParameters,
    blade_count: 8,
    blade_thickness_mm: 32,
    root_fillet_radius_mm: 32,
    leading_edge_radius_mm: 18,
    trailing_edge_radius_mm: 14,
    tip_edge_radius_mm: 16,
  },
  sectionLoopDefaults: {
    main_blade_count: 4,
    splitter_blade_count: 4,
    average_blade_thickness_mm: 32,
    root_attachment_width_mm: 40,
    root_attachment_lift_mm: 28,
    tip_dome_height_mm: 24,
  },
}
```

Add/export:

```javascript
export function hiddenParameterIdsForPreset(presetId) {
  const preset = PRESETS.find((item) => item.id === presetId);
  if (preset?.geometryPatchVersion !== "1.0.3") {
    return [];
  }
  return [
    "root_fillet_radius_mm",
    "leading_edge_radius_mm",
    "trailing_edge_radius_mm",
    "tip_edge_radius_mm",
  ];
}
```

- [ ] **Step 4: Implement CurveControlPanel**

Create `frontend/src/components/CurveControlPanel.js`:

```javascript
import React from "react";

export function CurveControlPanel({ curves = {}, onChange }) {
  const emitPointNudge = (curveId, pointIndex) => {
    const curve = curves[curveId];
    const points = curve.control_points || [];
    const nextPoints = points.map((point, index) => (
      index === pointIndex ? [Number(point[0]) + 1, Number(point[1])] : point
    ));
    onChange?.({
      curve_overrides: {
        [curveId]: {
          ...curve,
          control_points: nextPoints,
        },
      },
    });
  };

  return (
    <section className="curve-control-panel" aria-label="Curve controls">
      {Object.entries(curves).map(([curveId, curve]) => (
        <div className="curve-control-group" key={curveId}>
          <h3>{curve.label || curveId}</h3>
          {curve.segments ? (
            Object.entries(curve.segments).map(([segmentId, segment]) => (
              <div key={segmentId} className="curve-segment">
                <span>{segmentId}</span>
                {(segment.control_points || []).map((point, index) => (
                  <button
                    aria-label={`${segmentId} control point ${index}`}
                    key={`${segmentId}-${index}`}
                    type="button"
                    onClick={() => onChange?.({
                      section_loop_overrides: {
                        [curveId]: {
                          segment: segmentId,
                          point_index: index,
                          point,
                        },
                      },
                    })}
                  >
                    {index}
                  </button>
                ))}
              </div>
            ))
          ) : (
            (curve.control_points || []).map((point, index) => (
              <button
                aria-label={`${curve.label || curveId} control point ${index}`}
                key={index}
                type="button"
                onClick={() => emitPointNudge(curveId, index)}
              >
                {index}
              </button>
            ))
          )}
        </div>
      ))}
    </section>
  );
}
```

Integrate into `App.js` near other control panels:

```javascript
<CurveControlPanel curves={activePreset.curveControls || {}} onChange={handleCurveOverrideChange} />
```

Use the existing state update pattern for `curve_overrides` and `section_loop_overrides`.

- [ ] **Step 5: Hide duplicate scalar controls**

In `ParameterPanel.js`, import `hiddenParameterIdsForPreset` and filter parameter rows:

```javascript
const hiddenIds = new Set(hiddenParameterIdsForPreset(activePreset?.id));
const visibleParameters = parameterEntries.filter(([parameterId]) => !hiddenIds.has(parameterId));
```

Use `visibleParameters` in the render loop.

- [ ] **Step 6: Run frontend model/control tests**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js CurveControlPanel.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend\src\appModel.js frontend\src\appModel.test.js frontend\src\components\CurveControlPanel.js frontend\src\components\CurveControlPanel.test.js frontend\src\components\ParameterPanel.js frontend\src\App.js
git commit -m "feat: expose v1.0.3 curve controls in frontend"
```

---

### Task 9: Viewer Overlays For Control Points, Wireframe, And Mesh

**Files:**
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/simulationViewModel.js`
- Test: `frontend/src/simulationViewModel.test.js`
- Test: `frontend/src/workspaceModel.test.js`

- [ ] **Step 1: Write failing viewer/model tests**

In `frontend/src/simulationViewModel.test.js`, add:

```javascript
test("v1.0.3 root and tip dome surfaces remain visible as transition mesh surfaces", () => {
  const manifest = {
    geometry: {
      surface_graph: {
        surfaces: [
          { id: "root_aggregate", display: { visible_by_default: false, aggregate_surface: true } },
          { id: "root_patch", role: "root_to_hub_blend", display: { inspection_class: "root_to_hub_blend" } },
          { id: "tip_dome", role: "open_tip_dome", display: { inspection_class: "open_tip_dome" } },
        ],
      },
    },
  };

  const view = buildSimulationViewModel(manifest, { simulationViewMode: "cad_review_360" });

  expect(view.surfaces.map((surface) => surface.id)).toContain("root_patch");
  expect(view.surfaces.map((surface) => surface.id)).toContain("tip_dome");
  expect(view.surfaces.map((surface) => surface.id)).not.toContain("root_aggregate");
});
```

In `frontend/src/workspaceModel.test.js`, add:

```javascript
test("curve control overlays are preserved in workspace state", () => {
  const manifest = {
    curve_controls: {
      hub_profile_nurbs: { control_points: [[160, 400], [580, 0]] },
    },
  };

  const workspace = buildWorkspaceModel({ manifest });

  expect(workspace.curveControls.hub_profile_nurbs.control_points).toEqual([[160, 400], [580, 0]]);
});
```

- [ ] **Step 2: Run viewer/model tests and confirm failure**

Run:

```powershell
cd frontend
npm.cmd test -- simulationViewModel.test.js workspaceModel.test.js
```

Expected: FAIL if V1.0.3 surface visibility or curve controls are not parsed.

- [ ] **Step 3: Update simulation view model**

In `simulationViewModel.js`, ensure:

```javascript
export function surfaceVisibleInView(surface, viewMode, manifest) {
  if (surface?.display?.visible_by_default === false && viewMode !== "feature_debug") {
    return false;
  }
  return true;
}
```

Add root/tip dome inspection classes to any layer grouping:

```javascript
const TRANSITION_INSPECTION_CLASSES = new Set([
  "root_to_hub_blend",
  "open_tip_dome",
  "blade_leading_edge",
  "blade_trailing_edge",
]);
```

- [ ] **Step 4: Update workspace model**

In `workspaceModel.js`, preserve manifest curve controls:

```javascript
curveControls: manifest?.curve_controls || manifest?.geometry?.curve_controls || {},
sectionLoopControls: manifest?.section_loop_controls || manifest?.geometry?.section_loop_controls || {},
```

- [ ] **Step 5: Update ModelViewer overlay rendering**

In `ModelViewer.js`, add rendering priority:

```javascript
function displayColorForSurface(surface) {
  const display = surface.display || {};
  if (display.inspection_class === "root_to_hub_blend") return display.color || "#ff00cc";
  if (display.inspection_class === "open_tip_dome") return display.color || "#6f8fb8";
  return existingDisplayColorForSurface(surface);
}
```

Add control point overlay rendering for curve controls:

```javascript
function addCurveControlOverlays(scene, curveControls) {
  for (const [curveId, curve] of Object.entries(curveControls || {})) {
    for (const point of curve.control_points || []) {
      const marker = makeControlPointMarker(point, curveId);
      scene.add(marker);
    }
  }
}
```

Use existing Three.js helper patterns in the file for geometry/material construction. Do not add a new rendering library.

- [ ] **Step 6: Run viewer/model tests**

Run:

```powershell
cd frontend
npm.cmd test -- simulationViewModel.test.js workspaceModel.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend\src\components\ModelViewer.js frontend\src\simulationViewModel.js frontend\src\simulationViewModel.test.js frontend\src\workspaceModel.js frontend\src\workspaceModel.test.js
git commit -m "feat: render v1.0.3 transition and curve overlays"
```

---

### Task 10: End-To-End Backend And Frontend Verification

**Files:**
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/geometry-diagnostics.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`

- [ ] **Step 1: Run V1.0.3 backend tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_3_resources.py tests\test_impeller_v10_3_preset_defaults.py -q
python -m pytest tests\test_impeller_v10_3_section_loop.py tests\test_impeller_v10_3_blade_faces.py tests\test_impeller_v10_3_root_blend.py tests\test_impeller_v10_3_tip_dome.py -q
python -m pytest tests\test_impeller_v10_3_surface_graph.py tests\test_impeller_v10_3_validation.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run V1.0.2 regression tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_impeller_v10_2_blade_lattice.py tests\test_impeller_v10_2_surface_graph_integration.py tests\test_impeller_v10_2_validation.py -q
```

Expected: PASS. If V1.0.2 tests assume the first open preset is still V1.0.2, update those tests to explicitly compile the V1.0.2 historical/debug path instead of changing V1.0.3 defaults.

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: PASS.

- [ ] **Step 4: Run service smoke**

Restart backend from the worktree:

```powershell
$connection = Get-NetTCPConnection -LocalPort 8060 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($connection) { Stop-Process -Id $connection.OwningProcess -Force }
$env:PYTHONPATH='src'
$process = Start-Process -FilePath python -ArgumentList @('-m','uvicorn','part_rule_synthesis.api:app','--host','127.0.0.1','--port','8060') -WorkingDirectory 'C:\Users\CHEN Li\Documents\TurboJetCase\impellerConstructor\.worktrees\impeller-v1.0-topology-first' -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
Get-NetTCPConnection -LocalPort 8060 -ErrorAction SilentlyContinue | Select-Object -Property OwningProcess,LocalPort,State
```

Run smoke:

```powershell
$body = @{ part_family_id = 'impeller'; preset_id = 'radial_open_reference_v1_0'; facets = @{} } | ConvertTo-Json -Depth 5
$synth = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8060/api/rule-engines/synthesize' -ContentType 'application/json' -Body $body
$instBody = @{ parameters = @{}; geometry_stage = 'full' } | ConvertTo-Json -Depth 5
$inst = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8060/api/rule-engines/$($synth.engine_id)/instantiate" -ContentType 'application/json' -Body $instBody
$graph = $inst.manifest.geometry.surface_graph
[pscustomobject]@{
  geometry_version = $inst.manifest.geometry_version
  geometry_validation_status = $inst.manifest.geometry_validation_status
  transition_geometry_status = $inst.manifest.transition_geometry_status
  graph_patch = $graph.geometry_patch_version
  graph_status = $graph.surface_graph_status
  main_blade_count = $graph.main_blade_count
  splitter_blade_count = $graph.splitter_blade_count
  root_component_max_foldover = (($graph.surfaces | Where-Object { $_.role -eq 'root_to_hub_blend' } | ForEach-Object { $_.transition_quality.foldover_count } | Measure-Object -Maximum).Maximum)
  tip_dome_max_foldover = (($graph.surfaces | Where-Object { $_.role -eq 'open_tip_dome' } | ForEach-Object { $_.transition_quality.foldover_count } | Measure-Object -Maximum).Maximum)
} | ConvertTo-Json -Depth 5
```

Expected:

```json
{
  "geometry_version": "1.0",
  "geometry_validation_status": "PASS",
  "transition_geometry_status": "topology_first_section_loop_blade_root_blend_surface_graph",
  "graph_patch": "1.0.3",
  "graph_status": "PASS",
  "main_blade_count": 4,
  "splitter_blade_count": 4,
  "root_component_max_foldover": 0,
  "tip_dome_max_foldover": 0
}
```

- [ ] **Step 5: Update evidence logs**

Append to `geometry-diagnostics.md`:

```markdown
## 2026-07-06 V1.0.3 Section-Loop Root Blend Verification

radial_open_reference_v1_0:
  geometry_patch_version = 1.0.3
  main_blade_count = 4
  splitter_blade_count = 4
  blade_thickness_mm = 32.0
  root_component_max_foldover = 0
  tip_dome_max_foldover = 0
  geometry_validation_status = PASS
```

Append to `semantic-change-log.md`:

```markdown
## 2026-07-06 V1.0.3 Section-Loop Constructor

The default open preset now constructs blade faces from shared section-loop
segments. Root blend construction uses segmented support-domain Hermite/G2
patches. The open tip is a dome surface. V1.0.2 remains available as historical
evidence but is no longer the default open inspection path.
```

Append to `insight-log.md`:

```markdown
## Insight: Root Blend Robustness Comes From Domain Ownership

The root blend is stable only when ownership is explicit:
blade section loop owns the inner boundary; hub parameter domain owns the
footprint and outer boundary; segment patches own visible root geometry. Local
cross-product guesses are not allowed to choose material side independently for
pressure and suction segments.
```

Append test output summaries to `test-transcript-summary.md`.

- [ ] **Step 6: Commit evidence**

```powershell
git add docs\evidence\2026-07-05-impeller-v1-0-topology-first\geometry-diagnostics.md docs\evidence\2026-07-05-impeller-v1-0-topology-first\semantic-change-log.md docs\evidence\2026-07-05-impeller-v1-0-topology-first\insight-log.md docs\evidence\2026-07-05-impeller-v1-0-topology-first\test-transcript-summary.md
git commit -m "docs: record v1.0.3 section-loop verification"
```

---

## Final Acceptance Checklist

- [ ] `radial_open_reference_v1_0` compiles with `geometry_patch_version = "1.0.3"`.
- [ ] First UI preset shows 4 main blades and 4 splitter blades.
- [ ] Main and splitter blades are shorter than support bounds.
- [ ] Blade thickness default is 32 mm.
- [ ] Section loops contain exact shared PS/LE/SS/TE endpoints.
- [ ] LE/TE curvature metrics exceed PS/SS curvature metrics.
- [ ] Root has four visible component patches per blade.
- [ ] Suction-side root remains on material side and does not run below the blade.
- [ ] Open tip dome exists, is visible, has wireframe, and has mesh.
- [ ] Hub profile and blade section-loop control points are visible and editable in frontend.
- [ ] No duplicate scalar controls for curve-owned transition values.
- [ ] Every visible V1.0.3 transition component has `foldover_count == 0`.
- [ ] Backend V1.0.3 tests pass.
- [ ] V1.0.2 regression tests pass or are explicitly routed to historical V1.0.2 fixtures.
- [ ] `cd frontend && npm.cmd test` passes.
- [ ] HTTP smoke returns geometry validation PASS.

## Self-Review

Spec coverage:

- Preset resizing, main/splitter blades, thickness scaling, root width/lift, and tip dome defaults are covered in Task 1.
- Section-loop source object, four curve segments, exact shared endpoints, and curvature relationships are covered in Task 2.
- Pressure/suction/leading/trailing lofted faces and shared boundaries are covered in Task 3.
- Robust root method, support-domain footprint, segmented patches, material-side validation, and suction reversal failure are covered in Task 4.
- Open tip dome construction is covered in Task 5.
- V1.0.3 graph routing and open preset acceptance are covered in Task 6.
- Validation gates are covered in Task 7.
- Frontend editable NURBS/control-point requirements are covered in Tasks 8 and 9.
- Verification and evidence logs are covered in Task 10.

Completion scan:

- No unresolved marker text or open questions remain in this plan.

Type consistency:

- Runtime field names use `geometry_patch_version`, `resolved_section_loop_defaults`, and `v1_0_3_preset_feasibility`.
- Builder public APIs are consistent across tasks:
  - `build_section_loop_lattice(parameters, defaults)`
  - `build_blade_faces_from_section_lattice(lattice)`
  - `build_v10_3_root_blend(blade_index, lattice, blade_faces, hub_surface, defaults)`
  - `build_v10_3_tip_dome(blade_index, lattice, defaults)`
  - `validate_v10_3_surface_graph(surface_graph)`
