# Impeller V1.1.4 Review Workspace And Preset Hardening Spec

## Goal

Ship a stable preset-only review release. V1.1.4 corrects splitter placement,
restores all five representative presets, prevents collapsed trailing-edge blade
span in the first two presets, and replaces the parameter editor with a full-width
read-only CAD and engineering-drawing workspace.

## Version Semantics

- Runtime release: `1.1.4`.
- Canonical NURBS parameterization remains `1.1.2`.
- Geometry family remains V1.1; this release hardens mapping and preset contracts
  rather than introducing a new mathematical representation.
- Existing preset ids remain stable.

## Backend Requirements

1. A splitter using `main_passage_bisector` is evaluated at the same physical
   streamwise coordinate as its adjacent main blades, including when canonical
   skeleton and thickness fields are present.
2. The measured splitter passage fraction must remain inside a configurable
   clearance envelope around the requested fraction for all sampled span stations.
3. No-splitter presets use an explicit not-applicable placement contract without
   assuming a global X-axis direction.
4. Angular drawing evidence uses an engineering tolerance, not exact floating-point
   equality.
5. The first two presets provide enough hub-to-tip/shroud distance after attachment
   offsets. Their span direction against the local hub meridional tangent remains
   between 60 and 120 degrees over the active blade interval.
6. All five active presets synthesize and instantiate through `RuleSynthesisService`.

## Engineering Drawing Requirements

- Drawing data is read-only and derived from the resolved model.
- The frontend does not build a browser of every editable parameter.
- Top view contains the complete rotational model outline and representative blade
  dimensions.
- Meridional view contains hub and tip/shroud profiles, control polygons, bore and
  material envelope dimensions.
- S-Q view presents one main blade and one splitter blade separately when splitters
  exist; a no-splitter status is explicit.
- Drawings are vector SVG and occupy the full workspace.

## Frontend Requirements

- Remove the permanent left sidebar and all parameter, curve, transition and facet
  editors from the active application.
- Generate from the selected preset without frontend geometry overrides.
- Keep only `CAD Review` and `Engineering Drawing` workspaces.
- Remove `CFD full 360`, `CFD360 mesh`, and `Feature debug` navigation.
- Preset and resolved manifest data are read-only and shown in compact, dismissible
  disclosure panels.
- A rendering exception is contained by an error boundary and must not blank the app.
- Backend error details are shown instead of a generic fetch failure.

## Acceptance

- Five active presets instantiate successfully.
- Open main/splitter minimum passage clearance passes.
- Open and closed support-profile angle and active-height contracts pass.
- The active frontend has no editable numeric or control-point inputs.
- Only CAD Review and Engineering Drawing are present in workspace navigation.
- Frontend tests and V1.1 backend regression tests pass.
