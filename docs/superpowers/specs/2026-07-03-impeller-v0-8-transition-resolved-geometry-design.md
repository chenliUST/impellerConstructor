# Impeller V0.8 Transition-Resolved Geometry Design

Date: 2026-07-03

Status: Draft approved for implementation planning

Supersedes: V0.7 bounded transitions and mesh design

## Summary

V0.8 is the first impeller constructor version where enabled fillet and chamfer policies
change the actual generated geometry rather than only changing transition metadata. The
current V0.7 pipeline can emit transition surfaces, export them to STL/OBJ/STEP, and
trace them through manifests, but blade transition surfaces are still derived from
existing blade closure strips. Changing blade-root fillet radius or switching fillet to
chamfer updates role and policy metadata, but the blade transition `uv_grid` remains
unchanged.

V0.8 changes the contract:

```text
base surface_graph
-> transition geometry resolver
-> trimmed, transition-resolved surface_graph
-> transition-aware surface mesh
-> frontend / STL / OBJ / STEP / manifests
```

The target is a topology-first sampled B-Rep shell. Adjacent main surfaces are trimmed
back from treated edges, and real transition patches are inserted into the resulting
gap. The STEP output remains a bounded, unsewn surface shell for this version; watertight
sewing and manufacturing CAD certification are not part of V0.8.

## Background And Root Cause

The user reported that fillet and chamfer are still not visible in the frontend and STL
output. Investigation of a current V0.7 run showed:

- `surface_graph` contains transition surfaces.
- STL triangle regions include those transition surfaces.
- Frontend layer logic can identify transition surfaces.
- The failure is not primarily missing export or missing frontend layer support.

The root cause is semantic: V0.7 records transition policy evidence but does not fully
construct transition geometry for blade edges. For example, `blade_root_to_hub.default`
can be changed from fillet radius 8 mm to fillet radius 20 mm, or to chamfer radius
20 mm, while `blade_0_root_transition_surface.uv_grid` remains identical. The existing
surface is a renamed ruled closure strip, not a trimmed hub-to-blade fillet or chamfer.

Hub and bore transition bands are more geometry-driven than blade transitions, but even
there the geometry is a sampled band approximation and does not consistently distinguish
fillet circular arc behavior from chamfer linear behavior.

## Goals

1. Make V0.8 fillet and chamfer policies geometry-producing rules, not metadata-only
   annotations.
2. Preserve `surface_graph` as the central ontology and evidence interface.
3. Trim adjacent main surfaces back from treated edges.
4. Insert transition patches that occupy the trimmed region.
5. Support predictable impeller topology families rather than a freeform edge editor.
6. Generate frontend geometry, STL, OBJ, STEP, and mesh manifests from the same
   transition-resolved `surface_graph`.
7. Make transition-aware mesh quality inspectable and testable.
8. Keep V0.5, V0.6, and V0.7 loadable with their historical semantics.

## Non-Goals

1. V0.8 does not promise a watertight sewn solid.
2. V0.8 does not promise exact analytic CAD feature reconstruction for every surface.
3. V0.8 does not introduce a fully interactive arbitrary-edge CAD editor.
4. V0.8 does not produce solver-ready CFD volume meshes.
5. V0.8 does not rewrite historical V0.7 evidence or labels.

## Version Contract

V0.8 should be an additive DSL version line:

```text
src/part_rule_synthesis/dsl/impeller/
  axisymmetric_throughflow_radial_bladed/
    v0_8/
```

V0.8 presets should start from V0.7 defaults and be renamed:

- `radial_open_reference_v0_8`
- `radial_closed_reference_v0_8`

The V0.8 manifest must expose:

```json
{
  "geometry_version": "0.8",
  "transition_geometry_status": "resolved_trimmed_surface_graph",
  "mesh_strategy": "transition_aware_surface_mesh",
  "step_exactness": "transition_resolved_bounded_unsewn_brep_step",
  "target_step_exactness": "transition_resolved_trimmed_brep_step",
  "unsupported_transition_count": 0
}
```

V0.7 can continue to say that transition policy regions exist, but it must not be
retroactively labeled as transition-resolved geometry.

## Topology Families

V0.8 treats impeller edges through predictable topology families. The initial supported
families are:

- `blade_root_to_hub`
- `blade_leading_edge`
- `blade_trailing_edge`
- `blade_tip_or_shroud`
- `blade_tip_to_shroud` for closed impellers
- `hub_top_outer`
- `hub_bottom_outer`
- `mounting_bore_top`
- `mounting_bore_bottom`
- `hood_inlet_lip`
- `hood_outlet_lip`

Each family supports:

- `none`
- `chamfer`
- `fillet`

Each enabled treatment has:

- stable `edge_treatment_site_id`
- `edge_family`
- adjacent surface ids
- boundary curve ids
- `transition_policy_id`
- `treatment`
- `radius_mm`
- DSL variable provenance
- generated transition surface ids
- generated mesh region ids
- export face or triangle region ids

## Geometry Semantics

### Fillet

Fillet means an equal-radius circular arc transition in the local normal section. The
resolver should approximate G1 tangency between adjacent surfaces and the fillet patch.

For each station along the edge:

1. Estimate edge tangent.
2. Estimate adjacent surface normals.
3. Build a local cross-section plane normal to the edge tangent.
4. Compute feasible tangent points for the requested radius.
5. Sample the circular arc between tangent points.
6. Sweep those sampled sections along the edge.

The sampled fillet surface must store quality metrics:

- `requested_radius_mm`
- `effective_radius_mm`
- `arc_sample_count`
- `fit_max_radius_error_mm`
- `fit_rms_radius_error_mm`
- `tangent_continuity_error_deg`

### Chamfer

Chamfer means a straight-line ruled transition between two trimmed boundary curves.
For each station along the edge:

1. Compute trim points on both adjacent surfaces.
2. Connect trim points with a straight section.
3. Sweep those sections along the edge.

The sampled chamfer surface must store quality metrics:

- `requested_radius_mm`
- `section_linearity_max_error_mm`
- `section_planarity_max_error_mm`
- `chamfer_width_mm`

### None

`none` means no transition surface is created. Adjacent main surfaces should preserve
the sharp boundary behavior for that family.

## Transition Geometry Resolver

Introduce a dedicated resolver module, for example:

```text
src/part_rule_synthesis/impeller_transition_geometry.py
```

The resolver should be invoked after the base surface graph is constructed and before
export or simulation manifests are built.

Inputs:

- base `surface_graph`
- constructor facets
- edge families
- transition policies
- normalized DSL parameters
- geometry stage

Outputs:

- transition-resolved `surface_graph`
- `edge_treatment_sites`
- `transition_resolution_manifest`
- quality checks

The resolver owns these responsibilities:

1. Discover supported edge treatment sites.
2. Resolve effective policy per site.
3. Compute trim boundaries.
4. Resample adjacent main surfaces against trim boundaries.
5. Generate transition surfaces.
6. Validate boundary compatibility.
7. Attach provenance and quality metrics.

The kernel should no longer build blade transition surfaces by renaming existing closure
strips when V0.8 transition policies are active.

## Main Surface Trim-Back

The defining V0.8 rule is:

```text
enabled transition = adjacent main surfaces retreat + transition patch fills the gap
```

A run is not V0.8-compliant if:

- an enabled transition surface is present but adjacent main surfaces still occupy the
  original sharp edge;
- changing radius changes only metadata;
- switching `fillet` to `chamfer` changes only role names;
- STL or frontend output contains old closure-strip geometry masquerading as fillet.

The resolver must update or replace the affected main surfaces. The exact internal
representation can stay sampled, but the output `uv_grid` for affected main surfaces
must reflect the trimmed boundary.

## Transition-Aware Mesh

V0.8 mesh generation must consider transition topology. It cannot remain a blind
per-surface quad split.

The mesher should run on the transition-resolved surface graph and should produce:

- STL geometry
- OBJ geometry
- frontend mesh overlay
- `cfd_surface_mesh` manifest
- transition quality diagnostics

### Shared Boundary Sampling

If two adjacent regions share a trim boundary, both regions must use the same boundary
sample points. This applies to:

- blade pressure or suction surface against leading/trailing/root/tip transition;
- hub surface against blade-root transition;
- shroud or hood surface against tip/shroud transition;
- bore or cap faces against bore chamfers;
- hub cap or shell against hub outer transitions.

Boundary mismatch should be a failed quality check, not a warning.

### Transition Refinement

Transition surfaces need local refinement rules:

- fillet arc direction should use at least 5 to 9 samples, depending on radius and
  local angle;
- smaller radius and higher curvature should produce shorter local edges;
- chamfer may use fewer cross-section samples, but shared boundary sampling is still
  mandatory;
- transition strips must avoid highly skewed triangles where feasible.

### Mesh Manifest

Each transition mesh region must include:

```json
{
  "surface_graph_id": "blade_0_root_transition_surface",
  "edge_treatment_site_id": "blade_0.root_to_hub",
  "edge_family": "blade_root_to_hub",
  "transition_policy_id": "blade_root_to_hub.default",
  "treatment": "fillet",
  "radius_mm": 8.0,
  "triangle_start": 0,
  "triangle_count": 0,
  "quality": {
    "max_aspect_ratio": 0.0,
    "min_edge_length_mm": 0.0,
    "max_edge_length_mm": 0.0,
    "boundary_mismatch_max_mm": 0.0,
    "arc_deviation_max_mm": 0.0
  }
}
```

Quality gates:

- no degenerate transition triangles;
- no missing transition regions for enabled supported sites;
- no boundary sampling mismatch above tolerance;
- bounded aspect ratio threshold;
- bounded fillet arc deviation;
- bounded chamfer planarity or linearity deviation.

## STEP Export

V0.8 STEP output should use the existing bounded face shell direction, but source data
must be the transition-resolved `surface_graph`.

Export exactness:

```text
transition_resolved_bounded_unsewn_brep_step
```

Target exactness:

```text
transition_resolved_trimmed_brep_step
```

Each STEP face region must include:

- `surface_graph_id`
- `feature_id`
- `role`
- `kind`
- `edge_treatment_site_id` when applicable
- `edge_family` when applicable
- `transition_policy_id` when applicable
- `treatment` when applicable
- `radius_mm` when applicable
- fitting quality metrics

The exporter must fail rather than silently omitting enabled required transitions.

## STL And OBJ Export

STL and OBJ must use the transition-aware mesh, not the legacy per-surface exporter.

The outputs must agree with the mesh manifest:

- binary STL triangle count equals manifest triangle count;
- OBJ group ids match surface or transition region ids;
- transition triangle regions exist for every enabled supported transition site;
- triangle region provenance points back to edge policy and DSL variables.

## Frontend Design

The frontend should keep predictable topology-family controls rather than exposing a
general CAD edge picker.

The edge treatment panel should group controls as:

- Blade edges
- Hub edges
- Bore edges
- Hood and shroud edges

Each row should expose:

- enable toggle;
- treatment selector: `none`, `chamfer`, `fillet`;
- radius input or slider;
- status badge: `resolved`, `disabled`, `unsupported`, `radius too large`, or
  `geometry failure`;
- click-to-highlight behavior for related surfaces and mesh regions.

CAD review view:

- shows transition-resolved shaded geometry;
- transition surfaces should have visible default colors;
- selection should isolate transition patches and adjacent trimmed main faces.

CFD360 mesh view:

- shows triangle edges;
- highlights transition mesh regions;
- supports filtering by edge family;
- shows mesh quality metrics, including worst aspect ratio, minimum edge length,
  boundary mismatch, and fillet/chamfer deviation errors.

If a transition fails, the frontend should locate the issue in the edge treatment panel
and show the failing family, radius, reason, and suggested maximum radius when known.

## Failure Policy

Default enabled transitions are required for V0.8 reference presets. If a required
default transition cannot be generated, the run should fail geometry validation and
must not emit a successful V0.8 manifest.

Valid failure reasons include:

- radius exceeds local feasible limit;
- adjacent surface normals are degenerate;
- edge tangent is degenerate;
- trim-back would invert or self-intersect a surface;
- shared boundary sampling cannot be matched;
- transition mesh quality is below threshold.

The manifest should include:

```json
{
  "transition_failures": [
    {
      "edge_treatment_site_id": "blade_0.root_to_hub",
      "edge_family": "blade_root_to_hub",
      "transition_policy_id": "blade_root_to_hub.default",
      "requested_radius_mm": 100.0,
      "reason": "radius_exceeds_local_feasible_limit",
      "suggested_max_radius_mm": 12.5
    }
  ]
}
```

User-disabled transitions are not failures.

## Tests

### Unit Tests

Add tests for transition geometry, not only transition metadata.

Required tests:

1. Changing `blade_root_to_hub.default.radius_mm` changes root transition `uv_grid`.
2. Changing `blade_root_to_hub.default.treatment` from `fillet` to `chamfer` changes
   root transition `uv_grid`.
3. Blade fillet cross-sections fit a circle within tolerance.
4. Blade chamfer cross-sections fit a line or plane within tolerance.
5. Adjacent main surfaces retreat from the original sharp boundary when transition is
   enabled.
6. Disabling a transition removes the transition surface and restores sharp boundary
   behavior.
7. Hub, bore, hood, and shroud transition families obey the same geometry-change tests.
8. Unsupported or infeasible transitions fail explicitly.

### Mesh Tests

Required tests:

1. Transition-aware mesh has one transition region per enabled supported site.
2. Adjacent main surface and transition surface share boundary sample points.
3. No transition region contains degenerate triangles.
4. Mesh manifest reports local transition quality metrics.
5. Fillet arc deviation and chamfer linearity deviation pass thresholds.
6. STL triangle count equals mesh manifest triangle count.
7. OBJ groups include transition surface groups with provenance.

### STEP Tests

Required tests:

1. V0.8 open and closed presets export STEP from transition-resolved surface graph.
2. STEP reimport face count equals resolved surface count.
3. STEP face regions include transition provenance.
4. STEP contains B-spline faces for freeform transition patches.
5. STEP export fails if an enabled required transition is missing or unsupported.

### Workflow Tests

Required tests:

1. `radial_open_reference_v0_8` generates resolved transitions by default.
2. `radial_closed_reference_v0_8` generates resolved transitions by default.
3. Default open and closed STL/OBJ/STEP include blade root, leading, trailing, tip,
   hub, and bore transition regions.
4. Closed preset includes hood/shroud transition regions when applicable.
5. Parameter overrides update frontend manifest, STL mesh regions, OBJ groups, and
   STEP face regions consistently.
6. V0.5, V0.6, and V0.7 presets still load with historical semantics.

## Acceptance Criteria

V0.8 is acceptable when:

1. Default open and closed V0.8 presets show visible blade-root and blade-edge fillets
   in the frontend CAD review view.
2. Changing blade-root radius changes the generated `uv_grid`, STL triangles, mesh
   manifest, and STEP face geometry.
3. Changing blade-root treatment from fillet to chamfer changes generated geometry.
4. Transition-aware mesh view highlights transition regions and reports quality metrics.
5. STL and OBJ include transition regions with nonzero triangle counts.
6. STEP reimport succeeds with all resolved faces present.
7. Enabled default transition failures are explicit and block successful V0.8 export.
8. Historical versions remain loadable and are not relabeled as V0.8.

## Evidence To Record

Create a V0.8 evidence folder, for example:

```text
docs/evidence/2026-07-03-impeller-v0-8-transition-resolved-geometry/
```

Record:

1. V0.7 diagnosis showing blade transition `uv_grid` does not change under radius or
   treatment changes.
2. V0.8 before/after digest showing radius and treatment changes alter `uv_grid`.
3. Frontend screenshots of CAD review transition surfaces.
4. Frontend screenshots of CFD360 mesh transition quality view.
5. STL/OBJ manifest excerpts proving transition mesh regions.
6. STEP manifest excerpts proving transition face regions.
7. Third-party CAD screenshots when available.
8. Ontology insight: edge treatment evolves from annotation to topology-changing
   construction rule.

## Risks And Mitigations

### Risk: Robust Trim-Back Is Hard On Arbitrary Freeform Blades

Mitigation: V0.8 only promises predictable impeller topology families. The resolver
should use family-specific algorithms and fail explicitly when local geometry is
infeasible.

### Risk: Surface Sampling Mismatch Creates Mesh Cracks

Mitigation: centralize shared boundary sampling in the transition-aware mesher and
make boundary mismatch a quality gate.

### Risk: Fillet Approximation Is Mistaken For Exact CAD Fillet

Mitigation: manifest exactness must say sampled transition-resolved B-Rep shell. STEP
target exactness can point to future trimmed/sewn B-Rep, but V0.8 should not claim
solid certification.

### Risk: Large Implementation Blast Radius

Mitigation: add V0.8 as an additive version line. Keep V0.7 paths intact. Implement
family by family, beginning with blade root and leading/trailing edges, but do not mark
V0.8 complete until all default supported families pass.

## Open Engineering Notes

Implementation planning should decide exact module names and APIs, but the boundary
should remain clear:

- kernel builds base surface graph;
- transition resolver mutates or replaces affected surfaces;
- mesher consumes only resolved graph;
- exporters consume resolved graph or resolved mesh;
- frontend displays manifest status and resolved graph.

The key invariant is simple:

```text
If an edge treatment is enabled and supported, radius and treatment must affect geometry.
```

