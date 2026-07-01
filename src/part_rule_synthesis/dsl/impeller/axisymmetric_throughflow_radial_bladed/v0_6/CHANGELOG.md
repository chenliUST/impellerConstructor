# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.6 Changelog

Date: 2026-07-01

Supersedes: `v0_5`

## Motivation

v0.6 starts the trimmed NURBS B-Rep STEP resource line while keeping the v0.5 surface graph baseline loadable. It records the intended exact STEP export contract separately from the mesh-inspection path so downstream implementation cannot label mesh STEP output as B-Rep output.

## Changes

1. Added `export_contracts/surface_graph_trimmed_brep.json`.
2. Added constructor-level `surface_graph_trimmed_brep` export contract references.
3. Kept the v0.5 surface/feature graph, CFD full-360, and FEA schema resources as the geometry baseline.
4. Defined exact STEP direction as `surface_graph_trimmed_nurbs_step`.
5. Kept mesh inspection explicit as `surface_graph_sampled_mesh` and `surface_graph_mesh_step`.
6. Added explicit leading-edge, trailing-edge, tip-edge, and root-fillet defaults to the v0.6 presets.

## Implementation Status

The v0.6 resources define the contract for trimmed NURBS B-Rep STEP export. Writer implementation and later geometry-kernel work are intentionally outside this resource-line task.
