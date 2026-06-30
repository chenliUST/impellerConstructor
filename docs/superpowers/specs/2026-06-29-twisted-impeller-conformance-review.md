# Twisted Impeller Boundary Conformance Review

## Purpose

This note records the geometry correction made after reviewing the open and closed twisted impeller references.
The goal is to test whether blade boundary curves are constructed from the same hub and tip/shroud surfaces they
claim to connect to.

## Finding

The previous kernel could generate a single blade mean surface and a surface graph, but the blade boundary curves
were not constructed from a warped hub or warped tip/shroud surface field. That meant a visually twisted case could
still be mathematically under-constrained: the blade boundary might look close to the hub or tip surface, while not
being the exact same sampled curve.

The old behavior was acceptable for simple axisymmetric studies but not for validating high-twist impellers.

## Parameter Direction Convention

The code keeps the existing internal array convention:

- `mean_surface[row][0]` is the blade hub boundary.
- `mean_surface[row][-1]` is the blade tip or shroud boundary.
- `row` advances along the streamwise/meridional direction.

This maps to the engineering intent that one blade boundary lies on the hub surface and the opposite boundary lies
on the free tip or shroud surface.

## Mathematical Correction

The kernel now uses two warped surface fields:

- `hub` field: `hub_twist_deg`, `hub_warp_mm`
- `tip` field: `tip_twist_deg`, `tip_warp_mm`

For every blade and every meridional sample, the hub boundary point is sampled directly from the hub field and the
tip boundary point is sampled directly from the tip/shroud field. The blade mean surface is then lofted between
those two boundary curves. This makes conformance a construction rule, not a post-processing adjustment.

Open impeller:

- The blade tip boundary conforms to `tip_reference_surface`.

Closed impeller:

- The blade tip boundary conforms to `shroud_surface`.

## Added Cases

- `twisted_open_impeller_study`
  - open, mixed-flow, backward-curved
  - high hub/tip twist and warp
  - validates blade hub boundary and free tip boundary conformance

- `twisted_closed_impeller_study`
  - closed, mixed-flow, backward-curved
  - high hub/shroud twist and warp
  - validates blade hub boundary and shroud boundary conformance

## Validity Checks

The validity report now includes:

- `blade_hub_boundary_conformance`
- `blade_tip_boundary_conformance`

For the two new cases, both checks report:

```json
{
  "status": "PASS",
  "max_distance_mm": 0.0,
  "tolerance_mm": 0.001
}
```

## Current Boundary

This is still a research-grade proxy. The manifest and frontend wireframe now represent a stricter surface graph and
boundary-conforming sampled geometry, but the exported STEP/STL is still produced through simplified CadQuery solids.
The next engineering step is to make CAD export consume the same conforming surface graph boundaries rather than
approximating them through coarse loft/union operations.
