# Impeller v0.7 Bounded Transitions And Mesh Evidence

Date: 2026-07-02

Related spec:

- `docs/superpowers/specs/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh-design.md`

## 1. Starting Feedback

After the V0.6 branch was pushed, the user tested generated artifacts with third-party
software and reported the following issues:

1. `radial_closed_reference_v0_6-run-b9d120f1f3a1.mesh.step`,
   `radial_open_reference_v0_6-run-cf68b19c10a4.mesh.step`, and
   `radial_open_reference_v0_6-run-97f5b9111673.mesh.step` still failed to open in
   third-party software.
2. The corresponding non-mesh STEP files opened, but the geometry was wrong.
3. The hub shape was wrong.
4. The hub top and bottom faces appeared as very large planes.
5. Fillet/transition geometry was not visible enough in the frontend.
6. The user expects default rounded transitions between hub and blades and along blade
   edges.
7. In CFD full-360 and CFD360 mesh views, the hub appeared to be only one surface.
8. The frontend did not provide a true mesh detail view for engineering mesh-quality
   inspection.

The user then approved a V0.7 direction and clarified the transition requirement:

- all adjacent surface intersections should be selectable for edge treatment;
- treatment should allow none, chamfer, or fillet;
- radius should be controllable;
- because impeller topology is predictable, the frontend should probably expose
  topology families rather than a fully freeform edge editor;
- transition behavior must be implemented consistently in modeling, display, export,
  and mesh.

## 2. Screenshot Evidence

The following screenshots were provided by the user and copied into this evidence folder.

1. `v0-6-step-unbounded-support-plane-third-party-view.png`
   - Shows the V0.6 STEP geometry loaded in a third-party viewer with incorrect hub and
     blade geometry plus an unbounded support plane crossing the scene.

2. `v0-6-step-extreme-plane-scale-third-party-view.png`
   - Shows the same failure mode at scene scale: the impeller is tiny relative to a huge
     planar strip.

These screenshots are evidence that V0.6 support-face STEP export is insufficient for
third-party CAD review.

## 3. Code-Level Diagnosis

V0.6 ordinary STEP export is currently labeled:

```text
surface_graph_support_face_brep_step
```

That label is honest: it is a support-face B-Rep, not a true trimmed/sewn B-Rep.

The most direct cause of the giant top/bottom planes is that planar CAD support faces
are emitted with an arbitrary unbounded parameter range:

```python
BRepBuilderAPI_MakeFace(plane, -10000.0, 10000.0, -10000.0, 10000.0, 1.0e-6)
```

The underlying `surface_graph` for `inner_hub_bottom_face` and `hub_top_cap_face`
contains finite annular `uv_grid` regions, but the STEP writer does not consume the
annular boundary as a topological wire. Therefore third-party CAD software sees a huge
rectangular support face rather than a finite annular cap.

The mesh STEP problem has a separate root cause: V0.6 `mesh.step` uses AP242
`TRIANGULATED_FACE_SET`. This is standards-aware but not universally supported by CAD
viewers and should not remain the default mesh review exchange format.

## 4. Ontology Insight

V0.6 proved that a `surface_graph` can carry both sampled display geometry and CAD
support-surface payloads. V0.7 must add a stronger topological layer:

```text
surface_graph surface
-> bounded face
-> edge adjacency
-> transition policy
-> transition surface
-> sewn export shell
-> mesh region
```

The key ontology upgrade is that an edge is not merely a line of contact. It becomes a
designable transition site with:

- a stable `edge_id`;
- adjacent surfaces;
- an edge family;
- a treatment policy;
- a radius;
- generated transition surface ids;
- export face ids;
- mesh region ids;
- provenance back to constructor rules and DSL variables.

## 5. V0.7 Evidence To Collect

V0.7 should produce new evidence for:

1. STEP import into at least one third-party CAD/viewer with no unbounded plane.
2. STEP re-import through OCCT with valid bounded faces and finite bounding boxes.
3. Screenshots showing visible default blade-root and blade-edge fillets.
4. Screenshots showing hub top/bottom annular caps as bounded faces.
5. Frontend screenshots of the mesh view with triangle edges and transition-region
   quality highlighting.
6. Manifest excerpts proving every transition region maps back to
   `edge_id -> transition_policy_id -> surface_graph_id -> feature_id -> DSL variable`.

## 6. Current Status

This evidence package records motivation for V0.7. It does not change V0.6 behavior.
V0.6 remains an honest support-face B-Rep evidence line, while V0.7 is intended to
deliver bounded/sewn CAD faces, real transition topology, and a true engineering mesh
inspection workflow.
