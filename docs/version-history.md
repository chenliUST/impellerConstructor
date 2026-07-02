# Version History

This repository keeps previous impeller DSL versions in source control and in versioned resource folders. The goal is to preserve the research trail: observed loss, revised semantics, new DSL contracts, and implementation behavior should remain auditable.

Current latest baseline: `v0_7`. V0.6 remains the support-face B-Rep and mesh-inspection line; V0.7 is the bounded B-Rep transition-policy, OBJ mesh artifact, mesh overlay, and OCCT reimport bounding-box line.

## Git Milestones

| Milestone | Commit | Description |
| --- | --- | --- |
| Baseline | `bdb60d2` | Initial part-rule-synthesis project baseline. |
| v0.2 slice | `2d3957b` | First focused axisymmetric throughflow impeller DSL/runtime/frontend metadata path. |
| v0.3 runtime | `7afb0d2` | Solid hub/hood, profile/curve overrides, staged geometry, and frontend workflow. |
| v0.4 graph contract | `f74eb06` | Design-space campaign signatures, variable profile topology, surface/feature graph, CFD full-360 manifest, and frontend CFD view. |
| v0.5 export contract | local implementation | Surface-graph-faithful STL/STEP export contract with region provenance. |
| v0.6 B-Rep evidence line | local implementation | Graph-derived unsewn NURBS/analytic B-Rep support-face STEP export, CFD surface mesh inspection manifest, Model Output artifacts, and explicit fillet/blend controls. |
| v0.7 bounded transition line | current branch | Bounded B-Rep face export, edge-family transition policies, OBJ mesh artifacts, mesh overlay inspection, and OCCT reimport bounding-box gate. |

Version tags:

```text
impeller-dsl-v0.2 -> 2d3957b
impeller-dsl-v0.3 -> 7afb0d2
impeller-dsl-v0.4 -> f74eb06
```

The rollback tags currently cover v0.2 through v0.4. V0.5, V0.6, and V0.7 are preserved as versioned resource folders and implementation evidence in the current repository line.

## v0.2

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2
src/part_rule_synthesis/ontology/impeller/v0_2
```

Primary preset ids:

```text
radial_open_reference
radial_closed_reference
```

Purpose:

- Establish a narrow `AxisymmetricThroughflowRadialBladedImpeller` slice.
- Move from ad hoc impeller parameters into JSON DSL and ontology resources.
- Expose constructor metadata and validity contracts in run manifests.
- Keep the legacy `radial_open_reference` alias usable.

## v0.3

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3
src/part_rule_synthesis/ontology/impeller/v0_3
```

Primary preset ids:

```text
radial_open_reference_v0_3
radial_closed_reference_v0_3
```

Purpose:

- Add finite hub solid and finite hood shell semantics.
- Add hub/hood thickness and chamfer parameters.
- Add profile curve overrides and blade curve overrides.
- Add staged generation for hub, blades, and edge closures.
- Add frontend editors for meridional profiles and blade intrinsic curves.
- Produce v0.3 video sweep evidence.

## v0.4

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4
src/part_rule_synthesis/ontology/impeller/v0_4
```

Primary preset ids:

```text
radial_open_reference_v0_4
radial_closed_reference_v0_4
```

Purpose:

- Add optimization-ready design space and campaign signatures.
- Freeze topology separately from numeric design values.
- Support variable NURBS profile control topology.
- Add surface/feature graph contracts around generated sampled geometry.
- Add CFD full-360 manifest with patch groups and patch instances.
- Add frontend CAD review, CFD full-360, and feature-debug simulation views.

Known boundary:

- v0.4 emits research-grade sampled geometry.
- Sampled blend/fillet surfaces are labeled, not exact industrial B-Rep fillets.
- CFD manifest generation does not yet invoke a mesher or solver.
- Periodic single-passage CFD, FEA solid adapters, and CAM/DFMA feedback loops are future layers.

## v0.5

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5
```

Primary preset ids:

```text
radial_open_reference_v0_5
radial_closed_reference_v0_5
```

Purpose:

- Preserve the v0.4 surface/feature graph and CFD full-360 semantics.
- Add `export_contracts/surface_graph_faithful.json`.
- Route v0.5 STL/STEP exports through `manifest.geometry.surface_graph`.
- Add `export_manifests` with exactness labels and region provenance.
- Make exported triangles/faces traceable to `surface_graph_id`, feature, and role.

Known boundary:

- STL is a sampled mesh projection of `surface_graph`.
- STEP is a graph-derived faceted surface shell labeled `surface_graph_mesh_step`.
- v0.5 does not claim exact analytic B-Rep surfaces, OCCT sewing/healing, or solver-ready meshes.

## v0.6

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6
```

Primary preset ids:

```text
radial_open_reference_v0_6
radial_closed_reference_v0_6
```

Purpose:

- Preserve the v0.5 surface-graph source of truth.
- Add graph-derived unsewn NURBS/analytic B-Rep support-face STEP export.
- Add CFD surface mesh inspection manifests and Model Output artifact copies.
- Add explicit fillet/blend controls while keeping export exactness labels honest.

Known boundary:

- STEP exactness is `surface_graph_support_face_brep_step`.
- `surface_graph_trimmed_nurbs_step` remains a target label, not the current implementation.
- Trim loops and `cad_edge` wires are not consumed into true trimmed faces.
- V0.6 does not claim watertight sewing, manufacturing CAD certification, universal CAD healing, or solver-ready CFD volume meshes.

## v0.7

Location:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7
```

Primary preset ids:

```text
radial_open_reference_v0_7
radial_closed_reference_v0_7
```

Purpose:

- Advance from V0.6 support-face evidence to bounded B-Rep face export for supported surface families.
- Add edge-family transition policies and carry transition provenance through generated geometry, OBJ exports, and CFD surface mesh manifests.
- Add OBJ mesh artifacts for mesh review and frontend mesh overlay inspection.
- Add an OCCT reimport bounding-box gate for finite bounded STEP faces.

Known boundary:

- Bounded faces are unsewn and partially scoped to supported annular face families.
- OBJ and STL remain sampled mesh review artifacts, not manufacturing CAD.
- V0.7 does not claim sewn-solid certification, solver-ready CFD volume meshes, production meshing adapters, or manufacturing validation.

## How To Run A Specific Version

In Python tests or scripts:

```python
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("runs"))
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_7")
run = service.instantiate(engine.engine_id, {})
manifest = run.manifest
```

Change `preset_id` to one of the version-specific ids above to select earlier versions.

## Compatibility Rule

Do not mutate old version folders to express new semantics. If a natural-language loss record changes the meaning of a feature, create a new DSL version or an explicit patch file so earlier research evidence remains reproducible.
