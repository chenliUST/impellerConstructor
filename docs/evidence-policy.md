# Evidence And Large Asset Policy

This repository keeps research evidence when it explains why a DSL version changed. Evidence should be intentional, reproducible, and easy to distinguish from generated scratch output.

## Keep In Git

Keep these artifacts in git:

- design specs and implementation plans under `docs/superpowers/`
- evidence READMEs that describe observed behavior
- small screenshots needed to explain a visual issue or accepted baseline
- scripts that regenerate diagrams, reports, videos, or sweep data
- small generated diagrams under `docs/impeller_parameter_diagrams/`
- checksum or provenance notes for large external artifacts

## Avoid Adding To Git

Avoid adding these artifacts directly to git unless there is a deliberate review reason:

- large MP4 renders
- large sweep-data JavaScript or JSON payloads
- repeated screenshots that do not document a distinct research decision
- temporary local run output
- local collaboration files
- Python caches, Node modules, virtual environments, and build output

## Current Large Tracked Evidence

The `videos/impeller-v03-parameter-sweep/` folder currently contains tracked visual evidence and generated data for the v0.3 sweep. It is useful research evidence, but it is large enough that future video/data evidence should preferably move to one of these forms:

- GitHub release artifact with a checksum recorded in git
- Git LFS asset
- regenerated-on-demand output from a committed script

## Recommended Evidence Record Shape

Each evidence folder should include a `README.md` with:

- date
- related DSL version or commit
- command or script used to produce the artifact
- what the artifact proves
- what the artifact does not prove
- whether the source data is committed, external, or regenerable

## Cleanup Rule

Generated output belongs in git only when it is part of a research decision. Otherwise it belongs under ignored local output folders such as `runs/`, `renders/`, `.pytest_cache/`, or tool-specific cache folders.
