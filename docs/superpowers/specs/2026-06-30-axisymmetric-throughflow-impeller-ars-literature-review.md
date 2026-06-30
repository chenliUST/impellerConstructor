# Axisymmetric Throughflow Impeller ARS Literature Review

Date: 2026-06-30
Workflow: `academic-research-suite` / `deep-research` / `lit-review`
Status: detailed review draft for Ontology/DSL decisions
Language: Simplified Chinese with English technical terms retained

## 1. Research Question Brief

### Primary Research Question

For an axisymmetric throughflow bladed impeller, what geometry, topology, and
engineering-design concepts must the Ontology and DSL represent so that a local
constructor can deterministically generate valid hub, shroud/tip, blade pressure/suction
surfaces, edge closures, material domains, construction wireframes, and validation
losses?

### FINER Assessment

| Criterion | Score | Justification |
|---|---:|---|
| Feasible | 5/5 | Public engineering manuals, pump lexicons, NASA/NACA reports, and CAD parameterization papers are available. |
| Interesting | 5/5 | The current project already exposed semantic errors: reversed hub profile, missing blade edges, floating blades, and proxy wireframes. |
| Novel | 4/5 | Individual geometry methods exist, but translating them into an agent-generated, ontology-facing DSL is less settled. |
| Ethical | 5/5 | The work is geometry/engineering design infrastructure. No human-subject or sensitive-data issue is present. |
| Relevant | 5/5 | Directly determines whether the next code refactor is grounded or continues to encode ambiguous geometry. |
| Average | 4.8/5 | Suitable for a focused literature review, not yet a full systematic review. |

### Scope

In scope:

- radial and near-radial/mixed throughflow impellers as the knowledge source,
- axisymmetric hub and shroud/tip support surfaces,
- NURBS/Bezier/B-spline meridional and blade parameterization,
- pressure/suction surface generation,
- leading/trailing/root/tip closures,
- material domain and flow-domain implications,
- geometry/topology validity contracts for the DSL.

Out of scope:

- final CFD-quality inverse design,
- strict pump/compressor performance prediction,
- full PRISMA systematic review,
- manufacturing process planning,
- vortex/free-flow/channel impeller constructors,
- axial propeller-style blade-section constructors.

## 2. Search Strategy

### Databases / Source Families

- NASA Technical Reports Server / NACA reports
- CFturbo public manuals and engineering pages
- KSB centrifugal pump lexicon and wastewater impeller material
- Grundfos Ecademy PDF on main impeller types
- Hydraulic Institute public pump definitions
- CAESES public parametric impeller design material
- TU Delft repository / Computer-Aided Design paper
- Technical University of Crete repository / T4T paper metadata
- MDPI and other open-access articles
- Google web search over exact title and technical keyword combinations

### Representative Search Strings

```text
turbomachinery blade parametrization NURBS hub shroud camber thickness
centrifugal impeller parametric modeling NURBS pressure suction surfaces
CFturbo meridional contour blade profiles blade edges
axisymmetric throughflow impeller blade geometry parameterization
centrifugal pump impeller design blade angles wrap thickness leading edge
Impeller Blade Design Method for Centrifugal Compressors NASA
Stanitz Prian velocity distribution impeller blades arbitrary hub shroud contours
A Unified Geometry Parametrization Method for Turbomachinery Blades
A software tool for parametric design of turbomachinery blades NURBS
```

### Inclusion Criteria

- Source directly addresses impeller/turbomachinery classification, geometry definition,
  blade parameterization, meridional contour, blade thickness, edge treatment, material
  solids, or geometry validity.
- Publicly accessible official, academic, or engineering source.
- Prefer sources with stable publisher/organization pages, DOI, NTRS record, or official
  product manual.
- Include older NASA/NACA sources when foundational to impeller blade geometry or
  blade-surface analysis.

### Exclusion Criteria

- Generic pump tutorials with no geometry-construction detail.
- Unverified forum posts or SEO-heavy summaries.
- Pure CFD performance papers that vary one parameter but do not clarify geometry
  representation.
- Vortex, single-channel, cutter, or axial propeller sources unless they clarify taxonomy.

### Coverage Advisory

This is a structured literature review, not a PRISMA systematic review. Coverage is
skewed toward English-language public technical sources and industrial CAD/CAE workflows.
Chinese-language pump-design literature and full textbook chapters were not exhaustively
searched in this round.

## 3. Source Quality Matrix

| Source | Type | Verification / Quality | Main Contribution |
|---|---|---|---|
| KSB, "Impeller" | Industrial lexicon | High; official manufacturer lexicon | Separates flow pattern, shroud/open/closed, single/double entry, channel/free-flow/peripheral cases. |
| KSB, "Free-flow impeller" | Industrial lexicon | High; official lexicon | Confirms free-flow/vortex-like impeller is radial but defined by large free passage. |
| KSB wastewater impeller selection | Industrial application guide | High; official manufacturer guide | Shows open/closed and wastewater impeller types are application/passability choices, not just flow direction. |
| Grundfos main impeller types PDF | Industrial training PDF | Medium-high; official training material | Lists radial, mixed, channel/tube, vortex, axial as practical pump categories. |
| Hydraulic Institute definitions | Standards-adjacent glossary | Medium-high; public definitions page | Supports using pump terminology as controlled vocabulary, though public page is limited. |
| CFturbo impeller design steps | Industrial CAD/CAE workflow | High; official tool workflow | Gives ordered steps: dimensions, meridional contour, blade properties, mean lines, profiles, edges. |
| CFturbo meridional contour manual | Industrial CAD/CAE manual | High | Distinguishes primary flow path, hub/shroud material solids, and secondary flow path; lists geometry warnings. |
| CFturbo hub/shroud materials manual | Industrial CAD/CAE manual | High | Supports modeling material domain separately from flow-path support curves. |
| CFturbo blade profiles manual | Industrial CAD/CAE manual | High | Defines thickness profiles, pressure/suction side generation, spanwise thickness morphing, and warnings. |
| CFturbo blade edges manual | Industrial CAD/CAE manual | High | Confirms leading/trailing edge design is explicit and supports simple, linear, ellipse, and Bezier edge forms. |
| CAESES shrouded impeller geometry article | Industrial parametric CAD workflow | Medium-high | Explains meridional contour, theta function, thickness normal to camber, booleans, fillets, and fixed patch identifiers. |
| NASA NTRS Jansen & Kirschner 1974 | Foundational NASA report metadata | High; NASA record | Describes centrifugal impeller blade generation by hub-to-shroud straight-line elements and surface velocity distribution. |
| NACA TN 2421 Stanitz & Prian 1951 | Foundational NACA report | High; NASA-hosted PDF | Analyzes blade-surface velocity for radial/mixed centrifugal compressors with arbitrary hub/shroud contours and blade shape. |
| Agromayor et al. 2021, Computer-Aided Design | Peer-reviewed CAD paper | High; DOI and repository copy | Strongest source for topology-first, watertight-by-construction blade and flow-domain parametrization using NURBS. |
| Koini et al. 2009, Advances in Engineering Software | Peer-reviewed software paper | Medium-high; repository metadata and DOI | Supports NURBS surfaces for blades, hub, and shroud generated from 2D section parameters. |
| Siddappaji 2012 thesis | Graduate thesis | Medium; institutional PDF | Useful detail on 3D blade sections, stacking, hub/tip streamlines, NURBS surfaces, and CFD/FEA handoff. |
| Tao et al. 2018, Energies | Peer-reviewed OA article | Medium-high; DOI | Shows leading-edge shape is a real engineering variable affecting cavitation, not cosmetic geometry. |
| Ding et al. 2019, Vacuum | Peer-reviewed article PDF | Medium-high; publisher/CFturbo-hosted PDF | Demonstrates blade outlet angle as an important design variable with experiment/CFD comparison. |
| UPC centrifugal pump impeller design PDF | Academic/course-style PDF | Medium | Useful for preliminary design variables and velocity-triangle calculation, but not a geometry-kernel authority. |

## 4. Synthesis: What The Literature Actually Says

### 4.1 Classification: impeller type is multi-axis, not a tree

KSB separates impellers by flow-line pattern into radial, mixed, axial, and peripheral,
but the same page also describes shroud state, single/double entry, vane count, channel
impellers, single-vane impellers, free-flow impellers, and arrangements on the shaft.
Grundfos similarly puts radial, mixed, channel/tube, vortex, and axial in one practical
training list. This means "radial/mixed/axial" is not sufficient to select a constructor.

Ontology implication:

```yaml
classification_axes:
  flow_topology: radial | mixed | axial | peripheral
  passage_topology: throughflow_bladed_channel | single_channel | multi_channel | recessed_vortex | cutter
  shroud_topology: open | closed | semi_open
  entry_topology: single_entry | double_entry | multi_entry
  blade_population: full_blade_set | single_vane | channel_vane | splitter_augmented
  working_domain: pump | compressor | fan_or_blower | turbine_or_runner
```

Constructor selection should not be:

```text
flow_topology only
```

It should be:

```text
passage_topology + support_surface_model + blade_surface_model + material_domain_contract
```

### 4.2 The minimum object should start radial, not "radial or mixed" equally

Mixed-flow impellers share parts of the throughflow/blade-surface vocabulary, but they
increase ambiguity in meridional shape, outlet direction, blade sweep, and spanwise twist.
The current project is still struggling with basic hub orientation and blade closure.

Recommended freeze for v0.1:

```text
AxisymmetricThroughflowRadialBladedImpeller
```

Near-term extension:

```text
AxisymmetricThroughflowMixedBladedImpeller
```

This is stricter than the previous `AxisymmetricThroughflowBladedImpeller`, but it is more
testable and easier to validate.

### 4.3 Vortex/free-flow should remain outside this constructor

KSB defines free-flow impeller as a radial impeller with a large free passage for solids.
Grundfos states that vortex impellers create vortices in the pump housing and prioritize
clog-free reliability over efficiency. These are not ordinary throughflow bladed channels
bounded by hub/shroud and pressure/suction blade passages.

Ontology implication:

```yaml
recessed_vortex:
  flow_topology: radial
  passage_topology: recessed_vortex
  constructor_family: RecessedVortexFreePassageImpeller
```

Do not implement vortex as a parameter switch inside the throughflow NURBS constructor.

### 4.4 Industrial workflow separates flow path, material domain, blade, edges, and finishing

CFturbo's public workflow is especially useful because it matches how a deterministic
constructor should be staged:

1. main dimensions,
2. meridional contour,
3. blade properties,
4. blade mean lines,
5. blade profiles / thickness,
6. blade edges.

The CFturbo manual then further separates meridional contour into primary flow path,
hub/shroud material solids, and secondary flow path. This directly explains why the
project's earlier "hub is one surface" model was wrong.

DSL implication:

```yaml
flow_path:
  primary_meridional_boundary: ...

material_domain:
  hub_solid: ...
  front_shroud_solid: ...
  bore: ...

blade_domain:
  mean_lines: ...
  pressure_surface: ...
  suction_surface: ...
  edge_closures: ...
  fillets: ...

flow_domain:
  inlet_patch: ...
  outlet_patch: ...
  periodic_patches: ...
  wall_patches: ...
```

### 4.5 Meridional contour is not just "hub curve plus tip curve"

The primary flow path needs hub and shroud/tip curves in the meridional plane. These can
be Bezier, NURBS, line/arc segments, or polylines. CFturbo explicitly warns about:

- discontinuities inside blade region,
- tiny geometric artifacts,
- invalid primary flow path constraints,
- hub curve touching the axis internally,
- invalid inside-out contour topology.

Therefore, the DSL must include not only control points but validity contracts:

```yaml
meridional_profile_contracts:
  radius_positive: true
  no_internal_axis_touch: true
  hub_shroud_no_crossing: true
  connector_smoothness_minimum: G1
  no_micro_segments_below_mm: ...
  closed_wire_orientation: clockwise_in_rz
  blade_region_continuity: G1_or_better
```

The previous feedback "hub curve is reversed" is one instance of a broader meridional
orientation/validity problem.

### 4.6 Blade surface should be represented as skeleton + profile + closure, not one surface

The literature and CAD tools consistently split blade geometry into:

- mean/camber line or surface,
- span stations or meridional flow surfaces,
- blade angle / beta distribution,
- wrap/theta law,
- thickness distribution,
- pressure/suction side generation,
- leading/trailing edge shape,
- root/tip closure or fillet.

CFturbo supports blade design on 1 to 15 meridional spans, with mean-line design using
Bezier/polylines and conformal mapping to `m-theta` or `m-beta`. CAESES describes a theta
function in the `(m, theta)` system, then applies user-defined thickness normal to the
camber surface. The modern CAD literature supports NURBS/B-spline blade surfaces, often
from section-based definitions.

Recommended normalized vocabulary:

```yaml
blade_skeleton:
  leading_edge_curve: curve_on_meridional_channel
  trailing_edge_curve: curve_on_meridional_channel
  span_stations: hub_to_tip_or_shroud
  stacking_law: leading_edge | trailing_edge | centroid | custom_curve
  theta_law: beta_integral | m_theta_curve | direct_control_net
  beta_distribution:
    hub: curve
    shroud_or_tip: curve
    span_interpolation: linear | spline

blade_profile:
  thickness_distribution:
    streamwise_parameter: u_relative_le_to_te
    hub_profile: curve
    shroud_or_tip_profile: curve
    span_morphing: identical | linear | exponent | spline
  pressure_suction_coupling: symmetric | shifted | independent
  application_direction: mean_surface_normal | mean_line_normal_in_rotational_surface | tangential

blade_closure:
  leading_edge: simple | linear_elliptic | ellipse | bezier
  trailing_edge: simple | linear_elliptic | ellipse | bezier
  root: closure_surface | fillet_patch
  tip: exposed_closed_edge | shroud_join | tip_clearance
```

### 4.7 "Blade profile" must be disambiguated in Chinese and DSL

The current discussion uses "profile" ambiguously. Literature uses profile to mean
different things depending on context.

Recommended DSL terms:

| Ambiguous phrase | Use this instead | Meaning |
|---|---|---|
| hub profile | `hub_meridional_profile` | R-Z curve revolved into hub support surface. |
| shroud/tip profile | `tip_or_shroud_meridional_profile` | R-Z curve revolved into reference/material surface. |
| blade profile | `blade_thickness_profile` or `blade_section_profile` | Thickness/section definition along blade length. |
| leading edge profile | `leading_edge_closure_profile` | Rounded/Bezier/elliptic edge cross-section law. |
| blade curve | `blade_mean_line` or `theta_law` | Streamwise camber/skeleton curve, not thickness. |

Chinese glossary:

```text
meridional profile = 子午轮廓
blade mean line / camber line = 叶片中线 / 弯度线
blade section profile = 叶片截面型线
thickness profile = 厚度分布
leading/trailing edge profile = 前缘/尾缘闭合型线
hub/shroud material solid = 轮毂/盖板材料域
flow domain = 流体域
surface graph = 曲面拓扑图
```

### 4.8 Edge closures are not optional

CFturbo has a separate Blade edges stage. It supports blunt/simple, linear with elliptic
rounding, ellipse, and Bezier edge definitions. It also warns that edge geometry can cause
blades to exceed meridional boundaries, make trimming impossible, make hub/shroud
extrapolation fail, or overlap leading and trailing edge regions.

Therefore, the DSL cannot represent a blade as only pressure and suction surfaces.

Hard contract:

```yaml
blade_topology_contract:
  pressure_surface: required
  suction_surface: required
  leading_edge_closure_surface: required
  trailing_edge_closure_surface: required
  root_closure_or_fillet: required
  tip_closure_or_shroud_join: required
```

### 4.9 Thickness application direction is a real modeling choice

CFturbo lists three thickness application modes:

- perpendicular to mean surface,
- perpendicular to mean line inside the rotational surface,
- tangential.

It recommends mean-line-normal inside the rotational surface for stability in trimming
with hub/shroud, especially for highly curved blades. CAESES describes thickness applied
normal to the camber surface. These are not equivalent.

Recommended v0.1 choice:

```yaml
thickness_application_direction: mean_line_normal_in_rotational_surface
```

Reason:

- more stable than full surface normal for early research-grade geometry,
- closer to CFturbo's stability warning,
- easier to validate with hub/tip conformity,
- still more meaningful than purely tangential offset.

Keep full mean-surface normal as later mode:

```yaml
thickness_application_direction: mean_surface_normal
```

### 4.10 Watertight-by-construction is the right north star

Agromayor et al. 2021 is especially important for this project. It argues for a general
turbomachinery blade parameterization based on engineering variables and NURBS curves
and surfaces, formulated explicitly to avoid intersection/trimming operations. The paper
also describes constructing inlet, outlet, and periodic surfaces as ruled surfaces after hub
and shroud are defined, and states the blade/flow-domain parameterization is watertight by
construction.

Project implication:

```text
Do not build disconnected surfaces and later hope CAD trimming/booleans repair them.
Build a named surface graph whose adjacent patches share boundary curves by construction.
```

This should drive the next kernel refactor.

### 4.11 Engineering parameters are not all geometry controls

Several sources show that blade outlet angle, blade number, wrap angle, thickness, and
leading-edge shape affect pump performance, cavitation, blockage, and hydraulic losses.
However, this does not mean the geometry DSL should accept only performance goals.

Better separation:

```yaml
functional_design_inputs:
  flow_rate:
  head:
  rotational_speed:
  efficiency_target:
  specific_speed:
  fluid_class:

geometry_design_variables:
  outlet_diameter:
  inlet_diameter:
  inlet_width:
  outlet_width:
  hub_meridional_profile:
  shroud_meridional_profile:
  blade_count:
  beta_distribution:
  wrap_angle:
  rake_or_lean:
  thickness_distribution:
  edge_closure_profiles:
  fillet_radii:

derived_geometry:
  computed_from_functional_inputs: true | false
  derivation_model: empirical | velocity_triangle | inverse_design | optimizer
```

For v0.1, the constructor should accept direct geometry variables. Functional inputs can
generate initial guesses but should not hide the geometry law.

## 5. Recommended Ontology Revision

### 5.1 Constructor Family

Replace the current broad label with:

```yaml
constructor_family: AxisymmetricThroughflowRadialBladedImpeller
```

Definition:

```text
A radial throughflow impeller constructor whose blade passages are bounded by
axisymmetric hub and tip/shroud support surfaces, and whose blades are finite-thickness
surface graphs with pressure/suction sides, leading/trailing edge closures, root/tip
closures or fillets, and an explicit hub/shroud material-domain contract.
```

Supported v0.1 facets:

```yaml
part_family: impeller
flow_topology: radial
passage_topology: throughflow_bladed_channel
shroud_topology: open | closed
entry_topology: single_entry
blade_population: full_blade_set
support_surface_model: axisymmetric_revolved_meridional_profiles
blade_surface_model: meanline_thickness_edge_surface_graph
working_domain: pump | compressor | unknown
```

Deferred:

```yaml
flow_topology: mixed | axial | peripheral
passage_topology: recessed_vortex | single_channel | multi_channel | cutter
entry_topology: double_entry | multi_entry
blade_population: splitter_augmented | single_vane
support_surface_model: non_axisymmetric | spherical_adjustable_pitch
strict_cad_solid: required
```

### 5.2 Core Entities

```yaml
entities:
  coordinate_system:
    - rotation_axis
    - meridional_plane
    - cylindrical_frame

  primary_flow_path:
    - hub_meridional_profile
    - tip_or_shroud_meridional_profile
    - inlet_boundary_curve
    - outlet_boundary_curve
    - meridional_channel_wire

  support_surfaces:
    - hub_support_surface
    - tip_reference_surface
    - front_shroud_inner_surface

  material_domain:
    - hub_material_solid
    - back_shroud_or_disk
    - mounting_bore
    - front_shroud_material_solid
    - material_closure_faces

  blade:
    - blade_mean_line_set
    - blade_mean_surface
    - pressure_surface
    - suction_surface
    - leading_edge_closure_surface
    - trailing_edge_closure_surface
    - root_closure_or_fillet_surface
    - tip_closure_or_shroud_join_surface

  topology:
    - blade_instance
    - blade_pattern
    - surface_graph
    - adjacency_graph
    - named_boundary_curve

  validation:
    - geometry_validity_report
    - topology_validity_report
    - engineering_warning_report
    - loss_record
```

### 5.3 Relations

```yaml
relations:
  - revolves_about(profile_curve, rotation_axis)
  - generates_surface(profile_curve, support_surface)
  - bounds_meridional_channel(hub_profile, tip_or_shroud_profile, inlet_curve, outlet_curve)
  - lies_on(boundary_curve, support_surface)
  - conforms_to(blade_root_boundary, hub_support_surface)
  - conforms_to(blade_tip_boundary, tip_reference_or_shroud_surface)
  - offsets_from(pressure_surface, blade_mean_surface)
  - offsets_from(suction_surface, blade_mean_surface)
  - closes_between(edge_closure, pressure_surface, suction_surface)
  - joins_to(root_closure_or_fillet, hub_material_domain)
  - joins_to(tip_closure_or_shroud_join, tip_or_shroud_domain)
  - patterns_around_axis(blade_instance, rotation_axis)
  - shares_boundary(surface_a, surface_b, boundary_curve)
  - encloses_material(surface_graph, material_domain)
  - bounds_flow_domain(surface_graph, flow_domain)
```

## 6. DSL v0.2 Candidate

```yaml
dsl_version: 0.2
constructor_family: AxisymmetricThroughflowRadialBladedImpeller

classification:
  part_family: impeller
  flow_topology: radial
  passage_topology: throughflow_bladed_channel
  shroud_topology: open
  entry_topology: single_entry
  blade_population: full_blade_set
  working_domain: pump

coordinate_system:
  units: mm
  frame: cylindrical
  rotation_axis: z
  positive_rotation: counterclockwise_viewed_from_inlet

main_dimensions:
  inlet_diameter:
  outlet_diameter:
  inlet_width:
  outlet_width:
  hub_eye_radius:
  bore_radius:

primary_flow_path:
  hub_meridional_profile:
    representation: nurbs_curve
    parameter: s
    degree: 3
    control_points_rz: []
    knots: []
    weights: []
  tip_or_shroud_meridional_profile:
    representation: nurbs_curve
    parameter: s
    degree: 3
    control_points_rz: []
    knots: []
    weights: []
  inlet_boundary:
    kind: ruled_between_hub_tip
  outlet_boundary:
    kind: ruled_between_hub_tip

material_domain:
  hub:
    kind: revolved_solid_with_bore
    bore_radius:
    back_face:
    closure_faces:
  shroud:
    kind: none_for_open | front_shroud_for_closed
  material_contract:
    min_wall_thickness:
    require_closed_hub_shell: true

blade_skeleton:
  count:
  span_count:
  streamwise_parameter: u_le_to_te
  span_parameter: v_hub_to_tip
  leading_edge_curve:
    kind: curve_on_meridional_channel
  trailing_edge_curve:
    kind: curve_on_meridional_channel
  stacking_law:
    kind: leading_edge | trailing_edge | centroid | custom_curve
  theta_law:
    kind: beta_integral | m_theta_spline | direct_nurbs_control_net
  beta_distribution:
    hub_control_points:
    tip_control_points:
    interpolation: linear | spline
  wrap_angle:

blade_profile:
  thickness_distribution:
    representation: bezier_or_bspline_field
    hub_profile_points:
    tip_profile_points:
    span_morphing: identical | linear | exponent | spline
  pressure_suction_coupling: symmetric | shifted | independent
  application_direction: mean_line_normal_in_rotational_surface

blade_edges:
  leading_edge:
    kind: simple | linear_elliptic | ellipse | bezier
    parameters:
  trailing_edge:
    kind: simple | linear_elliptic | ellipse | bezier
    parameters:
  root:
    kind: fillet_patch | closure_surface
    radius:
  tip:
    kind: exposed_closed_edge | shroud_join | tip_clearance
    radius_or_clearance:

surface_graph:
  boundary_sharing: explicit
  shaded_surfaces_from_graph: true
  construction_lines_from_graph: true

validation:
  geometry_contracts:
    - radius_positive
    - hub_tip_no_crossing
    - no_internal_axis_touch
    - meridional_wire_orientation
    - blade_root_conforms_to_hub
    - blade_tip_conforms_to_tip_or_shroud
    - pressure_suction_not_swapped
    - edge_closures_present
  topology_contracts:
    - shared_boundary_curves
    - blade_surface_graph_complete
    - hub_material_domain_complete
    - open_tip_not_joined_to_front_shroud
    - closed_tip_joined_or_clearanced_to_front_shroud
  engineering_warnings:
    - beta_angle_plausibility
    - wrap_angle_plausibility
    - blockage_factor
    - leading_edge_thickness
    - root_fillet_nonzero
```

## 7. Validity Contracts To Implement Before More Part Families

### 7.1 Geometry Validity

```yaml
geometry_validity:
  meridional:
    - hub_profile and tip_profile have positive radius
    - hub_profile does not intermittently touch r = 0
    - hub and tip profiles do not cross
    - connector smoothness inside blade region is at least G1
    - no tiny artifact segments below configured tolerance
    - closed meridional wire has expected orientation

  blade_surface:
    - all sampled blade grids are finite
    - v=0 boundary lies on hub support surface
    - v=1 boundary lies on tip reference or shroud surface
    - pressure and suction sides do not intersect or swap
    - leading and trailing edge closure spans are not overlapping
    - blade geometry does not exceed meridional boundaries beyond tolerance

  wireframe:
    - construction lines are sampled from same surfaces as shaded geometry
    - every named surface has u/v construction lines
```

### 7.2 Topology Validity

```yaml
topology_validity:
  - every blade has pressure/suction/LE/TE/root/tip surfaces
  - adjacent surfaces share named boundary curves, not merely nearby coordinates
  - open impeller has exposed closed blade tip and no front shroud material
  - closed impeller has front shroud material and blade-tip join/clearance
  - hub material domain includes outer support surface, back face, bore cylinder, and caps
  - surface graph can produce a watertight preview mesh without CAD booleans
```

### 7.3 Engineering Warnings

```yaml
engineering_warning:
  - blade count plausible for diameter/domain
  - beta inlet/outlet values plausible for selected working_domain
  - wrap angle not too low or too high for surface quality
  - blockage factor below warning threshold
  - leading edge thickness compatible with fluid/application class
  - root fillet radius positive when blade joins hub
  - mounting bore leaves enough hub material
```

Engineering warnings should not block preview generation in v0.2, but they should become
structured loss candidates.

## 8. Loss Generation And Learning Implications

The three current human feedback cases are useful but too few. The literature suggests a
larger automated loss pipeline:

```yaml
loss_sources:
  deterministic_geometry_validator:
    examples:
      - hub_tip_crossing
      - invalid_meridional_wire_orientation
      - blade_root_not_on_hub
      - pressure_suction_swapped
      - missing_edge_closure

  topology_validator:
    examples:
      - boundary_curve_not_shared
      - open_tip_joined_to_shroud
      - material_domain_missing_bore
      - non_watertight_surface_graph

  cad_exporter:
    examples:
      - sew_failure
      - trim_failure
      - nonmanifold_edge
      - degenerate_face

  meshing_precheck:
    examples:
      - patch_identifier_missing
      - bad_aspect_region
      - tiny sliver surface

  engineering_precheck:
    examples:
      - blockage_factor_out_of_range
      - excessive beta span difference
      - implausible leading_edge_thickness
      - wrap angle causing overlap

  human_review:
    examples:
      - natural_language_claim
      - target_surface_or_entity
      - violated_contract
      - proposed_patch_intent
```

This turns "loss" from a small set of ad hoc comments into a contract-indexed corpus.
The learning target is not only numeric parameter correction; it includes ontology edits,
DSL schema edits, constructor algorithm edits, default-parameter edits, and validation-test
edits.

## 9. Devil's Advocate Checkpoint

### Verdict

PASS with major cautions.

### Major Issues

1. **Pump and compressor literature are related but not identical.**
   Compressor impeller geometry sources are useful for blade parameterization, but pump
   hydrodynamics and cavitation impose different engineering defaults. The DSL should
   reuse geometry abstractions, not copy compressor ranges into pump presets.

2. **Public tool manuals are strong for workflow, weaker for derivation.**
   CFturbo/CAESES tell us how professional tools organize the design process. They do not
   fully disclose all algorithms or empirical functions. Use them to structure DSL entities
   and contracts, not as sole mathematical proof.

3. **NURBS everywhere may be over-constraining.**
   Literature supports NURBS/B-spline/Bezier surfaces, but industrial workflows also use
   line/arc segments, polylines, and ruled surfaces. The ontology should allow several
   representations; a specific constructor may choose NURBS.

4. **Mixed-flow inclusion is risky too early.**
   The earlier minimum object allowed radial and mixed. This review suggests starting with
   radial only, because mixed-flow adds more geometry degrees of freedom and ambiguity.

5. **"Watertight by construction" is ambitious.**
   It is the correct north star, but v0.2 may only reach a watertight sampled surface graph,
   not a strict CAD B-Rep solid. The DSL should distinguish preview-mesh validity from
   OCCT solid validity.

### Strongest Counter-Argument

The project may be overfitting to CAD tool workflows rather than physical impeller design.
If the goal is truly engineering-grade design, functional inputs such as flow rate, head,
specific speed, and cavitation constraints should be first-class sooner. The response is to
separate functional design inputs from geometry variables, not to hide geometry behind
physics prematurely.

## 10. Final Recommendation

Freeze the next research object as:

```text
AxisymmetricThroughflowRadialBladedImpeller v0.2
```

Do not yet include mixed, axial, vortex, single-channel, multi-channel, cutter, double-entry,
splitter blades, or non-axisymmetric hub/shroud surfaces.

The next code refactor should be driven by these design rules:

1. Build a named surface graph first.
2. Make hub/tip support surfaces and hub/shroud material domains separate entities.
3. Represent blade geometry as skeleton + thickness + pressure/suction + edge closures +
   root/tip treatment.
4. Generate shaded surfaces and construction lines from the same surface graph.
5. Emit geometry validity, topology validity, and engineering warnings into the manifest.
6. Convert every human or automated defect into a structured `loss_record` tied to violated
   contracts.

## 11. References

- KSB. "Impeller." https://www.ksb.com/en-global/centrifugal-pump-lexicon/article/impeller-1116078
- KSB. "Free-flow impeller." https://www.ksb.com/en-global/centrifugal-pump-lexicon/article/free-flow-impeller-1118154
- KSB. "Waste water applications: Selecting pump impellers." https://www.ksb.com/en-us/solutions/wastewater-technology/wastewater-treatment/waste-water-applications-selecting-pump-impellers
- Grundfos. "Main impeller types." https://www.grundfos.com/content/dam/global/page-assets/learn/ecademy/pdfs/master-36-module-3-Main-impeller-types.pdf
- Hydraulic Institute. "Pump and Pump System Definitions." https://datatool.pumps.org/introduction-definitions-references/table-of-definitions
- CFturbo. "Design of impellers of various types." https://cfturbo.com/software/impellers
- CFturbo Manual. "Meridional contour." https://manual.cfturbo.com/en/mercon.html
- CFturbo Manual. "Hub/Shroud materials." https://manual.cfturbo.com/en/hub_shroud_solids.html
- CFturbo Manual. "Blade profiles." https://manual.cfturbo.com/en/prof.html
- CFturbo Manual. "Blade edges." https://manual.cfturbo.com/en/le.html
- CFturbo Manual. "Blade mean lines." https://manual.cfturbo.com/en/sl.html
- CAESES. "Water Pump Design: Geometry for a Shrouded Impeller." https://www.caeses.com/blog/2017/water-pump-design-geometry-for-impeller-and-casing-optimization/
- Jansen, W., & Kirschner, A. M. (1974). "Impeller blade design method for centrifugal compressors." NASA NTRS. https://ntrs.nasa.gov/citations/19750003125
- Stanitz, J. D., & Prian, V. D. (1951). "A rapid approximate method for determining velocity distribution on impeller blades of centrifugal compressors." NACA TN 2421. https://ntrs.nasa.gov/api/citations/19930083016/downloads/19930083016.pdf
- Agromayor, R., Anand, N., Müller, J.-D., Pini, M., & Nord, L. O. (2021). "A Unified Geometry Parametrization Method for Turbomachinery Blades." Computer-Aided Design, 133, 102987. https://doi.org/10.1016/j.cad.2020.102987
- Koini, G. N., Sarakinos, S. S., & Nikolos, I. K. (2009). "A software tool for parametric design of turbomachinery blades." Advances in Engineering Software, 40(1), 41-51. https://doi.org/10.1016/j.advengsoft.2008.03.008
- Siddappaji, K. (2012). "Parametric 3D Blade Geometry Modeling Tool for Turbomachinery Systems." University of Cincinnati thesis. https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1337264652&disposition=inline
- Tao, R., Xiao, R., & Wang, Z. (2018). "Influence of Blade Leading-Edge Shape on Cavitation in a Centrifugal Pump Impeller." Energies, 11(10), 2588. https://doi.org/10.3390/en11102588
- Ding, H., Li, Z., Gong, X., & Li, M. (2019). "The influence of blade outlet angle on the performance of centrifugal pump with high specific speed." Vacuum. https://cfturbo.com/fileadmin/content/down/publications/papers/2019-01-Vacuum-Journal-CFturbo-Influence-Blade-Outlet-Angle-Centrifugal-Pump-Performance.pdf
- UPC. "Preliminary design of centrifugal pumps: Impeller design." https://upcommons.upc.edu/bitstreams/7652df45-fa36-4c53-8755-692a0f7fbdee/download
