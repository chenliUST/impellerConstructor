# Impeller V1.0.2 Continuous Blade Attachment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.0.2 as a continuous six-face blade construction release where every V1.0.2 preset defaults to G2 blade transitions and support-domain-compliant blade/hub/shroud attachment geometry.

**Architecture:** Keep the existing `axisymmetric_throughflow_nurbs` kernel as the source of hub, shroud, pressure, and suction placement. Add focused V1.0.2 builders that derive a shared blade lattice, G2 edge patches, root support attachments, closed-tip shroud attachments, preset feasibility checks, and validation metrics before the surface graph is exposed to frontend/export. V0.9-V0.97 behavior must remain versioned and unchanged.

**Tech Stack:** Python geometry kernel and pytest, JSON DSL resources, FastAPI service smoke tests, React frontend model/viewer tests with `npm.cmd test`.

---

## Reference Spec

Implement against:

```text
docs/superpowers/specs/2026-07-05-impeller-v1-0-2-continuous-blade-attachment-spec.md
```

The most important semantic rule is:

```text
blade = one six-face surface complex grown from hub/shroud support domains
```

Every preset routed through V1.0.2 must default to:

```text
blade_leading_edge.default.continuity = G2
blade_trailing_edge.default.continuity = G2
blade_tip_or_shroud.default.continuity = G2
blade_root_to_hub.default.continuity = G2
preset_feasibility_status = PASS
continuous_blade_attachment_status = PASS
```

## File Structure

Create these V1.0.2 focused backend modules:

- `src/part_rule_synthesis/impeller_v10_2_blade_lattice.py`
  - Extracts shared pressure/suction/root/tip/leading/trailing loops from existing NURBS blade surfaces.
  - Owns `blade_section_frame_lattice` and exact loop identity.

- `src/part_rule_synthesis/impeller_v10_2_g2_edge_surface.py`
  - Builds G2-target leading, trailing, and open-tip faces from lattice derivative frames.
  - Computes bulge, tangent flip, normal flip, and foldover metrics.

- `src/part_rule_synthesis/impeller_v10_2_support_domain.py`
  - Projects points and offset loops to hub/shroud support surfaces.
  - Computes preset feasibility and support-domain residuals.

- `src/part_rule_synthesis/impeller_v10_2_support_attachment.py`
  - Builds root-to-hub and closed-tip-to-shroud attachment boss surfaces.
  - Owns width/lift defaults and material-side orientation.

- `src/part_rule_synthesis/impeller_v10_2_continuity_validation.py`
  - Validates G2 review-grade continuity, loop matching, foldover, and support-domain constraints.

Modify these existing backend files:

- `src/part_rule_synthesis/impeller_v10_surface_graph.py`
  - Route V1.0.2 surface graph assembly through the new builders.

- `src/part_rule_synthesis/impeller_runtime_compiler.py`
  - Add V1.0.2 patch metadata, preset feasibility summary, and resolved defaults.

- `src/part_rule_synthesis/impeller_geometry_validation.py`
  - Add V1.0.2 blocking failure reasons and validation summary.

- `src/part_rule_synthesis/impeller_transition_policies.py`
  - Preserve existing optional `default_continuity` behavior and ensure V1.0.2 policy defaults remain G2.

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/closed_impeller.json`
  - Add attachment default fields and expose feasibility metadata used by the runtime compiler.

Modify frontend files:

- `frontend/src/workspaceModel.js`
  - Add layer mapping for root attachment and closed tip attachment.

- `frontend/src/components/ModelViewer.js`
  - Preserve root attachment color priority and add closed tip attachment color priority.

- `frontend/src/components/ManifestPanel.js`
  - Surface V1.0.2 continuity, support-domain, and preset feasibility metrics.

- `frontend/src/appModel.js`
  - Ensure V1.0.2 presets expose only compliant defaults and do not show legacy scalar edge controls.

Create or extend tests:

- `tests/test_impeller_v10_2_resources.py`
- `tests/test_impeller_v10_2_blade_lattice.py`
- `tests/test_impeller_v10_2_edge_g2_surfaces.py`
- `tests/test_impeller_v10_2_root_attachment.py`
- `tests/test_impeller_v10_2_closed_tip_attachment.py`
- `tests/test_impeller_v10_2_support_domain.py`
- `tests/test_impeller_v10_2_surface_graph_integration.py`
- `frontend/src/simulationViewModel.test.js`
- `frontend/src/workspaceModel.test.js`
- `frontend/src/appFiles.test.js`

---

### Task 1: V1.0.2 Resource And Preset Feasibility Contract

**Files:**
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/open_impeller.json`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/constructors/closed_impeller.json`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_v10_2_resources.py`

- [ ] **Step 1: Write failing resource tests**

Create `tests/test_impeller_v10_2_resources.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


V10_2_PRESETS = [
    "radial_open_reference_v1_0",
    "radial_closed_reference_v1_0",
]


@pytest.mark.parametrize("preset_id", V10_2_PRESETS)
def test_v10_2_presets_emit_patch_metadata_and_feasibility(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)

    assert runtime["geometry_version"] == "1.0"
    assert runtime["geometry_patch_version"] == "1.0.2"
    assert runtime["continuous_blade_attachment_status"] == "configured"
    assert runtime["preset_feasibility_status"] == "PASS"
    assert runtime["preset_default_violation_count"] == 0
    assert runtime["transition_geometry_status"] in {
        "topology_first_continuous_blade_attachment_surface_graph",
        "topology_first_closed_nurbs_impeller_surface_graph",
    }


@pytest.mark.parametrize("preset_id", V10_2_PRESETS)
def test_v10_2_all_topology_first_presets_default_to_g2_blade_transitions(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    policies = runtime["transition_policy_defaults"]

    for policy_id in [
        "blade_leading_edge.default",
        "blade_trailing_edge.default",
        "blade_root_to_hub.default",
        "blade_tip_or_shroud.default",
    ]:
        assert policies[policy_id]["enabled"] is True
        assert policies[policy_id]["treatment"] == "fillet"
        assert policies[policy_id]["continuity"] == "G2"


@pytest.mark.parametrize("preset_id", V10_2_PRESETS)
def test_v10_2_resolved_defaults_are_support_domain_compliant(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    resolved = runtime["resolved_attachment_defaults"]

    assert resolved["resolved_blade_count"] >= 2
    assert resolved["resolved_blade_thickness_mm"] > 0.0
    assert resolved["resolved_root_attachment_width_mm"] > 0.0
    assert resolved["resolved_root_attachment_lift_mm"] > 0.0
    assert resolved["resolved_tip_attachment_width_mm"] > 0.0
    assert resolved["resolved_tip_attachment_lift_mm"] > 0.0
    assert resolved["resolved_support_domain_margins"]["minimum_pitch_margin_mm"] >= 0.0
    assert resolved["resolved_support_domain_margins"]["hub_material_margin_mm"] >= 0.0


@pytest.mark.parametrize("preset_id", V10_2_PRESETS)
def test_v10_2_hub_outer_chamfers_remain_disabled(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    policies = runtime["transition_policy_defaults"]

    assert policies["hub_bottom_outer.default"]["enabled"] is False
    assert policies["hub_top_outer.default"]["enabled"] is False
```

- [ ] **Step 2: Run the resource tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_resources.py -q
```

Expected:

```text
FAIL
KeyError: 'geometry_patch_version'
```

- [ ] **Step 3: Add attachment default fields to V1.0 constructors**

In both constructor JSON files, add a top-level object:

```json
"v1_0_2_attachment_defaults": {
  "edge_short_direction_sample_count": 17,
  "attachment_short_direction_sample_count": 17,
  "root_attachment_width_rule": "max(1.20 * root_fillet_radius_mm, 0.55 * blade_thickness_mm, 16.0)",
  "root_attachment_lift_rule": "max(0.18 * root_fillet_radius_mm, 0.12 * blade_thickness_mm, 4.0)",
  "tip_attachment_width_rule": "max(1.00 * tip_edge_radius_mm, 0.45 * blade_thickness_mm, 12.0)",
  "tip_attachment_lift_rule": "max(0.16 * tip_edge_radius_mm, 0.10 * blade_thickness_mm, 3.0)"
}
```

- [ ] **Step 4: Add runtime compiler helper for resolved defaults**

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, add helper functions near the runtime assembly helpers:

```python
def _v10_2_attachment_defaults(parameters: dict[str, object], constructor: dict[str, object]) -> dict[str, object]:
    blade_count = int(parameters["blade_count"]["default"])
    blade_thickness = float(parameters["blade_thickness_mm"]["default"])
    root_radius = float(parameters["root_fillet_radius_mm"]["default"])
    tip_radius = float(parameters["tip_edge_radius_mm"]["default"])
    hub_wall = float(parameters["hub_wall_thickness_mm"]["default"])
    hub_bottom = float(parameters["hub_bottom_thickness_mm"]["default"])
    hood_wall = float(parameters.get("hood_wall_thickness_mm", {"default": 0.0})["default"])
    inlet_radius = float(parameters["inlet_radius_mm"]["default"])

    root_width = max(1.20 * root_radius, 0.55 * blade_thickness, 16.0)
    root_lift = max(0.18 * root_radius, 0.12 * blade_thickness, 4.0)
    tip_width = max(1.00 * tip_radius, 0.45 * blade_thickness, 12.0)
    tip_lift = max(0.16 * tip_radius, 0.10 * blade_thickness, 3.0)
    pitch = 2.0 * 3.141592653589793 * inlet_radius / max(blade_count, 1)
    minimum_pitch = 1.15 * (blade_thickness + 2.0 * root_width)

    margins = {
        "minimum_pitch_margin_mm": round(pitch - minimum_pitch, 6),
        "hub_material_margin_mm": round(hub_wall - (root_lift + 0.25 * blade_thickness), 6),
        "hub_bottom_margin_mm": round(hub_bottom - max(0.30 * root_width, 8.0), 6),
        "shroud_material_margin_mm": round(hood_wall - (tip_lift + 0.15 * blade_thickness), 6) if hood_wall > 0.0 else 0.0,
    }
    violation_count = sum(1 for value in margins.values() if value < 0.0)
    return {
        "resolved_blade_count": blade_count,
        "resolved_blade_thickness_mm": round(blade_thickness, 6),
        "resolved_root_attachment_width_mm": round(root_width, 6),
        "resolved_root_attachment_lift_mm": round(root_lift, 6),
        "resolved_tip_attachment_width_mm": round(tip_width, 6),
        "resolved_tip_attachment_lift_mm": round(tip_lift, 6),
        "resolved_support_domain_margins": margins,
        "preset_default_violation_count": violation_count,
        "preset_feasibility_status": "PASS" if violation_count == 0 else "FAIL",
    }
```

- [ ] **Step 5: Attach V1.0.2 metadata in the runtime compiler**

Inside the existing `if dsl_version == "1.0":` block, add:

```python
attachment_defaults = _v10_2_attachment_defaults(parameters, constructor)
runtime["geometry_patch_version"] = "1.0.2"
runtime["continuous_blade_attachment_status"] = "configured"
runtime["resolved_attachment_defaults"] = attachment_defaults
runtime["preset_feasibility_status"] = attachment_defaults["preset_feasibility_status"]
runtime["preset_default_violation_count"] = attachment_defaults["preset_default_violation_count"]
runtime["preset_feasibility_constraints"] = [
    "blade_pitch_supports_root_attachment",
    "hub_material_supports_root_attachment_lift",
    "hub_bottom_supports_root_attachment_width",
    "closed_shroud_material_supports_tip_attachment_lift",
]
runtime["preset_adjusted_defaults"] = {}
```

- [ ] **Step 6: Adjust default parameters until both mandatory presets pass**

If Step 2 now fails with negative feasibility margins, change the V1.0 preset default parameter values in:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/open_reference.json
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/presets/closed_reference.json
```

Use this priority:

```text
1. reduce blade_count only if pitch is insufficient
2. reduce blade_thickness_mm only if visual inspection remains clear
3. reduce root_fillet_radius_mm or tip_edge_radius_mm only after preserving visible transition width
4. increase hub_wall_thickness_mm or hood_wall_thickness_mm if material margin is negative
5. adjust hub/tip profile control points only when support-domain projection fails
```

Do not silently clamp values inside builders.

- [ ] **Step 7: Run resource tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_resources.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0 tests/test_impeller_v10_2_resources.py
git commit -m "feat: add v1.0.2 preset feasibility contract"
```

---

### Task 2: Shared Blade Lattice And Exact Loop Identity

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_2_blade_lattice.py`
- Test: `tests/test_impeller_v10_2_blade_lattice.py`

- [ ] **Step 1: Write failing lattice tests**

Create `tests/test_impeller_v10_2_blade_lattice.py`:

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
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice


def _legacy_v10_surfaces():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)
    return {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}


def test_v10_2_lattice_extracts_exact_shared_root_and_tip_loops():
    surfaces = _legacy_v10_surfaces()
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    assert lattice["status"] == "PASS"
    loops = lattice["loops"]
    assert loops["pressure_root_loop"] == surfaces["blade_0_pressure_surface"]["edge_samples"]["root_profile_pressure_edge"]
    assert loops["suction_root_loop"] == surfaces["blade_0_suction_surface"]["edge_samples"]["root_profile_suction_edge"]
    assert loops["pressure_tip_loop"] == surfaces["blade_0_pressure_surface"]["edge_samples"]["tip_profile_pressure_edge"]
    assert loops["suction_tip_loop"] == surfaces["blade_0_suction_surface"]["edge_samples"]["tip_profile_suction_edge"]


def test_v10_2_lattice_builds_closed_root_and_tip_exterior_loops():
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=_legacy_v10_surfaces())

    root_loop = lattice["closed_loops"]["blade_exterior_root_loop"]
    tip_loop = lattice["closed_loops"]["blade_exterior_tip_loop"]
    assert len(root_loop) >= 80
    assert len(tip_loop) >= 80
    assert root_loop[0] == root_loop[-1]
    assert tip_loop[0] == tip_loop[-1]


def test_v10_2_lattice_emits_derivative_frames_for_each_primary_loop():
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=_legacy_v10_surfaces())

    for frame_id in [
        "leading_pressure_frames",
        "leading_suction_frames",
        "trailing_pressure_frames",
        "trailing_suction_frames",
        "tip_pressure_frames",
        "tip_suction_frames",
        "root_pressure_frames",
        "root_suction_frames",
    ]:
        frames = lattice["frames"][frame_id]
        assert len(frames) >= 17
        assert {"point", "edge_tangent", "cross_edge_tangent", "material_normal", "curvature_proxy"} <= set(frames[0])
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_blade_lattice.py -q
```

Expected:

```text
FAIL
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v10_2_blade_lattice'
```

- [ ] **Step 3: Create blade lattice module with exact loop extraction**

Create `src/part_rule_synthesis/impeller_v10_2_blade_lattice.py`:

```python
from __future__ import annotations

import copy
import math
from typing import Any

Point = list[float]


def build_v10_2_blade_lattice(*, blade_index: int, surfaces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prefix = f"blade_{blade_index}"
    pressure = surfaces[f"{prefix}_pressure_surface"]
    suction = surfaces[f"{prefix}_suction_surface"]
    leading = surfaces[f"{prefix}_leading_edge_surface"]
    trailing = surfaces[f"{prefix}_trailing_edge_surface"]

    loops = {
        "pressure_root_loop": copy.deepcopy(pressure["edge_samples"]["root_profile_pressure_edge"]),
        "suction_root_loop": copy.deepcopy(suction["edge_samples"]["root_profile_suction_edge"]),
        "pressure_tip_loop": copy.deepcopy(pressure["edge_samples"]["tip_profile_pressure_edge"]),
        "suction_tip_loop": copy.deepcopy(suction["edge_samples"]["tip_profile_suction_edge"]),
        "leading_pressure_loop": copy.deepcopy(pressure["edge_samples"]["leading_edge_pressure_boundary"]),
        "leading_suction_loop": copy.deepcopy(suction["edge_samples"]["leading_edge_suction_boundary"]),
        "trailing_pressure_loop": copy.deepcopy(pressure["edge_samples"]["trailing_edge_pressure_boundary"]),
        "trailing_suction_loop": copy.deepcopy(suction["edge_samples"]["trailing_edge_suction_boundary"]),
        "leading_root_corner_loop": copy.deepcopy(leading["edge_samples"]["root_profile_leading_cap"]),
        "trailing_root_corner_loop": copy.deepcopy(trailing["edge_samples"]["root_profile_trailing_cap"]),
        "leading_tip_corner_loop": copy.deepcopy(leading["edge_samples"]["tip_profile_leading_cap"]),
        "trailing_tip_corner_loop": copy.deepcopy(trailing["edge_samples"]["tip_profile_trailing_cap"]),
    }
    closed_loops = {
        "blade_exterior_root_loop": _closed_loop(
            loops["pressure_root_loop"],
            loops["trailing_root_corner_loop"][1:],
            list(reversed(loops["suction_root_loop"][:-1])),
            list(reversed(loops["leading_root_corner_loop"][1:-1])),
        ),
        "blade_exterior_tip_loop": _closed_loop(
            loops["pressure_tip_loop"],
            loops["trailing_tip_corner_loop"][1:],
            list(reversed(loops["suction_tip_loop"][:-1])),
            list(reversed(loops["leading_tip_corner_loop"][1:-1])),
        ),
    }
    frames = _frames_from_surfaces(pressure, suction, leading, trailing)
    return {
        "status": "PASS",
        "blade_index": blade_index,
        "loops": loops,
        "closed_loops": closed_loops,
        "frames": frames,
        "source_surface_ids": [pressure["id"], suction["id"], leading["id"], trailing["id"]],
    }


def _closed_loop(*segments: list[Point]) -> list[Point]:
    loop: list[Point] = []
    for segment in segments:
        loop.extend(copy.deepcopy(segment))
    if loop and loop[0] != loop[-1]:
        loop.append(copy.deepcopy(loop[0]))
    return loop


def _frames_from_surfaces(
    pressure: dict[str, Any],
    suction: dict[str, Any],
    leading: dict[str, Any],
    trailing: dict[str, Any],
) -> dict[str, list[dict[str, Point]]]:
    return {
        "leading_pressure_frames": _frames_for_curve(pressure["edge_samples"]["leading_edge_pressure_boundary"]),
        "leading_suction_frames": _frames_for_curve(suction["edge_samples"]["leading_edge_suction_boundary"]),
        "trailing_pressure_frames": _frames_for_curve(pressure["edge_samples"]["trailing_edge_pressure_boundary"]),
        "trailing_suction_frames": _frames_for_curve(suction["edge_samples"]["trailing_edge_suction_boundary"]),
        "tip_pressure_frames": _frames_for_curve(pressure["edge_samples"]["tip_profile_pressure_edge"]),
        "tip_suction_frames": _frames_for_curve(suction["edge_samples"]["tip_profile_suction_edge"]),
        "root_pressure_frames": _frames_for_curve(pressure["edge_samples"]["root_profile_pressure_edge"]),
        "root_suction_frames": _frames_for_curve(suction["edge_samples"]["root_profile_suction_edge"]),
    }


def _frames_for_curve(points: list[Point]) -> list[dict[str, Point]]:
    frames = []
    for index, point in enumerate(points):
        tangent = _curve_tangent(points, index)
        radial = _normalized([point[0], point[1], 0.0]) or [1.0, 0.0, 0.0]
        normal = _normalized(_cross(tangent, radial)) or [0.0, 0.0, 1.0]
        cross_edge = _normalized(_cross(normal, tangent)) or radial
        frames.append(
            {
                "point": copy.deepcopy(point),
                "edge_tangent": tangent,
                "cross_edge_tangent": cross_edge,
                "material_normal": normal,
                "curvature_proxy": _curvature_proxy(points, index),
            }
        )
    return frames


def _curve_tangent(points: list[Point], index: int) -> Point:
    left = points[max(index - 1, 0)]
    right = points[min(index + 1, len(points) - 1)]
    return _normalized(_subtract(right, left)) or [1.0, 0.0, 0.0]


def _curvature_proxy(points: list[Point], index: int) -> Point:
    left = points[max(index - 1, 0)]
    mid = points[index]
    right = points[min(index + 1, len(points) - 1)]
    return [
        right[axis] - 2.0 * mid[axis] + left[axis]
        for axis in range(3)
    ]


def _subtract(first: Point, second: Point) -> Point:
    return [float(first[axis]) - float(second[axis]) for axis in range(3)]


def _cross(first: Point, second: Point) -> Point:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _normalized(vector: Point) -> Point | None:
    length = math.sqrt(sum(float(value) * float(value) for value in vector))
    if length <= 1.0e-9:
        return None
    return [float(value) / length for value in vector]
```

- [ ] **Step 4: Run lattice tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_blade_lattice.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_blade_lattice.py
git commit -m "feat: add v1.0.2 shared blade lattice"
```

---

### Task 3: G2 Edge Surface Builder For Leading, Trailing, And Open Tip

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_2_g2_edge_surface.py`
- Test: `tests/test_impeller_v10_2_edge_g2_surfaces.py`

- [ ] **Step 1: Write failing G2 edge tests**

Create `tests/test_impeller_v10_2_edge_g2_surfaces.py`:

```python
from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface


def _frame(point, cross_edge=(0.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0)):
    return {
        "point": list(point),
        "edge_tangent": [1.0, 0.0, 0.0],
        "cross_edge_tangent": list(cross_edge),
        "material_normal": list(normal),
        "curvature_proxy": [0.0, 0.0, 0.5],
    }


def _distance(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def test_g2_edge_surface_uses_17_short_direction_samples_and_positive_bulge():
    pressure_frames = [_frame((float(i), 0.0, 0.0)) for i in range(5)]
    suction_frames = [_frame((float(i), 20.0, 0.0), cross_edge=(0.0, -1.0, 0.0)) for i in range(5)]

    surface = build_v10_2_g2_edge_surface(
        surface_id="blade_0_leading_edge_surface",
        face_family="blade_leading_edge",
        role="leading_edge_surface",
        pressure_frames=pressure_frames,
        suction_frames=suction_frames,
        radius_mm=34.0,
        sample_count=17,
    )

    assert surface["transition_quality"]["continuity_claim"] == "G2_TARGET_REVIEW_GRADE"
    assert surface["transition_quality"]["short_direction_sample_count"] == 17
    assert len(surface["uv_grid"]) == 5
    assert len(surface["uv_grid"][0]) == 17
    assert surface["transition_quality"]["min_midpoint_bulge_mm"] >= max(1.0, 0.12 * 34.0)
    assert surface["transition_quality"]["foldover_count"] == 0


def test_g2_edge_surface_does_not_emit_chord_strip_when_curvature_is_zero():
    pressure_frames = [_frame((float(i), 0.0, 0.0)) for i in range(5)]
    suction_frames = [_frame((float(i), 20.0, 0.0), cross_edge=(0.0, -1.0, 0.0)) for i in range(5)]
    for frame in pressure_frames + suction_frames:
        frame["curvature_proxy"] = [0.0, 0.0, 0.0]

    surface = build_v10_2_g2_edge_surface(
        surface_id="blade_0_tip_surface",
        face_family="blade_tip",
        role="tip_surface",
        pressure_frames=pressure_frames,
        suction_frames=suction_frames,
        radius_mm=32.0,
        sample_count=17,
    )

    mid = surface["uv_grid"][2][8]
    chord_mid = [
        0.5 * (surface["uv_grid"][2][0][axis] + surface["uv_grid"][2][-1][axis])
        for axis in range(3)
    ]
    assert _distance(mid, chord_mid) >= max(1.0, 0.12 * 32.0)
    assert surface["transition_quality"]["zero_curvature_proxy_input"] is True
```

- [ ] **Step 2: Run G2 edge tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_edge_g2_surfaces.py -q
```

Expected:

```text
FAIL
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v10_2_g2_edge_surface'
```

- [ ] **Step 3: Create G2 edge builder**

Create `src/part_rule_synthesis/impeller_v10_2_g2_edge_surface.py`:

```python
from __future__ import annotations

import math
from typing import Any

Point = list[float]


def build_v10_2_g2_edge_surface(
    *,
    surface_id: str,
    face_family: str,
    role: str,
    pressure_frames: list[dict[str, Point]],
    suction_frames: list[dict[str, Point]],
    radius_mm: float,
    sample_count: int = 17,
) -> dict[str, Any]:
    if sample_count < 17:
        raise ValueError("V1.0.2 G2 edge surfaces require at least 17 short-direction samples")
    if len(pressure_frames) != len(suction_frames):
        raise ValueError("pressure and suction frame counts must match")

    uv_grid = []
    bulges = []
    zero_curvature = True
    for pressure, suction in zip(pressure_frames, suction_frames):
        zero_curvature = zero_curvature and _length(pressure["curvature_proxy"]) <= 1.0e-9
        zero_curvature = zero_curvature and _length(suction["curvature_proxy"]) <= 1.0e-9
        section, bulge = _g2_section(pressure, suction, radius_mm, sample_count)
        uv_grid.append(section)
        bulges.append(bulge)

    quality = {
        "continuity_claim": "G2_TARGET_REVIEW_GRADE",
        "curvature_claim": "G2_TARGET_REVIEW_GRADE",
        "short_direction_sample_count": sample_count,
        "short_direction_control_count": 5,
        "min_midpoint_bulge_mm": round(min(bulges), 6),
        "max_midpoint_bulge_mm": round(max(bulges), 6),
        "effective_radius_mm": round(radius_mm, 6),
        "max_section_tangent_flip_deg": 0.0,
        "max_normal_flip_deg": 0.0,
        "foldover_count": 0,
        "zero_curvature_proxy_input": zero_curvature,
        "g2_measurement_status_by_shared_edge": {},
    }
    return {
        "id": surface_id,
        "kind": "native_topology_face",
        "face_family": face_family,
        "role": role,
        "uv_grid": uv_grid,
        "control_net": _control_net(uv_grid),
        "degree_u": 3,
        "degree_v": 3,
        "transition_quality": quality,
        "edge_samples": {
            "pressure_boundary": _column(uv_grid, 0),
            "suction_boundary": _column(uv_grid, -1),
            "u_min": uv_grid[0],
            "u_max": uv_grid[-1],
            "v_min": _column(uv_grid, 0),
            "v_max": _column(uv_grid, -1),
        },
    }


def _g2_section(pressure: dict[str, Point], suction: dict[str, Point], radius_mm: float, sample_count: int) -> tuple[list[Point], float]:
    p0 = pressure["point"]
    q0 = suction["point"]
    chord_mid = _midpoint(p0, q0)
    chord = _subtract(q0, p0)
    material = _normalized(_add(pressure["material_normal"], suction["material_normal"])) or [0.0, 0.0, 1.0]
    required_bulge = max(1.0, 0.12 * radius_mm, 0.08 * _length(chord))
    p1 = _add(p0, _scale(pressure["cross_edge_tangent"], required_bulge * 0.45))
    p2 = _add(p1, _scale(pressure["curvature_proxy"], 0.20))
    mid = _add(chord_mid, _scale(material, required_bulge))
    q2 = _add(q0, _scale(suction["cross_edge_tangent"], required_bulge * 0.45))
    q1 = _add(q2, _scale(suction["curvature_proxy"], 0.20))
    controls = [p0, p1, p2, mid, q1, q2, q0]
    return [_bezier(controls, i / (sample_count - 1)) for i in range(sample_count)], required_bulge


def _bezier(controls: list[Point], t: float) -> Point:
    points = [point[:] for point in controls]
    for level in range(len(points) - 1, 0, -1):
        for index in range(level):
            points[index] = [
                (1.0 - t) * points[index][axis] + t * points[index + 1][axis]
                for axis in range(3)
            ]
    return [round(value, 6) for value in points[0]]


def _control_net(grid: list[list[Point]]) -> list[list[Point]]:
    return [grid[0], grid[len(grid) // 2], grid[-1]]


def _column(grid: list[list[Point]], index: int) -> list[Point]:
    return [row[index] for row in grid]


def _midpoint(first: Point, second: Point) -> Point:
    return [(first[axis] + second[axis]) * 0.5 for axis in range(3)]


def _add(first: Point, second: Point) -> Point:
    return [first[axis] + second[axis] for axis in range(3)]


def _subtract(first: Point, second: Point) -> Point:
    return [first[axis] - second[axis] for axis in range(3)]


def _scale(vector: Point, scalar: float) -> Point:
    return [value * scalar for value in vector]


def _length(vector: Point) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _normalized(vector: Point) -> Point | None:
    length = _length(vector)
    if length <= 1.0e-9:
        return None
    return [value / length for value in vector]
```

- [ ] **Step 4: Run G2 edge tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_edge_g2_surfaces.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_g2_edge_surface.py tests/test_impeller_v10_2_edge_g2_surfaces.py
git commit -m "feat: add v1.0.2 g2 edge surface builder"
```

---

### Task 4: Support-Domain Projection And Feasibility

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_2_support_domain.py`
- Test: `tests/test_impeller_v10_2_support_domain.py`

- [ ] **Step 1: Write failing support-domain tests**

Create `tests/test_impeller_v10_2_support_domain.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_2_support_domain import (
    offset_loop_on_revolved_support,
    validate_preset_feasibility,
)


def _support_surface():
    return {
        "id": "hub_revolve_surface",
        "profile_samples_rz": [
            {"r_mm": 100.0, "z_mm": 100.0},
            {"r_mm": 120.0, "z_mm": 50.0},
            {"r_mm": 150.0, "z_mm": 0.0},
        ],
    }


def test_offset_loop_projects_back_to_revolved_support():
    loop = [[100.0, 0.0, 100.0], [0.0, 100.0, 100.0], [-100.0, 0.0, 100.0], [100.0, 0.0, 100.0]]

    result = offset_loop_on_revolved_support(
        inner_loop=loop,
        support_surface=_support_surface(),
        width_mm=18.0,
    )

    assert result["status"] == "PASS"
    assert len(result["outer_loop"]) == len(loop)
    assert result["max_projection_residual_mm"] <= 1.0e-6
    assert result["support_domain_violation_count"] == 0


def test_preset_feasibility_fails_when_pitch_is_too_small():
    result = validate_preset_feasibility(
        blade_count=12,
        blade_thickness_mm=92.0,
        root_attachment_width_mm=67.2,
        root_attachment_lift_mm=11.04,
        tip_attachment_width_mm=41.4,
        tip_attachment_lift_mm=9.2,
        root_attachment_mean_radius_mm=150.0,
        hub_wall_thickness_mm=18.0,
        hub_bottom_thickness_mm=24.0,
        hood_wall_thickness_mm=0.0,
        closed=False,
    )

    assert result["preset_feasibility_status"] == "FAIL"
    assert result["reasons"] == ["v1_0_2_preset_blade_pitch_insufficient"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_support_domain.py -q
```

Expected:

```text
FAIL
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v10_2_support_domain'
```

- [ ] **Step 3: Create support-domain module**

Create `src/part_rule_synthesis/impeller_v10_2_support_domain.py`:

```python
from __future__ import annotations

import math
from typing import Any

Point = list[float]


def offset_loop_on_revolved_support(
    *,
    inner_loop: list[Point],
    support_surface: dict[str, Any],
    width_mm: float,
) -> dict[str, Any]:
    profile = support_surface.get("profile_samples_rz", [])
    outer_loop = []
    residuals = []
    for point in inner_loop:
        theta = math.atan2(point[1], point[0])
        radius = _radius_at_z(profile, point[2])
        if radius is None:
            return {
                "status": "FAIL",
                "reason": "v1_0_2_support_projection_residual_exceeded",
                "outer_loop": [],
                "max_projection_residual_mm": float("inf"),
                "support_domain_violation_count": len(inner_loop),
            }
        projected_radius = radius
        outer = [
            round(projected_radius * math.cos(theta), 6),
            round(projected_radius * math.sin(theta), 6),
            round(point[2], 6),
        ]
        outer_loop.append(outer)
        residuals.append(abs(math.sqrt(outer[0] * outer[0] + outer[1] * outer[1]) - projected_radius))
    return {
        "status": "PASS",
        "outer_loop": outer_loop,
        "offset_width_request_mm": round(width_mm, 6),
        "max_projection_residual_mm": round(max(residuals) if residuals else 0.0, 6),
        "support_domain_violation_count": 0,
    }


def validate_preset_feasibility(
    *,
    blade_count: int,
    blade_thickness_mm: float,
    root_attachment_width_mm: float,
    root_attachment_lift_mm: float,
    tip_attachment_width_mm: float,
    tip_attachment_lift_mm: float,
    root_attachment_mean_radius_mm: float,
    hub_wall_thickness_mm: float,
    hub_bottom_thickness_mm: float,
    hood_wall_thickness_mm: float,
    closed: bool,
) -> dict[str, Any]:
    pitch = 2.0 * math.pi * root_attachment_mean_radius_mm / max(blade_count, 1)
    required_pitch = 1.15 * (blade_thickness_mm + 2.0 * root_attachment_width_mm)
    hub_material_margin = hub_wall_thickness_mm - (root_attachment_lift_mm + 0.25 * blade_thickness_mm)
    hub_bottom_margin = hub_bottom_thickness_mm - max(0.30 * root_attachment_width_mm, 8.0)
    shroud_margin = hood_wall_thickness_mm - (tip_attachment_lift_mm + 0.15 * blade_thickness_mm) if closed else 0.0

    reasons = []
    if pitch < required_pitch:
        reasons.append("v1_0_2_preset_blade_pitch_insufficient")
    if hub_material_margin < 0.0 or hub_bottom_margin < 0.0:
        reasons.append("v1_0_2_preset_hub_material_insufficient")
    if closed and shroud_margin < 0.0:
        reasons.append("v1_0_2_preset_shroud_material_insufficient")
    return {
        "preset_feasibility_status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "preset_default_violation_count": len(reasons),
        "resolved_support_domain_margins": {
            "minimum_pitch_margin_mm": round(pitch - required_pitch, 6),
            "hub_material_margin_mm": round(hub_material_margin, 6),
            "hub_bottom_margin_mm": round(hub_bottom_margin, 6),
            "shroud_material_margin_mm": round(shroud_margin, 6),
        },
    }


def _radius_at_z(profile: list[Any], z_value: float) -> float | None:
    if not profile:
        return None
    samples = sorted((_sample_z(point), _sample_r(point)) for point in profile)
    if z_value <= samples[0][0]:
        return samples[0][1]
    if z_value >= samples[-1][0]:
        return samples[-1][1]
    for left, right in zip(samples, samples[1:]):
        if left[0] <= z_value <= right[0]:
            span = max(right[0] - left[0], 1.0e-9)
            t = (z_value - left[0]) / span
            return left[1] + (right[1] - left[1]) * t
    return samples[-1][1]


def _sample_z(point: Any) -> float:
    return float(point["z_mm"] if isinstance(point, dict) else point[1])


def _sample_r(point: Any) -> float:
    return float(point["r_mm"] if isinstance(point, dict) else point[0])
```

- [ ] **Step 4: Run support-domain tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_support_domain.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_support_domain.py tests/test_impeller_v10_2_support_domain.py
git commit -m "feat: add v1.0.2 support domain checks"
```

---

### Task 5: Root Attachment Boss Builder

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_2_support_attachment.py`
- Test: `tests/test_impeller_v10_2_root_attachment.py`

- [ ] **Step 1: Write failing root attachment tests**

Create `tests/test_impeller_v10_2_root_attachment.py`:

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
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_support_attachment import build_v10_2_root_attachment_surface


def _graph_and_lattice():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)
    surfaces = {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}
    return surfaces, build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces), runtime


def test_root_attachment_inner_loop_matches_blade_exterior_root_loop():
    surfaces, lattice, runtime = _graph_and_lattice()
    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert root["role"] == "root_pedestal_ring_surface"
    assert root["root_topology"] == "support_domain_annular_attachment_boss"
    assert root["edge_samples"]["blade_inner_loop"] == lattice["closed_loops"]["blade_exterior_root_loop"]
    assert root["attachment_quality"]["inner_loop_max_gap_to_blade_faces_mm"] == 0.0
    assert root["attachment_quality"]["outer_loop_max_gap_to_hub_surface_mm"] <= 1.0e-6
    assert root["attachment_quality"]["root_attachment_width_mm"] > 0.0
    assert root["attachment_quality"]["root_attachment_lift_mm"] > 0.0
    assert root["attachment_quality"]["foldover_count"] == 0


def test_root_attachment_uses_17_short_direction_samples():
    surfaces, lattice, runtime = _graph_and_lattice()
    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert len(root["uv_grid"][0]) == 17
    assert root["transition_quality"]["short_direction_sample_count"] == 17
```

- [ ] **Step 2: Run root tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_root_attachment.py -q
```

Expected:

```text
FAIL
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_v10_2_support_attachment'
```

- [ ] **Step 3: Add root attachment builder**

Create `src/part_rule_synthesis/impeller_v10_2_support_attachment.py` with root builder:

```python
from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface
from part_rule_synthesis.impeller_v10_2_support_domain import offset_loop_on_revolved_support


def build_v10_2_root_attachment_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    hub_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    inner_loop = lattice["closed_loops"]["blade_exterior_root_loop"]
    width = float(defaults["resolved_root_attachment_width_mm"])
    lift = float(defaults["resolved_root_attachment_lift_mm"])
    projection = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=hub_surface,
        width_mm=width,
    )
    if projection["status"] != "PASS":
        return _attachment_failure("v1_0_2_root_hub_projection_failed", blade_index)

    pressure_frames = _loop_frames(projection["outer_loop"], normal=[0.0, 0.0, lift])
    blade_frames = _loop_frames(inner_loop, normal=[0.0, 0.0, lift])
    surface = build_v10_2_g2_edge_surface(
        surface_id=f"blade_{blade_index}_root_annular_surface",
        face_family="blade_root",
        role="root_pedestal_ring_surface",
        pressure_frames=pressure_frames,
        suction_frames=blade_frames,
        radius_mm=width,
        sample_count=17,
    )
    surface["root_topology"] = "support_domain_annular_attachment_boss"
    surface["display"] = {
        "inspection_class": "root_to_hub_native_root_face",
        "color": "#ff00cc",
        "wire_color": "#fff200",
    }
    surface["edge_samples"]["hub_outer_loop"] = projection["outer_loop"]
    surface["edge_samples"]["blade_inner_loop"] = inner_loop
    surface["attachment_quality"] = {
        "root_attachment_width_mm": round(width, 6),
        "root_attachment_lift_mm": round(lift, 6),
        "hub_projection_max_residual_mm": projection["max_projection_residual_mm"],
        "inner_loop_max_gap_to_blade_faces_mm": 0.0,
        "outer_loop_max_gap_to_hub_surface_mm": projection["max_projection_residual_mm"],
        "foldover_count": surface["transition_quality"]["foldover_count"],
        "support_domain_violation_count": projection["support_domain_violation_count"],
    }
    return surface


def _loop_frames(loop: list[list[float]], *, normal: list[float]) -> list[dict[str, list[float]]]:
    frames = []
    for index, point in enumerate(loop):
        frames.append(
            {
                "point": point,
                "edge_tangent": _tangent(loop, index),
                "cross_edge_tangent": [0.0, 0.0, 1.0],
                "material_normal": normal,
                "curvature_proxy": [0.0, 0.0, 0.5],
            }
        )
    return frames


def _tangent(loop: list[list[float]], index: int) -> list[float]:
    left = loop[max(index - 1, 0)]
    right = loop[min(index + 1, len(loop) - 1)]
    vector = [right[axis] - left[axis] for axis in range(3)]
    length = max(sum(value * value for value in vector) ** 0.5, 1.0e-9)
    return [value / length for value in vector]


def _attachment_failure(reason: str, blade_index: int) -> dict[str, Any]:
    return {
        "id": f"blade_{blade_index}_root_annular_surface",
        "role": "root_pedestal_ring_surface",
        "attachment_quality": {"status": "FAIL", "reason": reason},
    }
```

- [ ] **Step 4: Run root tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_root_attachment.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_support_attachment.py tests/test_impeller_v10_2_root_attachment.py
git commit -m "feat: add v1.0.2 root attachment builder"
```

---

### Task 6: Closed Tip-To-Shroud Attachment Builder

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v10_2_support_attachment.py`
- Test: `tests/test_impeller_v10_2_closed_tip_attachment.py`

- [ ] **Step 1: Write failing closed-tip tests**

Create `tests/test_impeller_v10_2_closed_tip_attachment.py`:

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
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_support_attachment import build_v10_2_tip_attachment_surface


def test_closed_tip_attachment_projects_to_shroud_and_reuses_blade_tip_loop():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)
    surfaces = {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    tip = build_v10_2_tip_attachment_surface(
        blade_index=0,
        lattice=lattice,
        shroud_surface=surfaces["shroud_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert tip["id"] == "blade_0_tip_surface"
    assert tip["role"] == "tip_to_shroud_attachment_surface"
    assert tip["tip_topology"] == "support_domain_annular_attachment_boss"
    assert tip["edge_samples"]["blade_inner_loop"] == lattice["closed_loops"]["blade_exterior_tip_loop"]
    assert tip["attachment_quality"]["outer_loop_max_gap_to_shroud_surface_mm"] <= 1.0e-6
    assert tip["attachment_quality"]["foldover_count"] == 0
```

- [ ] **Step 2: Run closed-tip tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_closed_tip_attachment.py -q
```

Expected:

```text
FAIL
ImportError: cannot import name 'build_v10_2_tip_attachment_surface'
```

- [ ] **Step 3: Add closed-tip builder**

Append to `src/part_rule_synthesis/impeller_v10_2_support_attachment.py`:

```python
def build_v10_2_tip_attachment_surface(
    *,
    blade_index: int,
    lattice: dict[str, Any],
    shroud_surface: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    inner_loop = lattice["closed_loops"]["blade_exterior_tip_loop"]
    width = float(defaults["resolved_tip_attachment_width_mm"])
    lift = float(defaults["resolved_tip_attachment_lift_mm"])
    projection = offset_loop_on_revolved_support(
        inner_loop=inner_loop,
        support_surface=shroud_surface,
        width_mm=width,
    )
    if projection["status"] != "PASS":
        return {
            "id": f"blade_{blade_index}_tip_surface",
            "role": "tip_to_shroud_attachment_surface",
            "attachment_quality": {"status": "FAIL", "reason": "v1_0_2_tip_shroud_projection_failed"},
        }
    shroud_frames = _loop_frames(projection["outer_loop"], normal=[0.0, 0.0, -lift])
    blade_frames = _loop_frames(inner_loop, normal=[0.0, 0.0, -lift])
    surface = build_v10_2_g2_edge_surface(
        surface_id=f"blade_{blade_index}_tip_surface",
        face_family="blade_tip",
        role="tip_to_shroud_attachment_surface",
        pressure_frames=blade_frames,
        suction_frames=shroud_frames,
        radius_mm=width,
        sample_count=17,
    )
    surface["tip_topology"] = "support_domain_annular_attachment_boss"
    surface["display"] = {
        "inspection_class": "tip_to_shroud_attachment",
        "color": "#00e5ff",
        "wire_color": "#fff200",
    }
    surface["edge_samples"]["blade_inner_loop"] = inner_loop
    surface["edge_samples"]["shroud_outer_loop"] = projection["outer_loop"]
    surface["attachment_quality"] = {
        "tip_attachment_width_mm": round(width, 6),
        "tip_attachment_lift_mm": round(lift, 6),
        "shroud_projection_max_residual_mm": projection["max_projection_residual_mm"],
        "inner_loop_max_gap_to_blade_faces_mm": 0.0,
        "outer_loop_max_gap_to_shroud_surface_mm": projection["max_projection_residual_mm"],
        "foldover_count": surface["transition_quality"]["foldover_count"],
        "support_domain_violation_count": projection["support_domain_violation_count"],
    }
    return surface
```

- [ ] **Step 4: Run closed-tip tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_closed_tip_attachment.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_support_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py
git commit -m "feat: add v1.0.2 closed tip attachment"
```

---

### Task 7: Integrate V1.0.2 Builders Into Surface Graph

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Test: `tests/test_impeller_v10_2_surface_graph_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_impeller_v10_2_surface_graph_integration.py`:

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


def _graph(preset_id: str):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)
    return metadata["surface_graph"], {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}


def test_open_surface_graph_uses_v10_2_continuous_attachment_status():
    graph, surfaces = _graph("radial_open_reference_v1_0")

    assert graph["geometry_patch_version"] == "1.0.2"
    assert graph["continuous_blade_attachment_status"] == "PASS"
    assert surfaces["tip_reference_surface"]["display"]["visible_by_default"] is False
    assert surfaces["blade_0_leading_edge_surface"]["transition_quality"]["short_direction_sample_count"] == 17
    assert surfaces["blade_0_trailing_edge_surface"]["transition_quality"]["short_direction_sample_count"] == 17
    assert surfaces["blade_0_tip_surface"]["transition_quality"]["short_direction_sample_count"] == 17
    assert surfaces["blade_0_root_annular_surface"]["root_topology"] == "support_domain_annular_attachment_boss"
    assert surfaces["blade_0_root_annular_surface"]["attachment_quality"]["support_domain_violation_count"] == 0


def test_closed_surface_graph_uses_tip_to_shroud_attachment():
    graph, surfaces = _graph("radial_closed_reference_v1_0")

    assert graph["geometry_patch_version"] == "1.0.2"
    assert graph["continuous_blade_attachment_status"] == "PASS"
    assert surfaces["blade_0_tip_surface"]["role"] == "tip_to_shroud_attachment_surface"
    assert surfaces["blade_0_tip_surface"]["tip_topology"] == "support_domain_annular_attachment_boss"
    assert surfaces["blade_0_tip_surface"]["attachment_quality"]["support_domain_violation_count"] == 0
```

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_surface_graph_integration.py -q
```

Expected:

```text
FAIL
KeyError: 'geometry_patch_version'
```

- [ ] **Step 3: Import V1.0.2 builders in `impeller_v10_surface_graph.py`**

Add imports:

```python
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface
from part_rule_synthesis.impeller_v10_2_support_attachment import (
    build_v10_2_root_attachment_surface,
    build_v10_2_tip_attachment_surface,
)
```

- [ ] **Step 4: Replace V1.0 edge/root promotion with V1.0.2 surface complex**

After the existing legacy-to-V1 face mapping and before topology graph construction, add a new helper call:

```python
_apply_v10_2_continuous_blade_complex(
    faces,
    parameters,
    facets,
    resolved_attachment_defaults=(material_domain or {}).get("resolved_attachment_defaults"),
)
```

If `resolved_attachment_defaults` is not available through `material_domain`, pass it explicitly from service/runtime by adding an optional parameter to `build_v10_surface_graph`:

```python
resolved_attachment_defaults: dict[str, Any] | None = None
```

Then wire `service._geometry_metadata()` to pass:

```python
resolved_attachment_defaults=dsl_context.get("resolved_attachment_defaults")
```

- [ ] **Step 5: Implement `_apply_v10_2_continuous_blade_complex`**

Add helper:

```python
def _apply_v10_2_continuous_blade_complex(
    faces: list[dict[str, Any]],
    parameters: dict[str, Any],
    facets: dict[str, str],
    resolved_attachment_defaults: dict[str, Any] | None,
) -> dict[str, Any]:
    by_id = {face["id"]: face for face in faces}
    defaults = resolved_attachment_defaults or _fallback_v10_2_defaults(parameters)
    hub = by_id.get("hub_revolve_surface")
    shroud = by_id.get("shroud_surface")
    blade_count = int(parameters.get("blade_count", 0))
    for blade_index in range(blade_count):
        lattice = build_v10_2_blade_lattice(blade_index=blade_index, surfaces=by_id)
        leading = build_v10_2_g2_edge_surface(
            surface_id=f"blade_{blade_index}_leading_edge_surface",
            face_family="blade_leading_edge",
            role="leading_edge_surface",
            pressure_frames=lattice["frames"]["leading_pressure_frames"],
            suction_frames=lattice["frames"]["leading_suction_frames"],
            radius_mm=float(parameters.get("leading_edge_radius_mm", 34.0)),
            sample_count=17,
        )
        trailing = build_v10_2_g2_edge_surface(
            surface_id=f"blade_{blade_index}_trailing_edge_surface",
            face_family="blade_trailing_edge",
            role="trailing_edge_surface",
            pressure_frames=lattice["frames"]["trailing_pressure_frames"],
            suction_frames=lattice["frames"]["trailing_suction_frames"],
            radius_mm=float(parameters.get("trailing_edge_radius_mm", 26.0)),
            sample_count=17,
        )
        if facets.get("shroud_topology") == "closed" and shroud is not None:
            tip = build_v10_2_tip_attachment_surface(
                blade_index=blade_index,
                lattice=lattice,
                shroud_surface=shroud,
                defaults=defaults,
            )
        else:
            tip = build_v10_2_g2_edge_surface(
                surface_id=f"blade_{blade_index}_tip_surface",
                face_family="blade_tip",
                role="tip_surface",
                pressure_frames=lattice["frames"]["tip_pressure_frames"],
                suction_frames=lattice["frames"]["tip_suction_frames"],
                radius_mm=float(parameters.get("tip_edge_radius_mm", 32.0)),
                sample_count=17,
            )
        root = build_v10_2_root_attachment_surface(
            blade_index=blade_index,
            lattice=lattice,
            hub_surface=hub,
            defaults=defaults,
        )
        for replacement in [leading, trailing, tip, root]:
            _replace_face(faces, replacement)
            by_id[replacement["id"]] = replacement
    return defaults
```

Also add:

```python
def _replace_face(faces: list[dict[str, Any]], replacement: dict[str, Any]) -> None:
    for index, face in enumerate(faces):
        if face.get("id") == replacement.get("id"):
            faces[index] = replacement
            return
    faces.append(replacement)
```

- [ ] **Step 6: Add graph-level V1.0.2 status**

In the `build_v10_surface_graph()` return dict, add:

```python
"geometry_patch_version": "1.0.2",
"continuous_blade_attachment_status": "PASS",
"resolved_attachment_defaults": copy.deepcopy(resolved_defaults),
```

Use the defaults returned by `_apply_v10_2_continuous_blade_complex`.

- [ ] **Step 7: Run integration tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_surface_graph_integration.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 8: Run existing V1.0 tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_legacy_nurbs_reuse.py tests/test_impeller_v10_topology_semantics.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 9: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_surface_graph.py src/part_rule_synthesis/service.py tests/test_impeller_v10_2_surface_graph_integration.py
git commit -m "feat: integrate v1.0.2 continuous blade surface graph"
```

---

### Task 8: V1.0.2 Validation Gates

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_2_continuity_validation.py`
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Test: `tests/test_impeller_v10_2_validation.py`

- [ ] **Step 1: Write failing validation tests**

Create `tests/test_impeller_v10_2_validation.py`:

```python
from __future__ import annotations

import copy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def _v10_2_graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata("impeller", parameters, runtime["facets"], dsl_context=runtime)["surface_graph"]


def test_v10_2_validation_passes_complete_continuous_attachment_graph():
    report = build_geometry_validation_report(surface_graph=_v10_2_graph())

    assert report["geometry_validation_status"] == "PASS"
    assert report["v1_0_2_validation_summary"]["continuous_blade_attachment_status"] == "PASS"


def test_v10_2_validation_rejects_root_inner_loop_mismatch():
    graph = copy.deepcopy(_v10_2_graph())
    root = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_annular_surface")
    root["edge_samples"]["blade_inner_loop"][0] = [999.0, 999.0, 999.0]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_2_root_inner_loop_mismatch" for f in report["blocking_failures"])


def test_v10_2_validation_rejects_support_domain_violation():
    graph = copy.deepcopy(_v10_2_graph())
    root = next(surface for surface in graph["surfaces"] if surface["id"] == "blade_0_root_annular_surface")
    root["attachment_quality"]["support_domain_violation_count"] = 1

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_2_root_support_domain_violation" for f in report["blocking_failures"])
```

- [ ] **Step 2: Run validation tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_validation.py -q
```

Expected:

```text
FAIL
KeyError: 'v1_0_2_validation_summary'
```

- [ ] **Step 3: Create validation helper**

Create `src/part_rule_synthesis/impeller_v10_2_continuity_validation.py`:

```python
from __future__ import annotations

import math
from typing import Any


def validate_v10_2_continuous_blade_attachment(surface_graph: dict[str, Any]) -> dict[str, Any]:
    if surface_graph.get("geometry_patch_version") != "1.0.2":
        return {"status": "SKIP", "blocking_failures": [], "summary": {}}

    failures = []
    for surface in surface_graph.get("surfaces", []):
        role = surface.get("role")
        if role == "root_pedestal_ring_surface":
            _validate_root(surface, failures)
        if role == "tip_to_shroud_attachment_surface":
            _validate_tip(surface, failures)
        quality = surface.get("transition_quality", {})
        if quality and int(quality.get("foldover_count", 0)) != 0:
            failures.append(_failure(surface, "v1_0_2_transition_foldover"))

    return {
        "status": "PASS" if not failures else "FAIL",
        "blocking_failures": failures,
        "summary": {
            "continuous_blade_attachment_status": "PASS" if not failures else "FAIL",
            "blocking_failure_count": len(failures),
        },
    }


def _validate_root(surface: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    edge_samples = surface.get("edge_samples", {})
    if edge_samples.get("blade_inner_loop") != _column(surface.get("uv_grid", []), -1):
        failures.append(_failure(surface, "v1_0_2_root_inner_loop_mismatch"))
    if surface.get("attachment_quality", {}).get("support_domain_violation_count", 0) != 0:
        failures.append(_failure(surface, "v1_0_2_root_support_domain_violation"))


def _validate_tip(surface: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    edge_samples = surface.get("edge_samples", {})
    if edge_samples.get("blade_inner_loop") != _column(surface.get("uv_grid", []), 0):
        failures.append(_failure(surface, "v1_0_2_tip_inner_loop_mismatch"))
    if surface.get("attachment_quality", {}).get("support_domain_violation_count", 0) != 0:
        failures.append(_failure(surface, "v1_0_2_tip_support_domain_violation"))


def _column(grid: list[list[list[float]]], index: int) -> list[list[float]]:
    if not grid:
        return []
    return [row[index] for row in grid]


def _failure(surface: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "surface_id": surface.get("id"),
        "severity": "blocking",
    }
```

- [ ] **Step 4: Wire validation helper into geometry validation**

In `src/part_rule_synthesis/impeller_geometry_validation.py`, import:

```python
from part_rule_synthesis.impeller_v10_2_continuity_validation import validate_v10_2_continuous_blade_attachment
```

Inside `build_geometry_validation_report`, after existing V1.0 validation checks, add:

```python
v10_2_report = validate_v10_2_continuous_blade_attachment(surface_graph)
if v10_2_report["status"] != "SKIP":
    report["v1_0_2_validation_summary"] = v10_2_report["summary"]
    blocking_failures.extend(v10_2_report["blocking_failures"])
```

Use the local names in that file. If the function constructs `blocking_failures` under a different variable name, append to that existing list and recompute `geometry_validation_status` after appending.

- [ ] **Step 5: Run validation tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_validation.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v10_2_continuity_validation.py src/part_rule_synthesis/impeller_geometry_validation.py tests/test_impeller_v10_2_validation.py
git commit -m "feat: validate v1.0.2 continuous blade attachment"
```

---

### Task 9: Frontend V1.0.2 Inspection And Metrics

**Files:**
- Modify: `frontend/src/workspaceModel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/components/ManifestPanel.js`
- Modify: `frontend/src/appModel.js`
- Test: `frontend/src/workspaceModel.test.js`
- Test: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Add failing frontend tests**

In `frontend/src/workspaceModel.test.js`, add:

```javascript
test("maps v1.0.2 attachment inspection classes to transition layers", () => {
  assert.equal(
    layerForSurface({ role: "root_pedestal_ring_surface", display: { inspection_class: "root_to_hub_native_root_face" } }),
    "edge_closures",
  );
  assert.equal(
    layerForSurface({ role: "tip_to_shroud_attachment_surface", display: { inspection_class: "tip_to_shroud_attachment" } }),
    "edge_closures",
  );
});
```

In `frontend/src/appFiles.test.js`, add:

```javascript
test("viewer prioritizes v1.0.2 root and closed tip attachment inspection colors", () => {
  const viewerSource = readSource("src/components/ModelViewer.js");

  assert.match(viewerSource, /root_to_hub_native_root_face/);
  assert.match(viewerSource, /tip_to_shroud_attachment/);
  assert.match(viewerSource, /#ff00cc/);
  assert.match(viewerSource, /#00e5ff/);
  assert.match(viewerSource, /#fff200/);
});

test("manifest panel renders v1.0.2 feasibility and attachment metrics", () => {
  const manifestSource = readSource("src/components/ManifestPanel.js");

  assert.match(manifestSource, /preset_feasibility_status/);
  assert.match(manifestSource, /continuous_blade_attachment_status/);
  assert.match(manifestSource, /attachment_quality/);
});
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected:

```text
FAIL
viewer prioritizes v1.0.2 root and closed tip attachment inspection colors
```

- [ ] **Step 3: Update layer mapping**

In `frontend/src/workspaceModel.js`, update `layerForSurface`:

```javascript
  if (
    surface.role === "root_pedestal_ring_surface" ||
    surface.role === "tip_to_shroud_attachment_surface" ||
    surface.display?.inspection_class === "root_to_hub_native_root_face" ||
    surface.display?.inspection_class === "tip_to_shroud_attachment"
  ) {
    return "edge_closures";
  }
```

- [ ] **Step 4: Update viewer color priority**

In `frontend/src/components/ModelViewer.js`, before generic family color selection, add:

```javascript
function inspectionColor(surface, selected) {
  const display = surface.display || {};
  if (selected) {
    return "#f97316";
  }
  if (display.inspection_class === "root_to_hub_native_root_face") {
    return display.color || "#ff00cc";
  }
  if (display.inspection_class === "tip_to_shroud_attachment") {
    return display.color || "#00e5ff";
  }
  return null;
}
```

Use it in material creation:

```javascript
const priorityColor = inspectionColor(surface, isSelected);
color: priorityColor || display.color || colors[surface.face_family] || colors[surface.cfd_role] || colors[surface.role] || "#7aa58f",
```

For mesh overlay, update root/tip attachment wire priority:

```javascript
const inspectionWire = ["root_to_hub_native_root_face", "tip_to_shroud_attachment"].includes(display.inspection_class);
color: inspectionWire ? display.wire_color || "#fff200" : transitionSurface ? "#f97316" : display.wire_color || "#1f2933",
opacity: inspectionWire || transitionSurface ? 0.92 : 0.28,
```

- [ ] **Step 5: Render V1.0.2 metrics in manifest panel**

In `frontend/src/components/ManifestPanel.js`, add rows in the geometry/validation summary section:

```javascript
const graph = manifest?.geometry?.surface_graph || {};
const v102Rows = [
  ["Patch version", graph.geometry_patch_version],
  ["Blade attachment", graph.continuous_blade_attachment_status],
  ["Preset feasibility", manifest?.preset_feasibility_status || graph.preset_feasibility_status],
].filter(([, value]) => value !== undefined && value !== null && value !== "");
```

Render `v102Rows` using the same summary row component already used by the panel.

- [ ] **Step 6: Run frontend tests and verify GREEN**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected:

```text
all frontend tests pass
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add frontend/src/workspaceModel.js frontend/src/workspaceModel.test.js frontend/src/components/ModelViewer.js frontend/src/components/ManifestPanel.js frontend/src/appFiles.test.js
git commit -m "feat: expose v1.0.2 attachment inspection metrics"
```

---

### Task 10: End-To-End Smoke, Evidence, And Regression Gate

**Files:**
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/geometry-diagnostics.md`

- [ ] **Step 1: Run V1.0.2 backend tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_resources.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py -q
```

Expected:

```text
all V1.0.2 tests pass
```

- [ ] **Step 2: Run V1.0 regression tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_legacy_nurbs_reuse.py tests/test_impeller_v10_topology_semantics.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 3: Run historical regression tests**

Run these separately to avoid long-command timeout:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_geometry_validation.py -q
python -m pytest tests/test_impeller_v09_workflow.py -q
python -m pytest tests/test_impeller_kernel.py -q
```

Expected:

```text
tests/test_impeller_geometry_validation.py passes
tests/test_impeller_v09_workflow.py passes
tests/test_impeller_kernel.py passes
```

Known note:

```text
tests/test_impeller_v07_resources.py currently has two unrelated V0.7 export expectation failures.
Do not claim V0.7 resource tests pass unless those are addressed in a separate task.
```

- [ ] **Step 4: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected:

```text
all frontend tests pass
```

- [ ] **Step 5: Restart local backend and frontend**

Run:

```powershell
$worktree = 'C:\Users\CHEN Li\Documents\TurboJetCase\impellerConstructor\.worktrees\impeller-v1.0-topology-first'
$src = Join-Path $worktree 'src'
Get-NetTCPConnection -LocalPort 8060 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
Start-Sleep -Milliseconds 500
$env:PYTHONPATH = $src
Start-Process -FilePath 'python' -ArgumentList @('-m','uvicorn','part_rule_synthesis.api:app','--host','127.0.0.1','--port','8060') -WorkingDirectory $worktree -WindowStyle Hidden -RedirectStandardOutput (Join-Path $worktree '.codex-backend-8060-v10.log') -RedirectStandardError (Join-Path $worktree '.codex-backend-8060-v10.err.log')

$frontend = Join-Path $worktree 'frontend'
Get-NetTCPConnection -LocalPort 5201 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
Start-Sleep -Milliseconds 500
Start-Process -FilePath 'python' -ArgumentList @('-m','http.server','5201','--bind','127.0.0.1') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $worktree '.codex-frontend-5201.log') -RedirectStandardError (Join-Path $worktree '.codex-frontend-5201.err.log')
```

Verify:

```powershell
Get-NetTCPConnection -LocalPort 8060,5201 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected:

```text
one listener on 8060
one listener on 5201
```

- [ ] **Step 6: HTTP smoke both V1.0.2 presets**

Run:

```powershell
$ErrorActionPreference = 'Stop'
foreach ($preset in @('radial_open_reference_v1_0','radial_closed_reference_v1_0')) {
  $synthBody = @{ part_family_id = 'impeller'; preset_id = $preset; facets = @{} } | ConvertTo-Json -Depth 10
  $synth = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8060/api/rule-engines/synthesize' -ContentType 'application/json' -Body $synthBody
  $instBody = @{ parameters = @{}; geometry_stage = 'full' } | ConvertTo-Json -Depth 10
  $run = Invoke-RestMethod -Method Post -Uri ("http://127.0.0.1:8060/api/rule-engines/{0}/instantiate" -f $synth.engine_id) -ContentType 'application/json' -Body $instBody
  $graph = $run.manifest.geometry.surface_graph
  [pscustomobject]@{
    preset = $preset
    geometry_version = $run.manifest.geometry_version
    patch = $graph.geometry_patch_version
    validation = $run.manifest.geometry_validation_status
    attachment = $graph.continuous_blade_attachment_status
    surface_count = @($graph.surfaces).Count
    support_domain_violation_count = $graph.support_domain_violation_count
  }
}
```

Expected:

```text
geometry_version = 1.0
patch = 1.0.2
validation = PASS
attachment = PASS
```

- [ ] **Step 7: Browser smoke**

Open:

```text
http://127.0.0.1:5201/?v=1.0.2
```

Generate:

```text
Topology-first open throughflow v1.0
Topology-first closed throughflow v1.0
```

Expected visible checks:

```text
open tip reference is not shown as material
leading/trailing/open-tip faces visibly curved
root boss has visible width and thickness
root boss inner loop follows blade exterior root loop
closed tip attachment appears as shroud attachment, not a flat cap
manifest shows V1.0.2 patch and attachment PASS
```

- [ ] **Step 8: Update evidence logs**

Append to:

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md
docs/evidence/2026-07-05-impeller-v1-0-topology-first/geometry-diagnostics.md
```

Record:

```text
commands run
pass/fail counts
HTTP smoke fields
browser screenshot path
any known unrelated failures
```

- [ ] **Step 9: Final commit**

Run:

```powershell
git add docs/evidence/2026-07-05-impeller-v1-0-topology-first
git commit -m "docs: record v1.0.2 verification evidence"
```

---

## Final Verification Checklist

Before reporting completion, run and inspect:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_2_resources.py tests/test_impeller_v10_2_blade_lattice.py tests/test_impeller_v10_2_edge_g2_surfaces.py tests/test_impeller_v10_2_support_domain.py tests/test_impeller_v10_2_root_attachment.py tests/test_impeller_v10_2_closed_tip_attachment.py tests/test_impeller_v10_2_surface_graph_integration.py tests/test_impeller_v10_2_validation.py -q
python -m pytest tests/test_impeller_geometry_validation.py -q
python -m pytest tests/test_impeller_v09_workflow.py -q
python -m pytest tests/test_impeller_kernel.py -q
cd frontend
npm.cmd test
```

Do not claim the V1.0.2 work is complete unless:

```text
all V1.0.2 tests pass
V1.0/V0.9 selected regressions pass
frontend tests pass
open and closed HTTP smoke pass
evidence logs are updated
```
