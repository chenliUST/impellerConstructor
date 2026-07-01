# Current Research Frontier

This document states what the current repository can and cannot claim. It should be updated whenever a new DSL version changes the research boundary.

## Current Canonical Repository

`impellerConstructor` is the active repository for the `part_rule_synthesis` impeller work.

The older sibling directory `part-rule-synthesis` is a baseline snapshot and should not receive new feature work unless it is intentionally being archived or compared.

Historical rollback evidence is anchored by these tags:

- `impeller-dsl-v0.2`
- `impeller-dsl-v0.3`
- `impeller-dsl-v0.4`

Run `.\scripts\verify_version_lineage.ps1` from `impellerConstructor` to verify that the current versioned folders and those historical tags can still synthesize and instantiate their reference presets.

## Current Supported Slice

The active research slice is:

```text
AxisymmetricThroughflowRadialBladedImpeller
```

Current focus:

- radial open impeller preset `radial_open_reference_v0_4`
- radial closed impeller preset `radial_closed_reference_v0_4`
- sampled surface graph generation
- surface/feature graph identity
- full-360 CFD patch-group manifest
- schema-only FEA solid view
- frontend CAD review, CFD full-360, and feature-debug views

## Claims The Repository Can Make

The current code can claim:

- deterministic runtime compilation from versioned JSON DSL resources
- deterministic sampled impeller surface graph for the v0.4 open and closed presets
- stable surface ids, feature ids, named boundary curves, and CFD patch group names for the tested presets
- campaign signatures that freeze topology-level optimization shape
- generated preview STL from sampled surface graph triangles
- generated placeholder STEP text that explicitly marks exact CAD export as deferred

## Claims The Repository Cannot Make Yet

The current code cannot yet claim:

- exact industrial B-Rep geometry
- watertight OCCT sewing or healing
- exact variable-radius CAD fillets or chamfers
- mesher-ready CFD volume domain
- solver-ready CFD case generation
- periodic single-passage CFD sector generation
- executable FEA solid workflow
- CAM, DFMA, manufacturing, or strength validation
- broad impeller taxonomy coverage beyond the active throughflow radial-bladed slice

## Highest-Risk Gap

The current highest-risk gap is feasibility and validity, not visualization.

The 2026-06-29 parameter experiment showed that the kernel can usually return a data structure, but many parameter combinations are mathematically invalid under sampled diagnostics. The next research increment should promote those diagnostics into first-class feasibility gates before expanding more impeller types.

Minimum next gates:

- radial and mixed-flow exit radius greater than inlet radius
- blade pitch versus blade thickness
- minimum hub-to-tip span versus thickness and fillet allowance
- maximum cumulative blade wrap
- signed radius stays positive before polar conversion
- surface normal consistency across sampled cells
- blade boundary point-on-support-surface conformance

## Status Vocabulary

Use these labels consistently in docs and manifests:

- `research_grade_sampled_surface`: sampled surface graph, not exact CAD
- `preview_mesh`: STL triangles generated from sampled surfaces
- `cad_export_deferred`: exact STEP/B-Rep is not generated
- `patch_contract_ready`: semantic CFD patch groups and instances are generated
- `solver_adapter_missing`: no mesher or solver has been invoked
- `schema_only`: resource shape exists but executable workflow does not

Avoid saying "CFD executable" without qualifying whether that means patch-contract executable, mesher executable, or solver executable.
