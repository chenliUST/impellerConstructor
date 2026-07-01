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

- radial open impeller preset `radial_open_reference_v0_6`
- radial closed impeller preset `radial_closed_reference_v0_6`
- sampled surface graph generation
- surface-graph-faithful STL exports for external CAD review
- graph-derived tessellated STEP mesh artifacts for external visual review
- generated STEP files as graph-derived unsewn NURBS/analytic B-Rep support faces for V0.6 presets
- surface/feature graph identity
- full-360 CFD patch-group manifest and CFD surface mesh inspection manifest
- schema-only FEA solid view
- frontend CAD review, CFD full-360, mesh inspection, feature-debug views, export options, and fillet controls

## Claims The Repository Can Make

The current code can claim:

- deterministic runtime compilation from versioned JSON DSL resources
- deterministic sampled impeller surface graph for the v0.6 open and closed presets
- stable surface ids, feature ids, named boundary curves, and CFD patch group names for the tested presets
- campaign signatures that freeze topology-level optimization shape
- generated binary STL files derived from `manifest.geometry.surface_graph.surfaces[*].uv_grid`
- generated STEP files as graph-derived unsewn NURBS/analytic B-Rep support faces for V0.6 presets
- generated mesh STEP files as graph-derived tessellated mesh artifacts, separate from the V0.6 B-Rep STEP
- export manifests with region provenance from exported triangles/faces to `surface_graph_id`, feature, and role
- `cad_surface` payloads for exportable NURBS, plane, and cylinder graph surfaces
- CFD surface mesh manifests for mesh-quality inspection
- documented evidence that v0.4 CadQuery exports can differ from the frontend surface graph, and v0.5 corrects the source-of-truth split
- documented V0.6 implementation evidence for NURBS/analytic B-Rep support-face export, mesh inspection, and explicit fillet/blend controls

## Claims The Repository Cannot Make Yet

The current code cannot yet claim:

- certified manufacturing CAD geometry
- consumed trim-loop/wire STEP export from `trim_loops` or `cad_edge` data
- watertight OCCT sewing or healing
- exact variable-radius industrial CAD fillets or chamfers across all parameter values
- universal CAD repair/import quality across the full parameter space
- CFD mesh-quality view backed by an external production-grade mesher
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
- `surface_graph_faithful_export`: v0.5 export mode where files are derived from selected `surface_graph` surfaces
- `surface_graph_sampled_mesh`: v0.5 STL exactness label for sampled graph triangulation
- `surface_graph_mesh_step`: v0.5 STEP exactness label for graph-derived tessellated mesh STEP
- `surface_graph_trimmed_nurbs_step`: v0.6 contract/exactness label; the current writer emits graph-derived unsewn NURBS/analytic B-Rep support faces and does not yet consume trim loops or `cad_edge` wires
- `patch_contract_ready`: semantic CFD patch groups and instances are generated
- `solver_adapter_missing`: no mesher or solver has been invoked
- `schema_only`: resource shape exists but executable workflow does not

Avoid saying "CFD executable" without qualifying whether that means patch-contract executable, mesher executable, or solver executable.
