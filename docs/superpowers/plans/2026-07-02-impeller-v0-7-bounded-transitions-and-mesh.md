# Impeller v0.7 Bounded Transitions And Mesh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V0.7 so impeller STEP export uses bounded topological faces, edge transitions are controlled by topology-family policies, and frontend/mesh/export artifacts all show the same transitions.

**Architecture:** V0.7 adds an additive DSL resource line and a shared transition-policy layer. Backend generation resolves edge-family policies into surface graph transition entities, bounded B-Rep export consumes those entities to produce finite faces and honest manifests, and frontend UI edits the same policy payload used by the kernel. Mesh inspection switches from metric-only display to real triangle overlay and transition-region quality review.

**Tech Stack:** Python 3.12, OCP/OCCT, pytest, FastAPI, React without JSX, Three.js, Node test runner, PowerShell verification scripts.

---

## File Structure

Create:

- `src/part_rule_synthesis/impeller_transition_policies.py`: normalize edge-family defaults, user overrides, policy validation, and manifest payloads.
- `src/part_rule_synthesis/impeller_bounded_brep_export.py`: build bounded OCCT faces, annular wires, bounded B-Rep STEP export, OCCT re-import checks, and export manifest fields.
- `src/part_rule_synthesis/impeller_mesh_export.py`: write OBJ mesh groups and mesh manifest artifacts from graph triangulation.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/...`: additive V0.7 schema, constructors, presets, export contracts, simulation views, and shape controls.
- `frontend/src/edgeTreatmentModel.js`: frontend model helpers for family-level transition policy rows and override payloads.
- `frontend/src/meshOverlayModel.js`: frontend model helpers for mesh overlay modes, region coloring, and quality summaries.
- `frontend/src/components/EdgeTreatmentPanel.js`: family-level edge treatment controls.
- `tests/test_impeller_v07_resources.py`: V0.7 resource loading and runtime compiler tests.
- `tests/test_impeller_transition_policies.py`: policy resolver and validation tests.
- `tests/test_impeller_bounded_brep_export.py`: bounded annular plane, bbox, and exactness tests.
- `tests/test_impeller_mesh_export.py`: OBJ/grouped mesh export and manifest tests.
- `frontend/src/edgeTreatmentModel.test.js`: frontend transition policy model tests.
- `frontend/src/meshOverlayModel.test.js`: mesh overlay model tests.

Modify:

- `src/part_rule_synthesis/api.py`: accept `transition_overrides` in instantiate requests.
- `src/part_rule_synthesis/service.py`: pass transition overrides through runtime generation and route V0.7 exports.
- `src/part_rule_synthesis/impeller_runtime_compiler.py`: load V0.7 resources and expose transition parameters.
- `src/part_rule_synthesis/impeller_dsl_resources.py`: add `v0_7` resource loading.
- `src/part_rule_synthesis/impeller_surface_graph_export.py`: keep V0.5/V0.6 mesh behavior and share triangulation with mesh export.
- `src/part_rule_synthesis/impeller_mesh_manifest.py`: add transition regions and quality buckets.
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`: consume transition policies, attach edge families, generate policy-linked transition surfaces, and mark bounded cap metadata.
- `frontend/src/App.js`: maintain `transitionOverrides` state and render `EdgeTreatmentPanel`.
- `frontend/src/appModel.js`: expose V0.7 presets, export options, and instantiate payload shape.
- `frontend/src/components/ModelViewer.js`: add transition layer coloring, mesh overlay edges, selected edge family highlight, and solid-context toggle behavior.
- `frontend/src/components/CfdManifestPanel.js`: rename CFD semantics and connect selected mesh/patch/family state.
- `frontend/src/components/MeshInspectionPanel.js`: show quality metrics, transition regions, and color-mode controls.
- `frontend/src/simulationViewModel.js`: distinguish CAD review, CFD boundary, CFD mesh, and feature debug semantics.
- `frontend/src/workspaceModel.js`: add transition and mesh layers.
- `tests/test_workflow.py`: V0.7 open/closed workflows, export exactness, mesh artifacts, and transition override behavior.
- `tests/test_impeller_version_lineage.py`: include V0.7 resource case.
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`: document V0.7.
- `README.md`, `docs/current-research-frontier.md`, `docs/repository-map.md`, and V0.7 evidence README: update after implementation evidence.

Do not commit generated binaries under `Model Output/` unless a separate evidence decision selects a small artifact.

---

## Defaults Chosen For This Plan

- Default additional mesh exchange: OBJ with named groups plus JSON mesh manifest.
- AP242 `TRIANGULATED_FACE_SET` remains available only as `experimental_mesh_step`.
- V0.7 accepted STEP exactness is `surface_graph_trimmed_brep_step` only when bounded face construction and validation pass.
- Diagnostic bounded-but-unsewn export exactness is `surface_graph_bounded_unsewn_brep_step`.
- Edge treatment UI is family-level by default; per-edge/per-blade overrides exist in payload shape but are advanced controls.
- Closed impeller hood/shroud transition families are included after open hub/blade families so open reference evidence can fail or pass independently.

---

### Task 1: Pre-Flight Branch And Baseline Guard

**Files:**
- Read: `docs/superpowers/specs/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh-design.md`
- Read: `docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md`
- Modify only if needed: `.git/config`

- [ ] **Step 1: Confirm branch and clean intended scope**

Run:

```powershell
git status -sb
git branch --show-current
git log --oneline --max-count=5
```

Expected:

```text
## impeller-v0.7-transition-spec
?? "Model Output/"
impeller-v0.7-transition-spec
```

Only `Model Output/` may be untracked before implementation begins.

- [ ] **Step 2: Create the implementation branch from the spec branch**

Run:

```powershell
git switch -c impeller-v0.7-bounded-transitions
```

Expected:

```text
Switched to a new branch 'impeller-v0.7-bounded-transitions'
```

- [ ] **Step 3: Run baseline fast verification**

Run:

```powershell
.\scripts\verify_repository.ps1 -Mode fast
```

Expected:

```text
42 passed
tests 50
frontend build check passed
```

If counts changed because the base branch advanced, record the observed counts in the task notes before continuing.

- [ ] **Step 4: Commit no changes**

Run:

```powershell
git status -sb
```

Expected:

```text
## impeller-v0.7-bounded-transitions
?? "Model Output/"
```

No commit is made in this task.

---

### Task 2: Add V0.7 DSL Resource Line

**Files:**
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/aliases.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/constructors/open_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/constructors/closed_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/presets/radial_open_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/presets/radial_closed_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/shape_controls/default_shape_controls.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/export_contracts/surface_graph_bounded_brep.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/simulation_views/cfd_full_360.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/simulation_views/fea_solid_schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/CHANGELOG.md`
- Modify: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- Test: `tests/test_impeller_v07_resources.py`
- Test: `tests/test_impeller_version_lineage.py`

- [ ] **Step 1: Write failing V0.7 resource tests**

Create `tests/test_impeller_v07_resources.py`:

```python
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v07_bundle_loads_schema_and_transition_resources():
    bundle = load_impeller_dsl_bundle("v0_7")

    assert bundle.schema["dsl_version"] == "0.7"
    assert bundle.shape_controls["shape_control_version"] == "0.7"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_7",
        "radial_closed_reference_v0_7",
    }
    assert bundle.export_contracts["surface_graph_bounded_brep"]["mode"] == "surface_graph_bounded_brep"
    assert bundle.export_contracts["surface_graph_bounded_brep"]["step_exactness"] == "surface_graph_trimmed_brep_step"


def test_v07_runtime_exposes_edge_families_and_default_policies():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_7")

    assert runtime["version"] == "0.7.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.7"
    assert "edge_families" in runtime
    assert "transition_policy_defaults" in runtime
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["hub_top_outer.default"]["treatment"] == "fillet"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v07_resources.py -q
```

Expected:

```text
FAILED ... unknown impeller DSL version: v0_7
```

- [ ] **Step 3: Copy V0.6 resources into V0.7**

Run:

```powershell
Copy-Item -Recurse `
  src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_6 `
  src\part_rule_synthesis\dsl\impeller\axisymmetric_throughflow_radial_bladed\v0_7
```

Then edit V0.7 JSON files so:

```json
{
  "dsl_version": "0.7",
  "supersedes": "../../v0_6/schema.json"
}
```

Presets must use:

```json
{
  "preset_id": "radial_open_reference_v0_7"
}
```

and:

```json
{
  "preset_id": "radial_closed_reference_v0_7"
}
```

- [ ] **Step 4: Add V0.7 export contract**

Create `v0_7/export_contracts/surface_graph_bounded_brep.json`:

```json
{
  "contract_version": "0.7",
  "mode": "surface_graph_bounded_brep",
  "default_view": "cad_review_360",
  "step_exactness": "surface_graph_trimmed_brep_step",
  "diagnostic_step_exactness": "surface_graph_bounded_unsewn_brep_step",
  "mesh_exports": ["stl", "obj", "mesh_manifest"],
  "experimental_exports": ["experimental_mesh_step"],
  "requires": [
    "bounded_faces",
    "finite_bounding_box",
    "transition_policy_regions",
    "occt_reimport_check"
  ]
}
```

- [ ] **Step 5: Add V0.7 edge families and defaults to constructors**

In both V0.7 constructor files add:

```json
{
  "edge_families": {
    "blade_leading_edge": {
      "scope": "blade_pattern",
      "adjacent_roles": ["blade_pressure", "blade_suction"],
      "default_treatment": "fillet",
      "default_radius_parameter": "leading_edge_radius_mm",
      "cfd_patch_group": "leading_edge_wall"
    },
    "blade_trailing_edge": {
      "scope": "blade_pattern",
      "adjacent_roles": ["blade_pressure", "blade_suction"],
      "default_treatment": "fillet",
      "default_radius_parameter": "trailing_edge_radius_mm",
      "cfd_patch_group": "trailing_edge_wall"
    },
    "blade_root_to_hub": {
      "scope": "blade_pattern",
      "adjacent_roles": ["blade_pressure", "blade_suction", "hub"],
      "default_treatment": "fillet",
      "default_radius_parameter": "root_fillet_radius_mm",
      "cfd_patch_group": "root_fillet_wall"
    },
    "blade_tip_or_shroud": {
      "scope": "blade_pattern",
      "adjacent_roles": ["blade_pressure", "blade_suction", "front_shroud_or_tip_reference"],
      "default_treatment": "fillet",
      "default_radius_parameter": "tip_edge_radius_mm",
      "cfd_patch_group": "tip_fillet_wall"
    },
    "hub_bottom_outer": {
      "scope": "hub_solid",
      "adjacent_roles": ["outer_hub_shell", "inner_hub_bottom"],
      "default_treatment": "fillet",
      "default_radius_parameter": "hub_chamfer_radius_mm",
      "cfd_patch_group": "solid_context"
    },
    "hub_top_outer": {
      "scope": "hub_solid",
      "adjacent_roles": ["outer_hub_shell", "hub_top_cap"],
      "default_treatment": "fillet",
      "default_radius_parameter": "hub_chamfer_radius_mm",
      "cfd_patch_group": "solid_context"
    },
    "mounting_bore_top": {
      "scope": "hub_solid",
      "adjacent_roles": ["mounting_bore", "hub_top_cap"],
      "default_treatment": "chamfer",
      "default_radius_parameter": "hub_chamfer_radius_mm",
      "cfd_patch_group": "solid_context"
    },
    "mounting_bore_bottom": {
      "scope": "hub_solid",
      "adjacent_roles": ["mounting_bore", "inner_hub_bottom"],
      "default_treatment": "chamfer",
      "default_radius_parameter": "hub_chamfer_radius_mm",
      "cfd_patch_group": "solid_context"
    }
  }
}
```

- [ ] **Step 6: Add V0.7 resource loading**

Modify `src/part_rule_synthesis/impeller_dsl_resources.py` so `load_impeller_dsl_bundle("v0_7")` works. Follow the existing `v0_6` branch pattern exactly.

Modify `src/part_rule_synthesis/impeller_runtime_compiler.py` so runtime output includes:

```python
runtime["version"] = "0.7.0"
runtime["edge_families"] = constructor.get("edge_families", {})
runtime["transition_policy_defaults"] = _transition_policy_defaults(
    constructor.get("edge_families", {}),
    parameters,
)
```

The helper can be introduced here and moved in Task 3:

```python
def _transition_policy_defaults(edge_families, parameters):
    policies = {}
    for family_id, family in edge_families.items():
        parameter_name = family["default_radius_parameter"]
        policies[f"{family_id}.default"] = {
            "edge_family": family_id,
            "enabled": True,
            "treatment": family["default_treatment"],
            "radius_mm": float(parameters[parameter_name]),
            "continuity": "G1" if family["default_treatment"] == "fillet" else "G0",
            "applies_to": "all_pattern_instances",
            "maps_to_parameters": [parameter_name],
            "overrides": [],
        }
    return policies
```

- [ ] **Step 7: Add V0.7 lineage case**

Modify `tests/test_impeller_version_lineage.py` so its version cases include:

```python
(
    "v0_7",
    "0.7",
    ["radial_open_reference_v0_7", "radial_closed_reference_v0_7"],
)
```

- [ ] **Step 8: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_v07_resources.py tests/test_impeller_version_lineage.py -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit**

Run:

```powershell
git add src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7 `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md `
  src/part_rule_synthesis/impeller_dsl_resources.py `
  src/part_rule_synthesis/impeller_runtime_compiler.py `
  tests/test_impeller_v07_resources.py `
  tests/test_impeller_version_lineage.py
git commit -m "feat: add impeller dsl v0.7 resources"
```

---

### Task 3: Transition Policy Resolver

**Files:**
- Create: `src/part_rule_synthesis/impeller_transition_policies.py`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/api.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Test: `tests/test_impeller_transition_policies.py`
- Test: `tests/test_acceptance.py`

- [ ] **Step 1: Write failing resolver tests**

Create `tests/test_impeller_transition_policies.py`:

```python
import pytest

from part_rule_synthesis.impeller_transition_policies import (
    TransitionPolicyError,
    resolve_transition_policies,
)


EDGE_FAMILIES = {
    "blade_root_to_hub": {
        "default_treatment": "fillet",
        "default_radius_parameter": "root_fillet_radius_mm",
    },
    "hub_top_outer": {
        "default_treatment": "fillet",
        "default_radius_parameter": "hub_chamfer_radius_mm",
    },
}

PARAMETERS = {
    "root_fillet_radius_mm": 8.0,
    "hub_chamfer_radius_mm": 3.0,
}


def test_resolve_transition_policies_builds_family_defaults():
    policies = resolve_transition_policies(EDGE_FAMILIES, PARAMETERS, {})

    assert policies["blade_root_to_hub.default"] == {
        "policy_id": "blade_root_to_hub.default",
        "edge_family": "blade_root_to_hub",
        "enabled": True,
        "treatment": "fillet",
        "radius_mm": 8.0,
        "continuity": "G1",
        "applies_to": "all_pattern_instances",
        "maps_to_parameters": ["root_fillet_radius_mm"],
        "overrides": [],
    }


def test_resolve_transition_policies_applies_override():
    policies = resolve_transition_policies(
        EDGE_FAMILIES,
        PARAMETERS,
        {
            "blade_root_to_hub.default": {
                "enabled": True,
                "treatment": "chamfer",
                "radius_mm": 5.5,
            }
        },
    )

    assert policies["blade_root_to_hub.default"]["treatment"] == "chamfer"
    assert policies["blade_root_to_hub.default"]["continuity"] == "G0"
    assert policies["blade_root_to_hub.default"]["radius_mm"] == 5.5


def test_resolve_transition_policies_rejects_unknown_policy():
    with pytest.raises(TransitionPolicyError, match="unknown transition policy"):
        resolve_transition_policies(
            EDGE_FAMILIES,
            PARAMETERS,
            {"unknown.default": {"treatment": "fillet", "radius_mm": 1.0}},
        )


def test_resolve_transition_policies_rejects_bad_treatment():
    with pytest.raises(TransitionPolicyError, match="unsupported transition treatment"):
        resolve_transition_policies(
            EDGE_FAMILIES,
            PARAMETERS,
            {"blade_root_to_hub.default": {"treatment": "round", "radius_mm": 1.0}},
        )


def test_resolve_transition_policies_rejects_negative_radius():
    with pytest.raises(TransitionPolicyError, match="radius_mm must be nonnegative"):
        resolve_transition_policies(
            EDGE_FAMILIES,
            PARAMETERS,
            {"blade_root_to_hub.default": {"treatment": "fillet", "radius_mm": -1.0}},
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_policies.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_transition_policies'
```

- [ ] **Step 3: Implement resolver**

Create `src/part_rule_synthesis/impeller_transition_policies.py`:

```python
from __future__ import annotations

from typing import Any


SUPPORTED_TREATMENTS = {"none", "chamfer", "fillet"}


class TransitionPolicyError(ValueError):
    pass


def resolve_transition_policies(
    edge_families: dict[str, Any],
    parameters: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    policies: dict[str, dict[str, Any]] = {}
    for family_id, family in edge_families.items():
        parameter_name = str(family["default_radius_parameter"])
        treatment = str(family["default_treatment"])
        radius = float(parameters[parameter_name])
        policy_id = f"{family_id}.default"
        policies[policy_id] = _policy(
            policy_id,
            family_id,
            True,
            treatment,
            radius,
            [parameter_name],
        )

    for policy_id, override in (overrides or {}).items():
        if policy_id not in policies:
            raise TransitionPolicyError(f"unknown transition policy: {policy_id}")
        if not isinstance(override, dict):
            raise TransitionPolicyError(f"{policy_id} override must be an object")
        base = dict(policies[policy_id])
        treatment = str(override.get("treatment", base["treatment"]))
        radius = float(override.get("radius_mm", base["radius_mm"]))
        enabled = bool(override.get("enabled", base["enabled"]))
        policies[policy_id] = _policy(
            policy_id,
            base["edge_family"],
            enabled,
            treatment,
            radius,
            list(base["maps_to_parameters"]),
            list(override.get("overrides", base["overrides"])),
        )
    return policies


def _policy(
    policy_id: str,
    family_id: str,
    enabled: bool,
    treatment: str,
    radius: float,
    maps_to_parameters: list[str],
    overrides: list[Any] | None = None,
) -> dict[str, Any]:
    if treatment not in SUPPORTED_TREATMENTS:
        raise TransitionPolicyError(f"unsupported transition treatment: {treatment}")
    if radius < 0.0:
        raise TransitionPolicyError("radius_mm must be nonnegative")
    if treatment == "none":
        enabled = False
        radius = 0.0
    return {
        "policy_id": policy_id,
        "edge_family": family_id,
        "enabled": enabled,
        "treatment": treatment,
        "radius_mm": round(float(radius), 6),
        "continuity": "G1" if treatment == "fillet" else "G0",
        "applies_to": "all_pattern_instances",
        "maps_to_parameters": maps_to_parameters,
        "overrides": overrides or [],
    }
```

- [ ] **Step 4: Add API payload support**

Modify `src/part_rule_synthesis/api.py`:

```python
class InstantiateRequest(BaseModel):
    parameters: dict[str, float | int] = Field(default_factory=dict)
    profile_overrides: dict[str, Any] | None = None
    curve_overrides: dict[str, Any] | None = None
    transition_overrides: dict[str, Any] | None = None
    geometry_stage: str = "full"
```

and pass it into service:

```python
run = service.instantiate(
    engine_id,
    request.parameters,
    profile_overrides=request.profile_overrides,
    curve_overrides=request.curve_overrides,
    transition_overrides=request.transition_overrides,
    geometry_stage=request.geometry_stage,
)
```

- [ ] **Step 5: Thread overrides through service**

Modify `RuleSynthesisService.instantiate` signature:

```python
def instantiate(
    self,
    engine_id: str,
    parameters: dict[str, Any],
    profile_overrides: dict[str, Any] | None = None,
    curve_overrides: dict[str, Any] | None = None,
    transition_overrides: dict[str, Any] | None = None,
    geometry_stage: str = "full",
) -> ModelRun:
```

Normalize:

```python
normalized_transition_overrides = transition_overrides or {}
```

Include in graph hash:

```python
"transition_overrides": normalized_transition_overrides,
```

Pass to metadata builders:

```python
transition_overrides=normalized_transition_overrides,
```

Add to manifest:

```python
"transition_overrides": normalized_transition_overrides,
```

- [ ] **Step 6: Add acceptance test for API payload**

Add to `tests/test_acceptance.py`:

```python
def test_acceptance_impeller_v07_accepts_transition_overrides(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference_v0_7"},
    ).json()["engine_id"]

    response = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={
            "parameters": {},
            "transition_overrides": {
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "chamfer",
                    "radius_mm": 6.0,
                }
            },
        },
    )

    assert response.status_code == 200
    manifest = response.json()["manifest"]
    assert manifest["transition_policies"]["blade_root_to_hub.default"]["treatment"] == "chamfer"
    assert manifest["transition_policies"]["blade_root_to_hub.default"]["radius_mm"] == 6.0
```

- [ ] **Step 7: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_transition_policies.py tests/test_acceptance.py::test_acceptance_impeller_v07_accepts_transition_overrides -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_transition_policies.py `
  src/part_rule_synthesis/api.py `
  src/part_rule_synthesis/service.py `
  src/part_rule_synthesis/impeller_runtime_compiler.py `
  tests/test_impeller_transition_policies.py `
  tests/test_acceptance.py
git commit -m "feat: resolve impeller transition policies"
```

---

### Task 4: Bounded Annular Plane B-Rep Export

**Files:**
- Create: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
- Modify: `src/part_rule_synthesis/impeller_cad_payload.py`
- Test: `tests/test_impeller_bounded_brep_export.py`

- [ ] **Step 1: Write failing tests for annular bounded faces**

Create `tests/test_impeller_bounded_brep_export.py`:

```python
from pathlib import Path

from part_rule_synthesis.impeller_bounded_brep_export import (
    bounded_step_contains_no_unbounded_plane_marker,
    make_annular_plane_face,
    write_bounded_brep_step,
)


def _annular_surface():
    return {
        "id": "hub_top_cap_face",
        "role": "hub_top_cap",
        "feature_id": "hub",
        "kind": "annular_plane_surface",
        "inner_radius_mm": 40.0,
        "outer_radius_mm": 150.0,
        "z_mm": 400.0,
        "cad_surface": {
            "surface_type": "plane",
            "origin": [0.0, 0.0, 400.0],
            "normal": [0.0, 0.0, 1.0],
            "u_dir": [1.0, 0.0, 0.0],
            "v_dir": [0.0, 1.0, 0.0],
        },
    }


def test_make_annular_plane_face_reports_finite_metadata():
    face, metadata = make_annular_plane_face(_annular_surface())

    assert face is not None
    assert metadata["bounded"] is True
    assert metadata["outer_radius_mm"] == 150.0
    assert metadata["inner_radius_mm"] == 40.0
    assert metadata["loop_count"] == 2


def test_write_bounded_brep_step_has_no_huge_plane_bounds(tmp_path: Path):
    step_path = tmp_path / "annular.step"
    manifest = write_bounded_brep_step(
        step_path,
        "test_impeller",
        {"surfaces": [_annular_surface()], "edges": []},
        view_id="cad_review_360",
    )

    assert step_path.exists()
    assert bounded_step_contains_no_unbounded_plane_marker(step_path)
    assert manifest["bounded_face_count"] == 1
    assert manifest["face_regions"][0]["surface_graph_id"] == "hub_top_cap_face"
    assert manifest["face_regions"][0]["bounded"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_bounded_brep_export.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_bounded_brep_export'
```

- [ ] **Step 3: Implement annular plane face builder**

Create `src/part_rule_synthesis/impeller_bounded_brep_export.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


BOUNDED_STEP_EXACTNESS = "surface_graph_trimmed_brep_step"
DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS = "surface_graph_bounded_unsewn_brep_step"


def make_annular_plane_face(surface: dict[str, Any]):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeCircle
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    outer_radius = float(surface["outer_radius_mm"])
    inner_radius = float(surface.get("inner_radius_mm", 0.0))
    z = float(surface["z_mm"])
    axis = gp_Ax2(gp_Pnt(0.0, 0.0, z), gp_Dir(0.0, 0.0, 1.0))

    outer_edge = BRepBuilderAPI_MakeEdge(GC_MakeCircle(axis, outer_radius).Value()).Edge()
    outer_wire = BRepBuilderAPI_MakeWire(outer_edge).Wire()
    maker = BRepBuilderAPI_MakeFace(outer_wire, True)

    loop_count = 1
    if inner_radius > 0.0:
        inner_edge = BRepBuilderAPI_MakeEdge(GC_MakeCircle(axis, inner_radius).Value()).Edge()
        inner_wire = BRepBuilderAPI_MakeWire(inner_edge).Wire()
        maker.Add(inner_wire)
        loop_count = 2

    return maker.Face(), {
        "bounded": True,
        "loop_count": loop_count,
        "outer_radius_mm": outer_radius,
        "inner_radius_mm": inner_radius,
    }
```

- [ ] **Step 4: Implement minimal bounded STEP writer**

Add to `src/part_rule_synthesis/impeller_bounded_brep_export.py`:

```python
def write_bounded_brep_step(
    step_path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    from OCP.BRep import BRep_Builder
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    regions = []

    for index, surface in enumerate(surface_graph.get("surfaces", [])):
        if surface.get("kind") == "annular_plane_surface":
            face, metadata = make_annular_plane_face(surface)
        else:
            raise ValueError(f"bounded B-Rep does not support surface kind: {surface.get('kind')}")
        builder.Add(compound, face)
        regions.append({
            "brep_face_id": f"face_{index:04d}",
            "surface_graph_id": surface["id"],
            "feature_id": surface.get("feature_id"),
            "role": surface.get("role"),
            **metadata,
        })

    writer = STEPControl_Writer()
    schema_key = "write.step.schema"
    previous_schema = Interface_Static.CVal_s(schema_key)
    try:
        Interface_Static.SetCVal_s(schema_key, "AP214IS")
        transfer_status = writer.Transfer(compound, STEPControl_AsIs)
        if transfer_status != IFSelect_RetDone:
            raise RuntimeError(f"OCCT STEP transfer failed with status {transfer_status}")
        write_status = writer.Write(str(step_path))
        if write_status != IFSelect_RetDone:
            raise RuntimeError(f"OCCT STEP write failed with status {write_status}")
    finally:
        Interface_Static.SetCVal_s(schema_key, previous_schema)

    return {
        "source": "surface_graph",
        "view": view_id,
        "solid_name": solid_name,
        "export_exactness": DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS,
        "target_exactness": BOUNDED_STEP_EXACTNESS,
        "bounded_face_count": len(regions),
        "sewing_status": "not_attempted",
        "open_edge_count": None,
        "face_regions": regions,
    }


def bounded_step_contains_no_unbounded_plane_marker(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "-10000." not in text and "10000." not in text and "-10000," not in text and "10000," not in text
```

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_bounded_brep_export.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_bounded_brep_export.py tests/test_impeller_bounded_brep_export.py
git commit -m "feat: add bounded annular brep export"
```

---

### Task 5: V0.7 Export Routing And Exactness Manifest

**Files:**
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
- Modify: `src/part_rule_synthesis/impeller_surface_graph_export.py`
- Test: `tests/test_workflow.py`
- Test: `tests/test_impeller_bounded_brep_export.py`

- [ ] **Step 1: Write failing workflow test**

Add to `tests/test_workflow.py`:

```python
def test_impeller_v07_exports_bounded_step_and_no_default_mesh_step(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference_v0_7")

    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["dsl_version"] == "0.7"
    assert manifest["export_strategy"]["mode"] == "surface_graph_bounded_brep"
    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["target_exactness"] == "surface_graph_trimmed_brep_step"
    assert step_manifest["bounded_face_count"] >= 2
    assert manifest["exports"]["step"].endswith(".step")
    assert manifest["exports"]["stl"].endswith(".stl")
    assert manifest["exports"]["obj"].endswith(".obj")
    assert "mesh_step" not in manifest["exports"]

    step_text = Path(manifest["exports"]["step"]).read_text(encoding="utf-8", errors="ignore")
    assert "-10000" not in step_text
    assert "ADVANCED_FACE" in step_text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v07_exports_bounded_step_and_no_default_mesh_step -q
```

Expected:

```text
FAILED ... KeyError: 'obj'
```

or:

```text
FAILED ... expected mode surface_graph_bounded_brep
```

- [ ] **Step 3: Route V0.7 exports**

In `src/part_rule_synthesis/service.py`, update `_write_exports`:

```python
if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_bounded_brep":
    surface_graph = (geometry_metadata or {}).get("surface_graph")
    if not surface_graph:
        raise RuntimeError("surface_graph_bounded_brep export requires geometry.surface_graph")
    output_dir = _model_output_dir_for_run(run_dir, model_output_root)
    stem = _safe_export_stem((dsl_context or {}).get("preset_id"), run_dir.name)
    step = output_dir / f"{stem}.step"
    stl = output_dir / f"{stem}.stl"
    obj = output_dir / f"{stem}.obj"
    manifest_copy = output_dir / f"{stem}.manifest.json"
    view_id = export_contract.get("default_view", "cad_review_360")
    brep_manifest = write_bounded_brep_step(step, part_family, surface_graph, view_id=view_id)
    mesh_manifests = write_surface_graph_exports(step.with_suffix(".experimental.mesh.step"), stl, part_family, surface_graph, view_id=view_id)
    obj_manifest = write_surface_graph_obj(obj, part_family, surface_graph, view_id=view_id)
    return (
        {"step": str(step), "stl": str(stl), "obj": str(obj), "manifest": str(manifest_copy)},
        {"step": brep_manifest, "stl": mesh_manifests["stl"], "obj": obj_manifest},
    )
```

This references `write_surface_graph_obj`, which Task 9 implements. For this task, add a local simple writer in Task 5 if Task 9 has not run. Use the Task 9 final module name to avoid renaming.

- [ ] **Step 4: Add export strategy**

In `_export_strategy`:

```python
if part_family in {"centrifugal_impeller", "impeller"} and export_contract.get("mode") == "surface_graph_bounded_brep":
    return {
        "mode": "surface_graph_bounded_brep",
        "cad_exports": "completed",
        "source": "geometry.surface_graph",
        "view": export_contract.get("default_view", "cad_review_360"),
        "reason": "STEP is generated from bounded surface_graph B-Rep faces; mesh artifacts are separate review outputs",
    }
```

- [ ] **Step 5: Run targeted workflow test**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v07_exports_bounded_step_and_no_default_mesh_step -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/service.py tests/test_workflow.py
git commit -m "feat: route v0.7 bounded brep exports"
```

---

### Task 6: Surface Graph Edge Families And Transition Policies

**Files:**
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_kernel.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing kernel test**

Add to `tests/test_impeller_kernel.py`:

```python
def test_v07_surface_graph_edges_include_family_and_policy_metadata():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from part_rule_synthesis.service import RuleSynthesisService

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_7")
        run = service.instantiate(engine.engine_id, {})

    manifest = run.manifest
    edges = {edge["id"]: edge for edge in manifest["geometry"]["surface_graph"]["edges"]}
    policies = manifest["transition_policies"]

    assert "blade_root_to_hub.default" in policies
    root_edges = [edge for edge in edges.values() if edge.get("edge_family") == "blade_root_to_hub"]
    assert root_edges
    assert all(edge["transition_policy_id"] == "blade_root_to_hub.default" for edge in root_edges)
    assert all(edge["transition_surface_ids"] for edge in root_edges)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_surface_graph_edges_include_family_and_policy_metadata -q
```

Expected:

```text
FAILED ... KeyError: 'transition_policies'
```

- [ ] **Step 3: Pass transition policies into kernel**

In service metadata builder call, pass:

```python
transition_overrides=normalized_transition_overrides
```

In the impeller geometry builder function signature, add:

```python
transition_overrides: dict[str, Any] | None = None
```

Resolve policies near parameter normalization:

```python
edge_families = (dsl_context or {}).get("edge_families", {})
transition_policies = resolve_transition_policies(edge_families, params, transition_overrides or {})
```

Add to returned geometry metadata:

```python
"edge_families": edge_families,
"transition_policies": transition_policies,
```

- [ ] **Step 4: Attach edge family metadata**

When building blade edges, add fields:

```python
{
    "edge_family": "blade_root_to_hub",
    "transition_policy_id": "blade_root_to_hub.default",
    "transition_surface_ids": [root_surface_id],
}
```

Map existing V0.6 edge relations:

```text
closed_blade_edge at leading side -> blade_leading_edge
closed_blade_edge at trailing side -> blade_trailing_edge
closed_blade_root_edge -> blade_root_to_hub
closed_blade_tip_edge -> blade_tip_or_shroud
closed_hub_solid_boundary with bottom -> hub_bottom_outer
closed_hub_solid_boundary with top -> hub_top_outer
mounting bore top/bottom -> mounting_bore_top / mounting_bore_bottom
```

- [ ] **Step 5: Add manifest fields**

In service manifest:

```python
"edge_families": geometry_metadata.get("edge_families", {}),
"transition_policies": geometry_metadata.get("transition_policies", {}),
```

- [ ] **Step 6: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_surface_graph_edges_include_family_and_policy_metadata -q
```

Expected:

```text
1 passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py src/part_rule_synthesis/service.py tests/test_impeller_kernel.py
git commit -m "feat: annotate v0.7 transition edge families"
```

---

### Task 7: Policy-Driven Blade Transition Geometry

**Files:**
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Test: `tests/test_impeller_kernel.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing tests for treatment changes**

Add to `tests/test_impeller_kernel.py`:

```python
def test_v07_transition_override_changes_blade_root_surface_role_and_radius():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from part_rule_synthesis.service import RuleSynthesisService

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_7")
        run = service.instantiate(
            engine.engine_id,
            {},
            transition_overrides={
                "blade_root_to_hub.default": {
                    "enabled": True,
                    "treatment": "chamfer",
                    "radius_mm": 6.0,
                }
            },
        )

    surfaces = {surface["id"]: surface for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]}
    root = surfaces["blade_0_root_transition_surface"]
    assert root["role"] == "blade_root_chamfer"
    assert root["treatment"] == "chamfer"
    assert root["radius_mm"] == 6.0
    assert root["transition_policy_id"] == "blade_root_to_hub.default"


def test_v07_disabled_transition_removes_blade_root_transition_surfaces():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from part_rule_synthesis.service import RuleSynthesisService

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_7")
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

    surface_ids = {surface["id"] for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]}
    assert "blade_0_root_transition_surface" not in surface_ids
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_transition_override_changes_blade_root_surface_role_and_radius tests/test_impeller_kernel.py::test_v07_disabled_transition_removes_blade_root_transition_surfaces -q
```

Expected:

```text
FAILED ... KeyError or AssertionError for blade_0_root_transition_surface
```

- [ ] **Step 3: Normalize V0.7 transition surface naming**

For V0.7 only, use stable names:

```text
blade_0_leading_transition_surface
blade_0_trailing_transition_surface
blade_0_root_transition_surface
blade_0_tip_transition_surface
```

Keep V0.6 names unchanged.

- [ ] **Step 4: Generate policy-driven transition surfaces**

In the blade surface loop:

```python
root_policy = transition_policies["blade_root_to_hub.default"]
if root_policy["enabled"]:
    root_surface = _transition_surface_record(
        surface_id=f"{prefix}_root_transition_surface",
        edge_family="blade_root_to_hub",
        policy=root_policy,
        fillet_role="blade_root_fillet",
        chamfer_role="blade_root_chamfer",
        grid=_root_fillet_grid(blade) if root_policy["treatment"] == "fillet" else _span_closure_grid(pressure, mean, suction, 0),
        feature_id=f"{blade_feature_id}.root_transition",
    )
    blade_surfaces.append(root_surface)
```

Add helper:

```python
def _transition_surface_record(surface_id, edge_family, policy, fillet_role, chamfer_role, grid, feature_id):
    treatment = policy["treatment"]
    role = fillet_role if treatment == "fillet" else chamfer_role
    control_net, cad_surface = _control_net_and_cad_surface(
        surface_id,
        role,
        feature_id,
        grid,
        source="surface_graph.control_net_transition_surface",
    )
    return {
        "id": surface_id,
        "kind": "transition_surface",
        "role": role,
        "edge_family": edge_family,
        "transition_policy_id": policy["policy_id"],
        "treatment": treatment,
        "radius_mm": _round(policy["radius_mm"]),
        "cfd_role": _cfd_role_for_edge_family(edge_family),
        "feature_id": feature_id,
        "control_net": control_net,
        "uv_grid": grid,
        "cad_surface": cad_surface,
        "display": {"color": _transition_color(treatment), "opacity": 1.0, "edge_highlight": True},
    }
```

- [ ] **Step 5: Preserve V0.6 behavior**

Gate new naming and policy behavior:

```python
is_v07 = str((dsl_context or {}).get("dsl_version")) == "0.7"
```

For `is_v07 is False`, keep existing V0.6 surface ids and roles.

- [ ] **Step 6: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_transition_override_changes_blade_root_surface_role_and_radius tests/test_impeller_kernel.py::test_v07_disabled_transition_removes_blade_root_transition_surfaces tests/test_workflow.py::test_impeller_v06_open_and_closed_workflows_include_brep_mesh_and_fillets -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py tests/test_impeller_kernel.py
git commit -m "feat: generate policy-driven blade transitions"
```

---

### Task 8: Hub And Hood Edge Treatment Families

**Files:**
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/constructors/closed_impeller.json`
- Test: `tests/test_impeller_kernel.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing tests for hub families**

Add to `tests/test_impeller_kernel.py`:

```python
def test_v07_hub_edge_treatments_are_policy_linked():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from part_rule_synthesis.service import RuleSynthesisService

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_7")
        run = service.instantiate(engine.engine_id, {})

    surfaces = {surface["id"]: surface for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]}
    assert surfaces["hub_bottom_outer_transition_surface"]["edge_family"] == "hub_bottom_outer"
    assert surfaces["hub_bottom_outer_transition_surface"]["transition_policy_id"] == "hub_bottom_outer.default"
    assert surfaces["hub_top_outer_transition_surface"]["edge_family"] == "hub_top_outer"
    assert surfaces["mounting_bore_top_transition_surface"]["edge_family"] == "mounting_bore_top"
    assert surfaces["mounting_bore_bottom_transition_surface"]["edge_family"] == "mounting_bore_bottom"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_hub_edge_treatments_are_policy_linked -q
```

Expected:

```text
FAILED ... KeyError: 'hub_bottom_outer_transition_surface'
```

- [ ] **Step 3: Replace V0.7 hub chamfer naming with transition naming**

For V0.7 only, map existing hub chamfer grids into:

```text
hub_bottom_outer_transition_surface
hub_top_outer_transition_surface
mounting_bore_top_transition_surface
mounting_bore_bottom_transition_surface
```

Each surface gets:

```python
{
    "kind": "transition_surface",
    "edge_family": "hub_bottom_outer",
    "transition_policy_id": "hub_bottom_outer.default",
    "treatment": policy["treatment"],
    "radius_mm": _round(policy["radius_mm"]),
}
```

- [ ] **Step 4: Add hood families for closed V0.7**

In `closed_impeller.json`, ensure `edge_families` includes:

```json
{
  "hood_inlet_lip": {
    "scope": "front_hood",
    "adjacent_roles": ["front_hood_outer_surface", "front_shroud_inner_surface"],
    "default_treatment": "fillet",
    "default_radius_parameter": "hood_chamfer_radius_mm",
    "cfd_patch_group": "solid_context"
  },
  "hood_outlet_lip": {
    "scope": "front_hood",
    "adjacent_roles": ["front_hood_outer_surface", "hood_cap"],
    "default_treatment": "fillet",
    "default_radius_parameter": "hood_chamfer_radius_mm",
    "cfd_patch_group": "solid_context"
  },
  "blade_tip_to_shroud": {
    "scope": "blade_pattern",
    "adjacent_roles": ["blade_pressure", "blade_suction", "front_shroud_inner_surface"],
    "default_treatment": "fillet",
    "default_radius_parameter": "tip_edge_radius_mm",
    "cfd_patch_group": "tip_fillet_wall"
  }
}
```

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_kernel.py::test_v07_hub_edge_treatments_are_policy_linked tests/test_workflow.py::test_impeller_v07_exports_bounded_step_and_no_default_mesh_step -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/constructors/closed_impeller.json `
  tests/test_impeller_kernel.py
git commit -m "feat: add v0.7 hub and hood transition families"
```

---

### Task 9: Mesh Manifest Upgrade And OBJ Export

**Files:**
- Create: `src/part_rule_synthesis/impeller_mesh_export.py`
- Modify: `src/part_rule_synthesis/impeller_mesh_manifest.py`
- Modify: `src/part_rule_synthesis/service.py`
- Test: `tests/test_impeller_mesh_export.py`
- Test: `tests/test_impeller_mesh_manifest.py`

- [ ] **Step 1: Write failing OBJ export tests**

Create `tests/test_impeller_mesh_export.py`:

```python
from pathlib import Path

from part_rule_synthesis.impeller_mesh_export import write_surface_graph_obj


def _graph():
    return {
        "surfaces": [
            {
                "id": "blade_0_root_transition_surface",
                "feature_id": "blade_00.root_transition",
                "role": "blade_root_fillet",
                "edge_family": "blade_root_to_hub",
                "transition_policy_id": "blade_root_to_hub.default",
                "uv_grid": [
                    [[1, 0, 0], [1, 1, 0]],
                    [[2, 0, 0], [2, 1, 0]],
                ],
            }
        ]
    }


def test_write_surface_graph_obj_groups_by_surface_and_transition(tmp_path: Path):
    path = tmp_path / "mesh.obj"
    manifest = write_surface_graph_obj(path, "impeller", _graph())

    text = path.read_text(encoding="utf-8")
    assert "g blade_0_root_transition_surface" in text
    assert "v 1.000000 0.000000 0.000000" in text
    assert "f 1 2 3" in text or "f 2 4 3" in text
    assert manifest["export_exactness"] == "surface_graph_obj_mesh"
    assert manifest["transition_regions"][0]["edge_family"] == "blade_root_to_hub"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_mesh_export.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'part_rule_synthesis.impeller_mesh_export'
```

- [ ] **Step 3: Implement OBJ writer**

Create `src/part_rule_synthesis/impeller_mesh_export.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from part_rule_synthesis.impeller_surface_graph_export import triangulate_surface_graph


def write_surface_graph_obj(
    path: Path,
    solid_name: str,
    surface_graph: dict[str, Any],
    view_id: str = "cad_review_360",
) -> dict[str, Any]:
    triangulation = triangulate_surface_graph(surface_graph, view_id=view_id)
    lines = [f"o {solid_name}"]
    vertex_index = 1
    transition_regions = []

    for region in triangulation["triangle_regions"]:
        surface_id = region["surface_graph_id"]
        lines.append(f"g {surface_id}")
        start = region["triangle_start"]
        count = region["triangle_count"]
        for triangle in triangulation["triangles"][start:start + count]:
            face_indices = []
            for point in triangle["points"]:
                lines.append(f"v {float(point[0]):.6f} {float(point[1]):.6f} {float(point[2]):.6f}")
                face_indices.append(vertex_index)
                vertex_index += 1
            lines.append(f"f {face_indices[0]} {face_indices[1]} {face_indices[2]}")
            if triangle.get("role", "").endswith("fillet") or "transition" in triangle.get("role", ""):
                transition_regions.append({
                    "surface_graph_id": surface_id,
                    "edge_family": _edge_family_for_surface(surface_graph, surface_id),
                    "transition_policy_id": _policy_for_surface(surface_graph, surface_id),
                    "triangle_start": start,
                    "triangle_count": count,
                })
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "source": "surface_graph",
        "view": view_id,
        "export_exactness": "surface_graph_obj_mesh",
        "triangle_count": triangulation["triangle_count"],
        "surface_count": len(triangulation["included_surface_ids"]),
        "transition_regions": transition_regions,
    }


def _surface_by_id(surface_graph: dict[str, Any], surface_id: str) -> dict[str, Any]:
    for surface in surface_graph.get("surfaces", []):
        if surface.get("id") == surface_id or surface.get("surface_graph_id") == surface_id:
            return surface
    return {}


def _edge_family_for_surface(surface_graph: dict[str, Any], surface_id: str) -> str:
    return str(_surface_by_id(surface_graph, surface_id).get("edge_family", ""))


def _policy_for_surface(surface_graph: dict[str, Any], surface_id: str) -> str:
    return str(_surface_by_id(surface_graph, surface_id).get("transition_policy_id", ""))
```

- [ ] **Step 4: Add transition regions to mesh manifest**

Modify `build_surface_mesh_manifest` to append:

```python
"transition_regions": [
    {
        "surface_graph_id": region["surface_graph_id"],
        "feature_id": region["feature_id"],
        "role": region["role"],
        "edge_family": _surface_lookup(surface_graph).get(region["surface_graph_id"], {}).get("edge_family", ""),
        "transition_policy_id": _surface_lookup(surface_graph).get(region["surface_graph_id"], {}).get("transition_policy_id", ""),
        "triangle_start": region["triangle_start"],
        "triangle_count": region["triangle_count"],
    }
    for region in triangulation["triangle_regions"]
    if _surface_lookup(surface_graph).get(region["surface_graph_id"], {}).get("transition_policy_id")
],
```

Add a local helper that builds the lookup once inside the function:

```python
surfaces_by_id = {
    str(surface.get("id") or surface.get("surface_graph_id")): surface
    for surface in surface_graph.get("surfaces", [])
}
```

Use `surfaces_by_id` in the list expression, not repeated helper calls.

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_mesh_export.py tests/test_impeller_mesh_manifest.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_mesh_export.py src/part_rule_synthesis/impeller_mesh_manifest.py tests/test_impeller_mesh_export.py tests/test_impeller_mesh_manifest.py
git commit -m "feat: export v0.7 obj mesh regions"
```

---

### Task 10: Frontend Edge Treatment Model And Panel

**Files:**
- Create: `frontend/src/edgeTreatmentModel.js`
- Create: `frontend/src/edgeTreatmentModel.test.js`
- Create: `frontend/src/components/EdgeTreatmentPanel.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/appModel.js`
- Modify: `frontend/src/appModel.test.js`
- Test: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Write frontend model tests**

Create `frontend/src/edgeTreatmentModel.test.js`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTransitionOverridePayload,
  edgeTreatmentRows,
  updateTransitionRow,
} from "./edgeTreatmentModel.js";

test("edgeTreatmentRows turns manifest policies into family rows", () => {
  const rows = edgeTreatmentRows({
    edge_families: {
      "blade_root_to_hub": { scope: "blade_pattern" },
    },
    transition_policies: {
      "blade_root_to_hub.default": {
        edge_family: "blade_root_to_hub",
        enabled: true,
        treatment: "fillet",
        radius_mm: 8,
        continuity: "G1",
      },
    },
  });

  assert.deepEqual(rows, [
    {
      policyId: "blade_root_to_hub.default",
      edgeFamily: "blade_root_to_hub",
      scope: "blade_pattern",
      enabled: true,
      treatment: "fillet",
      radiusMm: 8,
      continuity: "G1",
      status: "OK",
    },
  ]);
});

test("updateTransitionRow applies treatment and radius changes", () => {
  const current = {
    "blade_root_to_hub.default": { enabled: true, treatment: "fillet", radius_mm: 8 },
  };
  const next = updateTransitionRow(current, "blade_root_to_hub.default", {
    treatment: "chamfer",
    radiusMm: 6.5,
  });

  assert.equal(next["blade_root_to_hub.default"].treatment, "chamfer");
  assert.equal(next["blade_root_to_hub.default"].radius_mm, 6.5);
});

test("buildTransitionOverridePayload omits empty overrides", () => {
  assert.equal(buildTransitionOverridePayload({}), null);
  assert.deepEqual(buildTransitionOverridePayload({
    "blade_root_to_hub.default": { enabled: false, treatment: "none", radius_mm: 0 },
  }), {
    "blade_root_to_hub.default": { enabled: false, treatment: "none", radius_mm: 0 },
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- src/edgeTreatmentModel.test.js
```

Expected:

```text
ERR_MODULE_NOT_FOUND
```

- [ ] **Step 3: Implement frontend model**

Create `frontend/src/edgeTreatmentModel.js`:

```javascript
export function edgeTreatmentRows(manifest) {
  const families = manifest?.edge_families || {};
  const policies = manifest?.transition_policies || {};
  return Object.entries(policies).map(([policyId, policy]) => {
    const family = families[policy.edge_family] || {};
    return {
      policyId,
      edgeFamily: policy.edge_family,
      scope: family.scope || "",
      enabled: Boolean(policy.enabled),
      treatment: policy.treatment || "none",
      radiusMm: Number(policy.radius_mm || 0),
      continuity: policy.continuity || "",
      status: transitionStatus(policy),
    };
  }).sort((a, b) => a.policyId.localeCompare(b.policyId));
}

export function updateTransitionRow(currentOverrides, policyId, patch) {
  const current = currentOverrides?.[policyId] || {};
  return {
    ...(currentOverrides || {}),
    [policyId]: {
      enabled: patch.enabled ?? current.enabled ?? true,
      treatment: patch.treatment ?? current.treatment ?? "fillet",
      radius_mm: Number(patch.radiusMm ?? current.radius_mm ?? 0),
    },
  };
}

export function buildTransitionOverridePayload(overrides) {
  return Object.keys(overrides || {}).length ? overrides : null;
}

function transitionStatus(policy) {
  if (!policy.enabled || policy.treatment === "none") {
    return "OFF";
  }
  if (Number(policy.radius_mm || 0) < 0) {
    return "INVALID";
  }
  return "OK";
}
```

- [ ] **Step 4: Add panel component**

Create `frontend/src/components/EdgeTreatmentPanel.js`:

```javascript
import React from "react";

import { edgeTreatmentRows, updateTransitionRow } from "../edgeTreatmentModel.js";

const h = React.createElement;

export function EdgeTreatmentPanel({ manifest, overrides, onChange }) {
  const rows = edgeTreatmentRows(manifest);
  return h("section", { className: "panel-section edge-treatment-panel" }, [
    h("div", { key: "title", className: "section-title" }, "Edge treatment"),
    h(
      "div",
      { key: "rows", className: "edge-treatment-list" },
      rows.map((row) =>
        h("div", { key: row.policyId, className: "edge-treatment-row" }, [
          h("label", { key: "enabled", className: "toggle" }, [
            h("input", {
              type: "checkbox",
              checked: row.enabled,
              onChange: (event) => onChange(updateTransitionRow(overrides, row.policyId, { enabled: event.target.checked })),
            }),
            row.edgeFamily.replaceAll("_", " "),
          ]),
          h("select", {
            key: "treatment",
            value: row.treatment,
            onChange: (event) => onChange(updateTransitionRow(overrides, row.policyId, { treatment: event.target.value })),
          }, ["none", "chamfer", "fillet"].map((value) => h("option", { key: value, value }, value))),
          h("input", {
            key: "radius",
            type: "number",
            min: "0",
            step: "0.5",
            value: row.radiusMm,
            onChange: (event) => onChange(updateTransitionRow(overrides, row.policyId, { radiusMm: event.target.value })),
          }),
          h("span", { key: "status", className: "status-pill" }, row.status),
        ]),
      ),
    ),
  ]);
}
```

- [ ] **Step 5: Wire panel into App**

In `frontend/src/App.js`:

```javascript
import { buildTransitionOverridePayload } from "./edgeTreatmentModel.js";
import { EdgeTreatmentPanel } from "./components/EdgeTreatmentPanel.js";
```

Add state:

```javascript
const [transitionOverrides, setTransitionOverrides] = useState({});
```

Pass to instantiate:

```javascript
buildTransitionOverridePayload(transitionOverrides)
```

Render panel after `GenerationStagePanel`:

```javascript
h(EdgeTreatmentPanel, {
  manifest,
  overrides: transitionOverrides,
  onChange: setTransitionOverrides,
})
```

- [ ] **Step 6: Update instantiate payload helper**

In `frontend/src/appModel.js`, update `buildInstantiatePayload` signature:

```javascript
export function buildInstantiatePayload(
  inputParameters,
  profileOverrides = null,
  curveOverrides = null,
  transitionOverrides = null,
  geometryStage = "edge_closures",
) {
```

Add:

```javascript
if (transitionOverrides) {
  payload.transition_overrides = transitionOverrides;
}
```

- [ ] **Step 7: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
```

Expected:

```text
pass
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add frontend/src/edgeTreatmentModel.js `
  frontend/src/edgeTreatmentModel.test.js `
  frontend/src/components/EdgeTreatmentPanel.js `
  frontend/src/App.js `
  frontend/src/appModel.js `
  frontend/src/appModel.test.js `
  frontend/src/appFiles.test.js
git commit -m "feat: add frontend edge treatment controls"
```

---

### Task 11: Viewer Transition Highlight And Mesh Overlay

**Files:**
- Create: `frontend/src/meshOverlayModel.js`
- Create: `frontend/src/meshOverlayModel.test.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/components/MeshInspectionPanel.js`
- Modify: `frontend/src/simulationViewModel.js`
- Modify: `frontend/src/workspaceModel.js`
- Test: `frontend/src/appFiles.test.js`
- Test: `frontend/src/simulationViewModel.test.js`

- [ ] **Step 1: Write mesh overlay model tests**

Create `frontend/src/meshOverlayModel.test.js`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";

import { meshOverlayOptions, transitionRegionRows } from "./meshOverlayModel.js";

test("meshOverlayOptions exposes edge and quality modes", () => {
  assert.deepEqual(meshOverlayOptions().map((option) => option.id), [
    "off",
    "triangle_edges",
    "patch_groups",
    "quality",
    "transitions",
  ]);
});

test("transitionRegionRows maps mesh manifest transition regions", () => {
  const rows = transitionRegionRows({
    transition_regions: [
      {
        edge_family: "blade_root_to_hub",
        transition_policy_id: "blade_root_to_hub.default",
        surface_graph_id: "blade_0_root_transition_surface",
        triangle_count: 24,
      },
    ],
  });

  assert.equal(rows[0].edgeFamily, "blade_root_to_hub");
  assert.equal(rows[0].triangleCount, 24);
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd frontend
npm.cmd test -- src/meshOverlayModel.test.js
```

Expected:

```text
ERR_MODULE_NOT_FOUND
```

- [ ] **Step 3: Implement mesh overlay model**

Create `frontend/src/meshOverlayModel.js`:

```javascript
export function meshOverlayOptions() {
  return [
    { id: "off", label: "Off" },
    { id: "triangle_edges", label: "Triangle edges" },
    { id: "patch_groups", label: "Patch groups" },
    { id: "quality", label: "Quality" },
    { id: "transitions", label: "Transitions" },
  ];
}

export function transitionRegionRows(meshManifest) {
  return (meshManifest?.transition_regions || []).map((region) => ({
    edgeFamily: region.edge_family || "",
    transitionPolicyId: region.transition_policy_id || "",
    surfaceGraphId: region.surface_graph_id || "",
    triangleCount: Number(region.triangle_count || 0),
  }));
}
```

- [ ] **Step 4: Add mesh overlay state to ModelViewer**

In `ModelViewer`, add prop:

```javascript
meshOverlayMode = "triangle_edges",
```

When `simulationViewMode === "mesh"` and overlay mode is not `off`, add triangle edges:

```javascript
const wire = new THREE.LineSegments(
  new THREE.WireframeGeometry(geometry),
  new THREE.LineBasicMaterial({
    color: transitionSurface ? "#f97316" : "#111827",
    transparent: true,
    opacity: transitionSurface ? 0.95 : 0.32,
  }),
);
wire.userData.layer = transitionSurface ? "transition_mesh_edges" : "mesh_edges";
mesh.add(wire);
```

Define:

```javascript
const transitionSurface = Boolean(surface.transition_policy_id || surface.edge_family);
```

- [ ] **Step 5: Update workspace layers**

In `frontend/src/workspaceModel.js`, include:

```javascript
transition_surfaces: true,
mesh_edges: true,
transition_mesh_edges: true,
solid_context: true,
fluid_boundary: true,
```

Map transition surfaces:

```javascript
if (surface.transition_policy_id || String(surface.role || "").includes("fillet") || String(surface.role || "").includes("chamfer")) {
  return "transition_surfaces";
}
```

- [ ] **Step 6: Update MeshInspectionPanel**

Render transition region rows:

```javascript
transitionRegionRows(meshManifest).map((row) =>
  h("button", { key: row.surfaceGraphId, className: "patch-row", type: "button" }, [
    h("span", null, row.edgeFamily),
    h("strong", null, String(row.triangleCount)),
  ]),
)
```

- [ ] **Step 7: Run frontend tests and build**

Run:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

Expected:

```text
pass
frontend build check passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add frontend/src/meshOverlayModel.js `
  frontend/src/meshOverlayModel.test.js `
  frontend/src/components/ModelViewer.js `
  frontend/src/components/MeshInspectionPanel.js `
  frontend/src/simulationViewModel.js `
  frontend/src/workspaceModel.js `
  frontend/src/appFiles.test.js `
  frontend/src/simulationViewModel.test.js
git commit -m "feat: show transition mesh overlays"
```

---

### Task 12: OCCT Re-Import, Bounding Box, And Exactness Gate

**Files:**
- Modify: `src/part_rule_synthesis/impeller_bounded_brep_export.py`
- Test: `tests/test_impeller_bounded_brep_export.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing validation tests**

Add to `tests/test_impeller_bounded_brep_export.py`:

```python
from part_rule_synthesis.impeller_bounded_brep_export import reimport_step_bbox


def test_reimport_step_bbox_reports_finite_scale(tmp_path: Path):
    step_path = tmp_path / "annular.step"
    write_bounded_brep_step(
        step_path,
        "test_impeller",
        {"surfaces": [_annular_surface()], "edges": []},
        view_id="cad_review_360",
    )

    bbox = reimport_step_bbox(step_path)
    assert bbox["x_span_mm"] <= 310.0
    assert bbox["y_span_mm"] <= 310.0
    assert bbox["z_span_mm"] <= 1.0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_bounded_brep_export.py::test_reimport_step_bbox_reports_finite_scale -q
```

Expected:

```text
ImportError or AttributeError for reimport_step_bbox
```

- [ ] **Step 3: Implement re-import bbox**

Add:

```python
def reimport_step_bbox(path: Path) -> dict[str, float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"OCCT STEP read failed with status {status}")
    reader.TransferRoots()
    shape = reader.OneShape()
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    x_min, y_min, z_min, x_max, y_max, z_max = box.Get()
    return {
        "x_min": float(x_min),
        "x_max": float(x_max),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "z_min": float(z_min),
        "z_max": float(z_max),
        "x_span_mm": float(x_max - x_min),
        "y_span_mm": float(y_max - y_min),
        "z_span_mm": float(z_max - z_min),
    }
```

- [ ] **Step 4: Gate exactness in manifest**

After writing STEP:

```python
bbox = reimport_step_bbox(step_path)
finite_bbox = max(bbox["x_span_mm"], bbox["y_span_mm"], bbox["z_span_mm"]) < 5000.0
exactness = BOUNDED_STEP_EXACTNESS if finite_bbox and regions else DIAGNOSTIC_BOUNDED_UNSEWN_EXACTNESS
```

Return:

```python
"export_exactness": exactness,
"reimport_bbox": bbox,
"validation_checks": [
    {"name": "finite_reimport_bbox", "status": "PASS" if finite_bbox else "FAIL"}
],
```

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_impeller_bounded_brep_export.py tests/test_workflow.py::test_impeller_v07_exports_bounded_step_and_no_default_mesh_step -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/part_rule_synthesis/impeller_bounded_brep_export.py tests/test_impeller_bounded_brep_export.py tests/test_workflow.py
git commit -m "test: gate v0.7 step exactness by reimport bbox"
```

---

### Task 13: Workflow, Evidence, And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/current-research-frontier.md`
- Modify: `docs/repository-map.md`
- Modify: `docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/CHANGELOG.md`
- Test: `tests/test_workflow.py`
- Test: `tests/test_impeller_version_lineage.py`

- [ ] **Step 1: Add final workflow test**

Add to `tests/test_workflow.py`:

```python
def test_impeller_v07_open_and_closed_workflows_include_transitions_bounded_step_and_obj(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)

    for preset_id in ["radial_open_reference_v0_7", "radial_closed_reference_v0_7"]:
        engine = service.synthesize("impeller", preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest

        assert manifest["dsl_version"] == "0.7"
        assert manifest["transition_policies"]
        assert manifest["edge_families"]
        assert Path(manifest["exports"]["step"]).exists()
        assert Path(manifest["exports"]["stl"]).exists()
        assert Path(manifest["exports"]["obj"]).exists()
        assert manifest["export_manifests"]["step"]["bounded_face_count"] > 0
        assert manifest["export_manifests"]["obj"]["triangle_count"] > 0
        assert manifest["simulation_manifests"]["cfd_surface_mesh"]["transition_regions"]
```

- [ ] **Step 2: Run final workflow tests**

Run:

```powershell
$env:PYTHONPATH='src'
pytest tests/test_workflow.py::test_impeller_v07_open_and_closed_workflows_include_transitions_bounded_step_and_obj -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Generate V0.7 evidence artifacts locally**

Run:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(
    Path("Model Output") / "_v07_evidence_runs",
    model_output_root=Path("Model Output") / "_v07_evidence_exports",
)
for preset_id in ["radial_open_reference_v0_7", "radial_closed_reference_v0_7"]:
    engine = service.synthesize("impeller", preset_id=preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    print(preset_id, run.run_id)
    for key in ["step", "stl", "obj", "manifest"]:
        path = Path(manifest["exports"][key])
        print(" ", key, path, path.stat().st_size)
    print(" ", manifest["export_manifests"]["step"]["export_exactness"])
    print(" ", manifest["export_manifests"]["step"].get("reimport_bbox"))
'@ | python -
```

Expected:

```text
radial_open_reference_v0_7 run-...
  step ... positive_size
  stl ... positive_size
  obj ... positive_size
  manifest ... positive_size
```

- [ ] **Step 4: Update evidence README**

Append a section to `docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md`:

```markdown
## 7. V0.7 Implementation Evidence

Generated local artifacts under `Model Output/_v07_evidence_exports`.

Recorded checks:

- V0.7 open and closed presets generated STEP, STL, OBJ, and manifest artifacts.
- STEP export manifest recorded bounded face count and OCCT re-import bounding box.
- OBJ export manifest recorded transition regions.
- Generated binaries remain untracked.
```

Include the actual printed run ids and sizes from Step 3.

- [ ] **Step 5: Update README and repository docs**

In `README.md`, add V0.7 to the version table:

```markdown
| `v0_7` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7` | `radial_open_reference_v0_7`, `radial_closed_reference_v0_7` | Bounded B-Rep faces, edge-family transition policies, OBJ mesh artifacts, and mesh overlay inspection. |
```

In `docs/current-research-frontier.md`, state:

```markdown
V0.7 advances from support-face B-Rep evidence to bounded face export with transition-policy provenance. Manufacturing certification and CFD volume meshing remain outside the current prototype.
```

In `docs/repository-map.md`, add the V0.7 resource directory summary.

- [ ] **Step 6: Run full verification**

Run:

```powershell
.\scripts\verify_repository.ps1 -Mode fast
.\scripts\verify_repository.ps1 -Mode full
```

Expected:

```text
backend tests passed
frontend tests passed
frontend build check passed
```

- [ ] **Step 7: Run lineage verification**

On Windows, if path length blocks tag worktrees, use the same short-drive and process-level longpaths pattern used during V0.6 verification:

```powershell
$drive = 'T:'
$root = (Get-Location).Path
cmd /c "subst $drive `"$root`""
try {
  Push-Location "$drive\"
  $env:GIT_CONFIG_COUNT = '1'
  $env:GIT_CONFIG_KEY_0 = 'core.longpaths'
  $env:GIT_CONFIG_VALUE_0 = 'true'
  powershell -ExecutionPolicy Bypass -File .\scripts\verify_version_lineage.ps1
  Pop-Location
} finally {
  cmd /c "subst $drive /D"
}
```

Expected:

```text
Version lineage verification passed.
```

- [ ] **Step 8: Commit docs and final workflow tests**

Run:

```powershell
git add README.md `
  docs/current-research-frontier.md `
  docs/repository-map.md `
  docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/CHANGELOG.md `
  tests/test_workflow.py
git commit -m "docs: record impeller v0.7 bounded transition evidence"
```

- [ ] **Step 9: Final status**

Run:

```powershell
git status -sb
git log --oneline --max-count=8
```

Expected:

```text
## impeller-v0.7-bounded-transitions
?? "Model Output/"
```

Only local generated artifacts remain untracked.

---

## Plan Self-Review

Spec coverage:

- Bounded CAD faces: Tasks 4, 5, and 12.
- Edge treatment policies: Tasks 3, 6, 7, and 8.
- Family-level frontend UI: Task 10.
- Transition display and real mesh overlay: Task 11.
- Mesh export default beyond STL: Task 9.
- CFD boundary versus solid-context semantics: Tasks 10 and 11.
- V0.7 version lineage and evidence: Tasks 2 and 13.

Completeness scan:

- Each task names exact files.
- Each implementation task starts with a failing test.
- Each task has concrete commands and expected outcomes.
- Generated binaries remain outside commits.

Type consistency:

- Backend payload uses `transition_overrides`.
- Manifest fields use `edge_families` and `transition_policies`.
- Surface graph edge metadata uses `edge_family`, `transition_policy_id`, and `transition_surface_ids`.
- Export exactness labels are `surface_graph_trimmed_brep_step`, `surface_graph_bounded_unsewn_brep_step`, and `surface_graph_obj_mesh`.

Execution handoff:

Plan complete and saved to `docs/superpowers/plans/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
