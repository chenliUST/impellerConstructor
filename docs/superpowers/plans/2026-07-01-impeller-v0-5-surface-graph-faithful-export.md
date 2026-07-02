# Impeller v0.5 Surface-Graph-Faithful Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build v0.5 exports so STL/STEP artifacts are traceable projections of `manifest.geometry.surface_graph` rather than independent CadQuery proxy geometry.

**Architecture:** Add a dedicated surface graph export module and route v0.5 impeller exports through it. Keep v0.2-v0.4 loadable and preserve current CadQuery proxy behavior only for legacy versions or explicitly labeled fallback paths. Export manifests record source graph, view, exactness, and per-region provenance.

**Tech Stack:** Python 3.12, FastAPI service layer, standard-library `struct` for binary STL, existing impeller DSL loader/compiler, pytest, current PowerShell verification scripts.

---

## File Structure

Create:

- `src/part_rule_synthesis/impeller_surface_graph_export.py`  
  Surface selection, UV-grid triangulation, binary STL writing, optional STEP policy, and export metadata.

- `tests/test_impeller_surface_graph_export.py`  
  Unit tests for triangulation, region metadata, degenerate triangle filtering, and view selection.

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/CHANGELOG.md`  
  v0.5 export semantics changelog.

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/export_contracts/surface_graph_faithful.json`  
  JSON resource describing v0.5 export exactness and provenance contract.

Modify:

- `src/part_rule_synthesis/service.py`  
  Generate geometry metadata before exports for v0.5 and call the graph exporter.

- `src/part_rule_synthesis/impeller_runtime_compiler.py`  
  Load v0.5 export contract fields into runtime dictionaries.

- `src/part_rule_synthesis/impeller_dsl_resources.py`  
  Include v0.5 version folder and validate export contract resources.

- `tests/test_workflow.py`  
  Replace CadQuery proxy export assertions for latest impeller workflows with surface-graph-faithful assertions.

- `tests/test_impeller_version_lineage.py`  
  Add v0.5 lineage case after v0.5 resources are loadable.

- `README.md`, `docs/current-research-frontier.md`, `docs/repository-map.md`  
  Clarify current and planned export claims.

- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`  
  Add v0.5 table entry after implementation.

## Task 1: Add v0.5 Export Contract Resources

**Files:**

- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/CHANGELOG.md`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/export_contracts/surface_graph_faithful.json`
- Modify: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_v05_resources.py`

- [ ] **Step 1: Write failing resource tests**

Create `tests/test_impeller_v05_resources.py`:

```python
from pathlib import Path

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


DSL_ROOT = (
    Path("src")
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_5"
)


def test_v05_export_contract_resource_exists():
    contract = DSL_ROOT / "export_contracts" / "surface_graph_faithful.json"
    changelog = DSL_ROOT / "CHANGELOG.md"

    assert contract.exists()
    assert changelog.exists()


def test_v05_bundle_loads_surface_graph_faithful_export_contract():
    bundle = load_impeller_dsl_bundle("v0_5")

    assert "surface_graph_faithful" in bundle.export_contracts
    contract = bundle.export_contracts["surface_graph_faithful"]
    assert contract["source_geometry"] == "surface_graph"
    assert contract["default_view"] == "cad_review_360"
    assert "surface_graph_sampled_mesh" in contract["stl"]["allowed_exactness"]
    assert "cadquery_proxy_solid_claimed_as_surface_graph_export" in contract["disallowed_modes"]


def test_v05_runtime_preset_includes_export_contract():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_5")

    assert runtime["dsl_version"] == "0.5"
    assert runtime["export_contract"]["contract_id"] == "surface_graph_faithful"
    assert runtime["export_contract"]["source_geometry"] == "surface_graph"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_v05_resources.py -q
```

Expected: fails because v0.5 resources and `bundle.export_contracts` do not exist.

- [ ] **Step 3: Add export contract JSON**

Create `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/export_contracts/surface_graph_faithful.json`:

```json
{
  "contract_id": "surface_graph_faithful",
  "dsl_version": "0.5",
  "source_geometry": "surface_graph",
  "default_view": "cad_review_360",
  "views": ["cad_review_360", "cfd_full_360", "feature_debug_360"],
  "stl": {
    "required": true,
    "allowed_exactness": ["surface_graph_sampled_mesh"],
    "requires_triangle_regions": true
  },
  "step": {
    "required": false,
    "allowed_exactness": ["surface_graph_step_shell", "surface_graph_mesh_step", "step_not_available_for_view"],
    "requires_face_regions_when_available": true
  },
  "required_region_fields": ["surface_graph_id", "feature_id", "role"],
  "disallowed_modes": ["cadquery_proxy_solid_claimed_as_surface_graph_export"]
}
```

- [ ] **Step 4: Add v0.5 changelog**

Create `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/CHANGELOG.md` with the changelog draft from the v0.5 spec.

- [ ] **Step 5: Extend resource loader**

Update the impeller DSL bundle dataclass in `impeller_dsl_resources.py` to include:

```python
export_contracts: dict[str, dict[str, Any]]
```

Load JSON files from `export_contracts/*.json` into that field. For older versions,
return `{}`.

- [ ] **Step 6: Extend runtime compiler**

In `compile_impeller_runtime_preset`, if the loaded bundle has a `surface_graph_faithful`
export contract and the preset id ends with `_v0_5`, add:

```python
runtime["export_contract"] = bundle.export_contracts["surface_graph_faithful"]
runtime["dsl_version"] = "0.5"
```

Add v0.5 aliases:

```json
{
  "radial_open_reference_v0_5": "radial_open_reference_v0_5",
  "radial_closed_reference_v0_5": "radial_closed_reference_v0_5"
}
```

- [ ] **Step 7: Run resource tests**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_v05_resources.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit resource contract**

```powershell
git add tests/test_impeller_v05_resources.py src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5 src/part_rule_synthesis/impeller_dsl_resources.py src/part_rule_synthesis/impeller_runtime_compiler.py
git commit -m "feat: add impeller dsl v0.5 export contract"
```

## Task 2: Add Surface Graph STL Exporter

**Files:**

- Create: `src/part_rule_synthesis/impeller_surface_graph_export.py`
- Test: `tests/test_impeller_surface_graph_export.py`

- [ ] **Step 1: Write failing exporter tests**

Create `tests/test_impeller_surface_graph_export.py`:

```python
from pathlib import Path
import struct

from part_rule_synthesis.impeller_surface_graph_export import export_surface_graph_stl


def _surface(surface_id, role, z_offset=0.0):
    return {
        "id": surface_id,
        "role": role,
        "feature_id": "feature_a",
        "uv_grid": [
            [[0.0, 0.0, z_offset], [1.0, 0.0, z_offset]],
            [[0.0, 1.0, z_offset], [1.0, 1.0, z_offset]]
        ]
    }


def test_export_surface_graph_stl_writes_binary_stl_and_regions(tmp_path: Path):
    surface_graph = {"surfaces": [_surface("blade_0_pressure_surface", "blade_pressure")]}
    path = tmp_path / "impeller.stl"

    manifest = export_surface_graph_stl(surface_graph, path, view="cad_review_360", manifest_context={})

    data = path.read_bytes()
    triangle_count = struct.unpack("<I", data[80:84])[0]
    assert triangle_count == 2
    assert len(data) == 84 + 2 * 50
    assert manifest["source"] == "surface_graph"
    assert manifest["export_exactness"] == "surface_graph_sampled_mesh"
    assert manifest["triangle_regions"] == [
        {
            "surface_graph_id": "blade_0_pressure_surface",
            "feature_id": "feature_a",
            "role": "blade_pressure",
            "triangle_start": 0,
            "triangle_count": 2
        }
    ]


def test_export_surface_graph_stl_exports_edge_closure_surfaces(tmp_path: Path):
    surface_graph = {
        "surfaces": [
            _surface("blade_0_pressure_surface", "blade_pressure"),
            _surface("blade_0_leading_edge_surface", "blade_leading_edge_closure", z_offset=1.0)
        ]
    }
    path = tmp_path / "impeller.stl"

    manifest = export_surface_graph_stl(surface_graph, path, view="cad_review_360", manifest_context={})

    roles = {region["role"] for region in manifest["triangle_regions"]}
    assert "blade_pressure" in roles
    assert "blade_leading_edge_closure" in roles
    assert manifest["surface_count"] == 2
    assert manifest["triangle_count"] == 4


def test_export_surface_graph_stl_filters_degenerate_triangles(tmp_path: Path):
    surface_graph = {
        "surfaces": [
            {
                "id": "degenerate",
                "role": "debug",
                "feature_id": "debug",
                "uv_grid": [
                    [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                    [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
                ]
            }
        ]
    }
    path = tmp_path / "empty.stl"

    manifest = export_surface_graph_stl(surface_graph, path, view="cad_review_360", manifest_context={})

    assert manifest["triangle_count"] == 0
    assert manifest["warnings"] == ["surface degenerate produced no exportable triangles"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_surface_graph_export.py -q
```

Expected: fails because `impeller_surface_graph_export.py` does not exist.

- [ ] **Step 3: Implement exporter module**

Create `src/part_rule_synthesis/impeller_surface_graph_export.py`:

```python
from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any


def export_surface_graph_stl(
    surface_graph: dict[str, Any],
    path: Path,
    *,
    view: str,
    manifest_context: dict[str, Any],
) -> dict[str, Any]:
    selected = selected_export_surfaces(surface_graph, view=view, manifest_context=manifest_context)
    triangles: list[tuple[list[float], list[float], list[float], dict[str, Any]]] = []
    regions: list[dict[str, Any]] = []
    warnings: list[str] = []

    for surface in selected:
        start = len(triangles)
        for a, b, c in _triangulate_grid(surface.get("uv_grid", [])):
            if _triangle_area(a, b, c) > 1e-9:
                triangles.append((a, b, c, surface))
        count = len(triangles) - start
        if count == 0:
            warnings.append(f"surface {surface.get('id', '<missing>')} produced no exportable triangles")
            continue
        regions.append(
            {
                "surface_graph_id": surface["id"],
                "feature_id": surface.get("feature_id", ""),
                "role": surface.get("role", ""),
                "triangle_start": start,
                "triangle_count": count,
            }
        )

    _write_binary_stl(path, triangles)
    return {
        "format": "stl",
        "source": "surface_graph",
        "view": view,
        "status": "PASS" if triangles else "PASS_WITH_WARNINGS",
        "export_exactness": "surface_graph_sampled_mesh",
        "surface_count": len(selected),
        "triangle_count": len(triangles),
        "triangle_regions": regions,
        "warnings": warnings,
    }


def selected_export_surfaces(
    surface_graph: dict[str, Any],
    *,
    view: str,
    manifest_context: dict[str, Any],
) -> list[dict[str, Any]]:
    surfaces = list(surface_graph.get("surfaces", []))
    if view == "cad_review_360" or view == "feature_debug_360":
        return [surface for surface in surfaces if surface.get("uv_grid")]
    if view == "cfd_full_360":
        return [
            surface
            for surface in surfaces
            if surface.get("uv_grid")
            and surface.get("role") not in {"reference_only", "construction_support_only", "open_tip_reference"}
        ]
    raise ValueError(f"unsupported export view: {view}")


def _triangulate_grid(grid: list[list[list[float]]]):
    if len(grid) < 2 or not grid or len(grid[0]) < 2:
        return
    v_count = len(grid[0])
    for u_index in range(len(grid) - 1):
        if len(grid[u_index]) != v_count or len(grid[u_index + 1]) != v_count:
            continue
        for v_index in range(v_count - 1):
            a = grid[u_index][v_index]
            b = grid[u_index + 1][v_index]
            c = grid[u_index + 1][v_index + 1]
            d = grid[u_index][v_index + 1]
            yield a, b, d
            yield b, c, d


def _write_binary_stl(
    path: Path,
    triangles: list[tuple[list[float], list[float], list[float], dict[str, Any]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"surface_graph_faithful_export".ljust(80, b" "))
        handle.write(struct.pack("<I", len(triangles)))
        for a, b, c, _surface in triangles:
            normal = _triangle_normal(a, b, c)
            handle.write(struct.pack("<fff", *normal))
            handle.write(struct.pack("<fff", *a))
            handle.write(struct.pack("<fff", *b))
            handle.write(struct.pack("<fff", *c))
            handle.write(struct.pack("<H", 0))


def _triangle_normal(a: list[float], b: list[float], c: list[float]) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 0.0:
        return 0.0, 0.0, 0.0
    return nx / length, ny / length, nz / length


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    nx, ny, nz = _triangle_normal(a, b, c)
    if nx == 0.0 and ny == 0.0 and nz == 0.0:
        return 0.0
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cross_x = uy * vz - uz * vy
    cross_y = uz * vx - ux * vz
    cross_z = ux * vy - uy * vx
    return 0.5 * math.sqrt(cross_x * cross_x + cross_y * cross_y + cross_z * cross_z)
```

- [ ] **Step 4: Run exporter tests**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_surface_graph_export.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit exporter**

```powershell
git add src/part_rule_synthesis/impeller_surface_graph_export.py tests/test_impeller_surface_graph_export.py
git commit -m "feat: export impeller surface graph stl"
```

## Task 3: Integrate v0.5 Export Into Service

**Files:**

- Modify: `src/part_rule_synthesis/service.py`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Write failing workflow test**

Add this test to `tests/test_workflow.py`:

```python
def test_impeller_v05_exports_match_surface_graph_regions(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_5")
    run = service.instantiate(engine.engine_id, {})

    surface_graph = run.manifest["geometry"]["surface_graph"]
    stl_manifest = run.manifest["export_manifests"]["stl"]
    graph_surface_ids = {surface["id"] for surface in surface_graph["surfaces"]}
    exported_surface_ids = {region["surface_graph_id"] for region in stl_manifest["triangle_regions"]}

    assert run.manifest["export_strategy"]["mode"] == "surface_graph_faithful"
    assert stl_manifest["source"] == "surface_graph"
    assert stl_manifest["surface_count"] == len(surface_graph["surfaces"])
    assert exported_surface_ids == graph_surface_ids
    assert any(region["role"] == "blade_leading_edge_closure" for region in stl_manifest["triangle_regions"])
    assert "cadquery_proxy_disk" not in exported_surface_ids
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_workflow.py::test_impeller_v05_exports_match_surface_graph_regions -q
```

Expected: fails because v0.5 service export integration is absent.

- [ ] **Step 3: Refactor service instantiation order**

In `RuleSynthesisService.instantiate`, compute `geometry_validity`, `geometry_metadata`,
and `geometry_kernel` before `_write_exports(...)`. Pass `geometry_metadata` to
`_write_exports(...)`:

```python
exports, export_manifests = _write_exports(
    run_dir,
    dsl["part_family"],
    bound,
    dsl.get("facets", {}),
    profile_overrides=normalized_profile_overrides,
    curve_overrides=normalized_curve_overrides,
    geometry_stage=normalized_geometry_stage,
    dsl_context=dsl,
    geometry_metadata=geometry_metadata,
)
```

Update manifest creation:

```python
"export_strategy": export_strategy,
"exports": exports,
"export_manifests": export_manifests,
```

- [ ] **Step 4: Route v0.5 impellers through graph exporter**

In `_write_exports`, add `geometry_metadata` and return `(exports, export_manifests)`.
For v0.5:

```python
if part_family == "impeller" and _dsl_version(dsl_context or {}) == "0.5":
    from part_rule_synthesis.impeller_surface_graph_export import export_surface_graph_stl

    stl_manifest = export_surface_graph_stl(
        geometry_metadata["surface_graph"],
        stl,
        view="cad_review_360",
        manifest_context={"parameters": parameters, "facets": facets or {}},
    )
    step_manifest = {
        "format": "step",
        "source": "surface_graph",
        "view": "cad_review_360",
        "status": "PASS_WITH_WARNINGS",
        "export_exactness": "step_not_available_for_view",
        "face_regions": [],
        "warnings": ["faithful STEP shell export is not implemented in this task"]
    }
    step.write_text(
        "ISO-10303-21;\\n"
        "HEADER;\\n"
        "FILE_DESCRIPTION(('surface_graph faithful STEP not implemented; see export_manifests.step'),'2;1');\\n"
        "ENDSEC;\\n"
        "DATA;\\nENDSEC;\\nEND-ISO-10303-21;\\n",
        encoding="utf-8",
    )
    return {"step": str(step), "stl": str(stl)}, {"stl": stl_manifest, "step": step_manifest}
```

Keep the existing CadQuery path for older versions and legacy families, but label it
as non-faithful when used.

- [ ] **Step 5: Update export strategy**

In `_export_strategy`, use `dsl_context` or version-aware dispatch:

```python
if part_family == "impeller" and _dsl_version(dsl_context or {}) == "0.5":
    return {
        "mode": "surface_graph_faithful",
        "cad_exports": "completed",
        "reason": "exports are derived from manifest.geometry.surface_graph",
    }
```

- [ ] **Step 6: Run workflow test**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_workflow.py::test_impeller_v05_exports_match_surface_graph_regions -q
```

Expected: passes.

- [ ] **Step 7: Run focused backend tests**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_surface_graph_export.py tests/test_workflow.py tests/test_impeller_v05_resources.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit service integration**

```powershell
git add src/part_rule_synthesis/service.py tests/test_workflow.py
git commit -m "feat: route impeller v0.5 exports through surface graph"
```

## Task 4: Add STEP Honesty Policy Tests

**Files:**

- Modify: `tests/test_workflow.py`
- Modify: `src/part_rule_synthesis/service.py`

- [ ] **Step 1: Add failing STEP policy test**

Add:

```python
def test_impeller_v05_step_export_is_not_proxy_claimed_as_faithful(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_5")
    run = service.instantiate(engine.engine_id, {})

    step_manifest = run.manifest["export_manifests"]["step"]
    step_text = Path(run.manifest["exports"]["step"]).read_text(encoding="utf-8", errors="ignore")

    assert step_manifest["source"] == "surface_graph"
    assert step_manifest["export_exactness"] in {
        "surface_graph_step_shell",
        "surface_graph_mesh_step",
        "step_not_available_for_view",
    }
    assert step_manifest["export_exactness"] != "cadquery_proxy_solid_claimed_as_surface_graph_export"
    assert "surface_graph faithful STEP" in step_text
```

- [ ] **Step 2: Run test to verify behavior**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_workflow.py::test_impeller_v05_step_export_is_not_proxy_claimed_as_faithful -q
```

Expected: passes after Task 3. If it fails, update the v0.5 STEP manifest path so it
does not silently use CadQuery proxy geometry.

- [ ] **Step 3: Commit STEP policy**

```powershell
git add src/part_rule_synthesis/service.py tests/test_workflow.py
git commit -m "test: enforce honest impeller v0.5 step export policy"
```

## Task 5: Version Lineage And Documentation

**Files:**

- Modify: `tests/test_impeller_version_lineage.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Modify: `README.md`
- Modify: `docs/current-research-frontier.md`
- Modify: `docs/repository-map.md`

- [ ] **Step 1: Add v0.5 lineage test case**

In `tests/test_impeller_version_lineage.py`, add:

```python
(
    "v0_5",
    "0.5",
    ["radial_open_reference_v0_5", "radial_closed_reference_v0_5"],
),
```

- [ ] **Step 2: Run lineage test**

Run:

```powershell
$env:PYTHONPATH='.;src'
pytest tests/test_impeller_version_lineage.py -q
```

Expected: passes after v0.5 resources compile.

- [ ] **Step 3: Update version index**

Add v0.5 row:

```markdown
| `v0_5` | `radial_open_reference_v0_5`, `radial_closed_reference_v0_5` | Surface-graph-faithful export contract with STL region provenance and honest STEP fidelity labels. |
```

- [ ] **Step 4: Update README current status**

Set:

```markdown
- Latest DSL version: `v0_5`
- Export status: impeller STL downloads are faithful projections of `surface_graph`; STEP exactness is labeled in `export_manifests.step`.
```

- [ ] **Step 5: Update research frontier**

Add claim:

```markdown
- generated STL files from the same `surface_graph` rendered by the frontend
- export provenance from STL triangle regions to `surface_graph_id`, feature, and role
```

Keep non-claim:

```markdown
- exact industrial STEP B-Rep sewing
```

- [ ] **Step 6: Commit docs**

```powershell
git add README.md docs/current-research-frontier.md docs/repository-map.md src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md tests/test_impeller_version_lineage.py
git commit -m "docs: record impeller dsl v0.5 export lineage"
```

## Task 6: Full Verification

**Files:**

- Verify only.

- [ ] **Step 1: Run fast verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_repository.ps1 -Mode fast
```

Expected:

- backend focused tests pass,
- frontend tests pass,
- frontend build check passes.

- [ ] **Step 2: Run full verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_repository.ps1 -Mode full
```

Expected:

- all backend tests pass,
- frontend tests pass,
- frontend build check passes.

- [ ] **Step 3: Generate a v0.5 evidence export**

Run:

```powershell
$env:PYTHONPATH='.;src'
@'
from pathlib import Path
import json
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("runs/v05-export-evidence"))
engine = service.synthesize("impeller", "radial_open_reference_v0_5")
run = service.instantiate(engine.engine_id, {})
summary = {
    "run_id": run.run_id,
    "export_strategy": run.manifest["export_strategy"],
    "stl": run.manifest["export_manifests"]["stl"],
    "step": run.manifest["export_manifests"]["step"],
}
print(json.dumps(summary, indent=2))
'@ | python -
```

Expected:

- `export_strategy.mode` is `surface_graph_faithful`,
- `export_manifests.stl.source` is `surface_graph`,
- `triangle_regions` includes blade edge closure roles.

- [ ] **Step 4: Commit final verification doc update if needed**

If README expected counts changed, update them and commit:

```powershell
git add README.md docs/current-research-frontier.md
git commit -m "docs: update v0.5 verification status"
```

## Final Verification Checklist

- [ ] v0.2, v0.3, v0.4 version lineage remains loadable.
- [ ] v0.5 resource tests pass.
- [ ] v0.5 export tests pass.
- [ ] v0.5 STL has region provenance for every selected surface graph surface.
- [ ] v0.5 open preset includes blade edge closure surfaces in STL regions.
- [ ] v0.5 export does not introduce an unregistered disk/backplate.
- [ ] STEP is graph-derived or explicitly labeled as limited/unavailable.
- [ ] README and current research frontier do not overclaim industrial exact B-Rep.

## Plan Self-Review

- Spec coverage: covers export contract resources, STL fidelity, STEP honesty, service integration, lineage, and docs.
- Placeholder scan: no unresolved placeholders.
- Type consistency: uses `export_manifests`, `triangle_regions`, `surface_graph_id`, `feature_id`, `role`, and `surface_graph_faithful` consistently.
- Scope check: focused on v0.5 export semantics; exact STEP B-Rep sewing remains a later extension.

