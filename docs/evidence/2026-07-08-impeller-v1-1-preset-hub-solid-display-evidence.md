# Impeller V1.1 Preset/Hub/Display Evidence

Date: 2026-07-08

## User Insight

The current blade generation was close enough to keep the V1.1 blade-to-blade surface-family architecture, but the default preset needed better inspection geometry:

- flow-direction blade angle needed to be larger;
- blade-height stations needed visible angle variation;
- the blade loop should avoid obvious S-shaped twisting;
- leading and trailing edge caps were too sharp;
- the hub needed explicit solid thickness and a mounting bore;
- hub plus pressure/suction faces should be green, with other faces yellow.

## Root Cause

V1.1 had already moved to blade-to-blade loop construction, but the centerline camber was still hard-coded in `impeller_v11_blade_to_blade_loop.py` as a strong sinusoidal S-shaped function. The V1.1 preset did not expose flow-turn or spanwise-turn defaults. Hub support was emitted only as a profile revolve surface, without explicit bottom thickness, annulus faces, or bore wall. Colors mostly depended on frontend fallback maps instead of backend surface display metadata.

## Change Summary

- Added V1.1 DSL defaults:
  - `main_flow_turn_q_mm`;
  - `splitter_flow_turn_q_mm`;
  - `spanwise_flow_turn_delta_q_mm`;
  - `midspan_bow_q_mm`;
  - LE/TE cap roundness;
  - 13-control LE/TE caps.
- Replaced the fixed S-shaped loop camber with monotone flow turn plus mild midspan bow and blade-height variation.
- Added cap q-overshoot limiting for interior cap samples while preserving endpoint C2 samples.
- Added explicit V1.1 hub solid sampled faces: top annulus, bottom annulus, bottom outer wall, and mounting bore wall.
- Added backend display policy for green/yellow face coloring and UV wire color.
- Synchronized frontend V1.1 open/closed preset parameters and blade-to-blade preview controls.

## Verification Evidence

- `python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_six_face_surface_family.py -q`
  - Result: `25 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `58 passed`
- `cd frontend; npm.cmd test -- appModel.test.js`
  - Result: full frontend test script executed; `128 passed`
- Service smoke for `radial_open_reference_v1_1` and `radial_closed_reference_v1_1`
  - Result: STEP export completed for both.
  - Both manifests reported `geometry_version = 1.1`.
  - Both manifests reported `geometry_validation_status = PASS`.

## Root Attachment Correction

User observation: the root surface rendered as a swollen standalone band rather than a transition from the blade exterior to the hub. The suspected cause was correct: the first blade loop was still effectively on the hub, and `_root_attachment_surface()` converted the blade root loop's `s/q` samples back to the hub profile for both the inner and outer root boundaries.

Fix:

- `root_blade_lift_mm` is now an explicit V1.1 loop-family default.
- The V1.1 domain mapper lifts `h = 0` off the hub by the requested root blade lift, while keeping `h = 1` on the tip/shroud profile.
- The root attachment inner boundary now uses the real blade loop `points_xyz`, so it shares the same edge as the pressure, suction, leading-edge, and trailing-edge blade surfaces.
- The old sinusoidal middle-row root bulge was removed; root rows now interpolate from the hub outer footprint to the blade root loop with a smooth `smootherstep` parameter.

Verification evidence after correction:

- `python -m pytest tests/test_impeller_v11_root_attachment_surface.py::test_high_twist_root_attachment_inner_loop_is_lifted_blade_foot_not_hub_loop -q`
  - Result: `1 passed`
- `python -m pytest tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_resources.py -q`
  - Result: `22 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `61 passed`
- HTTP smoke on `http://127.0.0.1:8061` for `radial_open_high_twist_thin_reference_v1_1`
  - Manifest: `geometry_version = 1.1`
  - Manifest: `geometry_validation_status = PASS`
  - `blade_0_root_attachment_surface.v1_1_root_quality.root_blade_lift_min_mm = 16.000001`
  - `blade_0_root_attachment_surface.v1_1_root_quality.root_blade_lift_max_mm = 18.088924`

## Closed Shroud Attachment Correction

Question resolved: `root_blade_lift_mm` is not hard-coded in the builder. It is a V1.1 loop-family default carried by each preset and can be overridden through `blade_to_blade_loop_family_overrides`. The closed shroud attachment needed the same topology rule as root: the blade boundary should be offset from the support reference surface, and the attachment surface should bridge from the true blade boundary to that reference surface.

Fix:

- Added `shroud_blade_inset_mm` as the closed-shroud counterpart to `root_blade_lift_mm`.
- The V1.1 domain mapper now keeps closed-impeller blade tip loops inside the shroud reference surface by `shroud_blade_inset_mm`.
- `closed_shroud_attachment_surface` now interpolates from the true `blade_tip_loop` to a projected `shroud_reference_loop`, instead of extruding along the previous span direction.
- The closed preset defaults `shroud_blade_inset_mm = 16.0`; local feasibility can reduce actual measured inset where the hub-to-shroud span is small.

Verification evidence:

- `python -m pytest tests/test_impeller_v11_tip_or_shroud_surface.py::test_closed_shroud_attachment_bridges_blade_tip_to_shroud_reference_surface -q`
  - Result: `1 passed`
- `python -m pytest tests/test_impeller_v11_tip_or_shroud_surface.py -q`
  - Result: `7 passed`
- `python -m pytest tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py tests/test_impeller_v11_six_face_surface_family.py -q`
  - Result: `21 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `62 passed`
- Closed shroud diagnostic for `radial_closed_reference_v1_1`
  - `shroud_blade_inset_requested_mm = 16.0`
  - `shroud_blade_inset_min_mm = 13.507663`
  - `shroud_blade_inset_max_mm = 16.293513`

## First Open Preset High-Twist Shape Correction

User observation: the generated first open preset still looked radially distributed, the tip reference surface still started at `R = 230`, and the blades remained too thick. Root cause: the new high-twist/thin visual data had been added mainly to `radial_open_high_twist_thin_reference_v1_1`, while the first UI preset and default backend open preset still used the older `radial_open_reference_v1_1` values.

Fix:

- Promoted the high-twist/thin inspection shape into the first open V1.1 preset `radial_open_reference_v1_1`.
- Set first-open blade thickness to `18.0 mm`.
- Set first-open q-turn defaults to `main_flow_turn_q_mm = 320.0`, `splitter_flow_turn_q_mm = 230.0`, and `spanwise_flow_turn_delta_q_mm = 76.0`.
- Set first-open tip/shroud profile radii to the requested sequence:
  - `P0 R = 300`
  - `P1 R = 320`
  - `P2 R = 350`
  - `P3 R = 400`
  - `P4 R = 490`
  - `P5 R = 581`
- Synchronized the frontend first open preset parameters, profile editor defaults, blade-to-blade curve controls, and module cache-bust version `v=1.1.3`.
- Added cap and surface resampling safeguards so the stronger q-turn does not reintroduce edge segment spikes.

Verification evidence:

- `python -m pytest tests/test_impeller_v11_resources.py::test_v11_open_runtime_contract -q`
  - Result: `1 passed`
- `python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_six_face_surface_family.py -q`
  - Result: `35 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `62 passed`
- `cd frontend && npm.cmd test`
  - Result: `129 passed`
- HTTP smoke on `http://127.0.0.1:8061` for `radial_open_reference_v1_1`
  - Manifest: `geometry_version = 1.1`
  - Manifest: `geometry_validation_status = PASS`
  - Manifest parameter: `blade_thickness_mm = 18.0`
  - `open_tip_reference` first sampled point: `[300.0, 0.0, 407.0]`
  - Computed first sampled radius: `300.0`
- Frontend smoke on `http://127.0.0.1:5199`
  - HTTP status: `200`
  - Entry module cache-bust contains `main.js?v=1.1.3`

## Thin-Blade Leading/Trailing Edge Spike Correction

User observation: when the first open V1.1 preset uses thinner blades, the leading-edge and trailing-edge surfaces showed obvious local spikes. The root cause was in the blade-to-blade loop cap builder, not in the 3D surface mesher: the old cap used a quintic Hermite strip plus several streamwise limiters, but it had no explicit physical contract for cap sagitta. With `s` stored as a unitless streamwise fraction and `q` stored as millimeters, the old mixed-unit Hermite logic allowed the internal cap nose to overrun to about `3.3x` local blade thickness.

Fix:

- Replaced the V1.1 leading/trailing cap generator with a physical half-thickness semicircular cap in the `s_mm-q_mm` domain.
- Added `streamwise_metric_scale_mm` from the hub profile polyline length so `s` is converted to millimeters before measuring cap shape and C2 continuity.
- Set default leading/trailing cap sagitta to exactly `0.5 * local_thickness_mm`.
- Switched side-curve endpoint progression from `smoothstep` to `smootherstep`, giving pressure/suction side endpoints a flatter first and second derivative for C2-compatible semicircular caps.
- Kept adjacent side curvature in the first two cap samples, but limited it by the first physical segment length of the semicircular cap so the old Hermite overrun cannot return.

Verification evidence:

- New regression test: `tests/test_impeller_v11_loop_c2_continuity.py::test_edge_caps_default_to_half_local_thickness_sagitta`
  - Before fix: failed with `sagitta = 39.950264485825755 mm`, expected `6.0 mm`.
  - After fix: passes.
- `python -m pytest tests/test_impeller_v11_loop_c2_continuity.py -q`
  - Result: `9 passed`
- `python -m pytest tests/test_impeller_v11_six_face_surface_family.py::test_v11_edge_surfaces_do_not_have_endpoint_segment_length_spikes -q`
  - Result: `1 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `63 passed`
- Backend restarted on `http://127.0.0.1:8061`
  - PID: `10808`
- HTTP smoke on `http://127.0.0.1:8061` for `radial_open_reference_v1_1`
  - Manifest: `geometry_version = 1.1`
  - Manifest: `geometry_validation_status = PASS`
  - `leading_edge` local thickness: `12.0 mm`
  - `leading_edge` sagitta: `6.0 mm`
  - `leading_edge` sagitta/thickness ratio: `0.5`
  - `trailing_edge` local thickness: `12.0 mm`
  - `trailing_edge` sagitta: `6.0 mm`
  - `trailing_edge` sagitta/thickness ratio: `0.5`

## Splitter Passage-Bisector Position Correction

User observation: each splitter blade was too close to the neighboring main blade on one side, and the root region could visibly collide. The intended topology is that one splitter blade should approximately bisect the passage formed by two adjacent main blades.

Root cause:

- The old V1.1 splitter used `splitter_phase_offset_pitch = 0.5`, but its `q` camber curve was independently parameterized over the shorter splitter interval and started from `q = 0`.
- At the same global streamwise station `s`, the main blade already has significant camber `q`; therefore a half-pitch phase alone does not place the splitter at the main-to-main passage centerline.
- Measured before correction on `radial_open_reference_v1_1`: splitter passage fraction was about `0.08 .. 0.34`, explaining why the splitter sat near one main blade instead of centered in the passage.

Fix:

- Added explicit preset semantics:
  - `splitter_positioning_mode = "main_passage_bisector"`
  - `splitter_passage_fraction = 0.5`
- Updated open, high-twist-thin open, and closed V1.1 presets to declare this positioning rule.
- Changed the V1.1 loop constructor so the splitter centerline is computed from the adjacent main-blade passage at each `s,h`, not from an independent local splitter camber starting at zero.
- Added constructor metrics:
  - `splitter_positioning_status`
  - `splitter_passage_fraction_min`
  - `splitter_passage_fraction_max`
  - `splitter_passage_fraction_avg`
- Slightly widened only the local `q` boundary envelope used by leading/trailing cap C2 point inheritance, so the centered splitter can keep C2 continuity without relaxing the half-thickness `s` sagitta constraint.

Verification evidence:

- New regression test: `tests/test_impeller_v11_main_splitter_domain.py::test_splitter_centerline_bisects_adjacent_main_passage_across_span`
  - Before fix: failed with minimum passage fraction `0.07865710741526244`.
  - After fix: passes.
- `python -m pytest tests/test_impeller_v11_main_splitter_domain.py -q`
  - Result: `12 passed`
- `python -m pytest tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q`
  - Result: `21 passed`
- `python -m pytest tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_six_face_surface_family.py -q`
  - Result: `14 passed`
- V1.1 backend suite via explicit PowerShell file expansion:
  - Result: `64 passed`
- Backend restarted on `http://127.0.0.1:8061`
  - PID: `23220`
- HTTP smoke on `http://127.0.0.1:8061` for `radial_open_reference_v1_1`
  - Manifest: `geometry_version = 1.1`
  - Manifest: `geometry_validation_status = PASS`
  - Manifest loop-family metric: `splitter_positioning_status = PASS`
  - Manifest loop-family metric: `splitter_passage_fraction_min = 0.499894967`
  - Manifest loop-family metric: `splitter_passage_fraction_max = 0.50008856`
  - Manifest loop-family metric: `splitter_passage_fraction_avg = 0.500026951`
