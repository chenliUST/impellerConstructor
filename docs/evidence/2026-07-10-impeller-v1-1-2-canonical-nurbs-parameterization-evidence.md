# Impeller V1.1.2 Canonical NURBS Parameterization Evidence Log

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

## Evidence Scope

This evidence log starts the V1.1.2 semantic change record.

At this stage the work is specification-only. It documents:

- the active worktree;
- the current V1.1.1 baseline;
- the intended V1.1.2 parameterization change;
- the planned verification evidence to collect during implementation.

## Baseline Worktree

```text
worktree = C:\Users\CHEN Li\Documents\TurboJetCase\impeller-v112-hardening
branch = impeller-v1.1.2-acceptance-hardening
base = origin/master
```

Baseline checks already completed when the worktree was created:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_geometry_validation.py -q
result = 23 passed

cd frontend
npm.cmd test
result = 121 passed
```

Local services were then started for inspection:

```text
backend = http://127.0.0.1:8061
frontend = http://127.0.0.1:5199
```

Open V1.1 frontend-payload smoke completed:

```text
preset_id = radial_open_reference_v1_1
validationStatus = PASS
elapsed = approximately 204 seconds
```

## Specification Artifacts

Primary spec:

```text
docs/superpowers/specs/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-spec.md
```

Semantic change log:

```text
docs/evidence/2026-07-10-impeller-v1-1-2-semantic-change-log.md
```

Insight log:

```text
docs/evidence/2026-07-10-impeller-v1-1-2-insight-log.md
```

## Planned Implementation Evidence

The implementation phase should append:

```text
RED/GREEN test transcripts for canonical payload tests
preset translation manifest excerpts for all five active presets
frontend Parameter views screenshot or textual DOM evidence
service smoke for open and closed V1.1.2 presets
mesh/viewer evidence that V1.1.1 surface roles remain compatible
```

## Current Open Risks

1. The first real frontend-payload open preset smoke took roughly 204 seconds. V1.1.2 should not make generation time materially worse without documenting the cause.
2. If the canonical payload is added only to frontend data and not backend manifests, the annotation tab will diverge from generated geometry.
3. If direct NURBS segment-curve input and skeleton-thickness-cap input compile to different internal structures, the project will gain another ambiguous geometry language. They must compile to the same canonical loop family.
