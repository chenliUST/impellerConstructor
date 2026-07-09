# Impeller V1.0 Topology-First Constructor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.0 as a topology-first closed multi-face impeller constructor where blade edge, tip, root, hub, bore, and bevel faces are native named topology faces rather than post-generated transition patches.

**Architecture:** Build V1.0 from the clean V0.91 baseline in a new worktree. Add a new versioned DSL bundle and a new runtime path, then introduce small backend modules for closed blade section profiles, native blade face generation, revolved hub profile segments, shared-edge topology, and V1.0 validation. Keep V0.9-V0.91 behavior intact and do not port V0.97 transition repair code.

**Tech Stack:** Python 3.12, existing sampled NURBS-style surface graph, pytest, FastAPI, React/Three.js frontend model tests.

---

## Baseline State

Worktree:

```text
C:/Users/CHEN Li/Documents/TurboJetCase/impellerConstructor/.worktrees/impeller-v1.0-topology-first
```

Branch:

```text
impeller-v1.0-topology-first-constructor
```

Baseline checks already run:

```text
frontend npm.cmd test: 85 passed
backend core baseline: 45 passed
full python pytest: timed out after 184 seconds, no code failure observed before timeout
```

Use the focused backend baseline during inner-loop work:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_kernel.py tests/test_impeller_geometry_validation.py tests/test_impeller_v09_workflow.py -q
```

Use full or larger suites only at milestone gates.

---

## Task 1: Bootstrap V1.0 Versioned Resources

**Files:**
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/`
- Test: `tests/test_impeller_v10_resources.py`

- [x] **Step 1: Write failing resource tests**

Create `tests/test_impeller_v10_resources.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import (
    compile_impeller_runtime_preset,
    impeller_json_preset_ids,
)


def test_v10_open_and_closed_presets_are_registered():
    preset_ids = impeller_json_preset_ids()

    assert "radial_open_reference_v1_0" in preset_ids
    assert "radial_closed_reference_v1_0" in preset_ids


def test_v10_runtime_reports_topology_first_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")

    assert runtime["dsl_version"] == "1.0"
    assert runtime["geometry_version"] == "1.0"
    assert runtime["transition_geometry_status"] == "topology_first_closed_nurbs_impeller_surface_graph"
    assert runtime["mesh_strategy"] == "topology_first_shared_edge_quad_patch_mesh"
    assert runtime["kernel_capability_matrix_id"] == "impeller_v1_0_kernel_capabilities"
    assert runtime["golden_case_registry_id"] == "impeller_v1_0_golden_cases"
```

- [x] **Step 2: Run failing test**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_resources.py -q
```

Expected: `unknown impeller preset: radial_open_reference_v1_0`.

- [x] **Step 3: Copy V0.91 bundle to V1.0**

Use PowerShell copy:

```powershell
Copy-Item -Recurse `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91 `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0
```

Then update JSON ids inside the copied bundle:

```text
dsl_version: "1.0"
constructor ids: open_impeller_v1_0, closed_impeller_v1_0
preset ids: radial_open_reference_v1_0, radial_closed_reference_v1_0
geometry_version: "1.0"
transition_geometry_status: "topology_first_closed_nurbs_impeller_surface_graph"
mesh_strategy: "topology_first_shared_edge_quad_patch_mesh"
```

- [x] **Step 4: Register V1.0 in runtime compiler**

Modify `IMPELLER_DSL_VERSIONS`:

```python
IMPELLER_DSL_VERSIONS = ("v0_2", "v0_3", "v0_4", "v0_5", "v0_6", "v0_7", "v0_8", "v0_9", "v0_91", "v1_0")
```

Add runtime handling:

```python
if dsl_version == "1.0":
    runtime["dsl_version"] = "1.0"
    runtime["geometry_version"] = preset.get("geometry_version", "1.0")
    runtime["transition_geometry_status"] = preset.get(
        "transition_geometry_status",
        "topology_first_closed_nurbs_impeller_surface_graph",
    )
    runtime["mesh_strategy"] = export_contract.get("mesh_strategy", "topology_first_shared_edge_quad_patch_mesh")
    runtime["kernel_capability_matrix_id"] = "impeller_v1_0_kernel_capabilities"
    runtime["golden_case_registry_id"] = "impeller_v1_0_golden_cases"
```

- [x] **Step 5: Run resource tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_resources.py -q
```

Expected: tests pass.

---

## Task 2: Closed Blade Section Profile Builder

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_closed_profile.py`
- Test: `tests/test_impeller_v10_closed_profile.py`

- [x] **Step 1: Write failing profile tests**

Create `tests/test_impeller_v10_closed_profile.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_closed_profile import build_closed_blade_section_profile


def test_v10_closed_profile_has_named_pressure_suction_and_edge_cap_curves():
    profile = build_closed_blade_section_profile(
        station_index=0,
        station_count=5,
        center=(300.0, 0.0, 100.0),
        tangent=(0.0, 1.0, 0.0),
        radial=(1.0, 0.0, 0.0),
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
        sample_count=17,
    )

    assert profile["closed_profile_status"] == "PASS"
    assert set(profile["curves"]) == {
        "pressure_side_curve",
        "leading_edge_cap_curve",
        "suction_side_curve",
        "trailing_edge_cap_curve",
    }
    assert profile["max_closure_gap_mm"] <= 1.0e-9
    assert len(profile["closed_loop"]) > 20


def test_v10_closed_profile_rejects_non_positive_thickness():
    profile = build_closed_blade_section_profile(
        station_index=0,
        station_count=5,
        center=(300.0, 0.0, 100.0),
        tangent=(0.0, 1.0, 0.0),
        radial=(1.0, 0.0, 0.0),
        thickness_mm=0.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
        sample_count=17,
    )

    assert profile["closed_profile_status"] == "FAIL"
    assert profile["failure_reason"] == "v1_0_closed_blade_profile_failed"
```

- [x] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_closed_profile.py -q
```

Expected: import failure.

- [x] **Step 3: Implement minimal closed profile builder**

Create `impeller_v10_closed_profile.py` with:

```python
def build_closed_blade_section_profile(
    *,
    station_index: int,
    station_count: int,
    center: Point3,
    tangent: Point3,
    radial: Point3,
    thickness_mm: float,
    leading_radius_mm: float,
    trailing_radius_mm: float,
    sample_count: int = 17,
) -> dict[str, Any]:
    ...
```

Implementation rules:

- Return named curve arrays.
- Use pressure and suction offsets along `tangent`.
- Use leading/trailing cap arcs in a local 2D plane.
- Return a `closed_loop` with first and last point identical.
- Reject non-positive thickness and invalid sample count with structured failure dictionaries.

- [x] **Step 4: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_closed_profile.py -q
```

Expected: tests pass.

---

## Task 3: Native Blade Face Network

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_blade_faces.py`
- Test: `tests/test_impeller_v10_blade_faces.py`

- [x] **Step 1: Write failing blade face tests**

Create `tests/test_impeller_v10_blade_faces.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network


def test_v10_blade_face_network_has_required_named_faces():
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=7,
        sample_count=13,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )

    face_ids = {face["id"] for face in network["faces"]}

    assert network["blade_face_network_status"] == "PASS"
    assert {
        "blade_0_pressure_surface",
        "blade_0_suction_surface",
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_tip_surface",
        "blade_0_root_annular_surface",
    }.issubset(face_ids)
    assert network["closed_profile_count"] == 7


def test_v10_blade_face_network_has_no_transition_geometry_fields():
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=5,
        sample_count=9,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )

    assert all("transition_geometry" not in face for face in network["faces"])
```

- [x] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_blade_faces.py -q
```

Expected: import failure.

- [x] **Step 3: Implement blade face network**

Create `impeller_v10_blade_faces.py`.

Build a minimal review-grade face network:

- Generate station profiles with `build_closed_blade_section_profile`.
- Build UV grids by collecting corresponding named curve samples across stations.
- Emit required six face dictionaries with:
  - `id`
  - `kind: "native_topology_face"`
  - `face_family`
  - `role`
  - `uv_grid`
  - `control_net`
  - `degree_u`
  - `degree_v`
  - `boundary_roles`
  - `continuity_targets`

- [x] **Step 4: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_blade_faces.py -q
```

Expected: tests pass.

---

## Task 4: Native Hub Profile And Bevel Faces

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_hub_profile.py`
- Test: `tests/test_impeller_v10_hub_profile.py`

- [x] **Step 1: Write failing hub profile tests**

Create `tests/test_impeller_v10_hub_profile.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_hub_profile import build_v10_hub_revolve_faces


def test_v10_hub_profile_outputs_named_bevel_faces():
    hub = build_v10_hub_revolve_faces(
        outer_radius_mm=580.0,
        bore_radius_mm=40.0,
        height_mm=420.0,
        bottom_bevel_mm=24.0,
        bore_top_bevel_mm=18.0,
        bore_bottom_bevel_mm=18.0,
        theta_samples=17,
    )

    face_ids = {face["id"] for face in hub["faces"]}

    assert hub["hub_profile_status"] == "PASS"
    assert {
        "hub_main_revolve_surface",
        "hub_top_face",
        "hub_bottom_face",
        "hub_bottom_outer_bevel_surface",
        "mounting_bore_cylinder_surface",
        "mounting_bore_top_bevel_surface",
        "mounting_bore_bottom_bevel_surface",
    }.issubset(face_ids)


def test_v10_hub_profile_rejects_bevel_larger_than_radius_domain():
    hub = build_v10_hub_revolve_faces(
        outer_radius_mm=50.0,
        bore_radius_mm=40.0,
        height_mm=420.0,
        bottom_bevel_mm=24.0,
        bore_top_bevel_mm=18.0,
        bore_bottom_bevel_mm=18.0,
        theta_samples=17,
    )

    assert hub["hub_profile_status"] == "FAIL"
    assert hub["failure_reason"] == "v1_0_hub_profile_segment_failed"
```

- [x] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_hub_profile.py -q
```

Expected: import failure.

- [x] **Step 3: Implement hub revolve face builder**

Create `impeller_v10_hub_profile.py`.

Implementation rules:

- Build named R-Z profile segments.
- Revolve each profile segment into a sampled UV grid.
- Mark bevel faces with:

```python
"face_family": "hub_bevel"
"native_bevel_face": True
```

- Do not use transition-surface fields.

- [x] **Step 4: Run hub tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_hub_profile.py -q
```

Expected: tests pass.

---

## Task 5: Shared-Edge Topology Graph

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_topology_graph.py`
- Test: `tests/test_impeller_v10_topology_graph.py`

- [x] **Step 1: Write failing topology tests**

Create `tests/test_impeller_v10_topology_graph.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph


def test_v10_topology_graph_registers_shared_edges_from_constructor_faces():
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=5,
        sample_count=9,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )
    topology = build_v10_topology_graph(network["faces"])

    assert topology["topology_status"] == "PASS"
    assert topology["shared_edge_count"] >= 8
    assert topology["synthetic_shared_edge_count"] == 0
    assert topology["max_shared_edge_gap_mm"] <= 1.0e-9
```

- [x] **Step 2: Run failing test**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_topology_graph.py -q
```

Expected: import failure.

- [x] **Step 3: Implement topology graph builder**

Create `impeller_v10_topology_graph.py`.

Implementation rules:

- Read face `boundary_roles`.
- Register shared edges by constructor-declared boundary role pairs.
- Use exact samples from generated grids.
- Return `synthetic_shared_edge_count = 0`.
- Compute `max_shared_edge_gap_mm`.

- [x] **Step 4: Run topology tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_topology_graph.py -q
```

Expected: tests pass.

---

## Task 6: V1.0 Validation Gates

**Files:**
- Modify: `src/part_rule_synthesis/impeller_geometry_validation.py`
- Test: `tests/test_impeller_v10_validation.py`

- [x] **Step 1: Write failing validation tests**

Create `tests/test_impeller_v10_validation.py`:

```python
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_geometry_validation import build_geometry_validation_report
from part_rule_synthesis.impeller_v10_blade_faces import build_v10_blade_face_network
from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph


def _surface_graph() -> dict:
    network = build_v10_blade_face_network(
        blade_index=0,
        station_count=5,
        sample_count=9,
        root_radius_mm=180.0,
        tip_radius_mm=560.0,
        root_z_mm=0.0,
        tip_z_mm=420.0,
        thickness_mm=80.0,
        leading_radius_mm=30.0,
        trailing_radius_mm=22.0,
    )
    topology = build_v10_topology_graph(network["faces"])
    return {
        "transition_geometry_status": "topology_first_closed_nurbs_impeller_surface_graph",
        "surfaces": network["faces"],
        "topology_graph": topology,
    }


def test_v10_validation_passes_native_named_faces_and_shared_edges():
    report = build_geometry_validation_report(surface_graph=_surface_graph())

    assert report["geometry_validation_status"] == "PASS"


def test_v10_validation_rejects_missing_named_blade_face():
    graph = _surface_graph()
    graph["surfaces"] = [surface for surface in graph["surfaces"] if surface["id"] != "blade_0_tip_surface"]

    report = build_geometry_validation_report(surface_graph=graph)

    assert report["geometry_validation_status"] == "FAIL"
    assert any(f["reason"] == "v1_0_missing_named_blade_face" for f in report["blocking_failures"])
```

- [x] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_validation.py -q
```

Expected: validator does not yet know V1.0.

- [x] **Step 3: Add V1.0 validator branch**

In `impeller_geometry_validation.py`:

- Add constant:

```python
V10_TRANSITION_GEOMETRY_STATUS = "topology_first_closed_nurbs_impeller_surface_graph"
```

- Add checks for:
  - required blade faces;
  - no V0 transition geometry fields;
  - topology graph present;
  - synthetic shared edge count zero;
  - max shared edge gap under tolerance;
  - face foldover status.

Blocking reasons must match the spec.

- [x] **Step 4: Run validation tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_validation.py -q
```

Expected: tests pass.

---

## Task 7: Runtime Surface Graph Integration

**Files:**
- Create: `src/part_rule_synthesis/impeller_v10_surface_graph.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_v10_surface_graph.py`

- [x] **Step 1: Write failing integration test**

Create `tests/test_impeller_v10_surface_graph.py`:

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


def test_v10_open_runtime_generates_topology_first_surface_graph():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    graph = metadata["surface_graph"]
    face_ids = {surface["id"] for surface in graph["surfaces"]}

    assert graph["transition_geometry_status"] == "topology_first_closed_nurbs_impeller_surface_graph"
    assert "blade_0_leading_edge_surface" in face_ids
    assert "hub_bottom_outer_bevel_surface" in face_ids
    assert graph["topology_graph"]["synthetic_shared_edge_count"] == 0
```

- [x] **Step 2: Run failing integration test**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_surface_graph.py -q
```

Expected: V1.0 runtime not integrated.

- [x] **Step 3: Implement V1.0 graph builder**

Create `impeller_v10_surface_graph.py`:

```python
def build_v10_surface_graph(parameters: dict[str, float], facets: dict[str, str]) -> dict[str, Any]:
    ...
```

It should combine:

- `build_v10_hub_revolve_faces`;
- `build_v10_blade_face_network` for each blade;
- `build_v10_topology_graph`.

- [x] **Step 4: Route service metadata to V1.0 graph**

Modify `service.py` where impeller surface graph metadata is built:

```python
if dsl_context and dsl_context.get("geometry_version") == "1.0":
    surface_graph = build_v10_surface_graph(parameters, facets)
```

- [x] **Step 5: Run integration tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_surface_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_resources.py -q
```

Expected: tests pass.

---

## Task 8: Frontend V1.0 Preset And Inspection UI

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/appFiles.test.js`

- [x] **Step 1: Add failing frontend tests**

Modify `frontend/src/appModel.test.js`:

```javascript
test("v1.0 presets expose topology-first constructor studies", () => {
  const presetIds = presets.map((preset) => preset.id);
  assert.ok(presetIds.includes("radial_open_reference_v1_0"));
  assert.ok(presetIds.includes("radial_closed_reference_v1_0"));
});

test("v1.0 presets do not expose legacy edge treatment scalar controls", () => {
  const preset = presets.find((item) => item.id === "radial_open_reference_v1_0");
  const names = parameterSchema(preset).flatMap((group) => group.parameters.map((param) => param.name));
  assert.equal(names.includes("leading_edge_radius_mm"), false);
  assert.equal(names.includes("trailing_edge_radius_mm"), false);
  assert.equal(names.includes("hub_chamfer_radius_mm"), false);
});
```

Modify `frontend/src/appFiles.test.js`:

```javascript
it("viewer recognizes native v1.0 topology faces", () => {
  const viewer = fs.readFileSync(path.join(projectRoot, "src/components/ModelViewer.js"), "utf8");
  assert.match(viewer, /native_topology_face/);
  assert.match(viewer, /face_family/);
  assert.match(viewer, /shared_edge/);
});
```

- [x] **Step 2: Run failing frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: new tests fail.

- [x] **Step 3: Add V1.0 presets and hide legacy controls**

Modify `appModel.js`:

- Add two presets:
  - `radial_open_reference_v1_0`
  - `radial_closed_reference_v1_0`
- Hide legacy edge treatment scalar controls when `preset.id.endsWith("_v1_0")`.

- [x] **Step 4: Add native topology face rendering priority**

Modify `ModelViewer.js`:

- Treat `kind === "native_topology_face"` as visible CAD face.
- Color by `face_family`.
- Add shared edge inspection hooks if `surfaceGraph.topology_graph` exists.

- [x] **Step 5: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all frontend tests pass.

---

## Task 9: Evidence And Documentation Updates

**Files:**
- Modify: `docs/version-history.md`
- Modify: `docs/repository-map.md`
- Modify: `docs/superpowers/specs/2026-07-05-impeller-v1-0-topology-first-constructor-spec.md`
- Modify: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/README.md`
- Create: `docs/evidence/2026-07-05-impeller-v1-0-topology-first/test-transcript-summary.md`

- [x] **Step 1: Add test transcript summary**

Create `test-transcript-summary.md` with sections:

```markdown
# V1.0 Test Transcript Summary

## Baseline

## Resource Tests

## Geometry Unit Tests

## Integration Tests

## Frontend Tests

## HTTP Smoke
```

Record exact commands and pass/fail counts as they are run.

- [x] **Step 2: Update version history**

Add V1.0 entry to `docs/version-history.md`:

```markdown
## V1.0 Topology-First Closed NURBS Impeller Constructor

V1.0 replaces post-generated edge treatments with native named blade, root, hub, bore, and bevel faces. It introduces shared-edge topology identity and whole-face validation.
```

- [x] **Step 3: Run doc grep**

Run:

```powershell
rg -n "V1.0|topology-first|radial_open_reference_v1_0" docs src frontend tests
```

Expected: V1.0 appears in spec, evidence, resources, tests, and frontend model.

---

## Task 10: End-To-End Verification

**Files:**
- No new production files.

- [x] **Step 1: Run V1.0 backend tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_v10_resources.py tests/test_impeller_v10_closed_profile.py tests/test_impeller_v10_blade_faces.py tests/test_impeller_v10_hub_profile.py tests/test_impeller_v10_topology_graph.py tests/test_impeller_v10_validation.py tests/test_impeller_v10_surface_graph.py -q
```

Expected: all pass.

- [x] **Step 2: Run baseline regressions**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_impeller_kernel.py tests/test_impeller_geometry_validation.py tests/test_impeller_v09_workflow.py -q
```

Expected: 45 pass.

- [x] **Step 3: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all pass.

- [x] **Step 4: HTTP smoke open preset**

Run:

```powershell
$env:PYTHONPATH='src'
python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8060
```

In a second shell:

```powershell
$synth = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8060/api/rule-engines/synthesize' -ContentType 'application/json' -Body '{"part_family_id":"impeller","preset_id":"radial_open_reference_v1_0","facets":{}}'
$body = @{parameters=@{}; geometry_stage='full'} | ConvertTo-Json -Depth 10
$run = Invoke-RestMethod -Method Post -Uri ("http://127.0.0.1:8060/api/rule-engines/{0}/instantiate" -f $synth.engine_id) -ContentType 'application/json' -Body $body
$run.manifest.geometry_validation_status
$run.manifest.geometry.surface_graph.transition_geometry_status
```

Expected:

```text
PASS
topology_first_closed_nurbs_impeller_surface_graph
```

- [x] **Step 5: HTTP smoke closed preset**

Repeat Step 4 with:

```text
radial_closed_reference_v1_0
```

Expected: `PASS`.

---

## Notes For Implementers

- Do not port V0.97 edge fillet/chamfer builders into V1.0.
- Do not represent V1.0 native faces as `transition_surface`.
- Do not claim G2 globally. Attach continuity claims to named edges.
- Preserve V0.9-V0.91 behavior and tests.
- Keep evidence logs updated as implementation decisions are made.
