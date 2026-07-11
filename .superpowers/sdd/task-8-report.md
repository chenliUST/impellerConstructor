# Task 8 Report: Browser Acceptance, Evidence, And Regression Gate

## Status

BLOCKED. Task 8 acceptance evidence was implemented and executed, but production contract/rendering defects prevent acceptance. No files outside Task 8 ownership were patched.

## Owned Changes

- Rewrote `frontend/scripts/parameter-inspection-visual-smoke.cjs` for the exact Top, Meridional, desktop S-Q + Blade, and narrow S-Q + Blade contract.
- Added generated-manifest parameter assertions, visible black/red/blue pixel checks, selected-feature contact checks, forbidden-UI checks, layout overlap checks, and renderer/context lifecycle reporting.
- Added four retained screenshots under `docs/evidence/assets/v1.1.3-engineering-parameter-inspection/`.
- Updated the graphical evidence and insight logs with exact results and the authoritative-construction semantic rule.

## Verification

Backend brief command: exit `1` before collection because `tests/test_impeller_v11_2_resources.py` and `tests/test_impeller_v11_surface_family.py` do not exist. A current-filename supplemental run timed out after `1204s` without a result.

Frontend command: `npm.cmd test` from `frontend`.

```text
tests 196
suites 20
pass 196
fail 0
duration_ms 295.4475
```

HTTP after controlled worktree restart:

```text
backend  PID 39960  /api/presets/impeller  HTTP 200
frontend PID 29116  /                      HTTP 200
frontend src/App.js matched the worktree
```

## Browser Smoke

Final command:

```powershell
$env:CODEX_NODE_MODULES='C:\Users\CHEN Li\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node frontend/scripts/parameter-inspection-visual-smoke.cjs
```

Final result: exit `1` after all four screenshots were retained.

- Top context: FAIL, blank drawing interior (`black=0`, `red=0`, `blue=0`).
- Top selection: FAIL, `hub.profile.control.0.r` is not Top-applicable and cannot be selected.
- Meridional root lift: FAIL, red endpoints and blue dimension render but black hub/blade root boundaries do not (`black=0`).
- Desktop S-Q + Blade: FAIL, red 3D feature exists but is detached from blade context (`red=9`, `redNearNeutral=0`).
- Narrow S-Q + Blade: FAIL, detached feature repeats (`red=63`, `redNearNeutral=0`).
- Lifecycle: `createdRenderers=2`, `createdContexts=2`, `liveRenderers=1`, `liveContexts=1`, `lostContexts=0`, `restoredContexts=0`.
- UV, triangle, leader, standalone 3D, and Quad UI are absent; measured boxes do not overlap.

## Production Blockers

1. The generated hub profile control contract advertises only Meridional/Blade 3D applicability, so the required Top selection is disabled and Top has no visible context.
2. Meridional drawing context does not render the authoritative `hub_outer_loop_s_q` and `blade_inner_loop_s_q` root boundaries around the root-lift dimension.
3. `s_q_mm` leading-edge feature geometry is placed as a detached line in the isolated XYZ blade scene rather than on the selected blade.
4. The Task 8 backend command names two nonexistent test files, preventing the specified regression gate from collecting.

## Evidence Paths

```text
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-top.png
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-meridional.png
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/desktop-s-q-blade.png
docs/evidence/assets/v1.1.3-engineering-parameter-inspection/narrow-s-q-blade.png
```

Semantic rule:

```text
parameter selection identifies authoritative construction evidence;
it never substitutes whole-surface material highlighting for feature geometry.
```
