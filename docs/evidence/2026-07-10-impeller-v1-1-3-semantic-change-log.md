# Impeller V1.1.3 Semantic Change Log

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

## Change Summary

V1.1.3 changes the runtime and graphical inspection contract only. It does not introduce a new geometry constructor, geometry patch, or canonical parameterization.

```text
runtime_release_version = 1.1.3
parameter_inspection_contract_version = 1.1.3
geometry_version = 1.1
geometry_patch_version = 1.1.2
canonical_payload_version = 1.1.2
```

## What Changes

- The text-only `Parameter views` presentation is removed.
- The central graphics workspace adds read-only `3D`, `Top`, `Meridional`, `S-Q`, and `Quad` inspection views.
- One shared WebGL renderer and generated scene serve 3D, top, and meridional views.
- S-Q uses the resolved selected section loop, canonical control geometry, and continuity measurements.
- S-Q publishes normalized source coordinates separately from deterministic metric display coordinates; equal-aspect display uses `S (mm)` and `Q (mm)`.
- Selection and deterministic `key`, `selected`, and `all` annotation subsets are shared across views.
- Blade, station, segment, control-point, and surface-family selection is normalized through explicit contract relationships.
- Control points carry authoritative, stable IDs and ownership records from the backend.
- Contract validation is deep and bidirectional, including exact surface sets, loop closure, nested controls, and blade/station/loop references.
- Service manifests expose the V1.1.3 parameter-inspection contract and a generation ID that rejects stale inspectable geometry.

## What Does Not Change

- The five active V1.1 preset IDs remain unchanged.
- V1.1.2 geometry and canonical payload semantics remain authoritative.
- Inspection is read-only and cannot mutate geometry or transition overrides.
- Existing V1.1 geometry, validation, mesh, CAD, and CFD export behavior remains in force.
- The implementation remains review-grade sampled geometry and does not claim sewn production CAD or solver-ready CFD volume meshes.

## Compatibility Boundary

Generation IDs cover every source field that affects visible or inspectable evidence, including manufactured hub/shroud surfaces, section-loop samples and controls, dimensions, policies, and quality evidence. A UV grid is exempt only when explicit metadata marks the surface both reference-only and hidden/non-rendered. Categorical roles such as `hub_support` and `shroud_support` are never exemptions. The generation ID and derived inspection payload are excluded from their own hash input to avoid self-reference.

The same explicit `inspectable` classification controls scene input, camera bounds, picking, and annotations. A hash-exempt helper therefore cannot alter any visible inspection output. Visible hub/shroud support surfaces remain inspectable and hashed; selecting one clears blade-owned dependent identities without invalidating the S-Q fallback.
