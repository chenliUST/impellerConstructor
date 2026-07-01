# Impeller Constructor

Research codebase for deterministic, ontology-facing impeller rule synthesis.

The current focus is the `AxisymmetricThroughflowRadialBladedImpeller` slice: a parametric impeller constructor whose JSON DSL, Python runtime compiler, geometry kernel, manifest contracts, and frontend inspector evolve together.

## Current Status

This repository is a research-grade CAD/CAE integration prototype, not a production CAD kernel.

- Canonical workspace repository: `impellerConstructor`
- Latest slice: `impeller.axisymmetric_throughflow_radial_bladed`
- Latest DSL version: `v0_5`
- Latest frontend workflow: v0.5 open/closed throughflow presets with CAD review, CFD full-360, feature-debug views, and surface-graph-faithful exports
- Current export status: v0.5 impeller STL/STEP downloads are generated from `manifest.geometry.surface_graph` and include export-region provenance
- Legacy export status: v0.4 and older impeller exports remain CadQuery analysis-review artifacts and are not claimed as surface-graph-faithful
- Geometry exactness: sampled research surfaces plus graph-derived faceted export shells; exact industrial B-Rep fillets, meshing adapters, and solver adapters are future work

The older sibling directory `part-rule-synthesis` is an archived baseline snapshot. Current work should happen in this repository.

For the precise research boundary, see [docs/current-research-frontier.md](docs/current-research-frontier.md).

## Version Lineage

Earlier versions are preserved in both Git history and versioned DSL folders.

| Version | Location | Preset ids | Purpose |
| --- | --- | --- | --- |
| `v0_2` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2` | `radial_open_reference`, `radial_closed_reference` | First focused axisymmetric throughflow DSL slice and runtime contract. |
| `v0_3` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3` | `radial_open_reference_v0_3`, `radial_closed_reference_v0_3` | Solid hub/hood modeling, staged generation, and curve editor workflow. |
| `v0_4` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4` | `radial_open_reference_v0_4`, `radial_closed_reference_v0_4` | Optimization-ready design space, surface/feature graph, and CFD full-360 manifest. |
| `v0_5` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5` | `radial_open_reference_v0_5`, `radial_closed_reference_v0_5` | Surface-graph-faithful STL/STEP export contract with region provenance. |

See [docs/version-history.md](docs/version-history.md) and [src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md](src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md).

The v0.5 design package is recorded in:

- [v0.5 design spec](docs/superpowers/specs/2026-07-01-impeller-v0-5-surface-graph-faithful-export-design.md)
- [v0.5 implementation plan](docs/superpowers/plans/2026-07-01-impeller-v0-5-surface-graph-faithful-export.md)
- [v0.5 mismatch evidence](docs/evidence/2026-07-01-impeller-v0-5-surface-graph-faithful-export/README.md)

## Repository Map

- `src/part_rule_synthesis/`: backend service, DSL resource loading, runtime compiler, kernels, graph contracts, and CFD manifest generation
- `src/part_rule_synthesis/dsl/impeller/`: versioned impeller DSL resources
- `src/part_rule_synthesis/ontology/impeller/`: versioned ontology resources
- `frontend/`: browser-based impeller inspector and interactive parameter editor
- `tests/`: backend acceptance and unit tests
- `docs/`: design specs, implementation plans, evidence, diagrams, and kernel notes
- `videos/`: generated visual evidence and HyperFrames video material

See [docs/repository-map.md](docs/repository-map.md).

## Backend Quick Start

PowerShell from the repository root:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests -q
python -m compileall -q src
```

Start API service from a Python shell or script via `part_rule_synthesis.api:create_app`, or run tests against `RuleSynthesisService` directly.

## Frontend Quick Start

PowerShell from the repository root:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
npm.cmd run dev
```

The frontend expects the API base shown in the UI. By default this is `http://127.0.0.1:8040`.

## Validation Commands

Use the repository-level verification helper from the repository root:

```powershell
.\scripts\verify_repository.ps1 -Mode fast
.\scripts\verify_repository.ps1 -Mode full
.\scripts\verify_version_lineage.ps1
```

`fast` runs compileall, focused backend contract tests, frontend tests, and the frontend build check. `full` runs all backend tests plus the frontend checks.
`verify_version_lineage.ps1` checks the current versioned resource folders through v0.5 and the historical `impeller-dsl-v0.2`, `impeller-dsl-v0.3`, and `impeller-dsl-v0.4` tags through temporary git worktrees.

Expected current results:

- Backend tests: `115 passed`
- Frontend tests: `44 passed`
- Frontend build check: passed

## Development Notes

- Keep DSL versions additive and immutable once used as research evidence.
- Add a new version folder instead of overwriting old DSL semantics.
- Keep historical tags available locally with `git fetch --unshallow --tags origin` when cloning shallow.
- Preserve evidence screenshots, reports, and update plans that explain why a DSL version changed.
- Do not treat sampled fillet/blend surfaces, graph-derived faceted STEP shells, or analysis-review exports as exact industrial CAD operations; use `cad_exactness` and export fidelity metadata to distinguish research geometry from future B-Rep output.
- Follow [docs/evidence-policy.md](docs/evidence-policy.md) before adding generated video, sweep data, or large visual artifacts.
