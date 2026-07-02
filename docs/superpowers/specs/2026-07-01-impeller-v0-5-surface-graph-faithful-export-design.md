# Impeller v0.5 Surface-Graph-Faithful Export Design

Date: 2026-07-01
Status: review draft
Supersedes: v0.4 export behavior, without replacing v0.4 files
Evidence log: `docs/evidence/2026-07-01-impeller-v0-5-surface-graph-faithful-export/README.md`

## 1. Purpose

This spec defines the v0.5 design direction for exports from the
`AxisymmetricThroughflowRadialBladedImpeller` constructor family.

v0.4 made `surface_graph` the authoritative object for frontend CAD review, feature
debugging, and CFD manifest generation. The export path did not catch up: it still
builds a separate CadQuery proxy solid. That proxy can produce non-empty STEP/STL
files, but those files can contain a different object from the frontend view.

v0.5 fixes the semantic contract:

```text
Export artifacts must be projections of surface_graph, not independent substitute geometry.
```

The goal is to make third-party software and human experts inspect the same geometry
that the frontend and ontology manifests claim to represent.

## 2. Observed Problem

The user opened exported files and found that they did not match the frontend:

- extra disk/backplate under the hub,
- apparent blade-count mismatch when sample exports were generated with different
  run parameters,
- hub bottom and bottom-face semantics not matching the surface graph,
- blade edge closure surfaces missing or merged in the exported artifact.

The diagnosis is recorded in:

```text
docs/evidence/2026-07-01-impeller-v0-5-surface-graph-faithful-export/README.md
```

The essential mismatch is:

- frontend path: render `manifest.geometry.surface_graph.surfaces[*].uv_grid`;
- export path: build CadQuery `disk + hub + blade lofts + shroud` proxy solid.

## 3. Fixed Decisions

Use a new v0.5 DSL/ontology direction. Do not overwrite the v0.4 meaning because
v0.4 is research evidence for the surface/feature graph milestone.

The v0.5 export contract is graph-first:

1. Build or reuse the manifest `surface_graph`.
2. Select a named export view from that graph.
3. Emit STL/STEP from selected graph surfaces.
4. Record export fidelity, selected view, included/excluded surfaces, and traceability.

The first implementation target is faithful STL export. STEP should be graph-derived
when feasible, but must never silently fall back to a proxy solid while claiming to be
faithful.

Use this exactness label for the first v0.5 implementation:

```json
{
  "export_exactness": "surface_graph_sampled_mesh",
  "source_geometry": "manifest.geometry.surface_graph",
  "cad_exactness": "research_grade_sampled_surface"
}
```

## 4. Non-Goals

v0.5 does not include:

- industrial-grade exact B-Rep healing,
- guaranteed watertight OCCT sewing across all parameter values,
- solver-ready volume mesh generation,
- automatic CAD repair,
- replacing the frontend surface graph renderer,
- broadening the impeller taxonomy beyond the current slice.

v0.5 may produce a mesh-derived or face-shell-derived STEP for inspection, but it must
label that fidelity honestly. A lower-fidelity graph-derived artifact is better than
a visually smoother proxy artifact that represents a different object.

## 5. Architecture Options Considered

### Option A: Keep CadQuery Proxy And Tune It

This would continue using the current `disk + hub + blade lofts` path, then add fixes
for the obvious mismatches.

Pros:

- lowest immediate code churn,
- keeps STEP generation through CadQuery,
- preserves existing file sizes and basic third-party loading.

Cons:

- still creates geometry outside `surface_graph`,
- still loses per-surface graph identity after booleans,
- can keep drifting from frontend and CFD manifests,
- weak evidence chain for expert feedback.

Decision: reject for v0.5. It repeats the v0.4 problem.

### Option B: Surface-Graph Mesh Export First

This makes STL export triangulate exactly the same `uv_grid` surfaces that the frontend
renders. STEP can initially be a clearly labeled graph-derived inspection shell or a
declared unsupported format until a faithful STEP path is implemented.

Pros:

- maximum visual fidelity to frontend,
- preserves edge closure surfaces,
- easy to test surface counts, region names, and triangle provenance,
- no unregistered disk/backplate can appear.

Cons:

- not exact industrial B-Rep,
- may not be watertight if the graph itself has boundary gaps,
- STEP support needs careful fidelity labeling.

Decision: select as v0.5 baseline.

### Option C: Full OCCT Face Builder From Surface Graph

This converts each graph surface into OCCT faces, attempts sewing, and exports STEP
as a shell or solid while preserving graph provenance.

Pros:

- best long-term CAD direction,
- can support better STEP semantics,
- prepares for future B-Rep healing.

Cons:

- higher risk and larger implementation surface,
- hard to finish reliably without first freezing graph-fidelity tests,
- sewing failures could distract from the core v0.5 evidence requirement.

Decision: plan as v0.5 extension after Option B tests pass, not as the first task.

## 6. Selected Design

v0.5 introduces a dedicated export module:

```text
src/part_rule_synthesis/impeller_surface_graph_export.py
```

This module owns conversion from a manifest surface graph to export artifacts.

Core functions:

```python
def export_surface_graph_stl(surface_graph, path, *, view, manifest_context) -> dict:
    ...

def export_surface_graph_step(surface_graph, path, *, view, manifest_context) -> dict:
    ...

def selected_export_surfaces(surface_graph, *, view, manifest_context) -> list[dict]:
    ...
```

`service.py` should not build separate impeller CAD proxy solids for v0.5 presets.
It should call the graph exporter after the same geometry metadata has been generated
for the manifest.

## 7. Export Views

The export path must be view-aware.

Required views:

```text
cad_review_360
cfd_full_360
feature_debug_360
```

Initial default:

```text
cad_review_360
```

`cad_review_360` includes:

- material surfaces,
- blade pressure and suction surfaces,
- blade edge closure surfaces,
- hub bottom/top/bore/chamfer surfaces,
- shroud/hood surfaces when the preset is closed.

`cfd_full_360` includes:

- wetted surfaces only,
- no construction-only support surfaces,
- no suppressed internal assembly features.

`feature_debug_360` includes all graph surfaces and may color or group by feature
owner in future frontend/file metadata.

## 8. STL Contract

The STL exporter must:

1. Iterate selected `surface_graph.surfaces`.
2. Triangulate each `uv_grid` with the same cell split used by the frontend.
3. Emit nondegenerate triangles only.
4. Preserve orientation consistently where possible.
5. Include all selected edge closure surfaces.
6. Never add synthetic disks, caps, or support faces outside the selected graph.
7. Return export metadata with counts and traceability.

Required metadata:

```json
{
  "format": "stl",
  "source": "surface_graph",
  "view": "cad_review_360",
  "surface_count": 51,
  "triangle_count": 86155,
  "included_surface_ids": [],
  "excluded_surface_ids": [],
  "export_exactness": "surface_graph_sampled_mesh",
  "warnings": []
}
```

STL region metadata is limited by the STL format. For traceability, the manifest must
record triangle ranges per surface:

```json
{
  "triangle_regions": [
    {
      "surface_graph_id": "blade_0_pressure_surface",
      "feature_id": "blade_00",
      "role": "blade_pressure",
      "triangle_start": 0,
      "triangle_count": 1280
    }
  ]
}
```

## 9. STEP Contract

STEP export must be honest about fidelity.

Accepted v0.5 states:

```text
surface_graph_step_shell
surface_graph_mesh_step
step_not_available_for_view
```

Not accepted:

```text
cadquery_proxy_solid_claimed_as_surface_graph_export
```

The first implementation may export a graph-derived STEP shell if CadQuery/OCCT can
create faces from graph surfaces reliably. If not, the API should return a clear
error or manifest warning for STEP rather than silently exporting a different object.

Required STEP metadata:

```json
{
  "format": "step",
  "source": "surface_graph",
  "view": "cad_review_360",
  "export_exactness": "surface_graph_step_shell",
  "face_regions": [
    {
      "surface_graph_id": "blade_0_pressure_surface",
      "feature_id": "blade_00",
      "role": "blade_pressure"
    }
  ],
  "warnings": [
    "STEP surfaces are generated from sampled graph grids, not exact source NURBS"
  ]
}
```

If STEP cannot preserve enough geometry identity in v0.5, STL should still be faithful
and STEP should be labeled as limited or unavailable.

## 10. Manifest Changes

Add an `export_manifests` section beside `exports`:

```json
{
  "exports": {
    "stl": ".../impeller.stl",
    "step": ".../impeller.step"
  },
  "export_manifests": {
    "stl": {
      "format": "stl",
      "source": "surface_graph",
      "view": "cad_review_360",
      "status": "PASS",
      "export_exactness": "surface_graph_sampled_mesh",
      "surface_count": 51,
      "triangle_count": 86155,
      "triangle_regions": []
    },
    "step": {
      "format": "step",
      "source": "surface_graph",
      "view": "cad_review_360",
      "status": "PASS_WITH_WARNINGS",
      "export_exactness": "surface_graph_step_shell",
      "face_regions": [],
      "warnings": []
    }
  }
}
```

Update `export_strategy`:

```json
{
  "mode": "surface_graph_faithful",
  "cad_exports": "completed",
  "reason": "exports are derived from manifest.geometry.surface_graph"
}
```

## 11. Ontology Insight

v0.5 should treat export as a first-class ontology relation.

New or clarified entities:

- `surface_graph`
- `surface_graph_surface`
- `export_artifact`
- `export_region`
- `export_view`
- `export_fidelity`

New or clarified relations:

```text
derived_from(export_artifact, surface_graph)
projects_view(export_artifact, export_view)
contains_region(export_artifact, export_region)
derived_from(export_region, surface_graph_surface)
owned_by(surface_graph_surface, feature_node)
has_export_fidelity(export_artifact, export_fidelity)
```

This relation chain is required for ontology evolution:

```text
expert feedback on file
-> export region
-> surface_graph_id
-> feature node
-> constructor rule
-> DSL design variable or topology variable
```

Without `export_region -> surface_graph_surface`, expert inspection of exported files
cannot be used as reliable evidence for rule evolution.

## 12. Compatibility Rule

v0.2, v0.3, and v0.4 folders remain immutable evidence. v0.5 should add a new folder:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/
```

v0.5 can initially copy v0.4 constructors and presets, then add:

```text
export_contracts/
  surface_graph_faithful.json
```

The runtime compiler should support v0.5 without changing older version semantics.

## 13. Testing Strategy

Regression tests must prove the current mismatch cannot recur.

Required tests:

1. v0.5 STL surface IDs equal selected surface graph IDs.
2. v0.5 STL triangle regions cover every selected surface.
3. v0.5 open preset export includes all blade edge closure surfaces.
4. v0.5 export does not include an extra disk/backplate absent from surface graph.
5. v0.5 export uses the same `blade_count` as manifest parameters.
6. v0.5 export respects profile overrides and curve overrides.
7. v0.5 export metadata records `source: surface_graph`.
8. v0.4 lineage tests still pass.

Recommended acceptance assertion for the v0.4 diagnostic case promoted to v0.5:

```python
assert manifest["export_strategy"]["mode"] == "surface_graph_faithful"
assert manifest["export_manifests"]["stl"]["surface_count"] == len(
    manifest["geometry"]["surface_graph"]["surfaces"]
)
assert any(
    region["role"] == "blade_leading_edge_closure"
    for region in manifest["export_manifests"]["stl"]["triangle_regions"]
)
assert not any(
    region["surface_graph_id"] == "cadquery_proxy_disk"
    for region in manifest["export_manifests"]["stl"]["triangle_regions"]
)
```

## 14. Documentation Requirements

The implementation must update:

- `README.md`
- `docs/current-research-frontier.md`
- `docs/repository-map.md`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5/CHANGELOG.md`

The changelog must state that v0.5 changes export semantics, not blade construction
semantics alone.

## 15. Changelog Draft

```markdown
# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.5 Changelog

Date: 2026-07-01

Supersedes: `v0_4`

## Motivation

v0.5 makes STEP/STL exports faithful projections of `surface_graph` so third-party
CAD/STL inspection sees the same geometry used by the frontend and ontology manifests.

## Changes

1. Added surface-graph-faithful export contract.
2. Added export manifest metadata with source, view, exactness, and region traceability.
3. Added STL triangle-region provenance by `surface_graph_id`, feature, and role.
4. Required blade edge closure surfaces to appear in CAD review exports.
5. Disallowed unregistered proxy surfaces in v0.5 faithful exports.
6. Clarified STEP exactness labels for graph-derived shell/mesh exports.

## Implementation Status

The first v0.5 implementation provides faithful sampled STL exports and explicit
metadata. Exact industrial STEP B-Rep sewing remains future work unless implemented
and verified separately.
```

## 16. Open Risks

- A graph-faithful STL can faithfully expose graph defects. That is desirable for
  research evidence, but it may look worse than a smoothed proxy model.
- If surface graph boundaries are not watertight, the faithful STL will preserve that
  gap. The fix belongs in the graph/kernel, not in hidden export repair.
- STEP support may lag STL support because STEP wants stronger surface/face topology.
- Third-party tools may merge or reorder faces. The repository must keep its own
  `export_manifests` for provenance.

## 17. Spec Self-Review

- Placeholder scan: no unresolved placeholders.
- Internal consistency: v0.5 consistently treats `surface_graph` as authoritative.
- Scope check: focused on export semantics and provenance, not a full CAD/CAE stack.
- Ambiguity check: STL is required to be faithful first; STEP may be graph-derived
  with warnings or explicitly unavailable, but may not silently use a proxy solid.

