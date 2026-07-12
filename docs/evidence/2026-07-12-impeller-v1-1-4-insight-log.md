# Impeller V1.1.4 Insight Log

## Canonical Fields Can Bypass Legacy Corrections

The splitter collision was not a bad phase constant. The canonical skeleton branch
replaced the legacy camber function that contained the passage-bisector correction.
The splitter then sampled the full main skeleton using its own shorter normalized
interval, so equal normalized coordinates no longer represented equal physical `s`.
Any future canonical-field migration must audit behavior that lived in the fallback
evaluator before removing that path.

## Attachment Offsets Consume Real Flowpath Height

The old closed preset had roughly 39 mm of raw trailing-edge span while requesting
19 mm offsets at both hub and shroud. The mapper's safety caps left only about ten
percent of the span, producing a blade that visually lay on the hub. Root and shroud
offset feasibility must be measured after support-profile correspondence, not
validated as independent positive numbers.

## Parameter Direction Is Not A Stable Geometric Contract

A raw NURBS `v` direction can reverse without changing the surface. Review contracts
therefore need orientation-aware geometric measurements. V1.1.4 records a named
span-to-hub-meridional-tangent angle and active height; a future exact B-Rep release
should add the material-side oriented surface dihedral as a separate invariant.

## Review And Design Are Different Product Modes

Presenting coupled geometric inputs as independent fields created false affordances,
stale override state and a large rendering surface. Until constraint propagation is
designed, a preset-only review workspace is the more truthful interface. Historical
editor code is retained, but it is not part of the active application state graph.

## Engineering Drawings Should Read Geometry Directly

The active drawings use resolved surface boundaries, support-surface meridional
samples and representative S-Q loops. They do not build thousands of selectable
parameter records. Actual sampled support curves and their control polygons are
drawn as distinct entities so the control polygon cannot be mistaken for the NURBS
curve itself.

## Preset Defaults Must Have One Owner

Filling a nominally empty instantiate request from `presets[0]` made the active
preset selector cosmetic: closed and public presets inherited the open preset's
total blade count while retaining their own canonical main/splitter populations.
Preset-only review therefore sends no scalar defaults. The synthesized backend DSL
is the sole owner of preset defaults.

## Repeated Geometry Dimensions Need Semantic Deduplication

Inspection parameters are intentionally repeated across blade instances and span
stations, but an engineering drawing should dimension a representative repeated
feature once. Directly selecting every attachment parameter produced 37 coincident
root dimensions. Drawing contracts now deduplicate root/shroud attachment dimensions
by semantic feature before layout.

## Deterministic Run IDs Still Need Explicit UI Refresh

Regenerating unchanged geometry returns the same run id. Clearing a drawing contract
and relying only on the run id as a React effect dependency leaves the drawing empty.
The review workspace now carries an explicit drawing revision so an intentional
regeneration always refetches the generation-bound contract.
