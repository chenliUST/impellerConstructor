# Impeller v0.6 Trimmed NURBS B-Rep Export Evidence

Date: 2026-07-01

Related spec:

- `docs/superpowers/specs/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export-design.md`

## 1. Starting Feedback

After V0.5 compacted STEP export from a per-triangle open-shell representation to an
AP242 tessellated face set, the user reported that third-party STEP loading still has
problems.

The user clarified the desired export target:

1. Freeform surfaces should be stored as NURBS parameter surfaces.
2. Actual CAD faces should be trimmed by topological boundaries.
3. The export should not be triangle mesh data wrapped in a STEP file.
4. Exported files should use correct default file types and extensions.
5. Backend-generated artifacts should default to the project `Model Output/` folder.
6. The frontend should include a mesh inspection view for future CFD mesh-quality review.
7. Blade-hub root transitions and blade edges should be rounded/filleted, interactively
   designable, and visible in both frontend and output models.

## 2. Diagnosis Of Current V0.5 Boundary

V0.5 currently provides:

- binary STL from `surface_graph` triangles;
- AP242 tessellated STEP from the same sampled graph triangles;
- region provenance from exported mesh regions back to `surface_graph_id`, feature, and role;
- default 12-blade open/closed V0.5 presets;
- default straight blade `u=0` and `u=1` edges.

This is a faithful graph projection, but it is not CAD-grade B-Rep geometry.

The current STEP writer records:

```text
CARTESIAN_POINT_LIST_3D
TRIANGULATED_FACE_SET
TESSELLATED_SHAPE_REPRESENTATION
```

Those entities are mesh/tessellation entities. They are not equivalent to trimmed
NURBS/analytic CAD faces.

## 3. Root Cause

The persistent third-party issue is a representation mismatch:

```text
User needs CAD B-Rep/NURBS faces.
V0.5 exports a graph-derived tessellated mesh STEP.
```

The problem is no longer the V0.4 proxy-geometry split. V0.5 fixed that semantic
source-of-truth issue. The remaining issue is CAD exactness.

## 4. Version Decision

This feedback should become V0.6.

It should not be treated as a V0.5 patch because it requires:

- new `surface_graph` fields for CAD parameter surfaces and trim loops;
- a new OCCT B-Rep export path;
- new exactness labels;
- new frontend mesh-quality inspection affordances;
- new interactive fillet/blend design variables;
- new acceptance evidence from third-party CAD tools.

In this branch, V0.6 is implemented as graph-derived unsewn NURBS/analytic
B-Rep support-face STEP evidence for the open and closed reference presets. The STEP
writer creates support faces from `cad_surface` payloads, but it does not yet consume
`trim_loops` or `cad_edge` wires for true trimmed-face export. The implementation is
research B-Rep evidence, not certified manufacturing CAD, solver-ready CFD volume
meshing, or a promise that every parameter combination heals in every CAD tool.

## 5. Ontology Insight

V0.5 established:

```text
export_artifact is a projection of surface_graph
```

V0.6 establishes:

```text
surface_graph must contain both sampled view geometry and CAD-construction geometry.
```

These are distinct but linked layers:

- `uv_grid`: sampled points for rendering, STL, and mesh inspection;
- `cad_surface`: parametric support surface;
- `cad_edge`: topological and geometric trim boundary, not yet consumed by the STEP writer;
- `brep_face`: exported support face in the current writer, with true trim-loop/wire export still pending;
- `mesh_region`: simulation mesh review region;
- `blend_feature`: explicit fillet/rounding feature with design variables.

## 6. Implemented Evidence

Task 14 generated local V0.6 sample outputs under `Model Output/_v06_evidence_runs`.
The generated STEP/STL/mesh STEP files are intentionally local artifacts and should
remain untracked unless a small sample is explicitly selected as evidence.

```python
{'runs': [{'preset_id': 'radial_open_reference_v0_6', 'run_id': 'run-962deafb7272', 'step': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_open_reference_v0_6-run-962deafb7272.step', 'stl': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_open_reference_v0_6-run-962deafb7272.stl', 'mesh_step': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_open_reference_v0_6-run-962deafb7272.mesh.step', 'brep_face_count': 81, 'mesh_triangle_count': 42624, 'root_fillet_radius_mm': 8.0}, {'preset_id': 'radial_closed_reference_v0_6', 'run_id': 'run-331c7cacc1c2', 'step': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_closed_reference_v0_6-run-331c7cacc1c2.step', 'stl': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_closed_reference_v0_6-run-331c7cacc1c2.stl', 'mesh_step': 'Model Output\\_v06_evidence_runs\\Model Output\\radial_closed_reference_v0_6-run-331c7cacc1c2.mesh.step', 'brep_face_count': 86, 'mesh_triangle_count': 48000, 'root_fillet_radius_mm': 8.0}]}
```

Implemented pieces recorded by the branch:

1. `surface_graph_trimmed_brep` export contract.
2. OCP/OCCT STEP writer for graph-derived unsewn B-Rep support faces.
3. `cad_surface` payloads on exportable graph surfaces.
4. Analytic plane and cylinder support alongside NURBS surface payloads.
5. STEP exactness label `surface_graph_trimmed_nurbs_step`, with current implementation
   limited to support-face B-Rep geometry without consumed trim loops or wires.
6. STL and mesh STEP retained as separately labeled sampled/mesh artifacts.
7. Default output copies under the project `Model Output/` folder.
8. CFD surface mesh manifest with triangle-count evidence for mesh inspection.
9. Frontend V0.6 export options, mesh view affordances, and fillet controls.

## 7. Remaining Evidence Gaps

Manual evidence still to collect:

1. STEP import screenshots from at least one third-party CAD/viewer.
2. STEP writer consumption of `trim_loops` and `cad_edge` wires for actual trimmed
   topological faces.
3. Screenshot evidence that blade root fillets and edge rounding are visible in a
   third-party CAD/viewer.
4. Mesh-view screenshots showing CFD360 mesh inspection and quality metrics.
5. Failed CAD import logs across parameter sweeps, because failed import is useful
   ontology evidence.

## 8. Current Status

V0.6 runtime resources exist in this branch and generate STEP files as graph-derived
unsewn NURBS/analytic B-Rep support faces for `radial_open_reference_v0_6` and
`radial_closed_reference_v0_6`. The separate STL and mesh STEP artifacts remain
sampled mesh outputs and are labeled as such.
