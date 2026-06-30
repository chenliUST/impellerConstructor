# Impeller Ontology Rule Engine B Design

Date: 2026-06-29
Project: Part Rule Synthesis
Status: Approved for implementation

## Goal

Promote `impeller` to the primary part family and generate deterministic rule engines from ontology
facets. The frontend must let a user select impeller presets or facets, generate geometry, and inspect
both shaded STL and construction parameter lines.

## Scope

This version implements a complete ontology-facing rule engine interface for the main impeller facet
axes:

- `flow_topology`: `axial`, `mixed`, `radial`
- `shroud_topology`: `open`, `semi_open`, `closed`
- `suction_topology`: `single_suction`, `double_suction`
- `blade_exit_geometry`: `backward_curved`, `radial`, `forward_curved`
- `working_domain`: `pump`, `compressor`, `fan_or_blower`, `turbine_or_runner`, `unknown`

The generated geometry remains a research proxy. The requirement is that geometry differences are
visible and traceable to selected rules; it is not a release-quality aerodynamic or hydraulic design.

## Backend Behavior

`POST /api/rule-engines/synthesize` shall accept:

```json
{
  "part_family_id": "impeller",
  "preset_id": "radial_open_backward_single_reference",
  "facets": {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump"
  }
}
```

`preset_id` supplies defaults. Explicit `facets` override preset facets after validation.

The existing `centrifugal_impeller` part family remains a compatibility alias. Alias manifests shall
record `part_family: "centrifugal_impeller"` for old tests, while new `impeller` manifests record
`part_family: "impeller"`.

## Manifest Additions

Impeller manifests shall include:

- `preset_id`
- `facets`
- `selected_rules`
- `rule_implications`
- `unsupported_or_inferred_regions`
- `construction_lines`

`construction_lines` is a frontend-ready data structure:

```json
{
  "hub": [{ "name": "hub latitude 0", "points": [[0, 0, 0], [1, 0, 0]] }],
  "blade": [{ "name": "blade u 0", "points": [[0, 0, 0], [1, 0, 1]] }],
  "shroud": []
}
```

These lines represent construction parameter lines, not STL triangle edges.

## Geometry Rule Proxies

Facet implications:

- `flow_topology.radial`: outlet radius is greater than inlet radius; blade path expands radially.
- `flow_topology.mixed`: outlet is radial plus axial; blade path uses a raised mixed-flow meridional
  offset.
- `flow_topology.axial`: inlet and outlet radii are closer; blade path is more axial.
- `shroud_topology.open`: no shroud construction surface.
- `shroud_topology.semi_open`: one shroud parameter-line family is generated.
- `shroud_topology.closed`: front and back shroud parameter-line families are generated.
- `suction_topology.single_suction`: one inlet side.
- `suction_topology.double_suction`: mirrored construction lines across the midplane.
- `blade_exit_geometry.backward_curved`: outlet blade angle bends backward relative to the radial
  proxy convention.
- `blade_exit_geometry.radial`: outlet blade angle is near the radial proxy convention.
- `blade_exit_geometry.forward_curved`: outlet blade angle bends forward relative to the radial proxy
  convention.

## Frontend Behavior

The viewer shall:

- Disable camera auto-rotation by default.
- Remove the ground/grid plane.
- Keep shaded rendering from STL.
- Render wireframe mode from `manifest.geometry.construction_lines` only.
- Let combined mode show STL plus construction lines.
- Display facets, selected rules, inferred regions, and exports in the manifest panel.

## Acceptance Criteria

- `/api/ontology` exposes facet axes and allowed values.
- `/api/impeller-presets` lists ontology presets with facets and default parameters.
- `part_family_id: "impeller"` synthesizes a rule engine from presets/facets.
- `centrifugal_impeller` remains compatible.
- Generated impeller manifests contain selected rules and construction lines.
- Frontend defaults auto-rotation off and renders construction lines instead of STL triangle edges.
- Automated tests and browser visual verification pass.

