# Impeller V0.8 Transition-Resolved Geometry Evidence

Date: 2026-07-03

## Root Cause

V0.7 carried edge-family transition policies through manifests, mesh regions, OBJ
groups, and bounded B-Rep face provenance, but those policies could still change
metadata without changing the transition surface grids. A radius or chamfer override
could update role, policy, and provenance fields while the sampled blade transition
`uv_grid` stayed effectively unchanged.

## Fix

V0.8 routes the base `surface_graph` through a transition resolver before downstream
meshing and export. Enabled fillet and chamfer policies trim adjacent main-surface
metadata, generate sampled transition patches for supported edge families, and publish
the same resolved graph into the frontend, STL, OBJ, STEP, and manifest paths.

The implemented path is:

```text
base surface_graph
-> transition resolver
-> resolved transition surfaces and trimming metadata
-> transition-aware surface mesh
-> STL/OBJ/STEP/export manifests/frontend inspection
```

This makes V0.8 a topology-changing transition geometry line rather than an additive
resource-metadata line.

## Ontology Insight

The transition ontology now has a closed feedback path. A reviewer can trace geometry
quality feedback from:

```text
transition_policy_id -> edge_family -> transition surface -> mesh/STEP face region -> DSL override
```

That trace is the practical bridge from expert inspection of an exported mesh or STEP
face back to the DSL treatment that produced it.

## Validation Evidence

Focused verification recorded for this implementation:

- Backend bounded B-Rep validation tests: 34 passed.
- V0.8 workflow export test passed for transition-resolved graph, transition-aware mesh,
  and routed STL/OBJ/STEP manifests.
- Frontend test suite: 82/82 passed.
- Frontend production build passed.

Full repository verification remains the controller's follow-up responsibility because
this task updates the documentation and evidence record only.

## Remaining Limitations

- V0.8 still exports a bounded, unsewn B-Rep shell; it is not a watertight sewn solid.
- Fillet and chamfer patches are sampled transition geometry, not manufacturing-certified
  exact CAD feature reconstruction.
- Solver-ready CFD volume mesh generation is not implemented.
