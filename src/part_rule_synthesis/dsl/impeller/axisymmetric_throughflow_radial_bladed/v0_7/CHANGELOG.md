# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.7 Changelog

Date: 2026-07-02

Supersedes: `v0_6`

## Changes

1. Added `surface_graph_bounded_brep` as the V0.7 export contract.
2. Added constructor-level `edge_families` for blade, hub, and mounting-bore transition defaults.
3. Added runtime-visible transition policy defaults derived from edge-family radius parameters.
4. Preserved V0.6 reference parameters, simulation views, and shape-control topology as the V0.7 baseline.

## Limitations

- V0.7 routes the bounded B-Rep contract through the current deferred surface-graph mesh bridge: STEP/STL/manifest review artifacts are emitted now, while trimmed bounded B-Rep STEP remains the target export.
- Default transition policies are constructor-level metadata and do not yet override generated geometry without downstream task support.
