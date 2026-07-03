# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.8 Changelog

Date: 2026-07-02

Supersedes: `v0_7`

## Changes

1. Added `transition_resolved_bounded_brep` as the V0.8 export contract resource.
2. Relabeled V0.7 open/closed reference presets as `radial_open_reference_v0_8` and `radial_closed_reference_v0_8`.
3. Added runtime-visible `transition_geometry_status` metadata for the V0.8 presets.
4. Preserved V0.7 reference parameters, simulation views, edge-family defaults, and shape-control topology as the V0.8 baseline.

## Limitations

- V0.8 is an additive resource line only. It does not implement true transition-resolved geometry.
- Transition policies are exposed as runtime metadata, but transition radius and treatment overrides do not yet change the transition surface grids.
- The contract names the target transition-resolved B-Rep direction; STEP sewing, CAD healing, manufacturing certification, and solver-ready CFD volume meshing remain downstream work.
