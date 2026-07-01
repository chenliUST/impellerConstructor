# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.5 Implementation Log

Date: 2026-07-01

Status: implemented locally

Supersedes: `v0_4`

## Motivation

v0.5 makes STEP/STL exports faithful projections of `surface_graph` so third-party
CAD/STL inspection sees the same geometry used by the frontend and ontology manifests.

The immediate trigger was user-supplied third-party viewer evidence showing that the
current v0.4 CadQuery export path can produce an extra disk/backplate, omit explicit
blade edge closure surfaces, and differ from the frontend-rendered surface graph.

## Implemented Changes

1. Add a surface-graph-faithful export contract.
2. Add export manifest metadata with source, view, exactness, and region traceability.
3. Add STL triangle-region provenance by `surface_graph_id`, feature, and role.
4. Require blade edge closure surfaces to appear in CAD review exports.
5. Disallow unregistered proxy surfaces in v0.5 faithful exports.
6. Clarify STEP exactness labels for graph-derived shell/mesh exports.
7. Preserve v0.2, v0.3, and v0.4 version folders as historical evidence.

## Implementation Status

The first v0.5 implementation provides faithful sampled STL exports, graph-derived
faceted STEP surface shells, and explicit metadata. Exact industrial STEP B-Rep
sewing remains future work unless implemented and verified separately.

## Evidence Links

- `README.md`
- `exported-cad-proxy-mismatch-1.png`
- `exported-cad-proxy-mismatch-2.png`
- `export-summary.json`
- `docs/superpowers/specs/2026-07-01-impeller-v0-5-surface-graph-faithful-export-design.md`
- `docs/superpowers/plans/2026-07-01-impeller-v0-5-surface-graph-faithful-export.md`
