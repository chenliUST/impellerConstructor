# Impeller V1.1 Preset, Hub Solid, And Display Tuning Spec

Date: 2026-07-08

## Intent

This is a V1.1 patch-level refinement, not a new version. It keeps the blade-to-blade five-loop surface-family architecture and tunes the default presets so the generated model is easier to inspect.

## Requirements

- V1.1 open and closed presets must keep six main blades and six splitter blades.
- The blade-to-blade loop must have a larger flow-direction turn and visible variation across blade height.
- The loop centerline should be smooth and mostly monotone; it must not use the earlier strong S-shaped reversal.
- Leading and trailing edge loops must use denser rounded cap controls so the nose/tail are visibly smoother and less sharp.
- The open impeller must keep the tip reference surface hidden by default.
- The hub must be emitted as an explicit solid review model:
  - curved profile revolve outer support;
  - top annulus around the mounting bore;
  - bottom annulus below the hub profile with finite bottom thickness;
  - bottom outer cylindrical wall;
  - mounting bore inner cylindrical wall.
- The hub and pressure/suction blade faces are green.
- Other review faces, including leading/trailing/root/tip and mounting bore faces, are yellow.
- Each emitted sampled surface keeps UV wireframe enabled.

## Implementation Contract

- Defaults are stored in the V1.1 DSL preset bundle, not as frontend-only values.
- Frontend V1.1 preset parameters mirror the backend defaults so UI generation does not overwrite the intended model.
- Frontend blade-to-blade preview controls are sampled from the same V1.1 loop construction family and serve as editable initial controls only.
- Existing V1.0/V1.0.4 resources remain unchanged except for this patch's explicit correction of an accidental local frontend edit during implementation.

## Validation

- Add failing tests before implementation for preset defaults, loop turn/height variation, dense LE/TE controls, hub solid faces, and backend display colors.
- Required verification:
  - `python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_six_face_surface_family.py -q`
  - all V1.1 backend tests
  - frontend `npm.cmd test`
  - open and closed V1.1 service smoke with `geometry_validation_status == PASS`.
