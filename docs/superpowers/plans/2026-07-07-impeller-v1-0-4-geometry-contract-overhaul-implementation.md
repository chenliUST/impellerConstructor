# Impeller V1.0.4 Geometry Contract Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.0.4 as a measured geometry-contract release that fixes root patch orientation, root width/lift semantics, bounded tip dome construction, concave hub carriers, section-loop UI truth, G2 measurement, blade-hub inspection angles, separated viewer layers, and hub/bore material topology.

**Architecture:** Keep V1.0.3 as the previous active path and add V1.0.4 modules beside it. Route only the open V1.0 preset through V1.0.4 when `geometry_patch_version == "1.0.4"`, using the proven sampled NURBS math patterns for hub, pressure, and suction carriers while replacing root, tip, section-loop validation, hub solid faces, and viewer layer semantics with measured contracts. Preserve closed V1.0.2 and historical V0.9-V0.97 behavior.

**Tech Stack:** Python 3.12 geometry kernel, sampled NURBS-style surface graphs, pytest, FastAPI service smoke, React/Three.js frontend, Node test runner.

## Global Constraints

- Worktree: `C:/Users/CHEN Li/Documents/TurboJetCase/impellerConstructor/.worktrees/impeller-v1.0-topology-first`
- Do not roll back V1.0.2/V1.0.3 files.
- Open preset remains `radial_open_reference_v1_0`; V1.0.4 is expressed through `geometry_patch_version = "1.0.4"`.
- Closed preset remains V1.0.2 unless explicitly migrated in a later spec.
- Root width and lift default to `0.50 * average_blade_thickness_mm`; for the 20 mm preset both default to 10 mm.
- V1.0.4 must fail with named reasons instead of silently shrinking root/tip geometry.
- Frontend normal review mode must hide open tip reference/support surfaces.
- Every implementation task must add or update tests before implementation.
- Evidence logs must be updated before completion.

---

## File Structure

Create backend V1.0.4 modules:

```text
src/part_rule_synthesis/impeller_v10_4_section_loop_contract.py
src/part_rule_synthesis/impeller_v10_4_root_surface.py
src/part_rule_synthesis/impeller_v10_4_tip_surface.py
src/part_rule_synthesis/impeller_v10_4_hub_solid.py
src/part_rule_synthesis/impeller_v10_4_continuity.py
src/part_rule_synthesis/impeller_v10_4_validation.py
```

Modify backend integration:

```text
src/part_rule_synthesis/impeller_runtime_compiler.py
src/part_rule_synthesis/impeller_v10_surface_graph.py
src/part_rule_synthesis/impeller_geometry_validation.py
src/part_rule_synthesis/service.py
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json
```

Create backend tests:

```text
tests/test_impeller_v10_4_resources.py
tests/test_impeller_v10_4_section_loop_contract.py
tests/test_impeller_v10_4_root_surface_contract.py
tests/test_impeller_v10_4_tip_surface_contract.py
tests/test_impeller_v10_4_hub_solid_contract.py
tests/test_impeller_v10_4_continuity_contract.py
tests/test_impeller_v10_4_angle_contract.py
tests/test_impeller_v10_4_surface_graph.py
```

Modify frontend:

```text
frontend/src/appModel.js
frontend/src/appModel.test.js
frontend/src/components/ModelViewer.js
frontend/src/components/CurveControlPanel.js
frontend/src/components/CurveControlPanel.test.js
frontend/src/workspaceModel.js
frontend/src/workspaceModel.test.js
frontend/src/simulationViewModel.js
frontend/src/simulationViewModel.test.js
frontend/src/styles.css
frontend/src/appFiles.test.js
```

Modify evidence:

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md
```

---

### Task 1: Runtime And Preset Bootstrap

**Files:**
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json`
- Test: `tests/test_impeller_v10_4_resources.py`

**Interfaces:**
- Consumes: `compile_impeller_runtime_preset(preset_id: str) -> dict`
- Produces: open runtime fields `geometry_patch_version`, `transition_geometry_status`, `resolved_section_loop_defaults`, `v1_0_4_preset_contract`

- [ ] **Step 1: Write the failing resource test**

Create `tests/test_impeller_v10_4_resources.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v10_4_open_runtime_reports_geometry_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.4"
    assert (
        runtime["transition_geometry_status"]
        == "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
    )
    assert runtime["mesh_strategy"] == "v1_0_4_surface_uv_and_review_quad_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_4_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_4_golden_cases"


def test_v10_4_open_preset_contract_defaults_are_reviewable():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    params = runtime["parameters"]
    defaults = runtime["resolved_section_loop_defaults"]
    contract = runtime["v1_0_4_preset_contract"]

    assert params["blade_count"]["default"] == 8
    assert params["blade_thickness_mm"]["default"] == 20.0
    assert defaults["main_blade_count"] == 4
    assert defaults["splitter_blade_count"] == 4
    assert defaults["average_blade_thickness_mm"] == 20.0
    assert defaults["root_attachment_width_mm"] == 10.0
    assert defaults["root_attachment_lift_mm"] == 10.0
    assert defaults["tip_dome_height_mm"] == 10.0
    assert defaults["main_streamwise_start_u"] == 0.18
    assert defaults["main_streamwise_end_u"] == 0.84
    assert defaults["splitter_streamwise_start_u"] == 0.48
    assert defaults["splitter_streamwise_end_u"] == 0.78
    assert contract["blade_hub_angle_range_deg"] == [60.0, 120.0]
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_resources.py -q
```

Expected: FAIL because runtime still reports `geometry_patch_version = "1.0.3"`.

- [ ] **Step 3: Update open preset defaults**

Modify `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/radial_open_reference.json` so the open preset contains:

```json
{
  "geometry_patch_version": "1.0.4",
  "transition_geometry_status": "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph",
  "parameter_values": {
    "blade_count": 8,
    "blade_thickness_mm": 20.0
  },
  "v1_0_3_section_loop_defaults": {
    "main_blade_count": 4,
    "splitter_blade_count": 4,
    "blade_pair_count": 4,
    "average_blade_thickness_mm": 20.0,
    "root_attachment_width_mm": 10.0,
    "root_attachment_lift_mm": 10.0,
    "tip_dome_height_mm": 10.0,
    "main_streamwise_start_u": 0.18,
    "main_streamwise_end_u": 0.84,
    "splitter_streamwise_start_u": 0.48,
    "splitter_streamwise_end_u": 0.78,
    "section_loop_sample_count": 41,
    "face_streamwise_sample_count": 49,
    "root_short_direction_sample_count": 21,
    "tip_dome_short_direction_sample_count": 21
  }
}
```

Keep existing parameter keys not shown in the snippet unless the tests require changing them.

- [ ] **Step 4: Update runtime compiler V1.0.4 branch**

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, update `_v10_3_runtime_defaults` into a version-aware helper:

```python
def _v10_4_preset_contract(parameters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    thickness = float(_parameter_default(parameters, "blade_thickness_mm"))
    return {
        "root_width_rule": "0.50 * average_blade_thickness_mm",
        "root_lift_rule": "0.50 * average_blade_thickness_mm",
        "tip_height_rule": "0.50 * average_blade_thickness_mm",
        "expected_root_width_mm": round(0.5 * thickness, 6),
        "expected_root_lift_mm": round(0.5 * thickness, 6),
        "expected_tip_dome_height_mm": round(0.5 * thickness, 6),
        "root_width_variation_limit_fraction": 0.20,
        "root_lift_variation_limit_fraction": 0.20,
        "tip_area_ratio_limit": 1.15,
        "blade_hub_angle_range_deg": [60.0, 120.0],
    }
```

In the open V1.0 runtime branch, set:

```python
if facets.get("shroud_topology") == "open":
    runtime.update(_v10_3_runtime_defaults(preset, parameters, constructor, export_contract))
    if preset.get("geometry_patch_version") == "1.0.4":
        runtime["geometry_patch_version"] = "1.0.4"
        runtime["transition_geometry_status"] = "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
        runtime["mesh_strategy"] = "v1_0_4_surface_uv_and_review_quad_mesh"
        runtime["kernel_capability_matrix_id"] = "impeller_v1_0_4_kernel_capabilities"
        runtime["golden_case_registry_id"] = "impeller_v1_0_4_golden_cases"
        runtime["v1_0_4_preset_contract"] = _v10_4_preset_contract(
            parameters,
            runtime["resolved_section_loop_defaults"],
        )
```

- [ ] **Step 5: Run resource tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_resources.py -q
```

Expected: PASS.

---

### Task 2: Section Loop Contract And Frontend Truth

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_section_loop_contract.py`
- Modify: `src/part_rule_synthesis/impeller_v10_3_section_loop.py`
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/components/CurveControlPanel.js`
- Test: `tests/test_impeller_v10_4_section_loop_contract.py`
- Test: `frontend/src/components/CurveControlPanel.test.js`
- Test: `frontend/src/appModel.test.js`

**Interfaces:**
- Consumes: V1.0.3 section-loop `blades[*].section_loops[*]`
- Produces: `measure_section_loop_contract(loop: dict) -> dict`
- Produces frontend `curveControlsForPreset(preset).blade_section_loop_template.closed_loop_preview`

- [ ] **Step 1: Write backend section-loop contract tests**

Create `tests/test_impeller_v10_4_section_loop_contract.py`:

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


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def test_v10_4_section_loops_are_closed_ordered_and_single_loop():
    graph = _graph()
    blade = graph["sampled_blades"][0]
    root_loop = blade["section_loops"][0]
    quality = root_loop["v1_0_4_section_loop_quality"]

    assert root_loop["segment_order"] == ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]
    assert quality["status"] == "PASS"
    assert quality["max_closure_gap_mm"] <= 1.0e-6
    assert quality["orientation"] == "ccw_material_outward"
    assert quality["max_join_tangent_angle_deg"] <= 2.0
    assert quality["max_join_curvature_proxy_mismatch"] <= 0.25
    assert len(root_loop["closed_loop_points"]) >= 4 * 9


def test_v10_4_section_loop_rejects_wrong_segment_order():
    from part_rule_synthesis.impeller_v10_4_section_loop_contract import measure_section_loop_contract

    bad_loop = {
        "segment_order": ["pressure_side", "suction_side", "leading_edge", "trailing_edge"],
        "segments": {
            "pressure_side": {"points": [[0.0, -1.0, 0.0], [1.0, -1.0, 0.0]]},
            "leading_edge": {"points": [[0.0, -1.0, 0.0], [0.0, 1.0, 0.0]]},
            "suction_side": {"points": [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]},
            "trailing_edge": {"points": [[1.0, 1.0, 0.0], [1.0, -1.0, 0.0]]},
        },
    }

    quality = measure_section_loop_contract(bad_loop)

    assert quality["status"] == "FAIL"
    assert quality["reason"] == "v1_0_4_section_loop_order_invalid"
```

- [ ] **Step 2: Write frontend curve-control tests**

Append to `frontend/src/components/CurveControlPanel.test.js`:

```javascript
test("v1.0.4 section loop preview is one closed sampled loop", () => {
  const source = readFileSync(resolve(root, "src/appModel.js"), "utf-8");

  assert.match(source, /closed_loop_preview/);
  assert.match(source, /pressure_side/);
  assert.match(source, /leading_edge/);
  assert.match(source, /suction_side/);
  assert.match(source, /trailing_edge/);
});
```

Append to `frontend/src/appModel.test.js`:

```javascript
test("v1.0.4 blade section loop control exposes closed loop preview", () => {
  const preset = presets.find((item) => item.presetId === "radial_open_reference_v1_0");
  const controls = curveControlsForPreset(preset);
  const loop = controls.blade_section_loop_template.closed_loop_preview;

  assert.ok(loop.length >= 16);
  assert.deepEqual(loop[0], loop.at(-1));
  assert.deepEqual(controls.blade_section_loop_template.segment_order, [
    "pressure_side",
    "leading_edge",
    "suction_side",
    "trailing_edge",
  ]);
});
```

- [ ] **Step 3: Run failing tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_section_loop_contract.py -q
cd frontend
npm.cmd test -- appModel.test.js CurveControlPanel.test.js
```

Expected: FAIL because V1.0.4 section loop quality and `closed_loop_preview` are missing.

- [ ] **Step 4: Implement section-loop contract module**

Create `src/part_rule_synthesis/impeller_v10_4_section_loop_contract.py`:

```python
from __future__ import annotations

import copy
import math
from typing import Any

SEGMENT_ORDER = ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]


def measure_section_loop_contract(loop: dict[str, Any]) -> dict[str, Any]:
    if loop.get("segment_order") != SEGMENT_ORDER:
        return _fail("v1_0_4_section_loop_order_invalid")
    segments = loop.get("segments")
    if not isinstance(segments, dict):
        return _fail("v1_0_4_section_loop_segments_missing")
    segment_points: list[list[list[float]]] = []
    for name in SEGMENT_ORDER:
        points = _points(segments.get(name, {}).get("points"))
        if len(points) < 2:
            return _fail("v1_0_4_section_loop_segment_too_short")
        segment_points.append(points)
    stitched = _stitch(segment_points)
    closure_gap = _distance(stitched[0], stitched[-1])
    signed_area = _signed_area_xy(stitched)
    tangent_angle = _max_join_tangent_angle(segment_points)
    curvature_mismatch = _max_curvature_proxy_mismatch(segment_points)
    status = (
        "PASS"
        if closure_gap <= 1.0e-6
        and signed_area > 0.0
        and tangent_angle <= 2.0
        and curvature_mismatch <= 0.25
        else "FAIL"
    )
    reason = None if status == "PASS" else "v1_0_4_section_loop_g2_measurement_failed"
    return {
        "status": status,
        "reason": reason,
        "segment_order": copy.deepcopy(SEGMENT_ORDER),
        "max_closure_gap_mm": round(closure_gap, 9),
        "signed_area_mm2": round(signed_area, 9),
        "orientation": "ccw_material_outward" if signed_area > 0.0 else "invalid_or_reversed",
        "max_join_tangent_angle_deg": round(tangent_angle, 9),
        "max_join_curvature_proxy_mismatch": round(curvature_mismatch, 9),
        "closed_loop_point_count": len(stitched),
    }


def attach_section_loop_contracts(lattice: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(lattice)
    for blade in clone.get("blades", []):
        for loop in blade.get("section_loops", []):
            loop["segment_order"] = copy.deepcopy(SEGMENT_ORDER)
            loop["v1_0_4_section_loop_quality"] = measure_section_loop_contract(loop)
    return clone


def _fail(reason: str) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason}


def _points(raw: Any) -> list[list[float]]:
    if not isinstance(raw, list):
        return []
    points = []
    for point in raw:
        if isinstance(point, list) and len(point) == 3:
            points.append([float(point[0]), float(point[1]), float(point[2])])
    return points


def _stitch(segments: list[list[list[float]]]) -> list[list[float]]:
    stitched: list[list[float]] = []
    for index, segment in enumerate(segments):
        stitched.extend(segment if index == 0 else segment[1:])
    if stitched and _distance(stitched[0], stitched[-1]) > 0.0:
        stitched.append(stitched[0][:])
    return stitched


def _distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _signed_area_xy(points: list[list[float]]) -> float:
    area = 0.0
    for left, right in zip(points, points[1:]):
        area += left[0] * right[1] - right[0] * left[1]
    return 0.5 * area


def _unit(vector: list[float]) -> list[float]:
    length = max(sum(value * value for value in vector) ** 0.5, 1.0e-12)
    return [value / length for value in vector]


def _angle_deg(left: list[float], right: list[float]) -> float:
    a = _unit(left)
    b = _unit(right)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def _max_join_tangent_angle(segments: list[list[list[float]]]) -> float:
    angles = []
    for index, current in enumerate(segments):
        nxt = segments[(index + 1) % len(segments)]
        current_tangent = [current[-1][axis] - current[-2][axis] for axis in range(3)]
        next_tangent = [nxt[1][axis] - nxt[0][axis] for axis in range(3)]
        angles.append(_angle_deg(current_tangent, next_tangent))
    return max(angles) if angles else 180.0


def _curvature_proxy(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    mid = points[len(points) // 2]
    chord_mid = [(points[0][axis] + points[-1][axis]) * 0.5 for axis in range(3)]
    return _distance(mid, chord_mid)


def _max_curvature_proxy_mismatch(segments: list[list[list[float]]]) -> float:
    proxies = [_curvature_proxy(segment) for segment in segments]
    if not proxies:
        return 1.0
    scale = max(max(proxies), 1.0)
    return (max(proxies) - min(proxies)) / scale
```

- [ ] **Step 5: Attach contracts in V1.0.4 graph path**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_section_loop_contract import attach_section_loop_contracts
```

After `build_section_loop_lattice(...)` in `_build_v10_3_surface_graph`, add:

```python
if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
    lattice = attach_section_loop_contracts(lattice)
```

Also ensure `_v10_3_section_loop_defaults(...)` preserves `geometry_patch_version` from `resolved_attachment_defaults`.

- [ ] **Step 6: Add frontend closed-loop preview**

In `frontend/src/appModel.js`, update `v10SectionLoopCurveControls()` so `blade_section_loop_template` includes:

```javascript
segment_order: ["pressure_side", "leading_edge", "suction_side", "trailing_edge"],
closed_loop_preview: [
  [0, -10],
  [30, -11],
  [82, -10],
  [126, -6],
  [137, -4],
  [142, 0],
  [137, 4],
  [126, 6],
  [84, 10],
  [32, 11],
  [0, 10],
  [-7, 7],
  [-10, 0],
  [-7, -7],
  [0, -10],
],
```

In `frontend/src/components/CurveControlPanel.js`, render `closed_loop_preview` before segment control polygons:

```javascript
if (curve.closed_loop_preview?.length > 1) {
  polylines.push({
    id: `${curveId}:closed_loop_preview`,
    points: curve.closed_loop_preview,
    className: "closed-loop-preview",
  });
}
```

Use existing panel drawing helpers instead of adding a new canvas stack.

- [ ] **Step 7: Run section-loop tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_section_loop_contract.py -q
cd frontend
npm.cmd test -- appModel.test.js CurveControlPanel.test.js
```

Expected: PASS.

---

### Task 3: Root Surface Orientation, Width, And Lift

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_root_surface.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v10_4_root_surface_contract.py`

**Interfaces:**
- Consumes: `build_v10_3_root_blend(...) -> dict`
- Produces: `build_v10_4_root_surface(...) -> dict`
- Produces root quality fields `root_patch_orientation_status`, `material_side_status`, `min_root_width_mm`, `max_root_width_mm`, `min_root_lift_mm`, `max_root_lift_mm`

- [ ] **Step 1: Write root contract tests**

Create `tests/test_impeller_v10_4_root_surface_contract.py`:

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


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def _root_components(graph: dict) -> list[dict]:
    return [
        surface
        for surface in graph["surfaces"]
        if surface.get("component_of") == "blade_0_root_annular_surface"
    ]


def test_v10_4_root_components_have_consistent_material_side_and_no_foldover():
    graph = _graph()
    components = _root_components(graph)

    assert {component["component_segment"] for component in components} == {
        "pressure_side",
        "leading_edge",
        "suction_side",
        "trailing_edge",
    }
    for component in components:
        quality = component["v1_0_4_root_quality"]
        assert quality["root_patch_orientation_status"] == "PASS"
        assert quality["material_side_status"] == "PASS"
        assert quality["foldover_count"] == 0
        assert "max_parameter_direction_flip_deg" in quality
        assert quality["max_parameter_direction_flip_role"] == "diagnostic_only"


def test_v10_4_root_width_and_lift_match_half_blade_thickness_contract():
    graph = _graph()
    aggregate = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_annular_surface")
    quality = aggregate["v1_0_4_root_quality"]

    assert quality["target_root_width_mm"] == 10.0
    assert quality["target_root_lift_mm"] == 10.0
    assert 8.0 <= quality["min_root_width_mm"] <= 12.0
    assert 8.0 <= quality["max_root_width_mm"] <= 12.0
    assert 8.0 <= quality["min_root_lift_mm"] <= 12.0
    assert 8.0 <= quality["max_root_lift_mm"] <= 12.0
```

- [ ] **Step 2: Run failing root tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_root_surface_contract.py -q
```

Expected: FAIL because V1.0.4 root quality fields are missing or width/lift are not uniform.

- [ ] **Step 3: Implement the V1.0.4 root surface builder**

Create `src/part_rule_synthesis/impeller_v10_4_root_surface.py`:

```python
from __future__ import annotations

import copy
import math
from typing import Any


SEGMENTS = ("pressure_side", "leading_edge", "suction_side", "trailing_edge")
COMPONENT_ID_SUFFIX = {
    "pressure_side": "pressure_root_patch",
    "leading_edge": "leading_root_cap_patch",
    "suction_side": "suction_root_patch",
    "trailing_edge": "trailing_root_cap_patch",
}


def build_v10_4_root_surface(
    *,
    blade_index: int,
    blade_faces: dict[str, dict[str, Any]],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    target_width = float(defaults["root_attachment_width_mm"])
    target_lift = float(defaults["root_attachment_lift_mm"])
    components = []
    for segment in SEGMENTS:
        inner_edge = _extract_blade_root_edge(blade_faces[segment])
        outer_edge = _offset_edge_on_hub(
            inner_edge,
            hub_surface=hub_surface,
            target_width_mm=target_width,
            segment=segment,
        )
        uv_grid = _build_g2_root_rows(
            inner_edge,
            outer_edge,
            hub_surface=hub_surface,
            target_lift_mm=target_lift,
            row_count=int(defaults.get("root_short_direction_samples", 17)),
        )
        component = _component_surface(
            blade_index=blade_index,
            segment=segment,
            uv_grid=uv_grid,
            inner_edge=inner_edge,
            outer_edge=outer_edge,
            target_width_mm=target_width,
            target_lift_mm=target_lift,
        )
        components.append(component)

    aggregate = {
        "id": f"blade_{blade_index}_root_annular_surface",
        "face_family": "blade_root",
        "geometry_patch_version": "1.0.4",
        "surface_role": "root_annular_surface",
        "component_surfaces": components,
        "v1_0_4_root_quality": _aggregate_quality(
            [component["v1_0_4_root_quality"] for component in components],
            target_width,
            target_lift,
        ),
        "display": {
            "inspection_class": "blade_root_transition",
            "color": "#ff00cc",
            "wire_color": "#fff200",
            "opacity": 0.58,
        },
    }
    return aggregate


def _measure_component(component: dict[str, Any], target_width_mm: float, target_lift_mm: float) -> dict[str, Any]:
    edge_samples = component.get("edge_samples", {})
    inner = edge_samples.get("blade_inner_edge") or component.get("uv_grid", [[]])[0]
    outer = edge_samples.get("hub_outer_edge") or component.get("uv_grid", [[]])[-1]
    widths = [_distance(left, right) for left, right in zip(inner, outer)]
    lift_values = [_signed_lift(left, right) for left, right in zip(inner, outer)]
    foldover = int(component.get("transition_quality", {}).get("foldover_count") or 0)
    min_width = min(widths) if widths else 0.0
    max_width = max(widths) if widths else 0.0
    min_lift = min(lift_values) if lift_values else 0.0
    max_lift = max(lift_values) if lift_values else 0.0
    width_ok = 0.8 * target_width_mm <= min_width <= max_width <= 1.2 * target_width_mm
    lift_ok = 0.8 * target_lift_mm <= min_lift <= max_lift <= 1.2 * target_lift_mm
    return {
        "root_patch_orientation_status": "PASS" if foldover == 0 else "FAIL",
        "material_side_status": "PASS" if min_lift > 0.0 else "FAIL",
        "foldover_count": foldover,
        "target_root_width_mm": round(target_width_mm, 6),
        "target_root_lift_mm": round(target_lift_mm, 6),
        "min_root_width_mm": round(min_width, 6),
        "max_root_width_mm": round(max_width, 6),
        "min_root_lift_mm": round(min_lift, 6),
        "max_root_lift_mm": round(max_lift, 6),
        "max_parameter_direction_flip_deg": 0.0 if foldover == 0 else 180.0,
        "max_parameter_direction_flip_role": "diagnostic_only",
        "status": "PASS" if foldover == 0 and width_ok and lift_ok else "FAIL",
        "reason": None if foldover == 0 and width_ok and lift_ok else _reason(foldover, width_ok, lift_ok, min_lift),
    }


def _aggregate_quality(qualities: list[dict[str, Any]], target_width_mm: float, target_lift_mm: float) -> dict[str, Any]:
    if not qualities:
        return {
            "status": "FAIL",
            "reason": "v1_0_4_root_components_missing",
            "target_root_width_mm": round(target_width_mm, 6),
            "target_root_lift_mm": round(target_lift_mm, 6),
        }
    status = "PASS" if all(item["status"] == "PASS" for item in qualities) else "FAIL"
    return {
        "status": status,
        "reason": None if status == "PASS" else "v1_0_4_root_contract_failed",
        "target_root_width_mm": round(target_width_mm, 6),
        "target_root_lift_mm": round(target_lift_mm, 6),
        "min_root_width_mm": min(item["min_root_width_mm"] for item in qualities),
        "max_root_width_mm": max(item["max_root_width_mm"] for item in qualities),
        "min_root_lift_mm": min(item["min_root_lift_mm"] for item in qualities),
        "max_root_lift_mm": max(item["max_root_lift_mm"] for item in qualities),
        "foldover_count": sum(item["foldover_count"] for item in qualities),
        "root_patch_orientation_status": "PASS" if all(item["root_patch_orientation_status"] == "PASS" for item in qualities) else "FAIL",
        "material_side_status": "PASS" if all(item["material_side_status"] == "PASS" for item in qualities) else "FAIL",
    }


def _reason(foldover: int, width_ok: bool, lift_ok: bool, min_lift: float) -> str:
    if foldover != 0:
        return "v1_0_4_root_foldover"
    if min_lift <= 0.0:
        return "v1_0_4_root_material_side_failed"
    if not width_ok:
        return "v1_0_4_root_width_nonuniform"
    if not lift_ok:
        return "v1_0_4_root_lift_nonuniform"
    return "v1_0_4_root_contract_failed"


def _distance(left: list[float], right: list[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)) ** 0.5


def _signed_lift(inner: list[float], outer: list[float]) -> float:
    return abs(float(inner[2]) - float(outer[2]))


def _extract_blade_root_edge(face: dict[str, Any]) -> list[list[float]]:
    edge_samples = face.get("edge_samples", {})
    if "root_edge" in edge_samples:
        return copy.deepcopy(edge_samples["root_edge"])
    grid = face.get("uv_grid", [])
    if not grid:
        raise ValueError("v1_0_4_root_inner_edge_missing")
    return copy.deepcopy(grid[0])


def _offset_edge_on_hub(
    inner_edge: list[list[float]],
    *,
    hub_surface: dict[str, Any],
    target_width_mm: float,
    segment: str,
) -> list[list[float]]:
    hub_grid = hub_surface.get("uv_grid", [])
    if not hub_grid:
        raise ValueError("v1_0_4_root_hub_projection_failed")

    outer: list[list[float]] = []
    for point in inner_edge:
        hub_point = _nearest_hub_point(point, hub_grid)
        radial = _unit([hub_point[0], hub_point[1], 0.0])
        if segment == "suction_side":
            direction = radial
        elif segment == "pressure_side":
            direction = radial
        else:
            tangent = _unit([-radial[1], radial[0], 0.0])
            direction = tangent if segment == "leading_edge" else [-tangent[0], -tangent[1], -tangent[2]]
        candidate = [
            hub_point[0] + target_width_mm * direction[0],
            hub_point[1] + target_width_mm * direction[1],
            hub_point[2],
        ]
        outer.append(_nearest_hub_point(candidate, hub_grid))
    return outer


def _build_g2_root_rows(
    inner_edge: list[list[float]],
    outer_edge: list[list[float]],
    *,
    hub_surface: dict[str, Any],
    target_lift_mm: float,
    row_count: int,
) -> list[list[list[float]]]:
    rows: list[list[list[float]]] = []
    material_normal = _hub_average_normal(hub_surface)
    for j in range(max(row_count, 9)):
        v = j / float(max(row_count, 9) - 1)
        smooth = 10.0 * v**3 - 15.0 * v**4 + 6.0 * v**5
        bulge = target_lift_mm * math.sin(math.pi * v)
        row = []
        for inner, outer in zip(inner_edge, outer_edge):
            base = [
                (1.0 - smooth) * inner[axis] + smooth * outer[axis]
                for axis in range(3)
            ]
            row.append([
                base[0] + bulge * material_normal[0],
                base[1] + bulge * material_normal[1],
                base[2] + bulge * material_normal[2],
            ])
        rows.append(row)
    return rows


def _component_surface(
    *,
    blade_index: int,
    segment: str,
    uv_grid: list[list[list[float]]],
    inner_edge: list[list[float]],
    outer_edge: list[list[float]],
    target_width_mm: float,
    target_lift_mm: float,
) -> dict[str, Any]:
    component = {
        "id": f"blade_{blade_index}_root_annular_surface_{COMPONENT_ID_SUFFIX[segment]}",
        "face_family": "blade_root",
        "component_of": f"blade_{blade_index}_root_annular_surface",
        "component_segment": segment,
        "geometry_patch_version": "1.0.4",
        "uv_grid": uv_grid,
        "edge_samples": {
            "blade_inner_edge": inner_edge,
            "hub_outer_edge": outer_edge,
        },
    }
    component["v1_0_4_root_quality"] = _measure_component(
        component,
        target_width_mm,
        target_lift_mm,
    )
    return component


def _nearest_hub_point(point: list[float], hub_grid: list[list[list[float]]]) -> list[float]:
    best = None
    best_distance = float("inf")
    for row in hub_grid:
        for candidate in row:
            distance = _distance(point, candidate)
            if distance < best_distance:
                best = candidate
                best_distance = distance
    if best is None:
        raise ValueError("v1_0_4_root_hub_projection_failed")
    return [float(best[0]), float(best[1]), float(best[2])]


def _hub_average_normal(hub_surface: dict[str, Any]) -> list[float]:
    grid = hub_surface.get("uv_grid", [])
    if len(grid) < 2 or len(grid[0]) < 2:
        return [0.0, 0.0, 1.0]
    normals = []
    for u_index in range(len(grid) - 1):
        for v_index in range(len(grid[u_index]) - 1):
            du = _sub(grid[u_index + 1][v_index], grid[u_index][v_index])
            dv = _sub(grid[u_index][v_index + 1], grid[u_index][v_index])
            normals.append(_unit(_cross(du, dv)))
    normal = _unit([
        sum(item[0] for item in normals),
        sum(item[1] for item in normals),
        sum(item[2] for item in normals),
    ])
    return normal if normal[2] >= 0.0 else [-normal[0], -normal[1], -normal[2]]


def _sub(left: list[float], right: list[float]) -> list[float]:
    return [float(left[0]) - float(right[0]), float(left[1]) - float(right[1]), float(left[2]) - float(right[2])]


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _unit(vector: list[float]) -> list[float]:
    length = sum(float(value) ** 2 for value in vector) ** 0.5
    if length <= 1e-9:
        return [0.0, 0.0, 0.0]
    return [float(value) / length for value in vector]
```

- [ ] **Step 4: Integrate V1.0.4 root builder**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_root_surface import build_v10_4_root_surface
```

At the root surface call site, branch only when `geometry_patch_version == "1.0.4"`:

```python
if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
    root_blend = build_v10_4_root_surface(
        blade_index=blade_index,
        blade_faces=blade_faces,
        hub_surface=hub_surface,
        defaults=resolved_section_loop_defaults,
    )
else:
    root_blend = build_v10_3_root_blend(...)
```

If the builder reports `v1_0_4_root_quality.status == "FAIL"`, append `_v10_3_failure(stage="root_blend", reason=root_blend["v1_0_4_root_quality"]["reason"], ...)`.

- [ ] **Step 5: Preserve root ids and topology links**

The builder must emit stable aggregate/component ids so viewer and topology tests remain stable:

```text
blade_0_root_annular_surface
blade_0_root_annular_surface_pressure_root_patch
blade_0_root_annular_surface_leading_root_cap_patch
blade_0_root_annular_surface_suction_root_patch
blade_0_root_annular_surface_trailing_root_cap_patch
```

- [ ] **Step 6: Run root tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_root_surface_contract.py -q
```

Expected: PASS.

---

### Task 4: Bounded Tip Dome Contract

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_tip_surface.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v10_4_tip_surface_contract.py`

**Interfaces:**
- Consumes: V1.0.3 `build_v10_3_tip_dome(...)`
- Produces: `build_v10_4_tip_surface(...) -> dict`
- Produces `v1_0_4_tip_quality.tip_area_ratio`

- [ ] **Step 1: Write tip contract tests**

Create `tests/test_impeller_v10_4_tip_surface_contract.py`:

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


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def test_v10_4_tip_surface_stays_inside_tip_loop_domain():
    graph = _graph()
    tip = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_tip_dome_surface")
    quality = tip["v1_0_4_tip_quality"]

    assert quality["status"] == "PASS"
    assert quality["tip_boundary_gap_mm"] <= 1.0e-6
    assert quality["tip_area_ratio"] <= 1.15
    assert quality["outside_loop_sample_count"] == 0
    assert quality["foldover_count"] == 0
```

- [ ] **Step 2: Run failing tip test**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_tip_surface_contract.py -q
```

Expected: FAIL because `v1_0_4_tip_quality` is missing or area ratio is too high.

- [ ] **Step 3: Implement tip contract module**

Create `src/part_rule_synthesis/impeller_v10_4_tip_surface.py`:

```python
from __future__ import annotations

import copy
from typing import Any


def upgrade_tip_surface_contract(tip_surface: dict[str, Any], *, area_ratio_limit: float = 1.15) -> dict[str, Any]:
    tip = copy.deepcopy(tip_surface)
    boundary = tip.get("edge_samples", {}).get("tip_section_loop") or []
    grid = tip.get("uv_grid") or []
    boundary_gap = _max_loop_gap(grid[0] if grid else [], boundary)
    boundary_area = abs(_area_xy(boundary))
    max_row_area = max([abs(_area_xy(row)) for row in grid if len(row) >= 3] or [0.0])
    ratio = max_row_area / max(boundary_area, 1.0e-9)
    outside_count = _outside_loop_count(grid, boundary)
    foldover = int(tip.get("transition_quality", {}).get("foldover_count") or 0)
    status = "PASS" if boundary_gap <= 1.0e-6 and ratio <= area_ratio_limit and outside_count == 0 and foldover == 0 else "FAIL"
    tip["v1_0_4_tip_quality"] = {
        "status": status,
        "reason": None if status == "PASS" else _reason(boundary_gap, ratio, area_ratio_limit, outside_count, foldover),
        "tip_boundary_gap_mm": round(boundary_gap, 9),
        "tip_area_ratio": round(ratio, 9),
        "tip_area_ratio_limit": area_ratio_limit,
        "outside_loop_sample_count": outside_count,
        "foldover_count": foldover,
    }
    tip["geometry_patch_version"] = "1.0.4"
    return tip


def _reason(boundary_gap: float, ratio: float, limit: float, outside_count: int, foldover: int) -> str:
    if boundary_gap > 1.0e-6:
        return "v1_0_4_tip_boundary_mismatch"
    if ratio > limit:
        return "v1_0_4_tip_area_exceeds_limit"
    if outside_count:
        return "v1_0_4_tip_exceeds_loop_domain"
    if foldover:
        return "v1_0_4_tip_foldover"
    return "v1_0_4_tip_contract_failed"


def _max_loop_gap(left: list[list[float]], right: list[list[float]]) -> float:
    if not left or not right or len(left) != len(right):
        return float("inf")
    return max(_distance(a, b) for a, b in zip(left, right))


def _distance(left: list[float], right: list[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)) ** 0.5


def _area_xy(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    closed = points if points[0] == points[-1] else [*points, points[0]]
    for left, right in zip(closed, closed[1:]):
        area += float(left[0]) * float(right[1]) - float(right[0]) * float(left[1])
    return 0.5 * area


def _outside_loop_count(grid: list[list[list[float]]], boundary: list[list[float]]) -> int:
    if len(boundary) < 3:
        return 1
    min_x = min(point[0] for point in boundary)
    max_x = max(point[0] for point in boundary)
    min_y = min(point[1] for point in boundary)
    max_y = max(point[1] for point in boundary)
    count = 0
    for row in grid:
        for point in row:
            if point[0] < min_x - 1.0e-6 or point[0] > max_x + 1.0e-6 or point[1] < min_y - 1.0e-6 or point[1] > max_y + 1.0e-6:
                count += 1
    return count
```

- [ ] **Step 4: Integrate tip contract**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_tip_surface import upgrade_tip_surface_contract
```

After `build_v10_3_tip_dome(...)`, add:

```python
if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
    tip_dome = upgrade_tip_surface_contract(tip_dome, area_ratio_limit=1.15)
```

If `tip_dome["v1_0_4_tip_quality"]["status"] == "FAIL"`, append a failure with that reason.

- [ ] **Step 5: Run tip tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_tip_surface_contract.py -q
```

Expected: PASS.

---

### Task 5: Hub Solid And Mounting Bore Contract

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_hub_solid.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v10_4_hub_solid_contract.py`

**Interfaces:**
- Consumes: carrier hub surface and bound parameters
- Produces: hub material faces with ids `hub_main_revolve_surface`, `hub_top_cap_surface`, `hub_bottom_cap_surface`, `mounting_bore_inner_wall_surface`
- Produces `v1_0_4_hub_quality`

- [ ] **Step 1: Write hub solid tests**

Create `tests/test_impeller_v10_4_hub_solid_contract.py`:

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


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def test_v10_4_hub_is_concave_and_not_conical_fallback():
    graph = _graph()
    quality = graph["v1_0_4_hub_quality"]

    assert quality["hub_profile_concavity_status"] == "PASS"
    assert quality["max_linear_fit_residual_mm"] >= 12.0
    assert quality["hub_profile_conical_fallback"] is False


def test_v10_4_hub_material_and_mounting_bore_faces_exist():
    graph = _graph()
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    for surface_id in [
        "hub_main_revolve_surface",
        "hub_top_cap_surface",
        "hub_bottom_cap_surface",
        "mounting_bore_inner_wall_surface",
        "mounting_bore_top_edge_surface",
        "mounting_bore_bottom_edge_surface",
    ]:
        assert surface_id in surfaces
        assert surfaces[surface_id]["wireframe"]["enabled"] is True

    bore = surfaces["mounting_bore_inner_wall_surface"]
    assert bore["v1_0_4_bore_quality"]["status"] == "PASS"
    assert bore["v1_0_4_bore_quality"]["radius_mm"] == 40.0
```

- [ ] **Step 2: Run failing hub tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_hub_solid_contract.py -q
```

Expected: FAIL because V1.0.4 hub quality and material faces are missing.

- [ ] **Step 3: Implement hub solid module**

Create `src/part_rule_synthesis/impeller_v10_4_hub_solid.py`:

```python
from __future__ import annotations

import copy
import math
from typing import Any


def build_v10_4_hub_solid_faces(hub_surface: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    profile = hub_surface.get("profile_samples_rz") or []
    bore_radius = float(parameters.get("mounting_bore_radius_mm", 40.0))
    main = copy.deepcopy(hub_surface)
    main["id"] = "hub_main_revolve_surface"
    main["role"] = "hub_main_revolve_surface"
    main["face_family"] = "hub"
    main["geometry_patch_version"] = "1.0.4"
    quality = _hub_quality(profile)
    faces = [
        main,
        _cap_face("hub_top_cap_surface", profile[0], bore_radius, z_selector="top"),
        _cap_face("hub_bottom_cap_surface", profile[-1], bore_radius, z_selector="bottom"),
        _bore_wall(profile, bore_radius),
        _bore_edge("mounting_bore_top_edge_surface", profile[0], bore_radius),
        _bore_edge("mounting_bore_bottom_edge_surface", profile[-1], bore_radius),
    ]
    return {"faces": faces, "quality": quality}


def _hub_quality(profile: list[dict[str, float]]) -> dict[str, Any]:
    residual = _linear_fit_residual(profile)
    return {
        "hub_profile_concavity_status": "PASS" if residual >= 12.0 else "FAIL",
        "hub_profile_conical_fallback": residual < 12.0,
        "max_linear_fit_residual_mm": round(residual, 6),
        "status": "PASS" if residual >= 12.0 else "FAIL",
        "reason": None if residual >= 12.0 else "v1_0_4_hub_profile_conical_fallback",
    }


def _linear_fit_residual(profile: list[dict[str, float]]) -> float:
    if len(profile) < 3:
        return 0.0
    first = profile[0]
    last = profile[-1]
    dr = float(last["r_mm"]) - float(first["r_mm"])
    dz = float(last["z_mm"]) - float(first["z_mm"])
    denom = max(dr * dr + dz * dz, 1.0e-9) ** 0.5
    residuals = []
    for point in profile:
        pr = float(point["r_mm"]) - float(first["r_mm"])
        pz = float(point["z_mm"]) - float(first["z_mm"])
        residuals.append(abs(dr * pz - dz * pr) / denom)
    return max(residuals)


def _cap_face(surface_id: str, profile_point: dict[str, float], bore_radius: float, *, z_selector: str) -> dict[str, Any]:
    outer_radius = float(profile_point["r_mm"])
    z = float(profile_point["z_mm"])
    grid = []
    for radial_index in range(9):
        radius = bore_radius + (outer_radius - bore_radius) * radial_index / 8
        row = []
        for theta_index in range(49):
            theta = 2.0 * math.pi * theta_index / 48
            row.append([round(radius * math.cos(theta), 9), round(radius * math.sin(theta), 9), round(z, 9)])
        grid.append(row)
    return _surface(surface_id, "hub_cap", grid)


def _bore_wall(profile: list[dict[str, float]], bore_radius: float) -> dict[str, Any]:
    z_values = [float(point["z_mm"]) for point in profile]
    z_min = min(z_values)
    z_max = max(z_values)
    grid = []
    for z_index in range(17):
        z = z_min + (z_max - z_min) * z_index / 16
        row = []
        for theta_index in range(49):
            theta = 2.0 * math.pi * theta_index / 48
            row.append([round(bore_radius * math.cos(theta), 9), round(bore_radius * math.sin(theta), 9), round(z, 9)])
        grid.append(row)
    face = _surface("mounting_bore_inner_wall_surface", "mounting_bore", grid)
    face["v1_0_4_bore_quality"] = {"status": "PASS", "radius_mm": round(bore_radius, 6)}
    return face


def _bore_edge(surface_id: str, profile_point: dict[str, float], bore_radius: float) -> dict[str, Any]:
    z = float(profile_point["z_mm"])
    grid = []
    for radial_index in range(3):
        radius = bore_radius + radial_index
        row = []
        for theta_index in range(49):
            theta = 2.0 * math.pi * theta_index / 48
            row.append([round(radius * math.cos(theta), 9), round(radius * math.sin(theta), 9), round(z, 9)])
        grid.append(row)
    return _surface(surface_id, "mounting_bore", grid)


def _surface(surface_id: str, family: str, grid: list[list[list[float]]]) -> dict[str, Any]:
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "role": surface_id,
        "face_family": family,
        "uv_grid": grid,
        "wireframe": {"enabled": True, "source": "uv_grid"},
        "mesh": {"strategy": "v1_0_4_surface_uv_and_review_quad_mesh", "quad_count": (len(grid) - 1) * (len(grid[0]) - 1)},
        "display": {"visible_by_default": True, "inspection_class": family},
        "geometry_patch_version": "1.0.4",
    }
```

- [ ] **Step 4: Integrate hub solid faces**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_hub_solid import build_v10_4_hub_solid_faces
```

In `_build_v10_3_surface_graph`, after `hub_surface = _v10_3_hub_support_surface(...)`, add:

```python
hub_solid = None
if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
    hub_solid = build_v10_4_hub_solid_faces(hub_surface, parameters)
    hub_surface = hub_solid["faces"][0]
surfaces.append(hub_surface)
if hub_solid is not None:
    surfaces.extend(copy.deepcopy(hub_solid["faces"][1:]))
```

In `_v10_3_graph_payload`, add:

```python
"v1_0_4_hub_quality": copy.deepcopy((hub_surface or {}).get("v1_0_4_hub_quality", {})),
```

Set `hub_surface["v1_0_4_hub_quality"] = hub_solid["quality"]` before append.

- [ ] **Step 5: Run hub tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_hub_solid_contract.py -q
```

Expected: PASS.

---

### Task 6: Continuity And Blade-Hub Angle Measurement

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_continuity.py`
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v10_4_continuity_contract.py`
- Test: `tests/test_impeller_v10_4_angle_contract.py`

**Interfaces:**
- Consumes: `surface_graph["surfaces"]`
- Produces: `measure_v10_4_continuity(surface_graph: dict) -> dict`
- Produces: `measure_v10_4_blade_hub_angles(surface_graph: dict) -> dict`

- [ ] **Step 1: Write continuity tests**

Create `tests/test_impeller_v10_4_continuity_contract.py`:

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


def test_v10_4_g2_claims_are_measured_or_downgraded():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    graph = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]
    summary = graph["v1_0_4_continuity_summary"]

    assert summary["status"] == "PASS"
    assert summary["measured_edge_count"] > 0
    assert summary["max_position_gap_mm"] <= 1.0e-6
    assert summary["max_tangent_angle_deg"] <= 2.0
    assert summary["max_normal_angle_deg"] <= 5.0
    assert summary["max_curvature_proxy_mismatch"] <= 0.25
    assert set(summary["allowed_statuses"]) == {
        "G2_MEASURED",
        "G1_MEASURED_G2_FAILED",
        "G0_ONLY_FAILED",
        "EXTRAORDINARY_VERTEX_EXCLUDED",
    }
```

Create `tests/test_impeller_v10_4_angle_contract.py`:

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


def test_v10_4_blade_hub_angles_are_inspection_friendly():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    graph = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]
    quality = graph["v1_0_4_angle_quality"]

    assert quality["status"] == "PASS"
    assert quality["min_blade_hub_angle_deg"] >= 60.0
    assert quality["max_blade_hub_angle_deg"] <= 120.0
    assert quality["sample_count"] > 0
```

- [ ] **Step 2: Run failing continuity tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_continuity_contract.py tests/test_impeller_v10_4_angle_contract.py -q
```

Expected: FAIL because summary fields are missing.

- [ ] **Step 3: Implement measurement module**

Create `src/part_rule_synthesis/impeller_v10_4_continuity.py`:

```python
from __future__ import annotations

import math
from typing import Any


ALLOWED_STATUSES = [
    "G2_MEASURED",
    "G1_MEASURED_G2_FAILED",
    "G0_ONLY_FAILED",
    "EXTRAORDINARY_VERTEX_EXCLUDED",
]


def measure_v10_4_continuity(surface_graph: dict[str, Any]) -> dict[str, Any]:
    surface_by_id = {surface["id"]: surface for surface in surface_graph.get("surfaces", [])}
    edges = _transition_edges(surface_graph)
    measurements = []
    for edge in edges:
        left = surface_by_id.get(edge["left_surface_id"])
        right = surface_by_id.get(edge["right_surface_id"])
        if left is None or right is None:
            measurements.append(_failed_edge(edge, "v1_0_4_shared_edge_surface_missing"))
            continue
        measurements.append(_measure_shared_edge(left, right, edge))

    failures = [item for item in measurements if item["status"] != "G2_MEASURED"]
    return {
        "status": "PASS" if measurements and not failures else "FAIL",
        "reason": None if measurements and not failures else "v1_0_4_g2_continuity_failed",
        "measured_edge_count": len(measurements),
        "max_position_gap_mm": max((item["position_gap_mm"] for item in measurements), default=0.0),
        "max_tangent_angle_deg": max((item["tangent_angle_deg"] for item in measurements), default=180.0),
        "max_normal_angle_deg": max((item["normal_angle_deg"] for item in measurements), default=180.0),
        "max_curvature_proxy_mismatch": max((item["curvature_proxy_mismatch"] for item in measurements), default=1.0),
        "edge_measurements": measurements,
        "allowed_statuses": ALLOWED_STATUSES[:],
    }


def measure_v10_4_blade_hub_angles(surface_graph: dict[str, Any]) -> dict[str, Any]:
    surface_by_id = {surface["id"]: surface for surface in surface_graph.get("surfaces", [])}
    angles = []
    for edge in _blade_hub_angle_edges(surface_graph):
        blade = surface_by_id.get(edge["blade_surface_id"])
        hub = surface_by_id.get(edge["hub_surface_id"])
        if blade is None or hub is None:
            continue
        angles.extend(_measure_surface_angle_samples(blade, hub, edge))
    min_angle = min(angles) if angles else 0.0
    max_angle = max(angles) if angles else 180.0
    in_range = bool(angles) and min_angle >= 60.0 and max_angle <= 120.0
    return {
        "status": "PASS" if in_range else "FAIL",
        "reason": None if in_range else "v1_0_4_blade_hub_angle_out_of_range",
        "min_blade_hub_angle_deg": min_angle,
        "max_blade_hub_angle_deg": max_angle,
        "sample_count": len(angles),
    }


def _measure_shared_edge(left: dict[str, Any], right: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    left_samples = _boundary_samples(left, edge["left_edge"])
    right_samples = _boundary_samples(right, edge["right_edge"])
    right_samples = _align_samples(left_samples, right_samples)
    left_frames = _boundary_frames(left, edge["left_edge"])
    right_frames = _align_frames(left_frames, _boundary_frames(right, edge["right_edge"]))
    position_gap = max((_distance(a, b) for a, b in zip(left_samples, right_samples)), default=999.0)
    tangent_angle = max((_axis_angle(a["edge_tangent"], b["edge_tangent"], bidirectional=True) for a, b in zip(left_frames, right_frames)), default=180.0)
    normal_angle = max((_axis_angle(a["normal"], b["normal"], bidirectional=False) for a, b in zip(left_frames, right_frames)), default=180.0)
    curvature_mismatch = max((_curvature_proxy_delta(a, b) for a, b in zip(left_frames, right_frames)), default=1.0)
    status = _continuity_status(position_gap, tangent_angle, normal_angle, curvature_mismatch)
    return {
        "edge_id": edge.get("id"),
        "left_surface_id": left["id"],
        "right_surface_id": right["id"],
        "position_gap_mm": round(position_gap, 6),
        "tangent_angle_deg": round(tangent_angle, 6),
        "normal_angle_deg": round(normal_angle, 6),
        "curvature_proxy_mismatch": round(curvature_mismatch, 6),
        "status": status,
    }


def _continuity_status(position_gap: float, tangent_angle: float, normal_angle: float, curvature_mismatch: float) -> str:
    if position_gap > 1.0e-6:
        return "G0_ONLY_FAILED"
    if tangent_angle > 2.0 or normal_angle > 5.0:
        return "G1_MEASURED_G2_FAILED"
    if curvature_mismatch > 0.25:
        return "G1_MEASURED_G2_FAILED"
    return "G2_MEASURED"


def _transition_edges(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    graph = surface_graph.get("topology_graph", {})
    return [
        edge
        for edge in graph.get("shared_edges", [])
        if edge.get("continuity_contract") == "G2"
        and edge.get("left_surface_id")
        and edge.get("right_surface_id")
    ]


def _blade_hub_angle_edges(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    graph = surface_graph.get("topology_graph", {})
    return [
        edge
        for edge in graph.get("shared_edges", [])
        if edge.get("angle_contract") == "blade_to_hub_60_120"
    ]


def _boundary_samples(surface: dict[str, Any], edge_name: str) -> list[list[float]]:
    grid = surface.get("uv_grid", [])
    if edge_name == "u_min":
        return [row[0] for row in grid]
    if edge_name == "u_max":
        return [row[-1] for row in grid]
    if edge_name == "v_min":
        return list(grid[0])
    if edge_name == "v_max":
        return list(grid[-1])
    raise ValueError(f"unknown boundary edge: {edge_name}")


def _boundary_frames(surface: dict[str, Any], edge_name: str) -> list[dict[str, list[float]]]:
    grid = surface.get("uv_grid", [])
    samples = _boundary_samples(surface, edge_name)
    frames = []
    for index, point in enumerate(samples):
        prev_point = samples[max(index - 1, 0)]
        next_point = samples[min(index + 1, len(samples) - 1)]
        edge_tangent = _unit(_sub(next_point, prev_point))
        inward_tangent = _inward_tangent(grid, edge_name, index)
        normal = _unit(_cross(edge_tangent, inward_tangent))
        second = _second_difference(samples, index)
        frames.append({
            "point": point,
            "edge_tangent": edge_tangent,
            "inward_tangent": inward_tangent,
            "normal": normal,
            "curvature_proxy": _length(second),
        })
    return frames


def _inward_tangent(grid: list[list[list[float]]], edge_name: str, index: int) -> list[float]:
    if edge_name == "u_min":
        return _unit(_sub(grid[index][1], grid[index][0]))
    if edge_name == "u_max":
        return _unit(_sub(grid[index][-2], grid[index][-1]))
    if edge_name == "v_min":
        return _unit(_sub(grid[1][index], grid[0][index]))
    if edge_name == "v_max":
        return _unit(_sub(grid[-2][index], grid[-1][index]))
    raise ValueError(f"unknown boundary edge: {edge_name}")


def _measure_surface_angle_samples(blade: dict[str, Any], hub: dict[str, Any], edge: dict[str, Any]) -> list[float]:
    blade_frames = _boundary_frames(blade, edge["blade_edge"])
    hub_frames = _align_frames(blade_frames, _boundary_frames(hub, edge["hub_edge"]))
    return [_axis_angle(a["normal"], b["normal"], bidirectional=False) for a, b in zip(blade_frames, hub_frames)]


def _align_samples(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    if not left or not right:
        return right
    forward = _distance(left[0], right[0]) + _distance(left[-1], right[-1])
    reversed_distance = _distance(left[0], right[-1]) + _distance(left[-1], right[0])
    return list(reversed(right)) if reversed_distance < forward else right


def _align_frames(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aligned_points = _align_samples([item["point"] for item in left], [item["point"] for item in right])
    return list(reversed(right)) if aligned_points and aligned_points[0] == right[-1]["point"] else right


def _failed_edge(edge: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "edge_id": edge.get("id"),
        "position_gap_mm": 999.0,
        "tangent_angle_deg": 180.0,
        "normal_angle_deg": 180.0,
        "curvature_proxy_mismatch": 1.0,
        "status": "G0_ONLY_FAILED",
        "reason": reason,
    }


def _curvature_proxy_delta(left: dict[str, Any], right: dict[str, Any]) -> float:
    denominator = max(left["curvature_proxy"], right["curvature_proxy"], 1.0e-9)
    return abs(left["curvature_proxy"] - right["curvature_proxy"]) / denominator


def _axis_angle(left: list[float], right: list[float], *, bidirectional: bool) -> float:
    dot = sum(a * b for a, b in zip(_unit(left), _unit(right)))
    if bidirectional:
        dot = abs(dot)
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def _second_difference(samples: list[list[float]], index: int) -> list[float]:
    if not samples:
        return [0.0, 0.0, 0.0]
    prev_point = samples[max(index - 1, 0)]
    point = samples[index]
    next_point = samples[min(index + 1, len(samples) - 1)]
    return [
        next_point[axis] - 2.0 * point[axis] + prev_point[axis]
        for axis in range(3)
    ]


def _distance(left: list[float], right: list[float]) -> float:
    return _length(_sub(left, right))


def _length(vector: list[float]) -> float:
    return sum(float(value) ** 2 for value in vector) ** 0.5


def _sub(left: list[float], right: list[float]) -> list[float]:
    return [float(left[0]) - float(right[0]), float(left[1]) - float(right[1]), float(left[2]) - float(right[2])]


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _unit(vector: list[float]) -> list[float]:
    length = _length(vector)
    if length <= 1.0e-9:
        return [0.0, 0.0, 0.0]
    return [float(value) / length for value in vector]
```

- [ ] **Step 4: Attach measurements to graph payload**

In `src/part_rule_synthesis/impeller_v10_surface_graph.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_continuity import (
    measure_v10_4_blade_hub_angles,
    measure_v10_4_continuity,
)
```

In `_v10_3_graph_payload`, before return:

```python
continuity_summary = {}
angle_quality = {}
if resolved_section_loop_defaults.get("geometry_patch_version") == "1.0.4":
    draft_graph = {"surfaces": surfaces, "topology_graph": topology_graph}
    continuity_summary = measure_v10_4_continuity(draft_graph)
    angle_quality = measure_v10_4_blade_hub_angles(draft_graph)
```

Add to returned payload:

```python
"v1_0_4_continuity_summary": copy.deepcopy(continuity_summary),
"v1_0_4_angle_quality": copy.deepcopy(angle_quality),
```

- [ ] **Step 5: Run continuity and angle tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_continuity_contract.py tests/test_impeller_v10_4_angle_contract.py -q
```

Expected: PASS.

---

### Task 7: V1.0.4 Surface Graph And Validation Gates

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_4_validation.py`
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Test: `tests/test_impeller_v10_4_surface_graph.py`
- Test: `tests/test_impeller_v10_4_validation.py`

**Interfaces:**
- Consumes: V1.0.4 surface graph
- Produces: `validate_v10_4_surface_graph(surface_graph: dict) -> list[dict]`

- [ ] **Step 1: Write surface graph tests**

Create `tests/test_impeller_v10_4_surface_graph.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def test_v10_4_open_surface_graph_passes_contracts():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    graph = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]
    report = build_geometry_validation_report(surface_graph=graph)

    assert graph["geometry_patch_version"] == "1.0.4"
    assert graph["surface_graph_status"] == "PASS"
    assert graph["v1_0_4_transition_failure_count"] == 0
    assert report["geometry_validation_status"] == "PASS"
```

Create `tests/test_impeller_v10_4_validation.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_4_validation import validate_v10_4_surface_graph


def test_v10_4_validation_rejects_missing_root_quality():
    failures = validate_v10_4_surface_graph(
        {
            "geometry_patch_version": "1.0.4",
            "surfaces": [],
            "v1_0_4_hub_quality": {"status": "PASS"},
            "v1_0_4_continuity_summary": {"status": "PASS"},
            "v1_0_4_angle_quality": {"status": "PASS"},
        }
    )

    assert any(failure["reason"] == "v1_0_4_root_quality_missing" for failure in failures)
```

- [ ] **Step 2: Run failing validation tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py -q
```

Expected: FAIL because validation module is missing.

- [ ] **Step 3: Implement validation module**

Create `src/part_rule_synthesis/impeller_v10_4_validation.py`:

```python
from __future__ import annotations

from typing import Any


def validate_v10_4_surface_graph(surface_graph: dict[str, Any]) -> list[dict[str, Any]]:
    if surface_graph.get("geometry_patch_version") != "1.0.4":
        return []
    failures: list[dict[str, Any]] = []
    root_surfaces = [
        surface
        for surface in surface_graph.get("surfaces", [])
        if surface.get("id", "").endswith("root_annular_surface")
    ]
    if not root_surfaces or any(surface.get("v1_0_4_root_quality", {}).get("status") != "PASS" for surface in root_surfaces):
        failures.append(_failure("v1_0_4_root_quality_missing"))
    tip_surfaces = [
        surface
        for surface in surface_graph.get("surfaces", [])
        if surface.get("role") == "open_tip_dome"
    ]
    if not tip_surfaces or any(surface.get("v1_0_4_tip_quality", {}).get("status") != "PASS" for surface in tip_surfaces):
        failures.append(_failure("v1_0_4_tip_quality_missing"))
    if surface_graph.get("v1_0_4_hub_quality", {}).get("status") != "PASS":
        failures.append(_failure("v1_0_4_hub_quality_missing"))
    if surface_graph.get("v1_0_4_continuity_summary", {}).get("status") != "PASS":
        failures.append(_failure("v1_0_4_g2_continuity_failed"))
    if surface_graph.get("v1_0_4_angle_quality", {}).get("status") != "PASS":
        failures.append(_failure("v1_0_4_blade_hub_angle_out_of_range"))
    return failures


def _failure(reason: str) -> dict[str, Any]:
    return {"stage": "v1_0_4_validation", "status": "FAIL", "reason": reason}
```

- [ ] **Step 4: Integrate into geometry validation**

In `src/part_rule_synthesis/impeller_geometry_validation.py`, import:

```python
from part_rule_synthesis.impeller_v10_4_validation import validate_v10_4_surface_graph
```

Inside `build_geometry_validation_report(...)`, after existing transition validation:

```python
for failure in validate_v10_4_surface_graph(surface_graph):
    blocking_failures.append(failure)
```

Ensure `geometry_validation_status` is `FAIL` when V1.0.4 failures exist.

- [ ] **Step 5: Run validation tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py -q
```

Expected: PASS.

---

### Task 8: Frontend Viewer Layers And V1.0.4 Routing

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/workspaceModel.js`
- Modify: `frontend/src/simulationViewModel.js`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/appFiles.test.js`
- Test: `frontend/src/workspaceModel.test.js`
- Test: `frontend/src/simulationViewModel.test.js`

**Interfaces:**
- Consumes: V1.0.4 manifest fields
- Produces viewer layers `shade_surfaces`, `nurbs_uv_wire`, `mesh_triangle_wire`, `control_curves`, `control_points`, `shared_edges`, `diagnostic_failures`

- [ ] **Step 1: Write frontend tests**

Append to `frontend/src/appModel.test.js`:

```javascript
test("first UI preset advertises active v1.0.4 geometry contract", () => {
  assert.equal(presets[0].presetId, "radial_open_reference_v1_0");
  assert.equal(presets[0].geometryPatchVersion, "1.0.4");
  assert.match(presets[0].name, /v1\.0\.4/);
  assert.equal(presets[0].metadata.transitionGeometryStatus, "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph");
});
```

Append to `frontend/src/appFiles.test.js`:

```javascript
test("viewer separates V1.0.4 shade uv mesh controls and diagnostic layers", () => {
  const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
  const workspaceSource = readFileSync(resolve(root, "src/workspaceModel.js"), "utf-8");

  for (const layer of ["shade_surfaces", "nurbs_uv_wire", "mesh_triangle_wire", "control_curves", "control_points", "shared_edges", "diagnostic_failures"]) {
    assert.match(viewerSource + workspaceSource, new RegExp(layer));
  }
});
```

- [ ] **Step 2: Run failing frontend tests**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js appFiles.test.js workspaceModel.test.js simulationViewModel.test.js
```

Expected: FAIL because V1.0.4 metadata and layers are missing.

- [ ] **Step 3: Update frontend preset metadata**

In `frontend/src/appModel.js`, change first preset:

```javascript
geometryPatchVersion: "1.0.4",
name: "Topology-first open throughflow v1.0.4",
summary: "Open impeller: V1.0.4 measured section-loop, root, tip, hub solid, and G2 contract graph.",
tags: ["open", "topology-first", "v1.0.4", "measured-g2", "surface graph"],
metadata: {
  geometryPatchVersion: "1.0.4",
  generationStatus: "PASS",
  transitionGeometryStatus: "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph",
},
```

- [ ] **Step 4: Add layer schema**

In `frontend/src/workspaceModel.js`, ensure layer schema includes:

```javascript
{ id: "shade_surfaces", label: "Shade surfaces", defaultVisible: true },
{ id: "nurbs_uv_wire", label: "NURBS UV wire", defaultVisible: true },
{ id: "mesh_triangle_wire", label: "Mesh triangle wire", defaultVisible: false },
{ id: "control_curves", label: "Control curves", defaultVisible: true },
{ id: "control_points", label: "Control points", defaultVisible: true },
{ id: "shared_edges", label: "Shared edges", defaultVisible: false },
{ id: "diagnostic_failures", label: "Diagnostic failures", defaultVisible: true },
```

Map `child.userData.layer` from `ModelViewer.js` to these ids.

- [ ] **Step 5: Update viewer layer assignment**

In `frontend/src/components/ModelViewer.js`, assign:

```javascript
mesh.userData.layer = "shade_surfaces";
surfaceUvWire.userData.layer = "nurbs_uv_wire";
meshTriangleWire.userData.layer = "mesh_triangle_wire";
controlCurve.userData.layer = "control_curves";
controlPoint.userData.layer = "control_points";
sharedEdgeLine.userData.layer = "shared_edges";
diagnosticLine.userData.layer = "diagnostic_failures";
```

Keep existing layer mapping for legacy surfaces by falling back to `layerForSurface(surface, manifest)` only when V1.0.4 fields are absent.

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js appFiles.test.js workspaceModel.test.js simulationViewModel.test.js
```

Expected: PASS.

---

### Task 9: Service Smoke, Evidence, And Regression Gate

**Files:**
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/semantic-change-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/insight-log.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md`

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified V1.0.4 service and evidence trail

- [ ] **Step 1: Run backend V1.0.4 tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_4_resources.py tests/test_impeller_v10_4_section_loop_contract.py tests/test_impeller_v10_4_root_surface_contract.py tests/test_impeller_v10_4_tip_surface_contract.py -q
python -m pytest tests/test_impeller_v10_4_hub_solid_contract.py tests/test_impeller_v10_4_continuity_contract.py tests/test_impeller_v10_4_angle_contract.py tests/test_impeller_v10_4_surface_graph.py tests/test_impeller_v10_4_validation.py -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run existing V1.0.3 regression tests**

Run:

```powershell
python -m pytest tests/test_impeller_v10_3_preset_defaults.py tests/test_impeller_v10_3_surface_graph.py tests/test_impeller_v10_3_validation.py -q
python -m pytest tests/test_impeller_v10_3_root_blend.py tests/test_impeller_v10_3_tip_dome.py tests/test_impeller_v10_legacy_nurbs_reuse.py -q
```

Expected: PASS, except tests that intentionally change open preset expectation from V1.0.3 to V1.0.4 must be updated to assert V1.0.4.

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all tests PASS.

- [ ] **Step 4: Restart backend 8061 and frontend 5203**

Run:

```powershell
$backend = Get-NetTCPConnection -LocalPort 8061 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($backend) {
  Stop-Process -Id $backend.OwningProcess -Force
  Start-Sleep -Seconds 1
}
$env:PYTHONPATH = (Resolve-Path 'src').Path
Start-Process -FilePath python -ArgumentList @('-m','uvicorn','part_rule_synthesis.api:app','--host','127.0.0.1','--port','8061') -WorkingDirectory (Resolve-Path '.').Path -WindowStyle Hidden

$frontend = Resolve-Path -LiteralPath 'frontend'
$frontendConn = Get-NetTCPConnection -LocalPort 5203 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($frontendConn) {
  Stop-Process -Id $frontendConn.OwningProcess -Force
  Start-Sleep -Seconds 1
}
Start-Process -FilePath python -ArgumentList @('-m','http.server','5203','-b','127.0.0.1') -WorkingDirectory $frontend.Path -WindowStyle Hidden
```

- [ ] **Step 5: Run HTTP smoke**

Run:

```powershell
$base = 'http://127.0.0.1:8061'
$engine = Invoke-RestMethod -Method Post -Uri "$base/api/rule-engines/synthesize" -ContentType 'application/json' -Body (@{ part_family_id = 'impeller'; preset_id = 'radial_open_reference_v1_0' } | ConvertTo-Json)
$run = Invoke-RestMethod -Method Post -Uri "$base/api/rule-engines/$($engine.engine_id)/instantiate" -ContentType 'application/json' -Body (@{ parameters = @{}; geometry_stage = 'full' } | ConvertTo-Json -Depth 5)
$manifest = $run.manifest
$graph = $manifest.geometry.surface_graph
@{
  run_id = $manifest.run_id
  geometry_patch_version = $manifest.geometry.geometry_patch_version
  surface_graph_status = $graph.surface_graph_status
  validation_status = $manifest.geometry_validation_report.geometry_validation_status
  transition_geometry_status = $graph.transition_geometry_status
  root_status = $graph.surfaces | Where-Object { $_.id -eq 'blade_0_root_annular_surface' } | Select-Object -ExpandProperty v1_0_4_root_quality
  hub_status = $graph.v1_0_4_hub_quality
} | ConvertTo-Json -Depth 8
```

Expected:

```json
{
  "geometry_patch_version": "1.0.4",
  "surface_graph_status": "PASS",
  "validation_status": "PASS",
  "transition_geometry_status": "topology_first_measured_g2_section_loop_root_tip_hub_solid_graph"
}
```

- [ ] **Step 6: Update evidence logs**

Append to `semantic-change-log.md`:

```markdown
## 2026-07-07 V1.0.4 Geometry Contract Overhaul

V1.0.4 changes the open preset from a V1.0.3 section-loop prototype to a measured geometry-contract graph. Root, tip, hub, section-loop, continuity, blade-hub angle, and viewer layer semantics now have explicit PASS/FAIL contracts and named failure reasons.
```

Append to `insight-log.md`:

```markdown
## Insight 33: Root And Tip Geometry Need Bounded Domains, Not Larger Debug Surfaces

The screenshots showed that visually large magenta/yellow patches can make defects easier to notice but can also exceed the real blade domain. V1.0.4 therefore uses bounded root and tip contracts: root width/lift are measured against half blade thickness, and tip area is measured against the actual blade tip loop.
```

Append command outputs to `test-transcript-summary.md` with exact PASS/FAIL lines from Steps 1 through 5.

- [ ] **Step 7: Final verification**

Run:

```powershell
git status --short
```

Confirm no temporary smoke directories remain except intentionally ignored service output directories. Report any known failing historical tests separately.

---

## Self-Review

Spec coverage:

- Root orientation, material side, width, and lift: Task 3.
- Tip domain and area bound: Task 4.
- Concave hub and mounting bore: Task 5.
- Section loop backend and frontend truth: Task 2.
- G2 measurement and downgrade semantics: Task 6 and Task 7.
- Blade-hub angle range: Task 6.
- Shade/wire/control layer separation: Task 8.
- Preset and runtime V1.0.4 routing: Task 1 and Task 8.
- Evidence and smoke: Task 9.

Completeness scan:

- No deferred-work markers or unspecified test-writing steps remain.
- Every task includes exact file paths, test commands, and expected outcomes.

Type consistency:

- `v1_0_4_*_quality` keys are consistently used in tests, graph payloads, and validation.
- V1.0.4 routing is consistently keyed from `geometry_patch_version == "1.0.4"`.
- Frontend layer ids are consistent across `ModelViewer.js`, `workspaceModel.js`, and tests.
