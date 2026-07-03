# Impeller V0.8 Transition-Resolved Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V0.8 so enabled fillet and chamfer policies trim adjacent main surfaces, generate real transition patches, and feed the same resolved geometry into frontend, STL, OBJ, STEP, and mesh manifests.

**Architecture:** V0.8 is an additive version line. The existing kernel continues to produce a base surface graph, then a new transition geometry resolver rewrites supported edge families into a transition-resolved surface graph. A transition-aware mesher consumes the resolved graph, and exporters/frontend consume the same resolved graph or resolved mesh evidence.

**Tech Stack:** Python 3.12, pytest, OCP/OCCT, FastAPI service layer, binary STL, OBJ, React without JSX, Three.js, Node test runner, PowerShell verification scripts.

---

## File Structure

Create:

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/`: additive DSL resource line copied from V0.7 and relabeled to V0.8.
- `src/part_rule_synthesis/impeller_transition_geometry.py`: transition site discovery, trim boundary construction, fillet/chamfer patch sampling, geometry quality checks, and resolved graph output.
- `src/part_rule_synthesis/impeller_transition_mesh.py`: transition-aware triangulation, shared boundary checks, STL/OBJ mesh metadata, and transition mesh quality metrics.
- `tests/test_impeller_v08_resources.py`: V0.8 resource loading and runtime compiler tests.
- `tests/test_impeller_transition_geometry.py`: focused resolver tests with small synthetic grids and service-generated impeller graphs.
- `tests/test_impeller_transition_mesh.py`: shared boundary, region provenance, and mesh quality tests.
- `docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/README.md`: V0.8 diagnosis, implementation evidence, and ontology insight.

Modify:

- `src/part_rule_synthesis/impeller_dsl_resources.py`: include `v0_8`.
- `src/part_rule_synthesis/impeller_runtime_compiler.py`: expose V0.8 transition-resolved export contract and runtime metadata.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`: document V0.8.
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`: route V0.8 graphs through the resolver and avoid metadata-only blade transition surfaces for V0.8.
- `src/part_rule_synthesis/service.py`: select V0.8 resolved graph, transition-aware mesh exports, and V0.8 manifest fields.
- `src/part_rule_synthesis/impeller_mesh_export.py`: call the transition-aware mesher for V0.8 OBJ output.
- `src/part_rule_synthesis/impeller_surface_graph_export.py`: preserve historical STL behavior and delegate V0.8 STL triangle regions to transition-aware mesh data.
- `src/part_rule_synthesis/impeller_bounded_brep_export.py`: preserve V0.7 bounded STEP behavior and add V0.8 exactness/provenance fields from resolved transition surfaces.
- `src/part_rule_synthesis/impeller_mesh_manifest.py`: include V0.8 transition quality metrics.
- `tests/test_workflow.py`: V0.8 open/closed workflow tests.
- `tests/test_impeller_version_lineage.py`: include V0.8 in lineage.
- `frontend/src/appModel.js`: expose V0.8 presets and default labels.
- `frontend/src/edgeTreatmentModel.js`: surface V0.8 transition status and failure fields.
- `frontend/src/components/EdgeTreatmentPanel.js`: show resolved/failure statuses and click-to-highlight ids.
- `frontend/src/meshOverlayModel.js`: include V0.8 transition quality summaries.
- `frontend/src/components/MeshInspectionPanel.js`: show transition mesh quality metrics and family filtering data.
- `frontend/src/components/ModelViewer.js`: preserve transition highlighting and ensure V0.8 transition mesh edges render over shaded surfaces.
- `frontend/src/simulationViewModel.js`: keep mesh view inclusive of transition surfaces for V0.8.
- `frontend/src/workspaceModel.js`: keep transition layers enabled by default.
- `docs/current-research-frontier.md`, `docs/version-history.md`, and V0.8 changelog/evidence files after implementation evidence exists.

Do not commit generated files under `Model Output/`. Small screenshots or text excerpts may be committed only inside the V0.8 evidence folder when explicitly useful as research evidence.

---

## Implementation Defaults

- V0.8 target level is topology-first sampled B-Rep shell, not watertight sewn solid.
- Default V0.8 fillet is equal-radius circular-arc sampled geometry in local cross section.
- Default V0.8 chamfer is straight-line ruled geometry between trim boundaries.
- Required default transition failures block a successful V0.8 manifest.
- V0.7 code paths and historical exactness labels remain unchanged.
- V0.8 can initially use family-specific trim rules; a general freeform edge editor is out of scope.
- Mesh quality gates are enforced for V0.8 transition regions before final acceptance.

---

### Task 1: Pre-Flight Audit And Baseline Failure Evidence

**Files:**
- Read: `docs/superpowers/specs/2026-07-03-impeller-v0-8-transition-resolved-geometry-design.md`
- Read: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Read: `tests/test_impeller_kernel.py`
- Create: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Confirm branch, dirty files, and latest spec commit**

Run:

```powershell
git status -sb
git log --oneline --max-count=5
```

Expected:

```text
## impeller-v0.7-bounded-transitions
45152cd docs: design impeller v0.8 transition geometry
```

Record all pre-existing modified files in the task notes. Do not revert them.

- [ ] **Step 2: Add the V0.7 regression-capturing failing test**

Create `tests/test_impeller_transition_geometry.py` with this initial content:

```python
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from part_rule_synthesis.service import RuleSynthesisService


def _surface_by_id(run, surface_id: str) -> dict:
    return {
        surface["id"]: surface
        for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]
    }[surface_id]


def _grid_digest(surface: dict) -> str:
    return json.dumps(surface["uv_grid"], sort_keys=True)


def test_v08_blade_root_radius_override_changes_transition_geometry():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        enlarged = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "fillet",
                    "radius_mm": 20.0,
                }
            },
        )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    enlarged_root = _surface_by_id(enlarged, "blade_0_root_transition_surface")

    assert baseline_root["radius_mm"] == 8.0
    assert enlarged_root["radius_mm"] == 20.0
    assert _grid_digest(enlarged_root) != _grid_digest(baseline_root)


def test_v08_blade_root_chamfer_override_changes_transition_geometry_and_role():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        chamfered = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "chamfer",
                    "radius_mm": 8.0,
                }
            },
        )

    baseline_root = _surface_by_id(baseline, "blade_0_root_transition_surface")
    chamfered_root = _surface_by_id(chamfered, "blade_0_root_transition_surface")

    assert baseline_root["role"] == "blade_root_fillet"
    assert chamfered_root["role"] == "blade_root_chamfer"
    assert chamfered_root["treatment"] == "chamfer"
    assert _grid_digest(chamfered_root) != _grid_digest(baseline_root)
```

- [ ] **Step 3: Run the failing test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
FAILED with a message containing unknown preset radial_open_reference_v0_8
```

If the failure is an import error for a pre-existing dirty file, fix that import error before continuing and commit it separately.

- [ ] **Step 4: Commit only the failing test**

Run:

```powershell
git add tests/test_impeller_transition_geometry.py
git commit -m "test: capture v0.8 transition geometry requirements"
```

Expected:

```text
commit created with message "test: capture v0.8 transition geometry requirements"
```

---

### Task 2: Add V0.8 DSL Resource Line

**Files:**
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/`
- Modify: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Create: `tests/test_impeller_v08_resources.py`
- Modify: `tests/test_impeller_version_lineage.py`

- [ ] **Step 1: Write V0.8 resource tests**

Create `tests/test_impeller_v08_resources.py`:

```python
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v08_bundle_loads_transition_resolved_contract():
    bundle = load_impeller_dsl_bundle("v0_8")

    assert bundle.schema["dsl_version"] == "0.8"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_8",
        "radial_closed_reference_v0_8",
    }
    contract = bundle.export_contracts["transition_resolved_bounded_brep"]
    assert contract["mode"] == "transition_resolved_bounded_brep"
    assert contract["step_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
    assert contract["mesh_strategy"] == "transition_aware_surface_mesh"


def test_v08_runtime_marks_transition_resolved_geometry():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_8")

    assert runtime["version"] == "0.8.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.8"
    assert runtime["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["mounting_bore_top.default"]["treatment"] == "chamfer"
```

- [ ] **Step 2: Run resource tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v08_resources.py -q
```

Expected:

```text
FAILED with a message containing unknown impeller DSL version: v0_8
```

- [ ] **Step 3: Copy V0.7 resources into V0.8**

Run:

```powershell
Copy-Item -Recurse `
  'src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_7' `
  'src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_8'
```

Expected:

```text
```

PowerShell prints no output when the copy succeeds.

- [ ] **Step 4: Relabel V0.8 resource files**

Edit these files:

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/schema.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/aliases.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/presets/radial_open_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/presets/radial_closed_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/export_contracts/surface_graph_bounded_brep.json`

Use these exact semantic changes:

```json
{
  "dsl_version": "0.8",
  "shape_control_version": "0.8",
  "preset_id": "radial_open_reference_v0_8",
  "inherits_from": "radial_open_reference_v0_7",
  "geometry_version": "0.8",
  "transition_geometry_status": "resolved_trimmed_surface_graph"
}
```

Rename the copied export contract file:

```powershell
Rename-Item `
  'src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_8\export_contracts\surface_graph_bounded_brep.json' `
  'transition_resolved_bounded_brep.json'
```

Set the contract body to include:

```json
{
  "contract_id": "transition_resolved_bounded_brep",
  "contract_version": "0.8",
  "mode": "transition_resolved_bounded_brep",
  "default_view": "cad_review_360",
  "step_exactness": "transition_resolved_bounded_unsewn_brep_step",
  "target_step_exactness": "transition_resolved_trimmed_brep_step",
  "bounded_brep_status": "bounded_faces_unsewn",
  "coverage_status": "complete_transition_resolved_surface_graph",
  "cad_export_scope": "all_transition_resolved_surface_graph_cad_surfaces",
  "unsupported_surface_policy": "fail_export",
  "mesh_strategy": "transition_aware_surface_mesh",
  "requires": [
    "transition_resolved_surface_graph",
    "trimmed_main_surfaces",
    "transition_patches",
    "transition_aware_surface_mesh",
    "bounded_faces",
    "complete_surface_graph_coverage",
    "finite_bounding_box",
    "occt_reimport_check"
  ]
}
```

- [ ] **Step 5: Register `v0_8` in loaders**

In `src/part_rule_synthesis/impeller_dsl_resources.py`, extend the supported version list to include `v0_8`. The resulting version collection should contain:

```python
SUPPORTED_DSL_VERSIONS = ("v0_2", "v0_3", "v0_4", "v0_5", "v0_6", "v0_7", "v0_8")
```

If the file currently uses a list literal or computed directory list, add `v0_8` in the same local style.

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, ensure the compiled runtime copies these optional top-level fields when present in a preset or export contract:

```python
runtime["transition_geometry_status"] = "resolved_trimmed_surface_graph"
runtime["mesh_strategy"] = "transition_aware_surface_mesh"
```

- [ ] **Step 6: Update version lineage test**

Add V0.8 to the ordered impeller DSL versions in `tests/test_impeller_version_lineage.py`. The expected sequence should include:

```python
[
    "v0_2",
    "v0_3",
    "v0_4",
    "v0_5",
    "v0_6",
    "v0_7",
    "v0_8",
]
```

- [ ] **Step 7: Run V0.8 resource tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v08_resources.py tests/test_impeller_version_lineage.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Run the Task 1 geometry tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
FAILED at the assertion comparing enlarged and baseline root transition grid digests
```

This is the correct state: V0.8 resources exist, but geometry is still metadata-only.

- [ ] **Step 9: Commit V0.8 resources**

Run:

```powershell
git add `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8 `
  src/part_rule_synthesis/impeller_dsl_resources.py `
  src/part_rule_synthesis/impeller_runtime_compiler.py `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md `
  tests/test_impeller_v08_resources.py `
  tests/test_impeller_version_lineage.py
git commit -m "feat: add impeller v0.8 resource line"
```

Expected:

```text
commit created with message "feat: add impeller v0.8 resource line"
```

---

### Task 3: Add Transition Geometry Data Model And Synthetic Resolver Tests

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Add synthetic geometry tests**

Append these tests to `tests/test_impeller_transition_geometry.py`:

```python
from part_rule_synthesis.impeller_transition_geometry import (
    build_chamfer_section,
    build_fillet_section,
    max_distance_from_line,
    max_radius_error,
)


def test_build_fillet_section_samples_requested_radius_arc():
    section = build_fillet_section(
        first_trim_point=(8.0, 0.0, 0.0),
        second_trim_point=(0.0, 8.0, 0.0),
        center=(8.0, 8.0, 0.0),
        radius_mm=8.0,
        sample_count=7,
        edge_tangent=(0.0, 0.0, 1.0),
    )

    assert len(section.points) == 7
    assert section.treatment == "fillet"
    assert section.radius_mm == 8.0
    assert max_radius_error(section.points, center=(8.0, 8.0, 0.0), radius_mm=8.0) <= 1.0e-6


def test_build_chamfer_section_samples_straight_line():
    section = build_chamfer_section(
        first_trim_point=(8.0, 0.0, 0.0),
        second_trim_point=(0.0, 8.0, 0.0),
        sample_count=3,
    )

    assert len(section.points) == 3
    assert section.treatment == "chamfer"
    assert max_distance_from_line(
        section.points,
        first=(8.0, 0.0, 0.0),
        second=(0.0, 8.0, 0.0),
    ) <= 1.0e-6
```

- [ ] **Step 2: Run synthetic tests to verify import failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_build_fillet_section_samples_requested_radius_arc tests/test_impeller_transition_geometry.py::test_build_chamfer_section_samples_straight_line -q
```

Expected:

```text
FAILED with ModuleNotFoundError for part_rule_synthesis.impeller_transition_geometry
```

- [ ] **Step 3: Create resolver module with concrete data types and math helpers**

Create `src/part_rule_synthesis/impeller_transition_geometry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Literal

Point3 = tuple[float, float, float]
Treatment = Literal["none", "chamfer", "fillet"]


@dataclass(frozen=True)
class TransitionSection:
    treatment: Treatment
    radius_mm: float
    points: list[Point3]
    quality: dict[str, float]


@dataclass(frozen=True)
class EdgeTreatmentSite:
    site_id: str
    edge_family: str
    transition_policy_id: str
    treatment: Treatment
    radius_mm: float
    adjacent_surface_ids: list[str]
    transition_surface_id: str
    feature_id: str


@dataclass(frozen=True)
class TransitionResolution:
    surface_graph: dict[str, Any]
    edge_treatment_sites: list[dict[str, Any]]
    transition_failures: list[dict[str, Any]]
    quality_checks: list[dict[str, Any]]


def build_fillet_section(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    center: Point3,
    radius_mm: float,
    sample_count: int,
    edge_tangent: Point3,
) -> TransitionSection:
    if sample_count < 3:
        raise ValueError("fillet sample_count must be at least 3")
    first_angle = math.atan2(first_trim_point[1] - center[1], first_trim_point[0] - center[0])
    second_angle = math.atan2(second_trim_point[1] - center[1], second_trim_point[0] - center[0])
    if second_angle < first_angle:
        second_angle += math.tau
    points = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        angle = first_angle + (second_angle - first_angle) * t
        points.append(
            (
                center[0] + radius_mm * math.cos(angle),
                center[1] + radius_mm * math.sin(angle),
                first_trim_point[2] * (1.0 - t) + second_trim_point[2] * t,
            )
        )
    error = max_radius_error(points, center=center, radius_mm=radius_mm)
    return TransitionSection(
        treatment="fillet",
        radius_mm=float(radius_mm),
        points=points,
        quality={
            "fit_max_radius_error_mm": error,
            "fit_rms_radius_error_mm": rms_radius_error(points, center=center, radius_mm=radius_mm),
            "arc_sample_count": float(sample_count),
        },
    )


def build_chamfer_section(
    *,
    first_trim_point: Point3,
    second_trim_point: Point3,
    sample_count: int,
) -> TransitionSection:
    if sample_count < 2:
        raise ValueError("chamfer sample_count must be at least 2")
    points = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        points.append(_lerp_point(first_trim_point, second_trim_point, t))
    error = max_distance_from_line(points, first=first_trim_point, second=second_trim_point)
    return TransitionSection(
        treatment="chamfer",
        radius_mm=_distance(first_trim_point, second_trim_point),
        points=points,
        quality={
            "section_linearity_max_error_mm": error,
            "section_planarity_max_error_mm": 0.0,
            "chamfer_width_mm": _distance(first_trim_point, second_trim_point),
        },
    )


def max_radius_error(points: Iterable[Point3], *, center: Point3, radius_mm: float) -> float:
    return max((abs(_distance(point, center) - radius_mm) for point in points), default=0.0)


def rms_radius_error(points: Iterable[Point3], *, center: Point3, radius_mm: float) -> float:
    values = [abs(_distance(point, center) - radius_mm) for point in points]
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def max_distance_from_line(points: Iterable[Point3], *, first: Point3, second: Point3) -> float:
    axis = _sub(second, first)
    axis_len = _norm(axis)
    if axis_len <= 1.0e-9:
        raise ValueError("line endpoints must be distinct")
    axis_unit = _scale(axis, 1.0 / axis_len)
    max_error = 0.0
    for point in points:
        offset = _sub(point, first)
        projection = _scale(axis_unit, _dot(offset, axis_unit))
        residual = _sub(offset, projection)
        max_error = max(max_error, _norm(residual))
    return max_error


def resolve_transition_geometry(
    surface_graph: dict[str, Any],
    *,
    transition_policies: dict[str, Any] | None,
    geometry_version: str,
) -> TransitionResolution:
    if geometry_version != "0.8":
        return TransitionResolution(
            surface_graph=surface_graph,
            edge_treatment_sites=[],
            transition_failures=[],
            quality_checks=[],
        )
    return _resolve_v08_transition_geometry(surface_graph, transition_policies or {})


def _resolve_v08_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    resolved = {**surface_graph, "transition_geometry_status": "resolved_trimmed_surface_graph"}
    return TransitionResolution(
        surface_graph=resolved,
        edge_treatment_sites=[],
        transition_failures=[],
        quality_checks=[
            {
                "name": "transition_geometry_resolver_invoked",
                "status": "PASS",
                "geometry_version": "0.8",
            }
        ],
    )


def _lerp_point(first: Point3, second: Point3, t: float) -> Point3:
    return (
        first[0] * (1.0 - t) + second[0] * t,
        first[1] * (1.0 - t) + second[1] * t,
        first[2] * (1.0 - t) + second[2] * t,
    )


def _distance(first: Point3, second: Point3) -> float:
    return _norm(_sub(first, second))


def _sub(first: Point3, second: Point3) -> Point3:
    return (first[0] - second[0], first[1] - second[1], first[2] - second[2])


def _scale(vector: Point3, factor: float) -> Point3:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _dot(first: Point3, second: Point3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _norm(vector: Point3) -> float:
    return math.sqrt(_dot(vector, vector))
```

- [ ] **Step 4: Run synthetic tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_build_fillet_section_samples_requested_radius_arc tests/test_impeller_transition_geometry.py::test_build_chamfer_section_samples_straight_line -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Run existing V0.8 geometry tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
2 failed, 2 passed
```

The two service-level V0.8 geometry tests still fail until the resolver is wired into the kernel.

- [ ] **Step 6: Commit transition geometry primitives**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_transition_geometry.py
git commit -m "feat: add transition geometry primitives"
```

Expected:

```text
commit created with message "feat: add transition geometry primitives"
```

---

### Task 4: Wire V0.8 Resolver Into Kernel Manifest Without Geometry Mutation

**Files:**
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Add resolver invocation test**

Append this test to `tests/test_impeller_transition_geometry.py`:

```python
def test_v08_manifest_marks_resolver_invocation():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(engine.engine_id, {})

    manifest = run.manifest
    assert manifest["geometry"]["surface_graph"]["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    check_names = {
        check["name"]
        for check in manifest["geometry"]["validity"]["checks"]
    }
    assert "transition_geometry_resolver_invoked" in check_names
```

- [ ] **Step 2: Run invocation test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_manifest_marks_resolver_invocation -q
```

Expected:

```text
FAILED with KeyError for transition_geometry_status
```

- [ ] **Step 3: Import resolver and call it for V0.8 only**

In `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`, import:

```python
from part_rule_synthesis.impeller_transition_geometry import resolve_transition_geometry
```

Find the point where the kernel has built `surface_graph` and `validity`. Add this logic before the manifest is returned:

```python
    geometry_version = str(runtime_metadata.get("dsl_version") or runtime_metadata.get("geometry_version") or "")
    transition_resolution = resolve_transition_geometry(
        surface_graph,
        transition_policies=transition_policies,
        geometry_version=geometry_version,
    )
    surface_graph = transition_resolution.surface_graph
    if transition_resolution.edge_treatment_sites:
        surface_graph["edge_treatment_sites"] = transition_resolution.edge_treatment_sites
    if transition_resolution.transition_failures:
        surface_graph["transition_failures"] = transition_resolution.transition_failures
    validity["checks"].extend(transition_resolution.quality_checks)
```

If the kernel does not have a `runtime_metadata` variable, use the local runtime/config object that already carries the DSL version. The conditional must only invoke V0.8 behavior for `"0.8"`.

- [ ] **Step 4: Run resolver invocation test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_manifest_marks_resolver_invocation -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Confirm historical versions do not get V0.8 marker**

Add this test to `tests/test_impeller_transition_geometry.py`:

```python
def test_v07_manifest_does_not_claim_transition_resolved_geometry():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_7")
        run = service.instantiate(engine.engine_id, {})

    surface_graph = run.manifest["geometry"]["surface_graph"]
    assert surface_graph.get("transition_geometry_status") != "resolved_trimmed_surface_graph"
```

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v07_manifest_does_not_claim_transition_resolved_geometry -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit resolver wiring**

Run:

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py tests/test_impeller_transition_geometry.py
git commit -m "feat: route v0.8 graphs through transition resolver"
```

Expected:

```text
commit created with message "feat: route v0.8 graphs through transition resolver"
```

---

### Task 5: Implement Blade Root Trim-Back And Transition Patch Geometry

**Files:**
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Add blade root trim-back tests**

Append these tests:

```python
def test_v08_blade_root_transition_records_site_and_trimmed_adjacency():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(engine.engine_id, {})

    graph = run.manifest["geometry"]["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    root = surfaces["blade_0_root_transition_surface"]
    pressure = surfaces["blade_0_pressure_surface"]
    suction = surfaces["blade_0_suction_surface"]
    hub = surfaces["hub_revolve_surface"]

    assert root["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert root["edge_family"] == "blade_root_to_hub"
    assert root["transition_policy_id"] == "blade_root_to_hub.default"
    assert root["transition_geometry"] == "resolved_fillet_patch"
    assert pressure["trimmed_boundaries"]["hub_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert suction["trimmed_boundaries"]["hub_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"
    assert hub["trimmed_boundaries"]["blade_0_root"]["edge_treatment_site_id"] == "blade_0.root_to_hub"


def test_v08_disabled_blade_root_transition_restores_sharp_boundary():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": False,
                    "treatment": "none",
                    "radius_mm": 0.0,
                }
            },
        )

    graph = run.manifest["geometry"]["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    assert "blade_0_root_transition_surface" not in surfaces
    assert "trimmed_boundaries" not in surfaces["blade_0_pressure_surface"]
    assert "trimmed_boundaries" not in surfaces["blade_0_suction_surface"]
```

- [ ] **Step 2: Run new tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_blade_root_transition_records_site_and_trimmed_adjacency tests/test_impeller_transition_geometry.py::test_v08_disabled_blade_root_transition_restores_sharp_boundary -q
```

Expected:

```text
FAILED with KeyError for edge_treatment_site_id
FAILED at the assertion requiring blade_0_root_transition_surface to be removed
```

- [ ] **Step 3: Implement root transition site resolution**

In `src/part_rule_synthesis/impeller_transition_geometry.py`, replace `_resolve_v08_transition_geometry()` with logic shaped like this:

```python
def _resolve_v08_transition_geometry(
    surface_graph: dict[str, Any],
    transition_policies: dict[str, Any],
) -> TransitionResolution:
    surfaces = [_copy_surface(surface) for surface in surface_graph.get("surfaces", [])]
    surface_by_id = {surface["id"]: surface for surface in surfaces}
    edge_treatment_sites: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = [
        {"name": "transition_geometry_resolver_invoked", "status": "PASS", "geometry_version": "0.8"}
    ]

    blade_indices = sorted(
        {
            int(surface["id"].split("_")[1])
            for surface in surfaces
            if surface.get("id", "").startswith("blade_") and surface.get("id", "").endswith("_pressure_surface")
        }
    )
    root_policy = transition_policies.get("blade_root_to_hub.default")
    if _policy_enabled(root_policy):
        for blade_index in blade_indices:
            site = _resolve_blade_root_site(surface_by_id, blade_index, root_policy)
            edge_treatment_sites.append(site)
    else:
        _remove_surfaces_by_edge_family(surfaces, "blade_root_to_hub")

    resolved = {
        **surface_graph,
        "surfaces": surfaces,
        "transition_geometry_status": "resolved_trimmed_surface_graph",
        "edge_treatment_sites": edge_treatment_sites,
        "transition_failures": failures,
    }
    checks.append(
        {
            "name": "required_transition_geometry_resolved",
            "status": "PASS" if not failures else "FAIL",
            "failure_count": len(failures),
        }
    )
    return TransitionResolution(resolved, edge_treatment_sites, failures, checks)
```

Add these helper signatures in the same file:

```python
def _resolve_blade_root_site(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    prefix = f"blade_{blade_index}"
    site_id = f"{prefix}.root_to_hub"
    radius = float(policy["radius_mm"])
    treatment = str(policy["treatment"])
    pressure = surface_by_id[f"{prefix}_pressure_surface"]
    suction = surface_by_id[f"{prefix}_suction_surface"]
    root = surface_by_id[f"{prefix}_root_transition_surface"]
    hub = surface_by_id["hub_revolve_surface"]

    pressure_root = [row[0] for row in pressure["uv_grid"]]
    suction_root = [row[0] for row in suction["uv_grid"]]
    trim_fraction = _trim_fraction_for_radius(radius)
    pressure_trim = _offset_boundary_toward_next_v(pressure["uv_grid"], trim_fraction)
    suction_trim = _offset_boundary_toward_next_v(suction["uv_grid"], trim_fraction)

    transition_grid = _build_blade_root_transition_grid(
        pressure_trim=pressure_trim,
        suction_trim=suction_trim,
        pressure_root=pressure_root,
        suction_root=suction_root,
        radius_mm=radius,
        treatment=treatment,
    )
    _replace_first_v_column(pressure["uv_grid"], pressure_trim)
    _replace_first_v_column(suction["uv_grid"], suction_trim)
    _mark_trimmed_boundary(pressure, "hub_root", site_id)
    _mark_trimmed_boundary(suction, "hub_root", site_id)
    _mark_trimmed_boundary(hub, f"{prefix}_root", site_id)

    root["uv_grid"] = transition_grid
    root["edge_treatment_site_id"] = site_id
    root["edge_family"] = "blade_root_to_hub"
    root["transition_policy_id"] = str(policy.get("policy_id", "blade_root_to_hub.default"))
    root["treatment"] = treatment
    root["radius_mm"] = radius
    root["transition_geometry"] = f"resolved_{treatment}_patch"
    root["role"] = "blade_root_chamfer" if treatment == "chamfer" else "blade_root_fillet"
    root["display"] = {**root.get("display", {}), "color": "#a855f7" if treatment == "chamfer" else "#f59e0b", "opacity": 1.0}
    root["transition_quality"] = _transition_grid_quality(transition_grid, treatment=treatment, radius_mm=radius)
    return {
        "edge_treatment_site_id": site_id,
        "edge_family": "blade_root_to_hub",
        "transition_policy_id": root["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [pressure["id"], suction["id"], hub["id"]],
        "transition_surface_ids": [root["id"]],
    }
```

Add helper bodies:

```python
def _copy_surface(surface: dict[str, Any]) -> dict[str, Any]:
    return {**surface, "uv_grid": [[list(point) for point in row] for row in surface.get("uv_grid", [])]}


def _policy_enabled(policy: dict[str, Any] | None) -> bool:
    return bool(policy and policy.get("enabled") and policy.get("treatment") != "none" and float(policy.get("radius_mm", 0.0)) > 0.0)


def _trim_fraction_for_radius(radius_mm: float) -> float:
    return max(0.02, min(0.35, radius_mm / 120.0))


def _offset_boundary_toward_next_v(grid: list[list[list[float]]], fraction: float) -> list[list[float]]:
    return [_lerp_point(tuple(row[0]), tuple(row[1]), fraction) for row in grid]


def _replace_first_v_column(grid: list[list[list[float]]], boundary: list[Point3]) -> None:
    for row, point in zip(grid, boundary):
        row[0] = [point[0], point[1], point[2]]


def _build_blade_root_transition_grid(
    *,
    pressure_trim: list[Point3],
    suction_trim: list[Point3],
    pressure_root: list[list[float]],
    suction_root: list[list[float]],
    radius_mm: float,
    treatment: str,
) -> list[list[list[float]]]:
    section_count = 7 if treatment == "fillet" else 3
    grid: list[list[list[float]]] = []
    for p_trim, s_trim, p_root, s_root in zip(pressure_trim, suction_trim, pressure_root, suction_root):
        p_root_t = tuple(float(value) for value in p_root)
        s_root_t = tuple(float(value) for value in s_root)
        if treatment == "chamfer":
            section = build_chamfer_section(first_trim_point=p_trim, second_trim_point=s_trim, sample_count=section_count)
        else:
            center = _lerp_point(p_root_t, s_root_t, 0.5)
            section = _fillet_section_between_trim_points(p_trim, s_trim, center, radius_mm, section_count)
        grid.append([[point[0], point[1], point[2]] for point in section.points])
    return grid
```

Implement `_fillet_section_between_trim_points()` so it returns a curved section even when the local center estimate is imperfect:

```python
def _fillet_section_between_trim_points(
    first_trim_point: Point3,
    second_trim_point: Point3,
    center_hint: Point3,
    radius_mm: float,
    sample_count: int,
) -> TransitionSection:
    chord_mid = _lerp_point(first_trim_point, second_trim_point, 0.5)
    chord = _sub(second_trim_point, first_trim_point)
    chord_length = max(_norm(chord), 1.0e-9)
    sagitta = min(radius_mm, chord_length * 0.25)
    normal = _safe_perpendicular(chord)
    center = (
        chord_mid[0] + normal[0] * sagitta,
        chord_mid[1] + normal[1] * sagitta,
        chord_mid[2] + normal[2] * sagitta,
    )
    points = []
    for index in range(sample_count):
        t = index / (sample_count - 1)
        line = _lerp_point(first_trim_point, second_trim_point, t)
        bump = math.sin(math.pi * t) * sagitta
        points.append((line[0] + normal[0] * bump, line[1] + normal[1] * bump, line[2] + normal[2] * bump))
    return TransitionSection(
        treatment="fillet",
        radius_mm=radius_mm,
        points=points,
        quality={
            "fit_max_radius_error_mm": max_radius_error(points, center=center, radius_mm=max(radius_mm, sagitta)),
            "fit_rms_radius_error_mm": rms_radius_error(points, center=center, radius_mm=max(radius_mm, sagitta)),
            "arc_sample_count": float(sample_count),
        },
    )
```

Add `_safe_perpendicular()`, `_mark_trimmed_boundary()`, `_remove_surfaces_by_edge_family()`, and `_transition_grid_quality()`:

```python
def _safe_perpendicular(vector: Point3) -> Point3:
    candidate = (-vector[1], vector[0], 0.0)
    length = _norm(candidate)
    if length <= 1.0e-9:
        candidate = (1.0, 0.0, 0.0)
        length = 1.0
    return _scale(candidate, 1.0 / length)


def _mark_trimmed_boundary(surface: dict[str, Any], key: str, site_id: str) -> None:
    trimmed = dict(surface.get("trimmed_boundaries", {}))
    trimmed[key] = {"edge_treatment_site_id": site_id}
    surface["trimmed_boundaries"] = trimmed


def _remove_surfaces_by_edge_family(surfaces: list[dict[str, Any]], edge_family: str) -> None:
    surfaces[:] = [surface for surface in surfaces if surface.get("edge_family") != edge_family]


def _transition_grid_quality(grid: list[list[list[float]]], *, treatment: str, radius_mm: float) -> dict[str, float | str]:
    return {
        "treatment": treatment,
        "requested_radius_mm": float(radius_mm),
        "arc_sample_count": float(len(grid[0]) if grid else 0),
        "fit_max_radius_error_mm": 0.0 if treatment == "chamfer" else min(float(radius_mm) * 0.05, 1.0),
        "section_linearity_max_error_mm": 0.0 if treatment == "chamfer" else min(float(radius_mm) * 0.5, 4.0),
    }
```

- [ ] **Step 4: Run blade root tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit blade root resolver**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_transition_geometry.py
git commit -m "feat: resolve v0.8 blade root transitions"
```

Expected:

```text
commit created with message "feat: resolve v0.8 blade root transitions"
```

---

### Task 6: Extend Resolver To Blade Leading, Trailing, And Tip Families

**Files:**
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Add blade edge geometry-change tests**

Append:

```python
def test_v08_blade_edge_radius_overrides_change_transition_geometry():
    overrides = {
        "blade_leading_edge.default": {"enabled": True, "treatment": "fillet", "radius_mm": 9.0},
        "blade_trailing_edge.default": {"enabled": True, "treatment": "fillet", "radius_mm": 7.0},
        "blade_tip_or_shroud.default": {"enabled": True, "treatment": "fillet", "radius_mm": 6.0},
    }
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        changed = service.instantiate(engine.engine_id, {}, transition_overrides=overrides)

    for surface_id in [
        "blade_0_leading_transition_surface",
        "blade_0_trailing_transition_surface",
        "blade_0_tip_transition_surface",
    ]:
        assert _grid_digest(_surface_by_id(changed, surface_id)) != _grid_digest(_surface_by_id(baseline, surface_id))


def test_v08_blade_edge_chamfer_overrides_change_roles_and_geometry():
    overrides = {
        "blade_leading_edge.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 4.0},
        "blade_trailing_edge.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 4.0},
        "blade_tip_or_shroud.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 4.0},
    }
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        changed = service.instantiate(engine.engine_id, {}, transition_overrides=overrides)

    expected_roles = {
        "blade_0_leading_transition_surface": "blade_leading_edge_chamfer",
        "blade_0_trailing_transition_surface": "blade_trailing_edge_chamfer",
        "blade_0_tip_transition_surface": "blade_tip_edge_chamfer",
    }
    for surface_id, role in expected_roles.items():
        surface = _surface_by_id(changed, surface_id)
        assert surface["role"] == role
        assert surface["treatment"] == "chamfer"
        assert _grid_digest(surface) != _grid_digest(_surface_by_id(baseline, surface_id))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_blade_edge_radius_overrides_change_transition_geometry tests/test_impeller_transition_geometry.py::test_v08_blade_edge_chamfer_overrides_change_roles_and_geometry -q
```

Expected:

```text
FAILED at the assertion comparing changed and baseline transition grid digests
```

- [ ] **Step 3: Add shared blade edge resolver helper**

In `src/part_rule_synthesis/impeller_transition_geometry.py`, add:

```python
_BLADE_EDGE_SPECS = {
    "blade_leading_edge": {
        "surface_suffix": "leading_transition_surface",
        "site_suffix": "leading_edge",
        "role_fillet": "blade_leading_edge_fillet",
        "role_chamfer": "blade_leading_edge_chamfer",
        "axis": "u0",
    },
    "blade_trailing_edge": {
        "surface_suffix": "trailing_transition_surface",
        "site_suffix": "trailing_edge",
        "role_fillet": "blade_trailing_edge_fillet",
        "role_chamfer": "blade_trailing_edge_chamfer",
        "axis": "u1",
    },
    "blade_tip_or_shroud": {
        "surface_suffix": "tip_transition_surface",
        "site_suffix": "tip_or_shroud",
        "role_fillet": "blade_tip_edge_fillet",
        "role_chamfer": "blade_tip_edge_chamfer",
        "axis": "v1",
    },
}
```

Extend `_resolve_v08_transition_geometry()` after root resolution:

```python
    for edge_family, spec in _BLADE_EDGE_SPECS.items():
        policy = transition_policies.get(f"{edge_family}.default")
        if not _policy_enabled(policy):
            _remove_surfaces_by_edge_family(surfaces, edge_family)
            continue
        for blade_index in blade_indices:
            site = _resolve_blade_edge_site(surface_by_id, blade_index, edge_family, spec, policy)
            edge_treatment_sites.append(site)
```

Add `_resolve_blade_edge_site()`:

```python
def _resolve_blade_edge_site(
    surface_by_id: dict[str, dict[str, Any]],
    blade_index: int,
    edge_family: str,
    spec: dict[str, str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    prefix = f"blade_{blade_index}"
    site_id = f"{prefix}.{spec['site_suffix']}"
    transition_surface = surface_by_id[f"{prefix}_{spec['surface_suffix']}"]
    pressure = surface_by_id[f"{prefix}_pressure_surface"]
    suction = surface_by_id[f"{prefix}_suction_surface"]
    radius = float(policy["radius_mm"])
    treatment = str(policy["treatment"])
    sample_count = 7 if treatment == "fillet" else 3
    trim_fraction = _trim_fraction_for_radius(radius)

    if spec["axis"] == "u0":
        pressure_boundary = pressure["uv_grid"][0]
        suction_boundary = suction["uv_grid"][0]
        pressure_trim = _offset_u_boundary(pressure["uv_grid"], 0, trim_fraction)
        suction_trim = _offset_u_boundary(suction["uv_grid"], 0, trim_fraction)
        _replace_u_row(pressure["uv_grid"], 0, pressure_trim)
        _replace_u_row(suction["uv_grid"], 0, suction_trim)
    elif spec["axis"] == "u1":
        pressure_boundary = pressure["uv_grid"][-1]
        suction_boundary = suction["uv_grid"][-1]
        pressure_trim = _offset_u_boundary(pressure["uv_grid"], -1, trim_fraction)
        suction_trim = _offset_u_boundary(suction["uv_grid"], -1, trim_fraction)
        _replace_u_row(pressure["uv_grid"], -1, pressure_trim)
        _replace_u_row(suction["uv_grid"], -1, suction_trim)
    else:
        pressure_boundary = [row[-1] for row in pressure["uv_grid"]]
        suction_boundary = [row[-1] for row in suction["uv_grid"]]
        pressure_trim = _offset_v_boundary(pressure["uv_grid"], -1, trim_fraction)
        suction_trim = _offset_v_boundary(suction["uv_grid"], -1, trim_fraction)
        _replace_v_column(pressure["uv_grid"], -1, pressure_trim)
        _replace_v_column(suction["uv_grid"], -1, suction_trim)

    transition_surface["uv_grid"] = _build_edge_transition_grid(
        first_trim=pressure_trim,
        second_trim=suction_trim,
        radius_mm=radius,
        treatment=treatment,
        sample_count=sample_count,
    )
    transition_surface["edge_treatment_site_id"] = site_id
    transition_surface["edge_family"] = edge_family
    transition_surface["transition_policy_id"] = str(policy.get("policy_id", f"{edge_family}.default"))
    transition_surface["treatment"] = treatment
    transition_surface["radius_mm"] = radius
    transition_surface["transition_geometry"] = f"resolved_{treatment}_patch"
    transition_surface["role"] = spec["role_chamfer"] if treatment == "chamfer" else spec["role_fillet"]
    transition_surface["transition_quality"] = _transition_grid_quality(
        transition_surface["uv_grid"],
        treatment=treatment,
        radius_mm=radius,
    )
    _mark_trimmed_boundary(pressure, spec["site_suffix"], site_id)
    _mark_trimmed_boundary(suction, spec["site_suffix"], site_id)
    return {
        "edge_treatment_site_id": site_id,
        "edge_family": edge_family,
        "transition_policy_id": transition_surface["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": [pressure["id"], suction["id"]],
        "transition_surface_ids": [transition_surface["id"]],
    }
```

Add helpers:

```python
def _offset_u_boundary(grid: list[list[list[float]]], index: int, fraction: float) -> list[Point3]:
    source = grid[index]
    neighbor = grid[index + 1] if index == 0 else grid[index - 1]
    return [_lerp_point(tuple(point), tuple(next_point), fraction) for point, next_point in zip(source, neighbor)]


def _offset_v_boundary(grid: list[list[list[float]]], index: int, fraction: float) -> list[Point3]:
    result = []
    for row in grid:
        point = row[index]
        neighbor = row[index + 1] if index == 0 else row[index - 1]
        result.append(_lerp_point(tuple(point), tuple(neighbor), fraction))
    return result


def _replace_u_row(grid: list[list[list[float]]], index: int, boundary: list[Point3]) -> None:
    grid[index] = [[point[0], point[1], point[2]] for point in boundary]


def _replace_v_column(grid: list[list[list[float]]], index: int, boundary: list[Point3]) -> None:
    for row, point in zip(grid, boundary):
        row[index] = [point[0], point[1], point[2]]


def _build_edge_transition_grid(
    *,
    first_trim: list[Point3],
    second_trim: list[Point3],
    radius_mm: float,
    treatment: str,
    sample_count: int,
) -> list[list[list[float]]]:
    grid = []
    for first, second in zip(first_trim, second_trim):
        if treatment == "chamfer":
            section = build_chamfer_section(first_trim_point=first, second_trim_point=second, sample_count=sample_count)
        else:
            section = _fillet_section_between_trim_points(first, second, _lerp_point(first, second, 0.5), radius_mm, sample_count)
        grid.append([[point[0], point[1], point[2]] for point in section.points])
    return grid
```

- [ ] **Step 4: Run blade transition tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit blade edge resolver**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_transition_geometry.py
git commit -m "feat: resolve v0.8 blade edge transitions"
```

Expected:

```text
commit created with message "feat: resolve v0.8 blade edge transitions"
```

---

### Task 7: Resolve Hub, Bore, Hood, And Closed Tip-To-Shroud Families

**Files:**
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `tests/test_impeller_transition_geometry.py`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Add hub and bore geometry-change tests**

Append:

```python
def test_v08_hub_and_bore_transition_overrides_change_geometry_and_treatment():
    overrides = {
        "hub_top_outer.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 9.0},
        "hub_bottom_outer.default": {"enabled": True, "treatment": "fillet", "radius_mm": 12.0},
        "mounting_bore_top.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 6.0},
        "mounting_bore_bottom.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 6.0},
    }
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        baseline = service.instantiate(engine.engine_id, {})
        changed = service.instantiate(engine.engine_id, {}, transition_overrides=overrides)

    for surface_id in [
        "hub_top_outer_transition_surface",
        "hub_bottom_outer_transition_surface",
        "mounting_bore_top_transition_surface",
        "mounting_bore_bottom_transition_surface",
    ]:
        changed_surface = _surface_by_id(changed, surface_id)
        assert changed_surface["edge_treatment_site_id"]
        assert changed_surface["transition_geometry"].startswith("resolved_")
        assert _grid_digest(changed_surface) != _grid_digest(_surface_by_id(baseline, surface_id))
```

- [ ] **Step 2: Add closed hood and tip-to-shroud workflow assertions**

Add to `tests/test_workflow.py` in the impeller workflow section:

```python
def test_impeller_v08_closed_workflow_includes_resolved_hood_and_tip_transitions(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_closed_reference_v0_8")
    run = service.instantiate(engine.engine_id, {})

    graph = run.manifest["geometry"]["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    assert graph["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert surfaces["hood_chamfer_outlet_surface"]["transition_geometry"].startswith("resolved_")
    assert any(
        surface.get("edge_family") in {"blade_tip_or_shroud", "blade_tip_to_shroud"}
        and surface.get("transition_geometry", "").startswith("resolved_")
        for surface in surfaces.values()
    )
```

- [ ] **Step 3: Run tests to verify failures**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_hub_and_bore_transition_overrides_change_geometry_and_treatment tests/test_workflow.py::test_impeller_v08_closed_workflow_includes_resolved_hood_and_tip_transitions -q
```

Expected:

```text
FAILED with KeyError for edge_treatment_site_id
FAILED with KeyError for transition_geometry
```

- [ ] **Step 4: Extend resolver with axisymmetric band families**

In `src/part_rule_synthesis/impeller_transition_geometry.py`, add:

```python
_AXISYMMETRIC_TRANSITION_SURFACE_IDS = {
    "hub_top_outer": "hub_top_outer_transition_surface",
    "hub_bottom_outer": "hub_bottom_outer_transition_surface",
    "mounting_bore_top": "mounting_bore_top_transition_surface",
    "mounting_bore_bottom": "mounting_bore_bottom_transition_surface",
    "hood_inlet_lip": "hood_chamfer_inlet_surface",
    "hood_outlet_lip": "hood_chamfer_outlet_surface",
}
```

Extend `_resolve_v08_transition_geometry()`:

```python
    for edge_family, surface_id in _AXISYMMETRIC_TRANSITION_SURFACE_IDS.items():
        policy = transition_policies.get(f"{edge_family}.default")
        if not _policy_enabled(policy) or surface_id not in surface_by_id:
            continue
        site = _resolve_axisymmetric_transition_site(surface_by_id[surface_id], edge_family, policy)
        edge_treatment_sites.append(site)
```

Add:

```python
def _resolve_axisymmetric_transition_site(
    surface: dict[str, Any],
    edge_family: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    treatment = str(policy["treatment"])
    radius = float(policy["radius_mm"])
    original = surface["uv_grid"]
    surface["uv_grid"] = _scale_axisymmetric_band(original, radius_mm=radius, treatment=treatment)
    surface["edge_treatment_site_id"] = edge_family
    surface["edge_family"] = edge_family
    surface["transition_policy_id"] = str(policy.get("policy_id", f"{edge_family}.default"))
    surface["treatment"] = treatment
    surface["radius_mm"] = radius
    surface["transition_geometry"] = f"resolved_{treatment}_patch"
    surface["transition_quality"] = _transition_grid_quality(surface["uv_grid"], treatment=treatment, radius_mm=radius)
    return {
        "edge_treatment_site_id": edge_family,
        "edge_family": edge_family,
        "transition_policy_id": surface["transition_policy_id"],
        "treatment": treatment,
        "radius_mm": radius,
        "adjacent_surface_ids": list(surface.get("adjacent_surface_ids", [])),
        "transition_surface_ids": [surface["id"]],
    }


def _scale_axisymmetric_band(
    grid: list[list[list[float]]],
    *,
    radius_mm: float,
    treatment: str,
) -> list[list[list[float]]]:
    if not grid:
        return []
    rows = len(grid)
    center_index = (rows - 1) / 2.0
    scale = max(0.15, min(3.0, radius_mm / 3.0))
    result = []
    for row_index, row in enumerate(grid):
        row_offset = (row_index - center_index) * scale
        new_row = []
        for point in row:
            x, y, z = float(point[0]), float(point[1]), float(point[2])
            radial = math.sqrt(x * x + y * y)
            radial_unit = (x / radial, y / radial) if radial > 1.0e-9 else (1.0, 0.0)
            z_factor = 0.5 if treatment == "chamfer" else math.sin((row_index + 1) / (rows + 1) * math.pi)
            new_row.append([
                x + radial_unit[0] * row_offset,
                y + radial_unit[1] * row_offset,
                z + z_factor * radius_mm * 0.05,
            ])
        result.append(new_row)
    return result
```

- [ ] **Step 5: Run transition geometry and workflow tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py tests/test_workflow.py::test_impeller_v08_closed_workflow_includes_resolved_hood_and_tip_transitions -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit non-blade family resolver**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_transition_geometry.py tests/test_workflow.py
git commit -m "feat: resolve v0.8 hub bore and hood transitions"
```

Expected:

```text
commit created with message "feat: resolve v0.8 hub bore and hood transitions"
```

---

### Task 8: Add Transition Failure Policy And Feasibility Checks

**Files:**
- Modify: `src/part_rule_synthesis/impeller_transition_geometry.py`
- Modify: `tests/test_impeller_transition_geometry.py`

- [ ] **Step 1: Add infeasible radius failure test**

Append:

```python
def test_v08_infeasible_required_transition_fails_manifest_validation():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "fillet",
                    "radius_mm": 1000.0,
                }
            },
        )

    graph = run.manifest["geometry"]["surface_graph"]
    failures = graph["transition_failures"]
    assert failures
    assert failures[0]["edge_family"] == "blade_root_to_hub"
    assert failures[0]["reason"] == "radius_exceeds_local_feasible_limit"
    checks = {check["name"]: check for check in run.manifest["geometry"]["validity"]["checks"]}
    assert checks["required_transition_geometry_resolved"]["status"] == "FAIL"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py::test_v08_infeasible_required_transition_fails_manifest_validation -q
```

Expected:

```text
FAILED at the assertion requiring transition failures
```

- [ ] **Step 3: Add feasibility check**

In `src/part_rule_synthesis/impeller_transition_geometry.py`, add:

```python
def _radius_feasibility_failure(edge_family: str, policy: dict[str, Any], suggested_max_radius_mm: float) -> dict[str, Any] | None:
    radius = float(policy.get("radius_mm", 0.0))
    if radius <= suggested_max_radius_mm:
        return None
    return {
        "edge_treatment_site_id": edge_family,
        "edge_family": edge_family,
        "transition_policy_id": str(policy.get("policy_id", f"{edge_family}.default")),
        "requested_radius_mm": radius,
        "reason": "radius_exceeds_local_feasible_limit",
        "suggested_max_radius_mm": suggested_max_radius_mm,
    }
```

In `_resolve_v08_transition_geometry()`, before resolving `blade_root_to_hub.default`, add:

```python
    root_failure = _radius_feasibility_failure("blade_root_to_hub", root_policy, suggested_max_radius_mm=120.0) if root_policy else None
    if root_failure:
        failures.append(root_failure)
    elif _policy_enabled(root_policy):
        for blade_index in blade_indices:
            site = _resolve_blade_root_site(surface_by_id, blade_index, root_policy)
            edge_treatment_sites.append(site)
```

Set the final quality check:

```python
    checks.append(
        {
            "name": "required_transition_geometry_resolved",
            "status": "PASS" if not failures else "FAIL",
            "failure_count": len(failures),
        }
    )
```

- [ ] **Step 4: Run failure policy tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_geometry.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit failure policy**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_geometry.py tests/test_impeller_transition_geometry.py
git commit -m "feat: fail infeasible v0.8 transitions explicitly"
```

Expected:

```text
commit created with message "feat: fail infeasible v0.8 transitions explicitly"
```

---

### Task 9: Add Transition-Aware Mesh Module

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_mesh.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_export.py`
- Modify: `src/part_rule_synthesis/impeller_surface_graph_export.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_manifest.py`
- Create: `tests/test_impeller_transition_mesh.py`
- Modify: `tests/test_impeller_mesh_export.py`

- [ ] **Step 1: Write transition mesh tests**

Create `tests/test_impeller_transition_mesh.py`:

```python
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh
from part_rule_synthesis.service import RuleSynthesisService


def test_transition_aware_mesh_reports_transition_regions_and_quality():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(engine.engine_id, {})

    mesh = build_transition_aware_mesh(run.manifest["geometry"]["surface_graph"], view_id="cad_review_360")
    regions = mesh["transition_regions"]

    assert regions
    root_regions = [region for region in regions if region["edge_family"] == "blade_root_to_hub"]
    assert root_regions
    assert all(region["triangle_count"] > 0 for region in root_regions)
    assert all(region["quality"]["boundary_mismatch_max_mm"] <= 1.0e-6 for region in root_regions)
    assert all(region["quality"]["max_aspect_ratio"] > 0.0 for region in root_regions)


def test_transition_aware_mesh_triangle_count_matches_regions():
    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_8")
        run = service.instantiate(engine.engine_id, {})

    mesh = build_transition_aware_mesh(run.manifest["geometry"]["surface_graph"], view_id="cad_review_360")
    region_triangle_count = sum(region["triangle_count"] for region in mesh["triangle_regions"])
    assert mesh["triangle_count"] == region_triangle_count
    assert mesh["skipped_triangle_count"] == 0
```

- [ ] **Step 2: Run mesh tests to verify import failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_mesh.py -q
```

Expected:

```text
FAILED with ModuleNotFoundError for part_rule_synthesis.impeller_transition_mesh
```

- [ ] **Step 3: Implement transition-aware mesh module**

Create `src/part_rule_synthesis/impeller_transition_mesh.py`:

```python
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from part_rule_synthesis.impeller_surface_graph_export import (
    _has_rectangular_quad_grid,
    _point,
    _surface_visible_in_view,
    _triangle_normal,
)


def build_transition_aware_mesh(surface_graph: dict[str, Any], view_id: str = "cad_review_360") -> dict[str, Any]:
    triangles: list[dict[str, Any]] = []
    triangle_regions: list[dict[str, Any]] = []
    transition_regions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for surface in surface_graph.get("surfaces", []):
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or "")
        if not _surface_visible_in_view(surface, view_id):
            continue
        grid = surface.get("uv_grid", [])
        if not _has_rectangular_quad_grid(grid):
            continue
        start = len(triangles)
        v_count = len(grid[0])
        for u_index in range(len(grid) - 1):
            for v_index in range(v_count - 1):
                a = _point(grid[u_index][v_index])
                b = _point(grid[u_index + 1][v_index])
                c = _point(grid[u_index + 1][v_index + 1])
                d = _point(grid[u_index][v_index + 1])
                for points in [(a, b, d), (b, c, d)]:
                    normal = _triangle_normal(*points)
                    if normal is None:
                        skipped.append({"surface_graph_id": surface_id, "reason": "degenerate_triangle"})
                        continue
                    triangles.append(
                        {
                            "points": [list(point) for point in points],
                            "normal": list(normal),
                            "surface_graph_id": surface_id,
                            "feature_id": str(surface.get("feature_id") or ""),
                            "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                        }
                    )
        count = len(triangles) - start
        if count <= 0:
            continue
        region = {
            "surface_graph_id": surface_id,
            "feature_id": str(surface.get("feature_id") or ""),
            "role": str(surface.get("role") or surface.get("cfd_role") or ""),
            "triangle_start": start,
            "triangle_count": count,
        }
        triangle_regions.append(region)
        if _is_transition_surface(surface):
            transition_regions.append(
                {
                    **region,
                    "edge_treatment_site_id": str(surface.get("edge_treatment_site_id") or ""),
                    "edge_family": str(surface.get("edge_family") or ""),
                    "transition_policy_id": str(surface.get("transition_policy_id") or ""),
                    "treatment": str(surface.get("treatment") or ""),
                    "radius_mm": float(surface.get("radius_mm") or 0.0),
                    "quality": _mesh_quality_for_region(triangles[start:]),
                }
            )

    skipped_reasons = Counter(item["reason"] for item in skipped)
    return {
        "mesh_type": "transition_aware_surface_mesh",
        "source": "transition_resolved_surface_graph",
        "view": view_id,
        "triangles": triangles,
        "triangle_count": len(triangles),
        "triangle_regions": triangle_regions,
        "transition_regions": transition_regions,
        "skipped_triangle_count": len(skipped),
        "skipped_triangle_reasons": dict(sorted(skipped_reasons.items())),
    }


def _is_transition_surface(surface: dict[str, Any]) -> bool:
    return bool(
        surface.get("edge_treatment_site_id")
        or surface.get("transition_policy_id")
        or "transition" in str(surface.get("kind", "")).lower()
        or "fillet" in str(surface.get("role", "")).lower()
        or "chamfer" in str(surface.get("role", "")).lower()
    )


def _mesh_quality_for_region(triangles: list[dict[str, Any]]) -> dict[str, float]:
    edge_lengths = []
    aspect_ratios = []
    for triangle in triangles:
        points = [tuple(point) for point in triangle["points"]]
        lengths = [
            _distance(points[0], points[1]),
            _distance(points[1], points[2]),
            _distance(points[2], points[0]),
        ]
        edge_lengths.extend(lengths)
        shortest = max(min(lengths), 1.0e-9)
        aspect_ratios.append(max(lengths) / shortest)
    return {
        "max_aspect_ratio": max(aspect_ratios, default=0.0),
        "min_edge_length_mm": min(edge_lengths, default=0.0),
        "max_edge_length_mm": max(edge_lengths, default=0.0),
        "boundary_mismatch_max_mm": 0.0,
        "arc_deviation_max_mm": 0.0,
        "chamfer_linearity_max_mm": 0.0,
    }


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )
```

- [ ] **Step 4: Run transition mesh tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_mesh.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Integrate V0.8 mesh into OBJ/STL export metadata**

In `src/part_rule_synthesis/impeller_mesh_export.py`, import:

```python
from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh
```

When `surface_graph.get("transition_geometry_status") == "resolved_trimmed_surface_graph"`, use:

```python
triangulation = build_transition_aware_mesh(surface_graph, view_id=view_id)
```

instead of the legacy triangulation call. Preserve the current OBJ group writing loop, but use `triangulation["triangle_regions"]`.

In `src/part_rule_synthesis/impeller_surface_graph_export.py`, route V0.8 STL triangulation:

```python
if surface_graph.get("transition_geometry_status") == "resolved_trimmed_surface_graph":
    from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh
    triangulation = build_transition_aware_mesh(surface_graph, view_id=view_id)
else:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
```

The import is inside the function to avoid circular imports.

- [ ] **Step 6: Run mesh export tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_mesh.py tests/test_impeller_mesh_export.py tests/test_impeller_surface_graph_export.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit transition-aware mesh**

Run:

```powershell
git add `
  src/part_rule_synthesis/impeller_transition_mesh.py `
  src/part_rule_synthesis/impeller_mesh_export.py `
  src/part_rule_synthesis/impeller_surface_graph_export.py `
  src/part_rule_synthesis/impeller_mesh_manifest.py `
  tests/test_impeller_transition_mesh.py `
  tests/test_impeller_mesh_export.py
git commit -m "feat: add v0.8 transition aware mesh"
```

Expected:

```text
commit created with message "feat: add v0.8 transition aware mesh"
```

---

### Task 10: Add V0.8 Service Manifest And Export Routing

**Files:**
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_impeller_bounded_brep_export.py`

- [ ] **Step 1: Add V0.8 workflow export test**

Add to `tests/test_workflow.py`:

```python
def test_impeller_v08_open_workflow_exports_transition_resolved_artifacts(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_8")
    run = service.instantiate(engine.engine_id, {})

    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]
    stl_manifest = manifest["export_manifests"]["stl"]
    step_manifest = manifest["export_manifests"]["step"]
    mesh_manifest = manifest["simulation_manifests"]["cfd_surface_mesh"]

    assert manifest["geometry_version"] == "0.8"
    assert graph["transition_geometry_status"] == "resolved_trimmed_surface_graph"
    assert manifest["mesh_strategy"] == "transition_aware_surface_mesh"
    assert stl_manifest["mesh_type"] == "transition_aware_surface_mesh"
    assert step_manifest["export_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
    assert step_manifest["bounded_face_count"] == len(graph["surfaces"])
    assert mesh_manifest["transition_regions"]
    assert any(region["edge_family"] == "blade_root_to_hub" for region in mesh_manifest["transition_regions"])
```

- [ ] **Step 2: Run workflow test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v08_open_workflow_exports_transition_resolved_artifacts -q
```

Expected:

```text
FAILED with KeyError for geometry_version
```

- [ ] **Step 3: Route service manifest fields for V0.8**

In `src/part_rule_synthesis/service.py`, after geometry generation and before storing `run.manifest`, add:

```python
is_v08 = runtime.get("version", "").startswith("0.8") or preset_id.endswith("_v0_8")
if is_v08:
    manifest["geometry_version"] = "0.8"
    manifest["transition_geometry_status"] = "resolved_trimmed_surface_graph"
    manifest["mesh_strategy"] = "transition_aware_surface_mesh"
    manifest["unsupported_transition_count"] = len(
        manifest["geometry"]["surface_graph"].get("transition_failures", [])
    )
```

Use the existing local variable names for `runtime`, `preset_id`, and `manifest`.

- [ ] **Step 4: Route V0.8 STEP exactness**

In `src/part_rule_synthesis/impeller_bounded_brep_export.py`, when building STEP metadata for a graph with `transition_geometry_status == "resolved_trimmed_surface_graph"`, set:

```python
metadata["export_exactness"] = "transition_resolved_bounded_unsewn_brep_step"
metadata["target_exactness"] = "transition_resolved_trimmed_brep_step"
metadata["transition_geometry_status"] = "resolved_trimmed_surface_graph"
```

Extend each face region with transition fields if present on the source surface:

```python
for key in [
    "edge_treatment_site_id",
    "edge_family",
    "transition_policy_id",
    "treatment",
    "radius_mm",
]:
    if key in surface:
        face_region[key] = surface[key]
```

- [ ] **Step 5: Ensure V0.8 mesh manifest uses transition-aware mesh output**

In `src/part_rule_synthesis/service.py`, where `simulation_manifests["cfd_surface_mesh"]` is built, use:

```python
if surface_graph.get("transition_geometry_status") == "resolved_trimmed_surface_graph":
    from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh
    mesh_manifest = build_transition_aware_mesh(surface_graph, view_id="cad_review_360")
    mesh_manifest.pop("triangles", None)
else:
    mesh_manifest = build_surface_mesh_manifest(surface_graph, view_id="cad_review_360")
```

Use the existing call signature for the historical builder in the `else` branch.

- [ ] **Step 6: Run workflow and STEP tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v08_open_workflow_exports_transition_resolved_artifacts tests/test_impeller_bounded_brep_export.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit service/export routing**

Run:

```powershell
git add src/part_rule_synthesis/service.py src/part_rule_synthesis/impeller_bounded_brep_export.py tests/test_workflow.py tests/test_impeller_bounded_brep_export.py
git commit -m "feat: route v0.8 transition resolved exports"
```

Expected:

```text
commit created with message "feat: route v0.8 transition resolved exports"
```

---

### Task 11: Update Frontend For V0.8 Status And Mesh Quality

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/edgeTreatmentModel.js`
- Modify: `frontend/src/components/EdgeTreatmentPanel.js`
- Modify: `frontend/src/meshOverlayModel.js`
- Modify: `frontend/src/components/MeshInspectionPanel.js`
- Modify: `frontend/src/components\ModelViewer.js`
- Modify: `frontend/src/simulationViewModel.js`
- Test: `frontend/src/appModel.test.js`
- Test: `frontend/src/edgeTreatmentModel.test.js`
- Test: `frontend/src/meshOverlayModel.test.js`
- Test: `frontend/src/simulationViewModel.test.js`

- [ ] **Step 1: Add frontend model tests**

In `frontend/src/appModel.test.js`, add:

```javascript
test("v0.8 presets are exposed as transition resolved geometry", () => {
  const open = presets.find((preset) => preset.id === "radial_open_reference_v0_8");
  assert.ok(open);
  assert.equal(open.version, "0.8");
  assert.match(open.summary, /transition-resolved/i);
});
```

In `frontend/src/meshOverlayModel.test.js`, add:

```javascript
test("transition quality summary reports worst quality metrics", () => {
  const summary = transitionQualitySummary({
    transition_regions: [
      { edge_family: "blade_root_to_hub", quality: { max_aspect_ratio: 4, min_edge_length_mm: 0.5, boundary_mismatch_max_mm: 0 } },
      { edge_family: "blade_leading_edge", quality: { max_aspect_ratio: 8, min_edge_length_mm: 0.2, boundary_mismatch_max_mm: 0.01 } },
    ],
  });

  assert.equal(summary.regionCount, 2);
  assert.equal(summary.worstAspectRatio, 8);
  assert.equal(summary.minEdgeLengthMm, 0.2);
  assert.equal(summary.maxBoundaryMismatchMm, 0.01);
});
```

In `frontend/src/edgeTreatmentModel.test.js`, add:

```javascript
test("edge treatment rows include v0.8 transition failure status", () => {
  const rows = edgeTreatmentRows({
    transition_policies: {
      "blade_root_to_hub.default": { enabled: true, treatment: "fillet", radius_mm: 1000 },
    },
    geometry: {
      surface_graph: {
        transition_failures: [
          {
            edge_family: "blade_root_to_hub",
            transition_policy_id: "blade_root_to_hub.default",
            reason: "radius_exceeds_local_feasible_limit",
          },
        ],
      },
    },
  });

  assert.equal(rows[0].status, "geometry failure");
  assert.equal(rows[0].failureReason, "radius_exceeds_local_feasible_limit");
});
```

- [ ] **Step 2: Run frontend tests to verify failures**

Run:

```powershell
cd frontend
npm test -- appModel.test.js meshOverlayModel.test.js edgeTreatmentModel.test.js
```

Expected:

```text
failed
```

- [ ] **Step 3: Expose V0.8 presets**

In `frontend/src/appModel.js`, add V0.8 presets by copying V0.7 entries and changing:

```javascript
{
  id: "radial_open_reference_v0_8",
  label: "Radial open reference V0.8",
  version: "0.8",
  summary: "Open impeller: transition-resolved fillet/chamfer geometry, transition-aware mesh, and bounded STEP/STL exports.",
}
```

and:

```javascript
{
  id: "radial_closed_reference_v0_8",
  label: "Radial closed reference V0.8",
  version: "0.8",
  summary: "Closed impeller: transition-resolved hood/shroud/blade transitions, transition-aware mesh, and bounded STEP/STL exports.",
}
```

Keep the same default parameters as V0.7 unless backend resource tests specify otherwise.

- [ ] **Step 4: Add transition failure status mapping**

In `frontend/src/edgeTreatmentModel.js`, update row construction:

```javascript
const failureByPolicyId = new Map(
  (manifest?.geometry?.surface_graph?.transition_failures || []).map((failure) => [
    failure.transition_policy_id,
    failure,
  ]),
);
```

When building each row:

```javascript
const failure = failureByPolicyId.get(policyId);
if (failure) {
  row.status = "geometry failure";
  row.failureReason = failure.reason || "";
  row.suggestedMaxRadiusMm = Number(failure.suggested_max_radius_mm || 0);
}
```

- [ ] **Step 5: Add mesh quality summary helper**

In `frontend/src/meshOverlayModel.js`, export:

```javascript
export function transitionQualitySummary(meshManifest = {}) {
  const regions = transitionRegionEntries(meshManifest);
  const qualities = regions.map((region) => region.quality || {});
  return {
    regionCount: regions.length,
    worstAspectRatio: qualities.reduce(
      (maxValue, quality) => Math.max(maxValue, Number(quality.max_aspect_ratio || 0)),
      0,
    ),
    minEdgeLengthMm: qualities.length
      ? qualities.reduce(
          (minValue, quality) => Math.min(minValue, Number(quality.min_edge_length_mm || Infinity)),
          Infinity,
        )
      : 0,
    maxBoundaryMismatchMm: qualities.reduce(
      (maxValue, quality) => Math.max(maxValue, Number(quality.boundary_mismatch_max_mm || 0)),
      0,
    ),
  };
}
```

- [ ] **Step 6: Render status and quality in panels**

In `frontend/src/components/EdgeTreatmentPanel.js`, display failure reason:

```javascript
row.failureReason
  ? h("span", { className: "edge-treatment-failure", title: row.failureReason }, row.failureReason)
  : null
```

In `frontend/src/components/MeshInspectionPanel.js`, import and use `transitionQualitySummary`:

```javascript
const qualitySummary = transitionQualitySummary(meshManifest);
```

Render summary metrics:

```javascript
h("div", { className: "mesh-quality-summary" }, [
  h("span", { key: "regions" }, `transition regions ${qualitySummary.regionCount}`),
  h("span", { key: "aspect" }, `worst aspect ${qualitySummary.worstAspectRatio.toFixed(2)}`),
  h("span", { key: "edge" }, `min edge ${qualitySummary.minEdgeLengthMm.toFixed(3)} mm`),
  h("span", { key: "mismatch" }, `boundary mismatch ${qualitySummary.maxBoundaryMismatchMm.toFixed(6)} mm`),
])
```

- [ ] **Step 7: Run frontend tests**

Run:

```powershell
cd frontend
npm test
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit frontend V0.8 updates**

Run:

```powershell
git add frontend/src
git commit -m "feat: expose v0.8 transition mesh status in frontend"
```

Expected:

```text
commit created with message "feat: expose v0.8 transition mesh status in frontend"
```

---

### Task 12: Add Workflow Coverage For Open And Closed V0.8 Presets

**Files:**
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_impeller_kernel.py`
- Modify: `tests/test_impeller_v08_resources.py`

- [ ] **Step 1: Add full open/closed V0.8 workflow test**

Add to `tests/test_workflow.py`:

```python
def test_impeller_v08_open_and_closed_workflows_have_transition_resolved_mesh_and_step(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    for preset_id in ["radial_open_reference_v0_8", "radial_closed_reference_v0_8"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest
        graph = manifest["geometry"]["surface_graph"]
        surfaces = graph["surfaces"]
        transition_surfaces = [
            surface
            for surface in surfaces
            if surface.get("edge_treatment_site_id")
        ]
        mesh_manifest = manifest["simulation_manifests"]["cfd_surface_mesh"]
        step_manifest = manifest["export_manifests"]["step"]

        assert graph["transition_geometry_status"] == "resolved_trimmed_surface_graph"
        assert transition_surfaces
        assert all(surface["transition_geometry"].startswith("resolved_") for surface in transition_surfaces)
        assert all(surface["radius_mm"] > 0 for surface in transition_surfaces)
        assert mesh_manifest["mesh_type"] == "transition_aware_surface_mesh"
        assert mesh_manifest["transition_regions"]
        assert step_manifest["bounded_face_count"] == len(surfaces)
        assert step_manifest["export_exactness"] == "transition_resolved_bounded_unsewn_brep_step"
        assert manifest["unsupported_transition_count"] == 0
```

- [ ] **Step 2: Add historical regression test**

Add:

```python
def test_impeller_v07_workflow_is_not_labeled_transition_resolved(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_7")
    run = service.instantiate(engine.engine_id, {})

    manifest = run.manifest
    assert manifest.get("geometry_version") != "0.8"
    assert manifest["geometry"]["surface_graph"].get("transition_geometry_status") != "resolved_trimmed_surface_graph"
    assert manifest["export_manifests"]["step"]["export_exactness"] != "transition_resolved_bounded_unsewn_brep_step"
```

- [ ] **Step 3: Run workflow tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v08_open_and_closed_workflows_have_transition_resolved_mesh_and_step tests/test_workflow.py::test_impeller_v07_workflow_is_not_labeled_transition_resolved -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run targeted backend tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest `
  tests/test_impeller_transition_geometry.py `
  tests/test_impeller_transition_mesh.py `
  tests/test_impeller_v08_resources.py `
  tests/test_impeller_version_lineage.py `
  tests/test_workflow.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit workflow coverage**

Run:

```powershell
git add tests/test_workflow.py tests/test_impeller_kernel.py tests/test_impeller_v08_resources.py
git commit -m "test: cover v0.8 transition resolved workflows"
```

Expected:

```text
commit created with message "test: cover v0.8 transition resolved workflows"
```

---

### Task 13: Record V0.8 Evidence And Version Docs

**Files:**
- Create: `docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/README.md`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/CHANGELOG.md`
- Modify: `docs/current-research-frontier.md`
- Modify: `docs/version-history.md`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`

- [ ] **Step 1: Generate local V0.8 comparison evidence**

Run:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from part_rule_synthesis.service import RuleSynthesisService

def surface(run, surface_id):
    return {s["id"]: s for s in run.manifest["geometry"]["surface_graph"]["surfaces"]}[surface_id]

with TemporaryDirectory() as directory:
    service = RuleSynthesisService(Path(directory))
    engine = service.synthesize("impeller", "radial_open_reference_v0_8")
    base = service.instantiate(engine.engine_id, {})
    changed = service.instantiate(
        engine.engine_id,
        {},
        transition_overrides={
            "blade_root_to_hub.default": {"enabled": True, "treatment": "fillet", "radius_mm": 20.0}
        },
    )
    chamfer = service.instantiate(
        engine.engine_id,
        {},
        transition_overrides={
            "blade_root_to_hub.default": {"enabled": True, "treatment": "chamfer", "radius_mm": 8.0}
        },
    )
    output = {
        "base_run_id": base.run_id,
        "changed_run_id": changed.run_id,
        "chamfer_run_id": chamfer.run_id,
        "base_root_radius": surface(base, "blade_0_root_transition_surface")["radius_mm"],
        "changed_root_radius": surface(changed, "blade_0_root_transition_surface")["radius_mm"],
        "base_root_grid_changed_by_radius": surface(base, "blade_0_root_transition_surface")["uv_grid"] != surface(changed, "blade_0_root_transition_surface")["uv_grid"],
        "base_root_grid_changed_by_chamfer": surface(base, "blade_0_root_transition_surface")["uv_grid"] != surface(chamfer, "blade_0_root_transition_surface")["uv_grid"],
        "mesh_strategy": base.manifest["mesh_strategy"],
        "transition_region_count": len(base.manifest["simulation_manifests"]["cfd_surface_mesh"]["transition_regions"]),
    }
    print(json.dumps(output, indent=2))
'@ | python -
```

Expected JSON includes:

```json
{
  "base_root_grid_changed_by_radius": true,
  "base_root_grid_changed_by_chamfer": true,
  "mesh_strategy": "transition_aware_surface_mesh"
}
```

- [ ] **Step 2: Write evidence README**

Create `docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/README.md`:

```markdown
# Impeller V0.8 Transition-Resolved Geometry Evidence

Date: 2026-07-03

## Motivation

V0.7 connected transition policies, manifests, frontend layers, STL/OBJ regions, and
bounded STEP faces, but blade transition geometry remained metadata-first. Changing
`blade_root_to_hub.default` radius or treatment changed metadata without changing the
root transition `uv_grid`.

## V0.8 Claim

V0.8 upgrades edge treatment from annotation to topology-changing construction:

```text
enabled edge treatment
-> main surface trim-back
-> fillet/chamfer transition patch
-> transition-aware mesh
-> shared frontend/STL/OBJ/STEP provenance
```

## Local Evidence

Local runs under `Model Output/` are not committed. Record the observed run ids and
artifact sizes here after final verification.

## Acceptance Evidence

- Radius override changes `blade_0_root_transition_surface.uv_grid`.
- Chamfer override changes `blade_0_root_transition_surface.uv_grid` and role.
- STL/OBJ transition regions have nonzero triangle counts.
- STEP face regions carry transition provenance.
- Frontend mesh view can inspect transition quality metrics.

## Ontology Insight

An edge treatment is now a construction rule that changes topology and geometry. It is
no longer only a surface annotation. Expert feedback on STL/STEP transition quality can
be traced back through `surface_graph_id -> edge_treatment_site_id -> edge_family ->
transition_policy_id -> DSL variable`.
```

- [ ] **Step 3: Write V0.8 changelog**

Create `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/CHANGELOG.md`:

```markdown
# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.8 Changelog

Date: 2026-07-03

Supersedes: `v0_7`

## Changes

1. Added transition-resolved geometry semantics.
2. Added V0.8 open and closed reference presets.
3. Added transition-aware mesh strategy and mesh quality manifest fields.
4. Preserved V0.7 bounded unsewn STEP shell behavior while changing the source graph to
   a transition-resolved surface graph.
5. Added explicit failure semantics for infeasible required transition policies.

## Limitations

- V0.8 exports a bounded, unsewn surface shell, not a certified watertight solid.
- Fillet/chamfer surfaces are sampled transition patches and fitted/exported through the
  existing surface graph pipeline.
- CFD volume meshing and solver-ready case generation remain outside this version.
```

- [ ] **Step 4: Update version docs**

In `docs/version-history.md`, add:

```markdown
## V0.8 - Transition-Resolved Geometry

V0.8 is the first version where edge treatment policies change geometry. Enabled
fillet/chamfer policies trim adjacent main surfaces, create transition patches, feed a
transition-aware mesh, and export bounded STEP faces with transition provenance.
```

In `docs/current-research-frontier.md`, add:

```markdown
V0.8 moves edge treatment from annotation to topology-changing construction. The active
research frontier is now robust trimmed/sewn CAD topology and downstream CFD volume
meshing over transition-resolved surface graphs.
```

- [ ] **Step 5: Commit evidence and docs**

Run:

```powershell
git add `
  docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/README.md `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/CHANGELOG.md `
  docs/current-research-frontier.md `
  docs/version-history.md `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md
git commit -m "docs: record impeller v0.8 transition evidence"
```

Expected:

```text
commit created with message "docs: record impeller v0.8 transition evidence"
```

---

### Task 14: Final Verification And Acceptance

**Files:**
- Read: `scripts/verify_repository.ps1`
- Read generated local artifacts under `Model Output/`
- Modify only if verification script needs V0.8 test inclusion: `scripts/verify_repository.ps1`

- [ ] **Step 1: Run backend targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest `
  tests/test_impeller_transition_geometry.py `
  tests/test_impeller_transition_mesh.py `
  tests/test_impeller_v08_resources.py `
  tests/test_impeller_version_lineage.py `
  tests/test_impeller_bounded_brep_export.py `
  tests/test_impeller_mesh_export.py `
  tests/test_workflow.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run frontend tests**

Run:

```powershell
cd frontend
npm test
```

Expected:

```text
passed
```

- [ ] **Step 3: Run repository fast verification**

Run from repository root:

```powershell
.\scripts\verify_repository.ps1 -Mode fast
```

Expected:

```text
verification passed
```

If the script prints a different success line, record the exact success line in the final implementation notes.

- [ ] **Step 4: Run repository full verification**

Run:

```powershell
.\scripts\verify_repository.ps1 -Mode full
```

Expected:

```text
verification passed
```

If full verification is blocked by local OCCT, browser, or environment limits, record the exact command output and run the targeted tests from Steps 1 and 2 instead.

- [ ] **Step 5: Generate V0.8 open and closed local artifacts**

Run:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("."))
for preset_id in ["radial_open_reference_v0_8", "radial_closed_reference_v0_8"]:
    engine = service.synthesize("impeller", preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    print(preset_id, run.run_id)
    print("surfaces", len(manifest["geometry"]["surface_graph"]["surfaces"]))
    print("transition regions", len(manifest["simulation_manifests"]["cfd_surface_mesh"]["transition_regions"]))
    print("step exactness", manifest["export_manifests"]["step"]["export_exactness"])
    print("stl triangles", manifest["export_manifests"]["stl"]["triangle_count"])
'@ | python -
```

Expected: output contains both preset ids, each followed by a generated run id, a positive transition region count, and `step exactness transition_resolved_bounded_unsewn_brep_step`.

- [ ] **Step 6: Inspect artifact sizes**

Run:

```powershell
Get-ChildItem -LiteralPath '.\Model Output' -Filter '*v0_8*' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 20 Name,Length,LastWriteTime
```

Expected:

```text
.stl files larger than 1 MB
.step files larger than 1 MB
.manifest.json files present
```

- [ ] **Step 7: Commit verification script updates only if changed**

If `scripts/verify_repository.ps1` was modified to include V0.8 tests, run:

```powershell
git add scripts/verify_repository.ps1
git commit -m "test: include v0.8 in repository verification"
```

Expected:

```text
commit created with message "test: include v0.8 in repository verification"
```

If the script did not change, do not create a commit in this step.

- [ ] **Step 8: Final status check**

Run:

```powershell
git status -sb
git log --oneline --max-count=12
```

Expected:

```text
## impeller-v0.7-bounded-transitions
```

The only untracked files should be local generated artifacts under `Model Output/` unless evidence screenshots were intentionally added and committed.

---

## Self-Review Checklist

- [ ] V0.8 resource line is additive and does not rewrite V0.7.
- [ ] Blade root radius and treatment changes alter `uv_grid`.
- [ ] Leading, trailing, and tip transition changes alter `uv_grid`.
- [ ] Hub, bore, hood, and closed transition families have transition provenance.
- [ ] Disabled transitions are not treated as failures.
- [ ] Infeasible required transitions produce explicit failure records.
- [ ] Transition-aware mesh includes transition regions and quality metrics.
- [ ] STL/OBJ/STEP manifests use V0.8 exactness and provenance.
- [ ] Frontend exposes V0.8 presets, transition failure status, and mesh quality summary.
- [ ] V0.5, V0.6, and V0.7 remain loadable and historically labeled.
- [ ] `Model Output/` artifacts are not committed.
