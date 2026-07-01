# Version History

This repository keeps previous impeller DSL versions in source control and in versioned resource folders. The goal is to preserve the research trail: observed loss, revised semantics, new DSL contracts, and implementation behavior should remain auditable.

## Git Milestones

| Milestone | Commit | Description |
| --- | --- | --- |
| Baseline | `bdb60d2` | Initial part-rule-synthesis project baseline. |
| v0.2 slice | `2d3957b` | First focused axisymmetric throughflow impeller DSL/runtime/frontend metadata path. |
| v0.3 runtime | `7afb0d2` | Solid hub/hood, profile/curve overrides, staged geometry, and frontend workflow. |
| v0.4 graph contract | `f74eb06` | Design-space campaign signatures, variable profile topology, surface/feature graph, CFD full-360 manifest, and frontend CFD view. |

Version tags:

```text
impeller-dsl-v0.2 -> 2d3957b
impeller-dsl-v0.3 -> 7afb0d2
impeller-dsl-v0.4 -> f74eb06
```

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

## How To Run A Specific Version

In Python tests or scripts:

```python
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

service = RuleSynthesisService(Path("runs"))
engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
run = service.instantiate(engine.engine_id, {})
manifest = run.manifest
```

Change `preset_id` to one of the version-specific ids above to select earlier versions.

## Compatibility Rule

Do not mutate old version folders to express new semantics. If a natural-language loss record changes the meaning of a feature, create a new DSL version or an explicit patch file so earlier research evidence remains reproducible.
