# Axisymmetric Throughflow Radial Bladed Impeller DSL Version Index

This folder contains versioned JSON DSL resources for one ontology slice:

```text
AxisymmetricThroughflowRadialBladedImpeller
```

The versions are not replacements for one another. They are research checkpoints.

## Version Table

| Version | Preset ids | Main additions |
| --- | --- | --- |
| `v0_2` | `radial_open_reference`, `radial_closed_reference` | Initial focused DSL slice, open/closed constructors, shape-control schema, validity contracts. |
| `v0_3` | `radial_open_reference_v0_3`, `radial_closed_reference_v0_3` | Solid hub/hood thickness, chamfers, curve overrides, staged geometry workflow. |
| `v0_4` | `radial_open_reference_v0_4`, `radial_closed_reference_v0_4` | Design-space campaign signature, variable NURBS topology, surface/feature graph, CFD full-360 manifest. |
| `v0_5` | `radial_open_reference_v0_5`, `radial_closed_reference_v0_5` | Surface-graph-faithful export contract, STL/STEP region provenance, AP242 tessellated STEP, 12-blade default baseline, and honest STEP fidelity labels. |
| `v0_6` | `radial_open_reference_v0_6`, `radial_closed_reference_v0_6` | NURBS/analytic B-Rep support-face STEP export, mesh inspection manifest, Model Output artifacts, and explicit fillet/blend controls. |
| `v0_7` | `radial_open_reference_v0_7`, `radial_closed_reference_v0_7` | Bounded B-Rep export contract, edge-family transition defaults, and runtime transition policy metadata. |
| `v0_8` | `radial_open_reference_v0_8`, `radial_closed_reference_v0_8` | Transition-resolved fillet/chamfer surface patches, trimming metadata, transition-aware mesh, routed STL/OBJ/STEP manifests, and frontend inspection controls. |
| `v0_9` | `radial_open_reference_v0_9`, `radial_closed_reference_v0_9` | Kernel validity and reviewability line with capability matrix, golden cases, validation reports, double-sided root transitions, trim-aware mesh/STEP gates, and batch regression summaries. |
| `v0_91` | `radial_open_reference_v0_91`, `radial_closed_reference_v0_91` | Topology-first transition scaffold with V0.9 resources retagged for shared-node transition patch mesh contracts. |
| `v1_0` | `radial_open_reference_v1_0`, `radial_closed_reference_v1_0` | Topology-first constructor line with native blade edge, tip, root, hub, bore, and bevel faces plus shared-edge topology contracts. |
| `v1_1` | `radial_open_reference_v1_1`, `radial_closed_reference_v1_1` | Blade-to-blade 5-loop surface-family constructor with main/splitter blades, C2/G2 loop controls, six-face blade topology, and shared-boundary UV mesh/export contracts. |

## Folder Contract

Each version folder should keep the same broad resource shape:

```text
aliases.json
schema.json
constructors/
presets/
shape_controls/
```

Additional subfolders may be added when a version needs them. v0.4 adds:

```text
simulation_views/
```

The v0.5, v0.6, and v0.7 export contracts add:

```text
export_contracts/
```

## Runtime Loading

Runtime loading and compilation are handled by:

```text
src/part_rule_synthesis/impeller_dsl_resources.py
src/part_rule_synthesis/impeller_runtime_compiler.py
```

Service-level synthesis selects a preset id and receives a compiled runtime DSL dictionary:

```python
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_7")
```

Legacy v0.4 studies remain loadable:

```python
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
```

v0.5 is implemented by the `v0_5/` folder, runtime compiler support, graph-derived mesh export writer, and lineage tests. v0.6 is implemented by the `v0_6/` folder, runtime compiler support, graph-derived unsewn NURBS/analytic B-Rep support-face STEP export, mesh inspection manifests, Model Output artifacts, explicit fillet/blend controls, and lineage tests. v0.7 is implemented by the `v0_7/` folder, runtime compiler support, bounded B-Rep export contract resources, edge-family transition defaults, and lineage tests. v0.8 is implemented by the `v0_8/` folder, runtime compiler support, transition-resolved B-Rep contract resources, transition resolver routing, transition-aware mesh/export paths, frontend inspection controls, and lineage/workflow tests. v0.9 is implemented by the `v0_9/` folder, runtime compiler support, geometry validation reports, double-sided root transition resolver semantics, trim-aware mesh/STEP export gates, and batch regression tooling. v0.91 is implemented by the `v0_91/` folder and runtime compiler routing as a topology-first resource scaffold. v1.0 is implemented by the `v1_0/` folder and runtime compiler routing as the topology-first native face constructor line. v1.1 is implemented by the `v1_1/` folder, runtime compiler routing, the V1.1 blade-to-blade loop family and surface-graph builders, V1.1 validation/export contracts, and frontend profile/loop editors using the same control-point payload contract.

## Historical Git Tags

The repository keeps local and remote tags for research rollback:

```text
impeller-dsl-v0.2
impeller-dsl-v0.3
impeller-dsl-v0.4
```

Use this command from the repository root to verify both the current versioned resource folders and the tagged historical checkouts:

```powershell
.\scripts\verify_version_lineage.ps1
```

The script creates temporary detached git worktrees under `.worktrees/version-lineage/`, loads each tag, synthesizes both presets for that DSL version, instantiates them, checks manifest DSL version, and removes the temporary worktrees.

## Compatibility Rule

Keep old version folders reproducible. When new engineer feedback changes the meaning of a feature, add a new version or explicit patch resource instead of silently changing old semantics.

V0.2-V0.6 remain historical baselines and must stay loadable with their original semantics.

## v0.5 Evidence

The v0.5 export direction and implementation are documented so the ontology evolution has a traceable reason:

```text
docs/evidence/2026-07-01-impeller-v0-5-surface-graph-faithful-export/README.md
docs/superpowers/specs/2026-07-01-impeller-v0-5-surface-graph-faithful-export-design.md
docs/superpowers/plans/2026-07-01-impeller-v0-5-surface-graph-faithful-export.md
```

## v0.6 Evidence

The v0.6 export direction and implementation are documented so the B-Rep evidence
boundary stays explicit:

```text
docs/evidence/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export/README.md
docs/superpowers/specs/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export-design.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6/CHANGELOG.md
```

V0.6 generated STEP files are graph-derived unsewn NURBS/analytic B-Rep support faces
for the reference presets. Current STEP `export_exactness` is
`surface_graph_support_face_brep_step`; `surface_graph_trimmed_nurbs_step` is retained
only as the target exactness. The current writer does not yet consume `trim_loops` or
`cad_edge` wires for true trimmed-face export. The files are research B-Rep evidence,
not certified manufacturing geometry, not solver-ready CFD volume meshes, and not
universal CAD healing across all parameters.

## v0.7 Evidence

The v0.7 resource line introduces bounded B-Rep contract metadata and transition edge
families while preserving the v0.6 baseline geometry parameters:

```text
docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md
docs/superpowers/specs/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh-design.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7/CHANGELOG.md
```

## v0.8 Evidence

The v0.8 line is the first transition-resolved impeller geometry checkpoint. It routes
the base `surface_graph` through a resolver that creates supported fillet/chamfer
transition patches, records adjacent trimming metadata, feeds the transition-aware mesh,
and sends the same resolved graph into STL/OBJ/STEP manifests and frontend inspection.
The evidence also records the remaining boundary: bounded unsewn B-Rep shell, sampled
transition geometry, and no solver-ready volume mesh.

```text
docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/README.md
docs/superpowers/specs/2026-07-03-impeller-v0-8-transition-resolved-geometry-design.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_8/CHANGELOG.md
```

## v0.9 Evidence

The v0.9 line is a kernel validity and reviewability milestone. It adds a capability
matrix, golden case registry, validation reports, double-sided blade-root transition
surfaces, trim-aware mesh/STEP review exports, and batch regression summaries. It
does not claim watertight sewn B-Rep solids or solver-ready CFD.

```text
docs/evidence/2026-07-04-impeller-v0-9-kernel-validity-reviewability/README.md
docs/superpowers/specs/2026-07-04-impeller-v0-9-kernel-validity-reviewability-design.md
docs/superpowers/plans/2026-07-04-impeller-v0-9-kernel-validity-reviewability.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_9/CHANGELOG.md
```

## v0.91 Design Note

The v0.91 line is a completion patch scaffold for V0.9 transition validity. It retags
the V0.9 resources to topology-first transition contract ids and routes runtime
metadata to `topology_first_validated_transition_graph` with
`shared_node_transition_patch_mesh`. The actual topology-first transition solver is
implemented in later tasks.

```text
docs/superpowers/specs/2026-07-04-impeller-v0-91-topology-first-transitions-design.md
docs/superpowers/plans/2026-07-04-impeller-v0-91-topology-first-transitions.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91/CHANGELOG.md
```

## v1.0 Design Note

The v1.0 line stops treating blade edge/root and hub bevel geometry as post-generated
transition patches. It defines a native multi-face topology graph where pressure,
suction, leading-edge, trailing-edge, tip, root, hub, bore, and bevel faces are
generated as named constructor outputs with shared-edge identity.

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/README.md
docs/superpowers/specs/2026-07-05-impeller-v1-0-topology-first-constructor-spec.md
docs/superpowers/plans/2026-07-05-impeller-v1-0-topology-first-constructor-implementation.md
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/CHANGELOG.md
```
