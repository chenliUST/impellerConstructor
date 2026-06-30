# Axisymmetric Throughflow Radial Bladed Impeller DSL v0.4 Changelog

Date: 2026-07-01

Supersedes: `v0_3`

## Motivation

v0.4 introduces an optimization-ready surface/feature graph contract so the same DSL can support CAD review, full-360 CFD manifest generation, future FEA solid views, and structured loss traceability.

## Changes

1. Added `design_space` with topology variables, design variables, and campaign freeze rule.
2. Added boundary-guided blade surface model.
3. Added feature graph semantics for blade transitions, assembly features, and schema-only tuning features.
4. Added `simulation_views` for `cad_review_360`, executable `cfd_full_360`, and schema-only `fea_solid`.
5. Added group + instance CFD patch naming.
6. Added feature suppression rules for internal assembly features in CFD view.

## Implementation Status

The first implementation emits research-grade sampled surfaces and CFD manifests. It does not provide exact industrial B-Rep fillets, periodic sector CFD domains, solver adapters, or mesh adapters.
