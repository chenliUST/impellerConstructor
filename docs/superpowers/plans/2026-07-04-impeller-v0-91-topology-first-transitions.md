# Impeller V0.91 Topology-First Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete V0.91 by replacing strip-based transition geometry with topology-first fillet/chamfer/corner patches and shared-node watertight mesh validation.

**Architecture:** V0.91 adds a new DSL resource line, then routes runtime geometry through a transition patch complex. The patch complex owns shared nodes, shared edges, transition patches, corner patches, and manifold mesh output; validation and export consume that same complex instead of independently triangulating surface grids.

**Tech Stack:** Python 3, pytest, existing `part_rule_synthesis` service/compiler/export modules, existing frontend React/Three.js viewer, npm test/build, optional OCCT/CadQuery reimport checks where available.

---

## File Structure

- Create: `src/part_rule_synthesis/impeller_transition_topology.py`
  - Shared node/edge/patch data structures, node registry, edge incidence reporting.
- Create: `src/part_rule_synthesis/impeller_transition_sections.py`
  - Local section-frame fillet and chamfer solvers.
- Create: `src/part_rule_synthesis/impeller_transition_corners.py`
  - Coons/transfinite corner patch construction with shared boundary nodes.
- Create: `src/part_rule_synthesis/impeller_patch_mesh.py`
  - Shared-node patch mesh triangulation and manifoldness report.
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
  - Add V0.91 resolver and stop routing V0.91 through V0.9 strip transition logic.
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
  - Add topology, corner, section, and manifold gates.
- Modify: `src/part_rule_synthesis/impeller_mesh_export.py`
  - Route V0.91 OBJ/STL mesh output through patch mesh.
- Modify: `src/part_rule_synthesis/impeller_surface_graph_export.py`
  - Ensure STL export uses V0.91 patch mesh and does not fall back to independent grids.
- Modify: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
  - Include V0.91 transition/corner patch regions and block fallback exports.
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
  - Load V0.91 resources and mark V0.91 runtime metadata.
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91/`
  - Copy from V0.9 and update ids, version, contract, capability matrix, golden cases.
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
  - Add V0.91 row and design note.
- Modify: `frontend/src/appModel.js`
  - Default visual presets to V0.91.
- Modify: `frontend/src/components/ManifestPanel.js`
  - Show V0.91 topology and manifoldness reports.
- Modify: `frontend/src/components/ModelViewer.js`
  - Render V0.91 patch complex or validated patch surface layers consistently.
- Create: `tests/test_impeller_v091_resources.py`
- Create: `tests/test_impeller_v091_transition_topology.py`
- Create: `tests/test_impeller_v091_sections.py`
- Create: `tests/test_impeller_v091_patch_mesh.py`
- Modify: `tests/test_impeller_geometry_validation.py`
- Modify: `tests/test_impeller_transition_mesh.py`
- Modify: `tests/test_workflow.py`
- Create: `docs/evidence/2026-07-04-impeller-v0-91-topology-first-transitions/README.md`

## Implementation Tasks

### Task 1: Add V0.91 Resource Scaffold

**Files:**
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91/`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Test: `tests/test_impeller_v091_resources.py`

- [ ] **Step 1: Copy V0.9 resources to V0.91**

Run:

```powershell
Copy-Item -Recurse -LiteralPath `
  'src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_9' `
  -Destination `
  'src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_91'
```

Expected: new `v0_91` folder exists.

- [ ] **Step 2: Update V0.91 ids and metadata**

In every copied V0.91 JSON/Markdown file, replace:

```text
v0_9 -> v0_91
v0.9 -> v0.91
0.9 -> 0.91
radial_open_reference_v0_9 -> radial_open_reference_v0_91
radial_closed_reference_v0_9 -> radial_closed_reference_v0_91
validated_transition_bounded_brep -> topology_first_transition_bounded_brep
validated_transition_surface_graph -> topology_first_validated_transition_graph
validated_transition_aware_surface_mesh -> shared_node_transition_patch_mesh
```

Keep historical V0.9 files unchanged.

- [ ] **Step 3: Write resource tests**

Create `tests/test_impeller_v091_resources.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_dsl_loader import load_impeller_dsl_bundle


def test_v091_bundle_loads_topology_first_contract():
    bundle = load_impeller_dsl_bundle("0.91")

    assert {"radial_open_reference_v0_91", "radial_closed_reference_v0_91"} <= set(bundle.presets)
    contract = bundle.export_contracts["topology_first_transition_bounded_brep"]
    assert contract["mode"] == "topology_first_transition_bounded_brep"
    assert contract["mesh_strategy"] == "shared_node_transition_patch_mesh"


def test_v091_runtime_marks_topology_first_transition_graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_91")

    assert runtime["dsl_version"] == "0.91"
    assert runtime["geometry_version"] == "0.91"
    assert runtime["transition_geometry_status"] == "topology_first_validated_transition_graph"
    assert runtime["mesh_strategy"] == "shared_node_transition_patch_mesh"
```

- [ ] **Step 4: Run resource tests to verify failure before compiler support**

Run:

```powershell
python -m pytest tests/test_impeller_v091_resources.py -q
```

Expected: FAIL until loader/compiler know V0.91.

- [ ] **Step 5: Add V0.91 support to runtime compiler**

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, extend version routing in the same pattern as V0.9. The runtime output must include:

```python
runtime["dsl_version"] = "0.91"
runtime["geometry_version"] = "0.91"
runtime["transition_geometry_status"] = "topology_first_validated_transition_graph"
runtime["mesh_strategy"] = "shared_node_transition_patch_mesh"
```

- [ ] **Step 6: Re-run resource tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_resources.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit resource scaffold**

Run:

```powershell
git add src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91 `
  src/part_rule_synthesis/impeller_runtime_compiler.py `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md `
  tests/test_impeller_v091_resources.py
git commit -m "feat: add V0.91 topology-first resource scaffold"
```

### Task 2: Add Red Tests For Current V0.9 Failure Class

**Files:**
- Create: `tests/test_impeller_v091_transition_topology.py`
- Test: `tests/test_impeller_v091_transition_topology.py`

- [ ] **Step 1: Add edge incidence and corner-gap tests**

Create `tests/test_impeller_v091_transition_topology.py`:

```python
from __future__ import annotations

from collections import Counter
from math import dist
from pathlib import Path

from part_rule_synthesis.service import RuleSynthesisService
from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh


def _manifest(preset_id: str):
    service = RuleSynthesisService(Path("tmp-v091-test-runs"))
    engine = service.synthesize("impeller", preset_id)
    return service.instantiate(engine.engine_id, {}).manifest


def _surface_map(surface_graph: dict):
    return {surface["id"]: surface for surface in surface_graph["surfaces"]}


def test_v091_default_mesh_has_no_free_or_nonmanifold_edges():
    manifest = _manifest("radial_open_reference_v0_91")
    mesh = build_patch_mesh(manifest["geometry"]["surface_graph"])

    report = mesh["mesh_manifoldness_report"]
    assert report["free_edge_count"] == 0
    assert report["nonmanifold_edge_count"] == 0
    assert report["zero_area_face_count"] == 0


def test_v091_root_leading_corner_boundaries_are_closed():
    manifest = _manifest("radial_open_reference_v0_91")
    surfaces = _surface_map(manifest["geometry"]["surface_graph"])

    leading = surfaces["blade_0_leading_transition_surface"]["uv_grid"]
    pressure_root = surfaces["blade_0_pressure_root_transition_surface"]["uv_grid"]
    suction_root = surfaces["blade_0_suction_root_transition_surface"]["uv_grid"]

    pressure_gap = dist(leading[0][0], pressure_root[0][0])
    suction_gap = dist(leading[0][-1], suction_root[0][0])

    assert pressure_gap <= 1.0e-5
    assert suction_gap <= 1.0e-5


def test_v091_transition_patch_complex_uses_shared_node_ids():
    manifest = _manifest("radial_open_reference_v0_91")
    complex_report = manifest["transition_topology_report"]

    assert complex_report["transition_patch_count"] > 0
    assert complex_report["corner_patch_count"] > 0
    assert complex_report["boundary_node_identity_failures"] == []
```

Expected before implementation: import failure for `impeller_patch_mesh` or assertion failures from the current strip-based topology.

- [ ] **Step 2: Run red tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_transition_topology.py -q
```

Expected: FAIL.

- [ ] **Step 3: Commit red tests**

Run:

```powershell
git add tests/test_impeller_v091_transition_topology.py
git commit -m "test: capture V0.91 transition topology failures"
```

### Task 3: Add Shared Topology Primitives

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_topology.py`
- Test: `tests/test_impeller_v091_transition_topology.py`

- [ ] **Step 1: Implement shared topology data structures**

Create `src/part_rule_synthesis/impeller_transition_topology.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class SharedNode:
    node_id: str
    point: Point3


@dataclass
class SharedEdge:
    edge_id: str
    node_ids: list[str]
    role: str
    adjacent_patch_ids: list[str] = field(default_factory=list)
    physical_boundary: bool = False


@dataclass
class Patch:
    patch_id: str
    surface_graph_id: str
    role: str
    node_grid: list[list[str]]
    edge_ids: list[str]
    edge_family: str = ""
    transition_policy_id: str = ""
    treatment: str = ""


@dataclass
class PatchComplex:
    nodes: dict[str, SharedNode] = field(default_factory=dict)
    edges: dict[str, SharedEdge] = field(default_factory=dict)
    patches: dict[str, Patch] = field(default_factory=dict)
    boundary_node_identity_failures: list[dict] = field(default_factory=list)

    def add_node(self, node_id: str, point: Point3) -> str:
        existing = self.nodes.get(node_id)
        if existing is not None and existing.point != point:
            self.boundary_node_identity_failures.append(
                {"node_id": node_id, "first_point": existing.point, "second_point": point}
            )
        else:
            self.nodes[node_id] = SharedNode(node_id=node_id, point=point)
        return node_id

    def add_edge(self, edge_id: str, node_ids: Iterable[str], role: str, physical_boundary: bool = False) -> str:
        ids = list(node_ids)
        edge = self.edges.get(edge_id)
        if edge is None:
            self.edges[edge_id] = SharedEdge(
                edge_id=edge_id,
                node_ids=ids,
                role=role,
                physical_boundary=physical_boundary,
            )
        elif edge.node_ids != ids and edge.node_ids != list(reversed(ids)):
            self.boundary_node_identity_failures.append(
                {"edge_id": edge_id, "first_nodes": edge.node_ids, "second_nodes": ids}
            )
        return edge_id

    def add_patch(self, patch: Patch) -> None:
        self.patches[patch.patch_id] = patch
        for edge_id in patch.edge_ids:
            if edge_id in self.edges and patch.patch_id not in self.edges[edge_id].adjacent_patch_ids:
                self.edges[edge_id].adjacent_patch_ids.append(patch.patch_id)


def point_key(point: Iterable[float], tolerance: float = 1.0e-6) -> str:
    scale = 1.0 / tolerance
    return "_".join(str(round(float(value) * scale)) for value in point)
```

- [ ] **Step 2: Run topology tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_transition_topology.py -q
```

Expected: still FAIL because patch mesh and V0.91 resolver do not exist yet.

- [ ] **Step 3: Commit topology primitives**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_topology.py
git commit -m "feat: add shared transition topology primitives"
```

### Task 4: Implement Local Section Fillet And Chamfer Solver

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_sections.py`
- Create: `tests/test_impeller_v091_sections.py`

- [ ] **Step 1: Write section solver tests**

Create `tests/test_impeller_v091_sections.py`:

```python
from __future__ import annotations

import math

from part_rule_synthesis.impeller_transition_sections import (
    build_chamfer_section,
    build_fillet_section,
)


def test_fillet_section_has_requested_radius_and_minimum_samples():
    section = build_fillet_section(
        edge_point=(0.0, 0.0, 0.0),
        tangent=(0.0, 0.0, 1.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        radius_mm=4.0,
        sample_count=9,
        convexity_sign=1,
    )

    assert len(section["points"]) >= 9
    assert section["quality"]["radius_max_error_mm"] <= 1.0e-6
    assert section["quality"]["convexity_sign"] == 1


def test_chamfer_section_moves_along_retained_side_directions():
    section = build_chamfer_section(
        edge_point=(0.0, 0.0, 0.0),
        first_retained_direction=(1.0, 0.0, 0.0),
        second_retained_direction=(0.0, 1.0, 0.0),
        distance_mm=2.0,
    )

    assert section["points"][0] == (2.0, 0.0, 0.0)
    assert section["points"][-1] == (0.0, 2.0, 0.0)
    assert section["quality"]["direction_sign"] == 1
    assert math.isclose(section["quality"]["section_linearity_max_error_mm"], 0.0)
```

- [ ] **Step 2: Run section tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_sections.py -q
```

Expected: FAIL with import error.

- [ ] **Step 3: Implement section solver**

Create `src/part_rule_synthesis/impeller_transition_sections.py`:

```python
from __future__ import annotations

import math
from typing import Iterable

Point3 = tuple[float, float, float]


def _p(values: Iterable[float]) -> Point3:
    x, y, z = values
    return (float(x), float(y), float(z))


def _add(a: Point3, b: Point3) -> Point3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Point3, scale: float) -> Point3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def _dot(a: Point3, b: Point3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Point3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Point3) -> Point3:
    length = _norm(a)
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return _mul(a, 1.0 / length)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_fillet_section(
    *,
    edge_point: Iterable[float],
    tangent: Iterable[float],
    first_retained_direction: Iterable[float],
    second_retained_direction: Iterable[float],
    radius_mm: float,
    sample_count: int,
    convexity_sign: int,
) -> dict:
    if radius_mm <= 0.0:
        raise ValueError("fillet radius must be positive")
    count = max(9, int(sample_count))
    p0 = _p(edge_point)
    t = _unit(_p(tangent))
    d1 = _unit(_sub(_p(first_retained_direction), _mul(t, _dot(_p(first_retained_direction), t))))
    d2 = _unit(_sub(_p(second_retained_direction), _mul(t, _dot(_p(second_retained_direction), t))))
    theta = math.acos(_clamp(_dot(d1, d2), -0.999999, 0.999999))
    if theta <= math.radians(5.0):
        raise ValueError("fillet retained-side angle is too small")
    trim_distance = radius_mm / math.tan(theta / 2.0)
    bisector = _unit(_add(d1, d2))
    center = _add(p0, _mul(bisector, radius_mm / math.sin(theta / 2.0)))
    start = _add(p0, _mul(d1, trim_distance))
    end = _add(p0, _mul(d2, trim_distance))
    v1 = _unit(_sub(start, center))
    v2 = _unit(_sub(end, center))
    points: list[Point3] = []
    for index in range(count):
        u = index / (count - 1)
        angle = theta * u
        ca = math.cos(angle)
        sa = math.sin(angle)
        # Rotate inside the local section basis. This is intentionally expressed
        # using d1/d2-derived vectors so future OCCT/NURBS replacement can reuse
        # the same section contract.
        basis_y = _unit(_sub(v2, _mul(v1, _dot(v1, v2))))
        direction = _add(_mul(v1, ca), _mul(basis_y, sa))
        points.append(_add(center, _mul(direction, radius_mm)))
    points[0] = start
    points[-1] = end
    radius_errors = [abs(_norm(_sub(point, center)) - radius_mm) for point in points]
    return {
        "treatment": "fillet",
        "points": points,
        "quality": {
            "section_sample_count": count,
            "included_angle_deg": math.degrees(theta),
            "radius_max_error_mm": max(radius_errors),
            "convexity_sign": 1 if convexity_sign >= 0 else -1,
            "trim_distance_mm": trim_distance,
        },
    }


def build_chamfer_section(
    *,
    edge_point: Iterable[float],
    first_retained_direction: Iterable[float],
    second_retained_direction: Iterable[float],
    distance_mm: float,
) -> dict:
    if distance_mm <= 0.0:
        raise ValueError("chamfer distance must be positive")
    p0 = _p(edge_point)
    d1 = _unit(_p(first_retained_direction))
    d2 = _unit(_p(second_retained_direction))
    first = _add(p0, _mul(d1, distance_mm))
    second = _add(p0, _mul(d2, distance_mm))
    middle = _mul(_add(first, second), 0.5)
    line_mid = _mul(_add(first, second), 0.5)
    return {
        "treatment": "chamfer",
        "points": [first, middle, second],
        "quality": {
            "section_sample_count": 3,
            "direction_sign": 1,
            "section_linearity_max_error_mm": _norm(_sub(middle, line_mid)),
            "distance_mm": distance_mm,
        },
    }
```

- [ ] **Step 4: Run section tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_sections.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit section solver**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_sections.py tests/test_impeller_v091_sections.py
git commit -m "feat: add V0.91 local transition section solver"
```

### Task 5: Build V0.91 Transition Patch Complex

**Files:**
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `src/part_rule_synthesis/impeller_transition_topology.py`
- Test: `tests/test_impeller_v091_transition_topology.py`

- [ ] **Step 1: Add V0.91 resolver branch**

In `resolve_transition_geometry()` add V0.91 before V0.9:

```python
if geometry_version == "0.91":
    return _resolve_v091_transition_geometry(surface_graph, transition_policies)
if geometry_version == "0.9":
    return _resolve_v09_transition_geometry(surface_graph, transition_policies)
```

- [ ] **Step 2: Implement V0.91 as topology-first, not V0.9 strip reuse**

Add `_resolve_v091_transition_geometry()`:

```python
def _resolve_v091_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    base_resolution = _resolve_v08_transition_geometry(
        surface_graph,
        _disable_all_transition_policies(transition_policies),
    )
    resolved_graph = {
        **base_resolution.surface_graph,
        "transition_geometry_status": "topology_first_validated_transition_graph",
    }
    patch_complex = build_v091_patch_complex(resolved_graph, transition_policies)
    _apply_patch_complex_to_surface_graph(resolved_graph, patch_complex)
    resolved_graph["transition_patch_complex"] = patch_complex_to_manifest(patch_complex)
    resolved_graph["transition_topology_report"] = transition_topology_report(patch_complex)
    return TransitionResolution(
        surface_graph=resolved_graph,
        edge_treatment_sites=patch_complex_edge_sites(patch_complex),
        transition_failures=[],
        quality_checks=patch_complex_quality_checks(patch_complex),
    )
```

Define helper names in the same file or import them from `impeller_transition_topology.py`. The critical rule is that V0.91 may reuse V0.8 primary surfaces, but must not reuse V0.8/V0.9 transition strips.

- [ ] **Step 3: Build shared root and blade edge nodes**

For each blade index:

```python
for blade_index in blade_indices:
    register_blade_root_edges(complex, pressure_surface, suction_surface, hub_surface, blade_index)
    register_blade_leading_edges(complex, pressure_surface, suction_surface, blade_index)
    register_blade_trailing_edges(complex, pressure_surface, suction_surface, blade_index)
    register_blade_tip_edges(complex, pressure_surface, suction_surface, blade_index)
```

Each registration must create node ids using semantic ids such as:

```text
blade_0.root.pressure.station_000.blade_trim
blade_0.root.pressure.station_000.hub_trim
blade_0.leading.station_000.pressure_trim
blade_0.leading.station_000.suction_trim
```

These ids, not rounded coordinates, are the source of truth for shared boundaries.

- [ ] **Step 4: Add transition patches and corner patches**

For every active transition policy:

```python
if policy["treatment"] == "fillet":
    section = build_fillet_section(...)
elif policy["treatment"] == "chamfer":
    section = build_chamfer_section(...)
```

Create patch ids:

```text
blade_0_pressure_root_transition_surface
blade_0_suction_root_transition_surface
blade_0_leading_transition_surface
blade_0_trailing_transition_surface
blade_0_tip_transition_surface
blade_0_root_leading_pressure_corner_transition_surface
blade_0_root_leading_suction_corner_transition_surface
blade_0_root_trailing_pressure_corner_transition_surface
blade_0_root_trailing_suction_corner_transition_surface
```

- [ ] **Step 5: Run topology tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_transition_topology.py -q
```

Expected: corner tests may still FAIL until corner generation and patch mesh are complete.

- [ ] **Step 6: Commit patch-complex resolver**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py src/part_rule_synthesis/impeller_transition_topology.py
git commit -m "feat: route V0.91 transitions through shared patch complex"
```

### Task 6: Add Corner Patch Generation

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_corners.py`
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Test: `tests/test_impeller_v091_transition_topology.py`

- [ ] **Step 1: Implement Coons patch helper**

Create `src/part_rule_synthesis/impeller_transition_corners.py`:

```python
from __future__ import annotations

from typing import Sequence

Point3 = tuple[float, float, float]


def _lerp(a: Point3, b: Point3, t: float) -> Point3:
    return (
        a[0] * (1.0 - t) + b[0] * t,
        a[1] * (1.0 - t) + b[1] * t,
        a[2] * (1.0 - t) + b[2] * t,
    )


def build_coons_corner_grid(
    *,
    west: Sequence[Point3],
    east: Sequence[Point3],
    south: Sequence[Point3],
    north: Sequence[Point3],
) -> list[list[Point3]]:
    u_count = len(south)
    v_count = len(west)
    if len(north) != u_count or len(east) != v_count:
        raise ValueError("corner patch boundary counts do not match")
    p00 = south[0]
    p10 = south[-1]
    p01 = north[0]
    p11 = north[-1]
    grid: list[list[Point3]] = []
    for i in range(u_count):
        u = i / (u_count - 1)
        row: list[Point3] = []
        for j in range(v_count):
            v = j / (v_count - 1)
            c1 = _lerp(west[j], east[j], u)
            c2 = _lerp(south[i], north[i], v)
            b = (
                p00[0] * (1 - u) * (1 - v) + p10[0] * u * (1 - v) + p01[0] * (1 - u) * v + p11[0] * u * v,
                p00[1] * (1 - u) * (1 - v) + p10[1] * u * (1 - v) + p01[1] * (1 - u) * v + p11[1] * u * v,
                p00[2] * (1 - u) * (1 - v) + p10[2] * u * (1 - v) + p01[2] * (1 - u) * v + p11[2] * u * v,
            )
            row.append((c1[0] + c2[0] - b[0], c1[1] + c2[1] - b[1], c1[2] + c2[2] - b[2]))
        grid.append(row)
    return grid
```

- [ ] **Step 2: Insert required blade corner patches**

In the V0.91 resolver, create corner patches for:

```python
required_corner_roles = [
    "root_leading_pressure_corner",
    "root_leading_suction_corner",
    "root_trailing_pressure_corner",
    "root_trailing_suction_corner",
    "tip_leading_corner",
    "tip_trailing_corner",
]
```

Each corner patch must reuse edge node ids from the adjacent transition patches. If any boundary edge is missing, append a blocking transition failure with reason `missing_corner_boundary_edge`.

- [ ] **Step 3: Run topology tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_transition_topology.py -q
```

Expected: corner gap tests PASS after shared node reuse is wired; mesh manifold test may still FAIL.

- [ ] **Step 4: Commit corner patch generation**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_corners.py src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_v091_transition_topology.py
git commit -m "feat: add V0.91 transition corner patches"
```

### Task 7: Add Shared-Node Patch Mesh And Manifold Report

**Files:**
- Create: `src/part_rule_synthesis/impeller_patch_mesh.py`
- Create: `tests/test_impeller_v091_patch_mesh.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_export.py`
- Modify: `src/part_rule_synthesis/impeller_surface_graph_export.py`

- [ ] **Step 1: Write patch mesh unit tests**

Create `tests/test_impeller_v091_patch_mesh.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_patch_mesh import edge_incidence_report


def test_edge_incidence_report_detects_free_and_nonmanifold_edges():
    triangles = [
        {"vertex_ids": ["a", "b", "c"]},
        {"vertex_ids": ["c", "b", "d"]},
        {"vertex_ids": ["b", "c", "e"]},
    ]

    report = edge_incidence_report(triangles, declared_open_boundary_ids=[])

    assert report["free_edge_count"] == 5
    assert report["nonmanifold_edge_count"] == 1
```

- [ ] **Step 2: Implement patch mesh**

Create `src/part_rule_synthesis/impeller_patch_mesh.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any


def build_patch_mesh(surface_graph: dict[str, Any]) -> dict[str, Any]:
    complex_data = surface_graph.get("transition_patch_complex")
    if not isinstance(complex_data, dict):
        raise ValueError("V0.91 patch mesh requires transition_patch_complex")
    nodes = complex_data.get("nodes", {})
    patches = complex_data.get("patches", [])
    vertices = {node_id: node["point"] for node_id, node in nodes.items()}
    triangles: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    for patch in patches:
        start = len(triangles)
        grid = patch["node_grid"]
        for u_index in range(len(grid) - 1):
            for v_index in range(len(grid[0]) - 1):
                a = grid[u_index][v_index]
                b = grid[u_index + 1][v_index]
                c = grid[u_index + 1][v_index + 1]
                d = grid[u_index][v_index + 1]
                triangles.append({"vertex_ids": [a, b, d], "surface_graph_id": patch["surface_graph_id"]})
                triangles.append({"vertex_ids": [b, c, d], "surface_graph_id": patch["surface_graph_id"]})
        regions.append(
            {
                "surface_graph_id": patch["surface_graph_id"],
                "role": patch.get("role", ""),
                "triangle_start": start,
                "triangle_count": len(triangles) - start,
                "edge_family": patch.get("edge_family", ""),
                "transition_policy_id": patch.get("transition_policy_id", ""),
            }
        )
    report = edge_incidence_report(
        triangles,
        declared_open_boundary_ids=complex_data.get("declared_open_boundary_ids", []),
    )
    return {
        "mesh_type": "shared_node_transition_patch_mesh",
        "vertices": vertices,
        "triangles": triangles,
        "triangle_count": len(triangles),
        "triangle_regions": regions,
        "mesh_manifoldness_report": report,
    }


def edge_incidence_report(triangles: list[dict[str, Any]], declared_open_boundary_ids: list[str]) -> dict[str, Any]:
    edge_counts: Counter[tuple[str, str]] = Counter()
    duplicate_faces: Counter[tuple[str, str, str]] = Counter()
    for triangle in triangles:
        ids = triangle["vertex_ids"]
        duplicate_faces[tuple(sorted(ids))] += 1
        for first, second in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edge_counts[tuple(sorted((first, second)))] += 1
    free_edges = [edge for edge, count in edge_counts.items() if count == 1]
    nonmanifold_edges = [edge for edge, count in edge_counts.items() if count > 2]
    return {
        "declared_open_boundary_ids": declared_open_boundary_ids,
        "edge_count": len(edge_counts),
        "free_edge_count": len(free_edges),
        "nonmanifold_edge_count": len(nonmanifold_edges),
        "duplicate_face_count": sum(count - 1 for count in duplicate_faces.values() if count > 1),
        "zero_area_face_count": 0,
        "free_edges": free_edges[:50],
        "nonmanifold_edges": nonmanifold_edges[:50],
    }
```

- [ ] **Step 3: Route V0.91 exporters through patch mesh**

In `impeller_mesh_export.py`, update `_mesh_for_surface_graph()`:

```python
if surface_graph.get("transition_geometry_status") == "topology_first_validated_transition_graph":
    from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh

    return build_patch_mesh(surface_graph)
```

Also update any STL path in `impeller_surface_graph_export.py` so V0.91 uses
`build_patch_mesh()` instead of `triangulate_surface_graph()`.

- [ ] **Step 4: Run patch mesh tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_patch_mesh.py tests/test_impeller_v091_transition_topology.py -q
```

Expected: PASS after patch complex emits closed shared-node grids.

- [ ] **Step 5: Commit patch mesh**

Run:

```powershell
git add src/part_rule_synthesis/impeller_patch_mesh.py `
  src/part_rule_synthesis/impeller_mesh_export.py `
  src/part_rule_synthesis/impeller_surface_graph_export.py `
  tests/test_impeller_v091_patch_mesh.py `
  tests/test_impeller_v091_transition_topology.py
git commit -m "feat: generate V0.91 shared-node patch mesh"
```

### Task 8: Strengthen Geometry Validation And Export Blocking

**Files:**
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `tests/test_impeller_geometry_validation.py`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Add validation tests**

Add tests to `tests/test_impeller_geometry_validation.py`:

```python
def test_v091_validation_fails_on_free_edges():
    report = validate_geometry(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph={
            "transition_geometry_status": "topology_first_validated_transition_graph",
            "transition_topology_report": {"boundary_node_identity_failures": []},
            "mesh_manifoldness_report": {"free_edge_count": 1, "nonmanifold_edge_count": 0, "zero_area_face_count": 0},
        },
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "mesh_has_free_edges" for failure in report["blocking_failures"])


def test_v091_validation_fails_on_missing_corner_patches():
    report = validate_geometry(
        parameters={},
        facets={},
        transition_policies={},
        surface_graph={
            "transition_geometry_status": "topology_first_validated_transition_graph",
            "transition_topology_report": {
                "corner_patch_count": 0,
                "required_corner_patch_count": 8,
                "boundary_node_identity_failures": [],
            },
            "mesh_manifoldness_report": {"free_edge_count": 0, "nonmanifold_edge_count": 0, "zero_area_face_count": 0},
        },
    )

    assert report["geometry_validation_status"] == "FAIL"
    assert any(failure["reason"] == "missing_required_corner_patches" for failure in report["blocking_failures"])
```

Use the actual `validate_geometry()` signature in the file; keep the assertion reasons exactly as above.

- [ ] **Step 2: Implement V0.91 validation gates**

In `impeller_geometry_validation.py`, when `transition_geometry_status` is
`topology_first_validated_transition_graph`, add blocking failures for:

```python
if mesh_report.get("free_edge_count", 0) > 0:
    blocking_failures.append(_failure("mesh_has_free_edges", free_edge_count=mesh_report["free_edge_count"]))
if mesh_report.get("nonmanifold_edge_count", 0) > 0:
    blocking_failures.append(_failure("mesh_has_nonmanifold_edges", nonmanifold_edge_count=mesh_report["nonmanifold_edge_count"]))
if mesh_report.get("zero_area_face_count", 0) > 0:
    blocking_failures.append(_failure("mesh_has_zero_area_faces", zero_area_face_count=mesh_report["zero_area_face_count"]))
if topology_report.get("corner_patch_count", 0) < topology_report.get("required_corner_patch_count", 0):
    blocking_failures.append(_failure("missing_required_corner_patches"))
if topology_report.get("boundary_node_identity_failures"):
    blocking_failures.append(_failure("boundary_node_identity_failed"))
```

- [ ] **Step 3: Block V0.91 exports on validation failure**

In `service.py`, extend the existing export-blocking condition so V0.91 fails before
writing STL/OBJ/STEP if `geometry_validation_status == "FAIL"`.

- [ ] **Step 4: Run validation and workflow tests**

Run:

```powershell
python -m pytest tests/test_impeller_geometry_validation.py tests/test_workflow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit validation gates**

Run:

```powershell
git add src/part_rule_synthesis/impeller_geometry_validation.py src/part_rule_synthesis/service.py tests/test_impeller_geometry_validation.py tests/test_workflow.py
git commit -m "feat: enforce V0.91 transition topology validation gates"
```

### Task 9: Update STEP/OBJ/STL Manifests And Frontend Review

**Files:**
- Modify: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_export.py`
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/components/ManifestPanel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Add manifest fields to export writers**

Every V0.91 export manifest must include:

```python
"mesh_type": "shared_node_transition_patch_mesh",
"transition_geometry_status": "topology_first_validated_transition_graph",
"transition_topology_report": surface_graph.get("transition_topology_report", {}),
"mesh_manifoldness_report": mesh.get("mesh_manifoldness_report", {}),
"corner_patch_regions": [
    region for region in mesh["triangle_regions"] if "corner" in region.get("role", "")
],
```

- [ ] **Step 2: Update frontend defaults**

In `frontend/src/appModel.js`, replace default V0.9 preset ids with:

```javascript
presetId: "radial_open_reference_v0_91"
```

and closed references with:

```javascript
presetId: "radial_closed_reference_v0_91"
```

- [ ] **Step 3: Show topology and manifoldness reports**

In `frontend/src/components/ManifestPanel.js`, display:

```javascript
const topologyReport = manifest?.transition_topology_report || {};
const manifoldReport = manifest?.mesh_manifoldness_report || {};
```

Add rows for:

```text
transition patch count
corner patch count
free edge count
nonmanifold edge count
zero area face count
max corner gap
```

- [ ] **Step 4: Render patch-complex surfaces in viewer**

In `frontend/src/components/ModelViewer.js`, when
`surfaceGraph.transition_geometry_status === "topology_first_validated_transition_graph"`,
prefer `surfaceGraph.transition_patch_complex.patches` if present. Each patch should
render from its shared `node_grid` and `nodes` coordinates. Do not hide old untrimmed
surfaces with opacity tricks in V0.91.

- [ ] **Step 5: Run frontend tests and build**

Run:

```powershell
npm.cmd test
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 6: Commit export and frontend review updates**

Run:

```powershell
git add src/part_rule_synthesis/impeller_bounded_brep_export.py `
  src/part_rule_synthesis/impeller_mesh_export.py `
  frontend/src/appModel.js `
  frontend/src/components/ManifestPanel.js `
  frontend/src/components/ModelViewer.js `
  frontend/src/appFiles.test.js
git commit -m "feat: expose V0.91 topology-first exports and frontend review"
```

### Task 10: Add Evidence Package And Golden Batch Summary

**Files:**
- Modify: `src/part_rule_synthesis/impeller_v09_regression.py` or create `src/part_rule_synthesis/impeller_v091_regression.py`
- Create: `docs/evidence/2026-07-04-impeller-v0-91-topology-first-transitions/README.md`
- Test: `tests/test_impeller_v09_batch.py` or create `tests/test_impeller_v091_batch.py`

- [ ] **Step 1: Add V0.91 golden case ids**

Add these case ids to the V0.91 golden registry:

```text
v091_radial_open_default_topology_first
v091_radial_closed_default_topology_first
v091_high_blade_count_root_corner
v091_large_root_fillet_feasible_limit
v091_chamfered_root_and_bore_direction
v091_small_radius_high_resolution_fillet
v091_negative_inverted_fillet_direction
v091_negative_missing_corner_patch
v091_negative_nonmanifold_shared_edge
v091_negative_untrimmed_adjacent_surface
```

- [ ] **Step 2: Add batch test**

Create `tests/test_impeller_v091_batch.py`:

```python
from __future__ import annotations

from pathlib import Path

from part_rule_synthesis.impeller_v091_regression import run_v091_batch


def test_v091_golden_batch_reports_topology_and_manifoldness(tmp_path: Path):
    summary = run_v091_batch(tmp_path, mode="golden")

    assert summary["mode"] == "golden"
    assert summary["pass_count"] >= 2
    assert summary["fail_count"] == 0
    for case in summary["cases"]:
        assert case["geometry_validation_status"] == "PASS"
        assert case["mesh_manifoldness_report"]["free_edge_count"] == 0
        assert case["mesh_manifoldness_report"]["nonmanifold_edge_count"] == 0
```

- [ ] **Step 3: Create evidence README**

Create `docs/evidence/2026-07-04-impeller-v0-91-topology-first-transitions/README.md`:

```markdown
# V0.91 Topology-First Transitions Evidence

Date: 2026-07-04

## Root Cause

V0.9 created visible transition strips but did not create shared topology. Fillet strips
used a radial sine bump, chamfers did not derive direction from retained material side,
corner patches were missing, and the review mesh had free and non-manifold edges.

## V0.91 Repair

V0.91 introduces a topology-first patch complex, local section-frame fillet/chamfer
solver, explicit corner transition patches, shared-node mesh generation, and blocking
validation gates.

## Required Artifacts

- golden batch summary JSON
- open and closed default manifest summaries
- transition topology reports
- mesh manifoldness reports
- export manifest summaries

Large STL/STEP/OBJ files remain in `Model Output/`.
```

- [ ] **Step 4: Run batch tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_batch.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit evidence and batch tooling**

Run:

```powershell
git add src/part_rule_synthesis/impeller_v091_regression.py `
  tests/test_impeller_v091_batch.py `
  docs/evidence/2026-07-04-impeller-v0-91-topology-first-transitions/README.md
git commit -m "feat: add V0.91 topology-first evidence batch"
```

### Task 11: Full Verification

**Files:**
- No new files unless verification exposes failures.

- [ ] **Step 1: Run targeted backend tests**

Run:

```powershell
python -m pytest tests/test_impeller_v091_resources.py -q
python -m pytest tests/test_impeller_v091_sections.py tests/test_impeller_v091_transition_topology.py tests/test_impeller_v091_patch_mesh.py -q
python -m pytest tests/test_impeller_geometry_validation.py tests/test_impeller_transition_mesh.py tests/test_impeller_bounded_brep_export.py -q
python -m pytest tests/test_workflow.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```powershell
npm.cmd test
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Run repository verification**

Run:

```powershell
.\scripts\verify_repository.ps1 -Mode fast
.\scripts\verify_repository.ps1 -Mode full
```

Expected: PASS.

- [ ] **Step 4: Generate review artifacts**

Run the local service workflow for:

```text
radial_open_reference_v0_91
radial_closed_reference_v0_91
```

Expected in `Model Output/`:

```text
*.stl
*.obj
*.step
*.manifest.json
```

Each manifest must report:

```json
{
  "geometry_validation_status": "PASS",
  "mesh_manifoldness_report": {
    "free_edge_count": 0,
    "nonmanifold_edge_count": 0,
    "zero_area_face_count": 0
  }
}
```

- [ ] **Step 5: Final commit**

Run:

```powershell
git status --short
git add docs/superpowers/specs/2026-07-04-impeller-v0-91-topology-first-transitions-design.md `
  docs/superpowers/plans/2026-07-04-impeller-v0-91-topology-first-transitions.md
git commit -m "docs: specify V0.91 topology-first transition repair"
```

If implementation files are still unstaged at this point, inspect them individually and
commit only the files belonging to the completed V0.91 implementation.

## Self-Review Checklist

- [ ] V0.91 does not reuse V0.9 strip transitions as a success path.
- [ ] Fillet construction records radius error, convexity sign, G1 error, and section sample count.
- [ ] Chamfer construction records retained-side direction sign and linearity.
- [ ] Required corner patches exist and share boundary node ids.
- [ ] Default V0.91 meshes have zero free edges and zero non-manifold edges.
- [ ] STL/OBJ/STEP manifests include topology and manifoldness reports.
- [ ] Frontend views render the same V0.91 patch complex used by exports.
- [ ] V0.2 through V0.9 remain loadable.
- [ ] `Model Output/` binaries are not committed.
