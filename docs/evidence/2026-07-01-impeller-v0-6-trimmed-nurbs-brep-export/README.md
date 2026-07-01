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

## 5. Ontology Insight

V0.5 established:

```text
export_artifact is a projection of surface_graph
```

V0.6 should establish:

```text
surface_graph must contain both sampled view geometry and CAD-construction geometry.
```

These are distinct but linked layers:

- `uv_grid`: sampled points for rendering, STL, and mesh inspection;
- `cad_surface`: parametric support surface;
- `cad_edge`: topological and geometric trim boundary;
- `brep_face`: exported CAD face;
- `mesh_region`: simulation mesh review region;
- `blend_feature`: explicit fillet/rounding feature with design variables.

## 6. Evidence To Preserve During Implementation

When V0.6 is implemented, this folder should receive:

1. STEP import screenshots from at least one third-party CAD/viewer.
2. A machine-readable export summary with B-Rep face count, shell count, sewing status,
   and exactness labels.
3. A screenshot or export manifest showing visible blade root fillets.
4. A screenshot or manifest showing leading/trailing edge rounding.
5. Mesh view screenshots showing CFD360 mesh inspection and quality metrics.
6. Any failed CAD import logs, because failed import is useful ontology evidence.

Generated heavy STEP/STL outputs should remain in `Model Output/` unless a small
sample file is explicitly selected as evidence.

## 7. Current Status

No V0.6 runtime resources exist yet.

This evidence folder records the motivation and required research trace for a future
V0.6 implementation. It does not claim that trimmed NURBS/B-Rep export is already
implemented.
