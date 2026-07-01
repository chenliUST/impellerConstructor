# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.6 Changelog

Date: 2026-07-01

Supersedes: `v0_5`

## Changes

1. Added `surface_graph_trimmed_brep` export contract.
2. Added `surface_graph_support_face_brep_step` current STEP exactness label and
   `surface_graph_trimmed_nurbs_step` target exactness label for the V0.6 trimmed-face
   contract target.
3. Preserved STL and mesh STEP exports as separately labeled artifacts.
4. Added CAD payloads for exportable graph surfaces.
5. Added explicit blade root and edge fillet/blend feature controls.
6. Added CFD surface mesh manifest for mesh-quality inspection.
7. Added default output copies under `Model Output/`.

## Implementation Evidence

Task 14 generated local evidence runs for `radial_open_reference_v0_6` and
`radial_closed_reference_v0_6`. The open preset emitted 81 B-Rep faces and 42624 mesh
triangles; the closed preset emitted 86 B-Rep faces and 48000 mesh triangles. Both
runs used `root_fillet_radius_mm` of 8.0. The emitted STEP B-Rep faces are unsewn
NURBS/analytic support faces generated from `cad_surface` payloads.

## Limitations

- V0.6 STEP output is research B-Rep evidence, not certified manufacturing geometry.
- The current STEP writer does not yet consume `trim_loops` or `cad_edge` wires for
  true trimmed topological faces.
- CFD support is a surface mesh inspection manifest, not a solver-ready volume mesh.
- CAD healing/import quality still needs third-party review across parameter ranges.
