# Impeller v0.4 Surface/Feature Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable v0.4 surface/feature graph compiler contract for `AxisymmetricThroughflowRadialBladedImpeller`, with full-360 CFD manifest output and schema-level FEA view preparation.

**Architecture:** Keep v0.3 geometry behavior intact, then layer v0.4 resource files, design-space/campaign-signature logic, graph contract helpers, and CFD manifest generation around the existing axisymmetric NURBS kernel. The kernel remains research-grade sampled geometry; v0.4 adds stable identities, feature visibility, patch grouping, and validity checks so downstream CAD/CAE work has a contract.

**Tech Stack:** Python 3, FastAPI service layer, JSON DSL resources, pytest, React-free ESM frontend with Node test runner, Three.js viewer.

---

## Scope Check

This plan implements the v0.4 first executable slice only.

Included:

- v0.4 ontology/DSL JSON resources.
- Runtime loading of v0.4 presets alongside v0.2 and v0.3.
- Design-space/campaign-signature data model.
- Flexible clamped NURBS profile support for meridional hub/tip profiles.
- Feature graph nodes for implemented assembly features and research-grade transition features.
- Full-360 CFD manifest with group + instance patch naming.
- Frontend panels/models for view mode, CFD manifest inspection, and campaign freeze display.

Excluded from this plan:

- Periodic single-passage sector generation.
- Solver adapters, mesh adapters, DOE runner, result database, or optimization execution.
- Industrial exact B-Rep fillets.
- Full tensor-product NURBS surface editing UI.
- Complete executable FEA pipeline.

## File Structure

Create:

- `src/part_rule_synthesis/ontology/impeller/v0_4/slice.json`
- `src/part_rule_synthesis/ontology/impeller/v0_4/entities.json`
- `src/part_rule_synthesis/ontology/impeller/v0_4/relations.json`
- `src/part_rule_synthesis/ontology/impeller/v0_4/validity_contracts.json`
- `src/part_rule_synthesis/ontology/impeller/v0_4/loss_schema.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/schema.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/CHANGELOG.md`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/aliases.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/constructors/open_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/constructors/closed_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/presets/radial_open_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/presets/radial_closed_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/shape_controls/default_shape_controls.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/simulation_views/cfd_full_360.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/simulation_views/fea_solid_schema.json`
- `src/part_rule_synthesis/impeller_design_space.py`
- `src/part_rule_synthesis/impeller_graph_contract.py`
- `src/part_rule_synthesis/impeller_cfd_manifest.py`
- `tests/test_impeller_v04_resources.py`
- `tests/test_impeller_design_space.py`
- `tests/test_impeller_profile_topology.py`
- `tests/test_impeller_cfd_manifest.py`
- `frontend/src/simulationViewModel.js`
- `frontend/src/simulationViewModel.test.js`
- `frontend/src/components/CfdManifestPanel.js`

Modify:

- `src/part_rule_synthesis/impeller_dsl_resources.py`
- `src/part_rule_synthesis/impeller_runtime_compiler.py`
- `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- `src/part_rule_synthesis/service.py`
- `frontend/src/workspaceModel.js`
- `frontend/src/components/ModelViewer.js`
- `frontend/src/App.js`
- `frontend/src/styles.css`
- `frontend/src/appFiles.test.js`
- `tests/test_impeller_runtime_compiler.py`
- `tests/test_acceptance.py`

---

### Task 1: Add v0.4 Ontology And DSL Resources

**Files:**

- Create: `src/part_rule_synthesis/ontology/impeller/v0_4/slice.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_4/entities.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_4/relations.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_4/validity_contracts.json`
- Create: `src/part_rule_synthesis/ontology/impeller/v0_4/loss_schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/constructors/open_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/constructors/closed_impeller.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/presets/radial_open_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/presets/radial_closed_reference.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/shape_controls/default_shape_controls.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/simulation_views/cfd_full_360.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/simulation_views/fea_solid_schema.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/aliases.json`
- Create: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/CHANGELOG.md`
- Create: `tests/test_impeller_v04_resources.py`

- [ ] **Step 1: Write failing resource tests**

Create `tests/test_impeller_v04_resources.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = PROJECT_ROOT / "src" / "part_rule_synthesis" / "ontology" / "impeller" / "v0_4"
DSL_ROOT = (
    PROJECT_ROOT
    / "src"
    / "part_rule_synthesis"
    / "dsl"
    / "impeller"
    / "axisymmetric_throughflow_radial_bladed"
    / "v0_4"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v04_resource_files_exist_and_are_valid_json():
    ontology_files = [
        "slice.json",
        "entities.json",
        "relations.json",
        "validity_contracts.json",
        "loss_schema.json",
    ]
    dsl_files = [
        "schema.json",
        "constructors/open_impeller.json",
        "constructors/closed_impeller.json",
        "presets/radial_open_reference.json",
        "presets/radial_closed_reference.json",
        "shape_controls/default_shape_controls.json",
        "simulation_views/cfd_full_360.json",
        "simulation_views/fea_solid_schema.json",
        "aliases.json",
    ]

    for name in ontology_files:
        assert isinstance(read_json(ONTOLOGY_ROOT / name), dict), name
    for name in dsl_files:
        assert isinstance(read_json(DSL_ROOT / name), dict), name


def test_v04_schema_defines_graph_contract_design_space_and_simulation_views():
    schema = read_json(DSL_ROOT / "schema.json")

    assert schema["dsl_version"] == "0.4"
    assert schema["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert "design_space" in schema["required_sections"]
    assert "surface_graph_contract" in schema["required_sections"]
    assert "feature_graph_contract" in schema["required_sections"]
    assert "simulation_views" in schema["required_sections"]
    assert schema["patch_naming_policy"] == "group_and_instance"


def test_v04_design_space_separates_topology_and_numeric_variables():
    shape_controls = read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json")

    assert shape_controls["shape_control_version"] == "0.4"
    assert "topology_variables" in shape_controls["design_space"]
    assert "design_variables" in shape_controls["design_space"]
    assert "hub_profile.control_point_count" in shape_controls["design_space"]["topology_variables"]
    assert "root_fillet.radius_mm" in shape_controls["design_space"]["design_variables"]
    assert shape_controls["campaign_freeze_rule"] == "topology_variables_immutable_inside_campaign"


def test_v04_simulation_views_define_cfd_executable_and_fea_schema_only():
    cfd = read_json(DSL_ROOT / "simulation_views" / "cfd_full_360.json")
    fea = read_json(DSL_ROOT / "simulation_views" / "fea_solid_schema.json")

    assert cfd["view_id"] == "cfd_full_360"
    assert cfd["domain_kind"] == "full_360_wetted_surface"
    assert cfd["status"] == "research_grade_executable"
    assert cfd["patch_naming"] == "group_and_instance"
    assert "mounting_bore" in cfd["feature_suppression"]["suppressed_features"]
    assert fea["view_id"] == "fea_solid"
    assert fea["status"] == "schema_only_v0_4"


def test_v04_constructors_define_feature_graph_and_boundary_guided_blades():
    open_constructor = read_json(DSL_ROOT / "constructors" / "open_impeller.json")
    closed_constructor = read_json(DSL_ROOT / "constructors" / "closed_impeller.json")

    for constructor in [open_constructor, closed_constructor]:
        assert constructor["dsl_version"] == "0.4"
        assert constructor["blade_surface_model"]["kind"] == "boundary_guided_camber_surface_with_thickness"
        assert "leading_edge_round" in constructor["feature_graph"]["blade_transition_features"]
        assert "mounting_bore" in constructor["feature_graph"]["assembly_features"]
        assert "balance_holes" in constructor["feature_graph"]["tuning_features"]

    assert open_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is False
    assert closed_constructor["support_surfaces"]["blade_tip_support_surface"]["material"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_v04_resources.py -q
```

Expected: FAIL because `v0_4` files do not exist.

- [ ] **Step 3: Add v0.4 JSON resources**

Create the JSON files with these minimum contract keys.

`src/part_rule_synthesis/ontology/impeller/v0_4/slice.json`:

```json
{
  "ontology_version": "0.4",
  "slice_id": "impeller.axisymmetric_throughflow_radial_bladed",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "definition": "Optimization-ready radial throughflow impeller slice with explicit surface graph, feature graph, simulation views, campaign design space, and CFD patch manifest contracts.",
  "in_scope": {
    "part_family": ["impeller"],
    "flow_topology": ["radial"],
    "passage_topology": ["throughflow_bladed_channel"],
    "shroud_topology": ["open", "closed"],
    "entry_topology": ["single_entry"],
    "suction_topology": ["single_suction"],
    "blade_exit_geometry": ["backward_curved"],
    "blade_population": ["full_blade_set"],
    "working_domain": ["pump", "compressor", "fan_or_blower", "unknown"],
    "support_surface_model": ["axisymmetric_revolved_meridional_profiles"],
    "blade_surface_model": ["boundary_guided_camber_surface_with_thickness"],
    "simulation_views": ["cad_review_360", "cfd_full_360", "fea_solid"]
  },
  "out_of_scope": [
    "periodic_single_passage_cfd",
    "exact_industrial_brep_fillet",
    "solver_adapter",
    "mesh_adapter",
    "inverse_loading_design"
  ]
}
```

`src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/schema.json`:

```json
{
  "dsl_version": "0.4",
  "supersedes": "../v0_3/schema.json",
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
    "display_policy",
    "validation"
  ]
}
```

`src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/simulation_views/cfd_full_360.json`:

```json
{
  "view_id": "cfd_full_360",
  "domain_kind": "full_360_wetted_surface",
  "status": "research_grade_executable",
  "patch_naming": "group_and_instance",
  "feature_suppression": {
    "suppressed_features": [
      "mounting_bore",
      "shaft_seat",
      "keyway",
      "rear_hub_groove"
    ],
    "reason": "internal assembly features are not part of the wetted CFD flow domain"
  },
  "required_patch_groups": [
    "blade_pressure_wall",
    "blade_suction_wall",
    "leading_edge_wall",
    "trailing_edge_wall",
    "root_fillet_wall",
    "tip_fillet_wall",
    "hub_wall",
    "tip_or_shroud_wall",
    "inlet_patch",
    "outlet_patch"
  ]
}
```

Use the current v0.3 constructors/presets as the numeric base and add v0.4 sections:

```json
{
  "design_space": {
    "design_space_ref": "shape_controls/default_shape_controls.json"
  },
  "blade_surface_model": {
    "kind": "boundary_guided_camber_surface_with_thickness",
    "parameter_domain": {
      "u": "streamwise_leading_to_trailing",
      "v": "spanwise_hub_to_tip"
    },
    "output_surfaces": [
      "camber_surface",
      "pressure_surface",
      "suction_surface",
      "leading_edge_transition",
      "trailing_edge_transition",
      "root_transition",
      "tip_transition"
    ]
  },
  "feature_graph": {
    "blade_transition_features": {
      "leading_edge_round": {
        "kind": "rounded_edge_transition",
        "cfd_patch_group": "leading_edge_wall"
      },
      "trailing_edge_round": {
        "kind": "rounded_or_cutback_edge_transition",
        "cfd_patch_group": "trailing_edge_wall"
      },
      "root_fillet": {
        "kind": "sampled_surface_blend",
        "cfd_patch_group": "root_fillet_wall"
      },
      "tip_transition": {
        "kind": "tip_closure_or_shroud_blend",
        "cfd_patch_group": "tip_fillet_wall"
      }
    },
    "assembly_features": {
      "mounting_bore": {"kind": "axisymmetric_subtractive_cylinder"},
      "shaft_seat": {"kind": "axisymmetric_step_or_counterbore"},
      "keyway": {"kind": "angular_subtractive_slot"},
      "rear_hub_groove": {"kind": "axisymmetric_rear_groove"}
    },
    "tuning_features": {
      "balance_holes": {"status": "schema_only_v0_4"},
      "trim_edge": {"status": "schema_only_v0_4"},
      "lightening_slots": {"status": "schema_only_v0_4"}
    }
  }
}
```

- [ ] **Step 4: Run v0.4 resource tests**

Run:

```powershell
python -m pytest tests/test_impeller_v04_resources.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit resources**

```powershell
git add src/part_rule_synthesis/ontology/impeller/v0_4 `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4 `
  tests/test_impeller_v04_resources.py
git commit -m "feat: add impeller dsl v0.4 resources"
```

---

### Task 2: Load v0.4 Bundles And Compile v0.4 Presets

**Files:**

- Modify: `src/part_rule_synthesis/impeller_dsl_resources.py`
- Modify: `src/part_rule_synthesis/impeller_runtime_compiler.py`
- Modify: `tests/test_impeller_runtime_compiler.py`

- [ ] **Step 1: Add failing runtime compiler tests**

Append to `tests/test_impeller_runtime_compiler.py`:

```python
def test_load_impeller_dsl_bundle_v04_exposes_design_space_and_simulation_views():
    bundle = load_impeller_dsl_bundle("v0_4")

    assert bundle.slice["ontology_version"] == "0.4"
    assert bundle.schema["dsl_version"] == "0.4"
    assert "axisymmetric_throughflow_radial_bladed.open.v0_4" in bundle.constructors
    assert "radial_open_reference_v0_4" in bundle.presets
    assert bundle.shape_controls["shape_control_version"] == "0.4"
    assert "design_space" in bundle.shape_controls
    assert "simulation_views" in bundle.schema["required_sections"]


def test_compile_impeller_runtime_preset_v04_exposes_graph_contracts():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_4")

    assert runtime["version"] == "0.4.0"
    assert runtime["preset_id"] == "radial_open_reference_v0_4"
    assert runtime["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open.v0_4"
    assert runtime["dsl_sections"]["dsl_version"] == "0.4"
    assert runtime["shape_control"]["shape_control_version"] == "0.4"
    assert runtime["simulation_views"]["cfd_full_360"]["domain_kind"] == "full_360_wetted_surface"
    assert runtime["feature_graph"]["assembly_features"]["mounting_bore"]["kind"] == "axisymmetric_subtractive_cylinder"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_runtime_compiler.py::test_load_impeller_dsl_bundle_v04_exposes_design_space_and_simulation_views tests/test_impeller_runtime_compiler.py::test_compile_impeller_runtime_preset_v04_exposes_graph_contracts -q
```

Expected: FAIL because `IMPELLER_DSL_VERSIONS` does not include `v0_4` and the bundle dataclass does not expose simulation views.

- [ ] **Step 3: Extend `ImpellerDslBundle`**

Modify `src/part_rule_synthesis/impeller_dsl_resources.py`:

```python
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
    simulation_views: dict[str, dict[str, Any]]
```

In `load_impeller_dsl_bundle`, load optional simulation views:

```python
simulation_views = (
    _load_json_directory_by_id(dsl_root / "simulation_views", "view_id")
    if (dsl_root / "simulation_views").exists()
    else {}
)
```

Pass `simulation_views=simulation_views` into `ImpellerDslBundle(...)`.

- [ ] **Step 4: Relax shape-control validation for v0.4**

In `_validate_bundle`, keep v0.2/v0.3 compatibility but allow v0.4 design-space controls:

```python
if bundle.schema["dsl_version"] in {"0.2", "0.3"} and bundle.shape_control_schema["default_stage"] != 1:
    raise ValueError("impeller v0.2/v0.3 shape control must default to stage 1")
if bundle.schema["dsl_version"] == "0.4" and "design_space" not in bundle.shape_controls:
    raise ValueError("impeller v0.4 shape controls must include design_space")
```

Keep `_validate_shape_control_policies(bundle)` for v0.2/v0.3 and v0.4 when `policies` exists:

```python
if "policies" in bundle.shape_controls:
    _validate_shape_control_policies(bundle)
```

- [ ] **Step 5: Compile v0.4 runtime fields**

Modify `src/part_rule_synthesis/impeller_runtime_compiler.py`:

```python
IMPELLER_DSL_VERSIONS = ("v0_2", "v0_3", "v0_4")
```

Add fields in `compile_impeller_runtime_preset` return value:

```python
"feature_graph": constructor.get("feature_graph", {}),
"simulation_views": bundle.simulation_views,
```

Update `_selected_rules` so v0.4 includes the graph contract:

```python
if bundle.schema["dsl_version"] == "0.4":
    return [
        f"ontology_slice.{bundle.slice['slice_id']}",
        f"constructor_family.{bundle.slice['constructor_family']}",
        f"constructor.{constructor['constructor_id']}",
        "design_space.campaign_freeze_rule",
        "surface_graph_contract.named_surfaces_required",
        "feature_graph_contract.features_are_first_class_nodes",
        "simulation_views.cfd_full_360",
    ]
```

- [ ] **Step 6: Run runtime compiler tests**

Run:

```powershell
python -m pytest tests/test_impeller_runtime_compiler.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit runtime resource loading**

```powershell
git add src/part_rule_synthesis/impeller_dsl_resources.py `
  src/part_rule_synthesis/impeller_runtime_compiler.py `
  tests/test_impeller_runtime_compiler.py
git commit -m "feat: compile impeller dsl v0.4 presets"
```

---

### Task 3: Add Design Space And Campaign Signature Model

**Files:**

- Create: `src/part_rule_synthesis/impeller_design_space.py`
- Create: `tests/test_impeller_design_space.py`
- Modify: `src/part_rule_synthesis/service.py`

- [ ] **Step 1: Write failing design-space tests**

Create `tests/test_impeller_design_space.py`:

```python
from __future__ import annotations

import pytest

from part_rule_synthesis.impeller_design_space import (
    build_campaign_signature,
    flatten_design_vector,
    require_campaign_compatible,
)


def test_campaign_signature_freezes_topology_not_numeric_values():
    runtime = {
        "preset_id": "radial_open_reference_v0_4",
        "constructor_id": "axisymmetric_throughflow_radial_bladed.open.v0_4",
        "dsl_version": "0.4",
        "shape_control": {
            "design_space": {
                "topology_variables": [
                    "hub_profile.control_point_count",
                    "tip_profile.control_point_count",
                    "enabled_features"
                ],
                "design_variables": [
                    "hub_profile.control_points[*].r_mm",
                    "root_fillet.radius_mm"
                ]
            }
        },
    }
    profiles = {
        "hub_profile": {"degree": 3, "control_points": [[100, 50], [150, 30], [220, 10], [300, 0]]},
        "tip_or_shroud_profile": {"degree": 3, "control_points": [[140, 70], [180, 50], [260, 30], [340, 20]]},
    }
    features = {"mounting_bore": {"enabled": True}, "keyway": {"enabled": True}}

    signature = build_campaign_signature(runtime, profiles, features)

    assert signature["dsl_version"] == "0.4"
    assert signature["profile_topology"]["hub_profile"]["control_point_count"] == 4
    assert signature["enabled_features"] == ["keyway", "mounting_bore"]
    assert signature["design_vector_length"] == 18


def test_campaign_signature_detects_topology_change():
    baseline = {
        "profile_topology": {"hub_profile": {"control_point_count": 4}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
    }
    changed = {
        "profile_topology": {"hub_profile": {"control_point_count": 5}},
        "enabled_features": ["mounting_bore"],
        "patch_groups": ["hub_wall"],
    }

    with pytest.raises(ValueError, match="campaign topology changed"):
        require_campaign_compatible(baseline, changed)


def test_flatten_design_vector_returns_stable_sorted_values():
    values = {
        "root_fillet.radius_mm": 3.0,
        "hub_profile.control_points[1].r_mm": 150.0,
        "hub_profile.control_points[0].r_mm": 100.0,
    }

    vector = flatten_design_vector(values)

    assert vector == [
        {"name": "hub_profile.control_points[0].r_mm", "value": 100.0},
        {"name": "hub_profile.control_points[1].r_mm", "value": 150.0},
        {"name": "root_fillet.radius_mm", "value": 3.0},
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_design_space.py -q
```

Expected: FAIL because `impeller_design_space.py` does not exist.

- [ ] **Step 3: Implement design-space helpers**

Create `src/part_rule_synthesis/impeller_design_space.py`:

```python
from __future__ import annotations

from typing import Any


def build_campaign_signature(
    runtime: dict[str, Any],
    profile_overrides: dict[str, Any] | None,
    feature_states: dict[str, Any] | None,
    patch_groups: list[str] | None = None,
) -> dict[str, Any]:
    profiles = profile_overrides or {}
    features = feature_states or {}
    profile_topology = {}
    for profile_id in ["hub_profile", "tip_or_shroud_profile"]:
        profile = profiles.get(profile_id, {})
        control_points = profile.get("control_points", [])
        profile_topology[profile_id] = {
            "degree": int(profile.get("degree", 3)),
            "control_point_count": len(control_points),
            "knot_count": len(profile.get("knots", [])),
            "weight_count": len(profile.get("weights", [])),
        }
    enabled_features = sorted(
        feature_id for feature_id, state in features.items() if state.get("enabled", True)
    )
    design_vector_length = sum(
        2 * topology["control_point_count"]
        for topology in profile_topology.values()
    ) + len(enabled_features)
    return {
        "dsl_version": str(runtime.get("dsl_sections", {}).get("dsl_version", runtime.get("dsl_version", ""))),
        "preset_id": runtime.get("preset_id"),
        "constructor_id": runtime.get("constructor_id"),
        "profile_topology": profile_topology,
        "enabled_features": enabled_features,
        "patch_groups": sorted(patch_groups or []),
        "design_vector_length": design_vector_length,
        "freeze_rule": "topology_variables_immutable_inside_campaign",
    }


def require_campaign_compatible(previous: dict[str, Any], current: dict[str, Any]) -> None:
    for key in ["profile_topology", "enabled_features", "patch_groups"]:
        if previous.get(key) != current.get(key):
            raise ValueError(f"campaign topology changed: {key}")


def flatten_design_vector(values: dict[str, float | int]) -> list[dict[str, float]]:
    return [
        {"name": name, "value": float(values[name])}
        for name in sorted(values)
    ]
```

- [ ] **Step 4: Add signature to service manifest**

In `src/part_rule_synthesis/service.py`, import:

```python
from part_rule_synthesis.impeller_design_space import build_campaign_signature
```

After `geometry_validity = ...` in `RuleSynthesisService.instantiate`, add:

```python
campaign_signature = (
    build_campaign_signature(
        dsl,
        normalized_profile_overrides,
        dsl.get("feature_states", {}),
        patch_groups=[],
    )
    if _dsl_version(dsl) == "0.4"
    else None
)
```

Add to `manifest`:

```python
"campaign_signature": campaign_signature,
```

- [ ] **Step 5: Run design-space tests**

Run:

```powershell
python -m pytest tests/test_impeller_design_space.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit design-space model**

```powershell
git add src/part_rule_synthesis/impeller_design_space.py tests/test_impeller_design_space.py src/part_rule_synthesis/service.py
git commit -m "feat: add impeller campaign signature model"
```

---

### Task 4: Support Variable Meridional NURBS Control Counts

**Files:**

- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Create: `tests/test_impeller_profile_topology.py`

- [ ] **Step 1: Write failing profile topology tests**

Create `tests/test_impeller_profile_topology.py`:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)


PARAMS = {
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
    "root_fillet_radius_mm": 3.0,
    "hub_wall_thickness_mm": 18.0,
    "hub_bottom_thickness_mm": 24.0,
    "hub_top_cap_thickness_mm": 8.0,
    "hub_chamfer_radius_mm": 3.0,
    "hood_wall_thickness_mm": 12.0,
    "hood_chamfer_radius_mm": 3.0,
}

FACETS = {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel",
    "blade_exit_geometry": "backward_curved",
}


def clamped_curve(points):
    degree = 3
    interior_count = len(points) - degree - 1
    if interior_count <= 0:
        knots = [0, 0, 0, 0, 1, 1, 1, 1]
    else:
        interiors = [(index + 1) / (interior_count + 1) for index in range(interior_count)]
        knots = [0, 0, 0, 0, *interiors, 1, 1, 1, 1]
    return {
        "kind": "nurbs_curve",
        "degree": degree,
        "coordinate_system": "rz_meridional_mm",
        "control_points": points,
        "weights": [1.0] * len(points),
        "knots": knots,
    }


def test_kernel_accepts_six_point_hub_and_tip_profiles():
    profiles = {
        "hub_profile": clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    geometry = build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)

    hub_surface = next(surface for surface in geometry["surface_graph"]["surfaces"] if surface["id"] == "hub_revolve_surface")
    assert hub_surface["profile"]["control_points"] == profiles["hub_profile"]["control_points"]
    assert geometry["validity"]["status"] == "PASS"


def test_kernel_rejects_invalid_knot_count_for_variable_profile():
    profiles = {
        "hub_profile": {
            **clamped_curve([[120, 160], [170, 130], [240, 90], [340, 40], [470, 12], [570, 0]]),
            "knots": [0, 0, 0, 0, 1, 1, 1, 1],
        },
        "tip_or_shroud_profile": clamped_curve([[190, 320], [250, 292], [350, 230], [455, 150], [560, 96], [630, 78]]),
    }

    try:
        build_axisymmetric_throughflow_nurbs_geometry(PARAMS, FACETS, profile_overrides=profiles)
    except ValueError as exc:
        assert "knot count" in str(exc)
    else:
        raise AssertionError("expected invalid knot count to fail")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_profile_topology.py -q
```

Expected: FAIL because `_validated_profile_override` requires exactly four control points and `_profile_point` uses cubic Bezier basis.

- [ ] **Step 3: Replace fixed cubic profile evaluation**

In `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`, replace `_validated_profile_override`, `_nurbs_curve`, and `_profile_point` with variable-count B-spline/NURBS helpers.

Use these function signatures:

```python
def _validated_profile_override(
    name: str,
    override: dict[str, Any] | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    ...


def _nurbs_curve(curve_id: str, control_points: list[list[float]]) -> dict[str, Any]:
    ...


def _profile_point(profile: dict[str, Any], u: float) -> list[float]:
    ...


def _clamped_open_uniform_knots(point_count: int, degree: int) -> list[float]:
    ...


def _nurbs_basis(i: int, degree: int, u: float, knots: list[float]) -> float:
    ...
```

Use this implementation logic:

```python
def _clamped_open_uniform_knots(point_count: int, degree: int) -> list[float]:
    interior_count = point_count - degree - 1
    if point_count < degree + 1:
        raise ValueError("control point count must be at least degree + 1")
    interiors = [(index + 1) / (interior_count + 1) for index in range(interior_count)]
    return [0.0] * (degree + 1) + interiors + [1.0] * (degree + 1)
```

```python
def _nurbs_basis(i: int, degree: int, u: float, knots: list[float]) -> float:
    if degree == 0:
        if knots[i] <= u < knots[i + 1] or (u == 1.0 and knots[i] <= u <= knots[i + 1]):
            return 1.0
        return 0.0
    left_denominator = knots[i + degree] - knots[i]
    right_denominator = knots[i + degree + 1] - knots[i + 1]
    left = 0.0
    right = 0.0
    if left_denominator > 0:
        left = ((u - knots[i]) / left_denominator) * _nurbs_basis(i, degree - 1, u, knots)
    if right_denominator > 0:
        right = ((knots[i + degree + 1] - u) / right_denominator) * _nurbs_basis(i + 1, degree - 1, u, knots)
    return left + right
```

```python
def _profile_point(profile: dict[str, Any], u: float) -> list[float]:
    points = profile["control_points"]
    weights = profile["weights"]
    knots = profile["knots"]
    degree = int(profile["degree"])
    clamped_u = _clamp01(u)
    basis = [_nurbs_basis(index, degree, clamped_u, knots) for index in range(len(points))]
    denominator = sum(value * weights[index] for index, value in enumerate(basis))
    if denominator <= 0.0:
        raise ValueError("profile NURBS denominator must be positive")
    r = sum(basis[index] * weights[index] * points[index][0] for index in range(len(points))) / denominator
    z = sum(basis[index] * weights[index] * points[index][1] for index in range(len(points))) / denominator
    return [r, z]
```

Validate:

- `kind == "nurbs_curve"`
- `degree == 3`
- `len(control_points) >= 4`
- `len(weights) == len(control_points)`
- `len(knots) == len(control_points) + degree + 1`
- knots non-decreasing
- first and last `degree + 1` knots equal `0` and `1`
- control radii positive and finite

- [ ] **Step 4: Run profile topology tests**

Run:

```powershell
python -m pytest tests/test_impeller_profile_topology.py tests/test_impeller_kernel_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit variable profile topology**

```powershell
git add src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py tests/test_impeller_profile_topology.py
git commit -m "feat: support variable impeller profile control topology"
```

---

### Task 5: Build Surface/Feature Graph Contract Helpers

**Files:**

- Create: `src/part_rule_synthesis/impeller_graph_contract.py`
- Modify: `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`
- Create: `tests/test_impeller_cfd_manifest.py`

- [ ] **Step 1: Write failing graph contract tests**

Create `tests/test_impeller_cfd_manifest.py` with the graph portion first:

```python
from __future__ import annotations

from part_rule_synthesis.impeller_graph_contract import (
    estimate_surface_area,
    surface_feature_records,
    wetted_surfaces,
)


def test_estimate_surface_area_returns_positive_area_for_grid():
    surface = {
        "id": "quad",
        "role": "hub",
        "uv_grid": [
            [[0, 0, 0], [1, 0, 0]],
            [[0, 1, 0], [1, 1, 0]],
        ],
    }

    assert estimate_surface_area(surface) == 1.0


def test_wetted_surfaces_excludes_construction_and_internal_assembly():
    surfaces = [
        {"id": "hub", "role": "hub", "material_domain": "hub", "uv_grid": []},
        {"id": "tip_reference", "role": "construction_support_only", "uv_grid": []},
        {"id": "mounting_bore", "role": "mounting_bore", "material_domain": "hub", "feature_id": "mounting_bore", "uv_grid": []},
        {"id": "blade_pressure", "role": "blade_pressure", "uv_grid": []},
    ]

    ids = [surface["id"] for surface in wetted_surfaces(surfaces, suppressed_features={"mounting_bore"})]

    assert ids == ["hub", "blade_pressure"]


def test_surface_feature_records_map_feature_ids_to_generated_surfaces():
    surfaces = [
        {"id": "blade_00_root_transition", "feature_id": "blade_00.root_fillet", "role": "root_transition"},
        {"id": "blade_00_pressure_surface", "feature_id": "blade_00", "role": "blade_pressure"},
    ]

    records = surface_feature_records(surfaces)

    assert records["blade_00.root_fillet"]["generated_surfaces"] == ["blade_00_root_transition"]
    assert records["blade_00"]["generated_surfaces"] == ["blade_00_pressure_surface"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_cfd_manifest.py::test_estimate_surface_area_returns_positive_area_for_grid tests/test_impeller_cfd_manifest.py::test_wetted_surfaces_excludes_construction_and_internal_assembly tests/test_impeller_cfd_manifest.py::test_surface_feature_records_map_feature_ids_to_generated_surfaces -q
```

Expected: FAIL because `impeller_graph_contract.py` does not exist.

- [ ] **Step 3: Implement graph contract helpers**

Create `src/part_rule_synthesis/impeller_graph_contract.py`:

```python
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


CONSTRUCTION_ROLES = {"construction_support_only", "reference_only"}
INTERNAL_ASSEMBLY_ROLES = {"mounting_bore", "shaft_seat", "keyway", "rear_hub_groove"}


def estimate_surface_area(surface: dict[str, Any]) -> float:
    grid = surface.get("uv_grid") or []
    if len(grid) < 2 or len(grid[0]) < 2:
        return 0.0
    area = 0.0
    for u in range(len(grid) - 1):
        for v in range(len(grid[u]) - 1):
            area += _triangle_area(grid[u][v], grid[u + 1][v], grid[u][v + 1])
            area += _triangle_area(grid[u + 1][v], grid[u + 1][v + 1], grid[u][v + 1])
    return round(area, 6)


def wetted_surfaces(
    surfaces: list[dict[str, Any]],
    suppressed_features: set[str] | None = None,
) -> list[dict[str, Any]]:
    suppressed = suppressed_features or set()
    result = []
    for surface in surfaces:
        role = surface.get("role")
        feature_id = surface.get("feature_id")
        if role in CONSTRUCTION_ROLES:
            continue
        if role in INTERNAL_ASSEMBLY_ROLES:
            continue
        if feature_id in suppressed:
            continue
        result.append(surface)
    return result


def surface_feature_records(surfaces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = defaultdict(lambda: {"generated_surfaces": []})
    for surface in surfaces:
        feature_id = surface.get("feature_id")
        if not feature_id:
            continue
        records[feature_id]["generated_surfaces"].append(surface["id"])
    return dict(records)


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return 0.5 * math.sqrt(sum(value * value for value in cross))
```

- [ ] **Step 4: Add `feature_id` and `cfd_role` metadata to generated surfaces**

In `src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py`, update generated blade surfaces in `_surface_graph` where surfaces are appended.

Each blade surface should include:

```python
"feature_id": f"blade_{blade['index']:02d}",
"cfd_role": "blade_pressure",
```

Use these mappings:

```text
pressure_surface -> blade_pressure
suction_surface -> blade_suction
leading_edge_surface -> leading_edge_transition
trailing_edge_surface -> trailing_edge_transition
root_closure_surface -> root_transition
tip_closure_surface -> tip_transition
hub_revolve_surface -> hub_wall
shroud_surface/front_shroud_inner_surface -> tip_or_shroud_wall
```

For transition surfaces, use feature IDs:

```python
"feature_id": f"blade_{blade['index']:02d}.root_fillet"
```

for root transition, and equivalent `.leading_edge_round`, `.trailing_edge_round`, `.tip_transition`.

- [ ] **Step 5: Run graph helper tests**

Run:

```powershell
python -m pytest tests/test_impeller_cfd_manifest.py -q
```

Expected: PASS for the three graph helper tests.

- [ ] **Step 6: Commit graph contract helpers**

```powershell
git add src/part_rule_synthesis/impeller_graph_contract.py `
  src/part_rule_synthesis/impeller_kernels/axisymmetric_throughflow_nurbs.py `
  tests/test_impeller_cfd_manifest.py
git commit -m "feat: add impeller surface feature graph helpers"
```

---

### Task 6: Generate Full-360 CFD Manifest

**Files:**

- Create: `src/part_rule_synthesis/impeller_cfd_manifest.py`
- Modify: `src/part_rule_synthesis/service.py`
- Modify: `tests/test_impeller_cfd_manifest.py`
- Modify: `tests/test_acceptance.py`

- [ ] **Step 1: Add failing CFD manifest tests**

Append to `tests/test_impeller_cfd_manifest.py`:

```python
from part_rule_synthesis.impeller_cfd_manifest import build_cfd_full_360_manifest


def test_cfd_manifest_groups_blade_instances_by_group_and_instance():
    surface_graph = {
        "surfaces": [
            {"id": "hub_revolve_surface", "role": "hub", "cfd_role": "hub_wall", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]},
            {"id": "blade_00_pressure_surface", "role": "blade_pressure", "cfd_role": "blade_pressure", "feature_id": "blade_00", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]},
            {"id": "blade_01_pressure_surface", "role": "blade_pressure", "cfd_role": "blade_pressure", "feature_id": "blade_01", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]},
            {"id": "mounting_bore_cylinder", "role": "mounting_bore", "feature_id": "mounting_bore", "uv_grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0], [1, 1, 0]]]},
        ]
    }
    view = {
        "feature_suppression": {"suppressed_features": ["mounting_bore"]},
        "required_patch_groups": ["hub_wall", "blade_pressure_wall"],
    }

    manifest = build_cfd_full_360_manifest(surface_graph, view, blade_count=2)

    assert manifest["domain_kind"] == "full_360_wetted_surface"
    assert manifest["patch_groups"]["blade_pressure_wall"]["instances"] == [
        "blade_00_pressure_surface",
        "blade_01_pressure_surface",
    ]
    assert "mounting_bore_cylinder" not in manifest["patch_instances"]
    assert manifest["validity"]["status"] == "PASS"


def test_cfd_manifest_fails_when_required_patch_group_is_empty():
    surface_graph = {"surfaces": []}
    view = {
        "feature_suppression": {"suppressed_features": []},
        "required_patch_groups": ["hub_wall"],
    }

    manifest = build_cfd_full_360_manifest(surface_graph, view, blade_count=0)

    assert manifest["validity"]["status"] == "FAIL"
    assert "missing_patch_group_instances:hub_wall" in manifest["validity"]["failures"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_impeller_cfd_manifest.py -q
```

Expected: FAIL because `impeller_cfd_manifest.py` does not exist.

- [ ] **Step 3: Implement CFD manifest builder**

Create `src/part_rule_synthesis/impeller_cfd_manifest.py`:

```python
from __future__ import annotations

from typing import Any

from part_rule_synthesis.impeller_graph_contract import estimate_surface_area, wetted_surfaces


CFD_ROLE_TO_GROUP = {
    "blade_pressure": "blade_pressure_wall",
    "blade_suction": "blade_suction_wall",
    "leading_edge_transition": "leading_edge_wall",
    "trailing_edge_transition": "trailing_edge_wall",
    "root_transition": "root_fillet_wall",
    "tip_transition": "tip_fillet_wall",
    "hub_wall": "hub_wall",
    "tip_or_shroud_wall": "tip_or_shroud_wall",
    "inlet_patch": "inlet_patch",
    "outlet_patch": "outlet_patch",
}


def build_cfd_full_360_manifest(
    surface_graph: dict[str, Any],
    simulation_view: dict[str, Any],
    blade_count: int,
) -> dict[str, Any]:
    suppressed = set(simulation_view.get("feature_suppression", {}).get("suppressed_features", []))
    surfaces = wetted_surfaces(surface_graph.get("surfaces", []), suppressed_features=suppressed)
    patch_groups: dict[str, dict[str, Any]] = {
        group: {"type": "wall" if group not in {"inlet_patch", "outlet_patch"} else group.replace("_patch", ""), "instances": []}
        for group in simulation_view.get("required_patch_groups", [])
    }
    patch_instances: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        group = CFD_ROLE_TO_GROUP.get(surface.get("cfd_role"))
        if not group:
            continue
        patch_groups.setdefault(group, {"type": "wall", "instances": []})
        patch_groups[group]["instances"].append(surface["id"])
        patch_instances[surface["id"]] = {
            "group": group,
            "source_feature": surface.get("feature_id"),
            "surface_graph_id": surface["id"],
            "surface_role": surface.get("role"),
            "area_estimate_mm2": estimate_surface_area(surface),
        }
    for group in patch_groups.values():
        group["instances"].sort()
    failures = [
        f"missing_patch_group_instances:{group_id}"
        for group_id, group in patch_groups.items()
        if not group["instances"]
    ]
    return {
        "domain_kind": "full_360_wetted_surface",
        "status": "research_grade_executable",
        "blade_count": int(blade_count),
        "feature_suppression": simulation_view.get("feature_suppression", {}),
        "patch_groups": patch_groups,
        "patch_instances": patch_instances,
        "mesh_hints": simulation_view.get("mesh_hints", {}),
        "validity": {
            "status": "FAIL" if failures else "PASS",
            "failures": failures,
            "patch_group_count": len(patch_groups),
            "patch_instance_count": len(patch_instances),
        },
    }
```

- [ ] **Step 4: Wire CFD manifest into service manifest**

In `src/part_rule_synthesis/service.py`, import:

```python
from part_rule_synthesis.impeller_cfd_manifest import build_cfd_full_360_manifest
```

After `geometry_validity` and before assembling `manifest`, compute:

```python
simulation_manifests = {}
if dsl["part_family"] == "impeller" and _dsl_version(dsl) == "0.4":
    geometry_metadata = _geometry_metadata(
        dsl["part_family"],
        bound,
        dsl.get("facets", {}),
        profile_overrides=normalized_profile_overrides,
        curve_overrides=normalized_curve_overrides,
        geometry_stage=normalized_geometry_stage,
        dsl_context=dsl,
    )
    surface_graph = geometry_metadata.get("surface_graph", {})
    cfd_view = dsl.get("simulation_views", {}).get("cfd_full_360", {})
    simulation_manifests["cfd_full_360"] = build_cfd_full_360_manifest(
        surface_graph,
        cfd_view,
        blade_count=int(bound.get("blade_count", 0)),
    )
```

Add to manifest:

```python
"simulation_manifests": simulation_manifests,
```

If this duplicates `_geometry_metadata(...)`, refactor within the same task so `geometry_metadata` is computed once and reused in the manifest.

- [ ] **Step 5: Add API acceptance test**

Append to `tests/test_acceptance.py`:

```python
def test_impeller_v04_manifest_includes_cfd_full_360_patch_groups(tmp_path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
    parameters = {name: spec["default"] for name, spec in service.engines[engine.engine_id]["parameters"].items()}

    run = service.instantiate(engine.engine_id, parameters)
    cfd = run.manifest["simulation_manifests"]["cfd_full_360"]

    assert cfd["domain_kind"] == "full_360_wetted_surface"
    assert "blade_pressure_wall" in cfd["patch_groups"]
    assert "blade_suction_wall" in cfd["patch_groups"]
    assert cfd["feature_suppression"]["suppressed_features"]
    assert cfd["validity"]["status"] in {"PASS", "FAIL"}
```

- [ ] **Step 6: Run CFD manifest tests**

Run:

```powershell
python -m pytest tests/test_impeller_cfd_manifest.py tests/test_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit CFD manifest**

```powershell
git add src/part_rule_synthesis/impeller_cfd_manifest.py src/part_rule_synthesis/service.py tests/test_impeller_cfd_manifest.py tests/test_acceptance.py
git commit -m "feat: emit impeller cfd full 360 manifest"
```

---

### Task 7: Add Frontend Simulation View Models And CFD Panel

**Files:**

- Create: `frontend/src/simulationViewModel.js`
- Create: `frontend/src/simulationViewModel.test.js`
- Create: `frontend/src/components/CfdManifestPanel.js`
- Modify: `frontend/src/workspaceModel.js`
- Modify: `frontend/src/components/ModelViewer.js`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appFiles.test.js`

- [ ] **Step 1: Write failing frontend model tests**

Create `frontend/src/simulationViewModel.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  cfdPatchGroups,
  cfdPatchInstances,
  surfaceVisibleInView,
  viewModeOptions,
} from "./simulationViewModel.js";

describe("simulation view model", () => {
  test("viewModeOptions includes CAD, CFD, and feature debug views", () => {
    assert.deepEqual(viewModeOptions().map((option) => option.id), [
      "cad_review_360",
      "cfd_full_360",
      "feature_debug",
    ]);
  });

  test("surfaceVisibleInView hides construction and suppressed assembly in cfd view", () => {
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ role: "mounting_bore" }, "cfd_full_360"), false);
    assert.equal(surfaceVisibleInView({ cfd_role: "blade_pressure" }, "cfd_full_360"), true);
    assert.equal(surfaceVisibleInView({ role: "construction_support_only" }, "cad_review_360"), true);
  });

  test("cfdPatchGroups and cfdPatchInstances return sorted arrays", () => {
    const manifest = {
      simulation_manifests: {
        cfd_full_360: {
          patch_groups: {
            hub_wall: { instances: ["hub"] },
            blade_pressure_wall: { instances: ["blade_00_pressure_surface"] },
          },
          patch_instances: {
            hub: { group: "hub_wall" },
            blade_00_pressure_surface: { group: "blade_pressure_wall" },
          },
        },
      },
    };

    assert.deepEqual(cfdPatchGroups(manifest).map((group) => group.id), ["blade_pressure_wall", "hub_wall"]);
    assert.deepEqual(cfdPatchInstances(manifest).map((instance) => instance.id), ["blade_00_pressure_surface", "hub"]);
  });
});
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```powershell
cd frontend
npm.cmd test -- simulationViewModel.test.js
```

Expected: FAIL because `simulationViewModel.js` does not exist.

- [ ] **Step 3: Implement simulation view model**

Create `frontend/src/simulationViewModel.js`:

```javascript
const CFD_HIDDEN_ROLES = new Set([
  "construction_support_only",
  "reference_only",
  "mounting_bore",
  "shaft_seat",
  "keyway",
  "rear_hub_groove",
]);

export function viewModeOptions() {
  return [
    { id: "cad_review_360", label: "CAD review" },
    { id: "cfd_full_360", label: "CFD full 360" },
    { id: "feature_debug", label: "Feature debug" },
  ];
}

export function surfaceVisibleInView(surface, viewMode) {
  if (viewMode !== "cfd_full_360") {
    return true;
  }
  if (CFD_HIDDEN_ROLES.has(surface?.role)) {
    return false;
  }
  return Boolean(surface?.cfd_role || surface?.role?.includes("blade") || surface?.role === "hub");
}

export function cfdPatchGroups(manifest) {
  const groups = manifest?.simulation_manifests?.cfd_full_360?.patch_groups || {};
  return Object.entries(groups)
    .map(([id, value]) => ({ id, ...value }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function cfdPatchInstances(manifest) {
  const instances = manifest?.simulation_manifests?.cfd_full_360?.patch_instances || {};
  return Object.entries(instances)
    .map(([id, value]) => ({ id, ...value }))
    .sort((a, b) => a.id.localeCompare(b.id));
}
```

- [ ] **Step 4: Add CFD manifest panel component**

Create `frontend/src/components/CfdManifestPanel.js`:

```javascript
import { h } from "preact";

import { cfdPatchGroups, cfdPatchInstances } from "../simulationViewModel.js";

export function CfdManifestPanel({ manifest, selectedPatch, onSelectPatch }) {
  const groups = cfdPatchGroups(manifest);
  const instances = cfdPatchInstances(manifest);
  const cfd = manifest?.simulation_manifests?.cfd_full_360;
  return h(
    "section",
    { className: "panel-section cfd-manifest-panel" },
    h("div", { className: "section-title" }, "CFD full 360 manifest"),
    h("div", { className: "status-pill" }, cfd?.validity?.status || "NO CFD MANIFEST"),
    h(
      "div",
      { className: "patch-list" },
      groups.map((group) =>
        h(
          "button",
          {
            className: selectedPatch === group.id ? "patch-row selected" : "patch-row",
            type: "button",
            onClick: () => onSelectPatch(group.id),
            key: group.id,
          },
          h("span", null, group.id),
          h("strong", null, String(group.instances?.length || 0)),
        ),
      ),
    ),
    h("div", { className: "subtle-label" }, `instances ${instances.length}`),
  );
}
```

- [ ] **Step 5: Wire view modes into App and ModelViewer**

In `frontend/src/App.js`, import:

```javascript
import { CfdManifestPanel } from "./components/CfdManifestPanel.js";
import { viewModeOptions } from "./simulationViewModel.js";
```

Add state:

```javascript
const [viewMode, setViewMode] = useState("cad_review_360");
const [selectedPatch, setSelectedPatch] = useState(null);
```

Pass to `ModelViewer`:

```javascript
viewMode,
selectedPatch,
```

Render controls:

```javascript
h(
  "div",
  { className: "view-mode-tabs" },
  viewModeOptions().map((option) =>
    h(
      "button",
      {
        type: "button",
        className: viewMode === option.id ? "selected" : "",
        onClick: () => setViewMode(option.id),
        key: option.id,
      },
      option.label,
    ),
  ),
)
```

Render panel:

```javascript
h(CfdManifestPanel, {
  manifest,
  selectedPatch,
  onSelectPatch: setSelectedPatch,
})
```

In `frontend/src/components/ModelViewer.js`, import:

```javascript
import { surfaceVisibleInView } from "../simulationViewModel.js";
```

Filter surfaces before rendering:

```javascript
const visibleSurfaces = (surfaceGraph?.surfaces || []).filter((surface) => surfaceVisibleInView(surface, viewMode));
```

When `selectedPatch` is set, highlight surfaces where:

```javascript
surface.cfd_patch_group === selectedPatch || surface.id === selectedPatch
```

- [ ] **Step 6: Add CSS**

Append to `frontend/src/styles.css`:

```css
.view-mode-tabs {
  display: flex;
  gap: 6px;
  padding-top: 8px;
}

.view-mode-tabs button,
.patch-row {
  border: 1px solid #cbd4cf;
  background: #ffffff;
  color: #17211d;
  padding: 7px 8px;
  cursor: pointer;
}

.view-mode-tabs button.selected,
.patch-row.selected {
  border-color: #b86721;
  background: #fff7ed;
}

.cfd-manifest-panel .patch-list {
  display: grid;
  gap: 6px;
}

.patch-row {
  display: flex;
  justify-content: space-between;
  text-align: left;
}

.status-pill {
  display: inline-block;
  border: 1px solid #1f7a5a;
  color: #1f7a5a;
  padding: 4px 7px;
  margin-bottom: 8px;
  font-size: 12px;
}
```

- [ ] **Step 7: Add app file presence test**

Append to `frontend/src/appFiles.test.js`:

```javascript
test("application includes CFD manifest panel and simulation view model", () => {
  const appSource = readFileSync(resolve(root, "src/App.js"), "utf-8");
  const modelSource = readFileSync(resolve(root, "src/simulationViewModel.js"), "utf-8");

  assert.match(appSource, /CfdManifestPanel/);
  assert.match(modelSource, /cfdPatchGroups/);
  assert.match(modelSource, /surfaceVisibleInView/);
});
```

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 9: Commit frontend simulation view**

```powershell
git add frontend/src/simulationViewModel.js frontend/src/simulationViewModel.test.js `
  frontend/src/components/CfdManifestPanel.js frontend/src/App.js `
  frontend/src/components/ModelViewer.js frontend/src/workspaceModel.js `
  frontend/src/styles.css frontend/src/appFiles.test.js
git commit -m "feat: add impeller cfd manifest frontend view"
```

---

### Task 8: End-To-End v0.4 Acceptance And Documentation

**Files:**

- Modify: `docs/axisymmetric-throughflow-nurbs-kernel.md`
- Modify: `tests/test_acceptance.py`
- Modify: `frontend/src/workspaceModel.test.js`
- Modify: `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/CHANGELOG.md`

- [ ] **Step 1: Add end-to-end acceptance test**

Append to `tests/test_acceptance.py`:

```python
def test_impeller_v04_full_360_cfd_view_is_stable_under_numeric_parameter_change(tmp_path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
    dsl = service.engines[engine.engine_id]
    parameters = {name: spec["default"] for name, spec in dsl["parameters"].items()}

    baseline = service.instantiate(engine.engine_id, parameters)
    changed = service.instantiate(
        engine.engine_id,
        {**parameters, "blade_wrap_deg": parameters["blade_wrap_deg"] + 5.0},
    )

    baseline_groups = sorted(baseline.manifest["simulation_manifests"]["cfd_full_360"]["patch_groups"])
    changed_groups = sorted(changed.manifest["simulation_manifests"]["cfd_full_360"]["patch_groups"])

    assert baseline_groups == changed_groups
    assert baseline.manifest["campaign_signature"]["design_vector_length"] == changed.manifest["campaign_signature"]["design_vector_length"]
```

- [ ] **Step 2: Run acceptance test to verify failure or pass**

Run:

```powershell
python -m pytest tests/test_acceptance.py::test_impeller_v04_full_360_cfd_view_is_stable_under_numeric_parameter_change -q
```

Expected before previous tasks are complete: FAIL. Expected after Tasks 1-7: PASS.

- [ ] **Step 3: Update kernel documentation**

Append to `docs/axisymmetric-throughflow-nurbs-kernel.md`:

```markdown
## v0.4 Surface/Feature Graph Contract

v0.4 keeps the current research-grade sampled geometry but adds a graph contract around it.
The generated geometry now has three identities:

1. CAD review surface graph for human inspection.
2. Feature graph for source edges, transition features, assembly features, and generated surfaces.
3. CFD full-360 manifest for wetted patches, patch groups, patch instances, suppression rules, and mesh hints.

The first v0.4 CFD target is full 360-degree wetted geometry. Periodic single-passage CFD is a later view.

The first v0.4 fillets and blends are sampled blend surfaces. They must be labeled with:

```json
{
  "cad_exactness": "research_grade_sampled_surface",
  "intended_cad_operation": "fillet_or_blend"
}
```

This label prevents the research geometry from being mistaken for exact industrial B-Rep output.
```

- [ ] **Step 4: Update v0.4 changelog**

Write `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/CHANGELOG.md`:

```markdown
# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.4 Changelog

Date: 2026-07-01

Supersedes: `v0_3`

## Motivation

v0.4 introduces an optimization-ready surface/feature graph contract so the same DSL can support CAD review, full-360 CFD manifest generation, future FEA solid views, and structured loss traceability.

## Changes

1. Added `design_space` with topology variables, design variables, and campaign freeze rule.
2. Added boundary-guided blade surface model.
3. Added feature graph semantics for blade transitions, assembly features, and schema-only tuning features.
4. Added `simulation_views` for `cad_review_360`, executable `cfd_full_360`, and schema-only `fea_solid`.
5. Added group + instance CFD patch naming.
6. Added feature suppression rules for internal assembly features in CFD view.

## Implementation Status

The first implementation emits research-grade sampled surfaces and CFD manifests. It does not provide exact industrial B-Rep fillets, periodic sector CFD domains, solver adapters, or mesh adapters.
```

- [ ] **Step 5: Run full backend and frontend verification**

Run:

```powershell
python -m pytest tests -q
python -m compileall -q src
cd frontend
npm.cmd test
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 6: Commit acceptance and docs**

```powershell
git add docs/axisymmetric-throughflow-nurbs-kernel.md tests/test_acceptance.py `
  src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4/CHANGELOG.md
git commit -m "test: cover impeller v0.4 cfd view acceptance"
```

---

## Final Verification

After all tasks are complete, run:

```powershell
python -m pytest tests -q
python -m compileall -q src
cd frontend
npm.cmd test
npm.cmd run build
```

Expected final result:

- Backend tests pass.
- Frontend tests pass.
- Frontend build succeeds.
- v0.2 and v0.3 presets still compile.
- v0.4 presets compile.
- v0.4 manifest includes `simulation_manifests.cfd_full_360`.
- CFD patch groups include group + instance names.
- Assembly internals are suppressed from CFD view.
- Campaign signature is present and stable under numeric-only changes.

## Plan Self-Review

Spec coverage:

- DSL v0.4 structure: Tasks 1 and 2.
- Design-space and campaign freeze: Task 3.
- Variable NURBS control topology: Task 4.
- Feature graph and sampled transition surfaces: Task 5.
- CFD manifest and patch naming: Task 6.
- Frontend design-space/CFD inspection path: Task 7.
- Acceptance and documentation: Task 8.

Known implementation boundary:

- Task 5 labels research-grade transition surfaces and graph metadata, but does not implement exact CAD fillets.
- Task 6 emits adapter-neutral mesh hints and patch manifests, but does not invoke a mesher.
- Task 7 adds CFD view inspection and filtering, but does not build a full CAD/CAE campaign manager.
