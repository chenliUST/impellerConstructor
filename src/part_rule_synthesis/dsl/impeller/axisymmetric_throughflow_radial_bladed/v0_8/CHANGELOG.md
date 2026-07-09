# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.8 Changelog

Date: 2026-07-03

Supersedes: `v0_7`

## Changes

1. Added V0.8 open and closed reference presets with the
   `transition_resolved_bounded_brep` export contract.
2. Routed V0.8 generated geometry through the transition resolver so enabled fillet
   and chamfer policies produce resolved transition patches and adjacent trimming
   metadata instead of provenance-field changes alone.
3. Added transition geometry primitives for blade root, blade edge, hub, bore, hood,
   and shroud-related transition families, with explicit failure records for infeasible
   required transitions.
4. Added transition-aware surface mesh generation and mesh quality/provenance regions
   for resolved transition surfaces.
5. Routed V0.8 STL, OBJ, STEP, export manifests, simulation manifests, and frontend
   inspection data through the same transition-resolved `surface_graph`.
6. Added bounded B-Rep validation contracts that fail explicitly when required V0.8
   transition validation is infeasible or stale.
7. Exposed frontend mesh inspection controls for V0.8 transition regions and preserved
   wireframe overlay visibility behavior.

## Limitations

- V0.8 exports a bounded, unsewn B-Rep shell. It does not claim a watertight sewn solid.
- Fillet and chamfer patches are sampled transition geometry, not manufacturing-certified
  exact CAD feature reconstruction.
- STEP sewing, CAD healing, production meshing adapters, and solver-ready CFD volume
  meshes remain downstream work.
