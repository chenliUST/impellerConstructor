# V1.0 Insight Log

**Date:** 2026-07-05

## Insight 1: Post-Transition Modeling Is The Wrong Center Of Gravity

V0.9-V0.97 repeatedly tried to build pressure and suction faces first, then infer transition faces. This places the hardest topology and continuity decisions after the main surfaces already exist.

V1.0 moves those decisions into the original construction rule.

## Insight 2: A Fillet Is Not Just A Radius

The frontend exposed fillet/chamfer radius controls as if a transition could be fully defined by a scalar. In blade-edge and root topology, a robust transition also needs:

- edge-family orientation;
- section profile law;
- material-side convention;
- adjacent face derivative contract;
- corner behavior;
- local feasibility.

V1.0 therefore stops treating blade edge faces as generic edge treatments.

## Insight 3: Root-To-Hub Is A Dedicated Topology, Not An Edge Fillet

The root-to-hub area joins blade, hub, leading/trailing corners, and radial/axial hub parameterization. It cannot be solved by the same generic code that builds leading/trailing strips.

V1.0 makes the root a named annular NURBS face with its own construction law.

## Insight 4: Chamfers Should Be Hub Profile Segments

Hub bottom, bore top, and bore bottom chamfers failed because they were reconstructed after hub surface generation. These faces are naturally profile segments in the R-Z revolve definition.

V1.0 moves hub bevel/chamfer faces into the hub profile constructor.

## Insight 5: Shared Edge Identity Is Stronger Than Trim/Stitch

When two surfaces share the same constructor edge, G0 is structural. When they are separately sampled and later stitched, G0 is a tolerance claim.

V1.0 must prefer shared edge identity and use sewing only as export packaging or diagnostic confirmation.

## Insight 6: Validation Must Inspect Whole Patches

Endpoint tangency, midpoint bulge, and a few sampled lines are insufficient. A surface can fold internally while those measurements pass.

V1.0 validators must inspect all section rows, all station columns, all cell normals, shared edge curves, and face winding.

## Insight 7: G2 Claims Must Be Edge-Scoped

Global `G2` labels hide local failures. V1.0 must attach continuity measurements to named shared edges and extraordinary vertices.

Regular two-face edges can target G2. Multi-face corners should report measured status without unsupported claims.

## Insight 8: Topology-First Must Not Replace Proven NURBS Math

The first V1.0 implementation generated a new simplified hub cylinder and linear blade section network. It satisfied the new topology naming tests but visually regressed to primitive geometry.

Correct V1.0 scope is now tightened:

- the legacy `axisymmetric_throughflow_nurbs` kernel remains the authority for hub, tip/shroud, pressure, and suction `uv_grid` math;
- V1.0 adapts those surfaces into a named topology graph;
- new native leading/trailing/tip/root faces must be derived from actual legacy NURBS boundaries or migrated V0.97 blend builders, not from independent linear primitives;
- open tip support must remain present in the V1.0 review graph, even if older display policy hid it.

## Insight 9: Construction Reference Is Not Display Geometry

Open impellers still need a blade tip reference surface to define the pressure/suction/tip relationship, but showing that support surface as material misleads review. The correct contract is to keep it in the graph for diagnostics and hidden construction use, while the viewer honors `display.visible_by_default = false`.

## Insight 10: Hub Outer Chamfer Should Not Be A Default Feature Yet

The bottom/top outer hub chamfer is not just a local bevel. It changes the outer shell, cap boundaries, hub wall profile, and any adjacent blade-root or boss attachment semantics. Keeping it as a default feature forces premature decisions across too many bodies. V1.0 therefore defers hub outer chamfer by default and keeps only mounting-bore chamfers.

## Insight 11: Root-To-Hub Looks Wrong When Modeled As A Blade Bottom Face

A blade root closure strip connects pressure to suction inside the blade footprint. That is not the physical hub-root interface. The V1.0 root face must be annular:

- outer loop on the hub support surface;
- inner loop on the closed blade root perimeter;
- short direction transitions from hub land to blade exterior;
- inspection style must make it visually separable from hub and blade shades.

This is why the stable surface id can remain `blade_N_root_annular_surface`, but the role must change to `root_pedestal_ring_surface`.

## Insight 12: Three-Column Edge Closure Is Too Weak For G2 Review

A pressure-mid-suction strip can have a nonzero midpoint bulge and still look like a flat chord strip in the viewer. V1.0 needs more short-direction samples and explicit construction metrics so reviewers can see subtle edge-surface shape errors. The current adapter uses 13 short-direction samples for leading/trailing/tip faces and records G2 target metadata without claiming analytic OCCT fillets.

## Insight 13: Runtime Defaults Are Geometry, Not UI Defaults

V1.0.2 showed that attachment defaults are part of the geometry contract. If `resolved_attachment_defaults` are missing, silently falling back to `17` samples or zero-width attachment parameters can produce a surface graph that looks valid but is not tied to the preset feasibility contract.

The constructor now fails closed when resolved defaults are missing or malformed. This keeps preset feasibility, builder inputs, validation, frontend metrics, and exports aligned.

## Insight 14: Root And Closed Tip Attachments Share A Support-Domain Pattern

The root-to-hub and closed-tip-to-shroud joins are not generic edge fillets. They are support-domain attachments:

- inner loop from the blade exterior perimeter;
- outer loop projected onto the support surface;
- short direction sampled with enough resolution to inspect curvature;
- explicit width/lift/default feasibility.

This pattern works for both hub support and closed shroud support while preserving different inspection classes and colors.

## Insight 15: Diagnostic Counts Need Clear Semantics

The same word "foldover" appeared in multiple places with different meanings:

- a G2 builder/global-reference diagnostic count;
- a support-domain or attachment material foldover count;
- an explicit face foldover status.

Treating all of them as blocking would fail default review-grade geometry. Treating none of them as blocking would hide real failures. V1.0.2 separates these fields and blocks only explicit status, attachment-quality foldover, normalized top-level foldover, support-domain violations, loop mismatch, or graph-level builder failures.

## Insight 16: Failure Must Propagate Through Every Layer

A failed V1.0.2 builder must not be allowed to disappear behind an older kernel validity pass. The propagation path is now:

```text
builder/default failure
  -> v1_0_2_transition_failures
  -> continuous_blade_attachment_status = FAIL
  -> surface_graph_status = FAIL
  -> geometry.validity.status = FAIL
  -> manifest.validity.status = FAIL
  -> geometry_validation_status = FAIL
```

This is the guardrail that prevents another screenshot-visible failure from shipping with a green manifest.

## Insight 17: Viewer Diagnostics Must Obey Layer Semantics

Adding shared-edge diagnostic wires helped inspect topology, but lines that do not obey mesh-overlay visibility become visual noise and can hide material surfaces. V1.0.2 marks shared-edge lines as mesh overlays and creates them only when mesh overlay is active.

Inspection colors are also now class-based, not merely face-family based. Root-to-hub and closed-tip attachments have distinct high-contrast palettes so they remain visible against hub, shroud, pressure, and suction shades.

## Insight 18: Attachment Width Must Be Geometric, Not Metadata-Only

The support-domain solver originally computed a tangentially shifted `requested_offset_loop` but returned the unshifted support projection as `outer_loop`. This made root and closed-tip attachment faces nearly zero-width even though `resolved_root_attachment_width_mm` and `resolved_tip_attachment_width_mm` were nonzero.

Correct contract:

- `outer_loop` is the shifted support-surface loop;
- the loop remains on the hub/shroud support radius and z domain;
- attachment width is measurable as outer-inner point distance;
- collapse count must be zero for shipped defaults.

This is a topology rule, not a viewer setting. If the support attachment width is not visible in `uv_grid`, the blade complex is not actually attached as specified.

## Insight 19: Final Visible G2 Edge Caps Are The Attachment Source Of Truth

The first V1.0.2 attachment graph restored `root_profile_*_cap` edge samples from the legacy lattice after replacing the visible leading/trailing edge faces with G2 review surfaces. That created a split-brain topology: shaded edge surfaces used one cap, while root/tip attachment used another.

Correct contract:

- leading/trailing `root_profile_*_cap` equals the final edge surface `uv_grid[0]`;
- leading/trailing `tip_profile_*_cap` equals the final edge surface `uv_grid[-1]`;
- root and closed-tip attachment lattices are rebuilt after edge replacement;
- root/tip inner loops attach to the final visible G2 caps, not to legacy closure caps.

## Insight 20: Attachment Lift Is The Support-Domain Tolerance For G2 Cap Bulge

Once root/tip attachment uses final G2 caps, edge cap interiors can sit slightly outside the support profile z range. This is expected for a visible curved transition: the inner blade loop can rise into blade material while the outer loop stays on hub/shroud support.

Correct contract:

- support projection clamps small z overruns to the nearest support profile boundary;
- the allowed overrun is bounded by the resolved attachment lift;
- larger overruns still fail as support-domain violations;
- the inner loop remains the final G2 cap, so continuity review is not hidden by snapping the blade side back to the support.

## Insight 21: Root Lift Must Not Follow Blade Span Tangent

The screenshot regression with a 180-degree trailing-edge turn came from applying root lift along each blade row's local span tangent. Near the trailing edge, that shifted the root boundary into the blade span direction and created a local z dip:

```text
trailing pressure root z before correction:
  11.033860, 8.936670, 7.722190, 7.390418, 7.941354, ...
max adjacent tangent flip ~= 180 deg
```

The corrected rule lifts pressure/suction root boundaries along the hub revolved-support outward normal and applies a monotonic root guard. The guard preserves part of the original span slope, so it avoids both a root plateau and a root-edge reversal.

## Insight 22: Curvature Proxy Is Diagnostic, Not The Primary Edge-Bulge Direction

The V1.0.2 G2 edge builder briefly mixed curvature proxy into the short-direction bulge vector. At root-adjacent trailing sections the projected curvature proxy could point below the material side, producing internal edge-patch folds even when boundary tangents were smooth.

Correct rule:

```text
primary short-direction bulge = averaged shared-edge material normal
curvature proxy = diagnostic continuity input
fallback to curvature proxy only when material normal is degenerate
```

This keeps leading/trailing/open-tip edge patches from being steered by noisy second-difference samples.

## Insight 23: A Closed Blade Perimeter Needs Component Attachment Patches

A single annular UV patch around the complete blade exterior loop is too coarse for a root or closed-tip attachment. The loop contains pressure, trailing cap, suction, and leading cap segments with corner-like transitions. Connecting all segments in one UV sheet creates artificial cross-corner cells and can fold even when each physical segment is valid.

V1.0.2 now emits visible component patches for support attachments:

```text
root pressure patch
root trailing cap patch
root suction patch
root leading cap patch
```

The aggregate annular surface is retained for topology/diagnostics but hidden by default. This prevents a valid segmented construction from being visually corrupted by a single cross-corner mesh sheet.

## Insight 24: Root Blend Robustness Comes From Domain Ownership

The root blend is stable only when ownership is explicit:

- the blade section loop owns the inner boundary;
- the hub parameter domain owns the footprint and outer boundary;
- segment patches own visible root geometry;
- local cross-product guesses are not allowed to choose material side independently for pressure and suction segments.

V1.0.3 keeps root component roles segment-specific and uses `display.inspection_class = root_to_hub_blend` as the family-level inspection key. This prevents a viewer/test convenience label from erasing the topology fact that pressure-side, suction-side, leading-corner, and trailing-corner root blends are different patches.

## Insight 25: Frontend Version Truth Is A Runtime Contract

The backend can correctly generate V1.0.3 while the browser still shows stale behavior if `index.html`, `main.js`, or `App.js` keep a V1.0.2 cache token. The frontend cache-bust token is therefore part of the release contract, not a cosmetic string.

For V1.0.3, the correct frontend load chain is:

```text
index.html -> /src/main.js?v=1.0.3
main.js -> ./App.js?v=1.0.3
App.js -> ./appModel.js?v=1.0.3
```

## Insight 26: V1.0.3 Must Borrow NURBS Math As A Carrier, Not As A Graph

The primitive-looking V1.0.3 regression was not a frontend version mistake. The runtime was loading V1.0.3, but the section-loop builder was still using a simplified radial mapper for pressure/suction faces. That preserved the new topology labels while losing the previously validated hub and blade-face mathematics.

Correct rule:

- V1.0.3 keeps section-loop topology ownership.
- The older `axisymmetric_throughflow_nurbs_kernel` is used only as a carrier for hub support, pressure rows, and suction rows.
- Generated blade faces report `section_loop_source = v1_0_3_nurbs_carrier_section_lattice`.
- The legacy graph is not copied into V1.0.3, and old V1.0.3 root/tip/front-end work is not reverted.

## Insight 27: Root Lift Is Radial Material-Side Inflation In The Current Solver

Applying root lift along the blade span tangent pushes lifted root loops outside the hub support z-domain and forces projection clamps. Those clamps create root foldovers even when the underlying pressure/suction carrier surfaces are valid.

For the current sampled V1.0.3 solver, the measured material-side root height is `radius - hub_radius(z)`. Root lift therefore must inflate the first carrier section loops radially outward while preserving the carrier z law. This keeps the blade-face NURBS carrier shape, creates a real root inner loop, and lets the root solver project the outer annulus back to the hub domain.

## Insight 28: Root Attachment Size Constrains Preset Streamwise Extents

A 32 mm root width and 32 mm root lift cannot coexist with a blade root footprint that nearly touches the hub profile top and bottom edges. With the older `main_streamwise_start_u = 0.08` and `main_streamwise_end_u = 0.92`, the root solver must clamp many support-domain samples and folds.

The open V1.0.3 preset now uses:

```text
main_streamwise_start_u = 0.38
main_streamwise_end_u = 0.62
splitter_streamwise_start_u = 0.50
splitter_streamwise_end_u = 0.59
```

This is a compliance tradeoff: root width/lift remain review-visible and valid, while blade pressure/suction faces still come from the NURBS carrier instead of the primitive mapper.

## Insight 29: Stale Python Services Can Mix New JSON With Old Geometry Code

The 8060 backend process kept old Python modules loaded while reading updated preset JSON from disk. That created a dangerous mixed state:

```text
geometry_patch_version = 1.0.3
surface_graph_status = PASS
source_math_policy = section_loop_first_blade_faces_segmented_root_blends_open_tip_domes
```

The missing `nurbs_carrier` token proved the service had not loaded the new V1.0.3 carrier code. After backend restart on 8061, the correct smoke signature is:

```text
carrier_source_kernel = axisymmetric_throughflow_nurbs_kernel
source_math_policy = section_loop_first_nurbs_carrier_blade_faces_segmented_root_blends_open_tip_domes
pressure section_loop_source = v1_0_3_nurbs_carrier_section_lattice
```

## Insight 30: Profile Defaults Must Enter The V1.0.3 Carrier, Not Just The Runtime

The frontend showed a conical-looking hub because V1.0.3 compiled constructor `profile_defaults` but did not pass them into `_v10_3_nurbs_carrier_geometry`. The section-loop graph was active, but the carrier silently used generated fallback profiles.

The diagnostic signature was:

```text
constructor profile_defaults = concave NURBS curves
hub_support_surface profile_samples_rz = fallback generated samples
visual result = cone-like hub and inconsistent frontend preset values
```

The fixed signature is:

```text
hub_support_surface.profile_samples_rz[0] = {r_mm: 126.0, z_mm: 118.0}
hub_support_surface.profile_samples_rz[-1] = {r_mm: 600.0, z_mm: 0.0}
pressure/suction angular span > 90 degrees
surface_graph_status = PASS
```

## Insight 31: Root Width Is A Feasibility Constraint On Long Concave Profiles

With the new concave hub carrier and long blades, `root_attachment_width_mm = 10` and `root_attachment_lift_mm = 10` created one root segment foldover per blade even though hub projection itself was valid:

```text
projection residual ~= 1e-9
domain bracket failures = 0
offset self-intersection count = 0
root segment foldover count = 1
```

The stable default is `8 mm` width and `8 mm` lift. This keeps the thin 20 mm blade preset visually inspectable while preserving zero foldover on the root component surfaces and allowing the main blade streamwise range to remain `0.20 -> 0.80`.

## Insight 32: V1.0 Scalar Parameters Are Not The Same As Curve Ownership

The V1.0.3 frontend mismatch came from exposing too many scalar parameters after the algorithm moved to curve-owned hub/tip profiles and section-loop templates. Scalars such as `hub_curve_height_mm`, inlet/outlet blade heights, edge radii, and semantic profile handles can still exist in the DSL/runtime for compatibility, but they must not appear as independent controls when the active construction source is a NURBS/profile/section-loop curve.

The UI contract is now:

```text
ParameterPanel = compact high-level dimensions and material thickness only
Profile/Curve editors = hub profile, tip profile, section-loop, tip dome controls
EdgeTreatmentPanel = transition policy controls when applicable
```

## Insight 33: Root Patch Flips Are A Contract Failure, Not A Local Orientation Bug

The repeated suction-side root failure is not only a reversed row order. The root surface is under-defined unless the builder knows all four of these at construction time:

```text
inner ring = exact blade root loop boundary
outer ring = projected hub-domain offset ring
material side = support-domain signed side, not a local chord guess
short direction = monotone blade-to-hub parameter direction with no foldover
```

V1.0.4 therefore treats root construction as a dedicated annular transition solver. A post-process wrapper around V1.0.3 root patches is not sufficient, because it can measure a failure but cannot repair an inner ring that never matched the blade boundary.

## Insight 34: Tip Surface Size Must Be Bounded By The Blade Tip Loop

The oversized tip surface indicates that the dome builder is using support/reference extents instead of the actual six-face blade loop. For open impellers, the visible tip surface must be a cap/dome over the blade tip loop only:

```text
allowed domain = actual pressure/suction/leading/trailing top boundary loop
forbidden domain = blade tip reference surface, support carrier, or passage-level span
acceptance = tip area ratio <= 1.15 against loop polygon area
```

This is also why open normal review mode must hide the tip reference/support surface. Reference geometry can remain available for diagnostics, but it must not be mistaken for the manufactured blade tip face.

## Insight 35: G2 Cannot Be A Preset Label

The visual reports show straight or right-angle transitions even when the preset says G2. V1.0.4 defines G2 as a measured shared-edge result:

```text
position gap <= 1e-6 mm
tangent angle <= 2 deg
normal angle <= 5 deg
curvature proxy mismatch <= 0.25
```

If any measurement fails, the graph must report `G1_MEASURED_G2_FAILED` or `G0_ONLY_FAILED`. This prevents a versioned graph from appearing valid while the frontend/exported model still contains primitive-looking patches.

## Insight 36: Blade-Hub Review Angle Is A Geometry Feasibility Input

The user needs blade faces to meet the hub at an inspectable angle, roughly 60 to 120 degrees. This is not a cosmetic camera issue. Very shallow blade-hub angles make root lift and material-side validation ambiguous, and they hide whether the root annulus is above the hub or folded into the blade material.

V1.0.4 makes the angle range a measured contract attached to shared edges between blade/root/hub surfaces.

## Insight 33: Root And Tip Geometry Need Bounded Domains, Not Larger Debug Surfaces

The screenshots showed that visually large magenta/yellow patches can make defects easier to notice but can also exceed the real blade domain. V1.0.4 therefore uses bounded root and tip contracts: root width/lift are measured against half blade thickness, and tip area is measured against the actual blade tip loop.

This also changes how root diagnostics are interpreted. `max_parameter_direction_flip_deg` is retained as a diagnostic measurement, not as the pass/fail gate. After the root builder was corrected to match adjacent blade-face derivatives, local parameter-direction curvature can be high while the actual shared-edge G2 measurements still pass:

```text
root_patch_orientation_status = PASS
foldover_count = 0
position/tangent/normal/curvature continuity = G2_MEASURED
max_parameter_direction_flip_deg = diagnostic
```

The blocking root gates are material side, foldover absence, bounded width/lift, and measured continuity to adjacent faces.

## Insight 37: Blade Loops Belong In Blade-To-Blade Domain

The V1.0.4 screenshots and the accepted sandbox show that the previous "section loop" still mixed local chord/thickness coordinates with the streamwise loft direction. That can make the whole blade look like a primitive strip before root, tip, or edge surfaces are even considered.

The corrected V1.1 loop lives in the unwrapped blade-to-blade stream-surface domain:

```text
D_h = (s, q)
s = normalized meridional streamwise coordinate
q = r * delta_theta, circumferential offset in millimeters
h = span station from hub to tip/shroud
```

The meridional hub/tip carrier maps `(s, h)` to `(r, z)`; it does not define the blade loop shape. XY projection is diagnostic only. Main blades and splitter blades use the same domain and the same `(s, q, h) -> (x, y, z)` map. The splitter is shorter in `s` and phase-shifted by half a pitch, rather than being a separately scaled local chord object.

For V1.1, five span loops provide the complete boundary network for six named face families: pressure, suction, leading edge, trailing edge, root, and tip/shroud. Face builders must consume this shared loop-family network and its C2/G2 boundary jets. They must not invent new independent boundary curves after the blade loop has already been generated.

## Insight 38: Frontend Controls Must Match Geometry Payload Ownership

The V1.1 frontend cannot expose the same geometric intent through multiple panels or payload keys. The blade-to-blade loop family is not a generic curve override and must serialize only through:

```text
blade_to_blade_loop_family_overrides
```

Meridional hub and tip/shroud NURBS control belongs to the profile editor and must serialize through:

```text
profile_overrides
```

The previous duplicate exposure made the UI appear editable while edits could become inert or routed through the wrong backend contract. V1.1 therefore separates ownership:

```text
ProfileCurveEditor = hub_profile and tip_or_shroud_profile
CurveControlPanel = blade_to_blade_loop_family only
ParameterPanel = compact scalar preset controls only
```

The browser module cache-bust chain is also part of the frontend contract. When the active UI version changes to V1.1, `index.html`, `main.js`, and `App.js` must all point at `v=1.1`; otherwise users can keep loading the previous preset catalog and report a backend problem that is actually stale frontend code.

The same ownership rule applies below the API boundary. A payload key is not complete merely because it changes a run id or appears in a manifest. For V1.1, editable geometry controls must be consumed before the loop family is sampled:

```text
blade_to_blade_loop_family_overrides -> segment control polygons -> loop points_s_q -> points_xyz -> uv_grid
profile_overrides -> hub/tip profile points -> domain mapper -> points_xyz -> uv_grid
```

Any control that cannot reach this chain must be hidden for V1.1, otherwise the frontend is offering a no-op geometry edit.

## Insight 39: V1.1 Loop Edits Are Shape Templates, Not Absolute Station Geometry

The V1.1 blade-to-blade loop editor shows one compact segment control polygon to the user, but the generated blade contains five span stations and both main and splitter blade domains. A frontend payload therefore cannot be copied as absolute `(s, q)` points into every station.

The failure mode is specific:

```text
h=0 main-blade controls edited in UI
same absolute controls applied to h=0.25/0.5/0.75/1.0 and splitter loops
segment endpoints no longer match those station-specific adjacent surfaces
loop C2 validation fails
surface shared-edge validation fails
export gate blocks the run
```

The corrected rule is topology-owned boundary frames plus editable interior shape:

```text
frontend segment controls define the intended interior shape
backend fits that shape to each actual loop station
backend retains each station's first/last boundary samples
adjacent faces reuse the retained boundary curves
```

For V1.1 frontend controls, the visible default control counts must also match the backend validator:

```text
pressure_side = 11
suction_side = 11
leading_edge = 9
trailing_edge = 9
```

Endpoint movement is not a simple local curve edit in this topology. It changes the ownership boundary between pressure/suction/leading/trailing/root/tip surfaces, so ordinary UI controls should treat endpoints as constrained topology anchors unless a future version introduces an explicit boundary-edit workflow.

## Insight 40: Thin-Blade Edge Caps Need A Physical Sagitta Contract

The thin-blade spike defect showed that "C2 cap curve" is not enough if the curve is constructed in mixed units. V1.1 stores `s` as a normalized streamwise fraction and `q` as millimeters. If Hermite or limiter logic compares those directly, a cap can pass a local sampled continuity test while its physical nose protrudes several blade thicknesses.

The corrected rule is:

```text
convert s to s_mm using hub profile polyline length
construct leading/trailing caps in s_mm-q_mm
default cap sagitta = 0.5 * local_thickness_mm
then measure boundary continuity in the same physical domain
```

This is now a regression contract. For the first open V1.1 preset, the measured edge cap signature is:

```text
local thickness = 12.0 mm
cap sagitta = 6.0 mm
sagitta/thickness = 0.5
```

The broader insight is that every V1.1 validation metric must state its physical units. Mixed normalized and millimeter coordinates can create visually large modeling errors while still producing small-looking numeric differences.

## Insight 41: Splitter Position Is A Passage Constraint, Not A Phase Constant

The splitter collision defect showed that half-pitch phase offset alone is not a stable definition of splitter placement. In a curved impeller, the main blade has a nonzero `q(s,h)` centerline. A splitter with `phase_offset_pitch = 0.5` but an independent local camber reset at `q = 0` can still sit close to one main blade.

The corrected V1.1 rule is:

```text
splitter_positioning_mode = main_passage_bisector
splitter_passage_fraction = 0.5
splitter q(s,h) = main q(s,h) + (target_fraction - phase_offset_pitch) * local_pitch_arc_mm
```

The constructor now reports:

```text
splitter_positioning_status
splitter_passage_fraction_min
splitter_passage_fraction_max
splitter_passage_fraction_avg
```

The current first open V1.1 smoke result is:

```text
min = 0.499894967
max = 0.50008856
avg = 0.500026951
```

This converts splitter/root collision from a visual complaint into a measurable passage-balance constraint.

## Insight 42: V1.1 Ontology Is Currently DSL-Embedded

V1.1 has a real ontology slice, but it is not stored in a separate `src/part_rule_synthesis/ontology/impeller/v1_1` folder. The slice is currently embedded across:

```text
dsl/.../v1_1/schema.json
dsl/.../v1_1/constructors/open_impeller.json
dsl/.../v1_1/constructors/closed_impeller.json
dsl/.../v1_1/export_contracts/blade_to_blade_loop_surface_family_graph.json
dsl/.../v1_1/capability_matrices/impeller_v1_1_kernel_capabilities.json
dsl/.../v1_1/golden_cases/impeller_v1_1_golden_cases.json
```

This is acceptable for the current milestone as long as documentation calls it out explicitly. A future V1.2 or CAD-certification line may justify promoting these embedded semantics into a dedicated ontology resource folder, but doing that now would be a separate migration task, not a silent documentation cleanup.

## Insight 43: Viewer Modes Must Consume Surface Graphs, Not Construction Lines

The V1.1 geometry graph already contains enough sampled surface data for UV and mesh inspection. Rendering only construction or CFD patch lines hides correct geometry and makes failures look like geometry regressions. V1.1.1 therefore treats `uv_grid` as the review source of truth for wireframe and mesh inspection.

The same rule applies to active preset controls: a parameter row is useful only when it maps to the current constructor path. V1.1.1 moved the visible parameter list to preset-owned `editable_parameters` so the UI order and visibility are part of the same contract as the DSL preset.
