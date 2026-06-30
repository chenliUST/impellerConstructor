# Impeller Ontology v0.1 Design

Date: 2026-06-29
Project: Part Rule Synthesis
Status: Approved design for implementation planning

## Purpose

This design replaces the current hardcoded `centrifugal_impeller` part family with a more general
`impeller` ontology. The goal is to avoid mixing several independent classification systems into a
single inheritance tree.

The rule engine shall treat `impeller` as the part-family base. Terms such as centrifugal, axial,
open, closed, backward-curved, single-suction, and double-suction shall become facets. A preset can
combine facets, but no preset is allowed to redefine the meaning of the base part family.

Physical performance is out of scope for direct geometry generation in v0.1. Physics, CFD, FEA, or
mean-line calculations may later produce parameter suggestions, constraints, or optimization feedback,
but they shall not be direct inputs such as "generate a high-efficiency impeller."

## Conceptual Model

### Base Part Family

```yaml
part_family: impeller
```

An impeller is a rotating bladed component that transfers energy between a shaft and a working fluid.
The base ontology shall define shared geometry and topology concepts, not a specific pump, compressor,
fan, or turbine implementation.

### Required Base Features

Every impeller rule engine shall reason about these features, even if some are optional or absent in a
specific facet combination:

- `hub`: central rotating body connected to shaft or bore.
- `blade`: repeated energy-exchange surface.
- `blade_root`: attachment region between blade and hub or disk.
- `blade_airfoil`: blade surface or section representation.
- `inlet`: fluid entry region.
- `outlet`: fluid exit region.
- `flow_passage`: passage swept between neighboring blades.
- `rotation_axis`: primary axis of rotation.
- `optional_shroud`: covering surface present only for semi-open or closed variants.
- `mounting_interface`: shaft, bore, or fastener interface.

### Required Topology Relations

The base ontology shall include these relations:

- `embedded_contact(blade_root, hub.outer_surface)`
- `patterned_around_axis(blade, rotation_axis)`
- `bounds_flow_path(blade, flow_passage)`
- `has_inlet(impeller, inlet)`
- `has_outlet(impeller, outlet)`
- `attached_to(optional_shroud, blade)` when a shroud facet requires it
- `mirrored_about_midplane(inlet)` when double suction requires it

## Facet Axes

Facets are independent classification axes. They are metadata unless they explicitly trigger rule
implications.

### `flow_topology`

Allowed values:

- `axial`
- `mixed`
- `radial`

Rule implications:

- `radial`: inlet is near the eye/axis and outlet radius must be greater than inlet radius.
- `axial`: inlet and outlet remain primarily along the rotation axis.
- `mixed`: outlet has both radial and axial displacement; requires meridional path interpolation.

### `shroud_topology`

Allowed values:

- `open`
- `semi_open`
- `closed`
- `inferred`

Rule implications:

- `open`: no covering shroud surface; blade tips are exposed.
- `semi_open`: one shroud or backplate surface is present.
- `closed`: front and back shroud surfaces are present and bound the passage.
- `inferred`: source does not prove the topology; geometry may be generated but must be marked inferred.

### `suction_topology`

Allowed values:

- `single_suction`
- `double_suction`

Rule implications:

- `single_suction`: one inlet eye or inlet side.
- `double_suction`: mirrored inlet geometry on both sides of a midplane.

### `blade_exit_geometry`

Allowed values:

- `backward_curved`
- `radial`
- `forward_curved`
- `inferred`

Rule implications:

- `backward_curved`: outlet blade angle is below the radial reference for the chosen convention.
- `radial`: outlet blade angle aligns with radial reference.
- `forward_curved`: outlet blade angle is beyond the radial reference for the chosen convention.
- `inferred`: source does not prove blade exit geometry; generated geometry must record this.

### `working_domain`

Allowed values:

- `pump`
- `compressor`
- `fan_or_blower`
- `turbine_or_runner`
- `unknown`

Rule implications:

- None in v0.1.

This facet is metadata only in v0.1. It may affect source authority, terminology, and later analysis
interfaces, but it shall not select geometry rules yet.

## Preset Model

Presets combine facets and default parameters. A preset is not a new ontology class.

Current UPCommons-derived sample shall become:

```yaml
preset_id: upcommons_radial_pump_single_suction_backward_curved_demo
part_family: impeller
source_refs:
  - upcommons_centrifugal_pump_impeller
facets:
  working_domain: pump
  flow_topology: radial
  shroud_topology: inferred
  suction_topology: single_suction
  blade_exit_geometry: backward_curved
parameters:
  blade_count: 7
  inlet_radius_mm: 420.2
  exit_radius_mm: 1400.65
  inlet_blade_height_mm: 394.0
  outlet_blade_height_mm: 251.0
  inlet_blade_angle_deg: 17.47
  outlet_blade_angle_deg: 21.19
  blade_thickness_mm: 56.0
```

The preset may generate visible geometry, STEP, STL, and manifest artifacts. Its aerodynamic or hydraulic
performance remains inferred unless a later analysis step proves otherwise.

## DSL Impact

The DSL should change from:

```yaml
part_family: centrifugal_impeller
```

to:

```yaml
part_family: impeller
preset_id: upcommons_radial_pump_single_suction_backward_curved_demo
facets:
  flow_topology: radial
  shroud_topology: inferred
  suction_topology: single_suction
  blade_exit_geometry: backward_curved
```

The compiler shall first load the base `impeller` rules, then apply rule implications from facets, then
bind preset defaults and user parameters.

For v0.1, only these facets drive geometry rules:

- `flow_topology`
- `shroud_topology`
- `suction_topology`
- `blade_exit_geometry`

`working_domain` is retained as metadata only.

## Rule Selection

Facet rule implications shall be additive and explicit.

Example for the current preset:

```yaml
selected_rules:
  - base.impeller.has_hub
  - base.impeller.has_blade_pattern
  - flow_topology.radial.requires_outlet_radius_gt_inlet_radius
  - flow_topology.radial.uses_eye_inlet
  - suction_topology.single_suction.uses_single_eye
  - blade_exit_geometry.backward_curved.requires_backward_curve_check
  - shroud_topology.inferred.requires_authority_warning
```

Conflicts shall fail early. For example, a preset cannot select both `single_suction` and
`double_suction`.

## Feedback And Knowledge Ingestion

Feedback should target the base feature or the relevant facet.

Examples:

- "The blade does not grow from the hub" maps to `embedded_contact(blade_root, hub.outer_surface)`.
- "This should be double suction" maps to a `suction_topology` facet patch.
- "This is not a closed impeller" maps to a `shroud_topology` facet patch.
- "The blade is not backward-curved enough" maps to `blade_exit_geometry` or blade curve parameters.

Feedback must not create a new class such as `better_centrifugal_impeller`. It must become either:

- parameter patch
- facet patch
- topology/rule patch
- primitive gap proposal

## Implementation Sequence

1. Add an ontology/preset representation for `part_family: impeller`.
2. Keep the existing `centrifugal_impeller` endpoint as a compatibility alias.
3. Re-express the UPCommons sample as an `impeller` preset.
4. Update generated manifests to report `part_family: impeller`, `preset_id`, and facets.
5. Keep existing geometry generation initially unchanged.
6. Add tests proving the alias and preset produce equivalent STEP/STL exports.
7. Later, move rule selection out of the monolithic `service.py` into a small ontology/preset module.

## Acceptance Criteria

- `GET /api/ontology` exposes `impeller` base terms and facet axes.
- The API can synthesize `part_family: impeller` with the UPCommons preset.
- `centrifugal_impeller` still works as a compatibility alias during migration.
- Manifest records `part_family: impeller`, `preset_id`, `facets`, and `source_refs`.
- Current high-curvature sample can be regenerated through the preset path.
- Tests prove invalid facet combinations are rejected.

## References

- Hydraulic Institute pump principles: https://datatool.pumps.org/pump-fundamentals/pump-principles
- Hydraulic Institute ANSI/HI 14.3a examples: https://www.pumps.org/wp-content/uploads/2022/01/14.3a.pdf
- NASA NTRS PUMPA pump analysis examples: https://ntrs.nasa.gov/api/citations/19950013379/downloads/19950013379.pdf
- KSB impeller lexicon: https://www.ksb.com/en-global/centrifugal-pump-lexicon/article/impeller-1116078
- UPCommons reference PDF used for the current preset: https://upcommons.upc.edu/server/api/core/bitstreams/7652df45-fa36-4c53-8755-692a0f7fbdee/content
