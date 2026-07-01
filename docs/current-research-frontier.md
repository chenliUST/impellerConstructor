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
- CadQuery-generated STEP/STL exports for external CAD review, with known mismatch risk against frontend `surface_graph`
- surface/feature graph identity
- full-360 CFD patch-group manifest
- schema-only FEA solid view
- frontend CAD review, CFD full-360, and feature-debug views

Next planned frontier:

- v0.5 surface-graph-faithful export contract
- STL generated from the same `surface_graph` surfaces rendered in the frontend
- export-region provenance from third-party file inspection back to `surface_graph_id`, feature, and role

## Claims The Repository Can Make

The current code can claim:

- deterministic runtime compilation from versioned JSON DSL resources
- deterministic sampled impeller surface graph for the v0.4 open and closed presets
- stable surface ids, feature ids, named boundary curves, and CFD patch group names for the tested presets
- campaign signatures that freeze topology-level optimization shape
- generated STEP files containing CadQuery/OCCT topology entities for third-party CAD inspection
- generated binary STL files with non-empty triangle meshes for third-party geometry inspection
- documented evidence that current v0.4 CadQuery exports can differ from the frontend surface graph, with a v0.5 plan to correct that

## Claims The Repository Cannot Make Yet

The current code cannot yet claim:

- STEP/STL exports are faithful projections of `manifest.geometry.surface_graph`
- exact industrial B-Rep geometry
- watertight OCCT sewing or healing
- exact variable-radius CAD fillets or chamfers
- certified CAD repair quality across the full parameter space
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
- `analysis_review_cad_export`: CadQuery-generated STEP/STL intended for external inspection, not certified manufacturing geometry
- `cadquery_sync`: synchronous CadQuery export path used by the API
- `surface_graph_faithful_export`: planned v0.5 export mode where files are derived from selected `surface_graph` surfaces
- `surface_graph_sampled_mesh`: planned v0.5 STL exactness label for sampled graph triangulation
- `patch_contract_ready`: semantic CFD patch groups and instances are generated
- `solver_adapter_missing`: no mesher or solver has been invoked
- `schema_only`: resource shape exists but executable workflow does not

Avoid saying "CFD executable" without qualifying whether that means patch-contract executable, mesher executable, or solver executable.
