# Axisymmetric Throughflow Impeller Literature Review

Date: 2026-06-30
Status: review draft for ontology/DSL decisions
Scope: one minimum object, not the full impeller taxonomy

## 1. Review Goal

The current project should not try to finalize a universal impeller ontology before one
small object is understood well. This review therefore focuses on one intended object:

```text
axisymmetric throughflow bladed impeller with NURBS meridional hub/tip boundaries,
NURBS or spline-derived blade pressure/suction surfaces, and explicit blade/hub/shroud
closure topology
```

This object is narrower than "impeller". It can cover some radial and mixed-flow pump or
compressor style impellers, but it does not cover every centrifugal, axial, vortex,
channel, propeller, regenerative, or turbine runner geometry.

## 2. Source Hierarchy

This review separates sources into three reliability tiers:

1. Engineering taxonomy and industrial workflow:
   - KSB centrifugal pump lexicon: impeller, free-flow impeller, wastewater impeller selection.
   - Grundfos Ecademy material on main impeller types.
   - Hydraulic Institute public definitions for rotodynamic pump terminology.
   - CFturbo public software pages and manual pages for impeller design workflow.
   - CAESES public impeller parameterization articles.

2. Geometry and mathematical construction:
   - CFturbo manual pages on meridional contour, beta blade angle progression, blade edges,
     blade thickness, and model finishing.
   - Published turbomachinery blade-design papers using differential geometry or
     parametric blade-generation methods.
   - Open parametric turbomachinery blade design literature, such as T4T-style tooling
     papers and NURBS/Bezier blade parameterization studies.

3. Project-local empirical evidence:
   - Frontend screenshots showing mismatched wireframe/shaded surfaces.
   - Failed/default parameter runs where the hub orientation, blade edge closure, and
     manifold assumptions were wrong.

The first tier defines vocabulary and workflow. The second tier defines mathematical
objects. The third tier defines loss cases and regression tests, but should not alone
define the ontology.

## 3. Taxonomy Findings

### 3.1 Flow Direction Is Only One Facet

Public pump references commonly use radial, mixed, and axial flow to describe the main
flow direction through the impeller. This is a useful facet, but it should not be the
root inheritance tree for the whole ontology. The same geometric construction ideas can
appear across radial and mixed-flow machines, while other distinctions such as shroud
state, suction state, and passage type change topology more directly.

Recommended ontology treatment:

```yaml
flow_topology: radial | mixed | axial
```

For the minimum object, allow:

```yaml
flow_topology: radial | mixed
```

Axial should stay outside this first object unless the blade section/airfoil model is
explicitly extended.

### 3.2 Shroud Topology Must Distinguish Material From Reference Surface

Industrial terminology uses open, semi-open, and closed impellers, but the exact wording
varies by domain. For this project, the practical distinction is:

- Open: no front shroud material surface over the blade tips; a tip reference surface may
  still exist mathematically for blade construction and clearance checking.
- Closed: a front shroud material shell exists and blade tips conform to it.
- Semi-open: partially shrouded or one-sided shroud cases; this is too ambiguous for the
  first object unless we define the actual material surfaces.

Recommended ontology treatment:

```yaml
shroud_topology: open | closed
```

For now, defer `semi_open` or represent it only after material surfaces are explicit.

### 3.3 Passage Topology Is A Stronger Constructor Split Than Flow Direction

KSB and Grundfos both discuss vortex/free-flow/wastewater style impellers, but those
geometries are not ordinary throughflow bladed channels. They emphasize a large free
passage or recessed blade region. This makes them a different constructor family, even
if their flow direction can still be called radial.

Recommended ontology treatment:

```yaml
passage_topology:
  - throughflow_bladed_channel
  - recessed_vortex
  - single_channel
  - multi_channel
  - cutter
```

The minimum object should only include:

```yaml
passage_topology: throughflow_bladed_channel
```

Vortex/free-flow should stay in the broader taxonomy but outside this constructor.

### 3.4 Working Domain Should Not Drive Geometry Alone

Pump, compressor, fan/blower, and turbine/runner domains influence blade angles, speed,
flow coefficient, thickness, material, edge treatment, and validation criteria. They
should not directly choose a geometry kernel without intermediate design intent.

Recommended treatment:

```yaml
working_domain: pump | compressor | fan_or_blower | turbine_or_runner | unknown
```

For the minimum object, support `pump` and `compressor` as metadata, but keep the
geometry generated from explicit meridional/blade/thickness contracts.

## 4. Engineering Workflow Findings

Industrial design tools tend to split impeller design into ordered steps:

1. Main dimensions and operating context.
2. Meridional contour, including hub and shroud/tip boundaries.
3. Blade properties: blade count, blade angles, wrap, spans, splitter/main blade choices.
4. Blade surface construction: mean/camber surface plus thickness distribution.
5. Leading and trailing edge treatment.
6. Fillets, model finishing, material domain, and flow domain generation.
7. Checks, optimization, CFD/FEA/CAM handoff.

This is important for the DSL. A single parameter such as `blade_curve_gain` is not an
engineering concept. It hides at least three different things:

- blade beta-angle distribution,
- circumferential wrap or theta progression,
- spline/camber control-point shape.

The DSL should represent these separately.

## 5. Geometry Model Findings

### 5.1 Coordinate System

The standard construction frame is cylindrical:

```text
(r, theta, z)
```

The meridional plane is:

```text
(r, z)
```

The blade surface is usually expressed using:

```text
u: streamwise / meridional / relative blade length coordinate
v: span coordinate from hub/root to shroud/tip
theta: circumferential coordinate
```

The project currently sometimes uses `u=0` and `u=1` ambiguously. For this object:

```text
u = 0: inlet / eye / leading edge side
u = 1: outlet / trailing edge side
v = 0: hub/root side
v = 1: tip/shroud side
```

Hub profile orientation in the meridional plane is separate:

```text
hub_profile parameter s = 0..1
```

Do not overload `u` for both blade streamwise direction and hub profile direction.

### 5.2 Hub And Tip/Shroud Surfaces

For this minimum object, the hub and tip/shroud boundaries should be generated as
surfaces of revolution:

```text
hub_profile:      C_h(s) = (r_h(s), z_h(s))
tip_profile:      C_t(s) = (r_t(s), z_t(s))

hub_surface:      H(s, theta) = (r_h(s) cos theta, r_h(s) sin theta, z_h(s))
tip_surface:      T(s, theta) = (r_t(s) cos theta, r_t(s) sin theta, z_t(s))
```

The profile curves may be NURBS, B-spline, or Bezier-derived curves. The ontology should
not require NURBS everywhere, but the DSL can choose NURBS for this constructor.

Validity contracts:

- Radii must be positive and outside the mounting bore.
- Hub and tip profiles must not cross in the meridional plane.
- Open impellers still need a `tip_reference_surface`; closed impellers need a material
  `front_shroud_surface`.
- The hub is not just one surface. It needs a material-domain description: outer hub
  surface, bottom/back surface, mounting bore cylinder, and closure faces.

### 5.3 Blade Mean Surface

The blade mean/camber surface should be defined between hub and tip boundaries. A common
mathematical route is:

```text
M(u, v) = interpolated meridional position between hub and tip
theta(u, v) = theta law from blade angle beta, wrap, and/or spline control
P_m(u, v) = (r(u, v) cos theta(u, v), r(u, v) sin theta(u, v), z(u, v))
```

The beta-angle relation used in many radial/mixed-flow approximations is based on
meridional distance and circumferential progression:

```text
d theta / d m ~= 1 / (r tan(beta))
```

This is a design parameterization, not a full physical solve. It must be exposed as a
geometry law with sign convention, angle units, and coordinate definitions.

Recommended DSL concepts:

```yaml
blade_mean_surface:
  representation: nurbs_surface | beta_integrated_surface | control_net_surface
  streamwise_coordinate: u
  span_coordinate: v
  theta_law:
    kind: beta_integral | direct_spline | wrap_constrained_spline
  beta_distribution:
    hub: ...
    shroud_or_tip: ...
    span_interpolation: ...
```

### 5.4 Blade Pressure/Suction Surfaces

The phrase "blade profile" is overloaded. In this minimum object it should not mean one
standalone 2D airfoil pasted onto the blade. It should mean a structured set of laws:

- mean/camber law,
- thickness law along streamwise direction,
- optional thickness variation across span,
- pressure/suction split law,
- leading and trailing edge closure law,
- root/tip closure or fillet law.

For the first mathematically stable constructor:

```text
pressure_surface = offset(mean_surface, +thickness_direction * thickness/2)
suction_surface  = offset(mean_surface, -thickness_direction * thickness/2)
```

The offset direction must be declared. Options include:

- circumferential direction,
- local mean-surface normal,
- direction normal to camber line in a rotational surface,
- full airfoil-section normal.

Recommendation for v0.1:

```yaml
thickness_application:
  direction: circumferential_normal_in_span_section
```

Reason: it is simpler and more stable for radial/mixed preview geometry than full normal
offsets, which can self-intersect in high-curvature regions.

### 5.5 Blade Edges And Fillets Are First-Class Geometry

A blade is not a solid if it only has pressure and suction surfaces. It needs:

- leading edge closure,
- trailing edge closure,
- root closure or root fillet,
- tip closure or tip/shroud contact treatment.

For open impellers, the blade tip edge is visible and must be closed. For closed
impellers, the blade tip may be joined to the shroud or represented with a finite fillet
or weld-like transition.

Recommended DSL concepts:

```yaml
blade_edge_closures:
  leading_edge:
    kind: ruled | elliptical | nurbs_patch
  trailing_edge:
    kind: ruled | elliptical | nurbs_patch
  root:
    kind: ruled | fillet_patch
  tip:
    kind: exposed_closed_edge | shroud_join | tip_clearance
```

Fillets should be separate from edge closures:

```yaml
fillets:
  blade_root:
    radius_mm: ...
    continuity: G1 | G2
  blade_tip:
    radius_mm: ...
```

### 5.6 Surface Graph Before Solid CAD

For this research phase, the exact OCCT/CadQuery solid can lag behind the mathematical
surface graph, but it must not contradict it. The correct intermediate artifact is:

```text
surface_graph = named surfaces + boundary curves + adjacency relations
```

The STL/STEP/visualization path must sample from this same surface graph. A wireframe
generated from a different proxy is invalid.

## 6. Proposed Minimum Object Definition

Recommended name:

```text
AxisymmetricThroughflowBladedImpeller
```

Definition:

```text
A bladed rotating component whose primary blade passage is a throughflow channel bounded
by axisymmetric hub and tip/shroud meridional surfaces, with blades represented as
finite-thickness pressure/suction surface pairs whose hub and tip boundaries conform to
those axisymmetric surfaces.
```

In scope:

```yaml
part_family: impeller
flow_topology: radial | mixed
passage_topology: throughflow_bladed_channel
shroud_topology: open | closed
suction_topology: single_suction
blade_pattern: full_blade_set
hub_tip_boundary: axisymmetric_revolved_nurbs_profiles
blade_surface_representation: nurbs_or_spline_control_surface
blade_thickness: explicit_field
blade_edges: explicit_closure_surfaces
mounting_interface: central_bore
```

Out of scope for this object:

```yaml
flow_topology: axial
suction_topology: double_suction
passage_topology: recessed_vortex | single_channel | multi_channel | cutter
splitter_blades: true
non_axisymmetric_hub_or_shroud: true
regenerative_peripheral_pump: true
strict CFD-derived inverse design: true
manufacturing_process_specific_blade_law: true
```

## 7. Ontology Candidate

### 7.1 Entities

```yaml
entities:
  - rotation_axis
  - meridional_plane
  - hub_profile_curve
  - tip_profile_curve
  - hub_surface
  - tip_reference_surface
  - front_shroud_surface
  - hub_material_domain
  - mounting_bore
  - blade_mean_surface
  - blade_pressure_surface
  - blade_suction_surface
  - leading_edge_closure_surface
  - trailing_edge_closure_surface
  - root_edge_closure_or_fillet
  - tip_edge_closure_or_shroud_join
  - blade_pattern
  - throughflow_passage
  - surface_graph
```

### 7.2 Relations

```yaml
relations:
  - revolves_about(profile_curve, rotation_axis)
  - generates_surface(profile_curve, surface)
  - bounds_span(hub_surface, tip_or_shroud_surface)
  - conforms_to(boundary_curve, support_surface)
  - offsets_from(pressure_or_suction_surface, blade_mean_surface)
  - closes_edge(edge_closure_surface, pressure_surface, suction_surface)
  - joins_to(root_or_tip_closure, hub_or_shroud_surface)
  - patterns_around_axis(blade_instance, rotation_axis)
  - encloses_material(surface_graph, material_domain)
  - bounds_flow_passage(surface_graph, throughflow_passage)
```

### 7.3 Actions

Construction actions should not be ontology classes. They are DSL operations:

```yaml
actions:
  - define_coordinate_system
  - define_meridional_profile
  - revolve_profile
  - define_blade_mean_surface
  - define_thickness_field
  - offset_pressure_suction_surfaces
  - construct_edge_closure
  - construct_root_tip_fillet
  - pattern_blades
  - assemble_surface_graph
  - validate_geometry_contracts
  - validate_topology_contracts
  - export_preview_mesh
  - export_cad_solid
```

## 8. DSL v0.1 Shape

The DSL should be explicit enough to reconstruct a deterministic constructor:

```yaml
dsl_version: 0.1
constructor_family: AxisymmetricThroughflowBladedImpeller

classification:
  part_family: impeller
  flow_topology: radial
  passage_topology: throughflow_bladed_channel
  shroud_topology: open
  suction_topology: single_suction
  working_domain: pump

coordinate_system:
  axis: z
  units: mm
  angle_units: deg

meridional_boundary:
  hub_profile:
    representation: nurbs_curve
    parameter: s
    control_points_rz: []
    knots: []
    degree: 3
  tip_profile:
    representation: nurbs_curve
    parameter: s
    control_points_rz: []
    knots: []
    degree: 3
  profile_contracts:
    positive_radius: true
    hub_tip_no_crossing: true

hub_material:
  central_bore_radius_mm: 40
  back_face_z_mm: 0
  requires_closed_material_shell: true

blade:
  count: 7
  streamwise_coordinate: u
  span_coordinate: v
  mean_surface:
    kind: beta_integrated_surface
    beta_distribution:
      hub_control_points: []
      tip_control_points: []
      span_interpolation: linear
    wrap_constraint_deg: 118
  thickness:
    representation: spline_field
    control_points: []
    pressure_suction_split: symmetric
    application_direction: circumferential_normal_in_span_section
  edge_closures:
    leading_edge: {kind: elliptical_or_ruled}
    trailing_edge: {kind: elliptical_or_ruled}
    root: {kind: fillet_patch}
    tip: {kind: exposed_closed_edge}

validation:
  geometric_contracts: []
  topology_contracts: []
  engineering_contracts: []
```

## 9. Validity Contracts

### 9.1 Geometry Correctness

```yaml
geometry_validity:
  - every surface has a named parameter domain
  - sampled wireframe is generated from the same surfaces as shaded geometry
  - hub and tip/shroud curves are valid NURBS curves
  - hub and tip/shroud surfaces are positive-radius revolutions
  - blade v=0 boundary conforms to hub surface
  - blade v=1 boundary conforms to tip reference or shroud surface
  - pressure and suction surfaces do not swap sides
  - thickness is positive and below local curvature/clearance limits
  - leading/trailing/root/tip edge closures exist
  - no NaN, infinite, or duplicate degenerate grid rows
```

### 9.2 Topology Correctness

```yaml
topology_validity:
  - each blade has pressure, suction, leading, trailing, root, and tip boundary surfaces
  - open impeller blade tips are closed but not connected to a front shroud
  - closed impeller blade tips conform to or join the front shroud
  - hub material domain contains outer hub surface, bore surface, bottom/back face, and caps
  - blade root is attached to or filleted into hub, not floating
  - surface graph adjacency is explicit before CAD sewing
```

### 9.3 Preliminary Engineering Correctness

These should be warnings in v0.1, not hard failures:

```yaml
engineering_validity:
  - beta angles within plausible domain-specific ranges
  - blade count within plausible range for size/domain
  - wrap angle avoids excessive overlap or too-short passage
  - leading/trailing edge thickness is manufacturable
  - root fillet radius is nonzero when a solid blade joins a hub
  - mounting bore radius leaves enough hub material
  - open tip clearance is representable even if casing is absent
```

## 10. Loss Schema Implications

The three existing feedback examples map cleanly into structured loss:

### 10.1 Hub Profile Reversed

```yaml
raw_feedback: hub is concave/reversed; bottom radius should be larger than top radius
target_entities: [hub_profile_curve, hub_surface]
violated_contracts:
  - meridional_profile_orientation
  - radius_monotonicity_or_expected_trend
patch_intents:
  - clarify hub profile parameter direction
  - add orientation labels independent from blade u
  - add regression case for expected inlet/backplate radii
```

### 10.2 Missing Blade Edges

```yaml
raw_feedback: blade has only two surfaces and is not a complete solid
target_entities:
  - blade_pressure_surface
  - blade_suction_surface
  - leading_edge_closure_surface
  - trailing_edge_closure_surface
  - root_edge_closure_or_fillet
  - tip_edge_closure_or_shroud_join
violated_contracts:
  - blade_topology_complete
patch_intents:
  - make edge closures first-class DSL elements
  - add visual construction lines for every closure surface
  - add topology validation
```

### 10.3 Hub Not A Solid / Missing Bore

```yaml
raw_feedback: hub is not just one surface; it is a material body with a mounting bore
target_entities:
  - hub_material_domain
  - mounting_bore
  - hub_surface
violated_contracts:
  - hub_material_domain_complete
patch_intents:
  - split support surface from material domain
  - add bore and bottom/back face entities
  - add minimum wall-thickness warnings
```

Future losses should use the same shape:

```yaml
loss_record:
  raw_feedback: string
  source: human | simulation | meshing | CAM | manufacturing | test
  target_entities: []
  observed_claims: []
  violated_contracts: []
  patch_intents: []
  evidence_artifacts: []
  approval_status: proposed | accepted | rejected
  regression_tests: []
```

## 11. What This Means For Current Code

The current `impeller_kernel.py`/`axisymmetric_throughflow_nurbs.py` direction is only
partly aligned with the review.

Keep:

- one focused kernel for this object,
- surface graph as the source of shaded geometry and wireframe,
- open/closed variants,
- explicit hub/tip profiles,
- explicit blade edge closures.

Change later:

- Rename the object from a study preset to a constructor family.
- Separate ontology concepts from constructor operations.
- Replace vague parameters such as `blade_curve_gain` with beta/wrap/camber laws.
- Separate hub profile parameter `s` from blade coordinates `u,v`.
- Treat semi-open, vortex, channel, axial, splitter, and double-suction as out-of-scope
  until separate constructors are defined.
- Add geometry and topology validity outputs to every manifest.

## 12. Open Questions Before Freezing This Object

1. Should this minimum object allow both radial and mixed-flow, or should radial be the
   first strictly supported case?
2. Should `tip_profile` be mandatory for open impellers as a mathematical reference
   surface, even though it is not material?
3. Should pressure/suction surfaces be generated from a mean surface plus thickness, or
   should the DSL allow direct independent NURBS control nets for pressure and suction?
4. Should root/tip fillets be required in v0.1, or should ruled closure surfaces be
   acceptable with a warning?
5. Should the first validity target be a watertight mesh, an explicit surface graph, or
   a strict CAD solid?

## 13. Recommended Decision

Use this minimum object as the first serious ontology/DSL target:

```text
AxisymmetricThroughflowBladedImpeller
```

Start with radial open and radial closed variants. Allow mixed-flow as a near-term
extension, not as the initial validation target. Do not include vortex/free-flow,
single-channel, multi-channel, axial, double-suction, splitter blades, or non-axisymmetric
hub/shroud surfaces in the first constructor.

The most important ontology correction is to stop treating "impeller type" as one flat
classification. The constructor should be selected by:

```text
passage topology + support-surface model + blade-surface model + topology contract
```

not only by:

```text
radial / mixed / axial
```

## 14. References

- KSB, "Impeller", https://www.ksb.com/en-global/centrifugal-pump-lexicon/article/impeller-1116078
- KSB, "Free-flow impeller", https://www.ksb.com/en-global/centrifugal-pump-lexicon/article/free-flow-impeller-1118154
- KSB, wastewater impeller selection, https://www.ksb.com/en-us/solutions/wastewater-technology/wastewater-treatment/waste-water-applications-selecting-pump-impellers
- Grundfos, "Main impeller types", https://www.grundfos.com/content/dam/global/page-assets/learn/ecademy/pdfs/master-36-module-3-Main-impeller-types.pdf
- Hydraulic Institute, public table of definitions, https://datatool.pumps.org/introduction-definitions-references/table-of-definitions
- CFturbo, "Impellers", https://cfturbo.com/software/impellers
- CFturbo manual, "Beta blade angle progression", https://manual.cfturbo.com/en/x-beta-blade-angle-progression.html
- CFturbo manual, "Meridional contour", https://manual.cfturbo.com/en/mercon.html
- CFturbo manual, "Model finishing", https://manual.cfturbo.com/en/model_finishing.html
- CAESES, "Parametric impeller design", https://www.caeses.com/blog/2015/parametric-impeller-design/
- "Impeller blade design method based on differential geometry", https://engmechx.it.cas.cz/improc/2011/p127.pdf
- Aerospace 2022 parametric turbomachinery blade-design paper, https://www.mdpi.com/2226-4310/9/9/489
