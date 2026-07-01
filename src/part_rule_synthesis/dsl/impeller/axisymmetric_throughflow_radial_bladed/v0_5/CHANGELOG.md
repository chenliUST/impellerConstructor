# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.5 Changelog

Date: 2026-07-01

Supersedes: `v0_4`

## Motivation

v0.5 makes STL/STEP exports faithful to the `surface_graph` inspected in the frontend. The version exists because external CAD review showed that the previous CadQuery proxy export could diverge from the graph-rendered impeller: extra base disk, missing surfaces, and mismatched blade/edge topology.

## Changes

1. Added `export_contracts/surface_graph_faithful.json`.
2. Added constructor-level `surface_graph_faithful` export contract references.
3. Kept the v0.4 surface/feature graph and CFD full-360 contracts as the geometry baseline.
4. Defined STL exactness as `surface_graph_sampled_mesh`.
5. Defined STEP exactness as `surface_graph_mesh_step`.
6. Required export-region provenance from each exported triangle/face back to `surface_graph_id`, feature, and role.
7. Updated the V0.5 default baseline to 12 blades with zero default leading/trailing edge lean and sweep so the blade-surface `u=0` and `u=1` boundaries are straight by default.
8. Added DSL-level six-point Hub and Tip/Shroud NURBS profile defaults for the V0.5 baseline.
9. Replaced the initial per-triangle STEP open-shell writer with a smaller AP242 `TRIANGULATED_FACE_SET` representation with deduplicated vertices.

## Implementation Status

The current v0.5 implementation emits research-grade sampled STL and graph-derived AP242 tessellated STEP faces. It does not claim exact industrial analytic B-Rep surfaces, watertight OCCT sewing, CAD-native chamfer operations, or solver-ready CFD volume meshing.
