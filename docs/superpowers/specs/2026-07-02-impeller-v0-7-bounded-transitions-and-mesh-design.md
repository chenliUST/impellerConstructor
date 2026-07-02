# Impeller v0.7 Bounded Transitions And Mesh Design

Date: 2026-07-02
Status: review draft
Supersedes: v0.6 support-face B-Rep export target, without rewriting v0.6 resources or PR history
Evidence log: `docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/README.md`

## 1. Purpose

This spec defines V0.7 for the
`AxisymmetricThroughflowRadialBladedImpeller` constructor family.

V0.6 introduced graph-derived NURBS/analytic support-face STEP export, explicit
fillet/blend surfaces, model-output artifacts, and a first CFD surface mesh manifest.
That was a useful evidence step, but user testing showed that V0.6 is still not enough
for third-party CAD review or engineering mesh inspection.

V0.7 should be the first version where:

```text
STEP export contains bounded topological CAD faces rather than unbounded support faces,
and all designable edge transitions are represented consistently in modeling,
frontend display, export, and mesh inspection.
```

## 2. Observed V0.6 Problems

The user reported five concrete failure modes:

1. `mesh.step` files still fail to open in third-party software.
2. Regular STEP files open, but the geometry is wrong.
3. Hub geometry is wrong.
4. Hub top and bottom faces appear as very large planes.
5. Fillet/transition geometry is not visible in the frontend, and the mesh view does
   not show engineering mesh detail.

The user also clarified a new modeling requirement:

```text
All adjacent surface edge intersections should be selectable for edge treatment:
none, chamfer, or fillet, with controllable radius.
```

The frontend should not become a fully freeform edge-editing CAD tool. Because impeller
topology is predictable, it should expose edge families and transition policies.

## 3. Root-Cause Analysis

### 3.1 Unbounded Planar Support Faces

V0.6 exports planar faces by creating an OCCT plane with a large rectangular parameter
range:

```python
BRepBuilderAPI_MakeFace(plane, -10000.0, 10000.0, -10000.0, 10000.0, 1.0e-6)
```

The `surface_graph` source for hub caps is finite: `inner_hub_bottom_face` and
`hub_top_cap_face` have annular `uv_grid` regions and known inner/outer radii.

The actual problem is that V0.6 does not turn those finite annular boundaries into
topological wires. Third-party CAD software therefore receives huge untrimmed planes.

### 3.2 Support Faces Are Not True Trimmed B-Rep

V0.6 correctly labels the current STEP exactness as:

```text
surface_graph_support_face_brep_step
```

The target exactness remains:

```text
surface_graph_trimmed_nurbs_step
```

The missing implementation pieces are:

- consuming `trim_loops`;
- consuming `cad_edge` payloads;
- creating `TopoDS_Wire` boundaries;
- creating bounded `TopoDS_Face` instances;
- sewing adjacent faces into shells where possible;
- validating the result with OCCT.

### 3.3 Revolved Hub Shape Is Too Approximate

The hub is a revolved meridional NURBS profile. V0.6 converts many surfaces into a
small rectangular B-spline control net derived from samples. That is useful for support
face evidence, but it is not a robust representation of a revolved NURBS/analytic
surface.

V0.7 should represent hub and shroud as true revolved surfaces where practical, or as a
bounded B-spline surface with enough control fidelity and explicit periodic/closed
semantics.

### 3.4 Mesh STEP Is Not A Reliable Default Mesh Exchange

V0.6 `mesh.step` uses AP242 `TRIANGULATED_FACE_SET`. Some tools do not support that
representation. V0.7 should keep this as optional evidence only and choose more common
mesh exchange artifacts for default engineering inspection.

### 3.5 Fillets Exist As Surfaces But Not As Trustworthy Transitions

V0.6 emits root, leading-edge, trailing-edge, and tip blend surfaces. However:

- they are not clearly exposed in the frontend as transition features;
- adjacent main faces are not trimmed back by the transition;
- STEP export does not sew them as real topological blends;
- mesh inspection does not highlight them or refine them as transition zones.

V0.7 must treat transitions as first-class topology, not visual decoration.

## 4. Version Decision

This must be V0.7, not a V0.6 patch.

Reasons:

1. V0.6 was already pushed as a support-face B-Rep evidence line.
2. V0.7 changes the CAD topology contract from support surfaces to bounded/sewn faces.
3. V0.7 adds a transition policy layer that changes modeling, UI, export, and mesh.
4. V0.7 changes default mesh exchange expectations.
5. V0.7 creates a new engineering review workflow around edge families and mesh
   quality, rather than only adding fields to the existing manifest.

V0.2 through V0.6 must remain loadable and historically truthful.

## 5. Core V0.7 Requirements

### 5.1 Bounded CAD Faces

Every exported STEP face must be bounded by topology.

For planar hub caps:

- `inner_hub_bottom_face` must export as a finite annular face;
- `hub_top_cap_face` must export as a finite annular face;
- the mounting bore must appear as an inner loop;
- no arbitrary `-10000..10000` support-plane faces may appear in accepted V0.7 STEP.

For blade and hub support surfaces:

- support surfaces must be bounded by outer trim loops;
- edge curves should be reused by adjacent faces where possible;
- face regions must map back to `surface_graph_id`.

### 5.2 Sewn Or Explicitly Accounted Shells

The exporter should attempt to sew faces into shells. The manifest must report:

```json
{
  "sewing_status": "passed",
  "shell_count": 1,
  "open_edge_count": 0,
  "failed_edge_ids": []
}
```

If sewing does not pass, the export must not be labeled as a completed trimmed/sewn B-Rep.
It may be saved as a diagnostic artifact with an explicit lower exactness label.

### 5.3 Edge Treatment Policy Layer

All designable adjacent surface intersections must be represented by stable edge
families and policies.

Initial treatment kinds:

```text
none | chamfer | fillet
```

Initial continuity targets:

```text
G0 for none/chamfer
G1 target for fillet
```

The policy shape is:

```json
{
  "policy_id": "blade_root_to_hub.default",
  "edge_family": "blade_root_to_hub",
  "enabled": true,
  "treatment": "fillet",
  "radius_mm": 8.0,
  "continuity": "G1",
  "applies_to": "all_pattern_instances",
  "overrides": []
}
```

### 5.4 Predictable Edge Families

V0.7 should define topology families rather than exposing every edge as a primary UI
control.

Blade edge families:

- `blade_leading_edge`
- `blade_trailing_edge`
- `blade_root_to_hub`
- `blade_tip_or_shroud`

Hub solid edge families:

- `hub_bottom_outer`
- `hub_top_outer`
- `mounting_bore_top`
- `mounting_bore_bottom`

Closed impeller hood/shroud edge families:

- `hood_inlet_lip`
- `hood_outlet_lip`
- `hood_outer_cap`
- `blade_tip_to_shroud`

V0.7 data should allow advanced per-edge or per-blade overrides, but the default UI
should operate at the family level.

### 5.5 Transition Surfaces Must Be Real Modeling Entities

For every enabled chamfer or fillet policy, the kernel must produce:

- one or more transition surfaces;
- trimmed adjacent main surfaces;
- updated surface adjacency;
- transition-specific `surface_graph_id` values;
- transition mesh regions;
- transition export face regions.

The transition must be visible in:

- frontend shaded view;
- frontend wire/mesh view;
- STL or preferred mesh export;
- STEP B-Rep export;
- manifest provenance.

### 5.6 Frontend Edge Treatment UI

The frontend should add an `Edge Treatment` panel.

Default mode:

- `Use default engineering edge treatment` toggle;
- one row per edge family;
- controls per row:
  - enabled switch;
  - segmented control: None / Chamfer / Fillet;
  - radius input;
  - status badge: OK / too large / unsupported / diagnostic only.

Advanced mode:

- expand a family;
- show affected surface ids and edge ids;
- allow per-blade overrides for blade-family edges;
- show generated transition surface ids;
- select a family to highlight it in the viewer.

The primary UI should remain dense and engineering-oriented. It should not become a
general CAD edge-picking interface.

### 5.7 Frontend Transition Display

The viewer must expose layers:

- `Transitions`;
- `Fillet surfaces`;
- `Chamfer surfaces`;
- `Transition mesh edges`;
- `Main faces`;
- `Solid context`;
- `Fluid boundary`.

Transitions should have high-contrast colors and remain visible by default. If a
transition is too small to see at whole-model scale, selecting the row in the edge
treatment panel should frame the camera to that region and highlight the adjacent
surfaces.

### 5.8 Mesh Inspection

`CFD360 mesh` must become a real mesh view, not only a metric panel.

Required viewer behavior:

- render triangle edges;
- allow shaded + mesh overlay;
- color triangles by patch group or quality metric;
- allow transition-region filtering;
- highlight high-aspect-ratio and degenerate triangles;
- show selected patch/family triangle counts.

Mesh manifest should include:

```json
{
  "mesh_type": "surface_triangles",
  "triangle_count": 0,
  "quality_metrics": {
    "min_area": 0.0,
    "max_area": 0.0,
    "max_aspect_ratio": 0.0
  },
  "transition_regions": [
    {
      "edge_family": "blade_root_to_hub",
      "transition_policy_id": "blade_root_to_hub.default",
      "surface_graph_id": "blade_0_root_fillet_surface",
      "triangle_start": 0,
      "triangle_count": 0
    }
  ]
}
```

### 5.9 Mesh Export Defaults

V0.7 should not make AP242 tessellated STEP the default mesh review artifact.

Recommended defaults:

- binary STL for broad compatibility;
- OBJ or PLY for mesh inspection with named groups if simple to implement;
- mesh manifest JSON for region provenance and quality metrics.

Optional diagnostic:

- AP242 tessellated STEP may remain available as `experimental_mesh_step`, labeled
  clearly as compatibility-limited.

### 5.10 CFD View Semantics

The current CFD full-360 view showing only a hub wall surface can be correct if the view
means fluid-boundary surfaces.

V0.7 must make this explicit:

- `CAD review`: full solid-context surface graph;
- `CFD boundary`: fluid-domain boundary patches only;
- `CFD mesh`: mesh overlay on fluid-domain boundary patches;
- `Solid context`: optional overlay in CFD views.

This avoids the misunderstanding that the solid hub disappeared.

## 6. Data Model

### 6.1 Transition Policy

Add a top-level manifest section:

```json
{
  "transition_policies": {
    "blade_root_to_hub.default": {
      "edge_family": "blade_root_to_hub",
      "enabled": true,
      "treatment": "fillet",
      "radius_mm": 8.0,
      "continuity": "G1",
      "applies_to": "all_pattern_instances",
      "maps_to_parameters": ["root_fillet_radius_mm"]
    }
  }
}
```

### 6.2 Edge Family Registry

Add a constructor-level registry:

```json
{
  "edge_families": {
    "blade_root_to_hub": {
      "scope": "blade_pattern",
      "adjacent_roles": ["blade_pressure", "blade_suction", "hub"],
      "default_treatment": "fillet",
      "default_radius_parameter": "root_fillet_radius_mm",
      "cfd_patch_group": "root_fillet_wall"
    }
  }
}
```

### 6.3 Surface Graph Edges

Each edge should include topology and policy metadata:

```json
{
  "id": "blade_0_root_to_hub_pressure_edge",
  "edge_family": "blade_root_to_hub",
  "surfaces": ["blade_0_pressure_surface", "hub_revolve_surface"],
  "transition_policy_id": "blade_root_to_hub.default",
  "transition_surface_ids": ["blade_0_root_fillet_surface"],
  "cad_edge": {
    "curve_type": "bspline_curve",
    "control_points": [],
    "surface_uv": {}
  }
}
```

### 6.4 Export Manifest

STEP manifest must include:

```json
{
  "export_exactness": "surface_graph_trimmed_brep_step",
  "bounded_face_count": 0,
  "sewing_status": "passed",
  "open_edge_count": 0,
  "face_regions": [],
  "transition_face_regions": []
}
```

If V0.7 exports a diagnostic unsewn artifact, use a lower label such as:

```text
surface_graph_bounded_unsewn_brep_step
```

Do not label diagnostic support-face output as `surface_graph_trimmed_brep_step`.

## 7. Backend Architecture

### 7.1 Transition Policy Resolver

Add a resolver that combines:

- DSL default policies;
- preset defaults;
- user parameter overrides;
- optional advanced override payloads.

The resolver outputs a normalized `transition_policies` map.

### 7.2 Kernel Transition Builder

The kernel should:

1. build base hub/blade/shroud surfaces;
2. enumerate edge families;
3. apply transition policies;
4. trim or shorten adjacent surfaces;
5. generate transition surfaces;
6. update adjacency and provenance.

V0.7 may start with deterministic family-level transitions and postpone arbitrary
per-edge overrides if tests and manifests prove the data shape supports them.

### 7.3 Bounded B-Rep Exporter

The exporter should:

1. create support surfaces;
2. create 3D curves and pcurves where available;
3. build wires;
4. create bounded faces;
5. sew faces;
6. validate topology;
7. write STEP;
8. write an exactness manifest.

For annular planes, V0.7 can use direct OCCT wire construction from inner and outer
circles. This is a mandatory early acceptance case because it directly addresses the
giant-plane screenshots.

### 7.4 Mesh Builder

The surface mesh builder should:

- consume the same bounded surface graph;
- refine transition regions by minimum samples across radius;
- compute triangle quality;
- emit region/provenance metadata;
- provide data suitable for frontend mesh overlay.

## 8. Frontend Architecture

### 8.1 Edge Treatment Panel

Add a panel driven by `manifest.edge_families` and `manifest.transition_policies`.

The panel sends a compact override payload:

```json
{
  "transition_overrides": {
    "blade_root_to_hub.default": {
      "enabled": true,
      "treatment": "fillet",
      "radius_mm": 10.0
    }
  }
}
```

### 8.2 Viewer Layers

The viewer should render:

- main surfaces;
- transition surfaces;
- boundary curves;
- mesh triangle edges;
- selected edge-family highlight.

The mesh overlay should be independent of the shaded/wireframe toggle. The user should
be able to view shaded surfaces with mesh edges overlaid.

### 8.3 CFD/Solid View Naming

Rename view semantics if needed:

- `CAD review`;
- `CFD boundary`;
- `CFD mesh`;
- `Feature debug`.

Add a solid-context toggle in CFD views rather than forcing all solid surfaces into the
CFD boundary view.

## 9. Acceptance Criteria

### 9.1 CAD Export

1. V0.7 open and closed STEP files can be re-imported by OCCT.
2. Re-imported bounding boxes are within expected impeller scale and do not include
   extreme support-plane dimensions.
3. STEP text contains bounded face topology for hub cap annuli.
4. No accepted V0.7 STEP export uses arbitrary `-10000..10000` support plane bounds.
5. `export_manifests.step.export_exactness` is only
   `surface_graph_trimmed_brep_step` when bounded face construction and validation pass.

### 9.2 Transition Modeling

1. Default blade root, leading edge, trailing edge, and tip transitions are visible.
2. Default hub top/bottom/bore edge treatments are visible when enabled.
3. Changing a family policy from `fillet` to `chamfer` changes frontend geometry,
   STEP faces, STL/mesh output, and manifest policy metadata.
4. Disabling a family removes its transition surfaces and updates adjacent regions.
5. Invalid radii fail validation with a specific policy id and edge family.

### 9.3 Mesh Inspection

1. `CFD mesh` view renders triangle edges.
2. The user can color by patch group or quality metric.
3. Transition-region triangles are selectable and traceable.
4. Mesh quality summary matches manifest counts.
5. Default mesh artifacts open in a common mesh viewer.

### 9.4 Version Lineage

1. V0.2 through V0.6 remain loadable.
2. V0.7 resources are additive.
3. V0.6 manifests retain honest support-face labels.
4. V0.7 evidence includes the user-provided V0.6 failure screenshots.

## 10. Non-Goals

V0.7 does not need to deliver:

- production-certified CAD geometry;
- full CFD volume mesh generation;
- solver deck generation;
- arbitrary mouse-pick editing of every edge in the frontend;
- generalized CAD healing for all invalid parameter combinations;
- CAM/manufacturing process features.

V0.7 should focus on the predictable impeller topology and the edge families listed in
this spec.

## 11. Open Questions For Implementation Planning

1. Which mesh exchange artifact should be the first default beyond STL: OBJ, PLY, or
   VTK/VTU?
2. Should V0.7 require sewing to pass for both open and closed reference presets, or is
   bounded unsewn B-Rep acceptable as an intermediate diagnostic output?
3. Should closed impeller hood/shroud transitions ship in the same V0.7 implementation
   plan as hub/blade transitions, or should they be a second V0.7 milestone?
4. Which third-party viewer should be used for acceptance screenshots?

## 12. Recommended Implementation Sequence

1. Add V0.7 resource line and transition policy schema.
2. Implement bounded annular plane export and tests that prove giant planes are gone.
3. Implement edge family registry and transition policy resolver.
4. Upgrade kernel transition surfaces to use policy ids and update adjacency.
5. Add frontend edge treatment panel and transition highlighting.
6. Add real mesh overlay and mesh-quality coloring.
7. Replace default mesh exchange with STL plus one additional broadly supported mesh
   format.
8. Add OCCT re-import, bbox, and topology validation tests.
9. Generate V0.7 evidence artifacts and screenshots.

## 13. Spec Self-Review

Completeness scan: no incomplete markers remain.

Internal consistency: V0.7 exactness is only granted after bounded/sewn validation;
diagnostic artifacts retain lower exactness labels.

Scope check: This spec is large but coherent because transition policy, bounded export,
frontend transition display, and mesh inspection must share one topology model. The
implementation plan should split the work into independently reviewable tasks.

Ambiguity check: The frontend approach is family-level by default, with advanced
overrides supported by data model but not required as a primary UI.
