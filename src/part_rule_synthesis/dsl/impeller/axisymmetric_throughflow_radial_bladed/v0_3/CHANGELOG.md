# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.3 Changelog

Date: 2026-06-30

Supersedes: `v0_2`

## Motivation

This version records frontend and geometry-construction issues observed during interactive review:

- Open impeller showed a visible tip reference surface, making open and closed cases visually ambiguous.
- Curve editor operation areas were too small and did not expose numeric values.
- Hub appeared surface-like rather than a solid material domain.
- Hub and hood/shroud material domains lacked explicit nonzero thickness semantics.
- Hub and hood/shroud lacked chamfer/fillet feature semantics.

Evidence:

- `docs/evidence/2026-06-30-impeller-ui-and-dsl-issues/current-open-impeller-ui-issue.png`

## DSL Changes

1. Added explicit material-domain parameters:
   - `hub_wall_thickness_mm`
   - `hub_bottom_thickness_mm`
   - `hub_top_cap_thickness_mm`
   - `hood_wall_thickness_mm`

2. Added explicit edge-treatment parameters:
   - `hub_chamfer_radius_mm`
   - `hood_chamfer_radius_mm`

3. Changed open impeller tip support semantics:
   - v0.2: `blade_tip_support_surface.role = reference_only`
   - v0.3: `blade_tip_support_surface.role = construction_support_only`
   - v0.3 display policy hides this surface by default for open impellers.

4. Changed hub material semantics:
   - v0.2: `revolved_solid_with_bore`
   - v0.3: `capped_revolved_solid_with_bore`
   - v0.3 requires top cap face, bottom/backplate thickness, and through mounting bore.

5. Changed closed hood/shroud semantics:
   - v0.2: `revolved_material_shell`
   - v0.3: `finite_thickness_revolved_shell`
   - v0.3 requires inner/outer shell surfaces and positive wall thickness.

6. Added `solid_features` section to constructors:
   - `hub_bore`
   - `hub_chamfers`
   - `hood_chamfers` for closed impellers

## Files Added

- `src/part_rule_synthesis/ontology/impeller/v0_3/slice.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/schema.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/constructors/open_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/constructors/closed_impeller.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/presets/radial_open_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/presets/radial_closed_reference.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/shape_controls/default_shape_controls.json`
- `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3/aliases.json`

## Implementation Status

This is a research DSL version record. Runtime loading and geometry-kernel implementation are intentionally planned separately so v0.2 behavior remains reproducible.
