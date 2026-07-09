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

- radial open impeller preset `radial_open_reference_v1_1`
- radial closed impeller preset `radial_closed_reference_v1_1`
- high-twist thin inspection preset `radial_open_high_twist_thin_reference_v1_1`
- V1.1 blade-to-blade five-loop surface-family construction
- main/splitter passage-bisector semantics
- half-thickness leading/trailing edge cap semantics in physical `s_mm-q_mm`
- explicit sampled hub support/material review faces, including mounting bore and bottom thickness
- sampled surface graph generation and shared-boundary UV mesh review
- historical V0.7 bounded B-Rep, OBJ mesh, transition policy, and CFD surface mesh manifest paths retained as lineage evidence
- surface/feature graph identity
- full-360 CFD patch-group manifest and CFD surface mesh inspection manifest
- schema-only FEA solid view
- frontend CAD review, CFD full-360, mesh inspection, mesh overlay inspection, feature-debug views, export options, profile controls, and V1.1 blade-to-blade loop-family controls

V1.1 advances the current geometry-construction boundary from local section-loop and post-transition repair toward a blade-to-blade loop-family surface graph. V0.7 remains the strongest bounded B-Rep export evidence line. Manufacturing certification, sewn-solid validation, and CFD volume meshing remain outside this prototype.

## Claims The Repository Can Make

The current code can claim:

- deterministic runtime compilation from versioned JSON DSL resources
- deterministic sampled impeller surface graph for the V1.1 open, closed, and high-twist thin reference presets
- V1.1 blade-to-blade loop-family construction in `(s, q, h)` with `q = r * delta_theta`
- V1.1 main and splitter blade populations, including splitter passage-bisector positioning metrics
- V1.1 leading/trailing edge caps with half-local-thickness sagitta in physical `s_mm-q_mm`
- V1.1 root, open-tip, and closed-shroud attachment ribbons derived from actual blade loop boundaries
- V1.1 explicit sampled hub material review faces, including mounting bore and bottom thickness
- stable surface ids, feature ids, named boundary curves, and CFD patch group names for the tested presets
- campaign signatures that freeze topology-level optimization shape
- generated binary STL files derived from `manifest.geometry.surface_graph.surfaces[*].uv_grid`
- generated STEP files as graph-derived bounded, unsewn B-Rep faces for supported V0.7 annular surface-graph regions
- OCCT STEP reimport bounding-box checks for V0.7 bounded face exports
- generated OBJ mesh artifacts with transition-region provenance, separate from the V0.7 B-Rep STEP
- export manifests with region provenance from exported triangles/faces to `surface_graph_id`, feature, and role
- `cad_surface` payloads for exportable NURBS, plane, and cylinder graph surfaces
- CFD surface mesh manifests for mesh-quality inspection
- documented evidence that v0.4 CadQuery exports can differ from the frontend surface graph, and v0.5 corrects the source-of-truth split
- documented V0.6 implementation evidence for NURBS/analytic B-Rep support-face export, mesh inspection, and explicit fillet/blend controls
- documented V0.7 implementation evidence for bounded face export with transition-policy provenance through geometry, OBJ, and mesh manifests
- documented V1.1 implementation evidence for blade-to-blade construction logic, DSL resources, DSL-embedded ontology slice, half-thickness edge caps, splitter passage-bisector positioning, and V1.1 validation gates

## Claims The Repository Cannot Make Yet

The current code cannot yet claim:

- certified manufacturing CAD geometry
- consumed trim-loop/wire STEP export from `trim_loops` or `cad_edge` data
- watertight OCCT sewing or healing
- sewn solid certification
- exact variable-radius industrial CAD fillets or chamfers across all parameter values
- exact analytic V1.1 blade/root/tip surfaces beyond the current sampled review-grade graph
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
- `surface_graph_support_face_brep_step`: v0.6 exactness label for graph-derived unsewn NURBS/analytic B-Rep support faces
- `surface_graph_trimmed_nurbs_step`: v0.6 target exactness label; the current writer does not yet consume trim loops or `cad_edge` wires
- `surface_graph_bounded_unsewn_brep_step`: v0.7 diagnostic exactness label for bounded but unsewn B-Rep faces
- `surface_graph_trimmed_brep_step`: v0.7 current target/current exactness label for supported bounded face export; this does not imply sewn-solid certification
- `patch_contract_ready`: semantic CFD patch groups and instances are generated
- `solver_adapter_missing`: no mesher or solver has been invoked
- `schema_only`: resource shape exists but executable workflow does not

Avoid saying "CFD executable" without qualifying whether that means patch-contract executable, mesher executable, or solver executable.
