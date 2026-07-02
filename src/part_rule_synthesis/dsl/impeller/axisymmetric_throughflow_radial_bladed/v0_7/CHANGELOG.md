# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.7 Changelog

Date: 2026-07-02

Supersedes: `v0_6`

## Changes

1. Added `surface_graph_bounded_brep` as the V0.7 export contract.
2. Added constructor-level `edge_families` for blade, hub, and mounting-bore transition defaults.
3. Added runtime-visible transition policy defaults derived from edge-family radius parameters.
4. Preserved V0.6 reference parameters, simulation views, and shape-control topology as the V0.7 baseline.

## Limitations

- V0.7 emits bounded, unsewn surface-graph B-Rep faces for the main STEP export. STL and OBJ remain separate graph-mesh review outputs, while sewn trimmed-solid validation remains downstream work.
- Default transition policies are constructor-level metadata and do not yet override generated geometry without downstream task support.
