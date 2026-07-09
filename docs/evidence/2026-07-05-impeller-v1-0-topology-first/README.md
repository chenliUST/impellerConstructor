# V1.0 Topology-First Evidence Log

**Date:** 2026-07-05

This directory records the evidence behind the V1.0 impeller constructor semantic change.

## Purpose

V1.0 changes the rule of construction from:

```text
pressure/suction surfaces + post-generated transitions
```

to:

```text
closed multi-face topology generated from the beginning
```

The files in this directory must remain available for future review so the project does not repeat the V0.9-V0.97 cycle of local fixes.

## Files

- `public-references.md`
  Public sources supporting NURBS/B-spline, topology-first, and CAD-validity decisions.
- `geometry-diagnostics.md`
  Current V0.97 failure diagnostics that motivated the rewrite.
- `insight-log.md`
  Engineering lessons learned from V0.9 through V0.97.
- `semantic-change-log.md`
  Explicit semantic changes introduced by V1.0.
- `test-transcript-summary.md`
  Commands and pass/fail counts recorded during V1.0 implementation.
- `blade-to-blade-loop-sandbox.html`
  Standalone 2D blade-to-blade loop sandbox used during V1.1 construction-rule discussion.

## Worktree Policy

Implementation should happen in a new worktree:

```text
C:/Users/CHEN Li/Documents/TurboJetCase/impellerConstructor/.worktrees/impeller-v1.0-topology-first
```

The current V0.97 worktree should remain as historical evidence until V1.0 has passed acceptance.
