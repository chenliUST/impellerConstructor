# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.91 Changelog

Date: 2026-07-04

Supersedes: `v0_8`

## Changes

1. Added V0.91 open and closed reference presets with the
   `topology_first_transition_bounded_brep` export contract.
2. Defines V0.91 as a kernel validity and reviewability milestone, not a new broad
   impeller taxonomy line.
3. Adds kernel capability matrix and golden case registry resources for repeatable
   validation and expert review.
4. Requires geometry validation reports before export and blocks partial STL/STEP/OBJ
   success when blocking transition failures are present.
5. Replaces the V0.8 single root transition success criterion with double-sided
   pressure-root and suction-root transition surface topology.
6. Requires shared-node transition patch mesh and bounded review B-Rep export metadata
   so adjacent main faces do not hide transition defects.

## Limitations

- V0.91 exports a bounded, unsewn review B-Rep shell. It does not claim a watertight
  sewn solid.
- Fillet and chamfer patches are validated sampled transition geometry, not
  manufacturing-certified
  exact CAD feature reconstruction.
- STEP sewing, CAD healing, production meshing adapters, and solver-ready CFD volume
  meshes remain downstream work.
