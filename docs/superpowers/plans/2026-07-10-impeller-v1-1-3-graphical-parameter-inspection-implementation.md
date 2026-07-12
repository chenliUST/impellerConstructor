# Impeller V1.1.3 Graphical Parameter Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only graphical parameter-inspection workspace that displays resolved V1.1.2 impeller geometry and canonical parameters in full-size 3D, Top, Meridional, S-Q, and synchronized Quad views under the V1.1.3 runtime release.

**Architecture:** Build a versioned backend inspection contract from the existing V1.1.2 surface graph, with stable entity ids and deterministic generation provenance. In the frontend, use one shared Three.js scene for 3D, Top, and Meridional viewports, an SVG S-Q renderer for actual section loops and canonical controls, and one selection/annotation model shared by all tabs.

**Tech Stack:** Python geometry/service layer and pytest; JSON-compatible manifest contracts; React without JSX; Three.js with viewport/scissor rendering; SVG annotations; Node test runner; Playwright and PNG pixel inspection from the bundled Codex runtime for visual acceptance.

## Global Constraints

- `runtime_release_version = "1.1.3"`.
- `parameter_inspection_contract_version = "1.1.3"`.
- Preserve `geometry_patch_version = "1.1.2"` and `canonical_payload_version = "1.1.2"`.
- Preserve all active V1.1 preset ids; do not create V1.1.3-specific preset ids.
- Do not change V1.1.2 NURBS construction equations, surface roles, or export semantics.
- Remove the text-only `ParameterViewsPanel`; there must be one resolved-geometry inspection path.
- The graphical inspection workspace is read-only; no control-point dragging or geometry mutation callbacks.
- Generated values come from the resolved manifest and actual surface graph, never from preset labels after generation.
- Use one WebGL renderer and one shared Three.js scene for 3D, Top, and Meridional.
- Full-size 3D is the default; Quad is an optional synchronized overview.
- Annotation levels are exactly `key`, `selected`, and `all`.
- Preserve existing CAD review, CFD full 360, CFD360 mesh, Feature debug, shaded, UV-wire, and mesh behavior.

---

## File Structure

### Backend

- Create `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`: deterministic generation id, inspection-contract construction, and contract validation.
- Modify `src/part_rule_synthesis/impeller_v11_surface_family.py`: attach the contract to the completed V1.1.2 graph without changing geometry construction.
- Modify `src/part_rule_synthesis/impeller_runtime_compiler.py`: expose V1.1.3 runtime/inspection versions while preserving geometry/canonical versions.
- Modify `src/part_rule_synthesis/impeller_v11_validation.py`: include inspection-contract validation failures.
- Modify `src/part_rule_synthesis/service.py`: expose generation and inspection fields at manifest top level.
- Create `tests/test_impeller_v11_3_parameter_inspection_contract.py`: builder, provenance, references, and all-preset coverage.
- Create `tests/test_impeller_v11_3_service_manifest.py`: runtime/service version separation and validation behavior.

### Frontend

- Delete `frontend/src/parameterViewModel.js` and `frontend/src/parameterViewModel.test.js`.
- Delete `frontend/src/components/ParameterViewsPanel.js` and `frontend/src/components/ParameterViewsPanel.test.js`.
- Create `frontend/src/parameterInspectionModel.js`: contract resolution, validation, indices, shared selection, annotation filtering, and selected S-Q station lookup.
- Create `frontend/src/parameterInspectionModel.test.js`: pure-model tests.
- Modify `frontend/src/appModel.js` and `frontend/src/appModel.test.js`: identify the active frontend release as V1.1.3 while retaining V1.1 preset ids.
- Create `frontend/src/inspectionSceneModel.js`: deterministic viewport rectangles, camera framing, and view hit-testing.
- Create `frontend/src/inspectionSceneModel.test.js`: layout and camera tests.
- Create `frontend/src/components/InspectionScene.js`: one renderer/scene, three cameras, scissor rendering, picking, and lifecycle cleanup.
- Create `frontend/src/components/InspectionScene.test.js`: source/lifecycle contract tests.
- Create `frontend/src/components/SectionLoopInspectionView.js`: actual S-Q loop and canonical control rendering.
- Create `frontend/src/components/SectionLoopInspectionView.test.js`: source/interaction contract tests.
- Create `frontend/src/components/ParameterAnnotationOverlay.js`: projected labels and deterministic leader layout.
- Create `frontend/src/components/ParameterInspectionWorkspace.js`: tabs, Quad, maximize, annotation-level control, errors, and shared selection.
- Create `frontend/src/components/ParameterInspectionWorkspace.test.js`: workspace source contract tests.
- Modify `frontend/src/components/ModelViewer.js`: export existing reusable surface-graph scene helpers; do not alter existing rendered behavior.
- Modify `frontend/src/simulationViewModel.js` and `frontend/src/simulationViewModel.test.js`: add the central `parameter_inspection` mode.
- Modify `frontend/src/App.js` and `frontend/src/appFiles.test.js`: route the central workspace and remove the old panel.
- Modify `frontend/src/styles.css`: full-size and Quad layout, responsive stack, overlays, toolbar, and error states.
- Create `frontend/scripts/parameter-inspection-visual-smoke.cjs`: Playwright screenshots and nonblank pixel assertions.

### Documentation

- Modify `docs/version-history.md`.
- Create `docs/evidence/2026-07-10-impeller-v1-1-3-semantic-change-log.md`.
- Create `docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md`.
- Create `docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md`.
- Create screenshot assets under `docs/evidence/assets/v1.1.3-parameter-inspection/`.

---

### Task 1: Build the V1.1.3 Backend Inspection Contract

**Files:**
- Create: `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- Modify: `src/part_rule_synthesis/impeller_v11_surface_family.py:61-123`
- Test: `tests/test_impeller_v11_3_parameter_inspection_contract.py`

**Interfaces:**
- Consumes: a completed V1.1.2 `surface_graph` containing `surfaces`, `blade_to_blade_loop_family`, `canonical_nurbs_parameterization`, and `canonical_metrics`.
- Produces: `build_parameter_inspection_contract(surface_graph: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: `parameter_inspection_generation_id(surface_graph: Mapping[str, Any]) -> str`.
- Produces: graph fields `generation_id` and `parameter_inspection`.

- [ ] **Step 1: Write failing contract tests**

Create the test module with these assertions:

```python
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_3_parameter_inspection import parameter_inspection_generation_id
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def graph_for(preset_id="radial_open_reference_v1_1", edits=None):
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    parameters.update(edits or {})
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_contract_has_release_and_geometry_provenance():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    assert contract["contract_version"] == "1.1.3"
    assert contract["source_geometry_patch_version"] == "1.1.2"
    assert contract["source_canonical_payload_version"] == "1.1.2"
    assert contract["generation_id"] == graph["generation_id"]


def test_contract_references_existing_surfaces_and_actual_loops():
    graph = graph_for()
    contract = graph["parameter_inspection"]
    surface_ids = {surface["id"] for surface in graph["surfaces"]}
    assert set(contract["surface_references"]) == surface_ids
    station = next(iter(contract["span_stations"].values()))
    loop = contract["section_loops"][station["section_loop_id"]]
    assert loop["source_blade_index"] == station["source_blade_index"]
    assert loop["source_loop_index"] == station["source_loop_index"]
    assert set(loop["segment_references"]) == {
        "pressure_side", "suction_side", "leading_edge", "trailing_edge"
    }
    thickness = contract["resolved_dimensions"]["thickness_min_mm"]
    assert thickness["unit"] == "mm"
    assert thickness["requested_value"] is not None
    assert thickness["resolved_value"] == graph["canonical_metrics"]["thickness_min_mm"]


def test_generation_id_is_deterministic_and_geometry_sensitive():
    baseline_a = graph_for()
    baseline_b = graph_for()
    edited = deepcopy(baseline_a)
    edited["surfaces"][0]["uv_grid"][0][0][0] += 0.125
    assert baseline_a["generation_id"] == baseline_b["generation_id"]
    assert parameter_inspection_generation_id(edited) != baseline_a["generation_id"]


def test_all_active_presets_emit_contracts():
    for preset_id in ACTIVE_PRESETS:
        graph = graph_for(preset_id)
        assert graph["parameter_inspection"]["contract_version"] == "1.1.3", preset_id
        assert graph["parameter_inspection"]["blade_instances"], preset_id
```

- [ ] **Step 2: Run the test and verify the missing-contract failure**

Run:

```powershell
python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py -q
```

Expected: FAIL with `KeyError: 'parameter_inspection'`.

- [ ] **Step 3: Implement deterministic ids and the contract builder**

Create `impeller_v11_3_parameter_inspection.py` with these public constants and functions:

```python
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

RUNTIME_RELEASE_VERSION = "1.1.3"
INSPECTION_CONTRACT_VERSION = "1.1.3"


def parameter_inspection_generation_id(surface_graph: Mapping[str, Any]) -> str:
    basis = {
        "geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "canonical": surface_graph.get("canonical_nurbs_parameterization", {}),
        "surfaces": [
            {
                "id": surface.get("id"),
                "role": surface.get("role"),
                "uv_grid": surface.get("uv_grid", []),
            }
            for surface in surface_graph.get("surfaces", [])
        ],
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def build_parameter_inspection_contract(surface_graph: Mapping[str, Any]) -> dict[str, Any]:
    generation_id = parameter_inspection_generation_id(surface_graph)
    canonical = surface_graph.get("canonical_nurbs_parameterization", {})
    loop_family = surface_graph.get("blade_to_blade_loop_family", {})
    surfaces = surface_graph.get("surfaces", [])
    surface_references = {
        str(surface["id"]): {
            "surface_id": str(surface["id"]),
            "blade_instance_id": _blade_instance_id(surface.get("blade_index")),
            "blade_index": surface.get("blade_index"),
            "face_family": surface.get("face_family"),
            "role": surface.get("role"),
            "quality": copy.deepcopy(
                surface.get("v1_1_root_quality")
                or surface.get("v1_1_tip_quality")
                or surface.get("v1_1_span_domain_quality")
                or {}
            ),
        }
        for surface in surfaces
        if surface.get("id")
    }
    blade_instances: dict[str, Any] = {}
    span_stations: dict[str, Any] = {}
    section_loops: dict[str, Any] = {}
    for blade_index, blade in enumerate(loop_family.get("blades", [])):
        blade_id = _blade_instance_id(blade_index)
        blade_surface_ids = [
            surface_id
            for surface_id, reference in surface_references.items()
            if reference.get("blade_index") == blade_index
        ]
        station_ids = []
        for loop_index, loop in enumerate(blade.get("loops", [])):
            station_id = f"{blade_id}:span_{loop_index}"
            loop_id = f"{station_id}:loop"
            station_ids.append(station_id)
            span_stations[station_id] = {
                "span_station_id": station_id,
                "blade_instance_id": blade_id,
                "source_blade_index": blade_index,
                "source_loop_index": loop_index,
                "h": loop.get("h"),
                "active_span_fraction": loop.get("active_span_fraction"),
                "section_loop_id": loop_id,
            }
            section_loops[loop_id] = {
                "section_loop_id": loop_id,
                "span_station_id": station_id,
                "source_blade_index": blade_index,
                "source_loop_index": loop_index,
                "segment_references": {
                    name: {
                        "section_segment_id": f"{loop_id}:{name}",
                        "source_segment_name": name,
                        "points_s_q": copy.deepcopy(segment.get("points_s_q", [])),
                        "control_points_s_q": copy.deepcopy(segment.get("control_points_s_q", [])),
                    }
                    for name, segment in loop.get("segments", {}).items()
                },
                "metrics": copy.deepcopy(loop.get("metrics", {})),
                "join_metrics": copy.deepcopy(loop.get("join_metrics", {})),
            }
        blade_instances[blade_id] = {
            "blade_instance_id": blade_id,
            "blade_index": blade_index,
            "blade_class": blade.get("blade_class"),
            "blade_pair_index": blade.get("blade_pair_index"),
            "phase_offset_pitch": blade.get("phase_offset_pitch"),
            "surface_ids": blade_surface_ids,
            "span_station_ids": station_ids,
        }
    return {
        "contract_version": INSPECTION_CONTRACT_VERSION,
        "generation_id": generation_id,
        "source_geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "source_canonical_payload_version": canonical.get("canonical_payload_version"),
        "blade_instances": blade_instances,
        "surface_references": surface_references,
        "span_stations": span_stations,
        "section_loops": section_loops,
        "support_profiles": copy.deepcopy(canonical.get("support_profiles", {})),
        "resolved_dimensions": _resolved_dimensions(surface_graph, canonical),
        "continuity_measurements": {
            loop_id: copy.deepcopy(loop["join_metrics"])
            for loop_id, loop in section_loops.items()
        },
    }


def _blade_instance_id(blade_index: Any) -> str | None:
    return None if blade_index is None else f"blade_{int(blade_index)}"


def _resolved_dimensions(surface_graph: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    metrics = surface_graph.get("canonical_metrics", {})
    thickness_controls = [
        float(point[2])
        for row in canonical.get("thickness_field", {}).get("control_points", [])
        for point in row
    ]
    population = canonical.get("blade_population", {})
    active_span = canonical.get("active_span_policy", {})
    return {
        "thickness_min_mm": _dimension(
            min(thickness_controls) if thickness_controls else None,
            metrics.get("thickness_min_mm"),
            "mm",
        ),
        "thickness_max_mm": _dimension(
            max(thickness_controls) if thickness_controls else None,
            metrics.get("thickness_max_mm"),
            "mm",
        ),
        "root_offset_mm": _dimension(
            active_span.get("root_offset", {}).get("ratio_of_local_thickness"),
            active_span.get("root_offset", {}).get("resolved_constant_mm"),
            "mm",
            requested_unit="thickness ratio",
        ),
        "tip_offset_mm": _dimension(
            active_span.get("tip_offset", {}).get("ratio_of_local_thickness"),
            active_span.get("tip_offset", {}).get("resolved_constant_mm"),
            "mm",
            requested_unit="thickness ratio",
        ),
        "main_blade_count": _dimension(population.get("main_blade_count"), population.get("main_blade_count"), "count"),
        "splitter_blade_count": _dimension(population.get("splitter_blade_count"), population.get("splitter_blade_count"), "count"),
        "splitter_passage_fraction": _dimension(
            population.get("splitter_passage_fraction"),
            population.get("splitter_passage_fraction"),
            "pitch fraction",
        ),
    }


def _dimension(
    requested_value: Any,
    resolved_value: Any,
    unit: str,
    *,
    requested_unit: str | None = None,
) -> dict[str, Any]:
    return {
        "requested_value": requested_value,
        "resolved_value": resolved_value,
        "unit": unit,
        "requested_unit": requested_unit or unit,
    }
```

- [ ] **Step 4: Attach the contract after constructing the graph**

In `build_v11_surface_graph`, assign the existing return dictionary to a local variable named `graph` without changing any field, then append:

```python
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    build_parameter_inspection_contract,
)

inspection = build_parameter_inspection_contract(graph)
graph["generation_id"] = inspection["generation_id"]
graph["parameter_inspection"] = inspection
return graph
```

Do not change the existing geometry fields or the order in which surfaces are built.

- [ ] **Step 5: Run focused and V1.1.2 compatibility tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the backend contract**

```powershell
git add -- src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py src/part_rule_synthesis/impeller_v11_surface_family.py tests/test_impeller_v11_3_parameter_inspection_contract.py
git commit -m "feat: add v1.1.3 parameter inspection contract"
```

---

### Task 2: Integrate Runtime, Manifest, and Validation Semantics

**Files:**
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py:259-290`
- Modify: `src/part_rule_synthesis/impeller_v11_validation.py:22-67`
- Modify: `src/part_rule_synthesis/service.py:340-365`
- Modify: `src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py`
- Test: `tests/test_impeller_v11_3_service_manifest.py`

**Interfaces:**
- Consumes: `build_parameter_inspection_contract` output from Task 1.
- Produces: `validate_parameter_inspection_contract(surface_graph, contract) -> list[dict[str, Any]]`.
- Produces manifest fields `runtime_release_version`, `parameter_inspection_contract_version`, `generation_id`, and `parameter_inspection`.

- [ ] **Step 1: Write failing service and validation tests**

Create tests that synthesize and instantiate the open preset, then assert:

```python
def test_service_manifest_separates_runtime_and_geometry_versions(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v1_1")
    manifest = service.instantiate(engine.engine_id, {}).manifest
    assert manifest["runtime_release_version"] == "1.1.3"
    assert manifest["parameter_inspection_contract_version"] == "1.1.3"
    assert manifest["geometry_patch_version"] == "1.1.2"
    assert manifest["geometry"]["surface_graph"]["canonical_nurbs_parameterization"]["canonical_payload_version"] == "1.1.2"
    assert manifest["generation_id"] == manifest["parameter_inspection"]["generation_id"]


def test_validation_rejects_missing_surface_reference():
    graph = graph_for()
    surface_id = next(iter(graph["parameter_inspection"]["surface_references"]))
    del graph["parameter_inspection"]["surface_references"][surface_id]
    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}
    assert "parameter_inspection_surface_reference_missing" in reasons


def test_validation_rejects_generation_mismatch():
    graph = graph_for()
    graph["parameter_inspection"]["generation_id"] = "stale"
    reasons = {failure["reason"] for failure in validate_v11_surface_graph(graph)}
    assert "parameter_inspection_generation_id_mismatch" in reasons


def test_all_active_presets_expose_service_inspection_contracts(tmp_path):
    service = RuleSynthesisService(tmp_path, model_output_root=tmp_path / "Model Output")
    for preset_id in ACTIVE_PRESETS:
        engine = service.synthesize("impeller", preset_id=preset_id)
        manifest = service.instantiate(engine.engine_id, {}).manifest
        assert manifest["parameter_inspection_contract_version"] == "1.1.3", preset_id
        assert manifest["parameter_inspection"]["generation_id"] == manifest["generation_id"], preset_id
```

Reuse the `graph_for` helper and `ACTIVE_PRESETS` list shape from Task 1 and import `RuleSynthesisService` and `validate_v11_surface_graph` explicitly.

- [ ] **Step 2: Run the new tests and verify missing fields**

Run:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py -q
```

Expected: FAIL because runtime and manifest V1.1.3 fields do not exist.

- [ ] **Step 3: Add runtime release fields without changing geometry versions**

Import the V1.1.3 constants into `impeller_runtime_compiler.py` and add these keys to `_v11_runtime_defaults`:

```python
"runtime_release_version": RUNTIME_RELEASE_VERSION,
"parameter_inspection_contract_version": INSPECTION_CONTRACT_VERSION,
```

Leave this line unchanged in meaning:

```python
"geometry_patch_version": preset.get("geometry_patch_version", "1.1.2"),
```

- [ ] **Step 4: Implement contract validation**

Add this public validator to `impeller_v11_3_parameter_inspection.py`:

```python
def validate_parameter_inspection_contract(
    surface_graph: Mapping[str, Any],
    contract: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(contract, Mapping):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    failures: list[dict[str, Any]] = []
    if contract.get("contract_version") != INSPECTION_CONTRACT_VERSION:
        failures.append({"reason": "parameter_inspection_contract_unsupported"})
    if contract.get("generation_id") != surface_graph.get("generation_id"):
        failures.append({"reason": "parameter_inspection_generation_id_mismatch"})
    graph_surface_ids = {surface.get("id") for surface in surface_graph.get("surfaces", [])}
    referenced_surface_ids = set(contract.get("surface_references", {}))
    if graph_surface_ids != referenced_surface_ids:
        failures.append({"reason": "parameter_inspection_surface_reference_missing"})
    station_ids = set(contract.get("span_stations", {}))
    loop_station_ids = {
        loop.get("span_station_id")
        for loop in contract.get("section_loops", {}).values()
    }
    if station_ids != loop_station_ids:
        failures.append({"reason": "parameter_inspection_station_reference_missing"})
    for loop in contract.get("section_loops", {}).values():
        if loop.get("metrics", {}).get("join_status") != "PASS":
            failures.append({
                "reason": "parameter_inspection_loop_not_closed",
                "section_loop_id": loop.get("section_loop_id"),
            })
    return failures
```

Call it from `validate_v11_surface_graph` only when `geometry_patch_version == "1.1.2"` and append its failures after existing canonical validation.

- [ ] **Step 5: Expose the contract at manifest top level**

In the `dsl_version == "1.1"` branch in `service.py`, add:

```python
manifest["runtime_release_version"] = dsl.get("runtime_release_version", "1.1.3")
manifest["parameter_inspection_contract_version"] = dsl.get(
    "parameter_inspection_contract_version", "1.1.3"
)
manifest["generation_id"] = surface_graph.get("generation_id")
manifest["parameter_inspection"] = copy.deepcopy(surface_graph.get("parameter_inspection", {}))
```

Do not move or rewrite `manifest["geometry"]`; the graph remains available under `manifest.geometry.surface_graph`.

- [ ] **Step 6: Run service, validation, and all-preset tests**

Run:

```powershell
python -m pytest tests/test_impeller_v11_3_service_manifest.py tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_2_surface_graph_compatibility.py tests/test_impeller_v11_resources.py -q
```

Expected: all tests PASS.

- [ ] **Step 7: Commit integration**

```powershell
git add -- src/part_rule_synthesis/impeller_runtime_compiler.py src/part_rule_synthesis/impeller_v11_validation.py src/part_rule_synthesis/service.py src/part_rule_synthesis/impeller_v11_3_parameter_inspection.py tests/test_impeller_v11_3_service_manifest.py
git commit -m "feat: expose v1.1.3 inspection manifest"
```

---

### Task 3: Replace the Text Panel with a Pure Inspection Model

**Files:**
- Delete: `frontend/src/parameterViewModel.js`
- Delete: `frontend/src/parameterViewModel.test.js`
- Delete: `frontend/src/components/ParameterViewsPanel.js`
- Delete: `frontend/src/components/ParameterViewsPanel.test.js`
- Create: `frontend/src/parameterInspectionModel.js`
- Create: `frontend/src/parameterInspectionModel.test.js`
- Modify: `frontend/src/simulationViewModel.js:13-20`
- Modify: `frontend/src/simulationViewModel.test.js:20-31`
- Modify: `frontend/src/App.js:1-255`
- Modify: `frontend/src/appFiles.test.js`
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`

**Interfaces:**
- Consumes: `manifest.parameter_inspection` and `manifest.geometry.surface_graph` from Task 2.
- Produces: `resolveParameterInspection(manifest) -> { status, errorCode, contract, surfaceGraph, indices }`.
- Produces: `defaultInspectionSelection(model)`, `mergeInspectionSelection(selection, patch)`, `annotationsForView(model, viewId, level, selection)`, and `sectionLoopForSelection(model, selection)`.

- [ ] **Step 1: Write failing pure-model tests**

Create tests for supported resolution, stale generation rejection, default selection, shared selection merge, annotation filtering, and station lookup:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { presets } from "./appModel.js";
import {
  ANNOTATION_LEVELS,
  INSPECTION_TABS,
  annotationsForView,
  defaultInspectionSelection,
  mergeInspectionSelection,
  resolveParameterInspection,
  sectionLoopForSelection,
} from "./parameterInspectionModel.js";

function manifestFixture() {
  const contract = {
    contract_version: "1.1.3",
    generation_id: "g1",
    source_geometry_patch_version: "1.1.2",
    source_canonical_payload_version: "1.1.2",
    blade_instances: {
      blade_0: { blade_instance_id: "blade_0", surface_ids: ["blade_0_pressure_surface"], span_station_ids: ["blade_0:span_0"] },
    },
    surface_references: {
      blade_0_pressure_surface: { surface_id: "blade_0_pressure_surface", blade_instance_id: "blade_0", face_family: "blade_pressure" },
    },
    span_stations: {
      "blade_0:span_0": { span_station_id: "blade_0:span_0", section_loop_id: "blade_0:span_0:loop", h: 0.1 },
    },
    section_loops: {
      "blade_0:span_0:loop": {
        section_loop_id: "blade_0:span_0:loop",
        span_station_id: "blade_0:span_0",
        segment_references: {
          pressure_side: { points_s_q: [[0, -1], [1, -1]], control_points_s_q: [[0, -1], [1, -1]] },
          trailing_edge: { points_s_q: [[1, -1], [1.1, 0], [1, 1]], control_points_s_q: [[1, -1], [1.1, 0], [1, 1]] },
          suction_side: { points_s_q: [[1, 1], [0, 1]], control_points_s_q: [[1, 1], [0, 1]] },
          leading_edge: { points_s_q: [[0, 1], [-0.1, 0], [0, -1]], control_points_s_q: [[0, 1], [-0.1, 0], [0, -1]] },
        },
        metrics: { join_status: "PASS" },
        join_metrics: { pressure_to_leading: { status: "PASS", position_gap_mm: 0 } },
      },
    },
    support_profiles: {},
    resolved_dimensions: {
      thickness_min_mm: { requested_value: 6.8, resolved_value: 6.8, unit: "mm", requested_unit: "mm" },
      thickness_max_mm: { requested_value: 18, resolved_value: 18, unit: "mm", requested_unit: "mm" },
    },
  };
  return {
    runtime_release_version: "1.1.3",
    generation_id: "g1",
    parameter_inspection: contract,
    geometry: {
      surface_graph: {
        generation_id: "g1",
        surfaces: [{ id: "blade_0_pressure_surface", uv_grid: [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]] }],
      },
    },
  };
}

test("declares the five approved tabs and three annotation levels", () => {
  assert.deepEqual(INSPECTION_TABS.map((tab) => tab.id), ["3d", "top", "meridional", "s_q", "quad"]);
  assert.deepEqual(ANNOTATION_LEVELS, ["key", "selected", "all"]);
});

test("resolves one matched manifest and rejects stale evidence", () => {
  assert.equal(resolveParameterInspection(manifestFixture()).status, "ready");
  const stale = manifestFixture();
  stale.geometry.surface_graph.generation_id = "g2";
  assert.equal(resolveParameterInspection(stale).errorCode, "parameter_inspection_generation_id_mismatch");
  const missingSurface = manifestFixture();
  missingSurface.geometry.surface_graph.surfaces = [];
  assert.equal(resolveParameterInspection(missingSurface).errorCode, "parameter_inspection_surface_reference_missing");
});

test("selects the first blade and station without mutation", () => {
  const model = resolveParameterInspection(manifestFixture());
  const selection = defaultInspectionSelection(model);
  const updated = mergeInspectionSelection(selection, { surfaceId: "blade_0_pressure_surface" });
  assert.equal(selection.surfaceId, null);
  assert.equal(updated.surfaceId, "blade_0_pressure_surface");
  assert.equal(sectionLoopForSelection(model, updated).section_loop_id, "blade_0:span_0:loop");
});

test("filters annotation levels deterministically", () => {
  const model = resolveParameterInspection(manifestFixture());
  const selection = defaultInspectionSelection(model);
  assert.ok(annotationsForView(model, "s_q", "key", selection).length > 0);
  assert.ok(annotationsForView(model, "s_q", "all", selection).length >= annotationsForView(model, "s_q", "key", selection).length);
});

test("active display names identify v1.1.3 while backend preset ids remain stable", () => {
  for (const preset of presets) {
    assert.match(preset.name, /v1\.1\.3/i);
    assert.match(preset.summary, /V1\.1\.3/);
    assert.match(preset.presetId, /_v1_1$/);
  }
});
```

Import `presets` from `appModel.js` in the test module for the release-label assertion.

- [ ] **Step 2: Run the model tests and verify the module is missing**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: FAIL because `parameterInspectionModel.js` does not exist.

- [ ] **Step 3: Implement the pure model and error codes**

Implement the exported constants and functions with these rules:

```javascript
export const INSPECTION_TABS = [
  { id: "3d", label: "3D" },
  { id: "top", label: "Top" },
  { id: "meridional", label: "Meridional" },
  { id: "s_q", label: "S-Q" },
  { id: "quad", label: "Quad" },
];

export const ANNOTATION_LEVELS = ["key", "selected", "all"];

export function resolveParameterInspection(manifest) {
  if (!manifest) return { status: "empty", errorCode: "parameter_inspection_not_generated" };
  const contract = manifest.parameter_inspection;
  const surfaceGraph = manifest.geometry?.surface_graph;
  if (contract?.contract_version !== "1.1.3") {
    return { status: "error", errorCode: "parameter_inspection_contract_unsupported" };
  }
  if (!surfaceGraph || contract.generation_id !== surfaceGraph.generation_id || contract.generation_id !== manifest.generation_id) {
    return { status: "error", errorCode: "parameter_inspection_generation_id_mismatch" };
  }
  const graphSurfaceIds = new Set((surfaceGraph.surfaces || []).map((surface) => surface.id));
  const contractSurfaceIds = Object.keys(contract.surface_references || {});
  if (contractSurfaceIds.some((surfaceId) => !graphSurfaceIds.has(surfaceId))) {
    return { status: "error", errorCode: "parameter_inspection_surface_reference_missing" };
  }
  const loops = contract.section_loops || {};
  if (Object.values(contract.span_stations || {}).some((station) => !loops[station.section_loop_id])) {
    return { status: "error", errorCode: "parameter_inspection_station_reference_missing" };
  }
  return {
    status: "ready",
    errorCode: null,
    contract,
    surfaceGraph,
    indices: {
      blades: contract.blade_instances,
      surfaces: contract.surface_references,
      stations: contract.span_stations,
      loops: contract.section_loops,
    },
  };
}

export function defaultInspectionSelection(model) {
  const bladeId = Object.keys(model.indices?.blades || {})[0] || null;
  const blade = bladeId ? model.indices.blades[bladeId] : null;
  return {
    bladeId,
    surfaceId: null,
    spanStationId: blade?.span_station_ids?.[0] || null,
    sectionSegmentId: null,
    controlPointId: null,
  };
}

export function mergeInspectionSelection(selection, patch) {
  return { ...selection, ...patch };
}

export function sectionLoopForSelection(model, selection) {
  const station = model.indices?.stations?.[selection.spanStationId];
  return station ? model.indices.loops?.[station.section_loop_id] || null : null;
}
```

Implement `annotationsForView` as a pure switch over `viewId`, returning records shaped as:

```javascript
{
  id: "s_q:thickness_min_mm",
  level: "key",
  label: "Thickness min",
  requestedValue: 6.8,
  resolvedValue: 6.8,
  unit: "mm",
  anchor: { kind: "section_loop", sectionLoopId: "blade_0:span_0:loop" },
}
```

Format records with both values as `requested -> resolved`; if the values are equal, show only the resolved value. Preserve `requested_unit` when it differs from the resolved unit, for example a thickness ratio resolving to millimetres.

Filter `key` to `level === "key"`, `selected` to key plus records matching the shared selection, and `all` to all records. Keep values from the contract; do not derive continuity or thickness in JavaScript.

- [ ] **Step 4: Remove the obsolete panel and add the central mode id**

Delete the four old Parameter views files. Remove the `ParameterViewsPanel` import and render call from `App.js`. Add this mode to `viewModeOptions` after Feature debug:

```javascript
{ id: "parameter_inspection", label: "Parameter inspection" },
```

Update the simulation-view test expected ids to include `parameter_inspection`.

Update the five active frontend preset display names, summaries, and version tags from V1.1.2 to V1.1.3. Do not change any `presetId` value or canonical preset payload.

- [ ] **Step 5: Run all frontend tests**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: all tests PASS and no source test refers to `ParameterViewsPanel` or `parameterViewModel`.

- [ ] **Step 6: Commit the inspection model**

```powershell
git add -A -- frontend/src
git commit -m "feat: add graphical inspection view model"
```

---

### Task 4: Implement the S-Q View and Annotation Overlay

**Files:**
- Create: `frontend/src/components/SectionLoopInspectionView.js`
- Create: `frontend/src/components/SectionLoopInspectionView.test.js`
- Create: `frontend/src/components/ParameterAnnotationOverlay.js`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `sectionLoopForSelection(model, selection)` and annotation records from Task 3.
- Produces: `SectionLoopInspectionView({ loop, selection, annotationLevel, onSelect })`.
- Produces: `ParameterAnnotationOverlay({ annotations, projectAnchor })`.

- [ ] **Step 1: Write failing component source-contract tests**

Assert that the S-Q component:

```javascript
assert.match(source, /actual-section-loop/);
assert.match(source, /control-polygon/);
assert.match(source, /control-point/);
assert.match(source, /pressure_side/);
assert.match(source, /suction_side/);
assert.match(source, /leading_edge/);
assert.match(source, /trailing_edge/);
assert.match(source, /onSelect/);
assert.doesNotMatch(source, /onChange/);
assert.doesNotMatch(source, /drag/);
```

Assert that the overlay contains deterministic leader and label classes and no mutation callback.

- [ ] **Step 2: Run tests and verify missing components**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: FAIL because both component modules are missing.

- [ ] **Step 3: Implement S-Q coordinate fitting and semantic segments**

Use `React.createElement` and an SVG `viewBox="0 0 1000 700"`. Flatten all segment points, compute finite bounds, apply 70 px padding, preserve aspect ratio, and invert Q only at the display transform. Render segment polylines with these classes:

```javascript
const SEGMENT_CLASS = {
  pressure_side: "pressure-side",
  suction_side: "suction-side",
  leading_edge: "leading-edge",
  trailing_edge: "trailing-edge",
};
```

Render actual sampled points as solid semantic curves. For `selected` and `all`, render dashed control polygons and button-like SVG circles for control points. Each circle calls:

```javascript
onSelect?.({
  sectionSegmentId: segment.section_segment_id,
  controlPointId: `${segment.section_segment_id}:cp_${pointIndex}`,
});
```

Render join status and the authoritative `position_gap_mm`, `tangent_angle_deg`, and `curvature_proxy_mismatch` values from `loop.join_metrics`; do not calculate them in SVG code.

- [ ] **Step 4: Implement deterministic annotation leaders**

`ParameterAnnotationOverlay` must accept already resolved annotations and a projection callback. Sort by `id`, group labels into 28 px vertical slots per viewport, and render:

```javascript
h("line", { className: "inspection-leader", x1: anchor.x, y1: anchor.y, x2: label.x, y2: label.y })
h("text", { className: "inspection-label", x: label.x + 6, y: label.y + 4 }, formattedValue)
```

Define the label text before creating the elements:

```javascript
const resolvedText = `${annotation.resolvedValue}${annotation.unit ? ` ${annotation.unit}` : ""}`;
const requestedText = `${annotation.requestedValue}${annotation.requestedUnit ? ` ${annotation.requestedUnit}` : ""}`;
const formattedValue = annotation.requestedValue === annotation.resolvedValue
  ? `${annotation.label}: ${resolvedText}`
  : `${annotation.label}: ${requestedText} -> ${resolvedText}`;
```

If an annotation is selected, add `selected` to both class names. Never omit a selected annotation when slots collide; place it in the next available slot.

- [ ] **Step 5: Add focused styles and run tests**

Add stable semantic colors, minimum SVG dimensions, non-scaling strokes, readable label backgrounds, and no negative letter spacing. Then run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: all tests PASS.

- [ ] **Step 6: Commit S-Q and annotations**

```powershell
git add -- frontend/src/components/SectionLoopInspectionView.js frontend/src/components/SectionLoopInspectionView.test.js frontend/src/components/ParameterAnnotationOverlay.js frontend/src/styles.css
git commit -m "feat: render resolved s-q inspection view"
```

---

### Task 5: Implement One Shared Three.js Inspection Scene

**Files:**
- Create: `frontend/src/inspectionSceneModel.js`
- Create: `frontend/src/inspectionSceneModel.test.js`
- Create: `frontend/src/components/InspectionScene.js`
- Create: `frontend/src/components/InspectionScene.test.js`
- Modify: `frontend/src/components/ModelViewer.js:376,766,958`

**Interfaces:**
- Consumes: the actual `surfaceGraph`, selected surface id, active layout, visibility state, and selection callback.
- Produces: `inspectionViewportRects(width, height, layout) -> Record<string, Rect>`.
- Produces: `orthographicCameraFrame(bounds, viewId, aspect) -> CameraFrame`.
- Produces: `InspectionScene({ manifest, surfaceGraph, layout, selectedSurfaceId, onSelectSurface, onProjectionError, visibleLayers, viewMode, annotationsByView })`.

- [ ] **Step 1: Write failing layout and camera tests**

Create pure tests:

```javascript
test("quad reserves one pane for S-Q and three for shared-scene cameras", () => {
  const rects = inspectionViewportRects(1200, 800, "quad");
  assert.deepEqual(Object.keys(rects), ["3d", "meridional", "s_q", "top"]);
  assert.deepEqual(rects["3d"], { x: 0, y: 400, width: 600, height: 400 });
  assert.deepEqual(rects["s_q"], { x: 0, y: 0, width: 600, height: 400 });
});

test("full-size layout allocates the complete viewport", () => {
  assert.deepEqual(inspectionViewportRects(900, 600, "3d")["3d"], { x: 0, y: 0, width: 900, height: 600 });
});

test("top and meridional frames are deterministic", () => {
  const bounds = { center: [0, 0, 0], radius: 500 };
  assert.deepEqual(orthographicCameraFrame(bounds, "top", 2).up, [0, 1, 0]);
  assert.deepEqual(orthographicCameraFrame(bounds, "meridional", 2).up, [0, 0, 1]);
});
```

The source test must assert exactly one `new THREE.WebGLRenderer`, one shared scene, `setScissorTest(true)`, three camera records, `Raycaster`, `ResizeObserver`, and cleanup of animation frame, controls, renderer, and observer.

- [ ] **Step 2: Run tests and verify missing modules**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: FAIL because the scene modules do not exist.

- [ ] **Step 3: Implement pure viewport and camera helpers**

Use lower-left WebGL coordinates in `inspectionViewportRects`. Full-size layouts return one rectangle. Quad returns equal quadrants in stable insertion order: 3D top-left, Meridional top-right, S-Q bottom-left, Top bottom-right.

`orthographicCameraFrame` returns position, target, up, and half-height:

```javascript
export function orthographicCameraFrame(bounds, viewId, aspect) {
  const radius = Math.max(Number(bounds.radius) || 1, 1);
  const distance = radius * 4;
  if (viewId === "top") {
    return { position: [0, 0, distance], target: [0, 0, 0], up: [0, 1, 0], halfHeight: radius * 1.15, aspect };
  }
  return { position: [0, -distance, 0], target: [0, 0, 0], up: [0, 0, 1], halfHeight: radius * 1.15, aspect };
}
```

- [ ] **Step 4: Export existing surface-graph helpers**

Prefix the three existing declarations in `ModelViewer.js` with `export`. The exact exported signatures are:

```javascript
export function createSurfaceGraphGroup(
  surfaceGraph,
  center,
  simulationViewMode,
  selectedSurfaceIds = new Set(),
  meshOverlayMode = "triangle_edges",
  manifest = null,
)
export function surfaceGraphBounds(surfaceGraph) { }
export function disposeObject(object) { }
```

Keep function bodies unchanged. Add an app source test proving `ModelViewer` still calls the same helpers for its CAD/CFD path.

- [ ] **Step 5: Implement one renderer, one scene, and scissor cameras**

`InspectionScene` creates one scene/group and these cameras:

```javascript
const cameras = {
  "3d": new THREE.PerspectiveCamera(45, 1, 0.1, 100000),
  top: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
  meridional: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000),
};
```

Use `createSurfaceGraphGroup(surfaceGraph, bounds.center, "cad_review_360", new Set(), "off", manifest)` once. Store each mesh material's baseline emissive, emissive intensity, and opacity in `userData`. When `selectedSurfaceId` changes, traverse the existing group and update only material highlight properties; do not rebuild geometry or create another scene. In each animation frame:

```javascript
renderer.setScissorTest(true);
for (const viewId of visibleGeometricViews(layout)) {
  const rect = rects[viewId];
  renderer.setViewport(rect.x, rect.y, rect.width, rect.height);
  renderer.setScissor(rect.x, rect.y, rect.width, rect.height);
  renderer.render(scene, cameras[viewId]);
}
```

Enable OrbitControls rotation only for the 3D camera. Orthographic cameras allow pan and zoom with rotation disabled. Activate controls only for the viewport under the pointer.

Use a single `THREE.Raycaster` to pick meshes. Convert pointer coordinates through the hit viewport rectangle, intersect the shared surface group, and call `onSelectSurface?.(surfaceId)` from `object.userData.surfaceId`.

Apply `viewerLayerVisibility` to the shared group after creation. Mesh children follow `showShadedSurfaces`, UV-wire children follow `showSurfaceUvWire`, and mesh-overlay children follow `showMeshEdges`, using the same `visibleLayers` checks as `ModelViewer`.

Resolve annotation anchors without deriving authoritative dimensions:

- `surface_centroid`: average the referenced surface `uv_grid` only to obtain a screen anchor;
- `profile_rz`: map `[r, z]` to `[r, 0, z]` for the meridional camera;
- `viewport_corner`: place a key summary in a fixed viewport label rail;
- S-Q anchors remain inside `SectionLoopInspectionView`.

Project geometric anchors through the active camera and viewport rectangle, then render `ParameterAnnotationOverlay` for each visible geometric viewport from `annotationsByView`.

If a selected annotation has no resolvable anchor or projects outside a finite coordinate range, call `onProjectionError?.("parameter_inspection_projection_failed")`. Optional nonselected labels may render as `unavailable`, but a selected projection failure must remain visible to the workspace.

- [ ] **Step 6: Implement cleanup and status hooks**

On unmount, cancel the animation frame, disconnect `ResizeObserver`, dispose all controls, remove and dispose the shared group, dispose the renderer, and remove its canvas. Add data attributes:

```text
data-testid="inspection-webgl"
data-renderer-count="1"
data-scene-surface-count="<number>"
```

These are inspection evidence hooks, not user-visible text.

- [ ] **Step 7: Run frontend tests and commit**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: all tests PASS.

Commit:

```powershell
git add -- frontend/src/inspectionSceneModel.js frontend/src/inspectionSceneModel.test.js frontend/src/components/InspectionScene.js frontend/src/components/InspectionScene.test.js frontend/src/components/ModelViewer.js frontend/src/appFiles.test.js
git commit -m "feat: add shared-scene inspection renderer"
```

---

### Task 6: Integrate the Full-size and Quad Inspection Workspace

**Files:**
- Create: `frontend/src/components/ParameterInspectionWorkspace.js`
- Create: `frontend/src/components/ParameterInspectionWorkspace.test.js`
- Modify: `frontend/src/App.js:260-321`
- Modify: `frontend/src/appFiles.test.js`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 3 model, Task 4 SVG/overlay components, and Task 5 shared scene.
- Produces: `ParameterInspectionWorkspace({ manifest, visibleLayers, viewMode })`.

- [ ] **Step 1: Write failing workspace and routing tests**

The component source test must assert:

```javascript
assert.match(source, /INSPECTION_TABS/);
assert.match(source, /ANNOTATION_LEVELS/);
assert.match(source, /useState\("3d"\)/);
assert.match(source, /InspectionScene/);
assert.match(source, /SectionLoopInspectionView/);
assert.match(source, /ParameterAnnotationOverlay/);
assert.match(source, /parameter_inspection_not_generated/);
assert.match(source, /maximize/);
assert.doesNotMatch(source, /onChange/);
assert.doesNotMatch(source, /onGeometry/);
```

The App source test must assert conditional routing:

```javascript
assert.match(appSource, /simulationViewMode === "parameter_inspection"/);
assert.match(appSource, /h\(ParameterInspectionWorkspace/);
assert.match(appSource, /h\(ModelViewer/);
assert.doesNotMatch(appSource, /ParameterViewsPanel/);
```

- [ ] **Step 2: Run tests and verify the component is missing**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: FAIL because `ParameterInspectionWorkspace.js` does not exist.

- [ ] **Step 3: Implement tabs, shared selection, and error states**

The workspace owns:

```javascript
const [activeTab, setActiveTab] = useState("3d");
const [annotationLevel, setAnnotationLevel] = useState("key");
const [projectionError, setProjectionError] = useState(null);
const model = useMemo(() => resolveParameterInspection(manifest), [manifest]);
const [selection, setSelection] = useState(() => defaultInspectionSelection(model));
```

Reset selection when `model.contract?.generation_id` changes. Do not reset selection when switching tabs.

For `empty`, render `Generate a model to inspect resolved geometry.` For `error`, render the exact `model.errorCode` and no geometry. For `ready`, render the toolbar and the active full-size or Quad content.

Pass `setProjectionError` as `onProjectionError`. Render `projectionError` as a nonmodal inspection error banner above the active view and clear it when the generation id, selection, or active tab changes.

Maximize controls call `setActiveTab(viewId)`. The full-size 3D tab is the initial state after every new generation.

When `InspectionScene` returns a surface id, resolve its contract reference and merge both fields so every view stays synchronized:

```javascript
function handleSurfaceSelection(surfaceId) {
  const reference = model.indices.surfaces[surfaceId];
  setSelection((current) => mergeInspectionSelection(current, {
    surfaceId,
    bladeId: reference?.blade_instance_id || current.bladeId,
  }));
}
```

Build `annotationsByView` with `annotationsForView(model, viewId, annotationLevel, selection)` for `3d`, `top`, and `meridional`. Pass the selected loop and S-Q annotations to `SectionLoopInspectionView`.

Add stable evidence selectors:

```text
data-testid="inspection-workspace"
data-active-tab={activeTab}
data-testid="inspection-tab-3d"
data-testid="inspection-tab-top"
data-testid="inspection-tab-meridional"
data-testid="inspection-tab-s_q"
data-testid="inspection-tab-quad"
data-testid="inspection-annotation-level"
```

- [ ] **Step 4: Wire the central application route**

Import `ParameterInspectionWorkspace` in `App.js` and replace the unconditional viewer call with:

```javascript
simulationViewMode === "parameter_inspection"
  ? h(ParameterInspectionWorkspace, {
      manifest,
      visibleLayers,
      viewMode,
    })
  : h(ModelViewer, {
      stlUrl,
      surfaceGraph: manifest?.geometry?.surface_graph || null,
      constructionLines: manifest?.geometry?.construction_lines || {},
      viewMode,
      setViewMode,
      simulationViewMode,
      meshOverlayMode,
      setMeshOverlayMode,
      selectedPatch,
      manifest,
      autoRotate,
      setAutoRotate,
      visibleLayers,
    })
```

Add `data-testid="generate-model"` to the Generate button and `data-testid={`simulation-mode-${mode.id}`}` to each central mode button so visual acceptance does not depend on display text.

- [ ] **Step 5: Add full-size, Quad, and responsive styles**

Use a central workspace shell with a fixed toolbar row and a content area. Quad uses `grid-template-columns: 1fr 1fr` and `grid-template-rows: 1fr 1fr`. Every pane has `min-width: 0`, `min-height: 0`, and stable overflow behavior. At `max-width: 820px`, Quad becomes one column with each pane using `aspect-ratio: 4 / 3`.

Ensure labels have opaque or translucent neutral backgrounds, controls stay above the canvas, and no font size scales with viewport width.

- [ ] **Step 6: Run the frontend suite**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: all tests PASS, including obsolete-panel absence and existing ModelViewer contracts.

- [ ] **Step 7: Commit the integrated workspace**

```powershell
git add -- frontend/src/components/ParameterInspectionWorkspace.js frontend/src/components/ParameterInspectionWorkspace.test.js frontend/src/App.js frontend/src/appFiles.test.js frontend/src/styles.css frontend/src/simulationViewModel.js frontend/src/simulationViewModel.test.js
git commit -m "feat: integrate v1.1.3 parameter inspection workspace"
```

---

### Task 7: Visual Acceptance, Regression Verification, and Evidence

**Files:**
- Create: `frontend/scripts/parameter-inspection-visual-smoke.cjs`
- Create: `docs/evidence/assets/v1.1.3-parameter-inspection/desktop-3d.png`
- Create: `docs/evidence/assets/v1.1.3-parameter-inspection/desktop-quad.png`
- Create: `docs/evidence/assets/v1.1.3-parameter-inspection/narrow-s-q.png`
- Create: `docs/evidence/2026-07-10-impeller-v1-1-3-semantic-change-log.md`
- Create: `docs/evidence/2026-07-10-impeller-v1-1-3-insight-log.md`
- Create: `docs/evidence/2026-07-10-impeller-v1-1-3-graphical-parameter-inspection-evidence.md`
- Modify: `docs/version-history.md`

**Interfaces:**
- Consumes: the complete backend/frontend implementation and local services.
- Produces: reproducible screenshots, nonblank pixel evidence, test results, and semantic documentation.

- [ ] **Step 1: Add a Playwright visual smoke script**

Use the bundled runtime packages without adding project dependencies. The script receives `CODEX_NODE_MODULES` and loads Playwright and PNGJS with `createRequire`:

```javascript
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const moduleRoot = process.env.CODEX_NODE_MODULES;
assert.ok(moduleRoot, "CODEX_NODE_MODULES is required");
const runtimeRequire = createRequire(path.join(moduleRoot, "playwright", "package.json"));
const { chromium } = runtimeRequire("playwright");
const { PNG } = runtimeRequire("pngjs");

function nonBackgroundRatio(buffer) {
  const png = PNG.sync.read(buffer);
  let changed = 0;
  for (let index = 0; index < png.data.length; index += 4) {
    const red = png.data[index];
    const green = png.data[index + 1];
    const blue = png.data[index + 2];
    if (Math.abs(red - 238) + Math.abs(green - 242) + Math.abs(blue - 240) > 24) changed += 1;
  }
  return changed / (png.width * png.height);
}

async function main() {
  const outputDir = path.resolve("docs/evidence/assets/v1.1.3-parameter-inspection");
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto("http://127.0.0.1:5199", { waitUntil: "networkidle" });
    await page.locator('[data-testid="generate-model"]').click();
    await page.locator('[data-testid="generate-model"]:not([disabled])').waitFor({ timeout: 300000 });
    await page.locator('[data-testid="simulation-mode-parameter_inspection"]').click();
    const canvas = page.locator('[data-testid="inspection-webgl"]');
    await canvas.waitFor({ state: "visible", timeout: 300000 });
    assert.equal(await canvas.getAttribute("data-renderer-count"), "1");
    assert.ok(Number(await canvas.getAttribute("data-scene-surface-count")) > 0);

    const canvasBuffer = await canvas.screenshot();
    const ratio = nonBackgroundRatio(canvasBuffer);
    assert.ok(ratio >= 0.05, `inspection canvas ratio ${ratio} is below 0.05`);
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "desktop-3d.png"),
    });
    console.log("parameter inspection desktop 3D: PASS");

    await page.locator('[data-testid="inspection-tab-quad"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="quad"]').waitFor();
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "desktop-quad.png"),
    });
    console.log("parameter inspection desktop Quad: PASS");

    await page.setViewportSize({ width: 768, height: 1100 });
    await page.locator('[data-testid="inspection-tab-s_q"]').click();
    await page.locator('[data-testid="inspection-workspace"][data-active-tab="s_q"]').waitFor();
    await page.locator('[data-testid="inspection-workspace"]').screenshot({
      path: path.join(outputDir, "narrow-s-q.png"),
    });
    console.log("parameter inspection narrow S-Q: PASS");
    console.log(`inspection canvas non-background ratio: ${ratio.toFixed(4)}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
```

Launch Chromium, visit `http://127.0.0.1:5199`, click `[data-testid="generate-model"]`, wait for generation to finish, click `[data-testid="simulation-mode-parameter_inspection"]`, and wait for `[data-testid="inspection-webgl"][data-scene-surface-count]`. Assert `data-renderer-count === "1"` and a positive surface count.

Capture desktop 3D at `1440 x 1000`, click `[data-testid="inspection-tab-quad"]` for the desktop Quad screenshot, then resize to `768 x 1100`, click `[data-testid="inspection-tab-s_q"]`, and capture full-size S-Q. For the 3D canvas screenshot, assert `nonBackgroundRatio(buffer) >= 0.05`.

- [ ] **Step 2: Start clean local services from this worktree**

Backend:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8061
```

Frontend in a second terminal:

```powershell
Set-Location frontend
python -m http.server 5199 -b 127.0.0.1
```

Expected: `/api/presets/impeller` and the frontend root both return HTTP 200.

- [ ] **Step 3: Run Playwright screenshots and pixel checks**

Use the bundled dependency path reported by `codex_app__load_workspace_dependencies`:

```powershell
$env:CODEX_NODE_MODULES = "C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
& "C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" frontend/scripts/parameter-inspection-visual-smoke.cjs
```

Expected output:

```text
parameter inspection desktop 3D: PASS
parameter inspection desktop Quad: PASS
parameter inspection narrow S-Q: PASS
inspection canvas non-background ratio: >= 0.05
```

Visually inspect the three PNG files for nonblank geometry, correct framing, readable labels, no control overlap, distinct view orientation, and synchronized selected-object color.

- [ ] **Step 4: Run backend focused and regression suites**

Run:

```powershell
python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py tests/test_impeller_v11_3_service_manifest.py -q
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_mesh_and_export_contract.py -q
python -m pytest tests/test_impeller_geometry_validation.py tests/test_impeller_bounded_brep_export.py -q
```

Expected: all tests PASS with V1.1.2 geometry assertions unchanged.

- [ ] **Step 5: Run the full frontend suite**

Run:

```powershell
Set-Location frontend
npm.cmd test
```

Expected: all tests PASS.

- [ ] **Step 6: Write semantic, insight, and evidence records**

The semantic change log must state that V1.1.3 changes the runtime and inspection contract only, while geometry/canonical versions remain V1.1.2.

The insight log must record:

```text
Textual preset summaries cannot prove that resolved parameters are represented by generated geometry.
Independent view renderers risk geometry/state drift and unnecessary GPU duplication.
S-Q is a mathematical section domain and is clearer as SVG than as an arbitrary 3D camera projection.
Read-only inspection must precede direct graphical editing so the parameter-to-geometry mapping can be evaluated first.
```

The evidence log must include exact test commands/results, all five preset contract results, the renderer count, pixel ratio, screenshot paths, and any residual limitations.

- [ ] **Step 7: Update version history and verify the worktree**

Add a V1.1.3 entry to `docs/version-history.md` with runtime/geometry version separation and the graphical inspection feature. Then run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended V1.1.3 evidence, script, screenshot, and documentation files remain uncommitted.

- [ ] **Step 8: Commit acceptance evidence**

```powershell
git add -- frontend/scripts/parameter-inspection-visual-smoke.cjs docs/evidence docs/version-history.md
git commit -m "docs: record v1.1.3 inspection evidence"
```

- [ ] **Step 9: Request final code review**

Use `superpowers:requesting-code-review` against the complete V1.1.3 commit range. Address Critical and Important findings, rerun the affected focused tests, and record the review result in the evidence log before integration.

---

## Final Verification Checklist

- [ ] `runtime_release_version` and inspection contract report `1.1.3`.
- [ ] Geometry and canonical payload still report `1.1.2`.
- [ ] All five active preset ids synthesize without aliases or new ids.
- [ ] The old text-only Parameter views files and UI are absent.
- [ ] Parameter inspection opens in full-size 3D by default.
- [ ] Top and Meridional use the same generated scene and deterministic orthographic cameras.
- [ ] S-Q shows the actual selected loop plus canonical control geometry.
- [ ] Quad displays four distinct panes and each pane maximizes correctly.
- [ ] Selection survives tab changes and synchronizes across all views.
- [ ] `key`, `selected`, and `all` annotation levels produce deterministic subsets.
- [ ] Inspection callbacks cannot mutate geometry or transition overrides.
- [ ] Stale generation ids render an explicit error instead of mixed evidence.
- [ ] One WebGL renderer/context is used for all geometric inspection views.
- [ ] Desktop and narrow screenshots are nonblank, correctly framed, and free of incoherent overlap.
- [ ] V1.1.2 and V1.1 geometry, export, validation, and frontend regressions pass.
