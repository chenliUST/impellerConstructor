# V0.6 Changelog Draft

Date: 2026-07-01

Status: planning draft, not implemented

## Planned Motivation

V0.5 made exported STL/STEP files faithful to `surface_graph`, but the STEP file is
still a tessellated mesh representation. Third-party CAD inspection requires a more
general B-Rep export path where freeform surfaces are represented as NURBS/analytic
support surfaces and trimmed by topological boundary wires.

## Planned Changes

1. Add `v0_6` DSL resources copied from V0.5 only after the implementation plan is
   approved.
2. Add `surface_graph_trimmed_brep` export contract.
3. Add `cad_surface` payloads for exportable surfaces.
4. Add `cad_edge` payloads for trim boundaries and adjacency.
5. Add OCCT/CadQuery/OCP based STEP writer for trimmed NURBS/analytic B-Rep faces.
6. Preserve V0.5 STL and mesh STEP as separate compatibility/debug artifacts.
7. Add default output copies under project `Model Output/`.
8. Add frontend export choices with correct default extensions.
9. Add CFD360 mesh inspection view and mesh-quality metrics.
10. Promote blade root/edge rounding to explicit interactive fillet/blend features.

## Planned Exactness Labels

```text
surface_graph_trimmed_nurbs_step
surface_graph_sampled_mesh
surface_graph_mesh_step
```

## Non-Claims

Until implementation and third-party evidence exist, V0.6 does not claim:

- production-ready manufacturing CAD;
- solver-ready CFD volume mesh;
- universal CAD import compatibility;
- exact variable-radius fillets across all parameter values.

## Evidence Requirements

Before tagging or announcing V0.6:

1. Run repository fast and full verification.
2. Run version lineage verification.
3. Generate open and closed V0.6 artifacts.
4. Record B-Rep STEP import evidence.
5. Record mesh-view screenshots or equivalent bounded evidence.
6. Record fillet/blend visibility evidence.
