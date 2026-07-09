# Axisymmetric Throughflow Radial Bladed Impeller DSL v1.0 Changelog

Date: 2026-07-05

Supersedes: `v0_91`

## Changes

1. Adds V1.0 open and closed reference presets with the
   `topology_first_closed_nurbs_impeller_surface_graph` export contract.
2. Reframes the constructor around native topology faces instead of post-generated
   edge-treatment patches.
3. Declares pressure, suction, leading-edge, trailing-edge, tip, and root blade
   faces as first-class generated surfaces.
4. Declares hub, mounting-bore, and bevel/chamfer geometry as native revolved
   profile faces generated with the hub body.
5. Adds V1.0 capability matrix and golden-case registry ids for repeatable
   validation and expert review.
6. Sets inspection-oriented preset defaults with fewer, thicker blades and larger
   visible radii so face construction defects are easier to see.

## Limitations

- V1.0 remains sampled review-grade geometry until exact OCCT/analytic B-Rep
  sewing is implemented.
- Root face continuity may initially be measured G1 with explicit G2 targets where
  local topology allows it.
- Production meshing adapters and solver-ready CFD volume meshes remain downstream
  work.
