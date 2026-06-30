# Impeller Ontology Slice And DSL File Structure Design

Date: 2026-06-30
Status: review draft
Decision basis: `2026-06-30-axisymmetric-throughflow-impeller-ars-literature-review.md`

## 1. Purpose

This spec defines the first serious impeller ontology slice and DSL file structure for
the local deterministic part-rule synthesis system.

The goal is not to model all impellers. The goal is to define one narrow, inspectable
object well enough that:

- an agent or human can author a DSL instance from ontology-facing concepts,
- the local constructor can deterministically generate a named surface graph,
- shaded geometry and construction lines come from the same surfaces,
- open and closed radial impellers share a consistent mathematical model,
- NURBS control topology, editable variables, and optimization variables are explicit
  DSL assets instead of hidden kernel heuristics,
- geometry/topology defects can become structured loss records.

## 2. Fixed Decisions

Use file-structured JSON, not Python dictionaries as the canonical source of truth.

Use this first ontology slice:

```text
AxisymmetricThroughflowRadialBladedImpeller
```

Use JSON for v0.2 authoring and runtime loading. YAML authoring can be introduced later
as a convenience layer, but v0.2 must not require a YAML dependency.

Retain the blade tip support surface for both open and closed impellers. In open
impellers it is a mathematical reference surface, not a material shroud. In closed
impellers it corresponds to the front shroud inner support surface.

Represent all four blade boundaries explicitly:

```text
P(u, v)

v = 0: blade_root_boundary
v = 1: blade_tip_boundary
u = 0: leading_edge_boundary
u = 1: trailing_edge_boundary
```

`u=0` and `u=1` are leading/trailing blade boundaries, not generic inlet/outlet
boundaries. They may be near the inlet/outlet flow-path boundaries, but they are separate
blade topology objects.

Treat NURBS shape control as a first-class layer. The constructor may infer initial
control-point coordinates from high-level dimensions, but the resulting degree, control
net size, knot policy, weights, semantic handles, locked variables, and optimizable
variables must be declared in JSON. This prevents the kernel from silently changing
shape degrees of freedom that later need to be reviewed, optimized, or corrected through
human feedback.

For v0.2, use a conservative optimization stage: fixed degree, fixed control-point
count, fixed knot policy, positive unit weights, and editable control-point coordinates.
Later stages can unlock control-point count, knot placement, and rational weights after
geometry validity checks are stronger.

## 3. Non-Goals

This slice does not include:

- mixed-flow impellers,
- axial impellers or propeller-style blades,
- vortex/free-flow/recessed impellers,
- single-channel, multi-channel, or cutter impellers,
- double-entry/double-suction impellers,
- splitter blades,
- non-axisymmetric hub or shroud surfaces,
- full CFD inverse design,
- strict CAD B-Rep sewing as the first validation target.

The first validation target is a coherent named surface graph and sampled preview mesh.
Strict STEP B-Rep solids are a later exporter target.

## 4. Recommended File Layout

```text
src/part_rule_synthesis/
  ontology/
    impeller/
      v0_2/
        slice.json
        entities.json
        relations.json
        shape_control_schema.json
        validity_contracts.json
        loss_schema.json

  dsl/
    impeller/
      axisymmetric_throughflow_radial_bladed/
        v0_2/
          schema.json
          constructors/
            open_impeller.json
            closed_impeller.json
          shape_controls/
            default_shape_controls.json
          presets/
            radial_open_reference.json
            radial_closed_reference.json
```

The ontology files define vocabulary, relationships, validity contracts, and loss shape.
The DSL files define constructible rules and parameterized instances.

Python code should load these JSON files, validate them, and compile them into the
existing runtime `rule.json` shape for API compatibility.

## 5. Layer Responsibilities

### 5.1 Ontology Slice

Ontology answers:

- What object class is being described?
- What entities exist?
- What relationships are meaningful?
- What constraints define semantic validity?
- What kinds of loss can be recorded?

Ontology must not contain:

- executable geometry algorithms,
- numeric presets,
- frontend UI ranges,
- CAD-export implementation details.

### 5.2 DSL Schema

DSL schema answers:

- Which sections must a constructible rule instance contain?
- What representations are allowed for curves, surfaces, fields, and closures?
- Which fields are required for open and closed variants?
- Which ontology entities and contracts the DSL instance claims to satisfy.

### 5.3 DSL Constructor Instance

Constructor files answer:

- How to build the open or closed variant of this constructor family?
- Which support surfaces, material domains, blade boundaries, blade surface construction,
  edge closures, and validation checks are required?

### 5.4 Presets

Preset files answer:

- What initial numerical values should be used for a study case?
- Which constructor file do they bind to?
- Which parameters are exposed for user editing?

Presets are not ontology. Presets are not the constructor family.

### 5.5 Shape Control

Shape-control files answer:

- Which NURBS entities are controlled directly?
- Which degree, control-point count, knot policy, and weight policy are locked?
- Which control-point coordinates or semantic handles are editable by a human?
- Which variables are allowed to become optimization variables in the current stage?
- Which constraints must remain satisfied after a manual edit or optimization patch?

Shape control sits between high-level engineering parameters and the geometry kernel.
Presets provide initial values; shape control declares how those values populate NURBS
control nets and which parts of those control nets are legitimate design degrees of
freedom.

### 5.6 Runtime Manifest

Manifest answers:

- What was actually instantiated?
- What surface graph was generated?
- Which construction lines were sampled?
- Which validity contracts passed, warned, or failed?
- What loss records were emitted?

## 6. Ontology Slice File

File:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/slice.json
```

Proposed shape:

```json
{
  "ontology_version": "0.2",
  "slice_id": "impeller.axisymmetric_throughflow_radial_bladed",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "definition": "A radial throughflow impeller constructor whose blade passages are bounded by axisymmetric hub and blade-tip support surfaces, and whose blades are finite-thickness surface graphs with pressure/suction sides, leading/trailing edge closures, root/tip treatment, and explicit material-domain contracts.",
  "in_scope": {
    "part_family": ["impeller"],
    "flow_topology": ["radial"],
    "passage_topology": ["throughflow_bladed_channel"],
    "shroud_topology": ["open", "closed"],
    "entry_topology": ["single_entry"],
    "blade_population": ["full_blade_set"],
    "support_surface_model": ["axisymmetric_revolved_meridional_profiles"],
    "blade_surface_model": ["meanline_thickness_edge_surface_graph"]
  },
  "out_of_scope": [
    "mixed_flow",
    "axial_flow",
    "recessed_vortex",
    "single_channel",
    "multi_channel",
    "cutter",
    "double_entry",
    "splitter_blades",
    "non_axisymmetric_support_surfaces"
  ],
  "source_refs": [
    "ksb_impeller",
    "cfturbo_meridional_contour",
    "cfturbo_blade_profiles",
    "cfturbo_blade_edges",
    "caeses_shrouded_impeller_geometry",
    "agromayor_2021_unified_parametrization"
  ]
}
```

## 7. Entity File

File:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/entities.json
```

Proposed shape:

```json
{
  "coordinate_system": [
    "rotation_axis",
    "meridional_plane",
    "cylindrical_frame"
  ],
  "primary_flow_path": [
    "hub_meridional_profile",
    "blade_tip_meridional_profile",
    "inlet_flow_path_boundary",
    "outlet_flow_path_boundary",
    "meridional_channel_wire"
  ],
  "support_surfaces": [
    "hub_support_surface",
    "blade_tip_support_surface"
  ],
  "material_domain": [
    "hub_material_solid",
    "mounting_bore",
    "back_disk_or_back_shroud",
    "front_shroud_material_solid",
    "material_closure_faces"
  ],
  "blade": [
    "blade_mean_surface",
    "blade_root_boundary",
    "blade_tip_boundary",
    "leading_edge_boundary",
    "trailing_edge_boundary",
    "pressure_surface",
    "suction_surface",
    "leading_edge_closure_surface",
    "trailing_edge_closure_surface",
    "root_closure_or_fillet_surface",
    "tip_closure_or_shroud_join_surface"
  ],
  "topology": [
    "blade_instance",
    "blade_pattern",
    "surface_graph",
    "adjacency_graph",
    "named_boundary_curve"
  ],
  "shape_control": [
    "shape_control_policy",
    "shape_control_variable",
    "semantic_handle",
    "control_point_coordinate",
    "control_net_topology",
    "knot_vector_policy",
    "weight_policy",
    "shape_loss_record",
    "shape_patch"
  ],
  "validation": [
    "geometry_validity_report",
    "topology_validity_report",
    "engineering_warning_report",
    "loss_record"
  ]
}
```

## 8. Relations File

File:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/relations.json
```

Proposed shape:

```json
{
  "relations": [
    "revolves_about(profile_curve, rotation_axis)",
    "generates_surface(profile_curve, support_surface)",
    "bounds_meridional_channel(hub_meridional_profile, blade_tip_meridional_profile)",
    "lies_on(boundary_curve, support_surface)",
    "conforms_to(blade_root_boundary, hub_support_surface)",
    "conforms_to(blade_tip_boundary, blade_tip_support_surface)",
    "connects_between(leading_edge_boundary, hub_support_surface, blade_tip_support_surface)",
    "connects_between(trailing_edge_boundary, hub_support_surface, blade_tip_support_surface)",
    "offsets_from(pressure_surface, blade_mean_surface)",
    "offsets_from(suction_surface, blade_mean_surface)",
    "closes_between(edge_closure_surface, pressure_surface, suction_surface)",
    "joins_to(root_closure_or_fillet_surface, hub_material_solid)",
    "joins_to(tip_closure_or_shroud_join_surface, blade_tip_support_surface)",
    "patterns_around_axis(blade_instance, rotation_axis)",
    "shares_boundary(surface_a, surface_b, named_boundary_curve)",
    "encloses_material(surface_graph, material_domain)",
    "controls_shape_of(shape_control_policy, target_entity)",
    "parameterizes(shape_control_variable, control_point_coordinate)",
    "locks_topology(control_net_topology, target_entity)",
    "defines_knot_vector(knot_vector_policy, target_entity)",
    "defines_weights(weight_policy, target_entity)",
    "exposes_handle(semantic_handle, shape_control_variable)",
    "patches_shape(shape_patch, shape_control_policy)",
    "records_shape_loss(shape_loss_record, target_entity)"
  ]
}
```

## 9. Blade Tip Support Surface Semantics

Use the term:

```text
blade_tip_support_surface
```

Do not use unqualified `tip_surface` in DSL fields. The word "tip" alone is ambiguous:
it can mean blade tip, shroud inner surface, casing clearance, or outer meridional
boundary.

Open impeller semantics:

```json
{
  "blade_tip_support_surface": {
    "role": "reference_only",
    "material": false,
    "generated_from": "blade_tip_meridional_profile",
    "purpose": [
      "blade_v1_conformance",
      "tip_edge_closure",
      "tip_clearance_reference",
      "open_closed_kernel_consistency"
    ]
  }
}
```

Closed impeller semantics:

```json
{
  "blade_tip_support_surface": {
    "role": "front_shroud_inner_surface",
    "material": true,
    "generated_from": "blade_tip_meridional_profile",
    "purpose": [
      "blade_v1_conformance",
      "tip_shroud_join",
      "flow_path_boundary"
    ]
  }
}
```

This keeps open and closed impellers mathematically consistent while avoiding the false
claim that open impellers have a material shroud.

## 10. Blade Boundary Model

Every blade surface must expose four primary boundary curves:

```text
P(u, v)

v = 0: blade_root_boundary
v = 1: blade_tip_boundary
u = 0: leading_edge_boundary
u = 1: trailing_edge_boundary
```

`blade_height` is not a substitute for these boundary curves. Blade height can help
derive the blade-tip support surface or span distance, but it cannot fully define leading
edge direction, trailing edge direction, sweep, lean, or spanwise curvature.

Proposed DSL section:

```json
{
  "blade_boundaries": {
    "root": {
      "id": "blade_root_boundary",
      "parameter": "v=0",
      "support_surface": "hub_support_surface",
      "conformance": "required"
    },
    "tip": {
      "id": "blade_tip_boundary",
      "parameter": "v=1",
      "support_surface": "blade_tip_support_surface",
      "conformance": "required"
    },
    "leading_edge": {
      "id": "leading_edge_boundary",
      "parameter": "u=0",
      "kind": "spanwise_nurbs_curve",
      "hub_anchor": {"on": "hub_support_surface"},
      "tip_anchor": {"on": "blade_tip_support_surface"},
      "controls": {
        "spanwise_shape": "linear | bezier | nurbs",
        "meridional_sweep_law": "constant | linear | bspline",
        "circumferential_lean_law": "constant | linear | bspline"
      }
    },
    "trailing_edge": {
      "id": "trailing_edge_boundary",
      "parameter": "u=1",
      "kind": "spanwise_nurbs_curve",
      "hub_anchor": {"on": "hub_support_surface"},
      "tip_anchor": {"on": "blade_tip_support_surface"},
      "controls": {
        "spanwise_shape": "linear | bezier | nurbs",
        "meridional_sweep_law": "constant | linear | bspline",
        "circumferential_lean_law": "constant | linear | bspline"
      }
    }
  }
}
```

## 11. Blade Surface Construction

The blade surface should not be implicitly assumed to be a ruled surface.

Supported construction modes for v0.2 schema:

```json
{
  "blade_surface_construction": {
    "allowed_kinds": [
      "nurbs_coons_with_internal_controls",
      "beta_integrated_surface",
      "ruled_surface"
    ],
    "default_kind": "nurbs_coons_with_internal_controls"
  }
}
```

Recommended first constructor mode:

```json
{
  "blade_surface_construction": {
    "kind": "nurbs_coons_with_internal_controls",
    "boundary_contract": "four_boundary_curves_required",
    "internal_shape_controls": {
      "theta_law": "beta_integral",
      "wrap_angle": "parameterized",
      "camber_control_points": "parameterized",
      "spanwise_twist_law": "parameterized"
    }
  }
}
```

Ruled surface mode is allowed only when declared explicitly:

```json
{
  "blade_surface_construction": {
    "kind": "ruled_surface",
    "ruling_direction": "spanwise",
    "start_curve": "blade_root_boundary",
    "end_curve": "blade_tip_boundary"
  }
}
```

If a blade is generated as a ruled surface, the manifest must say so. The UI must not
make a curved NURBS blade look like it was controlled only by blade height.

## 11A. NURBS Shape-Control Layer

The current kernel risk is that NURBS control points, degree, knots, and weights are
created by internal rules. That is acceptable for a prototype preview, but it is not
acceptable for an ontology-facing constructor that must learn from human, simulation,
manufacturing, and CAM feedback.

For v0.2, every constructible NURBS feature must declare a shape-control policy. The
policy separates five concerns:

1. `target_entity`: the ontology entity being shaped.
2. `representation_topology`: degree, control-point count, knot policy, and weight
   policy.
3. `control_variables`: coordinates, weights, knots, or derived handles that can be
   edited or optimized.
4. `semantic_handles`: human-facing parameters that map to one or more low-level NURBS
   variables.
5. `constraints`: validity contracts that must remain true after editing.

Required target entities for the first slice:

```json
[
  "hub_meridional_profile",
  "blade_tip_meridional_profile",
  "leading_edge_boundary",
  "trailing_edge_boundary",
  "blade_mean_surface",
  "blade_thickness_distribution",
  "leading_edge_closure_surface",
  "trailing_edge_closure_surface",
  "root_closure_or_fillet_surface",
  "tip_closure_or_shroud_join_surface"
]
```

Shape-control schema file:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/shape_control_schema.json
```

Proposed shape:

```json
{
  "shape_control_schema_version": "0.2",
  "allowed_representations": [
    "nurbs_curve_rz",
    "nurbs_curve_xyz",
    "nurbs_surface_uv_xyz",
    "scalar_field_uv"
  ],
  "optimization_stages": [
    {
      "stage": 1,
      "name": "coordinate_only",
      "degree": "locked",
      "control_point_count": "locked",
      "knot_vector": "locked",
      "weights": "locked_positive_unit",
      "control_point_coordinates": "editable_optimizable"
    },
    {
      "stage": 2,
      "name": "finite_control_net_choices",
      "degree": "locked",
      "control_point_count": "finite_choices",
      "knot_vector": "regenerated_from_policy",
      "weights": "locked_positive_unit",
      "control_point_coordinates": "editable_optimizable"
    },
    {
      "stage": 3,
      "name": "knot_policy_search",
      "degree": "locked_or_finite_choices",
      "control_point_count": "finite_choices",
      "knot_vector": "policy_or_interior_knots_optimizable",
      "weights": "locked_positive_unit",
      "control_point_coordinates": "editable_optimizable"
    },
    {
      "stage": 4,
      "name": "rational_nurbs_search",
      "degree": "finite_choices",
      "control_point_count": "finite_choices",
      "knot_vector": "policy_or_interior_knots_optimizable",
      "weights": "positive_bounded_optimizable",
      "control_point_coordinates": "editable_optimizable"
    }
  ],
  "default_stage": 1
}
```

Default DSL shape-control file:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/shape_controls/default_shape_controls.json
```

Example target policy:

```json
{
  "target_entity": "hub_meridional_profile",
  "representation": "nurbs_curve_rz",
  "representation_topology": {
    "degree": 3,
    "control_point_count": 6,
    "knot_policy": "clamped_uniform",
    "weights": "unit"
  },
  "control_variables": [
    {
      "id": "hub_cp_0_r",
      "kind": "control_point_coordinate",
      "coordinate": "r",
      "control_point_index": 0,
      "editable": true,
      "optimizable": true,
      "bounds_mm": [40.0, 220.0]
    },
    {
      "id": "hub_cp_0_z",
      "kind": "control_point_coordinate",
      "coordinate": "z",
      "control_point_index": 0,
      "editable": true,
      "optimizable": true,
      "bounds_mm": [-120.0, 40.0]
    }
  ],
  "semantic_handles": [
    {
      "id": "hub_base_radius",
      "maps_to": ["hub_cp_0_r", "hub_cp_1_r"],
      "intent": "Set lower hub radius; must remain larger than upper hub nose radius."
    },
    {
      "id": "hub_nose_radius",
      "maps_to": ["hub_cp_4_r", "hub_cp_5_r"],
      "intent": "Set upper hub radius near the inlet eye."
    },
    {
      "id": "hub_profile_convexity",
      "maps_to": ["hub_cp_2_r", "hub_cp_3_r", "hub_cp_2_z", "hub_cp_3_z"],
      "intent": "Adjust meridional bulge without reversing profile orientation."
    }
  ],
  "constraints": [
    "radius_positive",
    "hub_profile_base_radius_greater_than_nose_radius",
    "nurbs_knot_vector_non_decreasing",
    "control_net_dimension_matches_degree",
    "hub_tip_profiles_do_not_cross"
  ]
}
```

This layer changes how feedback is represented. A human comment such as "the hub curve is
reversed" should not only become `change_default_parameter`; it should become a shape
loss record that targets the relevant semantic handles and constraints:

```json
{
  "loss_id": "loss-human-hub-profile-reversed-001",
  "source": "human_review",
  "raw_feedback": "Hub curve is reversed; bottom radius should be larger and top radius smaller.",
  "target_entities": ["hub_meridional_profile", "hub_support_surface"],
  "violated_contracts": [
    "hub_profile_base_radius_greater_than_nose_radius",
    "meridional_profile_orientation"
  ],
  "patch_intents": [
    "change_control_point_coordinates",
    "tighten_shape_constraint",
    "add_regression_test"
  ],
  "shape_patch": {
    "target_policy": "hub_meridional_profile.default",
    "semantic_handles": ["hub_base_radius", "hub_nose_radius"],
    "locked_topology": true
  },
  "approval_status": "accepted"
}
```

The UI should therefore expose two levels of shape editing:

- semantic handles for normal engineering review,
- optional control-net editing for advanced debugging and future optimization studies.

The manifest must record whether each shape came from a default rule, an explicit DSL
control net, a human-approved patch, or an optimizer-produced patch.

## 12. DSL Schema File

File:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/schema.json
```

Proposed high-level shape:

```json
{
  "dsl_version": "0.2",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "required_sections": [
    "classification",
    "coordinate_system",
    "main_dimensions",
    "primary_flow_path",
    "support_surfaces",
    "shape_control",
    "material_domain",
    "blade_pattern",
    "blade_boundaries",
    "blade_surface_construction",
    "blade_profile",
    "blade_edges",
    "surface_graph",
    "validation"
  ],
  "variant_rules": {
    "open": {
      "blade_tip_support_surface.material": false,
      "blade_tip_support_surface.role": "reference_only",
      "front_shroud_material_solid": "forbidden"
    },
    "closed": {
      "blade_tip_support_surface.material": true,
      "blade_tip_support_surface.role": "front_shroud_inner_surface",
      "front_shroud_material_solid": "required"
    }
  }
}
```

The first implementation can validate this with a lightweight Python checker. A full
JSON Schema validator can be introduced later if needed.

## 13. Open Constructor File

File:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/open_impeller.json
```

Proposed shape:

```json
{
  "dsl_version": "0.2",
  "constructor_id": "axisymmetric_throughflow_radial_bladed.open",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "classification": {
    "part_family": "impeller",
    "flow_topology": "radial",
    "passage_topology": "throughflow_bladed_channel",
    "shroud_topology": "open",
    "entry_topology": "single_entry",
    "blade_population": "full_blade_set",
    "working_domain": "pump"
  },
  "coordinate_system": {
    "units": "mm",
    "frame": "cylindrical",
    "rotation_axis": "z",
    "positive_rotation": "counterclockwise_viewed_from_inlet"
  },
  "support_surfaces": {
    "hub_support_surface": {
      "kind": "revolved_nurbs_surface",
      "source_profile": "hub_meridional_profile"
    },
    "blade_tip_support_surface": {
      "kind": "revolved_nurbs_surface",
      "source_profile": "blade_tip_meridional_profile",
      "role": "reference_only",
      "material": false
    }
  },
  "shape_control": {
    "shape_control_ref": "shape_controls/default_shape_controls.json",
    "optimization_stage": 1,
    "target_entities": [
      "hub_meridional_profile",
      "blade_tip_meridional_profile",
      "leading_edge_boundary",
      "trailing_edge_boundary",
      "blade_mean_surface",
      "blade_thickness_distribution"
    ]
  },
  "material_domain": {
    "hub": {
      "kind": "revolved_solid_with_bore",
      "requires_back_face": true,
      "requires_mounting_bore": true
    },
    "front_shroud": {
      "kind": "none"
    }
  },
  "blade_boundaries": {
    "root": {"support_surface": "hub_support_surface", "parameter": "v=0"},
    "tip": {"support_surface": "blade_tip_support_surface", "parameter": "v=1"},
    "leading_edge": {"kind": "spanwise_nurbs_curve", "parameter": "u=0"},
    "trailing_edge": {"kind": "spanwise_nurbs_curve", "parameter": "u=1"}
  },
  "blade_surface_construction": {
    "kind": "nurbs_coons_with_internal_controls",
    "boundary_contract": "four_boundary_curves_required"
  },
  "blade_edges": {
    "leading_edge": {"kind": "ellipse"},
    "trailing_edge": {"kind": "ellipse"},
    "root": {"kind": "fillet_patch"},
    "tip": {"kind": "exposed_closed_edge"}
  }
}
```

## 14. Closed Constructor File

File:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/constructors/closed_impeller.json
```

The closed constructor mirrors the open constructor, except:

```json
{
  "classification": {
    "shroud_topology": "closed"
  },
  "support_surfaces": {
    "blade_tip_support_surface": {
      "kind": "revolved_nurbs_surface",
      "source_profile": "blade_tip_meridional_profile",
      "role": "front_shroud_inner_surface",
      "material": true
    }
  },
  "shape_control": {
    "shape_control_ref": "shape_controls/default_shape_controls.json",
    "optimization_stage": 1
  },
  "material_domain": {
    "front_shroud": {
      "kind": "revolved_material_shell",
      "inner_surface": "blade_tip_support_surface",
      "requires_outer_surface": true,
      "requires_inlet_eye_opening": true
    }
  },
  "blade_edges": {
    "tip": {
      "kind": "shroud_join"
    }
  }
}
```

## 15. Preset Files

Preset files bind numerical defaults to constructor files.

Example:

```text
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2/presets/radial_open_reference.json
```

Proposed shape:

```json
{
  "preset_id": "radial_open_reference",
  "constructor_id": "axisymmetric_throughflow_radial_bladed.open",
  "display_name": "Radial open reference",
  "parameter_values": {
    "blade_count": 7,
    "inlet_diameter_mm": 360.0,
    "outlet_diameter_mm": 1240.0,
    "bore_radius_mm": 40.0,
    "wrap_angle_deg": 115.0
  },
  "editable_parameters": [
    "blade_count",
    "inlet_diameter_mm",
    "outlet_diameter_mm",
    "wrap_angle_deg",
    "leading_edge_lean_deg",
    "trailing_edge_lean_deg",
    "blade_thickness_mid_mm",
    "root_fillet_radius_mm"
  ],
  "source_refs": [
    "research_inferred_initial_values",
    "cfturbo_design_workflow"
  ]
}
```

`editable_parameters` should expose engineering-relevant controls. Avoid generic controls
such as `blade_curve_gain` unless they are retained only as a legacy alias.

## 16. Validity Contracts File

File:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/validity_contracts.json
```

Proposed categories:

```json
{
  "geometry_contracts": [
    "radius_positive",
    "hub_tip_profiles_do_not_cross",
    "no_internal_axis_touch",
    "blade_root_boundary_conforms_to_hub_support_surface",
    "blade_tip_boundary_conforms_to_blade_tip_support_surface",
    "leading_edge_boundary_connects_hub_to_tip_support",
    "trailing_edge_boundary_connects_hub_to_tip_support",
    "pressure_suction_surfaces_do_not_swap",
    "nurbs_degree_allowed",
    "control_net_dimension_matches_degree",
    "nurbs_knot_vector_non_decreasing",
    "nurbs_knot_multiplicity_valid",
    "nurbs_weights_positive",
    "hub_profile_base_radius_greater_than_nose_radius",
    "shape_control_variables_within_bounds",
    "construction_lines_sampled_from_surface_graph"
  ],
  "topology_contracts": [
    "blade_has_four_primary_boundaries",
    "blade_has_pressure_and_suction_surfaces",
    "blade_has_leading_and_trailing_edge_closures",
    "blade_has_root_and_tip_treatment",
    "open_impeller_has_no_front_shroud_material",
    "closed_impeller_has_front_shroud_material",
    "adjacent_surfaces_share_named_boundary_curves",
    "hub_material_domain_has_bore_and_back_face"
  ],
  "engineering_warnings": [
    "beta_angle_plausibility",
    "wrap_angle_plausibility",
    "blade_count_plausibility",
    "leading_edge_thickness_plausibility",
    "root_fillet_radius_positive",
    "bore_wall_thickness_plausibility",
    "shape_control_stage_matches_validation_strength"
  ]
}
```

Geometry and topology contracts can fail. Engineering contracts should warn in v0.2.

## 17. Loss Schema File

File:

```text
src/part_rule_synthesis/ontology/impeller/v0_2/loss_schema.json
```

Proposed shape:

```json
{
  "loss_record_schema_version": "0.2",
  "required_fields": [
    "loss_id",
    "source",
    "raw_feedback",
    "target_entities",
    "violated_contracts",
    "patch_intents",
    "shape_patch",
    "evidence_artifacts",
    "approval_status"
  ],
  "source_values": [
    "human_review",
    "geometry_validator",
    "topology_validator",
    "cad_exporter",
    "mesh_precheck",
    "engineering_precheck"
  ],
  "patch_intent_values": [
    "add_entity",
    "add_relation",
    "rename_concept",
    "split_concept",
    "tighten_contract",
    "tighten_shape_constraint",
    "add_constructor_field",
    "change_constructor_algorithm",
    "change_default_parameter",
    "add_shape_control_policy",
    "change_control_point_coordinates",
    "change_control_point_count",
    "change_knot_policy",
    "change_degree",
    "change_weight_policy",
    "lock_shape_variable",
    "unlock_shape_variable",
    "add_regression_test"
  ]
}
```

Example mapped from prior human feedback:

```json
{
  "loss_id": "loss-human-hub-profile-reversed-001",
  "source": "human_review",
  "raw_feedback": "Hub curve is reversed; bottom radius should be larger and top radius smaller.",
  "target_entities": ["hub_meridional_profile", "hub_support_surface"],
  "violated_contracts": ["meridional_profile_orientation"],
  "patch_intents": ["tighten_contract", "add_regression_test"],
  "approval_status": "accepted"
}
```

## 18. Runtime Loading And API Compatibility

The first implementation should keep the existing API stable:

```text
GET /api/ontology
POST /api/rule-engines/synthesize
POST /api/rule-engines/{engine_id}/instantiate
```

But internally:

1. Load ontology slice JSON.
2. Load DSL schema JSON.
3. Load shape-control schema JSON.
4. Load constructor JSON.
5. Load shape-control policy JSON.
6. Load preset JSON.
7. Validate constructor, shape-control policy, and preset against lightweight
   required-section checks.
8. Compile the JSON files into the current `rule.json` runtime object.
9. Instantiate geometry from the compiled DSL.
10. Emit manifest with `ontology_slice`, `constructor_family`, `constructor_id`,
    `surface_graph`, `shape_control`, `validity`, and `loss_records`.

Existing preset IDs can remain as aliases for a short transition:

```json
{
  "legacy_aliases": {
    "axisymmetric_nurbs_open_throughflow_study": "radial_open_reference",
    "axisymmetric_nurbs_closed_throughflow_study": "radial_closed_reference"
  }
}
```

## 19. Manifest Requirements

Every generated impeller manifest should include:

```json
{
  "ontology_slice": "impeller.axisymmetric_throughflow_radial_bladed",
  "constructor_family": "AxisymmetricThroughflowRadialBladedImpeller",
  "constructor_id": "axisymmetric_throughflow_radial_bladed.open",
  "dsl_version": "0.2",
  "surface_graph": {
    "surfaces": [],
    "named_boundary_curves": [],
    "adjacency": []
  },
  "shape_control": {
    "schema_version": "0.2",
    "optimization_stage": 1,
    "active_policies": [],
    "shape_optimization_space": {
      "editable_variables": [],
      "optimizable_variables": [],
      "locked_topology": true
    },
    "provenance": {
      "source": "default_rule | explicit_dsl_control_net | human_patch | optimizer_patch"
    }
  },
  "construction_lines": {
    "hub_support_surface": [],
    "blade_tip_support_surface": [],
    "blade_root_boundary": [],
    "blade_tip_boundary": [],
    "leading_edge_boundary": [],
    "trailing_edge_boundary": [],
    "pressure_surface_uv": [],
    "suction_surface_uv": [],
    "edge_closure_uv": []
  },
  "validity": {
    "geometry_contracts": [],
    "topology_contracts": [],
    "engineering_warnings": []
  },
  "loss_records": []
}
```

`construction_lines` must be sampled from the same surface graph as shaded geometry.
No independent proxy wireframe is allowed.

## 20. Frontend Implications

The frontend should stop exposing generic shape controls as if they are physical design
parameters.

Recommended first editable groups:

- main dimensions: inlet diameter, outlet diameter, bore radius,
- meridional support: hub profile semantic handles and optional control-point coordinates,
  blade-tip support profile semantic handles and optional control-point coordinates,
- blade pattern: blade count,
- leading/trailing boundaries: leading edge lean/sweep, trailing edge lean/sweep,
- blade surface: wrap angle, beta inlet/outlet controls, camber controls,
- blade profile: thickness distribution,
- edge treatment: leading/trailing edge type, root fillet radius, tip closure mode.

For v0.2, numeric inputs are acceptable. The frontend should show which DSL section a
parameter belongs to. It should also show whether a field is a semantic handle, a direct
NURBS control variable, a locked topology value, or a future optimization variable.

## 21. Acceptance Criteria For This Design

The spec is accepted when:

- the first ontology slice is named `AxisymmetricThroughflowRadialBladedImpeller`,
- canonical files are JSON,
- `blade_tip_support_surface` is retained and role-disambiguated,
- all four blade boundaries are first-class DSL entities,
- shape-control schema and default shape-control policies are first-class JSON assets,
- v0.2 declares fixed NURBS topology with editable/optimizable control-point
  coordinates,
- open and closed variants share the same mathematical support-surface model,
- open does not falsely declare front shroud material,
- closed does declare front shroud material,
- validity contracts include geometry, topology, and engineering warning categories,
- loss records are tied to violated contracts and patch intents,
- loss records can target semantic handles, shape-control policies, and NURBS control
  variables,
- existing API compatibility is preserved during migration.

## 22. Follow-Up Implementation Plan Topics

After this spec is reviewed, the implementation plan should cover:

1. Create JSON ontology and DSL directories.
2. Add a loader/validator module.
3. Add shape-control schema, default policies, and shape-control tests.
4. Move impeller taxonomy/preset data out of `impeller_taxonomy.py`.
5. Compile loaded JSON into the existing runtime rule format.
6. Refactor the axisymmetric impeller kernel to consume explicit four-boundary blade
   definitions.
7. Emit named boundary curves, adjacency, shape-control provenance, and optimization
   space in `surface_graph` and manifest.
8. Update frontend controls to reflect DSL sections and shape-control variable types.
9. Add tests for open/closed constructor semantics, four blade boundaries, tip-support
   roles, shape-control policies, and legacy preset aliases.
