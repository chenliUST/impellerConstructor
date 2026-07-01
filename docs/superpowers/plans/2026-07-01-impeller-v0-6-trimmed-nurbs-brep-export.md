# Impeller v0.6 Trimmed NURBS B-Rep Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V0.6 as the first impeller version that can export `surface_graph` geometry as trimmed NURBS/analytic B-Rep STEP, while preserving V0.5 mesh exports, adding `Model Output/` artifact routing, CFD360 mesh inspection, and interactive fillet/blend controls.

**Architecture:** Keep V0.5 untouched and add a V0.6 resource line. Add a focused OCCT/OCP B-Rep exporter beside the existing mesh exporter, enrich `surface_graph` with `cad_surface` and `cad_edge` payloads, and route V0.6 exports through the B-Rep path while still emitting STL and mesh STEP for comparison. Add frontend controls for export type, mesh inspection, and fillet radii without changing legacy presets.

**Tech Stack:** Python 3.12, FastAPI, OCP/OCCT via CadQuery environment, pytest, Three.js frontend, Node test runner, PowerShell verification scripts, versioned JSON DSL resources.

---

## Scope Note

This is a large version milestone. The tasks are ordered so that the work can be reviewed after each commit:

1. prove local OCCT B-spline STEP output;
2. add V0.6 resources without changing behavior;
3. add `cad_surface` and `cad_edge` payloads;
4. build B-Rep STEP export;
5. integrate exports and `Model Output/`;
6. add fillet/blend geometry and controls;
7. add CFD360 mesh inspection;
8. update evidence and run full verification.

Do not remove V0.5 behavior. Do not label mesh STEP as B-Rep STEP.

## File Structure

Create:

- `src/part_rule_synthesis/occt_compat.py`  
  Small OCP import and STEP writer helpers with one place to fail if OCCT is missing.

- `src/part_rule_synthesis/impeller_cad_payload.py`  
  Converts graph surfaces and boundaries into `cad_surface` and `cad_edge` payload dictionaries.

- `src/part_rule_synthesis/impeller_brep_export.py`  
  Converts `cad_surface` and `cad_edge` payloads into OCCT faces, writes B-Rep STEP, and returns export manifest metadata.

- `src/part_rule_synthesis/impeller_mesh_manifest.py`  
  Computes surface mesh quality metrics for the CFD360 mesh inspection view from graph triangles.

- `tests/test_impeller_occt_compat.py`  
  Confirms local OCP can write a minimal B-spline STEP containing B-spline and advanced-face entities.

- `tests/test_impeller_cad_payload.py`  
  Tests `cad_surface` and `cad_edge` payload generation from simple graph surfaces.

- `tests/test_impeller_brep_export.py`  
  Tests trimmed B-spline face STEP export, exactness labels, and no mesh fallback.

- `tests/test_impeller_mesh_manifest.py`  
  Tests mesh metrics and patch-region accounting.

- `tests/test_impeller_v06_resources.py`  
  Tests V0.6 DSL bundle loading, presets, export contract, and version lineage.

- `frontend/src/meshViewModel.js`  
  Frontend model for CFD360 mesh metrics, patch coloring, and mesh view state.

- `frontend/src/meshViewModel.test.js`  
  Frontend tests for mesh metrics display data and mesh view options.

- `frontend/src/components/MeshInspectionPanel.js`  
  CFD360 mesh summary panel for triangle counts, boundary/nonmanifold counts, and quality ranges.

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6/`  
  Versioned DSL resources copied from V0.5 and extended for B-Rep export.

Modify:

- `src/part_rule_synthesis/impeller_dsl_resources.py`  
  Load V0.6 resources and export contracts.

- `src/part_rule_synthesis/impeller_runtime_compiler.py`  
  Include V0.6 presets, parameters, export contracts, and new fillet variables.

- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`  
  Emit CAD payloads, root/edge blend surfaces, and feasibility checks.

- `src/part_rule_synthesis/impeller_surface_graph_export.py`  
  Keep V0.5 STL and mesh STEP behavior; expose reusable triangulation for mesh manifests.

- `src/part_rule_synthesis/service.py`  
  Route V0.6 exports through B-Rep STEP, write output copies to `Model Output/`, and include mesh manifests.

- `src/part_rule_synthesis/api.py`  
  Return correct download filenames and content disposition for multiple export kinds.

- `frontend/src/appModel.js`  
  Point default frontend presets to V0.6 only after backend workflow tests pass, add export type labels, and add fillet parameters.

- `frontend/src/apiClient.js`  
  Handle export kinds and filenames.

- `frontend/src/simulationViewModel.js`  
  Add CFD360 mesh view option.

- `frontend/src/workspaceModel.js`  
  Add mesh/quality inspection layer names.

- `frontend/src/components/ModelViewer.js`  
  Render mesh mode from graph triangulation or mesh manifest regions.

- `frontend/src/components/CfdManifestPanel.js`  
  Add Mesh tab/section entry point.

- `docs/current-research-frontier.md`, `docs/repository-map.md`, `README.md`  
  Update claims only after V0.6 workflow tests pass.

- `docs/evidence/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export/README.md`  
  Add generated evidence and manual CAD check notes.

---

## Task 1: OCCT/OCP B-Spline STEP Spike

**Files:**

- Create: `src/part_rule_synthesis/occt_compat.py`
- Create: `tests/test_impeller_occt_compat.py`

- [ ] **Step 1: Write the failing OCP availability and STEP smoke tests**

Create `tests/test_impeller_occt_compat.py`:

```python
from pathlib import Path

from part_rule_synthesis.occt_compat import write_minimal_bspline_step


def test_occt_can_write_minimal_bspline_step(tmp_path: Path):
    step_path = tmp_path / "minimal_bspline.step"

    metadata = write_minimal_bspline_step(step_path)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert metadata == {
        "writer": "occt_stepcontrol_writer",
        "shape": "single_bspline_face",
        "status": "PASS",
    }
    assert step_path.stat().st_size > 1024
    assert "B_SPLINE_SURFACE" in text
    assert "ADVANCED_FACE" in text
    assert "TRIANGULATED_FACE_SET" not in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_occt_compat.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'part_rule_synthesis.occt_compat'`.

- [ ] **Step 3: Implement the minimal OCCT writer helper**

Create `src/part_rule_synthesis/occt_compat.py`:

```python
from __future__ import annotations

from pathlib import Path


def write_minimal_bspline_step(path: Path) -> dict[str, str]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    poles = TColgp_Array2OfPnt(1, 4, 1, 4)
    for u_index in range(1, 5):
        for v_index in range(1, 5):
            poles.SetValue(
                u_index,
                v_index,
                gp_Pnt(float(u_index - 1), float(v_index - 1), 0.1 * (u_index - 1) * (v_index - 1)),
            )

    u_knots = _real_array([0.0, 1.0])
    v_knots = _real_array([0.0, 1.0])
    u_multiplicities = _int_array([4, 4])
    v_multiplicities = _int_array([4, 4])
    surface = Geom_BSplineSurface(
        poles,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        3,
        3,
        False,
        False,
    )
    face = BRepBuilderAPI_MakeFace(surface, 1.0e-6).Face()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    writer.Transfer(face, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP write failed with status {status}")
    return {"writer": "occt_stepcontrol_writer", "shape": "single_bspline_face", "status": "PASS"}


def _real_array(values: list[float]):
    from OCP.TColStd import TColStd_Array1OfReal

    result = TColStd_Array1OfReal(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, float(value))
    return result


def _int_array(values: list[int]):
    from OCP.TColStd import TColStd_Array1OfInteger

    result = TColStd_Array1OfInteger(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, int(value))
    return result
```

- [ ] **Step 4: Run the OCP smoke test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_occt_compat.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the OCP spike**

```powershell
git add src/part_rule_synthesis/occt_compat.py tests/test_impeller_occt_compat.py
git commit -m "test: prove occt bspline step writing"
```

---

## Task 2: Add V0.6 DSL Resource Line

**Files:**

- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6/`
- Modify: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Test: `tests/test_impeller_v06_resources.py`

- [ ] **Step 1: Write failing V0.6 resource tests**

Create `tests/test_impeller_v06_resources.py`:

```python
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v06_bundle_loads_brep_export_contract():
    bundle = load_impeller_dsl_bundle("v0_6")

    assert bundle.schema["dsl_version"] == "0.6"
    assert "surface_graph_trimmed_brep" in bundle.export_contracts
    contract = bundle.export_contracts["surface_graph_trimmed_brep"]
    assert contract["mode"] == "surface_graph_brep"
    assert contract["step_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert contract["mesh_step_exactness"] == "surface_graph_mesh_step"


def test_v06_open_and_closed_runtime_presets_compile():
    open_runtime = compile_impeller_runtime_preset("radial_open_reference_v0_6")
    closed_runtime = compile_impeller_runtime_preset("radial_closed_reference_v0_6")

    assert open_runtime["version"] == "0.6.0"
    assert closed_runtime["version"] == "0.6.0"
    assert open_runtime["export_contract"]["mode"] == "surface_graph_brep"
    assert closed_runtime["export_contract"]["mode"] == "surface_graph_brep"
    assert open_runtime["parameters"]["blade_count"]["default"] == 12
    assert closed_runtime["parameters"]["blade_count"]["default"] == 12
    assert "root_fillet_radius_mm" in open_runtime["parameters"]
    assert "leading_edge_radius_mm" in open_runtime["parameters"]
    assert "trailing_edge_radius_mm" in open_runtime["parameters"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v06_resources.py -q
```

Expected: fail because `v0_6` resources are absent.

- [ ] **Step 3: Copy V0.5 resources into V0.6**

Run:

```powershell
Copy-Item -Recurse `
  src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_5 `
  src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_6
```

- [ ] **Step 4: Update V0.6 schema and aliases**

Edit `v0_6/schema.json`:

```json
{
  "dsl_version": "0.6",
  "supersedes": "../v0_5/schema.json",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "patch_naming_policy": "group_and_instance",
  "required_sections": [
    "classification",
    "coordinate_system",
    "design_space",
    "main_dimensions",
    "primary_flow_path",
    "support_surfaces",
    "blade_surface_model",
    "surface_graph_contract",
    "feature_graph_contract",
    "simulation_views",
    "export_contracts",
    "display_policy",
    "validation"
  ]
}
```

Edit `v0_6/aliases.json`:

```json
{
  "radial_open_reference_v0_6": "radial_open_reference_v0_6",
  "radial_closed_reference_v0_6": "radial_closed_reference_v0_6"
}
```

- [ ] **Step 5: Rename V0.6 presets and constructors**

In `v0_6/presets/radial_open_reference.json`, set:

```json
{
  "preset_id": "radial_open_reference_v0_6",
  "supersedes": "../../v0_5/presets/radial_open_reference.json",
  "display_name": "Radial open reference v0.6",
  "summary": "Open radial throughflow impeller with trimmed NURBS B-Rep STEP export, mesh inspection, and explicit fillet/blend controls.",
  "constructor_id": "axisymmetric_throughflow_radial_bladed.open.v0_6"
}
```

In `v0_6/presets/radial_closed_reference.json`, set:

```json
{
  "preset_id": "radial_closed_reference_v0_6",
  "supersedes": "../../v0_5/presets/radial_closed_reference.json",
  "display_name": "Radial closed reference v0.6",
  "summary": "Closed radial throughflow impeller with trimmed NURBS B-Rep STEP export, mesh inspection, and explicit fillet/blend controls.",
  "constructor_id": "axisymmetric_throughflow_radial_bladed.closed.v0_6"
}
```

In the copied constructor JSON files, set `dsl_version` to `0.6` and constructor ids to:

```text
axisymmetric_throughflow_radial_bladed.open.v0_6
axisymmetric_throughflow_radial_bladed.closed.v0_6
```

- [ ] **Step 6: Add V0.6 export contract**

Create `v0_6/export_contracts/surface_graph_trimmed_brep.json`:

```json
{
  "contract_id": "surface_graph_trimmed_brep",
  "mode": "surface_graph_brep",
  "default_view": "cad_review_360",
  "source": "geometry.surface_graph",
  "step_exactness": "surface_graph_trimmed_nurbs_step",
  "stl_exactness": "surface_graph_sampled_mesh",
  "mesh_step_exactness": "surface_graph_mesh_step",
  "step_writer": "occt_stepcontrol_writer",
  "default_output_directory": "Model Output",
  "required_face_region_fields": [
    "brep_face_id",
    "surface_graph_id",
    "feature_id",
    "role",
    "cad_surface_type"
  ],
  "forbidden_fallbacks": [
    "mesh_step_labeled_as_brep_step",
    "cadquery_proxy_solid_claimed_as_surface_graph_export",
    "placeholder_step"
  ]
}
```

In both V0.6 constructors, replace the V0.5 export contract reference with:

```json
"export_contracts": {
  "surface_graph_trimmed_brep": {
    "contract_ref": "export_contracts/surface_graph_trimmed_brep.json"
  }
}
```

- [ ] **Step 7: Extend runtime version loading**

In `src/part_rule_synthesis/impeller_runtime_compiler.py`, update:

```python
IMPELLER_DSL_VERSIONS = ("v0_2", "v0_3", "v0_4", "v0_5", "v0_6")
```

Add parameter limits:

```python
"leading_edge_radius_mm": {"min": 0.0, "max": 200.0},
"trailing_edge_radius_mm": {"min": 0.0, "max": 200.0},
"tip_edge_radius_mm": {"min": 0.0, "max": 200.0},
```

- [ ] **Step 8: Add fillet defaults to V0.6 presets**

Add these values to both V0.6 preset `parameter_values`:

```json
{
  "root_fillet_radius_mm": 8.0,
  "leading_edge_radius_mm": 3.0,
  "trailing_edge_radius_mm": 2.0,
  "tip_edge_radius_mm": 2.0
}
```

- [ ] **Step 9: Run V0.6 resource tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v06_resources.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit V0.6 resource line**

```powershell
git add tests/test_impeller_v06_resources.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6 src/part_rule_synthesis/impeller_runtime_compiler.py
git commit -m "feat: add impeller dsl v0.6 resources"
```

---

## Task 3: Add CAD Surface And Edge Payload Helpers

**Files:**

- Create: `src/part_rule_synthesis/impeller_cad_payload.py`
- Test: `tests/test_impeller_cad_payload.py`

- [ ] **Step 1: Write failing CAD payload tests**

Create `tests/test_impeller_cad_payload.py`:

```python
from part_rule_synthesis.impeller_cad_payload import (
    bspline_surface_payload_from_control_net,
    boundary_edge_payload,
    knot_values_and_multiplicities,
)


def test_knot_values_and_multiplicities_compacts_clamped_knots():
    values, multiplicities = knot_values_and_multiplicities([0, 0, 0, 0, 0.5, 1, 1, 1, 1])

    assert values == [0.0, 0.5, 1.0]
    assert multiplicities == [4, 1, 4]


def test_bspline_surface_payload_from_control_net():
    surface = {
        "id": "blade_0_pressure_surface",
        "role": "blade_pressure",
        "feature_id": "blade_00",
        "degree_u": 3,
        "degree_v": 3,
        "control_net": [
            [[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0]],
            [[1, 0, 0], [1, 1, 0.2], [1, 2, 0.2], [1, 3, 0]],
            [[2, 0, 0], [2, 1, 0.2], [2, 2, 0.2], [2, 3, 0]],
            [[3, 0, 0], [3, 1, 0], [3, 2, 0], [3, 3, 0]],
        ],
    }

    payload = bspline_surface_payload_from_control_net(surface)

    assert payload["surface_type"] == "bspline_surface"
    assert payload["degree_u"] == 3
    assert payload["degree_v"] == 3
    assert payload["control_points"][0][0] == [0.0, 0.0, 0.0]
    assert payload["weights"][0][0] == 1.0
    assert payload["knots_u"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    assert payload["knots_v"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]


def test_boundary_edge_payload_uses_bspline_curve_shape():
    edge = boundary_edge_payload(
        "blade_0_pressure_leading_edge",
        [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]],
        surface_uv={"blade_0_pressure_surface": [[0, 0], [0.33, 0], [0.66, 0], [1, 0]]},
    )

    assert edge["id"] == "blade_0_pressure_leading_edge"
    assert edge["cad_edge"]["curve_type"] == "bspline_curve"
    assert edge["cad_edge"]["degree"] == 3
    assert edge["cad_edge"]["surface_uv"]["blade_0_pressure_surface"]["control_points"][-1] == [1.0, 0.0]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_cad_payload.py -q
```

Expected: fail because `impeller_cad_payload.py` is absent.

- [ ] **Step 3: Implement CAD payload helpers**

Create `src/part_rule_synthesis/impeller_cad_payload.py`:

```python
from __future__ import annotations

from typing import Any


def knot_values_and_multiplicities(knots: list[float]) -> tuple[list[float], list[int]]:
    values: list[float] = []
    multiplicities: list[int] = []
    for raw in knots:
        value = round(float(raw), 9)
        if values and value == values[-1]:
            multiplicities[-1] += 1
        else:
            values.append(value)
            multiplicities.append(1)
    return values, multiplicities


def clamped_open_uniform_knots(point_count: int, degree: int) -> list[float]:
    interior_count = point_count - degree - 1
    interiors = [(index + 1) / (interior_count + 1) for index in range(max(0, interior_count))]
    return [0.0] * (degree + 1) + interiors + [1.0] * (degree + 1)


def bspline_surface_payload_from_control_net(surface: dict[str, Any]) -> dict[str, Any]:
    control_net = surface["control_net"]
    degree_u = int(surface.get("degree_u", 3))
    degree_v = int(surface.get("degree_v", 3))
    u_count = len(control_net)
    v_count = len(control_net[0])
    return {
        "surface_type": "bspline_surface",
        "degree_u": degree_u,
        "degree_v": degree_v,
        "control_points": [
            [[round(float(value), 6) for value in point] for point in row]
            for row in control_net
        ],
        "weights": [[1.0 for _ in range(v_count)] for _ in range(u_count)],
        "knots_u": clamped_open_uniform_knots(u_count, degree_u),
        "knots_v": clamped_open_uniform_knots(v_count, degree_v),
        "trim_loops": [{"orientation": "outer", "edges": []}],
        "source": "surface_graph.control_net",
    }


def boundary_edge_payload(
    edge_id: str,
    points: list[list[float]],
    surface_uv: dict[str, list[list[float]]] | None = None,
) -> dict[str, Any]:
    degree = min(3, len(points) - 1)
    knots = clamped_open_uniform_knots(len(points), degree)
    return {
        "id": edge_id,
        "cad_edge": {
            "curve_type": "bspline_curve",
            "degree": degree,
            "control_points": [[round(float(value), 6) for value in point] for point in points],
            "weights": [1.0 for _ in points],
            "knots": knots,
            "surface_uv": {
                surface_id: {
                    "curve_type": "pcurve",
                    "control_points": [[round(float(value), 6) for value in point] for point in uv_points],
                }
                for surface_id, uv_points in (surface_uv or {}).items()
            },
        },
    }
```

- [ ] **Step 4: Run CAD payload tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_cad_payload.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit CAD payload helpers**

```powershell
git add src/part_rule_synthesis/impeller_cad_payload.py tests/test_impeller_cad_payload.py
git commit -m "feat: add impeller cad payload helpers"
```

---

## Task 4: Add Minimal B-Rep STEP Exporter

**Files:**

- Create: `src/part_rule_synthesis/impeller_brep_export.py`
- Modify: `src/part_rule_synthesis/occt_compat.py`
- Test: `tests/test_impeller_brep_export.py`

- [ ] **Step 1: Write failing B-Rep exporter tests**

Create `tests/test_impeller_brep_export.py`:

```python
from pathlib import Path

import pytest

from part_rule_synthesis.impeller_brep_export import write_trimmed_brep_step


def test_write_trimmed_brep_step_exports_bspline_face(tmp_path: Path):
    step_path = tmp_path / "brep.step"

    manifest = write_trimmed_brep_step(step_path, "impeller", _single_bspline_surface_graph())
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert manifest["source"] == "surface_graph"
    assert manifest["export_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert manifest["step_writer"] == "occt_stepcontrol_writer"
    assert manifest["brep_face_count"] == 1
    assert manifest["face_regions"] == [
        {
            "brep_face_id": "face_0000",
            "surface_graph_id": "surface_0",
            "feature_id": "blade_00",
            "role": "blade_pressure",
            "cad_surface_type": "bspline_surface",
        }
    ]
    assert "B_SPLINE_SURFACE" in text
    assert "ADVANCED_FACE" in text
    assert "TRIANGULATED_FACE_SET" not in text


def test_write_trimmed_brep_step_rejects_missing_cad_surface(tmp_path: Path):
    step_path = tmp_path / "missing.step"
    graph = {"surfaces": [{"id": "surface_0", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]}]}

    with pytest.raises(ValueError, match="surface_0 missing cad_surface"):
        write_trimmed_brep_step(step_path, "impeller", graph)

    assert not step_path.exists()


def _single_bspline_surface_graph():
    control_points = [
        [[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0]],
        [[1, 0, 0], [1, 1, 0.2], [1, 2, 0.2], [1, 3, 0]],
        [[2, 0, 0], [2, 1, 0.2], [2, 2, 0.2], [2, 3, 0]],
        [[3, 0, 0], [3, 1, 0], [3, 2, 0], [3, 3, 0]],
    ]
    return {
        "surfaces": [
            {
                "id": "surface_0",
                "feature_id": "blade_00",
                "role": "blade_pressure",
                "cad_surface": {
                    "surface_type": "bspline_surface",
                    "degree_u": 3,
                    "degree_v": 3,
                    "control_points": control_points,
                    "weights": [[1, 1, 1, 1] for _ in range(4)],
                    "knots_u": [0, 0, 0, 0, 1, 1, 1, 1],
                    "knots_v": [0, 0, 0, 0, 1, 1, 1, 1],
                    "trim_loops": [{"orientation": "outer", "edges": []}],
                },
            }
        ],
        "edges": [],
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_brep_export.py -q
```

Expected: fail because `impeller_brep_export.py` is absent.

- [ ] **Step 3: Move reusable OCP array helpers into `occt_compat.py`**

Add these helpers to `src/part_rule_synthesis/occt_compat.py`:

```python
def real_array(values: list[float]):
    from OCP.TColStd import TColStd_Array1OfReal

    result = TColStd_Array1OfReal(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, float(value))
    return result


def int_array(values: list[int]):
    from OCP.TColStd import TColStd_Array1OfInteger

    result = TColStd_Array1OfInteger(1, len(values))
    for index, value in enumerate(values, start=1):
        result.SetValue(index, int(value))
    return result
```

Keep the existing private helpers or replace their uses with the public helpers.

- [ ] **Step 4: Implement minimal B-Rep exporter**

Create `src/part_rule_synthesis/impeller_brep_export.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from part_rule_synthesis.impeller_cad_payload import knot_values_and_multiplicities
from part_rule_synthesis.occt_compat import int_array, real_array


def write_trimmed_brep_step(
    step_path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)

    face_regions: list[dict[str, Any]] = []
    for surface in surface_graph.get("surfaces", []):
        cad_surface = surface.get("cad_surface")
        surface_id = str(surface.get("id") or surface.get("surface_graph_id") or "")
        if cad_surface is None:
            raise ValueError(f"{surface_id} missing cad_surface")
        face = _face_from_cad_surface(cad_surface)
        brep_face_id = f"face_{len(face_regions):04d}"
        builder.Add(compound, face)
        face_regions.append(
            {
                "brep_face_id": brep_face_id,
                "surface_graph_id": surface_id,
                "feature_id": str(surface.get("feature_id") or ""),
                "role": str(surface.get("role") or surface.get("cfd_role") or ""),
                "cad_surface_type": str(cad_surface.get("surface_type") or ""),
            }
        )

    if not face_regions:
        raise ValueError("surface graph brep export produced no faces")

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    writer.Transfer(compound, STEPControl_AsIs)
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP write failed with status {status}")

    return {
        "source": "surface_graph",
        "view": view_id,
        "solid_name": solid_name,
        "export_exactness": "surface_graph_trimmed_nurbs_step",
        "step_writer": "occt_stepcontrol_writer",
        "brep_face_count": len(face_regions),
        "shell_count": 0,
        "sewing_status": "not_attempted",
        "face_regions": face_regions,
        "limitations": ["initial_faces_are_unsewn"],
    }


def _face_from_cad_surface(cad_surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

    if cad_surface.get("surface_type") != "bspline_surface":
        raise ValueError(f"unsupported cad_surface type: {cad_surface.get('surface_type')}")
    surface = _bspline_surface(cad_surface)
    return BRepBuilderAPI_MakeFace(surface, 1.0e-6).Face()


def _bspline_surface(cad_surface: dict[str, Any]):
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt

    points = cad_surface["control_points"]
    u_count = len(points)
    v_count = len(points[0])
    poles = TColgp_Array2OfPnt(1, u_count, 1, v_count)
    for u_index, row in enumerate(points, start=1):
        for v_index, point in enumerate(row, start=1):
            poles.SetValue(u_index, v_index, gp_Pnt(float(point[0]), float(point[1]), float(point[2])))

    u_values, u_mults = knot_values_and_multiplicities(cad_surface["knots_u"])
    v_values, v_mults = knot_values_and_multiplicities(cad_surface["knots_v"])
    return Geom_BSplineSurface(
        poles,
        real_array(u_values),
        real_array(v_values),
        int_array(u_mults),
        int_array(v_mults),
        int(cad_surface["degree_u"]),
        int(cad_surface["degree_v"]),
        False,
        False,
    )
```

- [ ] **Step 5: Run B-Rep exporter tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_occt_compat.py tests/test_impeller_cad_payload.py tests/test_impeller_brep_export.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit minimal B-Rep exporter**

```powershell
git add src/part_rule_synthesis/occt_compat.py src/part_rule_synthesis/impeller_brep_export.py tests/test_impeller_brep_export.py
git commit -m "feat: add trimmed brep step exporter"
```

---

## Task 5: Add `cad_surface` Payloads To Generated Surface Graphs

**Files:**

- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `src/part_rule_synthesis/impeller_cad_payload.py`
- Test: `tests/test_impeller_kernel.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing kernel payload test**

Append to `tests/test_impeller_kernel.py`:

```python
def test_v06_surface_graph_emits_cad_surface_payloads():
    from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
    from part_rule_synthesis.service import _bind_parameters, _geometry_metadata

    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_6")
    parameters = _bind_parameters(runtime, {})
    geometry = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}

    pressure = surfaces["blade_0_pressure_surface"]
    hub = surfaces["hub_revolve_surface"]
    bottom = surfaces["inner_hub_bottom_face"]

    assert pressure["cad_surface"]["surface_type"] == "bspline_surface"
    assert pressure["cad_surface"]["degree_u"] == 3
    assert pressure["cad_surface"]["degree_v"] == 3
    assert hub["cad_surface"]["surface_type"] in {"bspline_surface", "revolved_bspline_surface"}
    assert bottom["cad_surface"]["surface_type"] == "plane"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v06_surface_graph_emits_cad_surface_payloads -q
```

Expected: fail because surfaces do not include `cad_surface`.

- [ ] **Step 3: Add analytic plane and cylinder payload helpers**

Add to `src/part_rule_synthesis/impeller_cad_payload.py`:

```python
def plane_surface_payload(origin: list[float], normal: list[float], u_dir: list[float], v_dir: list[float]) -> dict[str, Any]:
    return {
        "surface_type": "plane",
        "origin": [round(float(value), 6) for value in origin],
        "normal": [round(float(value), 6) for value in normal],
        "u_dir": [round(float(value), 6) for value in u_dir],
        "v_dir": [round(float(value), 6) for value in v_dir],
        "trim_loops": [{"orientation": "outer", "edges": []}],
    }


def cylinder_surface_payload(radius: float, z_min: float, z_max: float) -> dict[str, Any]:
    return {
        "surface_type": "cylinder",
        "radius_mm": round(float(radius), 6),
        "z_min_mm": round(float(z_min), 6),
        "z_max_mm": round(float(z_max), 6),
        "axis": "z",
        "trim_loops": [{"orientation": "outer", "edges": []}],
    }
```

- [ ] **Step 4: Attach B-spline payloads to NURBS-like graph surfaces**

In `axisymmetric_throughflow_nurbs.py`, import:

```python
from part_rule_synthesis.impeller_cad_payload import (
    bspline_surface_payload_from_control_net,
    cylinder_surface_payload,
    plane_surface_payload,
)
```

When creating blade pressure, suction, and closure surfaces that already have `control_net`, add:

```python
"cad_surface": bspline_surface_payload_from_control_net({
    "control_net": _control_net_from_grid(blade["pressure_surface"]),
    "degree_u": 3,
    "degree_v": 3,
}),
```

Use the corresponding grid for suction and closure surfaces.

- [ ] **Step 5: Attach analytic payloads to hub faces and bore**

For `inner_hub_bottom_face` and `hub_top_cap_face`, add:

```python
"cad_surface": plane_surface_payload([0.0, 0.0, z_value], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]),
```

For `mounting_bore_cylinder`, add:

```python
"cad_surface": cylinder_surface_payload(bore_radius, bottom[1], top[1]),
```

For hub and shroud revolve surfaces in the first implementation, attach a B-spline payload from `control_net`. Record source as sampled support:

```python
payload = bspline_surface_payload_from_control_net(surface)
payload["source"] = "surface_graph.control_net_revolved_profile_sample"
```

- [ ] **Step 6: Run kernel payload test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v06_surface_graph_emits_cad_surface_payloads -q
```

Expected: pass.

- [ ] **Step 7: Commit CAD payload integration**

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py src/part_rule_synthesis/impeller_cad_payload.py tests/test_impeller_kernel.py
git commit -m "feat: emit cad surface payloads for v0.6"
```

---

## Task 6: Support Analytic Plane/Cylinder And Trimmed Wires In B-Rep Export

**Files:**

- Modify: `src/part_rule_synthesis/impeller_brep_export.py`
- Test: `tests/test_impeller_brep_export.py`

- [ ] **Step 1: Add failing tests for analytic surfaces and mesh fallback prevention**

Append to `tests/test_impeller_brep_export.py`:

```python
def test_brep_step_rejects_mesh_step_label(tmp_path: Path):
    step_path = tmp_path / "bad.step"
    graph = _single_bspline_surface_graph()
    graph["surfaces"][0]["cad_surface"]["surface_type"] = "triangulated_mesh"

    with pytest.raises(ValueError, match="unsupported cad_surface type: triangulated_mesh"):
        write_trimmed_brep_step(step_path, "impeller", graph)


def test_brep_step_exports_plane_and_cylinder_faces(tmp_path: Path):
    step_path = tmp_path / "analytic.step"
    graph = {
        "surfaces": [
            {
                "id": "bottom_face",
                "feature_id": "hub",
                "role": "inner_hub_bottom",
                "cad_surface": {
                    "surface_type": "plane",
                    "origin": [0, 0, 0],
                    "normal": [0, 0, 1],
                    "u_dir": [1, 0, 0],
                    "v_dir": [0, 1, 0],
                    "trim_loops": [{"orientation": "outer", "edges": []}],
                },
            },
            {
                "id": "bore",
                "feature_id": "hub.bore",
                "role": "mounting_bore",
                "cad_surface": {
                    "surface_type": "cylinder",
                    "radius_mm": 40,
                    "z_min_mm": 0,
                    "z_max_mm": 120,
                    "axis": "z",
                    "trim_loops": [{"orientation": "outer", "edges": []}],
                },
            },
        ],
        "edges": [],
    }

    manifest = write_trimmed_brep_step(step_path, "impeller", graph)
    text = step_path.read_text(encoding="utf-8", errors="ignore")

    assert manifest["brep_face_count"] == 2
    assert "PLANE" in text
    assert "CYLINDRICAL_SURFACE" in text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_brep_export.py -q
```

Expected: analytic surface test fails.

- [ ] **Step 3: Implement plane and cylinder face creation**

In `impeller_brep_export.py`, extend `_face_from_cad_surface`:

```python
def _face_from_cad_surface(cad_surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_CylindricalSurface, Geom_Plane
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    surface_type = cad_surface.get("surface_type")
    if surface_type == "bspline_surface":
        return BRepBuilderAPI_MakeFace(_bspline_surface(cad_surface), 1.0e-6).Face()
    if surface_type == "plane":
        origin = cad_surface["origin"]
        normal = cad_surface["normal"]
        plane = Geom_Plane(gp_Pnt(*[float(value) for value in origin]), gp_Dir(*[float(value) for value in normal]))
        return BRepBuilderAPI_MakeFace(plane, -10000.0, 10000.0, -10000.0, 10000.0, 1.0e-6).Face()
    if surface_type == "cylinder":
        radius = float(cad_surface["radius_mm"])
        z_min = float(cad_surface["z_min_mm"])
        z_max = float(cad_surface["z_max_mm"])
        cylinder = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)), radius)
        return BRepBuilderAPI_MakeFace(cylinder, 0.0, 6.283185307179586, z_min, z_max, 1.0e-6).Face()
    raise ValueError(f"unsupported cad_surface type: {surface_type}")
```

- [ ] **Step 4: Run B-Rep exporter tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_brep_export.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit analytic surface export**

```powershell
git add src/part_rule_synthesis/impeller_brep_export.py tests/test_impeller_brep_export.py
git commit -m "feat: export analytic brep support surfaces"
```

---

## Task 7: Integrate V0.6 Export Routing And `Model Output`

**Files:**

- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/api.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing workflow test for V0.6 exports**

Append to `tests/test_workflow.py`:

```python
def test_impeller_v06_exports_brep_step_and_model_output_files(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_6")

    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["dsl_version"] == "0.6"
    assert manifest["export_strategy"]["mode"] == "surface_graph_brep"
    assert manifest["export_manifests"]["step"]["export_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert manifest["export_manifests"]["mesh_step"]["export_exactness"] == "surface_graph_mesh_step"
    assert manifest["export_manifests"]["stl"]["export_exactness"] == "surface_graph_sampled_mesh"

    step_path = Path(manifest["exports"]["step"])
    stl_path = Path(manifest["exports"]["stl"])
    mesh_step_path = Path(manifest["exports"]["mesh_step"])
    manifest_copy = Path(manifest["exports"]["manifest"])

    assert step_path.parent.name == "Model Output"
    assert step_path.suffix == ".step"
    assert stl_path.suffix == ".stl"
    assert mesh_step_path.name.endswith(".mesh.step")
    assert manifest_copy.name.endswith(".manifest.json")
    assert step_path.exists()
    assert stl_path.exists()
    assert mesh_step_path.exists()
    assert manifest_copy.exists()

    step_text = step_path.read_text(encoding="utf-8", errors="ignore")
    assert "ADVANCED_FACE" in step_text
    assert "TRIANGULATED_FACE_SET" not in step_text
```

- [ ] **Step 2: Run workflow test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v06_exports_brep_step_and_model_output_files -q
```

Expected: fail because V0.6 service routing is absent.

- [ ] **Step 3: Add output path helper in `service.py`**

Add:

```python
def _model_output_dir(root: Path) -> Path:
    output_dir = root.parent / "Model Output" if root.name == "model_runs" else Path.cwd() / "Model Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _safe_export_stem(preset_id: str | None, run_id: str) -> str:
    raw = f"{preset_id or 'impeller'}_{run_id}"
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in raw)
```

If the service root is a temp test directory, ensure `Model Output` stays under that temp tree:

```python
def _model_output_dir_for_run(run_dir: Path) -> Path:
    output_dir = run_dir.parent.parent / "Model Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
```

- [ ] **Step 4: Route V0.6 B-Rep exports**

In `_write_exports`, detect:

```python
if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_brep":
```

Then write:

```python
output_dir = _model_output_dir_for_run(run_dir)
stem = _safe_export_stem((dsl_context or {}).get("preset_id"), run_dir.name)
step = output_dir / f"{stem}.step"
stl = output_dir / f"{stem}.stl"
mesh_step = output_dir / f"{stem}.mesh.step"
manifest_copy = output_dir / f"{stem}.manifest.json"
```

Call:

```python
brep_manifest = write_trimmed_brep_step(step, part_family, surface_graph, view_id=export_contract.get("default_view", "cad_review_360"))
mesh_manifests = write_surface_graph_exports(mesh_step, stl, part_family, surface_graph, view_id=export_contract.get("default_view", "cad_review_360"))
```

Return:

```python
return (
    {"step": str(step), "stl": str(stl), "mesh_step": str(mesh_step), "manifest": str(manifest_copy)},
    {"step": brep_manifest, "stl": mesh_manifests["stl"], "mesh_step": mesh_manifests["step"]},
)
```

After manifest creation, write `manifest_copy` with the final manifest JSON.

- [ ] **Step 5: Update API export formats**

In `api.py`, allow `step`, `stl`, `mesh_step`, and `manifest`. Add filename selection:

```python
filename = Path(path).name
return FileResponse(path, filename=filename)
```

Keep existing `/exports/step` and `/exports/stl` working.

- [ ] **Step 6: Run V0.6 export workflow test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v06_exports_brep_step_and_model_output_files -q
```

Expected: pass.

- [ ] **Step 7: Commit service export routing**

```powershell
git add src/part_rule_synthesis/service.py src/part_rule_synthesis/api.py tests/test_workflow.py
git commit -m "feat: route v0.6 brep exports to model output"
```

---

## Task 8: Add Mesh Manifest Metrics

**Files:**

- Create: `src/part_rule_synthesis/impeller_mesh_manifest.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_mesh_manifest.py`

- [ ] **Step 1: Write failing mesh manifest tests**

Create `tests/test_impeller_mesh_manifest.py`:

```python
from part_rule_synthesis.impeller_mesh_manifest import build_surface_mesh_manifest


def test_mesh_manifest_reports_triangle_quality_and_edges():
    surface_graph = {
        "surfaces": [
            {
                "id": "quad",
                "role": "blade_pressure",
                "feature_id": "blade_00",
                "uv_grid": [
                    [[0, 0, 0], [0, 1, 0]],
                    [[1, 0, 0], [1, 1, 0]],
                ],
            }
        ]
    }

    manifest = build_surface_mesh_manifest(surface_graph, view_id="cfd_full_360")

    assert manifest["source"] == "surface_graph"
    assert manifest["mesh_type"] == "surface_triangles"
    assert manifest["triangle_count"] == 2
    assert manifest["degenerate_triangle_count"] == 0
    assert manifest["quality_metrics"]["min_area"] > 0
    assert manifest["quality_metrics"]["max_aspect_ratio"] >= 1
    assert manifest["patch_regions"][0]["surface_graph_id"] == "quad"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_mesh_manifest.py -q
```

Expected: fail because `impeller_mesh_manifest.py` is absent.

- [ ] **Step 3: Implement mesh manifest using existing triangulation**

Create `src/part_rule_synthesis/impeller_mesh_manifest.py`:

```python
from __future__ import annotations

import math
from typing import Any

from part_rule_synthesis.impeller_surface_graph_export import triangulate_surface_graph


def build_surface_mesh_manifest(surface_graph: dict[str, Any], view_id: str = "cfd_full_360") -> dict[str, Any]:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
    areas = [_triangle_area(triangle["points"]) for triangle in triangulation["triangles"]]
    aspect_ratios = [_triangle_aspect_ratio(triangle["points"]) for triangle in triangulation["triangles"]]
    return {
        "source": "surface_graph",
        "view": view_id,
        "mesh_type": "surface_triangles",
        "triangle_count": triangulation["triangle_count"],
        "degenerate_triangle_count": triangulation["skipped_triangle_count"],
        "quality_metrics": {
            "min_area": round(min(areas), 9) if areas else 0.0,
            "max_area": round(max(areas), 9) if areas else 0.0,
            "max_aspect_ratio": round(max(aspect_ratios), 6) if aspect_ratios else 0.0,
        },
        "patch_regions": [
            {
                "surface_graph_id": region["surface_graph_id"],
                "feature_id": region["feature_id"],
                "role": region["role"],
                "triangle_start": region["triangle_start"],
                "triangle_count": region["triangle_count"],
            }
            for region in triangulation["triangle_regions"]
        ],
    }


def _triangle_area(points: list[list[float]]) -> float:
    a, b, c = points
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    return 0.5 * math.sqrt(sum(value * value for value in cross))


def _triangle_aspect_ratio(points: list[list[float]]) -> float:
    lengths = []
    for left, right in [(0, 1), (1, 2), (2, 0)]:
        dx = points[left][0] - points[right][0]
        dy = points[left][1] - points[right][1]
        dz = points[left][2] - points[right][2]
        lengths.append(math.sqrt(dx * dx + dy * dy + dz * dz))
    shortest = max(min(lengths), 1.0e-12)
    return max(lengths) / shortest
```

- [ ] **Step 4: Attach mesh manifest to service manifest**

In `service.py`, after CFD manifest generation for V0.6, add:

```python
if dsl["part_family"] == "impeller" and _dsl_version(dsl) == "0.6":
    simulation_manifests["cfd_surface_mesh"] = build_surface_mesh_manifest(
        geometry_metadata.get("surface_graph", {}),
        view_id="cfd_full_360",
    )
```

Import:

```python
from part_rule_synthesis.impeller_mesh_manifest import build_surface_mesh_manifest
```

- [ ] **Step 5: Run mesh manifest tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_mesh_manifest.py -q
```

Expected: pass.

- [ ] **Step 6: Commit mesh manifest**

```powershell
git add src/part_rule_synthesis/impeller_mesh_manifest.py src/part_rule_synthesis/service.py tests/test_impeller_mesh_manifest.py
git commit -m "feat: add cfd surface mesh manifest"
```

---

## Task 9: Add Explicit Fillet And Blend Geometry

**Files:**

- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: V0.6 constructor and preset JSON files
- Test: `tests/test_impeller_kernel.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Add failing fillet tests**

Append to `tests/test_impeller_kernel.py`:

```python
def test_v06_root_and_edge_fillets_are_explicit_design_surfaces():
    from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
    from part_rule_synthesis.service import RuleSynthesisService
    from pathlib import Path
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_6")
        run = service.instantiate(engine.engine_id, {"root_fillet_radius_mm": 10.0})

    surfaces = {surface["id"]: surface for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]}
    root = surfaces["blade_0_root_fillet_surface"]
    leading = surfaces["blade_0_leading_edge_fillet_surface"]
    trailing = surfaces["blade_0_trailing_edge_fillet_surface"]

    assert root["role"] == "blade_root_fillet"
    assert root["radius_mm"] == 10.0
    assert root["cad_surface"]["surface_type"] == "bspline_surface"
    assert leading["role"] == "blade_leading_edge_fillet"
    assert trailing["role"] == "blade_trailing_edge_fillet"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v06_root_and_edge_fillets_are_explicit_design_surfaces -q
```

Expected: fail because current surfaces use closure roles, not explicit fillet roles.

- [ ] **Step 3: Add V0.6 feature graph entries**

In both V0.6 constructors, add feature graph nodes:

```json
"blend_features": {
  "root_fillet": {
    "kind": "variable_radius_blend_surface",
    "parameters": ["root_fillet_radius_mm"],
    "cfd_patch_group": "root_fillet_wall"
  },
  "leading_edge_round": {
    "kind": "rounded_edge_blend_surface",
    "parameters": ["leading_edge_radius_mm"],
    "cfd_patch_group": "leading_edge_wall"
  },
  "trailing_edge_round": {
    "kind": "rounded_edge_blend_surface",
    "parameters": ["trailing_edge_radius_mm"],
    "cfd_patch_group": "trailing_edge_wall"
  },
  "tip_edge_round": {
    "kind": "rounded_edge_blend_surface",
    "parameters": ["tip_edge_radius_mm"],
    "cfd_patch_group": "tip_fillet_wall"
  }
}
```

- [ ] **Step 4: Rename V0.6 root/edge closure roles to fillet roles**

In the kernel surface creation path, when `_dsl_version` or runtime context is V0.6, emit:

```python
"id": f"{prefix}_root_fillet_surface",
"kind": "blend_surface",
"role": "blade_root_fillet",
"cfd_role": "root_transition",
"radius_mm": _round(params["root_fillet_radius_mm"]),
```

For leading and trailing:

```python
"id": f"{prefix}_leading_edge_fillet_surface",
"role": "blade_leading_edge_fillet",
"radius_mm": _round(params["leading_edge_radius_mm"]),
```

```python
"id": f"{prefix}_trailing_edge_fillet_surface",
"role": "blade_trailing_edge_fillet",
"radius_mm": _round(params["trailing_edge_radius_mm"]),
```

For the first V0.6 implementation, the geometry may remain a ruled/blend sample grid, but it must be named, parameterized, and exported as a NURBS support surface through `cad_surface`.

- [ ] **Step 5: Add feasibility checks for fillet radius**

Add a validation check:

```python
def _check_fillet_radius_feasible(params: dict[str, float]) -> dict[str, Any]:
    limit = max(params["blade_thickness_mm"] * 0.75, 1.0)
    requested = max(
        params.get("root_fillet_radius_mm", 0.0),
        params.get("leading_edge_radius_mm", 0.0),
        params.get("trailing_edge_radius_mm", 0.0),
    )
    return {
        "name": "fillet_radius_within_local_thickness_bounds",
        "status": "PASS" if requested <= limit else "FAIL",
        "limit_mm": _round(limit),
        "requested_max_mm": _round(requested),
    }
```

Include it in validity reports for V0.6.

- [ ] **Step 6: Run fillet tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v06_root_and_edge_fillets_are_explicit_design_surfaces -q
```

Expected: pass.

- [ ] **Step 7: Commit explicit fillet surfaces**

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6 tests/test_impeller_kernel.py
git commit -m "feat: add v0.6 explicit fillet surfaces"
```

---

## Task 10: Frontend Export Selector And Filenames

**Files:**

- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/apiClient.js`
- Modify: `frontend/src/App.js`
- Test: `frontend/src/appModel.test.js`

- [ ] **Step 1: Write failing frontend export option tests**

Append to `frontend/src/appModel.test.js`:

```javascript
import { exportFileOptions, exportFilename } from "./appModel.js";

test("exportFileOptions exposes brep mesh and manifest downloads", () => {
  assert.deepEqual(exportFileOptions.map((option) => option.id), ["step", "stl", "mesh_step", "manifest"]);
  assert.equal(exportFileOptions.find((option) => option.id === "step").label, "STEP B-Rep");
  assert.equal(exportFileOptions.find((option) => option.id === "mesh_step").extension, ".mesh.step");
});

test("exportFilename uses preset run id and correct extension", () => {
  assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "step"), "radial_open_reference_v0_6_run-abc.step");
  assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "mesh_step"), "radial_open_reference_v0_6_run-abc.mesh.step");
  assert.equal(exportFilename("radial_open_reference_v0_6", "run-abc", "manifest"), "radial_open_reference_v0_6_run-abc.manifest.json");
});
```

- [ ] **Step 2: Run frontend test to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js
```

Expected: fail because `exportFileOptions` and `exportFilename` are absent.

- [ ] **Step 3: Add export option helpers**

In `frontend/src/appModel.js`, add:

```javascript
export const exportFileOptions = [
  { id: "step", label: "STEP B-Rep", extension: ".step" },
  { id: "stl", label: "STL Mesh", extension: ".stl" },
  { id: "mesh_step", label: "STEP Mesh", extension: ".mesh.step" },
  { id: "manifest", label: "Manifest", extension: ".manifest.json" },
];

export function exportFilename(presetId, runId, exportKind) {
  const option = exportFileOptions.find((item) => item.id === exportKind) || exportFileOptions[0];
  const safePreset = String(presetId || "impeller").replace(/[^A-Za-z0-9_-]/g, "_");
  const safeRun = String(runId || "run").replace(/[^A-Za-z0-9_-]/g, "_");
  return `${safePreset}_${safeRun}${option.extension}`;
}
```

- [ ] **Step 4: Update UI download controls**

In `frontend/src/App.js`, replace separate hard-coded STL/STEP buttons with a mapped control:

```javascript
exportFileOptions.map((option) =>
  h("a", {
    key: option.id,
    className: "button",
    href: exportUrl(apiBase, run.run_id, option.id),
    download: exportFilename(selectedPresetState.presetId, run.run_id, option.id),
  }, option.label),
)
```

Keep existing button styling.

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all frontend tests pass.

- [ ] **Step 6: Commit export selector**

```powershell
git add frontend/src/appModel.js frontend/src/apiClient.js frontend/src/App.js frontend/src/appModel.test.js
git commit -m "feat: add export file type selector"
```

---

## Task 11: Frontend CFD360 Mesh View

**Files:**

- Create: `frontend/src/meshViewModel.js`
- Create: `frontend/src/meshViewModel.test.js`
- Create: `frontend/src/components/MeshInspectionPanel.js`
- Modify: `frontend/src/simulationViewModel.js`
- Modify: `frontend/src/components/CfdManifestPanel.js`
- Modify: `frontend/src/components/ModelViewer.js`

- [ ] **Step 1: Write failing mesh view model tests**

Create `frontend/src/meshViewModel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { meshQualitySummary, meshViewModes } from "./meshViewModel.js";

describe("mesh view model", () => {
  test("meshViewModes includes surface mesh inspection", () => {
    assert.deepEqual(meshViewModes.map((mode) => mode.id), ["patches", "mesh", "quality"]);
  });

  test("meshQualitySummary formats mesh manifest metrics", () => {
    const summary = meshQualitySummary({
      triangle_count: 12,
      degenerate_triangle_count: 1,
      quality_metrics: { min_area: 0.25, max_area: 4, max_aspect_ratio: 8.5 },
    });

    assert.deepEqual(summary, {
      triangleCount: 12,
      degenerateTriangleCount: 1,
      minArea: 0.25,
      maxArea: 4,
      maxAspectRatio: 8.5,
    });
  });
});
```

- [ ] **Step 2: Run frontend mesh tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- meshViewModel.test.js
```

Expected: fail because `meshViewModel.js` is absent.

- [ ] **Step 3: Implement mesh view model**

Create `frontend/src/meshViewModel.js`:

```javascript
export const meshViewModes = [
  { id: "patches", label: "Patch view" },
  { id: "mesh", label: "Mesh view" },
  { id: "quality", label: "Quality overlay" },
];

export function meshQualitySummary(meshManifest = {}) {
  const metrics = meshManifest.quality_metrics || {};
  return {
    triangleCount: Number(meshManifest.triangle_count || 0),
    degenerateTriangleCount: Number(meshManifest.degenerate_triangle_count || 0),
    minArea: Number(metrics.min_area || 0),
    maxArea: Number(metrics.max_area || 0),
    maxAspectRatio: Number(metrics.max_aspect_ratio || 0),
  };
}
```

- [ ] **Step 4: Add MeshInspectionPanel**

Create `frontend/src/components/MeshInspectionPanel.js`:

```javascript
import { h } from "../vendor/preact.js";
import { meshQualitySummary } from "../meshViewModel.js";

export function MeshInspectionPanel({ meshManifest }) {
  const summary = meshQualitySummary(meshManifest);
  return h("section", { className: "panel-section" }, [
    h("h3", { key: "title" }, "CFD360 Mesh"),
    h("dl", { key: "metrics", className: "metric-grid" }, [
      h("dt", { key: "tri-label" }, "Triangles"),
      h("dd", { key: "tri-value" }, String(summary.triangleCount)),
      h("dt", { key: "deg-label" }, "Degenerate"),
      h("dd", { key: "deg-value" }, String(summary.degenerateTriangleCount)),
      h("dt", { key: "aspect-label" }, "Max aspect"),
      h("dd", { key: "aspect-value" }, String(summary.maxAspectRatio)),
    ]),
  ]);
}
```

- [ ] **Step 5: Wire CFD360 mesh view into panels and viewer**

In `simulationViewModel.js`, add a CFD subview id `mesh`.

In `CfdManifestPanel.js`, render `MeshInspectionPanel` when `manifest.simulation_manifests.cfd_surface_mesh` exists.

In `ModelViewer.js`, when active view is CFD360 mesh mode, render triangle wire overlay using existing graph triangulation logic and color by `patch_regions`.

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all frontend tests pass.

- [ ] **Step 7: Commit mesh view**

```powershell
git add frontend/src/meshViewModel.js frontend/src/meshViewModel.test.js frontend/src/components/MeshInspectionPanel.js frontend/src/simulationViewModel.js frontend/src/components/CfdManifestPanel.js frontend/src/components/ModelViewer.js
git commit -m "feat: add cfd360 mesh inspection view"
```

---

## Task 12: Frontend Fillet Controls

**Files:**

- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`
- Modify: `frontend/src/components/ParameterPanel.js` or the current parameter panel location in `frontend/src/App.js`

- [ ] **Step 1: Add failing frontend parameter tests**

Append to `frontend/src/appModel.test.js`:

```javascript
test("v0.6 exposes interactive fillet and edge radius controls", () => {
  assert.equal(parameterSchema.root_fillet_radius_mm.group, "edge_treatment");
  assert.equal(parameterSchema.leading_edge_radius_mm.group, "edge_treatment");
  assert.equal(parameterSchema.trailing_edge_radius_mm.group, "edge_treatment");
  assert.equal(parameterSchema.tip_edge_radius_mm.group, "edge_treatment");

  const payload = buildInstantiatePayload({
    root_fillet_radius_mm: 10,
    leading_edge_radius_mm: 4,
    trailing_edge_radius_mm: 2.5,
    tip_edge_radius_mm: 2,
  });

  assert.equal(payload.parameters.root_fillet_radius_mm, 10);
  assert.equal(payload.parameters.leading_edge_radius_mm, 4);
  assert.equal(payload.parameters.trailing_edge_radius_mm, 2.5);
  assert.equal(payload.parameters.tip_edge_radius_mm, 2);
});
```

- [ ] **Step 2: Run frontend test to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- appModel.test.js
```

Expected: fail because new radius controls are absent or incomplete.

- [ ] **Step 3: Add parameter schema entries**

In `frontend/src/appModel.js`, add:

```javascript
leading_edge_radius_mm: { label: "Leading edge radius", unit: "mm", step: 0.5, default: 3, group: "edge_treatment" },
trailing_edge_radius_mm: { label: "Trailing edge radius", unit: "mm", step: 0.5, default: 2, group: "edge_treatment" },
tip_edge_radius_mm: { label: "Tip edge radius", unit: "mm", step: 0.5, default: 2, group: "edge_treatment" },
```

Ensure `root_fillet_radius_mm` remains in `edge_treatment`.

- [ ] **Step 4: Update V0.6 frontend presets**

Change frontend preset ids to:

```javascript
presetId: "radial_open_reference_v0_6"
presetId: "radial_closed_reference_v0_6"
```

Add V0.6 parameter defaults to each preset:

```javascript
root_fillet_radius_mm: 8,
leading_edge_radius_mm: 3,
trailing_edge_radius_mm: 2,
tip_edge_radius_mm: 2,
```

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected: all frontend tests pass.

- [ ] **Step 6: Commit fillet controls**

```powershell
git add frontend/src/appModel.js frontend/src/appModel.test.js frontend/src/App.js
git commit -m "feat: expose v0.6 fillet controls"
```

---

## Task 13: End-To-End V0.6 Workflow Tests

**Files:**

- Modify: `tests/test_workflow.py`
- Modify: `tests/test_impeller_version_lineage.py`
- Modify: `scripts/verify_repository.ps1` only if test selection needs a new focused V0.6 file

- [ ] **Step 1: Add end-to-end workflow assertions**

Append to `tests/test_workflow.py`:

```python
def test_impeller_v06_open_and_closed_workflows_include_brep_mesh_and_fillets(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    for preset_id in ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest
        surfaces = {surface["id"]: surface for surface in manifest["geometry"]["surface_graph"]["surfaces"]}

        assert manifest["dsl_version"] == "0.6"
        assert manifest["parameters"]["blade_count"] == 12
        assert manifest["export_manifests"]["step"]["export_exactness"] == "surface_graph_trimmed_nurbs_step"
        assert manifest["export_manifests"]["mesh_step"]["export_exactness"] == "surface_graph_mesh_step"
        assert manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"] > 0
        assert "blade_0_root_fillet_surface" in surfaces
        assert surfaces["blade_0_root_fillet_surface"]["radius_mm"] == manifest["parameters"]["root_fillet_radius_mm"]
        assert Path(manifest["exports"]["step"]).exists()
        assert Path(manifest["exports"]["mesh_step"]).exists()
        assert Path(manifest["exports"]["stl"]).exists()
```

- [ ] **Step 2: Run workflow tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v06_open_and_closed_workflows_include_brep_mesh_and_fillets -q
```

Expected: pass.

- [ ] **Step 3: Update version lineage tests**

In `tests/test_impeller_version_lineage.py`, add V0.6 to the current folder lineage cases:

```python
("0.6", ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"])
```

Do not add a historical git tag expectation for V0.6 until a V0.6 tag is intentionally created.

- [ ] **Step 4: Run lineage tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_version_lineage.py -q
```

Expected: pass.

- [ ] **Step 5: Commit workflow tests**

```powershell
git add tests/test_workflow.py tests/test_impeller_version_lineage.py
git commit -m "test: cover v0.6 brep workflow"
```

---

## Task 14: Evidence And Documentation Updates

**Files:**

- Modify: `docs/evidence/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export/README.md`
- Modify: `docs/evidence/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export/CHANGELOG-DRAFT.md`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6/CHANGELOG.md`
- Modify: `docs/current-research-frontier.md`
- Modify: `docs/repository-map.md`
- Modify: `README.md`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`

- [ ] **Step 1: Generate local V0.6 evidence summary**

Run:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("Model Output") / "_v06_evidence_runs")
summary = {"runs": []}
for preset_id in ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"]:
    engine = service.synthesize("impeller", preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    summary["runs"].append({
        "preset_id": preset_id,
        "run_id": run.run_id,
        "step": manifest["exports"]["step"],
        "stl": manifest["exports"]["stl"],
        "mesh_step": manifest["exports"]["mesh_step"],
        "brep_face_count": manifest["export_manifests"]["step"]["brep_face_count"],
        "mesh_triangle_count": manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"],
        "root_fillet_radius_mm": manifest["parameters"]["root_fillet_radius_mm"],
    })
print(summary)
'@ | python -
```

Record the printed summary manually in the evidence README. Keep generated binaries under `Model Output/`.

- [ ] **Step 2: Update V0.6 DSL changelog**

Create `v0_6/CHANGELOG.md` using the draft but change status to implemented. Include:

```markdown
# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.6 Changelog

Date: 2026-07-01

Supersedes: `v0_5`

## Changes

1. Added `surface_graph_trimmed_brep` export contract.
2. Added trimmed NURBS/analytic B-Rep STEP exactness label.
3. Preserved STL and mesh STEP exports as separately labeled artifacts.
4. Added CAD payloads for exportable graph surfaces.
5. Added explicit blade root and edge fillet/blend feature controls.
6. Added CFD surface mesh manifest for mesh-quality inspection.
7. Added default output copies under `Model Output/`.
```

- [ ] **Step 3: Update current research frontier**

Change supported claims from "proposed V0.6" to implemented claims only after the workflow tests pass:

```text
generated STEP files as graph-derived trimmed NURBS/analytic B-Rep faces for V0.6 presets
```

Keep limitations:

```text
not certified manufacturing geometry
not solver-ready CFD volume mesh
not universal CAD healing across all parameters
```

- [ ] **Step 4: Update VERSION_INDEX**

Add:

```markdown
| `v0_6` | `radial_open_reference_v0_6`, `radial_closed_reference_v0_6` | Trimmed NURBS/analytic B-Rep STEP export, mesh inspection manifest, Model Output artifacts, and explicit fillet/blend controls. |
```

- [ ] **Step 5: Run documentation sanity checks**

Run:

```powershell
rg -n "T[BD]{2}|f.?ill.?in|[<]" docs src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_6
```

Expected: no unfinished placeholders in V0.6 implementation docs. Historical mentions in older evidence can remain if they describe past placeholder exports.

- [ ] **Step 6: Commit docs and evidence**

```powershell
git add docs README.md src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6/CHANGELOG.md
git commit -m "docs: record impeller v0.6 brep evidence"
```

---

## Task 15: Full Verification And Local Reload

**Files:**

- No source files should be edited in this task unless verification exposes a defect.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest `
  tests/test_impeller_occt_compat.py `
  tests/test_impeller_cad_payload.py `
  tests/test_impeller_brep_export.py `
  tests/test_impeller_mesh_manifest.py `
  tests/test_impeller_v06_resources.py `
  tests/test_workflow.py::test_impeller_v06_open_and_closed_workflows_include_brep_mesh_and_fillets `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
cd ..
```

Expected: frontend tests and build pass.

- [ ] **Step 3: Run repository fast verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_repository.ps1 -Mode fast
```

Expected: backend focused suite, frontend tests, and frontend build pass.

- [ ] **Step 4: Run repository full verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_repository.ps1 -Mode full
```

Expected: full backend suite, frontend tests, and frontend build pass.

- [ ] **Step 5: Run version lineage verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_version_lineage.ps1
```

Expected: current v0.2-v0.6 resources pass; historical v0.2-v0.4 tags pass.

- [ ] **Step 6: Generate final local V0.6 samples**

Run:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("Model Output") / "_final_v06_runs")
for preset_id in ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"]:
    engine = service.synthesize("impeller", preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    print(preset_id)
    print("  step:", manifest["exports"]["step"])
    print("  stl:", manifest["exports"]["stl"])
    print("  mesh_step:", manifest["exports"]["mesh_step"])
    print("  brep_faces:", manifest["export_manifests"]["step"]["brep_face_count"])
    print("  triangles:", manifest["simulation_manifests"]["cfd_surface_mesh"]["triangle_count"])
'@ | python -
```

Expected: both presets write STEP B-Rep, STL, mesh STEP, and manifest artifacts under `Model Output/`.

- [ ] **Step 7: Restart local frontend and backend**

Stop existing local server processes on ports `8040` and `5199`, then run:

```powershell
$logDir = Join-Path $env:TEMP 'impellerConstructor-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Process -FilePath powershell -ArgumentList @(
  '-NoProfile',
  '-ExecutionPolicy',
  'Bypass',
  '-Command',
  "`$env:PYTHONPATH='src'; python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8040"
) -WorkingDirectory (Get-Location) -RedirectStandardOutput (Join-Path $logDir 'backend-v06.out.log') -RedirectStandardError (Join-Path $logDir 'backend-v06.err.log') -WindowStyle Hidden

Start-Process -FilePath powershell -ArgumentList @(
  '-NoProfile',
  '-ExecutionPolicy',
  'Bypass',
  '-Command',
  'npm.cmd run dev'
) -WorkingDirectory (Join-Path (Get-Location) 'frontend') -RedirectStandardOutput (Join-Path $logDir 'frontend-v06.out.log') -RedirectStandardError (Join-Path $logDir 'frontend-v06.err.log') -WindowStyle Hidden
```

Check:

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:5199/' -UseBasicParsing
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8040/api/health'
```

If no health route exists, use the existing synthesize API for a smoke check.

- [ ] **Step 8: Handle verification defects without broad staging**

If verification exposed defects, return to the task that introduced the failing surface and make a focused fix there. Before any follow-up commit, inspect the exact paths:

```powershell
git status --short
```

Do not use `git add .`. Do not create an empty commit when verification already passed.

---

## Self-Review Checklist

Spec coverage:

- Trimmed NURBS/B-Rep STEP: Tasks 1, 4, 6, 7, 13.
- V0.6 version line: Task 2.
- `surface_graph` CAD payloads: Tasks 3 and 5.
- No mesh fallback under B-Rep label: Tasks 4 and 6.
- `Model Output/` routing and filenames: Tasks 7 and 10.
- CFD360 mesh view: Tasks 8 and 11.
- Interactive root/edge fillet controls: Tasks 9 and 12.
- Evidence and research logs: Task 14.
- Full verification and local reload: Task 15.

Completion marker scan:

- This plan intentionally contains no unfinished-work markers.
- Any deferred research behavior is expressed as a manifest limitation, not as an unfinished plan step.

Type consistency:

- Backend B-Rep exporter function: `write_trimmed_brep_step`.
- B-Rep exactness label: `surface_graph_trimmed_nurbs_step`.
- Mesh STEP exactness label: `surface_graph_mesh_step`.
- STL exactness label: `surface_graph_sampled_mesh`.
- Mesh manifest key: `simulation_manifests.cfd_surface_mesh`.
- Export route keys: `step`, `stl`, `mesh_step`, `manifest`.
