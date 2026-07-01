# V0.6 Changelog Draft

Date: 2026-07-01

Status: implemented in this branch

## Motivation

V0.5 made exported STL/STEP files faithful to `surface_graph`, but its STEP file was
a tessellated mesh representation. V0.6 adds a graph-derived B-Rep export path where
exportable surfaces carry `cad_surface` payloads and the primary STEP output is
unsewn NURBS/analytic B-Rep support-face evidence. The exactness label retains the
trimmed-face contract name, but the current writer does not yet consume trim loops or
`cad_edge` wires.

## Implemented Changes

1. Added `v0_6` DSL resources and reference presets:
   `radial_open_reference_v0_6` and `radial_closed_reference_v0_6`.
2. Added `surface_graph_trimmed_brep` export contract.
3. Added `cad_surface` payloads for exportable graph surfaces.
4. Added OCP/OCCT STEP writer support for graph-derived NURBS, plane, and cylinder
   support faces.
5. Preserved STL and mesh STEP as separate sampled/mesh artifacts with separate
   exactness labels.
6. Added default output copies under project `Model Output/`.
7. Added CFD surface mesh manifest evidence for mesh-quality inspection.
8. Added frontend export choices, mesh view affordances, and fillet controls.
9. Promoted blade root and blade edge rounding to explicit fillet/blend feature
   controls.

## Exactness Labels

```text
surface_graph_trimmed_nurbs_step
surface_graph_sampled_mesh
surface_graph_mesh_step
```

`surface_graph_trimmed_nurbs_step` is the V0.6 contract/exactness label. Current
implementation evidence is support-face B-Rep geometry only; true trim-loop/wire
export remains unwired.

## Local Evidence

Task 14 generated the following local artifacts under `Model Output/_v06_evidence_runs`.
These generated STEP/STL/mesh STEP files remain untracked local outputs.

| Preset | Run id | B-Rep faces | Mesh triangles | Root fillet radius |
| --- | --- | ---: | ---: | ---: |
| `radial_open_reference_v0_6` | `run-962deafb7272` | 81 | 42624 | 8.0 mm |
| `radial_closed_reference_v0_6` | `run-331c7cacc1c2` | 86 | 48000 | 8.0 mm |

## Non-Claims

V0.6 does not claim:

- certified manufacturing CAD geometry;
- solver-ready CFD volume mesh;
- universal CAD healing or import compatibility across all parameter values;
- consumed trim-loop/wire STEP export from `trim_loops` or `cad_edge` data;
- exact variable-radius industrial fillets across all parameter values.

## Evidence Still To Collect

1. Third-party manual CAD import screenshots.
2. STEP writer consumption of `trim_loops` and `cad_edge` wires for actual trimmed
   topological faces.
3. Screenshot evidence for visible blade root fillets and edge rounding in a CAD
   viewer.
4. Mesh-view screenshots for CFD360 inspection and mesh-quality review.
5. Failed CAD import logs from parameter sweeps where import or healing quality is
   poor.
