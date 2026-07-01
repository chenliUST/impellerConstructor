# Impeller Constructor

Research codebase for deterministic, ontology-facing impeller rule synthesis.

The current focus is the `AxisymmetricThroughflowRadialBladedImpeller` slice: a parametric impeller constructor whose JSON DSL, Python runtime compiler, geometry kernel, manifest contracts, and frontend inspector evolve together.

## Current Status

This repository is a research-grade CAD/CAE integration prototype, not a production CAD kernel.

- Latest slice: `impeller.axisymmetric_throughflow_radial_bladed`
- Latest DSL version: `v0_4`
- Latest frontend workflow: v0.4 open/closed throughflow presets with CAD review, CFD full-360, and feature-debug views
- Geometry exactness: sampled research surfaces with explicit metadata; exact industrial B-Rep fillets, meshing adapters, and solver adapters are future work

## Version Lineage

Earlier versions are preserved in both Git history and versioned DSL folders.

| Version | Location | Preset ids | Purpose |
| --- | --- | --- | --- |
| `v0_2` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2` | `radial_open_reference`, `radial_closed_reference` | First focused axisymmetric throughflow DSL slice and runtime contract. |
| `v0_3` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3` | `radial_open_reference_v0_3`, `radial_closed_reference_v0_3` | Solid hub/hood modeling, staged generation, and curve editor workflow. |
| `v0_4` | `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4` | `radial_open_reference_v0_4`, `radial_closed_reference_v0_4` | Optimization-ready design space, surface/feature graph, and CFD full-360 manifest. |

See [docs/version-history.md](docs/version-history.md) and [src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md](src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/VERSION_INDEX.md).

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

The current v0.4 branch was validated with:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests -q
python -m compileall -q src
cd frontend
npm.cmd test
npm.cmd run build
```

Expected current results:

- Backend tests: `107 passed`
- Frontend tests: `43 passed`
- Frontend build check: passed

## Development Notes

- Keep DSL versions additive and immutable once used as research evidence.
- Add a new version folder instead of overwriting old DSL semantics.
- Preserve evidence screenshots, reports, and update plans that explain why a DSL version changed.
- Do not treat sampled fillet/blend surfaces as exact CAD operations; use `cad_exactness` metadata to distinguish research geometry from future B-Rep output.
