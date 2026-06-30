# Impeller Ontology DSL Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `AxisymmetricThroughflowRadialBladedImpeller` ontology slice and JSON DSL structure, then migrate the current impeller synthesis path to load that DSL while preserving the existing API.

**Architecture:** Add JSON ontology/DSL resources as the canonical source of truth, including a first-class NURBS shape-control layer for control nets, semantic handles, and staged optimization variables. A small Python loader/compiler turns those resources into the existing runtime `rule.json` shape, and a refactored axisymmetric impeller kernel exposes all four blade boundaries plus tip-support and shape-control semantics in the manifest. Keep the public API stable while adding richer manifest fields and frontend controls mapped to DSL sections.

**Tech Stack:** Python 3.12, FastAPI, standard-library `json`/`pathlib`, pytest, JavaScript frontend tests with the existing npm setup, existing sampled surface-graph preview exporter.

---

## Worktree Note

`C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis` is currently not a git repository. A real `git worktree` cannot be created until the project is either initialized as a git repo or replaced by the actual repo checkout.

This plan therefore starts with Task 0. Do not implement Tasks 1+ in the current directory until Task 0 has produced an isolated worktree or an explicit decision to work in place.

---

## File Structure

Create JSON resources:

- `src/part_rule_synthesis/ontology/impeller/v0_2/slice.json`: scope and identity of `AxisymmetricThroughflowRadialBladedImpeller`.
- `src/part_rule_synthesis/ontology/impeller/v0_2/entities.json`: canonical entity vocabulary.
- `src/part_rule_synthesis/ontology/impeller/v0_2/relations.json`: relation vocabulary.
- `src/part_rule_synthesis/ontology/impeller/v0_2/shape_control_schema.json`: allowed NURBS representations, topology locks, optimization stages, and target policy requirements.
- `src/part_rule_synthesis/ontology/impeller/v0_2/validity_contracts.json`: geometry/topology/engineering contracts.
- `src/part_rule_synthesis/ontology/impeller/v0_2/loss_schema.json`: structured loss record shape.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/schema.json`: constructor-family schema.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/open_impeller.json`: open variant.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/closed_impeller.json`: closed variant.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/shape_controls/default_shape_controls.json`: default stage-1 NURBS shape-control policies for support profiles, blade boundaries, blade surface, thickness, closures, and fillets.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/presets/radial_open_reference.json`: new open preset.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/presets/radial_closed_reference.json`: new closed preset.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/aliases.json`: legacy preset aliases.

Create Python modules:

- `src/part_rule_synthesis/impeller_dsl_resources.py`: load and validate JSON resources.
- `src/part_rule_synthesis/impeller_runtime_compiler.py`: compile JSON constructor/preset data into the runtime DSL consumed by `RuleSynthesisService`.
- `src/part_rule_synthesis/impeller_shape_control.py`: validate shape-control policies and normalize editable/optimizable NURBS variables for the compiler and manifest.

Create frontend modules/components:

- `frontend/src/workspaceModel.js`: viewer layer definitions, surface/line classification, and manifest-derived workspace stats.
- `frontend/src/workspaceModel.test.js`: Node test coverage for workspace layer classification.
- `frontend/src/components/GeometryLayerPanel.js`: checkboxes and legend for shaded surfaces, support surfaces, blade boundaries, UV lines, edge closures, and validity overlays.

Modify existing files:

- `src/part_rule_synthesis/impeller_taxonomy.py`: expose `ONTOLOGY`, `IMPELLER_FACET_AXES`, `IMPELLER_PRESETS`, and legacy facets from the new loader/compiler while keeping import compatibility.
- `src/part_rule_synthesis/service.py`: include constructor-family metadata, new parameter specs, manifest fields, and compiled DSL sections.
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`: replace implicit blade boundary logic with explicit root/tip/leading/trailing boundary objects.
- `src/part_rule_synthesis/api.py`: keep endpoints stable; no route changes expected.
- `frontend/src/appModel.js`: expose DSL-section-aligned parameters and new open/closed preset IDs while retaining legacy aliases for API calls during transition.
- `frontend/src/components/ParameterPanel.js`: show parameter groups if not already supported.
- `frontend/src/components/ManifestPanel.js`: display ontology slice, constructor family, and validity categories.
- `frontend/src/components/ModelViewer.js`: show named boundary and surface-graph construction lines from the new manifest keys.
- `frontend/src/App.js`: hold workspace state for selected layer visibility, selected surface, and generate/reset behavior.

Create/modify tests:

- `tests/test_impeller_ontology_dsl_resources.py`: JSON resource and loader tests.
- `tests/test_impeller_shape_control.py`: shape-control schema, policy, and optimization-stage tests.
- `tests/test_impeller_runtime_compiler.py`: compiler and alias tests.
- `tests/test_impeller_kernel_boundaries.py`: four-boundary geometry tests.
- `tests/test_acceptance.py`: extend API-level acceptance coverage.
- `frontend/src/appModel.test.js`: parameter and preset model tests.
- `frontend/src/workspaceModel.test.js`: viewer layer and manifest summary tests.

---

## Interactive Frontend Design Target

The frontend should be an impeller design workspace, not a marketing page and not just a raw parameter form.

The first screen should keep the existing three-column application structure:

- left: preset choice and DSL-section parameter editing,
- center: full-size 3D surface-graph viewer,
- right: manifest, selected surface, validity, export links, and loss/status data.

The workspace must support these interactions:

- choose open or closed radial reference constructor,
- edit key DSL-section parameters with direct numeric inputs,
- edit shape through semantic handles first, and optionally inspect direct NURBS control
  variables when advanced mode is enabled,
- generate the model through the existing API,
- toggle shaded surfaces, support surfaces, blade pressure/suction surfaces, edge closures, primary blade boundaries, UV lines, and axes,
- click or select a surface/line and inspect its `id`, `role`, `ontology_id`, `material`, and boundary relation,
- compare whether changing leading/trailing edge controls changes the intended `u=0` and `u=1` boundaries,
- inspect geometry validity, topology validity, and engineering warnings without reading raw JSON first,
- inspect shape-control provenance, locked topology, editable variables, and future
  optimization variables,
- export STL/STEP from the run manifest.

The viewer must not show STL triangle wireframe as the engineering wireframe. All displayed wireframe layers must come from `surface_graph`, `named_boundary_curves`, and `construction_lines`.

The first frontend implementation can use source-level tests and manual visual smoke checks. It does not need to introduce a new UI library or a full browser E2E dependency.

---

### Task 0: Establish Git Repo And Isolated Worktree

**Files:**
- No source files modified unless initializing local git metadata.
- Possible create/modify: `.gitignore`

- [ ] **Step 1: Confirm current repo status**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis"
git rev-parse --show-toplevel
```

Expected current result:

```text
fatal: not a git repository (or any of the parent directories): .git
```

- [ ] **Step 2: If the real repo exists elsewhere, stop and switch to it**

Run this only to search nearby directories:

```powershell
Get-ChildItem -Force "C:\Users\CHEN Li\Documents\TurboJetCase" -Directory |
  ForEach-Object {
    $candidate = Join-Path $_.FullName ".git"
    if (Test-Path $candidate) { $_.FullName }
  }
```

Expected if no nearby repo exists:

```text
<no output>
```

If this prints a path, use that repo as the implementation root and re-check whether it contains `part-rule-synthesis`.

- [ ] **Step 3: If no real repo exists, initialize a local repo**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis"
git init
@"
.worktrees/
worktrees/
frontend/node_modules/
runs/
.pytest_cache/
__pycache__/
"@ | Add-Content -Encoding UTF8 .gitignore
git add .
git commit -m "chore: baseline part rule synthesis project"
```

Expected:

```text
[main (root-commit) ...] chore: baseline part rule synthesis project
```

- [ ] **Step 4: Create the isolated worktree**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis"
git check-ignore -q .worktrees
git worktree add ".worktrees\impeller-ontology-dsl-slice" -b "feature/impeller-ontology-dsl-slice"
cd ".worktrees\impeller-ontology-dsl-slice"
```

Expected:

```text
Preparing worktree (new branch 'feature/impeller-ontology-dsl-slice')
HEAD is now at ...
```

- [ ] **Step 5: Run baseline tests in the worktree**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
python -m pytest tests -q
python -m compileall -q src scripts
cd frontend
npm.cmd test
npm.cmd run build
```

Expected:

```text
pytest: all tests pass
compileall: no output
npm test: all tests pass
npm build: build completes
```

- [ ] **Step 6: Commit worktree setup only if files changed**

Run:

```powershell
git status --short
```

If only `.gitignore` was changed during initialization, it is already committed in Step 3. If any unintended generated files appear, remove only generated files that are outside source/doc/test paths.

---

### Task 1: Add JSON Ontology And DSL Resource Files

**Files:**
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/slice.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/entities.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/relations.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/shape_control_schema.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/validity_contracts.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_2/loss_schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/open_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/closed_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/shape_controls/default_shape_controls.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/presets/radial_open_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/presets/radial_closed_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/aliases.json`
- Test: `tests/test_impeller_ontology_dsl_resources.py`

- [ ] **Step 1: Write failing JSON-resource tests**

Add `tests/test_impeller_ontology_dsl_resources.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = PROJECT_ROOT / "src" / "part_rule_synthesis" / "ontology" / "impeller" / "v0_2"
DSL_ROOT = (
    PROJECT_ROOT
    / "src"
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_2"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_impeller_ontology_slice_files_exist_and_are_valid_json():
    for name in [
        "slice.json",
        "entities.json",
        "relations.json",
        "shape_control_schema.json",
        "validity_contracts.json",
        "loss_schema.json",
    ]:
        data = _read_json(ONTOLOGY_ROOT / name)
        assert isinstance(data, dict)


def test_impeller_slice_names_axisymmetric_throughflow_radial_bladed_constructor():
    slice_data = _read_json(ONTOLOGY_ROOT / "slice.json")

    assert slice_data["slice_id"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert slice_data["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert slice_data["in_scope"]["flow_topology"] == ["radial"]
    assert "mixed_flow" in slice_data["out_of_scope"]
    assert "recessed_vortex" in slice_data["out_of_scope"]


def test_impeller_entities_include_tip_support_and_four_blade_boundaries():
    entities = _read_json(ONTOLOGY_ROOT / "entities.json")

    assert "blade_tip_support_surface" in entities["support_surfaces"]
    assert "shape_control_policy" in entities["shape_control"]
    assert "semantic_handle" in entities["shape_control"]
    assert "blade_root_boundary" in entities["blade"]
    assert "blade_tip_boundary" in entities["blade"]
    assert "leading_edge_boundary" in entities["blade"]
    assert "trailing_edge_boundary" in entities["blade"]


def test_impeller_shape_control_schema_defines_staged_nurbs_optimization():
    schema = _read_json(ONTOLOGY_ROOT / "shape_control_schema.json")

    assert schema["shape_control_schema_version"] == "0.2"
    assert schema["default_stage"] == 1
    assert [stage["stage"] for stage in schema["optimization_stages"]] == [1, 2, 3, 4]
    assert schema["optimization_stages"][0]["degree"] == "locked"
    assert schema["optimization_stages"][0]["control_point_count"] == "locked"
    assert schema["optimization_stages"][0]["knot_vector"] == "locked"
    assert schema["optimization_stages"][0]["control_point_coordinates"] == "editable_optimizable"


def test_impeller_validity_contracts_cover_geometry_topology_and_warnings():
    contracts = _read_json(ONTOLOGY_ROOT / "validity_contracts.json")

    assert "blade_root_boundary_conforms_to_hub_support_surface" in contracts["geometry_contracts"]
    assert "blade_tip_boundary_conforms_to_blade_tip_support_surface" in contracts["geometry_contracts"]
    assert "control_net_dimension_matches_degree" in contracts["geometry_contracts"]
    assert "nurbs_knot_vector_non_decreasing" in contracts["geometry_contracts"]
    assert "blade_has_four_primary_boundaries" in contracts["topology_contracts"]
    assert "wrap_angle_plausibility" in contracts["engineering_warnings"]


def test_impeller_dsl_schema_and_constructors_encode_open_closed_tip_support_roles():
    schema = _read_json(DSL_ROOT / "schema.json")
    open_constructor = _read_json(DSL_ROOT / "constructors" / "open_impeller.json")
    closed_constructor = _read_json(DSL_ROOT / "constructors" / "closed_impeller.json")
    shape_controls = _read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")

    assert schema["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert "blade_boundaries" in schema["required_sections"]
    assert "shape_control" in schema["required_sections"]
    assert open_constructor["shape_control"]["shape_control_ref"] == "shape_controls/default_shape_controls.json"
    assert closed_constructor["shape_control"]["shape_control_ref"] == "shape_controls/default_shape_controls.json"
    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["role"] == "reference_only"
    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is False
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["role"] == "front_shroud_inner_surface"
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is True
    assert "hub_meridional_profile" in shape_controls["target_entities"]
    assert shape_controls["policies"]["hub_meridional_profile"]["representation_topology"]["knot_policy"] == "clamped_uniform"


def test_impeller_presets_bind_to_new_constructors_and_alias_legacy_ids():
    aliases = _read_json(DSL_ROOT / "aliases.json")
    open_preset = _read_json(DSL_ROOT / "presets" / "radial_open_reference.json")
    closed_preset = _read_json(DSL_ROOT / "presets" / "radial_closed_reference.json")

    assert open_preset["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert closed_preset["constructor_id"] == "axisymmetric_throughflow_radial_bladed.closed"
    assert aliases["legacy_preset_aliases"]["axisymmetric_nurbs_open_throughflow_study"] == "radial_open_reference"
    assert aliases["legacy_preset_aliases"]["axisymmetric_nurbs_closed_throughflow_study"] == "radial_closed_reference"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_ontology_dsl_resources.py -q
```

Expected:

```text
FAILED ... FileNotFoundError
```

- [ ] **Step 3: Create ontology JSON files**

Create `src/part_rule_synthesis/ontology/impeller/v0_2/slice.json` with the accepted spec content:

```json
{
  "ontology_version": "0.2",
  "slice_id": "impeller.axisymmetric_throughflow_radial_bladed",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "definition": "A radial throughflow impeller constructor whose blade passages are bounded by axisymmetric hub and blade-tip support surfaces, and whose blades are finite-thickness surface graphs with pressure/suction sides, leading/trailing edge closures, root/tip treatment, and explicit material-domain contracts.",
  "in_scope": {
    "part_family": ["impeller"],
    "flow_topology": ["radial"],
    "passage_topology": ["throughflow_bladed_channel"],
    "shroud_topology": ["open", "closed"],
    "entry_topology": ["single_entry"],
    "blade_population": ["full_blade_set"],
    "support_surface_model": ["axisymmetric_revolved_meridional_profiles"],
    "blade_surface_model": ["meanline_thickness_edge_surface_graph"]
  },
  "out_of_scope": [
    "mixed_flow",
    "axial_flow",
    "recessed_vortex",
    "single_channel",
    "multi_channel",
    "cutter",
    "double_entry",
    "splitter_blades",
    "non_axisymmetric_support_surfaces"
  ],
  "source_refs": [
    "ksb_impeller",
    "cfturbo_meridional_contour",
    "cfturbo_blade_profiles",
    "cfturbo_blade_edges",
    "caeses_shrouded_impeller_geometry",
    "agromayor_2021_unified_parametrization"
  ]
}
```

Create `entities.json`, `relations.json`, `shape_control_schema.json`, `validity_contracts.json`, and `loss_schema.json` from Sections 7, 8, 11A, 16, and 17 of `docs/superpowers/specs/2026-06-30-impeller-ontology-dsl-slice-design.md`.

- [ ] **Step 4: Create DSL JSON files**

Create `schema.json`, `open_impeller.json`, `closed_impeller.json`, `shape_controls/default_shape_controls.json`, and two preset files from Sections 11A-15 of the spec. Use these preset IDs:

```json
{
  "open": "radial_open_reference",
  "closed": "radial_closed_reference"
}
```

Create `aliases.json`:

```json
{
  "legacy_preset_aliases": {
    "axisymmetric_nurbs_open_throughflow_study": "radial_open_reference",
    "axisymmetric_nurbs_closed_throughflow_study": "radial_closed_reference"
  }
}
```

- [ ] **Step 5: Run resource tests**

Run:

```powershell
python -m pytest tests/test_impeller_ontology_dsl_resources.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/ontology src/part_rule_synthesis/dsl tests/test_impeller_ontology_dsl_resources.py
git commit -m "feat: add impeller ontology and dsl json resources"
```

---

### Task 2: Add Shape-Control Validator, JSON Loader, And Runtime Compiler

**Files:**
- Create: `src/part_rule_synthesis/impeller_shape_control.py`
- Create: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Create: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_shape_control.py`
- Test: `tests/test_impeller_runtime_compiler.py`

- [ ] **Step 1: Write failing shape-control tests**

Create `tests/test_impeller_shape_control.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_shape_control import normalize_shape_control_space


def test_shape_control_space_exposes_required_target_entities_and_stage_one_locks():
    bundle = load_impeller_dsl_bundle()

    space = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)

    assert space["schema_version"] == "0.2"
    assert space["optimization_stage"] == 1
    assert space["locked_topology"] is True
    assert "hub_meridional_profile" in space["active_policies"]
    assert "blade_tip_meridional_profile" in space["active_policies"]
    assert "leading_edge_boundary" in space["active_policies"]
    assert "trailing_edge_boundary" in space["active_policies"]
    assert "blade_mean_surface" in space["active_policies"]
    assert "blade_thickness_distribution" in space["active_policies"]


def test_shape_control_space_separates_semantic_handles_from_direct_variables():
    bundle = load_impeller_dsl_bundle()

    space = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)

    semantic_ids = {handle["id"] for handle in space["semantic_handles"]}
    variable_ids = {variable["id"] for variable in space["editable_variables"]}

    assert "hub_base_radius" in semantic_ids
    assert "hub_nose_radius" in semantic_ids
    assert "hub_cp_0_r" in variable_ids
    assert "hub_cp_0_z" in variable_ids
    assert space["optimizable_variables"]
    assert all(variable["topology_locked"] for variable in space["editable_variables"])
```

- [ ] **Step 2: Write failing loader/compiler tests**

Create `tests/test_impeller_runtime_compiler.py`:

```python
from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_load_impeller_dsl_bundle_returns_slice_schema_constructors_presets_and_aliases():
    bundle = load_impeller_dsl_bundle()

    assert bundle.slice["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert bundle.shape_control_schema["default_stage"] == 1
    assert "hub_meridional_profile" in bundle.shape_controls["target_entities"]
    assert bundle.schema["dsl_version"] == "0.2"
    assert "axisymmetric_throughflow_radial_bladed.open" in bundle.constructors
    assert "axisymmetric_throughflow_radial_bladed.closed" in bundle.constructors
    assert "radial_open_reference" in bundle.presets
    assert bundle.aliases["axisymmetric_nurbs_open_throughflow_study"] == "radial_open_reference"


def test_compile_impeller_runtime_preset_resolves_legacy_alias_and_preserves_api_fields():
    runtime = compile_impeller_runtime_preset("axisymmetric_nurbs_open_throughflow_study")

    assert runtime["version"] == "0.2.0"
    assert runtime["part_family"] == "impeller"
    assert runtime["preset_id"] == "radial_open_reference"
    assert runtime["legacy_preset_id"] == "axisymmetric_nurbs_open_throughflow_study"
    assert runtime["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert runtime["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert runtime["facets"]["flow_topology"] == "radial"
    assert runtime["facets"]["shroud_topology"] == "open"
    assert runtime["shape_control"]["optimization_stage"] == 1
    assert runtime["shape_control"]["locked_topology"] is True
    assert "hub_base_radius" in {handle["id"] for handle in runtime["shape_control"]["semantic_handles"]}
    assert "blade_boundaries" in runtime["dsl_sections"]
    assert "leading_edge_lean_deg" in runtime["parameters"]
    assert "trailing_edge_lean_deg" in runtime["parameters"]


def test_compile_impeller_runtime_preset_rejects_unknown_preset():
    with pytest.raises(ValueError, match="unknown impeller preset"):
        compile_impeller_runtime_preset("not_a_preset")
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_shape_control.py tests/test_impeller_runtime_compiler.py -q
```

Expected:

```text
FAILED ... ModuleNotFoundError
```

- [ ] **Step 4: Implement shape-control normalization**

Create `src/part_rule_synthesis/impeller_shape_control.py`:

```python
from __future__ import annotations

from typing import Any


def normalize_shape_control_space(
    shape_control_schema: dict[str, Any],
    shape_controls: dict[str, Any],
) -> dict[str, Any]:
    default_stage = int(shape_control_schema["default_stage"])
    stage_def = next(
        stage for stage in shape_control_schema["optimization_stages"] if int(stage["stage"]) == default_stage
    )
    locked_topology = (
        stage_def["degree"] == "locked"
        and stage_def["control_point_count"] == "locked"
        and stage_def["knot_vector"] == "locked"
    )

    editable_variables: list[dict[str, Any]] = []
    optimizable_variables: list[dict[str, Any]] = []
    semantic_handles: list[dict[str, Any]] = []
    active_policies = shape_controls["policies"]

    for target_entity, policy in active_policies.items():
        topology = policy["representation_topology"]
        _validate_policy_topology(target_entity, topology)
        for variable in policy.get("control_variables", []):
            normalized_variable = {
                **variable,
                "target_entity": target_entity,
                "topology_locked": locked_topology,
            }
            if variable.get("editable", False):
                editable_variables.append(normalized_variable)
            if variable.get("optimizable", False):
                optimizable_variables.append(normalized_variable)
        for handle in policy.get("semantic_handles", []):
            semantic_handles.append({**handle, "target_entity": target_entity})

    return {
        "schema_version": shape_control_schema["shape_control_schema_version"],
        "optimization_stage": default_stage,
        "locked_topology": locked_topology,
        "active_policies": list(active_policies.keys()),
        "semantic_handles": semantic_handles,
        "editable_variables": editable_variables,
        "optimizable_variables": optimizable_variables,
    }


def _validate_policy_topology(target_entity: str, topology: dict[str, Any]) -> None:
    degree = int(topology["degree"])
    control_point_count = int(topology["control_point_count"])
    if degree < 1:
        raise ValueError(f"{target_entity} NURBS degree must be positive")
    if control_point_count <= degree:
        raise ValueError(f"{target_entity} control point count must exceed degree")
    if topology["knot_policy"] != "clamped_uniform":
        raise ValueError(f"{target_entity} only clamped_uniform knot policy is supported in v0.2")
    if topology["weights"] != "unit":
        raise ValueError(f"{target_entity} only unit weights are supported in v0.2")
```

- [ ] **Step 5: Implement JSON loader**

Create `src/part_rule_synthesis/impeller_dsl_resources.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
ONTOLOGY_ROOT = PACKAGE_ROOT / "ontology" / "impeller" / "v0_2"
DSL_ROOT = PACKAGE_ROOT / "dsl" / "impeller" / "axisymmetric_throughflow_radial_bladed" / "v0_2"


@dataclass(frozen=True)
class ImpellerDslBundle:
    slice: dict[str, Any]
    entities: dict[str, Any]
    relations: dict[str, Any]
    shape_control_schema: dict[str, Any]
    validity_contracts: dict[str, Any]
    loss_schema: dict[str, Any]
    schema: dict[str, Any]
    constructors: dict[str, dict[str, Any]]
    shape_controls: dict[str, Any]
    presets: dict[str, dict[str, Any]]
    aliases: dict[str, str]


def load_impeller_dsl_bundle() -> ImpellerDslBundle:
    constructors = {
        "axisymmetric_throughflow_radial_bladed.open": _read_json(DSL_ROOT / "constructors" / "open_impeller.json"),
        "axisymmetric_throughflow_radial_bladed.closed": _read_json(DSL_ROOT / "constructors" / "closed_impeller.json"),
    }
    presets = {
        "radial_open_reference": _read_json(DSL_ROOT / "presets" / "radial_open_reference.json"),
        "radial_closed_reference": _read_json(DSL_ROOT / "presets" / "radial_closed_reference.json"),
    }
    aliases = _read_json(DSL_ROOT / "aliases.json")["legacy_preset_aliases"]
    bundle = ImpellerDslBundle(
        slice=_read_json(ONTOLOGY_ROOT / "slice.json"),
        entities=_read_json(ONTOLOGY_ROOT / "entities.json"),
        relations=_read_json(ONTOLOGY_ROOT / "relations.json"),
        shape_control_schema=_read_json(ONTOLOGY_ROOT / "shape_control_schema.json"),
        validity_contracts=_read_json(ONTOLOGY_ROOT / "validity_contracts.json"),
        loss_schema=_read_json(ONTOLOGY_ROOT / "loss_schema.json"),
        schema=_read_json(DSL_ROOT / "schema.json"),
        constructors=constructors,
        shape_controls=_read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json"),
        presets=presets,
        aliases=aliases,
    )
    _validate_bundle(bundle)
    return bundle


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_bundle(bundle: ImpellerDslBundle) -> None:
    family = "AxisymmetricThroughflowRadialBladedImpeller"
    if bundle.slice["constructor_family"] != family:
        raise ValueError("impeller ontology slice constructor family mismatch")
    if bundle.schema["constructor_family"] != family:
        raise ValueError("impeller DSL schema constructor family mismatch")
    if bundle.shape_control_schema["default_stage"] != 1:
        raise ValueError("impeller v0.2 shape control must default to stage 1")
    if "hub_meridional_profile" not in bundle.shape_controls["target_entities"]:
        raise ValueError("default shape controls must include hub_meridional_profile")
    for constructor_id, constructor in bundle.constructors.items():
        if constructor["constructor_id"] != constructor_id:
            raise ValueError(f"constructor id mismatch: {constructor_id}")
        missing = set(bundle.schema["required_sections"]) - set(constructor)
        if missing:
            raise ValueError(f"constructor {constructor_id} missing sections: {sorted(missing)}")
        if constructor["shape_control"]["shape_control_ref"] != "shape_controls/default_shape_controls.json":
            raise ValueError(f"constructor {constructor_id} references unsupported shape control policy")
    for preset_id, preset in bundle.presets.items():
        if preset["preset_id"] != preset_id:
            raise ValueError(f"preset id mismatch: {preset_id}")
        if preset["constructor_id"] not in bundle.constructors:
            raise ValueError(f"preset {preset_id} references unknown constructor")
```

- [ ] **Step 6: Implement runtime compiler**

Create `src/part_rule_synthesis/impeller_runtime_compiler.py`:

```python
from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_shape_control import normalize_shape_control_space


IMPELLER_PARAMETER_LIMITS: dict[str, dict[str, float]] = {
    "blade_count": {"min": 2, "max": 64},
    "inlet_radius_mm": {"min": 0.1, "max": 5000.0},
    "exit_radius_mm": {"min": 0.1, "max": 10000.0},
    "inlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
    "outlet_blade_height_mm": {"min": 0.1, "max": 5000.0},
    "hub_curve_height_mm": {"min": 0.0, "max": 5000.0},
    "mounting_bore_radius_mm": {"min": 0.1, "max": 3000.0},
    "blade_wrap_deg": {"min": -720.0, "max": 720.0},
    "blade_lean_deg": {"min": -180.0, "max": 180.0},
    "leading_edge_lean_deg": {"min": -180.0, "max": 180.0},
    "trailing_edge_lean_deg": {"min": -180.0, "max": 180.0},
    "leading_edge_sweep_mm": {"min": -5000.0, "max": 5000.0},
    "trailing_edge_sweep_mm": {"min": -5000.0, "max": 5000.0},
    "inlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
    "outlet_blade_angle_deg": {"min": -89.0, "max": 89.0},
    "blade_thickness_mm": {"min": 0.01, "max": 1000.0},
    "root_fillet_radius_mm": {"min": 0.0, "max": 1000.0},
}


def compile_impeller_runtime_preset(preset_id: str | None = None, facet_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    bundle = load_impeller_dsl_bundle()
    requested_preset_id = preset_id or "radial_open_reference"
    resolved_preset_id = bundle.aliases.get(requested_preset_id, requested_preset_id)
    if resolved_preset_id not in bundle.presets:
        raise ValueError(f"unknown impeller preset: {requested_preset_id}")
    preset = bundle.presets[resolved_preset_id]
    constructor = bundle.constructors[preset["constructor_id"]]
    facets = {**constructor["classification"], **(facet_overrides or {})}
    _validate_facets(bundle, facets)
    shape_control = normalize_shape_control_space(bundle.shape_control_schema, bundle.shape_controls)
    return {
        "version": "0.2.0",
        "part_family": "impeller",
        "preset_id": resolved_preset_id,
        "legacy_preset_id": requested_preset_id if requested_preset_id != resolved_preset_id else None,
        "ontology_slice": bundle.slice["slice_id"],
        "constructor_family": bundle.slice["constructor_family"],
        "constructor_id": constructor["constructor_id"],
        "facets": facets,
        "parameters": _parameter_specs(preset["parameter_values"]),
        "features": _features_for_constructor(constructor),
        "constraints": _constraints_for_constructor(constructor),
        "selected_rules": _selected_rules(bundle, constructor),
        "rule_implications": _rule_implications(constructor),
        "unsupported_or_inferred_regions": _inferred_regions(constructor),
        "dsl_sections": constructor,
        "shape_control": shape_control,
        "validity_contracts": bundle.validity_contracts,
        "loss_schema": bundle.loss_schema,
        "source_refs": preset.get("source_refs", []),
    }


def compiled_impeller_presets() -> dict[str, dict[str, Any]]:
    bundle = load_impeller_dsl_bundle()
    result = {}
    for preset_id, preset in bundle.presets.items():
        constructor = bundle.constructors[preset["constructor_id"]]
        result[preset_id] = {
            "name": preset["display_name"],
            "summary": preset["summary"],
            "facets": constructor["classification"],
            "parameters": preset["parameter_values"],
            "constructor_id": preset["constructor_id"],
        }
    return result


def _validate_facets(bundle, facets: dict[str, str]) -> None:
    in_scope = bundle.slice["in_scope"]
    axis_map = {
        "part_family": "part_family",
        "flow_topology": "flow_topology",
        "passage_topology": "passage_topology",
        "shroud_topology": "shroud_topology",
        "entry_topology": "entry_topology",
        "blade_population": "blade_population",
    }
    for facet_name, scope_key in axis_map.items():
        if facet_name not in facets:
            raise ValueError(f"missing impeller facet: {facet_name}")
        if facets[facet_name] not in in_scope[scope_key]:
            raise ValueError(f"invalid facet {facet_name}: {facets[facet_name]}")


def _parameter_specs(values: dict[str, float | int]) -> dict[str, dict[str, float]]:
    specs = {}
    for name, default in values.items():
        limits = IMPELLER_PARAMETER_LIMITS[name]
        specs[name] = {"default": default, "min": limits["min"], "max": limits["max"]}
    return specs


def _features_for_constructor(constructor: dict[str, Any]) -> list[str]:
    features = [
        "hub_material_solid",
        "hub_support_surface",
        "blade_tip_support_surface",
        "blade_root_boundary",
        "blade_tip_boundary",
        "leading_edge_boundary",
        "trailing_edge_boundary",
        "pressure_surface",
        "suction_surface",
        "surface_graph",
    ]
    if constructor["classification"]["shroud_topology"] == "closed":
        features.append("front_shroud_material_solid")
    return features


def _constraints_for_constructor(constructor: dict[str, Any]) -> list[str]:
    shroud = constructor["classification"]["shroud_topology"]
    constraints = [
        "conforms_to(blade_root_boundary, hub_support_surface)",
        "conforms_to(blade_tip_boundary, blade_tip_support_surface)",
        "connects_between(leading_edge_boundary, hub_support_surface, blade_tip_support_surface)",
        "connects_between(trailing_edge_boundary, hub_support_surface, blade_tip_support_surface)",
        "shares_boundary(surface_graph.surfaces, named_boundary_curve)",
    ]
    if shroud == "open":
        constraints.append("not(material(blade_tip_support_surface))")
    if shroud == "closed":
        constraints.append("material(blade_tip_support_surface)")
    return constraints


def _selected_rules(bundle, constructor: dict[str, Any]) -> list[str]:
    return [
        f"ontology_slice.{bundle.slice['slice_id']}",
        f"constructor_family.{bundle.slice['constructor_family']}",
        f"constructor.{constructor['constructor_id']}",
        "blade_boundaries.four_primary_boundaries_required",
        "support_surfaces.blade_tip_support_surface_role_disambiguated",
        "shape_control.stage_one_locked_topology",
    ]


def _rule_implications(constructor: dict[str, Any]) -> dict[str, str]:
    material = constructor["support_surfaces"]["blade_tip_support_surface"]["material"]
    return {
        "constructor_family": "uses axisymmetric hub and blade-tip support surfaces",
        "blade_boundaries": "root, tip, leading edge, and trailing edge are explicit DSL objects",
        "blade_tip_support_surface": "material front shroud" if material else "reference-only open tip support",
        "shape_control": "NURBS degree, control-point count, knot policy, and weights are locked in stage 1",
    }


def _inferred_regions(constructor: dict[str, Any]) -> list[str]:
    regions = ["strict_cad_brep_export_deferred"]
    if constructor["blade_edges"]["root"]["kind"] == "fillet_patch":
        regions.append("root_fillet_geometry_research_grade")
    return regions
```

- [ ] **Step 7: Run shape-control and compiler tests**

Run:

```powershell
python -m pytest tests/test_impeller_shape_control.py tests/test_impeller_runtime_compiler.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_shape_control.py src/part_rule_synthesis/impeller_dsl_resources.py src/part_rule_synthesis/impeller_runtime_compiler.py tests/test_impeller_shape_control.py tests/test_impeller_runtime_compiler.py
git commit -m "feat: load and compile impeller ontology dsl resources"
```

---

### Task 3: Wire JSON DSL Into Existing API-Compatible Taxonomy

**Files:**
- Modify: `src/part_rule_synthesis/impeller_taxonomy.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_acceptance.py`

- [ ] **Step 1: Add failing API acceptance assertions**

Add this test to `tests/test_acceptance.py`:

```python
def test_acceptance_impeller_ontology_exposes_axisymmetric_radial_slice(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    ontology = client.get("/api/ontology").json()
    impeller = ontology["part_families"]["impeller"]

    assert impeller["ontology_slices"]["axisymmetric_throughflow_radial_bladed"]["constructor_family"] == (
        "AxisymmetricThroughflowRadialBladedImpeller"
    )
    assert impeller["ontology_slices"]["axisymmetric_throughflow_radial_bladed"]["flow_topology"] == ["radial"]
    assert "blade_tip_support_surface" in ontology["terms"]
    assert "leading_edge_boundary" in ontology["terms"]
    assert "trailing_edge_boundary" in ontology["terms"]
    assert "shape_control_policy" in ontology["terms"]
    assert "semantic_handle" in ontology["terms"]
```

Add this test:

```python
def test_acceptance_legacy_impeller_preset_alias_compiles_to_new_constructor_family(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "axisymmetric_nurbs_open_throughflow_study"},
    )

    assert engine.status_code == 200
    payload = engine.json()
    rule = json.loads(Path(payload["dsl_path"]).read_text(encoding="utf-8"))
    assert rule["preset_id"] == "radial_open_reference"
    assert rule["legacy_preset_id"] == "axisymmetric_nurbs_open_throughflow_study"
    assert rule["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert rule["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert rule["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert rule["shape_control"]["optimization_stage"] == 1
    assert rule["shape_control"]["locked_topology"] is True
```

If `json` is not imported at top of `tests/test_acceptance.py`, add:

```python
import json
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_impeller_ontology_exposes_axisymmetric_radial_slice tests/test_acceptance.py::test_acceptance_legacy_impeller_preset_alias_compiles_to_new_constructor_family -q
```

Expected:

```text
FAILED ... KeyError: 'ontology_slices'
```

- [ ] **Step 3: Update `impeller_taxonomy.py` to expose loaded ontology and presets**

Replace the current hand-written `IMPELLER_PRESETS` source with compiled presets, but keep existing variable names:

```python
from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compiled_impeller_presets


_BUNDLE = load_impeller_dsl_bundle()

IMPELLER_FACET_AXES: dict[str, list[str]] = {
    "flow_topology": ["radial"],
    "shroud_topology": ["open", "closed"],
    "entry_topology": ["single_entry"],
    "blade_population": ["full_blade_set"],
    "working_domain": ["pump", "compressor", "unknown"],
    "passage_topology": ["throughflow_bladed_channel"],
}

ONTOLOGY: dict[str, Any] = {
    "version": "0.2.0",
    "part_families": {
        "impeller": {
            "base_features": [
                "hub_material_solid",
                "hub_support_surface",
                "blade_tip_support_surface",
                "blade_root_boundary",
                "blade_tip_boundary",
                "leading_edge_boundary",
                "trailing_edge_boundary",
                "pressure_surface",
                "suction_surface",
                "surface_graph",
            ],
            "facet_axes": IMPELLER_FACET_AXES,
            "ontology_slices": {
                "axisymmetric_throughflow_radial_bladed": {
                    "slice_id": _BUNDLE.slice["slice_id"],
                    "constructor_family": _BUNDLE.slice["constructor_family"],
                    "flow_topology": _BUNDLE.slice["in_scope"]["flow_topology"],
                    "passage_topology": _BUNDLE.slice["in_scope"]["passage_topology"],
                    "shroud_topology": _BUNDLE.slice["in_scope"]["shroud_topology"],
                }
            },
        }
    },
    "terms": sorted(
        {
            term
            for values in _BUNDLE.entities.values()
            if isinstance(values, list)
            for term in values
        }
        | {"impeller", "hub", "blade", "flow_path", "mounting_interface"}
    ),
    "relations": _BUNDLE.relations["relations"],
    "shape_control_schema": _BUNDLE.shape_control_schema,
    "validity_contracts": _BUNDLE.validity_contracts,
    "loss_schema": _BUNDLE.loss_schema,
}

IMPELLER_PRESETS: dict[str, dict[str, Any]] = compiled_impeller_presets()

LEGACY_CENTRIFUGAL_IMPELLER_FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
}
```

- [ ] **Step 4: Update `service.py` to call the compiler**

In `src/part_rule_synthesis/service.py`, import:

```python
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
```

Replace the body of `_impeller_dsl_template` with:

```python
def _impeller_dsl_template(preset_id: str | None, facet_overrides: dict[str, str]) -> dict[str, Any]:
    return compile_impeller_runtime_preset(preset_id, facet_overrides)
```

- [ ] **Step 5: Adjust service facet compatibility**

Where `service.py` references `suction_topology` or `blade_exit_geometry` for impeller-only code, guard with defaults:

```python
facets.get("suction_topology", "single_suction")
facets.get("blade_exit_geometry", "backward_curved")
```

Do this in `_operation_graph`, `_impeller_features`, `_impeller_constraints`, `_impeller_selected_rules`, `_impeller_rule_implications`, `_impeller_inferred_regions`, and `_resolved_impeller_facets` if those functions remain. Remove references only after tests prove they are no longer used.

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_impeller_ontology_exposes_axisymmetric_radial_slice tests/test_acceptance.py::test_acceptance_legacy_impeller_preset_alias_compiles_to_new_constructor_family -q
```

Expected:

```text
2 passed
```

- [ ] **Step 7: Run all backend tests**

Run:

```powershell
python -m pytest tests -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_taxonomy.py src/part_rule_synthesis/service.py tests/test_acceptance.py
git commit -m "feat: compile impeller runtime rules from json dsl"
```

---

### Task 4: Add Manifest Metadata For Ontology Slice, Constructor, Validity, And Loss Records

**Files:**
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_acceptance.py`

- [ ] **Step 1: Write failing manifest test**

Add to `tests/test_acceptance.py`:

```python
def test_acceptance_impeller_manifest_includes_ontology_constructor_validity_and_loss_sections(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference"},
    ).json()

    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    assert manifest["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert manifest["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert manifest["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert manifest["dsl_version"] == "0.2"
    assert manifest["shape_control"]["optimization_stage"] == 1
    assert manifest["shape_control"]["locked_topology"] is True
    assert manifest["shape_control"]["shape_optimization_space"]["editable_variables"]
    assert manifest["shape_control"]["provenance"]["source"] in {
        "default_rule",
        "explicit_dsl_control_net",
        "human_patch",
        "optimizer_patch",
    }
    assert "geometry_contracts" in manifest["validity"]
    assert "topology_contracts" in manifest["validity"]
    assert "engineering_warnings" in manifest["validity"]
    assert manifest["loss_records"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_impeller_manifest_includes_ontology_constructor_validity_and_loss_sections -q
```

Expected:

```text
FAILED ... KeyError: 'ontology_slice'
```

- [ ] **Step 3: Update manifest assembly in `RuleSynthesisService.instantiate`**

In `service.py`, after `bound = _bind_parameters(dsl, parameters)`, create a structured validity payload:

```python
validity_contracts = dsl.get("validity_contracts", {})
geometry_validity = _geometry_validity_metadata(dsl["part_family"], bound, dsl.get("facets", {}))
manifest_validity = {
    "status": geometry_validity.get("status", "PASS") if geometry_validity else "PASS",
    "geometry_contracts": geometry_validity.get("geometry_checks", []),
    "topology_contracts": geometry_validity.get("topology_checks", []),
    "engineering_warnings": geometry_validity.get("engineering_checks", []),
    "declared_contracts": validity_contracts,
}
```

Add these keys to the manifest dict:

```python
"ontology_slice": dsl.get("ontology_slice"),
"constructor_family": dsl.get("constructor_family"),
"constructor_id": dsl.get("constructor_id"),
"dsl_version": dsl.get("dsl_sections", {}).get("dsl_version", dsl["version"].replace(".0", "", 1)),
"shape_control": _manifest_shape_control(dsl.get("shape_control", {})),
"validity": manifest_validity,
"loss_records": [],
```

Keep the existing `"geometry_validity"` key for backward compatibility during this task.

- [ ] **Step 4: Ensure old validation summary remains**

If older tests expect `manifest["validation"]["status"]`, leave this existing line unchanged:

```python
"validation": _validation(dsl["part_family"]),
```

Add helper:

```python
def _manifest_shape_control(shape_control: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": shape_control.get("schema_version", "0.2"),
        "optimization_stage": shape_control.get("optimization_stage", 1),
        "locked_topology": shape_control.get("locked_topology", True),
        "active_policies": shape_control.get("active_policies", []),
        "semantic_handles": shape_control.get("semantic_handles", []),
        "shape_optimization_space": {
            "editable_variables": shape_control.get("editable_variables", []),
            "optimizable_variables": shape_control.get("optimizable_variables", []),
            "locked_topology": shape_control.get("locked_topology", True),
        },
        "provenance": {
            "source": "default_rule",
        },
    }
```

- [ ] **Step 5: Run targeted test**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_impeller_manifest_includes_ontology_constructor_validity_and_loss_sections -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run acceptance tests**

Run:

```powershell
python -m pytest tests/test_acceptance.py -q
```

Expected:

```text
all acceptance tests pass
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/part_rule_synthesis/service.py tests/test_acceptance.py
git commit -m "feat: emit impeller ontology dsl manifest metadata"
```

---

### Task 5: Refactor Kernel To Emit Explicit Four Blade Boundaries

**Files:**
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Test: `tests/test_impeller_kernel_boundaries.py`

- [ ] **Step 1: Write failing boundary tests**

Create `tests/test_impeller_kernel_boundaries.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


BASE_PARAMS = {
    "blade_count": 3,
    "inlet_radius_mm": 180.0,
    "exit_radius_mm": 620.0,
    "inlet_blade_height_mm": 150.0,
    "outlet_blade_height_mm": 72.0,
    "hub_curve_height_mm": 82.0,
    "mounting_bore_radius_mm": 40.0,
    "blade_wrap_deg": 118.0,
    "blade_lean_deg": 8.0,
    "leading_edge_lean_deg": 12.0,
    "trailing_edge_lean_deg": -8.0,
    "leading_edge_sweep_mm": 30.0,
    "trailing_edge_sweep_mm": -45.0,
    "blade_thickness_mm": 18.0,
}

FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
}


def test_axisymmetric_kernel_emits_four_named_blade_boundaries():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(BASE_PARAMS, FACETS)
    blade = geometry["sampled_blades"][0]
    boundary_curves = geometry["surface_graph"]["named_boundary_curves"]

    assert "blade_root_boundary" in blade
    assert "blade_tip_boundary" in blade
    assert "leading_edge_boundary" in blade
    assert "trailing_edge_boundary" in blade
    assert any(curve["role"] == "blade_root_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "blade_tip_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "leading_edge_boundary" for curve in boundary_curves)
    assert any(curve["role"] == "trailing_edge_boundary" for curve in boundary_curves)


def test_leading_edge_lean_changes_leading_edge_boundary_without_changing_blade_count():
    baseline = build_axisymmetric_throughflow_nurbs_geometry({**BASE_PARAMS, "leading_edge_lean_deg": 0.0}, FACETS)
    changed = build_axisymmetric_throughflow_nurbs_geometry({**BASE_PARAMS, "leading_edge_lean_deg": 35.0}, FACETS)

    assert len(baseline["sampled_blades"]) == len(changed["sampled_blades"]) == 3
    assert baseline["sampled_blades"][0]["leading_edge_boundary"] != changed["sampled_blades"][0]["leading_edge_boundary"]


def test_trailing_edge_sweep_changes_trailing_edge_boundary():
    baseline = build_axisymmetric_throughflow_nurbs_geometry({**BASE_PARAMS, "trailing_edge_sweep_mm": 0.0}, FACETS)
    changed = build_axisymmetric_throughflow_nurbs_geometry({**BASE_PARAMS, "trailing_edge_sweep_mm": 90.0}, FACETS)

    assert baseline["sampled_blades"][0]["trailing_edge_boundary"] != changed["sampled_blades"][0]["trailing_edge_boundary"]


def test_axisymmetric_kernel_echoes_shape_control_stage_and_locked_topology():
    geometry = build_axisymmetric_throughflow_nurbs_geometry(
        BASE_PARAMS,
        FACETS,
        shape_control={
            "optimization_stage": 1,
            "locked_topology": True,
            "active_policies": ["hub_meridional_profile", "blade_tip_meridional_profile"],
        },
    )

    assert geometry["shape_control"]["optimization_stage"] == 1
    assert geometry["shape_control"]["locked_topology"] is True
    assert "hub_meridional_profile" in geometry["shape_control"]["active_policies"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_kernel_boundaries.py -q
```

Expected:

```text
FAILED ... KeyError: 'named_boundary_curves'
```

- [ ] **Step 3: Add new default parameters**

Update the public helper signature so the kernel can receive compiled shape-control
metadata without coupling itself to JSON loading:

```python
def build_axisymmetric_throughflow_nurbs_geometry(
    params: dict[str, float | int],
    facets: dict[str, str],
    shape_control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

In `_normalized_parameters`, add:

```python
numeric.setdefault("leading_edge_lean_deg", numeric.get("blade_lean_deg", 0.0))
numeric.setdefault("trailing_edge_lean_deg", numeric.get("blade_lean_deg", 0.0))
numeric.setdefault("leading_edge_sweep_mm", 0.0)
numeric.setdefault("trailing_edge_sweep_mm", 0.0)
```

- [ ] **Step 4: Replace support profile sampling with boundary-controlled support coordinate**

Add helper functions near `_blade_point`:

```python
def _support_u(u: float, v: float, params: dict[str, float]) -> float:
    radial_span = max(params["exit_radius_mm"] - params["inlet_radius_mm"], 1.0)
    edge_sweep = (1.0 - u) * params["leading_edge_sweep_mm"] + u * params["trailing_edge_sweep_mm"]
    return _clamp01(u + (edge_sweep / radial_span) * (v - 0.5))


def _edge_lean_theta(u: float, v: float, params: dict[str, float]) -> float:
    leading = math.radians(params["leading_edge_lean_deg"])
    trailing = math.radians(params["trailing_edge_lean_deg"])
    return ((1.0 - u) * leading + u * trailing) * (v - 0.5)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
```

Modify `_blade_point`:

```python
support_u = _support_u(u, v, params)
hub = _profile_point(hub_profile, support_u)
tip = _profile_point(tip_profile, support_u)
```

Modify `_theta_field` to add edge lean:

```python
return base_angle + wrap * _smoothstep(u) + lean * (v - 0.5) * math.sin(math.pi * u) + _edge_lean_theta(u, v, params)
```

- [ ] **Step 5: Add four mean-boundary arrays to each blade**

In `_blade_surfaces`, add these values to the returned blade dict:

```python
"blade_root_boundary": [row[0] for row in mean],
"blade_tip_boundary": [row[-1] for row in mean],
"leading_edge_boundary": mean[0],
"trailing_edge_boundary": mean[-1],
```

Keep legacy keys:

```python
"hub_boundary": [row[0] for row in mean],
"tip_boundary": [row[-1] for row in mean],
```

- [ ] **Step 6: Rename tip support surface while preserving legacy surface IDs**

In `_surface_graph`, keep existing surface IDs for compatibility, but add stable roles:

```python
tip_surface_id = "shroud_surface" if facets["shroud_topology"] == "closed" else "tip_reference_surface"
tip_support_role = "front_shroud_inner_surface" if facets["shroud_topology"] == "closed" else "reference_only"
tip_support_material = facets["shroud_topology"] == "closed"
```

Add these fields to the tip support surface object:

```python
"ontology_id": "blade_tip_support_surface",
"role": tip_support_role,
"material": tip_support_material,
```

Add this to the hub surface object:

```python
"ontology_id": "hub_support_surface",
```

- [ ] **Step 7: Emit `named_boundary_curves` list**

In `_surface_graph`, initialize:

```python
named_boundary_curves = []
```

For each blade, append:

```python
named_boundary_curves.extend(
    [
        {
            "id": f"{prefix}_blade_root_boundary",
            "role": "blade_root_boundary",
            "blade_index": blade["index"],
            "support_surface": "hub_revolve_surface",
            "parameter": "v=0",
            "points": blade["blade_root_boundary"],
        },
        {
            "id": f"{prefix}_blade_tip_boundary",
            "role": "blade_tip_boundary",
            "blade_index": blade["index"],
            "support_surface": tip_surface_id,
            "support_surface_ontology_id": "blade_tip_support_surface",
            "parameter": "v=1",
            "points": blade["blade_tip_boundary"],
        },
        {
            "id": f"{prefix}_leading_edge_boundary",
            "role": "leading_edge_boundary",
            "blade_index": blade["index"],
            "parameter": "u=0",
            "points": blade["leading_edge_boundary"],
        },
        {
            "id": f"{prefix}_trailing_edge_boundary",
            "role": "trailing_edge_boundary",
            "blade_index": blade["index"],
            "parameter": "u=1",
            "points": blade["trailing_edge_boundary"],
        },
    ]
)
```

Return it:

```python
return {"surfaces": surfaces, "edges": edges, "boundary_curves": boundary_curves, "named_boundary_curves": named_boundary_curves}
```

- [ ] **Step 8: Add construction lines for the four primary boundaries**

In `_construction_lines`, add:

```python
"blade_boundaries": _blade_boundary_lines(sampled_blades),
```

Add helper:

```python
def _blade_boundary_lines(sampled_blades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = []
    for blade in sampled_blades:
        blade_index = int(blade["index"])
        for role, color in [
            ("blade_root_boundary", "#22c55e"),
            ("blade_tip_boundary", "#38bdf8"),
            ("leading_edge_boundary", "#f59e0b"),
            ("trailing_edge_boundary", "#ef4444"),
        ]:
            lines.append(
                {
                    "name": f"blade {blade_index} {role}",
                    "role": role,
                    "blade_index": blade_index,
                    "source": "axisymmetric_throughflow_nurbs.named_boundary_curve",
                    "color": color,
                    "points": blade[role],
                }
            )
    return lines
```

- [ ] **Step 9: Add shape-control metadata to kernel output**

When assembling the geometry return dict, include:

```python
"shape_control": shape_control
or {
    "optimization_stage": 1,
    "locked_topology": True,
    "active_policies": [],
},
```

This metadata records which NURBS shape-control policy the sampled support surfaces and
blade surfaces were derived from. It does not replace `surface_graph`.

- [ ] **Step 10: Run boundary tests**

Run:

```powershell
python -m pytest tests/test_impeller_kernel_boundaries.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 11: Run existing impeller kernel/acceptance tests**

Run:

```powershell
python -m pytest tests/test_impeller_kernel.py tests/test_acceptance.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 12: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py tests/test_impeller_kernel_boundaries.py
git commit -m "feat: expose four boundary blade surface model"
```

---

### Task 6: Add API Acceptance For Open/Closed Tip Support Semantics And Boundary Lines

**Files:**
- Modify: `tests/test_acceptance.py`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`

- [ ] **Step 1: Write failing open/closed manifest test**

Add to `tests/test_acceptance.py`:

```python
def test_acceptance_open_and_closed_impellers_share_tip_support_surface_semantics(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    cases = [
        ("radial_open_reference", "reference_only", False),
        ("radial_closed_reference", "front_shroud_inner_surface", True),
    ]

    for preset_id, expected_role, expected_material in cases:
        engine = client.post(
            "/api/rule-engines/synthesize",
            json={"part_family_id": "impeller", "preset_id": preset_id},
        ).json()
        manifest = client.post(
            f"/api/rule-engines/{engine['engine_id']}/instantiate",
            json={"parameters": {}},
        ).json()["manifest"]
        tip_surfaces = [
            surface
            for surface in manifest["geometry"]["surface_graph"]["surfaces"]
            if surface.get("ontology_id") == "blade_tip_support_surface"
        ]

        assert len(tip_surfaces) == 1
        assert tip_surfaces[0]["role"] == expected_role
        assert tip_surfaces[0]["material"] is expected_material
        assert manifest["geometry"]["construction_lines"]["blade_boundaries"]
        roles = {line["role"] for line in manifest["geometry"]["construction_lines"]["blade_boundaries"]}
        assert {"blade_root_boundary", "blade_tip_boundary", "leading_edge_boundary", "trailing_edge_boundary"}.issubset(roles)
```

- [ ] **Step 2: Run test to verify failure if Task 5 did not fully expose manifest fields**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_open_and_closed_impellers_share_tip_support_surface_semantics -q
```

Expected before fixes:

```text
FAILED ... assertion or KeyError
```

- [ ] **Step 3: Ensure `_geometry_metadata` passes through new construction lines**

In `service.py`, confirm `_geometry_metadata` includes:

```python
"construction_lines": impeller_geometry.get("construction_lines", {})
```

If it does not, add it.

- [ ] **Step 4: Ensure `surface_graph` includes `named_boundary_curves`**

In `_surface_graph`, confirm returned dict includes:

```python
"named_boundary_curves": named_boundary_curves
```

- [ ] **Step 5: Run targeted acceptance**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_acceptance_open_and_closed_impellers_share_tip_support_surface_semantics -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add tests/test_acceptance.py src/part_rule_synthesis/service.py src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py
git commit -m "test: verify impeller tip support and boundary semantics"
```

---

### Task 7: Update Frontend Model To Use DSL-Section Parameters

**Files:**
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`

- [ ] **Step 1: Write failing frontend model tests**

Add to `frontend/src/appModel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { buildInstantiatePayload, parameterGroups, parameterSchema, presets } from "./appModel.js";

describe("impeller DSL section parameter model", () => {
  test("exposes leading and trailing boundary controls", () => {
    assert.equal(parameterSchema.leading_edge_lean_deg.group, "blade_boundaries");
    assert.equal(parameterSchema.trailing_edge_lean_deg.group, "blade_boundaries");
    assert.equal(parameterSchema.leading_edge_sweep_mm.group, "blade_boundaries");
    assert.equal(parameterSchema.trailing_edge_sweep_mm.group, "blade_boundaries");
  });

  test("builds instantiate payload with explicit boundary parameters", () => {
    const payload = buildInstantiatePayload({
      leading_edge_lean_deg: 15,
      trailing_edge_lean_deg: -10,
      leading_edge_sweep_mm: 25,
      trailing_edge_sweep_mm: -30,
    });

    assert.equal(payload.parameters.leading_edge_lean_deg, 15);
    assert.equal(payload.parameters.trailing_edge_lean_deg, -10);
    assert.equal(payload.parameters.leading_edge_sweep_mm, 25);
    assert.equal(payload.parameters.trailing_edge_sweep_mm, -30);
  });

  test("uses radial open and closed reference presets while preserving API preset ids", () => {
    assert.ok(presets.map((preset) => preset.presetId).includes("radial_open_reference"));
    assert.ok(presets.map((preset) => preset.presetId).includes("radial_closed_reference"));
  });

  test("declares parameter groups in display order", () => {
    assert.deepEqual(parameterGroups.map((group) => group.id), [
      "main_dimensions",
      "meridional_support",
      "shape_control",
      "blade_pattern",
      "blade_boundaries",
      "blade_surface",
      "blade_profile",
      "edge_treatment",
    ]);
  });

  test("exposes semantic shape handles separately from generic dimensions", () => {
    assert.equal(parameterSchema.hub_base_radius_mm.group, "shape_control");
    assert.equal(parameterSchema.hub_nose_radius_mm.group, "shape_control");
    assert.equal(parameterSchema.hub_profile_convexity.group, "shape_control");
    assert.equal(parameterSchema.hub_base_radius_mm.controlKind, "semantic_handle");
  });
});
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test -- appModel.test.js
```

Expected:

```text
FAIL ... parameterGroups is not exported
```

- [ ] **Step 3: Update `appModel.js` parameter groups and schema**

Add export:

```javascript
export const parameterGroups = [
  { id: "main_dimensions", label: "Main dimensions" },
  { id: "meridional_support", label: "Meridional support" },
  { id: "shape_control", label: "Shape control" },
  { id: "blade_pattern", label: "Blade pattern" },
  { id: "blade_boundaries", label: "Blade boundaries" },
  { id: "blade_surface", label: "Blade surface" },
  { id: "blade_profile", label: "Blade profile" },
  { id: "edge_treatment", label: "Edge treatment" },
];
```

Update `parameterSchema` entries with `group` fields and add:

```javascript
leading_edge_lean_deg: { label: "Leading edge lean", unit: "deg", step: 1, default: 12, group: "blade_boundaries" },
trailing_edge_lean_deg: { label: "Trailing edge lean", unit: "deg", step: 1, default: -8, group: "blade_boundaries" },
leading_edge_sweep_mm: { label: "Leading edge sweep", unit: "mm", step: 1, default: 30, group: "blade_boundaries" },
trailing_edge_sweep_mm: { label: "Trailing edge sweep", unit: "mm", step: 1, default: -45, group: "blade_boundaries" },
root_fillet_radius_mm: { label: "Root fillet radius", unit: "mm", step: 0.5, default: 8, group: "edge_treatment" },
hub_base_radius_mm: { label: "Hub base radius", unit: "mm", step: 1, default: 190, group: "shape_control", controlKind: "semantic_handle" },
hub_nose_radius_mm: { label: "Hub nose radius", unit: "mm", step: 1, default: 72, group: "shape_control", controlKind: "semantic_handle" },
hub_profile_convexity: { label: "Hub profile convexity", unit: "", step: 0.05, default: 0.35, group: "shape_control", controlKind: "semantic_handle" },
```

Assign existing fields:

```javascript
blade_count.group = "blade_pattern"
inlet_radius_mm.group = "main_dimensions"
exit_radius_mm.group = "main_dimensions"
inlet_blade_height_mm.group = "meridional_support"
outlet_blade_height_mm.group = "meridional_support"
hub_curve_height_mm.group = "meridional_support"
mounting_bore_radius_mm.group = "main_dimensions"
blade_wrap_deg.group = "blade_surface"
blade_lean_deg.group = "blade_surface"
blade_thickness_mm.group = "blade_profile"
```

Because object literal entries cannot be mutated inside the literal, write the final schema directly with each `group` field included.

- [ ] **Step 4: Update presets**

Change preset IDs:

```javascript
presetId: "radial_open_reference"
presetId: "radial_closed_reference"
```

Add the new boundary parameters to both preset parameter maps.

- [ ] **Step 5: Run frontend model tests**

Run:

```powershell
npm.cmd test -- appModel.test.js
```

Expected:

```text
all appModel tests pass
```

- [ ] **Step 6: Commit**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
git add frontend/src/appModel.js frontend/src/appModel.test.js
git commit -m "feat: expose impeller dsl boundary controls in frontend model"
```

---

### Task 8: Update Frontend Panels For Parameter Groups And Manifest Metadata

**Files:**
- Modify: `frontend/src/components/ParameterPanel.js`
- Modify: `frontend/src/components/ManifestPanel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Add frontend file smoke tests**

In `frontend/src/appFiles.test.js`, add assertions that the source files include the new keys:

```javascript
import fs from "node:fs";
import assert from "node:assert/strict";
import path from "node:path";
import { describe, test } from "node:test";

const srcRoot = path.resolve(import.meta.dirname);

function readSource(relativePath) {
  return fs.readFileSync(path.join(srcRoot, relativePath), "utf8");
}

describe("impeller ontology UI wiring", () => {
  test("renders parameter groups", () => {
    const source = readSource("components/ParameterPanel.js");
    assert.match(source, /parameterGroups/);
    assert.match(source, /blade_boundaries/);
  });

  test("renders ontology slice and constructor metadata", () => {
    const source = readSource("components/ManifestPanel.js");
    assert.match(source, /ontology_slice/);
    assert.match(source, /constructor_family/);
    assert.match(source, /constructor_id/);
    assert.match(source, /shape_control/);
    assert.match(source, /optimization_stage/);
  });

  test("renders blade boundary construction lines", () => {
    const source = readSource("components/ModelViewer.js");
    assert.match(source, /blade_boundaries/);
    assert.match(source, /named_boundary_curve/);
  });
});
```

If `appFiles.test.js` already has a `describe` block, add these `it` blocks to the existing file instead of duplicating imports.

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test -- appFiles.test.js
```

Expected:

```text
FAIL ... expected source to contain parameterGroups
```

- [ ] **Step 3: Update `ParameterPanel.js`**

Import `parameterGroups` from `appModel.js`. Render parameters grouped by `spec.group`:

```javascript
import { parameterGroups, parameterSchema } from "../appModel";

const groupedEntries = parameterGroups.map((group) => ({
  ...group,
  entries: Object.entries(parameterSchema).filter(([, spec]) => spec.group === group.id),
}));
```

Inside the panel JSX, render group headings and inputs:

```javascript
{groupedEntries.map((group) => (
  <section key={group.id} className="parameter-group" data-group={group.id}>
    <h3>{group.label}</h3>
    {group.entries.map(([name, spec]) => (
      <label key={name}>
        <span>{spec.label}</span>
        <input
          type="number"
          step={spec.step}
          value={parameters[name] ?? spec.default}
          onChange={(event) => onParameterChange(name, event.target.value)}
        />
        {spec.unit ? <small>{spec.unit}</small> : null}
      </label>
    ))}
  </section>
))}
```

Adapt variable names to the component's existing props. Do not change the component API if existing tests rely on it.

- [ ] **Step 4: Update `ManifestPanel.js`**

Add display rows for:

```javascript
manifest.ontology_slice
manifest.constructor_family
manifest.constructor_id
manifest.shape_control?.optimization_stage
manifest.shape_control?.locked_topology
manifest.shape_control?.semantic_handles
manifest.shape_control?.shape_optimization_space?.editable_variables
manifest.shape_control?.shape_optimization_space?.optimizable_variables
manifest.validity?.geometry_contracts
manifest.validity?.topology_contracts
manifest.validity?.engineering_warnings
```

Use compact counts for contract arrays:

```javascript
const geometryCount = manifest.validity?.geometry_contracts?.length ?? 0;
const topologyCount = manifest.validity?.topology_contracts?.length ?? 0;
const warningCount = manifest.validity?.engineering_warnings?.length ?? 0;
const semanticHandleCount = manifest.shape_control?.semantic_handles?.length ?? 0;
const editableVariableCount = manifest.shape_control?.shape_optimization_space?.editable_variables?.length ?? 0;
const optimizableVariableCount = manifest.shape_control?.shape_optimization_space?.optimizable_variables?.length ?? 0;
```

- [ ] **Step 5: Update `ModelViewer.js`**

When collecting construction lines, include:

```javascript
manifest.geometry?.construction_lines?.blade_boundaries
```

Treat these as source:

```javascript
"axisymmetric_throughflow_nurbs.named_boundary_curve"
```

Use each line's `color` when available.

- [ ] **Step 6: Run frontend tests and build**

Run:

```powershell
npm.cmd test
npm.cmd run build
```

Expected:

```text
all tests pass
build completes
```

- [ ] **Step 7: Commit**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
git add frontend/src/components/ParameterPanel.js frontend/src/components/ManifestPanel.js frontend/src/components/ModelViewer.js frontend/src/appFiles.test.js
git commit -m "feat: show impeller dsl groups and boundary metadata"
```

---

### Task 9: Build Interactive Impeller Design Workspace

**Files:**
- Create: `frontend/src/workspaceModel.js`
- Create: `frontend/src/workspaceModel.test.js`
- Create: `frontend/src/components/GeometryLayerPanel.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/components/ManifestPanel.js`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Write failing workspace model tests**

Create `frontend/src/workspaceModel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  defaultVisibleLayers,
  layerEnabled,
  lineLayer,
  surfaceLayer,
  visibleConstructionLine,
  visibleSurface,
  workspaceStats,
} from "./workspaceModel.js";

describe("impeller workspace model", () => {
  test("classifies support, blade, edge, and boundary layers", () => {
    assert.equal(surfaceLayer({ role: "reference_only", ontology_id: "blade_tip_support_surface" }), "support_surfaces");
    assert.equal(surfaceLayer({ role: "blade_pressure" }), "blade_surfaces");
    assert.equal(surfaceLayer({ kind: "edge_closure_surface" }), "edge_closures");
    assert.equal(lineLayer({ role: "leading_edge_boundary" }, "blade_boundaries"), "blade_boundaries");
    assert.equal(lineLayer({ surface_id: "hub_revolve_surface" }, "surface_uv"), "uv_lines");
  });

  test("uses default layers that show shaded geometry and construction boundaries", () => {
    assert.equal(layerEnabled(defaultVisibleLayers, "shaded_surfaces"), true);
    assert.equal(layerEnabled(defaultVisibleLayers, "support_surfaces"), true);
    assert.equal(layerEnabled(defaultVisibleLayers, "blade_boundaries"), true);
    assert.equal(layerEnabled(defaultVisibleLayers, "uv_lines"), true);
  });

  test("filters surfaces and construction lines by layer visibility", () => {
    const visible = { shaded_surfaces: true, blade_surfaces: false, blade_boundaries: true };
    assert.equal(visibleSurface({ role: "blade_pressure" }, visible), false);
    assert.equal(visibleSurface({ role: "hub", ontology_id: "hub_support_surface" }, visible), true);
    assert.equal(visibleConstructionLine({ role: "trailing_edge_boundary" }, "blade_boundaries", visible), true);
    assert.equal(visibleConstructionLine({ surface_id: "blade_0_pressure_surface" }, "surface_uv", visible), false);
  });

  test("summarizes manifest geometry and validity for the right panel", () => {
    const stats = workspaceStats({
      geometry: {
        surface_graph: {
          surfaces: [{ id: "hub" }, { id: "blade_0_pressure_surface" }],
          named_boundary_curves: [{ id: "blade_0_le" }],
        },
      },
      validity: {
        geometry_contracts: [{ status: "PASS" }],
        topology_contracts: [{ status: "FAIL" }],
        engineering_warnings: [{ status: "WARN" }],
      },
      shape_control: {
        semantic_handles: [{ id: "hub_base_radius" }, { id: "hub_nose_radius" }],
        shape_optimization_space: {
          editable_variables: [{ id: "hub_cp_0_r" }],
          optimizable_variables: [{ id: "hub_cp_0_r" }],
        },
      },
    });

    assert.deepEqual(stats, {
      surfaceCount: 2,
      boundaryCount: 1,
      geometryPass: 1,
      topologyFail: 1,
      engineeringWarnings: 1,
      semanticHandleCount: 2,
      editableShapeVariableCount: 1,
      optimizableShapeVariableCount: 1,
    });
  });
});
```

- [ ] **Step 2: Run workspace model test to verify it fails**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test -- workspaceModel.test.js
```

Expected:

```text
FAIL ... Cannot find module './workspaceModel.js'
```

- [ ] **Step 3: Implement `workspaceModel.js`**

Create `frontend/src/workspaceModel.js`:

```javascript
export const viewLayerSchema = [
  { id: "shaded_surfaces", label: "Shaded surfaces", color: "#7aa58f" },
  { id: "support_surfaces", label: "Hub/tip supports", color: "#0f766e" },
  { id: "blade_surfaces", label: "Pressure/suction", color: "#6f9b85" },
  { id: "edge_closures", label: "Edge closures", color: "#f59e0b" },
  { id: "blade_boundaries", label: "Blade boundaries", color: "#38bdf8" },
  { id: "uv_lines", label: "Surface UV lines", color: "#315f72" },
  { id: "axes", label: "Axes", color: "#2563eb" },
];

export const defaultVisibleLayers = {
  shaded_surfaces: true,
  support_surfaces: true,
  blade_surfaces: true,
  edge_closures: true,
  blade_boundaries: true,
  uv_lines: true,
  axes: true,
};

export function layerEnabled(visibleLayers, layerId) {
  return visibleLayers?.[layerId] !== false;
}

export function toggleLayer(visibleLayers, layerId) {
  return { ...visibleLayers, [layerId]: !layerEnabled(visibleLayers, layerId) };
}

export function surfaceLayer(surface) {
  if (surface?.kind === "edge_closure_surface") {
    return "edge_closures";
  }
  if (surface?.ontology_id === "hub_support_surface" || surface?.ontology_id === "blade_tip_support_surface") {
    return "support_surfaces";
  }
  if (String(surface?.role || "").startsWith("blade_")) {
    return "blade_surfaces";
  }
  return "shaded_surfaces";
}

export function lineLayer(line, feature) {
  if (feature === "blade_boundaries" || String(line?.role || "").endsWith("_boundary")) {
    return "blade_boundaries";
  }
  if (feature === "surface_uv" || line?.source === "axisymmetric_throughflow_nurbs.surface_graph") {
    return "uv_lines";
  }
  if (feature === "blade_edges") {
    return "edge_closures";
  }
  return "blade_boundaries";
}

export function visibleSurface(surface, visibleLayers) {
  const layer = surfaceLayer(surface);
  if (layer === "blade_surfaces") {
    return layerEnabled(visibleLayers, "shaded_surfaces") && layerEnabled(visibleLayers, "blade_surfaces");
  }
  return layerEnabled(visibleLayers, "shaded_surfaces") && layerEnabled(visibleLayers, layer);
}

export function visibleConstructionLine(line, feature, visibleLayers) {
  return layerEnabled(visibleLayers, lineLayer(line, feature));
}

export function workspaceStats(manifest) {
  const surfaces = manifest?.geometry?.surface_graph?.surfaces || [];
  const boundaries = manifest?.geometry?.surface_graph?.named_boundary_curves || [];
  const validity = manifest?.validity || {};
  const shapeControl = manifest?.shape_control || {};
  const optimizationSpace = shapeControl.shape_optimization_space || {};
  return {
    surfaceCount: surfaces.length,
    boundaryCount: boundaries.length,
    geometryPass: (validity.geometry_contracts || []).filter((check) => check.status === "PASS").length,
    topologyFail: (validity.topology_contracts || []).filter((check) => check.status === "FAIL").length,
    engineeringWarnings: (validity.engineering_warnings || []).length,
    semanticHandleCount: (shapeControl.semantic_handles || []).length,
    editableShapeVariableCount: (optimizationSpace.editable_variables || []).length,
    optimizableShapeVariableCount: (optimizationSpace.optimizable_variables || []).length,
  };
}
```

- [ ] **Step 4: Run workspace model tests**

Run:

```powershell
npm.cmd test -- workspaceModel.test.js
```

Expected:

```text
all workspaceModel tests pass
```

- [ ] **Step 5: Add source smoke tests for the interactive workspace**

Extend `frontend/src/appFiles.test.js`:

```javascript
test("interactive workspace files and layer controls are wired", () => {
  for (const file of [
    "src/workspaceModel.js",
    "src/components/GeometryLayerPanel.js",
  ]) {
    assert.equal(existsSync(resolve(root, file)), true, `${file} should exist`);
  }

  const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
  const viewerSource = readFileSync(resolve(root, "src/components/ModelViewer.js"), "utf-8");
  const manifestSource = readFileSync(resolve(root, "src/components/ManifestPanel.js"), "utf-8");

  assert.match(appSource, /visibleLayers/);
  assert.match(appSource, /selectedSurface/);
  assert.match(appSource, /GeometryLayerPanel/);
  assert.match(viewerSource, /visibleSurface/);
  assert.match(viewerSource, /onSurfaceSelect/);
  assert.match(viewerSource, /named_boundary_curves/);
  assert.match(manifestSource, /selectedSurface/);
  assert.match(manifestSource, /workspaceStats/);
});
```

- [ ] **Step 6: Run source smoke tests to verify failure**

Run:

```powershell
npm.cmd test -- appFiles.test.js
```

Expected:

```text
FAIL ... GeometryLayerPanel.js should exist
```

- [ ] **Step 7: Create `GeometryLayerPanel.js`**

Create `frontend/src/components/GeometryLayerPanel.js`:

```javascript
import React from "react";

import { viewLayerSchema } from "../workspaceModel.js";

const h = React.createElement;

export function GeometryLayerPanel({ visibleLayers, onToggleLayer }) {
  return h(
    "section",
    { className: "geometry-layer-panel" },
    h("div", { className: "section-title" }, "Geometry layers"),
    h(
      "div",
      { className: "layer-list" },
      viewLayerSchema.map((layer) =>
        h(
          "label",
          { className: "layer-row", key: layer.id },
          h("input", {
            type: "checkbox",
            checked: visibleLayers?.[layer.id] !== false,
            onChange: () => onToggleLayer(layer.id),
          }),
          h("span", { className: "layer-swatch", style: { backgroundColor: layer.color } }),
          h("span", null, layer.label),
        ),
      ),
    ),
  );
}
```

- [ ] **Step 8: Update `App.js` workspace state and layout**

Import:

```javascript
import { defaultVisibleLayers, toggleLayer } from "./workspaceModel.js";
import { GeometryLayerPanel } from "./components/GeometryLayerPanel.js";
```

Add state:

```javascript
const [visibleLayers, setVisibleLayers] = useState(defaultVisibleLayers);
const [selectedSurface, setSelectedSurface] = useState(null);
```

Add handler:

```javascript
function updateLayer(layerId) {
  setVisibleLayers((current) => toggleLayer(current, layerId));
}
```

In the left panel, render the layer panel after `ParameterPanel`:

```javascript
h(GeometryLayerPanel, {
  visibleLayers,
  onToggleLayer: updateLayer,
})
```

Pass viewer props:

```javascript
visibleLayers,
selectedSurfaceId: selectedSurface?.id || "",
onSurfaceSelect: setSelectedSurface,
```

Pass right-panel prop:

```javascript
selectedSurface,
```

Reset selected surface after preset change:

```javascript
setSelectedSurface(null);
```

- [ ] **Step 9: Update `ModelViewer.js` for layer filtering and surface selection**

Import:

```javascript
import { visibleConstructionLine, visibleSurface } from "../workspaceModel.js";
```

Add props:

```javascript
visibleLayers = {},
selectedSurfaceId = "",
onSurfaceSelect = () => {},
```

When creating surface meshes, skip hidden layers:

```javascript
if (!visibleSurface(surface, visibleLayers)) {
  continue;
}
```

Set mesh metadata:

```javascript
const mesh = new THREE.Mesh(geometry, material);
mesh.userData.surface = {
  id: surface.id,
  role: surface.role,
  ontology_id: surface.ontology_id,
  material: surface.material,
  kind: surface.kind,
};
group.add(mesh);
```

When creating construction lines, skip hidden layers:

```javascript
if (!visibleConstructionLine(line, feature, visibleLayers)) {
  continue;
}
```

Add a click handler using `THREE.Raycaster`:

```javascript
const raycasterRef = useRef(new THREE.Raycaster());
const pointerRef = useRef(new THREE.Vector2());

function handleCanvasClick(event) {
  const renderer = rendererRef.current;
  const camera = cameraRef.current;
  const shaded = modelRef.current.shaded;
  if (!renderer || !camera || !shaded) {
    return;
  }
  const rect = renderer.domElement.getBoundingClientRect();
  pointerRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointerRef.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycasterRef.current.setFromCamera(pointerRef.current, camera);
  const hits = raycasterRef.current.intersectObjects(shaded.children, true);
  const selected = hits.find((hit) => hit.object.userData.surface)?.object.userData.surface || null;
  onSurfaceSelect(selected);
}
```

Attach it after renderer creation:

```javascript
renderer.domElement.addEventListener("click", handleCanvasClick);
```

Remove it in cleanup:

```javascript
renderer.domElement.removeEventListener("click", handleCanvasClick);
```

Add `visibleLayers` to effects that render surface graph and construction lines so toggles update the view:

```javascript
}, [surfaceGraph, visibleLayers]);
```

```javascript
}, [constructionLines, visibleLayers]);
```

Keep axes visibility tied to `visibleLayers.axes`.

- [ ] **Step 10: Update `ManifestPanel.js` for selected surface and workspace stats**

Import:

```javascript
import { workspaceStats } from "../workspaceModel.js";
```

Change signature:

```javascript
export function ManifestPanel({ manifest, exportLinks, selectedSurface }) {
```

Compute:

```javascript
const stats = workspaceStats(manifest);
```

Add summary metrics:

```javascript
h(Metric, { label: "Surfaces", value: String(stats.surfaceCount) }),
h(Metric, { label: "Boundaries", value: String(stats.boundaryCount) }),
```

Add selected surface section before raw geometry JSON:

```javascript
h(Section, {
  title: "Selected surface",
  body: selectedSurface ? h("pre", null, JSON.stringify(selectedSurface, null, 2)) : "Click a shaded surface to inspect it.",
})
```

Add validity overview:

```javascript
h(Section, {
  title: "Validity overview",
  body: h("pre", null, JSON.stringify({
    geometry_pass: stats.geometryPass,
    topology_fail: stats.topologyFail,
    engineering_warnings: stats.engineeringWarnings,
  }, null, 2)),
})
```

- [ ] **Step 11: Update CSS for workspace density**

Add styles in `frontend/src/styles.css`:

```css
.geometry-layer-panel {
  border-top: 1px solid rgba(24, 40, 33, 0.12);
  padding-top: 12px;
}

.layer-list {
  display: grid;
  gap: 8px;
}

.layer-row {
  display: grid;
  grid-template-columns: 18px 14px 1fr;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.layer-swatch {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  border: 1px solid rgba(15, 23, 42, 0.2);
}

.parameter-group {
  border-top: 1px solid rgba(24, 40, 33, 0.1);
  padding-top: 10px;
}

.parameter-group h3 {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
  color: #52645b;
}
```

- [ ] **Step 12: Run frontend tests**

Run:

```powershell
npm.cmd test
npm.cmd run build
```

Expected:

```text
all frontend tests pass
build completes
```

- [ ] **Step 13: Commit**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
git add frontend/src/workspaceModel.js frontend/src/workspaceModel.test.js frontend/src/components/GeometryLayerPanel.js frontend/src/App.js frontend/src/components/ModelViewer.js frontend/src/components/ManifestPanel.js frontend/src/styles.css frontend/src/appFiles.test.js
git commit -m "feat: add interactive impeller design workspace"
```

---

### Task 10: Update Documentation And Migration Notes

**Files:**
- Modify: `docs/axisymmetric-throughflow-nurbs-kernel.md`
- Create: `docs/impeller-ontology-dsl-json-layout.md`

- [ ] **Step 1: Update kernel doc**

In `docs/axisymmetric-throughflow-nurbs-kernel.md`, replace the old construction-order text with a summary that includes:

```markdown
## Construction Order

1. Load the `AxisymmetricThroughflowRadialBladedImpeller` ontology slice and constructor DSL.
2. Establish the cylindrical coordinate system with Z as the rotation axis.
3. Define hub and blade-tip meridional profiles in the R-Z plane.
4. Revolve the hub profile into `hub_support_surface`.
5. Revolve the blade-tip profile into `blade_tip_support_surface`.
6. Interpret `blade_tip_support_surface` as `reference_only` for open impellers and `front_shroud_inner_surface` for closed impellers.
7. Define four blade boundaries: root, tip, leading edge, trailing edge.
8. Construct the blade mean surface using the four boundaries and internal beta/wrap/camber controls.
9. Generate pressure and suction surfaces from the mean surface and thickness field.
10. Generate leading, trailing, root, and tip closure or fillet surfaces.
11. Assemble a named surface graph with named boundary curves and adjacency.
12. Sample shaded geometry and construction lines from the same surface graph.
13. Emit geometry validity, topology validity, engineering warnings, and loss records.
```

- [ ] **Step 2: Create JSON layout doc**

Create `docs/impeller-ontology-dsl-json-layout.md` with:

```markdown
# Impeller Ontology And DSL JSON Layout

The canonical v0.2 impeller ontology slice is `AxisymmetricThroughflowRadialBladedImpeller`.

Ontology JSON files live under:

`src/part_rule_synthesis/ontology/impeller/v0_2/`

Constructor DSL JSON files live under:

`src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/`

Runtime rule JSON is still written to each generated engine directory for API compatibility.
It is compiled from the canonical JSON files by `impeller_runtime_compiler.py`.

Open impellers use `blade_tip_support_surface` with `material: false` and `role: reference_only`.
Closed impellers use `blade_tip_support_surface` with `material: true` and `role: front_shroud_inner_surface`.

Every blade must expose:

- `blade_root_boundary`
- `blade_tip_boundary`
- `leading_edge_boundary`
- `trailing_edge_boundary`

No frontend wireframe should be generated from a proxy independent of `surface_graph`.
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/axisymmetric-throughflow-nurbs-kernel.md docs/impeller-ontology-dsl-json-layout.md
git commit -m "docs: describe impeller ontology dsl json layout"
```

---

### Task 11: Full Verification And Visual Smoke Test

**Files:**
- No planned source changes unless verification exposes defects.

- [ ] **Step 1: Run full backend verification**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
python -m pytest tests -q
python -m compileall -q src scripts
```

Expected:

```text
pytest: all tests pass
compileall: no output
```

- [ ] **Step 2: Run full frontend verification**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend"
npm.cmd test
npm.cmd run build
```

Expected:

```text
npm test: all tests pass
npm build: build completes
```

- [ ] **Step 3: Start backend and frontend**

Run:

```powershell
cd "C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice"
Start-Process -WindowStyle Hidden powershell -ArgumentList "-NoProfile","-Command","cd 'C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice'; python -m uvicorn part_rule_synthesis.api:app --host 127.0.0.1 --port 8041"
cd frontend
Start-Process -WindowStyle Hidden powershell -ArgumentList "-NoProfile","-Command","cd 'C:\Users\CHEN Li\Documents\TurboJetCase\part-rule-synthesis\.worktrees\impeller-ontology-dsl-slice\frontend'; npm.cmd run dev -- --host 127.0.0.1 --port 5278"
```

Expected:

```text
Backend: http://127.0.0.1:8041
Frontend: http://127.0.0.1:5278
```

- [ ] **Step 4: API smoke test**

Run:

```powershell
$engine = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8041/api/rule-engines/synthesize" -ContentType "application/json" -Body '{"part_family_id":"impeller","preset_id":"radial_open_reference"}'
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8041/api/rule-engines/$($engine.engine_id)/instantiate" -ContentType "application/json" -Body '{"parameters":{"leading_edge_lean_deg":25,"trailing_edge_sweep_mm":60}}'
$run.manifest.ontology_slice
$run.manifest.geometry.surface_graph.named_boundary_curves.Count
```

Expected:

```text
impeller.axisymmetric_throughflow_radial_bladed
<positive integer>
```

- [ ] **Step 5: Browser visual smoke**

Open:

```text
http://127.0.0.1:5278
```

Manual checks:

- Open preset generates model.
- Closed preset generates model.
- Parameter panel shows "Blade boundaries".
- Geometry layer panel shows shaded surfaces, support surfaces, blade surfaces, edge closures, blade boundaries, UV lines, and axes.
- Turning off `UV lines` hides surface parameter lines while shaded geometry remains visible.
- Turning off `Blade boundaries` hides `u=0`, `u=1`, `v=0`, and `v=1` boundary curves while edge closure surfaces remain visible.
- Clicking a shaded hub, support, blade, or closure surface updates the selected surface section in the manifest panel.
- Selected surface data includes `id`, `role`, and either `ontology_id` or `kind`.
- Changing `Leading edge lean` visibly changes the leading-edge boundary direction.
- Changing `Trailing edge sweep` visibly changes trailing-edge boundary shape.
- Wireframe lines remain attached to shaded geometry.
- Manifest shows ontology slice, constructor family, validity overview, surface count, and boundary count.

- [ ] **Step 6: Final commit if smoke-test fixes were required**

Run if source changed:

```powershell
git status --short
git add <changed-files>
git commit -m "fix: complete impeller ontology dsl smoke verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - JSON canonical file structure: Tasks 1-3.
  - `AxisymmetricThroughflowRadialBladedImpeller`: Tasks 1-4.
  - NURBS shape-control schema, default policies, semantic handles, and stage-1 locked
    topology: Tasks 1, 2, 4, 5, 7, 8, 9.
  - `blade_tip_support_surface`: Tasks 1, 5, 6.
  - Four blade boundaries: Tasks 1, 5, 6, 8.
  - Open/closed material distinction: Tasks 1, 6.
  - Validity and loss schema: Tasks 1, 4.
  - Existing API compatibility: Tasks 3, 4, 6.
  - Frontend controls and interactive design workspace: Tasks 7, 8, 9.
  - Verification: Task 11.
- Placeholder scan:
  - No task contains unresolved placeholder markers or deferred-work wording.
- Type consistency:
  - Constructor family: `AxisymmetricThroughflowRadialBladedImpeller`.
  - Slice ID: `impeller.axisymmetric_throughflow_radial_bladed`.
  - Constructor IDs: `axisymmetric_throughflow_radial_bladed.open` and `.closed`.
  - Preset IDs: `radial_open_reference` and `radial_closed_reference`.
  - Boundary names: `blade_root_boundary`, `blade_tip_boundary`, `leading_edge_boundary`, `trailing_edge_boundary`.
  - Support surface name: `blade_tip_support_surface`.
  - Shape-control fields: `shape_control_schema`, `shape_controls/default_shape_controls.json`,
    `semantic_handles`, `shape_optimization_space`, `editable_variables`, and
    `optimizable_variables`.

---

## Execution Handoff

Plan complete. Recommended execution mode: Subagent-Driven if available after the worktree is ready; otherwise Inline Execution task-by-task with verification after each commit.
