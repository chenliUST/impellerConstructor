# Impeller v0.4 Optimization-Ready Surface/Feature Graph Design

Date: 2026-07-01
Status: review draft
Supersedes: v0.3 design direction, without replacing v0.3 files
Evidence log: `docs/evidence/2026-07-01-impeller-v0-4-optimization-ready-surface-feature-graph/README.md`

## 1. Purpose

This spec defines the v0.4 design direction for the
`AxisymmetricThroughflowRadialBladedImpeller` constructor family.

The current v0.3 geometry and parameters are acceptable as a visual research baseline,
but the next version must support future high-throughput CAD/CAE work. The main change
is to stop treating the kernel as a single place where DSL semantics, geometric
construction, frontend editing, and CAE metadata all accumulate. v0.4 introduces an
explicit surface/feature graph compiler contract.

The goal is to make one narrow impeller family suitable for:

- deterministic 360-degree CAD review geometry,
- executable full-360 CFD wetted geometry manifest,
- schema-level FEA solid view preparation,
- stable patch naming for meshing and post-processing,
- optimization campaign signatures with fixed design-vector length,
- structured loss traceability from CAE or expert feedback back to DSL variables.

## 2. Fixed Decisions

Use the existing constructor family:

```text
AxisymmetricThroughflowRadialBladedImpeller
```

Use a new v0.4 DSL/ontology version. Do not overwrite v0.3 because v0.3 is part of
the research evolution record.

Use architecture option B:

```text
Surface/feature graph compiler
```

This means the DSL defines design variables, topology variables, surfaces, features,
simulation views, validity contracts, and patch naming policy. The geometry kernel
compiles DSL instances into a named graph and derived manifests.

Use CFD executable-first development:

- v0.4 should make `cfd_full_360` a real generated view.
- v0.4 should define `fea_solid` schema and feature visibility, but not implement a
  complete structural-analysis pipeline.

Use full 360-degree wetted geometry as the first CFD executable target. Periodic
single-passage sectors remain a future view, not a v0.4 acceptance target.

Use group + instance CFD patch naming:

- CFD automation uses stable group names such as `blade_pressure_wall`.
- expert feedback, CAE failure localization, and loss records use instance names such
  as `blade_07_pressure_surface`.

Use boundary + guide/layer curves as the blade surface authoring contract. Do not
expose a raw full tensor-product NURBS control net as the primary user-facing design
language in v0.4.

Support variable control-point counts in design-space mode, but freeze topology
variables inside an optimization campaign.

## 3. Non-Goals

v0.4 does not include:

- a complete CAD/CAE workflow platform,
- DOE runner, solver adapter, meshing adapter, or result database,
- strict OCCT-grade exact filleting,
- guaranteed STEP B-Rep healing,
- periodic single-passage CFD domain generation,
- inverse-design blade loading as the primary authoring mode,
- full tensor-product NURBS surface editing in the frontend,
- final ontology taxonomy for all impeller classes.

The first target is a coherent, optimization-ready graph and manifest contract with
research-grade sampled geometry.

## 4. Recommended File Layout

```text
src/part_rule_synthesis/
  ontology/
    impeller/
      v0_4/
        slice.json
        entities.json
        relations.json
        validity_contracts.json
        loss_schema.json

  dsl/
    impeller/
      axisymmetric_throughflow_radial_bladed/
        v0_4/
          schema.json
          CHANGELOG.md
          aliases.json
          constructors/
            open_impeller.json
            closed_impeller.json
          presets/
            radial_open_reference.json
            radial_closed_reference.json
          shape_controls/
            default_shape_controls.json
          simulation_views/
            cfd_full_360.json
            fea_solid_schema.json
```

New Python implementation should be separated from the existing compatibility layer:

```text
src/part_rule_synthesis/
  impeller_graph_contract.py
  impeller_cfd_manifest.py
  impeller_design_space.py
```

The existing `impeller_kernels/axisymmetric_throughflow_nurbs.py` can remain the
research geometry compiler, but v0.4 should prevent it from becoming the only place
where ontology, DSL, features, CAE views, and frontend policy are encoded.

## 5. DSL v0.4 Structure

The v0.4 top-level DSL shape should be:

```json
{
  "dsl_version": "0.4",
  "part_family": "impeller",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "classification": {},
  "design_space": {},
  "geometry_definition": {},
  "surface_graph_contract": {},
  "feature_graph_contract": {},
  "simulation_views": {},
  "validity_contracts": {},
  "frontend_editing_contract": {}
}
```

The most important new section is `design_space`.

```json
{
  "design_space": {
    "topology_variables": [
      "hub_profile.control_point_count",
      "tip_profile.control_point_count",
      "blade_surface.guide_curve_count",
      "enabled_features"
    ],
    "design_variables": [
      "hub_profile.control_points[*].r_mm",
      "hub_profile.control_points[*].z_mm",
      "tip_profile.control_points[*].r_mm",
      "tip_profile.control_points[*].z_mm",
      "blade_theta_control_points[*].theta_deg",
      "thickness_control_points[*].thickness_mm",
      "root_fillet.radius_mm"
    ],
    "campaign_freeze_rule": "topology_variables are immutable inside one optimization campaign"
  }
}
```

Design-space mode and campaign mode must be explicitly different:

- In design-space mode, a user or agent can add/remove control points, change guide
  count, enable/disable features, and alter knot policy.
- In campaign mode, the design vector length, control-point count, feature set, patch
  groups, and topology variables are frozen. Numeric design variables may change.

## 6. Simulation Views

v0.4 defines three views:

```json
{
  "simulation_views": {
    "cad_review_360": {
      "purpose": "human geometry review",
      "domain": "full_360_solid_or_surface"
    },
    "cfd_full_360": {
      "purpose": "first executable high-throughput CFD view",
      "domain": "full_360_wetted_surface",
      "feature_suppression": [
        "mounting_bore_internal",
        "keyway_internal",
        "shaft_seat_internal",
        "rear_hub_groove_internal"
      ],
      "patch_naming": "group_and_instance"
    },
    "fea_solid": {
      "purpose": "future structural view",
      "status": "schema_only_v0_4"
    }
  }
}
```

`cad_review_360` may include construction/debug surfaces. `cfd_full_360` must not
include construction-only support surfaces or internal assembly features. `fea_solid`
should preserve material-domain and assembly-feature semantics, but v0.4 does not need
to make it a full executable FEA pipeline.

## 7. Blade Surface Model

The current v0.3 blade surface is field-driven: hub/tip interpolation plus
`theta_field(u,v)`, `support_u(u,v)`, and thickness offset. v0.4 should replace this
as the authoring contract with a boundary-guided model:

```text
u: streamwise direction, leading edge -> trailing edge
v: spanwise direction, hub -> tip/shroud
```

Each blade first defines a camber surface. Pressure and suction surfaces are generated
from that camber surface and a thickness field.

```json
{
  "blade_surface_model": {
    "kind": "boundary_guided_camber_surface_with_thickness",
    "parameter_domain": {
      "u": "streamwise_leading_to_trailing",
      "v": "spanwise_hub_to_tip"
    },
    "boundary_curves": {
      "hub_edge": "conformed_to_hub_surface",
      "tip_edge": "conformed_to_tip_or_shroud_surface",
      "leading_edge": "spanwise_curve",
      "trailing_edge": "spanwise_curve"
    },
    "internal_guides": {
      "streamwise_guides": [],
      "spanwise_layers": []
    },
    "thickness_field": {},
    "output_surfaces": [
      "camber_surface",
      "pressure_surface",
      "suction_surface",
      "leading_edge_transition",
      "trailing_edge_transition",
      "root_transition",
      "tip_transition"
    ]
  }
}
```

`iso-u` curves should no longer be only sampled output. v0.4 should allow selected
`u = constant` curves to be represented as editable spanwise guide curves. The compiler
may infer other iso-lines from interpolation.

The default v0.4 implementation should support:

- variable control-point count hub/tip profiles,
- editable leading/trailing edge spanwise curves,
- one to three internal streamwise guide curves,
- thickness as a `u` curve first, with a reserved two-dimensional `u,v` field schema,
- sampled surface graph output with stable IDs,
- future compilation to exact NURBS surfaces when the geometry contract is stable.

Use this exactness label for the first implementation:

```json
{
  "cad_exactness": "research_grade_sampled_surface",
  "intended_cad_operation": "boundary_guided_nurbs_or_bspline_surface"
}
```

## 8. Variable NURBS Control Topology

v0.3 fixed meridional profile curves to four control points. v0.4 should allow curve
control topology to be part of the design-space definition.

Example:

```json
{
  "hub_profile": {
    "degree": 3,
    "control_point_count": 6,
    "knot_policy": "clamped_open_uniform",
    "weight_policy": "positive_editable_or_unit_locked"
  },
  "tip_profile": {
    "degree": 3,
    "control_point_count": 6,
    "knot_policy": "clamped_open_uniform"
  },
  "blade_guides": {
    "streamwise_guide_count": 3,
    "control_point_count_each": 6
  }
}
```

Inside a campaign, these counts become part of `frozen_campaign_signature`.

## 9. Feature Graph

Every feature should be a graph node, not only a scalar parameter.

```json
{
  "id": "root_fillet",
  "kind": "fillet",
  "owner": "blade_root_to_hub",
  "input_edges": [],
  "parameters": {},
  "generated_surfaces": [],
  "simulation_visibility": {},
  "validity_contracts": []
}
```

Blade transition features:

```json
{
  "blade_transition_features": {
    "leading_edge_round": {
      "kind": "rounded_edge_transition",
      "input_boundaries": ["pressure_leading_edge", "suction_leading_edge"],
      "parameters": ["leading_edge_radius_mm", "leading_edge_shape_factor"],
      "cfd_patch_group": "leading_edge_wall"
    },
    "trailing_edge_round": {
      "kind": "rounded_or_cutback_edge_transition",
      "input_boundaries": ["pressure_trailing_edge", "suction_trailing_edge"],
      "parameters": ["trailing_edge_radius_mm", "trailing_edge_cutback_mm"],
      "cfd_patch_group": "trailing_edge_wall"
    },
    "root_fillet": {
      "kind": "surface_blend",
      "input_boundaries": ["blade_root_boundary", "hub_surface_contact_curve"],
      "parameters": ["root_fillet_radius_mm"],
      "cfd_patch_group": "root_fillet_wall"
    },
    "tip_transition": {
      "kind": "tip_closure_or_shroud_blend",
      "input_boundaries": ["blade_tip_boundary", "tip_or_shroud_surface"],
      "parameters": ["tip_clearance_mm", "tip_fillet_radius_mm"],
      "cfd_patch_group": "tip_fillet_wall"
    }
  }
}
```

Open and closed impellers must differ in `tip_transition` semantics:

- Open impeller: exposed blade tip closure or rounded tip.
- Closed impeller: blade-to-shroud blend, included in the wetted wall.

Hub/hood features should define view-specific visibility:

```json
{
  "mounting_bore_top_fillet": {
    "kind": "axisymmetric_edge_fillet",
    "source_edge": "mounting_bore_top_edge",
    "radius_mm": 3.0,
    "simulation_visibility": {
      "cad_review_360": true,
      "cfd_full_360": false,
      "fea_solid": true
    }
  }
}
```

## 10. Assembly And Tuning Features

v0.4 should define both assembly/manufacturing features and tuning features, but only
the assembly/manufacturing group needs real implementation in this version.

Implemented in v0.4:

```json
{
  "assembly_features": {
    "mounting_bore": {
      "kind": "axisymmetric_subtractive_cylinder",
      "parameters": ["radius_mm", "z_start_mm", "z_end_mm"]
    },
    "shaft_seat": {
      "kind": "axisymmetric_step_or_counterbore",
      "parameters": ["radius_mm", "depth_mm"]
    },
    "keyway": {
      "kind": "angular_subtractive_slot",
      "parameters": ["width_mm", "depth_mm", "angular_position_deg"]
    },
    "rear_hub_groove": {
      "kind": "axisymmetric_rear_groove",
      "parameters": ["inner_radius_mm", "outer_radius_mm", "depth_mm"]
    }
  }
}
```

Schema-only in v0.4:

```json
{
  "tuning_features": {
    "balance_holes": {
      "status": "schema_only_v0_4"
    },
    "trim_edge": {
      "status": "schema_only_v0_4"
    },
    "lightening_slots": {
      "status": "schema_only_v0_4"
    }
  }
}
```

Assembly internals are normally suppressed from `cfd_full_360` and retained in
`cad_review_360` and future `fea_solid`.

## 11. CFD Manifest

The generated manifest should include:

```json
{
  "simulation_manifests": {
    "cfd_full_360": {
      "domain_kind": "full_360_wetted_surface",
      "status": "research_grade_executable",
      "source_geometry_id": "axisymmetric_throughflow_radial_bladed.v0_4",
      "feature_suppression": {},
      "patch_groups": {},
      "patch_instances": {},
      "mesh_hints": {},
      "validity": {}
    }
  }
}
```

Required patch groups:

```text
blade_pressure_wall
blade_suction_wall
leading_edge_wall
trailing_edge_wall
root_fillet_wall
tip_fillet_wall
hub_wall
tip_or_shroud_wall
inlet_patch
outlet_patch
```

Group example:

```json
{
  "blade_pressure_wall": {
    "type": "wall",
    "surface_role": "blade_pressure",
    "instances": [
      "blade_00_pressure_surface",
      "blade_01_pressure_surface"
    ]
  }
}
```

Instance example:

```json
{
  "blade_07_root_fillet": {
    "group": "root_fillet_wall",
    "source_feature": "blade_07.root_fillet",
    "surface_graph_id": "blade_07_root_transition"
  }
}
```

Mesh hints should be included but treated as adapter-neutral:

```json
{
  "mesh_hints": {
    "global": {
      "target_surface_size_mm": 4.0,
      "curvature_refinement": true,
      "min_feature_size_mm": 1.0
    },
    "patch_overrides": {
      "leading_edge_wall": {
        "target_surface_size_mm": 1.2,
        "inflation_layers": 8
      },
      "root_fillet_wall": {
        "target_surface_size_mm": 1.0,
        "inflation_layers": 10
      }
    }
  }
}
```

## 12. Validity Contracts

Geometry validity:

- curve values are finite,
- radii are positive where required,
- generated surfaces have nonzero area,
- no NaN or Inf coordinates,
- blade root/tip boundaries conform to support surfaces,
- transition surfaces connect declared input boundaries within tolerance.

Topology validity:

- every feature source edge exists,
- every generated feature surface is registered in the surface graph,
- every wetted surface belongs to exactly one CFD patch group,
- every required CFD patch group has at least one instance,
- suppressed assembly features do not appear in CFD patch groups,
- patch group names are stable across numeric parameter changes.

Engineering validity:

- root fillet radius is within local thickness bounds,
- trailing edge thickness is above minimum,
- keyway depth does not violate minimum hub wall thickness,
- mounting bore radius is compatible with hub radius,
- campaign signature exists before high-throughput execution.

## 13. Frontend Changes

Add a design-space editor:

- edit control-point counts, degrees, weights, knots,
- edit guide curve counts,
- enable/disable features,
- show campaign signature and design vector length,
- disable topology edits after campaign freeze.

Add a surface/feature graph inspector:

- list surfaces by id, role, material/wetted/internal/construction status,
- list feature nodes, generated surfaces, and simulation visibility,
- expose validity status by feature and surface.

Add a CFD view panel:

- list patch groups and instances,
- show suppressed features,
- show mesh hints,
- allow selecting a group or instance and highlighting it in the viewer.

Update geometry viewer modes:

```text
CAD review view:
  material solids, construction support optional, feature debug optional

CFD full 360 view:
  wetted and CFD transition surfaces only, color by patch group

Feature debug view:
  color by feature owner, source edges visible
```

Curve editors should support add/remove/refine points in design-space mode, but lock
control topology in campaign mode.

## 14. Testing Strategy

DSL/schema tests:

- v0.4 schema contains `design_space`, `surface_graph_contract`,
  `feature_graph_contract`, and `simulation_views`,
- topology variables and design variables are separated,
- `cfd_full_360` exists and is executable in v0.4,
- `fea_solid` exists with `schema_only_v0_4`,
- patch naming policy is `group_and_instance`.

Kernel/compiler tests:

- variable profile control-point counts are accepted,
- generated knots and weights have valid lengths,
- blade graph contains camber, pressure, suction, and transition surfaces,
- feature graph nodes generate declared surfaces,
- campaign signature remains stable under numeric-only parameter changes.

CFD manifest tests:

- all wetted surfaces are assigned to exactly one CFD patch group,
- construction-only surfaces do not appear in CFD view,
- mounting bore, keyway, shaft seat, and rear hub groove are suppressed in CFD view,
- every required patch group has instances,
- blade count `N` produces `N` pressure, suction, root-fillet, and tip-transition
  instances,
- patch group names remain stable across parameter sweeps,
- manifest includes area estimates and validity report.

Frontend tests:

- add/remove control points changes design space only in design-space mode,
- campaign freeze disables topology edits,
- CFD panel renders group and instance names,
- clicking a patch group creates a viewer highlight selection,
- CFD view hides suppressed features.

## 15. Research And Industry Basis

The design follows industry practice where turbomachinery blade authoring is usually
performed through meridional contours, blade angle/wrap, thickness, leading/trailing
edge, spanwise sections, stacking, bow/lean/sweep, and derived pressure/suction
surfaces, rather than direct manual editing of a raw full tensor-product NURBS control
net.

References used during the discussion:

- CFturbo impeller workflow and meridional/blade-angle/profile documentation:
  <https://cfturbo.com/software/impellers>
  <https://manual.cfturbo.com/en/mercon.html>
  <https://manual.cfturbo.com/en/x-beta-blade-angle-progression.html>
  <https://manual.cfturbo.com/en/prof.html>
- Ansys BladeModeler documentation and radial angle/thickness workflow:
  <https://www.ansys.com/products/fluids/ansys-blademodeler>
  <https://www.aprens.com/pdfs_V11.0/blademodeler11.pdf>
- Concepts NREC AxCent blade stacking, swept edges, mid-span sections, and fillets:
  <https://www.conceptsnrec.com/axcent-software>
- ADT TURBOdesign inverse-design loading workflow:
  <https://www.adtechnology.com/products/3d-inverse-design-turbomachinery>
  <https://blog.adtechnology.com/what-is-blade-loading>
- Research examples on B-spline/NURBS turbomachinery blade parameterization:
  <https://repository.tudelft.nl/file/File_f54e874b-a8e0-4c84-8f5b-912f7dd289f7>
  <https://www.mdpi.com/2226-4310/9/9/489>

## 16. Update Log

2026-07-01:

- Accepted current v0.3 geometry and parameters as a research baseline pending future
  expert interview feedback.
- Identified four v0.4 pressure points: real edge transitions, feature grammar,
  variable control topology, and explicit iso-u/iso-v blade surface construction.
- Selected balanced v0.4 scope instead of a single-feature patch.
- Selected CFD + FEA dual simulation view concept.
- Selected CFD executable-first implementation depth.
- Selected full 360 CFD wetted geometry as first CFD executable target.
- Selected group + instance patch naming.
- Selected surface/feature graph compiler architecture.
- Deferred periodic sector generation, full CAD/CAE campaign platform, and exact
  industrial B-Rep filleting.

## 17. Open Risks

- Sampled blend surfaces may not be sufficient for downstream industrial meshers; the
  manifest must mark exactness honestly.
- Full 360 CFD will be heavier than periodic-sector CFD; later versions should add a
  sector view once patch naming and surface graph identity are stable.
- Variable control topology can make optimization unstable unless campaign freeze is
  enforced consistently in frontend, DSL, and compiler.
- Feature suppression must not silently remove wetted surfaces or leave the CFD view
  topologically open.

