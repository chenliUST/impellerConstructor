# Impeller V1.1.6 R14 Semantic Change Log

Date: 2026-07-17

## Contract Delta

- Audit implementation revision changes from
  `axis_first_triangle_surface_r13_2` to
  `axis_first_triangle_surface_r14_0`.
- Exact directional deviation arrays may be reused only through checkpoint
  contract `exact_triangle_surface_r14_0`.
- Checkpoint identity is content-addressed by semantic role plus complete source
  and reconstruction triangle-mesh fingerprints.
- Audit status now records worker ownership and surface-deviation heartbeat
  progress.
- Recovery is an application-startup action. Constructing or importing a
  service object no longer mutates active audit state.

## Unchanged Semantics

- Canonical geometry remains V1.1.2.
- The exact point-to-corresponding-triangle-surface distance definition is
  unchanged.
- Source/reconstruction role ownership, unsupported-feature exclusions,
  sampling, heatmap units, and acceptance status are unchanged.
- R13.2 manifests are intentionally incompatible with R14 full-audit reuse.

