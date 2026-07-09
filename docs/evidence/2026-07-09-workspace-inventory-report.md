# Impeller Constructor Workspace Inventory Report

Date: 2026-07-09

Scope: read-only audit of the local V1 topology-first worktree and its Git/cloud readiness. No files were deleted or moved during this audit.

## Executive Summary

The current local workspace contains valuable V1.0-V1.1.1 source, tests, DSL resources, frontend work, specs, plans, and evidence logs. It also contains large generated outputs and smoke artifacts that should not be committed.

Recommended immediate action:

1. Preserve the current worktree as the active V1.1 development workspace.
2. Stage and review source/test/docs in coherent commits, preferably by semantic version slice.
3. Add local run-output paths to `.gitignore` before any commit hygiene work.
4. Archive large generated artifacts outside Git.
5. Push this branch to origin with an upstream and tag verified milestones.

## Current Worktree And Cloud State

Current worktree:

```text
C:\Users\CHEN Li\Documents\TurboJetCase\impellerConstructor\.worktrees\impeller-v1.0-topology-first
```

Current branch:

```text
impeller-v1.0-topology-first-constructor
```

Current HEAD:

```text
dcc62317e48cbdcbb24dcfdb35d3c56aae3df22a
```

Remote:

```text
origin https://github.com/chenliUST/impellerConstructor.git
```

Observed worktrees:

```text
impellerConstructor                                      impeller-v0-6-brep-dev
.worktrees/impeller-v0.6-brep                           impeller-v0.7-bounded-transitions
.worktrees/impeller-v1.0-topology-first                 impeller-v1.0-topology-first-constructor
```

Cloud readiness notes:

- The current V1 branch does not show an upstream in `git branch -vv`.
- Existing tags only cover early DSL milestones: `impeller-dsl-v0.2`, `impeller-dsl-v0.3`, `impeller-dsl-v0.4`.
- There are no observed tags for `v0.97`, `v1.0`, `v1.1`, or `v1.1.1`.

## Git State Summary

Tracked modified files:

```text
39 files modified
3168 insertions
967 deletions
```

Untracked status entries:

```text
102 entries
```

Largest untracked/top-level categories by status grouping:

```text
tests       45
src         36
frontend    30
docs        19
```

Untracked extension distribution:

```text
.py      70
.json    59
.md      22
.step    13
.log      7
.png      3
.svg      3
.js       2
.html     1
.jpg      1
```

Interpretation:

- The repository is not ready for a blind `git add .`.
- Source/test/docs changes are mixed with smoke outputs and large generated mesh/STEP artifacts.
- The `.step` files are especially dangerous for accidental Git commits.

## Directory Size Audit

Generated/runtime artifact directories:

```text
Model Output       196 files   4773.389 MB
.tmp-v111-smoke     37 files   1030.530 MB
model_runs           4 files    434.815 MB
.tmp-v11-smoke      18 files    275.600 MB
rule_engines         3 files      0.170 MB
```

Documentation and DSL source-size candidates:

```text
docs/evidence                                                                      78 files   6.066 MB
docs/superpowers/specs                                                             24 files   0.364 MB
docs/superpowers/plans                                                             20 files   0.899 MB
src/.../axisymmetric_throughflow_radial_bladed/v1_0                                16 files   0.063 MB
src/.../axisymmetric_throughflow_radial_bladed/v1_1                                15 files   0.068 MB
frontend/sandbox                                                                    1 file    0.017 MB
```

Large artifact conclusion:

- `Model Output`, `.tmp-v111-smoke`, `.tmp-v11-smoke`, and `model_runs` should be treated as disposable/generated or archived outside Git.
- `rule_engines` is small but still runtime-generated and should not be source unless intentionally converted into a golden fixture.

## Should Commit

These categories should be reviewed and likely committed:

```text
src/part_rule_synthesis/impeller_v10*.py
src/part_rule_synthesis/impeller_v11*.py
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0/
src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1/
tests/test_impeller_v10*.py
tests/test_impeller_v11*.py
tests/impeller_v10_*_historical_fixture.py
frontend/src/
frontend/index.html
frontend/package.json
docs/superpowers/specs/
docs/superpowers/plans/
docs/version-history.md
docs/repository-map.md
docs/current-research-frontier.md
docs/evidence/*.md
```

Rationale:

- These files encode the V1 topology-first semantics, DSL evolution, validation gates, frontend integration, and regression history.
- The specs/plans/evidence are unusually important in this project because design intent and failure analysis have been part of the engineering process.

## Should Review Before Commit

These should be inspected before staging:

```text
docs/evidence/2026-07-05-impeller-v1-0-topology-first/*.png
docs/evidence/2026-07-05-impeller-v1-0-topology-first/*.svg
docs/evidence/2026-07-05-impeller-v1-0-topology-first/frontend-v1-smoke.jpg
frontend/sandbox/
```

Suggested policy:

- Keep representative images if they document a milestone or a resolved failure mode.
- Remove or externalize images that duplicate evidence already summarized in Markdown.
- Keep `frontend/sandbox/` only if it is part of the reproducible section-loop design evidence; otherwise move to `docs/evidence` or ignore it.

## Should Ignore Or Archive Outside Git

Add to `.gitignore` or keep outside the repository:

```text
model_runs/
rule_engines/
.tmp-*/
*.log
*.err.log
*.mesh.step
*.step
```

Already ignored:

```text
Model Output/
.pytest_cache/
frontend/node_modules/
__pycache__/
```

Reason:

- `Model Output` alone is approximately 4.77 GB.
- Smoke directories contain hundreds of MB to GB of generated mesh/STEP outputs.
- These are reproducible runtime artifacts, not source of truth.

## Suggested Commit Slices

Commit 1: V1.0 topology-first foundation

```text
src/part_rule_synthesis/dsl/.../v1_0/
src/part_rule_synthesis/impeller_v10*.py
tests/test_impeller_v10*.py
tests/impeller_v10_*_historical_fixture.py
docs/superpowers/specs/*v1-0*
docs/superpowers/plans/*v1-0*
docs/evidence/2026-07-05-impeller-v1-0-topology-first/
```

Commit 2: V1.1 blade-to-blade loop surface family

```text
src/part_rule_synthesis/dsl/.../v1_1/
src/part_rule_synthesis/impeller_v11*.py
tests/test_impeller_v11*.py
docs/superpowers/specs/*v1-1*
docs/superpowers/plans/*v1-1*
docs/evidence/*v1-1*
```

Commit 3: service/runtime/validation integration

```text
src/part_rule_synthesis/api.py
src/part_rule_synthesis/impeller_dsl_resources.py
src/part_rule_synthesis/impeller_geometry_validation.py
src/part_rule_synthesis/impeller_mesh_manifest.py
src/part_rule_synthesis/impeller_runtime_compiler.py
src/part_rule_synthesis/impeller_transition_policies.py
src/part_rule_synthesis/service.py
tests/test_impeller_geometry_validation.py
```

Commit 4: frontend V1.1 viewer/preset/parameter overhaul

```text
frontend/index.html
frontend/package.json
frontend/src/
```

Commit 5: project documentation index updates

```text
docs/current-research-frontier.md
docs/repository-map.md
docs/version-history.md
```

## Suggested Branch And Tag Policy

Branch:

```text
impeller-v1.0-topology-first-constructor
```

Suggested upstream action after cleanup:

```text
git push -u origin impeller-v1.0-topology-first-constructor
```

Suggested milestone tags after tests pass and commits are clean:

```text
impeller-v1.0-topology-first
impeller-v1.0.4-section-loop-repair
impeller-v1.1-blade-to-blade-loop
impeller-v1.1.1-viewer-preset-overhaul
```

Tag only after the corresponding source/test/docs commit is present.

## Recommended Cleanup Sequence

1. Update `.gitignore` for runtime artifacts.
2. Re-run `git status --short` and confirm generated artifacts disappear from candidate status.
3. Review and stage source/test/docs by version slice, not all at once.
4. Run focused backend and frontend verification before each semantic commit.
5. Create tags for verified milestones.
6. Push the branch to GitHub with upstream.
7. Optionally archive `Model Output`, `model_runs`, and `.tmp-*` to a separate artifact store, then remove local copies if disk space matters.

## Risk Register

High risk:

- Accidental commit of `.step` / mesh artifacts.
- Losing key V1.0-V1.1 semantic logs if docs are cleaned too aggressively.
- Current branch has no upstream, so cloud state likely does not include recent V1 work.

Medium risk:

- `master` shows ahead of `origin/master` by 6 commits in another worktree; avoid mixing this with V1 branch cleanup.
- Multiple worktrees share the same repository, so branch operations should be done deliberately.

Low risk:

- Existing `.gitignore` already protects `Model Output/`, `.pytest_cache/`, and `frontend/node_modules/`.

## Bottom Line

The source work is valuable and should be preserved. The generated artifacts are large and should be excluded or archived. The best next engineering step is to harden `.gitignore`, then create a small set of coherent commits and tags that make V1.0, V1.1, and V1.1.1 auditable in GitHub.
