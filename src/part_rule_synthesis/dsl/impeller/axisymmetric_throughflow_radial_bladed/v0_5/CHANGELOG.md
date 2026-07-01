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

## Implementation Status

The first v0.5 implementation emits research-grade sampled STL and graph-derived triangular STEP faces. It does not claim exact industrial analytic B-Rep surfaces, watertight OCCT sewing, or solver-ready CFD volume meshing.
