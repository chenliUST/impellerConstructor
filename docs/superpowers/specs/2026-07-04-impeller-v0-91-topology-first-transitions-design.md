# Impeller V0.91 Topology-First Transitions Design

Date: 2026-07-04

Status: Draft for implementation

Supersedes: V0.9 transition validation implementation where transition patches are
sampled strips without shared topology.

## 1. Version Thesis

V0.91 is the completion patch for the V0.9 kernel validity milestone.

V0.9 introduced validation reports, double-sided root transition surfaces, and
transition-aware export gates. The current implementation still fails the engineering
meaning of those gates: fillet strips can be visibly under-resolved or bend in the
wrong direction, chamfer strips can be placed without trimming the retained model, and
the mesh remains non-manifold because neighboring surfaces do not share edge nodes.

V0.91 therefore changes the transition implementation from surface-strip generation to
topology-first patch construction:

```text
shared edge topology -> retained-side section solver -> transition and corner patches
-> shared-node mesh -> validation -> export and frontend review
```

This is not V1.0. It does not claim industrial exact solid modeling. It is a required
repair of the V0.9 reliability promise.

## 2. Failure Evidence

Local inspection of `radial_open_reference_v0_9` shows that the visible transition
surfaces exist but are not valid topology:

- `blade_0_pressure_root_transition_surface` uses a `41 x 7` grid, while leading and
  trailing edge transition strips use `17 x 5` grids. Several fillet cross-sections
  therefore have too few points to review a controlled radius.
- The root/leading junction has a measured endpoint gap of about `0.334 mm`.
- The tip/leading junction has a measured endpoint gap of about `0.100 mm`.
- Mesh edge incidence on the generated transition-aware mesh reports roughly:
  - `free_edges = 1032`
  - `nonmanifold_edges = 3808`
- The current validation report can still return `PASS`, so the validation gate does
  not test the failure class visible in the frontend screenshots.

The root cause is in the implementation, not only in the renderer:

- `_fillet_section_between_trim_points()` builds a section by linear interpolation plus
  an XY radial sine bump. It does not compute a circle, does not use adjacent-surface
  normals/tangents, and does not enforce the requested fillet radius.
- Chamfer sections are straight connections between trim points, but the trim points
  are not derived from retained material side directions.
- Root, leading, trailing, and tip transitions are solved independently, so their
  endpoints do not necessarily meet at corners.
- Mesh generation triangulates each surface grid independently. It can deduplicate
  coordinates for OBJ output, but it does not create a shared topological vertex
  lattice, so watertightness and manifoldness are not guaranteed.

## 3. Public Reference Baseline

V0.91 uses public CAD/mesh practice as constraints, not as an exact implementation
dependency:

- Open CASCADE fillet and chamfer APIs model edge treatments as topology operations on
  edges and adjacent faces, not as unrelated display strips:
  - <https://dev.opencascade.org/doc/refman/html/class_b_rep_fillet_a_p_i___make_fillet.html>
  - <https://dev.opencascade.org/doc/refman/html/class_b_rep_fillet_a_p_i___make_chamfer.html>
- Open CASCADE validity and sewing tools expose the relevant checks for this project:
  valid shape analysis, free edges, and multiple edges:
  - <https://dev.opencascade.org/doc/refman/html/class_b_rep_check___analyzer.html>
  - <https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___sewing.html>
- Gmsh describes CAD geometry as boundary representation and supports transfinite
  curve/surface workflows where structured surface meshes share boundary nodes:
  - <https://gmsh.info/doc/texinfo/>

The project does not need to fully embed OCCT filleting in V0.91. It must, however,
adopt the same core invariant: an edge treatment is attached to shared topology and
the generated mesh reuses boundary nodes.

## 4. Goals

1. Add a V0.91 resource line that keeps V0.2 through V0.9 loadable.
2. Replace V0.9's radial-bump fillet with a local section-frame fillet solver.
3. Replace direction-ambiguous chamfer strips with retained-side chamfer sections.
4. Generate corner transition patches where edge treatments meet.
5. Introduce shared topological nodes for all transition and adjacent-surface patch
   boundaries.
6. Generate STL/OBJ/mesh review artifacts from a unified patch complex, not from
   independent surface triangle soups.
7. Require manifold and watertight mesh validation for default V0.91 golden cases.
8. Block export if transition geometry, shared nodes, corner closure, or manifoldness
   gates fail.
9. Show the same V0.91 patch complex in the frontend shaded, wireframe, and mesh views.
10. Preserve V0.9 artifacts as historical evidence of the failed strip-based approach.

## 5. Non-Goals

1. No V1.0 taxonomy expansion.
2. No arbitrary CAD edge editor.
3. No solver-ready CFD volume mesh.
4. No automatic expert feedback rule patching.
5. No claim that STEP is an exact sewn industrial solid unless OCCT reimport and shape
   validity prove it.
6. No silent fallback to V0.9 strip transitions when V0.91 validation fails.

## 6. V0.91 Geometry Contract

### 6.1 Shared Patch Complex

V0.91 must create a machine-readable `transition_patch_complex` inside the
`surface_graph` or manifest. The complex must include:

- `nodes`: stable shared vertex ids with 3D coordinates.
- `edges`: ordered node ids, role, physical boundary status, and adjacent patch ids.
- `patches`: surface id, role, edge family, treatment, node grid, and source rule.
- `edge_treatment_sites`: one record per active fillet/chamfer family instance.
- `corner_sites`: one record for each place where two or more edge treatments meet.

All transition patch boundaries and adjacent trimmed surface boundaries must reference
the same edge ids and node ids. Coordinate equality is not sufficient for V0.91
success.

### 6.2 Retained-Side Section Solver

At each edge station, the solver must compute:

- edge point `P(s)`;
- edge tangent `T(s)`;
- adjacent surface retained-side directions `D1(s)` and `D2(s)`, both perpendicular to
  `T(s)`;
- local section plane with normal `T(s)`;
- requested treatment parameters from the active transition policy.

For fillet:

- use a circular section in the local section plane;
- choose the convexity side from the edge family's material-side contract;
- use at least 9 section samples by default;
- increase section samples when the included angle or radius requires more detail;
- record `section_sample_count`, `included_angle_deg`, `radius_error_mm`,
  `convexity_sign`, and `g1_tangent_error_deg`.

For chamfer:

- compute trim points by moving along retained-side directions on each adjacent face;
- connect those trim points with a straight section;
- verify that the chamfer removes the edge region rather than adding an external strip;
- record `section_linearity_error_mm` and `direction_sign`.

### 6.3 Corner Patches

V0.91 must create explicit corner patches for transition intersections, including at
least:

- root-leading pressure side;
- root-leading suction side;
- root-trailing pressure side;
- root-trailing suction side;
- tip-leading;
- tip-trailing;
- hood/shroud transition corners for closed presets where the topology requires them.

Corner patches may use Coons or transfinite interpolation in V0.91, provided that:

- each boundary curve is an existing shared edge from a transition or trimmed primary
  surface;
- all boundary node ids are reused exactly;
- the patch is oriented consistently with adjacent patches;
- the patch has non-degenerate quads/triangles;
- validation records corner gap and twist metrics.

### 6.4 Trim Semantics

V0.91 trim is not allowed to be display-only metadata. When a transition consumes a
region of a blade, hub, shroud, bore, or cap surface:

- the retained primary surface boundary must move to the transition boundary;
- the removed cells must not appear in mesh/STL/OBJ output;
- the removed region must be recorded in `trim_exclusion_regions`;
- adjacent transition boundaries must share node ids with the retained primary surface.

### 6.5 Manifold And Watertight Mesh

For default V0.91 golden cases, the review mesh must be a single shared-node mesh with:

- `free_edge_count == 0`;
- `nonmanifold_edge_count == 0`;
- every non-boundary edge incident to exactly 2 faces;
- no duplicate faces;
- no zero-area faces;
- consistent triangle winding by connected component;
- node identity shared across all patch boundaries.

If a future case intentionally creates an open boundary, that boundary must be declared
in `declared_open_boundary_ids`. Default open and closed impeller reference presets do
not get this exception.

## 7. Manifest Requirements

V0.91 manifests must include:

```json
{
  "dsl_version": "0.91",
  "geometry_version": "0.91",
  "transition_geometry_status": "topology_first_validated_transition_graph",
  "mesh_strategy": "shared_node_transition_patch_mesh",
  "geometry_validation_status": "PASS",
  "transition_patch_complex_id": "radial_open_reference_v0_91-run-id.patch_complex",
  "transition_topology_report": {
    "patch_count": 0,
    "transition_patch_count": 0,
    "corner_patch_count": 0,
    "shared_edge_count": 0,
    "shared_node_count": 0,
    "max_corner_gap_mm": 0.0,
    "max_boundary_gap_mm": 0.0,
    "max_g1_tangent_error_deg": 0.0
  },
  "mesh_manifoldness_report": {
    "vertex_count": 0,
    "face_count": 0,
    "free_edge_count": 0,
    "nonmanifold_edge_count": 0,
    "duplicate_face_count": 0,
    "zero_area_face_count": 0,
    "declared_open_boundary_ids": []
  }
}
```

`geometry_validation_status` must be `FAIL` if any required V0.91 report field is
missing or if any blocking count is nonzero.

## 8. Export Requirements

STL/OBJ:

- must be generated from the shared-node patch mesh;
- must include transition and corner patch regions;
- must include manifoldness report in export manifests;
- must fail instead of falling back to V0.9 independent triangulation.

STEP:

- may remain review-grade bounded B-Rep in V0.91;
- must include transition and corner patches;
- must not claim watertight sewn exact solid unless OCCT reimport and shape validation
  prove it;
- must fail if the patch complex does not pass transition validation.

Frontend:

- shaded, wireframe, and mesh views must render the V0.91 patch complex;
- transition and corner patches must be visible without depending on polygon-offset
  tricks to hide overlapped old surfaces;
- detail panels must show topology, manifoldness, and transition validation failures.

## 9. Validation Gates

V0.91 blocks export on any of these failures:

- fillet section sample count below the configured minimum;
- fillet radius error over tolerance;
- fillet convexity sign opposite the edge-family contract;
- chamfer direction sign opposite the retained-side contract;
- chamfer section not linear within tolerance;
- adjacent primary surface not actually trimmed;
- transition boundary and adjacent primary boundary do not share node ids;
- required corner patch missing;
- corner patch boundary gap above tolerance;
- free edges in default golden-case mesh;
- non-manifold edges;
- duplicate or zero-area faces;
- unsupported transition policy silently ignored.

Default tolerances:

- `max_boundary_gap_mm <= 1e-6` for shared node identity checks;
- `max_corner_gap_mm <= 1e-5`;
- `radius_max_error_mm <= max(0.25, 0.05 * requested_radius_mm)`;
- `g1_tangent_max_error_deg <= 15`;
- `section_linearity_max_error_mm <= 1e-5`;
- `zero_area_face_count == 0`;
- `free_edge_count == 0`;
- `nonmanifold_edge_count == 0`.

## 10. Golden Cases

V0.91 inherits the V0.9 golden registry and adds explicit transition stress cases:

1. `v091_radial_open_default_topology_first`
2. `v091_radial_closed_default_topology_first`
3. `v091_high_blade_count_root_corner`
4. `v091_large_root_fillet_feasible_limit`
5. `v091_chamfered_root_and_bore_direction`
6. `v091_small_radius_high_resolution_fillet`
7. `v091_negative_inverted_fillet_direction`
8. `v091_negative_missing_corner_patch`
9. `v091_negative_nonmanifold_shared_edge`
10. `v091_negative_untrimmed_adjacent_surface`

Positive cases must export STL/OBJ/STEP review packages. Negative cases must fail
before export and record the exact blocking reason.

## 11. Evidence Package

The V0.91 evidence folder should be:

```text
docs/evidence/2026-07-04-impeller-v0-91-topology-first-transitions/
```

Required text/JSON evidence:

- root cause note referencing the V0.9 screenshots and measured edge-incidence report;
- golden batch summary;
- mesh manifoldness summary for open and closed default presets;
- transition topology report for representative blades;
- export manifest summaries;
- expert issue linkage schema.

Large generated STL/STEP/OBJ files stay in `Model Output/`.

## 12. Acceptance Criteria

V0.91 is complete only when:

1. V0.91 presets load independently of V0.9.
2. Default open and closed V0.91 runs produce `geometry_validation_status = PASS`.
3. Default open and closed V0.91 mesh reports have:
   - `free_edge_count == 0`;
   - `nonmanifold_edge_count == 0`;
   - `zero_area_face_count == 0`.
4. Every active transition policy produces transition patches and required corner
   patches.
5. The root-leading and root-trailing measured gaps are at or below tolerance.
6. Fillet section reports prove controlled radius, adequate sample count, and correct
   convexity side.
7. Chamfer reports prove correct retained-side direction and adjacent-surface trimming.
8. STL/OBJ exports come from the shared-node mesh.
9. STEP export includes transition and corner patches and does not silently fall back.
10. Frontend shaded, wireframe, and mesh views show the same V0.91 patch complex.
11. V0.2 through V0.9 remain loadable as historical baselines.
12. Verification commands and golden batch regression pass.

## 13. Deferred Work

The following remain post-V0.91:

- exact analytic fillet reconstruction from feature rules;
- watertight sewn OCCT solid with full p-curves and same-parameter edges;
- production CFD volume meshing;
- automatic expert feedback back-propagation into DSL rules;
- arbitrary topology interactive editing UI.
