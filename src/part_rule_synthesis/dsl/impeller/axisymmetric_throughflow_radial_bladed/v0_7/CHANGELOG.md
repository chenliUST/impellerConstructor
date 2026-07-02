# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.7 Changelog

Date: 2026-07-02

Supersedes: `v0_6`

## Changes

1. Added `surface_graph_bounded_brep` as the V0.7 export contract.
2. Added constructor-level `edge_families` for blade, hub, and mounting-bore transition defaults.
3. Added runtime-visible transition policy defaults derived from edge-family radius parameters.
4. Preserved V0.6 reference parameters, simulation views, and shape-control topology as the V0.7 baseline.

## Limitations

- V0.7 emits bounded, unsewn surface-graph B-Rep faces for the main STEP export. The bounded writer currently covers supported annular face families and records excluded unsupported surfaces; it does not certify a sewn solid.
- STEP export is gated by OCCT reimport bounding-box validation for finite faces, but watertight sewing, CAD healing, manufacturing certification, and broad third-party CAD repair remain downstream work.
- Transition policies now affect generated transition geometry and are carried into STEP/OBJ/mesh manifests through edge-family and transition-region provenance. They remain predictable topology-family controls, not a freeform industrial edge-editing system.
- STL and OBJ remain separate graph-mesh review outputs; CFD volume meshing and solver-ready case generation remain outside V0.7.
