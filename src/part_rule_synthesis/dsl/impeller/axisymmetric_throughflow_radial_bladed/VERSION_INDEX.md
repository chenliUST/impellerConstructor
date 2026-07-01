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

## Runtime Loading

Runtime loading and compilation are handled by:

```text
src/part_rule_synthesis/impeller_dsl_resources.py
src/part_rule_synthesis/impeller_runtime_compiler.py
```

Service-level synthesis selects a preset id and receives a compiled runtime DSL dictionary:

```python
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
```

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
